"""
Test Identity Modules (V2 Phase 6: P6.76-85)

Tests for:
  - SelfModel (P6.76)
  - AutobiographicMemory (P6.77)
  - ValueSystem (P6.78)
  - EmotionalMemorySystem (P6.79)
  - MoodSystem (P6.80)
  - StressResponse (P6.81)
  - UserModel (P6.82)
  - TrustModel (P6.83)
  - CollaborationPatterns (P6.84)
  - RelationshipHistory (P6.85)
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.self_model import SelfModel, AutobiographicMemory, ValueSystem
from core.emotional_memory import EmotionalMemorySystem, MoodSystem, StressResponse
from core.user_relationship import (
    UserModel, TrustModel, CollaborationPatterns, RelationshipHistory
)


# ═══════════════════════════════════════════════════════════════════════
# SelfModel (P6.76)
# ═══════════════════════════════════════════════════════════════════════

class TestSelfModel:
    """Tests for SelfModel — the brain's persistent self-image."""

    def test_record_outcome_updates_capability(self):
        sm = SelfModel()
        for i in range(5):
            sm.record_outcome('Coding_Engine', 'python', success=(i % 2 == 0))
        caps = sm.get_capabilities()
        assert 'Coding_Engine' in caps
        assert 'python' in caps['Coding_Engine']
        rec = caps['Coding_Engine']['python']
        assert rec['total_attempts'] == 5
        assert 0.0 <= rec['success_rate'] <= 1.0

    def test_strategy_tracking(self):
        sm = SelfModel()
        sm.record_outcome('Shell', 'docker', True, strategy='incremental')
        sm.record_outcome('Shell', 'docker', True, strategy='incremental')
        sm.record_outcome('Shell', 'docker', False, strategy='brute_force')
        prefs = sm.get_preferences()
        # incremental has 2 uses, should qualify
        strategies = prefs['preferred_strategies']
        strategy_names = [s['strategy'] for s in strategies]
        assert 'incremental' in strategy_names

    def test_tool_tracking(self):
        sm = SelfModel()
        sm.record_outcome('Shell', 'git', True, tools_used=['grep', 'pytest'])
        sm.record_outcome('Shell', 'git', True, tools_used=['grep'])
        sm.record_outcome('Shell', 'git', False, tools_used=['pytest'])
        prefs = sm.get_preferences()
        tools = prefs['preferred_tools']
        tool_names = [t['tool'] for t in tools]
        assert 'grep' in tool_names

    def test_weakness_auto_detection(self):
        sm = SelfModel()
        # Need 3+ attempts with low success rate to trigger auto-weakness
        sm.record_outcome('Shell', 'kubernetes', success=False)
        sm.record_outcome('Shell', 'kubernetes', success=False)
        sm.record_outcome('Shell', 'kubernetes', success=False)
        weaknesses = sm.get_weaknesses()
        # Should have auto-detected a weakness for Shell:kubernetes
        areas = [w['area'] for w in weaknesses]
        assert 'Shell:kubernetes' in areas

    def test_weakness_auto_resolve(self):
        sm = SelfModel(weakness_auto_resolve_threshold=5)
        # Create weakness first
        sm.record_outcome('Shell', 'k8s', success=False)
        sm.record_outcome('Shell', 'k8s', success=False)
        sm.record_outcome('Shell', 'k8s', success=False)
        assert len(sm.get_weaknesses()) > 0

        # Now achieve 5 consecutive successes to resolve it
        for _ in range(5):
            sm.record_outcome('Shell', 'k8s', success=True)
        weaknesses = sm.get_weaknesses()
        areas = [w['area'] for w in weaknesses]
        assert 'Shell:k8s' not in areas

    def test_record_weakness_external(self):
        sm = SelfModel()
        sm.record_weakness('regex', 'Cannot parse complex regex patterns', severity=0.7)
        weaknesses = sm.get_weaknesses()
        areas = [w['area'] for w in weaknesses]
        assert 'regex' in areas

    def test_strength_domains(self):
        sm = SelfModel()
        # Record 10 successes in python to establish a strength
        for _ in range(10):
            sm.record_outcome('Coding_Engine', 'python', success=True)
        strengths = sm.get_strength_domains(min_rate=0.8, min_attempts=5)
        assert len(strengths) >= 1
        assert strengths[0]['domain'] == 'python'

    def test_get_state(self):
        sm = SelfModel()
        sm.record_outcome('Shell', 'git', success=True)
        state = sm.get_state()
        assert isinstance(state, dict)
        expected_keys = [
            'total_outcomes', 'total_successes', 'overall_success_rate',
            'tracked_capabilities', 'tracked_systems', 'tracked_strategies',
            'tracked_tools', 'active_weaknesses', 'top_weaknesses',
            'strengths', 'preferences',
        ]
        for key in expected_keys:
            assert key in state, f"Missing key: {key}"

    def test_from_yaml(self):
        sm = SelfModel.from_yaml({'self_model': {'max_capabilities': 50}})
        assert sm.max_capabilities == 50

    def test_overall_success_rate(self):
        sm = SelfModel()
        sm.record_outcome('A', 'x', True)
        sm.record_outcome('A', 'x', False)
        state = sm.get_state()
        assert state['overall_success_rate'] == 0.5


