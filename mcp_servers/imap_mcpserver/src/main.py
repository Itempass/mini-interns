"""
FastAPI application for the IMAP MCP server.

This module creates a FastAPI application that mounts the FastMCP server,
providing the AI agent with access to the defined IMAP tools.
"""

import logging
import uvicorn
import os
from fastapi import FastAPI

from shared.config import settings
from .mcp_builder import mcp_builder
# This import is crucial as it registers the tools with the mcp_builder instance.
from . import tools 

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
log_format = '%(asctime)s - [imap_mcp_server] - %(name)s - %(levelname)s - %(message)s'
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
    port = settings.IMAP_MCP_PORT
    logger.info(f"Starting IMAP MCP server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
