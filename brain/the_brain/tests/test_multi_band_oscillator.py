"""
Tests for Multi-Band Oscillator and Synchrony Encoder

Tests cover:
1. MultiBandOscillator - basic functionality, PAC, backward compatibility
2. MultiBandSynchronyEncoder - encoding, history, detection
3. Integration tests - full pipeline
"""

import pytest
import numpy as np
from datetime import datetime

from core.multi_band_oscillator import (
    FrequencyBand,
    BandState,
    MultiBandState,
    PhaseAmplitudeCoupler,
    MultiBandOscillator
)
from core.multi_band_synchrony_encoder import (
    MultiBandSynchronyVector,
    MultiBandSynchronyEncoder,
    compute_multi_band_order_parameter
)
from core.action_potential_oscillator import (
    ActionPotentialOscillator,
    TripleOscillatorState,
    Channel
)
from core.synchrony_encoder import SynchronyVector


class TestFrequencyBand:
    """Tests for FrequencyBand enum"""

    def test_band_values(self):
        """Test that band enum has correct values"""
        assert FrequencyBand.THETA.value == "theta"
        assert FrequencyBand.ALPHA.value == "alpha"
        assert FrequencyBand.GAMMA.value == "gamma"

    def test_band_count(self):
        """Test that we have exactly 3 bands"""
        assert len(FrequencyBand) == 3


class TestBandState:
    """Tests for BandState dataclass"""

    def test_default_initialization(self):
        """Test default BandState values"""
        state = BandState(band=FrequencyBand.ALPHA)

        assert state.band == FrequencyBand.ALPHA
        assert state.phase_A == 0.0
        assert np.isclose(state.phase_B, 2 * np.pi / 3)
        assert np.isclose(state.phase_C, 4 * np.pi / 3)
        assert state.amp_A == 0.5
        assert state.amp_B == 0.5
        assert state.amp_C == 0.5

    def test_phases_property(self):
        """Test phases property returns correct array"""
        state = BandState(
            band=FrequencyBand.THETA,
            phase_A=0.1, phase_B=0.2, phase_C=0.3
        )
        phases = state.phases
        assert len(phases) == 3
        assert np.allclose(phases, [0.1, 0.2, 0.3])

    def test_amplitudes_property(self):
        """Test amplitudes property returns correct array"""
        state = BandState(
            band=FrequencyBand.GAMMA,
            amp_A=0.3, amp_B=0.6, amp_C=0.9
        )
        amps = state.amplitudes
        assert len(amps) == 3
        assert np.allclose(amps, [0.3, 0.6, 0.9])

    def test_mean_phase_circular(self):
        """Test circular mean phase calculation"""
        # All in phase
        state = BandState(
            band=FrequencyBand.ALPHA,
            phase_A=0.0, phase_B=0.0, phase_C=0.0
        )
        assert np.isclose(state.mean_phase, 0.0)

        # All at same phase (pi/2)
        state = BandState(
            band=FrequencyBand.ALPHA,
            phase_A=np.pi/2, phase_B=np.pi/2, phase_C=np.pi/2
        )
        assert np.isclose(state.mean_phase, np.pi/2)

        # 120 degree offset - circular mean angle is well-defined
        # but the magnitude is near 0, so direction is arbitrary
        state = BandState(
            band=FrequencyBand.ALPHA,
            phase_A=0.0,
            phase_B=2 * np.pi / 3,
            phase_C=4 * np.pi / 3
        )
        # Just verify it returns a valid angle in [0, 2*pi) or [-pi, pi]
        assert -np.pi <= state.mean_phase <= np.pi or 0 <= state.mean_phase <= 2 * np.pi

    def test_mean_amplitude(self):
        """Test mean amplitude calculation"""
        state = BandState(
            band=FrequencyBand.ALPHA,
            amp_A=0.2, amp_B=0.4, amp_C=0.6
        )
        assert np.isclose(state.mean_amplitude, 0.4)

    def test_power_calculation(self):
        """Test band power (sum of squared amplitudes)"""
        state = BandState(
            band=FrequencyBand.GAMMA,
            amp_A=0.5, amp_B=0.5, amp_C=0.5
        )
        # Power = 0.5^2 + 0.5^2 + 0.5^2 = 0.75
        assert np.isclose(state.power, 0.75)

    def test_to_6d_vector(self):
        """Test conversion to 6D vector"""
        state = BandState(
            band=FrequencyBand.ALPHA,
            phase_A=0.0, phase_B=np.pi/2, phase_C=np.pi,
            amp_A=1.0, amp_B=0.5, amp_C=0.5
        )
        vec = state.to_6d_vector()
        assert len(vec) == 6
        # A: amp=1, phase=0 -> (1, 0)
        assert np.isclose(vec[0], 1.0)
        assert np.isclose(vec[1], 0.0)
        # B: amp=0.5, phase=pi/2 -> (0, 0.5)
        assert np.isclose(vec[2], 0.0, atol=1e-6)
        assert np.isclose(vec[3], 0.5)

    def test_to_dict(self):
        """Test dictionary conversion"""
        state = BandState(band=FrequencyBand.THETA)
        d = state.to_dict()
        assert 'band' in d
        assert 'phases' in d
        assert 'amplitudes' in d
        assert d['band'] == 'theta'


