"""Health check endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as redis

from src.config import get_settings
from src.models.base import get_db

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Readiness check - verifies all dependencies are available.
    """
    status = {
        "status": "ready",
        "checks": {
            "database": "unknown",
            "redis": "unknown",
        }
    }

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        status["checks"]["database"] = "connected"
    except Exception as e:
        status["checks"]["database"] = f"error: {str(e)}"
        status["status"] = "not_ready"

    # Check Redis
    try:
        r = redis.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        status["checks"]["redis"] = "connected"
    except Exception as e:
        status["checks"]["redis"] = f"error: {str(e)}"
        status["status"] = "not_ready"

    return status


@router.get("/health/live")
async def liveness_check():
    """Liveness check - verifies the application is running."""
    return {"status": "alive"}
