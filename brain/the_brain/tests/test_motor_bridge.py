"""Tests for MotorBridge -- Motor Quintet -> Radial Attention Network.

Covers: MotorState defaults, module wiring, inter-module coupling,
hook-clamped field safety, multi-tick stability, and integration with
real neuroscience modules (Cerebellum, SubstantiaNigra, ZonaIncerta,
RedNucleus, PosteriorParietalCortex).
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

def _make_mock_cb():
    """Mock CerebellumModule with standard return."""
    m = MagicMock()
    m.compute_sensory_prediction_error.return_value = {
        'prediction_error': 0.12,
        'learning_signal': 0.24,
        'model_confidence': 0.76,
        'should_update_model': True,
    }
    return m


def _make_mock_sn():
    """Mock SubstantiaNigra with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'motor_da': 0.65,
        'go_nogo_balance': 0.2,
        'disinhibited': False,
        'inhibition_level': 0.4,
        'thalamic_gate': 0.6,
        'plasticity_modulation': 0.5,
    }
    return m


def _make_mock_zi():
    """Mock ZonaIncerta with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'inhibition_level': 0.35,
        'action_tendency': 0.6,
        'integration_strength': 0.4,
        'inhibition_release': 0.3,
        'gated_targets': {},
        'visceral': {},
    }
    return m


def _make_mock_rn():
    """Mock RedNucleus with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'corrected_signal': 0.5,
        'backup_signal': 0.1,
        'error_correction': -0.05,
        'is_compensating': False,
        'blend_ratio': 0.05,
    }
    return m


def _make_mock_ppc():
    """Mock PosteriorParietalCortex with standard return (nested action_plan)."""
    m = MagicMock()
    m.process.return_value = {
        'priority_map': [0.0] * 16,
        'peak_location': 3,
        'peak_salience': 0.72,
        'action_plan': {
            'action_vector': [0.0] * 16,
            'reach_plan': {'target_index': 3, 'distance': 0.5},
            'movement_confidence': 0.68,
        },
    }
    return m


def _make_bridge(cb=None, sn=None, zi=None, rn=None, ppc=None):
    """Construct MotorBridge with optional mock overrides."""
    from core.motor_bridge import MotorBridge
    return MotorBridge(
        cerebellum=cb if cb is not None else _make_mock_cb(),
        substantia_nigra=sn if sn is not None else _make_mock_sn(),
        zona_incerta=zi if zi is not None else _make_mock_zi(),
        red_nucleus=rn if rn is not None else _make_mock_rn(),
        posterior_parietal_cortex=ppc if ppc is not None else _make_mock_ppc(),
    )


# ===========================================================================
# Test classes
# ===========================================================================

class TestMotorState:
    """MotorState dataclass field defaults."""

    def test_state_defaults(self):
        from core.motor_bridge import MotorState
        s = MotorState()
        assert s.prediction_error == 0.0
        assert s.model_confidence == 0.5
        assert s.motor_da == 0.5
        assert s.go_nogo_balance == 0.0
        assert s.disinhibited is False
        assert s.inhibition_level == 0.5
        assert s.action_tendency == 0.5
        assert s.is_compensating is False
        assert s.error_correction == 0.0
        assert s.peak_salience == 0.5
        assert s.movement_confidence == 0.5


class TestMotorBridgeInit:
    """Constructor wiring tests."""

    def test_init_stores_modules(self):
        cb = _make_mock_cb()
        sn = _make_mock_sn()
        zi = _make_mock_zi()
        rn = _make_mock_rn()
        ppc = _make_mock_ppc()
        from core.motor_bridge import MotorBridge
        bridge = MotorBridge(
            cerebellum=cb,
            substantia_nigra=sn,
            zona_incerta=zi,
            red_nucleus=rn,
            posterior_parietal_cortex=ppc,
        )
        assert bridge._cerebellum is cb
        assert bridge._substantia_nigra is sn
        assert bridge._zona_incerta is zi
        assert bridge._red_nucleus is rn
        assert bridge._posterior_parietal_cortex is ppc

    def test_init_no_modules(self):
        """Init with no modules must not crash."""
        from core.motor_bridge import MotorBridge
        bridge = MotorBridge()
        assert bridge._cerebellum is None
        assert bridge._substantia_nigra is None
        assert bridge._zona_incerta is None
        assert bridge._red_nucleus is None
        assert bridge._posterior_parietal_cortex is None


class TestMotorBridgeUpdate:
    """update() behaviour with mocked modules."""

    def test_update_returns_state(self):
        from core.motor_bridge import MotorState
        bridge = _make_bridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, MotorState)

    def test_update_calls_cerebellum(self):
        cb = _make_mock_cb()
        bridge = _make_bridge(cb=cb)
        bridge.update(_ring_activations(), _prediction_errors())
        cb.compute_sensory_prediction_error.assert_called_once()
        call_kwargs = cb.compute_sensory_prediction_error.call_args
        # Verify predicted_sensory and actual_sensory are passed
        assert 'predicted_sensory' in call_kwargs.kwargs or len(call_kwargs.args) >= 2

    def test_update_calls_substantia_nigra(self):
        sn = _make_mock_sn()
        bridge = _make_bridge(sn=sn)
        bridge.update(_ring_activations(), _prediction_errors())
        sn.process.assert_called_once()

    def test_update_calls_zona_incerta(self):
        zi = _make_mock_zi()
        bridge = _make_bridge(zi=zi)
        bridge.update(_ring_activations(), _prediction_errors())
        zi.process.assert_called_once()

    def test_update_calls_red_nucleus(self):
        rn = _make_mock_rn()
        bridge = _make_bridge(rn=rn)
        bridge.update(_ring_activations(), _prediction_errors())
        rn.process.assert_called_once()

    def test_update_calls_ppc(self):
        ppc = _make_mock_ppc()
        bridge = _make_bridge(ppc=ppc)
        bridge.update(_ring_activations(), _prediction_errors())
        ppc.process.assert_called_once()


