"""
Tests for InterBridgeCouplingRegistry: all 6 pathways, cascade effects,
ModulationContext integration, and edge cases.
"""

import pytest
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.inter_bridge_coupling import (
    InterBridgeCouplingRegistry,
    CouplingPathway,
    _defense_to_motor,
    _limbic_to_visceral,
    _sleep_to_neuromod,
    _motor_to_integration,
    _integration_to_limbic,
    _social_to_limbic,
)
from core.modulation_context import ModulationContext


# ─── Fake state dataclasses ──────────────────────────────────────────────────

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
    defense_mode: str = 'calm'
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


def _make_all_states(**overrides):
    """Create a dict of all 10 bridge states with optional overrides."""
    states = {
        'neuromod': FakeNeuromodState(),
        'cortex': FakeCortexState(),
        'limbic': FakeLimbicState(),
        'sleep_wake': FakeSleepWakeState(),
        'motor': FakeMotorState(),
        'defense': FakeDefenseState(),
        'memory': FakeMemoryState(),
        'integration': FakeIntegrationState(),
        'visceral': FakeVisceralState(),
        'social': FakeSocialState(),
    }
    for key, value in overrides.items():
        states[key] = value
    return states


# ─── Test: Registry Basics ────────────────────────────────────────────────────

class TestRegistryBasics:
    def test_defaults_registered(self):
        reg = InterBridgeCouplingRegistry()
        assert len(reg.pathways) == 6

    def test_no_defaults(self):
        reg = InterBridgeCouplingRegistry(register_defaults=False)
        assert len(reg.pathways) == 0

    def test_register_custom_pathway(self):
        reg = InterBridgeCouplingRegistry(register_defaults=False)
        reg.register(CouplingPathway(
            name='test', source_bridge='a', target_bridge='b',
            transform=lambda s, t: None,
        ))
        assert len(reg.pathways) == 1

    def test_unregister(self):
        reg = InterBridgeCouplingRegistry()
        assert reg.unregister('defense_to_motor') is True
        assert len(reg.pathways) == 5
        assert reg.unregister('nonexistent') is False

    def test_set_enabled(self):
        reg = InterBridgeCouplingRegistry()
        assert reg.set_enabled('defense_to_motor', False) is True
        p = reg.get_pathway('defense_to_motor')
        assert p.enabled is False

    def test_get_pathway(self):
        reg = InterBridgeCouplingRegistry()
        p = reg.get_pathway('defense_to_motor')
        assert p is not None
        assert p.source_bridge == 'defense'
        assert p.target_bridge == 'motor'

    def test_list_pathways(self):
        reg = InterBridgeCouplingRegistry()
        listing = reg.list_pathways()
        assert len(listing) == 6
        names = [p['name'] for p in listing]
        assert 'defense_to_motor' in names
        assert 'social_to_limbic' in names

    def test_propagation_count(self):
        reg = InterBridgeCouplingRegistry()
        states = _make_all_states()
        reg.propagate(states)
        assert reg.propagation_count == 1
        reg.propagate(states)
        assert reg.propagation_count == 2

    def test_propagate_returns_fired_count(self):
        reg = InterBridgeCouplingRegistry()
        states = _make_all_states()
        fired = reg.propagate(states)
        assert fired == 6  # All 6 pathways fire

    def test_propagate_skips_disabled(self):
        reg = InterBridgeCouplingRegistry()
        reg.set_enabled('defense_to_motor', False)
        states = _make_all_states()
        fired = reg.propagate(states)
        assert fired == 5

    def test_propagate_skips_missing_bridge(self):
        reg = InterBridgeCouplingRegistry()
        # Only provide neuromod and sleep_wake
        states = {'sleep_wake': FakeSleepWakeState(arousal=0.1),
                  'neuromod': FakeNeuromodState()}
        fired = reg.propagate(states)
        assert fired == 1  # Only sleep_to_neuromod fires


# ─── Test: Defense→Motor Coupling ─────────────────────────────────────────────