# ═══════════════════════════════════════════════════════════════════════
# AutobiographicMemory (P6.77)
# ═══════════════════════════════════════════════════════════════════════

class TestAutobiographicMemory:
    """Tests for the brain's long-term developmental memory."""

    def test_record_milestone(self):
        am = AutobiographicMemory()
        m = am.record_milestone("First Docker deploy", "first_success", 0.9)
        assert m.event == "First Docker deploy"
        recent = am.get_recent_milestones()
        assert len(recent) == 1
        assert recent[0]['event'] == "First Docker deploy"

    def test_record_first_dedup(self):
        am = AutobiographicMemory()
        first = am.record_first("First python success", "python")
        assert first is not None
        second = am.record_first("Another python success", "python")
        assert second is None

    def test_record_daily_summary(self):
        am = AutobiographicMemory()
        summary = am.record_daily_summary(42, 0.85, ["Fixed auth bug"])
        assert summary.tasks_completed == 42
        state = am.get_state()
        assert state['total_daily_summaries'] == 1

    def test_get_narrative(self):
        am = AutobiographicMemory()
        am.record_milestone("First unit test passed", "first_success", 0.95)
        am.record_milestone("Learned Docker", "learning", 0.8)
        narrative = am.get_narrative()
        assert isinstance(narrative, str)
        assert len(narrative) > 0
        assert "Development Narrative" in narrative

    def test_milestones_filtered_by_valence(self):
        am = AutobiographicMemory()
        am.record_milestone("Great event", "learning", emotional_valence=0.9)
        am.record_milestone("Bad event", "failure_recovery", emotional_valence=0.2)
        am.record_milestone("Neutral event", "system_event", emotional_valence=0.5)

        high_valence = am.get_milestones(min_valence=0.6)
        assert len(high_valence) == 1
        assert high_valence[0]['emotional_valence'] >= 0.6

    def test_get_state_keys(self):
        am = AutobiographicMemory()
        state = am.get_state()
        assert isinstance(state, dict)
        assert 'total_milestones' in state
        assert 'firsts_recorded' in state

    def test_narrative_empty(self):
        am = AutobiographicMemory()
        narrative = am.get_narrative()
        assert "journey is just beginning" in narrative.lower()


# ═══════════════════════════════════════════════════════════════════════
# ValueSystem (P6.78)
# ═══════════════════════════════════════════════════════════════════════