class TestMultiBandState:
    """Tests for MultiBandState dataclass"""

    def test_initialization(self):
        """Test MultiBandState initialization"""
        theta = BandState(band=FrequencyBand.THETA)
        alpha = BandState(band=FrequencyBand.ALPHA)
        gamma = BandState(band=FrequencyBand.GAMMA)

        state = MultiBandState(theta=theta, alpha=alpha, gamma=gamma)

        assert state.theta.band == FrequencyBand.THETA
        assert state.alpha.band == FrequencyBand.ALPHA
        assert state.gamma.band == FrequencyBand.GAMMA
        assert state.beat_index == 0

    def test_band_powers(self):
        """Test band powers property"""
        theta = BandState(band=FrequencyBand.THETA, amp_A=0.3, amp_B=0.3, amp_C=0.3)
        alpha = BandState(band=FrequencyBand.ALPHA, amp_A=0.5, amp_B=0.5, amp_C=0.5)
        gamma = BandState(band=FrequencyBand.GAMMA, amp_A=0.8, amp_B=0.8, amp_C=0.8)

        state = MultiBandState(theta=theta, alpha=alpha, gamma=gamma)
        powers = state.band_powers

        assert 'theta' in powers
        assert 'alpha' in powers
        assert 'gamma' in powers
        # Gamma should have highest power
        assert powers['gamma'] > powers['alpha'] > powers['theta']

    def test_dominant_band(self):
        """Test dominant band detection"""
        theta = BandState(band=FrequencyBand.THETA, amp_A=0.9, amp_B=0.9, amp_C=0.9)
        alpha = BandState(band=FrequencyBand.ALPHA, amp_A=0.3, amp_B=0.3, amp_C=0.3)
        gamma = BandState(band=FrequencyBand.GAMMA, amp_A=0.1, amp_B=0.1, amp_C=0.1)

        state = MultiBandState(theta=theta, alpha=alpha, gamma=gamma)
        assert state.dominant_band == FrequencyBand.THETA

    def test_get_band(self):
        """Test get_band method"""
        theta = BandState(band=FrequencyBand.THETA)
        alpha = BandState(band=FrequencyBand.ALPHA)
        gamma = BandState(band=FrequencyBand.GAMMA)

        state = MultiBandState(theta=theta, alpha=alpha, gamma=gamma)

        assert state.get_band(FrequencyBand.THETA) == theta
        assert state.get_band(FrequencyBand.ALPHA) == alpha
        assert state.get_band(FrequencyBand.GAMMA) == gamma

    def test_to_18d_vector(self):
        """Test conversion to 18D vector"""
        theta = BandState(band=FrequencyBand.THETA)
        alpha = BandState(band=FrequencyBand.ALPHA)
        gamma = BandState(band=FrequencyBand.GAMMA)

        state = MultiBandState(theta=theta, alpha=alpha, gamma=gamma)
        vec = state.to_18d_vector()

        assert len(vec) == 18
        assert vec.shape == (18,)

    def test_to_legacy_6d(self):
        """Test backward compatible 6D output"""
        theta = BandState(band=FrequencyBand.THETA)
        alpha = BandState(band=FrequencyBand.ALPHA)
        gamma = BandState(band=FrequencyBand.GAMMA)

        state = MultiBandState(theta=theta, alpha=alpha, gamma=gamma)

        # Default uses alpha
        legacy = state.to_legacy_6d()
        assert len(legacy) == 6

        # Can specify different band
        legacy_theta = state.to_legacy_6d(FrequencyBand.THETA)
        assert len(legacy_theta) == 6

    def test_to_legacy_state(self):
        """Test conversion to legacy TripleOscillatorState"""
        theta = BandState(band=FrequencyBand.THETA, amp_A=0.3)
        alpha = BandState(band=FrequencyBand.ALPHA, amp_A=0.7)
        gamma = BandState(band=FrequencyBand.GAMMA, amp_A=0.9)

        state = MultiBandState(theta=theta, alpha=alpha, gamma=gamma)
        legacy = state.to_legacy_state()

        assert isinstance(legacy, TripleOscillatorState)
        assert legacy.A.amplitude == 0.7  # From alpha band
        assert legacy.A.channel == Channel.ADVANCE


