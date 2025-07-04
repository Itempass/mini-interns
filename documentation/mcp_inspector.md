# MCP Inspector

The MCP Inspector is a powerful debugging tool that is included in this project. It allows you to directly interact with the internal MCP servers.

## Enabling the Inspector

By default, the MCP Inspector is **disabled** to save resources.

To enable it, add the following line to your `.env` file and restart the application:
```env
ENABLE_MCP_INSPECTOR=true
```

## Accessing the Inspector

When enabled, the inspector runs on two fixed ports on your host machine:
*   **Web UI**: `http://localhost:6274`
*   **Proxy Server**: `http://localhost:6277`

For security, the inspector requires an authentication token. When you start the application with the inspector enabled, the full URL including the required token will be printed in your Docker logs. Look for a line similar to this:

```
🔗 Open inspector with token pre-filled:
   http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=[a-long-security-token]
```
Simply copy and paste this URL into your browser to get started.


## MCP Server Configuration

- **Internal Networking**: MCP servers are not bound to host machine ports - they run internally within the Docker container
- **Inspector Connection**: The MCP Inspector proxy connects to MCP servers internally using the format:
  ```
  http://0.0.0.0:[PORT]/mcp
  ```
  **IMPORTANT:** make sure to select streamable http!

- **Port Configuration**: MCP server ports can be configured in your `.env` file. See [/documentation/port_configuration.md](/documentation/port_configuration.md).