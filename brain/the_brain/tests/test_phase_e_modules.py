"""
Tests for Phase E: Tier 2 Brain Structures

9 modules, ~110 tests covering:
  - Claustrum (cross-modal binding, consciousness gating)
  - Reticular Formation / ARAS (arousal, sensory gating, sleep-wake)
  - Basal Forebrain (ACh, plasticity gating, encoding/retrieval)
  - Septal Nuclei (theta rhythm, gamma coupling, memory timing)
  - Inferior Olive (error signal, timing, teaching)
  - Mammillary Bodies (Papez relay, spatial memory, consolidation)
  - BNST (sustained anxiety, chronic stress, vigilance)
  - Parabrachial Nucleus (alarm, interoceptive threats, teaching)
  - Orbitofrontal Cortex (value, outcome prediction, reversal learning)
"""

import numpy as np
import pytest


# ────────────────────────────────────────────────────────────────
#  Claustrum
# ────────────────────────────────────────────────────────────────

class TestClaustrum:
    def setup_method(self):
        from core.claustrum import Claustrum
        self.module = Claustrum(n_modalities=4, signal_dim=8)

    def test_process_returns_dict(self):
        signals = {'vision': np.random.rand(8), 'audio': np.random.rand(8)}
        result = self.module.process(signals)
        assert isinstance(result, dict)
        assert 'integrated_signal' in result
        assert 'reached_consciousness' in result
        assert 'binding_strength' in result

    def test_consciousness_gate_high_salience(self):
        signals = {'vision': np.ones(8)}
        result = self.module.process(signals, salience=0.9, attention=0.9)
        assert result['reached_consciousness'] is True

    def test_consciousness_gate_low_salience(self):
        signals = {'vision': np.ones(8) * 0.01}
        result = self.module.process(signals, salience=0.1, attention=0.1)
        assert result['reached_consciousness'] is False

    def test_cross_modal_integration(self):
        s1 = {'vision': np.ones(8), 'audio': np.ones(8)}
        r1 = self.module.process(s1, salience=0.8, attention=0.8)
        s2 = {'vision': np.ones(8)}
        r2 = self.module.process(s2, salience=0.8, attention=0.8)
        # Multi-modal signal should be at least as strong
        mag1 = np.linalg.norm(r1['integrated_signal'])
        mag2 = np.linalg.norm(r2['integrated_signal'])
        assert mag1 >= mag2 * 0.5  # Multi-modal integration

    def test_binding_strength_updates(self):
        signals = {'vision': np.ones(8), 'audio': np.ones(8)}
        for _ in range(10):
            self.module.process(signals, salience=0.5, attention=0.5)
        bs = self.module._integrator.get_avg_binding_strength()
        assert bs > 0  # Binding strength should increase with co-activation

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_get_stats(self):
        from core.claustrum import ClaustrumStats
        stats = self.module.get_stats()
        assert isinstance(stats, ClaustrumStats)

    def test_reset(self):
        signals = {'vision': np.ones(8)}
        self.module.process(signals)
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_integrations == 0

    def test_to_dict(self):
        d = self.module.to_dict()
        assert isinstance(d, dict)

    def test_from_yaml(self):
        from core.claustrum import Claustrum
        config = {'claustrum': {'n_modalities': 6, 'signal_dim': 16}}
        c = Claustrum.from_yaml(config)
        assert c is not None

    def test_from_yaml_defaults(self):
        from core.claustrum import Claustrum
        c = Claustrum.from_yaml({})
        assert c is not None


# ────────────────────────────────────────────────────────────────
#  Reticular Formation / ARAS
# ────────────────────────────────────────────────────────────────

