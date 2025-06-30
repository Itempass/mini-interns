import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.endpoints import app_settings, agent, agentlogger, mcp, connection
from shared.config import settings
from shared.version import __version__, get_latest_version
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI()

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

@app.on_event("startup")
def startup_event():
    # Add any additional startup logic here
    pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.CONTAINERPORT_API) 