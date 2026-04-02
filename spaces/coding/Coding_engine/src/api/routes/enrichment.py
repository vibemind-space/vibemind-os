"""
FastAPI routes for Enrichment Pipeline visualization.

Reads enrichment output files (enriched tasks, schema, mapping)
and provides them to the dashboard for visualization.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import json
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/enrichment", tags=["Enrichment"])


# ── Pydantic Models ──────────────────────────────────────────────────────

class EnrichmentStats(BaseModel):
    """Enrichment statistics for an epic."""
    total_tasks: int = 0
    tasks_with_requirements: int = 0
    tasks_with_user_stories: int = 0
    tasks_with_diagrams: int = 0
    tasks_with_warnings: int = 0
    tasks_with_dtos: int = 0
    tasks_with_success_criteria: int = 0
    tasks_with_test_scenarios: int = 0
    tasks_with_component_specs: int = 0
    tasks_with_screen_specs: int = 0
    tasks_with_accessibility: int = 0
    tasks_with_routes: int = 0
    tasks_with_design_tokens: int = 0


class EnrichmentOverview(BaseModel):
    """Overview of enrichment for an epic."""
    epic_id: str
    epic_name: str
    enrichment_timestamp: Optional[str] = None
    stats: EnrichmentStats
    task_type_distribution: Dict[str, int]
    enrichment_coverage: Dict[str, float]  # percentage per enrichment type


class EnrichedTaskSummary(BaseModel):
    """Summary of a single enriched task (lightweight for list views)."""
    id: str
    epic_id: str
    type: str
    title: str
    status: str
    has_requirements: bool
    has_user_stories: bool
    has_diagrams: bool
    has_warnings: bool
    has_dtos: bool
    has_success_criteria: bool
    has_test_scenarios: bool
    has_component_spec: bool
    has_screen_spec: bool
    has_accessibility: bool
    has_design_tokens: bool
    enrichment_score: float  # 0-1 coverage ratio


class EnrichedTaskDetail(BaseModel):
    """Full enriched task with all context."""
    id: str
    epic_id: str
    type: str
    title: str
    description: str
    status: str
    dependencies: List[str]
    related_requirements: List[str]
    related_user_stories: List[str]
    success_criteria: Optional[str] = None
    enrichment_context: Optional[Dict[str, Any]] = None


class SchemaOverview(BaseModel):
    """Project schema discovery result."""
    project_name: Optional[str] = None
    language: Optional[str] = None
    requirement_id_pattern: Optional[str] = None
    source_count: int = 0
    sources: Dict[str, Any] = {}
    schema_hash: Optional[str] = None


class MappingOverview(BaseModel):
    """Task mapping result."""
    llm_used: bool = False
    total_mappings: int = 0
    tasks_with_types: int = 0
    tasks_with_requirements: int = 0
    tasks_with_stories: int = 0
    type_distribution: Dict[str, int] = {}


# ── Helpers ──────────────────────────────────────────────────────────────

def _find_enriched_file(project_path: str, epic_id: str) -> Optional[Path]:
    """Find the enriched tasks JSON file for an epic."""
    base = Path(project_path)
    candidates = [
        base / "tasks" / f"{epic_id.lower()}-tasks-enriched.json",
        base / "tasks" / f"epic-{epic_id.split('-')[-1]}-tasks-enriched.json" if '-' in epic_id else None,
        base / f"tasks/{epic_id}-tasks-enriched.json",
    ]
    for c in candidates:
        if c and c.exists():
            return c

    # Glob fallback
    tasks_dir = base / "tasks"
    if tasks_dir.exists():
        for f in tasks_dir.glob("*enriched*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("epic_id", "").upper() == epic_id.upper():
                    return f
            except Exception:
                continue
    return None


def _load_json_safe(path: Path) -> Optional[Dict]:
    """Load JSON file safely."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _calculate_enrichment_score(task: Dict) -> float:
    """Calculate enrichment coverage score (0-1) for a task."""
    ctx = task.get("enrichment_context") or {}
    checks = [
        bool(task.get("related_requirements")),
        bool(task.get("related_user_stories")),
        bool(ctx.get("diagrams")),
        bool(ctx.get("known_gaps")),
        bool(ctx.get("related_dtos")),
        bool(task.get("success_criteria")),
        bool(ctx.get("test_scenarios")),
        bool(ctx.get("component_spec")),
        bool(ctx.get("screen_spec")),
        bool(ctx.get("accessibility_rules")),
        bool(ctx.get("design_tokens")),
    ]
    return sum(checks) / len(checks) if checks else 0.0


