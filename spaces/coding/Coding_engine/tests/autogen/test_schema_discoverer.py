"""Tests for Phase 30: SchemaDiscoverer."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.autogen.schema_discoverer import (
    FileSource,
    ProjectSchema,
    SchemaDiscoverer,
)


@pytest.fixture
def project_dir(tmp_path):
    """Create a realistic project structure for testing."""
    # tasks/task_list.json
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task_list.json").write_text(json.dumps({
        "project_name": "Test Project",
        "features": {
            "FEAT-001": [
                {
                    "id": "TASK-001",
                    "title": "User Registration Backend",
                    "description": "Implement registration",
                    "task_type": "development",
                    "parent_feature_id": "FEAT-001",
                    "parent_requirement_id": "",
                    "parent_user_story_id": "",
                }
            ]
        }
    }), encoding="utf-8")

    # user_stories.json
    (tmp_path / "user_stories.json").write_text(json.dumps({
        "user_stories": [
            {
                "id": "US-001",
                "title": "User Registration",
                "persona": "new user",
                "action": "register with phone",
                "benefit": "access the platform",
                "parent_requirement_id": "APP-AUTH-001",
                "linked_requirement_ids": ["APP-AUTH-001"],
            }
        ]
    }), encoding="utf-8")

    # ui_design/components.md
    ui_dir = tmp_path / "ui_design"
    ui_dir.mkdir()
    (ui_dir / "components.md").write_text(
        "# Component Library\n\n## Button\n\n**ID:** `COMP-001`\n\n---\n\n"
        "## TextInput\n\n**ID:** `COMP-002`\n",
        encoding="utf-8",
    )

    # ui_design/design_tokens.json
    (ui_dir / "design_tokens.json").write_text(json.dumps({
        "colors": {"primary": "#007AFF"},
        "typography": {"h1": {"size": "32px", "weight": "bold"}},
    }), encoding="utf-8")

    # ui_design/screens/
    screens_dir = ui_dir / "screens"
    screens_dir.mkdir()
    (screens_dir / "screen-screen-001.md").write_text(
        "# Login Screen\n\n**ID:** `SCREEN-001`\n**Route:** `/login`\n",
        encoding="utf-8",
    )

    # testing/us_001.feature
    testing_dir = tmp_path / "testing"
    testing_dir.mkdir()
    (testing_dir / "us_001.feature").write_text(
        "@smoke\nFeature: User Registration\n  Scenario: Happy path\n    Given user is on registration\n",
        encoding="utf-8",
    )

    # diagrams/
    diagrams_dir = tmp_path / "diagrams"
    diagrams_dir.mkdir()
    (diagrams_dir / "APP-AUTH-001_sequence.mmd").write_text(
        "sequenceDiagram\n  User->>Server: Register\n", encoding="utf-8"
    )

    # ux_design/
    ux_dir = tmp_path / "ux_design"
    ux_dir.mkdir()
    (ux_dir / "accessibility_checklist.md").write_text(
        "# WCAG 2.1 AA\n- [ ] Keyboard navigation\n- [ ] Color contrast 4.5:1\n",
        encoding="utf-8",
    )
    (ux_dir / "information_architecture.md").write_text(
        "# Site Map\n- **Login** (`/login`)\n    - Content: forms, inputs\n",
        encoding="utf-8",
    )

    # data/data_dictionary.md
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "data_dictionary.md").write_text(
        "### User\n\nUser table\n\n*Source Requirements:* APP-AUTH-001, APP-AUTH-002\n\n| Field |\n",
        encoding="utf-8",
    )

    # quality/self_critique_report.json
    quality_dir = tmp_path / "quality"
    quality_dir.mkdir()
    (quality_dir / "self_critique_report.json").write_text(json.dumps({
        "issues": [
            {
                "id": "SC-001",
                "severity": "high",
                "title": "Missing input validation",
                "suggestion": "Add server-side validation",
                "affected_artifacts": ["APP-AUTH-001"],
            }
        ]
    }), encoding="utf-8")

    return tmp_path


class TestProjectSchema:
    """Tests for ProjectSchema data class."""

    def test_to_dict_empty(self):
        schema = ProjectSchema()
        d = schema.to_dict()
        assert d["project_name"] == ""
        assert d["language"] == "en"
        assert d["sources"] == {}

    def test_to_dict_with_sources(self):
        schema = ProjectSchema(
            project_name="Test",
            language="de",
            sources={
                "tasks": FileSource(
                    file="tasks/list.json",
                    format="json",
                    purpose="tasks",
                    id_pattern="TASK-\\d+",
                ),
            },
        )
        d = schema.to_dict()
        assert d["project_name"] == "Test"
        assert d["language"] == "de"
        assert "tasks" in d["sources"]
        assert d["sources"]["tasks"]["id_pattern"] == "TASK-\\d+"

    def test_from_dict_roundtrip(self):
        original = ProjectSchema(
            project_name="MyProject",
            language="de",
            requirement_id_pattern="WA-[A-Z]+-\\d+",
            diagram_naming="{requirement_id}_{type}.mmd",
            schema_hash="abc123",
            sources={
                "tasks": FileSource(
                    file="tasks/list.json",
                    format="json",
                    purpose="tasks",
                    id_field="id",
                    id_pattern="TASK-\\d+",
                    structure="nested_by_feature",
                    key_fields={"title": "title", "type": "task_type"},
                ),
            },
        )
        d = original.to_dict()
        restored = ProjectSchema.from_dict(d)
        assert restored.project_name == "MyProject"
        assert restored.language == "de"
        assert restored.schema_hash == "abc123"
        assert "tasks" in restored.sources
        assert restored.sources["tasks"].id_pattern == "TASK-\\d+"
        assert restored.sources["tasks"].key_fields["type"] == "task_type"


class TestSchemaDiscovererSampling:
    """Tests for file sampling logic."""

    def test_samples_files_from_directories(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        paths = [s["path"] for s in samples if s["header"]]
        assert any("task_list.json" in p for p in paths)
        assert any("user_stories.json" in p for p in paths)
        assert any("components.md" in p for p in paths)

    def test_samples_contain_headers(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        for sample in samples:
            if sample["header"]:
                assert len(sample["header"]) > 0
                assert sample["size_bytes"] > 0

    def test_deduplication_limits_similar_files(self, project_dir):
        # Create 10 similar screen files
        screens_dir = project_dir / "ui_design" / "screens"
        for i in range(10):
            (screens_dir / f"screen-screen-{i:03d}.md").write_text(
                f"# Screen {i}\n\n**ID:** `SCREEN-{i:03d}`\n", encoding="utf-8"
            )
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        screen_samples = [s for s in samples if "screen-screen-" in s["path"]]
        # Should be capped at 3 real samples + 1 "... and N more" note
        real_samples = [s for s in screen_samples if s["header"]]
        assert len(real_samples) <= 3

    def test_skips_non_doc_extensions(self, project_dir):
        (project_dir / "tasks" / "compiled.pyc").write_bytes(b"\x00\x01\x02")
        (project_dir / "tasks" / "binary.bin").write_bytes(b"\x00\x01\x02")
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        paths = [s["path"] for s in samples]
        assert not any(p.endswith(".pyc") for p in paths)
        assert not any(p.endswith(".bin") for p in paths)


class TestSchemaDiscovererHeuristic:
    """Tests for the heuristic fallback (no LLM)."""

    def test_detects_task_source(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "tasks" in schema.sources
        assert schema.sources["tasks"].format == "json"

    def test_detects_user_stories(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "user_stories" in schema.sources

    def test_detects_components(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "components" in schema.sources
        assert schema.sources["components"].structure == "markdown_sections"

    def test_detects_gherkin_features(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "gherkin_features" in schema.sources
        assert schema.sources["gherkin_features"].format == "gherkin"
        assert schema.sources["gherkin_features"].structure == "directory"

    def test_detects_diagrams(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "diagrams" in schema.sources
        assert schema.sources["diagrams"].format == "mermaid"

    def test_detects_design_tokens(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "design_tokens" in schema.sources

    def test_detects_accessibility(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "accessibility" in schema.sources

    def test_detects_routes(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "routes" in schema.sources

    def test_detects_quality_report(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "quality_report" in schema.sources

    def test_detects_data_dictionary(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert "data_dictionary" in schema.sources

    def test_detects_german_language(self, project_dir):
        # Add German content
        (project_dir / "tasks" / "task_list.json").write_text(json.dumps({
            "features": {"FEAT-001": [{"id": "T-1", "title": "Implementierung der Authentifizierung"}]}
        }), encoding="utf-8")
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert schema.language == "de"

    def test_empty_project(self, tmp_path):
        discoverer = SchemaDiscoverer(tmp_path, api_key="")
        samples = discoverer._sample_file_headers()
        schema = discoverer._heuristic_fallback(samples)
        assert len(schema.sources) == 0


class TestSchemaDiscovererCaching:
    """Tests for caching."""

    def test_compute_file_hash_deterministic(self, project_dir):
        d1 = SchemaDiscoverer(project_dir, api_key="")
        d2 = SchemaDiscoverer(project_dir, api_key="")
        assert d1._compute_file_hash() == d2._compute_file_hash()

    def test_hash_changes_on_new_file(self, project_dir):
        d1 = SchemaDiscoverer(project_dir, api_key="")
        hash1 = d1._compute_file_hash()
        (project_dir / "tasks" / "extra.json").write_text("{}", encoding="utf-8")
        hash2 = d1._compute_file_hash()
        assert hash1 != hash2

    def test_save_and_load_cache(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        schema = ProjectSchema(
            project_name="CacheTest",
            schema_hash="test_hash_123",
            sources={"tasks": FileSource(file="tasks/list.json", format="json", purpose="tasks")},
        )
        discoverer._save_cache(schema)
        loaded = discoverer._load_cache("test_hash_123")
        assert loaded is not None
        assert loaded.project_name == "CacheTest"
        assert "tasks" in loaded.sources

    def test_cache_miss_on_hash_mismatch(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        schema = ProjectSchema(schema_hash="old_hash")
        discoverer._save_cache(schema)
        loaded = discoverer._load_cache("new_hash")
        assert loaded is None

    def test_discover_uses_cache(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        current_hash = discoverer._compute_file_hash()
        schema = ProjectSchema(
            project_name="Cached",
            schema_hash=current_hash,
            sources={"tasks": FileSource(file="t.json", format="json", purpose="tasks")},
        )
        discoverer._save_cache(schema)
        result = discoverer.discover()
        assert result.project_name == "Cached"

    def test_discover_force_bypasses_cache(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        current_hash = discoverer._compute_file_hash()
        schema = ProjectSchema(project_name="Cached", schema_hash=current_hash)
        discoverer._save_cache(schema)
        # Force should bypass cache and use heuristic (no API key)
        result = discoverer.discover(force=True)
        assert result.project_name != "Cached"


class TestSchemaDiscovererLLM:
    """Tests for LLM integration (mocked)."""

    def test_llm_called_when_api_key_present(self, project_dir):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "project_name": "LLM-Discovered",
            "language": "de",
            "requirement_id_pattern": "WA-[A-Z]+-\\d+",
            "diagram_naming": "",
            "sources": {
                "tasks": {
                    "file": "tasks/task_list.json",
                    "format": "json",
                    "purpose": "tasks",
                    "id_field": "id",
                    "id_pattern": "TASK-\\d+",
                    "structure": "nested_by_feature",
                    "key_fields": {"title": "title"},
                }
            },
        }))]

        with patch("src.autogen.schema_discoverer.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.Anthropic.return_value = mock_client

            discoverer = SchemaDiscoverer(project_dir, api_key="test-key")
            result = discoverer.discover(force=True)

            assert result.project_name == "LLM-Discovered"
            assert result.language == "de"
            assert "tasks" in result.sources

    def test_extract_json_from_code_block(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        text = 'Some text\n```json\n{"key": "value"}\n```\nmore text'
        result = discoverer._extract_json(text)
        assert json.loads(result) == {"key": "value"}

    def test_extract_json_from_raw(self, project_dir):
        discoverer = SchemaDiscoverer(project_dir, api_key="")
        text = 'Here is the result: {"key": "value"} end'
        result = discoverer._extract_json(text)
        assert json.loads(result) == {"key": "value"}

    def test_fallback_on_llm_error(self, project_dir):
        with patch("src.autogen.schema_discoverer.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API error")
            mock_anthropic.Anthropic.return_value = mock_client

            discoverer = SchemaDiscoverer(project_dir, api_key="test-key")
            result = discoverer.discover(force=True)
            # Should fall back to heuristic
            assert len(result.sources) > 0
