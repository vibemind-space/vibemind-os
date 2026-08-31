"""
Unit tests for the Dream Mode / Sleep Consolidation system.

Test coverage:
- SleepConsolidation initialization (default & custom config)
- SleepStateMachine transitions (WAKE->DROWSY->NREM_N1->...->REM->WAKE)
- SynapticHomeostasis (NREM and REM weight scaling, selective preservation)
- SharpWaveRippleGenerator (ripple generation, memory selection)
- Immediate consolidation (memory replay without full sleep)
- step() method with different activity levels
- enter_sleep_cycle() / wake_up()
- Statistics collection (get_statistics())
- Consolidation importance threshold
- Integration with NeuromodulationSystem (mock)
- Edge cases (multiple rapid transitions, zero activity, empty memories)
"""

import pytest
import numpy as np
import sys
import os
from unittest.mock import MagicMock, patch
from collections import deque
from dataclasses import dataclass

# Add parent directory to path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from core.sleep_consolidation import (
    SleepConsolidation,
    SleepConsolidationConfig,
    SleepState,
    SleepStateMachine,
    SynapticHomeostasis,
    SharpWaveRippleGenerator,
    SleepStageManager,
    ConsolidationMetrics,
    SleepConsolidationOutput,
    RippleEvent,
    create_sleep_consolidation,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def config():
    """Default SleepConsolidationConfig."""
    return SleepConsolidationConfig(seed=42)


@pytest.fixture
def fast_config():
    """Config with short durations for faster test cycles."""
    return SleepConsolidationConfig(
        seed=42,
        idle_threshold_seconds=5.0,
        drowsy_duration=2.0,
        nrem_n1_duration=3.0,
        nrem_n2_duration=4.0,
        nrem_n3_duration=5.0,
        rem_duration=4.0,
        max_sleep_cycles=2,
    )


@pytest.fixture
def state_machine(config):
    """Pre-built SleepStateMachine."""
    return SleepStateMachine(config)


@pytest.fixture
def fast_state_machine(fast_config):
    """State machine with short durations."""
    return SleepStateMachine(fast_config)


@pytest.fixture
def homeostasis(config):
    """Pre-built SynapticHomeostasis."""
    return SynapticHomeostasis(config)


@pytest.fixture
def swr_generator(config):
    """Pre-built SharpWaveRippleGenerator."""
    return SharpWaveRippleGenerator(config)


@pytest.fixture
def consolidator(config):
    """SleepConsolidation with no external dependencies."""
    return SleepConsolidation(config=config)


@pytest.fixture
def fast_consolidator(fast_config):
    """SleepConsolidation with fast durations, no external deps."""
    return SleepConsolidation(config=fast_config)


def _make_mock_memory(timestamp=0, prediction_error=0.5, strength=1.0):
    """Create a mock EpisodicMemory object with the fields SWR needs."""
    mem = MagicMock()
    mem.timestamp = timestamp
    mem.prediction_error = prediction_error
    mem.strength = strength
    mem.retrieval_count = 0
    mem.state = np.random.randn(16)
    mem.context = np.random.randn(6)
    return mem


def _make_mock_hippocampus(n_memories=10):
    """Create a mock Hippocampus with n episodic memories."""
    hipp = MagicMock()
    hipp.memories = [
        _make_mock_memory(timestamp=i, prediction_error=0.1 * i, strength=0.5 + 0.05 * i)
        for i in range(n_memories)
    ]
    return hipp


def _make_mock_neuromod():
    """Create a mock NeuromodulationSystem with mutable levels."""
    neuromod = MagicMock()
    levels = MagicMock()
    levels.dopamine = 0.5
    levels.serotonin = 0.5
    levels.norepinephrine = 0.5
    neuromod.levels = levels
    return neuromod


# ============================================================================
# 1. Initialization Tests
# ============================================================================

