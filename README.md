# Mini Interns

Mini Interns is a framework to manage **trigger-based agentic workflows**. Add triggers (eg. new incoming email), configure your agent (eg. label these emails as X), and improve based on past runs.


## Installation
### Compatibility
Only **gmail** (either personal or workspace) is supported. Support for Outlook and other email servers are on our roadmap.

### Prerequisites
- Make sure you have [Docker installed](https://docs.docker.com/engine/install/)
- Create an [Openrouter](https://openrouter.ai/) account and generate an API key.
- Create an [OpenAI API](https://platform.openai.com/) or [Voyage API](https://www.voyageai.com/) (recommended) account and generate an API key. These are used for embedding and retrieval.

### Installation steps using Terminal
1. In terminal, navigate to the folder where you'd like to install the project
2. Clone the project using `git clone https://github.com/Itempass/mini-interns`
3. Navigate into the directory you just cloned using `cd mini-interns`
4. Rename .env.example to .env (on Mac: `cp .env.example .env` | on Windows: `copy .env.example .env`)
5. Use `nano .env` to open the .env file
6. Add your `OPENROUTER_API_KEY`, and your `EMBEDDING_OPENAI_API_KEY` or `EMBEDDING_VOYAGE_API_KEY` (recommended).
7. Use `ctrl + x` to save your changes
8. Use `docker-compose up` to start the server. After a minute or two, you will be able to access the frontend at `http://localhost:3000/`

*Note: currently, using EMBEDDING_OPENAI_API_KEY skips the reranking algorithm when retrieving relevant emails. Hence, EMBEDDING_VOYAGE_API_KEY is recommended.*

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

- forwarding all backend logs -> set the .env variable `DISABLE_LOG_FORWARDING=False`
- forwarding anonimized agent logs -> will be implemented in future version

These logs are used to detect and fix bugs, improve agents workflows, and improve system prompts. These improvements are shared back with the community in future updates. 

## Port configuration
By default, ports 3000, 6333, 6334, 6379, 8000, and 8001 are used. See [documentation/port_configuration.md](documentation/port_configuration.md) for a detailled explanation and customization options.

## MCP Inspector

As this project is heavily reliant on MCP, Anthropic's MCP Inspector Dashboard is included for easy debugging.

See [documentation/mcp_inspector.md](documentation/mcp_inspector.md) for an explanation on how to use it.


