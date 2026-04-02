"""
IdeaJournal - Collection of explored idea connections.

Adapted from AI-Scientist-v2's journal.py Journal class.
Manages the tree of discovered connections during exploration.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
import json
import logging

from .idea_node import IdeaNode, ConnectionType

logger = logging.getLogger(__name__)


@dataclass
class ExplorationSession:
    """
    Tracks a single exploration session.

    A session starts when user says "Finde Verbindungen" and ends
    when exploration completes or is stopped.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    root_bubble_id: str = field(default="")
    root_bubble_title: str = field(default="")
    exploration_query: str = field(default="")  # Original user request
    status: str = field(default="running")  # running, completed, paused, stopped
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = field(default=None)
    current_stage: int = field(default=1)  # 1-4
    total_nodes_explored: int = field(default=0)
    best_score: float = field(default=0.0)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "root_bubble_id": self.root_bubble_id,
            "root_bubble_title": self.root_bubble_title,
            "exploration_query": self.exploration_query,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "current_stage": self.current_stage,
            "total_nodes_explored": self.total_nodes_explored,
            "best_score": self.best_score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExplorationSession":
        return cls(**data)


@dataclass
class IdeaJournal:
    """
    Collection of explored idea connections.

    Manages the tree structure of discovered connections,
    provides methods for finding best connections, and
    supports serialization for persistence.
    """

    nodes: List[IdeaNode] = field(default_factory=list)
    session: Optional[ExplorationSession] = field(default=None)

    # ---- Node Access ----

    def __getitem__(self, idx: int) -> IdeaNode:
        return self.nodes[idx]

    def __len__(self) -> int:
        return len(self.nodes)

    def append(self, node: IdeaNode) -> None:
        """Add a new node to the journal."""
        node.step = len(self.nodes)
        self.nodes.append(node)

        # Update session stats
        if self.session:
            self.session.total_nodes_explored = len(self.nodes)
            if node.combined_score > self.session.best_score:
                self.session.best_score = node.combined_score

    def get_node_by_id(self, node_id: str) -> Optional[IdeaNode]:
        """Find a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    # ---- Node Filtering ----

    @property
    def root_nodes(self) -> List[IdeaNode]:
        """Get all nodes without a parent (starting points)."""
        return [n for n in self.nodes if n.parent is None]

    @property
    def leaf_nodes(self) -> List[IdeaNode]:
        """Get all nodes without children."""
        return [n for n in self.nodes if n.is_leaf]

    @property
    def valid_nodes(self) -> List[IdeaNode]:
        """Get all valid (non-rejected) nodes."""
        return [n for n in self.nodes if n.is_valid and not n.is_rejected]

    @property
    def accepted_nodes(self) -> List[IdeaNode]:
        """Get all user-accepted nodes."""
        return [n for n in self.nodes if n.is_accepted]

    def get_nodes_by_depth(self, depth: int) -> List[IdeaNode]:
        """Get all nodes at a specific exploration depth."""
        return [n for n in self.nodes if n.exploration_depth == depth]

    def get_nodes_by_stage(self, stage_name: str) -> List[IdeaNode]:
        """Get all nodes from a specific stage."""
        return [n for n in self.nodes if n.stage_name == stage_name]

    def get_nodes_by_type(self, connection_type: ConnectionType) -> List[IdeaNode]:
        """Get all nodes of a specific connection type."""
        return [n for n in self.nodes if n.connection_type == connection_type]

    # ---- Best Node Selection ----

    def get_best_nodes(
        self,
        top_k: int = 5,
        only_valid: bool = True,
        min_score: float = 0.0
    ) -> List[IdeaNode]:
        """
        Get the top-k best connections by combined score.

        Args:
            top_k: Number of nodes to return
            only_valid: Only include valid nodes
            min_score: Minimum score threshold

        Returns:
            List of best nodes sorted by score descending
        """
        logger.debug("get_best_nodes: top_k=%s, only_valid=%s, min_score=%s",
                     top_k, only_valid, min_score)
        nodes = self.valid_nodes if only_valid else self.nodes
        nodes = [n for n in nodes if n.combined_score >= min_score]
        nodes.sort(key=lambda n: n.combined_score, reverse=True)
        return nodes[:top_k]

    def get_best_node(self, only_valid: bool = True) -> Optional[IdeaNode]:
        """Get the single best node."""
        best = self.get_best_nodes(top_k=1, only_valid=only_valid)
        return best[0] if best else None

    def get_best_node_for_expansion(self) -> Optional[IdeaNode]:
        """
        Get the best leaf node for tree expansion.

        This is used by the BFTS algorithm to decide which
        node to expand next.
        """
        leaf_nodes = [n for n in self.valid_nodes if n.is_leaf]
        if not leaf_nodes:
            return None
        return max(leaf_nodes, key=lambda n: n.combined_score)

    # ---- Connection Deduplication ----

    def connection_exists(self, source_id: str, target_id: str) -> bool:
        """Check if a connection already exists (in either direction)."""
        for node in self.nodes:
            if (node.source_bubble_id == source_id and node.target_bubble_id == target_id):
                return True
            if (node.source_bubble_id == target_id and node.target_bubble_id == source_id):
                return True
        return False

    def get_connected_bubble_ids(self, bubble_id: str) -> List[str]:
        """Get all bubble IDs connected to the given bubble."""
        connected = set()
        for node in self.valid_nodes:
            if node.source_bubble_id == bubble_id:
                connected.add(node.target_bubble_id)
            if node.target_bubble_id == bubble_id:
                connected.add(node.source_bubble_id)
        return list(connected)

    # ---- Tree Traversal ----

    def get_path_to_root(self, node: IdeaNode) -> List[IdeaNode]:
        """Get the path from a node back to its root."""
        logger.debug("get_path_to_root: node_id=%s", node.id)
        path = [node]
        current = node
        while current.parent is not None:
            current = current.parent
            path.append(current)
        path.reverse()
        return path

    def get_subtree(self, node: IdeaNode) -> List[IdeaNode]:
        """Get all nodes in the subtree rooted at the given node."""
        result = [node]
        for child in node.children:
            result.extend(self.get_subtree(child))
        return result

    # ---- Statistics ----

    def get_stats(self) -> Dict[str, Any]:
        """Get exploration statistics."""
        logger.debug("get_stats: total_nodes=%s", len(self.nodes))
        if not self.nodes:
            return {
                "total_nodes": 0,
                "valid_nodes": 0,
                "accepted_nodes": 0,
                "best_score": 0.0,
                "avg_score": 0.0,
                "depths": {},
                "types": {},
            }

        valid = self.valid_nodes
        scores = [n.combined_score for n in valid]

        # Count by depth
        depths = {}
        for n in self.nodes:
            d = n.exploration_depth
            depths[d] = depths.get(d, 0) + 1

        # Count by type
        types = {}
        for n in self.nodes:
            t = n.connection_type.value
            types[t] = types.get(t, 0) + 1

        return {
            "total_nodes": len(self.nodes),
            "valid_nodes": len(valid),
            "accepted_nodes": len(self.accepted_nodes),
            "best_score": max(scores) if scores else 0.0,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "depths": depths,
            "types": types,
        }

    # ---- Serialization ----

    def to_dict(self) -> Dict[str, Any]:
        """Convert journal to dictionary for serialization."""
        return {
            "session": self.session.to_dict() if self.session else None,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdeaJournal":
        """Create journal from dictionary."""
        journal = cls()

        # Restore session
        if data.get("session"):
            journal.session = ExplorationSession.from_dict(data["session"])

        # First pass: create all nodes without relationships
        node_map = {}
        for node_data in data.get("nodes", []):
            node = IdeaNode.from_dict(node_data.copy())
            node_map[node.id] = node
            journal.nodes.append(node)

        # Second pass: restore parent-child relationships
        for node_data, node in zip(data.get("nodes", []), journal.nodes):
            parent_id = node_data.get("parent_id")
            if parent_id and parent_id in node_map:
                node.parent = node_map[parent_id]
                node.parent.children.add(node)

        return journal

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "IdeaJournal":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ---- Export Formats ----

    def to_edges_list(self) -> List[Dict[str, Any]]:
        """
        Export all valid connections as edge dictionaries.
        Suitable for inserting into VibeMind's discovered_edges table.
        """
        return [n.to_edge_dict() for n in self.valid_nodes]

    def to_visualization_data(self) -> Dict[str, Any]:
        """
        Export data for Electron 3D visualization.
        """
        return {
            "session_id": self.session.id if self.session else None,
            "root_bubble_id": self.session.root_bubble_id if self.session else None,
            "status": self.session.status if self.session else "unknown",
            "stats": self.get_stats(),
            "connections": [n.to_visualization_dict() for n in self.valid_nodes],
            "best_connections": [n.to_visualization_dict() for n in self.get_best_nodes(top_k=5)],
        }

    # ---- Summary Generation ----

    def generate_summary(self, include_reasoning: bool = True) -> str:
        """
        Generate a text summary of exploration results.
        Suitable for voice feedback.
        """
        if not self.nodes:
            return "Keine Verbindungen gefunden."

        stats = self.get_stats()
        best = self.get_best_nodes(top_k=3)

        summary_parts = [
            f"Ich habe {stats['total_nodes']} Verbindungen entdeckt.",
        ]

        if best:
            summary_parts.append(f"Die {len(best)} besten Verbindungen sind:")
            for i, node in enumerate(best, 1):
                connection_text = f"{i}. '{node.source_bubble_title}' und '{node.target_bubble_title}'"
                if node.edge_label:
                    connection_text += f" ({node.edge_label})"
                if include_reasoning and node.reasoning:
                    # Truncate reasoning for voice
                    reasoning = node.reasoning[:100] + "..." if len(node.reasoning) > 100 else node.reasoning
                    connection_text += f" - {reasoning}"
                summary_parts.append(connection_text)

        return " ".join(summary_parts)