class TestSleepConsolidationInit:
    """Test SleepConsolidation initialization."""

    def test_default_initialization(self):
        """SleepConsolidation should initialize with default config."""
        sc = SleepConsolidation()
        assert sc.config is not None
        assert sc.state_machine.current_state == SleepState.WAKE
        assert sc.total_timesteps == 0
        assert sc.is_consolidating is False

    def test_custom_config(self):
        """SleepConsolidation should respect custom config values."""
        cfg = SleepConsolidationConfig(
            idle_threshold_seconds=120.0,
            max_sleep_cycles=8,
            nrem_scaling_rate=0.90,
            seed=99,
        )
        sc = SleepConsolidation(config=cfg)
        assert sc.config.idle_threshold_seconds == 120.0
        assert sc.config.max_sleep_cycles == 8
        assert sc.config.nrem_scaling_rate == 0.90
        assert sc.config.seed == 99

    def test_metrics_initialized(self):
        """Metrics should be zero-initialized on creation."""
        sc = SleepConsolidation()
        assert sc.metrics.total_sleep_time == 0.0
        assert sc.metrics.cycles_completed == 0
        assert sc.metrics.replays_triggered == 0
        assert len(sc.metrics.swr_events) == 0
        # time_per_stage should have an entry for every SleepState
        for state in SleepState:
            assert state in sc.metrics.time_per_stage

    def test_factory_function(self):
        """create_sleep_consolidation factory should work."""
        sc = create_sleep_consolidation(seed=77, idle_threshold_seconds=30.0)
        assert sc.config.seed == 77
        assert sc.config.idle_threshold_seconds == 30.0
        assert sc.state_machine.current_state == SleepState.WAKE


# ============================================================================
# 2. Sleep State Machine Transitions
# ============================================================================

class TestSleepStateMachine:
    """Test state machine transitions through the full sleep cycle."""

    def test_starts_in_wake(self, state_machine):
        """State machine should start in WAKE."""
        assert state_machine.current_state == SleepState.WAKE

    def test_wake_to_drowsy_on_idle(self, state_machine):
        """After idle_threshold_seconds of low activity, should transition to DROWSY."""
        cfg = state_machine.config
        # Step with low activity until idle threshold is passed
        total = 0.0
        dt = 1.0
        while total <= cfg.idle_threshold_seconds + 1:
            state, changed = state_machine.step(activity_level=0.1, dt=dt)
            total += dt
        assert state == SleepState.DROWSY

    def test_full_cycle_progression(self, fast_state_machine):
        """Walk through WAKE->DROWSY->N1->N2->N3->REM in order."""
        sm = fast_state_machine
        expected_sequence = [
            SleepState.WAKE,
            SleepState.DROWSY,
            SleepState.NREM_N1,
            SleepState.NREM_N2,
            SleepState.NREM_N3,
            SleepState.REM,
        ]

        visited = [SleepState.WAKE]
        for _ in range(500):
            state, changed = sm.step(activity_level=0.0, dt=1.0)
            if changed and state not in visited:
                visited.append(state)
            if state == SleepState.REM:
                break

        assert visited == expected_sequence, (
            f"Expected progression {[s.value for s in expected_sequence]}, "
            f"got {[s.value for s in visited]}"
        )

    def test_rem_cycles_back_to_nrem2(self, fast_state_machine):
        """After REM completes (before max cycles), should cycle back to NREM_N2."""
        sm = fast_state_machine
        # Drive through to REM
        for _ in range(200):
            state, _ = sm.step(activity_level=0.0, dt=1.0)
            if state == SleepState.REM:
                break

        assert state == SleepState.REM
        # Now step until REM ends
        for _ in range(200):
            state, changed = sm.step(activity_level=0.0, dt=1.0)
            if changed and state != SleepState.REM:
                break

        # Should be NREM_N2 (cycle back) or WAKE (if max cycles hit)
        assert state in [SleepState.NREM_N2, SleepState.WAKE]

    def test_max_cycles_return_to_wake(self, fast_state_machine):
        """After max_sleep_cycles REM cycles, should return to WAKE."""
        sm = fast_state_machine
        max_cycles = sm.config.max_sleep_cycles
        for _ in range(5000):
            state, _ = sm.step(activity_level=0.0, dt=1.0)
            if state == SleepState.WAKE and sm.state_duration == 0.0 and len(sm.state_history) > 0:
                # Woke up after being asleep
                break

        # We should have completed the expected number of cycles
        # The cycles_completed resets to 0 on WAKE, so check history
        assert state == SleepState.WAKE

    def test_high_activity_forces_wake(self, fast_state_machine):
        """High activity during sleep should force WAKE."""
        sm = fast_state_machine
        # Enter sleep
        for _ in range(100):
            sm.step(activity_level=0.0, dt=1.0)
        # Should be in some sleep state by now
        assert sm.current_state != SleepState.WAKE

        # Force wake with high activity
        state, changed = sm.step(activity_level=0.8, dt=1.0)
        assert state == SleepState.WAKE
        assert changed is True

    def test_force_state(self, state_machine):
        """force_state() should immediately transition."""
        state_machine.force_state(SleepState.NREM_N3)
        assert state_machine.current_state == SleepState.NREM_N3
        assert state_machine.state_duration == 0.0

    def test_force_wake_resets_cycles(self, state_machine):
        """force_wake() should reset cycles_completed and idle_time."""
        state_machine.cycles_completed = 3
        state_machine.idle_time = 50.0
        state_machine.force_wake()
        assert state_machine.current_state == SleepState.WAKE
        assert state_machine.cycles_completed == 0
        assert state_machine.idle_time == 0.0

    def test_is_sleeping(self, state_machine):
        """is_sleeping should return False for WAKE/DROWSY, True for NREM/REM."""
        state_machine.force_state(SleepState.WAKE)
        assert state_machine.is_sleeping() is False

        state_machine.force_state(SleepState.DROWSY)
        assert state_machine.is_sleeping() is False

        state_machine.force_state(SleepState.NREM_N1)
        assert state_machine.is_sleeping() is True

        state_machine.force_state(SleepState.NREM_N3)
        assert state_machine.is_sleeping() is True

        state_machine.force_state(SleepState.REM)
        assert state_machine.is_sleeping() is True

    def test_reset(self, state_machine):
        """reset() should return to clean WAKE state."""
        state_machine.force_state(SleepState.NREM_N3)
        state_machine.cycles_completed = 2
        state_machine.idle_time = 100.0

        state_machine.reset()
        assert state_machine.current_state == SleepState.WAKE
        assert state_machine.state_duration == 0.0
        assert state_machine.idle_time == 0.0
        assert state_machine.cycles_completed == 0


