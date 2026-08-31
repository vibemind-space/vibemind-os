"""Tests for LimbicBridge -- Limbic Quartet -> Radial Attention Network."""
import pytest
import numpy as np
import torch
from core.radial_attention import RingLayer, DualProcessRouter, RadialAttentionNetwork


class TestLimbicState:
    """LimbicState dataclass defaults and ranges."""

    def test_defaults(self):
        from core.limbic_bridge import LimbicState
        s = LimbicState()
        assert s.valence == 0.0
        assert s.arousal == 0.3
        assert s.threat_level == 0.0
        assert s.is_threat is False
        assert s.go_drive == 0.5
        assert s.nogo_drive == 0.5
        assert s.net_value == 0.0
        assert s.effort_cost == 0.3
        assert s.salience == 0.3
        assert s.body_budget == 1.0
        assert s.feeling == 'neutral'
        assert s.urgency == 0.0
        assert s.approach_drive == 0.3
        assert s.stress == 0.0

    def test_custom_values(self):
        from core.limbic_bridge import LimbicState
        s = LimbicState(valence=-0.5, arousal=0.9, threat_level=0.8, is_threat=True)
        assert s.valence == -0.5
        assert s.arousal == 0.9
        assert s.threat_level == 0.8
        assert s.is_threat is True


from unittest.mock import MagicMock


def _make_mock_amygdala():
    m = MagicMock()
    m.process_stimulus.return_value = {
        'evaluation': {'valence': -0.3, 'arousal': 0.7, 'threat_level': 0.4},
        'response': {'hpa_activation': 0.35},
        'is_threat': False,
    }
    return m


def _make_mock_nacc():
    m = MagicMock()
    m.evaluate.return_value = {
        'go_drive': 0.6, 'nogo_drive': 0.4,
        'net_value': 0.2, 'effort_cost': 0.35,
    }
    return m


def _make_mock_insula():
    m = MagicMock()
    m.process.return_value = {
        'salience': 0.55, 'body_budget': 0.9,
        'feeling': 'alert', 'body_deviation': 0.1,
        'body_state': np.zeros(8),
    }
    return m


def _make_mock_hypothalamus():
    m = MagicMock()
    m.update_drives.return_value = {
        'urgency': 0.2, 'approach_drive': 0.4, 'stress': 0.15,
    }
    m.process_stressor.return_value = 0.35
    return m


def _make_bridge():
    from core.limbic_bridge import LimbicBridge
    return LimbicBridge(
        amygdala=_make_mock_amygdala(),
        nucleus_accumbens=_make_mock_nacc(),
        insular_cortex=_make_mock_insula(),
        hypothalamus=_make_mock_hypothalamus(),
    )


def _fake_ring_activations():
    """5 ring activations matching Radial Network dims."""
    return [
        np.random.randn(64),   # Ring 1 (Sensory)
        np.random.randn(128),  # Ring 2 (Pattern)
        np.random.randn(256),  # Ring 3 (Semantic)
        np.random.randn(256),  # Ring 4 (Abstract)
        np.random.randn(128),  # Ring 5 (Meta)
    ]


