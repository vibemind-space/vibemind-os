"""
ErrorContextAgent - LLM-Powered Cross-File Error Tracing.

Uses Claude to:
1. Trace errors across multiple files to find root cause
2. Follow import chains to identify missing exports
3. Track data flow to find where undefined values originate
4. Suggest fixes in the correct file (not just where error appears)
5. Understand type mismatches across interfaces

This agent provides intelligent error diagnosis that goes beyond the symptom
to find the actual root cause, even when it's in a different file.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType
from src.tools.claude_code_tool import ClaudeCodeTool


logger = structlog.get_logger(__name__)


@dataclass
class ErrorTrace:
    """Result of LLM error tracing analysis."""
    symptom_file: str
    symptom_line: int
    symptom_message: str
    root_cause_file: Optional[str] = None
    root_cause_line: Optional[int] = None
    explanation: str = ""
    fix_location: Optional[str] = None
    fix_description: str = ""
    fix_code: str = ""
    related_files: list[str] = field(default_factory=list)
    trace_path: list[str] = field(default_factory=list)  # File chain from symptom to root


class ErrorContextAgent(AutonomousAgent):
    """
    LLM-powered autonomous agent for tracing errors across files.

    Uses Claude to:
    1. Parse error messages to extract file, line, and context
    2. Follow import chains to find missing exports
    3. Track data flow to identify where undefined values originate
    4. Compare interfaces/types to find type mismatches
    5. Suggest fixes in the correct file (root cause, not symptom)

    Publishes ERROR_CONTEXT_ANALYZED event with trace for GeneratorAgent.
    """

    COOLDOWN_SECONDS = 5.0  # Allow rapid tracing

    # Error patterns that benefit from cross-file tracing
    TRACEABLE_ERROR_PATTERNS = [
        (r"Cannot read propert.*of undefined", "undefined_access"),
        (r"Cannot read propert.*of null", "null_access"),
        (r"is not a function", "missing_function"),
        (r"Module not found", "import_error"),
        (r"Cannot find module", "import_error"),
        (r"has no exported member", "export_error"),
        (r"is not assignable to type", "type_mismatch"),
        (r"Property .* does not exist", "missing_property"),
        (r"Argument of type .* is not assignable", "type_mismatch"),
        (r"Expected \d+ arguments, but got \d+", "argument_count"),
        (r"Object is possibly 'undefined'", "undefined_check"),
        (r"Object is possibly 'null'", "null_check"),
    ]

    def __init__(
        self,
        name: str = "ErrorContextAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.claude_tool = ClaudeCodeTool(working_dir=working_dir)
        self._traced_errors: set[str] = set()  # Track already traced errors
        self.logger = logger.bind(agent=name)

        self.logger.info(
            "error_context_agent_initialized",
            working_dir=working_dir,
            subscribed_events=[e.value for e in self.subscribed_events],
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.BUILD_FAILED,
            EventType.SANDBOX_TEST_FAILED,
            EventType.BROWSER_ERROR,
            EventType.TYPE_ERROR,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Determine if any error would benefit from cross-file tracing."""
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Get error content
            error_content = ""
            if event.data:
                error_content = str(event.data.get("build_output", "")) + str(event.data.get("error", ""))

            if not error_content:
                continue

            # Check if it's a traceable error pattern
            for pattern, error_type in self.TRACEABLE_ERROR_PATTERNS:
                if re.search(pattern, error_content, re.IGNORECASE):
                    # Create hash to avoid re-tracing same error
                    error_hash = hash(error_content[:500])
                    if error_hash in self._traced_errors:
                        self.logger.debug("error_already_traced", hash=error_hash)
                        continue
                    self._traced_errors.add(error_hash)
                    return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Trace error across files using LLM."""
        # Find the first matching event
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self.logger.info(
            "tracing_error_context",
            event_type=event.type.value,
            project_id=event.data.get("project_id") if event.data else None,
        )

        try:
            # Extract error information
            error_output = ""
            errors = []
            if event.data:
                error_output = event.data.get("build_output", "") or event.data.get("error", "")
                errors = event.data.get("errors", [])

            # Parse first error for file/line info
            symptom_file, symptom_line, symptom_message = self._parse_error_location(
                error_output, errors
            )

            if not symptom_file:
                self.logger.warning("could_not_parse_error_location")
                return

            # Load related files (imports, exports, usages)
            related_files = await self._find_related_files(symptom_file)
            context = await self._load_file_contents([symptom_file] + related_files)

            # Perform LLM tracing
            trace = await self._trace_error_to_root_cause(
                symptom_file=symptom_file,
                symptom_line=symptom_line,
                symptom_message=symptom_message,
                context=context,
            )

            if trace:
                self.logger.info(
                    "trace_complete",
                    symptom_file=trace.symptom_file,
                    root_cause_file=trace.root_cause_file,
                    fix_location=trace.fix_location,
                )

                # Publish trace for GeneratorAgent
                await self.event_bus.publish(Event(
                    type=EventType.DOCUMENT_CREATED,
                    source=self.name,
                    data={
                        "document_type": "error_trace",
                        "project_id": event.data.get("project_id"),
                        "trace": {
                            "symptom_file": trace.symptom_file,
                            "symptom_line": trace.symptom_line,
                            "symptom_message": trace.symptom_message,
                            "root_cause_file": trace.root_cause_file,
                            "root_cause_line": trace.root_cause_line,
                            "explanation": trace.explanation,
                            "fix_location": trace.fix_location,
                            "fix_description": trace.fix_description,
                            "fix_code": trace.fix_code,
                            "related_files": trace.related_files,
                            "trace_path": trace.trace_path,
                        },
                        "original_error": error_output[:1000],
                    }
                ))

                # Update shared state
                if self.shared_state:
                    self.shared_state.set(
                        f"error_trace_{event.data.get('project_id', 'default')}",
                        trace.__dict__
                    )

        except Exception as e:
            self.logger.error("tracing_failed", error=str(e))

    def _parse_error_location(
        self, error_output: str, errors: list[dict]
    ) -> tuple[Optional[str], int, str]:
        """Extract file, line, and message from error output."""
        # Try structured errors first
        if errors and len(errors) > 0:
            first_error = errors[0]
            return (
                first_error.get("file"),
                first_error.get("line", 0),
                first_error.get("message", ""),
            )

        # Parse from text output
        # Pattern: filename.ts:line:col - message
        patterns = [
            r"([^\s:]+\.[tj]sx?):(\d+)(?::\d+)?.*?(?:error|Error|ERROR)[:\s]*(.+)",
            r"at\s+.*?\(([^\s:]+\.[tj]sx?):(\d+):\d+\)",  # Stack trace
            r"Error:.*?in\s+([^\s:]+\.[tj]sx?):(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_output)
            if match:
                groups = match.groups()
                return (
                    groups[0],
                    int(groups[1]) if len(groups) > 1 else 0,
                    groups[2] if len(groups) > 2 else "",
                )

        return None, 0, error_output[:200]

    async def _find_related_files(self, source_file: str) -> list[str]:
        """Find files related to the source file (imports, exports)."""
        related = []
        working_path = Path(self.working_dir)
        source_path = working_path / source_file

        if not source_path.exists():
            return related

        try:
            content = source_path.read_text()

            # Extract imports
            import_patterns = [
                r"import\s+.*?from\s+['\"]([^'\"]+)['\"]",
                r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            ]

            for pattern in import_patterns:
                for match in re.finditer(pattern, content):
                    import_path = match.group(1)

                    # Resolve relative imports
                    if import_path.startswith("."):
                        resolved = (source_path.parent / import_path).resolve()

                        # Try with extensions
                        for ext in ["", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx"]:
                            test_path = Path(str(resolved) + ext)
                            if test_path.exists():
                                rel_path = test_path.relative_to(working_path)
                                if str(rel_path) not in related:
                                    related.append(str(rel_path))
                                break

            # Limit to prevent token overflow
            return related[:5]

        except Exception as e:
            self.logger.warning("failed_to_find_related_files", error=str(e))
            return []

    async def _load_file_contents(self, files: list[str]) -> str:
        """Load contents of multiple files."""
        content = ""
        working_path = Path(self.working_dir)

        for file_path in files[:5]:  # Limit to 5 files
            full_path = working_path / file_path
            if full_path.exists():
                try:
                    file_content = full_path.read_text()
                    # Truncate large files
                    if len(file_content) > 2000:
                        file_content = file_content[:2000] + "\n... (truncated)"
                    content += f"\n=== FILE: {file_path} ===\n{file_content}\n"
                except Exception:
                    pass

        return content

    async def _trace_error_to_root_cause(
        self,
        symptom_file: str,
        symptom_line: int,
        symptom_message: str,
        context: str,
    ) -> Optional[ErrorTrace]:
        """Use LLM to trace error to its root cause."""

        prompt = f"""Trace this error to its root cause across files.

