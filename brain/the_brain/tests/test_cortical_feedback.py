"""
Tests for Cortical Feedback Loops

Tests the cortical feedback system including:
- AttentionController: Goal/oscillator/PE-driven attention computation
- FeedbackGenerator: Prior and TRN modulation generation
- CorticalProcessor: Complete feedback coordination
- Integration with ThalamoHippocampalSystem
"""

import pytest
import numpy as np
from typing import Dict

# Import cortical feedback components
from core.cortical_feedback import (
    CorticalState,
    CorticalFeedback,
    AttentionController,
    FeedbackGenerator,
    ExpectationNetwork,
    CorticalProcessor,
    softmax,
    normalize
)

# Import for integration tests
from core.thalamo_hippocampal_system import ThalamoHippocampalSystem
from core.action_potential_oscillator import ActionPotentialOscillator, TripleOscillatorState
from core.neuromodulation import NeuromodulationSystem


class TestUtilityFunctions:
    """Test utility functions."""

    def test_softmax_basic(self):
        """Test softmax produces valid probability distribution."""
        x = np.array([1.0, 2.0, 3.0])
        result = softmax(x)

        assert np.allclose(np.sum(result), 1.0)
        assert np.all(result >= 0)
        assert np.all(result <= 1)

    def test_softmax_temperature(self):
        """Test temperature affects softmax sharpness."""
        x = np.array([1.0, 2.0, 3.0])

        # Low temperature -> sharper
        low_temp = softmax(x, temperature=0.1)
        # High temperature -> flatter
        high_temp = softmax(x, temperature=2.0)

        # Low temp should have more peaked distribution
        assert np.max(low_temp) > np.max(high_temp)

    def test_softmax_numerical_stability(self):
        """Test softmax handles large values."""
        x = np.array([1000.0, 1001.0, 1002.0])
        result = softmax(x)

        assert np.allclose(np.sum(result), 1.0)
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))

    def test_normalize_basic(self):
        """Test normalize produces sum-to-one distribution."""
        x = np.array([1.0, 2.0, 3.0])
        result = normalize(x)

        assert np.allclose(np.sum(result), 1.0)


class TestCorticalState:
    """Test CorticalState dataclass."""

    def test_creation(self):
        """Test CorticalState creation."""
        attention = np.array([0.2, 0.3, 0.5])
        state = CorticalState(attention_weights=attention)

        assert np.array_equal(state.attention_weights, attention)
        assert state.feedback_gain == 1.0

    def test_default_values(self):
        """Test CorticalState defaults."""
        state = CorticalState(attention_weights=np.zeros(3))

        assert len(state.expectation) == 0
        assert state.feedback_gain == 1.0


class TestCorticalFeedback:
    """Test CorticalFeedback dataclass."""

    def test_creation(self):
        """Test CorticalFeedback creation."""
        feedback = CorticalFeedback(
            prior_modulation=np.array([0.1, -0.1, 0.0]),
            trn_modulation=np.zeros((3, 3)),
            gain_modulation=1.2,
            attention_weights=np.array([0.3, 0.3, 0.4])
        )

        assert len(feedback.prior_modulation) == 3
        assert feedback.gain_modulation == 1.2

    def test_to_dict(self):
        """Test CorticalFeedback serialization."""
        feedback = CorticalFeedback(
            prior_modulation=np.array([0.1, -0.1]),
            trn_modulation=np.zeros((2, 2)),
            gain_modulation=1.0,
            attention_weights=np.array([0.5, 0.5])
        )

        d = feedback.to_dict()
        assert 'prior_modulation' in d
        assert 'trn_modulation' in d
        assert 'gain_modulation' in d
        assert 'attention_weights' in d


