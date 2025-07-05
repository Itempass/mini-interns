# This file is for internal use only and should not be used directly by the end-user. 
import aiosqlite
import json
from uuid import UUID
from datetime import datetime
from typing import List
from agent.models import AgentModel, AgentInstanceModel, MessageModel, TriggerModel

DB_PATH = "/data/db/agent.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        with open("agent/schema.sql", "r") as f:
            await db.executescript(f.read())
        await db.commit()

async def _create_agent_in_db(agent: AgentModel) -> AgentModel:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO agents (uuid, name, description, system_prompt, user_instructions, tools, paused, model, param_schema, param_values, use_abstracted_editor, template_id, template_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(agent.uuid),
                agent.name,
                agent.description,
                agent.system_prompt,
                agent.user_instructions,
                json.dumps(agent.tools),
                agent.paused,
                agent.model,
                json.dumps(agent.param_schema),
                json.dumps(agent.param_values),
                agent.use_abstracted_editor,
                agent.template_id,
                agent.template_version,
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
        if not row:
            return None
        
        data = dict(row)
        if data.get("tools"):
            data["tools"] = json.loads(data["tools"])
        else:
            data["tools"] = {}

        if data.get("param_schema"):
            data["param_schema"] = json.loads(data["param_schema"])
        else:
            data["param_schema"] = []

        if data.get("param_values"):
            data["param_values"] = json.loads(data["param_values"])
        else:
            data["param_values"] = {}
            
        return AgentModel(**data)

async def _list_agents_from_db() -> List[AgentModel]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM agents ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        
        agents = []
        for row in rows:
            data = dict(row)
            if data.get("tools"):
                data["tools"] = json.loads(data["tools"])
            else:
                data["tools"] = {}
            
            if data.get("param_schema"):
                data["param_schema"] = json.loads(data["param_schema"])
            else:
                data["param_schema"] = []

            if data.get("param_values"):
                data["param_values"] = json.loads(data["param_values"])
            else:
                data["param_values"] = {}

            agents.append(AgentModel(**data))
        return agents

async def _update_agent_in_db(agent: AgentModel) -> AgentModel:
    agent.updated_at = datetime.utcnow()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE agents
            SET name = ?, description = ?, system_prompt = ?, user_instructions = ?, tools = ?, paused = ?, model = ?, param_schema = ?, param_values = ?, use_abstracted_editor = ?, template_id = ?, template_version = ?, updated_at = ?
            WHERE uuid = ?
            """,
            (
                agent.name,
                agent.description,
                agent.system_prompt,
                agent.user_instructions,
                json.dumps(agent.tools),
                agent.paused,
                agent.model,
                json.dumps(agent.param_schema),
                json.dumps(agent.param_values),
                agent.use_abstracted_editor,
                agent.template_id,
                agent.template_version,
                agent.updated_at,
                str(agent.uuid),
            ),
        )
        await db.commit()
    return agent

async def _delete_agent_from_db(uuid: UUID):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM agents WHERE uuid = ?", (str(uuid),))
        await db.commit()

async def _create_instance_in_db(instance: AgentInstanceModel) -> AgentInstanceModel:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO agent_instances (uuid, agent_uuid, user_input, context_identifier, messages, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(instance.uuid),
                str(instance.agent_uuid),
                instance.user_input,
                instance.context_identifier,
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

# --- Trigger Functions ---

async def _create_trigger_in_db(trigger: TriggerModel) -> TriggerModel:
    async with aiosqlite.connect(DB_PATH) as db:
        rules_payload = {
            "trigger_conditions": trigger.trigger_conditions,
            "filter_rules": trigger.filter_rules
        }
        await db.execute(
            """
            INSERT INTO triggers (uuid, agent_uuid, rules_json, trigger_bypass, model, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(trigger.uuid),
                str(trigger.agent_uuid),
                json.dumps(rules_payload),
                trigger.trigger_bypass,
                trigger.model,
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
        rules_payload = json.loads(data["rules_json"])
        data["trigger_conditions"] = rules_payload.get("trigger_conditions", "")
        data["filter_rules"] = rules_payload.get("filter_rules", {})

        return TriggerModel(**data)

async def _get_trigger_for_agent_from_db(agent_uuid: UUID) -> TriggerModel | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM triggers WHERE agent_uuid = ?", (str(agent_uuid),))
        row = await cursor.fetchone()
        if not row:
            return None
        
        data = dict(row)
        rules_payload = json.loads(data["rules_json"])
        data["trigger_conditions"] = rules_payload.get("trigger_conditions", "")
        data["filter_rules"] = rules_payload.get("filter_rules", {})

        return TriggerModel(**data)

async def _list_triggers_from_db() -> List[TriggerModel]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM triggers ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        
        triggers = []
        for row in rows:
            data = dict(row)
            rules_payload = json.loads(data["rules_json"])
            data["trigger_conditions"] = rules_payload.get("trigger_conditions", "")
            data["filter_rules"] = rules_payload.get("filter_rules", {})
            triggers.append(TriggerModel(**data))
        return triggers

async def _update_trigger_in_db(trigger: TriggerModel) -> TriggerModel:
    trigger.updated_at = datetime.utcnow()
    async with aiosqlite.connect(DB_PATH) as db:
        rules_payload = {
            "trigger_conditions": trigger.trigger_conditions,
            "filter_rules": trigger.filter_rules
        }
        await db.execute(
            """
            UPDATE triggers
            SET agent_uuid = ?, rules_json = ?, trigger_bypass = ?, model = ?, updated_at = ?
            WHERE uuid = ?
            """,
            (
                str(trigger.agent_uuid),
                json.dumps(rules_payload),
                trigger.trigger_bypass,
                trigger.model,
                trigger.updated_at,
                str(trigger.uuid),
            ),
        )
        await db.commit()
    return trigger

async def _delete_trigger_from_db(uuid: UUID):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM triggers WHERE uuid = ?", (str(uuid),))
        await db.commit()
