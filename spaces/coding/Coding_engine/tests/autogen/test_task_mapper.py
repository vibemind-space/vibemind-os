"""Tests for Phase 30: TaskMapper."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.autogen.schema_discoverer import FileSource, ProjectSchema
from src.autogen.task_mapper import TaskMapper, TaskMapping, TaskMappingResult


@pytest.fixture
def project_dir(tmp_path):
    """Create a project structure for task mapping tests."""
    # user_stories.json with linked_requirement_ids
    (tmp_path / "user_stories.json").write_text(json.dumps({
        "user_stories": [
            {
                "id": "US-001",
                "title": "Phone Registration",
                "persona": "user",
                "action": "register with phone",
                "benefit": "access",
                "parent_requirement_id": "WA-AUTH-001",
                "linked_requirement_ids": ["WA-AUTH-001"],
            },
            {
                "id": "US-002",
                "title": "Two-Factor Auth",
                "persona": "user",
                "action": "enable 2FA",
                "benefit": "security",
                "parent_requirement_id": "WA-AUTH-002",
                "linked_requirement_ids": ["WA-AUTH-002"],
            },
        ]
    }), encoding="utf-8")

    # ui_design/components.md
    ui_dir = tmp_path / "ui_design"
    ui_dir.mkdir()
    (ui_dir / "components.md").write_text(
        "## Button\n**ID:** `COMP-001`\n---\n## TextInput\n**ID:** `COMP-002`\n---\n"
        "## OTPInput\n**ID:** `COMP-003`\n",
        encoding="utf-8",
    )

    # ui_design/screens/
    screens_dir = ui_dir / "screens"
    screens_dir.mkdir()
    (screens_dir / "screen-001.md").write_text(
        "# 2FA Screen\n**ID:** `SCREEN-001`\n**Route:** `/settings/2fa`\n",
        encoding="utf-8",
    )
    (screens_dir / "screen-002.md").write_text(
        "# Registration\n**ID:** `SCREEN-002`\n**Route:** `/register`\n",
        encoding="utf-8",
    )

    # testing/ feature files
    testing_dir = tmp_path / "testing"
    testing_dir.mkdir()
    (testing_dir / "us_001.feature").write_text("Feature: Phone Reg\n", encoding="utf-8")
    (testing_dir / "us_002.feature").write_text("Feature: 2FA\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def schema():
    """Create a ProjectSchema for tests."""
    return ProjectSchema(
        project_name="Test",
        language="de",
        requirement_id_pattern="WA-[A-Z]+-\\d+",
        sources={
            "user_stories": FileSource(
                file="user_stories.json",
                format="json",
                purpose="user_stories",
                id_field="id",
                id_pattern="US-\\d+",
                key_fields={
                    "id": "id",
                    "requirement_link": "linked_requirement_ids",
                },
            ),
            "screens": FileSource(
                file="ui_design/screens",
                format="markdown",
                purpose="screens",
                id_pattern="SCREEN-\\d+",
                structure="directory",
            ),
            "components": FileSource(
                file="ui_design/components.md",
                format="markdown",
                purpose="components",
                id_pattern="COMP-\\d+",
                structure="markdown_sections",
            ),
            "gherkin_features": FileSource(
                file="testing",
                format="gherkin",
                purpose="gherkin_features",
                structure="directory",
            ),
        },
    )


class FakeTask:
    """Minimal task object for testing."""
    def __init__(self, id, title, type="development", description="", acceptance_criteria=None):
        self.id = id
        self.title = title
        self.type = type
        self.description = description
        self.acceptance_criteria = acceptance_criteria or []


class TestTaskMappingResult:
    """Tests for TaskMappingResult serialization."""

    def test_to_dict_empty(self):
        result = TaskMappingResult()
        d = result.to_dict()
        assert d["mappings"] == {}
        assert d["llm_used"] is False

    def test_to_dict_with_mappings(self):
        result = TaskMappingResult(
            llm_used=True,
            mappings={
                "TASK-001": TaskMapping(
                    task_id="TASK-001",
                    inferred_type="api_controller",
                    requirement_ids=["WA-AUTH-001"],
                    user_story_ids=["US-001"],
                ),
            },
        )
        d = result.to_dict()
        assert d["llm_used"] is True
        assert "TASK-001" in d["mappings"]
        assert d["mappings"]["TASK-001"]["inferred_type"] == "api_controller"
        assert d["mappings"]["TASK-001"]["requirement_ids"] == ["WA-AUTH-001"]

    def test_from_dict_roundtrip(self):
        original = TaskMappingResult(
            llm_used=True,
            mappings={
                "T-1": TaskMapping(
                    task_id="T-1",
                    inferred_type="fe_page",
                    screen_ids=["SCREEN-001"],
                    component_ids=["COMP-001", "COMP-002"],
                ),
            },
        )
        d = original.to_dict()
        restored = TaskMappingResult.from_dict(d)
        assert restored.llm_used is True
        assert "T-1" in restored.mappings
        assert restored.mappings["T-1"].inferred_type == "fe_page"
        assert restored.mappings["T-1"].screen_ids == ["SCREEN-001"]


class TestArtifactGathering:
    """Tests for artifact ID collection."""

    def test_gathers_requirement_ids(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        artifacts = mapper._gather_artifact_ids()
        assert "WA-AUTH-001" in artifacts["requirement_ids"]
        assert "WA-AUTH-002" in artifacts["requirement_ids"]

    def test_gathers_user_story_ids(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        artifacts = mapper._gather_artifact_ids()
        assert "US-001" in artifacts["user_story_ids"]
        assert "US-002" in artifacts["user_story_ids"]

    def test_gathers_screen_ids(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        artifacts = mapper._gather_artifact_ids()
        assert "SCREEN-001" in artifacts["screen_ids"]
        assert "SCREEN-002" in artifacts["screen_ids"]

    def test_gathers_component_ids(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        artifacts = mapper._gather_artifact_ids()
        assert "COMP-001" in artifacts["component_ids"]
        assert "COMP-002" in artifacts["component_ids"]
        assert "COMP-003" in artifacts["component_ids"]

    def test_gathers_feature_files(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        artifacts = mapper._gather_artifact_ids()
        assert "us_001.feature" in artifacts["feature_files"]
        assert "us_002.feature" in artifacts["feature_files"]

    def test_handles_missing_directories(self, tmp_path, schema):
        mapper = TaskMapper(tmp_path, schema, api_key="")
        artifacts = mapper._gather_artifact_ids()
        assert artifacts["requirement_ids"] == []
        assert artifacts["screen_ids"] == []


class TestTaskSummaryBuilding:
    """Tests for task summary creation."""

    def test_builds_summaries(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        tasks = [
            FakeTask("T-1", "Backend Auth", "development", "Implement auth"),
            FakeTask("T-2", "Frontend Login", "development"),
        ]
        summaries = mapper._build_task_summaries(tasks)
        assert len(summaries) == 2
        assert summaries[0]["id"] == "T-1"
        assert summaries[0]["title"] == "Backend Auth"
        assert summaries[0]["description"] == "Implement auth"

    def test_truncates_long_descriptions(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        tasks = [FakeTask("T-1", "Title", description="x" * 500)]
        summaries = mapper._build_task_summaries(tasks)
        assert len(summaries[0]["description"]) <= 200

    def test_includes_acceptance_criteria(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        tasks = [FakeTask("T-1", "Title", acceptance_criteria=["a", "b", "c", "d"])]
        summaries = mapper._build_task_summaries(tasks)
        assert len(summaries[0]["acceptance_criteria"]) == 3  # capped at 3


class TestLLMMapping:
    """Tests for LLM-based mapping (mocked)."""

    def test_llm_produces_valid_mapping(self, project_dir, schema):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "mappings": {
                "TASK-001": {
                    "inferred_type": "api_controller",
                    "requirement_ids": ["WA-AUTH-001"],
                    "user_story_ids": ["US-001"],
                    "screen_ids": [],
                    "component_ids": [],
                    "feature_files": ["us_001.feature"],
                    "keywords": ["registration", "phone"],
                },
                "TASK-002": {
                    "inferred_type": "fe_page",
                    "requirement_ids": ["WA-AUTH-002"],
                    "user_story_ids": ["US-002"],
                    "screen_ids": ["SCREEN-001"],
                    "component_ids": ["COMP-003"],
                    "feature_files": [],
                    "keywords": ["2fa", "security"],
                },
            }
        }))]

        with patch("src.autogen.task_mapper.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.Anthropic.return_value = mock_client

            mapper = TaskMapper(project_dir, schema, api_key="test-key")
            tasks = [
                FakeTask("TASK-001", "Phone Registration Backend"),
                FakeTask("TASK-002", "2FA Frontend"),
            ]
            result = mapper.map_tasks(tasks)

            assert result.llm_used is True
            assert "TASK-001" in result.mappings
            assert result.mappings["TASK-001"].inferred_type == "api_controller"
            assert result.mappings["TASK-001"].requirement_ids == ["WA-AUTH-001"]
            assert result.mappings["TASK-002"].screen_ids == ["SCREEN-001"]

    def test_validates_artifact_ids(self, project_dir, schema):
        """LLM-returned IDs that don't exist in project are filtered out."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "mappings": {
                "TASK-001": {
                    "inferred_type": "api_controller",
                    "requirement_ids": ["WA-AUTH-001", "FAKE-REQ-999"],
                    "user_story_ids": ["US-001", "US-999"],
                    "screen_ids": ["SCREEN-001", "SCREEN-999"],
                    "component_ids": ["COMP-001", "COMP-999"],
                    "feature_files": ["us_001.feature", "nonexistent.feature"],
                    "keywords": [],
                }
            }
        }))]

        with patch("src.autogen.task_mapper.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.Anthropic.return_value = mock_client

            mapper = TaskMapper(project_dir, schema, api_key="test-key")
            result = mapper.map_tasks([FakeTask("TASK-001", "Test")])

            m = result.mappings["TASK-001"]
            assert "WA-AUTH-001" in m.requirement_ids
            assert "FAKE-REQ-999" not in m.requirement_ids
            assert "US-001" in m.user_story_ids
            assert "US-999" not in m.user_story_ids
            assert "SCREEN-001" in m.screen_ids
            assert "SCREEN-999" not in m.screen_ids
            assert "COMP-001" in m.component_ids
            assert "COMP-999" not in m.component_ids
            assert "us_001.feature" in m.feature_files
            assert "nonexistent.feature" not in m.feature_files

    def test_validates_inferred_type(self, project_dir, schema):
        """Invalid inferred types are cleared."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "mappings": {
                "T-1": {
                    "inferred_type": "invalid_type_foobar",
                    "requirement_ids": [],
                    "user_story_ids": [],
                    "screen_ids": [],
                    "component_ids": [],
                    "feature_files": [],
                    "keywords": [],
                }
            }
        }))]

        with patch("src.autogen.task_mapper.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.Anthropic.return_value = mock_client

            mapper = TaskMapper(project_dir, schema, api_key="test-key")
            result = mapper.map_tasks([FakeTask("T-1", "Test")])
            assert result.mappings["T-1"].inferred_type == ""

    def test_handles_llm_error(self, project_dir, schema):
        with patch("src.autogen.task_mapper.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API timeout")
            mock_anthropic.Anthropic.return_value = mock_client

            mapper = TaskMapper(project_dir, schema, api_key="test-key")
            result = mapper.map_tasks([FakeTask("T-1", "Test")])
            assert not result.llm_used
            assert "API timeout" in result.error

    def test_no_api_key_returns_empty(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        result = mapper.map_tasks([FakeTask("T-1", "Test")])
        assert not result.llm_used
        assert result.error == "no_api_key"

    def test_empty_task_list(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="test-key")
        result = mapper.map_tasks([])
        assert len(result.mappings) == 0


class TestMappingPersistence:
    """Tests for saving/loading mappings."""

    def test_save_mapping(self, project_dir, schema):
        mapper = TaskMapper(project_dir, schema, api_key="")
        result = TaskMappingResult(
            llm_used=True,
            mappings={"T-1": TaskMapping(task_id="T-1", inferred_type="fe_page")},
        )
        mapper._save_mapping(result)

        cache_file = project_dir / ".enrichment_cache" / "task_mapping.json"
        assert cache_file.exists()
        loaded = json.loads(cache_file.read_text(encoding="utf-8"))
        assert loaded["llm_used"] is True
        assert "T-1" in loaded["mappings"]
