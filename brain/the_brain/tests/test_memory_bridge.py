"""
Tests for MemoryBridge -- connects memory-related brain modules
(SeptalNuclei, EntorhinalCortex, MammillaryBodies, InferiorOlive)
to the Radial Attention Network.

15 tests covering defaults, module calls, coupling, stability, hooks,
get_state, skeleton mode, and integration with real modules.
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from core.memory_bridge import MemoryBridge, MemoryState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ring_activations():
    """Standard 5-ring activations for testing."""
    return [
        np.random.randn(64),   # Ring 1: Sensory
        np.random.randn(128),  # Ring 2: Pattern
        np.random.randn(256),  # Ring 3: Semantic
        np.random.randn(256),  # Ring 4: Abstract
        np.random.randn(128),  # Ring 5: Meta
    ]


def _make_prediction_errors():
    """Standard 4-element prediction errors."""
    return [0.1, 0.2, 0.15, 0.1]


def _mock_septal_nuclei():
    """Mock SeptalNuclei with realistic process() output."""
    m = MagicMock()
    m.process.return_value = {
        'theta_frequency': 6.0,
        'theta_power': 0.5,
        'theta_phase': 1.57,
        'memory_phase': 'encoding',
        'n_gamma_slots': 4,
        'coupling_strength': 0.8,
        'approach_drive': 0.0,
        'avoid_drive': 0.0,
    }
    return m


def _mock_entorhinal_cortex():
    """Mock EntorhinalCortex with realistic process_input() output."""
    m = MagicMock()
    m.process_input.return_value = np.random.randn(16).astype(np.float32)
    return m


def _mock_mammillary_bodies():
    """Mock MammillaryBodies with realistic process() output."""
    m = MagicMock()
    m.process.return_value = {
        'relayed_signal': np.zeros(16),
        'spatial_code': np.zeros(10),
        'consolidation_strength': 0.6,
        'head_direction_estimate': 0.0,
        'relay_strength': 0.5,
    }
    return m


def _mock_inferior_olive():
    """Mock InferiorOlive with realistic process() output."""
    m = MagicMock()
    m.process.return_value = {
        'error_magnitude': 0.15,
        'teaching_signal': [0.1, 0.05, -0.02, 0.0, 0.0, 0.0, 0.0, 0.0],
        'spike_probability': 0.78,
        'timing_signal': {'progress_fraction': 0.0, 'timing_error': 0.0, 'sync_quality': 1.0},
        'oscillator_phase': 0.63,
        'error_trend': 'stable',
    }
    return m


def _build_bridge(**overrides):
    """Build a MemoryBridge with mocked modules (overridable)."""
    kwargs = {
        'septal_nuclei': _mock_septal_nuclei(),
        'entorhinal_cortex': _mock_entorhinal_cortex(),
        'mammillary_bodies': _mock_mammillary_bodies(),
        'inferior_olive': _mock_inferior_olive(),
    }
    kwargs.update(overrides)
    return MemoryBridge(**kwargs)


# ===========================================================================
# Tests
# ===========================================================================


class TestMemoryBridge:
    """Tests for MemoryBridge."""

    # 1. test_state_defaults
    def test_state_defaults(self):
        """MemoryState dataclass has expected defaults."""
        state = MemoryState()
        assert state.theta_power == 0.5
        assert state.theta_frequency == 6.0
        assert state.coupling_strength == 0.5
        assert state.consolidation_strength == 0.5
        assert state.relay_strength == 0.5
        assert state.teaching_signal == 0.0
        assert state.error_magnitude == 0.0
        assert state.memory_gateway == 0.5

    # 2. test_init_stores_modules
    def test_init_stores_modules(self):
        """Bridge stores all four module references."""
        sn = _mock_septal_nuclei()
        ec = _mock_entorhinal_cortex()
        mb = _mock_mammillary_bodies()
        io = _mock_inferior_olive()
        bridge = MemoryBridge(
            septal_nuclei=sn,
            entorhinal_cortex=ec,
            mammillary_bodies=mb,
            inferior_olive=io,
        )
        assert bridge._septal_nuclei is sn
        assert bridge._entorhinal_cortex is ec
        assert bridge._mammillary_bodies is mb
        assert bridge._inferior_olive is io

    # 3. test_init_no_modules
    def test_init_no_modules(self):
        """Bridge can be constructed with None modules (skeleton mode)."""
        bridge = MemoryBridge(
            septal_nuclei=None,
            entorhinal_cortex=None,
            mammillary_bodies=None,
            inferior_olive=None,
        )
        assert bridge._septal_nuclei is None
        assert bridge._entorhinal_cortex is None
        assert bridge._mammillary_bodies is None
        assert bridge._inferior_olive is None

    # 4. test_update_returns_state
    def test_update_returns_state(self):
        """update() returns a MemoryState instance."""
        bridge = _build_bridge()
        state = bridge.update(_make_ring_activations(), _make_prediction_errors())
        assert isinstance(state, MemoryState)

    # 5. test_update_calls_septal_nuclei
    def test_update_calls_septal_nuclei(self):
        """update() calls SeptalNuclei.process() with correct args."""
        sn = _mock_septal_nuclei()
        bridge = _build_bridge(septal_nuclei=sn)
        pes = [0.1, 0.2, 0.15, 0.1]
        bridge.update(_make_ring_activations(), pes)

        sn.process.assert_called_once()
        call_kwargs = sn.process.call_args
        # Should pass arousal=0.5 and memory_demand=avg_pe
        assert call_kwargs[1]['arousal'] == 0.5
        avg_pe = sum(pes) / len(pes)
        assert abs(call_kwargs[1]['memory_demand'] - avg_pe) < 1e-6

    # 6. test_update_calls_entorhinal_cortex
    def test_update_calls_entorhinal_cortex(self):
        """update() calls EntorhinalCortex.process_input() with ring1."""
        ec = _mock_entorhinal_cortex()
        bridge = _build_bridge(entorhinal_cortex=ec)
        rings = _make_ring_activations()
        bridge.update(rings, _make_prediction_errors())

        ec.process_input.assert_called_once()
        call_args = ec.process_input.call_args[0]
        # First positional arg should be ring1 (64-dim)
        np.testing.assert_array_equal(call_args[0], rings[0])

    # 7. test_update_calls_mammillary_bodies
    def test_update_calls_mammillary_bodies(self):
        """update() calls MammillaryBodies.process() with correct args."""
        mb = _mock_mammillary_bodies()
        bridge = _build_bridge(mammillary_bodies=mb)
        bridge.update(_make_ring_activations(), _make_prediction_errors())

        mb.process.assert_called_once()
        call_kwargs = mb.process.call_args[1]
        assert 'hippocampal_signal' in call_kwargs
        assert 'importance' in call_kwargs
        assert 'emotional_arousal' in call_kwargs
        assert call_kwargs['emotional_arousal'] == 0.5

    # 8. test_update_calls_inferior_olive
    def test_update_calls_inferior_olive(self):
        """update() calls InferiorOlive.process() with sliced ring1/ring2."""
        io = _mock_inferior_olive()
        bridge = _build_bridge(inferior_olive=io)
        rings = _make_ring_activations()
        bridge.update(rings, _make_prediction_errors())

        io.process.assert_called_once()
        call_kwargs = io.process.call_args[1]
        # prediction = ring2[:8], actual = ring1[:8]
        assert len(call_kwargs['prediction']) == 8
        assert len(call_kwargs['actual']) == 8

    # 9. test_sn_mb_coupling -- SN theta_power feeds MB importance on next tick
    def test_sn_mb_coupling(self):
        """SeptalNuclei theta_power feeds MammillaryBodies importance on next tick."""
        sn = _mock_septal_nuclei()
        mb = _mock_mammillary_bodies()

        # Tick 1: SN returns theta_power=0.7
        sn.process.return_value = {
            'theta_frequency': 6.0,
            'theta_power': 0.7,
            'theta_phase': 1.57,
            'memory_phase': 'encoding',
            'n_gamma_slots': 4,
            'coupling_strength': 0.8,
            'approach_drive': 0.0,
            'avoid_drive': 0.0,
        }

        bridge = _build_bridge(septal_nuclei=sn, mammillary_bodies=mb)
        rings = _make_ring_activations()
        pes = _make_prediction_errors()

        # Tick 1: MB receives default _prev_theta_power (0.5)
        bridge.update(rings, pes)
        tick1_importance = mb.process.call_args[1]['importance']
        assert abs(tick1_importance - 0.5) < 1e-6, (
            f"Tick 1 should use default _prev_theta_power=0.5, got {tick1_importance}"
        )

        # Tick 2: MB should receive theta_power=0.7 from tick 1
        bridge.update(rings, pes)
        tick2_importance = mb.process.call_args[1]['importance']
        assert abs(tick2_importance - 0.7) < 1e-6, (
            f"Tick 2 should use SN theta_power=0.7 from tick 1, got {tick2_importance}"
        )

    # 10. test_ec_mb_coupling -- EC memory_gateway feeds MB hippocampal_signal on same tick
    def test_ec_mb_coupling(self):
        """EntorhinalCortex memory_gateway feeds MammillaryBodies hippocampal_signal on same tick."""
        ec = _mock_entorhinal_cortex()
        mb = _mock_mammillary_bodies()

        # EC returns a specific encoding
        encoding = np.ones(16, dtype=np.float32) * 0.5
        ec.process_input.return_value = encoding

        bridge = _build_bridge(entorhinal_cortex=ec, mammillary_bodies=mb)
        bridge.update(_make_ring_activations(), _make_prediction_errors())

        # MB hippocampal_signal should be the memory_gateway value (a float)
        mb_call = mb.process.call_args[1]
        hippocampal_signal = mb_call['hippocampal_signal']
        # memory_gateway = min(1.0, ec_norm / (sqrt(16) + 1e-8))
        ec_norm = float(np.linalg.norm(encoding))
        expected_gateway = min(1.0, ec_norm / (np.sqrt(len(encoding)) + 1e-8))
        assert abs(hippocampal_signal - expected_gateway) < 1e-6

    # 11. test_multi_tick_stability -- 20 ticks, all fields in range
    def test_multi_tick_stability(self):
        """20 ticks of update produce bounded fields."""
        bridge = _build_bridge()
        rings = _make_ring_activations()
        pes = _make_prediction_errors()

        for _ in range(20):
            state = bridge.update(rings, pes)
            assert 0.0 <= state.theta_power <= 1.0
            assert 4.0 <= state.theta_frequency <= 8.0 or state.theta_frequency == 6.0
            assert 0.0 <= state.coupling_strength <= 1.0
            assert 0.0 <= state.consolidation_strength <= 1.0
            assert state.relay_strength >= 0.0
            assert state.error_magnitude >= 0.0
            assert 0.0 <= state.memory_gateway <= 1.0

    # 12. test_hook_fields_clamped -- theta_power, consolidation_strength in [0,1]
    def test_hook_fields_clamped(self):
        """Hook fields (H21: theta_power, H22: consolidation_strength) are clamped to [0,1]."""
        sn = _mock_septal_nuclei()
        mb = _mock_mammillary_bodies()

        # SN returns out-of-range theta_power
        sn.process.return_value = {
            'theta_frequency': 6.0,
            'theta_power': 1.5,  # Out of range
            'theta_phase': 1.57,
            'memory_phase': 'encoding',
            'n_gamma_slots': 4,
            'coupling_strength': 0.8,
            'approach_drive': 0.0,
            'avoid_drive': 0.0,
        }

        # MB returns out-of-range relay_strength (consolidation_strength)
        mb.process.return_value = {
            'relayed_signal': np.zeros(16),
            'spatial_code': np.zeros(10),
            'consolidation_strength': 1.8,  # Out of range
            'head_direction_estimate': 0.0,
            'relay_strength': 2.0,  # Out of range
        }

        bridge = _build_bridge(septal_nuclei=sn, mammillary_bodies=mb)
        state = bridge.update(_make_ring_activations(), _make_prediction_errors())

        assert 0.0 <= state.theta_power <= 1.0, f"theta_power={state.theta_power} not in [0,1]"
        assert 0.0 <= state.consolidation_strength <= 1.0, (
            f"consolidation_strength={state.consolidation_strength} not in [0,1]"
        )

    # 13. test_get_state
    def test_get_state(self):
        """get_state() returns the MemoryState dataclass."""
        bridge = _build_bridge()
        bridge.update(_make_ring_activations(), _make_prediction_errors())
        state = bridge.get_state()

        assert isinstance(state, MemoryState)
        expected_fields = [
            'theta_power', 'theta_frequency', 'coupling_strength',
            'consolidation_strength', 'relay_strength', 'teaching_signal',
            'error_magnitude', 'memory_gateway',
        ]
        for field in expected_fields:
            assert hasattr(state, field), f"Missing field: {field}"

    # 14. test_skeleton_no_modules
    def test_skeleton_no_modules(self):
        """Bridge with None modules returns default MemoryState without crashing."""
        bridge = MemoryBridge(
            septal_nuclei=None,
            entorhinal_cortex=None,
            mammillary_bodies=None,
            inferior_olive=None,
        )
        state = bridge.update(_make_ring_activations(), _make_prediction_errors())
        assert isinstance(state, MemoryState)
        # Should return defaults
        assert state.theta_power == 0.5
        assert state.consolidation_strength == 0.5

    # 15. test_integration_with_real_modules
    def test_integration_with_real_modules(self):
        """Integration test with real brain module instances."""
        from core.septal_nuclei import SeptalNuclei
        from core.entorhinal_cortex import EntorhinalCortex
        from core.mammillary_bodies import MammillaryBodies
        from core.inferior_olive import InferiorOlive

        sn = SeptalNuclei()
        ec = EntorhinalCortex()
        mb = MammillaryBodies()
        io = InferiorOlive()

        bridge = MemoryBridge(
            septal_nuclei=sn,
            entorhinal_cortex=ec,
            mammillary_bodies=mb,
            inferior_olive=io,
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

        assert isinstance(state, MemoryState)
        assert 0 <= state.theta_power <= 1
        assert 0 <= state.consolidation_strength <= 1
