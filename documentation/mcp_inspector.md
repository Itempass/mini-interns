# MCP Inspector

## Accessing the MCP Inspector

1. **Check the Docker logs** for the inspector URL with authentication token (format `http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=[generated-token]`


## MCP Server Configuration

- **Internal Networking**: MCP servers are not bound to host machine ports - they run internally within the Docker container
- **Inspector Connection**: The MCP Inspector proxy connects to MCP servers internally using the format:
  ```
  http://0.0.0.0:[PORT]/mcp
  ```
- **Port Configuration**: MCP server ports can be configured in your `.env` file:
  ```env
  CONTAINERPORT_MCP_IMAP=8080
  # Add other MCP server ports as needed
  ```