# ============================================================================
# 3. Synaptic Homeostasis
# ============================================================================

class TestSynapticHomeostasis:
    """Test synaptic homeostasis weight scaling."""

    def test_nrem_scaling_reduces_weights(self, homeostasis):
        """NREM scaling should reduce overall weight magnitude."""
        np.random.seed(42)
        weights = {'layer1': np.random.rand(4, 4) * 2.0}
        original_norm = np.linalg.norm(weights['layer1'], 'fro')

        scaled = homeostasis.apply_homeostasis(weights, SleepState.NREM_N3)

        # The output is renormalized to target_weight_norm=1.0, so
        # total_scaling_applied should have been multiplied by nrem_scaling_rate
        assert homeostasis.total_scaling_applied == pytest.approx(
            homeostasis.config.nrem_scaling_rate, abs=1e-6
        )
        assert 'layer1' in scaled

    def test_rem_scaling_is_milder(self, homeostasis):
        """REM scaling should be milder than NREM."""
        np.random.seed(42)
        weights = {'layer1': np.random.rand(4, 4)}

        homeostasis.apply_homeostasis(weights, SleepState.REM)
        rem_ratio = homeostasis.get_scaling_ratio()

        homeostasis.reset()
        homeostasis.apply_homeostasis(weights, SleepState.NREM_N3)
        nrem_ratio = homeostasis.get_scaling_ratio()

        # REM scaling (0.98) should be closer to 1.0 than NREM (0.95)
        assert rem_ratio > nrem_ratio

    def test_wake_no_scaling(self, homeostasis):
        """WAKE stage should not apply any scaling."""
        np.random.seed(42)
        weights = {'layer1': np.random.rand(4, 4)}
        original = weights['layer1'].copy()

        result = homeostasis.apply_homeostasis(weights, SleepState.WAKE)
        # Should be the same dict (no modification)
        assert np.array_equal(result['layer1'], original)
        assert homeostasis.get_scaling_ratio() == 1.0

    def test_selective_preservation(self, homeostasis):
        """Strongly activated synapses should be selectively preserved."""
        np.random.seed(42)
        weights = {'test': np.ones((4, 4))}

        # Record high activation for some synapses
        activation = np.zeros((4, 4))
        activation[0, 0] = 10.0  # Very high activation for one synapse
        # Record many times to build up EMA
        for _ in range(50):
            homeostasis.record_activation('test', activation)

        scaled = homeostasis.apply_homeostasis(weights, SleepState.NREM_N3)
        # The result is renormalized, but the relative pattern should show
        # the highly-activated synapse has a relatively higher weight
        w = scaled['test']
        # The [0,0] element should be relatively stronger than others
        assert w[0, 0] > w[1, 1], (
            f"Strongly activated synapse {w[0,0]} should be > weakly activated {w[1,1]}"
        )

    def test_weight_clipping(self, homeostasis):
        """Weights should stay within [min_weight, max_weight]."""
        weights = {'test': np.array([[100.0]])}
        scaled = homeostasis.apply_homeostasis(weights, SleepState.NREM_N3)
        assert np.all(scaled['test'] >= homeostasis.config.min_weight)
        assert np.all(scaled['test'] <= homeostasis.config.max_weight)

    def test_reset_clears_state(self, homeostasis):
        """reset() should clear activation history and scaling tracker."""
        homeostasis.record_activation('test', np.ones(5))
        weights = {'test': np.ones((5, 5))}
        homeostasis.apply_homeostasis(weights, SleepState.NREM_N3)

        assert homeostasis.get_scaling_ratio() != 1.0
        assert len(homeostasis.activation_history) > 0

        homeostasis.reset()
        assert homeostasis.get_scaling_ratio() == 1.0
        assert len(homeostasis.activation_history) == 0


