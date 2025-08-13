import mysql.connector
import time
import os
from shared.config import settings
import logging
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_workflow_db():
    """Initializes the workflow database by connecting and executing the schema.sql file."""
    retries = 10
    delay = 5  # seconds

    for i in range(retries):
        try:
            logger.info("Attempting to connect to workflow database...")
            # Use the configuration from shared/config.py
            conn = mysql.connector.connect(
                host='db',  # This is the service name from docker-compose.yaml
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                database=settings.MYSQL_DATABASE,
                port=3306
            )
            logger.info("Database connection successful.")
            
            cursor = conn.cursor()

            # --- Schema Initialization ---
            # Execute schema files first to ensure all tables are created before we try to alter them.
            
            # Execute each statement from the workflow schema file
            schema_path = os.path.join('workflow', 'schema.sql')
            logger.info(f"Reading schema from {schema_path}")
            with open(schema_path, 'r') as f:
                sql_script = f.read()
            for statement in sql_script.split(';'):
                statement = statement.strip()
                if statement:
                    try:
                        cursor.execute(statement)
                    except mysql.connector.Error as err:
                        if err.errno == 1061:  # ER_DUP_KEYNAME for MySQL
                            logger.info(f"Ignoring duplicate key/index error for workflow schema: {err}")
                        else:
                            raise err

            # Execute each statement from the prompt_optimizer schema file
            optimizer_schema_path = os.path.join('prompt_optimizer', 'schema.sql')
            if os.path.exists(optimizer_schema_path):
                logger.info(f"Reading schema from {optimizer_schema_path}")
                with open(optimizer_schema_path, 'r') as f:
                    optimizer_sql_script = f.read()
                for statement in optimizer_sql_script.split(';'):
                    statement = statement.strip()
                    if statement:
                        try:
                            cursor.execute(statement)
                        except mysql.connector.Error as err:
                            if err.errno == 1061:  # ER_DUP_KEYNAME for MySQL
                                logger.info(f"Ignoring duplicate key/index error for optimizer schema: {err}")
                            else:
                                raise err
            else:
                logger.warning(f"Schema file not found at {optimizer_schema_path}. Skipping.")

            # Execute each statement from the user schema file
            user_schema_path = os.path.join('user', 'schema.sql')
            if os.path.exists(user_schema_path):
                logger.info(f"Reading schema from {user_schema_path}")
                with open(user_schema_path, 'r') as f:
                    user_sql_script = f.read()
                for statement in user_sql_script.split(';'):
                    statement = statement.strip()
                    if statement:
                        try:
                            cursor.execute(statement)
                        except mysql.connector.Error as err:
                            if err.errno == 1061:  # ER_DUP_KEYNAME for MySQL
                                logger.info(f"Ignoring duplicate key/index error for user schema: {err}")
                            else:
                                raise err
            else:
                logger.warning(f"Schema file not found at {user_schema_path}. Skipping.")

            # --- Migrations ---
            # Now that tables are created, run all migrations.

            # --- Start of Default System User Creation ---
            # As per our plan, we only create a default user if we are in password-auth mode.
            if not settings.AUTH0_DOMAIN and (settings.AUTH_PASSWORD or settings.AUTH_SELFSET_PASSWORD):
                logger.info("Password authentication is enabled. Ensuring default system user exists...")
                default_user_uuid = "12345678-1234-5678-9012-123456789012"
                # Use INSERT IGNORE to make this operation idempotent. It won't fail if the user already exists.
                # We use UUID_TO_BIN to correctly store the UUID in the BINARY(16) column.
                insert_query = "INSERT IGNORE INTO users (uuid) VALUES (UUID_TO_BIN(%s))"
                try:
                    cursor.execute(insert_query, (default_user_uuid,))
                    if cursor.rowcount > 0:
                        logger.info(f"Default system user with UUID {default_user_uuid} created.")
                    else:
                        logger.info(f"Default system user with UUID {default_user_uuid} already exists.")
                except mysql.connector.Error as err:
                    logger.error(f"Failed to create or verify default system user: {err}")
                    raise err
            # --- End of Default System User Creation ---

            # --- Start of Evaluation Template Polling Status Migration ---
            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'evaluation_templates' AND column_name = 'status' AND table_schema = %s", (settings.MYSQL_DATABASE,))
            if cursor.fetchone()[0] == 0:
                logger.info("Adding 'status' column to 'evaluation_templates'...")
                cursor.execute("ALTER TABLE evaluation_templates ADD COLUMN status VARCHAR(50) DEFAULT 'completed'")

            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'evaluation_templates' AND column_name = 'processing_error' AND table_schema = %s", (settings.MYSQL_DATABASE,))
            if cursor.fetchone()[0] == 0:
                logger.info("Adding 'processing_error' column to 'evaluation_templates'...")
                cursor.execute("ALTER TABLE evaluation_templates ADD COLUMN processing_error TEXT")
            # --- End of Evaluation Template Polling Status Migration ---

            # --- Start of Targeted Migration ---
            # Check if the 'created_at' column exists in 'evaluation_runs'
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'evaluation_runs' AND column_name = 'created_at' AND table_schema = %s
            """, (settings.MYSQL_DATABASE,))
            
            column_exists = cursor.fetchone()[0] == 1

            # If the column does not exist, add it.
            if not column_exists:
                logger.info("Column 'created_at' not found in 'evaluation_runs'. Adding it now...")
                try:
                    cursor.execute("""
                        ALTER TABLE evaluation_runs
                        ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    """)
                    logger.info("Successfully added 'created_at' column to 'evaluation_runs'.")
                except mysql.connector.Error as err:
                    logger.error(f"Failed to add 'created_at' column: {err}")
                    raise err
            # --- End of Targeted Migration ---

            # --- Start of Decoupling Migration ---
            # Check for original_prompt column
            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'evaluation_runs' AND column_name = 'original_prompt' AND table_schema = %s", (settings.MYSQL_DATABASE,))
            if cursor.fetchone()[0] == 0:
                logger.info("Adding 'original_prompt' column to 'evaluation_runs'...")
                cursor.execute("ALTER TABLE evaluation_runs ADD COLUMN original_prompt TEXT NOT NULL")

            # Check for original_model column
            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'evaluation_runs' AND column_name = 'original_model' AND table_schema = %s", (settings.MYSQL_DATABASE,))
            if cursor.fetchone()[0] == 0:
                logger.info("Adding 'original_model' column to 'evaluation_runs'...")
                cursor.execute("ALTER TABLE evaluation_runs ADD COLUMN original_model VARCHAR(255) NOT NULL")

            # Check if old workflow_step_uuid column exists before trying to drop it
            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'evaluation_runs' AND column_name = 'workflow_step_uuid' AND table_schema = %s", (settings.MYSQL_DATABASE,))
            if cursor.fetchone()[0] > 0:
                logger.info("Dropping obsolete 'workflow_step_uuid' column from 'evaluation_runs'...")
                cursor.execute("ALTER TABLE evaluation_runs DROP COLUMN workflow_step_uuid")
            # --- End of Decoupling Migration ---

            # --- Start of User Balance Migration ---
            # First, add the column if it doesn't exist
            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'balance' AND table_schema = %s", (settings.MYSQL_DATABASE,))
            if cursor.fetchone()[0] == 0:
                logger.info("Adding 'balance' column to 'users' table...")
                cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
                logger.info("Successfully added 'balance' column.")

                # Second, set initial balance for any existing users.
                # This should ONLY run once, immediately after the column is created.
                logger.info("Setting initial $5.00 balance for all existing users...")
                cursor.execute("UPDATE users SET balance = 5.0")
                logger.info(f"{cursor.rowcount} user(s) updated to initial balance.")
            # --- End of User Balance Migration ---
            
            # --- Start of Trigger Model Backfill Migration ---
            logger.info("Starting trigger_model backfill migration...")
            try:
                cursor.execute("SELECT uuid, details FROM triggers")
                triggers = cursor.fetchall()
                logger.info(f"Found {len(triggers)} triggers to check.")
                
                for trigger_uuid_bytes, details_json in triggers:
                    trigger_uuid = trigger_uuid_bytes.hex()
                    details = json.loads(details_json) if details_json else {}
                    
                    if "trigger_model" not in details or not details["trigger_model"]:
                        details["trigger_model"] = "google/gemini-2.5-flash"
                        updated_details_json = json.dumps(details)
                        
                        update_query = "UPDATE triggers SET details = %s WHERE uuid = UUID_TO_BIN(%s)"
                        cursor.execute(update_query, (updated_details_json, trigger_uuid))
                        logger.info(f"Updated trigger {trigger_uuid} to include default trigger_model.")
            except mysql.connector.Error as err:
                logger.error(f"An error occurred during the trigger_model backfill migration: {err}")
            # --- End of Trigger Model Backfill Migration ---

            # --- Start of Stripe Payments Table Creation ---
            # Create stripe_payments table if it doesn't exist (idempotent)
            logger.info("Ensuring 'stripe_payments' table exists...")
            try:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stripe_payments (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        payment_intent_id VARCHAR(255) UNIQUE,
                        checkout_session_id VARCHAR(255) UNIQUE,
                        user_uuid BINARY(16) NOT NULL,
                        amount_cents INT NOT NULL,
                        currency VARCHAR(10) NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                logger.info("'stripe_payments' table is present or was created successfully.")
            except mysql.connector.Error as err:
                logger.error(f"Failed to create 'stripe_payments' table: {err}")
                raise err
            # --- End of Stripe Payments Table Creation ---

            conn.commit()
            cursor.close()
            conn.close()
            logger.info("Workflow database schema initialized successfully.")
            return
        
        except mysql.connector.Error as err:
            logger.warning(f"Database connection failed on attempt {i+1}/{retries}: {err}")
            if i < retries - 1:
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error("Could not connect to the database after several retries. Exiting.")
                # Exit with an error to prevent the API from starting with a bad DB state.
                exit(1)

if __name__ == "__main__":
    init_workflow_db() 