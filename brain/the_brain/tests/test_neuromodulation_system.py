"""
Comprehensive tests for NeuromodulationSystem (core/neuromodulation.py)

Covers:
- Initialization and defaults
- Serialization (to_dict)
- Dopamine reward dynamics (positive and negative RPE)
- Serotonin dynamics
- Norepinephrine dynamics
- Decay toward baseline
- compute_effects structure and responsiveness
- get_state_description output
- Boundary clamping (levels stay in [0, 1])
- Reward prediction error computation
- Sequential reward accumulation
- Reset via re-initialization
- Thread safety (concurrent access without crash)
"""

import sys
import os
import math
import threading
import pytest

# Ensure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.neuromodulation import (
    NeuromodulationSystem,
    NeuromodulatorLevels,
    NeuromodulatorEffects,
)


# ---------------------------------------------------------------------------
# 1. Default initialization -- all levels at baseline 0.5
# ---------------------------------------------------------------------------
class TestDefaultInitialization:
    def test_default_levels_at_baseline(self):
        nms = NeuromodulationSystem()
        assert nms.levels.dopamine == pytest.approx(0.5)
        assert nms.levels.serotonin == pytest.approx(0.5)
        assert nms.levels.norepinephrine == pytest.approx(0.5)
        assert nms.total_updates == 0
        assert nms.expected_reward == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 2. Levels to_dict serialization
# ---------------------------------------------------------------------------
class TestLevelsToDict:
    def test_levels_to_dict_keys_and_values(self):
        nms = NeuromodulationSystem()
        d = nms.levels.to_dict()
        assert isinstance(d, dict)
        assert set(d.keys()) == {"dopamine", "serotonin", "norepinephrine"}
        for key in d:
            assert isinstance(d[key], float)
            assert d[key] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 3. Dopamine response to positive reward
# ---------------------------------------------------------------------------
class TestDopaminePositiveReward:
    def test_dopamine_increases_on_positive_reward(self):
        nms = NeuromodulationSystem()
        initial_da = nms.levels.dopamine
        # Reward of 1.0 vs expected 0.5 => positive RPE => dopamine rises
        rpe = nms.update_dopamine(reward=1.0)
        assert rpe > 0, "RPE should be positive for reward > expected"
        assert nms.levels.dopamine > initial_da, "Dopamine should increase"


# ---------------------------------------------------------------------------
# 4. Dopamine response to negative reward
# ---------------------------------------------------------------------------
class TestDopamineNegativeReward:
    def test_dopamine_decreases_on_negative_reward(self):
        nms = NeuromodulationSystem()
        initial_da = nms.levels.dopamine
        # Reward of 0.0 vs expected 0.5 => negative RPE => dopamine drops
        rpe = nms.update_dopamine(reward=0.0)
        assert rpe < 0, "RPE should be negative for reward < expected"
        assert nms.levels.dopamine < initial_da, "Dopamine should decrease"


# ---------------------------------------------------------------------------
# 5. Serotonin dynamics
# ---------------------------------------------------------------------------
class TestSerotoninDynamics:
    def test_serotonin_increases_with_high_success(self):
        nms = NeuromodulationSystem()
        initial_5ht = nms.levels.serotonin
        # High success rate + high consistency should push serotonin up
        nms.update_serotonin(recent_success_rate=1.0, consistency=1.0)
        assert nms.levels.serotonin > initial_5ht

    def test_serotonin_decreases_with_low_success(self):
        nms = NeuromodulationSystem()
        initial_5ht = nms.levels.serotonin
        # Low success rate + low consistency should push serotonin down
        nms.update_serotonin(recent_success_rate=0.0, consistency=0.0)
        assert nms.levels.serotonin < initial_5ht


# ---------------------------------------------------------------------------
# 6. Norepinephrine dynamics
# ---------------------------------------------------------------------------
class TestNorepinephrineDynamics:
    def test_norepinephrine_increases_with_high_urgency_and_threat(self):
        nms = NeuromodulationSystem()
        initial_ne = nms.levels.norepinephrine
        nms.update_norepinephrine(urgency=1.0, threat=1.0, complexity=1.0)
        assert nms.levels.norepinephrine > initial_ne

    def test_norepinephrine_decreases_with_low_urgency(self):
        nms = NeuromodulationSystem()
        initial_ne = nms.levels.norepinephrine
        nms.update_norepinephrine(urgency=0.0, threat=0.0, complexity=0.0)
        assert nms.levels.norepinephrine < initial_ne


