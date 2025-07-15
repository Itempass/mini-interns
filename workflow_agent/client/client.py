import logging
from typing import List
from uuid import UUID

from workflow_agent.client.internals.agent_runner import run_agent_turn
from workflow_agent.client.models import ChatMessage, ChatStepResponse, ChatRequest

logger = logging.getLogger(__name__)

async def run_chat_step(
    request: ChatRequest, user_id: UUID, workflow_uuid: UUID
) -> ChatStepResponse:
    """
    Runs the next step of a chat conversation with the workflow agent.
    This function orchestrates the agent's turn-based logic.
    """
    conversation_history = request.messages

    # The loop ensures that the agent can complete its multi-step
    # thinking process (e.g., call a tool, get the result, and then form a response)
    # within a single API call from the frontend's perspective.
    # The frontend will call this endpoint repeatedly until is_complete is true.
    
    logger.info(f"Running chat step for conversation {request.conversation_id}")
    
    # Run one turn of the agent logic (either LLM call or tool execution)
    updated_history = await run_agent_turn(
        conversation_history, user_id=user_id, workflow_uuid=workflow_uuid
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