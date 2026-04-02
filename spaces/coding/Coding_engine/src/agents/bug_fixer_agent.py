"""
Bug Fixer Agent - Fast-path agent for fixing code-level errors during generation.

Handles code errors detected by the dev server:
- Missing exports (module does not provide an export named 'X')
- Import path errors
- Circular dependencies
- Syntax errors

Works alongside DependencyManagerAgent:
- DependencyManagerAgent: handles npm module installation
- BugFixerAgent: handles code-level fixes

Publishes:
- CODE_FIXED: After successfully fixing code
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    code_fixed_event,
)
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent
from ..tools.claude_code_tool import ClaudeCodeTool


logger = structlog.get_logger(__name__)


class BugFixerAgent(AutonomousAgent):
    """
    Fast-path agent for fixing code-level errors during code generation.

    Subscribes to:
    - VALIDATION_ERROR with error_type="code_error"

    Publishes:
    - CODE_FIXED: After fixing code

    Workflow:
    1. DevServerManager detects code error (missing export, etc.)
    2. Publishes VALIDATION_ERROR with code_error_type
    3. BugFixerAgent receives event
    4. Reads affected file, uses Claude to generate fix
    5. Publishes CODE_FIXED event
    6. DevServerManager restarts automatically
    """

    # Cooldown to prevent rapid-fire fixes on the same error
    COOLDOWN_SECONDS = 10.0

    # Track recently fixed errors to avoid loops
    MAX_RECENT_FIXES = 50

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        timeout: int = 120,
    ):
        """
        Initialize the BugFixerAgent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics (can be None for early startup)
            working_dir: Project working directory
            timeout: Timeout for Claude CLI calls
        """
        super().__init__(name, event_bus, shared_state, working_dir)
        self.timeout = timeout
        self._last_fix_time: Optional[float] = None
        self._recent_fixes: list[str] = []  # Track error hashes to avoid loops

        # Initialize Claude Code tool
        self.code_tool = ClaudeCodeTool(
            working_dir=working_dir,
            timeout=timeout,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.VALIDATION_ERROR,
            EventType.BROWSER_ERROR,  # Browser console errors detected by BrowserErrorDetector
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if we should fix a code error.

        Acts when:
        - VALIDATION_ERROR with error_type="code_error"
        - BROWSER_ERROR with error_type we can handle (missing_export, etc.)
        - code_error_type is one we can handle
        - Not in cooldown period
        - Haven't already tried to fix this exact error
        """
        import time
        import hashlib

        for event in events:
            error_data = event.data or {}

            # Handle BROWSER_ERROR events (from BrowserErrorDetector)
            if event.type == EventType.BROWSER_ERROR:
                error_type = error_data.get("error_type")
                # Handle ALL browser errors generically - Claude will analyze and fix
                # Only skip network errors (404s) as they're usually caused by other errors
                if error_type == "network_error":
                    continue

                # Create error hash to detect duplicates
                error_hash = hashlib.md5(
                    f"browser:{error_type}:{error_data.get('target_module')}:{error_data.get('missing_export')}".encode()
                ).hexdigest()[:16]

                if error_hash in self._recent_fixes:
                    self.logger.debug(
                        "skipping_duplicate_browser_fix",
                        error_hash=error_hash,
                        error_type=error_type,
                    )
                    continue

                # Check cooldown
                if self._last_fix_time:
                    elapsed = time.time() - self._last_fix_time
                    if elapsed < self.COOLDOWN_SECONDS:
                        continue

                self.logger.info(
                    "browser_error_detected",
                    error_type=error_type,
                    missing_export=error_data.get("missing_export"),
                )
                return True

            # Handle VALIDATION_ERROR events (from DevServerManager)
            if event.type == EventType.VALIDATION_ERROR:
                error_type = error_data.get("error_type")

                # Only handle code errors (not module_not_found - that's DependencyManager's job)
                if error_type != "code_error":
                    continue

                code_error_type = error_data.get("code_error_type")

                # We now handle ALL code_error types with specialized handlers + generic fallback
                # Specialized: missing_export, import_path_error, circular_dependency, duplicate_identifier, require_not_defined
                # Everything else: generic fallback using Claude

                # Create error hash to detect duplicates
                error_hash = hashlib.md5(
                    f"{code_error_type}:{error_data.get('target_module')}:{error_data.get('missing_export')}".encode()
                ).hexdigest()[:16]

                # Skip if we recently tried to fix this exact error
                if error_hash in self._recent_fixes:
                    self.logger.debug(
                        "skipping_duplicate_fix",
                        error_hash=error_hash,
                        code_error_type=code_error_type,
                    )
                    continue

                # Check cooldown
                if self._last_fix_time:
                    elapsed = time.time() - self._last_fix_time
                    if elapsed < self.COOLDOWN_SECONDS:
                        self.logger.debug(
                            "in_cooldown",
                            elapsed=elapsed,
                            remaining=self.COOLDOWN_SECONDS - elapsed,
                        )
                        continue

                return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Fix code errors.

        Routes to appropriate fix method based on error type.
        Handles both VALIDATION_ERROR (server-side) and BROWSER_ERROR (client-side).
        """
        import time
        import hashlib

        for event in events:
            error_data = event.data or {}

            # Handle BROWSER_ERROR events (from BrowserErrorDetector)
            if event.type == EventType.BROWSER_ERROR:
                error_type = error_data.get("error_type")

                # Handle ALL browser errors - only skip network errors
                if error_type == "network_error":
                    continue

                # Create error hash for tracking
                error_hash = hashlib.md5(
                    f"browser:{error_type}:{error_data.get('target_module')}:{error_data.get('missing_export')}".encode()
                ).hexdigest()[:16]

                self._recent_fixes.append(error_hash)
                if len(self._recent_fixes) > self.MAX_RECENT_FIXES:
                    self._recent_fixes.pop(0)

                self._last_fix_time = time.time()

                self.logger.info(
                    "fixing_browser_error",
                    error_type=error_type,
                    target_module=error_data.get("target_module"),
                    missing_export=error_data.get("missing_export"),
                )

                success = await self._fix_browser_error(error_data)

                if success:
                    self.logger.info("browser_fix_succeeded", error_type=error_type)
                else:
                    self.logger.warning("browser_fix_failed", error_type=error_type)

                return

            # Handle VALIDATION_ERROR events (from DevServerManager)
            if event.type == EventType.VALIDATION_ERROR:
                if error_data.get("error_type") != "code_error":
                    continue

                code_error_type = error_data.get("code_error_type")

                # Create error hash for tracking
                error_hash = hashlib.md5(
                    f"{code_error_type}:{error_data.get('target_module')}:{error_data.get('missing_export')}".encode()
                ).hexdigest()[:16]

                # Track this fix attempt
                self._recent_fixes.append(error_hash)
                if len(self._recent_fixes) > self.MAX_RECENT_FIXES:
                    self._recent_fixes.pop(0)

                self._last_fix_time = time.time()

                self.logger.info(
                    "fixing_code_error",
                    code_error_type=code_error_type,
                    target_module=error_data.get("target_module"),
                    missing_export=error_data.get("missing_export"),
                )

                success = False
                if code_error_type == "missing_export":
                    success = await self._fix_missing_export(error_data)
                elif code_error_type == "import_path_error":
                    success = await self._fix_import_path(error_data)
                elif code_error_type == "circular_dependency":
                    success = await self._fix_circular_dependency(error_data)
                elif code_error_type == "duplicate_identifier":
                    success = await self._fix_duplicate_identifier(error_data)
                elif code_error_type == "require_not_defined":
                    success = await self._fix_require_not_defined(error_data)
                elif code_error_type == "syntax_error":
                    success = await self._fix_syntax_error(error_data)
                else:
                    # Generic fallback for unknown error types
                    success = await self._fix_generic_error(error_data)

                if success:
                    self.logger.info("code_fix_succeeded", code_error_type=code_error_type)
                else:
                    self.logger.warning("code_fix_failed", code_error_type=code_error_type)

                # Only process one error at a time
                return

    async def _fix_missing_export(self, error_data: dict) -> bool:
        """
        Fix a missing export by adding it to the source module.

        Strategy:
        1. Resolve the target module path
        2. Read the module file
        3. Use Claude to add the missing export
        4. Publish CODE_FIXED event
        """
        target_module = error_data.get("target_module")
        missing_export = error_data.get("missing_export")
        source_file = error_data.get("source_file")
        raw_error = error_data.get("raw_error", "")

        if not missing_export:
            self.logger.warning("missing_export_name_not_provided")
            return False

        # Try to resolve the module path
        module_path = await self._resolve_module_path(source_file, target_module, raw_error)

        if not module_path:
            self.logger.debug(
                "could_not_resolve_module_path",
                target_module=target_module,
                source_file=source_file,
            )
            # Try to find the file by searching for the module name
            module_path = await self._find_module_file(target_module)

        if not module_path:
            # Last resort: Search for import statements that reference this export
            # This handles the case where we only have the export name from browser overlay
            self.logger.info(
                "trying_import_based_search",
                missing_export=missing_export,
            )
            module_path = await self._find_export_source_by_import(missing_export)

        if not module_path:
            self.logger.warning("module_file_not_found", target_module=target_module, missing_export=missing_export)
            return False

        # Read the module file
        module_content = await self._read_file(module_path)
        if module_content is None:
            self.logger.warning("could_not_read_module", path=module_path)
            return False

        # Build fix prompt
        prompt = f"""Fix the missing export in this TypeScript/JavaScript file.

