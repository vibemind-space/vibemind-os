"""
Tests for Goal Management System (V2 Phase 3: P3.37-40)

Tests:
- GoalHierarchy (P3.37): 3-level system, decomposition, completion cascade
- GoalGeneration (P3.38): 5 sources, failure tracking, cooldowns
- GoalPrioritization (P3.39): composite scoring, neuromodulation bias
- GoalConflictResolution (P3.40): detection, auto-resolve, escalation
- GoalManager (orchestrator): tick cycle, end-to-end workflow
- YAML configuration: from_yaml loading
"""

import pytest
import time
import uuid
from unittest.mock import MagicMock, patch
from core.goal_management import (
    GoalHorizon, GoalSource, ConflictType, ConflictResolution,
    ManagedGoal, GoalConflict, GoalTask,
    FailureTracker, GoalGenerator, GoalPrioritizer,
    GoalConflictResolver, GoalHierarchy, GoalManager,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def managed_goal():
    return ManagedGoal(
        goal_id="test_goal_1",
        description="Fix the build",
        horizon=GoalHorizon.SHORT_TERM,
        source=GoalSource.SENSOR_EVENT,
        domain="ci",
        urgency=0.8,
        importance=0.7,
    )


@pytest.fixture
def goal_hierarchy():
    return GoalHierarchy(max_goals=50)


@pytest.fixture
def goal_generator():
    return GoalGenerator(
        failure_threshold=3,
        curiosity_pe_threshold=0.5,
        max_goals_per_tick=3,
        cooldown_seconds=0.0,  # No cooldown for tests
    )


@pytest.fixture
def goal_prioritizer():
    return GoalPrioritizer()


@pytest.fixture
def conflict_resolver():
    return GoalConflictResolver(
        resource_conflict_threshold=0.8,
        auto_resolve_severity_threshold=0.7,
    )


@pytest.fixture
def goal_manager():
    return GoalManager(
        max_goals=50,
        failure_threshold=3,
        curiosity_pe_threshold=0.5,
        max_goals_per_tick=3,
        generation_cooldown_seconds=0.0,
        max_tasks_per_tick=3,
    )


# ─── ManagedGoal Tests ─────────────────────────────────────────────────────

class TestManagedGoal:
    """Tests for ManagedGoal dataclass and scoring."""

    def test_default_values(self):
        g = ManagedGoal(goal_id="g1", description="test")
        assert g.horizon == GoalHorizon.SHORT_TERM
        assert g.source == GoalSource.INTERNAL
        assert g.urgency == 0.5
        assert g.importance == 0.5
        assert g.active is True
        assert g.completed is False

    def test_composite_score_positive(self, managed_goal):
        score = managed_goal.composite_score()
        assert score > 0, "Score should be positive for non-trivial goals"

    def test_user_request_bonus(self):
        g = ManagedGoal(goal_id="g1", description="test", source=GoalSource.USER_REQUEST)
        g_internal = ManagedGoal(goal_id="g2", description="test", source=GoalSource.INTERNAL)
        assert g.composite_score() > g_internal.composite_score(), \
            "User requests should have higher score"

    def test_short_term_urgency_boost(self):
        g_short = ManagedGoal(goal_id="g1", description="test", horizon=GoalHorizon.SHORT_TERM,
                               urgency=0.5, importance=0.5)
        g_long = ManagedGoal(goal_id="g2", description="test", horizon=GoalHorizon.LONG_TERM,
                              urgency=0.5, importance=0.5)
        assert g_short.composite_score() > g_long.composite_score()

    def test_neuro_bias_affects_score(self):
        g_pos = ManagedGoal(goal_id="g1", description="test", neuro_bias=0.5)
        g_neg = ManagedGoal(goal_id="g2", description="test", neuro_bias=-0.5)
        assert g_pos.composite_score() > g_neg.composite_score()

    def test_to_dict(self, managed_goal):
        d = managed_goal.to_dict()
        assert d['goal_id'] == "test_goal_1"
        assert d['description'] == "Fix the build"
        assert d['horizon'] == "short_term"
        assert d['source'] == "sensor_event"
        assert 'composite_score' in d
        assert isinstance(d['composite_score'], float)

    def test_effort_zero_safe(self):
        """estimated_effort=0 should not cause division by zero."""
        g = ManagedGoal(goal_id="g1", description="test", estimated_effort=0.0)
        score = g.composite_score()
        assert score > 0

    def test_score_bounded(self):
        """Score should be non-negative."""
        g = ManagedGoal(goal_id="g1", description="test",
                        urgency=0.0, importance=0.0, expected_reward=0.0, neuro_bias=-0.5)
        assert g.composite_score() >= 0.0


# ─── FailureTracker Tests ──────────────────────────────────────────────────

class TestFailureTracker:
    """Tests for repeated failure detection (P3.38b)."""

    def test_no_failures(self):
        ft = FailureTracker(threshold=3)
        assert ft.get_repeated_failures() == []

    def test_below_threshold(self):
        ft = FailureTracker(threshold=3)
        ft.record_failure("ci", "build failed")
        ft.record_failure("ci", "build failed again")
        assert ft.get_repeated_failures() == []

    def test_at_threshold(self):
        ft = FailureTracker(threshold=3)
        for i in range(3):
            ft.record_failure("ci", f"attempt {i}")
        result = ft.get_repeated_failures()
        assert len(result) == 1
        assert result[0][0] == "ci"
        assert result[0][1] == 3

    def test_multiple_domains(self):
        ft = FailureTracker(threshold=2)
        ft.record_failure("ci", "fail")
        ft.record_failure("ci", "fail")
        ft.record_failure("deploy", "fail")
        ft.record_failure("deploy", "fail")
        result = ft.get_repeated_failures()
        domains = {r[0] for r in result}
        assert "ci" in domains
        assert "deploy" in domains

    def test_clear_domain(self):
        ft = FailureTracker(threshold=2)
        ft.record_failure("ci", "fail")
        ft.record_failure("ci", "fail")
        ft.clear_domain("ci")
        assert ft.get_repeated_failures() == []

    def test_window_expiry(self):
        ft = FailureTracker(threshold=2, window_seconds=1.0)
        ft.record_failure("ci", "fail")
        ft.record_failure("ci", "fail")
        assert len(ft.get_repeated_failures()) == 1
        time.sleep(1.1)
        assert ft.get_repeated_failures() == []

    def test_get_state(self):
        ft = FailureTracker(threshold=3)
        ft.record_failure("ci", "test")
        state = ft.get_state()
        assert state['tracked_domains'] == 1
        assert state['threshold'] == 3


# ─── GoalGenerator Tests ──────────────────────────────────────────────────

class TestGoalGenerator:
    """Tests for goal generation from 5 sources (P3.38)."""

    def test_sensor_event_error(self, goal_generator):
        goal = goal_generator.generate_from_sensor_event(
            event_type="error",
            event_data={'message': "Build failed", 'domain': 'ci'},
        )
        assert goal is not None
        assert goal.source == GoalSource.SENSOR_EVENT
        assert goal.urgency >= 0.7
        assert "Fix" in goal.description

    def test_sensor_event_warning(self, goal_generator):
        goal = goal_generator.generate_from_sensor_event(
            event_type="degradation",
            event_data={'message': "High latency"},
        )
        assert goal is not None
        assert "Investigate" in goal.description

    def test_sensor_event_info(self, goal_generator):
        goal = goal_generator.generate_from_sensor_event(
            event_type="info",
            event_data={'message': "Deployed OK"},
        )
        assert goal is not None
        assert goal.urgency < 0.5

    def test_failure_generation(self, goal_generator):
        for i in range(3):
            goal_generator.record_failure("ci", f"fail {i}")
        goals = goal_generator.generate_from_failures()
        assert len(goals) == 1
        assert goals[0].source == GoalSource.REPEATED_FAILURE
        assert "root cause" in goals[0].description.lower()

    def test_failure_clears_after_generation(self, goal_generator):
        for i in range(3):
            goal_generator.record_failure("ci", f"fail {i}")
        goal_generator.generate_from_failures()
        # Second call should not generate (domain cleared)
        goals2 = goal_generator.generate_from_failures()
        assert len(goals2) == 0

    def test_curiosity_high_pe(self, goal_generator):
        goals = goal_generator.generate_from_curiosity({
            'docker': 0.8,
            'git': 0.3,
        })
        assert len(goals) == 1  # Only docker (>= 0.5 threshold)
        assert goals[0].domain == 'docker'
        assert goals[0].source == GoalSource.CURIOSITY

    def test_curiosity_below_threshold(self, goal_generator):
        goals = goal_generator.generate_from_curiosity({'git': 0.2})
        assert len(goals) == 0

    def test_user_request(self, goal_generator):
        goal = goal_generator.generate_from_user_request("Deploy to production")
        assert goal.source == GoalSource.USER_REQUEST
        assert goal.urgency == 1.0
        assert goal.importance == 1.0

    def test_pattern_generation(self, goal_generator):
        goal = goal_generator.generate_from_pattern("Merge branches before standup")
        assert goal is not None
        assert goal.source == GoalSource.PATTERN
        assert "Proactive" in goal.description

    def test_cooldown_respected(self):
        gen = GoalGenerator(cooldown_seconds=10.0)
        # First call works
        goal = gen.generate_from_sensor_event("error", {'message': 'fail'})
        assert goal is not None
        # Second call blocked by cooldown
        goal2 = gen.generate_from_sensor_event("error", {'message': 'fail2'})
        assert goal2 is None

    def test_max_per_tick(self, goal_generator):
        goals = goal_generator.generate_from_curiosity({
            'a': 0.9, 'b': 0.8, 'c': 0.7, 'd': 0.6, 'e': 0.5,
        })
        assert len(goals) <= 3  # max_goals_per_tick = 3

    def test_get_state(self, goal_generator):
        state = goal_generator.get_state()
        assert 'generated_count' in state
        assert 'failure_tracker' in state


# ─── GoalPrioritizer Tests ────────────────────────────────────────────────

class TestGoalPrioritizer:
    """Tests for goal prioritization (P3.39)."""

    def test_rank_by_score(self, goal_prioritizer):
        g1 = ManagedGoal(goal_id="g1", description="low", urgency=0.2, importance=0.2)
        g2 = ManagedGoal(goal_id="g2", description="high", urgency=0.9, importance=0.9)
        ranked = goal_prioritizer.rank_goals([g1, g2])
        assert ranked[0].goal_id == "g2"

    def test_high_dopamine_boosts_reward(self, goal_prioritizer):
        goals = [
            ManagedGoal(goal_id="g1", description="safe", expected_reward=0.2),
            ManagedGoal(goal_id="g2", description="risky", expected_reward=0.9),
        ]
        neuro = {'dopamine': 0.8, 'norepinephrine': 0.5, 'serotonin': 0.5}
        goals = goal_prioritizer.apply_neuromodulation(goals, neuro)
        # High dopamine should give positive bias to high-reward goal
        assert goals[1].neuro_bias > goals[0].neuro_bias

    def test_low_dopamine_penalizes_reward(self, goal_prioritizer):
        goals = [
            ManagedGoal(goal_id="g1", description="risky", expected_reward=0.9),
        ]
        neuro = {'dopamine': 0.2, 'norepinephrine': 0.5, 'serotonin': 0.5}
        goals = goal_prioritizer.apply_neuromodulation(goals, neuro)
        assert goals[0].neuro_bias < 0

    def test_high_ne_boosts_urgent(self, goal_prioritizer):
        goals = [
            ManagedGoal(goal_id="g1", description="chill", urgency=0.2),
            ManagedGoal(goal_id="g2", description="urgent", urgency=0.9),
        ]
        neuro = {'dopamine': 0.5, 'norepinephrine': 0.8, 'serotonin': 0.5}
        goals = goal_prioritizer.apply_neuromodulation(goals, neuro)
        assert goals[1].neuro_bias > goals[0].neuro_bias

    def test_high_serotonin_prefers_low_effort(self, goal_prioritizer):
        goals = [
            ManagedGoal(goal_id="g1", description="hard", estimated_effort=0.9),
            ManagedGoal(goal_id="g2", description="easy", estimated_effort=0.1),
        ]
        neuro = {'dopamine': 0.5, 'norepinephrine': 0.5, 'serotonin': 0.8}
        goals = goal_prioritizer.apply_neuromodulation(goals, neuro)
        assert goals[1].neuro_bias > goals[0].neuro_bias

    def test_neuro_with_object(self, goal_prioritizer):
        """Neuromodulation works with object-style levels."""
        mock_levels = MagicMock()
        mock_levels.dopamine = 0.7
        mock_levels.norepinephrine = 0.5
        mock_levels.serotonin = 0.5
        goals = [ManagedGoal(goal_id="g1", description="test", expected_reward=0.8)]
        goals = goal_prioritizer.apply_neuromodulation(goals, mock_levels)
        assert goals[0].neuro_bias > 0

    def test_neuro_none_passthrough(self, goal_prioritizer):
        goals = [ManagedGoal(goal_id="g1", description="test")]
        result = goal_prioritizer.apply_neuromodulation(goals, None)
        assert result[0].neuro_bias == 0.0

    def test_neuro_bias_bounded(self, goal_prioritizer):
        goals = [
            ManagedGoal(goal_id="g1", description="test",
                        urgency=1.0, expected_reward=1.0, estimated_effort=0.0),
        ]
        neuro = {'dopamine': 1.0, 'norepinephrine': 1.0, 'serotonin': 1.0}
        goals = goal_prioritizer.apply_neuromodulation(goals, neuro)
        assert -0.5 <= goals[0].neuro_bias <= 0.5

    def test_get_top_actionable(self, goal_prioritizer):
        goals = [
            ManagedGoal(goal_id="g1", description="a", urgency=0.9, importance=0.9),
            ManagedGoal(goal_id="g2", description="b", urgency=0.5, importance=0.5),
            ManagedGoal(goal_id="g3", description="c", completed=True),  # Should be excluded
        ]
        top = goal_prioritizer.get_top_actionable(goals, max_goals=2)
        assert len(top) == 2
        assert all(not g.completed for g in top)

    def test_get_top_excludes_failed(self, goal_prioritizer):
        goals = [
            ManagedGoal(goal_id="g1", description="a", failed=True, active=False),
            ManagedGoal(goal_id="g2", description="b", urgency=0.5),
        ]
        top = goal_prioritizer.get_top_actionable(goals, max_goals=5)
        assert len(top) == 1
        assert top[0].goal_id == "g2"


# ─── GoalConflictResolver Tests ──────────────────────────────────────────

class TestGoalConflictResolver:
    """Tests for goal conflict detection and resolution (P3.40)."""

    def test_no_conflicts(self, conflict_resolver):
        goals = [
            ManagedGoal(goal_id="g1", description="A", domain="ci"),
            ManagedGoal(goal_id="g2", description="B", domain="deploy"),
        ]
        conflicts = conflict_resolver.detect_conflicts(goals)
        assert len(conflicts) == 0

    def test_resource_conflict_same_domain(self, conflict_resolver):
        goals = [
            ManagedGoal(goal_id="g1", description="Task A", domain="ci", urgency=0.8),
            ManagedGoal(goal_id="g2", description="Task B", domain="ci", urgency=0.7),
        ]
        conflicts = conflict_resolver.detect_conflicts(goals)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == ConflictType.RESOURCE

    def test_no_conflict_general_domain(self, conflict_resolver):
        """'general' domain should not trigger resource conflicts."""
        goals = [
            ManagedGoal(goal_id="g1", description="A", domain="general"),
            ManagedGoal(goal_id="g2", description="B", domain="general"),
        ]
        conflicts = conflict_resolver.detect_conflicts(goals)
        resource_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.RESOURCE]
        assert len(resource_conflicts) == 0

    def test_logical_conflict_deploy_vs_fix(self, conflict_resolver):
        goals = [
            ManagedGoal(goal_id="g1", description="Deploy to production", domain="prod"),
            ManagedGoal(goal_id="g2", description="Fix critical test failures", domain="test"),
        ]
        conflicts = conflict_resolver.detect_conflicts(goals)
        logical = [c for c in conflicts if c.conflict_type == ConflictType.LOGICAL]
        assert len(logical) == 1

    def test_auto_resolve_low_severity(self, conflict_resolver):
        conflict = GoalConflict(
            conflict_id="c1",
            goal_a_id="g1",
            goal_b_id="g2",
            conflict_type=ConflictType.RESOURCE,
            severity=0.5,
        )
        goals = {
            "g1": ManagedGoal(goal_id="g1", description="A", urgency=0.9, importance=0.9),
            "g2": ManagedGoal(goal_id="g2", description="B", urgency=0.3, importance=0.3),
        }
        resolution = conflict_resolver.resolve_conflict(conflict, goals)
        assert resolution == ConflictResolution.PRIORITY_OVERRIDE
        assert conflict.resolved_at is not None

    def test_escalate_high_severity(self, conflict_resolver):
        conflict = GoalConflict(
            conflict_id="c1",
            goal_a_id="g1",
            goal_b_id="g2",
            conflict_type=ConflictType.LOGICAL,
            severity=0.9,
        )
        goals = {
            "g1": ManagedGoal(goal_id="g1", description="A"),
            "g2": ManagedGoal(goal_id="g2", description="B"),
        }
        resolution = conflict_resolver.resolve_conflict(conflict, goals)
        assert resolution == ConflictResolution.USER_DECIDED

    def test_resolve_missing_goal(self, conflict_resolver):
        conflict = GoalConflict(
            conflict_id="c1", goal_a_id="missing", goal_b_id="g2",
            conflict_type=ConflictType.RESOURCE, severity=0.3,
        )
        resolution = conflict_resolver.resolve_conflict(conflict, {})
        assert resolution == ConflictResolution.ABANDONED

    def test_already_resolved(self, conflict_resolver):
        conflict = GoalConflict(
            conflict_id="c1", goal_a_id="g1", goal_b_id="g2",
            conflict_type=ConflictType.RESOURCE, severity=0.3,
            resolution=ConflictResolution.MERGED,
        )
        result = conflict_resolver.resolve_conflict(conflict, {})
        assert result == ConflictResolution.MERGED

    def test_sequential_for_equal_scores(self, conflict_resolver):
        conflict = GoalConflict(
            conflict_id="c1", goal_a_id="g1", goal_b_id="g2",
            conflict_type=ConflictType.RESOURCE, severity=0.5,
        )
        goals = {
            "g1": ManagedGoal(goal_id="g1", description="A", urgency=0.5, importance=0.5),
            "g2": ManagedGoal(goal_id="g2", description="B", urgency=0.5, importance=0.5),
        }
        resolution = conflict_resolver.resolve_conflict(conflict, goals)
        assert resolution == ConflictResolution.SEQUENTIAL

    def test_get_state(self, conflict_resolver):
        state = conflict_resolver.get_state()
        assert 'total_conflicts' in state
        assert 'resolved_count' in state


