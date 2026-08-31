"""
Resilience System (V2 Phase 7: P7.86-92)

Seven resilience subsystems that make Tahlamus robust against failures,
adversarial inputs, uncertainty, and resource constraints:

1. GracefulDegradationV2 (P7.86):
   Configurable fallback chains so that when a subsystem fails,
   the brain can degrade gracefully to an alternative path.

2. SelfHealing (P7.87):
   Detects and repairs internal problems: memory corruption signals,
   stuck-loop detection, gate weight inconsistency auto-correction.

3. AdversarialResilience (P7.88):
   Protection from manipulative inputs: prompt injection detection,
   implausible sensor data filtering, rate limiting.

4. UncertaintyHandling (P7.89):
   Explicit uncertainty communication when confidence is low or
   multiple equally viable options exist.

5. ContextSwitching (P7.90):
   Clean task switching with working memory save/restore on interrupt.

6. LongRunningTaskManager (P7.91):
   Checkpoint-based progress tracking for tasks spanning hours or days.

7. ResourceAwareness (P7.92):
   Token budget tracking, CPU/RAM awareness, and task decomposition
   decisions based on current resource state.
"""

import logging
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger('brain.resilience')


# ─── Graceful Degradation V2 (P7.86) ────────────────────────────────────────

DEFAULT_FALLBACK_CHAINS: Dict[str, List[str]] = {
    'automation_ui': ['shell_commands'],
    'coding_engine': ['llm_direct'],
    'requirements_engine': ['logic_ctm'],
    'llm': ['keyword_routing'],
}


