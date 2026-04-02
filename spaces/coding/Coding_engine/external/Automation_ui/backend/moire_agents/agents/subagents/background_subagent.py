"""
Background Subagent - Long-running monitors that don't block the queue.

BackgroundSubagents monitor for conditions like:
- ELEMENT_APPEARS: Wait for a UI element to appear
- ELEMENT_DISAPPEARS: Wait for element to disappear (loading finished)
- TEXT_CONTAINS: Wait for specific text on screen
- STATE_CHANGE: Wait for application state change
- FILE_EXISTS: Wait for file to appear
- DOWNLOAD_COMPLETE: Wait for download to finish

Each monitor runs in the background and triggers a callback when
the condition is met or times out.

Example:
    Monitor for download completion:
    - Condition: "Download complete" text appears
    - Callback: Notify orchestrator that download finished
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable

from .base_subagent import BaseSubagent, SubagentContext, SubagentOutput

logger = logging.getLogger(__name__)


class MonitorCondition(Enum):
    """Types of conditions to monitor."""
    ELEMENT_APPEARS = "element_appears"       # UI element becomes visible
    ELEMENT_DISAPPEARS = "element_disappears" # UI element disappears
    TEXT_CONTAINS = "text_contains"           # Text appears on screen
    STATE_CHANGE = "state_change"             # Application state changes
    FILE_EXISTS = "file_exists"               # File appears on disk
    FILE_MODIFIED = "file_modified"           # File is modified
    DOWNLOAD_COMPLETE = "download_complete"   # Download finishes
    WINDOW_OPENS = "window_opens"             # New window appears
    WINDOW_CLOSES = "window_closes"           # Window closes
    PROCESS_STARTS = "process_starts"         # Process starts running
    PROCESS_ENDS = "process_ends"             # Process stops running
    CUSTOM = "custom"                         # Custom condition check


@dataclass
class MonitorConfig:
    """Configuration for a background monitor."""
    condition: MonitorCondition
    target: str                    # What to look for (element name, text, file path, etc.)
    check_interval: float = 1.0   # How often to check (seconds)
    timeout: Optional[float] = None  # Max time to monitor (None = indefinite)
    screenshot_required: bool = True  # Whether to take screenshots for visual checks
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorResult:
    """Result from a background monitor check."""
    condition_met: bool
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    check_number: int = 0


class BackgroundSubagent(BaseSubagent):
    """
    Subagent that monitors for conditions in the background.

    Unlike other subagents, this one runs continuously until
    the condition is met or timeout occurs.
    """

    def __init__(
        self,
        subagent_id: str,
        openrouter_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the background subagent.

        Args:
            subagent_id: Unique identifier
            openrouter_client: LLM client for vision checks
            config: Additional configuration
        """
        super().__init__(subagent_id, openrouter_client, config)
        self._active_monitors: Dict[str, asyncio.Task] = {}

    def get_capabilities(self) -> Dict[str, Any]:
        """Return capabilities of this background subagent."""
        return {
            "type": "background",
            "can_handle": list(MonitorCondition.__members__.keys()),
            "supports_vision": self.client is not None,
            "active_monitors": len(self._active_monitors)
        }

    async def execute(self, context: SubagentContext) -> SubagentOutput:
        """
        Execute a single condition check.

        This is called by the runner for one-shot checks.
        For continuous monitoring, use start_monitor().

        Args:
            context: SubagentContext with check parameters

        Returns:
            SubagentOutput with condition check result
        """
        params = context.params
        condition = MonitorCondition(params.get("check_type", "element_appears"))
        target = params.get("target", "")

        logger.info(f"Background check [{condition.value}]: {target}")

        # Perform the check
        result = await self._check_condition(
            condition=condition,
            target=target,
            screenshot_bytes=context.screenshot_bytes,
            params=params
        )

        return SubagentOutput(
            success=True,
            result={
                "condition_met": result.condition_met,
                "details": result.details,
                "timestamp": result.timestamp,
                "condition": condition.value,
                "target": target
            },
            confidence=0.9 if result.condition_met else 0.5,
            reasoning=f"Check {condition.value}: {'met' if result.condition_met else 'not met'}"
        )

    async def _check_condition(
        self,
        condition: MonitorCondition,
        target: str,
        screenshot_bytes: Optional[bytes] = None,
        params: Dict[str, Any] = None
    ) -> MonitorResult:
        """Check if a condition is met."""
        params = params or {}

        if condition == MonitorCondition.ELEMENT_APPEARS:
            return await self._check_element_appears(target, screenshot_bytes, params)

        elif condition == MonitorCondition.ELEMENT_DISAPPEARS:
            return await self._check_element_disappears(target, screenshot_bytes, params)

        elif condition == MonitorCondition.TEXT_CONTAINS:
            return await self._check_text_contains(target, screenshot_bytes, params)

        elif condition == MonitorCondition.FILE_EXISTS:
            return self._check_file_exists(target, params)

        elif condition == MonitorCondition.FILE_MODIFIED:
            return self._check_file_modified(target, params)

        elif condition == MonitorCondition.DOWNLOAD_COMPLETE:
            return self._check_download_complete(target, params)

        elif condition == MonitorCondition.PROCESS_STARTS:
            return await self._check_process_running(target, params, should_exist=True)

        elif condition == MonitorCondition.PROCESS_ENDS:
            return await self._check_process_running(target, params, should_exist=False)

        elif condition == MonitorCondition.WINDOW_OPENS:
            return await self._check_window_exists(target, params, should_exist=True)

        elif condition == MonitorCondition.WINDOW_CLOSES:
            return await self._check_window_exists(target, params, should_exist=False)

        else:
            # Custom or unknown condition
            return MonitorResult(
                condition_met=False,
                details={"error": f"Unknown condition: {condition.value}"}
            )

    async def _check_element_appears(
        self,
        target: str,
        screenshot_bytes: Optional[bytes],
        params: Dict[str, Any]
    ) -> MonitorResult:
        """Check if a UI element has appeared."""
        if not screenshot_bytes:
            return MonitorResult(
                condition_met=False,
                details={"error": "No screenshot provided for element check"}
            )

        # Use LLM vision to check for element
        if self.client:
            try:
                import base64
                image_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

                response = await self.client.chat_completion(
                    model="openai/gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a UI element detector. Answer only 'YES' or 'NO'."},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Is the element '{target}' visible in this screenshot? Answer YES or NO."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                            ]
                        }
                    ],
                    temperature=0.1,
                    max_tokens=10
                )

                answer = response.get("choices", [{}])[0].get("message", {}).get("content", "NO").strip().upper()
                found = "YES" in answer

                return MonitorResult(
                    condition_met=found,
                    details={"element": target, "llm_response": answer}
                )

            except Exception as e:
                logger.error(f"LLM vision check failed: {e}")

        # Fallback: basic check (always returns False without LLM)
        return MonitorResult(
            condition_met=False,
            details={"element": target, "method": "no_llm_available"}
        )

    async def _check_element_disappears(
        self,
        target: str,
        screenshot_bytes: Optional[bytes],
        params: Dict[str, Any]
    ) -> MonitorResult:
        """Check if a UI element has disappeared."""
        # Check if element appears
        result = await self._check_element_appears(target, screenshot_bytes, params)
        # Invert the result
        return MonitorResult(
            condition_met=not result.condition_met,
            details={**result.details, "check_type": "disappeared"}
        )

    async def _check_text_contains(
        self,
        target: str,
        screenshot_bytes: Optional[bytes],
        params: Dict[str, Any]
    ) -> MonitorResult:
        """Check if specific text appears on screen."""
        if not screenshot_bytes:
            return MonitorResult(
                condition_met=False,
                details={"error": "No screenshot provided for text check"}
            )

        # Use LLM vision for text detection
        if self.client:
            try:
                import base64
                image_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

                response = await self.client.chat_completion(
                    model="openai/gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a text detector. Answer only 'YES' or 'NO'."},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Does this screenshot contain the text '{target}' (or very similar)? Answer YES or NO."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                            ]
                        }
                    ],
                    temperature=0.1,
                    max_tokens=10
                )

                answer = response.get("choices", [{}])[0].get("message", {}).get("content", "NO").strip().upper()
                found = "YES" in answer

                return MonitorResult(
                    condition_met=found,
                    details={"text": target, "llm_response": answer}
                )

            except Exception as e:
                logger.error(f"LLM text check failed: {e}")

        return MonitorResult(
            condition_met=False,
            details={"text": target, "method": "no_llm_available"}
        )

    def _check_file_exists(self, target: str, params: Dict[str, Any]) -> MonitorResult:
        """Check if a file exists."""
        exists = os.path.exists(target)
        details = {"path": target, "exists": exists}

        if exists:
            stat = os.stat(target)
            details["size"] = stat.st_size
            details["modified"] = stat.st_mtime

        return MonitorResult(condition_met=exists, details=details)

    def _check_file_modified(self, target: str, params: Dict[str, Any]) -> MonitorResult:
        """Check if a file has been modified since a reference time."""
        if not os.path.exists(target):
            return MonitorResult(
                condition_met=False,
                details={"path": target, "error": "File does not exist"}
            )

        stat = os.stat(target)
        reference_time = params.get("reference_time", time.time() - 60)  # Default: last minute

        modified = stat.st_mtime > reference_time

        return MonitorResult(
            condition_met=modified,
            details={
                "path": target,
                "modified_time": stat.st_mtime,
                "reference_time": reference_time,
                "modified": modified
            }
        )

    def _check_download_complete(self, target: str, params: Dict[str, Any]) -> MonitorResult:
        """Check if a download has completed."""
        download_dir = params.get("download_dir", os.path.expanduser("~/Downloads"))
        file_pattern = target.lower()

        # Look for completed downloads
        for filename in os.listdir(download_dir):
            filepath = os.path.join(download_dir, filename)

            # Skip partial/temp files
            if filename.endswith(('.crdownload', '.part', '.tmp', '.download')):
                continue

            # Match pattern
            if file_pattern in filename.lower():
                stat = os.stat(filepath)
                # Check if file is stable (not being written to)
                return MonitorResult(
                    condition_met=True,
                    details={
                        "file": filepath,
                        "size": stat.st_size,
                        "completed": True
                    }
                )

        return MonitorResult(
            condition_met=False,
            details={"pattern": target, "download_dir": download_dir, "completed": False}
        )

    async def _check_process_running(
        self,
        target: str,
        params: Dict[str, Any],
        should_exist: bool
    ) -> MonitorResult:
        """Check if a process is running."""
        try:
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {target}*'],
                capture_output=True,
                text=True
            )
            is_running = target.lower() in result.stdout.lower()

            condition_met = is_running if should_exist else not is_running

            return MonitorResult(
                condition_met=condition_met,
                details={
                    "process": target,
                    "is_running": is_running,
                    "expected_state": "running" if should_exist else "stopped"
                }
            )
        except Exception as e:
            return MonitorResult(
                condition_met=False,
                details={"error": str(e), "process": target}
            )

    async def _check_window_exists(
        self,
        target: str,
        params: Dict[str, Any],
        should_exist: bool
    ) -> MonitorResult:
        """Check if a window with specific title exists."""
        try:
            import ctypes
            user32 = ctypes.windll.user32

            # Enumerate windows to find matching title
            found = False
            window_titles = []

            def enum_callback(hwnd, _):
                nonlocal found
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buffer, length + 1)
                        title = buffer.value
                        window_titles.append(title)
                        if target.lower() in title.lower():
                            found = True
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

            condition_met = found if should_exist else not found

            return MonitorResult(
                condition_met=condition_met,
                details={
                    "target_title": target,
                    "window_found": found,
                    "expected_state": "open" if should_exist else "closed"
                }
            )
        except Exception as e:
            return MonitorResult(
                condition_met=False,
                details={"error": str(e), "target_title": target}
            )


