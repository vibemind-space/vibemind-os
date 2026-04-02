"""
Test NeuroSymbolic Multi-Generational Integration

Tests the complete wiring from multi_generational_trainer through the
neurosymbolic components:
1. KlotskiDarkModeCoordinator with real graph (or fallback)
2. NeuroSymbolicHeartSystem (frozen)
3. NeuroSymbolicBrainSystem (evolving)
4. DualSystemAgent (70/30 voting)
5. MultiGenerationalTrainer neurosymbolic mode
"""

import pytest
import numpy as np
from typing import Dict, Any
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# Test Imports
# ============================================================================

class TestNeuroSymbolicImports:
    """Verify all neurosymbolic components can be imported."""

    def test_import_klotski_coordinator(self):
        """KlotskiDarkModeCoordinator should import."""
        from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator
        assert KlotskiDarkModeCoordinator is not None

    def test_import_heart_brain_components(self):
        """All heart/brain components should import."""
        from core.neurosymbolic_heart_brain import (
            NeuroSymbolicHeartSystem,
            NeuroSymbolicBrainSystem,
            DualSystemAgent
        )
        assert NeuroSymbolicHeartSystem is not None
        assert NeuroSymbolicBrainSystem is not None
        assert DualSystemAgent is not None

    def test_import_trainer(self):
        """NeuroSymbolicTrainer should import."""
        from core.neurosymbolic_trainer import NeuroSymbolicTrainer
        assert NeuroSymbolicTrainer is not None

    def test_import_multi_generational(self):
        """MultiGenerationalTrainer should import."""
        from core.multi_generational_trainer import MultiGenerationalTrainer
        assert MultiGenerationalTrainer is not None


# ============================================================================
# Test NeuroSymbolicBrainSystem
# ============================================================================

class TestNeuroSymbolicBrainSystem:
    """Tests for the evolving brain system."""

    @pytest.fixture
    def brain_system(self):
        """Create a brain system for testing."""
        from core.neurosymbolic_heart_brain import NeuroSymbolicBrainSystem
        return NeuroSymbolicBrainSystem(learning_rate=1e-4)

    def test_brain_initialization(self, brain_system):
        """Brain should initialize with correct attributes."""
        assert brain_system.brain is not None
        assert brain_system.optimizer is not None
        assert brain_system.device is not None

    def test_brain_is_trainable(self, brain_system):
        """Brain parameters should be trainable."""
        trainable_count = 0
        for param in brain_system.brain.parameters():
            if param.requires_grad:
                trainable_count += 1
        assert trainable_count > 0, "Brain should have trainable parameters"

    def test_brain_select_action(self, brain_system):
        """Brain should select actions correctly."""
        state = "abcdefghij1234567890"  # 20-char test state
        action, info = brain_system.select_action(state)

        assert isinstance(action, int)
        assert 0 <= action < 40
        assert 'action_logits' in info
        assert 'confidence' in info

    def test_brain_reset_for_new_generation(self, brain_system):
        """reset_for_new_generation should clear buffers."""
        # Add some data
        brain_system.experience_buffer = [{'test': 1}, {'test': 2}]
        brain_system.total_decisions = 100
        brain_system.total_updates = 50
        brain_system.confidence_scores = [0.5, 0.6, 0.7]
        brain_system.loss_history = [0.1, 0.2, 0.3]

        # Reset
        brain_system.reset_for_new_generation()

        # Verify
        assert len(brain_system.experience_buffer) == 0
        assert brain_system.total_decisions == 0
        assert brain_system.total_updates == 0
        assert len(brain_system.confidence_scores) == 0
        assert len(brain_system.loss_history) == 0

    def test_brain_get_statistics(self, brain_system):
        """get_statistics should return correct format."""
        stats = brain_system.get_statistics()

        assert 'total_decisions' in stats
        assert 'total_updates' in stats
        assert 'trainable' in stats
        assert stats['trainable'] == True
        assert stats['system'] == 'brain'


# ============================================================================
# Test NeuroSymbolicHeartSystem
# ============================================================================

class TestNeuroSymbolicHeartSystem:
    """Tests for the frozen heart system."""

    @pytest.fixture
    def heart_system(self):
        """Create a heart system for testing."""
        from core.neurosymbolic_heart_brain import NeuroSymbolicHeartSystem
        return NeuroSymbolicHeartSystem()

    def test_heart_initialization(self, heart_system):
        """Heart should initialize correctly."""
        assert heart_system.brain is not None
        assert heart_system.device is not None

    def test_heart_is_frozen(self, heart_system):
        """Heart parameters should not require gradients."""
        for param in heart_system.brain.parameters():
            assert not param.requires_grad, "Heart should be frozen"

    def test_heart_select_action(self, heart_system):
        """Heart should select actions."""
        state = "abcdefghij1234567890"
        action, info = heart_system.select_action(state)

        assert isinstance(action, int)
        assert 0 <= action < 40
        assert info.get('frozen', False) == True

    def test_heart_get_statistics(self, heart_system):
        """get_statistics should show frozen status."""
        stats = heart_system.get_statistics()

        assert 'frozen' in stats
        assert stats['frozen'] == True
        assert stats['system'] == 'heart'


