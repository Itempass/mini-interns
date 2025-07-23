import logging
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api.endpoints import app_settings, agent, agentlogger, mcp, connection, auth, workflow, prompt_optimizer
from shared.config import settings
from shared.version import __version__, get_latest_version
import uvicorn

# Add project root to the Python path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On application startup, check for any background tasks that were
    in a "running" state and mark them as "failed" since they were
    interrupted by the server restart.
    """

    # TODO: Redis hasn't started yet, + this function runs for all 4 instances of our api!!


    from shared.redis.redis_client import get_redis_client
    from shared.redis.keys import RedisKeys

    logger = logging.getLogger(__name__)
    logger.info("Running startup checks for stale background tasks...")
    
    try:
        redis_client = get_redis_client()
        
        # --- Scan for and reset stale 'running' statuses for all users ---
        patterns_to_check = [
            "user:*:inbox:initialization:status",
            "user:*:tone_of_voice_status"
        ]
        
        for pattern in patterns_to_check:
            stale_keys = []
            for key in redis_client.scan_iter(match=pattern):
                if redis_client.get(key) == b'running':
                    stale_keys.append(key)
            
            if stale_keys:
                logger.warning(f"Found {len(stale_keys)} stale 'running' statuses for pattern '{pattern}'. Resetting to 'failed'.")
                for key in stale_keys:
                    redis_client.set(key, "failed")
            else:
                logger.info(f"No stale 'running' statuses found for pattern '{pattern}'.")

    except Exception as e:
        logger.error(f"Error during startup status check: {e}", exc_info=True)
    
    yield


app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    """
    This middleware runs for every request. It's the earliest point
    at which we can inspect the incoming request headers.
    """
    #print(f"[MIDDLEWARE_DEBUG] Request received: {request.method} {request.url.path}")
    #print(f"[MIDDLEWARE_DEBUG] Raw Headers: {request.headers}")
    response = await call_next(request)
    return response

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include the main auth router which has password-based and mode-selection endpoints
app.include_router(auth.router)

# Conditionally include the Auth0-specific router if Auth0 is enabled
if settings.AUTH0_DOMAIN:
    from api.endpoints.auth import auth0_router
    app.include_router(auth0_router)
    
app.include_router(app_settings.router, tags=["app_settings"])
app.include_router(agent.router, tags=["agent"])
app.include_router(agentlogger.router, tags=["agentlogger"])
app.include_router(mcp.router, tags=["mcp"])
app.include_router(connection.router, tags=["connection"])
app.include_router(workflow.router, tags=["workflow"])
app.include_router(prompt_optimizer.router, tags=["prompt_optimizer"])

@app.get("/version")
def get_app_version():
    return {"version": __version__}

@app.get("/version/latest")
async def get_latest_app_version():
    latest_version = await get_latest_version()
    return {"latest_version": latest_version}

@app.get("/")
def read_root():
    return {"message": "Welcome to the Agent API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.CONTAINERPORT_API)