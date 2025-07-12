import asyncio
import json
import logging
import re
from uuid import UUID
from typing import Any

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
    CustomAgentInstanceModel,
)
from jsonpath_ng import parse

# Placeholder for a real LLM API client.
# In a real scenario, this would be in a separate, shared module.
from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)

logger = logging.getLogger(__name__)

# REGEX to find placeholders like <<step_output.uuid>> or <<trigger_output>>
placeholder_re = re.compile(r"<<(trigger_output|step_output\.([a-fA-F0-9-]+))>>")


def _resolve_data_reference(
    ref_key: str,
    step_definition: WorkflowStep,
    step_outputs: dict[UUID, StepOutputData],
    trigger_output: StepOutputData,
) -> Any:
    """
    Resolves a single data reference to its actual data.
    """
    if ref_key == "trigger_output":
        data_source = trigger_output
    else:
        # It's a step_output reference
        step_uuid_str = ref_key.split(".")[1]
        step_uuid = UUID(step_uuid_str)
        if step_uuid not in step_outputs:
            raise ValueError(f"Could not find output for referenced step {step_uuid}")
        data_source = step_outputs[step_uuid]

    # Agents get a compressed reference, others get the raw data.
    if step_definition.type == "custom_agent":
        return json.dumps({
            "summary": data_source.summary,
            "output_id": str(data_source.uuid),
            "comment": "The full data can be retrieved using the get_step_output tool with this ID.",
        })
    else:
        # LLM steps and others get the raw data directly.
        return data_source.raw_data


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
            full_match_key = match.group(1)  # e.g., "step_output.uuid-goes-here"
            return str(
                _resolve_data_reference(
                    full_match_key, step_definition, step_outputs, trigger_output
                )
            )

        prepared_config["system_prompt"] = placeholder_re.sub(
            replace_match, prepared_config["system_prompt"]
        )

    return prepared_config


async def run_workflow(workflow_instance_uuid: UUID, user_id: UUID):
    """
    The main entry point for executing a workflow instance.
    """
    logger.info(f"Starting run for workflow instance {workflow_instance_uuid}")
    instance = await db._get_workflow_instance_from_db(
        uuid=workflow_instance_uuid, user_id=user_id
    )
    if not instance:
        logger.error(f"Workflow instance {workflow_instance_uuid} not found.")
        return

    workflow = await workflow_client.get_with_details(
        workflow_uuid=instance.workflow_definition_uuid, user_id=user_id
    )
    if not workflow:
        instance.status = "failed"
        instance.error_message = "Workflow definition not found."
        await db._update_workflow_instance_in_db(instance, user_id)
        return

    # Keep track of the outputs of each step as it completes.
    step_outputs: dict[UUID, StepOutputData] = {}
    if instance.trigger_output:
        # The trigger's output doesn't have a step UUID, so we can't store it
        # in the dict. We'll handle it separately during input preparation.
        pass
    else:
        logger.warning("Workflow instance started with no trigger data.")
        # Create a dummy trigger output to avoid errors
        instance.trigger_output = await create_output_data(raw_data={}, summary_prompt="Empty trigger")

    # Create a map of step UUID to step definition for easy lookup
    step_definitions = {step.uuid: step for step in workflow.steps}

    for step_uuid in workflow.steps:
        step_def = step_definitions[step_uuid]
        step_instance = None
        try:
            # 1. Create Step Instance
            if step_def.type == "custom_llm":
                step_instance = await llm_client.create_instance(
                    workflow_instance_uuid, step_def.uuid, user_id
                )
            elif step_def.type == "custom_agent":
                step_instance = await agent_client.create_instance(
                    workflow_instance_uuid, step_def.uuid, user_id
                )
            elif step_def.type == "stop_checker":
                step_instance = await checker_client.create_instance(
                    workflow_instance_uuid, step_def.uuid, user_id
                )
            
            # 2. Prepare Inputs
            prepared_config = _prepare_input(
                step_def, step_outputs, instance.trigger_output
            )
            step_instance.input_data = prepared_config

            # 3. Execute Step
            raw_output = None
            should_stop = False
            if step_def.type == "custom_llm":
                raw_output = await llm_client.execute_step(
                    instance=step_instance,
                    llm_definition=step_def,
                    resolved_system_prompt=prepared_config["system_prompt"],
                )
            elif step_def.type == "custom_agent":
                updated_agent_instance = await agent_client.execute_step(
                    instance=step_instance,
                    agent_definition=step_def,
                    resolved_system_prompt=prepared_config["system_prompt"],
                )
                # The agent runner now populates the output directly on the instance
                step_instance = updated_agent_instance
                if updated_agent_instance.output:
                    raw_output = updated_agent_instance.output.raw_data
            elif step_def.type == "stop_checker":
                should_stop = await checker_client.execute_step(
                    instance=step_instance,
                    step_definition=step_def,
                    step_outputs=step_outputs,
                )
                if should_stop:
                    instance.status = "stopped"
                    logger.info(f"Workflow stopped by checker step {step_def.name}")
                    step_instance.status = "completed"
                    await db._update_step_instance_in_db(step_instance, user_id)
                    break # Exit the loop

            # 4. Process and Save Output
            if raw_output is not None:
                output_data = await create_output_data(
                    raw_data=raw_output, summary_prompt=f"Summarize the output of step '{step_def.name}'"
                )
                step_instance.output = output_data
                step_outputs[step_def.uuid] = output_data

            step_instance.status = "completed"

        except Exception as e:
            logger.error(f"Error executing step {step_def.uuid}: {e}", exc_info=True)
            instance.status = "failed"
            instance.error_message = str(e)
            if step_instance:
                step_instance.status = "failed"
                step_instance.error_message = str(e)
            break # Stop execution on failure
        finally:
            if step_instance:
                # Save the final state of the step instance via its client
                if step_def.type == "custom_llm":
                    await llm_client.save_instance(step_instance, user_id)
                elif step_def.type == "custom_agent":
                    await agent_client.save_instance(step_instance, user_id)
                elif step_def.type == "stop_checker":
                    await checker_client.save_instance(step_instance, user_id)

    # Finalize workflow instance status
    if instance.status not in ["failed", "stopped"]:
        instance.status = "completed"
    
    await db._update_workflow_instance_in_db(instance, user_id)
    logger.info(f"Finished run for workflow instance {workflow_instance_uuid} with status: {instance.status}") 