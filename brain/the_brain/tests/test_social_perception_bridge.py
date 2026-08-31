"""
Tests for SocialPerceptionBridge -- connects OlfactorySystem, FusiformGyrus,
and TemporoparietalJunction to the Radial Attention Network.

15 tests covering state defaults, module wiring, coupling, hooks, and integration.
"""

import unittest
from unittest.mock import MagicMock, patch
from dataclasses import fields as dc_fields

import numpy as np

from core.social_perception_bridge import SocialPerceptionBridge, SocialPerceptionState


class TestSocialPerceptionState(unittest.TestCase):
    """Test 1: SocialPerceptionState defaults."""

    def test_state_defaults(self):
        s = SocialPerceptionState()
        self.assertFalse(s.face_detected)
        self.assertEqual(s.identity_score, 0.0)
        self.assertFalse(s.text_detected)
        self.assertEqual(s.word_score, 0.0)
        self.assertEqual(s.agency_score, 0.5)
        self.assertFalse(s.reorient_signal)
        self.assertEqual(s.social_inference, 0.0)
        self.assertEqual(s.social_salience, 0.0)
        self.assertEqual(s.familiarity, 0.3)
        self.assertFalse(s.is_novel)


class TestSocialPerceptionBridgeInit(unittest.TestCase):
    """Tests 2-3: Init with and without modules."""

    def test_init_stores_modules(self):
        olfa = MagicMock()
        fg = MagicMock()
        tpj = MagicMock()
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa,
            fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        self.assertIs(bridge._olfactory_system, olfa)
        self.assertIs(bridge._fusiform_gyrus, fg)
        self.assertIs(bridge._temporoparietal_junction, tpj)

    def test_init_no_modules(self):
        bridge = SocialPerceptionBridge()
        self.assertIsNone(bridge._olfactory_system)
        self.assertIsNone(bridge._fusiform_gyrus)
        self.assertIsNone(bridge._temporoparietal_junction)


class TestSocialPerceptionBridgeUpdate(unittest.TestCase):
    """Tests 4-7: update() with mocked modules."""

    def _make_ring_acts(self):
        return [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]

    def _mock_modules(self):
        olfa = MagicMock()
        olfa.process.return_value = {
            'sparse_code': np.zeros(16),
            'familiarity': 0.45,
            'is_novel': True,
            'best_match_label': None,
            'timestamp': 0.0,
        }

        fg = MagicMock()
        fg.process.return_value = {
            'domain': 'face',
            'face_result': {
                'face_detected': True,
                'identity_score': 0.7,
                'expression_estimate': 0.5,
                'familiarity': 0.6,
            },
            'text_result': {
                'text_detected': False,
                'word_score': 0.2,
                'symbol_type': 'unknown',
                'reading_fluency': 0.0,
            },
            'chosen_domain': 'face',
            'timestamp': 0.0,
        }

        tpj = MagicMock()
        tpj.process.return_value = {
            'tom_result': {
                'inferred_intention': 0.4,
                'belief_state': 0.8,
                'emotional_state': 0.1,
                'confidence': 0.55,
            },
            'agency_result': {
                'is_self_generated': True,
                'agency_score': 0.75,
                'distinction_clarity': 0.5,
            },
            'reorienting_result': {
                'reorient_signal': False,
                'surprise': 0.1,
                'novelty_drive': 0.2,
            },
            'timestamp': 0.0,
        }
        return olfa, fg, tpj

    def test_update_returns_state(self):
        olfa, fg, tpj = self._mock_modules()
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        state = bridge.update(self._make_ring_acts(), [0.1, 0.2])
        self.assertIsInstance(state, SocialPerceptionState)

    def test_update_calls_olfactory_system(self):
        olfa, fg, tpj = self._mock_modules()
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        bridge.update(self._make_ring_acts(), [0.1, 0.2])
        olfa.process.assert_called_once()
        # Should receive 32-dim input
        call_args = olfa.process.call_args[0][0]
        self.assertEqual(len(call_args), 32)

    def test_update_calls_fusiform_gyrus(self):
        olfa, fg, tpj = self._mock_modules()
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        bridge.update(self._make_ring_acts(), [0.1, 0.2])
        fg.process.assert_called_once()
        # domain='auto'
        call_kwargs = fg.process.call_args
        self.assertEqual(call_kwargs[1].get('domain', call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None), 'auto')

    def test_update_calls_tpj(self):
        olfa, fg, tpj = self._mock_modules()
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        bridge.update(self._make_ring_acts(), [0.1, 0.2])
        tpj.process.assert_called_once()
        # Check action_signal, sensory_feedback, prediction passed as kwargs
        call_kwargs = tpj.process.call_args[1]
        self.assertIn('action_signal', call_kwargs)
        self.assertIn('sensory_feedback', call_kwargs)
        self.assertIn('prediction', call_kwargs)


