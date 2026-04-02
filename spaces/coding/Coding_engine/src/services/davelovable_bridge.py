"""
DaveLovable Bridge - Connects Coding Engine pipeline to DaveLovable Vibe Coder UI.

This service:
1. Creates a DaveLovable project for each Coding Engine generation
2. Pushes generated files to DaveLovable's file system
3. Streams pipeline events (build, test, verify) to DaveLovable chat
4. Provides real-time preview of generated code in DaveLovable's WebContainer
5. Exposes TreeQuest verification results and ShinkaEvolve status in the UI

Architecture:
  Coding Engine EventBus → DaveLovableBridge → DaveLovable REST API
  DaveLovable Chat → DaveLovableBridge → Coding Engine commands
"""

import asyncio
import json
import os
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiohttp
import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DAVELOVABLE_URL = os.environ.get("DAVELOVABLE_URL", "http://localhost:8000")
DAVELOVABLE_API = f"{DAVELOVABLE_URL}/api/v1"


# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

class DaveLovableClient:
    """HTTP client for DaveLovable API."""

    def __init__(self, base_url: str = DAVELOVABLE_API):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Any = None,
        params: Optional[Dict] = None,
    ) -> Optional[Dict]:
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        try:
            async with session.request(
                method, url, json=json_data, params=params
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.warning("davelovable_api_error", status=resp.status, path=path, body=text[:200])
                    return None
                if resp.content_type == "application/json":
                    return await resp.json()
                return {"text": await resp.text()}
        except Exception as e:
            logger.warning("davelovable_request_failed", path=path, error=str(e))
            return None

    # Health
    async def health(self) -> bool:
        result = await self._request("GET", "/../health")
        return result is not None

    # Projects
    async def create_project(self, name: str, description: str) -> Optional[Dict]:
        return await self._request("POST", "/projects", json_data={
            "name": name,
            "description": description,
        })

    async def create_project_from_message(self, message: str) -> Optional[Dict]:
        return await self._request("POST", "/projects/from-message", json_data={
            "message": message,
        })

    async def get_project(self, project_id: int) -> Optional[Dict]:
        return await self._request("GET", f"/projects/{project_id}")

    # Files
    async def add_file(
        self, project_id: int, filepath: str, content: str, language: str = ""
    ) -> Optional[Dict]:
        return await self._request("POST", f"/projects/{project_id}/files", json_data={
            "filepath": filepath,
            "content": content,
            "language": language or self._detect_language(filepath),
        })

    async def update_file(
        self, project_id: int, file_id: int, content: str
    ) -> Optional[Dict]:
        return await self._request("PUT", f"/projects/{project_id}/files/{file_id}", json_data={
            "content": content,
        })

    async def get_files(self, project_id: int) -> Optional[List[Dict]]:
        result = await self._request("GET", f"/projects/{project_id}/files")
        return result if isinstance(result, list) else None

    # Chat
    async def create_session(self, project_id: int) -> Optional[Dict]:
        return await self._request("POST", f"/chat/{project_id}/sessions")

    async def send_message(
        self, project_id: int, message: str
    ) -> Optional[Dict]:
        return await self._request("POST", f"/chat/{project_id}", json_data={
            "message": message,
        })

    def _detect_language(self, filepath: str) -> str:
        ext_map = {
            ".py": "python", ".ts": "typescript", ".tsx": "typescriptreact",
            ".js": "javascript", ".jsx": "javascriptreact", ".json": "json",
            ".html": "html", ".css": "css", ".md": "markdown", ".yaml": "yaml",
            ".yml": "yaml", ".sql": "sql", ".rs": "rust", ".go": "go",
            ".java": "java", ".rb": "ruby", ".php": "php",
        }
        ext = Path(filepath).suffix.lower()
        return ext_map.get(ext, "plaintext")


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class DaveLovableBridge:
    """Bridges Coding Engine to DaveLovable Vibe Coder UI."""

    def __init__(
        self,
        event_bus: EventBus,
        davelovable_url: str = DAVELOVABLE_URL,
    ):
        self.event_bus = event_bus
        self.client = DaveLovableClient(f"{davelovable_url}/api/v1")
        self._project_id: Optional[int] = None
        self._session_id: Optional[int] = None
        self._file_map: Dict[str, int] = {}  # filepath -> DaveLovable file_id
        self._initialized = False

    async def initialize(self, project_name: str, description: str = "") -> bool:
        """Create a DaveLovable project and connect to EventBus."""
        if not await self.client.health():
            logger.warning("DaveLovable not available, bridge disabled")
            return False

        # Create project
        result = await self.client.create_project(
            project_name,
            description or f"Auto-generated by Coding Engine at {datetime.now().isoformat()}",
        )
        if result and "id" in result:
            self._project_id = result["id"]
            logger.info("davelovable_project_created", id=self._project_id, name=project_name)
        else:
            logger.error("davelovable_project_creation_failed")
            return False

        # Create chat session
        session = await self.client.create_session(self._project_id)
        if session and "id" in session:
            self._session_id = session["id"]

        # Subscribe to events
        self.event_bus.subscribe(EventType.FILE_CREATED, self._on_file_created)
        self.event_bus.subscribe(EventType.FILE_MODIFIED, self._on_file_modified)
        self.event_bus.subscribe(EventType.CODE_GENERATED, self._on_code_generated)
        self.event_bus.subscribe(EventType.BUILD_SUCCEEDED, self._on_build_event)
        self.event_bus.subscribe(EventType.BUILD_FAILED, self._on_build_event)
        self.event_bus.subscribe(EventType.TEST_PASSED, self._on_test_event)
        self.event_bus.subscribe(EventType.TEST_FAILED, self._on_test_event)
        self.event_bus.subscribe(EventType.CODE_FIXED, self._on_code_fixed)

        # Emergent system events
        self.event_bus.subscribe(EventType.TREEQUEST_VERIFICATION_COMPLETE, self._on_generic_event)
        self.event_bus.subscribe(EventType.TREEQUEST_FINDING_CRITICAL, self._on_generic_event)
        self.event_bus.subscribe(EventType.EVOLUTION_APPLIED, self._on_generic_event)
        self.event_bus.subscribe(EventType.PIPELINE_COMPLETED, self._on_generic_event)
        self.event_bus.subscribe(EventType.PIPELINE_FAILED, self._on_generic_event)

        self._initialized = True
        return True

    async def push_project_files(self, project_dir: Path) -> int:
        """Push all source files from a project directory to DaveLovable."""
        if not self._initialized or not self._project_id:
            return 0

        count = 0
        extensions = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".html", ".css",
            ".md", ".yaml", ".yml", ".sql", ".env", ".toml", ".cfg",
            ".vue", ".svelte", ".scss", ".less",
        }
        skip_dirs = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv", ".next"}

        for f in sorted(project_dir.rglob("*")):
            if f.is_file() and f.suffix in extensions:
                # Skip ignored dirs
                if any(d in f.parts for d in skip_dirs):
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    rel_path = str(f.relative_to(project_dir)).replace("\\", "/")

                    result = await self.client.add_file(
                        self._project_id, rel_path, content
                    )
                    if result and "id" in result:
                        self._file_map[rel_path] = result["id"]
                        count += 1
                except Exception as e:
                    logger.debug("davelovable_file_push_failed", file=str(f), error=str(e))

        logger.info("davelovable_files_pushed", count=count, project_dir=str(project_dir))
        return count

    async def push_verification_results(self, findings: List[Dict]) -> None:
        """Push TreeQuest/verification findings to DaveLovable chat."""
        if not self._project_id:
            return

        summary_parts = [f"## Verification Results\n\n**{len(findings)} findings:**\n"]
        for f in findings[:15]:
            sev = f.get("severity", "?")
            desc = f.get("description", "")
            file = Path(f.get("file", "?")).name
            summary_parts.append(f"- **[{sev.upper()}]** `{file}`: {desc}")

        await self.client.send_message(
            self._project_id,
            "\n".join(summary_parts),
        )

    async def push_evolution_result(self, result: Dict) -> None:
        """Push ShinkaEvolve evolution result to DaveLovable chat."""
        if not self._project_id:
            return

        success = result.get("success", False)
        file = Path(result.get("file", "")).name
        msg = (
            f"## Evolution Result\n\n"
            f"**File:** `{file}`\n"
            f"**Status:** {'Improved ✓' if success else 'No improvement found'}\n"
            f"**Task Dir:** `{result.get('task_dir', 'N/A')}`"
        )
        await self.client.send_message(self._project_id, msg)

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    async def _on_file_created(self, event: Event) -> None:
        if not self._project_id:
            return
        file_path = event.data.get("file", "")
        if not file_path:
            return

        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
            rel = self._make_relative(file_path)
            result = await self.client.add_file(self._project_id, rel, content)
            if result and "id" in result:
                self._file_map[rel] = result["id"]
        except Exception as e:
            logger.debug("davelovable_file_create_failed", error=str(e))

    async def _on_file_modified(self, event: Event) -> None:
        if not self._project_id:
            return
        file_path = event.data.get("file", "")
        rel = self._make_relative(file_path)

        if rel in self._file_map:
            try:
                content = Path(file_path).read_text(encoding="utf-8", errors="replace")
                await self.client.update_file(self._project_id, self._file_map[rel], content)
            except Exception:
                pass

    async def _on_code_generated(self, event: Event) -> None:
        if not self._project_id:
            return
        file = event.data.get("file", "unknown")
        await self.client.send_message(
            self._project_id,
            f"Code generated: `{Path(file).name}`",
        )

    async def _on_build_event(self, event: Event) -> None:
        if not self._project_id:
            return
        status = "succeeded ✓" if event.type == EventType.BUILD_SUCCEEDED else "failed ✗"
        await self.client.send_message(
            self._project_id,
            f"Build {status}",
        )

    async def _on_test_event(self, event: Event) -> None:
        if not self._project_id:
            return
        status = "passed ✓" if event.type == EventType.TEST_PASSED else "failed ✗"
        await self.client.send_message(
            self._project_id,
            f"Tests {status}",
        )

    async def _on_code_fixed(self, event: Event) -> None:
        if not self._project_id:
            return
        file = event.data.get("file", "")
        fix_type = event.data.get("fix_type", "standard")
        await self.client.send_message(
            self._project_id,
            f"Code fix applied ({fix_type}): `{Path(file).name}`",
        )

    async def _on_generic_event(self, event: Event) -> None:
        """Forward emergent system events as chat messages to DaveLovable."""
        if not self._project_id:
            return
        event_name = event.type.value.replace("_", " ").title()
        details = ""
        if event.data.get("file"):
            details = f" | File: `{Path(event.data['file']).name}`"
        if event.data.get("project"):
            details += f" | Project: {event.data['project']}"
        await self.client.send_message(
            self._project_id,
            f"[{event_name}]{details}",
        )

    def _make_relative(self, file_path: str) -> str:
        """Convert absolute path to project-relative path."""
        shared = SharedState()
        project_dir = shared.get("project_dir", "")
        if project_dir and file_path.startswith(project_dir):
            return file_path[len(project_dir):].lstrip("/\\").replace("\\", "/")
        return Path(file_path).name

    async def close(self):
        await self.client.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

async def create_davelovable_bridge(
    event_bus: EventBus,
    project_name: str,
    description: str = "",
    davelovable_url: Optional[str] = None,
) -> Optional[DaveLovableBridge]:
    """Create and initialize a DaveLovable bridge. Returns None if unavailable."""
    bridge = DaveLovableBridge(
        event_bus=event_bus,
        davelovable_url=davelovable_url or DAVELOVABLE_URL,
    )
    success = await bridge.initialize(project_name, description)
    if success:
        return bridge
    return None
