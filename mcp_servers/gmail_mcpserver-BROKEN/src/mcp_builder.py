"""
Shared FastMCP builder instance for Gmail MCP server.

This module provides a single, shared FastMCP builder instance that:
- Is imported by all tool modules to register their functions
- Maintains consistent MCP server configuration across the application
- Enables modular tool registration while keeping a unified MCP interface

The builder is configured for JSON responses and is used throughout the
application to register Gmail tools and create the MCP HTTP app.
"""

from fastmcp import FastMCP

# This is the single, shared builder instance that all tool modules will import.
mcp_builder = FastMCP(
    name="gmail-mcp-server-final",
    json_response=True
)