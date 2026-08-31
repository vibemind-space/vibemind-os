"""
Tests for Safety Regulation System (V2 Phase 3: P3.44-45)

Tests cover:
- AutonomyBudgetManager: Category-specific rate limits
- SafetyGovernor: Veto system for dangerous actions
- SafetyRegulation: Combined budget + governor
- YAML configuration support
"""

import pytest
import time
import json
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.safety_regulation import (
    BudgetCategory,
    BudgetPeriod,
    BudgetLimit,
    AutonomyBudgetManager,
    SafetyVerdict,
    VetoReason,
    SafetyCheckResult,
    SafetyGovernor,
    SafetyRegulation,
)


# ──────────────────────────────────────────────────────────────────────────────
# BudgetLimit Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestBudgetLimit:
    """Tests for individual BudgetLimit."""

    def test_initial_count_zero(self):
        limit = BudgetLimit(
            category=BudgetCategory.SHELL_COMMAND,
            period=BudgetPeriod.HOUR,
            max_count=50,
        )
        assert limit.count_in_window() == 0
        assert limit.remaining() == 50
        assert limit.is_exhausted() is False

    def test_record_and_count(self):
        limit = BudgetLimit(
            category=BudgetCategory.SHELL_COMMAND,
            period=BudgetPeriod.HOUR,
            max_count=50,
        )
        limit.record()
        limit.record()
        limit.record()
        assert limit.count_in_window() == 3
        assert limit.remaining() == 47

    def test_exhaustion(self):
        limit = BudgetLimit(
            category=BudgetCategory.FILE_WRITE,
            period=BudgetPeriod.HOUR,
            max_count=3,
        )
        for _ in range(3):
            limit.record()
        assert limit.is_exhausted() is True
        assert limit.remaining() == 0

    def test_utilization(self):
        limit = BudgetLimit(
            category=BudgetCategory.FILE_WRITE,
            period=BudgetPeriod.HOUR,
            max_count=10,
        )
        for _ in range(5):
            limit.record()
        assert limit.utilization() == 0.5

    def test_window_expiry(self):
        limit = BudgetLimit(
            category=BudgetCategory.SHELL_COMMAND,
            period=BudgetPeriod.MINUTE,
            max_count=10,
        )
        # Record actions 2 minutes ago (outside 1-minute window)
        old_time = time.time() - 150
        for _ in range(5):
            limit.record(old_time)

        # Should all have expired
        assert limit.count_in_window() == 0
        assert limit.remaining() == 10

    def test_to_dict(self):
        limit = BudgetLimit(
            category=BudgetCategory.CODING_JOB,
            period=BudgetPeriod.DAY,
            max_count=5,
            description="Max 5 coding jobs/day",
        )
        limit.record()
        d = limit.to_dict()
        assert d['category'] == 'coding_job'
        assert d['period'] == 'day'
        assert d['max_count'] == 5
        assert d['current_count'] == 1
        assert d['remaining'] == 4
        assert d['exhausted'] is False


# ──────────────────────────────────────────────────────────────────────────────
# AutonomyBudgetManager Tests (P3.44)
# ──────────────────────────────────────────────────────────────────────────────

