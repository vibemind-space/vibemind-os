"""
Meta-Cognition System (V2 PHASE 5: P5.70-72)

P5.70: SelfAwarenessModule
  - Per-system confidence tracking
  - Per-domain confidence tracking
  - Calibration: comparing predictions vs outcomes over time

P5.71: LearningDiagnosis
  - Detects learning progress or stagnation
  - Suggests focused practice areas
  - Tracks skill improvement over time

P5.72: KnowledgeGapDetection
  - Detects gaps from repeated failures
  - Generates targeted learning goals
  - Tracks knowledge gap resolution
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger('brain.meta_cognition')


# ─── P5.70: Self-Awareness Module ──────────────────────────────────────

@dataclass
class ConfidenceRecord:
    """Tracks confidence vs actual outcome for calibration."""
    predicted_confidence: float
    actual_success: bool
    domain: str
    system: str
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class SelfAwarenessModule:
    """
    P5.70: Tahlamus knows what it can and can't do.

    Tracks per-system and per-domain confidence, calibrating
    against actual outcomes over time.
    """

    def __init__(self, calibration_window: int = 100,
                 min_samples_for_confidence: int = 5):
        self.calibration_window = calibration_window
        self.min_samples = min_samples_for_confidence

        # Per-system tracking
        self._system_records: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=calibration_window)
        )
        # Per-domain tracking
        self._domain_records: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=calibration_window)
        )
        # Combined
        self._all_records: deque = deque(maxlen=calibration_window * 5)
        self._total_records = 0

    def record_outcome(self, system: str, domain: str,
                        predicted_confidence: float, success: bool) -> None:
        """Record an outcome for calibration tracking."""
        record = ConfidenceRecord(
            predicted_confidence=predicted_confidence,
            actual_success=success,
            domain=domain,
            system=system,
        )
        self._system_records[system].append(record)
        self._domain_records[domain].append(record)
        self._all_records.append(record)
        self._total_records += 1

    def get_system_confidence(self, system: str) -> Dict:
        """Get calibrated confidence for a system."""
        records = list(self._system_records.get(system, []))
        if len(records) < self.min_samples:
            return {
                'system': system,
                'confidence': 0.5,
                'calibrated': False,
                'samples': len(records),
            }

        success_rate = sum(1 for r in records if r.actual_success) / len(records)
        avg_predicted = sum(r.predicted_confidence for r in records) / len(records)
        calibration_error = abs(avg_predicted - success_rate)

        return {
            'system': system,
            'confidence': round(success_rate, 3),
            'avg_predicted': round(avg_predicted, 3),
            'calibration_error': round(calibration_error, 3),
            'calibrated': True,
            'samples': len(records),
        }

    def get_domain_confidence(self, domain: str) -> Dict:
        """Get calibrated confidence for a domain."""
        records = list(self._domain_records.get(domain, []))
        if len(records) < self.min_samples:
            return {
                'domain': domain,
                'confidence': 0.5,
                'calibrated': False,
                'samples': len(records),
            }

        success_rate = sum(1 for r in records if r.actual_success) / len(records)
        avg_predicted = sum(r.predicted_confidence for r in records) / len(records)

        return {
            'domain': domain,
            'confidence': round(success_rate, 3),
            'avg_predicted': round(avg_predicted, 3),
            'calibration_error': round(abs(avg_predicted - success_rate), 3),
            'calibrated': True,
            'samples': len(records),
        }

    def get_overall_calibration(self) -> Dict:
        """Get overall confidence calibration metrics."""
        records = list(self._all_records)
        if not records:
            return {'calibrated': False, 'samples': 0}

        # Bin predictions into buckets and check actual rates
        buckets = defaultdict(list)
        for r in records:
            bucket = round(r.predicted_confidence, 1)
            buckets[bucket].append(r.actual_success)

        calibration_data = {}
        total_error = 0.0
        bucket_count = 0
        for bucket, outcomes in sorted(buckets.items()):
            if len(outcomes) >= 3:
                actual_rate = sum(outcomes) / len(outcomes)
                calibration_data[str(bucket)] = {
                    'predicted': bucket,
                    'actual': round(actual_rate, 3),
                    'samples': len(outcomes),
                }
                total_error += abs(bucket - actual_rate)
                bucket_count += 1

        avg_error = total_error / max(bucket_count, 1)

        return {
            'calibrated': True,
            'samples': len(records),
            'avg_calibration_error': round(avg_error, 3),
            'calibration_buckets': calibration_data,
        }

    def get_weakest_areas(self, top_n: int = 5) -> List[Dict]:
        """Get domains/systems with lowest confidence."""
        areas = []
        for domain in self._domain_records:
            conf = self.get_domain_confidence(domain)
            if conf['calibrated']:
                areas.append({
                    'type': 'domain',
                    'name': domain,
                    'confidence': conf['confidence'],
                    'samples': conf['samples'],
                })
        for system in self._system_records:
            conf = self.get_system_confidence(system)
            if conf['calibrated']:
                areas.append({
                    'type': 'system',
                    'name': system,
                    'confidence': conf['confidence'],
                    'samples': conf['samples'],
                })

        areas.sort(key=lambda a: a['confidence'])
        return areas[:top_n]

    def get_state(self) -> Dict:
        return {
            'total_records': self._total_records,
            'tracked_systems': list(self._system_records.keys()),
            'tracked_domains': list(self._domain_records.keys()),
            'overall_calibration': self.get_overall_calibration(),
            'weakest_areas': self.get_weakest_areas(3),
        }


# ─── P5.71: Learning Diagnosis ─────────────────────────────────────────

class TrendDirection(Enum):
    IMPROVING = "improving"
    STAGNATING = "stagnating"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class LearningTrajectory:
    """Tracks learning progress in a specific area."""
    area: str                 # Domain or system
    area_type: str            # "domain" or "system"
    window_size: int = 20
    _success_history: List[bool] = field(default_factory=list)
    _timestamps: List[float] = field(default_factory=list)

    def record(self, success: bool) -> None:
        self._success_history.append(success)
        self._timestamps.append(time.time())
        if len(self._success_history) > self.window_size * 3:
            self._success_history = self._success_history[-self.window_size * 3:]
            self._timestamps = self._timestamps[-self.window_size * 3:]

    def get_trend(self) -> TrendDirection:
        """Determine learning trend by comparing recent vs older performance."""
        if len(self._success_history) < self.window_size:
            return TrendDirection.INSUFFICIENT_DATA

        mid = len(self._success_history) // 2
        older = self._success_history[:mid]
        recent = self._success_history[mid:]

        older_rate = sum(older) / len(older)
        recent_rate = sum(recent) / len(recent)

        delta = recent_rate - older_rate
        if delta > 0.1:
            return TrendDirection.IMPROVING
        elif delta < -0.1:
            return TrendDirection.DECLINING
        else:
            return TrendDirection.STAGNATING

    def get_current_rate(self) -> float:
        if not self._success_history:
            return 0.0
        recent = self._success_history[-self.window_size:]
        return sum(recent) / len(recent)

    def get_improvement(self) -> float:
        """Get improvement from first window to last window."""
        if len(self._success_history) < self.window_size:
            return 0.0
        first = self._success_history[:self.window_size]
        last = self._success_history[-self.window_size:]
        return (sum(last) / len(last)) - (sum(first) / len(first))

    def to_dict(self) -> Dict:
        return {
            'area': self.area,
            'area_type': self.area_type,
            'current_rate': round(self.get_current_rate(), 3),
            'trend': self.get_trend().value,
            'improvement': round(self.get_improvement(), 3),
            'samples': len(self._success_history),
        }


class LearningDiagnosis:
    """
    P5.71: Diagnoses learning progress and stagnation.

    Tracks success rates over time per area, detects improvement
    or stagnation, and suggests focus areas.
    """

    def __init__(self, stagnation_threshold: int = 30,
                 improvement_threshold: float = 0.1):
        self.stagnation_threshold = stagnation_threshold
        self.improvement_threshold = improvement_threshold
        self._trajectories: Dict[str, LearningTrajectory] = {}
        self._practice_suggestions: List[Dict] = []
        self._total_diagnoses = 0

    def record_outcome(self, area: str, area_type: str, success: bool) -> None:
        """Record a learning outcome for an area."""
        key = f"{area_type}:{area}"
        if key not in self._trajectories:
            self._trajectories[key] = LearningTrajectory(
                area=area, area_type=area_type
            )
        self._trajectories[key].record(success)

    def diagnose(self) -> List[Dict]:
        """
        Run diagnosis on all tracked areas.
        Returns list of diagnoses with suggestions.
        """
        diagnoses = []
        self._total_diagnoses += 1

        for key, trajectory in self._trajectories.items():
            trend = trajectory.get_trend()
            current_rate = trajectory.get_current_rate()
            improvement = trajectory.get_improvement()

            diagnosis = {
                'area': trajectory.area,
                'area_type': trajectory.area_type,
                'current_rate': round(current_rate, 3),
                'trend': trend.value,
                'improvement': round(improvement, 3),
                'suggestion': None,
            }

            if trend == TrendDirection.STAGNATING and current_rate < 0.7:
                diagnosis['suggestion'] = (
                    f"Stagnating in {trajectory.area} at {current_rate:.0%} — "
                    f"consider new strategies or focused practice."
                )
            elif trend == TrendDirection.DECLINING:
                diagnosis['suggestion'] = (
                    f"Declining in {trajectory.area} — investigate recent failures."
                )
            elif trend == TrendDirection.IMPROVING:
                diagnosis['suggestion'] = (
                    f"Improving in {trajectory.area} by {improvement:+.0%} — keep current approach."
                )

            diagnoses.append(diagnosis)

        return diagnoses

    def get_focus_areas(self) -> List[Dict]:
        """Get areas that need the most attention."""
        areas = []
        for key, trajectory in self._trajectories.items():
            trend = trajectory.get_trend()
            rate = trajectory.get_current_rate()
            # Priority: declining > stagnating+low > everything else
            priority = 0.0
            if trend == TrendDirection.DECLINING:
                priority = 2.0 + (1.0 - rate)
            elif trend == TrendDirection.STAGNATING and rate < 0.7:
                priority = 1.0 + (1.0 - rate)
            elif rate < 0.5:
                priority = 0.5 + (1.0 - rate)

            if priority > 0:
                areas.append({
                    'area': trajectory.area,
                    'area_type': trajectory.area_type,
                    'priority': round(priority, 3),
                    'current_rate': round(rate, 3),
                    'trend': trend.value,
                })

        areas.sort(key=lambda a: a['priority'], reverse=True)
        return areas[:5]

    def get_state(self) -> Dict:
        return {
            'tracked_areas': len(self._trajectories),
            'total_diagnoses': self._total_diagnoses,
            'trajectories': [t.to_dict() for t in self._trajectories.values()],
            'focus_areas': self.get_focus_areas(),
        }


# ─── P5.72: Knowledge Gap Detection ────────────────────────────────────

@dataclass
class KnowledgeGap:
    """A detected knowledge gap."""
    area: str
    description: str
    failure_count: int = 0
    first_detected: float = 0.0
    last_failure: float = 0.0
    severity: float = 0.0         # 0-1, based on failure frequency and impact
    resolved: bool = False
    resolution_strategy: str = ""
    learning_goal_id: str = ""    # Link to GoalGraph

    def __post_init__(self):
        if self.first_detected == 0.0:
            self.first_detected = time.time()

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure = time.time()
        self._update_severity()

    def _update_severity(self) -> None:
        # Severity based on failure frequency and recency
        frequency_factor = min(1.0, self.failure_count / 10.0)
        recency_hours = (time.time() - self.last_failure) / 3600.0
        recency_factor = max(0.1, 1.0 / (1.0 + recency_hours * 0.1))
        self.severity = frequency_factor * recency_factor

    def to_dict(self) -> Dict:
        return {
            'area': self.area,
            'description': self.description,
            'failure_count': self.failure_count,
            'severity': round(self.severity, 3),
            'resolved': self.resolved,
            'resolution_strategy': self.resolution_strategy,
            'learning_goal_id': self.learning_goal_id,
        }


class KnowledgeGapDetection:
    """
    P5.72: Detects knowledge gaps from repeated failures.

    When the system fails 3+ times in the same area, it's flagged
    as a knowledge gap. Generates learning goals and tracks resolution.
    """

    def __init__(self, failure_threshold: int = 3,
                 max_gaps: int = 50):
        self.failure_threshold = failure_threshold
        self.max_gaps = max_gaps
        self._gaps: Dict[str, KnowledgeGap] = {}  # area -> gap
        self._failure_buffer: Dict[str, List[float]] = defaultdict(list)  # area -> failure timestamps
        self._total_gaps_detected = 0
        self._total_gaps_resolved = 0

    def record_failure(self, area: str, description: str = "") -> Optional[KnowledgeGap]:
        """
        Record a failure in an area. Returns a KnowledgeGap if threshold reached.
        """
        self._failure_buffer[area].append(time.time())
        # Keep only recent failures (last 7 days)
        cutoff = time.time() - 7 * 86400
        self._failure_buffer[area] = [t for t in self._failure_buffer[area] if t > cutoff]

        if len(self._failure_buffer[area]) >= self.failure_threshold:
            if area not in self._gaps:
                gap = KnowledgeGap(
                    area=area,
                    description=description or f"Repeated failures in {area}",
                    failure_count=len(self._failure_buffer[area]),
                )
                self._gaps[area] = gap
                self._total_gaps_detected += 1

                # Capacity management
                if len(self._gaps) > self.max_gaps:
                    self._evict_resolved()

                return gap
            else:
                self._gaps[area].record_failure()
                if description:
                    self._gaps[area].description = description
                return self._gaps[area]

        return None

    def record_success(self, area: str) -> bool:
        """Record a success — may resolve a gap."""
        gap = self._gaps.get(area)
        if gap and not gap.resolved:
            # Check if we have enough recent successes to resolve
            # Simple: 3 successes in a row resolves the gap
            gap.failure_count = max(0, gap.failure_count - 1)
            if gap.failure_count <= 0:
                gap.resolved = True
                gap.resolution_strategy = "Achieved sufficient successes"
                self._total_gaps_resolved += 1
                return True
        return False

    def resolve_gap(self, area: str, strategy: str = "") -> bool:
        """Manually resolve a knowledge gap."""
        gap = self._gaps.get(area)
        if gap and not gap.resolved:
            gap.resolved = True
            gap.resolution_strategy = strategy
            self._total_gaps_resolved += 1
            return True
        return False

    def get_active_gaps(self) -> List[KnowledgeGap]:
        """Get all unresolved gaps, sorted by severity."""
        active = [g for g in self._gaps.values() if not g.resolved]
        active.sort(key=lambda g: g.severity, reverse=True)
        return active

    def get_gap(self, area: str) -> Optional[KnowledgeGap]:
        return self._gaps.get(area)

    def generate_learning_goals(self) -> List[Dict]:
        """Generate learning goals from knowledge gaps."""
        goals = []
        for gap in self.get_active_gaps():
            if gap.severity > 0.3:
                goals.append({
                    'area': gap.area,
                    'description': f"Fill knowledge gap: {gap.description}",
                    'severity': round(gap.severity, 3),
                    'failure_count': gap.failure_count,
                    'suggested_actions': [
                        f"Practice {gap.area} tasks with increasing difficulty",
                        f"Review past failures in {gap.area} for patterns",
                        f"Research best practices for {gap.area}",
                    ],
                })
        return goals

    def _evict_resolved(self) -> None:
        """Remove oldest resolved gaps."""
        resolved = [(k, g) for k, g in self._gaps.items() if g.resolved]
        resolved.sort(key=lambda x: x[1].first_detected)
        for key, _ in resolved[:10]:
            del self._gaps[key]

    def get_state(self) -> Dict:
        active = self.get_active_gaps()
        return {
            'total_gaps_detected': self._total_gaps_detected,
            'total_gaps_resolved': self._total_gaps_resolved,
            'active_gaps': len(active),
            'gaps': [g.to_dict() for g in active[:10]],
            'learning_goals': self.generate_learning_goals()[:5],
        }


# ─── Wisdom Module (Berkovich-Ohana 2014; Drigas 2023) ──────────────────

class WisdomModule:
    """Integrates cognition, affect, and reflection into wisdom.

    Wisdom = the ability to balance multiple perspectives, regulate emotions,
    accept uncertainty, and make decisions that serve long-term well-being.

    Research basis:
    - Berkovich-Ohana & Glicksohn (2014): CSS model of consciousness, 72 citations
    - Drigas et al. (2023): Meta-learning 9-layer model, 27 citations
    - Richter et al. (2024): Brain imaging of emotional well-being, 7 citations
    """

    def __init__(self):
        self._wisdom_dimensions: Dict[str, float] = {
            'cognitive_flexibility': 0.5,   # ability to shift perspectives
            'emotional_regulation': 0.5,    # managing emotional responses
            'self_reflection': 0.5,         # depth of introspection
            'uncertainty_tolerance': 0.5,   # comfort with ambiguity
            'perspective_taking': 0.5,      # seeing others' viewpoints
            'long_term_thinking': 0.5,      # temporal horizon of decisions
        }
        self._growth_trajectory: deque = deque(maxlen=200)
        self._peak_experiences: List[Dict] = []
        self._flow_count: int = 0
        self._reflection_count: int = 0
        self._total_decisions: int = 0

    def record_wise_decision(self, decision: str, dimensions_used: List[str],
                              outcome_quality: float = 0.5) -> Dict[str, Any]:
        """Record a decision and update wisdom dimensions.

        Wisdom grows through experience — especially through difficult decisions
        where multiple perspectives were considered.
        """
        outcome_quality = max(0.0, min(1.0, outcome_quality))
        self._total_decisions += 1

        complexity = len(dimensions_used) / len(self._wisdom_dimensions)
        growth = outcome_quality * complexity * 0.02

        for dim in dimensions_used:
            if dim in self._wisdom_dimensions:
                self._wisdom_dimensions[dim] = min(1.0,
                    self._wisdom_dimensions[dim] + growth)

        self._growth_trajectory.append({
            'time': time.time(),
            'wisdom_level': self._compute_overall_wisdom(),
            'decision': decision[:50]
        })

        return {
            'decision': decision,
            'complexity': round(complexity, 4),
            'growth': round(growth, 4),
            'wisdom_level': round(self._compute_overall_wisdom(), 4),
            'dimensions': {k: round(v, 4) for k, v in self._wisdom_dimensions.items()}
        }

    def record_peak_experience(self, description: str,
                                 flow_state: bool = False) -> Dict[str, Any]:
        """Record a peak experience (Maslow) or flow state.

        Peak experiences and flow states indicate self-actualization moments.
        """
        if flow_state:
            self._flow_count += 1

        experience = {
            'time': time.time(),
            'description': description[:100],
            'flow_state': flow_state,
            'wisdom_at_time': self._compute_overall_wisdom()
        }
        self._peak_experiences.append(experience)
        if len(self._peak_experiences) > 50:
            self._peak_experiences = self._peak_experiences[-50:]

        if flow_state:
            self._wisdom_dimensions['cognitive_flexibility'] = min(1.0,
                self._wisdom_dimensions['cognitive_flexibility'] + 0.01)

        return {
            'recorded': True,
            'total_peak_experiences': len(self._peak_experiences),
            'flow_count': self._flow_count,
            'self_actualization_progress': round(
                self._compute_self_actualization(), 4)
        }

    def record_reflection(self, insight: str = '') -> Dict[str, Any]:
        """Record a moment of self-reflection.

        Reflection deepens wisdom — the unexamined life...
        """
        self._reflection_count += 1
        self._wisdom_dimensions['self_reflection'] = min(1.0,
            self._wisdom_dimensions['self_reflection'] + 0.01)

        return {
            'reflection_count': self._reflection_count,
            'self_reflection_level': round(
                self._wisdom_dimensions['self_reflection'], 4),
            'wisdom_level': round(self._compute_overall_wisdom(), 4)
        }

    def get_wisdom_profile(self) -> Dict[str, Any]:
        """Comprehensive wisdom assessment."""
        overall = self._compute_overall_wisdom()
        self_act = self._compute_self_actualization()

        if overall > 0.8:
            wisdom_stage = 'sage'
        elif overall > 0.6:
            wisdom_stage = 'practitioner'
        elif overall > 0.4:
            wisdom_stage = 'developing'
        else:
            wisdom_stage = 'novice'

        weakest = min(self._wisdom_dimensions,
                     key=self._wisdom_dimensions.get)
        strongest = max(self._wisdom_dimensions,
                       key=self._wisdom_dimensions.get)

        return {
            'overall_wisdom': round(overall, 4),
            'wisdom_stage': wisdom_stage,
            'dimensions': {k: round(v, 4) for k, v in self._wisdom_dimensions.items()},
            'strongest_dimension': strongest,
            'growth_area': weakest,
            'self_actualization': round(self_act, 4),
            'peak_experiences': len(self._peak_experiences),
            'flow_states': self._flow_count,
            'reflections': self._reflection_count,
            'total_decisions': self._total_decisions
        }

    def _compute_overall_wisdom(self) -> float:
        """Compute overall wisdom as balanced integration of dimensions."""
        values = list(self._wisdom_dimensions.values())
        if not values:
            return 0.5
        mean = sum(values) / len(values)
        variance = sum((v - mean)**2 for v in values) / len(values)
        balance_bonus = max(0, 0.1 - variance) * 2
        return min(1.0, mean + balance_bonus)

    def _compute_self_actualization(self) -> float:
        """How close to self-actualization? (Maslow hierarchy top)."""
        wisdom = self._compute_overall_wisdom()
        peak_factor = min(0.2, len(self._peak_experiences) * 0.01)
        flow_factor = min(0.1, self._flow_count * 0.005)
        reflection_factor = min(0.1, self._reflection_count * 0.002)
        return min(1.0, wisdom * 0.6 + peak_factor + flow_factor + reflection_factor)

    def get_state(self) -> Dict[str, Any]:
        return self.get_wisdom_profile()
