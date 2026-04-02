"""
IdeaNode - Single node in the idea exploration tree.

Adapted from AI-Scientist-v2's journal.py Node class.
Instead of code experiments, each node represents a discovered
connection between two bubbles/ideas.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Set, Dict, Any, List
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    """Types of connections that can be discovered between ideas."""
    SEMANTIC = "semantic"       # Similar meaning/content
    CAUSAL = "causal"          # One causes/leads to another
    TEMPORAL = "temporal"      # Time-based relationship
    HIERARCHICAL = "hierarchical"  # Parent-child relationship
    CONTRAST = "contrast"      # Opposing or contrasting ideas
    CREATIVE = "creative"      # Novel/non-obvious connection
    DEPENDENCY = "dependency"  # One depends on another
    ELABORATION = "elaboration"  # One elaborates on another


@dataclass(eq=False)
class IdeaNode:
    """
    A single node in the idea exploration tree.

    Represents a discovered connection between two bubbles/ideas,
    with scoring and reasoning about why they're connected.
    """

    # ---- Identity ----
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    step: int = field(default=0)
    ctime: float = field(default_factory=time.time)

    # ---- Connection Details ----
    source_bubble_id: str = field(default="")
    source_bubble_title: str = field(default="")
    target_bubble_id: str = field(default="")
    target_bubble_title: str = field(default="")

    # ---- Connection Metadata ----
    connection_type: ConnectionType = field(default=ConnectionType.SEMANTIC)
    reasoning: str = field(default="")  # LLM-generated explanation
    edge_label: str = field(default="")  # Short label for visualization

    # ---- Scoring ----
    embedding_similarity: float = field(default=0.0)  # 0-1, from EmbeddingService
    llm_confidence: float = field(default=0.0)        # 0-1, from LLM evaluation
    combined_score: float = field(default=0.0)        # Weighted combination

    # ---- Tree Structure ----
    parent: Optional["IdeaNode"] = field(default=None, repr=False)
    children: Set["IdeaNode"] = field(default_factory=set, repr=False)
    exploration_depth: int = field(default=1)  # How many hops from root

    # ---- Status ----
    is_accepted: bool = field(default=False)  # User accepted this connection
    is_rejected: bool = field(default=False)  # User rejected this connection
    is_valid: bool = field(default=True)      # Connection is valid/makes sense

    # ---- Metadata ----
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize node and add to parent's children if applicable."""
        if isinstance(self.children, list):
            self.children = set(self.children)
        if self.parent is not None and not isinstance(self.parent, str):
            self.parent.children.add(self)
        # Calculate combined score if not set
        if self.combined_score == 0.0 and (self.embedding_similarity > 0 or self.llm_confidence > 0):
            self.calculate_combined_score()

    def calculate_combined_score(self, embedding_weight: float = 0.4, llm_weight: float = 0.6) -> float:
        """
        Calculate combined score from embedding similarity and LLM confidence.

        Args:
            embedding_weight: Weight for embedding similarity (default 0.4)
            llm_weight: Weight for LLM confidence (default 0.6)

        Returns:
            Combined score between 0 and 1
        """
        self.combined_score = (
            embedding_weight * self.embedding_similarity +
            llm_weight * self.llm_confidence
        )
        return self.combined_score

    @property
    def is_leaf(self) -> bool:
        """Check if this node has no children."""
        return not self.children

    @property
    def stage_name(self) -> str:
        """
        Return the exploration stage based on depth:
        - Stage 1: Direct connections (depth 1)
        - Stage 2: Indirect connections (depth 2)
        - Stage 3: Abstract patterns (depth 3)
        - Stage 4: Creative synthesis (depth 4+)
        """
        if self.exploration_depth <= 1:
            return "direct"
        elif self.exploration_depth == 2:
            return "indirect"
        elif self.exploration_depth == 3:
            return "abstract"
        else:
            return "creative"

    def __eq__(self, other):
        return isinstance(other, IdeaNode) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return (
            f"IdeaNode(id={self.id[:8]}, "
            f"'{self.source_bubble_title}' -> '{self.target_bubble_title}', "
            f"score={self.combined_score:.2f})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary for serialization."""
        return {
            "id": self.id,
            "step": self.step,
            "ctime": self.ctime,
            "source_bubble_id": self.source_bubble_id,
            "source_bubble_title": self.source_bubble_title,
            "target_bubble_id": self.target_bubble_id,
            "target_bubble_title": self.target_bubble_title,
            "connection_type": self.connection_type.value,
            "reasoning": self.reasoning,
            "edge_label": self.edge_label,
            "embedding_similarity": self.embedding_similarity,
            "llm_confidence": self.llm_confidence,
            "combined_score": self.combined_score,
            "exploration_depth": self.exploration_depth,
            "is_accepted": self.is_accepted,
            "is_rejected": self.is_rejected,
            "is_valid": self.is_valid,
            "parent_id": self.parent.id if self.parent else None,
            "children_ids": [c.id for c in self.children],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], journal: Optional["IdeaJournal"] = None) -> "IdeaNode":
        """Create an IdeaNode from a dictionary."""
        # Extract relationship IDs
        parent_id = data.pop("parent_id", None)
        children_ids = data.pop("children_ids", [])

        # Convert connection_type string to enum
        if "connection_type" in data and isinstance(data["connection_type"], str):
            data["connection_type"] = ConnectionType(data["connection_type"])

        # Create node
        node = cls(**data)

        # Restore relationships if journal provided
        if journal is not None and parent_id:
            parent = journal.get_node_by_id(parent_id)
            if parent:
                node.parent = parent
                parent.children.add(node)

        return node

    def to_edge_dict(self) -> Dict[str, Any]:
        """
        Convert to edge format for VibeMind canvas_edges table.
        """
        return {
            "from_idea_id": self.source_bubble_id,
            "to_idea_id": self.target_bubble_id,
            "edge_type": "discovered",
            "edge_label": self.edge_label,
            "reasoning": self.reasoning,
            "confidence": self.combined_score,
            "connection_type": self.connection_type.value,
            "metadata": json.dumps({
                "exploration_node_id": self.id,
                "embedding_similarity": self.embedding_similarity,
                "llm_confidence": self.llm_confidence,
                "exploration_depth": self.exploration_depth,
            }),
        }

    def to_visualization_dict(self) -> Dict[str, Any]:
        """
        Convert to format suitable for Electron 3D visualization.
        """
        return {
            "id": self.id,
            "from_bubble_id": self.source_bubble_id,
            "from_bubble_title": self.source_bubble_title,
            "to_bubble_id": self.target_bubble_id,
            "to_bubble_title": self.target_bubble_title,
            "edge_label": self.edge_label,
            "reasoning": self.reasoning,
            "confidence": self.combined_score,
            "connection_type": self.connection_type.value,
            "depth": self.exploration_depth,
            "is_accepted": self.is_accepted,
        }
