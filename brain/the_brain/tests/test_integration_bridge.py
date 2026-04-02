"""Tests for IntegrationBridge -- connects Claustrum, DMN, SuperiorColliculus,
CorticalColumn, and CorpusCallosum to the Radial Attention Network.

Hooks: H23 (binding_strength), H24 (dmn_activation), H25 (orienting_saliency).
"""
import unittest
from unittest.mock import MagicMock, patch

import numpy as np


class TestIntegrationStateDefaults(unittest.TestCase):
    """1. test_state_defaults"""

    def test_state_defaults(self):
        from core.integration_bridge import IntegrationState

        state = IntegrationState()
        self.assertAlmostEqual(state.binding_strength, 0.5)
        self.assertFalse(state.reached_consciousness)
        self.assertAlmostEqual(state.dmn_activation, 0.3)
        self.assertEqual(state.dmn_mode, 'default')
        self.assertAlmostEqual(state.orienting_saliency, 0.3)
        self.assertAlmostEqual(state.cortical_error, 0.0)
        self.assertAlmostEqual(state.cortical_output, 0.5)
        self.assertAlmostEqual(state.bilateral_coherence, 0.5)
        self.assertAlmostEqual(state.transfer_efficiency, 0.5)


class TestIntegrationBridgeInit(unittest.TestCase):
    """2. test_init_stores_modules and 3. test_init_no_modules"""

    def test_init_stores_modules(self):
        from core.integration_bridge import IntegrationBridge

        sc = MagicMock()
        dmn = MagicMock()
        cl = MagicMock()
        cc = MagicMock()
        corpus = MagicMock()
        bridge = IntegrationBridge(
            superior_colliculus=sc,
            default_mode_network=dmn,
            claustrum=cl,
            cortical_column=cc,
            corpus_callosum=corpus,
        )
        self.assertIs(bridge._superior_colliculus, sc)
        self.assertIs(bridge._default_mode_network, dmn)
        self.assertIs(bridge._claustrum, cl)
        self.assertIs(bridge._cortical_column, cc)
        self.assertIs(bridge._corpus_callosum, corpus)

    def test_init_no_modules(self):
        from core.integration_bridge import IntegrationBridge

        bridge = IntegrationBridge()
        self.assertIsNone(bridge._superior_colliculus)
        self.assertIsNone(bridge._default_mode_network)
        self.assertIsNone(bridge._claustrum)
        self.assertIsNone(bridge._cortical_column)
        self.assertIsNone(bridge._corpus_callosum)


class TestIntegrationBridgeUpdate(unittest.TestCase):
    """Tests 4-9: update calls each module correctly."""

    def _make_ring_activations(self):
        return [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]

    def _make_pes(self):
        return [0.1, 0.2, 0.15, 0.1]

    def test_update_returns_state(self):
        """4. test_update_returns_state"""
        from core.integration_bridge import IntegrationBridge, IntegrationState

        sc = MagicMock()
        sc.process.return_value = {'peak_saliency': 0.4}
        dmn = MagicMock()
        dmn_out = MagicMock()
        dmn_out.activation_level = 0.6
        dmn_out.mode = 'active'
        dmn.process.return_value = dmn_out
        cl = MagicMock()
        cl.process.return_value = {
            'binding_strength': np.eye(2) * 0.5,
            'reached_consciousness': True,
        }
        cc = MagicMock()
        cc.process.return_value = {
            'error_magnitude': 0.1,
            'output_magnitude': 0.6,
        }
        corpus = MagicMock()
        corpus.process.return_value = {
            'coordination_quality': 0.7,
            'transfer_efficiency': 0.8,
        }

        bridge = IntegrationBridge(
            superior_colliculus=sc,
            default_mode_network=dmn,
            claustrum=cl,
            cortical_column=cc,
            corpus_callosum=corpus,
        )
        state = bridge.update(self._make_ring_activations(), self._make_pes())
        self.assertIsInstance(state, IntegrationState)

    def test_update_calls_superior_colliculus(self):
        """5. test_update_calls_superior_colliculus"""
        from core.integration_bridge import IntegrationBridge

        sc = MagicMock()
        sc.process.return_value = {'peak_saliency': 0.5}
        bridge = IntegrationBridge(superior_colliculus=sc)
        bridge.update(self._make_ring_activations(), self._make_pes())
        sc.process.assert_called_once()
        _, kwargs = sc.process.call_args
        self.assertIn('visual', kwargs)
        self.assertEqual(len(kwargs['visual']), min(64, 16))

    def test_update_calls_dmn(self):
        """6. test_update_calls_dmn"""
        from core.integration_bridge import IntegrationBridge

        dmn = MagicMock()
        dmn_out = MagicMock()
        dmn_out.activation_level = 0.5
        dmn_out.mode = 'active'
        dmn.process.return_value = dmn_out
        bridge = IntegrationBridge(default_mode_network=dmn)
        bridge.update(self._make_ring_activations(), self._make_pes())
        dmn.process.assert_called_once()
        _, kwargs = dmn.process.call_args
        self.assertIn('state', kwargs)
        self.assertIn('task_load', kwargs)

    def test_update_calls_claustrum(self):
        """7. test_update_calls_claustrum"""
        from core.integration_bridge import IntegrationBridge

        cl = MagicMock()
        cl.process.return_value = {
            'binding_strength': np.eye(2) * 0.5,
            'reached_consciousness': False,
        }
        bridge = IntegrationBridge(claustrum=cl)
        bridge.update(self._make_ring_activations(), self._make_pes())
        cl.process.assert_called_once()
        _, kwargs = cl.process.call_args
        self.assertIn('modality_signals', kwargs)
        self.assertIn('salience', kwargs)
        self.assertIn('attention', kwargs)

    def test_update_calls_cortical_column(self):
        """8. test_update_calls_cortical_column"""
        from core.integration_bridge import IntegrationBridge

        cc = MagicMock()
        cc.process.return_value = {
            'error_magnitude': 0.2,
            'output_magnitude': 0.5,
        }
        bridge = IntegrationBridge(cortical_column=cc)
        bridge.update(self._make_ring_activations(), self._make_pes())
        cc.process.assert_called_once()
        _, kwargs = cc.process.call_args
        self.assertIn('thalamic_input', kwargs)
        self.assertIn('cortical_input', kwargs)

    def test_update_calls_corpus_callosum(self):
        """9. test_update_calls_corpus_callosum"""
        from core.integration_bridge import IntegrationBridge

        corpus = MagicMock()
        corpus.process.return_value = {
            'coordination_quality': 0.6,
            'transfer_efficiency': 0.7,
        }
        bridge = IntegrationBridge(corpus_callosum=corpus)
        bridge.update(self._make_ring_activations(), self._make_pes())
        corpus.process.assert_called_once()
        _, kwargs = corpus.process.call_args
        self.assertIn('left_signal', kwargs)
        self.assertIn('right_signal', kwargs)


