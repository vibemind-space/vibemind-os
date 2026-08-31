"""
Sensory Layer (Layer 1) - Bottom-up Attention and Feature Extraction

The first layer in the hierarchical routing system.
Wraps ThalamoPC6Adaptive to provide the HierarchicalLayer interface.

Properties:
    - Temperature: 1.0 (softest gates, most exploratory)
    - Learning rate: 0.001 (slowest adaptation)
    - Skip inputs: None (this is the bottom layer)
    - Core: ThalamoPC6Adaptive for multimodal thalamic routing
"""

import numpy as np
from typing import Dict, Optional, Any, TYPE_CHECKING

from core.hierarchical_layer import (
    HierarchicalLayer,
    LayerConfig,
    LayerOutput,
    verify_gate_invariant
)
from core.thalamo_pc_adaptive import ThalamoPC6Adaptive

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels


# Default configuration for Layer 1 (Sensory)
SENSORY_LAYER_DEFAULTS = {
    'layer_index': 1,
    'temperature': 1.0,      # Softest - most exploratory
    'learning_rate': 0.001,  # Slowest - stable sensory processing
    'output_dim': 128,       # Maximum modality dimension
    'n_modalities': 6,       # vision, audio, touch, taste, vestibular, threat
}


class SensoryLayer(HierarchicalLayer):
    """
    Layer 1: Sensory processing with bottom-up attention.

    Wraps ThalamoPC6Adaptive to provide:
    - Multimodal sensory integration
    - Predictive coding and error computation
    - Adaptive thalamic gating

    As the bottom layer, it does not receive skip inputs.
    It produces outputs that can skip to higher layers.
    """

    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        thalamus: Optional[ThalamoPC6Adaptive] = None,
        seed: int = 42,
        **thalamus_kwargs
    ):
        """
        Initialize Sensory Layer.

        Args:
            config: LayerConfig (uses SENSORY_LAYER_DEFAULTS if None)
            thalamus: Pre-configured ThalamoPC6Adaptive (creates new if None)
            seed: Random seed for reproducibility
            **thalamus_kwargs: Arguments passed to ThalamoPC6Adaptive if creating
        """
        # Create default config if not provided
        if config is None:
            config = LayerConfig(**SENSORY_LAYER_DEFAULTS)

        # Validate layer index
        assert config.layer_index == 1, "SensoryLayer must be layer_index=1"

        super().__init__(config, seed)

        # Create or use provided thalamus
        if thalamus is not None:
            self.thalamus = thalamus
        else:
            # Create with sensory-appropriate parameters
            self.thalamus = ThalamoPC6Adaptive(
                gate_temp=self.temperature,
                seed=seed,
                **thalamus_kwargs
            )

        # Extract modality info from thalamus
        self.modalities = self.thalamus.modalities
        self.modality_dims = {m: self.thalamus.d[m] for m in self.modalities}

        # Output dimension is sum of all modality dimensions
        self.total_output_dim = sum(self.modality_dims.values())

        # Track prediction errors for higher layers
        self.last_prediction_errors: Dict[str, float] = {}

    def step(
        self,
        x: Dict[str, np.ndarray],
        skip_inputs: Optional[Dict[int, LayerOutput]] = None,
        context: Optional[np.ndarray] = None,
        hazard: Optional[Dict[str, float]] = None,
        reward: Optional[Dict[str, float]] = None,
        adapt: bool = True,
        **kwargs
    ) -> LayerOutput:
        """
        Process sensory input through thalamic routing.

        Args:
            x: Dict mapping modality name -> input vector
            skip_inputs: Ignored (Layer 1 has no lower layers)
            context: Optional context vector for top-down modulation
            hazard: Optional hazard signals per modality
            reward: Optional reward signals per modality
            adapt: Whether to perform online adaptation
            **kwargs: Additional arguments (oscillator_state, neuromod_levels)

        Returns:
            LayerOutput with gates summing to 1.0
        """
        self.step_count += 1

        # Convert context to M-dim if needed
        ctx = None
        if context is not None:
            if len(context) == self.n_modalities:
                ctx = context
            else:
                # Project context to modality dimension
                ctx = context[:self.n_modalities] if len(context) > self.n_modalities else None

        # Call thalamus step
        thalamus_out = self.thalamus.step(
            x=x,
            ctx=ctx,
            hazard=hazard,
            reward=reward,
            adapt=adapt
        )

        # Extract gates (already normalized by thalamus)
        gates = thalamus_out['g']

        # Verify gate invariant
        verify_gate_invariant(gates, "SensoryLayer")

        # Store prediction errors for higher layers
        self.last_prediction_errors = {
            m: self.thalamus.PE[m] for m in self.modalities
        }

        # Construct combined output representation
        # Concatenate all modality latent vectors weighted by gates
        output_parts = []
        for i, m in enumerate(self.modalities):
            v_m = thalamus_out['v_next'][m]
            weighted_v = gates[i] * v_m
            output_parts.append(weighted_v)

        # Concatenate to form output vector
        output = np.concatenate(output_parts)

        # Layer 1 has no skip contributions (no lower layers)
        skip_contributions: Dict[int, np.ndarray] = {}

        return LayerOutput(
            output=output,
            gates=gates,
            layer_index=self.layer_index,
            temperature=self.temperature,
            local_gates=gates.copy(),  # No skip blending at L1
            skip_contributions=skip_contributions
        )

    def get_prediction_errors(self) -> Dict[str, float]:
        """Get the last computed prediction errors per modality."""
        return self.last_prediction_errors.copy()

    def get_modality_outputs(self) -> Dict[str, np.ndarray]:
        """Get the current latent vectors per modality."""
        return {m: self.thalamus.v[m].copy() for m in self.modalities}

    def apply_top_down_feedback(
        self,
        prior_delta: np.ndarray,
        trn_delta: np.ndarray,
        gain: float = 1.0
    ) -> Dict[str, Any]:
        """
        Apply top-down feedback from higher layers.

        This allows Layer 3/4 to modulate sensory processing.

        Args:
            prior_delta: Modality prior adjustments
            trn_delta: TRN inhibition adjustments
            gain: Activity gain (arousal modulation)

        Returns:
            Dict of applied changes
        """
        return self.thalamus.apply_feedback(prior_delta, trn_delta, gain)

    def reset(self):
        """Reset layer state while preserving learned weights."""
        self.step_count = 0
        self.total_skip_contribution = 0.0
        self.last_prediction_errors = {}

        # Reset thalamus state (v = latent vectors, PE = prediction errors)
        for m in self.modalities:
            self.thalamus.v[m] = np.zeros_like(self.thalamus.v[m])
            self.thalamus.PE[m] = 0.0

    def get_state(self) -> Dict[str, Any]:
        """Get serializable layer state."""
        return {
            'layer_index': self.layer_index,
            'temperature': self.temperature,
            'learning_rate': self.learning_rate,
            'n_modalities': self.n_modalities,
            'step_count': self.step_count,
            'modalities': list(self.modalities),
            'modality_dims': self.modality_dims,
            'skip_weights': self.skip_weights.copy(),
            'last_prediction_errors': self.last_prediction_errors.copy(),
            'thalamus_state': self.thalamus.get_adaptive_state()
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get layer statistics including thalamus metrics."""
        base_stats = super().get_statistics()

        # Add sensory-specific stats
        base_stats['modalities'] = list(self.modalities)
        base_stats['modality_dims'] = self.modality_dims
        base_stats['total_output_dim'] = self.total_output_dim
        base_stats['last_gate_entropy'] = float(
            -np.sum(self.thalamus.last_g * np.log(self.thalamus.last_g + 1e-10))
        )
        base_stats['thalamus_gate_temp'] = self.thalamus.gate_temp

        return base_stats
