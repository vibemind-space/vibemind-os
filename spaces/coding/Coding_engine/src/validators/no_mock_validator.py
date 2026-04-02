"""
No-Mock Validator - Detects and blocks mock implementations.

This validator ensures that generated code uses real database connections,
actual API calls, and genuine authentication - no hardcoded data arrays,
fake responses, or placeholder implementations.

CRITICAL: Mocks destroy autonomy. A system that generates mocks is not
truly autonomous - it's just creating illusions of functionality.
"""

import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from .base_validator import (
    BaseValidator,
    ValidationResult,
    ValidationFailure,
    ValidationSeverity,
)


@dataclass
class MockViolation:
    """Represents a detected mock pattern violation."""
    file_path: str
    pattern_name: str
    pattern: str
    match_text: str
    line_number: int
    severity: str = "error"
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "pattern_name": self.pattern_name,
            "pattern": self.pattern,
            "match_text": self.match_text[:200],  # Truncate for readability
            "line_number": self.line_number,
            "severity": self.severity,
            "suggested_fix": self.suggested_fix,
        }


# Mock patterns to detect - each is a tuple of (name, pattern, severity, suggested_fix)
MOCK_PATTERNS: list[tuple[str, str, str, str]] = [
    # Hardcoded data arrays as "database"
    (
        "hardcoded_data_array",
        r"const\s+\w+\s*=\s*\[\s*\{[^}]*id\s*:",
        "error",
        "Replace hardcoded array with Prisma/database query: const users = await prisma.user.findMany()"
    ),
    (
        "hardcoded_users_array",
        r"(const|let|var)\s+(users|posts|items|products|orders)\s*=\s*\[",
        "error",
        "Replace with database query instead of hardcoded array"
    ),

    # TODO/FIXME placeholders for real logic
    (
        "todo_implement",
        r"//\s*TODO:?\s*(implement|add|fix|complete)",
        "error",
        "Remove TODO and implement the actual functionality"
    ),
    (
        "fixme_placeholder",
        r"//\s*FIXME:?\s*(implement|add|later)",
        "error",
        "Remove FIXME and implement the actual functionality"
    ),

    # Fake success returns without logic
    (
        "fake_success_return",
        r"return\s*\{\s*success\s*:\s*true\s*\}",
        "warning",
        "Ensure success is based on actual operation result, not hardcoded"
    ),

    # Mock/Fake/Dummy imports
    (
        "mock_import",
        r"from\s+['\"].*mock['\"]",
        "error",
        "Remove mock imports and use real implementations"
    ),
    (
        "fake_import",
        r"import\s+.*\b(mock|fake|stub)\b",
        "error",
        "Remove fake/stub imports and use real implementations"
    ),

    # Hardcoded test IDs
    (
        "hardcoded_test_id",
        r"id\s*:\s*['\"]?(mock|fake|test|dummy|sample)[_-]?\d*['\"]?",
        "error",
        "Use real database-generated IDs instead of hardcoded values"
    ),

    # Empty async functions (stubs)
    (
        "empty_async_function",
        r"async\s+function\s+\w+\s*\([^)]*\)\s*\{\s*\}",
        "error",
        "Implement the actual async function logic"
    ),
    (
        "empty_arrow_async",
        r"=\s*async\s*\([^)]*\)\s*=>\s*\{\s*\}",
        "error",
        "Implement the actual async arrow function logic"
    ),

    # Placeholder responses
    (
        "not_implemented_return",
        r"return\s+['\"]Not implemented['\"]",
        "error",
        "Implement the actual functionality instead of returning placeholder"
    ),
    (
        "todo_response",
        r"return\s+['\"]TODO['\"]",
        "error",
        "Implement the actual functionality instead of returning TODO"
    ),

    # In-memory Map/Object as database substitute
    (
        "in_memory_map",
        r"const\s+\w+Map\s*=\s*new\s+Map\s*\(\s*\)",
        "warning",
        "Consider using a real database instead of in-memory Map"
    ),
    (
        "in_memory_store",
        r"const\s+\w+Store\s*=\s*\{\s*\}",
        "warning",
        "Consider using a real database instead of in-memory object store"
    ),

    # Fake tokens/secrets
    (
        "fake_jwt_token",
        r"['\"]eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*['\"]",
        "error",
        "Use jwt.sign() to generate real tokens, not hardcoded JWTs"
    ),
    (
        "fake_api_key",
        r"api[_-]?key\s*[:=]\s*['\"](?:test|fake|mock|demo|sample)[_-]?",
        "error",
        "Use environment variables for API keys: process.env.API_KEY"
    ),

    # Fake/mock password verification
    (
        "fake_password_check",
        r"(verifyPassword|checkPassword|comparePassword)\s*\([^)]*\)\s*\{?\s*return\s+true",
        "error",
        "Use bcrypt.compare() for real password verification"
    ),

    # setTimeout as database delay simulation
    (
        "simulated_db_delay",
        r"await\s+new\s+Promise\s*\(\s*resolve\s*=>\s*setTimeout",
        "warning",
        "Remove simulated delays - use real database operations"
    ),

    # Console.log with "mock" or "fake" mentions
    (
        "mock_console_log",
        r"console\.log\s*\(\s*['\"].*\b(mock|fake|simulating)\b",
        "warning",
        "Remove mock logging - implement real functionality"
    ),

    # Static JSON file as database
    (
        "json_file_database",
        r"(readFileSync|readFile)\s*\([^)]*\.(json)['\"]",
        "warning",
        "Consider using a real database instead of JSON files for data storage"
    ),

    # Hardcoded credentials
    (
        "hardcoded_password",
        r"password\s*[:=]\s*['\"](?!process\.env)\w+['\"]",
        "error",
        "Use environment variables for passwords: process.env.DB_PASSWORD"
    ),
    (
        "hardcoded_secret",
        r"secret\s*[:=]\s*['\"](?!process\.env)[a-zA-Z0-9]+['\"]",
        "error",
        "Use environment variables for secrets: process.env.JWT_SECRET"
    ),
]

