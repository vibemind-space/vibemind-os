"""
ContinuousDebugAgent - Real-time debugging during code generation.

This agent:
1. Runs alongside AI code generation
2. Listens for sandbox test failures (BUILD_FAILED, SANDBOX_TEST_FAILED)
3. Analyzes errors using Claude Code
4. Generates and applies fixes
5. Syncs fixed files to running container
6. Triggers hot-reload/rebuild
7. Repeats until app runs successfully

The key innovation: Instead of waiting for generation to finish,
this agent provides immediate feedback and fixes during the generation process.
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from ..mind.event_bus import (
    Event, EventType, EventBus,
    debug_started_event,
    file_created_event,
    code_fixed_event,
    debug_complete_event,
)
from ..mind.shared_state import SharedState
from ..mind.event_payloads import (
    SandboxTestPayload,
    BuildFailurePayload,
    TypeErrorPayload,
)
from ..utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)

logger = structlog.get_logger(__name__)


@dataclass
class ClassifiedError:
    """Error with LLM-assigned classification."""
    original_error: dict
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    fix_complexity: str  # trivial, moderate, complex
    suggested_fix: str
    category: str  # syntax, type, import, runtime, logic


class ContainerFileSyncer:
    """Syncs files to a running Docker container."""
    
    def __init__(self, container_id: str, working_dir: str):
        self.container_id = container_id
        self.working_dir = Path(working_dir)
        self.logger = logger.bind(component="file_syncer", container=container_id[:12])
    
    async def sync_file(self, file_path: str) -> bool:
        """
        Sync a single file to the container.
        
        Args:
            file_path: Relative path to file
            
        Returns:
            True if sync succeeded
        """
        local_path = self.working_dir / file_path
        container_path = f"/app/{file_path}"
        
        if not local_path.exists():
            self.logger.warning("file_not_found", path=file_path)
            return False
        
        cmd = ["docker", "cp", str(local_path), f"{self.container_id}:{container_path}"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            
            if process.returncode == 0:
                self.logger.debug("file_synced", path=file_path)
                return True
            else:
                self.logger.error("sync_failed", path=file_path, error=stderr.decode())
                return False
                
        except asyncio.TimeoutError:
            self.logger.error("sync_timeout", path=file_path)
            return False
        except Exception as e:
            self.logger.error("sync_error", path=file_path, error=str(e))
            return False
    
    async def sync_files(self, file_paths: list[str]) -> dict[str, bool]:
        """
        Sync multiple files to the container.
        
        Returns:
            Dict mapping file paths to sync success status
        """
        results = {}
        for path in file_paths:
            results[path] = await self.sync_file(path)
        return results
    
    async def trigger_rebuild(self) -> bool:
        """
        Trigger a rebuild in the container.
        
        Sends a signal to rebuild/restart the app.
        """
        # Method 1: Touch a trigger file that the entrypoint watches
        touch_cmd = ["docker", "exec", self.container_id, "touch", "/tmp/rebuild_trigger"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *touch_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=10)
            
            # Method 2: Kill the app process to trigger restart
            # The entrypoint should restart it automatically
            kill_cmd = ["docker", "exec", self.container_id, 
                       "bash", "-c", "pkill -f 'node|vite|npm' 2>/dev/null || true"]
            
            process = await asyncio.create_subprocess_exec(
                *kill_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=10)
            
            self.logger.info("rebuild_triggered")
            return True
            
        except Exception as e:
            self.logger.error("rebuild_trigger_failed", error=str(e))
            return False


class DebugCycleResult:
    """Result of a single debug cycle."""
    
    def __init__(
        self,
        cycle_number: int,
        errors_found: int,
        fixes_attempted: int,
        fixes_applied: int,
        files_synced: list[str],
        success: bool,
        duration_ms: int,
        error_message: Optional[str] = None,
    ):
        self.cycle_number = cycle_number
        self.errors_found = errors_found
        self.fixes_attempted = fixes_attempted
        self.fixes_applied = fixes_applied
        self.files_synced = files_synced
        self.success = success
        self.duration_ms = duration_ms
        self.error_message = error_message
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_number": self.cycle_number,
            "errors_found": self.errors_found,
            "fixes_attempted": self.fixes_attempted,
            "fixes_applied": self.fixes_applied,
            "files_synced": self.files_synced,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }


class ContinuousDebugAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Agent that provides real-time debugging during code generation.
    
    Workflow:
    1. Listens for SANDBOX_TEST_FAILED, BUILD_FAILED events
    2. Extracts error details from event data
    3. Uses Claude Code to analyze and fix errors
    4. Syncs fixed files to running container
    5. Triggers rebuild/restart
    6. Repeats until success or max iterations reached
    
    Key Features:
    - Real-time feedback during generation (not after)
    - Automatic file sync to container
    - Hot-reload support
    - VNC preview integration (see fixes applied live)
    
    Events Published:
    - DEBUG_CYCLE_STARTED
    - DEBUG_CYCLE_COMPLETE
    - CODE_FIXED (when fixes are applied)
    - DEBUG_CONVERGED (when app runs successfully)
    """
    
    def __init__(
        self,
        name: str = "ContinuousDebug",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        poll_interval: float = 2.0,
        memory_tool: Optional[Any] = None,
        # Debug config
        max_debug_iterations: int = 50,
        debug_cooldown_seconds: int = 5,
        enable_file_sync: bool = True,
        enable_hot_reload: bool = True,
        # Container config
        container_id: Optional[str] = None,
        # Claude config
        claude_timeout: int = 120,
    ):
        """
        Initialize the continuous debug agent.
        
        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project directory
            poll_interval: Seconds between event checks
            memory_tool: Optional memory tool
            max_debug_iterations: Max fix attempts per error group
            debug_cooldown_seconds: Cooldown between debug cycles
            enable_file_sync: Sync fixed files to container
            enable_hot_reload: Trigger rebuild after sync
            container_id: Docker container ID (set dynamically)
            claude_timeout: Timeout for Claude API calls
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )
        
        self.max_debug_iterations = max_debug_iterations
        self.debug_cooldown_seconds = debug_cooldown_seconds
        self.enable_file_sync = enable_file_sync
        self.enable_hot_reload = enable_hot_reload
        self.container_id = container_id
        self.claude_timeout = claude_timeout
        
        # State
        self._debug_count = 0
        self._total_fixes = 0
        self._last_debug_time: Optional[datetime] = None
        self._file_syncer: Optional[ContainerFileSyncer] = None
        self._recent_errors: list[str] = []  # Track recent errors to avoid loops
        self._consecutive_failures = 0
        self._detected_frameworks: list[str] = []  # Cache detected frameworks

        # Container Log Seeder reference (set during orchestrator init)
        self._container_log_seeder = None

    def set_container_log_seeder(self, seeder) -> None:
        """Set the ContainerLogSeeder reference for log retrieval."""
        self._container_log_seeder = seeder
        self.logger.debug("container_log_seeder_attached")

    def get_container_logs_history(
        self,
        container_name: str = None,
        limit: int = 3,
        search_pattern: str = None
    ) -> list[dict]:
        """
        Retrieve historical container logs from the ContainerLogSeeder.

        Args:
            container_name: Container name (uses current container_id if None)
            limit: Maximum number of log entries to retrieve
            search_pattern: Optional pattern to search for in logs

        Returns:
            List of log entries with timestamps and content
        """
        if not self._container_log_seeder:
            self.logger.debug("no_log_seeder_available")
            return []

        name = container_name or (self.container_id[:12] if self.container_id else None)
        if not name:
            return []

        try:
            if search_pattern:
                # Search logs for specific pattern (e.g., "Error", "Exception")
                results = self._container_log_seeder.search_logs(
                    pattern=search_pattern,
                    container_name=name,
                )
                return results[:limit]
            else:
                # Get latest logs
                return self._container_log_seeder.get_latest_logs(name, limit)
        except Exception as e:
            self.logger.warning("log_retrieval_failed", error=str(e))
            return []

    def _detect_frameworks(self) -> list[str]:
        """
        Detect frameworks/technologies used in the project.

        Returns:
            List of detected framework names (e.g., ['fastapi', 'react', 'typescript'])
        """
        if self._detected_frameworks:
            return self._detected_frameworks

        frameworks = []
        project_dir = Path(self.working_dir)

        # Python frameworks
        requirements_txt = project_dir / "requirements.txt"
        pyproject_toml = project_dir / "pyproject.toml"

        python_deps = ""
        if requirements_txt.exists():
            python_deps = requirements_txt.read_text(errors='replace').lower()
        if pyproject_toml.exists():
            python_deps += pyproject_toml.read_text(errors='replace').lower()

        if "fastapi" in python_deps:
            frameworks.append("fastapi")
        if "django" in python_deps:
            frameworks.append("django")
        if "flask" in python_deps:
            frameworks.append("flask")
        if "uvicorn" in python_deps:
            frameworks.append("uvicorn")
        if "pydantic" in python_deps:
            frameworks.append("pydantic")

        # Node/JavaScript frameworks
        package_json = project_dir / "package.json"
        if package_json.exists():
            try:
                import json
                pkg = json.loads(package_json.read_text(errors='replace'))
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

                if "react" in deps:
                    frameworks.append("react")
                if "vue" in deps:
                    frameworks.append("vue")
                if "express" in deps:
                    frameworks.append("express")
                if "typescript" in deps:
                    frameworks.append("typescript")
                if "electron" in deps:
                    frameworks.append("electron")
            except Exception:
                pass

        self._detected_frameworks = frameworks
        return frameworks

    def _build_framework_aware_prompt(self, errors_text: str) -> str:
        """
        Build a fix prompt with framework-specific guidance.

        Args:
            errors_text: Formatted error text

        Returns:
            Complete prompt with framework-specific hints
        """
        frameworks = self._detect_frameworks()

        base_instructions = """
