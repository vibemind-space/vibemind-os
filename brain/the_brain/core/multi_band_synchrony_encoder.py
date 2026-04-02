"""
Multi-Band Synchrony Encoder - Extended 16D Synchrony Vector

Extends the existing 9D SynchronyVector with multi-band information:

    9D Legacy (backward compatible):
        [|A|, |B|, |C|, cos_AB, sin_AB, cos_AC, sin_AC, cos_BC, sin_BC]

    7D Multi-Band Extension:
        [theta_power, alpha_power, gamma_power,
         pac_theta_alpha, pac_alpha_gamma,
         theta_gamma_coherence, alpha_gamma_ratio]

    Total: 16D

The extended vector captures:
    1. Traditional amplitude and phase relationships (9D)
    2. Frequency band power distribution (3D)
    3. Phase-Amplitude Coupling strength (2D)
    4. Cross-frequency relationships (2D)

This provides a comprehensive encoding of the oscillatory state that
can be used for:
    - Regime detection (via band power ratios)
    - Memory encoding (via theta power)
    - Attention routing (via alpha power)
    - Action binding (via gamma power)
    - Temporal coordination (via PAC metrics)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from core.synchrony_encoder import SynchronyVector, SynchronyEncoder
from core.multi_band_oscillator import (
    MultiBandState,
    MultiBandOscillator,
    FrequencyBand,
    BandState
)
from core.action_potential_oscillator import Channel


@dataclass
class MultiBandSynchronyVector:
    """
    16-dimensional multi-band synchrony vector

    Combines the legacy 9D synchrony vector with 7D multi-band features.
    """
    # Legacy 9D synchrony (backward compatible)
    legacy_sync: SynchronyVector

    # Band powers [0, 3] (sum of 3 squared amplitudes per band)
    theta_power: float
    alpha_power: float
    gamma_power: float

    # Phase-Amplitude Coupling indices [0, 1]
    pac_theta_alpha: float
    pac_alpha_gamma: float

    # Cross-frequency relationships
    theta_gamma_coherence: float  # How well theta and gamma are coordinated
    alpha_gamma_ratio: float      # Relative power: alpha / (alpha + gamma)

    # Metadata
    beat_index: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def vector(self) -> np.ndarray:
        """Get full 16D vector"""
        return np.concatenate([
            self.legacy_sync.vector,  # 9D
            np.array([
                self.theta_power,
                self.alpha_power,
                self.gamma_power,
                self.pac_theta_alpha,
                self.pac_alpha_gamma,
                self.theta_gamma_coherence,
                self.alpha_gamma_ratio
            ])  # 7D
        ])

    @property
    def legacy_vector(self) -> np.ndarray:
        """Get legacy 9D vector for backward compatibility"""
        return self.legacy_sync.vector

    @property
    def band_powers_vector(self) -> np.ndarray:
        """Get band powers as [3] vector"""
        return np.array([self.theta_power, self.alpha_power, self.gamma_power])

    @property
    def pac_vector(self) -> np.ndarray:
        """Get PAC metrics as [2] vector"""
        return np.array([self.pac_theta_alpha, self.pac_alpha_gamma])

    @property
    def total_power(self) -> float:
        """Total power across all bands"""
        return self.theta_power + self.alpha_power + self.gamma_power

    @property
    def dominant_band(self) -> FrequencyBand:
        """Band with highest power"""
        powers = {'theta': self.theta_power, 'alpha': self.alpha_power, 'gamma': self.gamma_power}
        max_band = max(powers, key=powers.get)
        return {'theta': FrequencyBand.THETA,
                'alpha': FrequencyBand.ALPHA,
                'gamma': FrequencyBand.GAMMA}[max_band]

    @property
    def normalized_band_powers(self) -> Dict[str, float]:
        """Band powers normalized to sum to 1"""
        total = self.total_power + 1e-6
        return {
            'theta': self.theta_power / total,
            'alpha': self.alpha_power / total,
            'gamma': self.gamma_power / total
        }

    @property
    def pac_strength(self) -> float:
        """Combined PAC strength (mean of both couplings)"""
        return (self.pac_theta_alpha + self.pac_alpha_gamma) / 2

    def is_theta_dominant(self, threshold: float = 0.4) -> bool:
        """Check if theta band is dominant (planning/memory mode)"""
        norm = self.normalized_band_powers
        return norm['theta'] > threshold

    def is_gamma_dominant(self, threshold: float = 0.4) -> bool:
        """Check if gamma band is dominant (action/binding mode)"""
        norm = self.normalized_band_powers
        return norm['gamma'] > threshold

    def is_alpha_suppressed(self, threshold: float = 0.2) -> bool:
        """Check if alpha is suppressed (attention engaged)"""
        norm = self.normalized_band_powers
        return norm['alpha'] < threshold

    def to_dict(self) -> Dict:
        return {
            'legacy': self.legacy_sync.to_dict(),
            'band_powers': {
                'theta': self.theta_power,
                'alpha': self.alpha_power,
                'gamma': self.gamma_power,
                'total': self.total_power
            },
            'normalized_powers': self.normalized_band_powers,
            'pac': {
                'theta_alpha': self.pac_theta_alpha,
                'alpha_gamma': self.pac_alpha_gamma,
                'combined': self.pac_strength
            },
            'cross_frequency': {
                'theta_gamma_coherence': self.theta_gamma_coherence,
                'alpha_gamma_ratio': self.alpha_gamma_ratio
            },
            'dominant_band': self.dominant_band.value,
            'beat_index': self.beat_index
        }


class MultiBandSynchronyEncoder:
    """
    Encodes MultiBandState into 16D MultiBandSynchronyVector

    The encoder:
    1. Creates a legacy 9D SynchronyVector from alpha band (for compatibility)
    2. Extracts band powers from theta/alpha/gamma
    3. Captures PAC metrics
    4. Computes cross-frequency relationships
    5. Returns combined 16D MultiBandSynchronyVector

    Usage:
        encoder = MultiBandSynchronyEncoder()
        multi_band_state = osc.step(...)
        sync_vector = encoder.encode(multi_band_state)

        # Full 16D
        full = sync_vector.vector

        # Legacy 9D (backward compatible)
        legacy = sync_vector.legacy_vector
    """

    def __init__(
        self,
        history_length: int = 100,
        smoothing_alpha: float = 0.0,
        legacy_band: FrequencyBand = FrequencyBand.ALPHA
    ):
        """
        Initialize encoder

        Args:
            history_length: Number of past vectors to keep
            smoothing_alpha: Exponential smoothing factor (0 = no smoothing)
            legacy_band: Which band to use for legacy 9D encoding (default: alpha)
        """
        self.history_length = history_length
        self.smoothing_alpha = smoothing_alpha
        self.legacy_band = legacy_band

        # Legacy encoder for 9D component
        self.legacy_encoder = SynchronyEncoder(
            history_length=history_length,
            smoothing_alpha=smoothing_alpha
        )

        # History
        self.history: List[MultiBandSynchronyVector] = []

        # Running averages
        self._smoothed_vector: Optional[np.ndarray] = None
        self._smoothed_band_powers: Optional[np.ndarray] = None

    def encode(self, multi_band_state: MultiBandState) -> MultiBandSynchronyVector:
        """
        Encode multi-band state to 16D synchrony vector

        Args:
            multi_band_state: Current MultiBandState from oscillator

        Returns:
            16D MultiBandSynchronyVector
        """
        # Get legacy 9D from alpha band
        legacy_triple_state = multi_band_state.to_legacy_state(self.legacy_band)
        legacy_sync = self.legacy_encoder.encode(legacy_triple_state)

        # Extract band powers
        theta_power = multi_band_state.theta.power
        alpha_power = multi_band_state.alpha.power
        gamma_power = multi_band_state.gamma.power

        # Get PAC metrics
        pac_theta_alpha = multi_band_state.pac_theta_alpha
        pac_alpha_gamma = multi_band_state.pac_alpha_gamma

        # Compute cross-frequency relationships
        theta_gamma_coherence = self._compute_theta_gamma_coherence(
            multi_band_state.theta,
            multi_band_state.gamma
        )
        alpha_gamma_ratio = self._compute_alpha_gamma_ratio(
            alpha_power, gamma_power
        )

        # Create multi-band synchrony vector
        sync = MultiBandSynchronyVector(
            legacy_sync=legacy_sync,
            theta_power=theta_power,
            alpha_power=alpha_power,
            gamma_power=gamma_power,
            pac_theta_alpha=pac_theta_alpha,
            pac_alpha_gamma=pac_alpha_gamma,
            theta_gamma_coherence=theta_gamma_coherence,
            alpha_gamma_ratio=alpha_gamma_ratio,
            beat_index=multi_band_state.beat_index
        )

        # Update smoothed vectors
        if self.smoothing_alpha > 0:
            raw = sync.vector
            if self._smoothed_vector is None:
                self._smoothed_vector = raw.copy()
            else:
                self._smoothed_vector = (
                    self.smoothing_alpha * raw +
                    (1 - self.smoothing_alpha) * self._smoothed_vector
                )

            band_powers = sync.band_powers_vector
            if self._smoothed_band_powers is None:
                self._smoothed_band_powers = band_powers.copy()
            else:
                self._smoothed_band_powers = (
                    self.smoothing_alpha * band_powers +
                    (1 - self.smoothing_alpha) * self._smoothed_band_powers
                )

        # Add to history
        self.history.append(sync)
        if len(self.history) > self.history_length:
            self.history = self.history[-self.history_length:]

        return sync

    def _compute_theta_gamma_coherence(
        self,
        theta_state: BandState,
        gamma_state: BandState
    ) -> float:
        """
        Compute coherence between theta and gamma bands

        Uses phase locking value between mean phases.
        High coherence indicates theta is organizing gamma timing.
        """
        # Compute phase difference between band mean phases
        theta_mean = theta_state.mean_phase
        gamma_mean = gamma_state.mean_phase

        # Phase Locking Value (PLV) approximation
        # For real PLV, we'd need history; here we use instantaneous approximation
        phase_diff = theta_mean - gamma_mean

        # Coherence based on consistency of phase relationship
        # Using cosine to measure how consistent the relationship is
        # Weight by amplitudes to emphasize when both bands are active
        amp_weight = np.sqrt(theta_state.mean_amplitude * gamma_state.mean_amplitude)
        coherence = amp_weight * (1 + np.cos(phase_diff)) / 2

        return float(np.clip(coherence, 0.0, 1.0))

    def _compute_alpha_gamma_ratio(
        self,
        alpha_power: float,
        gamma_power: float
    ) -> float:
        """
        Compute ratio of alpha to gamma power

        Returns value in [0, 1]:
            - Near 1: Alpha dominant (inhibition, idling)
            - Near 0: Gamma dominant (active processing)
            - ~0.5: Balanced
        """
        total = alpha_power + gamma_power + 1e-6
        return alpha_power / total

    def encode_from_oscillator(self, osc: MultiBandOscillator) -> MultiBandSynchronyVector:
        """
        Convenience method to encode directly from oscillator

        Args:
            osc: MultiBandOscillator instance

        Returns:
            MultiBandSynchronyVector
        """
        return self.encode(osc.get_state())

    def get_smoothed_vector(self) -> Optional[np.ndarray]:
        """Get exponentially smoothed 16D vector"""
        return self._smoothed_vector

    def get_smoothed_band_powers(self) -> Optional[np.ndarray]:
        """Get exponentially smoothed band powers [3]"""
        return self._smoothed_band_powers

    def get_history_matrix(self) -> np.ndarray:
        """Get history as [T, 16] matrix"""
        if not self.history:
            return np.zeros((0, 16))
        return np.array([s.vector for s in self.history])

    def get_legacy_history_matrix(self) -> np.ndarray:
        """Get legacy 9D history as [T, 9] matrix"""
        if not self.history:
            return np.zeros((0, 9))
        return np.array([s.legacy_vector for s in self.history])

    def get_band_power_history(self) -> np.ndarray:
        """Get band power history as [T, 3] matrix"""
        if not self.history:
            return np.zeros((0, 3))
        return np.array([s.band_powers_vector for s in self.history])

    def get_pac_history(self) -> np.ndarray:
        """Get PAC history as [T, 2] matrix"""
        if not self.history:
            return np.zeros((0, 2))
        return np.array([s.pac_vector for s in self.history])

    def detect_band_transition(
        self,
        window: int = 5,
        threshold: float = 0.2
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if a band power transition occurred recently

        Args:
            window: Number of recent samples to compare
            threshold: Change threshold for detection

        Returns:
            Dict with transition info if detected, None otherwise
        """
        if len(self.history) < window * 2:
            return None

        recent = self.get_band_power_history()[-window:]
        earlier = self.get_band_power_history()[-(window*2):-window]

        recent_mean = np.mean(recent, axis=0)
        earlier_mean = np.mean(earlier, axis=0)

        change = recent_mean - earlier_mean
        max_change_idx = np.argmax(np.abs(change))
        max_change = change[max_change_idx]

        if np.abs(max_change) > threshold:
            band_names = ['theta', 'alpha', 'gamma']
            return {
                'detected': True,
                'band': band_names[max_change_idx],
                'direction': 'increase' if max_change > 0 else 'decrease',
                'magnitude': abs(max_change),
                'from_power': earlier_mean[max_change_idx],
                'to_power': recent_mean[max_change_idx]
            }

        return None

    def detect_pac_change(
        self,
        window: int = 5,
        threshold: float = 0.15
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if PAC coupling strength changed significantly

        Args:
            window: Number of recent samples to compare
            threshold: Change threshold for detection

        Returns:
            Dict with PAC change info if detected, None otherwise
        """
        if len(self.history) < window * 2:
            return None

        recent = self.get_pac_history()[-window:]
        earlier = self.get_pac_history()[-(window*2):-window]

        recent_mean = np.mean(recent, axis=0)
        earlier_mean = np.mean(earlier, axis=0)

        change = recent_mean - earlier_mean

        results = {}
        coupling_names = ['theta_alpha', 'alpha_gamma']

        for i, name in enumerate(coupling_names):
            if np.abs(change[i]) > threshold:
                results[name] = {
                    'direction': 'increase' if change[i] > 0 else 'decrease',
                    'magnitude': abs(change[i]),
                    'from_pac': earlier_mean[i],
                    'to_pac': recent_mean[i]
                }

        if results:
            return {'detected': True, 'changes': results}
        return None

    def get_statistics(self) -> Dict:
        """Get encoder statistics"""
        stats = {
            'history_length': len(self.history),
            'smoothing_alpha': self.smoothing_alpha,
            'legacy_band': self.legacy_band.value
        }

        if self.history:
            last = self.history[-1]
            stats['current'] = {
                'band_powers': last.normalized_band_powers,
                'pac_strength': last.pac_strength,
                'dominant_band': last.dominant_band.value,
                'theta_gamma_coherence': last.theta_gamma_coherence
            }

            if len(self.history) > 1:
                band_hist = self.get_band_power_history()
                pac_hist = self.get_pac_history()
                stats['band_power_stats'] = {
                    'mean': np.mean(band_hist, axis=0).tolist(),
                    'std': np.std(band_hist, axis=0).tolist()
                }
                stats['pac_stats'] = {
                    'mean': np.mean(pac_hist, axis=0).tolist(),
                    'std': np.std(pac_hist, axis=0).tolist()
                }

        return stats

    def reset(self):
        """Reset encoder state"""
        self.legacy_encoder.reset()
        self.history.clear()
        self._smoothed_vector = None
        self._smoothed_band_powers = None


def compute_multi_band_order_parameter(
    sync_vectors: List[MultiBandSynchronyVector]
) -> Dict[str, float]:
    """
    Compute order parameters for multi-band synchronization

    Returns separate order parameters for:
    - Legacy coherence (from 9D component)
    - Band power stability
    - PAC consistency

    Args:
        sync_vectors: List of MultiBandSynchronyVector

    Returns:
        Dict with order parameters
    """
    if not sync_vectors:
        return {
            'legacy_coherence': 0.0,
            'band_stability': 0.0,
            'pac_consistency': 0.0
        }

    # Legacy coherence (from 9D)
    legacy_coherences = [s.legacy_sync.mean_coherence for s in sync_vectors]
    legacy_order = np.mean(legacy_coherences)

    # Band power stability (inverse of variance)
    band_powers = np.array([s.band_powers_vector for s in sync_vectors])
    band_var = np.mean(np.var(band_powers, axis=0))
    band_stability = 1.0 / (1.0 + band_var)

    # PAC consistency (inverse of PAC variance)
    pacs = np.array([s.pac_vector for s in sync_vectors])
    pac_var = np.mean(np.var(pacs, axis=0))
    pac_consistency = 1.0 / (1.0 + pac_var)

    return {
        'legacy_coherence': float(legacy_order),
        'band_stability': float(band_stability),
        'pac_consistency': float(pac_consistency)
    }


if __name__ == "__main__":
    print("=" * 70)
    print("MULTI-BAND SYNCHRONY ENCODER - 16D Vector from Multi-Band State")
    print("=" * 70)
    print()
    print("Vector Structure:")
    print("  9D Legacy:  [|A|, |B|, |C|, cos_AB, sin_AB, cos_AC, sin_AC, cos_BC, sin_BC]")
    print("  7D Bands:   [theta_power, alpha_power, gamma_power,")
    print("               pac_theta_alpha, pac_alpha_gamma,")
    print("               theta_gamma_coherence, alpha_gamma_ratio]")
    print("  Total: 16D")
    print()

    # Create oscillator and encoder
    from core.multi_band_oscillator import MultiBandOscillator

    osc = MultiBandOscillator()
    encoder = MultiBandSynchronyEncoder(smoothing_alpha=0.1)

    print("Encoding multi-band states over 10 beats:")
    print("-" * 70)

    scenarios = [
        {'advance': 0.8, 'explore': 0.1, 'correct': 0.1},  # Exploit
        {'advance': 0.8, 'explore': 0.1, 'correct': 0.1},
        {'advance': 0.5, 'explore': 0.5, 'correct': 0.1},  # Transition
        {'advance': 0.2, 'explore': 0.8, 'correct': 0.1},  # Explore
        {'advance': 0.2, 'explore': 0.8, 'correct': 0.1},
        {'advance': 0.1, 'explore': 0.3, 'correct': 0.8},  # Transition to correct
        {'advance': 0.1, 'explore': 0.1, 'correct': 0.9},  # Correct
        {'advance': 0.1, 'explore': 0.1, 'correct': 0.9},
        {'advance': 0.5, 'explore': 0.3, 'correct': 0.2},  # Back to balanced
        {'advance': 0.7, 'explore': 0.2, 'correct': 0.1},  # Back to exploit
    ]

    for i, scenario in enumerate(scenarios):
        state = osc.step(external_input=scenario)
        sync = encoder.encode(state)

        print(f"Beat {i+1}:")
        print(f"  Input: A={scenario['advance']:.1f}, B={scenario['explore']:.1f}, C={scenario['correct']:.1f}")
        print(f"  Band powers: theta={sync.theta_power:.3f}, alpha={sync.alpha_power:.3f}, gamma={sync.gamma_power:.3f}")
        print(f"  PAC: theta->alpha={sync.pac_theta_alpha:.3f}, alpha->gamma={sync.pac_alpha_gamma:.3f}")
        print(f"  Theta-gamma coherence: {sync.theta_gamma_coherence:.3f}")
        print(f"  Dominant band: {sync.dominant_band.value}")
        print(f"  Full 16D vector shape: {sync.vector.shape}")
        print()

    print("-" * 70)
    print("History matrix shape:", encoder.get_history_matrix().shape)
    print("Legacy history shape:", encoder.get_legacy_history_matrix().shape)
    print()

    # Detect transitions
    band_trans = encoder.detect_band_transition()
    print(f"Band transition: {band_trans}")

    pac_change = encoder.detect_pac_change()
    print(f"PAC change: {pac_change}")

    print()
    print("Order parameters:", compute_multi_band_order_parameter(encoder.history))
    print()
    print("Statistics:", encoder.get_statistics())
    print()
    print("=" * 70)
