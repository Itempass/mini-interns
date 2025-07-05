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

def _get_next_required_tool(required_tools_sequence: list[str], completed_required_tools: set) -> str | None:
    """Returns the next required tool that hasn't been completed yet, or None if all are done."""
    for tool_id in required_tools_sequence:
        if tool_id not in completed_required_tools:
            return tool_id
    return None

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
    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not found in settings. Cannot proceed.")
        instance.messages.append(MessageModel(role="system", content="Error: OPENROUTER_API_KEY not configured."))
        return instance

    llm_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )

    mcp_clients: dict[str, Client] = {}
    try:
        api_url = f"http://localhost:{settings.CONTAINERPORT_API}/mcp/servers"
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(api_url)
            response.raise_for_status()
            servers_info = response.json()
            if not servers_info:
                logger.error("No MCP servers discovered. Cannot proceed.")
                instance.messages.append(MessageModel(role="system", content="Error: No MCP servers available."))
                return instance

            for server_info in servers_info:
                server_name = server_info.get("name")
                server_url = server_info.get("url")
                if server_name and server_url:
                    mcp_clients[server_name] = Client(server_url)
                    logger.info(f"Initialized client for MCP server: {server_name} at {server_url}")
                else:
                    logger.warning(f"Skipping server with incomplete info: {server_info}")

    except Exception as e:
        logger.error(f"Failed to discover or initialize MCP clients: {e}", exc_info=True)
        instance.messages.append(MessageModel(role="system", content=f"Error: Could not discover MCP servers. {e}"))
        return instance

    if not mcp_clients:
        logger.error("No MCP servers could be initialized. Cannot proceed.")
        instance.messages.append(MessageModel(role="system", content="Error: No MCP servers available."))
        return instance

    all_mcp_tools = []
    available_tool_names = set()
    all_formatted_tools = []
    
    try:
        # Enter all client contexts
        await asyncio.gather(*(client.__aenter__() for client in mcp_clients.values()))

        # List tools from all servers
        tool_listing_tasks = [client.list_tools() for client in mcp_clients.values()]
        server_tool_results = await asyncio.gather(*tool_listing_tasks, return_exceptions=True)

        for (server_name, client), tools_result in zip(mcp_clients.items(), server_tool_results):
            if isinstance(tools_result, Exception):
                logger.error(f"Failed to list tools from server '{server_name}': {tools_result}")
                continue
            
            server_tools = tools_result
            all_mcp_tools.extend(server_tools)
            for tool in server_tools:
                available_tool_names.add(f"{server_name}-{tool.name}")
            
            all_formatted_tools.extend(_format_mcp_tools_for_openai(server_tools, server_name))
        
        enabled_tool_ids = {tool_id for tool_id, details in agent_model.tools.items() if details.get('enabled')}
        
        # Filter formatted tools based on whether they are enabled in the agent model
        tools = [tool for tool in all_formatted_tools if tool['function']['name'] in enabled_tool_ids]
        
        if not tools:
            logger.warning("Agent has no enabled tools from any available server.")
            instance.messages.append(MessageModel(role="system", content="Warning: Agent has no enabled tools. Cannot perform actions."))
            return instance
            
        stop_workflow_tool = {
            "type": "function",
            "function": {
                "name": "stop_workflow",
                "description": "Call this tool to indicate that you have finished your work. This should be used when you have a final answer for the user or are COMPLETELY unable to continue.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "final_answer": {
                            "type": "string",
                            "description": "The final answer or summary of the work done to be presented to the user."
                        }
                    },
                    "required": ["final_answer"]
                }
            }
        }
        tools.append(stop_workflow_tool)
        
        required_tools_with_order = sorted(
            [(tool_id, details['order']) for tool_id, details in agent_model.tools.items() if details.get('required') and tool_id in available_tool_names],
            key=lambda x: x[1]
        )
        required_tools_sequence = [tool_id for tool_id, order in required_tools_with_order]
        
        num_required_tools = len(required_tools_sequence)
        num_enabled_mcp_tools = len(tools) - 1 # Exclude stop_workflow
        num_non_required_tools = num_enabled_mcp_tools - num_required_tools
        num_internal_tools = 1  # For stop_workflow
        max_cycles = num_internal_tools + (2 * num_required_tools) + num_non_required_tools
        logger.info(f"Calculated max_cycles: {max_cycles} (internal: {num_internal_tools}, required: {num_required_tools}, non-required: {num_non_required_tools})")

        current_date = datetime.now().strftime('%Y-%m-%d')
        my_email = app_settings.IMAP_USERNAME or ""

        system_prompt = agent_model.system_prompt.replace("<<CURRENT_DATE>>", current_date)
        system_prompt = system_prompt.replace("<<MY_EMAIL>>", my_email)

        user_instructions = agent_model.user_instructions.replace("<<CURRENT_DATE>>", current_date)
        user_instructions = user_instructions.replace("<<MY_EMAIL>>", my_email)

        # New prompt injection logic
        if agent_model.param_values:
            # 1. Bulk injection
            param_values_json = json.dumps(agent_model.param_values)
            system_prompt = system_prompt.replace("<<PARAM_VALUES>>", param_values_json)
            user_instructions = user_instructions.replace("<<PARAM_VALUES>>", param_values_json)

            # 2. Individual injection
            if agent_model.param_schema:
                for field in agent_model.param_schema:
                    injection_key = field.get("injection_key")
                    if injection_key:
                        value = agent_model.param_values.get(field["parameter_key"])
                        
                        # JSON-serialize complex types, otherwise convert to string
                        if isinstance(value, (dict, list)):
                            replacement = json.dumps(value)
                        else:
                            replacement = str(value)
                        
                        system_prompt = system_prompt.replace(f"<<{injection_key}>>", replacement)
                        user_instructions = user_instructions.replace(f"<<{injection_key}>>", replacement)
        
        required_tools_prompt = f"\n\nYou have multiple tools available to you. You MUST use the required tools, and you MUST use them in this order: {', '.join(required_tools_sequence)}." if required_tools_sequence else ""

        messages_for_run = [
            MessageModel(role="system", content=user_instructions),
            MessageModel(role="system", content=system_prompt),
            MessageModel(role="user", content=instance.user_input),
            MessageModel(role="system", content=required_tools_prompt)
        ]
        instance.messages.extend(messages_for_run)

        completed_required_tools = set()
        for turn in range(max_cycles):
            next_required_tool = _get_next_required_tool(required_tools_sequence, completed_required_tools)
            logger.info(f"Instance {instance.uuid}, Turn {turn + 1}/{max_cycles}. Completed required tools: {completed_required_tools}. Next required: {next_required_tool}")
            
            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model=agent_model.model,
                messages=[msg.model_dump(exclude_none=True, include={'role', 'content', 'tool_calls', 'tool_call_id', 'name'}) for msg in instance.messages],
                tools=tools,
                tool_choice="auto",
            )
            response_message = response.choices[0].message
            instance.messages.append(MessageModel.model_validate(response_message.model_dump()))

            if not response_message.tool_calls:
                if next_required_tool:
                    nudge_message = f"You cannot finish yet. You must call the '{next_required_tool}' tool next. The required tool order is: {', '.join(required_tools_sequence)}."
                    instance.messages.append(MessageModel(role="system", content=nudge_message))
                    logger.info(f"Nudging agent: {nudge_message}")
                    continue
                else:
                    logger.info("Agent decided to finish, and all required tools were used.")
                    break
            
            should_stop = False
            final_answer = ""
            mcp_tool_calls = []

            for tool_call in response_message.tool_calls:
                if tool_call.function.name == "stop_workflow":
                    should_stop = True
                    logger.info("Agent requested to stop workflow.")
                    try:
                        args = json.loads(tool_call.function.arguments)
                        final_answer = args.get("final_answer", "Workflow finished by agent.")
                        instance.messages.append(MessageModel(
                            tool_call_id=tool_call.id,
                            role="tool",
                            name=tool_call.function.name,
                            content="Workflow stop acknowledged.",
                        ))
                    except (json.JSONDecodeError, AttributeError) as e:
                        logger.warning(f"Could not parse arguments for stop_workflow: {e}", exc_info=True)
                        final_answer = "Workflow finished with error parsing final answer."
                        instance.messages.append(MessageModel(
                            tool_call_id=tool_call.id,
                            role="tool",
                            name=tool_call.function.name,
                            content=f"Error processing arguments: {e}",
                        ))
                else:
                    mcp_tool_calls.append(tool_call)

            called_tool_ids = {tc.function.name for tc in response_message.tool_calls}
            
            if next_required_tool and next_required_tool not in called_tool_ids:
                future_required_tools = set()
                found_next = False
                for tool_id in required_tools_sequence:
                    if tool_id == next_required_tool:
                        found_next = True
                    elif found_next:
                        future_required_tools.add(tool_id)
                
                called_future_tools = called_tool_ids.intersection(future_required_tools)

                if called_future_tools:
                    logger.warning(f"Agent tried to call future required tools {called_future_tools} before completing {next_required_tool}. Intervening.")
                    tool_error_message = f"Error: Tool call denied. You cannot call {', '.join(called_future_tools)} until you have called '{next_required_tool}' first. The required tool order is: {', '.join(required_tools_sequence)}. You have completed: {', '.join(completed_required_tools) if completed_required_tools else 'none'}."
                    for tool_call in response_message.tool_calls:
                        instance.messages.append(MessageModel(
                            tool_call_id=tool_call.id, role="tool", name=tool_call.function.name, content=tool_error_message
                        ))
                    continue
                else:
                    logger.info(f"Agent called {called_tool_ids} without calling next required tool '{next_required_tool}'. This is allowed (re-calls or non-required tools).")
            else:
                logger.info(f"Agent called required tool '{next_required_tool}' as expected, or no required tools pending.")

            if mcp_tool_calls:
                tasks = []
                tool_call_details = []
                for tool_call in mcp_tool_calls:
                    full_tool_name = tool_call.function.name
                    server_name, short_tool_name = full_tool_name.split('-', 1)
                    
                    if server_name not in mcp_clients:
                        logger.error(f"Attempted to call tool on unknown server: {server_name}")
                        # Append an error message for this tool call and skip it
                        instance.messages.append(MessageModel(
                            tool_call_id=tool_call.id,
                            role="tool",
                            name=full_tool_name,
                            content=f"Error: Server '{server_name}' is not available.",
                        ))
                        continue
                        
                    client = mcp_clients[server_name]
                    function_args = json.loads(tool_call.function.arguments)
                    tasks.append(client.call_tool(short_tool_name, function_args))
                    tool_call_details.append(tool_call)
                
                tool_results = await asyncio.gather(*tasks, return_exceptions=True)

                for tool_call, result in zip(tool_call_details, tool_results):
                    if isinstance(result, Exception):
                        logger.error(f"Error calling tool {tool_call.function.name}: {result}", exc_info=True)
                        content = f"Error executing tool: {result}"
                    else:
                        content = "\n".join(item.text for item in result.content)
                    
                    instance.messages.append(MessageModel(
                        tool_call_id=tool_call.id,
                        role="tool",
                        name=tool_call.function.name,
                        content=content,
                    ))

            for tool_id in called_tool_ids:
                if tool_id in required_tools_sequence:
                    completed_required_tools.add(tool_id)
                    logger.info(f"Required tool '{tool_id}' marked as completed.")
            
            if should_stop:
                logger.info("Stopping workflow as requested by agent.")
                if final_answer:
                    instance.messages.append(MessageModel(role="assistant", content=final_answer))
                break

    finally:
        # Exit all client contexts
        await asyncio.gather(*(client.__aexit__(None, None, None) for client in mcp_clients.values()))

    logger.info(f"Finished execution for instance {instance.uuid}. Logging conversation.")
    try:
        await save_conversation(ConversationData(
            metadata=Metadata(
                conversation_id=f"agent_{instance.uuid}",
                readable_workflow_name=f"Agent: {agent_model.name}",
                readable_instance_context=instance.context_identifier,
                model=agent_model.model
            ),
            messages=[LoggerMessage.model_validate(m.model_dump()) for m in instance.messages if m.content is not None]
        ))
        logger.info(f"Conversation for instance {instance.uuid} logged successfully.")
    except Exception as e:
        logger.warning(f"Failed to log agent conversation for instance {instance.uuid}: {e}", exc_info=True)

    return instance 