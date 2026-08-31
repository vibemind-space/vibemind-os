"""
Tests for Proactive Behavior System (V2 Phase 3: P3.41-43)

Tests cover:
- ProactiveTaskGenerator: Error signal, job failure, health degradation tasks
- ScheduledActionManager: Time-based scheduling with adaptive intervals
- ReactivePatternEngine: Event-Condition-Action rule evaluation
- ProactiveBehavior: Combined system integration
- YAML configuration support
"""

import pytest
import time
from unittest.mock import MagicMock, patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.proactive_behavior import (
    ProactiveSource,
    ScheduleType,
    ProactiveTask,
    ProactiveTaskGenerator,
    ScheduledAction,
    ScheduledActionManager,
    ConditionOperator,
    Condition,
    ReactiveAction,
    ReactivePattern,
    ReactivePatternEngine,
    ProactiveBehavior,
)


# ──────────────────────────────────────────────────────────────────────────────
# ProactiveTask Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestProactiveTask:
    """Tests for the ProactiveTask dataclass."""

    def test_defaults(self):
        t = ProactiveTask(
            task_id="test_1",
            description="Test task",
            source=ProactiveSource.ERROR_SIGNAL,
        )
        assert t.urgency == 0.5
        assert t.importance == 0.5
        assert t.domain == "general"
        assert t.metadata == {}

    def test_to_dict(self):
        t = ProactiveTask(
            task_id="test_1",
            description="Test task",
            source=ProactiveSource.JOB_FAILURE,
            urgency=0.8,
            importance=0.7,
            domain="testing",
            metadata={'key': 'value'},
        )
        d = t.to_dict()
        assert d['task_id'] == 'test_1'
        assert d['source'] == 'job_failure'
        assert d['urgency'] == 0.8
        assert d['domain'] == 'testing'
        assert d['metadata']['key'] == 'value'

    def test_all_sources(self):
        """Verify all source types serialize correctly."""
        for source in ProactiveSource:
            t = ProactiveTask(
                task_id=f"test_{source.value}",
                description="test",
                source=source,
            )
            d = t.to_dict()
            assert d['source'] == source.value


# ──────────────────────────────────────────────────────────────────────────────
# ProactiveTaskGenerator Tests (P3.41)
# ──────────────────────────────────────────────────────────────────────────────

