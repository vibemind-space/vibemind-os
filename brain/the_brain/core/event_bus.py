"""
Event Bus (PHASE 7: P7.99)

Lightweight in-process event bus for inter-module communication within the brain.

Features:
1. Publish/subscribe pattern for decoupled module communication
2. Typed events with priority levels
3. Async-compatible event dispatch
4. Event history with configurable retention
5. Wildcard subscriptions (e.g., 'memory.*')
6. Thread-safe operation
"""

import time
import logging
import threading
from typing import Dict, Any, Optional, List, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from datetime import datetime

logger = logging.getLogger('brain.event_bus')


class EventPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class BrainEvent:
    """A brain event carrying data between modules."""
    topic: str
    data: Dict[str, Any]
    source: str  # Module that emitted the event
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"evt_{int(time.time()*1000)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'topic': self.topic,
            'source': self.source,
            'priority': self.priority.name,
            'timestamp': self.timestamp,
            'data': self.data,
        }


# Type alias for event handler callbacks
EventHandler = Callable[[BrainEvent], None]


class EventBus:
    """
    Central event bus for brain inter-module communication.

    Modules can publish events and subscribe to topics.
    Supports exact match and wildcard (*) subscriptions.
    """

    def __init__(self, max_history: int = 500):
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._history: deque = deque(maxlen=max_history)
        self._lock = threading.Lock()
        self._event_counts: Dict[str, int] = {}
        self._total_events = 0
        self._total_dispatched = 0
        self._error_count = 0
        self._started_at = time.time()

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """
        Subscribe to a topic.

        Args:
            topic: Event topic (e.g., 'memory.store', 'neuromod.*', '*')
            handler: Callback function receiving BrainEvent
        """
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(handler)
        logger.debug(f"Subscribed to '{topic}': {handler.__name__ if hasattr(handler, '__name__') else str(handler)}")

    def unsubscribe(self, topic: str, handler: EventHandler) -> bool:
        """
        Unsubscribe from a topic.

        Returns:
            True if handler was found and removed
        """
        with self._lock:
            if topic in self._subscribers:
                try:
                    self._subscribers[topic].remove(handler)
                    return True
                except ValueError:
                    return False
        return False

    def publish(self, event: BrainEvent) -> int:
        """
        Publish an event to all matching subscribers.

        Args:
            event: The BrainEvent to publish

        Returns:
            Number of handlers that received the event
        """
        handlers = self._get_matching_handlers(event.topic)

        # Sort by priority (CRITICAL first)
        # Note: handlers don't have priority, but events do - we dispatch all matching

        dispatched = 0
        for handler in handlers:
            try:
                handler(event)
                dispatched += 1
            except Exception as e:
                self._error_count += 1
                logger.error(f"Event handler error for '{event.topic}': {e}")

        # Record in history
        with self._lock:
            self._history.append(event)
            self._event_counts[event.topic] = self._event_counts.get(event.topic, 0) + 1
            self._total_events += 1
            self._total_dispatched += dispatched

        return dispatched

    def emit(self, topic: str, data: Dict[str, Any], source: str = "unknown",
             priority: EventPriority = EventPriority.NORMAL) -> int:
        """
        Convenience method to create and publish an event in one call.

        Args:
            topic: Event topic
            data: Event data dict
            source: Source module name
            priority: Event priority

        Returns:
            Number of handlers dispatched
        """
        event = BrainEvent(
            topic=topic,
            data=data,
            source=source,
            priority=priority,
        )
        return self.publish(event)

    def _get_matching_handlers(self, topic: str) -> List[EventHandler]:
        """Get all handlers matching a topic, including wildcards."""
        handlers = []
        with self._lock:
            # Exact match
            if topic in self._subscribers:
                handlers.extend(self._subscribers[topic])

            # Wildcard match: 'memory.*' matches 'memory.store', 'memory.recall'
            topic_parts = topic.split('.')
            for sub_topic, sub_handlers in self._subscribers.items():
                if sub_topic == topic:
                    continue  # Already added
                if '*' in sub_topic:
                    # Check wildcard pattern
                    sub_parts = sub_topic.split('.')
                    if self._matches_wildcard(topic_parts, sub_parts):
                        handlers.extend(sub_handlers)

        return handlers

    @staticmethod
    def _matches_wildcard(topic_parts: List[str], pattern_parts: List[str]) -> bool:
        """Check if topic matches a wildcard pattern."""
        if len(pattern_parts) == 1 and pattern_parts[0] == '*':
            return True  # Global wildcard matches everything

        if len(pattern_parts) != len(topic_parts):
            return False

        for tp, pp in zip(topic_parts, pattern_parts):
            if pp == '*':
                continue
            if tp != pp:
                return False
        return True

    def get_history(self, topic: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get recent event history, optionally filtered by topic."""
        with self._lock:
            events = list(self._history)

        if topic:
            events = [e for e in events if e.topic == topic or e.topic.startswith(topic.rstrip('*'))]

        return [e.to_dict() for e in events[-limit:]]

    def get_statistics(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        with self._lock:
            subscriber_count = sum(len(handlers) for handlers in self._subscribers.values())
            topic_count = len(self._subscribers)
            top_topics = sorted(self._event_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            'total_events': self._total_events,
            'total_dispatched': self._total_dispatched,
            'error_count': self._error_count,
            'subscriber_count': subscriber_count,
            'topic_count': topic_count,
            'history_size': len(self._history),
            'uptime_seconds': round(time.time() - self._started_at, 1),
            'top_topics': [{'topic': t, 'count': c} for t, c in top_topics],
        }

    def get_subscribers(self) -> Dict[str, int]:
        """Get subscriber counts per topic."""
        with self._lock:
            return {topic: len(handlers) for topic, handlers in self._subscribers.items()}

    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._history.clear()

    def reset(self) -> None:
        """Reset all subscribers and history."""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()
            self._event_counts.clear()
            self._total_events = 0
            self._total_dispatched = 0
            self._error_count = 0


# Module-level singleton for global brain event bus
_global_event_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus(max_history: int = 500) -> EventBus:
    """Get or create the global event bus singleton."""
    global _global_event_bus
    if _global_event_bus is None:
        with _bus_lock:
            if _global_event_bus is None:
                _global_event_bus = EventBus(max_history=max_history)
    return _global_event_bus


# Common event topics
class BrainTopics:
    """Standard event topics for brain modules."""
    # Memory events
    MEMORY_STORE = "memory.store"
    MEMORY_RECALL = "memory.recall"
    MEMORY_CONSOLIDATE = "memory.consolidate"

    # Prediction events
    PREDICT_START = "predict.start"
    PREDICT_COMPLETE = "predict.complete"
    PREDICT_ERROR = "predict.error"

    # Feedback events
    FEEDBACK_RECEIVED = "feedback.received"
    FEEDBACK_PROPAGATED = "feedback.propagated"

    # Cognitive loop events
    LOOP_PHASE_ENTER = "loop.phase.enter"
    LOOP_PHASE_EXIT = "loop.phase.exit"
    LOOP_ITERATION = "loop.iteration"
    LOOP_RECONSIDER = "loop.reconsider"

    # Neuromodulation events
    NEUROMOD_UPDATE = "neuromod.update"
    NEUROMOD_THRESHOLD = "neuromod.threshold"

    # Emotional events
    EMOTION_APPRAISAL = "emotion.appraisal"
    EMOTION_SHIFT = "emotion.shift"

    # Goal events
    GOAL_CREATED = "goal.created"
    GOAL_COMPLETED = "goal.completed"
    GOAL_FAILED = "goal.failed"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_SNAPSHOT = "system.snapshot"
    SYSTEM_RESTORE = "system.restore"

    # Frequency events
    FREQUENCY_CHANGE = "frequency.change"

    # Health events
    HEALTH_CHECK = "health.check"
    HEALTH_DEGRADED = "health.degraded"