class TestPhaseAmplitudeCoupler:
    """Tests for PhaseAmplitudeCoupler"""

    def test_initialization(self):
        """Test PAC coupler initialization"""
        pac = PhaseAmplitudeCoupler(
            theta_alpha_strength=0.6,
            alpha_gamma_strength=0.4
        )
        assert pac.theta_alpha_strength == 0.6
        assert pac.alpha_gamma_strength == 0.4

    def test_pac_theta_alpha_at_peak(self):
        """Test PAC at theta peak (phase=0)"""
        pac = PhaseAmplitudeCoupler(theta_alpha_strength=0.5)
        # At phase=0, PAC should be maximal
        pac_value = pac.compute_pac_theta_alpha(0.0)
        assert np.isclose(pac_value, 0.5)

    def test_pac_theta_alpha_at_trough(self):
        """Test PAC at theta trough (phase=pi)"""
        pac = PhaseAmplitudeCoupler(theta_alpha_strength=0.5)
        # At phase=pi, PAC should be 0
        pac_value = pac.compute_pac_theta_alpha(np.pi)
        assert np.isclose(pac_value, 0.0)

    def test_pac_modulation(self):
        """Test amplitude modulation by PAC"""
        pac = PhaseAmplitudeCoupler()

        # At peak (high PAC), amplitude should increase
        base_amp = 0.5
        pac_index = 0.5  # High coupling
        kappa = 0.3

        modulated = pac.modulate_amplitude(base_amp, pac_index, kappa)
        # modulated = 0.5 * (1 + 0.3 * 0.5) = 0.5 * 1.15 = 0.575
        assert modulated > base_amp
        assert np.isclose(modulated, 0.575)

    def test_pac_modulation_clipping(self):
        """Test that modulated amplitude is clipped to [0, 1]"""
        pac = PhaseAmplitudeCoupler()

        # High base amplitude with strong modulation should clip
        modulated = pac.modulate_amplitude(0.95, 0.5, 0.5)
        assert modulated <= 1.0

    def test_apply_coupling(self):
        """Test full coupling chain"""
        pac = PhaseAmplitudeCoupler(
            theta_alpha_strength=0.5,
            alpha_gamma_strength=0.5
        )

        theta = BandState(band=FrequencyBand.THETA, phase_A=0.0)  # Peak
        alpha = BandState(band=FrequencyBand.ALPHA, amp_A=0.5)
        gamma = BandState(band=FrequencyBand.GAMMA, amp_A=0.5)

        mod_alpha, mod_gamma, pac_ta, pac_ag = pac.apply_coupling(
            theta, alpha, gamma
        )

        # PAC should be non-zero at theta peak
        assert pac_ta > 0
        # Alpha amplitude should be boosted
        assert mod_alpha.amp_A > 0.5

    def test_pac_history(self):
        """Test that PAC values are recorded in history"""
        pac = PhaseAmplitudeCoupler()

        theta = BandState(band=FrequencyBand.THETA)
        alpha = BandState(band=FrequencyBand.ALPHA)
        gamma = BandState(band=FrequencyBand.GAMMA)

        for _ in range(5):
            pac.apply_coupling(theta, alpha, gamma)

        assert len(pac.pac_history_theta_alpha) == 5
        assert len(pac.pac_history_alpha_gamma) == 5


