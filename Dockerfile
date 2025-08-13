# Stage 1: Build the Next.js frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend

# Accept CONTAINERPORT_API as a build argument and set it as an environment variable
ARG CONTAINERPORT_API
ENV CONTAINERPORT_API=${CONTAINERPORT_API}

COPY frontend/package*.json ./
RUN npm install && npm install zod
COPY frontend ./
RUN npm run build

# Stage 2: Setup Python environment and install dependencies
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    redis-server \
    supervisor \
    nodejs \
    npm \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install MCP Inspector globally
RUN npm install -g @modelcontextprotocol/inspector@0.14.3

# Copy Python requirements and install packages
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code in a specific order
COPY VERSION ./
COPY shared/ ./shared/
COPY agentlogger/ ./agentlogger/
COPY api/ ./api/
COPY mcp_servers/ ./mcp_servers/
COPY triggers/ ./triggers/
COPY workflow/ ./workflow/
COPY workflow_agent/ ./workflow_agent/
COPY user/ ./user/
COPY payments/ ./payments/
COPY prompt_optimizer/ ./prompt_optimizer/
COPY scripts/ ./scripts/
COPY promtail-config.yml .
COPY supervisord.conf .

# Copy the built frontend from the builder stage
COPY --from=frontend-builder /app/frontend/.next ./frontend/.next
COPY --from=frontend-builder /app/frontend/package.json ./frontend/package.json
COPY --from=frontend-builder /app/frontend/node_modules ./frontend/node_modules
COPY --from=frontend-builder /app/frontend/public ./frontend/public

# Make entrypoint script executable
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Create directories for persistent data
RUN mkdir -p /data/redis /data/db /data/keys

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports for frontend
EXPOSE 3000

# Define volumes for persistent data
VOLUME ["/data/redis", "/data/db", "/data/keys"]

# Set the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

# Start supervisor (this is passed as the command to the entrypoint)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"] 