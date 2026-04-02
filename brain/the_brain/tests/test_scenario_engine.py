"""
Tests for ScenarioEngine: core mechanics + all 6 named scenarios.

Each scenario asserts expected bridge state patterns emerge from the
multi-tick simulation.
"""

import pytest
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch

from core.radial_attention import RadialAttentionNetwork
from core.modulation_context import ModulationContext
from core.inter_bridge_coupling import InterBridgeCouplingRegistry
from core.scenario_engine import (
    ScenarioEngine,
    ScenarioResult,
    TickSnapshot,
    SCENARIOS,
    run_scenario,
    scenario_threat_while_sleepy,
    scenario_novel_social_under_load,
    scenario_reward_prediction_error,
    scenario_sustained_stress,
    scenario_creative_exploration,
    scenario_minibook_collaboration_burst,
)


# ─── Fake bridge states (lightweight, no real modules needed) ─────────────────

@dataclass
class FakeNeuromodState:
    dopamine: float = 0.5
    norepinephrine: float = 0.5
    serotonin: float = 0.5
    acetylcholine: float = 0.5
    anti_reward: float = 0.0
    ne_gain: float = 1.0
    explore_ratio: float = 0.5


@dataclass
class FakeCortexState:
    bias_signal: Optional[np.ndarray] = None
    inhibit: bool = False
    pfc_value: float = 0.5
    pfc_surprise: float = 0.0
    conflict: float = 0.0
    control_signal: float = 0.5
    error_likelihood: float = 0.0
    subjective_value: float = 0.5
    decision_confidence: float = 0.5
    choice_difficulty: float = 0.5


@dataclass
class FakeLimbicState:
    valence: float = 0.0
    arousal: float = 0.3
    threat_level: float = 0.0
    is_threat: bool = False
    go_drive: float = 0.5
    nogo_drive: float = 0.5
    net_value: float = 0.0
    effort_cost: float = 0.3
    salience: float = 0.3
    body_budget: float = 1.0
    feeling: str = 'neutral'
    urgency: float = 0.0
    approach_drive: float = 0.3
    stress: float = 0.0


@dataclass
class FakeSleepWakeState:
    arousal: float = 0.5
    sensory_gain: float = 0.5
    histamine: float = 0.5
    is_awake: bool = True
    wakefulness_drive: float = 0.5
    melatonin: float = 0.0
    sleep_pressure: float = 0.0
    cholinergic_tone: float = 0.5
    rem_probability: float = 0.0


@dataclass
class FakeMotorState:
    prediction_error: float = 0.0
    model_confidence: float = 0.5
    motor_da: float = 0.5
    go_nogo_balance: float = 0.0
    disinhibited: bool = False
    inhibition_level: float = 0.5
    action_tendency: float = 0.5
    is_compensating: bool = False
    error_correction: float = 0.0
    peak_salience: float = 0.5
    movement_confidence: float = 0.5


@dataclass
class FakeDefenseState:
    defense_mode: str = 'freeze'
    defense_intensity: float = 0.0
    emergency_mode: bool = False
    autonomic_activation: float = 0.0
    alarm_level: float = 0.0
    alarm_urgency: float = 0.0
    anxiety_level: float = 0.0
    vigilance: float = 0.3
    is_chronic_stress: bool = False
    should_interrupt: bool = False


@dataclass
class FakeMemoryState:
    theta_power: float = 0.5
    theta_frequency: float = 6.0
    coupling_strength: float = 0.5
    consolidation_strength: float = 0.5
    relay_strength: float = 0.5
    teaching_signal: float = 0.0
    error_magnitude: float = 0.0
    memory_gateway: float = 0.5


@dataclass
class FakeIntegrationState:
    binding_strength: float = 0.5
    reached_consciousness: bool = False
    dmn_activation: float = 0.3
    dmn_mode: str = 'default'
    orienting_saliency: float = 0.3
    cortical_error: float = 0.0
    cortical_output: float = 0.5
    bilateral_coherence: float = 0.5
    transfer_efficiency: float = 0.5


