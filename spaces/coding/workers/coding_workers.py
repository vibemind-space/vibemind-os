"""
Coding Space Workers

Workers for the Coding Space:
- GenerateWorker: Code generation
- PreviewWorker: Project preview management
- FileWorker: File operations
"""

import logging
from typing import Any

from swarm.navigation import SpaceType
from swarm.event_buffer import TaskInfo
from swarm.workers.base_worker import BaseWorker, WorkerConfig

logger = logging.getLogger(__name__)


class GenerateWorker(BaseWorker):
    """
    Worker for code generation.

    Handles: generate code, get status, cancel generation
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="generate_worker",
            space_type=SpaceType.CODING,
            description="Handles code generation tasks",
            task_timeout_seconds=300.0,  # 5 min for code gen
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute a code generation task."""
        text = task.input_event.text.lower()

        try:
            from spaces.coding.tools.adapted_coding_tools import (
                generate_code, get_generation_status, cancel_generation,
            )

            if "status" in text:
                await self._publish_progress(50, "Checking generation status...")
                result = get_generation_status()

            elif "cancel" in text or "abbrech" in text or "stopp" in text:
                await self._publish_progress(50, "Cancelling generation...")
                result = cancel_generation()

            else:
                # Default: generate code
                description = self._extract_description(text)
                language = self._detect_language(text)

                await self._publish_progress(10, f"Starting {language} generation...")
                await self._publish_progress(30, "Analyzing requirements...")

                result = generate_code(
                    description=description,
                    language=language,
                )

                await self._publish_progress(90, "Finalizing...")

            return result

        except ImportError as e:
            return f"Coding tools not available: {e}"
        except Exception as e:
            logger.error(f"GenerateWorker error: {e}")
            return f"Error: {e}"

    def _extract_description(self, text: str) -> str:
        """Extract code description from text."""
        # Remove common prefixes
        for prefix in [
            "generate", "create", "write", "make",
            "generiere", "erstelle", "schreibe",
        ]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text

    def _detect_language(self, text: str) -> str:
        """Detect programming language from text."""
        languages = {
            "python": "python",
            "javascript": "javascript",
            "typescript": "typescript",
            "react": "react",
            "vue": "vue",
            "html": "html",
            "css": "css",
            "java": "java",
            "c++": "cpp",
            "rust": "rust",
            "go": "go",
        }
        for kw, lang in languages.items():
            if kw in text:
                return lang
        return "python"  # default


class PreviewWorker(BaseWorker):
    """
    Worker for project preview management.

    Handles: start preview, stop preview
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="preview_worker",
            space_type=SpaceType.CODING,
            description="Handles project preview operations",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute a preview task."""
        text = task.input_event.text.lower()

        try:
            from spaces.coding.tools.adapted_coding_tools import (
                start_preview, stop_preview,
            )

            if "stop" in text or "stopp" in text or "end" in text:
                await self._publish_progress(50, "Stopping preview...")
                result = stop_preview()

            else:
                # Start preview
                project_name = self._extract_project_name(text)
                await self._publish_progress(50, f"Starting preview: {project_name}")
                result = start_preview(project_name=project_name)

            return result

        except ImportError as e:
            return f"Preview tools not available: {e}"
        except Exception as e:
            logger.error(f"PreviewWorker error: {e}")
            return f"Error: {e}"

    def _extract_project_name(self, text: str) -> str:
        """Extract project name from text."""
        for marker in ["preview", "project", "projekt"]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) > 1:
                    return parts[-1].strip()
        return ""


class FileWorker(BaseWorker):
    """
    Worker for file operations.

    Handles: list projects, file operations
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="file_worker",
            space_type=SpaceType.CODING,
            description="Handles file and project operations",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute a file operation task."""
        text = task.input_event.text.lower()

        try:
            from spaces.coding.tools.adapted_coding_tools import (
                list_generated_projects,
            )

            if "list" in text or "zeig" in text or "show" in text:
                await self._publish_progress(50, "Listing projects...")
                result = list_generated_projects()

            else:
                result = "Unknown file operation"

            return result

        except ImportError as e:
            return f"File tools not available: {e}"
        except Exception as e:
            logger.error(f"FileWorker error: {e}")
            return f"Error: {e}"


def create_coding_workers(event_manager=None) -> list:
    """Create all Coding Space workers."""
    return [
        GenerateWorker(event_manager),
        PreviewWorker(event_manager),
        FileWorker(event_manager),
    ]


__all__ = [
    "GenerateWorker",
    "PreviewWorker",
    "FileWorker",
    "create_coding_workers",
]
