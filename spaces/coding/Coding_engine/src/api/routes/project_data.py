"""
Project Data Import + API Endpoints.

Imports all project data files (epics, requirements, API specs, diagrams, tests, metadata)
into the database, and provides API endpoints for the UI tabs.
"""
import json
import re
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.models.base import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["project-data"])


# ── Helper: get project_id from DB ────────────────────────
async def _get_or_create_project_id(db: AsyncSession, project_name: str) -> int:
    """Get the DB projects.id for a project, create if missing."""
    # projects table has: id, name, description, status, git_repo_url, git_branch, config_json
    result = await db.execute(
        text("SELECT id FROM projects WHERE name = :pid LIMIT 1"),
        {"pid": project_name},
    )
    row = result.fetchone()
    if row:
        return row[0]
    # Try partial match
    result = await db.execute(
        text("SELECT id FROM projects WHERE name LIKE :pat LIMIT 1"),
        {"pat": f"%{project_name}%"},
    )
    row = result.fetchone()
    if row:
        return row[0]
    # Create new — need required fields: name, status, git_branch
    result = await db.execute(
        text("INSERT INTO projects (name, status, git_branch, created_at, updated_at) VALUES (:name, 'active', 'main', NOW(), NOW()) RETURNING id"),
        {"name": project_name},
    )
    await db.commit()
    row = result.fetchone()
    return row[0]


# ══════════════════════════════════════════════════════════
# IMPORT PIPELINE
# ══════════════════════════════════════════════════════════

@router.post("/import-project-data")
async def import_project_data(
    project_name: str = Query("", description="Project key from engine_settings"),
    db: AsyncSession = Depends(get_db),
):
    """Import all project data files into DB tables."""
    try:
        from src.engine_settings import get_project
        proj = get_project(project_name)
        if not proj:
            return {"success": False, "error": "Project not found: %s" % project_name}
        req_path = Path(proj.get("requirements_path", ""))
    except Exception as e:
        return {"success": False, "error": "Settings error: %s" % str(e)[:200]}

    if not req_path.exists():
        return {"success": False, "error": "Path not found: %s" % req_path}

    pid = await _get_or_create_project_id(db, proj.get("id", project_name))
    counts = {}

    importers = [
        ("epics", _import_epics),
        ("requirements", _import_requirements),
        ("api_endpoints", _import_api_endpoints),
        ("diagrams", _import_diagrams),
        ("test_cases", _import_test_cases),
        ("db_entities", _import_db_entities),
        ("metadata", _import_metadata),
    ]

    for name, func in importers:
        try:
            counts[name] = await func(db, pid, req_path)
            await db.commit()
        except Exception as e:
            logger.error("%s import failed: %s", name, e)
            counts["%s_error" % name] = str(e)[:200]
            await db.rollback()
    return {"success": True, "project_id": pid, "imported": counts}


# ── Import: Epics ──────────────────────────────────────────
async def _import_epics(db: AsyncSession, pid: int, req_path: Path) -> int:
    tasks_dir = req_path / "tasks"
    if not tasks_dir.exists():
        return 0
    count = 0
    for epic_file in sorted(tasks_dir.glob("epic-*-tasks-enriched.json")):
        try:
            data = json.loads(epic_file.read_text(encoding="utf-8"))
        except Exception:
            data = json.loads(epic_file.read_text(encoding="utf-8", errors="replace"))

        epic_id = data.get("epic_id", epic_file.stem.split("-tasks")[0].upper())
        name = data.get("epic_name", "")
        stats = data.get("enrichment_stats", {})
        total = stats.get("total_tasks", len(data.get("tasks", [])))

        # Count completed/failed from tasks
        tasks = data.get("tasks", [])
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        failed = sum(1 for t in tasks if t.get("status") == "failed")

        await db.execute(text("""
            INSERT INTO epics (project_id, epic_id, name, total_tasks, completed_tasks, failed_tasks, status)
            VALUES (:pid, :eid, :name, :total, :completed, :failed, :status)
            ON CONFLICT (project_id, epic_id) DO UPDATE SET
                name = EXCLUDED.name, total_tasks = EXCLUDED.total_tasks,
                completed_tasks = EXCLUDED.completed_tasks, failed_tasks = EXCLUDED.failed_tasks,
                status = EXCLUDED.status, updated_at = NOW()
        """), {
            "pid": pid, "eid": epic_id, "name": name,
            "total": total, "completed": completed, "failed": failed,
            "status": "completed" if completed == total and total > 0 else "pending",
        })
        count += 1
    return count


