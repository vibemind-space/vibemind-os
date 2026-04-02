"""
Unit tests for the Consciousness Metrics System (core/consciousness_metrics.py)

Tests cover:
- CognitiveState dataclass initialization and serialization
- ConsciousnessMetrics default initialization
- State tracking via update_cognitive_state
- current_state to_dict serialization
- total_states_tracked increments
- Known unknowns tracking (epistemic humility)
- Confidence calibration statistics
- Uncertainty detection and state confidence
- High and low uncertainty states
- Bias detection (overconfidence, underconfidence)
- MetaCognitiveAssessment creation and serialization
- Multiple consecutive state updates
- State with extreme values (0.0, 1.0)
- State with minimal input
- Introspection reports
- History tracking (deque bounded)
- Reset / fresh instance behavior
- Thread safety (concurrent updates do not crash)
- Cognitive load estimation
- Integration with cognitive loop state patterns
- Recent performance analysis
- Statistics aggregation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
import time
import threading
from core.consciousness_metrics import (
    ConsciousnessMetrics,
    CognitiveState,
    MetaCognitiveAssessment,
)


# ---------------------------------------------------------------------------
# CognitiveState dataclass tests
# ---------------------------------------------------------------------------

class TestCognitiveState:
    """Tests for the CognitiveState dataclass."""

    def test_default_fields(self):
        """Verify default field values for CognitiveState."""
        state = CognitiveState(
            timestamp=1.0,
            attention_focus="focused",
            memory_load=0.5,
            reasoning_depth=2,
            uncertainty_level=0.3,
        )
        assert state.confidence_in_state == 0.5
        assert state.known_unknowns == []

    def test_to_dict_keys(self):
        """to_dict returns the expected keys."""
        state = CognitiveState(
            timestamp=100.0,
            attention_focus="distributed",
            memory_load=0.7,
            reasoning_depth=1,
            uncertainty_level=0.4,
        )
        d = state.to_dict()
        expected_keys = {
            'timestamp', 'attention_focus', 'memory_load',
            'reasoning_depth', 'uncertainty_level',
            'confidence_in_state', 'known_unknowns',
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        """to_dict returns correct values."""
        state = CognitiveState(
            timestamp=42.0,
            attention_focus="shifting",
            memory_load=0.9,
            reasoning_depth=3,
            uncertainty_level=0.8,
            confidence_in_state=0.6,
            known_unknowns=["a", "b", "c"],
        )
        d = state.to_dict()
        assert d['timestamp'] == 42.0
        assert d['attention_focus'] == "shifting"
        assert d['memory_load'] == 0.9
        assert d['reasoning_depth'] == 3
        assert d['uncertainty_level'] == 0.8
        assert d['confidence_in_state'] == 0.6
        # known_unknowns in to_dict is len(), not the list itself
        assert d['known_unknowns'] == 3

    def test_known_unknowns_as_count_in_dict(self):
        """to_dict serializes known_unknowns as a count, not a list."""
        state = CognitiveState(
            timestamp=0.0,
            attention_focus="focused",
            memory_load=0.0,
            reasoning_depth=0,
            uncertainty_level=0.0,
            known_unknowns=["x", "y"],
        )
        d = state.to_dict()
        assert isinstance(d['known_unknowns'], int)
        assert d['known_unknowns'] == 2


# ---------------------------------------------------------------------------
# MetaCognitiveAssessment dataclass tests
# ---------------------------------------------------------------------------

class TestMetaCognitiveAssessment:
    """Tests for the MetaCognitiveAssessment dataclass."""

    def test_default_lists(self):
        """identified_biases and lessons_learned default to empty lists."""
        a = MetaCognitiveAssessment(
            assessment_id="test_0",
            task_type="routing",
            decision_made="suggest",
            predicted_outcome="success",
            actual_outcome="success",
            confidence_before=0.8,
            surprise_after=0.1,
            calibration_error=0.1,
        )
        assert a.identified_biases == []
        assert a.lessons_learned == []

    def test_to_dict_keys(self):
        """to_dict returns the expected set of keys."""
        a = MetaCognitiveAssessment(
            assessment_id="a1",
            task_type="t",
            decision_made="d",
            predicted_outcome="p",
            actual_outcome="a",
            confidence_before=0.5,
            surprise_after=0.5,
            calibration_error=0.5,
        )
        d = a.to_dict()
        expected = {
            'assessment_id', 'task_type', 'decision_made',
            'predicted_outcome', 'actual_outcome',
            'confidence_before', 'surprise_after', 'calibration_error',
            'identified_biases', 'lessons_learned',
        }
        assert set(d.keys()) == expected

    def test_to_dict_preserves_lists(self):
        """to_dict preserves identified_biases and lessons_learned as lists."""
        a = MetaCognitiveAssessment(
            assessment_id="a2",
            task_type="routing",
            decision_made="retry",
            predicted_outcome="fail",
            actual_outcome="success",
            confidence_before=0.9,
            surprise_after=0.9,
            calibration_error=0.9,
            identified_biases=["overconfidence"],
            lessons_learned=["be more careful"],
        )
        d = a.to_dict()
        assert d['identified_biases'] == ["overconfidence"]
        assert d['lessons_learned'] == ["be more careful"]


# ---------------------------------------------------------------------------
# ConsciousnessMetrics main tests
# ---------------------------------------------------------------------------

class TestConsciousnessMetricsInit:
    """Tests for ConsciousnessMetrics initialization."""

    def test_default_initialization(self):
        """Fresh ConsciousnessMetrics has zeroed counters and None current_state."""
        cm = ConsciousnessMetrics()
        assert cm.total_states_tracked == 0
        assert cm.total_assessments == 0
        assert cm.self_awareness_events == 0
        assert cm.current_state is None
        assert len(cm.cognitive_states) == 0
        assert len(cm.assessments) == 0
        assert len(cm.known_unknowns) == 0
        assert len(cm.detected_biases) == 0

    def test_custom_history_size(self):
        """state_history_size and calibration_window are configurable."""
        cm = ConsciousnessMetrics(state_history_size=10, calibration_window=5)
        assert cm.state_history_size == 10
        assert cm.calibration_window == 5
        assert cm.cognitive_states.maxlen == 10
        assert cm.confidence_accuracy_pairs.maxlen == 5

    def test_repr(self):
        """__repr__ returns expected format."""
        cm = ConsciousnessMetrics()
        r = repr(cm)
        assert "ConsciousnessMetrics(" in r
        assert "states=0" in r
        assert "assessments=0" in r
        assert "awareness_events=0" in r


class TestUpdateCognitiveState:
    """Tests for update_cognitive_state."""

    def test_single_update(self):
        """A single update creates current_state and increments counter."""
        cm = ConsciousnessMetrics()
        state = cm.update_cognitive_state(
            attention_focus="focused",
            memory_load=0.3,
            reasoning_depth=1,
            uncertainty_level=0.2,
            timestamp=1000.0,
        )
        assert cm.current_state is state
        assert cm.total_states_tracked == 1
        assert len(cm.cognitive_states) == 1
        assert state.attention_focus == "focused"
        assert state.memory_load == 0.3
        assert state.reasoning_depth == 1
        assert state.uncertainty_level == 0.2
        assert state.timestamp == 1000.0

    def test_total_states_tracked_increments(self):
        """total_states_tracked increments with each call."""
        cm = ConsciousnessMetrics()
        for i in range(5):
            cm.update_cognitive_state("focused", 0.1, 1, 0.1, float(i))
        assert cm.total_states_tracked == 5

    def test_current_state_is_latest(self):
        """current_state always points to the most recent update."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.1, 1, 0.1, 1.0)
        cm.update_cognitive_state("distributed", 0.9, 3, 0.9, 2.0)
        assert cm.current_state.attention_focus == "distributed"
        assert cm.current_state.timestamp == 2.0

    def test_current_state_to_dict(self):
        """current_state.to_dict() returns proper serialization after update."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("shifting", 0.5, 2, 0.5, 99.0)
        d = cm.current_state.to_dict()
        assert d['timestamp'] == 99.0
        assert d['attention_focus'] == "shifting"
        assert isinstance(d['confidence_in_state'], float)

    def test_state_confidence_focused_low_load_low_uncertainty(self):
        """Focused attention + low load + low uncertainty -> high confidence."""
        cm = ConsciousnessMetrics()
        state = cm.update_cognitive_state("focused", 0.0, 1, 0.0, 1.0)
        # confidence = 1.0*0.3 + 1.0*0.3 + 1.0*0.4 = 1.0
        assert abs(state.confidence_in_state - 1.0) < 1e-9

    def test_state_confidence_distributed_high_load_high_uncertainty(self):
        """Distributed + high load + high uncertainty -> low confidence."""
        cm = ConsciousnessMetrics()
        state = cm.update_cognitive_state("distributed", 1.0, 3, 1.0, 1.0)
        # confidence = 0.5*0.3 + 0.0*0.3 + 0.0*0.4 = 0.15
        assert abs(state.confidence_in_state - 0.15) < 1e-9

    def test_high_uncertainty_state(self):
        """High uncertainty_level leads to lower state confidence."""
        cm = ConsciousnessMetrics()
        state = cm.update_cognitive_state("focused", 0.5, 2, 0.95, 1.0)
        # uncertainty_score = 1.0 - 0.95 = 0.05
        # confidence = 1.0*0.3 + 0.5*0.3 + 0.05*0.4 = 0.3 + 0.15 + 0.02 = 0.47
        assert abs(state.confidence_in_state - 0.47) < 1e-9

    def test_low_uncertainty_state(self):
        """Low uncertainty_level leads to higher state confidence."""
        cm = ConsciousnessMetrics()
        state = cm.update_cognitive_state("focused", 0.1, 0, 0.05, 1.0)
        # confidence = 1.0*0.3 + 0.9*0.3 + 0.95*0.4 = 0.3 + 0.27 + 0.38 = 0.95
        assert abs(state.confidence_in_state - 0.95) < 1e-9

    def test_extreme_values_zero(self):
        """State with all-zero floats does not crash."""
        cm = ConsciousnessMetrics()
        state = cm.update_cognitive_state("focused", 0.0, 0, 0.0, 0.0)
        assert state.memory_load == 0.0
        assert state.uncertainty_level == 0.0
        assert state.reasoning_depth == 0
        d = state.to_dict()
        assert d is not None

    def test_extreme_values_one(self):
        """State with all-one floats does not crash."""
        cm = ConsciousnessMetrics()
        state = cm.update_cognitive_state("distributed", 1.0, 3, 1.0, 1.0)
        assert state.memory_load == 1.0
        assert state.uncertainty_level == 1.0
        assert state.reasoning_depth == 3
        d = state.to_dict()
        assert d is not None

    def test_multiple_consecutive_updates(self):
        """20 consecutive updates all tracked correctly."""
        cm = ConsciousnessMetrics()
        for i in range(20):
            focus = ["focused", "distributed", "shifting"][i % 3]
            cm.update_cognitive_state(
                focus, i / 20.0, i % 4, i / 20.0, float(i)
            )
        assert cm.total_states_tracked == 20
        assert len(cm.cognitive_states) == 20
        assert cm.current_state.timestamp == 19.0


class TestKnownUnknowns:
    """Tests for epistemic humility / known unknowns tracking."""

    def test_track_known_unknown_no_current_state(self):
        """Tracking an unknown when current_state is None does not crash."""
        cm = ConsciousnessMetrics()
        cm.track_known_unknown("what is consciousness?")
        assert cm.known_unknowns["what is consciousness?"] == 1

    def test_track_known_unknown_with_current_state(self):
        """Unknown is appended to current_state.known_unknowns."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.5, 1, 0.3, 1.0)
        cm.track_known_unknown("edge case handling")
        assert "edge case handling" in cm.current_state.known_unknowns
        assert cm.known_unknowns["edge case handling"] == 1

    def test_track_multiple_unknowns(self):
        """Multiple distinct unknowns are tracked separately."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.5, 1, 0.3, 1.0)
        cm.track_known_unknown("uncertainty A")
        cm.track_known_unknown("uncertainty B")
        cm.track_known_unknown("uncertainty A")  # duplicate
        assert cm.known_unknowns["uncertainty A"] == 2
        assert cm.known_unknowns["uncertainty B"] == 1
        assert len(cm.current_state.known_unknowns) == 3

    def test_known_unknowns_count_in_state_dict(self):
        """to_dict known_unknowns reflects accumulated count."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.5, 1, 0.3, 1.0)
        cm.track_known_unknown("a")
        cm.track_known_unknown("b")
        d = cm.current_state.to_dict()
        assert d['known_unknowns'] == 2


