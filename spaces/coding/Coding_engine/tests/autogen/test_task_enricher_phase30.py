"""Tests for Phase 30: TaskEnricher with LLM task mapping integration."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from src.autogen.task_enricher import TaskEnricher
from src.autogen.task_mapper import TaskMapping, TaskMappingResult


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class FakeTask:
    """Minimal task for testing."""
    def __init__(self, id, title, type="development", description="",
                 related_requirements=None, related_user_stories=None,
                 enrichment_context=None, success_criteria=None,
                 epic_id="EPIC-001", dependencies=None, estimated_minutes=60,
                 output_files=None, status="pending", phase=1):
        self.id = id
        self.title = title
        self.type = type
        self.description = description
        self.related_requirements = related_requirements or []
        self.related_user_stories = related_user_stories or []
        self.enrichment_context = enrichment_context
        self.success_criteria = success_criteria
        self.epic_id = epic_id
        self.dependencies = dependencies or []
        self.estimated_minutes = estimated_minutes
        self.output_files = output_files or []
        self.status = status
        self.phase = phase


class FakeTaskList:
    """Minimal task list for testing."""
    def __init__(self, tasks, epic_id="EPIC-001"):
        self.tasks = tasks
        self.epic_id = epic_id
        self.epic_name = "Test Epic"


@pytest.fixture
def project_dir(tmp_path):
    """Create a project with all documentation formats."""
    # user_stories.json — new format with linked_requirement_ids
    (tmp_path / "user_stories.json").write_text(json.dumps({
        "user_stories": [
            {
                "id": "US-001",
                "title": "Phone Registration",
                "persona": "new user",
                "action": "register with phone number",
                "benefit": "access the platform",
                "parent_requirement_id": "WA-AUTH-001",
                "linked_requirement_ids": ["WA-AUTH-001"],
            },
            {
                "id": "US-002",
                "title": "Two-Factor Auth",
                "persona": "registered user",
                "action": "enable 2FA with PIN",
                "benefit": "protect my account",
                "parent_requirement_id": "WA-AUTH-002",
                "linked_requirement_ids": ["WA-AUTH-002"],
            },
        ]
    }), encoding="utf-8")

    # data/data_dictionary.md
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "data_dictionary.md").write_text(
        "### User\n\nUser table\n\n*Source Requirements:* WA-AUTH-001\n\n| Field |\n",
        encoding="utf-8",
    )

    # diagrams/
    diagrams_dir = tmp_path / "diagrams"
    diagrams_dir.mkdir()
    (diagrams_dir / "WA-AUTH-001_sequence.mmd").write_text(
        "sequenceDiagram\n  User->>Server: Register\n", encoding="utf-8"
    )
    (diagrams_dir / "WA-AUTH-002_flowchart.mmd").write_text(
        "flowchart TD\n  A[Start] --> B[Enable 2FA]\n", encoding="utf-8"
    )

    # ui_design/
    ui_dir = tmp_path / "ui_design"
    ui_dir.mkdir()
    (ui_dir / "components.md").write_text(
        "# Component Library\n\n## Button\n\n**ID:** `COMP-001`\n**Type:** button\n\n"
        "### Props\n\n| Prop | Type |\n|------|------|\n| `onClick` | `() => void` |\n\n"
        "### Variants\n\n- `primary`\n- `secondary`\n\n"
        "### Accessibility\n\n- **role:** button\n\n---\n\n"
        "## OTPInput\n\n**ID:** `COMP-003`\n**Type:** input\n\n"
        "### Props\n\n| Prop | Type |\n|------|------|\n| `length` | `number` |\n\n"
        "### Variants\n\n- `default`\n\n"
        "### Accessibility\n\n- **role:** group\n\n---\n",
        encoding="utf-8",
    )
    (ui_dir / "design_tokens.json").write_text(json.dumps({
        "colors": {"primary": "#007AFF", "secondary": "#5856D6"},
        "typography": {"h1": {"size": "32px", "weight": "bold"}},
        "spacing": {"sm": "0.5rem", "md": "1rem"},
    }), encoding="utf-8")

    # ui_design/screens/
    screens_dir = ui_dir / "screens"
    screens_dir.mkdir()
    (screens_dir / "screen-screen-001.md").write_text(
        "# 2FA Setup\n\n**ID:** `SCREEN-001`\n**Route:** `/settings/2fa`\n\n"
        "## Components Used\n\n- `COMP-001`\n- `COMP-003`\n\n"
        "## Data Requirements\n\n- `POST /api/settings/2fa/enable`\n\n"
        "## Related User Story\n\n`US-002`\n",
        encoding="utf-8",
    )

    # testing/ — individual .feature files
    testing_dir = tmp_path / "testing"
    testing_dir.mkdir()
    (testing_dir / "us_001.feature").write_text(
        "@smoke @regression\n"
        "Feature: Phone Registration\n"
        "  Scenario: Successful registration\n"
        "    Given user opens registration\n"
        "    When user enters valid phone\n"
        "    Then account is created\n",
        encoding="utf-8",
    )
    (testing_dir / "us_002.feature").write_text(
        "@smoke\n"
        "Feature: Two-Factor Authentication\n"
        "  Scenario: Enable 2FA\n"
        "    Given user is logged in\n"
        "    When user enables 2FA with PIN\n"
        "    Then 2FA is active\n",
        encoding="utf-8",
    )

    # ux_design/
    ux_dir = tmp_path / "ux_design"
    ux_dir.mkdir()
    (ux_dir / "accessibility_checklist.md").write_text(
        "# WCAG 2.1 AA\n- [ ] Keyboard navigation\n- [ ] Color contrast 4.5:1\n",
        encoding="utf-8",
    )
    (ux_dir / "information_architecture.md").write_text(
        "# Site Map\n- **2FA Settings** (`/settings/2fa`)\n    - Content: PIN input, toggle\n",
        encoding="utf-8",
    )

    # quality/
    quality_dir = tmp_path / "quality"
    quality_dir.mkdir()
    (quality_dir / "self_critique_report.json").write_text(json.dumps({
        "issues": [{
            "id": "SC-001", "severity": "high",
            "title": "Missing rate limiting",
            "suggestion": "Add rate limiting to auth endpoints",
            "affected_artifacts": ["WA-AUTH-001"],
        }]
    }), encoding="utf-8")

    # tasks/ dir for saving enriched output
    (tmp_path / "tasks").mkdir()

    return tmp_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTS: LLM Mapping Integration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestEnricherWithMapping:
    """Tests for TaskEnricher using pre-computed LLM mappings."""

    def _make_mapping(self, mappings_dict):
        """Build a TaskMappingResult from a dict."""
        result = TaskMappingResult(llm_used=True)
        for task_id, data in mappings_dict.items():
            result.mappings[task_id] = TaskMapping(
                task_id=task_id,
                inferred_type=data.get("inferred_type", ""),
                requirement_ids=data.get("requirement_ids", []),
                user_story_ids=data.get("user_story_ids", []),
                screen_ids=data.get("screen_ids", []),
                component_ids=data.get("component_ids", []),
                feature_files=data.get("feature_files", []),
                keywords=data.get("keywords", []),
            )
        return result

    def test_mapping_fills_requirements(self, project_dir):
        """LLM mapping provides requirements that regex cannot infer."""
        mapping = self._make_mapping({
            "TASK-001": {
                "inferred_type": "api_controller",
                "requirement_ids": ["WA-AUTH-001"],
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-001", "Telefonnummer-Registrierung Backend")
        changes = enricher._enrich_task(task)

        assert "WA-AUTH-001" in task.related_requirements
        assert changes > 0

    def test_mapping_fills_user_stories(self, project_dir):
        """LLM mapping provides user stories directly."""
        mapping = self._make_mapping({
            "TASK-002": {
                "inferred_type": "fe_page",
                "user_story_ids": ["US-002"],
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-002", "2FA Frontend")
        enricher._enrich_task(task)

        assert "US-002" in task.related_user_stories

    def test_inferred_type_enables_fe_enrichment(self, project_dir):
        """Task with generic type="development" gets fe_page enrichment via inferred_type."""
        mapping = self._make_mapping({
            "TASK-002": {
                "inferred_type": "fe_page",
                "requirement_ids": ["WA-AUTH-002"],
                "user_story_ids": ["US-002"],
                "screen_ids": ["SCREEN-001"],
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-002", "2FA Frontend", type="development")
        enricher._enrich_task(task)

        # Should get fe_page enrichments despite type="development"
        assert task.enrichment_context is not None
        assert task.enrichment_context.get("inferred_type") == "fe_page"
        # Screen spec should be found via mapping
        assert "screen_spec" in task.enrichment_context
        assert task.enrichment_context["screen_spec"]["id"] == "SCREEN-001"

    def test_inferred_type_enables_test_enrichment(self, project_dir):
        """Task with type="testing" gets test enrichment via inferred_type."""
        mapping = self._make_mapping({
            "TASK-006": {
                "inferred_type": "test_e2e_happy",
                "requirement_ids": ["WA-AUTH-001"],
                "user_story_ids": ["US-001"],
                "feature_files": ["us_001.feature"],
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-006", "Security & Auth Testing", type="testing")
        enricher._enrich_task(task)

        assert task.enrichment_context is not None
        # Gherkin scenarios should be found via mapping feature_files
        assert "test_scenarios" in task.enrichment_context
        assert "Phone Registration" in task.enrichment_context["test_scenarios"]

    def test_inferred_type_enables_schema_enrichment(self, project_dir):
        """Task with inferred_type schema_model gets DTO enrichment."""
        mapping = self._make_mapping({
            "TASK-001": {
                "inferred_type": "schema_model",
                "requirement_ids": ["WA-AUTH-001"],
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-001", "Backend Database Schema", type="development")
        enricher._enrich_task(task)

        # Should get diagrams via requirement linkage
        assert task.enrichment_context is not None
        assert "diagrams" in task.enrichment_context

    def test_mapping_component_ids_for_fe_component(self, project_dir):
        """LLM-mapped component IDs are used to find component specs."""
        mapping = self._make_mapping({
            "TASK-X": {
                "inferred_type": "fe_component",
                "component_ids": ["COMP-003"],
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-X", "OTP Input Component", type="development")
        enricher._enrich_task(task)

        assert "component_spec" in task.enrichment_context
        assert task.enrichment_context["component_spec"]["id"] == "COMP-003"
        assert task.enrichment_context["component_spec"]["name"] == "OTPInput"

    def test_design_tokens_via_inferred_type(self, project_dir):
        """fe_* inferred type triggers design token injection."""
        mapping = self._make_mapping({
            "TASK-002": {
                "inferred_type": "fe_page",
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-002", "2FA Page", type="development")
        enricher._enrich_task(task)

        assert "design_tokens" in task.enrichment_context
        assert "primary" in task.enrichment_context["design_tokens"]["colors"]

    def test_accessibility_via_inferred_type(self, project_dir):
        """fe_* inferred type triggers accessibility rules injection."""
        mapping = self._make_mapping({
            "TASK-002": {
                "inferred_type": "fe_component",
            }
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask("TASK-002", "Button Component", type="development")
        enricher._enrich_task(task)

        assert "accessibility_rules" in task.enrichment_context

    def test_no_mapping_falls_back_to_regex(self, project_dir):
        """Without mapping, enricher uses original regex-based inference."""
        enricher = TaskEnricher(project_dir, task_mapping=None)
        task = FakeTask(
            "EPIC-001-SCHEMA-User-model",
            "Create User Prisma model",
            type="schema_model",
        )
        enricher._enrich_task(task)

        # Regex should match "User" entity -> WA-AUTH-001
        assert "WA-AUTH-001" in task.related_requirements

    def test_mapping_for_unknown_task_falls_back(self, project_dir):
        """Task not in mapping dict falls back to regex."""
        mapping = self._make_mapping({
            "TASK-999": {"inferred_type": "api_controller"},
        })
        enricher = TaskEnricher(project_dir, task_mapping=mapping)
        task = FakeTask(
            "EPIC-001-SCHEMA-User-model",
            "Create User model",
            type="schema_model",
        )
        enricher._enrich_task(task)

        # TASK-999 is in mapping but this task is not -> falls back
        assert "WA-AUTH-001" in task.related_requirements


class TestGherkinFeatureFiles:
    """Tests for reading individual .feature files (Phase 30)."""

    def test_gherkin_index_from_feature_files(self, project_dir):
        """Gherkin index built from individual us_*.feature files."""
        enricher = TaskEnricher(project_dir)
        assert "US-001" in enricher._us_to_gherkin
        assert "US-002" in enricher._us_to_gherkin
        assert "Phone Registration" in enricher._us_to_gherkin["US-001"]

    def test_gherkin_via_mapping_feature_files(self, project_dir):
        """Feature files from mapping are read directly."""
        mapping_result = TaskMappingResult(llm_used=True)
        mapping_result.mappings["TASK-006"] = TaskMapping(
            task_id="TASK-006",
            inferred_type="test_e2e_happy",
            feature_files=["us_002.feature"],
        )
        enricher = TaskEnricher(project_dir, task_mapping=mapping_result)
        task = FakeTask("TASK-006", "Test 2FA", type="testing")
        enricher._enrich_task(task)

        assert "test_scenarios" in task.enrichment_context
        assert "Two-Factor" in task.enrichment_context["test_scenarios"]

    def test_gherkin_via_mapping_user_story_id(self, project_dir):
        """Feature files resolved from user story ID when no feature_files in mapping."""
        mapping_result = TaskMappingResult(llm_used=True)
        mapping_result.mappings["TASK-006"] = TaskMapping(
            task_id="TASK-006",
            inferred_type="test_unit",
            user_story_ids=["US-001"],
            feature_files=[],  # empty -> will try US-ID based lookup
        )
        enricher = TaskEnricher(project_dir, task_mapping=mapping_result)
        task = FakeTask("TASK-006", "Test registration", type="testing")
        # Give it user stories from mapping
        task.related_user_stories = ["US-001"]
        enricher._enrich_task(task)

        # Should find via _us_to_gherkin index (built from feature files)
        assert "test_scenarios" in task.enrichment_context


class TestUserStoryNewFormat:
    """Tests for the new user_stories.json format with linked_requirement_ids."""

    def test_linked_requirement_ids_array(self, project_dir):
        """New format: linked_requirement_ids array is parsed."""
        enricher = TaskEnricher(project_dir)
        assert "WA-AUTH-001" in enricher._req_to_user_stories
        assert "WA-AUTH-002" in enricher._req_to_user_stories

    def test_persona_action_benefit_fields(self, project_dir):
        """New BDD fields (persona/action/benefit) mapped to as_a/i_want/so_that."""
        enricher = TaskEnricher(project_dir)
        stories = enricher._req_to_user_stories.get("WA-AUTH-001", [])
        assert len(stories) > 0
        story = stories[0]
        assert story["as_a"] == "new user"  # mapped from persona
        assert story["i_want"] == "register with phone number"  # mapped from action
        assert story["so_that"] == "access the platform"  # mapped from benefit

    def test_nested_user_stories_format(self, project_dir):
        """Handles {"user_stories": [...]} wrapper."""
        enricher = TaskEnricher(project_dir)
        total_stories = sum(len(v) for v in enricher._req_to_user_stories.values())
        assert total_stories == 2  # US-001 and US-002


class TestEnrichAllWithMapping:
    """End-to-end tests for enrich_all with LLM mapping."""

    def test_full_pipeline_with_mapping(self, project_dir):
        """Full enrichment with mapping produces complete context."""
        mapping_result = TaskMappingResult(llm_used=True)
        mapping_result.mappings["TASK-001"] = TaskMapping(
            task_id="TASK-001",
            inferred_type="api_controller",
            requirement_ids=["WA-AUTH-001"],
            user_story_ids=["US-001"],
        )
        mapping_result.mappings["TASK-002"] = TaskMapping(
            task_id="TASK-002",
            inferred_type="fe_page",
            requirement_ids=["WA-AUTH-002"],
            user_story_ids=["US-002"],
            screen_ids=["SCREEN-001"],
        )

        enricher = TaskEnricher(project_dir, task_mapping=mapping_result)
        tasks = FakeTaskList([
            FakeTask("TASK-001", "Backend Auth", type="development"),
            FakeTask("TASK-002", "2FA Frontend", type="development"),
        ])
        enricher.enrich_all(tasks)

        # TASK-001: api_controller gets diagrams + warnings
        t1 = tasks.tasks[0]
        assert "WA-AUTH-001" in t1.related_requirements
        assert "US-001" in t1.related_user_stories
        assert t1.enrichment_context.get("diagrams") is not None

        # TASK-002: fe_page gets screen spec + design tokens + accessibility
        t2 = tasks.tasks[1]
        assert "WA-AUTH-002" in t2.related_requirements
        assert "US-002" in t2.related_user_stories
        assert "screen_spec" in t2.enrichment_context
        assert "design_tokens" in t2.enrichment_context
        assert "accessibility_rules" in t2.enrichment_context

    def test_stats_tracking_with_mapping(self, project_dir):
        """Stats correctly track mapping-enriched tasks."""
        mapping_result = TaskMappingResult(llm_used=True)
        mapping_result.mappings["T-1"] = TaskMapping(
            task_id="T-1",
            inferred_type="fe_page",
            requirement_ids=["WA-AUTH-002"],
            user_story_ids=["US-002"],
            screen_ids=["SCREEN-001"],
        )

        enricher = TaskEnricher(project_dir, task_mapping=mapping_result)
        tasks = FakeTaskList([FakeTask("T-1", "2FA Page", type="development")])
        enricher.enrich_all(tasks)

        assert enricher.stats.tasks_with_requirements == 1
        assert enricher.stats.tasks_with_user_stories == 1
        assert enricher.stats.tasks_with_screen_specs == 1
        assert enricher.stats.tasks_with_design_tokens == 1
        assert enricher.stats.tasks_with_accessibility == 1
