"""WebSocket package for TRAE Backend

Provides WebSocket connection management and real-time communication.
"""

from .handlers import WebSocketHandler
from .manager import WebSocketManager

__all__ = ["WebSocketManager", "WebSocketHandler"]
