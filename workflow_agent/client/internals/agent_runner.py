import asyncio
import json
import logging
import os
from typing import List, Tuple
from uuid import UUID

from fastmcp import Client as MCPClient
from fastmcp.client.transports import StreamableHttpTransport
from openai import OpenAI

from shared.config import settings
from workflow_agent.client.models import ChatMessage, HumanInputRequired

logger = logging.getLogger(__name__)

# Load the system prompt from the file.
SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'system_prompt.md')
with open(SYSTEM_PROMPT_PATH, 'r') as f:
    SYSTEM_PROMPT = f.read()

def _format_mcp_tools_for_openai(tools) -> list[dict]:
    """Formats a list of MCP Tools into the format expected by OpenAI."""
    formatted_tools = []
    for tool in tools:
        # The tool name is accessed directly, no server prefix needed for this agent
        full_tool_name = tool.name
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

async def run_agent_turn(
    conversation: List[ChatMessage], user_id: UUID, workflow_uuid: UUID
) -> Tuple[List[ChatMessage], HumanInputRequired | None]:
    """
    Runs a single turn of the workflow agent. This is a state machine driven by
    the role of the last message in the conversation history.
    - user -> call LLM
    - assistant(with tool_calls) -> execute tools
    - tool -> call LLM
    """
    if not settings.OPENROUTER_API_KEY:
        error_message = "Error: OPENROUTER_API_KEY not configured."
        logger.error(error_message)
        conversation.append(ChatMessage(role="assistant", content=error_message))
        return conversation, None

    llm_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )

    last_message = conversation[-1]

    # Pre-emptively check for human input requests to avoid creating an unnecessary MCP connection.
    if last_message.role == "assistant" and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            if tool_call['function']['name'] == 'feature_request':
                logger.info("Human input required for feature_request. Bypassing MCP connection.")
                try:
                    args = json.loads(tool_call['function']['arguments'])
                    human_input_required = HumanInputRequired(
                        type='feature_request',
                        tool_call_id=tool_call['id'],
                        data={
                            "name": args.get("suggested_name", ""),
                            "description": args.get("suggested_description", ""),
                        },
                    )
                    # We don't execute the tool, just return the request for input
                    return conversation, human_input_required
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Error processing feature_request arguments: {e}")
                    # Fallback to returning an error message in the conversation
                    error_message = f"Internal error processing your request: {e}"
                    conversation.append(ChatMessage(role="assistant", content=error_message))
                    return conversation, None

    mcp_url = f"http://localhost:{settings.CONTAINERPORT_MCP_WORKFLOW_AGENT}/mcp"
    headers = {
        "X-User-ID": str(user_id),
        "X-Workflow-UUID": str(workflow_uuid),
    }
    transport = StreamableHttpTransport(url=mcp_url, headers=headers)
    mcp_client = MCPClient(transport)

    async with mcp_client:
        if last_message.role == "assistant" and last_message.tool_calls:
            # STATE: LLM requested tool execution.
            logger.info("Agent is executing tools.")
            tool_calls = last_message.tool_calls
            
            tool_coroutines = []
            
            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = json.loads(tool_call['function']['arguments'])
                # Pass the arguments as a single dictionary, not as keyword arguments
                coro = mcp_client.call_tool(tool_name, tool_args)
                tool_coroutines.append(coro)

            tool_results = await asyncio.gather(*tool_coroutines, return_exceptions=True)

            # Append the results of each tool call to the conversation history
            for i, result in enumerate(tool_results):
                tool_call_id = tool_calls[i]['id']
                if isinstance(result, Exception):
                    logger.error(f"Error executing tool {tool_calls[i]['function']['name']}: {result}")
                    content = f"Error: {str(result)}"
                else:
                    # --- TEMPORARY DEBUGGING ---
                    logger.info(f"WORKFLOW_AGENT_DEBUG: Tool result object: {result}")
                    logger.info(f"WORKFLOW_AGENT_DEBUG: Tool result structured_content: {result.structured_content}")
                    # --- END TEMPORARY DEBUGGING ---

                    # The structure of structured_content varies. If the tool returns a list,
                    # it's wrapped in a 'result' key. Otherwise, it's the object itself.
                    if result.structured_content is None:
                        payload = None
                    elif 'result' in result.structured_content:
                        payload = result.structured_content['result']
                    else:
                        payload = result.structured_content
                    
                    content = json.dumps(payload)

                conversation.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=tool_call_id,
                        content=content,
                    )
                )

        elif last_message.role == "user" or last_message.role == "tool":
            # STATE: User sent a message OR tools have finished. Call LLM for the next step.
            logger.info("Agent is calling LLM.")
            available_tools = await mcp_client.list_tools()
            formatted_tools = _format_mcp_tools_for_openai(available_tools)
            
            messages_for_llm = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ] + [msg.model_dump(exclude_none=True, include={"role", "content", "tool_calls", "tool_call_id"}) for msg in conversation]
            
            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model="google/gemini-2.5-pro",
                messages=messages_for_llm,
                tools=formatted_tools,
                tool_choice="auto" if formatted_tools else "none",
            )
            response_message = response.choices[0].message
            conversation.append(ChatMessage.model_validate(response_message.model_dump()))
        
        # If the last message is from the assistant without tool calls, we do nothing.
        # The turn is considered complete.

    return conversation, None 