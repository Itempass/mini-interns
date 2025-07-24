"""
Database Service for Agent Logger
Handles SQLite operations for conversation storage
"""

import os
import json
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from .models import LogEntry, Message

# Configure logging
logger = logging.getLogger(__name__)

class DatabaseService:
    """SQLite database service for conversation storage"""

    def __init__(self, db_path: str = "/data/db/agentlogger.db"):
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
        """
        Initialize database with schema and run migrations if necessary.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Run schema to create tables if they don't exist
                schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
                with open(schema_path, 'r') as f:
                    # We only run the CREATE TABLE statement to avoid errors with indices on missing columns
                    schema_sql = f.read()
                    create_table_statement = schema_sql.split(';')[0]
                    cursor.execute(create_table_statement)

                # --- Start of Column Migrations ---
                # Check for all required columns and add them if they are missing.
                cursor.execute("PRAGMA table_info(logs)")
                columns = [info[1] for info in cursor.fetchall()]

                migrations = {
                    'prompt_tokens': "ALTER TABLE logs ADD COLUMN prompt_tokens INTEGER",
                    'completion_tokens': "ALTER TABLE logs ADD COLUMN completion_tokens INTEGER",
                    'total_tokens': "ALTER TABLE logs ADD COLUMN total_tokens INTEGER",
                    'total_cost': "ALTER TABLE logs ADD COLUMN total_cost REAL",
                    'user_id': "ALTER TABLE logs ADD COLUMN user_id TEXT",
                    'model': "ALTER TABLE logs ADD COLUMN model TEXT"
                }

                for col, statement in migrations.items():
                    if col not in columns:
                        logger.info(f"Adding '{col}' column to 'logs' table.")
                        cursor.execute(statement)

                # --- End of Column Migrations ---

                # --- Start of Index Creation ---
                # Now that all columns are guaranteed to exist, we can create indices.
                # We extract index creation from the schema file to run them separately.
                index_statements = [stmt for stmt in schema_sql.split(';') if "CREATE INDEX" in stmt]
                for statement in index_statements:
                    if statement.strip():
                        cursor.execute(statement)
                # --- End of Index Creation ---

                # --- Legacy Migration for 'stop_checker' in CHECK constraint ---
                # This is a more complex migration that involves renaming and copying data.
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='logs'")
                create_sql_row = cursor.fetchone()
                if create_sql_row and "'stop_checker'" not in create_sql_row[0]:
                    self._run_stop_checker_migration(conn)
                
                conn.commit()
            logger.info(f"Database initialized at: {self.db_path}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}", exc_info=True)
            raise

    def _run_stop_checker_migration(self, conn: sqlite3.Connection):
        """
        Handles the specific migration to add 'stop_checker' to the log_type
        CHECK constraint by rebuilding the table.
        """
        logger.info("Starting schema migration to add 'stop_checker' to 'logs' table...")
        
        # 1. Rename the old table
        conn.execute("ALTER TABLE logs RENAME TO logs_old;")
        logger.info("Renamed 'logs' to 'logs_old'.")

        # 2. Create the new table with the fully updated schema
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        logger.info("Created new 'logs' table with updated schema.")

        # 3. Copy data from the old table to the new one, handling potentially missing columns
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(logs_old)")
        old_columns = [info[1] for info in cursor.fetchall()]

        # These are the columns in the new schema
        new_columns = [
            'id', 'reference_string', 'log_type', 'workflow_id', 'workflow_instance_id',
            'workflow_name', 'step_id', 'step_instance_id', 'step_name', 'messages',
            'needs_review', 'feedback', 'start_time', 'end_time', 'anonymized',
            'prompt_tokens', 'completion_tokens', 'total_tokens', 'total_cost', 'user_id', 'model'
        ]
        
        # Select only the columns that exist in the old table
        columns_to_copy = [col for col in new_columns if col in old_columns]
        
        insert_sql = f"""
            INSERT INTO logs ({', '.join(columns_to_copy)})
            SELECT {', '.join(columns_to_copy)}
            FROM logs_old;
        """
        conn.execute(insert_sql)
        logger.info("Copied data from 'logs_old' to new 'logs' table.")

        # 4. Drop the old table
        conn.execute("DROP TABLE logs_old;")
        logger.info("Dropped 'logs_old' table. Migration complete.")

    def create_log_entry(self, log_entry: LogEntry) -> str:
        """
        Store a log entry in the database.
        """
        try:
            # Serialize messages to a JSON string if they exist
            messages_json = json.dumps([msg.model_dump() for msg in log_entry.messages]) if log_entry.messages else None

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO logs (id, reference_string, log_type, workflow_id, workflow_instance_id, workflow_name, step_id, step_instance_id, step_name, messages, needs_review, feedback, start_time, end_time, anonymized, prompt_tokens, completion_tokens, total_tokens, total_cost, user_id, model)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log_entry.id,
                        log_entry.reference_string,
                        log_entry.log_type,
                        log_entry.workflow_id,
                        log_entry.workflow_instance_id,
                        log_entry.workflow_name,
                        log_entry.step_id,
                        log_entry.step_instance_id,
                        log_entry.step_name,
                        messages_json,
                        log_entry.needs_review,
                        log_entry.feedback,
                        log_entry.start_time,
                        log_entry.end_time,
                        log_entry.anonymized,
                        log_entry.prompt_tokens,
                        log_entry.completion_tokens,
                        log_entry.total_tokens,
                        log_entry.total_cost,
                        log_entry.user_id,
                        log_entry.model,
                    )
                )
                conn.commit()

            logger.info(f"Stored log entry: {log_entry.id}")
            return log_entry.id

        except sqlite3.IntegrityError as e:
            logger.error(f"Log entry {log_entry.id} already exists: {e}")
            raise ValueError(f"Log entry {log_entry.id} already exists")
        except Exception as e:
            logger.error(f"Failed to store log entry {log_entry.id}: {e}")
            raise

    def upsert_log_entry(self, log_entry: LogEntry) -> str:
        """
        Insert or update a log entry in the database.
        If a log with the same ID exists, it will be overwritten.
        """
        try:
            messages_json = json.dumps([msg.model_dump() for msg in log_entry.messages]) if log_entry.messages else None

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO logs (id, reference_string, log_type, workflow_id, workflow_instance_id, workflow_name, step_id, step_instance_id, step_name, messages, needs_review, feedback, start_time, end_time, anonymized, prompt_tokens, completion_tokens, total_tokens, total_cost, user_id, model)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        reference_string = excluded.reference_string,
                        log_type = excluded.log_type,
                        workflow_id = excluded.workflow_id,
                        workflow_instance_id = excluded.workflow_instance_id,
                        workflow_name = excluded.workflow_name,
                        step_id = excluded.step_id,
                        step_instance_id = excluded.step_instance_id,
                        step_name = excluded.step_name,
                        messages = excluded.messages,
                        needs_review = excluded.needs_review,
                        feedback = excluded.feedback,
                        start_time = excluded.start_time,
                        end_time = excluded.end_time,
                        anonymized = excluded.anonymized,
                        prompt_tokens = excluded.prompt_tokens,
                        completion_tokens = excluded.completion_tokens,
                        total_tokens = excluded.total_tokens,
                        total_cost = excluded.total_cost,
                        user_id = excluded.user_id,
                        model = excluded.model
                    """,
                    (
                        log_entry.id,
                        log_entry.reference_string,
                        log_entry.log_type,
                        log_entry.workflow_id,
                        log_entry.workflow_instance_id,
                        log_entry.workflow_name,
                        log_entry.step_id,
                        log_entry.step_instance_id,
                        log_entry.step_name,
                        messages_json,
                        log_entry.needs_review,
                        log_entry.feedback,
                        log_entry.start_time.isoformat(),
                        log_entry.end_time.isoformat() if log_entry.end_time else None,
                        log_entry.anonymized,
                        log_entry.prompt_tokens,
                        log_entry.completion_tokens,
                        log_entry.total_tokens,
                        log_entry.total_cost,
                        log_entry.user_id,
                        log_entry.model,
                    )
                )
                conn.commit()

            logger.info(f"Upserted log entry: {log_entry.id}")
            return log_entry.id
        except Exception as e:
            logger.error(f"Failed to upsert log entry {log_entry.id}: {e}", exc_info=True)
            raise

    def get_log_entry(self, log_id: str, user_id: str) -> Optional[LogEntry]:
        """
        Retrieve a log entry from the database, filtered by user.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                query = "SELECT * FROM logs WHERE id = ? AND user_id = ?"
                params = (log_id, user_id)

                cursor = conn.execute(query, params)
                row = cursor.fetchone()

            if row is None:
                logger.info(f"Log entry not found: {log_id}")
                return None

            return self._row_to_log_entry(row)

        except Exception as e:
            logger.error(f"Failed to retrieve log entry {log_id}: {e}")
            return None

    def get_all_log_entries(self, user_id: str) -> List[LogEntry]:
        """
        Retrieve all log entries for a specific user from the database.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                query = "SELECT * FROM logs WHERE user_id = ? ORDER BY start_time DESC"
                params = (user_id,)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

            return [self._row_to_log_entry(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to retrieve log entries for user {user_id}: {e}")
            return []
            
    def get_cost_history(self, user_id: str) -> List[LogEntry]:
        """
        Retrieve all log entries with a cost for a specific user.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                query = "SELECT * FROM logs WHERE user_id = ? AND total_cost > 0 ORDER BY start_time DESC"
                params = (user_id,)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

            return [self._row_to_log_entry(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to retrieve cost history for user {user_id}: {e}")
            return []

    def get_grouped_log_entries(self, user_id: str, limit: int, offset: int, workflow_id: Optional[str] = None, log_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve paginated and grouped log entries from the database for a specific user.
        Fetches workflow logs with pagination and their associated step logs.
        Can be filtered by a specific workflow_id and/or log_type.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # 1. Build base queries and params
                parent_log_types = "('workflow', 'workflow_agent')"
                if log_type:
                    parent_log_types = f"('{log_type}')"

                count_query = f"SELECT COUNT(*) FROM logs WHERE log_type IN {parent_log_types} AND user_id = ?"
                main_query = f"SELECT * FROM logs WHERE log_type IN {parent_log_types} AND user_id = ?"
                params = [user_id]

                if workflow_id:
                    count_query += " AND workflow_id = ?"
                    main_query += " AND workflow_id = ?"
                    params.append(workflow_id)

                # 2. Get total count of workflows for pagination
                total_workflows_cursor = conn.execute(count_query, tuple(params))
                total_workflows = total_workflows_cursor.fetchone()[0]

                # 3. Fetch a page of parent workflow logs
                main_query += " ORDER BY DATETIME(start_time) DESC LIMIT ? OFFSET ?"
                pagination_params = (limit, offset)
                
                workflows_cursor = conn.execute(main_query, tuple(params) + pagination_params)
                workflow_rows = workflows_cursor.fetchall()
                
                if not workflow_rows:
                    return {"workflows": [], "total_workflows": total_workflows}

                parent_workflows = [self._row_to_log_entry(row) for row in workflow_rows]
                workflow_instance_ids = [wf.workflow_instance_id for wf in parent_workflows if wf.workflow_instance_id]
                
                # 3. Fetch all child logs for the retrieved workflows
                child_logs = []
                if workflow_instance_ids:
                    # Create placeholders for the IN clause
                    placeholders = ','.join('?' for _ in workflow_instance_ids)

                    child_query = f"""
                        SELECT * FROM logs 
                        WHERE log_type IN ('custom_agent', 'custom_llm', 'stop_checker') 
                        AND workflow_instance_id IN ({placeholders})
                        AND user_id = ?
                        """
                    child_params = list(workflow_instance_ids)
                    child_params.append(user_id)
                        
                    child_query += " ORDER BY DATETIME(start_time) ASC"
                    
                    children_cursor = conn.execute(
                        child_query,
                        tuple(child_params)
                    )
                    child_rows = children_cursor.fetchall()
                    child_logs = [self._row_to_log_entry(row) for row in child_rows]
                
                # 4. Group children under their parents
                child_map = {}
                for child in child_logs:
                    if child.workflow_instance_id not in child_map:
                        child_map[child.workflow_instance_id] = []
                    child_map[child.workflow_instance_id].append(child)

                grouped_logs = []
                for wf in parent_workflows:
                    # Convert model to dict for JSON serialization in the API layer
                    grouped_logs.append({
                        "workflow_log": wf.model_dump(),
                        "step_logs": [child.model_dump() for child in child_map.get(wf.workflow_instance_id, [])]
                    })

                return {"workflows": grouped_logs, "total_workflows": total_workflows}

        except Exception as e:
            logger.error(f"Failed to retrieve grouped log entries: {e}", exc_info=True)
            return {"workflows": [], "total_workflows": 0}

    def get_workflow_usage_stats(self, workflow_instance_id: str) -> Dict[str, Any]:
        """
        Calculates the total tokens and cost for a given workflow instance.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        SUM(prompt_tokens) as total_prompt_tokens,
                        SUM(completion_tokens) as total_completion_tokens,
                        SUM(total_tokens) as total_tokens,
                        SUM(total_cost) as total_cost
                    FROM logs
                    WHERE workflow_instance_id = ?
                    """,
                    (workflow_instance_id,),
                )
                stats = cursor.fetchone()

                return {
                    "total_prompt_tokens": stats[0] or 0,
                    "total_completion_tokens": stats[1] or 0,
                    "total_tokens": stats[2] or 0,
                    "total_cost": stats[3] or 0.0,
                }
        except Exception as e:
            logger.error(f"Failed to calculate usage stats for workflow {workflow_instance_id}: {e}", exc_info=True)
            return {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
            }

    def _row_to_log_entry(self, row: sqlite3.Row) -> LogEntry:
        """Converts a database row to a LogEntry model."""
        log_data = dict(row)
        messages_json = log_data.pop('messages', None)
        if messages_json:
            log_data['messages'] = [Message.model_validate(msg) for msg in json.loads(messages_json)]
        # Handle timezone for datetime fields from SQLite (stored as strings)
        if 'start_time' in log_data and isinstance(log_data['start_time'], str):
            log_data['start_time'] = datetime.fromisoformat(log_data['start_time'].replace("Z", "+00:00"))
        if 'end_time' in log_data and log_data['end_time'] and isinstance(log_data['end_time'], str):
            log_data['end_time'] = datetime.fromisoformat(log_data['end_time'].replace("Z", "+00:00"))

        # Ensure numeric fields are correctly typed, defaulting to None if they don't exist
        log_data['prompt_tokens'] = log_data.get('prompt_tokens')
        log_data['completion_tokens'] = log_data.get('completion_tokens')
        log_data['total_tokens'] = log_data.get('total_tokens')
        log_data['total_cost'] = log_data.get('total_cost')
        
        return LogEntry.model_validate(log_data)

    def health_check(self) -> Dict[str, Any]:
        """
        Check database health.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM logs")
                result = cursor.fetchone()
                log_count = result[0] if result else 0

            return {
                "service": "database",
                "status": "healthy",
                "database_path": self.db_path,
                "log_count": log_count,
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

_database_service = None

def get_database_service() -> DatabaseService:
    """Get the global database service instance (lazy initialization)"""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service 