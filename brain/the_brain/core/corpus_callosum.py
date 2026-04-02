"""
Corpus Callosum — Interhemispheric Communication and Bilateral Coordination

Largest white matter tract connecting left and right hemispheres.
Enables cross-hemispheric transfer, lateralisation, and bilateral
cooperative/competitive processing.

References:
    - Gazzaniga (2000): Interhemispheric communication and specialization
    - Banich (1998): Integration of information across cerebral hemispheres
"""

import logging
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.corpus_callosum')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class CorpusCallosumStats:
    """Accumulated statistics for the corpus callosum module."""
    total_transfers: int = 0
    avg_transfer_efficiency: float = 0.0
    left_dominant_count: int = 0
    right_dominant_count: int = 0
    avg_coordination: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_transfers': self.total_transfers,
            'avg_transfer_efficiency': round(self.avg_transfer_efficiency, 4),
            'left_dominant_count': self.left_dominant_count,
            'right_dominant_count': self.right_dominant_count,
            'avg_coordination': round(self.avg_coordination, 4),
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class InterhemisphericTransfer:
    """Bidirectional signal transfer between hemispheres via callosal fibres."""

    def __init__(self, bandwidth: float = 0.8, signal_dim: int = 16):
        self.bandwidth = float(np.clip(bandwidth, 0.0, 1.0))
        self.signal_dim = signal_dim
        rng = np.random.default_rng(42)
        self._w_l2r = rng.normal(0.0, 0.1, (signal_dim, signal_dim)).astype(np.float64)
        np.fill_diagonal(self._w_l2r, self.bandwidth)
        self._w_r2l = rng.normal(0.0, 0.1, (signal_dim, signal_dim)).astype(np.float64)
        np.fill_diagonal(self._w_r2l, self.bandwidth)

    def _pad(self, arr: np.ndarray) -> np.ndarray:
        a = np.asarray(arr, dtype=np.float64).flatten()[:self.signal_dim]
        if a.shape[0] < self.signal_dim:
            a = np.pad(a, (0, self.signal_dim - a.shape[0]))
        return a

    def transfer(self, left_signal: np.ndarray, right_signal: np.ndarray) -> Dict[str, Any]:
        """Transfer information between hemispheres. Returns transferred
        signals, transfer_efficiency, and bandwidth."""
        left, right = self._pad(left_signal), self._pad(right_signal)
        l2r = self.bandwidth * (self._w_l2r @ left)
        r2l = self.bandwidth * (self._w_r2l @ right)
        l2r_c = float(np.clip(np.corrcoef(left, l2r)[0, 1], -1, 1)) if np.std(left) > 1e-8 else 0.0
        r2l_c = float(np.clip(np.corrcoef(right, r2l)[0, 1], -1, 1)) if np.std(right) > 1e-8 else 0.0
        efficiency = float(np.clip(0.5 * (abs(l2r_c) + abs(r2l_c)), 0.0, 1.0))
        return {
            'transferred_left_to_right': l2r, 'transferred_right_to_left': r2l,
            'transfer_efficiency': efficiency, 'bandwidth': self.bandwidth,
        }


