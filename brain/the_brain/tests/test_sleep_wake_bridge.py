"""Tests for SleepWakeBridge -- Sleep/Wake Quartet -> Radial Attention Network.

Covers: SleepWakeState defaults, module wiring, inter-module coupling,
hook-clamped field safety, multi-tick stability, and integration with
real neuroscience modules (RF, TMN, PG, PPN).
"""
import pytest
import numpy as np
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers: ring activations and prediction errors
# ---------------------------------------------------------------------------

def _ring_activations():
    """Standard 5-ring activations: [64, 128, 256, 256, 128]."""
    return [
        np.random.randn(64),
        np.random.randn(128),
        np.random.randn(256),
        np.random.randn(256),
        np.random.randn(128),
    ]


def _prediction_errors():
    """Standard 4-element prediction error list."""
    return [0.1, 0.2, 0.15, 0.1]


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

def _make_mock_rf():
    """Mock ReticularFormation with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'arousal': 0.6,
        'sensory_gain': 0.75,
        'state': 'awake',
        'motor_tone': 0.5,
        'gated_signal_strength': 0.4,
    }
    return m


def _make_mock_tmn():
    """Mock TuberomammillaryNucleus with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'histamine_level': 0.65,
        'wakefulness_drive': 0.7,
        'is_awake': True,
        'arousal_input': 0.6,
        'circadian_input': 0.5,
        'sleep_pressure_input': 0.0,
    }
    return m


