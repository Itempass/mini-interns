# This file ensures all tool modules are imported when the tools package is imported
# This allows the @mcp_builder.tool() decorators to register tools properly

from . import imap  # This will register all the Gmail tools with mcp_builder