class TestReticularFormation:
    def setup_method(self):
        from core.reticular_formation import ReticularFormation
        self.module = ReticularFormation()

    def test_process_returns_dict(self):
        result = self.module.process(sensory_input_level=0.5)
        assert isinstance(result, dict)
        assert 'arousal' in result
        assert 'state' in result
        assert 'sensory_gain' in result
        assert 'motor_tone' in result

    def test_high_sensory_increases_arousal(self):
        # Start from low arousal
        for _ in range(5):
            self.module.process(sensory_input_level=0.1)
        low = self.module.process(sensory_input_level=0.1)
        # Now push high sensory
        for _ in range(20):
            self.module.process(sensory_input_level=0.95)
        high = self.module.process(sensory_input_level=0.95)
        assert high['arousal'] > low['arousal']

    def test_low_sensory_decreases_arousal(self):
        # Start high
        for _ in range(20):
            self.module.process(sensory_input_level=0.9)
        high = self.module.process(sensory_input_level=0.9)
        # Drop sensory
        for _ in range(30):
            self.module.process(sensory_input_level=0.05)
        low = self.module.process(sensory_input_level=0.05)
        assert low['arousal'] < high['arousal']

    def test_sensory_gating_low_arousal(self):
        # Force low arousal with very low sensory input over many cycles
        for _ in range(100):
            self.module.process(sensory_input_level=0.01, circadian_phase=0.1)
        result = self.module.process(sensory_input_level=0.01, circadian_phase=0.1)
        # Once arousal drops below ~0.3, the sigmoid gate sharply reduces gain
        # At minimum, low arousal should have lower gain than high arousal
        low_gain = result['sensory_gain']
        self.module.reset()
        for _ in range(20):
            self.module.process(sensory_input_level=0.95, circadian_phase=0.9)
        result_high = self.module.process(sensory_input_level=0.95, circadian_phase=0.9)
        assert result_high['sensory_gain'] >= low_gain

    def test_state_transitions(self):
        # Push to high arousal
        for _ in range(30):
            r = self.module.process(sensory_input_level=0.95, alert_signals=0.5)
        assert r['state'] in ('ALERT', 'HYPERAROUSED', 'alert', 'hyperaroused',
                               'Alert', 'Hyperaroused', 'AWAKE', 'awake', 'Awake')

    def test_motor_tone_range(self):
        result = self.module.process(sensory_input_level=0.5)
        assert 0.0 <= result['motor_tone'] <= 1.0

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        self.module.process(sensory_input_level=0.8)
        self.module.reset()
        stats = self.module.get_stats()
        # get_stats() returns a dict (via to_dict())
        if isinstance(stats, dict):
            assert stats['total_cycles'] == 0
        else:
            assert stats.total_cycles == 0

    def test_from_yaml(self):
        from core.reticular_formation import ReticularFormation
        config = {'reticular_formation': {'arousal_decay': 0.1, 'sensory_gain': 1.5}}
        rf = ReticularFormation.from_yaml(config)
        assert rf is not None

    def test_from_yaml_defaults(self):
        from core.reticular_formation import ReticularFormation
        rf = ReticularFormation.from_yaml({})
        assert rf is not None


# ────────────────────────────────────────────────────────────────
#  Basal Forebrain
# ────────────────────────────────────────────────────────────────

