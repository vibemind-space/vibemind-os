"""
Society Runner - Main entry point for running the Society of Mind.

Combines:
1. Orchestrator for agent coordination
2. Live Preview for real-time app viewing
3. WebSocket bridge for UI streaming
4. Progress callbacks for external integration

This is the primary interface for running the continuous iteration system.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any, TYPE_CHECKING
import structlog

from .event_bus import EventBus, Event, EventType
from .shared_state import SharedState, ConvergenceMetrics
from .convergence import ConvergenceCriteria, DEFAULT_CRITERIA
from .orchestrator import Orchestrator, OrchestratorResult
from .live_preview import LivePreviewSystem, PreviewStatus

# Lazy import to avoid circular dependency with api.websocket
if TYPE_CHECKING:
    from ..api.websocket import WebSocketBridge, ConnectionManager


logger = structlog.get_logger(__name__)


@dataclass
class SocietyConfig:
    """Configuration for the Society of Mind runner."""
    # Working directory
    working_dir: str

    # Convergence settings
    criteria: ConvergenceCriteria = field(default_factory=lambda: DEFAULT_CRITERIA)

    # Live preview settings
    enable_live_preview: bool = True
    preview_port: int = 5173
    wait_for_preview_ready: bool = True
    preview_timeout: float = 60.0

    # WebSocket settings
    enable_websocket: bool = True
    session_id: Optional[str] = None

    # Callbacks
    progress_callback: Optional[Callable[[ConvergenceMetrics, float], None]] = None
    event_callback: Optional[Callable[[Event], None]] = None

    # Agent settings
    custom_agents: list[Any] = field(default_factory=list)


@dataclass
class SocietyResult:
    """Result from running the Society of Mind."""
    success: bool
    converged: bool
    orchestrator_result: Optional[OrchestratorResult] = None
    preview_url: Optional[str] = None
    total_duration_seconds: float = 0
    iterations: int = 0
    final_metrics: Optional[ConvergenceMetrics] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "converged": self.converged,
            "preview_url": self.preview_url,
            "total_duration_seconds": self.total_duration_seconds,
            "iterations": self.iterations,
            "errors": self.errors,
            "orchestrator": self.orchestrator_result.to_dict() if self.orchestrator_result else None,
            "metrics": self.final_metrics.to_dict() if self.final_metrics else None,
        }


class SocietyRunner:
    """
    Main runner for the Society of Mind system.

    Coordinates all components:
    - Orchestrator: Manages agents
    - Live Preview: Real-time app viewing
    - WebSocket: UI streaming
    """

    def __init__(self, config: SocietyConfig):
        self.config = config
        self.working_dir = Path(config.working_dir)

        # Core components
        self.event_bus = EventBus()
        self.shared_state = SharedState()

        # Orchestrator
        self.orchestrator = Orchestrator(
            working_dir=config.working_dir,
            criteria=config.criteria,
            progress_callback=config.progress_callback,
        )
        # Share event bus and state
        self.orchestrator.event_bus = self.event_bus
        self.orchestrator.shared_state = self.shared_state

        # Live preview (optional)
        self.live_preview: Optional[LivePreviewSystem] = None
        if config.enable_live_preview:
            self.live_preview = LivePreviewSystem(
                working_dir=config.working_dir,
                event_bus=self.event_bus,
                port=config.preview_port,
            )

        # WebSocket bridge (optional)
        self.ws_bridge: Optional["WebSocketBridge"] = None
        if config.enable_websocket:
            # Lazy import to avoid circular dependency
            from ..api.websocket import WebSocketBridge, get_connection_manager
            self.ws_bridge = WebSocketBridge(
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                connection_manager=get_connection_manager(),
            )
            self.ws_bridge.setup(config.session_id)

        # Add custom agents
        for agent in config.custom_agents:
            self.orchestrator.add_agent(agent)

        # Subscribe to events if callback provided
        if config.event_callback:
            self.event_bus.subscribe_all(config.event_callback)

        self.logger = logger.bind(component="society_runner")

        # State
        self._start_time: Optional[datetime] = None
        self._running = False

    async def run(self) -> SocietyResult:
        """
        Run the Society of Mind until convergence.

        Returns:
            SocietyResult with final state
        """
        self._start_time = datetime.now()
        self._running = True
        errors = []

        self.logger.info(
            "society_starting",
            working_dir=str(self.working_dir),
            live_preview=self.config.enable_live_preview,
            websocket=self.config.enable_websocket,
        )

        # Publish start event
        await self.event_bus.publish(Event(
            type=EventType.BUILD_STARTED,
            source="society_runner",
            data={"config": {
                "working_dir": str(self.working_dir),
                "criteria": str(self.config.criteria),
            }},
        ))

        preview_url: Optional[str] = None

        try:
            # Start live preview if enabled
            if self.live_preview:
                self.logger.info("starting_live_preview")
                preview_started = await self.live_preview.start(
                    wait_for_ready=self.config.wait_for_preview_ready,
                    timeout=self.config.preview_timeout,
                )
                if preview_started:
                    preview_url = self.live_preview.dev_server.state.url
                    self.logger.info("live_preview_ready", url=preview_url)
                else:
                    errors.append("Failed to start live preview")
                    self.logger.warning("live_preview_failed")

            # Run the orchestrator (main loop)
            self.logger.info("starting_orchestrator")
            orchestrator_result = await self.orchestrator.run()

            # Calculate final results
            duration = (datetime.now() - self._start_time).total_seconds()

            result = SocietyResult(
                success=orchestrator_result.success,
                converged=orchestrator_result.converged,
                orchestrator_result=orchestrator_result,
                preview_url=preview_url,
                total_duration_seconds=duration,
                iterations=orchestrator_result.iterations,
                final_metrics=orchestrator_result.final_metrics,
                errors=errors + orchestrator_result.errors,
            )

            self.logger.info(
                "society_complete",
                success=result.success,
                converged=result.converged,
                iterations=result.iterations,
                duration=duration,
            )

            # Publish completion event
            await self.event_bus.publish(Event(
                type=EventType.SYSTEM_READY if result.success else EventType.SYSTEM_ERROR,
                source="society_runner",
                success=result.success,
                data=result.to_dict(),
            ))

            return result

        except Exception as e:
            errors.append(str(e))
            self.logger.error("society_error", error=str(e))

            duration = (datetime.now() - self._start_time).total_seconds()

            return SocietyResult(
                success=False,
                converged=False,
                preview_url=preview_url,
                total_duration_seconds=duration,
                errors=errors,
            )

        finally:
            self._running = False
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        # Stop live preview
        if self.live_preview:
            try:
                await self.live_preview.stop()
            except Exception as e:
                self.logger.error("preview_cleanup_error", error=str(e))

    async def stop(self) -> None:
        """Stop the society runner."""
        self.logger.info("stopping_society")
        self._running = False
        await self.orchestrator.stop()
        await self._cleanup()

    def get_status(self) -> dict:
        """Get current status of all components."""
        status = {
            "running": self._running,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "orchestrator": self.orchestrator.get_status(),
        }

        if self.live_preview:
            status["preview"] = self.live_preview.get_state()

        if self.ws_bridge:
            status["websocket"] = self.ws_bridge.manager.get_stats()

        return status


async def run_society_of_mind(
    working_dir: str,
    criteria: Optional[ConvergenceCriteria] = None,
    enable_live_preview: bool = True,
    preview_port: int = 5173,
    enable_websocket: bool = True,
    session_id: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> SocietyResult:
    """
    Convenience function to run the Society of Mind.

    This is the primary entry point for the continuous iteration system.

    Args:
        working_dir: Project working directory
        criteria: Convergence criteria (uses defaults if not provided)
        enable_live_preview: Enable real-time app preview
        preview_port: Port for dev server
        enable_websocket: Enable WebSocket streaming
        session_id: Session ID for WebSocket filtering
        progress_callback: Called with (metrics, progress_percentage) on updates

    Returns:
        SocietyResult with final state

    Example:
        ```python
        result = await run_society_of_mind(
            working_dir="./output",
            criteria=RELAXED_CRITERIA,
            enable_live_preview=True,
        )

        if result.success:
            print(f"Converged in {result.iterations} iterations")
            print(f"Preview available at: {result.preview_url}")
        else:
            print(f"Failed: {result.errors}")
        ```
    """
    config = SocietyConfig(
        working_dir=working_dir,
        criteria=criteria or DEFAULT_CRITERIA,
        enable_live_preview=enable_live_preview,
        preview_port=preview_port,
        enable_websocket=enable_websocket,
        session_id=session_id,
        progress_callback=progress_callback,
    )

    runner = SocietyRunner(config)
    return await runner.run()


# CLI entry point
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Run the Society of Mind continuous iteration system"
    )
    parser.add_argument(
        "working_dir",
        help="Project working directory",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5173,
        help="Dev server port (default: 5173)",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable live preview",
    )
    parser.add_argument(
        "--no-websocket",
        action="store_true",
        help="Disable WebSocket",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Maximum iterations (default: 50)",
    )
    parser.add_argument(
        "--max-time",
        type=int,
        default=600,
        help="Maximum time in seconds (default: 600)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict convergence criteria",
    )
    parser.add_argument(
        "--relaxed",
        action="store_true",
        help="Use relaxed convergence criteria",
    )

    args = parser.parse_args()

    # Select criteria
    from .convergence import STRICT_CRITERIA, RELAXED_CRITERIA

    criteria = DEFAULT_CRITERIA
    if args.strict:
        criteria = STRICT_CRITERIA
    elif args.relaxed:
        criteria = RELAXED_CRITERIA

    # Override iteration/time limits
    criteria.max_iterations = args.max_iterations
    criteria.max_time_seconds = args.max_time

    # Progress callback for CLI
    def print_progress(metrics: ConvergenceMetrics, progress: float):
        print(f"\r[{progress:.1f}%] Tests: {metrics.tests_passed}/{metrics.total_tests}, "
              f"Build: {'OK' if metrics.build_success else 'FAIL'}, "
              f"Confidence: {metrics.confidence_score:.1%}", end="", flush=True)

    # Run
    async def main():
        result = await run_society_of_mind(
            working_dir=args.working_dir,
            criteria=criteria,
            enable_live_preview=not args.no_preview,
            preview_port=args.port,
            enable_websocket=not args.no_websocket,
            progress_callback=print_progress,
        )

        print()  # New line after progress
        if result.success:
            print(f"\nSuccess! Converged in {result.iterations} iterations.")
            if result.preview_url:
                print(f"Preview: {result.preview_url}")
        else:
            print(f"\nFailed after {result.iterations} iterations.")
            for error in result.errors:
                print(f"  - {error}")

        return 0 if result.success else 1

    sys.exit(asyncio.run(main()))
