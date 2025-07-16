import json
import logging
from typing import List, Optional
from uuid import UUID

import mysql.connector

from shared.config import settings
from .models import EvaluationTemplate

logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        conn = mysql.connector.connect(
            host='db',
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            port=3306
        )
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Error connecting to database: {err}")
        raise

def create_evaluation_template(template: EvaluationTemplate) -> EvaluationTemplate:
    """Saves a new EvaluationTemplate to the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO evaluation_templates (
                uuid, user_id, name, description, data_source_config,
                field_mapping_config, cached_data, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Serialize Pydantic models and lists to JSON strings
            data_source_config_str = template.data_source_config.model_dump_json()
            field_mapping_config_str = template.field_mapping_config.model_dump_json()
            cached_data_str = json.dumps(template.cached_data)

            cursor.execute(sql, (
                str(template.uuid),
                str(template.user_id),
                template.name,
                template.description,
                data_source_config_str,
                field_mapping_config_str,
                cached_data_str,
                template.created_at,
                template.updated_at
            ))
            conn.commit()
            return template
    except mysql.connector.Error as err:
        logger.error(f"Error creating evaluation template: {err}")
        conn.rollback()
        raise
    finally:
        conn.close()

def get_evaluation_template(template_uuid: UUID, user_id: UUID) -> Optional[EvaluationTemplate]:
    """Retrieves a single EvaluationTemplate from the database by its UUID."""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            sql = "SELECT * FROM evaluation_templates WHERE uuid = %s AND user_id = %s"
            cursor.execute(sql, (str(template_uuid), str(user_id)))
            row = cursor.fetchone()
            if row:
                return EvaluationTemplate(**row)
            return None
    except mysql.connector.Error as err:
        logger.error(f"Error getting evaluation template {template_uuid}: {err}")
        raise
    finally:
        conn.close()

def list_evaluation_templates(user_id: UUID) -> List[EvaluationTemplate]:
    """Lists all EvaluationTemplates for a given user."""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            sql = "SELECT * FROM evaluation_templates WHERE user_id = %s ORDER BY updated_at DESC"
            cursor.execute(sql, (str(user_id),))
            rows = cursor.fetchall()
            return [EvaluationTemplate(**row) for row in rows]
    except mysql.connector.Error as err:
        logger.error(f"Error listing evaluation templates for user {user_id}: {err}")
        return []
    finally:
        conn.close()