# ─── GoalHierarchy Tests ──────────────────────────────────────────────────

class TestGoalHierarchy:
    """Tests for 3-level goal hierarchy (P3.37)."""

    def test_add_goal(self, goal_hierarchy):
        g = ManagedGoal(goal_id="g1", description="test", horizon=GoalHorizon.SHORT_TERM)
        assert goal_hierarchy.add_goal(g) is True
        assert goal_hierarchy.get_goal("g1") is not None

    def test_max_goals(self):
        h = GoalHierarchy(max_goals=3)
        for i in range(3):
            g = ManagedGoal(goal_id=f"g{i}", description=f"goal {i}")
            assert h.add_goal(g) is True
        # 4th should fail
        g = ManagedGoal(goal_id="g3", description="overflow")
        assert h.add_goal(g) is False

    def test_cleanup_allows_more(self):
        h = GoalHierarchy(max_goals=3)
        for i in range(3):
            g = ManagedGoal(goal_id=f"g{i}", description=f"goal {i}",
                           completed=True if i < 2 else False)
            g.created_at = time.time() - 7200  # 2 hours ago (eligible for cleanup)
            h.add_goal(g)
        # Adding a 4th should trigger cleanup of completed goals
        g = ManagedGoal(goal_id="g3", description="new goal")
        assert h.add_goal(g) is True

    def test_get_by_horizon(self, goal_hierarchy):
        g1 = ManagedGoal(goal_id="g1", description="long", horizon=GoalHorizon.LONG_TERM)
        g2 = ManagedGoal(goal_id="g2", description="short", horizon=GoalHorizon.SHORT_TERM)
        goal_hierarchy.add_goal(g1)
        goal_hierarchy.add_goal(g2)
        long_goals = goal_hierarchy.get_goals_by_horizon(GoalHorizon.LONG_TERM)
        assert len(long_goals) == 1
        assert long_goals[0].goal_id == "g1"

    def test_complete_goal(self, goal_hierarchy):
        g = ManagedGoal(goal_id="g1", description="test")
        goal_hierarchy.add_goal(g)
        assert goal_hierarchy.complete_goal("g1") is True
        assert goal_hierarchy.get_goal("g1").completed is True
        assert goal_hierarchy.get_goal("g1").active is False

    def test_complete_nonexistent(self, goal_hierarchy):
        assert goal_hierarchy.complete_goal("missing") is False

    def test_fail_goal_retries(self, goal_hierarchy):
        g = ManagedGoal(goal_id="g1", description="test", max_attempts=3)
        goal_hierarchy.add_goal(g)
        goal_hierarchy.fail_goal("g1", "first fail")
        # Should still be active (attempt 1/3)
        assert goal_hierarchy.get_goal("g1").active is True
        assert goal_hierarchy.get_goal("g1").attempts == 1

    def test_fail_goal_exhausted(self, goal_hierarchy):
        g = ManagedGoal(goal_id="g1", description="test", max_attempts=2)
        goal_hierarchy.add_goal(g)
        goal_hierarchy.fail_goal("g1", "fail 1")
        goal_hierarchy.fail_goal("g1", "fail 2")
        # Should be permanently failed
        assert goal_hierarchy.get_goal("g1").failed is True
        assert goal_hierarchy.get_goal("g1").active is False

    def test_parent_child_completion(self, goal_hierarchy):
        parent = ManagedGoal(goal_id="parent", description="parent",
                             horizon=GoalHorizon.MID_TERM)
        child1 = ManagedGoal(goal_id="c1", description="child 1",
                              parent_goal_id="parent")
        child2 = ManagedGoal(goal_id="c2", description="child 2",
                              parent_goal_id="parent")
        goal_hierarchy.add_goal(parent)
        goal_hierarchy.add_goal(child1)
        goal_hierarchy.add_goal(child2)

        goal_hierarchy.complete_goal("c1")
        assert goal_hierarchy.get_goal("parent").completed is False
        goal_hierarchy.complete_goal("c2")
        assert goal_hierarchy.get_goal("parent").completed is True

    def test_decompose_goal(self, goal_hierarchy):
        parent = ManagedGoal(goal_id="parent", description="Deploy",
                             horizon=GoalHorizon.LONG_TERM, domain="deploy",
                             urgency=0.8, importance=0.9)
        goal_hierarchy.add_goal(parent)
        children = goal_hierarchy.decompose_goal(
            "parent",
            ["Build image", "Run tests", "Push to registry"],
            GoalHorizon.MID_TERM,
        )
        assert len(children) == 3
        assert all(c.parent_goal_id == "parent" for c in children)
        assert all(c.horizon == GoalHorizon.MID_TERM for c in children)
        assert all(c.domain == "deploy" for c in children)
        # Parent should have child IDs
        assert len(goal_hierarchy.get_goal("parent").child_goal_ids) == 3

    def test_decompose_nonexistent(self, goal_hierarchy):
        result = goal_hierarchy.decompose_goal("missing", ["a", "b"])
        assert result == []

    def test_get_all_active(self, goal_hierarchy):
        g1 = ManagedGoal(goal_id="g1", description="active")
        g2 = ManagedGoal(goal_id="g2", description="done", completed=True, active=False)
        goal_hierarchy.add_goal(g1)
        goal_hierarchy.add_goal(g2)
        active = goal_hierarchy.get_all_active()
        assert len(active) == 1

    def test_get_state(self, goal_hierarchy):
        g = ManagedGoal(goal_id="g1", description="test")
        goal_hierarchy.add_goal(g)
        state = goal_hierarchy.get_state()
        assert state['total_goals'] == 1
        assert state['active_goals'] == 1
        assert 'by_horizon' in state
        assert 'top_goals' in state


