"""Manages workflow execution graphs (nodes and edges)."""

import copy
import time
import hashlib
import dataclasses
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentWorkflowGraphState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowGraph:
    """Manages workflow execution graphs (nodes and edges)."""

    PREFIX = "awgr-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowGraphState()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("_seq_num", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, event: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._callbacks

    @on_change.setter
    def on_change(self, value: dict):
        self._callbacks = value

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # --- Graph Management ---

    def create_graph(self, workflow_id: str, label: str = "") -> str:
        """Create a new workflow execution graph. Returns graph ID."""
        if not workflow_id:
            return ""
        graph_id = self._generate_id(f"{workflow_id}{label}{time.time()}")
        seq_num = self._state._seq
        entry = {
            "graph_id": graph_id,
            "workflow_id": workflow_id,
            "label": label,
            "nodes": {},
            "edges": [],
            "created_at": time.time(),
            "_seq_num": seq_num,
        }
        self._state.entries[graph_id] = entry
        self._prune()
        self._fire("graph_created", {"graph_id": graph_id, "workflow_id": workflow_id})
        return graph_id

    def add_node(self, graph_id: str, node_name: str, metadata: dict = None) -> bool:
        """Add a node to a graph."""
        entry = self._state.entries.get(graph_id)
        if not entry:
            return False
        if not node_name:
            return False
        if node_name in entry["nodes"]:
            return False
        entry["nodes"][node_name] = {
            "name": node_name,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "added_at": time.time(),
        }
        self._fire("node_added", {"graph_id": graph_id, "node_name": node_name})
        return True

    def add_edge(self, graph_id: str, from_node: str, to_node: str) -> bool:
        """Add an edge between two nodes in a graph."""
        entry = self._state.entries.get(graph_id)
        if not entry:
            return False
        if from_node not in entry["nodes"] or to_node not in entry["nodes"]:
            return False
        # Check for duplicate edge
        for edge in entry["edges"]:
            if edge["from"] == from_node and edge["to"] == to_node:
                return False
        entry["edges"].append({
            "from": from_node,
            "to": to_node,
            "added_at": time.time(),
        })
        self._fire("edge_added", {"graph_id": graph_id, "from_node": from_node, "to_node": to_node})
        return True

    def get_graph(self, graph_id: str) -> Optional[dict]:
        """Retrieve a single graph by ID."""
        entry = self._state.entries.get(graph_id)
        if not entry:
            return None
        return {
            "graph_id": entry["graph_id"],
            "workflow_id": entry["workflow_id"],
            "label": entry["label"],
            "nodes": {k: dict(v) for k, v in entry["nodes"].items()},
            "edges": [dict(e) for e in entry["edges"]],
            "created_at": entry["created_at"],
        }

    def get_graphs(self, workflow_id: str = "", limit: int = 50) -> List[dict]:
        """Retrieve graphs, newest first (sorted by created_at and _seq)."""
        results = list(self._state.entries.values())
        if workflow_id:
            results = [e for e in results if e["workflow_id"] == workflow_id]
        results.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq_num", 0)), reverse=True)
        out = []
        for e in results[:limit]:
            out.append({
                "graph_id": e["graph_id"],
                "workflow_id": e["workflow_id"],
                "label": e["label"],
                "node_count": len(e["nodes"]),
                "edge_count": len(e["edges"]),
                "created_at": e["created_at"],
            })
        return out

    def get_graph_count(self, workflow_id: str = "") -> int:
        """Count graphs matching optional workflow filter."""
        if not workflow_id:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if e["workflow_id"] == workflow_id:
                count += 1
        return count

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        total_nodes = 0
        total_edges = 0
        for e in self._state.entries.values():
            total_nodes += len(e["nodes"])
            total_edges += len(e["edges"])
        return {
            "total_graphs": len(self._state.entries),
            "total_nodes": total_nodes,
            "total_edges": total_edges,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowGraphState()
        self._callbacks.clear()
        self._fire("reset", {})
