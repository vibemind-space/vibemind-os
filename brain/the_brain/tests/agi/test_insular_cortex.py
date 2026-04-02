"""
Insular Cortex Tests - Phase B2

Tests for interoception, salience detection, subjective feelings,
body budget, network switching, and full insular cortex integration.
"""

import pytest
import numpy as np


@pytest.fixture
def insular():
    from core.insular_cortex import InsularCortex
    return InsularCortex(salience_threshold=0.5)


class TestInteroceptiveProcessor:

    def test_update(self):
        from core.insular_cortex import InteroceptiveProcessor
        ip = InteroceptiveProcessor(n_channels=6)
        deviation = ip.update(np.array([0.8, 0.2, 0.5, 0.6, 0.4, 0.3]))
        assert deviation.shape == (6,)

    def test_deviation_tracking(self):
        from core.insular_cortex import InteroceptiveProcessor
        ip = InteroceptiveProcessor(n_channels=6)
        ip.update(np.array([0.9, 0.1, 0.5, 0.5, 0.5, 0.5]))
        dev = ip.get_deviation()
        assert dev > 0

    def test_baseline_adaptation(self):
        from core.insular_cortex import InteroceptiveProcessor
        ip = InteroceptiveProcessor(n_channels=4)
        for _ in range(100):
            ip.update(np.array([0.8, 0.8, 0.8, 0.8]))
        # Baseline should drift toward 0.8
        assert ip._baseline[0] > 0.5


class TestSalienceDetector:

    def test_compute_salience(self):
        from core.insular_cortex import SalienceDetector
        sd = SalienceDetector(threshold=0.5)
        sal = sd.compute_salience({'visual': 0.8, 'audio': 0.6}, novelty=0.5)
        assert 0.0 <= sal <= 1.0

    def test_threshold_detection(self):
        from core.insular_cortex import SalienceDetector
        sd = SalienceDetector(threshold=0.3)
        sal = sd.compute_salience({'visual': 0.9}, novelty=0.9, emotional_intensity=0.9)
        assert sd.is_salient(sal)

    def test_recent_events(self):
        from core.insular_cortex import SalienceDetector
        sd = SalienceDetector(threshold=0.3)
        sd.compute_salience({'x': 0.9}, novelty=0.9, emotional_intensity=0.9)
        events = sd.get_recent_events()
        assert len(events) >= 1


class TestSubjectiveFeelingGenerator:

    def test_generate_feeling(self):
        from core.insular_cortex import SubjectiveFeelingGenerator
        sfg = SubjectiveFeelingGenerator()
        feeling = sfg.generate_feeling(body_deviation=0.1, salience=0.1, stress=0.8)
        assert feeling == 'stressed'

    def test_fatigued_feeling(self):
        from core.insular_cortex import SubjectiveFeelingGenerator
        sfg = SubjectiveFeelingGenerator()
        feeling = sfg.generate_feeling(body_deviation=0.1, salience=0.1, stress=0.1, energy=0.1)
        assert feeling == 'fatigued'


class TestBodyBudgetAccounting:

    def test_spend(self):
        from core.insular_cortex import BodyBudgetAccounting
        bb = BodyBudgetAccounting()
        bb.spend(0.3, "task")
        assert bb.balance == pytest.approx(0.7)

    def test_deposit(self):
        from core.insular_cortex import BodyBudgetAccounting
        bb = BodyBudgetAccounting()
        bb.spend(0.5)
        bb.deposit(0.3, "rest")
        assert bb.balance == pytest.approx(0.8)

    def test_depletion(self):
        from core.insular_cortex import BodyBudgetAccounting
        bb = BodyBudgetAccounting()
        bb.spend(0.9)
        assert bb.is_depleted


class TestNetworkSwitcher:

    def test_default_dmn(self):
        from core.insular_cortex import NetworkSwitcher
        ns = NetworkSwitcher()
        assert ns.current_network == "dmn"

    def test_switch_to_tpn(self):
        from core.insular_cortex import NetworkSwitcher
        ns = NetworkSwitcher(switch_speed=1.0)
        ns.evaluate_switch(salience=0.9, current_task_demand=0.9)
        assert ns.current_network == "tpn"


class TestInsularCortex:

    def test_instantiation(self, insular):
        assert insular is not None

    def test_process(self, insular):
        result = insular.process(
            body_signals=np.array([0.5, 0.3, 0.5, 0.5, 0.5, 0.5]),
            sensory_signals={'visual': 0.3},
            novelty=0.2,
        )
        assert 'salience' in result
        assert 'feeling' in result
        assert 'body_budget' in result
        assert 'active_network' in result

    def test_high_salience(self, insular):
        result = insular.process(
            sensory_signals={'visual': 0.9, 'audio': 0.8},
            novelty=0.9,
            emotional_intensity=0.9,
        )
        assert result['salience'] > 0.5

    def test_get_state(self, insular):
        insular.process(body_signals=np.array([0.5] * 6))
        state = insular.get_state()
        assert 'stats' in state
        assert 'interoceptive' in state

    def test_reset(self, insular):
        insular.process(body_signals=np.array([0.5] * 6))
        insular.reset()
        assert insular.get_stats().interoceptive_updates == 0

    def test_from_yaml(self):
        from core.insular_cortex import InsularCortex
        ic = InsularCortex.from_yaml({
            'insular_cortex': {'salience_threshold': 0.8}
        })
        assert ic.salience_detector.threshold == 0.8

    def test_from_yaml_defaults(self):
        from core.insular_cortex import InsularCortex
        ic = InsularCortex.from_yaml({})
        assert ic is not None
