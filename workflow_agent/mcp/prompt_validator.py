from typing import List
import re
from uuid import UUID

from workflow.models import WorkflowWithDetails


def validate_prompt_references(
    system_prompt: str, workflow: WorkflowWithDetails, step_uuid_for_prompt: UUID
):
    """
    Validates references like <<trigger_output>> and <<step_output.UUID>> in a system prompt.

    Args:
        system_prompt: The system prompt content to validate.
        workflow: The full workflow details.
        step_uuid_for_prompt: The UUID of the step this prompt belongs to. For a new step, this can be a dummy UUID.

    Raises:
        ValueError: If any invalid references are found, with a detailed message.
    """
    references = re.findall(r"<<(.+?)>>", system_prompt)
    if not references:
        return

    workflow_step_uuids = [s.uuid for s in workflow.steps]
    try:
        current_step_index = workflow_step_uuids.index(step_uuid_for_prompt)
        valid_step_uuids_for_reference = workflow_step_uuids[:current_step_index]
    except ValueError:
        valid_step_uuids_for_reference = workflow_step_uuids

    valid_step_uuids_for_reference_str = {
        str(uuid) for uuid in valid_step_uuids_for_reference
    }

    invalid_references = {}
    for ref in references:
        parts = ref.split(".")
        base = parts[0]

        if base == "trigger_output":
            if len(parts) > 1:
                invalid_references[ref] = "<<trigger_output>>"
        elif base == "step_output":
            if len(parts) != 2:
                invalid_references[ref] = "Correct format is <<step_output.STEP_UUID>>"
            else:
                step_uuid_str = parts[1]
                try:
                    UUID(step_uuid_str)
                except ValueError:
                    invalid_references[
                        ref
                    ] = f"'{step_uuid_str}' is not a valid UUID."
                    continue

                if step_uuid_str not in valid_step_uuids_for_reference_str:
                    invalid_references[
                        ref
                    ] = f"Step with UUID '{step_uuid_str}' is not a valid preceding step."
        else:
            invalid_references[ref] = (
                "References must start with 'trigger_output' or 'step_output'."
            )

    if invalid_references:
        error_messages = []
        for invalid_ref, suggestion in invalid_references.items():
            if (
                "Correct format" in suggestion
                or "not a valid" in suggestion
                or "must start with" in suggestion
            ):
                error_messages.append(
                    f"Invalid reference '<<{invalid_ref}>>': {suggestion}"
                )
            else:
                error_messages.append(
                    f"Invalid reference '<<{invalid_ref}>>'. Did you mean '{suggestion}'?"
                )

        valid_refs = ["'<<trigger_output>>'"]
        if valid_step_uuids_for_reference_str:
            valid_step_refs = ", ".join(
                [
                    f"'<<step_output.{uuid}>>'"
                    for uuid in valid_step_uuids_for_reference_str
                ]
            )
            if valid_step_refs:
                valid_refs.append(valid_step_refs)

        raise ValueError(
            "Found invalid references in system prompt:\n"
            + "\n".join(error_messages)
            + f"\n\nValid references for this step are: {', '.join(valid_refs)}."
        ) 