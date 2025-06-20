import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.endpoints import app_settings, agent, agentlogger
from shared.config import settings
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

app.include_router(app_settings.router)
app.include_router(agent.router)
app.include_router(agentlogger.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Agent API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.CONTAINERPORT_API) 