class TestDefenseToMotor:
    def test_no_effect_below_threshold(self):
        defense = FakeDefenseState(defense_intensity=0.3)
        motor = FakeMotorState(action_tendency=0.5, inhibition_level=0.5)
        _defense_to_motor(defense, motor)
        assert motor.action_tendency == 0.5  # unchanged
        assert motor.inhibition_level == 0.5

    def test_high_threat_boosts_action(self):
        defense = FakeDefenseState(defense_intensity=0.9)
        motor = FakeMotorState(action_tendency=0.5, inhibition_level=0.5)
        _defense_to_motor(defense, motor)
        # excess = 0.9 - 0.5 = 0.4, boost = 0.4 * 0.4 = 0.16
        assert motor.action_tendency > 0.5
        assert motor.action_tendency == pytest.approx(0.66, abs=0.01)

    def test_high_threat_reduces_inhibition(self):
        defense = FakeDefenseState(defense_intensity=0.9)
        motor = FakeMotorState(inhibition_level=0.5)
        _defense_to_motor(defense, motor)
        # excess = 0.4, reduction = 0.3 * 0.4 = 0.12
        assert motor.inhibition_level < 0.5
        assert motor.inhibition_level == pytest.approx(0.38, abs=0.01)

    def test_clamped_to_range(self):
        defense = FakeDefenseState(defense_intensity=1.0)
        motor = FakeMotorState(action_tendency=0.95, inhibition_level=0.05)
        _defense_to_motor(defense, motor)
        assert 0.0 <= motor.action_tendency <= 1.0
        assert 0.0 <= motor.inhibition_level <= 1.0

    def test_max_threat(self):
        defense = FakeDefenseState(defense_intensity=1.0)
        motor = FakeMotorState(action_tendency=0.5, inhibition_level=0.5)
        _defense_to_motor(defense, motor)
        assert motor.action_tendency > 0.6
        assert motor.inhibition_level < 0.4


# ─── Test: Limbic→Visceral Coupling ───────────────────────────────────────────

class TestLimbicToVisceral:
    def test_no_effect_below_threshold(self):
        limbic = FakeLimbicState(arousal=0.4)
        visceral = FakeVisceralState(afferent_strength=0.3)
        _limbic_to_visceral(limbic, visceral)
        assert visceral.afferent_strength == 0.3

    def test_high_arousal_boosts_afferent(self):
        limbic = FakeLimbicState(arousal=0.9)
        visceral = FakeVisceralState(afferent_strength=0.3)
        _limbic_to_visceral(limbic, visceral)
        # excess = 0.3, boost = 0.5 * 0.3 = 0.15
        assert visceral.afferent_strength == pytest.approx(0.45, abs=0.01)

    def test_clamped(self):
        limbic = FakeLimbicState(arousal=1.0)
        visceral = FakeVisceralState(afferent_strength=0.9)
        _limbic_to_visceral(limbic, visceral)
        assert visceral.afferent_strength <= 1.0


# ─── Test: SleepWake→Neuromod Coupling ────────────────────────────────────────

class TestSleepToNeuromod:
    def test_no_effect_when_awake(self):
        sleep = FakeSleepWakeState(arousal=0.7)
        neuromod = FakeNeuromodState(dopamine=0.5, norepinephrine=0.5)
        _sleep_to_neuromod(sleep, neuromod)
        assert neuromod.dopamine == 0.5
        assert neuromod.norepinephrine == 0.5

    def test_low_arousal_suppresses_da_ne(self):
        sleep = FakeSleepWakeState(arousal=0.15)
        neuromod = FakeNeuromodState(dopamine=0.6, norepinephrine=0.6)
        _sleep_to_neuromod(sleep, neuromod)
        # suppress = 0.15 / 0.3 = 0.5
        assert neuromod.dopamine == pytest.approx(0.3, abs=0.01)
        assert neuromod.norepinephrine == pytest.approx(0.3, abs=0.01)

    def test_zero_arousal_fully_suppresses(self):
        sleep = FakeSleepWakeState(arousal=0.0)
        neuromod = FakeNeuromodState(dopamine=0.5, norepinephrine=0.5)
        _sleep_to_neuromod(sleep, neuromod)
        assert neuromod.dopamine == 0.0
        assert neuromod.norepinephrine == 0.0

    def test_boundary_arousal(self):
        sleep = FakeSleepWakeState(arousal=0.3)
        neuromod = FakeNeuromodState(dopamine=0.5, norepinephrine=0.5)
        _sleep_to_neuromod(sleep, neuromod)
        # arousal == threshold → no suppression (condition is <0.3)
        assert neuromod.dopamine == 0.5


# ─── Test: Motor→Integration Coupling ─────────────────────────────────────────

class TestMotorToIntegration:
    def test_action_feeds_binding(self):
        motor = FakeMotorState(action_tendency=0.8)
        integration = FakeIntegrationState(binding_strength=0.5)
        _motor_to_integration(motor, integration)
        # boost = 0.15 * 0.8 = 0.12
        assert integration.binding_strength == pytest.approx(0.62, abs=0.01)

    def test_zero_action(self):
        motor = FakeMotorState(action_tendency=0.0)
        integration = FakeIntegrationState(binding_strength=0.5)
        _motor_to_integration(motor, integration)
        assert integration.binding_strength == 0.5  # No change (0.15 * 0 = 0)

    def test_clamped(self):
        motor = FakeMotorState(action_tendency=1.0)
        integration = FakeIntegrationState(binding_strength=0.95)
        _motor_to_integration(motor, integration)
        assert integration.binding_strength <= 1.0