# ============================================================================
# 4. Sharp-Wave Ripple Generator
# ============================================================================

class TestSharpWaveRippleGenerator:
    """Test SWR generation and memory selection."""

    def test_ripple_only_in_nrem3(self, swr_generator):
        """Ripples should only fire during NREM_N3."""
        # Run many checks in non-NREM_N3 states - should never trigger
        for stage in [SleepState.WAKE, SleepState.DROWSY, SleepState.NREM_N1,
                      SleepState.NREM_N2, SleepState.REM]:
            for t in range(100):
                assert swr_generator.check_for_ripple(stage, t) is False

    def test_ripple_can_fire_in_nrem3(self, swr_generator):
        """Ripples should eventually fire during NREM_N3 given swr_probability > 0."""
        fired = False
        for t in range(1000):
            if swr_generator.check_for_ripple(SleepState.NREM_N3, t):
                fired = True
                break
        assert fired, "Expected at least one ripple in 1000 NREM_N3 timesteps"

    def test_generate_ripple_creates_event(self, swr_generator):
        """generate_ripple should produce a valid RippleEvent."""
        ripple = swr_generator.generate_ripple(timestamp=42.0)
        assert isinstance(ripple, RippleEvent)
        assert ripple.timestamp == 42.0
        assert 3 <= ripple.duration <= 7  # rng.integers(3, 8) is [3, 7]
        assert 0.5 <= ripple.strength <= 1.0
        assert ripple.memories_replayed == []
        assert swr_generator.active_ripple is ripple

    def test_complete_ripple_stores_in_history(self, swr_generator):
        """complete_ripple should move active ripple to history."""
        ripple = swr_generator.generate_ripple(timestamp=1.0)
        swr_generator.complete_ripple([0, 1, 2])

        assert swr_generator.active_ripple is None
        assert swr_generator.get_ripple_count() == 1
        assert swr_generator.ripple_history[0].memories_replayed == [0, 1, 2]

    def test_select_memories_empty_list(self, swr_generator):
        """select_memories_for_replay should return empty for empty memory list."""
        result = swr_generator.select_memories_for_replay([], k=5)
        assert result == []

    def test_select_memories_respects_k(self, swr_generator):
        """Should return at most k memory indices."""
        memories = [_make_mock_memory(timestamp=i) for i in range(20)]
        selected = swr_generator.select_memories_for_replay(memories, k=5)
        assert len(selected) == 5
        # Indices should be valid
        for idx in selected:
            assert 0 <= idx < 20

    def test_select_memories_clamps_to_available(self, swr_generator):
        """If k > len(memories), should return len(memories) indices."""
        memories = [_make_mock_memory(timestamp=i) for i in range(3)]
        selected = swr_generator.select_memories_for_replay(memories, k=10)
        assert len(selected) == 3

    def test_reset_clears_state(self, swr_generator):
        """reset() should clear ripple history and active ripple."""
        swr_generator.generate_ripple(1.0)
        swr_generator.complete_ripple([0])
        swr_generator.generate_ripple(2.0)

        swr_generator.reset()
        assert swr_generator.active_ripple is None
        assert swr_generator.get_ripple_count() == 0
        assert swr_generator.timestep == 0


