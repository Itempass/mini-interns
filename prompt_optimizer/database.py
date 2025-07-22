import json
import logging
from typing import List, Optional
from uuid import UUID

import mysql.connector

from shared.config import settings
from .models import EvaluationTemplate, EvaluationTemplateLight, EvaluationRun
from datetime import timezone, datetime

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
                field_mapping_config, cached_data, created_at, updated_at,
                status, processing_error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                template.updated_at,
                template.status,
                template.processing_error
            ))
            conn.commit()
            return template
    except mysql.connector.Error as err:
        logger.error(f"Error creating evaluation template: {err}")
        conn.rollback()
        raise
    finally:
        conn.close()

def update_evaluation_template(template: EvaluationTemplate) -> EvaluationTemplate:
    """Updates an existing EvaluationTemplate in the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            UPDATE evaluation_templates SET
                name = %s,
                description = %s,
                data_source_config = %s,
                field_mapping_config = %s,
                cached_data = %s,
                updated_at = %s
            WHERE uuid = %s AND user_id = %s
            """
            
            # Serialize Pydantic models and lists to JSON strings
            data_source_config_str = template.data_source_config.model_dump_json()
            field_mapping_config_str = template.field_mapping_config.model_dump_json()
            cached_data_str = json.dumps(template.cached_data)

            cursor.execute(sql, (
                template.name,
                template.description,
                data_source_config_str,
                field_mapping_config_str,
                cached_data_str,
                template.updated_at,
                str(template.uuid),
                str(template.user_id)
            ))
            conn.commit()
            
            # Check if any row was actually updated
            if cursor.rowcount == 0:
                raise ValueError("Template not found or user not authorized to update.")

            return template
    except mysql.connector.Error as err:
        logger.error(f"Error updating evaluation template {template.uuid}: {err}")
        conn.rollback()
        raise
    finally:
        conn.close()

def update_template_snapshot_data(uuid: UUID, cached_data: list, status: str, error_message: Optional[str] = None):
    """Updates the cached_data, status, and processing_error fields for a specific template."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            UPDATE evaluation_templates SET
                cached_data = %s,
                status = %s,
                processing_error = %s,
                updated_at = %s
            WHERE uuid = %s
            """
            cursor.execute(sql, (
                json.dumps(cached_data),
                status,
                error_message,
                datetime.now(timezone.utc).isoformat(),
                str(uuid)
            ))
            conn.commit()
            logger.info(f"Successfully updated snapshot data for template {uuid}")
    except mysql.connector.Error as err:
        logger.error(f"Error updating template snapshot data for {uuid}: {err}")
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
                # Deserialize JSON string fields before creating the Pydantic model
                row['data_source_config'] = json.loads(row['data_source_config'])
                row['field_mapping_config'] = json.loads(row['field_mapping_config'])
                row['cached_data'] = json.loads(row['cached_data'])
                return EvaluationTemplate(**row)
            return None
    except mysql.connector.Error as err:
        logger.error(f"Error getting evaluation template {template_uuid}: {err}")
        raise
    finally:
        conn.close()

def list_evaluation_templates_light(user_id: UUID) -> List[EvaluationTemplateLight]:
    """Lists lightweight EvaluationTemplates for a given user, excluding heavy JSON fields."""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            sql = "SELECT uuid, user_id, name, description, updated_at FROM evaluation_templates WHERE user_id = %s ORDER BY updated_at DESC"
            cursor.execute(sql, (str(user_id),))
            rows = cursor.fetchall()
            return [EvaluationTemplateLight(**row) for row in rows]
    except mysql.connector.Error as err:
        logger.error(f"Error listing evaluation templates for user {user_id}: {err}")
        return []
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
            
            # Deserialize JSON string fields for each row before creating the Pydantic model
            parsed_rows = []
            for row in rows:
                row['data_source_config'] = json.loads(row['data_source_config'])
                row['field_mapping_config'] = json.loads(row['field_mapping_config'])
                row['cached_data'] = json.loads(row['cached_data'])
                parsed_rows.append(row)

            return [EvaluationTemplate(**row) for row in parsed_rows]
    except mysql.connector.Error as err:
        logger.error(f"Error listing evaluation templates for user {user_id}: {err}")
        return []
    finally:
        conn.close()


# --- Evaluation Run Functions ---

def create_evaluation_run(run: EvaluationRun) -> EvaluationRun:
    """Saves a new EvaluationRun to the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO evaluation_runs (
                uuid, user_id, template_uuid, original_prompt, original_model, status,
                summary_report, detailed_results, started_at, finished_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            summary_report_str = json.dumps(run.summary_report) if run.summary_report else None
            detailed_results_str = json.dumps(run.detailed_results) if run.detailed_results else None

            cursor.execute(sql, (
                str(run.uuid),
                str(run.user_id),
                str(run.template_uuid),
                run.original_prompt,
                run.original_model,
                run.status,
                summary_report_str,
                detailed_results_str,
                run.started_at,
                run.finished_at,
                run.created_at
            ))
            conn.commit()
            return run
    except mysql.connector.Error as err:
        logger.error(f"Error creating evaluation run: {err}")
        conn.rollback()
        raise
    finally:
        conn.close()


def update_evaluation_run(run: EvaluationRun) -> EvaluationRun:
    """Updates an existing EvaluationRun in the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            UPDATE evaluation_runs SET
                status = %s,
                summary_report = %s,
                detailed_results = %s,
                started_at = %s,
                finished_at = %s
            WHERE uuid = %s AND user_id = %s
            """
            
            summary_report_str = json.dumps(run.summary_report) if run.summary_report else None
            detailed_results_str = json.dumps(run.detailed_results) if run.detailed_results else None
            
            cursor.execute(sql, (
                run.status,
                summary_report_str,
                detailed_results_str,
                run.started_at,
                run.finished_at,
                str(run.uuid),
                str(run.user_id)
            ))
            conn.commit()

            if cursor.rowcount == 0:
                raise ValueError("EvaluationRun not found or user not authorized to update.")

            return run
    except mysql.connector.Error as err:
        logger.error(f"Error updating evaluation run {run.uuid}: {err}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_evaluation_run(run_uuid: UUID, user_id: UUID) -> Optional[EvaluationRun]:
    """Retrieves a single EvaluationRun from the database by its UUID."""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            sql = "SELECT * FROM evaluation_runs WHERE uuid = %s AND user_id = %s"
            cursor.execute(sql, (str(run_uuid), str(user_id)))
            row = cursor.fetchone()
            if row:
                # Deserialize JSON fields if they exist
                if row.get('summary_report'):
                    row['summary_report'] = json.loads(row['summary_report'])
                if row.get('detailed_results'):
                    row['detailed_results'] = json.loads(row['detailed_results'])

                # Convert created_at to timezone-aware if it's not
                if row.get('created_at') and row['created_at'].tzinfo is None:
                    row['created_at'] = row['created_at'].replace(tzinfo=timezone.utc)

                return EvaluationRun(**row)
            return None
    except mysql.connector.Error as err:
        logger.error(f"Error getting evaluation run {run_uuid}: {err}")
        raise
    finally:
        conn.close()