ERROR: The module does not provide an export named '{missing_export}'

FILE: {module_path}

CURRENT CONTENT:
```typescript
{module_content}
```

TASK:
1. Add the missing export '{missing_export}' to this file
2. If '{missing_export}' doesn't exist in the file, create an appropriate definition based on:
   - The naming convention (e.g., 'ErrorCodes' suggests an enum or object of error codes)
   - Any existing patterns in the file
   - What makes sense for the module's purpose

3. Make sure the export is properly exported (use 'export' keyword)

Write the complete fixed file to {module_path}.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing missing export '{missing_export}' in {module_path}",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fixed_file": module_path,
                        "fix_type": "missing_export",
                        "missing_export": missing_export,
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                return True
            else:
                self.logger.warning(
                    "fix_generation_failed",
                    error=result.error,
                )
                return False

        except Exception as e:
            self.logger.error("fix_exception", error=str(e))
            return False

    async def _fix_import_path(self, error_data: dict) -> bool:
        """
        Fix an import path error.

        Strategy:
        1. Find the correct path for the module
        2. Either fix the import statement or create the missing file
        """
        source_file = error_data.get("source_file")
        target_module = error_data.get("target_module")
        raw_error = error_data.get("raw_error", "")

        if not source_file or not target_module:
            self.logger.warning("missing_source_or_target")
            return False

        # Try to find the correct file
        possible_paths = await self._find_possible_paths(target_module)

        if possible_paths:
            # Fix the import statement
            correct_path = possible_paths[0]
            prompt = f"""Fix the import path in {source_file}.

ERROR: {raw_error}

The import path '{target_module}' is incorrect or the file doesn't exist.
Found possible correct path: '{correct_path}'

Update the import statement to use the correct path, or if the file needs to be
created, create it with appropriate exports.
"""
        else:
            # Create the missing file
            prompt = f"""Create the missing file that {source_file} is trying to import.

ERROR: {raw_error}

The import path is '{target_module}' but this file doesn't exist.
Based on the import path and typical conventions, create the missing file with
appropriate exports that {source_file} likely needs.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing import path for {target_module}",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fix_type": "import_path_error",
                        "target_module": target_module,
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                return True

            return False

        except Exception as e:
            self.logger.error("fix_exception", error=str(e))
            return False

    async def _fix_circular_dependency(self, error_data: dict) -> bool:
        """
        Fix a circular dependency.

        Strategy:
        1. Identify the circular import chain
        2. Restructure imports or extract shared types
        """
        target_module = error_data.get("target_module")
        raw_error = error_data.get("raw_error", "")

        prompt = f"""Fix the circular dependency issue.

