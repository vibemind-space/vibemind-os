"""
Superior Colliculus Module - Neuroscience Architecture Extension Phase B3

Computational model of the superior colliculus for attention orienting,
multisensory integration, and rapid response generation.

Neuroscience basis:
- Superficial layers: Visual saliency map (retinotopic)
- Deep layers: Multisensory integration + motor commands
- Orienting response: Rapid attention shifts to novel stimuli
- Inhibition of return (IOR): Prevents re-attending already-checked locations
- Sprague effect: SC lesion lifts contralateral neglect

Key references:
- "Primate superior colliculus: abstract higher-order cognition" (PubMed)
- Stein & Meredith (1993): The merging of the senses
- Posner & Cohen (1984): Inhibition of return

Integration points:
- Input: Visual data (via Thalamus/V1), audio, somatosensory
- Output: Orienting commands to Thalamus (attention shift)
- Wiring: Before ATTEND phase in cognitive_loop.py
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.superior_colliculus')


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class OrientingCommand:
    """Command to orient attention to a location/feature."""
    target_location: int  # Index in the saliency map
    urgency: float = 0.5
    source: str = "visual"  # which modality triggered it
    timestamp: float = field(default_factory=time.time)


@dataclass
class SCStats:
    """Superior colliculus statistics."""
    total_orientations: int = 0
    total_integrations: int = 0
    inhibitions_of_return: int = 0
    current_target: int = -1
    avg_saliency: float = 0.0
    multisensory_enhancement: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_orientations': self.total_orientations,
            'total_integrations': self.total_integrations,
            'inhibitions_of_return': self.inhibitions_of_return,
            'current_target': self.current_target,
            'avg_saliency': round(self.avg_saliency, 3),
            'multisensory_enhancement': round(self.multisensory_enhancement, 3),
        }


# ─── Visual Saliency Map (Superficial Layers) ─────────────────────────────────

class VisualSaliencyMap:
    """
    Topographic saliency map in the superficial layers.

    Each position represents a region in the visual/attentional field.
    The most salient position drives the orienting response.
    """

    def __init__(self, map_size: int = 16, decay_rate: float = 0.1):
        self.map_size = map_size
        self.decay_rate = decay_rate
        self._saliency = np.zeros(map_size, dtype=np.float32)

    def update(self, visual_input: np.ndarray) -> np.ndarray:
        """
        Update saliency map from visual input.

        Args:
            visual_input: Raw visual features [map_size]

        Returns:
            Updated saliency map
        """
        v = np.asarray(visual_input, dtype=np.float32).flatten()
        padded = np.zeros(self.map_size, dtype=np.float32)
        n = min(len(v), self.map_size)
        padded[:n] = np.abs(v[:n])

        # Decay old saliency, add new
        self._saliency = (1 - self.decay_rate) * self._saliency + self.decay_rate * padded

        return self._saliency.copy()

    def get_peak(self) -> Tuple[int, float]:
        """Return position and value of peak saliency."""
        idx = int(np.argmax(self._saliency))
        return idx, float(self._saliency[idx])

    def suppress_location(self, location: int, amount: float = 0.5):
        """Suppress saliency at a location (for IOR)."""
        if 0 <= location < self.map_size:
            self._saliency[location] *= (1 - amount)

    def get_map(self) -> np.ndarray:
        return self._saliency.copy()

    def to_dict(self) -> Dict[str, Any]:
        peak_idx, peak_val = self.get_peak()
        return {
            'map_size': self.map_size,
            'peak_location': peak_idx,
            'peak_saliency': round(peak_val, 3),
            'mean_saliency': round(float(self._saliency.mean()), 3),
        }


# ─── Multisensory Integrator (Deep Layers) ────────────────────────────────────

class MultisensoryIntegrator:
    """
    Deep-layer multisensory integration.

    Stein & Meredith (1993): SC neurons show multisensory enhancement
    when visual, auditory, and somatosensory signals are spatially
    and temporally aligned.

    Principle of inverse effectiveness: Weak unimodal stimuli benefit
    most from multisensory integration.
    """

    def __init__(self, modality_weights: Optional[List[float]] = None):
        # Default weights: visual 0.5, auditory 0.3, somatosensory 0.2
        if modality_weights:
            self._weights = np.array(modality_weights, dtype=np.float32)
        else:
            self._weights = np.array([0.5, 0.3, 0.2], dtype=np.float32)
        self._weights /= self._weights.sum()
        self.n_modalities = len(self._weights)
        self._enhancement_history = deque(maxlen=50)

    def integrate(
        self,
        modality_signals: Dict[str, np.ndarray],
        map_size: int = 16
    ) -> Tuple[np.ndarray, float]:
        """
        Integrate signals from multiple modalities.

        Args:
            modality_signals: Dict of modality_name -> signal_array
            map_size: Size of the output spatial map

        Returns:
            (integrated_map, multisensory_enhancement)
        """
        integrated = np.zeros(map_size, dtype=np.float32)
        unimodal_peaks = []

        for i, (name, signal) in enumerate(modality_signals.items()):
            s = np.asarray(signal, dtype=np.float32).flatten()
            padded = np.zeros(map_size, dtype=np.float32)
            n = min(len(s), map_size)
            padded[:n] = np.abs(s[:n])

            w = self._weights[i] if i < self.n_modalities else 1.0 / (i + 1)
            integrated += w * padded
            unimodal_peaks.append(float(padded.max()))

        # Multisensory enhancement: super-additive when signals align
        if len(unimodal_peaks) > 1:
            # Inverse effectiveness: weaker signals get more enhancement
            min_peak = min(unimodal_peaks) if unimodal_peaks else 0.0
            enhancement = 1.0 + 0.5 * (1.0 - min_peak)  # Stronger boost for weak signals
            integrated *= enhancement
            enhancement_val = enhancement - 1.0
        else:
            enhancement_val = 0.0

        self._enhancement_history.append(enhancement_val)
        return integrated, enhancement_val

    def get_avg_enhancement(self) -> float:
        if not self._enhancement_history:
            return 0.0
        return float(np.mean(list(self._enhancement_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_modalities': self.n_modalities,
            'weights': self._weights.tolist(),
            'avg_enhancement': self.get_avg_enhancement(),
        }


# ─── Orienting Response ───────────────────────────────────────────────────────

class OrientingResponse:
    """
    Generates rapid orienting commands.

    The SC drives reflexive and voluntary saccades/attention shifts
    toward salient locations.
    """

    def __init__(self, threshold: float = 0.3, speed: float = 50.0):
        self.threshold = threshold
        self.speed = speed  # Conceptual response speed (ms)
        self._current_target = -1
        self._orientation_count = 0

    def orient(self, saliency_map: np.ndarray) -> Optional[OrientingCommand]:
        """
        Generate orienting command if saliency exceeds threshold.

        Args:
            saliency_map: Current saliency across locations

        Returns:
            OrientingCommand or None if no orientation needed
        """
        peak_idx = int(np.argmax(saliency_map))
        peak_val = float(saliency_map[peak_idx])

        if peak_val > self.threshold and peak_idx != self._current_target:
            self._current_target = peak_idx
            self._orientation_count += 1
            return OrientingCommand(
                target_location=peak_idx,
                urgency=peak_val,
                source="multisensory",
            )
        return None

    @property
    def current_target(self) -> int:
        return self._current_target

    @property
    def orientation_count(self) -> int:
        return self._orientation_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'current_target': self._current_target,
            'threshold': self.threshold,
            'orientations': self._orientation_count,
        }


# ─── Inhibition of Return ─────────────────────────────────────────────────────

class InhibitionOfReturn:
    """
    Inhibition of Return (IOR) mechanism.

    Posner & Cohen (1984): After attention is withdrawn from a location,
    there is a temporary suppression of return to that location.
    This promotes exploration of novel locations.
    """

    def __init__(self, decay_rate: float = 0.05, max_suppression: float = 0.8):
        self.decay_rate = decay_rate
        self.max_suppression = max_suppression
        self._suppression_map: Dict[int, float] = {}
        self._ior_count = 0

    def apply_ior(self, location: int):
        """Mark a location for inhibition of return."""
        self._suppression_map[location] = self.max_suppression
        self._ior_count += 1

    def get_suppression(self, location: int) -> float:
        """Get current suppression at a location."""
        return self._suppression_map.get(location, 0.0)

    def decay(self):
        """Decay all suppressions."""
        to_remove = []
        for loc in self._suppression_map:
            self._suppression_map[loc] -= self.decay_rate
            if self._suppression_map[loc] <= 0.01:
                to_remove.append(loc)
        for loc in to_remove:
            del self._suppression_map[loc]

    def apply_to_map(self, saliency_map: np.ndarray) -> np.ndarray:
        """Apply IOR suppression to a saliency map."""
        result = saliency_map.copy()
        for loc, suppression in self._suppression_map.items():
            if 0 <= loc < len(result):
                result[loc] *= (1 - suppression)
        return result

    @property
    def ior_count(self) -> int:
        return self._ior_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'active_suppressions': len(self._suppression_map),
            'ior_count': self._ior_count,
        }


# ─── Main Superior Colliculus Module ───────────────────────────────────────────

class SuperiorColliculus:
    """
    Complete superior colliculus module.

    Functions:
    1. Visual saliency mapping (superficial layers)
    2. Multisensory integration (deep layers)
    3. Rapid orienting response
    4. Inhibition of return (exploration promotion)
    """

    def __init__(
        self,
        map_size: int = 16,
        orientation_threshold: float = 0.3,
        orientation_speed: float = 50.0,
        ior_decay_rate: float = 0.05,
        multisensory_weights: Optional[List[float]] = None,
    ):
        self.map_size = map_size

        self.saliency_map = VisualSaliencyMap(map_size)
        self.integrator = MultisensoryIntegrator(multisensory_weights)
        self.orienting = OrientingResponse(orientation_threshold, orientation_speed)
        self.ior = InhibitionOfReturn(ior_decay_rate)

        self._stats = SCStats()
        self._saliency_history = deque(maxlen=100)

    def process(
        self,
        visual: Optional[np.ndarray] = None,
        auditory: Optional[np.ndarray] = None,
        somatosensory: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Full SC processing cycle.

        1. Update visual saliency map
        2. Integrate multisensory signals
        3. Apply inhibition of return
        4. Generate orienting command if warranted

        Args:
            visual: Visual input features
            auditory: Auditory input features
            somatosensory: Somatosensory input features

        Returns:
            Dict with saliency map, orienting command, etc.
        """
        # 1. Update visual saliency
        if visual is not None:
            self.saliency_map.update(visual)

        # 2. Multisensory integration
        modalities = {}
        if visual is not None:
            modalities['visual'] = visual
        if auditory is not None:
            modalities['auditory'] = auditory
        if somatosensory is not None:
            modalities['somatosensory'] = somatosensory

        if modalities:
            integrated, enhancement = self.integrator.integrate(modalities, self.map_size)
            self._stats.total_integrations += 1
            self._stats.multisensory_enhancement = enhancement
        else:
            integrated = self.saliency_map.get_map()
            enhancement = 0.0

        # 3. Apply IOR
        self.ior.decay()
        ior_adjusted = self.ior.apply_to_map(integrated)

        # 4. Generate orienting command
        command = self.orienting.orient(ior_adjusted)
        if command:
            self._stats.total_orientations += 1
            self._stats.current_target = command.target_location
            # Apply IOR to the oriented location
            self.ior.apply_ior(command.target_location)
            self._stats.inhibitions_of_return = self.ior.ior_count

        # Track average saliency
        avg_sal = float(ior_adjusted.mean())
        self._saliency_history.append(avg_sal)
        self._stats.avg_saliency = float(np.mean(list(self._saliency_history)))

        return {
            'saliency_map': ior_adjusted,
            'orienting_command': command,
            'peak_location': int(np.argmax(ior_adjusted)),
            'peak_saliency': float(ior_adjusted.max()),
            'multisensory_enhancement': enhancement,
            'ior_active': len(self.ior._suppression_map),
        }

    def get_attention_target(self) -> int:
        """Return current attention target location."""
        return self.orienting.current_target

    def multisensory_enhancement(
        self,
        visual_strength: float,
        auditory_strength: float,
        spatial_alignment: float = 1.0,
    ) -> Dict[str, float]:
        """
        Multisensory enhancement/depression (Stein & Meredith, 1993).

        SC neurons show superadditive responses when cross-modal stimuli
        are spatially and temporally aligned. Weak unimodal signals can
        produce strong responses when combined (inverse effectiveness).

        Args:
            visual_strength: Visual signal strength [0, 1]
            auditory_strength: Auditory signal strength [0, 1]
            spatial_alignment: How spatially aligned the signals are [0, 1]

        Returns:
            Dict with enhanced_response, enhancement_ratio, is_superadditive
        """
        # Unimodal sum
        linear_sum = visual_strength + auditory_strength

        # Inverse effectiveness: weaker signals get more enhancement
        weakness = max(0.0, 1.0 - max(visual_strength, auditory_strength))
        enhancement_factor = 1.0 + weakness * spatial_alignment * 1.5

        # Multisensory response (superadditive when aligned)
        if spatial_alignment > 0.5:
            enhanced = linear_sum * enhancement_factor
        else:
            # Spatial misalignment -> depression
            enhanced = linear_sum * (0.5 + spatial_alignment)

        enhanced = min(2.0, max(0.0, enhanced))
        ratio = enhanced / max(0.01, linear_sum)

        return {
            'enhanced_response': round(enhanced, 4),
            'linear_sum': round(linear_sum, 4),
            'enhancement_ratio': round(ratio, 4),
            'is_superadditive': ratio > 1.1,
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'saliency': self.saliency_map.to_dict(),
            'integrator': self.integrator.to_dict(),
            'orienting': self.orienting.to_dict(),
            'ior': self.ior.to_dict(),
        }

    def get_stats(self) -> SCStats:
        return self._stats

    def reset(self):
        self._stats = SCStats()
        self.saliency_map._saliency[:] = 0.0
        self.ior._suppression_map.clear()
        self._saliency_history.clear()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'SuperiorColliculus':
        """
        Expected config:
            superior_colliculus:
              orientation_speed: 50
              inhibition_of_return: 500
              multisensory_weight: [0.5, 0.3, 0.2]
        """
        sc = config.get('superior_colliculus', {})
        weights = sc.get('multisensory_weight', None)
        ior_ms = sc.get('inhibition_of_return', 500)
        ior_decay = 1.0 / max(1, ior_ms / 50.0)  # Convert ms to decay rate

        return cls(
            map_size=sc.get('map_size', 16),
            orientation_threshold=sc.get('orientation_threshold', 0.3),
            orientation_speed=sc.get('orientation_speed', 50.0),
            ior_decay_rate=ior_decay,
            multisensory_weights=weights,
        )