# ── API Endpoints ────────────────────────────────────────────────────────

@router.get("/overview/{epic_id}", response_model=EnrichmentOverview)
async def get_enrichment_overview(
    epic_id: str,
    project_path: str = Query(..., description="Path to the project"),
) -> EnrichmentOverview:
    """
    Get enrichment overview for an epic.

    Returns statistics, coverage percentages, and task type distribution.
    """
    enriched_file = _find_enriched_file(project_path, epic_id)
    if not enriched_file:
        raise HTTPException(
            status_code=404,
            detail=f"No enriched data found for {epic_id}. Run enrichment first.",
        )

    data = _load_json_safe(enriched_file)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to parse enrichment file")

    raw_stats = data.get("enrichment_stats", {})
    stats = EnrichmentStats(**{k: raw_stats.get(k, 0) for k in EnrichmentStats.model_fields})

    # Task type distribution
    tasks = data.get("tasks", [])
    type_dist: Dict[str, int] = {}
    for t in tasks:
        task_type = t.get("type", "unknown")
        type_dist[task_type] = type_dist.get(task_type, 0) + 1

    # Coverage percentages
    total = max(stats.total_tasks, 1)
    coverage = {
        "requirements": stats.tasks_with_requirements / total,
        "user_stories": stats.tasks_with_user_stories / total,
        "diagrams": stats.tasks_with_diagrams / total,
        "dtos": stats.tasks_with_dtos / total,
        "success_criteria": stats.tasks_with_success_criteria / total,
        "test_scenarios": stats.tasks_with_test_scenarios / total,
        "component_specs": stats.tasks_with_component_specs / total,
        "screen_specs": stats.tasks_with_screen_specs / total,
        "accessibility": stats.tasks_with_accessibility / total,
        "design_tokens": stats.tasks_with_design_tokens / total,
        "warnings": stats.tasks_with_warnings / total,
    }

    return EnrichmentOverview(
        epic_id=data.get("epic_id", epic_id),
        epic_name=data.get("epic_name", epic_id),
        enrichment_timestamp=data.get("enrichment_timestamp"),
        stats=stats,
        task_type_distribution=type_dist,
        enrichment_coverage=coverage,
    )


