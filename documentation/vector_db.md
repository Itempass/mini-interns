# Vector Database

This project uses Qdrant as a vector database for storing and searching email embeddings. It runs as a **separate Docker container** (`mini-interns-qdrant`), completely isolated from external access.

## Container Isolation

- **Separate Container**: Qdrant runs in its own container (`qdrant` service) defined in `docker-compose.yaml`
- **Inter-Container Communication**: The main application container communicates with Qdrant internally using the hostname `qdrant` and port `6333` (gRPC)
- **Data Persistence**: Qdrant data is stored in `./data/qdrant` on the host and mounted into the container for persistence across container restarts

## Using the Qdrant Client

**All interaction with Qdrant must go through the shared client:**

```python
from shared.qdrant.qdrant_client import get_qdrant_client, semantic_search

# Get the configured Qdrant client
client = get_qdrant_client()

# Perform semantic search
results = semantic_search(
    collection_name="emails",
    query="your search query",
    user_email="user@example.com",
    top_k=5
)
```

The `shared.qdrant.qdrant_client` module handles all connection details, collection management, and provides convenience functions for common operations. Import this client in your services instead of creating direct Qdrant connections.

## Read-Only Debug Dashboard

For debugging purposes, a **read-only** version of the Qdrant web dashboard is exposed on the host machine at:

- **URL**: `http://localhost:6333/dashboard`

This is implemented via a secure Nginx reverse proxy that only allows safe, read-only operations:
- ✅ **Allowed**: `GET` requests (viewing collections, points, etc.) and read-only `POST` requests (searching, recommendations).
- ❌ **Blocked**: All write operations (`PUT`, `DELETE`, `PATCH`, etc.) are blocked, ensuring data cannot be accidentally modified or deleted from the UI.

**NOTE**: we still need to test that this is effectively blocked!