# ---------------------------------------------------------------------------
# 7. Decay toward baseline
# ---------------------------------------------------------------------------
class TestDecayTowardBaseline:
    def test_decay_moves_elevated_dopamine_toward_baseline(self):
        nms = NeuromodulationSystem()
        # Push dopamine high
        nms.levels.dopamine = 0.9
        before = nms.levels.dopamine
        nms.apply_decay()
        # After decay, dopamine should be closer to 0.5
        assert abs(nms.levels.dopamine - 0.5) < abs(before - 0.5)

    def test_decay_moves_depressed_dopamine_toward_baseline(self):
        nms = NeuromodulationSystem()
        nms.levels.dopamine = 0.1
        before = nms.levels.dopamine
        nms.apply_decay()
        assert abs(nms.levels.dopamine - 0.5) < abs(before - 0.5)


# ---------------------------------------------------------------------------
# 8. Multiple decay steps converge to baseline
# ---------------------------------------------------------------------------
class TestMultipleDecayConvergence:
    def test_many_decays_converge_to_baseline(self):
        nms = NeuromodulationSystem()
        nms.levels.dopamine = 1.0
        nms.levels.serotonin = 0.0
        nms.levels.norepinephrine = 0.9
        for _ in range(200):
            nms.apply_decay()
        assert nms.levels.dopamine == pytest.approx(0.5, abs=0.01)
        assert nms.levels.serotonin == pytest.approx(0.5, abs=0.01)
        assert nms.levels.norepinephrine == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# 9. compute_effects returns valid structure
# ---------------------------------------------------------------------------
class TestComputeEffectsStructure:
    def test_compute_effects_returns_neuromodulator_effects(self):
        nms = NeuromodulationSystem()
        effects = nms.compute_effects()
        assert isinstance(effects, NeuromodulatorEffects)
        assert hasattr(effects, "learning_rate_multiplier")
        assert hasattr(effects, "exploration_boost")
        assert hasattr(effects, "attention_focus_multiplier")
        assert hasattr(effects, "confidence_threshold_delta")
        assert hasattr(effects, "response_urgency")


# ---------------------------------------------------------------------------
# 10. Effects respond to dopamine changes
# ---------------------------------------------------------------------------
class TestEffectsRespondToDopamine:
    def test_high_dopamine_increases_learning_rate_and_exploration(self):
        nms = NeuromodulationSystem()
        baseline_effects = nms.compute_effects()

        nms.levels.dopamine = 0.9
        high_da_effects = nms.compute_effects()

        assert high_da_effects.learning_rate_multiplier > baseline_effects.learning_rate_multiplier
        assert high_da_effects.exploration_boost > baseline_effects.exploration_boost


# ---------------------------------------------------------------------------
# 11. Effects respond to norepinephrine changes
# ---------------------------------------------------------------------------
class TestEffectsRespondToNE:
    def test_high_ne_increases_attention_and_urgency(self):
        nms = NeuromodulationSystem()
        baseline_effects = nms.compute_effects()

        nms.levels.norepinephrine = 0.9
        high_ne_effects = nms.compute_effects()

        assert high_ne_effects.attention_focus_multiplier > baseline_effects.attention_focus_multiplier
        assert high_ne_effects.response_urgency > baseline_effects.response_urgency


# ---------------------------------------------------------------------------
# 12. get_state_description returns string
# ---------------------------------------------------------------------------
class TestGetStateDescription:
    def test_state_description_is_string(self):
        nms = NeuromodulationSystem()
        desc = nms.get_state_description()
        assert isinstance(desc, str)
        assert len(desc) > 0


# ---------------------------------------------------------------------------
# 13. Levels stay in [0, 1] range after large positive reward
# ---------------------------------------------------------------------------
class TestLevelsClamping:
    def test_levels_clamped_after_large_positive_rewards(self):
        nms = NeuromodulationSystem()
        # Push dopamine extremely high with many large rewards
        for _ in range(100):
            nms.update_dopamine(reward=1.0, expected_reward=0.0)
        nms.levels.clip()
        assert 0.0 <= nms.levels.dopamine <= 1.0
        assert 0.0 <= nms.levels.serotonin <= 1.0
        assert 0.0 <= nms.levels.norepinephrine <= 1.0


# ---------------------------------------------------------------------------
# 14. Levels stay in [0, 1] range after large negative reward
# ---------------------------------------------------------------------------
class TestLevelsClampingNegative:
    def test_levels_clamped_after_large_negative_rewards(self):
        nms = NeuromodulationSystem()
        # Push dopamine extremely low with many negative RPE
        for _ in range(100):
            nms.update_dopamine(reward=0.0, expected_reward=1.0)
        nms.levels.clip()
        assert 0.0 <= nms.levels.dopamine <= 1.0


