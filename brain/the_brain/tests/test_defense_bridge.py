"""Tests for DefenseBridge -- Defense Triad (PAG + PBN + BNST) -> Radial Attention Network.

Covers: DefenseState defaults, module wiring, inter-module coupling,
hook-clamped field safety (H19-H20), multi-tick stability, and integration
with real neuroscience modules (PeriaqueductalGray, ParabrachialNucleus,
BedNucleusStriaTerminalis).
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

def _make_mock_pbn():
    """Mock ParabrachialNucleus with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'alarm_level': 0.3,
        'urgency': 0.25,
        'threats_detected': ['error_rate'],
        'teaching_signal': {},
        'drive_outputs': [],
        'n_active_threats': 1,
        'autonomic_activation': 0.2,
    }
    return m


def _make_mock_bnst():
    """Mock BedNucleusStriaTerminalis with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'anxiety_level': 0.15,
        'vigilance': 0.3,
        'chronic_stress': 0.05,
        'amplified_threat': 0.1,
        'scanning_breadth': 0.85,
        'startle_sensitivity': 0.35,
        'is_chronic_stress': False,
    }
    return m


def _make_mock_pag():
    """Mock PeriaqueductalGray with standard return."""
    m = MagicMock()
    m.process.return_value = {
        'selected_defense': 'freeze',
        'defense_intensity': 0.2,
        'fight_activation': 0.05,
        'flight_activation': 0.1,
        'freeze_activation': 0.2,
        'autonomic_activation': 0.15,
        'pain_suppression': 0.0,
        'emergency_mode': False,
    }
    return m


def _make_bridge(pbn=None, bnst=None, pag=None):
    """Construct DefenseBridge with optional mock overrides."""
    from core.defense_bridge import DefenseBridge
    return DefenseBridge(
        parabrachial_nucleus=pbn if pbn is not None else _make_mock_pbn(),
        bnst=bnst if bnst is not None else _make_mock_bnst(),
        periaqueductal_gray=pag if pag is not None else _make_mock_pag(),
    )


# ===========================================================================
# Test classes
# ===========================================================================

class TestDefenseState:
    """DefenseState dataclass field defaults."""

    def test_state_defaults(self):
        from core.defense_bridge import DefenseState
        s = DefenseState()
        assert s.defense_mode == 'freeze'
        assert s.defense_intensity == 0.0
        assert s.emergency_mode is False
        assert s.autonomic_activation == 0.0
        assert s.anxiety_level == 0.0
        assert s.vigilance == 0.3
        assert s.is_chronic_stress is False
        assert s.alarm_level == 0.0
        assert s.alarm_urgency == 0.0
        assert s.should_interrupt is False


class TestDefenseBridgeInit:
    """Constructor wiring tests."""

    def test_init_stores_modules(self):
        pbn = _make_mock_pbn()
        bnst = _make_mock_bnst()
        pag = _make_mock_pag()
        from core.defense_bridge import DefenseBridge
        bridge = DefenseBridge(
            parabrachial_nucleus=pbn,
            bnst=bnst,
            periaqueductal_gray=pag,
        )
        assert bridge._parabrachial_nucleus is pbn
        assert bridge._bnst is bnst
        assert bridge._periaqueductal_gray is pag

    def test_init_no_modules(self):
        """Init with no modules must not crash."""
        from core.defense_bridge import DefenseBridge
        bridge = DefenseBridge()
        assert bridge._parabrachial_nucleus is None
        assert bridge._bnst is None
        assert bridge._periaqueductal_gray is None


class TestDefenseBridgeUpdate:
    """update() behaviour with mocked modules."""

    def test_update_returns_state(self):
        from core.defense_bridge import DefenseState
        bridge = _make_bridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, DefenseState)

    def test_update_calls_parabrachial_nucleus(self):
        pbn = _make_mock_pbn()
        bridge = _make_bridge(pbn=pbn)
        bridge.update(_ring_activations(), _prediction_errors())
        pbn.process.assert_called_once()
        # PBN.process() takes a DICT argument (not kwargs)
        call_args = pbn.process.call_args
        assert isinstance(call_args.args[0], dict)
        assert 'pain' in call_args.args[0]
        assert 'error_rate' in call_args.args[0]
        assert 'visceral_distress' in call_args.args[0]

    def test_update_calls_bnst(self):
        bnst = _make_mock_bnst()
        bridge = _make_bridge(bnst=bnst)
        bridge.update(_ring_activations(), _prediction_errors())
        bnst.process.assert_called_once()
        # BNST.process() takes kwargs
        call_kwargs = bnst.process.call_args.kwargs
        assert 'threat_level' in call_kwargs
        assert 'uncertainty' in call_kwargs
        assert 'stressor_intensity' in call_kwargs

    def test_update_calls_pag(self):
        pag = _make_mock_pag()
        bridge = _make_bridge(pag=pag)
        bridge.update(_ring_activations(), _prediction_errors())
        pag.process.assert_called_once()
        # PAG.process() takes kwargs
        call_kwargs = pag.process.call_args.kwargs
        assert 'threat' in call_kwargs
        assert 'escapability' in call_kwargs
        assert 'proximity' in call_kwargs
        assert 'arousal' in call_kwargs


class TestDefenseBridgeCoupling:
    """Inter-module coupling tests."""

    def test_pbn_bnst_coupling(self):
        """PBN alarm feeds BNST stressor_intensity on NEXT tick (1-tick delay)."""
        pbn = _make_mock_pbn()
        pbn.process.return_value = {
            'alarm_level': 0.7,
            'urgency': 0.6,
            'threats_detected': ['pain'],
            'teaching_signal': {},
            'drive_outputs': [],
            'n_active_threats': 1,
        }
        bnst = _make_mock_bnst()
        bridge = _make_bridge(pbn=pbn, bnst=bnst)

        # First tick: BNST gets _prev_alarm=0.0 (initial default)
        bridge.update(_ring_activations(), _prediction_errors())
        first_call = bnst.process.call_args
        assert first_call.kwargs.get('stressor_intensity') == 0.0

        # Second tick: BNST should now get PBN alarm (0.7) from first tick
        bnst.reset_mock()
        bridge.update(_ring_activations(), _prediction_errors())
        second_call = bnst.process.call_args
        assert second_call.kwargs.get('stressor_intensity') == 0.7

    def test_bnst_pag_coupling(self):
        """BNST anxiety feeds PAG proximity/arousal on NEXT tick (1-tick delay)."""
        bnst = _make_mock_bnst()
        bnst.process.return_value = {
            'anxiety_level': 0.65,
            'vigilance': 0.5,
            'chronic_stress': 0.1,
            'amplified_threat': 0.4,
            'scanning_breadth': 0.5,
            'startle_sensitivity': 0.6,
            'is_chronic_stress': False,
        }
        pag = _make_mock_pag()
        bridge = _make_bridge(bnst=bnst, pag=pag)

        # First tick: PAG gets _prev_anxiety=0.0 (initial default)
        bridge.update(_ring_activations(), _prediction_errors())
        first_call = pag.process.call_args
        assert first_call.kwargs.get('proximity') == 0.0
        assert first_call.kwargs.get('arousal') == 0.0

        # Second tick: PAG should now get BNST anxiety (0.65) from first tick
        pag.reset_mock()
        bridge.update(_ring_activations(), _prediction_errors())
        second_call = pag.process.call_args
        assert second_call.kwargs.get('proximity') == 0.65
        assert second_call.kwargs.get('arousal') == 0.65


class TestDefenseBridgeInterrupt:
    """should_interrupt flag tests."""

    def test_should_interrupt_flag(self):
        """should_interrupt is True when alarm_urgency > 0.5."""
        pbn = _make_mock_pbn()
        pbn.process.return_value = {
            'alarm_level': 0.8,
            'urgency': 0.75,  # > 0.5 -> should_interrupt = True
            'threats_detected': ['pain'],
            'teaching_signal': {},
            'drive_outputs': [],
            'n_active_threats': 1,
        }
        bridge = _make_bridge(pbn=pbn)
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert state.should_interrupt is True

    def test_should_not_interrupt_flag(self):
        """should_interrupt is False when alarm_urgency <= 0.5."""
        pbn = _make_mock_pbn()
        pbn.process.return_value = {
            'alarm_level': 0.2,
            'urgency': 0.15,  # <= 0.5 -> should_interrupt = False
            'threats_detected': [],
            'teaching_signal': {},
            'drive_outputs': [],
            'n_active_threats': 0,
        }
        bridge = _make_bridge(pbn=pbn)
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert state.should_interrupt is False


class TestDefenseBridgeStability:
    """Multi-tick and clamping safety tests."""

    def test_multi_tick_stability(self):
        """20 ticks, all fields remain in reasonable ranges."""
        from core.defense_bridge import DefenseState
        bridge = _make_bridge()
        for _ in range(20):
            state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, DefenseState)
        assert 0.0 <= state.defense_intensity <= 1.0
        assert 0.0 <= state.anxiety_level <= 1.0
        assert 0.0 <= state.autonomic_activation <= 1.0
        assert 0.0 <= state.alarm_level <= 1.0
        assert 0.0 <= state.alarm_urgency <= 1.0
        assert 0.0 <= state.vigilance <= 1.0
        assert isinstance(state.emergency_mode, bool)
        assert isinstance(state.is_chronic_stress, bool)
        assert isinstance(state.should_interrupt, bool)
        assert state.defense_mode in ('calm', 'fight', 'flight', 'freeze')

    def test_hook_fields_clamped(self):
        """defense_intensity (H19) and anxiety_level (H20) are clamped to [0, 1]."""
        pag = _make_mock_pag()
        pag.process.return_value = {
            'selected_defense': 'fight',
            'defense_intensity': 1.8,  # out of range!
            'fight_activation': 0.9,
            'flight_activation': 0.1,
            'freeze_activation': 0.05,
            'autonomic_activation': 0.5,
            'pain_suppression': 0.0,
            'emergency_mode': True,
        }
        bnst = _make_mock_bnst()
        bnst.process.return_value = {
            'anxiety_level': -0.3,  # out of range!
            'vigilance': 0.5,
            'chronic_stress': 0.1,
            'amplified_threat': 0.2,
            'scanning_breadth': 0.6,
            'startle_sensitivity': 0.5,
            'is_chronic_stress': False,
        }
        bridge = _make_bridge(pag=pag, bnst=bnst)
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert 0.0 <= state.defense_intensity <= 1.0, (
            f"defense_intensity {state.defense_intensity} not in [0,1]"
        )
        assert 0.0 <= state.anxiety_level <= 1.0, (
            f"anxiety_level {state.anxiety_level} not in [0,1]"
        )


class TestDefenseBridgeGetState:
    """get_state() accessor test."""

    def test_get_state(self):
        from core.defense_bridge import DefenseState
        bridge = _make_bridge()
        bridge.update(_ring_activations(), _prediction_errors())
        state = bridge.get_state()
        assert isinstance(state, DefenseState)


class TestDefenseBridgeNoModules:
    """Skeleton behaviour when all modules are None."""

    def test_skeleton_no_modules(self):
        """update() with no modules returns default-ish state, no crash."""
        from core.defense_bridge import DefenseBridge, DefenseState
        bridge = DefenseBridge()
        state = bridge.update(_ring_activations(), _prediction_errors())
        assert isinstance(state, DefenseState)
        assert 0.0 <= state.defense_intensity <= 1.0
        assert 0.0 <= state.anxiety_level <= 1.0
        assert state.should_interrupt is False


class TestDefenseBridgeIntegration:
    """Integration test with real neuroscience modules."""

    def test_integration_with_real_modules(self):
        from core.parabrachial_nucleus import ParabrachialNucleus
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        from core.periaqueductal_gray import PeriaqueductalGray
        from core.defense_bridge import DefenseBridge, DefenseState

        pbn = ParabrachialNucleus()
        bnst = BedNucleusStriaTerminalis()
        pag = PeriaqueductalGray()
        bridge = DefenseBridge(
            parabrachial_nucleus=pbn,
            bnst=bnst,
            periaqueductal_gray=pag,
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

        assert isinstance(state, DefenseState)
        assert 0.0 <= state.defense_intensity <= 1.0
        assert 0.0 <= state.anxiety_level <= 1.0
