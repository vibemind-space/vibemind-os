"""
Expert Activity (Phase 4) - Expert Activation Vectors

Implements the E (expert activity) component of the phase dynamics equation:
    ΔφH(r) = -λ(ωqf δ(r) + ∇·(W×E))

Expert activity vectors represent the activation levels of different "experts"
which map to operational regimes:
- EXPLOIT expert (index 0)
- EXPLORE expert (index 1)
- REPAIR expert (index 2)
- TRANSITION expert (index 3)
- DEADLOCK expert (index 4)

The coupling term ∇·(W×E) represents how other experts influence phase changes.
"""

import numpy as np
import torch
import torch.nn as nn
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import IntEnum


class ExpertIndex(IntEnum):
    """Index mapping for experts (matches Regime enum)"""
    EXPLOIT = 0
    EXPLORE = 1
    REPAIR = 2
    TRANSITION = 3
    DEADLOCK = 4


@dataclass
class ExpertState:
    """State of a single expert"""
    index: int
    name: str
    activation: float = 0.0
    history: List[float] = field(default_factory=list)

    def update(self, new_activation: float, decay: float = 0.9):
        """Update activation with exponential smoothing"""
        self.activation = decay * self.activation + (1 - decay) * new_activation
        self.history.append(self.activation)
        if len(self.history) > 100:
            self.history = self.history[-100:]


class ExpertActivityTracker:
    """
    Tracks activation levels of multiple CTM experts

    E[i] = activation level of expert i
    Experts map to regimes: EXPLOIT, EXPLORE, REPAIR, TRANSITION, DEADLOCK

    The tracker:
    - Updates E from regime probability distributions
    - Computes coupling divergence ∇·(W×E) for phase dynamics
    - Maintains activation history for analysis
    """

    def __init__(
        self,
        num_experts: int = 5,
        smoothing: float = 0.9,
        min_activation: float = 0.01
    ):
        """
        Initialize expert activity tracker

        Args:
            num_experts: Number of experts (default 5 for 5 regimes)
            smoothing: Exponential smoothing factor
            min_activation: Minimum activation to prevent complete suppression
        """
        self.num_experts = num_experts
        self.smoothing = smoothing
        self.min_activation = min_activation

        # Expert names (matching Regime enum)
        self.expert_names = ['EXPLOIT', 'EXPLORE', 'REPAIR', 'TRANSITION', 'DEADLOCK']

        # Current activations: E[i] in [0, 1]
        self.activations = np.ones(num_experts, dtype=np.float32) / num_experts

        # Expert states with history
        self.experts = [
            ExpertState(i, self.expert_names[i] if i < len(self.expert_names) else f"expert_{i}")
            for i in range(num_experts)
        ]

        # Activation history for the entire tracker
        self.history: List[np.ndarray] = []

    def update_from_regime(self, regime_probs: np.ndarray):
        """
        Update E from regime probability distribution

        Args:
            regime_probs: [num_experts] probability distribution over regimes
        """
        if len(regime_probs) != self.num_experts:
            raise ValueError(f"Expected {self.num_experts} probs, got {len(regime_probs)}")

        # Apply smoothing
        self.activations = (
            self.smoothing * self.activations +
            (1 - self.smoothing) * regime_probs
        )

        # Apply minimum activation
        self.activations = np.maximum(self.activations, self.min_activation)

        # Normalize to sum to 1
        self.activations = self.activations / (self.activations.sum() + 1e-8)

        # Update individual expert states
        for i, expert in enumerate(self.experts):
            expert.update(self.activations[i], self.smoothing)

        # Save history
        self.history.append(self.activations.copy())
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def update_from_dominant(self, dominant_index: int, confidence: float = 0.8):
        """
        Update E from a single dominant expert

        Args:
            dominant_index: Index of dominant expert
            confidence: How strongly dominant (default 0.8)
        """
        probs = np.full(self.num_experts, (1 - confidence) / (self.num_experts - 1))
        probs[dominant_index] = confidence
        self.update_from_regime(probs)

    def get_activations(self) -> np.ndarray:
        """Get current activation vector E"""
        return self.activations.copy()

    def get_tensor(self, device: str = 'cpu') -> torch.Tensor:
        """Get activations as PyTorch tensor"""
        return torch.tensor(self.activations, dtype=torch.float32, device=device)

    def get_divergence(self, W: np.ndarray) -> np.ndarray:
        """
        Compute ∇·(W×E) - coupling pressure from other experts

        For expert phase dynamics:
        Δφ = -λ(ω⊙δ + W^T @ E)

        Args:
            W: [num_experts, num_channels] coupling matrix
               or [num_experts, num_experts] for expert-expert coupling

        Returns:
            Coupling divergence vector
        """
        # W^T @ E gives coupling influence
        coupling = W.T @ self.activations
        return coupling

    def get_dominant_expert(self) -> Tuple[int, str, float]:
        """
        Get currently dominant expert

        Returns:
            (index, name, activation)
        """
        idx = int(np.argmax(self.activations))
        return idx, self.expert_names[idx], self.activations[idx]

    def get_statistics(self) -> Dict[str, float]:
        """Get activity statistics"""
        idx, name, activation = self.get_dominant_expert()
        return {
            'dominant_expert': name,
            'dominant_activation': float(activation),
            'entropy': float(-np.sum(self.activations * np.log(self.activations + 1e-8))),
            'max_activation': float(np.max(self.activations)),
            'min_activation': float(np.min(self.activations)),
            'activation_std': float(np.std(self.activations))
        }

    def reset(self):
        """Reset to uniform activation"""
        self.activations = np.ones(self.num_experts, dtype=np.float32) / self.num_experts
        for expert in self.experts:
            expert.activation = 1.0 / self.num_experts
            expert.history = []
        self.history = []