class GracefulDegradationV2:
    """
    Fallback chains for each subsystem (P7.86).

    When a primary system is unavailable, the degradation manager
    provides the next available fallback from a configurable chain.
    This ensures the brain can continue operating (at reduced
    capability) rather than failing completely.
    """

    def __init__(
        self,
        fallback_chains: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Args:
            fallback_chains: Mapping from system_name to ordered list
                             of fallback system names.
        """
        self.fallback_chains: Dict[str, List[str]] = dict(
            fallback_chains or DEFAULT_FALLBACK_CHAINS
        )

        # System availability tracking
        self._system_status: Dict[str, bool] = {}
        # Currently active fallbacks: primary → active fallback
        self._active_fallbacks: Dict[str, str] = {}
        self._fallback_activations: int = 0
        self._total_queries: int = 0

    def record_system_status(self, system_name: str, is_available: bool):
        """
        Record the availability status of a system.

        When a system becomes unavailable, its fallback chain is
        activated. When it becomes available again, active fallbacks
        for it are cleared.
        """
        prev = self._system_status.get(system_name, True)
        self._system_status[system_name] = is_available

        if prev and not is_available:
            logger.warning(
                f"System '{system_name}' became unavailable, "
                f"fallback chain will be used"
            )
        elif not prev and is_available:
            # System recovered — clear active fallback
            if system_name in self._active_fallbacks:
                logger.info(
                    f"System '{system_name}' recovered, "
                    f"clearing fallback '{self._active_fallbacks[system_name]}'"
                )
                del self._active_fallbacks[system_name]

    def get_fallback(self, system_name: str) -> Optional[str]:
        """
        Get the next available fallback for a system.

        Walks the fallback chain for *system_name* and returns the
        first system that is marked available (or not yet tracked,
        which defaults to available).  Returns None if no fallback
        is available.
        """
        self._total_queries += 1

        chain = self.fallback_chains.get(system_name, [])
        for candidate in chain:
            # A system not yet recorded is assumed available
            if self._system_status.get(candidate, True):
                self._active_fallbacks[system_name] = candidate
                self._fallback_activations += 1
                logger.info(
                    f"Fallback for '{system_name}' → '{candidate}'"
                )
                return candidate

        return None

    def get_active_fallbacks(self) -> Dict[str, str]:
        """Return dict of currently active fallbacks (primary → fallback)."""
        return dict(self._active_fallbacks)

    def get_state(self) -> Dict[str, Any]:
        """Get degradation state for dashboard."""
        return {
            'name': 'GracefulDegradationV2',
            'fallback_chains': self.fallback_chains,
            'system_status': dict(self._system_status),
            'active_fallbacks': dict(self._active_fallbacks),
            'total_queries': self._total_queries,
            'fallback_activations': self._fallback_activations,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'GracefulDegradationV2':
        """Create GracefulDegradationV2 from YAML config dict."""
        s = config.get('graceful_degradation', {})
        chains = s.get('fallback_chains', None)
        return cls(fallback_chains=chains)


# ─── Self Healing (P7.87) ────────────────────────────────────────────────────

@dataclass
class HealingAction:
    """A recommended self-healing action."""
    action_type: str       # 'rebuild_memory', 'restart_loop', 'renormalize_gates'
    description: str
    severity: str = 'warning'   # 'info', 'warning', 'critical'
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action_type': self.action_type,
            'description': self.description,
            'severity': self.severity,
            'timestamp': self.timestamp,
        }


class SelfHealing:
    """
    Detects and repairs own problems (P7.87).

    Three capabilities:
    1. Memory corruption detection → rebuild signal
    2. Stuck loop detection (same state > timeout)
    3. Gate weight inconsistency → softmax re-normalization
    """

    def __init__(
        self,
        stuck_timeout: float = 300.0,
        gate_tolerance: float = 1e-4,
        max_healing_history: int = 100,
    ):
        """
        Args:
            stuck_timeout: Seconds in the same state before flagging stuck.
            gate_tolerance: Max deviation from 1.0 for gate sum before
                            triggering re-normalization.
            max_healing_history: Max healing actions to keep in history.
        """
        self.stuck_timeout = stuck_timeout
        self.gate_tolerance = gate_tolerance

        # State tracking for stuck detection
        self._current_state: Optional[str] = None
        self._state_entered_at: float = 0.0
        self._state_history: deque = deque(maxlen=200)

        # Healing action history
        self._healing_history: deque = deque(maxlen=max_healing_history)
        self._total_heals: int = 0
        self._total_gate_corrections: int = 0
        self._total_stuck_detections: int = 0

    def record_state(self, state_name: str, timestamp: Optional[float] = None):
        """
        Record the current cognitive/agent state for stuck detection.

        If the state changes, reset the timer.  If the same state
        persists beyond stuck_timeout, is_stuck() returns True.
        """
        now = timestamp or time.time()

        if state_name != self._current_state:
            self._state_history.append({
                'state': self._current_state,
                'entered': self._state_entered_at,
                'exited': now,
            })
            self._current_state = state_name
            self._state_entered_at = now
        # else: same state — timer keeps running

    def is_stuck(self) -> bool:
        """
        Check whether the system is stuck in the same state.

        Returns True if the current state has been active longer
        than stuck_timeout seconds.
        """
        if self._current_state is None:
            return False

        elapsed = time.time() - self._state_entered_at
        if elapsed > self.stuck_timeout:
            self._total_stuck_detections += 1
            return True
        return False

    def check_gate_consistency(self, gates) -> list:
        """
        Check and correct gate weights so they sum to 1.0.

        Accepts ndarray or list.  If the sum deviates from 1.0 by
        more than gate_tolerance, applies softmax re-normalization.

        Returns:
            Corrected gate weights as a Python list.
        """
        # Convert to plain list
        if hasattr(gates, 'tolist'):
            weights = gates.tolist()
        else:
            weights = list(gates)

        total = sum(weights)
        if abs(total - 1.0) <= self.gate_tolerance:
            return weights

        # Need correction — apply softmax
        logger.warning(
            f"Gate sum {total:.6f} deviates from 1.0 "
            f"(tolerance {self.gate_tolerance}), re-normalizing"
        )
        corrected = self._softmax(weights)

        self._total_gate_corrections += 1
        self._healing_history.append(HealingAction(
            action_type='renormalize_gates',
            description=f"Gate sum was {total:.6f}, applied softmax",
            severity='warning',
        ))
        self._total_heals += 1

        return corrected

    def get_healing_actions(self) -> List[Dict[str, Any]]:
        """
        Get list of recommended healing actions based on current state.

        Checks for:
        - Stuck loops
        - Recent gate corrections (suggesting upstream instability)
        """
        actions: List[HealingAction] = []

        # Check stuck
        if self.is_stuck():
            actions.append(HealingAction(
                action_type='restart_loop',
                description=(
                    f"System stuck in state '{self._current_state}' "
                    f"for {time.time() - self._state_entered_at:.0f}s "
                    f"(threshold: {self.stuck_timeout:.0f}s)"
                ),
                severity='critical',
            ))

        # Check for high rate of gate corrections (instability)
        recent_corrections = sum(
            1 for h in self._healing_history
            if h.action_type == 'renormalize_gates'
            and time.time() - h.timestamp < 60.0
        )
        if recent_corrections >= 5:
            actions.append(HealingAction(
                action_type='rebuild_memory',
                description=(
                    f"{recent_corrections} gate corrections in last 60s — "
                    f"possible memory corruption or unstable routing"
                ),
                severity='critical',
            ))

        return [a.to_dict() for a in actions]

    @staticmethod
    def _softmax(weights: List[float]) -> List[float]:
        """Inline softmax normalization (no numpy dependency)."""
        max_w = max(weights) if weights else 0.0
        exp_w = [math.exp(x - max_w) for x in weights]
        total = sum(exp_w)
        if total == 0:
            n = len(weights)
            return [1.0 / n] * n if n > 0 else []
        return [x / total for x in exp_w]

    def get_state(self) -> Dict[str, Any]:
        """Get self-healing state for dashboard."""
        return {
            'name': 'SelfHealing',
            'current_state': self._current_state,
            'state_duration_s': (
                round(time.time() - self._state_entered_at, 1)
                if self._current_state else 0
            ),
            'is_stuck': self.is_stuck() if self._current_state else False,
            'stuck_timeout': self.stuck_timeout,
            'gate_tolerance': self.gate_tolerance,
            'total_heals': self._total_heals,
            'total_gate_corrections': self._total_gate_corrections,
            'total_stuck_detections': self._total_stuck_detections,
            'recent_healing_actions': [
                h.to_dict() for h in list(self._healing_history)[-10:]
            ],
        }


# ─── Adversarial Resilience (P7.88) ─────────────────────────────────────────

@dataclass
class InputCheckResult:
    """Result of an adversarial input check."""
    safe: bool
    risk_level: float = 0.0     # 0.0 (safe) to 1.0 (dangerous)
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'safe': self.safe,
            'risk_level': round(self.risk_level, 3),
            'flags': self.flags,
        }


# Common prompt injection patterns (case-insensitive)
_INJECTION_PATTERNS = [
    r'ignore\s+(all\s+)?previous\s+instructions',
    r'ignore\s+(all\s+)?above\s+instructions',
    r'disregard\s+(all\s+)?prior\s+(instructions|rules)',
    r'you\s+are\s+now\s+(a|an)\s+',
    r'forget\s+(everything|all)\s+you\s+(know|were\s+told)',
    r'new\s+instructions?\s*:',
    r'system\s*:\s*you\s+are',
    r'override\s+(safety|security|rules)',
    r'jailbreak',
    r'pretend\s+you\s+are',
    r'act\s+as\s+(if\s+)?you\s+(are|were)',
    r'do\s+not\s+follow\s+(any\s+)?(safety|content)\s+(rules|guidelines)',
    r'<\s*(system|admin|root)\s*>',
    r'\bDAN\b.*\bmode\b',
]


class AdversarialResilience:
    """
    Protection from manipulative inputs (P7.88).

    Three defenses:
    1. Prompt injection detection via regex pattern matching
    2. Implausible sensor data filtering (value range checks)
    3. Rate limiting for external input sources
    """

    def __init__(
        self,
        extra_patterns: Optional[List[str]] = None,
        default_rate_limit: int = 10,
    ):
        """
        Args:
            extra_patterns: Additional regex patterns to detect injections.
            default_rate_limit: Default max requests per minute per source.
        """
        self.default_rate_limit = default_rate_limit

        patterns = list(_INJECTION_PATTERNS)
        if extra_patterns:
            patterns.extend(extra_patterns)
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in patterns
        ]

        # Rate limiting: source → deque of timestamps
        self._rate_windows: Dict[str, deque] = {}

        # Statistics
        self._total_checks: int = 0
        self._total_flagged: int = 0
        self._total_sensor_rejects: int = 0
        self._total_rate_limited: int = 0

    def check_input(self, text: str) -> InputCheckResult:
        """
        Check text input for adversarial patterns.

        Returns:
            InputCheckResult with safe=False if injection detected.
        """
        self._total_checks += 1
        flags: List[str] = []
        risk = 0.0

        for pattern in self._compiled_patterns:
            if pattern.search(text):
                flags.append(f"injection_pattern: {pattern.pattern}")
                risk = max(risk, 0.8)

        if flags:
            self._total_flagged += 1
            risk = min(1.0, risk + 0.1 * (len(flags) - 1))
            logger.warning(
                f"Adversarial input detected ({len(flags)} flags): "
                f"{flags[0]}"
            )

        return InputCheckResult(
            safe=len(flags) == 0,
            risk_level=risk,
            flags=flags,
        )

    def validate_sensor_data(
        self,
        metric: str,
        value: float,
        min_val: float = 0.0,
        max_val: float = 100.0,
    ) -> Tuple[bool, float]:
        """
        Validate a sensor reading against plausible bounds.

        Args:
            metric: Name of the metric (for logging).
            value: The sensor reading.
            min_val: Minimum plausible value.
            max_val: Maximum plausible value.

        Returns:
            (valid, clamped_value):
            - valid: True if value was within bounds.
            - clamped_value: The original value if valid, otherwise clamped.
        """
        if min_val <= value <= max_val:
            return (True, value)

        self._total_sensor_rejects += 1
        clamped = max(min_val, min(max_val, value))
        logger.warning(
            f"Implausible sensor data for '{metric}': {value} "
            f"(bounds [{min_val}, {max_val}]), clamped to {clamped}"
        )
        return (False, clamped)

    def check_rate_limit(
        self,
        source: str,
        max_per_minute: int = 0,
    ) -> bool:
        """
        Check whether an input source exceeds its rate limit.

        Args:
            source: Identifier for the input source.
            max_per_minute: Max requests per minute.
                            Uses default_rate_limit if 0.

        Returns:
            True if the request is allowed, False if rate-limited.
        """
        limit = max_per_minute if max_per_minute > 0 else self.default_rate_limit
        now = time.time()
        cutoff = now - 60.0

        if source not in self._rate_windows:
            self._rate_windows[source] = deque(maxlen=1000)

        window = self._rate_windows[source]
        # Prune old entries
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= limit:
            self._total_rate_limited += 1
            logger.warning(
                f"Rate limit exceeded for source '{source}': "
                f"{len(window)}/{limit} per minute"
            )
            return False

        window.append(now)
        return True

    def get_state(self) -> Dict[str, Any]:
        """Get adversarial resilience state for dashboard."""
        return {
            'name': 'AdversarialResilience',
            'total_checks': self._total_checks,
            'total_flagged': self._total_flagged,
            'total_sensor_rejects': self._total_sensor_rejects,
            'total_rate_limited': self._total_rate_limited,
            'pattern_count': len(self._compiled_patterns),
            'active_sources': len(self._rate_windows),
            'default_rate_limit': self.default_rate_limit,
        }


# ─── Uncertainty Handling (P7.89) ────────────────────────────────────────────

@dataclass
class UncertaintyAssessment:
    """Result of an uncertainty assessment."""
    should_communicate: bool
    message: str
    action: str    # 'proceed', 'ask_user', 'escalate'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'should_communicate': self.should_communicate,
            'message': self.message,
            'action': self.action,
        }


class UncertaintyHandling:
    """
    Explicit uncertainty communication (P7.89).

    "I'm not sure" is a valid and valuable answer.

    When confidence is low (< 0.3), the system communicates
    uncertainty explicitly.  When multiple equally viable options
    exist, it asks the user to decide.
    """

    def __init__(
        self,
        low_confidence_threshold: float = 0.3,
        ambiguity_threshold: int = 2,
    ):
        """
        Args:
            low_confidence_threshold: Below this, flag uncertainty.
            ambiguity_threshold: If num_alternatives >= this, ask user.
        """
        self.low_confidence_threshold = low_confidence_threshold
        self.ambiguity_threshold = ambiguity_threshold

        self._total_assessments: int = 0
        self._total_uncertain: int = 0
        self._total_ask_user: int = 0
        self._total_escalated: int = 0

    def assess_confidence(
        self,
        confidence: float,
        num_alternatives: int = 1,
    ) -> UncertaintyAssessment:
        """
        Assess whether the current confidence level warrants
        explicit uncertainty communication.

        Args:
            confidence: Model confidence (0-1).
            num_alternatives: Number of equally viable alternatives.

        Returns:
            UncertaintyAssessment with action recommendation.
        """
        self._total_assessments += 1

        # Very low confidence: escalate
        if confidence < self.low_confidence_threshold / 2:
            self._total_escalated += 1
            return UncertaintyAssessment(
                should_communicate=True,
                message=(
                    f"Confidence is very low ({confidence:.2f}). "
                    f"Unable to make a reliable decision."
                ),
                action='escalate',
            )

        # Low confidence: communicate uncertainty
        if confidence < self.low_confidence_threshold:
            self._total_uncertain += 1
            return UncertaintyAssessment(
                should_communicate=True,
                message=(
                    f"Confidence is low ({confidence:.2f}). "
                    f"The result may not be reliable."
                ),
                action='proceed',
            )

        # Multiple equivalent options: ask user
        if num_alternatives >= self.ambiguity_threshold:
            self._total_ask_user += 1
            return UncertaintyAssessment(
                should_communicate=True,
                message=(
                    f"Found {num_alternatives} equally viable options. "
                    f"User input recommended to choose."
                ),
                action='ask_user',
            )

        # Confident enough — proceed silently
        return UncertaintyAssessment(
            should_communicate=False,
            message='',
            action='proceed',
        )

    def get_state(self) -> Dict[str, Any]:
        """Get uncertainty handling state for dashboard."""
        return {
            'name': 'UncertaintyHandling',
            'low_confidence_threshold': self.low_confidence_threshold,
            'ambiguity_threshold': self.ambiguity_threshold,
            'total_assessments': self._total_assessments,
            'total_uncertain': self._total_uncertain,
            'total_ask_user': self._total_ask_user,
            'total_escalated': self._total_escalated,
        }


# ─── Context Switching (P7.90) ───────────────────────────────────────────────

class ContextSwitching:
    """
    Clean task switching with working memory save/restore (P7.90).

    When the agent is interrupted by a higher-priority task, the
    current working memory context is saved so it can be seamlessly
    restored when the agent returns to the original task.
    """

    def __init__(self, max_saved_contexts: int = 20):
        """
        Args:
            max_saved_contexts: Maximum number of saved contexts before
                                the oldest is evicted.
        """
        self.max_saved_contexts = max_saved_contexts

        # task_id → {context_data, saved_at}
        self._contexts: Dict[str, Dict[str, Any]] = {}
        # Insertion order tracking for eviction
        self._order: deque = deque(maxlen=max_saved_contexts * 2)

        self._total_saves: int = 0
        self._total_restores: int = 0

    def save_context(self, task_id: str, context_data: Dict):
        """
        Save working memory context for a task.

        If max_saved_contexts is reached, the oldest context is evicted.
        """
        # Evict if at capacity and this is a new task_id
        if (
            task_id not in self._contexts
            and len(self._contexts) >= self.max_saved_contexts
        ):
            self._evict_oldest()

        self._contexts[task_id] = {
            'context_data': context_data,
            'saved_at': time.time(),
        }
        # Track insertion order (append to right)
        self._order.append(task_id)
        self._total_saves += 1

        logger.info(f"Context saved for task '{task_id}'")

    def restore_context(self, task_id: str) -> Optional[Dict]:
        """
        Restore a previously saved context.

        Returns the context_data dict, or None if not found.
        Does NOT remove the context (call clear_context to remove).
        """
        entry = self._contexts.get(task_id)
        if entry is None:
            logger.debug(f"No saved context for task '{task_id}'")
            return None

        self._total_restores += 1
        logger.info(f"Context restored for task '{task_id}'")
        return entry['context_data']

    def list_saved_contexts(self) -> List[str]:
        """Return list of task IDs with saved contexts."""
        return list(self._contexts.keys())

    def clear_context(self, task_id: str):
        """Remove a saved context."""
        if task_id in self._contexts:
            del self._contexts[task_id]
            logger.info(f"Context cleared for task '{task_id}'")

    def _evict_oldest(self):
        """Evict the oldest saved context to make room."""
        # Walk the order deque to find the oldest still-existing entry
        while self._order:
            oldest = self._order.popleft()
            if oldest in self._contexts:
                del self._contexts[oldest]
                logger.debug(f"Evicted oldest context: '{oldest}'")
                return

    def get_state(self) -> Dict[str, Any]:
        """Get context switching state for dashboard."""
        return {
            'name': 'ContextSwitching',
            'max_saved_contexts': self.max_saved_contexts,
            'active_contexts': len(self._contexts),
            'saved_task_ids': list(self._contexts.keys()),
            'total_saves': self._total_saves,
            'total_restores': self._total_restores,
        }


# ─── Long Running Task Manager (P7.91) ──────────────────────────────────────

class TaskStatus(Enum):
    """Status of a long-running task."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class LongRunningTask:
    """Internal tracking state for a long-running task."""
    task_id: str
    description: str
    estimated_duration_hours: Optional[float]
    status: TaskStatus = TaskStatus.RUNNING
    progress_pct: float = 0.0
    started_at: float = 0.0
    last_checkpoint_at: float = 0.0
    completed_at: Optional[float] = None
    success: Optional[bool] = None
    state_data: Optional[Dict[str, Any]] = None
    checkpoint_count: int = 0

    def __post_init__(self):
        if self.started_at == 0.0:
            self.started_at = time.time()
        if self.last_checkpoint_at == 0.0:
            self.last_checkpoint_at = self.started_at

    def elapsed_hours(self) -> float:
        end = self.completed_at or time.time()
        return (end - self.started_at) / 3600.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'description': self.description,
            'status': self.status.value,
            'progress_pct': round(self.progress_pct, 1),
            'estimated_duration_hours': self.estimated_duration_hours,
            'elapsed_hours': round(self.elapsed_hours(), 3),
            'started_at': self.started_at,
            'last_checkpoint_at': self.last_checkpoint_at,
            'completed_at': self.completed_at,
            'success': self.success,
            'checkpoint_count': self.checkpoint_count,
            'has_state_data': self.state_data is not None,
        }