class TestSocialPerceptionBridgeCoupling(unittest.TestCase):
    """Tests 8-9: Inter-module coupling across ticks."""

    def _make_ring_acts(self):
        return [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]

    def test_fg_tpj_coupling(self):
        """FG face_detected feeds TPJ action_signal on NEXT tick."""
        olfa = MagicMock()
        olfa.process.return_value = {
            'sparse_code': np.zeros(16), 'familiarity': 0.3,
            'is_novel': False, 'best_match_label': None, 'timestamp': 0.0,
        }

        fg = MagicMock()
        fg.process.return_value = {
            'domain': 'face',
            'face_result': {
                'face_detected': True, 'identity_score': 0.6,
                'expression_estimate': 0.5, 'familiarity': 0.5,
            },
            'text_result': {
                'text_detected': False, 'word_score': 0.0,
                'symbol_type': 'unknown', 'reading_fluency': 0.0,
            },
            'chosen_domain': 'face', 'timestamp': 0.0,
        }

        tpj = MagicMock()
        tpj.process.return_value = {
            'tom_result': {'inferred_intention': 0.3, 'belief_state': 0.7,
                           'emotional_state': 0.0, 'confidence': 0.4},
            'agency_result': {'is_self_generated': False, 'agency_score': 0.5,
                              'distinction_clarity': 0.0},
            'reorienting_result': {'reorient_signal': False, 'surprise': 0.0,
                                   'novelty_drive': 0.0},
            'timestamp': 0.0,
        }

        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )

        # Tick 1: FG detects a face. TPJ gets default action_signal=0.0
        bridge.update(self._make_ring_acts(), [0.1])
        tick1_kwargs = tpj.process.call_args[1]
        self.assertEqual(tick1_kwargs['action_signal'], 0.0)

        # Tick 2: TPJ should receive action_signal=1.0 because face was detected on tick 1
        bridge.update(self._make_ring_acts(), [0.1])
        tick2_kwargs = tpj.process.call_args[1]
        self.assertEqual(tick2_kwargs['action_signal'], 1.0)

    def test_olfa_fg_coupling(self):
        """Olfactory familiarity biases FG input on NEXT tick."""
        olfa = MagicMock()
        olfa.process.return_value = {
            'sparse_code': np.zeros(16), 'familiarity': 0.8,
            'is_novel': False, 'best_match_label': 'known', 'timestamp': 0.0,
        }

        fg = MagicMock()
        fg.process.return_value = {
            'domain': 'face',
            'face_result': {
                'face_detected': False, 'identity_score': 0.0,
                'expression_estimate': 0.0, 'familiarity': 0.0,
            },
            'text_result': {
                'text_detected': False, 'word_score': 0.0,
                'symbol_type': 'unknown', 'reading_fluency': 0.0,
            },
            'chosen_domain': 'face', 'timestamp': 0.0,
        }

        tpj = MagicMock()
        tpj.process.return_value = {
            'tom_result': {'inferred_intention': 0.0, 'belief_state': 0.0,
                           'emotional_state': 0.0, 'confidence': 0.0},
            'agency_result': {'is_self_generated': False, 'agency_score': 0.5,
                              'distinction_clarity': 0.0},
            'reorienting_result': {'reorient_signal': False, 'surprise': 0.0,
                                   'novelty_drive': 0.0},
            'timestamp': 0.0,
        }

        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )

        # Tick 1: default familiarity=0.3 used for FG bias
        ring_acts = self._make_ring_acts()
        bridge.update(ring_acts, [0.1])
        tick1_fg_input = fg.process.call_args[0][0]

        # Tick 2: familiarity=0.8 from olfactory should increase FG bias
        bridge.update(ring_acts, [0.1])
        tick2_fg_input = fg.process.call_args[0][0]

        # The bias factor is (1 + 0.1 * familiarity), so tick2 should have
        # higher magnitude inputs (with familiarity 0.8 vs default 0.3)
        # We check that the inputs differ
        self.assertFalse(np.allclose(tick1_fg_input, tick2_fg_input))