# ─── Test: Integration→Limbic Coupling ────────────────────────────────────────

class TestIntegrationToLimbic:
    def test_binding_feeds_salience(self):
        integration = FakeIntegrationState(binding_strength=0.8)
        limbic = FakeLimbicState(salience=0.3)
        _integration_to_limbic(integration, limbic)
        # boost = 0.15 * 0.8 = 0.12
        assert limbic.salience == pytest.approx(0.42, abs=0.01)

    def test_clamped(self):
        integration = FakeIntegrationState(binding_strength=1.0)
        limbic = FakeLimbicState(salience=0.95)
        _integration_to_limbic(integration, limbic)
        assert limbic.salience <= 1.0


# ─── Test: Social→Limbic Coupling ─────────────────────────────────────────────

class TestSocialToLimbic:
    def test_no_effect_below_threshold(self):
        social = FakeSocialState(social_salience=0.1)
        limbic = FakeLimbicState(valence=0.0, arousal=0.3)
        _social_to_limbic(social, limbic)
        assert limbic.valence == 0.0
        assert limbic.arousal == 0.3

    def test_high_social_boosts_valence_and_arousal(self):
        social = FakeSocialState(social_salience=0.8)
        limbic = FakeLimbicState(valence=0.0, arousal=0.3)
        _social_to_limbic(social, limbic)
        # excess = 0.6, valence += 0.15 * 0.6 = 0.09, arousal += 0.1 * 0.6 = 0.06
        assert limbic.valence > 0.0
        assert limbic.valence == pytest.approx(0.09, abs=0.01)
        assert limbic.arousal > 0.3
        assert limbic.arousal == pytest.approx(0.36, abs=0.01)

    def test_max_social(self):
        social = FakeSocialState(social_salience=1.0)
        limbic = FakeLimbicState(valence=0.0, arousal=0.3)
        _social_to_limbic(social, limbic)
        assert limbic.valence > 0.0
        assert limbic.arousal > 0.3

    def test_clamped(self):
        social = FakeSocialState(social_salience=1.0)
        limbic = FakeLimbicState(valence=0.9, arousal=0.95)
        _social_to_limbic(social, limbic)
        assert limbic.valence <= 1.0
        assert limbic.arousal <= 1.0


# ─── Test: Multi-Bridge Cascade ───────────────────────────────────────────────

class TestCascade:
    def test_threat_cascade_defense_motor_integration(self):
        """High threat → defense activates → motor boosts action →
        integration binding increases."""
        reg = InterBridgeCouplingRegistry()
        defense = FakeDefenseState(defense_intensity=0.9)
        motor = FakeMotorState(action_tendency=0.5, inhibition_level=0.5)
        integration = FakeIntegrationState(binding_strength=0.5)
        states = _make_all_states(
            defense=defense, motor=motor, integration=integration)

        reg.propagate(states)

        # Defense→Motor should have fired
        assert motor.action_tendency > 0.5
        # Motor→Integration should have fired (using boosted action_tendency)
        assert integration.binding_strength > 0.5

    def test_social_cascade_social_limbic_visceral(self):
        """High social signal → limbic arousal/valence up →
        visceral afferent up (if arousal crosses threshold)."""
        reg = InterBridgeCouplingRegistry()
        social = FakeSocialState(social_salience=0.9)
        limbic = FakeLimbicState(valence=0.0, arousal=0.55, salience=0.3)
        visceral = FakeVisceralState(afferent_strength=0.3)
        states = _make_all_states(
            social=social, limbic=limbic, visceral=visceral)

        reg.propagate(states)

        # Social→Limbic fires: arousal goes up
        assert limbic.arousal > 0.55
        # Limbic→Visceral: if arousal now > 0.6, afferent increases
        # arousal started at 0.55 + social boost ~0.07 = ~0.62
        if limbic.arousal > 0.6:
            assert visceral.afferent_strength > 0.3

    def test_sleep_cascade_suppresses_everything(self):
        """Deep sleep → neuromod DA/NE suppressed."""
        reg = InterBridgeCouplingRegistry()
        sleep = FakeSleepWakeState(arousal=0.1)
        neuromod = FakeNeuromodState(dopamine=0.6, norepinephrine=0.6)
        states = _make_all_states(sleep_wake=sleep, neuromod=neuromod)

        reg.propagate(states)

        # Sleep→Neuromod: DA and NE suppressed
        assert neuromod.dopamine < 0.6
        assert neuromod.norepinephrine < 0.6


