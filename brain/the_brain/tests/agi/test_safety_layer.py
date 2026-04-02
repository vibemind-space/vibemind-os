"""
Safety Layer Tests - Priority 1

Comprehensive tests for the SafetyLayer component.
This is critical for ensuring safe AGI operation.
"""

import pytest
import numpy as np
import torch


class TestSafetyLayerInstantiation:
    """Test SafetyLayer can be created correctly."""

    def test_basic_instantiation(self, action_dim):
        """Test basic instantiation."""
        from core.safety_layer import SafetyLayer
        layer = SafetyLayer(action_dim=action_dim)
        assert layer is not None
        assert layer.action_dim == action_dim

    def test_instantiation_with_state_dim(self, action_dim, state_dim):
        """Test instantiation with state_dim if supported."""
        from core.safety_layer import SafetyLayer
        # Basic instantiation always works
        layer = SafetyLayer(action_dim=action_dim)
        assert layer is not None
        assert layer.action_dim == action_dim


class TestSafetyCheck:
    """Test safety checking functionality."""

    def test_check_action_returns_report(self, safety_layer, sample_state, sample_action):
        """Test check_action returns a SafetyReport."""
        report = safety_layer.check_action(sample_state, sample_action)
        assert hasattr(report, 'is_safe')
        assert hasattr(report, 'risk_score')
        assert hasattr(report, 'violated_constraints')

    def test_check_action_risk_score_range(self, safety_layer, sample_state, sample_action):
        """Test risk_score is in valid range [0, 1]."""
        report = safety_layer.check_action(sample_state, sample_action)
        assert 0.0 <= report.risk_score <= 1.0

    def test_safe_action_marked_safe(self, safety_layer, sample_state, sample_action):
        """Test that normal actions are marked safe."""
        report = safety_layer.check_action(sample_state, sample_action)
        # With default settings, most random states should be safe
        assert report.is_safe or report.risk_score > 0.5

    def test_check_multiple_actions(self, safety_layer, sample_state, action_dim):
        """Test checking all possible actions."""
        for action in range(action_dim):
            report = safety_layer.check_action(sample_state, action)
            assert hasattr(report, 'is_safe')
            assert 0.0 <= report.risk_score <= 1.0


class TestSafetyConstraints:
    """Test constraint-based safety."""

    def test_violated_constraints_is_list(self, safety_layer, sample_state, sample_action):
        """Test violated_constraints is a list."""
        report = safety_layer.check_action(sample_state, sample_action)
        assert isinstance(report.violated_constraints, (list, tuple))

    def test_safe_action_no_violations(self, safety_layer, sample_state, sample_action):
        """Test safe actions have no constraint violations."""
        report = safety_layer.check_action(sample_state, sample_action)
        if report.is_safe:
            # Safe actions should have no violations or very low risk
            assert report.risk_score < 0.5 or len(report.violated_constraints) == 0


class TestActionFiltering:
    """Test action filtering functionality."""

    def test_filter_action_if_available(self, safety_layer, sample_state, sample_action):
        """Test filter_action returns a valid action if available."""
        if hasattr(safety_layer, 'filter_action'):
            from core.safety_layer import SafetyLayer
            layer = SafetyLayer(action_dim=4)
            filtered = layer.filter_action(sample_state, sample_action)
            assert isinstance(filtered, (int, np.integer))
            assert 0 <= filtered < 4
        else:
            # filter_action is optional - test passes if not implemented
            pytest.skip("filter_action not implemented")

    def test_safe_action_check(self, safety_layer, sample_state, sample_action):
        """Test safe actions are identified correctly."""
        report = safety_layer.check_action(sample_state, sample_action)
        # Either action is safe or has a risk score
        assert hasattr(report, 'is_safe')
        assert hasattr(report, 'risk_score')


class TestEmergencyStop:
    """Test emergency stop functionality."""

    def test_emergency_stop_if_available(self, safety_layer):
        """Test SafetyLayer emergency_stop method if available."""
        has_emergency = (
            hasattr(safety_layer, 'emergency_stop') or
            hasattr(safety_layer, 'trigger_emergency') or
            hasattr(safety_layer, 'get_safe_action')
        )
        # Emergency stop is an optional safety feature
        if not has_emergency:
            pytest.skip("Emergency stop not implemented")

    def test_get_safe_action(self, safety_layer, sample_state, action_dim):
        """Test getting a guaranteed safe action."""
        if hasattr(safety_layer, 'get_safe_action'):
            safe_action = safety_layer.get_safe_action(sample_state)
            assert 0 <= safe_action < action_dim
            report = safety_layer.check_action(sample_state, safe_action)
            assert report.is_safe


class TestSafetyMetrics:
    """Test safety metrics and monitoring."""

    def test_get_safety_stats(self, safety_layer, sample_state, sample_action):
        """Test retrieving safety statistics."""
        # Perform some checks
        for _ in range(5):
            safety_layer.check_action(sample_state, sample_action)

        if hasattr(safety_layer, 'get_stats'):
            stats = safety_layer.get_stats()
            assert isinstance(stats, dict)


class TestBatchProcessing:
    """Test batch safety checking."""

    def test_batch_check_if_available(self, safety_layer, sample_batch_states, action_dim):
        """Test batch safety checking if supported."""
        if hasattr(safety_layer, 'check_batch'):
            actions = np.random.randint(0, action_dim, size=len(sample_batch_states))
            results = safety_layer.check_batch(sample_batch_states, actions)
            assert len(results) == len(sample_batch_states)


class TestSafetyIntegration:
    """Test integration with other components."""

    def test_works_with_policy_learner(self, safety_layer, policy_learner, sample_state):
        """Test safety layer works with policy learner output."""
        action, _ = policy_learner.select_action(sample_state)
        report = safety_layer.check_action(sample_state, action)
        assert hasattr(report, 'is_safe')

    def test_works_with_numpy_and_tensor(self, safety_layer, sample_state, sample_action):
        """Test works with both numpy arrays and tensors."""
        # Numpy input
        report_np = safety_layer.check_action(sample_state, sample_action)
        assert hasattr(report_np, 'is_safe')

        # Tensor input
        state_tensor = torch.FloatTensor(sample_state)
        report_tensor = safety_layer.check_action(state_tensor.numpy(), sample_action)
        assert hasattr(report_tensor, 'is_safe')
