import logging
import os
from filelock import FileLock, Timeout
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

JWT_KEY_FILE_PATH = "/data/keys/jwt_secret.key"
_JWT_SECRET_KEY = None

ALGORITHM = "HS256"

def get_jwt_secret_key() -> str:
    """
    Retrieves the JWT secret key in a thread-safe and multi-process-safe manner.
    
    This logic mirrors the pattern in shared/security/encryption.py. It ensures
    a persistent, strong secret is generated once and reused.
    """
    global _JWT_SECRET_KEY
    if _JWT_SECRET_KEY:
        return _JWT_SECRET_KEY

    if os.path.exists(JWT_KEY_FILE_PATH):
        with open(JWT_KEY_FILE_PATH, "r") as key_file:
            key = key_file.read().strip()
        _JWT_SECRET_KEY = key
        return key

    lock_file_path = JWT_KEY_FILE_PATH + ".lock"
    
    try:
        logger.debug("Attempting to acquire JWT secret lock.")
        lock = FileLock(lock_file_path, timeout=10)
        with lock:
            logger.debug("JWT secret lock acquired.")
            # Re-check if the key was created while waiting for the lock.
            if os.path.exists(JWT_KEY_FILE_PATH):
                with open(JWT_KEY_FILE_PATH, "r") as key_file:
                    key = key_file.read().strip()
            else:
                logger.warning(f"No JWT secret key found. Generating a new one at {JWT_KEY_FILE_PATH}...")
                os.makedirs(os.path.dirname(JWT_KEY_FILE_PATH), exist_ok=True)
                key = secrets.token_hex(32) # A 256-bit random key
                with open(JWT_KEY_FILE_PATH, "w") as key_file:
                    key_file.write(key)
    except Timeout:
        logger.error(f"Could not acquire lock on {lock_file_path} after 10 seconds.")
        if os.path.exists(JWT_KEY_FILE_PATH):
            with open(JWT_KEY_FILE_PATH, "r") as key_file:
                key = key_file.read().strip()
        else:
            raise RuntimeError("Failed to obtain JWT secret key due to a persistent lock.")

    _JWT_SECRET_KEY = key
    return key 

def create_access_token(data: Dict[str, Any], expires_delta: timedelta = timedelta(days=7)) -> str:
    """
    Creates a new JWT access token.
    
    Args:
        data: The payload to include in the token.
        expires_delta: The lifespan of the token.
        
    Returns:
        The encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    
    secret_key = get_jwt_secret_key()
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validates and decodes a JWT access token.
    
    Args:
        token: The encoded JWT string.
        
    Returns:
        The decoded payload if the token is valid, otherwise None.
    """
    try:
        secret_key = get_jwt_secret_key()
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError as e:
        logger.error(f"JWT validation failed: {e}", exc_info=True)
        return None 