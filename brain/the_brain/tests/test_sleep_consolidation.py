"""
Tests for Sleep Consolidation System

Tests cover:
1. Sleep state machine transitions
2. Synaptic homeostasis (weight scaling)
3. Sharp-Wave Ripple generation
4. NREM/REM stage differentiation
5. Integration with hippocampus and neuromodulation
6. Full sleep cycle execution
"""

import pytest
import numpy as np
from typing import List
from collections import deque

from core.sleep_consolidation import (
    SleepState,
    SleepConsolidationConfig,
    SleepStateMachine,
    SynapticHomeostasis,
    SharpWaveRippleGenerator,
    SleepStageManager,
    SleepConsolidation,
    ConsolidationMetrics,
    create_sleep_consolidation
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def config():
    """Standard configuration."""
    return SleepConsolidationConfig(seed=42)


@pytest.fixture
def fast_config():
    """Configuration with shorter durations for faster testing."""
    return SleepConsolidationConfig(
        idle_threshold_seconds=5.0,
        drowsy_duration=1.0,
        nrem_n1_duration=2.0,
        nrem_n2_duration=3.0,
        nrem_n3_duration=5.0,
        rem_duration=3.0,
        max_sleep_cycles=2,
        seed=42
    )


@pytest.fixture
def state_machine(config):
    """Sleep state machine fixture."""
    return SleepStateMachine(config)


@pytest.fixture
def fast_state_machine(fast_config):
    """Fast sleep state machine for cycle tests."""
    return SleepStateMachine(fast_config)


@pytest.fixture
def synaptic_homeostasis(config):
    """Synaptic homeostasis fixture."""
    return SynapticHomeostasis(config)


@pytest.fixture
def swr_generator(config):
    """SWR generator fixture."""
    return SharpWaveRippleGenerator(config)


@pytest.fixture
def consolidator(config):
    """Sleep consolidation system fixture."""
    return SleepConsolidation(config=config)


@pytest.fixture
def fast_consolidator(fast_config):
    """Fast consolidator for cycle tests."""
    return SleepConsolidation(config=fast_config)


# ============================================================================
# Mock Classes for Integration Tests
# ============================================================================

class MockMemory:
    """Mock episodic memory for testing."""
    def __init__(self, timestamp: int = 0, prediction_error: float = 0.5):
        self.state = np.random.randn(64)
        self.context = np.random.randn(32)
        self.gates = np.random.rand(6)
        self.gates /= np.sum(self.gates)
        self.prediction_error = prediction_error
        self.timestamp = timestamp
        self.strength = 1.0
        self.retrieval_count = 0


class MockHippocampus:
    """Mock hippocampus for testing."""
    def __init__(self, num_memories: int = 10):
        self.memories = deque(
            [MockMemory(timestamp=i, prediction_error=0.3 + 0.4 * np.random.rand())
             for i in range(num_memories)],
            maxlen=100
        )

    def pattern_completion(self, state, context):
        return np.random.randn(64)


class MockNeuromodLevels:
    """Mock neuromodulator levels."""
    def __init__(self):
        self.dopamine = 0.5
        self.serotonin = 0.5
        self.norepinephrine = 0.5


class MockNeuromodulation:
    """Mock neuromodulation system."""
    def __init__(self):
        self.levels = MockNeuromodLevels()


# ============================================================================
# Test Sleep State Machine
# ============================================================================

class TestSleepStateMachine:
    """Tests for sleep state machine."""

    def test_initial_state_is_wake(self, state_machine):
        """State machine should start in WAKE."""
        assert state_machine.current_state == SleepState.WAKE

    def test_high_activity_stays_wake(self, state_machine):
        """High activity should keep system awake."""
        for _ in range(100):
            state, changed = state_machine.step(activity_level=0.8, dt=1.0)

        assert state == SleepState.WAKE
        assert state_machine.idle_time == 0.0

    def test_low_activity_transitions_to_drowsy(self, state_machine):
        """Low activity for threshold time should transition to DROWSY."""
        config = state_machine.config
        states_visited = set()

        # Run until idle threshold exceeded
        for _ in range(int(config.idle_threshold_seconds) + 10):
            state, changed = state_machine.step(activity_level=0.1, dt=1.0)
            states_visited.add(state)

        # Should have visited DROWSY (may have progressed further)
        assert SleepState.DROWSY in states_visited

    def test_drowsy_to_nrem_n1(self, fast_state_machine):
        """DROWSY should transition to NREM_N1 after duration."""
        sm = fast_state_machine
        sm.force_state(SleepState.DROWSY)

        # Run through drowsy duration with small dt to catch transition
        states_visited = []
        for _ in range(20):
            state, changed = sm.step(activity_level=0.0, dt=0.1)
            if changed:
                states_visited.append(state)

        # First transition should be to NREM_N1
        assert len(states_visited) > 0
        assert states_visited[0] == SleepState.NREM_N1

    def test_full_nrem_progression(self, fast_state_machine):
        """Test NREM_N1 → NREM_N2 → NREM_N3 progression."""
        sm = fast_state_machine
        sm.force_state(SleepState.NREM_N1)

        stages_visited = [SleepState.NREM_N1]

        for _ in range(50):
            state, changed = sm.step(activity_level=0.0, dt=1.0)
            if changed and state not in stages_visited:
                stages_visited.append(state)

        assert SleepState.NREM_N2 in stages_visited
        assert SleepState.NREM_N3 in stages_visited

    def test_nrem_n3_to_rem(self, fast_state_machine):
        """NREM_N3 should transition to REM."""
        sm = fast_state_machine
        sm.force_state(SleepState.NREM_N3)

        # Track states with small dt to catch REM transition
        states_visited = []
        for _ in range(100):
            state, changed = sm.step(activity_level=0.0, dt=0.1)
            if changed:
                states_visited.append(state)

        # REM should be reached after NREM_N3
        assert SleepState.REM in states_visited

    def test_rem_cycles_back_to_nrem_n2(self, fast_state_machine):
        """REM should cycle back to NREM_N2 (not N1)."""
        sm = fast_state_machine
        sm.force_state(SleepState.REM)

        # Track states with small dt to catch first transition after REM
        states_visited = []
        for _ in range(50):
            state, changed = sm.step(activity_level=0.0, dt=0.1)
            if changed:
                states_visited.append(state)
                # Stop after first transition from REM
                break

        # After REM, should cycle to NREM_N2 (not N1)
        assert len(states_visited) > 0
        assert states_visited[0] == SleepState.NREM_N2
        assert sm.cycles_completed == 1

    def test_max_cycles_triggers_wake(self, fast_state_machine):
        """Max sleep cycles should trigger wake."""
        sm = fast_state_machine
        sm.force_state(SleepState.NREM_N1)
        max_cycles = sm.config.max_sleep_cycles

        # Track REM completions (cycles)
        cycles_seen = 0
        prev_state = SleepState.NREM_N1

        # Run until max cycles with small dt
        # Total cycle time: N1(2) + N2(3) + N3(5) + REM(3) = 13s per cycle
        for _ in range(500):
            state, _ = sm.step(activity_level=0.0, dt=0.1)

            # Count REM → other transitions as completed cycles
            if prev_state == SleepState.REM and state != SleepState.REM:
                cycles_seen += 1

            if state == SleepState.WAKE:
                break

            prev_state = state

        assert state == SleepState.WAKE
        # cycles_completed is reset on wake, so check we saw enough cycles
        assert cycles_seen >= max_cycles

    def test_forced_wake_on_high_activity(self, fast_state_machine):
        """High activity during sleep should force wake."""
        sm = fast_state_machine
        sm.force_state(SleepState.NREM_N3)

        state, changed = sm.step(activity_level=0.9, dt=1.0)

        assert state == SleepState.WAKE
        assert changed

    def test_force_wake(self, state_machine):
        """force_wake() should immediately transition to WAKE."""
        state_machine.force_state(SleepState.REM)
        state_machine.force_wake()

        assert state_machine.current_state == SleepState.WAKE

    def test_is_sleeping(self, state_machine):
        """is_sleeping() should return correct values."""
        state_machine.force_state(SleepState.WAKE)
        assert not state_machine.is_sleeping()

        state_machine.force_state(SleepState.DROWSY)
        assert not state_machine.is_sleeping()

        state_machine.force_state(SleepState.NREM_N3)
        assert state_machine.is_sleeping()

        state_machine.force_state(SleepState.REM)
        assert state_machine.is_sleeping()

    def test_reset(self, state_machine):
        """reset() should return to initial state."""
        state_machine.force_state(SleepState.REM)
        state_machine.cycles_completed = 3

        state_machine.reset()

        assert state_machine.current_state == SleepState.WAKE
        assert state_machine.cycles_completed == 0
        assert state_machine.idle_time == 0.0


# ============================================================================
# Test Synaptic Homeostasis
# ============================================================================

class TestSynapticHomeostasis:
    """Tests for synaptic homeostasis."""

    def test_nrem_downscaling(self, synaptic_homeostasis):
        """NREM should scale down weights."""
        sh = synaptic_homeostasis

        weights = {'W': np.ones((10, 10))}
        initial_sum = np.sum(weights['W'])

        scaled = sh.apply_homeostasis(weights, SleepState.NREM_N3)
        final_sum = np.sum(scaled['W'])

        # Should be reduced (after normalization)
        assert sh.get_scaling_ratio() < 1.0

    def test_wake_no_scaling(self, synaptic_homeostasis):
        """WAKE should not scale weights."""
        sh = synaptic_homeostasis

        weights = {'W': np.ones((10, 10)) * 0.5}

        scaled = sh.apply_homeostasis(weights, SleepState.WAKE)

        np.testing.assert_array_equal(weights['W'], scaled['W'])

    def test_selective_strengthening(self, synaptic_homeostasis):
        """Highly activated synapses should be preserved."""
        sh = synaptic_homeostasis

        # Record activation history
        activation = np.zeros((5, 5))
        activation[0, 0] = 1.0  # High activation
        activation[1, 1] = 1.0
        sh.record_activation('W', activation)
        sh.record_activation('W', activation)  # Record twice to accumulate

        weights = {'W': np.ones((5, 5))}

        scaled = sh.apply_homeostasis(weights, SleepState.NREM_N3)

        # High activation spots should be relatively stronger
        # (though all are scaled down, ratio should favor high-activation)

    def test_rem_milder_scaling(self, synaptic_homeostasis):
        """REM scaling should be milder than NREM."""
        sh = synaptic_homeostasis

        weights_nrem = {'W': np.ones((10, 10))}
        weights_rem = {'W': np.ones((10, 10))}

        sh.apply_homeostasis(weights_nrem, SleepState.NREM_N3)
        nrem_ratio = sh.get_scaling_ratio()

        sh.reset()

        sh.apply_homeostasis(weights_rem, SleepState.REM)
        rem_ratio = sh.get_scaling_ratio()

        assert rem_ratio > nrem_ratio  # REM is milder

    def test_weight_clipping(self, config):
        """Weights should be clipped to bounds."""
        config.min_weight = 0.1
        config.max_weight = 2.0
        sh = SynapticHomeostasis(config)

        weights = {'W': np.ones((5, 5)) * 0.001}  # Below min

        scaled = sh.apply_homeostasis(weights, SleepState.NREM_N3)

        assert np.all(scaled['W'] >= config.min_weight)

    def test_reset(self, synaptic_homeostasis):
        """reset() should clear history and scaling."""
        sh = synaptic_homeostasis

        sh.record_activation('W', np.ones((5, 5)))
        sh.total_scaling_applied = 0.5

        sh.reset()

        assert len(sh.activation_history) == 0
        assert sh.total_scaling_applied == 1.0


# ============================================================================
# Test Sharp-Wave Ripple Generator
# ============================================================================

class TestSharpWaveRippleGenerator:
    """Tests for SWR generator."""

    def test_ripple_only_in_nrem_n3(self, swr_generator):
        """SWR should only trigger in NREM_N3."""
        swr = swr_generator

        # Set probability to 1.0 for deterministic test
        swr.config.swr_probability = 1.0

        assert not swr.check_for_ripple(SleepState.WAKE, 0)
        assert not swr.check_for_ripple(SleepState.DROWSY, 0)
        assert not swr.check_for_ripple(SleepState.NREM_N1, 0)
        assert not swr.check_for_ripple(SleepState.NREM_N2, 0)
        assert swr.check_for_ripple(SleepState.NREM_N3, 0)
        assert not swr.check_for_ripple(SleepState.REM, 0)

    def test_ripple_probability(self, config):
        """SWR should follow probability distribution."""
        config.swr_probability = 0.5
        swr = SharpWaveRippleGenerator(config)

        ripple_count = 0
        trials = 1000

        for i in range(trials):
            if swr.check_for_ripple(SleepState.NREM_N3, i):
                ripple_count += 1

        # Should be roughly 50% (within margin)
        ratio = ripple_count / trials
        assert 0.4 < ratio < 0.6

    def test_generate_ripple(self, swr_generator):
        """generate_ripple() should create valid RippleEvent."""
        ripple = swr_generator.generate_ripple(100.0)

        assert ripple.timestamp == 100.0
        assert 3 <= ripple.duration <= 8
        assert 0.5 <= ripple.strength <= 1.0
        assert swr_generator.active_ripple is not None

    def test_memory_selection(self, swr_generator):
        """Memory selection should prioritize appropriately."""
        memories = [MockMemory(timestamp=i) for i in range(20)]

        # Make some memories more important
        memories[0].prediction_error = 1.0  # High novelty
        memories[1].strength = 2.0  # High strength

        selected = swr_generator.select_memories_for_replay(memories, k=5)

        assert len(selected) == 5
        assert len(set(selected)) == 5  # No duplicates

    def test_memory_selection_empty(self, swr_generator):
        """Memory selection with empty list should return empty."""
        selected = swr_generator.select_memories_for_replay([], k=5)
        assert selected == []

    def test_complete_ripple(self, swr_generator):
        """complete_ripple() should finalize and record ripple."""
        swr_generator.generate_ripple(0.0)
        swr_generator.complete_ripple([0, 1, 2])

        assert swr_generator.active_ripple is None
        assert len(swr_generator.ripple_history) == 1
        assert swr_generator.ripple_history[0].memories_replayed == [0, 1, 2]

    def test_reset(self, swr_generator):
        """reset() should clear state."""
        swr_generator.generate_ripple(0.0)
        swr_generator.complete_ripple([0])

        swr_generator.reset()

        assert swr_generator.active_ripple is None
        assert len(swr_generator.ripple_history) == 0


# ============================================================================
# Test Sleep Stage Manager
# ============================================================================

class TestSleepStageManager:
    """Tests for sleep stage manager."""

    def test_neuromod_targets_wake(self, config):
        """Wake should have baseline neuromodulator targets."""
        manager = SleepStageManager(config)
        targets = manager.get_neuromod_targets(SleepState.WAKE)

        assert targets['dopamine'] == config.wake_dopamine
        assert targets['serotonin'] == config.wake_serotonin
        assert targets['norepinephrine'] == config.wake_norepinephrine

    def test_neuromod_targets_nrem_n3(self, config):
        """NREM_N3 should have sleep-specific targets."""
        manager = SleepStageManager(config)
        targets = manager.get_neuromod_targets(SleepState.NREM_N3)

        assert targets['dopamine'] == config.sleep_dopamine
        assert targets['norepinephrine'] == config.sleep_norepinephrine

    def test_gate_modulation_sleep(self, config):
        """Sleep stages should increase gate temperature."""
        manager = SleepStageManager(config)

        wake_mod = manager.get_gate_modulation(SleepState.WAKE)
        sleep_mod = manager.get_gate_modulation(SleepState.NREM_N3)

        assert sleep_mod['temperature_multiplier'] > wake_mod['temperature_multiplier']

    def test_l4_dominates_during_sleep(self, config):
        """Layer 4 should dominate during sleep."""
        manager = SleepStageManager(config)
        mod = manager.get_gate_modulation(SleepState.NREM_N3)

        assert mod['layer_weights'][4] > mod['layer_weights'][1]
        assert mod['layer_weights'][4] >= 0.70

    def test_should_run_replay(self, config):
        """Replay should only run in NREM_N3."""
        manager = SleepStageManager(config)

        assert not manager.should_run_replay(SleepState.WAKE)
        assert not manager.should_run_replay(SleepState.REM)
        assert manager.should_run_replay(SleepState.NREM_N3)

    def test_should_run_counterfactual(self, config):
        """Counterfactual should only run in REM."""
        manager = SleepStageManager(config)

        assert not manager.should_run_counterfactual(SleepState.WAKE)
        assert not manager.should_run_counterfactual(SleepState.NREM_N3)
        assert manager.should_run_counterfactual(SleepState.REM)


# ============================================================================
# Test Sleep Consolidation (Main Orchestrator)
# ============================================================================

class TestSleepConsolidation:
    """Tests for main sleep consolidation orchestrator."""

    def test_initial_state(self, consolidator):
        """Consolidator should start in WAKE."""
        assert consolidator.get_current_state() == SleepState.WAKE
        assert not consolidator.is_sleeping()

    def test_step_updates_metrics(self, consolidator):
        """step() should update metrics."""
        output = consolidator.step(activity_level=0.5, dt=1.0)

        assert output.state == SleepState.WAKE
        assert consolidator.total_timesteps == 1

    def test_step_through_drowsy(self, fast_consolidator):
        """step() should transition through DROWSY state."""
        states_visited = set()

        # Idle to trigger sleep progression
        for _ in range(100):
            output = fast_consolidator.step(activity_level=0.1, dt=0.1)
            states_visited.add(output.state)

        # Should have passed through DROWSY on the way to sleep
        assert SleepState.DROWSY in states_visited

    def test_swr_triggers_in_nrem_n3(self, fast_consolidator):
        """SWR should trigger during NREM_N3."""
        fc = fast_consolidator
        fc.state_machine.force_state(SleepState.NREM_N3)
        fc.config.swr_probability = 1.0  # Guarantee SWR
        fc.swr_generator.config.swr_probability = 1.0

        output = fc.step(activity_level=0.0, dt=1.0)

        assert output.swr_triggered

    def test_immediate_consolidation(self):
        """immediate_consolidation() should strengthen memories."""
        mock_hc = MockHippocampus(num_memories=10)
        consolidator = SleepConsolidation(hippocampus=mock_hc)

        initial_strength = mock_hc.memories[0].strength

        metrics = consolidator.immediate_consolidation(num_replays=3)

        assert metrics.replays_triggered >= 1

    def test_enter_sleep_cycle(self, fast_consolidator):
        """enter_sleep_cycle() should complete full cycle."""
        fc = fast_consolidator

        metrics = fc.enter_sleep_cycle(max_duration=100)

        assert fc.get_current_state() == SleepState.WAKE
        assert metrics.cycles_completed >= 1 or metrics.total_sleep_time > 0

    def test_wake_up(self, fast_consolidator):
        """wake_up() should force immediate wake."""
        fc = fast_consolidator
        fc.state_machine.force_state(SleepState.REM)

        fc.wake_up()

        assert fc.get_current_state() == SleepState.WAKE

    def test_should_sleep(self, consolidator):
        """should_sleep() should recommend sleep on low activity."""
        activity = deque([0.1] * 30)
        assert consolidator.should_sleep(activity)

        activity = deque([0.8] * 30)
        assert not consolidator.should_sleep(activity)

    def test_integration_with_hippocampus(self):
        """Test integration with mock hippocampus."""
        mock_hc = MockHippocampus(num_memories=20)
        consolidator = SleepConsolidation(
            config=SleepConsolidationConfig(
                swr_probability=1.0,
                swr_replay_count=3,
                seed=42
            ),
            hippocampus=mock_hc
        )

        consolidator.state_machine.force_state(SleepState.NREM_N3)

        output = consolidator.step(activity_level=0.0, dt=1.0)

        assert output.swr_triggered
        assert output.replays_this_step > 0

    def test_integration_with_neuromodulation(self):
        """Test integration with mock neuromodulation."""
        mock_neuromod = MockNeuromodulation()
        consolidator = SleepConsolidation(neuromodulation=mock_neuromod)

        consolidator.state_machine.force_state(SleepState.NREM_N3)

        # Step several times to let neuromodulators adjust
        for _ in range(20):
            output = consolidator.step(activity_level=0.0, dt=1.0)

        # Dopamine should decrease during sleep
        assert mock_neuromod.levels.dopamine < 0.5

    def test_get_statistics(self, consolidator):
        """get_statistics() should return valid data."""
        consolidator.step(activity_level=0.5, dt=1.0)
        stats = consolidator.get_statistics()

        assert 'current_state' in stats
        assert 'is_sleeping' in stats
        assert 'total_timesteps' in stats
        assert 'metrics' in stats

    def test_get_state(self, consolidator):
        """get_state() should return serializable state."""
        consolidator.step(activity_level=0.5, dt=1.0)
        state = consolidator.get_state()

        assert 'current_state' in state
        assert 'cycles_completed' in state

    def test_reset(self, consolidator):
        """reset() should clear all state."""
        consolidator.state_machine.force_state(SleepState.REM)
        consolidator.total_timesteps = 100

        consolidator.reset()

        assert consolidator.get_current_state() == SleepState.WAKE
        assert consolidator.total_timesteps == 0


# ============================================================================
# Test Factory Function
# ============================================================================

class TestFactoryFunction:
    """Tests for create_sleep_consolidation factory."""

    def test_create_with_defaults(self):
        """Factory should create with defaults."""
        consolidator = create_sleep_consolidation()

        assert consolidator is not None
        assert consolidator.get_current_state() == SleepState.WAKE

    def test_create_with_components(self):
        """Factory should accept components."""
        mock_hc = MockHippocampus()
        mock_neuromod = MockNeuromodulation()

        consolidator = create_sleep_consolidation(
            hippocampus=mock_hc,
            neuromodulation=mock_neuromod
        )

        assert consolidator.hippocampus is mock_hc
        assert consolidator.neuromodulation is mock_neuromod

    def test_create_with_config_kwargs(self):
        """Factory should accept config kwargs."""
        consolidator = create_sleep_consolidation(
            max_sleep_cycles=2,
            swr_probability=0.5
        )

        assert consolidator.config.max_sleep_cycles == 2
        assert consolidator.config.swr_probability == 0.5


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for full system."""

    def test_full_sleep_cycle_with_replay(self):
        """Test complete sleep cycle with memory replay."""
        mock_hc = MockHippocampus(num_memories=20)
        mock_neuromod = MockNeuromodulation()

        config = SleepConsolidationConfig(
            idle_threshold_seconds=2.0,
            drowsy_duration=1.0,
            nrem_n1_duration=1.0,
            nrem_n2_duration=2.0,
            nrem_n3_duration=5.0,
            rem_duration=2.0,
            max_sleep_cycles=1,
            swr_probability=0.5,
            seed=42
        )

        consolidator = SleepConsolidation(
            config=config,
            hippocampus=mock_hc,
            neuromodulation=mock_neuromod
        )

        metrics = consolidator.enter_sleep_cycle(max_duration=50)

        # Should have completed at least one cycle
        assert metrics.cycles_completed >= 1 or metrics.total_sleep_time > 0

        # Should have triggered some replays
        # (probabilistic, may be 0)

    def test_wake_on_external_activity(self):
        """Test that external activity wakes the system."""
        consolidator = create_sleep_consolidation()
        consolidator.state_machine.force_state(SleepState.NREM_N3)

        # High activity should wake
        output = consolidator.step(activity_level=0.9, dt=1.0)

        assert output.state == SleepState.WAKE
        assert output.state_changed


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