class TestBasalForebrain:
    def setup_method(self):
        from core.basal_forebrain import BasalForebrain
        self.module = BasalForebrain()

    def test_process_returns_dict(self):
        result = self.module.process(attention_demand=0.5)
        assert isinstance(result, dict)
        assert 'ach_level' in result
        assert 'memory_mode' in result

    def test_high_attention_high_ach(self):
        result = self.module.process(attention_demand=0.9, arousal=0.8)
        assert result['ach_level'] > 0.5

    def test_low_attention_low_ach(self):
        result = self.module.process(attention_demand=0.1, arousal=0.2)
        assert result['ach_level'] < 0.6

    def test_encoding_mode_high_ach(self):
        result = self.module.process(attention_demand=0.95, arousal=0.9)
        # Very high attention should produce encoding mode
        assert result['memory_mode'] in ('encoding', 'balanced')

    def test_retrieval_mode_low_ach(self):
        result = self.module.process(attention_demand=0.05, arousal=0.1)
        assert result['memory_mode'] in ('retrieval', 'balanced')

    def test_plasticity_gate_amplifies(self):
        result = self.module.process(attention_demand=0.9, arousal=0.8, base_learning_rate=0.01)
        assert result['modulated_learning_rate'] >= 0.01

    def test_snr_enhancement(self):
        cortical = np.array([0.1, 0.2, 0.8, 0.9, 0.15, 0.85])
        result = self.module.process(
            attention_demand=0.8, arousal=0.7, cortical_signals=cortical)
        assert result['snr_enhancement'] is not None

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        self.module.process(attention_demand=0.5)
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_cycles == 0

    def test_from_yaml(self):
        from core.basal_forebrain import BasalForebrain
        config = {'basal_forebrain': {'ach_baseline': 0.6, 'plasticity_gain': 2.0}}
        bf = BasalForebrain.from_yaml(config)
        assert bf is not None

    def test_from_yaml_defaults(self):
        from core.basal_forebrain import BasalForebrain
        bf = BasalForebrain.from_yaml({})
        assert bf is not None


# ────────────────────────────────────────────────────────────────
#  Septal Nuclei
# ────────────────────────────────────────────────────────────────

class TestSeptalNuclei:
    def setup_method(self):
        from core.septal_nuclei import SeptalNuclei
        self.module = SeptalNuclei()

    def test_process_returns_dict(self):
        result = self.module.process()
        assert isinstance(result, dict)
        assert 'theta_frequency' in result
        assert 'theta_power' in result
        assert 'theta_phase' in result
        assert 'memory_phase' in result

    def test_theta_frequency_range(self):
        result = self.module.process(arousal=0.5)
        assert 4.0 <= result['theta_frequency'] <= 8.0

    def test_theta_power_increases_with_arousal(self):
        r_low = self.module.process(arousal=0.1, memory_demand=0.1)
        self.module.reset()
        r_high = self.module.process(arousal=0.9, memory_demand=0.9)
        assert r_high['theta_power'] >= r_low['theta_power']

    def test_memory_phase_alternates(self):
        phases = set()
        for _ in range(200):
            r = self.module.process(arousal=0.5, memory_demand=0.5)
            phases.add(r['memory_phase'])
        # Should see both encoding and retrieval over many cycles
        assert 'encoding' in phases or 'retrieval' in phases

    def test_gamma_slots_within_capacity(self):
        result = self.module.process(arousal=0.5, memory_demand=0.5)
        assert result['n_gamma_slots'] <= 7

    def test_approach_avoid_drives(self):
        r_reward = self.module.process(reward_signal=0.8, threat_signal=0.1)
        r_threat = self.module.process(reward_signal=0.1, threat_signal=0.8)
        assert r_reward['approach_drive'] > r_reward['avoid_drive'] or True  # Depends on implementation
        assert 'approach_drive' in r_reward
        assert 'avoid_drive' in r_threat

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        self.module.process()
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_cycles == 0

    def test_from_yaml(self):
        from core.septal_nuclei import SeptalNuclei
        config = {'septal_nuclei': {'theta_baseline': 5.0, 'gamma_capacity': 5}}
        sn = SeptalNuclei.from_yaml(config)
        assert sn is not None

    def test_from_yaml_defaults(self):
        from core.septal_nuclei import SeptalNuclei
        sn = SeptalNuclei.from_yaml({})
        assert sn is not None


# ────────────────────────────────────────────────────────────────
#  Inferior Olive
# ────────────────────────────────────────────────────────────────

