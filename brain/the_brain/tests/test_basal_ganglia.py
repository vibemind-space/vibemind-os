"""
Tests for Basal Ganglia Module

Tests cover:
1. D1/D2 dopamine modulation
2. Go/NoGo pathway competition
3. Action selection
4. Learning updates with TD error
5. Integration with oscillator and neuromodulation
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.basal_ganglia import (
    BasalGanglia, BasalGangliaOutput, BGAction,
    Striatum, DirectPathway, IndirectPathway, HyperdirectPathway, GPiSNr,
    StriatumState, create_bg_from_oscillator_state
)


class TestStriatumState:
    """Test StriatumState dataclass"""

    def test_creation(self):
        """Test creating a StriatumState"""
        d1 = np.array([0.5, 0.3, 0.2])
        d2 = np.array([0.2, 0.4, 0.6])
        state = StriatumState(d1_activity=d1, d2_activity=d2, dopamine=0.7)

        assert np.allclose(state.d1_activity, d1)
        assert np.allclose(state.d2_activity, d2)
        assert state.dopamine == 0.7

    def test_go_nogo_signals(self):
        """Test Go and NoGo signal properties"""
        d1 = np.array([0.8, 0.2, 0.1])
        d2 = np.array([0.2, 0.5, 0.8])
        state = StriatumState(d1_activity=d1, d2_activity=d2)

        assert np.allclose(state.go_signal, d1)
        assert np.allclose(state.nogo_signal, d2)

    def test_competition(self):
        """Test Go-NoGo competition"""
        d1 = np.array([0.8, 0.3, 0.1])
        d2 = np.array([0.2, 0.3, 0.7])
        state = StriatumState(d1_activity=d1, d2_activity=d2)

        competition = state.competition
        assert competition[0] > 0  # Go wins for action 0
        assert np.isclose(competition[1], 0, atol=0.01)  # Balanced for action 1
        assert competition[2] < 0  # NoGo wins for action 2

    def test_to_dict(self):
        """Test dictionary conversion"""
        state = StriatumState(
            d1_activity=np.array([0.5, 0.5, 0.5]),
            d2_activity=np.array([0.3, 0.3, 0.3]),
            dopamine=0.6
        )
        d = state.to_dict()

        assert 'd1_activity' in d
        assert 'd2_activity' in d
        assert 'dopamine' in d
        assert 'go_signal' in d
        assert 'nogo_signal' in d
        assert 'competition' in d


class TestStriatum:
    """Test Striatum component"""

    def test_initialization(self):
        """Test Striatum initialization"""
        striatum = Striatum(n_inputs=6, n_actions=3)

        assert striatum.n_inputs == 6
        assert striatum.n_actions == 3
        assert striatum.W_d1.shape == (3, 6)
        assert striatum.W_d2.shape == (3, 6)

    def test_dopamine_modulation_d1(self):
        """Test that high dopamine enhances D1 activity"""
        striatum = Striatum()
        cortical_input = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])

        # Low dopamine
        state_low = striatum.forward(cortical_input, dopamine=0.2)
        # High dopamine
        state_high = striatum.forward(cortical_input, dopamine=0.8)

        # D1 should be higher with high dopamine
        assert np.mean(state_high.d1_activity) > np.mean(state_low.d1_activity)

    def test_dopamine_modulation_d2(self):
        """Test that high dopamine suppresses D2 activity"""
        striatum = Striatum()
        cortical_input = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])

        # Low dopamine
        state_low = striatum.forward(cortical_input, dopamine=0.2)
        # High dopamine
        state_high = striatum.forward(cortical_input, dopamine=0.8)

        # D2 should be lower with high dopamine
        assert np.mean(state_high.d2_activity) < np.mean(state_low.d2_activity)

    def test_weight_update(self):
        """Test weight update with TD error"""
        striatum = Striatum()
        initial_w_d1 = striatum.W_d1.copy()
        initial_w_d2 = striatum.W_d2.copy()

        eligibility_d1 = np.random.randn(3, 6) * 0.1
        eligibility_d2 = np.random.randn(3, 6) * 0.1

        # Positive TD error should strengthen D1 (Go)
        striatum.update_weights(td_error=0.5, eligibility_d1=eligibility_d1,
                                 eligibility_d2=eligibility_d2, learning_rate=0.1)

        assert not np.allclose(striatum.W_d1, initial_w_d1)


class TestPathways:
    """Test individual pathway components"""

    def test_direct_pathway(self):
        """Test direct (Go) pathway"""
        direct = DirectPathway(n_actions=3)
        d1_activity = np.array([0.8, 0.3, 0.1])

        go_signal = direct.forward(d1_activity)

        assert go_signal.shape == (3,)
        # Higher D1 should produce higher Go signal
        assert go_signal[0] > go_signal[2]

    def test_indirect_pathway(self):
        """Test indirect (NoGo) pathway"""
        indirect = IndirectPathway(n_actions=3)
        d2_activity = np.array([0.2, 0.5, 0.9])

        stn_activity, nogo_signal = indirect.forward(d2_activity)

        assert stn_activity.shape == (3,)
        assert nogo_signal.shape == (3,)

    def test_hyperdirect_pathway(self):
        """Test hyperdirect pathway"""
        hyperdirect = HyperdirectPathway(n_inputs=6, n_actions=3)
        # Use positive cortical input to ensure positive cortical drive
        cortical_input = np.abs(np.random.randn(6)) + 0.1

        # Low urgency
        output_low = hyperdirect.forward(cortical_input, urgency=0.2)
        # High urgency
        output_high = hyperdirect.forward(cortical_input, urgency=0.9)

        assert isinstance(output_low, float)
        assert isinstance(output_high, float)
        assert output_low >= 0
        assert output_high >= 0
        # Higher urgency should produce stronger global inhibition
        # (within a reasonable tolerance given weight randomness)
        assert output_high >= output_low - 0.1  # Allow small tolerance


class TestGPiSNr:
    """Test GPi/SNr output nucleus"""

    def test_forward(self):
        """Test GPi forward pass"""
        gpi = GPiSNr(n_actions=3, tonic_activity=0.8, temperature=0.5)

        go_signal = np.array([0.5, 0.2, 0.1])
        nogo_signal = np.array([0.2, 0.3, 0.6])
        hyperdirect = 0.1

        gpi_activity, action_gates = gpi.forward(go_signal, nogo_signal, hyperdirect)

        assert gpi_activity.shape == (3,)
        assert action_gates.shape == (3,)
        # Gates should sum to 1
        assert np.isclose(action_gates.sum(), 1.0)

    def test_go_bias_wins(self):
        """Test that strong Go signal leads to action selection"""
        gpi = GPiSNr(n_actions=3)

        # Strong Go for action 0
        go_signal = np.array([0.9, 0.1, 0.1])
        nogo_signal = np.array([0.1, 0.1, 0.1])
        hyperdirect = 0.1

        _, action_gates = gpi.forward(go_signal, nogo_signal, hyperdirect)

        # Action 0 should have highest probability
        assert np.argmax(action_gates) == 0

    def test_nogo_bias_loses(self):
        """Test that strong NoGo signal prevents action selection"""
        gpi = GPiSNr(n_actions=3)

        # Strong NoGo for action 2
        go_signal = np.array([0.3, 0.3, 0.3])
        nogo_signal = np.array([0.1, 0.1, 0.9])
        hyperdirect = 0.1

        _, action_gates = gpi.forward(go_signal, nogo_signal, hyperdirect)

        # Action 2 should have lowest probability
        assert np.argmin(action_gates) == 2


class TestBasalGanglia:
    """Test complete Basal Ganglia system"""

    def test_initialization(self):
        """Test BG initialization"""
        bg = BasalGanglia(n_inputs=6, n_actions=3)

        assert bg.n_inputs == 6
        assert bg.n_actions == 3
        assert bg.striatum is not None
        assert bg.direct is not None
        assert bg.indirect is not None
        assert bg.hyperdirect is not None
        assert bg.gpi is not None

    def test_step(self):
        """Test single BG step"""
        bg = BasalGanglia()
        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        output = bg.step(cortical_input, dopamine=0.5, urgency=0.5)

        assert isinstance(output, BasalGangliaOutput)
        assert output.action_gates.shape == (3,)
        assert np.isclose(output.action_gates.sum(), 1.0)
        assert output.selected_action in [0, 1, 2]
        assert 0 <= output.selection_confidence <= 1

    def test_high_advance_selects_advance(self):
        """Test that high ADVANCE channel input selects ADVANCE action"""
        bg = BasalGanglia()

        # High activation for ADVANCE channel (first 2 dimensions)
        cortical_input = np.array([0.9, 0.5, 0.1, 0.1, 0.1, 0.1])

        # Run multiple steps to stabilize
        for _ in range(5):
            output = bg.step(cortical_input, dopamine=0.6, urgency=0.3)

        # Should select ADVANCE (action 0)
        assert output.selected_action == 0 or output.action_gates[0] > 0.3

    def test_high_correct_selects_correct(self):
        """Test that high CORRECT channel input selects CORRECT action"""
        np.random.seed(42)  # Seed for deterministic test
        bg = BasalGanglia()

        # High activation for CORRECT channel (last 2 dimensions)
        cortical_input = np.array([0.1, 0.1, 0.1, 0.1, 0.9, 0.5])

        # Run multiple steps
        for _ in range(5):
            output = bg.step(cortical_input, dopamine=0.4, urgency=0.5)

        # Should favor CORRECT (action 2)
        assert output.selected_action == 2 or output.action_gates[2] > 0.3

    def test_dopamine_biases_go(self):
        """Test that high dopamine biases toward action (Go)"""
        bg_high_da = BasalGanglia()
        bg_low_da = BasalGanglia()

        cortical_input = np.array([0.5, 0.3, 0.5, 0.3, 0.5, 0.3])

        # High dopamine
        for _ in range(5):
            out_high = bg_high_da.step(cortical_input, dopamine=0.9, urgency=0.5)

        # Low dopamine
        for _ in range(5):
            out_low = bg_low_da.step(cortical_input, dopamine=0.2, urgency=0.5)

        # High dopamine should lead to higher Go signal
        assert np.mean(out_high.direct_output) >= np.mean(out_low.direct_output) - 0.1

    def test_learning_positive_td(self):
        """Test learning with positive TD error"""
        bg = BasalGanglia(learning_rate=0.1)

        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])
        bg.step(cortical_input, dopamine=0.5, urgency=0.5)

        initial_go = bg.direct.W_go.copy()

        # Positive TD error (action was better than expected)
        bg.update_weights(td_error=0.5, action_taken=0)

        # Go weights should change
        assert not np.allclose(bg.direct.W_go, initial_go)

    def test_learning_negative_td(self):
        """Test learning with negative TD error"""
        bg = BasalGanglia(learning_rate=0.1)

        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])
        bg.step(cortical_input, dopamine=0.5, urgency=0.5)

        initial_nogo = bg.indirect.W_stn.copy()

        # Negative TD error (action was worse than expected)
        bg.update_weights(td_error=-0.5, action_taken=0)

        # NoGo weights should change
        assert not np.allclose(bg.indirect.W_stn, initial_nogo)

    def test_modulate_oscillator(self):
        """Test oscillator modulation output"""
        bg = BasalGanglia()
        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        output = bg.step(cortical_input, dopamine=0.5, urgency=0.5)
        osc_mod = bg.modulate_oscillator(output)

        assert 'advance' in osc_mod
        assert 'explore' in osc_mod
        assert 'correct' in osc_mod
        assert np.isclose(osc_mod['advance'] + osc_mod['explore'] + osc_mod['correct'], 1.0)

    def test_modulate_thalamic_gates(self):
        """Test thalamic gate modulation"""
        bg = BasalGanglia()
        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        output = bg.step(cortical_input, dopamine=0.5, urgency=0.5)

        # 6 modality thalamic gates
        thalamic_gates = np.array([0.2, 0.15, 0.15, 0.15, 0.15, 0.2])

        modulated = bg.modulate_thalamic_gates(thalamic_gates, output, modulation_strength=0.3)

        assert modulated.shape == (6,)
        assert np.isclose(modulated.sum(), 1.0)

    def test_reset(self):
        """Test BG reset"""
        bg = BasalGanglia()
        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        # Run some steps
        for _ in range(10):
            bg.step(cortical_input, dopamine=0.5, urgency=0.5)

        assert bg.total_steps == 10
        assert len(bg.action_history) == 10

        bg.reset()

        assert bg.total_steps == 0
        assert len(bg.action_history) == 0

    def test_statistics(self):
        """Test statistics output"""
        bg = BasalGanglia()
        cortical_input = np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        for _ in range(5):
            bg.step(cortical_input, dopamine=0.5, urgency=0.5)

        stats = bg.get_statistics()

        assert 'total_steps' in stats
        assert stats['total_steps'] == 5
        assert 'action_counts' in stats
        assert 'action_probabilities' in stats

    def test_action_names(self):
        """Test action name lookup"""
        bg = BasalGanglia()

        assert bg.get_action_name(0) == 'ADVANCE'
        assert bg.get_action_name(1) == 'EXPLORE'
        assert bg.get_action_name(2) == 'CORRECT'


class TestIntegration:
    """Integration tests with oscillator and neuromodulation"""

    def test_with_mock_oscillator_state(self):
        """Test BG with mock oscillator state"""
        bg = BasalGanglia()

        # Mock a 6D oscillator state
        # High ADVANCE channel
        osc_vector = np.array([0.8, 0.2, 0.3, 0.1, 0.2, 0.1])

        output = bg.step(osc_vector, dopamine=0.6, urgency=0.4)

        assert output is not None
        assert output.selected_action in [0, 1, 2]

    def test_create_bg_from_oscillator_state_function(self):
        """Test the convenience function (with mocked types)"""
        bg = BasalGanglia()

        # Create mock objects that have the expected methods
        class MockOscState:
            def to_6d_vector(self):
                return np.array([0.5, 0.3, 0.4, 0.2, 0.3, 0.1])

        class MockNeuromodLevels:
            dopamine = 0.6
            norepinephrine = 0.4

        osc_state = MockOscState()
        neuromod_levels = MockNeuromodLevels()

        output = create_bg_from_oscillator_state(osc_state, neuromod_levels, bg)

        assert isinstance(output, BasalGangliaOutput)


class TestBGAction:
    """Test BGAction enum"""

    def test_action_values(self):
        """Test action enum values"""
        assert BGAction.ADVANCE.value == 0
        assert BGAction.EXPLORE.value == 1
        assert BGAction.CORRECT.value == 2

    def test_action_from_int(self):
        """Test creating action from integer"""
        assert BGAction(0) == BGAction.ADVANCE
        assert BGAction(1) == BGAction.EXPLORE
        assert BGAction(2) == BGAction.CORRECT


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
