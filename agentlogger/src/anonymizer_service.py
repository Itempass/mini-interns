"""
Anonymizer Service for Agent Logger
Handles automatic redaction of sensitive information using OpenRouter LLM API
"""

import os
import time
import logging
from typing import Dict, Any, Optional
import httpx
from shared.config import settings
from .models import LogEntry, Message

# Configure logging
logger = logging.getLogger(__name__)

# Configuration constants
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 1
REQUEST_TIMEOUT = 60

def _get_http_client() -> httpx.Client:
    """Setup HTTP client with timeout and retry configuration"""
    return httpx.Client(
        timeout=REQUEST_TIMEOUT,
        transport=httpx.HTTPTransport(retries=MAX_RETRIES)
    )

def _load_anonymization_system_prompt() -> str:
    """Load the anonymization system prompt from markdown file"""
    prompt_file = os.path.join(os.path.dirname(__file__), "anonymization_prompt.md")
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Failed to load anonymization prompt: {e}")
        raise

def anonymize_content(content: str) -> Optional[str]:
    """
    Anonymize a string using OpenRouter LLM API
    """
    if not content or not content.strip():
        return content

    headers = {
        "Authorization": f"Bearer {settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = _load_anonymization_system_prompt()
    
    payload = {
        "model": settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ],
        "temperature": 0.1,
        "max_tokens": len(content) + 500
    }
    
    try:
        with _get_http_client() as client:
            response = client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            if 'choices' in data and len(data['choices']) > 0:
                anonymized_content = data['choices'][0]['message']['content']
                logger.info(f"Content successfully anonymized (length: {len(content)} -> {len(anonymized_content)})")
                return anonymized_content.strip()
            else:
                logger.error(f"Unexpected API response structure: {data}")
                return None
                
    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.error(f"Anonymization failed: {e}")
        return None

def anonymize_message(message: Message) -> Optional[Message]:
    """
    Anonymize a single message model. If the message has no content, it is returned as is.
    """
    if not message.content:
        return message

    anonymized_content = anonymize_content(message.content)
    if anonymized_content is None:
        return None

    anonymized_data = message.model_dump()
    anonymized_data['content'] = anonymized_content
    return Message.model_validate(anonymized_data)

def anonymize_log_entry(log_entry: LogEntry) -> Optional[LogEntry]:
    """
    Anonymize an entire log entry by anonymizing its messages.
    If the log has no messages, it is returned as is.
    """
    if not log_entry.messages:
        return log_entry

    logger.info(f"Starting anonymization of log entry {log_entry.id} with {len(log_entry.messages)} messages")
    
    anonymized_messages = []
    for i, message in enumerate(log_entry.messages):
        logger.debug(f"Anonymizing message {i+1}/{len(log_entry.messages)}")
        
        anonymized_message = anonymize_message(message)
        if anonymized_message is None:
            logger.error(f"Failed to anonymize message {i+1} in log {log_entry.id}, aborting anonymization")
            return None
        
        anonymized_messages.append(anonymized_message)
    
    # Create a new LogEntry with the anonymized messages
    anonymized_log = log_entry.model_copy(deep=True)
    anonymized_log.messages = anonymized_messages
    anonymized_log.anonymized = True
    
    logger.info(f"Log entry {log_entry.id} anonymization completed successfully")
    return anonymized_log

def health_check() -> Dict[str, Any]:
    """
    Check the health of the anonymizer service.
    """
    try:
        api_key = settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY
        model = settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_MODEL
        configured = bool(api_key and model)
        
        return {
            "service": "anonymizer",
            "status": "healthy" if configured else "unhealthy",
            "configured": configured,
            "model": model,
            "timestamp": time.time(),
            "error": None if configured else "Missing required environment variables"
        }
    except Exception as e:
        return {
            "service": "anonymizer",
            "status": "unhealthy",
            "configured": False,
            "model": None,
            "timestamp": time.time(),
            "error": f"Configuration error: {e}"
        } 