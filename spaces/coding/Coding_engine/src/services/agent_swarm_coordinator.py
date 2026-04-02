"""Agent Swarm Coordinator – coordinate swarms of agents working on related tasks.

Supports creating swarms with shared objectives, leader election,
task distribution among members, progress aggregation, and broadcast messaging.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Swarm:
    swarm_id: str
    name: str
    objective: str
    max_agents: int
    leader: str
    tags: List[str]
    created_at: float


@dataclass
class _SwarmMember:
    member_id: str
    swarm_name: str
    agent_id: str
    role: str  # leader | worker | observer
    joined_at: float


@dataclass
class _SwarmTask:
    task_id: str
    swarm_name: str
    agent_id: str
    task_name: str
    priority: int
    status: str  # pending | running | completed | failed
    reason: str
    created_at: float
    completed_at: float


@dataclass
class _SwarmEvent:
    event_id: str
    swarm_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class AgentSwarmCoordinator:
    """Coordinates swarms of agents with shared objectives and task distribution."""

    ROLES = ("leader", "worker", "observer")
    TASK_STATUSES = ("pending", "running", "completed", "failed")

    def __init__(self, max_swarms: int = 5000,
                 max_history: int = 100000) -> None:
        self._max_swarms = max_swarms
        self._max_history = max_history
        self._swarms: Dict[str, _Swarm] = {}
        self._members: Dict[str, _SwarmMember] = {}
        self._tasks: Dict[str, _SwarmTask] = {}
        self._history: List[_SwarmEvent] = []
        self._callbacks: Dict[str, Any] = {}
        self._seq = 0
        self._stats = {
            "total_swarms_created": 0,
            "total_members_joined": 0,
            "total_tasks_assigned": 0,
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
            "total_broadcasts": 0,
        }

    # ------------------------------------------------------------------
    # Swarm CRUD
    # ------------------------------------------------------------------

    def create_swarm(self, name: str, objective: str = "",
                     max_agents: int = 20,
                     tags: Optional[List[str]] = None) -> str:
        if not name:
            return ""
        if len(self._swarms) >= self._max_swarms:
            return ""
        # Reject duplicate names
        for s in self._swarms.values():
            if s.name == name:
                return ""
        self._seq += 1
        raw = f"swm-{name}-{self._seq}-{len(self._swarms)}"
        sid = "swm-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        s = _Swarm(
            swarm_id=sid, name=name, objective=objective,
            max_agents=max_agents, leader="",
            tags=list(tags or []), created_at=time.time(),
        )
        self._swarms[sid] = s
        self._stats["total_swarms_created"] += 1
        self._record(name, "swarm_created", {"swarm_id": sid, "name": name})
        self._fire("swarm_created", {"swarm_id": sid, "name": name})
        return sid

    def get_swarm(self, name: str) -> Optional[Dict]:
        swarm = self._find_swarm(name)
        if swarm is None:
            return None
        members = [m for m in self._members.values() if m.swarm_name == name]
        tasks = [t for t in self._tasks.values() if t.swarm_name == name]
        completed = sum(1 for t in tasks if t.status == "completed")
        failed = sum(1 for t in tasks if t.status == "failed")
        return {
            "swarm_id": swarm.swarm_id,
            "name": swarm.name,
            "objective": swarm.objective,
            "max_agents": swarm.max_agents,
            "leader": swarm.leader,
            "tags": list(swarm.tags),
            "created_at": swarm.created_at,
            "member_count": len(members),
            "task_count": len(tasks),
            "completed_tasks": completed,
            "failed_tasks": failed,
        }

    def list_swarms(self, tag: str = "") -> List[Dict]:
        results = []
        for s in self._swarms.values():
            if tag and tag not in s.tags:
                continue
            results.append({
                "swarm_id": s.swarm_id,
                "name": s.name,
                "objective": s.objective,
                "leader": s.leader,
                "tags": list(s.tags),
                "created_at": s.created_at,
            })
        results.sort(key=lambda x: x["created_at"])
        return results

    def remove_swarm(self, name: str) -> bool:
        swarm = self._find_swarm(name)
        if swarm is None:
            return False
        del self._swarms[swarm.swarm_id]
        # Cascade members
        to_rm = [m for m in self._members.values() if m.swarm_name == name]
        for m in to_rm:
            del self._members[m.member_id]
        # Cascade tasks
        to_rm_t = [t for t in self._tasks.values() if t.swarm_name == name]
        for t in to_rm_t:
            del self._tasks[t.task_id]
        self._record(name, "swarm_removed", {"name": name})
        self._fire("swarm_removed", {"name": name})
        return True

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------

    def join_swarm(self, swarm_name: str, agent_id: str,
                   role: str = "worker") -> bool:
        swarm = self._find_swarm(swarm_name)
        if swarm is None:
            return False
        if role not in self.ROLES:
            return False
        if not agent_id:
            return False
        # Check already a member
        for m in self._members.values():
            if m.swarm_name == swarm_name and m.agent_id == agent_id:
                return False
        # Check capacity
        current_count = sum(
            1 for m in self._members.values() if m.swarm_name == swarm_name
        )
        if current_count >= swarm.max_agents:
            return False
        self._seq += 1
        raw = f"mem-{swarm_name}-{agent_id}-{self._seq}"
        mid = "mem-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        member = _SwarmMember(
            member_id=mid, swarm_name=swarm_name, agent_id=agent_id,
            role=role, joined_at=time.time(),
        )
        self._members[mid] = member
        # If role is leader, update swarm leader
        if role == "leader":
            swarm.leader = agent_id
        self._stats["total_members_joined"] += 1
        self._record(swarm_name, "member_joined", {
            "agent_id": agent_id, "role": role,
        })
        self._fire("member_joined", {
            "swarm_name": swarm_name, "agent_id": agent_id, "role": role,
        })
        return True

    def leave_swarm(self, swarm_name: str, agent_id: str) -> bool:
        swarm = self._find_swarm(swarm_name)
        if swarm is None:
            return False
        target = None
        for m in self._members.values():
            if m.swarm_name == swarm_name and m.agent_id == agent_id:
                target = m
                break
        if target is None:
            return False
        del self._members[target.member_id]
        # If this was the leader, clear the leader
        if swarm.leader == agent_id:
            swarm.leader = ""
        self._record(swarm_name, "member_left", {"agent_id": agent_id})
        self._fire("member_left", {
            "swarm_name": swarm_name, "agent_id": agent_id,
        })
        return True

    # ------------------------------------------------------------------
    # Leader Election
    # ------------------------------------------------------------------

    def elect_leader(self, swarm_name: str) -> str:
        swarm = self._find_swarm(swarm_name)
        if swarm is None:
            return ""
        members = [
            m for m in self._members.values()
            if m.swarm_name == swarm_name and m.role in ("leader", "worker")
        ]
        if not members:
            return ""
        # If there is already a leader member, pick them
        leaders = [m for m in members if m.role == "leader"]
        if leaders:
            chosen = leaders[0]
        else:
            # Elect first joined worker
            members.sort(key=lambda m: m.joined_at)
            chosen = members[0]
            chosen.role = "leader"
        swarm.leader = chosen.agent_id
        self._record(swarm_name, "leader_elected", {
            "agent_id": chosen.agent_id,
        })
        self._fire("leader_elected", {
            "swarm_name": swarm_name, "agent_id": chosen.agent_id,
        })
        return chosen.agent_id

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def assign_task(self, swarm_name: str, agent_id: str,
                    task_name: str, priority: int = 5) -> str:
        swarm = self._find_swarm(swarm_name)
        if swarm is None:
            return ""
        if not task_name or not agent_id:
            return ""
        # Verify agent is a member
        is_member = any(
            m.swarm_name == swarm_name and m.agent_id == agent_id
            for m in self._members.values()
        )
        if not is_member:
            return ""
        self._seq += 1
        raw = f"stk-{swarm_name}-{agent_id}-{task_name}-{self._seq}"
        tid = "stk-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        task = _SwarmTask(
            task_id=tid, swarm_name=swarm_name, agent_id=agent_id,
            task_name=task_name, priority=priority, status="pending",
            reason="", created_at=time.time(), completed_at=0.0,
        )
        self._tasks[tid] = task
        self._stats["total_tasks_assigned"] += 1
        self._record(swarm_name, "task_assigned", {
            "task_id": tid, "agent_id": agent_id, "task_name": task_name,
        })
        self._fire("task_assigned", {
            "swarm_name": swarm_name, "task_id": tid, "agent_id": agent_id,
        })
        return tid

    def complete_task(self, swarm_name: str, task_id: str) -> bool:
        swarm = self._find_swarm(swarm_name)
        if swarm is None:
            return False
        task = self._tasks.get(task_id)
        if task is None or task.swarm_name != swarm_name:
            return False
        if task.status not in ("pending", "running"):
            return False
        task.status = "completed"
        task.completed_at = time.time()
        self._stats["total_tasks_completed"] += 1
        self._record(swarm_name, "task_completed", {"task_id": task_id})
        self._fire("task_completed", {
            "swarm_name": swarm_name, "task_id": task_id,
        })
        return True

    def fail_task(self, swarm_name: str, task_id: str,
                  reason: str = "") -> bool:
        swarm = self._find_swarm(swarm_name)
        if swarm is None:
            return False
        task = self._tasks.get(task_id)
        if task is None or task.swarm_name != swarm_name:
            return False
        if task.status not in ("pending", "running"):
            return False
        task.status = "failed"
        task.reason = reason
        task.completed_at = time.time()
        self._stats["total_tasks_failed"] += 1
        self._record(swarm_name, "task_failed", {
            "task_id": task_id, "reason": reason,
        })
        self._fire("task_failed", {
            "swarm_name": swarm_name, "task_id": task_id, "reason": reason,
        })
        return True

    # ------------------------------------------------------------------
    # Progress & Broadcast
    # ------------------------------------------------------------------

    def get_swarm_progress(self, name: str) -> Dict:
        swarm = self._find_swarm(name)
        if swarm is None:
            return {}
        tasks = [t for t in self._tasks.values() if t.swarm_name == name]
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == "completed")
        failed = sum(1 for t in tasks if t.status == "failed")
        pending = total - completed - failed
        pct = (completed / total * 100.0) if total > 0 else 0.0
        return {
            "swarm_name": name,
            "completion_pct": round(pct, 2),
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
        }

    def broadcast(self, swarm_name: str, message: str,
                  sender: str = "") -> int:
        swarm = self._find_swarm(swarm_name)
        if swarm is None:
            return 0
        if not message:
            return 0
        members = [
            m for m in self._members.values() if m.swarm_name == swarm_name
        ]
        count = len(members)
        self._stats["total_broadcasts"] += 1
        self._record(swarm_name, "broadcast", {
            "sender": sender, "message": message,
            "recipients": count,
        })
        self._fire("broadcast", {
            "swarm_name": swarm_name, "sender": sender,
            "message": message, "recipients": count,
        })
        return count

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50, **filters: Any) -> List[Dict]:
        results = []
        swarm_name = filters.get("swarm_name", "")
        action = filters.get("action", "")
        for ev in reversed(self._history):
            if swarm_name and ev.swarm_name != swarm_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "swarm_name": ev.swarm_name,
                "action": ev.action,
                "data": dict(ev.data),
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "current_swarms": len(self._swarms),
            "current_members": len(self._members),
            "current_tasks": len(self._tasks),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._swarms.clear()
        self._members.clear()
        self._tasks.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {
            "total_swarms_created": 0,
            "total_members_joined": 0,
            "total_tasks_assigned": 0,
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
            "total_broadcasts": 0,
        }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _find_swarm(self, name: str) -> Optional[_Swarm]:
        for s in self._swarms.values():
            if s.name == name:
                return s
        return None

    def _record(self, swarm_name: str, action: str,
                data: Dict[str, Any]) -> None:
        self._seq += 1
        raw = f"evt-{swarm_name}-{action}-{self._seq}"
        eid = "evt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        ev = _SwarmEvent(
            event_id=eid, swarm_name=swarm_name, action=action,
            data=dict(data), timestamp=time.time(),
        )
        self._history.append(ev)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
