"""
Hierarchical Routing System - Main Orchestrator for 4-Layer Routing

Coordinates all hierarchical routing layers:
    - Layer 1 (Sensory): ThalamoPC6Adaptive, bottom-up attention
    - Layer 2 (Feature): PredictiveRouter, temporal prediction
    - Layer 3 (Semantic): CorticalProcessor, concept-based attention
    - Layer 4 (Abstract): BasalGanglia + Hippocampus, executive control

Key Properties:
    - Gates ALWAYS sum to 1.0 at each layer
    - Skip connections allow fast information flow between layers
    - Skip weights clamped < 0.5 to ensure local computation dominates
    - Temperature decreases up hierarchy (soft → sharp)
    - Learning rate increases up hierarchy (slow → fast)

Usage:
    from core.hierarchical_routing_system import HierarchicalRoutingSystem

    hrs = HierarchicalRoutingSystem()

    result = hrs.step(
        x={'vision': vision_vec, 'audio': audio_vec, ...},
        context=context_vec,
        goal=goal_vec,
        oscillator_state=osc.state,
        neuromod_levels=neuromod.levels,
        td_error=td_error
    )

    # Access layer outputs
    l1_gates = result.layer_outputs[1].gates
    l4_action = result.layer_outputs[4].gates

    # Final blended gates
    final_gates = result.final_gates
"""

import numpy as np
import time
from typing import Dict, Optional, Any, List, TYPE_CHECKING
from dataclasses import dataclass

from core.hierarchical_layer import (
    HierarchicalLayer,
    LayerConfig,
    LayerOutput,
    HierarchicalRoutingResult,
    blend_gates_weighted,
    verify_gate_invariant
)
from core.sensory_layer import SensoryLayer, SENSORY_LAYER_DEFAULTS
from core.feature_layer import FeatureLayer, FEATURE_LAYER_DEFAULTS
from core.semantic_layer import SemanticLayer, SEMANTIC_LAYER_DEFAULTS
from core.abstract_layer import AbstractLayer, ABSTRACT_LAYER_DEFAULTS

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels
    from core.thalamo_pc_adaptive import ThalamoPC6Adaptive
    from core.predictive_router import PredictiveRouter
    from core.cortical_feedback import CorticalProcessor
    from core.basal_ganglia import BasalGanglia
    from core.hippocampus import Hippocampus


# Default layer weights for final gate blending
DEFAULT_LAYER_WEIGHTS = {
    1: 0.15,  # Sensory (lowest influence on final)
    2: 0.20,  # Feature
    3: 0.30,  # Semantic
    4: 0.35,  # Abstract (highest influence on final)
}


@dataclass
class HierarchicalRoutingConfig:
    """Configuration for the Hierarchical Routing System."""
    # Layer weights for final gate blending
    layer_weights: Dict[int, float] = None

    # Skip connection configuration
    enable_skip_connections: bool = True
    skip_weight_init: float = 0.1
    skip_weight_max: float = 0.5

    # Learning
    enable_learning: bool = True

    # Performance
    max_processing_time_ms: float = 10.0

    # Modalities
    modalities: List[str] = None
    modality_dims: Dict[str, int] = None

    # Dimensions
    goal_dim: int = 32
    state_dim: int = 128

    # Random seed
    seed: int = 42

    def __post_init__(self):
        if self.layer_weights is None:
            self.layer_weights = DEFAULT_LAYER_WEIGHTS.copy()

        if self.modalities is None:
            self.modalities = ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']

        if self.modality_dims is None:
            self.modality_dims = {
                'vision': 128, 'audio': 64, 'touch': 32,
                'taste': 16, 'vestibular': 16, 'threat': 8
            }


