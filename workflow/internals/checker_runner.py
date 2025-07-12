import logging
from typing import Dict
from uuid import UUID

from jsonpath_ng import parse

from workflow.models import (
    StepOutputData,
    StopWorkflowChecker,
    StopWorkflowCheckerInstanceModel,
)

logger = logging.getLogger(__name__)


async def run_checker_step(
    instance: StopWorkflowCheckerInstanceModel,
    step_definition: StopWorkflowChecker,
    step_outputs: dict[UUID, StepOutputData],
) -> bool:
    """
    Evaluates the conditions of a StopWorkflowChecker step.
    Returns True if any stop condition is met, False otherwise.
    """
    logger.info(f"Executing Checker step for instance {instance.uuid}")
    for condition in step_definition.stop_conditions:
        try:
            # 1. Find the step output to inspect
            source_step_output = step_outputs.get(condition.step_definition_uuid)
            if source_step_output is None:
                logger.warning(
                    f"Checker condition referenced a step UUID ({condition.step_definition_uuid}) that has no output. Skipping."
                )
                continue

            # 2. Extract data using JSONPath
            jsonpath_expression = parse(condition.extraction_json_path)
            matches = jsonpath_expression.find(source_step_output.raw_data)

            if not matches:
                logger.info(f"JSONPath '{condition.extraction_json_path}' found no matches.")
                continue

            extracted_value = matches[0].value
            target_value = condition.target_value

            # 3. Evaluate the condition
            result = False
            op = condition.operator
            if op == "equals":
                result = extracted_value == target_value
            elif op == "not_equals":
                result = extracted_value != target_value
            elif op == "contains":
                result = target_value in extracted_value
            elif op == "greater_than":
                result = extracted_value > target_value
            elif op == "less_than":
                result = extracted_value < target_value

            logger.info(
                f"Checker condition evaluated: {extracted_value} {op} {target_value} -> {result}"
            )

            if result:
                return True  # Stop the workflow

        except Exception as e:
            logger.error(f"Error evaluating stop condition: {e}", exc_info=True)
            # For now, we'll ignore it and continue checking other conditions.
            continue

    # If no condition returned True, don't stop the workflow
    return False 