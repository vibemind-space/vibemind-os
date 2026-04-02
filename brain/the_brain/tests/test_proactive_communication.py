"""
Tests for Proactive Communication (P4.55-57).

Covers: StatusUpdater, ExplanationSystem, SuggestionEngine.
"""

import pytest
import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.proactive_communication import (
    StatusVerbosity,
    StatusUpdate,
    StatusUpdater,
    ExplanationSystem,
    Suggestion,
    SuggestionEngine,
)


# ─── StatusUpdate Tests ──────────────────────────────────────────────────

class TestStatusUpdate:
    def test_auto_timestamp(self):
        """Timestamp auto-generated."""
        u = StatusUpdate(category='info', message='test', importance=0.5)
        assert u.timestamp > 0

    def test_manual_timestamp(self):
        """Manual timestamp preserved."""
        u = StatusUpdate(category='info', message='test', importance=0.5, timestamp=42.0)
        assert u.timestamp == 42.0


# ─── StatusUpdater Tests ─────────────────────────────────────────────────

class TestStatusUpdater:
    def test_report_action_started(self):
        """Report action started creates update."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        update = su.report_action_started("Analyzing logs")
        assert update is not None
        assert "Working on" in update.message
        assert "Analyzing logs" in update.message

    def test_report_action_completed_success(self):
        """Report completed action (success)."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        update = su.report_action_completed("Build fix", success=True)
        assert update is not None
        assert "completed successfully" in update.message

    def test_report_action_completed_failure(self):
        """Report completed action (failure)."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        update = su.report_action_completed("Deploy", success=False)
        assert update is not None
        assert "failed" in update.message

    def test_report_issue_critical(self):
        """Report critical issue."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        update = su.report_issue("Disk at 95%", severity=0.9)
        assert update is not None
        assert "Critical" in update.message

    def test_report_issue_warning(self):
        """Report warning-level issue."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        update = su.report_issue("Memory at 75%", severity=0.6)
        assert "Warning" in update.message

    def test_report_issue_notice(self):
        """Report notice-level issue."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        update = su.report_issue("New commit detected", severity=0.3)
        assert "Notice" in update.message

    def test_silent_suppresses_all(self):
        """Silent verbosity suppresses all updates."""
        su = StatusUpdater(verbosity=StatusVerbosity.SILENT)
        update = su.report_issue("Critical error!", severity=1.0)
        assert update is None
        assert su._suppressed_count == 1

    def test_important_filters_low(self):
        """Important verbosity filters low-importance updates."""
        su = StatusUpdater(verbosity=StatusVerbosity.IMPORTANT, importance_threshold=0.5)
        # Low importance suppressed
        u1 = su.report_info("routine check", importance=0.2)
        assert u1 is None
        # High importance accepted
        u2 = su.report_issue("error detected", severity=0.8)
        assert u2 is not None

    def test_get_pending(self):
        """Pending updates can be retrieved and cleared."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        su.report_info("msg1")
        su.report_info("msg2")
        pending = su.get_pending()
        assert len(pending) == 2
        # After get, pending is cleared
        assert len(su.get_pending()) == 0

    def test_get_recent(self):
        """Recent history available as dicts."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL)
        su.report_info("msg1")
        su.report_info("msg2")
        recent = su.get_recent(5)
        assert len(recent) == 2
        assert recent[0]['message'] == 'msg1'

    def test_max_history(self):
        """History respects max_history."""
        su = StatusUpdater(verbosity=StatusVerbosity.ALL, max_history=5)
        for i in range(10):
            su.report_info(f"msg{i}")
        assert len(su._history) == 5

    def test_get_state(self):
        """State dict is complete."""
        su = StatusUpdater(verbosity=StatusVerbosity.IMPORTANT)
        su.report_info("low", importance=0.1)
        su.report_issue("high", severity=0.9)
        state = su.get_state()
        assert state['verbosity'] == 'important'
        assert state['total_updates'] == 2
        assert state['suppressed_count'] == 1

    def test_from_yaml(self):
        """Creates from YAML config."""
        config = {
            'status_updater': {
                'verbosity': 'all',
                'importance_threshold': 0.3,
                'max_history': 200,
            }
        }
        su = StatusUpdater.from_yaml(config)
        assert su.verbosity == StatusVerbosity.ALL
        assert su.importance_threshold == 0.3

    def test_from_yaml_invalid_verbosity(self):
        """Invalid verbosity falls back to IMPORTANT."""
        config = {'status_updater': {'verbosity': 'invalid'}}
        su = StatusUpdater.from_yaml(config)
        assert su.verbosity == StatusVerbosity.IMPORTANT


# ─── ExplanationSystem Tests ─────────────────────────────────────────────