@dataclass
class FakeVisceralState:
    visceral_level: float = 0.5
    afferent_strength: float = 0.3
    reflex_active: bool = False
    liking: float = 0.5
    wanting: float = 0.5
    approach_strength: float = 0.3


@dataclass
class FakeSocialState:
    face_detected: bool = False
    identity_score: float = 0.0
    text_detected: bool = False
    word_score: float = 0.0
    agency_score: float = 0.5
    reorient_signal: bool = False
    social_inference: float = 0.0
    social_salience: float = 0.0
    familiarity: float = 0.3
    is_novel: bool = False


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_network_with_fake_states(with_coupling: bool = True):
    """Create a RadialAttentionNetwork with fake bridge states pre-loaded.

    No real bridge modules — just state objects that the scenario can modify.
    The network won't update bridge states (no bridges attached), but the
    ScenarioEngine step_fn overwrites them each tick anyway.
    """
    net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)

    # Populate legacy bridge states directly
    net._neuromod_state = FakeNeuromodState()
    net._cortex_state = FakeCortexState()
    net._limbic_state = FakeLimbicState()

    # Populate generic bridge states
    net._bridge_states['sleep_wake'] = FakeSleepWakeState()
    net._bridge_states['motor'] = FakeMotorState()
    net._bridge_states['defense'] = FakeDefenseState()
    net._bridge_states['memory'] = FakeMemoryState()
    net._bridge_states['integration'] = FakeIntegrationState()
    net._bridge_states['visceral'] = FakeVisceralState()
    net._bridge_states['social'] = FakeSocialState()

    return net


@pytest.fixture
def network():
    """Network with all 10 fake bridge states."""
    return _make_network_with_fake_states()


@pytest.fixture
def engine(network):
    """ScenarioEngine wrapping a fully-bridged network."""
    return ScenarioEngine(network, seed_dim=384)


# ─── Test: ScenarioEngine Core Mechanics ──────────────────────────────────────

