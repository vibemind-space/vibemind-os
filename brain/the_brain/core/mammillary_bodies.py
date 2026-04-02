"""
Mammillary Bodies Module

Neuroscience basis:
  The mammillary bodies are a pair of small, round nuclei in the posterior
  hypothalamus. They serve as a critical relay station in the Papez circuit
  (Papez, 1937): Hippocampus -> Mammillary Bodies -> Anterior Thalamus ->
  Cingulate Cortex -> Hippocampus. Lesion studies show that damage to the
  mammillary bodies produces severe anterograde amnesia comparable to
  hippocampal damage (Vann & Aggleton, 2004).

Key functions modeled here:
  1. Memory relay: Hippocampal signals are transformed and relayed to the
     anterior thalamus with emotional gain modulation (amygdala input).
  2. Spatial memory: Head direction cells in the lateral mammillary nucleus
     encode facing direction; the medial nucleus integrates spatial context.
  3. Episodic consolidation: Importance- and recency-weighted strengthening
     of memory traces during offline periods.
  4. Head direction processing: Angular velocity integration and predictive
     direction estimation.

References:
  - Papez, J.W. (1937). A proposed mechanism of emotion.
  - Vann, S.D. & Aggleton, J.P. (2004). The mammillary bodies: two memory
    systems in one? Nature Reviews Neuroscience, 5(1), 35-44.
  - Taube, J.S. (2007). The head direction signal: origins and
    sensory-motor integration.
"""

import math
import logging
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger('brain.mammillary_bodies')


# ─── Stats Dataclass ──────────────────────────────────────────────────────

@dataclass
class MammillaryBodiesStats:
    """Aggregate statistics for the mammillary bodies module."""
    total_relays: int = 0
    avg_relay_strength: float = 0.0
    consolidations_triggered: int = 0
    avg_spatial_novelty: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_relays': self.total_relays,
            'avg_relay_strength': round(self.avg_relay_strength, 4),
            'consolidations_triggered': self.consolidations_triggered,
            'avg_spatial_novelty': round(self.avg_spatial_novelty, 4),
        }


# ─── Papez Circuit Relay ─────────────────────────────────────────────────

class PapezCircuitRelay:
    """
    Relays memory signals through the Papez circuit.

    Receives hippocampal output, applies a learnable linear projection
    with tanh nonlinearity, and modulates the result by emotional arousal
    (amygdala input). The relayed signal is directed toward the anterior
    thalamus representation.
    """

    def __init__(self, relay_dim: int = 16, emotional_gain: float = 1.0):
        self.relay_dim = relay_dim
        self.emotional_gain = emotional_gain
        # Learnable projection weights (initialized with small random values)
        rng = np.random.default_rng(42)
        self._weights = rng.normal(0.0, 0.1, (relay_dim, relay_dim))
        self._bias = np.zeros(relay_dim)
        self._relay_history: deque = deque(maxlen=200)

    def relay(self, hippocampal_signal: np.ndarray,
              context: Dict[str, float]) -> Dict[str, Any]:
        """
        Transform and relay a hippocampal signal.

        Args:
            hippocampal_signal: Signal from the hippocampus (length relay_dim).
            context: Dict with optional 'emotional_arousal' (0-1) key.

        Returns:
            Dict with relayed_signal, relay_strength, emotional_modulation.
        """
        sig = np.asarray(hippocampal_signal, dtype=np.float64).flatten()
        if sig.shape[0] != self.relay_dim:
            sig = np.resize(sig, self.relay_dim)

        # Linear projection + tanh nonlinearity
        projected = np.tanh(self._weights @ sig + self._bias)

        # Emotional gain modulation
        arousal = float(context.get('emotional_arousal', 0.5))
        arousal = max(0.0, min(1.0, arousal))
        modulation = 1.0 + (arousal - 0.5) * self.emotional_gain
        relayed = projected * modulation

        strength = float(np.linalg.norm(relayed))
        self._relay_history.append(strength)

        return {
            'relayed_signal': relayed,
            'relay_strength': strength,
            'emotional_modulation': round(modulation, 4),
        }

    def get_avg_strength(self) -> float:
        if not self._relay_history:
            return 0.0
        return float(np.mean(list(self._relay_history)))


