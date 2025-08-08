import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from functools import lru_cache
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys
from shared.qdrant.qdrant_client import count_points, get_qdrant_client, recreate_collection
from api.background_tasks.inbox_initializer import initialize_inbox
from api.background_tasks.determine_tone_of_voice import determine_user_tone_of_voice
from shared.config import settings
import json
from uuid import UUID
from typing import List
import asyncio
import os
from pathlib import Path

#from agent import client as agent_client
#from agent.models import AgentModel, TriggerModel
from workflow import agent_client

from user.models import User
from api.endpoints.auth import get_current_user


router = APIRouter()
logger = logging.getLogger(__name__)

AGENT_TEMPLATES_DIR = Path("api/agent_templates")

@lru_cache(maxsize=1)
def get_default_system_prompt():
    """
    Loads the default system prompt from a file.
    Caches the result to avoid repeated file I/O.
    """
    try:
        # Assuming the app runs from the project root
        with open("api/defaults/systemprompt_default.md", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("default system prompt file not found. Using a fallback default.")
        raise Exception("default system prompt file not found")

@lru_cache(maxsize=1)
def get_default_trigger_conditions():
    """
    Reads the default trigger conditions from the markdown file.
    """
    try:
        with open("api/defaults/triggerconditions_default.md", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("Default trigger conditions file not found.")
        return "Default trigger conditions not found."

@router.post("/agent/initialize-inbox")
async def trigger_inbox_initialization(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """
    Triggers the background task to initialize the user's inbox.
    Uses Redis to track the status and prevent multiple initializations.
    """
    redis_client = get_redis_client()
    status_key = RedisKeys.get_inbox_initialization_status_key(current_user.uuid)
    status = redis_client.get(status_key)

    if status == b'running':
        return {"message": "Inbox initialization is already in progress."}
    
    # Also check the fallback condition to prevent re-running a completed task
    if status == b'completed' or count_points(user_uuid=current_user.uuid) > 0:
        return {"message": "Inbox has already been initialized."}

    # Set the status to "running" immediately to prevent race conditions
    redis_client.set(status_key, "running")

    # The background task will update the status upon completion or failure
    background_tasks.add_task(initialize_inbox, user_uuid=current_user.uuid)
    return {"message": "Inbox initialization started."}

@router.post("/agent/reinitialize-inbox")
async def reinitialize_inbox_endpoint(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """
    Clears existing vector data and triggers the background task to re-initialize the user's inbox.
    If a vectorization process is already running, it will be gracefully interrupted.
    """
    redis_client = get_redis_client()
    status_key = RedisKeys.get_inbox_initialization_status_key(current_user.uuid)
    status = redis_client.get(status_key)

    # If a job is currently running, signal it to stop.
    if status == b'running':
        logger.info("An inbox initialization process is already running. Sending interruption signal.")
        interruption_key = RedisKeys.get_inbox_vectorization_interrupted_key(current_user.uuid)
        redis_client.set(interruption_key, "true")
        # Give the background worker a moment to see the signal and stop
        await asyncio.sleep(1)

    logger.info(f"Starting inbox re-initialization for user {current_user.uuid}. Clearing existing collections.")
    
    # Clear existing vector data by recreating the user's collection
    recreate_collection(user_uuid=current_user.uuid)
    
    logger.info(f"Collections cleared for user {current_user.uuid}. Triggering background task.")
    
    # Set the status to "running" immediately to prevent race conditions
    redis_client.set(status_key, "running")
    
    # The background task will update the status upon completion or failure
    background_tasks.add_task(initialize_inbox, user_uuid=current_user.uuid)
    
    return {"message": "Inbox re-initialization process started."}

@router.post("/agent/rerun-tone-analysis")
async def rerun_tone_of_voice_analysis(current_user: User = Depends(get_current_user)):
    """
    Triggers the background task to re-run the tone of voice analysis,
    but only if the inbox has been successfully initialized for the current user.
    """
    redis_client = get_redis_client()
    status_key = RedisKeys.get_inbox_initialization_status_key(current_user.uuid)
    status = redis_client.get(status_key)

    # Fallback: if Redis has no status, check Qdrant directly
    if not status:
        if count_points(user_uuid=current_user.uuid) > 0:
            status = b'completed'
    
    if status != b'completed':
        logger.warning(f"Tone of voice analysis requested for user {current_user.uuid}, but inbox initialization status is '{status}'.")
        raise HTTPException(
            status_code=400,
            detail="Inbox must be successfully vectorized before running tone of voice analysis. Please wait for initialization to complete."
        )

    logger.info(f"Rerunning tone of voice analysis for user {current_user.uuid} due to manual trigger.")
    asyncio.create_task(determine_user_tone_of_voice(user_uuid=current_user.uuid))
    return {"status": "success", "message": "Tone of voice analysis has been started."}

@router.get("/agent/initialize-inbox/status")
async def get_inbox_initialization_status(current_user: User = Depends(get_current_user)):
    """
    Gets the status of the inbox initialization task from Redis for the current user.
    Falls back to checking Qdrant if the Redis key is not present.
    """
    try:
        redis_client = get_redis_client()
        status_key = RedisKeys.get_inbox_initialization_status_key(current_user.uuid)
        status = redis_client.get(status_key)

        if status:
            return {"status": status}

        # If no status is in Redis, check Qdrant as a fallback.
        if count_points(user_uuid=current_user.uuid) > 0:
            return {"status": "completed"}

        return {"status": "not_started"}
    except Exception as e:
        logger.error(f"Error fetching inbox initialization status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tools")
async def discover_tools():
    """
    Discovers all available tools from all connected MCP servers.
    """
    logger.info("GET /tools - Discovering tools")
    try:
        tools = await agent_client.discover_mcp_tools()
        logger.info(f"GET /tools - Found {len(tools)} tools")
        return tools
    except Exception as e:
        logger.error(f"GET /tools - Error discovering tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error discovering tools.")
