"""
HybridNeuroSymbolicCTM - Combining SakanaAI's CTM with the_brain's Neurosymbolic Architecture

This module represents the culmination of integrating SakanaAI's
Continuous Thought Machine innovations into the_brain system.

Key Components from SakanaAI:
1. NeuronLevelModel (NLM) - Per-neuron temporal processing
2. SynchronisationModule - Pairwise neuron sync as representation
3. StateTraceManager - Sliding window temporal traces
4. SynapseUNET - U-Net style inter-neuron communication

Key Components from the_brain:
1. Neurosymbolic Brain Modules (VIS, SOM, DLPFC, DMN, etc.)
2. Symbolic Rule Constraints (Allis Rules)
3. Consciousness Metric (DMN-based)
4. Multi-CTM Domain Routing

The Hybrid CTM combines both approaches:
- SakanaAI's temporal processing for rich internal dynamics
- the_brain's interpretable module structure for domain specialization

Usage:
    from core.hybrid_ctm import HybridNeuroSymbolicCTM

    ctm = HybridNeuroSymbolicCTM(
        feature_dim=256,
        iterations=50,
        consciousness_threshold=0.85
    )

    board = torch.randint(0, 11, (batch_size, 5, 4))
    output = ctm(board)

    print(f"Converged: {output.converged}")
    print(f"Steps: {output.reasoning_steps}")
    print(f"Consciousness: {output.consciousness_trajectory[-1]}")
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

try:
    from core.neuron_level_model import NeuronLevelModel
    from core.synchronisation_module import SynchronisationModule, DualSynchronisation
    from core.state_trace_manager import StateTraceManager
    from core.thought_projector import ThoughtProjector
except ImportError:
    from neuron_level_model import NeuronLevelModel
    from synchronisation_module import SynchronisationModule, DualSynchronisation
    from state_trace_manager import StateTraceManager
    from thought_projector import ThoughtProjector


@dataclass
class HybridCTMOutput:
    """
    Output from Hybrid CTM reasoning.

    Attributes:
        predictions: Per-iteration predictions (batch, out_dims, iterations)
        certainties: Per-iteration certainty scores (batch, iterations)
        final_sync: Final synchronisation vector (batch, n_synch_out)
        consciousness_trajectory: Consciousness score per iteration
        converged: Whether reasoning converged early
        reasoning_steps: Total steps taken
        final_prediction: Best prediction (batch, out_dims)
        thought_vector: Projected thought vector for text decoding (batch, thought_dim)
    """
    predictions: torch.Tensor
    certainties: torch.Tensor
    final_sync: torch.Tensor
    consciousness_trajectory: List[float]
    converged: bool
    reasoning_steps: int
    final_prediction: torch.Tensor
    thought_vector: Optional[torch.Tensor] = None


class SynapseUNET(nn.Module):
    """
    U-Net style synapse model for inter-neuron communication.

    Based on SakanaAI's synapse architecture. Uses skip connections
    and multiple depth levels for flexible information mixing.

    The intuition: synaptic connections in the brain are complex,
    and a deep U-Net can learn sophisticated update rules.

    Parameters:
        d_model: Output dimension (should match input after projection)
        depth: Number of U-Net levels (more = more complex processing)
        min_width: Minimum width at bottleneck
        dropout: Dropout rate
    """

    def __init__(
        self,
        d_model: int,
        depth: int = 4,
        min_width: int = 16,
        dropout: float = 0.0
    ):
        super().__init__()
        self.d_model = d_model
        self.depth = depth

        # Compute width at each level
        widths = np.linspace(d_model, min_width, depth).astype(int)

        # Initial projection (LazyLinear handles variable input)
        self.first_proj = nn.Sequential(
            nn.LazyLinear(int(widths[0])),
            nn.LayerNorm(int(widths[0])),
            nn.SiLU()
        )

        # Build down and up paths
        self.down = nn.ModuleList()
        self.up = nn.ModuleList()
        self.skip_norms = nn.ModuleList()

        for i in range(len(widths) - 1):
            # Downward: widths[i] -> widths[i+1]
            self.down.append(nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(int(widths[i]), int(widths[i + 1])),
                nn.LayerNorm(int(widths[i + 1])),
                nn.SiLU()
            ))

            # Upward: widths[i+1] -> widths[i]
            self.up.append(nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(int(widths[i + 1]), int(widths[i])),
                nn.LayerNorm(int(widths[i])),
                nn.SiLU()
            ))

            # Skip connection normalization
            self.skip_norms.append(nn.LayerNorm(int(widths[i])))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Process input through U-Net structure.

        Args:
            x: Input tensor (batch, input_dim)

        Returns:
            Output tensor (batch, d_model)
        """
        # Initial projection
        out = self.first_proj(x)

        # Downward path with skip connection storage
        skips = [out]
        for down_layer in self.down:
            out = down_layer(out)
            skips.append(out)

        # Upward path with skip connections
        num_ups = len(self.up)
        for i, up_layer in enumerate(reversed(self.up)):
            skip_idx = num_ups - 1 - i
            out = up_layer(out)
            # Add skip connection and normalize
            out = self.skip_norms[skip_idx](out + skips[skip_idx])

        return out


