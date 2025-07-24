import logging
import uuid
from typing import Any
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException

from agentlogger.src.client import save_log_entry
from agentlogger.src.models import (
    LogEntry,
    Message as LoggerMessage,
)
from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)
from workflow.internals.output_processor import create_output_data, generate_summary
from workflow.models import CustomLLM, CustomLLMInstanceModel, MessageModel, StepOutputData, WorkflowModel
from shared.config import settings
from user import client as user_client
from user.exceptions import InsufficientBalanceError

logger = logging.getLogger(__name__)


async def run_llm_step(
    llm_definition: CustomLLM,
    resolved_system_prompt: str,
    user_id: UUID,
    workflow_instance_uuid: UUID,
    workflow_definition: WorkflowModel,
) -> CustomLLMInstanceModel:
    """Runs a CustomLLM step."""
    logger.info(f"Starting execution for LLM step {llm_definition.uuid}")
    instance = CustomLLMInstanceModel(
        user_id=user_id,
        workflow_instance_uuid=workflow_instance_uuid,
        status="running",
        llm_definition_uuid=llm_definition.uuid,
    )

    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not found. Cannot proceed.")
    
    try:
        # --- Balance Check ---
        logger.info(f"Checking balance for user {user_id} before running LLM step.")
        user_client.check_user_balance(user_id)
        logger.info(f"User {user_id} has sufficient balance.")

        logger.debug(f"LLM definition: {llm_definition.model_dump_json(indent=2)}")
        logger.debug(f"Resolved system prompt: {resolved_system_prompt}")

        # The instance messages will be used to build the conversation history.
        # For a simple LLM step, we start with the resolved system prompt.
        instance.messages = [
            MessageModel(role="system", content=resolved_system_prompt),
            MessageModel(role="user", content="Proceed as instructed."),
        ]

        logger.info(f"Calling OpenRouter for instance {instance.uuid} with model {llm_definition.model}")
        # Use the OpenRouter service to get the LLM response
        response_data = await openrouter_service.get_llm_response(
            prompt="Proceed as instructed.",
            system_prompt=resolved_system_prompt,
            model=llm_definition.model,
        )
        logger.info(f"Received response from OpenRouter for instance {instance.uuid}")
        logger.debug(f"Response data: {response_data}")

        # Extract the content and other details from the response
        response_content = response_data["choices"][0]["message"]["content"]
        generation_id = response_data.get("id")
        usage = response_data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        
        # Get the cost
        total_cost = None
        if generation_id:
            try:
                total_cost = await openrouter_service.get_generation_cost(generation_id)
                if total_cost is not None and total_cost > 0:
                    logger.info(f"Deducting {total_cost} from balance of user {user_id}.")
                    user_client.deduct_from_balance(user_id, total_cost)
            except Exception as e:
                logger.error(f"Could not retrieve cost for generation {generation_id}: {e}")

        # Add the response to the messages
        instance.messages.append(MessageModel(role="assistant", content=response_content))

        # Package the result into a standard StepOutputData object
        # The final message content is the output
        final_content = response_content or "LLM provided no final answer."
        markdown_rep = f"{final_content}"
        instance.output = await create_output_data(
            markdown_representation=markdown_rep,
            user_id=user_id,
        )
        instance.status = "completed"
        logger.info(f"LLM step for instance {instance.uuid} completed successfully.")

    except InsufficientBalanceError as e:
        logger.warning(f"Blocking LLM step for user {user_id} due to insufficient balance.")
        instance.status = "failed"
        instance.error_message = str(e)
        # Re-raise as HTTPException to be caught by the API layer
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error during LLM step execution for instance {instance.uuid}: {e}", exc_info=True)
        instance.status = "failed"
        instance.error_message = str(e)
    finally:
        # This block ensures that we try to log the conversation even if an error occurs during the run.
        try:
            logger.info(f"Saving LLM conversation for instance {instance.uuid} to agentlogger.")
            
            logger_messages = [
                LoggerMessage.model_validate(msg.model_dump()) 
                for msg in instance.messages
            ]
            
            log_entry = LogEntry(
                user_id=str(user_id),
                log_type='custom_llm',
                workflow_id=str(workflow_definition.uuid),
                workflow_instance_id=str(workflow_instance_uuid),
                workflow_name=workflow_definition.name,
                step_id=str(llm_definition.uuid),
                step_instance_id=str(instance.uuid),
                step_name=llm_definition.name,
                messages=logger_messages,
                start_time=instance.started_at,
                end_time=datetime.now(timezone.utc),
                reference_string="TODO: PASS REFERENCE STRING",
                # Add token and cost info
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                total_cost=total_cost,
            )
            await save_log_entry(log_entry)
            logger.info(f"Successfully saved LLM conversation for instance {instance.uuid}.")
        except Exception as e:
            logger.error(
                f"Failed to save LLM conversation for instance {instance.uuid} to agentlogger: {e}",
                exc_info=True,
            )

    instance.finished_at = datetime.now(timezone.utc)
    # Return the final instance
    return instance 