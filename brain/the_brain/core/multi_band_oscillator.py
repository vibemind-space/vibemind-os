"""
Multi-Band Oscillator - Theta/Alpha/Gamma with Phase-Amplitude Coupling

Extends the 3-channel ActionPotentialOscillator (A/B/C) with biologically-inspired
multi-frequency neural oscillations:

    THETA (4-8 Hz):  Planning, memory sequences, hippocampal binding
    ALPHA (8-12 Hz): Thalamic gating, attention routing, inhibition
    GAMMA (30-100 Hz): Feature binding, action execution, consciousness

Phase-Amplitude Coupling (PAC):
    - Theta phase modulates Alpha amplitude
    - Alpha phase modulates Gamma amplitude

This creates a hierarchical temporal structure where slow oscillations
organize the timing of fast oscillations - a key principle of neural computation.

Mathematical Model (no FFT, real-time capable):
    For each band k in {theta, alpha, gamma}, channel i in {A, B, C}:
        d(theta_ki)/dt = omega_ki + K_k * sum_j(sin(theta_kj - theta_ki))  [Kuramoto]
        d(A_ki)/dt = -lambda_k * A_ki + I_ki + PAC_k                        [Amplitude]

    PAC computation:
        PAC_theta_alpha(t) = mu * (1 + cos(theta_theta(t))) / 2
        A_alpha(t) = A_alpha_base(t) * (1 + kappa * PAC_theta_alpha(t))
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.action_potential_oscillator import (
    ActionPotentialOscillator,
    TripleOscillatorState,
    OscillatorState,
    Channel
)


class FrequencyBand(Enum):
    """Neural frequency bands with biological roles"""
    THETA = "theta"   # 4-8 Hz: Planning, memory, hippocampal
    ALPHA = "alpha"   # 8-12 Hz: Thalamic gating, attention
    GAMMA = "gamma"   # 30-100 Hz: Feature binding, action execution


@dataclass
class BandState:
    """
    State of one frequency band's 3 oscillators (A, B, C)

    Each band has its own set of phases and amplitudes for the
    three action channels (Advance, Explore, Correct).
    """
    band: FrequencyBand

    # Phases for each channel [0, 2*pi)
    phase_A: float = 0.0
    phase_B: float = 2 * np.pi / 3   # 120 deg offset
    phase_C: float = 4 * np.pi / 3   # 240 deg offset

    # Amplitudes for each channel [0, 1]
    amp_A: float = 0.5
    amp_B: float = 0.5
    amp_C: float = 0.5

    # Band-specific parameters
    base_frequency: float = 10.0  # Hz
    coupling_strength: float = 0.5
    amplitude_decay: float = 0.95

    @property
    def phases(self) -> np.ndarray:
        """Get phase vector [3]"""
        return np.array([self.phase_A, self.phase_B, self.phase_C])

    @property
    def amplitudes(self) -> np.ndarray:
        """Get amplitude vector [3]"""
        return np.array([self.amp_A, self.amp_B, self.amp_C])

    @property
    def mean_phase(self) -> float:
        """Mean phase across channels (circular mean)"""
        complex_sum = np.sum(np.exp(1j * self.phases))
        return np.angle(complex_sum)

    @property
    def mean_amplitude(self) -> float:
        """Mean amplitude across channels"""
        return np.mean(self.amplitudes)

    @property
    def power(self) -> float:
        """Band power (sum of squared amplitudes)"""
        return np.sum(self.amplitudes ** 2)

    def to_6d_vector(self) -> np.ndarray:
        """Convert to 6D vector [A_real, A_imag, B_real, B_imag, C_real, C_imag]"""
        return np.array([
            self.amp_A * np.cos(self.phase_A),
            self.amp_A * np.sin(self.phase_A),
            self.amp_B * np.cos(self.phase_B),
            self.amp_B * np.sin(self.phase_B),
            self.amp_C * np.cos(self.phase_C),
            self.amp_C * np.sin(self.phase_C)
        ])

    def to_dict(self) -> Dict:
        return {
            'band': self.band.value,
            'phases': {'A': self.phase_A, 'B': self.phase_B, 'C': self.phase_C},
            'amplitudes': {'A': self.amp_A, 'B': self.amp_B, 'C': self.amp_C},
            'mean_phase': self.mean_phase,
            'mean_amplitude': self.mean_amplitude,
            'power': self.power,
            'base_frequency': self.base_frequency
        }


@dataclass
class MultiBandState:
    """
    Combined state of all frequency bands

    Provides unified access to Theta, Alpha, and Gamma band states,
    plus Phase-Amplitude Coupling metrics.
    """
    theta: BandState
    alpha: BandState
    gamma: BandState

    # PAC metrics (computed during step)
    pac_theta_alpha: float = 0.0  # Modulation index
    pac_alpha_gamma: float = 0.0  # Modulation index

    # Metadata
    beat_index: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def band_powers(self) -> Dict[str, float]:
        """Get power for each band"""
        return {
            'theta': self.theta.power,
            'alpha': self.alpha.power,
            'gamma': self.gamma.power
        }

    @property
    def dominant_band(self) -> FrequencyBand:
        """Band with highest power"""
        powers = self.band_powers
        max_band = max(powers, key=powers.get)
        return {'theta': FrequencyBand.THETA,
                'alpha': FrequencyBand.ALPHA,
                'gamma': FrequencyBand.GAMMA}[max_band]

    def get_band(self, band: FrequencyBand) -> BandState:
        """Get state for specific band"""
        if band == FrequencyBand.THETA:
            return self.theta
        elif band == FrequencyBand.ALPHA:
            return self.alpha
        else:
            return self.gamma

    def to_18d_vector(self) -> np.ndarray:
        """
        Convert to 18D vector (6D per band)

        Format: [theta_6d, alpha_6d, gamma_6d]
        """
        return np.concatenate([
            self.theta.to_6d_vector(),
            self.alpha.to_6d_vector(),
            self.gamma.to_6d_vector()
        ])

    def to_legacy_6d(self, band: FrequencyBand = FrequencyBand.ALPHA) -> np.ndarray:
        """
        Get legacy 6D vector compatible with existing ActionPotentialOscillator output

        Args:
            band: Which band to use for legacy output (default: alpha)

        Returns:
            6D vector [A_real, A_imag, B_real, B_imag, C_real, C_imag]
        """
        return self.get_band(band).to_6d_vector()

    def to_legacy_state(self, band: FrequencyBand = FrequencyBand.ALPHA) -> TripleOscillatorState:
        """
        Convert to legacy TripleOscillatorState for backward compatibility

        Args:
            band: Which band to use for legacy output (default: alpha)

        Returns:
            TripleOscillatorState compatible with existing code
        """
        b = self.get_band(band)
        return TripleOscillatorState(
            A=OscillatorState(
                channel=Channel.ADVANCE,
                amplitude=b.amp_A,
                phase=b.phase_A,
                frequency=b.base_frequency
            ),
            B=OscillatorState(
                channel=Channel.EXPLORE,
                amplitude=b.amp_B,
                phase=b.phase_B,
                frequency=b.base_frequency
            ),
            C=OscillatorState(
                channel=Channel.CORRECT,
                amplitude=b.amp_C,
                phase=b.phase_C,
                frequency=b.base_frequency
            ),
            beat_index=self.beat_index
        )

    def to_dict(self) -> Dict:
        return {
            'theta': self.theta.to_dict(),
            'alpha': self.alpha.to_dict(),
            'gamma': self.gamma.to_dict(),
            'pac': {
                'theta_alpha': self.pac_theta_alpha,
                'alpha_gamma': self.pac_alpha_gamma
            },
            'dominant_band': self.dominant_band.value,
            'beat_index': self.beat_index
        }


class PhaseAmplitudeCoupler:
    """
    Computes Phase-Amplitude Coupling (PAC) between frequency bands

    PAC is a key mechanism in neural computation where the phase of a
    slow oscillation modulates the amplitude of a faster oscillation.

    Uses direct phase-based computation (no FFT) for real-time capability:
        PAC(t) = mu * (1 + cos(slow_phase(t))) / 2
        A_fast(t) = A_fast_base(t) * (1 + kappa * PAC(t))

    When slow_phase = 0 (peak): PAC = mu, amplitude boosted by (1 + kappa*mu)
    When slow_phase = pi (trough): PAC = 0, amplitude at baseline
    """

    def __init__(
        self,
        theta_alpha_strength: float = 0.5,   # mu for theta->alpha
        alpha_gamma_strength: float = 0.5,   # mu for alpha->gamma
        theta_alpha_kappa: float = 0.3,      # Modulation depth
        alpha_gamma_kappa: float = 0.4       # Modulation depth
    ):
        """
        Initialize PAC coupler

        Args:
            theta_alpha_strength: Base coupling strength theta->alpha
            alpha_gamma_strength: Base coupling strength alpha->gamma
            theta_alpha_kappa: Modulation depth for alpha amplitude
            alpha_gamma_kappa: Modulation depth for gamma amplitude
        """
        self.theta_alpha_strength = theta_alpha_strength
        self.alpha_gamma_strength = alpha_gamma_strength
        self.theta_alpha_kappa = theta_alpha_kappa
        self.alpha_gamma_kappa = alpha_gamma_kappa

        # Tracking
        self.pac_history_theta_alpha: List[float] = []
        self.pac_history_alpha_gamma: List[float] = []

    def compute_pac_theta_alpha(self, theta_phase: float) -> float:
        """
        Compute PAC modulation index for theta->alpha coupling

        Args:
            theta_phase: Current mean phase of theta band

        Returns:
            PAC modulation index [0, theta_alpha_strength]
        """
        # PAC = mu * (1 + cos(phase)) / 2
        # At phase=0: PAC = mu
        # At phase=pi: PAC = 0
        pac = self.theta_alpha_strength * (1 + np.cos(theta_phase)) / 2
        return pac

    def compute_pac_alpha_gamma(self, alpha_phase: float) -> float:
        """
        Compute PAC modulation index for alpha->gamma coupling

        Args:
            alpha_phase: Current mean phase of alpha band

        Returns:
            PAC modulation index [0, alpha_gamma_strength]
        """
        pac = self.alpha_gamma_strength * (1 + np.cos(alpha_phase)) / 2
        return pac

    def modulate_amplitude(
        self,
        base_amplitude: float,
        pac_index: float,
        kappa: float
    ) -> float:
        """
        Apply PAC modulation to amplitude

        Args:
            base_amplitude: Unmodulated amplitude
            pac_index: PAC modulation index
            kappa: Modulation depth

        Returns:
            Modulated amplitude
        """
        # A_modulated = A_base * (1 + kappa * PAC)
        modulated = base_amplitude * (1 + kappa * pac_index)
        return np.clip(modulated, 0.0, 1.0)

    def apply_coupling(
        self,
        theta_state: BandState,
        alpha_state: BandState,
        gamma_state: BandState
    ) -> Tuple[BandState, BandState, float, float]:
        """
        Apply full PAC coupling chain

        Theta phase -> Alpha amplitude modulation
        Alpha phase -> Gamma amplitude modulation

        Args:
            theta_state: Current theta band state
            alpha_state: Current alpha band state
            gamma_state: Current gamma band state

        Returns:
            Tuple of (modulated_alpha, modulated_gamma, pac_theta_alpha, pac_alpha_gamma)
        """
        # Compute PAC indices
        pac_ta = self.compute_pac_theta_alpha(theta_state.mean_phase)
        pac_ag = self.compute_pac_alpha_gamma(alpha_state.mean_phase)

        # Modulate alpha amplitudes based on theta phase
        alpha_state.amp_A = self.modulate_amplitude(
            alpha_state.amp_A, pac_ta, self.theta_alpha_kappa
        )
        alpha_state.amp_B = self.modulate_amplitude(
            alpha_state.amp_B, pac_ta, self.theta_alpha_kappa
        )
        alpha_state.amp_C = self.modulate_amplitude(
            alpha_state.amp_C, pac_ta, self.theta_alpha_kappa
        )

        # Modulate gamma amplitudes based on alpha phase
        gamma_state.amp_A = self.modulate_amplitude(
            gamma_state.amp_A, pac_ag, self.alpha_gamma_kappa
        )
        gamma_state.amp_B = self.modulate_amplitude(
            gamma_state.amp_B, pac_ag, self.alpha_gamma_kappa
        )
        gamma_state.amp_C = self.modulate_amplitude(
            gamma_state.amp_C, pac_ag, self.alpha_gamma_kappa
        )

        # Record history
        self.pac_history_theta_alpha.append(pac_ta)
        self.pac_history_alpha_gamma.append(pac_ag)
        if len(self.pac_history_theta_alpha) > 100:
            self.pac_history_theta_alpha = self.pac_history_theta_alpha[-100:]
            self.pac_history_alpha_gamma = self.pac_history_alpha_gamma[-100:]

        return alpha_state, gamma_state, pac_ta, pac_ag

    def get_statistics(self) -> Dict:
        """Get PAC statistics"""
        stats = {
            'theta_alpha_strength': self.theta_alpha_strength,
            'alpha_gamma_strength': self.alpha_gamma_strength,
            'theta_alpha_kappa': self.theta_alpha_kappa,
            'alpha_gamma_kappa': self.alpha_gamma_kappa
        }

        if self.pac_history_theta_alpha:
            stats['theta_alpha_mean'] = np.mean(self.pac_history_theta_alpha)
            stats['theta_alpha_std'] = np.std(self.pac_history_theta_alpha)
        if self.pac_history_alpha_gamma:
            stats['alpha_gamma_mean'] = np.mean(self.pac_history_alpha_gamma)
            stats['alpha_gamma_std'] = np.std(self.pac_history_alpha_gamma)

        return stats


class MultiBandOscillator:
    """
    Multi-Band Oscillator with Phase-Amplitude Coupling

    Wraps the existing ActionPotentialOscillator to add multi-frequency
    neural oscillations (Theta, Alpha, Gamma) with biologically-inspired
    Phase-Amplitude Coupling.

    The base oscillator (if provided) is used to drive the Alpha band,
    maintaining backward compatibility while adding Theta and Gamma.

    Usage:
        osc = MultiBandOscillator()

        # Step with external input
        state = osc.step(external_input={'advance': 0.8, 'explore': 0.2, 'correct': 0.1})

        # Get multi-band state
        print(f"Theta power: {state.theta.power}")
        print(f"PAC theta->alpha: {state.pac_theta_alpha}")

        # Backward compatible legacy output
        legacy_6d = state.to_legacy_6d()
        legacy_state = state.to_legacy_state()
    """

    def __init__(
        self,
        base_oscillator: Optional[ActionPotentialOscillator] = None,
        theta_freq: float = 6.0,      # Hz (4-8 range)
        alpha_freq: float = 10.0,     # Hz (8-12 range)
        gamma_freq: float = 40.0,     # Hz (30-100 range)
        theta_coupling: float = 0.3,
        alpha_coupling: float = 0.5,
        gamma_coupling: float = 0.7,
        pac_theta_alpha: float = 0.5,
        pac_alpha_gamma: float = 0.5,
        amplitude_decay: float = 0.95,
        device: str = 'cpu'
    ):
        """
        Initialize multi-band oscillator

        Args:
            base_oscillator: Optional existing oscillator to wrap (used for alpha)
            theta_freq: Theta band center frequency (Hz)
            alpha_freq: Alpha band center frequency (Hz)
            gamma_freq: Gamma band center frequency (Hz)
            theta_coupling: Kuramoto coupling strength for theta
            alpha_coupling: Kuramoto coupling strength for alpha
            gamma_coupling: Kuramoto coupling strength for gamma
            pac_theta_alpha: PAC strength theta->alpha
            pac_alpha_gamma: PAC strength alpha->gamma
            amplitude_decay: Amplitude decay factor
            device: Torch device for neural coupling
        """
        self.device = device
        self.amplitude_decay = amplitude_decay

        # Frequency parameters (convert Hz to rad/step for dt=1)
        # Assuming step corresponds to ~100ms, scale appropriately
        self.theta_freq = theta_freq
        self.alpha_freq = alpha_freq
        self.gamma_freq = gamma_freq

        # Angular velocities (rad/step) - scaled for reasonable dynamics
        # Using a time constant that gives ~1 cycle per several steps
        self.theta_omega = theta_freq * 0.1   # ~0.6 rad/step
        self.alpha_omega = alpha_freq * 0.1   # ~1.0 rad/step
        self.gamma_omega = gamma_freq * 0.1   # ~4.0 rad/step

        # Coupling strengths
        self.theta_coupling = theta_coupling
        self.alpha_coupling = alpha_coupling
        self.gamma_coupling = gamma_coupling

        # Base oscillator (for alpha band and legacy compatibility)
        if base_oscillator is not None:
            self.base_oscillator = base_oscillator
        else:
            self.base_oscillator = ActionPotentialOscillator(
                natural_frequencies=(self.alpha_omega, self.alpha_omega * 1.2, self.alpha_omega * 0.8),
                coupling_strength=alpha_coupling,
                amplitude_decay=amplitude_decay,
                use_neural_coupling=False,  # Use Kuramoto for simplicity
                device=device
            )

        # Initialize band states
        self.theta_state = BandState(
            band=FrequencyBand.THETA,
            phase_A=0.0,
            phase_B=2 * np.pi / 3,
            phase_C=4 * np.pi / 3,
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            base_frequency=theta_freq,
            coupling_strength=theta_coupling,
            amplitude_decay=amplitude_decay
        )

        self.alpha_state = BandState(
            band=FrequencyBand.ALPHA,
            phase_A=0.0,
            phase_B=2 * np.pi / 3,
            phase_C=4 * np.pi / 3,
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            base_frequency=alpha_freq,
            coupling_strength=alpha_coupling,
            amplitude_decay=amplitude_decay
        )

        self.gamma_state = BandState(
            band=FrequencyBand.GAMMA,
            phase_A=0.0,
            phase_B=2 * np.pi / 3,
            phase_C=4 * np.pi / 3,
            amp_A=0.5, amp_B=0.5, amp_C=0.5,
            base_frequency=gamma_freq,
            coupling_strength=gamma_coupling,
            amplitude_decay=amplitude_decay
        )

        # Phase-Amplitude Coupler
        self.pac_coupler = PhaseAmplitudeCoupler(
            theta_alpha_strength=pac_theta_alpha,
            alpha_gamma_strength=pac_alpha_gamma
        )

        # State tracking
        self.beat_index = 0
        self.state_history: List[MultiBandState] = []

    def step(
        self,
        external_input: Optional[Dict[str, float]] = None,
        dt: float = 1.0,
        band_weights: Optional[Dict[str, float]] = None
    ) -> MultiBandState:
        """
        Advance all bands by one time step with PAC coupling

        Args:
            external_input: Dict with 'advance', 'explore', 'correct' activations
            dt: Time step size
            band_weights: Optional weights for band influence {'theta': w, 'alpha': w, 'gamma': w}

        Returns:
            MultiBandState with updated states and PAC metrics
        """
        # Parse external input
        ext_A = external_input.get('advance', 0.0) if external_input else 0.0
        ext_B = external_input.get('explore', 0.0) if external_input else 0.0
        ext_C = external_input.get('correct', 0.0) if external_input else 0.0

        # Parse band weights (default: equal influence)
        if band_weights is None:
            band_weights = {'theta': 1.0, 'alpha': 1.0, 'gamma': 1.0}

        # Step 1: Update theta band (slowest, drives planning)
        self._step_band(
            self.theta_state,
            ext_A * band_weights.get('theta', 1.0),
            ext_B * band_weights.get('theta', 1.0),
            ext_C * band_weights.get('theta', 1.0),
            self.theta_omega,
            dt
        )

        # Step 2: Update alpha band (via base oscillator for compatibility)
        # The base oscillator handles alpha dynamics
        base_state = self.base_oscillator.step(
            external_input={
                'advance': ext_A * band_weights.get('alpha', 1.0),
                'explore': ext_B * band_weights.get('alpha', 1.0),
                'correct': ext_C * band_weights.get('alpha', 1.0)
            },
            dt=dt
        )
        # Sync alpha state from base oscillator
        self.alpha_state.phase_A = base_state.A.phase
        self.alpha_state.phase_B = base_state.B.phase
        self.alpha_state.phase_C = base_state.C.phase
        self.alpha_state.amp_A = base_state.A.amplitude
        self.alpha_state.amp_B = base_state.B.amplitude
        self.alpha_state.amp_C = base_state.C.amplitude

        # Step 3: Update gamma band (fastest, action execution)
        self._step_band(
            self.gamma_state,
            ext_A * band_weights.get('gamma', 1.0),
            ext_B * band_weights.get('gamma', 1.0),
            ext_C * band_weights.get('gamma', 1.0),
            self.gamma_omega,
            dt
        )

        # Step 4: Apply Phase-Amplitude Coupling
        self.alpha_state, self.gamma_state, pac_ta, pac_ag = self.pac_coupler.apply_coupling(
            self.theta_state,
            self.alpha_state,
            self.gamma_state
        )

        # Create combined state
        self.beat_index += 1
        state = MultiBandState(
            theta=BandState(
                band=FrequencyBand.THETA,
                phase_A=self.theta_state.phase_A,
                phase_B=self.theta_state.phase_B,
                phase_C=self.theta_state.phase_C,
                amp_A=self.theta_state.amp_A,
                amp_B=self.theta_state.amp_B,
                amp_C=self.theta_state.amp_C,
                base_frequency=self.theta_freq,
                coupling_strength=self.theta_coupling,
                amplitude_decay=self.amplitude_decay
            ),
            alpha=BandState(
                band=FrequencyBand.ALPHA,
                phase_A=self.alpha_state.phase_A,
                phase_B=self.alpha_state.phase_B,
                phase_C=self.alpha_state.phase_C,
                amp_A=self.alpha_state.amp_A,
                amp_B=self.alpha_state.amp_B,
                amp_C=self.alpha_state.amp_C,
                base_frequency=self.alpha_freq,
                coupling_strength=self.alpha_coupling,
                amplitude_decay=self.amplitude_decay
            ),
            gamma=BandState(
                band=FrequencyBand.GAMMA,
                phase_A=self.gamma_state.phase_A,
                phase_B=self.gamma_state.phase_B,
                phase_C=self.gamma_state.phase_C,
                amp_A=self.gamma_state.amp_A,
                amp_B=self.gamma_state.amp_B,
                amp_C=self.gamma_state.amp_C,
                base_frequency=self.gamma_freq,
                coupling_strength=self.gamma_coupling,
                amplitude_decay=self.amplitude_decay
            ),
            pac_theta_alpha=pac_ta,
            pac_alpha_gamma=pac_ag,
            beat_index=self.beat_index
        )

        # Store in history
        self.state_history.append(state)
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]

        return state

    def _step_band(
        self,
        band_state: BandState,
        ext_A: float,
        ext_B: float,
        ext_C: float,
        omega: float,
        dt: float
    ):
        """
        Update a single band using Kuramoto-style dynamics

        Args:
            band_state: The band state to update (modified in place)
            ext_A, ext_B, ext_C: External inputs for each channel
            omega: Angular velocity for this band
            dt: Time step
        """
        K = band_state.coupling_strength
        decay = band_state.amplitude_decay

        # Current state
        theta_A, theta_B, theta_C = band_state.phase_A, band_state.phase_B, band_state.phase_C
        amp_A, amp_B, amp_C = band_state.amp_A, band_state.amp_B, band_state.amp_C

        # Phase coupling (Kuramoto)
        dtheta_A = omega + K * (
            amp_B * np.sin(theta_B - theta_A) +
            amp_C * np.sin(theta_C - theta_A)
        )
        dtheta_B = omega * 1.1 + K * (  # Slight frequency variation
            amp_A * np.sin(theta_A - theta_B) +
            amp_C * np.sin(theta_C - theta_B)
        )
        dtheta_C = omega * 0.9 + K * (
            amp_A * np.sin(theta_A - theta_C) +
            amp_B * np.sin(theta_B - theta_C)
        )

        # Amplitude competition
        total_ext = ext_A + ext_B + ext_C + 1e-6
        norm_A, norm_B, norm_C = ext_A / total_ext, ext_B / total_ext, ext_C / total_ext

        # Update amplitudes
        band_state.amp_A = np.clip(
            decay * amp_A + 0.3 * ext_A + 0.1 * norm_A, 0.0, 1.0
        )
        band_state.amp_B = np.clip(
            decay * amp_B + 0.3 * ext_B + 0.1 * norm_B, 0.0, 1.0
        )
        band_state.amp_C = np.clip(
            decay * amp_C + 0.3 * ext_C + 0.1 * norm_C, 0.0, 1.0
        )

        # Update phases
        band_state.phase_A = (theta_A + dt * dtheta_A) % (2 * np.pi)
        band_state.phase_B = (theta_B + dt * dtheta_B) % (2 * np.pi)
        band_state.phase_C = (theta_C + dt * dtheta_C) % (2 * np.pi)

    def get_state(self) -> MultiBandState:
        """Get current multi-band state"""
        return MultiBandState(
            theta=self.theta_state,
            alpha=self.alpha_state,
            gamma=self.gamma_state,
            pac_theta_alpha=self.pac_coupler.pac_history_theta_alpha[-1] if self.pac_coupler.pac_history_theta_alpha else 0.0,
            pac_alpha_gamma=self.pac_coupler.pac_history_alpha_gamma[-1] if self.pac_coupler.pac_history_alpha_gamma else 0.0,
            beat_index=self.beat_index
        )

    def get_band_power(self, band: FrequencyBand) -> float:
        """Get power for specific band"""
        if band == FrequencyBand.THETA:
            return self.theta_state.power
        elif band == FrequencyBand.ALPHA:
            return self.alpha_state.power
        else:
            return self.gamma_state.power

    def get_pac_metrics(self) -> Dict[str, float]:
        """Get current PAC metrics"""
        return {
            'theta_alpha': self.pac_coupler.pac_history_theta_alpha[-1] if self.pac_coupler.pac_history_theta_alpha else 0.0,
            'alpha_gamma': self.pac_coupler.pac_history_alpha_gamma[-1] if self.pac_coupler.pac_history_alpha_gamma else 0.0,
            'theta_alpha_mean': np.mean(self.pac_coupler.pac_history_theta_alpha) if self.pac_coupler.pac_history_theta_alpha else 0.0,
            'alpha_gamma_mean': np.mean(self.pac_coupler.pac_history_alpha_gamma) if self.pac_coupler.pac_history_alpha_gamma else 0.0
        }

    def get_legacy_state(self) -> TripleOscillatorState:
        """
        Get legacy TripleOscillatorState for backward compatibility

        Uses the alpha band (which wraps the base oscillator).
        """
        return self.base_oscillator.get_state()

    def reset(self):
        """Reset all bands to initial state"""
        # Reset base oscillator
        self.base_oscillator.reset()

        # Reset theta
        self.theta_state.phase_A = 0.0
        self.theta_state.phase_B = 2 * np.pi / 3
        self.theta_state.phase_C = 4 * np.pi / 3
        self.theta_state.amp_A = 0.5
        self.theta_state.amp_B = 0.5
        self.theta_state.amp_C = 0.5

        # Reset alpha (synced from base oscillator on next step)
        self.alpha_state.phase_A = 0.0
        self.alpha_state.phase_B = 2 * np.pi / 3
        self.alpha_state.phase_C = 4 * np.pi / 3
        self.alpha_state.amp_A = 0.5
        self.alpha_state.amp_B = 0.5
        self.alpha_state.amp_C = 0.5

        # Reset gamma
        self.gamma_state.phase_A = 0.0
        self.gamma_state.phase_B = 2 * np.pi / 3
        self.gamma_state.phase_C = 4 * np.pi / 3
        self.gamma_state.amp_A = 0.5
        self.gamma_state.amp_B = 0.5
        self.gamma_state.amp_C = 0.5

        # Reset tracking
        self.beat_index = 0
        self.state_history.clear()
        self.pac_coupler.pac_history_theta_alpha.clear()
        self.pac_coupler.pac_history_alpha_gamma.clear()

    def get_statistics(self) -> Dict:
        """Get comprehensive oscillator statistics"""
        return {
            'beat_index': self.beat_index,
            'frequencies': {
                'theta': self.theta_freq,
                'alpha': self.alpha_freq,
                'gamma': self.gamma_freq
            },
            'band_powers': {
                'theta': self.theta_state.power,
                'alpha': self.alpha_state.power,
                'gamma': self.gamma_state.power
            },
            'pac': self.pac_coupler.get_statistics(),
            'history_length': len(self.state_history)
        }


if __name__ == "__main__":
    print("=" * 70)
    print("MULTI-BAND OSCILLATOR - Theta/Alpha/Gamma with PAC")
    print("=" * 70)
    print()
    print("Frequency Bands:")
    print("  THETA (4-8 Hz):  Planning, memory, hippocampal binding")
    print("  ALPHA (8-12 Hz): Thalamic gating, attention routing")
    print("  GAMMA (30-100 Hz): Feature binding, action execution")
    print()
    print("Phase-Amplitude Coupling:")
    print("  Theta phase -> Alpha amplitude")
    print("  Alpha phase -> Gamma amplitude")
    print()

    # Create multi-band oscillator
    osc = MultiBandOscillator(
        theta_freq=6.0,
        alpha_freq=10.0,
        gamma_freq=40.0,
        pac_theta_alpha=0.5,
        pac_alpha_gamma=0.5
    )

    print("Initial state:")
    state = osc.get_state()
    print(f"  Theta power: {state.theta.power:.3f}")
    print(f"  Alpha power: {state.alpha.power:.3f}")
    print(f"  Gamma power: {state.gamma.power:.3f}")
    print()

    # Simulate with different inputs
    print("Simulating with varying inputs:")
    print("-" * 70)

    scenarios = [
        {'advance': 0.8, 'explore': 0.1, 'correct': 0.1},  # Exploit mode
        {'advance': 0.2, 'explore': 0.7, 'correct': 0.1},  # Explore mode
        {'advance': 0.1, 'explore': 0.1, 'correct': 0.8},  # Correct mode
        {'advance': 0.4, 'explore': 0.4, 'correct': 0.2},  # Balanced
    ]

    for i, scenario in enumerate(scenarios):
        print(f"\nScenario {i+1}: {scenario}")

        # Run several steps
        for _ in range(5):
            state = osc.step(external_input=scenario)

        print(f"  After 5 steps:")
        print(f"    Theta: power={state.theta.power:.3f}, mean_amp={state.theta.mean_amplitude:.3f}")
        print(f"    Alpha: power={state.alpha.power:.3f}, mean_amp={state.alpha.mean_amplitude:.3f}")
        print(f"    Gamma: power={state.gamma.power:.3f}, mean_amp={state.gamma.mean_amplitude:.3f}")
        print(f"    PAC theta->alpha: {state.pac_theta_alpha:.3f}")
        print(f"    PAC alpha->gamma: {state.pac_alpha_gamma:.3f}")
        print(f"    Dominant band: {state.dominant_band.value}")

    print()
    print("-" * 70)
    print("Legacy compatibility test:")
    legacy_6d = state.to_legacy_6d()
    print(f"  Legacy 6D vector shape: {legacy_6d.shape}")
    print(f"  Legacy 6D vector: {legacy_6d}")

    legacy_state = osc.get_legacy_state()
    print(f"  Legacy state dominant: {legacy_state.dominant_channel().value}")

    print()
    print("18D full state vector shape:", state.to_18d_vector().shape)
    print()
    print("Statistics:", osc.get_statistics())
    print()
    print("=" * 70)
