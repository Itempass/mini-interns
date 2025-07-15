import asyncio
import json
import logging
import re
from uuid import UUID
from typing import Any, Dict, List

import workflow.client as workflow_client
import workflow.internals.database as db
from workflow.internals import llm_runner
from workflow.internals import agent_runner
from workflow.internals.output_processor import create_output_data, generate_summary
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


def _prepare_input(
    step_definition: WorkflowStep,
    workflow_instance: WorkflowInstanceModel,
) -> Dict[str, Any]:
    """
    Prepares the configuration for a step by replacing placeholders
    in its system prompt with the outputs of previous steps.
    """
    prepared_config = step_definition.model_dump()
    system_prompt = prepared_config.get("system_prompt", "")
    if not system_prompt:
        return prepared_config

    # Create a unified dictionary of all available outputs, keyed by their source name.
    available_outputs: Dict[str, StepOutputData] = {}
    if workflow_instance.trigger_output:
        available_outputs["trigger_output"] = workflow_instance.trigger_output
        logger.info(f"RUNNER_DEBUG: Added trigger_output to available_outputs")
    
    logger.info(f"RUNNER_DEBUG: Found {len(workflow_instance.step_instances)} step instances in workflow")
    for i, inst in enumerate(workflow_instance.step_instances):
        logger.info(f"RUNNER_DEBUG: Step instance {i}: type={type(inst).__name__}, has_output={inst.output is not None}")
        logger.info(f"RUNNER_DEBUG: Step instance {i} attributes: {list(vars(inst).keys())}")
        
        if inst.output:
            def_uuid = None
            if hasattr(inst, 'llm_definition_uuid'):
                def_uuid = inst.llm_definition_uuid
                logger.info(f"RUNNER_DEBUG: Step instance {i} has llm_definition_uuid: {def_uuid}")
            elif hasattr(inst, 'agent_definition_uuid'):
                def_uuid = inst.agent_definition_uuid
                logger.info(f"RUNNER_DEBUG: Step instance {i} has agent_definition_uuid: {def_uuid}")
            elif hasattr(inst, 'checker_definition_uuid'):
                def_uuid = inst.checker_definition_uuid
                logger.info(f"RUNNER_DEBUG: Step instance {i} has checker_definition_uuid: {def_uuid}")

            if def_uuid:
                logger.info(f"RUNNER_DEBUG: Found previous step instance of type {type(inst).__name__} with output. Storing output under key {str(def_uuid)}.")
                available_outputs[str(def_uuid)] = inst.output
            else:
                logger.warning(f"RUNNER_DEBUG: Found previous step instance of type {type(inst).__name__} with output, but could not determine its definition UUID.")
    
    logger.info(f"RUNNER_DEBUG: Final available_outputs keys: {list(available_outputs.keys())}")

    # This regex finds all occurrences of <<some_placeholder>>
    placeholder_re = re.compile(r"<<(.*?)>>")

    def replace_match(match):
        placeholder = match.group(1).strip()
        logger.info(f"RUNNER_DEBUG: Processing placeholder '<<{placeholder}>>'")

        lookup_key = placeholder
        if placeholder.startswith("step_output."):
            try:
                lookup_key = placeholder.split('.', 1)[1]
            except IndexError:
                logger.warning(f"RUNNER_DEBUG: Malformed step_output placeholder '<<{placeholder}>>'.")
                return f"<<{placeholder}>>"

        if lookup_key in available_outputs:
            output_data = available_outputs[lookup_key]
            logger.info(f"RUNNER_DEBUG: Found data for key '{lookup_key}'. Replacing with markdown representation.")
            return output_data.markdown_representation
        else:
            logger.warning(f"RUNNER_DEBUG: Could not find data for placeholder '<<{placeholder}>>' (looked for key '{lookup_key}'). Leaving it as is.")
            return f"<<{placeholder}>>"

    prepared_config["system_prompt"] = placeholder_re.sub(replace_match, system_prompt)
    return prepared_config


async def run_workflow(instance_uuid: UUID, user_id: UUID):
    """
    Asynchronously runs a workflow instance from start to finish.
    It fetches the workflow definition, then iterates through the steps,
    executing each one in sequence and passing the output of previous
    steps to subsequent ones.
    """
    logger.info(f"Starting workflow run for instance {instance_uuid}")
    instance = await db._get_workflow_instance_from_db(instance_uuid, user_id=user_id)
    if not instance:
        logger.error(f"Workflow instance {instance_uuid} not found.")
        return

    workflow_def = await db._get_workflow_from_db(instance.workflow_definition_uuid, user_id=user_id)
    if not workflow_def:
        message = f"Workflow definition {instance.workflow_definition_uuid} not found for instance {instance.uuid}. Aborting."
        logger.error(message)
        instance.status = "failed"
        instance.error_message = message
        await db._update_workflow_instance_in_db(instance, user_id)
        return

    logger.info(f"Executing workflow '{workflow_def.name}' ({workflow_def.uuid}) for instance {instance.uuid}")

    current_step_index = 0
    while True:
        if current_step_index >= len(workflow_def.steps):
            logger.info(f"Workflow {instance.uuid} completed all steps.")
            instance.status = "completed"
            await db._update_workflow_instance_in_db(instance, user_id)
            break

        step_uuid = workflow_def.steps[current_step_index]
        step_def = await db._get_step_from_db(step_uuid, user_id=user_id)

        if not step_def:
            message = f"Could not find step definition for {step_uuid} in workflow {instance.uuid}. Aborting."
            logger.error(message)
            instance.status = "failed"
            instance.error_message = message
            await db._update_workflow_instance_in_db(instance, user_id)
            break

        try:
            # Prepare inputs by resolving placeholders
            logger.info(f"Preparing inputs for step {step_uuid}")
            prepared_config = _prepare_input(step_def, instance)

            step_instance: WorkflowStepInstance = None
            if step_def.type == "custom_llm":
                step_instance = await llm_runner.run_llm_step(
                    step_def, prepared_config["system_prompt"], user_id, instance.uuid
                )
            elif step_def.type == "custom_agent":
                step_instance = await agent_runner.run_agent_step(
                    step_def, prepared_config["system_prompt"], user_id, instance.uuid
                )
            elif step_def.type == "stop_checker":
                logger.info("stop checker not implemented")

            # After the step runs, append its instance to the main workflow instance.
            if step_instance:
                instance.step_instances.append(step_instance)
                await db._update_workflow_instance_in_db(instance, user_id)

            logger.info(f"RUNNER_DEBUG: End of loop for step {step_uuid}. Total instances on workflow model: {len(instance.step_instances)}")

        except Exception as e:
            message = f"Error executing step {step_uuid} in workflow {instance.uuid}: {e}"
            logger.error(message, exc_info=True)
            instance.status = "failed"
            instance.error_message = message
            await db._update_workflow_instance_in_db(instance, user_id)
            break  # Stop workflow on step failure

        current_step_index += 1
