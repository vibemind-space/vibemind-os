"""
Prompt Hints - Structured guidance for Claude when building prompts.

PromptHints provide contextual instructions that help Claude focus on
the most important aspects of a fix request.

Benefits:
- Priority instructions guide Claude to fix critical issues first
- Constraints prevent common mistakes (e.g., "do not use 'any' type")
- Previous attempts help avoid repeating failed fixes
- Suggested approaches provide a starting point

Usage:
    from src.mind.prompt_hints import build_hints_from_event, PromptHints

    # Build hints from an event
    hints = build_hints_from_event(event)

    # Generate prompt section
    prompt_section = hints.to_prompt_section()

    # Merge hints from multiple events
    merged = hints1.merge(hints2)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .event_bus import Event, EventType
    from .event_payloads import EventPayload


class HintPriority(Enum):
    """Priority level for prompt hints."""
    CRITICAL = "critical"  # Blocking issue, fix immediately
    HIGH = "high"          # Important, fix soon
    MEDIUM = "medium"      # Should fix, but not blocking
    LOW = "low"            # Nice to have


@dataclass
class PromptHints:
    """
    Structured hints for Claude when building fix prompts.

    These hints are injected at the top of prompts to guide
    Claude's focus and prevent common mistakes.
    """

    # What to focus on first
    priority_instructions: list[str] = field(default_factory=list)

    # Files that are relevant to the fix
    context_files: list[str] = field(default_factory=list)

    # Rules that MUST be followed
    constraints: list[str] = field(default_factory=list)

    # Patterns to avoid
    avoid_patterns: list[str] = field(default_factory=list)

    # Previous fix attempts (for learning)
    previous_attempts: list[dict] = field(default_factory=list)
    # Each attempt: {"summary": str, "success": bool, "reason": str}

    # Suggested fix approach
    suggested_approach: Optional[str] = None

    # Priority level
    priority: HintPriority = HintPriority.HIGH

    # Root cause hypothesis
    root_cause: Optional[str] = None

    # Token budget hint (for progressive disclosure)
    max_context_files: int = 5
    truncate_errors_after: int = 10

    def to_prompt_section(self) -> str:
        """
        Generate a prompt section from these hints.

        Returns a formatted string that can be prepended to prompts.
        """
        lines = []

        # Priority header
        priority_label = self.priority.value.upper()
        lines.append(f"## {priority_label} PRIORITY\n")

        # Root cause
        if self.root_cause:
            lines.append(f"### Likely Root Cause")
            lines.append(f"{self.root_cause}\n")

        # Priority instructions
        if self.priority_instructions:
            lines.append("### Priority Instructions")
            for i, instruction in enumerate(self.priority_instructions, 1):
                lines.append(f"{i}. {instruction}")
            lines.append("")

        # Relevant files
        if self.context_files:
            lines.append("### Relevant Files")
            for file_path in self.context_files[:self.max_context_files]:
                lines.append(f"- {file_path}")
            if len(self.context_files) > self.max_context_files:
                remaining = len(self.context_files) - self.max_context_files
                lines.append(f"- ... and {remaining} more files")
            lines.append("")

        # Constraints
        if self.constraints:
            lines.append("### Constraints (MUST follow)")
            for constraint in self.constraints:
                lines.append(f"- {constraint}")
            lines.append("")

        # Avoid patterns
        if self.avoid_patterns:
            lines.append("### Avoid These Patterns")
            for pattern in self.avoid_patterns:
                lines.append(f"- {pattern}")
            lines.append("")

        # Previous attempts
        if self.previous_attempts:
            lines.append("### Previous Attempts (learn from these)")
            for attempt in self.previous_attempts[-3:]:  # Last 3 attempts
                status = "SUCCESS" if attempt.get("success") else "FAILED"
                lines.append(f"- [{status}] {attempt.get('summary', 'Unknown')}")
                if attempt.get("reason"):
                    lines.append(f"  Reason: {attempt.get('reason')}")
            lines.append("")

        # Suggested approach
        if self.suggested_approach:
            lines.append("### Suggested Approach")
            lines.append(self.suggested_approach)
            lines.append("")

        return "\n".join(lines)

    def merge(self, other: "PromptHints") -> "PromptHints":
        """
        Merge two PromptHints, combining their content.

        Higher priority hints take precedence.
        """
        # Determine which has higher priority
        priority_order = [HintPriority.CRITICAL, HintPriority.HIGH,
                         HintPriority.MEDIUM, HintPriority.LOW]
        self_idx = priority_order.index(self.priority)
        other_idx = priority_order.index(other.priority)

        # Use higher priority
        merged_priority = self.priority if self_idx <= other_idx else other.priority

        # Merge lists (deduplicate)
        def merge_lists(a: list, b: list) -> list:
            seen = set()
            result = []
            for item in a + b:
                key = str(item) if isinstance(item, dict) else item
                if key not in seen:
                    seen.add(key)
                    result.append(item)
            return result

        return PromptHints(
            priority_instructions=merge_lists(
                self.priority_instructions, other.priority_instructions
            ),
            context_files=merge_lists(self.context_files, other.context_files),
            constraints=merge_lists(self.constraints, other.constraints),
            avoid_patterns=merge_lists(self.avoid_patterns, other.avoid_patterns),
            previous_attempts=self.previous_attempts + other.previous_attempts,
            suggested_approach=self.suggested_approach or other.suggested_approach,
            priority=merged_priority,
            root_cause=self.root_cause or other.root_cause,
            max_context_files=min(self.max_context_files, other.max_context_files),
            truncate_errors_after=min(
                self.truncate_errors_after, other.truncate_errors_after
            ),
        )

    def is_empty(self) -> bool:
        """Check if hints contain any meaningful content."""
        return (
            not self.priority_instructions
            and not self.context_files
            and not self.constraints
            and not self.avoid_patterns
            and not self.previous_attempts
            and not self.suggested_approach
            and not self.root_cause
        )


# =============================================================================
# Hint Builders for Specific Event Types
# =============================================================================

def build_hints_for_build_failure(payload) -> PromptHints:
    """
    Build PromptHints for BUILD_FAILED events.

    Analyzes the build failure payload to generate targeted hints.
    """
    from .event_payloads import BuildFailurePayload

    if not isinstance(payload, BuildFailurePayload):
        return PromptHints()

    hints = PromptHints(priority=HintPriority.CRITICAL)

    # Root cause from payload analysis
    if payload.is_import_error:
        hints.root_cause = "Import resolution failure - missing module or incorrect path"
        hints.priority_instructions.append(
            "Check import paths and ensure all dependencies are installed"
        )
        hints.priority_instructions.append(
            "Verify package.json has all required dependencies"
        )
        hints.constraints.append("Do not use relative imports for node_modules packages")

    elif payload.is_type_error:
        hints.root_cause = "TypeScript type checking failure"
        hints.priority_instructions.append(
            "Fix type mismatches starting with the first error"
        )
        hints.priority_instructions.append(
            "Later errors may be cascading from the first"
        )
        hints.constraints.append("Do not use 'any' type as a fix")
        hints.constraints.append("Ensure all function parameters have explicit types")

    elif payload.is_syntax_error:
        hints.root_cause = "JavaScript/TypeScript syntax error"
        hints.priority_instructions.append(
            "Check for missing brackets, parentheses, or semicolons"
        )
        hints.constraints.append("Ensure all JSX tags are properly closed")

    # Add affected files
    hints.context_files = payload.affected_files[:10]

    # Add likely causes as instructions
    for cause in payload.likely_causes:
        if cause not in hints.priority_instructions:
            hints.priority_instructions.append(cause)

    # Suggest approach
    if payload.error_count == 1:
        hints.suggested_approach = "Single error - fix directly"
    elif payload.error_count <= 5:
        hints.suggested_approach = (
            "Multiple related errors - fix the first one and verify "
            "if remaining errors are resolved"
        )
    else:
        hints.suggested_approach = (
            f"{payload.error_count} errors detected. Focus on the first 3 errors - "
            "many may be cascading from earlier issues"
        )

    return hints


def build_hints_for_type_error(payload) -> PromptHints:
    """Build PromptHints for TYPE_ERROR events."""
    from .event_payloads import TypeErrorPayload

    if not isinstance(payload, TypeErrorPayload):
        return PromptHints()

    hints = PromptHints(priority=HintPriority.HIGH)

    # Root cause based on error types
    if payload.missing_types:
        hints.root_cause = f"Missing type definitions: {', '.join(payload.missing_types[:5])}"
        hints.priority_instructions.append(
            f"Define or import these types: {', '.join(payload.missing_types[:3])}"
        )

    if payload.type_mismatches:
        mismatch = payload.type_mismatches[0]
        hints.priority_instructions.append(
            f"Fix type mismatch at {mismatch['location']}: "
            f"expected '{mismatch['expected']}' but got '{mismatch['actual']}'"
        )

    # Context files (grouped by file)
    hints.context_files = list(payload.errors_by_file.keys())[:10]

    # Standard TypeScript constraints
    hints.constraints = [
        "Do not use 'any' type",
        "Ensure all exports have explicit types",
        "Use proper generic types instead of type assertions",
    ]

    hints.avoid_patterns = [
        "// @ts-ignore",
        "// @ts-expect-error",
        "as unknown as",
    ]

    # Suggested approach
    if len(payload.errors_by_file) == 1:
        file = list(payload.errors_by_file.keys())[0]
        hints.suggested_approach = f"All errors in one file ({file}) - fix in order"
    else:
        hints.suggested_approach = (
            "Errors across multiple files - start with the file that has the most errors"
        )

    return hints


def build_hints_for_test_failure(payload) -> PromptHints:
    """Build PromptHints for TEST_FAILED events."""
    from .event_payloads import TestFailurePayload

    if not isinstance(payload, TestFailurePayload):
        return PromptHints()

    hints = PromptHints(priority=HintPriority.HIGH)

    hints.root_cause = f"Test '{payload.test_name}' failed"

    # Add assertion details
    if payload.expected and payload.actual:
        hints.priority_instructions.append(
            f"Expected: {payload.expected}"
        )
        hints.priority_instructions.append(
            f"Actual: {payload.actual}"
        )
        hints.priority_instructions.append(
            "Fix the source code to produce the expected result"
        )

    # Context files
    if payload.test_file:
        hints.context_files.append(payload.test_file)
    hints.context_files.extend(payload.related_source_files)

    # Constraints for test fixes
    hints.constraints = [
        "Do not modify the test expectations unless they are incorrect",
        "Fix the source code, not the test assertions",
    ]

    if payload.is_flaky:
        hints.priority_instructions.append(
            "This test is FLAKY - ensure async operations are properly awaited"
        )
        hints.avoid_patterns.append("setTimeout without await")

    return hints


def build_hints_for_mock_violation(payload) -> PromptHints:
    """Build PromptHints for MOCK_DETECTED events."""
    from .event_payloads import MockViolationPayload

    if not isinstance(payload, MockViolationPayload):
        return PromptHints()

    hints = PromptHints(priority=HintPriority.HIGH)

    hints.root_cause = f"Found {payload.error_count} mock/placeholder violations"

    # Categorized instructions
    if payload.hardcoded_data:
        hints.priority_instructions.append(
            f"Replace {len(payload.hardcoded_data)} hardcoded data values with real implementations"
        )

    if payload.mock_functions:
        hints.priority_instructions.append(
            f"Implement {len(payload.mock_functions)} mock functions with real logic"
        )

    if payload.placeholder_text:
        hints.priority_instructions.append(
            f"Replace {len(payload.placeholder_text)} placeholder texts"
        )

    if payload.todo_comments:
        hints.priority_instructions.append(
            f"Address {len(payload.todo_comments)} TODO comments"
        )

    # Context files
    affected_files = set()
    for v in payload.violations:
        if "file" in v:
            affected_files.add(v["file"])
    hints.context_files = list(affected_files)[:10]

    # Constraints
    hints.constraints = [
        "All data must come from real sources (API, database, user input)",
        "No Lorem Ipsum or placeholder text in production code",
        "No TODO comments - implement the functionality now",
    ]

    hints.avoid_patterns = [
        "Lorem ipsum",
        "TODO:",
        "FIXME:",
        "mock_",
        "placeholder",
        "sample data",
    ]

    return hints


def build_hints_for_e2e_failure(payload) -> PromptHints:
    """Build PromptHints for E2E_TEST_FAILED events."""
    from .event_payloads import E2ETestResultPayload

    if not isinstance(payload, E2ETestResultPayload):
        return PromptHints()

    hints = PromptHints(priority=HintPriority.HIGH)

    hints.root_cause = f"E2E test '{payload.test_name}' failed: {payload.error_message}"

    # Add specific failure context
    if payload.failing_step:
        hints.priority_instructions.append(
            f"Failed at step: {payload.failing_step}"
        )

    if payload.element_selector:
        hints.priority_instructions.append(
            f"Could not interact with element: {payload.element_selector}"
        )

    if payload.console_errors:
        hints.priority_instructions.append(
            f"Console errors detected: {payload.console_errors[0]}"
        )

    if payload.network_errors:
        hints.priority_instructions.append(
            f"Network errors: {payload.network_errors[0]}"
        )

    # Context
    if payload.page_url:
        hints.context_files.append(f"Page: {payload.page_url}")

    # Constraints
    hints.constraints = [
        "Ensure all interactive elements have proper test IDs",
        "Wait for elements to be visible before interaction",
        "Handle loading states properly",
    ]

    return hints


def build_hints_for_ux_issue(payload) -> PromptHints:
    """Build PromptHints for UX_ISSUE_FOUND events."""
    from .event_payloads import UXIssuePayload

    if not isinstance(payload, UXIssuePayload):
        return PromptHints()

    # Determine priority based on issue severity
    if payload.critical_count > 0:
        priority = HintPriority.CRITICAL
    elif payload.major_count > 0:
        priority = HintPriority.HIGH
    else:
        priority = HintPriority.MEDIUM

    hints = PromptHints(priority=priority)

    hints.root_cause = (
        f"UX issues found: {payload.critical_count} critical, "
        f"{payload.major_count} major, {payload.minor_count} minor"
    )

    # Add issues as instructions
    for issue in payload.issues[:5]:
        severity = issue.get("severity", "unknown").upper()
        description = issue.get("description", "")
        suggestion = issue.get("suggestion", "")

        hints.priority_instructions.append(
            f"[{severity}] {description}"
        )
        if suggestion:
            hints.priority_instructions.append(f"  → Suggestion: {suggestion}")

    # Constraints
    hints.constraints = [
        "Follow consistent spacing and padding",
        "Ensure text is readable (contrast ratio >= 4.5:1)",
        "Interactive elements must have visible hover states",
    ]

    return hints


# =============================================================================
# Main Builder Function
# =============================================================================

def build_hints_from_event(event: "Event") -> Optional[PromptHints]:
    """
    Build PromptHints from an Event.

    Automatically detects the event type and uses the appropriate builder.
    Returns None if no hints can be built for this event type.
    """
    from .event_bus import EventType
    from .event_payloads import get_typed_payload

    # Get typed payload
    payload = event._typed_payload
    if payload is None and event.data:
        payload = get_typed_payload(event.type, event.data)

    if payload is None:
        return None

    # Map event types to hint builders
    HINT_BUILDERS = {
        EventType.BUILD_FAILED: build_hints_for_build_failure,
        EventType.TYPE_ERROR: build_hints_for_type_error,
        EventType.TEST_FAILED: build_hints_for_test_failure,
        EventType.MOCK_DETECTED: build_hints_for_mock_violation,
        EventType.E2E_TEST_FAILED: build_hints_for_e2e_failure,
        EventType.UX_ISSUE_FOUND: build_hints_for_ux_issue,
    }

    builder = HINT_BUILDERS.get(event.type)
    if builder:
        return builder(payload)

    return None


def merge_hints_from_events(events: list["Event"]) -> PromptHints:
    """
    Merge hints from multiple events into a single PromptHints.

    Useful when fixing multiple issues at once.
    """
    merged = PromptHints()

    for event in events:
        hints = build_hints_from_event(event)
        if hints:
            merged = merged.merge(hints)

    return merged
