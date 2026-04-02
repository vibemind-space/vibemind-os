"""
CLI Tracker - Monitors and records Claude CLI activity.

Provides detailed tracking of all CLI calls including:
- Prompt/Response content
- Token estimates
- Latency measurements
- Success/Error rates
- Agent-level breakdown
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Any
from collections import deque
import structlog
import hashlib

logger = structlog.get_logger(__name__)


@dataclass
class CLICall:
    """
    Record of a single Claude CLI call.
    
    Captures all relevant information for monitoring and debugging.
    """
    id: str
    timestamp: datetime
    agent: str
    prompt: str
    prompt_preview: str  # First 200 chars for display
    response: str
    response_preview: str  # First 500 chars for display
    tokens_in: int  # Estimated input tokens
    tokens_out: int  # Estimated output tokens
    latency_ms: int
    success: bool
    error: Optional[str] = None
    files_modified: list[str] = field(default_factory=list)
    working_dir: Optional[str] = None
    
    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        Estimate token count (rough approximation).
        
        Claude uses ~4 chars per token on average.
        """
        if not text:
            return 0
        return len(text) // 4
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "agent": self.agent,
            "prompt_preview": self.prompt_preview,
            "response_preview": self.response_preview,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error": self.error,
            "files_modified": self.files_modified,
        }
    
    def to_summary(self) -> dict:
        """Short summary for dashboard display."""
        return {
            "id": self.id[:8],
            "time": self.timestamp.strftime("%H:%M:%S"),
            "agent": self.agent,
            "success": "PASS" if self.success else "FAIL",
            "preview": self.prompt_preview[:50] + "..." if len(self.prompt_preview) > 50 else self.prompt_preview,
            "latency": f"{self.latency_ms}ms",
            "tokens": f"{self.tokens_in + self.tokens_out}",
        }


@dataclass
class CLIStats:
    """
    Aggregated statistics from CLI calls.
    """
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_latency_ms: int = 0
    avg_latency_ms: float = 0.0
    calls_by_agent: dict[str, int] = field(default_factory=dict)
    errors_by_type: dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        """Percentage of successful calls."""
        if self.total_calls == 0:
            return 100.0
        return (self.successful_calls / self.total_calls) * 100
    
    @property
    def total_tokens(self) -> int:
        """Total tokens (in + out)."""
        return self.total_tokens_in + self.total_tokens_out
    
    def update_from_call(self, call: CLICall) -> None:
        """Update stats from a new call."""
        self.total_calls += 1
        if call.success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            if call.error:
                error_type = call.error.split(":")[0] if ":" in call.error else "UNKNOWN"
                self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1
        
        self.total_tokens_in += call.tokens_in
        self.total_tokens_out += call.tokens_out
        self.total_latency_ms += call.latency_ms
        
        if self.total_calls > 0:
            self.avg_latency_ms = self.total_latency_ms / self.total_calls
        
        self.calls_by_agent[call.agent] = self.calls_by_agent.get(call.agent, 0) + 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 1),
            "total_tokens": self.total_tokens,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "calls_by_agent": self.calls_by_agent,
            "errors_by_type": self.errors_by_type,
        }


class CLICallStore:
    """
    Thread-safe store for CLI call history.
    
    Maintains a bounded history of recent calls and aggregated stats.
    """
    
    def __init__(self, max_history: int = 100):
        """
        Initialize store.
        
        Args:
            max_history: Maximum number of calls to keep in history
        """
        self._calls: deque[CLICall] = deque(maxlen=max_history)
        self._stats = CLIStats()
        self._lock = asyncio.Lock()
        self._handlers: list[Callable[[CLICall], Any]] = []
        self.logger = logger.bind(component="cli_call_store")
    
    def on_call(self, handler: Callable[[CLICall], Any]) -> None:
        """Register a handler to be called when a new CLI call is recorded."""
        self._handlers.append(handler)
    
    async def record(self, call: CLICall) -> None:
        """
        Record a CLI call.
        
        Args:
            call: The CLI call to record
        """
        async with self._lock:
            self._calls.append(call)
            self._stats.update_from_call(call)
        
        self.logger.debug(
            "cli_call_recorded",
            call_id=call.id[:8],
            agent=call.agent,
            success=call.success,
            latency_ms=call.latency_ms,
        )
        
        # Notify handlers
        for handler in self._handlers:
            try:
                result = handler(call)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.warning("handler_error", error=str(e))
    
    async def get_recent(self, limit: int = 10) -> list[CLICall]:
        """Get most recent calls."""
        async with self._lock:
            return list(self._calls)[-limit:]
    
    async def get_by_agent(self, agent: str, limit: int = 10) -> list[CLICall]:
        """Get recent calls by a specific agent."""
        async with self._lock:
            return [c for c in self._calls if c.agent == agent][-limit:]
    
    async def get_stats(self) -> CLIStats:
        """Get aggregated statistics."""
        async with self._lock:
            return self._stats
    
    async def get_full_prompt(self, call_id: str) -> Optional[str]:
        """Get full prompt for a specific call."""
        async with self._lock:
            for call in self._calls:
                if call.id == call_id:
                    return call.prompt
            return None
    
    async def get_full_response(self, call_id: str) -> Optional[str]:
        """Get full response for a specific call."""
        async with self._lock:
            for call in self._calls:
                if call.id == call_id:
                    return call.response
            return None
    
    async def clear(self) -> None:
        """Clear all history (stats are preserved)."""
        async with self._lock:
            self._calls.clear()


# Global singleton store
_global_store: Optional[CLICallStore] = None