class TestAutonomyBudgetManager:
    """Tests for the AutonomyBudgetManager."""

    def test_initial_all_allowed(self):
        mgr = AutonomyBudgetManager()
        for cat in BudgetCategory:
            assert mgr.can_perform(cat) is True

    def test_shell_command_budget(self):
        mgr = AutonomyBudgetManager(shell_commands_per_hour=3)
        for _ in range(3):
            mgr.record_action(BudgetCategory.SHELL_COMMAND)
        assert mgr.can_perform(BudgetCategory.SHELL_COMMAND) is False

    def test_file_write_budget(self):
        mgr = AutonomyBudgetManager(file_writes_per_hour=2)
        mgr.record_action(BudgetCategory.FILE_WRITE)
        mgr.record_action(BudgetCategory.FILE_WRITE)
        assert mgr.can_perform(BudgetCategory.FILE_WRITE) is False

    def test_coding_job_budget(self):
        mgr = AutonomyBudgetManager(coding_jobs_per_day=1)
        mgr.record_action(BudgetCategory.CODING_JOB)
        assert mgr.can_perform(BudgetCategory.CODING_JOB) is False

    def test_llm_token_budget(self):
        mgr = AutonomyBudgetManager(llm_tokens_per_minute=100)
        for _ in range(100):
            mgr.record_action(BudgetCategory.LLM_TOKEN)
        assert mgr.can_perform(BudgetCategory.LLM_TOKEN) is False

    def test_cross_category_independence(self):
        """Exhausting one category shouldn't affect others."""
        mgr = AutonomyBudgetManager(shell_commands_per_hour=2, file_writes_per_hour=10)
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        assert mgr.can_perform(BudgetCategory.SHELL_COMMAND) is False
        assert mgr.can_perform(BudgetCategory.FILE_WRITE) is True

    def test_should_escalate(self):
        mgr = AutonomyBudgetManager(
            shell_commands_per_hour=10,
            escalation_threshold=0.8,
        )
        for _ in range(9):
            mgr.record_action(BudgetCategory.SHELL_COMMAND)
        assert mgr.should_escalate(BudgetCategory.SHELL_COMMAND) is True

    def test_should_not_escalate_below_threshold(self):
        mgr = AutonomyBudgetManager(
            shell_commands_per_hour=10,
            escalation_threshold=0.8,
        )
        for _ in range(5):
            mgr.record_action(BudgetCategory.SHELL_COMMAND)
        assert mgr.should_escalate(BudgetCategory.SHELL_COMMAND) is False

    def test_denial_history(self):
        mgr = AutonomyBudgetManager(shell_commands_per_hour=1)
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        mgr.can_perform(BudgetCategory.SHELL_COMMAND)
        assert len(mgr._denial_history) == 1
        assert mgr._total_denied == 1

    def test_get_category_remaining(self):
        mgr = AutonomyBudgetManager(shell_commands_per_hour=10)
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        assert mgr.get_category_remaining(BudgetCategory.SHELL_COMMAND) == 8

    def test_reset_category(self):
        mgr = AutonomyBudgetManager(shell_commands_per_hour=2)
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        assert mgr.can_perform(BudgetCategory.SHELL_COMMAND) is False

        mgr.reset_category(BudgetCategory.SHELL_COMMAND)
        assert mgr.can_perform(BudgetCategory.SHELL_COMMAND) is True

    def test_record_action_multiple(self):
        mgr = AutonomyBudgetManager(llm_tokens_per_minute=100)
        mgr.record_action(BudgetCategory.LLM_TOKEN, count=50)
        assert mgr.get_category_remaining(BudgetCategory.LLM_TOKEN) == 50

    def test_get_state(self):
        mgr = AutonomyBudgetManager()
        mgr.record_action(BudgetCategory.SHELL_COMMAND)
        state = mgr.get_state()
        assert state['name'] == 'AutonomyBudgetManager'
        assert state['total_allowed'] == 1
        assert 'budgets' in state
        assert 'shell_hour' in state['budgets']


# ──────────────────────────────────────────────────────────────────────────────
# SafetyCheckResult Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSafetyCheckResult:
    """Tests for SafetyCheckResult."""

    def test_approve(self):
        result = SafetyCheckResult(verdict=SafetyVerdict.APPROVE)
        assert result.verdict == SafetyVerdict.APPROVE
        assert result.reason is None

    def test_deny_with_reason(self):
        result = SafetyCheckResult(
            verdict=SafetyVerdict.DENY,
            reason=VetoReason.DESTRUCTIVE_COMMAND,
            message="Dangerous!",
        )
        assert result.verdict == SafetyVerdict.DENY
        assert result.reason == VetoReason.DESTRUCTIVE_COMMAND

    def test_to_dict(self):
        result = SafetyCheckResult(
            verdict=SafetyVerdict.ESCALATE,
            reason=VetoReason.PATH_VIOLATION,
            message="Outside allowed paths",
            confidence=0.9,
        )
        d = result.to_dict()
        assert d['verdict'] == 'escalate'
        assert d['reason'] == 'path_violation'
        assert d['confidence'] == 0.9


# ──────────────────────────────────────────────────────────────────────────────
# SafetyGovernor Tests (P3.45)
# ──────────────────────────────────────────────────────────────────────────────

