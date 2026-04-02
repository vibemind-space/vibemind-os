"""Services Package for TRAE Backend

Contains all service modules for backend functionality.
"""

from ..core.websocket_manager import WebSocketManager
from .click_automation_service import ClickAutomationService
from .desktop_automation_service import DesktopAutomationService
from .graph_execution_service import (GraphExecutionService,
                                      get_graph_execution_service)
from .manager import ServiceManager
from .ocr_service import OCRService
from .shell_service import ShellService

# Export services
__all__ = [
    "ServiceManager",
    "DesktopAutomationService",
    "ClickAutomationService",
    "ShellService",
    "GraphExecutionService",
    "get_graph_execution_service",
    "get_service_manager",
    "get_websocket_manager",
    "get_ocr_service",
]


# Service getter functions
def get_desktop_automation_service() -> DesktopAutomationService:
    """Get DesktopAutomationService instance"""
    manager = get_service_manager()
    return manager.get_service("desktop_automation")


def get_click_automation_service() -> ClickAutomationService:
    """Get ClickAutomationService instance"""
    manager = get_service_manager()
    return manager.get_service("click_automation")


def get_shell_service() -> ShellService:
    """Get ShellService instance"""
    manager = get_service_manager()
    return manager.get_service("shell")


def get_websocket_manager() -> WebSocketManager:
    """Get WebSocketManager instance"""
    manager = get_service_manager()
    return manager.get_service("websocket_manager")


def get_ocr_service() -> OCRService:
    """Get OCRService instance"""
    manager = get_service_manager()
    return manager.get_service("ocr")


def get_service_manager() -> ServiceManager:
    """Get ServiceManager instance from FastAPI app state"""
    import contextvars

    from fastapi import Request
    from starlette.requests import Request as StarletteRequest

    # Try to get from FastAPI app context
    try:
        import inspect

        from fastapi.applications import FastAPI
        from fastapi.routing import APIRoute

        # Get the current request context if available
        frame = inspect.currentframe()
        while frame:
            if "request" in frame.f_locals and hasattr(
                frame.f_locals["request"], "app"
            ):
                app = frame.f_locals["request"].app
                if hasattr(app.state, "service_manager"):
                    return app.state.service_manager
            frame = frame.f_back

        # Fallback: create a new instance if not found in app state
        # This should only happen during startup or testing
        return ServiceManager()

    except Exception:
        # Final fallback
        return ServiceManager()