class TestAttentionController:
    """Test AttentionController class."""

    def test_initialization(self):
        """Test AttentionController initialization."""
        controller = AttentionController(
            n_modalities=6,
            goal_dim=32
        )

        assert controller.n_modalities == 6
        assert controller.goal_dim == 32
        assert controller.W_goal.shape == (6, 32)
        assert controller.W_osc.shape == (6, 6)

    def test_compute_attention_no_inputs(self):
        """Test attention computation with no inputs."""
        controller = AttentionController(n_modalities=4, goal_dim=16)

        attention = controller.compute_attention(
            goal=None,
            oscillator_state=None,
            prediction_errors=None
        )

        # Should return uniform attention
        assert len(attention) == 4
        assert np.allclose(np.sum(attention), 1.0)
        assert np.allclose(attention, np.ones(4) / 4)

    def test_compute_attention_with_goal(self):
        """Test goal-driven attention."""
        controller = AttentionController(n_modalities=4, goal_dim=16, alpha_goal=1.0, beta_osc=0.0, gamma_pe=0.0)

        # Use a goal with strong bias to ensure non-uniform attention
        goal = np.zeros(16)
        goal[0] = 5.0  # Strong signal in first dimension
        attention = controller.compute_attention(goal=goal)

        assert len(attention) == 4
        assert np.allclose(np.sum(attention), 1.0)
        # The attention should be a valid distribution
        assert np.all(attention >= 0)
        assert np.all(attention <= 1)

    def test_compute_attention_with_pe(self):
        """Test PE-driven attention."""
        controller = AttentionController(n_modalities=4, goal_dim=16, alpha_goal=0.0, beta_osc=0.0, gamma_pe=1.0)

        # High PE for modality 0
        prediction_errors = np.array([1.0, 0.1, 0.1, 0.1])
        attention = controller.compute_attention(goal=None, prediction_errors=prediction_errors)

        # Modality 0 should get most attention
        assert attention[0] > attention[1]
        assert attention[0] > attention[2]
        assert attention[0] > attention[3]

    def test_compute_attention_with_oscillator(self):
        """Test oscillator-modulated attention."""
        controller = AttentionController(n_modalities=4, goal_dim=16, alpha_goal=0.0, beta_osc=1.0, gamma_pe=0.0)

        # Create mock oscillator state
        osc = ActionPotentialOscillator()
        for _ in range(10):
            osc.step()

        attention = controller.compute_attention(goal=None, oscillator_state=osc.state)

        assert len(attention) == 4
        assert np.allclose(np.sum(attention), 1.0)

    def test_update_weights(self):
        """Test attention weight learning."""
        controller = AttentionController(n_modalities=4, goal_dim=16, lr_attention=0.1)

        goal = np.random.randn(16)
        attention = np.array([0.4, 0.3, 0.2, 0.1])
        W_goal_before = controller.W_goal.copy()

        controller.update_weights(
            attention=attention,
            reward=1.0,
            goal=goal
        )

        # Weights should change
        assert not np.allclose(controller.W_goal, W_goal_before)

    def test_statistics(self):
        """Test statistics retrieval."""
        controller = AttentionController(n_modalities=4, goal_dim=16)
        controller.compute_attention(goal=None)

        stats = controller.get_statistics()
        assert 'steps' in stats
        assert 'n_modalities' in stats
        assert 'blend_weights' in stats


