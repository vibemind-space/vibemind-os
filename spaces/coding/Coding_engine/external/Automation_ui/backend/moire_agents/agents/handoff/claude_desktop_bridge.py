"""
Claude Desktop Bridge - Two-way communication with Claude Desktop projects

Enables the handoff system to:
1. Send tasks to Claude Desktop
2. Receive structured feedback/reports via event stream
3. Parse Claude Desktop responses for automation decisions

The Claude Desktop project needs specific instructions to output
structured feedback that this bridge can capture.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ReportType(Enum):
    """Types of reports Claude Desktop can send."""
    STATUS = "status"           # Current status update
    COMPLETION = "completion"   # Task completed
    ERROR = "error"             # Error occurred
    REQUEST = "request"         # Requesting action from automation
    DATA = "data"               # Data/results to process


@dataclass
class ClaudeDesktopReport:
    """Structured report from Claude Desktop."""
    report_type: ReportType
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    task_id: Optional[str] = None

    # For REQUEST type - what action is needed
    requested_action: Optional[str] = None
    action_params: Dict[str, Any] = field(default_factory=dict)


# ==================== Project Instructions ====================

CLAUDE_DESKTOP_INSTRUCTIONS = """
## Automation Integration Instructions

You are connected to a desktop automation system. When completing tasks, output structured feedback using this format so the automation can track progress and take actions.

### Report Format

Always wrap reports in a code block with `automation-report` tag:

```automation-report
{
  "type": "status|completion|error|request|data",
  "message": "Human readable message",
  "task_id": "optional task identifier",
  "data": {},
  "request": {
    "action": "action_name",
    "params": {}
  }
}
```

### Report Types

1. **status** - Progress updates
```automation-report
{"type": "status", "message": "Analyzing Docker containers...", "data": {"progress": 50}}
```

2. **completion** - Task finished successfully
```automation-report
{"type": "completion", "message": "Report generated", "data": {"file": "docker_report.docx"}}
```

3. **error** - Something went wrong
```automation-report
{"type": "error", "message": "Cannot connect to Docker daemon", "data": {"error_code": "DOCKER_NOT_RUNNING"}}
```

4. **request** - Need automation to do something
```automation-report
{"type": "request", "message": "Need to save file", "request": {"action": "save_file", "params": {"path": "C:/reports/", "filename": "report.docx"}}}
```

5. **data** - Return processed data
```automation-report
{"type": "data", "message": "Container info", "data": {"containers": [{"name": "nginx", "status": "running"}]}}
```

### Available Request Actions

The automation system can perform these actions when you request them:
- `save_file` - Save content to a file
- `open_url` - Open a URL in browser
- `run_command` - Execute a shell command
- `capture_screen` - Take a screenshot
- `click_element` - Click a UI element
- `type_text` - Type text somewhere
- `notify_user` - Show notification

### Example Workflow

For a Docker debug task:
1. Status: "Starting Docker analysis..."
2. Request: {"action": "run_command", "params": {"cmd": "docker ps -a"}}
3. Data: Container list received
4. Status: "Generating report..."
5. Request: {"action": "save_file", "params": {"content": "...", "path": "report.docx"}}
6. Completion: "Docker debug report saved"