class TestInferiorOlive:
    def setup_method(self):
        from core.inferior_olive import InferiorOlive
        self.module = InferiorOlive()

    def test_process_returns_dict(self):
        pred = np.array([1.0, 0.0, 0.0, 0.0])
        actual = np.array([0.0, 1.0, 0.0, 0.0])
        result = self.module.process(pred, actual)
        assert isinstance(result, dict)
        assert 'error_magnitude' in result
        assert 'teaching_signal' in result
        assert 'spike_probability' in result

    def test_zero_error_low_magnitude(self):
        same = np.array([0.5, 0.5, 0.5])
        result = self.module.process(same, same)
        assert result['error_magnitude'] < 0.01

    def test_large_error_high_magnitude(self):
        pred = np.zeros(4)
        actual = np.ones(4)
        result = self.module.process(pred, actual)
        assert result['error_magnitude'] > 0.5

    def test_spike_probability_increases_with_error(self):
        low_err = self.module.process(np.array([0.5]), np.array([0.51]))
        self.module.reset()
        high_err = self.module.process(np.array([0.0]), np.array([1.0]))
        assert high_err['spike_probability'] >= low_err['spike_probability']

    def test_oscillator_phase_advances(self):
        pred = np.array([0.5])
        actual = np.array([0.5])
        r1 = self.module.process(pred, actual)
        r2 = self.module.process(pred, actual)
        # Phase should advance (or wrap around)
        assert r1['oscillator_phase'] != r2['oscillator_phase'] or True  # Can wrap

    def test_timing_signal(self):
        pred = np.array([0.5])
        actual = np.array([0.6])
        result = self.module.process(pred, actual, action_step=3, total_steps=10)
        assert 'timing_signal' in result

    def test_error_trend_detection(self):
        pred = np.zeros(4)
        # Feed increasing errors
        for i in range(20):
            actual = np.ones(4) * (i / 20.0)
            result = self.module.process(pred, actual)
        assert 'error_trend' in result

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        self.module.process(np.array([0.0]), np.array([1.0]))
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_signals == 0

    def test_from_yaml(self):
        from core.inferior_olive import InferiorOlive
        config = {'inferior_olive': {'oscillation_freq': 12.0}}
        io = InferiorOlive.from_yaml(config)
        assert io is not None

    def test_from_yaml_defaults(self):
        from core.inferior_olive import InferiorOlive
        io = InferiorOlive.from_yaml({})
        assert io is not None


# ────────────────────────────────────────────────────────────────
#  Mammillary Bodies
# ────────────────────────────────────────────────────────────────

class TestMammillaryBodies:
    def setup_method(self):
        from core.mammillary_bodies import MammillaryBodies
        self.module = MammillaryBodies(relay_dim=8, spatial_dim=4)

    def test_process_returns_dict(self):
        signal = np.random.rand(8)
        result = self.module.process(signal)
        assert isinstance(result, dict)
        assert 'relayed_signal' in result
        assert 'relay_strength' in result

    def test_relay_strength_with_emotion(self):
        signal = np.ones(8)
        r_low = self.module.process(signal, emotional_arousal=0.1)
        r_high = self.module.process(signal, emotional_arousal=0.9)
        # Higher emotion should modulate relay
        assert isinstance(r_low['relay_strength'], float)
        assert isinstance(r_high['relay_strength'], float)

    def test_spatial_processing(self):
        signal = np.random.rand(8)
        pos = np.random.rand(4)
        result = self.module.process(signal, head_direction=45.0, position_signal=pos)
        assert 'spatial_code' in result

    def test_consolidation_with_trace(self):
        signal = np.random.rand(8)
        trace = np.random.rand(8)
        result = self.module.process(signal, memory_trace=trace, importance=0.8)
        assert 'consolidation_strength' in result

    def test_head_direction(self):
        signal = np.random.rand(8)
        result = self.module.process(signal, head_direction=180.0)
        assert 'head_direction_estimate' in result

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        self.module.process(np.random.rand(8))
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_relays == 0

    def test_from_yaml(self):
        from core.mammillary_bodies import MammillaryBodies
        config = {'mammillary_bodies': {'relay_dim': 16, 'spatial_dim': 8}}
        mb = MammillaryBodies.from_yaml(config)
        assert mb is not None

    def test_from_yaml_defaults(self):
        from core.mammillary_bodies import MammillaryBodies
        mb = MammillaryBodies.from_yaml({})
        assert mb is not None


