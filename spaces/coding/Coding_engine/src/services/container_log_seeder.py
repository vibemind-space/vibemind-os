"""
Container Log Seeder Service

Automatically captures and stores container logs when container lifecycle events occur.
Enables debugging agents to access historical logs for analysis.

Events Subscribed:
- SANDBOX_TEST_STARTED, SANDBOX_TEST_PASSED, SANDBOX_TEST_FAILED
- DEPLOY_STARTED, DEPLOY_SUCCEEDED, DEPLOY_FAILED
- DEV_CONTAINER_STARTED, DEV_CONTAINER_READY, DEV_CONTAINER_STOPPED

Events Published:
- SANDBOX_LOGS_COLLECTED
- DEPLOY_LOGS_COLLECTED
"""

import asyncio
import json
import os
import subprocess
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ContainerLogEntry:
    """A single container log capture entry."""
    container_id: str
    container_name: str
    timestamp: str
    event_type: str
    logs: str
    exit_code: Optional[int] = None
    health_status: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LogSeedResult:
    """Result of a log seeding operation."""
    success: bool
    container_id: str
    log_file_path: Optional[str] = None
    lines_captured: int = 0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ContainerLogSeeder:
    """
    Service that automatically captures container logs on lifecycle events.

    Features:
    - Automatic log capture on container start/stop/error events
    - Structured log storage in output_dir/logs/containers/
    - Log rotation (keeps last N logs per container)
    - Redis stream publishing for real-time log access
    - Index file for quick log lookup
    """

    def __init__(
        self,
        output_dir: str,
        event_bus: Optional[Any] = None,
        max_logs_per_container: int = 10,
        default_tail_lines: int = 500,
        redis_client: Optional[Any] = None,
    ):
        self.output_dir = Path(output_dir)
        self.logs_dir = self.output_dir / "logs" / "containers"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.event_bus = event_bus
        self.max_logs_per_container = max_logs_per_container
        self.default_tail_lines = default_tail_lines
        self.redis_client = redis_client

        # Index of captured logs
        self._log_index: Dict[str, List[str]] = {}
        self._load_index()

        # Track active subscriptions
        self._subscribed = False

    def _load_index(self) -> None:
        """Load log index from disk."""
        index_file = self.logs_dir / "index.json"
        if index_file.exists():
            try:
                with open(index_file, "r") as f:
                    self._log_index = json.load(f)
            except Exception as e:
                logger.warning("log_index_load_failed", error=str(e))
                self._log_index = {}

    def _save_index(self) -> None:
        """Save log index to disk."""
        index_file = self.logs_dir / "index.json"
        try:
            with open(index_file, "w") as f:
                json.dump(self._log_index, f, indent=2)
        except Exception as e:
            logger.warning("log_index_save_failed", error=str(e))

    def _run_docker_cmd(self, args: List[str], timeout: int = 30) -> tuple:
        """Run a docker CLI command."""
        try:
            use_shell = platform.system() == "Windows"
            cmd = ["docker"] + args

            result = subprocess.run(
                cmd if not use_shell else " ".join(cmd),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=use_shell
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s"
        except FileNotFoundError:
            return False, "Docker CLI not found"
        except Exception as e:
            return False, str(e)

    def _get_container_info(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Get container inspection info."""
        success, output = self._run_docker_cmd(["inspect", container_id])
        if not success:
            return None

        try:
            data = json.loads(output)
            if data and len(data) > 0:
                c = data[0]
                return {
                    "id": c.get("Id", "")[:12],
                    "name": c.get("Name", "").lstrip("/"),
                    "status": c.get("State", {}).get("Status", ""),
                    "exit_code": c.get("State", {}).get("ExitCode"),
                    "health": c.get("State", {}).get("Health", {}).get("Status"),
                    "image": c.get("Config", {}).get("Image", ""),
                    "created": c.get("Created", ""),
                }
        except json.JSONDecodeError:
            pass
        return None

    def _capture_logs(self, container_id: str, tail: int = None) -> tuple:
        """Capture logs from a container."""
        tail = tail or self.default_tail_lines
        success, output = self._run_docker_cmd(
            ["logs", "--tail", str(tail), "--timestamps", container_id]
        )
        return success, output

    async def seed_container_logs(
        self,
        container_id: str,
        event_type: str,
        tail_lines: int = None,
        extra_context: Dict[str, Any] = None,
    ) -> LogSeedResult:
        """
        Capture and store logs from a container.

        Args:
            container_id: Container ID or name
            event_type: The event that triggered log capture
            tail_lines: Number of log lines to capture
            extra_context: Additional context to store with logs

        Returns:
            LogSeedResult with capture status
        """
        logger.info(
            "seeding_container_logs",
            container_id=container_id,
            event_type=event_type
        )

        # Get container info
        container_info = self._get_container_info(container_id)
        container_name = container_info.get("name", container_id) if container_info else container_id

        # Capture logs
        success, logs = self._capture_logs(container_id, tail_lines)

        if not success:
            logger.warning(
                "container_logs_capture_failed",
                container_id=container_id,
                error=logs
            )
            return LogSeedResult(
                success=False,
                container_id=container_id,
                error=logs
            )

        # Create log entry
        timestamp = datetime.now().isoformat()
        safe_timestamp = timestamp.replace(":", "-").replace(".", "-")

        log_entry = ContainerLogEntry(
            container_id=container_id[:12] if len(container_id) > 12 else container_id,
            container_name=container_name,
            timestamp=timestamp,
            event_type=event_type,
            logs=logs,
            exit_code=container_info.get("exit_code") if container_info else None,
            health_status=container_info.get("health") if container_info else None,
        )

        # Create container-specific directory
        container_log_dir = self.logs_dir / container_name
        container_log_dir.mkdir(parents=True, exist_ok=True)

        # Save log file
        log_filename = f"{safe_timestamp}_{event_type}.json"
        log_file_path = container_log_dir / log_filename

        try:
            with open(log_file_path, "w", encoding="utf-8") as f:
                json.dump({
                    **log_entry.to_dict(),
                    "extra_context": extra_context or {},
                    "container_info": container_info,
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("log_file_write_failed", error=str(e))
            return LogSeedResult(
                success=False,
                container_id=container_id,
                error=str(e)
            )

        # Update index
        if container_name not in self._log_index:
            self._log_index[container_name] = []

        self._log_index[container_name].append(str(log_file_path))

        # Rotate old logs if needed
        self._rotate_logs(container_name)

        # Save index
        self._save_index()

        # Publish to Redis stream if available
        if self.redis_client:
            try:
                await self._publish_to_redis(container_name, log_entry, extra_context)
            except Exception as e:
                logger.warning("redis_publish_failed", error=str(e))

        # Publish event bus event
        if self.event_bus:
            await self._publish_logs_collected_event(
                container_id, container_name, event_type, str(log_file_path), len(logs.split("\n"))
            )

        lines_captured = len(logs.split("\n"))
        logger.info(
            "container_logs_seeded",
            container_id=container_id,
            container_name=container_name,
            lines_captured=lines_captured,
            log_file=str(log_file_path)
        )

        return LogSeedResult(
            success=True,
            container_id=container_id,
            log_file_path=str(log_file_path),
            lines_captured=lines_captured
        )

    def _rotate_logs(self, container_name: str) -> None:
        """Remove old logs beyond max_logs_per_container."""
        if container_name not in self._log_index:
            return

        log_files = self._log_index[container_name]
        if len(log_files) > self.max_logs_per_container:
            # Remove oldest logs
            files_to_remove = log_files[:-self.max_logs_per_container]
            for file_path in files_to_remove:
                try:
                    Path(file_path).unlink(missing_ok=True)
                    logger.debug("rotated_old_log", file=file_path)
                except Exception as e:
                    logger.warning("log_rotation_failed", file=file_path, error=str(e))

            # Update index
            self._log_index[container_name] = log_files[-self.max_logs_per_container:]

    async def _publish_to_redis(
        self,
        container_name: str,
        log_entry: ContainerLogEntry,
        extra_context: Dict[str, Any] = None
    ) -> None:
        """Publish log entry to Redis stream for real-time access."""
        stream_key = f"container_logs:{container_name}"

        # Truncate logs for Redis (keep last 100 lines)
        log_lines = log_entry.logs.split("\n")
        truncated_logs = "\n".join(log_lines[-100:])

        await self.redis_client.xadd(
            stream_key,
            {
                "timestamp": log_entry.timestamp,
                "event_type": log_entry.event_type,
                "logs": truncated_logs,
                "exit_code": str(log_entry.exit_code or ""),
                "health_status": log_entry.health_status or "",
                "context": json.dumps(extra_context or {}),
            },
            maxlen=100  # Keep last 100 entries per container
        )

    async def _publish_logs_collected_event(
        self,
        container_id: str,
        container_name: str,
        event_type: str,
        log_file_path: str,
        lines_captured: int
    ) -> None:
        """Publish LOGS_COLLECTED event to EventBus."""
        from src.mind.event_bus import EventType, Event

        # Determine which event type to publish based on source event
        if "SANDBOX" in event_type.upper():
            publish_event = EventType.SANDBOX_LOGS_COLLECTED
        elif "DEPLOY" in event_type.upper():
            publish_event = EventType.DEPLOY_LOGS_COLLECTED
        else:
            publish_event = EventType.SANDBOX_LOGS_COLLECTED  # Default

        await self.event_bus.publish(Event(
            type=publish_event,
            data={
                "container_id": container_id,
                "container_name": container_name,
                "source_event": event_type,
                "log_file": log_file_path,
                "lines_captured": lines_captured,
                "timestamp": datetime.now().isoformat(),
            }
        ))

    async def subscribe_to_events(self) -> None:
        """Subscribe to container lifecycle events."""
        if not self.event_bus or self._subscribed:
            return

        from src.mind.event_bus import EventType

        # Events that should trigger log capture
        trigger_events = [
            EventType.SANDBOX_TEST_STARTED,
            EventType.SANDBOX_TEST_PASSED,
            EventType.SANDBOX_TEST_FAILED,
            EventType.DEPLOY_STARTED,
            EventType.DEPLOY_SUCCEEDED,
            EventType.DEPLOY_FAILED,
            EventType.DEV_CONTAINER_STARTED,
            EventType.DEV_CONTAINER_READY,
            EventType.DEV_CONTAINER_STOPPED,
        ]

        for event_type in trigger_events:
            self.event_bus.subscribe(event_type, self._handle_container_event)

        self._subscribed = True
        logger.info("container_log_seeder_subscribed", events=len(trigger_events))

    async def _handle_container_event(self, event: Any) -> None:
        """Handle container lifecycle events and seed logs."""
        container_id = event.data.get("container_id") or event.data.get("container")

        if not container_id:
            logger.debug("no_container_id_in_event", event_type=event.type)
            return

        # Extract extra context from event
        extra_context = {
            k: v for k, v in event.data.items()
            if k not in ("container_id", "container", "logs")
        }

        # Seed logs
        await self.seed_container_logs(
            container_id=container_id,
            event_type=str(event.type.value if hasattr(event.type, 'value') else event.type),
            extra_context=extra_context
        )

    def get_latest_logs(self, container_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get the latest log entries for a container.

        Args:
            container_name: Container name to get logs for
            limit: Maximum number of log entries to return

        Returns:
            List of log entries (most recent first)
        """
        if container_name not in self._log_index:
            return []

        log_files = self._log_index[container_name][-limit:]
        log_files.reverse()  # Most recent first

        entries = []
        for file_path in log_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    entries.append(json.load(f))
            except Exception as e:
                logger.warning("log_read_failed", file=file_path, error=str(e))

        return entries

    def get_all_containers(self) -> List[str]:
        """Get list of all containers with seeded logs."""
        return list(self._log_index.keys())

    def search_logs(
        self,
        pattern: str,
        container_name: str = None,
        event_type: str = None
    ) -> List[Dict[str, Any]]:
        """
        Search logs for a pattern.

        Args:
            pattern: Text pattern to search for
            container_name: Optional filter by container
            event_type: Optional filter by event type

        Returns:
            List of matching log entries with matched lines highlighted
        """
        results = []

        containers = [container_name] if container_name else self.get_all_containers()

        for container in containers:
            if container not in self._log_index:
                continue

            for file_path in self._log_index[container]:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        entry = json.load(f)

                    # Filter by event type if specified
                    if event_type and entry.get("event_type") != event_type:
                        continue

                    # Search in logs
                    logs = entry.get("logs", "")
                    if pattern.lower() in logs.lower():
                        # Extract matching lines
                        matching_lines = [
                            line for line in logs.split("\n")
                            if pattern.lower() in line.lower()
                        ]

                        results.append({
                            "container_name": container,
                            "log_file": file_path,
                            "event_type": entry.get("event_type"),
                            "timestamp": entry.get("timestamp"),
                            "matching_lines": matching_lines[:10],  # Limit to 10 matches
                            "total_matches": len(matching_lines),
                        })
                except Exception as e:
                    logger.warning("log_search_error", file=file_path, error=str(e))

        return results


# Singleton instance for global access
_seeder_instance: Optional[ContainerLogSeeder] = None


def get_container_log_seeder(
    output_dir: str = None,
    event_bus: Any = None,
    **kwargs
) -> ContainerLogSeeder:
    """Get or create the global ContainerLogSeeder instance."""
    global _seeder_instance

    if _seeder_instance is None:
        if output_dir is None:
            raise ValueError("output_dir required for first initialization")
        _seeder_instance = ContainerLogSeeder(
            output_dir=output_dir,
            event_bus=event_bus,
            **kwargs
        )

    return _seeder_instance


async def setup_container_log_seeder(
    output_dir: str,
    event_bus: Any,
    redis_client: Any = None
) -> ContainerLogSeeder:
    """
    Setup and initialize the ContainerLogSeeder with EventBus subscription.

    Call this during application startup.
    """
    seeder = get_container_log_seeder(
        output_dir=output_dir,
        event_bus=event_bus,
        redis_client=redis_client
    )

    await seeder.subscribe_to_events()

    logger.info(
        "container_log_seeder_initialized",
        output_dir=output_dir,
        logs_dir=str(seeder.logs_dir)
    )

    return seeder