Instructions:
1. Analyze each error carefully
2. Identify the root cause
3. Create or modify files to fix the errors
4. For missing imports: add the correct import statements
5. For type errors: fix type definitions or add type assertions
6. For build errors: ensure all dependencies and syntax are correct
7. For sandbox errors: check that the app can start correctly

Focus on fixing the most critical errors first. Implement complete solutions."""

        # Add framework-specific guidance
        framework_hints = []

        if "fastapi" in frameworks:
            framework_hints.append("""
## FastAPI-Specific Guidance:
- For "non-body parameters must be in path, query, header or cookie" errors:
  - NEVER use `password: str` as a direct route parameter
  - Always wrap password in a Pydantic BaseModel for request body
  - Use `from fastapi import Body` for explicit body parameters
  - Example fix: `class LoginRequest(BaseModel): username: str; password: str`
- For form data (OAuth2PasswordRequestForm): ensure `python-multipart` is installed
- For validation errors: check Pydantic model field definitions
- For startup errors: check all route parameter annotations are valid""")

        if "pydantic" in frameworks:
            framework_hints.append("""
## Pydantic-Specific Guidance:
- Use Field() for validation constraints (min_length, max_length)
- Use Optional[] for nullable fields with default None
- Use @field_validator for custom validation
- Ensure all model fields have type annotations""")

        if "react" in frameworks:
            framework_hints.append("""