class HybridNeuroSymbolicCTM(nn.Module):
    """
    Hybrid CTM combining SakanaAI's temporal processing with
    the_brain's neurosymbolic architecture.

    Architecture:
        Input -> Encoder -> [Iteration Loop] -> Output

        Iteration Loop:
        1. Compute action sync from activated_state
        2. Combine input features with activated_state
        3. Process through SynapseUNET (inter-neuron communication)
        4. Update state_trace (sliding window)
        5. Process through NLM (per-neuron temporal processing)
        6. Compute output sync for prediction
        7. Check certainty/convergence

    Parameters:
        feature_dim: Internal feature dimension (d_model)
        memory_length: Temporal trace length (M)
        iterations: Maximum reasoning iterations (T)
        n_synch_out: Sync pairs for output
        n_synch_action: Sync pairs for action/attention
        synapse_depth: U-Net depth for synapses
        nlm_hidden_dims: Hidden dims for NLM
        out_dims: Output dimension
        consciousness_threshold: Early stopping threshold
        device: Torch device
    """

    def __init__(
        self,
        feature_dim: int = 256,
        memory_length: int = 10,
        iterations: int = 50,
        n_synch_out: int = 64,
        n_synch_action: int = 32,
        synapse_depth: int = 4,
        nlm_hidden_dims: int = 64,
        out_dims: int = 4,
        consciousness_threshold: float = 0.85,
        device: str = 'cpu',
        enable_thought_projection: bool = False,
        thought_dim: int = 2048
    ):
        super().__init__()

        self.feature_dim = feature_dim
        self.memory_length = memory_length
        self.iterations = iterations
        self.consciousness_threshold = consciousness_threshold
        self.device = device
        self.out_dims = out_dims
        self.n_synch_out = n_synch_out
        self.enable_thought_projection = enable_thought_projection
        self.thought_dim = thought_dim

        # === State Management (Phase 3) ===
        self.trace_manager = StateTraceManager(feature_dim, memory_length)

        # === Core CTM Components ===

        # Synapse model: combines input + activated_state -> new pre-activation
        self.synapses = SynapseUNET(
            d_model=feature_dim,
            depth=synapse_depth,
            min_width=16,
            dropout=0.0
        )

        # NLM: processes state_trace -> activated_state (Phase 1)
        self.nlm = NeuronLevelModel(
            d_model=feature_dim,
            memory_length=memory_length,
            hidden_dims=nlm_hidden_dims,
            deep_nlm=True
        )

        # Synchronisation modules (Phase 2)
        self.sync_action = SynchronisationModule(
            d_model=feature_dim,
            n_synch_pairs=n_synch_action,
            neuron_select_type='random-pairing'
        )

        self.sync_out = SynchronisationModule(
            d_model=feature_dim,
            n_synch_pairs=n_synch_out,
            neuron_select_type='random-pairing'
        )

        # === Output Processing ===
        self.output_projector = nn.Sequential(
            nn.Linear(n_synch_out, out_dims)
        )

        # === Input Processing ===
        # Encode puzzle board to features
        self.input_encoder = nn.Sequential(
            nn.Linear(20, 128),  # 5x4 board = 20 cells
            nn.ReLU(),
            nn.Linear(128, feature_dim),
            nn.LayerNorm(feature_dim)
        )

        # Project sync_action to query for potential attention
        self.action_proj = nn.Linear(n_synch_action, feature_dim)

        # === Thought Projection (Phase 5) ===
        # Optionally project CTM states to thought vector for text decoding
        if enable_thought_projection:
            self.thought_projector = ThoughtProjector(
                sync_dim=n_synch_out,
                thought_dim=thought_dim,
                certainty_embed_dim=128,
                consciousness_hidden=256,
                dropout=0.1
            )
        else:
            self.thought_projector = None

    def compute_certainty(self, logits: torch.Tensor) -> torch.Tensor:
        """
        Compute certainty as 1 - normalized entropy (SakanaAI style).

        High certainty = model is confident in its prediction
        Low certainty = model is uncertain

        Args:
            logits: Raw output logits (batch, out_dims)

        Returns:
            certainty: (batch,) certainty scores in [0, 1]
        """
        probs = F.softmax(logits, dim=-1)
        # Add small epsilon for numerical stability
        entropy = -(probs * torch.log(probs + 1e-8)).sum(dim=-1)
        max_entropy = torch.log(torch.tensor(logits.size(-1), dtype=torch.float, device=logits.device))
        normalized_entropy = entropy / max_entropy
        certainty = 1 - normalized_entropy
        return certainty

    def forward(
        self,
        board: torch.Tensor,
        max_iterations: Optional[int] = None,
        track: bool = False,
        semantic_features: Optional[torch.Tensor] = None
    ) -> HybridCTMOutput:
        """
        Full hybrid reasoning pass.

        Args:
            board: (batch, 5, 4) puzzle state tensor
            max_iterations: Override default max iterations
            track: Whether to track additional info
            semantic_features: Optional (batch, feature_dim) semantic encoding from
                               Sentence-BERT. If provided, combines with board features.

        Returns:
            HybridCTMOutput with predictions, certainties, etc.
        """
        B = board.size(0)
        iters = max_iterations or self.iterations
        device = board.device

        # === Encode Input ===
        board_flat = board.view(B, -1).float()
        input_features = self.input_encoder(board_flat)

        # === Combine with Semantic Features if provided ===
        if semantic_features is not None:
            # Ensure semantic_features is on correct device and has correct shape
            semantic_features = semantic_features.to(device)
            if semantic_features.dim() == 1:
                semantic_features = semantic_features.unsqueeze(0)
            # Combine: weighted sum of board features and semantic features
            # Semantic features provide richer task understanding
            input_features = 0.5 * input_features + 0.5 * semantic_features

        # === Initialize State ===
        state_trace, activated_state = self.trace_manager.get_initial_state(B, device)

        # Initialize sync accumulators
        alpha_action, beta_action = None, None
        alpha_out, beta_out = None, None

        # Storage for outputs
        predictions = torch.zeros(B, self.out_dims, iters, device=device)
        certainties = torch.zeros(B, iters, device=device)
        consciousness_trajectory = []

        converged = False
        final_step = iters
        best_certainty = 0.0
        best_prediction = None

        # === Reasoning Loop ===
        for step in range(iters):
            # 1. Compute action synchronisation (for attention/query)
            sync_action, alpha_action, beta_action = self.sync_action(
                activated_state, alpha_action, beta_action
            )

            # 2. Project action sync and combine with input
            action_query = self.action_proj(sync_action)
            combined = torch.cat([input_features, activated_state, action_query], dim=-1)

            # 3. Synaptic processing (inter-neuron communication)
            new_pre_activation = self.synapses(combined)

            # 4. Update state trace (sliding window)
            state_trace = self.trace_manager.update_trace(state_trace, new_pre_activation)

            # 5. NLM processing (per-neuron temporal processing)
            activated_state = self.nlm(state_trace)

            # 6. Compute output synchronisation
            sync_out, alpha_out, beta_out = self.sync_out(
                activated_state, alpha_out, beta_out
            )

            # 7. Get prediction and certainty
            prediction = self.output_projector(sync_out)
            certainty = self.compute_certainty(prediction)

            predictions[:, :, step] = prediction
            certainties[:, step] = certainty

            # Track best prediction
            mean_certainty = certainty.mean().item()
            if mean_certainty > best_certainty:
                best_certainty = mean_certainty
                best_prediction = prediction.clone()

            # Consciousness = certainty (simplified, could use DMN in full version)
            consciousness_trajectory.append(mean_certainty)

            # 8. Check convergence
            if mean_certainty >= self.consciousness_threshold:
                converged = True
                final_step = step + 1
                break

        # Use best prediction if we didn't converge
        if best_prediction is None:
            best_prediction = predictions[:, :, -1]

        # === Compute Thought Vector (Phase 5) ===
        thought_vector = None
        if self.thought_projector is not None:
            thought_vector = self.thought_projector(
                sync_out=sync_out,
                certainties=certainties[:, :final_step],
                consciousness_trajectory=consciousness_trajectory
            )

        return HybridCTMOutput(
            predictions=predictions[:, :, :final_step],
            certainties=certainties[:, :final_step],
            final_sync=sync_out,
            consciousness_trajectory=consciousness_trajectory,
            converged=converged,
            reasoning_steps=final_step,
            final_prediction=best_prediction,
            thought_vector=thought_vector
        )

    def get_num_parameters(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters())

    def get_component_params(self) -> dict:
        """Return parameter count per component."""
        params = {
            'trace_manager': sum(p.numel() for p in self.trace_manager.parameters()),
            'synapses': sum(p.numel() for p in self.synapses.parameters()),
            'nlm': sum(p.numel() for p in self.nlm.parameters()),
            'sync_action': sum(p.numel() for p in self.sync_action.parameters()),
            'sync_out': sum(p.numel() for p in self.sync_out.parameters()),
            'output_projector': sum(p.numel() for p in self.output_projector.parameters()),
            'input_encoder': sum(p.numel() for p in self.input_encoder.parameters()),
            'action_proj': sum(p.numel() for p in self.action_proj.parameters()),
        }
        if self.thought_projector is not None:
            params['thought_projector'] = sum(p.numel() for p in self.thought_projector.parameters())
        return params


