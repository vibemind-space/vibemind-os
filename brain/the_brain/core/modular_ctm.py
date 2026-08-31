"""
ModularCTM - Specialized Brain Modules for Different Task Types

Implements a modular CTM architecture with specialized processing modules
for different cognitive domains, inspired by neuroscience research on
brain specialization.

Modules:
- VIS (Visual/Spatial): Spatial reasoning, visual processing
- LAN (Language): Linguistic analysis, semantic understanding
- MTL (Memory/Temporal): Temporal sequences, episodic memory
- OFC (Orbitofrontal): Value assessment, decision making
- DLPFC (Executive): Meta-control, task coordination

Architecture:
    Task → Router → [Module Selection] → Specialized Processing → Integration → Output

Usage:
    from core.modular_ctm import ModularCTM

    ctm = ModularCTM(
        feature_dim=256,
        iterations=30,
        enable_routing=True
    )

    output = ctm(task_encoding, task_type='language')
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Optional, List, Tuple, Union
from dataclasses import dataclass
from enum import Enum

try:
    from core.neuron_level_model import NeuronLevelModel
    from core.synchronisation_module import SynchronisationModule
    from core.state_trace_manager import StateTraceManager
except ImportError:
    from neuron_level_model import NeuronLevelModel
    from synchronisation_module import SynchronisationModule
    from state_trace_manager import StateTraceManager


class ModuleType(Enum):
    """Brain module types."""
    VIS = "visual"       # Visual/Spatial processing
    LAN = "language"     # Language/Semantic processing
    MTL = "temporal"     # Memory/Temporal processing
    OFC = "value"        # Value/Decision processing
    DLPFC = "executive"  # Executive control (meta-module)


@dataclass
class ModularCTMOutput:
    """Output from ModularCTM."""
    predictions: torch.Tensor
    certainties: torch.Tensor
    module_activations: Dict[str, torch.Tensor]
    routing_weights: Dict[str, float]
    thought_vector: Optional[torch.Tensor]
    consciousness_trajectory: List[float]
    converged: bool
    reasoning_steps: int
    primary_module: str


class BrainModule(nn.Module):
    """
    Specialized brain module for a specific cognitive domain.

    Each module has its own:
    - Feature processing layers
    - Attention mechanisms
    - Output projection

    Parameters:
        feature_dim: Internal feature dimension
        specialization: Module type (visual, language, temporal, value)
        hidden_dim: Hidden layer dimension
        num_heads: Number of attention heads
        dropout: Dropout rate
    """

    def __init__(
        self,
        feature_dim: int = 256,
        specialization: str = "general",
        hidden_dim: int = 512,
        num_heads: int = 4,
        dropout: float = 0.1
    ):
        super().__init__()
        self.feature_dim = feature_dim
        self.specialization = specialization

        # Feature transformation
        self.input_proj = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout)
        )

        # Self-attention for internal processing
        self.self_attn = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )

        # Specialization-specific processing
        if specialization == "visual":
            # Spatial processing - position encoding emphasized
            self.spec_layer = nn.Sequential(
                nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU()
            )
        elif specialization == "language":
            # Semantic processing - larger capacity
            self.spec_layer = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim * 2),
                nn.LayerNorm(hidden_dim * 2),
                nn.GELU(),
                nn.Linear(hidden_dim * 2, hidden_dim),
                nn.LayerNorm(hidden_dim)
            )
        elif specialization == "temporal":
            # Sequence processing - GRU for temporal dependencies
            self.spec_layer = nn.GRU(
                hidden_dim, hidden_dim, batch_first=True
            )
        elif specialization == "value":
            # Value estimation - regression-style
            self.spec_layer = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.Tanh()  # Bounded output for value
            )
        else:
            # General processing
            self.spec_layer = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.GELU()
            )

        # Output projection
        self.output_proj = nn.Sequential(
            nn.Linear(hidden_dim, feature_dim),
            nn.LayerNorm(feature_dim)
        )

        # Module activation gate (learned)
        self.activation_gate = nn.Sequential(
            nn.Linear(feature_dim, 1),
            nn.Sigmoid()
        )

    def forward(
        self,
        x: torch.Tensor,
        context: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Process input through specialized module.

        Args:
            x: Input features (batch, feature_dim) or (batch, seq, feature_dim)
            context: Optional context from other modules

        Returns:
            output: Processed features (batch, feature_dim)
            activation: Module activation level (batch, 1)
        """
        # Ensure 3D for attention
        if x.dim() == 2:
            x = x.unsqueeze(1)  # (batch, 1, feature_dim)

        # Input projection
        h = self.input_proj(x)  # (batch, seq, hidden_dim)

        # Self-attention
        h_attn, _ = self.self_attn(h, h, h)
        h = h + h_attn  # Residual

        # Specialization-specific processing
        if self.specialization == "visual":
            # Transpose for conv1d
            h = self.spec_layer(h.transpose(1, 2)).transpose(1, 2)
        elif self.specialization == "temporal":
            h, _ = self.spec_layer(h)
        else:
            h = self.spec_layer(h)

        # Pool if sequence
        if h.size(1) > 1:
            h = h.mean(dim=1)
        else:
            h = h.squeeze(1)

        # Output projection
        output = self.output_proj(h)

        # Compute activation level
        activation = self.activation_gate(output)

        return output, activation


