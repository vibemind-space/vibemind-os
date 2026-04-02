"""
Agent Runtime - Message Broker for Handoff Pattern

Central coordinator for handoff-based multi-agent system.
Based on AutoGen's distributed runtime pattern.

Key responsibilities:
- Agent registry and discovery
- Task routing between agents
- Handoff request processing
- Progress update aggregation
- Session management
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

from .messages import (
    UserTask,
    AgentResponse,
    HandoffRequest,
    ProgressUpdate,
    RecoveryRequest
)
from .base_agent import BaseHandoffAgent

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Tracks a user session across agent handoffs."""
    id: str
    created_at: datetime = field(default_factory=datetime.now)
    task: Optional[UserTask] = None
    responses: List[AgentResponse] = field(default_factory=list)
    progress_updates: List[ProgressUpdate] = field(default_factory=list)
    current_agent: Optional[str] = None
    handoff_count: int = 0
    completed: bool = False
    final_result: Optional[Any] = None


class AgentRuntime:
    """
    Central coordinator for handoff-based multi-agent system.

    Implements the AutoGen runtime pattern:
    - Agents register with the runtime
    - Tasks are published to specific agents
    - Handoffs are routed automatically
    - Progress is aggregated across agents
    """

    def __init__(
        self,
        max_handoffs: int = 10,
        task_timeout: float = 120.0,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None
    ):
        """
        Initialize the agent runtime.

        Args:
            max_handoffs: Maximum handoffs before aborting (loop prevention)
            task_timeout: Maximum time for a task to complete
            on_progress: Optional callback for progress updates
        """
        self.max_handoffs = max_handoffs
        self.task_timeout = task_timeout
        self.on_progress = on_progress

        # Agent registry
        self._agents: Dict[str, BaseHandoffAgent] = {}

        # Session management
        self._sessions: Dict[str, Session] = {}

        # Task queue
        self._task_queue: asyncio.Queue = asyncio.Queue()

        # State
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None

        # Statistics
        self._stats = {
            "tasks_processed": 0,
            "handoffs_routed": 0,
            "errors": 0,
            "sessions_completed": 0
        }

    # ==================== Agent Management ====================

    async def register_agent(self, name: str, agent: BaseHandoffAgent):
        """
        Register an agent with the runtime.

        Args:
            name: Unique agent name
            agent: Agent instance
        """
        if name in self._agents:
            logger.warning(f"Agent '{name}' already registered, replacing")

        self._agents[name] = agent
        agent.set_runtime(self)
        await agent.start()

        logger.info(f"Runtime: Registered agent '{name}'")

    def get_agent(self, name: str) -> Optional[BaseHandoffAgent]:
        """Get an agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    # ==================== Task Distribution ====================

    async def publish_task(
        self,
        task: UserTask,
        target_agent: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Publish a task to a specific agent.

        Args:
            task: The task to execute
            target_agent: Name of the agent to receive the task
            session_id: Optional session ID (creates new if not provided)

        Returns:
            Session ID for tracking
        """
        # Create or get session
        if session_id is None:
            session_id = str(uuid.uuid4())

        if session_id not in self._sessions:
            self._sessions[session_id] = Session(id=session_id, task=task)

        session = self._sessions[session_id]
        session.current_agent = target_agent
        task.session_id = session_id

        # Queue the task
        await self._task_queue.put((task, target_agent))

        logger.info(f"Runtime: Published task to '{target_agent}' (session: {session_id[:8]})")
        return session_id

    async def handle_handoff(self, request: HandoffRequest) -> AgentResponse:
        """
        Handle a handoff request from one agent to another.

        Args:
            request: The handoff request

        Returns:
            Response from the target agent
        """
        # Check handoff limit
        if request.handoff_count >= self.max_handoffs:
            logger.error(f"Runtime: Max handoffs ({self.max_handoffs}) exceeded")
            return AgentResponse(
                success=False,
                error=f"Maximum handoffs ({self.max_handoffs}) exceeded",
                session_id=request.task.session_id if request.task else ""
            )

        target_agent = self._agents.get(request.target_agent)
        if not target_agent:
            logger.error(f"Runtime: Unknown target agent '{request.target_agent}'")
            return AgentResponse(
                success=False,
                error=f"Unknown agent: {request.target_agent}",
                session_id=request.task.session_id if request.task else ""
            )

        # Update session
        session_id = request.task.session_id if request.task else ""
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.current_agent = request.target_agent
            session.handoff_count += 1

        self._stats["handoffs_routed"] += 1

        logger.info(
            f"Runtime: Routing handoff to '{request.target_agent}' "
            f"(reason: {request.reason}, count: {request.handoff_count})"
        )

        # Execute on target agent
        if request.task:
            request.task.context["handoff_count"] = request.handoff_count + 1
            return await target_agent.handle_task(request.task)
        else:
            return AgentResponse(
                success=False,
                error="Handoff request missing task",
                session_id=session_id
            )

    # ==================== Progress & Results ====================

    async def publish_progress(self, update: ProgressUpdate):
        """
        Publish a progress update from an agent.

        Args:
            update: Progress update
        """
        session_id = update.session_id
        if session_id and session_id in self._sessions:
            self._sessions[session_id].progress_updates.append(update)

        logger.debug(
            f"Runtime: Progress from '{update.agent_name}': "
            f"{update.progress_percentage:.0f}% - {update.current_action}"
        )

        # Call progress callback if registered
        if self.on_progress:
            try:
                self.on_progress(update)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def wait_for_completion(
        self,
        session_id: str,
        timeout: Optional[float] = None
    ) -> Optional[AgentResponse]:
        """
        Wait for a session to complete.

        Args:
            session_id: Session to wait for
            timeout: Optional timeout (uses default if not specified)

        Returns:
            Final response or None if timeout
        """
        timeout = timeout or self.task_timeout
        start_time = asyncio.get_event_loop().time()

        while True:
            session = self._sessions.get(session_id)
            if not session:
                return None

            if session.completed:
                return session.responses[-1] if session.responses else None

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Runtime: Session {session_id[:8]} timed out")
                return None

            await asyncio.sleep(0.1)

    # ==================== Runtime Lifecycle ====================

    async def start(self):
        """Start the runtime processor."""
        if self._running:
            logger.warning("Runtime already running")
            return

        self._running = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info("Runtime: Started")

    async def stop(self):
        """Stop the runtime."""
        self._running = False

        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        # Stop all agents
        for agent in self._agents.values():
            await agent.stop()

        logger.info("Runtime: Stopped")

    async def stop_when_idle(self, timeout: float = 30.0):
        """Stop when all tasks are processed or timeout."""
        start_time = asyncio.get_event_loop().time()

        while self._running:
            if self._task_queue.empty():
                # Check if any sessions are still active
                active = any(
                    not s.completed for s in self._sessions.values()
                )
                if not active:
                    break

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning("Runtime: Idle timeout reached")
                break

            await asyncio.sleep(0.1)

        await self.stop()

    async def _process_loop(self):
        """Main processing loop."""
        logger.info("Runtime: Processing loop started")

        while self._running:
            try:
                # Get next task with timeout
                try:
                    task, target_agent = await asyncio.wait_for(
                        self._task_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Get agent
                agent = self._agents.get(target_agent)
                if not agent:
                    logger.error(f"Runtime: Unknown agent '{target_agent}'")
                    continue

                # Process task
                self._stats["tasks_processed"] += 1
                response = await agent.handle_task(task)

                # Update session
                session = self._sessions.get(task.session_id)
                if session:
                    session.responses.append(response)

                # Handle handoff if needed
                if response.next_agent:
                    # Create handoff request
                    handoff = HandoffRequest(
                        target_agent=response.next_agent,
                        task=task,
                        reason=f"Handoff from {target_agent}",
                        handoff_count=task.context.get("handoff_count", 0)
                    )

                    # Route to next agent
                    next_response = await self.handle_handoff(handoff)

                    # Continue chaining until no more handoffs
                    while next_response.next_agent:
                        if session:
                            session.responses.append(next_response)

                        handoff = HandoffRequest(
                            target_agent=next_response.next_agent,
                            task=task,
                            reason=f"Handoff chain",
                            handoff_count=task.context.get("handoff_count", 0)
                        )
                        next_response = await self.handle_handoff(handoff)

                    # Final response
                    if session:
                        session.responses.append(next_response)
                        session.completed = True
                        session.final_result = next_response.result
                        self._stats["sessions_completed"] += 1
                else:
                    # No handoff - task complete
                    if session:
                        session.completed = True
                        session.final_result = response.result
                        self._stats["sessions_completed"] += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Runtime: Processing error - {e}")
                self._stats["errors"] += 1

        logger.info("Runtime: Processing loop ended")

    # ==================== Utilities ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        return {
            **self._stats,
            "agents_registered": len(self._agents),
            "active_sessions": sum(1 for s in self._sessions.values() if not s.completed),
            "total_sessions": len(self._sessions)
        }

    async def run_task(
        self,
        task: UserTask,
        entry_agent: str = "orchestrator"
    ) -> AgentResponse:
        """
        Convenience method to run a single task to completion.

        Args:
            task: Task to execute
            entry_agent: Agent to start with

        Returns:
            Final response
        """
        session_id = await self.publish_task(task, entry_agent)
        await self.start()
        response = await self.wait_for_completion(session_id, self.task_timeout)
        await self.stop()

        return response or AgentResponse(
            success=False,
            error="Task did not complete",
            session_id=session_id
        )
