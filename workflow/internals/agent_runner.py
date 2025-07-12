# This file is for internal use only and should not be used directly by the end-user. 
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Coroutine

import httpx
from fastmcp import Client as MCPClient
from openai import OpenAI

from mcp.types import Tool
from shared.app_settings import load_app_settings
from shared.config import settings
from workflow.models import CustomAgent, MessageModel, StepOutputData, CustomAgentInstanceModel

logger = logging.getLogger(__name__)


def _get_next_required_tool(
    required_tools_sequence: list[str], completed_required_tools: set
) -> str | None:
    """Returns the next required tool that hasn't been completed yet, or None if all are done."""
    for tool_id in required_tools_sequence:
        if tool_id not in completed_required_tools:
            return tool_id
    return None


def _format_mcp_tools_for_openai(
    tools: list[Tool], server_name: str
) -> list[dict]:
    """Formats a list of MCP Tools into the format expected by OpenAI."""
    formatted_tools = []
    for tool in tools:
        full_tool_name = f"{server_name}-{tool.name}"
        formatted_tool = {
            "type": "function",
            "function": {
                "name": full_tool_name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        formatted_tools.append(formatted_tool)
    return formatted_tools


async def run_agent_step(
    instance: CustomAgentInstanceModel,
    agent_definition: CustomAgent,
    resolved_system_prompt: str,
) -> CustomAgentInstanceModel:
    logger.info(
        f"Starting execution for agent step instance {instance.uuid} of agent {agent_definition.uuid}"
    )

    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not found. Cannot proceed.")
        instance.messages.append(
            MessageModel(
                role="system", content="Error: OPENROUTER_API_KEY not configured."
            )
        )
        instance.status = "failed"
        instance.error_message = "OPENROUTER_API_KEY not found."
        return instance

    llm_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )

    mcp_clients: dict[str, MCPClient] = {}
    try:
        api_url = f"http://localhost:{settings.CONTAINERPORT_API}/mcp/servers"
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(api_url)
            response.raise_for_status()
            servers_info = response.json()
            if not servers_info:
                instance.messages.append(
                    MessageModel(role="system", content="Error: No MCP servers available.")
                )
                return instance

            for server_info in servers_info:
                server_name = server_info.get("name")
                server_url = server_info.get("url")
                if server_name and server_url:
                    mcp_clients[server_name] = MCPClient(server_url)
    except Exception as e:
        logger.error(f"Failed to discover or initialize MCP clients: {e}", exc_info=True)
        instance.messages.append(
            MessageModel(
                role="system", content=f"Error: Could not discover MCP servers. {e}"
            )
        )
        return instance

    all_formatted_tools = []
    available_tool_names = set()

    try:
        await asyncio.gather(*(client.__aenter__() for client in mcp_clients.values()))

        tool_listing_tasks = [
            client.list_tools() for client in mcp_clients.values()
        ]
        server_tool_results = await asyncio.gather(
            *tool_listing_tasks, return_exceptions=True
        )

        for (server_name, _), tools_result in zip(
            mcp_clients.items(), server_tool_results
        ):
            if isinstance(tools_result, Exception):
                logger.error(
                    f"Failed to list tools from server '{server_name}': {tools_result}"
                )
                continue

            for tool in tools_result:
                available_tool_names.add(f"{server_name}-{tool.name}")
            all_formatted_tools.extend(
                _format_mcp_tools_for_openai(tools_result, server_name)
            )

        enabled_tool_ids = {
            tool_id
            for tool_id, details in agent_definition.tools.items()
            if details.get("enabled")
        }
        tools = [
            tool
            for tool in all_formatted_tools
            if tool["function"]["name"] in enabled_tool_ids
        ]

        if not tools:
            logger.warning("Agent step has no enabled tools.")
            # This is not a failure, just a simple LLM call.
            pass

        # Add a tool to get output from a previous step
        get_output_tool = {
            "type": "function",
            "function": {
                "name": "get_step_output",
                "description": "Retrieves the full, raw output data from a previous step in the workflow using its unique output ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "output_id": {
                            "type": "string",
                            "description": "The UUID of the output data to retrieve. This is found in the compressed JSON reference provided in the prompt.",
                        }
                    },
                    "required": ["output_id"],
                },
            },
        }
        tools.append(get_output_tool)

        # The 'stop_workflow' tool is implicit now. The agent finishes by just responding.
        
        # NOTE: Required tools logic is removed for now to simplify.
        # It can be added back if needed for specific agent behaviors.

        max_cycles = 10  # A reasonable limit for agent execution cycles
        
        messages_for_run = [MessageModel(role="system", content=resolved_system_prompt)]
        instance.messages.extend(messages_for_run)

        for turn in range(max_cycles):
            logger.info(
                f"Agent Step Instance {instance.uuid}, Turn {turn + 1}/{max_cycles}."
            )
            
            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model=agent_definition.model,
                messages=[
                    msg.model_dump(
                        exclude_none=True,
                        include={"role", "content", "tool_calls", "tool_call_id", "name"},
                    )
                    for msg in instance.messages
                ],
                tools=tools,
                tool_choice="auto" if tools else "none",
            )
            response_message = response.choices[0].message
            instance.messages.append(
                MessageModel.model_validate(response_message.model_dump())
            )

            if not response_message.tool_calls:
                logger.info("Agent finished execution loop.")
                # The final message content is the output
                instance.output = await create_output_data(
                    raw_data=response_message.content,
                    summary_prompt="Summarize the agent's final answer."
                )
                break

            tool_calls = response_message.tool_calls
            tool_results_coroutines: list[Coroutine] = []
            tool_call_details_map: dict[int, Any] = {}

            for i, tool_call in enumerate(tool_calls):
                tool_call_details_map[i] = tool_call
                function_name = tool_call.function.name
                
                if function_name == "get_step_output":
                    tool_results_coroutines.append(
                        _handle_get_step_output(tool_call, instance.user_id)
                    )
                else:
                    tool_results_coroutines.append(
                        _handle_mcp_tool_call(tool_call, mcp_clients)
                    )

            tool_results = await asyncio.gather(*tool_results_coroutines)

            for i, result_content in enumerate(tool_results):
                tool_call = tool_call_details_map[i]
                instance.messages.append(
                    MessageModel(
                        tool_call_id=tool_call.id,
                        role="tool",
                        name=tool_call.function.name,
                        content=result_content,
                    )
                )

            if turn == max_cycles - 1:
                logger.warning(f"Agent reached max cycles ({max_cycles}). Finishing.")
                instance.output = await create_output_data(
                    raw_data="Agent reached maximum execution cycles.",
                    summary_prompt="Summarize the agent's final answer."
                )

    except Exception as e:
        logger.error(f"Error during agent step execution for instance {instance.uuid}: {e}", exc_info=True)
        instance.status = "failed"
        instance.error_message = str(e)
    finally:
        await asyncio.gather(
            *(client.__aexit__(None, None, None) for client in mcp_clients.values())
        )

    logger.info(f"Finished execution for agent instance {instance.uuid}.")
    return instance

