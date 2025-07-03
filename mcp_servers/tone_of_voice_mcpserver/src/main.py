"""
FastAPI application for the Tone of Voice MCP server.

This module creates a FastAPI application that mounts the FastMCP server,
providing the AI agent with access to the defined tone of voice tools.
"""

import os
import sys

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
import uvicorn
from fastapi import FastAPI

from shared.config import settings
from mcp_servers.tone_of_voice_mcpserver.src.mcp_builder import mcp_builder
# This import is crucial as it registers the tools with the mcp_builder instance.
import mcp_servers.tone_of_voice_mcpserver.src.tools

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
log_format = '%(asctime)s - [tone_of_voice_mcp_server] - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=getattr(logging, log_level), format=log_format)
logger = logging.getLogger(__name__)

# Create and mount the MCP application
# This exposes all registered tools under the /mcp path.
mcp_app = mcp_builder.http_app(path="/", transport="streamable-http")

# Create the main FastAPI application with FastMCP lifespan
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)

@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}

if __name__ == "__main__":
    port = settings.CONTAINERPORT_MCP_TONE_OF_VOICE
    logger.info(f"Starting Tone of Voice MCP server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port) 