# ============================================================================
# 5. Immediate Consolidation
# ============================================================================

class TestImmediateConsolidation:
    """Test immediate_consolidation (quick replay without full sleep)."""

    def test_no_hippocampus_returns_metrics(self, consolidator):
        """Without hippocampus, should return metrics unchanged."""
        result = consolidator.immediate_consolidation(num_replays=5)
        assert isinstance(result, ConsolidationMetrics)
        assert result.replays_triggered == 0

    def test_with_hippocampus_replays_memories(self, fast_config):
        """With hippocampus, should replay and strengthen memories."""
        hipp = _make_mock_hippocampus(n_memories=10)
        sc = SleepConsolidation(config=fast_config, hippocampus=hipp)

        result = sc.immediate_consolidation(num_replays=3)
        assert result.replays_triggered == 3

    def test_memory_strength_increases(self, fast_config):
        """Replayed memories should have increased strength."""
        hipp = _make_mock_hippocampus(n_memories=5)
        # Set low initial strength
        for mem in hipp.memories:
            mem.strength = 0.5
        original_strengths = [mem.strength for mem in hipp.memories]

        sc = SleepConsolidation(config=fast_config, hippocampus=hipp)
        sc.immediate_consolidation(num_replays=5)

        # At least some memories should be stronger
        strengthened = sum(
            1 for mem in hipp.memories if mem.strength > 0.5
        )
        assert strengthened > 0, "At least one memory should have been strengthened"

    def test_strength_capped_at_one(self, fast_config):
        """Memory strength should not exceed 1.0."""
        hipp = _make_mock_hippocampus(n_memories=3)
        for mem in hipp.memories:
            mem.strength = 0.95

        sc = SleepConsolidation(config=fast_config, hippocampus=hipp)
        sc.immediate_consolidation(num_replays=3)

        for mem in hipp.memories:
            assert mem.strength <= 1.0


# ============================================================================
# 6. step() Method
# ============================================================================

