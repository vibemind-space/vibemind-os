"""
Phase-Locking Loss Functions for Temporal CTM Training

Novel loss functions for training oscillator-based temporal control:
- PhaseLockingLoss: Penalize phase drift when lock expected
- RegimeLoss: Cross-entropy on regime classification
- TransitionSmoothnessLoss: Penalize sudden regime jumps

Phase 4 Extensions (Expert Phase Dynamics):
- DynamicsConsistencyLoss: Phase changes follow ΔφH(r) = -λ(ωqf δ(r) + ∇·(W×E))
- ExpertDiversityLoss: Prevent expert collapse
- ExpertSpecializationLoss: Stability when no events

These losses enforce phase synchronization patterns:
- EXPLOIT: A-B in-phase (lock=1.0), A-C in-phase
- EXPLORE: B dominant, A-C anti-phase (lock=-1.0)
- REPAIR: C dominant, A-B-C converging
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Phase 4 imports
try:
    from .expert_dynamics_loss import (
        DynamicsConsistencyLoss,
        ExpertDiversityLoss,
        ExpertSpecializationLoss,
        CombinedExpertDynamicsLoss
    )
    PHASE4_AVAILABLE = True
except ImportError:
    PHASE4_AVAILABLE = False


class Regime(Enum):
    """Operational regimes (must match core/regime_detector.py)"""
    EXPLOIT = "exploit"
    EXPLORE = "explore"
    REPAIR = "repair"
    TRANSITION = "transition"
    DEADLOCK = "deadlock"


@dataclass
class PhaseLockTarget:
    """Target phase-locking pattern for a regime"""
    regime: Regime
    ab_lock: float  # Target cos(theta_A - theta_B): 1.0=in-phase, -1.0=anti-phase, 0.0=free
    ac_lock: float  # Target cos(theta_A - theta_C)
    bc_lock: float  # Target cos(theta_B - theta_C)
    weight: float = 1.0  # Importance weight


# Define target phase-lock patterns for each regime
REGIME_PHASE_LOCKS = {
    Regime.EXPLOIT: PhaseLockTarget(
        regime=Regime.EXPLOIT,
        ab_lock=1.0,    # A-B in-phase (exploit together)
        ac_lock=1.0,    # A-C in-phase
        bc_lock=1.0,    # B-C in-phase (all synchronized)
        weight=1.0
    ),
    Regime.EXPLORE: PhaseLockTarget(
        regime=Regime.EXPLORE,
        ab_lock=0.0,    # A-B free (B exploring independently)
        ac_lock=-1.0,   # A-C anti-phase (A suppressed during explore)
        bc_lock=0.0,    # B-C free
        weight=1.0
    ),
    Regime.REPAIR: PhaseLockTarget(
        regime=Regime.REPAIR,
        ab_lock=0.5,    # A-B partially locked (converging)
        ac_lock=1.0,    # A-C in-phase (C leads correction)
        bc_lock=0.5,    # B-C partially locked
        weight=1.0
    ),
    Regime.TRANSITION: PhaseLockTarget(
        regime=Regime.TRANSITION,
        ab_lock=0.0,    # No lock expected
        ac_lock=0.0,
        bc_lock=0.0,
        weight=0.5      # Lower weight during transitions
    ),
    Regime.DEADLOCK: PhaseLockTarget(
        regime=Regime.DEADLOCK,
        ab_lock=0.0,    # All free (drifting)
        ac_lock=0.0,
        bc_lock=0.0,
        weight=0.3      # Lowest weight for deadlock
    ),
}


class PhaseLockingLoss(nn.Module):
    """
    Phase-locking loss for oscillator synchronization

    Penalizes deviation from target phase relationships based on regime.

    L_phase_lock = Σ_pairs w_pair * ||cos(Δθ_ij) - target_lock_ij||²

    The synchrony vector has 9 components:
    [|A|, |B|, |C|, cos(ΔAB), sin(ΔAB), cos(ΔAC), sin(ΔAC), cos(ΔBC), sin(ΔBC)]

    We use indices 3, 5, 7 for the cosine terms (phase differences).
    """

    def __init__(self):
        super().__init__()
        # Index mapping for synchrony vector
        self.cos_ab_idx = 3
        self.cos_ac_idx = 5
        self.cos_bc_idx = 7

    def forward(
        self,
        sync_vectors: torch.Tensor,
        target_regimes: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute phase-locking loss

        Args:
            sync_vectors: [batch, 9] synchrony vectors
            target_regimes: [batch] integer regime indices (0-4)

        Returns:
            Scalar loss value
        """
        batch_size = sync_vectors.shape[0]
        device = sync_vectors.device

        # Extract cosine phase differences
        cos_ab = sync_vectors[:, self.cos_ab_idx]
        cos_ac = sync_vectors[:, self.cos_ac_idx]
        cos_bc = sync_vectors[:, self.cos_bc_idx]

        # Build target tensors based on regimes
        target_ab = torch.zeros(batch_size, device=device)
        target_ac = torch.zeros(batch_size, device=device)
        target_bc = torch.zeros(batch_size, device=device)
        weights = torch.ones(batch_size, device=device)

        # Map regime indices to targets
        regime_list = list(Regime)
        for i, regime in enumerate(regime_list):
            mask = (target_regimes == i)
            if mask.any():
                lock_target = REGIME_PHASE_LOCKS[regime]
                target_ab[mask] = lock_target.ab_lock
                target_ac[mask] = lock_target.ac_lock
                target_bc[mask] = lock_target.bc_lock
                weights[mask] = lock_target.weight

        # Compute MSE loss for each pair
        loss_ab = F.mse_loss(cos_ab, target_ab, reduction='none')
        loss_ac = F.mse_loss(cos_ac, target_ac, reduction='none')
        loss_bc = F.mse_loss(cos_bc, target_bc, reduction='none')

        # Weighted sum
        total_loss = weights * (loss_ab + loss_ac + loss_bc)

        return total_loss.mean()

    def get_targets_for_regime(self, regime: Regime) -> Tuple[float, float, float]:
        """Get target phase locks for a regime"""
        lock_target = REGIME_PHASE_LOCKS[regime]
        return lock_target.ab_lock, lock_target.ac_lock, lock_target.bc_lock


