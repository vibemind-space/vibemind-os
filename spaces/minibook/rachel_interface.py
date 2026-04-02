"""
Rachel Interface — Rachel's metadata dashboard for agent status, tasks, and reports.

Provides Rachel (voice agent) with live information about:
- Which agents are registered and their current status
- Active and recently completed tasks
- Alerts (agent timeouts, failures)
- Prompt context string for Rachel's system prompt

This is a passive data aggregator, NOT an execution agent.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import deque

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[RachelInterface] %s", msg)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AgentStatus:
    """Status of a single Minibook agent."""
    agent_name: str
    space_key: str
    status: str = "registered"  # registered, online, busy, offline, error
    last_response_at: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_error: Optional[str] = None

    @property
    def is_online(self) -> bool:
        """Agent considered online if responded within last 5 minutes."""
        if self.status in ("online", "busy"):
            return True
        if self.last_response_at > 0:
            return (time.time() - self.last_response_at) < 300
        return self.status == "registered"

    @property
    def status_icon(self) -> str:
        if self.status == "busy":
            return "~"
        return "+" if self.is_online else "-"


@dataclass
class TaskStatus:
    """Status of an active task dispatched through the hub."""
    task_id: str
    original_request: str
    spaces: List[str]
    status: str = "dispatched"  # dispatched, in_progress, completed, failed, timeout
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    result_summary: Optional[str] = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or time.time()
        return end - self.created_at


@dataclass
class TaskResult:
    """A completed task result for history."""
    task_id: str
    event_type: str
    original_request: str
    result_summary: str
    spaces: List[str]
    completed_at: float = field(default_factory=time.time)
    success: bool = True


# =============================================================================
# Rachel Interface
# =============================================================================

class RachelInterface:
    """
    Rachel's metadata dashboard.

    Aggregates status from all sources and provides:
    - Agent registry and live status
    - Active task tracking
    - Recent result history
    - Formatted prompt context for Rachel's system prompt
    - Voice-callable reports
    """

    MAX_RECENT_RESULTS = 20
    MAX_ALERTS = 10

    def __init__(self):
        self._agents: Dict[str, AgentStatus] = {}
        self._active_tasks: Dict[str, TaskStatus] = {}
        self._recent_results: deque = deque(maxlen=self.MAX_RECENT_RESULTS)
        self._alerts: deque = deque(maxlen=self.MAX_ALERTS)

    # =========================================================================
    # Agent Registration & Status
    # =========================================================================

    def register_agent(self, agent_name: str, space_key: str) -> None:
        """Register an agent in Rachel's dashboard."""
        self._agents[agent_name] = AgentStatus(
            agent_name=agent_name,
            space_key=space_key,
            status="registered",
        )

    def update_agent_status(
        self,
        agent_name: str,
        status: str,
        last_response_time: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update an agent's status."""
        agent = self._agents.get(agent_name)
        if not agent:
            return
        agent.status = status
        if last_response_time is not None:
            agent.last_response_at = last_response_time
        if error:
            agent.last_error = error

    def mark_agent_responded(self, agent_name: str) -> None:
        """Mark that an agent just responded successfully."""
        agent = self._agents.get(agent_name)
        if agent:
            agent.status = "online"
            agent.last_response_at = time.time()
            agent.tasks_completed += 1

    def mark_agent_failed(self, agent_name: str, error: str) -> None:
        """Mark that an agent's task failed."""
        agent = self._agents.get(agent_name)
        if agent:
            agent.tasks_failed += 1
            agent.last_error = error
            self._add_alert(f"{agent.space_key}-Agent Fehler: {error[:80]}")

    # =========================================================================
    # Task Tracking
    # =========================================================================

    def register_task(
        self,
        task_id: str,
        spaces: List[str],
        original_request: str,
    ) -> None:
        """Register a new task being dispatched."""
        self._active_tasks[task_id] = TaskStatus(
            task_id=task_id,
            original_request=original_request,
            spaces=spaces,
            status="dispatched",
        )

    def update_task_status(self, task_id: str, status: str) -> None:
        """Update a task's status."""
        task = self._active_tasks.get(task_id)
        if task:
            task.status = status

    def complete_task(
        self,
        task_id: str,
        event_type: str,
        result_summary: str,
        success: bool = True,
    ) -> None:
        """Mark a task as completed and move to history."""
        task = self._active_tasks.pop(task_id, None)
        if not task:
            return

        task.status = "completed" if success else "failed"
        task.completed_at = time.time()
        task.result_summary = result_summary

        self._recent_results.appendleft(TaskResult(
            task_id=task_id,
            event_type=event_type,
            original_request=task.original_request,
            result_summary=result_summary,
            spaces=task.spaces,
            completed_at=task.completed_at,
            success=success,
        ))

        # Brain reward: send routing outcome to SpaceRoutingHead
        routing_id = getattr(task, 'routing_id', None) or (
            task.metadata.get('routing_id') if hasattr(task, 'metadata') and task.metadata else None
        )
        if routing_id:
            try:
                import requests as _req
                _req.post(
                    "http://localhost:5000/api/cortex/route/reward",
                    json={"routing_id": routing_id, "success": success},
                    timeout=1,
                )
            except Exception:
                pass

    def timeout_task(self, task_id: str) -> None:
        """Mark a task as timed out."""
        task = self._active_tasks.pop(task_id, None)
        if task:
            task.status = "timeout"
            self._add_alert(
                f"Task Timeout: '{task.original_request[:50]}' "
                f"(Spaces: {', '.join(task.spaces)})"
            )

    # =========================================================================
    # Alerts
    # =========================================================================

    def _add_alert(self, message: str) -> None:
        """Add an alert to the dashboard."""
        self._alerts.appendleft({
            "message": message,
            "time": time.time(),
        })

    # =========================================================================
    # Prompt Context for Rachel
    # =========================================================================

    def get_prompt_context(self) -> str:
        """
        Build a formatted context string for Rachel's system prompt.

        Injected on every voice interaction so Rachel can answer
        status queries without tool calls.
        """
        _logger.debug("get_prompt_context called: agents=%s, active_tasks=%s", len(self._agents), len(self._active_tasks))
        lines = ["=== VibeMind Agent Status ==="]

        # Agent status line
        agent_parts = []
        for agent in self._agents.values():
            agent_parts.append(f"{agent.space_key}({agent.status_icon})")
        if agent_parts:
            lines.append(f"Agents: {', '.join(agent_parts)}")

        # Active tasks
        active_count = len(self._active_tasks)
        if active_count > 0:
            task_descs = []
            for task in list(self._active_tasks.values())[:3]:
                spaces_str = "+".join(task.spaces)
                elapsed = f"{task.elapsed_seconds:.0f}s"
                task_descs.append(f"{spaces_str}: {task.original_request[:40]} ({elapsed})")
            lines.append(f"Laufende Tasks ({active_count}): {'; '.join(task_descs)}")
        else:
            lines.append("Laufende Tasks: keine")

        # Recent results (last 3)
        if self._recent_results:
            result_parts = []
            for r in list(self._recent_results)[:3]:
                ago = time.time() - r.completed_at
                if ago < 60:
                    ago_str = f"vor {ago:.0f}s"
                else:
                    ago_str = f"vor {ago / 60:.0f} Min"
                icon = "+" if r.success else "!"
                result_parts.append(f"({icon}) {r.event_type} ({ago_str})")
            lines.append(f"Letzte Ergebnisse: {', '.join(result_parts)}")

        # Alerts (last 2)
        if self._alerts:
            for alert in list(self._alerts)[:2]:
                lines.append(f"ALERT: {alert['message']}")

        return "\n".join(lines)

    # =========================================================================
    # Voice Commands (Tool Results)
    # =========================================================================

    def get_agent_report(self) -> Dict[str, Any]:
        """
        For 'Welche Agents habe ich?' voice command.

        Returns a structured dict for voice output.
        """
        _logger.debug("get_agent_report called: agent_count=%s", len(self._agents))
        agents_info = []
        online_count = 0
        for agent in self._agents.values():
            is_online = agent.is_online
            if is_online:
                online_count += 1
            agents_info.append({
                "space": agent.space_key,
                "name": agent.agent_name,
                "status": "online" if is_online else agent.status,
                "tasks_completed": agent.tasks_completed,
                "tasks_failed": agent.tasks_failed,
            })

        total = len(self._agents)
        summary = (
            f"Du hast {total} Agents registriert, "
            f"davon {online_count} online: "
            + ", ".join(a["space"] for a in agents_info if a["status"] == "online")
        )

        return {
            "success": True,
            "agents": agents_info,
            "total": total,
            "online": online_count,
            "response_hint": summary,
        }

    def get_task_dashboard(self) -> Dict[str, Any]:
        """
        For 'Was laeuft gerade?' voice command.

        Returns active and recent tasks.
        """
        _logger.debug("get_task_dashboard called: active_tasks=%s, recent_results=%s", len(self._active_tasks), len(self._recent_results))
        active = []
        for task in self._active_tasks.values():
            active.append({
                "task_id": task.task_id,
                "request": task.original_request[:80],
                "spaces": task.spaces,
                "status": task.status,
                "elapsed_seconds": task.elapsed_seconds,
            })

        recent = []
        for r in list(self._recent_results)[:5]:
            recent.append({
                "event_type": r.event_type,
                "request": r.original_request[:80],
                "success": r.success,
                "result": r.result_summary[:100] if r.result_summary else "",
            })

        if active:
            summary = f"Es laufen {len(active)} Tasks: " + ", ".join(
                f"{t['spaces'][0]}: {t['request'][:30]}" for t in active
            )
        else:
            summary = "Keine laufenden Tasks."
            if recent:
                last = recent[0]
                summary += f" Letztes Ergebnis: {last['event_type']}"

        return {
            "success": True,
            "active_tasks": active,
            "recent_results": recent,
            "response_hint": summary,
        }

    # =========================================================================
    # Internal Stats
    # =========================================================================

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def online_agent_count(self) -> int:
        return sum(1 for a in self._agents.values() if a.is_online)

    @property
    def active_task_count(self) -> int:
        return len(self._active_tasks)


# =============================================================================
# Singleton
# =============================================================================

_rachel_interface: Optional[RachelInterface] = None


def get_rachel_interface() -> RachelInterface:
    """Get or create the global RachelInterface singleton."""
    global _rachel_interface
    if _rachel_interface is None:
        _rachel_interface = RachelInterface()
    return _rachel_interface


__all__ = [
    "RachelInterface",
    "AgentStatus",
    "TaskStatus",
    "TaskResult",
    "get_rachel_interface",
]
