"""Brain-OpenFang Bridge -- FastAPI application."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from bridge import space_agent_mapper
from bridge.config import settings
from bridge.router import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bridge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Bridge starting up...")
    logger.info(f"  Brain:    {settings.brain_url}")
    logger.info(f"  OpenFang: {settings.openfang_url}")
    space_agent_mapper.load()
    yield
    logger.info("Bridge shutting down.")


app = FastAPI(
    title="Brain-OpenFang Bridge",
    description="Routes Brain (Tahlamus) cognitive decisions to OpenFang agents with Claude Code.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "brain-openfang-bridge",
        "version": "0.1.0",
        "endpoints": [
            "POST /bridge/route",
            "GET  /bridge/tasks/{id}/status",
            "GET  /bridge/health",
            "GET  /bridge/mapping",
            "PUT  /bridge/mapping/reload",
        ],
    }


if __name__ == "__main__":
    uvicorn.run(
        "bridge.main:app",
        host="0.0.0.0",
        port=settings.bridge_port,
        reload=True,
    )