Always output reports so the automation system stays informed!
"""


# ==================== Event Stream ====================

class EventStream:
    """
    Event stream for receiving reports from Claude Desktop.

    Captures screen content, parses automation-report blocks,
    and dispatches to handlers.
    """

    def __init__(self):
        self._handlers: Dict[ReportType, List[Callable]] = {
            rt: [] for rt in ReportType
        }
        self._all_handlers: List[Callable] = []
        self._reports: List[ClaudeDesktopReport] = []
        self._running = False

    def on(self, report_type: ReportType, handler: Callable):
        """Register handler for specific report type."""
        self._handlers[report_type].append(handler)

    def on_any(self, handler: Callable):
        """Register handler for all report types."""
        self._all_handlers.append(handler)

    async def emit(self, report: ClaudeDesktopReport):
        """Emit a report to all registered handlers."""
        self._reports.append(report)

        # Call type-specific handlers
        for handler in self._handlers.get(report.report_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(report)
                else:
                    handler(report)
            except Exception as e:
                logger.error(f"Handler error: {e}")

        # Call all-type handlers
        for handler in self._all_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(report)
                else:
                    handler(report)
            except Exception as e:
                logger.error(f"Handler error: {e}")

    def get_reports(self, report_type: Optional[ReportType] = None) -> List[ClaudeDesktopReport]:
        """Get all reports, optionally filtered by type."""
        if report_type:
            return [r for r in self._reports if r.report_type == report_type]
        return self._reports.copy()

    def clear(self):
        """Clear all reports."""
        self._reports.clear()


# ==================== Report Parser ====================

class ReportParser:
    """Parses automation-report blocks from text."""

    # Pattern to match automation-report code blocks
    REPORT_PATTERN = re.compile(
        r'```automation-report\s*\n(.*?)\n```',
        re.DOTALL | re.MULTILINE
    )

    @classmethod
    def parse_text(cls, text: str) -> List[ClaudeDesktopReport]:
        """Extract all automation reports from text."""
        reports = []

        matches = cls.REPORT_PATTERN.findall(text)
        for match in matches:
            try:
                report = cls._parse_json(match.strip())
                if report:
                    reports.append(report)
            except Exception as e:
                logger.warning(f"Failed to parse report: {e}")

        return reports

    @classmethod
    def _parse_json(cls, json_str: str) -> Optional[ClaudeDesktopReport]:
        """Parse JSON into ClaudeDesktopReport."""
        try:
            data = json.loads(json_str)

            report_type = ReportType(data.get("type", "status"))
            message = data.get("message", "")

            report = ClaudeDesktopReport(
                report_type=report_type,
                message=message,
                data=data.get("data", {}),
                task_id=data.get("task_id")
            )

            # Handle request type
            if report_type == ReportType.REQUEST and "request" in data:
                req = data["request"]
                report.requested_action = req.get("action")
                report.action_params = req.get("params", {})

            return report

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in report: {e}")
            return None
        except ValueError as e:
            logger.warning(f"Invalid report type: {e}")
            return None


# ==================== Claude Desktop Bridge ====================

class ClaudeDesktopBridge:
    """
    Bridge between handoff system and Claude Desktop.

    Handles:
    - Sending tasks to Claude Desktop
    - Monitoring for responses
    - Parsing and dispatching reports
    - Executing requested actions
    """

    def __init__(
        self,
        moire_host: str = "localhost",
        moire_port: int = 8765,
        poll_interval: float = 2.0
    ):
        self.moire_host = moire_host
        self.moire_port = moire_port
        self.poll_interval = poll_interval

        self.event_stream = EventStream()
        self.parser = ReportParser()

        self._moire_client = None
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_seen_text = ""

        # Action handlers for REQUEST reports
        self._action_handlers: Dict[str, Callable] = {}
        self._register_default_actions()

    def _register_default_actions(self):
        """Register default action handlers."""
        self.register_action("notify_user", self._action_notify)
        self.register_action("run_command", self._action_run_command)
        self.register_action("save_file", self._action_save_file)

    def register_action(self, action_name: str, handler: Callable):
        """Register a handler for a requested action."""
        self._action_handlers[action_name] = handler

    async def _get_moire_client(self):
        """Get or create MoireServer client."""
        if self._moire_client is None:
            try:
                from bridge.websocket_client import MoireWebSocketClient
                self._moire_client = MoireWebSocketClient(
                    host=self.moire_host,
                    port=self.moire_port
                )
                await self._moire_client.connect()
            except Exception as e:
                logger.warning(f"Could not connect to MoireServer: {e}")
                self._moire_client = None
        return self._moire_client

    async def start_monitoring(self):
        """Start monitoring Claude Desktop for reports."""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("ClaudeDesktopBridge: Started monitoring")

    async def stop_monitoring(self):
        """Stop monitoring."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("ClaudeDesktopBridge: Stopped monitoring")

    async def _monitor_loop(self):
        """Main monitoring loop - captures screen and parses reports."""
        while self._monitoring:
            try:
                # Capture screen and get OCR text
                text = await self._capture_screen_text()

                if text and text != self._last_seen_text:
                    # Find new content
                    new_text = self._get_new_content(text)

                    if new_text:
                        # Parse reports from new text
                        reports = self.parser.parse_text(new_text)

                        for report in reports:
                            logger.info(f"ClaudeDesktopBridge: Received {report.report_type.value} report")
                            await self.event_stream.emit(report)

                            # Handle REQUEST reports
                            if report.report_type == ReportType.REQUEST:
                                await self._handle_request(report)

                    self._last_seen_text = text

            except Exception as e:
                logger.error(f"Monitor error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _capture_screen_text(self) -> str:
        """Capture screen and extract text via OCR."""
        client = await self._get_moire_client()
        if not client:
            return ""

        try:
            result = await client.capture_and_wait_for_complete(timeout=10.0)
            if result.success:
                # Get all OCR text
                elements = client.get_all_elements()
                return "\n".join(e.text for e in elements if e.text)
        except Exception as e:
            logger.error(f"Screen capture error: {e}")

        return ""

    def _get_new_content(self, current_text: str) -> str:
        """Get content that's new since last check."""
        if not self._last_seen_text:
            return current_text

        # Simple approach: return content after last seen
        # In practice, you'd want smarter diffing
        if current_text.startswith(self._last_seen_text):
            return current_text[len(self._last_seen_text):]

        return current_text

    async def _handle_request(self, report: ClaudeDesktopReport):
        """Handle a REQUEST type report by executing the action."""
        action = report.requested_action
        params = report.action_params

        if not action:
            logger.warning("Request report missing action")
            return

        handler = self._action_handlers.get(action)
        if handler:
            try:
                logger.info(f"Executing action: {action}")
                if asyncio.iscoroutinefunction(handler):
                    await handler(params)
                else:
                    handler(params)
            except Exception as e:
                logger.error(f"Action {action} failed: {e}")
        else:
            logger.warning(f"No handler for action: {action}")

    # ==================== Default Action Handlers ====================

    async def _action_notify(self, params: Dict):
        """Show notification to user."""
        message = params.get("message", "Notification from Claude Desktop")
        logger.info(f"NOTIFICATION: {message}")
        # Could use system notifications here

    async def _action_run_command(self, params: Dict):
        """Run a shell command."""
        cmd = params.get("cmd", "")
        if not cmd:
            return

        logger.info(f"Running command: {cmd}")
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        return {
            "stdout": stdout.decode() if stdout else "",
            "stderr": stderr.decode() if stderr else "",
            "returncode": proc.returncode
        }

    async def _action_save_file(self, params: Dict):
        """Save content to a file."""
        path = params.get("path", "")
        content = params.get("content", "")

        if path and content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Saved file: {path}")

    # ==================== High-level API ====================

    async def send_task_and_wait(
        self,
        task: str,
        timeout: float = 60.0,
        wait_for_completion: bool = True
    ) -> Optional[ClaudeDesktopReport]:
        """
        Send a task to Claude Desktop and wait for completion report.

        Args:
            task: Task message to send
            timeout: Max time to wait
            wait_for_completion: Whether to wait for completion report

        Returns:
            Completion report or None if timeout
        """
        from .runtime import AgentRuntime
        from .orchestrator_agent import OrchestratorAgent
        from .execution_agent import ExecutionAgent
        from .messages import UserTask

        # Start monitoring
        await self.start_monitoring()

        completion_event = asyncio.Event()
        final_report: Optional[ClaudeDesktopReport] = None

        def on_completion(report: ClaudeDesktopReport):
            nonlocal final_report
            final_report = report
            completion_event.set()

        if wait_for_completion:
            self.event_stream.on(ReportType.COMPLETION, on_completion)
            self.event_stream.on(ReportType.ERROR, on_completion)

        # Send task via handoff system
        runtime = AgentRuntime(max_handoffs=15)
        await runtime.register_agent("orchestrator", OrchestratorAgent())
        await runtime.register_agent("execution", ExecutionAgent())

        user_task = UserTask(
            goal=f"Send to Claude Desktop: {task}",
            context={
                "workflow": "claude_desktop",
                "message": task
            }
        )

        await runtime.run_task(user_task, entry_agent="orchestrator")

        if wait_for_completion:
            try:
                await asyncio.wait_for(completion_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for completion")

        await self.stop_monitoring()
        return final_report


def get_project_instructions() -> str:
    """Get the instructions to add to Claude Desktop project."""
    return CLAUDE_DESKTOP_INSTRUCTIONS
