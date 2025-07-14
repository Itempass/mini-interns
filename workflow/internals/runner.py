import asyncio
import json
import logging
import re
from uuid import UUID
from typing import Any, Dict

import workflow.agent_client as agent_client
import workflow.checker_client as checker_client
import workflow.client as workflow_client
import workflow.internals.database as db
import workflow.llm_client as llm_client
from workflow.internals.output_processor import create_output_data
from workflow.models import (
    CustomAgent,
    CustomLLM,
    StepOutputData,
    StopWorkflowChecker,
    WorkflowInstanceModel,
    WorkflowStep,
    WorkflowStepInstance,
)
from jsonpath_ng import parse

# Placeholder for a real LLM API client.
# In a real scenario, this would be in a separate, shared module.
from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)

logger = logging.getLogger(__name__)

# REGEX to find placeholders like <<trigger_output>> or <<step_output.uuid-goes-here>>
placeholder_re = re.compile(r"<<([^>]+)>>")


def _prepare_input(
    step_definition: WorkflowStep,
    step_outputs: dict[UUID, StepOutputData],
    trigger_output: StepOutputData,
) -> dict:
    """
    Prepares the input for a step by resolving data references in its config.
    It inspects the step's `system_prompt` or other fields and injects the
    actual data from previous steps or the trigger.
    """
    config = step_definition.model_dump()
    prepared_config = config.copy()

    # For now, we only resolve placeholders in the system_prompt.
    # This could be extended to other fields.
    if "system_prompt" in prepared_config and prepared_config["system_prompt"]:

        def replace_match(match):
            placeholder = match.group(1).strip()  # e.g., "trigger_output" or "step_output.uuid-goes-here"

            parts = placeholder.split('.')
            base_ref_type = parts[0]
            
            data_source: StepOutputData

            if base_ref_type == "trigger_output":
                if len(parts) > 1:
                    raise ValueError("The <<trigger_output>> placeholder does not support any sub-paths.")
                data_source = trigger_output
            elif base_ref_type == "step_output":
                if len(parts) != 2:
                    raise ValueError(f"Invalid step reference format. Use '<<step_output.UUID>>'. Found: '{placeholder}'")
                step_uuid_str = parts[1]
                try:
                    step_uuid = UUID(step_uuid_str)
                except ValueError:
                    raise ValueError(f"Invalid UUID in step reference: {step_uuid_str}")
                
                if step_uuid not in step_outputs:
                    raise ValueError(f"Could not find output for referenced step {step_uuid}")
                data_source = step_outputs[step_uuid]
            else:
                raise ValueError(f"Unknown placeholder base '{base_ref_type}' in '{placeholder}'")

            # For agents, inject a detailed markdown block with a schema.
            # For other step types, just provide the most representative text content.
            if step_definition.type == "custom_agent":
                
                # Dynamically build the schema for the container's top-level properties
                container_schema = {
                    "type": "object",
                    "properties": {}
                }
                if data_source.raw_data is not None:
                    # If the raw_data has its own schema, embed it.
                    if data_source.data_schema:
                         container_schema["properties"]["raw_data"] = {
                            "description": "The raw, structured data from the step.",
                            **data_source.data_schema
                         }
                    else: # Otherwise, just describe its type.
                        container_schema["properties"]["raw_data"] = {
                            "type": str(type(data_source.raw_data).__name__),
                            "description": "The raw, unstructured data from the step."
                        }

                if data_source.markdown_representation is not None:
                    container_schema["properties"]["markdown_representation"] = {
                        "type": "string",
                        "description": "A long-form markdown version of the data, useful for summarization or analysis."
                    }
                
                schema_json_string = json.dumps(container_schema, indent=2)

                return (
                    f"DATA CONTAINER:\n"
                    f"* summary: {data_source.summary}\n"
                    f"* id: {data_source.uuid}\n"
                    f"* data_schema:\n"
                    f"  This container provides the following fields. You can access them using a JSONPath "
                    f"(e.g., '$.raw_data.messageId' or '$.markdown_representation').\n"
                    f"  ```json\n{schema_json_string}\n  ```"
                )
            else: 
                replacement = data_source.markdown_representation or data_source.raw_data
                if isinstance(replacement, (dict, list)):
                    return json.dumps(replacement)
                return str(replacement)

        prepared_config["system_prompt"] = placeholder_re.sub(
            replace_match, prepared_config["system_prompt"]
        )

    return prepared_config


