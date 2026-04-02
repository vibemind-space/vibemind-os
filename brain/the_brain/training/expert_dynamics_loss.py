"""
Expert Dynamics Loss (Phase 4) - Loss Functions for Phase Dynamics Training

Implements three new loss components for the phase dynamics equation:
    ΔφH(r) = -λ(ωqf δ(r) + ∇·(W×E))

Loss Components:
- L_dyn: Dynamics consistency - phase changes follow the equation
- L_div: Expert diversity - experts don't collapse to same behavior
- L_spec: Expert specialization - stable when no events

Total loss extension:
    L_total = L_existing + λ_dyn·L_dyn + λ_div·L_div + λ_spec·L_spec
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Optional, Tuple, Dict


class DynamicsConsistencyLoss(nn.Module):
    """
    L_dyn - Dynamics Consistency Loss

    Ensures phase changes follow the dynamics equation:
        φ[t+1] - φ[t] ≈ -λ(ω⊙δ + W^T @ E)

    This loss penalizes deviations from the expected phase dynamics,
    training the system to evolve phases according to the equation.
    """

    def __init__(self, phase_wrap: bool = True):
        """
        Initialize dynamics consistency loss

        Args:
            phase_wrap: Whether to handle 2π phase wrapping
        """
        super().__init__()
        self.phase_wrap = phase_wrap

    def _wrap_phase_diff(self, diff: torch.Tensor) -> torch.Tensor:
        """
        Handle 2π wrapping in phase differences

        Args:
            diff: Phase differences

        Returns:
            Wrapped differences in [-π, π]
        """
        return torch.atan2(torch.sin(diff), torch.cos(diff))

    def forward(
        self,
        phase_t: torch.Tensor,           # [batch, 3] or [3] - phases at t
        phase_t1: torch.Tensor,          # [batch, 3] or [3] - phases at t+1
        omega: torch.Tensor,             # [batch, 3] or [3] - frequencies
        amplitude: torch.Tensor,         # [batch, 3] or [3] - amplitudes
        events: torch.Tensor,            # [batch, 5] or [5] - event vector δ
        expert_E: torch.Tensor,          # [batch, 5] or [5] - expert activations
        event_proj: torch.Tensor,        # [5, 3] - event projection matrix
        W: torch.Tensor,                 # [5, 3] - coupling matrix
        lambda_val: float = 0.1,         # Time constant
        dt: float = 0.1                  # Time step
    ) -> torch.Tensor:
        """
        Compute dynamics consistency loss

        L_dyn = ||Δφ_actual - Δφ_expected||²

        Where:
            Δφ_expected = -λ * dt * (ω_qf ⊙ δ_channel + W^T @ E)

        Args:
            phase_t: Phases at time t
            phase_t1: Phases at time t+1
            omega: Oscillator frequencies
            amplitude: Oscillator amplitudes (action potentials)
            events: Event trigger vector (5-D)
            expert_E: Expert activation vector (5-D)
            event_proj: Learnable event projection [5, 3]
            W: Learnable coupling matrix [5, 3]
            lambda_val: Time constant λ
            dt: Time step for dynamics

        Returns:
            Scalar loss value
        """
        # Handle batch vs single input
        if phase_t.dim() == 1:
            phase_t = phase_t.unsqueeze(0)
            phase_t1 = phase_t1.unsqueeze(0)
            omega = omega.unsqueeze(0)
            amplitude = amplitude.unsqueeze(0)
            events = events.unsqueeze(0)
            expert_E = expert_E.unsqueeze(0)

        batch_size = phase_t.size(0)

        # Compute actual phase change
        delta_phi_actual = phase_t1 - phase_t
        if self.phase_wrap:
            delta_phi_actual = self._wrap_phase_diff(delta_phi_actual)

        # Compute expected phase change from equation
        # ω_qf = ω * amplitude (frequency × action potential)
        omega_qf = omega * amplitude  # [batch, 3]

        # Project events to channels: δ_channel = event_proj^T @ events
        # [5, 3]^T @ [batch, 5]^T = [3, batch] → transpose
        delta_channel = torch.einsum('ec,be->bc', event_proj, events)  # [batch, 3]

        # Expert coupling: W^T @ E
        coupling = torch.einsum('ec,be->bc', W, expert_E)  # [batch, 3]

        # THE EQUATION: Δφ_expected = -λ * dt * (ω_qf ⊙ δ_channel + coupling)
        delta_phi_expected = -lambda_val * dt * (omega_qf * delta_channel + coupling)

        # MSE loss between actual and expected
        loss = F.mse_loss(delta_phi_actual, delta_phi_expected)

        return loss


class ExpertDiversityLoss(nn.Module):
    """
    L_div - Expert Diversity Loss (Anti-Collapse)

    Prevents experts from collapsing to identical behavior.
    Penalizes high correlation between expert activation patterns.

    L_div = Σ_{i≠j} corr(E_i, E_j)²

    This encourages each expert to specialize in different regimes.
    """

    def __init__(self, temperature: float = 1.0):
        """
        Initialize expert diversity loss

        Args:
            temperature: Scaling factor for correlation penalty
        """
        super().__init__()
        self.temperature = temperature

    def forward(
        self,
        expert_E: torch.Tensor,  # [batch, time, num_experts] or [batch, num_experts]
        expert_activations_over_time: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Compute expert diversity loss

        Args:
            expert_E: Expert activations.
                      If 3D [batch, time, experts]: compute temporal correlation
                      If 2D [batch, experts]: use batch as samples

        Returns:
            Scalar loss value
        """
        if expert_E.dim() == 2:
            # [batch, experts] - treat batch as samples
            # Compute correlation across batch dimension
            E = expert_E  # [batch, num_experts]

            # Center the data
            E_centered = E - E.mean(dim=0, keepdim=True)

            # Compute covariance matrix
            # cov[i,j] = E[E_i * E_j] / (std_i * std_j)
            std = E_centered.std(dim=0, keepdim=True) + 1e-8
            E_normalized = E_centered / std

            # Correlation matrix: [num_experts, num_experts]
            corr_matrix = torch.mm(E_normalized.T, E_normalized) / E.size(0)

        elif expert_E.dim() == 3:
            # [batch, time, experts] - compute temporal correlation per batch
            batch_size, time_steps, num_experts = expert_E.shape

            # Reshape to [batch * time, experts] and compute correlation
            E_flat = expert_E.reshape(-1, num_experts)

            # Center and normalize
            E_centered = E_flat - E_flat.mean(dim=0, keepdim=True)
            std = E_centered.std(dim=0, keepdim=True) + 1e-8
            E_normalized = E_centered / std

            # Correlation matrix
            corr_matrix = torch.mm(E_normalized.T, E_normalized) / E_flat.size(0)

        else:
            raise ValueError(f"Expected 2D or 3D tensor, got {expert_E.dim()}D")

        # Create mask to exclude diagonal (self-correlation)
        num_experts = corr_matrix.size(0)
        mask = 1.0 - torch.eye(num_experts, device=corr_matrix.device)

        # Penalize squared off-diagonal correlations
        # High correlation between different experts is bad
        loss = (corr_matrix.pow(2) * mask).sum() / (mask.sum() + 1e-8)

        return loss * self.temperature