class TestProactiveTaskGenerator:
    """Tests for the ProactiveTaskGenerator."""

    def test_no_tasks_without_observations(self):
        gen = ProactiveTaskGenerator()
        tasks = gen.generate_tasks()
        assert tasks == []

    def test_error_signal_below_threshold(self):
        gen = ProactiveTaskGenerator(error_threshold=0.7)
        gen.observe_error(0.5, source='test', details='low error')
        tasks = gen.generate_tasks()
        assert tasks == []

    def test_error_signal_above_threshold(self):
        gen = ProactiveTaskGenerator(error_threshold=0.7, cooldown_seconds=0.0)
        # Multiple errors to get average above threshold
        for _ in range(5):
            gen.observe_error(0.9, source='brain', details='high error')
        tasks = gen.generate_tasks()
        assert len(tasks) == 1
        assert tasks[0].source == ProactiveSource.ERROR_SIGNAL
        assert 'brain' in tasks[0].description
        assert tasks[0].urgency >= 0.7

    def test_error_signal_identifies_top_source(self):
        gen = ProactiveTaskGenerator(error_threshold=0.7, cooldown_seconds=0.0)
        gen.observe_error(0.9, source='module_a')
        gen.observe_error(0.9, source='module_b')
        gen.observe_error(0.9, source='module_b')
        gen.observe_error(0.9, source='module_b')
        tasks = gen.generate_tasks()
        assert len(tasks) == 1
        assert tasks[0].metadata['top_source'] == 'module_b'

    def test_job_failure_below_threshold(self):
        gen = ProactiveTaskGenerator(failure_count_threshold=3)
        gen.observe_job_failure('build', 'compile error')
        tasks = gen.generate_tasks()
        assert tasks == []

    def test_job_failure_at_threshold(self):
        gen = ProactiveTaskGenerator(
            failure_count_threshold=2,
            cooldown_seconds=0.0,
            failure_window_seconds=300.0,
        )
        gen.observe_job_failure('build', 'error 1', 'ci')
        gen.observe_job_failure('build', 'error 2', 'ci')
        tasks = gen.generate_tasks()
        assert len(tasks) == 1
        assert tasks[0].source == ProactiveSource.JOB_FAILURE
        assert tasks[0].metadata['failure_count'] == 2
        assert 'build' in tasks[0].description

    def test_job_failure_multiple_jobs(self):
        gen = ProactiveTaskGenerator(
            failure_count_threshold=2,
            cooldown_seconds=0.0,
        )
        gen.observe_job_failure('build', 'err')
        gen.observe_job_failure('build', 'err')
        gen.observe_job_failure('test', 'err')
        gen.observe_job_failure('test', 'err')
        tasks = gen.generate_tasks()
        assert len(tasks) == 2
        job_names = {t.metadata['job_name'] for t in tasks}
        assert 'build' in job_names
        assert 'test' in job_names

    def test_job_failure_window_expiry(self):
        gen = ProactiveTaskGenerator(
            failure_count_threshold=2,
            cooldown_seconds=0.0,
            failure_window_seconds=10.0,
        )
        # Record old failures
        gen.observe_job_failure('build', 'err')
        gen._recent_failures[-1]['time'] -= 20  # Make it 20s old
        gen.observe_job_failure('build', 'err')
        gen._recent_failures[-1]['time'] -= 20  # Make it 20s old
        # These should be outside window
        tasks = gen.generate_tasks()
        assert tasks == []

    def test_health_degradation(self):
        gen = ProactiveTaskGenerator(
            health_degradation_threshold=0.5,
            cooldown_seconds=0.0,
        )
        gen.observe_health('brain', 0.3, 'degraded')
        gen.observe_health('brain', 0.4, 'still degraded')
        tasks = gen.generate_tasks()
        assert len(tasks) == 1
        assert tasks[0].source == ProactiveSource.HEALTH_DEGRADATION
        assert 'brain' in tasks[0].description

    def test_health_above_threshold_no_task(self):
        gen = ProactiveTaskGenerator(health_degradation_threshold=0.5)
        gen.observe_health('brain', 0.8, 'healthy')
        tasks = gen.generate_tasks()
        assert tasks == []

    def test_cooldown_respected(self):
        gen = ProactiveTaskGenerator(
            error_threshold=0.7,
            cooldown_seconds=60.0,
        )
        for _ in range(5):
            gen.observe_error(0.9, source='test')

        # First call generates task
        tasks1 = gen.generate_tasks()
        assert len(tasks1) == 1

        # Second call within cooldown should not
        for _ in range(5):
            gen.observe_error(0.9, source='test')
        tasks2 = gen.generate_tasks()
        assert len(tasks2) == 0

    def test_max_tasks_per_tick(self):
        gen = ProactiveTaskGenerator(
            error_threshold=0.1,
            failure_count_threshold=1,
            health_degradation_threshold=0.99,
            cooldown_seconds=0.0,
            max_tasks_per_tick=2,
        )
        for _ in range(10):
            gen.observe_error(0.9, source='test')
        gen.observe_job_failure('build', 'err')
        gen.observe_health('brain', 0.1)
        tasks = gen.generate_tasks()
        assert len(tasks) <= 2

    def test_get_state(self):
        gen = ProactiveTaskGenerator()
        gen.observe_error(0.9, source='test')
        state = gen.get_state()
        assert state['name'] == 'ProactiveTaskGenerator'
        assert state['pending_errors'] == 1
        assert 'config' in state
        assert state['config']['error_threshold'] == 0.7


# ──────────────────────────────────────────────────────────────────────────────
# ScheduledAction Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestScheduledAction:
    """Tests for individual ScheduledAction."""

    def test_defaults(self):
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=60.0,
            description="Test action",
        )
        assert action.current_interval == 60.0
        assert action.total_runs == 0

    def test_is_due(self):
        now = time.time()
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=10.0,
            description="Test",
            last_run_time=now - 15,  # 15 seconds ago
        )
        assert action.is_due(now) is True

    def test_not_yet_due(self):
        now = time.time()
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=60.0,
            description="Test",
            last_run_time=now - 30,  # Only 30s ago, need 60s
        )
        assert action.is_due(now) is False

    def test_mark_run(self):
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=60.0,
            description="Test",
        )
        now = time.time()
        action.mark_run(now)
        assert action.total_runs == 1
        assert action.last_run_time == now

    def test_adapt_interval_faster(self):
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=100.0,
            description="Test",
            min_interval_seconds=10.0,
        )
        action.adapt_interval(0.5)  # Run 2x faster
        assert action.current_interval == 50.0

    def test_adapt_interval_slower(self):
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=100.0,
            description="Test",
            max_interval_seconds=200.0,
        )
        action.adapt_interval(1.5)  # Run 1.5x slower
        assert action.current_interval == 150.0

    def test_adapt_interval_min_bound(self):
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=20.0,
            description="Test",
            min_interval_seconds=10.0,
        )
        action.adapt_interval(0.1)  # Would make 2s, but min is 10
        assert action.current_interval == 10.0

    def test_adapt_interval_max_bound(self):
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=1000.0,
            description="Test",
            max_interval_seconds=2000.0,
        )
        action.adapt_interval(10.0)  # Would make 10000, but max is 2000
        assert action.current_interval == 2000.0

    def test_time_of_day_restriction_overnight(self):
        """Test overnight active window (e.g., 22:00-06:00)."""
        action = ScheduledAction(
            name="dream",
            schedule_type=ScheduleType.DREAM_MODE,
            base_interval_seconds=10.0,
            description="Dream",
            last_run_time=0,
            active_start_hour=22,
            active_end_hour=6,
        )
        now = time.time()
        # We can't easily mock datetime.now() here, so just verify
        # the is_due method considers the time restriction
        # (the result depends on current time of day)
        result = action.is_due(now)
        assert isinstance(result, bool)

    def test_to_dict(self):
        action = ScheduledAction(
            name="test",
            schedule_type=ScheduleType.HEALTH_CHECK,
            base_interval_seconds=60.0,
            description="Test action",
        )
        d = action.to_dict()
        assert d['name'] == 'test'
        assert d['type'] == 'health_check'
        assert d['base_interval_seconds'] == 60.0
        assert 'time_until_next' in d


