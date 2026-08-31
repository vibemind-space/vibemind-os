"""
Temporal Memory System (PHASE 7)

Implements temporal context and sequence learning:

1. Temporal Tagging:
   - All memories tagged with precise timestamps
   - Relative time tracking (how long ago)
   - Time-of-day and day-of-week patterns

2. Temporal Decay:
   - Memory strength fades with time
   - Importance modulates decay rate
   - Repeated access strengthens memories

3. Temporal Sequence Learning:
   - Learn what typically follows what
   - Transition probabilities between events
   - Temporal prediction (what's next?)

4. Temporal Context Retrieval:
   - Find memories from specific time periods
   - Time-based similarity (temporal proximity)
   - Recent vs distant memory retrieval

5. Temporal Patterns:
   - Daily rhythms and routines
   - Weekly patterns
   - Time-conditioned behaviors

Based on neuroscience research:
- Time cells in hippocampus (Eichenbaum, 2014)
- Temporal context model (Howard & Kahana, 2002)
- Sequential memory in recurrent networks
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict


@dataclass
class TemporalContext:
    """
    Temporal context for a memory or event
    """
    timestamp: datetime
    time_of_day: str  # 'morning', 'afternoon', 'evening', 'night'
    day_of_week: str  # 'monday', 'tuesday', etc.
    relative_time: str  # 'just_now', 'recent', 'hours_ago', 'days_ago', 'weeks_ago'

    # Temporal relationships
    previous_event: Optional[str] = None
    time_since_previous: Optional[float] = None  # Seconds

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'time_of_day': self.time_of_day,
            'day_of_week': self.day_of_week,
            'relative_time': self.relative_time,
            'previous_event': self.previous_event,
            'time_since_previous': self.time_since_previous
        }


@dataclass
class TemporalSequence:
    """
    A learned temporal sequence
    """
    events: List[str]  # Sequence of event types
    timestamps: List[datetime]  # When each event occurred
    support: int = 1  # How many times this sequence was observed
    avg_duration: float = 0.0  # Average time for sequence
    confidence: float = 0.0  # Confidence in sequence (0-1)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'events': self.events,
            'timestamps': [t.isoformat() for t in self.timestamps],
            'support': self.support,
            'avg_duration': self.avg_duration,
            'confidence': self.confidence
        }


class TemporalMemory:
    """
    Temporal memory system that tracks when events happen

    Key features:
    - Temporal tagging of all events
    - Time-based memory decay
    - Sequence learning
    - Temporal pattern detection
    """

    def __init__(
        self,
        decay_rate: float = 0.1,  # How fast memories decay per day
        sequence_window: int = 5,  # Max events in a learned sequence
        temporal_horizon: int = 7,  # Days to keep in active temporal context
        min_sequence_support: int = 2  # Min occurrences to recognize sequence
    ):
        """
        Initialize temporal memory system

        Args:
            decay_rate: Memory strength decay per day (0-1)
            sequence_window: Maximum length of learned sequences
            temporal_horizon: Days to keep in active context
            min_sequence_support: Min times sequence must occur
        """
        self.decay_rate = decay_rate
        self.sequence_window = sequence_window
        self.temporal_horizon = temporal_horizon
        min_sequence_support = min_sequence_support

        # Event history (temporal stream)
        self.event_stream: Deque[Tuple[str, datetime]] = deque(maxlen=100)

        # Learned sequences
        self.sequences: Dict[str, TemporalSequence] = {}

        # Temporal transitions (Markov chain)
        self.transition_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.transition_times: Dict[str, List[float]] = defaultdict(list)

        # Temporal patterns
        self.time_of_day_patterns: Dict[str, Dict[str, int]] = {
            'morning': defaultdict(int),
            'afternoon': defaultdict(int),
            'evening': defaultdict(int),
            'night': defaultdict(int)
        }

        self.day_of_week_patterns: Dict[str, Dict[str, int]] = {
            day: defaultdict(int) for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        }

        # Statistics
        self.total_events = 0
        self.sequences_learned = 0

    def add_event(
        self,
        event_type: str,
        timestamp: Optional[datetime] = None
    ) -> TemporalContext:
        """
        Add an event to temporal memory

        Args:
            event_type: Type of event (task type, decision, etc.)
            timestamp: When it happened (default: now)

        Returns:
            TemporalContext for this event
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Create temporal context
        context = self._create_temporal_context(event_type, timestamp)

        # Add to event stream
        self.event_stream.append((event_type, timestamp))

        # Update patterns
        self._update_patterns(event_type, context)

        # Update transitions if there's a previous event
        if len(self.event_stream) >= 2:
            prev_event, prev_time = self.event_stream[-2]
            self.transition_counts[prev_event][event_type] += 1

            time_diff = (timestamp - prev_time).total_seconds()
            self.transition_times[f"{prev_event}->{event_type}"].append(time_diff)

        # Learn sequences
        self._learn_sequences()

        self.total_events += 1

        return context

    def _create_temporal_context(
        self,
        event_type: str,
        timestamp: datetime
    ) -> TemporalContext:
        """Create temporal context for an event"""
        # Time of day
        hour = timestamp.hour
        if 5 <= hour < 12:
            time_of_day = 'morning'
        elif 12 <= hour < 17:
            time_of_day = 'afternoon'
        elif 17 <= hour < 21:
            time_of_day = 'evening'
        else:
            time_of_day = 'night'

        # Day of week
        day_of_week = timestamp.strftime('%A').lower()

        # Relative time
        now = datetime.now()
        diff = (now - timestamp).total_seconds()

        if diff < 60:
            relative_time = 'just_now'
        elif diff < 3600:
            relative_time = 'recent'
        elif diff < 86400:
            relative_time = 'hours_ago'
        elif diff < 604800:
            relative_time = 'days_ago'
        else:
            relative_time = 'weeks_ago'

        # Previous event
        previous_event = None
        time_since_previous = None
        if len(self.event_stream) > 0:
            prev_event, prev_time = self.event_stream[-1]
            previous_event = prev_event
            time_since_previous = (timestamp - prev_time).total_seconds()

        return TemporalContext(
            timestamp=timestamp,
            time_of_day=time_of_day,
            day_of_week=day_of_week,
            relative_time=relative_time,
            previous_event=previous_event,
            time_since_previous=time_since_previous
        )

    def _update_patterns(
        self,
        event_type: str,
        context: TemporalContext
    ):
        """Update temporal patterns"""
        # Time of day patterns
        self.time_of_day_patterns[context.time_of_day][event_type] += 1

        # Day of week patterns
        self.day_of_week_patterns[context.day_of_week][event_type] += 1

    def _learn_sequences(self):
        """Learn temporal sequences from event stream"""
        if len(self.event_stream) < 2:
            return

        # Extract recent sequences of varying lengths
        for length in range(2, min(self.sequence_window + 1, len(self.event_stream) + 1)):
            # Get last N events
            recent = list(self.event_stream)[-length:]
            events = [e[0] for e in recent]
            timestamps = [e[1] for e in recent]

            # Create sequence key
            seq_key = "->".join(events)

            # Update or create sequence
            if seq_key in self.sequences:
                seq = self.sequences[seq_key]
                seq.support += 1

                # Update average duration
                duration = (timestamps[-1] - timestamps[0]).total_seconds()
                seq.avg_duration = (seq.avg_duration * (seq.support - 1) + duration) / seq.support

                # Update confidence (higher support = higher confidence)
                seq.confidence = min(1.0, seq.support / 10.0)
            else:
                # New sequence
                duration = (timestamps[-1] - timestamps[0]).total_seconds()
                self.sequences[seq_key] = TemporalSequence(
                    events=events,
                    timestamps=timestamps,
                    support=1,
                    avg_duration=duration,
                    confidence=0.1
                )
                self.sequences_learned += 1

    def predict_next_event(
        self,
        current_event: str,
        top_k: int = 3
    ) -> List[Tuple[str, float]]:
        """
        Predict what event is likely to follow

        Args:
            current_event: Current event type
            top_k: Number of predictions to return

        Returns:
            List of (event_type, probability) tuples
        """
        if current_event not in self.transition_counts:
            return []

        # Get transition counts
        transitions = self.transition_counts[current_event]

        # Calculate probabilities
        total = sum(transitions.values())
        probs = [(event, count / total) for event, count in transitions.items()]

        # Sort by probability
        probs.sort(key=lambda x: x[1], reverse=True)

        return probs[:top_k]

    def get_memory_strength(
        self,
        timestamp: datetime,
        importance: float = 0.5,
        retrieval_count: int = 0
    ) -> float:
        """
        Calculate memory strength based on time and usage

        Args:
            timestamp: When memory was created
            importance: Memory importance (0-1)
            retrieval_count: How many times accessed

        Returns:
            Memory strength (0-1)
        """
        # Time-based decay
        now = datetime.now()
        days_ago = (now - timestamp).total_seconds() / 86400.0

        # Exponential decay modulated by importance
        # More important memories decay slower
        effective_decay = self.decay_rate * (1.0 - importance * 0.5)
        time_factor = np.exp(-effective_decay * days_ago)

        # Retrieval strengthens memory (spaced repetition effect)
        retrieval_boost = min(0.3, retrieval_count * 0.05)

        # Combined strength
        strength = min(1.0, time_factor + retrieval_boost)

        return strength

    def get_temporal_context_similarity(
        self,
        context1: TemporalContext,
        context2: TemporalContext
    ) -> float:
        """
        Calculate similarity between two temporal contexts

        Args:
            context1: First temporal context
            context2: Second temporal context

        Returns:
            Similarity score (0-1)
        """
        similarity = 0.0

        # Same time of day
        if context1.time_of_day == context2.time_of_day:
            similarity += 0.3

        # Same day of week
        if context1.day_of_week == context2.day_of_week:
            similarity += 0.2

        # Temporal proximity (events close in time are similar)
        time_diff = abs((context1.timestamp - context2.timestamp).total_seconds())
        proximity_score = np.exp(-time_diff / 86400.0)  # Decay over days
        similarity += 0.5 * proximity_score

        return min(1.0, similarity)

    def get_recent_events(
        self,
        hours: int = 24,
        event_type: Optional[str] = None
    ) -> List[Tuple[str, datetime]]:
        """
        Get recent events within time window

        Args:
            hours: How many hours back to look
            event_type: Optional filter by event type

        Returns:
            List of (event_type, timestamp) tuples
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        recent = [
            (e, t) for e, t in self.event_stream
            if t >= cutoff and (event_type is None or e == event_type)
        ]

        return recent

    def get_temporal_patterns(
        self,
        time_of_day: Optional[str] = None,
        day_of_week: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Get event patterns for specific temporal context

        Args:
            time_of_day: Filter by time of day
            day_of_week: Filter by day of week

        Returns:
            Dictionary of event_type -> count
        """
        patterns = defaultdict(int)

        if time_of_day and time_of_day in self.time_of_day_patterns:
            for event, count in self.time_of_day_patterns[time_of_day].items():
                patterns[event] += count

        if day_of_week and day_of_week in self.day_of_week_patterns:
            for event, count in self.day_of_week_patterns[day_of_week].items():
                patterns[event] += count

        return dict(patterns)

    def get_statistics(self) -> Dict:
        """Get temporal memory statistics"""
        # Most common transitions
        top_transitions = []
        for from_event, to_events in self.transition_counts.items():
            for to_event, count in to_events.items():
                top_transitions.append((f"{from_event}->{to_event}", count))
        top_transitions.sort(key=lambda x: x[1], reverse=True)

        return {
            'total_events': self.total_events,
            'unique_event_types': len(set(e for e, _ in self.event_stream)),
            'sequences_learned': self.sequences_learned,
            'top_transitions': top_transitions[:5],
            'event_stream_size': len(self.event_stream),
            'time_of_day_distribution': {
                tod: sum(counts.values())
                for tod, counts in self.time_of_day_patterns.items()
            },
            'day_of_week_distribution': {
                dow: sum(counts.values())
                for dow, counts in self.day_of_week_patterns.items()
            }
        }

    def __repr__(self):
        return (
            f"TemporalMemory("
            f"events={self.total_events}, "
            f"sequences={self.sequences_learned}, "
            f"unique_types={len(set(e for e, _ in self.event_stream))})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("TEMPORAL MEMORY SYSTEM (PHASE 7)")
    print("=" * 70)
    print()
    print("This module implements temporal memory and sequence learning:")
    print("  - Temporal tagging of all events")
    print("  - Time-based memory decay")
    print("  - Temporal sequence learning")
    print("  - Temporal pattern detection")
    print("  - Next-event prediction")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_temporal_memory.py")
    print()
    print("=" * 70)
