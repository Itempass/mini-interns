"""
Pydantic utility functions for the workflow engine.
"""
from pydantic import BaseModel
import logging
import json

logger = logging.getLogger(__name__)


def generate_simplified_json_schema(model: BaseModel) -> dict:
    """
    Generates a simplified JSON schema from a Pydantic model for LLM consumption.
    This version correctly introspects nested Pydantic models in the `raw_data` field.
    """
    logger.info(f"SCHEMA_DEBUG_UTIL: --- Generating schema for model of type: {type(model)} ---")
    
    # Start with a base schema for the container.
    schema = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A concise, human-readable summary of the data content."
            },
            "markdown_representation": {
                "type": "string",
                "description": "A long-form markdown version of the data, useful for summarization or analysis."
            }
        }
    }

    if not hasattr(model, 'raw_data'):
        logger.warning("SCHEMA_DEBUG_UTIL: Model has no 'raw_data' attribute.")
        return schema # Return base schema if no raw_data

    raw_data_instance = getattr(model, 'raw_data')
    logger.info(f"SCHEMA_DEBUG_UTIL: 'raw_data' attribute is of type: {type(raw_data_instance)}")


    # KEY FIX: Check if raw_data is a Pydantic model and generate its real schema.
    if isinstance(raw_data_instance, BaseModel):
        logger.info("SCHEMA_DEBUG_UTIL: 'raw_data' is a Pydantic BaseModel. Generating its full JSON schema.")
        raw_data_schema = raw_data_instance.model_json_schema()
        raw_data_schema["description"] = "The raw, structured data from the step."
        schema["properties"]["raw_data"] = raw_data_schema
    else:
        logger.info("SCHEMA_DEBUG_UTIL: 'raw_data' is NOT a Pydantic BaseModel. Using fallback logic for primitive types.")
        # Fallback for primitive types.
        raw_data_type = "string"
        if isinstance(raw_data_instance, dict):
            raw_data_type = "object"
        elif isinstance(raw_data_instance, list):
            raw_data_type = "array"
        elif isinstance(raw_data_instance, (int, float)):
            raw_data_type = "number"
        elif isinstance(raw_data_instance, bool):
            raw_data_type = "boolean"
        
        schema["properties"]["raw_data"] = {
            "type": raw_data_type,
            "description": "The raw, unstructured data from the step."
        }
        if raw_data_type == "object":
            schema["properties"]["raw_data"]["additionalProperties"] = True

    logger.info(f"SCHEMA_DEBUG_UTIL: --- Finished schema generation. Final schema: {json.dumps(schema, indent=2)} ---")
    return schema 