# ─── Spatial Memory Processor ────────────────────────────────────────────

class SpatialMemoryProcessor:
    """
    Processes spatial information, integrating head direction signals
    and maintaining a buffer of recent positions for novelty detection.
    """

    def __init__(self, spatial_dim: int = 8, buffer_size: int = 200):
        self.spatial_dim = spatial_dim
        self._position_buffer: deque = deque(maxlen=buffer_size)
        self._novelty_history: deque = deque(maxlen=200)

    def process_spatial(self, head_direction: float,
                        position_signal: np.ndarray) -> Dict[str, Any]:
        """
        Process a spatial snapshot.

        Args:
            head_direction: Current facing direction in degrees (0-360).
            position_signal: Spatial position encoding (length spatial_dim).

        Returns:
            Dict with spatial_code, head_direction_stable, position_certainty.
        """
        pos = np.asarray(position_signal, dtype=np.float64).flatten()
        if pos.shape[0] != self.spatial_dim:
            pos = np.resize(pos, self.spatial_dim)

        # Normalise head direction to [0, 360)
        hd = head_direction % 360.0

        # Encode head direction as sin/cos pair appended to position
        hd_rad = math.radians(hd)
        hd_vec = np.array([math.sin(hd_rad), math.cos(hd_rad)])
        spatial_code = np.concatenate([pos, hd_vec])

        # Stability: compare to recent buffer
        head_direction_stable = True
        if len(self._position_buffer) >= 2:
            recent = list(self._position_buffer)[-1]
            recent_hd = recent[-2:]
            delta = np.linalg.norm(hd_vec - recent_hd)
            head_direction_stable = delta < 0.3

        # Position certainty from signal magnitude
        position_certainty = float(np.clip(np.linalg.norm(pos) / self.spatial_dim, 0.0, 1.0))

        # Novelty detection
        novelty = self._compute_novelty(pos)
        self._novelty_history.append(novelty)
        self._position_buffer.append(spatial_code.copy())

        return {
            'spatial_code': spatial_code,
            'head_direction_stable': head_direction_stable,
            'position_certainty': round(position_certainty, 4),
            'spatial_novelty': round(novelty, 4),
        }

    def _compute_novelty(self, position: np.ndarray) -> float:
        """Novelty = minimum distance to any buffered position."""
        if not self._position_buffer:
            return 1.0
        positions = np.array([p[:self.spatial_dim] for p in self._position_buffer])
        dists = np.linalg.norm(positions - position, axis=1)
        min_dist = float(np.min(dists))
        # Sigmoid-like mapping: 0 = familiar, 1 = novel
        return float(1.0 - math.exp(-min_dist))

    def get_avg_novelty(self) -> float:
        if not self._novelty_history:
            return 0.0
        return float(np.mean(list(self._novelty_history)))


# ─── Episodic Memory Consolidator ────────────────────────────────────────

class EpisodicMemoryConsolidator:
    """
    Importance- and recency-weighted consolidation of memory traces.

    Stronger and more recent memories receive higher consolidation
    priority, analogous to the mammillary bodies' role in offline
    memory replay selection.
    """

    def __init__(self, consolidation_threshold: float = 0.5):
        self.consolidation_threshold = consolidation_threshold
        self._consolidation_count: int = 0

    def consolidate(self, memory_trace: np.ndarray,
                    importance: float,
                    recency: float) -> Dict[str, Any]:
        """
        Evaluate a memory trace for consolidation.

        Args:
            memory_trace: The memory vector to evaluate.
            importance: How important this memory is (0-1).
            recency: How recent this memory is (0-1, 1 = just formed).

        Returns:
            Dict with consolidation_strength, should_strengthen, replay_priority.
        """
        importance = max(0.0, min(1.0, importance))
        recency = max(0.0, min(1.0, recency))

        trace = np.asarray(memory_trace, dtype=np.float64).flatten()
        trace_magnitude = float(np.linalg.norm(trace))

        # Consolidation strength: weighted combination
        consolidation_strength = (
            0.5 * importance +
            0.3 * recency +
            0.2 * min(trace_magnitude, 1.0)
        )

        should_strengthen = consolidation_strength >= self.consolidation_threshold
        if should_strengthen:
            self._consolidation_count += 1

        # Replay priority: importance dominates, recency breaks ties
        replay_priority = importance * 0.7 + recency * 0.3

        return {
            'consolidation_strength': round(consolidation_strength, 4),
            'should_strengthen': should_strengthen,
            'replay_priority': round(replay_priority, 4),
        }


