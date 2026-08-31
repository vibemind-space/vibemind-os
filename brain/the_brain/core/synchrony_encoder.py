"""
Synchrony Encoder - Computes 9-D Synchrony Vector from Oscillator States

The synchrony vector encodes BOTH time and location:
    - TIME: Phase positions within global beat
    - LOCATION: Which regime the system is in (via synchrony patterns)

Synchrony Vector (9 dimensions):
    sync = [|A|, |B|, |C|,              # 3 amplitudes
            cos(ΔAB), sin(ΔAB),          # Phase diff A-B
            cos(ΔAC), sin(ΔAC),          # Phase diff A-C
            cos(ΔBC), sin(ΔBC)]          # Phase diff B-C

Where ΔXY = θ_X - θ_Y (phase difference between oscillators)

The cos/sin encoding preserves the circular nature of phase:
    - cos(Δ) = 1, sin(Δ) = 0  → In-phase (synchronized)
    - cos(Δ) = -1, sin(Δ) = 0 → Anti-phase (opposite)
    - cos(Δ) = 0, sin(Δ) = ±1 → Quadrature (90° offset)

This vector can be used to:
    1. Detect operational regimes (via synchrony patterns)
    2. Drive the 3×N Drumpad (amplitude → row, phase → column)
    3. Encode temporal trajectories for learning
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from core.action_potential_oscillator import (
    TripleOscillatorState,
    OscillatorState,
    Channel
)


@dataclass
class SynchronyVector:
    """
    9-dimensional synchrony vector

    Encodes amplitudes and phase relationships between A, B, C oscillators.
    """
    # Amplitudes [0, 1]
    amp_A: float
    amp_B: float
    amp_C: float

    # Phase difference A-B encoded as (cos, sin)
    cos_AB: float
    sin_AB: float

    # Phase difference A-C encoded as (cos, sin)
    cos_AC: float
    sin_AC: float

    # Phase difference B-C encoded as (cos, sin)
    cos_BC: float
    sin_BC: float

    # Metadata
    beat_index: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def vector(self) -> np.ndarray:
        """Get as numpy array [9]"""
        return np.array([
            self.amp_A, self.amp_B, self.amp_C,
            self.cos_AB, self.sin_AB,
            self.cos_AC, self.sin_AC,
            self.cos_BC, self.sin_BC
        ])

    @property
    def amplitudes(self) -> np.ndarray:
        """Get amplitude sub-vector [3]"""
        return np.array([self.amp_A, self.amp_B, self.amp_C])

    @property
    def phase_coherence_AB(self) -> float:
        """Phase coherence between A and B (1 = locked, 0 = drifting)"""
        return np.sqrt(self.cos_AB**2 + self.sin_AB**2)

    @property
    def phase_coherence_AC(self) -> float:
        """Phase coherence between A and C"""
        return np.sqrt(self.cos_AC**2 + self.sin_AC**2)

    @property
    def phase_coherence_BC(self) -> float:
        """Phase coherence between B and C"""
        return np.sqrt(self.cos_BC**2 + self.sin_BC**2)

    @property
    def mean_coherence(self) -> float:
        """Mean phase coherence across all pairs"""
        return (self.phase_coherence_AB + self.phase_coherence_AC + self.phase_coherence_BC) / 3

    @property
    def phase_AB_degrees(self) -> float:
        """Phase difference A-B in degrees"""
        return np.degrees(np.arctan2(self.sin_AB, self.cos_AB))

    @property
    def phase_AC_degrees(self) -> float:
        """Phase difference A-C in degrees"""
        return np.degrees(np.arctan2(self.sin_AC, self.cos_AC))

    @property
    def phase_BC_degrees(self) -> float:
        """Phase difference B-C in degrees"""
        return np.degrees(np.arctan2(self.sin_BC, self.cos_BC))

    def dominant_channel(self) -> Channel:
        """Channel with highest amplitude"""
        amps = {'A': self.amp_A, 'B': self.amp_B, 'C': self.amp_C}
        max_ch = max(amps, key=amps.get)
        return {'A': Channel.ADVANCE, 'B': Channel.EXPLORE, 'C': Channel.CORRECT}[max_ch]

    def is_in_phase(self, pair: str, threshold: float = 0.8) -> bool:
        """Check if pair is in-phase (cos ≈ 1)"""
        if pair == 'AB':
            return self.cos_AB > threshold
        elif pair == 'AC':
            return self.cos_AC > threshold
        elif pair == 'BC':
            return self.cos_BC > threshold
        return False

    def is_anti_phase(self, pair: str, threshold: float = -0.8) -> bool:
        """Check if pair is anti-phase (cos ≈ -1)"""
        if pair == 'AB':
            return self.cos_AB < threshold
        elif pair == 'AC':
            return self.cos_AC < threshold
        elif pair == 'BC':
            return self.cos_BC < threshold
        return False

    def to_dict(self) -> Dict:
        return {
            'amplitudes': {
                'A': self.amp_A,
                'B': self.amp_B,
                'C': self.amp_C
            },
            'phase_diffs': {
                'AB': {'cos': self.cos_AB, 'sin': self.sin_AB, 'degrees': self.phase_AB_degrees},
                'AC': {'cos': self.cos_AC, 'sin': self.sin_AC, 'degrees': self.phase_AC_degrees},
                'BC': {'cos': self.cos_BC, 'sin': self.sin_BC, 'degrees': self.phase_BC_degrees}
            },
            'coherence': {
                'AB': self.phase_coherence_AB,
                'AC': self.phase_coherence_AC,
                'BC': self.phase_coherence_BC,
                'mean': self.mean_coherence
            },
            'dominant': self.dominant_channel().value,
            'beat_index': self.beat_index
        }


class SynchronyEncoder:
    """
    Encodes oscillator states into 9-D synchrony vectors

    The encoder:
    1. Takes TripleOscillatorState as input
    2. Computes amplitudes and phase differences
    3. Encodes phase diffs as (cos, sin) pairs
    4. Returns SynchronyVector

    Can also:
    - Track synchrony history
    - Compute running statistics
    - Detect synchrony transitions
    """

    def __init__(
        self,
        history_length: int = 100,
        smoothing_alpha: float = 0.0  # 0 = no smoothing, >0 = exponential smoothing
    ):
        """
        Initialize encoder

        Args:
            history_length: Number of past vectors to keep
            smoothing_alpha: Exponential smoothing factor for stable readouts
        """
        self.history_length = history_length
        self.smoothing_alpha = smoothing_alpha

        # History
        self.history: List[SynchronyVector] = []

        # Running average (for smoothed output)
        self._smoothed_vector: Optional[np.ndarray] = None

    def encode(self, osc_state: TripleOscillatorState) -> SynchronyVector:
        """
        Encode oscillator state to synchrony vector

        Args:
            osc_state: Current oscillator state with A, B, C

        Returns:
            9-D SynchronyVector
        """
        # Extract amplitudes
        amp_A = osc_state.A.amplitude
        amp_B = osc_state.B.amplitude
        amp_C = osc_state.C.amplitude

        # Compute phase differences
        delta_AB = osc_state.A.phase - osc_state.B.phase
        delta_AC = osc_state.A.phase - osc_state.C.phase
        delta_BC = osc_state.B.phase - osc_state.C.phase

        # Encode as (cos, sin) pairs
        cos_AB, sin_AB = np.cos(delta_AB), np.sin(delta_AB)
        cos_AC, sin_AC = np.cos(delta_AC), np.sin(delta_AC)
        cos_BC, sin_BC = np.cos(delta_BC), np.sin(delta_BC)

        # Create synchrony vector
        sync = SynchronyVector(
            amp_A=amp_A,
            amp_B=amp_B,
            amp_C=amp_C,
            cos_AB=cos_AB,
            sin_AB=sin_AB,
            cos_AC=cos_AC,
            sin_AC=sin_AC,
            cos_BC=cos_BC,
            sin_BC=sin_BC,
            beat_index=osc_state.beat_index
        )

        # Update smoothed vector
        if self.smoothing_alpha > 0:
            raw = sync.vector
            if self._smoothed_vector is None:
                self._smoothed_vector = raw.copy()
            else:
                self._smoothed_vector = (
                    self.smoothing_alpha * raw +
                    (1 - self.smoothing_alpha) * self._smoothed_vector
                )

        # Add to history
        self.history.append(sync)
        if len(self.history) > self.history_length:
            self.history = self.history[-self.history_length:]

        return sync

    def encode_from_raw(
        self,
        amplitudes: Tuple[float, float, float],
        phases: Tuple[float, float, float],
        beat_index: int = 0
    ) -> SynchronyVector:
        """
        Encode from raw amplitude and phase values

        Args:
            amplitudes: (amp_A, amp_B, amp_C)
            phases: (phase_A, phase_B, phase_C)
            beat_index: Current beat

        Returns:
            SynchronyVector
        """
        amp_A, amp_B, amp_C = amplitudes
        phase_A, phase_B, phase_C = phases

        delta_AB = phase_A - phase_B
        delta_AC = phase_A - phase_C
        delta_BC = phase_B - phase_C

        return SynchronyVector(
            amp_A=amp_A,
            amp_B=amp_B,
            amp_C=amp_C,
            cos_AB=np.cos(delta_AB),
            sin_AB=np.sin(delta_AB),
            cos_AC=np.cos(delta_AC),
            sin_AC=np.sin(delta_AC),
            cos_BC=np.cos(delta_BC),
            sin_BC=np.sin(delta_BC),
            beat_index=beat_index
        )

    def get_smoothed_vector(self) -> Optional[np.ndarray]:
        """Get exponentially smoothed synchrony vector"""
        return self._smoothed_vector

    def get_history_matrix(self) -> np.ndarray:
        """Get history as [T, 9] matrix"""
        if not self.history:
            return np.zeros((0, 9))
        return np.array([s.vector for s in self.history])

    def get_amplitude_history(self) -> np.ndarray:
        """Get amplitude history as [T, 3] matrix"""
        if not self.history:
            return np.zeros((0, 3))
        return np.array([s.amplitudes for s in self.history])

    def get_coherence_history(self) -> np.ndarray:
        """Get coherence history as [T, 3] matrix (AB, AC, BC)"""
        if not self.history:
            return np.zeros((0, 3))
        return np.array([
            [s.phase_coherence_AB, s.phase_coherence_AC, s.phase_coherence_BC]
            for s in self.history
        ])

    def detect_transition(self, window: int = 5, threshold: float = 0.3) -> bool:
        """
        Detect if a synchrony transition occurred recently

        Looks for significant change in coherence pattern.

        Args:
            window: Number of recent samples to compare
            threshold: Change threshold for detection

        Returns:
            True if transition detected
        """
        if len(self.history) < window * 2:
            return False

        recent = self.get_coherence_history()[-window:]
        earlier = self.get_coherence_history()[-(window*2):-window]

        recent_mean = np.mean(recent, axis=0)
        earlier_mean = np.mean(earlier, axis=0)

        change = np.linalg.norm(recent_mean - earlier_mean)
        return change > threshold

    def get_statistics(self) -> Dict:
        """Get encoder statistics"""
        stats = {
            'history_length': len(self.history),
            'smoothing_alpha': self.smoothing_alpha
        }

        if self.history:
            last = self.history[-1]
            stats['current'] = {
                'amplitudes': last.amplitudes.tolist(),
                'mean_coherence': last.mean_coherence,
                'dominant': last.dominant_channel().value
            }

            if len(self.history) > 1:
                coherence_hist = self.get_coherence_history()
                stats['coherence_stats'] = {
                    'mean': np.mean(coherence_hist, axis=0).tolist(),
                    'std': np.std(coherence_hist, axis=0).tolist()
                }

        return stats

    def reset(self):
        """Reset encoder state"""
        self.history.clear()
        self._smoothed_vector = None


def compute_order_parameter(sync_vectors: List[SynchronyVector]) -> float:
    """
    Compute Kuramoto order parameter from synchrony vectors

    The order parameter R ∈ [0, 1] measures global synchronization:
    - R ≈ 0: oscillators are incoherent (unsynchronized)
    - R ≈ 1: oscillators are fully synchronized

    Uses the mean coherence as a proxy for order parameter.

    Args:
        sync_vectors: List of synchrony vectors

    Returns:
        Order parameter R
    """
    if not sync_vectors:
        return 0.0

    coherences = [s.mean_coherence for s in sync_vectors]
    return np.mean(coherences)


if __name__ == "__main__":
    print("=" * 70)
    print("SYNCHRONY ENCODER - 9-D Vector from Oscillator States")
    print("=" * 70)
    print()
    print("Synchrony Vector:")
    print("  sync = [|A|, |B|, |C|, cos ΔAB, sin ΔAB, cos ΔAC, sin ΔAC, cos ΔBC, sin ΔBC]")
    print()

    # Create encoder
    encoder = SynchronyEncoder(smoothing_alpha=0.1)

    # Create test oscillator state
    from core.action_potential_oscillator import ActionPotentialOscillator

    osc = ActionPotentialOscillator(use_neural_coupling=False)

    print("Encoding oscillator states over 10 beats:")
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
        osc_state = osc.step(external_input=scenario)
        sync = encoder.encode(osc_state)

        print(f"Beat {i+1}:")
        print(f"  Input: A={scenario['advance']:.1f}, B={scenario['explore']:.1f}, C={scenario['correct']:.1f}")
        print(f"  Amplitudes: A={sync.amp_A:.3f}, B={sync.amp_B:.3f}, C={sync.amp_C:.3f}")
        print(f"  Coherence: AB={sync.phase_coherence_AB:.3f}, AC={sync.phase_coherence_AC:.3f}, BC={sync.phase_coherence_BC:.3f}")
        print(f"  Dominant: {sync.dominant_channel().value}")
        print(f"  Vector: {sync.vector}")
        print()

    print("-" * 70)
    print("History matrix shape:", encoder.get_history_matrix().shape)
    print()
    print("Transition detection:", encoder.detect_transition())
    print()
    print("Order parameter:", compute_order_parameter(encoder.history))
    print()
    print("Statistics:", encoder.get_statistics())
    print()
    print("=" * 70)
