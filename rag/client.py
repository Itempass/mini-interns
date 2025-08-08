from uuid import UUID
from typing import List, Optional, Dict, Any
import json
import os
import httpx
import logging
from .models import VectorDatabase
from .internals import database as db
from shared.services.embedding_service import get_embedding_model_vector_size
from .internals.pinecone import test_pinecone_serverless_connection

logger = logging.getLogger(__name__)

RAG_AVAILABLE_PATH = os.path.join(os.path.dirname(__file__), 'available.json')

async def get_available_providers() -> Dict[str, Any]:
    """Reads and returns the available RAG providers from the JSON file."""
    try:
        with open(RAG_AVAILABLE_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

async def create_vector_database(db_config: VectorDatabase) -> VectorDatabase:
    """Creates a new vector database configuration."""
    return await db._create_vector_database_in_db(db_config)

async def get_vector_database(uuid: UUID, user_id: UUID) -> Optional[VectorDatabase]:
    """Retrieves a specific vector database configuration."""
    return await db._get_vector_database_from_db(uuid, user_id)

async def list_vector_databases(user_id: UUID) -> List[VectorDatabase]:
    """Lists all vector database configurations for a user."""
    return await db._list_vector_databases_from_db(user_id)

async def update_vector_database(uuid: UUID, db_config: VectorDatabase, user_id: UUID) -> Optional[VectorDatabase]:
    """Updates an existing vector database configuration."""
    return await db._update_vector_database_in_db(uuid, db_config, user_id)

async def delete_vector_database(uuid: UUID, user_id: UUID) -> bool:
    """Deletes a vector database configuration."""
    return await db._delete_vector_database_from_db(uuid, user_id)

# --- Phase 2: RAG Execution Integration ---
async def execute_step(
    *,
    user_id: UUID,
    workflow_instance_uuid: UUID,
    rag_definition_uuid: UUID,
    prompt: str,
    vectordb_uuid: UUID,
    rerank: bool,
    top_k: int,
) -> Dict[str, Any]:
    """
    Executes a RAG step. This is a thin facade that will call an internal runner
    which handles provider-specific logic.
    """
    from .internals import runner as rag_runner  # Local import to avoid cycles if any
    return await rag_runner.run_rag_step(
        user_id=user_id,
        workflow_instance_uuid=workflow_instance_uuid,
        rag_definition_uuid=rag_definition_uuid,
        prompt=prompt,
        vectordb_uuid=vectordb_uuid,
        rerank=rerank,
        top_k=top_k,
    )

# --- Connectivity Tests ---
async def test_vector_database_connection(db_config: VectorDatabase) -> Dict[str, Any]:
    """
    Tests connectivity for a configured vector database.
    Serverless Pinecone only is supported for external provider 'pinecone-serverless'.
    Internal providers: success (no external connectivity required)
    Returns: { ok: bool, message: str }
    """
    try:
        if db_config.type == "internal":
            return {"ok": True, "message": "Internal provider does not require external connectivity."}

        provider = (db_config.provider or "").lower()

        if provider == "pinecone-serverless":
            return await test_pinecone_serverless_connection(db_config)

        # Default: Unknown external provider
        return {"ok": False, "message": f"Unknown provider '{db_config.provider}'. Cannot test connectivity."}
    except Exception as e:
        logger.error(f"[RAG/Test] Unexpected error: {e}", exc_info=True)
        return {"ok": False, "message": f"Unexpected error during connectivity test: {e}"}
