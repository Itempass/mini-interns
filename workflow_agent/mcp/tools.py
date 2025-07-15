from typing import Any, Dict, List, Optional
from uuid import UUID

import workflow.agent_client as agent_client
import workflow.client as workflow_client
import workflow.llm_client as llm_client
import workflow.trigger_client as trigger_client
from workflow_agent.mcp.dependencies import get_context_from_headers
from workflow_agent.mcp.mcp_builder import mcp_builder


@mcp_builder.tool()
async def get_workflow_details() -> dict:
    """
    Retrieves the full, detailed configuration of a specific workflow, including its name, description, trigger, and all of its steps in order.
    You can use <<trigger_output>> or <<step_output.[step uuid]>> to reference the trigger output or the output of a previous step.
    """
    context = get_context_from_headers()
    workflow = await workflow_client.get_with_details(
        workflow_uuid=context.workflow_uuid, user_id=context.user_id
    )
    return workflow.model_dump() if workflow else None


@mcp_builder.tool()
async def list_available_triggers() -> List[dict]:
    """
    Returns a list of all available trigger types that can be used to start a workflow. Each trigger type includes its 'id', 'name', and 'description'.
    """
    return await workflow_client.list_available_trigger_types()


@mcp_builder.tool()
async def set_trigger(trigger_type_id: str) -> dict:
    """
    Sets or replaces the trigger for a specific workflow. Use 'list_available_triggers' to find the correct 'trigger_type_id'. 
    You can use <<trigger_output>> to reference the trigger output.
    """
    context = get_context_from_headers()
    workflow = await workflow_client.set_trigger(
        workflow_uuid=context.workflow_uuid,
        trigger_type_id=trigger_type_id,
        user_id=context.user_id,
    )
    return workflow.model_dump()


@mcp_builder.tool()
async def update_trigger_settings(
    trigger_uuid: str,
    filter_rules: dict,
) -> dict:
    """
    Updates the settings of an existing trigger. The 'filter_rules' determine the conditions under which the workflow runs. The 'trigger_uuid' can be found in the workflow details. Returns the updated `TriggerModel`.
    """
    context = get_context_from_headers()
    trigger = await trigger_client.get(
        uuid=UUID(trigger_uuid), user_id=context.user_id
    )
    if not trigger:
        raise ValueError("Trigger not found")
    trigger.filter_rules = filter_rules
    updated_trigger = await trigger_client.update(trigger, user_id=context.user_id)
    return updated_trigger.model_dump()


@mcp_builder.tool()
async def list_available_step_types() -> List[dict]:
    """
    Returns a list of all available step types that can be added to a workflow, such as 'custom_llm' or 'custom_agent'.
    """
    return await workflow_client.list_available_step_types()


@mcp_builder.tool()
async def add_step(
    step_type: str,
    name: str,
    system_prompt: Optional[str] = None,
) -> dict:
    """
    Adds a new step to the end of a specified workflow, optionally setting its system prompt.
    Use 'list_available_step_types' to see valid options for 'step_type'.
    You can use <<trigger_output>> or <<step_output.[step uuid]>> to reference the trigger output or the output of a previous step.
    """
    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow_uuid = context.workflow_uuid
    workflow = await workflow_client.add_new_step(
        workflow_uuid=workflow_uuid,
        step_type=step_type,
        name=name,
        user_id=user_uuid,
    )

    if system_prompt and step_type in ["custom_llm", "custom_agent"]:
        new_step_uuid = workflow.steps[-1]

        step_to_update = None
        if step_type == "custom_llm":
            step_to_update = await llm_client.get(uuid=new_step_uuid, user_id=user_uuid)
        elif step_type == "custom_agent":
            step_to_update = await agent_client.get(
                uuid=new_step_uuid, user_id=user_uuid
            )

        if not step_to_update:
            raise ValueError("Newly added step not found. This should not happen.")

        step_to_update.system_prompt = system_prompt
        await workflow_client.update_step(step_to_update, user_uuid)

    workflow = await workflow_client.get_with_details(workflow_uuid, user_uuid)

    return workflow.model_dump()


@mcp_builder.tool()
async def remove_step(step_uuid: str) -> None:
    """
    Removes a specific step from a workflow. The agent can find the 'step_uuid' from the workflow details.
    """
    context = get_context_from_headers()
    await workflow_client.delete_step(
        workflow_uuid=context.workflow_uuid,
        step_uuid=UUID(step_uuid),
        user_id=context.user_id,
    )
    return None


@mcp_builder.tool()
async def reorder_steps(ordered_step_uuids: List[str]) -> dict:
    """
    Changes the execution order of steps in a workflow. Provide the full list of 'step_uuid's in the desired new order. Make sure to check the system prompts afterwards to see if the output references (<<trigger_output>> or <<step_output.[step uuid]>>) are correct.
    """
    context = get_context_from_headers()
    ordered_uuids = [UUID(uuid) for uuid in ordered_step_uuids]
    workflow = await workflow_client.reorder_steps(
        workflow_uuid=context.workflow_uuid,
        ordered_step_uuids=ordered_uuids,
        user_id=context.user_id,
    )
    return workflow.model_dump()


@mcp_builder.tool()
async def update_system_prompt_for_step(
    step_uuid: str,
    system_prompt: str,
) -> dict:
    """
    Updates the system prompt for a specific workflow step. This works for steps of type 'custom_llm' or 'custom_agent'. Use <<trigger_output>> or <<step_output.[step uuid]>> to reference the trigger output or the output of a previous step.
    """
    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow = await workflow_client.get_with_details(context.workflow_uuid, user_uuid)
    if not workflow:
        raise ValueError("Workflow not found")

    step_to_update = next((s for s in workflow.steps if str(s.uuid) == step_uuid), None)
    if not step_to_update:
        raise ValueError("Step not found in workflow")

    if not hasattr(step_to_update, "system_prompt"):
        raise TypeError(
            f"Step of type {step_to_update.type} does not have a system_prompt attribute."
        )

    step_to_update.system_prompt = system_prompt
    updated_step = await workflow_client.update_step(step_to_update, user_uuid)
    return updated_step.model_dump()


@mcp_builder.tool()
async def list_available_mcp_tools() -> List[dict]:
    """
    Returns a list of all available tools from all connected MCP servers that can be enabled for an agent step.
    """
    return await workflow_client.discover_mcp_tools()


@mcp_builder.tool()
async def update_step_mcp_tools(
    step_uuid: str,
    enabled_tools: List[str],
) -> dict:
    """
    Updates the set of enabled tools for a specific agent step. This only works for steps of type 'custom_agent'. Provide the full list of tool names that should be enabled. Returns the updated step model.
    """
    context = get_context_from_headers()
    user_uuid = context.user_id
    workflow = await workflow_client.get_with_details(context.workflow_uuid, user_uuid)
    if not workflow:
        raise ValueError("Workflow not found")

    step_to_update = next((s for s in workflow.steps if str(s.uuid) == step_uuid), None)
    if not step_to_update:
        raise ValueError("Step not found in workflow")

    if step_to_update.type != "custom_agent":
        raise TypeError(
            "MCP tools can only be updated for steps of type 'custom_agent'."
        )

    # The tools attribute is a dictionary where keys are tool names (e.g., 'imap-mcp-server-send_email')
    # and values are dictionaries indicating if the tool is enabled.
    new_tools_dict = {}
    for tool_name in enabled_tools:
        new_tools_dict[tool_name] = {"enabled": True}

    step_to_update.tools = new_tools_dict
    updated_step = await workflow_client.update_step(step_to_update, user_uuid)
    return updated_step.model_dump() 