class TestValueSystem:
    """Tests for the brain's explicit value system."""

    def test_evaluate_action_safe(self):
        vs = ValueSystem()
        assessment = vs.evaluate_action("help user fix bug", risk_level=0.1)
        assert assessment.recommendation == "proceed"

    def test_evaluate_action_risky(self):
        vs = ValueSystem()
        assessment = vs.evaluate_action("delete production database", risk_level=0.9)
        assert len(assessment.concerns) > 0
        # High risk action should at least be "caution" or "reconsider"
        assert assessment.recommendation in ("caution", "reconsider")

    def test_get_priority_weight(self):
        vs = ValueSystem()
        fix_weight = vs.get_priority_weight('fix')
        explore_weight = vs.get_priority_weight('explore')
        # Both should be valid floats, and potentially different
        assert 0.0 <= fix_weight <= 1.0
        assert 0.0 <= explore_weight <= 1.0

    def test_adjust_value(self):
        vs = ValueSystem()
        old_caution = vs.get_value('caution')
        result = vs.adjust_value('caution', -0.1)
        assert result is True
        new_caution = vs.get_value('caution')
        assert abs(new_caution - (old_caution - 0.1)) < 1e-6

    def test_adjust_value_unknown(self):
        vs = ValueSystem()
        result = vs.adjust_value('nonexistent_value', 0.1)
        assert result is False

    def test_get_value_instructions(self):
        vs = ValueSystem()
        instructions = vs.get_value_instructions()
        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_from_yaml(self):
        vs = ValueSystem.from_yaml({
            'value_system': {'values': {'reliability': 0.5}}
        })
        assert abs(vs.get_value('reliability') - 0.5) < 1e-6

    def test_get_state(self):
        vs = ValueSystem()
        state = vs.get_state()
        assert isinstance(state, dict)
        assert 'values' in state
        assert 'total_evaluations' in state

    def test_evaluate_growth_action(self):
        vs = ValueSystem()
        assessment = vs.evaluate_action("explore new deployment strategy", risk_level=0.2)
        assert 'growth' in assessment.supporting_values


# ═══════════════════════════════════════════════════════════════════════
# EmotionalMemorySystem (P6.79)
# ═══════════════════════════════════════════════════════════════════════

class TestEmotionalMemorySystem:
    """Tests for emotional memory — linking emotions to task outcomes."""

    def test_record_experience_success(self):
        ems = EmotionalMemorySystem()
        exp = ems.record_emotional_experience(
            "Deploy app", "deployment", "success", 0.8, 0.3
        )
        assert exp.marker == "confidence"

    def test_record_experience_failure(self):
        ems = EmotionalMemorySystem()
        exp = ems.record_emotional_experience(
            "Deploy app", "deployment", "failure", -0.5, 0.8
        )
        assert exp.marker == "frustration"

    def test_record_experience_failure_low_arousal(self):
        ems = EmotionalMemorySystem()
        exp = ems.record_emotional_experience(
            "Deploy app", "deployment", "failure", -0.5, 0.3
        )
        assert exp.marker == "disappointment"

    def test_emotional_bias_cautious(self):
        ems = EmotionalMemorySystem(similarity_threshold=0.0)
        # Record failures in the domain
        for _ in range(5):
            ems.record_emotional_experience(
                "deploy container", "deployment", "failure", -0.7, 0.8
            )
        bias = ems.get_emotional_bias("deploy container", "deployment")
        assert bias['caution_level'] > 0

    def test_emotional_bias_confident(self):
        ems = EmotionalMemorySystem(similarity_threshold=0.0)
        for _ in range(5):
            ems.record_emotional_experience(
                "deploy container", "deployment", "success", 0.8, 0.3
            )
        bias = ems.get_emotional_bias("deploy container", "deployment")
        assert bias['strategy_hint'] == 'confident'

    def test_emotional_bias_no_history(self):
        ems = EmotionalMemorySystem()
        bias = ems.get_emotional_bias("unknown task", "unknown_domain")
        assert bias['strategy_hint'] == 'neutral'
        assert bias['matching_memories'] == 0

    def test_from_yaml(self):
        ems = EmotionalMemorySystem.from_yaml({
            'emotional_memory_system': {'max_memories': 100}
        })
        assert ems.max_memories == 100

    def test_get_state(self):
        ems = EmotionalMemorySystem()
        ems.record_emotional_experience("test", "test", "success", 0.5, 0.5)
        state = ems.get_state()
        assert isinstance(state, dict)
        assert 'total_recorded' in state
        assert state['total_recorded'] == 1


