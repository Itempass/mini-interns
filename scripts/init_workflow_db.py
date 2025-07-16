import mysql.connector
import time
import os
from shared.config import settings
import logging

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
            
            schema_path = os.path.join('workflow', 'schema.sql')
            logger.info(f"Reading schema from {schema_path}")

            with open(schema_path, 'r') as f:
                sql_script = f.read()
            
            # Execute each statement from the workflow schema file
            for statement in sql_script.split(';'):
                statement = statement.strip()
                if statement:
                    cursor.execute(statement)

            # Execute each statement from the prompt_optimizer schema file
            optimizer_schema_path = os.path.join('prompt_optimizer', 'schema.sql')
            if os.path.exists(optimizer_schema_path):
                logger.info(f"Reading schema from {optimizer_schema_path}")
                with open(optimizer_schema_path, 'r') as f:
                    optimizer_sql_script = f.read()
                
                for statement in optimizer_sql_script.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
            else:
                logger.warning(f"Schema file not found at {optimizer_schema_path}. Skipping.")
            
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