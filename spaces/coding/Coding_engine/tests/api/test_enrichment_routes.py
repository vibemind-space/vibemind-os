"""
Tests for src/api/routes/enrichment.py

Tests the enrichment pipeline visualization API endpoints.
NO MOCKS — tests the real helper functions and Pydantic models.
"""

import json
import pytest
import tempfile
from pathlib import Path

from src.api.routes.enrichment import (
    _find_enriched_file,
    _load_json_safe,
    _calculate_enrichment_score,
    EnrichmentStats,
    EnrichmentOverview,
    EnrichedTaskSummary,
    EnrichedTaskDetail,
    SchemaOverview,
    MappingOverview,
)


# ── Sample Data ─────────────────────────────────────────────────────────

SAMPLE_ENRICHED_TASKS = {
    "epic_id": "EPIC-001",
    "epic_name": "WhatsApp Auth System",
    "enrichment_timestamp": "2025-01-15T10:30:00Z",
    "enrichment_stats": {
        "total_tasks": 5,
        "tasks_with_requirements": 4,
        "tasks_with_user_stories": 3,
        "tasks_with_diagrams": 2,
        "tasks_with_warnings": 1,
        "tasks_with_dtos": 2,
        "tasks_with_success_criteria": 4,
        "tasks_with_test_scenarios": 3,
        "tasks_with_component_specs": 1,
        "tasks_with_screen_specs": 1,
        "tasks_with_accessibility": 1,
        "tasks_with_routes": 0,
        "tasks_with_design_tokens": 2,
    },
    "tasks": [
        {
            "id": "TASK-001",
            "epic_id": "EPIC-001",
            "type": "schema_migration",
            "title": "Create user authentication schema",
            "description": "Design and implement the Prisma schema for user auth",
            "status": "completed",
            "dependencies": ["TASK-000"],
            "related_requirements": ["REQ-001", "REQ-002"],
            "related_user_stories": ["US-001"],
            "success_criteria": "Schema compiles and migrates successfully",
            "enrichment_context": {
                "diagrams": ["erd-user-auth.mermaid"],
                "known_gaps": ["Missing rate limiting"],
                "related_dtos": ["UserDTO", "AuthDTO"],
                "test_scenarios": ["Login flow", "Registration flow"],
                "component_spec": None,
                "screen_spec": None,
                "accessibility_rules": None,
                "design_tokens": {"colors": {"primary": "#3b82f6"}},
            },
        },
        {
            "id": "TASK-002",
            "epic_id": "EPIC-001",
            "type": "api_endpoint",
            "title": "Implement login endpoint",
            "description": "POST /api/v1/auth/login",
            "status": "pending",
            "dependencies": ["TASK-001"],
            "related_requirements": ["REQ-003"],
            "related_user_stories": ["US-001", "US-002"],
            "success_criteria": "Endpoint returns JWT on valid credentials",
            "enrichment_context": {
                "diagrams": None,
                "known_gaps": None,
                "related_dtos": None,
                "test_scenarios": None,
                "component_spec": None,
                "screen_spec": None,
                "accessibility_rules": None,
                "design_tokens": None,
            },
        },
        {
            "id": "TASK-003",
            "epic_id": "EPIC-001",
            "type": "fe_component",
            "title": "Login form component",
            "description": "React login form with validation",
            "status": "pending",
            "dependencies": ["TASK-002"],
            "related_requirements": [],
            "related_user_stories": [],
            "success_criteria": None,
            "enrichment_context": {
                "diagrams": None,
                "known_gaps": None,
                "related_dtos": None,
                "test_scenarios": None,
                "component_spec": {"name": "LoginForm", "props": ["onSubmit"]},
                "screen_spec": {"route": "/login"},
                "accessibility_rules": ["WCAG 2.1 AA"],
                "design_tokens": {"spacing": {"sm": "8px"}},
            },
        },
    ],
}

