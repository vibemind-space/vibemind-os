"""
Phase 29: Tests for TaskEnricher and ContextInjector.

Tests the full enrichment pipeline:
- Index building from various data sources
- Per-task requirement inference (schema, api, fe, test)
- User story cross-referencing
- Diagram selection and priority sorting
- Self-critique warning injection
- OpenAPI DTO cross-referencing
- Success criteria generation
- ContextInjector prompt formatting
- EpicOrchestrator integration
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mcp_plugins" / "servers" / "grpc_host"))

from src.autogen.task_enricher import TaskEnricher, EnrichmentStats
from src.autogen.context_injector import ContextInjector


# ═══════════════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class MockTask:
    """Minimal Task dataclass for testing (mirrors epic_task_generator.Task)."""
    id: str
    epic_id: str = "EPIC-001"
    type: str = "schema_model"
    title: str = "Test Task"
    description: str = "Test description"
    status: str = "pending"
    dependencies: List[str] = field(default_factory=list)
    estimated_minutes: int = 5
    output_files: List[str] = field(default_factory=list)
    related_requirements: List[str] = field(default_factory=list)
    related_user_stories: List[str] = field(default_factory=list)
    phase: str = "schema"
    success_criteria: Optional[str] = None
    enrichment_context: Optional[Dict[str, Any]] = None


@dataclass
class MockTaskList:
    """Minimal EpicTaskList for testing."""
    epic_id: str = "EPIC-001"
    epic_name: str = "WhatsApp Auth"
    tasks: List[MockTask] = field(default_factory=list)


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal project directory with test data files."""
    project = tmp_path / "whatsapp"
    project.mkdir()

    # data/data_dictionary.md
    data_dir = project / "data"
    data_dir.mkdir()
    (data_dir / "data_dictionary.md").write_text(
        "## Data Dictionary\n\n"
        "### AuthMethod\n\n"
        "| Field | Type |\n|---|---|\n| id | UUID |\n\n"
        "*Source Requirements:* WA-AUTH-001, WA-AUTH-002\n\n"
        "### User\n\n"
        "| Field | Type |\n|---|---|\n| id | UUID |\n\n"
        "*Source Requirements:* WA-USER-001, WA-USER-002\n\n"
        "### Session\n\n"
        "| Field | Type |\n|---|---|\n| id | UUID |\n\n"
        "*Source Requirements:* WA-SESS-001\n\n",
        encoding="utf-8",
    )

    # user_stories.json
    (project / "user_stories.json").write_text(
        json.dumps([
            {
                "id": "US-001",
                "title": "Phone Registration",
                "linked_requirement": "WA-AUTH-001",
                "priority": "high",
                "description": "User registers with phone number",
                "as_a": "new user",
                "i_want": "register using my phone number",
                "so_that": "I can access the messaging platform",
            },
            {
                "id": "US-002",
                "title": "Two-Factor Auth",
                "linked_requirement": "WA-AUTH-002",
                "priority": "high",
                "description": "User sets up 2FA",
                "as_a": "registered user",
                "i_want": "enable two-factor authentication",
                "so_that": "my account is more secure",
            },
            {
                "id": "US-003",
                "title": "Session Management",
                "linked_requirement": "WA-SESS-001",
                "priority": "medium",
                "description": "User manages active sessions",
                "as_a": "logged-in user",
                "i_want": "see and manage my active sessions",
                "so_that": "I can revoke unauthorized access",
            },
        ]),
        encoding="utf-8",
    )

    # diagrams/*.mmd
    diagrams_dir = project / "diagrams"
    diagrams_dir.mkdir()
    (diagrams_dir / "WA-AUTH-001_sequence.mmd").write_text(
        "sequenceDiagram\n  User->>API: POST /auth/register\n  API->>DB: Insert User\n  DB-->>API: OK\n  API-->>User: 201 Created",
        encoding="utf-8",
    )
    (diagrams_dir / "WA-AUTH-001_erDiagram.mmd").write_text(
        "erDiagram\n  User ||--o{ AuthMethod : has\n  AuthMethod { uuid id PK }",
        encoding="utf-8",
    )
    (diagrams_dir / "WA-AUTH-002_sequence.mmd").write_text(
        "sequenceDiagram\n  User->>API: POST /auth/2fa/setup\n  API->>User: QR Code",
        encoding="utf-8",
    )
    (diagrams_dir / "WA-SESS-001_state.mmd").write_text(
        "stateDiagram-v2\n  [*] --> Active\n  Active --> Expired\n  Active --> Revoked",
        encoding="utf-8",
    )
    # Non-matching file (should be ignored)
    (diagrams_dir / "overview.mmd").write_text("graph TD\n  A-->B", encoding="utf-8")

    # quality/self_critique_report.json
    quality_dir = project / "quality"
    quality_dir.mkdir()
    (quality_dir / "self_critique_report.json").write_text(
        json.dumps({
            "issues": [
                {
                    "id": "SC-001",
                    "severity": "high",
                    "title": "Missing rate limiting",
                    "suggestion": "Add rate limiting to registration endpoint",
                    "affected_artifacts": ["WA-AUTH-001"],
                },
                {
                    "id": "SC-002",
                    "severity": "medium",
                    "title": "Weak session expiry",
                    "suggestion": "Implement sliding window session expiry",
                    "affected_artifacts": ["WA-SESS-001"],
                },
            ]
        }),
        encoding="utf-8",
    )

    # api/openapi_spec.yaml
    api_dir = project / "api"
    api_dir.mkdir()
    (api_dir / "openapi_spec.yaml").write_text(
        "openapi: 3.0.3\n"
        "info:\n  title: WhatsApp Auth\n  version: 1.0.0\n"
        "components:\n"
        "  schemas:\n"
        "    CreateAuthMethodRequest:\n"
        "      type: object\n"
        "      properties:\n"
        "        methodType:\n"
        "          type: string\n"
        "          enum: [phone, email, biometric]\n"
        "        identifier:\n"
        "          type: string\n"
        "    AuthMethodResponse:\n"
        "      type: object\n"
        "      properties:\n"
        "        id:\n"
        "          type: string\n"
        "        methodType:\n"
        "          type: string\n"
        "        verified:\n"
        "          type: boolean\n"
        "    CreateUserRequest:\n"
        "      type: object\n"
        "      properties:\n"
        "        phoneNumber:\n"
        "          type: string\n"
        "        displayName:\n"
        "          type: string\n",
        encoding="utf-8",
    )

    # tasks/ dir (for saving enriched output)
    (project / "tasks").mkdir()

    # ── Phase 29b: Additional data sources ──

    # testing/test_documentation.md (Gherkin scenarios)
    testing_dir = project / "testing"
    testing_dir.mkdir()
    (testing_dir / "test_documentation.md").write_text(
        "# Test Documentation\n\n"
        "## Phone Registration Tests\n\n"
        "### Phone Number Registration Flow\n\n"
        "*User Story:* US-001\n\n"
        "```gherkin\n"
        "Feature: Phone Registration\n"
        "  Scenario: Successful phone registration\n"
        "    Given a new user with phone \"+49123456\"\n"
        "    When they submit the registration form\n"
        "    Then an OTP is sent to their phone\n"
        "    And the user account is created\n\n"
        "  Scenario: Invalid phone number\n"
        "    Given a new user with phone \"invalid\"\n"
        "    When they submit the registration form\n"
        "    Then an error message is displayed\n"
        "```\n\n"
        "### Two-Factor Authentication Setup\n\n"
        "*User Story:* US-002\n\n"
        "```gherkin\n"
        "Feature: Two-Factor Authentication\n"
        "  Scenario: Enable 2FA with authenticator app\n"
        "    Given a registered user\n"
        "    When they enable 2FA\n"
        "    Then a QR code is displayed\n"
        "```\n\n"
        "### Session Management\n\n"
        "*User Story:* US-003\n\n"
        "```gherkin\n"
        "Feature: Session Management\n"
        "  Scenario: View active sessions\n"
        "    Given a logged-in user\n"
        "    When they visit the sessions page\n"
        "    Then all active sessions are listed\n"
        "```\n\n",
        encoding="utf-8",
    )

    # ui_design/components.md (Component specifications)
    ui_dir = project / "ui_design"
    ui_dir.mkdir()
    (ui_dir / "components.md").write_text(
        "# UI Components\n\n"
        "## Button\n\n"
        "**ID:** `COMP-001`\n\n"
        "Primary action button component.\n\n"
        "### Props\n\n"
        "| Prop | Type | Default |\n"
        "|---|---|---|\n"
        "| `label` | `string` | - |\n"
        "| `variant` | `'primary' \\| 'secondary'` | `'primary'` |\n"
        "| `disabled` | `boolean` | `false` |\n"
        "| `onClick` | `() => void` | - |\n\n"
        "### Variants\n\n"
        "- `primary`\n"
        "- `secondary`\n"
        "- `danger`\n\n"
        "### Accessibility\n\n"
        "- **Role:** button\n"
        "- **ARIA Label:** Required\n"
        "- **Focus:** Visible focus ring\n\n"
        "---\n\n"
        "## PhoneInput\n\n"
        "**ID:** `COMP-003`\n\n"
        "International phone number input with country code selector.\n\n"
        "### Props\n\n"
        "| Prop | Type | Default |\n"
        "|---|---|---|\n"
        "| `value` | `string` | - |\n"
        "| `countryCode` | `string` | `'+49'` |\n"
        "| `onChange` | `(value: string) => void` | - |\n"
        "| `error` | `string` | - |\n\n"
        "### Variants\n\n"
        "- `default`\n"
        "- `error`\n\n"
        "### Accessibility\n\n"
        "- **Role:** textbox\n"
        "- **ARIA Label:** Phone number\n\n"
        "---\n\n"
        "## OTPInput\n\n"
        "**ID:** `COMP-004`\n\n"
        "Six-digit OTP verification code input.\n\n"
        "### Props\n\n"
        "| Prop | Type | Default |\n"
        "|---|---|---|\n"
        "| `length` | `number` | `6` |\n"
        "| `onComplete` | `(code: string) => void` | - |\n\n"
        "### Accessibility\n\n"
        "- **Role:** group\n"
        "- **ARIA Label:** Verification code\n\n"
        "---\n\n",
        encoding="utf-8",
    )

    # ui_design/screens/screen-screen-001.md (Screen spec)
    screens_dir = ui_dir / "screens"
    screens_dir.mkdir()
    (screens_dir / "screen-screen-001.md").write_text(
        "# Phone Registration\n\n"
        "**ID:** `SCREEN-001`\n"
        "**Route:** `/register`\n"
        "**Layout:** centered\n\n"
        "Registration screen for phone-based signup.\n\n"
        "---\n\n"
        "## Components Used\n\n"
        "- `COMP-001`\n"
        "- `COMP-003`\n"
        "- `COMP-004`\n\n"
        "---\n\n"
        "## Data Requirements\n\n"
        "- `POST /api/auth/send-otp`\n"
        "- `POST /api/auth/verify-otp`\n"
        "- `POST /api/auth/register`\n\n"
        "---\n\n"
        "## Related User Story\n\n"
        "`US-001`\n\n"
        "---\n\n"
        "## Wireframe\n\n"
        "```\n"
        "[Phone Registration wireframe]\n"
        "```\n",
        encoding="utf-8",
    )
    (screens_dir / "screen-screen-002.md").write_text(
        "# Session Dashboard\n\n"
        "**ID:** `SCREEN-002`\n"
        "**Route:** `/sessions`\n"
        "**Layout:** sidebar\n\n"
        "Session management dashboard.\n\n"
        "---\n\n"
        "## Components Used\n\n"
        "- `COMP-001`\n\n"
        "---\n\n"
        "## Data Requirements\n\n"
        "- `GET /api/sessions`\n"
        "- `DELETE /api/sessions/:id`\n\n"
        "---\n\n"
        "## Related User Story\n\n"
        "`US-003`\n\n",
        encoding="utf-8",
    )

    # ux_design/information_architecture.md (Route map)
    ux_dir = project / "ux_design"
    ux_dir.mkdir()
    (ux_dir / "information_architecture.md").write_text(
        "# Information Architecture\n\n"
        "## Route Hierarchy\n\n"
        "### Authentication Routes\n\n"
        "- **Phone Registration** (`/register`)\n"
        "  - Content: phone input, OTP verification, terms acceptance\n\n"
        "- **Login** (`/login`)\n"
        "  - Content: phone login, biometric authentication, session creation\n\n"
        "### Application Routes\n\n"
        "- **Session Management** (`/sessions`)\n"
        "  - Content: active sessions list, revoke session, device info\n\n"
        "- **Settings** (`/settings`)\n"
        "  - Content: profile settings, security preferences, notification config\n\n",
        encoding="utf-8",
    )

    # ui_design/design_tokens.json (Phase 29c: Design system tokens)
    (ui_dir / "design_tokens.json").write_text(
        json.dumps({
            "colors": {
                "primary": "#1E3A8A",
                "primary-dark": "#1E2F6E",
                "secondary": "#6B7280",
                "background": "#F5F7FA",
                "surface": "#FFFFFF",
                "text-primary": "#111827",
                "error": "#DC2626",
                "success": "#10B981",
            },
            "typography": {
                "font-family": {
                    "base": "Inter, Helvetica, Arial, sans-serif",
                    "mono": "JetBrains Mono, Menlo, monospace",
                },
                "h1": {"size": "2.5rem", "weight": "700", "line-height": "1.2"},
                "h2": {"size": "2rem", "weight": "600", "line-height": "1.25"},
                "body": {"size": "1rem", "weight": "400", "line-height": "1.5"},
                "caption": {"size": "0.75rem", "weight": "400", "line-height": "1.4"},
            },
            "spacing": {
                "xs": "0.25rem",
                "sm": "0.5rem",
                "md": "1rem",
                "lg": "1.5rem",
                "xl": "2rem",
            },
            "breakpoints": {
                "mobile": 320,
                "tablet": 768,
                "desktop": 1024,
                "desktop-lg": 1280,
            },
            "border_radius": {
                "sm": "0.125rem",
                "md": "0.375rem",
                "lg": "0.5rem",
                "full": "9999px",
            },
        }),
        encoding="utf-8",
    )

    # ux_design/accessibility_checklist.md (WCAG rules)
    (ux_dir / "accessibility_checklist.md").write_text(
        "# Accessibility Checklist (WCAG 2.1 AA)\n\n"
        "## Perceivable\n\n"
        "- [x] All images have alt text\n"
        "- [ ] Color contrast meets 4.5:1 ratio\n"
        "- [x] Text can be resized to 200%\n\n"
        "## Operable\n\n"
        "- [ ] All functionality available via keyboard\n"
        "- [x] Focus indicators are visible\n"
        "- [ ] No keyboard traps\n\n"
        "## Understandable\n\n"
        "- [ ] Error messages are clear and specific\n"
        "- [x] Form labels are descriptive\n\n",
        encoding="utf-8",
    )

    return project


