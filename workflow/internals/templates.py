import json
import os
from typing import Optional, Tuple, List, Dict, Any

from uuid import UUID

from workflow.models import (
    TemplateInfo,
    StarterChat,
    StarterChatOption,
)


# Fixed location per design feedback
TEMPLATES_DIR = os.path.join("workflow", "templates")


def _read_template_file(template_id: str) -> Dict[str, Any]:
    template_path = os.path.join(TEMPLATES_DIR, f"{template_id}.json")
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"Template with ID '{template_id}' not found at {template_path}")
    with open(template_path, "r") as f:
        return json.load(f)


def list_templates_on_disk() -> List[TemplateInfo]:
    if not os.path.isdir(TEMPLATES_DIR):
        return []
    templates: List[TemplateInfo] = []
    for filename in os.listdir(TEMPLATES_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(TEMPLATES_DIR, filename), "r") as f:
                data = json.load(f)
            templates.append(
                TemplateInfo(
                    id=filename[:-5],
                    name=data.get("name", "Unnamed Template"),
                    description=data.get("description", "No description available."),
                )
            )
        except Exception:
            # Skip malformed files silently; callers can log at a higher layer if needed
            continue
    return templates


def _parse_starter_chat(data: Dict[str, Any]) -> Optional[StarterChat]:
    starter_chat_data = data.get("starter_chat")
    if not isinstance(starter_chat_data, dict):
        return None
    mode = starter_chat_data.get("mode")
    message = starter_chat_data.get("message")
    if not isinstance(mode, str) or not isinstance(message, str):
        return None
    responses_list: List[StarterChatOption] = []
    raw_responses = starter_chat_data.get("responses") or []
    if isinstance(raw_responses, list):
        for r in raw_responses:
            if isinstance(r, dict) and isinstance(r.get("label"), str) and isinstance(r.get("message"), str):
                responses_list.append(StarterChatOption(label=r["label"], message=r["message"]))
    return StarterChat(mode=mode, message=message, responses=responses_list)


def read_and_parse_template(template_id: str) -> Tuple[Dict[str, Any], Optional[StarterChat]]:
    """Read template JSON and return raw dict plus parsed StarterChat if present."""
    template_data = _read_template_file(template_id)
    starter_chat = _parse_starter_chat(template_data)
    return template_data, starter_chat