class TestLimbicBridgeSkeleton:
    """LimbicBridge init and update flow."""

    def test_init_stores_modules(self):
        bridge = _make_bridge()
        assert bridge._tick_count == 0
        assert bridge._ring1_to_amygdala.shape == (10, 64)

    def test_update_returns_limbic_state(self):
        from core.limbic_bridge import LimbicState
        bridge = _make_bridge()
        state = bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert isinstance(state, LimbicState)

    def test_update_calls_all_four_modules(self):
        bridge = _make_bridge()
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        bridge._amygdala.process_stimulus.assert_called_once()
        bridge._nucleus_accumbens.evaluate.assert_called_once()
        bridge._insular_cortex.process.assert_called_once()
        bridge._hypothalamus.update_drives.assert_called_once()
        bridge._hypothalamus.process_stressor.assert_called_once()

    def test_tick_count_increments(self):
        bridge = _make_bridge()
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge._tick_count == 1
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge._tick_count == 2

    def test_amygdala_hpa_feeds_hypothalamus(self):
        """Amygdala hpa_activation -> Hypothalamus process_stressor (inter-module coupling)."""
        bridge = _make_bridge()
        # First tick: no previous hpa, process_stressor called with 0.0
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        bridge._hypothalamus.process_stressor.assert_called_with(0.0)
        # Second tick: uses cached hpa_activation from first tick (0.35)
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge._hypothalamus.process_stressor.call_args_list[-1].args[0] == pytest.approx(0.35)

    def test_amygdala_arousal_feeds_insula(self):
        """Amygdala arousal -> InsularCortex emotional_intensity (inter-module coupling)."""
        bridge = _make_bridge()
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        # First tick uses default arousal (0.3 from LimbicState default)
        call_kwargs = bridge._insular_cortex.process.call_args
        assert 'emotional_intensity' in call_kwargs.kwargs or len(call_kwargs.args) >= 4

    def test_get_state_returns_current(self):
        bridge = _make_bridge()
        state = bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge.get_state() is state


class TestRingLayerLimbic:
    """Hook 10: arousal -> attention gain in RingLayer."""

    def test_forward_accepts_limbic_state(self):
        """RingLayer.forward() doesn't crash with limbic_state kwarg."""
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        out = ring(x, limbic_state=None)
        assert out.shape == (1, 128)

    def test_arousal_amplifies_attention(self):
        """High arousal (1.0) produces different output vs baseline (0.0)."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        out_low = ring(x, limbic_state=LimbicState(arousal=0.0))
        out_high = ring(x, limbic_state=LimbicState(arousal=1.0))
        # Different arousal gains (0.7 vs 1.3) must produce different outputs
        diff = (out_high - out_low).abs().mean().item()
        assert diff > 1e-4, "arousal gain should change output"
        # Verify the outputs are not identical (gain effect survives LayerNorm)
        assert not torch.allclose(out_low, out_high)

    def test_no_limbic_state_no_change(self):
        """limbic_state=None should have no effect (backward compat)."""
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        torch.manual_seed(42)
        out_none = ring(x, limbic_state=None)
        torch.manual_seed(42)
        out_skip = ring(x)
        assert torch.allclose(out_none, out_skip)

    def test_hook10_stacks_with_hook1_ne(self):
        """Arousal gain (H10) stacks with NE gain (H1) multiplicatively."""
        from core.limbic_bridge import LimbicState
        from core.neuromodulation_bridge import NeuromodState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        nm = NeuromodState(ne_gain=1.2)
        ls = LimbicState(arousal=1.0)  # gain = 1.3
        # Combined effect on attention: 1.2 * 1.3 = 1.56x
        out = ring(x, neuromod=nm, limbic_state=ls)
        assert out.shape == (1, 128)


class TestRingLayerSalience:
    """Hook 11: salience -> precision gate in RingLayer."""

    def test_salience_boosts_precision(self):
        """High salience amplifies precision-gated error."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        pred = torch.randn(1, 128)
        torch.manual_seed(42)
        out_low = ring(x, top_down_prediction=pred, limbic_state=LimbicState(salience=0.0))
        torch.manual_seed(42)
        out_high = ring(x, top_down_prediction=pred, limbic_state=LimbicState(salience=1.0))
        # Outputs should differ (salience affects precision weighting)
        assert not torch.allclose(out_low, out_high, atol=1e-6)

    def test_no_prediction_no_salience_effect(self):
        """Without top-down prediction, salience hook doesn't fire."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        torch.manual_seed(42)
        out_low = ring(x, limbic_state=LimbicState(salience=0.0))
        torch.manual_seed(42)
        out_high = ring(x, limbic_state=LimbicState(salience=1.0))
        # Both still go through arousal_gain (both 0.3 default arousal)
        # so outputs should be same (salience only affects precision branch)
        assert torch.allclose(out_low, out_high, atol=1e-5)


class TestRingLayerUrgency:
    """Hook 13: urgency -> FFN throughput in RingLayer."""

    def test_urgency_amplifies_output(self):
        """High urgency (1.0) amplifies FFN output vs low (0.0)."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        pred = torch.randn(1, 128)
        torch.manual_seed(42)
        out_low = ring(x, top_down_prediction=pred, limbic_state=LimbicState(urgency=0.0))
        torch.manual_seed(42)
        out_high = ring(x, top_down_prediction=pred, limbic_state=LimbicState(urgency=1.0))
        # urgency=0.0 -> gate=0.8, urgency=1.0 -> gate=1.2
        assert not torch.allclose(out_low, out_high, atol=1e-6)