# ─── Head Direction Relay ────────────────────────────────────────────────

class HeadDirectionRelay:
    """
    Processes and relays head direction information.

    Maintains a running estimate of head direction and uses angular
    velocity to predict future facing direction, mirroring the
    anticipatory firing of head direction cells in the lateral
    mammillary nucleus (Taube, 2007).
    """

    def __init__(self):
        self._current_estimate: float = 0.0
        self._smoothing: float = 0.7  # Exponential smoothing factor

    def process_direction(self, current_direction: float,
                          angular_velocity: float) -> Dict[str, float]:
        """
        Update head direction estimate and predict future direction.

        Args:
            current_direction: Observed direction in degrees (0-360).
            angular_velocity: Rate of turn in degrees per time step.

        Returns:
            Dict with estimated_direction, predicted_direction,
            direction_confidence.
        """
        current_direction = current_direction % 360.0

        # Exponential smoothing of direction estimate
        # Handle wrap-around via angular difference
        diff = (current_direction - self._current_estimate + 180.0) % 360.0 - 180.0
        self._current_estimate = (self._current_estimate + (1.0 - self._smoothing) * diff) % 360.0

        # Predict future direction
        predicted = (self._current_estimate + angular_velocity) % 360.0

        # Confidence based on agreement between estimate and observation
        angular_error = abs(diff)
        confidence = max(0.0, 1.0 - angular_error / 180.0)

        return {
            'estimated_direction': round(self._current_estimate, 2),
            'predicted_direction': round(predicted, 2),
            'direction_confidence': round(confidence, 4),
        }


# ─── Main Class: Mammillary Bodies ────────────────────────────────────────

