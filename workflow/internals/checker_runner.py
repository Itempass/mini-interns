import logging
from typing import Dict
from uuid import UUID

from workflow.models import (
    CheckerResult,
    StepOutputData,
    StopWorkflowChecker,
    StopWorkflowCheckerInstanceModel,
)

logger = logging.getLogger(__name__)


async def run_checker_step(
    instance: StopWorkflowCheckerInstanceModel,
    step_definition: StopWorkflowChecker,
    step_outputs: dict[UUID, StepOutputData],
) -> CheckerResult:
    """
    Evaluates the conditions of a StopWorkflowChecker step.
    Returns a CheckerResult object with the outcome and a reason.
    """
    logger.info(f"Executing Checker step for instance {instance.uuid}")
    evaluated_text = ""

    # 1. Check if a step to check is selected
    if not step_definition.step_to_check_uuid:
        reason = "Checker step has no step_to_check_uuid configured. Not stopping."
        logger.warning(reason)
        return CheckerResult(should_stop=False, reason=reason, evaluated_input=evaluated_text)

    # 2. Find the step output to inspect
    source_step_output = step_outputs.get(step_definition.step_to_check_uuid)
    if source_step_output is None:
        reason = f"Checker could not find output for step UUID {step_definition.step_to_check_uuid}. Not stopping."
        logger.warning(reason)
        return CheckerResult(should_stop=False, reason=reason, evaluated_input=evaluated_text)

    # 3. Check for matches
    evaluated_text = source_step_output.markdown_representation.lower()
    match_found = any(val.lower() in evaluated_text for val in step_definition.match_values)
    
    logger.info(f"Checker ({step_definition.name}): Mode='{step_definition.check_mode}', MatchFound={match_found}")

    # 4. Decide whether to stop
    if step_definition.check_mode == "stop_if_output_contains":
        if match_found:
            reason = f"Stopping workflow because a match was found for one of the values: {step_definition.match_values}."
            logger.info(reason)
            return CheckerResult(should_stop=True, reason=reason, evaluated_input=evaluated_text)
        else:
            reason = "Not stopping workflow because no match was found."
            logger.info(reason)
            return CheckerResult(should_stop=False, reason=reason, evaluated_input=evaluated_text)
    elif step_definition.check_mode == "continue_if_output_contains":
        if not match_found:
            reason = f"Stopping workflow because no match was found for any of the values: {step_definition.match_values}."
            logger.info(reason)
            return CheckerResult(should_stop=True, reason=reason, evaluated_input=evaluated_text)
        else:
            reason = "Not stopping workflow because a match was found."
            logger.info(reason)
            return CheckerResult(should_stop=False, reason=reason, evaluated_input=evaluated_text)

    # Default case, should not be reached
    return CheckerResult(should_stop=False, reason="Default case reached in checker; this should not happen.", evaluated_input=evaluated_text) 