class TestConfidenceCalibration:
    """Tests for confidence calibration tracking."""

    def test_empty_calibration(self):
        """No assessments -> zeroed calibration report."""
        cm = ConsciousnessMetrics()
        cal = cm.get_confidence_calibration()
        assert cal['calibration_error'] == 0.0
        assert cal['num_samples'] == 0
        assert cal['overconfidence'] == 0.0
        assert cal['underconfidence'] == 0.0

    def test_perfect_calibration(self):
        """When confidence matches accuracy perfectly, calibration error is 0."""
        cm = ConsciousnessMetrics()
        # Correct prediction with confidence 1.0
        cm.assess_decision_quality("routing", "suggest", "success", "success", 1.0)
        cal = cm.get_confidence_calibration()
        assert abs(cal['calibration_error']) < 1e-9
        assert cal['num_samples'] == 1

    def test_overconfidence_detection(self):
        """High confidence + wrong prediction -> overconfidence."""
        cm = ConsciousnessMetrics()
        cm.assess_decision_quality("routing", "suggest", "success", "fail", 0.9)
        cal = cm.get_confidence_calibration()
        assert cal['overconfidence'] > 0.0
        assert cal['num_samples'] == 1

    def test_underconfidence_detection(self):
        """Low confidence + correct prediction -> underconfidence."""
        cm = ConsciousnessMetrics()
        cm.assess_decision_quality("routing", "suggest", "success", "success", 0.2)
        cal = cm.get_confidence_calibration()
        assert cal['underconfidence'] > 0.0

    def test_calibration_window_bounded(self):
        """Calibration pairs respect the window size."""
        cm = ConsciousnessMetrics(calibration_window=5)
        for i in range(10):
            cm.assess_decision_quality("t", "d", "success", "success", 0.5)
        assert len(cm.confidence_accuracy_pairs) == 5