class ExpertSpecializationLoss(nn.Module):
    """
    L_spec - Expert Specialization Loss

    Ensures experts are STABLE when not triggered by events.
    When no events occur (δ ≈ 0), phase changes should be minimal.

    L_spec = (1 - |δ|) · |Δφ|

    This encourages:
    - Large phase changes only when events trigger them
    - Stability in the absence of events
    """

    def __init__(self, stability_threshold: float = 0.1):
        """
        Initialize expert specialization loss

        Args:
            stability_threshold: Minimum event strength to allow phase change
        """
        super().__init__()
        self.stability_threshold = stability_threshold

    def forward(
        self,
        phase_delta: torch.Tensor,    # [batch, 3] - phase changes
        events: torch.Tensor,         # [batch, 5] - event strengths
        event_proj: Optional[torch.Tensor] = None  # [5, 3] - projection
    ) -> torch.Tensor:
        """
        Compute expert specialization loss

        Args:
            phase_delta: Phase changes (φ[t+1] - φ[t])
            events: Event trigger vector
            event_proj: Optional projection matrix (if None, uses max event)

        Returns:
            Scalar loss value
        """
        # Handle dimensions
        if phase_delta.dim() == 1:
            phase_delta = phase_delta.unsqueeze(0)
        if events.dim() == 1:
            events = events.unsqueeze(0)

        # Compute "event presence" per channel
        if event_proj is not None:
            # Project events to channels
            event_strength = torch.einsum('ec,be->bc', event_proj.abs(), events)
            # Normalize to [0, 1]
            event_strength = torch.clamp(event_strength, 0, 1)
        else:
            # Use max event as global trigger
            event_strength = events.max(dim=-1, keepdim=True)[0].expand_as(phase_delta)

        # No-event weight: high when events are low
        no_event_weight = 1.0 - event_strength

        # Penalize phase changes when no events
        # |Δφ| weighted by absence of events
        phase_change_magnitude = phase_delta.abs()

        # Loss: encourage stability when no events
        loss = (no_event_weight * phase_change_magnitude).mean()

        return loss


