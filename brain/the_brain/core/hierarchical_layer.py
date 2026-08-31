"""
Hierarchical Layer - Base Abstract Class for 4-Layer Routing Hierarchy

Defines the interface and shared functionality for hierarchical routing layers:
    - Layer 1 (Sensory): Bottom-up attention, feature extraction
    - Layer 2 (Feature): Temporal prediction, feature binding
    - Layer 3 (Semantic): Concept-based attention, goal modulation
    - Layer 4 (Abstract): Executive control, action selection

Key Design Principles:
    - Gates ALWAYS sum to 1.0 (softmax normalized)
    - Skip connection weights clamped < 0.5 (local computation dominates)
    - Temperature decreases up hierarchy (softer at bottom, sharper at top)
    - Learning rate increases up hierarchy (slower adaptation at sensory level)

Interface:
    step(x, skip_inputs, context) -> LayerOutput
"""

import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List, Any, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels


@dataclass
class LayerConfig:
    """Configuration for a hierarchical routing layer."""
    layer_index: int               # 1-4
    temperature: float             # Softmax temperature (higher = softer)
    learning_rate: float           # Layer-specific learning rate
    output_dim: int                # Output dimension
    n_modalities: int              # Number of modalities (gate dimensions)
    skip_weight_max: float = 0.5   # Maximum skip weight (ensures local dominance)
    skip_weight_init: float = 0.1  # Initial skip weight


@dataclass
class LayerOutput:
    """Output from a hierarchical routing layer."""
    output: np.ndarray                           # Processed representation
    gates: np.ndarray                            # Gate distribution (sum to 1.0)
    layer_index: int                             # Which layer (1-4)
    temperature: float                           # Current temperature
    local_gates: np.ndarray                      # Gates before skip blending
    skip_contributions: Dict[int, np.ndarray]    # Contributions from skip inputs
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'layer_index': self.layer_index,
            'temperature': self.temperature,
            'gates': self.gates.tolist(),
            'local_gates': self.local_gates.tolist(),
            'skip_contributions': {
                k: v.tolist() for k, v in self.skip_contributions.items()
            },
            'output_norm': float(np.linalg.norm(self.output)),
            'dominant_gate': int(np.argmax(self.gates)),
            'gate_entropy': float(-np.sum(self.gates * np.log(self.gates + 1e-10)))
        }


@dataclass
class HierarchicalRoutingResult:
    """Complete result from hierarchical routing through all layers."""
    layer_outputs: Dict[int, LayerOutput]  # 1-4 -> LayerOutput
    final_gates: np.ndarray                # Weighted combination of all layers
    dominant_layer: int                    # Which layer dominated final decision
    processing_time_ms: float              # Total processing time

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'layer_outputs': {
                k: v.to_dict() for k, v in self.layer_outputs.items()
            },
            'final_gates': self.final_gates.tolist(),
            'dominant_layer': self.dominant_layer,
            'processing_time_ms': self.processing_time_ms
        }


