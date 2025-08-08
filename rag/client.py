from uuid import UUID
from typing import List, Optional, Dict, Any
import json
import os
from .models import VectorDatabase
from .internals import database as db

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
