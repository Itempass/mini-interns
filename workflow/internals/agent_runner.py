# This file is for internal use only and should not be used directly by the end-user. 
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Coroutine
from uuid import UUID

import httpx
from fastmcp import Client as MCPClient
from fastmcp.client.transports import StreamableHttpTransport
from fastapi import HTTPException
from openai import OpenAI
from jsonpath_ng import parse

from agentlogger.src.client import save_log_entry
from agentlogger.src.models import (
    LogEntry,
    Message as LoggerMessage,
)
from mcp.types import Tool
from shared.app_settings import load_app_settings
from shared.config import settings
from workflow.internals.output_processor import create_output_data, generate_summary
from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)
from workflow.models import (
    CustomAgent,
    CustomAgentInstanceModel,
    MessageModel,
    StepOutputData,
    WorkflowModel,
)
import workflow.client as workflow_client
from user import client as user_client
from user.exceptions import InsufficientBalanceError


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
    agent_definition: CustomAgent,
    resolved_system_prompt: str,
    user_id: UUID,
    workflow_instance_uuid: UUID,
    workflow_definition: WorkflowModel,
) -> CustomAgentInstanceModel:
    """Runs a CustomAgent step."""
    logger.info(
        f"Starting execution for agent step {agent_definition.uuid} in workflow instance {workflow_instance_uuid}"
    )

    instance = CustomAgentInstanceModel(
        user_id=user_id,
        workflow_instance_uuid=workflow_instance_uuid,
        status="running",
        agent_definition_uuid=agent_definition.uuid,
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
    servers_info = []
    try:
        api_url = f"http://localhost:{settings.CONTAINERPORT_API}/mcp/servers"
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(api_url)
            response.raise_for_status()
            servers_info = response.json()

            if servers_info:
                headers = {
                    "X-User-ID": str(user_id),
                    "X-Workflow-UUID": str(workflow_instance_uuid)
                }
                for server_info in servers_info:
                    server_name = server_info.get("name")
                    server_url = server_info.get("url")
                    if server_name and server_url:
                        transport = StreamableHttpTransport(url=server_url, headers=headers)
                        mcp_clients[server_name] = MCPClient(transport)
    except Exception as e:
        logger.warning(
            f"Could not discover MCP servers: {e}. This is okay if no tools are used."
        )
        # Proceed with no clients, this will be checked later if tools are required.

    logger.info(f"Discovered {len(mcp_clients)} MCP clients: {list(mcp_clients.keys())}")

    all_formatted_tools = []
    available_tool_names = set()

    if mcp_clients:
        try:
            await asyncio.gather(
                *(client.__aenter__() for client in mcp_clients.values())
            )

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
        except Exception as e:
            logger.error(f"Error communicating with MCP servers: {e}", exc_info=True)

    logger.info(f"Discovered {len(available_tool_names)} total tools from all servers.")

    # After attempting to discover all tools, check if any enabled tools are missing.
    enabled_tool_ids = {
        tool_id
        for tool_id, details in agent_definition.tools.items()
        if details.get("enabled")
    }

    logger.debug(f"Agent has {len(enabled_tool_ids)} enabled tools: {enabled_tool_ids}")

    if enabled_tool_ids:
        missing_tools = enabled_tool_ids - available_tool_names
        if missing_tools:
            error_msg = f"Agent step failed because required tools are unavailable: {', '.join(missing_tools)}"
            logger.error(error_msg)
            instance.status = "failed"
            instance.error_message = error_msg
            instance.messages.append(MessageModel(role="system", content=error_msg))
            return instance

    # Filter the tools to only those that are enabled for this agent.
    tools = [
        tool
        for tool in all_formatted_tools
        if tool["function"]["name"] in enabled_tool_ids
    ]

    logger.info(f"Providing {len(tools)} enabled and available tools to the LLM.")

    
    try:
        # --- Balance Check ---
        logger.info(f"Checking balance for user {user_id} before running agent step.")
        user_client.check_user_balance(user_id)
        logger.info(f"User {user_id} has sufficient balance.")

        max_cycles = 10  # A reasonable limit for agent execution cycles
        
        messages_for_run = [MessageModel(role="system", content=resolved_system_prompt)]
        instance.messages.extend(messages_for_run)

        # To store cumulative token and cost information
        cumulative_prompt_tokens = 0
        cumulative_completion_tokens = 0
        cumulative_total_tokens = 0
        cumulative_total_cost = 0.0

        logger.info(f"Starting agent execution loop for instance {instance.uuid}. Max cycles: {max_cycles}")
        for turn in range(max_cycles):
            logger.info(
                f"Agent Step Instance {instance.uuid}, Turn {turn + 1}/{max_cycles}."
            )
            
            logger.debug(f"Calling LLM with {len(instance.messages)} messages and {len(tools)} tools.")
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

            # Accumulate usage data
            if response.usage:
                cumulative_prompt_tokens += response.usage.prompt_tokens
                cumulative_completion_tokens += response.usage.completion_tokens
                cumulative_total_tokens += response.usage.total_tokens
                # Cost retrieval would need a generation ID, which is available in the 'id' of the response.
                # Assuming openrouter_service can be used here as well.
                if response.id:
                    try:
                        # This assumes a similar setup as llm_runner and might need adjustment
                        # if openrouter_service is not directly available here.
                        # For now, let's assume we can fetch it.
                        cost = await openrouter_service.get_generation_cost(response.id)
                        cumulative_total_cost += cost
                    except Exception as e:
                        logger.error(f"Could not retrieve cost for generation {response.id}: {e}")


            if not response_message.tool_calls:
                logger.info("Agent finished execution loop.")
                # The final message content is the output
                final_content = response_message.content or "Agent provided no final answer."
                markdown_rep = f"{final_content}"
                instance.output = await create_output_data(
                    markdown_representation=markdown_rep,
                    user_id=user_id,
                )
                break

            tool_calls = response_message.tool_calls
            tool_results_coroutines: list[Coroutine] = []
            tool_call_details_map: dict[int, Any] = {}

            # --- Argument Resolution Step ---
            # Before calling the tools, resolve any "magic string" data pointers.
            # resolved_tool_calls = await _resolve_tool_arguments(tool_calls, instance.user_id)
            resolved_tool_calls = tool_calls

            for i, tool_call in enumerate(resolved_tool_calls):
                tool_call_details_map[i] = tool_call
                function_name = tool_call.function.name
                
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
                timeout_message = "Agent reached maximum execution cycles and was terminated."
                markdown_rep = f"## Agent Timed Out\n\n{timeout_message}"
                instance.output = await create_output_data(
                    markdown_representation=markdown_rep,
                    user_id=user_id
                )

    except InsufficientBalanceError as e:
        logger.warning(f"Blocking agent step for user {user_id} due to insufficient balance.")
        instance.status = "failed"
        instance.error_message = str(e)
        # Re-raise as HTTPException to be caught by the API layer
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error during agent step execution for instance {instance.uuid}: {e}", exc_info=True)
        instance.status = "failed"
        instance.error_message = str(e)
    finally:
        # --- Cost Deduction ---
        if cumulative_total_cost > 0:
            logger.info(f"Deducting total cost of {cumulative_total_cost} from user {user_id}'s balance.")
            try:
                user_client.deduct_from_balance(user_id, cumulative_total_cost)
            except Exception as e:
                logger.error(f"Failed to deduct cost for user {user_id}: {e}", exc_info=True)

        # This block ensures that we try to log the conversation even if an error occurs during the run.
        try:
            logger.info(f"Saving conversation for agent instance {instance.uuid} to agentlogger.")
            
            logger_messages = [
                LoggerMessage.model_validate(msg.model_dump()) 
                for msg in instance.messages
            ]

            log_entry = LogEntry(
                user_id=str(user_id),
                log_type='custom_agent',
                workflow_id=str(workflow_definition.uuid),
                workflow_instance_id=str(workflow_instance_uuid),
                workflow_name=workflow_definition.name,
                step_id=str(agent_definition.uuid),
                step_instance_id=str(instance.uuid),
                step_name=agent_definition.name,
                messages=logger_messages,
                start_time=instance.started_at,
                end_time=datetime.now(timezone.utc),
                reference_string="TODO: PASS REFERENCE STRING",
                prompt_tokens=cumulative_prompt_tokens,
                completion_tokens=cumulative_completion_tokens,
                total_tokens=cumulative_total_tokens,
                total_cost=cumulative_total_cost,
                model=agent_definition.model,
            )
            await save_log_entry(log_entry)
            logger.info(f"Successfully saved conversation for instance {instance.uuid}.")
        except Exception as e:
            logger.error(
                f"Failed to save conversation for instance {instance.uuid} to agentlogger: {e}",
                exc_info=True,
            )

        # Clean up MCP clients
        if mcp_clients:
            await asyncio.gather(
                *(client.__aexit__(None, None, None) for client in mcp_clients.values()),
                return_exceptions=True,  # To prevent one failure from stopping others
            )

    instance.finished_at = datetime.now(timezone.utc)
    return instance


async def _resolve_tool_arguments(tool_calls: list, user_id: str) -> list:
    """
    Inspects tool call arguments and resolves any "magic string" data pointers.
    Format: 'step_output:<step_output_id>:<JSONPath>'
    """
    for tool_call in tool_calls:
        try:
            arguments = json.loads(tool_call.function.arguments)
            logger.info(f"ARG_RESOLVER_DEBUG: Original arguments for tool '{tool_call.function.name}': {arguments}")
        except json.JSONDecodeError:
            logger.warning(f"ARG_RESOLVER_DEBUG: Could not parse arguments for tool '{tool_call.function.name}'. Skipping.")
            continue # If args aren't valid JSON, skip them.

        resolved_args = {}
        for key, value in arguments.items():
            if isinstance(value, str) and value.startswith("step_output:"):
                try:
                    _, step_output_id, path = value.split(":", 2)
                    logger.info(f"ARG_RESOLVER_DEBUG: Found data pointer '{value}'. Fetching...")
                    
                    # Fetch the data container
                    output_data = await workflow_client.get_output_data(output_id=step_output_id, user_id=user_id)
                    if not output_data:
                        raise ValueError(f"Could not find output data with ID {step_output_id}")

                    # Use JSONPath to extract the specific value
                    jsonpath_expr = parse(path)
                    matches = jsonpath_expr.find(output_data.model_dump())
                    if not matches:
                        raise ValueError(f"Path '{path}' not found in data from step output {step_output_id}")
                    
                    resolved_args[key] = matches[0].value
                except Exception as e:
                    logger.error(f"Failed to resolve data pointer '{value}': {e}", exc_info=True)
                    # Pass the unresolved value to the tool, which will likely fail and provide a signal to the LLM
                    resolved_args[key] = value
            else:
                # HOTFIX: The LLM sometimes returns a JSON-encoded string within the JSON object.
                # We try to decode it, but if it fails, we use the raw value.
                if isinstance(value, str):
                    logger.info(f"ARG_RESOLVER_DEBUG: Argument '{key}' is a string. Attempting to JSON decode value: '{value}'")
                    try:
                        decoded_value = json.loads(value)
                        resolved_args[key] = decoded_value
                        logger.info(f"ARG_RESOLVER_DEBUG: Successfully decoded string argument '{key}'. New value: {decoded_value}")
                    except json.JSONDecodeError:
                        resolved_args[key] = value
                        logger.info(f"ARG_RESOLVER_DEBUG: Failed to decode string argument '{key}'. Using original value: '{value}'")
                else:
                    resolved_args[key] = value
        
        logger.info(f"ARG_RESOLVER_DEBUG: Final resolved arguments for tool '{tool_call.function.name}': {resolved_args}")
        tool_call.function.arguments = json.dumps(resolved_args)

    return tool_calls


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