class LongRunningTaskManager:
    """
    Checkpoint-based tracking for long-running tasks (P7.91).

    Tasks that span hours or days need periodic progress checkpoints
    so they can be monitored, paused, and resumed.
    """

    def __init__(self, max_tracked_tasks: int = 50):
        """
        Args:
            max_tracked_tasks: Maximum number of tasks to track simultaneously.
        """
        self.max_tracked_tasks = max_tracked_tasks
        self._tasks: Dict[str, LongRunningTask] = {}
        self._total_started: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0

    def start_task(
        self,
        task_id: str,
        description: str,
        estimated_duration_hours: Optional[float] = None,
    ):
        """
        Start tracking a new long-running task.

        If max_tracked_tasks is reached, the oldest completed task is
        removed to make room.
        """
        # Evict completed tasks if at capacity
        if len(self._tasks) >= self.max_tracked_tasks:
            self._evict_completed()

        if len(self._tasks) >= self.max_tracked_tasks:
            logger.warning(
                f"Cannot track task '{task_id}': "
                f"at capacity ({self.max_tracked_tasks})"
            )
            return

        self._tasks[task_id] = LongRunningTask(
            task_id=task_id,
            description=description,
            estimated_duration_hours=estimated_duration_hours,
        )
        self._total_started += 1
        logger.info(
            f"Started tracking task '{task_id}': {description}"
        )

    def checkpoint(
        self,
        task_id: str,
        progress_pct: float,
        state_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Record a checkpoint for a running task.

        Args:
            task_id: Task identifier.
            progress_pct: Progress percentage (0-100).
            state_data: Optional state data for resume capability.
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"Checkpoint for unknown task '{task_id}'")
            return

        task.progress_pct = max(0.0, min(100.0, progress_pct))
        task.last_checkpoint_at = time.time()
        task.checkpoint_count += 1
        if state_data is not None:
            task.state_data = state_data

        logger.debug(
            f"Task '{task_id}' checkpoint: {progress_pct:.1f}% "
            f"(checkpoint #{task.checkpoint_count})"
        )

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a tracked task.

        Returns dict with progress, elapsed time, last checkpoint,
        or None if task not found.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return task.to_dict()

    def get_resumable_tasks(self) -> List[Dict[str, Any]]:
        """
        Get tasks that can be resumed (running or paused with state data).
        """
        resumable = []
        for task in self._tasks.values():
            if (
                task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED)
                and task.state_data is not None
            ):
                resumable.append(task.to_dict())
        return resumable

    def complete_task(self, task_id: str, success: bool):
        """Mark a task as completed (success or failure)."""
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"Complete called for unknown task '{task_id}'")
            return

        task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        task.completed_at = time.time()
        task.success = success
        task.progress_pct = 100.0 if success else task.progress_pct

        if success:
            self._total_completed += 1
        else:
            self._total_failed += 1

        logger.info(
            f"Task '{task_id}' {'completed' if success else 'failed'} "
            f"after {task.elapsed_hours():.2f}h"
        )

    def _evict_completed(self):
        """Remove the oldest completed/failed task to make room."""
        oldest_id = None
        oldest_time = float('inf')

        for tid, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                if task.started_at < oldest_time:
                    oldest_time = task.started_at
                    oldest_id = tid

        if oldest_id:
            del self._tasks[oldest_id]
            logger.debug(f"Evicted completed task '{oldest_id}'")

    def get_state(self) -> Dict[str, Any]:
        """Get task manager state for dashboard."""
        running = sum(
            1 for t in self._tasks.values()
            if t.status == TaskStatus.RUNNING
        )
        return {
            'name': 'LongRunningTaskManager',
            'max_tracked_tasks': self.max_tracked_tasks,
            'active_tasks': len(self._tasks),
            'running_tasks': running,
            'total_started': self._total_started,
            'total_completed': self._total_completed,
            'total_failed': self._total_failed,
            'tasks': {
                tid: t.to_dict() for tid, t in self._tasks.items()
            },
        }