class TestIntegrationBridgeCoupling(unittest.TestCase):
    """Tests 10-11: inter-module coupling via cached state."""

    def _make_ring_activations(self):
        return [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]

    def _make_pes(self):
        return [0.1, 0.2, 0.15, 0.1]

    def test_sc_claustrum_coupling(self):
        """10. SC saliency feeds Claustrum salience on next tick."""
        from core.integration_bridge import IntegrationBridge

        sc = MagicMock()
        sc.process.return_value = {'peak_saliency': 0.9}
        cl = MagicMock()
        cl.process.return_value = {
            'binding_strength': np.eye(2) * 0.5,
            'reached_consciousness': False,
        }
        bridge = IntegrationBridge(superior_colliculus=sc, claustrum=cl)

        # Tick 1: SC returns high saliency
        bridge.update(self._make_ring_activations(), self._make_pes())
        # After tick 1, _prev_saliency should have been updated to 0.9

        # Tick 2: Claustrum should receive the cached saliency from tick 1
        bridge.update(self._make_ring_activations(), self._make_pes())
        _, kwargs_t2 = cl.process.call_args
        self.assertAlmostEqual(kwargs_t2['salience'], 0.9, places=3)

    def test_dmn_claustrum_coupling(self):
        """11. DMN activation feeds Claustrum attention (inverse) on next tick."""
        from core.integration_bridge import IntegrationBridge

        dmn = MagicMock()
        dmn_out = MagicMock()
        dmn_out.activation_level = 0.8
        dmn_out.mode = 'active'
        dmn.process.return_value = dmn_out
        cl = MagicMock()
        cl.process.return_value = {
            'binding_strength': np.eye(2) * 0.5,
            'reached_consciousness': False,
        }
        bridge = IntegrationBridge(default_mode_network=dmn, claustrum=cl)

        # Tick 1: DMN returns 0.8 activation
        bridge.update(self._make_ring_activations(), self._make_pes())
        # After tick 1, _prev_dmn_activation should be 0.8

        # Tick 2: Claustrum attention should be 1.0 - 0.8 = 0.2
        bridge.update(self._make_ring_activations(), self._make_pes())
        _, kwargs_t2 = cl.process.call_args
        self.assertAlmostEqual(kwargs_t2['attention'], 0.2, places=3)