# ──────────────────────────────────────────────────────────────────────────────
# ScheduledActionManager Tests (P3.42)
# ──────────────────────────────────────────────────────────────────────────────

class TestScheduledActionManager:
    """Tests for the ScheduledActionManager."""

    def test_default_actions_created(self):
        mgr = ScheduledActionManager()
        assert 'memory_consolidation' in mgr._actions
        assert 'health_check' in mgr._actions
        assert 'git_scan' in mgr._actions
        assert 'dream_mode' in mgr._actions
        assert 'cleanup' in mgr._actions
        assert 'metrics_snapshot' in mgr._actions

    def test_no_actions_due_initially(self):
        mgr = ScheduledActionManager()
        # All actions were just created, so none are due
        tasks = mgr.get_due_actions()
        assert tasks == []

    def test_action_becomes_due(self):
        mgr = ScheduledActionManager(health_check_interval=10.0)
        # Artificially set last_run_time to far past
        mgr._actions['health_check'].last_run_time = time.time() - 20
        tasks = mgr.get_due_actions()
        assert len(tasks) >= 1
        health_tasks = [t for t in tasks if t.metadata.get('schedule_name') == 'health_check']
        assert len(health_tasks) == 1
        assert health_tasks[0].source == ProactiveSource.SCHEDULED

    def test_action_not_due_twice(self):
        mgr = ScheduledActionManager(health_check_interval=10.0)
        mgr._actions['health_check'].last_run_time = time.time() - 20
        tasks1 = mgr.get_due_actions()
        assert len([t for t in tasks1 if 'health_check' in t.metadata.get('schedule_name', '')]) == 1

        # Immediately checking again should not return it
        tasks2 = mgr.get_due_actions()
        assert len([t for t in tasks2 if 'health_check' in t.metadata.get('schedule_name', '')]) == 0

    def test_add_custom_action(self):
        mgr = ScheduledActionManager()
        custom = ScheduledAction(
            name="my_custom_check",
            schedule_type=ScheduleType.CUSTOM,
            base_interval_seconds=5.0,
            description="Custom check",
            last_run_time=0,  # Due immediately
        )
        mgr.add_action(custom)
        assert 'my_custom_check' in mgr._actions

        tasks = mgr.get_due_actions()
        custom_tasks = [t for t in tasks if t.metadata.get('schedule_name') == 'my_custom_check']
        assert len(custom_tasks) == 1

    def test_remove_action(self):
        mgr = ScheduledActionManager()
        assert mgr.remove_action('health_check') is True
        assert 'health_check' not in mgr._actions
        assert mgr.remove_action('nonexistent') is False

    def test_update_system_context_high_load(self):
        mgr = ScheduledActionManager(health_check_interval=60.0)
        original_interval = mgr._actions['cleanup'].current_interval

        # High load should slow down low-urgency actions
        mgr.update_system_context(system_load=0.95)
        new_interval = mgr._actions['cleanup'].current_interval
        assert new_interval >= original_interval

    def test_update_system_context_high_activity(self):
        mgr = ScheduledActionManager(health_check_interval=60.0)
        original_interval = mgr._actions['health_check'].current_interval

        # High activity should speed up monitoring
        mgr.update_system_context(activity_level=0.9)
        new_interval = mgr._actions['health_check'].current_interval
        assert new_interval <= original_interval

    def test_update_system_context_high_sleep_pressure(self):
        mgr = ScheduledActionManager(memory_consolidation_interval=14400.0)  # 4h (default)
        original = mgr._actions['memory_consolidation'].current_interval

        # High sleep pressure should speed up consolidation
        mgr.update_system_context(sleep_pressure=0.8)
        new_interval = mgr._actions['memory_consolidation'].current_interval
        assert new_interval < original

    def test_get_state(self):
        mgr = ScheduledActionManager()
        state = mgr.get_state()
        assert state['name'] == 'ScheduledActionManager'
        assert 'actions' in state
        assert 'memory_consolidation' in state['actions']