ERROR: {raw_error}

CIRCULAR DEPENDENCY involving: {target_module}

Common solutions:
1. Extract shared types/interfaces to a separate file
2. Use dynamic imports for one direction
3. Restructure the module hierarchy

Analyze the error and apply the most appropriate fix.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing circular dependency involving {target_module}",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fix_type": "circular_dependency",
                        "target_module": target_module,
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                return True

            return False

        except Exception as e:
            self.logger.error("fix_exception", error=str(e))
            return False

    async def _fix_browser_error(self, error_data: dict) -> bool:
        """
        Fix a browser console error.

        Browser errors are similar to server-side code errors but detected
        via Playwright console monitoring. They include:
        - missing_export: Module doesn't export the requested name
        - import_error: Failed to resolve module specifier
        - reference_error: Undefined variable used

        Strategy:
        1. Parse the error to extract file and export info
        2. Route to appropriate fix method
        """
        error_type = error_data.get("error_type")
        missing_export = error_data.get("missing_export")
        target_module = error_data.get("target_module")
        source_file = error_data.get("source_file")
        raw_message = error_data.get("message", "")

        self.logger.info(
            "fixing_browser_error",
            error_type=error_type,
            missing_export=missing_export,
            target_module=target_module,
            source_file=source_file,
        )

        if error_type == "missing_export":
            # Reuse the missing export fix logic
            return await self._fix_missing_export({
                "missing_export": missing_export,
                "target_module": target_module,
                "source_file": source_file,
                "raw_error": raw_message,
            })

        elif error_type == "import_error":
            # Reuse the import path fix logic
            return await self._fix_import_path({
                "target_module": target_module,
                "source_file": source_file,
                "raw_error": raw_message,
            })

        elif error_type == "reference_error":
            # Fix undefined reference by analyzing context
            undefined_name = error_data.get("undefined_name")

            prompt = f"""Fix the undefined reference error in the browser.

ERROR: ReferenceError - '{undefined_name}' is not defined

SOURCE FILE: {source_file or 'unknown'}
ERROR MESSAGE: {raw_message}

This error means a variable, function, or import named '{undefined_name}' is used
but never defined. Common fixes:
1. Add the missing import statement
2. Define the missing variable/function
3. Fix a typo in the name

Analyze and fix the issue.
"""

            try:
                result = await self.code_tool.execute(
                    prompt=prompt,
                    context=f"Fixing undefined reference '{undefined_name}'",
                    agent_type="general",
                )

                if result.success and result.files:
                    await self.event_bus.publish(Event(
                        type=EventType.CODE_FIXED,
                        source=self.name,
                        data={
                            "fix_type": "browser_reference_error",
                            "undefined_name": undefined_name,
                            "files_modified": [f.path for f in result.files],
                        },
                    ))
                    return True

                return False

            except Exception as e:
                self.logger.error("browser_fix_exception", error=str(e))
                return False

        else:
            # Generic LLM-based fix for any browser error type
            return await self._fix_generic_browser_error(error_data)

    async def _fix_generic_browser_error(self, error_data: dict) -> bool:
        """
        Fix any browser error using Claude to analyze and fix.

        This is the generic fallback for all browser errors that don't have
        specialized handlers. Uses Claude to analyze the error and apply
        the appropriate fix.

        Common browser errors handled:
        - ReferenceError: require is not defined → Convert to ESM imports
        - SyntaxError → Fix syntax issues
        - TypeError → Fix type-related issues
        - Any other browser console error
        """
        error_type = error_data.get("error_type", "unknown")
        raw_message = error_data.get("message", "")
        source_file = error_data.get("source_file")
        undefined_name = error_data.get("undefined_name")

        self.logger.info(
            "fixing_generic_browser_error",
            error_type=error_type,
            message=raw_message[:100] if raw_message else "no message",
        )

        # Try to find the source file from the error message
        if not source_file:
            source_file = await self._find_file_from_browser_error(raw_message)

        context = ""
        if source_file:
            content = await self._read_file(source_file)
            if content:
                context = f"""

SOURCE FILE: {source_file}
```typescript
{content}
```
"""

        # Build a comprehensive prompt for Claude
        prompt = f"""Fix this browser console error:

ERROR TYPE: {error_type}
ERROR MESSAGE: {raw_message}
{f"UNDEFINED NAME: {undefined_name}" if undefined_name else ""}
{context}

Analyze the error and apply the appropriate fix. Common browser errors include:
- ReferenceError: require is not defined → Convert require() to ESM imports
- ReferenceError: X is not defined → Add missing import or define the variable
- SyntaxError → Fix syntax issues (missing brackets, invalid expressions)
- TypeError → Fix type-related issues (null checks, type conversions)
- Missing exports → Add missing exports to source modules

Apply the fix to the relevant file(s). Search the codebase to find the correct file if not provided.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing browser {error_type} error",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fix_type": "browser_generic",
                        "original_error_type": error_type,
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                self.logger.info(
                    "generic_browser_fix_succeeded",
                    error_type=error_type,
                    files_modified=len(result.files),
                )
                return True

            self.logger.warning(
                "generic_browser_fix_failed",
                error_type=error_type,
                error=result.error,
            )
            return False

        except Exception as e:
            self.logger.error("generic_browser_fix_exception", error=str(e))
            return False

    async def _find_file_from_browser_error(self, error_message: str) -> Optional[str]:
        """
        Extract source file path from a browser error message.

        Browser errors often contain file paths like:
        - "at index.ts:14:51"
        - "at http://localhost:5173/src/components/App.tsx:42"
        - "(http://localhost:5173/src/services/api.ts:15:10)"
        """
        if not error_message:
            return None

        # Pattern 1: "at filename.ts:line:col"
        match = re.search(r"at\s+([^:\s]+\.[tj]sx?):(\d+)", error_message)
        if match:
            filename = match.group(1)
            # Check if it exists in the working directory
            file_path = await self._find_module_file(filename)
            if file_path:
                return file_path

        # Pattern 2: URL with path "http://localhost:5173/src/..."
        match = re.search(r"localhost:\d+(/src/[^:]+\.[tj]sx?)", error_message)
        if match:
            file_path = match.group(1).lstrip("/")
            if (Path(self.working_dir) / file_path).exists():
                return file_path

        # Pattern 3: Just extract any .ts/.tsx/.js/.jsx file reference
        match = re.search(r"([^/\s:]+\.[tj]sx?)", error_message)
        if match:
            filename = match.group(1)
            file_path = await self._find_module_file(filename)
            if file_path:
                return file_path

        return None

    async def _resolve_module_path(
        self,
        source_file: Optional[str],
        target_module: Optional[str],
        raw_error: str,
    ) -> Optional[str]:
        """Resolve a relative module path to an absolute path."""
        if not target_module:
            # Try to extract from raw error
            match = re.search(r"['\"]([./][^'\"]+)['\"]", raw_error)
            if match:
                target_module = match.group(1)
            else:
                return None

        # If source_file is provided, resolve relative to it
        if source_file:
            source_path = Path(self.working_dir) / source_file
            if source_path.exists():
                source_dir = source_path.parent
                target_path = source_dir / target_module

                # Try common extensions
                for ext in ["", ".ts", ".tsx", ".js", ".jsx"]:
                    full_path = target_path.with_suffix(ext) if ext else target_path
                    if full_path.exists():
                        return str(full_path.relative_to(self.working_dir))

                    # Try index file
                    index_path = target_path / f"index{ext}"
                    if index_path.exists():
                        return str(index_path.relative_to(self.working_dir))

        return None

    async def _find_module_file(self, target_module: Optional[str]) -> Optional[str]:
        """Search for a module file in the project."""
        if not target_module:
            return None

        # Extract the file name from the module path
        module_name = Path(target_module).name
        if not module_name:
            return None

        # Search for the file
        working_path = Path(self.working_dir)
        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            # Search in src directory first
            for path in working_path.rglob(f"*{module_name}{ext}"):
                if "node_modules" not in str(path):
                    return str(path.relative_to(working_path))

        return None

    async def _find_export_source_by_import(self, missing_export: str) -> Optional[str]:
        """
        Find the file that should export a symbol by searching for import statements.

        When we only have the export name but not the source file or target module,
        we search the codebase for:
        1. Import statements that reference the missing export
        2. Extract the import path to find which file should export it
        3. Return that file path

        Args:
            missing_export: The name of the missing export (e.g., "generateFinancialReport")

        Returns:
            The file path that should contain the export, or None if not found
        """
        working_path = Path(self.working_dir)

        # Search for import statements that include the missing export
        # Pattern: import { ..., missingExport, ... } from '...'
        search_patterns = [
            f"import.*{missing_export}.*from",  # Named import
            f"\\{{ ?{missing_export}[ ,}}]",     # Destructured import
        ]

        for pattern in search_patterns:
            try:
                # Use ripgrep via tool registry for fast search
                result = await self.call_tool(
                    "search.ripgrep",
                    pattern=pattern,
                    path=".",
                    cwd=str(self.working_dir),
                )

                matches = result.get("matches", [])
                if matches:
                    # Extract unique file paths from matches
                    importing_files = list(dict.fromkeys(
                        m["file"] for m in matches
                        if "node_modules" not in m.get("file", "")
                    ))

                    for importing_file in importing_files:
                        if "node_modules" in importing_file:
                            continue

                        # Read the file and extract the import path
                        try:
                            file_path = working_path / importing_file
                            content = file_path.read_text(encoding="utf-8")

                            # Find the import statement with the missing export
                            import_match = re.search(
                                rf"import\s*\{{[^}}]*{re.escape(missing_export)}[^}}]*\}}\s*from\s*['\"]([^'\"]+)['\"]",
                                content
                            )

                            if import_match:
                                import_path = import_match.group(1)

                                # Resolve the import path relative to the importing file
                                if import_path.startswith("."):
                                    source_dir = file_path.parent
                                    target_path = (source_dir / import_path).resolve()

                                    # Try common extensions
                                    for ext in ["", ".ts", ".tsx", ".js", ".jsx"]:
                                        check_path = Path(str(target_path) + ext) if ext else target_path
                                        if check_path.exists():
                                            rel_path = check_path.relative_to(working_path)
                                            self.logger.info(
                                                "found_export_source_by_import",
                                                missing_export=missing_export,
                                                importing_file=importing_file,
                                                target_file=str(rel_path),
                                            )
                                            return str(rel_path)

                                        # Try index file
                                        index_path = target_path / f"index{ext}"
                                        if index_path.exists():
                                            rel_path = index_path.relative_to(working_path)
                                            self.logger.info(
                                                "found_export_source_by_import",
                                                missing_export=missing_export,
                                                importing_file=importing_file,
                                                target_file=str(rel_path),
                                            )
                                            return str(rel_path)

                        except Exception as e:
                            self.logger.debug("import_parse_error", file=importing_file, error=str(e))
                            continue

            except Exception as e:
                self.logger.warning("ripgrep_search_failed", pattern=pattern, error=str(e))

        # Fallback: Search for files that might export this symbol
        # Look for the export name in service/util files
        self.logger.debug("trying_fallback_export_search", missing_export=missing_export)

        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            for path in working_path.rglob(f"*{ext}"):
                if "node_modules" in str(path):
                    continue

                try:
                    content = path.read_text(encoding="utf-8")

                    # Check if file exports or could export this symbol
                    # Look for function/const/class definitions with similar names
                    if re.search(rf"\b{re.escape(missing_export)}\b", content):
                        # File contains the symbol name
                        rel_path = path.relative_to(working_path)
                        self.logger.info(
                            "found_potential_export_source",
                            missing_export=missing_export,
                            file=str(rel_path),
                        )
                        return str(rel_path)

                except Exception:
                    continue

        return None

    async def _find_possible_paths(self, target_module: Optional[str]) -> list[str]:
        """Find possible correct paths for a module."""
        if not target_module:
            return []

        results = []
        module_name = Path(target_module).name
        working_path = Path(self.working_dir)

        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            for path in working_path.rglob(f"*{module_name}{ext}"):
                if "node_modules" not in str(path):
                    results.append(str(path.relative_to(working_path)))

        return results

    async def _read_file(self, file_path: str) -> Optional[str]:
        """Read a file from the working directory."""
        try:
            full_path = Path(self.working_dir) / file_path
            if full_path.exists():
                return full_path.read_text(encoding="utf-8")
            return None
        except Exception as e:
            self.logger.error("file_read_error", path=file_path, error=str(e))
            return None

    async def _fix_duplicate_identifier(self, error_data: dict) -> bool:
        """
        Fix duplicate identifier errors (e.g., same import declared twice).

        Error: "Identifier 'BillingDashboard' has already been declared"

        Strategy:
        1. Find the file with duplicate imports
        2. Use Claude to remove duplicate import statements
        3. Keep only one import per identifier
        """
        raw_error = error_data.get("raw_error", "")
        source_file = error_data.get("source_file")
        duplicate_name = error_data.get("duplicate_name")

        # Extract duplicate name from error if not provided
        if not duplicate_name:
            match = re.search(r"Identifier ['\"]?([^'\"]+)['\"]? has already been declared", raw_error)
            if match:
                duplicate_name = match.group(1)

        if not duplicate_name:
            self.logger.warning("could_not_extract_duplicate_name", raw_error=raw_error)
            return False

        # Find the file with the error - usually App.tsx or an index file
        if not source_file:
            # Search for files that might have the duplicate
            source_file = await self._find_file_with_duplicate(duplicate_name)

        if not source_file:
            # Default to App.tsx as most common case
            possible_files = ["src/App.tsx", "src/index.tsx", "src/main.tsx"]
            for f in possible_files:
                full_path = Path(self.working_dir) / f
                if full_path.exists():
                    source_file = f
                    break

        if not source_file:
            self.logger.warning("source_file_not_found_for_duplicate")
            return False

        # Read the file
        file_content = await self._read_file(source_file)
        if not file_content:
            return False

        prompt = f"""Fix the duplicate identifier error in this file.

