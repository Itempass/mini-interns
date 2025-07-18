# Brewdock
*Brewdock, The Agents Factory*

Brewdock is a framework to manage **trigger-based agentic workflows**. Add triggers (eg. new incoming email), configure your agent (eg. label these emails as X), and improve based on past runs.


## Installation
### Compatibility
Only **gmail** (either personal or workspace) is supported. Support for Outlook and other email servers are on our roadmap.

### Prerequisites
- Make sure you have [Docker installed](https://docs.docker.com/engine/install/)
- Create an [Openrouter](https://openrouter.ai/) account and generate an API key.
- Create an [OpenAI API](https://platform.openai.com/) or [Voyage API](https://www.voyageai.com/) (recommended) account and generate an API key. These are used for embedding and retrieval.

### Installation steps using Terminal
1. In terminal, navigate to the folder where you'd like to install the project
2. Clone the project using `git clone https://github.com/Itempass/brewdock`
3. Navigate into the directory you just cloned using `cd brewdock`
4. Rename .env.example to .env (on Mac: `cp .env.example .env` | on Windows: `copy .env.example .env`)
5. Use `nano .env` to open the .env file
6. Add your `OPENROUTER_API_KEY`, and your `EMBEDDING_OPENAI_API_KEY` or `EMBEDDING_VOYAGE_API_KEY` (recommended).
7. Use `ctrl + x` to save your changes
8. Use `docker-compose up` to start the server. After a minute or two, you will be able to access the frontend at `http://localhost:3000/`

*Note: currently, using EMBEDDING_OPENAI_API_KEY skips the reranking algorithm when retrieving relevant emails. Hence, EMBEDDING_VOYAGE_API_KEY is recommended.*

### Updating an existing installation
1. In terminal, navigate to the folder containing the clone you made earlier (eg `cd Documents/brewdock`)
2. Use `docker-compose down` to stop the server, or stop it using [Docker for Desktop](https://www.docker.com/products/docker-desktop/)
3. Use `git pull` to update
4. Use `docker-compose up` to start the updated server

### Securing Your Installation
By default, your Brewdock instance is accessible to anyone on your network. It is highly recommended to secure your installation with a password. For detailed instructions on how to set up a password, please see the guide here: [**Securing Your Installation**](documentation/set_passwords.md)

## Feedback and Feature Requests

Don't hesitate to contact us on LinkedIn for feedback and feature requests!

* [@ArthurDevel](https://www.linkedin.com/in/arthurstockman/)
* [@roaldp](https://www.linkedin.com/in/roaldparmentier/)

## Roadmap

* 🛠️ Prompt optimizer
* 🛠️ AI prompt writer
* 🛠️ More triggers and integrations
* 🛠️ Better logging and traceability of your agents
* 🛠️ Support for Outlook and other email servers

## Project Structure

See [documentation/project_structure.md](documentation/project_structure.md) for high-level file tree with descriptions.

## Support the project with log-forwarding
**By default, all log-forwarding is turned OFF.**

You can contribute to the project by sharing your logs with the developers. Access is restricted to the core team, following least-privilege principles. 

- forwarding all backend logs -> set the .env variable `ENABLE_LOG_FORWARDING=true`
- forwarding anonimized agent logs -> will be implemented in future version

These logs are used to detect and fix bugs, improve agents workflows, and improve system prompts. These improvements are shared back with the community in future updates. 

## Port configuration
By default, the following host ports are used: 3000 (Frontend), 6333 (Qdrant), and 6334 (Qdrant gRPC). MCP Inspector ports (6274 and 6277) are commented out by default. These, and the internal container ports, can be fully customized. See [documentation/port_configuration.md](documentation/port_configuration.md) for a detailed explanation.

## MCP Inspector

As this project is heavily reliant on MCP, Anthropic's MCP Inspector Dashboard is included for easy debugging.

It is disabled by default. To enable it:
1. Add the following variable to your `.env` file:
   ```
   ENABLE_MCP_INSPECTOR=true
   ```
2. Uncomment the MCP Inspector port lines in `docker-compose.yaml`:
   ```yaml
   - "6274:6274"  # MCP Inspector Web UI
   - "6277:6277"  # MCP Inspector Proxy Server
   ```

See [documentation/mcp_inspector.md](documentation/mcp_inspector.md) for an explanation on how to use it.

## Startup Process

The application uses a managed startup sequence to ensure all services launch in the correct order and are properly initialized. This process is orchestrated by `supervisord` and defined in `supervisord.conf`.

The sequence is as follows:

1.  **Database Initialization (`scripts/init_db.py`)**: The `entrypoint.sh` script first runs this script to set up the necessary SQL database tables. This happens once before any other services are started.

2.  **Redis Server**: `supervisord` starts the Redis server with the highest priority to ensure it is available for other services.

3.  **API Pre-launch Scripts**: Before launching the main API server, `supervisord` executes two scripts:
    *   `scripts/clear_redis_on_startup.py`: Clears any transient data from previous sessions to ensure a clean start.
    *   `scripts/set_initial_embedding_model.py`: Detects available API keys and configures the optimal embedding model for the session.

4.  **API Server**: The main FastAPI application is launched with 4 worker processes.

5.  **Startup Orchestrator (`scripts/startup_orchestrator.py`)**: This crucial script runs *after* the API server is online. Its responsibilities are:
    *   To wait for both Redis and the API to be fully responsive.
    *   To check if the vectorization logic has been updated by comparing a version number in the code against the version stored in Redis from the last run.
    *   If the versions mismatch, it automatically triggers the re-vectorization process via an API call. This ensures the user's vectorized data is always in sync with the latest processing improvements without requiring manual intervention.

6.  **Other Services**: Finally, the `trigger` process and the `frontend` server are started.


