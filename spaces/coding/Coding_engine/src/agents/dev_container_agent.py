"""
Development Container Agent - Manages dev container for live code generation viewing.

This agent:
1. Starts dev container with VNC after scaffolding completes
2. Monitors container health throughout generation
3. Publishes events when VNC and dev server are ready
4. Stops container when generation completes or on error

The dev container uses Docker volume mounts so files appear live as they're generated.
"""

import asyncio
from typing import Optional
import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import EventBus, Event, EventType
from src.tools.dev_container_tool import DevContainerTool, DevContainerState, DevContainerResult

logger = structlog.get_logger(__name__)


class DevContainerAgent(AutonomousAgent):
    """
    Agent that manages development container for live VNC viewing during generation.

    Subscribes to:
    - SCAFFOLDING_COMPLETE: Start dev container with VNC
    - BUILD_FAILED: Keep running (show errors in browser console)
    - CONVERGENCE_ACHIEVED: Keep running for final viewing
    - SYSTEM_ERROR: Stop container

    Publishes:
    - DEV_CONTAINER_STARTED: Container created and VNC ready
    - DEV_CONTAINER_READY: Dev server running in browser
    - DEV_CONTAINER_STOPPED: Container stopped
    """

    def __init__(
        self,
        event_bus: EventBus,
        output_dir: str,
        vnc_port: int = 6080,
        dev_port: int = 5173,
        auto_stop_on_complete: bool = False,
    ):
        """
        Initialize dev container agent.

        Args:
            event_bus: EventBus for pub/sub
            output_dir: Output directory to mount in container
            vnc_port: VNC web port (default 6080)
            dev_port: Dev server port (default 5173)
            auto_stop_on_complete: Whether to stop container when generation completes
        """
        super().__init__(
            agent_type="dev_container",
            event_bus=event_bus,
        )

        self.output_dir = output_dir
        self.vnc_port = vnc_port
        self.dev_port = dev_port
        self.auto_stop_on_complete = auto_stop_on_complete

        self._container_tool: Optional[DevContainerTool] = None
        self._container_result: Optional[DevContainerResult] = None
        self._running = False

        self.logger = logger.bind(
            component="dev_container_agent",
            output_dir=output_dir,
            vnc_port=vnc_port,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent subscribes to."""
        return [
            EventType.SCAFFOLDING_COMPLETE,  # Start container
            EventType.BUILD_FAILED,          # Log but keep running
            EventType.BUILD_SUCCEEDED,       # Keep running
            EventType.CONVERGENCE_ACHIEVED,  # Generation complete
            EventType.SYSTEM_ERROR,          # Stop on error
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Determine if agent should act on event."""
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            if event.type == EventType.SCAFFOLDING_COMPLETE:
                # Start container if not already running
                if not self._running:
                    return True

            if event.type == EventType.SYSTEM_ERROR:
                # Stop container on error
                if self._running:
                    return True

            if event.type == EventType.CONVERGENCE_ACHIEVED:
                # Optionally stop on complete
                if self._running and self.auto_stop_on_complete:
                    return True

        return False

    async def act(self, events: list[Event]):
        """Handle event and take action."""
        # Find the first matching event
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        if event.type == EventType.SCAFFOLDING_COMPLETE:
            await self._start_container()

        elif event.type == EventType.SYSTEM_ERROR:
            await self._stop_container("system_error")

        elif event.type == EventType.CONVERGENCE_ACHIEVED:
            if self.auto_stop_on_complete:
                await self._stop_container("generation_complete")
            else:
                self.logger.info(
                    "generation_complete_container_running",
                    vnc_url=self._container_result.vnc_url if self._container_result else None,
                )

    async def _start_container(self):
        """Start the dev container with VNC."""
        self.logger.info("starting_dev_container")

        try:
            self._container_tool = DevContainerTool(
                project_dir=self.output_dir,
                vnc_port=self.vnc_port,
                dev_port=self.dev_port,
                state_callback=self._on_state_change,
            )

            self._container_result = await self._container_tool.start()

            if self._container_result.success:
                self._running = True

                # Publish DEV_CONTAINER_STARTED
                await self._publish_event(Event(
                    type=EventType.DEV_CONTAINER_STARTED,
                    source=self.agent_type,
                    data={
                        "container_id": self._container_result.container_id,
                        "vnc_url": self._container_result.vnc_url,
                        "dev_server_url": self._container_result.dev_server_url,
                        "state": self._container_result.state.value,
                    }
                ))

                self.logger.info(
                    "dev_container_started",
                    vnc_url=self._container_result.vnc_url,
                    container_id=self._container_result.container_id,
                )

            else:
                self.logger.error(
                    "dev_container_start_failed",
                    error=self._container_result.error,
                )

        except Exception as e:
            self.logger.error("dev_container_start_exception", error=str(e))

    async def _stop_container(self, reason: str):
        """Stop the dev container."""
        self.logger.info("stopping_dev_container", reason=reason)

        if self._container_tool:
            await self._container_tool.stop()

        self._running = False
        self._container_tool = None
        self._container_result = None

        # Publish DEV_CONTAINER_STOPPED
        await self._publish_event(Event(
            type=EventType.DEV_CONTAINER_STOPPED,
            source=self.agent_type,
            data={"reason": reason}
        ))

    def _on_state_change(self, new_state: DevContainerState):
        """Handle state changes from the container tool."""
        self.logger.debug("container_state_changed", state=new_state.value)

        # Publish event when dev server starts
        if new_state == DevContainerState.RUNNING:
            # Fire and forget the event publish
            asyncio.create_task(self._publish_dev_server_started())

    async def _publish_dev_server_started(self):
        """Publish DEV_SERVER_STARTED event."""
        await self._publish_event(Event(
            type=EventType.DEV_SERVER_STARTED,
            source=self.agent_type,
            data={
                "vnc_url": self._container_result.vnc_url if self._container_result else None,
                "dev_server_url": self._container_result.dev_server_url if self._container_result else None,
            }
        ))

        # Also publish DEV_CONTAINER_READY
        await self._publish_event(Event(
            type=EventType.DEV_CONTAINER_READY,
            source=self.agent_type,
            data={
                "vnc_url": self._container_result.vnc_url if self._container_result else None,
                "dev_server_url": self._container_result.dev_server_url if self._container_result else None,
                "container_id": self._container_result.container_id if self._container_result else None,
            }
        ))

    async def _publish_event(self, event: Event):
        """Publish event to event bus."""
        if self.event_bus:
            await self.event_bus.publish(event)

    def get_status(self) -> dict:
        """Get current status of the dev container."""
        if self._container_tool:
            return {
                "running": self._running,
                **self._container_tool.get_status(),
            }
        return {
            "running": False,
            "state": DevContainerState.STOPPED.value,
        }

    async def stop(self):
        """Stop the agent and container."""
        if self._running:
            await self._stop_container("agent_stopped")