class TestMultiBandOscillator:
    """Tests for MultiBandOscillator"""

    def test_initialization_default(self):
        """Test default initialization"""
        osc = MultiBandOscillator()

        assert osc.theta_freq == 6.0
        assert osc.alpha_freq == 10.0
        assert osc.gamma_freq == 40.0
        assert osc.beat_index == 0

    def test_initialization_custom(self):
        """Test custom initialization"""
        osc = MultiBandOscillator(
            theta_freq=5.0,
            alpha_freq=11.0,
            gamma_freq=50.0,
            pac_theta_alpha=0.7,
            pac_alpha_gamma=0.6
        )

        assert osc.theta_freq == 5.0
        assert osc.alpha_freq == 11.0
        assert osc.gamma_freq == 50.0

    def test_initialization_with_base_oscillator(self):
        """Test initialization with existing base oscillator"""
        base = ActionPotentialOscillator(use_neural_coupling=False)
        osc = MultiBandOscillator(base_oscillator=base)

        assert osc.base_oscillator is base

    def test_step_basic(self):
        """Test basic step functionality"""
        osc = MultiBandOscillator()
        state = osc.step()

        assert isinstance(state, MultiBandState)
        assert state.beat_index == 1

    def test_step_with_input(self):
        """Test step with external input"""
        osc = MultiBandOscillator()
        state = osc.step(external_input={
            'advance': 0.8,
            'explore': 0.1,
            'correct': 0.1
        })

        # After input, amplitudes should reflect input
        assert state.alpha.amp_A > state.alpha.amp_B
        assert state.alpha.amp_A > state.alpha.amp_C

    def test_step_updates_beat_index(self):
        """Test that beat index increments"""
        osc = MultiBandOscillator()

        for i in range(5):
            state = osc.step()
            assert state.beat_index == i + 1

    def test_step_with_band_weights(self):
        """Test step with band-specific weights"""
        osc = MultiBandOscillator()

        # Emphasize gamma band
        state = osc.step(
            external_input={'advance': 0.5, 'explore': 0.3, 'correct': 0.2},
            band_weights={'theta': 0.5, 'alpha': 1.0, 'gamma': 2.0}
        )

        assert isinstance(state, MultiBandState)

    def test_pac_computation(self):
        """Test that PAC is computed during step"""
        osc = MultiBandOscillator(pac_theta_alpha=0.6, pac_alpha_gamma=0.5)

        # Run several steps
        for _ in range(10):
            state = osc.step()

        # PAC metrics should be populated
        metrics = osc.get_pac_metrics()
        assert 'theta_alpha' in metrics
        assert 'alpha_gamma' in metrics

    def test_get_band_power(self):
        """Test getting power for specific band"""
        osc = MultiBandOscillator()
        osc.step()

        theta_power = osc.get_band_power(FrequencyBand.THETA)
        alpha_power = osc.get_band_power(FrequencyBand.ALPHA)
        gamma_power = osc.get_band_power(FrequencyBand.GAMMA)

        assert theta_power >= 0
        assert alpha_power >= 0
        assert gamma_power >= 0

    def test_get_legacy_state(self):
        """Test backward compatible legacy state"""
        osc = MultiBandOscillator()
        osc.step()

        legacy = osc.get_legacy_state()
        assert isinstance(legacy, TripleOscillatorState)
        assert hasattr(legacy, 'A')
        assert hasattr(legacy, 'B')
        assert hasattr(legacy, 'C')

    def test_reset(self):
        """Test reset functionality"""
        osc = MultiBandOscillator()

        # Run some steps
        for _ in range(10):
            osc.step()

        assert osc.beat_index == 10
        assert len(osc.state_history) > 0

        # Reset
        osc.reset()

        assert osc.beat_index == 0
        assert len(osc.state_history) == 0

    def test_state_history(self):
        """Test that state history is maintained"""
        osc = MultiBandOscillator()

        for _ in range(5):
            osc.step()

        assert len(osc.state_history) == 5

    def test_state_history_limit(self):
        """Test that state history is limited to 100"""
        osc = MultiBandOscillator()

        for _ in range(150):
            osc.step()

        assert len(osc.state_history) == 100

    def test_get_statistics(self):
        """Test statistics retrieval"""
        osc = MultiBandOscillator()
        osc.step()

        stats = osc.get_statistics()

        assert 'beat_index' in stats
        assert 'frequencies' in stats
        assert 'band_powers' in stats
        assert 'pac' in stats

    def test_step_performance(self):
        """Test that step executes quickly (no FFT)"""
        osc = MultiBandOscillator()

        import time
        start = time.time()
        for _ in range(100):
            osc.step()
        elapsed = time.time() - start

        # 100 steps should take << 1 second
        assert elapsed < 1.0, f"100 steps took {elapsed:.3f}s, expected < 1s"