# ---------------------------------------------------------------------------
# 15. RPE (reward prediction error) computation
# ---------------------------------------------------------------------------
class TestRPEComputation:
    def test_rpe_equals_reward_minus_expected(self):
        nms = NeuromodulationSystem()
        expected = 0.3
        reward = 0.8
        rpe = nms.update_dopamine(reward=reward, expected_reward=expected)
        assert rpe == pytest.approx(reward - expected)

    def test_rpe_stored_in_history(self):
        nms = NeuromodulationSystem()
        nms.update_dopamine(reward=0.9, expected_reward=0.5)
        assert len(nms.reward_prediction_errors) == 1
        assert nms.reward_prediction_errors[0] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 16. Effects to_dict serialization
# ---------------------------------------------------------------------------
class TestEffectsToDict:
    def test_effects_to_dict_keys_and_types(self):
        nms = NeuromodulationSystem()
        effects = nms.compute_effects()
        d = effects.to_dict()
        assert isinstance(d, dict)
        expected_keys = {
            "learning_rate_multiplier",
            "exploration_boost",
            "attention_focus_multiplier",
            "confidence_threshold_delta",
            "response_urgency",
        }
        assert set(d.keys()) == expected_keys
        for v in d.values():
            assert isinstance(v, float)


# ---------------------------------------------------------------------------
# 17. Multiple sequential rewards accumulate
# ---------------------------------------------------------------------------
class TestSequentialRewardAccumulation:
    def test_sequential_successes_raise_dopamine_above_single(self):
        nms_single = NeuromodulationSystem()
        nms_single.update_dopamine(reward=1.0)
        single_da = nms_single.levels.dopamine

        nms_multi = NeuromodulationSystem()
        nms_multi.update_dopamine(reward=1.0)
        nms_multi.update_dopamine(reward=1.0)
        multi_da = nms_multi.levels.dopamine

        assert multi_da > single_da, "Two positive rewards should push dopamine higher"


# ---------------------------------------------------------------------------
# 18. Reset functionality (re-init to baseline)
# ---------------------------------------------------------------------------
class TestResetFunctionality:
    def test_new_instance_resets_to_baseline(self):
        nms = NeuromodulationSystem()
        # Perturb the system heavily
        for _ in range(10):
            nms.update(outcome="success", urgency=1.0, threat=1.0)
        assert nms.total_updates == 10

        # Create a fresh instance -- effectively a reset
        nms2 = NeuromodulationSystem()
        assert nms2.levels.dopamine == pytest.approx(0.5)
        assert nms2.levels.serotonin == pytest.approx(0.5)
        assert nms2.levels.norepinephrine == pytest.approx(0.5)
        assert nms2.total_updates == 0
        assert len(nms2.reward_prediction_errors) == 0


# ---------------------------------------------------------------------------
# 19. State description changes with levels
# ---------------------------------------------------------------------------
class TestStateDescriptionChanges:
    def test_high_dopamine_shows_motivated(self):
        nms = NeuromodulationSystem()
        nms.levels.dopamine = 0.8
        desc = nms.get_state_description()
        assert "MOTIVATED" in desc

    def test_low_dopamine_shows_demotivated(self):
        nms = NeuromodulationSystem()
        nms.levels.dopamine = 0.2
        desc = nms.get_state_description()
        assert "DEMOTIVATED" in desc

    def test_high_serotonin_shows_patient(self):
        nms = NeuromodulationSystem()
        nms.levels.serotonin = 0.8
        desc = nms.get_state_description()
        assert "PATIENT" in desc

    def test_high_ne_shows_alert(self):
        nms = NeuromodulationSystem()
        nms.levels.norepinephrine = 0.8
        desc = nms.get_state_description()
        assert "ALERT" in desc


# ---------------------------------------------------------------------------
# 20. Thread safety -- concurrent access without crash
# ---------------------------------------------------------------------------
class TestThreadSafety:
    def test_concurrent_updates_do_not_crash(self):
        nms = NeuromodulationSystem()
        errors = []

        def worker(outcome):
            try:
                for _ in range(50):
                    nms.update(
                        outcome=outcome,
                        urgency=0.5,
                        threat=0.0,
                        complexity=0.5,
                        recent_success_rate=0.5,
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=("success",)),
            threading.Thread(target=worker, args=("failure",)),
            threading.Thread(target=worker, args=("success",)),
            threading.Thread(target=worker, args=("failure",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(errors) == 0, f"Concurrent access caused errors: {errors}"
        # After all updates, levels should still be within valid range
        nms.levels.clip()
        assert 0.0 <= nms.levels.dopamine <= 1.0
        assert 0.0 <= nms.levels.serotonin <= 1.0
        assert 0.0 <= nms.levels.norepinephrine <= 1.0
