"""
Abstract Layer (Layer 4) - Executive Control and Action Selection

The top layer in the hierarchical routing system.
Integrates BasalGanglia for action selection and Hippocampus for memory.

Properties:
    - Temperature: 0.1 (sharpest gates, most decisive)
    - Learning rate: 0.01 (fastest adaptation)
    - Skip inputs: From Layer 1 and Layer 2
    - Core: BasalGanglia for Go/NoGo action selection
           Hippocampus for episodic memory and context-dependent routing
"""

import numpy as np
from typing import Dict, Optional, Any, List, TYPE_CHECKING

from core.hierarchical_layer import (
    HierarchicalLayer,
    LayerConfig,
    LayerOutput,
    verify_gate_invariant
)
from core.basal_ganglia import BasalGanglia, BasalGangliaOutput, BGAction
from core.hippocampus import Hippocampus

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels


# Default configuration for Layer 4 (Abstract)
ABSTRACT_LAYER_DEFAULTS = {
    'layer_index': 4,
    'temperature': 0.1,      # Sharpest - most decisive
    'learning_rate': 0.01,   # Fastest adaptation
    'output_dim': 128,
    'n_modalities': 6,
}


class AbstractLayer(HierarchicalLayer):
    """
    Layer 4: Executive control and action selection.

    Integrates BasalGanglia and Hippocampus to provide:
    - Go/NoGo action selection (ADVANCE/EXPLORE/CORRECT)
    - Episodic memory for context-dependent routing
    - TD-based learning from reward signals

    Receives skip inputs from Layer 1 and Layer 2.
    This is the top of the hierarchy; outputs influence all lower layers.
    """

    def __init__(
        self,
        config: Optional[LayerConfig] = None,
        n_modalities: int = 6,
        state_dim: int = 128,
        context_dim: int = 32,
        n_actions: int = 3,
        basal_ganglia: Optional[BasalGanglia] = None,
        hippocampus: Optional[Hippocampus] = None,
        bg_modulation_strength: float = 0.3,
        memory_influence: float = 0.2,
        seed: int = 42,
        **kwargs
    ):
        """
        Initialize Abstract Layer.

        Args:
            config: LayerConfig (uses ABSTRACT_LAYER_DEFAULTS if None)
            n_modalities: Number of modalities for routing
            state_dim: Dimension of state representation
            context_dim: Dimension of context/goal vectors
            n_actions: Number of BG actions (ADVANCE, EXPLORE, CORRECT)
            basal_ganglia: Pre-configured BasalGanglia (creates new if None)
            hippocampus: Pre-configured Hippocampus (creates new if None)
            bg_modulation_strength: How strongly BG influences gates
            memory_influence: How strongly memory influences gates
            seed: Random seed for reproducibility
            **kwargs: Additional arguments
        """
        # Create default config if not provided
        if config is None:
            config = LayerConfig(**ABSTRACT_LAYER_DEFAULTS)

        # Validate layer index
        assert config.layer_index == 4, "AbstractLayer must be layer_index=4"

        super().__init__(config, seed)

        self.state_dim = state_dim
        self.context_dim = context_dim
        self.n_actions = n_actions
        self.bg_modulation_strength = bg_modulation_strength
        self.memory_influence = memory_influence

        # Create or use provided Basal Ganglia
        if basal_ganglia is not None:
            self.bg = basal_ganglia
        else:
            self.bg = BasalGanglia(
                n_inputs=6,  # 6D oscillator state
                n_actions=n_actions,
                temperature=self.temperature,
                learning_rate=self.learning_rate
            )

        # Create or use provided Hippocampus
        if hippocampus is not None:
            self.hc = hippocampus
        else:
            self.hc = Hippocampus(
                state_dim=state_dim,
                context_dim=context_dim,
                num_modalities=n_modalities,
                memory_influence=memory_influence,
                seed=seed
            )

        # Initialize skip weights from lower layers
        self.initialize_skip_weight(1, self.config.skip_weight_init)  # From L1
        self.initialize_skip_weight(2, self.config.skip_weight_init * 0.7)  # From L2

        # Executive control weights: action -> gate modulation
        self.W_action_gate = self.rng.normal(0, 0.1, (self.n_modalities, n_actions))

        # Novelty threshold for memory encoding
        self.novelty_threshold = 0.5

        # Last outputs for external use
        self.last_bg_output: Optional[BasalGangliaOutput] = None
        self.last_memory_output: Optional[Dict] = None
        self.last_action: Optional[BGAction] = None

    def step(
        self,
        x: Dict[str, np.ndarray],
        skip_inputs: Optional[Dict[int, LayerOutput]] = None,
        context: Optional[np.ndarray] = None,
        goal: Optional[np.ndarray] = None,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        td_error: Optional[float] = None,
        **kwargs
    ) -> LayerOutput:
        """
        Process input through executive control systems.

        Args:
            x: Dict mapping modality name -> feature vector
            skip_inputs: Dict with Layer 1 and Layer 2 outputs
            context: Optional context vector
            goal: Goal/task encoding vector
            oscillator_state: Current oscillator state (for BG)
            neuromod_levels: Current neuromodulator levels (for BG)
            td_error: TD error for learning (optional)
            **kwargs: Additional arguments

        Returns:
            LayerOutput with gates summing to 1.0
        """
        self.step_count += 1

        # 1) Get oscillator 6D vector for BG input
        if oscillator_state is not None:
            osc_input = oscillator_state.to_6d_vector()
        else:
            osc_input = np.zeros(6)

        # Get neuromodulator levels for BG
        dopamine = 0.5
        urgency = 0.5
        if neuromod_levels is not None:
            dopamine = neuromod_levels.dopamine
            urgency = neuromod_levels.norepinephrine

        # 2) Step Basal Ganglia for action selection
        bg_output = self.bg.step(osc_input, dopamine, urgency)
        self.last_bg_output = bg_output
        self.last_action = BGAction(bg_output.selected_action)

        # 3) Compute local scores from action selection
        # Map BG action gates to modality gates
        local_scores = self.W_action_gate @ bg_output.action_gates

        # 4) Compute local gates
        local_gates = self._softmax_with_temperature(local_scores)

        # 5) Build state vector for hippocampus
        state_vector = self._build_state_vector(x, skip_inputs)

        # 6) Step Hippocampus for memory-based routing
        prediction_error = self._compute_prediction_error(skip_inputs)
        hc_output = self.hc.step(
            state=state_vector,
            context=goal if goal is not None else context,
            gates=local_gates,
            prediction_error=prediction_error,
            encode=prediction_error > self.novelty_threshold
        )
        self.last_memory_output = hc_output

        # 7) Blend local gates with memory bias
        memory_biased_gates = hc_output['memory_biased_gates']
        blended_gates = (1 - self.memory_influence) * local_gates + \
                        self.memory_influence * memory_biased_gates

        # 8) Apply BG modulation
        bg_modulated_gates = self.bg.modulate_thalamic_gates(
            blended_gates, bg_output, self.bg_modulation_strength
        )

        # 9) Incorporate skip connections
        gates, skip_contributions = self._compute_gates_with_skips(
            bg_modulated_gates,
            skip_inputs
        )

        # Verify invariant
        verify_gate_invariant(gates, "AbstractLayer")

        # 10) Apply TD learning if error provided
        if td_error is not None:
            self.bg.update_weights(td_error, bg_output.selected_action)

        # 11) Compute output representation
        output = self._compute_output(x, gates, bg_output)

        return LayerOutput(
            output=output,
            gates=gates,
            layer_index=self.layer_index,
            temperature=self.temperature,
            local_gates=local_gates,
            skip_contributions=skip_contributions
        )

    def _build_state_vector(
        self,
        x: Dict[str, np.ndarray],
        skip_inputs: Optional[Dict[int, LayerOutput]]
    ) -> np.ndarray:
        """Build state vector for hippocampus from inputs."""
        parts = []

        # Include skip input representations if available
        if skip_inputs:
            if 1 in skip_inputs:
                parts.append(skip_inputs[1].output[:min(64, len(skip_inputs[1].output))])
            if 2 in skip_inputs:
                parts.append(skip_inputs[2].output[:min(64, len(skip_inputs[2].output))])

        # If not enough, pad or use default
        if len(parts) == 0:
            return np.zeros(self.state_dim)

        state = np.concatenate(parts)

        # Pad or truncate to state_dim
        if len(state) < self.state_dim:
            state = np.pad(state, (0, self.state_dim - len(state)))
        elif len(state) > self.state_dim:
            state = state[:self.state_dim]

        return state

    def _compute_prediction_error(
        self,
        skip_inputs: Optional[Dict[int, LayerOutput]]
    ) -> float:
        """Compute aggregate prediction error from lower layers."""
        if not skip_inputs:
            return 0.0

        errors = []
        for layer_idx, layer_out in skip_inputs.items():
            # Use gate entropy as proxy for uncertainty/prediction error
            entropy = -np.sum(layer_out.gates * np.log(layer_out.gates + 1e-10))
            errors.append(entropy)

        return float(np.mean(errors)) if errors else 0.0

    def _compute_output(
        self,
        x: Dict[str, np.ndarray],
        gates: np.ndarray,
        bg_output: BasalGangliaOutput
    ) -> np.ndarray:
        """Compute output representation."""
        # Combine BG state with gated features
        output_parts = []

        # Include BG action gates
        output_parts.append(bg_output.action_gates)

        # Include gated feature summary
        for i, (key, val) in enumerate(x.items()):
            if i >= len(gates):
                break
            gate = gates[i]
            # Summary statistic: gated mean
            output_parts.append(np.array([gate * np.mean(val)]))

        output = np.concatenate(output_parts)

        # Pad to output_dim
        if len(output) < self.output_dim:
            output = np.pad(output, (0, self.output_dim - len(output)))
        elif len(output) > self.output_dim:
            output = output[:self.output_dim]

        return output

    def get_action(self) -> Optional[BGAction]:
        """Get the last selected action."""
        return self.last_action

    def get_action_gates(self) -> Optional[np.ndarray]:
        """Get the BG action gate distribution."""
        if self.last_bg_output is not None:
            return self.last_bg_output.action_gates.copy()
        return None

    def get_bg_output(self) -> Optional[BasalGangliaOutput]:
        """Get the last BG output."""
        return self.last_bg_output

    def apply_td_learning(self, td_error: float):
        """
        Apply TD learning to Basal Ganglia.

        Args:
            td_error: Temporal difference error from reward prediction
        """
        if self.last_bg_output is not None:
            self.bg.update_weights(td_error, self.last_bg_output.selected_action)

    def get_memory_count(self) -> int:
        """Get number of stored episodic memories."""
        return len(self.hc.memories)

    def reset(self):
        """Reset layer state while preserving learned weights."""
        self.step_count = 0
        self.total_skip_contribution = 0.0
        self.last_bg_output = None
        self.last_memory_output = None
        self.last_action = None
        self.bg.reset()
        self.hc.reset()

    def get_state(self) -> Dict[str, Any]:
        """Get serializable layer state."""
        return {
            'layer_index': self.layer_index,
            'temperature': self.temperature,
            'learning_rate': self.learning_rate,
            'n_modalities': self.n_modalities,
            'n_actions': self.n_actions,
            'step_count': self.step_count,
            'skip_weights': self.skip_weights.copy(),
            'bg_statistics': self.bg.get_statistics(),
            'hc_state': self.hc.get_state(),
            'last_action': self.last_action.name if self.last_action else None
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get layer statistics including BG and HC metrics."""
        base_stats = super().get_statistics()

        # Add abstract-specific stats
        base_stats['n_actions'] = self.n_actions
        base_stats['bg_statistics'] = self.bg.get_statistics()
        base_stats['memory_count'] = len(self.hc.memories)
        base_stats['bg_modulation_strength'] = self.bg_modulation_strength
        base_stats['memory_influence'] = self.memory_influence

        if self.last_action:
            base_stats['last_action'] = self.last_action.name

        if self.last_bg_output:
            base_stats['action_confidence'] = self.last_bg_output.selection_confidence

        return base_stats