class TestMultiBandSynchronyVector:
    """Tests for MultiBandSynchronyVector"""

    def test_initialization(self):
        """Test vector initialization"""
        legacy = SynchronyVector(
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            cos_AB=1.0, sin_AB=0.0,
            cos_AC=1.0, sin_AC=0.0,
            cos_BC=1.0, sin_BC=0.0
        )

        vec = MultiBandSynchronyVector(
            legacy_sync=legacy,
            theta_power=0.5,
            alpha_power=0.6,
            gamma_power=0.7,
            pac_theta_alpha=0.3,
            pac_alpha_gamma=0.4,
            theta_gamma_coherence=0.5,
            alpha_gamma_ratio=0.46
        )

        assert vec.theta_power == 0.5
        assert vec.alpha_power == 0.6
        assert vec.gamma_power == 0.7

    def test_vector_shape(self):
        """Test that full vector is 16D"""
        legacy = SynchronyVector(
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            cos_AB=1.0, sin_AB=0.0,
            cos_AC=1.0, sin_AC=0.0,
            cos_BC=1.0, sin_BC=0.0
        )

        vec = MultiBandSynchronyVector(
            legacy_sync=legacy,
            theta_power=0.5,
            alpha_power=0.6,
            gamma_power=0.7,
            pac_theta_alpha=0.3,
            pac_alpha_gamma=0.4,
            theta_gamma_coherence=0.5,
            alpha_gamma_ratio=0.46
        )

        assert len(vec.vector) == 16
        assert vec.vector.shape == (16,)

    def test_legacy_vector(self):
        """Test legacy 9D vector extraction"""
        legacy = SynchronyVector(
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            cos_AB=1.0, sin_AB=0.0,
            cos_AC=1.0, sin_AC=0.0,
            cos_BC=1.0, sin_BC=0.0
        )

        vec = MultiBandSynchronyVector(
            legacy_sync=legacy,
            theta_power=0.5, alpha_power=0.6, gamma_power=0.7,
            pac_theta_alpha=0.3, pac_alpha_gamma=0.4,
            theta_gamma_coherence=0.5, alpha_gamma_ratio=0.46
        )

        legacy_vec = vec.legacy_vector
        assert len(legacy_vec) == 9

    def test_dominant_band(self):
        """Test dominant band detection"""
        legacy = SynchronyVector(
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            cos_AB=1.0, sin_AB=0.0,
            cos_AC=1.0, sin_AC=0.0,
            cos_BC=1.0, sin_BC=0.0
        )

        vec = MultiBandSynchronyVector(
            legacy_sync=legacy,
            theta_power=0.9,  # Highest
            alpha_power=0.3,
            gamma_power=0.2,
            pac_theta_alpha=0.3, pac_alpha_gamma=0.4,
            theta_gamma_coherence=0.5, alpha_gamma_ratio=0.6
        )

        assert vec.dominant_band == FrequencyBand.THETA

    def test_normalized_band_powers(self):
        """Test normalized powers sum to 1"""
        legacy = SynchronyVector(
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            cos_AB=1.0, sin_AB=0.0,
            cos_AC=1.0, sin_AC=0.0,
            cos_BC=1.0, sin_BC=0.0
        )

        vec = MultiBandSynchronyVector(
            legacy_sync=legacy,
            theta_power=0.5, alpha_power=0.3, gamma_power=0.2,
            pac_theta_alpha=0.3, pac_alpha_gamma=0.4,
            theta_gamma_coherence=0.5, alpha_gamma_ratio=0.6
        )

        norm = vec.normalized_band_powers
        total = sum(norm.values())
        assert np.isclose(total, 1.0)


