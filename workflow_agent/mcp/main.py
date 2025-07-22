import os
import sys

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
import uvicorn
from fastapi import FastAPI

from shared.config import settings
from workflow_agent.mcp.mcp_builder import mcp_builder
# This import is crucial as it registers the tools with the mcp_builder instance.
import workflow_agent.mcp.tools

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
log_format = '%(asctime)s - [workflow_agent_mcp_server] - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=getattr(logging, log_level), format=log_format)
logger = logging.getLogger(__name__)

# Create and mount the MCP application
mcp_app = mcp_builder.http_app(path="/", transport="streamable-http")

# Create the main FastAPI application with FastMCP lifespan
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)

@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}

if __name__ == "__main__":
    # Note: We need to add a new port to the settings for this server.
    # For now, we will use a placeholder and add a TODO to fix it.
    port = settings.CONTAINERPORT_MCP_WORKFLOW_AGENT
    logger.info(f"Starting Workflow Agent MCP server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port) 