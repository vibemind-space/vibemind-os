"""
Claude CLI Wrapper - Invokes Claude Code CLI for agent tasks.

This wrapper:
1. Invokes 'claude' CLI via subprocess
2. Uses OAuth authentication (your Max subscription)
3. Handles prompts and responses
4. Parses output for generated files
5. Supports MCP servers (Playwright, custom tools)
"""
import asyncio
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any

import structlog

from ..config import get_settings

if TYPE_CHECKING:
    from ..mcp import MCPServerManager

logger = structlog.get_logger()

# Code file extensions for disk scanning
CODE_EXTENSIONS = {'.ts', '.tsx', '.js', '.jsx', '.py', '.css', '.html', '.json', '.vue', '.svelte', '.md', '.yaml', '.yml'}
IGNORE_DIRS = {'node_modules', '.git', '__pycache__', 'dist', 'build', '.next', '.venv', 'venv', '.cache'}


def _get_claude_executable() -> str:
    """
    Get the Claude CLI executable path.

    Checks in order:
    1. CLAUDE_CODE_PATH environment variable
    2. System PATH via shutil.which
    3. Common installation paths

    Returns:
        Path to claude executable, or 'claude' as fallback
    """
    import shutil
    import sys

    # 1. Check environment variable
    env_path = os.getenv("CLAUDE_CODE_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # 2. Check system PATH
    which_result = shutil.which("claude")
    if which_result:
        return which_result

    # 3. Check common locations
    common_paths = []
    if sys.platform == "win32":
        common_paths = [
            Path(os.getenv("APPDATA", "")) / "npm" / "claude.cmd",
            Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Claude" / "claude.exe",
            Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
        ]
    else:
        common_paths = [
            Path.home() / ".local" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path.home() / ".npm-global" / "bin" / "claude",
        ]

    for path in common_paths:
        if path.exists():
            return str(path)

    # Fallback to 'claude' and hope it's in PATH
    return "claude"

# Import CLI tracker for monitoring
try:
    from ..monitoring.cli_tracker import CLITracker, get_cli_store
    TRACKING_AVAILABLE = True
except ImportError:
    TRACKING_AVAILABLE = False

# Import FileLockManager for safe concurrent file operations
def _get_file_lock_manager():
    """Lazy import FileLockManager."""
    try:
        from ..tools.file_lock_manager import FileLockManager, get_file_lock_manager
        return get_file_lock_manager()
    except ImportError:
        return None


# Import RateLimitError for proper error handling
def _get_rate_limit_error():
    """Lazy import RateLimitError to avoid circular imports."""
    try:
        from ..engine.rate_limit_handler import RateLimitError
        return RateLimitError
    except ImportError:
        return None


@dataclass
class GeneratedFile:
    """A file extracted from CLI output."""
    path: str
    content: str
    language: str


@dataclass
class CLIResponse:
    """Response from Claude CLI execution."""
    success: bool
    output: str
    files: list[GeneratedFile] = field(default_factory=list)
    error: Optional[str] = None
    exit_code: int = 0
    execution_time_ms: int = 0
    session_id: Optional[str] = None


class ClaudeCLI:
    """
    Wrapper for Claude Code CLI.

    Uses subprocess to invoke 'claude' with prompts.
    Assumes user has authenticated via 'claude login' (OAuth).

    Supports MCP servers for extended capabilities:
    - Playwright for browser automation / frontend validation
    - Custom tools via MCPServerManager
    
    Uses FileLockManager for safe concurrent file writes.
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None,
        max_tokens: int = 4096,
        mcp_manager: Optional["MCPServerManager"] = None,
        enable_playwright: bool = False,
        agent_name: str = "ClaudeCLI",  # NEW: for tracking
        event_bus: Optional[Any] = None,  # NEW: for event publishing
        use_file_locks: bool = True,  # NEW: enable file locking
    ):
        self.working_dir = working_dir or os.getcwd()
        self.timeout = timeout if timeout is not None else get_settings().cli_timeout
        self.max_tokens = max_tokens
        self.mcp_manager = mcp_manager
        self.enable_playwright = enable_playwright
        self._mcp_initialized = False
        self.use_file_locks = use_file_locks
        self._file_lock_manager = _get_file_lock_manager() if use_file_locks else None
        self.logger = logger.bind(component="claude_cli")
        
        # Initialize tracker for monitoring
        self.tracker: Optional[CLITracker] = None
        if TRACKING_AVAILABLE:
            self.tracker = CLITracker(
                agent=agent_name,
                working_dir=self.working_dir,
                event_bus=event_bus,
            )

    async def _ensure_mcp_initialized(self) -> Optional[Path]:
        """Initialize MCP servers if needed and return config path.

        Generates a .claude/mcp.json from servers.json with all active
        stdio MCP servers so Claude CLI can use them via --mcp-config.
        """
        if self._mcp_initialized:
            if self._mcp_config_path and self._mcp_config_path.exists():
                return self._mcp_config_path
            if self.mcp_manager:
                return self.mcp_manager.get_config_path()
            return None

        self._mcp_initialized = True
        self._mcp_config_path = None

        # Generate CLI MCP config from servers.json (all active stdio servers)
        try:
            from ..mcp.project_config import generate_cli_mcp_config
            self._mcp_config_path = generate_cli_mcp_config(
                working_dir=self.working_dir,
            )
            self.logger.info(
                "mcp_cli_config_generated",
                path=str(self._mcp_config_path),
            )
        except Exception as e:
            self.logger.warning("mcp_cli_config_failed", error=str(e))

        # Also start Playwright via MCPServerManager if enabled
        if self.enable_playwright and not self.mcp_manager:
            from ..mcp import MCPServerManager
            self.mcp_manager = MCPServerManager(working_dir=self.working_dir)

        if self.enable_playwright and self.mcp_manager:
            try:
                await self.mcp_manager.start_from_template("playwright")
                self.logger.info("mcp_playwright_started")
            except Exception as e:
                self.logger.warning("mcp_playwright_failed", error=str(e))

        if self._mcp_config_path and self._mcp_config_path.exists():
            return self._mcp_config_path
        if self.mcp_manager:
            return self.mcp_manager.get_config_path()
        return None

    async def execute(
        self,
        prompt: str,
        context_files: Optional[list[str]] = None,
        output_format: str = "json",
        use_mcp: bool = True,
        file_context: str = "",
        agent_name: Optional[str] = None,
        max_turns: Optional[int] = None,
        session_id: Optional[str] = None,
        allowed_tools: Optional[list[str]] = None,
    ) -> CLIResponse:
        """
        Execute a prompt using Claude CLI.

        Args:
            prompt: The task prompt
            context_files: Optional files to include as context
            output_format: Output format ("text" or "json"), defaults to "json"
            use_mcp: Whether to use MCP servers (default: True)
            file_context: Context for generated filenames (e.g., "fixer_minimal", "generator_crud")
            agent_name: Optional .claude/agents/ agent name (e.g., "coder", "database-agent")
            max_turns: Optional max agentic turns (prevents runaway cost)
            session_id: Optional session ID to resume a previous conversation
            allowed_tools: Optional list of allowed tools (e.g., ["Read", "Write", "Edit"]).
                When provided, uses --allowedTools instead of --dangerously-skip-permissions.

        Returns:
            CLIResponse with results
        """
        import time
        start_time = time.time()

        # Track active CLI call count
        try:
            from ..monitoring.cli_tracker import increment_active, decrement_active
            await increment_active()
            _tracking_active = True
        except ImportError:
            _tracking_active = False

        try:
            # Sanitize prompt - remove/replace problematic Unicode chars for Windows
            sanitized_prompt = self._sanitize_prompt(prompt)

            # Create file snapshot BEFORE CLI execution to detect new files later
            before_snapshot = self._get_file_snapshot()
            
            # Initialize MCP if needed
            mcp_config_path = None
            if use_mcp:
                mcp_config_path = await self._ensure_mcp_initialized()

            # Build command - full .claude integration
            # --dangerously-skip-permissions: ALL tools allowed, zero permission prompts
            # --output-format json: structured output for reliable parsing
            # --agent: route to specialized .claude/agents/*.md definitions
            # --max-turns: cost control per task type
            # --model: from config/llm_models.yml via llm_config
            claude_exe = _get_claude_executable()

            # Permission mode: fine-grained tool control or skip-all
            if allowed_tools:
                tools_csv = ",".join(allowed_tools)
                cmd = f'"{claude_exe}" --allowedTools {tools_csv}'
            else:
                cmd = f'"{claude_exe}" --dangerously-skip-permissions'

            # Session resumption (multi-turn conversations)
            if session_id:
                cmd += f' --resume {session_id}'

            # Model from llm_models.yml (single source of truth)
            try:
                from src.llm_config import get_model
                cli_model = get_model("cli")
            except (ImportError, Exception):
                cli_model = get_settings().cli_model
            if cli_model:
                cmd += f' --model {cli_model}'

            # Structured JSON output (always, for reliable parsing)
            cmd += ' --output-format json'

            # Agent routing: .claude/agents/{name}.md
            if agent_name:
                cmd += f' --agent {agent_name}'

            # Cost control: max agentic turns (default 10 if not specified)
            effective_max_turns = max_turns if max_turns else 10
            cmd += f' --max-turns {effective_max_turns}'

            # Add MCP config if available
            if mcp_config_path and mcp_config_path.exists():
                cmd += f' --mcp-config "{mcp_config_path}"'

            # -p = non-interactive print mode, prompt via stdin
            cmd += ' -p'

            self.logger.info(
                "executing_cli",
                prompt_length=len(sanitized_prompt),
                working_dir=self.working_dir,
                model=cli_model,
                agent=agent_name,
                max_turns=max_turns,
                output_format="json",
                mcp_enabled=mcp_config_path is not None,
                playwright_enabled=self.enable_playwright,
                resume_session=session_id,
                allowed_tools=allowed_tools,
                cmd_preview=cmd[:200],
            )

            # Run subprocess with UTF-8 encoding and proper environment
            # On Windows, large prompts (>8KB) cause [Errno 22] Invalid argument
            # when passed via subprocess.run(input=..., shell=True). Fix: write
            # prompt to temp file and redirect stdin from the file.
            import tempfile

            def run_cmd():
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                # Remove CLAUDECODE env var to prevent "nested session" error
                # when spawning Claude CLI from within a Claude Code session
                env.pop('CLAUDECODE', None)

                # Write prompt to temp file to avoid Windows stdin pipe limits
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', encoding='utf-8',
                    delete=False, dir=os.environ.get('TEMP', None)
                ) as tmp:
                    tmp.write(sanitized_prompt)
                    tmp_path = tmp.name

                try:
                    with open(tmp_path, 'r', encoding='utf-8') as stdin_file:
                        return subprocess.run(
                            cmd,
                            stdin=stdin_file,
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace',  # Replace unencodable chars
                            timeout=self.timeout,
                            cwd=self.working_dir,
                            shell=True,
                            env=env,
                        )
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            # Add asyncio-level timeout to prevent hanging on Windows
            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, run_cmd),
                    timeout=self.timeout + 30  # Extra buffer for executor overhead
                )
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                self.logger.error(
                    "cli_asyncio_timeout",
                    timeout=self.timeout,
                    elapsed_seconds=int(elapsed),
                    hint="Consider reducing prompt size or increasing timeout via VOTING_PROPOSAL_TIMEOUT",
                )
                response = CLIResponse(
                    success=False,
                    output="",
                    error=f"Asyncio timeout after {int(elapsed)}s (subprocess may be hung). Hint: Reduce prompt size or increase VOTING_PROPOSAL_TIMEOUT.",
                    exit_code=-2,
                    execution_time_ms=int(elapsed * 1000),
                )
                # Track failed call
                if self.tracker:
                    await self.tracker.record_call(
                        prompt=sanitized_prompt,
                        response="",
                        success=False,
                        latency_ms=response.execution_time_ms,
                        error=response.error,
                    )
                return response

            execution_time = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                # Extract detailed error information
                error_msg = result.stderr or f"Exit code: {result.returncode}"
                
                # Check for common authentication/installation issues
                if "not authenticated" in error_msg.lower() or "login" in error_msg.lower():
                    error_msg = f"CLI_AUTH_ERROR: Claude CLI not authenticated. Run 'claude login' or set ANTHROPIC_API_KEY. Original: {error_msg}"
                elif "command not found" in error_msg.lower() or "not recognized" in error_msg.lower():
                    error_msg = f"CLI_NOT_INSTALLED: Claude CLI not found. Install with 'npm install -g @anthropic-ai/claude-cli'. Original: {error_msg}"
                elif "rate limit" in error_msg.lower():
                    error_msg = f"CLI_RATE_LIMIT: API rate limit exceeded. Original: {error_msg}"
                    # Raise RateLimitError for upstream handling
                    RateLimitError = _get_rate_limit_error()
                    if RateLimitError:
                        self.logger.warning(
                            "rate_limit_detected",
                            error=error_msg,
                        )
                        raise RateLimitError(error_msg)
                elif result.returncode == 1 and not result.stderr:
                    # Silent failure often means auth issues
                    error_msg = f"CLI_SILENT_FAILURE: Exit code 1 with no stderr. This often indicates missing authentication. Check ANTHROPIC_API_KEY or run 'claude login'."
                
                self.logger.error(
                    "cli_error",
                    exit_code=result.returncode,
                    stderr=result.stderr[:500] if result.stderr else None,
                    stdout_preview=result.stdout[:200] if result.stdout else None,
                    error_type=error_msg.split(":")[0] if ":" in error_msg else "CLI_ERROR",
                )
                
                # Also log to stdout for visibility in container logs (with encoding safety)
                def safe_print(msg):
                    try:
                        print(msg)
                    except UnicodeEncodeError:
                        print(msg.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
                safe_print(f"[CLI_ERROR] Exit code: {result.returncode}")
                safe_print(f"[CLI_ERROR] stderr: {result.stderr[:500] if result.stderr else 'None'}")
                safe_print(f"[CLI_ERROR] stdout: {result.stdout[:200] if result.stdout else 'None'}")
                
                response = CLIResponse(
                    success=False,
                    output=result.stdout,
                    error=error_msg,
                    exit_code=result.returncode,
                    execution_time_ms=execution_time,
                )
                
                # Track failed call
                if self.tracker:
                    await self.tracker.record_call(
                        prompt=sanitized_prompt,
                        response=result.stdout or "",
                        success=False,
                        latency_ms=execution_time,
                        error=error_msg,
                    )
                
                return response

            # Parse JSON output (structured) with fallback to raw text
            raw_stdout = result.stdout
            output_text = raw_stdout
            session_id = None

            try:
                json_data = json.loads(raw_stdout)
                # Extract result text from JSON wrapper
                if isinstance(json_data, dict):
                    # Claude CLI JSON: {"result": "...", "session_id": "...", ...}
                    output_text = json_data.get("result", raw_stdout)
                    session_id = json_data.get("session_id")
                    # If result is a list of content blocks, extract text
                    if isinstance(output_text, dict) and "content" in output_text:
                        content_blocks = output_text["content"]
                        if isinstance(content_blocks, list):
                            output_text = "\n".join(
                                b.get("text", "") for b in content_blocks
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                    self.logger.debug(
                        "json_output_parsed",
                        session_id=session_id,
                        result_length=len(str(output_text)),
                    )
            except (json.JSONDecodeError, TypeError):
                # Fallback: raw text output (CLI error, non-JSON response)
                self.logger.debug("json_parse_fallback", stdout_length=len(raw_stdout))

            # Parse output for generated files (from stdout code blocks)
            files = self._extract_files(raw_stdout, context=file_context)

            # Write extracted files to disk
            files_written = self._write_files(files)

            # If no files extracted from stdout, scan disk for files created by CLI directly
            if not files:
                disk_files = self._scan_disk_for_new_files(before_snapshot)
                if disk_files:
                    files.extend(disk_files)
                    self.logger.info(
                        "files_detected_from_disk",
                        count=len(disk_files),
                        paths=[f.path for f in disk_files[:5]],
                    )

            # Collect file paths for tracking
            file_paths = [f.path for f in files]

            self.logger.info(
                "cli_success",
                output_length=len(raw_stdout),
                files_extracted=len(files),
                files_written=files_written,
                execution_time_ms=execution_time,
                session_id=session_id,
                agent=agent_name,
            )

            response = CLIResponse(
                success=True,
                output=output_text if isinstance(output_text, str) else raw_stdout,
                files=files,
                exit_code=0,
                execution_time_ms=execution_time,
                session_id=session_id,
            )
            
            # Track successful call
            if self.tracker:
                await self.tracker.record_call(
                    prompt=sanitized_prompt,
                    response=result.stdout,
                    success=True,
                    latency_ms=execution_time,
                    files_modified=file_paths,
                )
            
            return response

        except subprocess.TimeoutExpired:
            self.logger.error("cli_timeout", timeout=self.timeout)
            response = CLIResponse(
                success=False,
                output="",
                error=f"Command timed out after {self.timeout}s",
                exit_code=-1,
                execution_time_ms=self.timeout * 1000,
            )
            # Track timeout
            if self.tracker:
                await self.tracker.record_call(
                    prompt=prompt,
                    response="",
                    success=False,
                    latency_ms=self.timeout * 1000,
                    error=response.error,
                )
            return response
        except Exception as e:
            self.logger.error("cli_exception", error=str(e))
            execution_time = int((time.time() - start_time) * 1000)
            response = CLIResponse(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                execution_time_ms=execution_time,
            )
            # Track exception
            if self.tracker:
                await self.tracker.record_call(
                    prompt=prompt,
                    response="",
                    success=False,
                    latency_ms=execution_time,
                    error=str(e),
                )
            return response
        finally:
            # Decrement active CLI call count
            if _tracking_active:
                try:
                    await decrement_active()
                except Exception:
                    pass  # Ignore errors in tracking

    def _sanitize_prompt(self, prompt: str) -> str:
        """
        Sanitize prompt for safe transmission to CLI.

        Removes or replaces problematic Unicode characters that can cause
        encoding issues on Windows.
        """
        # Replace common problematic math/special chars with ASCII equivalents
        replacements = {
            '\u2264': '<=',  # ≤
            '\u2265': '>=',  # ≥
            '\u2260': '!=',  # ≠
            '\u2248': '~=',  # ≈
            '\u0302': '^',   # combining circumflex
            '\u2192': '->',  # →
            '\u2190': '<-',  # ←
            '\u2194': '<->',  # ↔
            '\u2713': '[OK]',  # ✓
            '\u2717': '[X]',   # ✗
            '\u2022': '*',   # •
            '\u2026': '...',  # …
            '\u201c': '"',   # "
            '\u201d': '"',   # "
            '\u2018': "'",   # '
            '\u2019': "'",   # '
            '\u2014': '--',  # —
            '\u2013': '-',   # –
        }

        result = prompt
        for char, replacement in replacements.items():
            result = result.replace(char, replacement)

        # Remove any remaining non-ASCII chars that could cause issues
        # Keep basic UTF-8 but remove combining chars and other problematic ones
        cleaned = []
        for char in result:
            code = ord(char)
            # Keep ASCII, common extended Latin, and some safe ranges
            if code < 0x300 or (code >= 0x400 and code < 0x500):
                cleaned.append(char)
            elif code >= 0x300 and code < 0x370:
                # Combining diacritical marks - skip
                continue
            else:
                # Replace other chars with space or skip
                cleaned.append(' ')

        return ''.join(cleaned)

    def _extract_files(self, output: str, context: str = "") -> list[GeneratedFile]:
        """
        Extract generated files from CLI output.

        Looks for code blocks with file paths in the output.

        Args:
            output: CLI output containing code blocks
            context: Optional context for meaningful filenames (e.g., "fixer_minimal", "generator_crud")
        """
        files = []

        # Generate timestamp prefix for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Generate meaningful prefix from context
        if context:
            # Sanitize: "Generating minimal fix proposal" -> "minimal_fix_proposal"
            prefix = re.sub(r'[^a-z0-9]+', '_', context.lower())[:30]
            prefix = prefix.strip('_') or "generated"
        else:
            prefix = "generated"

        # Pattern: ```language:path or ```language filename
        # Also handles: File: path\n```language
        patterns = [
            # ```python:src/main.py
            r'```(\w+):([^\n]+)\n(.*?)```',
            # File: src/main.py\n```python
            r'File:\s*([^\n]+)\n```(\w+)\n(.*?)```',
            # <!-- file: src/main.py -->\n```python
            r'<!--\s*file:\s*([^\n]+)\s*-->\n```(\w+)\n(.*?)```',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output, re.DOTALL)
            for match in matches:
                if len(match) == 3:
                    if pattern == patterns[0]:
                        lang, path, content = match
                    else:
                        path, lang, content = match

                    files.append(GeneratedFile(
                        path=path.strip(),
                        content=content.strip(),
                        language=lang.strip(),
                    ))

        # Also look for standalone code blocks and infer file type
        standalone_pattern = r'```(\w+)\n(.*?)```'
        standalone_matches = re.findall(standalone_pattern, output, re.DOTALL)

        # Track which content we've already captured
        captured_content = {f.content for f in files}

        for lang, content in standalone_matches:
            content = content.strip()
            if content not in captured_content:
                # Generate a filename based on language
                ext_map = {
                    'python': '.py',
                    'javascript': '.js',
                    'typescript': '.ts',
                    'rust': '.rs',
                    'go': '.go',
                    'java': '.java',
                    'cpp': '.cpp',
                    'c': '.c',
                    'html': '.html',
                    'css': '.css',
                    'json': '.json',
                    'yaml': '.yaml',
                    'dockerfile': 'Dockerfile',
                    'sql': '.sql',
                }
                ext = ext_map.get(lang.lower(), f'.{lang}')
                # Use context-based filename for meaningful naming
                filename = f"{prefix}_{timestamp}_{len(files) + 1}{ext}"

                files.append(GeneratedFile(
                    path=filename,
                    content=content,
                    language=lang,
                ))
                captured_content.add(content)

        return files

    def _write_files(self, files: list[GeneratedFile]) -> int:
        """
        Write extracted files to disk.

        Args:
            files: List of GeneratedFile objects to write

        Returns:
            Number of files successfully written
        """
        written = 0

        for file in files:
            try:
                # Validate path - prevent path traversal
                file_path = Path(file.path)

                # Don't allow absolute paths or parent directory traversal
                if file_path.is_absolute():
                    file_path = Path(file_path.name)

                # Remove any parent directory references
                parts = [p for p in file_path.parts if p not in ('..', '.')]
                if not parts:
                    self.logger.warning("invalid_file_path", path=file.path)
                    continue

                file_path = Path(*parts)

                # Build full path relative to working directory
                full_path = Path(self.working_dir) / file_path

                # Create parent directories if needed
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Always use synchronous write in this sync method
                # The async FileLockManager can't be reliably used from sync context
                # because asyncio.run() fails if an event loop is already running
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(file.content)
                written += 1
                self.logger.debug(
                    "file_written",
                    path=str(full_path),
                    size=len(file.content),
                )

            except Exception as e:
                self.logger.error(
                    "file_write_error",
                    path=file.path,
                    error=str(e),
                )

        return written

    async def _write_file_with_lock(self, full_path: Path, content: str) -> None:
        """Write a file with lock protection (async helper for async contexts only)."""
        if self._file_lock_manager:
            await self._file_lock_manager.safe_write(
                str(full_path),
                content,
                holder=f"cli_{id(self)}",
                merge_on_conflict=True,
            )
        else:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
    
    async def write_files_async(self, files: list[GeneratedFile]) -> int:
        """
        Write extracted files to disk with async lock protection.
        
        Use this method in async contexts for safe concurrent writes.
        
        Args:
            files: List of GeneratedFile objects to write

        Returns:
            Number of files successfully written
        """
        written = 0

        for file in files:
            try:
                # Validate path - prevent path traversal
                file_path = Path(file.path)

                # Don't allow absolute paths or parent directory traversal
                if file_path.is_absolute():
                    file_path = Path(file_path.name)

                # Remove any parent directory references
                parts = [p for p in file_path.parts if p not in ('..', '.')]
                if not parts:
                    self.logger.warning("invalid_file_path", path=file.path)
                    continue

                file_path = Path(*parts)

                # Build full path relative to working directory
                full_path = Path(self.working_dir) / file_path

                # Create parent directories if needed
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Use async lock if available
                if self._file_lock_manager and self.use_file_locks:
                    success, _ = await self._file_lock_manager.safe_write(
                        str(full_path),
                        file.content,
                        holder=f"cli_{id(self)}",
                        merge_on_conflict=True,
                    )
                    if success:
                        written += 1
                        self.logger.debug(
                            "file_written_with_lock",
                            path=str(full_path),
                            size=len(file.content),
                        )
                else:
                    # Direct write without locking
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(file.content)
                    written += 1
                    self.logger.debug(
                        "file_written",
                        path=str(full_path),
                        size=len(file.content),
                    )

            except Exception as e:
                self.logger.error(
                    "file_write_error",
                    path=file.path,
                    error=str(e),
                )

        return written

    def _get_file_snapshot(self) -> dict[str, float]:
        """
        Create a snapshot of all files in working directory with their modification times.
        
        Returns:
            Dict mapping relative file paths to their modification timestamps
        """
        snapshot = {}
        working_path = Path(self.working_dir)
        
        try:
            for file_path in working_path.rglob("*"):
                if not file_path.is_file():
                    continue
                    
                # Skip ignored directories
                if any(ignored in file_path.parts for ignored in IGNORE_DIRS):
                    continue
                    
                # Only track code files
                if file_path.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                    
                try:
                    rel_path = str(file_path.relative_to(working_path))
                    snapshot[rel_path] = file_path.stat().st_mtime
                except (ValueError, OSError):
                    continue
                    
        except Exception as e:
            self.logger.warning("file_snapshot_failed", error=str(e))
            
        return snapshot
    
    def _scan_disk_for_new_files(self, before_snapshot: dict[str, float]) -> list[GeneratedFile]:
        """
        Scan working directory for files created or modified after the snapshot.
        
        This catches files that Claude CLI writes directly to disk (with --dangerously-skip-permissions)
        without outputting them to stdout.
        
        Args:
            before_snapshot: File snapshot from before CLI execution
            
        Returns:
            List of GeneratedFile objects for new/modified files
        """
        new_files = []
        working_path = Path(self.working_dir)
        
        try:
            for file_path in working_path.rglob("*"):
                if not file_path.is_file():
                    continue
                    
                # Skip ignored directories
                if any(ignored in file_path.parts for ignored in IGNORE_DIRS):
                    continue
                    
                # Only check code files
                if file_path.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                    
                try:
                    rel_path = str(file_path.relative_to(working_path))
                    current_mtime = file_path.stat().st_mtime
                    
                    # Check if file is new or modified
                    is_new = rel_path not in before_snapshot
                    is_modified = not is_new and current_mtime > before_snapshot.get(rel_path, 0)
                    
                    if is_new or is_modified:
                        # Read file content
                        content = file_path.read_text(encoding='utf-8', errors='replace')
                        language = self._detect_language(file_path.suffix)
                        
                        new_files.append(GeneratedFile(
                            path=rel_path,
                            content=content,
                            language=language,
                        ))
                        
                except (ValueError, OSError, UnicodeDecodeError) as e:
                    self.logger.warning("disk_scan_file_error", path=str(file_path), error=str(e))
                    continue
                    
        except Exception as e:
            self.logger.warning("disk_scan_failed", error=str(e))
            
        return new_files
    
    def _detect_language(self, suffix: str) -> str:
        """
        Detect programming language from file extension.
        
        Args:
            suffix: File extension (e.g., '.ts')
            
        Returns:
            Language name for the extension
        """
        ext_to_lang = {
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.py': 'python',
            '.css': 'css',
            '.html': 'html',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.md': 'markdown',
            '.vue': 'vue',
            '.svelte': 'svelte',
            '.sql': 'sql',
            '.sh': 'bash',
            '.bash': 'bash',
        }
        return ext_to_lang.get(suffix.lower(), suffix.lstrip('.'))

    async def check_auth(self) -> bool:
        """Check if CLI is authenticated."""
        try:
            claude_exe = _get_claude_executable()
            result = subprocess.run(
                f'"{claude_exe}" --version',
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    async def execute_streaming(
        self,
        prompt: str,
        agent_name: Optional[str] = None,
        allowed_tools: Optional[list[str]] = None,
        max_turns: int = 10,
        session_id: Optional[str] = None,
        use_mcp: bool = True,
    ):
        """
        Execute Claude CLI and yield streaming frames.

        Uses --output-format stream-json for real-time output.
        Yields dicts with type: "text", "tool_use", "error", "complete".

        Args:
            prompt: The task prompt
            agent_name: Optional .claude/agents/ agent name
            allowed_tools: Optional tool restriction list
            max_turns: Max agentic turns
            session_id: Optional session ID to resume
            use_mcp: Whether to use MCP servers

        Yields:
            dict frames: {"type": "text"|"tool_use"|"error"|"complete", ...}
        """
        sanitized_prompt = self._sanitize_prompt(prompt)

        # Initialize MCP if needed
        mcp_config_path = None
        if use_mcp:
            mcp_config_path = await self._ensure_mcp_initialized()

        # Build command with stream-json output
        claude_exe = _get_claude_executable()

        if allowed_tools:
            tools_csv = ",".join(allowed_tools)
            cmd_parts = [claude_exe, "--allowedTools", tools_csv]
        else:
            cmd_parts = [claude_exe, "--dangerously-skip-permissions"]

        if session_id:
            cmd_parts.extend(["--resume", session_id])

        try:
            from src.llm_config import get_model
            cli_model = get_model("cli")
        except (ImportError, Exception):
            cli_model = get_settings().cli_model
        if cli_model:
            cmd_parts.extend(["--model", cli_model])

        cmd_parts.extend(["--output-format", "stream-json"])

        if agent_name:
            cmd_parts.extend(["--agent", agent_name])

        cmd_parts.extend(["--max-turns", str(max_turns)])

        if mcp_config_path and mcp_config_path.exists():
            cmd_parts.extend(["--mcp-config", str(mcp_config_path)])

        cmd_parts.append("-p")

        self.logger.info(
            "executing_cli_streaming",
            agent=agent_name,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
        )

        # Write prompt to temp file (Windows stdin pipe limit)
        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8',
            delete=False, dir=os.environ.get('TEMP', None),
        )
        tmp.write(sanitized_prompt)
        tmp.close()
        tmp_path = tmp.name

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env.pop('CLAUDECODE', None)

        stdin_file = None
        try:
            stdin_file = open(tmp_path, 'r', encoding='utf-8')
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdin=stdin_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env=env,
            )

            result_session_id = None
            changed_files = []

            # Stream stdout line by line
            async for line_bytes in process.stdout:
                line = line_bytes.decode('utf-8', errors='replace').strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    yield {"type": "text", "content": line}
                    continue

                msg_type = data.get("type", "")

                if msg_type == "assistant":
                    message = data.get("message", {})
                    for block in message.get("content", []):
                        if block.get("type") == "text":
                            yield {"type": "text", "content": block["text"]}
                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            tool_input = block.get("input", {})
                            file_path = (
                                tool_input.get("file_path")
                                or tool_input.get("path")
                                or tool_input.get("command", "")[:80]
                            )
                            if tool_name in ("Edit", "Write") and file_path:
                                changed_files.append(file_path)
                            yield {
                                "type": "tool_use",
                                "tool": tool_name,
                                "file": file_path,
                                "status": "running",
                            }

                elif msg_type == "result":
                    result_session_id = data.get("session_id")
                    yield {
                        "type": "complete",
                        "success": True,
                        "session_id": result_session_id,
                        "files": changed_files,
                    }

                elif msg_type == "error":
                    yield {
                        "type": "error",
                        "message": data.get("error", {}).get("message", str(data)),
                    }

            await process.wait()

            if not result_session_id and process.returncode == 0:
                yield {
                    "type": "complete",
                    "success": True,
                    "session_id": None,
                    "files": changed_files,
                }
            elif process.returncode != 0:
                stderr = ""
                if process.stderr:
                    stderr = (await process.stderr.read()).decode('utf-8', errors='replace')
                yield {
                    "type": "error",
                    "message": f"CLI exited with code {process.returncode}: {stderr[:500]}",
                }

        except Exception as e:
            self.logger.error("streaming_error", error=str(e))
            yield {"type": "error", "message": str(e)}
        finally:
            if stdin_file:
                stdin_file.close()
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def execute_sync(self, prompt: str) -> CLIResponse:
        """Synchronous version of execute."""
        return asyncio.run(self.execute(prompt))


class ClaudeCLIPool:
    """
    Pool of CLI instances for parallel execution.

    Manages multiple concurrent CLI calls while respecting rate limits.
    Uses FileLockManager for safe concurrent file writes.
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        working_dir: Optional[str] = None,
        use_file_locks: bool = True,
    ):
        self.max_concurrent = max_concurrent
        self.working_dir = working_dir
        self.use_file_locks = use_file_locks
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._file_lock_manager = _get_file_lock_manager() if use_file_locks else None
        self.logger = logger.bind(component="cli_pool")

    @property
    def active_count(self) -> int:
        """
        Get the number of currently active CLI calls globally.

        This returns the global active count from cli_tracker,
        which tracks all CLI calls across all pools and instances.

        Returns:
            Number of currently executing CLI calls.
        """
        try:
            from ..monitoring.cli_tracker import get_active_count
            return get_active_count()
        except ImportError:
            return 0

    async def execute_batch(
        self,
        prompts: list[tuple[str, str]],  # (task_id, prompt)
    ) -> dict[str, CLIResponse]:
        """
        Execute multiple prompts in parallel.

        Args:
            prompts: List of (task_id, prompt) tuples

        Returns:
            Dict mapping task_id to CLIResponse
        """
        results: dict[str, CLIResponse] = {}

        async def execute_one(task_id: str, prompt: str):
            async with self._semaphore:
                cli = ClaudeCLI(
                    working_dir=self.working_dir,
                    use_file_locks=self.use_file_locks,
                )
                response = await cli.execute(prompt)
                results[task_id] = response

        # Execute all in parallel (limited by semaphore)
        tasks = [
            execute_one(task_id, prompt)
            for task_id, prompt in prompts
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def execute_batch_with_file_tracking(
        self,
        prompts: list[tuple[str, str]],  # (task_id, prompt)
    ) -> tuple[dict[str, CLIResponse], list[str]]:
        """
        Execute multiple prompts in parallel with file conflict tracking.

        Args:
            prompts: List of (task_id, prompt) tuples

        Returns:
            Tuple of (results dict, list of conflicted file paths)
        """
        results: dict[str, CLIResponse] = {}
        all_files: dict[str, list[str]] = {}  # file_path -> list of task_ids that wrote it
        conflicts: list[str] = []

        async def execute_one(task_id: str, prompt: str):
            async with self._semaphore:
                cli = ClaudeCLI(
                    working_dir=self.working_dir,
                    use_file_locks=self.use_file_locks,
                )
                response = await cli.execute(prompt)
                results[task_id] = response
                
                # Track which files were written
                for file in response.files:
                    if file.path not in all_files:
                        all_files[file.path] = []
                    all_files[file.path].append(task_id)

        # Execute all in parallel (limited by semaphore)
        tasks = [
            execute_one(task_id, prompt)
            for task_id, prompt in prompts
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        # Detect conflicts (multiple tasks wrote to same file)
        for file_path, task_ids in all_files.items():
            if len(task_ids) > 1:
                conflicts.append(file_path)
                self.logger.warning(
                    "file_conflict_detected",
                    file=file_path,
                    writers=task_ids,
                )

        return results, conflicts


async def run_claude_agent(
    prompt: str,
    agent: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
    max_turns: int = 10,
    session_id: Optional[str] = None,
    working_dir: Optional[str] = None,
    use_mcp: bool = True,
) -> CLIResponse:
    """
    Convenience wrapper for Claude Code agent execution.

    Handles CLI setup, agent routing, tool restrictions, and session continuity
    in a single call. Designed for pipeline integration and vibe-coding workflows.

    Args:
        prompt: Task prompt for the agent
        agent: Agent name from .claude/agents/ (e.g., "coder", "debugger")
        allowed_tools: Restrict to specific tools (e.g., ["Read", "Grep"]).
            When None, uses --dangerously-skip-permissions (all tools).
        max_turns: Max agentic turns (default 10)
        session_id: Resume a previous session for multi-turn workflows
        working_dir: Working directory for CLI execution
        use_mcp: Whether to use MCP servers (default True)

    Returns:
        CLIResponse with output, files, session_id for chaining

    Usage:
        # Pipeline calls agent
        result = await run_claude_agent("Fix auth bug", agent="debugger", max_turns=5)

        # Multi-step with session continuity
        r1 = await run_claude_agent("Create schema", agent="database-agent")
        r2 = await run_claude_agent("Generate API", agent="api-generator", session_id=r1.session_id)

        # Read-only security scan
        result = await run_claude_agent("Audit auth module", agent="security-auditor",
                                         allowed_tools=["Read", "Grep", "Glob"])
    """
    cli = ClaudeCLI(working_dir=working_dir, agent_name=agent or "run_claude_agent")
    return await cli.execute(
        prompt=prompt,
        agent_name=agent,
        allowed_tools=allowed_tools,
        max_turns=max_turns,
        session_id=session_id,
        use_mcp=use_mcp,
    )