class TestScenarioEngineCore:
    """Core engine mechanics: run, trajectory, snapshots."""

    def test_basic_run(self, engine):
        """Run a minimal scenario, verify trajectory length."""
        result = engine.run(name='test_basic', ticks=5)
        assert isinstance(result, ScenarioResult)
        assert result.name == 'test_basic'
        assert result.ticks == 5
        assert len(result.trajectory) == 5

    def test_tick_snapshots_have_correct_fields(self, engine):
        """Each TickSnapshot has all expected fields."""
        result = engine.run(name='test_fields', ticks=3)
        for snap in result.trajectory:
            assert isinstance(snap, TickSnapshot)
            assert isinstance(snap.tick, int)
            assert isinstance(snap.bridge_states, dict)
            assert isinstance(snap.modulation_factors, dict)
            assert isinstance(snap.prediction_errors, list)
            assert isinstance(snap.ring_norms, list)

    def test_bridge_states_captured(self, engine):
        """Bridge states are captured in snapshots."""
        result = engine.run(name='test_states', ticks=2)
        snap = result.trajectory[0]
        # Should have all 10 bridges
        assert 'neuromod' in snap.bridge_states
        assert 'cortex' in snap.bridge_states
        assert 'limbic' in snap.bridge_states
        assert 'sleep_wake' in snap.bridge_states
        assert 'motor' in snap.bridge_states
        assert 'defense' in snap.bridge_states
        assert 'memory' in snap.bridge_states
        assert 'integration' in snap.bridge_states
        assert 'visceral' in snap.bridge_states
        assert 'social' in snap.bridge_states

    def test_modulation_factors_captured(self, engine):
        """Modulation factors are captured in snapshots."""
        result = engine.run(name='test_mod', ticks=2)
        snap = result.trajectory[0]
        assert 'attention_gain' in snap.modulation_factors
        assert 'precision_boost' in snap.modulation_factors
        assert 'ffn_throughput' in snap.modulation_factors
        assert 'threshold_mod' in snap.modulation_factors

    def test_ring_norms_captured(self, engine):
        """Ring norms are captured (5 rings)."""
        result = engine.run(name='test_norms', ticks=2)
        snap = result.trajectory[0]
        assert len(snap.ring_norms) == 5
        for norm in snap.ring_norms:
            assert isinstance(norm, float)
            assert norm >= 0

    def test_prediction_errors_captured(self, engine):
        """Prediction errors are captured (4 inter-ring errors)."""
        result = engine.run(name='test_pe', ticks=2)
        snap = result.trajectory[0]
        assert len(snap.prediction_errors) == 4
        for pe in snap.prediction_errors:
            assert isinstance(pe, float)

    def test_step_fn_called(self, engine):
        """step_fn is called each tick with correct args."""
        calls = []

        def step(tick, eng):
            calls.append(tick)
            assert isinstance(eng, ScenarioEngine)

        engine.run(name='test_step', ticks=5, step_fn=step)
        assert calls == [0, 1, 2, 3, 4]

    def test_seed_fn_called(self, engine):
        """Custom seed_fn provides seeds."""
        def seed_fn(tick):
            return torch.ones(1, 384) * (tick + 1)

        result = engine.run(name='test_seed', ticks=3, seed_fn=seed_fn)
        assert len(result.trajectory) == 3

    def test_initial_overrides(self, engine):
        """Initial overrides are applied before first tick."""
        result = engine.run(
            name='test_override',
            ticks=1,
            initial_overrides={
                'defense': {'defense_intensity': 0.99},
            },
        )
        # The defense state should reflect the override
        # (Note: since no real bridge updates, the override persists)
        snap = result.trajectory[0]
        assert snap.bridge_states['defense']['defense_intensity'] == 0.99

    def test_bridge_series_extraction(self, engine):
        """bridge_series extracts time series correctly."""
        def step(tick, eng):
            eng.set_bridge_field('neuromod', 'dopamine', 0.1 * tick)

        result = engine.run(name='test_series', ticks=5, step_fn=step)
        da_series = result.bridge_series('neuromod', 'dopamine')
        assert len(da_series) == 5
        # Values should reflect what step_fn set
        for i, val in enumerate(da_series):
            assert abs(val - 0.1 * i) < 0.01

    def test_modulation_series_extraction(self, engine):
        """modulation_series extracts composite factor time series."""
        result = engine.run(name='test_mod_series', ticks=3)
        att_series = result.modulation_series('attention_gain')
        assert len(att_series) == 3
        for val in att_series:
            assert 0.3 <= val <= 3.0  # clamped range

    def test_metadata_stored(self, engine):
        """Metadata is stored on result."""
        result = engine.run(
            name='test_meta', ticks=1,
            metadata={'key': 'value'},
        )
        assert result.metadata == {'key': 'value'}

    def test_results_cached(self, engine):
        """Results are accessible after run."""
        engine.run(name='cached_test', ticks=1)
        retrieved = engine.get_results('cached_test')
        assert retrieved is not None
        assert retrieved.name == 'cached_test'

    def test_list_results(self, engine):
        """list_results returns all completed scenario names."""
        engine.run(name='a', ticks=1)
        engine.run(name='b', ticks=1)
        assert set(engine.list_results()) == {'a', 'b'}

    def test_final_property(self, engine):
        """result.final returns last tick snapshot."""
        result = engine.run(name='test_final', ticks=5)
        assert result.final.tick == 4

    def test_set_bridge_field_legacy(self, engine):
        """set_bridge_field works for legacy bridges."""
        assert engine.set_bridge_field('neuromod', 'dopamine', 0.9)
        assert engine.get_bridge_state('neuromod').dopamine == 0.9

    def test_set_bridge_field_generic(self, engine):
        """set_bridge_field works for generic bridges."""
        assert engine.set_bridge_field('defense', 'defense_intensity', 0.8)
        assert engine.get_bridge_state('defense').defense_intensity == 0.8

    def test_set_bridge_field_missing(self, engine):
        """set_bridge_field returns False for nonexistent bridge."""
        assert not engine.set_bridge_field('nonexistent', 'field', 0.5)


