"""Service layer wrapping the DaveFelix Coding Engine."""
import logging
import os
import json
from pathlib import Path
from typing import Optional

from app.schemas.engine import (
    EngineProjectSummary,
    EngineProjectDetail,
    GenerationStatus,
    GenerationPhase,
    AgentInfo,
    AgentStatus,
    EpicInfo,
)

logger = logging.getLogger(__name__)

# Path to engine data directory
# From web-app/backend-app/app/services/ → repo root is 4 levels up
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
ENGINE_DATA_DIR = REPO_ROOT / "Data" / "all_services"


class EngineService:
    """Manages engine projects and generation state."""

    # In-memory generation state (per project)
    _generation_state: dict[str, GenerationStatus] = {}

    @classmethod
    def list_projects(cls) -> list[EngineProjectSummary]:
        """Scan Data/all_services/ for engine projects."""
        projects = []
        if not ENGINE_DATA_DIR.exists():
            logger.warning(f"Engine data dir not found: {ENGINE_DATA_DIR}")
            return projects

        for entry in sorted(ENGINE_DATA_DIR.iterdir()):
            if not entry.is_dir():
                continue
            # Detect valid project by presence of key files
            has_arch = (entry / "architecture").is_dir() or (entry / "MASTER_DOCUMENT.md").exists()
            if not has_arch:
                continue

            summary = cls._scan_project(entry)
            if summary:
                projects.append(summary)

        return projects

    @classmethod
    def _scan_project(cls, project_dir: Path) -> Optional[EngineProjectSummary]:
        """Scan a single project directory for metadata."""
        try:
            # Count services from architecture dir
            service_count = 0
            arch_dir = project_dir / "architecture"
            if arch_dir.exists():
                service_count = sum(
                    1 for f in arch_dir.iterdir()
                    if f.suffix == ".md" and f.name != "architecture.md"
                )

            # Count endpoints from openapi spec
            endpoint_count = 0
            api_spec = project_dir / "api" / "openapi_spec.yaml"
            if api_spec.exists():
                try:
                    import yaml
                    with open(api_spec) as f:
                        spec = yaml.safe_load(f)
                    paths = spec.get("paths", {})
                    for path_methods in paths.values():
                        endpoint_count += len([
                            m for m in path_methods
                            if m in ("get", "post", "put", "delete", "patch")
                        ])
                except Exception:
                    pass

            # Count stories
            story_count = 0
            stories_dir = project_dir / "user_stories"
            if stories_dir.exists():
                for f in stories_dir.glob("*.json"):
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                        if isinstance(data, list):
                            story_count += len(data)
                        elif isinstance(data, dict) and "user_stories" in data:
                            story_count += len(data["user_stories"])
                    except Exception:
                        pass

            return EngineProjectSummary(
                name=project_dir.name,
                path=str(project_dir),
                service_count=service_count,
                endpoint_count=endpoint_count,
                story_count=story_count,
            )
        except Exception as e:
            logger.error(f"Failed to scan project {project_dir}: {e}")
            return None

    @classmethod
    def get_project(cls, project_name: str) -> Optional[EngineProjectDetail]:
        """Get detailed project info including parsed spec data."""
        project_dir = ENGINE_DATA_DIR / project_name
        if not project_dir.exists():
            return None

        summary = cls._scan_project(project_dir)
        if not summary:
            return None

        # Try structured parse for detailed info
        services = []
        generation_order = []
        dependency_graph = {}

        try:
            import sys
            repo_root = str(REPO_ROOT)
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
            from src.engine.spec_parser import SpecParser

            parsed = SpecParser(project_dir).parse()
            for svc_name, svc in parsed.services.items():
                services.append({
                    "name": svc_name,
                    "port": svc.port,
                    "endpoint_count": len(svc.endpoints),
                    "entity_count": len(svc.entities),
                    "story_count": len(svc.stories),
                })
            generation_order = parsed.generation_order
            dependency_graph = parsed.dependency_graph
        except Exception as e:
            logger.warning(f"Structured parse failed for {project_name}: {e}")

        return EngineProjectDetail(
            name=summary.name,
            path=summary.path,
            service_count=summary.service_count,
            endpoint_count=summary.endpoint_count,
            story_count=summary.story_count,
            services=services,
            generation_order=generation_order,
            dependency_graph=dependency_graph,
        )

    @classmethod
    def get_generation_status(cls, project_name: str) -> GenerationStatus:
        """Get current generation status for a project."""
        if project_name in cls._generation_state:
            return cls._generation_state[project_name]
        return GenerationStatus(
            project_name=project_name,
            phase=GenerationPhase.IDLE,
        )

    @classmethod
    def start_generation(cls, project_name: str, skeleton_only: bool = False) -> GenerationStatus:
        """Start generation for a project (skeleton phase for now)."""
        project_dir = ENGINE_DATA_DIR / project_name
        if not project_dir.exists():
            raise ValueError(f"Project not found: {project_name}")

        status = GenerationStatus(
            project_name=project_name,
            phase=GenerationPhase.SKELETON if skeleton_only else GenerationPhase.PARSING,
            progress_pct=0,
        )
        cls._generation_state[project_name] = status

        # Run skeleton generation synchronously for now
        try:
            import sys
            repo_root = str(REPO_ROOT)
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
            from src.engine.spec_parser import SpecParser
            from src.engine.skeleton_generator import SkeletonGenerator

            status.phase = GenerationPhase.PARSING
            status.progress_pct = 10
            parsed = SpecParser(project_dir).parse()

            status.phase = GenerationPhase.SKELETON
            status.progress_pct = 30
            status.service_count = len(parsed.services)
            status.endpoint_count = sum(len(s.endpoints) for s in parsed.services.values())

            output_dir = REPO_ROOT / "output" / project_name
            gen = SkeletonGenerator(parsed, str(output_dir))
            gen.generate_all()

            status.phase = GenerationPhase.COMPLETE if skeleton_only else GenerationPhase.GENERATION
            status.progress_pct = 100 if skeleton_only else 50

        except Exception as e:
            logger.error(f"Generation failed for {project_name}: {e}")
            status.phase = GenerationPhase.FAILED

        return status

    @classmethod
    def stop_generation(cls, project_name: str) -> GenerationStatus:
        """Stop generation for a project."""
        if project_name in cls._generation_state:
            cls._generation_state[project_name].phase = GenerationPhase.IDLE
            cls._generation_state[project_name].progress_pct = 0
        return cls.get_generation_status(project_name)