SAMPLE_SCHEMA = {
    "project_name": "WhatsApp Auth",
    "language": "TypeScript",
    "requirement_id_pattern": "REQ-\\d{3}",
    "sources": {
        "requirements.md": {"type": "requirements", "count": 15},
        "user_stories.md": {"type": "stories", "count": 8},
    },
    "schema_hash": "abc123",
}

SAMPLE_MAPPING = {
    "llm_used": True,
    "mappings": {
        "TASK-001": {
            "inferred_type": "schema_migration",
            "requirement_ids": ["REQ-001"],
            "user_story_ids": ["US-001"],
        },
        "TASK-002": {
            "inferred_type": "api_endpoint",
            "requirement_ids": ["REQ-003"],
            "user_story_ids": [],
        },
        "TASK-003": {
            "inferred_type": "fe_component",
            "requirement_ids": [],
            "user_story_ids": [],
        },
    },
}


# ── Test _calculate_enrichment_score ────────────────────────────────────

class TestCalculateEnrichmentScore:
    """Test the enrichment score calculation."""

    def test_fully_enriched_task(self):
        """Task with all enrichment dimensions filled → score ~1.0."""
        task = {
            "related_requirements": ["REQ-001"],
            "related_user_stories": ["US-001"],
            "success_criteria": "Must pass tests",
            "enrichment_context": {
                "diagrams": ["diagram.mmd"],
                "known_gaps": ["gap1"],
                "related_dtos": ["DTO1"],
                "test_scenarios": ["scenario1"],
                "component_spec": {"name": "Comp"},
                "screen_spec": {"route": "/login"},
                "accessibility_rules": ["WCAG"],
                "design_tokens": {"colors": {}},
            },
        }
        score = _calculate_enrichment_score(task)
        assert score == 1.0

    def test_empty_task(self):
        """Task with no enrichment → score 0.0."""
        task = {
            "related_requirements": [],
            "related_user_stories": [],
            "success_criteria": None,
            "enrichment_context": {},
        }
        score = _calculate_enrichment_score(task)
        assert score == 0.0

    def test_partial_enrichment(self):
        """Task with some enrichment → score between 0 and 1."""
        task = {
            "related_requirements": ["REQ-001"],
            "related_user_stories": [],
            "success_criteria": "criteria",
            "enrichment_context": {
                "diagrams": ["d1"],
                "known_gaps": None,
                "related_dtos": None,
                "test_scenarios": None,
            },
        }
        score = _calculate_enrichment_score(task)
        assert 0.0 < score < 1.0
        # requirements + success_criteria + diagrams = 3 out of 11
        assert abs(score - 3.0 / 11.0) < 0.01

    def test_no_enrichment_context(self):
        """Task with no enrichment_context key → score based on top-level fields only."""
        task = {
            "related_requirements": ["REQ-001"],
            "related_user_stories": ["US-001"],
            "success_criteria": "criteria",
        }
        score = _calculate_enrichment_score(task)
        # requirements + user_stories + success_criteria = 3 out of 11
        assert abs(score - 3.0 / 11.0) < 0.01


# ── Test _find_enriched_file ────────────────────────────────────────────

class TestFindEnrichedFile:
    """Test finding enriched task files."""

    def test_direct_path_match(self, tmp_path):
        """Finds file via direct path pattern."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        enriched_file = tasks_dir / "epic-001-tasks-enriched.json"
        enriched_file.write_text(json.dumps({"epic_id": "EPIC-001"}), encoding="utf-8")

        result = _find_enriched_file(str(tmp_path), "EPIC-001")
        assert result is not None
        assert result.name == "epic-001-tasks-enriched.json"

    def test_lowercase_match(self, tmp_path):
        """Finds file with lowercase epic ID."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        enriched_file = tasks_dir / "epic-001-tasks-enriched.json"
        enriched_file.write_text(json.dumps({"epic_id": "EPIC-001"}), encoding="utf-8")

        result = _find_enriched_file(str(tmp_path), "epic-001")
        assert result is not None

    def test_glob_fallback(self, tmp_path):
        """Falls back to glob search when direct path doesn't match."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        # Non-standard filename
        enriched_file = tasks_dir / "my-project-enriched.json"
        enriched_file.write_text(
            json.dumps({"epic_id": "EPIC-042", "tasks": []}), encoding="utf-8"
        )

        result = _find_enriched_file(str(tmp_path), "EPIC-042")
        assert result is not None
        assert result.name == "my-project-enriched.json"

    def test_not_found(self, tmp_path):
        """Returns None when no enriched file exists."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        result = _find_enriched_file(str(tmp_path), "EPIC-999")
        assert result is None

    def test_no_tasks_dir(self, tmp_path):
        """Returns None when tasks directory doesn't exist."""
        result = _find_enriched_file(str(tmp_path), "EPIC-001")
        assert result is None