class HierarchicalRoutingSystem:
    """
    Main orchestrator for 4-layer hierarchical routing.

    Coordinates bottom-up and top-down information flow:
    1. Bottom-up: L1 → L2 → L3 → L4 (sensory → abstract)
    2. Skip connections: L1 → L3, L1 → L4, L2 → L4
    3. Final gates: Weighted blend of all layer gates

    Critical Invariants:
    - All gates sum to 1.0 at every layer
    - Skip weights < 0.5 (local dominates)
    """

    def __init__(
        self,
        config: Optional[HierarchicalRoutingConfig] = None,
        thalamus: Optional['ThalamoPC6Adaptive'] = None,
        predictive_router: Optional['PredictiveRouter'] = None,
        cortical_processor: Optional['CorticalProcessor'] = None,
        basal_ganglia: Optional['BasalGanglia'] = None,
        hippocampus: Optional['Hippocampus'] = None
    ):
        """
        Initialize Hierarchical Routing System.

        Args:
            config: HierarchicalRoutingConfig (uses defaults if None)
            thalamus: Pre-configured ThalamoPC6Adaptive for L1
            predictive_router: Pre-configured PredictiveRouter for L2
            cortical_processor: Pre-configured CorticalProcessor for L3
            basal_ganglia: Pre-configured BasalGanglia for L4
            hippocampus: Pre-configured Hippocampus for L4
        """
        self.config = config or HierarchicalRoutingConfig()

        # Create layers
        self._init_layers(
            thalamus, predictive_router, cortical_processor,
            basal_ganglia, hippocampus
        )

        # Layer weights for final blend
        self.layer_weights = self.config.layer_weights.copy()

        # Statistics
        self.step_count = 0
        self.total_processing_time_ms = 0.0
        self.gate_history: List[np.ndarray] = []
        self.max_history = 100

    def _init_layers(
        self,
        thalamus: Optional['ThalamoPC6Adaptive'],
        predictive_router: Optional['PredictiveRouter'],
        cortical_processor: Optional['CorticalProcessor'],
        basal_ganglia: Optional['BasalGanglia'],
        hippocampus: Optional['Hippocampus']
    ):
        """Initialize all four layers."""
        seed = self.config.seed
        modalities = self.config.modalities
        modality_dims = self.config.modality_dims

        # Layer 1: Sensory
        l1_config = LayerConfig(**SENSORY_LAYER_DEFAULTS)
        l1_config.skip_weight_init = self.config.skip_weight_init
        l1_config.skip_weight_max = self.config.skip_weight_max
        self.layer1 = SensoryLayer(
            config=l1_config,
            thalamus=thalamus,
            seed=seed
        )

        # Layer 2: Feature
        l2_config = LayerConfig(**FEATURE_LAYER_DEFAULTS)
        l2_config.skip_weight_init = self.config.skip_weight_init
        l2_config.skip_weight_max = self.config.skip_weight_max
        self.layer2 = FeatureLayer(
            config=l2_config,
            modalities=modalities,
            latent_dims=modality_dims,
            predictive_router=predictive_router,
            seed=seed + 1
        )

        # Layer 3: Semantic
        l3_config = LayerConfig(**SEMANTIC_LAYER_DEFAULTS)
        l3_config.skip_weight_init = self.config.skip_weight_init
        l3_config.skip_weight_max = self.config.skip_weight_max
        self.layer3 = SemanticLayer(
            config=l3_config,
            n_modalities=len(modalities),
            goal_dim=self.config.goal_dim,
            state_dim=self.config.state_dim,
            modalities=modalities,
            modality_dims=modality_dims,
            cortical_processor=cortical_processor,
            seed=seed + 2
        )

        # Layer 4: Abstract
        l4_config = LayerConfig(**ABSTRACT_LAYER_DEFAULTS)
        l4_config.skip_weight_init = self.config.skip_weight_init
        l4_config.skip_weight_max = self.config.skip_weight_max
        self.layer4 = AbstractLayer(
            config=l4_config,
            n_modalities=len(modalities),
            state_dim=self.config.state_dim,
            context_dim=self.config.goal_dim,
            basal_ganglia=basal_ganglia,
            hippocampus=hippocampus,
            seed=seed + 3
        )

        # Store as dict for easy access
        self.layers: Dict[int, HierarchicalLayer] = {
            1: self.layer1,
            2: self.layer2,
            3: self.layer3,
            4: self.layer4
        }

    def step(
        self,
        x: Dict[str, np.ndarray],
        context: Optional[np.ndarray] = None,
        goal: Optional[np.ndarray] = None,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        td_error: Optional[float] = None,
        hazard: Optional[Dict[str, float]] = None,
        reward: Optional[Dict[str, float]] = None,
        adapt: bool = True
    ) -> HierarchicalRoutingResult:
        """
        Process input through all hierarchical layers.

        Args:
            x: Dict mapping modality -> input vector
            context: Optional context vector
            goal: Goal/task encoding vector
            oscillator_state: Current oscillator state
            neuromod_levels: Current neuromodulator levels
            td_error: TD error for learning
            hazard: Hazard signals per modality (for L1)
            reward: Reward signals per modality (for L1)
            adapt: Whether to perform online adaptation

        Returns:
            HierarchicalRoutingResult with all layer outputs and final gates
        """
        start_time = time.perf_counter()
        self.step_count += 1

        layer_outputs: Dict[int, LayerOutput] = {}

        # ========== Layer 1: Sensory ==========
        l1_out = self.layer1.step(
            x=x,
            skip_inputs=None,  # L1 has no skip inputs
            context=context,
            hazard=hazard,
            reward=reward,
            adapt=adapt and self.config.enable_learning
        )
        layer_outputs[1] = l1_out

        # Build L2 input from L1 output
        l2_input = self._extract_latents_for_l2(l1_out)

        # ========== Layer 2: Feature ==========
        l2_skip = {1: l1_out} if self.config.enable_skip_connections else None
        l2_out = self.layer2.step(
            x=l2_input,
            skip_inputs=l2_skip,
            context=context
        )
        layer_outputs[2] = l2_out

        # Build thalamic output for L3
        thalamic_output = self._build_thalamic_output(l1_out)

        # ========== Layer 3: Semantic ==========
        l3_skip = {}
        if self.config.enable_skip_connections:
            l3_skip[1] = l1_out
            l3_skip[2] = l2_out
        l3_out = self.layer3.step(
            x=l2_input,
            skip_inputs=l3_skip if l3_skip else None,
            context=context,
            goal=goal,
            oscillator_state=oscillator_state,
            neuromod_levels=neuromod_levels,
            thalamic_output=thalamic_output
        )
        layer_outputs[3] = l3_out

        # ========== Layer 4: Abstract ==========
        l4_skip = {}
        if self.config.enable_skip_connections:
            l4_skip[1] = l1_out
            l4_skip[2] = l2_out
        l4_out = self.layer4.step(
            x=l2_input,
            skip_inputs=l4_skip if l4_skip else None,
            context=context,
            goal=goal,
            oscillator_state=oscillator_state,
            neuromod_levels=neuromod_levels,
            td_error=td_error if self.config.enable_learning else None
        )
        layer_outputs[4] = l4_out

        # ========== Final Gate Computation ==========
        final_gates = blend_gates_weighted(layer_outputs, self.layer_weights)
        verify_gate_invariant(final_gates, "HierarchicalRoutingSystem.final")

        # Determine dominant layer
        layer_contributions = {
            i: np.max(out.gates) * self.layer_weights[i]
            for i, out in layer_outputs.items()
        }
        dominant_layer = max(layer_contributions, key=layer_contributions.get)

        # Compute processing time
        processing_time_ms = (time.perf_counter() - start_time) * 1000
        self.total_processing_time_ms += processing_time_ms

        # Track gate history
        self.gate_history.append(final_gates.copy())
        if len(self.gate_history) > self.max_history:
            self.gate_history.pop(0)

        return HierarchicalRoutingResult(
            layer_outputs=layer_outputs,
            final_gates=final_gates,
            dominant_layer=dominant_layer,
            processing_time_ms=processing_time_ms
        )

    def _extract_latents_for_l2(self, l1_out: LayerOutput) -> Dict[str, np.ndarray]:
        """Extract latent representations from L1 for L2 input."""
        # Get modality outputs from thalamus
        if hasattr(self.layer1, 'get_modality_outputs'):
            return self.layer1.get_modality_outputs()

        # Fallback: split L1 output by modality dimension
        modalities = self.config.modalities
        modality_dims = self.config.modality_dims
        result = {}
        offset = 0
        for m in modalities:
            dim = modality_dims.get(m, 32)
            if offset + dim <= len(l1_out.output):
                result[m] = l1_out.output[offset:offset+dim]
            else:
                result[m] = np.zeros(dim)
            offset += dim
        return result

    def _build_thalamic_output(self, l1_out: LayerOutput) -> Dict:
        """Build thalamic output dict for L3 from L1 output."""
        modalities = self.config.modalities

        # Get prediction errors from L1 if available
        pe_dict = {}
        if hasattr(self.layer1, 'get_prediction_errors'):
            pe_dict = self.layer1.get_prediction_errors()
        else:
            # Use gate distribution as proxy
            for i, m in enumerate(modalities):
                if i < len(l1_out.gates):
                    pe_dict[m] = float(l1_out.gates[i])

        priors = {m: 0.5 for m in modalities}

        return {
            'PE': pe_dict,
            'priors': priors,
            'g': l1_out.gates
        }

    def get_layer(self, layer_idx: int) -> HierarchicalLayer:
        """Get a specific layer by index."""
        if layer_idx not in self.layers:
            raise ValueError(f"Invalid layer index: {layer_idx}")
        return self.layers[layer_idx]

    def get_all_gates(self) -> Dict[int, np.ndarray]:
        """Get current gates from all layers."""
        return {
            i: layer.get_statistics().get('gates', np.zeros(6))
            for i, layer in self.layers.items()
        }

    def get_action(self):
        """Get the selected action from Layer 4."""
        return self.layer4.get_action()

    def apply_cortical_feedback(
        self,
        prior_delta: np.ndarray,
        trn_delta: np.ndarray,
        gain: float = 1.0
    ) -> Dict[str, Any]:
        """
        Apply top-down cortical feedback to Layer 1 (thalamus).

        Args:
            prior_delta: Modality prior adjustments
            trn_delta: TRN inhibition adjustments
            gain: Activity gain

        Returns:
            Dict of applied changes
        """
        if hasattr(self.layer1, 'apply_top_down_feedback'):
            return self.layer1.apply_top_down_feedback(prior_delta, trn_delta, gain)
        return {}

    def update_layer_weights(self, new_weights: Dict[int, float]):
        """
        Update layer weights for final gate blending.

        Args:
            new_weights: Dict mapping layer_index -> weight
        """
        for layer_idx, weight in new_weights.items():
            if layer_idx in self.layer_weights:
                self.layer_weights[layer_idx] = weight

        # Normalize
        total = sum(self.layer_weights.values())
        for layer_idx in self.layer_weights:
            self.layer_weights[layer_idx] /= total

    def reset(self):
        """Reset all layers."""
        for layer in self.layers.values():
            layer.reset()
        self.step_count = 0
        self.total_processing_time_ms = 0.0
        self.gate_history.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        return {
            'step_count': self.step_count,
            'total_processing_time_ms': self.total_processing_time_ms,
            'avg_processing_time_ms': (
                self.total_processing_time_ms / max(self.step_count, 1)
            ),
            'layer_weights': self.layer_weights.copy(),
            'layer_statistics': {
                i: layer.get_statistics() for i, layer in self.layers.items()
            },
            'recent_gate_entropy': float(
                -np.sum(self.gate_history[-1] * np.log(self.gate_history[-1] + 1e-10))
            ) if self.gate_history else 0.0
        }

    def get_state(self) -> Dict[str, Any]:
        """Get serializable system state."""
        return {
            'config': {
                'layer_weights': self.config.layer_weights,
                'enable_skip_connections': self.config.enable_skip_connections,
                'enable_learning': self.config.enable_learning,
                'modalities': self.config.modalities,
                'goal_dim': self.config.goal_dim,
                'state_dim': self.config.state_dim
            },
            'step_count': self.step_count,
            'layer_states': {
                i: layer.get_state() for i, layer in self.layers.items()
            }
        }


