"""
Proactive Communication (V2 Phase 4: P4.55-57)

StatusUpdater: Reports proactively about ongoing actions, completions, and issues.
ExplanationSystem: Wraps ExplanationGenerator for decision explanation.
SuggestionEngine: Generates proactive suggestions from pattern recognition.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Status Updater (P4.55) ──────────────────────────────────────────────

class StatusVerbosity(Enum):
    """How verbose status updates should be."""
    SILENT = 'silent'        # No proactive updates
    IMPORTANT = 'important'  # Only significant events
    ALL = 'all'              # Everything, including routine updates


@dataclass
class StatusUpdate:
    """A single status update message."""
    category: str           # 'action_started', 'action_completed', 'issue_detected', 'info'
    message: str
    importance: float       # 0.0 = trivial, 1.0 = critical
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class StatusUpdater:
    """
    Proactively reports status updates (P4.55).

    Reports about:
    - Running actions: "Analyzing build logs..."
    - Completed tasks: "Build fix deployed successfully."
    - Detected issues: "Warning: Disk usage at 85%."

    Verbosity configurable: silent | important | all
    """

    def __init__(
        self,
        verbosity: StatusVerbosity = StatusVerbosity.IMPORTANT,
        importance_threshold: float = 0.5,
        max_history: int = 100,
    ):
        self.verbosity = verbosity
        self.importance_threshold = importance_threshold
        self.max_history = max_history

        self._history: List[StatusUpdate] = []
        self._pending: List[StatusUpdate] = []
        self._total_updates = 0
        self._suppressed_count = 0

    def report_action_started(self, action: str, importance: float = 0.3, **metadata) -> Optional[StatusUpdate]:
        """Report that an action has started."""
        update = StatusUpdate(
            category='action_started',
            message=f"Working on: {action}",
            importance=importance,
            metadata=metadata,
        )
        return self._submit(update)

    def report_action_completed(self, action: str, success: bool = True,
                                importance: float = 0.5, **metadata) -> Optional[StatusUpdate]:
        """Report that an action has completed."""
        status_word = "completed successfully" if success else "failed"
        update = StatusUpdate(
            category='action_completed',
            message=f"{action} {status_word}.",
            importance=importance,
            metadata={'success': success, **metadata},
        )
        return self._submit(update)

    def report_issue(self, issue: str, severity: float = 0.7, **metadata) -> Optional[StatusUpdate]:
        """Report a detected issue."""
        if severity > 0.8:
            prefix = "Critical"
        elif severity > 0.5:
            prefix = "Warning"
        else:
            prefix = "Notice"

        update = StatusUpdate(
            category='issue_detected',
            message=f"{prefix}: {issue}",
            importance=severity,
            metadata=metadata,
        )
        return self._submit(update)

    def report_info(self, message: str, importance: float = 0.2, **metadata) -> Optional[StatusUpdate]:
        """Report informational status."""
        update = StatusUpdate(
            category='info',
            message=message,
            importance=importance,
            metadata=metadata,
        )
        return self._submit(update)

    def _submit(self, update: StatusUpdate) -> Optional[StatusUpdate]:
        """Submit an update, respecting verbosity settings."""
        self._total_updates += 1

        if self.verbosity == StatusVerbosity.SILENT:
            self._suppressed_count += 1
            return None

        if self.verbosity == StatusVerbosity.IMPORTANT:
            if update.importance < self.importance_threshold:
                self._suppressed_count += 1
                return None

        # Accept the update
        self._pending.append(update)
        self._history.append(update)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

        return update

    def get_pending(self) -> List[StatusUpdate]:
        """Get and clear pending updates."""
        pending = list(self._pending)
        self._pending.clear()
        return pending

    def get_recent(self, count: int = 10) -> List[Dict]:
        """Get recent updates as dicts."""
        recent = self._history[-count:] if self._history else []
        return [
            {
                'category': u.category,
                'message': u.message,
                'importance': round(u.importance, 2),
                'timestamp': u.timestamp,
                'metadata': u.metadata,
            }
            for u in recent
        ]

    def get_state(self) -> Dict[str, Any]:
        return {
            'verbosity': self.verbosity.value,
            'importance_threshold': self.importance_threshold,
            'total_updates': self._total_updates,
            'suppressed_count': self._suppressed_count,
            'pending_count': len(self._pending),
            'history_count': len(self._history),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'StatusUpdater':
        """Create from YAML config."""
        su = config.get('status_updater', {})
        verb_str = su.get('verbosity', 'important')
        try:
            verbosity = StatusVerbosity(verb_str)
        except ValueError:
            verbosity = StatusVerbosity.IMPORTANT
        return cls(
            verbosity=verbosity,
            importance_threshold=su.get('importance_threshold', 0.5),
            max_history=su.get('max_history', 100),
        )


# ─── Explanation System (P4.56) ──────────────────────────────────────────

class ExplanationSystem:
    """
    Explains the brain's decisions in natural language (P4.56).

    Wraps the existing ExplanationGenerator (core/explanation_generator.py)
    and adds conversational formatting. Can explain:
    - Why a particular decision was made
    - What alternatives were considered
    - What past experience influenced the choice
    """

    def __init__(
        self,
        explanation_generator: Optional[Any] = None,
        max_reasoning_steps: int = 5,
        include_alternatives: bool = True,
        include_memory_influence: bool = True,
    ):
        self._generator = explanation_generator
        self.max_reasoning_steps = max_reasoning_steps
        self.include_alternatives = include_alternatives
        self.include_memory_influence = include_memory_influence
        self._total_explanations = 0

    def explain_decision(
        self,
        task_description: str,
        decision: Optional[str] = None,
        confidence: float = 0.5,
        reasoning_steps: Optional[List] = None,
        alternatives: Optional[List[Dict]] = None,
        memory_influence: Optional[Dict] = None,
        loop_context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Generate a structured explanation of a decision.

        Returns dict with:
        - summary: One-line explanation
        - reasoning: List of reasoning step descriptions
        - alternatives: Why alternatives were not chosen
        - memory_influence: How past experience shaped the decision
        - confidence_note: Confidence assessment
        """
        self._total_explanations += 1

        # Try using ExplanationGenerator if available
        generator_output = None
        if self._generator and loop_context:
            try:
                if hasattr(self._generator, 'generate_explanation'):
                    generator_output = self._generator.generate_explanation(loop_context)
                elif hasattr(self._generator, 'explain'):
                    generator_output = self._generator.explain(loop_context)
            except Exception as e:
                logger.debug(f"ExplanationGenerator failed: {e}")

        # Build explanation
        result = {
            'summary': '',
            'reasoning': [],
            'alternatives': [],
            'memory_influence': None,
            'confidence_note': '',
        }

        # Summary
        if decision:
            result['summary'] = f"I chose to {decision} for the task: {task_description[:80]}."
        else:
            result['summary'] = f"I processed the task: {task_description[:80]}."

        # Reasoning steps
        steps = []
        if generator_output and isinstance(generator_output, dict):
            raw_steps = generator_output.get('reasoning_steps', [])
            for s in raw_steps[:self.max_reasoning_steps]:
                if isinstance(s, dict):
                    steps.append(s.get('description', str(s)))
                else:
                    steps.append(str(s))
        elif reasoning_steps:
            steps = [str(s) for s in reasoning_steps[:self.max_reasoning_steps]]
        result['reasoning'] = steps

        # Alternatives
        if self.include_alternatives and alternatives:
            alt_explanations = []
            for alt in alternatives[:3]:
                name = alt.get('name', alt.get('decision', 'unknown'))
                reason = alt.get('rejection_reason', 'lower confidence')
                alt_explanations.append(f"{name} (rejected: {reason})")
            result['alternatives'] = alt_explanations

        # Memory influence
        if self.include_memory_influence and memory_influence:
            similar = memory_influence.get('similar_tasks', [])
            if similar:
                top = similar[0]
                task_entry = top[0] if isinstance(top, (list, tuple)) else top
                if isinstance(task_entry, dict):
                    past_task = task_entry.get('task', 'unknown')[:60]
                    past_outcome = task_entry.get('outcome', 'unknown')
                    result['memory_influence'] = (
                        f"Similar past task '{past_task}' had outcome: {past_outcome}. "
                        f"This influenced the current decision."
                    )

        # Confidence note
        if confidence > 0.8:
            result['confidence_note'] = "High confidence in this decision."
        elif confidence > 0.5:
            result['confidence_note'] = "Moderate confidence. The approach seems reasonable."
        elif confidence > 0.3:
            result['confidence_note'] = "Low confidence. This decision may need review."
        else:
            result['confidence_note'] = "Very low confidence. I'd recommend human oversight here."

        return result

    def format_explanation(self, explanation: Dict[str, Any]) -> str:
        """Format a structured explanation as natural language text."""
        parts = [explanation.get('summary', '')]

        reasoning = explanation.get('reasoning', [])
        if reasoning:
            parts.append("My reasoning:")
            for i, step in enumerate(reasoning, 1):
                parts.append(f"  {i}. {step}")

        alternatives = explanation.get('alternatives', [])
        if alternatives:
            parts.append(f"I also considered: {'; '.join(alternatives)}.")

        mem = explanation.get('memory_influence')
        if mem:
            parts.append(mem)

        note = explanation.get('confidence_note', '')
        if note:
            parts.append(note)

        return '\n'.join(parts)

    def get_state(self) -> Dict[str, Any]:
        return {
            'total_explanations': self._total_explanations,
            'has_generator': self._generator is not None,
            'max_reasoning_steps': self.max_reasoning_steps,
            'include_alternatives': self.include_alternatives,
            'include_memory_influence': self.include_memory_influence,
        }


