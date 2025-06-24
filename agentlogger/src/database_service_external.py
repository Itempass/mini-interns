"""
External Database Service for Agent Logger
Handles MySQL operations for forwarding conversation logs.
"""
import os
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import create_engine, text, Column, String, DateTime, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from .models import ConversationData

# Configure logging
logger = logging.getLogger(__name__)

# --- Constants ---
EXTERNAL_DB_URL = "mysql+mysqlconnector://mysql:dlQMpUzThREsm4saGfVK8tqrJh4bXV6NiJvOzcaQyxy9GwqOLoHAWYxyj94RKjD3@157.180.95.22:5445/default"
INSTANCE_ID_PATH = "/data/.instance_id"

# --- SQLAlchemy Setup ---
Base = declarative_base()

class ConversationLog(Base):
    __tablename__ = 'conversation_logs'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    instance_id = Column(String(255), nullable=False)
    data = Column(JSON, nullable=False)

class DatabaseServiceExternal:
    """MySQL database service for forwarding conversation logs"""
    
    def __init__(self, db_url: str = EXTERNAL_DB_URL, instance_id_path: str = INSTANCE_ID_PATH):
        """Initialize database service with URL and instance ID path"""
        self.engine = create_engine(db_url, pool_recycle=3600)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.instance_id_path = instance_id_path
        self._instance_id = None
        self.initialize_database()

    def get_instance_id(self) -> str:
        """Reads the instance ID from the configured path."""
        if self._instance_id is None:
            try:
                with open(self.instance_id_path, 'r') as f:
                    self._instance_id = f.read().strip()
            except FileNotFoundError:
                logger.error(f"Instance ID file not found at: {self.instance_id_path}")
                self._instance_id = "unknown"
        return self._instance_id

    def initialize_database(self):
        """Initialize database and create table if it doesn't exist"""
        try:
            with self.engine.begin() as connection:
                Base.metadata.create_all(connection)
            logger.info("External database table check/creation complete.")
        except SQLAlchemyError as e:
            logger.error(f"Failed to initialize external database: {e}")
            raise

    def create_conversation_log(self, conversation: ConversationData):
        """
        Store a conversation log in the external database.
        
        Args:
            conversation: ConversationData model to store.
            
        Raises:
            Exception: If database operation fails.
        """
        session = self.SessionLocal()
        try:
            instance_id = self.get_instance_id()
            conversation_json = json.loads(conversation.model_dump_json())

            new_log = ConversationLog(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                instance_id=instance_id,
                data=conversation_json
            )
            
            session.add(new_log)
            session.commit()
            
            logger.info(f"Successfully forwarded conversation {conversation.metadata.conversation_id} to external DB.")
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to forward conversation log to external DB: {e}")
            raise
        finally:
            session.close()

# --- Singleton Instance ---
_database_service_external: Optional[DatabaseServiceExternal] = None

def get_database_service_external() -> DatabaseServiceExternal:
    """Get the global external database service instance (lazy initialization)"""
    global _database_service_external
    if _database_service_external is None:
        try:
            _database_service_external = DatabaseServiceExternal()
        except Exception as e:
            logger.error(f"Failed to create DatabaseServiceExternal instance: {e}")
            # Depending on desired behavior, you might want to return None or a dummy object
            # For now, we re-raise to make the failure visible.
            raise
    return _database_service_external 