class TestSafetyGovernor:
    """Tests for the SafetyGovernor."""

    def test_safe_action_approved(self):
        gov = SafetyGovernor()
        result = gov.check_action("Run pytest tests/test_core.py")
        assert result.verdict == SafetyVerdict.APPROVE

    def test_rm_rf_denied(self):
        gov = SafetyGovernor()
        result = gov.check_action("rm -rf /")
        assert result.verdict == SafetyVerdict.DENY
        assert result.reason == VetoReason.DESTRUCTIVE_COMMAND

    def test_rm_rf_star_denied(self):
        gov = SafetyGovernor()
        result = gov.check_action("rm -rf *")
        assert result.verdict == SafetyVerdict.DENY

    def test_drop_table_denied(self):
        gov = SafetyGovernor()
        result = gov.check_action("DROP TABLE users")
        assert result.verdict == SafetyVerdict.DENY
        assert result.reason == VetoReason.DESTRUCTIVE_COMMAND

    def test_truncate_table_denied(self):
        gov = SafetyGovernor()
        result = gov.check_action("TRUNCATE TABLE orders")
        assert result.verdict == SafetyVerdict.DENY

    def test_delete_without_where_denied(self):
        gov = SafetyGovernor()
        result = gov.check_action("DELETE FROM users")
        assert result.verdict == SafetyVerdict.DENY

    def test_delete_with_where_approved(self):
        gov = SafetyGovernor()
        result = gov.check_action("DELETE FROM users WHERE id = 5")
        assert result.verdict == SafetyVerdict.APPROVE

    def test_format_drive_denied(self):
        gov = SafetyGovernor()
        result = gov.check_action("format C:")
        assert result.verdict == SafetyVerdict.DENY

    def test_shutdown_denied(self):
        gov = SafetyGovernor()
        result = gov.check_action("shutdown /s /t 0")
        assert result.verdict == SafetyVerdict.DENY

    def test_case_insensitive(self):
        gov = SafetyGovernor()
        result = gov.check_action("DROP TABLE Users")
        assert result.verdict == SafetyVerdict.DENY

    def test_path_within_allowed(self):
        gov = SafetyGovernor(
            allowed_paths=['/home/user/projects'],
        )
        result = gov.check_action(
            "Write file",
            target_path='/home/user/projects/test.py',
        )
        assert result.verdict == SafetyVerdict.APPROVE

    def test_path_outside_allowed_escalates(self):
        gov = SafetyGovernor(
            allowed_paths=['/home/user/projects'],
        )
        result = gov.check_action(
            "Write file",
            target_path='/etc/passwd',
        )
        assert result.verdict == SafetyVerdict.ESCALATE
        assert result.reason == VetoReason.PATH_VIOLATION

    def test_path_check_disabled(self):
        gov = SafetyGovernor(
            allowed_paths=['/home/user'],
            enable_path_check=False,
        )
        result = gov.check_action(
            "Write file",
            target_path='/etc/passwd',
        )
        assert result.verdict == SafetyVerdict.APPROVE

    def test_no_allowed_paths_means_all_allowed(self):
        gov = SafetyGovernor(allowed_paths=[])
        result = gov.check_action(
            "Write file",
            target_path='/any/path',
        )
        assert result.verdict == SafetyVerdict.APPROVE

    def test_known_host_allowed(self):
        gov = SafetyGovernor()
        result = gov.check_action(
            "HTTP request",
            target_host='localhost',
        )
        assert result.verdict == SafetyVerdict.APPROVE

    def test_unknown_host_escalates(self):
        gov = SafetyGovernor()
        result = gov.check_action(
            "HTTP request",
            target_host='evil-server.com',
        )
        assert result.verdict == SafetyVerdict.ESCALATE
        assert result.reason == VetoReason.UNKNOWN_HOST

    def test_host_check_disabled(self):
        gov = SafetyGovernor(enable_host_check=False)
        result = gov.check_action(
            "HTTP request",
            target_host='evil-server.com',
        )
        assert result.verdict == SafetyVerdict.APPROVE

    def test_cpu_within_limit(self):
        gov = SafetyGovernor(max_cpu_seconds=300.0)
        result = gov.check_action(
            "Run computation",
            estimated_cpu_seconds=100.0,
        )
        assert result.verdict == SafetyVerdict.APPROVE

    def test_cpu_over_limit_escalates(self):
        gov = SafetyGovernor(max_cpu_seconds=300.0)
        result = gov.check_action(
            "Run heavy computation",
            estimated_cpu_seconds=600.0,
        )
        assert result.verdict == SafetyVerdict.ESCALATE
        assert result.reason == VetoReason.CPU_LIMIT_EXCEEDED

    def test_sensitive_data_escalates(self):
        gov = SafetyGovernor()
        result = gov.check_action("Set password = myS3cretP@ss")
        assert result.verdict == SafetyVerdict.ESCALATE
        assert result.reason == VetoReason.SENSITIVE_DATA

    def test_api_key_escalates(self):
        gov = SafetyGovernor()
        result = gov.check_action("Use api_key=sk_live_12345678901234567890")
        assert result.verdict == SafetyVerdict.ESCALATE
        assert result.reason == VetoReason.SENSITIVE_DATA

    def test_normal_text_not_sensitive(self):
        gov = SafetyGovernor()
        result = gov.check_action("Analyze code quality metrics")
        assert result.verdict == SafetyVerdict.APPROVE

    def test_add_allowed_path(self):
        gov = SafetyGovernor(allowed_paths=['/home'])
        gov.add_allowed_path('/tmp')
        assert '/tmp' in gov.allowed_paths

    def test_add_allowed_host(self):
        gov = SafetyGovernor()
        gov.add_allowed_host('api.github.com')
        assert any(h.lower() == 'api.github.com' for h in gov.allowed_hosts)

    def test_custom_destructive_pattern(self):
        gov = SafetyGovernor(
            destructive_pattern_override=[r'DANGER_COMMAND'],
        )
        result = gov.check_action("Execute DANGER_COMMAND now")
        assert result.verdict == SafetyVerdict.DENY

    def test_destructive_check_disabled(self):
        gov = SafetyGovernor(enable_destructive_check=False)
        result = gov.check_action("rm -rf /")
        assert result.verdict == SafetyVerdict.APPROVE

    def test_statistics_tracked(self):
        gov = SafetyGovernor()
        gov.check_action("safe action")
        gov.check_action("rm -rf /")
        gov.check_action("safe again")

        assert gov._total_checks == 3
        assert gov._total_approved == 2
        assert gov._total_denied == 1

    def test_get_state(self):
        gov = SafetyGovernor()
        gov.check_action("safe action")
        gov.check_action("rm -rf /")
        state = gov.get_state()
        assert state['name'] == 'SafetyGovernor'
        assert state['total_checks'] == 2
        assert state['total_approved'] == 1
        assert state['total_denied'] == 1
        assert 'recent_vetoes' in state


