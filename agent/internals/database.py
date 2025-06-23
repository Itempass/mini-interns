# This file is for internal use only and should not be used directly by the end-user. 
import aiosqlite
import json
from uuid import UUID
from datetime import datetime
from typing import List
from agent.models import AgentModel, AgentInstanceModel, MessageModel, TriggerModel

DB_PATH = "data/db/agent.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        with open("agent/schema.sql", "r") as f:
            await db.executescript(f.read())
        await db.commit()

async def _create_agent_in_db(agent: AgentModel) -> AgentModel:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO agents (uuid, name, description, system_prompt, user_instructions, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(agent.uuid),
                agent.name,
                agent.description,
                agent.system_prompt,
                agent.user_instructions,
                agent.created_at,
                agent.updated_at,
            ),
        )
        await db.commit()
    return agent

async def _get_agent_from_db(uuid: UUID) -> AgentModel | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM agents WHERE uuid = ?", (str(uuid),))
        row = await cursor.fetchone()
        return AgentModel(**dict(row)) if row else None

async def _list_agents_from_db() -> List[AgentModel]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM agents ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [AgentModel(**dict(row)) for row in rows]

async def _update_agent_in_db(agent: AgentModel) -> AgentModel:
    agent.updated_at = datetime.utcnow()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE agents
            SET name = ?, description = ?, system_prompt = ?, user_instructions = ?, updated_at = ?
            WHERE uuid = ?
            """,
            (
                agent.name,
                agent.description,
                agent.system_prompt,
                agent.user_instructions,
                agent.updated_at,
                str(agent.uuid),
            ),
        )
        await db.commit()
    return agent

async def _create_instance_in_db(instance: AgentInstanceModel) -> AgentInstanceModel:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO agent_instances (uuid, agent_uuid, user_input, messages, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(instance.uuid),
                str(instance.agent_uuid),
                instance.user_input,
                json.dumps([msg.model_dump() for msg in instance.messages]),
                instance.created_at,
                instance.updated_at,
            ),
        )
        await db.commit()
    return instance

async def _get_instance_from_db(uuid: UUID) -> AgentInstanceModel | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM agent_instances WHERE uuid = ?", (str(uuid),))
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["messages"] = [MessageModel(**msg) for msg in json.loads(data["messages"])]
        return AgentInstanceModel(**data)

async def _update_instance_in_db(instance: AgentInstanceModel) -> AgentInstanceModel:
    instance.updated_at = datetime.utcnow()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE agent_instances
            SET messages = ?, updated_at = ?
            WHERE uuid = ?
            """,
            (
                json.dumps([msg.model_dump(exclude_none=True) for msg in instance.messages]),
                instance.updated_at,
                str(instance.uuid),
            ),
        )
        await db.commit()
    return instance

async def _create_trigger_in_db(trigger: TriggerModel) -> TriggerModel:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO triggers (uuid, agent_uuid, function_name, rules_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(trigger.uuid),
                str(trigger.agent_uuid),
                trigger.function_name,
                json.dumps(trigger.rules_json),
                trigger.created_at,
                trigger.updated_at,
            ),
        )
        await db.commit()
    return trigger

async def _get_trigger_from_db(uuid: UUID) -> TriggerModel | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM triggers WHERE uuid = ?", (str(uuid),))
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["rules_json"] = json.loads(data["rules_json"])
        return TriggerModel(**data)

async def _update_trigger_in_db(trigger: TriggerModel) -> TriggerModel:
    trigger.updated_at = datetime.utcnow()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE triggers
            SET function_name = ?, rules_json = ?, updated_at = ?
            WHERE uuid = ?
            """,
            (
                trigger.function_name,
                json.dumps(trigger.rules_json),
                trigger.updated_at,
                str(trigger.uuid),
            ),
        )
        await db.commit()
    return trigger 