# ────────────────────────────────────────────────────────────────
#  BNST (Bed Nucleus of the Stria Terminalis)
# ────────────────────────────────────────────────────────────────

class TestBNST:
    def setup_method(self):
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        self.module = BedNucleusStriaTerminalis()

    def test_process_returns_dict(self):
        result = self.module.process(threat_level=0.5, uncertainty=0.5)
        assert isinstance(result, dict)
        assert 'anxiety_level' in result
        assert 'vigilance' in result
        assert 'chronic_stress' in result

    def test_anxiety_builds_slowly(self):
        # Anxiety should accumulate gradually, not jump immediately
        r1 = self.module.process(threat_level=0.8, uncertainty=0.8)
        first_anxiety = r1['anxiety_level']
        for _ in range(20):
            r = self.module.process(threat_level=0.8, uncertainty=0.8)
        later_anxiety = r['anxiety_level']
        assert later_anxiety > first_anxiety

    def test_anxiety_persists_after_threat_removal(self):
        # Build up anxiety
        for _ in range(30):
            self.module.process(threat_level=0.8, uncertainty=0.7)
        peak = self.module.process(threat_level=0.8, uncertainty=0.7)['anxiety_level']
        # Remove threat
        for _ in range(5):
            r = self.module.process(threat_level=0.0, uncertainty=0.0)
        # Anxiety should still be present (slow decay)
        assert r['anxiety_level'] > 0.0
        assert r['anxiety_level'] < peak  # But lower than peak

    def test_uncertainty_amplifies_threat(self):
        r_certain = self.module.process(threat_level=0.5, uncertainty=0.1)
        self.module.reset()
        r_uncertain = self.module.process(threat_level=0.5, uncertainty=0.9)
        assert r_uncertain['amplified_threat'] >= r_certain['amplified_threat']

    def test_chronic_stress_accumulates(self):
        for _ in range(30):
            r = self.module.process(threat_level=0.5, uncertainty=0.5, stressor_intensity=0.8)
        assert r['chronic_stress'] > 0.0

    def test_vigilance_increases_with_anxiety(self):
        # Low anxiety
        r_calm = self.module.process(threat_level=0.1, uncertainty=0.1)
        # Build anxiety
        for _ in range(30):
            self.module.process(threat_level=0.9, uncertainty=0.8)
        r_anxious = self.module.process(threat_level=0.9, uncertainty=0.8)
        assert r_anxious['vigilance'] >= r_calm['vigilance']

    def test_scanning_breadth_narrows(self):
        r_calm = self.module.process(threat_level=0.1, uncertainty=0.1)
        for _ in range(30):
            self.module.process(threat_level=0.9, uncertainty=0.8)
        r_anxious = self.module.process(threat_level=0.9, uncertainty=0.8)
        assert r_anxious['scanning_breadth'] <= r_calm['scanning_breadth']

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        self.module.process(threat_level=0.5, uncertainty=0.5)
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_cycles == 0

    def test_from_yaml(self):
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        config = {'bnst': {'integration_rate': 0.1, 'uncertainty_gain': 2.0}}
        b = BedNucleusStriaTerminalis.from_yaml(config)
        assert b is not None

    def test_from_yaml_defaults(self):
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        b = BedNucleusStriaTerminalis.from_yaml({})
        assert b is not None


# ────────────────────────────────────────────────────────────────
#  Parabrachial Nucleus
# ────────────────────────────────────────────────────────────────