class TestFeedbackGenerator:
    """Test FeedbackGenerator class."""

    def test_initialization(self):
        """Test FeedbackGenerator initialization."""
        generator = FeedbackGenerator(n_modalities=6, state_dim=128)

        assert generator.n_modalities == 6
        assert len(generator.expected_salience) == 6

    def test_generate_feedback_basic(self):
        """Test basic feedback generation."""
        generator = FeedbackGenerator(n_modalities=4)

        attention = np.array([0.4, 0.3, 0.2, 0.1])
        feedback = generator.generate_feedback(attention)

        assert isinstance(feedback, CorticalFeedback)
        assert len(feedback.prior_modulation) == 4
        assert feedback.trn_modulation.shape == (4, 4)
        assert feedback.gain_modulation > 0

    def test_prior_modulation_direction(self):
        """Test that prior modulation boosts attended modalities."""
        generator = FeedbackGenerator(n_modalities=4, prior_strength=0.5)
        generator.current_priors = np.array([0.2, 0.5, 0.5, 0.5])  # Low prior for attended modality
        generator.expected_salience = np.array([0.8, 0.5, 0.5, 0.5])  # High salience for attended modality

        # Attend to modality 0
        attention = np.array([1.0, 0.0, 0.0, 0.0])
        feedback = generator.generate_feedback(attention)

        # Modality 0 should get positive prior delta (moving toward salience)
        # prior_delta[0] = 0.5 * (1.0 * 0.8 - 0.2) = 0.5 * 0.6 = 0.3
        assert feedback.prior_modulation[0] > 0

    def test_trn_modulation_suppression(self):
        """Test TRN modulation suppresses unattended modalities."""
        generator = FeedbackGenerator(n_modalities=4, trn_strength=0.1)

        # Attend to modality 0, ignore modality 3
        attention = np.array([1.0, 0.0, 0.0, 0.0])
        feedback = generator.generate_feedback(attention)

        # TRN delta from 0 to 3 should be negative (increase inhibition)
        assert feedback.trn_modulation[0, 3] < 0

    def test_gain_modulation_with_neuromodulation(self):
        """Test gain modulation with neuromodulator levels."""
        generator = FeedbackGenerator(n_modalities=4, gain_baseline=1.0, gain_scale=0.5)

        # Create neuromodulator levels directly
        from core.neuromodulation import NeuromodulatorLevels
        neuromod_levels = NeuromodulatorLevels(
            dopamine=0.5,
            serotonin=0.5,
            norepinephrine=0.9  # High arousal
        )

        attention = np.ones(4) / 4
        feedback = generator.generate_feedback(attention, neuromod_levels=neuromod_levels)

        # High norepinephrine should increase gain
        assert feedback.gain_modulation > 1.0

    def test_salience_learning(self):
        """Test expected salience updates from PE."""
        generator = FeedbackGenerator(n_modalities=4, lr_salience=0.1)
        salience_before = generator.expected_salience.copy()

        attention = np.ones(4) / 4
        high_pe = np.array([1.0, 0.1, 0.1, 0.1])
        generator.generate_feedback(attention, prediction_errors=high_pe)

        # Modality 0 salience should increase
        assert generator.expected_salience[0] > salience_before[0]


class TestExpectationNetwork:
    """Test ExpectationNetwork class."""

    def test_initialization(self):
        """Test ExpectationNetwork initialization."""
        dims = {'vision': 64, 'audio': 32}
        network = ExpectationNetwork(modality_dims=dims, context_dim=16)

        assert 'vision' in network.W
        assert 'audio' in network.W
        assert network.W['vision'].shape == (64, 16)

    def test_predict_no_context(self):
        """Test prediction with no context."""
        dims = {'vision': 8, 'audio': 4}
        network = ExpectationNetwork(modality_dims=dims, context_dim=4)

        predictions = network.predict(context=None)

        assert 'vision' in predictions
        assert 'audio' in predictions
        assert len(predictions['vision']) == 8

    def test_predict_with_context(self):
        """Test prediction with context."""
        dims = {'vision': 8, 'audio': 4}
        network = ExpectationNetwork(modality_dims=dims, context_dim=4)

        context = np.random.randn(4)
        predictions = network.predict(context)

        assert len(predictions['vision']) == 8
        # Predictions should be in [-1, 1] due to tanh
        assert np.all(np.abs(predictions['vision']) <= 1.0)

    def test_update_learning(self):
        """Test expectation learning."""
        dims = {'vision': 4}
        network = ExpectationNetwork(modality_dims=dims, context_dim=4, lr=0.1)

        context = np.random.randn(4)
        actual = {'vision': np.array([0.5, 0.5, -0.5, -0.5])}
        attention = np.array([1.0])  # Fully attend

        W_before = network.W['vision'].copy()
        network.update(context, actual, attention, ['vision'])

        # Weights should change
        assert not np.allclose(network.W['vision'], W_before)