# File patterns to scan
SCAN_FILE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx",  # TypeScript/JavaScript
    ".py",                          # Python
    ".vue",                         # Vue
}

# Directories to skip
SKIP_DIRECTORIES = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "__pycache__",
    "coverage",
    ".pytest_cache",
    "venv",
    ".venv",
}

# Files to skip (test files are allowed to have mocks in production code validation)
SKIP_FILE_PATTERNS = [
    r".*\.test\.(ts|tsx|js|jsx)$",
    r".*\.spec\.(ts|tsx|js|jsx)$",
    r".*_test\.py$",
    r"test_.*\.py$",
    r".*\.mock\.(ts|tsx|js|jsx)$",
    r"__mocks__/.*",
    r".*\.stories\.(ts|tsx|js|jsx)$",  # Storybook stories can have mocks
]

# Test file patterns (for validating tests have NO MOCKS)
TEST_FILE_PATTERNS = [
    r".*\.test\.(ts|tsx|js|jsx)$",
    r".*\.spec\.(ts|tsx|js|jsx)$",
    r".*_test\.py$",
    r"test_.*\.py$",
]

# Test-specific mock patterns - detect mocking in test files
# Phase 3: NO MOCKS policy - all tests must be real integration tests
TEST_MOCK_PATTERNS: list[tuple[str, str, str, str]] = [
    # Python unittest.mock patterns
    (
        "unittest_mock_import",
        r"from\s+unittest\.mock\s+import",
        "error",
        "Use real implementations instead of unittest.mock"
    ),
    (
        "unittest_mock_module",
        r"from\s+unittest\s+import\s+mock",
        "error",
        "Use real implementations instead of unittest.mock"
    ),
    (
        "mock_patch_decorator",
        r"@patch\s*\(",
        "error",
        "Remove @patch - test against real implementation"
    ),
    (
        "mock_patch_context",
        r"with\s+patch\s*\(",
        "error",
        "Remove patch() context - test against real implementation"
    ),
    (
        "mock_class_usage",
        r"\bMock\s*\(",
        "error",
        "Remove Mock() - use real objects"
    ),
    (
        "magic_mock_usage",
        r"\bMagicMock\s*\(",
        "error",
        "Remove MagicMock() - use real objects"
    ),
    (
        "async_mock_usage",
        r"\bAsyncMock\s*\(",
        "error",
        "Remove AsyncMock() - use real async implementations"
    ),
    (
        "pytest_mock_fixture",
        r"\bmocker\s*\.",
        "error",
        "Remove pytest-mock mocker fixture - use real implementations"
    ),
    (
        "mock_return_value",
        r"\.return_value\s*=",
        "error",
        "Remove return_value assignment - use real return values"
    ),
    (
        "mock_side_effect",
        r"\.side_effect\s*=",
        "error",
        "Remove side_effect assignment - use real behavior"
    ),
    (
        "create_autospec",
        r"create_autospec\s*\(",
        "error",
        "Remove create_autospec() - use real objects"
    ),

    # JavaScript/TypeScript Jest patterns
    (
        "jest_mock",
        r"jest\.mock\s*\(",
        "error",
        "Remove jest.mock() - test against real modules"
    ),
    (
        "jest_fn",
        r"jest\.fn\s*\(",
        "error",
        "Remove jest.fn() - use real functions"
    ),
    (
        "jest_spyon",
        r"jest\.spyOn\s*\(",
        "error",
        "Remove jest.spyOn() - test real behavior"
    ),
    (
        "jest_mock_implementation",
        r"\.mockImplementation\s*\(",
        "error",
        "Remove mockImplementation() - use real implementation"
    ),
    (
        "jest_mock_return",
        r"\.mockReturnValue\s*\(",
        "error",
        "Remove mockReturnValue() - use real values"
    ),
    (
        "jest_mock_resolved",
        r"\.mockResolvedValue\s*\(",
        "error",
        "Remove mockResolvedValue() - use real async values"
    ),
    (
        "jest_mock_rejected",
        r"\.mockRejectedValue\s*\(",
        "error",
        "Remove mockRejectedValue() - use real error handling"
    ),

    # Vitest patterns
    (
        "vitest_mock",
        r"vi\.mock\s*\(",
        "error",
        "Remove vi.mock() - test against real modules"
    ),
    (
        "vitest_fn",
        r"vi\.fn\s*\(",
        "error",
        "Remove vi.fn() - use real functions"
    ),
    (
        "vitest_spyon",
        r"vi\.spyOn\s*\(",
        "error",
        "Remove vi.spyOn() - test real behavior"
    ),
    (
        "vitest_stubenv",
        r"vi\.stubEnv\s*\(",
        "error",
        "Remove vi.stubEnv() - use real environment variables"
    ),

    # Sinon patterns
    (
        "sinon_stub",
        r"sinon\.stub\s*\(",
        "error",
        "Remove sinon.stub() - use real implementation"
    ),
    (
        "sinon_mock",
        r"sinon\.mock\s*\(",
        "error",
        "Remove sinon.mock() - use real implementation"
    ),
    (
        "sinon_fake",
        r"sinon\.fake\s*\(",
        "error",
        "Remove sinon.fake() - use real implementation"
    ),
    (
        "sinon_spy",
        r"sinon\.spy\s*\(",
        "error",
        "Remove sinon.spy() - test real behavior"
    ),
    (
        "sinon_import",
        r"import\s+.*\bsinon\b",
        "error",
        "Remove sinon import - use real implementations"
    ),

    # HTTP mocking libraries
    (
        "nock_mock",
        r"nock\s*\(",
        "error",
        "Remove nock() - use real HTTP calls or test server"
    ),
    (
        "msw_import",
        r"from\s+['\"]msw['\"]",
        "error",
        "Remove MSW import - use real API or test server"
    ),
    (
        "fetch_mock",
        r"fetchMock\b",
        "error",
        "Remove fetch-mock - use real fetch calls"
    ),
    (
        "axios_mock",
        r"MockAdapter\s*\(",
        "error",
        "Remove axios MockAdapter - use real HTTP calls"
    ),
    (
        "responses_decorator",
        r"@responses\.activate",
        "error",
        "Remove responses decorator - use real HTTP calls"
    ),

    # pytest-httpx and similar
    (
        "httpx_mock",
        r"httpx_mock\b",
        "error",
        "Remove httpx_mock - use real HTTP calls"
    ),
    (
        "aioresponses",
        r"aioresponses\b",
        "error",
        "Remove aioresponses - use real async HTTP"
    ),

    # Generic mock/stub/fake patterns
    (
        "generic_mock_class",
        r"class\s+Mock\w+",
        "warning",
        "Consider using real implementation instead of Mock class"
    ),
    (
        "generic_fake_class",
        r"class\s+Fake\w+",
        "warning",
        "Consider using real implementation instead of Fake class"
    ),
    (
        "generic_stub_class",
        r"class\s+Stub\w+",
        "warning",
        "Consider using real implementation instead of Stub class"
    ),
]


