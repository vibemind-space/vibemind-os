"""
SmartTestGeneratorAgent - LLM-Powered Intelligent Test Generation.

Uses Claude to:
1. Analyze code to generate comprehensive test cases
2. Identify edge cases, error cases, and boundary conditions
3. Perform test gap analysis to find untested code
4. Prioritize which files need tests most urgently
5. Generate NO-MOCK tests with real integrations

This agent provides intelligent test generation that goes beyond simple templates,
using LLM understanding of code logic to create meaningful tests.
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
class TestCase:
    """A single generated test case."""
    name: str
    description: str
    code: str
    category: str = "unit"  # unit, integration, e2e
    covers: list[str] = field(default_factory=list)  # Functions/methods covered


@dataclass
class TestGenerationResult:
    """Result of LLM test generation."""
    target_file: str
    test_file: str
    test_cases: list[TestCase] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    setup_code: str = ""
    teardown_code: str = ""


@dataclass
class TestGapAnalysis:
    """Result of test gap analysis."""
    untested_files: list[str] = field(default_factory=list)
    priority_files: list[dict] = field(default_factory=list)  # {file, reason, risk}
    coverage_estimate: float = 0.0


class SmartTestGeneratorAgent(AutonomousAgent):
    """
    LLM-powered autonomous agent for intelligent test generation.

    Uses Claude to:
    1. Analyze source code to understand logic and edge cases
    2. Generate comprehensive test cases (happy path, edge, error)
    3. Identify files that need tests most urgently
    4. Create NO-MOCK tests with real implementations
    5. Generate integration tests for critical paths

    Publishes TESTS_GENERATED event with test code for ValidationTeamAgent.
    """

    COOLDOWN_SECONDS = 30.0  # Test generation is expensive

    def __init__(
        self,
        name: str = "SmartTestGeneratorAgent",
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
        self._generated_for: set[str] = set()  # Track files we've generated tests for
        self.logger = logger.bind(agent=name)

        self.logger.info(
            "smart_test_generator_initialized",
            working_dir=working_dir,
            subscribed_events=[e.value for e in self.subscribed_events],
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.CODE_GENERATED,
            EventType.GENERATION_COMPLETE,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Determine if we should generate tests for any of these events."""
        for event in events:
            # Only act on successful builds or completed generation
            if event.type == EventType.BUILD_SUCCEEDED:
                return True

            if event.type == EventType.GENERATION_COMPLETE:
                return True

            if event.type == EventType.CODE_GENERATED:
                # Check if it's a new file that needs tests
                file_path = event.data.get("file_path", "") if event.data else ""
                if file_path and file_path not in self._generated_for:
                    # Only generate for source files, not test files
                    if not file_path.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx")):
                        return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Generate tests based on the events."""
        # Find the first relevant event
        event = None
        for e in events:
            if e.type in self.subscribed_events:
                event = e
                break

        if not event:
            return

        self.logger.info(
            "generating_tests",
            event_type=event.type.value,
            project_id=event.data.get("project_id") if event.data else None,
        )

        try:
            if event.type == EventType.CODE_GENERATED:
                # Generate tests for specific file
                file_path = event.data.get("file_path", "") if event.data else ""
                if file_path:
                    await self._generate_tests_for_file(file_path, event)
            else:
                # Perform gap analysis and generate priority tests
                await self._analyze_and_generate_priority_tests(event)

        except Exception as e:
            self.logger.error("test_generation_failed", error=str(e))

    async def _generate_tests_for_file(self, file_path: str, event: Event) -> None:
        """Generate tests for a specific file."""
        working_path = Path(self.working_dir)
        full_path = working_path / file_path

        if not full_path.exists():
            self.logger.warning("file_not_found", file_path=file_path)
            return

        # Skip if already generated
        if file_path in self._generated_for:
            return
        self._generated_for.add(file_path)

        # Read file content
        code_content = full_path.read_text(encoding='utf-8', errors='ignore')

        # Generate tests using LLM
        result = await self._llm_generate_tests(file_path, code_content)

        if result and result.test_cases:
            # Write test file
            test_file_path = self._get_test_file_path(file_path)
            await self._write_test_file(test_file_path, result)

            # Publish event
            await self.event_bus.publish(Event(
                type=EventType.FILE_CREATED,
                source=self.name,
                data={
                    "file_path": test_file_path,
                    "project_id": event.data.get("project_id"),
                    "test_count": len(result.test_cases),
                    "categories": list(set(tc.category for tc in result.test_cases)),
                }
            ))

            self.logger.info(
                "tests_generated",
                target_file=file_path,
                test_file=test_file_path,
                test_count=len(result.test_cases),
            )

    async def _analyze_and_generate_priority_tests(self, event: Event) -> None:
        """Analyze test gaps and generate tests for priority files."""
        # Find source and test files
        working_path = Path(self.working_dir)

        source_files = []
        test_files = []

        for pattern in ["src/**/*.ts", "src/**/*.tsx", "lib/**/*.ts"]:
            for f in working_path.glob(pattern):
                if f.is_file():
                    rel_path = str(f.relative_to(working_path))
                    if ".test." in rel_path or ".spec." in rel_path:
                        test_files.append(rel_path)
                    else:
                        source_files.append(rel_path)

        # Perform gap analysis
        gap_analysis = await self._analyze_test_gaps(source_files, test_files)

        if gap_analysis and gap_analysis.priority_files:
            self.logger.info(
                "gap_analysis_complete",
                untested_count=len(gap_analysis.untested_files),
                priority_count=len(gap_analysis.priority_files),
            )

            # Generate tests for top priority files (limit to 3)
            for priority_file in gap_analysis.priority_files[:3]:
                file_path = priority_file.get("file", "")
                if file_path and file_path not in self._generated_for:
                    await self._generate_tests_for_file(file_path, event)

    async def _llm_generate_tests(
        self, file_path: str, code_content: str
    ) -> Optional[TestGenerationResult]:
        """Use LLM to generate comprehensive tests for a file."""

        prompt = f"""Analyze this code and generate comprehensive tests.