# ──────────────────────────────────────────────────────────────────────────────
# SafetyRegulation Combined Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSafetyRegulation:
    """Tests for the combined SafetyRegulation system."""

    def test_safe_action_within_budget(self):
        sr = SafetyRegulation()
        result = sr.check_and_record("Run tests", BudgetCategory.SHELL_COMMAND)
        assert result.verdict == SafetyVerdict.APPROVE

    def test_dangerous_action_denied(self):
        sr = SafetyRegulation()
        result = sr.check_and_record("rm -rf /", BudgetCategory.SHELL_COMMAND)
        assert result.verdict == SafetyVerdict.DENY

    def test_budget_exhaustion_escalates(self):
        sr = SafetyRegulation(
            budget=AutonomyBudgetManager(shell_commands_per_hour=2),
        )
        sr.check_and_record("cmd 1", BudgetCategory.SHELL_COMMAND)
        sr.check_and_record("cmd 2", BudgetCategory.SHELL_COMMAND)
        result = sr.check_and_record("cmd 3", BudgetCategory.SHELL_COMMAND)
        assert result.verdict == SafetyVerdict.ESCALATE
        assert result.reason == VetoReason.RATE_LIMITED

    def test_skip_budget_for_user_request(self):
        sr = SafetyRegulation(
            budget=AutonomyBudgetManager(shell_commands_per_hour=1),
        )
        sr.check_and_record("cmd 1", BudgetCategory.SHELL_COMMAND)

        # Budget exhausted, but skip_budget bypasses it
        result = sr.check_and_record(
            "user cmd",
            BudgetCategory.SHELL_COMMAND,
            skip_budget_check=True,
        )
        assert result.verdict == SafetyVerdict.APPROVE

    def test_governor_check_before_budget_record(self):
        """A denied action shouldn't consume budget."""
        sr = SafetyRegulation(
            budget=AutonomyBudgetManager(shell_commands_per_hour=5),
        )
        # Dangerous action should be denied without budget consumption
        result = sr.check_and_record("rm -rf /", BudgetCategory.SHELL_COMMAND)
        assert result.verdict == SafetyVerdict.DENY

        # Budget should still have 5 remaining (nothing consumed)
        assert sr.budget.get_category_remaining(BudgetCategory.SHELL_COMMAND) == 5

    def test_path_and_budget_combined(self):
        sr = SafetyRegulation(
            governor=SafetyGovernor(allowed_paths=['/home/user']),
        )
        result = sr.check_and_record(
            "Write config",
            BudgetCategory.FILE_WRITE,
            target_path='/etc/config',
        )
        assert result.verdict == SafetyVerdict.ESCALATE
        assert result.reason == VetoReason.PATH_VIOLATION

    def test_get_state(self):
        sr = SafetyRegulation()
        sr.check_and_record("safe action", BudgetCategory.TASK_EXECUTION)
        state = sr.get_state()
        assert state['total_checks'] == 1
        assert 'budget' in state
        assert 'governor' in state

    def test_multiple_categories(self):
        sr = SafetyRegulation(
            budget=AutonomyBudgetManager(
                shell_commands_per_hour=2,
                file_writes_per_hour=1,
            ),
        )
        sr.check_and_record("cmd 1", BudgetCategory.SHELL_COMMAND)
        sr.check_and_record("write 1", BudgetCategory.FILE_WRITE)
        sr.check_and_record("cmd 2", BudgetCategory.SHELL_COMMAND)

        # Shell exhausted
        result_shell = sr.check_and_record("cmd 3", BudgetCategory.SHELL_COMMAND)
        assert result_shell.verdict == SafetyVerdict.ESCALATE

        # File write also exhausted
        result_file = sr.check_and_record("write 2", BudgetCategory.FILE_WRITE)
        assert result_file.verdict == SafetyVerdict.ESCALATE