class NoMockValidator(BaseValidator):
    """
    Validator that detects mock patterns in generated code.

    This validator scans all generated source files for patterns that
    indicate mock implementations, hardcoded data, or placeholder code.

    PHILOSOPHY: True autonomy requires real implementations. Mocks are
    acceptable in test files but never in production code.
    """

    def __init__(self, project_dir: str, strict_mode: bool = True):
        """
        Initialize the NoMockValidator.

        Args:
            project_dir: Path to the project to validate
            strict_mode: If True, warnings are treated as errors
        """
        super().__init__(project_dir)
        self.strict_mode = strict_mode
        self._compiled_patterns: list[tuple[str, re.Pattern, str, str]] = []
        self._compiled_skip_patterns: list[re.Pattern] = []
        self._compiled_test_patterns: list[tuple[str, re.Pattern, str, str]] = []
        self._compiled_test_file_patterns: list[re.Pattern] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile all regex patterns for performance."""
        # Production code mock patterns
        for name, pattern, severity, fix in MOCK_PATTERNS:
            try:
                compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                self._compiled_patterns.append((name, compiled, severity, fix))
            except re.error as e:
                print(f"Warning: Invalid regex pattern '{name}': {e}")

        for pattern in SKIP_FILE_PATTERNS:
            try:
                self._compiled_skip_patterns.append(re.compile(pattern))
            except re.error:
                pass

        # Test file mock patterns (Phase 3: NO MOCKS policy)
        for name, pattern, severity, fix in TEST_MOCK_PATTERNS:
            try:
                compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                self._compiled_test_patterns.append((name, compiled, severity, fix))
            except re.error as e:
                print(f"Warning: Invalid test pattern '{name}': {e}")

        for pattern in TEST_FILE_PATTERNS:
            try:
                self._compiled_test_file_patterns.append(re.compile(pattern))
            except re.error:
                pass

    @property
    def name(self) -> str:
        return "No-Mock Validator"

    @property
    def check_type(self) -> str:
        return "no_mock"

    def is_applicable(self) -> bool:
        """Check if project has source files to scan."""
        return self.project_dir.exists() and any(
            self.project_dir.rglob("*.ts")
        ) or any(
            self.project_dir.rglob("*.tsx")
        ) or any(
            self.project_dir.rglob("*.js")
        )

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped (test files, etc.)."""
        # Skip if in excluded directory
        for part in file_path.parts:
            if part in SKIP_DIRECTORIES:
                return True

        # Skip if matches skip pattern
        file_str = str(file_path)
        for pattern in self._compiled_skip_patterns:
            if pattern.search(file_str):
                return True

        return False

    def _should_scan_file(self, file_path: Path) -> bool:
        """Check if file should be scanned based on extension."""
        return file_path.suffix.lower() in SCAN_FILE_EXTENSIONS

    async def validate(self) -> ValidationResult:
        """
        Scan all source files for mock patterns.

        Returns:
            ValidationResult with any mock violations found
        """
        import time
        start_time = time.time()

        result = self._create_result()
        violations: list[MockViolation] = []

        # Recursively scan all source files
        for file_path in self.project_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if not self._should_scan_file(file_path):
                continue
            if self._should_skip_file(file_path):
                continue

            file_violations = await self._scan_file(file_path)
            violations.extend(file_violations)

        # Convert violations to ValidationFailures
        for violation in violations:
            severity = (
                ValidationSeverity.ERROR
                if violation.severity == "error" or self.strict_mode
                else ValidationSeverity.WARNING
            )

            result.add_failure(self._create_failure(
                error_message=f"Mock pattern detected: {violation.pattern_name}",
                severity=severity,
                file_path=str(violation.file_path),
                line_number=violation.line_number,
                error_code=f"MOCK_{violation.pattern_name.upper()}",
                raw_output=f"Matched: {violation.match_text[:100]}...",
                suggested_fix=violation.suggested_fix,
            ))

        result.execution_time_ms = (time.time() - start_time) * 1000

        if result.passed:
            result.checks_passed.append(self.check_type)

        return result

    async def _scan_file(self, file_path: Path) -> list[MockViolation]:
        """
        Scan a single file for mock patterns.

        Args:
            file_path: Path to file to scan

        Returns:
            List of MockViolation objects
        """
        violations: list[MockViolation] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            # Skip files we can't read
            return violations

        lines = content.split("\n")

        for name, pattern, severity, fix in self._compiled_patterns:
            for match in pattern.finditer(content):
                # Find line number
                line_number = content[:match.start()].count("\n") + 1

                violations.append(MockViolation(
                    file_path=str(file_path.relative_to(self.project_dir)),
                    pattern_name=name,
                    pattern=pattern.pattern,
                    match_text=match.group(0),
                    line_number=line_number,
                    severity=severity,
                    suggested_fix=fix,
                ))

        return violations

    async def get_violation_summary(self) -> dict:
        """
        Get a summary of all violations without full details.

        Returns:
            Dictionary with violation counts by type
        """
        result = await self.validate()

        summary = {
            "total_violations": len(result.failures),
            "errors": result.error_count,
            "warnings": result.warning_count,
            "passed": result.passed,
            "violations_by_type": {},
            "violations_by_file": {},
        }

        for failure in result.failures:
            # Count by type
            code = failure.error_code or "UNKNOWN"
            summary["violations_by_type"][code] = \
                summary["violations_by_type"].get(code, 0) + 1

            # Count by file
            file_path = failure.file_path or "unknown"
            summary["violations_by_file"][file_path] = \
                summary["violations_by_file"].get(file_path, 0) + 1

        return summary

    # =========================================================================
    # Phase 3: Test File Mock Validation (NO MOCKS policy)
    # =========================================================================

    def _is_test_file(self, file_path: Path) -> bool:
        """Check if file is a test file based on naming patterns."""
        file_str = str(file_path)
        for pattern in self._compiled_test_file_patterns:
            if pattern.search(file_str):
                return True
        return False

    async def validate_test_files(
        self,
        test_files: Optional[list[Path]] = None,
    ) -> ValidationResult:
        """
        Validate test files for mock usage (Phase 3: NO MOCKS policy).

        This enforces that all generated tests are real integration tests
        without any mocking frameworks.

        Args:
            test_files: Optional list of specific test files to validate.
                       If None, scans all test files in project.

        Returns:
            ValidationResult with any mock violations found
        """
        import time
        start_time = time.time()

        result = self._create_result()
        violations: list[MockViolation] = []

        # Get files to scan
        if test_files:
            files_to_scan = test_files
        else:
            # Find all test files in project
            files_to_scan = []
            for file_path in self.project_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if not self._should_scan_file(file_path):
                    continue
                # Skip excluded directories
                skip = False
                for part in file_path.parts:
                    if part in SKIP_DIRECTORIES:
                        skip = True
                        break
                if skip:
                    continue
                # Only include test files
                if self._is_test_file(file_path):
                    files_to_scan.append(file_path)

        # Scan each test file for mock patterns
        for file_path in files_to_scan:
            file_violations = await self._scan_test_file(file_path)
            violations.extend(file_violations)

        # Convert violations to ValidationFailures
        for violation in violations:
            severity = (
                ValidationSeverity.ERROR
                if violation.severity == "error" or self.strict_mode
                else ValidationSeverity.WARNING
            )

            result.add_failure(self._create_failure(
                error_message=f"Mock detected in test file: {violation.pattern_name}",
                severity=severity,
                file_path=str(violation.file_path),
                line_number=violation.line_number,
                error_code=f"TEST_MOCK_{violation.pattern_name.upper()}",
                raw_output=f"Matched: {violation.match_text[:100]}...",
                suggested_fix=violation.suggested_fix,
            ))

        result.execution_time_ms = (time.time() - start_time) * 1000

        if result.passed:
            result.checks_passed.append("no_mock_tests")

        return result

    async def _scan_test_file(self, file_path: Path) -> list[MockViolation]:
        """
        Scan a test file for mock patterns.

        Uses TEST_MOCK_PATTERNS which specifically target mocking
        frameworks and patterns commonly used in test files.

        Args:
            file_path: Path to test file to scan

        Returns:
            List of MockViolation objects
        """
        violations: list[MockViolation] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return violations

        for name, pattern, severity, fix in self._compiled_test_patterns:
            for match in pattern.finditer(content):
                line_number = content[:match.start()].count("\n") + 1

                try:
                    rel_path = str(file_path.relative_to(self.project_dir))
                except ValueError:
                    rel_path = str(file_path)

                violations.append(MockViolation(
                    file_path=rel_path,
                    pattern_name=name,
                    pattern=pattern.pattern,
                    match_text=match.group(0),
                    line_number=line_number,
                    severity=severity,
                    suggested_fix=fix,
                ))

        return violations

    async def validate_test_files_quick(
        self,
        test_files: list[Path],
    ) -> tuple[bool, list[str]]:
        """
        Quick validation for chunk results - returns simple pass/fail.

        Used by HybridPipeline during parallel code+test generation
        to quickly check if generated tests contain mocks.

        Args:
            test_files: List of test file paths to validate

        Returns:
            Tuple of (passed: bool, violations: list[str])
        """
        result = await self.validate_test_files(test_files)
        violation_messages = [
            f"{f.file_path}:{f.line_number} - {f.error_message}"
            for f in result.failures
        ]
        return result.passed, violation_messages


    # =========================================================================
    # Phase 8: LLM-Enhanced Hidden Mock Detection
    # =========================================================================

    async def detect_hidden_mocks_with_llm(
        self,
        test_code: str,
        file_path: str = "unknown",
    ) -> dict:
        """
        Use LLM to detect subtle mocking patterns that regex can't catch.

        This method detects:
        1. Dependency injection of fake implementations
        2. Hard-coded responses instead of real API calls
        3. Stub objects that mimic real services
        4. Factory functions returning mock data
        5. Test doubles disguised as real implementations

        Args:
            test_code: The test file content to analyze
            file_path: Path to the file (for context)

        Returns:
            Dict with has_mocks, mock_locations, and suggestions
        """
        import json
        import re as regex_module

        # First, run regex-based detection
        regex_violations = []
        for name, pattern, severity, fix in self._compiled_test_patterns:
            for match in pattern.finditer(test_code):
                line_number = test_code[:match.start()].count("\n") + 1
                regex_violations.append({
                    "pattern": name,
                    "line": line_number,
                    "match": match.group(0)[:50],
                })

        # If regex found obvious mocks, return early
        if len(regex_violations) > 5:
            return {
                "has_mocks": True,
                "detection_method": "regex",
                "mock_locations": [
                    f"Line {v['line']}: {v['pattern']} - {v['match']}"
                    for v in regex_violations[:10]
                ],
                "suggestion": "Remove explicit mocking patterns before LLM analysis",
                "confidence": 1.0,
            }

        # Use LLM for semantic analysis of subtle patterns
        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            prompt = f"""Analyze this test file for hidden mocking patterns (we have a strict NO-MOCKS policy):

FILE: {file_path}
CODE:
{test_code[:3000]}

Look for subtle mocking patterns that regex can't catch:

1. **Dependency Injection Fakes**: Classes/functions injected that don't do real work
   - Example: `const fakeDB = {{ query: () => [] }}`
   - Example: `class MockUserService implements UserService {{ ... }}`

2. **Hard-coded Responses**: Functions returning static data instead of calling APIs
   - Example: `const getUsers = () => [{{ id: 1, name: 'Test' }}]`
   - Example: `return Promise.resolve({{ success: true }})`

3. **Stub Objects**: Objects that mimic real services but don't connect
   - Example: `const api = {{ get: async () => testData }}`

4. **Factory Functions**: Helpers that generate fake data for tests
   - Example: `function createFakeUser() {{ return {{ ... }} }}`

5. **Test Doubles**: Real-looking classes that are actually fakes
   - Example: `class TestDatabase extends Database {{ /* empty methods */ }}`

6. **Intercepted Imports**: Dynamic import replacement
   - Example: Reassigning module exports in beforeEach

IMPORTANT: Only flag as mock if it's clearly NOT hitting real systems.
Real integration tests that use test databases or test servers are OK.

Respond with JSON:
```json
{{
  "has_mocks": true/false,
  "mock_locations": [
    "Line X: Description of the mock pattern found"
  ],
  "suggestion": "How to fix the most critical issue",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}}
```
"""

            tool = ClaudeCodeTool(working_dir=str(self.project_dir), timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context="Hidden mock detection analysis",
                agent_type="mock_detector",
            )

            # Parse JSON response
            json_match = regex_module.search(
                r'```json\s*(.*?)\s*```',
                result.output or "",
                regex_module.DOTALL
            )

            if json_match:
                analysis = json.loads(json_match.group(1))

                # Merge with regex results
                all_locations = [
                    f"Line {v['line']}: [REGEX] {v['pattern']}"
                    for v in regex_violations
                ] + analysis.get("mock_locations", [])

                return {
                    "has_mocks": analysis.get("has_mocks", False) or len(regex_violations) > 0,
                    "detection_method": "llm+regex",
                    "mock_locations": all_locations[:15],
                    "suggestion": analysis.get("suggestion", "Review flagged patterns"),
                    "confidence": analysis.get("confidence", 0.5),
                    "reasoning": analysis.get("reasoning", ""),
                    "regex_violations": len(regex_violations),
                    "llm_detected": analysis.get("has_mocks", False),
                }

        except Exception as e:
            # Fall back to regex-only results
            return {
                "has_mocks": len(regex_violations) > 0,
                "detection_method": "regex_fallback",
                "mock_locations": [
                    f"Line {v['line']}: {v['pattern']} - {v['match']}"
                    for v in regex_violations
                ],
                "suggestion": "LLM analysis failed - review regex findings",
                "confidence": 0.7 if regex_violations else 0.3,
                "error": str(e),
            }

    async def validate_with_llm(
        self,
        test_files: list[Path] | None = None,
    ) -> ValidationResult:
        """
        Validate test files using both regex and LLM detection.

        This provides more comprehensive mock detection by combining
        pattern matching with semantic understanding.

        Args:
            test_files: Optional list of test files. If None, scans all.

        Returns:
            ValidationResult with both regex and LLM-detected violations
        """
        import time
        start_time = time.time()

        result = self._create_result()

        # Get files to scan
        if test_files is None:
            test_files = []
            for file_path in self.project_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if not self._should_scan_file(file_path):
                    continue
                skip = False
                for part in file_path.parts:
                    if part in SKIP_DIRECTORIES:
                        skip = True
                        break
                if skip:
                    continue
                if self._is_test_file(file_path):
                    test_files.append(file_path)

        # Analyze each file with LLM
        for file_path in test_files[:20]:  # Limit for performance
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                try:
                    rel_path = str(file_path.relative_to(self.project_dir))
                except ValueError:
                    rel_path = str(file_path)

                analysis = await self.detect_hidden_mocks_with_llm(content, rel_path)

                if analysis.get("has_mocks"):
                    for location in analysis.get("mock_locations", []):
                        # Extract line number if present
                        line_num = 1
                        if location.startswith("Line "):
                            try:
                                line_num = int(location.split(":")[0].replace("Line ", ""))
                            except (ValueError, IndexError):
                                pass

                        result.add_failure(self._create_failure(
                            error_message=f"Hidden mock detected: {location}",
                            severity=ValidationSeverity.ERROR,
                            file_path=rel_path,
                            line_number=line_num,
                            error_code="LLM_HIDDEN_MOCK",
                            raw_output=analysis.get("reasoning", ""),
                            suggested_fix=analysis.get("suggestion", ""),
                        ))

            except Exception as e:
                # Log but continue
                pass

        result.execution_time_ms = (time.time() - start_time) * 1000

        if result.passed:
            result.checks_passed.append("no_mock_llm")

        return result