class TestBiasDetection:
    """Tests for cognitive bias detection."""

    def test_overconfidence_bias_flagged(self):
        """Confidence > accuracy + 0.3 -> overconfidence bias detected."""
        cm = ConsciousnessMetrics()
        assessment = cm.assess_decision_quality(
            "routing", "suggest", "success", "fail", 0.9
        )
        # confidence=0.9, accuracy=0.0, difference=0.9 > 0.3
        assert "overconfidence" in assessment.identified_biases
        assert cm.detected_biases['overconfidence'] >= 1

    def test_underconfidence_bias_flagged(self):
        """Confidence < accuracy - 0.3 -> underconfidence bias detected."""
        cm = ConsciousnessMetrics()
        assessment = cm.assess_decision_quality(
            "routing", "suggest", "success", "success", 0.1
        )
        # confidence=0.1, accuracy=1.0, difference=-0.9 < -0.3
        assert "underconfidence" in assessment.identified_biases
        assert cm.detected_biases['underconfidence'] >= 1

    def test_no_bias_when_calibrated(self):
        """Well-calibrated prediction has no bias flags."""
        cm = ConsciousnessMetrics()
        assessment = cm.assess_decision_quality(
            "routing", "suggest", "success", "success", 0.8
        )
        # confidence=0.8, accuracy=1.0, difference=-0.2 within [-0.3, 0.3]
        assert "overconfidence" not in assessment.identified_biases
        assert "underconfidence" not in assessment.identified_biases

    def test_task_specific_miscalibration_after_repeated_errors(self):
        """5+ assessments with high cal error triggers task-specific miscalibration."""
        cm = ConsciousnessMetrics()
        for i in range(6):
            cm.assess_decision_quality(
                "deploy", "execute", "success", "fail", 0.9
            )
        # The 6th assessment should detect miscalibration pattern
        last = cm.assessments[-1]
        miscalibration_biases = [
            b for b in last.identified_biases if "miscalibration" in b
        ]
        assert len(miscalibration_biases) > 0