class RegimeClassificationLoss(nn.Module):
    """
    Cross-entropy loss for regime classification

    Predicts which regime the system should be in based on state.
    """

    def __init__(self, num_regimes: int = 5):
        super().__init__()
        self.num_regimes = num_regimes
        self.ce_loss = nn.CrossEntropyLoss()

    def forward(
        self,
        regime_logits: torch.Tensor,
        target_regimes: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute regime classification loss

        Args:
            regime_logits: [batch, num_regimes] logits
            target_regimes: [batch] integer regime indices

        Returns:
            Scalar loss value
        """
        return self.ce_loss(regime_logits, target_regimes)


class TransitionSmoothnessLoss(nn.Module):
    """
    Transition smoothness loss

    Penalizes sudden regime changes when no transition is expected.
    Encourages smooth regime evolution.
    """

    def __init__(self, smoothness_weight: float = 0.1):
        super().__init__()
        self.smoothness_weight = smoothness_weight

    def forward(
        self,
        regime_probs: torch.Tensor,
        prev_regime_probs: Optional[torch.Tensor] = None,
        transition_expected: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Compute transition smoothness loss

        Args:
            regime_probs: [batch, num_regimes] current regime probabilities
            prev_regime_probs: [batch, num_regimes] previous regime probabilities
            transition_expected: [batch] boolean mask where transition is expected

        Returns:
            Scalar loss value
        """
        if prev_regime_probs is None:
            return torch.tensor(0.0, device=regime_probs.device)

        # Compute KL divergence between consecutive regime distributions
        kl_div = F.kl_div(
            F.log_softmax(regime_probs, dim=-1),
            F.softmax(prev_regime_probs, dim=-1),
            reduction='none'
        ).sum(dim=-1)

        # Only penalize when transition is NOT expected
        if transition_expected is not None:
            # Where transition is expected, set loss to 0
            kl_div = kl_div * (~transition_expected).float()

        return self.smoothness_weight * kl_div.mean()


class TemporalCTMLoss(nn.Module):
    """
    Combined loss for Temporal CTM training

    L_total = λ_action · L_action
            + λ_timing · L_timing
            + λ_regime · L_regime
            + λ_lock   · L_phase_lock
            + λ_trans  · L_transition
    """

    def __init__(
        self,
        num_cells: int = 24,
        num_regimes: int = 5,
        lambda_action: float = 1.0,
        lambda_timing: float = 0.5,
        lambda_regime: float = 0.3,
        lambda_lock: float = 0.2,
        lambda_trans: float = 0.1
    ):
        super().__init__()

        # Loss weights
        self.lambda_action = lambda_action
        self.lambda_timing = lambda_timing
        self.lambda_regime = lambda_regime
        self.lambda_lock = lambda_lock
        self.lambda_trans = lambda_trans

        # Component losses
        self.action_loss = nn.CrossEntropyLoss()
        self.timing_loss = nn.BCEWithLogitsLoss()
        self.regime_loss = RegimeClassificationLoss(num_regimes)
        self.phase_lock_loss = PhaseLockingLoss()
        self.transition_loss = TransitionSmoothnessLoss()

    def forward(
        self,
        cell_logits: torch.Tensor,
        timing_logits: torch.Tensor,
        regime_logits: torch.Tensor,
        sync_vectors: torch.Tensor,
        target_cells: torch.Tensor,
        target_timing: torch.Tensor,
        target_regimes: torch.Tensor,
        prev_regime_probs: Optional[torch.Tensor] = None,
        transition_expected: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Compute total loss and components

        Args:
            cell_logits: [batch, num_cells] action logits
            timing_logits: [batch, 1] timing gate logits
            regime_logits: [batch, num_regimes] regime logits
            sync_vectors: [batch, 9] synchrony vectors
            target_cells: [batch] target drumpad cells
            target_timing: [batch] target should_act (0 or 1)
            target_regimes: [batch] target regime indices
            prev_regime_probs: [batch, num_regimes] previous regime probs
            transition_expected: [batch] boolean mask

        Returns:
            Dict with 'total' and component losses
        """
        # Action loss (drumpad cell selection)
        L_action = self.action_loss(cell_logits, target_cells)

        # Timing loss (when to act)
        L_timing = self.timing_loss(
            timing_logits.squeeze(-1),
            target_timing.float()
        )

        # Regime classification loss
        L_regime = self.regime_loss(regime_logits, target_regimes)

        # Phase-locking loss
        L_lock = self.phase_lock_loss(sync_vectors, target_regimes)

        # Transition smoothness loss
        regime_probs = F.softmax(regime_logits, dim=-1)
        L_trans = self.transition_loss(
            regime_probs,
            prev_regime_probs,
            transition_expected
        )

        # Total loss
        total = (
            self.lambda_action * L_action +
            self.lambda_timing * L_timing +
            self.lambda_regime * L_regime +
            self.lambda_lock * L_lock +
            self.lambda_trans * L_trans
        )

        return {
            'total': total,
            'action': L_action,
            'timing': L_timing,
            'regime': L_regime,
            'phase_lock': L_lock,
            'transition': L_trans
        }


class ExtendedTemporalCTMLoss(nn.Module):
    """
    Extended loss for Temporal CTM training with Phase 4 expert dynamics

    L_total = L_base (5 terms)
            + λ_dyn  · L_dyn       # Dynamics consistency
            + λ_div  · L_div       # Expert diversity
            + λ_spec · L_spec      # Expert specialization

    Where L_base includes:
        λ_action · L_action
        λ_timing · L_timing
        λ_regime · L_regime
        λ_lock   · L_phase_lock
        λ_trans  · L_transition
    """

    def __init__(
        self,
        num_cells: int = 24,
        num_regimes: int = 5,
        # Base loss weights
        lambda_action: float = 1.0,
        lambda_timing: float = 0.5,
        lambda_regime: float = 0.3,
        lambda_lock: float = 0.2,
        lambda_trans: float = 0.1,
        # Phase 4 loss weights
        lambda_dyn: float = 0.3,
        lambda_div: float = 0.2,
        lambda_spec: float = 0.15,
        # Phase 4 settings
        phase_wrap: bool = True
    ):
        super().__init__()

        if not PHASE4_AVAILABLE:
            raise ImportError("Phase 4 expert_dynamics_loss module not available")

        # Base loss (Phase 2)
        self.base_loss = TemporalCTMLoss(
            num_cells=num_cells,
            num_regimes=num_regimes,
            lambda_action=lambda_action,
            lambda_timing=lambda_timing,
            lambda_regime=lambda_regime,
            lambda_lock=lambda_lock,
            lambda_trans=lambda_trans
        )

        # Phase 4 losses
        self.lambda_dyn = lambda_dyn
        self.lambda_div = lambda_div
        self.lambda_spec = lambda_spec

        self.dynamics_loss = DynamicsConsistencyLoss(phase_wrap=phase_wrap)
        self.diversity_loss = ExpertDiversityLoss()
        self.specialization_loss = ExpertSpecializationLoss()

    def forward(
        self,
        # Base loss inputs
        cell_logits: torch.Tensor,
        timing_logits: torch.Tensor,
        regime_logits: torch.Tensor,
        sync_vectors: torch.Tensor,
        target_cells: torch.Tensor,
        target_timing: torch.Tensor,
        target_regimes: torch.Tensor,
        # Phase 4 inputs
        phase_t: Optional[torch.Tensor] = None,
        phase_t1: Optional[torch.Tensor] = None,
        omega: Optional[torch.Tensor] = None,
        amplitude: Optional[torch.Tensor] = None,
        events: Optional[torch.Tensor] = None,
        expert_E: Optional[torch.Tensor] = None,
        event_proj: Optional[torch.Tensor] = None,
        W: Optional[torch.Tensor] = None,
        lambda_val: float = 0.1,
        dt: float = 0.1,
        # Optional
        prev_regime_probs: Optional[torch.Tensor] = None,
        transition_expected: Optional[torch.Tensor] = None,
        expert_history: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Compute total loss including Phase 4 expert dynamics

        Args:
            cell_logits: [batch, num_cells] action logits
            timing_logits: [batch, 1] timing gate logits
            regime_logits: [batch, num_regimes] regime logits
            sync_vectors: [batch, 9] synchrony vectors
            target_cells: [batch] target drumpad cells
            target_timing: [batch] target should_act
            target_regimes: [batch] target regime indices
            phase_t: [batch, 3] phases at time t
            phase_t1: [batch, 3] phases at time t+1
            omega: [batch, 3] oscillator frequencies
            amplitude: [batch, 3] oscillator amplitudes
            events: [batch, 5] event vector
            expert_E: [batch, 5] expert activations
            event_proj: [5, 3] event projection matrix
            W: [5, 3] coupling matrix
            lambda_val: Time constant λ
            dt: Time step
            prev_regime_probs: [batch, num_regimes] previous regime probs
            transition_expected: [batch] boolean mask
            expert_history: [batch, time, 5] expert history for diversity

        Returns:
            Dict with 'total' and all component losses
        """
        # Compute base losses
        losses = self.base_loss(
            cell_logits, timing_logits, regime_logits, sync_vectors,
            target_cells, target_timing, target_regimes,
            prev_regime_probs, transition_expected
        )

        total = losses['total']

        # Phase 4 losses (if inputs provided)
        L_dyn = torch.tensor(0.0, device=total.device)
        L_div = torch.tensor(0.0, device=total.device)
        L_spec = torch.tensor(0.0, device=total.device)

        # Dynamics consistency loss
        if all(x is not None for x in [phase_t, phase_t1, omega, amplitude, events, expert_E, event_proj, W]):
            L_dyn = self.dynamics_loss(
                phase_t, phase_t1, omega, amplitude,
                events, expert_E, event_proj, W,
                lambda_val, dt
            )
            total = total + self.lambda_dyn * L_dyn

        # Expert diversity loss
        if expert_E is not None:
            if expert_history is not None:
                L_div = self.diversity_loss(expert_history)
            else:
                L_div = self.diversity_loss(expert_E)
            total = total + self.lambda_div * L_div

        # Expert specialization loss
        if phase_t is not None and phase_t1 is not None and events is not None:
            phase_delta = phase_t1 - phase_t
            L_spec = self.specialization_loss(phase_delta, events, event_proj)
            total = total + self.lambda_spec * L_spec

        # Update total and add new losses
        losses['total'] = total
        losses['dynamics'] = L_dyn
        losses['diversity'] = L_div
        losses['specialization'] = L_spec

        return losses

    def get_loss_weights(self) -> Dict[str, float]:
        """Get all loss weights for logging"""
        return {
            'lambda_action': self.base_loss.lambda_action,
            'lambda_timing': self.base_loss.lambda_timing,
            'lambda_regime': self.base_loss.lambda_regime,
            'lambda_lock': self.base_loss.lambda_lock,
            'lambda_trans': self.base_loss.lambda_trans,
            'lambda_dyn': self.lambda_dyn,
            'lambda_div': self.lambda_div,
            'lambda_spec': self.lambda_spec
        }


if __name__ == "__main__":
    print("=" * 70)
    print("PHASE-LOCKING LOSS - Testing")
    print("=" * 70)
    print()

    # Test PhaseLockingLoss
    print("[1] Testing PhaseLockingLoss...")
    phase_loss = PhaseLockingLoss()

    # Create test synchrony vectors
    # [|A|, |B|, |C|, cos(ΔAB), sin(ΔAB), cos(ΔAC), sin(ΔAC), cos(ΔBC), sin(ΔBC)]
    sync_exploit = torch.tensor([[0.8, 0.2, 0.1, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]])  # All in-phase
    sync_explore = torch.tensor([[0.2, 0.8, 0.1, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0]])  # A-C anti-phase
    sync_wrong = torch.tensor([[0.8, 0.2, 0.1, -1.0, 0.0, -1.0, 0.0, -1.0, 0.0]])  # Wrong for EXPLOIT

    # Test EXPLOIT regime (index 0)
    target_exploit = torch.tensor([0])
    loss_correct = phase_loss(sync_exploit, target_exploit)
    loss_wrong = phase_loss(sync_wrong, target_exploit)
    print(f"    EXPLOIT regime - correct sync: loss={loss_correct.item():.4f}")
    print(f"    EXPLOIT regime - wrong sync: loss={loss_wrong.item():.4f}")
    print(f"    [OK] Wrong sync has higher loss: {loss_wrong > loss_correct}")
    print()

    # Test TemporalCTMLoss
    print("[2] Testing TemporalCTMLoss...")
    combined_loss = TemporalCTMLoss(num_cells=24, num_regimes=5)

    batch_size = 4
    cell_logits = torch.randn(batch_size, 24)
    timing_logits = torch.randn(batch_size, 1)
    regime_logits = torch.randn(batch_size, 5)
    sync_vectors = torch.rand(batch_size, 9) * 2 - 1  # Random in [-1, 1]

    target_cells = torch.randint(0, 24, (batch_size,))
    target_timing = torch.randint(0, 2, (batch_size,))
    target_regimes = torch.randint(0, 5, (batch_size,))

    losses = combined_loss(
        cell_logits, timing_logits, regime_logits, sync_vectors,
        target_cells, target_timing, target_regimes
    )

    print(f"    Total loss: {losses['total'].item():.4f}")
    print(f"    Action loss: {losses['action'].item():.4f}")
    print(f"    Timing loss: {losses['timing'].item():.4f}")
    print(f"    Regime loss: {losses['regime'].item():.4f}")
    print(f"    Phase-lock loss: {losses['phase_lock'].item():.4f}")
    print(f"    Transition loss: {losses['transition'].item():.4f}")
    print("    [OK] All losses computed")
    print()

    # Test gradient flow
    print("[3] Testing gradient flow...")
    cell_logits.requires_grad = True
    timing_logits.requires_grad = True
    regime_logits.requires_grad = True

    losses = combined_loss(
        cell_logits, timing_logits, regime_logits, sync_vectors,
        target_cells, target_timing, target_regimes
    )
    losses['total'].backward()

    print(f"    cell_logits.grad exists: {cell_logits.grad is not None}")
    print(f"    timing_logits.grad exists: {timing_logits.grad is not None}")
    print(f"    regime_logits.grad exists: {regime_logits.grad is not None}")
    print("    [OK] Gradients flow correctly")
    print()

    # Test ExtendedTemporalCTMLoss (Phase 4)
    if PHASE4_AVAILABLE:
        print("[4] Testing ExtendedTemporalCTMLoss (Phase 4)...")
        extended_loss = ExtendedTemporalCTMLoss(
            num_cells=24,
            num_regimes=5,
            lambda_dyn=0.3,
            lambda_div=0.2,
            lambda_spec=0.15
        )

        # Create Phase 4 inputs
        batch_size = 4
        phase_t = torch.rand(batch_size, 3) * 2 * np.pi
        phase_t1 = phase_t + torch.randn(batch_size, 3) * 0.1
        omega = torch.ones(batch_size, 3)
        amplitude = torch.rand(batch_size, 3) * 0.5 + 0.5
        events = torch.rand(batch_size, 5)
        expert_E = F.softmax(torch.randn(batch_size, 5), dim=-1)
        event_proj = torch.randn(5, 3) * 0.1
        W = torch.randn(5, 3) * 0.1

        # Reset logits for gradient test
        cell_logits = torch.randn(batch_size, 24, requires_grad=True)
        timing_logits = torch.randn(batch_size, 1, requires_grad=True)
        regime_logits = torch.randn(batch_size, 5, requires_grad=True)
        sync_vectors = torch.rand(batch_size, 9) * 2 - 1
        target_cells = torch.randint(0, 24, (batch_size,))
        target_timing = torch.randint(0, 2, (batch_size,))
        target_regimes = torch.randint(0, 5, (batch_size,))

        losses = extended_loss(
            cell_logits, timing_logits, regime_logits, sync_vectors,
            target_cells, target_timing, target_regimes,
            phase_t=phase_t, phase_t1=phase_t1,
            omega=omega, amplitude=amplitude,
            events=events, expert_E=expert_E,
            event_proj=event_proj, W=W
        )

        print(f"    Total loss: {losses['total'].item():.4f}")
        print(f"    Base losses: action={losses['action'].item():.4f}, timing={losses['timing'].item():.4f}")
        print(f"    Phase 4 losses:")
        print(f"        dynamics: {losses['dynamics'].item():.4f}")
        print(f"        diversity: {losses['diversity'].item():.4f}")
        print(f"        specialization: {losses['specialization'].item():.4f}")
        print("    [OK] Extended loss working")
        print()

        # Test gradient flow for Phase 4
        print("[5] Testing Phase 4 gradient flow...")
        event_proj_param = nn.Parameter(torch.randn(5, 3) * 0.1)
        W_param = nn.Parameter(torch.randn(5, 3) * 0.1)

        losses = extended_loss(
            cell_logits, timing_logits, regime_logits, sync_vectors,
            target_cells, target_timing, target_regimes,
            phase_t=phase_t, phase_t1=phase_t1,
            omega=omega, amplitude=amplitude,
            events=events, expert_E=expert_E,
            event_proj=event_proj_param, W=W_param
        )
        losses['total'].backward()

        print(f"    event_proj.grad norm: {event_proj_param.grad.norm().item():.6f}")
        print(f"    W.grad norm: {W_param.grad.norm().item():.6f}")
        print("    [OK] Phase 4 gradients flow correctly")
        print()

        # Print loss weights
        print("[6] Loss weights...")
        weights = extended_loss.get_loss_weights()
        for k, v in weights.items():
            print(f"    {k}: {v}")
        print("    [OK] Loss weights accessible")
        print()
    else:
        print("[4] ExtendedTemporalCTMLoss - SKIPPED (Phase 4 not available)")
        print()

    print("=" * 70)
    print("PHASE-LOCKING LOSS TESTS COMPLETE")
    print("=" * 70)