async def validate_no_mocks(project_dir: str, strict: bool = True) -> ValidationResult:
    """
    Convenience function to validate a project for mock patterns.

    Args:
        project_dir: Path to project directory
        strict: If True, warnings are treated as errors

    Returns:
        ValidationResult with any violations found
    """
    validator = NoMockValidator(project_dir, strict_mode=strict)
    return await validator.validate()


async def validate_test_files_no_mocks(
    project_dir: str,
    test_files: Optional[list[Path]] = None,
    strict: bool = True,
) -> ValidationResult:
    """
    Convenience function to validate test files for mock usage.

    Phase 3: NO MOCKS policy - all tests must be real integration tests.

    Args:
        project_dir: Path to project directory
        test_files: Optional list of specific test file paths
        strict: If True, warnings are treated as errors

    Returns:
        ValidationResult with any mock violations in test files
    """
    validator = NoMockValidator(project_dir, strict_mode=strict)
    return await validator.validate_test_files(test_files)


# Standalone testing
if __name__ == "__main__":
    import asyncio
    import sys

    def print_usage():
        print("Usage: python no_mock_validator.py <project_dir> [--tests]")
        print()
        print("Options:")
        print("  --tests    Validate test files only (NO MOCKS policy)")
        print()
        print("Examples:")
        print("  python no_mock_validator.py ./my_project")
        print("  python no_mock_validator.py ./my_project --tests")

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    project_dir = sys.argv[1]
    validate_tests_only = "--tests" in sys.argv

    async def main():
        if validate_tests_only:
            print(f"\n{'='*60}")
            print("TEST FILE MOCK VALIDATION (NO MOCKS policy)")
            print(f"{'='*60}")
            result = await validate_test_files_no_mocks(project_dir)
        else:
            print(f"\n{'='*60}")
            print("PRODUCTION CODE MOCK VALIDATION")
            print(f"{'='*60}")
            result = await validate_no_mocks(project_dir)

        print(f"Project: {project_dir}")
        print(f"Passed: {result.passed}")
        print(f"Errors: {result.error_count}")
        print(f"Warnings: {result.warning_count}")
        print(f"Execution time: {result.execution_time_ms:.2f}ms")

        if result.failures:
            print(f"\n{'='*60}")
            print("Violations Found:")
            print(f"{'='*60}")
            for failure in result.failures:
                print(f"\n{failure.to_prompt_context()}")

        if validate_tests_only and not result.passed:
            print(f"\n{'='*60}")
            print("POLICY REMINDER: NO MOCKS ALLOWED IN TESTS")
            print("All tests must be real integration tests:")
            print("  - Real HTTP calls to actual endpoints")
            print("  - Real database operations (SQLite/test DB)")
            print("  - Real file I/O operations")
            print("  - Real external service calls (test containers)")
            print(f"{'='*60}")

        sys.exit(0 if result.passed else 1)

    asyncio.run(main())
