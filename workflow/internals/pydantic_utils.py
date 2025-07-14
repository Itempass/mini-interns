"""
Pydantic utility functions for the workflow engine.
"""
from pydantic import BaseModel

def generate_simplified_json_schema(model: BaseModel) -> dict:
    """
    Generates a simplified JSON schema from a Pydantic model for LLM consumption.
    It exposes only `raw_data` and `markdown_representation`, simplifying the
    type information for clarity.
    """
    raw_data_type = "string" # Default
    if hasattr(model, 'raw_data'):
        raw_data_instance = model.raw_data
        if isinstance(raw_data_instance, dict):
            raw_data_type = "object"
        elif isinstance(raw_data_instance, list):
            raw_data_type = "array"
        elif isinstance(raw_data_instance, (int, float)):
            raw_data_type = "number"
        elif isinstance(raw_data_instance, bool):
            raw_data_type = "boolean"

    schema = {
        "type": "object",
        "properties": {
            "raw_data": {
                "type": raw_data_type
            },
            "markdown_representation": {
                "type": "string"
            }
        }
    }
    
    if raw_data_type == "object":
        schema["properties"]["raw_data"]["additionalProperties"] = True
        
    return schema 