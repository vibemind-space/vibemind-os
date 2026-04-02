"""
Claude Agent Tool - SDK-based wrapper for agent workflows.

This tool wraps the official Claude Agent SDK providing:
1. Single prompt execution with streaming
2. Multi-step workflow routines
3. Multi-turn conversations
4. Native tool use support

Falls back to ClaudeCLI if no API key is available.
"""

import asyncio
import os
import shutil
import sys
import uuid
import random
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================

class ClaudeCodeNotFoundError(Exception):
    """
    Raised when Claude Code executable is not found.

    This allows callers to catch this specific error and fall back to CLI.
    """
    def __init__(self, message: str, searched_paths: list[str] = None):
        super().__init__(message)
        self.searched_paths = searched_paths or []


class StreamingStallError(Exception):
    """
    Raised when streaming output stalls for too long.

    This indicates the SDK is still running but producing no output,
    which may indicate a hang or very slow processing.
    """
    def __init__(self, message: str, stall_duration: float = 0, last_output: str = ""):
        super().__init__(message)
        self.stall_duration = stall_duration
        self.last_output = last_output[:200] if last_output else ""


# =============================================================================
# Error Detection Functions
# =============================================================================

# Known error patterns that indicate Claude Code executable not found
CLAUDE_NOT_FOUND_PATTERNS = [
    "Claude Code not found",
    "claude.exe not found",
    "No such file or directory",
    "_bundled/claude",
    "FileNotFoundError",
    "spawn claude ENOENT",
    "The system cannot find the file specified",
    "command not found: claude",
]

# Known error patterns that indicate file locking issues (retryable)
FILE_LOCK_ERROR_PATTERNS = [
    "EBUSY",
    "resource busy or locked",
    ".claude.json",
    "The process cannot access the file",
    "being used by another process",
]


def is_file_lock_error(error: Exception) -> bool:
    """
    Check if an error is a file locking issue that can be retried.

    Args:
        error: The exception to check

    Returns:
        True if the error is a retryable file lock error
    """
    error_str = str(error).lower()
    return any(pattern.lower() in error_str for pattern in FILE_LOCK_ERROR_PATTERNS)