async def _handle_get_step_output(tool_call, user_id) -> str:
    """Handles the special 'get_step_output' tool call."""
    from workflow.client import get_output_data # Avoid circular import

    try:
        args = json.loads(tool_call.function.arguments)
        output_id = args.get("output_id")
        if not output_id:
            return "Error: `output_id` is required."
        
        output_data = await get_output_data(output_id, user_id)
        if not output_data:
            return f"Error: No output data found for ID {output_id}."
        
        # Return the raw_data, serialized if it's complex
        if isinstance(output_data.raw_data, (dict, list, int, float, bool)):
            return json.dumps(output_data.raw_data)
        return str(output_data.raw_data)

    except (json.JSONDecodeError, AttributeError, Exception) as e:
        logger.warning(f"Could not process get_step_output call: {e}", exc_info=True)
        return f"Error processing tool call: {e}"

async def _handle_mcp_tool_call(tool_call, mcp_clients: dict[str, MCPClient]) -> str:
    """Handles a standard tool call to an MCP server."""
    full_tool_name = tool_call.function.name
    try:
        server_name, short_tool_name = full_tool_name.split("-", 1)
        if server_name not in mcp_clients:
            return f"Error: Server '{server_name}' is not available."

        client = mcp_clients[server_name]
        function_args = json.loads(tool_call.function.arguments)
        result = await client.call_tool(short_tool_name, function_args)
        return "\n".join(item.text for item in result.content)
    except Exception as e:
        logger.error(f"Error calling tool {full_tool_name}: {e}", exc_info=True)
        return f"Error executing tool: {e}" 