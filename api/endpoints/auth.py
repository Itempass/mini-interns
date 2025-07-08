import os
from fastapi import APIRouter, Response, HTTPException, status
from pydantic import BaseModel
import secrets
import hashlib
import hmac

router = APIRouter(prefix="/auth", tags=["authentication"])

AUTH_COOKIE_NAME = "min_interns_auth_session"
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD")
# This salt should be a fixed, random string to ensure hash consistency.
SESSION_SALT = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"

class LoginRequest(BaseModel):
    password: str

def get_session_token():
    """Generates a verification token based on the auth password."""
    if not AUTH_PASSWORD:
        return None
    
    # This logic must exactly match the logic in the frontend middleware.
    token_source = f"{SESSION_SALT}-{AUTH_PASSWORD}"
    salt_bytes = SESSION_SALT.encode()
    token_source_bytes = token_source.encode()
    
    return hmac.new(salt_bytes, token_source_bytes, hashlib.sha256).hexdigest()

@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """
    Authenticate a user and set a session cookie.
    """
    if not AUTH_PASSWORD:
        # This endpoint should not be used if auth is disabled
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authentication is not enabled on the server.",
        )

    if secrets.compare_digest(request.password, AUTH_PASSWORD):
        # Password is correct, set a secure, http-only cookie
        # Cookie expires in 1 year (31536000 seconds)
        session_token = get_session_token()
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