class TestCorticalProcessor:
    """Test CorticalProcessor class."""

    def test_initialization(self):
        """Test CorticalProcessor initialization."""
        processor = CorticalProcessor(
            n_modalities=6,
            goal_dim=32,
            state_dim=128
        )

        assert processor.n_modalities == 6
        assert processor.goal_dim == 32
        assert processor.attention is not None
        assert processor.feedback is not None

    def test_step_basic(self):
        """Test basic step through processor."""
        processor = CorticalProcessor(n_modalities=4, goal_dim=16)

        thalamic_output = {
            'PE': {'m0': 0.5, 'm1': 0.3, 'm2': 0.1, 'm3': 0.2},
            'priors': {'m0': 0.4, 'm1': 0.3, 'm2': 0.2, 'm3': 0.1},
            'gates': np.array([0.3, 0.3, 0.2, 0.2])
        }
        processor.modality_order = ['m0', 'm1', 'm2', 'm3']

        feedback = processor.step(thalamic_output)

        assert isinstance(feedback, CorticalFeedback)
        assert len(feedback.prior_modulation) == 4

    def test_step_with_goal(self):
        """Test step with goal input."""
        processor = CorticalProcessor(n_modalities=4, goal_dim=16)

        thalamic_output = {
            'PE': {'m0': 0.5, 'm1': 0.3, 'm2': 0.1, 'm3': 0.2},
            'priors': {'m0': 0.4, 'm1': 0.3, 'm2': 0.2, 'm3': 0.1}
        }
        processor.modality_order = ['m0', 'm1', 'm2', 'm3']

        goal = np.random.randn(16)
        feedback = processor.step(thalamic_output, goal=goal)

        assert isinstance(feedback, CorticalFeedback)

    def test_step_with_oscillator(self):
        """Test step with oscillator state."""
        processor = CorticalProcessor(n_modalities=4, goal_dim=16)

        thalamic_output = {
            'PE': {},
            'priors': {}
        }
        processor.modality_order = ['m0', 'm1', 'm2', 'm3']

        osc = ActionPotentialOscillator()
        for _ in range(10):
            osc.step()

        feedback = processor.step(thalamic_output, oscillator_state=osc.state)

        assert isinstance(feedback, CorticalFeedback)

    def test_update_from_reward(self):
        """Test reward-based learning."""
        processor = CorticalProcessor(n_modalities=4, goal_dim=16, enable_learning=True)

        # Do a step first
        thalamic_output = {'PE': {}, 'priors': {}}
        processor.modality_order = ['m0', 'm1', 'm2', 'm3']
        goal = np.random.randn(16)
        processor.step(thalamic_output, goal=goal)

        W_before = processor.attention.W_goal.copy()
        processor.update_from_reward(reward=1.0, goal=goal)

        # Weights should change with positive reward
        assert not np.allclose(processor.attention.W_goal, W_before)

    def test_get_statistics(self):
        """Test statistics retrieval."""
        processor = CorticalProcessor(n_modalities=4, goal_dim=16)

        thalamic_output = {'PE': {}, 'priors': {}}
        processor.modality_order = ['m0', 'm1', 'm2', 'm3']
        processor.step(thalamic_output)

        stats = processor.get_statistics()
        assert 'steps' in stats
        assert 'n_modalities' in stats
        assert 'attention_controller' in stats
        assert 'feedback_generator' in stats

    def test_reset(self):
        """Test processor reset."""
        processor = CorticalProcessor(n_modalities=4, goal_dim=16)

        thalamic_output = {'PE': {}, 'priors': {}}
        processor.modality_order = ['m0', 'm1', 'm2', 'm3']
        processor.step(thalamic_output)

        assert processor.last_feedback is not None
        processor.reset()
        assert processor.last_feedback is None


