import os
from fastapi import APIRouter, Response, HTTPException, status, Depends
from pydantic import BaseModel
import secrets
import hashlib
import hmac
from pathlib import Path

from shared.security.encryption import encrypt_value, decrypt_value

router = APIRouter(prefix="/auth", tags=["authentication"])

# --- New Configuration ---
AUTH_SELFSET_PASSWORD = os.getenv("AUTH_SELFSET_PASSWORD", "false").lower() == "true"
# Use an absolute path within the container that corresponds to the mounted volume
AUTH_PASSWORD_FILE_PATH = "/data/keys/auth_password.key"
LEGACY_AUTH_PASSWORD = os.getenv("AUTH_PASSWORD")

# Use a different cookie name for each auth method to prevent session bleed-over
if AUTH_SELFSET_PASSWORD:
    AUTH_COOKIE_NAME = "min_interns_auth_session_selfset"
else:
    AUTH_COOKIE_NAME = "min_interns_auth_session_legacy"

# This salt should be a fixed, random string to ensure hash consistency.
SESSION_SALT = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"

# --- Helper functions ---

async def get_password_from_file():
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

def is_self_set_configured():
    return os.path.exists(AUTH_PASSWORD_FILE_PATH)

def get_auth_configuration_status():
    if AUTH_SELFSET_PASSWORD:
        if is_self_set_configured():
            return "self_set_configured"
        else:
            return "self_set_unconfigured"
    elif LEGACY_AUTH_PASSWORD:
        return "legacy_configured"
    else:
        return "unconfigured"

async def get_active_password():
    """Gets the active password based on the configuration."""
    if AUTH_SELFSET_PASSWORD:
        return await get_password_from_file()
    return LEGACY_AUTH_PASSWORD

def get_session_token(password: str):
    """Generates a verification token based on a given password."""
    if not password:
        return None
    
    # This logic must exactly match the logic in the frontend middleware.
    token_source = f"{SESSION_SALT}-{password}"
    salt_bytes = SESSION_SALT.encode()
    token_source_bytes = token_source.encode()
    
    return hmac.new(salt_bytes, token_source_bytes, hashlib.sha256).hexdigest()


class LoginRequest(BaseModel):
    password: str

class SetPasswordRequest(BaseModel):
    password: str

class VerifyTokenRequest(BaseModel):
    token: str


@router.get("/status")
async def auth_status():
    """Returns the current authentication configuration status."""
    return {"status": get_auth_configuration_status()}

@router.post("/set-password")
async def set_password(request: SetPasswordRequest, response: Response):
    """
    Sets the password for the first time when in self-set mode.
    """
    if get_auth_configuration_status() != "self_set_unconfigured":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password has already been set or self-set mode is not enabled.",
        )
    
    if not request.password or len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )

    # Create directory if it doesn't exist, using the exact pattern from encryption.py
    os.makedirs(os.path.dirname(AUTH_PASSWORD_FILE_PATH), exist_ok=True)
    
    encrypted_password = encrypt_value(request.password)
    with open(AUTH_PASSWORD_FILE_PATH, mode='w') as f:
        f.write(encrypted_password)
    
    # Log the user in immediately
    session_token = get_session_token(request.password)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=True, 
        samesite='lax',
        max_age=31536000,
    )
    return {"message": "Password set successfully."}


@router.post("/verify")
async def verify_token(request: VerifyTokenRequest, active_password: str = Depends(get_active_password)):
    """
    Verifies if a session token is still valid against the current password.
    This is used by the middleware in self-set mode to ensure sessions are
    invalidated if the password changes.
    """
    if not active_password:
        return {"valid": False}

    expected_token = get_session_token(active_password)
    
    # Use a secure comparison to prevent timing attacks
    is_valid = secrets.compare_digest(request.token, expected_token)
    return {"valid": is_valid}


@router.post("/login")
async def login(request: LoginRequest, response: Response, active_password: str = Depends(get_active_password)):
    """
    Authenticate a user and set a session cookie.
    """
    auth_status = get_auth_configuration_status()

    if auth_status == "unconfigured":
         raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authentication is not enabled on the server.",
        )
    
    if auth_status == "self_set_unconfigured":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A password has not been set for the application yet.",
        )

    if active_password and secrets.compare_digest(request.password, active_password):
        # Password is correct, set a secure, http-only cookie
        # Cookie expires in 1 year (31536000 seconds)
        session_token = get_session_token(active_password)
        response.set_cookie(
            key=AUTH_COOKIE_NAME,
            value=session_token,
            httponly=True,
            secure=True, # Set to True in production
            samesite='lax',
            max_age=31536000,
        )
        return {"message": "Login successful"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        ) 