class TestMotorBridgeCoupling:
    """Inter-module coupling tests."""

    def test_cb_rn_coupling(self):
        """Cerebellum prediction_error feeds into RedNucleus error_signal."""
        cb = _make_mock_cb()
        cb.compute_sensory_prediction_error.return_value = {
            'prediction_error': 0.35,
            'learning_signal': 0.7,
            'model_confidence': 0.3,
            'should_update_model': True,
        }
        rn = _make_mock_rn()
        bridge = _make_bridge(cb=cb, rn=rn)
        bridge.update(_ring_activations(), _prediction_errors())
        # RN should receive error_signal from CB's prediction_error (0.35)
        rn_call_kwargs = rn.process.call_args
        if rn_call_kwargs.kwargs:
            assert rn_call_kwargs.kwargs.get('error_signal') == 0.35
        else:
            # positional: (primary_motor_signal, error_signal, cerebellar_input)
            assert rn_call_kwargs.args[1] == 0.35

    def test_sn_zi_coupling(self):
        """SN motor_da feeds ZI motivation on NEXT tick (1-tick delay)."""
        sn = _make_mock_sn()
        sn.process.return_value = {
            'motor_da': 0.85,
            'go_nogo_balance': 0.3,
            'disinhibited': True,
            'inhibition_level': 0.2,
            'thalamic_gate': 0.8,
            'plasticity_modulation': 0.5,
        }
        zi = _make_mock_zi()
        bridge = _make_bridge(sn=sn, zi=zi)

        # First tick: ZI gets _prev_motor_da=0.5 (initial default)
        bridge.update(_ring_activations(), _prediction_errors())
        first_call = zi.process.call_args
        if first_call.kwargs:
            assert first_call.kwargs.get('motivation') == 0.5
        else:
            assert first_call.args[0] == 0.5

        # Second tick: ZI should now get SN motor_da (0.85) from first tick
        zi.reset_mock()
        bridge.update(_ring_activations(), _prediction_errors())
        second_call = zi.process.call_args
        if second_call.kwargs:
            assert second_call.kwargs.get('motivation') == 0.85
        else:
            assert second_call.args[0] == 0.85


class TestMotorBridgeStability:
    """Multi-tick and clamping safety tests."""

    def test_multi_tick_stability(self):
        """20 ticks, all fields remain in reasonable ranges."""
        from core.motor_bridge import MotorState
        bridge = _make_bridge()
        for _ in range(20):
            state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, MotorState)
        assert 0.0 <= state.model_confidence <= 1.0
        assert 0.0 <= state.action_tendency <= 1.0
        assert isinstance(state.disinhibited, bool)
        assert isinstance(state.is_compensating, bool)
        # All float fields should be finite
        assert np.isfinite(state.prediction_error)
        assert np.isfinite(state.motor_da)
        assert np.isfinite(state.go_nogo_balance)
        assert np.isfinite(state.inhibition_level)
        assert np.isfinite(state.error_correction)
        assert np.isfinite(state.peak_salience)
        assert np.isfinite(state.movement_confidence)

    def test_hook_fields_clamped(self):
        """model_confidence and action_tendency are always clamped to [0, 1]."""
        cb = _make_mock_cb()
        # Return out-of-range model_confidence
        cb.compute_sensory_prediction_error.return_value = {
            'prediction_error': 0.5,
            'learning_signal': 1.0,
            'model_confidence': 1.8,  # out of range!
            'should_update_model': True,
        }
        zi = _make_mock_zi()
        # Return out-of-range action_tendency
        zi.process.return_value = {
            'inhibition_level': 0.5,
            'action_tendency': -0.5,  # out of range!
            'integration_strength': 0.4,
            'inhibition_release': 0.3,
        }
        bridge = _make_bridge(cb=cb, zi=zi)
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert 0.0 <= state.model_confidence <= 1.0, (
            f"model_confidence {state.model_confidence} not in [0,1]"
        )
        assert 0.0 <= state.action_tendency <= 1.0, (
            f"action_tendency {state.action_tendency} not in [0,1]"
        )


class TestMotorBridgeNoModules:
    """Skeleton behaviour when all modules are None."""

    def test_skeleton_no_modules(self):
        """update() with no modules returns default-ish state, no crash."""
        from core.motor_bridge import MotorBridge, MotorState
        bridge = MotorBridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, MotorState)
        assert 0.0 <= state.model_confidence <= 1.0
        assert 0.0 <= state.action_tendency <= 1.0


class TestMotorBridgeIntegration:
    """Integration test with real neuroscience modules."""

    def test_integration_with_real_modules(self):
        from core.cerebellum_module import CerebellumModule
        from core.substantia_nigra import SubstantiaNigra
        from core.zona_incerta import ZonaIncerta
        from core.red_nucleus import RedNucleus
        from core.posterior_parietal_cortex import PosteriorParietalCortex
        from core.motor_bridge import MotorBridge, MotorState

        cb = CerebellumModule()
        sn = SubstantiaNigra()
        zi = ZonaIncerta()
        rn = RedNucleus()
        ppc = PosteriorParietalCortex()
        bridge = MotorBridge(
            cerebellum=cb,
            substantia_nigra=sn,
            zona_incerta=zi,
            red_nucleus=rn,
            posterior_parietal_cortex=ppc,
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

        assert isinstance(state, MotorState)
        assert 0.0 <= state.model_confidence <= 1.0
        assert 0.0 <= state.action_tendency <= 1.0
