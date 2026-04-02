"""
Validation Recovery Agent - Uses Claude Code to fix validation failures.

Similar to RecoveryAgent but specialized for project-level validation
issues like build errors, Electron configuration, and module resolution.
"""

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import structlog

from ..validators.base_validator import ValidationFailure, ValidationResult, ValidationSeverity
from ..tools.claude_code_tool import ClaudeCodeTool, CodeGenerationResult
from ..tools.memory_tool import MemoryTool


logger = structlog.get_logger(__name__)


@dataclass
class ValidationFix:
    """Result of attempting to fix a validation failure."""
    failure: ValidationFailure
    success: bool
    files_modified: list[str]
    error_message: Optional[str] = None
    iterations: int = 1


class ValidationRecoveryAgent:
    """
    Agent that uses Claude Code to fix validation failures.

    Follows the same pattern as RecoveryAgent:
    1. Analyze the failure
    2. Build a targeted prompt
    3. Invoke Claude Code to generate fix
    4. Apply and verify the fix
    """

    def __init__(
        self,
        project_dir: str,
        claude_tool: Optional[ClaudeCodeTool] = None,
        max_retries: int = 2,
        memory_tool: Optional[MemoryTool] = None,
    ):
        """
        Initialize recovery agent.

        Args:
            project_dir: Path to the project
            claude_tool: Claude Code tool instance
            max_retries: Maximum retries per failure
            memory_tool: Memory tool for learning from past fixes
        """
        self.project_dir = Path(project_dir)
        # Use minimal_context=True to skip engine/skills docs for validation fixes
        self.claude_tool = claude_tool or ClaudeCodeTool(
            working_dir=str(project_dir),
            minimal_context=True,  # Reduces prompt by ~10KB for validation fixes
        )
        self.max_retries = max_retries
        self.memory_tool = memory_tool

    async def fix_failure(self, failure: ValidationFailure) -> ValidationFix:
        """
        Attempt to fix a single validation failure.

        Args:
            failure: The validation failure to fix

        Returns:
            ValidationFix with result
        """
        logger.info(
            "fixing_validation_failure",
            check_type=failure.check_type,
            error=failure.error_message[:100],
        )

        # Search for similar validation fixes in memory
        similar_fixes = []
        if self.memory_tool and self.memory_tool.enabled:
            try:
                project_type = self._detect_project_type()
                patterns = await self.memory_tool.search_validation_fixes(
                    check_type=failure.check_type,
                    error_message=failure.error_message[:200],
                    project_type=project_type,
                    limit=5,  # Get 5 candidates for scoring
                    rerank=True  # Enable reranking
                )
                if patterns:
                    similar_fixes = patterns
                    logger.info(
                        "found_similar_validation_fixes",
                        check_type=failure.check_type,
                        matches=len(patterns),
                        top_confidence=patterns[0].confidence if patterns else 0
                    )
            except Exception as e:
                logger.warning("memory_search_failed", error=str(e))

        for attempt in range(self.max_retries):
            try:
                # Build prompt for Claude with learned fixes
                prompt = self._build_fix_prompt(failure, attempt, similar_fixes)

                # Get relevant context files
                context_files = self._get_context_files(failure)

                # Invoke Claude Code
                result = await self.claude_tool.execute(
                    prompt=prompt,
                    context_files=context_files,
                )

                if result.success and result.files:
                    logger.info(
                        "validation_fix_generated",
                        check_type=failure.check_type,
                        files_count=len(result.files),
                        attempt=attempt + 1,
                    )

                    # Store successful fix in memory
                    if self.memory_tool and self.memory_tool.enabled:
                        try:
                            await self.memory_tool.store_error_fix(
                                error_type=f"validation_{failure.check_type}",
                                error_message=failure.error_message[:300],
                                fix_description=result.output[:500] if result.output else "Validation fix applied",
                                files_modified=[f.path for f in result.files],
                                project_type=self._detect_project_type(),
                                project_name=os.path.basename(str(self.project_dir)),
                                iteration=attempt + 1,
                                success=True
                            )
                            logger.info("stored_validation_fix_in_memory", check_type=failure.check_type)
                        except Exception as e:
                            logger.warning("memory_store_failed", error=str(e))

                    return ValidationFix(
                        failure=failure,
                        success=True,
                        files_modified=[f.path for f in result.files],
                        iterations=attempt + 1,
                    )
                else:
                    logger.warning(
                        "validation_fix_failed",
                        check_type=failure.check_type,
                        attempt=attempt + 1,
                        error=result.error,
                    )

            except Exception as e:
                logger.error(
                    "validation_fix_exception",
                    check_type=failure.check_type,
                    attempt=attempt + 1,
                    error=str(e),
                )

        return ValidationFix(
            failure=failure,
            success=False,
            files_modified=[],
            error_message=f"Failed after {self.max_retries} attempts",
            iterations=self.max_retries,
        )

    async def fix_multiple(
        self,
        failures: list[ValidationFailure],
        stop_on_first_success: bool = False,
    ) -> list[ValidationFix]:
        """
        Fix errors in parallel, grouped by target file to avoid conflicts.

        Errors affecting different files run fully in parallel.
        Errors affecting the same file run sequentially within their group.
        This prevents file write conflicts while maximizing parallelism.

        Args:
            failures: List of failures to fix
            stop_on_first_success: Stop after first successful fix

        Returns:
            List of ValidationFix results
        """
        # 1. Group failures by target file to avoid write conflicts
        file_groups: dict[str, list[ValidationFailure]] = {}
        for failure in failures:
            target_file = self._extract_target_file(failure)
            if target_file not in file_groups:
                file_groups[target_file] = []
            file_groups[target_file].append(failure)

        logger.info(
            "file_based_parallel_grouping",
            total_errors=len(failures),
            unique_files=len(file_groups),
            max_errors_per_file=max(len(g) for g in file_groups.values()) if file_groups else 0,
        )

        # 2. Define task to fix all errors for a single file (sequential within file)
        async def fix_file_group(file_path: str, group_failures: list[ValidationFailure]) -> list[ValidationFix]:
            fixes = []
            for failure in group_failures:
                fix = await self.fix_failure(failure)
                fixes.append(fix)
                if fix.success and stop_on_first_success:
                    break
            return fixes

        # 3. Run ALL file groups in parallel - no file conflicts possible!
        group_tasks = [
            fix_file_group(file_path, group_failures)
            for file_path, group_failures in file_groups.items()
        ]

        logger.info(
            "starting_parallel_file_groups",
            parallel_groups=len(group_tasks),
        )

        results = await asyncio.gather(*group_tasks, return_exceptions=True)

        # 4. Flatten results
        all_fixes = []
        successful_count = 0
        failed_count = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error("file_group_exception", error=str(result))
                failed_count += 1
                continue
            for fix in result:
                all_fixes.append(fix)
                if fix.success:
                    successful_count += 1
                else:
                    failed_count += 1

        logger.info(
            "parallel_fixes_complete",
            total_fixes=len(all_fixes),
            successful=successful_count,
            failed=failed_count,
        )

        return all_fixes

    def _extract_target_file(self, failure: ValidationFailure) -> str:
        """
        Extract the file that will be modified from the error.

        This is used to group errors by target file to avoid parallel write conflicts.

        Examples:
            "src/types.ts(15,5): error TS2304" -> "src/types.ts"
            "Error in ./src/components/Button.tsx" -> "src/components/Button.tsx"
        """
        # First check if failure has explicit file_path
        if failure.file_path:
            return failure.file_path

        # Parse error message to find target file
        error_msg = failure.error_message

        # Pattern 1: TypeScript error format: "src/file.ts(line,col): error"
        match = re.search(r'^([^(\s]+\.tsx?)\(', error_msg)
        if match:
            return match.group(1)

        # Pattern 2: Vite/Webpack format: "Error in ./src/file.tsx"
        match = re.search(r'in \./([^\s:]+\.tsx?)', error_msg)
        if match:
            return match.group(1)

        # Pattern 3: General file path in error: "src/something.ts"
        match = re.search(r'([^\s"\']+\.tsx?)', error_msg)
        if match:
            return match.group(1)

        # Fallback: group by check_type to avoid conflicts within same validation type
        return f"_unknown_{failure.check_type}"

    def _build_fix_prompt(self, failure: ValidationFailure, attempt: int, similar_fixes: list = None) -> str:
        """Build a targeted prompt for fixing the validation failure, optionally including learned fixes."""
        prompt_parts = [
            "# Fix Validation Error",
            "",
            "You are fixing a validation error in a generated project.",
            "Analyze the error and make the minimal changes needed to fix it.",
            "",
            failure.to_prompt_context(),
            "",
        ]

        # Add code context for TypeScript errors (enriches prompt with actual code)
        if failure.check_type == "typescript" and failure.file_path and failure.line_number:
            code_context = self._extract_code_context(failure.file_path, failure.line_number)
            if code_context:
                prompt_parts.extend([
                    "## Code Context (error line marked with >>>)",
                    "```typescript",
                    code_context,
                    "```",
                    "",
                ])

            # Add type definitions for types mentioned in error
            type_names = self._extract_type_names_from_error(failure.error_message)
            if type_names:
                type_defs = self._find_type_definitions(type_names)
                if type_defs:
                    prompt_parts.extend([
                        "## Related Type Definitions",
                        "```typescript",
                        type_defs,
                        "```",
                        "",
                    ])
                    logger.debug(
                        "type_definitions_added_to_prompt",
                        types=type_names,
                        definitions_found=len(type_defs.split('\n\n')),
                    )

        prompt_parts.extend([
            "## Instructions",
            "",
        ])

        # Add check-type specific instructions
        if failure.check_type == "electron":
            prompt_parts.extend([
                "This is an Electron configuration issue. Common fixes:",
                "- Ensure 'electron' is in external array in bundler config",
                "- Check that electron-vite.config.ts has proper rollupOptions.external",
                "- Verify main process entry point uses correct import syntax",
                "- Check preload script has contextBridge setup",
                "",
            ])
        elif failure.check_type == "typescript":
            prompt_parts.extend([
                "This is a TypeScript compilation error. Common fixes:",
                "- Fix type mismatches",
                "- Add missing type imports",
                "- Update tsconfig.json paths",
                "",
            ])
        elif failure.check_type == "build":
            prompt_parts.extend([
                "This is a build error. Common fixes:",
                "- Check package.json scripts",
                "- Verify all dependencies are installed",
                "- Check for circular imports",
                "",
            ])
        elif failure.check_type == "completeness":
            # Truncated/incomplete file detection
            prompt_parts.extend([
                "## CRITICAL: File Truncation Detected",
                "",
                f"The file `{failure.file_path}` is INCOMPLETE or TRUNCATED.",
                "",
                "**IMPORTANT RULES:**",
                "1. You MUST regenerate the COMPLETE file content",
                "2. Do NOT use truncation markers like:",
                "   - `// ...`",
                "   - `// ... rest of file`",
                "   - `// ... remaining unchanged`",
                "   - `// TODO: implement`",
                "3. Write out the FULL implementation, including ALL:",
                "   - Import statements",
                "   - Type definitions",
                "   - Function implementations",
                "   - Class methods",
                "   - Export statements",
                "4. Ensure all brackets {} and parentheses () are properly closed",
                "",
                "The truncated content detected:",
                f"```",
                f"{failure.error_message}",
                f"```",
                "",
            ])

        # Add learned fixes from memory as context
        if similar_fixes:
            prompt_parts.extend([
                "## Context from Similar Past Fixes",
                "These patterns have worked for similar validation issues:",
                "",
            ])
            for i, fix in enumerate(similar_fixes[:3], 1):  # Top 3 fixes
                prompt_parts.append(f"{i}. {fix.fix_description}")
                if fix.files_modified:
                    prompt_parts.append(f"   Files modified: {', '.join(fix.files_modified[:2])}")
                prompt_parts.append(f"   Confidence: {fix.confidence:.2f}")
                prompt_parts.append("")

        # On retry, add more debugging context
        if attempt > 0:
            prompt_parts.extend([
                f"## Note: This is retry attempt {attempt + 1}",
                "The previous fix attempt did not resolve the issue.",
                "Please try a different approach or be more thorough.",
                "",
            ])

        if failure.suggested_fix:
            prompt_parts.extend([
                "## Suggested Fix",
                failure.suggested_fix,
                "",
            ])

        prompt_parts.extend([
            "## Requirements",
            "1. Make only the minimal changes needed to fix this specific error",
            "2. Do not add unnecessary code or refactoring",
            "3. Preserve existing functionality",
            "4. Output the complete fixed file(s)",
            "",
        ])

        return "\n".join(prompt_parts)

    def _get_context_files(self, failure: ValidationFailure) -> list[str]:
        """Get relevant files to provide as context for the fix."""
        context_files = []

        # Always include package.json
        pkg_json = self.project_dir / "package.json"
        if pkg_json.exists():
            context_files.append(str(pkg_json))

        # Include the failing file if specified
        if failure.file_path:
            file_path = Path(failure.file_path)
            if file_path.exists():
                context_files.append(str(file_path))

        # Include related files
        for rel_file in failure.related_files:
            rel_path = self.project_dir / rel_file
            if rel_path.exists():
                context_files.append(str(rel_path))

        # Check-type specific context
        if failure.check_type == "electron":
            config_files = [
                "electron.vite.config.ts",
                "electron.vite.config.js",
                "vite.config.ts",
                "src/main/main.ts",
                "src/preload/preload.ts",
            ]
            for config in config_files:
                config_path = self.project_dir / config
                if config_path.exists() and str(config_path) not in context_files:
                    context_files.append(str(config_path))

        elif failure.check_type == "typescript":
            tsconfig = self.project_dir / "tsconfig.json"
            if tsconfig.exists():
                context_files.append(str(tsconfig))

        return context_files[:10]  # Limit context size

    def _extract_code_context(
        self,
        file_path: str,
        line_number: int,
        context_lines: int = 15,
    ) -> str:
        """
        Extract code context around the error line.

        Args:
            file_path: Path to the file with the error
            line_number: Line number of the error (1-indexed)
            context_lines: Number of lines before and after to include

        Returns:
            Formatted code snippet with line numbers, error line marked with >>>
        """
        try:
            # Try relative to project dir first, then absolute
            full_path = self.project_dir / file_path
            if not full_path.exists():
                full_path = Path(file_path)
            if not full_path.exists():
                return ""

            content = full_path.read_text(encoding="utf-8")
            lines = content.split('\n')

            # Calculate range (convert to 0-indexed)
            start = max(0, line_number - 1 - context_lines)
            end = min(len(lines), line_number + context_lines)

            # Format with line numbers, highlight error line
            result_lines = []
            for i in range(start, end):
                line_num = i + 1
                prefix = ">>> " if line_num == line_number else "    "
                result_lines.append(f"{prefix}{line_num:4d} | {lines[i]}")

            return '\n'.join(result_lines)
        except Exception as e:
            logger.debug("code_context_extraction_failed", error=str(e), file=file_path)
            return ""

    def _extract_type_names_from_error(self, error_message: str) -> list[str]:
        """
        Extract type names mentioned in a TypeScript error message.

        Examples:
            "Type 'Foo' is not assignable to type 'Bar'" -> ['Foo', 'Bar']
            "Property 'x' does not exist on type 'Baz'" -> ['Baz']
        """
        type_patterns = [
            r"type ['\"](\w+)['\"]",           # type 'TypeName'
            r"Type ['\"](\w+)['\"]",           # Type 'TypeName'
            r"of type ['\"](\w+)['\"]",        # of type 'TypeName'
            r"to type ['\"](\w+)['\"]",        # to type 'TypeName'
            r"interface ['\"](\w+)['\"]",      # interface 'TypeName'
            r"['\"](\w+)['\"] is not",         # 'TypeName' is not
        ]

        types = set()
        for pattern in type_patterns:
            matches = re.findall(pattern, error_message, re.IGNORECASE)
            types.update(matches)

        # Filter out common TypeScript primitive types
        exclude = {'string', 'number', 'boolean', 'null', 'undefined', 'any', 'void', 'never', 'object', 'unknown'}
        return [t for t in types if t.lower() not in exclude]

    def _find_type_definitions(self, type_names: list[str]) -> str:
        """
        Find type/interface definitions for the given type names.

        Searches for:
            - interface TypeName { ... }
            - type TypeName = ...
            - enum TypeName { ... }

        Returns formatted definitions with source file info.
        """
        if not type_names:
            return ""

        definitions = []

        for type_name in type_names[:5]:  # Limit to 5 types to avoid huge prompts
            # Search for type definition
            pattern = rf"(export\s+)?(interface|type|enum)\s+{re.escape(type_name)}\b"

            for ts_file in self.project_dir.rglob("*.ts"):
                if "node_modules" in str(ts_file):
                    continue

                try:
                    content = ts_file.read_text(encoding="utf-8")
                    match = re.search(pattern, content)

                    if match:
                        # Extract the definition (first 15 lines from match position)
                        start_pos = match.start()
                        lines = content[start_pos:].split('\n')[:15]
                        definition = '\n'.join(lines)

                        # Get relative path
                        try:
                            rel_path = ts_file.relative_to(self.project_dir)
                        except ValueError:
                            rel_path = ts_file.name

                        definitions.append(f"// From: {rel_path}\n{definition}")
                        break  # Found this type, move to next
                except Exception:
                    continue

        return '\n\n'.join(definitions)

    def _detect_project_type(self) -> str:
        """Detect project type from project directory."""
        # Simple detection based on file existence
        if (self.project_dir / "package.json").exists():
            if (self.project_dir / "electron.vite.config.ts").exists() or (self.project_dir / "electron.vite.config.js").exists():
                return "electron-vite"
            elif (self.project_dir / "electron-builder.yml").exists():
                return "electron"
            return "node"
        elif (self.project_dir / "requirements.txt").exists():
            return "python"
        elif (self.project_dir / "Cargo.toml").exists():
            return "rust"
        return "unknown"

    def _group_failures(
        self,
        failures: list[ValidationFailure],
    ) -> dict[str, list[ValidationFailure]]:
        """Group related failures to avoid redundant fix attempts."""
        groups: dict[str, list[ValidationFailure]] = {}

        for failure in failures:
            # Group by check_type + file
            if failure.file_path:
                key = f"{failure.check_type}:{failure.file_path}"
            else:
                key = failure.check_type

            if key not in groups:
                groups[key] = []
            groups[key].append(failure)

        # Sort within groups by severity
        for key in groups:
            groups[key].sort(
                key=lambda f: 0 if f.severity == ValidationSeverity.ERROR else 1
            )

        return groups


async def fix_validation_failures(
    project_dir: str,
    result: ValidationResult,
) -> list[ValidationFix]:
    """
    Convenience function to fix validation failures.

    Args:
        project_dir: Path to project
        result: ValidationResult with failures

    Returns:
        List of fix attempts
    """
    agent = ValidationRecoveryAgent(project_dir)
    return await agent.fix_multiple(result.failures)