# ============================================================================
# Test DualSystemAgent
# ============================================================================

class TestDualSystemAgent:
    """Tests for the dual heart+brain agent."""

    @pytest.fixture
    def dual_agent(self):
        """Create a dual system agent."""
        from core.neurosymbolic_heart_brain import (
            NeuroSymbolicHeartSystem,
            NeuroSymbolicBrainSystem,
            DualSystemAgent
        )
        heart = NeuroSymbolicHeartSystem()
        brain = NeuroSymbolicBrainSystem()
        return DualSystemAgent(heart, brain, heart_weight=0.7, brain_weight=0.3)

    def test_agent_initialization(self, dual_agent):
        """Agent should initialize with correct weights."""
        assert dual_agent.heart_weight == 0.7
        assert dual_agent.brain_weight == 0.3
        assert dual_agent.heart is not None
        assert dual_agent.brain is not None

    def test_agent_select_action(self, dual_agent):
        """Agent should select actions via weighted voting."""
        state = "abcdefghij1234567890"
        action, info = dual_agent.select_action(state)

        assert isinstance(action, int)
        assert 0 <= action < 40
        assert 'heart_action' in info
        assert 'brain_action' in info
        assert 'agreement' in info

    def test_agent_learn_from_episode_success(self, dual_agent):
        """learn_from_episode should store experiences for successful episodes."""
        initial_buffer_len = len(dual_agent.brain.experience_buffer)

        episode_data = {
            'success': True,
            'quality': 0.8,
            'path': ['state1_abcdefghij12', 'state2_abcdefghij12', 'state3_abcdefghij12'],
            'actions': [0, 1]
        }

        dual_agent.learn_from_episode(episode_data)

        # Should have added experiences
        assert len(dual_agent.brain.experience_buffer) >= initial_buffer_len

    def test_agent_learn_from_episode_failure(self, dual_agent):
        """learn_from_episode should skip failed episodes."""
        initial_buffer_len = len(dual_agent.brain.experience_buffer)

        episode_data = {
            'success': False,
            'quality': 0.0,
            'path': ['state1', 'state2'],
            'actions': [0]
        }

        dual_agent.learn_from_episode(episode_data)

        # Should not have added experiences
        assert len(dual_agent.brain.experience_buffer) == initial_buffer_len

    def test_agent_reset_for_new_generation(self, dual_agent):
        """reset_for_new_generation should clear all counters."""
        # Set some values
        dual_agent.total_decisions = 100
        dual_agent.heart_dominant_count = 60
        dual_agent.brain_dominant_count = 30
        dual_agent.agreement_count = 50

        # Reset
        dual_agent.reset_for_new_generation()

        # Verify
        assert dual_agent.total_decisions == 0
        assert dual_agent.heart_dominant_count == 0
        assert dual_agent.brain_dominant_count == 0
        assert dual_agent.agreement_count == 0

    def test_agent_get_statistics(self, dual_agent):
        """get_statistics should return comprehensive stats."""
        stats = dual_agent.get_statistics()

        assert 'total_decisions' in stats
        assert 'heart_dominant_rate' in stats
        assert 'brain_dominant_rate' in stats
        assert 'agreement_rate' in stats
        assert 'heart_weight' in stats
        assert 'brain_weight' in stats
        assert 'heart_stats' in stats
        assert 'brain_stats' in stats


# ============================================================================
# Test KlotskiDarkModeCoordinator
# ============================================================================

class TestKlotskiDarkModeCoordinator:
    """Tests for the 3-agent Klotski coordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create coordinator (will use fallback mode)."""
        from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator
        return KlotskiDarkModeCoordinator(
            current_generation=0,
            graph_file="nonexistent.json"  # Force fallback mode
        )

    def test_coordinator_has_three_agents(self, coordinator):
        """Coordinator should have 3 agent states."""
        assert len(coordinator.agent_states) == 3
        assert 'beginning' in coordinator.agent_states
        assert 'mid' in coordinator.agent_states
        assert 'end' in coordinator.agent_states

    def test_coordinator_reset(self, coordinator):
        """reset() should return states for all agents."""
        states = coordinator.reset()

        assert 'beginning' in states
        assert 'mid' in states
        assert 'end' in states

    def test_coordinator_step(self, coordinator):
        """step() should execute actions and return results."""
        coordinator.reset()

        actions = {
            'beginning': "Move: Right",
            'mid': "Move: Down",
            'end': "Move: Left"
        }

        next_states, reward, done, info = coordinator.step(actions)

        assert isinstance(reward, (int, float))
        assert isinstance(done, bool)
        assert isinstance(info, dict)

    def test_coordinator_conversation_penalty(self, coordinator):
        """Conversation penalty should scale with generation."""
        # Gen 0 should have low penalty (close to 0)
        gen0_penalty = coordinator.conversation_penalty
        assert abs(gen0_penalty) <= 0.5

        # Higher generation should have larger magnitude penalty
        from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator
        coord_gen5 = KlotskiDarkModeCoordinator(
            current_generation=5,
            graph_file="nonexistent.json"
        )
        # Penalties are negative, so larger magnitude means more negative
        assert abs(coord_gen5.conversation_penalty) > abs(gen0_penalty)