## React-Specific Guidance:
- For hook errors: ensure hooks are called at component top level
- For import errors: check relative paths and file extensions
- For state errors: use useState/useReducer correctly
- For prop errors: verify prop types match component expectations""")

        if "typescript" in frameworks:
            framework_hints.append("""
## TypeScript-Specific Guidance:
- For type errors: add explicit type annotations
- For import errors: check tsconfig paths and module resolution
- For interface errors: ensure all required properties are defined
- Use 'as' for type assertions when confident about types""")

        if "electron" in frameworks:
            framework_hints.append("""
## Electron-Specific Guidance:
- Separate main process and renderer process code
- Use contextBridge and preload scripts for IPC
- Check nodeIntegration and contextIsolation settings
- Ensure proper path handling for packaged apps""")

        # Build final prompt
        framework_section = "\n".join(framework_hints) if framework_hints else ""

        prompt = f"""Fix the following errors in this project:

{errors_text}
{base_instructions}
{framework_section}
"""
        return prompt

    async def _classify_error_patterns(
        self, errors: list[dict]
    ) -> list[ClassifiedError]:
        """
        Use LLM to classify errors by severity and fix urgency.

        This enables smarter prioritization - fix critical errors first,
        and potentially skip low-priority issues during rapid iteration.

        Args:
            errors: List of extracted error dictionaries

        Returns:
            List of ClassifiedError with severity and fix guidance
        """
        if not errors:
            return []

        from ..tools.claude_code_tool import ClaudeCodeTool

        # Format errors for LLM
        errors_text = "\n".join([
            f"[{i}] Type: {e.get('type', 'unknown')}, "
            f"File: {e.get('file', 'Unknown')}, "
            f"Message: {e.get('message', 'Unknown')[:200]}"
            for i, e in enumerate(errors[:20])
        ])

        prompt = f"""Classify these build/runtime errors by severity and urgency.

## ERRORS:
{errors_text}

## CLASSIFICATION CRITERIA:

**CRITICAL** - Blocks execution entirely:
- Syntax errors preventing parse
- Missing required modules/imports
- Application crash on startup

**HIGH** - Breaks core functionality:
- Type errors in critical paths
- Undefined property access
- Missing required props

**MEDIUM** - Degraded but functional:
- Console warnings
- Deprecation notices
- Non-critical type mismatches

**LOW** - Style/quality issues:
- Unused variables
- Formatting issues
- Optional type annotations

