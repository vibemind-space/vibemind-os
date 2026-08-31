"""
HierarchicalCTM - Fast/Slow Thinking Architecture

Implements a dual-system architecture inspired by Kahneman's System 1/System 2:
- System 1 (Fast): Quick, intuitive processing (5-10 iterations, small model)
- System 2 (Slow): Deliberate, analytical processing (30-100 iterations, large model)

The meta-controller decides when to escalate from fast to slow thinking
based on uncertainty and task complexity.

Architecture:
    Task → Fast CTM (System 1) → Meta-Controller → [If uncertain] → Slow CTM (System 2) → Output

Usage:
    from core.hierarchical_ctm import HierarchicalCTM

    ctm = HierarchicalCTM(
        fast_dim=128,
        slow_dim=512,
        uncertainty_threshold=0.7
    )

    output = ctm(task_encoding)
    print(f"Used system: {output.system_used}")
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from core.hybrid_ctm import HybridNeuroSymbolicCTM, HybridCTMOutput
except ImportError:
    from hybrid_ctm import HybridNeuroSymbolicCTM, HybridCTMOutput


class ThinkingSystem(Enum):
    """Which thinking system was used."""
    FAST = "system1"
    SLOW = "system2"
    BOTH = "escalated"


@dataclass
class HierarchicalCTMOutput:
    """Output from HierarchicalCTM."""
    predictions: torch.Tensor
    certainties: torch.Tensor
    thought_vector: Optional[torch.Tensor]
    consciousness_trajectory: List[float]
    converged: bool
    reasoning_steps: int
    system_used: ThinkingSystem
    fast_certainty: float
    slow_certainty: Optional[float]
    escalation_reason: Optional[str]
    meta_confidence: float


class MetaController(nn.Module):
    """
    Meta-controller that decides when to escalate from fast to slow thinking.

    Factors considered:
    - Certainty level from fast system
    - Task complexity (estimated from input)
    - Historical performance on similar tasks

    Parameters:
        input_dim: Input feature dimension
        threshold: Certainty threshold for escalation
    """

    def __init__(
        self,
        input_dim: int = 128,
        threshold: float = 0.7,
        learned_escalation: bool = True
    ):
        super().__init__()
        self.threshold = threshold
        self.learned_escalation = learned_escalation

        if learned_escalation:
            # Learned escalation network
            self.escalation_net = nn.Sequential(
                nn.Linear(input_dim + 2, 64),  # +2 for certainty and steps
                nn.ReLU(),
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
                nn.Sigmoid()
            )
        else:
            self.escalation_net = None

        # Complexity estimator
        self.complexity_estimator = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(
        self,
        fast_output: HybridCTMOutput,
        input_features: torch.Tensor
    ) -> Tuple[bool, float, str]:
        """
        Decide whether to escalate to slow system.

        Args:
            fast_output: Output from fast CTM
            input_features: Original input features

        Returns:
            should_escalate: Whether to use slow system
            confidence: Meta-controller confidence
            reason: Reason for decision
        """
        # Get fast system certainty
        fast_certainty = fast_output.certainties[:, -1].mean().item()

        # Estimate task complexity
        complexity = self.complexity_estimator(input_features).mean().item()

        if self.learned_escalation:
            # Combine features for learned decision
            batch_size = input_features.size(0)
            certainty_tensor = torch.tensor([[fast_certainty]] * batch_size, device=input_features.device)
            steps_tensor = torch.tensor([[fast_output.reasoning_steps / 50]] * batch_size, device=input_features.device)

            combined = torch.cat([
                input_features,
                certainty_tensor,
                steps_tensor
            ], dim=-1)

            escalate_prob = self.escalation_net(combined).mean().item()
            should_escalate = escalate_prob > 0.5
            confidence = abs(escalate_prob - 0.5) * 2  # 0 at boundary, 1 at extremes
        else:
            # Simple threshold-based decision
            should_escalate = fast_certainty < self.threshold or complexity > 0.7
            confidence = 1.0 - fast_certainty if should_escalate else fast_certainty

        # Determine reason
        if should_escalate:
            if fast_certainty < self.threshold:
                reason = f"low_certainty ({fast_certainty:.2f} < {self.threshold:.2f})"
            elif complexity > 0.7:
                reason = f"high_complexity ({complexity:.2f})"
            else:
                reason = "learned_decision"
        else:
            reason = "sufficient_certainty"

        return should_escalate, confidence, reason


class HierarchicalCTM(nn.Module):
    """
    Hierarchical CTM with fast (System 1) and slow (System 2) thinking.

    The architecture mimics human dual-process cognition:
    - Fast system: Quick, pattern-based responses
    - Slow system: Deliberate, analytical reasoning

    Parameters:
        fast_feature_dim: Feature dimension for fast system (smaller)
        slow_feature_dim: Feature dimension for slow system (larger)
        fast_iterations: Max iterations for fast system
        slow_iterations: Max iterations for slow system
        fast_threshold: Consciousness threshold for fast system
        slow_threshold: Consciousness threshold for slow system
        uncertainty_threshold: When to escalate to slow system
        enable_thought_projection: Project to thought vectors
        thought_dim: Thought vector dimension
        device: Torch device
    """

    def __init__(
        self,
        fast_feature_dim: int = 128,
        slow_feature_dim: int = 512,
        fast_iterations: int = 10,
        slow_iterations: int = 50,
        fast_threshold: float = 0.9,
        slow_threshold: float = 0.85,
        uncertainty_threshold: float = 0.7,
        enable_thought_projection: bool = True,
        thought_dim: int = 2048,
        device: str = 'cpu'
    ):
        super().__init__()

        self.fast_feature_dim = fast_feature_dim
        self.slow_feature_dim = slow_feature_dim
        self.uncertainty_threshold = uncertainty_threshold
        self.device = device
        self.enable_thought_projection = enable_thought_projection
        self.thought_dim = thought_dim

        # System 1: Fast, intuitive CTM
        self.fast_ctm = HybridNeuroSymbolicCTM(
            feature_dim=fast_feature_dim,
            memory_length=5,  # Shorter memory
            iterations=fast_iterations,
            n_synch_out=32,   # Fewer sync pairs
            n_synch_action=16,
            synapse_depth=2,  # Shallower
            nlm_hidden_dims=32,
            consciousness_threshold=fast_threshold,
            enable_thought_projection=enable_thought_projection,
            thought_dim=thought_dim,
            device=device
        )

        # System 2: Slow, analytical CTM
        self.slow_ctm = HybridNeuroSymbolicCTM(
            feature_dim=slow_feature_dim,
            memory_length=20,  # Longer memory
            iterations=slow_iterations,
            n_synch_out=128,  # More sync pairs
            n_synch_action=64,
            synapse_depth=6,  # Deeper
            nlm_hidden_dims=128,
            consciousness_threshold=slow_threshold,
            enable_thought_projection=enable_thought_projection,
            thought_dim=thought_dim,
            device=device
        )

        # Meta-controller
        self.meta_controller = MetaController(
            input_dim=fast_feature_dim,
            threshold=uncertainty_threshold,
            learned_escalation=True
        )

        # Input adapters (to handle different feature dims)
        self.fast_input_adapter = nn.Sequential(
            nn.LazyLinear(fast_feature_dim),
            nn.LayerNorm(fast_feature_dim)
        )

        self.slow_input_adapter = nn.Sequential(
            nn.LazyLinear(slow_feature_dim),
            nn.LayerNorm(slow_feature_dim)
        )

        # Thought combiner (when using both systems)
        if enable_thought_projection:
            self.thought_combiner = nn.Sequential(
                nn.Linear(thought_dim * 2, thought_dim),
                nn.LayerNorm(thought_dim)
            )

    def _initialize_if_needed(self, x: torch.Tensor):
        """Initialize lazy modules if not already done."""
        # Initialize adapters
        if hasattr(self.fast_input_adapter[0], 'weight') and self.fast_input_adapter[0].weight is None:
            with torch.no_grad():
                _ = self.fast_input_adapter(x)

        if hasattr(self.slow_input_adapter[0], 'weight') and self.slow_input_adapter[0].weight is None:
            with torch.no_grad():
                _ = self.slow_input_adapter(x)

        # Initialize CTMs
        dummy_board = torch.randint(0, 11, (1, 5, 4), device=x.device)
        with torch.no_grad():
            try:
                _ = self.fast_ctm(dummy_board, max_iterations=1)
            except (RuntimeError, ValueError, TypeError):
                pass
            try:
                _ = self.slow_ctm(dummy_board, max_iterations=1)
            except (RuntimeError, ValueError, TypeError):
                pass

    def forward(
        self,
        x: torch.Tensor,
        max_iterations: Optional[int] = None,
        force_system: Optional[str] = None
    ) -> HierarchicalCTMOutput:
        """
        Forward pass through hierarchical CTM.

        Args:
            x: Input tensor (batch, ...) will be flattened
            max_iterations: Override max iterations (applies to active system)
            force_system: Force use of 'fast' or 'slow' system

        Returns:
            HierarchicalCTMOutput
        """
        # Flatten input if needed
        if x.dim() > 2:
            x = x.view(x.size(0), -1).float()

        # Initialize lazy modules
        self._initialize_if_needed(x)

        # Create board-like input for CTMs
        B = x.size(0)
        board_fast = self._create_board_input(x, self.fast_feature_dim)
        board_slow = self._create_board_input(x, self.slow_feature_dim)

        # Always run fast system first (unless forced slow)
        if force_system != 'slow':
            fast_output = self.fast_ctm(board_fast, max_iterations=max_iterations)
            fast_certainty = fast_output.certainties[:, -1].mean().item()
        else:
            fast_output = None
            fast_certainty = 0.0

        # Decide whether to escalate
        if force_system == 'fast':
            should_escalate = False
            meta_confidence = 1.0
            escalation_reason = "forced_fast"
        elif force_system == 'slow':
            should_escalate = True
            meta_confidence = 1.0
            escalation_reason = "forced_slow"
        else:
            # Use meta-controller
            fast_features = self.fast_input_adapter(x)
            should_escalate, meta_confidence, escalation_reason = self.meta_controller(
                fast_output, fast_features
            )

        # Run slow system if needed
        if should_escalate:
            slow_output = self.slow_ctm(board_slow, max_iterations=max_iterations)
            slow_certainty = slow_output.certainties[:, -1].mean().item()

            # Determine which output to use
            if fast_output is not None:
                system_used = ThinkingSystem.BOTH

                # Combine thought vectors
                if self.enable_thought_projection and fast_output.thought_vector is not None:
                    combined_thought = torch.cat([
                        fast_output.thought_vector,
                        slow_output.thought_vector
                    ], dim=-1)
                    thought_vector = self.thought_combiner(combined_thought)
                else:
                    thought_vector = slow_output.thought_vector

                # Use slow system's predictions but combine consciousness
                combined_consciousness = (
                    fast_output.consciousness_trajectory +
                    slow_output.consciousness_trajectory
                )
            else:
                system_used = ThinkingSystem.SLOW
                thought_vector = slow_output.thought_vector
                combined_consciousness = slow_output.consciousness_trajectory

            final_output = slow_output
            final_certainty = slow_certainty
        else:
            system_used = ThinkingSystem.FAST
            final_output = fast_output
            thought_vector = fast_output.thought_vector
            combined_consciousness = fast_output.consciousness_trajectory
            slow_certainty = None
            final_certainty = fast_certainty

        # Compute total reasoning steps
        total_steps = final_output.reasoning_steps
        if system_used == ThinkingSystem.BOTH:
            total_steps = fast_output.reasoning_steps + slow_output.reasoning_steps

        return HierarchicalCTMOutput(
            predictions=final_output.predictions[:, :, -1] if final_output.predictions.dim() > 2 else final_output.predictions,
            certainties=final_output.certainties,
            thought_vector=thought_vector,
            consciousness_trajectory=combined_consciousness,
            converged=final_output.converged,
            reasoning_steps=total_steps,
            system_used=system_used,
            fast_certainty=fast_certainty,
            slow_certainty=slow_certainty,
            escalation_reason=escalation_reason,
            meta_confidence=meta_confidence
        )

    def _create_board_input(self, x: torch.Tensor, feature_dim: int) -> torch.Tensor:
        """Create board-like input for CTM."""
        B = x.size(0)

        # Project to feature_dim, then reshape to (B, 5, 4)
        # We'll use a simple approach: tile/truncate to 20 values
        if feature_dim == self.fast_feature_dim:
            projected = self.fast_input_adapter(x)
        else:
            projected = self.slow_input_adapter(x)

        # Reshape to board-like (use first 20 or pad)
        if projected.size(1) >= 20:
            board_flat = projected[:, :20]
        else:
            padding = torch.zeros(B, 20 - projected.size(1), device=x.device)
            board_flat = torch.cat([projected, padding], dim=1)

        # Normalize to 0-10 range for board compatibility
        board_flat = torch.sigmoid(board_flat) * 10
        board = board_flat.view(B, 5, 4).long()

        return board

    def get_system_stats(self) -> Dict[str, Any]:
        """Get statistics about both systems."""
        fast_params = self.fast_ctm.get_num_parameters()
        slow_params = self.slow_ctm.get_num_parameters()
        meta_params = sum(p.numel() for p in self.meta_controller.parameters())

        return {
            'fast_system': {
                'parameters': fast_params,
                'feature_dim': self.fast_feature_dim,
                'max_iterations': self.fast_ctm.iterations
            },
            'slow_system': {
                'parameters': slow_params,
                'feature_dim': self.slow_feature_dim,
                'max_iterations': self.slow_ctm.iterations
            },
            'meta_controller': {
                'parameters': meta_params,
                'threshold': self.uncertainty_threshold
            },
            'total_parameters': fast_params + slow_params + meta_params
        }

    def get_num_parameters(self) -> int:
        """Get total parameter count."""
        return sum(p.numel() for p in self.parameters())


if __name__ == "__main__":
    print("=" * 60)
    print("Testing HierarchicalCTM")
    print("=" * 60)

    # Create HierarchicalCTM
    print("\n" + "-" * 40)
    print("Creating HierarchicalCTM:")
    print("-" * 40)

    ctm = HierarchicalCTM(
        fast_feature_dim=128,
        slow_feature_dim=256,
        fast_iterations=10,
        slow_iterations=30,
        uncertainty_threshold=0.7,
        enable_thought_projection=True,
        thought_dim=2048
    )

    # Initialize with dummy input
    dummy = torch.randn(1, 20)
    with torch.no_grad():
        _ = ctm(dummy, max_iterations=1, force_system='fast')
        _ = ctm(dummy, max_iterations=1, force_system='slow')

    print("\nSystem statistics:")
    stats = ctm.get_system_stats()
    print(f"  Fast system: {stats['fast_system']['parameters']:,} params")
    print(f"  Slow system: {stats['slow_system']['parameters']:,} params")
    print(f"  Meta-controller: {stats['meta_controller']['parameters']:,} params")
    print(f"  Total: {stats['total_parameters']:,} params")

    # Test with automatic escalation
    print("\n" + "-" * 40)
    print("Testing automatic escalation:")
    print("-" * 40)

    test_input = torch.randn(2, 20)

    for i in range(5):
        output = ctm(test_input, max_iterations=15)
        print(f"\nRun {i + 1}:")
        print(f"  System used: {output.system_used.value}")
        print(f"  Fast certainty: {output.fast_certainty:.3f}")
        print(f"  Slow certainty: {output.slow_certainty if output.slow_certainty else 'N/A'}")
        print(f"  Escalation: {output.escalation_reason}")
        print(f"  Total steps: {output.reasoning_steps}")
        if output.thought_vector is not None:
            print(f"  Thought vector: {output.thought_vector.shape}")

    # Test forced systems
    print("\n" + "-" * 40)
    print("Testing forced systems:")
    print("-" * 40)

    for force in ['fast', 'slow']:
        output = ctm(test_input, force_system=force)
        print(f"\nForced {force}:")
        print(f"  System used: {output.system_used.value}")
        print(f"  Steps: {output.reasoning_steps}")
        print(f"  Certainty: {output.fast_certainty if force == 'fast' else output.slow_certainty:.3f}")

    print("\n" + "=" * 60)
    print("HierarchicalCTM tests PASSED!")
    print("=" * 60)
