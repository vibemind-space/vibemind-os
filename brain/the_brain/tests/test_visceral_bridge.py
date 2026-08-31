"""Tests for VisceralBridge -- NTS + VP -> Radial Attention Network.

Covers: VisceralState defaults, module wiring, inter-module coupling,
hook-clamped field safety (H26: afferent_strength, H27: liking),
multi-tick stability, VP nested dict handling, and integration with
real neuroscience modules (NucleusTractSolitarius, VentralPallidum).
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

def _make_mock_nts():
    """Mock NucleusTractSolitarius with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'overall_visceral': 0.5,
        'afferent_strength': 0.4,
        'reflex_active': False,
        'cardiovascular_state': 0.5,
        'respiratory_state': 0.5,
        'gi_state': 0.5,
    }
    return m


def _make_mock_vp():
    """Mock VentralPallidum with standard nested-dict return."""
    m = MagicMock()
    m.process.return_value = {
        'liking': {
            'liking_response': 0.6,
            'hedonic_value': 0.55,
            'pleasure_amplification': 1.5,
        },
        'motor': {
            'motor_output': 0.4,
            'approach_strength': 0.45,
            'consummatory_drive': 0.3,
        },
        'opioid_level': 0.5,
        'wanting_signal': 0.5,
    }
    return m


def _make_bridge(nts=None, vp=None):
    """Construct VisceralBridge with optional mock overrides."""
    from core.visceral_bridge import VisceralBridge
    return VisceralBridge(
        nucleus_tractus_solitarius=nts if nts is not None else _make_mock_nts(),
        ventral_pallidum=vp if vp is not None else _make_mock_vp(),
    )


# ===========================================================================
# Test classes
# ===========================================================================

class TestVisceralState:
    """VisceralState dataclass field defaults."""

    def test_state_defaults(self):
        from core.visceral_bridge import VisceralState
        s = VisceralState()
        assert s.visceral_level == 0.5
        assert s.afferent_strength == 0.3
        assert s.reflex_active is False
        assert s.liking == 0.5
        assert s.wanting == 0.5
        assert s.approach_strength == 0.3


class TestVisceralBridgeInit:
    """Constructor wiring tests."""

    def test_init_stores_modules(self):
        nts = _make_mock_nts()
        vp = _make_mock_vp()
        from core.visceral_bridge import VisceralBridge
        bridge = VisceralBridge(
            nucleus_tractus_solitarius=nts,
            ventral_pallidum=vp,
        )
        assert bridge._nucleus_tractus_solitarius is nts
        assert bridge._ventral_pallidum is vp

    def test_init_no_modules(self):
        """Init with no modules must not crash."""
        from core.visceral_bridge import VisceralBridge
        bridge = VisceralBridge()
        assert bridge._nucleus_tractus_solitarius is None
        assert bridge._ventral_pallidum is None


class TestVisceralBridgeUpdate:
    """update() behaviour with mocked modules."""

    def test_update_returns_state(self):
        from core.visceral_bridge import VisceralState
        bridge = _make_bridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, VisceralState)

    def test_update_calls_nts(self):
        nts = _make_mock_nts()
        bridge = _make_bridge(nts=nts)
        bridge.update(_ring_activations(), _prediction_errors())
        nts.process.assert_called_once()
        # Verify it was called with a dict argument
        call_args = nts.process.call_args
        assert len(call_args.args) == 1 or 'visceral_inputs' in str(call_args)
        input_dict = call_args.args[0] if call_args.args else call_args.kwargs
        assert isinstance(input_dict, dict)

    def test_update_calls_ventral_pallidum(self):
        vp = _make_mock_vp()
        bridge = _make_bridge(vp=vp)
        bridge.update(_ring_activations(), _prediction_errors())
        vp.process.assert_called_once()
        # Verify kwargs were used
        call_kwargs = vp.process.call_args.kwargs
        assert 'reward_signal' in call_kwargs
        assert 'opioid_level' in call_kwargs
        assert 'wanting_signal' in call_kwargs
        assert 'inhibition' in call_kwargs


class TestVisceralBridgeCoupling:
    """Inter-module coupling tests."""

    def test_nts_coupling(self):
        """NTS visceral_level feeds itself on next tick via _prev_visceral."""
        nts = _make_mock_nts()
        # Tick 1: returns visceral_level = 0.7
        nts.process.return_value = {
            'overall_visceral': 0.7,
            'afferent_strength': 0.5,
            'reflex_active': False,
            'cardiovascular_state': 0.5,
            'respiratory_state': 0.5,
            'gi_state': 0.5,
        }
        bridge = _make_bridge(nts=nts)

        # Tick 1: _prev_visceral is 0.0 (initial)
        bridge.update(_ring_activations(), _prediction_errors())
        first_call = nts.process.call_args
        first_input = first_call.args[0]
        assert first_input['visceral_distress'] == 0.0  # initial _prev_visceral

        # Tick 2: _prev_visceral should be 0.7 from tick 1
        nts.reset_mock()
        bridge.update(_ring_activations(), _prediction_errors())
        second_call = nts.process.call_args
        second_input = second_call.args[0]
        assert second_input['visceral_distress'] == pytest.approx(0.7, abs=0.01)

    def test_nts_vp_coupling(self):
        """NTS visceral_level feeds VP inhibition."""
        nts = _make_mock_nts()
        nts.process.return_value = {
            'overall_visceral': 0.8,
            'afferent_strength': 0.6,
            'reflex_active': True,
            'cardiovascular_state': 0.5,
            'respiratory_state': 0.5,
            'gi_state': 0.5,
        }
        vp = _make_mock_vp()
        bridge = _make_bridge(nts=nts, vp=vp)

        # Tick 1: VP inhibition uses _prev_visceral (0.0) * 0.3 = 0.0
        bridge.update(_ring_activations(), _prediction_errors())
        first_vp_call = vp.process.call_args
        assert first_vp_call.kwargs['inhibition'] == pytest.approx(0.0, abs=0.01)

        # Tick 2: VP inhibition uses _prev_visceral (0.8) * 0.3 = 0.24
        vp.reset_mock()
        bridge.update(_ring_activations(), _prediction_errors())
        second_vp_call = vp.process.call_args
        assert second_vp_call.kwargs['inhibition'] == pytest.approx(0.8 * 0.3, abs=0.01)


