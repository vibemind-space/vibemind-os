"""
Consciousness Metrics System (PHASE 11)

Implements self-awareness tracking and meta-cognitive monitoring:

1. Self-Awareness Tracking:
   - Monitor own cognitive states
   - Track certainty and uncertainty
   - Recognize knowledge boundaries
   - "Knowing that you know" vs. "knowing that you don't know"

2. Introspection:
   - Examine own reasoning processes
   - Identify cognitive biases
   - Assess decision quality
   - Meta-cognitive evaluation

3. Confidence Calibration:
   - Track prediction accuracy vs. confidence
   - Detect over/under-confidence
   - Improve calibration over time

4. Cognitive State Monitoring:
   - Track attention, memory, reasoning states
   - Detect cognitive load
   - Monitor resource allocation
   - Identify cognitive bottlenecks

5. Performance Meta-Analysis:
   - Analyze patterns in successes/failures
   - Identify systematic biases
   - Track improvement over time

Based on consciousness and meta-cognition research:
- Global Workspace Theory (Baars, 1988)
- Higher-Order Thought Theory (Rosenthal, 1986)
- Meta-cognition (Flavell, 1979)
- Introspective awareness (Schooler, 2002)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque, defaultdict


@dataclass
class CognitiveState:
    """
    Snapshot of cognitive state at a moment
    """
    timestamp: float

    # State dimensions
    attention_focus: str  # focused, distributed, shifting
    memory_load: float  # 0-1
    reasoning_depth: int  # 0-3 (shallow to deep)
    uncertainty_level: float  # 0-1

    # Meta-cognitive awareness
    confidence_in_state: float = 0.5  # How confident in this self-assessment
    known_unknowns: List[str] = field(default_factory=list)  # What we know we don't know

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'attention_focus': self.attention_focus,
            'memory_load': self.memory_load,
            'reasoning_depth': self.reasoning_depth,
            'uncertainty_level': self.uncertainty_level,
            'confidence_in_state': self.confidence_in_state,
            'known_unknowns': len(self.known_unknowns)
        }


@dataclass
class MetaCognitiveAssessment:
    """
    Meta-cognitive assessment of own performance
    """
    assessment_id: str

    # What was assessed
    task_type: str
    decision_made: str
    predicted_outcome: str
    actual_outcome: str

    # Meta-cognitive judgments
    confidence_before: float  # Confidence before seeing outcome
    surprise_after: float  # Surprise at outcome
    calibration_error: float  # |confidence - accuracy|

    # Insights
    identified_biases: List[str] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'assessment_id': self.assessment_id,
            'task_type': self.task_type,
            'decision_made': self.decision_made,
            'predicted_outcome': self.predicted_outcome,
            'actual_outcome': self.actual_outcome,
            'confidence_before': self.confidence_before,
            'surprise_after': self.surprise_after,
            'calibration_error': self.calibration_error,
            'identified_biases': self.identified_biases,
            'lessons_learned': self.lessons_learned
        }


class ConsciousnessMetrics:
    """
    Consciousness and meta-cognition monitoring system

    Key features:
    - Track self-awareness
    - Monitor cognitive states
    - Calibrate confidence
    - Introspective analysis
    - Meta-cognitive learning
    """

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'ConsciousnessMetrics':
        """Create ConsciousnessMetrics from YAML config dict (P5.67)."""
        cm = yaml_config.get('consciousness', {})
        return cls(
            state_history_size=cm.get('state_history_size', 100),
            calibration_window=cm.get('calibration_window', 50),
        )

    def __init__(
        self,
        state_history_size: int = 100,
        calibration_window: int = 50
    ):
        """
        Initialize consciousness metrics system

        Args:
            state_history_size: Number of cognitive states to remember
            calibration_window: Window for confidence calibration
        """
        self.state_history_size = state_history_size
        self.calibration_window = calibration_window

        # Cognitive state tracking
        self.cognitive_states: deque = deque(maxlen=state_history_size)
        self.current_state: Optional[CognitiveState] = None

        # Meta-cognitive assessments
        self.assessments: List[MetaCognitiveAssessment] = []

        # Confidence calibration
        self.confidence_accuracy_pairs: deque = deque(maxlen=calibration_window)

        # Known unknowns (epistemic humility)
        self.known_unknowns: Dict[str, int] = defaultdict(int)  # What we know we don't know

        # Cognitive biases detected
        self.detected_biases: Dict[str, int] = defaultdict(int)

        # Statistics
        self.total_states_tracked = 0
        self.total_assessments = 0
        self.self_awareness_events = 0

    def update_cognitive_state(
        self,
        attention_focus: str,
        memory_load: float,
        reasoning_depth: int,
        uncertainty_level: float,
        timestamp: float
    ) -> CognitiveState:
        """
        Update current cognitive state

        Args:
            attention_focus: Current attention state
            memory_load: Memory system load (0-1)
            reasoning_depth: Depth of reasoning (0-3)
            uncertainty_level: Overall uncertainty (0-1)
            timestamp: Current timestamp

        Returns:
            New cognitive state
        """
        state = CognitiveState(
            timestamp=timestamp,
            attention_focus=attention_focus,
            memory_load=memory_load,
            reasoning_depth=reasoning_depth,
            uncertainty_level=uncertainty_level,
            confidence_in_state=self._compute_state_confidence(
                attention_focus,
                memory_load,
                uncertainty_level
            )
        )

        self.cognitive_states.append(state)
        self.current_state = state
        self.total_states_tracked += 1

        return state

    def _compute_state_confidence(
        self,
        attention_focus: str,
        memory_load: float,
        uncertainty: float
    ) -> float:
        """Compute confidence in self-assessment"""
        # Higher confidence if focused, lower memory load, lower uncertainty
        focus_score = 1.0 if attention_focus == "focused" else 0.5
        load_score = 1.0 - memory_load
        uncertainty_score = 1.0 - uncertainty

        confidence = (focus_score * 0.3 + load_score * 0.3 + uncertainty_score * 0.4)

        return confidence

    def track_known_unknown(self, unknown: str):
        """Track something we know we don't know (epistemic humility)"""
        self.known_unknowns[unknown] += 1

        if self.current_state:
            self.current_state.known_unknowns.append(unknown)

    def assess_decision_quality(
        self,
        task_type: str,
        decision: str,
        predicted_outcome: str,
        actual_outcome: str,
        confidence: float
    ) -> MetaCognitiveAssessment:
        """
        Meta-cognitively assess a decision

        Args:
            task_type: Type of task
            decision: Decision that was made
            predicted_outcome: What we predicted would happen
            actual_outcome: What actually happened
            confidence: How confident we were

        Returns:
            Meta-cognitive assessment
        """
        # Compute surprise
        outcome_match = 1.0 if predicted_outcome == actual_outcome else 0.0
        surprise = abs(confidence - outcome_match)

        # Calibration error
        calibration_error = abs(confidence - outcome_match)

        # Record confidence-accuracy pair
        self.confidence_accuracy_pairs.append((confidence, outcome_match))

        # Create assessment
        assessment = MetaCognitiveAssessment(
            assessment_id=f"assess_{self.total_assessments}",
            task_type=task_type,
            decision_made=decision,
            predicted_outcome=predicted_outcome,
            actual_outcome=actual_outcome,
            confidence_before=confidence,
            surprise_after=surprise,
            calibration_error=calibration_error
        )

        # Detect biases
        biases = self._detect_biases(confidence, outcome_match, task_type)
        assessment.identified_biases = biases

        # Learn lessons
        lessons = self._extract_lessons(assessment)
        assessment.lessons_learned = lessons

        self.assessments.append(assessment)
        self.total_assessments += 1

        return assessment

    def _detect_biases(
        self,
        confidence: float,
        accuracy: float,
        task_type: str
    ) -> List[str]:
        """Detect cognitive biases"""
        biases = []

        # Overconfidence bias
        if confidence > accuracy + 0.3:
            biases.append("overconfidence")
            self.detected_biases['overconfidence'] += 1

        # Underconfidence bias
        if confidence < accuracy - 0.3:
            biases.append("underconfidence")
            self.detected_biases['underconfidence'] += 1

        # Check for task-specific patterns
        task_assessments = [a for a in self.assessments if a.task_type == task_type]
        if len(task_assessments) >= 5:
            # Check for consistent overconfidence on this task type
            recent_cal_errors = [a.calibration_error for a in task_assessments[-5:]]
            if np.mean(recent_cal_errors) > 0.3:
                biases.append(f"{task_type}_miscalibration")
                self.detected_biases[f"{task_type}_miscalibration"] += 1

        return biases

    def _extract_lessons(
        self,
        assessment: MetaCognitiveAssessment
    ) -> List[str]:
        """Extract lessons from assessment"""
        lessons = []

        # High surprise → uncertain situation
        if assessment.surprise_after > 0.5:
            lessons.append(f"High uncertainty on {assessment.task_type} tasks")

        # Calibration error → confidence miscalibration
        if assessment.calibration_error > 0.3:
            lessons.append("Improve confidence calibration")

        # Biases detected
        if assessment.identified_biases:
            lessons.append(f"Detected biases: {', '.join(assessment.identified_biases)}")

        return lessons

    def get_confidence_calibration(self) -> Dict:
        """Get confidence calibration statistics"""
        if not self.confidence_accuracy_pairs:
            return {
                'calibration_error': 0.0,
                'num_samples': 0,
                'overconfidence': 0.0,
                'underconfidence': 0.0
            }

        confidences = [c for c, a in self.confidence_accuracy_pairs]
        accuracies = [a for c, a in self.confidence_accuracy_pairs]

        # Mean calibration error
        calibration_error = np.mean([abs(c - a) for c, a in self.confidence_accuracy_pairs])

        # Overconfidence (confidence > accuracy)
        overconfidence = np.mean([max(0, c - a) for c, a in self.confidence_accuracy_pairs])

        # Underconfidence (accuracy > confidence)
        underconfidence = np.mean([max(0, a - c) for c, a in self.confidence_accuracy_pairs])

        return {
            'calibration_error': calibration_error,
            'num_samples': len(self.confidence_accuracy_pairs),
            'overconfidence': overconfidence,
            'underconfidence': underconfidence,
            'avg_confidence': np.mean(confidences),
            'avg_accuracy': np.mean(accuracies)
        }

    def introspect(self) -> Dict:
        """
        Perform introspection on own cognitive state

        Returns:
            Introspection report
        """
        self.self_awareness_events += 1

        report = {
            'current_state': self.current_state.to_dict() if self.current_state else None,
            'known_unknowns_count': len(self.known_unknowns),
            'detected_biases': dict(self.detected_biases),
            'confidence_calibration': self.get_confidence_calibration(),
            'recent_performance': self._analyze_recent_performance(),
            'cognitive_load': self._estimate_cognitive_load()
        }

        return report

    def _analyze_recent_performance(self, window: int = 10) -> Dict:
        """Analyze recent performance"""
        if not self.assessments:
            return {'accuracy': 0.0, 'num_tasks': 0}

        recent = self.assessments[-window:]

        accuracy = np.mean([
            1.0 if a.predicted_outcome == a.actual_outcome else 0.0
            for a in recent
        ])

        return {
            'accuracy': accuracy,
            'num_tasks': len(recent),
            'avg_surprise': np.mean([a.surprise_after for a in recent]),
            'avg_confidence': np.mean([a.confidence_before for a in recent])
        }

    def _estimate_cognitive_load(self) -> float:
        """Estimate current cognitive load"""
        if not self.current_state:
            return 0.5

        # Combine various indicators
        load = (
            self.current_state.memory_load * 0.4 +
            self.current_state.uncertainty_level * 0.3 +
            (self.current_state.reasoning_depth / 3.0) * 0.3
        )

        return load

    def get_statistics(self) -> Dict:
        """Get consciousness metrics statistics"""
        return {
            'total_states_tracked': self.total_states_tracked,
            'total_assessments': self.total_assessments,
            'self_awareness_events': self.self_awareness_events,
            'known_unknowns': len(self.known_unknowns),
            'top_unknowns': sorted(
                self.known_unknowns.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            'detected_biases': dict(self.detected_biases),
            'confidence_calibration': self.get_confidence_calibration()
        }

    def __repr__(self):
        return (
            f"ConsciousnessMetrics("
            f"states={len(self.cognitive_states)}, "
            f"assessments={len(self.assessments)}, "
            f"awareness_events={self.self_awareness_events})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("CONSCIOUSNESS METRICS SYSTEM (PHASE 11)")
    print("=" * 70)
    print()
    print("This module implements self-awareness and meta-cognition:")
    print("  - Track cognitive states")
    print("  - Monitor self-awareness")
    print("  - Calibrate confidence")
    print("  - Detect cognitive biases")
    print("  - Introspective analysis")
    print()
    print("=" * 70)
