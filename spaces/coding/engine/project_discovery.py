"""
ProjectDiscoveryService - Discovers completed projects from Coding Engine
filesystem and syncs them to the VibeMind database.

Scans Data/all_services/ for project directories and reads:
- pipeline_manifest.json  -> name, status, duration, cost, stages
- tech_stack/tech_stack.json -> tech stack details
- quality/self_critique_report.json -> issue counts, quality score, full issues
- content_analysis.json -> artifact counts
- MASTER_DOCUMENT.md -> project description (first 500 chars)
- tasks/task_list.json -> task count
- diagrams/ -> diagram count (file count)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ProjectDiscoveryService:
    """Discovers on-disk Coding Engine projects and returns structured metadata."""

    def __init__(self, coding_engine_path: str):
        self.coding_engine_path = Path(coding_engine_path)
        self.data_dir = self.coding_engine_path / "Data" / "all_services"

    def discover_projects(self) -> List[Dict[str, Any]]:
        """Scan Data/all_services/ and return metadata for each project directory."""
        if not self.data_dir.exists():
            logger.warning(f"Data dir not found: {self.data_dir}")
            return []

        projects = []
        for entry in sorted(self.data_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            meta = self._read_project_metadata(entry)
            if meta:
                projects.append(meta)

        logger.info(f"Discovered {len(projects)} projects in {self.data_dir}")
        return projects

    def read_issues(self, project_path: str) -> List[Dict[str, Any]]:
        """Read full issue list from a project's self_critique_report.json."""
        qr_path = Path(project_path) / "quality" / "self_critique_report.json"
        if not qr_path.exists():
            return []
        data = self._safe_json_load(qr_path)
        if not data:
            return []
        return data.get("issues", [])

    def _read_project_metadata(self, project_dir: Path) -> Optional[Dict[str, Any]]:
        """Read all available metadata files from a project directory."""
        meta: Dict[str, Any] = {
            "dir_name": project_dir.name,
            "project_path": str(project_dir),
            "name": self._extract_name(project_dir.name),
        }

        # Get creation time from directory
        try:
            meta["created_at"] = datetime.fromtimestamp(
                project_dir.stat().st_ctime
            ).isoformat()
        except OSError:
            meta["created_at"] = datetime.now().isoformat()

        has_any_data = False

        # 1. pipeline_manifest.json — Primary source
        manifest_path = project_dir / "pipeline_manifest.json"
        if manifest_path.exists():
            manifest = self._safe_json_load(manifest_path)
            if manifest:
                has_any_data = True
                meta["name"] = manifest.get("project_name", meta["name"])
                meta["total_stages"] = manifest.get("total_stages", 0)
                meta["total_cost_usd"] = manifest.get("total_cost_usd", 0)
                meta["total_duration_ms"] = manifest.get("total_duration_ms", 0)
                meta["started_at"] = manifest.get("started_at")
                meta["completed_at"] = manifest.get("completed_at")
                stages = manifest.get("stages", [])
                completed = sum(1 for s in stages if s.get("status") == "completed")
                meta["stages_completed"] = completed
                # If all stages completed, mark as completed
                if completed > 0 and completed == meta["total_stages"]:
                    meta["generation_status"] = "completed"
                    meta["convergence_progress"] = 100.0
                elif completed > 0:
                    meta["generation_status"] = "generating"
                    meta["convergence_progress"] = (completed / meta["total_stages"]) * 100

        # 2. tech_stack/tech_stack.json
        ts_path = project_dir / "tech_stack" / "tech_stack.json"
        if ts_path.exists():
            ts = self._safe_json_load(ts_path)
            if ts:
                has_any_data = True
                # Extract tech stack tags as comma-separated string
                tags = []
                for key in ("frontend_framework", "backend_framework", "database", "cache"):
                    val = ts.get(key)
                    if val and isinstance(val, str):
                        tags.append(val)
                    elif val and isinstance(val, dict):
                        name = val.get("name") or val.get("technology")
                        if name:
                            tags.append(name)
                meta["tech_stack"] = ", ".join(tags) if tags else None
                meta["tech_stack_full"] = ts

        # 3. quality/self_critique_report.json
        qr_path = project_dir / "quality" / "self_critique_report.json"
        if qr_path.exists():
            qr = self._safe_json_load(qr_path)
            if qr:
                has_any_data = True
                summary = qr.get("summary", {})
                meta["issue_counts"] = summary.get("by_severity", {})
                meta["issue_categories"] = summary.get("by_category", {})
                meta["total_issues"] = summary.get("total_issues", 0)
                meta["quality_score"] = qr.get("quality_score", 0)
                meta["auto_fixed"] = summary.get("auto_fixed", 0)

        # 4. content_analysis.json
        ca_path = project_dir / "content_analysis.json"
        if ca_path.exists():
            ca = self._safe_json_load(ca_path)
            if ca:
                has_any_data = True
                meta["total_artifacts"] = ca.get("total_artifacts", 0)

        # 5. tasks/task_list.json
        tasks_path = project_dir / "tasks" / "task_list.json"
        if tasks_path.exists():
            tasks_data = self._safe_json_load(tasks_path)
            if tasks_data:
                has_any_data = True
                if isinstance(tasks_data, list):
                    meta["task_count"] = len(tasks_data)
                elif isinstance(tasks_data, dict):
                    # May have epics with tasks inside
                    total = 0
                    for epic in tasks_data.get("epics", []):
                        total += len(epic.get("tasks", []))
                    meta["task_count"] = total or len(tasks_data.get("tasks", []))

        # 6. user_stories.json
        us_path = project_dir / "user_stories.json"
        if us_path.exists():
            us_data = self._safe_json_load(us_path)
            if us_data:
                has_any_data = True
                if isinstance(us_data, list):
                    meta["user_story_count"] = len(us_data)
                elif isinstance(us_data, dict):
                    meta["user_story_count"] = len(us_data.get("user_stories", []))

        # 7. diagrams/ — Count mermaid files
        diagrams_dir = project_dir / "diagrams"
        if diagrams_dir.exists():
            has_any_data = True
            mmd_count = sum(1 for f in diagrams_dir.rglob("*.mmd"))
            meta["diagram_count"] = mmd_count

        # 8. MASTER_DOCUMENT.md — Description excerpt
        md_path = project_dir / "MASTER_DOCUMENT.md"
        if md_path.exists():
            try:
                text = md_path.read_text(encoding="utf-8")[:500]
                meta["description"] = text.strip()
            except Exception:
                pass

        # Set defaults for generation_status if not set
        if "generation_status" not in meta:
            if has_any_data:
                meta["generation_status"] = "completed"
                meta["convergence_progress"] = 100.0
            else:
                meta["generation_status"] = "unknown"
                meta["convergence_progress"] = 0.0

        # Skip directories with no meaningful data
        if not has_any_data:
            return None

        return meta

    def _extract_name(self, dir_name: str) -> str:
        """Extract project name from directory name (strip timestamp suffix)."""
        # Format: project-name_20260211_025459
        parts = dir_name.rsplit("_", 2)
        if len(parts) >= 3:
            try:
                int(parts[-1])  # time part
                int(parts[-2])  # date part
                return parts[0].replace("_", "-")
            except ValueError:
                pass
        return dir_name

    def _safe_json_load(self, path: Path) -> Optional[dict]:
        """Safely load a JSON file, returning None on failure."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to parse {path.name}: {e}")
            return None
