"""Agent Collaboration Graph – track collaboration relationships between agents.

Builds a weighted directed graph where edges represent collaboration strength
based on shared tasks, communication frequency, and trust scores.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


@dataclass
class _GraphAgent:
    node_id: str
    agent_id: str
    tags: List[str]
    created_at: float


@dataclass
class _CollabEdge:
    edge_id: str
    from_agent: str
    to_agent: str
    weight: float
    interaction_count: int
    contexts: List[str]
    first_at: float
    last_at: float


@dataclass
class _GraphEvent:
    event_id: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class AgentCollaborationGraph:
    """Track collaboration relationships between agents as a weighted directed graph."""

    def __init__(self, max_agents: int = 5000, max_history: int = 100000):
        self._max_agents = max(1, max_agents)
        self._max_history = max(1, max_history)
        self._agents: Dict[str, _GraphAgent] = {}
        self._agent_index: Dict[str, str] = {}  # agent_id -> node_id
        self._edges: Dict[Tuple[str, str], _CollabEdge] = {}  # (from_id, to_id) -> edge
        self._history: List[_GraphEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._total_agents_added = 0
        self._total_collaborations_added = 0
        self._total_removed_agents = 0
        self._total_removed_collaborations = 0

    # --- ID Generation ---

    def _make_id(self, prefix: str, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # --- History ---

    def _record(self, action: str, data: Dict[str, Any]) -> None:
        eid = self._make_id("evt-", action)
        event = _GraphEvent(event_id=eid, action=action, data=data, timestamp=time.time())
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._fire(action, data)

    # --- Agent Management ---

    def add_agent(self, agent_id: str, tags: Optional[List[str]] = None) -> str:
        """Register an agent node in the graph. Returns node_id or empty string."""
        if not agent_id:
            return ""
        if agent_id in self._agent_index:
            return ""
        if len(self._agents) >= self._max_agents:
            return ""
        nid = self._make_id("acg-", agent_id)
        now = time.time()
        agent = _GraphAgent(node_id=nid, agent_id=agent_id, tags=tags or [], created_at=now)
        self._agents[nid] = agent
        self._agent_index[agent_id] = nid
        self._total_agents_added += 1
        self._record("agent_added", {"node_id": nid, "agent_id": agent_id})
        return nid

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent info including connection_count, total_weight, avg_weight."""
        nid = self._agent_index.get(agent_id)
        if not nid:
            return None
        agent = self._agents[nid]
        outgoing = [e for e in self._edges.values() if e.from_agent == agent_id]
        incoming = [e for e in self._edges.values() if e.to_agent == agent_id]
        all_edges = outgoing + incoming
        connection_count = len(all_edges)
        total_weight = sum(e.weight for e in all_edges)
        avg_weight = total_weight / connection_count if connection_count > 0 else 0.0
        return {
            "node_id": agent.node_id,
            "agent_id": agent.agent_id,
            "tags": list(agent.tags),
            "created_at": agent.created_at,
            "connection_count": connection_count,
            "total_weight": total_weight,
            "avg_weight": avg_weight,
        }

    def list_agents(self, tag: str = "") -> List[Dict[str, Any]]:
        """List all agents, optionally filtered by tag."""
        results = []
        for agent in self._agents.values():
            if tag and tag not in agent.tags:
                continue
            info = self.get_agent(agent.agent_id)
            if info:
                results.append(info)
        return results

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent and all its collaborations."""
        nid = self._agent_index.pop(agent_id, None)
        if not nid:
            return False
        self._agents.pop(nid, None)
        # Remove all edges involving this agent
        keys_to_remove = [
            k for k in self._edges
            if k[0] == agent_id or k[1] == agent_id
        ]
        for k in keys_to_remove:
            self._edges.pop(k, None)
            self._total_removed_collaborations += 1
        self._total_removed_agents += 1
        self._record("agent_removed", {"agent_id": agent_id})
        return True

    # --- Collaboration Management ---

    def add_collaboration(
        self,
        from_agent: str,
        to_agent: str,
        weight: float = 1.0,
        context: str = "",
    ) -> str:
        """Add or strengthen a collaboration edge. Returns edge_id or empty string."""
        if from_agent not in self._agent_index or to_agent not in self._agent_index:
            return ""
        if from_agent == to_agent:
            return ""
        if weight <= 0:
            return ""
        key = (from_agent, to_agent)
        now = time.time()
        existing = self._edges.get(key)
        if existing:
            existing.weight += weight
            existing.interaction_count += 1
            existing.last_at = now
            if context and context not in existing.contexts:
                existing.contexts.append(context)
            self._total_collaborations_added += 1
            self._record("collaboration_strengthened", {
                "edge_id": existing.edge_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "new_weight": existing.weight,
            })
            return existing.edge_id
        eid = self._make_id("col-", f"{from_agent}-{to_agent}")
        contexts = [context] if context else []
        edge = _CollabEdge(
            edge_id=eid,
            from_agent=from_agent,
            to_agent=to_agent,
            weight=weight,
            interaction_count=1,
            contexts=contexts,
            first_at=now,
            last_at=now,
        )
        self._edges[key] = edge
        self._total_collaborations_added += 1
        self._record("collaboration_added", {
            "edge_id": eid,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "weight": weight,
        })
        return eid

    def get_collaboration(self, from_agent: str, to_agent: str) -> Optional[Dict[str, Any]]:
        """Get collaboration details between two agents."""
        edge = self._edges.get((from_agent, to_agent))
        if not edge:
            return None
        return {
            "edge_id": edge.edge_id,
            "from_agent": edge.from_agent,
            "to_agent": edge.to_agent,
            "weight": edge.weight,
            "interaction_count": edge.interaction_count,
            "contexts": list(edge.contexts),
            "first_at": edge.first_at,
            "last_at": edge.last_at,
        }

    def remove_collaboration(self, from_agent: str, to_agent: str) -> bool:
        """Remove a collaboration edge."""
        key = (from_agent, to_agent)
        if key not in self._edges:
            return False
        self._edges.pop(key)
        self._total_removed_collaborations += 1
        self._record("collaboration_removed", {
            "from_agent": from_agent,
            "to_agent": to_agent,
        })
        return True

    # --- Query Methods ---

    def get_agent_connections(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get all outgoing collaborations for an agent."""
        if agent_id not in self._agent_index:
            return []
        results = []
        for edge in self._edges.values():
            if edge.from_agent == agent_id:
                results.append({
                    "edge_id": edge.edge_id,
                    "from_agent": edge.from_agent,
                    "to_agent": edge.to_agent,
                    "weight": edge.weight,
                    "interaction_count": edge.interaction_count,
                    "contexts": list(edge.contexts),
                    "first_at": edge.first_at,
                    "last_at": edge.last_at,
                })
        return results

    def get_most_collaborative(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get agents sorted by total collaboration weight (incoming + outgoing)."""
        weight_map: Dict[str, float] = {}
        for edge in self._edges.values():
            weight_map[edge.from_agent] = weight_map.get(edge.from_agent, 0.0) + edge.weight
            weight_map[edge.to_agent] = weight_map.get(edge.to_agent, 0.0) + edge.weight
        sorted_agents = sorted(weight_map.items(), key=lambda x: x[1], reverse=True)
        results = []
        for agent_id, total_weight in sorted_agents[:limit]:
            info = self.get_agent(agent_id)
            if info:
                results.append(info)
        return results

    def get_strongest_pairs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top agent pairs sorted by collaboration weight."""
        sorted_edges = sorted(self._edges.values(), key=lambda e: e.weight, reverse=True)
        results = []
        for edge in sorted_edges[:limit]:
            results.append({
                "from_agent": edge.from_agent,
                "to_agent": edge.to_agent,
                "weight": edge.weight,
                "interaction_count": edge.interaction_count,
                "contexts": list(edge.contexts),
            })
        return results

    def get_clusters(self, min_weight: float = 2.0) -> List[List[str]]:
        """Find clusters of strongly connected agents using BFS on undirected edges >= min_weight."""
        # Build undirected adjacency for edges meeting threshold
        adj: Dict[str, Set[str]] = {}
        for edge in self._edges.values():
            if edge.weight >= min_weight:
                adj.setdefault(edge.from_agent, set()).add(edge.to_agent)
                adj.setdefault(edge.to_agent, set()).add(edge.from_agent)
        visited: Set[str] = set()
        clusters: List[List[str]] = []
        for start in adj:
            if start in visited:
                continue
            # BFS
            cluster: List[str] = []
            queue = [start]
            visited.add(start)
            while queue:
                current = queue.pop(0)
                cluster.append(current)
                for neighbor in adj.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(cluster) >= 2:
                clusters.append(sorted(cluster))
        return clusters

    def get_isolated_agents(self) -> List[Dict[str, Any]]:
        """Get agents with no collaborations (no incoming or outgoing edges)."""
        connected: Set[str] = set()
        for edge in self._edges.values():
            connected.add(edge.from_agent)
            connected.add(edge.to_agent)
        results = []
        for agent in self._agents.values():
            if agent.agent_id not in connected:
                info = self.get_agent(agent.agent_id)
                if info:
                    results.append(info)
        return results

    # --- Standard Interface ---

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent history events."""
        entries = self._history[-limit:] if limit > 0 else self._history
        results = []
        for evt in reversed(entries):
            results.append({
                "event_id": evt.event_id,
                "action": evt.action,
                "data": evt.data,
                "timestamp": evt.timestamp,
            })
        return results

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Notify all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return {
            "current_agents": len(self._agents),
            "current_edges": len(self._edges),
            "total_agents_added": self._total_agents_added,
            "total_collaborations_added": self._total_collaborations_added,
            "total_removed_agents": self._total_removed_agents,
            "total_removed_collaborations": self._total_removed_collaborations,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._agents.clear()
        self._agent_index.clear()
        self._edges.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_agents_added = 0
        self._total_collaborations_added = 0
        self._total_removed_agents = 0
        self._total_removed_collaborations = 0