class TestStepMethod:
    """Test the main step() method."""

    def test_step_returns_output(self, consolidator):
        """step() should return a SleepConsolidationOutput."""
        output = consolidator.step(activity_level=0.5, dt=1.0)
        assert isinstance(output, SleepConsolidationOutput)
        assert isinstance(output.state, SleepState)
        assert isinstance(output.neuromod_targets, dict)
        assert isinstance(output.gate_modulation, dict)
        assert isinstance(output.metrics, ConsolidationMetrics)

    def test_step_increments_timestep(self, consolidator):
        """Each step should increment total_timesteps."""
        assert consolidator.total_timesteps == 0
        consolidator.step(activity_level=0.5, dt=1.0)
        assert consolidator.total_timesteps == 1
        consolidator.step(activity_level=0.5, dt=1.0)
        assert consolidator.total_timesteps == 2

    def test_step_tracks_time_per_stage(self, consolidator):
        """step should accumulate time_per_stage."""
        consolidator.step(activity_level=0.8, dt=5.0)
        # High activity keeps us in WAKE
        assert consolidator.metrics.time_per_stage[SleepState.WAKE] == pytest.approx(5.0)

    def test_step_high_activity_stays_wake(self, consolidator):
        """High activity should keep the system in WAKE."""
        for _ in range(100):
            output = consolidator.step(activity_level=0.8, dt=1.0)
        assert output.state == SleepState.WAKE

    def test_step_zero_activity_enters_sleep(self, fast_consolidator):
        """Zero activity for long enough should cause sleep transition."""
        last_output = None
        for _ in range(200):
            last_output = fast_consolidator.step(activity_level=0.0, dt=1.0)
        # Should have moved past WAKE
        assert last_output.state != SleepState.WAKE

    def test_step_sleep_time_only_during_sleep(self, fast_consolidator):
        """total_sleep_time should only accumulate during actual sleep stages."""
        # Active period
        for _ in range(3):
            fast_consolidator.step(activity_level=0.8, dt=1.0)
        assert fast_consolidator.metrics.total_sleep_time == 0.0

        # Now go idle until sleeping (past DROWSY)
        for _ in range(500):
            output = fast_consolidator.step(activity_level=0.0, dt=1.0)
            if fast_consolidator.state_machine.is_sleeping():
                break

        # Once sleeping, sleep time should accumulate
        sleep_before = fast_consolidator.metrics.total_sleep_time
        fast_consolidator.step(activity_level=0.0, dt=1.0)
        if fast_consolidator.state_machine.is_sleeping():
            assert fast_consolidator.metrics.total_sleep_time > sleep_before


# ============================================================================
# 7. enter_sleep_cycle() / wake_up()
# ============================================================================

class TestSleepCycleControl:
    """Test full sleep cycle entry and wake-up control."""

    def test_enter_sleep_cycle_completes(self, fast_consolidator):
        """enter_sleep_cycle should run through a full cycle and return metrics."""
        metrics = fast_consolidator.enter_sleep_cycle()
        assert isinstance(metrics, ConsolidationMetrics)
        assert metrics.total_sleep_time > 0

    def test_enter_sleep_cycle_returns_to_wake(self, fast_consolidator):
        """After enter_sleep_cycle, system should be in WAKE."""
        fast_consolidator.enter_sleep_cycle()
        assert fast_consolidator.get_current_state() == SleepState.WAKE
        assert fast_consolidator.is_consolidating is False

    def test_enter_sleep_cycle_max_duration(self, fast_consolidator):
        """max_duration should cap the cycle."""
        metrics = fast_consolidator.enter_sleep_cycle(max_duration=10.0)
        assert metrics.total_sleep_time <= 15.0  # Some slack for last step
        assert fast_consolidator.get_current_state() == SleepState.WAKE

    def test_wake_up_forces_wake(self, fast_consolidator):
        """wake_up() should force immediate return to WAKE."""
        # Start entering sleep
        fast_consolidator.state_machine.force_state(SleepState.NREM_N3)
        fast_consolidator.is_consolidating = True

        fast_consolidator.wake_up()
        assert fast_consolidator.get_current_state() == SleepState.WAKE
        assert fast_consolidator.is_consolidating is False


# ============================================================================
# 8. Statistics Collection
# ============================================================================

