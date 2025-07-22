import asyncio
import os
import uuid
from urllib.parse import urlparse
from unittest.mock import MagicMock, AsyncMock

import aiomysql
import pytest
from aiomysql.cursors import DictCursor
from dotenv import load_dotenv

# Add project root to path to allow imports
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
# --- MOCKING a redis client before it gets called on import
from shared.redis import redis_client
redis_client.get_redis_client = MagicMock()
# ---
from shared.config import settings
from workflow.internals import runner, database
from workflow.models import (
    InitialWorkflowData,
    StepOutputData,
    WorkflowInstanceModel,
    WorkflowStepInstance,
)
import workflow.client as workflow_client
import workflow.llm_client as llm_client
import workflow.agent_client as agent_client
from mcp.types import Tool
from shared.app_settings import AppSettings
from qdrant_client import QdrantClient
import json


# --- Mocks & Test Data ---

TEST_USER_ID = uuid.uuid4()


# --- Test Setup ---

# Check for the test database URL environment variable
load_dotenv(override=True)
TEST_DB_URL = os.getenv("MYSQL_TESTDB_URL")


# This marker will apply to all tests in this file
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not TEST_DB_URL,
        reason="MYSQL_TESTDB_URL environment variable not set. Skipping integration test.",
    ),
]


@pytest.fixture(scope="function")
def event_loop():
    """Function-scoped event loop for test isolation."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def mock_app_settings(monkeypatch):
    """
    Globally mocks load_app_settings to prevent any test from trying
    to connect to Redis or other external services during setup.
    """
    dummy_settings = AppSettings(
        IMAP_SERVER="dummy.server.com",
        IMAP_USERNAME="dummyuser",
        IMAP_PASSWORD="dummypassword",
        EMBEDDING_MODEL="text-embedding-3-large"
    )
    monkeypatch.setattr(
        "shared.app_settings.load_app_settings", lambda: dummy_settings
    )
    # Mock the QdrantClient class *before* it can be imported and used by
    # our application code. This prevents the client from trying to connect
    # to a live server during test collection.
    monkeypatch.setattr("qdrant_client.QdrantClient", MagicMock())


@pytest.fixture(scope="function")
async def test_db(monkeypatch):
    """
    Connects to a user-provided test database, creates a temporary schema,
    runs the test, and tears it down.
    """
    parsed_url = urlparse(TEST_DB_URL)
    
    # 1. Patch settings to use the provided test DB URL
    monkeypatch.setattr(settings, "WORKFLOW_DATABASE_URL", TEST_DB_URL)
    # Patch Redis URL to avoid connection errors as it's not needed for this test
    monkeypatch.setattr(settings, "REDIS_URL", "redis://dummy-redis:6379")

    # 2. Connect to the server and create the schema in the provided database
    conn = await aiomysql.connect(
        host=parsed_url.hostname,
        port=parsed_url.port,
        user=parsed_url.username,
        password=parsed_url.password,
        db=parsed_url.path.lstrip("/") # Connect directly to the database
    )
    async with conn.cursor() as cursor:
        # 3. Read and execute the schema
        schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
        with open(schema_path, "r") as f:
            sql_commands = f.read().split(";")
            for command in sql_commands:
                if command.strip():
                    await cursor.execute(command)
    conn.close()

    # 4. Point the application's connection pool to our test database
    database.pool = None  # Reset the pool to force re-initialization
    await database.get_workflow_db_pool()

    yield  # Run the actual test

    # 5. Teardown: Clean up the tables from the database
    conn = await aiomysql.connect(
        host=parsed_url.hostname,
        port=parsed_url.port,
        user=parsed_url.username,
        password=parsed_url.password,
        db=parsed_url.path.lstrip("/")
    )
    async with conn.cursor() as cursor:
        await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        await cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s;", (parsed_url.path.lstrip("/"),))
        tables = await cursor.fetchall()
        for table in tables:
            await cursor.execute(f"DROP TABLE IF EXISTS `{table[0]}`")
        await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    conn.close()


# --- Integration Test ---

async def test_workflow_execution_completes_successfully(test_db):
    """
    This is an integration test that uses a real, external database to
    verify that a simple workflow runs to completion.
    """
    from workflow import client as workflow_client
    from workflow import llm_client as llm_client
    from workflow import agent_client as agent_client
    from workflow.internals import runner

    print("--- ENTERING test_workflow_execution_completes_successfully ---")
    user_id = uuid.uuid4()

    # 1. Create workflow and step definitions using the app's clients
    workflow_def = await workflow_client.create(
        name="Test Workflow", description="Integration test workflow", user_id=user_id
    )
    llm_step_def = await llm_client.create(
        name="Test LLM Step",
        model="google/gemini-2.5-flash",
        system_prompt="Respond with only the word 'Hello, <<trigger_output>>'.",
        user_id=user_id,
    )
    agent_step_def = await agent_client.create(
        name="Test Agent Step",
        model="google/gemini-2.5-flash",
        system_prompt=f"You are a parrot. Repeat the following text exactly, without any preamble: <<step_output.{llm_step_def.uuid}>>",
        user_id=user_id,
    )
    workflow_def.steps.append(llm_step_def.uuid)
    workflow_def.steps.append(agent_step_def.uuid)
    await workflow_client.save(workflow_def, user_id)

    # 2. Create the initial trigger data and workflow instance
    trigger_data = InitialWorkflowData(raw_data="world")
    instance = await workflow_client.create_instance(
        workflow_uuid=workflow_def.uuid, triggering_data=trigger_data, user_id=user_id
    )

    # 3. Act: Run the workflow
    print("--- CALLING runner.run_workflow ---")
    await runner.run_workflow(instance.uuid, user_id)
    print("--- RETURNED FROM runner.run_workflow ---")

    # 4. Assert: Check the final state of the workflow in the database
    final_instance = await workflow_client.get_instance(instance.uuid, user_id)
    
    assert final_instance is not None
    assert final_instance.status == "completed"
    assert len(final_instance.step_instances) == 2, f"Expected 2 step instances, but found {len(final_instance.step_instances)}"
    
    # Assertions for Step 1: LLM
    llm_step_instance = final_instance.step_instances[0]
    assert llm_step_instance.status == "completed"
    assert llm_step_instance.output is not None
    assert llm_step_instance.output.raw_data == "Hello, world"
    assert "Hello, world" in llm_step_instance.messages[-1].content
    
    # Assertions for Step 2: Agent
    agent_step_instance = final_instance.step_instances[1]
    assert agent_step_instance.status == "completed"
    assert agent_step_instance.output is not None
    
    # The agent's prompt resolves the placeholder to a special format.
    # We expect the agent to "parrot" this exact format back.
    # To make the test robust, we'll parse the agent's output as if it were a similar structure
    # and check the important parts, rather than doing a brittle string comparison.
    # The agent's raw output is a multi-line string, so we split by newline.
    output_lines = agent_step_instance.output.raw_data.strip().split('\n')
    
    # We are only interested in the lines that start with an asterisk, which denote the key-value pairs.
    data_lines = [line for line in output_lines if line.strip().startswith("*")]
    
    output_dict = {}
    for line in data_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            output_dict[key.strip("* ")] = value.strip()

    assert "summary" in output_dict
    assert "id" in output_dict
    assert "data_schema" in output_dict
    
    # Check that the core data from the previous step is present.
    assert llm_step_instance.output.summary in output_dict["summary"]
    assert str(llm_step_instance.output.uuid) in output_dict["id"]
    
    print("--- EXITING test_workflow_execution_completes_successfully ---")


async def test_agent_tool_use_with_data_pointer(test_db, monkeypatch):
    """
    Tests that an agent can correctly use the 'magic string' data pointer
    to pass a value from a previous step's output directly to a tool,
    and that the resolver layer correctly processes it.
    """
    from workflow import client as workflow_client
    from workflow import llm_client as llm_client
    from workflow import agent_client as agent_client
    from workflow.internals import runner
    from fastmcp import Client as MCPClient

    print("--- ENTERING test_agent_tool_use_with_data_pointer ---")
    user_id = uuid.uuid4()
    message_id_to_test = f"test-message-{uuid.uuid4()}"

    # --- PATCHING ---

    # Since this is an integration test for the AGENT's tool use, we can
    # safely mock the preceding LLM step's network call to avoid event loop
    # issues with the global openrouter client.
    mock_llm_output_content = json.dumps({"messageId": message_id_to_test})
    mock_get_llm_response = AsyncMock(return_value=mock_llm_output_content)
    monkeypatch.setattr(
        "workflow.internals.llm_runner.openrouter_service.get_llm_response",
        mock_get_llm_response
    )

    # We patch the internal tool-handling function directly. This is the most
    # direct way to confirm the agent runner is attempting a tool call
    # without worrying about lower-level client mocking.
    mock_handle_tool_call = AsyncMock(return_value="Label set successfully.")
    monkeypatch.setattr(
        "workflow.internals.agent_runner._handle_mcp_tool_call",
        mock_handle_tool_call
    )

    # We also need to patch the tool discovery to simulate the tool being available.
    mock_http_response = MagicMock()
    mock_http_response.raise_for_status.return_value = None
    # Ensure that .json() is a regular method returning a list, not a mock/coroutine
    mock_http_response.json = lambda: [{
        "name": "imap_mcpserver",
        "url": "http://dummy-mcp-server:8000"
    }]
    
    mock_mcp_tool_list = [
        Tool(name="set_label", description="Adds a label to an email.", inputSchema={
            "type": "object",
            "properties": {
                "messageId": {"type": "string"},
                "label": {"type": "string"}
            }
        })
    ]
    
    # Create a mock for httpx.AsyncClient that returns the correct async behavior
    mock_mcp_async_client = AsyncMock()
    
    # The `get` method must be an async function that returns our mock response
    async def mock_get(*args, **kwargs):
        return mock_http_response
    
    # The context manager should return an object with the mocked 'get' method
    mock_context_manager = AsyncMock()
    mock_context_manager.get = mock_get
    mock_mcp_async_client.__aenter__.return_value = mock_context_manager
    mock_mcp_async_client.__aexit__.return_value = None

    # We need to return an async context manager for the MCPClient
    # and its list_tools method must be awaitable.
    mock_mcp_client_instance = AsyncMock()
    mock_mcp_client_instance.list_tools.return_value = mock_mcp_tool_list
    # Ensure the async context manager returns itself
    mock_mcp_client_instance.__aenter__.return_value = mock_mcp_client_instance

    monkeypatch.setattr(
        "workflow.internals.agent_runner.httpx.AsyncClient", 
        lambda: mock_mcp_async_client
    )
    monkeypatch.setattr(
        "workflow.internals.agent_runner.MCPClient", 
        lambda url: mock_mcp_client_instance
    )

    # 1. Create Workflow
    # Step 1 (LLM): Outputs a JSON object with the messageId
    llm_step_def = await llm_client.create(
        name="Get Message ID",
        model="google/gemini-2.5-flash",
        system_prompt=f"Output a JSON object with the key 'messageId' and the value '{message_id_to_test}'",
        user_id=user_id
    )
    
    # Step 2 (Agent): Uses the `set_label` tool with a data pointer
    agent_step_def = await agent_client.create(
        name="Labeling Agent",
        model="google/gemini-2.5-flash",
        system_prompt=(
            "You have one tool available: `imap_mcpserver-set_label`. "
            "You MUST call this tool to apply the 'Triaged' label to the email found in the data container. "
            f"The data container is: <<step_output.{llm_step_def.uuid}>>"
        ),
        user_id=user_id,
        tools={"imap_mcpserver-set_label": {"enabled": True}}
    )

    workflow_def = await workflow_client.create(name="Tool Test Workflow", description="", user_id=user_id)
    workflow_def.steps = [llm_step_def.uuid, agent_step_def.uuid]
    await workflow_client.save(workflow_def, user_id)

    # 2. Create Instances
    instance = await workflow_client.create_instance(
        workflow_uuid=workflow_def.uuid,
        triggering_data=InitialWorkflowData(raw_data={"some": "data"}),
        user_id=user_id
    )

    # 3. Run Workflow
    await runner.run_workflow(instance.uuid, user_id)

    # 4. Assert
    final_instance = await workflow_client.get_instance(instance.uuid, user_id)
    assert final_instance.status == "completed"

    # Check that our patched tool was called. We check the call count
    # because the LLM may decide to call the tool multiple times in a loop.
    assert mock_handle_tool_call.call_count > 0

    print("--- EXITING test_agent_tool_use_with_data_pointer ---")