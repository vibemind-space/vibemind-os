"""
Unit tests for Phase 11: PromptHints and Event Payloads system.

Tests cover:
- EventPayload dataclasses and parsing
- PromptHints generation and merging
- Event class typed payload support
- Backward compatibility
"""

import pytest
from datetime import datetime

from src.mind.event_bus import Event, EventType
from src.mind.event_payloads import (
    EventPayload,
    BuildFailurePayload,
    BuildSuccessPayload,
    TypeErrorPayload,
    TestFailurePayload,
    MockViolationPayload,
    CodeFixNeededPayload,
    E2ETestResultPayload,
    UXIssuePayload,
    get_payload_type,
    get_typed_payload,
    PayloadPriority,
)
from src.mind.prompt_hints import (
    PromptHints,
    HintPriority,
    build_hints_from_event,
    merge_hints_from_events,
    build_hints_for_build_failure,
    build_hints_for_type_error,
    build_hints_for_test_failure,
    build_hints_for_mock_violation,
)


class TestEventPayloads:
    """Tests for typed event payloads."""

    def test_build_failure_payload_creation(self):
        """Test creating a BuildFailurePayload."""
        payload = BuildFailurePayload(
            error_count=3,
            errors=[
                {"file": "src/App.tsx", "line": 10, "message": "Cannot find module"},
            ],
            failing_command="npm run build",
            exit_code=1,
            is_import_error=True,
        )

        assert payload.error_count == 3
        assert payload.is_import_error is True
        assert payload.is_type_error is False
        assert len(payload.errors) == 1

    def test_build_failure_from_output(self):
        """Test parsing build output into payload."""
        output = """
src/App.tsx:10:5: error TS2307: Cannot find module './utils'.
src/index.ts:5:1: error TS2345: Argument of type 'string' is not assignable.
        """

        payload = BuildFailurePayload.from_build_output(output, exit_code=1)

        assert payload.error_count >= 1
        assert payload.is_import_error is True
        assert "src/App.tsx" in payload.affected_files or len(payload.affected_files) > 0

    def test_type_error_payload_from_tsc(self):
        """Test parsing TypeScript compiler output."""
        output = """
src/components/Button.tsx(15,3): error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.
src/utils/helper.ts(42,10): error TS2304: Cannot find name 'MyType'.
        """

        payload = TypeErrorPayload.from_tsc_output(output)

        assert payload.error_count == 2
        assert len(payload.errors_by_file) == 2
        assert "MyType" in payload.missing_types
        assert len(payload.type_mismatches) >= 1

    def test_mock_violation_payload_categorization(self):
        """Test categorizing mock violations."""
        violations = [
            {"message": "Mock data detected", "severity": "error"},
            {"message": "TODO: implement this", "code": "// TODO", "severity": "warning"},
            {"message": "Lorem ipsum placeholder", "severity": "error"},
            {"message": "mock_function() returns fake data", "code": "mock_", "severity": "error"},
        ]

        payload = MockViolationPayload.from_violations(violations)

        assert payload.error_count == 3
        assert payload.warning_count == 1
        assert len(payload.todo_comments) == 1
        assert len(payload.placeholder_text) == 1
        # Both "Mock data detected" and "mock_function()" are categorized as mock-related
        assert len(payload.mock_functions) == 2

    def test_payload_to_dict(self):
        """Test converting payload to dictionary."""
        payload = BuildFailurePayload(
            error_count=1,
            errors=[{"file": "test.ts", "message": "Error"}],
        )

        data = payload.to_dict()

        assert data["error_count"] == 1
        assert len(data["errors"]) == 1
        assert "timestamp" in data

    def test_payload_from_dict(self):
        """Test creating payload from dictionary."""
        data = {
            "error_count": 2,
            "errors": [{"file": "a.ts"}, {"file": "b.ts"}],
            "failing_command": "npm test",
        }

        payload = BuildFailurePayload.from_dict(data)

        assert payload.error_count == 2
        assert payload.failing_command == "npm test"

    def test_get_payload_type(self):
        """Test getting payload type for event types."""
        assert get_payload_type(EventType.BUILD_FAILED) == BuildFailurePayload
        assert get_payload_type(EventType.TYPE_ERROR) == TypeErrorPayload
        assert get_payload_type(EventType.TEST_FAILED) == TestFailurePayload
        assert get_payload_type(EventType.MOCK_DETECTED) == MockViolationPayload

    def test_get_typed_payload(self):
        """Test parsing event data into typed payload."""
        data = {
            "error_count": 1,
            "errors": [{"file": "test.ts"}],
            "is_type_error": True,
        }

        payload = get_typed_payload(EventType.BUILD_FAILED, data)

        assert isinstance(payload, BuildFailurePayload)
        assert payload.error_count == 1


