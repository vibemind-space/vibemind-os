"""
Ideas Space Workers

Workers for the Ideas Space:
- BubbleWorker: Bubble/space CRUD operations
- IdeaWorker: Idea management
- ScoreWorker: Bubble scoring and evaluation
"""

import logging
from typing import Any

from swarm.navigation import SpaceType
from swarm.event_buffer import TaskInfo
from swarm.workers.base_worker import BaseWorker, WorkerConfig

logger = logging.getLogger(__name__)


class BubbleWorker(BaseWorker):
    """
    Worker for bubble/space operations.

    Handles: create, list, enter, exit, delete bubbles
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="bubble_worker",
            space_type=SpaceType.IDEAS,
            description="Handles bubble/space CRUD operations",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute a bubble-related task."""
        text = task.input_event.text.lower()

        try:
            from spaces.ideas.adapted.bubble_tools import (
                list_bubbles, create_bubble, enter_bubble,
                exit_bubble, delete_bubble,
            )

            # Determine operation
            if "list" in text or "zeig" in text or "show" in text:
                await self._publish_progress(50, "Listing bubbles...")
                result = list_bubbles()

            elif "create" in text or "erstell" in text or "neu" in text:
                # Extract title (simple heuristic)
                title = self._extract_title(text)
                await self._publish_progress(50, f"Creating bubble: {title}")
                result = create_bubble(title=title)

            elif "enter" in text or "betret" in text or "geh" in text:
                bubble_name = self._extract_bubble_name(text)
                await self._publish_progress(50, f"Entering: {bubble_name}")
                result = enter_bubble(bubble_id=bubble_name)

            elif "exit" in text or "verlasse" in text or "raus" in text:
                await self._publish_progress(50, "Exiting bubble...")
                result = exit_bubble()

            elif "delete" in text or "lösch" in text:
                bubble_name = self._extract_bubble_name(text)
                await self._publish_progress(50, f"Deleting: {bubble_name}")
                result = delete_bubble(bubble_id=bubble_name)

            else:
                result = "Unknown bubble operation"

            return result

        except ImportError as e:
            return f"Bubble tools not available: {e}"
        except Exception as e:
            logger.error(f"BubbleWorker error: {e}")
            return f"Error: {e}"

    def _extract_title(self, text: str) -> str:
        """Extract bubble title from text."""
        # Simple extraction - look for quoted text or text after "named"
        import re
        quoted = re.search(r'["\']([^"\']+)["\']', text)
        if quoted:
            return quoted.group(1)

        for marker in ["named", "called", "namens", "mit name"]:
            if marker in text:
                return text.split(marker)[-1].strip()

        return "Neue Bubble"

    def _extract_bubble_name(self, text: str) -> str:
        """Extract bubble name/id from text."""
        # Simple extraction
        for marker in ["bubble", "space", "raum"]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) > 1:
                    return parts[-1].strip()
        return text.split()[-1] if text.split() else ""


class IdeaWorker(BaseWorker):
    """
    Worker for idea operations.

    Handles: create, find, update, delete, connect ideas
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="idea_worker",
            space_type=SpaceType.IDEAS,
            description="Handles idea CRUD operations",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute an idea-related task."""
        text = task.input_event.text.lower()

        try:
            from spaces.ideas.adapted.idea_tools import (
                list_ideas, create_idea, find_idea,
                update_idea, delete_idea,
            )

            if "list" in text or "zeig" in text or "show" in text:
                await self._publish_progress(50, "Listing ideas...")
                result = list_ideas()

            elif "create" in text or "erstell" in text or "neu" in text:
                content = self._extract_content(text)
                await self._publish_progress(50, f"Creating idea...")
                result = create_idea(content=content)

            elif "find" in text or "such" in text or "search" in text:
                query = self._extract_query(text)
                await self._publish_progress(50, f"Searching: {query}")
                result = find_idea(query=query)

            elif "delete" in text or "lösch" in text:
                idea_id = self._extract_idea_id(text)
                await self._publish_progress(50, f"Deleting idea...")
                result = delete_idea(idea_id=idea_id)

            else:
                result = "Unknown idea operation"

            return result

        except ImportError as e:
            return f"Idea tools not available: {e}"
        except Exception as e:
            logger.error(f"IdeaWorker error: {e}")
            return f"Error: {e}"

    def _extract_content(self, text: str) -> str:
        """Extract idea content from text."""
        for marker in ["idea", "idee", "note", "notiz"]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) > 1:
                    return parts[-1].strip()
        return text

    def _extract_query(self, text: str) -> str:
        """Extract search query from text."""
        for marker in ["for", "nach", "find", "such"]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) > 1:
                    return parts[-1].strip()
        return text

    def _extract_idea_id(self, text: str) -> str:
        """Extract idea ID from text."""
        return text.split()[-1] if text.split() else ""


class ScoreWorker(BaseWorker):
    """
    Worker for bubble scoring.

    Handles: score bubbles, get stats
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="score_worker",
            space_type=SpaceType.IDEAS,
            description="Handles bubble scoring and evaluation",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute a scoring task."""
        text = task.input_event.text.lower()

        try:
            from spaces.ideas.adapted.bubble_tools import (
                score_bubble, get_bubble_stats,
            )

            if "stats" in text or "statistik" in text:
                await self._publish_progress(50, "Getting stats...")
                result = get_bubble_stats()

            elif "score" in text or "bewert" in text:
                bubble_id = self._extract_bubble_id(text)
                await self._publish_progress(50, f"Scoring bubble...")
                result = score_bubble(bubble_id=bubble_id)

            else:
                result = "Unknown scoring operation"

            return result

        except ImportError as e:
            return f"Score tools not available: {e}"
        except Exception as e:
            logger.error(f"ScoreWorker error: {e}")
            return f"Error: {e}"

    def _extract_bubble_id(self, text: str) -> str:
        """Extract bubble ID from text."""
        return text.split()[-1] if text.split() else ""


def create_ideas_workers(event_manager=None) -> list:
    """Create all Ideas Space workers."""
    return [
        BubbleWorker(event_manager),
        IdeaWorker(event_manager),
        ScoreWorker(event_manager),
    ]


__all__ = [
    "BubbleWorker",
    "IdeaWorker",
    "ScoreWorker",
    "create_ideas_workers",
]