# ── Test _load_json_safe ────────────────────────────────────────────────

class TestLoadJsonSafe:
    """Test safe JSON loading."""

    def test_valid_json(self, tmp_path):
        """Loads valid JSON file."""
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = _load_json_safe(f)
        assert result == {"key": "value"}

    def test_invalid_json(self, tmp_path):
        """Returns None for invalid JSON."""
        f = tmp_path / "bad.json"
        f.write_text("not json {{{", encoding="utf-8")
        result = _load_json_safe(f)
        assert result is None

    def test_missing_file(self, tmp_path):
        """Returns None for missing file."""
        f = tmp_path / "nonexistent.json"
        result = _load_json_safe(f)
        assert result is None


# ── Test Pydantic Models ────────────────────────────────────────────────

class TestPydanticModels:
    """Test Pydantic model construction and defaults."""

    def test_enrichment_stats_defaults(self):
        """EnrichmentStats has proper defaults."""
        stats = EnrichmentStats()
        assert stats.total_tasks == 0
        assert stats.tasks_with_requirements == 0
        assert stats.tasks_with_design_tokens == 0

    def test_enrichment_stats_from_dict(self):
        """EnrichmentStats can be constructed from a dict."""
        data = {"total_tasks": 10, "tasks_with_requirements": 8}
        stats = EnrichmentStats(**{k: data.get(k, 0) for k in EnrichmentStats.model_fields})
        assert stats.total_tasks == 10
        assert stats.tasks_with_requirements == 8
        assert stats.tasks_with_diagrams == 0

    def test_enriched_task_summary(self):
        """EnrichedTaskSummary construction."""
        summary = EnrichedTaskSummary(
            id="TASK-001",
            epic_id="EPIC-001",
            type="schema_migration",
            title="Create schema",
            status="completed",
            has_requirements=True,
            has_user_stories=True,
            has_diagrams=True,
            has_warnings=False,
            has_dtos=True,
            has_success_criteria=True,
            has_test_scenarios=True,
            has_component_spec=False,
            has_screen_spec=False,
            has_accessibility=False,
            has_design_tokens=True,
            enrichment_score=0.72,
        )
        assert summary.id == "TASK-001"
        assert summary.enrichment_score == 0.72
        assert summary.has_requirements is True
        assert summary.has_component_spec is False

    def test_enriched_task_detail(self):
        """EnrichedTaskDetail with optional fields."""
        detail = EnrichedTaskDetail(
            id="TASK-002",
            epic_id="EPIC-001",
            type="api_endpoint",
            title="Login endpoint",
            description="POST /api/v1/auth/login",
            status="pending",
            dependencies=["TASK-001"],
            related_requirements=["REQ-003"],
            related_user_stories=[],
            success_criteria=None,
            enrichment_context=None,
        )
        assert detail.dependencies == ["TASK-001"]
        assert detail.success_criteria is None
        assert detail.enrichment_context is None

    def test_schema_overview_defaults(self):
        """SchemaOverview with defaults."""
        schema = SchemaOverview()
        assert schema.project_name is None
        assert schema.source_count == 0
        assert schema.sources == {}

    def test_mapping_overview_defaults(self):
        """MappingOverview with defaults."""
        mapping = MappingOverview()
        assert mapping.llm_used is False
        assert mapping.total_mappings == 0
        assert mapping.type_distribution == {}

    def test_enrichment_overview(self):
        """EnrichmentOverview construction."""
        stats = EnrichmentStats(total_tasks=5, tasks_with_requirements=4)
        overview = EnrichmentOverview(
            epic_id="EPIC-001",
            epic_name="Test Epic",
            enrichment_timestamp="2025-01-15T10:30:00Z",
            stats=stats,
            task_type_distribution={"schema_migration": 2, "api_endpoint": 3},
            enrichment_coverage={"requirements": 0.8, "user_stories": 0.6},
        )
        assert overview.epic_id == "EPIC-001"
        assert overview.stats.total_tasks == 5
        assert overview.task_type_distribution["api_endpoint"] == 3
        assert overview.enrichment_coverage["requirements"] == 0.8