class TestExplanationSystem:
    def test_basic_explanation(self):
        """Generate a basic explanation."""
        es = ExplanationSystem()
        exp = es.explain_decision(
            task_description="Run unit tests",
            decision="run pytest",
            confidence=0.85,
        )
        assert 'summary' in exp
        assert 'reasoning' in exp
        assert 'confidence_note' in exp
        assert "run pytest" in exp['summary']
        assert "High confidence" in exp['confidence_note']
        assert es._total_explanations == 1

    def test_with_reasoning_steps(self):
        """Reasoning steps included."""
        es = ExplanationSystem()
        exp = es.explain_decision(
            task_description="test",
            reasoning_steps=["Step 1", "Step 2", "Step 3"],
        )
        assert len(exp['reasoning']) == 3

    def test_with_alternatives(self):
        """Alternatives explained."""
        es = ExplanationSystem()
        exp = es.explain_decision(
            task_description="test",
            alternatives=[
                {'name': 'manual fix', 'rejection_reason': 'too slow'},
                {'name': 'skip', 'rejection_reason': 'risky'},
            ],
        )
        assert len(exp['alternatives']) == 2
        assert 'manual fix' in exp['alternatives'][0]
        assert 'too slow' in exp['alternatives'][0]

    def test_with_memory_influence(self):
        """Memory influence described."""
        es = ExplanationSystem()
        exp = es.explain_decision(
            task_description="test",
            memory_influence={
                'similar_tasks': [
                    ({'task': 'deploy api v2', 'outcome': 'success'}, 0.9),
                ]
            },
        )
        assert exp['memory_influence'] is not None
        assert 'deploy api v2' in exp['memory_influence']

    def test_with_generator(self):
        """Uses ExplanationGenerator when available."""
        class FakeGenerator:
            def generate_explanation(self, ctx):
                return {
                    'reasoning_steps': [
                        {'description': 'Analyzed error pattern'},
                        {'description': 'Found root cause'},
                    ]
                }

        class FakeCtx:
            pass

        es = ExplanationSystem(explanation_generator=FakeGenerator())
        exp = es.explain_decision(
            task_description="test",
            loop_context=FakeCtx(),
        )
        assert len(exp['reasoning']) == 2
        assert 'Analyzed error pattern' in exp['reasoning'][0]

    def test_confidence_notes(self):
        """Confidence maps to correct notes."""
        es = ExplanationSystem()
        high = es.explain_decision(task_description="t", confidence=0.9)
        assert "High" in high['confidence_note']

        med = es.explain_decision(task_description="t", confidence=0.6)
        assert "Moderate" in med['confidence_note']

        low = es.explain_decision(task_description="t", confidence=0.35)
        assert "Low" in low['confidence_note']

        very_low = es.explain_decision(task_description="t", confidence=0.1)
        assert "Very low" in very_low['confidence_note']

    def test_format_explanation(self):
        """Formatted explanation is readable text."""
        es = ExplanationSystem()
        exp = es.explain_decision(
            task_description="Fix build",
            decision="apply patch",
            confidence=0.8,
            reasoning_steps=["Found the bug", "Applied fix"],
        )
        text = es.format_explanation(exp)
        assert "apply patch" in text
        assert "1. Found the bug" in text

    def test_max_reasoning_steps(self):
        """Reasoning steps capped at max."""
        es = ExplanationSystem(max_reasoning_steps=2)
        exp = es.explain_decision(
            task_description="test",
            reasoning_steps=["s1", "s2", "s3", "s4", "s5"],
        )
        assert len(exp['reasoning']) == 2

    def test_get_state(self):
        """State is correct."""
        es = ExplanationSystem()
        es.explain_decision(task_description="test")
        state = es.get_state()
        assert state['total_explanations'] == 1
        assert state['has_generator'] is False


# ─── Suggestion Tests ────────────────────────────────────────────────────

class TestSuggestion:
    def test_auto_timestamp(self):
        """Timestamp auto-generated."""
        s = Suggestion(source='test', message='msg', confidence=0.8, actionable=False)
        assert s.timestamp > 0


# ─── SuggestionEngine Tests ──────────────────────────────────────────────