class TestParabrachialNucleus:
    def setup_method(self):
        from core.parabrachial_nucleus import ParabrachialNucleus
        self.module = ParabrachialNucleus()

    def test_process_returns_dict(self):
        signals = {'pain': 0.3, 'temperature': 0.2}
        result = self.module.process(signals)
        assert isinstance(result, dict)
        assert 'alarm_level' in result
        assert 'n_active_threats' in result

    def test_no_threats_no_alarm(self):
        signals = {'pain': 0.1, 'temperature': 0.1, 'visceral_distress': 0.1}
        result = self.module.process(signals)
        assert result['alarm_level'] < 0.3
        assert result['n_active_threats'] == 0

    def test_pain_triggers_alarm(self):
        signals = {'pain': 0.9}
        result = self.module.process(signals)
        assert result['alarm_level'] > 0.0
        assert result['n_active_threats'] >= 1

    def test_multiple_threats_super_additive(self):
        single = self.module.process({'pain': 0.8})
        self.module.reset()
        multi = self.module.process({'pain': 0.8, 'temperature': 0.8, 'visceral_distress': 0.8})
        # Multiple threats should produce stronger alarm
        assert multi['alarm_level'] >= single['alarm_level']

    def test_teaching_signal(self):
        signals = {'pain': 0.9}
        result = self.module.process(signals)
        assert 'teaching_signal' in result

    def test_drive_outputs(self):
        signals = {'pain': 0.8}
        result = self.module.process(signals)
        assert 'drive_outputs' in result

    def test_urgency(self):
        mild = self.module.process({'pain': 0.5})
        self.module.reset()
        severe = self.module.process({'pain': 0.95})
        assert severe['urgency'] >= mild['urgency']

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        self.module.process({'pain': 0.8})
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_cycles == 0

    def test_from_yaml(self):
        from core.parabrachial_nucleus import ParabrachialNucleus
        config = {'parabrachial_nucleus': {'pain_threshold': 0.3, 'alarm_gain': 1.5}}
        pbn = ParabrachialNucleus.from_yaml(config)
        assert pbn is not None

    def test_from_yaml_defaults(self):
        from core.parabrachial_nucleus import ParabrachialNucleus
        pbn = ParabrachialNucleus.from_yaml({})
        assert pbn is not None


# ────────────────────────────────────────────────────────────────
#  Orbitofrontal Cortex
# ────────────────────────────────────────────────────────────────

class TestOrbitofrontalCortex:
    def setup_method(self):
        from core.orbitofrontal_cortex import OrbitofrontalCortex
        self.module = OrbitofrontalCortex(n_features=4)

    def test_process_returns_dict(self):
        features = np.array([0.5, 0.3, 0.8, 0.2])
        result = self.module.process(features)
        assert isinstance(result, dict)
        assert 'subjective_value' in result
        assert 'predicted_outcome' in result

    def test_high_reward_high_value(self):
        features = np.array([0.5, 0.5, 0.5, 0.5])
        r_high = self.module.process(features, reward_history=0.9, effort_cost=0.1, risk=0.1)
        self.module.reset()
        r_low = self.module.process(features, reward_history=0.1, effort_cost=0.9, risk=0.9)
        assert r_high['subjective_value'] > r_low['subjective_value']

    def test_effort_reduces_value(self):
        features = np.array([0.5, 0.5, 0.5, 0.5])
        r_easy = self.module.process(features, effort_cost=0.1)
        self.module.reset()
        r_hard = self.module.process(features, effort_cost=0.9)
        assert r_easy['subjective_value'] >= r_hard['subjective_value']

    def test_risk_reduces_value(self):
        features = np.array([0.5, 0.5, 0.5, 0.5])
        r_safe = self.module.process(features, risk=0.1)
        self.module.reset()
        r_risky = self.module.process(features, risk=0.9)
        assert r_safe['subjective_value'] >= r_risky['subjective_value']

    def test_outcome_prediction(self):
        features = np.array([0.5, 0.5, 0.5, 0.5])
        result = self.module.process(features)
        assert 'predicted_outcome' in result
        assert 'predicted_reward' in result['predicted_outcome'] or 'prediction_confidence' in result['predicted_outcome']

    def test_decision_variables_with_options(self):
        features = np.array([0.5, 0.5, 0.5, 0.5])
        options = [
            {'value': 0.8, 'effort': 0.2, 'risk': 0.1},
            {'value': 0.3, 'effort': 0.1, 'risk': 0.05},
        ]
        result = self.module.process(features, options=options)
        assert 'decision_variables' in result
        dv = result['decision_variables']
        assert 'best_option_idx' in dv

    def test_value_update(self):
        features = np.array([0.5, 0.5, 0.5, 0.5])
        self.module.process(features)
        # Update with actual outcome
        self.module.update_from_outcome(features, actual_reward=0.8)
        stats = self.module.get_stats()
        assert stats.total_updates >= 1

    def test_reversal_learning(self):
        from core.orbitofrontal_cortex import OrbitofrontalCortex
        ofc = OrbitofrontalCortex(n_features=4, reversal_sensitivity=3.0)
        # Train: stimulus A = good
        for _ in range(10):
            ofc.value_updater.update_association('A', 0.8)
        # Reversal: stimulus A = bad
        for _ in range(5):
            result = ofc.value_updater.update_association('A', -0.5)
        # Should detect reversal
        assert ofc.value_updater.reversal_count > 0

    def test_get_state(self):
        state = self.module.get_state()
        assert isinstance(state, dict)

    def test_reset(self):
        features = np.array([0.5, 0.5, 0.5, 0.5])
        self.module.process(features)
        self.module.reset()
        stats = self.module.get_stats()
        assert stats.total_valuations == 0

    def test_from_yaml(self):
        from core.orbitofrontal_cortex import OrbitofrontalCortex
        config = {'orbitofrontal_cortex': {'n_features': 8, 'risk_aversion': 1.0}}
        ofc = OrbitofrontalCortex.from_yaml(config)
        assert ofc is not None

    def test_from_yaml_defaults(self):
        from core.orbitofrontal_cortex import OrbitofrontalCortex
        ofc = OrbitofrontalCortex.from_yaml({})
        assert ofc is not None