## RESPONSE FORMAT:
Return JSON array with classification for each error:
```json
[
  {{
    "index": 0,
    "severity": "CRITICAL|HIGH|MEDIUM|LOW",
    "fix_complexity": "trivial|moderate|complex",
    "category": "syntax|type|import|runtime|logic|style",
    "suggested_fix": "Brief description of how to fix"
  }}
]
```
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context="Error classification for debug prioritization",
                agent_type="error_classifier",
            )

            # Parse JSON from response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                classifications = json.loads(json_match.group(1))

                classified_errors = []
                for cls in classifications:
                    idx = cls.get("index", 0)
                    if idx < len(errors):
                        classified_errors.append(ClassifiedError(
                            original_error=errors[idx],
                            severity=cls.get("severity", "HIGH"),
                            fix_complexity=cls.get("fix_complexity", "moderate"),
                            suggested_fix=cls.get("suggested_fix", ""),
                            category=cls.get("category", "unknown"),
                        ))

                self.logger.info(
                    "errors_classified",
                    total=len(errors),
                    critical=sum(1 for e in classified_errors if e.severity == "CRITICAL"),
                    high=sum(1 for e in classified_errors if e.severity == "HIGH"),
                )

                return classified_errors

        except Exception as e:
            self.logger.warning("error_classification_failed", error=str(e))

        # Fallback: return all errors as HIGH severity
        return [
            ClassifiedError(
                original_error=e,
                severity="HIGH",
                fix_complexity="moderate",
                suggested_fix="",
                category="unknown",
            )
            for e in errors
        ]

    def _prioritize_errors_by_severity(
        self, classified_errors: list[ClassifiedError]
    ) -> list[dict]:
        """
        Sort errors by severity for fix prioritization.

        Returns original error dicts sorted by severity (CRITICAL first).
        """
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_errors = sorted(
            classified_errors,
            key=lambda e: severity_order.get(e.severity, 2)
        )
        return [e.original_error for e in sorted_errors]

    async def humanize_error_message(self, raw_error: str) -> dict:
        """
        Use pattern classification with LLM fallback to translate technical errors.

        Uses multi-tier approach:
        1. Check cache for previously humanized similar errors
        2. Use pattern-based humanization for known error types (fast)
        3. Fall back to LLM for unknown error types
        4. Cache successful humanizations for future use

        Args:
            raw_error: Raw technical error message (TypeScript, runtime, etc.)

        Returns:
            Dict with humanized explanation and fix guidance:
            {
                "explanation": str,     # Plain English explanation
                "location": str,        # File/line that caused it
                "fix_hint": str,        # What needs to change
                "common_causes": [str], # Common reasons for this error
                "search_terms": [str],  # Terms to search for solutions
                "original_error": str   # Original error for reference
            }
        """
        if not raw_error or len(raw_error.strip()) < 5:
            return {
                "explanation": "Empty or invalid error message",
                "location": "Unknown",
                "fix_hint": "Check build output for details",
                "common_causes": [],
                "search_terms": [],
                "original_error": raw_error,
            }

        # Use classification cache for error type detection
        cache = get_classification_cache()
        key = cache._generate_key(raw_error, "humanize")

        # Check cache first
        cached = await cache.get(key)
        if cached and cached.metadata.get("humanized"):
            self.logger.debug(
                "humanization_cache_hit",
                source=cached.source.value,
                category=cached.category,
            )
            humanized = cached.metadata["humanized"]
            humanized["original_error"] = raw_error[:500]
            return humanized

        # Try pattern-based classification first (fast path)
        classification = self._pattern_classify_for_humanization(raw_error)
        if classification.confidence >= 0.8:
            # Use pre-defined humanization for known error types
            humanized = self._get_humanization_for_type(classification.category, raw_error)

            # Cache the result
            classification.metadata["humanized"] = humanized
            await cache.set(key, classification)

            self.logger.debug(
                "humanization_pattern_match",
                category=classification.category,
                confidence=f"{classification.confidence:.2f}",
            )
            return humanized

        # LLM fallback for unknown error types
        humanized = await self._llm_humanize_error(raw_error)

        # Cache successful LLM humanization
        result = ClassificationResult(
            category=humanized.get("error_type", "unknown"),
            confidence=0.9,
            source=ClassificationSource.LLM,
            metadata={"humanized": humanized},
        )
        await cache.set(key, result)

        return humanized

    def _pattern_classify_for_humanization(self, raw_error: str) -> ClassificationResult:
        """Fast pattern-based classification for humanization."""
        error_lower = raw_error.lower()

        patterns = [
            (["cannot find module"], "module_not_found", 0.95),
            (["module not found"], "module_not_found", 0.95),
            (["is not assignable to"], "type_mismatch", 0.9),
            (["property", "does not exist"], "property_not_exist", 0.9),
            (["undefined"], "null_undefined", 0.7),
            (["null"], "null_undefined", 0.7),
            (["syntax error"], "syntax_error", 0.95),
            (["unexpected token"], "syntax_error", 0.9),
            (["enoent"], "file_not_found", 0.9),
            (["no such file"], "file_not_found", 0.85),
            (["permission denied"], "permission_error", 0.9),
            (["eacces"], "permission_error", 0.9),
            (["timeout"], "timeout_error", 0.85),
            (["connection refused"], "connection_error", 0.9),
            (["econnrefused"], "connection_error", 0.9),
        ]

        for keywords, category, confidence in patterns:
            if all(kw in error_lower for kw in keywords):
                return ClassificationResult(
                    category=category,
                    confidence=confidence,
                    source=ClassificationSource.PATTERN,
                    metadata={"matched_keywords": keywords},
                )

        return ClassificationResult(
            category="unknown",
            confidence=0.0,
            source=ClassificationSource.PATTERN,
        )

    def _get_humanization_for_type(self, error_type: str, raw_error: str) -> dict:
        """Get pre-defined humanization for known error types."""
        # Extract location from error
        location = self._extract_location(raw_error)

        humanization_map = {
            "module_not_found": {
                "explanation": "A required module or file cannot be found",
                "fix_hint": "Check import paths and ensure the module is installed",
                "common_causes": ["Typo in import path", "Missing npm install", "Wrong relative path"],
                "search_terms": ["cannot find module", "module not found npm"],
            },
            "type_mismatch": {
                "explanation": "TypeScript type mismatch - a value doesn't match its expected type",
                "fix_hint": "Check the type definitions and ensure values match",
                "common_causes": ["Wrong type annotation", "Missing type conversion", "Interface mismatch"],
                "search_terms": ["typescript not assignable", "type mismatch"],
            },
            "property_not_exist": {
                "explanation": "Accessing a property that doesn't exist on the type",
                "fix_hint": "Add the missing property to the type or check for typos",
                "common_causes": ["Typo in property name", "Missing interface property", "Optional property access"],
                "search_terms": ["property does not exist on type", "typescript missing property"],
            },
            "null_undefined": {
                "explanation": "Trying to use a value that is undefined or null",
                "fix_hint": "Add null check or ensure the value is initialized",
                "common_causes": ["Missing initialization", "Async timing issue", "Optional chaining needed"],
                "search_terms": ["cannot read property undefined", "null reference error"],
            },
            "syntax_error": {
                "explanation": "Invalid code syntax that the parser cannot understand",
                "fix_hint": "Check for missing brackets, quotes, or semicolons near the error",
                "common_causes": ["Missing closing bracket", "Unclosed string", "Invalid JSX"],
                "search_terms": ["syntax error javascript", "unexpected token"],
            },
            "file_not_found": {
                "explanation": "A file or directory doesn't exist at the specified path",
                "fix_hint": "Verify the file path and create missing files/directories",
                "common_causes": ["Wrong file path", "File not created yet", "Case sensitivity"],
                "search_terms": ["ENOENT no such file", "file not found node"],
            },
            "permission_error": {
                "explanation": "Insufficient permissions to access a file or resource",
                "fix_hint": "Check file permissions or run with appropriate privileges",
                "common_causes": ["File owned by root", "Locked by another process", "Protected directory"],
                "search_terms": ["EACCES permission denied", "npm permission error"],
            },
            "timeout_error": {
                "explanation": "An operation took too long and was cancelled",
                "fix_hint": "Increase timeout value or optimize the slow operation",
                "common_causes": ["Slow network", "Heavy computation", "Deadlock"],
                "search_terms": ["timeout error node", "async timeout"],
            },
            "connection_error": {
                "explanation": "Cannot connect to a remote service or database",
                "fix_hint": "Check if the service is running and network configuration",
                "common_causes": ["Service not started", "Wrong port/host", "Firewall blocking"],
                "search_terms": ["connection refused", "ECONNREFUSED"],
            },
        }

        base = humanization_map.get(error_type, {
            "explanation": "An error occurred during build/runtime",
            "fix_hint": "Check the error message details",
            "common_causes": [],
            "search_terms": [],
        })

        return {
            **base,
            "location": location,
            "original_error": raw_error[:500],
            "error_type": error_type,
        }

    def _extract_location(self, raw_error: str) -> str:
        """Extract file:line location from error message."""
        location_patterns = [
            r'([a-zA-Z0-9_/\\.-]+\.[a-zA-Z]+):(\d+):?(\d+)?',
            r'at ([a-zA-Z0-9_/\\.-]+\.[a-zA-Z]+):(\d+)',
            r'in ([a-zA-Z0-9_/\\.-]+\.[a-zA-Z]+) \(line (\d+)\)',
        ]

        for pattern in location_patterns:
            match = re.search(pattern, raw_error)
            if match:
                return f"{match.group(1)}:{match.group(2)}"

        return "Unknown"

    async def _llm_humanize_error(self, raw_error: str) -> dict:
        """Use LLM to humanize unknown error types."""
        from ..tools.claude_code_tool import ClaudeCodeTool

        prompt = f"""Translate this technical error to plain English for a developer:

## ERROR:
{raw_error[:2000]}

## YOUR TASK:
Provide a clear, helpful explanation that a developer can act on.

## RESPONSE FORMAT:
Return JSON:
```json
{{
  "explanation": "One clear sentence explaining what's wrong",
  "location": "file.ts:42 or 'build process' or 'runtime'",
  "fix_hint": "Specific action: 'Add import X to file Y' or 'Change type from A to B'",
  "common_causes": [
    "Missing import statement",
    "Type mismatch between function and caller"
  ],
  "search_terms": ["typescript cannot find module", "TS2307"],
  "error_type": "category like module_not_found, type_error, syntax_error, etc."
}}
```

## GUIDELINES:
- explanation: ONE sentence, no jargon, explain the actual problem
- location: Extract file:line if present, otherwise describe where (build/runtime/test)
- fix_hint: Be SPECIFIC - say exactly what to change, not "fix the error"
- common_causes: 2-3 most likely reasons (not generic "check your code")
- search_terms: Terms that would find Stack Overflow answers
- error_type: Classify the error type for caching
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=45)
            result = await tool.execute(
                prompt=prompt,
                context="Error humanization for developer feedback",
                agent_type="error_humanizer",
            )

            # Parse JSON from response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                humanized = json.loads(json_match.group(1))
                humanized["original_error"] = raw_error[:500]

                self.logger.debug(
                    "error_humanized_llm",
                    explanation=humanized.get("explanation", "")[:100],
                    location=humanized.get("location", ""),
                )

                return humanized

        except Exception as e:
            self.logger.warning("error_humanization_failed", error=str(e))

        # Final fallback if LLM fails
        return self._get_humanization_for_type("unknown", raw_error)

    async def humanize_errors_batch(self, errors: list[dict]) -> list[dict]:
        """
        Humanize multiple errors efficiently.

        Processes errors in batch to reduce LLM calls while providing
        human-readable explanations for each error.

        Args:
            errors: List of error dicts with 'message' field

        Returns:
            List of humanized error dicts
        """
        if not errors:
            return []

        humanized = []
        for error in errors[:10]:  # Limit to prevent overload
            message = error.get("message", "") or error.get("error_message", "")
            if message:
                result = await self.humanize_error_message(message)
                # Merge with original error data
                humanized.append({
                    **error,
                    "humanized": result,
                })
            else:
                humanized.append({
                    **error,
                    "humanized": {
                        "explanation": "Error without message",
                        "location": error.get("file", "Unknown"),
                        "fix_hint": "Check error type and context",
                        "common_causes": [],
                        "search_terms": [],
                        "original_error": str(error)[:200],
                    },
                })

        return humanized

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.SANDBOX_TEST_FAILED,
            EventType.BUILD_FAILED,
            EventType.TYPE_ERROR,
            # Also listen for container info
            EventType.SANDBOX_TEST_STARTED,
            EventType.SCREEN_STREAM_READY,
        ]
    
    def set_container_id(self, container_id: str) -> None:
        """Set the container ID for file syncing."""
        self.container_id = container_id
        if self.enable_file_sync:
            self._file_syncer = ContainerFileSyncer(container_id, self.working_dir)
        self.logger.info("container_id_set", container=container_id[:12] if container_id else None)
    
    async def should_act(self, events: list[Event]) -> bool:
        """Decide if we should attempt to debug."""
        # Check cooldown
        if self._last_debug_time:
            elapsed = (datetime.now() - self._last_debug_time).total_seconds()
            if elapsed < self.debug_cooldown_seconds:
                return False
        
        # Check if we've exceeded max iterations
        if self._consecutive_failures >= self.max_debug_iterations:
            self.logger.warning(
                "max_debug_iterations_reached",
                iterations=self._consecutive_failures,
            )
            return False
        
        # Update container ID from events
        for event in events:
            if event.type == EventType.SANDBOX_TEST_STARTED:
                # Use typed payload if available
                if event.typed and isinstance(event.typed, SandboxTestPayload):
                    container_id = event.typed.container_id
                else:
                    container_id = event.data.get("container_id")
                if container_id:
                    self.set_container_id(container_id)
            elif event.type == EventType.SCREEN_STREAM_READY:
                # Use typed payload if available
                if event.typed and isinstance(event.typed, SandboxTestPayload):
                    container_id = event.typed.container_id
                else:
                    container_id = event.data.get("container_id")
                if container_id:
                    self.set_container_id(container_id)
        
        # Check for failure events - always act on failure event types
        # Note: Don't check event.success since failure events may not have it set
        for event in events:
            if event.type in [EventType.SANDBOX_TEST_FAILED, EventType.BUILD_FAILED, EventType.TYPE_ERROR]:
                return True

        return False
    
    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Execute debug cycle. Dispatches to autogen team or legacy.
        """
        self.logger.info(
            "debug_cycle_dispatch",
            mode="autogen" if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true" else "legacy",
        )
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """
        Debug cycle using autogen team: DebugAnalyst + FixOperator.

        Preserves container sync, hot reload, and framework detection.
        """
        self._last_debug_time = datetime.now()
        self._debug_count += 1
        start_time = datetime.now()

        await self.event_bus.publish(debug_started_event(
            source=self.name,
            cycle=self._debug_count,
            working_dir=self.working_dir,
        ))

        error_context = self._extract_errors(events)
        if not error_context:
            return None

        # Build error text
        errors_text = "\n\n".join([
            f"Error Type: {e.get('type', 'unknown')}\n"
            f"File: {e.get('file', 'Unknown')}\n"
            f"Line: {e.get('line', 'Unknown')}\n"
            f"Message: {e.get('message', 'Unknown error')}\n"
            f"Code: {e.get('code', '')}\n"
            f"Details: {e.get('stdout', '')} {e.get('stderr', '')}"
            for e in error_context
        ])

        # Use framework-aware prompt
        prompt = self._build_framework_aware_prompt(errors_text)

        try:
            team = self.create_team(
                operator_name="DebugAnalyst",
                operator_prompt=(
                    "You are a real-time debug analyst for running applications. "
                    "Analyze build errors, sandbox failures, and type errors. "
                    "Identify root causes from error messages, container logs, and stack traces. "
                    "Apply targeted fixes to source files. "
                    "Focus on getting the application running — fix critical errors first. "
                    "After applying fixes, say TASK_COMPLETE."
                ),
                validator_name="FixValidator",
                validator_prompt=(
                    "You validate debug fixes for running applications. Check:\n"
                    "1. Fix addresses the actual error, not a symptom\n"
                    "2. Application can start after the fix\n"
                    "3. No new import or type errors introduced\n"
                    "4. Fix is minimal and targeted\n"
                    "If the fix looks correct, say TASK_COMPLETE.\n"
                    "If issues remain, describe what needs to change."
                ),
                tool_categories=["filesystem", "npm", "docker"],
                max_turns=15,
                task=prompt,
            )

            result = await self.run_team(team, prompt)

            if result["success"]:
                # Sync files to container if enabled
                if self.enable_file_sync and self._file_syncer:
                    # Note: autogen team modifies files on disk, we need to detect which files changed
                    # For now, trigger a full rebuild
                    if self.enable_hot_reload:
                        await self._file_syncer.trigger_rebuild()

                self._consecutive_failures = 0
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                return code_fixed_event(
                    source=self.name,
                    success=True,
                    extra_data={
                        "cycle_number": self._debug_count,
                        "duration_ms": duration_ms,
                        "mode": "autogen",
                    },
                )
            else:
                self._consecutive_failures += 1
                return debug_complete_event(
                    source=self.name,
                    success=False,
                    error_message=result.get("result_text", "Autogen debug failed"),
                    cycle=self._debug_count,
                    errors_found=len(error_context),
                )

        except Exception as e:
            self.logger.error("autogen_debug_failed", error=str(e))
            self._consecutive_failures += 1
            return debug_complete_event(
                source=self.name,
                success=False,
                error_message=str(e),
                cycle=self._debug_count,
                errors_found=len(error_context),
            )

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """
        Legacy: Execute debug cycle: analyze errors, fix, sync, rebuild.
        """
        self._last_debug_time = datetime.now()
        self._debug_count += 1
        start_time = datetime.now()

        self.logger.info(
            "debug_cycle_starting",
            cycle=self._debug_count,
            consecutive_failures=self._consecutive_failures,
        )
        
        # Publish start event
        await self.event_bus.publish(debug_started_event(
            source=self.name,
            cycle=self._debug_count,
            working_dir=self.working_dir,
        ))
        
        # Collect errors from events
        error_context = self._extract_errors(events)
        
        if not error_context:
            self.logger.info("no_errors_to_fix")
            return None
        
        self.logger.info(
            "errors_extracted",
            count=len(error_context),
            types=[e.get("type") for e in error_context],
        )
        
        try:
            # Step 1: Use Claude to analyze and fix
            fixed_files = await self._fix_errors_with_claude(error_context)
            
            if not fixed_files:
                self.logger.warning("no_fixes_generated")
                self._consecutive_failures += 1
                return self._create_result_event(
                    DebugCycleResult(
                        cycle_number=self._debug_count,
                        errors_found=len(error_context),
                        fixes_attempted=len(error_context),
                        fixes_applied=0,
                        files_synced=[],
                        success=False,
                        duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                        error_message="No fixes generated",
                    )
                )
            
            # Step 2: Sync files to container (if enabled and container available)
            synced_files = []
            if self.enable_file_sync and self._file_syncer:
                sync_results = await self._file_syncer.sync_files(fixed_files)
                synced_files = [f for f, success in sync_results.items() if success]
                self.logger.info("files_synced", count=len(synced_files), files=synced_files)
            
            # Step 3: Trigger hot reload (if enabled)
            if self.enable_hot_reload and self._file_syncer and synced_files:
                await self._file_syncer.trigger_rebuild()
                self.logger.info("hot_reload_triggered")
            
            # Success - reset failure counter
            self._consecutive_failures = 0
            self._total_fixes += len(fixed_files)
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            result = DebugCycleResult(
                cycle_number=self._debug_count,
                errors_found=len(error_context),
                fixes_attempted=len(error_context),
                fixes_applied=len(fixed_files),
                files_synced=synced_files,
                success=True,
                duration_ms=duration_ms,
            )
            
            self.logger.info(
                "debug_cycle_complete",
                cycle=self._debug_count,
                fixes=len(fixed_files),
                synced=len(synced_files),
                duration_ms=duration_ms,
            )
            
            return self._create_result_event(result)
            
        except Exception as e:
            self.logger.error("debug_cycle_error", error=str(e))
            self._consecutive_failures += 1

            return debug_complete_event(
                source=self.name,
                success=False,
                error_message=str(e),
                cycle=self._debug_count,
                errors_found=len(error_context),
            )
    
    def _extract_errors(self, events: list[Event]) -> list[dict[str, Any]]:
        """Extract error details from events."""
        errors = []
        
        for event in events:
            if event.success:
                continue
            
            if event.type == EventType.SANDBOX_TEST_FAILED:
                # Use typed payload if available
                if event.typed and isinstance(event.typed, SandboxTestPayload):
                    payload = event.typed
                    if payload.error_message:
                        errors.append({
                            "type": "sandbox_error",
                            "message": payload.error_message,
                            "container_id": payload.container_id,
                            "container_logs": payload.container_logs,
                        })
                else:
                    # Legacy fallback
                    data = event.data or {}
                    for step in data.get("steps", []):
                        if not step.get("success", True):
                            errors.append({
                                "type": "sandbox_error",
                                "step": step.get("name"),
                                "message": step.get("error_message") or event.error_message,
                                "stdout": step.get("stdout", ""),
                                "stderr": step.get("stderr", ""),
                            })
                    if not errors and event.error_message:
                        errors.append({
                            "type": "sandbox_error",
                            "message": event.error_message,
                            "data": data,
                        })

            elif event.type == EventType.BUILD_FAILED:
                # Use typed payload if available
                if event.typed and isinstance(event.typed, BuildFailurePayload):
                    payload = event.typed
                    for error in payload.errors:
                        errors.append({
                            "type": "build_error",
                            "file": error.get("file"),
                            "line": error.get("line"),
                            "message": error.get("message"),
                            "code": error.get("code"),
                        })
                    # If no individual errors, use general info
                    if not errors and event.error_message:
                        errors.append({
                            "type": "build_error",
                            "message": event.error_message,
                            "errors": payload.error_count,
                            "is_type_error": payload.is_type_error,
                            "is_import_error": payload.is_import_error,
                            "likely_causes": payload.likely_causes,
                        })
                else:
                    # Legacy fallback
                    data = event.data or {}
                    for failure in data.get("failures", []):
                        errors.append({
                            "type": "build_error",
                            "file": failure.get("file"),
                            "line": failure.get("line"),
                            "message": failure.get("message") or failure.get("description"),
                            "code": failure.get("error_code"),
                        })
                    if not errors and event.error_message:
                        errors.append({
                            "type": "build_error",
                            "message": event.error_message,
                            "errors": data.get("errors", 0),
                        })

            elif event.type == EventType.TYPE_ERROR:
                # Use typed payload if available
                if event.typed and isinstance(event.typed, TypeErrorPayload):
                    payload = event.typed
                    for error in payload.errors:
                        errors.append({
                            "type": "type_error",
                            "file": error.get("file"),
                            "line": error.get("line"),
                            "column": error.get("column"),
                            "message": error.get("message"),
                            "code": error.get("code"),
                        })
                else:
                    # Legacy fallback
                    data = event.data or {}
                    for failure in data.get("failures", []):
                        errors.append({
                            "type": "type_error",
                            "file": failure.get("file"),
                            "line": failure.get("line"),
                            "message": failure.get("message") or failure.get("description"),
                            "code": failure.get("error_code"),
                        })

        # Enrich errors with historical logs if container_logs is missing
        errors = self._enrich_errors_with_seeded_logs(errors)

        return errors

    def _enrich_errors_with_seeded_logs(self, errors: list[dict]) -> list[dict]:
        """
        Enrich error context with historical container logs from LogSeeder.

        For sandbox errors without container_logs, fetch from seeded log history.
        """
        if not self._container_log_seeder:
            return errors

        for error in errors:
            if error.get("type") == "sandbox_error" and not error.get("container_logs"):
                container_id = error.get("container_id")
                if container_id:
                    # Get recent logs from seeder
                    historical_logs = self.get_container_logs_history(
                        container_name=container_id[:12] if len(container_id) > 12 else container_id,
                        limit=2,
                    )
                    if historical_logs:
                        # Extract log content from most recent entry
                        latest = historical_logs[0]
                        error["container_logs"] = latest.get("logs", "")
                        error["log_source"] = "seeded_history"
                        error["log_timestamp"] = latest.get("timestamp", "")
                        self.logger.debug(
                            "enriched_error_with_seeded_logs",
                            container_id=container_id[:12],
                            log_lines=len(error["container_logs"].split("\n")) if error["container_logs"] else 0,
                        )

        return errors
    
    async def _fix_errors_with_claude(self, error_context: list[dict]) -> list[str]:
        """
        Use Claude Code Tool to fix errors.

        Returns:
            List of fixed file paths
        """
        from ..tools.claude_code_tool import ClaudeCodeTool
        from ..skills.loader import SkillLoader

        # Load debugging skill for enhanced fix guidance
        skill = None
        try:
            import os
            engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            loader = SkillLoader(engine_root)
            skill = loader.load_skill("debugging")
            if skill:
                self.logger.debug("skill_loaded", skill_name=skill.name, tokens=skill.total_tokens)
        except Exception as e:
            self.logger.debug("skill_load_failed", error=str(e))

        # Build error description
        errors_text = "\n\n".join([
            f"Error Type: {e.get('type', 'unknown')}\n"
            f"File: {e.get('file', 'Unknown')}\n"
            f"Line: {e.get('line', 'Unknown')}\n"
            f"Message: {e.get('message', 'Unknown error')}\n"
            f"Code: {e.get('code', '')}\n"
            f"Details: {e.get('stdout', '')} {e.get('stderr', '')}"
            for e in error_context
        ])

        # Use framework-aware prompt with specific guidance for detected technologies
        prompt = self._build_framework_aware_prompt(errors_text)
        
        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=self.claude_timeout, skill=skill)
            result = await tool.execute(
                prompt=prompt,
                context=f"Continuous debug cycle {self._debug_count}: fixing {len(error_context)} errors",
                agent_type="continuous_debugger",
            )
            
            if result.success and result.files:
                self.logger.info(
                    "claude_fixes_applied",
                    files=result.files,
                )
                
                # Publish FILE_CREATED events
                for file in result.files:
                    # Handle both GeneratedFile objects and string paths
                    path = file.path if hasattr(file, 'path') else str(file)
                    await self.event_bus.publish(file_created_event(
                        source=self.name,
                        file_path=path,
                    ))
                
                return result.files
            else:
                self.logger.warning("claude_fix_failed", error=result.error)
                return []
                
        except Exception as e:
            self.logger.error("claude_tool_error", error=str(e))
            return []
    
    def _create_result_event(self, result: DebugCycleResult) -> Event:
        """Create result event from debug cycle result."""
        if result.success and result.fixes_applied > 0:
            return code_fixed_event(
                source=self.name,
                success=True,
                extra_data=result.to_dict(),
            )
        else:
            return debug_complete_event(
                source=self.name,
                success=result.success,
                error_message=result.error_message,
                data=result.to_dict(),
            )
    
    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Debug cycle #{self._debug_count}"
    
    def get_debug_status(self) -> dict[str, Any]:
        """Get current debug status."""
        return {
            "debug_count": self._debug_count,
            "total_fixes": self._total_fixes,
            "consecutive_failures": self._consecutive_failures,
            "max_iterations": self.max_debug_iterations,
            "container_id": self.container_id[:12] if self.container_id else None,
            "file_sync_enabled": self.enable_file_sync,
            "hot_reload_enabled": self.enable_hot_reload,
        }


# Convenience function
async def run_continuous_debug(
    project_dir: str,
    container_id: str,
    max_iterations: int = 10,
) -> list[DebugCycleResult]:
    """
    Run continuous debugging on a project.
    
    This is a standalone function for testing the debug cycle
    without the full orchestrator.
    
    Args:
        project_dir: Path to project
        container_id: Docker container ID
        max_iterations: Max debug iterations
        
    Returns:
        List of DebugCycleResults
    """
    from ..mind.event_bus import EventBus
    from ..mind.shared_state import SharedState
    
    event_bus = EventBus()
    shared_state = SharedState()
    await shared_state.start()
    
    agent = ContinuousDebugAgent(
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=project_dir,
        container_id=container_id,
        max_debug_iterations=max_iterations,
    )
    
    await agent.start()
    
    # Run until converged or max iterations
    results = []
    # ... implementation would go here
    
    await agent.stop()
    return results