class TestVisceralBridgeStability:
    """Multi-tick and clamping safety tests."""

    def test_multi_tick_stability(self):
        """20 ticks, all fields remain in reasonable ranges."""
        from core.visceral_bridge import VisceralState
        bridge = _make_bridge()
        for _ in range(20):
            state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, VisceralState)
        assert 0.0 <= state.visceral_level <= 1.0
        assert 0.0 <= state.afferent_strength <= 1.0
        assert isinstance(state.reflex_active, bool)
        assert 0.0 <= state.liking <= 1.0
        assert np.isfinite(state.wanting)
        assert np.isfinite(state.approach_strength)

    def test_hook_fields_clamped(self):
        """H26: afferent_strength and H27: liking are always clamped to [0, 1]."""
        nts = _make_mock_nts()
        # Return out-of-range afferent_strength
        nts.process.return_value = {
            'overall_visceral': 0.5,
            'afferent_strength': 1.8,  # out of range!
            'reflex_active': False,
            'cardiovascular_state': 0.5,
            'respiratory_state': 0.5,
            'gi_state': 0.5,
        }
        vp = _make_mock_vp()
        # Return out-of-range liking_response
        vp.process.return_value = {
            'liking': {
                'liking_response': -0.5,  # out of range!
                'hedonic_value': 0.5,
                'pleasure_amplification': 1.0,
            },
            'motor': {
                'motor_output': 0.4,
                'approach_strength': 0.45,
                'consummatory_drive': 0.3,
            },
            'opioid_level': 0.5,
            'wanting_signal': 0.5,
        }
        bridge = _make_bridge(nts=nts, vp=vp)
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert 0.0 <= state.afferent_strength <= 1.0, (
            f"H26: afferent_strength {state.afferent_strength} not in [0,1]"
        )
        assert 0.0 <= state.liking <= 1.0, (
            f"H27: liking {state.liking} not in [0,1]"
        )


class TestVisceralBridgeGetState:
    """get_state() introspection."""

    def test_get_state(self):
        from core.visceral_bridge import VisceralState
        bridge = _make_bridge()
        bridge.update(_ring_activations(), _prediction_errors())
        state = bridge.get_state()
        assert isinstance(state, VisceralState)
        assert state.visceral_level == pytest.approx(0.5, abs=0.01)


class TestVisceralBridgeNoModules:
    """Skeleton behaviour when all modules are None."""

    def test_skeleton_no_modules(self):
        """update() with no modules returns default-ish state, no crash."""
        from core.visceral_bridge import VisceralBridge, VisceralState
        bridge = VisceralBridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, VisceralState)
        assert 0.0 <= state.afferent_strength <= 1.0
        assert 0.0 <= state.liking <= 1.0


class TestVisceralBridgeVPNested:
    """VP nested dict handling."""

    def test_vp_nested_dict_handling(self):
        """VP nested dict correctly extracted for liking and approach_strength."""
        vp = _make_mock_vp()
        vp.process.return_value = {
            'liking': {
                'liking_response': 0.82,
                'hedonic_value': 0.75,
                'pleasure_amplification': 1.8,
            },
            'motor': {
                'motor_output': 0.55,
                'approach_strength': 0.72,
                'consummatory_drive': 0.45,
            },
            'opioid_level': 0.6,
            'wanting_signal': 0.5,
        }
        bridge = _make_bridge(vp=vp)
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert state.liking == pytest.approx(0.82, abs=0.01)
        assert state.approach_strength == pytest.approx(0.72, abs=0.01)


class TestVisceralBridgeIntegration:
    """Integration test with real neuroscience modules."""

    def test_integration_with_real_modules(self):
        from core.nucleus_tractus_solitarius import NucleusTractSolitarius
        from core.ventral_pallidum import VentralPallidum
        from core.visceral_bridge import VisceralBridge, VisceralState

        nts = NucleusTractSolitarius()
        vp = VentralPallidum()
        bridge = VisceralBridge(
            nucleus_tractus_solitarius=nts,
            ventral_pallidum=vp,
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

        assert isinstance(state, VisceralState)
        assert 0.0 <= state.afferent_strength <= 1.0
        assert 0.0 <= state.liking <= 1.0