async def run_workflow(workflow_instance_uuid: UUID, user_id: UUID):
    """
    The main entry point for executing a workflow instance.
    """
    print(f"--- ENTERING run_workflow for instance {workflow_instance_uuid} ---")
    logger.info(f"Starting run for workflow instance {workflow_instance_uuid}")
    instance = await db._get_workflow_instance_from_db(
        uuid=workflow_instance_uuid, user_id=user_id
    )
    if not instance:
        logger.error(f"Workflow instance {workflow_instance_uuid} not found.")
        return

    workflow = await workflow_client.get(
        uuid=instance.workflow_definition_uuid, user_id=user_id
    )
    if not workflow:
        instance.status = "failed"
        instance.error_message = "Workflow definition not found."
        await db._update_workflow_instance_in_db(instance, user_id)
        return

    # Keep track of the outputs of each step as it completes.
    step_outputs: dict[UUID, StepOutputData] = {}
    if instance.trigger_output:
        # The trigger's output is handled directly by _prepare_input.
        pass
    else:
        logger.warning(f"Workflow instance {workflow_instance_uuid} started with no trigger data.")
        # Create a dummy trigger output to avoid errors
        instance.trigger_output = await create_output_data(
            raw_data={"message": "No trigger data provided."},
            summary="Empty trigger",
        )

    # The `workflow.steps` is a list of step UUIDs. We fetch each one before execution.
    for step_uuid in workflow.steps:
        step_def = await db._get_step_from_db(uuid=step_uuid, user_id=user_id)
        if not step_def:
            instance.status = "failed"
            instance.error_message = f"Step definition {step_uuid} not found."
            await db._update_workflow_instance_in_db(instance, user_id)
            logger.error(f"Workflow instance {workflow_instance_uuid} failed because step {step_uuid} was not found.")
            return

        step_instance = None
        try:
            # 1. Create Step Instance record
            if step_def.type == "custom_llm":
                step_instance = await llm_client.create_instance(
                    workflow_instance_uuid=workflow_instance_uuid, 
                    llm_definition_uuid=step_def.uuid, 
                    user_id=user_id
                )
            elif step_def.type == "custom_agent":
                step_instance = await agent_client.create_instance(
                    workflow_instance_uuid=workflow_instance_uuid, 
                    agent_definition_uuid=step_def.uuid, 
                    user_id=user_id
                )
            elif step_def.type == "stop_checker":
                step_instance = await checker_client.create_instance(
                    workflow_instance_uuid=workflow_instance_uuid, 
                    checker_definition_uuid=step_def.uuid, 
                    user_id=user_id
                )
            else:
                raise ValueError(f"Unknown step type: {step_def.type}")

            # 2. Prepare Inputs by resolving placeholders
            prepared_config = _prepare_input(
                step_def, step_outputs, instance.trigger_output
            )
            step_instance.input_data = prepared_config

            # 3. Execute Step
            should_stop = False
            if step_def.type == "custom_llm":
                step_instance = await llm_client.execute_step(
                    instance=step_instance,
                    llm_definition=step_def,
                    resolved_system_prompt=prepared_config["system_prompt"],
                    user_id=user_id,
                )
            elif step_def.type == "custom_agent":
                step_instance = await agent_client.execute_step(
                    instance=step_instance,
                    agent_definition=step_def,
                    resolved_system_prompt=prepared_config["system_prompt"],
                    user_id=user_id,
                )
            elif step_def.type == "stop_checker":
                should_stop = await checker_client.execute_step(
                    instance=step_instance,
                    step_definition=step_def,
                    step_outputs=step_outputs
                )

            # Mark the step as completed and save its state, since execution was successful
            step_instance.status = "completed"
            await db._update_step_instance_in_db(instance=step_instance, user_id=user_id)
            print(f"--- Step instance {step_instance.uuid} marked as completed and saved ---")

            # 4. Process Output
            if step_instance and hasattr(step_instance, 'output') and step_instance.output:
                step_outputs[step_def.uuid] = step_instance.output

            if should_stop:
                logger.info(
                    f"Stopping workflow {workflow_instance_uuid} as requested by step {step_uuid}."
                )
                instance.status = "completed"
                await db._update_workflow_instance_in_db(instance, user_id)
                break
        except Exception as e:
            logger.error(f"Error executing step {step_uuid} in workflow {workflow_instance_uuid}: {e}", exc_info=True)
            instance.status = "failed"
            instance.error_message = f"Error in step {step_uuid}: {e}"
            if step_instance:
                step_instance.status = "failed"
                step_instance.error_message = str(e)
                # Ensure the failed step instance is saved
                await db._update_step_instance_in_db(instance=step_instance, user_id=user_id)
            
            await db._update_workflow_instance_in_db(instance, user_id)
            return  # Stop execution on failure

    # Finalize the workflow instance state
    if instance.status not in ["failed", "completed"]:  # completed can be set by a checker
        instance.status = "completed"

    await db._update_workflow_instance_in_db(instance, user_id=user_id)
    logger.info(
        f"Finished run for workflow instance {workflow_instance_uuid} with status {instance.status}"
    )
    print(f"--- EXITING run_workflow for instance {workflow_instance_uuid} ---")
