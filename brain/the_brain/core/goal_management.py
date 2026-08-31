"""
Goal Management System (V2 Phase 3: P3.37-40)

Wraps the existing GoalGraph with:

1. GoalHierarchy (P3.37):
   Three-level system: long-term (days), mid-term (hours), short-term (minutes).
   Automatic decomposition from high-level objectives down to actionable tasks.

2. GoalGeneration (P3.38):
   Five sources for new goals:
   (a) Sensor events  (b) Repeated failures  (c) Curiosity/PE
   (d) User requests   (e) Pattern recognition

3. GoalPrioritization (P3.39):
   Dynamic scoring based on urgency, importance, effort, expected reward,
   and neuromodulation (dopamine biases toward risky goals, NE toward urgent).

4. GoalConflictResolution (P3.40):
   Detects resource/temporal/logical conflicts between active goals.
   Proposes resolution via trade-off analysis. Escalates to user when stuck.

Integration:
    AgentLoop calls goal_manager.tick() each cycle.
    Returned GoalTasks are converted to AgentTasks for execution.
"""

import logging
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger('brain.goal_management')


# ─── Goal Time Horizon ─────────────────────────────────────────────────────

class GoalHorizon(Enum):
    """Three-level goal horizon (P3.37)."""
    LONG_TERM = "long_term"       # Days  — e.g. "Deploy project X"
    MID_TERM = "mid_term"         # Hours — e.g. "Implement feature Y"
    SHORT_TERM = "short_term"     # Minutes — e.g. "Fix test Z"


class GoalSource(Enum):
    """Where a goal originated from (P3.38)."""
    SENSOR_EVENT = "sensor_event"       # (a) Build failed, service down
    REPEATED_FAILURE = "repeated_failure"  # (b) 3x same error -> fix root cause
    CURIOSITY = "curiosity"             # (c) High prediction error -> investigate
    USER_REQUEST = "user_request"       # (d) Via /predict or Clawdbot
    PATTERN = "pattern"                 # (e) Recurring temporal patterns
    MOTIVATION = "motivation"           # From motivation drives (P3.34-36)
    DECOMPOSITION = "decomposition"     # Auto-decomposed from parent goal
    INTERNAL = "internal"               # System-generated maintenance


class ConflictType(Enum):
    """Types of goal conflicts (P3.40)."""
    RESOURCE = "resource"         # Both need same resource (e.g. same file)
    TEMPORAL = "temporal"         # Deadline collision
    LOGICAL = "logical"          # Mutually exclusive outcomes
    DEPENDENCY = "dependency"     # Circular or broken dependency chain


class ConflictResolution(Enum):
    """How a conflict was resolved."""
    PRIORITY_OVERRIDE = "priority_override"   # Higher priority wins
    SEQUENTIAL = "sequential"                 # Do one after another
    MERGED = "merged"                         # Combined into single goal
    USER_DECIDED = "user_decided"             # User chose
    ABANDONED = "abandoned"                   # One goal abandoned


# ─── Data Structures ────────────────────────────────────────────────────────

@dataclass
class ManagedGoal:
    """
    Extended goal with management metadata.
    Wraps information beyond what GoalGraph.Goal tracks.
    """
    goal_id: str
    description: str
    horizon: GoalHorizon = GoalHorizon.SHORT_TERM
    source: GoalSource = GoalSource.INTERNAL
    domain: str = "general"

    # Scoring (P3.39)
    urgency: float = 0.5          # 0-1, sensor-driven
    importance: float = 0.5       # 0-1, user=1.0, self=0.3
    estimated_effort: float = 0.5  # 0-1, from experience
    expected_reward: float = 0.5   # 0-1, from meta-learning
    neuro_bias: float = 0.0        # -0.5 to 0.5, from neuromodulation

    # Tracking
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    max_attempts: int = 5
    last_failure_reason: str = ""
    parent_goal_id: Optional[str] = None
    child_goal_ids: List[str] = field(default_factory=list)

    # Status
    active: bool = True
    completed: bool = False
    failed: bool = False

    def composite_score(self) -> float:
        """
        Composite priority score (higher = more important).
        P3.39: urgency * importance / effort * reward + neuro_bias
        """
        eff = max(0.1, self.estimated_effort)  # Avoid division by zero
        score = (self.urgency * 0.35 + self.importance * 0.30) / eff
        score += self.expected_reward * 0.25
        score += self.neuro_bias * 0.10
        # Source bonus: user requests are always top
        if self.source == GoalSource.USER_REQUEST:
            score += 1.0
        # Horizon bonus: short-term gets slight urgency boost
        if self.horizon == GoalHorizon.SHORT_TERM:
            score += 0.1
        # Age bonus: older goals get slight boost to prevent starvation
        age_minutes = (time.time() - self.created_at) / 60.0
        score += min(0.2, age_minutes / 60.0)
        return max(0.0, score)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'goal_id': self.goal_id,
            'description': self.description,
            'horizon': self.horizon.value,
            'source': self.source.value,
            'domain': self.domain,
            'urgency': round(self.urgency, 3),
            'importance': round(self.importance, 3),
            'estimated_effort': round(self.estimated_effort, 3),
            'expected_reward': round(self.expected_reward, 3),
            'neuro_bias': round(self.neuro_bias, 3),
            'composite_score': round(self.composite_score(), 3),
            'active': self.active,
            'completed': self.completed,
            'failed': self.failed,
            'attempts': self.attempts,
            'parent_goal_id': self.parent_goal_id,
            'child_goal_ids': self.child_goal_ids,
            'created_at': self.created_at,
        }