class TaskRouter(nn.Module):
    """
    Routes tasks to appropriate brain modules based on task type.

    Uses learned routing weights to determine module contributions.

    Parameters:
        feature_dim: Input feature dimension
        num_modules: Number of brain modules to route to
    """

    def __init__(
        self,
        feature_dim: int = 256,
        num_modules: int = 5,
        temperature: float = 1.0
    ):
        super().__init__()
        self.feature_dim = feature_dim
        self.num_modules = num_modules
        self.temperature = temperature

        # Routing network
        self.router = nn.Sequential(
            nn.Linear(feature_dim, feature_dim),
            nn.ReLU(),
            nn.Linear(feature_dim, num_modules)
        )

        # Module names
        self.module_names = ['VIS', 'LAN', 'MTL', 'OFC', 'DLPFC']

    def forward(
        self,
        x: torch.Tensor,
        task_type: Optional[str] = None
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        Compute routing weights for modules.

        Args:
            x: Input features (batch, feature_dim)
            task_type: Optional explicit task type override

        Returns:
            weights: Routing weights (batch, num_modules)
            weight_dict: Dictionary of module weights
        """
        if task_type is not None:
            # Hard routing based on task type
            weights = torch.zeros(x.size(0), self.num_modules, device=x.device)
            type_to_module = {
                'visual': 0, 'spatial': 0,
                'language': 1, 'semantic': 1,
                'temporal': 2, 'sequence': 2, 'memory': 2,
                'value': 3, 'decision': 3,
                'executive': 4, 'meta': 4
            }
            module_idx = type_to_module.get(task_type.lower(), 4)  # Default to executive
            weights[:, module_idx] = 1.0
        else:
            # Learned soft routing
            logits = self.router(x)
            weights = F.softmax(logits / self.temperature, dim=-1)

        # Create weight dictionary
        weight_dict = {}
        for i, name in enumerate(self.module_names[:self.num_modules]):
            weight_dict[name] = weights[:, i].mean().item()

        return weights, weight_dict


class ModuleIntegrator(nn.Module):
    """
    Integrates outputs from multiple brain modules.

    Uses attention-based integration to combine module outputs
    based on their relevance to the task.

    Parameters:
        feature_dim: Feature dimension
        num_modules: Number of modules to integrate
    """

    def __init__(
        self,
        feature_dim: int = 256,
        num_modules: int = 5
    ):
        super().__init__()

        # Integration attention
        self.query = nn.Linear(feature_dim, feature_dim)
        self.key = nn.Linear(feature_dim, feature_dim)
        self.value = nn.Linear(feature_dim, feature_dim)

        # Output projection
        self.output_proj = nn.Sequential(
            nn.Linear(feature_dim, feature_dim),
            nn.LayerNorm(feature_dim)
        )

    def forward(
        self,
        module_outputs: List[torch.Tensor],
        routing_weights: torch.Tensor
    ) -> torch.Tensor:
        """
        Integrate module outputs.

        Args:
            module_outputs: List of (batch, feature_dim) tensors
            routing_weights: (batch, num_modules) routing weights

        Returns:
            integrated: (batch, feature_dim) integrated output
        """
        # Stack outputs: (batch, num_modules, feature_dim)
        stacked = torch.stack(module_outputs, dim=1)

        # Weight by routing
        weighted = stacked * routing_weights.unsqueeze(-1)

        # Sum weighted outputs
        integrated = weighted.sum(dim=1)

        # Project
        integrated = self.output_proj(integrated)

        return integrated


class ModularCTM(nn.Module):
    """
    Modular Continuous Thought Machine with specialized brain modules.

    Combines multiple specialized modules for different cognitive domains,
    with learned routing to select appropriate modules for each task.

    Parameters:
        feature_dim: Internal feature dimension
        memory_length: Temporal trace length
        iterations: Maximum reasoning iterations
        module_hidden_dim: Hidden dimension for modules
        n_synch_out: Synchronization pairs for output
        consciousness_threshold: Early stopping threshold
        enable_routing: Use learned routing (vs explicit)
        enable_thought_projection: Project to thought vector
        thought_dim: Thought vector dimension
        device: Torch device
    """

    def __init__(
        self,
        feature_dim: int = 256,
        memory_length: int = 10,
        iterations: int = 30,
        module_hidden_dim: int = 512,
        n_synch_out: int = 64,
        consciousness_threshold: float = 0.85,
        enable_routing: bool = True,
        enable_thought_projection: bool = False,
        thought_dim: int = 2048,
        device: str = 'cpu'
    ):
        super().__init__()

        self.feature_dim = feature_dim
        self.iterations = iterations
        self.consciousness_threshold = consciousness_threshold
        self.enable_routing = enable_routing
        self.enable_thought_projection = enable_thought_projection
        self.device = device

        # State management
        self.trace_manager = StateTraceManager(feature_dim, memory_length)

        # NLM for temporal processing
        self.nlm = NeuronLevelModel(
            d_model=feature_dim,
            memory_length=memory_length,
            hidden_dims=64,
            deep_nlm=True
        )

        # Synchronization for output
        self.sync_out = SynchronisationModule(
            d_model=feature_dim,
            n_synch_pairs=n_synch_out
        )

        # Brain modules
        self.modules = nn.ModuleDict({
            'VIS': BrainModule(feature_dim, 'visual', module_hidden_dim),
            'LAN': BrainModule(feature_dim, 'language', module_hidden_dim),
            'MTL': BrainModule(feature_dim, 'temporal', module_hidden_dim),
            'OFC': BrainModule(feature_dim, 'value', module_hidden_dim),
            'DLPFC': BrainModule(feature_dim, 'executive', module_hidden_dim)
        })

        # Router
        self.router = TaskRouter(feature_dim, num_modules=len(self.modules))

        # Integrator
        self.integrator = ModuleIntegrator(feature_dim, num_modules=len(self.modules))

        # Input encoder
        self.input_encoder = nn.Sequential(
            nn.LazyLinear(feature_dim),
            nn.LayerNorm(feature_dim),
            nn.ReLU()
        )

        # Output projection
        self.output_projector = nn.Linear(n_synch_out, 4)  # Default 4 outputs

        # Thought projection
        if enable_thought_projection:
            self.thought_projector = nn.Sequential(
                nn.Linear(n_synch_out + feature_dim, 512),
                nn.ReLU(),
                nn.Linear(512, thought_dim),
                nn.LayerNorm(thought_dim)
            )
        else:
            self.thought_projector = None

    def compute_certainty(self, logits: torch.Tensor) -> torch.Tensor:
        """Compute certainty from logits."""
        probs = F.softmax(logits, dim=-1)
        entropy = -(probs * torch.log(probs + 1e-8)).sum(dim=-1)
        max_entropy = torch.log(torch.tensor(logits.size(-1), dtype=torch.float, device=logits.device))
        return 1 - (entropy / max_entropy)

    def forward(
        self,
        x: torch.Tensor,
        max_iterations: Optional[int] = None,
        task_type: Optional[str] = None
    ) -> ModularCTMOutput:
        """
        Forward pass through modular CTM.

        Args:
            x: Input tensor (batch, input_dim) or (batch, 5, 4) board
            max_iterations: Override default iterations
            task_type: Optional task type for explicit routing

        Returns:
            ModularCTMOutput
        """
        # Flatten if needed
        if x.dim() > 2:
            x = x.view(x.size(0), -1).float()

        B = x.size(0)
        iters = max_iterations or self.iterations
        device = x.device

        # Encode input
        input_features = self.input_encoder(x)

        # Get routing weights
        routing_weights, weight_dict = self.router(input_features, task_type)

        # Initialize state
        state_trace, activated_state = self.trace_manager.get_initial_state(B, device)
        alpha_out, beta_out = None, None

        # Storage
        module_activations = {name: [] for name in self.modules.keys()}
        consciousness_trajectory = []
        all_certainties = []

        converged = False
        final_step = iters

        for step in range(iters):
            # Process through each module
            module_outputs = []
            for name, module in self.modules.items():
                combined = input_features + activated_state
                output, activation = module(combined)
                module_outputs.append(output)
                module_activations[name].append(activation.mean().item())

            # Integrate module outputs
            integrated = self.integrator(module_outputs, routing_weights)

            # Update trace
            state_trace = self.trace_manager.update_trace(state_trace, integrated)

            # NLM processing
            activated_state = self.nlm(state_trace)

            # Synchronization
            sync_out, alpha_out, beta_out = self.sync_out(activated_state, alpha_out, beta_out)

            # Output
            prediction = self.output_projector(sync_out)
            certainty = self.compute_certainty(prediction)
            all_certainties.append(certainty)

            # Consciousness
            consciousness = certainty.mean().item()
            consciousness_trajectory.append(consciousness)

            # Check convergence
            if consciousness >= self.consciousness_threshold:
                converged = True
                final_step = step + 1
                break

        # Stack certainties
        certainties = torch.stack(all_certainties[:final_step], dim=1)

        # Final module activations (average)
        final_activations = {}
        for name, acts in module_activations.items():
            if acts:
                final_activations[name] = torch.tensor(acts[:final_step]).mean()

        # Determine primary module
        primary_module = max(weight_dict, key=weight_dict.get)

        # Thought projection
        thought_vector = None
        if self.thought_projector is not None:
            combined_for_thought = torch.cat([sync_out, activated_state], dim=-1)
            thought_vector = self.thought_projector(combined_for_thought)

        return ModularCTMOutput(
            predictions=prediction,
            certainties=certainties,
            module_activations=final_activations,
            routing_weights=weight_dict,
            thought_vector=thought_vector,
            consciousness_trajectory=consciousness_trajectory,
            converged=converged,
            reasoning_steps=final_step,
            primary_module=primary_module
        )

    def get_num_parameters(self) -> int:
        """Get total parameter count."""
        return sum(p.numel() for p in self.parameters())

    def get_module_parameters(self) -> Dict[str, int]:
        """Get parameter count per module."""
        counts = {}
        for name, module in self.modules.items():
            counts[name] = sum(p.numel() for p in module.parameters())
        counts['router'] = sum(p.numel() for p in self.router.parameters())
        counts['integrator'] = sum(p.numel() for p in self.integrator.parameters())
        counts['nlm'] = sum(p.numel() for p in self.nlm.parameters())
        return counts


if __name__ == "__main__":
    print("=" * 60)
    print("Testing ModularCTM")
    print("=" * 60)

    # Create ModularCTM
    print("\n" + "-" * 40)
    print("Creating ModularCTM:")
    print("-" * 40)

    ctm = ModularCTM(
        feature_dim=256,
        iterations=20,
        consciousness_threshold=0.85,
        enable_routing=True,
        enable_thought_projection=True,
        thought_dim=2048
    )

    # Initialize lazy modules
    dummy = torch.randn(1, 20)
    with torch.no_grad():
        _ = ctm(dummy, max_iterations=1)

    print(f"\nTotal parameters: {ctm.get_num_parameters():,}")
    print("\nModule parameters:")
    for name, count in ctm.get_module_parameters().items():
        print(f"  {name}: {count:,}")

    # Test with different task types
    print("\n" + "-" * 40)
    print("Testing with different task types:")
    print("-" * 40)

    test_input = torch.randn(2, 20)

    for task_type in ['visual', 'language', 'temporal', 'value', None]:
        output = ctm(test_input, max_iterations=10, task_type=task_type)
        print(f"\nTask type: {task_type or 'auto'}")
        print(f"  Primary module: {output.primary_module}")
        print(f"  Routing: {output.routing_weights}")
        print(f"  Steps: {output.reasoning_steps}")
        print(f"  Converged: {output.converged}")
        if output.thought_vector is not None:
            print(f"  Thought vector: {output.thought_vector.shape}")

    # Test module activations
    print("\n" + "-" * 40)
    print("Testing module activations:")
    print("-" * 40)

    output = ctm(test_input, max_iterations=15)
    print("Module activations (average):")
    for name, activation in output.module_activations.items():
        print(f"  {name}: {activation:.4f}")

    print("\n" + "=" * 60)
    print("ModularCTM tests PASSED!")
    print("=" * 60)