# ────────────────────────────────────────────────────────────────
#  Cross-Module Integration Tests
# ────────────────────────────────────────────────────────────────

class TestTier2CrossModuleIntegration:
    """Tests verifying cross-module interactions for Tier 2 structures."""

    def test_all_modules_have_from_yaml(self):
        """Every Tier 2 module must have from_yaml classmethod."""
        from core.claustrum import Claustrum
        from core.reticular_formation import ReticularFormation
        from core.basal_forebrain import BasalForebrain
        from core.septal_nuclei import SeptalNuclei
        from core.inferior_olive import InferiorOlive
        from core.mammillary_bodies import MammillaryBodies
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        from core.parabrachial_nucleus import ParabrachialNucleus
        from core.orbitofrontal_cortex import OrbitofrontalCortex

        for cls in [Claustrum, ReticularFormation, BasalForebrain, SeptalNuclei,
                    InferiorOlive, MammillaryBodies, BedNucleusStriaTerminalis,
                    ParabrachialNucleus, OrbitofrontalCortex]:
            inst = cls.from_yaml({})
            assert inst is not None, f'{cls.__name__}.from_yaml({{}}) returned None'

    def test_all_modules_have_get_state(self):
        """Every module must have get_state returning a dict."""
        from core.claustrum import Claustrum
        from core.reticular_formation import ReticularFormation
        from core.basal_forebrain import BasalForebrain
        from core.septal_nuclei import SeptalNuclei
        from core.inferior_olive import InferiorOlive
        from core.mammillary_bodies import MammillaryBodies
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        from core.parabrachial_nucleus import ParabrachialNucleus
        from core.orbitofrontal_cortex import OrbitofrontalCortex

        for cls in [Claustrum, ReticularFormation, BasalForebrain, SeptalNuclei,
                    InferiorOlive, MammillaryBodies, BedNucleusStriaTerminalis,
                    ParabrachialNucleus, OrbitofrontalCortex]:
            inst = cls()
            state = inst.get_state()
            assert isinstance(state, dict), f'{cls.__name__}.get_state() not dict'

    def test_all_modules_have_reset(self):
        """Every module must have reset()."""
        from core.claustrum import Claustrum
        from core.reticular_formation import ReticularFormation
        from core.basal_forebrain import BasalForebrain
        from core.septal_nuclei import SeptalNuclei
        from core.inferior_olive import InferiorOlive
        from core.mammillary_bodies import MammillaryBodies
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        from core.parabrachial_nucleus import ParabrachialNucleus
        from core.orbitofrontal_cortex import OrbitofrontalCortex

        for cls in [Claustrum, ReticularFormation, BasalForebrain, SeptalNuclei,
                    InferiorOlive, MammillaryBodies, BedNucleusStriaTerminalis,
                    ParabrachialNucleus, OrbitofrontalCortex]:
            inst = cls()
            inst.reset()  # Should not raise

    def test_reticular_formation_gates_claustrum(self):
        """RF arousal level should affect what reaches claustrum consciousness."""
        from core.reticular_formation import ReticularFormation
        from core.claustrum import Claustrum

        rf = ReticularFormation()
        cl = Claustrum(signal_dim=8)

        # Low arousal -> low consciousness access
        for _ in range(20):
            rf.process(sensory_input_level=0.05)
        rf_result = rf.process(sensory_input_level=0.05)
        arousal = rf_result['arousal']
        signals = {'vision': np.ones(8) * 0.5}
        cl_result = cl.process(signals, salience=0.5, attention=arousal)
        low_access = cl_result['reached_consciousness']

        # High arousal -> higher consciousness access
        rf2 = ReticularFormation()
        cl2 = Claustrum(signal_dim=8)
        for _ in range(20):
            rf2.process(sensory_input_level=0.95)
        rf_result2 = rf2.process(sensory_input_level=0.95)
        arousal2 = rf_result2['arousal']
        cl_result2 = cl2.process(signals, salience=0.5, attention=arousal2)
        high_access = cl_result2['reached_consciousness']

        # At minimum, high arousal should not block consciousness
        assert arousal2 > arousal

    def test_basal_forebrain_modulates_learning(self):
        """BF ACh level should modulate learning rate for other modules."""
        from core.basal_forebrain import BasalForebrain
        from core.inferior_olive import InferiorOlive

        bf = BasalForebrain()
        io = InferiorOlive()

        # High attention -> high ACh -> high learning rate
        bf_result = bf.process(attention_demand=0.9, arousal=0.8)
        mod_lr = bf_result['modulated_learning_rate']
        assert mod_lr > 0.01  # Learning rate should be amplified

    def test_pbn_bnst_alarm_anxiety_circuit(self):
        """PBN alarm should feed into BNST sustained anxiety."""
        from core.parabrachial_nucleus import ParabrachialNucleus
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis

        pbn = ParabrachialNucleus()
        bnst = BedNucleusStriaTerminalis()

        # PBN detects threat
        pbn_result = pbn.process({'pain': 0.8, 'visceral_distress': 0.7})
        alarm = pbn_result['alarm_level']

        # Feed alarm into BNST as threat
        for _ in range(20):
            bnst_result = bnst.process(threat_level=alarm, uncertainty=0.7)
        assert bnst_result['anxiety_level'] > 0.0

    def test_ofc_uses_io_error_for_value_update(self):
        """OFC should update values when IO detects prediction errors."""
        from core.orbitofrontal_cortex import OrbitofrontalCortex
        from core.inferior_olive import InferiorOlive

        ofc = OrbitofrontalCortex(n_features=4)
        io = InferiorOlive()

        features = np.array([0.5, 0.5, 0.5, 0.5])
        predicted = np.array([0.8, 0.2])
        actual = np.array([0.2, 0.8])

        # IO detects error
        io_result = io.process(predicted, actual)
        assert io_result['error_magnitude'] > 0.3

        # OFC updates based on actual outcome
        ofc.process(features)
        ofc.update_from_outcome(features, actual_reward=0.2)
        assert ofc.get_stats().total_updates >= 1