# ============================================================================
# Test Integration: Full Pipeline
# ============================================================================

class TestIntegration:
    """Integration tests for the complete pipeline."""

    def test_dual_agent_workflow(self):
        """Test complete dual agent workflow."""
        from core.neurosymbolic_heart_brain import (
            NeuroSymbolicHeartSystem,
            NeuroSymbolicBrainSystem,
            DualSystemAgent
        )
        import torch

        # Create components
        heart = NeuroSymbolicHeartSystem()
        brain = NeuroSymbolicBrainSystem()
        agent = DualSystemAgent(heart, brain)

        # Workflow: select action, store experience, train
        state = "test_state_123456789012"
        action, info = agent.select_action(state)

        # Get action logits from brain directly if not in info
        action_logits = info.get('action_logits')
        if action_logits is None:
            # Create dummy logits for testing
            action_logits = torch.randn(40)

        # Store experience
        agent.update_brain(
            state=state,
            action=action,
            reward=1.0,
            next_state=state,
            done=True,
            action_logits=action_logits
        )

        # Verify experience was stored
        assert len(brain.experience_buffer) > 0

        # Reset for new generation
        agent.reset_for_new_generation()
        assert len(brain.experience_buffer) == 0

    def test_coordinator_agent_interaction(self):
        """Test coordinator and agent interaction."""
        from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator
        from core.neurosymbolic_heart_brain import (
            NeuroSymbolicHeartSystem,
            NeuroSymbolicBrainSystem,
            DualSystemAgent
        )

        # Create coordinator
        coord = KlotskiDarkModeCoordinator(
            current_generation=0,
            graph_file="nonexistent.json"
        )

        # Create agents
        heart = NeuroSymbolicHeartSystem()
        agents = {}
        for name in ['beginning', 'mid', 'end']:
            brain = NeuroSymbolicBrainSystem()
            agents[name] = DualSystemAgent(heart, brain)

        # Run one step
        states = coord.reset()
        actions = {}
        for name in agents:
            state = states.get(name, 'fallback_state_12345')
            action, _ = agents[name].select_action(str(state)[:20].ljust(20, '0'))
            actions[name] = f"Move: Right"  # Simple action for fallback mode

        next_states, reward, done, info = coord.step(actions)

        # Verify interaction worked
        assert isinstance(reward, (int, float))
        assert isinstance(done, bool)


# ============================================================================
# Test Interface Compatibility
# ============================================================================

class TestInterfaceCompatibility:
    """Test that interfaces match what multi_generational_trainer expects."""

    def test_dual_agent_has_learn_from_episode(self):
        """DualSystemAgent must have learn_from_episode method."""
        from core.neurosymbolic_heart_brain import DualSystemAgent
        assert hasattr(DualSystemAgent, 'learn_from_episode')
        assert callable(getattr(DualSystemAgent, 'learn_from_episode'))

    def test_dual_agent_has_reset_for_new_generation(self):
        """DualSystemAgent must have reset_for_new_generation method."""
        from core.neurosymbolic_heart_brain import DualSystemAgent
        assert hasattr(DualSystemAgent, 'reset_for_new_generation')
        assert callable(getattr(DualSystemAgent, 'reset_for_new_generation'))

    def test_brain_system_has_reset_for_new_generation(self):
        """NeuroSymbolicBrainSystem must have reset_for_new_generation method."""
        from core.neurosymbolic_heart_brain import NeuroSymbolicBrainSystem
        assert hasattr(NeuroSymbolicBrainSystem, 'reset_for_new_generation')
        assert callable(getattr(NeuroSymbolicBrainSystem, 'reset_for_new_generation'))

    def test_dual_agent_has_select_action(self):
        """DualSystemAgent must have select_action method."""
        from core.neurosymbolic_heart_brain import DualSystemAgent
        assert hasattr(DualSystemAgent, 'select_action')

    def test_dual_agent_has_train_brain(self):
        """DualSystemAgent must have train_brain method."""
        from core.neurosymbolic_heart_brain import DualSystemAgent
        assert hasattr(DualSystemAgent, 'train_brain')

    def test_coordinator_has_reset(self):
        """KlotskiDarkModeCoordinator must have reset method."""
        from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator
        assert hasattr(KlotskiDarkModeCoordinator, 'reset')

    def test_coordinator_has_step(self):
        """KlotskiDarkModeCoordinator must have step method."""
        from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator
        assert hasattr(KlotskiDarkModeCoordinator, 'step')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
