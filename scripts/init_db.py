import sqlite3
import os

# Define the path for the SQLite database within the container
MESSAGES_DATABASE_PATH = '/data/db/database.sqlite3'
AGENTLOGGER_DATABASE_PATH = '/data/db/conversations.db'

def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """
    Adds a column to a table if it does not already exist.
    """
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    
    if column_name not in columns:
        print(f"Column '{column_name}' not found in table '{table_name}'. Adding it...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        print(f"Column '{column_name}' added successfully.")
    else:
        print(f"Column '{column_name}' already exists in table '{table_name}'.")

def migrate_agentlogger_db():
    """
    Initializes and migrates the Agent Logger database.
    - Adds new columns to the 'conversations' table for schema evolution.
    """
    print("--- Running Agent Logger database migration ---")

    db_dir = os.path.dirname(AGENTLOGGER_DATABASE_PATH)
    if not os.path.exists(db_dir):
        print(f"Database directory not found at {db_dir}. This script is for migrating an existing database, which may not exist yet.")
        print("--- Agent Logger database migration skipped ---")
        return

    try:
        with sqlite3.connect(AGENTLOGGER_DATABASE_PATH) as conn:
            cursor = conn.cursor()
            print("Successfully connected to the Agent Logger database.")

            # Add 'readable_workflow_name' column
            add_column_if_not_exists(cursor, 'conversations', 'readable_workflow_name', 'TEXT')

            # Add 'readable_instance_context' column
            add_column_if_not_exists(cursor, 'conversations', 'readable_instance_context', 'TEXT')
            
            # Create index for readable_workflow_name
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_workflow_name ON conversations(readable_workflow_name)")
            print("Index 'idx_conversations_workflow_name' is present or was created successfully.")

            conn.commit()
        
        print("--- Agent Logger database migration complete ---")

    except sqlite3.Error as e:
        print(f"An error occurred during Agent Logger database migration: {e}")
        # Do not exit, as this may be a non-critical error (e.g., table not found yet)

def main():
    """
    Initializes the database. Creates the directory, database file,
    and tables if they don't already exist.
    """
    print("--- Running database initialization ---")

    # Ensure the directory for the database exists
    db_dir = os.path.dirname(MESSAGES_DATABASE_PATH)
    if not os.path.exists(db_dir):
        print(f"Database directory not found. Creating {db_dir}...")
        os.makedirs(db_dir)
        print("Directory created.")
    else:
        print("Database directory already exists.")

    try:
        # Connect to the messages database.
        with sqlite3.connect(MESSAGES_DATABASE_PATH) as conn:
            cursor = conn.cursor()
            print("Successfully connected to the messages database.")

            # Create the 'messages' table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            print("Table 'messages' is present or was created successfully.")
        
        # Run agentlogger migration which connects to its own DB
        migrate_agentlogger_db()

        print("--- Database initialization and migration complete ---")

    except sqlite3.Error as e:
        print(f"An error occurred during database initialization: {e}")
        # Exit with a non-zero status code to indicate failure
        exit(1)

if __name__ == "__main__":
    main() 