# ──────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSafetyIntegration:
    """End-to-end integration tests."""

    def test_full_lifecycle(self):
        """Full lifecycle: check, record, exhaust, escalate."""
        sr = SafetyRegulation(
            budget=AutonomyBudgetManager(shell_commands_per_hour=3),
            governor=SafetyGovernor(allowed_paths=['/home/user']),
        )

        # Safe action within budget
        r1 = sr.check_and_record("echo hello", BudgetCategory.SHELL_COMMAND)
        assert r1.verdict == SafetyVerdict.APPROVE

        # Dangerous action blocked regardless of budget
        r2 = sr.check_and_record("rm -rf /", BudgetCategory.SHELL_COMMAND)
        assert r2.verdict == SafetyVerdict.DENY

        # Path violation escalated
        r3 = sr.check_and_record(
            "write config",
            BudgetCategory.FILE_WRITE,
            target_path='/etc/secret',
        )
        assert r3.verdict == SafetyVerdict.ESCALATE

        # Continue using shell budget
        sr.check_and_record("echo 2", BudgetCategory.SHELL_COMMAND)
        sr.check_and_record("echo 3", BudgetCategory.SHELL_COMMAND)

        # Budget now exhausted
        r4 = sr.check_and_record("echo 4", BudgetCategory.SHELL_COMMAND)
        assert r4.verdict == SafetyVerdict.ESCALATE

    def test_all_serializable(self):
        """All objects must be JSON-serializable."""
        sr = SafetyRegulation()
        sr.check_and_record("safe", BudgetCategory.TASK_EXECUTION)
        sr.check_and_record("rm -rf /", BudgetCategory.SHELL_COMMAND)

        state = sr.get_state()
        serialized = json.dumps(state)
        assert len(serialized) > 100
        deserialized = json.loads(serialized)
        assert deserialized['total_checks'] == 2

    def test_verdicts_cover_all_cases(self):
        """Verify we can get APPROVE, DENY, and ESCALATE verdicts."""
        sr = SafetyRegulation(
            budget=AutonomyBudgetManager(shell_commands_per_hour=1),
            governor=SafetyGovernor(allowed_paths=['/home']),
        )

        # APPROVE
        r1 = sr.check_and_record("safe action", BudgetCategory.TASK_EXECUTION)
        assert r1.verdict == SafetyVerdict.APPROVE

        # DENY
        r2 = sr.check_and_record("rm -rf /", BudgetCategory.SHELL_COMMAND)
        assert r2.verdict == SafetyVerdict.DENY

        # ESCALATE (budget exhaustion)
        sr.check_and_record("cmd", BudgetCategory.SHELL_COMMAND)
        r3 = sr.check_and_record("cmd2", BudgetCategory.SHELL_COMMAND)
        assert r3.verdict == SafetyVerdict.ESCALATE

    def test_error_resilience(self):
        """System should handle edge cases gracefully."""
        sr = SafetyRegulation()

        # Empty description
        r = sr.check_and_record("", BudgetCategory.TASK_EXECUTION)
        assert r.verdict == SafetyVerdict.APPROVE

        # Very long description
        long_desc = "x" * 10000
        r = sr.check_and_record(long_desc, BudgetCategory.TASK_EXECUTION)
        assert r.verdict == SafetyVerdict.APPROVE

        # None target path/host (should not crash)
        r = sr.check_and_record("test", BudgetCategory.TASK_EXECUTION,
                                target_path=None, target_host=None)
        assert r.verdict == SafetyVerdict.APPROVE