class TestMetaCognitiveAssessmentCreation:
    """Tests for assess_decision_quality."""

    def test_correct_prediction_low_surprise(self):
        """Correct prediction has surprise 0."""
        cm = ConsciousnessMetrics()
        a = cm.assess_decision_quality("t", "d", "success", "success", 1.0)
        assert a.surprise_after == 0.0
        assert a.calibration_error == 0.0

    def test_wrong_prediction_high_surprise(self):
        """Wrong prediction with high confidence has high surprise."""
        cm = ConsciousnessMetrics()
        a = cm.assess_decision_quality("t", "d", "success", "fail", 0.9)
        assert a.surprise_after == 0.9
        assert a.calibration_error == 0.9

    def test_assessment_id_sequential(self):
        """Assessment IDs are sequential."""
        cm = ConsciousnessMetrics()
        a0 = cm.assess_decision_quality("t", "d", "s", "s", 0.5)
        a1 = cm.assess_decision_quality("t", "d", "s", "f", 0.5)
        assert a0.assessment_id == "assess_0"
        assert a1.assessment_id == "assess_1"

    def test_total_assessments_increments(self):
        """total_assessments counter increments."""
        cm = ConsciousnessMetrics()
        cm.assess_decision_quality("t", "d", "s", "s", 0.5)
        cm.assess_decision_quality("t", "d", "s", "f", 0.5)
        assert cm.total_assessments == 2

    def test_lessons_extracted_on_high_surprise(self):
        """High surprise leads to lessons about uncertainty."""
        cm = ConsciousnessMetrics()
        a = cm.assess_decision_quality("routing", "suggest", "success", "fail", 0.8)
        # surprise = |0.8 - 0| = 0.8 > 0.5 -> lesson about uncertainty
        assert any("uncertainty" in l.lower() or "High" in l for l in a.lessons_learned)

    def test_lessons_extracted_on_calibration_error(self):
        """High calibration error leads to lesson about calibration."""
        cm = ConsciousnessMetrics()
        a = cm.assess_decision_quality("routing", "suggest", "success", "fail", 0.7)
        # calibration_error = |0.7 - 0| = 0.7 > 0.3 -> calibration lesson
        assert any("calibration" in l.lower() for l in a.lessons_learned)

    def test_assessment_to_dict(self):
        """MetaCognitiveAssessment.to_dict() serializes all fields."""
        cm = ConsciousnessMetrics()
        a = cm.assess_decision_quality("routing", "retry", "fail", "fail", 0.5)
        d = a.to_dict()
        assert d['task_type'] == "routing"
        assert d['decision_made'] == "retry"
        assert d['predicted_outcome'] == "fail"
        assert d['actual_outcome'] == "fail"
        assert isinstance(d['identified_biases'], list)
        assert isinstance(d['lessons_learned'], list)


