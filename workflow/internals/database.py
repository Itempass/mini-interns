import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import urlparse
from uuid import UUID

import aiomysql
from aiomysql.cursors import DictCursor

from shared.config import settings
from workflow.models import (
    CustomAgent,
    CustomAgentInstanceModel,
    CustomLLM,
    CustomLLMInstanceModel,
    MessageModel,
    StepOutputData,
    StopWorkflowChecker,
    StopWorkflowCheckerInstanceModel,
    TriggerModel,
    WorkflowInstanceModel,
    WorkflowModel,
    WorkflowStep,
    WorkflowStepInstance,
)

logger = logging.getLogger(__name__)

# Global connection pool
pool = None


async def get_workflow_db_pool():
    """Singleton to create and return a database connection pool."""
    global pool
    if pool is None:
        try:
            # Use the built-in urllib.parse to deconstruct the database URL
            url = urlparse(str(settings.WORKFLOW_DATABASE_URL))
            pool = await aiomysql.create_pool(
                host=url.hostname,
                port=url.port or 3306,
                user=url.username,
                password=url.password,
                db=url.path.lstrip("/"),
                autocommit=False,  # Important for transaction management
            )
            logger.info("Successfully created database connection pool for workflows.")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise
    return pool


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[aiomysql.Connection, None]:
    """Provides a connection from the pool, ensuring it's closed and released."""
    db_pool = await get_workflow_db_pool()
    conn = await db_pool.acquire()
    try:
        yield conn
    finally:
        db_pool.release(conn)