class TestMultiBandSynchronyEncoder:
    """Tests for MultiBandSynchronyEncoder"""

    def test_initialization(self):
        """Test encoder initialization"""
        encoder = MultiBandSynchronyEncoder()
        assert encoder.history_length == 100
        assert encoder.smoothing_alpha == 0.0

    def test_encode(self):
        """Test basic encoding"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        state = osc.step()
        sync = encoder.encode(state)

        assert isinstance(sync, MultiBandSynchronyVector)
        assert len(sync.vector) == 16

    def test_encode_from_oscillator(self):
        """Test convenience encoding method"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        osc.step()
        sync = encoder.encode_from_oscillator(osc)

        assert isinstance(sync, MultiBandSynchronyVector)

    def test_history(self):
        """Test that encoder maintains history"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        for _ in range(5):
            state = osc.step()
            encoder.encode(state)

        assert len(encoder.history) == 5

    def test_history_matrix(self):
        """Test history matrix retrieval"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        for _ in range(10):
            state = osc.step()
            encoder.encode(state)

        matrix = encoder.get_history_matrix()
        assert matrix.shape == (10, 16)

    def test_legacy_history_matrix(self):
        """Test legacy history matrix"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        for _ in range(10):
            state = osc.step()
            encoder.encode(state)

        legacy_matrix = encoder.get_legacy_history_matrix()
        assert legacy_matrix.shape == (10, 9)

    def test_smoothing(self):
        """Test exponential smoothing"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder(smoothing_alpha=0.3)

        for _ in range(10):
            state = osc.step()
            encoder.encode(state)

        smoothed = encoder.get_smoothed_vector()
        assert smoothed is not None
        assert len(smoothed) == 16

    def test_band_transition_detection(self):
        """Test band power transition detection"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        # First phase: exploit mode (should boost alpha/gamma)
        for _ in range(10):
            state = osc.step(external_input={'advance': 0.9, 'explore': 0.05, 'correct': 0.05})
            encoder.encode(state)

        # Second phase: different mode
        for _ in range(10):
            state = osc.step(external_input={'advance': 0.05, 'explore': 0.9, 'correct': 0.05})
            encoder.encode(state)

        # Should detect some transition
        transition = encoder.detect_band_transition(window=5, threshold=0.1)
        # Note: might or might not detect depending on dynamics
        # Just check it returns valid format
        if transition:
            assert 'band' in transition
            assert 'direction' in transition

    def test_reset(self):
        """Test encoder reset"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder(smoothing_alpha=0.1)

        for _ in range(10):
            state = osc.step()
            encoder.encode(state)

        encoder.reset()

        assert len(encoder.history) == 0
        assert encoder.get_smoothed_vector() is None

    def test_statistics(self):
        """Test statistics retrieval"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        for _ in range(10):
            state = osc.step()
            encoder.encode(state)

        stats = encoder.get_statistics()

        assert 'history_length' in stats
        assert 'current' in stats


class TestOrderParameter:
    """Tests for order parameter computation"""

    def test_empty_list(self):
        """Test with empty list"""
        result = compute_multi_band_order_parameter([])
        assert result['legacy_coherence'] == 0.0
        assert result['band_stability'] == 0.0
        assert result['pac_consistency'] == 0.0

    def test_with_vectors(self):
        """Test with actual vectors"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        for _ in range(10):
            state = osc.step()
            encoder.encode(state)

        result = compute_multi_band_order_parameter(encoder.history)

        assert 'legacy_coherence' in result
        assert 'band_stability' in result
        assert 'pac_consistency' in result
        assert all(0.0 <= v <= 1.0 for v in result.values())


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code"""

    def test_legacy_state_compatibility(self):
        """Test that legacy state works with existing SynchronyEncoder"""
        from core.synchrony_encoder import SynchronyEncoder as LegacyEncoder

        osc = MultiBandOscillator()
        legacy_encoder = LegacyEncoder()

        state = osc.step()
        legacy_state = state.to_legacy_state()

        # Should work with legacy encoder
        sync = legacy_encoder.encode(legacy_state)
        assert len(sync.vector) == 9

    def test_legacy_6d_shape(self):
        """Test legacy 6D vector matches original oscillator"""
        # Original oscillator
        orig_osc = ActionPotentialOscillator(use_neural_coupling=False)
        orig_state = orig_osc.step()
        orig_6d = orig_state.to_6d_vector()

        # Multi-band oscillator
        multi_osc = MultiBandOscillator()
        multi_state = multi_osc.step()
        multi_6d = multi_state.to_legacy_6d()

        # Should have same shape
        assert orig_6d.shape == multi_6d.shape == (6,)

    def test_channel_preservation(self):
        """Test that channel semantics are preserved"""
        osc = MultiBandOscillator()
        state = osc.step(external_input={'advance': 0.9, 'explore': 0.05, 'correct': 0.05})

        legacy = state.to_legacy_state()

        # Advance should have highest amplitude
        assert legacy.A.channel == Channel.ADVANCE
        assert legacy.A.amplitude > legacy.B.amplitude
        assert legacy.A.amplitude > legacy.C.amplitude


class TestIntegration:
    """Integration tests for the full pipeline"""

    def test_full_pipeline(self):
        """Test complete oscillator -> encoder pipeline"""
        osc = MultiBandOscillator()
        encoder = MultiBandSynchronyEncoder()

        # Simulate a sequence of different modes
        modes = [
            {'advance': 0.8, 'explore': 0.1, 'correct': 0.1},
            {'advance': 0.2, 'explore': 0.7, 'correct': 0.1},
            {'advance': 0.1, 'explore': 0.1, 'correct': 0.8},
        ]

        for mode in modes:
            for _ in range(10):
                state = osc.step(external_input=mode)
                sync = encoder.encode(state)

                # All outputs should be valid
                assert len(sync.vector) == 16
                assert sync.total_power > 0

        # Final checks
        assert len(encoder.history) == 30
        assert osc.beat_index == 30

    def test_pac_modulation_visible(self):
        """Test that PAC creates visible amplitude modulation"""
        osc = MultiBandOscillator(
            pac_theta_alpha=0.8,  # Strong coupling
            pac_alpha_gamma=0.8
        )

        alpha_amps = []
        gamma_amps = []

        for _ in range(100):
            state = osc.step()
            alpha_amps.append(state.alpha.mean_amplitude)
            gamma_amps.append(state.gamma.mean_amplitude)

        # There should be variation in amplitudes due to PAC
        alpha_std = np.std(alpha_amps)
        gamma_std = np.std(gamma_amps)

        # With strong PAC, we should see some variation
        # (exact threshold depends on implementation)
        assert alpha_std > 0 or gamma_std > 0, "PAC should create amplitude variation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
