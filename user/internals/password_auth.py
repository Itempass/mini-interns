import os
import hashlib
import hmac
from typing import Optional

from shared.security.encryption import encrypt_value, decrypt_value
from shared.config import settings

# Centralized constants for password-mode auth
AUTH_PASSWORD_FILE_PATH = "/data/keys/auth_password.key"
SESSION_SALT = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"


def _read_password_from_file() -> Optional[str]:
    if not os.path.exists(AUTH_PASSWORD_FILE_PATH):
        return None
    try:
        with open(AUTH_PASSWORD_FILE_PATH, mode='r') as f:
            encrypted_password = f.read().strip()
            if not encrypted_password:
                return None
            return decrypt_value(encrypted_password)
    except FileNotFoundError:
        return None


def _is_self_set_configured() -> bool:
    return os.path.exists(AUTH_PASSWORD_FILE_PATH)


def get_auth_configuration_status() -> str:
    if settings.AUTH_SELFSET_PASSWORD:
        return "self_set_configured" if _is_self_set_configured() else "self_set_unconfigured"
    if settings.AUTH_PASSWORD:
        return "legacy_configured"
    return "unconfigured"


def get_active_password() -> Optional[str]:
    if settings.AUTH_SELFSET_PASSWORD:
        return _read_password_from_file()
    return settings.AUTH_PASSWORD


def get_session_token(password: str) -> Optional[str]:
    if not password:
        return None
    token_source = f"{SESSION_SALT}-{password}"
    salt_bytes = SESSION_SALT.encode()
    token_source_bytes = token_source.encode()
    return hmac.new(salt_bytes, token_source_bytes, hashlib.sha256).hexdigest()


def verify_session_token(token: str) -> bool:
    active_password = get_active_password()
    if not active_password:
        return False
    expected = get_session_token(active_password)
    if expected is None:
        return False
    # Use compare_digest to avoid timing attacks
    return hmac.compare_digest(token, expected)


def set_password(new_password: str) -> None:
    os.makedirs(os.path.dirname(AUTH_PASSWORD_FILE_PATH), exist_ok=True)
    encrypted_password = encrypt_value(new_password)
    with open(AUTH_PASSWORD_FILE_PATH, mode='w') as f:
        f.write(encrypted_password)


def login(password: str) -> Optional[str]:
    active_password = get_active_password()
    if not active_password:
        return None
    if hmac.compare_digest(password, active_password):
        return get_session_token(active_password)
    return None


def get_auth_mode() -> str:
    # Explicitly check for non-empty string to avoid stale env vars
    if settings.AUTH0_DOMAIN and str(settings.AUTH0_DOMAIN).strip():
        return "auth0"
    if settings.AUTH_PASSWORD or settings.AUTH_SELFSET_PASSWORD:
        return "password"
    return "none"