# ─── Test: ModulationContext Integration ──────────────────────────────────────

class TestModulationContextIntegration:
    def test_coupling_fires_before_hooks(self):
        """Couplings should modify states before hooks read them."""
        reg = InterBridgeCouplingRegistry()

        # Deep sleep state → should suppress neuromod DA/NE
        neuromod = FakeNeuromodState(dopamine=0.6, norepinephrine=0.6)
        sleep = FakeSleepWakeState(arousal=0.1)

        ctx = ModulationContext(
            neuromod=neuromod,
            sleep_wake=sleep,
            coupling_registry=reg,
        )
        ctx.compute()

        # After coupling: DA should be suppressed
        assert neuromod.dopamine < 0.6
        # Hooks then read suppressed DA → precision_boost is lower
        # than it would be without coupling

    def test_no_coupling_without_registry(self):
        """Without registry, behavior unchanged."""
        neuromod = FakeNeuromodState(dopamine=0.6)
        ctx_no_coupling = ModulationContext(neuromod=neuromod)
        ctx_no_coupling.compute()
        prec_no = ctx_no_coupling.precision_boost

        neuromod2 = FakeNeuromodState(dopamine=0.6)
        ctx_with_empty = ModulationContext(
            neuromod=neuromod2,
            coupling_registry=InterBridgeCouplingRegistry(register_defaults=False),
        )
        ctx_with_empty.compute()
        prec_with = ctx_with_empty.precision_boost

        assert prec_no == pytest.approx(prec_with, abs=1e-6)

    def test_coupling_affects_composite_factors(self):
        """Defense→Motor coupling should change attention_gain via H18."""
        reg = InterBridgeCouplingRegistry()

        # High threat → motor action_tendency boosted
        defense = FakeDefenseState(defense_intensity=0.9)
        motor = FakeMotorState(action_tendency=0.5)

        # Without coupling
        motor_uncoupled = FakeMotorState(action_tendency=0.5)
        ctx1 = ModulationContext(defense=FakeDefenseState(defense_intensity=0.9),
                                 motor=motor_uncoupled)
        ctx1.compute()
        att_uncoupled = ctx1.attention_gain

        # With coupling
        ctx2 = ModulationContext(defense=defense, motor=motor,
                                 coupling_registry=reg)
        ctx2.compute()
        att_coupled = ctx2.attention_gain

        # Coupled should have higher attention (boosted action_tendency → H18)
        assert att_coupled > att_uncoupled

    def test_all_bridges_with_coupling(self):
        """Full suite of bridges with coupling should compute without error."""
        reg = InterBridgeCouplingRegistry()
        states = _make_all_states()
        ctx = ModulationContext(
            neuromod=states['neuromod'],
            cortex=states['cortex'],
            limbic=states['limbic'],
            sleep_wake=states['sleep_wake'],
            motor=states['motor'],
            defense=states['defense'],
            memory=states['memory'],
            integration=states['integration'],
            visceral=states['visceral'],
            social=states['social'],
            coupling_registry=reg,
        )
        ctx.compute()

        # All factors should be within clamp range
        assert 0.3 <= ctx.attention_gain <= 3.0
        assert 0.3 <= ctx.precision_boost <= 3.0
        assert 0.3 <= ctx.ffn_throughput <= 3.0
        assert 0.3 <= ctx.threshold_mod <= 3.0


# ─── Test: Edge Cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_propagate_empty_states(self):
        reg = InterBridgeCouplingRegistry()
        fired = reg.propagate({})
        assert fired == 0

    def test_propagate_partial_states(self):
        reg = InterBridgeCouplingRegistry()
        fired = reg.propagate({'neuromod': FakeNeuromodState()})
        assert fired == 0  # No pathway has neuromod as source

    def test_transform_exception_handled(self):
        """If a transform raises, it should be caught and skipped."""
        def bad_transform(s, t):
            raise ValueError("boom")

        reg = InterBridgeCouplingRegistry(register_defaults=False)
        reg.register(CouplingPathway(
            name='bad', source_bridge='defense', target_bridge='motor',
            transform=bad_transform,
        ))
        states = _make_all_states()
        fired = reg.propagate(states)
        assert fired == 0  # Exception prevented count

    def test_disabled_pathway_not_called(self):
        called = []

        def tracking_transform(s, t):
            called.append(True)

        reg = InterBridgeCouplingRegistry(register_defaults=False)
        reg.register(CouplingPathway(
            name='test', source_bridge='defense', target_bridge='motor',
            transform=tracking_transform, enabled=False,
        ))
        states = _make_all_states()
        reg.propagate(states)
        assert len(called) == 0