def get_cli_store() -> CLICallStore:
    """Get the global CLI call store."""
    global _global_store
    if _global_store is None:
        _global_store = CLICallStore()
    return _global_store


# ============================================================================
# Active CLI Call Tracking
# ============================================================================
# Tracks the number of currently executing CLI calls globally.

_global_active_count: int = 0
_active_lock: asyncio.Lock = asyncio.Lock()


async def increment_active() -> int:
    """
    Increment the active CLI call count.

    Call this when starting a CLI call.

    Returns:
        The new active count after incrementing.
    """
    global _global_active_count
    async with _active_lock:
        _global_active_count += 1
        return _global_active_count


async def decrement_active() -> int:
    """
    Decrement the active CLI call count.

    Call this when a CLI call completes (success or failure).

    Returns:
        The new active count after decrementing.
    """
    global _global_active_count
    async with _active_lock:
        _global_active_count = max(0, _global_active_count - 1)
        return _global_active_count


def get_active_count() -> int:
    """
    Get the current number of active (in-progress) CLI calls.

    This is a synchronous function for easy access from logs/API.

    Returns:
        Number of currently executing CLI calls.
    """
    return _global_active_count


class CLITracker:
    """
    Tracks CLI calls and integrates with the event system.
    
    Usage:
        tracker = CLITracker(agent="Generator", event_bus=event_bus)
        async with tracker.track_call(prompt) as call:
            response = await cli.execute(prompt)
            call.complete(response)
    """
    
    def __init__(
        self,
        agent: str = "unknown",
        working_dir: Optional[str] = None,
        event_bus: Optional[Any] = None,  # EventBus type
        store: Optional[CLICallStore] = None,
    ):
        """
        Initialize tracker.
        
        Args:
            agent: Name of the agent making calls
            working_dir: Working directory for file operations
            event_bus: Optional event bus for publishing events
            store: Optional custom store (uses global by default)
        """
        self.agent = agent
        self.working_dir = working_dir
        self.event_bus = event_bus
        self.store = store or get_cli_store()
        self.logger = logger.bind(component="cli_tracker", agent=agent)
    
    def track_call(self, prompt: str) -> "TrackedCall":
        """
        Create a tracked call context manager.
        
        Args:
            prompt: The prompt being sent
            
        Returns:
            TrackedCall context manager
        """
        return TrackedCall(
            tracker=self,
            prompt=prompt,
        )
    
    async def record_call(
        self,
        prompt: str,
        response: str,
        success: bool,
        latency_ms: int,
        error: Optional[str] = None,
        files_modified: Optional[list[str]] = None,
    ) -> CLICall:
        """
        Record a completed CLI call.
        
        Args:
            prompt: The prompt sent
            response: The response received
            success: Whether the call succeeded
            latency_ms: Call latency in milliseconds
            error: Error message if failed
            files_modified: List of files that were modified
            
        Returns:
            The recorded CLICall
        """
        call = CLICall(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            agent=self.agent,
            prompt=prompt,
            prompt_preview=prompt[:200] if prompt else "",
            response=response,
            response_preview=response[:500] if response else "",
            tokens_in=CLICall.estimate_tokens(prompt),
            tokens_out=CLICall.estimate_tokens(response),
            latency_ms=latency_ms,
            success=success,
            error=error,
            files_modified=files_modified or [],
            working_dir=self.working_dir,
        )
        
        await self.store.record(call)
        
        # Publish event if event bus available
        if self.event_bus:
            await self._publish_event(call)
        
        return call
    
    async def _publish_event(self, call: CLICall) -> None:
        """Publish CLI call event to event bus."""
        from ..mind.event_bus import Event, EventType
        
        try:
            event = Event(
                type=EventType.SYSTEM_EVENT if call.success else EventType.SYSTEM_ERROR,
                source=f"CLITracker:{self.agent}",
                success=call.success,
                data={
                    "event_subtype": "CLI_CALL_COMPLETE",
                    "call_id": call.id,
                    "agent": call.agent,
                    "tokens_in": call.tokens_in,
                    "tokens_out": call.tokens_out,
                    "latency_ms": call.latency_ms,
                    "files_modified": call.files_modified,
                },
                error_message=call.error,
            )
            await self.event_bus.publish(event)
        except Exception as e:
            self.logger.warning("event_publish_failed", error=str(e))


class TrackedCall:
    """
    Context manager for tracking a CLI call.
    
    Automatically records timing and handles completion.
    """
    
    def __init__(self, tracker: CLITracker, prompt: str):
        self.tracker = tracker
        self.prompt = prompt
        self.start_time: Optional[datetime] = None
        self.response: str = ""
        self.success: bool = False
        self.error: Optional[str] = None
        self.files_modified: list[str] = []
    
    async def __aenter__(self) -> "TrackedCall":
        self.start_time = datetime.now()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.start_time:
            latency_ms = int((datetime.now() - self.start_time).total_seconds() * 1000)
            await self.tracker.record_call(
                prompt=self.prompt,
                response=self.response,
                success=self.success,
                latency_ms=latency_ms,
                error=self.error,
                files_modified=self.files_modified,
            )
    
    def complete(
        self,
        response: str,
        success: bool = True,
        error: Optional[str] = None,
        files_modified: Optional[list[str]] = None,
    ) -> None:
        """
        Mark the call as complete.
        
        Args:
            response: The response received
            success: Whether successful
            error: Error message if failed
            files_modified: Files that were modified
        """
        self.response = response
        self.success = success
        self.error = error
        self.files_modified = files_modified or []