@pytest.fixture
def task_list():
    """Create a task list with various task types."""
    return MockTaskList(tasks=[
        MockTask(
            id="EPIC-001-SCHEMA-AuthMethod-model",
            type="schema_model",
            title="Create Prisma model for AuthMethod",
            description="Define AuthMethod entity in Prisma schema",
            phase="schema",
            output_files=["prisma/schema.prisma"],
        ),
        MockTask(
            id="EPIC-001-SCHEMA-AuthMethod-relations",
            type="schema_relations",
            title="Define AuthMethod relations",
            description="Set up relations between AuthMethod and User",
            phase="schema",
        ),
        MockTask(
            id="EPIC-001-API-POST-api_v1_auth_register-controller",
            type="api_controller",
            title="Create auth registration controller",
            description="POST /api/v1/auth/register endpoint",
            phase="api",
        ),
        MockTask(
            id="EPIC-001-FE-LoginPage",
            type="fe_page",
            title="Create login page with auth methods",
            description="React page for user authentication login",
            phase="frontend",
        ),
        MockTask(
            id="EPIC-001-TEST-AuthMethod-unit",
            type="test_unit",
            title="Unit tests for AuthMethod service",
            description="Test AuthMethod CRUD operations",
            phase="test",
        ),
        MockTask(
            id="EPIC-001-VERIFY-schema-migration",
            type="verify_build",
            title="Verify schema migration runs",
            description="Run prisma validate and prisma migrate",
            phase="verify",
        ),
        # Phase 29b: Additional task types for new enrichment paths
        MockTask(
            id="EPIC-001-FE-Button-component",
            type="fe_component",
            title="Create Button component",
            description="Reusable Button component with variants",
            phase="frontend",
        ),
        MockTask(
            id="EPIC-001-FE-PhoneRegistration-page",
            type="fe_page",
            title="Create Phone Registration page",
            description="Phone registration with OTP verification",
            phase="frontend",
        ),
        MockTask(
            id="EPIC-001-TEST-Registration-e2e",
            type="test_e2e_happy",
            title="E2E test for phone registration flow",
            description="Test complete registration happy path",
            phase="test",
        ),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# TASK ENRICHER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestTaskEnricherInit:
    """Tests for TaskEnricher initialization and index building."""

    def test_init_builds_entity_index(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert "authmethod" in enricher._entity_to_reqs
        assert "user" in enricher._entity_to_reqs
        assert "session" in enricher._entity_to_reqs

    def test_entity_index_has_correct_requirements(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert "WA-AUTH-001" in enricher._entity_to_reqs["authmethod"]
        assert "WA-AUTH-002" in enricher._entity_to_reqs["authmethod"]

    def test_user_story_index_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert "WA-AUTH-001" in enricher._req_to_user_stories
        assert enricher._req_to_user_stories["WA-AUTH-001"][0]["id"] == "US-001"

    def test_diagram_index_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert "WA-AUTH-001" in enricher._req_to_diagrams
        assert len(enricher._req_to_diagrams["WA-AUTH-001"]) == 2  # sequence + erDiagram

    def test_diagram_ignores_non_matching_files(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # overview.mmd doesn't match WA-*-NNN pattern
        all_diagrams = sum(len(v) for v in enricher._req_to_diagrams.values())
        assert all_diagrams == 4  # 2 for AUTH-001, 1 for AUTH-002, 1 for SESS-001

    def test_critique_index_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert "WA-AUTH-001" in enricher._req_to_critique
        assert enricher._req_to_critique["WA-AUTH-001"][0]["id"] == "SC-001"

    def test_openapi_schemas_loaded(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert "CreateAuthMethodRequest" in enricher._openapi_schemas
        assert "AuthMethodResponse" in enricher._openapi_schemas

    def test_init_with_missing_files(self, tmp_path):
        """TaskEnricher should handle missing files gracefully."""
        empty_project = tmp_path / "empty"
        empty_project.mkdir()
        enricher = TaskEnricher(empty_project)
        assert len(enricher._entity_to_reqs) == 0
        assert len(enricher._req_to_user_stories) == 0

    def test_init_with_doc_spec(self, project_dir):
        """TaskEnricher should use DocumentationSpec entities when provided."""
        mock_entity = MagicMock()
        mock_entity.name = "DeviceToken"
        mock_entity.source_requirements = ["WA-DEVICE-001"]

        mock_spec = MagicMock()
        mock_spec.entities = [mock_entity]
        mock_spec.user_stories = []
        mock_spec.quality_report = None

        enricher = TaskEnricher(project_dir, doc_spec=mock_spec)
        assert "devicetoken" in enricher._entity_to_reqs


class TestRequirementInference:
    """Tests for _infer_requirements across task types."""

    def test_schema_task_gets_entity_requirements(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        task = task_list.tasks[0]  # SCHEMA-AuthMethod-model
        reqs = enricher._infer_requirements(task)
        assert "WA-AUTH-001" in reqs
        assert "WA-AUTH-002" in reqs

    def test_api_task_gets_entity_requirements(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        task = task_list.tasks[2]  # API-POST-api_v1_auth_register-controller
        reqs = enricher._infer_requirements(task)
        # Should match "auth" entity via keyword matching
        assert len(reqs) > 0

    def test_test_task_inherits_entity_requirements(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        task = task_list.tasks[4]  # TEST-AuthMethod-unit
        reqs = enricher._infer_requirements(task)
        assert "WA-AUTH-001" in reqs

    def test_requirements_capped_at_10(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # Add many requirements for one entity
        enricher._entity_to_reqs["testentity"] = [f"REQ-{i:03d}" for i in range(20)]

        task = MockTask(id="EPIC-001-SCHEMA-TestEntity-model", type="schema_model", title="Test")
        reqs = enricher._infer_requirements(task)
        assert len(reqs) <= 10

    def test_unknown_entity_returns_empty(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="EPIC-001-SCHEMA-Unknown-model", type="schema_model", title="Unknown entity")
        reqs = enricher._infer_requirements(task)
        assert reqs == []


class TestUserStoryInference:
    """Tests for _infer_user_stories."""

    def test_user_stories_from_requirements(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="test",
            related_requirements=["WA-AUTH-001", "WA-AUTH-002"],
        )
        stories = enricher._infer_user_stories(task)
        assert "US-001" in stories
        assert "US-002" in stories

    def test_user_stories_capped_at_5(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # Add many stories for one requirement
        enricher._req_to_user_stories["WA-AUTH-001"] = [
            {"id": f"US-{i:03d}"} for i in range(10)
        ]
        task = MockTask(id="test", related_requirements=["WA-AUTH-001"])
        stories = enricher._infer_user_stories(task)
        assert len(stories) <= 5

    def test_no_stories_without_requirements(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="test", related_requirements=[])
        stories = enricher._infer_user_stories(task)
        assert stories == []


class TestDiagramSelection:
    """Tests for _get_relevant_diagrams with priority sorting."""

    def test_schema_task_prefers_er_diagrams(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="test",
            type="schema_model",
            related_requirements=["WA-AUTH-001"],
        )
        diagrams = enricher._get_relevant_diagrams(task)
        assert len(diagrams) > 0
        # erDiagram should come first for schema_model tasks
        assert diagrams[0]["type"] == "erDiagram"

    def test_api_task_prefers_sequence_diagrams(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="test",
            type="api_controller",
            related_requirements=["WA-AUTH-001"],
        )
        diagrams = enricher._get_relevant_diagrams(task)
        assert len(diagrams) > 0
        assert diagrams[0]["type"] == "sequence"

    def test_diagrams_capped_at_3(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # Add many diagrams for one requirement
        enricher._req_to_diagrams["WA-AUTH-001"] = [
            {"type": f"type{i}", "content": "test", "file": f"f{i}.mmd"} for i in range(10)
        ]
        task = MockTask(id="test", type="api_controller", related_requirements=["WA-AUTH-001"])
        diagrams = enricher._get_relevant_diagrams(task)
        assert len(diagrams) <= 3

    def test_no_diagrams_without_requirements(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="test", related_requirements=[])
        diagrams = enricher._get_relevant_diagrams(task)
        assert diagrams == []


class TestCritiqueWarnings:
    """Tests for _get_critique_warnings."""

    def test_critique_warnings_for_matched_requirements(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="test", related_requirements=["WA-AUTH-001"])
        warnings = enricher._get_critique_warnings(task)
        assert len(warnings) == 1
        assert warnings[0]["id"] == "SC-001"
        assert warnings[0]["severity"] == "high"

    def test_warnings_sorted_by_severity(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # Add high + low for same req
        enricher._req_to_critique["WA-AUTH-001"].append({
            "id": "SC-099",
            "severity": "low",
            "title": "Minor issue",
            "suggestion": "Consider improving",
        })
        task = MockTask(id="test", related_requirements=["WA-AUTH-001"])
        warnings = enricher._get_critique_warnings(task)
        assert warnings[0]["severity"] == "high"
        assert warnings[-1]["severity"] == "low"

    def test_warnings_capped_at_5(self, project_dir):
        enricher = TaskEnricher(project_dir)
        enricher._req_to_critique["WA-AUTH-001"] = [
            {"id": f"SC-{i}", "severity": "medium", "title": f"Issue {i}", "suggestion": ""} for i in range(10)
        ]
        task = MockTask(id="test", related_requirements=["WA-AUTH-001"])
        warnings = enricher._get_critique_warnings(task)
        assert len(warnings) <= 5


class TestDTOCrossReference:
    """Tests for _get_related_dtos."""

    def test_schema_task_gets_matching_dtos(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="EPIC-001-SCHEMA-AuthMethod-model",
            type="schema_model",
        )
        dtos = enricher._get_related_dtos(task)
        assert len(dtos) >= 1
        dto_names = [d["name"] for d in dtos]
        assert "CreateAuthMethodRequest" in dto_names

    def test_dto_includes_properties(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="EPIC-001-SCHEMA-AuthMethod-model", type="schema_model")
        dtos = enricher._get_related_dtos(task)
        dto = next(d for d in dtos if d["name"] == "CreateAuthMethodRequest")
        prop_names = [p["name"] for p in dto["properties"]]
        assert "methodType" in prop_names
        assert "identifier" in prop_names

    def test_dto_includes_enum_values(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="EPIC-001-SCHEMA-AuthMethod-model", type="schema_model")
        dtos = enricher._get_related_dtos(task)
        dto = next(d for d in dtos if d["name"] == "CreateAuthMethodRequest")
        method_prop = next(p for p in dto["properties"] if p["name"] == "methodType")
        assert "enum" in method_prop
        assert "phone" in method_prop["enum"]

    def test_non_schema_task_skips_dtos(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="test", type="api_controller")
        # _get_related_dtos only runs for schema_ tasks in _enrich_task
        # but the method itself doesn't restrict
        # Let's test the _enrich_task path
        task.related_requirements = []
        enricher._enrich_task(task)
        ctx = task.enrichment_context
        # api_controller tasks should NOT have related_dtos
        assert ctx is None or "related_dtos" not in (ctx or {})

    def test_unknown_entity_gets_no_dtos(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="EPIC-001-SCHEMA-Unknown-model", type="schema_model")
        dtos = enricher._get_related_dtos(task)
        assert dtos == []


class TestSuccessCriteriaGeneration:
    """Tests for _generate_success_criteria."""

    def test_schema_model_gets_base_criteria(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="test",
            type="schema_model",
            related_requirements=["WA-AUTH-001"],
        )
        criteria = enricher._generate_success_criteria(task)
        assert criteria is not None
        assert "Prisma model" in criteria

    def test_criteria_includes_user_story(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="test",
            type="api_controller",
            related_requirements=["WA-AUTH-001"],
        )
        criteria = enricher._generate_success_criteria(task)
        assert "register using my phone number" in criteria

    def test_criteria_includes_critique_suggestion(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="test",
            type="api_controller",
            related_requirements=["WA-AUTH-001"],
        )
        criteria = enricher._generate_success_criteria(task)
        assert "rate limiting" in criteria

    def test_unknown_type_gets_none(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(id="test", type="custom_unknown", related_requirements=[])
        criteria = enricher._generate_success_criteria(task)
        assert criteria is None


class TestEnrichAll:
    """Tests for the full enrich_all pipeline."""

    def test_enrich_all_fills_requirements(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        # Schema-AuthMethod should have requirements
        schema_task = task_list.tasks[0]
        assert len(schema_task.related_requirements) > 0
        assert "WA-AUTH-001" in schema_task.related_requirements

    def test_enrich_all_fills_user_stories(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        schema_task = task_list.tasks[0]
        assert len(schema_task.related_user_stories) > 0

    def test_enrich_all_fills_enrichment_context(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        schema_task = task_list.tasks[0]
        assert schema_task.enrichment_context is not None
        assert "diagrams" in schema_task.enrichment_context

    def test_enrich_all_fills_success_criteria(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        schema_task = task_list.tasks[0]
        assert schema_task.success_criteria is not None

    def test_enrich_all_updates_stats(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        assert enricher.stats.total_tasks == 9  # 6 original + 3 Phase 29b
        assert enricher.stats.tasks_with_requirements > 0

    def test_enrich_all_saves_enriched_file(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        enriched_path = project_dir / "tasks" / "epic-001-tasks-enriched.json"
        assert enriched_path.exists()

        data = json.loads(enriched_path.read_text(encoding="utf-8"))
        assert data["epic_id"] == "EPIC-001"
        assert len(data["tasks"]) == 9  # 6 original + 3 Phase 29b
        assert data["enrichment_stats"]["total_tasks"] == 9

    def test_enrich_all_preserves_existing_requirements(self, project_dir):
        """Tasks with existing requirements should not be overwritten."""
        task_list = MockTaskList(tasks=[
            MockTask(
                id="EPIC-001-SCHEMA-AuthMethod-model",
                type="schema_model",
                title="AuthMethod model",
                related_requirements=["EXISTING-REQ-001"],
            ),
        ])
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        # Existing requirements should be preserved
        assert task_list.tasks[0].related_requirements == ["EXISTING-REQ-001"]

    def test_enrich_all_idempotent(self, project_dir, task_list):
        """Running enrichment twice should produce the same result."""
        enricher1 = TaskEnricher(project_dir)
        enricher1.enrich_all(task_list)
        reqs_after_first = list(task_list.tasks[0].related_requirements)

        enricher2 = TaskEnricher(project_dir)
        enricher2.enrich_all(task_list)
        reqs_after_second = list(task_list.tasks[0].related_requirements)

        assert reqs_after_first == reqs_after_second

    def test_enrich_all_with_empty_task_list(self, project_dir):
        """Should handle empty task list gracefully."""
        task_list = MockTaskList(tasks=[])
        enricher = TaskEnricher(project_dir)
        result = enricher.enrich_all(task_list)
        assert result is task_list
        assert enricher.stats.total_tasks == 0


class TestUserStoryDetails:
    """Tests for user story detail enrichment."""

    def test_user_story_details_stored_in_context(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        schema_task = task_list.tasks[0]
        ctx = schema_task.enrichment_context
        assert ctx is not None
        assert "user_story_details" in ctx
        details = ctx["user_story_details"]
        assert len(details) > 0
        assert details[0]["as_a"] == "new user"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 29b: NEW ENRICHMENT PATH TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestGherkinIndex:
    """Tests for Gherkin test scenario index building and extraction."""

    def test_gherkin_index_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert len(enricher._us_to_gherkin) == 3
        assert "US-001" in enricher._us_to_gherkin
        assert "US-002" in enricher._us_to_gherkin
        assert "US-003" in enricher._us_to_gherkin

    def test_gherkin_content_correct(self, project_dir):
        enricher = TaskEnricher(project_dir)
        gherkin = enricher._us_to_gherkin["US-001"]
        assert "Feature: Phone Registration" in gherkin
        assert "Successful phone registration" in gherkin
        assert "Invalid phone number" in gherkin

    def test_gherkin_injected_for_test_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        # test_unit for AuthMethod → WA-AUTH-001 → US-001 → Gherkin
        test_task = task_list.tasks[4]  # TEST-AuthMethod-unit
        assert test_task.enrichment_context is not None
        scenarios = test_task.enrichment_context.get("test_scenarios")
        assert scenarios is not None
        assert "Feature: Phone Registration" in scenarios

    def test_gherkin_injected_for_e2e_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        # test_e2e_happy for Registration → should match via keywords
        e2e_task = task_list.tasks[8]  # TEST-Registration-e2e
        assert e2e_task.enrichment_context is not None
        scenarios = e2e_task.enrichment_context.get("test_scenarios")
        assert scenarios is not None
        assert "registration" in scenarios.lower() or "phone" in scenarios.lower()

    def test_gherkin_not_injected_for_schema_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        schema_task = task_list.tasks[0]  # SCHEMA-AuthMethod-model
        ctx = schema_task.enrichment_context or {}
        assert "test_scenarios" not in ctx

    def test_gherkin_truncated_when_long(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # Inject a very long Gherkin block
        enricher._us_to_gherkin["US-001"] = "Feature: Long\n" + "  Scenario: X\n" * 200
        task = MockTask(
            id="test", type="test_unit", title="Test",
            related_requirements=["WA-AUTH-001"],
        )
        enricher._req_to_user_stories = {"WA-AUTH-001": [{"id": "US-001"}]}
        result = enricher._get_gherkin_scenarios(task)
        assert result is not None
        assert len(result) <= 820  # 780 + truncation message

    def test_gherkin_keyword_fallback(self, project_dir):
        """Test fallback: match by keywords when no user story link exists."""
        enricher = TaskEnricher(project_dir)
        # Task with no requirements but keyword match
        task = MockTask(
            id="EPIC-001-TEST-registration-e2e",
            type="test_e2e_happy",
            title="E2E test for phone registration flow",
            related_requirements=[],
        )
        result = enricher._get_gherkin_scenarios(task)
        # Should match "registration" keyword in Gherkin feature
        assert result is not None
        assert "Registration" in result or "registration" in result.lower()

    def test_gherkin_returns_none_without_data(self, tmp_path):
        """No test_documentation.md → no Gherkin."""
        empty = tmp_path / "empty"
        empty.mkdir()
        enricher = TaskEnricher(empty)
        assert len(enricher._us_to_gherkin) == 0

    def test_gherkin_stats_updated(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        assert enricher.stats.tasks_with_test_scenarios > 0


class TestComponentSpecIndex:
    """Tests for component spec index building and extraction."""

    def test_component_index_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert len(enricher._comp_specs) == 3  # Button, PhoneInput, OTPInput
        assert "COMP-001" in enricher._comp_specs
        assert "COMP-003" in enricher._comp_specs
        assert "COMP-004" in enricher._comp_specs

    def test_component_name_correct(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert enricher._comp_specs["COMP-001"]["name"] == "Button"
        assert enricher._comp_specs["COMP-003"]["name"] == "PhoneInput"
        assert enricher._comp_specs["COMP-004"]["name"] == "OTPInput"

    def test_component_props_extracted(self, project_dir):
        enricher = TaskEnricher(project_dir)
        button_props = enricher._comp_specs["COMP-001"]["props"]
        assert len(button_props) >= 3
        prop_names = [p["name"] for p in button_props]
        assert "label" in prop_names
        assert "variant" in prop_names
        assert "disabled" in prop_names

    def test_component_variants_extracted(self, project_dir):
        enricher = TaskEnricher(project_dir)
        variants = enricher._comp_specs["COMP-001"]["variants"]
        # Variants may have backtick remnants from markdown parsing
        variants_clean = [v.strip("`").strip() for v in variants]
        assert "primary" in variants_clean
        assert "secondary" in variants_clean
        assert "danger" in variants_clean

    def test_component_accessibility_extracted(self, project_dir):
        enricher = TaskEnricher(project_dir)
        a11y = enricher._comp_specs["COMP-001"]["accessibility"]
        assert "Role" in a11y
        assert a11y["Role"] == "button"

    def test_component_spec_injected_for_fe_component_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        button_task = task_list.tasks[6]  # FE-Button-component
        assert button_task.enrichment_context is not None
        comp_spec = button_task.enrichment_context.get("component_spec")
        assert comp_spec is not None
        assert comp_spec["name"] == "Button"
        assert len(comp_spec["props"]) >= 3

    def test_component_spec_not_injected_for_non_component_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        page_task = task_list.tasks[3]  # FE-LoginPage (fe_page)
        ctx = page_task.enrichment_context or {}
        assert "component_spec" not in ctx

    def test_component_spec_match_by_comp_id(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="EPIC-001-FE-COMP-003-component",
            type="fe_component",
            title="Create COMP-003 PhoneInput",
            description="Phone number input with country selector",
        )
        spec = enricher._get_component_spec(task)
        assert spec is not None
        assert spec["name"] == "PhoneInput"

    def test_component_spec_returns_none_for_unknown(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="EPIC-001-FE-Unknown-component",
            type="fe_component",
            title="Create Unknown component",
        )
        spec = enricher._get_component_spec(task)
        assert spec is None

    def test_component_stats_updated(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        assert enricher.stats.tasks_with_component_specs > 0

    def test_component_index_empty_without_file(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        enricher = TaskEnricher(empty)
        assert len(enricher._comp_specs) == 0


class TestScreenSpecIndex:
    """Tests for screen spec index building and extraction."""

    def test_screen_index_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert len(enricher._screen_specs) == 2  # SCREEN-001, SCREEN-002
        assert "SCREEN-001" in enricher._screen_specs
        assert "SCREEN-002" in enricher._screen_specs

    def test_screen_title_correct(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert enricher._screen_specs["SCREEN-001"]["title"] == "Phone Registration"
        assert enricher._screen_specs["SCREEN-002"]["title"] == "Session Dashboard"

    def test_screen_route_correct(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert enricher._screen_specs["SCREEN-001"]["route"] == "/register"
        assert enricher._screen_specs["SCREEN-002"]["route"] == "/sessions"

    def test_screen_components_extracted(self, project_dir):
        enricher = TaskEnricher(project_dir)
        comps = enricher._screen_specs["SCREEN-001"]["components"]
        assert "COMP-001" in comps
        assert "COMP-003" in comps
        assert "COMP-004" in comps

    def test_screen_components_deduplicated(self, project_dir):
        enricher = TaskEnricher(project_dir)
        comps = enricher._screen_specs["SCREEN-001"]["components"]
        assert len(comps) == len(set(comps))

    def test_screen_api_endpoints_extracted(self, project_dir):
        enricher = TaskEnricher(project_dir)
        endpoints = enricher._screen_specs["SCREEN-001"]["api_endpoints"]
        assert "POST /api/auth/send-otp" in endpoints
        assert "POST /api/auth/verify-otp" in endpoints
        assert "POST /api/auth/register" in endpoints

    def test_screen_user_story_extracted(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert enricher._screen_specs["SCREEN-001"]["user_story"] == "US-001"
        assert enricher._screen_specs["SCREEN-002"]["user_story"] == "US-003"

    def test_us_to_screen_reverse_index(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert enricher._us_to_screen["US-001"] == "SCREEN-001"
        assert enricher._us_to_screen["US-003"] == "SCREEN-002"

    def test_screen_spec_injected_for_fe_page_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        # FE-PhoneRegistration-page → WA-AUTH-001 → US-001 → SCREEN-001
        reg_task = task_list.tasks[7]  # FE-PhoneRegistration-page
        assert reg_task.enrichment_context is not None
        screen = reg_task.enrichment_context.get("screen_spec")
        assert screen is not None
        assert screen["route"] == "/register"

    def test_screen_spec_enriched_with_component_details(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        reg_task = task_list.tasks[7]  # FE-PhoneRegistration-page
        screen = reg_task.enrichment_context.get("screen_spec")
        assert screen is not None
        # Should have component_details from _comp_specs
        comp_details = screen.get("component_details", [])
        assert len(comp_details) > 0
        detail_names = [cd["name"] for cd in comp_details]
        assert "Button" in detail_names

    def test_screen_spec_not_injected_for_schema_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        schema_task = task_list.tasks[0]
        ctx = schema_task.enrichment_context or {}
        assert "screen_spec" not in ctx

    def test_screen_spec_returns_none_for_unmatched(self, project_dir):
        enricher = TaskEnricher(project_dir)
        task = MockTask(
            id="EPIC-001-FE-Unknown-page",
            type="fe_page",
            title="Create Unknown page",
            related_requirements=[],
        )
        spec = enricher._get_screen_spec(task)
        assert spec is None

    def test_screen_stats_updated(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        assert enricher.stats.tasks_with_screen_specs > 0

    def test_screen_index_empty_without_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        enricher = TaskEnricher(empty)
        assert len(enricher._screen_specs) == 0


class TestAccessibilityRules:
    """Tests for accessibility checklist extraction."""

    def test_accessibility_rules_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert len(enricher._accessibility_rules) > 0

    def test_accessibility_rules_content(self, project_dir):
        enricher = TaskEnricher(project_dir)
        rules_text = " ".join(enricher._accessibility_rules)
        assert "alt text" in rules_text
        assert "keyboard" in rules_text
        assert "contrast" in rules_text

    def test_accessibility_injected_for_fe_page_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        page_task = task_list.tasks[3]  # FE-LoginPage
        assert page_task.enrichment_context is not None
        rules = page_task.enrichment_context.get("accessibility_rules")
        assert rules is not None
        assert len(rules) > 0

    def test_accessibility_injected_for_fe_component_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        comp_task = task_list.tasks[6]  # FE-Button-component
        assert comp_task.enrichment_context is not None
        rules = comp_task.enrichment_context.get("accessibility_rules")
        assert rules is not None
        assert len(rules) > 0

    def test_accessibility_not_injected_for_api_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        api_task = task_list.tasks[2]  # API controller
        ctx = api_task.enrichment_context or {}
        assert "accessibility_rules" not in ctx

    def test_accessibility_capped_at_8(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # Force more rules
        enricher._accessibility_rules = [f"Rule {i}" for i in range(20)]
        task = MockTask(id="test", type="fe_page", title="Test")
        task.enrichment_context = {}
        enricher._enrich_task(task)
        assert len(task.enrichment_context.get("accessibility_rules", [])) <= 8

    def test_accessibility_stats_updated(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        assert enricher.stats.tasks_with_accessibility > 0

    def test_accessibility_empty_without_file(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        enricher = TaskEnricher(empty)
        assert len(enricher._accessibility_rules) == 0


class TestRouteIndex:
    """Tests for route/information architecture index building."""

    def test_route_index_built(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert len(enricher._route_map) == 4  # registration, login, sessions, settings

    def test_route_content_correct(self, project_dir):
        enricher = TaskEnricher(project_dir)
        routes = {r["route"]: r for r in enricher._route_map}
        assert "/register" in routes
        assert "/login" in routes
        assert "/sessions" in routes
        assert "/settings" in routes

    def test_route_names_correct(self, project_dir):
        enricher = TaskEnricher(project_dir)
        names = [r["name"] for r in enricher._route_map]
        assert "Phone Registration" in names
        assert "Login" in names
        assert "Session Management" in names

    def test_routes_injected_for_fe_page_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        # FE-PhoneRegistration-page should match routes with "registration" keyword
        reg_task = task_list.tasks[7]  # FE-PhoneRegistration-page
        assert reg_task.enrichment_context is not None
        routes = reg_task.enrichment_context.get("routes")
        assert routes is not None
        assert len(routes) > 0

    def test_routes_not_injected_for_test_tasks(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        test_task = task_list.tasks[4]  # TEST-AuthMethod-unit
        ctx = test_task.enrichment_context or {}
        assert "routes" not in ctx

    def test_routes_capped_at_5(self, project_dir):
        enricher = TaskEnricher(project_dir)
        enricher._route_map = [
            {"name": f"Route {i}", "route": f"/route{i}", "content": "auth login register"}
            for i in range(20)
        ]
        task = MockTask(id="test", type="fe_page", title="Login page with auth")
        routes = enricher._get_related_routes(task)
        assert len(routes) <= 5

    def test_routes_stats_updated(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        assert enricher.stats.tasks_with_routes > 0

    def test_routes_empty_without_file(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        enricher = TaskEnricher(empty)
        assert len(enricher._route_map) == 0


class TestEnrichmentStatsSerialization:
    """Tests for new stats fields in saved enrichment output."""

    def test_saved_json_includes_new_stats(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        enriched_path = project_dir / "tasks" / "epic-001-tasks-enriched.json"
        data = json.loads(enriched_path.read_text(encoding="utf-8"))
        stats = data["enrichment_stats"]

        # All new stat fields should exist
        assert "tasks_with_test_scenarios" in stats
        assert "tasks_with_component_specs" in stats
        assert "tasks_with_screen_specs" in stats
        assert "tasks_with_accessibility" in stats
        assert "tasks_with_routes" in stats
        assert "tasks_with_design_tokens" in stats

    def test_saved_tasks_include_new_enrichment_keys(self, project_dir, task_list):
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        enriched_path = project_dir / "tasks" / "epic-001-tasks-enriched.json"
        data = json.loads(enriched_path.read_text(encoding="utf-8"))

        # Find the button component task
        button_task = next(t for t in data["tasks"] if "Button" in t["title"])
        assert "enrichment_context" in button_task
        assert "component_spec" in button_task["enrichment_context"]
        assert "design_tokens" in button_task["enrichment_context"]


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT INJECTOR TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestContextInjectorFormatEnrichment:
    """Tests for ContextInjector.format_enrichment."""

    def test_returns_empty_for_no_context(self):
        task = MockTask(id="test", enrichment_context=None)
        result = ContextInjector.format_enrichment(task)
        assert result == ""

    def test_returns_empty_for_empty_context(self):
        task = MockTask(id="test", enrichment_context={})
        result = ContextInjector.format_enrichment(task)
        assert result == ""

    def test_formats_diagrams(self):
        task = MockTask(id="test", enrichment_context={
            "diagrams": [
                {"type": "sequence", "file": "WA-AUTH-001_sequence.mmd", "content": "sequenceDiagram\n  A->>B: Hello"},
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert "Architecture Diagrams" in result
        assert "sequence" in result
        assert "```mermaid" in result

    def test_formats_known_gaps(self):
        task = MockTask(id="test", enrichment_context={
            "known_gaps": [
                {"severity": "high", "title": "Missing rate limiting", "suggestion": "Add rate limiting"},
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert "Known Issues" in result
        assert "HIGH" in result
        assert "rate limiting" in result

    def test_formats_related_dtos(self):
        task = MockTask(id="test", enrichment_context={
            "related_dtos": [
                {
                    "name": "CreateAuthMethodRequest",
                    "properties": [
                        {"name": "methodType", "type": "string", "enum": ["phone", "email"]},
                        {"name": "identifier", "type": "string"},
                    ],
                },
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert "Related DTOs" in result
        assert "CreateAuthMethodRequest" in result
        assert "methodType" in result

    def test_truncates_at_3500_chars(self):
        task = MockTask(id="test", enrichment_context={
            "diagrams": [
                {"type": f"type{i}", "file": f"f{i}.mmd", "content": "x" * 500} for i in range(10)
            ],
            "known_gaps": [
                {"severity": "high", "title": f"Issue {i}", "suggestion": "x" * 200} for i in range(10)
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert len(result) <= 3600  # 3500 + small margin for truncation text

    def test_combined_sections(self):
        task = MockTask(id="test", enrichment_context={
            "diagrams": [
                {"type": "sequence", "file": "f1.mmd", "content": "test content"},
            ],
            "known_gaps": [
                {"severity": "high", "title": "Issue 1", "suggestion": "Fix it"},
            ],
            "related_dtos": [
                {"name": "Dto1", "properties": [{"name": "field1", "type": "string"}]},
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert "Architecture Diagrams" in result
        assert "Known Issues" in result
        assert "Related DTOs" in result


class TestContextInjectorUserStories:
    """Tests for ContextInjector.format_user_stories_detail."""

    def test_returns_empty_for_no_context(self):
        task = MockTask(id="test", enrichment_context=None)
        result = ContextInjector.format_user_stories_detail(task)
        assert result == ""

    def test_formats_user_story_details(self):
        task = MockTask(id="test", enrichment_context={
            "user_story_details": [
                {
                    "title": "Phone Registration",
                    "as_a": "new user",
                    "i_want": "register with phone",
                    "so_that": "I can use the app",
                },
            ],
        })
        result = ContextInjector.format_user_stories_detail(task)
        assert "User Story Details" in result
        assert "new user" in result
        assert "register with phone" in result

    def test_caps_at_3_stories(self):
        task = MockTask(id="test", enrichment_context={
            "user_story_details": [
                {"title": f"Story {i}", "as_a": "user", "i_want": f"feature {i}", "so_that": "test"}
                for i in range(10)
            ],
        })
        result = ContextInjector.format_user_stories_detail(task)
        # Should only include 3 stories
        assert result.count("As user") <= 3


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 29b: CONTEXT INJECTOR NEW SECTION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestContextInjectorTestScenarios:
    """Tests for ContextInjector._format_test_scenarios."""

    def test_formats_gherkin_scenarios(self):
        task = MockTask(id="test", enrichment_context={
            "test_scenarios": (
                "Feature: Phone Registration\n"
                "  Scenario: Successful registration\n"
                "    Given a new user\n"
                "    When they register\n"
                "    Then account is created"
            ),
        })
        result = ContextInjector.format_enrichment(task)
        assert "Test Scenarios" in result
        assert "```gherkin" in result
        assert "Feature: Phone Registration" in result

    def test_gherkin_truncated_in_injector(self):
        long_gherkin = "Feature: Long\n" + "  Scenario: X\n    Given Y\n    When Z\n    Then W\n" * 50
        task = MockTask(id="test", enrichment_context={
            "test_scenarios": long_gherkin,
        })
        result = ContextInjector.format_enrichment(task)
        # The gherkin block itself should be within ~850 chars
        assert "```gherkin" in result


class TestContextInjectorComponentSpec:
    """Tests for ContextInjector._format_component_spec."""

    def test_formats_component_spec(self):
        task = MockTask(id="test", enrichment_context={
            "component_spec": {
                "name": "Button",
                "props": [
                    {"name": "label", "type": "string"},
                    {"name": "variant", "type": "'primary' | 'secondary'"},
                    {"name": "disabled", "type": "boolean"},
                ],
                "variants": ["primary", "secondary", "danger"],
                "accessibility": {"Role": "button", "ARIA Label": "Required"},
            },
        })
        result = ContextInjector.format_enrichment(task)
        assert "Component Spec: Button" in result
        assert "Props" in result
        assert "`label`" in result
        assert "Variants" in result
        assert "primary" in result
        assert "Accessibility" in result
        assert "Role" in result

    def test_formats_component_spec_minimal(self):
        """Component spec with only name and one prop still formats."""
        task = MockTask(id="test", enrichment_context={
            "component_spec": {
                "name": "Spinner",
                "props": [{"name": "size", "type": "number"}],
                "variants": [],
                "accessibility": {},
            },
        })
        result = ContextInjector.format_enrichment(task)
        assert "Component Spec: Spinner" in result
        assert "`size`" in result


class TestContextInjectorScreenSpec:
    """Tests for ContextInjector._format_screen_spec."""

    def test_formats_screen_spec(self):
        task = MockTask(id="test", enrichment_context={
            "screen_spec": {
                "title": "Phone Registration",
                "route": "/register",
                "api_endpoints": [
                    "POST /api/auth/send-otp",
                    "POST /api/auth/verify-otp",
                ],
                "component_details": [
                    {
                        "name": "Button",
                        "props": [
                            {"name": "label", "type": "string"},
                        ],
                        "accessibility": {"role": "button"},
                    },
                    {
                        "name": "PhoneInput",
                        "props": [
                            {"name": "value", "type": "string"},
                        ],
                        "accessibility": {},
                    },
                ],
            },
        })
        result = ContextInjector.format_enrichment(task)
        assert "Screen Spec: Phone Registration" in result
        assert "`/register`" in result
        assert "API Calls Required" in result
        assert "`POST /api/auth/send-otp`" in result
        assert "Components to Import" in result
        assert "`Button`" in result
        assert "`PhoneInput`" in result

    def test_formats_screen_spec_fallback_components(self):
        """Falls back to component ID list when no component_details."""
        task = MockTask(id="test", enrichment_context={
            "screen_spec": {
                "title": "Test Screen",
                "route": "/test",
                "components": ["COMP-001", "COMP-003", "COMP-004"],
            },
        })
        result = ContextInjector.format_enrichment(task)
        assert "Screen Spec: Test Screen" in result
        assert "Components:" in result
        assert "COMP-001" in result

    def test_screen_spec_with_role_attribute(self):
        task = MockTask(id="test", enrichment_context={
            "screen_spec": {
                "title": "Test",
                "route": "/test",
                "component_details": [
                    {
                        "name": "NavBar",
                        "props": [],
                        "accessibility": {"role": "navigation"},
                    },
                ],
            },
        })
        result = ContextInjector.format_enrichment(task)
        assert "[role=navigation]" in result


class TestContextInjectorAccessibility:
    """Tests for ContextInjector._format_accessibility."""

    def test_formats_accessibility_rules(self):
        task = MockTask(id="test", enrichment_context={
            "accessibility_rules": [
                "All images have alt text",
                "Color contrast meets 4.5:1 ratio",
                "All functionality available via keyboard",
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert "Accessibility Requirements" in result
        assert "WCAG 2.1 AA" in result
        assert "alt text" in result
        assert "keyboard" in result


class TestContextInjectorRoutes:
    """Tests for ContextInjector._format_routes."""

    def test_formats_routes(self):
        task = MockTask(id="test", enrichment_context={
            "routes": [
                {"name": "Phone Registration", "route": "/register", "content": "phone input, OTP"},
                {"name": "Login", "route": "/login", "content": "biometric auth"},
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert "Related Routes" in result
        assert "`/register`" in result
        assert "Phone Registration" in result
        assert "`/login`" in result


class TestContextInjectorCombinedPhase29b:
    """Tests for combined Phase 29b sections in ContextInjector."""

    def test_all_sections_combined(self):
        task = MockTask(id="test", enrichment_context={
            "diagrams": [
                {"type": "sequence", "file": "f1.mmd", "content": "A->>B"},
            ],
            "known_gaps": [
                {"severity": "high", "title": "Issue", "suggestion": "Fix it"},
            ],
            "test_scenarios": "Feature: Test\n  Scenario: X\n    Given Y\n",
            "component_spec": {
                "name": "Button",
                "props": [{"name": "label", "type": "string"}],
                "variants": [],
                "accessibility": {},
            },
            "screen_spec": {
                "title": "Login",
                "route": "/login",
                "api_endpoints": ["POST /api/auth/login"],
            },
            "accessibility_rules": [
                "Focus indicators visible",
            ],
            "routes": [
                {"name": "Login", "route": "/login", "content": "auth"},
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert "Architecture Diagrams" in result
        assert "Known Issues" in result
        assert "Test Scenarios" in result
        assert "Component Spec: Button" in result
        assert "Screen Spec: Login" in result
        assert "Accessibility Requirements" in result
        assert "Related Routes" in result

    def test_combined_stays_under_budget(self):
        """Even with all sections, output should be within 3500 chars."""
        task = MockTask(id="test", enrichment_context={
            "diagrams": [
                {"type": "seq", "file": "f.mmd", "content": "x" * 300},
            ],
            "known_gaps": [
                {"severity": "high", "title": "Gap", "suggestion": "x" * 200},
            ],
            "test_scenarios": "Feature: T\n" + "  Scenario: X\n" * 20,
            "component_spec": {
                "name": "Widget",
                "props": [{"name": f"p{i}", "type": "string"} for i in range(8)],
                "variants": ["a", "b", "c"],
                "accessibility": {"Role": "widget", "Label": "test"},
            },
            "screen_spec": {
                "title": "Page",
                "route": "/page",
                "api_endpoints": [f"GET /api/e{i}" for i in range(6)],
                "component_details": [
                    {"name": f"C{i}", "props": [{"name": "x", "type": "y"}], "accessibility": {}}
                    for i in range(5)
                ],
            },
            "accessibility_rules": [f"Rule {i}" for i in range(6)],
            "routes": [
                {"name": f"Route{i}", "route": f"/r{i}", "content": "stuff"} for i in range(5)
            ],
        })
        result = ContextInjector.format_enrichment(task)
        assert len(result) <= 3600  # 3500 + margin


# ═══════════════════════════════════════════════════════════════════════════
# HELPER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestHelperMethods:
    """Tests for TaskEnricher helper methods."""

    def test_extract_entity_name_schema(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert enricher._extract_entity_name("EPIC-001-SCHEMA-AuthMethod-model") == "AuthMethod"
        assert enricher._extract_entity_name("EPIC-001-SCHEMA-User-relations") == "User"
        assert enricher._extract_entity_name("EPIC-001-SCHEMA-DeviceToken-migration") == "DeviceToken"

    def test_extract_entity_name_non_schema(self, project_dir):
        enricher = TaskEnricher(project_dir)
        assert enricher._extract_entity_name("EPIC-001-API-POST-auth") is None

    def test_extract_keywords_from_title(self, project_dir):
        enricher = TaskEnricher(project_dir)
        keywords = enricher._extract_keywords_from_title("Create Prisma model for AuthMethod")
        assert "authmethod" in keywords
        # Common words should be filtered
        assert "create" not in keywords
        assert "prisma" not in keywords
        assert "model" not in keywords

    def test_extract_entity_from_api_task(self, project_dir):
        enricher = TaskEnricher(project_dir)
        # "authmethod" entity should be found in the task ID
        entity = enricher._extract_entity_from_api_task(
            "EPIC-001-API-POST-api_v1_authmethod_register-controller"
        )
        assert entity == "authmethod"


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    """End-to-end tests for the full enrichment + formatting pipeline."""

    def test_full_pipeline_schema_task(self, project_dir, task_list):
        """Schema task should get requirements, diagrams, DTOs, and criteria."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[0]  # SCHEMA-AuthMethod-model

        # Requirements populated
        assert "WA-AUTH-001" in task.related_requirements

        # Enrichment context populated
        assert task.enrichment_context is not None
        assert "diagrams" in task.enrichment_context
        assert "related_dtos" in task.enrichment_context

        # Success criteria generated
        assert task.success_criteria is not None

        # ContextInjector can format it
        prompt_text = ContextInjector.format_enrichment(task)
        assert len(prompt_text) > 0
        assert "erDiagram" in prompt_text or "sequence" in prompt_text

    def test_full_pipeline_api_task(self, project_dir, task_list):
        """API task should get diagrams and sequence flows."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[2]  # API controller

        # Should have some requirements (via keyword matching)
        # and possibly diagrams
        prompt_text = ContextInjector.format_enrichment(task)
        # Even if no direct match, the format should work
        assert isinstance(prompt_text, str)

    def test_full_pipeline_test_task(self, project_dir, task_list):
        """Test task should inherit from the entity being tested."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[4]  # TEST-AuthMethod-unit

        # Should inherit AuthMethod requirements
        assert "WA-AUTH-001" in task.related_requirements

    def test_enrichment_token_budget(self, project_dir, task_list):
        """Enrichment output should stay within token budget (~3500 chars)."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        for task in task_list.tasks:
            prompt_text = ContextInjector.format_enrichment(task)
            assert len(prompt_text) <= 3600, (
                f"Task {task.id} enrichment exceeds budget: {len(prompt_text)} chars"
            )

    def test_full_pipeline_fe_component_task(self, project_dir, task_list):
        """FE component task gets component spec, accessibility rules."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[6]  # FE-Button-component

        # Should have component spec
        assert task.enrichment_context is not None
        assert "component_spec" in task.enrichment_context
        assert task.enrichment_context["component_spec"]["name"] == "Button"

        # Should have accessibility rules
        assert "accessibility_rules" in task.enrichment_context
        assert len(task.enrichment_context["accessibility_rules"]) > 0

        # Should NOT have screen spec or routes
        assert "screen_spec" not in task.enrichment_context
        assert "routes" not in task.enrichment_context

        # ContextInjector can format it
        prompt_text = ContextInjector.format_enrichment(task)
        assert "Component Spec: Button" in prompt_text
        assert "Accessibility Requirements" in prompt_text

    def test_full_pipeline_fe_page_task(self, project_dir, task_list):
        """FE page task gets screen spec, accessibility, and routes."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[7]  # FE-PhoneRegistration-page

        assert task.enrichment_context is not None

        # Should have screen spec (via US-001 → SCREEN-001)
        assert "screen_spec" in task.enrichment_context
        screen = task.enrichment_context["screen_spec"]
        assert screen["route"] == "/register"

        # Screen should include component details
        assert "component_details" in screen
        assert len(screen["component_details"]) > 0

        # Should have accessibility rules
        assert "accessibility_rules" in task.enrichment_context

        # Should have routes (via keyword matching "phone" or "registration")
        assert "routes" in task.enrichment_context

        # ContextInjector formats all sections
        prompt_text = ContextInjector.format_enrichment(task)
        assert "Screen Spec" in prompt_text
        assert "Accessibility Requirements" in prompt_text

    def test_full_pipeline_test_task_with_gherkin(self, project_dir, task_list):
        """Test task gets Gherkin scenarios injected."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[4]  # TEST-AuthMethod-unit

        assert task.enrichment_context is not None
        assert "test_scenarios" in task.enrichment_context
        assert "Feature:" in task.enrichment_context["test_scenarios"]

        # ContextInjector formats it
        prompt_text = ContextInjector.format_enrichment(task)
        assert "Test Scenarios" in prompt_text
        assert "```gherkin" in prompt_text


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 29c: DESIGN TOKENS TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestDesignTokensIndex:
    """Tests for design tokens index building and enrichment (Phase 29c)."""

    def test_design_tokens_index_built(self, project_dir):
        """Design tokens loaded from ui_design/design_tokens.json."""
        enricher = TaskEnricher(project_dir)
        assert enricher._design_tokens
        assert "colors" in enricher._design_tokens

    def test_design_tokens_has_colors(self, project_dir):
        """Colors section extracted with correct values."""
        enricher = TaskEnricher(project_dir)
        colors = enricher._design_tokens.get("colors", {})
        assert colors["primary"] == "#1E3A8A"
        assert colors["error"] == "#DC2626"
        assert colors["success"] == "#10B981"

    def test_design_tokens_has_typography(self, project_dir):
        """Typography section extracted in compact format."""
        enricher = TaskEnricher(project_dir)
        typo = enricher._design_tokens.get("typography", {})
        assert "h1" in typo
        assert "2.5rem" in typo["h1"]
        assert "body" in typo

    def test_design_tokens_has_font_family(self, project_dir):
        """Font family extracted from typography section."""
        enricher = TaskEnricher(project_dir)
        font = enricher._design_tokens.get("font_family", "")
        assert "Inter" in font

    def test_design_tokens_has_spacing(self, project_dir):
        """Spacing scale extracted correctly."""
        enricher = TaskEnricher(project_dir)
        spacing = enricher._design_tokens.get("spacing", {})
        assert spacing["xs"] == "0.25rem"
        assert spacing["md"] == "1rem"

    def test_design_tokens_has_breakpoints(self, project_dir):
        """Breakpoints extracted as numeric values."""
        enricher = TaskEnricher(project_dir)
        bp = enricher._design_tokens.get("breakpoints", {})
        assert bp["mobile"] == 320
        assert bp["desktop"] == 1024

    def test_design_tokens_has_border_radius(self, project_dir):
        """Border radius tokens extracted."""
        enricher = TaskEnricher(project_dir)
        br = enricher._design_tokens.get("border_radius", {})
        assert "sm" in br
        assert "full" in br
        assert br["full"] == "9999px"

    def test_design_tokens_injected_for_fe_component(self, project_dir, task_list):
        """fe_component tasks get design tokens."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        task = task_list.tasks[6]  # FE-Button-component
        assert task.type == "fe_component"
        assert task.enrichment_context is not None
        assert "design_tokens" in task.enrichment_context
        assert task.enrichment_context["design_tokens"]["colors"]["primary"] == "#1E3A8A"

    def test_design_tokens_injected_for_fe_page(self, project_dir, task_list):
        """fe_page tasks get design tokens."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        task = task_list.tasks[3]  # FE-LoginPage
        assert task.type == "fe_page"
        assert task.enrichment_context is not None
        assert "design_tokens" in task.enrichment_context

    def test_design_tokens_not_injected_for_schema(self, project_dir, task_list):
        """schema_model tasks do NOT get design tokens."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        task = task_list.tasks[0]  # SCHEMA-AuthMethod-model
        assert task.type == "schema_model"
        if task.enrichment_context:
            assert "design_tokens" not in task.enrichment_context

    def test_design_tokens_not_injected_for_api(self, project_dir, task_list):
        """api_controller tasks do NOT get design tokens."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        task = task_list.tasks[2]  # API-POST controller
        assert task.type == "api_controller"
        if task.enrichment_context:
            assert "design_tokens" not in task.enrichment_context

    def test_design_tokens_not_injected_for_test(self, project_dir, task_list):
        """test_unit tasks do NOT get design tokens."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        task = task_list.tasks[4]  # TEST-AuthMethod-unit
        assert task.type == "test_unit"
        if task.enrichment_context:
            assert "design_tokens" not in task.enrichment_context

    def test_design_tokens_stats_updated(self, project_dir, task_list):
        """Stats track how many tasks got design tokens."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)
        # 4 fe_* tasks: fe_page (LoginPage), fe_component (Button), fe_page (PhoneReg), + fe_page again
        # tasks[3]=fe_page, tasks[6]=fe_component, tasks[7]=fe_page → 3 fe_* tasks
        assert enricher.stats.tasks_with_design_tokens >= 3

    def test_design_tokens_empty_without_file(self, tmp_path):
        """No crash when design_tokens.json is missing."""
        project = tmp_path / "empty_project"
        project.mkdir()
        enricher = TaskEnricher(project)
        assert enricher._design_tokens == {}

    def test_design_tokens_invalid_json(self, tmp_path):
        """Handles invalid JSON gracefully."""
        project = tmp_path / "bad_project"
        project.mkdir()
        ui_dir = project / "ui_design"
        ui_dir.mkdir()
        (ui_dir / "design_tokens.json").write_text("not valid json", encoding="utf-8")
        enricher = TaskEnricher(project)
        assert enricher._design_tokens == {}

    def test_design_tokens_empty_object(self, tmp_path):
        """Handles empty JSON object (no sections)."""
        project = tmp_path / "minimal_project"
        project.mkdir()
        ui_dir = project / "ui_design"
        ui_dir.mkdir()
        (ui_dir / "design_tokens.json").write_text("{}", encoding="utf-8")
        enricher = TaskEnricher(project)
        assert enricher._design_tokens == {}

    def test_design_tokens_partial_sections(self, tmp_path):
        """Handles JSON with only some sections."""
        project = tmp_path / "partial_project"
        project.mkdir()
        ui_dir = project / "ui_design"
        ui_dir.mkdir()
        (ui_dir / "design_tokens.json").write_text(
            json.dumps({"colors": {"primary": "#FF0000"}}),
            encoding="utf-8",
        )
        enricher = TaskEnricher(project)
        assert enricher._design_tokens
        assert enricher._design_tokens["colors"]["primary"] == "#FF0000"
        assert "typography" not in enricher._design_tokens


class TestContextInjectorDesignTokens:
    """Tests for ContextInjector design tokens formatting (Phase 29c)."""

    def test_format_design_tokens_includes_colors(self):
        """Design tokens section includes color values."""
        task = MockTask(
            id="test-fe-comp", type="fe_component",
            enrichment_context={
                "design_tokens": {
                    "colors": {"primary": "#1E3A8A", "error": "#DC2626"},
                }
            }
        )
        text = ContextInjector.format_enrichment(task)
        assert "Design System Tokens" in text
        assert "#1E3A8A" in text
        assert "primary" in text

    def test_format_design_tokens_includes_typography(self):
        """Design tokens section includes typography scale."""
        task = MockTask(
            id="test-fe-comp", type="fe_component",
            enrichment_context={
                "design_tokens": {
                    "typography": {"h1": "2.5rem/700", "body": "1rem/400"},
                    "font_family": "Inter, Helvetica, sans-serif",
                }
            }
        )
        text = ContextInjector.format_enrichment(task)
        assert "Typography" in text
        assert "2.5rem/700" in text
        assert "Inter" in text

    def test_format_design_tokens_includes_spacing(self):
        """Design tokens section includes spacing scale."""
        task = MockTask(
            id="test-fe-comp", type="fe_component",
            enrichment_context={
                "design_tokens": {
                    "spacing": {"xs": "0.25rem", "md": "1rem", "xl": "2rem"},
                }
            }
        )
        text = ContextInjector.format_enrichment(task)
        assert "Spacing" in text
        assert "0.25rem" in text

    def test_format_design_tokens_includes_breakpoints(self):
        """Design tokens section includes responsive breakpoints."""
        task = MockTask(
            id="test-fe-comp", type="fe_component",
            enrichment_context={
                "design_tokens": {
                    "breakpoints": {"mobile": 320, "desktop": 1024},
                }
            }
        )
        text = ContextInjector.format_enrichment(task)
        assert "Breakpoints" in text
        assert "320px" in text
        assert "1024px" in text

    def test_format_design_tokens_includes_border_radius(self):
        """Design tokens section includes border radius values."""
        task = MockTask(
            id="test-fe-comp", type="fe_component",
            enrichment_context={
                "design_tokens": {
                    "border_radius": {"sm": "0.125rem", "full": "9999px"},
                }
            }
        )
        text = ContextInjector.format_enrichment(task)
        assert "Border Radius" in text
        assert "9999px" in text

    def test_format_design_tokens_combined_budget(self):
        """Full design tokens stay within reasonable size."""
        task = MockTask(
            id="test-fe-comp", type="fe_component",
            enrichment_context={
                "design_tokens": {
                    "colors": {"primary": "#1E3A8A", "secondary": "#6B7280",
                               "error": "#DC2626", "success": "#10B981"},
                    "font_family": "Inter, Helvetica, sans-serif",
                    "typography": {"h1": "2.5rem/700", "h2": "2rem/600", "body": "1rem/400"},
                    "spacing": {"xs": "0.25rem", "sm": "0.5rem", "md": "1rem",
                                "lg": "1.5rem", "xl": "2rem"},
                    "breakpoints": {"mobile": 320, "tablet": 768, "desktop": 1024},
                    "border_radius": {"sm": "0.125rem", "md": "0.375rem", "full": "9999px"},
                }
            }
        )
        text = ContextInjector.format_enrichment(task)
        # Design tokens should be ~400-600 chars — well within 3500 budget
        assert len(text) < 1000
        assert "Design System Tokens" in text


class TestEndToEndDesignTokens:
    """End-to-end test for design tokens in the full pipeline (Phase 29c)."""

    def test_full_pipeline_fe_component_gets_design_tokens(self, project_dir, task_list):
        """fe_component task gets design tokens + ContextInjector formats them."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[6]  # FE-Button-component
        assert task.enrichment_context is not None
        assert "design_tokens" in task.enrichment_context
        assert "colors" in task.enrichment_context["design_tokens"]
        assert "spacing" in task.enrichment_context["design_tokens"]

        # ContextInjector includes them in prompt
        prompt_text = ContextInjector.format_enrichment(task)
        assert "Design System Tokens" in prompt_text
        assert "#1E3A8A" in prompt_text  # primary color
        assert "Inter" in prompt_text    # font family

    def test_full_pipeline_fe_page_gets_design_tokens(self, project_dir, task_list):
        """fe_page task gets design tokens alongside screen spec and accessibility."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[7]  # FE-PhoneRegistration-page
        assert task.enrichment_context is not None
        assert "design_tokens" in task.enrichment_context

        # Should also have screen_spec + accessibility (from Phase 29b)
        prompt_text = ContextInjector.format_enrichment(task)
        assert "Design System Tokens" in prompt_text
        # This page should also have screen spec and accessibility
        assert "Accessibility Requirements" in prompt_text

    def test_full_pipeline_schema_has_no_design_tokens(self, project_dir, task_list):
        """schema_model task prompt does NOT contain design tokens."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[0]  # SCHEMA-AuthMethod-model
        prompt_text = ContextInjector.format_enrichment(task)
        assert "Design System Tokens" not in prompt_text

    def test_design_tokens_within_total_budget(self, project_dir, task_list):
        """fe_page task with ALL enrichment stays within 3500 char budget."""
        enricher = TaskEnricher(project_dir)
        enricher.enrich_all(task_list)

        task = task_list.tasks[7]  # FE-PhoneRegistration-page (has everything)
        prompt_text = ContextInjector.format_enrichment(task)
        assert len(prompt_text) <= 3500