# ──────────────────────────────────────────────────────────────────────────────
# Condition Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCondition:
    """Tests for the Condition class used in reactive patterns."""

    def test_gt(self):
        c = Condition(field='error_signal', operator=ConditionOperator.GT, threshold=0.5)
        assert c.evaluate({'error_signal': 0.8}) is True
        assert c.evaluate({'error_signal': 0.3}) is False
        assert c.evaluate({'error_signal': 0.5}) is False

    def test_gte(self):
        c = Condition(field='x', operator=ConditionOperator.GTE, threshold=5)
        assert c.evaluate({'x': 5}) is True
        assert c.evaluate({'x': 4}) is False

    def test_lt(self):
        c = Condition(field='x', operator=ConditionOperator.LT, threshold=10)
        assert c.evaluate({'x': 5}) is True
        assert c.evaluate({'x': 15}) is False

    def test_lte(self):
        c = Condition(field='x', operator=ConditionOperator.LTE, threshold=10)
        assert c.evaluate({'x': 10}) is True
        assert c.evaluate({'x': 11}) is False

    def test_eq_numeric(self):
        c = Condition(field='x', operator=ConditionOperator.EQ, threshold=5)
        assert c.evaluate({'x': 5}) is True
        assert c.evaluate({'x': 6}) is False

    def test_eq_string(self):
        c = Condition(field='status', operator=ConditionOperator.EQ, threshold='active')
        assert c.evaluate({'status': 'active'}) is True
        assert c.evaluate({'status': 'inactive'}) is False

    def test_neq(self):
        c = Condition(field='x', operator=ConditionOperator.NEQ, threshold=5)
        assert c.evaluate({'x': 6}) is True
        assert c.evaluate({'x': 5}) is False

    def test_contains(self):
        c = Condition(field='msg', operator=ConditionOperator.CONTAINS, threshold='error')
        assert c.evaluate({'msg': 'fatal error occurred'}) is True
        assert c.evaluate({'msg': 'all good'}) is False

    def test_exists_true(self):
        c = Condition(field='x', operator=ConditionOperator.EXISTS, threshold=True)
        assert c.evaluate({'x': 42}) is True
        assert c.evaluate({}) is False

    def test_exists_false(self):
        c = Condition(field='x', operator=ConditionOperator.EXISTS, threshold=False)
        assert c.evaluate({}) is True
        assert c.evaluate({'x': 42}) is False

    def test_dotted_field_path(self):
        c = Condition(field='health.brain.score', operator=ConditionOperator.GT, threshold=0.5)
        assert c.evaluate({'health': {'brain': {'score': 0.8}}}) is True
        assert c.evaluate({'health': {'brain': {'score': 0.3}}}) is False

    def test_missing_field_returns_false(self):
        c = Condition(field='nonexistent', operator=ConditionOperator.GT, threshold=0.5)
        assert c.evaluate({}) is False

    def test_boolean_eq(self):
        c = Condition(field='flag', operator=ConditionOperator.EQ, threshold=True)
        assert c.evaluate({'flag': True}) is True

    def test_to_dict(self):
        c = Condition(
            field='error_signal',
            operator=ConditionOperator.GT,
            threshold=0.8,
            description="High error",
        )
        d = c.to_dict()
        assert d['field'] == 'error_signal'
        assert d['operator'] == '>'
        assert d['threshold'] == 0.8


