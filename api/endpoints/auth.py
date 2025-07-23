import os
from fastapi import APIRouter, Response, HTTPException, status, Depends, Request
from pydantic import BaseModel
import secrets
import hashlib
import hmac
from pathlib import Path
from uuid import uuid4, UUID
from typing import Optional
from datetime import datetime
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from shared.security.encryption import encrypt_value, decrypt_value
from shared.config import settings
from user import client as user_client
from user.models import User

# Create a new router for Auth0-specific endpoints
auth0_router = APIRouter(prefix="/auth", tags=["authentication-auth0"])

# Create a reusable dependency for getting the bearer token, but disable auto-error
reusable_bearer = HTTPBearer(auto_error=False)


# Keep the existing router for password-based and general auth endpoints
router = APIRouter(prefix="/auth", tags=["authentication"])

# --- New Configuration ---
AUTH_PASSWORD_FILE_PATH = "/data/keys/auth_password.key"

# Use a different cookie name for each auth method to prevent session bleed-over
if settings.AUTH_SELFSET_PASSWORD:
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
    if settings.AUTH_SELFSET_PASSWORD:
        if is_self_set_configured():
            return "self_set_configured"
        else:
            return "self_set_unconfigured"
    elif settings.AUTH_PASSWORD:
        return "legacy_configured"
    else:
        return "unconfigured"

async def get_active_password():
    """Gets the active password based on the configuration."""
    if settings.AUTH_SELFSET_PASSWORD:
        return await get_password_from_file()
    return settings.AUTH_PASSWORD

def get_session_token(password: str):
    """Generates a verification token based on a given password."""
    if not password:
        return None
    
    # This logic must exactly match the logic in the frontend middleware.
    token_source = f"{SESSION_SALT}-{password}"
    salt_bytes = SESSION_SALT.encode()
    token_source_bytes = token_source.encode()
    
    return hmac.new(salt_bytes, token_source_bytes, hashlib.sha256).hexdigest()


async def get_current_user(
    request: Request,
    token: Optional[HTTPAuthorizationCredentials] = Depends(reusable_bearer)
) -> User:
    """
    Primary dependency for user authentication.
    
    Resolves the current user based on the active authentication mode by
    validating an Auth0-vended JWT.
    
    This dependency makes all other services agnostic to the auth method.
    """
    print(f"[AUTH_DEBUG] Checking auth mode. settings.AUTH0_DOMAIN = '{settings.AUTH0_DOMAIN}' (Type: {type(settings.AUTH0_DOMAIN)})")
    print(f"[AUTH_DEBUG] get_current_user called.")

    # Explicitly check for a non-empty string to avoid issues with stale env vars.
    if settings.AUTH0_DOMAIN and settings.AUTH0_DOMAIN.strip():
        if token is None:
            print("[AUTH_DEBUG] Auth0 mode: Token is missing.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        print(f"[AUTH_DEBUG] Auth0 mode: Received token credentials: {token.credentials[:10]}...")
        
        from user.internals import auth0_validator
        
        payload = await auth0_validator.validate_auth0_token(token.credentials)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        auth0_sub = payload.get("sub")
        email = payload.get("email") # Get email from the validated token

        if not auth0_sub:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user subject",
            )
        
        # Find the user in our DB, or create them if it's their first time.
        user = user_client.find_or_create_user_by_auth0_sub(
            auth0_sub=auth0_sub,
            email=email
        )
        return user
    
    if settings.AUTH_PASSWORD or settings.AUTH_SELFSET_PASSWORD:
        # TODO: Get session cookie from request and validate it.
        # For now, we'll just return the default user if password auth is on.
        user = user_client.get_default_system_user()
        if not user:
             raise HTTPException(
                status_code=500,
                detail="Default system user not found in the database. A misconfiguration has occurred.",
            )
        return user

    # "No Auth" mode
    return User(
        uuid=UUID("12345678-1234-5678-9012-123456789012"),
        email="anonymous@example.com",
        created_at=datetime.utcnow()
    )


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

@router.get("/mode")
async def get_auth_mode():
    """
    Returns the active authentication mode for the entire application.
    This is used by the frontend to determine which authentication UI and
    logic to use.
    """
    # Explicitly check for a non-empty string to avoid issues with stale env vars.
    if settings.AUTH0_DOMAIN and settings.AUTH0_DOMAIN.strip():
        return {"mode": "auth0"}
    
    if settings.AUTH_PASSWORD or settings.AUTH_SELFSET_PASSWORD:
        return {"mode": "password"}
    
    return {"mode": "none"}

# Conditionally include the Auth0 router if Auth0 is enabled
# This logic is moved to api/main.py to prevent circular imports.
# if settings.AUTH0_DOMAIN:
#     from api.main import app as main_app
#     main_app.include_router(auth0_router)


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