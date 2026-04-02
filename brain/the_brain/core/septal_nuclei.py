"""
Septal Nuclei Module

The septal nuclei are a set of midline structures in the basal forebrain
that serve as the primary pacemaker for hippocampal theta rhythm and act
as a critical relay between the hippocampus and hypothalamus for emotional
and reward processing.

Neuroscience basis:
- Medial Septal Nucleus (MSN): Contains cholinergic and GABAergic neurons
  that generate rhythmic theta-frequency (4-8 Hz) input to the hippocampus.
  This theta rhythm is the "clock signal" for memory encoding and retrieval.
  (Winson, 1978; Stewart & Fox, 1990)
- Lateral Septal Nucleus (LSN): Receives hippocampal output and projects
  to hypothalamus, mediating reward and emotional modulation. Acts as
  a relay for approach/avoid decision-making.
  (Sheehan et al., 2004)
- Theta-gamma coupling: Gamma oscillations (30-80 Hz) are nested within
  theta cycles, with each theta cycle accommodating ~7 gamma bursts.
  This maps directly to working memory capacity (~7 items).
  (Buzsaki, 2002; Lisman & Jensen, 2013)
- Memory phase alternation: Encoding occurs at theta peak, retrieval at
  theta trough, allowing the hippocampus to alternate between writing
  and reading within each oscillatory cycle.
  (Hasselmo et al., 2002)

Key functions:
- Hippocampal theta rhythm generation (4-8 Hz pacemaker)
- Memory encoding/retrieval timing via theta phase
- Theta-gamma coupling for working memory capacity
- Reward and emotional relay (hippocampus <-> hypothalamus)

Integration:
- Output: MSN -> hippocampus (theta rhythm)
- Input: LSN <- hippocampus (processed memory signals)
- Output: LSN -> hypothalamus (reward/emotional relay)
- Modulated by: brainstem arousal systems, prefrontal cortex
"""

import logging
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger('brain.septal_nuclei')


@dataclass
class SeptalNucleiStats:
    """Septal nuclei processing statistics."""
    total_cycles: int = 0
    avg_theta_frequency: float = 0.0
    avg_theta_power: float = 0.0
    encoding_ratio: float = 0.0
    retrieval_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_theta_frequency': round(self.avg_theta_frequency, 3),
            'avg_theta_power': round(self.avg_theta_power, 3),
            'encoding_ratio': round(self.encoding_ratio, 3),
            'retrieval_ratio': round(self.retrieval_ratio, 3),
        }