## FILE: {file_path}

## CODE:
```typescript
{code_content[:4000]}
```

## REQUIREMENTS:

Generate tests that cover:
1. **Happy Path**: Normal, expected usage
2. **Edge Cases**: Empty input, null, undefined, max/min values
3. **Error Cases**: Invalid input, exceptions, error handling
4. **Boundary Conditions**: Array bounds, string limits, numeric limits

## CRITICAL RULES:
- Use Vitest/Jest syntax
- **NO MOCKS** - Use real implementations
- Test actual behavior, not implementation details
- Include integration tests where appropriate
- Each test should be independent

Respond with test code in this format:
```typescript
import {{ describe, it, expect, beforeEach, afterEach }} from 'vitest';
// ... other imports

describe('{file_path}', () => {{
  // Setup if needed
  beforeEach(() => {{
    // ...
  }});

  describe('functionName', () => {{
    it('should handle normal case', () => {{
      // Test code
    }});

    it('should handle edge case: empty input', () => {{
      // Test code
    }});

    it('should handle error case: invalid input', () => {{
      // Test code
    }});
  }});
}});
```

Also provide a JSON summary after the code:
```json
{{
    "test_file": "path/to/file.test.ts",
    "test_count": 5,
    "categories": ["unit", "integration"],
    "covered_functions": ["func1", "func2"]
}}
```
"""

        try:
            result = await self.claude_tool.execute(
                prompt=prompt,
                agent_type="test-generation",
            )

            # Extract the output string from CodeGenerationResult
            output_text = result.output if hasattr(result, 'output') else str(result)

            # Extract test code
            code_match = re.search(r'```typescript\s*(.*?)\s*```', output_text, re.DOTALL)
            if not code_match:
                code_match = re.search(r'```ts\s*(.*?)\s*```', output_text, re.DOTALL)

            if code_match:
                test_code = code_match.group(1)

                # Parse imports from test code
                imports = re.findall(r"^import\s+.*?;$", test_code, re.MULTILINE)

                # Extract test cases from describe/it blocks
                test_cases = []
                it_pattern = r"it\s*\(\s*['\"]([^'\"]+)['\"]"
                for match in re.finditer(it_pattern, test_code):
                    test_cases.append(TestCase(
                        name=match.group(1),
                        description=match.group(1),
                        code=test_code,  # Full code for now
                        category="unit",
                    ))

                test_file_path = self._get_test_file_path(file_path)

                return TestGenerationResult(
                    target_file=file_path,
                    test_file=test_file_path,
                    test_cases=test_cases,
                    imports=imports,
                )
            else:
                self.logger.warning("no_test_code_in_response")
                return None

        except Exception as e:
            self.logger.error("llm_test_generation_failed", error=str(e))
            return None

    async def _analyze_test_gaps(
        self, source_files: list[str], test_files: list[str]
    ) -> Optional[TestGapAnalysis]:
        """Use LLM to analyze which files need tests most urgently."""

        # Find tested files by parsing test imports
        tested_files = set()
        working_path = Path(self.working_dir)

        for test_file in test_files:
            try:
                content = (working_path / test_file).read_text(encoding='utf-8', errors='ignore')
                # Extract imported source files
                for match in re.finditer(r"from\s+['\"]([^'\"]+)['\"]", content):
                    import_path = match.group(1)
                    if import_path.startswith("."):
                        # Resolve relative import
                        test_dir = Path(test_file).parent
                        resolved = (test_dir / import_path).as_posix()
                        # Normalize
                        for ext in [".ts", ".tsx", ""]:
                            candidate = resolved + ext
                            if candidate in source_files:
                                tested_files.add(candidate)
            except Exception:
                pass

        # Find untested files
        untested = [f for f in source_files if f not in tested_files]

        if not untested:
            return TestGapAnalysis(coverage_estimate=100.0)

        # Use LLM to prioritize
        prompt = f"""Analyze these untested files and prioritize which need tests most urgently.

