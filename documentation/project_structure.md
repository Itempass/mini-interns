# Project Structure

## File Tree
```
mini-interns/
├── agent/             # Agent management system with models and database schema
├── agentlogger/       # Agent logging and anonymization package
├── api/               # FastAPI backend for settings management
├── data/              # Persistent storage (SQLite DB, Redis, Qdrant)
├── documentation/     # Project documentation, plans, and PR drafts
├── frontend/          # Next.js web interface for configuration
├── mcp_servers/       # MCP server implementations for different email providers
├── scripts/           # Database initialization and utilities
├── shared/            # Common utilities and Redis client
└── triggers/          # Email monitoring and LLM processing engine
```

## Component Overview

- **`agent/`** - Core agent management system providing models, database schema, and client interface for managing AI agents, instances, conversations, and trigger configurations
- **`agentlogger/`** - Package providing client interface for agent logging and log anonymization functionality, used by other services within the container
- **`api/`** - FastAPI REST API that manages application settings and agent configurations, storing them in Redis for real-time access
- **`data/`** - Persistent data storage with SQLite database for structured data, Redis for caching and real-time configuration, and Qdrant for vector storage. Will persist when Docker image is rebuild.
- **`documentation/`** - Project documentation including structure documentation, development plans, PR description drafts, and cursor prompts for development workflows
- **`frontend/`** - Next.js TypeScript application providing a web UI for configuring IMAP settings, AI model parameters, system prompts, and trigger conditions
- **`mcp_servers/`** - MCP (Model Context Protocol) server implementations for different email providers (IMAP, Gmail) with tools for email processing and management
- **`scripts/`** - Database initialization scripts and other utility tools for system setup and maintenance
- **`shared/`** - Common utilities including Redis client, configuration management, and shared data models used across all services
- **`triggers/`** - Core email processing engine that polls IMAP inbox, runs LLM workflows to analyze emails, and creates draft replies when conditions are met

