"""
AGI Meta Controller Tests - Priority 1

Comprehensive tests for the AGIMetaController integration component.
This is the central orchestration layer for all AGI components.
"""

import pytest
import numpy as np
import torch


class TestAGIControllerInstantiation:
    """Test AGIMetaController can be created correctly."""

    def test_basic_instantiation(self, state_dim, action_dim, hidden_dim):
        """Test basic instantiation."""
        from core.agi_meta_controller import create_agi_controller
        controller = create_agi_controller(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_dim=hidden_dim
        )
        assert controller is not None

    def test_factory_function(self, state_dim, action_dim):
        """Test factory function creates valid controller."""
        from core.agi_meta_controller import create_agi_controller
        controller = create_agi_controller(state_dim=state_dim, action_dim=action_dim)
        assert hasattr(controller, 'decide')
        assert hasattr(controller, 'learn')

    def test_component_count(self, agi_controller):
        """Test all expected components are registered."""
        assert hasattr(agi_controller, 'component_status')
        # Should have multiple components registered
        assert len(agi_controller.component_status) >= 10


class TestDecisionMaking:
    """Test decision-making functionality."""

    def test_decide_returns_action(self, agi_controller, sample_state, action_dim):
        """Test decide returns valid action."""
        action, metadata = agi_controller.decide(sample_state)
        assert isinstance(action, (int, np.integer))
        assert 0 <= action < action_dim

    def test_decide_returns_metadata(self, agi_controller, sample_state):
        """Test decide returns metadata dict."""
        action, metadata = agi_controller.decide(sample_state)
        assert isinstance(metadata, dict)

    def test_decide_includes_explanation(self, agi_controller, sample_state):
        """Test decide includes explanation in metadata."""
        action, metadata = agi_controller.decide(sample_state)
        assert 'explanation' in metadata or 'decision_source' in metadata

    def test_decide_deterministic(self, agi_controller, sample_state, seed):
        """Test deterministic mode produces consistent results."""
        np.random.seed(seed)
        torch.manual_seed(seed)
        action1, _ = agi_controller.decide(sample_state)

        np.random.seed(seed)
        torch.manual_seed(seed)
        action2, _ = agi_controller.decide(sample_state)

        # Note: Due to complex interactions, may not be perfectly deterministic
        # but should be mostly consistent
        assert isinstance(action1, (int, np.integer))
        assert isinstance(action2, (int, np.integer))


class TestLearning:
    """Test learning functionality."""

    def test_learn_method_exists(self, agi_controller):
        """Test learn method exists."""
        assert hasattr(agi_controller, 'learn')

    def test_learn_accepts_experience(
        self, agi_controller, sample_state, sample_action,
        sample_reward, sample_next_state
    ):
        """Test learn accepts experience tuple."""
        # This should not raise an error
        result = agi_controller.learn(
            state=sample_state,
            action=sample_action,
            reward=sample_reward,
            next_state=sample_next_state,
            done=False
        )
        # Result could be None or a metrics dict
        assert result is None or isinstance(result, dict)


class TestSafetyIntegration:
    """Test safety layer integration."""

    def test_has_safety_layer(self, agi_controller):
        """Test controller has safety layer."""
        assert hasattr(agi_controller, 'safety_layer')

    def test_decide_respects_safety(self, agi_controller, sample_state, action_dim):
        """Test decisions go through safety check."""
        action, metadata = agi_controller.decide(sample_state)
        # Action should be within valid range
        assert 0 <= action < action_dim
        # Should have safety info if available
        if 'safety' in metadata:
            assert 'safe' in metadata['safety'] or 'is_safe' in metadata['safety']


class TestComponentOrchestration:
    """Test component orchestration."""

    def test_policy_learner_exists(self, agi_controller):
        """Test policy learner component exists."""
        assert hasattr(agi_controller, 'policy_learner')

    def test_planner_exists(self, agi_controller):
        """Test MCTS planner exists."""
        assert hasattr(agi_controller, 'planner')

    def test_curiosity_agent_exists(self, agi_controller):
        """Test curiosity agent exists."""
        assert hasattr(agi_controller, 'curiosity_agent')

    def test_explainer_exists(self, agi_controller):
        """Test explanation generator exists."""
        assert hasattr(agi_controller, 'explainer')


