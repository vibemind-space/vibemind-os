"""
Claude Monitor - AI-Powered Error Analysis for Coding Engine.

Watches coding engine output for errors and provides intelligent
improvement suggestions using Claude via the Anthropic API.

Features:
- Event-triggered analysis (TEST_FAILED, BUILD_FAILED, TYPE_ERROR)
- Context-aware suggestions using recent log history
- Markdown output to improvement_suggestions.md
- Rate limiting to avoid API spam

Usage:
    monitor = ClaudeMonitor(output_dir="./output")
    monitor.start()

    # Register with event bus
    event_bus.subscribe(EventType.TEST_FAILED, monitor.on_error_event)
    event_bus.subscribe(EventType.BUILD_FAILED, monitor.on_error_event)
"""

import asyncio
import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from collections import deque
import threading

from src.llm_config import get_model

logger = logging.getLogger(__name__)

# Module-level instance
_monitor_instance: Optional['ClaudeMonitor'] = None


def get_monitor() -> Optional['ClaudeMonitor']:
    """Get the global ClaudeMonitor instance."""
    return _monitor_instance


@dataclass
class ErrorContext:
    """Context for an error event."""
    error_type: str  # TEST_FAILED, BUILD_FAILED, TYPE_ERROR, LINT_ERROR
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    recent_logs: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    iteration: int = 0
    
    def to_prompt_context(self) -> str:
        """Format for Claude prompt."""
        parts = [
            f"## Error Type: {self.error_type}",
            f"**Message:** {self.message}",
        ]
        
        if self.file_path:
            parts.append(f"**File:** {self.file_path}")
        if self.line_number:
            parts.append(f"**Line:** {self.line_number}")
        if self.stack_trace:
            parts.append(f"\n**Stack Trace:**\n```\n{self.stack_trace}\n```")
        
        if self.recent_logs:
            parts.append(f"\n**Recent Log Context ({len(self.recent_logs)} lines):**")
            parts.append("```")
            parts.extend(self.recent_logs[-50:])  # Last 50 lines
            parts.append("```")
        
        return "\n".join(parts)


@dataclass
class Suggestion:
    """An improvement suggestion from Claude."""
    category: str  # code_fix, architecture, testing, performance, security
    title: str
    description: str
    code_example: Optional[str] = None
    priority: str = "medium"  # low, medium, high, critical
    related_file: Optional[str] = None
    error_context: Optional[ErrorContext] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_markdown(self) -> str:
        """Format as markdown."""
        priority_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }
        
        emoji = priority_emoji.get(self.priority, "⚪")
        
        lines = [
            f"### {emoji} [{self.category.upper()}] {self.title}",
            f"**Priority:** {self.priority} | **Time:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            self.description,
        ]
        
        if self.related_file:
            lines.append(f"\n**Related File:** `{self.related_file}`")
        
        if self.code_example:
            lines.append(f"\n**Suggested Change:**\n```\n{self.code_example}\n```")
        
        if self.error_context:
            lines.append(f"\n<details><summary>Error Context</summary>\n")
            lines.append(f"Error: {self.error_context.error_type}")
            lines.append(f"Message: {self.error_context.message}")
            lines.append("</details>")
        
        return "\n".join(lines)