# ─── GoalManager Tests ────────────────────────────────────────────────────

class TestGoalManager:
    """Tests for the GoalManager orchestrator."""

    def test_tick_empty(self, goal_manager):
        tasks = goal_manager.tick()
        assert tasks == []

    def test_tick_with_sensor_events(self, goal_manager):
        tasks = goal_manager.tick(
            sensor_events=[
                {'type': 'error', 'data': {'message': 'Build failed', 'domain': 'ci'}},
            ],
        )
        # Should generate at least one task from error event
        assert len(tasks) >= 1
        assert tasks[0].source == GoalSource.SENSOR_EVENT

    def test_tick_with_curiosity(self, goal_manager):
        tasks = goal_manager.tick(
            prediction_errors={'docker': 0.9},
        )
        assert len(tasks) >= 1
        assert tasks[0].source == GoalSource.CURIOSITY

    def test_tick_with_neuromodulation(self, goal_manager):
        # Add a goal first
        goal_manager.submit_user_goal("Deploy to production")
        tasks = goal_manager.tick(
            neuro_levels={'dopamine': 0.8, 'norepinephrine': 0.5, 'serotonin': 0.5},
        )
        assert len(tasks) >= 1

    def test_submit_user_goal(self, goal_manager):
        goal = goal_manager.submit_user_goal("Fix the bug")
        assert goal.source == GoalSource.USER_REQUEST
        assert goal.importance == 1.0

    def test_complete_goal(self, goal_manager):
        goal = goal_manager.submit_user_goal("Do something")
        goal_manager.complete_goal(goal.goal_id)
        retrieved = goal_manager.hierarchy.get_goal(goal.goal_id)
        assert retrieved.completed is True

    def test_fail_goal_records_failure(self, goal_manager):
        goal = goal_manager.submit_user_goal("Do something")
        goal_manager.fail_goal(goal.goal_id, "broken")
        # Goal should be retrying (under max_attempts)
        retrieved = goal_manager.hierarchy.get_goal(goal.goal_id)
        assert retrieved.attempts == 1

    def test_record_task_outcome_success(self, goal_manager):
        goal = goal_manager.submit_user_goal("Task")
        goal_manager.record_task_outcome(goal.goal_id, success=True)
        assert goal_manager.hierarchy.get_goal(goal.goal_id).completed is True

    def test_record_task_outcome_failure(self, goal_manager):
        goal = goal_manager.submit_user_goal("Task")
        goal_manager.record_task_outcome(goal.goal_id, success=False, reason="timeout")
        retrieved = goal_manager.hierarchy.get_goal(goal.goal_id)
        assert retrieved.attempts >= 1

    def test_decompose_goal(self, goal_manager):
        goal = goal_manager.submit_user_goal("Deploy system")
        children = goal_manager.decompose_goal(
            goal.goal_id,
            ["Build image", "Run tests", "Push"],
        )
        assert len(children) == 3
        # Children should be one horizon level down (MID -> SHORT)
        assert all(c.horizon == GoalHorizon.SHORT_TERM for c in children)

    def test_max_tasks_per_tick(self, goal_manager):
        for i in range(10):
            goal_manager.submit_user_goal(f"Task {i}")
        tasks = goal_manager.tick()
        assert len(tasks) <= 3  # max_tasks_per_tick

    def test_conflict_detection_in_tick(self, goal_manager):
        # Add conflicting goals
        g1 = ManagedGoal(goal_id="g1", description="Deploy now",
                         domain="prod", urgency=0.8)
        g2 = ManagedGoal(goal_id="g2", description="Fix tests first",
                         domain="prod", urgency=0.7)
        goal_manager.hierarchy.add_goal(g1)
        goal_manager.hierarchy.add_goal(g2)
        goal_manager.tick()
        # Should have detected conflict
        conflicts = goal_manager.conflict_resolver._conflicts
        assert len(conflicts) >= 1

    def test_get_state(self, goal_manager):
        goal_manager.submit_user_goal("Test goal")
        goal_manager.tick()
        state = goal_manager.get_state()
        assert 'hierarchy' in state
        assert 'generator' in state
        assert 'conflict_resolver' in state
        assert 'stats' in state
        assert state['stats']['total_ticks'] >= 1

    def test_goal_task_to_dict(self, goal_manager):
        goal_manager.submit_user_goal("Test")
        tasks = goal_manager.tick()
        if tasks:
            d = tasks[0].to_dict()
            assert 'goal_id' in d
            assert 'priority_score' in d
            assert 'source' in d

    def test_error_resilience(self, goal_manager):
        """GoalManager should not crash on bad input."""
        tasks = goal_manager.tick(
            sensor_events=[{'type': None, 'data': None}],
            prediction_errors=None,
            neuro_levels='invalid',
        )
        # Should handle gracefully (may return empty)
        assert isinstance(tasks, list)