def _make_mock_pg():
    """Mock PinealGland with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'melatonin_level': 0.15,
        'sleep_pressure': 0.12,
        'circadian_strength': 0.5,
        'phase_shift': 0.001,
        'entrainment_strength': 0.9,
        'is_entrained': True,
    }
    return m


def _make_mock_ppn():
    """Mock PedunculopontineNucleus with standard return (nested rem dict)."""
    m = MagicMock()
    m.process.return_value = {
        'cholinergic_tone': 0.55,
        'locomotion': {
            'locomotion_drive': 0.0,
            'gait_signal': 0.0,
            'initiation_threshold_met': False,
        },
        'rem': {
            'rem_probability': 0.05,
            'cholinergic_burst': 0.0,
            'muscle_atonia': 0.0,
        },
        'arousal_output': 0.5,
    }
    return m


def _make_bridge(rf=None, tmn=None, pg=None, ppn=None):
    """Construct SleepWakeBridge with optional mock overrides."""
    from core.sleep_wake_bridge import SleepWakeBridge
    return SleepWakeBridge(
        reticular_formation=rf if rf is not None else _make_mock_rf(),
        tuberomammillary_nucleus=tmn if tmn is not None else _make_mock_tmn(),
        pineal_gland=pg if pg is not None else _make_mock_pg(),
        pedunculopontine_nucleus=ppn if ppn is not None else _make_mock_ppn(),
    )


# ===========================================================================
# Test classes
# ===========================================================================

class TestSleepWakeState:
    """SleepWakeState dataclass field defaults."""

    def test_state_defaults(self):
        from core.sleep_wake_bridge import SleepWakeState
        s = SleepWakeState()
        assert s.arousal == 0.5
        assert s.sensory_gain == 0.5
        assert s.histamine == 0.5
        assert s.is_awake is True
        assert s.wakefulness_drive == 0.5
        assert s.melatonin == 0.0
        assert s.sleep_pressure == 0.0
        assert s.cholinergic_tone == 0.5
        assert s.rem_probability == 0.0


class TestSleepWakeBridgeInit:
    """Constructor wiring tests."""

    def test_init_stores_modules(self):
        rf, tmn, pg, ppn = _make_mock_rf(), _make_mock_tmn(), _make_mock_pg(), _make_mock_ppn()
        from core.sleep_wake_bridge import SleepWakeBridge
        bridge = SleepWakeBridge(
            reticular_formation=rf,
            tuberomammillary_nucleus=tmn,
            pineal_gland=pg,
            pedunculopontine_nucleus=ppn,
        )
        assert bridge._reticular_formation is rf
        assert bridge._tuberomammillary_nucleus is tmn
        assert bridge._pineal_gland is pg
        assert bridge._pedunculopontine_nucleus is ppn

    def test_init_no_modules(self):
        """Init with no modules must not crash."""
        from core.sleep_wake_bridge import SleepWakeBridge
        bridge = SleepWakeBridge()
        assert bridge._reticular_formation is None
        assert bridge._tuberomammillary_nucleus is None
        assert bridge._pineal_gland is None
        assert bridge._pedunculopontine_nucleus is None


class TestSleepWakeBridgeUpdate:
    """update() behaviour with mocked modules."""

    def test_update_returns_state(self):
        from core.sleep_wake_bridge import SleepWakeState
        bridge = _make_bridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, SleepWakeState)

    def test_update_calls_reticular_formation(self):
        rf = _make_mock_rf()
        bridge = _make_bridge(rf=rf)
        bridge.update(_ring_activations(), _prediction_errors())
        rf.process.assert_called_once()
        call_kwargs = rf.process.call_args
        # Verify sensory_input_level is passed
        assert 'sensory_input_level' in call_kwargs.kwargs or len(call_kwargs.args) > 0

    def test_update_calls_tuberomammillary_nucleus(self):
        tmn = _make_mock_tmn()
        bridge = _make_bridge(tmn=tmn)
        bridge.update(_ring_activations(), _prediction_errors())
        tmn.process.assert_called_once()

    def test_update_calls_pineal_gland(self):
        pg = _make_mock_pg()
        bridge = _make_bridge(pg=pg)
        bridge.update(_ring_activations(), _prediction_errors())
        pg.process.assert_called_once()

    def test_update_calls_pedunculopontine_nucleus(self):
        ppn = _make_mock_ppn()
        bridge = _make_bridge(ppn=ppn)
        bridge.update(_ring_activations(), _prediction_errors())
        ppn.process.assert_called_once()


class TestSleepWakeBridgeCoupling:
    """Inter-module coupling: RF -> TMN, PG -> TMN (next tick)."""

    def test_rf_tmn_coupling(self):
        """RF arousal feeds into TMN arousal_drive."""
        rf = _make_mock_rf()
        rf.process.return_value = {
            'arousal': 0.8,
            'sensory_gain': 0.9,
            'state': 'alert',
            'motor_tone': 0.7,
            'gated_signal_strength': 0.6,
        }
        tmn = _make_mock_tmn()
        bridge = _make_bridge(rf=rf, tmn=tmn)
        bridge.update(_ring_activations(), _prediction_errors())
        # TMN should receive arousal_drive from RF's arousal output
        tmn_call_kwargs = tmn.process.call_args
        # arousal_drive should be 0.8 (from RF)
        if tmn_call_kwargs.kwargs:
            assert tmn_call_kwargs.kwargs.get('arousal_drive') == 0.8
        else:
            assert tmn_call_kwargs.args[0] == 0.8

    def test_pg_tmn_coupling(self):
        """PG melatonin feeds into TMN sleep_pressure on the NEXT tick."""
        pg = _make_mock_pg()
        pg.process.return_value = {
            'melatonin_level': 0.7,
            'sleep_pressure': 0.6,
            'circadian_strength': 0.5,
            'phase_shift': 0.001,
            'entrainment_strength': 0.9,
            'is_entrained': True,
        }
        tmn = _make_mock_tmn()
        bridge = _make_bridge(pg=pg, tmn=tmn)

        # First tick: TMN gets _prev_melatonin=0.0 (initial default)
        bridge.update(_ring_activations(), _prediction_errors())
        first_call = tmn.process.call_args
        if first_call.kwargs:
            assert first_call.kwargs.get('sleep_pressure') == 0.0
        else:
            # positional: (arousal_drive, circadian_phase, sleep_pressure)
            assert first_call.args[2] == 0.0

        # Second tick: TMN should now get PG melatonin (0.7) from first tick
        tmn.reset_mock()
        bridge.update(_ring_activations(), _prediction_errors())
        second_call = tmn.process.call_args
        if second_call.kwargs:
            assert second_call.kwargs.get('sleep_pressure') == 0.7
        else:
            assert second_call.args[2] == 0.7


class TestSleepWakeBridgeStability:
    """Multi-tick and clamping safety tests."""

    def test_multi_tick_stability(self):
        """20 ticks, all fields remain in reasonable ranges."""
        from core.sleep_wake_bridge import SleepWakeState
        bridge = _make_bridge()
        for _ in range(20):
            state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, SleepWakeState)
        assert 0.0 <= state.arousal <= 1.0
        assert 0.0 <= state.sensory_gain <= 1.0
        assert 0.0 <= state.histamine <= 1.0
        assert isinstance(state.is_awake, bool)
        assert 0.0 <= state.wakefulness_drive <= 1.0
        assert 0.0 <= state.melatonin <= 1.0
        assert 0.0 <= state.sleep_pressure <= 1.0
        assert 0.0 <= state.cholinergic_tone <= 1.0
        assert 0.0 <= state.rem_probability <= 1.0

    def test_hook_fields_clamped(self):
        """arousal, histamine, melatonin are always clamped to [0, 1]."""
        rf = _make_mock_rf()
        # Return out-of-range arousal
        rf.process.return_value = {
            'arousal': 1.5,
            'sensory_gain': 0.5,
            'state': 'hyperaroused',
            'motor_tone': 0.5,
            'gated_signal_strength': 0.5,
        }
        tmn = _make_mock_tmn()
        tmn.process.return_value = {
            'histamine_level': -0.3,
            'wakefulness_drive': 0.5,
            'is_awake': True,
        }
        pg = _make_mock_pg()
        pg.process.return_value = {
            'melatonin_level': 2.0,
            'sleep_pressure': 0.5,
            'circadian_strength': 0.5,
        }
        bridge = _make_bridge(rf=rf, tmn=tmn, pg=pg)
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert 0.0 <= state.arousal <= 1.0, f"arousal {state.arousal} not in [0,1]"
        assert 0.0 <= state.histamine <= 1.0, f"histamine {state.histamine} not in [0,1]"
        assert 0.0 <= state.melatonin <= 1.0, f"melatonin {state.melatonin} not in [0,1]"


class TestSleepWakeBridgeGetState:
    """get_state() accessor tests."""

    def test_get_state(self):
        from core.sleep_wake_bridge import SleepWakeState
        bridge = _make_bridge()
        state = bridge.get_state()
        assert isinstance(state, SleepWakeState)

    def test_get_state_after_update(self):
        bridge = _make_bridge()
        returned = bridge.update(_ring_activations(), _prediction_errors())
        fetched = bridge.get_state()
        assert returned is fetched


class TestSleepWakeBridgeNoModules:
    """Skeleton behaviour when all modules are None."""

    def test_skeleton_no_modules(self):
        """update() with no modules returns default-ish state, no crash."""
        from core.sleep_wake_bridge import SleepWakeBridge, SleepWakeState
        bridge = SleepWakeBridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, SleepWakeState)
        # Should be default or close to default values
        assert 0.0 <= state.arousal <= 1.0
        assert 0.0 <= state.histamine <= 1.0
        assert 0.0 <= state.melatonin <= 1.0


class TestSleepWakeBridgeIntegration:
    """Integration test with real neuroscience modules."""

    def test_integration_with_real_modules(self):
        from core.reticular_formation import ReticularFormation
        from core.tuberomammillary_nucleus import TuberomammillaryNucleus
        from core.pineal_gland import PinealGland
        from core.pedunculopontine_nucleus import PedunculopontineNucleus
        from core.sleep_wake_bridge import SleepWakeBridge, SleepWakeState

        rf = ReticularFormation()
        tmn = TuberomammillaryNucleus()
        pg = PinealGland()
        ppn = PedunculopontineNucleus()
        bridge = SleepWakeBridge(
            reticular_formation=rf,
            tuberomammillary_nucleus=tmn,
            pineal_gland=pg,
            pedunculopontine_nucleus=ppn,
        )

        ring_acts = [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]
        pes = [0.1, 0.2, 0.15, 0.1]

        for _ in range(10):
            state = bridge.update(ring_acts, pes)

        assert isinstance(state, SleepWakeState)
        assert 0.0 <= state.arousal <= 1.0
        assert 0.0 <= state.histamine <= 1.0
        assert 0.0 <= state.melatonin <= 1.0
        assert 0.0 <= state.sensory_gain <= 1.0
        assert 0.0 <= state.wakefulness_drive <= 1.0
        assert 0.0 <= state.sleep_pressure <= 1.0
        assert 0.0 <= state.cholinergic_tone <= 1.0
        assert 0.0 <= state.rem_probability <= 1.0
        assert isinstance(state.is_awake, bool)
