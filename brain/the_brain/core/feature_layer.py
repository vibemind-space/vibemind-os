"""
Feature Layer (Layer 2) - Temporal Prediction and Feature Binding

The second layer in the hierarchical routing system.
Integrates PredictiveRouter for anticipatory gate adjustments.

Properties:
    - Temperature: 0.5 (moderate sharpness)
    - Learning rate: 0.003 (moderate adaptation)
    - Skip inputs: Optional from Layer 1
    - Core: PredictiveRouter for temporal prediction
"""

import numpy as np
from typing import Dict, Optional, Any, List, TYPE_CHECKING

from core.hierarchical_layer import (
    HierarchicalLayer,
    LayerConfig,
    LayerOutput,
    verify_gate_invariant
)
from core.predictive_router import PredictiveRouter, RoutingPrediction

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels


# Default configuration for Layer 2 (Feature)
FEATURE_LAYER_DEFAULTS = {
    'layer_index': 2,
    'temperature': 0.5,      # Moderate sharpness
    'learning_rate': 0.003,  # Moderate adaptation
    'output_dim': 128,
    'n_modalities': 6,
}


class FeatureLayer(HierarchicalLayer):
    """
    Layer 2: Feature binding and temporal prediction.

    Integrates PredictiveRouter to provide:
    - Forward models for next-state prediction
    - Anticipatory gate adjustments
    - Temporal pattern learning

    Receives optional skip input from Layer 1 (Sensory).
    Produces outputs that can skip to higher layers.
    """

    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        modalities: Optional[List[str]] = None,
        latent_dims: Optional[Dict[str, int]] = None,
        predictive_router: Optional[PredictiveRouter] = None,
        seed: int = 42,
        **router_kwargs
    ):
        """
        Initialize Feature Layer.

        Args:
            config: LayerConfig (uses FEATURE_LAYER_DEFAULTS if None)
            modalities: List of modality names
            latent_dims: Dict mapping modality -> latent dimension
            predictive_router: Pre-configured PredictiveRouter (creates new if None)
            seed: Random seed for reproducibility
            **router_kwargs: Arguments passed to PredictiveRouter if creating
        """
        # Create default config if not provided
        if config is None:
            config = LayerConfig(**FEATURE_LAYER_DEFAULTS)

        # Validate layer index
        assert config.layer_index == 2, "FeatureLayer must be layer_index=2"

        super().__init__(config, seed)

        # Default modalities if not provided
        if modalities is None:
            modalities = ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']

        if latent_dims is None:
            latent_dims = {
                'vision': 128, 'audio': 64, 'touch': 32,
                'taste': 16, 'vestibular': 16, 'threat': 8
            }

        self.modalities = modalities
        self.latent_dims = latent_dims

        # Create or use provided predictive router
        if predictive_router is not None:
            self.predictor = predictive_router
        else:
            self.predictor = PredictiveRouter(
                modalities=modalities,
                latent_dims=latent_dims,
                temperature=self.temperature,
                **router_kwargs
            )

        # Initialize skip weight from Layer 1
        self.initialize_skip_weight(1, self.config.skip_weight_init)

        # Local gate computation weights
        self.total_input_dim = sum(latent_dims.get(m, 32) for m in modalities)
        self.W_local = self.rng.normal(0, 0.1, (self.n_modalities, self.total_input_dim))

        # Last prediction for higher layers
        self.last_prediction: Optional[RoutingPrediction] = None

    def step(
        self,
        x: Dict[str, np.ndarray],
        skip_inputs: Optional[Dict[int, LayerOutput]] = None,
        context: Optional[np.ndarray] = None,
        **kwargs
    ) -> LayerOutput:
        """
        Process input through feature binding and prediction.

        Args:
            x: Dict mapping modality name -> latent vector
            skip_inputs: Optional Dict with Layer 1 output
            context: Optional context vector
            **kwargs: Additional arguments (oscillator_state, neuromod_levels)

        Returns:
            LayerOutput with gates summing to 1.0
        """
        self.step_count += 1

        # Get current latent states from input
        v_current = {}
        for m in self.modalities:
            if m in x:
                v_current[m] = x[m]
            else:
                v_current[m] = np.zeros(self.latent_dims.get(m, 32))

        # 1) Compute local relevance scores
        local_scores = self._compute_local_scores(v_current)

        # 2) Get gates from Layer 1 skip (if available)
        l1_gates = None
        if skip_inputs and 1 in skip_inputs:
            l1_gates = skip_inputs[1].gates

        # 3) Compute local gates via softmax
        local_gates = self._softmax_with_temperature(local_scores)

        # 4) Use predictive router for anticipatory adjustment
        prediction = self.predictor.step(
            v_current=v_current,
            current_gates=local_gates,
            context=context
        )
        self.last_prediction = prediction

        # Use blended gates from predictor as base
        combined_gates = prediction.blended_gates.copy()

        # 5) Incorporate skip connections
        gates, skip_contributions = self._compute_gates_with_skips(
            combined_gates,
            skip_inputs
        )

        # Verify invariant
        verify_gate_invariant(gates, "FeatureLayer")

        # 6) Compute output representation
        # Weighted combination of latent states + prediction influence
        output = self._compute_output(v_current, gates, prediction)

        return LayerOutput(
            output=output,
            gates=gates,
            layer_index=self.layer_index,
            temperature=self.temperature,
            local_gates=local_gates,
            skip_contributions=skip_contributions
        )

    def _compute_local_scores(self, v_current: Dict[str, np.ndarray]) -> np.ndarray:
        """Compute local relevance scores from current latent states."""
        # Concatenate latent vectors
        v_parts = []
        for m in self.modalities:
            dim = self.latent_dims.get(m, 32)
            v = v_current.get(m, np.zeros(dim))
            if len(v) != dim:
                v = np.zeros(dim)
            v_parts.append(v)

        v_concat = np.concatenate(v_parts)

        # Linear projection to scores
        scores = self.W_local @ v_concat

        return scores

    def _compute_output(
        self,
        v_current: Dict[str, np.ndarray],
        gates: np.ndarray,
        prediction: RoutingPrediction
    ) -> np.ndarray:
        """Compute output representation."""
        # Weighted sum of current latents
        output_parts = []
        for i, m in enumerate(self.modalities):
            v = v_current.get(m, np.zeros(self.latent_dims.get(m, 32)))
            gate = gates[i] if i < len(gates) else 0.0
            output_parts.append(gate * v)

        output = np.concatenate(output_parts)

        # Modulate by prediction confidence
        output *= (0.8 + 0.2 * prediction.confidence)

        return output

    def get_prediction_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the last prediction."""
        if self.last_prediction is None:
            return None

        return {
            'blended_gates': self.last_prediction.blended_gates.tolist(),
            'gate_deltas': self.last_prediction.gate_deltas.tolist(),
            'prediction_error': self.last_prediction.prediction_error,
            'confidence': self.last_prediction.confidence
        }

    def learn(self, v_actual: Dict[str, np.ndarray], v_input: Dict[str, np.ndarray]):
        """
        Update forward models from actual outcomes.

        Args:
            v_actual: Actual observed latent states
            v_input: Input latents used for prediction
        """
        self.predictor.learn(v_actual, v_input)

    def reset(self):
        """Reset layer state while preserving learned weights."""
        self.step_count = 0
        self.total_skip_contribution = 0.0
        self.last_prediction = None
        self.predictor.reset()

    def get_state(self) -> Dict[str, Any]:
        """Get serializable layer state."""
        return {
            'layer_index': self.layer_index,
            'temperature': self.temperature,
            'learning_rate': self.learning_rate,
            'n_modalities': self.n_modalities,
            'step_count': self.step_count,
            'modalities': list(self.modalities),
            'latent_dims': self.latent_dims,
            'skip_weights': self.skip_weights.copy(),
            'predictor_state': self.predictor.get_state(),
            'predictor_metrics': self.predictor.get_metrics()
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get layer statistics including predictor metrics."""
        base_stats = super().get_statistics()

        # Add feature-specific stats
        base_stats['modalities'] = list(self.modalities)
        base_stats['predictor_confidence'] = self.predictor.confidence
        base_stats['predictor_metrics'] = self.predictor.get_metrics()

        if self.last_prediction:
            base_stats['last_prediction_error'] = self.last_prediction.prediction_error

        return base_stats