def is_claude_not_found_error(error: Exception) -> bool:
    """
    Check if an error indicates Claude Code executable is missing.

    Args:
        error: The exception to check

    Returns:
        True if the error indicates Claude Code was not found
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Check for our custom exception
    if isinstance(error, ClaudeCodeNotFoundError):
        return True

    # Check error message patterns
    for pattern in CLAUDE_NOT_FOUND_PATTERNS:
        if pattern.lower() in error_str:
            return True

    # Check for FileNotFoundError with claude-related path
    if error_type == "FileNotFoundError" and "claude" in error_str:
        return True

    return False


# =============================================================================
# Streaming Progress Tracking
# =============================================================================

@dataclass
class StreamingProgress:
    """Track streaming progress for stall detection."""
    chunks_received: int = 0
    bytes_received: int = 0
    last_chunk_time: float = field(default_factory=lambda: datetime.now().timestamp())
    last_output: str = ""
    start_time: float = field(default_factory=lambda: datetime.now().timestamp())

    def update(self, content: str) -> None:
        """Update progress with new content."""
        self.chunks_received += 1
        self.bytes_received += len(content.encode("utf-8"))
        self.last_chunk_time = datetime.now().timestamp()
        self.last_output = content[:200] if content else self.last_output

    def seconds_since_last_chunk(self) -> float:
        """Get seconds since last chunk was received."""
        return datetime.now().timestamp() - self.last_chunk_time

    def elapsed_seconds(self) -> float:
        """Get total elapsed time in seconds."""
        return datetime.now().timestamp() - self.start_time


def find_claude_executable() -> Optional[str]:
    """
    Search for Claude Code executable in common locations.

    Checks:
    1. CLAUDE_CODE_PATH environment variable
    2. System PATH (via shutil.which)
    3. Common installation directories

    Returns:
        Path to Claude executable if found, None otherwise
    """
    # 1. Check environment variable first
    env_path = os.getenv("CLAUDE_CODE_PATH")
    if env_path and Path(env_path).exists():
        logger.debug("claude_found_via_env", path=env_path)
        return env_path

    # 2. Check system PATH
    which_result = shutil.which("claude")
    if which_result:
        logger.debug("claude_found_via_path", path=which_result)
        return which_result

    # 3. Check common locations
    common_paths = []

    if sys.platform == "win32":
        # Windows paths
        common_paths.extend([
            Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Claude" / "claude.exe",
            Path(os.getenv("PROGRAMFILES", "")) / "Claude" / "claude.exe",
            Path(os.getenv("APPDATA", "")) / "npm" / "claude.cmd",
            Path.home() / "AppData" / "Local" / "Programs" / "Claude" / "claude.exe",
        ])
    else:
        # Unix/Mac paths
        common_paths.extend([
            Path.home() / ".local" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path("/usr/bin/claude"),
            Path.home() / ".npm-global" / "bin" / "claude",
        ])

    for path in common_paths:
        if path.exists():
            logger.debug("claude_found_at_common_path", path=str(path))
            return str(path)

    logger.warning(
        "claude_executable_not_found",
        searched_paths=[str(p) for p in common_paths if p.parts],  # Filter empty paths
    )
    return None


def get_searched_paths() -> list[str]:
    """Get list of paths that would be searched for Claude executable."""
    paths = []

    env_path = os.getenv("CLAUDE_CODE_PATH")
    if env_path:
        paths.append(f"CLAUDE_CODE_PATH: {env_path}")

    paths.append("System PATH (via shutil.which)")

    if sys.platform == "win32":
        paths.extend([
            f"{os.getenv('LOCALAPPDATA', '')}\\Programs\\Claude\\claude.exe",
            f"{os.getenv('PROGRAMFILES', '')}\\Claude\\claude.exe",
            f"{os.getenv('APPDATA', '')}\\npm\\claude.cmd",
        ])
    else:
        paths.extend([
            "~/.local/bin/claude",
            "/usr/local/bin/claude",
            "/usr/bin/claude",
        ])

    return paths

# Try to import the Claude Agent SDK
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    logger.warning("claude_agent_sdk not installed, SDK features unavailable")


@dataclass
class GeneratedFile:
    """A file generated by Claude."""
    path: str
    content: str
    language: str


@dataclass
class AgentResponse:
    """Response from Claude Agent SDK execution."""
    success: bool
    output: str
    files: list[GeneratedFile] = field(default_factory=list)
    error: Optional[str] = None
    execution_time_ms: int = 0
    messages: list[dict] = field(default_factory=list)  # Full conversation history

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output[:500] if self.output else "",
            "files": [{"path": f.path, "language": f.language} for f in self.files],
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class WorkflowStep:
    """A single step in a workflow routine."""
    name: str
    prompt: str
    tools: list[str] = field(default_factory=list)
    condition: Optional[Callable[["WorkflowContext"], bool]] = None
    retry: int = 3
    timeout: int = 300
    on_success: Optional[Callable[["WorkflowContext", AgentResponse], None]] = None
    on_failure: Optional[Callable[["WorkflowContext", Exception], None]] = None


@dataclass
class WorkflowContext:
    """Shared context across workflow steps."""
    working_dir: str
    variables: dict = field(default_factory=dict)
    results: list[AgentResponse] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    current_step: int = 0

    def set(self, key: str, value: Any) -> None:
        """Set a context variable."""
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a context variable."""
        return self.variables.get(key, default)

    def last_result(self) -> Optional[AgentResponse]:
        """Get the last step's result."""
        return self.results[-1] if self.results else None


@dataclass
class WorkflowResult:
    """Result of executing a complete workflow."""
    success: bool
    steps_completed: int
    total_steps: int
    context: WorkflowContext
    duration_ms: int = 0
    error: Optional[str] = None