# ============================================================================
# Factory Function
# ============================================================================

def create_hierarchical_routing_system(
    modalities: Optional[List[str]] = None,
    modality_dims: Optional[Dict[str, int]] = None,
    goal_dim: int = 32,
    enable_skip_connections: bool = True,
    enable_learning: bool = True,
    seed: int = 42
) -> HierarchicalRoutingSystem:
    """
    Factory function to create a HierarchicalRoutingSystem with custom config.

    Args:
        modalities: List of modality names
        modality_dims: Dict mapping modality -> dimension
        goal_dim: Dimension of goal/context vectors
        enable_skip_connections: Whether to enable skip connections
        enable_learning: Whether to enable online learning
        seed: Random seed

    Returns:
        Configured HierarchicalRoutingSystem
    """
    config = HierarchicalRoutingConfig(
        modalities=modalities,
        modality_dims=modality_dims,
        goal_dim=goal_dim,
        enable_skip_connections=enable_skip_connections,
        enable_learning=enable_learning,
        seed=seed
    )
    return HierarchicalRoutingSystem(config=config)


# ============================================================================
# Demo
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("HIERARCHICAL ROUTING SYSTEM - 4-Layer Architecture Demo")
    print("=" * 70)
    print()

    # Create system
    hrs = create_hierarchical_routing_system()

    print("System created with layers:")
    for i, layer in hrs.layers.items():
        print(f"  Layer {i}: {layer.__class__.__name__}")
        print(f"    Temperature: {layer.temperature}")
        print(f"    Learning Rate: {layer.learning_rate}")
    print()

    print("Layer weights for final gates:", hrs.layer_weights)
    print()

    # Create test input
    x = {
        'vision': np.random.randn(128) * 0.5,
        'audio': np.random.randn(64) * 0.3,
        'touch': np.random.randn(32) * 0.2,
        'taste': np.random.randn(16) * 0.1,
        'vestibular': np.random.randn(16) * 0.1,
        'threat': np.random.randn(8) * 0.1
    }
    context = np.random.randn(32) * 0.2
    goal = np.random.randn(32) * 0.3

    print("Running 10 steps...")
    for step in range(10):
        result = hrs.step(
            x=x,
            context=context,
            goal=goal,
            td_error=np.random.randn() * 0.1 if step > 5 else None
        )

        if step == 0 or step == 9:
            print(f"\nStep {step + 1}:")
            print(f"  Processing time: {result.processing_time_ms:.2f}ms")
            print(f"  Dominant layer: {result.dominant_layer}")
            print(f"  Final gates: {np.round(result.final_gates, 3)}")
            print(f"  Layer gate entropies:")
            for i, out in result.layer_outputs.items():
                entropy = -np.sum(out.gates * np.log(out.gates + 1e-10))
                print(f"    L{i}: {entropy:.3f}")

    print()
    print("Final statistics:")
    stats = hrs.get_statistics()
    print(f"  Total steps: {stats['step_count']}")
    print(f"  Avg processing time: {stats['avg_processing_time_ms']:.2f}ms")
    print()
    print("=" * 70)