class HemisphericSpecializer:
    """Models functional lateralisation.
    Left: sequential, analytical, linguistic. Right: spatial, holistic, emotional."""

    def __init__(self, signal_dim: int = 16):
        self.signal_dim = signal_dim
        self._left_pref = np.zeros(signal_dim, dtype=np.float64)
        self._left_pref[:signal_dim // 2] = 1.0
        self._right_pref = np.zeros(signal_dim, dtype=np.float64)
        self._right_pref[signal_dim // 2:] = 1.0

    def specialize(self, task_features: np.ndarray) -> Dict[str, Any]:
        """Determine hemisphere dominance for a task."""
        feat = np.asarray(task_features, dtype=np.float64).flatten()[:self.signal_dim]
        if feat.shape[0] < self.signal_dim:
            feat = np.pad(feat, (0, self.signal_dim - feat.shape[0]))
        left_score = float(np.dot(feat, self._left_pref))
        right_score = float(np.dot(feat, self._right_pref))
        total = abs(left_score) + abs(right_score)
        if total < 1e-8:
            return {'dominant_hemisphere': 'left', 'lateralization_index': 0.0, 'specialization_strength': 0.0}
        lat_index = float(np.clip((left_score - right_score) / total, -1.0, 1.0))
        dominant = 'left' if lat_index >= 0.0 else 'right'
        return {
            'dominant_hemisphere': dominant,
            'lateralization_index': round(lat_index, 4),
            'specialization_strength': round(abs(lat_index), 4),
        }


class BilateralCoordinator:
    """Coordinates bilateral processing by integrating hemisphere outputs."""

    def __init__(self, coordination_gain: float = 1.0, signal_dim: int = 16):
        self.coordination_gain = coordination_gain
        self.signal_dim = signal_dim

    def _pad(self, arr: np.ndarray) -> np.ndarray:
        a = np.asarray(arr, dtype=np.float64).flatten()[:self.signal_dim]
        if a.shape[0] < self.signal_dim:
            a = np.pad(a, (0, self.signal_dim - a.shape[0]))
        return a

    def coordinate(self, left_output: np.ndarray, right_output: np.ndarray,
                   task_type: str = 'general') -> Dict[str, Any]:
        """Integrate bilateral outputs. task_type: 'analytical', 'spatial', or 'general'."""
        left, right = self._pad(left_output), self._pad(right_output)
        weights = {'analytical': (0.7, 0.3), 'spatial': (0.3, 0.7)}.get(task_type, (0.5, 0.5))
        integrated = self.coordination_gain * (weights[0] * left + weights[1] * right)
        if np.std(left) > 1e-8 and np.std(right) > 1e-8:
            cooperation = float(np.clip(np.corrcoef(left, right)[0, 1], -1.0, 1.0))
        else:
            cooperation = 0.0
        norm_ratio = min(float(np.linalg.norm(integrated)) / (self.signal_dim * 0.5 + 1e-8), 1.0)
        quality = float(np.clip(0.5 * (1.0 + cooperation) * norm_ratio, 0.0, 1.0))
        return {
            'integrated_output': integrated,
            'coordination_quality': round(quality, 4),
            'cooperation_level': round(float(np.clip(0.5 * (1.0 + cooperation), 0.0, 1.0)), 4),
        }


# ============================================================================
# Main Class
# ============================================================================

class CorpusCallosum:
    """Complete corpus callosum module integrating interhemispheric
    transfer, hemispheric specialisation, and bilateral coordination."""

    def __init__(self, transfer_bandwidth: float = 0.8, lateralization_bias: float = 0.0,
                 coordination_gain: float = 1.0, signal_dim: int = 16):
        self.transfer_bandwidth = transfer_bandwidth
        self.lateralization_bias = lateralization_bias
        self.coordination_gain = coordination_gain
        self.signal_dim = signal_dim
        self.transfer = InterhemisphericTransfer(bandwidth=transfer_bandwidth, signal_dim=signal_dim)
        self.specializer = HemisphericSpecializer(signal_dim=signal_dim)
        self.coordinator = BilateralCoordinator(coordination_gain=coordination_gain, signal_dim=signal_dim)
        self._stats = CorpusCallosumStats()
        self._efficiency_history: deque = deque(maxlen=200)
        self._coordination_history: deque = deque(maxlen=200)
        logger.info("CorpusCallosum initialised — bw=%.2f, bias=%.2f, gain=%.1f, dim=%d",
                     transfer_bandwidth, lateralization_bias, coordination_gain, signal_dim)

    def _pad(self, arr: np.ndarray) -> np.ndarray:
        a = np.asarray(arr, dtype=np.float64).flatten()[:self.signal_dim]
        if a.shape[0] < self.signal_dim:
            a = np.pad(a, (0, self.signal_dim - a.shape[0]))
        return a

    # ------------------------------------------------------------------ core
    def process(self, left_signal: Optional[np.ndarray] = None, right_signal: Optional[np.ndarray] = None,
                task_features: Optional[np.ndarray] = None, task_type: str = 'general') -> Dict[str, Any]:
        """Run one cycle of interhemispheric communication."""
        if left_signal is None:
            left_signal = np.zeros(self.signal_dim)
        if right_signal is None:
            right_signal = np.zeros(self.signal_dim)
        if task_features is None:
            task_features = np.zeros(self.signal_dim)

        xfer = self.transfer.transfer(left_signal, right_signal)
        spec = self.specializer.specialize(task_features)
        left_aug = self._pad(left_signal) + 0.3 * xfer['transferred_right_to_left']
        right_aug = self._pad(right_signal) + 0.3 * xfer['transferred_left_to_right']
        coord = self.coordinator.coordinate(left_aug, right_aug, task_type)

        self._efficiency_history.append(xfer['transfer_efficiency'])
        self._coordination_history.append(coord['coordination_quality'])
        self._stats.total_transfers += 1
        if spec['dominant_hemisphere'] == 'left':
            self._stats.left_dominant_count += 1
        else:
            self._stats.right_dominant_count += 1
        self._stats.avg_transfer_efficiency = float(np.mean(list(self._efficiency_history)))
        self._stats.avg_coordination = float(np.mean(list(self._coordination_history)))

        logger.debug("CC cycle %d — eff=%.3f dom=%s coord=%.3f",
                      self._stats.total_transfers, xfer['transfer_efficiency'],
                      spec['dominant_hemisphere'], coord['coordination_quality'])
        return {
            'transfer_efficiency': xfer['transfer_efficiency'],
            'bandwidth': xfer['bandwidth'],
            'dominant_hemisphere': spec['dominant_hemisphere'],
            'lateralization_index': spec['lateralization_index'],
            'specialization_strength': spec['specialization_strength'],
            'integrated_output': coord['integrated_output'],
            'coordination_quality': coord['coordination_quality'],
            'cooperation_level': coord['cooperation_level'],
        }

    def hemispheric_specialization(self) -> Dict[str, Any]:
        """
        Assess hemispheric specialization (Gazzaniga, 2000).

        The corpus callosum enables interhemispheric communication but
        also maintains hemispheric specialization. Left hemisphere
        specializes in sequential/analytic processing, right in
        holistic/spatial. The CC balances integration vs independence.

        Returns:
            Dict with lateralization_index, dominant_hemisphere, integration_quality
        """
        left_count = self._stats.left_dominant_count
        right_count = self._stats.right_dominant_count
        total = max(1, left_count + right_count)

        # Lateralization index: -1 = pure right, +1 = pure left
        lateralization = (left_count - right_count) / total

        # Dominant hemisphere
        if lateralization > 0.1:
            dominant = 'left_analytical'
        elif lateralization < -0.1:
            dominant = 'right_holistic'
        else:
            dominant = 'bilateral'

        # Integration quality: how well hemispheres cooperate
        avg_efficiency = self._stats.avg_transfer_efficiency
        avg_coordination = self._stats.avg_coordination

        integration = (avg_efficiency + avg_coordination) / 2.0

        return {
            'lateralization_index': round(lateralization, 4),
            'dominant_hemisphere': dominant,
            'integration_quality': round(integration, 4),
            'left_dominant_ratio': round(left_count / total, 4),
            'right_dominant_ratio': round(right_count / total, 4),
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'transfer_efficiency': float(self._efficiency_history[-1]) if self._efficiency_history else 0.0,
            'avg_transfer_efficiency': self._stats.avg_transfer_efficiency,
            'avg_coordination': self._stats.avg_coordination,
            'left_dominant_count': self._stats.left_dominant_count,
            'right_dominant_count': self._stats.right_dominant_count,
            'total_transfers': self._stats.total_transfers,
        }

    def get_stats(self) -> CorpusCallosumStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'efficiency_history': [round(v, 4) for v in list(self._efficiency_history)[-20:]],
            'coordination_history': [round(v, 4) for v in list(self._coordination_history)[-20:]],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self.transfer = InterhemisphericTransfer(bandwidth=self.transfer_bandwidth, signal_dim=self.signal_dim)
        self.specializer = HemisphericSpecializer(signal_dim=self.signal_dim)
        self.coordinator = BilateralCoordinator(coordination_gain=self.coordination_gain, signal_dim=self.signal_dim)
        self._efficiency_history.clear()
        self._coordination_history.clear()
        self._stats = CorpusCallosumStats()
        logger.info("CorpusCallosum reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'CorpusCallosum':
        """Construct from parsed YAML config dict."""
        cc = config.get('corpus_callosum', {})
        return cls(
            transfer_bandwidth=cc.get('transfer_bandwidth', 0.8),
            lateralization_bias=cc.get('lateralization_bias', 0.0),
            coordination_gain=cc.get('coordination_gain', 1.0),
            signal_dim=cc.get('signal_dim', 16),
        )

    def __repr__(self) -> str:
        return (f"CorpusCallosum(transfers={self._stats.total_transfers}, "
                f"efficiency={self._stats.avg_transfer_efficiency:.3f})")
