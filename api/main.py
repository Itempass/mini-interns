import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.endpoints import app_settings, agent, agentlogger, mcp, connection
from shared.config import settings
from shared.version import __version__, get_latest_version
import uvicorn

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
        
        # Check Inbox Vectorization status
        inbox_status = redis_client.get(RedisKeys.INBOX_INITIALIZATION_STATUS)
        if inbox_status == b'running':
            redis_client.set(RedisKeys.INBOX_INITIALIZATION_STATUS, "failed")
            logger.warning("Stale 'running' status for inbox vectorization found. Resetting to 'failed'.")
            
        # Check Tone of Voice status
        tone_status = redis_client.get(RedisKeys.TONE_OF_VOICE_STATUS)
        if tone_status == b'running':
            redis_client.set(RedisKeys.TONE_OF_VOICE_STATUS, "failed")
            logger.warning("Stale 'running' status for tone of voice analysis found. Resetting to 'failed'.")
            
    except Exception as e:
        logger.error(f"Error during startup status check: {e}", exc_info=True)
    
    yield


app = FastAPI(lifespan=lifespan)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(app_settings.router, tags=["app_settings"])
app.include_router(agent.router, tags=["agent"])
app.include_router(agentlogger.router, tags=["agentlogger"])
app.include_router(mcp.router, tags=["mcp"])
app.include_router(connection.router, tags=["connection"])

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