class TestStatistics:
    """Test get_statistics() and get_state()."""

    def test_get_statistics_structure(self, consolidator):
        """get_statistics should return complete dict structure."""
        stats = consolidator.get_statistics()
        assert 'current_state' in stats
        assert 'is_sleeping' in stats
        assert 'cycles_completed' in stats
        assert 'total_timesteps' in stats
        assert 'metrics' in stats
        assert 'weight_scaling_ratio' in stats
        assert 'swr_count' in stats

    def test_get_statistics_after_steps(self, fast_consolidator):
        """Statistics should reflect system activity."""
        for _ in range(10):
            fast_consolidator.step(activity_level=0.8, dt=1.0)

        stats = fast_consolidator.get_statistics()
        assert stats['total_timesteps'] == 10
        assert stats['current_state'] == 'wake'
        assert stats['is_sleeping'] is False
        assert stats['weight_scaling_ratio'] == 1.0

    def test_get_state_serializable(self, consolidator):
        """get_state should return a serializable dict."""
        state = consolidator.get_state()
        assert 'current_state' in state
        assert 'state_duration' in state
        assert 'cycles_completed' in state
        assert 'total_timesteps' in state
        assert 'weight_scaling' in state
        assert 'metrics' in state

    def test_metrics_to_dict(self, consolidator):
        """ConsolidationMetrics.to_dict() should produce clean output."""
        consolidator.step(activity_level=0.5, dt=1.0)
        d = consolidator.metrics.to_dict()
        assert isinstance(d, dict)
        assert 'total_sleep_time' in d
        assert 'time_per_stage' in d
        assert 'cycles_completed' in d
        assert 'num_swr_events' in d
        # time_per_stage keys should be string values of SleepState
        for key in d['time_per_stage']:
            assert isinstance(key, str)


# ============================================================================
# 9. Consolidation Importance Threshold
# ============================================================================

class TestConsolidationThreshold:
    """Test should_sleep and selective memory handling."""

    def test_should_sleep_low_activity(self, consolidator):
        """should_sleep returns True when recent activity is low."""
        history = deque([0.1] * 30)
        assert consolidator.should_sleep(history) == True

    def test_should_sleep_high_activity(self, consolidator):
        """should_sleep returns False when recent activity is high."""
        history = deque([0.8] * 30)
        assert consolidator.should_sleep(history) == False

    def test_should_sleep_insufficient_history(self, consolidator):
        """should_sleep returns False with too few samples."""
        history = deque([0.1] * 5)
        assert consolidator.should_sleep(history) == False

    def test_should_sleep_boundary(self, consolidator):
        """should_sleep boundary at avg activity 0.3."""
        # Exactly at threshold
        history = deque([0.3] * 30)
        # 0.3 is not < 0.3, so should be False
        assert consolidator.should_sleep(history) == False

        # Just below
        history = deque([0.29] * 30)
        assert consolidator.should_sleep(history) == True


# ============================================================================
# 10. Integration with NeuromodulationSystem
# ============================================================================

class TestNeuromodulationIntegration:
    """Test integration with (mocked) NeuromodulationSystem."""

    def test_neuromod_targets_applied_during_sleep(self, fast_config):
        """Neuromodulator levels should shift toward sleep targets."""
        neuromod = _make_mock_neuromod()
        sc = SleepConsolidation(config=fast_config, neuromodulation=neuromod)

        initial_dopamine = neuromod.levels.dopamine
        # Force into deep sleep where targets differ from wake
        sc.state_machine.force_state(SleepState.NREM_N3)
        sc.step(activity_level=0.0, dt=1.0)

        # Dopamine target for NREM_N3 is 0.2 (config.sleep_dopamine)
        # Should have moved toward 0.2 from 0.5
        assert neuromod.levels.dopamine < initial_dopamine

    def test_neuromod_not_called_when_none(self, consolidator):
        """Without neuromodulation system, step should not crash."""
        assert consolidator.neuromodulation is None
        # Should not raise
        output = consolidator.step(activity_level=0.5, dt=1.0)
        assert output is not None

    def test_stage_manager_neuromod_targets(self):
        """SleepStageManager should return correct neuromod targets per stage."""
        manager = SleepStageManager(SleepConsolidationConfig())

        wake_targets = manager.get_neuromod_targets(SleepState.WAKE)
        assert wake_targets['dopamine'] == 0.5
        assert wake_targets['serotonin'] == 0.5

        nrem3_targets = manager.get_neuromod_targets(SleepState.NREM_N3)
        assert nrem3_targets['dopamine'] == 0.2  # sleep_dopamine default
        assert nrem3_targets['serotonin'] == 0.7  # sleep_serotonin default

        rem_targets = manager.get_neuromod_targets(SleepState.REM)
        assert rem_targets['norepinephrine'] == 0.1