@dataclass
class GoalConflict:
    """A detected conflict between two goals (P3.40)."""
    conflict_id: str
    goal_a_id: str
    goal_b_id: str
    conflict_type: ConflictType
    severity: float = 0.5  # 0-1
    description: str = ""
    resolution: Optional[ConflictResolution] = None
    resolved_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'conflict_id': self.conflict_id,
            'goal_a_id': self.goal_a_id,
            'goal_b_id': self.goal_b_id,
            'conflict_type': self.conflict_type.value,
            'severity': round(self.severity, 3),
            'description': self.description,
            'resolution': self.resolution.value if self.resolution else None,
            'resolved_at': self.resolved_at,
        }


@dataclass
class GoalTask:
    """A task derived from a goal, ready for the AgentLoop."""
    goal_id: str
    description: str
    priority_score: float
    source: GoalSource
    horizon: GoalHorizon
    domain: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'goal_id': self.goal_id,
            'description': self.description,
            'priority_score': round(self.priority_score, 3),
            'source': self.source.value,
            'horizon': self.horizon.value,
            'domain': self.domain,
            'metadata': self.metadata,
        }


# ─── Failure Tracker ────────────────────────────────────────────────────────

class FailureTracker:
    """
    Tracks repeated failures per domain to trigger root-cause goals (P3.38b).
    If the same domain/error pattern fails N times, generates a fix-root-cause goal.
    """

    def __init__(self, threshold: int = 3, window_seconds: float = 3600.0):
        self._threshold = threshold
        self._window = window_seconds
        self._failures: Dict[str, List[Tuple[float, str]]] = defaultdict(list)

    def record_failure(self, domain: str, reason: str = ""):
        """Record a failure in a domain."""
        now = time.time()
        self._failures[domain].append((now, reason))
        # Prune old entries
        cutoff = now - self._window
        self._failures[domain] = [
            (t, r) for t, r in self._failures[domain] if t > cutoff
        ]

    def get_repeated_failures(self) -> List[Tuple[str, int, str]]:
        """
        Get domains with repeated failures above threshold.
        Returns: [(domain, failure_count, last_reason), ...]
        """
        now = time.time()
        cutoff = now - self._window
        results = []
        for domain, entries in self._failures.items():
            recent = [(t, r) for t, r in entries if t > cutoff]
            if len(recent) >= self._threshold:
                last_reason = recent[-1][1] if recent else ""
                results.append((domain, len(recent), last_reason))
        return results

    def clear_domain(self, domain: str):
        """Clear failure tracking for a domain (e.g. after fix)."""
        self._failures.pop(domain, None)

    def get_state(self) -> Dict[str, Any]:
        now = time.time()
        cutoff = now - self._window
        return {
            'tracked_domains': len(self._failures),
            'domains': {
                d: len([t for t, _ in entries if t > cutoff])
                for d, entries in self._failures.items()
            },
            'threshold': self._threshold,
            'window_seconds': self._window,
        }


# ─── Goal Generation (P3.38) ──────────────────────────────────────────────

