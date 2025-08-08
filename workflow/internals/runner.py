import asyncio
import json
import logging
import re
from uuid import UUID
from typing import Any, Dict, List
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agentlogger.src.client import save_log_entry
from agentlogger.src.models import LogEntry, Message
import workflow.client as workflow_client
import workflow.internals.database as db
from workflow.internals import llm_runner
from workflow.internals import agent_runner
from workflow.internals import checker_runner
from workflow.internals.output_processor import create_output_data, generate_summary
from workflow.models import (
    CustomAgent,
    CustomLLM,
    StepOutputData,
    StopWorkflowChecker,
    StopWorkflowCheckerInstanceModel,
    WorkflowInstanceModel,
    WorkflowStep,
    WorkflowStepInstance,
    RAGStep,
    RAGStepInstanceModel,
)
from jsonpath_ng import parse

# Placeholder for a real LLM API client.
# In a real scenario, this would be in a separate, shared module.
from mcp_servers.tone_of_voice_mcpserver.src.services.openrouter_service import (
    openrouter_service,
)

from rag import client as rag_client

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
        # For checker steps, we don't need to prepare any system prompt
        if isinstance(step_definition, StopWorkflowChecker):
            return prepared_config
        return prepared_config

    # Create a unified dictionary of all available outputs, keyed by their source name.
    available_outputs: Dict[str, StepOutputData] = {}
    if workflow_instance.trigger_output:
        available_outputs["trigger_output"] = workflow_instance.trigger_output
        logger.info(f"RUNNER_DEBUG: Added trigger_output to available_outputs")
    
    logger.info(f"RUNNER_DEBUG: Found {len(workflow_instance.step_instances)} step instances in workflow")
    for i, inst in enumerate(workflow_instance.step_instances):
        # Checker instances have no output and should be skipped
        if isinstance(inst, StopWorkflowCheckerInstanceModel):
            continue
            
        logger.info(f"RUNNER_DEBUG: Step instance {i}: type={type(inst).__name__}, has_output={hasattr(inst, 'output') and inst.output is not None}")
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
                # Checker steps don't produce output for other steps to consume
                continue
            elif hasattr(inst, 'rag_definition_uuid'):
                def_uuid = inst.rag_definition_uuid
                logger.info(f"RUNNER_DEBUG: Step instance {i} has rag_definition_uuid: {def_uuid}")

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

        # Handle built-in dynamic values
        if placeholder.startswith("CURRENT_DATE"):
            parts = placeholder.split('.')
            timezone_str = parts[1] if len(parts) > 1 else 'UTC'
            try:
                tz = ZoneInfo(timezone_str)
                current_date = datetime.now(tz).strftime('%Y-%m-%d')
                logger.info(f"RUNNER_DEBUG: Replacing '<<{placeholder}>>' with current date '{current_date}' for timezone '{timezone_str}'")
                return current_date
            except ZoneInfoNotFoundError:
                logger.warning(f"RUNNER_DEBUG: Invalid timezone '{timezone_str}' for placeholder '<<{placeholder}>>'. Falling back to UTC.")
                return datetime.now(timezone.utc).strftime('%Y-%m-%d')
            except Exception as e:
                logger.error(f"RUNNER_DEBUG: Error processing date for '<<{placeholder}>>': {e}. Falling back to UTC.", exc_info=True)
                return datetime.now(timezone.utc).strftime('%Y-%m-%d')

        # Handle step outputs
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
    log_entry = None
    instance = None
    try:
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

        log_entry = LogEntry(
            user_id=str(user_id),
            log_type='workflow',
            workflow_id=str(workflow_def.uuid),
            workflow_instance_id=str(instance.uuid),
            workflow_name=workflow_def.name,
            start_time=instance.created_at,
            reference_string=instance.trigger_output.markdown_representation if instance.trigger_output else "Workflow started without trigger data."
        )

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
                    llm_instance = await llm_runner.run_llm_step(
                        llm_definition=step_def,
                        resolved_system_prompt=prepared_config["system_prompt"],
                        user_id=user_id,
                        workflow_instance_uuid=instance_uuid,
                        workflow_definition=workflow_def,
                    )
                    instance.step_instances.append(llm_instance)
                    await db._update_workflow_instance_in_db(instance, user_id)
                elif step_def.type == "custom_agent":
                    agent_instance = await agent_runner.run_agent_step(
                        agent_definition=step_def,
                        resolved_system_prompt=prepared_config["system_prompt"],
                        user_id=user_id,
                        workflow_instance_uuid=instance_uuid,
                        workflow_definition=workflow_def,
                    )
                    instance.step_instances.append(agent_instance)
                    await db._update_workflow_instance_in_db(instance, user_id)
                elif step_def.type == "stop_checker":
                    # Create the instance model for the checker
                    checker_instance = StopWorkflowCheckerInstanceModel(
                        user_id=user_id,
                        workflow_instance_uuid=instance_uuid,
                        status="running",
                        checker_definition_uuid=step_def.uuid,
                    )
                    instance.step_instances.append(checker_instance)
                    await db._update_workflow_instance_in_db(instance, user_id)
                    
                    # Collate all previous step outputs
                    step_outputs = {}
                    if instance.trigger_output:
                        step_outputs["trigger_output"] = instance.trigger_output # Although trigger can't be checked yet
                    for inst in instance.step_instances:
                        # Checker instances have no output and should be skipped
                        if isinstance(inst, StopWorkflowCheckerInstanceModel):
                            continue
                        if inst.output:
                            def_uuid = getattr(inst, 'llm_definition_uuid', None) or getattr(inst, 'agent_definition_uuid', None) or getattr(inst, 'rag_definition_uuid', None)
                            if def_uuid:
                                step_outputs[def_uuid] = inst.output

                    result = await checker_runner.run_checker_step(
                        instance=checker_instance,
                        step_definition=step_def,
                        step_outputs=step_outputs
                    )

                    checker_instance.status = "completed"
                    checker_instance.finished_at = datetime.now(timezone.utc)
                    await db._update_workflow_instance_in_db(instance, user_id)

                    # Create a log entry for the checker step
                    checker_log_entry = LogEntry(
                        user_id=str(user_id),
                        log_type='stop_checker',
                        step_id=str(step_def.uuid),
                        step_name=step_def.name,
                        workflow_instance_id=str(instance.uuid),
                        messages=[
                            Message(role="system", content=f"Input to be evaluated:\n\n---\n{result.evaluated_input}\n---"),
                            Message(role="system", content=f"Result: {result.reason}")
                        ],
                        start_time=checker_instance.started_at,
                        end_time=checker_instance.finished_at,
                    )
                    await save_log_entry(checker_log_entry)

                    if result.should_stop:
                        logger.info(f"Workflow {instance.uuid} stopped by checker step {step_def.name} ({step_def.uuid}).")
                        instance.status = "stopped"
                        await db._update_workflow_instance_in_db(instance, user_id)
                        break # Exit the while loop
                elif step_def.type == "rag":
                    # Validate that a vector database has been selected
                    if not step_def.vectordb_uuid:
                        raise ValueError("RAG step is not configured. Please edit the step and select a vector database.")
                    # Create the instance model for RAG
                    rag_instance = RAGStepInstanceModel(
                        user_id=user_id,
                        workflow_instance_uuid=instance_uuid,
                        status="running",
                        rag_definition_uuid=step_def.uuid,
                    )
                    instance.step_instances.append(rag_instance)
                    await db._update_workflow_instance_in_db(instance, user_id)

                    # Execute RAG step via rag client
                    result = await rag_client.execute_step(
                        user_id=user_id,
                        workflow_instance_uuid=instance_uuid,
                        rag_definition_uuid=step_def.uuid,
                        prompt=prepared_config["system_prompt"],
                        vectordb_uuid=step_def.vectordb_uuid,
                        rerank=bool(step_def.rerank),
                        top_k=int(step_def.top_k),
                    )

                    rag_instance.output = result["output"]
                    rag_instance.status = "completed"
                    rag_instance.finished_at = datetime.now(timezone.utc)
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
    except Exception as e:
        logger.error(f"Unhandled exception in workflow run {instance_uuid}: {e}", exc_info=True)
        if instance:
            instance.status = "failed"
            instance.error_message = str(e)
            await db._update_workflow_instance_in_db(instance, user_id)
    finally:
        if log_entry and instance:
            final_instance = await db._get_workflow_instance_from_db(instance_uuid, user_id=user_id)
            summary_message = f"Workflow '{log_entry.workflow_name}' finished with status: {final_instance.status}."
            if final_instance.error_message:
                summary_message += f"\nError: {final_instance.error_message}"

            log_entry.messages = [Message(role="system", content=summary_message)]
            log_entry.end_time = datetime.now(timezone.utc)
            await save_log_entry(log_entry)
            logger.info(f"Saved workflow log for instance {instance_uuid}")
