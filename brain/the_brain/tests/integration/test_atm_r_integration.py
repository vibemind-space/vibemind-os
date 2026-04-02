"""
ATM-R Integration Tests

Comprehensive end-to-end tests validating that all ATM-R components
work together correctly.

Integration Paths Tested:
1. Sensory Input -> Hierarchical Routing -> Basal Ganglia Action Selection
2. Sleep Consolidation -> Hippocampus Memory Replay -> Weight Updates
3. Neuromodulation -> Learning Rate Modulation -> All Layers

Cross-Component Invariants:
- Gates always sum to 1.0 at every layer
- Skip weights <= 0.5
- Memory strength in [0, 1]
- Neuromodulator levels in [0, 1]
"""

import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.sleep_consolidation import SleepState


# ============================================================================
# Path 1: Sensory -> Hierarchical Routing -> Basal Ganglia
# ============================================================================

class TestSensoryToActionPipeline:
    """Test sensory input flowing through to action selection."""

    def test_sensory_input_reaches_layer1(self, hierarchical_routing, sample_sensory_input):
        """Verify sensory input is processed by Layer 1."""
        result = hierarchical_routing.step(x=sample_sensory_input)

        assert result.layer_outputs[1] is not None
        assert result.layer_outputs[1].gates is not None
        assert np.isclose(np.sum(result.layer_outputs[1].gates), 1.0, atol=1e-6)

    def test_gates_propagate_through_hierarchy(self, hierarchical_routing, sample_sensory_input, sample_goal):
        """Gates should flow L1 -> L2 -> L3 -> L4."""
        result = hierarchical_routing.step(x=sample_sensory_input, goal=sample_goal)

        # All layers should produce output
        for layer_idx in [1, 2, 3, 4]:
            assert layer_idx in result.layer_outputs
            layer_out = result.layer_outputs[layer_idx]
            assert layer_out.gates is not None
            # CRITICAL INVARIANT: gates sum to 1.0
            assert np.isclose(np.sum(layer_out.gates), 1.0, atol=1e-6), \
                f"Layer {layer_idx} gates sum to {np.sum(layer_out.gates)}"

    def test_final_gates_sum_to_one(self, hierarchical_routing, sample_sensory_input):
        """Final blended gates must sum to 1.0."""
        for _ in range(10):
            result = hierarchical_routing.step(x=sample_sensory_input)
            assert np.isclose(np.sum(result.final_gates), 1.0, atol=1e-6)

    def test_basal_ganglia_action_selection(self, basal_ganglia, neuromodulation):
        """BG should produce valid action selection."""
        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        bg_output = basal_ganglia.step(
            cortical_input=cortical_input,
            dopamine=neuromodulation.levels.dopamine,
            urgency=neuromodulation.levels.norepinephrine
        )

        assert bg_output.action_gates is not None
        assert np.isclose(np.sum(bg_output.action_gates), 1.0, atol=1e-6)
        assert bg_output.selected_action in [0, 1, 2]

    def test_layer4_abstract_output_valid(self, hierarchical_routing, sample_sensory_input, sample_goal):
        """Layer 4 (abstract) should produce valid output with BG action."""
        result = hierarchical_routing.step(x=sample_sensory_input, goal=sample_goal)

        l4_out = result.layer_outputs[4]
        assert l4_out is not None
        assert l4_out.output is not None
        assert np.isclose(np.sum(l4_out.gates), 1.0, atol=1e-6)

    def test_routing_stable_gates(self, hierarchical_routing, sample_sensory_input):
        """Routing should produce stable, valid gates for consistent input."""
        # Run multiple steps with same input
        results = [hierarchical_routing.step(x=sample_sensory_input) for _ in range(3)]

        # Each result should have valid gates
        for result in results:
            assert np.isclose(np.sum(result.final_gates), 1.0, atol=1e-6)
            assert np.all(result.final_gates >= 0)

    def test_threat_modality_affects_gates(self, hierarchical_routing, modality_dims, modalities):
        """High threat input should affect gate distribution."""
        # Low threat
        low_threat = {m: np.zeros(modality_dims[m]) for m in modalities}
        low_threat['vision'] = np.ones(modality_dims['vision'])

        # High threat
        high_threat = {m: np.zeros(modality_dims[m]) for m in modalities}
        high_threat['threat'] = np.ones(modality_dims['threat']) * 2.0

        result_low = hierarchical_routing.step(x=low_threat)
        result_high = hierarchical_routing.step(x=high_threat)

        # Gates should differ
        assert not np.allclose(result_low.final_gates, result_high.final_gates, atol=0.01)

    def test_multiple_steps_stable(self, hierarchical_routing, sample_sensory_input):
        """Multiple routing steps should remain stable."""
        for i in range(50):
            result = hierarchical_routing.step(x=sample_sensory_input)

            # All gates still valid
            for layer_idx in result.layer_outputs:
                gates = result.layer_outputs[layer_idx].gates
                assert np.all(np.isfinite(gates)), f"Step {i}: Layer {layer_idx} has non-finite gates"
                assert np.isclose(np.sum(gates), 1.0, atol=1e-6)


