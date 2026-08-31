"""
Basal Forebrain / Nucleus Basalis of Meynert — Cholinergic Cortical Modulation

Sole source of cortical acetylcholine (ACh). Implements:
1. Cortical activation via tonic/phasic ACh release
2. Attention-dependent plasticity gating (learning rate modulation)
3. Encoding vs retrieval mode switching (Hasselmo, 2006)
4. Signal-to-noise enhancement (multiplicative gain control)

References:
    - Mesulam (1995): Cholinergic innervation of neocortex
    - Hasselmo (2006): ACh and encoding/retrieval modes in hippocampus
    - Sarter et al. (2005): Tonic vs phasic cholinergic signalling
    - Everitt & Robbins (1997): Reward modulation of cholinergic output
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger('brain.basal_forebrain')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class BasalForebrainStats:
    """Accumulated statistics for the basal forebrain module."""
    total_cycles: int = 0
    avg_ach_level: float = 0.0
    encoding_mode_ratio: float = 0.0
    retrieval_mode_ratio: float = 0.0
    avg_plasticity_gain: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_ach_level': round(self.avg_ach_level, 4),
            'encoding_mode_ratio': round(self.encoding_mode_ratio, 4),
            'retrieval_mode_ratio': round(self.retrieval_mode_ratio, 4),
            'avg_plasticity_gain': round(self.avg_plasticity_gain, 4),
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class CholinergicProjection:
    """ACh release with tonic (arousal-driven baseline) and phasic (attention burst) components."""

    def __init__(self, baseline: float = 0.5, attention_gain: float = 1.0):
        self.baseline = np.clip(baseline, 0.0, 1.0)
        self.attention_gain = attention_gain
        self._tonic: float = self.baseline
        self._phasic: float = 0.0

    def compute_ach_level(
        self,
        attention_demand: float,
        arousal: float,
        reward_signal: float,
    ) -> float:
        """Compute combined ACh level. All inputs clipped to valid ranges."""
        # Tonic: slow-moving baseline driven by arousal
        tonic_target = self.baseline * (0.5 + 0.5 * np.clip(arousal, 0.0, 1.0))
        self._tonic += 0.1 * (tonic_target - self._tonic)
        self._tonic = float(np.clip(self._tonic, 0.05, 0.95))

        # Phasic: fast burst proportional to attention demand, reward-modulated
        reward_mod = 1.0 + 0.3 * np.clip(reward_signal, -1.0, 1.0)
        phasic_raw = self.attention_gain * np.clip(attention_demand, 0.0, 1.0) * reward_mod
        self._phasic = float(np.clip(phasic_raw, 0.0, 1.0))

        ach = float(np.clip(self._tonic + 0.5 * self._phasic, 0.0, 1.0))
        return ach

    @property
    def tonic(self) -> float:
        return self._tonic

    @property
    def phasic(self) -> float:
        return self._phasic


class PlasticityGate:
    """Modulated_lr = base_lr * (1 + ach_gain * ach_level). High ACh => more plasticity."""

    def __init__(self, ach_gain: float = 1.5):
        self.ach_gain = ach_gain

    def gate_plasticity(self, base_learning_rate: float, ach_level: float) -> float:
        """Return modulated learning rate (always >= base_learning_rate)."""
        modulated = base_learning_rate * (1.0 + self.ach_gain * np.clip(ach_level, 0.0, 1.0))
        return float(modulated)


class SignalToNoiseEnhancer:
    """ACh-driven multiplicative gain: boost above-mean signals, suppress below-mean."""

    def __init__(self, snr_gain: float = 0.5):
        self.snr_gain = snr_gain

    def enhance(self, cortical_signals: np.ndarray, ach_level: float) -> np.ndarray:
        """Apply SNR enhancement. Returns array of same shape."""
        signals = np.asarray(cortical_signals, dtype=np.float64)
        if signals.size == 0:
            return signals

        mean_val = float(np.mean(signals))
        gain = self.snr_gain * np.clip(ach_level, 0.0, 1.0)

        # Boost above-mean, suppress below-mean
        delta = signals - mean_val
        enhanced = signals + gain * delta

        return enhanced


class EncodingRetrievalSwitch:
    """ACh > threshold => encoding, ACh < threshold => retrieval, else balanced."""

    def __init__(
        self,
        encoding_threshold: float = 0.6,
        retrieval_threshold: float = 0.4,
        history_len: int = 50,
    ):
        self.encoding_threshold = encoding_threshold
        self.retrieval_threshold = retrieval_threshold
        self._history: deque = deque(maxlen=history_len)

    def get_mode(self, ach_level: float) -> str:
        """Return 'encoding', 'retrieval', or 'balanced' based on ACh level."""
        if ach_level > self.encoding_threshold:
            mode = 'encoding'
        elif ach_level < self.retrieval_threshold:
            mode = 'retrieval'
        else:
            mode = 'balanced'
        self._history.append(mode)
        return mode

    @property
    def history(self) -> List[str]:
        return list(self._history)

    def oscillation_detected(self, window: int = 10) -> bool:
        """Check if mode is oscillating rapidly (sign of instability)."""
        recent = list(self._history)[-window:]
        if len(recent) < window:
            return False
        transitions = sum(1 for i in range(1, len(recent)) if recent[i] != recent[i - 1])
        return transitions > window * 0.6


# ============================================================================
# Main Class
# ============================================================================

class BasalForebrain:
    """
    Complete Basal Forebrain module integrating cholinergic projection,
    plasticity gating, signal-to-noise enhancement, and memory-mode
    switching.

    Usage:
        bf = BasalForebrain()
        result = bf.process(attention_demand=0.8, arousal=0.6, reward_signal=0.2)
        # result keys: ach_level, modulated_learning_rate, memory_mode,
        #              snr_enhancement, tonic_ach, phasic_ach
    """

    def __init__(
        self,
        ach_baseline: float = 0.5,
        attention_gain: float = 1.0,
        plasticity_gain: float = 1.5,
        snr_gain: float = 0.5,
        encoding_threshold: float = 0.6,
        retrieval_threshold: float = 0.4,
    ):
        self.ach_baseline = ach_baseline

        # Sub-components
        self.projection = CholinergicProjection(
            baseline=ach_baseline, attention_gain=attention_gain,
        )
        self.plasticity_gate = PlasticityGate(ach_gain=plasticity_gain)
        self.snr_enhancer = SignalToNoiseEnhancer(snr_gain=snr_gain)
        self.encoding_switch = EncodingRetrievalSwitch(
            encoding_threshold=encoding_threshold,
            retrieval_threshold=retrieval_threshold,
        )

        # Running statistics
        self._stats = BasalForebrainStats()
        self._ach_history: deque = deque(maxlen=200)
        self._plasticity_history: deque = deque(maxlen=200)
        self._mode_counts: Dict[str, int] = {'encoding': 0, 'retrieval': 0, 'balanced': 0}

        logger.info(
            "BasalForebrain initialised — ACh baseline=%.2f, plasticity_gain=%.1f",
            ach_baseline, plasticity_gain,
        )

    # ------------------------------------------------------------------ core
    def process(
        self,
        attention_demand: float,
        arousal: float = 0.5,
        reward_signal: float = 0.0,
        base_learning_rate: float = 0.01,
        cortical_signals: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Run one cycle. Returns dict with ach_level, modulated_learning_rate,
        memory_mode, snr_enhancement, tonic_ach, phasic_ach."""
        # 1. Cholinergic projection
        ach = self.projection.compute_ach_level(attention_demand, arousal, reward_signal)

        # 2. Plasticity gate
        mod_lr = self.plasticity_gate.gate_plasticity(base_learning_rate, ach)

        # 3. Memory mode
        mode = self.encoding_switch.get_mode(ach)

        # 4. SNR enhancement (if signals provided)
        if cortical_signals is not None:
            enhanced = self.snr_enhancer.enhance(cortical_signals, ach)
            snr_out = float(np.mean(np.abs(enhanced - cortical_signals)))
        else:
            snr_out = 0.0

        # Update internal bookkeeping
        self._ach_history.append(ach)
        self._plasticity_history.append(mod_lr)
        self._mode_counts[mode] = self._mode_counts.get(mode, 0) + 1
        self._stats.total_cycles += 1

        total = max(self._stats.total_cycles, 1)
        self._stats.avg_ach_level = float(np.mean(list(self._ach_history)))
        self._stats.avg_plasticity_gain = float(np.mean(list(self._plasticity_history)))
        self._stats.encoding_mode_ratio = self._mode_counts['encoding'] / total
        self._stats.retrieval_mode_ratio = self._mode_counts['retrieval'] / total

        logger.debug(
            "BF cycle %d — ACh=%.3f mode=%s lr=%.5f",
            self._stats.total_cycles, ach, mode, mod_lr,
        )

        return {
            'ach_level': ach,
            'modulated_learning_rate': mod_lr,
            'memory_mode': mode,
            'snr_enhancement': snr_out,
            'tonic_ach': self.projection.tonic,
            'phasic_ach': self.projection.phasic,
        }

    def attention_for_learning(
        self,
        stimulus_novelty: float,
        reward_prediction_error: float,
    ) -> Dict[str, float]:
        """
        ACh-mediated attention-for-learning signal (Yu & Dayan, 2005).

        Basal forebrain ACh signals expected uncertainty — the uncertainty
        that comes from not knowing which cue is predictive. This differs
        from norepinephrine (unexpected uncertainty from environmental
        changes). ACh boosts learning rate for novel/uncertain stimuli.

        Args:
            stimulus_novelty: How novel the stimulus is [0, 1]
            reward_prediction_error: Unsigned RPE magnitude [0, 1]

        Returns:
            Dict with ach_burst, learning_boost, attention_weight
        """
        # ACh burst: driven by novelty and prediction errors
        ach_burst = stimulus_novelty * 0.6 + reward_prediction_error * 0.4
        ach_burst = min(1.0, ach_burst)

        # Learning rate boost: ACh multiplicatively increases plasticity
        learning_boost = 1.0 + ach_burst * 2.0  # Up to 3x boost

        # Attention weight: how much to weight this stimulus
        attention_weight = 0.3 + ach_burst * 0.7

        return {
            'ach_burst': round(ach_burst, 4),
            'learning_boost': round(learning_boost, 4),
            'attention_weight': round(min(1.0, attention_weight), 4),
            'expected_uncertainty': round(stimulus_novelty, 4),
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'ach_level': float(self._ach_history[-1]) if self._ach_history else self.ach_baseline,
            'tonic_ach': self.projection.tonic,
            'phasic_ach': self.projection.phasic,
            'memory_mode': self.encoding_switch.history[-1] if self.encoding_switch.history else 'balanced',
            'mode_counts': dict(self._mode_counts),
            'oscillation_detected': self.encoding_switch.oscillation_detected(),
            'total_cycles': self._stats.total_cycles,
        }

    def get_stats(self) -> BasalForebrainStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'ach_history': [round(v, 4) for v in list(self._ach_history)[-20:]],
            'mode_history': self.encoding_switch.history[-20:],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self.projection = CholinergicProjection(
            baseline=self.ach_baseline,
            attention_gain=self.projection.attention_gain,
        )
        self._ach_history.clear()
        self._plasticity_history.clear()
        self._mode_counts = {'encoding': 0, 'retrieval': 0, 'balanced': 0}
        self.encoding_switch._history.clear()
        self._stats = BasalForebrainStats()
        logger.info("BasalForebrain reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'BasalForebrain':
        """Construct from parsed YAML config dict."""
        bf = config.get('basal_forebrain', {})
        return cls(
            ach_baseline=bf.get('ach_baseline', 0.5),
            attention_gain=bf.get('attention_gain', 1.0),
            plasticity_gain=bf.get('plasticity_gain', 1.5),
            snr_gain=bf.get('snr_gain', 0.5),
            encoding_threshold=bf.get('encoding_threshold', 0.6),
            retrieval_threshold=bf.get('retrieval_threshold', 0.4),
        )

    def __repr__(self) -> str:
        return (
            f"BasalForebrain(cycles={self._stats.total_cycles}, "
            f"ach={self._stats.avg_ach_level:.3f})"
        )