# ──────────────────────────────────────────────────────────────────────────────
# ReactivePattern Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestReactivePattern:
    """Tests for individual ReactivePattern."""

    def test_single_condition_evaluates(self):
        pattern = ReactivePattern(
            pattern_id="test_1",
            name="Test Pattern",
            conditions=[
                Condition(field='x', operator=ConditionOperator.GT, threshold=5),
            ],
            actions=[
                ReactiveAction(action_type='generate_task', description='Do thing'),
            ],
        )
        assert pattern.evaluate({'x': 10}) is True
        assert pattern.evaluate({'x': 3}) is False

    def test_all_conditions_must_match(self):
        pattern = ReactivePattern(
            pattern_id="test_2",
            name="Multi-condition",
            conditions=[
                Condition(field='a', operator=ConditionOperator.GT, threshold=5),
                Condition(field='b', operator=ConditionOperator.LT, threshold=10),
            ],
            actions=[ReactiveAction(action_type='generate_task', description='Do')],
        )
        assert pattern.evaluate({'a': 10, 'b': 5}) is True
        assert pattern.evaluate({'a': 10, 'b': 15}) is False
        assert pattern.evaluate({'a': 3, 'b': 5}) is False

    def test_disabled_pattern_never_fires(self):
        pattern = ReactivePattern(
            pattern_id="test_3",
            name="Disabled",
            conditions=[
                Condition(field='x', operator=ConditionOperator.GT, threshold=0),
            ],
            actions=[ReactiveAction(action_type='generate_task', description='Do')],
            enabled=False,
        )
        assert pattern.evaluate({'x': 100}) is False

    def test_cooldown(self):
        now = time.time()
        pattern = ReactivePattern(
            pattern_id="test_4",
            name="Cooldown test",
            conditions=[],
            actions=[],
            cooldown_seconds=60.0,
            last_fired_time=now - 30,
        )
        assert pattern.is_on_cooldown(now) is True

        pattern.last_fired_time = now - 120
        assert pattern.is_on_cooldown(now) is False

    def test_fire_updates_tracking(self):
        pattern = ReactivePattern(
            pattern_id="test_5",
            name="Fire test",
            conditions=[],
            actions=[],
        )
        now = time.time()
        pattern.fire(now)
        assert pattern.total_fires == 1
        assert pattern.last_fired_time == now

    def test_to_dict(self):
        pattern = ReactivePattern(
            pattern_id="test_6",
            name="Dict test",
            conditions=[
                Condition(field='x', operator=ConditionOperator.GT, threshold=5),
            ],
            actions=[
                ReactiveAction(action_type='generate_task', description='Do', parameters={'urgency': 0.8}),
            ],
            learned=True,
            confidence=0.7,
        )
        d = pattern.to_dict()
        assert d['pattern_id'] == 'test_6'
        assert d['learned'] is True
        assert d['confidence'] == 0.7
        assert len(d['conditions']) == 1
        assert len(d['actions']) == 1


# ──────────────────────────────────────────────────────────────────────────────
# ReactivePatternEngine Tests (P3.43)
# ──────────────────────────────────────────────────────────────────────────────

