"""
Dashboard Server - Serves the real-time dashboard and WebSocket events.

Provides:
1. HTTP server for dashboard static files
2. WebSocket server for real-time event streaming
3. Integration with EventBus for event broadcasting
"""

import asyncio
import json
import socket
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional, Set, Any, Tuple
from threading import Thread
import structlog

try:
    import websockets
    from websockets.server import serve as websocket_serve
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState, ConvergenceMetrics
from ..mind.convergence import get_progress_percentage, ConvergenceCriteria, DEFAULT_CRITERIA

logger = structlog.get_logger(__name__)


def _find_free_port(start_port: int, max_attempts: int = 10) -> int:
    """Find a free port starting from start_port.

    Args:
        start_port: Port to start searching from
        max_attempts: Maximum number of ports to try

    Returns:
        First available port found

    Raises:
        OSError: If no free port found in range
    """
    for i in range(max_attempts):
        port = start_port + i
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise OSError(f"No free port found in range {start_port}-{start_port + max_attempts - 1}")


def _find_free_ports(http_port: int, ws_port: int, max_attempts: int = 10) -> Tuple[int, int]:
    """Find free ports for both HTTP and WebSocket servers.

    Args:
        http_port: Preferred HTTP port
        ws_port: Preferred WebSocket port
        max_attempts: Maximum attempts per port

    Returns:
        Tuple of (http_port, ws_port)
    """
    actual_http = _find_free_port(http_port, max_attempts)
    actual_ws = _find_free_port(ws_port, max_attempts)
    return actual_http, actual_ws


class DashboardHTTPHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler for dashboard files."""

    def __init__(self, *args, dashboard_dir: str = None, **kwargs):
        self.dashboard_dir = dashboard_dir
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        """Translate URL path to filesystem path."""
        if self.dashboard_dir:
            if path == "/" or path == "":
                return str(Path(self.dashboard_dir) / "index.html")
            return str(Path(self.dashboard_dir) / path.lstrip("/"))
        return super().translate_path(path)

    def log_message(self, format: str, *args) -> None:
        """Suppress HTTP access logs."""
        pass


class DashboardServer:
    """
    Dashboard server with HTTP and WebSocket support.

    Serves:
    - Dashboard HTML at http://localhost:8080
    - WebSocket events at ws://localhost:8765
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        http_port: int = 9000,
        ws_port: int = 8765,
        criteria: Optional[ConvergenceCriteria] = None,
        preview_port: int = 5173,
    ):
        self.event_bus = event_bus
        self.shared_state = shared_state
        self.http_port = http_port
        self.ws_port = ws_port
        self.criteria = criteria or DEFAULT_CRITERIA
        self.preview_port = preview_port

        self._dashboard_dir = Path(__file__).parent
        self._http_server: Optional[HTTPServer] = None
        self._http_thread: Optional[Thread] = None
        self._ws_server: Optional[Any] = None
        self._ws_clients: Set[Any] = set()
        self._running = False

        self.logger = logger.bind(component="dashboard_server")

    async def start(self, open_browser: bool = True) -> None:
        """Start the dashboard server."""
        if not HAS_WEBSOCKETS:
            self.logger.warning("websockets_not_installed", msg="pip install websockets for dashboard")
            return

        self._running = True

        # Find free ports (auto-increment if ports are in use)
        try:
            self.http_port, self.ws_port = _find_free_ports(
                self.http_port, self.ws_port, max_attempts=10
            )
        except OSError as e:
            self.logger.error("no_free_ports", error=str(e))
            raise

        # Start HTTP server in thread
        self._start_http_server()

        # Start WebSocket server
        await self._start_ws_server()

        # Subscribe to all events
        self.event_bus.subscribe_all(self._on_event)

        # Subscribe to state changes
        self.shared_state.on_change(self._on_metrics_change)

        dashboard_url = f"http://localhost:{self.http_port}?ws={self.ws_port}"
        self.logger.info("dashboard_started", url=dashboard_url, ws_port=self.ws_port)

        # Open browser
        if open_browser:
            try:
                webbrowser.open(dashboard_url)
                self.logger.info("browser_opened", url=dashboard_url)
            except Exception as e:
                self.logger.warning("browser_open_failed", error=str(e))

    def _start_http_server(self) -> None:
        """Start HTTP server in background thread."""
        dashboard_dir = str(self._dashboard_dir)

        def handler(*args, **kwargs):
            return DashboardHTTPHandler(*args, dashboard_dir=dashboard_dir, **kwargs)

        self._http_server = HTTPServer(("", self.http_port), handler)
        self._http_thread = Thread(target=self._http_server.serve_forever, daemon=True)
        self._http_thread.start()

        self.logger.debug("http_server_started", port=self.http_port)

    async def _start_ws_server(self) -> None:
        """Start WebSocket server."""
        self._ws_server = await websocket_serve(
            self._ws_handler,
            "0.0.0.0",
            self.ws_port,
        )
        self.logger.debug("ws_server_started", port=self.ws_port)

    async def _ws_handler(self, websocket) -> None:
        """Handle WebSocket connections."""
        self._ws_clients.add(websocket)
        self.logger.debug("ws_client_connected", clients=len(self._ws_clients))

        try:
            # Send current state on connect
            await self._send_initial_state(websocket)

            # Keep connection alive
            async for message in websocket:
                # Handle any client messages (currently none expected)
                pass

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._ws_clients.discard(websocket)
            self.logger.debug("ws_client_disconnected", clients=len(self._ws_clients))

    async def _send_initial_state(self, websocket) -> None:
        """Send initial state to new client."""
        # Send preview URL
        await websocket.send(json.dumps({
            "type": "preview_url",
            "data": {"url": f"http://localhost:{self.preview_port}"},
        }))

        # Send current metrics
        metrics = self.shared_state.metrics
        progress = get_progress_percentage(metrics, self.criteria)
        await websocket.send(json.dumps({
            "type": "metrics",
            "data": {
                **metrics.to_dict(),
                "progress": progress,
            },
        }))

    def _on_event(self, event: Event) -> None:
        """Handle events from EventBus."""
        if not self._ws_clients:
            return

        message = json.dumps({
            "type": "event",
            "data": event.to_dict(),
        })

        # Broadcast to all clients
        asyncio.create_task(self._broadcast(message))

    async def _on_metrics_change(self, metrics: ConvergenceMetrics) -> None:
        """Handle metrics changes."""
        if not self._ws_clients:
            return

        progress = get_progress_percentage(metrics, self.criteria)
        message = json.dumps({
            "type": "metrics",
            "data": {
                **metrics.to_dict(),
                "progress": progress,
            },
        })

        await self._broadcast(message)

    async def _broadcast(self, message: str) -> None:
        """Broadcast message to all WebSocket clients."""
        if not self._ws_clients:
            return

        # Create tasks for all sends
        tasks = [
            asyncio.create_task(self._safe_send(client, message))
            for client in self._ws_clients
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, websocket, message: str) -> None:
        """Safely send message to websocket."""
        try:
            await websocket.send(message)
        except Exception:
            self._ws_clients.discard(websocket)

    async def send_agents_update(self, agents: list) -> None:
        """Send agents update to all clients."""
        if not self._ws_clients:
            return

        message = json.dumps({
            "type": "agents",
            "data": agents,
        })

        await self._broadcast(message)

    async def stop(self) -> None:
        """Stop the dashboard server."""
        self._running = False

        # Close WebSocket clients
        for client in list(self._ws_clients):
            try:
                await client.close()
            except Exception:
                pass
        self._ws_clients.clear()

        # Stop WebSocket server
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()

        # Stop HTTP server
        if self._http_server:
            self._http_server.shutdown()

        self.logger.info("dashboard_stopped")


async def start_dashboard(
    event_bus: EventBus,
    shared_state: SharedState,
    http_port: int = 9000,
    ws_port: int = 8765,
    preview_port: int = 5173,
    open_browser: bool = True,
    criteria: Optional[ConvergenceCriteria] = None,
) -> DashboardServer:
    """
    Convenience function to start the dashboard.

    Args:
        event_bus: EventBus for events
        shared_state: SharedState for metrics
        http_port: HTTP server port
        ws_port: WebSocket server port
        preview_port: App preview port
        open_browser: Open browser automatically
        criteria: Convergence criteria for progress calculation

    Returns:
        Running DashboardServer instance
    """
    server = DashboardServer(
        event_bus=event_bus,
        shared_state=shared_state,
        http_port=http_port,
        ws_port=ws_port,
        preview_port=preview_port,
        criteria=criteria,
    )
    await server.start(open_browser=open_browser)
    return server
