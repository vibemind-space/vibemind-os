"""
Error Receiver Server

A lightweight HTTP server that receives JavaScript runtime errors
from the client-side error reporter and publishes them to the EventBus.

This enables automatic error detection for React apps even when:
- Playwright can't navigate to a crashed page
- Runtime errors don't appear in HTTP responses
- Error boundaries prevent full page crashes

Port: 8765 (configurable)

Usage:
    from src.monitoring.error_receiver_server import ErrorReceiverServer

    server = ErrorReceiverServer(event_bus)
    await server.start()
    # ... app runs ...
    await server.stop()
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional
from aiohttp import web

import structlog

logger = structlog.get_logger(__name__)


class ErrorReceiverServer:
    """
    HTTP server that receives browser error reports and publishes them to EventBus.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        port: int = 8765,
        host: str = "0.0.0.0",
    ):
        self.event_bus = event_bus
        self.port = port
        self.host = host
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

        # Track received errors
        self._error_buffer: list[dict] = []
        self._max_buffer_size = 100

        # Setup routes
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Configure HTTP routes."""
        self.app.router.add_post("/api/browser-errors", self._handle_errors)
        self.app.router.add_get("/api/browser-errors", self._get_errors)
        self.app.router.add_options("/api/browser-errors", self._handle_cors)
        self.app.router.add_get("/health", self._health_check)

        # Add CORS middleware
        self.app.middlewares.append(self._cors_middleware)

    @web.middleware
    async def _cors_middleware(
        self,
        request: web.Request,
        handler: Any,
    ) -> web.Response:
        """Add CORS headers to all responses."""
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    async def _handle_cors(self, request: web.Request) -> web.Response:
        """Handle CORS preflight requests."""
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    async def _handle_errors(self, request: web.Request) -> web.Response:
        """
        Receive error reports from the client-side error reporter.

        Expected JSON format:
        {
            "errors": [
                {
                    "type": "runtime_error" | "unhandled_rejection" | "react_error",
                    "message": "Error message",
                    "stack": "Error stack trace",
                    "filename": "/src/components/App.tsx",
                    "lineno": 42,
                    "colno": 15,
                    "componentStack": "React component stack (for react_error)",
                    "timestamp": "2025-01-26T10:30:00.000Z",
                    "url": "http://localhost:5173/",
                    "userAgent": "..."
                }
            ]
        }
        """
        try:
            data = await request.json()
            errors = data.get("errors", [])

            if not errors:
                return web.json_response(
                    {"status": "ok", "received": 0},
                    status=200,
                )

            logger.info(
                "received_browser_errors",
                count=len(errors),
                types=[e.get("type") for e in errors],
            )

            # Process each error
            for error in errors:
                await self._process_error(error)

            return web.json_response(
                {"status": "ok", "received": len(errors)},
                status=200,
            )

        except json.JSONDecodeError as e:
            logger.warning("invalid_json_payload", error=str(e))
            return web.json_response(
                {"status": "error", "message": "Invalid JSON"},
                status=400,
            )
        except Exception as e:
            logger.error("error_processing_request", error=str(e))
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500,
            )

    async def _process_error(self, error: dict) -> None:
        """Process a single error report and publish to EventBus."""
        # Add to buffer
        self._error_buffer.append({
            **error,
            "received_at": datetime.now().isoformat(),
        })

        # Trim buffer if needed
        if len(self._error_buffer) > self._max_buffer_size:
            self._error_buffer = self._error_buffer[-self._max_buffer_size:]

        # Publish to EventBus
        if self.event_bus:
            await self._publish_browser_error(error)

    async def _publish_browser_error(self, error: dict) -> None:
        """Publish a BROWSER_ERROR event to the EventBus."""
        try:
            from src.mind.event_bus import EventType, Event

            # Map error type to severity
            severity = "error"
            if error.get("type") == "react_error":
                severity = "critical"
            elif "warning" in error.get("message", "").lower():
                severity = "warning"

            # Extract file path from URL-style filename
            filename = error.get("filename", "")
            if filename.startswith("/src/"):
                filename = filename[1:]  # Remove leading slash

            await self.event_bus.publish(Event(
                type=EventType.BROWSER_ERROR,
                data={
                    "error_type": error.get("type", "runtime_error"),
                    "message": error.get("message", "Unknown error"),
                    "file_path": filename,
                    "line_number": error.get("lineno"),
                    "column_number": error.get("colno"),
                    "stack_trace": error.get("stack"),
                    "component_stack": error.get("componentStack"),
                    "severity": severity,
                    "url": error.get("url"),
                    "timestamp": error.get("timestamp"),
                    "source": "client_error_reporter",
                },
            ))

            logger.info(
                "published_browser_error",
                message=error.get("message", "")[:100],
                file=filename,
                line=error.get("lineno"),
            )

        except ImportError:
            logger.warning("event_bus_not_available")
        except Exception as e:
            logger.error("failed_to_publish_error", error=str(e))

    async def _get_errors(self, request: web.Request) -> web.Response:
        """Get buffered errors (for debugging/monitoring)."""
        limit = int(request.query.get("limit", "20"))
        return web.json_response({
            "errors": self._error_buffer[-limit:],
            "total": len(self._error_buffer),
        })

    async def _health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "port": self.port,
            "errors_received": len(self._error_buffer),
        })

    async def start(self) -> None:
        """Start the HTTP server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        logger.info(
            "error_receiver_server_started",
            host=self.host,
            port=self.port,
            endpoint=f"http://{self.host}:{self.port}/api/browser-errors",
        )

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        logger.info("error_receiver_server_stopped")

    def get_buffered_errors(self) -> list[dict]:
        """Get all buffered errors."""
        return self._error_buffer.copy()

    def clear_buffer(self) -> None:
        """Clear the error buffer."""
        self._error_buffer.clear()


# Singleton instance
_server_instance: Optional[ErrorReceiverServer] = None


async def start_error_receiver(
    event_bus: Optional[Any] = None,
    port: int = 8765,
) -> ErrorReceiverServer:
    """Start the global error receiver server."""
    global _server_instance

    if _server_instance is not None:
        return _server_instance

    _server_instance = ErrorReceiverServer(event_bus=event_bus, port=port)
    await _server_instance.start()

    return _server_instance


async def stop_error_receiver() -> None:
    """Stop the global error receiver server."""
    global _server_instance

    if _server_instance:
        await _server_instance.stop()
        _server_instance = None


def get_error_receiver() -> Optional[ErrorReceiverServer]:
    """Get the global error receiver server instance."""
    return _server_instance