async def _create_workflow_in_db(workflow: WorkflowModel, user_id: UUID) -> WorkflowModel:
    """Creates a new workflow record in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            try:
                await cursor.execute(
                    """
                    INSERT INTO workflows (uuid, user_id, name, description, is_active, trigger_uuid, steps, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        workflow.uuid.bytes,
                        user_id.bytes,
                        workflow.name,
                        workflow.description,
                        workflow.is_active,
                        workflow.trigger_uuid.bytes if workflow.trigger_uuid else None,
                        json.dumps([step_uuid.hex for step_uuid in workflow.steps]),
                        workflow.created_at,
                        workflow.updated_at,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully created workflow {workflow.uuid} in the database.")
                return workflow
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to create workflow {workflow.uuid}: {e}")
                raise 

async def _get_workflow_from_db(uuid: UUID, user_id: UUID) -> WorkflowModel | None:
    """Retrieves a single workflow from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT uuid, name, description, is_active, trigger_uuid, steps, created_at, updated_at FROM workflows WHERE uuid = %s AND user_id = %s",
                (uuid.bytes, user_id.bytes),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            # Deserialize JSON fields
            if row.get("steps"):
                row["steps"] = [UUID(step_uuid) for step_uuid in json.loads(row["steps"])]
            else:
                row["steps"] = []
            
            # Convert binary UUIDs back to UUID objects
            row["uuid"] = UUID(bytes=row["uuid"])
            if row.get("trigger_uuid"):
                row["trigger_uuid"] = UUID(bytes=row["trigger_uuid"])

            # Add user_id to the row dict before model instantiation
            row["user_id"] = user_id
            return WorkflowModel(**row)


async def _list_workflows_from_db(user_id: UUID) -> list[WorkflowModel]:
    """Retrieves all workflows for a user from the database."""
    workflows = []
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT uuid, name, description, is_active, trigger_uuid, steps, created_at, updated_at FROM workflows WHERE user_id = %s ORDER BY updated_at DESC",
                (user_id.bytes,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                # Deserialize JSON fields
                if row.get("steps"):
                    row["steps"] = [UUID(step_uuid) for step_uuid in json.loads(row["steps"])]
                else:
                    row["steps"] = []

                # Convert binary UUIDs back to UUID objects
                row["uuid"] = UUID(bytes=row["uuid"])
                if row.get("trigger_uuid"):
                    row["trigger_uuid"] = UUID(bytes=row["trigger_uuid"])

                # Add user_id to the row dict before model instantiation
                row["user_id"] = user_id
                workflows.append(WorkflowModel(**row))
    return workflows


async def _update_workflow_in_db(workflow: WorkflowModel, user_id: UUID) -> WorkflowModel:
    """Updates an existing workflow in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            try:
                await cursor.execute(
                    """
                    UPDATE workflows
                    SET name = %s, description = %s, is_active = %s, trigger_uuid = %s, steps = %s, updated_at = %s
                    WHERE uuid = %s AND user_id = %s
                    """,
                    (
                        workflow.name,
                        workflow.description,
                        workflow.is_active,
                        workflow.trigger_uuid.bytes if workflow.trigger_uuid else None,
                        json.dumps([step_uuid.hex for step_uuid in workflow.steps]),
                        workflow.updated_at,
                        workflow.uuid.bytes,
                        user_id.bytes,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully updated workflow {workflow.uuid} in the database.")
                return workflow
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to update workflow {workflow.uuid}: {e}")
                raise


async def _delete_workflow_in_db(uuid: UUID, user_id: UUID) -> None:
    """Deletes a workflow from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute(
                    "DELETE FROM workflows WHERE uuid = %s AND user_id = %s",
                    (uuid.bytes, user_id.bytes),
                )
                await conn.commit()
                logger.info(f"Successfully deleted workflow {uuid} from the database.")
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to delete workflow {uuid}: {e}")
                raise


#
# Workflow Step CRUD
#

async def _create_step_in_db(step: WorkflowStep, user_id: UUID) -> WorkflowStep:
    """Creates a new workflow step record in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            # The 'details' field will store the full Pydantic model dict
            details_json = step.model_dump_json()
            try:
                await cursor.execute(
                    """
                    INSERT INTO workflow_steps (uuid, user_id, name, type, details)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        step.uuid.bytes,
                        user_id.bytes,
                        step.name,
                        step.type,
                        details_json,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully created workflow step {step.uuid} in the database.")
                return step
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to create workflow step {step.uuid}: {e}")
                raise


def _instantiate_step_from_row(row: dict, user_id: UUID) -> WorkflowStep | None:
    """Helper to instantiate the correct Pydantic model from a database row."""
    if not row:
        return None

    step_type = row.get("type")
    details_json = row.get("details")
    if not step_type or not details_json:
        logger.error(f"Missing type or details in step data: {row}")
        return None

    details = json.loads(details_json)
    details["user_id"] = user_id # Ensure user_id is present for validation

    if step_type == "custom_llm":
        return CustomLLM(**details)
    elif step_type == "custom_agent":
        return CustomAgent(**details)
    elif step_type == "stop_checker":
        return StopWorkflowChecker(**details)
    else:
        logger.warning(f"Unknown step type '{step_type}' encountered.")
        return None


async def _get_step_from_db(uuid: UUID, user_id: UUID) -> WorkflowStep | None:
    """Retrieves a single workflow step from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT type, details FROM workflow_steps WHERE uuid = %s AND user_id = %s",
                (uuid.bytes, user_id.bytes),
            )
            row = await cursor.fetchone()
            return _instantiate_step_from_row(row, user_id)


async def _update_step_in_db(step: WorkflowStep, user_id: UUID) -> WorkflowStep:
    """Updates an existing workflow step in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            details_json = step.model_dump_json()
            try:
                await cursor.execute(
                    """
                    UPDATE workflow_steps
                    SET name = %s, type = %s, details = %s, updated_at = NOW()
                    WHERE uuid = %s AND user_id = %s
                    """,
                    (
                        step.name,
                        step.type,
                        details_json,
                        step.uuid.bytes,
                        user_id.bytes,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully updated workflow step {step.uuid} in the database.")
                return step
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to update workflow step {step.uuid}: {e}")
                raise


async def _delete_step_in_db(uuid: UUID, user_id: UUID) -> None:
    """Deletes a workflow step from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute(
                    "DELETE FROM workflow_steps WHERE uuid = %s AND user_id = %s",
                    (uuid.bytes, user_id.bytes),
                )
                await conn.commit()
                logger.info(f"Successfully deleted workflow step {uuid} from the database.")
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to delete workflow step {uuid}: {e}")
                raise

#
# Trigger CRUD
#

async def _create_trigger_in_db(trigger: TriggerModel, user_id: UUID) -> TriggerModel:
    """Creates a new trigger record in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            # The 'details' field will store the filter rules and description
            details = {
                "filter_rules": trigger.filter_rules,
                "initial_data_description": trigger.initial_data_description,
            }
            details_json = json.dumps(details)
            try:
                await cursor.execute(
                    """
                    INSERT INTO triggers (uuid, user_id, workflow_uuid, details, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        trigger.uuid.bytes,
                        user_id.bytes,
                        trigger.workflow_uuid.bytes,
                        details_json,
                        trigger.created_at,
                        trigger.updated_at,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully created trigger {trigger.uuid} in the database.")
                return trigger
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to create trigger {trigger.uuid}: {e}")
                raise


async def _get_trigger_from_db(uuid: UUID, user_id: UUID) -> TriggerModel | None:
    """Retrieves a single trigger from the database by its UUID."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT uuid, workflow_uuid, details, created_at, updated_at FROM triggers WHERE uuid = %s AND user_id = %s",
                (uuid.bytes, user_id.bytes),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            details = json.loads(row["details"])
            return TriggerModel(
                uuid=UUID(bytes=row["uuid"]),
                user_id=user_id,
                workflow_uuid=UUID(bytes=row["workflow_uuid"]),
                filter_rules=details.get("filter_rules", {}),
                initial_data_description=details.get("initial_data_description", ""),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )


async def _list_triggers_from_db(user_id: UUID) -> list[TriggerModel]:
    """Retrieves all triggers for a user from the database."""
    triggers = []
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT uuid, workflow_uuid, details, created_at, updated_at FROM triggers WHERE user_id = %s ORDER BY updated_at DESC",
                (user_id.bytes,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                details = json.loads(row["details"])
                triggers.append(
                    TriggerModel(
                        uuid=UUID(bytes=row["uuid"]),
                        user_id=user_id,
                        workflow_uuid=UUID(bytes=row["workflow_uuid"]),
                        filter_rules=details.get("filter_rules", {}),
                        initial_data_description=details.get(
                            "initial_data_description", ""
                        ),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                )
    return triggers


async def _get_trigger_for_workflow_from_db(
    workflow_uuid: UUID, user_id: UUID
) -> TriggerModel | None:
    """Retrieves the trigger for a specific workflow from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT uuid, workflow_uuid, details, created_at, updated_at FROM triggers WHERE workflow_uuid = %s AND user_id = %s",
                (workflow_uuid.bytes, user_id.bytes),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            details = json.loads(row["details"])
            return TriggerModel(
                uuid=UUID(bytes=row["uuid"]),
                user_id=user_id,
                workflow_uuid=UUID(bytes=row["workflow_uuid"]),
                filter_rules=details.get("filter_rules", {}),
                initial_data_description=details.get("initial_data_description", ""),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

async def _update_trigger_in_db(trigger: TriggerModel, user_id: UUID) -> TriggerModel:
    """Updates an existing trigger in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            details = {
                "filter_rules": trigger.filter_rules,
                "initial_data_description": trigger.initial_data_description,
            }
            details_json = json.dumps(details)
            try:
                await cursor.execute(
                    """
                    UPDATE triggers
                    SET details = %s, updated_at = NOW()
                    WHERE uuid = %s AND user_id = %s
                    """,
                    (
                        details_json,
                        trigger.uuid.bytes,
                        user_id.bytes,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully updated trigger {trigger.uuid} in the database.")
                return trigger
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to update trigger {trigger.uuid}: {e}")
                raise

async def _delete_trigger_in_db(uuid: UUID, user_id: UUID) -> None:
    """Deletes a trigger from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute(
                    "DELETE FROM triggers WHERE uuid = %s AND user_id = %s",
                    (uuid.bytes, user_id.bytes),
                )
                await conn.commit()
                logger.info(f"Successfully deleted trigger {uuid} from the database.")
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to delete trigger {uuid}: {e}")
                raise

#
# Instance CRUD
#

async def _create_workflow_instance_in_db(instance: WorkflowInstanceModel, user_id: UUID) -> WorkflowInstanceModel:
    """Creates a new workflow instance record in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            trigger_output_json = instance.trigger_output.model_dump_json() if instance.trigger_output else None
            try:
                await cursor.execute(
                    """
                    INSERT INTO workflow_instances (uuid, user_id, workflow_definition_uuid, status, trigger_output, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        instance.uuid.bytes,
                        user_id.bytes,
                        instance.workflow_definition_uuid.bytes,
                        instance.status,
                        trigger_output_json,
                        instance.created_at,
                        instance.updated_at,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully created workflow instance {instance.uuid} in the database.")
                return instance
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to create workflow instance {instance.uuid}: {e}")
                raise

async def _get_workflow_instance_from_db(
    uuid: UUID, user_id: UUID
) -> WorkflowInstanceModel | None:
    """Retrieves a single workflow instance from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                "SELECT uuid, workflow_definition_uuid, status, trigger_output, created_at, updated_at FROM workflow_instances WHERE uuid = %s AND user_id = %s",
                (uuid.bytes, user_id.bytes),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            # Add user_id before instantiation
            row["user_id"] = user_id

            # Deserialize JSON and binary fields
            row["uuid"] = UUID(bytes=row["uuid"])
            row["workflow_definition_uuid"] = UUID(
                bytes=row["workflow_definition_uuid"]
            )
            if row.get("trigger_output"):
                trigger_output_data = json.loads(row["trigger_output"])
                # Ensure UUID is an object
                trigger_output_data["uuid"] = UUID(trigger_output_data["uuid"])
                row["trigger_output"] = StepOutputData(**trigger_output_data)

            # We don't fetch step instances here for performance.
            # The runner or a detailed getter will do that.
            row["step_instances"] = []

            return WorkflowInstanceModel(**row)


async def _list_workflow_instances_from_db(
    workflow_uuid: UUID, user_id: UUID
) -> list[WorkflowInstanceModel]:
    """Retrieves all instances for a specific workflow from the database."""
    instances = []
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT uuid, workflow_definition_uuid, status, trigger_output, created_at, updated_at
                FROM workflow_instances
                WHERE workflow_definition_uuid = %s AND user_id = %s
                ORDER BY created_at DESC
                """,
                (workflow_uuid.bytes, user_id.bytes),
            )
            rows = await cursor.fetchall()
            for row in rows:
                # Add user_id before instantiation
                row["user_id"] = user_id

                # Deserialize JSON and binary fields
                row["uuid"] = UUID(bytes=row["uuid"])
                row["workflow_definition_uuid"] = UUID(
                    bytes=row["workflow_definition_uuid"]
                )
                if row.get("trigger_output"):
                    trigger_output_data = json.loads(row["trigger_output"])
                    # Ensure UUID is an object
                    trigger_output_data["uuid"] = UUID(trigger_output_data["uuid"])
                    row["trigger_output"] = StepOutputData(**trigger_output_data)

                # We don't fetch step instances here for performance.
                row["step_instances"] = []

                instances.append(WorkflowInstanceModel(**row))
    return instances


async def _update_workflow_instance_in_db(
    instance: WorkflowInstanceModel, user_id: UUID
) -> WorkflowInstanceModel:
    """Updates the status of an existing workflow instance in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            try:
                await cursor.execute(
                    """
                    UPDATE workflow_instances
                    SET status = %s, updated_at = NOW()
                    WHERE uuid = %s AND user_id = %s
                    """,
                    (
                        instance.status,
                        instance.uuid.bytes,
                        user_id.bytes,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully updated workflow instance {instance.uuid} to status {instance.status}.")
                return instance
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to update workflow instance {instance.uuid}: {e}")
                raise

async def _create_step_instance_in_db(instance: WorkflowStepInstance, user_id: UUID) -> WorkflowStepInstance:
    """Creates a new workflow step instance record in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            # Prepare data for insertion
            output_json = instance.output.model_dump_json() if hasattr(instance, "output") and instance.output else None
            output_id_bytes = instance.output.uuid.bytes if hasattr(instance, "output") and instance.output else None
            
            # Consolidate remaining fields into the 'details' JSON blob
            details = {
                "messages": [msg.model_dump() for msg in instance.messages] if hasattr(instance, "messages") else [],
                "input_data": instance.input_data if hasattr(instance, "input_data") else None,
                "error_message": instance.error_message if hasattr(instance, "error_message") else None,
            }
            details_json = json.dumps(details, default=str)
            
            # Get the correct definition UUID based on the instance type
            step_definition_uuid = getattr(instance, 'llm_definition_uuid', 
                                    getattr(instance, 'agent_definition_uuid', 
                                    getattr(instance, 'checker_definition_uuid')))

            try:
                await cursor.execute(
                    """
                    INSERT INTO workflow_step_instances 
                    (uuid, user_id, workflow_instance_uuid, step_definition_uuid, status, started_at, finished_at, output_id, output, details, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        instance.uuid.bytes,
                        user_id.bytes,
                        instance.workflow_instance_uuid.bytes,
                        step_definition_uuid.bytes,
                        instance.status,
                        instance.started_at,
                        instance.finished_at,
                        output_id_bytes,
                        output_json,
                        details_json,
                        instance.created_at,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully created step instance {instance.uuid} in the database.")
                return instance
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to create step instance {instance.uuid}: {e}")
                raise


def _instantiate_step_instance_from_row(row: dict, step_definition_type: str, user_id: UUID) -> WorkflowStepInstance | None:
    """Helper to instantiate the correct Pydantic model for a step instance from a database row."""
    if not row:
        return None

    details = json.loads(row.get("details", "{}"))
    output = StepOutputData(**json.loads(row["output"])) if row.get("output") else None

    # Common fields for all instance types
    base_fields = {
        "uuid": UUID(bytes=row["uuid"]),
        "user_id": user_id,
        "workflow_instance_uuid": UUID(bytes=row["workflow_instance_uuid"]),
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "created_at": row["created_at"],
        "input_data": details.get("input_data"),
        "error_message": details.get("error_message"),
        "messages": [MessageModel(**msg) for msg in details.get("messages", [])],
        "output": output,
    }

    if step_definition_type == "custom_llm":
        return CustomLLMInstanceModel(llm_definition_uuid=UUID(bytes=row["step_definition_uuid"]), **base_fields)
    elif step_definition_type == "custom_agent":
        return CustomAgentInstanceModel(agent_definition_uuid=UUID(bytes=row["step_definition_uuid"]), **base_fields)
    elif step_definition_type == "stop_checker":
        # Stop checker does not have output or messages
        base_fields.pop("output")
        base_fields.pop("messages")
        return StopWorkflowCheckerInstanceModel(checker_definition_uuid=UUID(bytes=row["step_definition_uuid"]), **base_fields)
    else:
        logger.warning(f"Unknown step definition type '{step_definition_type}' encountered.")
        return None


async def _get_step_instance_from_db(uuid: UUID, user_id: UUID) -> WorkflowStepInstance | None:
    """Retrieves a single workflow step instance from the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            # We need to join with workflow_steps to get the 'type' of the definition
            await cursor.execute(
                """
                SELECT si.*, sd.type as step_definition_type
                FROM workflow_step_instances si
                JOIN workflow_steps sd ON si.step_definition_uuid = sd.uuid
                WHERE si.uuid = %s AND si.user_id = %s
                """,
                (uuid.bytes, user_id.bytes),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return _instantiate_step_instance_from_row(row, row["step_definition_type"], user_id)


async def _list_step_instances_for_workflow_instance_from_db(workflow_instance_uuid: UUID, user_id: UUID) -> list[WorkflowStepInstance]:
    """Retrieves all step instances for a specific workflow instance from the database."""
    instances = []
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            # We need to join with workflow_steps to get the 'type' of the definition
            await cursor.execute(
                """
                SELECT si.*, sd.type as step_definition_type
                FROM workflow_step_instances si
                JOIN workflow_steps sd ON si.step_definition_uuid = sd.uuid
                WHERE si.workflow_instance_uuid = %s AND si.user_id = %s
                ORDER BY si.created_at ASC
                """,
                (workflow_instance_uuid.bytes, user_id.bytes),
            )
            rows = await cursor.fetchall()
            for row in rows:
                instance = _instantiate_step_instance_from_row(row, row["step_definition_type"], user_id)
                if instance:
                    instances.append(instance)
    return instances


async def _update_step_instance_in_db(instance: WorkflowStepInstance, user_id: UUID) -> WorkflowStepInstance:
    """Updates an existing workflow step instance in the database."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            # Prepare data for update
            output_json = instance.output.model_dump_json() if hasattr(instance, "output") and instance.output else None
            output_id_bytes = instance.output.uuid.bytes if hasattr(instance, "output") and instance.output else None
            
            details = {
                "messages": [msg.model_dump() for msg in instance.messages] if hasattr(instance, "messages") else [],
                "input_data": instance.input_data if hasattr(instance, "input_data") else None,
                "error_message": instance.error_message if hasattr(instance, "error_message") else None,
            }
            details_json = json.dumps(details, default=str)

            try:
                await cursor.execute(
                    """
                    UPDATE workflow_step_instances
                    SET status = %s, started_at = %s, finished_at = %s, output_id = %s, output = %s, details = %s, updated_at = NOW()
                    WHERE uuid = %s AND user_id = %s
                    """,
                    (
                        instance.status,
                        instance.started_at,
                        instance.finished_at,
                        output_id_bytes,
                        output_json,
                        details_json,
                        instance.uuid.bytes,
                        user_id.bytes,
                    ),
                )
                await conn.commit()
                logger.info(f"Successfully updated step instance {instance.uuid} in the database.")
                return instance
            except Exception as e:
                await conn.rollback()
                logger.error(f"Failed to update step instance {instance.uuid}: {e}")
                raise


async def _get_step_output_data_from_db(output_id: UUID, user_id: UUID) -> Optional[StepOutputData]:
    """Retries a step's output data object from the database using its unique ID."""
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            # The output is stored on the step instance, so we query that table.
            # We also index by output_id for efficient lookup.
            await cursor.execute(
                """
                SELECT output FROM workflow_step_instances
                WHERE output_id = %s AND user_id = %s
                """,
                (output_id.bytes, user_id.bytes),
            )
            row = await cursor.fetchone()
            if not row or not row.get("output"):
                return None
            
            # The 'output' column is a JSON blob, so we load it.
            output_data = json.loads(row["output"])
            return StepOutputData(**output_data)