# ─── Suggestion Engine (P4.57) ──────────────────────────────────────────

@dataclass
class Suggestion:
    """A proactive suggestion from pattern recognition."""
    source: str           # 'pattern', 'prediction', 'anomaly', 'memory'
    message: str
    confidence: float     # 0.0 - 1.0
    actionable: bool      # Can the brain act on this automatically?
    action_hint: Optional[str] = None  # What action to take
    evidence: Optional[str] = None     # Supporting evidence
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class SuggestionEngine:
    """
    Generates proactive suggestions from pattern recognition (P4.57).

    Sources:
    - Pattern detection: recurring error patterns, timing correlations
    - Predictive coding: expected events based on recent trends
    - Memory: lessons from past successes/failures

    Only suggests high-confidence (> threshold) items. Designed to be
    helpful without being annoying.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        max_suggestions_per_tick: int = 3,
        cooldown_seconds: float = 300.0,  # 5 min between same-type suggestions
        max_history: int = 50,
    ):
        self.confidence_threshold = confidence_threshold
        self.max_suggestions_per_tick = max_suggestions_per_tick
        self.cooldown_seconds = cooldown_seconds
        self.max_history = max_history

        self._history: List[Suggestion] = []
        self._pending: List[Suggestion] = []
        self._last_suggestion_time: Dict[str, float] = {}  # source → timestamp
        self._total_generated = 0
        self._total_suppressed = 0

    def check_for_suggestions(
        self,
        prediction_errors: Optional[Dict] = None,
        error_patterns: Optional[List[Dict]] = None,
        memory_context: Optional[Dict] = None,
        health_data: Optional[Dict] = None,
        recent_tasks: Optional[List[Dict]] = None,
    ) -> List[Suggestion]:
        """
        Check all sources for potential suggestions.

        Called periodically (e.g., every cognitive loop tick).
        Returns list of new suggestions above the confidence threshold.
        """
        candidates: List[Suggestion] = []

        # 1. Prediction error patterns
        if prediction_errors:
            candidates.extend(self._check_prediction_errors(prediction_errors))

        # 2. Recurring error patterns
        if error_patterns:
            candidates.extend(self._check_error_patterns(error_patterns))

        # 3. Memory-based suggestions
        if memory_context:
            candidates.extend(self._check_memory_patterns(memory_context))

        # 4. Health-based suggestions
        if health_data:
            candidates.extend(self._check_health(health_data))

        # 5. Task outcome patterns
        if recent_tasks:
            candidates.extend(self._check_task_patterns(recent_tasks))

        # Filter by confidence threshold and cooldown
        now = time.time()
        accepted = []
        for s in candidates:
            if s.confidence < self.confidence_threshold:
                self._total_suppressed += 1
                continue

            # Check cooldown
            key = f"{s.source}:{s.message[:30]}"
            last_time = self._last_suggestion_time.get(key, 0)
            if now - last_time < self.cooldown_seconds:
                self._total_suppressed += 1
                continue

            accepted.append(s)
            self._last_suggestion_time[key] = now

            if len(accepted) >= self.max_suggestions_per_tick:
                break

        # Record
        for s in accepted:
            self._total_generated += 1
            self._pending.append(s)
            self._history.append(s)

        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

        return accepted

    def _check_prediction_errors(self, pe: Dict) -> List[Suggestion]:
        """Analyze prediction errors for actionable patterns."""
        suggestions = []
        for domain, error in pe.items():
            if not isinstance(error, (int, float)):
                continue
            if error > 0.7:
                suggestions.append(Suggestion(
                    source='prediction',
                    message=f"High prediction error in '{domain}' ({error:.2f}). "
                            f"The model may need recalibration for this domain.",
                    confidence=min(1.0, error),
                    actionable=True,
                    action_hint=f"recalibrate_{domain}",
                    evidence=f"PE={error:.2f} exceeds threshold 0.7",
                ))
        return suggestions

    def _check_error_patterns(self, patterns: List[Dict]) -> List[Suggestion]:
        """Check for recurring error patterns."""
        suggestions = []
        for pattern in patterns[:5]:
            count = pattern.get('count', 0)
            description = pattern.get('description', pattern.get('pattern', 'unknown'))
            period = pattern.get('period', 'recently')

            if count >= 3:
                confidence = min(1.0, 0.5 + count * 0.1)
                suggestions.append(Suggestion(
                    source='pattern',
                    message=f"Recurring pattern: '{description}' has occurred {count} times {period}.",
                    confidence=confidence,
                    actionable=False,
                    evidence=f"{count} occurrences detected",
                ))
        return suggestions

    def _check_memory_patterns(self, memory_ctx: Dict) -> List[Suggestion]:
        """Suggest based on memory patterns."""
        suggestions = []
        wm = memory_ctx.get('working_memory', {})
        recent = wm.get('recent_tasks', [])

        # Check for repeated failures in a domain
        if recent:
            failure_domains: Dict[str, int] = {}
            for task in recent:
                if task.get('outcome') == 'failure':
                    domain = task.get('task_type', task.get('domain', 'general'))
                    failure_domains[domain] = failure_domains.get(domain, 0) + 1

            for domain, count in failure_domains.items():
                if count >= 2:
                    suggestions.append(Suggestion(
                        source='memory',
                        message=f"Multiple recent failures in '{domain}' ({count} failures). "
                                f"Consider reviewing the approach for this task type.",
                        confidence=min(1.0, 0.6 + count * 0.1),
                        actionable=False,
                        evidence=f"{count} failures in recent memory",
                    ))

        return suggestions

    def _check_health(self, health_data: Dict) -> List[Suggestion]:
        """Check health data for actionable suggestions."""
        suggestions = []

        # Check resource warnings
        for resource in ('cpu', 'memory', 'disk'):
            usage = health_data.get(f'{resource}_usage', health_data.get(resource))
            if isinstance(usage, (int, float)) and usage > 80:
                suggestions.append(Suggestion(
                    source='anomaly',
                    message=f"{resource.upper()} usage at {usage:.0f}%. Consider investigating.",
                    confidence=0.8 if usage > 90 else 0.7,
                    actionable=resource == 'disk',
                    action_hint=f"cleanup_{resource}" if resource == 'disk' else None,
                    evidence=f"{resource}={usage:.0f}%",
                ))

        return suggestions

    def _check_task_patterns(self, tasks: List[Dict]) -> List[Suggestion]:
        """Analyze recent task outcomes for patterns."""
        suggestions = []
        if len(tasks) < 3:
            return suggestions

        # Check for declining success rate
        recent_3 = tasks[-3:]
        successes = sum(1 for t in recent_3 if t.get('outcome') == 'success')
        if successes == 0:
            suggestions.append(Suggestion(
                source='pattern',
                message="Last 3 tasks all failed. The system may need attention or a different approach.",
                confidence=0.8,
                actionable=False,
                evidence="0/3 recent tasks succeeded",
            ))

        return suggestions

    def get_pending(self) -> List[Suggestion]:
        """Get and clear pending suggestions."""
        pending = list(self._pending)
        self._pending.clear()
        return pending

    def get_recent(self, count: int = 10) -> List[Dict]:
        """Get recent suggestions as dicts."""
        recent = self._history[-count:] if self._history else []
        return [
            {
                'source': s.source,
                'message': s.message,
                'confidence': round(s.confidence, 2),
                'actionable': s.actionable,
                'action_hint': s.action_hint,
                'timestamp': s.timestamp,
            }
            for s in recent
        ]

    def get_state(self) -> Dict[str, Any]:
        return {
            'confidence_threshold': self.confidence_threshold,
            'total_generated': self._total_generated,
            'total_suppressed': self._total_suppressed,
            'pending_count': len(self._pending),
            'history_count': len(self._history),
            'cooldown_seconds': self.cooldown_seconds,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'SuggestionEngine':
        """Create from YAML config."""
        se = config.get('suggestion_engine', {})
        return cls(
            confidence_threshold=se.get('confidence_threshold', 0.7),
            max_suggestions_per_tick=se.get('max_suggestions_per_tick', 3),
            cooldown_seconds=se.get('cooldown_seconds', 300.0),
            max_history=se.get('max_history', 50),
        )
