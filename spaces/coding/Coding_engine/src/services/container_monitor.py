"""
Container Health Monitor.

Polls Docker container health status and publishes events
to the EventBus when containers crash or become unhealthy.

The Orchestrator subscribes to APP_CRASHED events and dispatches
recovery to the DevOps-Bot via Discord #orchestrator channel.
"""

import asyncio
import logging
import subprocess
from typing import Optional

logger = logging.getLogger("container_monitor")

# Containers to monitor
MONITORED_CONTAINERS = [
    "coding-engine-api",
    "coding-engine-sandbox",
    "coding-engine-automation-ui",
    "coding-engine-openclaw",
    "coding-engine-postgres",
    "coding-engine-redis",
]


class ContainerHealthMonitor:
    """Polls container health and emits events on state changes."""

    def __init__(self, event_bus=None, check_interval: int = 60):
        self.event_bus = event_bus
        self.check_interval = check_interval
        self.running = False
        self._last_states = {}  # container_name → "healthy"|"unhealthy"|"exited"
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the monitor loop."""
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("ContainerHealthMonitor started, interval=%ds", self.check_interval)

    async def stop(self):
        """Stop the monitor."""
        self.running = False
        if self._task:
            self._task.cancel()

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                await self._check_all_containers()
            except Exception as e:
                logger.error("Monitor error: %s", e)

            await asyncio.sleep(self.check_interval)

    async def _check_all_containers(self):
        """Check health of all monitored containers."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                name, status = parts

                if name not in MONITORED_CONTAINERS:
                    continue

                # Determine state
                state = "unknown"
                status_lower = status.lower()
                if "healthy" in status_lower:
                    state = "healthy"
                elif "unhealthy" in status_lower:
                    state = "unhealthy"
                elif "exited" in status_lower:
                    state = "exited"
                elif "restarting" in status_lower:
                    state = "restarting"
                elif "up" in status_lower:
                    state = "running"

                prev_state = self._last_states.get(name, "unknown")

                # Detect state change
                if state != prev_state and prev_state != "unknown":
                    if state in ("exited", "unhealthy", "restarting"):
                        logger.warning("Container %s: %s → %s", name, prev_state, state)
                        await self._emit_crash(name, state, status)
                    elif state in ("healthy", "running") and prev_state in ("exited", "unhealthy", "restarting"):
                        logger.info("Container %s recovered: %s → %s", name, prev_state, state)
                        await self._emit_recovery(name, state)

                self._last_states[name] = state

        except subprocess.TimeoutExpired:
            logger.warning("Docker ps timed out")
        except FileNotFoundError:
            logger.warning("Docker CLI not found")

    async def _emit_crash(self, container: str, state: str, status: str):
        """Emit APP_CRASHED event."""
        # Get container logs
        logs = ""
        try:
            result = subprocess.run(
                ["docker", "logs", container, "--tail", "20"],
                capture_output=True, text=True, timeout=5,
            )
            logs = result.stdout[-500:] + result.stderr[-500:]
        except Exception:
            logs = "Could not fetch logs"

        if self.event_bus:
            try:
                from src.mind.event_bus import EventType
                await self.event_bus.publish(EventType.APP_CRASHED, {
                    "container": container,
                    "state": state,
                    "status": status,
                    "logs": logs,
                })
            except Exception as e:
                logger.error("Failed to emit crash event: %s", e)

    async def _emit_recovery(self, container: str, state: str):
        """Emit recovery event."""
        if self.event_bus:
            try:
                from src.mind.event_bus import EventType
                await self.event_bus.publish(EventType.DEPLOY_SUCCEEDED, {
                    "container": container,
                    "state": state,
                })
            except Exception as e:
                logger.error("Failed to emit recovery event: %s", e)

    def get_status(self) -> dict:
        """Get current container states."""
        return dict(self._last_states)