class TestIntrospection:
    """Tests for introspect() reports."""

    def test_introspection_no_state(self):
        """Introspection with no state returns None for current_state."""
        cm = ConsciousnessMetrics()
        report = cm.introspect()
        assert report['current_state'] is None
        assert report['known_unknowns_count'] == 0
        assert cm.self_awareness_events == 1

    def test_introspection_with_state(self):
        """Introspection with a current_state returns populated report."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.3, 1, 0.2, 1.0)
        cm.track_known_unknown("test unknown")
        report = cm.introspect()
        assert report['current_state'] is not None
        assert report['known_unknowns_count'] == 1
        assert 'confidence_calibration' in report
        assert 'recent_performance' in report
        assert 'cognitive_load' in report

    def test_introspection_increments_awareness_events(self):
        """Each introspect() call increments self_awareness_events."""
        cm = ConsciousnessMetrics()
        cm.introspect()
        cm.introspect()
        cm.introspect()
        assert cm.self_awareness_events == 3

    def test_introspection_report_keys(self):
        """Introspection report has the expected keys."""
        cm = ConsciousnessMetrics()
        report = cm.introspect()
        expected_keys = {
            'current_state', 'known_unknowns_count',
            'detected_biases', 'confidence_calibration',
            'recent_performance', 'cognitive_load',
        }
        assert set(report.keys()) == expected_keys


class TestCognitiveLoadEstimation:
    """Tests for _estimate_cognitive_load."""

    def test_no_state_default_load(self):
        """No current_state -> cognitive load 0.5."""
        cm = ConsciousnessMetrics()
        load = cm._estimate_cognitive_load()
        assert load == 0.5

    def test_zero_load_state(self):
        """All-zero state -> cognitive load 0."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.0, 0, 0.0, 1.0)
        load = cm._estimate_cognitive_load()
        assert abs(load - 0.0) < 1e-9

    def test_max_load_state(self):
        """All-max state -> cognitive load 1.0."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 1.0, 3, 1.0, 1.0)
        load = cm._estimate_cognitive_load()
        # load = 1.0*0.4 + 1.0*0.3 + (3/3)*0.3 = 0.4+0.3+0.3 = 1.0
        assert abs(load - 1.0) < 1e-9

    def test_partial_load(self):
        """Partial state values produce proportional cognitive load."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.5, 1, 0.5, 1.0)
        load = cm._estimate_cognitive_load()
        # load = 0.5*0.4 + 0.5*0.3 + (1/3)*0.3 = 0.2 + 0.15 + 0.1 = 0.45
        assert abs(load - 0.45) < 1e-9