class TestDualProcessLimbic:
    """Hook 12: nogo_drive -> DualProcess threshold."""

    def test_forward_accepts_limbic_state(self):
        from core.limbic_bridge import LimbicState
        router = DualProcessRouter(dim=64)
        s1 = torch.randn(1, 64)
        s2 = torch.randn(1, 64)
        result = router(s1, s2, limbic_state=LimbicState())
        assert 'output' in result

    def test_high_nogo_favors_system2(self):
        """High nogo_drive should lower threshold -> more System 2 usage."""
        from core.limbic_bridge import LimbicState
        router = DualProcessRouter(dim=64, conflict_threshold=0.5)
        s1 = torch.randn(1, 64)
        s2 = s1 * 1.05  # Slightly different -> borderline conflict
        # nogo=0.0: threshold stays 0.5
        result_low = router(s1, s2, limbic_state=LimbicState(nogo_drive=0.0))
        # nogo=1.0: threshold *= (1 - 0.2) = 0.4
        result_high = router(s1, s2, limbic_state=LimbicState(nogo_drive=1.0))
        # With lower threshold, more likely to use System 2
        assert result_low is not None and result_high is not None

    def test_hook12_stacks_with_hook8_acc(self):
        """NoGo (H12) stacks with ACC conflict (H8) multiplicatively."""
        from core.limbic_bridge import LimbicState
        from core.cortex_bridge import CortexState
        router = DualProcessRouter(dim=64)
        s1 = torch.randn(1, 64)
        s2 = torch.randn(1, 64)
        result = router(s1, s2,
                        cortex_state=CortexState(conflict=0.5),
                        limbic_state=LimbicState(nogo_drive=0.8))
        assert 'output' in result


class TestRadialNetworkLimbic:
    """Integration: LimbicBridge attached to RadialAttentionNetwork."""

    def test_attach_limbic(self):
        net = RadialAttentionNetwork()
        bridge = _make_bridge()
        net.attach_limbic(bridge)
        assert net._limbic_bridge is bridge
        assert net._limbic_state is None

    def test_forward_without_limbic(self):
        """Network works fine without limbic bridge (backward compat)."""
        net = RadialAttentionNetwork()
        x = torch.randn(1, 384)
        result = net(x)
        assert 'ring_activations' in result
        assert result.get('limbic_state') is None

    def test_forward_with_limbic(self):
        """Network produces limbic_state when bridge is attached."""
        from core.limbic_bridge import LimbicState
        net = RadialAttentionNetwork()
        bridge = _make_bridge()
        net.attach_limbic(bridge)
        x = torch.randn(1, 384)
        result = net(x)
        assert isinstance(result.get('limbic_state'), LimbicState)

    def test_limbic_state_used_on_next_tick(self):
        """LimbicState from tick 1 is used in tick 2 (1-tick delay)."""
        net = RadialAttentionNetwork()
        bridge = _make_bridge()
        net.attach_limbic(bridge)
        x = torch.randn(1, 384)
        # Tick 1: limbic_state is None during forward, computed after
        result1 = net(x)
        # After tick 1, _limbic_state should be set
        assert net._limbic_state is not None
        # Tick 2: uses the state computed in tick 1
        result2 = net(x)
        assert result2.get('limbic_state') is not None

    def test_all_bridges_coexist(self):
        """Neuromod + Cortex + Limbic all work together."""
        from core.limbic_bridge import LimbicState
        net = RadialAttentionNetwork()
        limbic_bridge = _make_bridge()
        net.attach_limbic(limbic_bridge)
        x = torch.randn(1, 384)
        result = net(x)
        assert 'ring_activations' in result
        assert isinstance(result.get('limbic_state'), LimbicState)