class TestIntegrationWithThalamoHippocampalSystem:
    """Test cortical feedback integration with ThalamoHippocampalSystem."""

    def test_system_with_cortex_enabled(self):
        """Test ThalamoHippocampalSystem with cortex enabled."""
        system = ThalamoHippocampalSystem(
            enable_hippocampus=True,
            enable_basal_ganglia=True,
            enable_cortex=True,
            goal_dim=16
        )

        assert system.cortex is not None
        assert system.enable_cortex is True

    def test_system_step_with_cortex(self):
        """Test system step includes cortical feedback."""
        system = ThalamoHippocampalSystem(
            enable_hippocampus=False,  # Simpler test
            enable_basal_ganglia=False,
            enable_cortex=True,
            goal_dim=16
        )

        # Create input
        x = {m: np.random.randn(system.thalamus.d[m]) for m in system.thalamus.modalities}
        goal = np.random.randn(16)

        result = system.step(x, goal=goal)

        assert 'cortical_feedback' in result
        assert 'cortical_attention' in result

    def test_system_step_with_oscillator_and_cortex(self):
        """Test system step with oscillator and cortex."""
        system = ThalamoHippocampalSystem(
            enable_hippocampus=False,
            enable_basal_ganglia=True,
            enable_cortex=True,
            goal_dim=16
        )

        osc = ActionPotentialOscillator()
        neuromod = NeuromodulationSystem()
        for _ in range(10):
            osc.step()
            neuromod.update(outcome='success', confidence=0.5, urgency=0.5)

        x = {m: np.random.randn(system.thalamus.d[m]) for m in system.thalamus.modalities}
        goal = np.random.randn(16)

        result = system.step(
            x,
            goal=goal,
            oscillator_state=osc.state,
            neuromod_levels=neuromod.levels
        )

        assert 'cortical_feedback' in result
        assert 'bg_output' in result

    def test_cortex_affects_gates(self):
        """Test that cortical feedback affects final gates."""
        system = ThalamoHippocampalSystem(
            enable_hippocampus=False,
            enable_basal_ganglia=False,
            enable_cortex=True,
            goal_dim=16,
            cortex_prior_strength=0.5  # Strong effect
        )

        x = {m: np.random.randn(system.thalamus.d[m]) for m in system.thalamus.modalities}

        # Step without goal
        result1 = system.step(x, goal=None)
        gates1 = result1['gates']

        # Reset and step with strong goal bias
        system.reset()
        goal = np.zeros(16)
        goal[0] = 10.0  # Strong bias toward first feature

        result2 = system.step(x, goal=goal)
        gates2 = result2['gates']

        # Gates should be different due to cortical influence
        assert not np.allclose(gates1, gates2)

    def test_cortex_state_description(self):
        """Test cortex state description."""
        system = ThalamoHippocampalSystem(
            enable_hippocampus=False,
            enable_basal_ganglia=False,
            enable_cortex=True
        )

        # Before any step
        desc = system.get_cortex_state_description()
        assert "not active" in desc

        # After step
        x = {m: np.random.randn(system.thalamus.d[m]) for m in system.thalamus.modalities}
        system.step(x, goal=np.random.randn(32))

        desc = system.get_cortex_state_description()
        assert "Attention:" in desc

    def test_system_reset_clears_cortex(self):
        """Test system reset clears cortical state."""
        system = ThalamoHippocampalSystem(
            enable_cortex=True,
            enable_hippocampus=False,
            enable_basal_ganglia=False
        )

        x = {m: np.random.randn(system.thalamus.d[m]) for m in system.thalamus.modalities}
        system.step(x, goal=np.random.randn(32))

        assert system._last_cortical_feedback is not None

        system.reset()
        assert system._last_cortical_feedback is None

    def test_cortex_reward_learning(self):
        """Test cortical learning from reward."""
        system = ThalamoHippocampalSystem(
            enable_cortex=True,
            enable_hippocampus=False,
            enable_basal_ganglia=False
        )

        x = {m: np.random.randn(system.thalamus.d[m]) for m in system.thalamus.modalities}
        goal = np.random.randn(32)
        system.step(x, goal=goal)

        W_before = system.cortex.attention.W_goal.copy()
        system.update_cortex_from_reward(reward=1.0, goal=goal)

        # Weights should change
        assert not np.allclose(system.cortex.attention.W_goal, W_before)


class TestCortexDisabled:
    """Test behavior when cortex is disabled."""

    def test_system_without_cortex(self):
        """Test system works without cortex."""
        system = ThalamoHippocampalSystem(
            enable_hippocampus=True,
            enable_basal_ganglia=True,
            enable_cortex=False
        )

        assert system.cortex is None

        x = {m: np.random.randn(system.thalamus.d[m]) for m in system.thalamus.modalities}
        result = system.step(x)

        assert 'cortical_feedback' not in result

    def test_toggle_cortex(self):
        """Test enabling/disabling cortex at runtime."""
        system = ThalamoHippocampalSystem(enable_cortex=True)

        assert system.enable_cortex is True

        system.set_cortex_enabled(False)
        assert system.enable_cortex is False

        system.set_cortex_enabled(True)
        assert system.enable_cortex is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