class TestIntegrationBridgeStability(unittest.TestCase):
    """12. test_multi_tick_stability -- 20 ticks, no crash."""

    def test_multi_tick_stability(self):
        from core.integration_bridge import IntegrationBridge, IntegrationState

        sc = MagicMock()
        sc.process.return_value = {'peak_saliency': 0.4}
        dmn = MagicMock()
        dmn_out = MagicMock()
        dmn_out.activation_level = 0.5
        dmn_out.mode = 'active'
        dmn.process.return_value = dmn_out
        cl = MagicMock()
        cl.process.return_value = {
            'binding_strength': np.eye(2) * 0.5,
            'reached_consciousness': False,
        }
        cc = MagicMock()
        cc.process.return_value = {
            'error_magnitude': 0.1,
            'output_magnitude': 0.5,
        }
        corpus = MagicMock()
        corpus.process.return_value = {
            'coordination_quality': 0.6,
            'transfer_efficiency': 0.7,
        }

        bridge = IntegrationBridge(
            superior_colliculus=sc,
            default_mode_network=dmn,
            claustrum=cl,
            cortical_column=cc,
            corpus_callosum=corpus,
        )
        ring_acts = [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]
        pes = [0.1, 0.2, 0.15, 0.1]

        for _ in range(20):
            state = bridge.update(ring_acts, pes)
        self.assertIsInstance(state, IntegrationState)


class TestHookFieldsClamped(unittest.TestCase):
    """13. test_hook_fields_clamped -- H23, H24, H25 in [0,1]."""

    def test_hook_fields_clamped(self):
        from core.integration_bridge import IntegrationBridge

        # Return extreme values to test clamping
        sc = MagicMock()
        sc.process.return_value = {'peak_saliency': 5.0}  # Above 1
        dmn = MagicMock()
        dmn_out = MagicMock()
        dmn_out.activation_level = -2.0  # Below 0
        dmn_out.mode = 'active'
        dmn.process.return_value = dmn_out
        cl = MagicMock()
        # binding_strength can be a matrix with values >1 -- we test clamping
        cl.process.return_value = {
            'binding_strength': np.ones((2, 2)) * 5.0,
            'reached_consciousness': True,
        }
        cc = MagicMock()
        cc.process.return_value = {
            'error_magnitude': 0.1,
            'output_magnitude': 0.5,
        }
        corpus = MagicMock()
        corpus.process.return_value = {
            'coordination_quality': 0.6,
            'transfer_efficiency': 0.7,
        }

        bridge = IntegrationBridge(
            superior_colliculus=sc,
            default_mode_network=dmn,
            claustrum=cl,
            cortical_column=cc,
            corpus_callosum=corpus,
        )
        ring_acts = [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]
        pes = [0.1, 0.2, 0.15, 0.1]

        state = bridge.update(ring_acts, pes)

        # H23: binding_strength in [0, 1]
        self.assertGreaterEqual(state.binding_strength, 0.0)
        self.assertLessEqual(state.binding_strength, 1.0)

        # H24: dmn_activation in [0, 1]
        self.assertGreaterEqual(state.dmn_activation, 0.0)
        self.assertLessEqual(state.dmn_activation, 1.0)

        # H25: orienting_saliency in [0, 1]
        self.assertGreaterEqual(state.orienting_saliency, 0.0)
        self.assertLessEqual(state.orienting_saliency, 1.0)


class TestSkeletonNoModules(unittest.TestCase):
    """14. test_skeleton_no_modules -- runs with all modules None."""

    def test_skeleton_no_modules(self):
        from core.integration_bridge import IntegrationBridge, IntegrationState

        bridge = IntegrationBridge()
        ring_acts = [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]
        pes = [0.1, 0.2, 0.15, 0.1]

        state = bridge.update(ring_acts, pes)
        self.assertIsInstance(state, IntegrationState)
        # Should return defaults when no modules present
        self.assertAlmostEqual(state.binding_strength, 0.5)
        self.assertAlmostEqual(state.dmn_activation, 0.3)
        self.assertEqual(state.dmn_mode, 'default')
        self.assertAlmostEqual(state.orienting_saliency, 0.3)


class TestIntegrationWithRealModules(unittest.TestCase):
    """15. test_integration_with_real_modules -- full integration test."""

    def test_integration_with_real_modules(self):
        from core.superior_colliculus import SuperiorColliculus
        from core.default_mode_network import DefaultModeNetwork
        from core.claustrum import Claustrum
        from core.cortical_column import CorticalColumn
        from core.corpus_callosum import CorpusCallosum
        from core.integration_bridge import IntegrationBridge, IntegrationState

        sc = SuperiorColliculus()
        dmn = DefaultModeNetwork()
        cl = Claustrum()
        cc = CorticalColumn()
        corpus = CorpusCallosum()
        bridge = IntegrationBridge(
            superior_colliculus=sc,
            default_mode_network=dmn,
            claustrum=cl,
            cortical_column=cc,
            corpus_callosum=corpus,
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
        self.assertIsInstance(state, IntegrationState)
        self.assertGreaterEqual(state.binding_strength, 0.0)
        self.assertLessEqual(state.binding_strength, 1.0)
        self.assertGreaterEqual(state.dmn_activation, 0.0)
        self.assertLessEqual(state.dmn_activation, 1.0)
        self.assertGreaterEqual(state.orienting_saliency, 0.0)
        self.assertLessEqual(state.orienting_saliency, 1.0)


if __name__ == '__main__':
    unittest.main()
