"""
Unit tests for the Emotional System (core/emotional_system.py)

Tests cover:
- EmotionalState dataclass
- Keyword appraisal (positive, negative, neutral, mixed)
- Memory-based appraisal
- Routing weight modulation (fear response, reward response, calm)
- Attention strength modulation
- Neuromodulation bias mapping
- Emotional learning from outcomes
- Decay mechanics
- History management
- Capacity management
- Edge cases (empty input, extreme values)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
from core.emotional_system import (
    EmotionalSystem,
    EmotionalSystemConfig,
    EmotionalState,
    EmotionalMemory,
)


class TestEmotionalState:
    """Tests for the EmotionalState dataclass."""

    def test_default_state(self):
        state = EmotionalState()
        assert state.valence == 0.0
        assert state.arousal == 0.0
        assert state.dominant_emotion == "neutral"

    def test_to_dict(self):
        state = EmotionalState(valence=0.12345, arousal=0.67891, dominant_emotion="happy")
        d = state.to_dict()
        assert d['valence'] == 0.123
        assert d['arousal'] == 0.679
        assert d['dominant_emotion'] == "happy"


class TestEmotionalSystemConfig:
    """Tests for configuration."""

    def test_defaults(self):
        config = EmotionalSystemConfig()
        assert config.valence_decay_rate == 0.05
        assert config.arousal_decay_rate == 0.1
        assert config.memory_capacity == 200
        assert config.learning_rate == 0.1

    def test_custom_config(self):
        config = EmotionalSystemConfig(
            valence_decay_rate=0.01,
            fear_threshold=0.9,
            memory_capacity=50
        )
        assert config.valence_decay_rate == 0.01
        assert config.fear_threshold == 0.9
        assert config.memory_capacity == 50


class TestKeywordAppraisal:
    """Tests for keyword-based emotional appraisal."""

    def test_negative_high_arousal_keywords(self):
        es = EmotionalSystem()
        state = es.appraise_task("There is a critical error in the system crash")
        assert state.valence < 0, "Negative keywords should produce negative valence"
        assert state.arousal > 0.3, "Crisis keywords should produce high arousal"

    def test_positive_keywords(self):
        es = EmotionalSystem()
        state = es.appraise_task("We achieved great success and deployed the new build")
        assert state.valence > 0, "Positive keywords should produce positive valence"
        assert state.arousal > 0.2, "Success/deploy should produce moderate arousal"

    def test_neutral_keywords(self):
        es = EmotionalSystem()
        state = es.appraise_task("The weather is nice today")
        # No emotional keywords → near-neutral
        assert -0.2 <= state.valence <= 0.2
        assert state.arousal < 0.5

    def test_mixed_keywords(self):
        es = EmotionalSystem()
        state = es.appraise_task("The critical bug was successfully solved")
        # Both negative (critical, bug) and positive (successfully, solved)
        # Should partially cancel out
        assert state.dominant_emotion != ""

    def test_empty_task(self):
        es = EmotionalSystem()
        state = es.appraise_task("")
        assert state.dominant_emotion == "neutral"
        assert state.arousal < 0.5

    def test_single_word_task(self):
        es = EmotionalSystem()
        state = es.appraise_task("crash")
        assert state.valence < 0
        assert state.arousal > 0.3  # Emotional inertia blends with initial (0,0) state


class TestEmotionClassification:
    """Tests for Russell circumplex emotion classification."""

    def test_excited(self):
        es = EmotionalSystem()
        result = es._classify_emotion(0.8, 0.9)
        assert result == "excited"

    def test_fearful(self):
        es = EmotionalSystem()
        result = es._classify_emotion(-0.8, 0.9)
        assert result == "fearful"

    def test_content(self):
        es = EmotionalSystem()
        result = es._classify_emotion(0.7, 0.3)
        assert result == "content"

    def test_sad(self):
        es = EmotionalSystem()
        result = es._classify_emotion(-0.7, 0.3)
        assert result == "sad"

    def test_neutral(self):
        es = EmotionalSystem()
        result = es._classify_emotion(0.0, 0.2)
        assert result == "neutral"

    def test_alert(self):
        es = EmotionalSystem()
        result = es._classify_emotion(0.0, 0.8)
        assert result == "alert"


class TestRoutingWeightModulation:
    """Tests for emotional modulation of routing weights."""

    def test_fear_boosts_threat_channel(self):
        es = EmotionalSystem()
        # Set fear state: negative valence, high arousal
        es._state.valence = -0.8
        es._state.arousal = 0.9

        weights = np.array([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
        modulated = es.modulate_routing_weights(weights)

        # Should still sum to ~1.0 (gate invariant)
        assert abs(np.sum(modulated) - 1.0) < 1e-6, "Gate invariant violated"
        # Threat channel (index 5) should be boosted relative to original
        assert modulated[5] > weights[5], "Threat channel should be boosted under fear"

    def test_reward_boosts_success_channel(self):
        es = EmotionalSystem()
        es._state.valence = 0.8
        es._state.arousal = 0.9

        weights = np.array([0.1] * 10)
        modulated = es.modulate_routing_weights(weights)

        assert abs(np.sum(modulated) - 1.0) < 1e-6
        assert modulated[9] > weights[9], "Success channel should be boosted under reward"

    def test_calm_makes_distribution_more_uniform(self):
        es = EmotionalSystem()
        es._state.valence = 0.0
        es._state.arousal = 0.1  # Very calm

        # Sharply peaked distribution
        weights = np.array([0.5, 0.3, 0.1, 0.05, 0.05])
        modulated = es.modulate_routing_weights(weights)

        # Should be more uniform (lower max)
        assert abs(np.sum(modulated) - 1.0) < 1e-6
        assert np.max(modulated) < np.max(weights), "Calm should flatten distribution"

    def test_gate_invariant_preserved(self):
        """Gate sum must always be 1.0 after modulation."""
        es = EmotionalSystem()
        for v, a in [(-1.0, 1.0), (1.0, 1.0), (0.0, 0.0), (0.5, 0.5)]:
            es._state.valence = v
            es._state.arousal = a
            weights = np.random.dirichlet(np.ones(10))
            modulated = es.modulate_routing_weights(weights)
            assert abs(np.sum(modulated) - 1.0) < 1e-6, f"Gate invariant violated at v={v}, a={a}"

    def test_modulation_with_6_modalities(self):
        es = EmotionalSystem()
        es._state.valence = -0.5
        es._state.arousal = 0.8

        weights = np.array([0.2, 0.2, 0.15, 0.15, 0.15, 0.15])
        modulated = es.modulate_routing_weights(weights)
        assert abs(np.sum(modulated) - 1.0) < 1e-6

    def test_modulation_with_small_weights(self):
        es = EmotionalSystem()
        es._state.valence = 0.5
        es._state.arousal = 0.5

        weights = np.array([0.001, 0.001, 0.001, 0.997])
        modulated = es.modulate_routing_weights(weights)
        assert abs(np.sum(modulated) - 1.0) < 1e-6
        assert all(w >= 0 for w in modulated), "All weights must be non-negative"


class TestAttentionModulation:
    """Tests for attention strength modulation."""

    def test_high_arousal_increases_attention(self):
        es = EmotionalSystem()
        es._state.arousal = 0.9
        result = es.modulate_attention_strength(0.5)
        assert result > 0.5

    def test_low_arousal_keeps_attention_close(self):
        es = EmotionalSystem()
        es._state.arousal = 0.0
        result = es.modulate_attention_strength(0.5)
        assert result == 0.5

    def test_attention_scales_linearly(self):
        es = EmotionalSystem()
        es._state.arousal = 1.0
        result = es.modulate_attention_strength(1.0)
        assert result == pytest.approx(1.3, abs=0.01)


class TestNeuromodulationBias:
    """Tests for emotion → neurotransmitter mapping."""

    def test_positive_valence_boosts_dopamine(self):
        es = EmotionalSystem()
        es._state.valence = 0.8
        es._state.arousal = 0.5
        bias = es.get_neuromodulation_bias()
        assert bias['dopamine_delta'] > 0

    def test_negative_valence_decreases_serotonin(self):
        es = EmotionalSystem()
        es._state.valence = -0.8
        es._state.arousal = 0.5
        bias = es.get_neuromodulation_bias()
        assert bias['serotonin_delta'] < 0

    def test_high_arousal_boosts_norepinephrine(self):
        es = EmotionalSystem()
        es._state.valence = 0.0
        es._state.arousal = 0.9
        bias = es.get_neuromodulation_bias()
        assert bias['norepinephrine_delta'] > 0

    def test_bias_clamped(self):
        es = EmotionalSystem()
        es._state.valence = 1.0
        es._state.arousal = 1.0
        bias = es.get_neuromodulation_bias()
        assert -0.1 <= bias['dopamine_delta'] <= 0.1
        assert -0.05 <= bias['norepinephrine_delta'] <= 0.1
        assert -0.05 <= bias['serotonin_delta'] <= 0.05


class TestEmotionalLearning:
    """Tests for learning from outcomes."""

    def test_learn_success(self):
        es = EmotionalSystem()
        es.learn_from_outcome("deploy application", success=True, confidence=0.8)
        assert len(es._emotional_memories) == 1
        assert es._emotional_memories[0].valence > 0
        assert es._emotional_memories[0].task_pattern == "deploy application"

    def test_learn_failure(self):
        es = EmotionalSystem()
        es.learn_from_outcome("delete database", success=False, confidence=0.3)
        assert len(es._emotional_memories) == 1
        assert es._emotional_memories[0].valence < 0

    def test_learn_updates_existing_memory(self):
        es = EmotionalSystem()
        es.learn_from_outcome("deploy application", success=True, confidence=0.8)
        initial_valence = es._emotional_memories[0].valence

        # Same task, different outcome → update existing
        es.learn_from_outcome("deploy application", success=False, confidence=0.5)
        assert len(es._emotional_memories) == 1  # Still just one memory
        assert es._emotional_memories[0].valence < initial_valence  # Shifted negative

    def test_memory_capacity_management(self):
        config = EmotionalSystemConfig(memory_capacity=5)
        es = EmotionalSystem(config=config)

        # Add more than capacity
        for i in range(10):
            es.learn_from_outcome(f"unique_task_{i}", success=True, confidence=0.5)

        assert len(es._emotional_memories) <= 5

    def test_learned_memories_bias_future_appraisal(self):
        es = EmotionalSystem()
        # Learn that "deploy" is negative (many failures)
        for _ in range(5):
            es.learn_from_outcome("deploy the server", success=False, confidence=0.3)

        # Now appraise similar task
        state = es.appraise_task("deploy the application server")
        # Should have negative bias from memory
        assert state.valence < 0.3  # Memory should drag it negative


class TestDecay:
    """Tests for homeostatic decay."""

    def test_valence_decays_toward_zero(self):
        es = EmotionalSystem()
        es._state.valence = 0.8
        es._state.arousal = 0.9

        for _ in range(50):
            es.decay()

        assert abs(es._state.valence) < 0.1, "Valence should decay toward 0"
        assert es._state.arousal < 0.1, "Arousal should decay toward 0"

    def test_decay_rate_configurable(self):
        fast_config = EmotionalSystemConfig(valence_decay_rate=0.5, arousal_decay_rate=0.5)
        es = EmotionalSystem(config=fast_config)
        es._state.valence = 1.0
        es._state.arousal = 1.0

        es.decay()
        assert es._state.valence == pytest.approx(0.5)
        assert es._state.arousal == pytest.approx(0.5)

    def test_memory_strength_decays(self):
        es = EmotionalSystem()
        es.learn_from_outcome("test task", success=True, confidence=0.8)
        initial_strength = es._emotional_memories[0].strength

        for _ in range(100):
            es.decay()

        assert es._emotional_memories[0].strength < initial_strength


class TestHistory:
    """Tests for emotional state history."""

    def test_history_accumulates(self):
        es = EmotionalSystem()
        for i in range(5):
            es.appraise_task(f"task {i}")

        assert len(es._history) == 5

    def test_history_capped_at_100(self):
        es = EmotionalSystem()
        for i in range(120):
            es.appraise_task(f"task {i}")

        assert len(es._history) == 100


class TestGetStateDict:
    """Tests for dashboard state export."""

    def test_state_dict_keys(self):
        es = EmotionalSystem()
        es.appraise_task("test task")
        d = es.get_state_dict()

        assert 'current_state' in d
        assert 'emotional_memories_count' in d
        assert 'history_length' in d
        assert 'recent_emotions' in d

    def test_state_dict_after_learning(self):
        es = EmotionalSystem()
        es.learn_from_outcome("task A", success=True, confidence=0.8)
        es.learn_from_outcome("task B", success=False, confidence=0.3)
        d = es.get_state_dict()

        assert d['emotional_memories_count'] == 2


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_zero_weights(self):
        es = EmotionalSystem()
        es._state.valence = 0.5
        es._state.arousal = 0.5
        weights = np.zeros(10)
        # Should handle gracefully (no division by zero)
        modulated = es.modulate_routing_weights(weights)
        # When all zero, modulated should be all zeros (sum is 0)
        assert not np.any(np.isnan(modulated))

    def test_very_long_task_description(self):
        es = EmotionalSystem()
        long_task = "error " * 1000  # 1000 repetitions of "error"
        state = es.appraise_task(long_task)
        assert state.valence <= 0  # Clipped to valid range
        assert 0 <= state.arousal <= 1.0

    def test_unicode_task_description(self):
        es = EmotionalSystem()
        state = es.appraise_task("Fehler im System beheben")  # German
        assert state.dominant_emotion is not None

    def test_task_with_special_characters(self):
        es = EmotionalSystem()
        state = es.appraise_task("Fix the #1 bug: error@line:42!")
        assert state.dominant_emotion is not None

    def test_repeated_appraisal_same_task(self):
        """Emotional inertia should mean repeated same-task produces consistent state."""
        es = EmotionalSystem()
        states = []
        for _ in range(10):
            s = es.appraise_task("critical error crash")
            states.append((s.valence, s.arousal))

        # Should converge (last few should be similar)
        final_v = states[-1][0]
        assert abs(states[-1][0] - states[-2][0]) < 0.05


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