# ── Test Enrichment Score Edge Cases ────────────────────────────────────

class TestEnrichmentScoreEdgeCases:
    """Additional edge case tests for enrichment scoring."""

    def test_empty_lists_count_as_false(self):
        """Empty lists should not count as enrichment."""
        task = {
            "related_requirements": [],
            "related_user_stories": [],
            "success_criteria": "",
            "enrichment_context": {
                "diagrams": [],
                "known_gaps": [],
                "related_dtos": [],
                "test_scenarios": [],
                "component_spec": {},
                "screen_spec": {},
                "accessibility_rules": [],
                "design_tokens": {},
            },
        }
        score = _calculate_enrichment_score(task)
        # Empty strings are falsy, empty dicts are falsy...
        # Actually {} is falsy in Python? No, {} is truthy!
        # But [] is falsy, "" is falsy
        # So component_spec={} → truthy, screen_spec={} → truthy, design_tokens={} → truthy
        # That means: component_spec + screen_spec + design_tokens = 3 truthy
        # Actually wait: bool({}) is False in Python. Let me verify...
        # Actually bool({}) is False! So all empty containers are falsy.
        assert score == 0.0

    def test_none_enrichment_context_values(self):
        """None values in enrichment_context don't contribute to score."""
        task = {
            "related_requirements": None,
            "related_user_stories": None,
            "success_criteria": None,
            "enrichment_context": None,
        }
        score = _calculate_enrichment_score(task)
        assert score == 0.0


# ── Test File Discovery with Real Structure ─────────────────────────────

class TestFileDiscoveryRealStructure:
    """Test file discovery with project-like directory structures."""

    def test_enriched_file_with_enrichment_cache(self, tmp_path):
        """Test that schema and mapping files are found in .enrichment_cache."""
        cache_dir = tmp_path / ".enrichment_cache"
        cache_dir.mkdir()

        schema = {"project_name": "Test", "sources": {}}
        (cache_dir / "project_schema.json").write_text(
            json.dumps(schema), encoding="utf-8"
        )

        mapping = {"llm_used": True, "mappings": {}}
        (cache_dir / "task_mapping.json").write_text(
            json.dumps(mapping), encoding="utf-8"
        )

        # Verify schema loads
        result = _load_json_safe(cache_dir / "project_schema.json")
        assert result is not None
        assert result["project_name"] == "Test"

        # Verify mapping loads
        result = _load_json_safe(cache_dir / "task_mapping.json")
        assert result is not None
        assert result["llm_used"] is True

    def test_multiple_enriched_files_finds_correct_epic(self, tmp_path):
        """When multiple enriched files exist, finds the one matching the epic ID."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # Two enriched files for different epics
        (tasks_dir / "project-enriched.json").write_text(
            json.dumps({"epic_id": "EPIC-001", "tasks": []}), encoding="utf-8"
        )
        (tasks_dir / "other-enriched.json").write_text(
            json.dumps({"epic_id": "EPIC-002", "tasks": []}), encoding="utf-8"
        )

        result = _find_enriched_file(str(tmp_path), "EPIC-002")
        assert result is not None
        assert "other-enriched" in result.name