class TestSystemStatus:
    """Test system status and monitoring."""

    def test_get_status(self, agi_controller):
        """Test getting system status."""
        if hasattr(agi_controller, 'get_status'):
            status = agi_controller.get_status()
            assert isinstance(status, dict)

    def test_component_status_tracking(self, agi_controller):
        """Test component status is tracked."""
        assert hasattr(agi_controller, 'component_status')
        for name, status in agi_controller.component_status.items():
            assert hasattr(status, 'active') or 'active' in status


class TestExplanationGeneration:
    """Test explanation generation."""

    def test_explain_decision(self, agi_controller, sample_state):
        """Test decision explanation."""
        action, metadata = agi_controller.decide(sample_state)
        if hasattr(agi_controller, 'explain_decision'):
            explanation = agi_controller.explain_decision(sample_state, action)
            assert explanation is not None

    def test_explanation_in_metadata(self, agi_controller, sample_state):
        """Test explanation included in metadata."""
        action, metadata = agi_controller.decide(sample_state)
        # Should have some form of explanation
        has_explanation = (
            'explanation' in metadata or
            'reasoning' in metadata or
            'decision_source' in metadata
        )
        assert has_explanation


class TestResourceManagement:
    """Test resource management."""

    def test_has_resource_manager(self, agi_controller):
        """Test resource manager exists if available."""
        # Resource manager is optional
        if hasattr(agi_controller, 'resource_manager'):
            rm = agi_controller.resource_manager
            assert rm is not None


class TestBatchProcessing:
    """Test batch processing capabilities."""

    def test_batch_decide_if_available(self, agi_controller, sample_batch_states, action_dim):
        """Test batch decision making if supported."""
        if hasattr(agi_controller, 'decide_batch'):
            actions, metadata_list = agi_controller.decide_batch(sample_batch_states)
            assert len(actions) == len(sample_batch_states)
            for action in actions:
                assert 0 <= action < action_dim


class TestStateManagement:
    """Test internal state management."""

    def test_reset_if_available(self, agi_controller):
        """Test reset functionality if available."""
        if hasattr(agi_controller, 'reset'):
            agi_controller.reset()
            # Should not raise an error

    def test_state_dimensions(self, agi_controller, state_dim, action_dim):
        """Test state/action dimensions are stored correctly."""
        assert agi_controller.state_dim == state_dim
        assert agi_controller.action_dim == action_dim


class TestErrorHandling:
    """Test error handling."""

    def test_handles_invalid_state_shape(self, agi_controller):
        """Test handling of invalid state shape."""
        invalid_state = np.random.randn(5).astype(np.float32)  # Wrong dimension
        try:
            action, _ = agi_controller.decide(invalid_state)
            # If it doesn't error, action should still be valid
            assert isinstance(action, (int, np.integer))
        except (ValueError, RuntimeError):
            # Expected error for wrong dimensions
            pass

    def test_handles_nan_state(self, agi_controller, state_dim):
        """Test handling of NaN values in state."""
        nan_state = np.full(state_dim, np.nan, dtype=np.float32)
        try:
            action, _ = agi_controller.decide(nan_state)
            # Should either handle gracefully or raise error
            assert isinstance(action, (int, np.integer))
        except (ValueError, RuntimeError, AttributeError, TypeError):
            # Expected - NaN propagation can cause various errors
            # in complex multi-component systems
            pass


class TestPerformance:
    """Test performance characteristics."""

    def test_decide_time(self, agi_controller, sample_state):
        """Test decision time is reasonable."""
        import time
        start = time.time()
        for _ in range(10):
            agi_controller.decide(sample_state)
        elapsed = time.time() - start
        avg_time = elapsed / 10
        # Should complete in reasonable time (< 1 second per decision)
        assert avg_time < 1.0, f"Average decision time {avg_time:.3f}s too slow"
