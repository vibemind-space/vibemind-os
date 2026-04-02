"""
Semantic Layer (Layer 3) - Concept-based Attention and Goal Modulation

The third layer in the hierarchical routing system.
Integrates CorticalProcessor for top-down attention control.

Properties:
    - Temperature: 0.3 (sharper gates, more focused)
    - Learning rate: 0.005 (moderate-fast adaptation)
    - Skip inputs: Required from Layer 1, optional from Layer 2
    - Core: CorticalProcessor for cortical feedback and attention
"""

import numpy as np
from typing import Dict, Optional, Any, List, TYPE_CHECKING

from core.hierarchical_layer import (
    HierarchicalLayer,
    LayerConfig,
    LayerOutput,
    verify_gate_invariant
)
from core.cortical_feedback import CorticalProcessor, CorticalFeedback

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels


# Default configuration for Layer 3 (Semantic)
SEMANTIC_LAYER_DEFAULTS = {
    'layer_index': 3,
    'temperature': 0.3,      # Sharper - more focused attention
    'learning_rate': 0.005,  # Moderate-fast adaptation
    'output_dim': 128,
    'n_modalities': 6,
}


class SemanticLayer(HierarchicalLayer):
    """
    Layer 3: Concept-based attention and goal modulation.

    Integrates CorticalProcessor to provide:
    - Top-down attention control based on goals
    - Expectation-driven processing
    - Cortical feedback for thalamic modulation

    Receives required skip input from Layer 1 (Sensory).
    Produces outputs that can skip to Layer 4.
    """

    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        n_modalities: int = 6,
        goal_dim: int = 32,
        state_dim: int = 128,
        modalities: Optional[List[str]] = None,
        modality_dims: Optional[Dict[str, int]] = None,
        cortical_processor: Optional[CorticalProcessor] = None,
        seed: int = 42,
        **processor_kwargs
    ):
        """
        Initialize Semantic Layer.

        Args:
            config: LayerConfig (uses SEMANTIC_LAYER_DEFAULTS if None)
            n_modalities: Number of modalities
            goal_dim: Dimension of goal/task encoding
            state_dim: Total state dimension
            modalities: List of modality names
            modality_dims: Dict mapping modality -> dimension
            cortical_processor: Pre-configured CorticalProcessor (creates new if None)
            seed: Random seed for reproducibility
            **processor_kwargs: Arguments passed to CorticalProcessor if creating
        """
        # Create default config if not provided
        if config is None:
            config = LayerConfig(**SEMANTIC_LAYER_DEFAULTS)

        # Validate layer index
        assert config.layer_index == 3, "SemanticLayer must be layer_index=3"

        super().__init__(config, seed)

        self.goal_dim = goal_dim
        self.state_dim = state_dim

        # Default modalities if not provided
        if modalities is None:
            modalities = ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']
        self.modalities = modalities

        if modality_dims is None:
            modality_dims = {
                'vision': 128, 'audio': 64, 'touch': 32,
                'taste': 16, 'vestibular': 16, 'threat': 8
            }
        self.modality_dims = modality_dims

        # Create or use provided cortical processor
        if cortical_processor is not None:
            self.cortex = cortical_processor
        else:
            self.cortex = CorticalProcessor(
                n_modalities=n_modalities,
                goal_dim=goal_dim,
                state_dim=state_dim,
                modality_dims=modality_dims,
                modality_order=modalities,
                **processor_kwargs
            )

        # Initialize skip weights from lower layers
        self.initialize_skip_weight(1, self.config.skip_weight_init)  # From L1
        self.initialize_skip_weight(2, self.config.skip_weight_init * 0.5)  # From L2

        # Goal processing weights
        self.W_goal_gate = self.rng.normal(0, 0.1, (self.n_modalities, goal_dim))

        # Last feedback for external use
        self.last_feedback: Optional[CorticalFeedback] = None
        self.last_goal: Optional[np.ndarray] = None

    def step(
        self,
        x: Dict[str, np.ndarray],
        skip_inputs: Optional[Dict[int, LayerOutput]] = None,
        context: Optional[np.ndarray] = None,
        goal: Optional[np.ndarray] = None,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        thalamic_output: Optional[Dict] = None,
        **kwargs
    ) -> LayerOutput:
        """
        Process input through semantic/cortical processing.

        Args:
            x: Dict mapping modality name -> feature vector
            skip_inputs: Dict with Layer 1 and optionally Layer 2 outputs
            context: Optional context vector
            goal: Goal/task encoding vector
            oscillator_state: Current oscillator state
            neuromod_levels: Current neuromodulator levels
            thalamic_output: Output from thalamus (for feedback generation)
            **kwargs: Additional arguments

        Returns:
            LayerOutput with gates summing to 1.0
        """
        self.step_count += 1

        # Use context as goal if goal not provided
        if goal is None and context is not None:
            if len(context) >= self.goal_dim:
                goal = context[:self.goal_dim]

        self.last_goal = goal

        # 1) Compute goal-driven local scores
        if goal is not None and len(goal) == self.goal_dim:
            local_scores = self.W_goal_gate @ goal
        else:
            local_scores = np.zeros(self.n_modalities)

        # 2) Get attention from cortical processor
        # Build thalamic output if not provided
        if thalamic_output is None:
            thalamic_output = self._build_thalamic_output(x, skip_inputs)

        feedback = self.cortex.step(
            thalamic_output=thalamic_output,
            goal=goal,
            oscillator_state=oscillator_state,
            neuromod_levels=neuromod_levels,
            actual_inputs=x
        )
        self.last_feedback = feedback

        # Cortical attention influences local scores
        cortical_attention = feedback.attention_weights
        local_scores += cortical_attention * self.temperature

        # 3) Compute local gates
        local_gates = self._softmax_with_temperature(local_scores)

        # 4) Incorporate skip connections
        gates, skip_contributions = self._compute_gates_with_skips(
            local_gates,
            skip_inputs
        )

        # Verify invariant
        verify_gate_invariant(gates, "SemanticLayer")

        # 5) Compute output representation
        output = self._compute_output(x, gates, cortical_attention)

        return LayerOutput(
            output=output,
            gates=gates,
            layer_index=self.layer_index,
            temperature=self.temperature,
            local_gates=local_gates,
            skip_contributions=skip_contributions
        )

    def _build_thalamic_output(
        self,
        x: Dict[str, np.ndarray],
        skip_inputs: Optional[Dict[int, LayerOutput]]
    ) -> Dict:
        """Build a thalamic output dict from available inputs."""
        # Extract prediction errors from L1 skip if available
        pe_dict = {}
        priors = {}

        if skip_inputs and 1 in skip_inputs:
            l1_out = skip_inputs[1]
            # Use L1 gate distribution as proxy for PE
            for i, m in enumerate(self.modalities):
                if i < len(l1_out.gates):
                    # Higher gate = higher "prediction error" (more attention needed)
                    pe_dict[m] = float(l1_out.gates[i])
                    priors[m] = 0.5  # Default prior

        return {
            'PE': pe_dict,
            'priors': priors
        }

    def _compute_output(
        self,
        x: Dict[str, np.ndarray],
        gates: np.ndarray,
        cortical_attention: np.ndarray
    ) -> np.ndarray:
        """Compute output representation with cortical modulation."""
        output_parts = []

        for i, m in enumerate(self.modalities):
            dim = self.modality_dims.get(m, 32)
            v = x.get(m, np.zeros(dim))

            # Ensure correct dimension
            if len(v) != dim:
                v = np.zeros(dim)

            # Gate and attention modulated output
            gate = gates[i] if i < len(gates) else 0.0
            attn = cortical_attention[i] if i < len(cortical_attention) else 0.0

            # Combined modulation: gates for routing, attention for emphasis
            modulation = 0.7 * gate + 0.3 * attn
            output_parts.append(modulation * v)

        return np.concatenate(output_parts)

    def get_cortical_feedback(self) -> Optional[CorticalFeedback]:
        """Get the last generated cortical feedback."""
        return self.last_feedback

    def get_attention_weights(self) -> np.ndarray:
        """Get current cortical attention weights."""
        return self.cortex.state.attention_weights.copy()

    def predict_next_attention(self, prediction_confidence: float = 0.5) -> np.ndarray:
        """
        Predict next-step attention for anticipatory processing.

        Args:
            prediction_confidence: Confidence in prediction (0-1)

        Returns:
            Predicted attention weights (sum to 1.0)
        """
        current = self.cortex.state.attention_weights
        return self.cortex.predict_next_attention(current, prediction_confidence)

    def apply_reward_learning(
        self,
        reward: float,
        oscillator_state: Optional['TripleOscillatorState'] = None
    ):
        """
        Update attention weights based on reward.

        Args:
            reward: Reward signal (+1 success, -1 failure)
            oscillator_state: Oscillator state that was used
        """
        if self.last_goal is not None:
            self.cortex.update_from_reward(
                reward=reward,
                goal=self.last_goal,
                oscillator_state=oscillator_state
            )

    def reset(self):
        """Reset layer state while preserving learned weights."""
        self.step_count = 0
        self.total_skip_contribution = 0.0
        self.last_feedback = None
        self.last_goal = None
        self.cortex.reset()

    def get_state(self) -> Dict[str, Any]:
        """Get serializable layer state."""
        return {
            'layer_index': self.layer_index,
            'temperature': self.temperature,
            'learning_rate': self.learning_rate,
            'n_modalities': self.n_modalities,
            'goal_dim': self.goal_dim,
            'step_count': self.step_count,
            'modalities': list(self.modalities),
            'skip_weights': self.skip_weights.copy(),
            'cortex_state': self.cortex.get_statistics(),
            'current_attention': self.cortex.state.attention_weights.tolist()
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get layer statistics including cortical metrics."""
        base_stats = super().get_statistics()

        # Add semantic-specific stats
        base_stats['goal_dim'] = self.goal_dim
        base_stats['modalities'] = list(self.modalities)
        base_stats['current_attention'] = self.cortex.state.attention_weights.tolist()
        base_stats['feedback_gain'] = self.cortex.state.feedback_gain
        base_stats['cortex_steps'] = self.cortex.steps

        if self.last_feedback:
            base_stats['last_gain_modulation'] = self.last_feedback.gain_modulation

        return base_stats