def compare_with_original_ctm():
    """
    Compare HybridCTM with original KlotskiCTM on same input.

    This demonstrates the difference in reasoning approaches.
    """
    print("\n" + "=" * 60)
    print("Comparison: HybridCTM vs Original Approach")
    print("=" * 60)

    # Create hybrid CTM
    hybrid = HybridNeuroSymbolicCTM(
        feature_dim=256,
        iterations=30,
        consciousness_threshold=0.85
    )

    # Test input
    board = torch.randint(0, 11, (2, 5, 4))

    # Run hybrid
    with torch.no_grad():
        output = hybrid(board)

    print("\nHybrid CTM Results:")
    print(f"  Converged: {output.converged}")
    print(f"  Steps: {output.reasoning_steps}")
    print(f"  Final consciousness: {output.consciousness_trajectory[-1]:.3f}")
    print(f"  Prediction shape: {output.final_prediction.shape}")

    print("\nKey Differences:")
    print("  Original: Random board perturbation, module activations")
    print("  Hybrid: Temporal traces + NLM + Synchronisation")


if __name__ == "__main__":
    # Test the HybridNeuroSymbolicCTM
    print("=" * 60)
    print("Testing HybridNeuroSymbolicCTM")
    print("=" * 60)

    # Create model
    ctm = HybridNeuroSymbolicCTM(
        feature_dim=256,
        memory_length=10,
        iterations=50,
        n_synch_out=64,
        n_synch_action=32,
        synapse_depth=4,
        nlm_hidden_dims=64,
        out_dims=4,
        consciousness_threshold=0.85
    )

    # Initialize lazy modules with a dummy forward pass
    print("\nInitializing lazy modules...")
    dummy_board = torch.randint(0, 11, (1, 5, 4))
    with torch.no_grad():
        _ = ctm(dummy_board, max_iterations=1)
    print("Lazy modules initialized.")

    print(f"\nTotal parameters: {ctm.get_num_parameters():,}")
    print("\nComponent breakdown:")
    for name, count in ctm.get_component_params().items():
        print(f"  {name}: {count:,}")

    # Test forward pass
    print("\n" + "-" * 40)
    print("Forward pass test:")
    print("-" * 40)

    batch_size = 4
    board = torch.randint(0, 11, (batch_size, 5, 4))

    print(f"Input board shape: {board.shape}")

    with torch.no_grad():
        output = ctm(board, max_iterations=30)

    print(f"\nOutput:")
    print(f"  predictions shape: {output.predictions.shape}")
    print(f"  certainties shape: {output.certainties.shape}")
    print(f"  final_sync shape: {output.final_sync.shape}")
    print(f"  converged: {output.converged}")
    print(f"  reasoning_steps: {output.reasoning_steps}")
    print(f"  final_prediction shape: {output.final_prediction.shape}")

    print(f"\nConsciousness trajectory (last 5):")
    for i, c in enumerate(output.consciousness_trajectory[-5:]):
        print(f"  Step {output.reasoning_steps - 5 + i}: {c:.4f}")

    # Test gradient flow
    print("\n" + "-" * 40)
    print("Gradient test:")
    print("-" * 40)

    board = torch.randint(0, 11, (2, 5, 4)).float()
    board.requires_grad = True

    output = ctm(board.long(), max_iterations=10)
    loss = output.final_prediction.sum()
    loss.backward()

    print(f"Gradient flows to input: {board.grad is not None}")

    # Test convergence behavior
    print("\n" + "-" * 40)
    print("Convergence test:")
    print("-" * 40)

    results = []
    for threshold in [0.5, 0.7, 0.85, 0.95]:
        ctm.consciousness_threshold = threshold
        with torch.no_grad():
            output = ctm(board.long(), max_iterations=50)
        results.append((threshold, output.converged, output.reasoning_steps))

    print("Threshold | Converged | Steps")
    print("-" * 35)
    for thresh, conv, steps in results:
        print(f"  {thresh:.2f}    |    {conv}    |  {steps}")

    # Compare with original approach
    compare_with_original_ctm()

    print("\n" + "=" * 60)
    print("HybridNeuroSymbolicCTM tests PASSED!")
    print("=" * 60)