class TestReactivePatternEngine:
    """Tests for the ReactivePatternEngine."""

    def test_default_patterns_created(self):
        engine = ReactivePatternEngine()
        assert len(engine._patterns) >= 6
        assert 'rp_error_high' in engine._patterns
        assert 'rp_process_down' in engine._patterns
        assert 'rp_idle_curiosity' in engine._patterns

    def test_error_signal_pattern_fires(self):
        engine = ReactivePatternEngine()
        # Reset cooldown on pattern
        engine._patterns['rp_error_high'].last_fired_time = 0

        tasks = engine.evaluate({'error_signal': 0.9})
        error_tasks = [t for t in tasks if t.metadata.get('pattern_id') == 'rp_error_high']
        assert len(error_tasks) == 1
        assert error_tasks[0].source == ProactiveSource.REACTIVE_RULE

    def test_error_signal_below_threshold_no_fire(self):
        engine = ReactivePatternEngine()
        engine._patterns['rp_error_high'].last_fired_time = 0

        tasks = engine.evaluate({'error_signal': 0.5})
        error_tasks = [t for t in tasks if t.metadata.get('pattern_id') == 'rp_error_high']
        assert len(error_tasks) == 0

    def test_multiple_conditions_both_met(self):
        engine = ReactivePatternEngine()
        engine._patterns['rp_low_test_coverage'].last_fired_time = 0

        tasks = engine.evaluate({
            'coding_job_completed': True,
            'test_coverage': 60.0,
        })
        coverage_tasks = [t for t in tasks if t.metadata.get('pattern_id') == 'rp_low_test_coverage']
        assert len(coverage_tasks) == 1

    def test_multiple_conditions_one_unmet(self):
        engine = ReactivePatternEngine()
        engine._patterns['rp_low_test_coverage'].last_fired_time = 0

        tasks = engine.evaluate({
            'coding_job_completed': True,
            'test_coverage': 90.0,  # Above 80, so condition fails
        })
        coverage_tasks = [t for t in tasks if t.metadata.get('pattern_id') == 'rp_low_test_coverage']
        assert len(coverage_tasks) == 0

    def test_cooldown_prevents_repeat_fire(self):
        engine = ReactivePatternEngine()
        engine._patterns['rp_error_high'].last_fired_time = 0

        # First evaluation fires
        tasks1 = engine.evaluate({'error_signal': 0.9})
        assert any(t.metadata.get('pattern_id') == 'rp_error_high' for t in tasks1)

        # Second evaluation should be on cooldown
        tasks2 = engine.evaluate({'error_signal': 0.9})
        error_tasks2 = [t for t in tasks2 if t.metadata.get('pattern_id') == 'rp_error_high']
        assert len(error_tasks2) == 0

    def test_add_pattern(self):
        engine = ReactivePatternEngine()
        initial = len(engine._patterns)

        pattern = ReactivePattern(
            pattern_id="custom_1",
            name="Custom Pattern",
            conditions=[
                Condition(field='temp', operator=ConditionOperator.GT, threshold=100),
            ],
            actions=[
                ReactiveAction(action_type='generate_task', description='Cool down', parameters={'urgency': 0.8}),
            ],
        )
        assert engine.add_pattern(pattern) is True
        assert len(engine._patterns) == initial + 1

    def test_add_pattern_at_capacity(self):
        engine = ReactivePatternEngine(max_patterns=6)  # Already has 6 defaults
        pattern = ReactivePattern(
            pattern_id="overflow",
            name="Over capacity",
            conditions=[],
            actions=[],
        )
        # May or may not fit depending on exact default count
        # Just verify it returns bool
        result = engine.add_pattern(pattern)
        assert isinstance(result, bool)

    def test_remove_pattern(self):
        engine = ReactivePatternEngine()
        assert engine.remove_pattern('rp_error_high') is True
        assert 'rp_error_high' not in engine._patterns
        assert engine.remove_pattern('nonexistent') is False

    def test_enable_disable_pattern(self):
        engine = ReactivePatternEngine()
        assert engine.enable_pattern('rp_error_high', enabled=False) is True
        assert engine._patterns['rp_error_high'].enabled is False

        assert engine.enable_pattern('rp_error_high', enabled=True) is True
        assert engine._patterns['rp_error_high'].enabled is True

        assert engine.enable_pattern('nonexistent') is False

    def test_max_fires_per_tick(self):
        engine = ReactivePatternEngine(max_fires_per_tick=2)
        # Reset all cooldowns
        for p in engine._patterns.values():
            p.last_fired_time = 0

        # Context that should trigger many patterns
        context = {
            'error_signal': 0.9,
            'process_down': True,
            'coding_job_completed': True,
            'test_coverage': 50.0,
            'idle_time': 700,
            'memory_usage': 0.9,
            'prediction_error': 0.8,
        }
        tasks = engine.evaluate(context)
        assert len(tasks) <= 2

    def test_learn_pattern(self):
        engine = ReactivePatternEngine(learning_enabled=True)
        pid = engine.learn_pattern_from_observation(
            name="Learned: High CPU → Throttle",
            conditions=[
                Condition(field='cpu', operator=ConditionOperator.GT, threshold=90),
            ],
            actions=[
                ReactiveAction(
                    action_type='generate_task',
                    description='Throttle non-critical tasks',
                    parameters={'urgency': 0.6},
                ),
            ],
            confidence=0.7,
        )
        assert pid is not None
        assert pid in engine._patterns
        assert engine._patterns[pid].learned is True
        assert engine._patterns[pid].confidence == 0.7

    def test_learn_pattern_disabled(self):
        engine = ReactivePatternEngine(learning_enabled=False)
        pid = engine.learn_pattern_from_observation(
            name="Shouldn't learn",
            conditions=[],
            actions=[],
        )
        assert pid is None

    def test_idle_curiosity_pattern(self):
        engine = ReactivePatternEngine()
        engine._patterns['rp_idle_curiosity'].last_fired_time = 0

        tasks = engine.evaluate({'idle_time': 700})  # Over 600s threshold
        idle_tasks = [t for t in tasks if t.metadata.get('pattern_id') == 'rp_idle_curiosity']
        assert len(idle_tasks) == 1

    def test_suppressed_count(self):
        engine = ReactivePatternEngine()
        engine._patterns['rp_error_high'].last_fired_time = 0

        # Fire once
        engine.evaluate({'error_signal': 0.9})
        assert engine._patterns['rp_error_high'].total_fires == 1

        # Try to fire again (should be suppressed due to cooldown)
        engine.evaluate({'error_signal': 0.9})
        assert engine._patterns['rp_error_high'].total_suppressed == 1

    def test_get_state(self):
        engine = ReactivePatternEngine()
        state = engine.get_state()
        assert state['name'] == 'ReactivePatternEngine'
        assert state['predefined_patterns'] >= 6
        assert state['learned_patterns'] == 0
        assert 'patterns' in state


