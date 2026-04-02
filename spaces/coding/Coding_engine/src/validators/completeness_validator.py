"""
File Completeness Validator - Detects truncated/incomplete generated files.

Claude CLI sometimes generates incomplete files that end with truncation markers like:
- // ... rest of file
- // ... rest unchanged
- // TODO: implement

This validator detects these patterns and triggers regeneration.
"""

import re
import time
from pathlib import Path
from typing import Optional

import structlog

from .base_validator import (
    BaseValidator,
    ValidationFailure,
    ValidationResult,
    ValidationSeverity,
)

logger = structlog.get_logger(__name__)


class FileCompletenessValidator(BaseValidator):
    """
    Validates that generated files are complete and not truncated.

    Scans code files for truncation patterns that indicate Claude CLI
    did not generate the complete file content.
    """

    # Truncation patterns to detect (pattern, description)
    TRUNCATION_PATTERNS = [
        # Explicit truncation markers
        (r'//\s*\.\.\.\s*(rest|remaining|continued|etc|of\s+file)', 'truncation_marker'),
        (r'//\s*\.\.\.\s*(rest|remaining)\s+unchanged', 'unchanged_marker'),
        (r'//\s*\.\.\.\s*$', 'ellipsis_comment'),
        (r'/\*\s*\.\.\.\s*\*/', 'block_ellipsis'),

        # Python truncation markers
        (r'#\s*\.\.\.\s*(rest|remaining|continued|etc|of\s+file)', 'python_truncation'),
        (r'#\s*\.\.\.\s*$', 'python_ellipsis'),

        # Incomplete implementation markers (only match TODO: implement specifically)
        (r'//\s*TODO:\s*(implement|complete|finish|add)\s+', 'todo_incomplete'),
        (r'#\s*TODO:\s*(implement|complete|finish|add)\s+', 'python_todo_incomplete'),

        # Special markers
        (r'//\s*@incomplete', 'incomplete_marker'),
        (r'//\s*TRUNCATED', 'truncated_marker'),

        # "Same as above/before" patterns that indicate skipped code
        (r'//\s*(same\s+as|similar\s+to|like)\s+(above|before)', 'same_as_marker'),
    ]

    # File extensions to check
    CODE_EXTENSIONS = {
        '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',  # JavaScript/TypeScript
        '.py', '.pyw',  # Python
        '.java', '.kt', '.kts',  # JVM
        '.go',  # Go
        '.rs',  # Rust
        '.c', '.cpp', '.h', '.hpp',  # C/C++
        '.cs',  # C#
        '.rb',  # Ruby
        '.php',  # PHP
        '.swift',  # Swift
        '.vue', '.svelte',  # Frontend frameworks
    }

    # Directories to skip
    SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', '.next', '__pycache__', '.venv', 'venv'}

    @property
    def name(self) -> str:
        return "File Completeness"

    @property
    def check_type(self) -> str:
        return "completeness"

    async def validate(self) -> ValidationResult:
        """
        Scan generated files for truncation patterns and structural issues.

        Returns:
            ValidationResult with any completeness failures found
        """
        start_time = time.time()
        result = self._create_result()

        try:
            files_checked = 0

            for file_path in self._scan_code_files():
                files_checked += 1
                try:
                    content = file_path.read_text(encoding='utf-8')
                    failures = self._check_file_completeness(file_path, content)

                    for failure in failures:
                        result.add_failure(failure)

                except Exception as e:
                    logger.debug(
                        "file_read_error",
                        file=str(file_path),
                        error=str(e)
                    )

            result.execution_time_ms = (time.time() - start_time) * 1000

            if result.passed:
                result.checks_passed.append(self.check_type)
                logger.info(
                    "completeness_check_passed",
                    files_checked=files_checked
                )
            else:
                logger.warning(
                    "completeness_check_failed",
                    files_checked=files_checked,
                    errors=result.error_count,
                    warnings=result.warning_count
                )

        except Exception as e:
            logger.error("completeness_validation_error", error=str(e))
            result.add_failure(self._create_failure(
                error_message=f"Completeness validation failed: {str(e)}",
                severity=ValidationSeverity.ERROR,
            ))

        return result

    def _scan_code_files(self):
        """
        Yield all code files in the project directory.

        Yields:
            Path objects for each code file
        """
        for file_path in self.project_dir.rglob('*'):
            if file_path.is_file():
                # Skip directories in SKIP_DIRS
                if any(skip_dir in file_path.parts for skip_dir in self.SKIP_DIRS):
                    continue

                # Only check code files
                if file_path.suffix.lower() in self.CODE_EXTENSIONS:
                    yield file_path

    def _check_file_completeness(
        self,
        file_path: Path,
        content: str
    ) -> list[ValidationFailure]:
        """
        Check a single file for incompleteness patterns.

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            List of ValidationFailure objects for any issues found
        """
        failures = []
        rel_path = self._get_relative_path(file_path)

        # Check for truncation patterns
        for pattern, pattern_type in self.TRUNCATION_PATTERNS:
            matches = list(re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE))

            for match in matches:
                line_number = content[:match.start()].count('\n') + 1
                matched_text = match.group(0).strip()

                failures.append(self._create_failure(
                    error_message=f"Truncation pattern detected: '{matched_text}'",
                    severity=ValidationSeverity.ERROR,
                    file_path=rel_path,
                    line_number=line_number,
                    error_code=f"TRUNCATED_{pattern_type.upper()}",
                    suggested_fix="Regenerate this file with complete implementation. "
                                  "Do NOT use '// ...' or similar markers.",
                ))

        # Check for unclosed braces (TypeScript/JavaScript/Java/etc.)
        if file_path.suffix.lower() in {'.ts', '.tsx', '.js', '.jsx', '.java', '.c', '.cpp', '.cs', '.go', '.rs'}:
            brace_failure = self._check_brace_balance(rel_path, content)
            if brace_failure:
                failures.append(brace_failure)

        # Check for unclosed brackets in Python (parentheses, brackets)
        if file_path.suffix.lower() in {'.py', '.pyw'}:
            bracket_failure = self._check_python_bracket_balance(rel_path, content)
            if bracket_failure:
                failures.append(bracket_failure)

        # Check for file ending mid-line (no trailing newline with unclosed structure)
        if content and not content.endswith('\n'):
            # Only flag if the last line looks incomplete
            last_line = content.split('\n')[-1].strip()
            if last_line and not last_line.endswith((';', '{', '}', ')', ']', ':', ',', '"""', "'''")):
                if len(last_line) > 5:  # Avoid flagging very short files
                    failures.append(self._create_failure(
                        error_message="File ends without newline and may be truncated",
                        severity=ValidationSeverity.WARNING,
                        file_path=rel_path,
                        line_number=content.count('\n') + 1,
                        error_code="TRUNCATED_NO_NEWLINE",
                        suggested_fix="Check if file content is complete",
                    ))

        return failures

    def _check_brace_balance(
        self,
        file_path: str,
        content: str
    ) -> Optional[ValidationFailure]:
        """
        Check if braces {} are balanced in the file.

        Args:
            file_path: Relative file path
            content: File content

        Returns:
            ValidationFailure if braces are unbalanced, None otherwise
        """
        # Remove string literals and comments to avoid false positives
        cleaned = self._remove_strings_and_comments(content)

        open_braces = cleaned.count('{')
        close_braces = cleaned.count('}')

        if open_braces > close_braces:
            diff = open_braces - close_braces
            return self._create_failure(
                error_message=f"Unclosed braces: {diff} more '{{' than '}}'",
                severity=ValidationSeverity.ERROR,
                file_path=file_path,
                error_code="TRUNCATED_UNCLOSED_BRACE",
                suggested_fix=f"File is missing {diff} closing brace(s). Regenerate with complete implementation.",
            )

        return None

    def _check_python_bracket_balance(
        self,
        file_path: str,
        content: str
    ) -> Optional[ValidationFailure]:
        """
        Check if brackets (), [], {} are balanced in Python file.

        Args:
            file_path: Relative file path
            content: File content

        Returns:
            ValidationFailure if brackets are unbalanced, None otherwise
        """
        # Remove string literals and comments
        cleaned = self._remove_python_strings_and_comments(content)

        pairs = [('(', ')'), ('[', ']'), ('{', '}')]

        for open_char, close_char in pairs:
            opens = cleaned.count(open_char)
            closes = cleaned.count(close_char)

            if opens > closes:
                diff = opens - closes
                return self._create_failure(
                    error_message=f"Unclosed brackets: {diff} more '{open_char}' than '{close_char}'",
                    severity=ValidationSeverity.ERROR,
                    file_path=file_path,
                    error_code="TRUNCATED_UNCLOSED_BRACKET",
                    suggested_fix=f"File is missing {diff} closing bracket(s). Regenerate with complete implementation.",
                )

        return None

    def _remove_strings_and_comments(self, content: str) -> str:
        """
        Remove string literals and comments from JS/TS content.

        This prevents false positives from braces inside strings/comments.
        """
        # Remove multi-line comments
        content = re.sub(r'/\*[\s\S]*?\*/', '', content)
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        # Remove template literals
        content = re.sub(r'`[^`]*`', '""', content)
        # Remove double-quoted strings
        content = re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)
        # Remove single-quoted strings
        content = re.sub(r"'(?:[^'\\]|\\.)*'", "''", content)

        return content

    def _remove_python_strings_and_comments(self, content: str) -> str:
        """
        Remove string literals and comments from Python content.
        """
        # Remove triple-quoted strings
        content = re.sub(r'"""[\s\S]*?"""', '""', content)
        content = re.sub(r"'''[\s\S]*?'''", "''", content)
        # Remove single-line comments
        content = re.sub(r'#.*$', '', content, flags=re.MULTILINE)
        # Remove double-quoted strings
        content = re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)
        # Remove single-quoted strings
        content = re.sub(r"'(?:[^'\\]|\\.)*'", "''", content)

        return content

    def _get_relative_path(self, file_path: Path) -> str:
        """Get path relative to project directory."""
        try:
            return str(file_path.relative_to(self.project_dir))
        except ValueError:
            return str(file_path)