# ============================================================================
# 11. Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_multiple_rapid_transitions(self, state_machine):
        """Rapid force_state transitions should maintain consistent state."""
        for target in [SleepState.DROWSY, SleepState.NREM_N1, SleepState.REM, SleepState.WAKE]:
            state_machine.force_state(target)
            assert state_machine.current_state == target
            assert state_machine.state_duration == 0.0
        # History should track all transitions
        assert len(state_machine.state_history) == 4

    def test_zero_dt_step(self, consolidator):
        """step with dt=0 should not crash or change state durations."""
        output = consolidator.step(activity_level=0.5, dt=0.0)
        assert output is not None
        assert consolidator.total_timesteps == 1

    def test_very_large_dt(self, fast_consolidator):
        """Large dt should cause immediate stage transition."""
        # Force DROWSY, then a huge dt should push past duration
        fast_consolidator.state_machine.force_state(SleepState.DROWSY)
        output = fast_consolidator.step(activity_level=0.0, dt=1000.0)
        # Should have transitioned past DROWSY
        assert output.state != SleepState.DROWSY

    def test_empty_hippocampus_swr_replay(self, fast_config):
        """SWR replay with empty hippocampus should not crash."""
        hipp = MagicMock()
        hipp.memories = []
        sc = SleepConsolidation(config=fast_config, hippocampus=hipp)

        sc.state_machine.force_state(SleepState.NREM_N3)
        # Run several steps; SWR may fire but replay should handle empty memories
        for _ in range(100):
            output = sc.step(activity_level=0.0, dt=1.0)
        # Should not crash; replays should be 0
        assert output is not None

    def test_reset_returns_to_clean_state(self, fast_consolidator):
        """reset() should fully reinitialize."""
        # Run some steps
        for _ in range(50):
            fast_consolidator.step(activity_level=0.0, dt=1.0)

        fast_consolidator.reset()
        assert fast_consolidator.get_current_state() == SleepState.WAKE
        assert fast_consolidator.total_timesteps == 0
        assert fast_consolidator.is_consolidating is False
        assert fast_consolidator.metrics.total_sleep_time == 0.0
        assert fast_consolidator.metrics.replays_triggered == 0
        assert fast_consolidator.synaptic_homeostasis.get_scaling_ratio() == 1.0
        assert fast_consolidator.swr_generator.get_ripple_count() == 0

    def test_gate_modulation_during_sleep(self):
        """Gate modulation should shift layer weights during deep sleep."""
        manager = SleepStageManager(SleepConsolidationConfig())

        deep_mod = manager.get_gate_modulation(SleepState.NREM_N3)
        wake_mod = manager.get_gate_modulation(SleepState.WAKE)

        # During deep sleep, L4 should dominate (0.70 vs 0.35)
        assert deep_mod['layer_weights'][4] > wake_mod['layer_weights'][4]
        # During deep sleep, temperature multiplier should be higher
        assert deep_mod['temperature_multiplier'] > wake_mod['temperature_multiplier']

    def test_state_history_bounded(self, state_machine):
        """State history should not grow unbounded."""
        for _ in range(200):
            state_machine.force_state(SleepState.NREM_N1)
            state_machine.force_state(SleepState.WAKE)
        assert len(state_machine.state_history) <= state_machine.max_history

    def test_determinism_with_same_seed(self):
        """Two systems with same seed should produce identical SWR patterns."""
        gen1 = SharpWaveRippleGenerator(SleepConsolidationConfig(seed=42))
        gen2 = SharpWaveRippleGenerator(SleepConsolidationConfig(seed=42))

        results1 = [gen1.check_for_ripple(SleepState.NREM_N3, t) for t in range(100)]
        results2 = [gen2.check_for_ripple(SleepState.NREM_N3, t) for t in range(100)]

        assert results1 == results2, "Same seed should produce identical ripple patterns"


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
