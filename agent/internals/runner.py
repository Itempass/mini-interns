# This file is for internal use only and should not be used directly by the end-user. 
import logging
import json
import asyncio
import httpx
from openai import OpenAI
from fastmcp import Client
from shared.config import settings
from agent.models import Agent as AgentModel, AgentInstance as AgentInstanceModel, Message

logger = logging.getLogger(__name__)

def _format_mcp_tools_for_openai(tools) -> list[dict]:
    formatted_tools = []
    for tool in tools:
        formatted_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        formatted_tools.append(formatted_tool)
    return formatted_tools

async def _execute_run(agent_model: AgentModel, instance: AgentInstanceModel, openrouter_api_key: str) -> AgentInstanceModel:
    logger.info(f"Starting execution for instance {instance.uuid} of agent {agent_model.uuid}")

    # 1. Initialize OpenAI Client
    llm_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_api_key,
    )

    # 2. Discover and connect to MCP server
    mcp_server_url = None
    try:
        api_url = f"http://localhost:{settings.CONTAINERPORT_API}/mcp/servers"
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(api_url)
            response.raise_for_status()
            servers = response.json()
            if servers:
                mcp_server_url = servers[0].get("url")
    except Exception as e:
        logger.error(f"Failed to discover MCP servers: {e}", exc_info=True)
        # Handle error appropriately, maybe update instance state
        return instance

    if not mcp_server_url:
        logger.error("No MCP servers discovered. Cannot proceed.")
        return instance

    mcp_client = Client(mcp_server_url)
    async with mcp_client as client:
        # 3. Prepare tools and initial messages
        mcp_tools = await client.list_tools()
        tools = _format_mcp_tools_for_openai(mcp_tools)

        messages = [
            Message(role="system", content=agent_model.system_prompt),
            Message(role="user", content=agent_model.user_instructions),
            Message(role="user", content=instance.user_input)
        ]
        instance.messages.extend(messages)

        # 4. Agentic Loop
        for turn in range(5): # Max 5 turns
            logger.info(f"Instance {instance.uuid}, Turn {turn + 1}")
            
            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model="openai/gpt-4o", # Or from a config
                messages=[msg.model_dump(exclude_none=True) for msg in instance.messages],
                tools=tools,
                tool_choice="auto",
            )
            response_message = response.choices[0].message
            instance.messages.append(Message.model_validate(response_message))

            if not response_message.tool_calls:
                logger.info("Agent decided to finish.")
                break

            tasks = []
            for tool_call in response_message.tool_calls:
                tool_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                tasks.append(client.call_tool(tool_name, function_args))
            
            tool_results = await asyncio.gather(*tasks)

            for tool_call, result in zip(response_message.tool_calls, tool_results):
                result_text = "\n".join(item.text for item in result)
                instance.messages.append(Message(
                    tool_call_id=tool_call.id,
                    role="tool",
                    name=tool_call.function.name,
                    content=result_text,
                ))

    logger.info(f"Finished execution for instance {instance.uuid}")
    return instance 