## ERROR SYMPTOM:
- **File**: {symptom_file}
- **Line**: {symptom_line}
- **Message**: {symptom_message}

## CODE CONTEXT:
{context[:6000]}

## ANALYSIS REQUIRED:

Trace this error back to its root cause. The error might appear in one file,
but the actual problem could be in a different file (missing export, incorrect type,
data not passed correctly, etc.).

Questions to answer:
1. Where does the error appear (symptom)?
2. Where does the problem actually originate (root cause)?
3. What is the chain of files/imports from root to symptom?
4. Which file should be modified to fix this?
5. What is the exact fix needed?

Respond in this exact JSON format:
```json
{{
    "symptom_file": "path/to/file.ts",
    "symptom_line": 42,
    "symptom_message": "Original error message",
    "root_cause_file": "path/to/actual/problem.ts",
    "root_cause_line": 15,
    "explanation": "Clear explanation of why this happened",
    "fix_location": "path/to/file/to/modify.ts",
    "fix_description": "What change needs to be made",
    "fix_code": "The actual code to add/change",
    "related_files": ["file1.ts", "file2.ts"],
    "trace_path": ["symptom.ts", "intermediate.ts", "root.ts"]
}}
```
"""

        try:
            result = await self.claude_tool.execute(
                prompt=prompt,
                skill="debugging",
                skill_tier="standard",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                trace_data = json.loads(json_match.group(1))
                return ErrorTrace(
                    symptom_file=trace_data.get("symptom_file", symptom_file),
                    symptom_line=trace_data.get("symptom_line", symptom_line),
                    symptom_message=trace_data.get("symptom_message", symptom_message),
                    root_cause_file=trace_data.get("root_cause_file"),
                    root_cause_line=trace_data.get("root_cause_line"),
                    explanation=trace_data.get("explanation", ""),
                    fix_location=trace_data.get("fix_location"),
                    fix_description=trace_data.get("fix_description", ""),
                    fix_code=trace_data.get("fix_code", ""),
                    related_files=trace_data.get("related_files", []),
                    trace_path=trace_data.get("trace_path", []),
                )
            else:
                self.logger.warning("json_parse_failed_using_fallback")
                return ErrorTrace(
                    symptom_file=symptom_file,
                    symptom_line=symptom_line,
                    symptom_message=symptom_message,
                    explanation=f"LLM analysis: {result[:500]}",
                    fix_description="Review the error and related files manually",
                )

        except Exception as e:
            self.logger.error("llm_tracing_failed", error=str(e))
            return None
