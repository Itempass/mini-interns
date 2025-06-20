"""
Session management and Gmail client creation for multi-tenant MCP server.

This module handles the core session management logic that enables multi-tenancy:
- Maintains in-memory user sessions (SESSIONS dict)
- Authenticates users via external Auth Portal
- Creates Gmail API clients for authenticated sessions
- Provides the key helper function get_gmail_from_context() that extracts
  session IDs from FastMCP request context and returns authenticated Gmail clients

This is the workaround that bridges FastMCP's single-user design with our
multi-tenant requirements by intercepting raw HTTP headers and mapping them
to user contexts.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field
from google.oauth2.credentials import Credentials
from fastmcp import Context

# --- New Imports ---
from shared.auth import google_manager
from shared.auth.google_manager import get_gmail_access_token, GoogleTokenError

# Set up logging
logger = logging.getLogger(__name__)

# In-memory storage for sessions
# Key: mcp_session_id, Value: UserContext  
SESSIONS = {}

class UserContext(BaseModel):
    auth0_id: str
    account_email: EmailStr
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    cached_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None

async def fetch_token_from_auth_portal(user_context: UserContext) -> str:
    """Fetch Gmail access token using the new shared authentication module."""
    logger.info(f"[AUTH] Fetching token for {user_context.account_email} using shared auth module.")
    try:
        access_token = await google_manager.get_gmail_access_token(
            auth0_id=user_context.auth0_id,
            user_email=user_context.account_email
        )
        if not access_token:
            raise ValueError("No access_token returned from the authentication service.")
        return access_token
    except GoogleTokenError as e:
        logger.error(f"Failed to get a new token for session {user_context.account_email}: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Could not retrieve a valid Google token.")
    except Exception as e:
        logger.error(f"An unexpected error occurred getting token for session {user_context.account_email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

async def get_cached_or_fresh_token(user_context: UserContext) -> str:
    """Get cached token if valid, otherwise fetch fresh token from Auth Portal"""
    # Check if we have a valid cached token
    if (user_context.cached_token and 
        user_context.token_expires_at and 
        datetime.utcnow() < user_context.token_expires_at):
        logger.debug(f"[TOKEN] Using cached token for {user_context.account_email}")
        return user_context.cached_token
    
    # Fetch fresh token and cache it
    logger.debug(f"[TOKEN] Fetching fresh token for {user_context.account_email}")
    token = await fetch_token_from_auth_portal(user_context)
    
    # Cache the token with 1-hour expiration (with 5-minute buffer)
    user_context.cached_token = token
    user_context.token_expires_at = datetime.utcnow() + timedelta(minutes=55)
    
    return token

async def ensure_session_authenticated(mcp_session_id: str):
    """Ensure the MCP session is authenticated"""
    if mcp_session_id in SESSIONS:
        return  # Already authenticated
    
    # If the session is not found, raise an error
    # The session should have been created during session registration
    raise ValueError(f"MCP session {mcp_session_id} not found. Please initialize MCP session with user credentials.")

def cleanup_session(mcp_session_id: str) -> bool:
    """Remove a session and cleanup its resources"""
    if mcp_session_id in SESSIONS:
        user_email = SESSIONS[mcp_session_id].account_email
        del SESSIONS[mcp_session_id]
        logger.info(f"[CLEANUP] Session {mcp_session_id} removed for {user_email}")
        return True
    return False

def cleanup_expired_sessions() -> int:
    """Remove sessions that have been inactive for more than 5 minutes"""
    cutoff_time = datetime.utcnow() - timedelta(minutes=5)
    expired_sessions = [
        session_id for session_id, user_context in SESSIONS.items()
        if user_context.last_activity < cutoff_time
    ]
    
    for session_id in expired_sessions:
        cleanup_session(session_id)
    
    if expired_sessions:
        logger.info(f"[CLEANUP] Removed {len(expired_sessions)} expired sessions")
    
    return len(expired_sessions)

def get_session_stats() -> Dict[str, Any]:
    """Get statistics about active sessions"""
    now = datetime.utcnow()
    stats = {
        "total_sessions": len(SESSIONS),
        "sessions": []
    }
    
    for session_id, user_context in SESSIONS.items():
        age_minutes = (now - user_context.last_activity).total_seconds() / 60
        
        # Show partial session ID for identification without security risk
        # Format: "95894...e4d" (first 5 + last 3 characters)
        partial_session_id = f"{session_id[:5]}...{session_id[-3:]}" if len(session_id) >= 8 else session_id
        
        stats["sessions"].append({
            "session_id": partial_session_id,
            "user_email": user_context.account_email,
            "created_at": user_context.created_at.isoformat(),
            "last_activity": user_context.last_activity.isoformat(),
            "age_minutes": round(age_minutes, 1),
            "has_cached_token": bool(user_context.cached_token),
            "token_expires_at": user_context.token_expires_at.isoformat() if user_context.token_expires_at else None
        })
    
    return stats

async def get_user_context_from_context(ctx: Context) -> UserContext:
    """
    Extract session ID from FastMCP context and return the user's session context.
    
    This provides access to user identity details like auth0_id.
    """
    try:
        request = ctx.request_context.request
        mcp_session_id = request.headers.get("mcp-session-id")
        
        if not mcp_session_id:
            raise ValueError("No MCP session ID found in request headers.")
            
    except Exception as e:
        raise ValueError(f"Failed to get session ID from context: {str(e)}")

    if mcp_session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="MCP session not found or not authenticated.")

    user_context = SESSIONS[mcp_session_id]
    user_context.last_activity = datetime.utcnow() # Update activity timestamp
    
    return user_context 