# ── Import: Requirements ───────────────────────────────────
async def _import_requirements(db: AsyncSession, pid: int, req_path: Path) -> int:
    analysis_file = req_path / "content_analysis.json"
    if not analysis_file.exists():
        return 0

    data = json.loads(analysis_file.read_text(encoding="utf-8"))
    summaries = data.get("artifact_summaries", {})
    count = 0

    # User Stories from content_analysis
    us_data = summaries.get("user_stories", {})
    for item in us_data.get("items", []):
        await db.execute(text("""
            INSERT INTO requirements (project_id, req_id, type, title, persona, description, priority, acceptance_criteria)
            VALUES (:pid, :rid, 'user_story', :title, :persona, :desc, :priority, CAST(:ac AS jsonb))
            ON CONFLICT (project_id, req_id) DO UPDATE SET
                title = EXCLUDED.title, persona = EXCLUDED.persona,
                description = EXCLUDED.description, acceptance_criteria = EXCLUDED.acceptance_criteria
        """), {
            "pid": pid,
            "rid": item.get("id", "US-%d" % count),
            "title": item.get("title", "")[:500],
            "persona": item.get("persona", "")[:200],
            "desc": "%s, damit %s" % (item.get("action", ""), item.get("benefit", "")),
            "priority": item.get("priority", "must")[:10],
            "ac": json.dumps(item.get("acceptance_criteria", [])),
        })
        count += 1

    # Requirements from content_analysis
    req_data = summaries.get("requirements", summaries.get("functional_requirements", {}))
    for item in req_data.get("items", []):
        await db.execute(text("""
            INSERT INTO requirements (project_id, req_id, type, title, description, priority)
            VALUES (:pid, :rid, 'requirement', :title, :desc, :priority)
            ON CONFLICT (project_id, req_id) DO UPDATE SET
                title = EXCLUDED.title, description = EXCLUDED.description
        """), {
            "pid": pid,
            "rid": item.get("id", "REQ-%d" % count),
            "title": item.get("title", "")[:500],
            "desc": item.get("description", ""),
            "priority": item.get("priority", "must")[:10],
        })
        count += 1

    # Also extract unique requirement IDs from task enrichments (WA-AUTH-001 etc.)
    tasks_dir = req_path / "tasks"
    if tasks_dir.exists():
        seen_reqs = set()
        for epic_file in sorted(tasks_dir.glob("epic-*-tasks-enriched.json")):
            try:
                edata = json.loads(epic_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            epic_id = edata.get("epic_id", "")
            for task in edata.get("tasks", []):
                for req_id in task.get("related_requirements", []):
                    if req_id and req_id not in seen_reqs:
                        seen_reqs.add(req_id)
                        await db.execute(text("""
                            INSERT INTO requirements (project_id, req_id, type, title, related_epic)
                            VALUES (:pid, :rid, 'requirement', :title, :epic)
                            ON CONFLICT (project_id, req_id) DO UPDATE SET
                                related_epic = COALESCE(EXCLUDED.related_epic, requirements.related_epic)
                        """), {
                            "pid": pid, "rid": req_id,
                            "title": req_id, "epic": epic_id,
                        })
                        count += 1

    return count


# ── Import: API Endpoints ──────────────────────────────────
async def _import_api_endpoints(db: AsyncSession, pid: int, req_path: Path) -> int:
    spec_file = req_path / "api" / "openapi_spec.yaml"
    if not spec_file.exists():
        return 0

    try:
        import yaml
        spec = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
    except ImportError:
        # Fallback: basic YAML parsing
        content = spec_file.read_text(encoding="utf-8")
        spec = json.loads(content) if content.strip().startswith("{") else {}
    except Exception:
        return 0

    paths = spec.get("paths", {})
    count = 0

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if method in ("parameters", "summary", "description") or not isinstance(details, dict):
                continue
            await db.execute(text("""
                INSERT INTO api_endpoints (project_id, method, path, operation_id, summary, tags, auth_required)
                VALUES (:pid, :method, :path, :op_id, :summary, CAST(:tags AS jsonb), :auth)
                ON CONFLICT (project_id, method, path) DO UPDATE SET
                    operation_id = EXCLUDED.operation_id, summary = EXCLUDED.summary, tags = EXCLUDED.tags
            """), {
                "pid": pid,
                "method": method.upper()[:10],
                "path": path[:500],
                "op_id": (details.get("operationId") or "")[:200],
                "summary": (details.get("summary") or "")[:500],
                "tags": json.dumps(details.get("tags", [])),
                "auth": len(details.get("security", [{}])) > 0,
            })
            count += 1

    return count


# ── Import: Diagrams ───────────────────────────────────────
async def _import_diagrams(db: AsyncSession, pid: int, req_path: Path) -> int:
    diagrams_dir = req_path / "diagrams"
    if not diagrams_dir.exists():
        return 0

    count = 0
    for mmd in diagrams_dir.glob("*.mmd"):
        name = mmd.stem
        parts = name.rsplit("_", 1)
        dtype = parts[1] if len(parts) > 1 else "unknown"
        related_req = parts[0] if len(parts) > 1 else ""

        content = mmd.read_text(encoding="utf-8", errors="replace")

        await db.execute(text("""
            INSERT INTO diagrams (project_id, diagram_id, type, title, content, related_requirement)
            VALUES (:pid, :did, :dtype, :title, :content, :req)
            ON CONFLICT (project_id, diagram_id) DO UPDATE SET
                content = EXCLUDED.content, type = EXCLUDED.type
        """), {
            "pid": pid, "did": name[:100], "dtype": dtype[:30],
            "title": name[:500], "content": content, "req": related_req[:30],
        })
        count += 1

    # Also import architecture diagrams
    arch_dir = req_path / "architecture"
    if arch_dir.exists():
        for mmd in arch_dir.glob("*.mmd"):
            content = mmd.read_text(encoding="utf-8", errors="replace")
            await db.execute(text("""
                INSERT INTO diagrams (project_id, diagram_id, type, title, content, related_requirement)
                VALUES (:pid, :did, :dtype, :title, :content, '')
                ON CONFLICT (project_id, diagram_id) DO UPDATE SET content = EXCLUDED.content
            """), {
                "pid": pid, "did": "arch_%s" % mmd.stem,
                "dtype": mmd.stem.replace("_", " "),
                "title": mmd.stem, "content": content,
            })
            count += 1

    return count


# ── Import: Test Cases ─────────────────────────────────────
async def _import_test_cases(db: AsyncSession, pid: int, req_path: Path) -> int:
    test_file = req_path / "testing" / "test_documentation.md"
    if not test_file.exists():
        return 0

    content = test_file.read_text(encoding="utf-8", errors="replace")
    count = 0

    # Parse markdown test cases: ### TC-001: Title
    pattern = re.compile(
        r"###\s+(TC-\d+):\s*(.+?)(?:\n\n|\n(?=###)|\Z)",
        re.DOTALL,
    )

    for match in pattern.finditer(content):
        test_id = match.group(1)
        block = match.group(2)

        title_line = block.split("\n")[0].strip()

        # Extract fields from block
        test_type = _extract_field(block, "Type") or "e2e"
        priority = _extract_field(block, "Priority") or "medium"
        desc = _extract_field(block, "Description") or ""
        precond = _extract_field(block, "Preconditions") or ""
        req = _extract_field(block, "Requirement") or ""
        us = _extract_field(block, "User Story") or ""

        await db.execute(text("""
            INSERT INTO test_cases (project_id, test_id, type, title, description, priority, preconditions,
                related_requirement, related_user_story)
            VALUES (:pid, :tid, :type, :title, :desc, :priority, :precond, :req, :us)
            ON CONFLICT (project_id, test_id) DO UPDATE SET
                title = EXCLUDED.title, description = EXCLUDED.description
        """), {
            "pid": pid, "tid": test_id[:30], "type": test_type[:20],
            "title": title_line[:500], "desc": desc, "priority": priority[:10],
            "precond": precond, "req": req[:30], "us": us[:30],
        })
        count += 1

    return count


def _extract_field(block: str, field: str) -> str:
    m = re.search(r"\*\*%s:\*\*\s*(.+)" % field, block)
    return m.group(1).strip() if m else ""


# ── Import: DB Entities ────────────────────────────────────
async def _import_db_entities(db: AsyncSession, pid: int, req_path: Path) -> int:
    schema_file = req_path / "data" / "schema.sql"
    if not schema_file.exists():
        return 0

    content = schema_file.read_text(encoding="utf-8", errors="replace")
    count = 0

    # Parse CREATE TABLE statements
    table_pattern = re.compile(
        r"CREATE TABLE\s+(\w+)\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )

    for match in table_pattern.finditer(content):
        entity_name = match.group(1)
        body = match.group(2)

        # Parse columns
        columns = []
        for line in body.split(",\n"):
            line = line.strip()
            if not line or line.upper().startswith(("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "CONSTRAINT", "CHECK")):
                continue
            parts = line.split()
            if len(parts) >= 2:
                col_name = parts[0].strip('"')
                col_type = parts[1]
                nullable = "NOT NULL" not in line.upper()
                columns.append({"name": col_name, "type": col_type, "nullable": nullable})

        await db.execute(text("""
            INSERT INTO db_entities (project_id, entity_name, columns)
            VALUES (:pid, :name, CAST(:cols AS jsonb))
            ON CONFLICT (project_id, entity_name) DO UPDATE SET columns = EXCLUDED.columns
        """), {
            "pid": pid, "name": entity_name[:200],
            "cols": json.dumps(columns),
        })
        count += 1

    return count


# ── Import: Metadata ───────────────────────────────────────
async def _import_metadata(db: AsyncSession, pid: int, req_path: Path) -> int:
    mappings = [
        ("architecture", "architecture/architecture.json"),
        ("infrastructure", "infrastructure/infrastructure.json"),
        ("ui_design", "ui_design/ui_spec.json"),
        ("quality", "quality/self_critique_report.json"),
        ("content_analysis", "content_analysis.json"),
    ]
    count = 0

    for category, filename in mappings:
        filepath = req_path / filename
        if not filepath.exists():
            continue
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            continue

        await db.execute(text("""
            INSERT INTO project_metadata (project_id, category, data, source_file)
            VALUES (:pid, :cat, CAST(:data AS jsonb), :src)
            ON CONFLICT (project_id, category, source_file) DO UPDATE SET
                data = EXCLUDED.data, updated_at = NOW()
        """), {
            "pid": pid, "cat": category[:50],
            "data": json.dumps(data), "src": filename[:200],
        })
        count += 1

    return count


# ══════════════════════════════════════════════════════════
# API ENDPOINTS FOR UI TABS
# ══════════════════════════════════════════════════════════

@router.get("/epics/{project_id}")
async def get_epics(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get all epics for a project with task stats."""
    result = await db.execute(text("""
        SELECT epic_id, name, description, total_tasks, completed_tasks, failed_tasks, status
        FROM epics WHERE project_id = :pid ORDER BY epic_id
    """), {"pid": project_id})
    return {"epics": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/epics/{project_id}/{epic_id}/tasks")
async def get_epic_tasks(project_id: int, epic_id: str, db: AsyncSession = Depends(get_db)):
    """Get all tasks for a specific epic."""
    # Get job_id for this project
    job_result = await db.execute(text("""
        SELECT j.id FROM jobs j
        JOIN projects p ON p.id = j.project_id
        WHERE p.id = :pid ORDER BY j.created_at DESC LIMIT 1
    """), {"pid": project_id})
    job_row = job_result.fetchone()
    if not job_row:
        return {"tasks": []}

    result = await db.execute(text("""
        SELECT task_id, title, status, status_message, task_type, execution_time_ms
        FROM tasks WHERE job_id = :jid AND task_id LIKE :pattern ORDER BY task_id
    """), {"jid": job_row[0], "pattern": f"{epic_id}%"})
    return {"tasks": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/requirements/{project_id}")
async def get_requirements(
    project_id: int,
    type: str = Query("", description="Filter by type: user_story|requirement"),
    db: AsyncSession = Depends(get_db),
):
    """Get all requirements/user stories for a project."""
    if type:
        result = await db.execute(text("""
            SELECT req_id, type, title, persona, description, priority, acceptance_criteria, related_epic
            FROM requirements WHERE project_id = :pid AND type = :type ORDER BY req_id
        """), {"pid": project_id, "type": type})
    else:
        result = await db.execute(text("""
            SELECT req_id, type, title, persona, description, priority, acceptance_criteria, related_epic
            FROM requirements WHERE project_id = :pid ORDER BY req_id
        """), {"pid": project_id})
    return {"requirements": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/api-endpoints/{project_id}")
async def get_api_endpoints(
    project_id: int,
    tag: str = Query("", description="Filter by tag"),
    db: AsyncSession = Depends(get_db),
):
    """Get all API endpoints for a project."""
    if tag:
        result = await db.execute(text("""
            SELECT method, path, operation_id, summary, tags, auth_required
            FROM api_endpoints WHERE project_id = :pid AND tags::text LIKE :tag ORDER BY path, method
        """), {"pid": project_id, "tag": f"%{tag}%"})
    else:
        result = await db.execute(text("""
            SELECT method, path, operation_id, summary, tags, auth_required
            FROM api_endpoints WHERE project_id = :pid ORDER BY path, method
        """), {"pid": project_id})
    return {"endpoints": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/db-entities/{project_id}")
async def get_db_entities(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get all database entities for a project."""
    result = await db.execute(text("""
        SELECT entity_name, columns, enums, indexes, relationships
        FROM db_entities WHERE project_id = :pid ORDER BY entity_name
    """), {"pid": project_id})
    return {"entities": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/diagrams/{project_id}")
async def get_diagrams(
    project_id: int,
    type: str = Query("", description="Filter by type: sequence|c4|class|state|flowchart"),
    db: AsyncSession = Depends(get_db),
):
    """Get all diagrams for a project."""
    if type:
        result = await db.execute(text("""
            SELECT diagram_id, type, title, content, related_requirement
            FROM diagrams WHERE project_id = :pid AND type = :type ORDER BY diagram_id
        """), {"pid": project_id, "type": type})
    else:
        result = await db.execute(text("""
            SELECT diagram_id, type, title, content, related_requirement
            FROM diagrams WHERE project_id = :pid ORDER BY diagram_id
        """), {"pid": project_id})
    return {"diagrams": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/test-cases/{project_id}")
async def get_test_cases(
    project_id: int,
    type: str = Query("", description="Filter: e2e|integration|unit"),
    priority: str = Query("", description="Filter: high|medium|low"),
    db: AsyncSession = Depends(get_db),
):
    """Get all test cases for a project."""
    query = "SELECT test_id, type, title, description, priority, preconditions, related_requirement, related_user_story, status FROM test_cases WHERE project_id = :pid"
    params = {"pid": project_id}

    if type:
        query += " AND type = :type"
        params["type"] = type
    if priority:
        query += " AND priority = :priority"
        params["priority"] = priority

    query += " ORDER BY test_id"
    result = await db.execute(text(query), params)
    return {"test_cases": [dict(r._mapping) for r in result.fetchall()]}


@router.get("/project-metadata/{project_id}/{category}")
async def get_project_metadata(project_id: int, category: str, db: AsyncSession = Depends(get_db)):
    """Get project metadata by category (architecture, infrastructure, ui_design, quality)."""
    result = await db.execute(text("""
        SELECT category, data, source_file, updated_at
        FROM project_metadata WHERE project_id = :pid AND category = :cat
    """), {"pid": project_id, "cat": category})
    rows = [dict(r._mapping) for r in result.fetchall()]
    if len(rows) == 1:
        return rows[0]
    return {"metadata": rows}