# ─── Resource Awareness (P7.92) ─────────────────────────────────────────────

class ResourceAwareness:
    """
    Knows own resource limits and adapts behavior (P7.92).

    Tracks token budget consumption and CPU/RAM usage to inform
    decisions about task decomposition and concurrency.
    """

    def __init__(
        self,
        tokens_per_minute: int = 1000,
        tokens_per_hour: int = 50000,
        cpu_high_threshold: float = 80.0,
        ram_high_threshold: float = 85.0,
        max_concurrent_base: int = 4,
        history_size: int = 120,
    ):
        """
        Args:
            tokens_per_minute: Token budget per minute.
            tokens_per_hour: Token budget per hour.
            cpu_high_threshold: CPU % above which to reduce concurrency.
            ram_high_threshold: RAM % above which to reduce concurrency.
            max_concurrent_base: Base max concurrent tasks at low load.
            history_size: Number of resource samples to keep.
        """
        self.tokens_per_minute = tokens_per_minute
        self.tokens_per_hour = tokens_per_hour
        self.cpu_high_threshold = cpu_high_threshold
        self.ram_high_threshold = ram_high_threshold
        self.max_concurrent_base = max_concurrent_base

        # Token usage tracking: deque of (timestamp, tokens)
        self._token_history: deque = deque(maxlen=history_size * 60)

        # Resource usage tracking: deque of (timestamp, cpu_pct, ram_pct)
        self._resource_history: deque = deque(maxlen=history_size)

        # Totals
        self._total_tokens_used: int = 0

    def record_token_usage(self, tokens: int):
        """Record token consumption."""
        self._token_history.append((time.time(), tokens))
        self._total_tokens_used += tokens

    def record_resource_usage(self, cpu_pct: float, ram_pct: float):
        """Record a CPU/RAM usage snapshot."""
        self._resource_history.append((time.time(), cpu_pct, ram_pct))

    def _tokens_in_window(self, window_seconds: float) -> int:
        """Sum tokens consumed in the last window_seconds."""
        cutoff = time.time() - window_seconds
        total = 0
        for ts, tok in self._token_history:
            if ts >= cutoff:
                total += tok
        return total

    def get_budget_status(self) -> Dict[str, Any]:
        """
        Get current token budget and resource status.

        Returns:
            Dict with tokens_remaining_minute, tokens_remaining_hour,
            cpu_avg, ram_avg.
        """
        used_minute = self._tokens_in_window(60.0)
        used_hour = self._tokens_in_window(3600.0)

        # Average CPU/RAM over recent samples (last 10)
        recent = list(self._resource_history)[-10:]
        if recent:
            cpu_avg = sum(r[1] for r in recent) / len(recent)
            ram_avg = sum(r[2] for r in recent) / len(recent)
        else:
            cpu_avg = 0.0
            ram_avg = 0.0

        return {
            'tokens_remaining_minute': max(0, self.tokens_per_minute - used_minute),
            'tokens_remaining_hour': max(0, self.tokens_per_hour - used_hour),
            'tokens_used_minute': used_minute,
            'tokens_used_hour': used_hour,
            'cpu_avg': round(cpu_avg, 1),
            'ram_avg': round(ram_avg, 1),
        }

    def should_decompose_task(self, estimated_tokens: int) -> bool:
        """
        Check whether a task should be decomposed into sub-tasks
        because it would exceed the remaining token budget.

        Returns True if the estimated tokens exceed what remains
        in the per-minute budget.
        """
        remaining = max(
            0, self.tokens_per_minute - self._tokens_in_window(60.0)
        )
        return estimated_tokens > remaining

    def get_max_concurrent_tasks(self) -> int:
        """
        Determine how many tasks can run concurrently based on
        current CPU/RAM pressure.

        Returns an integer (>= 1).
        """
        recent = list(self._resource_history)[-5:]
        if not recent:
            return self.max_concurrent_base

        cpu_avg = sum(r[1] for r in recent) / len(recent)
        ram_avg = sum(r[2] for r in recent) / len(recent)

        # Reduce concurrency under high load
        if cpu_avg > self.cpu_high_threshold or ram_avg > self.ram_high_threshold:
            return max(1, self.max_concurrent_base // 2)

        if cpu_avg > self.cpu_high_threshold * 0.75:
            return max(1, self.max_concurrent_base - 1)

        return self.max_concurrent_base

    def get_state(self) -> Dict[str, Any]:
        """Get resource awareness state for dashboard."""
        budget = self.get_budget_status()
        return {
            'name': 'ResourceAwareness',
            'tokens_per_minute': self.tokens_per_minute,
            'tokens_per_hour': self.tokens_per_hour,
            'cpu_high_threshold': self.cpu_high_threshold,
            'ram_high_threshold': self.ram_high_threshold,
            'max_concurrent_base': self.max_concurrent_base,
            'current_max_concurrent': self.get_max_concurrent_tasks(),
            'total_tokens_used': self._total_tokens_used,
            'budget': budget,
            'resource_samples': len(self._resource_history),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'ResourceAwareness':
        """Create ResourceAwareness from YAML config dict."""
        s = config.get('resource_awareness', {})
        return cls(
            tokens_per_minute=s.get('tokens_per_minute', 1000),
            tokens_per_hour=s.get('tokens_per_hour', 50000),
            cpu_high_threshold=s.get('cpu_high_threshold', 80.0),
            ram_high_threshold=s.get('ram_high_threshold', 85.0),
            max_concurrent_base=s.get('max_concurrent_base', 4),
            history_size=s.get('history_size', 120),
        )
