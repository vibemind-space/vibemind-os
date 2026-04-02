"""
Package Ingestion Service — Watches /Data/all_services/ for new project packages.

Dynamically detects new packages dropped into the data directory,
parses their structure (MASTER_DOCUMENT, tech_stack, tasks, api specs, etc.),
validates completeness, and triggers the Coding Engine pipeline.

Works with ANY project type — WhatsApp, E-Commerce, CRM, IoT —
the package structure is the contract.

Integration Points:
- SpecAdapter (DOCUMENTATION format) for parsing
- DocumentationLoader for deep content extraction
- HybridPipeline / Orchestrator for code generation
- EventBus for notifying agents
- Fungus Memory for RAG indexing
- DaveLovable for live preview (via REST API)
- Minibook for agent discussion logging
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
import structlog

logger = structlog.get_logger(__name__)


class PackageStatus(str, Enum):
    """Status of a detected package."""
    DETECTED = "detected"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    PARSING = "parsing"
    PARSED = "parsed"
    INDEXING = "indexing"        # Indexing into Fungus Memory
    INDEXED = "indexed"
    QUEUED = "queued"           # Queued for pipeline execution
    RUNNING = "running"         # Pipeline executing
    COMPLETED = "completed"
    FAILED = "failed"


class PackageCompleteness(str, Enum):
    """How complete is the package specification?"""
    FULL = "full"           # Has everything: tasks, api, data, tests, ui
    STANDARD = "standard"   # Has core: tasks, api, data
    MINIMAL = "minimal"     # Has basics: MASTER_DOCUMENT + tech_stack
    INCOMPLETE = "incomplete"  # Missing critical files


@dataclass
class PackageManifest:
    """Parsed manifest of a project package."""
    package_path: Path
    project_name: str
    timestamp: str = ""
    domain: str = ""

    # What files/directories exist
    has_master_document: bool = False
    has_pipeline_manifest: bool = False
    has_tech_stack: bool = False
    has_tasks: bool = False
    has_api_spec: bool = False
    has_async_api: bool = False
    has_data_dictionary: bool = False
    has_user_stories: bool = False
    has_ui_design: bool = False
    has_ux_design: bool = False
    has_testing: bool = False
    has_diagrams: bool = False
    has_work_breakdown: bool = False
    has_quality: bool = False
    has_enrichment_cache: bool = False

    # Extracted metadata
    tech_stack: Dict[str, Any] = field(default_factory=dict)
    total_requirements: int = 0
    total_tasks: int = 0
    total_test_cases: int = 0
    total_api_endpoints: int = 0
    total_entities: int = 0
    total_diagrams: int = 0
    total_epics: int = 0
    total_user_stories: int = 0
    total_estimated_hours: float = 0
    total_story_points: int = 0

    # Task breakdown per epic
    epics: Dict[str, int] = field(default_factory=dict)  # epic_id -> task_count

    # Status tracking
    status: PackageStatus = PackageStatus.DETECTED
    completeness: PackageCompleteness = PackageCompleteness.INCOMPLETE
    errors: List[str] = field(default_factory=list)
    detected_at: str = ""
    started_at: str = ""
    completed_at: str = ""

    @property
    def completeness_score(self) -> float:
        """Calculate completeness score 0.0-1.0."""
        checks = [
            self.has_master_document,
            self.has_tech_stack,
            self.has_tasks,
            self.has_api_spec,
            self.has_data_dictionary,
            self.has_user_stories,
            self.has_ui_design,
            self.has_testing,
            self.has_diagrams,
            self.has_work_breakdown,
        ]
        return sum(checks) / len(checks)

    def to_dict(self) -> Dict:
        return {
            "package_path": str(self.package_path),
            "project_name": self.project_name,
            "timestamp": self.timestamp,
            "domain": self.domain,
            "status": self.status.value,
            "completeness": self.completeness.value,
            "completeness_score": self.completeness_score,
            "tech_stack": self.tech_stack,
            "totals": {
                "requirements": self.total_requirements,
                "tasks": self.total_tasks,
                "test_cases": self.total_test_cases,
                "api_endpoints": self.total_api_endpoints,
                "entities": self.total_entities,
                "diagrams": self.total_diagrams,
                "epics": self.total_epics,
                "user_stories": self.total_user_stories,
                "estimated_hours": self.total_estimated_hours,
                "story_points": self.total_story_points,
            },
            "epics": self.epics,
            "errors": self.errors,
            "detected_at": self.detected_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class PackageParser:
    """Parses a project package directory into a PackageManifest."""

    def parse(self, package_path: Path) -> PackageManifest:
        """Parse a package directory and extract all metadata."""
        manifest = PackageManifest(
            package_path=package_path,
            project_name=self._extract_project_name(package_path),
            timestamp=self._extract_timestamp(package_path),
            detected_at=datetime.now().isoformat(),
        )

        manifest.status = PackageStatus.VALIDATING

        # Check what exists
        manifest.has_master_document = (package_path / "MASTER_DOCUMENT.md").exists()
        manifest.has_pipeline_manifest = (package_path / "pipeline_manifest.json").exists()
        manifest.has_tech_stack = (package_path / "tech_stack").is_dir()
        manifest.has_tasks = (package_path / "tasks").is_dir()
        manifest.has_api_spec = (package_path / "api").is_dir()
        manifest.has_async_api = (package_path / "api" / "asyncapi_spec.yaml").exists()
        manifest.has_data_dictionary = (package_path / "data").is_dir()
        manifest.has_user_stories = (package_path / "user_stories").is_dir()
        manifest.has_ui_design = (package_path / "ui_design").is_dir()
        manifest.has_ux_design = (package_path / "ux_design").is_dir()
        manifest.has_testing = (package_path / "testing").is_dir()
        manifest.has_diagrams = (package_path / "diagrams").is_dir()
        manifest.has_work_breakdown = (package_path / "work_breakdown").is_dir()
        manifest.has_quality = (package_path / "quality").is_dir()
        manifest.has_enrichment_cache = (package_path / ".enrichment_cache").is_dir()

        # Parse tech stack
        if manifest.has_tech_stack:
            self._parse_tech_stack(manifest)

        # Parse tasks
        if manifest.has_tasks:
            self._parse_tasks(manifest)

        # Parse pipeline manifest for metadata
        if manifest.has_pipeline_manifest:
            self._parse_pipeline_manifest(manifest)

        # Count diagrams
        if manifest.has_diagrams:
            diagrams_dir = package_path / "diagrams"
            manifest.total_diagrams = sum(
                1 for f in diagrams_dir.rglob("*.mmd")
            )

        # Determine completeness
        manifest.completeness = self._assess_completeness(manifest)

        # Validate
        if not manifest.has_master_document:
            manifest.errors.append("Missing MASTER_DOCUMENT.md — cannot proceed")
            manifest.status = PackageStatus.INVALID
        elif manifest.completeness == PackageCompleteness.INCOMPLETE:
            manifest.errors.append("Package too incomplete for reliable generation")
            manifest.status = PackageStatus.INVALID
        else:
            manifest.status = PackageStatus.VALID

        logger.info(
            "package_parsed",
            project=manifest.project_name,
            completeness=manifest.completeness.value,
            score=f"{manifest.completeness_score:.0%}",
            tasks=manifest.total_tasks,
            endpoints=manifest.total_api_endpoints,
            status=manifest.status.value,
        )

        return manifest

    def _extract_project_name(self, path: Path) -> str:
        """Extract project name from directory name (strip timestamp)."""
        name = path.name
        # Pattern: project-name_YYYYMMDD_HHMMSS
        parts = name.rsplit("_", 2)
        if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
            return "_".join(parts[:-2])
        return name

    def _extract_timestamp(self, path: Path) -> str:
        """Extract timestamp from directory name."""
        name = path.name
        parts = name.rsplit("_", 2)
        if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
            return f"{parts[-2]}_{parts[-1]}"
        return ""

    def _parse_tech_stack(self, manifest: PackageManifest) -> None:
        """Parse tech_stack/tech_stack.json."""
        try:
            ts_file = manifest.package_path / "tech_stack" / "tech_stack.json"
            if ts_file.exists():
                data = json.loads(ts_file.read_text(encoding="utf-8"))
                manifest.tech_stack = data
                manifest.domain = data.get("architecture_pattern", "")
        except (json.JSONDecodeError, OSError) as e:
            manifest.errors.append(f"Failed to parse tech_stack.json: {e}")

    def _parse_tasks(self, manifest: PackageManifest) -> None:
        """Parse tasks/task_list.json for task counts and epic breakdown."""
        try:
            task_file = manifest.package_path / "tasks" / "task_list.json"
            if task_file.exists():
                data = json.loads(task_file.read_text(encoding="utf-8"))
                manifest.total_tasks = data.get("total_tasks", 0)
                manifest.total_estimated_hours = data.get("total_hours", 0)
                manifest.total_story_points = data.get("total_story_points", 0)

                features = data.get("features", {})
                for feat_id, tasks in features.items():
                    manifest.epics[feat_id] = len(tasks) if isinstance(tasks, list) else 0

                manifest.total_epics = len([k for k in features if k.startswith("FEAT-")])

            # Count epic task files
            tasks_dir = manifest.package_path / "tasks"
            epic_files = list(tasks_dir.glob("epic-*-tasks*.json"))
            if epic_files and manifest.total_epics == 0:
                manifest.total_epics = len(epic_files)

        except (json.JSONDecodeError, OSError) as e:
            manifest.errors.append(f"Failed to parse task_list.json: {e}")

    def _parse_pipeline_manifest(self, manifest: PackageManifest) -> None:
        """Parse pipeline_manifest.json for pipeline metadata."""
        try:
            pm_file = manifest.package_path / "pipeline_manifest.json"
            data = json.loads(pm_file.read_text(encoding="utf-8"))
            # Extract stage count as proxy for complexity
            manifest.domain = manifest.domain or data.get("project_name", "")
        except (json.JSONDecodeError, OSError) as e:
            manifest.errors.append(f"Failed to parse pipeline_manifest.json: {e}")

    def _assess_completeness(self, manifest: PackageManifest) -> PackageCompleteness:
        """Assess how complete the package is."""
        score = manifest.completeness_score
        if score >= 0.8:
            return PackageCompleteness.FULL
        elif score >= 0.5:
            return PackageCompleteness.STANDARD
        elif manifest.has_master_document and manifest.has_tech_stack:
            return PackageCompleteness.MINIMAL
        else:
            return PackageCompleteness.INCOMPLETE


class PackageIngestionService:
    """
    Watches /Data/all_services/ for new project packages and
    triggers the Coding Engine pipeline.

    Usage:
        service = PackageIngestionService(
            watch_dir=Path("Data/all_services"),
            output_dir=Path("output"),
            on_package_detected=my_callback,
        )
        await service.start()  # Runs forever, watching for new packages
    """

    def __init__(
        self,
        watch_dir: Path,
        output_dir: Path = Path("output"),
        poll_interval: float = 5.0,
        auto_start: bool = True,
        on_package_detected: Optional[Callable] = None,
        on_package_completed: Optional[Callable] = None,
        on_package_failed: Optional[Callable] = None,
    ):
        self.watch_dir = Path(watch_dir)
        self.output_dir = Path(output_dir)
        self.poll_interval = poll_interval
        self.auto_start = auto_start

        # Callbacks
        self.on_package_detected = on_package_detected
        self.on_package_completed = on_package_completed
        self.on_package_failed = on_package_failed

        # State
        self.parser = PackageParser()
        self.known_packages: Set[str] = set()
        self.active_manifests: Dict[str, PackageManifest] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None

        # Track what's already been processed
        self._load_known_packages()

    def _load_known_packages(self) -> None:
        """Load previously known packages from state file."""
        state_file = self.watch_dir / ".ingestion_state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                self.known_packages = set(data.get("known_packages", []))
                logger.info("loaded_known_packages", count=len(self.known_packages))
            except (json.JSONDecodeError, OSError):
                pass

    def _save_known_packages(self) -> None:
        """Save known packages to state file."""
        state_file = self.watch_dir / ".ingestion_state.json"
        try:
            state_file.write_text(
                json.dumps({
                    "known_packages": list(self.known_packages),
                    "updated_at": datetime.now().isoformat(),
                }, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def scan_for_new_packages(self) -> List[Path]:
        """Scan watch directory for new, unprocessed packages."""
        if not self.watch_dir.exists():
            return []

        new_packages = []
        for entry in self.watch_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            if entry.name in self.known_packages:
                continue

            # Check if it looks like a project package
            has_master = (entry / "MASTER_DOCUMENT.md").exists()
            has_tasks = (entry / "tasks").is_dir()
            has_tech = (entry / "tech_stack").is_dir()

            if has_master or (has_tasks and has_tech):
                new_packages.append(entry)

        return sorted(new_packages, key=lambda p: p.stat().st_mtime)

    async def ingest_package(self, package_path: Path) -> PackageManifest:
        """
        Ingest a single package: parse, validate, index, and queue.

        Returns the manifest with final status.
        """
        logger.info("ingesting_package", path=str(package_path))

        # Phase 1: Parse
        manifest = self.parser.parse(package_path)
        self.active_manifests[manifest.project_name] = manifest

        if manifest.status == PackageStatus.INVALID:
            logger.warning(
                "package_invalid",
                project=manifest.project_name,
                errors=manifest.errors,
            )
            if self.on_package_failed:
                await self._call_async(self.on_package_failed, manifest)
            return manifest

        # Phase 2: Notify detection
        if self.on_package_detected:
            await self._call_async(self.on_package_detected, manifest)

        # Phase 3: Mark as parsed and ready for pipeline
        manifest.status = PackageStatus.PARSED

        logger.info(
            "package_ready",
            project=manifest.project_name,
            completeness=manifest.completeness.value,
            score=f"{manifest.completeness_score:.0%}",
            tasks=manifest.total_tasks,
            hours=manifest.total_estimated_hours,
            tech=manifest.tech_stack.get("backend_framework", "unknown"),
        )

        # Mark as known
        self.known_packages.add(package_path.name)
        self._save_known_packages()

        return manifest

    async def start(self) -> None:
        """Start watching for new packages."""
        self.running = True
        logger.info(
            "package_watcher_started",
            watch_dir=str(self.watch_dir),
            poll_interval=self.poll_interval,
        )

        while self.running:
            try:
                new_packages = self.scan_for_new_packages()

                for package_path in new_packages:
                    logger.info("new_package_detected", path=str(package_path))
                    manifest = await self.ingest_package(package_path)

                    if manifest.status == PackageStatus.PARSED and self.auto_start:
                        manifest.status = PackageStatus.QUEUED
                        logger.info(
                            "package_queued_for_pipeline",
                            project=manifest.project_name,
                        )

            except Exception as e:
                logger.error("package_watcher_error", error=str(e))

            await asyncio.sleep(self.poll_interval)

    def start_watchdog(self) -> None:
        """Start watchdog-based filesystem observer for instant package detection."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _PackageHandler(FileSystemEventHandler):
                def __init__(self, service):
                    self.service = service

                def on_created(self, event):
                    if event.is_directory:
                        path = Path(event.src_path)
                        # Check if it looks like a package
                        if not path.name.startswith(".") and not path.name.startswith("_"):
                            logger.info("watchdog_new_directory", path=str(path))

            self._observer = Observer()
            self._observer.schedule(
                _PackageHandler(self),
                str(self.watch_dir),
                recursive=False,
            )
            self._observer.start()
            logger.info("watchdog_observer_started", watch_dir=str(self.watch_dir))
        except ImportError:
            logger.debug("watchdog_not_available", msg="Using poll-based watcher")

    async def stop(self) -> None:
        """Stop watching."""
        self.running = False
        if self._task:
            self._task.cancel()
        if hasattr(self, "_observer"):
            self._observer.stop()
            self._observer.join()
        logger.info("package_watcher_stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get current ingestion service status."""
        return {
            "running": self.running,
            "watch_dir": str(self.watch_dir),
            "known_packages": len(self.known_packages),
            "active_manifests": {
                name: m.to_dict() for name, m in self.active_manifests.items()
            },
        }

    async def _call_async(self, callback: Callable, *args) -> Any:
        """Call callback, handling both sync and async."""
        if asyncio.iscoroutinefunction(callback):
            return await callback(*args)
        return callback(*args)


# =============================================================================
# Pipeline Bridge — Connects ingestion to the Coding Engine pipeline
# =============================================================================

class PipelineBridge:
    """
    Bridge between PackageIngestionService and the Coding Engine.

    Takes a PackageManifest and starts the appropriate pipeline:
    - Society of Mind (run_society_hybrid) for full generation
    - Epic Orchestrator (run_engine) for task-based execution
    - Differential Pipeline for verification
    """

    def __init__(
        self,
        output_base: Path = Path("output"),
        mode: str = "engine",  # "society", "engine", "epic"
        parallel: int = 10,
        autonomous: bool = True,
    ):
        self.output_base = output_base
        self.mode = mode
        self.parallel = parallel
        self.autonomous = autonomous

    def get_output_dir(self, manifest: PackageManifest) -> Path:
        """Get output directory for a project."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.output_base / f"{manifest.project_name}_{timestamp}"

    async def start_pipeline(self, manifest: PackageManifest) -> Dict[str, Any]:
        """
        Start the Coding Engine pipeline for a parsed package.

        This is the main integration point. It:
        1. Sets up the output directory
        2. Configures the pipeline based on package completeness
        3. Starts the appropriate pipeline mode
        4. Returns pipeline handle for monitoring
        """
        output_dir = self.get_output_dir(manifest)
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest.status = PackageStatus.RUNNING
        manifest.started_at = datetime.now().isoformat()

        logger.info(
            "pipeline_starting",
            project=manifest.project_name,
            mode=self.mode,
            package_path=str(manifest.package_path),
            output_dir=str(output_dir),
            completeness=manifest.completeness.value,
            tasks=manifest.total_tasks,
        )

        # The pipeline uses SpecAdapter.DOCUMENTATION format
        # which reads directly from the package directory
        pipeline_config = {
            "project_path": str(manifest.package_path),
            "output_dir": str(output_dir),
            "mode": self.mode,
            "parallel": self.parallel,
            "autonomous": self.autonomous,
            "package_manifest": manifest.to_dict(),
            # Pass tech stack for agent configuration
            "tech_stack": manifest.tech_stack,
            # Task-based execution config
            "epic_tasks": {
                epic_id: count
                for epic_id, count in manifest.epics.items()
            },
        }

        # Write pipeline config for the engine to pick up
        config_file = output_dir / "pipeline_config.json"
        config_file.write_text(
            json.dumps(pipeline_config, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "pipeline_config_written",
            config_file=str(config_file),
            project=manifest.project_name,
        )

        return {
            "project_name": manifest.project_name,
            "output_dir": str(output_dir),
            "config_file": str(config_file),
            "status": "started",
            "manifest": manifest.to_dict(),
        }


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Run the Package Ingestion Service as standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="Package Ingestion Service")
    parser.add_argument(
        "--watch-dir",
        default="Data/all_services",
        help="Directory to watch for new packages",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory for generated projects",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between scans",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Scan once and exit (don't watch)",
    )
    parser.add_argument(
        "--mode",
        choices=["society", "engine", "epic"],
        default="engine",
        help="Pipeline mode to use",
    )

    args = parser.parse_args()

    bridge = PipelineBridge(
        output_base=Path(args.output_dir),
        mode=args.mode,
    )

    async def on_detected(manifest: PackageManifest):
        print(f"\n{'='*60}")
        print(f"📦 NEW PACKAGE DETECTED: {manifest.project_name}")
        print(f"{'='*60}")
        print(f"  Completeness: {manifest.completeness.value} ({manifest.completeness_score:.0%})")
        print(f"  Tasks: {manifest.total_tasks}")
        print(f"  Estimated Hours: {manifest.total_estimated_hours}")
        print(f"  Tech: {manifest.tech_stack.get('backend_framework', 'N/A')}")
        print(f"  Epics: {manifest.total_epics}")
        for epic_id, count in manifest.epics.items():
            print(f"    {epic_id}: {count} tasks")
        print(f"{'='*60}\n")

    service = PackageIngestionService(
        watch_dir=Path(args.watch_dir),
        output_dir=Path(args.output_dir),
        poll_interval=args.poll_interval,
        auto_start=True,
        on_package_detected=on_detected,
    )

    if args.scan_only:
        # One-shot scan
        new = service.scan_for_new_packages()
        if not new:
            print("No new packages found.")
            return

        for pkg_path in new:
            manifest = await service.ingest_package(pkg_path)
            if manifest.status == PackageStatus.PARSED:
                result = await bridge.start_pipeline(manifest)
                print(f"\n✅ Pipeline started: {result['project_name']}")
                print(f"   Output: {result['output_dir']}")
    else:
        # Watch mode
        print(f"👁️  Watching {args.watch_dir} for new packages...")
        print(f"   Poll interval: {args.poll_interval}s")
        print(f"   Press Ctrl+C to stop\n")

        try:
            await service.start()
        except KeyboardInterrupt:
            await service.stop()
            print("\nStopped.")


if __name__ == "__main__":
    asyncio.run(main())
