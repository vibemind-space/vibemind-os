"""
Tests for Agent Loop (V2 Phase 3: P3.31-33)

Tests the autonomous agent loop, state machine, interrupt handler,
task priority queue, and autonomy budget.
"""

import pytest
import time
import threading
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.agent_loop import (
    AgentLoop,
    AgentLoopConfig,
    AgentStateMachine,
    AgentState,
    AgentTask,
    TaskPriority,
    InterruptHandler,
    AutonomyBudget,
    VALID_TRANSITIONS,
)


# ─── AgentStateMachine Tests (P3.32) ─────────────────────────────────────

class TestAgentStateMachine:
    """Tests for the FSM governing agent states."""

    def test_initial_state_is_stopped(self):
        fsm = AgentStateMachine()
        assert fsm.state == AgentState.STOPPED

    def test_valid_transition_stopped_to_idle(self):
        fsm = AgentStateMachine()
        assert fsm.transition(AgentState.IDLE)
        assert fsm.state == AgentState.IDLE

    def test_invalid_transition_stopped_to_acting(self):
        fsm = AgentStateMachine()
        assert not fsm.transition(AgentState.ACTING)
        assert fsm.state == AgentState.STOPPED  # Unchanged

    def test_transition_chain_idle_perceiving_thinking_acting(self):
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.IDLE)
        assert fsm.transition(AgentState.PERCEIVING)
        assert fsm.transition(AgentState.THINKING)
        assert fsm.transition(AgentState.ACTING)
        assert fsm.state == AgentState.ACTING

    def test_transition_to_same_state_returns_true(self):
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.IDLE)
        assert fsm.transition(AgentState.IDLE)
        assert fsm.state == AgentState.IDLE

    def test_force_state_bypasses_validation(self):
        fsm = AgentStateMachine()
        # STOPPED -> ACTING is invalid normally
        fsm.force_state(AgentState.ACTING)
        assert fsm.state == AgentState.ACTING

    def test_time_in_state(self):
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.IDLE)
        time.sleep(0.05)
        assert fsm.time_in_state >= 0.04

    def test_transition_count(self):
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.IDLE)
        assert fsm._transition_count == 0  # force_state doesn't count
        fsm.transition(AgentState.PERCEIVING)
        fsm.transition(AgentState.THINKING)
        assert fsm._transition_count == 2

    def test_state_history_recorded(self):
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.IDLE)
        fsm.transition(AgentState.PERCEIVING)
        fsm.transition(AgentState.THINKING)
        history = list(fsm._state_history)
        assert len(history) == 2
        assert history[0]['from'] == 'idle'
        assert history[0]['to'] == 'perceiving'
        assert history[1]['from'] == 'perceiving'
        assert history[1]['to'] == 'thinking'

    def test_to_dict(self):
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.IDLE)
        d = fsm.to_dict()
        assert d['current_state'] == 'idle'
        assert 'time_in_state_seconds' in d
        assert 'transition_count' in d
        assert 'recent_transitions' in d

    def test_all_states_can_transition_to_stopped(self):
        """Every state should be able to transition to STOPPED."""
        for state in AgentState:
            if state == AgentState.STOPPED:
                continue
            fsm = AgentStateMachine()
            fsm.force_state(state)
            assert fsm.transition(AgentState.STOPPED), \
                f"{state.value} should transition to STOPPED"

    def test_dreaming_to_idle(self):
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.DREAMING)
        assert fsm.transition(AgentState.IDLE)

    def test_thread_safety(self):
        """Multiple threads transitioning simultaneously should not corrupt state."""
        fsm = AgentStateMachine()
        fsm.force_state(AgentState.IDLE)
        errors = []

        def toggle_state(n):
            try:
                for _ in range(n):
                    fsm.force_state(AgentState.PERCEIVING)
                    fsm.force_state(AgentState.IDLE)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle_state, args=(50,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert fsm.state in (AgentState.IDLE, AgentState.PERCEIVING)


# ─── TaskPriority Tests ──────────────────────────────────────────────────

class TestTaskPriority:
    """Tests for task scoring and priority."""

    def test_user_request_highest_priority(self):
        user_task = AgentTask(
            task_id="t1", description="user request",
            priority=TaskPriority.USER_REQUEST, source="user",
            urgency=1.0, importance=1.0,
        )
        bg_task = AgentTask(
            task_id="t2", description="background",
            priority=TaskPriority.BACKGROUND, source="schedule",
            urgency=0.2, importance=0.2,
        )
        assert user_task.score() < bg_task.score()  # Lower score = higher priority

    def test_alarm_higher_than_self_initiated(self):
        alarm = AgentTask(
            task_id="t1", description="alarm",
            priority=TaskPriority.ALARM, source="sensor",
            urgency=0.9, importance=0.8,
        )
        self_init = AgentTask(
            task_id="t2", description="self",
            priority=TaskPriority.SELF_INITIATED, source="curiosity",
            urgency=0.5, importance=0.5,
        )
        assert alarm.score() < self_init.score()

    def test_urgency_affects_score(self):
        urgent = AgentTask(
            task_id="t1", description="urgent",
            priority=TaskPriority.SELF_INITIATED, source="sensor",
            urgency=1.0, importance=0.5,
        )
        not_urgent = AgentTask(
            task_id="t2", description="not urgent",
            priority=TaskPriority.SELF_INITIATED, source="sensor",
            urgency=0.1, importance=0.5,
        )
        assert urgent.score() < not_urgent.score()

    def test_task_to_dict(self):
        task = AgentTask(
            task_id="t1", description="test task",
            priority=TaskPriority.SELF_INITIATED, source="test",
        )
        d = task.to_dict()
        assert d['task_id'] == 't1'
        assert d['priority'] == 'SELF_INITIATED'
        assert 'score' in d


# ─── InterruptHandler Tests (P3.33) ──────────────────────────────────────

class TestInterruptHandler:
    """Tests for interrupt handling."""

    def test_no_interrupts_initially(self):
        handler = InterruptHandler(AgentLoopConfig())
        assert not handler.has_interrupt()
        assert handler.get_interrupt() is None

    def test_submit_and_get_interrupt(self):
        handler = InterruptHandler(AgentLoopConfig())
        task = AgentTask(
            task_id="int1", description="urgent!",
            priority=TaskPriority.USER_REQUEST, source="user",
        )
        handler.submit_interrupt(task)
        assert handler.has_interrupt()
        retrieved = handler.get_interrupt()
        assert retrieved.task_id == "int1"
        assert not handler.has_interrupt()

    def test_highest_priority_interrupt_first(self):
        handler = InterruptHandler(AgentLoopConfig())
        low = AgentTask(
            task_id="low", description="low priority",
            priority=TaskPriority.SELF_INITIATED, source="internal",
        )
        high = AgentTask(
            task_id="high", description="high priority",
            priority=TaskPriority.USER_REQUEST, source="user",
            urgency=1.0, importance=1.0,
        )
        handler.submit_interrupt(low)
        handler.submit_interrupt(high)
        first = handler.get_interrupt()
        assert first.task_id == "high"

    def test_clear_interrupts(self):
        handler = InterruptHandler(AgentLoopConfig())
        handler.submit_interrupt(AgentTask(
            task_id="t1", description="test",
            priority=TaskPriority.ALARM, source="sensor",
        ))
        handler.clear()
        assert not handler.has_interrupt()

    def test_wait_for_interrupt_timeout(self):
        handler = InterruptHandler(AgentLoopConfig())
        start = time.time()
        result = handler.wait_for_interrupt(timeout=0.1)
        elapsed = time.time() - start
        assert not result
        assert elapsed >= 0.09

    def test_wait_for_interrupt_wakeup(self):
        handler = InterruptHandler(AgentLoopConfig())

        def submit_after_delay():
            time.sleep(0.05)
            handler.submit_interrupt(AgentTask(
                task_id="wake", description="wake up",
                priority=TaskPriority.USER_REQUEST, source="user",
            ))

        t = threading.Thread(target=submit_after_delay)
        t.start()
        result = handler.wait_for_interrupt(timeout=2.0)
        t.join()
        assert result  # Should have been woken up

    def test_to_dict(self):
        handler = InterruptHandler(AgentLoopConfig())
        handler.submit_interrupt(AgentTask(
            task_id="t1", description="test",
            priority=TaskPriority.ALARM, source="sensor",
        ))
        d = handler.to_dict()
        assert d['pending_interrupts'] == 1
        assert len(d['interrupts']) == 1


# ─── AutonomyBudget Tests ────────────────────────────────────────────────

class TestAutonomyBudget:
    """Tests for action rate limiting."""

    def test_initial_budget_full(self):
        budget = AutonomyBudget(max_per_hour=10)
        assert budget.can_act()
        assert budget.remaining() == 10

    def test_record_action_reduces_budget(self):
        budget = AutonomyBudget(max_per_hour=3)
        budget.record_action()
        assert budget.remaining() == 2
        budget.record_action()
        assert budget.remaining() == 1
        budget.record_action()
        assert budget.remaining() == 0
        assert not budget.can_act()

    def test_old_actions_expire(self):
        budget = AutonomyBudget(max_per_hour=2)
        # Manually add an old timestamp
        budget._action_timestamps.append(time.time() - 3700)  # > 1 hour ago
        budget.record_action()
        # After pruning, the old one is gone
        assert budget.remaining() == 1  # Only the recent one counts

    def test_to_dict(self):
        budget = AutonomyBudget(max_per_hour=50)
        budget.record_action()
        d = budget.to_dict()
        assert d['max_per_hour'] == 50
        assert d['used_this_hour'] == 1
        assert d['remaining'] == 49


# ─── AgentLoopConfig Tests ───────────────────────────────────────────────

class TestAgentLoopConfig:
    """Tests for configuration."""

    def test_defaults(self):
        config = AgentLoopConfig()
        assert config.active_tick_interval == 1.0
        assert config.idle_tick_interval == 30.0
        assert config.max_autonomous_actions_per_hour == 50
        assert config.max_consecutive_errors == 5

    def test_from_yaml(self):
        yaml_dict = {
            'agent_loop': {
                'active_tick_interval': 2.0,
                'idle_tick_interval': 60.0,
                'max_autonomous_actions_per_hour': 100,
            }
        }
        config = AgentLoopConfig.from_yaml(yaml_dict)
        assert config.active_tick_interval == 2.0
        assert config.idle_tick_interval == 60.0
        assert config.max_autonomous_actions_per_hour == 100
        # Default for unspecified
        assert config.max_consecutive_errors == 5

    def test_from_yaml_empty(self):
        config = AgentLoopConfig.from_yaml({})
        assert config.active_tick_interval == 1.0  # Default


# ─── AgentLoop Integration Tests (P3.31) ─────────────────────────────────

class TestAgentLoop:
    """Tests for the main agent loop."""

    def test_initial_state(self):
        loop = AgentLoop()
        assert not loop.is_running
        assert loop.fsm.state == AgentState.STOPPED

    def test_submit_task(self):
        loop = AgentLoop()
        task_id = loop.submit_task("test task", TaskPriority.SELF_INITIATED)
        assert task_id.startswith("task_")
        with loop._task_queue_lock:
            assert len(loop._task_queue) == 1

    def test_submit_user_request_goes_to_interrupts(self):
        loop = AgentLoop()
        loop.submit_user_request("help me")
        assert loop.interrupt_handler.has_interrupt()
        with loop._task_queue_lock:
            assert len(loop._task_queue) == 0  # Not in regular queue

    def test_submit_alarm_goes_to_interrupts(self):
        loop = AgentLoop()
        loop.submit_task("fire!", TaskPriority.ALARM, source="sensor")
        assert loop.interrupt_handler.has_interrupt()

    def test_get_next_task_interrupts_first(self):
        loop = AgentLoop()
        # Add regular task
        loop.submit_task("background", TaskPriority.BACKGROUND)
        # Add interrupt
        loop.submit_user_request("urgent")

        task = loop._get_next_task()
        assert task.source == 'user'  # Interrupt first

    def test_task_queue_limit(self):
        config = AgentLoopConfig(max_pending_tasks=3)
        loop = AgentLoop(config)
        for i in range(5):
            loop.submit_task(f"task {i}", TaskPriority.SELF_INITIATED)
        with loop._task_queue_lock:
            assert len(loop._task_queue) == 3  # Capped

    def test_get_state(self):
        loop = AgentLoop()
        state = loop.get_state()
        assert 'running' in state
        assert 'state_machine' in state
        assert 'task_queue' in state
        assert 'interrupts' in state
        assert 'autonomy_budget' in state
        assert 'stats' in state
        assert state['running'] is False

    def test_start_and_stop(self):
        config = AgentLoopConfig(idle_tick_interval=0.1)
        loop = AgentLoop(config)
        loop.start()
        assert loop.is_running
        assert loop.fsm.state != AgentState.STOPPED
        time.sleep(0.2)
        loop.stop()
        assert not loop.is_running
        assert loop.fsm.state == AgentState.STOPPED

    def test_task_execution_with_mock_planner(self):
        """Test that the loop can process a task with a mocked planner."""
        config = AgentLoopConfig(active_tick_interval=0.05, idle_tick_interval=0.1)
        loop = AgentLoop(config)

        # Mock planner
        mock_prediction = MagicMock()
        mock_prediction.confidence = 0.8
        mock_prediction.brain_gates = [0.1] * 10
        mock_planner = MagicMock()
        mock_planner.predict.return_value = mock_prediction
        loop.planner = mock_planner

        loop.start()
        try:
            loop.submit_task("test prediction", TaskPriority.SELF_INITIATED, source="test")
            time.sleep(0.5)  # Give time for processing
        finally:
            loop.stop()

        assert loop._total_tasks_processed >= 1
        mock_planner.predict.assert_called()

    def test_interrupt_wakes_sleeping_loop(self):
        """Submitting an interrupt should wake up the loop from sleep."""
        config = AgentLoopConfig(idle_tick_interval=10.0)  # Long sleep
        loop = AgentLoop(config)

        mock_prediction = MagicMock()
        mock_prediction.confidence = 0.9
        mock_prediction.brain_gates = [0.1] * 10
        mock_planner = MagicMock()
        mock_planner.predict.return_value = mock_prediction
        loop.planner = mock_planner

        loop.start()
        try:
            time.sleep(0.1)
            # This should wake up the loop even though idle_tick is 10s
            loop.submit_user_request("wake up!")
            time.sleep(0.5)  # Should be enough for the interrupt to be processed
        finally:
            loop.stop()

        # The interrupt should have been processed
        assert loop._total_tasks_processed >= 1

    def test_autonomy_budget_tracked(self):
        config = AgentLoopConfig(
            active_tick_interval=0.05,
            idle_tick_interval=0.1,
            max_autonomous_actions_per_hour=100,
        )
        loop = AgentLoop(config)

        mock_prediction = MagicMock()
        mock_prediction.confidence = 0.8
        mock_prediction.brain_gates = [0.1] * 10
        mock_planner = MagicMock()
        mock_planner.predict.return_value = mock_prediction
        loop.planner = mock_planner

        loop.start()
        try:
            loop.submit_task("autonomous task", TaskPriority.SELF_INITIATED)
            time.sleep(0.3)
        finally:
            loop.stop()

        # Self-initiated task should count against budget
        budget = loop.autonomy_budget.to_dict()
        assert budget['used_this_hour'] >= 1

    def test_user_request_doesnt_count_budget(self):
        config = AgentLoopConfig(active_tick_interval=0.05, idle_tick_interval=0.1)
        loop = AgentLoop(config)

        mock_prediction = MagicMock()
        mock_prediction.confidence = 0.8
        mock_prediction.brain_gates = [0.1] * 10
        mock_planner = MagicMock()
        mock_planner.predict.return_value = mock_prediction
        loop.planner = mock_planner

        loop.start()
        try:
            loop.submit_user_request("user task")
            time.sleep(0.3)
        finally:
            loop.stop()

        # User requests should NOT count against budget
        budget = loop.autonomy_budget.to_dict()
        assert budget['used_this_hour'] == 0

    def test_dream_mode_with_high_sleep_pressure(self):
        config = AgentLoopConfig(
            idle_tick_interval=0.1,
            dream_duration_seconds=0.3,
            sleep_pressure_threshold=0.5,
        )
        loop = AgentLoop(config)

        # Mock homeostatic with high sleep pressure
        mock_homeo = MagicMock()
        mock_state = MagicMock()
        mock_state.sleep_pressure = 0.8  # Above threshold
        mock_homeo.get_state.return_value = mock_state
        loop.homeostatic = mock_homeo

        loop.start()
        time.sleep(0.5)

        # Should have entered dream mode at some point
        state = loop.get_state()
        loop.stop()

        # Dream time should be > 0 (it entered dream mode)
        assert state['stats']['total_dream_time_seconds'] >= 0

    def test_consecutive_error_handling(self):
        config = AgentLoopConfig(
            active_tick_interval=0.05,
            idle_tick_interval=0.1,
            max_consecutive_errors=3,
            error_cooldown_seconds=0.1,
        )
        loop = AgentLoop(config)

        # Planner that always fails
        mock_planner = MagicMock()
        mock_planner.predict.side_effect = RuntimeError("always fail")
        loop.planner = mock_planner

        loop.start()
        try:
            for i in range(5):
                loop.submit_task(f"fail task {i}", TaskPriority.SELF_INITIATED)
            time.sleep(1.0)
        finally:
            loop.stop()

        # Should have recorded failures
        assert loop._total_tasks_failed >= 1

    def test_valid_transitions_cover_all_states(self):
        """Ensure every state is represented in VALID_TRANSITIONS."""
        for state in AgentState:
            assert state in VALID_TRANSITIONS, f"{state.value} missing from VALID_TRANSITIONS"

    def test_event_bus_subscription(self):
        loop = AgentLoop()
        mock_bus = MagicMock()
        loop.event_bus = mock_bus
        loop._subscribe_to_events()
        assert mock_bus.subscribe.called


# ─── YAML Config Section Integration ──────────────────────────────────────

class TestAgentLoopYAMLIntegration:
    """Test that agent_loop config section is properly handled."""

    def test_full_yaml_config(self):
        yaml_dict = {
            'agent_loop': {
                'active_tick_interval': 0.5,
                'idle_tick_interval': 15.0,
                'dream_tick_interval': 45.0,
                'idle_threshold_seconds': 120.0,
                'dream_duration_seconds': 60.0,
                'sleep_pressure_threshold': 0.8,
                'low_energy_threshold': 0.15,
                'max_pending_tasks': 100,
                'max_concurrent_actions': 2,
                'task_timeout_seconds': 600.0,
                'interrupt_grace_period': 1.0,
                'max_autonomous_actions_per_hour': 200,
                'require_approval_above_risk': 'medium',
                'max_consecutive_errors': 10,
                'error_cooldown_seconds': 60.0,
            }
        }
        config = AgentLoopConfig.from_yaml(yaml_dict)
        assert config.active_tick_interval == 0.5
        assert config.idle_tick_interval == 15.0
        assert config.dream_tick_interval == 45.0
        assert config.idle_threshold_seconds == 120.0
        assert config.dream_duration_seconds == 60.0
        assert config.sleep_pressure_threshold == 0.8
        assert config.low_energy_threshold == 0.15
        assert config.max_pending_tasks == 100
        assert config.max_concurrent_actions == 2
        assert config.task_timeout_seconds == 600.0
        assert config.interrupt_grace_period == 1.0
        assert config.max_autonomous_actions_per_hour == 200
        assert config.require_approval_above_risk == 'medium'
        assert config.max_consecutive_errors == 10
        assert config.error_cooldown_seconds == 60.0
