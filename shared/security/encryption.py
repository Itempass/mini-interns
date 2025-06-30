import logging
import os
import time
from cryptography.fernet import Fernet
from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)

# Define the persistent path for the key file within a dedicated, mapped volume.
# The path must be absolute to ensure it's written into the volume mount,
# not into the application's relative working directory.
KEY_FILE_PATH = "/data/keys/secret.key"

_ENCRYPTION_KEY = None

def _generate_key() -> bytes:
    """Generates a new Fernet key."""
    return Fernet.generate_key()

def get_encryption_key() -> bytes:
    """
    Retrieves the encryption key in a thread-safe and multi-process-safe manner.
    
    It uses the `filelock` library to prevent race conditions during key generation
    when multiple processes start simultaneously.
    """
    pid = os.getpid()
    logger.info(f"[PID: {pid}] Requesting encryption key.")
    
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY:
        logger.info(f"[PID: {pid}] Returning cached key: {_ENCRYPTION_KEY[:8]}...")
        return _ENCRYPTION_KEY

    # The key is read outside the lock to allow for concurrent reads.
    # The lock is only for the critical section where the key might be created.
    if os.path.exists(KEY_FILE_PATH):
        logger.info(f"[PID: {pid}] Key file exists. Reading key from disk.")
        with open(KEY_FILE_PATH, "rb") as key_file:
            key = key_file.read()
        _ENCRYPTION_KEY = key
        logger.info(f"[PID: {pid}] Loaded key from disk: {key[:8]}...")
        return key

    lock_file_path = KEY_FILE_PATH + ".lock"
    
    try:
        # Create a lock object with a timeout to prevent indefinite hanging.
        logger.info(f"[PID: {pid}] Attempting to acquire lock: {lock_file_path}")
        lock = FileLock(lock_file_path, timeout=10)
        with lock:
            logger.info(f"[PID: {pid}] Lock acquired.")
            # Re-check if the key was created by another process while we were waiting for the lock.
            if os.path.exists(KEY_FILE_PATH):
                logger.info(f"[PID: {pid}] Key file now exists after acquiring lock. Reading.")
                with open(KEY_FILE_PATH, "rb") as key_file:
                    key = key_file.read()
            else:
                # We have the lock and the key still doesn't exist. It's our job to create it.
                logger.warning(f"[PID: {pid}] No encryption key found. Generating a new one at {KEY_FILE_PATH}...")
                os.makedirs(os.path.dirname(KEY_FILE_PATH), exist_ok=True)
                key = _generate_key()
                with open(KEY_FILE_PATH, "wb") as key_file:
                    key_file.write(key)
                logger.info(f"[PID: {pid}] New encryption key generated and saved: {key[:8]}...")
    except Timeout:
        logger.error(f"[PID: {pid}] Could not acquire lock on {lock_file_path} after 10 seconds. The application may be in an inconsistent state.")
        # If we time out, we should try one last time to read the key, as it might have been created
        # just as we timed out.
        if os.path.exists(KEY_FILE_PATH):
            with open(KEY_FILE_PATH, "rb") as key_file:
                key = key_file.read()
        else:
            # This is a critical failure. The app cannot proceed without a key.
            raise RuntimeError("Failed to obtain encryption key due to a persistent lock.")

    _ENCRYPTION_KEY = key
    logger.info(f"[PID: {pid}] Caching and returning key: {key[:8]}...")
    return key

def encrypt_value(value: str) -> str:
    """
    Encrypts a string value using the application's secret key.
    
    Args:
        value: The plaintext string to encrypt.
        
    Returns:
        The encrypted value as a URL-safe base64 encoded string.
    """
    if not value:
        return value
    key = get_encryption_key()
    f = Fernet(key)
    encrypted_value = f.encrypt(value.encode('utf-8'))
    return encrypted_value.decode('utf-8')

def decrypt_value(encrypted_value: str) -> str:
    """
    Decrypts a string value using the application's secret key.
    
    If the value is not a valid Fernet token, it is assumed to be
    a plaintext value from a previous installation and is returned as is.
    
    Args:
        encrypted_value: The encrypted, URL-safe base64 string.
        
    Returns:
        The decrypted plaintext string.
    """
    pid = os.getpid()
    if not encrypted_value:
        return encrypted_value
        
    key = get_encryption_key()
    f = Fernet(key)
    try:
        # Ensure value is bytes
        encrypted_bytes = encrypted_value.encode('utf-8')
        decrypted_value = f.decrypt(encrypted_bytes)
        logger.info(f"[PID: {pid}] Successfully decrypted value.")
        return decrypted_value.decode('utf-8')
    except Exception as e:
        # This can happen if the value is not encrypted (e.g., from a previous
        # version of the app) or if the key is wrong. We assume it's the former.
        logger.warning(f"[PID: {pid}] Failed to decrypt value: {e}. Returning it as plaintext. This may happen during migration from an unencrypted setup.")
        return encrypted_value 