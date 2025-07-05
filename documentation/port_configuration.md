# Port Configuration

This project uses a flexible system for port configuration to avoid conflicts and allow for advanced setups. All ports can be configured using environment variables in your `.env` file.

## Host vs. Container Ports

For each service, you can configure two types of ports:

*   **`HOSTPORT_*`**: This is the port on your local machine (the "host") that you use to access a service. You can change this to any available port on your system.
*   **`CONTAINERPORT_*`**: This is the internal port that the service uses *inside* its Docker container. **You should generally not change this unless you have a specific reason to.**

For example, the frontend mapping is `"${HOSTPORT_FRONTEND:-3000}:${CONTAINERPORT_FRONTEND:-3000}"`. If you set `HOSTPORT_FRONTEND=3001` in your `.env` file, you can access the application at `http://localhost:3001`, while the application inside the container continues to run on port `3000`.

## Configurable Ports

Here is a complete list of all configurable ports. You can override any of these by adding the variable to your `.env` file.

| Service                     | Environment Variable                | Default Value | Description                                  |
| --------------------------- | ----------------------------------- | ------------- | -------------------------------------------- |
| **Frontend (Host)**         | `HOSTPORT_FRONTEND`                 | `3000`        | The port to access the web UI in your browser. |
| **Frontend (Container)**    | `CONTAINERPORT_FRONTEND`            | `3000`        | The internal port for the Next.js server.    |
| **Qdrant HTTP (Host)**      | `HOSTPORT_QDRANT`                   | `6333`        | The port to access the Qdrant dashboard.     |
| **Qdrant HTTP (Container)** | `CONTAINERPORT_QDRANT`              | `6333`        | The internal port for the Qdrant HTTP API.   |
| **Qdrant gRPC (Host)**      | `HOSTPORT_QDRANT_GRPC`              | `6334`        | The port for high-performance gRPC connections. |
| **Qdrant gRPC (Container)** | `CONTAINERPORT_QDRANT_GRPC`         | `6334`        | The internal port for the Qdrant gRPC API.   |
| **API Server (Container)**  | `CONTAINERPORT_API`                 | `8000`        | The internal port for the main backend API.  |
| **IMAP MCP (Container)**    | `CONTAINERPORT_MCP_IMAP`            | `8001`        | The internal port for the IMAP MCP server.   |
| **Tone MCP (Container)**    | `CONTAINERPORT_MCP_TONE_OF_VOICE`   | `8002`        | The internal port for the Tone MCP server.   |

### MCP Inspector

The MCP Inspector ports are hardcoded to `6274` (Web UI) and `6277` (Proxy) to simplify its use. The ports are commented out by default in `docker-compose.yaml` to prevent port conflicts.

To enable it:
1. Add the following variable to your `.env` file:
   ```
   ENABLE_MCP_INSPECTOR=true
   ```
2. Uncomment the MCP Inspector port lines in `docker-compose.yaml`:
   ```yaml
   - "6274:6274"  # MCP Inspector Web UI
   - "6277:6277"  # MCP Inspector Proxy Server
   ```
