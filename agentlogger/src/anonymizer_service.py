"""
Anonymizer Service for EmailDrafter Agent Logger
Handles automatic redaction of sensitive information using OpenRouter LLM API
"""

import os
import time
import logging
from typing import Dict, Any, Optional
import httpx
from shared.config import settings
from .models import ConversationData, Message

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
    
    Args:
        content: The string to anonymize
        
    Returns:
        Anonymized content or None if failed
    """
    if not content or not content.strip():
        return content
    
    headers = {
        "Authorization": f"Bearer {settings.AGENTLOGGER_OPENROUTER_ANONIMIZER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/emaildrafter-agentlogger",
        "X-Title": "EmailDrafter Agent Logger Anonymizer"
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
    Anonymize a single message model
    
    Args:
        message: Message model with content field
        
    Returns:
        Anonymized message model or None if failed
    """
    anonymized_content = anonymize_content(message.content)
    if anonymized_content is None:
        return None
    
    # Create new message with anonymized content
    anonymized_data = message.model_dump()
    anonymized_data['content'] = anonymized_content
    return Message.model_validate(anonymized_data)

def anonymize_conversation(conversation_data: ConversationData) -> Optional[ConversationData]:
    """
    Anonymize an entire conversation
    
    Args:
        conversation_data: Complete conversation data model
        
    Returns:
        Fully anonymized conversation model or None if failed
    """
    messages = conversation_data.messages
    logger.info(f"Starting anonymization of conversation with {len(messages)} messages")
    
    anonymized_messages = []
    for i, message in enumerate(messages):
        logger.debug(f"Anonymizing message {i+1}/{len(messages)}")
        
        anonymized_message = anonymize_message(message)
        if anonymized_message is None:
            logger.error(f"Failed to anonymize message {i+1}, aborting conversation anonymization")
            return None
        
        anonymized_messages.append(anonymized_message)
    
    # Create anonymized conversation with metadata
    anonymized_data = conversation_data.model_dump()
    anonymized_data['messages'] = [msg.model_dump() for msg in anonymized_messages]
    
    # Add anonymization metadata
    if 'metadata' in anonymized_data:
        anonymized_data['metadata']['anonymization_status'] = 'success'
        anonymized_data['metadata']['anonymization_timestamp'] = time.time()
    
    logger.info("Conversation anonymization completed successfully")
    return ConversationData.model_validate(anonymized_data)

    """
    Check the health of the anonymizer service
    
    Returns:
        Health status information
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