class ClaudeMonitor:
    """
    AI-powered monitor that analyzes errors and provides suggestions.
    
    Uses the Anthropic API to analyze coding errors and generate
    intelligent improvement suggestions.
    """
    
    # Analysis prompt template
    ANALYSIS_PROMPT = """You are an expert code reviewer analyzing errors from an automated code generation system.

Given the following error context, provide a helpful improvement suggestion.

{error_context}

Please respond with a JSON object containing:
{{
    "category": "code_fix|architecture|testing|performance|security",
    "title": "Brief title for the suggestion",
    "description": "Detailed explanation of the issue and how to fix it",
    "code_example": "Optional code snippet showing the fix (or null)",
    "priority": "low|medium|high|critical",
    "related_file": "Path to related file if known (or null)"
}}

Focus on:
1. Root cause analysis - why did this error occur?
2. Concrete fix suggestions - what specific changes should be made?
3. Prevention strategies - how to avoid similar errors in the future?

Be concise but thorough. If you see patterns in the recent logs, mention them."""

    def __init__(
        self,
        output_dir: str,
        api_key: Optional[str] = None,
        suggestions_file: str = "improvement_suggestions.md",
        max_log_history: int = 100,
        rate_limit_seconds: float = 30.0,
        model: str = None
    ):
        """
        Initialize the Claude Monitor.
        
        Args:
            output_dir: Directory to write suggestions file
            api_key: Anthropic API key (or from ANTHROPIC_API_KEY env)
            suggestions_file: Name of the suggestions markdown file
            max_log_history: Maximum log lines to keep in memory
            rate_limit_seconds: Minimum seconds between API calls
            model: Claude model to use
        """
        global _monitor_instance
        
        self.output_dir = Path(output_dir)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.suggestions_path = self.output_dir / suggestions_file
        self.max_log_history = max_log_history
        self.rate_limit_seconds = rate_limit_seconds
        self.model = model or get_model("primary")
        
        # State
        self.log_history: deque = deque(maxlen=max_log_history)
        self.suggestions: list[Suggestion] = []
        self.last_api_call: Optional[datetime] = None
        self.error_count: int = 0
        self.suggestion_count: int = 0
        self.running: bool = False
        
        # Threading
        self._lock = threading.Lock()
        self._analysis_queue: Optional[asyncio.Queue] = None
        
        # Anthropic client (lazy init)
        self._client = None
        
        _monitor_instance = self
        
        logger.info(f"ClaudeMonitor initialized, suggestions will be written to: {self.suggestions_path}")
    
    @property
    def client(self):
        """Lazy-initialize Anthropic client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY not set - cannot analyze errors")
            
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        
        return self._client
    
    def start(self):
        """Start the monitor."""
        self.running = True
        self._ensure_suggestions_file()
        logger.info("ClaudeMonitor started")
    
    def stop(self):
        """Stop the monitor."""
        self.running = False
        logger.info(f"ClaudeMonitor stopped. Analyzed {self.error_count} errors, generated {self.suggestion_count} suggestions")
    
    def _ensure_suggestions_file(self):
        """Ensure the suggestions file exists with header."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.suggestions_path.exists():
            header = f"""# Improvement Suggestions

Generated by Claude Monitor - AI-Powered Error Analysis

**Project:** {self.output_dir.name}
**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

"""
            self.suggestions_path.write_text(header, encoding='utf-8')
    
    def add_log_line(self, line: str):
        """Add a log line to history."""
        with self._lock:
            self.log_history.append(line)
    
    def add_log_lines(self, lines: list[str]):
        """Add multiple log lines to history."""
        with self._lock:
            for line in lines:
                self.log_history.append(line)
    
    async def on_error_event(self, event: Any):
        """
        Handle an error event from the event bus.
        
        This is the main entry point for error analysis.
        """
        if not self.running:
            return
        
        # Parse the event into ErrorContext
        error_context = self._parse_event(event)
        if error_context is None:
            return
        
        self.error_count += 1
        
        # Check rate limit
        if not self._can_call_api():
            logger.debug(f"Rate limited, skipping analysis for {error_context.error_type}")
            return
        
        # Analyze and generate suggestion
        try:
            suggestion = await self._analyze_error(error_context)
            if suggestion:
                self.suggestions.append(suggestion)
                self.suggestion_count += 1
                self._write_suggestion(suggestion)
                logger.info(f"Generated suggestion: [{suggestion.category}] {suggestion.title}")
        except Exception as e:
            logger.warning(f"Failed to analyze error: {e}")
    
    def _parse_event(self, event: Any) -> Optional[ErrorContext]:
        """Parse an event into ErrorContext."""
        # Handle different event formats
        
        # If it's a dict
        if isinstance(event, dict):
            return ErrorContext(
                error_type=event.get("type", "UNKNOWN"),
                message=event.get("message", str(event)),
                file_path=event.get("file_path") or event.get("file"),
                line_number=event.get("line_number") or event.get("line"),
                stack_trace=event.get("stack_trace") or event.get("trace"),
                recent_logs=list(self.log_history),
                iteration=event.get("iteration", 0),
            )
        
        # If it has attributes (dataclass or object)
        if hasattr(event, "event_type"):
            return ErrorContext(
                error_type=str(event.event_type),
                message=getattr(event, "message", str(event)),
                file_path=getattr(event, "file_path", None),
                line_number=getattr(event, "line_number", None),
                stack_trace=getattr(event, "stack_trace", None),
                recent_logs=list(self.log_history),
                iteration=getattr(event, "iteration", 0),
            )
        
        # Fallback - treat as string
        return ErrorContext(
            error_type="UNKNOWN",
            message=str(event),
            recent_logs=list(self.log_history),
        )
    
    def _can_call_api(self) -> bool:
        """Check if we can make an API call (rate limiting)."""
        if self.last_api_call is None:
            return True
        
        elapsed = (datetime.now() - self.last_api_call).total_seconds()
        return elapsed >= self.rate_limit_seconds
    
    async def _analyze_error(self, context: ErrorContext) -> Optional[Suggestion]:
        """Analyze an error and generate a suggestion using Claude."""
        self.last_api_call = datetime.now()
        
        prompt = self.ANALYSIS_PROMPT.format(
            error_context=context.to_prompt_context()
        )
        
        try:
            # Make API call (sync - we're in async context so run in executor)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}]
                )
            )
            
            # Parse response
            response_text = response.content[0].text
            
            # Extract JSON from response (might be wrapped in markdown)
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                logger.warning("No JSON found in Claude response")
                return None
            
            data = json.loads(json_match.group())
            
            return Suggestion(
                category=data.get("category", "code_fix"),
                title=data.get("title", "Suggestion"),
                description=data.get("description", response_text),
                code_example=data.get("code_example"),
                priority=data.get("priority", "medium"),
                related_file=data.get("related_file") or context.file_path,
                error_context=context,
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Claude response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return None
    
    def _write_suggestion(self, suggestion: Suggestion):
        """Append a suggestion to the markdown file."""
        try:
            with open(self.suggestions_path, 'a', encoding='utf-8') as f:
                f.write("\n\n")
                f.write(suggestion.to_markdown())
                f.write("\n\n---")
            
            logger.debug(f"Wrote suggestion to {self.suggestions_path}")
        except Exception as e:
            logger.error(f"Failed to write suggestion: {e}")
    
    def get_stats(self) -> dict[str, Any]:
        """Get monitor statistics."""
        return {
            "errors_analyzed": self.error_count,
            "suggestions_generated": self.suggestion_count,
            "log_lines_tracked": len(self.log_history),
            "suggestions_file": str(self.suggestions_path),
            "running": self.running,
        }
    
    # ==== Event Handler Factories ====
    
    def create_test_failed_handler(self) -> Callable:
        """Create a handler for TEST_FAILED events."""
        async def handler(event):
            event_dict = {"type": "TEST_FAILED"}
            if hasattr(event, 'data'):
                event_dict.update(event.data)
            if hasattr(event, 'message'):
                event_dict["message"] = event.message
            await self.on_error_event(event_dict)
        return handler
    
    def create_build_failed_handler(self) -> Callable:
        """Create a handler for BUILD_FAILED events."""
        async def handler(event):
            event_dict = {"type": "BUILD_FAILED"}
            if hasattr(event, 'data'):
                event_dict.update(event.data)
            if hasattr(event, 'message'):
                event_dict["message"] = event.message
            await self.on_error_event(event_dict)
        return handler
    
    def create_type_error_handler(self) -> Callable:
        """Create a handler for TYPE_ERROR events."""
        async def handler(event):
            event_dict = {"type": "TYPE_ERROR"}
            if hasattr(event, 'data'):
                event_dict.update(event.data)
            if hasattr(event, 'message'):
                event_dict["message"] = event.message
            await self.on_error_event(event_dict)
        return handler


# ==== Convenience Function ====

def create_monitor(output_dir: str, **kwargs) -> ClaudeMonitor:
    """
    Create and start a Claude Monitor.
    
    Args:
        output_dir: Directory for suggestions file
        **kwargs: Additional arguments for ClaudeMonitor
    
    Returns:
        Started ClaudeMonitor instance
    """
    monitor = ClaudeMonitor(output_dir=output_dir, **kwargs)
    monitor.start()
    return monitor