"""
Tests for Phase 2 INTERN Action Systems (P2.18, P2.25-30).

Tests for:
  - ApprovalGate (P2.18)
  - ActionPlanner (P2.25)
  - ActionValidator (P2.26)
  - ActionMonitor (P2.27)
  - ActionOutcomeDetector (P2.28)
  - ActionReplayMemory (P2.29)
  - ActionLearning (P2.30)
  - ActionSystems (combined orchestrator)
"""

import pytest
import time
import os
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.action_systems import (
    PlannedAction,
    ActionPlan,
    ActionOutcome,
    ApprovalRequest,
    ApprovalGate,
    ActionPlanner,
    ValidationResult,
    ActionValidator,
    MonitoredAction,
    ActionMonitor,
    ActionOutcomeDetector,
    ReplayEntry,
    ActionReplayMemory,
    ActionLearning,
    ActionSystems,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_action(
    action_id='act_001',
    action_type='shell',
    target_system='automation',
    risk_level='low',
    parameters=None,
):
    """Factory for PlannedAction with sensible defaults."""
    return PlannedAction(
        action_id=action_id,
        action_type=action_type,
        target_system=target_system,
        parameters=parameters or {},
        risk_level=risk_level,
    )


def _make_plan(goal='test goal', actions=None):
    """Factory for ActionPlan with sensible defaults."""
    return ActionPlan(
        plan_id='plan_001',
        goal=goal,
        actions=actions or [],
    )


# ═══════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════

class TestPlannedAction:
    """Tests for the PlannedAction dataclass."""

    def test_default_values(self):
        a = PlannedAction(action_id='a1', action_type='shell', target_system='automation')
        assert a.action_id == 'a1'
        assert a.action_type == 'shell'
        assert a.target_system == 'automation'
        assert a.parameters == {}
        assert a.dependencies == []
        assert a.estimated_duration_seconds == 30.0
        assert a.risk_level == 'low'
        assert a.status == 'pending'

    def test_to_dict(self):
        a = _make_action(parameters={'cmd': 'echo hi'})
        d = a.to_dict()
        assert d['action_id'] == 'act_001'
        assert d['parameters'] == {'cmd': 'echo hi'}
        assert 'risk_level' in d
        assert 'status' in d


class TestActionPlan:
    """Tests for the ActionPlan dataclass."""

    def test_created_at_auto_set(self):
        plan = ActionPlan(plan_id='p1', goal='test')
        assert plan.created_at > 0

    def test_to_dict_with_actions(self):
        a1 = _make_action(action_id='a1')
        a2 = _make_action(action_id='a2')
        plan = ActionPlan(plan_id='p1', goal='deploy app', actions=[a1, a2])
        d = plan.to_dict()
        assert d['plan_id'] == 'p1'
        assert d['goal'] == 'deploy app'
        assert d['action_count'] == 2
        assert len(d['actions']) == 2

    def test_empty_plan(self):
        plan = ActionPlan(plan_id='p1', goal='empty')
        assert plan.to_dict()['action_count'] == 0


class TestActionOutcome:
    """Tests for the ActionOutcome dataclass."""

    def test_timestamp_auto_set(self):
        o = ActionOutcome(action_id='a1', plan_id='p1', success=True)
        assert o.timestamp > 0

    def test_to_dict_rounding(self):
        o = ActionOutcome(
            action_id='a1', plan_id='p1', success=False,
            duration_seconds=1.23456789, error_message='fail',
        )
        d = o.to_dict()
        assert d['duration_seconds'] == 1.235
        assert d['error_message'] == 'fail'


class TestApprovalRequest:
    """Tests for the ApprovalRequest dataclass."""

    def test_is_expired_false_when_fresh(self):
        action = _make_action()
        req = ApprovalRequest(
            request_id='r1', action=action, reason='test',
            risk_level='high', timeout_seconds=60.0,
        )
        assert not req.is_expired()

    def test_is_expired_true_when_old(self):
        action = _make_action()
        req = ApprovalRequest(
            request_id='r1', action=action, reason='test',
            risk_level='high', timeout_seconds=0.001,
            requested_at=time.time() - 10.0,
        )
        assert req.is_expired()

    def test_to_dict_keys(self):
        action = _make_action()
        req = ApprovalRequest(
            request_id='r1', action=action, reason='risky',
            risk_level='high',
        )
        d = req.to_dict()
        assert d['request_id'] == 'r1'
        assert d['action_id'] == 'act_001'
        assert d['reason'] == 'risky'
        assert 'is_expired' in d


# ═══════════════════════════════════════════════════════════════════════
# ApprovalGate (P2.18)
# ═══════════════════════════════════════════════════════════════════════

class TestApprovalGate:
    """Tests for the ApprovalGate class."""

    def test_default_init(self):
        gate = ApprovalGate()
        assert gate.default_timeout == 60.0
        assert gate.auto_reject_on_timeout is True
        assert gate.risk_threshold == 'high'

    def test_custom_init(self):
        gate = ApprovalGate(
            default_timeout=30.0,
            auto_reject_on_timeout=False,
            risk_threshold='medium',
        )
        assert gate.default_timeout == 30.0
        assert gate.auto_reject_on_timeout is False
        assert gate.risk_threshold == 'medium'

    def test_get_state(self):
        gate = ApprovalGate()
        state = gate.get_state()
        assert state['name'] == 'ApprovalGate'
        assert 'default_timeout' in state
        assert 'pending_count' in state
        assert 'total_requests' in state
        assert 'approval_rate' in state
        assert 'recent_audit' in state

    def test_requires_approval_high_risk(self):
        gate = ApprovalGate(risk_threshold='high')
        high_action = _make_action(risk_level='high')
        assert gate.requires_approval(high_action) is True

    def test_requires_approval_critical_risk(self):
        gate = ApprovalGate(risk_threshold='high')
        critical = _make_action(risk_level='critical')
        assert gate.requires_approval(critical) is True

    def test_does_not_require_approval_low_risk(self):
        gate = ApprovalGate(risk_threshold='high')
        low_action = _make_action(risk_level='low')
        assert gate.requires_approval(low_action) is False

    def test_requires_approval_medium_threshold(self):
        gate = ApprovalGate(risk_threshold='medium')
        medium_action = _make_action(risk_level='medium')
        assert gate.requires_approval(medium_action) is True

    def test_request_approval_creates_pending(self):
        gate = ApprovalGate()
        action = _make_action(risk_level='high')
        req = gate.request_approval(action, reason='testing')
        assert req.status == 'pending'
        assert req.request_id in [r['request_id'] for r in gate.get_pending_requests()]
        assert gate._total_requests == 1

    def test_approve_request(self):
        gate = ApprovalGate()
        action = _make_action(risk_level='high')
        req = gate.request_approval(action)
        result = gate.approve(req.request_id)
        assert result is True
        assert gate._total_approved == 1
        assert action.status == 'approved'

    def test_approve_nonexistent_request(self):
        gate = ApprovalGate()
        result = gate.approve('nonexistent_id')
        assert result is False

    def test_reject_request(self):
        gate = ApprovalGate()
        action = _make_action(risk_level='high')
        req = gate.request_approval(action)
        result = gate.reject(req.request_id, reason='too dangerous')
        assert result is True
        assert gate._total_rejected == 1
        assert action.status == 'rejected'

    def test_reject_nonexistent_request(self):
        gate = ApprovalGate()
        result = gate.reject('nonexistent_id')
        assert result is False

    def test_timeout_auto_rejects(self):
        gate = ApprovalGate(default_timeout=0.001, auto_reject_on_timeout=True)
        action = _make_action(risk_level='high')
        req = gate.request_approval(action)
        # Force expiration
        req.requested_at = time.time() - 10.0
        timed_out = gate.process_timeouts()
        assert len(timed_out) == 1
        assert timed_out[0].status == 'timeout'
        assert action.status == 'rejected'
        assert gate._total_timeouts == 1

    def test_approve_expired_request_fails(self):
        gate = ApprovalGate(default_timeout=0.001)
        action = _make_action(risk_level='high')
        req = gate.request_approval(action)
        req.requested_at = time.time() - 10.0
        result = gate.approve(req.request_id)
        assert result is False
        assert gate._total_timeouts == 1

    def test_audit_log_populated(self):
        gate = ApprovalGate()
        action = _make_action(risk_level='high')
        req = gate.request_approval(action)
        gate.approve(req.request_id)
        state = gate.get_state()
        assert len(state['recent_audit']) == 1
        assert state['recent_audit'][0]['decision'] == 'approved'

    def test_get_pending_requests_clears_expired(self):
        gate = ApprovalGate(default_timeout=0.001)
        action = _make_action(risk_level='high')
        req = gate.request_approval(action)
        req.requested_at = time.time() - 10.0
        # get_pending_requests calls process_timeouts internally
        pending = gate.get_pending_requests()
        assert len(pending) == 0


# ═══════════════════════════════════════════════════════════════════════
# ActionPlanner (P2.25)
# ═══════════════════════════════════════════════════════════════════════

class TestActionPlanner:
    """Tests for the ActionPlanner class."""

    def test_default_init(self):
        planner = ActionPlanner()
        assert planner.max_plan_depth == 10
        assert planner.max_actions_per_plan == 50
        assert planner.default_risk == 'low'
        assert len(planner._templates) > 0

    def test_custom_init(self):
        planner = ActionPlanner(
            max_plan_depth=5,
            max_actions_per_plan=20,
            default_risk='medium',
            templates={'custom': [{'action_type': 'run', 'target_system': 'automation', 'risk': 'low'}]},
        )
        assert planner.max_plan_depth == 5
        assert planner.max_actions_per_plan == 20
        assert planner.default_risk == 'medium'
        assert 'custom' in planner._templates

    def test_get_state(self):
        planner = ActionPlanner()
        state = planner.get_state()
        assert state['name'] == 'ActionPlanner'
        assert 'max_plan_depth' in state
        assert 'template_count' in state
        assert 'template_keywords' in state
        assert 'total_plans' in state

    def test_create_plan_with_template_match(self):
        planner = ActionPlanner()
        plan = planner.create_plan('deploy the new feature')
        assert plan.goal == 'deploy the new feature'
        assert len(plan.actions) > 0
        assert plan.status == 'pending'
        assert planner._total_plans == 1

    def test_create_plan_no_template_match(self):
        planner = ActionPlanner()
        plan = planner.create_plan('do something unusual xyz123')
        # Falls back to single generic action
        assert len(plan.actions) == 1
        assert plan.actions[0].action_type == 'execute'

    def test_create_plan_fix_template(self):
        planner = ActionPlanner()
        plan = planner.create_plan('fix the login bug')
        assert len(plan.actions) == 3
        types = [a.action_type for a in plan.actions]
        assert 'diagnose' in types
        assert 'implement_fix' in types

    def test_create_plan_investigate_template(self):
        planner = ActionPlanner()
        plan = planner.create_plan('investigate the error spike')
        assert len(plan.actions) == 3

    def test_create_plan_test_template(self):
        planner = ActionPlanner()
        plan = planner.create_plan('test the integration')
        assert len(plan.actions) == 3

    def test_plan_actions_have_dependencies(self):
        planner = ActionPlanner()
        plan = planner.create_plan('deploy service')
        # Template-based plans have sequential dependencies
        for i in range(1, len(plan.actions)):
            assert len(plan.actions[i].dependencies) == 1

    def test_max_actions_per_plan_enforced(self):
        planner = ActionPlanner(max_actions_per_plan=2)
        plan = planner.create_plan('deploy the app')
        assert len(plan.actions) <= 2

    def test_add_custom_template(self):
        planner = ActionPlanner()
        planner.add_custom_template('migrate', [
            {'action_type': 'backup', 'target_system': 'automation', 'risk': 'medium'},
            {'action_type': 'migrate_data', 'target_system': 'coding_engine', 'risk': 'high'},
        ])
        plan = planner.create_plan('migrate the database')
        assert len(plan.actions) == 2
        assert plan.actions[0].action_type == 'backup'

    def test_get_execution_order_empty_plan(self):
        planner = ActionPlanner()
        plan = _make_plan(actions=[])
        layers = planner.get_execution_order(plan)
        assert layers == []

    def test_get_execution_order_sequential(self):
        planner = ActionPlanner()
        plan = planner.create_plan('deploy feature')
        layers = planner.get_execution_order(plan)
        assert len(layers) > 0
        # First layer has one action (the root)
        assert len(layers[0]) == 1

    def test_get_execution_order_parallel_root(self):
        """Actions with no dependencies can run in parallel."""
        a1 = _make_action(action_id='a1')
        a2 = _make_action(action_id='a2')
        plan = _make_plan(actions=[a1, a2])
        planner = ActionPlanner()
        layers = planner.get_execution_order(plan)
        # Both actions have no deps, so they are in the same layer
        assert len(layers) == 1
        assert len(layers[0]) == 2

    def test_create_plan_context_target_system(self):
        planner = ActionPlanner()
        plan = planner.create_plan('random goal xyz', context={'target_system': 'coding_engine'})
        assert plan.actions[0].target_system == 'coding_engine'

    def test_total_actions_planned_counter(self):
        planner = ActionPlanner()
        planner.create_plan('fix bug')
        planner.create_plan('deploy app')
        assert planner._total_actions_planned > 0
        assert planner._total_plans == 2


# ═══════════════════════════════════════════════════════════════════════
# ActionValidator (P2.26)
# ═══════════════════════════════════════════════════════════════════════

class TestActionValidator:
    """Tests for the ActionValidator class."""

    def test_default_init(self):
        validator = ActionValidator()
        assert validator.max_resource_cost == 100.0
        assert len(validator._blocked_compiled) > 0
        assert len(validator._approval_compiled) > 0

    def test_custom_init(self):
        validator = ActionValidator(
            blocked_patterns=[r'dangerous'],
            max_resource_cost=50.0,
            require_approval_patterns=[r'careful'],
        )
        assert validator.max_resource_cost == 50.0
        assert len(validator._blocked_compiled) == 1
        assert len(validator._approval_compiled) == 1

    def test_get_state(self):
        validator = ActionValidator()
        state = validator.get_state()
        assert state['name'] == 'ActionValidator'
        assert 'blocked_pattern_count' in state
        assert 'approval_pattern_count' in state
        assert 'total_validated' in state
        assert 'approval_rate' in state

    def test_validate_safe_action(self):
        validator = ActionValidator()
        action = _make_action(action_type='shell', parameters={'cmd': 'echo hello'})
        result = validator.validate_action(action)
        assert result.approved is True
        assert 'Passed all safety checks' in result.reason

    def test_validate_blocked_rm_rf(self):
        validator = ActionValidator()
        action = _make_action(
            action_type='shell',
            parameters={'cmd': 'rm -rf /'},
        )
        result = validator.validate_action(action)
        assert result.approved is False
        assert 'blocked pattern' in result.reason.lower()

    def test_validate_blocked_drop_table(self):
        validator = ActionValidator()
        action = _make_action(
            action_type='shell',
            parameters={'cmd': 'DROP TABLE users'},
        )
        result = validator.validate_action(action)
        assert result.approved is False

    def test_validate_blocked_truncate(self):
        validator = ActionValidator()
        action = _make_action(
            action_type='shell',
            parameters={'cmd': 'TRUNCATE TABLE logs'},
        )
        result = validator.validate_action(action)
        assert result.approved is False

    def test_validate_blocked_format_drive(self):
        validator = ActionValidator()
        action = _make_action(
            action_type='shell',
            parameters={'cmd': 'format C:'},
        )
        result = validator.validate_action(action)
        assert result.approved is False

    def test_validate_approval_pattern_elevates_risk(self):
        validator = ActionValidator()
        action = _make_action(
            action_type='deploy',
            target_system='automation',
            risk_level='low',
        )
        result = validator.validate_action(action)
        assert result.approved is True
        assert 'approval' in result.reason.lower()
        # Risk should have been elevated to high
        assert action.risk_level == 'high'

    def test_validate_approval_pattern_sudo(self):
        validator = ActionValidator()
        action = _make_action(
            action_type='shell',
            parameters={'cmd': 'sudo apt update'},
        )
        result = validator.validate_action(action)
        assert result.approved is True
        assert action.risk_level == 'high'

    def test_validate_resource_cost_exceeded(self):
        validator = ActionValidator(max_resource_cost=10.0)
        action = _make_action(parameters={'resource_cost': 50.0})
        result = validator.validate_action(action)
        assert result.approved is False
        assert 'resource cost' in result.reason.lower()

    def test_validate_resource_cost_within_limit(self):
        validator = ActionValidator(max_resource_cost=100.0)
        action = _make_action(parameters={'resource_cost': 5.0})
        result = validator.validate_action(action)
        assert result.approved is True

    def test_validate_plan(self):
        validator = ActionValidator()
        a1 = _make_action(action_id='a1', action_type='shell', parameters={'cmd': 'echo ok'})
        a2 = _make_action(action_id='a2', action_type='shell', parameters={'cmd': 'rm -rf /'})
        plan = _make_plan(actions=[a1, a2])
        results = validator.validate_plan(plan)
        assert len(results) == 2
        assert results[0].approved is True
        assert results[1].approved is False

    def test_statistics_tracked(self):
        validator = ActionValidator()
        validator.validate_action(_make_action(parameters={'cmd': 'echo ok'}))
        validator.validate_action(_make_action(parameters={'cmd': 'rm -rf /'}))
        assert validator._total_validated == 2
        assert validator._total_approved == 1
        assert validator._total_rejected == 1

    def test_custom_blocked_pattern(self):
        validator = ActionValidator(blocked_patterns=[r'forbidden_cmd'])
        action = _make_action(parameters={'cmd': 'forbidden_cmd --yes'})
        result = validator.validate_action(action)
        assert result.approved is False


# ═══════════════════════════════════════════════════════════════════════
# ActionMonitor (P2.27)
# ═══════════════════════════════════════════════════════════════════════

class TestActionMonitor:
    """Tests for the ActionMonitor class."""

    def test_default_init(self):
        monitor = ActionMonitor()
        assert monitor.default_timeout_seconds == 300.0
        assert monitor.max_retries == 3
        assert monitor.escalation_threshold == 0.9

    def test_custom_init(self):
        monitor = ActionMonitor(
            default_timeout_seconds=60.0,
            max_retries=1,
            escalation_threshold=0.5,
        )
        assert monitor.default_timeout_seconds == 60.0
        assert monitor.max_retries == 1
        assert monitor.escalation_threshold == 0.5

    def test_get_state(self):
        monitor = ActionMonitor()
        state = monitor.get_state()
        assert state['name'] == 'ActionMonitor'
        assert 'default_timeout_seconds' in state
        assert 'active_monitors' in state
        assert 'total_monitored' in state
        assert 'pending_events' in state

    def test_start_monitoring(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        assert len(monitor._active) == 1
        assert monitor._total_monitored == 1

    def test_stop_monitoring(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        monitor.stop_monitoring('a1')
        assert len(monitor._active) == 0

    def test_stop_monitoring_nonexistent(self):
        monitor = ActionMonitor()
        # Should not raise
        monitor.stop_monitoring('nonexistent')

    def test_timeout_detection_with_retry(self):
        monitor = ActionMonitor(default_timeout_seconds=0.001, max_retries=2)
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        # Force timeout
        monitor._active['a1'].started_at = time.time() - 10.0
        events = monitor.check_all()
        assert len(events) == 1
        assert events[0]['type'] == 'action_timeout_retry'
        assert monitor._active['a1'].retries == 1

    def test_timeout_detection_abort_after_retries(self):
        monitor = ActionMonitor(default_timeout_seconds=0.001, max_retries=0)
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        monitor._active['a1'].started_at = time.time() - 10.0
        events = monitor.check_all()
        assert len(events) == 1
        assert events[0]['type'] == 'action_aborted'
        assert monitor._active['a1'].aborted is True

    def test_resource_escalation_abort(self):
        monitor = ActionMonitor(escalation_threshold=0.8)
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        monitor.record_resource_usage('a1', 0.95)
        events = monitor.check_all()
        assert len(events) == 1
        assert events[0]['type'] == 'action_aborted'
        assert 'resource usage' in events[0]['reason'].lower()

    def test_resource_usage_clamped(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        monitor.record_resource_usage('a1', 5.0)
        assert monitor._active['a1'].resource_usage == 1.0
        monitor.record_resource_usage('a1', -2.0)
        assert monitor._active['a1'].resource_usage == 0.0

    def test_loop_detection(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        # Feed 5 identical outputs
        for _ in range(5):
            monitor.record_output('a1', 'same output line')
        events = monitor.check_all()
        assert len(events) == 1
        assert 'loop' in events[0]['reason'].lower()

    def test_no_loop_with_varied_output(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        for i in range(5):
            monitor.record_output('a1', f'output line {i}')
        events = monitor.check_all()
        assert len(events) == 0

    def test_no_loop_with_fewer_than_five_outputs(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        for _ in range(4):
            monitor.record_output('a1', 'same')
        events = monitor.check_all()
        # Not enough outputs for loop detection
        assert len(events) == 0

    def test_no_loop_with_empty_output(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        for _ in range(5):
            monitor.record_output('a1', '')
        events = monitor.check_all()
        assert len(events) == 0

    def test_record_output_for_nonexistent_action(self):
        monitor = ActionMonitor()
        # Should not raise
        monitor.record_output('nonexistent', 'data')

    def test_record_resource_for_nonexistent_action(self):
        monitor = ActionMonitor()
        # Should not raise
        monitor.record_resource_usage('nonexistent', 0.5)

    def test_get_active_monitors(self):
        monitor = ActionMonitor()
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        active = monitor.get_active_monitors()
        assert len(active) == 1
        assert active[0]['action_id'] == 'a1'

    def test_drain_events(self):
        monitor = ActionMonitor(default_timeout_seconds=0.001, max_retries=0)
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1')
        monitor._active['a1'].started_at = time.time() - 10.0
        monitor.check_all()
        events = monitor.drain_events()
        assert len(events) == 1
        # Drain again should be empty
        assert len(monitor.drain_events()) == 0

    def test_timeout_override(self):
        monitor = ActionMonitor(default_timeout_seconds=300.0)
        action = _make_action(action_id='a1')
        monitor.start_monitoring(action, plan_id='p1', timeout_override=5.0)
        assert monitor._active['a1'].timeout_seconds == 5.0


# ═══════════════════════════════════════════════════════════════════════
# ActionOutcomeDetector (P2.28)
# ═══════════════════════════════════════════════════════════════════════

class TestActionOutcomeDetector:
    """Tests for the ActionOutcomeDetector class."""

    def test_default_init(self):
        detector = ActionOutcomeDetector()
        assert detector.unknown_timeout == 60.0

    def test_custom_init(self):
        detector = ActionOutcomeDetector(unknown_timeout=30.0)
        assert detector.unknown_timeout == 30.0

    def test_get_state(self):
        detector = ActionOutcomeDetector()
        state = detector.get_state()
        assert state['name'] == 'ActionOutcomeDetector'
        assert 'total_detected' in state
        assert 'total_success' in state
        assert 'total_failure' in state
        assert 'overall_success_rate' in state

    def test_detect_shell_success(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='shell')
        outcome = detector.detect_outcome(action, 'p1', {'exit_code': 0}, duration_seconds=1.0)
        assert outcome.success is True
        assert outcome.exit_code == 0

    def test_detect_shell_failure(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='shell')
        outcome = detector.detect_outcome(action, 'p1', {'exit_code': 1, 'stderr': 'error'})
        assert outcome.success is False

    def test_detect_http_success(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='http')
        outcome = detector.detect_outcome(action, 'p1', {'status_code': 200})
        assert outcome.success is True

    def test_detect_http_failure(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='http')
        outcome = detector.detect_outcome(action, 'p1', {'status_code': 500})
        assert outcome.success is False

    def test_detect_http_client_error(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='http_request')
        outcome = detector.detect_outcome(action, 'p1', {'status_code': 404})
        assert outcome.success is False

    def test_detect_coding_job_completed(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='coding_job')
        outcome = detector.detect_outcome(action, 'p1', {'status': 'COMPLETED'})
        assert outcome.success is True

    def test_detect_coding_job_failed(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='implement')
        outcome = detector.detect_outcome(action, 'p1', {'status': 'FAILED'})
        assert outcome.success is False

    def test_detect_coding_job_cancelled(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='coding_job')
        outcome = detector.detect_outcome(action, 'p1', {'status': 'CANCELLED'})
        assert outcome.success is False

    def test_detect_file_write_success(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='file_write')
        outcome = detector.detect_outcome(action, 'p1', {'exists': True, 'path': '/tmp/f'})
        assert outcome.success is True

    def test_detect_file_write_failure(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='file_create')
        outcome = detector.detect_outcome(action, 'p1', {'exists': False})
        assert outcome.success is False

    def test_detect_generic_success_key(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='unknown_type')
        outcome = detector.detect_outcome(action, 'p1', {'success': True})
        assert outcome.success is True

    def test_detect_generic_error_key(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='unknown_type')
        outcome = detector.detect_outcome(action, 'p1', {'error': 'something broke'})
        assert outcome.success is False
        assert 'something broke' in outcome.error_message

    def test_detect_unknown_defaults_success(self):
        """Unknown outcome with short duration defaults to success."""
        detector = ActionOutcomeDetector(unknown_timeout=60.0)
        action = _make_action(action_type='unknown_type')
        outcome = detector.detect_outcome(action, 'p1', {}, duration_seconds=5.0)
        assert outcome.success is True

    def test_detect_unknown_timeout_failure(self):
        """Unknown outcome past timeout classified as failure."""
        detector = ActionOutcomeDetector(unknown_timeout=10.0)
        action = _make_action(action_type='unknown_type')
        outcome = detector.detect_outcome(action, 'p1', {}, duration_seconds=30.0)
        assert outcome.success is False
        assert 'undetermined' in outcome.error_message.lower()

    def test_get_recent_outcomes(self):
        detector = ActionOutcomeDetector()
        for i in range(5):
            action = _make_action(action_id=f'a{i}', action_type='shell')
            detector.detect_outcome(action, 'p1', {'exit_code': 0})
        recent = detector.get_recent_outcomes(count=3)
        assert len(recent) == 3

    def test_get_success_rate(self):
        detector = ActionOutcomeDetector()
        for i in range(10):
            action = _make_action(action_id=f'a{i}', action_type='shell')
            code = 0 if i < 7 else 1
            detector.detect_outcome(action, 'p1', {'exit_code': code})
        rate = detector.get_success_rate()
        assert rate == 0.7

    def test_get_success_rate_empty(self):
        detector = ActionOutcomeDetector()
        assert detector.get_success_rate() == 0.0

    def test_error_message_truncated(self):
        detector = ActionOutcomeDetector()
        action = _make_action(action_type='unknown_type')
        long_error = 'x' * 500
        outcome = detector.detect_outcome(action, 'p1', {'error': long_error})
        assert len(outcome.error_message) <= 200


# ═══════════════════════════════════════════════════════════════════════
# ActionReplayMemory (P2.29)
# ═══════════════════════════════════════════════════════════════════════

class TestActionReplayMemory:
    """Tests for the ActionReplayMemory class."""

    def test_default_init(self):
        mem = ActionReplayMemory()
        assert mem.max_memories == 5000
        assert mem.priority_boost_on_failure == 2.0
        assert mem.replay_batch_size == 32

    def test_custom_init(self):
        mem = ActionReplayMemory(
            max_memories=100,
            priority_boost_on_failure=3.0,
            replay_batch_size=8,
        )
        assert mem.max_memories == 100
        assert mem.priority_boost_on_failure == 3.0
        assert mem.replay_batch_size == 8

    def test_get_state(self):
        mem = ActionReplayMemory()
        state = mem.get_state()
        assert state['name'] == 'ActionReplayMemory'
        assert 'max_memories' in state
        assert 'current_size' in state
        assert 'total_stored' in state
        assert 'effectiveness_summary' in state

    def test_store_success(self):
        mem = ActionReplayMemory()
        mem.store('deploy app', 'automation', 'shell', outcome_success=True, duration_seconds=5.0)
        assert mem._total_stored == 1
        assert len(mem._memory) == 1

    def test_store_failure_boosted_priority(self):
        mem = ActionReplayMemory(priority_boost_on_failure=3.0)
        mem.store('deploy app', 'automation', 'shell', outcome_success=False)
        entry = list(mem._memory)[-1]
        assert entry.priority == 3.0

    def test_store_success_default_priority(self):
        mem = ActionReplayMemory()
        mem.store('run test', 'coding_engine', 'test', outcome_success=True)
        entry = list(mem._memory)[-1]
        assert entry.priority == 1.0

    def test_store_truncates_long_situation(self):
        mem = ActionReplayMemory()
        long_situation = 'x' * 1000
        mem.store(long_situation, 'automation', 'shell')
        entry = list(mem._memory)[-1]
        assert len(entry.situation) <= 500

    def test_replay_batch_empty(self):
        mem = ActionReplayMemory()
        batch = mem.replay_batch()
        assert batch == []

    def test_replay_batch_returns_entries(self):
        mem = ActionReplayMemory(replay_batch_size=5)
        for i in range(10):
            mem.store(f'task {i}', 'automation', 'shell', outcome_success=(i % 2 == 0))
        batch = mem.replay_batch()
        assert len(batch) == 5
        assert mem._total_replays == 1

    def test_replay_batch_prioritizes_failures(self):
        mem = ActionReplayMemory(replay_batch_size=2, priority_boost_on_failure=10.0)
        # Store 5 successes and 2 failures
        for i in range(5):
            mem.store(f'ok {i}', 'automation', 'shell', outcome_success=True)
        mem.store('fail 1', 'automation', 'shell', outcome_success=False)
        mem.store('fail 2', 'automation', 'shell', outcome_success=False)
        batch = mem.replay_batch()
        # Failures have much higher priority so should appear first
        assert any(not e['outcome_success'] for e in batch)

    def test_get_best_system_for_no_data(self):
        mem = ActionReplayMemory()
        result = mem.get_best_system_for('unknown_action')
        assert result is None

    def test_get_best_system_for_with_data(self):
        mem = ActionReplayMemory()
        # automation: 2 successes out of 3
        mem.store('task', 'automation', 'shell', outcome_success=True)
        mem.store('task', 'automation', 'shell', outcome_success=True)
        mem.store('task', 'automation', 'shell', outcome_success=False)
        # coding_engine: 1 success out of 3
        mem.store('task', 'coding_engine', 'shell', outcome_success=True)
        mem.store('task', 'coding_engine', 'shell', outcome_success=False)
        mem.store('task', 'coding_engine', 'shell', outcome_success=False)
        best = mem.get_best_system_for('shell')
        assert best == 'automation'

    def test_get_best_system_needs_min_samples(self):
        mem = ActionReplayMemory()
        # Only 1 sample each -- insufficient (needs 2)
        mem.store('task', 'automation', 'shell', outcome_success=True)
        mem.store('task', 'coding_engine', 'shell', outcome_success=True)
        best = mem.get_best_system_for('shell')
        assert best is None

    def test_get_system_effectiveness(self):
        mem = ActionReplayMemory()
        mem.store('task', 'automation', 'shell', outcome_success=True)
        mem.store('task', 'automation', 'shell', outcome_success=False)
        summary = mem.get_system_effectiveness()
        assert 'shell' in summary
        assert 'automation' in summary['shell']
        assert summary['shell']['automation']['total_count'] == 2

    def test_max_memories_eviction(self):
        mem = ActionReplayMemory(max_memories=5)
        for i in range(10):
            mem.store(f'task {i}', 'automation', 'shell')
        assert len(mem._memory) == 5
        assert mem._total_stored == 10


# ═══════════════════════════════════════════════════════════════════════
# ActionLearning (P2.30)
# ═══════════════════════════════════════════════════════════════════════

class TestActionLearning:
    """Tests for the ActionLearning class."""

    def test_default_init(self):
        learning = ActionLearning()
        assert learning.learning_rate == 0.1
        assert learning.min_samples == 5
        assert learning.decay_factor == 0.95

    def test_custom_init(self):
        learning = ActionLearning(
            learning_rate=0.2,
            min_samples=3,
            decay_factor=0.9,
        )
        assert learning.learning_rate == 0.2
        assert learning.min_samples == 3
        assert learning.decay_factor == 0.9

    def test_get_state(self):
        learning = ActionLearning()
        state = learning.get_state()
        assert state['name'] == 'ActionLearning'
        assert 'learning_rate' in state
        assert 'known_systems' in state
        assert 'routing_weights' in state
        assert 'total_observations' in state

    def test_get_routing_weights_unknown_type(self):
        learning = ActionLearning()
        weights = learning.get_routing_weights('totally_new')
        # Should return uniform weights
        assert len(weights) == 3
        for w in weights.values():
            assert abs(w - 1.0 / 3) < 0.01

    def test_get_best_system_uniform(self):
        learning = ActionLearning()
        # With no observations, all weights are equal; just check it returns a valid system
        best = learning.get_best_system('deploy')
        assert best in learning._systems

    def test_observe_records(self):
        learning = ActionLearning()
        learning.observe('deploy', 'automation', True)
        assert learning._total_observations == 1

    def test_weights_update_after_min_samples(self):
        learning = ActionLearning(min_samples=3, learning_rate=0.5, decay_factor=1.0)
        # Feed automation successes
        for _ in range(5):
            learning.observe('deploy', 'automation', True)
        # Feed coding_engine failures
        for _ in range(5):
            learning.observe('deploy', 'coding_engine', False)
        weights = learning.get_routing_weights('deploy')
        # automation should have higher weight than coding_engine
        assert weights['automation'] > weights['coding_engine']

    def test_get_best_system_after_learning(self):
        learning = ActionLearning(min_samples=3, learning_rate=0.5, decay_factor=1.0)
        for _ in range(10):
            learning.observe('fix', 'coding_engine', True)
        for _ in range(10):
            learning.observe('fix', 'automation', False)
        best = learning.get_best_system('fix')
        assert best == 'coding_engine'

    def test_decay_reduces_counts(self):
        learning = ActionLearning(decay_factor=0.5)
        # Store an initial observation
        learning._observations['test']['automation'] = [10, 20]
        learning._apply_decay('test')
        obs = learning._observations['test']['automation']
        assert obs[0] == 5
        assert obs[1] == 10

    def test_weights_floor_prevents_zero(self):
        learning = ActionLearning(min_samples=1, learning_rate=1.0, decay_factor=1.0)
        # All failures for one system
        for _ in range(5):
            learning.observe('deploy', 'automation', False)
        weights = learning.get_routing_weights('deploy')
        # Weight should be floored at 0.01 (before normalization)
        assert weights['automation'] > 0

    def test_observe_new_system(self):
        learning = ActionLearning()
        learning.observe('deploy', 'new_custom_system', True)
        assert 'new_custom_system' in learning._systems

    def test_get_all_weights(self):
        learning = ActionLearning(min_samples=1, decay_factor=1.0)
        for _ in range(3):
            learning.observe('deploy', 'automation', True)
            learning.observe('fix', 'coding_engine', True)
        all_w = learning.get_all_weights()
        assert 'deploy' in all_w
        assert 'fix' in all_w

    def test_weights_sum_to_one(self):
        learning = ActionLearning(min_samples=2, learning_rate=0.3, decay_factor=1.0)
        for _ in range(10):
            learning.observe('deploy', 'automation', True)
            learning.observe('deploy', 'coding_engine', False)
            learning.observe('deploy', 'requirements_engine', True)
        weights = learning.get_routing_weights('deploy')
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    def test_total_updates_counter(self):
        learning = ActionLearning(min_samples=2, decay_factor=1.0)
        for _ in range(5):
            learning.observe('deploy', 'automation', True)
        assert learning._total_updates > 0


# ═══════════════════════════════════════════════════════════════════════
# ActionSystems (combined orchestrator)
# ═══════════════════════════════════════════════════════════════════════

class TestActionSystems:
    """Tests for the ActionSystems combined orchestrator."""

    def test_default_init(self):
        systems = ActionSystems()
        assert isinstance(systems.approval_gate, ApprovalGate)
        assert isinstance(systems.planner, ActionPlanner)
        assert isinstance(systems.validator, ActionValidator)
        assert isinstance(systems.monitor, ActionMonitor)
        assert isinstance(systems.outcome_detector, ActionOutcomeDetector)
        assert isinstance(systems.replay_memory, ActionReplayMemory)
        assert isinstance(systems.learning, ActionLearning)

    def test_from_yaml_defaults(self):
        systems = ActionSystems.from_yaml({})
        assert isinstance(systems.approval_gate, ApprovalGate)
        assert systems.approval_gate.default_timeout == 60.0
        assert systems.planner.max_plan_depth == 10

    def test_from_yaml_custom_config(self):
        config = {
            'action_systems': {
                'default_timeout': 30.0,
                'risk_threshold': 'medium',
                'max_plan_depth': 5,
                'max_resource_cost': 50.0,
                'default_timeout_seconds': 120.0,
                'max_retries': 1,
                'unknown_timeout': 45.0,
                'max_memories': 2000,
                'learning_rate': 0.2,
            }
        }
        systems = ActionSystems.from_yaml(config)
        assert systems.approval_gate.default_timeout == 30.0
        assert systems.approval_gate.risk_threshold == 'medium'
        assert systems.planner.max_plan_depth == 5
        assert systems.validator.max_resource_cost == 50.0
        assert systems.monitor.default_timeout_seconds == 120.0
        assert systems.monitor.max_retries == 1
        assert systems.outcome_detector.unknown_timeout == 45.0
        assert systems.replay_memory.max_memories == 2000
        assert systems.learning.learning_rate == 0.2

    def test_get_state(self):
        systems = ActionSystems()
        state = systems.get_state()
        assert 'total_plans_executed' in state
        assert 'total_actions_executed' in state
        assert 'approval_gate' in state
        assert 'planner' in state
        assert 'validator' in state
        assert 'monitor' in state
        assert 'outcome_detector' in state
        assert 'replay_memory' in state
        assert 'learning' in state

    def test_plan_and_validate(self):
        systems = ActionSystems()
        plan, results = systems.plan_and_validate('fix the login bug')
        assert isinstance(plan, ActionPlan)
        assert len(results) == len(plan.actions)
        assert all(isinstance(r, ValidationResult) for r in results)

    def test_plan_and_validate_with_rejection(self):
        validator = ActionValidator(blocked_patterns=[r'diagnose'])
        systems = ActionSystems(validator=validator)
        plan, results = systems.plan_and_validate('fix the issue')
        rejected = [r for r in results if not r.approved]
        assert len(rejected) > 0

    def test_record_outcome_full_pipeline(self):
        systems = ActionSystems()
        action = _make_action(action_id='a1', action_type='shell', target_system='automation')
        # Start monitoring
        systems.monitor.start_monitoring(action, plan_id='p1')
        # Record outcome
        outcome = systems.record_outcome(
            action=action,
            plan_id='p1',
            result_data={'exit_code': 0},
            duration_seconds=2.5,
            situation='run tests',
        )
        assert outcome.success is True
        assert systems._total_actions_executed == 1
        # Monitoring should be stopped
        assert 'a1' not in systems.monitor._active
        # Replay memory should have entry
        assert systems.replay_memory._total_stored == 1
        # Learning should have observation
        assert systems.learning._total_observations == 1

    def test_record_outcome_failure(self):
        systems = ActionSystems()
        action = _make_action(action_id='a2', action_type='shell', target_system='automation')
        outcome = systems.record_outcome(
            action=action,
            plan_id='p1',
            result_data={'exit_code': 1, 'stderr': 'command not found'},
            duration_seconds=0.5,
        )
        assert outcome.success is False


# ═══════════════════════════════════════════════════════════════════════
# MonitoredAction dataclass
# ═══════════════════════════════════════════════════════════════════════

class TestMonitoredAction:
    """Tests for the MonitoredAction dataclass."""

    def test_started_at_auto_set(self):
        m = MonitoredAction(action_id='a1', plan_id='p1', action_type='shell')
        assert m.started_at > 0

    def test_elapsed_seconds(self):
        m = MonitoredAction(
            action_id='a1', plan_id='p1', action_type='shell',
            started_at=time.time() - 5.0,
        )
        assert m.elapsed_seconds() >= 4.9

    def test_is_timed_out_false(self):
        m = MonitoredAction(
            action_id='a1', plan_id='p1', action_type='shell',
            timeout_seconds=300.0,
        )
        assert m.is_timed_out() is False

    def test_is_timed_out_true(self):
        m = MonitoredAction(
            action_id='a1', plan_id='p1', action_type='shell',
            started_at=time.time() - 500.0,
            timeout_seconds=300.0,
        )
        assert m.is_timed_out() is True

    def test_to_dict(self):
        m = MonitoredAction(action_id='a1', plan_id='p1', action_type='shell')
        d = m.to_dict()
        assert d['action_id'] == 'a1'
        assert d['plan_id'] == 'p1'
        assert 'elapsed_seconds' in d
        assert 'resource_usage' in d


# ═══════════════════════════════════════════════════════════════════════
# ValidationResult dataclass
# ═══════════════════════════════════════════════════════════════════════

class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    def test_to_dict(self):
        r = ValidationResult(action_id='a1', approved=True, reason='ok')
        d = r.to_dict()
        assert d['action_id'] == 'a1'
        assert d['approved'] is True
        assert d['reason'] == 'ok'


# ═══════════════════════════════════════════════════════════════════════
# ReplayEntry dataclass
# ═══════════════════════════════════════════════════════════════════════

class TestReplayEntry:
    """Tests for the ReplayEntry dataclass."""

    def test_timestamp_auto_set(self):
        e = ReplayEntry(situation='task', system_used='automation', action_type='shell')
        assert e.timestamp > 0

    def test_to_dict(self):
        e = ReplayEntry(
            situation='deploy service',
            system_used='automation',
            action_type='shell',
            outcome_success=True,
            duration_seconds=3.456789,
            priority=2.0,
        )
        d = e.to_dict()
        assert d['situation'] == 'deploy service'
        assert d['duration_seconds'] == 3.457
        assert d['priority'] == 2.0
