import asyncio
import logging
import os
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from fastmcp import Client
from mcp.types import Tool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class McpTool(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]


class McpServer(BaseModel):
    name: str
    port: int
    url: str
    tools: List[McpTool]


async def fetch_tools_from_server(name: str, port: int) -> McpServer:
    """Connects to an MCP server and fetches its tools."""
    url = f"http://localhost:{port}/mcp"
    logger.info(f"Connecting to MCP server '{name}' at {url}")
    try:
        async with Client(url) as client:
            mcp_tools: List[Tool] = await client.list_tools()
            logger.info(f"Found {len(mcp_tools)} tools for server '{name}'")

            # Convert fastmcp.types.Tool to McpTool
            tools = [McpTool(name=t.name, description=t.description, inputSchema=t.inputSchema) for t in mcp_tools]
            
            return McpServer(name=name, port=port, url=url, tools=tools)

    except Exception as e:
        logger.error(f"Could not connect to or fetch tools from MCP server '{name}' at {url}. Error: {e}")
        # Return a server object with an empty tool list to indicate it was found but unavailable
        return McpServer(name=name, port=port, url=url, tools=[])


@router.get("/mcp/servers", response_model=List[McpServer])
async def get_mcp_servers():
    """
    Discovers available MCP servers by scanning environment variables
    and lists the tools they provide.
    """
    mcp_servers_vars = {
        key: value
        for key, value in os.environ.items()
        if key.startswith("CONTAINERPORT_MCP_")
    }

    if not mcp_servers_vars:
        logger.warning("No MCP server environment variables found (e.g., CONTAINERPORT_MCP_IMAP).")
        return []

    tasks = []
    for key, port_str in mcp_servers_vars.items():
        try:
            port = int(port_str)
            # Extract server name from variable, e.g., CONTAINERPORT_MCP_IMAP -> IMAP
            name = key.replace("CONTAINERPORT_MCP_", "").lower()
            tasks.append(fetch_tools_from_server(name, port))
        except (ValueError, TypeError):
            logger.warning(f"Could not parse port for MCP server from environment variable: {key}={port_str}")
            continue

    discovered_servers = await asyncio.gather(*tasks)
    
    # Filter out servers that are unavailable or have no tools.
    active_servers = [s for s in discovered_servers if s and s.tools]

    logger.info(f"Successfully discovered {len(active_servers)} active MCP servers.")
    return active_servers 