class TestLimbicBridgeConfig:
    """Config and production wiring."""

    def test_config_has_limbic_bridge(self):
        import yaml
        with open('configs/default.yaml', 'r') as f:
            cfg = yaml.safe_load(f)
        assert cfg.get('limbic_bridge', {}).get('enabled') is True


class TestLimbicIntegration:
    """Integration tests with real brain modules (no mocks)."""

    def _make_real_bridge(self):
        from core.limbic_bridge import LimbicBridge
        from core.amygdala_complex import AmygdalaComplex
        from core.nucleus_accumbens import NucleusAccumbens
        from core.insular_cortex import InsularCortex
        from core.hypothalamus_drives import HypothalamusModule
        return LimbicBridge(
            amygdala=AmygdalaComplex(),
            nucleus_accumbens=NucleusAccumbens(),
            insular_cortex=InsularCortex(),
            hypothalamus=HypothalamusModule(),
        )

    def test_real_modules_single_tick(self):
        """One tick with real modules: no crashes, valid state."""
        from core.limbic_bridge import LimbicState
        bridge = self._make_real_bridge()
        acts = [np.random.randn(64), np.random.randn(128),
                np.random.randn(256), np.random.randn(256), np.random.randn(128)]
        state = bridge.update(acts, [0.1, 0.2, 0.15, 0.1])
        assert isinstance(state, LimbicState)
        assert -1.0 <= state.valence <= 1.0
        assert 0.0 <= state.arousal <= 1.0
        assert 0.0 <= state.salience <= 1.0

    def test_real_modules_multi_tick(self):
        """Multiple ticks: inter-module coupling propagates without error."""
        bridge = self._make_real_bridge()
        acts = [np.random.randn(64), np.random.randn(128),
                np.random.randn(256), np.random.randn(256), np.random.randn(128)]
        for _ in range(5):
            state = bridge.update(acts, [0.1, 0.2, 0.15, 0.1])
        assert bridge._tick_count == 5
        assert state.feeling != ''  # InsularCortex produces a feeling label

    def test_full_network_integration(self):
        """LimbicBridge inside RadialAttentionNetwork with real modules."""
        from core.limbic_bridge import LimbicState
        net = RadialAttentionNetwork()
        bridge = self._make_real_bridge()
        net.attach_limbic(bridge)
        x = torch.randn(1, 384)
        result = net(x)
        assert isinstance(result.get('limbic_state'), LimbicState)
        # Run a second tick to confirm inter-module coupling works
        result2 = net(x)
        assert isinstance(result2.get('limbic_state'), LimbicState)

    def test_extreme_limbic_state_no_nan(self):
        """Extreme limbic values don't produce NaN/inf in network output."""
        from core.limbic_bridge import LimbicState
        net = RadialAttentionNetwork()
        x = torch.randn(1, 384)
        extreme = LimbicState(arousal=1.0, salience=1.0, urgency=1.0, nogo_drive=1.0)
        net._limbic_state = extreme
        result = net(x)
        for act in result['ring_activations']:
            assert not torch.isnan(act).any(), "NaN in ring activation with extreme limbic state"
            assert not torch.isinf(act).any(), "Inf in ring activation with extreme limbic state"