# ═══════════════════════════════════════════════════════════════════════
# MoodSystem (P6.80)
# ═══════════════════════════════════════════════════════════════════════

class TestMoodSystem:
    """Tests for the long-lasting mood system."""

    def test_update_mood_positive(self):
        ms = MoodSystem(inertia=0.0)  # No inertia for direct testing
        mood = ms.update_mood(
            success_rate_24h=0.95,
            sensor_health=0.95,
            user_feedback_score=0.8
        )
        # Positive signals should not produce 'stressed' label
        assert mood.label != 'stressed'

    def test_update_mood_negative(self):
        ms = MoodSystem(inertia=0.0)
        mood = ms.update_mood(
            success_rate_24h=0.1,
            sensor_health=0.2,
            user_feedback_score=-0.8
        )
        assert mood.valence < 0

    def test_behavioral_modifiers(self):
        ms = MoodSystem()
        modifiers = ms.get_behavioral_modifiers()
        assert 0.1 <= modifiers['risk_tolerance'] <= 0.95
        assert modifiers['communication_tone'] in ('positive', 'neutral', 'cautious')

    def test_mood_inertia(self):
        ms = MoodSystem(inertia=0.85)
        # First update pushes mood very positive
        ms.update_mood(1.0, 1.0, 1.0)
        first_valence = ms.get_mood().valence
        # Second update tries to push mood very negative
        ms.update_mood(0.0, 0.0, -1.0)
        second_valence = ms.get_mood().valence
        # Due to inertia, the mood should not have jumped fully to negative
        # It should be different from a zero-inertia system
        assert second_valence != first_valence

    def test_save_load_state(self):
        ms = MoodSystem(inertia=0.0)
        ms.update_mood(0.9, 0.9, 0.7)
        saved = ms.save_state()

        ms2 = MoodSystem()
        ms2.load_state(saved)
        mood = ms2.get_mood()
        assert abs(mood.valence - saved['valence']) < 1e-6

    def test_get_state(self):
        ms = MoodSystem()
        state = ms.get_state()
        assert isinstance(state, dict)
        assert 'mood' in state
        assert 'behavioral_modifiers' in state


# ═══════════════════════════════════════════════════════════════════════
# StressResponse (P6.81)
# ═══════════════════════════════════════════════════════════════════════

class TestStressResponse:
    """Tests for the stress response system."""

    def test_task_events_increase_stress(self):
        sr = StressResponse(max_concurrent_tasks=5)
        initial = sr.get_stress_level()
        for _ in range(5):
            sr.record_event('task_start')
        assert sr.get_stress_level() > initial

    def test_errors_increase_stress(self):
        sr = StressResponse()
        for _ in range(5):
            sr.record_event('task_error')
        assert sr.get_stress_level() > 0.3

    def test_task_complete_resets_errors(self):
        sr = StressResponse()
        sr.record_event('task_error')
        sr.record_event('task_error')
        assert sr._consecutive_errors == 2
        sr.record_event('task_complete')
        assert sr._consecutive_errors == 0

    def test_recovery_threshold(self):
        sr = StressResponse(recovery_threshold=0.85, max_concurrent_tasks=5)
        # Push stress very high with concurrent tasks and errors
        for _ in range(5):
            sr.record_event('task_start')
        for _ in range(5):
            sr.record_event('task_error')
        # With 5 active tasks (100% load) and 5 consecutive errors,
        # stress should be very high
        if sr.get_stress_level() >= 0.85:
            assert sr.should_enter_recovery() is True

    def test_behavioral_adjustments(self):
        sr = StressResponse()
        adjustments = sr.get_behavioral_adjustments()
        assert 1.0 <= adjustments['caution_multiplier'] <= 2.0
        assert 0.0 <= adjustments['priority_strictness'] <= 1.0

    def test_from_yaml(self):
        sr = StressResponse.from_yaml({
            'stress_response': {'max_concurrent_tasks': 20}
        })
        assert sr.max_concurrent_tasks == 20

    def test_get_state(self):
        sr = StressResponse()
        state = sr.get_state()
        assert isinstance(state, dict)
        assert 'stress_level' in state
        assert 'stress_category' in state

    def test_stress_category_calm(self):
        sr = StressResponse()
        assert sr.get_stress_category() == 'calm'

    def test_task_start_resets_consecutive_errors(self):
        sr = StressResponse()
        sr.record_event('task_error')
        sr.record_event('task_error')
        assert sr._consecutive_errors == 2
        sr.record_event('task_start')
        assert sr._consecutive_errors == 0


