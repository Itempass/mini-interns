# Port Configuration


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