class TestSuggestionEngine:
    def test_prediction_error_suggestion(self):
        """High prediction error generates suggestion."""
        se = SuggestionEngine(confidence_threshold=0.5)
        suggestions = se.check_for_suggestions(
            prediction_errors={'logic': 0.9, 'temporal': 0.2},
        )
        assert len(suggestions) == 1
        assert 'logic' in suggestions[0].message
        assert suggestions[0].actionable is True

    def test_error_pattern_suggestion(self):
        """Recurring error pattern generates suggestion."""
        se = SuggestionEngine(confidence_threshold=0.5)
        suggestions = se.check_for_suggestions(
            error_patterns=[
                {'description': 'timeout errors', 'count': 5, 'period': 'last hour'},
            ],
        )
        assert len(suggestions) == 1
        assert 'timeout errors' in suggestions[0].message

    def test_memory_failure_suggestion(self):
        """Repeated failures generate suggestion."""
        se = SuggestionEngine(confidence_threshold=0.5)
        suggestions = se.check_for_suggestions(
            memory_context={
                'working_memory': {
                    'recent_tasks': [
                        {'outcome': 'failure', 'task_type': 'deploy'},
                        {'outcome': 'failure', 'task_type': 'deploy'},
                        {'outcome': 'success', 'task_type': 'build'},
                    ]
                }
            },
        )
        assert len(suggestions) >= 1
        deploy_sug = [s for s in suggestions if 'deploy' in s.message.lower()]
        assert len(deploy_sug) >= 1

    def test_health_suggestion(self):
        """High resource usage generates suggestion."""
        se = SuggestionEngine(confidence_threshold=0.5)
        suggestions = se.check_for_suggestions(
            health_data={'cpu_usage': 95, 'memory_usage': 60},
        )
        assert len(suggestions) >= 1
        cpu_sug = [s for s in suggestions if 'CPU' in s.message]
        assert len(cpu_sug) == 1

    def test_task_failure_pattern(self):
        """Three consecutive failures generate suggestion."""
        se = SuggestionEngine(confidence_threshold=0.5)
        suggestions = se.check_for_suggestions(
            recent_tasks=[
                {'outcome': 'failure'},
                {'outcome': 'failure'},
                {'outcome': 'failure'},
            ],
        )
        assert len(suggestions) >= 1
        assert 'failed' in suggestions[0].message.lower() or 'attention' in suggestions[0].message.lower()

    def test_confidence_threshold_filter(self):
        """Low-confidence suggestions filtered out."""
        se = SuggestionEngine(confidence_threshold=0.95)
        suggestions = se.check_for_suggestions(
            prediction_errors={'logic': 0.8},  # PE > 0.7 so candidate generated, but confidence 0.8 < 0.95
        )
        assert len(suggestions) == 0
        assert se._total_suppressed >= 1

    def test_cooldown_prevents_duplicates(self):
        """Same suggestion not repeated within cooldown."""
        se = SuggestionEngine(confidence_threshold=0.5, cooldown_seconds=60)
        s1 = se.check_for_suggestions(prediction_errors={'logic': 0.9})
        assert len(s1) == 1

        # Same check immediately → filtered by cooldown
        s2 = se.check_for_suggestions(prediction_errors={'logic': 0.9})
        assert len(s2) == 0

    def test_max_suggestions_per_tick(self):
        """Max suggestions per tick respected."""
        se = SuggestionEngine(confidence_threshold=0.3, max_suggestions_per_tick=2)
        suggestions = se.check_for_suggestions(
            prediction_errors={'a': 0.9, 'b': 0.9, 'c': 0.9, 'd': 0.9},
        )
        assert len(suggestions) <= 2

    def test_get_pending(self):
        """Pending suggestions retrievable and clearable."""
        se = SuggestionEngine(confidence_threshold=0.5)
        se.check_for_suggestions(prediction_errors={'logic': 0.9})
        pending = se.get_pending()
        assert len(pending) == 1
        assert len(se.get_pending()) == 0  # Cleared

    def test_get_recent(self):
        """Recent suggestions as dicts."""
        se = SuggestionEngine(confidence_threshold=0.5)
        se.check_for_suggestions(prediction_errors={'logic': 0.9})
        recent = se.get_recent()
        assert len(recent) == 1
        assert 'source' in recent[0]
        assert 'confidence' in recent[0]

    def test_max_history(self):
        """History respects max size."""
        se = SuggestionEngine(confidence_threshold=0.3, max_history=3, cooldown_seconds=0)
        for i in range(10):
            se.check_for_suggestions(prediction_errors={f'domain_{i}': 0.9})
        assert len(se._history) <= 3

    def test_no_suggestions_on_empty(self):
        """No suggestions when nothing provided."""
        se = SuggestionEngine()
        suggestions = se.check_for_suggestions()
        assert len(suggestions) == 0

    def test_get_state(self):
        """State dict is complete."""
        se = SuggestionEngine(confidence_threshold=0.7)
        state = se.get_state()
        assert state['confidence_threshold'] == 0.7
        assert state['total_generated'] == 0

    def test_from_yaml(self):
        """Creates from YAML config."""
        config = {
            'suggestion_engine': {
                'confidence_threshold': 0.8,
                'max_suggestions_per_tick': 5,
                'cooldown_seconds': 600,
            }
        }
        se = SuggestionEngine.from_yaml(config)
        assert se.confidence_threshold == 0.8
        assert se.max_suggestions_per_tick == 5
        assert se.cooldown_seconds == 600

    def test_from_yaml_empty(self):
        """Empty config uses defaults."""
        se = SuggestionEngine.from_yaml({})
        assert se.confidence_threshold == 0.7


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
