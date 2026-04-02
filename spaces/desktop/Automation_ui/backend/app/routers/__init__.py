"""
API Routers Package for TRAE Backend

Contains all FastAPI router modules organized by functionality.
"""

from .api_v1 import router as api_v1_router
from .client_manager import router as client_manager_router
from .desktop import router as desktop_router
from .health import router as health_router
from .mcp_bridge import router as mcp_bridge_router
from .node_configs import router as node_configs_router
from .ocr import router as ocr_router
from .shell import router as shell_router
from .websocket import router as websocket_router
from .workflows import router as workflows_router

__all__ = [
    "health_router",
    "desktop_router",
    "websocket_router",
    "node_configs_router",
    "shell_router",
    "workflows_router",
    "api_v1_router",
    "ocr_router",
    "client_manager_router",
    "mcp_bridge_router",
]