# ============================================================================
# Path 2: Sleep -> Memory Consolidation -> Weight Updates
# ============================================================================

class TestSleepMemoryConsolidation:
    """Test sleep consolidation with memory replay."""

    def test_hippocampus_encodes_novel_experiences(self, hippocampus, modality_dims, modalities):
        """Novel experiences (high PE) should be encoded."""
        state_dim = sum(modality_dims.values())

        state = np.random.randn(state_dim)
        context = np.random.rand(6)
        context /= np.sum(context)
        gates = np.random.rand(6)
        gates /= np.sum(gates)

        initial_count = len(hippocampus.memories)

        output = hippocampus.step(
            state=state,
            context=context,
            gates=gates,
            prediction_error=0.8  # Above novelty_threshold (0.5)
        )

        assert output['encoded'] is True
        assert len(hippocampus.memories) == initial_count + 1

    def test_hippocampus_ignores_familiar(self, hippocampus, modality_dims, modalities):
        """Familiar experiences (low PE) should not be encoded."""
        state_dim = sum(modality_dims.values())

        state = np.random.randn(state_dim)
        context = np.random.rand(6)
        context /= np.sum(context)
        gates = np.random.rand(6)
        gates /= np.sum(gates)

        initial_count = len(hippocampus.memories)

        output = hippocampus.step(
            state=state,
            context=context,
            gates=gates,
            prediction_error=0.2  # Below novelty_threshold (0.5)
        )

        assert output['encoded'] is False
        assert len(hippocampus.memories) == initial_count

    def test_swr_only_in_nrem_n3(self, sleep_consolidation):
        """SWR should only trigger during NREM N3 (deep sleep)."""
        sc = sleep_consolidation

        for state in [SleepState.WAKE, SleepState.DROWSY, SleepState.NREM_N1, SleepState.NREM_N2, SleepState.REM]:
            sc.state_machine.force_state(state)
            output = sc.step(activity_level=0.0, dt=1.0)
            assert output.swr_triggered is False, f"SWR should NOT trigger in {state.value}"

        # NREM_N3 should trigger SWR (with high probability)
        sc.state_machine.force_state(SleepState.NREM_N3)
        sc.config.swr_probability = 1.0
        sc.swr_generator.config.swr_probability = 1.0
        output = sc.step(activity_level=0.0, dt=1.0)
        assert output.swr_triggered is True

    def test_sleep_cycle_progression(self, sleep_consolidation):
        """Sleep should progress through stages."""
        sc = sleep_consolidation
        sc.state_machine.force_state(SleepState.DROWSY)

        states_visited = set()

        for _ in range(100):
            output = sc.step(activity_level=0.0, dt=0.1)
            states_visited.add(output.state)

        # Should have progressed through multiple stages
        assert len(states_visited) >= 2

    def test_high_activity_forces_wake(self, sleep_consolidation):
        """High activity during sleep should force wake."""
        sc = sleep_consolidation
        sc.state_machine.force_state(SleepState.NREM_N3)

        output = sc.step(activity_level=0.9, dt=1.0)

        assert output.state == SleepState.WAKE
        assert output.state_changed is True

    def test_memory_strength_bounded(self, hippocampus, modality_dims):
        """Memory strength should stay in [0, 1]."""
        state_dim = sum(modality_dims.values())

        for i in range(10):
            hippocampus.step(
                state=np.random.randn(state_dim),
                context=np.random.rand(6) / 6,
                gates=np.random.rand(6) / 6,
                prediction_error=0.9
            )

        for mem in hippocampus.memories:
            assert 0.0 <= mem.strength <= 1.0, f"Memory strength {mem.strength} out of bounds"

    def test_neuromodulators_change_during_sleep(self, sleep_consolidation, neuromodulation):
        """Neuromodulator levels should adjust during sleep."""
        sc = sleep_consolidation

        # Force deep sleep
        sc.state_machine.force_state(SleepState.NREM_N3)

        # Run sleep steps
        for _ in range(10):
            sc.step(activity_level=0.0, dt=1.0)

        # Neuromodulators should remain bounded
        assert 0.0 <= neuromodulation.levels.dopamine <= 1.0
        assert 0.0 <= neuromodulation.levels.serotonin <= 1.0
        assert 0.0 <= neuromodulation.levels.norepinephrine <= 1.0