class LearnableCouplingMatrix(nn.Module):
    """
    Learnable coupling matrix W for expert-channel interaction

    W: [num_experts, num_channels] maps expert activations to channel influences
    Used in: Δφ = -λ(ω⊙δ + W^T @ E)
    """

    def __init__(
        self,
        num_experts: int = 5,
        num_channels: int = 3,
        init_scale: float = 0.1
    ):
        """
        Initialize learnable coupling matrix

        Args:
            num_experts: Number of experts (5 for regimes)
            num_channels: Number of oscillator channels (3 for A/B/C)
            init_scale: Scale for random initialization
        """
        super().__init__()
        self.num_experts = num_experts
        self.num_channels = num_channels

        # Learnable W: [num_experts, num_channels]
        # Experts influence channels asymmetrically
        self.W = nn.Parameter(torch.randn(num_experts, num_channels) * init_scale)

        # Initialize with semantic prior (optional)
        self._init_semantic_prior()

    def _init_semantic_prior(self):
        """Initialize with semantic structure"""
        with torch.no_grad():
            # Channel indices: A=0 (Advance), B=1 (Explore), C=2 (Correct)
            # Expert indices: EXPLOIT=0, EXPLORE=1, REPAIR=2, TRANSITION=3, DEADLOCK=4

            # EXPLOIT primarily activates A (Advance)
            self.W.data[0, 0] = 0.3   # EXPLOIT -> A (strong)
            self.W.data[0, 1] = -0.1  # EXPLOIT -> B (suppress exploration)
            self.W.data[0, 2] = 0.0   # EXPLOIT -> C (neutral)

            # EXPLORE primarily activates B (Explore)
            self.W.data[1, 0] = -0.1  # EXPLORE -> A (suppress advance)
            self.W.data[1, 1] = 0.3   # EXPLORE -> B (strong)
            self.W.data[1, 2] = 0.1   # EXPLORE -> C (mild correction)

            # REPAIR primarily activates C (Correct)
            self.W.data[2, 0] = -0.1  # REPAIR -> A (suppress advance)
            self.W.data[2, 1] = 0.0   # REPAIR -> B (neutral)
            self.W.data[2, 2] = 0.3   # REPAIR -> C (strong)

            # TRANSITION - balanced influence
            self.W.data[3, 0] = 0.1
            self.W.data[3, 1] = 0.1
            self.W.data[3, 2] = 0.1

            # DEADLOCK - suppress all channels
            self.W.data[4, 0] = -0.2
            self.W.data[4, 1] = -0.2
            self.W.data[4, 2] = -0.2

    def forward(self, expert_E: torch.Tensor) -> torch.Tensor:
        """
        Compute coupling influence on channels

        Args:
            expert_E: [batch, num_experts] or [num_experts] expert activations

        Returns:
            [batch, num_channels] or [num_channels] coupling influence
        """
        # W^T @ E: [num_channels, num_experts] @ [batch, num_experts, 1] -> [batch, num_channels]
        if expert_E.dim() == 1:
            return self.W.T @ expert_E
        else:
            return torch.einsum('ec,be->bc', self.W, expert_E)

    def get_matrix(self) -> torch.Tensor:
        """Get coupling matrix"""
        return self.W