class MammillaryBodies:
    """
    Complete mammillary bodies module.

    Integrates Papez circuit relay, spatial memory processing, episodic
    memory consolidation, and head direction relay into a unified
    processing interface.
    """

    def __init__(
        self,
        relay_dim: int = 16,
        spatial_dim: int = 8,
        consolidation_threshold: float = 0.5,
        emotional_gain: float = 1.0,
    ):
        self.relay_dim = relay_dim
        self.spatial_dim = spatial_dim

        self._papez_relay = PapezCircuitRelay(relay_dim=relay_dim,
                                              emotional_gain=emotional_gain)
        self._spatial_processor = SpatialMemoryProcessor(spatial_dim=spatial_dim)
        self._consolidator = EpisodicMemoryConsolidator(
            consolidation_threshold=consolidation_threshold)
        self._head_direction = HeadDirectionRelay()

        self._total_relays: int = 0
        logger.info("MammillaryBodies initialised (relay_dim=%d, spatial_dim=%d)",
                     relay_dim, spatial_dim)

    def process(
        self,
        hippocampal_signal: np.ndarray,
        head_direction: float = 0.0,
        position_signal: Optional[np.ndarray] = None,
        memory_trace: Optional[np.ndarray] = None,
        importance: float = 0.5,
        emotional_arousal: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Run a full processing cycle through the mammillary bodies.

        Args:
            hippocampal_signal: Input from hippocampus (length relay_dim).
            head_direction: Current facing direction in degrees.
            position_signal: Spatial position vector (length spatial_dim).
            memory_trace: Memory vector for consolidation evaluation.
            importance: Importance weight for consolidation (0-1).
            emotional_arousal: Amygdala arousal level (0-1).

        Returns:
            Dict with relayed_signal, spatial_code, consolidation_strength,
            head_direction_estimate, relay_strength.
        """
        self._total_relays += 1

        # 1. Papez circuit relay
        relay_result = self._papez_relay.relay(
            hippocampal_signal,
            context={'emotional_arousal': emotional_arousal},
        )

        # 2. Spatial memory
        if position_signal is None:
            position_signal = np.zeros(self.spatial_dim)
        spatial_result = self._spatial_processor.process_spatial(
            head_direction, position_signal)

        # 3. Episodic consolidation
        if memory_trace is None:
            memory_trace = hippocampal_signal
        recency = max(0.0, min(1.0, 1.0 - (self._total_relays / 1000.0)))
        consol_result = self._consolidator.consolidate(
            memory_trace, importance, recency)

        # 4. Head direction relay
        hd_result = self._head_direction.process_direction(
            head_direction, angular_velocity=0.0)

        return {
            'relayed_signal': relay_result['relayed_signal'],
            'spatial_code': spatial_result['spatial_code'],
            'consolidation_strength': consol_result['consolidation_strength'],
            'head_direction_estimate': hd_result['estimated_direction'],
            'relay_strength': relay_result['relay_strength'],
        }

    def papez_circuit_integrity(self) -> Dict[str, float]:
        """
        Assess Papez circuit integrity for emotional memory (Papez, 1937).

        The mammillary bodies are a critical relay in the Papez circuit:
        Hippocampus -> Fornix -> MB -> Mammillothalamic tract -> Anterior
        Thalamus -> Cingulate -> Hippocampus. Damage causes anterograde
        amnesia (Korsakoff syndrome).

        Returns:
            Dict with circuit_integrity, relay_efficiency, memory_throughput
        """
        avg_strength = self._papez_relay.get_avg_strength()
        consolidations = self._consolidator._consolidation_count
        total_relays = max(1, self._total_relays)

        relay_efficiency = avg_strength
        memory_throughput = min(1.0, consolidations / total_relays) if total_relays > 10 else 0.5
        integrity = relay_efficiency * 0.6 + memory_throughput * 0.4

        return {
            'circuit_integrity': round(integrity, 4),
            'relay_efficiency': round(relay_efficiency, 4),
            'memory_throughput': round(memory_throughput, 4),
            'total_relays': total_relays,
        }

    def get_state(self) -> Dict[str, Any]:
        """Return current internal state for monitoring."""
        return {
            'total_relays': self._total_relays,
            'avg_relay_strength': self._papez_relay.get_avg_strength(),
            'consolidations_triggered': self._consolidator._consolidation_count,
            'avg_spatial_novelty': self._spatial_processor.get_avg_novelty(),
            'head_direction_estimate': self._head_direction._current_estimate,
        }

    def get_stats(self) -> MammillaryBodiesStats:
        """Return aggregate stats as a dataclass."""
        return MammillaryBodiesStats(
            total_relays=self._total_relays,
            avg_relay_strength=self._papez_relay.get_avg_strength(),
            consolidations_triggered=self._consolidator._consolidation_count,
            avg_spatial_novelty=self._spatial_processor.get_avg_novelty(),
        )

    def reset(self) -> None:
        """Reset all internal state."""
        self._papez_relay._relay_history.clear()
        self._spatial_processor._position_buffer.clear()
        self._spatial_processor._novelty_history.clear()
        self._consolidator._consolidation_count = 0
        self._head_direction._current_estimate = 0.0
        self._total_relays = 0
        logger.info("MammillaryBodies reset")

    def to_dict(self) -> Dict[str, Any]:
        """Serialise state for persistence."""
        return {
            'total_relays': self._total_relays,
            'stats': self.get_stats().to_dict(),
            'head_direction_estimate': self._head_direction._current_estimate,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'MammillaryBodies':
        """Construct from YAML configuration dict."""
        section = config.get('mammillary_bodies', {})
        return cls(
            relay_dim=section.get('relay_dim', 16),
            spatial_dim=section.get('spatial_dim', 8),
            consolidation_threshold=section.get('consolidation_threshold', 0.5),
            emotional_gain=section.get('emotional_gain', 1.0),
        )