class ClaudeAgentTool:
    """
    SDK-based wrapper for Claude Agent interactions.

    Provides:
    - execute(): Single prompt execution
    - workflow(): Multi-step workflow execution
    - conversation(): Multi-turn conversation

    Example:
        tool = ClaudeAgentTool(working_dir="./project")

        # Simple execution
        result = await tool.execute("Generate a React component for a login form")

        # Workflow execution
        workflow = [
            WorkflowStep(name="analyze", prompt="Analyze the error: {error}"),
            WorkflowStep(name="fix", prompt="Fix the identified issue"),
            WorkflowStep(name="verify", prompt="Verify the fix compiles"),
        ]
        result = await tool.workflow(workflow, context={"error": "TypeError..."})
    """

    # Default tools for code generation
    DEFAULT_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    def __init__(
        self,
        working_dir: str,
        api_key: Optional[str] = None,
        timeout: int = 300,
        max_tokens: int = 4096,
    ):
        """
        Initialize the Claude Agent Tool.

        Args:
            working_dir: Working directory for file operations
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            timeout: Default timeout for operations in seconds
            max_tokens: Maximum tokens for responses
        """
        self.working_dir = Path(working_dir)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.logger = logger.bind(component="claude_agent_tool")

    @staticmethod
    def is_available() -> bool:
        """Check if SDK is available and API key is configured."""
        return SDK_AVAILABLE and bool(os.getenv("ANTHROPIC_API_KEY"))

    async def execute(
        self,
        prompt: str,
        tools: Optional[list[str]] = None,
        context_files: Optional[list[str]] = None,
        timeout: Optional[int] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> AgentResponse:
        """
        Execute a single prompt using the Claude Agent SDK.

        Args:
            prompt: The prompt to send to Claude
            tools: List of allowed tools (defaults to DEFAULT_TOOLS)
            context_files: Optional files to include as context
            timeout: Timeout in seconds
            stream_callback: Optional callback for streaming output

        Returns:
            AgentResponse with success status, output, and generated files
        """
        if not SDK_AVAILABLE:
            return AgentResponse(
                success=False,
                output="",
                error="claude-agent-sdk not installed",
            )

        if not self.api_key:
            return AgentResponse(
                success=False,
                output="",
                error="ANTHROPIC_API_KEY not configured",
            )

        start_time = datetime.now()
        tools = tools or self.DEFAULT_TOOLS

        self.logger.info(
            "executing_prompt",
            prompt_length=len(prompt),
            tools=tools,
            working_dir=str(self.working_dir),
        )

        # Retry configuration for file locking errors (EBUSY)
        max_retries = int(os.getenv("CLAUDE_FILE_LOCK_RETRIES", "3"))
        base_delay = float(os.getenv("CLAUDE_FILE_LOCK_BASE_DELAY", "1.0"))

        # Create unique config directory for this execution to prevent parallel conflicts
        execution_id = str(uuid.uuid4())[:8]
        unique_config_dir = Path(tempfile.gettempdir()) / f".claude-config-{execution_id}"
        unique_config_dir.mkdir(parents=True, exist_ok=True)

        # Save original env and set unique config dir
        original_config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(unique_config_dir)

        try:
            # Build enhanced prompt with context files
            full_prompt = prompt
            if context_files:
                context_text = await self._load_context_files(context_files)
                full_prompt = f"{context_text}\n\n{prompt}"

            # Execute using SDK with retry logic for file locking errors
            last_error = None
            for attempt in range(max_retries):
                try:
                    output_parts = []
                    files_written = []

                    options = ClaudeAgentOptions(
                        allowed_tools=tools,
                        cwd=str(self.working_dir),
                    )

                    # Initialize progress tracking for stall detection
                    progress = StreamingProgress()

                    # Get stall timeout from environment or use default
                    stall_timeout = int(os.getenv("CLAUDE_STREAMING_STALL_TIMEOUT", "30"))

                    async for message in query(prompt=full_prompt, options=options):
                        # Handle different message types
                        if hasattr(message, 'content'):
                            # Extract text from TextBlock objects (SDK returns these)
                            msg_content = message.content
                            if hasattr(msg_content, '__iter__') and not isinstance(msg_content, str):
                                # List of TextBlock objects
                                content = ' '.join(
                                    str(block.text) if hasattr(block, 'text') else str(block)
                                    for block in msg_content
                                )
                            elif hasattr(msg_content, 'text'):
                                # Single TextBlock object
                                content = str(msg_content.text)
                            else:
                                content = str(msg_content)

                            # Update progress tracking
                            progress.update(content)

                            output_parts.append(content)
                            if stream_callback:
                                stream_callback(content)

                            # Log progress periodically (every 10 chunks)
                            if progress.chunks_received % 10 == 0:
                                self.logger.debug(
                                    "streaming_progress",
                                    chunks=progress.chunks_received,
                                    bytes=progress.bytes_received,
                                    elapsed=f"{progress.elapsed_seconds():.1f}s",
                                )

                        # Track file writes from tool use
                        if hasattr(message, 'tool_use') and message.tool_use:
                            for tool_call in message.tool_use:
                                if tool_call.name in ['Write', 'Edit']:
                                    file_path = tool_call.input.get('file_path', '')
                                    if file_path:
                                        files_written.append(file_path)

                        # Check for stall (but only after receiving at least one chunk)
                        if progress.chunks_received > 0:
                            stall_duration = progress.seconds_since_last_chunk()
                            if stall_duration > stall_timeout:
                                self.logger.warning(
                                    "streaming_stall_detected",
                                    stall_duration=f"{stall_duration:.1f}s",
                                    stall_timeout=stall_timeout,
                                    chunks_so_far=progress.chunks_received,
                                )
                                raise StreamingStallError(
                                    f"Streaming stalled for {stall_duration:.1f}s",
                                    stall_duration=stall_duration,
                                    last_output=progress.last_output,
                                )

                    output = "\n".join(output_parts)

                    # Log final progress
                    self.logger.info(
                        "streaming_complete",
                        total_chunks=progress.chunks_received,
                        total_bytes=progress.bytes_received,
                        total_time=f"{progress.elapsed_seconds():.1f}s",
                    )

                    # Scan for new files in working directory
                    generated_files = await self._scan_for_new_files(files_written)

                    duration = int((datetime.now() - start_time).total_seconds() * 1000)

                    self.logger.info(
                        "execution_complete",
                        success=True,
                        files_generated=len(generated_files),
                        duration_ms=duration,
                    )

                    return AgentResponse(
                        success=True,
                        output=output,
                        files=generated_files,
                        execution_time_ms=duration,
                    )

                except Exception as e:
                    # Check if this is a retryable file locking error
                    if is_file_lock_error(e) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        self.logger.warning(
                            "file_lock_retry",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            error=str(e),
                            delay=f"{delay:.2f}s",
                        )
                        await asyncio.sleep(delay)
                        last_error = e
                        continue
                    else:
                        # Not a file lock error or out of retries, re-raise
                        raise

            # If we exhausted all retries due to file lock errors
            if last_error:
                raise last_error

        except asyncio.TimeoutError:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            self.logger.error("execution_timeout", timeout=timeout or self.timeout)
            return AgentResponse(
                success=False,
                output="",
                error=f"Timeout after {timeout or self.timeout}s",
                execution_time_ms=duration,
            )

        except StreamingStallError as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            self.logger.error(
                "streaming_stall_error",
                stall_duration=e.stall_duration,
                last_output=e.last_output[:100] if e.last_output else "",
            )
            return AgentResponse(
                success=False,
                output="",
                error=f"Streaming stalled: {e}",
                execution_time_ms=duration,
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            # Check if this is a "Claude Code not found" error
            if is_claude_not_found_error(e):
                self.logger.error(
                    "claude_code_not_found",
                    error=str(e),
                    searched_paths=get_searched_paths(),
                )
                # Re-raise as specific error type for caller to handle
                raise ClaudeCodeNotFoundError(
                    f"Claude Code executable not found: {e}",
                    searched_paths=get_searched_paths(),
                ) from e

            self.logger.error("execution_error", error=str(e))
            return AgentResponse(
                success=False,
                output="",
                error=str(e),
                execution_time_ms=duration,
            )

        finally:
            # Restore original CLAUDE_CONFIG_DIR
            if original_config_dir is not None:
                os.environ["CLAUDE_CONFIG_DIR"] = original_config_dir
            elif "CLAUDE_CONFIG_DIR" in os.environ:
                del os.environ["CLAUDE_CONFIG_DIR"]

            # Clean up unique config directory
            try:
                if unique_config_dir.exists():
                    shutil.rmtree(unique_config_dir, ignore_errors=True)
            except Exception:
                pass  # Ignore cleanup errors

    async def workflow(
        self,
        steps: list[WorkflowStep],
        initial_context: Optional[dict] = None,
        on_step_complete: Optional[Callable[[int, str, AgentResponse], None]] = None,
    ) -> WorkflowResult:
        """
        Execute a multi-step workflow routine.

        Args:
            steps: List of workflow steps to execute
            initial_context: Initial variables for the workflow context
            on_step_complete: Callback after each step completes

        Returns:
            WorkflowResult with overall success and step results
        """
        start_time = datetime.now()
        context = WorkflowContext(
            working_dir=str(self.working_dir),
            variables=initial_context or {},
        )

        self.logger.info(
            "workflow_starting",
            steps=len(steps),
            step_names=[s.name for s in steps],
        )

        for i, step in enumerate(steps):
            context.current_step = i

            # Check condition
            if step.condition and not step.condition(context):
                self.logger.info("step_skipped", step=step.name, reason="condition_false")
                continue

            # Interpolate prompt with context variables
            prompt = step.prompt.format(**context.variables)

            self.logger.info(
                "step_starting",
                step=step.name,
                step_number=i + 1,
                total_steps=len(steps),
            )

            # Execute with retries
            last_error = None
            for attempt in range(step.retry):
                try:
                    result = await self.execute(
                        prompt=prompt,
                        tools=step.tools or self.DEFAULT_TOOLS,
                        timeout=step.timeout,
                    )

                    if result.success:
                        context.results.append(result)
                        if step.on_success:
                            step.on_success(context, result)
                        if on_step_complete:
                            on_step_complete(i, step.name, result)

                        self.logger.info(
                            "step_complete",
                            step=step.name,
                            success=True,
                            attempt=attempt + 1,
                        )
                        break

                    last_error = result.error

                except Exception as e:
                    last_error = str(e)
                    self.logger.warning(
                        "step_attempt_failed",
                        step=step.name,
                        attempt=attempt + 1,
                        error=str(e),
                    )

                if attempt < step.retry - 1:
                    await asyncio.sleep(1)  # Brief pause before retry

            else:
                # All retries exhausted
                error_msg = f"Step '{step.name}' failed after {step.retry} attempts: {last_error}"
                context.errors.append(error_msg)

                if step.on_failure:
                    step.on_failure(context, Exception(error_msg))

                self.logger.error(
                    "step_failed",
                    step=step.name,
                    error=error_msg,
                )

                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                return WorkflowResult(
                    success=False,
                    steps_completed=i,
                    total_steps=len(steps),
                    context=context,
                    duration_ms=duration,
                    error=error_msg,
                )

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        self.logger.info(
            "workflow_complete",
            success=True,
            steps_completed=len(steps),
            duration_ms=duration,
        )

        return WorkflowResult(
            success=True,
            steps_completed=len(steps),
            total_steps=len(steps),
            context=context,
            duration_ms=duration,
        )

    async def conversation(
        self,
        messages: list[dict],
        tools: Optional[list[str]] = None,
    ) -> AgentResponse:
        """
        Execute a multi-turn conversation.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Allowed tools for the conversation

        Returns:
            AgentResponse with the assistant's response
        """
        if not messages:
            return AgentResponse(
                success=False,
                output="",
                error="No messages provided",
            )

        # Build conversation prompt
        conversation_text = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            conversation_text.append(f"{role.upper()}: {content}")

        full_prompt = "\n\n".join(conversation_text)
        full_prompt += "\n\nASSISTANT:"

        return await self.execute(
            prompt=full_prompt,
            tools=tools,
        )

    async def _load_context_files(self, file_paths: list[str]) -> str:
        """Load content from context files."""
        context_parts = []
        for path in file_paths:
            full_path = self.working_dir / path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    context_parts.append(f"## File: {path}\n```\n{content}\n```")
                except Exception as e:
                    self.logger.warning(
                        "context_file_load_error",
                        path=path,
                        error=str(e),
                    )
        return "\n\n".join(context_parts)

    async def _scan_for_new_files(self, known_files: list[str]) -> list[GeneratedFile]:
        """Scan working directory for generated files."""
        files = []
        for file_path in known_files:
            full_path = self.working_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    language = self._detect_language(file_path)
                    files.append(GeneratedFile(
                        path=file_path,
                        content=content,
                        language=language,
                    ))
                except Exception:
                    pass
        return files

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".css": "css",
            ".html": "html",
            ".json": "json",
            ".md": "markdown",
            ".yaml": "yaml",
            ".yml": "yaml",
        }
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "text")


# Convenience function for simple execution
async def execute_with_sdk(
    prompt: str,
    working_dir: str = ".",
    tools: Optional[list[str]] = None,
) -> AgentResponse:
    """
    Convenience function for quick SDK execution.

    Example:
        result = await execute_with_sdk(
            "Create a Python function that calculates fibonacci numbers",
            working_dir="./src"
        )
    """
    tool = ClaudeAgentTool(working_dir=working_dir)
    return await tool.execute(prompt, tools=tools)
