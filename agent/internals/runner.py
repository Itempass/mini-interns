# This file is for internal use only and should not be used directly by the end-user. 
import logging
import json
import asyncio
import httpx
from openai import OpenAI
from fastmcp import Client
from datetime import datetime

from shared.config import settings
from agent.models import AgentModel, AgentInstanceModel, MessageModel
from shared.app_settings import load_app_settings
from mcp.types import Tool
from agentlogger.src.client import save_conversation
from agentlogger.src.models import ConversationData, Message as LoggerMessage, Metadata

logger = logging.getLogger(__name__)

def _format_mcp_tools_for_openai(tools: list[Tool], server_name: str) -> list[dict]:
    """Formats a list of MCP Tools into the format expected by OpenAI."""
    logger.info(f"Formatting {len(tools)} MCP tools for OpenAI using server name '{server_name}':")
    
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
        logger.debug(f"Formatted tool with full name: {json.dumps(formatted_tool, indent=2)}")
    
    logger.info(f"Successfully formatted {len(formatted_tools)} tools for OpenAI")
    return formatted_tools

async def _execute_run(agent_model: AgentModel, instance: AgentInstanceModel) -> AgentInstanceModel:
    logger.info(f"Starting execution for instance {instance.uuid} of agent {agent_model.uuid}")

    app_settings = load_app_settings()
    if not app_settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not found in settings. Cannot proceed.")
        instance.messages.append(MessageModel(role="system", content="Error: OPENROUTER_API_KEY not configured."))
        return instance

    llm_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=app_settings.OPENROUTER_API_KEY,
    )

    mcp_server_url, server_name = None, None
    try:
        api_url = f"http://localhost:{settings.CONTAINERPORT_API}/mcp/servers"
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(api_url)
            response.raise_for_status()
            servers = response.json()
            if servers:
                selected_server = servers[0]
                server_name = selected_server.get("name")
                mcp_server_url = selected_server.get("url")
                logger.info(f"Selected MCP server: {server_name} at {mcp_server_url}")
    except Exception as e:
        logger.error(f"Failed to discover MCP servers: {e}", exc_info=True)
        instance.messages.append(MessageModel(role="system", content=f"Error: Could not discover MCP servers. {e}"))
        return instance

    if not mcp_server_url:
        logger.error("No MCP servers discovered. Cannot proceed.")
        instance.messages.append(MessageModel(role="system", content="Error: No MCP servers available."))
        return instance

    mcp_client = Client(mcp_server_url)
    async with mcp_client as client:
        all_mcp_tools = await client.list_tools()
        
        enabled_tool_ids = {tool_id for tool_id, details in agent_model.tools.items() if details.get('enabled')}
        mcp_tools = [tool for tool in all_mcp_tools if f"{server_name}-{tool.name}" in enabled_tool_ids]
        
        if not mcp_tools:
            logger.warning("Agent has no enabled tools.")
            instance.messages.append(MessageModel(role="system", content="Warning: Agent has no enabled tools. Cannot perform actions."))
            return instance
            
        tools = _format_mcp_tools_for_openai(mcp_tools, server_name=server_name)
        
        required_tools_with_order = sorted(
            [(tool_id, details['order']) for tool_id, details in agent_model.tools.items() if details.get('required')],
            key=lambda x: x[1]
        )
        required_tools_sequence = [tool_id for tool_id, order in required_tools_with_order]
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        system_prompt = agent_model.system_prompt.replace("<<CURRENT_DATE>>", current_date)
        user_instructions = agent_model.user_instructions.replace("<<CURRENT_DATE>>", current_date)
        
        required_tools_prompt = f"\n\nYou have multiple tools available to you. You MUST use the required tools, and you MUST use them in this order: {', '.join(required_tools_sequence)}." if required_tools_sequence else ""

        messages_for_run = [
            MessageModel(role="system", content=user_instructions),
            MessageModel(role="system", content=system_prompt),
            MessageModel(role="user", content=instance.user_input),
            MessageModel(role="system", content=required_tools_prompt)
        ]
        instance.messages.extend(messages_for_run)

        required_tool_index = 0
        for turn in range(7):
            logger.info(f"Instance {instance.uuid}, Turn {turn + 1}. Required tool index: {required_tool_index}")
            
            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model=app_settings.OPENROUTER_MODEL or "openai/gpt-4o",
                messages=[msg.model_dump(exclude_none=True, include={'role', 'content', 'tool_calls', 'tool_call_id', 'name'}) for msg in instance.messages],
                tools=tools,
                tool_choice="auto",
            )
            response_message = response.choices[0].message
            instance.messages.append(MessageModel.model_validate(response_message.model_dump()))

            if not response_message.tool_calls:
                if required_tool_index < len(required_tools_sequence):
                    next_required_tool = required_tools_sequence[required_tool_index]
                    nudge_message = f"You cannot finish yet. You must call the '{next_required_tool}' tool next. The required tool order is: {', '.join(required_tools_sequence)}."
                    instance.messages.append(MessageModel(role="system", content=nudge_message))
                    logger.info(f"Nudging agent: {nudge_message}")
                    continue
                else:
                    logger.info("Agent decided to finish, and all required tools were used.")
                    break
            
            called_tool_ids = {tc.function.name for tc in response_message.tool_calls}
            if required_tool_index < len(required_tools_sequence):
                next_required_tool = required_tools_sequence[required_tool_index]
                if next_required_tool not in called_tool_ids:
                    logger.warning(f"Invalid tool call order. Expected {next_required_tool}, but got {called_tool_ids}. Intervening.")
                    tool_error_message = f"Error: Tool call denied. You must call the '{next_required_tool}' tool next. The required tool order is: {', '.join(required_tools_sequence)}."
                    for tool_call in response_message.tool_calls:
                        instance.messages.append(MessageModel(
                            tool_call_id=tool_call.id, role="tool", name=tool_call.function.name, content=tool_error_message
                        ))
                    continue

            tasks = []
            for tool_call in response_message.tool_calls:
                full_tool_name = tool_call.function.name
                short_tool_name = full_tool_name.replace(f"{server_name}-", "", 1)
                function_args = json.loads(tool_call.function.arguments)
                tasks.append(client.call_tool(short_tool_name, function_args))
            
            tool_results = await asyncio.gather(*tasks)

            for tool_call, result in zip(response_message.tool_calls, tool_results):
                result_text = "\n".join(item.text for item in result)
                instance.messages.append(MessageModel(
                    tool_call_id=tool_call.id,
                    role="tool",
                    name=tool_call.function.name,
                    content=result_text,
                ))

            if required_tool_index < len(required_tools_sequence) and required_tools_sequence[required_tool_index] in called_tool_ids:
                logger.info(f"Required tool '{required_tools_sequence[required_tool_index]}' was successfully called.")
                required_tool_index += 1

    logger.info(f"Finished execution for instance {instance.uuid}. Logging conversation.")
    try:
        await save_conversation(ConversationData(
            metadata=Metadata(
                conversation_id=f"agent_{instance.uuid}",
                readable_workflow_name=f"Agent: {agent_model.name}",
                readable_instance_context=f"Instance: {instance.uuid}"
            ),
            messages=[LoggerMessage.model_validate(m.model_dump()) for m in instance.messages if m.content is not None]
        ))
        logger.info(f"Conversation for instance {instance.uuid} logged successfully.")
    except Exception as e:
        logger.warning(f"Failed to log agent conversation for instance {instance.uuid}: {e}", exc_info=True)

    return instance 