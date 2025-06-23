from __future__ import annotations
from typing import List
from uuid import UUID
from agent.models import Agent as AgentModel, AgentInstance as AgentInstanceModel
from agent.internals.database import (
    _create_agent_in_db,
    _get_agent_from_db,
    _update_agent_in_db,
    _create_instance_in_db,
    _update_instance_in_db
)
from agent.internals.runner import _execute_run
from shared.config import settings
from shared.app_settings import AppSettings

class AgentInstance:
    """
    Represents a single, stateful run of an Agent.
    Is responsible for its own execution and persistence.
    Allows direct access to instance properties (e.g., instance.messages).
    """
    def __init__(self, agent: Agent, model: AgentInstanceModel):
        self.agent = agent
        self.model = model

    def __getattr__(self, name: str):
        """Proxies attribute getting to the underlying Pydantic model."""
        return getattr(self.model, name)

    def __setattr__(self, name: str, value):
        """Proxies attribute setting to the underlying Pydantic model."""
        if name in ['agent', 'model']:
            super().__setattr__(name, value)
        else:
            setattr(self.model, name, value)

    async def run(self) -> AgentInstance:
        """
        Runs the agentic loop for this instance.
        """
        # NOTE: The runner will now load the API key itself.
        completed_model = await _execute_run(self.agent.model, self.model)
        self.model = completed_model
        await _update_instance_in_db(self.model)
        return self

class Agent:
    """
    The main class for interacting with a persistent, runnable Agent blueprint.
    Allows direct modification of agent properties (e.g., agent.name = "New Name").
    Changes must be persisted by calling agent.save().
    """
    
    def __init__(self, agent_model: AgentModel):
        self.model = agent_model

    def __getattr__(self, name: str):
        """Proxies attribute getting to the underlying Pydantic model."""
        return getattr(self.model, name)

    def __setattr__(self, name: str, value):
        """Proxies attribute setting to the underlying Pydantic model."""
        if name == 'model':
            super().__setattr__(name, value)
        else:
            setattr(self.model, name, value)

    @classmethod
    async def create(
        cls,
        name: str,
        description: str,
        system_prompt: str,
        user_instructions: str,
    ) -> Agent:
        """
        Creates a new Agent, persists it to the database, and returns a runnable Agent instance.
        """
        agent_model = AgentModel(
            name=name,
            description=description,
            system_prompt=system_prompt,
            user_instructions=user_instructions
        )
        await _create_agent_in_db(agent_model)
        return cls(agent_model)

    @classmethod
    async def get(cls, uuid: UUID) -> Agent | None:
        """
        Retrieves an existing Agent from the database.
        """
        agent_model = await _get_agent_from_db(uuid)
        return cls(agent_model) if agent_model else None

    async def save(self) -> None:
        """
        Saves the current state of the Agent to the database.
        """
        await _update_agent_in_db(self.model)

    async def create_instance(self, user_input: str) -> AgentInstance:
        """
        Creates a new, persistent instance of this agent for a specific run.
        """
        instance_model = AgentInstanceModel(agent_uuid=self.model.uuid, user_input=user_input)
        await _create_instance_in_db(instance_model)
        return AgentInstance(self, instance_model) 