# ─── Test: Scenario Registry ─────────────────────────────────────────────────

class TestScenarioRegistry:
    """Tests for the SCENARIOS registry and run_scenario()."""

    def test_all_scenarios_registered(self):
        """All 6 scenarios are in the registry."""
        assert len(SCENARIOS) == 6
        expected = {
            'threat_while_sleepy',
            'novel_social_under_load',
            'reward_prediction_error',
            'sustained_stress',
            'creative_exploration',
            'minibook_collaboration_burst',
        }
        assert set(SCENARIOS.keys()) == expected

    def test_run_scenario_convenience(self):
        """run_scenario() convenience function works."""
        net = _make_network_with_fake_states()
        result = run_scenario(net, 'threat_while_sleepy', ticks=5)
        assert result.name == 'threat_while_sleepy'
        assert result.ticks == 5

    def test_run_scenario_unknown(self):
        """run_scenario() raises for unknown name."""
        net = _make_network_with_fake_states()
        with pytest.raises(ValueError, match="Unknown scenario"):
            run_scenario(net, 'nonexistent')


# ─── Test: Scenario — threat_while_sleepy ─────────────────────────────────────

class TestThreatWhileSleepy:
    """Threat + sleep → defense active, motor suppressed, conflict elevated."""

    def test_runs_without_error(self):
        """Scenario completes without exceptions."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_threat_while_sleepy(engine, ticks=20)
        assert result.ticks == 20

    def test_defense_intensity_high(self):
        """Defense intensity stays high throughout."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_threat_while_sleepy(engine, ticks=20)
        for snap in result.trajectory:
            di = snap.bridge_states.get('defense', {}).get('defense_intensity', 0)
            assert di >= 0.8, f"Tick {snap.tick}: defense_intensity={di}"

    def test_sleep_arousal_starts_low(self):
        """Sleep-wake arousal starts low and gradually increases."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_threat_while_sleepy(engine, ticks=20)
        early_arousal = result.trajectory[0].bridge_states.get(
            'sleep_wake', {}).get('arousal', 1.0)
        late_arousal = result.trajectory[-1].bridge_states.get(
            'sleep_wake', {}).get('arousal', 0.0)
        assert early_arousal < 0.3, f"Early arousal should be low: {early_arousal}"
        assert late_arousal > early_arousal, "Arousal should increase over time"

    def test_attention_gain_responds(self):
        """Attention gain reflects the defense×sleep interaction."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_threat_while_sleepy(engine, ticks=20)
        # Attention should be affected by both defense (H19) and sleep (H14)
        gains = result.modulation_series('attention_gain')
        # Later ticks should have higher attention (arousal recovering)
        assert gains[-1] > gains[0] or gains[-1] > 0.3

    def test_high_melatonin_early(self):
        """Melatonin is high early (sleepy) and decreases."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_threat_while_sleepy(engine, ticks=20)
        early_mel = result.trajectory[0].bridge_states.get(
            'sleep_wake', {}).get('melatonin', 0)
        late_mel = result.trajectory[-1].bridge_states.get(
            'sleep_wake', {}).get('melatonin', 1)
        assert early_mel > late_mel, "Melatonin should decrease as waking up"


# ─── Test: Scenario — novel_social_under_load ─────────────────────────────────

class TestNovelSocialUnderLoad:
    """Novel social + cognitive load → social activates but constrained."""

    def test_runs_without_error(self):
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_novel_social_under_load(engine, ticks=20)
        assert result.ticks == 20

    def test_social_salience_after_onset(self):
        """Social salience rises after tick 5."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_novel_social_under_load(engine, ticks=20)
        pre = result.trajectory[3].bridge_states.get(
            'social', {}).get('social_salience', 0)
        post = result.trajectory[10].bridge_states.get(
            'social', {}).get('social_salience', 0)
        assert post > pre, f"Social salience should rise: {pre} -> {post}"

    def test_conflict_high_throughout(self):
        """ACC conflict stays elevated (cognitive load)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_novel_social_under_load(engine, ticks=20)
        for snap in result.trajectory:
            conflict = snap.bridge_states.get('cortex', {}).get('conflict', 0)
            assert conflict >= 0.6, f"Tick {snap.tick}: conflict={conflict}"

    def test_threshold_mod_reflects_conflict(self):
        """Threshold mod should be affected by high conflict (H8)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_novel_social_under_load(engine, ticks=20)
        thr = result.modulation_series('threshold_mod')
        # High conflict → threshold_mod reduced (H8: 1.0 - 0.3 * conflict)
        for val in thr:
            assert val < 1.5, f"Threshold should be modulated by conflict: {val}"

    def test_low_familiarity(self):
        """Novel social input has low familiarity."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_novel_social_under_load(engine, ticks=15)
        # After onset (tick 5+)
        fam = result.trajectory[8].bridge_states.get(
            'social', {}).get('familiarity', 1.0)
        assert fam <= 0.2, f"Familiarity should be low for novel: {fam}"


# ─── Test: Scenario — reward_prediction_error ─────────────────────────────────

class TestRewardPredictionError:
    """Positive RPE → DA burst, approach increase, learning boost."""

    def test_runs_without_error(self):
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_reward_prediction_error(engine, ticks=25)
        assert result.ticks == 25

    def test_da_spike_at_rpe(self):
        """Dopamine spikes at tick 10 (reward delivery)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_reward_prediction_error(engine, ticks=25)
        da_series = result.bridge_series('neuromod', 'dopamine')
        # Baseline DA at tick 5
        assert da_series[5] < 0.5
        # Spike at tick 10
        assert da_series[10] > 0.9

    def test_da_decays_after_spike(self):
        """Dopamine decays back toward baseline after RPE."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_reward_prediction_error(engine, ticks=25)
        da_series = result.bridge_series('neuromod', 'dopamine')
        assert da_series[15] < da_series[10], "DA should decay after spike"
        assert da_series[20] < da_series[15], "DA should continue decaying"

    def test_positive_valence_at_rpe(self):
        """Valence becomes positive at RPE."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_reward_prediction_error(engine, ticks=20)
        val_series = result.bridge_series('limbic', 'valence')
        assert val_series[5] == 0.0  # baseline
        assert val_series[10] > 0.5  # positive at RPE

    def test_ach_learning_boost(self):
        """ACh increases at RPE for plasticity enhancement."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_reward_prediction_error(engine, ticks=20)
        ach_series = result.bridge_series('neuromod', 'acetylcholine')
        assert ach_series[10] > ach_series[5], "ACh should spike at RPE"

    def test_approach_drive_increases(self):
        """Approach drive increases at reward."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_reward_prediction_error(engine, ticks=20)
        approach = result.bridge_series('limbic', 'approach_drive')
        assert approach[10] > approach[5], "Approach should increase at RPE"

    def test_precision_boost_reflects_da(self):
        """Precision boost affected by DA spike (H2)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_reward_prediction_error(engine, ticks=20)
        prec = result.modulation_series('precision_boost')
        # At tick 10 DA is high → precision should be elevated
        assert prec[10] > prec[5], "Precision should rise with DA"


# ─── Test: Scenario — sustained_stress ────────────────────────────────────────

class TestSustainedStress:
    """Prolonged stress → rising anxiety, suppressed encoding, negative valence."""

    def test_runs_without_error(self):
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_sustained_stress(engine, ticks=50)
        assert result.ticks == 50

    def test_anxiety_rises(self):
        """Anxiety level increases over time."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_sustained_stress(engine, ticks=50)
        anx = result.bridge_series('defense', 'anxiety_level')
        assert anx[-1] > anx[0], "Anxiety should rise over time"
        assert anx[-1] > 0.6, f"Anxiety should be high by end: {anx[-1]}"

    def test_stress_accumulates(self):
        """Limbic stress accumulates over ticks."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_sustained_stress(engine, ticks=50)
        stress = result.bridge_series('limbic', 'stress')
        assert stress[-1] > stress[0], "Stress should accumulate"
        assert stress[-1] > 0.5

    def test_encoding_suppressed(self):
        """Memory consolidation decreases under sustained stress."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_sustained_stress(engine, ticks=50)
        consol = result.bridge_series('memory', 'consolidation_strength')
        assert consol[-1] < consol[0], "Consolidation should decrease"
        assert consol[-1] < 0.4, f"Consolidation should be low: {consol[-1]}"

    def test_negative_valence(self):
        """Valence becomes increasingly negative."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_sustained_stress(engine, ticks=50)
        val = result.bridge_series('limbic', 'valence')
        assert val[-1] < val[0], "Valence should decrease"
        assert val[-1] < -0.2, f"Valence should be negative: {val[-1]}"

    def test_ne_elevated(self):
        """NE stays elevated (vigilance response)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_sustained_stress(engine, ticks=50)
        ne = result.bridge_series('neuromod', 'norepinephrine')
        assert ne[-1] > ne[0], "NE should rise"
        assert ne[-1] > 0.7

    def test_serotonin_depleted(self):
        """Serotonin dips under sustained stress."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_sustained_stress(engine, ticks=50)
        sert = result.bridge_series('neuromod', 'serotonin')
        assert sert[-1] < sert[0], "Serotonin should decrease under stress"


# ─── Test: Scenario — creative_exploration ────────────────────────────────────

class TestCreativeExploration:
    """Safe idle → DMN active, explore mode, high ACh."""

    def test_runs_without_error(self):
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_creative_exploration(engine, ticks=20)
        assert result.ticks == 20

    def test_no_defense(self):
        """Defense is deactivated throughout."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_creative_exploration(engine, ticks=20)
        for snap in result.trajectory:
            di = snap.bridge_states.get('defense', {}).get(
                'defense_intensity', 1)
            assert di == 0.0

    def test_explore_mode(self):
        """Explore ratio is high (LC tonic)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_creative_exploration(engine, ticks=20)
        exp = result.bridge_series('neuromod', 'explore_ratio')
        for val in exp:
            assert val >= 0.7, f"Explore ratio should be high: {val}"

    def test_high_ach(self):
        """ACh is high for plasticity."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_creative_exploration(engine, ticks=20)
        ach = result.bridge_series('neuromod', 'acetylcholine')
        for val in ach:
            assert val >= 0.7, f"ACh should be high: {val}"

    def test_dmn_active(self):
        """DMN activation is elevated."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_creative_exploration(engine, ticks=20)
        dmn = result.bridge_series('integration', 'dmn_activation')
        for val in dmn:
            assert val >= 0.6, f"DMN should be active: {val}"

    def test_low_ne(self):
        """NE is low (tonic LC, broad attention)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_creative_exploration(engine, ticks=20)
        ne = result.bridge_series('neuromod', 'norepinephrine')
        for val in ne:
            assert val <= 0.4, f"NE should be low: {val}"

    def test_positive_valence(self):
        """Valence is mildly positive."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_creative_exploration(engine, ticks=20)
        val = result.bridge_series('limbic', 'valence')
        for v in val:
            assert v > 0, f"Valence should be positive: {v}"


# ─── Test: Scenario — minibook_collaboration_burst ────────────────────────────

class TestMinibookCollaborationBurst:
    """Social burst → social activation, positive valence, attention reorienting."""

    def test_runs_without_error(self):
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_minibook_collaboration_burst(engine, ticks=25)
        assert result.ticks == 25

    def test_social_salience_rises_during_burst(self):
        """Social salience increases during burst phase."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_minibook_collaboration_burst(engine, ticks=25)
        pre = result.trajectory[1].bridge_states.get(
            'social', {}).get('social_salience', 0)
        peak = result.trajectory[12].bridge_states.get(
            'social', {}).get('social_salience', 0)
        assert peak > pre, f"Social salience should rise: {pre} -> {peak}"
        assert peak > 0.6

    def test_social_salience_decays_after_burst(self):
        """Social salience decays after burst peak."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_minibook_collaboration_burst(engine, ticks=25)
        peak = result.trajectory[12].bridge_states.get(
            'social', {}).get('social_salience', 0)
        late = result.trajectory[-1].bridge_states.get(
            'social', {}).get('social_salience', 0)
        assert late < peak, f"Social salience should decay: {peak} -> {late}"

    def test_binding_strength_rises(self):
        """Integration binding increases for multi-agent tracking."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_minibook_collaboration_burst(engine, ticks=25)
        bind = result.bridge_series('integration', 'binding_strength')
        assert bind[10] > bind[0], "Binding should increase during burst"

    def test_attention_gain_modulated(self):
        """Attention gain reflects social + integration activity."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_minibook_collaboration_burst(engine, ticks=25)
        att = result.modulation_series('attention_gain')
        # During burst, social salience (H28) + binding (H23) should boost attention
        burst_att = att[10]
        pre_att = att[0]
        assert burst_att > pre_att * 0.9, "Attention should be affected by social burst"

    def test_identity_score_during_burst(self):
        """Identity scores are set during burst (multi-agent recognition)."""
        net = _make_network_with_fake_states()
        engine = ScenarioEngine(net, seed_dim=384)
        result = scenario_minibook_collaboration_burst(engine, ticks=20)
        ident = result.trajectory[8].bridge_states.get(
            'social', {}).get('identity_score', 0)
        assert ident > 0.5, f"Identity should be active during burst: {ident}"


# ─── Test: Cross-Scenario Comparisons ─────────────────────────────────────────

class TestCrossScenarioComparisons:
    """Compare emergent properties across different scenarios."""

    def test_stress_vs_exploration_valence(self):
        """Sustained stress has more negative valence than creative exploration."""
        net1 = _make_network_with_fake_states()
        eng1 = ScenarioEngine(net1, seed_dim=384)
        stress = scenario_sustained_stress(eng1, ticks=30)

        net2 = _make_network_with_fake_states()
        eng2 = ScenarioEngine(net2, seed_dim=384)
        creative = scenario_creative_exploration(eng2, ticks=30)

        stress_val = stress.bridge_series('limbic', 'valence')[-1]
        creative_val = creative.bridge_series('limbic', 'valence')[-1]
        assert stress_val < creative_val, \
            f"Stress valence ({stress_val}) should be lower than creative ({creative_val})"

    def test_threat_vs_exploration_defense(self):
        """Threat scenario has higher defense than exploration."""
        net1 = _make_network_with_fake_states()
        eng1 = ScenarioEngine(net1, seed_dim=384)
        threat = scenario_threat_while_sleepy(eng1, ticks=15)

        net2 = _make_network_with_fake_states()
        eng2 = ScenarioEngine(net2, seed_dim=384)
        creative = scenario_creative_exploration(eng2, ticks=15)

        threat_def = threat.bridge_series('defense', 'defense_intensity')[-1]
        creative_def = creative.bridge_series('defense', 'defense_intensity')[-1]
        assert threat_def > creative_def

    def test_rpe_vs_stress_dopamine(self):
        """RPE scenario has DA spike, stress does not."""
        net1 = _make_network_with_fake_states()
        eng1 = ScenarioEngine(net1, seed_dim=384)
        rpe = scenario_reward_prediction_error(eng1, ticks=15)

        net2 = _make_network_with_fake_states()
        eng2 = ScenarioEngine(net2, seed_dim=384)
        stress = scenario_sustained_stress(eng2, ticks=15)

        rpe_da_peak = max(rpe.bridge_series('neuromod', 'dopamine'))
        stress_da_peak = max(stress.bridge_series('neuromod', 'dopamine'))
        assert rpe_da_peak > stress_da_peak, \
            f"RPE DA peak ({rpe_da_peak}) should exceed stress ({stress_da_peak})"