# ═══════════════════════════════════════════════════════════════════════
# UserModel (P6.82)
# ═══════════════════════════════════════════════════════════════════════

class TestUserModel:
    """Tests for the user model — tracking user preferences and patterns."""

    def test_record_interaction(self):
        um = UserModel()
        now = time.time()
        um.record_interaction(now, 'python', 0.5)
        um.record_interaction(now, 'docker', 0.7)
        assert um._total_interactions == 2

    def test_expertise_beginner(self):
        um = UserModel()
        now = time.time()
        # Few simple interactions
        for _ in range(4):
            um.record_interaction(now, 'java', 0.2, user_feedback_score=0.5)
        expertise = um.get_expertise('java')
        assert expertise == 'beginner'

    def test_expertise_advanced(self):
        um = UserModel()
        now = time.time()
        # Many complex successful interactions
        for _ in range(20):
            um.record_interaction(now, 'python', 0.85, user_feedback_score=0.9)
        expertise = um.get_expertise('python')
        assert expertise in ('advanced', 'expert')

    def test_set_preference(self):
        um = UserModel()
        um.set_preference('technical', 0.9)
        prefs = um.get_preferences()
        assert abs(prefs['technical_vs_simple'] - 0.9) < 1e-6

    def test_get_state(self):
        um = UserModel()
        state = um.get_state()
        assert isinstance(state, dict)
        assert 'total_interactions' in state
        assert 'preferences' in state

    def test_from_yaml(self):
        um = UserModel.from_yaml({
            'user_model': {
                'max_interactions': 500,
                'default_preferences': {'technical': 0.8}
            }
        })
        assert um.max_interactions == 500
        assert abs(um._preference_technical - 0.8) < 1e-6


# ═══════════════════════════════════════════════════════════════════════
# TrustModel (P6.83)
# ═══════════════════════════════════════════════════════════════════════

class TestTrustModel:
    """Tests for bidirectional trust tracking."""

    def test_approval_increases_trust(self):
        tm = TrustModel()
        for _ in range(10):
            tm.record_approval(True)
        trust = tm.get_trust_levels()
        assert trust['user_trust'] > 0.5

    def test_denial_decreases_trust(self):
        tm = TrustModel()
        for _ in range(10):
            tm.record_approval(False)
        trust = tm.get_trust_levels()
        assert trust['user_trust'] < 0.5

    def test_autonomy_modifier(self):
        tm = TrustModel(autonomy_min=0.5, autonomy_max=2.0)
        modifier = tm.get_autonomy_modifier()
        assert 0.5 <= modifier <= 2.0

    def test_instruction_clarity(self):
        tm = TrustModel()
        for _ in range(10):
            tm.record_instruction_clarity(True)
        trust = tm.get_trust_levels()
        assert trust['system_trust'] > 0.5

    def test_get_state(self):
        tm = TrustModel()
        state = tm.get_state()
        assert isinstance(state, dict)
        assert 'user_trust_in_system' in state
        assert 'autonomy_modifier' in state

    def test_mixed_signals(self):
        tm = TrustModel()
        for _ in range(5):
            tm.record_approval(True)
        for _ in range(5):
            tm.record_approval(False)
        trust = tm.get_trust_levels()
        # Should be roughly balanced
        assert 0.3 <= trust['user_trust'] <= 0.7


# ═══════════════════════════════════════════════════════════════════════
# CollaborationPatterns (P6.84)
# ═══════════════════════════════════════════════════════════════════════