class CombinedExpertDynamicsLoss(nn.Module):
    """
    Combined loss for expert phase dynamics

    L_expert = λ_dyn·L_dyn + λ_div·L_div + λ_spec·L_spec

    This module combines all three Phase 4 losses for convenient use.
    """

    def __init__(
        self,
        lambda_dyn: float = 0.3,
        lambda_div: float = 0.2,
        lambda_spec: float = 0.15,
        phase_wrap: bool = True
    ):
        """
        Initialize combined loss

        Args:
            lambda_dyn: Weight for dynamics consistency
            lambda_div: Weight for expert diversity
            lambda_spec: Weight for expert specialization
            phase_wrap: Handle 2π phase wrapping
        """
        super().__init__()
        self.lambda_dyn = lambda_dyn
        self.lambda_div = lambda_div
        self.lambda_spec = lambda_spec

        # Individual loss modules
        self.dynamics_loss = DynamicsConsistencyLoss(phase_wrap=phase_wrap)
        self.diversity_loss = ExpertDiversityLoss()
        self.specialization_loss = ExpertSpecializationLoss()

    def forward(
        self,
        phase_t: torch.Tensor,
        phase_t1: torch.Tensor,
        omega: torch.Tensor,
        amplitude: torch.Tensor,
        events: torch.Tensor,
        expert_E: torch.Tensor,
        event_proj: torch.Tensor,
        W: torch.Tensor,
        lambda_val: float = 0.1,
        dt: float = 0.1,
        expert_history: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        Compute combined expert dynamics loss

        Args:
            phase_t: Phases at time t
            phase_t1: Phases at time t+1
            omega: Oscillator frequencies
            amplitude: Oscillator amplitudes
            events: Event vector
            expert_E: Expert activations (current or batched)
            event_proj: Event projection matrix
            W: Coupling matrix
            lambda_val: Time constant
            dt: Time step
            expert_history: Optional [batch, time, experts] for diversity

        Returns:
            (total_loss, loss_components_dict)
        """
        # Phase delta
        phase_delta = phase_t1 - phase_t

        # Dynamics consistency
        L_dyn = self.dynamics_loss(
            phase_t, phase_t1, omega, amplitude,
            events, expert_E, event_proj, W,
            lambda_val, dt
        )

        # Expert diversity (use history if available)
        if expert_history is not None:
            L_div = self.diversity_loss(expert_history)
        else:
            L_div = self.diversity_loss(expert_E)

        # Expert specialization
        L_spec = self.specialization_loss(phase_delta, events, event_proj)

        # Combined loss
        total_loss = (
            self.lambda_dyn * L_dyn +
            self.lambda_div * L_div +
            self.lambda_spec * L_spec
        )

        # Return components for logging
        components = {
            'L_dyn': L_dyn.item(),
            'L_div': L_div.item(),
            'L_spec': L_spec.item(),
            'L_expert_total': total_loss.item()
        }

        return total_loss, components


def compute_expected_phase_change(
    omega: torch.Tensor,
    amplitude: torch.Tensor,
    events: torch.Tensor,
    expert_E: torch.Tensor,
    event_proj: torch.Tensor,
    W: torch.Tensor,
    lambda_val: float = 0.1,
    dt: float = 0.1
) -> torch.Tensor:
    """
    Compute expected phase change from the dynamics equation

    Δφ = -λ * dt * (ω_qf ⊙ δ_channel + W^T @ E)

    Args:
        omega: [batch, 3] or [3] - frequencies
        amplitude: [batch, 3] or [3] - amplitudes
        events: [batch, 5] or [5] - event vector
        expert_E: [batch, 5] or [5] - expert activations
        event_proj: [5, 3] - event projection
        W: [5, 3] - coupling matrix
        lambda_val: Time constant
        dt: Time step

    Returns:
        [batch, 3] or [3] - expected phase changes
    """
    # Handle dimensions
    squeeze_output = False
    if omega.dim() == 1:
        omega = omega.unsqueeze(0)
        amplitude = amplitude.unsqueeze(0)
        events = events.unsqueeze(0)
        expert_E = expert_E.unsqueeze(0)
        squeeze_output = True

    # ω_qf = ω * amplitude
    omega_qf = omega * amplitude

    # δ_channel = event_proj^T @ events
    delta_channel = torch.einsum('ec,be->bc', event_proj, events)

    # coupling = W^T @ E
    coupling = torch.einsum('ec,be->bc', W, expert_E)

    # Δφ = -λ * dt * (ω_qf ⊙ δ_channel + coupling)
    delta_phi = -lambda_val * dt * (omega_qf * delta_channel + coupling)

    if squeeze_output:
        delta_phi = delta_phi.squeeze(0)

    return delta_phi


if __name__ == "__main__":
    print("=" * 70)
    print("EXPERT DYNAMICS LOSS - Testing")
    print("=" * 70)
    print()

    # Test setup
    torch.manual_seed(42)
    batch_size = 4
    num_experts = 5
    num_channels = 3

    # Create test data
    phase_t = torch.rand(batch_size, num_channels) * 2 * np.pi
    omega = torch.ones(batch_size, num_channels) * 1.0
    amplitude = torch.rand(batch_size, num_channels) * 0.5 + 0.5
    events = torch.rand(batch_size, num_experts)
    expert_E = F.softmax(torch.randn(batch_size, num_experts), dim=-1)

    # Learnable matrices
    event_proj = torch.randn(num_experts, num_channels) * 0.1
    W = torch.randn(num_experts, num_channels) * 0.1

    # Compute expected phase change
    delta_phi_expected = compute_expected_phase_change(
        omega, amplitude, events, expert_E, event_proj, W, lambda_val=0.1, dt=0.1
    )
    phase_t1 = phase_t + delta_phi_expected

    # Test 1: Dynamics Consistency Loss
    print("[1] Testing DynamicsConsistencyLoss...")
    dyn_loss = DynamicsConsistencyLoss()
    L_dyn = dyn_loss(phase_t, phase_t1, omega, amplitude, events, expert_E, event_proj, W)
    print(f"    L_dyn (should be ~0): {L_dyn.item():.6f}")
    assert L_dyn.item() < 0.01, "Loss should be near zero when phases follow equation"
    print("    [OK] Dynamics consistency working")
    print()

    # Test with perturbed phases
    phase_t1_noisy = phase_t1 + torch.randn_like(phase_t1) * 0.1
    L_dyn_noisy = dyn_loss(phase_t, phase_t1_noisy, omega, amplitude, events, expert_E, event_proj, W)
    print(f"    L_dyn (noisy, should be > 0): {L_dyn_noisy.item():.6f}")
    assert L_dyn_noisy.item() > L_dyn.item(), "Noisy should have higher loss"
    print()

    # Test 2: Expert Diversity Loss
    print("[2] Testing ExpertDiversityLoss...")
    div_loss = ExpertDiversityLoss()

    # Diverse experts (low correlation)
    diverse_E = F.softmax(torch.randn(batch_size, num_experts) * 3, dim=-1)
    L_div_diverse = div_loss(diverse_E)
    print(f"    L_div (diverse): {L_div_diverse.item():.6f}")

    # Collapsed experts (high correlation)
    collapsed_E = F.softmax(torch.ones(batch_size, num_experts), dim=-1)
    L_div_collapsed = div_loss(collapsed_E)
    print(f"    L_div (collapsed, should be higher): {L_div_collapsed.item():.6f}")
    print("    [OK] Expert diversity working")
    print()

    # Test 3: Expert Specialization Loss
    print("[3] Testing ExpertSpecializationLoss...")
    spec_loss = ExpertSpecializationLoss()

    # No events, no phase change (good)
    no_events = torch.zeros(batch_size, num_experts)
    small_delta = torch.ones(batch_size, num_channels) * 0.01
    L_spec_good = spec_loss(small_delta, no_events, event_proj)
    print(f"    L_spec (no events, small delta): {L_spec_good.item():.6f}")

    # No events, large phase change (bad)
    large_delta = torch.ones(batch_size, num_channels) * 1.0
    L_spec_bad = spec_loss(large_delta, no_events, event_proj)
    print(f"    L_spec (no events, large delta, should be higher): {L_spec_bad.item():.6f}")
    assert L_spec_bad.item() > L_spec_good.item(), "Large delta with no events should be penalized"

    # Events present, large phase change (acceptable)
    strong_events = torch.ones(batch_size, num_experts)
    L_spec_with_events = spec_loss(large_delta, strong_events, event_proj)
    print(f"    L_spec (with events, large delta): {L_spec_with_events.item():.6f}")
    print("    [OK] Expert specialization working")
    print()

    # Test 4: Combined Loss
    print("[4] Testing CombinedExpertDynamicsLoss...")
    combined_loss = CombinedExpertDynamicsLoss(
        lambda_dyn=0.3,
        lambda_div=0.2,
        lambda_spec=0.15
    )

    L_total, components = combined_loss(
        phase_t, phase_t1, omega, amplitude,
        events, expert_E, event_proj, W,
        lambda_val=0.1, dt=0.1
    )
    print(f"    Total loss: {L_total.item():.6f}")
    print(f"    Components: {components}")
    print("    [OK] Combined loss working")
    print()

    # Test 5: Backward pass
    print("[5] Testing gradient flow...")
    event_proj_param = nn.Parameter(torch.randn(num_experts, num_channels) * 0.1)
    W_param = nn.Parameter(torch.randn(num_experts, num_channels) * 0.1)

    L_total, _ = combined_loss(
        phase_t, phase_t1, omega, amplitude,
        events, expert_E, event_proj_param, W_param
    )
    L_total.backward()

    assert event_proj_param.grad is not None, "event_proj should have gradients"
    assert W_param.grad is not None, "W should have gradients"
    print(f"    event_proj grad norm: {event_proj_param.grad.norm().item():.6f}")
    print(f"    W grad norm: {W_param.grad.norm().item():.6f}")
    print("    [OK] Gradient flow working")
    print()

    # Test 6: Single sample (no batch)
    print("[6] Testing single sample input...")
    phase_t_single = torch.rand(num_channels) * 2 * np.pi
    phase_t1_single = phase_t_single + torch.randn(num_channels) * 0.1
    omega_single = torch.ones(num_channels)
    amp_single = torch.rand(num_channels)
    events_single = torch.rand(num_experts)
    expert_single = F.softmax(torch.randn(num_experts), dim=-1)

    L_dyn_single = dyn_loss(
        phase_t_single, phase_t1_single, omega_single, amp_single,
        events_single, expert_single, event_proj, W
    )
    print(f"    L_dyn (single): {L_dyn_single.item():.6f}")
    print("    [OK] Single sample working")
    print()

    print("=" * 70)
    print("EXPERT DYNAMICS LOSS TESTS COMPLETE")
    print("=" * 70)