ERROR: Identifier '{duplicate_name}' has already been declared

FILE: {source_file}

CURRENT CONTENT:
```typescript
{file_content}
```

TASK:
1. Find all import statements that import '{duplicate_name}'
2. Keep only ONE import statement for '{duplicate_name}' (preferably the first one)
3. Remove all duplicate imports of the same identifier
4. Make sure the file still compiles correctly

Write the complete fixed file to {source_file}.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing duplicate identifier '{duplicate_name}' in {source_file}",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fixed_file": source_file,
                        "fix_type": "duplicate_identifier",
                        "duplicate_name": duplicate_name,
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                return True

            return False

        except Exception as e:
            self.logger.error("duplicate_fix_exception", error=str(e))
            return False

    async def _find_file_with_duplicate(self, duplicate_name: str) -> Optional[str]:
        """Find the file that contains duplicate imports of a name."""
        working_path = Path(self.working_dir)

        # Search for files that import this name multiple times
        for ext in [".tsx", ".ts", ".jsx", ".js"]:
            for path in working_path.rglob(f"*{ext}"):
                if "node_modules" in str(path):
                    continue

                try:
                    content = path.read_text(encoding="utf-8")
                    # Count import occurrences
                    import_pattern = rf"import\s*\{{[^}}]*\b{re.escape(duplicate_name)}\b[^}}]*\}}"
                    matches = re.findall(import_pattern, content)
                    if len(matches) > 1:
                        return str(path.relative_to(working_path))
                except Exception:
                    continue

        return None

    async def _fix_require_not_defined(self, error_data: dict) -> bool:
        """
        Fix 'require is not defined' errors (CommonJS in ESM context).

        Error: "ReferenceError: require is not defined"

        This happens when:
        1. Code uses require() but the project is ESM (type: module)
        2. A dependency exports CommonJS but is imported as ESM

        Strategy:
        1. Find the file with require()
        2. Replace require() with ESM import statements
        """
        raw_error = error_data.get("raw_error", "")
        source_file = error_data.get("source_file")

        # Extract source file from error if not provided
        if not source_file:
            # Try to extract from error like "at index.ts:14:51"
            match = re.search(r"at\s+([^:]+\.[tj]sx?):(\d+)", raw_error)
            if match:
                source_file = match.group(1)

        if not source_file:
            # Search for files with require() calls
            source_file = await self._find_file_with_require()

        if not source_file:
            self.logger.warning("could_not_find_file_with_require")
            return False

        # Read the file
        file_content = await self._read_file(source_file)
        if not file_content:
            return False

        prompt = f"""Fix the 'require is not defined' error in this file.

ERROR: ReferenceError: require is not defined
FILE: {source_file}

CURRENT CONTENT:
```typescript
{file_content}
```

TASK:
1. Find all require() calls in the file
2. Convert each require() to ESM import syntax:
   - const x = require('module') → import x from 'module'
   - const {{ a, b }} = require('module') → import {{ a, b }} from 'module'
   - require.resolve() → Use import.meta.resolve() or remove if not needed
3. For dynamic requires, use dynamic import(): await import('module')
4. Make sure all imports are at the top of the file

Write the complete fixed file to {source_file}.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing require() calls in {source_file}",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fixed_file": source_file,
                        "fix_type": "require_not_defined",
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                return True

            return False

        except Exception as e:
            self.logger.error("require_fix_exception", error=str(e))
            return False

    async def _find_file_with_require(self) -> Optional[str]:
        """Find a TypeScript/JavaScript file that uses require()."""
        working_path = Path(self.working_dir)

        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            for path in working_path.rglob(f"*{ext}"):
                if "node_modules" in str(path):
                    continue

                try:
                    content = path.read_text(encoding="utf-8")
                    if re.search(r"\brequire\s*\(", content):
                        return str(path.relative_to(working_path))
                except Exception:
                    continue

        return None

    async def _fix_syntax_error(self, error_data: dict) -> bool:
        """
        Fix syntax errors in code.

        Error: "SyntaxError: ..."

        Strategy:
        1. Find the file with the syntax error
        2. Use Claude to fix the syntax issue
        """
        raw_error = error_data.get("raw_error", "")
        source_file = error_data.get("source_file")

        # Try to extract source file from error
        if not source_file:
            match = re.search(r"([^:\s]+\.[tj]sx?):(\d+)", raw_error)
            if match:
                source_file = match.group(1)

        if not source_file:
            self.logger.warning("could_not_find_file_for_syntax_error")
            # Try generic fix
            return await self._fix_generic_error(error_data)

        # Read the file
        file_content = await self._read_file(source_file)
        if not file_content:
            return False

        prompt = f"""Fix the syntax error in this file.