# ──────────────────────────────────────────────────────────────────────────────
# YAML Config Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSafetyRegulationYAML:
    """Tests for YAML configuration support."""

    def test_from_yaml_full(self):
        config = {
            'safety_regulation': {
                'shell_commands_per_hour': 30,
                'file_writes_per_hour': 5,
                'coding_jobs_per_day': 3,
                'llm_tokens_per_minute': 500,
                'network_calls_per_hour': 20,
                'tasks_per_hour': 40,
                'escalation_threshold': 0.9,
                'allowed_paths': ['/home/user', '/tmp'],
                'allowed_hosts': ['localhost', 'api.github.com'],
                'max_cpu_seconds': 600.0,
                'enable_path_check': True,
                'enable_host_check': True,
                'enable_destructive_check': True,
                'enable_cpu_check': False,
            },
        }
        sr = SafetyRegulation.from_yaml(config)

        # Budget checks
        assert sr.budget._limits['shell_hour'].max_count == 30
        assert sr.budget._limits['file_hour'].max_count == 5
        assert sr.budget._limits['coding_day'].max_count == 3
        assert sr.budget._limits['llm_minute'].max_count == 500
        assert sr.budget.escalation_threshold == 0.9

        # Governor checks
        assert '/home/user' in sr.governor.allowed_paths
        assert '/tmp' in sr.governor.allowed_paths
        assert 'api.github.com' in sr.governor.allowed_hosts
        assert sr.governor.max_cpu_seconds == 600.0
        assert sr.governor.enable_cpu_check is False

    def test_from_yaml_empty(self):
        sr = SafetyRegulation.from_yaml({})
        assert sr.budget._limits['shell_hour'].max_count == 50
        assert sr.governor.max_cpu_seconds == 300.0

    def test_from_yaml_partial(self):
        config = {
            'safety_regulation': {
                'shell_commands_per_hour': 25,
            },
        }
        sr = SafetyRegulation.from_yaml(config)
        assert sr.budget._limits['shell_hour'].max_count == 25
        assert sr.budget._limits['file_hour'].max_count == 10  # Default

    def test_from_yaml_functional(self):
        """Created-from-YAML system should function correctly."""
        config = {
            'safety_regulation': {
                'shell_commands_per_hour': 2,
            },
        }
        sr = SafetyRegulation.from_yaml(config)

        # Should allow 2 commands
        r1 = sr.check_and_record("cmd 1", BudgetCategory.SHELL_COMMAND)
        assert r1.verdict == SafetyVerdict.APPROVE
        r2 = sr.check_and_record("cmd 2", BudgetCategory.SHELL_COMMAND)
        assert r2.verdict == SafetyVerdict.APPROVE

        # Third should be rate-limited
        r3 = sr.check_and_record("cmd 3", BudgetCategory.SHELL_COMMAND)
        assert r3.verdict == SafetyVerdict.ESCALATE
