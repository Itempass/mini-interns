"""
Database Service for Agent Logger
Handles SQLite operations for conversation storage
"""

import os
import json
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from .models import ConversationData

# Configure logging
logger = logging.getLogger(__name__)

class DatabaseService:
    """SQLite database service for conversation storage"""
    
    def __init__(self, db_path: str = "/data/db/conversations.db"):
        """Initialize database service with path"""
        self.db_path = db_path
        self._ensure_db_directory()
        self.initialize_database()
    
    def _ensure_db_directory(self):
        """Ensure the database directory exists"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
    
    def initialize_database(self):
        """Initialize database with schema"""
        try:
            # Read schema from file
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            # Execute schema
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(schema_sql)
                conn.commit()
            
            logger.info(f"Database initialized at: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def create_conversation(self, conversation: ConversationData, anonymized: bool = True) -> str:
        """
        Store a conversation in the database
        
        Args:
            conversation: ConversationData model to store
            anonymized: Whether the conversation has been anonymized
            
        Returns:
            conversation_id of the stored conversation
            
        Raises:
            Exception: If database operation fails
        """
        try:
            conversation_id = conversation.metadata.conversation_id
            
            # Ensure timestamp is present
            if not conversation.metadata.timestamp:
                conversation.metadata.timestamp = datetime.now().isoformat()
                
            conversation_json = json.dumps(conversation.model_dump())
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO conversations (id, data, anonymized) 
                    VALUES (?, ?, ?)
                    """,
                    (conversation_id, conversation_json, anonymized)
                )
                conn.commit()
            
            logger.info(f"Stored conversation: {conversation_id} (anonymized: {anonymized})")
            return conversation_id
            
        except sqlite3.IntegrityError as e:
            logger.error(f"Conversation {conversation_id} already exists: {e}")
            raise ValueError(f"Conversation {conversation_id} already exists")
        except Exception as e:
            logger.error(f"Failed to store conversation {conversation_id}: {e}")
            raise
    
    def get_conversation(self, conversation_id: str) -> Optional[ConversationData]:
        """
        Retrieve a conversation from the database
        
        Args:
            conversation_id: ID of the conversation to retrieve
            
        Returns:
            ConversationData model or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT data FROM conversations WHERE id = ?",
                    (conversation_id,)
                )
                row = cursor.fetchone()
            
            if row is None:
                logger.info(f"Conversation not found: {conversation_id}")
                return None
            
            # Parse JSON and create model
            conversation_data = json.loads(row['data'])
            return ConversationData.model_validate(conversation_data)
            
        except Exception as e:
            logger.error(f"Failed to retrieve conversation {conversation_id}: {e}")
            return None
    
    def get_all_conversations(self) -> List[ConversationData]:
        """
        Retrieve all conversations from the database
        
        Returns:
            List of ConversationData models (empty list if none found)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT data FROM conversations ORDER BY created_at DESC"
                )
                rows = cursor.fetchall()
            
            conversations = []
            for row in rows:
                try:
                    conversation_data = json.loads(row['data'])
                    conversation = ConversationData.model_validate(conversation_data)
                    conversations.append(conversation)
                except Exception as e:
                    logger.warning(f"Failed to parse conversation data: {e}")
                    continue
            
            logger.info(f"Retrieved {len(conversations)} conversations")
            return conversations
            
        except Exception as e:
            logger.error(f"Failed to retrieve conversations: {e}")
            return []
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check database health
        
        Returns:
            Health status information
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM conversations")
                result = cursor.fetchone()
                conversation_count = result[0] if result else 0
            
            return {
                "service": "database",
                "status": "healthy",
                "database_path": self.db_path,
                "conversation_count": conversation_count,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "service": "database", 
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

# Global service instance (lazy initialization)
_database_service = None

def get_database_service() -> DatabaseService:
    """Get the global database service instance (lazy initialization)"""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service 