## UNTESTED FILES:
{chr(10).join(untested[:20])}

## PRIORITIZATION CRITERIA:
1. **Risk**: Auth, payment, data handling = critical
2. **Complexity**: More logic = more tests needed
3. **Usage**: Heavily imported = high impact

Return the top 5 priority files with reasoning in this JSON format:
```json
{{
    "priority_files": [
        {{"file": "path/to/file.ts", "reason": "Critical auth logic", "risk": "high"}},
        {{"file": "path/to/file.ts", "reason": "Complex data processing", "risk": "medium"}}
    ],
    "coverage_estimate": 45.5
}}
```
"""

        try:
            result = await self.claude_tool.execute(
                prompt=prompt,
                agent_type="test-generation",
            )

            # Extract the output string from CodeGenerationResult
            output_text = result.output if hasattr(result, 'output') else str(result)

            json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL)
            if json_match:
                analysis_data = json.loads(json_match.group(1))
                return TestGapAnalysis(
                    untested_files=untested,
                    priority_files=analysis_data.get("priority_files", []),
                    coverage_estimate=analysis_data.get("coverage_estimate", 0.0),
                )

        except Exception as e:
            self.logger.error("gap_analysis_failed", error=str(e))

        # Fallback: return simple analysis
        return TestGapAnalysis(
            untested_files=untested,
            priority_files=[{"file": f, "reason": "No tests", "risk": "unknown"} for f in untested[:5]],
            coverage_estimate=len(tested_files) / len(source_files) * 100 if source_files else 0,
        )

    def _get_test_file_path(self, source_file: str) -> str:
        """Generate test file path from source file path."""
        path = Path(source_file)

        # Replace .ts/.tsx with .test.ts/.test.tsx
        if path.suffix == ".tsx":
            test_name = path.stem + ".test.tsx"
        else:
            test_name = path.stem + ".test.ts"

        # Put in same directory or __tests__ directory
        return str(path.parent / test_name)

    async def _write_test_file(self, test_file_path: str, result: TestGenerationResult) -> None:
        """Write generated tests to file."""
        working_path = Path(self.working_dir)
        full_path = working_path / test_file_path

        # Ensure directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Combine all test code
        test_content = []

        # Add imports
        test_content.append("import { describe, it, expect, beforeEach, afterEach } from 'vitest';")
        for imp in result.imports:
            if imp not in test_content:
                test_content.append(imp)
        test_content.append("")

        # Add setup if needed
        if result.setup_code:
            test_content.append(result.setup_code)
            test_content.append("")

        # Add test cases (using the first one's full code since they all contain the same)
        if result.test_cases:
            # Extract just the describe blocks (not imports)
            full_code = result.test_cases[0].code
            # Remove imports from beginning
            describe_start = full_code.find("describe(")
            if describe_start > 0:
                test_content.append(full_code[describe_start:])
            else:
                test_content.append(full_code)

        full_path.write_text("\n".join(test_content))