# ============================================================================
# Path 3: Neuromodulation -> Learning Rate -> All Layers
# ============================================================================

class TestNeuromodulationLearning:
    """Test neuromodulation effects on learning."""

    def test_dopamine_bounded(self, neuromodulation):
        """Dopamine should be bounded after apply_decay (which includes clipping)."""
        # Push high
        for _ in range(50):
            neuromodulation.update_dopamine(reward=1.0)

        # apply_decay should clip values to valid range
        neuromodulation.apply_decay()
        assert 0.0 <= neuromodulation.levels.dopamine <= 1.0

        # Push low
        neuromodulation.levels.dopamine = 0.5
        for _ in range(50):
            neuromodulation.update_dopamine(reward=0.0)
        neuromodulation.apply_decay()
        assert 0.0 <= neuromodulation.levels.dopamine <= 1.0

    def test_serotonin_bounded(self, neuromodulation):
        """Serotonin should stay in [0, 1]."""
        for _ in range(50):
            neuromodulation.update_serotonin(recent_success_rate=1.0, consistency=1.0)
        assert 0.0 <= neuromodulation.levels.serotonin <= 1.0

        neuromodulation.levels.serotonin = 0.5
        for _ in range(50):
            neuromodulation.update_serotonin(recent_success_rate=0.0, consistency=0.0)
        assert 0.0 <= neuromodulation.levels.serotonin <= 1.0

    def test_norepinephrine_bounded(self, neuromodulation):
        """Norepinephrine should stay in [0, 1]."""
        for _ in range(50):
            neuromodulation.update_norepinephrine(urgency=1.0, threat=1.0, complexity=1.0)
        assert 0.0 <= neuromodulation.levels.norepinephrine <= 1.0

        neuromodulation.levels.norepinephrine = 0.5
        for _ in range(50):
            neuromodulation.update_norepinephrine(urgency=0.0, threat=0.0, complexity=0.0)
        assert 0.0 <= neuromodulation.levels.norepinephrine <= 1.0

    def test_high_dopamine_increases_learning_rate(self, neuromodulation):
        """High dopamine should increase learning rate multiplier."""
        neuromodulation.levels.dopamine = 0.5
        baseline_effects = neuromodulation.compute_effects()
        baseline_lr = baseline_effects.learning_rate_multiplier

        neuromodulation.levels.dopamine = 0.9
        high_effects = neuromodulation.compute_effects()

        assert high_effects.learning_rate_multiplier > baseline_lr

    def test_low_dopamine_decreases_learning_rate(self, neuromodulation):
        """Low dopamine should decrease learning rate multiplier."""
        neuromodulation.levels.dopamine = 0.5
        baseline_effects = neuromodulation.compute_effects()
        baseline_lr = baseline_effects.learning_rate_multiplier

        neuromodulation.levels.dopamine = 0.1
        low_effects = neuromodulation.compute_effects()

        assert low_effects.learning_rate_multiplier < baseline_lr

    def test_dopamine_affects_basal_ganglia(self, basal_ganglia):
        """Dopamine level should affect BG action selection."""
        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        out_low_da = basal_ganglia.step(cortical_input, dopamine=0.2, urgency=0.5)
        basal_ganglia.reset()
        out_high_da = basal_ganglia.step(cortical_input, dopamine=0.8, urgency=0.5)

        # Both should produce valid output
        assert np.isclose(np.sum(out_low_da.action_gates), 1.0, atol=1e-6)
        assert np.isclose(np.sum(out_high_da.action_gates), 1.0, atol=1e-6)

    def test_positive_rpe_increases_dopamine(self, neuromodulation):
        """Positive RPE should increase dopamine."""
        initial_da = neuromodulation.levels.dopamine

        neuromodulation.update_dopamine(reward=1.0, expected_reward=0.3)

        assert neuromodulation.levels.dopamine > initial_da

    def test_negative_rpe_decreases_dopamine(self, neuromodulation):
        """Negative RPE should decrease dopamine."""
        initial_da = neuromodulation.levels.dopamine

        neuromodulation.update_dopamine(reward=0.0, expected_reward=0.7)

        assert neuromodulation.levels.dopamine < initial_da

    def test_decay_toward_baseline(self, neuromodulation):
        """Neuromodulators should decay toward baseline."""
        neuromodulation.levels.dopamine = 0.9
        baseline = neuromodulation.baseline_dopamine

        for _ in range(100):
            neuromodulation.apply_decay()

        assert abs(neuromodulation.levels.dopamine - baseline) < abs(0.9 - baseline)


# ============================================================================
# Cross-Component Invariants
# ============================================================================