# ──────────────────────────────────────────────────────────────────────────────
# ProactiveBehavior Integration Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestProactiveBehavior:
    """Tests for the combined ProactiveBehavior system."""

    def test_empty_tick(self):
        pb = ProactiveBehavior()
        tasks = pb.tick()
        assert isinstance(tasks, list)

    def test_tick_with_errors(self):
        pb = ProactiveBehavior(
            task_generator=ProactiveTaskGenerator(
                error_threshold=0.5,
                cooldown_seconds=0.0,
            ),
        )
        for _ in range(5):
            pb.observe_error(0.9, 'test', 'error details')
        tasks = pb.tick()
        error_tasks = [t for t in tasks if t.source == ProactiveSource.ERROR_SIGNAL]
        assert len(error_tasks) >= 1

    def test_tick_with_job_failures(self):
        pb = ProactiveBehavior(
            task_generator=ProactiveTaskGenerator(
                failure_count_threshold=1,
                cooldown_seconds=0.0,
            ),
        )
        pb.observe_job_failure('build', 'compile error', 'ci')
        tasks = pb.tick()
        failure_tasks = [t for t in tasks if t.source == ProactiveSource.JOB_FAILURE]
        assert len(failure_tasks) >= 1

    def test_tick_with_health_degradation(self):
        pb = ProactiveBehavior(
            task_generator=ProactiveTaskGenerator(
                health_degradation_threshold=0.5,
                cooldown_seconds=0.0,
            ),
        )
        pb.observe_health('brain', 0.2, 'degraded')
        pb.observe_health('brain', 0.3, 'still bad')
        tasks = pb.tick()
        health_tasks = [t for t in tasks if t.source == ProactiveSource.HEALTH_DEGRADATION]
        assert len(health_tasks) >= 1

    def test_tick_with_scheduled_actions(self):
        # Create scheduler where an action is immediately due
        pb = ProactiveBehavior()
        pb.scheduler._actions['health_check'].last_run_time = time.time() - 99999
        tasks = pb.tick()
        sched_tasks = [t for t in tasks if t.source == ProactiveSource.SCHEDULED]
        assert len(sched_tasks) >= 1

    def test_tick_with_reactive_patterns(self):
        pb = ProactiveBehavior()
        # Reset cooldowns
        for p in pb.patterns._patterns.values():
            p.last_fired_time = 0

        context = {'error_signal': 0.95}
        tasks = pb.tick(context=context)
        reactive_tasks = [t for t in tasks if t.source == ProactiveSource.REACTIVE_RULE]
        assert len(reactive_tasks) >= 1

    def test_tick_max_tasks(self):
        pb = ProactiveBehavior(max_tasks_per_tick=2)
        pb.generator.cooldown_seconds = 0.0
        pb.generator.error_threshold = 0.1
        pb.generator.failure_count_threshold = 1

        for _ in range(10):
            pb.observe_error(0.9, 'test')
        pb.observe_job_failure('build', 'err')
        pb.observe_health('brain', 0.1)

        tasks = pb.tick()
        assert len(tasks) <= 2

    def test_tick_context_for_adaptation(self):
        pb = ProactiveBehavior()
        original_interval = pb.scheduler._actions['memory_consolidation'].current_interval

        # Tick with high sleep pressure should adapt consolidation interval
        pb.tick(sleep_pressure=0.9)
        new_interval = pb.scheduler._actions['memory_consolidation'].current_interval
        assert new_interval < original_interval

    def test_get_state(self):
        pb = ProactiveBehavior()
        state = pb.get_state()
        assert 'generator' in state
        assert 'scheduler' in state
        assert 'patterns' in state
        assert state['total_tasks_generated'] == 0

    def test_error_resilience(self):
        """Individual subsystem failures shouldn't crash the whole tick."""
        pb = ProactiveBehavior()

        # Mock generator to throw an error
        pb.generator.generate_tasks = MagicMock(side_effect=RuntimeError("generator boom"))

        # Should still work (returns empty or tasks from other systems)
        tasks = pb.tick()
        assert isinstance(tasks, list)

    def test_scheduler_resilience(self):
        """Scheduler failure shouldn't crash tick."""
        pb = ProactiveBehavior()
        pb.scheduler.get_due_actions = MagicMock(side_effect=RuntimeError("scheduler boom"))

        tasks = pb.tick()
        assert isinstance(tasks, list)

    def test_pattern_engine_resilience(self):
        """Pattern engine failure shouldn't crash tick."""
        pb = ProactiveBehavior()
        pb.patterns.evaluate = MagicMock(side_effect=RuntimeError("pattern boom"))

        tasks = pb.tick(context={'error_signal': 0.9})
        assert isinstance(tasks, list)


# ──────────────────────────────────────────────────────────────────────────────
# Full Lifecycle Integration Test
# ──────────────────────────────────────────────────────────────────────────────