# Runner for the background subagent
from core.subagent_runner import SubagentRunner, SubagentType, SubagentTask, SubagentResult


class BackgroundSubagentRunner(SubagentRunner):
    """
    Runner that wraps BackgroundSubagent for Redis stream processing.

    Listens to moire:background stream and processes monitor checks.
    """

    def __init__(
        self,
        redis_client,
        worker_id: Optional[str] = None,
        openrouter_client: Optional[Any] = None
    ):
        super().__init__(
            redis_client=redis_client,
            agent_type=SubagentType.BACKGROUND,
            worker_id=worker_id or "background_monitor"
        )
        self.subagent = BackgroundSubagent(
            subagent_id=self.worker_id,
            openrouter_client=openrouter_client
        )

    async def execute(self, task: SubagentTask) -> SubagentResult:
        """Process a background check task."""
        # Build context from task params
        context = SubagentContext(
            task_id=task.task_id,
            goal=f"Check condition: {task.params.get('check_type', 'unknown')}",
            params=task.params,
            screenshot_bytes=task.params.get("screenshot_bytes"),
            timeout=task.timeout
        )

        # Execute check
        output = await self.subagent.process(context)

        return SubagentResult(
            success=output.success,
            result=output.result,
            confidence=output.confidence,
            error=output.error
        )


# Convenience function to start background workers
async def start_background_workers(
    redis_client,
    openrouter_client=None,
    num_workers: int = 2
) -> List[BackgroundSubagentRunner]:
    """
    Start background monitor workers.

    Args:
        redis_client: Connected RedisStreamClient
        openrouter_client: Optional LLM client for vision checks
        num_workers: Number of workers to start

    Returns:
        List of running BackgroundSubagentRunner instances
    """
    import asyncio

    runners = []

    for i in range(num_workers):
        runner = BackgroundSubagentRunner(
            redis_client=redis_client,
            worker_id=f"background_worker_{i}",
            openrouter_client=openrouter_client
        )
        runners.append(runner)
        asyncio.create_task(runner.run_forever())
        logger.info(f"Started background worker: {runner.worker_id}")

    return runners