class MedialSeptalNucleus:
    """
    Medial Septal Nucleus (MSN) — Theta pacemaker.

    Contains interleaved cholinergic and GABAergic projection neurons
    that rhythmically drive hippocampal theta oscillations at 4-8 Hz.
    Theta power scales with arousal and memory demand.

    Winson (1978): Theta rhythm is critical for memory encoding and
    retrieval. Lesions of MSN abolish hippocampal theta and impair
    spatial memory.
    Stewart & Fox (1990): GABAergic MSN neurons pace hippocampal
    interneurons via rhythmic disinhibition.
    """

    def __init__(
        self,
        theta_baseline: float = 6.0,
        theta_power_baseline: float = 0.5,
        arousal_gain: float = 1.0,
        dt: float = 0.01,
    ):
        self.theta_baseline = theta_baseline
        self.theta_power_baseline = theta_power_baseline
        self.arousal_gain = arousal_gain
        self.dt = dt

        # Internal oscillator state
        self._phase: float = 0.0
        self._frequency_history = deque(maxlen=200)
        self._power_history = deque(maxlen=200)

    def generate_theta(
        self,
        arousal: float = 0.5,
        memory_demand: float = 0.5,
    ) -> Dict[str, float]:
        """
        Generate theta oscillation based on current arousal and memory demand.

        Theta frequency is modulated by arousal (faster during active
        exploration) and power scales with both arousal and memory demand.

        Args:
            arousal: Current arousal level [0, 1]
            memory_demand: Current memory encoding/retrieval demand [0, 1]

        Returns:
            Dict with theta_frequency, theta_power, theta_phase
        """
        arousal = max(0.0, min(1.0, arousal))
        memory_demand = max(0.0, min(1.0, memory_demand))

        # Frequency: baseline modulated by arousal (4-8 Hz range)
        # Higher arousal -> faster theta (active exploration)
        freq_modulation = (arousal - 0.5) * 2.0 * self.arousal_gain
        frequency = self.theta_baseline + freq_modulation
        frequency = max(4.0, min(8.0, frequency))

        # Power: scales with arousal and memory demand
        power = self.theta_power_baseline * (
            0.5 + 0.3 * arousal + 0.2 * memory_demand
        )
        power = max(0.0, min(1.0, power))

        # Phase advances each cycle
        self._phase += 2.0 * np.pi * frequency * self.dt
        self._phase = self._phase % (2.0 * np.pi)

        self._frequency_history.append(frequency)
        self._power_history.append(power)

        return {
            'theta_frequency': round(frequency, 3),
            'theta_power': round(power, 3),
            'theta_phase': round(self._phase, 4),
        }

    def get_avg_frequency(self) -> float:
        if not self._frequency_history:
            return self.theta_baseline
        return float(np.mean(list(self._frequency_history)))

    def get_avg_power(self) -> float:
        if not self._power_history:
            return self.theta_power_baseline
        return float(np.mean(list(self._power_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'current_phase': round(self._phase, 4),
            'avg_frequency': round(self.get_avg_frequency(), 3),
            'avg_power': round(self.get_avg_power(), 3),
            'theta_baseline': self.theta_baseline,
        }


class ThetaGammaCoupler:
    """
    Theta-Gamma Coupler — Nests gamma bursts within theta cycles.

    Gamma oscillations (30-80 Hz) ride on the slower theta wave.
    Each theta cycle can accommodate approximately 7 gamma cycles,
    which maps to the classic working memory capacity of 7 +/- 2 items
    (Miller, 1956; Lisman & Jensen, 2013).

    Buzsaki (2002): Theta-gamma coupling organizes hippocampal cell
    assembly sequences, with each gamma cycle activating a distinct
    memory representation.
    """

    def __init__(self, gamma_capacity: int = 7):
        self.gamma_capacity = gamma_capacity
        self._coupling_history = deque(maxlen=200)

    def couple(
        self,
        theta_phase: float,
        gamma_items: int,
    ) -> Dict[str, Any]:
        """
        Compute theta-gamma coupling for current theta phase.

        Determines how many gamma slots are available in this theta
        cycle and how strongly gamma is phase-locked to theta.

        Args:
            theta_phase: Current theta phase [0, 2*pi]
            gamma_items: Number of items to encode in gamma bursts

        Returns:
            Dict with n_gamma_slots, coupling_strength, phase_locking
        """
        gamma_items = max(0, gamma_items)

        # Available gamma slots: capacity modulated by theta phase
        # Peak of theta (phase ~pi/2) has strongest coupling
        phase_factor = 0.5 + 0.5 * np.cos(theta_phase - np.pi / 2)
        n_gamma_slots = max(1, int(self.gamma_capacity * phase_factor))

        # Coupling strength: how well gamma locks to theta
        # Stronger when items fit within capacity
        load_ratio = gamma_items / max(1, self.gamma_capacity)
        coupling_strength = 1.0 - 0.5 * max(0.0, load_ratio - 1.0)
        coupling_strength = max(0.0, min(1.0, coupling_strength))

        # Phase locking value (PLV): higher when coupling is strong
        # Decreases with overload
        phase_locking = coupling_strength * phase_factor
        phase_locking = max(0.0, min(1.0, phase_locking))

        self._coupling_history.append(coupling_strength)

        return {
            'n_gamma_slots': n_gamma_slots,
            'coupling_strength': round(coupling_strength, 3),
            'phase_locking': round(phase_locking, 3),
        }

    def get_avg_coupling(self) -> float:
        if not self._coupling_history:
            return 0.0
        return float(np.mean(list(self._coupling_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'gamma_capacity': self.gamma_capacity,
            'avg_coupling': round(self.get_avg_coupling(), 3),
        }


class LateralSeptalNucleus:
    """
    Lateral Septal Nucleus (LSN) — Emotional and reward relay.

    Receives hippocampal output and projects to the hypothalamus,
    integrating reward and threat signals to compute approach/avoid
    biases. Acts as a critical relay for translating memory-based
    evaluations into motivational drives.

    Sheehan et al. (2004): LSN modulates hypothalamic output for
    reward processing and defensive behaviors.
    """

    def __init__(self):
        self._valence_history = deque(maxlen=200)

    def modulate(
        self,
        reward_signal: float = 0.0,
        threat_signal: float = 0.0,
    ) -> Dict[str, float]:
        """
        Integrate reward and threat signals for approach/avoid bias.

        Args:
            reward_signal: Reward magnitude [-1, 1] (negative = punishment)
            threat_signal: Threat level [0, 1]

        Returns:
            Dict with approach_drive, avoid_drive, emotional_valence
        """
        reward_signal = max(-1.0, min(1.0, reward_signal))
        threat_signal = max(0.0, min(1.0, threat_signal))

        # Approach drive: increases with reward, suppressed by threat
        approach_drive = max(0.0, reward_signal) * (1.0 - threat_signal * 0.7)
        approach_drive = max(0.0, min(1.0, approach_drive))

        # Avoid drive: increases with threat and punishment
        avoid_drive = threat_signal * 0.7 + max(0.0, -reward_signal) * 0.3
        avoid_drive = max(0.0, min(1.0, avoid_drive))

        # Emotional valence: net reward/threat balance
        emotional_valence = reward_signal * 0.6 - threat_signal * 0.4
        emotional_valence = max(-1.0, min(1.0, emotional_valence))

        self._valence_history.append(emotional_valence)

        return {
            'approach_drive': round(approach_drive, 3),
            'avoid_drive': round(avoid_drive, 3),
            'emotional_valence': round(emotional_valence, 3),
        }

    def get_avg_valence(self) -> float:
        if not self._valence_history:
            return 0.0
        return float(np.mean(list(self._valence_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'avg_valence': round(self.get_avg_valence(), 3),
        }


class MemoryTimingController:
    """
    Memory Timing Controller — Alternates encoding and retrieval.

    Memory operations alternate with theta phase: encoding occurs at
    the peak of theta (when EC->CA1 input is strongest) and retrieval
    at the trough (when CA3->CA1 input dominates).

    Hasselmo et al. (2002): Acetylcholine levels fluctuate with theta,
    high ACh at theta peak suppresses CA3 feedback and enhances EC
    input (encoding mode), while low ACh at trough allows CA3
    recurrence (retrieval mode).
    """

    def __init__(self):
        self._encoding_count: int = 0
        self._retrieval_count: int = 0

    def get_memory_phase(self, theta_phase: float) -> str:
        """
        Determine current memory operation phase from theta phase.

        Args:
            theta_phase: Current theta oscillation phase [0, 2*pi]

        Returns:
            'encoding' at theta peak, 'retrieval' at theta trough
        """
        # Peak region: [0, pi) -> encoding
        # Trough region: [pi, 2*pi) -> retrieval
        phase = theta_phase % (2.0 * np.pi)
        if phase < np.pi:
            self._encoding_count += 1
            return 'encoding'
        else:
            self._retrieval_count += 1
            return 'retrieval'

    @property
    def encoding_ratio(self) -> float:
        total = self._encoding_count + self._retrieval_count
        if total == 0:
            return 0.0
        return self._encoding_count / total

    @property
    def retrieval_ratio(self) -> float:
        total = self._encoding_count + self._retrieval_count
        if total == 0:
            return 0.0
        return self._retrieval_count / total

    def to_dict(self) -> Dict[str, Any]:
        return {
            'encoding_count': self._encoding_count,
            'retrieval_count': self._retrieval_count,
            'encoding_ratio': round(self.encoding_ratio, 3),
            'retrieval_ratio': round(self.retrieval_ratio, 3),
        }


class SeptalNuclei:
    """
    Complete Septal Nuclei module.

    Integrates the medial septal nucleus (theta pacemaker), theta-gamma
    coupler, lateral septal nucleus (reward/emotional relay), and memory
    timing controller into a unified oscillatory timing system for memory
    and emotional processing.

    Functions:
    1. Hippocampal theta rhythm generation (MSN)
    2. Theta-gamma coupling for working memory capacity (TGC)
    3. Memory encode/retrieve phase alternation (MTC)
    4. Reward and threat relay to hypothalamus (LSN)
    """

    def __init__(
        self,
        theta_baseline: float = 6.0,
        theta_power_baseline: float = 0.5,
        gamma_capacity: int = 7,
        arousal_gain: float = 1.0,
        dt: float = 0.01,
    ):
        self.msn = MedialSeptalNucleus(
            theta_baseline=theta_baseline,
            theta_power_baseline=theta_power_baseline,
            arousal_gain=arousal_gain,
            dt=dt,
        )
        self.coupler = ThetaGammaCoupler(gamma_capacity=gamma_capacity)
        self.lsn = LateralSeptalNucleus()
        self.timing = MemoryTimingController()
        self._stats = SeptalNucleiStats()

    def process(
        self,
        arousal: float = 0.5,
        memory_demand: float = 0.5,
        reward_signal: float = 0.0,
        threat_signal: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Full septal nuclei processing cycle.

        1. MSN generates theta rhythm based on arousal and memory demand
        2. Theta-gamma coupler determines working memory slots
        3. Memory timing controller determines encode/retrieve phase
        4. LSN relays reward/threat for approach/avoid computation

        Args:
            arousal: Current arousal level [0, 1]
            memory_demand: Memory encoding/retrieval demand [0, 1]
            reward_signal: Reward magnitude [-1, 1]
            threat_signal: Threat level [0, 1]

        Returns:
            Dict with theta_frequency, theta_power, theta_phase,
            memory_phase, n_gamma_slots, coupling_strength,
            approach_drive, avoid_drive
        """
        # MSN: generate theta
        theta = self.msn.generate_theta(arousal, memory_demand)

        # Theta-gamma coupling: use memory_demand as proxy for item count
        gamma_items = max(1, int(memory_demand * self.coupler.gamma_capacity))
        coupling = self.coupler.couple(theta['theta_phase'], gamma_items)

        # Memory timing: encode or retrieve
        memory_phase = self.timing.get_memory_phase(theta['theta_phase'])

        # LSN: reward/threat modulation
        modulation = self.lsn.modulate(reward_signal, threat_signal)

        # Update stats
        self._stats.total_cycles += 1
        self._stats.avg_theta_frequency = self.msn.get_avg_frequency()
        self._stats.avg_theta_power = self.msn.get_avg_power()
        self._stats.encoding_ratio = self.timing.encoding_ratio
        self._stats.retrieval_ratio = self.timing.retrieval_ratio

        return {
            'theta_frequency': theta['theta_frequency'],
            'theta_power': theta['theta_power'],
            'theta_phase': theta['theta_phase'],
            'memory_phase': memory_phase,
            'n_gamma_slots': coupling['n_gamma_slots'],
            'coupling_strength': coupling['coupling_strength'],
            'approach_drive': modulation['approach_drive'],
            'avoid_drive': modulation['avoid_drive'],
        }

    def theta_gamma_memory_capacity(self) -> Dict[str, float]:
        """
        Theta-gamma coupling memory capacity (Lisman & Jensen, 2013).

        The number of items in working memory is limited by the number of
        gamma cycles that fit within one theta cycle. Each gamma burst
        (~40ms) encodes one item; theta provides the organizing frame
        (~125ms = ~7 gamma cycles, matching Miller's magical number 7).

        Returns:
            Dict with memory_slots, theta_freq, gamma_freq, coupling_quality
        """
        theta_freq = self.msn.frequency  # ~8 Hz
        gamma_freq = 40.0  # Typical gamma ~40 Hz

        # Slots = gamma_freq / theta_freq (how many gamma in one theta)
        if theta_freq > 0:
            memory_slots = gamma_freq / theta_freq
        else:
            memory_slots = 7.0

        # Coupling quality from the coupler
        coupling_strength = self.coupler._coupling_strength

        # Effective slots: degraded by poor coupling
        effective_slots = memory_slots * coupling_strength

        return {
            'memory_slots': round(memory_slots, 1),
            'effective_slots': round(effective_slots, 1),
            'theta_frequency': round(theta_freq, 2),
            'gamma_frequency': round(gamma_freq, 2),
            'coupling_quality': round(coupling_strength, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'msn': self.msn.to_dict(),
            'coupler': self.coupler.to_dict(),
            'lsn': self.lsn.to_dict(),
            'timing': self.timing.to_dict(),
        }

    def get_stats(self) -> SeptalNucleiStats:
        return self._stats

    def reset(self):
        self._stats = SeptalNucleiStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'SeptalNuclei':
        cfg = config.get('septal_nuclei', {})
        return cls(
            theta_baseline=cfg.get('theta_baseline', 6.0),
            theta_power_baseline=cfg.get('theta_power_baseline', 0.5),
            gamma_capacity=cfg.get('gamma_capacity', 7),
            arousal_gain=cfg.get('arousal_gain', 1.0),
            dt=cfg.get('dt', 0.01),
        )
