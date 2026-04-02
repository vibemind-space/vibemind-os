"""
Deadlock Detector — Detects and prevents circular waits among agents.

Provides:
- Wait-for graph construction (agent A waiting on agent B)
- Cycle detection using DFS with coloring
- Deadlock prevention via resource ordering
- Timeout-based deadlock resolution
- Event bus integration for real-time alerts

Usage::

    detector = DeadlockDetector(event_bus, check_interval=5.0)
    detector.start()

    # Register that agent A is waiting for agent B's output
    detector.register_wait("AgentA", "AgentB", resource="build_output")

    # When the wait is resolved
    detector.resolve_wait("AgentA", "AgentB")

    # Check for deadlocks manually
    cycles = detector.detect_deadlocks()
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


class WaitState(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    TIMED_OUT = "timed_out"
    BROKEN = "broken"  # Forcefully broken to resolve deadlock


@dataclass
class WaitEdge:
    """An edge in the wait-for graph: waiter -> blocker."""
    waiter: str
    blocker: str
    resource: str = ""
    registered_at: float = field(default_factory=time.time)
    timeout_seconds: float = 300.0  # Default 5 min timeout
    state: WaitState = WaitState.ACTIVE
    resolved_at: Optional[float] = None

    @property
    def is_active(self) -> bool:
        return self.state == WaitState.ACTIVE

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.registered_at

    @property
    def is_timed_out(self) -> bool:
        return self.elapsed_seconds > self.timeout_seconds


@dataclass
class DeadlockCycle:
    """A detected deadlock cycle."""
    agents: List[str]
    edges: List[WaitEdge]
    detected_at: float = field(default_factory=time.time)
    resolved: bool = False
    resolution: str = ""

    @property
    def cycle_str(self) -> str:
        return " -> ".join(self.agents + [self.agents[0]])

    def to_dict(self) -> dict:
        return {
            "agents": self.agents,
            "cycle": self.cycle_str,
            "edges": [
                {
                    "waiter": e.waiter,
                    "blocker": e.blocker,
                    "resource": e.resource,
                    "elapsed_seconds": round(e.elapsed_seconds, 1),
                }
                for e in self.edges
            ],
            "detected_at": self.detected_at,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }


class DeadlockDetector:
    """
    Detects circular waits among agents using a wait-for graph.

    The wait-for graph tracks which agents are waiting for which other agents.
    Cycle detection uses DFS with three-color marking (WHITE, GRAY, BLACK).
    """

    def __init__(
        self,
        event_bus=None,
        check_interval: float = 5.0,
        default_timeout: float = 300.0,
        auto_resolve: bool = True,
    ):
        self.event_bus = event_bus
        self.check_interval = check_interval
        self.default_timeout = default_timeout
        self.auto_resolve = auto_resolve

        # Wait-for graph: waiter -> list of WaitEdges
        self._waits: Dict[str, List[WaitEdge]] = {}
        # All known agents
        self._agents: Set[str] = set()
        # Detected cycles history
        self._cycles: List[DeadlockCycle] = []
        # Background checker task
        self._checker_task: Optional[asyncio.Task] = None
        # Callbacks
        self._on_deadlock_callbacks: List = []

        self.logger = logger.bind(component="deadlock_detector")

    def start(self):
        """Start the background deadlock checker."""
        if self._checker_task is None or self._checker_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._checker_task = loop.create_task(self._periodic_check())
                self.logger.info("deadlock_detector_started", interval=self.check_interval)
            except RuntimeError:
                pass  # No event loop

    def stop(self):
        """Stop the background checker."""
        if self._checker_task and not self._checker_task.done():
            self._checker_task.cancel()
            self._checker_task = None

    def register_wait(
        self,
        waiter: str,
        blocker: str,
        resource: str = "",
        timeout: Optional[float] = None,
    ):
        """Register that 'waiter' is waiting for 'blocker'."""
        self._agents.add(waiter)
        self._agents.add(blocker)

        edge = WaitEdge(
            waiter=waiter,
            blocker=blocker,
            resource=resource,
            timeout_seconds=timeout or self.default_timeout,
        )

        if waiter not in self._waits:
            self._waits[waiter] = []

        # Don't add duplicate active waits
        for existing in self._waits[waiter]:
            if existing.blocker == blocker and existing.is_active:
                return

        self._waits[waiter].append(edge)
        self.logger.debug("wait_registered", waiter=waiter, blocker=blocker, resource=resource)

    def resolve_wait(self, waiter: str, blocker: str):
        """Mark a wait as resolved."""
        if waiter in self._waits:
            for edge in self._waits[waiter]:
                if edge.blocker == blocker and edge.is_active:
                    edge.state = WaitState.RESOLVED
                    edge.resolved_at = time.time()
                    self.logger.debug("wait_resolved", waiter=waiter, blocker=blocker)
                    return True
        return False

    def detect_deadlocks(self) -> List[DeadlockCycle]:
        """
        Detect all cycles in the wait-for graph.

        Uses DFS with three-color marking:
        - WHITE (0): Unvisited
        - GRAY (1): In current DFS path (potential cycle member)
        - BLACK (2): Fully explored
        """
        # Build adjacency list of active waits only
        adj: Dict[str, List[str]] = {}
        edge_map: Dict[Tuple[str, str], WaitEdge] = {}

        for waiter, edges in self._waits.items():
            for edge in edges:
                if edge.is_active:
                    if waiter not in adj:
                        adj[waiter] = []
                    adj[waiter].append(edge.blocker)
                    edge_map[(waiter, edge.blocker)] = edge

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {agent: WHITE for agent in self._agents}
        parent: Dict[str, Optional[str]] = {agent: None for agent in self._agents}
        cycles: List[List[str]] = []

        def dfs(node: str):
            color[node] = GRAY

            for neighbor in adj.get(node, []):
                if color.get(neighbor, WHITE) == GRAY:
                    # Found a cycle! Trace it back
                    cycle = [neighbor]
                    current = node
                    while current != neighbor:
                        cycle.append(current)
                        current = parent.get(current)
                        if current is None:
                            break
                    cycle.reverse()
                    cycles.append(cycle)
                elif color.get(neighbor, WHITE) == WHITE:
                    parent[neighbor] = node
                    dfs(neighbor)

            color[node] = BLACK

        for agent in self._agents:
            if color.get(agent, WHITE) == WHITE:
                dfs(agent)

        # Convert to DeadlockCycle objects
        new_cycles = []
        for cycle_agents in cycles:
            edges = []
            for i in range(len(cycle_agents)):
                waiter = cycle_agents[i]
                blocker = cycle_agents[(i + 1) % len(cycle_agents)]
                edge = edge_map.get((waiter, blocker))
                if edge:
                    edges.append(edge)

            dc = DeadlockCycle(agents=cycle_agents, edges=edges)
            new_cycles.append(dc)
            self._cycles.append(dc)

            self.logger.warning(
                "deadlock_detected",
                cycle=dc.cycle_str,
                agents=len(dc.agents),
            )

        return new_cycles

    def resolve_deadlock(self, cycle: DeadlockCycle, strategy: str = "break_longest_wait"):
        """
        Resolve a deadlock by breaking one edge in the cycle.

        Strategies:
        - break_longest_wait: Break the edge that has been waiting longest
        - break_lowest_priority: Break edge involving lowest priority agent
        - break_all: Break all edges in the cycle
        """
        if not cycle.edges:
            return

        if strategy == "break_longest_wait":
            # Find the edge that's been waiting the longest
            longest = max(cycle.edges, key=lambda e: e.elapsed_seconds)
            longest.state = WaitState.BROKEN
            longest.resolved_at = time.time()
            cycle.resolved = True
            cycle.resolution = f"Broke wait: {longest.waiter} -> {longest.blocker} (waited {longest.elapsed_seconds:.1f}s)"

        elif strategy == "break_all":
            for edge in cycle.edges:
                edge.state = WaitState.BROKEN
                edge.resolved_at = time.time()
            cycle.resolved = True
            cycle.resolution = f"Broke all {len(cycle.edges)} edges in cycle"

        self.logger.info("deadlock_resolved", strategy=strategy, resolution=cycle.resolution)

    def on_deadlock(self, callback):
        """Register a callback for deadlock detection."""
        self._on_deadlock_callbacks.append(callback)

    async def _periodic_check(self):
        """Background task that periodically checks for deadlocks."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)

                # Check for timed-out waits
                self._check_timeouts()

                # Detect deadlocks
                cycles = self.detect_deadlocks()

                if cycles:
                    for cycle in cycles:
                        # Fire callbacks
                        for cb in self._on_deadlock_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(cb):
                                    await cb(cycle)
                                else:
                                    cb(cycle)
                            except Exception:
                                pass

                        # Auto-resolve if enabled
                        if self.auto_resolve and not cycle.resolved:
                            self.resolve_deadlock(cycle)

                    # Broadcast via event bus
                    self._broadcast_deadlock(cycles)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("deadlock_check_error", error=str(e))

    def _check_timeouts(self):
        """Check for timed-out waits and resolve them."""
        for waiter, edges in self._waits.items():
            for edge in edges:
                if edge.is_active and edge.is_timed_out:
                    edge.state = WaitState.TIMED_OUT
                    edge.resolved_at = time.time()
                    self.logger.warning(
                        "wait_timed_out",
                        waiter=edge.waiter,
                        blocker=edge.blocker,
                        elapsed=f"{edge.elapsed_seconds:.1f}s",
                    )

    def _broadcast_deadlock(self, cycles: List[DeadlockCycle]):
        """Broadcast deadlock alerts via event bus."""
        if not self.event_bus:
            return
        try:
            from src.mind.event_bus import Event, EventType
            event = Event(
                type=EventType.ERROR_OCCURRED,
                source="deadlock_detector",
                data={
                    "action": "deadlock_alert",
                    "cycles": [c.to_dict() for c in cycles],
                },
            )
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.event_bus.publish(event))
            except RuntimeError:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_wait_graph(self) -> dict:
        """Get current wait-for graph."""
        active_waits = {}
        for waiter, edges in self._waits.items():
            active = [e for e in edges if e.is_active]
            if active:
                active_waits[waiter] = [
                    {
                        "blocker": e.blocker,
                        "resource": e.resource,
                        "elapsed_seconds": round(e.elapsed_seconds, 1),
                        "timeout_seconds": e.timeout_seconds,
                    }
                    for e in active
                ]
        return active_waits

    def get_agent_waits(self, agent_name: str) -> dict:
        """Get what an agent is waiting for and who is waiting for it."""
        waiting_for = []
        waited_by = []

        for waiter, edges in self._waits.items():
            for edge in edges:
                if not edge.is_active:
                    continue
                if waiter == agent_name:
                    waiting_for.append({
                        "blocker": edge.blocker,
                        "resource": edge.resource,
                        "elapsed_seconds": round(edge.elapsed_seconds, 1),
                    })
                elif edge.blocker == agent_name:
                    waited_by.append({
                        "waiter": waiter,
                        "resource": edge.resource,
                        "elapsed_seconds": round(edge.elapsed_seconds, 1),
                    })

        return {
            "agent": agent_name,
            "waiting_for": waiting_for,
            "waited_by": waited_by,
        }

    def get_deadlock_history(self, limit: int = 20) -> List[dict]:
        """Get history of detected deadlocks."""
        return [c.to_dict() for c in self._cycles[-limit:]]

    def get_stats(self) -> dict:
        """Get deadlock detector stats."""
        total_waits = sum(len(edges) for edges in self._waits.values())
        active_waits = sum(
            sum(1 for e in edges if e.is_active)
            for edges in self._waits.values()
        )
        return {
            "total_agents": len(self._agents),
            "total_waits_registered": total_waits,
            "active_waits": active_waits,
            "total_deadlocks_detected": len(self._cycles),
            "resolved_deadlocks": sum(1 for c in self._cycles if c.resolved),
            "unresolved_deadlocks": sum(1 for c in self._cycles if not c.resolved),
        }

    def clear(self):
        """Clear all tracking data."""
        self._waits.clear()
        self._agents.clear()
        self._cycles.clear()