class TestSocialPerceptionBridgeComputed(unittest.TestCase):
    """Tests 10-12: Computed fields and clamping."""

    def _make_ring_acts(self):
        return [
            np.random.randn(64),
            np.random.randn(128),
            np.random.randn(256),
            np.random.randn(256),
            np.random.randn(128),
        ]

    def _mock_modules(self, identity_score=0.4, tom_confidence=0.7):
        olfa = MagicMock()
        olfa.process.return_value = {
            'sparse_code': np.zeros(16), 'familiarity': 0.5,
            'is_novel': False, 'best_match_label': None, 'timestamp': 0.0,
        }

        fg = MagicMock()
        fg.process.return_value = {
            'domain': 'face',
            'face_result': {
                'face_detected': True, 'identity_score': identity_score,
                'expression_estimate': 0.5, 'familiarity': 0.5,
            },
            'text_result': {
                'text_detected': False, 'word_score': 0.1,
                'symbol_type': 'unknown', 'reading_fluency': 0.0,
            },
            'chosen_domain': 'face', 'timestamp': 0.0,
        }

        tpj = MagicMock()
        tpj.process.return_value = {
            'tom_result': {'inferred_intention': 0.3, 'belief_state': 0.7,
                           'emotional_state': 0.0, 'confidence': tom_confidence},
            'agency_result': {'is_self_generated': False, 'agency_score': 0.5,
                              'distinction_clarity': 0.0},
            'reorienting_result': {'reorient_signal': False, 'surprise': 0.0,
                                   'novelty_drive': 0.0},
            'timestamp': 0.0,
        }
        return olfa, fg, tpj

    def test_social_salience_computed(self):
        """social_salience = max(identity_score, social_inference)"""
        olfa, fg, tpj = self._mock_modules(identity_score=0.4, tom_confidence=0.7)
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        state = bridge.update(self._make_ring_acts(), [0.1])
        expected = max(0.4, 0.7)  # identity=0.4, social_inference(tom confidence)=0.7
        self.assertAlmostEqual(state.social_salience, expected, places=3)

    def test_multi_tick_stability(self):
        """20 ticks without crash; state remains valid."""
        olfa, fg, tpj = self._mock_modules()
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        for _ in range(20):
            state = bridge.update(self._make_ring_acts(), [0.1, 0.2, 0.15])
        self.assertIsInstance(state, SocialPerceptionState)
        self.assertTrue(0.0 <= state.social_salience <= 1.0)
        self.assertTrue(0.0 <= state.familiarity <= 1.0)

    def test_hook_fields_clamped(self):
        """social_salience (H28) and familiarity (H29) always in [0, 1]."""
        olfa = MagicMock()
        olfa.process.return_value = {
            'sparse_code': np.zeros(16), 'familiarity': 5.0,  # intentionally out of range
            'is_novel': False, 'best_match_label': None, 'timestamp': 0.0,
        }

        fg = MagicMock()
        fg.process.return_value = {
            'domain': 'face',
            'face_result': {
                'face_detected': True, 'identity_score': 3.0,  # out of range
                'expression_estimate': 0.5, 'familiarity': 0.5,
            },
            'text_result': {
                'text_detected': False, 'word_score': 0.1,
                'symbol_type': 'unknown', 'reading_fluency': 0.0,
            },
            'chosen_domain': 'face', 'timestamp': 0.0,
        }

        tpj = MagicMock()
        tpj.process.return_value = {
            'tom_result': {'inferred_intention': 0.3, 'belief_state': 0.7,
                           'emotional_state': 0.0, 'confidence': 2.5},
            'agency_result': {'is_self_generated': False, 'agency_score': 0.5,
                              'distinction_clarity': 0.0},
            'reorienting_result': {'reorient_signal': False, 'surprise': 0.0,
                                   'novelty_drive': 0.0},
            'timestamp': 0.0,
        }

        bridge = SocialPerceptionBridge(
            olfactory_system=olfa, fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        state = bridge.update(self._make_ring_acts(), [0.1])
        self.assertTrue(0.0 <= state.social_salience <= 1.0,
                        f"social_salience out of range: {state.social_salience}")
        self.assertTrue(0.0 <= state.familiarity <= 1.0,
                        f"familiarity out of range: {state.familiarity}")


class TestSocialPerceptionBridgeGetState(unittest.TestCase):
    """Tests 13-14: get_state() and skeleton (no modules)."""

    def test_get_state(self):
        bridge = SocialPerceptionBridge()
        state = bridge.get_state()
        self.assertIsInstance(state, SocialPerceptionState)
        # Should be defaults
        self.assertFalse(state.face_detected)
        self.assertEqual(state.familiarity, 0.3)

    def test_skeleton_no_modules(self):
        """update() with no modules still returns a valid default state."""
        bridge = SocialPerceptionBridge()
        ring_acts = [
            np.random.randn(64), np.random.randn(128),
            np.random.randn(256), np.random.randn(256),
            np.random.randn(128),
        ]
        state = bridge.update(ring_acts, [0.1, 0.2])
        self.assertIsInstance(state, SocialPerceptionState)
        # All fields should be defaults
        self.assertFalse(state.face_detected)
        self.assertEqual(state.social_salience, 0.0)


class TestSocialPerceptionBridgeIntegration(unittest.TestCase):
    """Test 15: Integration with real modules."""

    def test_integration_with_real_modules(self):
        from core.olfactory_system import OlfactorySystem
        from core.fusiform_gyrus import FusiformGyrus
        from core.temporoparietal_junction import TemporoparietalJunction

        olfa = OlfactorySystem()
        fg = FusiformGyrus()
        tpj = TemporoparietalJunction()
        bridge = SocialPerceptionBridge(
            olfactory_system=olfa,
            fusiform_gyrus=fg,
            temporoparietal_junction=tpj,
        )
        ring_acts = [
            np.random.randn(64), np.random.randn(128),
            np.random.randn(256), np.random.randn(256),
            np.random.randn(128),
        ]
        pes = [0.1, 0.2, 0.15, 0.1]
        for _ in range(10):
            state = bridge.update(ring_acts, pes)
        self.assertIsInstance(state, SocialPerceptionState)
        self.assertTrue(0 <= state.social_salience <= 1)
        self.assertTrue(0 <= state.familiarity <= 1)


if __name__ == '__main__':
    unittest.main()