class LearnableEventProjection(nn.Module):
    """
    Learnable projection from events to channels

    Projects 5 event types to 3 oscillator channels:
    δ_channel = event_proj^T @ δ
    """

    def __init__(
        self,
        num_events: int = 5,
        num_channels: int = 3,
        init_scale: float = 0.1
    ):
        """
        Initialize event projection

        Args:
            num_events: Number of event types (5)
            num_channels: Number of channels (3 for A/B/C)
            init_scale: Initialization scale
        """
        super().__init__()
        self.num_events = num_events
        self.num_channels = num_channels

        # Learnable projection: [num_events, num_channels]
        self.event_proj = nn.Parameter(torch.randn(num_events, num_channels) * init_scale)

        # Initialize with semantic prior
        self._init_semantic_prior()

    def _init_semantic_prior(self):
        """Initialize with semantic structure"""
        with torch.no_grad():
            # Event indices: error=0, goal_near=1, loop=2, novelty=3, timeout=4
            # Channel indices: A=0, B=1, C=2

            # Error -> primarily affects C (Correct)
            self.event_proj.data[0, 0] = -0.2  # error suppresses A
            self.event_proj.data[0, 1] = 0.1   # error triggers exploration
            self.event_proj.data[0, 2] = 0.4   # error strongly triggers C

            # Goal near -> strongly activates A (Advance)
            self.event_proj.data[1, 0] = 0.4   # goal triggers A
            self.event_proj.data[1, 1] = -0.1  # goal suppresses exploration
            self.event_proj.data[1, 2] = 0.0   # goal neutral to C

            # Loop -> triggers exploration (escape loop)
            self.event_proj.data[2, 0] = -0.2  # loop suppresses A
            self.event_proj.data[2, 1] = 0.3   # loop triggers B (explore)
            self.event_proj.data[2, 2] = 0.2   # loop triggers C (correct)

            # Novelty -> triggers exploration
            self.event_proj.data[3, 0] = 0.0   # novelty neutral to A
            self.event_proj.data[3, 1] = 0.4   # novelty strongly triggers B
            self.event_proj.data[3, 2] = 0.1   # novelty mild trigger C

            # Timeout -> triggers correction
            self.event_proj.data[4, 0] = -0.1  # timeout suppresses A
            self.event_proj.data[4, 1] = 0.1   # timeout triggers B
            self.event_proj.data[4, 2] = 0.3   # timeout triggers C

    def forward(self, events: torch.Tensor) -> torch.Tensor:
        """
        Project events to channels

        Args:
            events: [batch, num_events] or [num_events] event vector

        Returns:
            [batch, num_channels] or [num_channels] channel events
        """
        if events.dim() == 1:
            return self.event_proj.T @ events
        else:
            return torch.einsum('ec,be->bc', self.event_proj, events)

    def get_matrix(self) -> torch.Tensor:
        """Get projection matrix"""
        return self.event_proj


if __name__ == "__main__":
    print("=" * 70)
    print("EXPERT ACTIVITY - Testing")
    print("=" * 70)
    print()

    # Test 1: Basic tracker
    print("[1] Testing ExpertActivityTracker...")
    tracker = ExpertActivityTracker()
    print(f"    Initial activations: {tracker.get_activations()}")

    # Update with regime probabilities
    probs = np.array([0.6, 0.2, 0.1, 0.05, 0.05])
    tracker.update_from_regime(probs)
    print(f"    After update: {tracker.get_activations()}")

    idx, name, act = tracker.get_dominant_expert()
    print(f"    Dominant: {name} ({act:.3f})")
    assert name == 'EXPLOIT', "Should be EXPLOIT"
    print("    [OK] Basic tracker working")
    print()

    # Test 2: Coupling matrix
    print("[2] Testing LearnableCouplingMatrix...")
    coupling = LearnableCouplingMatrix()
    E = torch.tensor([0.6, 0.2, 0.1, 0.05, 0.05])
    influence = coupling(E)
    print(f"    E: {E}")
    print(f"    W^T @ E: {influence}")
    print(f"    W shape: {coupling.W.shape}")
    assert influence.shape == (3,), "Should output 3 channels"
    print("    [OK] Coupling matrix working")
    print()

    # Test 3: Event projection
    print("[3] Testing LearnableEventProjection...")
    proj = LearnableEventProjection()
    events = torch.tensor([0.8, 0.0, 0.0, 0.0, 0.0])  # Error only
    channels = proj(events)
    print(f"    Events: {events}")
    print(f"    Projected: {channels}")
    assert channels.shape == (3,), "Should output 3 channels"
    # Error should primarily activate C (index 2)
    print(f"    C channel activation: {channels[2]:.3f}")
    print("    [OK] Event projection working")
    print()

    # Test 4: Batch processing
    print("[4] Testing batch processing...")
    batch_E = torch.randn(4, 5).softmax(dim=-1)
    batch_influence = coupling(batch_E)
    print(f"    Batch E shape: {batch_E.shape}")
    print(f"    Batch influence shape: {batch_influence.shape}")
    assert batch_influence.shape == (4, 3), "Should be (batch, channels)"

    batch_events = torch.rand(4, 5)
    batch_channels = proj(batch_events)
    print(f"    Batch events shape: {batch_events.shape}")
    print(f"    Batch channels shape: {batch_channels.shape}")
    assert batch_channels.shape == (4, 3), "Should be (batch, channels)"
    print("    [OK] Batch processing working")
    print()

    # Test 5: Statistics
    print("[5] Testing statistics...")
    tracker.reset()
    for i in range(10):
        tracker.update_from_dominant(i % 5, confidence=0.7)
    stats = tracker.get_statistics()
    print(f"    Stats: {stats}")
    print("    [OK] Statistics working")
    print()

    print("=" * 70)
    print("EXPERT ACTIVITY TESTS COMPLETE")
    print("=" * 70)