# ─── Integration Tests ──────────────────────────────────────────────────

class TestGoalIntegration:
    """Integration tests combining multiple components."""

    def test_full_lifecycle(self, goal_manager):
        """Full goal lifecycle: create -> prioritize -> execute -> complete."""
        # 1. User submits goal
        goal = goal_manager.submit_user_goal("Deploy version 2.0")

        # 2. Decompose into sub-goals
        children = goal_manager.decompose_goal(
            goal.goal_id,
            ["Build Docker image", "Run integration tests", "Push to registry"],
        )
        assert len(children) == 3

        # 3. Tick to get prioritized tasks
        tasks = goal_manager.tick()
        assert len(tasks) > 0

        # 4. Complete children
        for child in children:
            goal_manager.complete_goal(child.goal_id)

        # 5. Parent should be auto-completed
        assert goal_manager.hierarchy.get_goal(goal.goal_id).completed is True

    def test_failure_triggers_root_cause_goal(self, goal_manager):
        """Repeated failures should generate a root-cause goal."""
        domain = "test_ci"
        # Record 3 failures
        for i in range(3):
            goal_manager.generator.record_failure(domain, f"failure {i}")

        # Tick should generate root-cause goal
        tasks = goal_manager.tick()
        root_cause_tasks = [t for t in tasks if 'root cause' in t.description.lower()]
        assert len(root_cause_tasks) >= 1

    def test_neuro_modulation_changes_ranking(self, goal_manager):
        """Neuromodulation should change goal rankings."""
        # Add two goals: one safe, one risky
        safe = ManagedGoal(
            goal_id="safe", description="Run routine check",
            expected_reward=0.2, urgency=0.3, importance=0.4,
        )
        risky = ManagedGoal(
            goal_id="risky", description="Try new deployment strategy",
            expected_reward=0.9, urgency=0.3, importance=0.4,
        )
        goal_manager.hierarchy.add_goal(safe)
        goal_manager.hierarchy.add_goal(risky)

        # With high dopamine, risky should rank higher
        tasks_high_da = goal_manager.tick(
            neuro_levels={'dopamine': 0.9, 'norepinephrine': 0.5, 'serotonin': 0.5},
        )
        risky_score_high_da = goal_manager.hierarchy.get_goal("risky").neuro_bias

        # Reset
        safe.neuro_bias = 0.0
        risky.neuro_bias = 0.0

        # With low dopamine, risky should rank lower
        tasks_low_da = goal_manager.tick(
            neuro_levels={'dopamine': 0.1, 'norepinephrine': 0.5, 'serotonin': 0.5},
        )
        risky_score_low_da = goal_manager.hierarchy.get_goal("risky").neuro_bias

        assert risky_score_high_da > risky_score_low_da

    def test_all_serializable(self, goal_manager):
        """All state should be JSON-serializable."""
        import json
        goal_manager.submit_user_goal("Test goal")
        goal_manager.tick()
        state = goal_manager.get_state()
        json_str = json.dumps(state)
        assert isinstance(json_str, str)

    def test_diverse_sources(self, goal_manager):
        """Goals from different sources should coexist."""
        # User request
        goal_manager.submit_user_goal("User task")
        # Sensor event
        goal_manager.tick(sensor_events=[
            {'type': 'error', 'data': {'message': 'fail', 'domain': 'ci'}},
        ])
        # Curiosity
        goal_manager.tick(prediction_errors={'docker': 0.8})

        active = goal_manager.hierarchy.get_all_active()
        sources = {g.source for g in active}
        assert GoalSource.USER_REQUEST in sources