class TestHistoryTracking:
    """Tests for bounded state history."""

    def test_history_bounded_by_maxlen(self):
        """cognitive_states deque respects state_history_size."""
        cm = ConsciousnessMetrics(state_history_size=5)
        for i in range(10):
            cm.update_cognitive_state("focused", 0.1, 1, 0.1, float(i))
        assert len(cm.cognitive_states) == 5
        # total_states_tracked still counts all
        assert cm.total_states_tracked == 10

    def test_oldest_states_evicted(self):
        """Oldest states are evicted when history is full."""
        cm = ConsciousnessMetrics(state_history_size=3)
        for i in range(5):
            cm.update_cognitive_state("focused", 0.1, 1, 0.1, float(i))
        timestamps = [s.timestamp for s in cm.cognitive_states]
        assert timestamps == [2.0, 3.0, 4.0]

    def test_assessments_not_bounded(self):
        """assessments list is unbounded (plain list)."""
        cm = ConsciousnessMetrics()
        for i in range(20):
            cm.assess_decision_quality("t", "d", "s", "s", 0.5)
        assert len(cm.assessments) == 20
        assert cm.total_assessments == 20


class TestRecentPerformance:
    """Tests for _analyze_recent_performance."""

    def test_no_assessments(self):
        """No assessments -> accuracy 0 and num_tasks 0."""
        cm = ConsciousnessMetrics()
        perf = cm._analyze_recent_performance()
        assert perf['accuracy'] == 0.0
        assert perf['num_tasks'] == 0

    def test_all_correct(self):
        """All correct predictions -> accuracy 1.0."""
        cm = ConsciousnessMetrics()
        for _ in range(5):
            cm.assess_decision_quality("t", "d", "success", "success", 0.8)
        perf = cm._analyze_recent_performance()
        assert perf['accuracy'] == 1.0
        assert perf['num_tasks'] == 5

    def test_all_wrong(self):
        """All wrong predictions -> accuracy 0.0."""
        cm = ConsciousnessMetrics()
        for _ in range(5):
            cm.assess_decision_quality("t", "d", "success", "fail", 0.8)
        perf = cm._analyze_recent_performance()
        assert perf['accuracy'] == 0.0

    def test_windowed_performance(self):
        """Recent performance uses the window parameter."""
        cm = ConsciousnessMetrics()
        # 10 wrong then 5 right
        for _ in range(10):
            cm.assess_decision_quality("t", "d", "success", "fail", 0.5)
        for _ in range(5):
            cm.assess_decision_quality("t", "d", "success", "success", 0.5)
        perf = cm._analyze_recent_performance(window=5)
        assert perf['accuracy'] == 1.0
        assert perf['num_tasks'] == 5


