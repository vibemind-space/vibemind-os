"""
Rowboat Reader — Ingests published VibeMind bubble/idea data from Rowboat manifests.

Reads ~/.rowboat/vibemind/ideas/bubble--*.json files that the VibeMind
IdeasPublisher writes when ROWBOAT_PUBLISH_ENABLED=true.
"""

import json
import os
import glob
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RowboatIdea:
    """A single idea/note from a Rowboat manifest."""
    id: str
    title: str
    content: str = ""
    tags: List[str] = field(default_factory=list)
    node_type: str = "note"
    bubble_id: str = ""
    bubble_title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content[:200] if self.content else "",
            "tags": self.tags,
            "node_type": self.node_type,
            "bubble_id": self.bubble_id,
            "bubble_title": self.bubble_title,
        }


@dataclass
class RowboatBubble:
    """A bubble with its child ideas from a Rowboat manifest."""
    id: str
    title: str
    description: str = ""
    notes: List[RowboatIdea] = field(default_factory=list)
    edges: List[Dict[str, str]] = field(default_factory=list)
    published_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description[:200] if self.description else "",
            "note_count": len(self.notes),
            "edge_count": len(self.edges),
            "published_at": self.published_at,
        }


def _find_rowboat_dir() -> Optional[Path]:
    """Locate the Rowboat vibemind ideas directory."""
    env_path = os.environ.get("ROWBOAT_DATA_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    home = Path.home()
    default = home / ".rowboat" / "vibemind" / "ideas"
    if default.exists():
        return default

    return None


def read_all_manifests() -> Dict[str, Any]:
    """Read all Rowboat bubble manifests and return structured data.

    Returns:
        {
            "bubbles": List[RowboatBubble],
            "all_ideas": List[RowboatIdea],  # flattened across all bubbles
            "stats": {"bubble_count": int, "idea_count": int, "edge_count": int},
            "source_dir": str,
        }
    """
    rowboat_dir = _find_rowboat_dir()
    if rowboat_dir is None:
        logger.warning("Rowboat data directory not found (~/.rowboat/vibemind/ideas/)")
        return {
            "bubbles": [],
            "all_ideas": [],
            "stats": {"bubble_count": 0, "idea_count": 0, "edge_count": 0},
            "source_dir": None,
        }

    manifest_files = sorted(rowboat_dir.glob("bubble--*.json"))
    logger.info(f"[RowboatReader] Found {len(manifest_files)} manifests in {rowboat_dir}")

    bubbles = []
    all_ideas = []
    total_edges = 0

    for fpath in manifest_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            bubble_data = data.get("bubble", {})
            bubble = RowboatBubble(
                id=bubble_data.get("id", ""),
                title=bubble_data.get("title", fpath.stem),
                description=bubble_data.get("description", ""),
                published_at=data.get("published_at", ""),
                edges=data.get("edges", []),
            )

            for note in data.get("notes", []):
                idea = RowboatIdea(
                    id=note.get("id", ""),
                    title=note.get("title", ""),
                    content=note.get("content", ""),
                    tags=note.get("tags", []),
                    node_type=note.get("node_type", "note"),
                    bubble_id=bubble.id,
                    bubble_title=bubble.title,
                )
                bubble.notes.append(idea)
                all_ideas.append(idea)

            total_edges += len(bubble.edges)
            bubbles.append(bubble)

        except Exception as e:
            logger.error(f"[RowboatReader] Failed to read {fpath.name}: {e}")

    logger.info(
        f"[RowboatReader] Loaded {len(bubbles)} bubbles, "
        f"{len(all_ideas)} ideas, {total_edges} edges"
    )

    return {
        "bubbles": bubbles,
        "all_ideas": all_ideas,
        "stats": {
            "bubble_count": len(bubbles),
            "idea_count": len(all_ideas),
            "edge_count": total_edges,
        },
        "source_dir": str(rowboat_dir),
    }
