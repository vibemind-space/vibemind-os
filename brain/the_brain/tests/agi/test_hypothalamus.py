"""
Hypothalamus Tests - Phase A3

Tests for drive states, circadian clock, HPA axis,
homeostatic comparator, and full hypothalamus integration.
"""

import pytest
import numpy as np


@pytest.fixture
def hypothalamus():
    from core.hypothalamus_drives import HypothalamusModule
    return HypothalamusModule()


class TestDriveState:

    def test_to_vector(self):
        from core.hypothalamus_drives import DriveState
        ds = DriveState(hunger=0.8, thirst=0.2)
        vec = ds.to_vector()
        assert vec.shape == (6,)
        assert vec[0] == pytest.approx(0.8)
        assert vec[1] == pytest.approx(0.2)

    def test_from_vector(self):
        from core.hypothalamus_drives import DriveState
        ds = DriveState()
        ds.from_vector(np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]))
        assert ds.hunger == pytest.approx(0.1)
        assert ds.curiosity == pytest.approx(0.6)

    def test_most_urgent_drive(self):
        from core.hypothalamus_drives import DriveState
        ds = DriveState(hunger=0.9, thirst=0.3)
        setpoints = np.array([0.3, 0.3, 0.5, 0.3, 0.5, 0.5], dtype=np.float32)
        name, dev = ds.most_urgent_drive(setpoints)
        assert name == 'hunger'
        assert dev > 0.5

    def test_total_deviation(self):
        from core.hypothalamus_drives import DriveState
        ds = DriveState()
        setpoints = ds.to_vector()
        assert ds.total_deviation(setpoints) == pytest.approx(0.0)


class TestSuprachiasmaticNucleus:

    def test_tick(self):
        from core.hypothalamus_drives import SuprachiasmaticNucleus
        scn = SuprachiasmaticNucleus(cycle_period=100.0)
        phase = scn.tick(elapsed_seconds=25.0)
        assert 0 <= phase < 2 * np.pi

    def test_arousal_modulation(self):
        from core.hypothalamus_drives import SuprachiasmaticNucleus
        scn = SuprachiasmaticNucleus(cycle_period=100.0)
        scn.tick(elapsed_seconds=0.0)
        arousal = scn.get_arousal_modulation()
        assert 0.0 <= arousal <= 1.0

    def test_full_cycle(self):
        from core.hypothalamus_drives import SuprachiasmaticNucleus
        scn = SuprachiasmaticNucleus(cycle_period=100.0)
        scn.tick(elapsed_seconds=100.0)
        assert scn.phase == pytest.approx(0.0, abs=0.01)


class TestHPAAxis:

    def test_process_stressor(self):
        from core.hypothalamus_drives import HPAAxis
        hpa = HPAAxis()
        cortisol = hpa.process_stressor(0.8)
        assert cortisol > 0.0
        assert cortisol <= 1.0

    def test_recovery(self):
        from core.hypothalamus_drives import HPAAxis
        hpa = HPAAxis(recovery_rate=0.1)
        hpa.process_stressor(0.9)
        initial = hpa.cortisol
        hpa.recover()
        assert hpa.cortisol < initial

    def test_is_stressed(self):
        from core.hypothalamus_drives import HPAAxis
        hpa = HPAAxis(stress_threshold=0.2)
        for _ in range(5):
            hpa.process_stressor(1.0)
        assert hpa.is_stressed

    def test_chronic_stress(self):
        from core.hypothalamus_drives import HPAAxis
        hpa = HPAAxis()
        for _ in range(10):
            hpa.process_stressor(0.5)
        assert hpa.get_chronic_stress() > 0.0


class TestHomeostaticComparator:

    def test_compute_error(self):
        from core.hypothalamus_drives import HomeostaticComparator, DriveState
        hc = HomeostaticComparator()
        ds = DriveState(hunger=0.9)
        error = hc.compute_error(ds)
        assert error[0] > 0  # Hunger above setpoint

    def test_urgency(self):
        from core.hypothalamus_drives import HomeostaticComparator, DriveState
        hc = HomeostaticComparator()
        ds = DriveState(hunger=1.0)
        urgency = hc.compute_urgency(ds)
        assert urgency > 0.5


class TestHypothalamusModule:

    def test_instantiation(self, hypothalamus):
        assert hypothalamus is not None

    def test_update_drives(self, hypothalamus):
        result = hypothalamus.update_drives(elapsed_seconds=3600)
        assert 'drives' in result
        assert 'urgency' in result
        assert 'arousal' in result
        assert 'most_urgent' in result

    def test_drives_increase_over_time(self, hypothalamus):
        hypothalamus.drives.hunger = 0.3
        hypothalamus.update_drives(elapsed_seconds=7200)  # 2 hours
        assert hypothalamus.drives.hunger > 0.3

    def test_satisfy_drive(self, hypothalamus):
        hypothalamus.drives.hunger = 0.8
        hypothalamus.satisfy_drive('hunger', 0.5)
        assert hypothalamus.drives.hunger == pytest.approx(0.3)

    def test_process_stressor(self, hypothalamus):
        cortisol = hypothalamus.process_stressor(0.9)
        assert cortisol > 0.0

    def test_external_signals(self, hypothalamus):
        hypothalamus.drives.hunger = 0.8
        hypothalamus.update_drives(external_signals={'hunger': -0.3})
        assert hypothalamus.drives.hunger < 0.8

    def test_get_state(self, hypothalamus):
        state = hypothalamus.get_state()
        assert 'stats' in state
        assert 'drives' in state
        assert 'circadian' in state
        assert 'hpa' in state

    def test_reset(self, hypothalamus):
        hypothalamus.process_stressor(1.0)
        hypothalamus.reset()
        assert hypothalamus.hpa.cortisol == 0.0

    def test_from_yaml(self):
        from core.hypothalamus_drives import HypothalamusModule
        ht = HypothalamusModule.from_yaml({
            'hypothalamus': {'stress_threshold': 0.5, 'circadian_period': 1000}
        })
        assert ht.hpa.stress_threshold == 0.5

    def test_from_yaml_defaults(self):
        from core.hypothalamus_drives import HypothalamusModule
        ht = HypothalamusModule.from_yaml({})
        assert ht is not None