class TestStatistics:
    """Tests for get_statistics."""

    def test_fresh_statistics(self):
        """Fresh instance returns zeroed statistics."""
        cm = ConsciousnessMetrics()
        stats = cm.get_statistics()
        assert stats['total_states_tracked'] == 0
        assert stats['total_assessments'] == 0
        assert stats['self_awareness_events'] == 0
        assert stats['known_unknowns'] == 0
        assert stats['top_unknowns'] == []

    def test_statistics_after_activity(self):
        """Statistics reflect tracked activity."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.5, 1, 0.3, 1.0)
        cm.update_cognitive_state("distributed", 0.8, 2, 0.7, 2.0)
        cm.track_known_unknown("area A")
        cm.track_known_unknown("area B")
        cm.track_known_unknown("area A")
        cm.assess_decision_quality("t", "d", "s", "s", 0.5)
        cm.introspect()

        stats = cm.get_statistics()
        assert stats['total_states_tracked'] == 2
        assert stats['total_assessments'] == 1
        assert stats['self_awareness_events'] == 1
        assert stats['known_unknowns'] == 2  # 2 distinct unknowns
        assert stats['top_unknowns'][0] == ("area A", 2)

    def test_statistics_keys(self):
        """get_statistics returns the expected keys."""
        cm = ConsciousnessMetrics()
        stats = cm.get_statistics()
        expected_keys = {
            'total_states_tracked', 'total_assessments',
            'self_awareness_events', 'known_unknowns',
            'top_unknowns', 'detected_biases', 'confidence_calibration',
        }
        assert set(stats.keys()) == expected_keys


class TestResetBehavior:
    """Tests for fresh-instance behavior (no explicit reset method)."""

    def test_fresh_instance_independent(self):
        """A new ConsciousnessMetrics is fully independent of previous ones."""
        cm1 = ConsciousnessMetrics()
        cm1.update_cognitive_state("focused", 0.5, 1, 0.3, 1.0)
        cm1.track_known_unknown("x")
        cm1.assess_decision_quality("t", "d", "s", "s", 0.5)

        cm2 = ConsciousnessMetrics()
        assert cm2.total_states_tracked == 0
        assert cm2.total_assessments == 0
        assert cm2.current_state is None
        assert len(cm2.known_unknowns) == 0


class TestThreadSafety:
    """Tests for thread safety (no crash under concurrent access)."""

    def test_concurrent_state_updates_no_crash(self):
        """Multiple threads updating state concurrently do not crash."""
        cm = ConsciousnessMetrics(state_history_size=200)
        errors = []

        def update_states(thread_id):
            try:
                for i in range(50):
                    focus = ["focused", "distributed", "shifting"][i % 3]
                    cm.update_cognitive_state(
                        focus, i / 50.0, i % 4, i / 50.0,
                        float(thread_id * 1000 + i)
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_states, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All 200 updates should have been counted
        assert cm.total_states_tracked == 200

    def test_concurrent_assessments_no_crash(self):
        """Multiple threads creating assessments concurrently do not crash."""
        cm = ConsciousnessMetrics()
        errors = []

        def assess(thread_id):
            try:
                for i in range(20):
                    cm.assess_decision_quality(
                        f"type_{thread_id}", "suggest",
                        "success", "success" if i % 2 == 0 else "fail",
                        0.5 + (i % 3) * 0.1
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=assess, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_introspection_no_crash(self):
        """Introspection during concurrent updates does not crash."""
        cm = ConsciousnessMetrics()
        errors = []

        def updater():
            try:
                for i in range(30):
                    cm.update_cognitive_state("focused", 0.5, 1, 0.3, float(i))
                    cm.track_known_unknown(f"unknown_{i}")
            except Exception as e:
                errors.append(e)

        def inspector():
            try:
                for _ in range(10):
                    cm.introspect()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=updater)
        t2 = threading.Thread(target=inspector)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0


class TestIntegrationWithCognitiveLoopPattern:
    """
    Tests that mimic how the cognitive loop uses ConsciousnessMetrics:
    - perceive -> reflect -> update cognitive state -> introspect
    """

    def test_cognitive_loop_usage_pattern(self):
        """Simulate the cognitive loop's REFLECT phase usage pattern."""
        cm = ConsciousnessMetrics()

        # Step 1: Update cognitive state (as cognitive_loop.py does)
        attention_focus = "distributed"
        memory_load = 0.6
        reasoning_depth = 2
        uncertainty_level = 0.4

        state = cm.update_cognitive_state(
            attention_focus=attention_focus,
            memory_load=memory_load,
            reasoning_depth=reasoning_depth,
            uncertainty_level=uncertainty_level,
            timestamp=time.time(),
        )

        assert state is not None
        assert state.attention_focus == "distributed"

        # Step 2: Track known unknowns
        cm.track_known_unknown("task complexity unclear")

        # Step 3: Assess a decision
        assessment = cm.assess_decision_quality(
            task_type="routing",
            decision="suggest",
            predicted_outcome="success",
            actual_outcome="success",
            confidence=0.75,
        )
        assert assessment is not None

        # Step 4: Introspect
        report = cm.introspect()
        assert report['current_state'] is not None
        assert report['known_unknowns_count'] == 1
        assert report['recent_performance']['num_tasks'] == 1

    def test_full_session_simulation(self):
        """Simulate a full session with multiple tasks."""
        cm = ConsciousnessMetrics()
        tasks = [
            ("focused", 0.2, 1, 0.1, "success", "success", 0.9),
            ("distributed", 0.5, 2, 0.4, "success", "fail", 0.7),
            ("shifting", 0.8, 3, 0.8, "fail", "fail", 0.3),
            ("focused", 0.3, 1, 0.2, "success", "success", 0.85),
            ("distributed", 0.6, 2, 0.5, "success", "success", 0.6),
        ]

        for i, (focus, mem, depth, unc, pred, actual, conf) in enumerate(tasks):
            cm.update_cognitive_state(focus, mem, depth, unc, float(i))
            cm.assess_decision_quality("routing", "suggest", pred, actual, conf)

        assert cm.total_states_tracked == 5
        assert cm.total_assessments == 5

        stats = cm.get_statistics()
        assert stats['total_states_tracked'] == 5
        assert stats['total_assessments'] == 5

        cal = cm.get_confidence_calibration()
        assert cal['num_samples'] == 5
        assert 0.0 <= cal['calibration_error'] <= 1.0

    def test_state_dict_used_as_cognitive_loop_context(self):
        """Verify the state dict can be used as context (as cognitive loop does)."""
        cm = ConsciousnessMetrics()
        cm.update_cognitive_state("focused", 0.5, 2, 0.3, time.time())
        state_dict = cm.current_state.to_dict()

        # The cognitive loop stores this in ctx.cognitive_state
        # Verify all fields are JSON-serializable types
        import json
        serialized = json.dumps(state_dict)
        assert serialized is not None

        deserialized = json.loads(serialized)
        assert deserialized['attention_focus'] == "focused"
        assert deserialized['memory_load'] == 0.5
        assert deserialized['reasoning_depth'] == 2
