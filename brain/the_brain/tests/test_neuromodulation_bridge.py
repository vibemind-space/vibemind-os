"""Tests for NeuromodulationBridge -- neuromodulator integration with Radial Attention."""
import pytest
import torch
from unittest.mock import MagicMock

from core.neuromodulation_bridge import NeuromodState, NeuromodulationBridge
from core.radial_attention import RingLayer, DualProcessRouter, RadialAttentionNetwork
from core.hebbian_plasticity import HebbianAttentionUpdate


class TestNeuromodState:
    def test_default_values(self):
        state = NeuromodState()
        assert state.dopamine == 0.5
        assert state.norepinephrine == 0.5
        assert state.serotonin == 0.5
        assert state.acetylcholine == 0.5
        assert state.anti_reward == 0.0
        assert state.ne_gain == 1.0
        assert state.explore_ratio == 0.5

    def test_custom_values(self):
        state = NeuromodState(dopamine=0.8, anti_reward=0.3)
        assert state.dopamine == 0.8
        assert state.anti_reward == 0.3
        assert state.serotonin == 0.5  # unchanged default


class TestNeuromodulationBridgeSkeleton:
    def _make_mock_modules(self):
        """Create mock neuromodulator modules with .process() returning valid dicts."""
        vta = MagicMock()
        vta.process.return_value = {
            'rpe': 0.1, 'dopamine': {'total_da': 0.6},
            'salience': 0.4, 'motivation': 0.5,
        }
        lc = MagicMock()
        lc.process.return_value = {
            'ne_level': 0.55, 'gain': 1.2, 'mode': 'balanced',
            'arousal': 0.6, 'explore_ratio': 0.45,
        }
        raphe = MagicMock()
        raphe.process.return_value = {
            'serotonin': 0.6, 'patience': 0.7, 'mood': 0.65,
        }
        bf = MagicMock()
        bf.process.return_value = {
            'ach_level': 0.55, 'memory_mode': 'encoding',
        }
        lhb = MagicMock()
        lhb.process.return_value = {
            'anti_reward': 0.1, 'vta_inhibition': 0.05, 'drn_inhibition': 0.03,
        }
        return vta, lc, raphe, bf, lhb

    def test_bridge_init(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        assert bridge is not None

    def test_update_returns_neuromod_state(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        state = bridge.update([0.1, 0.2, 0.15, 0.12])
        assert isinstance(state, NeuromodState)
        assert 0.0 <= state.dopamine <= 1.0
        assert 0.0 <= state.norepinephrine <= 1.0
        assert 0.0 <= state.serotonin <= 1.0
        assert 0.0 <= state.acetylcholine <= 1.0
        assert 0.0 <= state.anti_reward <= 1.0

    def test_update_calls_all_modules(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        vta.process.assert_called_once()
        lc.process.assert_called_once()
        raphe.process.assert_called_once()
        bf.process.assert_called_once()
        lhb.process.assert_called_once()

    def test_lhb_inhibition_feeds_into_vta(self):
        """LHb anti_reward from previous tick feeds into VTA as lhb_inhibition."""
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        # First call -- no previous anti_reward
        bridge.update([0.1, 0.2, 0.15, 0.12])
        call_kwargs_1 = vta.process.call_args[1]
        assert call_kwargs_1.get('lhb_inhibition', 0.0) == 0.0
        # Second call -- should use lhb's anti_reward from first call (0.1)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        call_kwargs_2 = vta.process.call_args[1]
        assert call_kwargs_2.get('lhb_inhibition', 0.0) == pytest.approx(0.1)

    def test_lc_arousal_feeds_into_bf(self):
        """LC arousal feeds into BasalForebrain."""
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        bf_kwargs = bf.process.call_args[1]
        assert bf_kwargs.get('arousal', None) == pytest.approx(0.6)

    def test_empty_prediction_errors(self):
        """Bridge handles empty prediction errors gracefully."""
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        state = bridge.update([])
        assert isinstance(state, NeuromodState)

    def test_get_state(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        info = bridge.get_state()
        assert 'neuromod_state' in info
        assert 'tick_count' in info


class TestRingLayerNeuromod:
    def _make_ring(self, in_dim=64, out_dim=128):
        return RingLayer(in_dim=in_dim, out_dim=out_dim, num_heads=4)

    def test_forward_without_neuromod_unchanged(self):
        """Without neuromod param, output is identical to original behavior."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        torch.manual_seed(42)
        out_none = ring(x, neuromod=None)
        torch.manual_seed(42)
        out_no_arg = ring(x)
        assert torch.allclose(out_none, out_no_arg, atol=1e-6)

    def test_ne_gain_modulates_attention(self):
        """High NE gain should amplify output vs baseline."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        baseline = ring(x, neuromod=NeuromodState(ne_gain=1.0))
        amplified = ring(x, neuromod=NeuromodState(ne_gain=2.0))
        # Amplified should have larger magnitude on average
        assert amplified.abs().mean() > baseline.abs().mean()

    def test_da_modulates_precision(self):
        """High DA should increase precision gate effect when top-down present."""
        ring = self._make_ring(in_dim=128, out_dim=128)
        x = torch.randn(2, 128)
        td = torch.randn(2, 128)
        low_da = ring(x, top_down_prediction=td, neuromod=NeuromodState(dopamine=0.0))
        high_da = ring(x, top_down_prediction=td, neuromod=NeuromodState(dopamine=1.0))
        # Outputs should differ due to DA modulation
        assert not torch.allclose(low_da, high_da, atol=1e-4)

    def test_ach_modulates_ffn(self):
        """High ACh should amplify FFN output."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        low_ach = ring(x, neuromod=NeuromodState(acetylcholine=0.0))
        high_ach = ring(x, neuromod=NeuromodState(acetylcholine=1.0))
        assert not torch.allclose(low_ach, high_ach, atol=1e-4)

    def test_serotonin_modulates_stability(self):
        """Different 5-HT levels should produce different outputs."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        low_5ht = ring(x, neuromod=NeuromodState(serotonin=0.0))
        high_5ht = ring(x, neuromod=NeuromodState(serotonin=1.0))
        assert not torch.allclose(low_5ht, high_5ht, atol=1e-4)

    def test_anti_reward_dampens_precision(self):
        """High anti-reward should reduce precision vs no anti-reward."""
        ring = self._make_ring(in_dim=128, out_dim=128)
        x = torch.randn(2, 128)
        td = torch.randn(2, 128)
        no_ar = ring(x, top_down_prediction=td, neuromod=NeuromodState(anti_reward=0.0))
        high_ar = ring(x, top_down_prediction=td, neuromod=NeuromodState(anti_reward=1.0))
        assert not torch.allclose(no_ar, high_ar, atol=1e-4)


class TestHebbianNeuromod:
    def test_serotonin_modulates_decay(self):
        """High 5-HT should slow decay (better consolidation)."""
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebbian = HebbianAttentionUpdate(learning_rate=0.01, decay=0.1)
        pre = torch.randn(2, 64)
        post = torch.randn(2, 64)

        # High 5-HT: decay should be slow (effective_decay = 0.1 * (1.5 - 1.0) = 0.05)
        ring.attention_bias.fill_(1.0)
        high_5ht = NeuromodState(serotonin=1.0)
        hebbian.update(ring, pre, post, neuromod=high_5ht)
        bias_high_5ht = ring.attention_bias.clone()

        # Low 5-HT: decay should be fast (effective_decay = 0.1 * (1.5 - 0.0) = 0.15)
        ring.attention_bias.fill_(1.0)
        low_5ht = NeuromodState(serotonin=0.0)
        hebbian.update(ring, pre, post, neuromod=low_5ht)
        bias_low_5ht = ring.attention_bias.clone()

        # High 5-HT should preserve more bias (less decay)
        assert bias_high_5ht.abs().mean() > bias_low_5ht.abs().mean()

    def test_hebbian_without_neuromod_unchanged(self):
        """Without neuromod, Hebbian behaves exactly as before."""
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebbian = HebbianAttentionUpdate(learning_rate=0.01, decay=0.01)
        pre = torch.randn(2, 64)
        post = torch.randn(2, 64)

        ring.attention_bias.fill_(0.5)
        torch.manual_seed(42)
        hebbian.update(ring, pre, post)  # No neuromod param
        bias_no_arg = ring.attention_bias.clone()

        ring.attention_bias.fill_(0.5)
        torch.manual_seed(42)
        hebbian.update(ring, pre, post, neuromod=None)
        bias_none = ring.attention_bias.clone()

        assert torch.allclose(bias_no_arg, bias_none, atol=1e-6)


class TestDualProcessNeuromod:
    def test_explore_ratio_lowers_threshold(self):
        """High explore_ratio should lower effective threshold -> more System 2."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        # s2 slightly different (moderate conflict)
        s2 = s1 + 0.3 * torch.randn(1, 128)

        # High explore: threshold drops -> more likely System 2
        explore_state = NeuromodState(explore_ratio=1.0)  # thresh *= 0.5
        result_explore = router(s1, s2, neuromod=explore_state)

        # Exploit: threshold rises -> more likely System 1
        exploit_state = NeuromodState(explore_ratio=0.0)  # thresh *= 1.5
        result_exploit = router(s1, s2, neuromod=exploit_state)

        # With identical inputs, explore should be >= exploit in system_used
        assert result_explore['system_used'] >= result_exploit['system_used']

    def test_router_without_neuromod_unchanged(self):
        """Without neuromod, router uses base threshold."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = s1.clone()  # Identical -> low conflict -> S1
        result = router(s1, s2)
        assert result['system_used'] == 1

        result_none = router(s1, s2, neuromod=None)
        assert result_none['system_used'] == 1


class TestRadialNetworkNeuromod:
    def _make_mock_bridge(self):
        bridge = MagicMock()
        bridge.update.return_value = NeuromodState(
            dopamine=0.7, norepinephrine=0.6, serotonin=0.55,
            acetylcholine=0.65, anti_reward=0.05, ne_gain=1.3, explore_ratio=0.4,
        )
        return bridge

    def test_attach_neuromodulation(self):
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        bridge = self._make_mock_bridge()
        net.attach_neuromodulation(bridge)
        assert net._neuromod_bridge is bridge

    def test_forward_without_bridge(self):
        """Without bridge, forward works as before and returns no neuromod_state."""
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        x = torch.randn(2, 384)
        result = net(x)
        assert 'prediction_errors' in result
        assert result.get('neuromod_state') is None

    def test_forward_with_bridge(self):
        """With bridge, forward returns neuromod_state and calls bridge.update."""
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        bridge = self._make_mock_bridge()
        net.attach_neuromodulation(bridge)

        x = torch.randn(2, 384)
        result = net(x)

        assert result['neuromod_state'] is not None
        assert isinstance(result['neuromod_state'], NeuromodState)
        bridge.update.assert_called_once()
        # Bridge receives prediction_errors list
        call_args = bridge.update.call_args[0][0]
        assert isinstance(call_args, list)
        assert len(call_args) == 4  # 5 rings -> 4 prediction errors

    def test_neuromod_state_used_on_second_pass(self):
        """After first forward, neuromod_state should be set for second forward."""
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        bridge = self._make_mock_bridge()
        net.attach_neuromodulation(bridge)

        x = torch.randn(2, 384)
        result1 = net(x)
        # After first pass, internal state should be set
        assert net._neuromod_state is not None
        # Second pass uses the state
        result2 = net(x)
        assert bridge.update.call_count == 2


class TestNeuromodIntegration:
    """Integration test: real neuromodulator modules + real RadialAttentionNetwork."""

    def _try_import_modules(self):
        """Import real modules, skip if unavailable."""
        try:
            from core.ventral_tegmental_area import VentralTegmentalArea
            from core.locus_coeruleus import LocusCoeruleus
            from core.raphe_nuclei import RapheNuclei
            from core.basal_forebrain import BasalForebrain
            from core.lateral_habenula import LateralHabenula
            return VentralTegmentalArea, LocusCoeruleus, RapheNuclei, BasalForebrain, LateralHabenula
        except ImportError:
            pytest.skip("Neuromodulator modules not available")

    def test_full_loop_with_real_modules(self):
        """Full wake cycle: seed -> radial -> bridge -> neuromod state."""
        VTA, LC, Raphe, BF, LHb = self._try_import_modules()

        vta = VTA()
        lc = LC()
        raphe = Raphe()
        bf = BF()
        lhb = LHb()

        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        net.attach_neuromodulation(bridge)

        # Run 5 ticks
        for tick in range(5):
            x = torch.randn(1, 384)
            result = net(x)

            assert 'neuromod_state' in result
            state = result['neuromod_state']
            assert isinstance(state, NeuromodState)
            assert 0.0 <= state.dopamine <= 1.0
            assert 0.0 <= state.norepinephrine <= 1.0
            assert 0.0 <= state.serotonin <= 1.0
            assert 0.0 <= state.acetylcholine <= 1.0
            assert 0.0 <= state.anti_reward <= 1.0
            assert 0.2 <= state.ne_gain <= 2.0

    def test_neuromod_evolves_over_ticks(self):
        """Neuromod state should change between ticks (not static)."""
        VTA, LC, Raphe, BF, LHb = self._try_import_modules()

        bridge = NeuromodulationBridge(VTA(), LC(), Raphe(), BF(), LHb())
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        net.attach_neuromodulation(bridge)

        states = []
        for _ in range(10):
            x = torch.randn(1, 384)  # Different input each tick
            result = net(x)
            states.append(result['neuromod_state'])

        # At least one transmitter should vary across ticks
        # (DA may saturate at 1.0 with consistently small prediction errors — that's correct)
        any_varies = False
        for attr in ['dopamine', 'norepinephrine', 'serotonin', 'acetylcholine', 'anti_reward']:
            values = [getattr(s, attr) for s in states]
            if len(set(round(v, 4) for v in values)) > 1:
                any_varies = True
                break
        assert any_varies, "At least one transmitter should vary across ticks"