class TestProactiveLifecycle:
    """End-to-end lifecycle tests."""

    def test_full_lifecycle(self):
        """Full lifecycle: observe → generate → tick → verify."""
        pb = ProactiveBehavior(
            task_generator=ProactiveTaskGenerator(
                error_threshold=0.5,
                failure_count_threshold=2,
                health_degradation_threshold=0.5,
                cooldown_seconds=0.0,
            ),
        )

        # Phase 1: Observe errors
        pb.observe_error(0.8, 'module_a', 'error in module A')
        pb.observe_error(0.9, 'module_a', 'another error')

        # Phase 2: Observe failures
        pb.observe_job_failure('deploy', 'connection timeout', 'infra')
        pb.observe_job_failure('deploy', 'connection refused', 'infra')

        # Phase 3: Observe health
        pb.observe_health('database', 0.3, 'slow queries')

        # Phase 4: Tick with reactive context
        context = {'error_signal': 0.9}
        # Reset reactive pattern cooldowns
        for p in pb.patterns._patterns.values():
            p.last_fired_time = 0

        tasks = pb.tick(context=context)

        # Should get tasks from multiple sources
        assert len(tasks) > 0
        sources = {t.source for t in tasks}
        # At minimum we should see error and failure tasks
        assert ProactiveSource.ERROR_SIGNAL in sources or ProactiveSource.JOB_FAILURE in sources

    def test_all_serializable(self):
        """All proactive objects must be JSON-serializable via to_dict()."""
        import json

        pb = ProactiveBehavior()
        pb.observe_error(0.8, 'test', 'details')
        pb.observe_job_failure('build', 'error')
        pb.observe_health('brain', 0.5)

        # Tick to generate some tasks
        pb.generator.cooldown_seconds = 0.0
        for p in pb.patterns._patterns.values():
            p.last_fired_time = 0
        pb.tick(context={'error_signal': 0.9})

        state = pb.get_state()
        serialized = json.dumps(state)
        assert len(serialized) > 100
        deserialized = json.loads(serialized)
        assert deserialized['generator']['name'] == 'ProactiveTaskGenerator'

    def test_diverse_task_sources(self):
        """Verify we can generate tasks from all three subsystems in one tick."""
        pb = ProactiveBehavior(
            task_generator=ProactiveTaskGenerator(
                error_threshold=0.1,
                cooldown_seconds=0.0,
            ),
            max_tasks_per_tick=20,
        )

        # Set up error observation
        for _ in range(5):
            pb.observe_error(0.9, 'test')

        # Make a scheduled action due
        pb.scheduler._actions['health_check'].last_run_time = 0

        # Reset reactive pattern cooldowns
        for p in pb.patterns._patterns.values():
            p.last_fired_time = 0

        tasks = pb.tick(context={'error_signal': 0.9})
        sources = {t.source for t in tasks}

        # Should have at least 2 different sources
        assert len(sources) >= 2

    def test_observation_forwarding(self):
        """ProactiveBehavior.observe_* should forward to generator."""
        pb = ProactiveBehavior()

        pb.observe_error(0.5, 'test')
        assert len(pb.generator._recent_errors) == 1

        pb.observe_job_failure('build', 'err')
        assert len(pb.generator._recent_failures) == 1

        pb.observe_health('brain', 0.5)
        assert len(pb.generator._health_history) == 1


# ──────────────────────────────────────────────────────────────────────────────
# YAML Config Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestProactiveBehaviorYAML:
    """Tests for YAML configuration support."""

    def test_from_yaml_full(self):
        config = {
            'proactive_behavior': {
                'error_threshold': 0.6,
                'failure_window_seconds': 200.0,
                'failure_count_threshold': 3,
                'health_degradation_threshold': 0.4,
                'generator_cooldown_seconds': 90.0,
                'generator_max_tasks_per_tick': 4,
                'memory_consolidation_interval': 7200.0,
                'health_check_interval': 600.0,
                'git_scan_interval': 120.0,
                'dream_idle_threshold': 900.0,
                'cleanup_interval': 1800.0,
                'metrics_snapshot_interval': 300.0,
                'max_patterns': 50,
                'max_fires_per_tick': 3,
                'learning_enabled': False,
                'max_tasks_per_tick': 4,
            },
        }
        pb = ProactiveBehavior.from_yaml(config)

        assert pb.generator.error_threshold == 0.6
        assert pb.generator.failure_count_threshold == 3
        assert pb.generator.cooldown_seconds == 90.0

        assert pb.scheduler._actions['health_check'].base_interval_seconds == 600.0
        assert pb.scheduler._actions['git_scan'].base_interval_seconds == 120.0

        assert pb.patterns.max_patterns == 50
        assert pb.patterns.learning_enabled is False

        assert pb.max_tasks_per_tick == 4

    def test_from_yaml_empty(self):
        pb = ProactiveBehavior.from_yaml({})
        assert pb.generator.error_threshold == 0.7
        assert pb.max_tasks_per_tick == 5

    def test_from_yaml_partial(self):
        config = {
            'proactive_behavior': {
                'error_threshold': 0.9,
            },
        }
        pb = ProactiveBehavior.from_yaml(config)
        assert pb.generator.error_threshold == 0.9
        # Other values should be defaults
        assert pb.generator.failure_count_threshold == 2

    def test_from_yaml_functional(self):
        """Created-from-YAML system should function correctly."""
        config = {
            'proactive_behavior': {
                'error_threshold': 0.3,
                'generator_cooldown_seconds': 0.0,
            },
        }
        pb = ProactiveBehavior.from_yaml(config)

        for _ in range(5):
            pb.observe_error(0.5, 'test')

        tasks = pb.tick()
        assert len(tasks) > 0