# ─── YAML Configuration Tests ────────────────────────────────────────────

class TestGoalManagementYAML:
    """Tests for YAML configuration loading."""

    def test_from_yaml_full(self):
        config = {
            'goal_management': {
                'max_goals': 200,
                'failure_threshold': 5,
                'curiosity_pe_threshold': 0.3,
                'max_goals_per_tick': 5,
                'generation_cooldown_seconds': 30.0,
                'dopamine_risk_weight': 0.4,
                'ne_urgency_weight': 0.4,
                'serotonin_stability_weight': 0.3,
                'resource_conflict_threshold': 0.9,
                'auto_resolve_severity': 0.8,
                'max_tasks_per_tick': 5,
            },
        }
        gm = GoalManager.from_yaml(config)
        assert gm.hierarchy._max_goals == 200
        assert gm._max_tasks_per_tick == 5
        assert gm.generator._curiosity_pe_threshold == 0.3

    def test_from_yaml_empty(self):
        gm = GoalManager.from_yaml({})
        assert gm.hierarchy._max_goals == 100  # Default
        assert gm._max_tasks_per_tick == 3

    def test_from_yaml_partial(self):
        config = {
            'goal_management': {
                'max_goals': 75,
            },
        }
        gm = GoalManager.from_yaml(config)
        assert gm.hierarchy._max_goals == 75
        assert gm._max_tasks_per_tick == 3  # Default

    def test_from_yaml_functional(self):
        """YAML-configured manager should be functional."""
        config = {
            'goal_management': {
                'max_goals': 10,
                'curiosity_pe_threshold': 0.3,
                'generation_cooldown_seconds': 0.0,
            },
        }
        gm = GoalManager.from_yaml(config)
        goal = gm.submit_user_goal("Test from YAML")
        tasks = gm.tick()
        assert len(tasks) >= 1