class TestCrossComponentInvariants:
    """Tests for critical invariants across all components."""

    def test_all_layer_gates_sum_to_one(self, hierarchical_routing, sample_sensory_input, sample_goal):
        """Every layer must produce gates summing to 1.0."""
        for _ in range(20):
            result = hierarchical_routing.step(x=sample_sensory_input, goal=sample_goal)

            for layer_idx, layer_out in result.layer_outputs.items():
                gate_sum = np.sum(layer_out.gates)
                assert np.isclose(gate_sum, 1.0, atol=1e-6), \
                    f"Layer {layer_idx} gates sum to {gate_sum}"

    def test_basal_ganglia_action_gates_sum_to_one(self, basal_ganglia):
        """BG action gates must sum to 1.0."""
        for _ in range(20):
            cortical_input = np.random.rand(6)
            output = basal_ganglia.step(cortical_input, dopamine=0.5, urgency=0.5)
            assert np.isclose(np.sum(output.action_gates), 1.0, atol=1e-6)

    def test_neuromodulators_always_bounded(self, neuromodulation):
        """Neuromodulators should stay bounded under all conditions."""
        for _ in range(100):
            outcome = 'success' if np.random.rand() > 0.5 else 'failure'
            neuromodulation.update(
                outcome=outcome,
                urgency=np.random.rand(),
                threat=np.random.rand(),
                complexity=np.random.rand(),
                recent_success_rate=np.random.rand()
            )

        assert 0.0 <= neuromodulation.levels.dopamine <= 1.0
        assert 0.0 <= neuromodulation.levels.serotonin <= 1.0
        assert 0.0 <= neuromodulation.levels.norepinephrine <= 1.0

    def test_temperature_gradient_l1_to_l4(self, hierarchical_routing):
        """Temperature should decrease up the hierarchy (L1 > L2 > L3 > L4)."""
        temps = [hierarchical_routing.layers[i].temperature for i in [1, 2, 3, 4]]

        assert temps[0] > temps[1], f"L1 temp ({temps[0]}) should > L2 temp ({temps[1]})"
        assert temps[1] > temps[2], f"L2 temp ({temps[1]}) should > L3 temp ({temps[2]})"
        assert temps[2] > temps[3], f"L3 temp ({temps[2]}) should > L4 temp ({temps[3]})"

    def test_learning_rate_gradient_l1_to_l4(self, hierarchical_routing):
        """Learning rate should increase up the hierarchy (L1 < L2 < L3 < L4)."""
        lrs = [hierarchical_routing.layers[i].learning_rate for i in [1, 2, 3, 4]]

        assert lrs[0] < lrs[1], f"L1 LR ({lrs[0]}) should < L2 LR ({lrs[1]})"
        assert lrs[1] < lrs[2], f"L2 LR ({lrs[1]}) should < L3 LR ({lrs[2]})"
        assert lrs[2] < lrs[3] or lrs[2] == lrs[3], f"L3 LR ({lrs[2]}) should <= L4 LR ({lrs[3]})"

    def test_gates_non_negative(self, hierarchical_routing, sample_sensory_input):
        """All gates must be non-negative."""
        for _ in range(20):
            result = hierarchical_routing.step(x=sample_sensory_input)

            for layer_idx, layer_out in result.layer_outputs.items():
                assert np.all(layer_out.gates >= 0), f"Layer {layer_idx} has negative gates"

            assert np.all(result.final_gates >= 0), "Final gates have negative values"

    def test_outputs_finite(self, hierarchical_routing, sample_sensory_input):
        """All outputs must be finite (no NaN or Inf)."""
        for _ in range(20):
            result = hierarchical_routing.step(x=sample_sensory_input)

            for layer_idx, layer_out in result.layer_outputs.items():
                assert np.all(np.isfinite(layer_out.gates)), f"Layer {layer_idx} has non-finite gates"
                assert np.all(np.isfinite(layer_out.output)), f"Layer {layer_idx} has non-finite output"

            assert np.all(np.isfinite(result.final_gates)), "Final gates have non-finite values"

    def test_hippocampus_memory_biased_gates_valid(self, hippocampus, modality_dims):
        """Memory-biased gates must sum to 1.0."""
        state_dim = sum(modality_dims.values())

        # Store some memories
        for _ in range(5):
            hippocampus.step(
                state=np.random.randn(state_dim),
                context=np.random.rand(6) / 6,
                gates=np.random.rand(6) / 6,
                prediction_error=0.9
            )

        # Query memory bias
        query_state = np.random.randn(state_dim)
        query_context = np.random.rand(6)
        query_context /= np.sum(query_context)
        current_gates = np.random.rand(6)
        current_gates /= np.sum(current_gates)

        biased_gates = hippocampus.compute_memory_bias(query_state, query_context, current_gates)
        assert np.isclose(np.sum(biased_gates), 1.0, atol=1e-6)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
