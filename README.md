# Mini Interns

## Project Structure

```
mini-interns/
├── frontend/          # Next.js web interface for configuration
├── api/               # FastAPI backend for settings management
├── triggers/          # Email monitoring and LLM processing engine
├── agentlogger/       # Agent logging and anonymization package
├── shared/            # Common utilities and Redis client
├── data/              # Persistent storage (SQLite DB + Redis)
└── scripts/           # Database initialization and utilities
```

### Component Overview

- **`frontend/`** - Next.js TypeScript application providing a web UI for configuring IMAP settings, AI model parameters, system prompts, and trigger conditions
- **`api/`** - FastAPI REST API that manages application settings and agent configurations, storing them in Redis for real-time access
- **`triggers/`** - Core email processing engine that polls IMAP inbox, runs LLM workflows to analyze emails, and creates draft replies when conditions are met
- **`agentlogger/`** - Package providing client interface for agent logging and log anonymization functionality, used by other services within the container
- **`shared/`** - Common utilities including Redis client, configuration management, and shared data models used across all services
- **`data/`** - Persistent data storage with SQLite database for structured data and Redis for caching and real-time configuration. Will persist when Docker image is rebuild.
- **`scripts/`** - Database initialization scripts and other utility tools for system setup and maintenance

## Keeping everything internal: only exposing the frontend

The application is configured to keep the backend API private and only expose the frontend to external traffic. This is achieved through:

- **Next.js Proxy**: The frontend (`next.config.js`) rewrites all `/api/*` requests to the internal backend at `127.0.0.1:5001`
- **Single Port Exposure**: Only port 3000 (frontend) is exposed in Docker, while the backend runs internally on port 5001
- **API Client Configuration**: The frontend API client (`services/api.ts`) uses `/api` as the base URL, routing through the Next.js proxy

This setup ensures that:
- External users can only access the frontend interface
- All API communication happens internally within the Docker container
- The backend remains completely isolated from external network access

## Port Configuration

The host machine port that the Docker container maps to can be customized using the `FRONTEND_HOST_PORT` environment variable (defaults to 3000). This is useful when running multiple instances to avoid port conflicts:

```bash
FRONTEND_HOST_PORT=3001 docker compose up -d
```

## Testing MCP Servers

The application includes a visual MCP Inspector for testing and debugging MCP servers (the official FastMCP Inspector). 

### Accessing the MCP Inspector

1. **Check the Docker logs** for the inspector URL with authentication token (format `http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=[generated-token]`


### MCP Server Configuration

- **Internal Networking**: MCP servers are not bound to host machine ports - they run internally within the Docker container
- **Inspector Connection**: The MCP Inspector proxy connects to MCP servers internally using the format:
  ```
  http://localhost:[PORT]/mcp
  ```
- **Port Configuration**: MCP server ports can be configured in your `.env` file:
  ```env
  CONTAINERPORT_MCP_IMAP=8080
  # Add other MCP server ports as needed
  ```


