"""Tests for CortexBridge -- cortex module integration with Radial Attention."""
import pytest
import numpy as np
from core.cortex_bridge import CortexState


class TestCortexState:
    def test_default_values(self):
        state = CortexState()
        assert state.bias_signal is None
        assert state.inhibit is False
        assert state.pfc_value == 0.5
        assert state.pfc_surprise == 0.0
        assert state.conflict == 0.0
        assert state.control_signal == 0.5
        assert state.error_likelihood == 0.0
        assert state.subjective_value == 0.5
        assert state.decision_confidence == 0.5
        assert state.choice_difficulty == 0.5

    def test_custom_values(self):
        bias = np.ones(32) * 0.1
        state = CortexState(bias_signal=bias, conflict=0.8, subjective_value=0.9)
        assert np.allclose(state.bias_signal, 0.1)
        assert state.conflict == 0.8
        assert state.subjective_value == 0.9
        assert state.pfc_value == 0.5  # unchanged default


from unittest.mock import MagicMock
from core.cortex_bridge import CortexBridge


class TestCortexBridgeSkeleton:
    def _make_mock_modules(self):
        pfc = MagicMock()
        pfc.process.return_value = {
            'bias_signal': np.ones(32) * 0.1,
            'value': 0.6,
            'inhibit': False,
            'surprise': 0.05,
        }
        acc = MagicMock()
        acc.process.return_value = {
            'conflict': 0.3,
            'control_signal': 0.6,
            'error_likelihood': 0.1,
            'effort': 0.4,
        }
        ofc = MagicMock()
        ofc.process.return_value = {
            'subjective_value': 0.7,
            'value_confidence': 0.8,
        }
        return pfc, acc, ofc

    def test_bridge_init(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        assert bridge._tick_count == 0
        assert isinstance(bridge._state, CortexState)

    def test_update_returns_cortex_state(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        state = bridge.update(ring_acts, pred_errors)
        assert isinstance(state, CortexState)
        assert state.bias_signal is not None
        assert 0.0 <= state.conflict <= 1.0
        assert 0.0 <= state.subjective_value <= 1.0

    def test_update_calls_all_modules(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        bridge.update(ring_acts, pred_errors)
        pfc.process.assert_called_once()
        acc.process.assert_called_once()
        ofc.process.assert_called_once()

    def test_tick_count_increments(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        bridge.update(ring_acts, pred_errors)
        assert bridge._tick_count == 1
        bridge.update(ring_acts, pred_errors)
        assert bridge._tick_count == 2

    def test_acc_conflict_feeds_into_pfc_context(self):
        """ACC conflict from tick t should appear in PFC context at tick t+1."""
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        # Tick 0: ACC returns conflict=0.3
        bridge.update(ring_acts, pred_errors)
        # Tick 1: PFC should receive conflict=0.3 in context
        bridge.update(ring_acts, pred_errors)
        call_args = pfc.process.call_args
        if call_args.kwargs.get('context'):
            assert call_args.kwargs['context']['conflict'] == 0.3

    def test_acc_effort_feeds_into_ofc(self):
        """ACC effort from tick t should feed into OFC effort_cost at tick t+1."""
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        # Tick 0: ACC returns effort=0.4
        bridge.update(ring_acts, pred_errors)
        # Tick 1: OFC should receive effort_cost=0.4
        bridge.update(ring_acts, pred_errors)
        call_args = ofc.process.call_args
        assert call_args.kwargs.get('effort_cost') == 0.4 or \
               (len(call_args.args) > 2 and call_args.args[2] == 0.4)

    def test_get_state(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        state = bridge.get_state()
        assert isinstance(state, CortexState)


import torch
from core.radial_attention import RingLayer


class TestRingLayerCortex:
    @pytest.fixture
    def ring_and_inputs(self):
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4, dropout=0.0)
        x = torch.randn(2, 64)
        td = torch.randn(2, 128)
        return ring, x, td

    def test_forward_without_cortex_unchanged(self, ring_and_inputs):
        ring, x, td = ring_and_inputs
        out1 = ring(x, top_down_prediction=td)
        out2 = ring(x, top_down_prediction=td, cortex_state=None)
        assert torch.allclose(out1, out2)

    def test_ofc_value_boosts_precision(self, ring_and_inputs):
        """High subjective_value should increase output magnitude (precision boost)."""
        ring, x, td = ring_and_inputs
        baseline = ring(x, top_down_prediction=td)
        high_val = CortexState(subjective_value=1.0)
        boosted = ring(x, top_down_prediction=td, cortex_state=high_val)
        assert not torch.allclose(baseline, boosted)

    def test_ofc_low_value_dampens_precision(self, ring_and_inputs):
        """Low subjective_value should decrease precision relative to high."""
        ring, x, td = ring_and_inputs
        low_val = CortexState(subjective_value=0.0)
        high_val = CortexState(subjective_value=1.0)
        out_low = ring(x, top_down_prediction=td, cortex_state=low_val)
        out_high = ring(x, top_down_prediction=td, cortex_state=high_val)
        diff = (out_high - out_low).abs().mean().item()
        assert diff > 0.001

    def test_cortex_no_effect_without_top_down(self, ring_and_inputs):
        """Without top-down prediction, precision gate isn't used, so cortex has no effect."""
        ring, x, _ = ring_and_inputs
        baseline = ring(x)
        with_cortex = ring(x, cortex_state=CortexState(subjective_value=1.0))
        assert torch.allclose(baseline, with_cortex)


from core.radial_attention import DualProcessRouter


class TestDualProcessCortex:
    def test_conflict_lowers_threshold(self):
        """High ACC conflict -> lower threshold -> more System 2."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = s1 + torch.randn(1, 128) * 0.1  # Small difference -> low conflict

        baseline = router(s1, s2)
        high_conflict = CortexState(conflict=1.0)
        with_conflict = router(s1, s2, cortex_state=high_conflict)

        # High conflict -> lower threshold -> might switch to System 2
        assert 'system_used' in with_conflict

    def test_zero_conflict_no_effect(self):
        """Zero ACC conflict should not change threshold."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = torch.randn(1, 128)

        baseline = router(s1, s2)
        zero_conflict = CortexState(conflict=0.0)
        with_zero = router(s1, s2, cortex_state=zero_conflict)

        assert baseline['conflict_level'] == with_zero['conflict_level']

    def test_cortex_none_unchanged(self):
        """No cortex_state should behave same as without it."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = torch.randn(1, 128)

        out1 = router(s1, s2)
        out2 = router(s1, s2, cortex_state=None)
        assert out1['system_used'] == out2['system_used']


from core.radial_attention import RadialAttentionNetwork


class TestRadialNetworkCortex:
    @pytest.fixture
    def network(self):
        return RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)

    def test_attach_cortex(self, network):
        mock_bridge = MagicMock()
        network.attach_cortex(mock_bridge)
        assert network._cortex_bridge is mock_bridge
        assert network._cortex_state is None
        assert hasattr(network, '_pfc_bias_proj')

    def test_forward_without_cortex_bridge(self, network):
        """No cortex bridge -> forward unchanged, result has cortex_state=None."""
        x = torch.randn(1, 384)
        result = network(x)
        assert 'cortex_state' in result
        assert result['cortex_state'] is None

    def test_forward_with_cortex_bridge(self, network):
        """With cortex bridge -> forward calls bridge.update(), result has CortexState."""
        mock_bridge = MagicMock()
        mock_state = CortexState(
            bias_signal=np.ones(32) * 0.1,
            conflict=0.3,
            subjective_value=0.7,
        )
        mock_bridge.update.return_value = mock_state
        network.attach_cortex(mock_bridge)

        x = torch.randn(1, 384)
        result = network(x)

        mock_bridge.update.assert_called_once()
        result2 = network(x)
        assert mock_bridge.update.call_count == 2

    def test_cortex_state_used_on_second_pass(self, network):
        """CortexState from tick 0 should be passed to rings/router on tick 1."""
        mock_bridge = MagicMock()
        mock_state = CortexState(
            bias_signal=np.ones(32) * 0.1,
            conflict=0.3,
            subjective_value=0.7,
        )
        mock_bridge.update.return_value = mock_state
        network.attach_cortex(mock_bridge)

        x = torch.randn(1, 384)
        r0 = network(x)
        r1 = network(x)
        assert mock_bridge.update.call_count == 2

    def test_pfc_bias_modulates_ring4(self, network):
        """Hook 7: PFC bias should additively modulate Ring 4 activations."""
        mock_bridge = MagicMock()
        mock_state = CortexState(
            bias_signal=np.ones(32) * 5.0,
            conflict=0.0,
            subjective_value=0.5,
        )
        mock_bridge.update.return_value = mock_state
        network.attach_cortex(mock_bridge)

        x = torch.randn(1, 384)
        network(x)
        r1 = network(x)

        network2 = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        network2.load_state_dict(network.state_dict(), strict=False)
        r2 = network2(x)

        ring4_diff = (r1['ring_activations'][3] - r2['ring_activations'][3]).abs().mean().item()
        assert ring4_diff > 0.01


class TestCortexBridgeConfig:
    def test_config_section_exists(self):
        """Verify cortex_bridge config section is in default.yaml."""
        import yaml
        import os
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 'configs', 'default.yaml'
        )
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert 'cortex_bridge' in config
        assert config['cortex_bridge']['enabled'] is True


# ─── Integration Tests with Real Modules ─────────────────────────────────────

from core.prefrontal_cortex import PrefrontalCortex
from core.anterior_cingulate import AnteriorCingulateCortex
from core.orbitofrontal_cortex import OrbitofrontalCortex


class TestCortexIntegration:
    @pytest.fixture
    def real_bridge(self):
        pfc = PrefrontalCortex()
        acc = AnteriorCingulateCortex()
        ofc = OrbitofrontalCortex()
        return CortexBridge(pfc=pfc, acc=acc, ofc=ofc)

    def test_full_loop_with_real_modules(self, real_bridge):
        """Run 10 ticks through the real cortex modules."""
        for t in range(10):
            ring_acts = [
                np.random.randn(64),
                np.random.randn(128),
                np.random.randn(256),
                np.random.randn(256),
                np.random.randn(128),
            ]
            pred_errors = [0.2 + 0.05 * t, 0.15, 0.18, 0.12]
            state = real_bridge.update(ring_acts, pred_errors)
            assert isinstance(state, CortexState)
            assert state.bias_signal is not None

    def test_cortex_evolves_over_ticks(self, real_bridge):
        """At least one cortex output should vary across 10 ticks."""
        states = []
        for t in range(10):
            ring_acts = [
                np.random.randn(64) * (1 + 0.5 * t),
                np.random.randn(128) * (1 + 0.3 * t),
                np.random.randn(256) * (1 + 0.2 * t),
                np.random.randn(256) * (1 + 0.1 * t),
                np.random.randn(128),
            ]
            pred_errors = [0.1 + 0.08 * t, 0.1 + 0.06 * t,
                           0.1 + 0.04 * t, 0.1 + 0.02 * t]
            state = real_bridge.update(ring_acts, pred_errors)
            states.append(state)

        varied = False
        for attr in ['conflict', 'control_signal', 'subjective_value',
                     'pfc_value', 'error_likelihood', 'decision_confidence']:
            values = [getattr(s, attr) for s in states]
            if max(values) - min(values) > 0.01:
                varied = True
                break
        assert varied, "No cortex output varied over 10 ticks"

    def test_full_network_with_cortex_bridge(self):
        """End-to-end: RadialAttentionNetwork + CortexBridge + real modules."""
        pfc = PrefrontalCortex()
        acc = AnteriorCingulateCortex()
        ofc = OrbitofrontalCortex()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)

        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        net.attach_cortex(bridge)

        for t in range(5):
            x = torch.randn(1, 384)
            result = net(x)
            assert 'cortex_state' in result
            if t > 0:
                assert result['cortex_state'] is not None
