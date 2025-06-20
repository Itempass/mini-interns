"""
FastAPI application for multi-tenant Gmail MCP server.

This module creates a FastAPI application that:
- Mounts a FastMCP server for handling MCP protocol messages
- Provides custom endpoints for session management (/register-session)  
- Handles user authentication via external Auth Portal
- Serves a test client for development/debugging

The architecture bridges FastMCP (designed for single-user) with multi-tenant 
requirements by using a dual-protocol approach: MCP protocol for tools + 
custom HTTP endpoints for session management.
"""

import asyncio
import json
import logging
import uvicorn
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from .mcp_builder import mcp_builder
from . import tools  # This will register the tools with mcp_builder
from .session_manager import SESSIONS, UserContext, fetch_token_from_auth_portal, cleanup_expired_sessions, get_session_stats, cleanup_session

# Configure logging - can be controlled by LOG_LEVEL environment variable
import os
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
log_format = '%(asctime)s - [gmail_mcp_server] - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=getattr(logging, log_level), format=log_format)
logger = logging.getLogger(__name__)

# Background task for session cleanup
async def session_cleanup_task():
    """Background task that runs every minute to cleanup expired sessions"""
    while True:
        try:
            cleanup_expired_sessions()
            await asyncio.sleep(60)  # Run every minute
        except Exception as e:
            print(f"[ERROR] Session cleanup task failed: {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Start background cleanup task
    cleanup_task = asyncio.create_task(session_cleanup_task())
    print("[STARTUP] Session cleanup task started")
    
    # Use MCP lifespan as well
    async with mcp_app.lifespan(app):
        yield
    
    # Cleanup on shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        print("[SHUTDOWN] Session cleanup task stopped")

# Create the MCP app first
mcp_app = mcp_builder.http_app(path="/", transport="streamable-http")

# Create FastAPI application with combined lifespan
app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Only log tool calls and important endpoints
    if request.url.path.startswith("/mcp"):
        session_id = request.headers.get('mcp-session-id', 'no-session')
        # We'll log basic info now, and try to capture more detail from the response
        logger.info(f"🔄 MCP REQUEST: {request.url.path} [session: {session_id[:8] if session_id != 'no-session' else 'new'}...]")
    
    elif request.url.path == "/register-session":
        session_id = request.headers.get('mcp-session-id', 'unknown')
        logger.info(f"🔐 SESSION REGISTER [session: {session_id[:8]}...]")
    
    # Process the request
    response = await call_next(request)
    return response

@app.get("/")
async def serve_test_client():
    return FileResponse('mcpserver_gmail/test-sse.html')

# Mount the MCP app
app.mount("/mcp", mcp_app)

@app.get("/health")
def health_check():
    """Health check endpoint with detailed session information"""
    return {
        "status": "ok", 
        "timestamp": datetime.utcnow().isoformat(),
        **get_session_stats()
    }

@app.post("/register-session")
async def register_session(session_data: UserContext, request: Request):
    """Register user info for an MCP session with authentication validation"""
    # Get the session ID from the header
    mcp_session_id = request.headers.get("mcp-session-id")
    
    if not mcp_session_id:
        raise HTTPException(status_code=400, detail="Missing mcp-session-id header")
    
    # Create user context
    user_context = UserContext(
        auth0_id=session_data.auth0_id,
        account_email=session_data.account_email
    )
    
    # Validate credentials by trying to fetch a token from the auth portal
    try:
        print(f"[SESSION] Validating credentials for {session_data.account_email}...")
        token = await fetch_token_from_auth_portal(user_context)
        print(f"[SESSION] Credentials validated successfully for {session_data.account_email}")
    except Exception as e:
        print(f"[SESSION] Credential validation failed for {session_data.account_email}: {str(e)}")
        raise HTTPException(
            status_code=401, 
            detail=f"Authentication failed: {str(e)}"
        )
    
    # Only store the session if authentication succeeded
    SESSIONS[mcp_session_id] = user_context
    
    print(f"[SESSION] Registered authenticated session {mcp_session_id} for user {session_data.account_email}")
    
    return {"status": "registered", "session_id": mcp_session_id, "authenticated": True}

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Manually delete a specific session"""
    if cleanup_session(session_id):
        return {"status": "deleted", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.post("/cleanup-sessions")
async def manual_cleanup():
    """Manually trigger cleanup of expired sessions"""
    removed = cleanup_expired_sessions()
    return {
        "status": "completed",
        "removed_sessions": removed,
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    port_str = os.getenv("GMAIL_MCP_PORT")
    if not port_str:
        logger.critical("FATAL: GMAIL_MCP_PORT environment variable is not set. The server cannot start.")
        raise ValueError("GMAIL_MCP_PORT environment variable must be set.")
    
    try:
        port = int(port_str)
    except ValueError:
        logger.critical(f"FATAL: Invalid GMAIL_MCP_PORT value: '{port_str}'. Must be an integer.")
        raise
        
    logger.info(f"Starting Gmail MCP server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