ERROR: {raw_error}

FILE: {source_file}

CURRENT CONTENT:
```typescript
{file_content}
```

TASK:
1. Find the syntax error in the code
2. Fix the syntax issue (missing brackets, semicolons, invalid expressions, etc.)
3. Make sure the code compiles correctly

Write the complete fixed file to {source_file}.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing syntax error in {source_file}",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fixed_file": source_file,
                        "fix_type": "syntax_error",
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                return True

            return False

        except Exception as e:
            self.logger.error("syntax_fix_exception", error=str(e))
            return False

    async def _fix_generic_error(self, error_data: dict) -> bool:
        """
        Generic fallback for unknown error types.

        Uses Claude to analyze and fix any code error based on the raw error message.
        """
        raw_error = error_data.get("raw_error", "")
        source_file = error_data.get("source_file")
        code_error_type = error_data.get("code_error_type", "unknown")

        if not raw_error:
            self.logger.warning("no_raw_error_for_generic_fix")
            return False

        # Try to find source file from error
        if not source_file:
            match = re.search(r"([^:\s]+\.[tj]sx?)", raw_error)
            if match:
                source_file = match.group(1)

        context_content = ""
        if source_file:
            file_content = await self._read_file(source_file)
            if file_content:
                context_content = f"""

SOURCE FILE: {source_file}
```typescript
{file_content}
```
"""

        prompt = f"""Fix this code error.

ERROR TYPE: {code_error_type}
ERROR MESSAGE:
{raw_error}
{context_content}

Analyze the error and fix it. Common fixes include:
- Missing imports or exports
- Syntax errors
- Type mismatches
- Undefined variables
- Module resolution issues

Apply the appropriate fix.
"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context=f"Fixing {code_error_type} error",
                agent_type="general",
            )

            if result.success and result.files:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "fix_type": "generic",
                        "original_error_type": code_error_type,
                        "files_modified": [f.path for f in result.files],
                    },
                ))
                return True

            return False

        except Exception as e:
            self.logger.error("generic_fix_exception", error=str(e))
            return False
