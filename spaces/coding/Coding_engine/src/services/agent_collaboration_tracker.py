"""Agent collaboration tracker - track and analyze inter-agent collaborations."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class Collaboration:
    """A collaboration session between agents."""
    collab_id: str = ""
    name: str = ""
    agents: list = field(default_factory=list)
    collab_type: str = ""
    status: str = "active"
    messages: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: float = 0.0
    ended_at: float = 0.0
    result: str = ""


@dataclass
class CollabMessage:
    """A message within a collaboration."""
    message_id: str = ""
    collab_id: str = ""
    sender: str = ""
    content: str = ""
    msg_type: str = "message"
    timestamp: float = 0.0


class AgentCollaborationTracker:
    """Track collaborations between agents."""

    COLLAB_TYPES = (
        "pair", "group", "review", "handoff",
        "consensus", "debate", "delegation", "custom",
    )

    STATUSES = ("active", "completed", "failed", "cancelled")

    MSG_TYPES = ("message", "proposal", "vote", "decision", "question", "answer", "update")

    def __init__(self, max_collabs: int = 50000, max_messages_per_collab: int = 1000):
        self._max_collabs = max(1, max_collabs)
        self._max_messages = max(1, max_messages_per_collab)
        self._collabs: Dict[str, Collaboration] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_created": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_messages": 0,
        }

    # --- Collaboration Management ---

    def create_collaboration(
        self,
        name: str,
        agents: List[str],
        collab_type: str = "pair",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a new collaboration session."""
        if not name or not agents:
            return ""
        if collab_type not in self.COLLAB_TYPES:
            return ""
        if len(agents) < 2:
            return ""
        if len(self._collabs) >= self._max_collabs:
            return ""

        cid = f"collab-{uuid.uuid4().hex[:12]}"
        self._collabs[cid] = Collaboration(
            collab_id=cid,
            name=name,
            agents=list(agents),
            collab_type=collab_type,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            created_at=time.time(),
        )
        self._stats["total_created"] += 1
        self._fire("collab_created", {"collab_id": cid, "name": name, "agents": list(agents)})
        return cid

    def get_collaboration(self, collab_id: str) -> Optional[Dict]:
        """Get collaboration details."""
        c = self._collabs.get(collab_id)
        if not c:
            return None
        return {
            "collab_id": c.collab_id,
            "name": c.name,
            "agents": list(c.agents),
            "collab_type": c.collab_type,
            "status": c.status,
            "message_count": len(c.messages),
            "tags": list(c.tags),
            "result": c.result,
            "created_at": c.created_at,
            "ended_at": c.ended_at,
        }

    def end_collaboration(self, collab_id: str, status: str = "completed", result: str = "") -> bool:
        """End a collaboration session."""
        c = self._collabs.get(collab_id)
        if not c or c.status != "active":
            return False
        if status not in ("completed", "failed", "cancelled"):
            return False

        c.status = status
        c.result = result
        c.ended_at = time.time()

        if status == "completed":
            self._stats["total_completed"] += 1
        elif status == "failed":
            self._stats["total_failed"] += 1

        self._fire(f"collab_{status}", {"collab_id": collab_id})
        return True

    def remove_collaboration(self, collab_id: str) -> bool:
        """Remove a collaboration."""
        if collab_id not in self._collabs:
            return False
        del self._collabs[collab_id]
        return True

    # --- Messages ---

    def send_message(
        self,
        collab_id: str,
        sender: str,
        content: str,
        msg_type: str = "message",
    ) -> str:
        """Send a message within a collaboration."""
        c = self._collabs.get(collab_id)
        if not c or c.status != "active":
            return ""
        if not sender or not content:
            return ""
        if msg_type not in self.MSG_TYPES:
            return ""
        if sender not in c.agents:
            return ""

        mid = f"msg-{uuid.uuid4().hex[:12]}"
        msg = CollabMessage(
            message_id=mid,
            collab_id=collab_id,
            sender=sender,
            content=content,
            msg_type=msg_type,
            timestamp=time.time(),
        )

        c.messages.append(msg)
        if len(c.messages) > self._max_messages:
            c.messages = c.messages[-self._max_messages:]

        self._stats["total_messages"] += 1
        self._fire("message_sent", {"collab_id": collab_id, "sender": sender, "msg_type": msg_type})
        return mid

    def get_messages(
        self,
        collab_id: str,
        sender: str = "",
        msg_type: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """Get messages from a collaboration."""
        c = self._collabs.get(collab_id)
        if not c:
            return []

        results = []
        for m in reversed(c.messages):
            if sender and m.sender != sender:
                continue
            if msg_type and m.msg_type != msg_type:
                continue
            results.append({
                "message_id": m.message_id,
                "sender": m.sender,
                "content": m.content,
                "msg_type": m.msg_type,
                "timestamp": m.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    # --- Queries ---

    def list_collaborations(
        self,
        status: str = "",
        collab_type: str = "",
        agent: str = "",
        tag: str = "",
    ) -> List[Dict]:
        """List collaborations with filters."""
        results = []
        for c in self._collabs.values():
            if status and c.status != status:
                continue
            if collab_type and c.collab_type != collab_type:
                continue
            if agent and agent not in c.agents:
                continue
            if tag and tag not in c.tags:
                continue
            results.append({
                "collab_id": c.collab_id,
                "name": c.name,
                "agents": list(c.agents),
                "collab_type": c.collab_type,
                "status": c.status,
                "message_count": len(c.messages),
            })
        return results

    def get_active_collaborations(self) -> List[Dict]:
        """Get all active collaborations."""
        return self.list_collaborations(status="active")

    def get_agent_collaborations(self, agent: str) -> List[Dict]:
        """Get all collaborations for an agent."""
        return self.list_collaborations(agent=agent)

    def get_agent_partners(self, agent: str) -> Dict[str, int]:
        """Get agents that have collaborated with the given agent and count."""
        partners: Dict[str, int] = {}
        for c in self._collabs.values():
            if agent in c.agents:
                for a in c.agents:
                    if a != agent:
                        partners[a] = partners.get(a, 0) + 1
        return partners

    def get_agent_stats(self, agent: str) -> Dict:
        """Get collaboration statistics for an agent."""
        total = 0
        active = 0
        completed = 0
        messages_sent = 0

        for c in self._collabs.values():
            if agent not in c.agents:
                continue
            total += 1
            if c.status == "active":
                active += 1
            elif c.status == "completed":
                completed += 1
            for m in c.messages:
                if m.sender == agent:
                    messages_sent += 1

        if total == 0:
            return {}

        return {
            "agent": agent,
            "total_collaborations": total,
            "active": active,
            "completed": completed,
            "messages_sent": messages_sent,
        }

    def get_most_active_agents(self, limit: int = 10) -> List[Dict]:
        """Get most active collaborating agents."""
        agent_counts: Dict[str, int] = {}
        for c in self._collabs.values():
            for a in c.agents:
                agent_counts[a] = agent_counts.get(a, 0) + 1

        ranked = sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"agent": a, "collab_count": cnt} for a, cnt in ranked[:limit]]

    def get_collab_type_summary(self) -> List[Dict]:
        """Get summary by collaboration type."""
        type_counts: Dict[str, Dict] = {}
        for c in self._collabs.values():
            if c.collab_type not in type_counts:
                type_counts[c.collab_type] = {"count": 0, "active": 0, "completed": 0}
            type_counts[c.collab_type]["count"] += 1
            if c.status == "active":
                type_counts[c.collab_type]["active"] += 1
            elif c.status == "completed":
                type_counts[c.collab_type]["completed"] += 1

        return [
            {"collab_type": ct, **data}
            for ct, data in sorted(type_counts.items())
        ]

    # --- Callbacks ---

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # --- Stats ---

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_collabs": len(self._collabs),
            "active_collabs": sum(1 for c in self._collabs.values() if c.status == "active"),
        }

    def reset(self) -> None:
        self._collabs.clear()
        self._callbacks.clear()
        self._stats = {
            "total_created": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_messages": 0,
        }

    # --- Internal ---

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