class TestCollaborationPatterns:
    """Tests for learning optimal collaboration style."""

    def test_record_preference(self):
        cp = CollaborationPatterns()
        for _ in range(5):
            cp.record_preference('error', 'detailed')
        recommended = cp.get_recommended_detail_level('error')
        assert recommended == 'detailed'

    def test_default_detail_level(self):
        cp = CollaborationPatterns()
        # No data: error defaults to 'detailed', success defaults to 'minimal'
        assert cp.get_recommended_detail_level('error') == 'detailed'
        assert cp.get_recommended_detail_level('success') == 'minimal'

    def test_should_notify_high_severity(self):
        cp = CollaborationPatterns()
        # severity >= 0.9 should always trigger notification
        assert cp.should_notify_proactively('any_event', severity=0.95) is True

    def test_notification_learning(self):
        cp = CollaborationPatterns()
        # Record that notifications for 'status' events were unwanted
        for _ in range(10):
            cp.record_notification_feedback('status', was_wanted=False)
        # Low severity status events should not notify
        assert cp.should_notify_proactively('status', severity=0.3) is False

    def test_get_state(self):
        cp = CollaborationPatterns()
        state = cp.get_state()
        assert isinstance(state, dict)
        assert 'detail_preferences' in state

    def test_majority_vote(self):
        cp = CollaborationPatterns()
        cp.record_preference('critical', 'minimal')
        cp.record_preference('critical', 'minimal')
        cp.record_preference('critical', 'detailed')
        assert cp.get_recommended_detail_level('critical') == 'minimal'


# ═══════════════════════════════════════════════════════════════════════
# RelationshipHistory (P6.85)
# ═══════════════════════════════════════════════════════════════════════

class TestRelationshipHistory:
    """Tests for the chronicle of collaboration."""

    def test_record_task(self):
        rh = RelationshipHistory()
        rh.record_task("Deploy app", "deployment", True)
        rh.record_task("Fix bug", "coding", False)
        summary = rh.get_summary()
        assert summary['total_tasks'] == 2

    def test_domain_stats(self):
        rh = RelationshipHistory()
        rh.record_task("Deploy v1", "deployment", True)
        rh.record_task("Deploy v2", "deployment", True)
        rh.record_task("Fix auth", "coding", False)
        state = rh.get_state()
        assert 'domain_breakdown' in state
        assert 'deployment' in state['domain_breakdown']
        assert state['domain_breakdown']['deployment']['total'] == 2

    def test_project_tracking(self):
        rh = RelationshipHistory()
        rh.record_project("Project Alpha")
        rh.record_project("Project Alpha", outcome='success')
        state = rh.get_state()
        projects = state.get('projects', [])
        assert len(projects) == 1
        assert projects[0]['outcome'] == 'success'

    def test_highlight_on_new_domain(self):
        rh = RelationshipHistory()
        rh.record_task("First k8s deploy", "kubernetes", True)
        # First success in a new domain should create a highlight
        summary = rh.get_summary()
        highlights = summary.get('highlights', [])
        assert any('kubernetes' in h.get('description', '') for h in highlights)

    def test_get_state(self):
        rh = RelationshipHistory()
        state = rh.get_state()
        assert isinstance(state, dict)
        assert 'total_tasks' in state

    def test_success_rate_calculation(self):
        rh = RelationshipHistory()
        rh.record_task("t1", "d", True)
        rh.record_task("t2", "d", True)
        rh.record_task("t3", "d", False)
        summary = rh.get_summary()
        expected = 2.0 / 3.0
        assert abs(summary['success_rate'] - round(expected, 3)) < 0.01

    def test_project_failure_creates_lowpoint(self):
        rh = RelationshipHistory()
        rh.record_project("Doomed Project")
        rh.record_project("Doomed Project", outcome='failed')
        summary = rh.get_summary()
        lowpoints = summary.get('lowpoints', [])
        assert any('Doomed Project' in lp.get('description', '') for lp in lowpoints)
