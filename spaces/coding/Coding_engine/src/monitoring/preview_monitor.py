"""
Preview Health Monitor Service

Continuously monitors the preview server health and notifies
the deployment team if it goes down.

Runs every 30 seconds, checking HTTP connectivity to the preview port.
On failure, publishes DEPLOY_FAILED event to trigger auto-recovery.
"""

import asyncio
from datetime import datetime
from typing import Optional

import httpx
import structlog

from src.mind.event_bus import EventBus, Event, EventType

logger = structlog.get_logger(__name__)


class PreviewHealthMonitor:
    """
    Monitors preview server health and triggers recovery on failure.

    Usage:
        monitor = PreviewHealthMonitor(event_bus, port=5173)
        await monitor.start()
        # ... runs in background ...
        await monitor.stop()
    """

    def __init__(
        self,
        event_bus: EventBus,
        port: int = 5173,
        check_interval: float = 30.0,
        timeout: float = 10.0,  # Increased from 5.0 for slow dev servers
        failure_threshold: int = 2,  # Consecutive failures before alerting
        working_dir: Optional[str] = None,
    ):
        """
        Initialize the preview health monitor.

        Args:
            event_bus: EventBus for publishing events
            port: Preview server port (default: 5173 for Vite)
            check_interval: Seconds between health checks (default: 30)
            timeout: HTTP request timeout in seconds (default: 10)
            failure_threshold: Consecutive failures before publishing event (default: 2)
            working_dir: Working directory for the project
        """
        self.event_bus = event_bus
        self.port = port
        self.check_interval = check_interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.working_dir = working_dir

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consecutive_failures = 0
        self._last_check_time: Optional[datetime] = None
        self._last_status: Optional[bool] = None
        self._total_checks = 0
        self._total_failures = 0

        self.logger = logger.bind(
            component="preview_health_monitor",
            port=port,
        )

        # Subscribe to port detection events for auto-update
        self.event_bus.subscribe(EventType.SERVER_PORT_DETECTED, self._on_port_detected)

    async def _on_port_detected(self, event) -> None:
        """Handle port detection event - only update for frontend ports.

        The preview health monitor tracks the frontend server (Vite/React),
        not backend APIs (Express). Backend health is monitored separately.
        """
        if not event.data:
            return

        new_port = event.data.get("port")
        port_type = event.data.get("port_type", "frontend")  # Default for backwards compatibility

        if not new_port:
            return

        # Only monitor frontend ports (the preview UI)
        if port_type != "frontend":
            self.logger.debug(
                "ignoring_backend_port_for_preview",
                port=new_port,
                port_type=port_type,
            )
            return

        if new_port != self.port:
            old_port = self.port
            self.port = new_port
            # Reset failure counter since we're now checking a different port
            self._consecutive_failures = 0
            self.logger.info(
                "port_updated_from_detection",
                old_port=old_port,
                new_port=new_port,
                port_type=port_type,
            )
            # Update logger binding
            self.logger = logger.bind(
                component="preview_health_monitor",
                port=new_port,
            )

    async def start(self) -> None:
        """Start the health monitoring loop."""
        if self._running:
            self.logger.warning("monitor_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

        self.logger.info(
            "preview_monitor_started",
            check_interval=self.check_interval,
            failure_threshold=self.failure_threshold,
        )

    async def stop(self) -> None:
        """Stop the health monitoring loop."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self.logger.info(
            "preview_monitor_stopped",
            total_checks=self._total_checks,
            total_failures=self._total_failures,
        )

    async def check_health(self) -> bool:
        """
        Check if the preview server is responding.

        Returns:
            True if server responds with status < 500, False otherwise
        """
        url = f"http://localhost:{self.port}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                # Consider 2xx, 3xx, 4xx as "alive" (server is responding)
                # Only 5xx or connection errors indicate server is down
                is_healthy = response.status_code < 500

                self.logger.debug(
                    "health_check_result",
                    url=url,
                    status=response.status_code,
                    healthy=is_healthy,
                )

                return is_healthy

        except httpx.ConnectError as e:
            self.logger.debug(
                "health_check_connection_error",
                url=url,
                error=str(e),
            )
            return False

        except httpx.TimeoutException:
            self.logger.debug(
                "health_check_timeout",
                url=url,
                timeout=self.timeout,
            )
            return False

        except Exception as e:
            self.logger.warning(
                "health_check_error",
                url=url,
                error=str(e),
            )
            return False

    async def _monitor_loop(self) -> None:
        """Main monitoring loop - runs until stopped."""
        self.logger.info("monitor_loop_starting")

        # Initial delay to let server start
        await asyncio.sleep(5.0)

        while self._running:
            try:
                # Perform health check
                self._total_checks += 1
                self._last_check_time = datetime.now()
                is_healthy = await self.check_health()
                self._last_status = is_healthy

                if is_healthy:
                    # Reset failure counter on success
                    if self._consecutive_failures > 0:
                        self.logger.info(
                            "preview_recovered",
                            previous_failures=self._consecutive_failures,
                        )
                    self._consecutive_failures = 0
                else:
                    # Increment failure counter
                    self._consecutive_failures += 1
                    self._total_failures += 1

                    self.logger.warning(
                        "preview_health_check_failed",
                        consecutive_failures=self._consecutive_failures,
                        threshold=self.failure_threshold,
                    )

                    # Publish event if threshold reached
                    if self._consecutive_failures >= self.failure_threshold:
                        await self._publish_failure_event()

                # Wait for next check
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "monitor_loop_error",
                    error=str(e),
                )
                await asyncio.sleep(self.check_interval)

        self.logger.info("monitor_loop_stopped")

    async def _publish_failure_event(self) -> None:
        """Publish DEPLOY_FAILED event to trigger recovery."""
        self.logger.warning(
            "publishing_deploy_failed_event",
            consecutive_failures=self._consecutive_failures,
            port=self.port,
        )

        event = Event(
            type=EventType.DEPLOY_FAILED,
            source="preview_health_monitor",
            data={
                "error_message": f"Preview server not responding on port {self.port}",
                "port": self.port,
                "action_required": "restart_preview",
                "consecutive_failures": self._consecutive_failures,
                "working_dir": self.working_dir,
                "timestamp": datetime.now().isoformat(),
            },
        )

        await self.event_bus.publish(event)

        self.logger.info(
            "deploy_failed_event_published",
            event_type=event.type.value,
        )

    @property
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running

    @property
    def status(self) -> dict:
        """Get current monitor status."""
        return {
            "running": self._running,
            "port": self.port,
            "check_interval": self.check_interval,
            "consecutive_failures": self._consecutive_failures,
            "last_check_time": self._last_check_time.isoformat() if self._last_check_time else None,
            "last_status": self._last_status,
            "total_checks": self._total_checks,
            "total_failures": self._total_failures,
        }


async def create_preview_monitor(
    event_bus: EventBus,
    port: int = 5173,
    check_interval: float = 30.0,
    working_dir: Optional[str] = None,
    auto_start: bool = True,
) -> PreviewHealthMonitor:
    """
    Factory function to create and optionally start a preview monitor.

    Args:
        event_bus: EventBus for publishing events
        port: Preview server port
        check_interval: Seconds between checks
        working_dir: Project working directory
        auto_start: Start monitoring immediately

    Returns:
        PreviewHealthMonitor instance
    """
    monitor = PreviewHealthMonitor(
        event_bus=event_bus,
        port=port,
        check_interval=check_interval,
        working_dir=working_dir,
    )

    if auto_start:
        await monitor.start()

    return monitor
