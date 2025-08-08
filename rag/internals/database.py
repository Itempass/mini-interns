import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional
from uuid import UUID

import aiomysql
from aiomysql.cursors import DictCursor

from shared.config import settings
from rag.models import VectorDatabase

logger = logging.getLogger(__name__)

# Global connection pool
pool = None

async def get_rag_db_pool():
    """Singleton to create and return a database connection pool for RAG."""
    global pool
    if pool is None:
        try:
            pool = await aiomysql.create_pool(
                host='db',
                port=3306,
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                db=settings.MYSQL_DATABASE,
                autocommit=False,
                init_command="SET time_zone='+00:00'",
            )
            logger.info("Successfully created database connection pool for RAG.")
        except Exception as e:
            logger.error(f"Failed to create RAG database connection pool: {e}")
            raise
    return pool

@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[aiomysql.Connection, None]:
    """Provides a database connection from the pool."""
    db_pool = await get_rag_db_pool()
    conn = None
    try:
        conn = await db_pool.acquire()
        yield conn
    finally:
        if conn:
            db_pool.release(conn)

def _row_to_model(row: dict) -> VectorDatabase:
    """Converts a database row to a VectorDatabase Pydantic model."""
    row['uuid'] = UUID(bytes=row['uuid'])
    row['user_id'] = UUID(bytes=row['user_id'])
    if isinstance(row.get('settings'), str):
        row['settings'] = json.loads(row['settings'])
    return VectorDatabase(**row)

async def _create_vector_database_in_db(db_config: VectorDatabase) -> VectorDatabase:
    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO vector_databases (uuid, user_id, name, type, provider, settings, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    db_config.uuid.bytes, db_config.user_id.bytes, db_config.name, db_config.type,
                    db_config.provider, json.dumps(db_config.settings), db_config.status, db_config.error_message
                )
            )
            await conn.commit()
    return db_config

async def _get_vector_database_from_db(uuid: UUID, user_id: UUID) -> Optional[VectorDatabase]:
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute("SELECT * FROM vector_databases WHERE uuid = %s AND user_id = %s", (uuid.bytes, user_id.bytes))
            row = await cursor.fetchone()
    return _row_to_model(row) if row else None

async def _list_vector_databases_from_db(user_id: UUID) -> List[VectorDatabase]:
    databases = []
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute("SELECT * FROM vector_databases WHERE user_id = %s", (user_id.bytes,))
            rows = await cursor.fetchall()
    for row in rows:
        databases.append(_row_to_model(row))
    return databases

async def _update_vector_database_in_db(uuid: UUID, db_config: VectorDatabase, user_id: UUID) -> Optional[VectorDatabase]:
    async with get_db_connection() as conn:
        async with conn.cursor(DictCursor) as cursor:
            await cursor.execute(
                """
                UPDATE vector_databases
                SET name = %s, type = %s, provider = %s, settings = %s, status = %s, error_message = %s, updated_at = NOW()
                WHERE uuid = %s AND user_id = %s
                """,
                (
                    db_config.name, db_config.type, db_config.provider, json.dumps(db_config.settings),
                    db_config.status, db_config.error_message, uuid.bytes, user_id.bytes
                )
            )
            await conn.commit()
            if cursor.rowcount == 0:
                return None
    return await _get_vector_database_from_db(uuid, user_id)

async def _delete_vector_database_from_db(uuid: UUID, user_id: UUID) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("DELETE FROM vector_databases WHERE uuid = %s AND user_id = %s", (uuid.bytes, user_id.bytes))
            await conn.commit()
            return cursor.rowcount > 0 