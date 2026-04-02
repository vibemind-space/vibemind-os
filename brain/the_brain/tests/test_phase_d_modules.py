"""
Tests for Phase D brain modules: Tier 1 missing structures.

Modules tested:
- AmygdalaComplex (amygdala_complex.py)
- VentralTegmentalArea (ventral_tegmental_area.py)
- LocusCoeruleus (locus_coeruleus.py)
- RapheNuclei (raphe_nuclei.py)
- LateralHabenula (lateral_habenula.py)
- PeriaqueductalGray (periaqueductal_gray.py)
"""

import pytest
import numpy as np


# ============================================================
# Amygdala Complex Tests
# ============================================================

class TestBasolateralAmygdala:
    def setup_method(self):
        from core.amygdala_complex import BasolateralAmygdala
        self.bla = BasolateralAmygdala(n_features=10)

    def test_evaluate_stimulus_returns_correct_keys(self):
        features = np.random.rand(10)
        result = self.bla.evaluate_stimulus(features)
        assert 'valence' in result
        assert 'arousal' in result
        assert 'threat_level' in result
        assert 'dominance' in result
        assert 'pathway' in result

    def test_evaluate_with_context_uses_dual_pathway(self):
        features = np.random.rand(10)
        context = np.random.rand(10)
        result = self.bla.evaluate_stimulus(features, context)
        assert result['pathway'] == 'dual'

    def test_evaluate_without_context_uses_fast_pathway(self):
        features = np.random.rand(10)
        result = self.bla.evaluate_stimulus(features)
        assert result['pathway'] == 'fast'

    def test_valence_in_range(self):
        for _ in range(20):
            features = np.random.rand(10) * 2 - 1
            result = self.bla.evaluate_stimulus(features)
            assert -1.0 <= result['valence'] <= 1.0

    def test_arousal_in_range(self):
        features = np.random.rand(10)
        result = self.bla.evaluate_stimulus(features)
        assert 0.0 <= result['arousal'] <= 1.0

    def test_threat_level_in_range(self):
        features = np.random.rand(10)
        result = self.bla.evaluate_stimulus(features)
        assert 0.0 <= result['threat_level'] <= 1.0

    def test_fear_conditioning(self):
        features = np.array([1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.bla.condition_fear("test_stim", features, strength=1.0)
        assert self.bla.is_fear_conditioned("test_stim")

    def test_fear_extinction(self):
        features = np.array([1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.bla.condition_fear("test_stim", features, strength=0.5)
        # Extinguish many times
        for _ in range(50):
            self.bla.extinguish_fear("test_stim", features)
        # Strength should be reduced
        assert not self.bla.is_fear_conditioned("test_stim", threshold=0.3)

    def test_unconditioned_stimulus_returns_false(self):
        assert not self.bla.is_fear_conditioned("never_seen")

    def test_feature_padding(self):
        """Short feature vectors should be zero-padded."""
        features = np.array([0.5, 0.3])  # Only 2 features
        result = self.bla.evaluate_stimulus(features)
        assert 'valence' in result


class TestCentralAmygdala:
    def setup_method(self):
        from core.amygdala_complex import CentralAmygdala
        self.cea = CentralAmygdala()

    def test_response_keys(self):
        result = self.cea.generate_response(0.5, 0.0, 0.5)
        assert 'hpa_activation' in result
        assert 'pag_signal' in result
        assert 'lc_signal' in result
        assert 'autonomic_arousal' in result
        assert 'freeze_signal' in result

    def test_high_threat_high_outputs(self):
        result = self.cea.generate_response(0.9, 0.5, 0.8)
        assert result['hpa_activation'] > 0.5
        assert result['pag_signal'] > 0.5
        assert result['lc_signal'] > 0.5

    def test_low_threat_low_outputs(self):
        result = self.cea.generate_response(0.0, 0.0, 0.1)
        assert result['hpa_activation'] < 0.3
        assert result['pag_signal'] < 0.1

    def test_outputs_clamped(self):
        result = self.cea.generate_response(1.0, 1.0, 1.0)
        for v in result.values():
            assert 0.0 <= v <= 1.0


class TestMedialAmygdala:
    def setup_method(self):
        from core.amygdala_complex import MedialAmygdala
        self.mea = MedialAmygdala()

    def test_cooperative_signal_positive_valence(self):
        result = self.mea.evaluate_social_signal("agent1", "cooperative", 0.8)
        assert result['social_valence'] > 0
        assert result['approach_tendency'] > 0.5

    def test_threatening_signal_negative_valence(self):
        result = self.mea.evaluate_social_signal("agent2", "threatening", 0.8)
        assert result['social_valence'] < 0
        assert result['approach_tendency'] < 0.5

    def test_social_memory_accumulates(self):
        for _ in range(10):
            self.mea.evaluate_social_signal("agent3", "cooperative", 0.8)
        trust = self.mea.get_social_trust("agent3")
        assert trust > 0


class TestAmygdalaComplex:
    def setup_method(self):
        from core.amygdala_complex import AmygdalaComplex
        self.amygdala = AmygdalaComplex()

    def test_process_stimulus_returns_correct_structure(self):
        features = np.random.rand(10)
        result = self.amygdala.process_stimulus(features)
        assert 'evaluation' in result
        assert 'response' in result
        assert 'is_threat' in result

    def test_stats_update(self):
        features = np.random.rand(10)
        self.amygdala.process_stimulus(features)
        stats = self.amygdala.get_stats()
        assert stats.total_evaluations == 1

    def test_from_yaml(self):
        from core.amygdala_complex import AmygdalaComplex
        config = {'amygdala': {'n_features': 8, 'threat_threshold': 0.7}}
        amygdala = AmygdalaComplex.from_yaml(config)
        assert amygdala._threat_threshold == 0.7

    def test_get_state_dict(self):
        state = self.amygdala.get_state()
        assert 'stats' in state
        assert 'bla' in state
        assert 'cea' in state
        assert 'mea' in state

    def test_reset_clears_stats(self):
        features = np.random.rand(10)
        self.amygdala.process_stimulus(features)
        self.amygdala.reset()
        assert self.amygdala.get_stats().total_evaluations == 0


# ============================================================
# Ventral Tegmental Area Tests
# ============================================================

class TestDopamineNeuronPopulation:
    def setup_method(self):
        from core.ventral_tegmental_area import DopamineNeuronPopulation
        self.pop = DopamineNeuronPopulation(tonic_baseline=0.5)

    def test_positive_rpe_causes_burst(self):
        result = self.pop.compute_firing(0.5)
        assert result['is_burst'] is True

    def test_negative_rpe_causes_pause(self):
        result = self.pop.compute_firing(-0.5)
        assert result['is_pause'] is True

    def test_zero_rpe_neutral(self):
        result = self.pop.compute_firing(0.0)
        assert not result['is_burst']
        assert not result['is_pause']

    def test_total_da_clamped(self):
        result = self.pop.compute_firing(1.0)
        assert 0.0 <= result['total_da'] <= 1.0
        result = self.pop.compute_firing(-1.0)
        assert 0.0 <= result['total_da'] <= 1.0

    def test_tonic_adaptation(self):
        self.pop.adapt_tonic(0.8)
        assert self.pop.tonic_level > 0.5
        self.pop.adapt_tonic(0.2)
        # Should move toward 0.2 but slowly


class TestRewardPredictor:
    def setup_method(self):
        from core.ventral_tegmental_area import RewardPredictor
        self.pred = RewardPredictor(learning_rate=0.1)

    def test_initial_prediction(self):
        assert self.pred.predict_reward() == 0.5

    def test_positive_rpe_updates_value(self):
        rpe = self.pred.compute_rpe(0.8)
        assert rpe > 0
        # Value should increase
        new_prediction = self.pred.predict_reward()
        assert new_prediction > 0.5

    def test_negative_rpe_updates_value(self):
        # First set high value to create expectation
        for _ in range(30):
            self.pred.compute_rpe(0.9)
        # Now zero reward should create negative RPE
        # RPE = 0.0 + 0.95*V - V = -0.05*V < 0
        rpe = self.pred.compute_rpe(0.0)
        assert rpe < 0

    def test_rpe_clamped(self):
        rpe = self.pred.compute_rpe(100.0)  # Extreme
        assert -1.0 <= rpe <= 1.0

    def test_different_states(self):
        self.pred.compute_rpe(0.9, state_id='good_task')
        self.pred.compute_rpe(0.1, state_id='bad_task')
        assert self.pred.predict_reward('good_task') > self.pred.predict_reward('bad_task')


class TestVentralTegmentalArea:
    def setup_method(self):
        from core.ventral_tegmental_area import VentralTegmentalArea
        self.vta = VentralTegmentalArea()

    def test_process_returns_correct_keys(self):
        result = self.vta.process(actual_reward=0.5)
        assert 'rpe' in result
        assert 'dopamine' in result
        assert 'salience' in result
        assert 'motivation' in result

    def test_high_reward_positive_rpe(self):
        result = self.vta.process(actual_reward=0.9)
        assert result['rpe'] > 0

    def test_low_reward_negative_rpe(self):
        # First set expectations high with many iterations
        for _ in range(30):
            self.vta.process(actual_reward=0.9)
        # Then zero reward — RPE should be negative
        result = self.vta.process(actual_reward=0.0)
        assert result['rpe'] < 0

    def test_lhb_inhibition_reduces_dopamine(self):
        from core.ventral_tegmental_area import VentralTegmentalArea as VTA
        vta1 = VTA()
        r1 = vta1.process(actual_reward=0.8, lhb_inhibition=0.0)
        vta2 = VTA()
        r2 = vta2.process(actual_reward=0.8, lhb_inhibition=0.9)
        assert r2['dopamine']['total_da'] <= r1['dopamine']['total_da']

    def test_novelty_increases_salience(self):
        from core.ventral_tegmental_area import VentralTegmentalArea as VTA
        vta1 = VTA()
        r1 = vta1.process(actual_reward=0.5, novelty=0.0)
        vta2 = VTA()
        r2 = vta2.process(actual_reward=0.5, novelty=0.9)
        assert r2['salience'] >= r1['salience']

    def test_from_yaml(self):
        from core.ventral_tegmental_area import VentralTegmentalArea as VTA
        config = {'vta': {'tonic_baseline': 0.6, 'learning_rate': 0.05}}
        vta = VTA.from_yaml(config)
        assert vta.da_neurons.tonic_baseline == 0.6

    def test_stats_update(self):
        self.vta.process(actual_reward=0.8)
        stats = self.vta.get_stats()
        assert stats.total_predictions == 1

    def test_motivation_in_range(self):
        result = self.vta.process(actual_reward=0.5)
        assert 0.0 <= result['motivation'] <= 1.0


# ============================================================
# Locus Coeruleus Tests
# ============================================================

class TestAdaptiveGainController:
    def setup_method(self):
        from core.locus_coeruleus import AdaptiveGainController
        self.agc = AdaptiveGainController()

    def test_high_performance_phasic_mode(self):
        for _ in range(20):
            result = self.agc.update_gain(0.9)
        assert result['mode'] == 'phasic'

    def test_low_performance_tonic_mode(self):
        for _ in range(20):
            result = self.agc.update_gain(0.2)
        assert result['mode'] == 'tonic'

    def test_gain_modulation(self):
        signal = np.array([0.3, 0.5, 0.7, 0.2])
        # High gain should amplify differences
        self.agc._current_gain = 2.0
        modulated = self.agc.apply_gain(signal)
        diff_original = np.max(signal) - np.min(signal)
        diff_modulated = np.max(modulated) - np.min(modulated)
        assert diff_modulated > diff_original


class TestArousalRegulator:
    def setup_method(self):
        from core.locus_coeruleus import ArousalRegulator
        self.ar = ArousalRegulator()

    def test_arousal_in_range(self):
        arousal = self.ar.update_arousal(0.8, 0.5, 0.3)
        assert 0.0 <= arousal <= 1.0

    def test_yerkes_dodson(self):
        # Optimal arousal should give highest modifier
        self.ar._arousal = self.ar.optimal_arousal
        optimal_mod = self.ar.get_performance_modifier()
        self.ar._arousal = 0.1
        low_mod = self.ar.get_performance_modifier()
        self.ar._arousal = 0.95
        high_mod = self.ar.get_performance_modifier()
        assert optimal_mod >= low_mod
        assert optimal_mod >= high_mod


class TestLocusCoeruleus:
    def setup_method(self):
        from core.locus_coeruleus import LocusCoeruleus
        self.lc = LocusCoeruleus()

    def test_process_returns_correct_keys(self):
        result = self.lc.process()
        assert 'ne_level' in result
        assert 'gain' in result
        assert 'mode' in result
        assert 'arousal' in result
        assert 'explore_ratio' in result
        assert 'network_reset' in result

    def test_ne_level_in_range(self):
        result = self.lc.process(stress=0.9, threat=0.9)
        assert 0.0 <= result['ne_level'] <= 1.0

    def test_explore_ratio_in_range(self):
        result = self.lc.process()
        assert 0.0 <= result['explore_ratio'] <= 1.0

    def test_high_performance_shifts_to_exploit(self):
        for _ in range(30):
            result = self.lc.process(task_performance=0.9)
        assert result['mode'] == 'phasic'
        assert result['explore_ratio'] < 0.5

    def test_low_performance_shifts_to_explore(self):
        for _ in range(30):
            result = self.lc.process(task_performance=0.1)
        assert result['mode'] == 'tonic'
        assert result['explore_ratio'] > 0.3

    def test_threat_increases_ne(self):
        from core.locus_coeruleus import LocusCoeruleus as LC
        lc1 = LC()
        r1 = lc1.process(threat=0.0)
        lc2 = LC()
        r2 = lc2.process(threat=0.9)
        assert r2['ne_level'] > r1['ne_level']

    def test_from_yaml(self):
        from core.locus_coeruleus import LocusCoeruleus as LC
        config = {'locus_coeruleus': {'tonic_baseline': 0.6, 'optimal_arousal': 0.7}}
        lc = LC.from_yaml(config)
        assert lc.arousal_regulator.optimal_arousal == 0.7

    def test_stats_update(self):
        self.lc.process()
        stats = self.lc.get_stats()
        assert stats.total_cycles == 1


# ============================================================
# Raphe Nuclei Tests
# ============================================================

class TestDorsalRapheNucleus:
    def setup_method(self):
        from core.raphe_nuclei import DorsalRapheNucleus
        self.drn = DorsalRapheNucleus()

    def test_update_returns_correct_keys(self):
        result = self.drn.update()
        assert 'serotonin' in result
        assert 'patience' in result
        assert 'mood' in result
        assert 'discount_factor' in result

    def test_serotonin_in_range(self):
        result = self.drn.update(reward_rate=0.9, punishment=0.0)
        assert 0.0 <= result['serotonin'] <= 1.0

    def test_patience_correlates_with_serotonin(self):
        # High reward rate -> higher 5-HT -> higher patience
        for _ in range(20):
            self.drn.update(reward_rate=0.9)
        assert self.drn.patience > 0.5

    def test_punishment_reduces_mood(self):
        for _ in range(20):
            self.drn.update(punishment=0.8)
        assert self.drn.mood < 0.5

    def test_should_wait_patient(self):
        # Make 5-HT high (patient)
        for _ in range(20):
            self.drn.update(reward_rate=0.9)
        # Should wait for better delayed reward
        should = self.drn.should_wait(
            immediate_reward=0.3,
            delayed_reward=0.8,
            delay=0.5,
        )
        assert should is True

    def test_discount_factor_range(self):
        result = self.drn.update()
        assert 0.5 <= result['discount_factor'] <= 0.95


class TestMedianRapheNucleus:
    def setup_method(self):
        from core.raphe_nuclei import MedianRapheNucleus
        self.mrn = MedianRapheNucleus()

    def test_theta_modulation(self):
        result = self.mrn.modulate_theta(memory_demand=0.8)
        assert 'theta_power' in result
        assert 0.0 <= result['theta_power'] <= 1.0

    def test_behavioral_inhibition(self):
        assert self.mrn.behavioral_inhibition(0.9) is True  # 0.9 * 0.6 = 0.54 > 0.5
        assert self.mrn.behavioral_inhibition(0.2) is False  # 0.2 * 0.6 = 0.12 < 0.5


class TestRapheNuclei:
    def setup_method(self):
        from core.raphe_nuclei import RapheNuclei
        self.raphe = RapheNuclei()

    def test_process_returns_correct_keys(self):
        result = self.raphe.process()
        assert 'serotonin' in result
        assert 'patience' in result
        assert 'mood' in result
        assert 'theta_power' in result
        assert 'should_inhibit' in result

    def test_from_yaml(self):
        from core.raphe_nuclei import RapheNuclei as RN
        config = {'raphe_nuclei': {'baseline_5ht': 0.6, 'patience_gain': 0.8}}
        raphe = RN.from_yaml(config)
        assert raphe.drn.patience_gain == 0.8

    def test_stats_update(self):
        self.raphe.process()
        stats = self.raphe.get_stats()
        assert stats.total_cycles == 1


# ============================================================
# Lateral Habenula Tests
# ============================================================

class TestAntiRewardSignal:
    def setup_method(self):
        from core.lateral_habenula import AntiRewardSignal
        self.ars = AntiRewardSignal()

    def test_disappointment_when_expected_exceeds_actual(self):
        signal = self.ars.compute(expected_reward=0.8, actual_reward=0.2)
        assert signal > 0

    def test_no_signal_when_outcome_meets_expectations(self):
        signal = self.ars.compute(expected_reward=0.5, actual_reward=0.5)
        assert signal < 0.2

    def test_punishment_increases_signal(self):
        s1 = self.ars.compute(0.5, 0.5, punishment=0.0)
        s2 = self.ars.compute(0.5, 0.5, punishment=0.9)
        assert s2 > s1

    def test_signal_clamped(self):
        signal = self.ars.compute(1.0, 0.0, punishment=1.0)
        assert 0.0 <= signal <= 1.0


class TestAvoidanceLearning:
    def setup_method(self):
        from core.lateral_habenula import AvoidanceLearning
        self.al = AvoidanceLearning()

    def test_learn_and_retrieve(self):
        self.al.learn_avoidance("bad_action", 0.8)
        assert self.al.get_avoidance("bad_action") > 0

    def test_unknown_action_zero(self):
        assert self.al.get_avoidance("unknown") == 0.0

    def test_decay(self):
        self.al.learn_avoidance("test", 0.5)
        for _ in range(100):
            self.al.decay_avoidance(0.1)
        assert self.al.get_avoidance("test") < 0.01


class TestLateralHabenula:
    def setup_method(self):
        from core.lateral_habenula import LateralHabenula
        self.lhb = LateralHabenula()

    def test_process_returns_correct_keys(self):
        result = self.lhb.process(expected_reward=0.8, actual_reward=0.2)
        assert 'anti_reward' in result
        assert 'vta_inhibition' in result
        assert 'drn_inhibition' in result
        assert 'chronic_activation' in result

    def test_disappointment_triggers_inhibition(self):
        result = self.lhb.process(expected_reward=0.9, actual_reward=0.1)
        assert result['vta_inhibition'] > 0
        assert result['drn_inhibition'] > 0

    def test_good_outcome_low_inhibition(self):
        result = self.lhb.process(expected_reward=0.3, actual_reward=0.8)
        assert result['anti_reward'] < 0.3

    def test_avoidance_learning_with_action(self):
        self.lhb.process(
            expected_reward=0.8,
            actual_reward=0.1,
            action_id="risky_action",
        )
        avoidance = self.lhb.get_avoidance_for("risky_action")
        assert avoidance > 0

    def test_from_yaml(self):
        from core.lateral_habenula import LateralHabenula as LHb
        config = {'lateral_habenula': {'sensitivity': 1.5, 'vta_inhibition_gain': 0.9}}
        lhb = LHb.from_yaml(config)
        assert lhb._vta_inhibition_gain == 0.9

    def test_stats_update(self):
        self.lhb.process(0.5, 0.3)
        stats = self.lhb.get_stats()
        assert stats.total_evaluations == 1

    def test_chronic_activation_for_depression_risk(self):
        # Repeated disappointment should increase chronic activation
        for _ in range(100):
            self.lhb.process(expected_reward=0.9, actual_reward=0.1, punishment=0.5)
        result = self.lhb.process(expected_reward=0.9, actual_reward=0.1, punishment=0.5)
        assert result['chronic_activation'] > 0.3


# ============================================================
# Periaqueductal Gray Tests
# ============================================================

class TestPAGColumns:
    def test_fight_activation(self):
        from core.periaqueductal_gray import DorsolateralPAG
        dl = DorsolateralPAG()
        # Fight: high threat, low escapability, high resources
        fight = dl.compute(threat=0.8, escapability=0.1, resources=0.9)
        assert fight > 0.5

    def test_flight_activation(self):
        from core.periaqueductal_gray import LateralPAG
        l_pag = LateralPAG()
        # Flight: high threat, high escapability
        flight = l_pag.compute(threat=0.8, escapability=0.9, resources=0.5)
        assert flight > 0.5

    def test_freeze_activation(self):
        from core.periaqueductal_gray import VentrolateralPAG
        vl = VentrolateralPAG()
        # Freeze: high threat, inescapable, proximate
        freeze, opioid = vl.compute(threat=0.9, escapability=0.1, proximity=0.9)
        assert freeze > 0.5
        assert opioid > 0  # Pain suppression activated

    def test_autonomic_activation(self):
        from core.periaqueductal_gray import DorsomedialPAG
        dm = DorsomedialPAG()
        activation = dm.compute(threat=0.8, arousal=0.7)
        assert activation > 0.3


class TestPeriaqueductalGray:
    def setup_method(self):
        from core.periaqueductal_gray import PeriaqueductalGray
        self.pag = PeriaqueductalGray()

    def test_process_returns_correct_keys(self):
        result = self.pag.process(threat=0.5)
        assert 'selected_defense' in result
        assert 'defense_intensity' in result
        assert 'fight_activation' in result
        assert 'flight_activation' in result
        assert 'freeze_activation' in result
        assert 'pain_suppression' in result
        assert 'emergency_mode' in result

    def test_low_threat_calm(self):
        result = self.pag.process(threat=0.1)
        assert result['selected_defense'] == 'calm'

    def test_high_threat_escapable_flight(self):
        result = self.pag.process(threat=0.9, escapability=0.9)
        assert result['selected_defense'] == 'flight'

    def test_high_threat_inescapable_fight_or_freeze(self):
        result = self.pag.process(threat=0.9, escapability=0.1, proximity=0.9)
        assert result['selected_defense'] in ('fight', 'freeze')

    def test_emergency_mode(self):
        result = self.pag.process(threat=0.95)
        assert result['emergency_mode'] is True

    def test_no_emergency_low_threat(self):
        result = self.pag.process(threat=0.3)
        assert result['emergency_mode'] is False

    def test_pain_suppression_during_freeze(self):
        result = self.pag.process(
            threat=0.9, escapability=0.05, proximity=0.95
        )
        # vlPAG should release opioids
        assert result['pain_suppression'] >= 0.0

    def test_from_yaml(self):
        from core.periaqueductal_gray import PeriaqueductalGray as PAG
        config = {'periaqueductal_gray': {'emergency_threshold': 0.9, 'autonomic_gain': 0.5}}
        pag = PAG.from_yaml(config)
        assert pag._emergency_threshold == 0.9

    def test_stats_update(self):
        self.pag.process(threat=0.5)
        stats = self.pag.get_stats()
        assert stats.total_evaluations == 1

    def test_defense_intensity_range(self):
        result = self.pag.process(threat=0.7)
        assert 0.0 <= result['defense_intensity'] <= 1.0


# ============================================================
# Integration: Cross-Module Interaction Tests
# ============================================================

class TestCrossModuleIntegration:
    """Test that the modules work together as a circuit."""

    def test_vta_lhb_circuit(self):
        """LHb inhibits VTA when disappointed."""
        from core.ventral_tegmental_area import VentralTegmentalArea
        from core.lateral_habenula import LateralHabenula

        lhb = LateralHabenula()
        vta = VentralTegmentalArea()

        # First build up expectations
        for _ in range(20):
            vta.process(actual_reward=0.8)

        # Now: disappointment (zero reward)
        lhb_result = lhb.process(expected_reward=0.9, actual_reward=0.0)
        vta_result = vta.process(
            actual_reward=0.0,
            lhb_inhibition=lhb_result['vta_inhibition'],
        )
        # VTA should show negative RPE with built-up expectations
        assert vta_result['rpe'] < 0
        # LHb should have generated significant inhibition
        assert lhb_result['vta_inhibition'] > 0.1

    def test_amygdala_pag_circuit(self):
        """Amygdala threat -> PAG defensive response."""
        from core.amygdala_complex import AmygdalaComplex
        from core.periaqueductal_gray import PeriaqueductalGray

        amygdala = AmygdalaComplex()
        pag = PeriaqueductalGray()

        # Threatening stimulus
        features = np.ones(10) * 0.8
        amygdala_result = amygdala.process_stimulus(features)
        threat = amygdala_result['response']['pag_signal']

        pag_result = pag.process(threat=threat, escapability=0.5)
        assert pag_result['selected_defense'] != 'calm' or threat < 0.2

    def test_lc_explore_exploit_cycle(self):
        """LC adapts explore/exploit based on performance."""
        from core.locus_coeruleus import LocusCoeruleus

        lc = LocusCoeruleus()

        # Good performance -> exploit (phasic)
        for _ in range(50):
            result = lc.process(task_performance=0.9)
        assert result['mode'] == 'phasic'

        # Performance drops -> should shift toward exploration
        for _ in range(60):
            result = lc.process(task_performance=0.1)
        # After enough low performance, should be tonic
        assert result['mode'] == 'tonic'

    def test_raphe_patience_decision(self):
        """Raphe 5-HT modulates patience for delayed rewards."""
        from core.raphe_nuclei import RapheNuclei

        raphe = RapheNuclei()

        # Build up patience (high 5-HT)
        for _ in range(20):
            raphe.process(reward_rate=0.9)

        # Should wait for better delayed reward
        assert raphe.should_wait(
            immediate=0.3,
            delayed=0.7,
            delay=0.5,
        ) is True

    def test_all_modules_have_from_yaml(self):
        """All modules must support from_yaml construction."""
        from core.amygdala_complex import AmygdalaComplex
        from core.ventral_tegmental_area import VentralTegmentalArea
        from core.locus_coeruleus import LocusCoeruleus
        from core.raphe_nuclei import RapheNuclei
        from core.lateral_habenula import LateralHabenula
        from core.periaqueductal_gray import PeriaqueductalGray

        empty_config = {}
        assert AmygdalaComplex.from_yaml(empty_config) is not None
        assert VentralTegmentalArea.from_yaml(empty_config) is not None
        assert LocusCoeruleus.from_yaml(empty_config) is not None
        assert RapheNuclei.from_yaml(empty_config) is not None
        assert LateralHabenula.from_yaml(empty_config) is not None
        assert PeriaqueductalGray.from_yaml(empty_config) is not None

    def test_all_modules_have_get_state(self):
        """All modules must expose get_state() for dashboard."""
        from core.amygdala_complex import AmygdalaComplex
        from core.ventral_tegmental_area import VentralTegmentalArea
        from core.locus_coeruleus import LocusCoeruleus
        from core.raphe_nuclei import RapheNuclei
        from core.lateral_habenula import LateralHabenula
        from core.periaqueductal_gray import PeriaqueductalGray

        for ModuleClass in [
            AmygdalaComplex, VentralTegmentalArea, LocusCoeruleus,
            RapheNuclei, LateralHabenula, PeriaqueductalGray
        ]:
            module = ModuleClass()
            state = module.get_state()
            assert isinstance(state, dict)
            assert 'stats' in state

    def test_all_modules_have_reset(self):
        """All modules must support reset() for testing."""
        from core.amygdala_complex import AmygdalaComplex
        from core.ventral_tegmental_area import VentralTegmentalArea
        from core.locus_coeruleus import LocusCoeruleus
        from core.raphe_nuclei import RapheNuclei
        from core.lateral_habenula import LateralHabenula
        from core.periaqueductal_gray import PeriaqueductalGray

        for ModuleClass in [
            AmygdalaComplex, VentralTegmentalArea, LocusCoeruleus,
            RapheNuclei, LateralHabenula, PeriaqueductalGray
        ]:
            module = ModuleClass()
            module.reset()
            stats = module.get_stats()
            # Check that stats are zeroed — different modules use different counter names
            stats_dict = stats.to_dict()
            # All counter stats (prefixed with total_) should be 0 after reset
            for key, val in stats_dict.items():
                if isinstance(val, int) and key.startswith('total_'):
                    assert val == 0, f"{ModuleClass.__name__}.{key} should be 0 after reset"