class GoalGenerator:
    """
    Generates new goals from 5 sources:
    (a) Sensor events (b) Repeated failures (c) Curiosity/PE
    (d) User requests  (e) Pattern recognition
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        curiosity_pe_threshold: float = 0.5,
        max_goals_per_tick: int = 3,
        cooldown_seconds: float = 60.0,
    ):
        self._failure_tracker = FailureTracker(threshold=failure_threshold)
        self._curiosity_pe_threshold = curiosity_pe_threshold
        self._max_per_tick = max_goals_per_tick
        self._cooldown = cooldown_seconds
        self._last_generation: Dict[str, float] = {}  # source -> last_time
        self._generated_count: int = 0

    def generate_from_sensor_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> Optional[ManagedGoal]:
        """
        (a) Generate goal from sensor event.
        e.g. "build failed" -> goal: "Fix build"
        """
        if self._is_on_cooldown("sensor"):
            return None

        # Handle None/missing inputs gracefully
        if not event_type:
            return None
        event_data = event_data or {}

        description = ""
        urgency = 0.5
        domain = event_data.get('domain', 'system')

        if 'error' in event_type.lower() or 'fail' in event_type.lower():
            description = f"Fix: {event_data.get('message', event_type)}"
            urgency = 0.8
        elif 'degradation' in event_type.lower() or 'warning' in event_type.lower():
            description = f"Investigate: {event_data.get('message', event_type)}"
            urgency = 0.6
        elif 'info' in event_type.lower():
            description = f"Note: {event_data.get('message', event_type)}"
            urgency = 0.3
        else:
            description = f"Handle event: {event_type}"
            urgency = 0.4

        if not description:
            return None

        self._record_generation("sensor")
        return self._create_goal(
            description=description[:200],
            horizon=GoalHorizon.SHORT_TERM,
            source=GoalSource.SENSOR_EVENT,
            domain=domain,
            urgency=urgency,
            importance=0.6,
        )

    def generate_from_failures(self) -> List[ManagedGoal]:
        """
        (b) Generate goals from repeated failures.
        3x same domain failing -> "Fix root cause in <domain>"
        """
        if self._is_on_cooldown("failure"):
            return []

        goals = []
        repeated = self._failure_tracker.get_repeated_failures()

        for domain, count, reason in repeated:
            desc = f"Fix root cause: {count}x failures in '{domain}'"
            if reason:
                desc += f" (last: {reason[:80]})"

            goal = self._create_goal(
                description=desc,
                horizon=GoalHorizon.MID_TERM,
                source=GoalSource.REPEATED_FAILURE,
                domain=domain,
                urgency=min(1.0, 0.5 + count * 0.1),
                importance=0.7,
                estimated_effort=0.6,
            )
            goals.append(goal)
            # Clear tracking after generating goal
            self._failure_tracker.clear_domain(domain)

        if goals:
            self._record_generation("failure")
        return goals[:self._max_per_tick]

    def generate_from_curiosity(
        self,
        prediction_errors: Dict[str, float],
    ) -> List[ManagedGoal]:
        """
        (c) Generate goals from high prediction errors.
        High PE in a domain -> "Investigate <domain>"
        """
        if self._is_on_cooldown("curiosity"):
            return []

        goals = []
        for domain, pe in prediction_errors.items():
            if pe >= self._curiosity_pe_threshold:
                goal = self._create_goal(
                    description=f"Investigate high prediction error in '{domain}' (PE={pe:.2f})",
                    horizon=GoalHorizon.SHORT_TERM,
                    source=GoalSource.CURIOSITY,
                    domain=domain,
                    urgency=min(1.0, pe),
                    importance=0.4,
                    expected_reward=min(1.0, pe * 0.8),
                )
                goals.append(goal)

        if goals:
            self._record_generation("curiosity")
        return sorted(goals, key=lambda g: g.urgency, reverse=True)[:self._max_per_tick]

    def generate_from_user_request(
        self,
        description: str,
        metadata: Optional[Dict] = None,
    ) -> ManagedGoal:
        """(d) Generate goal from user request (always accepted)."""
        return self._create_goal(
            description=description,
            horizon=GoalHorizon.MID_TERM,
            source=GoalSource.USER_REQUEST,
            domain=metadata.get('domain', 'user') if metadata else 'user',
            urgency=1.0,
            importance=1.0,
            metadata=metadata,
        )

    def generate_from_pattern(
        self,
        pattern_description: str,
        domain: str = "general",
        urgency: float = 0.4,
    ) -> Optional[ManagedGoal]:
        """
        (e) Generate goal from recognized pattern.
        e.g. "Every Monday at 9 there are merge conflicts" -> "Preventively merge branches"
        """
        if self._is_on_cooldown("pattern"):
            return None

        goal = self._create_goal(
            description=f"Proactive: {pattern_description}",
            horizon=GoalHorizon.MID_TERM,
            source=GoalSource.PATTERN,
            domain=domain,
            urgency=urgency,
            importance=0.5,
            estimated_effort=0.4,
            expected_reward=0.6,
        )
        self._record_generation("pattern")
        return goal

    def record_failure(self, domain: str, reason: str = ""):
        """Record a failure for the failure tracker (P3.38b)."""
        self._failure_tracker.record_failure(domain, reason)

    # ── Internal helpers ────────────────────────────────────────────

    def _create_goal(
        self,
        description: str,
        horizon: GoalHorizon,
        source: GoalSource,
        domain: str = "general",
        urgency: float = 0.5,
        importance: float = 0.5,
        estimated_effort: float = 0.5,
        expected_reward: float = 0.5,
        metadata: Optional[Dict] = None,
    ) -> ManagedGoal:
        self._generated_count += 1
        goal = ManagedGoal(
            goal_id=f"goal_{self._generated_count}_{uuid.uuid4().hex[:6]}",
            description=description,
            horizon=horizon,
            source=source,
            domain=domain,
            urgency=urgency,
            importance=importance,
            estimated_effort=estimated_effort,
            expected_reward=expected_reward,
        )
        return goal

    def _is_on_cooldown(self, source: str) -> bool:
        last = self._last_generation.get(source, 0)
        return (time.time() - last) < self._cooldown

    def _record_generation(self, source: str):
        self._last_generation[source] = time.time()

    def get_state(self) -> Dict[str, Any]:
        return {
            'generated_count': self._generated_count,
            'failure_tracker': self._failure_tracker.get_state(),
            'curiosity_pe_threshold': self._curiosity_pe_threshold,
            'max_per_tick': self._max_per_tick,
            'cooldown_seconds': self._cooldown,
        }


# ─── Goal Prioritizer (P3.39) ──────────────────────────────────────────────

class GoalPrioritizer:
    """
    Dynamic goal prioritization based on multi-factor scoring.

    Factors:
    - Urgency (sensor-driven: error=high, info=low)
    - Importance (user-request=1.0, self-generated=0.3)
    - Effort (estimated from ActionPlanner / experience)
    - Expected Reward (from meta-learning success rates)
    - Neuromodulation: high dopamine -> riskier goals, high NE -> urgent goals
    """

    def __init__(
        self,
        dopamine_risk_weight: float = 0.3,
        norepinephrine_urgency_weight: float = 0.3,
        serotonin_stability_weight: float = 0.2,
    ):
        self._dopamine_weight = dopamine_risk_weight
        self._ne_weight = norepinephrine_urgency_weight
        self._serotonin_weight = serotonin_stability_weight

    def apply_neuromodulation(
        self,
        goals: List[ManagedGoal],
        neuro_levels: Optional[Any] = None,
    ) -> List[ManagedGoal]:
        """
        Apply neuromodulation bias to goal scores.

        High dopamine (>0.6) -> boost goals with high expected_reward (risk-taking)
        High NE (>0.6) -> boost goals with high urgency (focus on urgent)
        High serotonin (>0.6) -> boost goals with low effort (prefer stability)
        """
        if neuro_levels is None:
            return goals

        # Extract levels (handle both object and dict)
        if hasattr(neuro_levels, 'dopamine'):
            dopamine = float(neuro_levels.dopamine)
            norepinephrine = float(neuro_levels.norepinephrine)
            serotonin = float(neuro_levels.serotonin)
        elif isinstance(neuro_levels, dict):
            dopamine = float(neuro_levels.get('dopamine', 0.5))
            norepinephrine = float(neuro_levels.get('norepinephrine', 0.5))
            serotonin = float(neuro_levels.get('serotonin', 0.5))
        else:
            return goals

        for goal in goals:
            bias = 0.0
            # High dopamine -> boost risky/high-reward goals
            if dopamine > 0.6:
                bias += (dopamine - 0.5) * self._dopamine_weight * goal.expected_reward
            elif dopamine < 0.3:
                # Low dopamine -> penalize risky goals (prefer safe)
                bias -= (0.5 - dopamine) * self._dopamine_weight * goal.expected_reward

            # High NE -> boost urgent goals
            if norepinephrine > 0.6:
                bias += (norepinephrine - 0.5) * self._ne_weight * goal.urgency
            elif norepinephrine < 0.3:
                # Low NE -> reduce urgency sensitivity
                bias -= (0.5 - norepinephrine) * self._ne_weight * 0.5

            # High serotonin -> prefer low-effort/stable goals
            if serotonin > 0.6:
                bias += (serotonin - 0.5) * self._serotonin_weight * (1.0 - goal.estimated_effort)

            goal.neuro_bias = max(-0.5, min(0.5, bias))

        return goals

    def rank_goals(self, goals: List[ManagedGoal]) -> List[ManagedGoal]:
        """Rank goals by composite score (highest first)."""
        return sorted(goals, key=lambda g: g.composite_score(), reverse=True)

    def get_top_actionable(
        self,
        goals: List[ManagedGoal],
        max_goals: int = 5,
    ) -> List[ManagedGoal]:
        """Get top N actionable goals (active, not completed/failed)."""
        active = [g for g in goals if g.active and not g.completed and not g.failed]
        ranked = self.rank_goals(active)
        return ranked[:max_goals]


# ─── Goal Conflict Resolution (P3.40) ──────────────────────────────────────

class GoalConflictResolver:
    """
    Detects and resolves conflicts between goals.

    Conflict types:
    - Resource: Both need same domain/resource simultaneously
    - Temporal: Deadline collision (both due soon, can't do both)
    - Logical: Mutually exclusive (e.g. "deploy now" vs "tests not ready")
    - Dependency: Circular or broken chains

    Resolution strategies:
    - Priority override (higher priority wins)
    - Sequential execution (do one after other)
    - Merge (combine into single goal)
    - User escalation (ask user to decide)
    """

    def __init__(
        self,
        resource_conflict_threshold: float = 0.8,
        temporal_conflict_window_minutes: float = 30.0,
        auto_resolve_severity_threshold: float = 0.7,
    ):
        self._resource_threshold = resource_conflict_threshold
        self._temporal_window = temporal_conflict_window_minutes
        self._auto_resolve_threshold = auto_resolve_severity_threshold
        self._conflicts: List[GoalConflict] = []
        self._resolved_count: int = 0
        self._escalated_count: int = 0

    def detect_conflicts(self, goals: List[ManagedGoal]) -> List[GoalConflict]:
        """Detect conflicts among active goals."""
        conflicts = []
        active = [g for g in goals if g.active and not g.completed and not g.failed]

        for i, goal_a in enumerate(active):
            for goal_b in active[i + 1:]:
                conflict = self._check_pair(goal_a, goal_b)
                if conflict:
                    conflicts.append(conflict)

        self._conflicts.extend(conflicts)
        return conflicts

    def _check_pair(self, a: ManagedGoal, b: ManagedGoal) -> Optional[GoalConflict]:
        """Check if two goals conflict."""
        # Resource conflict: same domain, both active
        if a.domain == b.domain and a.domain != "general":
            # Same specific domain -> potential resource conflict
            severity = min(1.0, (a.urgency + b.urgency) / 2.0)
            if severity >= self._resource_threshold * 0.5:
                return GoalConflict(
                    conflict_id=f"conflict_{uuid.uuid4().hex[:6]}",
                    goal_a_id=a.goal_id,
                    goal_b_id=b.goal_id,
                    conflict_type=ConflictType.RESOURCE,
                    severity=severity,
                    description=f"Both goals target domain '{a.domain}'",
                )

        # Logical conflict: detect keywords suggesting mutual exclusion
        a_lower = a.description.lower()
        b_lower = b.description.lower()

        # Simple heuristic: "deploy" vs "test" or "fix" can conflict
        deploy_keywords = {'deploy', 'release', 'push', 'ship'}
        block_keywords = {'fix', 'test', 'debug', 'investigate', 'rollback'}

        a_deploy = any(k in a_lower for k in deploy_keywords)
        b_block = any(k in b_lower for k in block_keywords)
        b_deploy = any(k in b_lower for k in deploy_keywords)
        a_block = any(k in a_lower for k in block_keywords)

        if (a_deploy and b_block) or (b_deploy and a_block):
            return GoalConflict(
                conflict_id=f"conflict_{uuid.uuid4().hex[:6]}",
                goal_a_id=a.goal_id,
                goal_b_id=b.goal_id,
                conflict_type=ConflictType.LOGICAL,
                severity=0.8,
                description=f"Potential deploy/fix conflict: '{a.description[:40]}' vs '{b.description[:40]}'",
            )

        return None

    def resolve_conflict(
        self,
        conflict: GoalConflict,
        goals: Dict[str, ManagedGoal],
    ) -> ConflictResolution:
        """
        Attempt to auto-resolve a conflict.
        Returns the resolution strategy used.
        """
        if conflict.resolution:
            return conflict.resolution  # Already resolved

        goal_a = goals.get(conflict.goal_a_id)
        goal_b = goals.get(conflict.goal_b_id)

        if not goal_a or not goal_b:
            conflict.resolution = ConflictResolution.ABANDONED
            conflict.resolved_at = time.time()
            self._resolved_count += 1
            return ConflictResolution.ABANDONED

        # Severity check: auto-resolve only below threshold
        if conflict.severity > self._auto_resolve_threshold:
            # High severity: needs user decision
            self._escalated_count += 1
            return ConflictResolution.USER_DECIDED

        # Strategy: Higher composite score wins
        score_a = goal_a.composite_score()
        score_b = goal_b.composite_score()

        if abs(score_a - score_b) > 0.2:
            # Clear winner by priority
            loser = goal_b if score_a > score_b else goal_a
            loser.urgency *= 0.5  # Reduce urgency of lower-priority goal
            conflict.resolution = ConflictResolution.PRIORITY_OVERRIDE
        elif conflict.conflict_type == ConflictType.RESOURCE:
            # Same resource: do sequentially
            conflict.resolution = ConflictResolution.SEQUENTIAL
        else:
            # Default: priority override
            conflict.resolution = ConflictResolution.PRIORITY_OVERRIDE

        conflict.resolved_at = time.time()
        self._resolved_count += 1
        return conflict.resolution

    def get_unresolved(self) -> List[GoalConflict]:
        """Get conflicts needing user decision."""
        return [c for c in self._conflicts if c.resolution is None]

    def get_escalated(self) -> List[GoalConflict]:
        """Get conflicts escalated to user."""
        return [
            c for c in self._conflicts
            if c.resolution == ConflictResolution.USER_DECIDED and c.resolved_at is None
        ]

    def get_state(self) -> Dict[str, Any]:
        return {
            'total_conflicts': len(self._conflicts),
            'resolved_count': self._resolved_count,
            'escalated_count': self._escalated_count,
            'unresolved': len(self.get_unresolved()),
            'recent_conflicts': [c.to_dict() for c in self._conflicts[-5:]],
        }


# ─── Goal Hierarchy (P3.37) ───────────────────────────────────────────────

class GoalHierarchy:
    """
    Three-level goal hierarchy with automatic decomposition.

    Long-term (days):  "Deploy project X" - from RE specs
    Mid-term (hours):  "Implement feature Y" - from decomposition
    Short-term (min):  "Fix test Z" - from sensor events
    """

    def __init__(self, max_goals: int = 100):
        self._goals: Dict[str, ManagedGoal] = {}
        self._max_goals = max_goals

        # Indexes by horizon
        self._by_horizon: Dict[GoalHorizon, Set[str]] = {
            GoalHorizon.LONG_TERM: set(),
            GoalHorizon.MID_TERM: set(),
            GoalHorizon.SHORT_TERM: set(),
        }

    def add_goal(self, goal: ManagedGoal) -> bool:
        """Add a goal to the hierarchy. Returns False if at capacity."""
        if len(self._goals) >= self._max_goals:
            # Try to clean up completed/failed goals
            self._cleanup()
            if len(self._goals) >= self._max_goals:
                logger.warning(f"Goal hierarchy full ({self._max_goals})")
                return False

        self._goals[goal.goal_id] = goal
        self._by_horizon[goal.horizon].add(goal.goal_id)

        # Link to parent
        if goal.parent_goal_id and goal.parent_goal_id in self._goals:
            parent = self._goals[goal.parent_goal_id]
            if goal.goal_id not in parent.child_goal_ids:
                parent.child_goal_ids.append(goal.goal_id)

        return True

    def get_goal(self, goal_id: str) -> Optional[ManagedGoal]:
        return self._goals.get(goal_id)

    def get_goals_by_horizon(self, horizon: GoalHorizon) -> List[ManagedGoal]:
        """Get all active goals at a given horizon level."""
        return [
            self._goals[gid] for gid in self._by_horizon[horizon]
            if gid in self._goals and self._goals[gid].active
        ]

    def get_all_active(self) -> List[ManagedGoal]:
        """Get all active goals across all horizons."""
        return [g for g in self._goals.values() if g.active and not g.completed and not g.failed]

    def complete_goal(self, goal_id: str) -> bool:
        """Mark goal as completed. Propagates to parent if all children done."""
        goal = self._goals.get(goal_id)
        if not goal:
            return False

        goal.completed = True
        goal.active = False

        # Check if all siblings are done -> mark parent as completable
        if goal.parent_goal_id and goal.parent_goal_id in self._goals:
            parent = self._goals[goal.parent_goal_id]
            all_children_done = all(
                self._goals[cid].completed
                for cid in parent.child_goal_ids
                if cid in self._goals
            )
            if all_children_done and parent.child_goal_ids:
                # Parent can be auto-completed
                parent.completed = True
                parent.active = False
                logger.info(f"Parent goal auto-completed: {parent.description[:60]}")

        return True

    def fail_goal(self, goal_id: str, reason: str = "") -> bool:
        """Mark goal as failed."""
        goal = self._goals.get(goal_id)
        if not goal:
            return False

        goal.failed = True
        goal.active = False
        goal.last_failure_reason = reason
        goal.attempts += 1

        # If under max attempts, re-activate
        if goal.attempts < goal.max_attempts:
            goal.failed = False
            goal.active = True
            logger.info(f"Goal retrying ({goal.attempts}/{goal.max_attempts}): {goal.description[:60]}")

        return True

    def decompose_goal(
        self,
        parent_id: str,
        sub_descriptions: List[str],
        sub_horizon: GoalHorizon = GoalHorizon.SHORT_TERM,
    ) -> List[ManagedGoal]:
        """
        Decompose a parent goal into sub-goals.
        Returns list of created sub-goals.
        """
        parent = self._goals.get(parent_id)
        if not parent:
            return []

        children = []
        for desc in sub_descriptions:
            child = ManagedGoal(
                goal_id=f"goal_sub_{uuid.uuid4().hex[:6]}",
                description=desc,
                horizon=sub_horizon,
                source=GoalSource.DECOMPOSITION,
                domain=parent.domain,
                urgency=parent.urgency * 0.8,
                importance=parent.importance * 0.9,
                estimated_effort=parent.estimated_effort / max(1, len(sub_descriptions)),
                expected_reward=parent.expected_reward * 0.7,
                parent_goal_id=parent_id,
            )
            if self.add_goal(child):
                children.append(child)

        return children

    def _cleanup(self):
        """Remove completed/failed goals beyond retention."""
        removable = [
            gid for gid, g in self._goals.items()
            if (g.completed or (g.failed and g.attempts >= g.max_attempts))
            and (time.time() - g.created_at) > 3600  # Keep for at least 1 hour
        ]
        for gid in removable[:20]:  # Remove max 20 at a time
            goal = self._goals.pop(gid, None)
            if goal:
                self._by_horizon[goal.horizon].discard(gid)

    def get_state(self) -> Dict[str, Any]:
        active = self.get_all_active()
        return {
            'total_goals': len(self._goals),
            'active_goals': len(active),
            'by_horizon': {
                h.value: len([
                    gid for gid in gids
                    if gid in self._goals and self._goals[gid].active
                ])
                for h, gids in self._by_horizon.items()
            },
            'completed': len([g for g in self._goals.values() if g.completed]),
            'failed': len([g for g in self._goals.values() if g.failed]),
            'top_goals': [g.to_dict() for g in sorted(active, key=lambda g: g.composite_score(), reverse=True)[:5]],
        }


# ─── Goal Manager (orchestrates everything) ──────────────────────────────

class GoalManager:
    """
    Central orchestrator for P3.37-40.

    Composes:
    - GoalHierarchy (P3.37)
    - GoalGenerator (P3.38)
    - GoalPrioritizer (P3.39)
    - GoalConflictResolver (P3.40)

    Called by AgentLoop.tick() to produce GoalTasks.
    """

    def __init__(
        self,
        max_goals: int = 100,
        failure_threshold: int = 3,
        curiosity_pe_threshold: float = 0.5,
        max_goals_per_tick: int = 3,
        generation_cooldown_seconds: float = 60.0,
        dopamine_risk_weight: float = 0.3,
        ne_urgency_weight: float = 0.3,
        serotonin_stability_weight: float = 0.2,
        resource_conflict_threshold: float = 0.8,
        auto_resolve_severity: float = 0.7,
        max_tasks_per_tick: int = 3,
    ):
        self.hierarchy = GoalHierarchy(max_goals=max_goals)
        self.generator = GoalGenerator(
            failure_threshold=failure_threshold,
            curiosity_pe_threshold=curiosity_pe_threshold,
            max_goals_per_tick=max_goals_per_tick,
            cooldown_seconds=generation_cooldown_seconds,
        )
        self.prioritizer = GoalPrioritizer(
            dopamine_risk_weight=dopamine_risk_weight,
            norepinephrine_urgency_weight=ne_urgency_weight,
            serotonin_stability_weight=serotonin_stability_weight,
        )
        self.conflict_resolver = GoalConflictResolver(
            resource_conflict_threshold=resource_conflict_threshold,
            auto_resolve_severity_threshold=auto_resolve_severity,
        )
        self._max_tasks_per_tick = max_tasks_per_tick
        self._total_ticks = 0
        self._total_tasks_generated = 0

    @classmethod
    def from_yaml(cls, config: Dict) -> 'GoalManager':
        """Create from YAML config dict."""
        section = config.get('goal_management', {})
        return cls(
            max_goals=section.get('max_goals', 100),
            failure_threshold=section.get('failure_threshold', 3),
            curiosity_pe_threshold=section.get('curiosity_pe_threshold', 0.5),
            max_goals_per_tick=section.get('max_goals_per_tick', 3),
            generation_cooldown_seconds=section.get('generation_cooldown_seconds', 60.0),
            dopamine_risk_weight=section.get('dopamine_risk_weight', 0.3),
            ne_urgency_weight=section.get('ne_urgency_weight', 0.3),
            serotonin_stability_weight=section.get('serotonin_stability_weight', 0.2),
            resource_conflict_threshold=section.get('resource_conflict_threshold', 0.8),
            auto_resolve_severity=section.get('auto_resolve_severity', 0.7),
            max_tasks_per_tick=section.get('max_tasks_per_tick', 3),
        )

    # ─── Main Tick ─────────────────────────────────────────────────

    def tick(
        self,
        sensor_events: Optional[List[Dict]] = None,
        prediction_errors: Optional[Dict[str, float]] = None,
        neuro_levels: Optional[Any] = None,
    ) -> List[GoalTask]:
        """
        Main tick: generate, prioritize, resolve conflicts, return tasks.

        Called by AgentLoop each cycle.

        Args:
            sensor_events: New sensor events [{type, data}, ...]
            prediction_errors: PE per domain {domain: float}
            neuro_levels: NeuromodulatorLevels (or dict)

        Returns:
            List of GoalTasks ready for execution
        """
        self._total_ticks += 1

        # 1. Generate new goals from various sources
        new_goals = self._generate_goals(sensor_events, prediction_errors)

        # 2. Add to hierarchy
        for goal in new_goals:
            self.hierarchy.add_goal(goal)

        # 3. Apply neuromodulation to all active goals
        active_goals = self.hierarchy.get_all_active()
        if neuro_levels:
            active_goals = self.prioritizer.apply_neuromodulation(active_goals, neuro_levels)

        # 4. Detect and resolve conflicts
        conflicts = self.conflict_resolver.detect_conflicts(active_goals)
        for conflict in conflicts:
            self.conflict_resolver.resolve_conflict(conflict, self.hierarchy._goals)

        # 5. Prioritize and select top goals
        top_goals = self.prioritizer.get_top_actionable(active_goals, self._max_tasks_per_tick)

        # 6. Convert to GoalTasks
        tasks = []
        for goal in top_goals:
            task = GoalTask(
                goal_id=goal.goal_id,
                description=goal.description,
                priority_score=goal.composite_score(),
                source=goal.source,
                horizon=goal.horizon,
                domain=goal.domain,
                metadata={
                    'urgency': goal.urgency,
                    'importance': goal.importance,
                    'effort': goal.estimated_effort,
                    'reward': goal.expected_reward,
                    'neuro_bias': goal.neuro_bias,
                },
            )
            tasks.append(task)
            self._total_tasks_generated += 1

        return tasks

    # ─── Goal Lifecycle ────────────────────────────────────────────

    def submit_user_goal(self, description: str, metadata: Optional[Dict] = None) -> ManagedGoal:
        """Submit a user-initiated goal (highest priority)."""
        goal = self.generator.generate_from_user_request(description, metadata)
        self.hierarchy.add_goal(goal)
        return goal

    def complete_goal(self, goal_id: str):
        """Mark a goal as completed."""
        self.hierarchy.complete_goal(goal_id)

    def fail_goal(self, goal_id: str, reason: str = ""):
        """Mark a goal as failed. Records in failure tracker."""
        goal = self.hierarchy.get_goal(goal_id)
        if goal:
            self.generator.record_failure(goal.domain, reason)
        self.hierarchy.fail_goal(goal_id, reason)

    def record_task_outcome(self, goal_id: str, success: bool, reason: str = ""):
        """Record outcome of a goal-driven task."""
        if success:
            self.complete_goal(goal_id)
        else:
            self.fail_goal(goal_id, reason)

    def decompose_goal(
        self,
        parent_id: str,
        sub_descriptions: List[str],
    ) -> List[ManagedGoal]:
        """Decompose a goal into sub-goals."""
        parent = self.hierarchy.get_goal(parent_id)
        if not parent:
            return []
        # Sub-goals are one level down in horizon
        sub_horizon_map = {
            GoalHorizon.LONG_TERM: GoalHorizon.MID_TERM,
            GoalHorizon.MID_TERM: GoalHorizon.SHORT_TERM,
            GoalHorizon.SHORT_TERM: GoalHorizon.SHORT_TERM,
        }
        sub_horizon = sub_horizon_map[parent.horizon]
        return self.hierarchy.decompose_goal(parent_id, sub_descriptions, sub_horizon)

    # ─── Internal ──────────────────────────────────────────────────

    def _generate_goals(
        self,
        sensor_events: Optional[List[Dict]],
        prediction_errors: Optional[Dict[str, float]],
    ) -> List[ManagedGoal]:
        """Generate goals from all sources."""
        new_goals = []

        # (a) Sensor events
        if sensor_events:
            for event in sensor_events:
                try:
                    if not isinstance(event, dict):
                        continue
                    goal = self.generator.generate_from_sensor_event(
                        event_type=event.get('type') or 'unknown',
                        event_data=event.get('data') or {},
                    )
                    if goal:
                        new_goals.append(goal)
                except Exception as e:
                    logger.debug(f"Sensor event goal generation failed: {e}")

        # (b) Repeated failures
        failure_goals = self.generator.generate_from_failures()
        new_goals.extend(failure_goals)

        # (c) Curiosity (from prediction errors)
        if prediction_errors:
            curiosity_goals = self.generator.generate_from_curiosity(prediction_errors)
            new_goals.extend(curiosity_goals)

        return new_goals

    # ─── State API ─────────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        """Get full goal management state for dashboard/API."""
        return {
            'hierarchy': self.hierarchy.get_state(),
            'generator': self.generator.get_state(),
            'conflict_resolver': self.conflict_resolver.get_state(),
            'stats': {
                'total_ticks': self._total_ticks,
                'total_tasks_generated': self._total_tasks_generated,
                'max_tasks_per_tick': self._max_tasks_per_tick,
            },
        }