@router.get("/tasks/{epic_id}", response_model=List[EnrichedTaskSummary])
async def get_enriched_tasks(
    epic_id: str,
    project_path: str = Query(..., description="Path to the project"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
) -> List[EnrichedTaskSummary]:
    """
    Get enriched task summaries for an epic.

    Returns lightweight task summaries with enrichment flags for list views.
    """
    enriched_file = _find_enriched_file(project_path, epic_id)
    if not enriched_file:
        raise HTTPException(status_code=404, detail=f"No enriched data for {epic_id}")

    data = _load_json_safe(enriched_file)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to parse enrichment file")

    tasks = data.get("tasks", [])
    if task_type:
        tasks = [t for t in tasks if t.get("type") == task_type]

    summaries = []
    for t in tasks:
        ctx = t.get("enrichment_context") or {}
        summaries.append(EnrichedTaskSummary(
            id=t.get("id", ""),
            epic_id=t.get("epic_id", epic_id),
            type=t.get("type", "unknown"),
            title=t.get("title", ""),
            status=t.get("status", "pending"),
            has_requirements=bool(t.get("related_requirements")),
            has_user_stories=bool(t.get("related_user_stories")),
            has_diagrams=bool(ctx.get("diagrams")),
            has_warnings=bool(ctx.get("known_gaps")),
            has_dtos=bool(ctx.get("related_dtos")),
            has_success_criteria=bool(t.get("success_criteria")),
            has_test_scenarios=bool(ctx.get("test_scenarios")),
            has_component_spec=bool(ctx.get("component_spec")),
            has_screen_spec=bool(ctx.get("screen_spec")),
            has_accessibility=bool(ctx.get("accessibility_rules")),
            has_design_tokens=bool(ctx.get("design_tokens")),
            enrichment_score=_calculate_enrichment_score(t),
        ))

    return summaries


@router.get("/task/{epic_id}/{task_id}", response_model=EnrichedTaskDetail)
async def get_enriched_task_detail(
    epic_id: str,
    task_id: str,
    project_path: str = Query(..., description="Path to the project"),
) -> EnrichedTaskDetail:
    """
    Get full enriched task detail including all context.
    """
    enriched_file = _find_enriched_file(project_path, epic_id)
    if not enriched_file:
        raise HTTPException(status_code=404, detail=f"No enriched data for {epic_id}")

    data = _load_json_safe(enriched_file)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to parse enrichment file")

    tasks = data.get("tasks", [])
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return EnrichedTaskDetail(
        id=task.get("id", ""),
        epic_id=task.get("epic_id", epic_id),
        type=task.get("type", "unknown"),
        title=task.get("title", ""),
        description=task.get("description", ""),
        status=task.get("status", "pending"),
        dependencies=task.get("dependencies", []),
        related_requirements=task.get("related_requirements", []),
        related_user_stories=task.get("related_user_stories", []),
        success_criteria=task.get("success_criteria"),
        enrichment_context=task.get("enrichment_context"),
    )


@router.get("/schema", response_model=SchemaOverview)
async def get_schema_overview(
    project_path: str = Query(..., description="Path to the project"),
) -> SchemaOverview:
    """
    Get the project schema discovery result.
    """
    cache_dir = Path(project_path) / ".enrichment_cache"
    schema_file = cache_dir / "project_schema.json"

    if not schema_file.exists():
        return SchemaOverview()

    data = _load_json_safe(schema_file)
    if not data:
        return SchemaOverview()

    sources = data.get("sources", {})
    return SchemaOverview(
        project_name=data.get("project_name"),
        language=data.get("language"),
        requirement_id_pattern=data.get("requirement_id_pattern"),
        source_count=len(sources),
        sources=sources,
        schema_hash=data.get("schema_hash"),
    )


@router.get("/mapping", response_model=MappingOverview)
async def get_mapping_overview(
    project_path: str = Query(..., description="Path to the project"),
) -> MappingOverview:
    """
    Get the task mapping result overview.
    """
    cache_dir = Path(project_path) / ".enrichment_cache"
    mapping_file = cache_dir / "task_mapping.json"

    if not mapping_file.exists():
        return MappingOverview()

    data = _load_json_safe(mapping_file)
    if not data:
        return MappingOverview()

    mappings = data.get("mappings", {})

    # Calculate stats
    type_dist: Dict[str, int] = {}
    with_reqs = 0
    with_stories = 0
    with_types = 0

    for m in mappings.values():
        itype = m.get("inferred_type", "")
        if itype:
            with_types += 1
            type_dist[itype] = type_dist.get(itype, 0) + 1
        if m.get("requirement_ids"):
            with_reqs += 1
        if m.get("user_story_ids"):
            with_stories += 1

    return MappingOverview(
        llm_used=data.get("llm_used", False),
        total_mappings=len(mappings),
        tasks_with_types=with_types,
        tasks_with_requirements=with_reqs,
        tasks_with_stories=with_stories,
        type_distribution=type_dist,
    )
