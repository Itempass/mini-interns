import os
from fastapi import APIRouter, Response, HTTPException, status, Depends, Request
from pydantic import BaseModel
from uuid import uuid4, UUID
from typing import Optional
from datetime import datetime
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from shared.config import settings
from user import client as user_client
from user.models import User

# Create a new router for Auth0-specific endpoints
auth0_router = APIRouter(prefix="/auth", tags=["authentication-auth0"])

# Create a reusable dependency for getting the bearer token, but disable auto-error
reusable_bearer = HTTPBearer(auto_error=False)


# Keep the existing router for password-based and general auth endpoints
router = APIRouter(prefix="/auth", tags=["authentication"])

# Use a different cookie name for each auth method to prevent session bleed-over
if settings.AUTH_SELFSET_PASSWORD:
    AUTH_COOKIE_NAME = "min_interns_auth_session_selfset"
else:
    AUTH_COOKIE_NAME = "min_interns_auth_session_legacy"


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

    # Delegate auth mode decision to user client for centralization
    if user_client.get_auth_mode() == "auth0":
        if token is None:
            print("[AUTH_DEBUG] Auth0 mode: Token is missing.")
            print(f"[AUTH_DEBUG] Request details: client={request.client} headers={dict(request.headers)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        print(f"[AUTH_DEBUG] Auth0 mode: Received token credentials: {token.credentials[:10]}...")
        
        # Validate token via centralized user client helper
        payload = await user_client.validate_auth0_token(token.credentials)
        print(f"[AUTH_DEBUG] Decoded Auth0 token payload: {payload}")
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not payload or not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user subject",
            )
        
        # Resolve/find user from payload in centralized user client
        user = user_client.find_or_create_user_from_auth0_payload(payload)
        if not user:
             raise HTTPException(
                status_code=500,
                detail="Could not find or create user for the given Auth0 subject.",
            )
        return user
    
    # For both password-based auth and "no-auth" mode, we rely on a default user.
    # This ensures consistency and that a valid user object is always available.
    user = user_client.get_or_create_default_user()
    if not user:
        # This case should ideally not be reached if the get_or_create function works correctly.
        raise HTTPException(
            status_code=500,
            detail="Default system user could not be retrieved or created.",
        )
    return user


class LoginRequest(BaseModel):
    password: str

class SetPasswordRequest(BaseModel):
    password: str

class VerifyTokenRequest(BaseModel):
    token: str


@router.get("/status")
async def auth_status():
    """Returns the current authentication configuration status."""
    return {"status": user_client.get_auth_configuration_status()}

@router.get("/mode")
async def get_auth_mode():
    """
    Returns the active authentication mode for the entire application.
    This is used by the frontend to determine which authentication UI and
    logic to use.
    """
    return {"mode": user_client.get_auth_mode()}

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
    if user_client.get_auth_configuration_status() != "self_set_unconfigured":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password has already been set or self-set mode is not enabled.",
        )
    
    if not request.password or len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )

    # Set the password and log the user in immediately
    user_client.set_password(request.password)
    session_token = user_client.get_session_token(request.password)
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
async def verify_token(request: VerifyTokenRequest):
    """
    Verifies if a session token is still valid against the current password.
    This is used by the middleware in self-set mode to ensure sessions are
    invalidated if the password changes.
    """
    return {"valid": user_client.verify_session_token(request.token)}


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """
    Authenticate a user and set a session cookie.
    """
    auth_status = user_client.get_auth_configuration_status()

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

    session_token = user_client.login(request.password)
    if session_token:
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