class HierarchicalLayer(ABC):
    """
    Abstract base class for hierarchical routing layers.

    All layers must:
    1. Accept skip inputs from lower layers
    2. Compute gates that sum to 1.0
    3. Maintain learnable skip connection weights
    4. Support reset and state serialization

    Interface: step(x, skip_inputs, context) -> LayerOutput
    """

    def __init__(self, config: LayerConfig, seed: int = 42):
        """
        Initialize hierarchical layer.

        Args:
            config: LayerConfig with layer parameters
            seed: Random seed for reproducibility
        """
        self.config = config
        self.layer_index = config.layer_index
        self.temperature = config.temperature
        self.learning_rate = config.learning_rate
        self.n_modalities = config.n_modalities
        self.output_dim = config.output_dim

        # Skip connection weights: source_layer_index -> weight
        # Initialized to config.skip_weight_init, clamped to [0, skip_weight_max]
        self.skip_weights: Dict[int, float] = {}

        # Random generator
        self.rng = np.random.default_rng(seed)

        # Statistics tracking
        self.step_count = 0
        self.total_skip_contribution = 0.0

    @abstractmethod
    def step(
        self,
        x: Dict[str, np.ndarray],
        skip_inputs: Optional[Dict[int, LayerOutput]] = None,
        context: Optional[np.ndarray] = None,
        **kwargs
    ) -> LayerOutput:
        """
        Process input through this layer.

        Args:
            x: Input dict mapping modality -> vector
            skip_inputs: Dict mapping source_layer_index -> LayerOutput
            context: Optional context vector
            **kwargs: Layer-specific additional arguments

        Returns:
            LayerOutput with output, gates (sum to 1.0), and metadata
        """
        pass

    def _compute_gates_with_skips(
        self,
        local_scores: np.ndarray,
        skip_inputs: Optional[Dict[int, LayerOutput]] = None
    ) -> Tuple[np.ndarray, Dict[int, np.ndarray]]:
        """
        Compute gates incorporating skip connections.

        Critical: Gates ALWAYS sum to 1.0

        Args:
            local_scores: Relevance scores from local computation
            skip_inputs: Optional skip connection inputs

        Returns:
            Tuple of (final_gates, skip_contributions)
        """
        # Start with local relevance scores
        combined_scores = local_scores.copy()
        skip_contributions: Dict[int, np.ndarray] = {}
        total_skip_weight = 0.0

        if skip_inputs:
            for src_layer, layer_out in skip_inputs.items():
                if src_layer in self.skip_weights:
                    w = self.skip_weights[src_layer]
                    # Ensure weight <= max (local dominates)
                    w = min(w, self.config.skip_weight_max)
                    # Contribution is weighted gates from source layer
                    contribution = w * layer_out.gates
                    combined_scores += contribution
                    skip_contributions[src_layer] = contribution
                    total_skip_weight += w

        # Track statistics
        self.total_skip_contribution += total_skip_weight

        # Softmax with layer-specific temperature
        gates = self._softmax_with_temperature(combined_scores)

        return gates, skip_contributions

    def _softmax_with_temperature(self, scores: np.ndarray) -> np.ndarray:
        """
        Compute softmax with layer-specific temperature.

        Critical: Result ALWAYS sums to 1.0

        Args:
            scores: Raw relevance scores

        Returns:
            Normalized probability distribution
        """
        # Scale by temperature
        scaled = scores / max(self.temperature, 1e-6)

        # Numerical stability: subtract max
        scaled = scaled - np.max(scaled)

        # Exponential
        exp_s = np.exp(scaled)

        # Normalize
        gates = exp_s / (np.sum(exp_s) + 1e-10)

        # Verify invariant
        gate_sum = np.sum(gates)
        if not np.isclose(gate_sum, 1.0, atol=1e-6):
            # Force normalization if numerical issues
            gates = gates / gate_sum

        return gates

    def update_skip_weight(
        self,
        source_layer: int,
        delta: float,
        clip_max: Optional[float] = None
    ):
        """
        Update skip connection weight (clamped to max).

        Args:
            source_layer: Source layer index
            delta: Weight change (scaled by learning rate)
            clip_max: Maximum weight (defaults to config)
        """
        clip_max = clip_max or self.config.skip_weight_max

        if source_layer not in self.skip_weights:
            self.skip_weights[source_layer] = self.config.skip_weight_init

        self.skip_weights[source_layer] += delta * self.learning_rate
        self.skip_weights[source_layer] = np.clip(
            self.skip_weights[source_layer],
            0.0,
            clip_max
        )

    def initialize_skip_weight(self, source_layer: int, weight: float = None):
        """
        Initialize skip connection weight from a source layer.

        Args:
            source_layer: Source layer index
            weight: Initial weight (defaults to config.skip_weight_init)
        """
        weight = weight if weight is not None else self.config.skip_weight_init
        self.skip_weights[source_layer] = min(weight, self.config.skip_weight_max)

    @abstractmethod
    def reset(self):
        """Reset layer state (keep learned weights)."""
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """Get serializable layer state."""
        pass

    def get_skip_weights(self) -> Dict[int, float]:
        """Get current skip connection weights."""
        return self.skip_weights.copy()

    def get_statistics(self) -> Dict[str, Any]:
        """Get layer statistics."""
        return {
            'layer_index': self.layer_index,
            'step_count': self.step_count,
            'temperature': self.temperature,
            'learning_rate': self.learning_rate,
            'n_modalities': self.n_modalities,
            'skip_weights': self.skip_weights.copy(),
            'avg_skip_contribution': (
                self.total_skip_contribution / max(self.step_count, 1)
            )
        }


def verify_gate_invariant(gates: np.ndarray, layer_name: str = ""):
    """
    Verify that gates sum to 1.0.

    Raises AssertionError if invariant violated.

    Args:
        gates: Gate distribution to verify
        layer_name: Name for error message
    """
    gate_sum = np.sum(gates)
    assert np.isclose(gate_sum, 1.0, atol=1e-5), \
        f"{layer_name} gates must sum to 1.0, got {gate_sum}"


def compute_gate_entropy(gates: np.ndarray) -> float:
    """
    Compute entropy of gate distribution.

    Higher entropy = more uncertain/distributed.
    Lower entropy = more focused/certain.

    Args:
        gates: Gate distribution (should sum to 1.0)

    Returns:
        Entropy in nats
    """
    # Avoid log(0)
    safe_gates = gates + 1e-10
    return -np.sum(gates * np.log(safe_gates))


def blend_gates_weighted(
    layer_outputs: Dict[int, LayerOutput],
    layer_weights: Dict[int, float]
) -> np.ndarray:
    """
    Compute weighted blend of gates from multiple layers.

    Critical: Result sums to 1.0.

    Args:
        layer_outputs: Dict of layer_index -> LayerOutput
        layer_weights: Dict of layer_index -> weight

    Returns:
        Blended gate distribution (sum to 1.0)
    """
    n_modalities = None
    combined = None
    total_weight = 0.0

    for layer_idx, out in layer_outputs.items():
        if n_modalities is None:
            n_modalities = len(out.gates)
            combined = np.zeros(n_modalities)

        w = layer_weights.get(layer_idx, 0.0)
        combined += w * out.gates
        total_weight += w

    if combined is None or total_weight == 0:
        raise ValueError("No valid layer outputs to blend")

    # Normalize
    combined = combined / total_weight

    # Ensure sum to 1.0
    combined = combined / np.sum(combined)

    return combined