class TestPromptHints:
    """Tests for PromptHints generation and merging."""

    def test_prompt_hints_creation(self):
        """Test creating PromptHints."""
        hints = PromptHints(
            priority=HintPriority.CRITICAL,
            priority_instructions=["Fix the import error first"],
            context_files=["src/App.tsx"],
            constraints=["Do not use 'any' type"],
            root_cause="Missing module import",
        )

        assert hints.priority == HintPriority.CRITICAL
        assert len(hints.priority_instructions) == 1
        assert not hints.is_empty()

    def test_prompt_hints_to_section(self):
        """Test generating prompt section from hints."""
        hints = PromptHints(
            priority=HintPriority.HIGH,
            priority_instructions=["Fix type mismatch"],
            context_files=["src/utils.ts"],
            constraints=["No any type"],
            root_cause="Type mismatch in function return",
        )

        section = hints.to_prompt_section()

        assert "## HIGH PRIORITY" in section
        assert "Fix type mismatch" in section
        assert "src/utils.ts" in section
        assert "No any type" in section
        assert "Type mismatch" in section

    def test_prompt_hints_is_empty(self):
        """Test detecting empty hints."""
        empty = PromptHints()
        assert empty.is_empty()

        non_empty = PromptHints(priority_instructions=["Do something"])
        assert not non_empty.is_empty()

    def test_prompt_hints_merge(self):
        """Test merging two PromptHints."""
        hints1 = PromptHints(
            priority=HintPriority.HIGH,
            priority_instructions=["Instruction 1"],
            context_files=["file1.ts"],
            constraints=["Constraint 1"],
        )

        hints2 = PromptHints(
            priority=HintPriority.CRITICAL,
            priority_instructions=["Instruction 2"],
            context_files=["file2.ts"],
            constraints=["Constraint 2"],
        )

        merged = hints1.merge(hints2)

        # Higher priority wins
        assert merged.priority == HintPriority.CRITICAL

        # Lists are merged
        assert len(merged.priority_instructions) == 2
        assert len(merged.context_files) == 2
        assert len(merged.constraints) == 2

    def test_prompt_hints_merge_deduplicates(self):
        """Test that merging deduplicates lists."""
        hints1 = PromptHints(
            context_files=["file1.ts", "file2.ts"],
        )

        hints2 = PromptHints(
            context_files=["file2.ts", "file3.ts"],
        )

        merged = hints1.merge(hints2)

        # Should have 3 unique files, not 4
        assert len(merged.context_files) == 3


class TestHintBuilders:
    """Tests for event-specific hint builders."""

    def test_build_hints_for_build_failure_import(self):
        """Test building hints for import error build failure."""
        payload = BuildFailurePayload(
            error_count=1,
            is_import_error=True,
            likely_causes=["Missing import"],
            affected_files=["src/App.tsx"],
        )

        hints = build_hints_for_build_failure(payload)

        assert hints.priority == HintPriority.CRITICAL
        assert "import" in hints.root_cause.lower()
        assert any("import" in i.lower() for i in hints.priority_instructions)
        assert "src/App.tsx" in hints.context_files

    def test_build_hints_for_build_failure_type_error(self):
        """Test building hints for type error build failure."""
        payload = BuildFailurePayload(
            error_count=1,
            is_type_error=True,
            affected_files=["src/utils.ts"],
        )

        hints = build_hints_for_build_failure(payload)

        assert hints.priority == HintPriority.CRITICAL
        assert "type" in hints.root_cause.lower()
        assert any("any" in c.lower() for c in hints.constraints)

    def test_build_hints_for_type_error(self):
        """Test building hints for TypeScript errors."""
        payload = TypeErrorPayload(
            error_count=2,
            errors_by_file={"src/a.ts": [], "src/b.ts": []},
            missing_types=["MyType"],
            type_mismatches=[{
                "expected": "number",
                "actual": "string",
                "location": "src/a.ts:10",
            }],
        )

        hints = build_hints_for_type_error(payload)

        assert hints.priority == HintPriority.HIGH
        assert "MyType" in hints.root_cause
        assert "src/a.ts" in hints.context_files
        assert any("any" in c.lower() for c in hints.constraints)

    def test_build_hints_for_test_failure(self):
        """Test building hints for test failure."""
        payload = TestFailurePayload(
            test_name="should render correctly",
            test_file="tests/App.test.tsx",
            expected="<Button>Click me</Button>",
            actual="<Button>Click</Button>",
            related_source_files=["src/App.tsx"],
        )

        hints = build_hints_for_test_failure(payload)

        assert hints.priority == HintPriority.HIGH
        assert "should render correctly" in hints.root_cause
        assert "tests/App.test.tsx" in hints.context_files
        assert any("test" in c.lower() for c in hints.constraints)

    def test_build_hints_for_mock_violation(self):
        """Test building hints for mock violations."""
        payload = MockViolationPayload(
            violations=[{"file": "src/api.ts", "message": "Mock data"}],
            error_count=1,
            hardcoded_data=[{"file": "src/api.ts"}],
        )

        hints = build_hints_for_mock_violation(payload)

        assert hints.priority == HintPriority.HIGH
        assert "mock" in hints.root_cause.lower() or "1" in hints.root_cause
        assert "src/api.ts" in hints.context_files
        assert any("mock" in p.lower() or "lorem" in p.lower() for p in hints.avoid_patterns)


