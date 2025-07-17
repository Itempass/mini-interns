import logging
import json
from typing import List
from uuid import UUID

from fastmcp import Client as MCPClient
from fastmcp.client.transports import StreamableHttpTransport

from shared.config import settings
from workflow_agent.client.internals.agent_runner import run_agent_turn
from workflow_agent.client.models import ChatMessage, ChatStepResponse, ChatRequest

logger = logging.getLogger(__name__)

async def run_chat_step(
    request: ChatRequest, user_id: UUID, workflow_uuid: UUID
) -> ChatStepResponse:
    """
    Runs the next step of a chat conversation with the workflow agent.
    This function orchestrates the agent's turn-based logic.

    If the request includes `human_input`, it will first execute the
    corresponding tool call before proceeding with the normal agent turn.
    """
    conversation_history = request.messages

    # If human input is provided, execute the tool call before the agent's turn.
    if request.human_input:
        logger.info(
            f"Processing human input for tool call {request.human_input.tool_call_id} "
            f"in conversation {request.conversation_id}"
        )
        
        mcp_url = f"http://localhost:{settings.CONTAINERPORT_MCP_WORKFLOW_AGENT}/mcp"
        headers = {
            "X-User-ID": str(user_id),
            "X-Workflow-UUID": str(workflow_uuid),
        }
        transport = StreamableHttpTransport(url=mcp_url, headers=headers)
        mcp_client = MCPClient(transport)
        
        tool_result_content = ""
        async with mcp_client:
            try:
                tool_args = {
                    "suggested_name": request.human_input.user_input.get("name"),
                    "suggested_description": request.human_input.user_input.get("description"),
                }
                tool_result = await mcp_client.call_tool("feature_request", tool_args)
                
                if tool_result.structured_content is None:
                    payload = None
                elif 'result' in tool_result.structured_content:
                    payload = tool_result.structured_content['result']
                else:
                    payload = tool_result.structured_content
                
                tool_result_content = json.dumps(payload)

            except Exception as e:
                logger.error(f"Error executing tool during human input processing: {e}", exc_info=True)
                tool_result_content = json.dumps({"error": f"Failed to execute the feature request tool: {e}"})

        # Append the tool's result to the conversation history for the agent to process
        conversation_history.append(
            ChatMessage(
                role="tool",
                tool_call_id=request.human_input.tool_call_id,
                content=tool_result_content,
            )
        )

    # The loop ensures that the agent can complete its multi-step
    # thinking process (e.g., call a tool, get the result, and then form a response)
    # within a single API call from the frontend's perspective.
    # The frontend will call this endpoint repeatedly until is_complete is true.
    
    logger.info(f"Running chat step for conversation {request.conversation_id}")
    
    # Run one turn of the agent logic (either LLM call or tool execution)
    updated_history, human_input_required = await run_agent_turn(
        conversation_history, user_id=user_id, workflow_uuid=workflow_uuid
    )
    
    # If human input is required, we stop here and let the frontend handle it.
    if human_input_required:
        logger.info(f"Human input required for conversation {request.conversation_id}. Pausing.")
        return ChatStepResponse(
            conversation_id=request.conversation_id,
            messages=updated_history,
            is_complete=False, # The agent is not done, it's waiting for input
            human_input_required=human_input_required,
        )

    # Check the last message to determine if the turn is complete.
    last_message = updated_history[-1]
    is_complete = (last_message.role == "assistant" and not last_message.tool_calls)

    logger.info(f"Chat step for conversation {request.conversation_id} complete. Is final turn: {is_complete}")

    return ChatStepResponse(
        conversation_id=request.conversation_id,
        messages=updated_history,
        is_complete=is_complete,
    ) 