class TestEventWithTypedPayload:
    """Tests for Event class with typed payload support."""

    def test_event_auto_parses_typed_payload(self):
        """Test that Event auto-parses typed payload from data."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="TestAgent",
            data={
                "error_count": 2,
                "errors": [{"file": "test.ts"}],
            },
        )

        assert event.typed is not None
        assert isinstance(event.typed, BuildFailurePayload)
        assert event.typed.error_count == 2

    def test_event_get_method_with_typed_payload(self):
        """Test Event.get() falls back to typed payload."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="TestAgent",
            data={"error_count": 3},
        )

        # Should get from typed payload
        assert event.get("error_count") == 3

        # Should return default for missing keys
        assert event.get("nonexistent", "default") == "default"

    def test_event_with_payload_factory(self):
        """Test Event.with_payload() factory method."""
        payload = BuildFailurePayload(
            error_count=1,
            errors=[{"file": "test.ts", "message": "Error"}],
        )

        event = Event.with_payload(
            type=EventType.BUILD_FAILED,
            source="TestAgent",
            payload=payload,
        )

        assert event.typed is payload
        assert event.data["error_count"] == 1

    def test_event_prompt_hints_on_demand(self):
        """Test that prompt_hints are built on-demand."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="TestAgent",
            data={
                "error_count": 1,
                "is_import_error": True,
            },
        )

        hints = event.prompt_hints

        # Should build hints on access
        assert hints is not None
        assert isinstance(hints, PromptHints)

    def test_event_to_dict_includes_typed_payload(self):
        """Test that to_dict includes typed payload."""
        payload = BuildFailurePayload(error_count=1)
        event = Event.with_payload(
            type=EventType.BUILD_FAILED,
            source="TestAgent",
            payload=payload,
        )

        data = event.to_dict()

        assert "typed_payload" in data
        assert data["typed_payload"]["error_count"] == 1

    def test_backward_compatibility_data_dict(self):
        """Test that event.data still works for backward compatibility."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="TestAgent",
            data={
                "error_count": 5,
                "custom_field": "custom_value",
            },
        )

        # Old way should still work
        assert event.data.get("error_count") == 5
        assert event.data.get("custom_field") == "custom_value"


class TestMergeHintsFromEvents:
    """Tests for merging hints from multiple events."""

    def test_merge_hints_from_multiple_events(self):
        """Test merging hints from multiple events."""
        events = [
            Event(
                type=EventType.BUILD_FAILED,
                source="BuildAgent",
                data={"error_count": 1, "is_import_error": True},
            ),
            Event(
                type=EventType.TYPE_ERROR,
                source="TypeChecker",
                data={
                    "error_count": 2,
                    "errors_by_file": {"src/a.ts": []},
                    "missing_types": ["MyType"],
                },
            ),
        ]

        merged = merge_hints_from_events(events)

        # Should merge instructions from both
        assert len(merged.priority_instructions) > 0

        # Should have context files from both
        assert len(merged.context_files) > 0

    def test_merge_hints_empty_events(self):
        """Test merging with no events."""
        merged = merge_hints_from_events([])

        assert merged.is_empty()

    def test_merge_hints_no_applicable_events(self):
        """Test merging with events that have no hint builders."""
        events = [
            Event(
                type=EventType.FILE_CREATED,
                source="FileAgent",
                data={"path": "/tmp/test.ts"},
            ),
        ]

        merged = merge_hints_from_events(events)

        # FILE_CREATED has no hint builder, so should be empty
        assert merged.is_empty()


class TestBuildHintsFromEvent:
    """Tests for build_hints_from_event function."""

    def test_build_hints_from_build_failed_event(self):
        """Test building hints from BUILD_FAILED event."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="BuildAgent",
            data={
                "error_count": 1,
                "is_import_error": True,
                "affected_files": ["src/App.tsx"],
            },
        )

        hints = build_hints_from_event(event)

        assert hints is not None
        assert hints.priority == HintPriority.CRITICAL

    def test_build_hints_returns_none_for_unknown_event(self):
        """Test that None is returned for events without hint builders."""
        event = Event(
            type=EventType.FILE_CREATED,
            source="FileAgent",
            data={},
        )

        hints = build_hints_from_event(event)

        assert hints is None

    def test_build_hints_uses_cached_typed_payload(self):
        """Test that hints use the cached typed payload."""
        payload = BuildFailurePayload(
            error_count=5,
            is_type_error=True,
        )

        event = Event.with_payload(
            type=EventType.BUILD_FAILED,
            source="BuildAgent",
            payload=payload,
        )

        hints = build_hints_from_event(event)

        assert hints is not None
        # Hints should be based on the typed payload
        assert "type" in hints.root_cause.lower()
