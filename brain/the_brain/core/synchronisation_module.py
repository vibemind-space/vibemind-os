"""
SynchronisationModule - Pairwise Neuron Synchronisation as Representation

Based on SakanaAI's Continuous Thought Machine architecture:
https://github.com/SakanaAI/continuous-thought-machines

Key Innovation:
- Standard approach: Use raw activations as representation
- SakanaAI: Use pairwise SYNCHRONISATION between neurons

Synchronisation between neuron i and j is the dot product of their
temporal traces, accumulated with exponential decay over time.

This encodes temporal information directly into the representation,
enabling the model to "remember" how neurons co-activated over time.

Mathematical formulation:
    sync(i,j,t) = decay_alpha(t) / sqrt(decay_beta(t))
    where:
        decay_alpha(t) = r * decay_alpha(t-1) + activation[i] * activation[j]
        decay_beta(t) = r * decay_beta(t-1) + 1
        r = exp(-decay_params)  # learnable per-pair decay

Usage:
    from core.synchronisation_module import SynchronisationModule

    sync_mod = SynchronisationModule(d_model=256, n_synch_pairs=64)

    # First iteration
    sync, alpha, beta = sync_mod(activated_state)

    # Subsequent iterations (with decay accumulation)
    sync, alpha, beta = sync_mod(activated_state, alpha, beta)
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Tuple, Optional


class SynchronisationModule(nn.Module):
    """
    Compute pairwise neuron synchronisation as representation.

    Synchronisation between neuron i and j is computed as the accumulated
    dot product of their activations over time, with exponential decay.

    Three neuron selection strategies (from SakanaAI):
    1. 'random-pairing': Randomly pair neurons (DEFAULT, best performance)
    2. 'first-last': Use first N neurons for output, last N for action
    3. 'random': Random selection with dense pairwise matrix

    Parameters:
        d_model: Total number of neurons
        n_synch_pairs: Number of neuron pairs for synchronisation
        neuron_select_type: Strategy for selecting neuron pairs
        n_random_self: Number of self-pairings (i-to-i) for snapshot recovery

    Shape:
        Input: (batch, d_model) activated states
        Output: (batch, n_synch_pairs) synchronisation vector
    """

    def __init__(
        self,
        d_model: int,
        n_synch_pairs: int = 64,
        neuron_select_type: str = 'random-pairing',
        n_random_self: int = 0
    ):
        super().__init__()
        self.d_model = d_model
        self.n_synch_pairs = n_synch_pairs
        self.neuron_select_type = neuron_select_type
        self.n_random_self = n_random_self

        # Initialize neuron pairings based on strategy
        left, right = self._initialize_neuron_indices(
            d_model, n_synch_pairs, neuron_select_type, n_random_self
        )

        # Register as buffers (saved in state_dict but not trained)
        self.register_buffer('neuron_indices_left', left)
        self.register_buffer('neuron_indices_right', right)

        # Learnable decay parameters (one per pair)
        # Higher values = faster decay (forgets older activations faster)
        self.decay_params = nn.Parameter(torch.zeros(n_synch_pairs))

    def _initialize_neuron_indices(
        self,
        d_model: int,
        n_synch: int,
        select_type: str,
        n_self: int = 0
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Initialize left and right neuron indices based on selection strategy.

        Returns:
            left, right: Tensor indices for neuron pairs
        """
        if select_type == 'random-pairing':
            # Random pairing: each pair is independent
            # Include n_self self-pairings for snapshot recovery
            left = torch.from_numpy(
                np.random.choice(d_model, size=n_synch, replace=True)
            ).long()

            if n_self > 0:
                # First n_self pairs are self-to-self
                right = torch.cat([
                    left[:n_self],  # Self pairings
                    torch.from_numpy(
                        np.random.choice(d_model, size=n_synch - n_self, replace=True)
                    ).long()
                ])
            else:
                right = torch.from_numpy(
                    np.random.choice(d_model, size=n_synch, replace=True)
                ).long()

        elif select_type == 'first-last':
            # First N neurons paired with themselves (for output)
            # Last N neurons paired with themselves (for action)
            left = torch.arange(n_synch).long()
            right = torch.arange(d_model - n_synch, d_model).long()

        elif select_type == 'random':
            # Random selection with potential overlap
            left = torch.from_numpy(
                np.random.choice(d_model, size=n_synch, replace=True)
            ).long()
            right = torch.from_numpy(
                np.random.choice(d_model, size=n_synch, replace=True)
            ).long()

        else:
            raise ValueError(f"Unknown neuron_select_type: {select_type}")

        return left, right

    def forward(
        self,
        activated_state: torch.Tensor,
        decay_alpha: Optional[torch.Tensor] = None,
        decay_beta: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Compute synchronisation from activated neuron states.

        The synchronisation is computed as:
            sync = decay_alpha / sqrt(decay_beta)

        Where decay_alpha and decay_beta accumulate over iterations:
            decay_alpha = r * prev_alpha + (left * right)
            decay_beta = r * prev_beta + 1

        Args:
            activated_state: (batch, d_model) current post-activations
            decay_alpha: Previous alpha accumulator (or None for first step)
            decay_beta: Previous beta accumulator (or None for first step)

        Returns:
            sync: (batch, n_synch_pairs) synchronisation representation
            decay_alpha: Updated alpha accumulator
            decay_beta: Updated beta accumulator
        """
        batch_size = activated_state.size(0)

        # Get selected neuron activations
        left = activated_state[:, self.neuron_indices_left]    # (B, n_pairs)
        right = activated_state[:, self.neuron_indices_right]  # (B, n_pairs)

        # Pairwise product
        pairwise_product = left * right  # (B, n_pairs)

        # Compute decay factor (clamp for numerical stability)
        # r close to 1 = slow decay (long memory)
        # r close to 0 = fast decay (short memory)
        r = torch.exp(-torch.clamp(self.decay_params, 0, 15))
        r = r.unsqueeze(0)  # (1, n_pairs) for broadcasting

        # Initialize or update accumulators
        if decay_alpha is None or decay_beta is None:
            # First iteration: initialize accumulators
            decay_alpha = pairwise_product
            decay_beta = torch.ones_like(pairwise_product)
        else:
            # Subsequent iterations: accumulate with decay
            decay_alpha = r * decay_alpha + pairwise_product
            decay_beta = r * decay_beta + 1

        # Compute synchronisation (normalized by sqrt of count)
        sync = decay_alpha / torch.sqrt(decay_beta + 1e-8)

        return sync, decay_alpha, decay_beta

    def reset_accumulators(
        self,
        batch_size: int,
        device: torch.device = None
    ) -> Tuple[None, None]:
        """
        Return None accumulators to signal fresh start.

        Returns:
            (None, None) - signals first iteration
        """
        return None, None

    def get_synch_dim(self) -> int:
        """Return output dimension of synchronisation vector."""
        return self.n_synch_pairs

    def get_decay_stats(self) -> dict:
        """Return statistics about learned decay parameters."""
        with torch.no_grad():
            r = torch.exp(-torch.clamp(self.decay_params, 0, 15))
            return {
                'decay_params_mean': self.decay_params.mean().item(),
                'decay_params_std': self.decay_params.std().item(),
                'decay_params_min': self.decay_params.min().item(),
                'decay_params_max': self.decay_params.max().item(),
                'effective_r_mean': r.mean().item(),
                'effective_r_min': r.min().item(),
                'effective_r_max': r.max().item(),
            }

    def extra_repr(self) -> str:
        return (f'd_model={self.d_model}, n_synch_pairs={self.n_synch_pairs}, '
                f'neuron_select_type={self.neuron_select_type}')


class DualSynchronisation(nn.Module):
    """
    Dual synchronisation module for action and output (like SakanaAI CTM).

    Maintains separate sync modules for:
    - Action sync: Used for attention/query computation
    - Output sync: Used for final prediction

    This separation allows different synchronisation patterns for
    different purposes in the reasoning process.
    """

    def __init__(
        self,
        d_model: int,
        n_synch_action: int = 32,
        n_synch_out: int = 64,
        neuron_select_type: str = 'random-pairing'
    ):
        super().__init__()

        self.sync_action = SynchronisationModule(
            d_model=d_model,
            n_synch_pairs=n_synch_action,
            neuron_select_type=neuron_select_type
        )

        self.sync_out = SynchronisationModule(
            d_model=d_model,
            n_synch_pairs=n_synch_out,
            neuron_select_type=neuron_select_type
        )

    def forward(
        self,
        activated_state: torch.Tensor,
        alpha_action: Optional[torch.Tensor] = None,
        beta_action: Optional[torch.Tensor] = None,
        alpha_out: Optional[torch.Tensor] = None,
        beta_out: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor, dict]:
        """
        Compute both action and output synchronisation.

        Returns:
            sync_action: For attention computation
            sync_out: For output prediction
            accumulators: Dict with updated alpha/beta values
        """
        sync_action, alpha_action, beta_action = self.sync_action(
            activated_state, alpha_action, beta_action
        )

        sync_out, alpha_out, beta_out = self.sync_out(
            activated_state, alpha_out, beta_out
        )

        accumulators = {
            'alpha_action': alpha_action,
            'beta_action': beta_action,
            'alpha_out': alpha_out,
            'beta_out': beta_out
        }

        return sync_action, sync_out, accumulators


if __name__ == "__main__":
    # Test the SynchronisationModule
    print("=" * 60)
    print("Testing SynchronisationModule")
    print("=" * 60)

    d_model = 256
    n_synch_pairs = 64
    batch_size = 4
    n_iterations = 10

    sync_mod = SynchronisationModule(
        d_model=d_model,
        n_synch_pairs=n_synch_pairs,
        neuron_select_type='random-pairing'
    )

    print(f"\nModule: {sync_mod}")
    print(f"Parameters: {sum(p.numel() for p in sync_mod.parameters()):,}")

    # Test single iteration
    print("\n" + "-" * 40)
    print("Single iteration test:")
    print("-" * 40)

    state = torch.randn(batch_size, d_model)
    sync, alpha, beta = sync_mod(state)

    print(f"Input shape:  {state.shape}")
    print(f"Output shape: {sync.shape}")
    print(f"Alpha shape:  {alpha.shape}")
    print(f"Beta shape:   {beta.shape}")

    # Test accumulation over iterations
    print("\n" + "-" * 40)
    print(f"Accumulation test ({n_iterations} iterations):")
    print("-" * 40)

    alpha, beta = None, None
    sync_history = []

    for i in range(n_iterations):
        state = torch.randn(batch_size, d_model)
        sync, alpha, beta = sync_mod(state, alpha, beta)
        sync_history.append(sync.mean().item())

    print(f"Sync values over iterations:")
    for i, s in enumerate(sync_history):
        print(f"  Iter {i}: {s:.4f}")

    # Verify accumulation is working
    print(f"\nFinal beta mean: {beta.mean().item():.2f} (should grow with iterations)")

    # Test gradient flow
    print("\n" + "-" * 40)
    print("Gradient test:")
    print("-" * 40)

    state = torch.randn(batch_size, d_model, requires_grad=True)
    sync, _, _ = sync_mod(state)
    loss = sync.sum()
    loss.backward()

    print(f"Gradient flows to input: {state.grad is not None}")
    print(f"Decay params gradient: {sync_mod.decay_params.grad is not None}")

    # Test decay statistics
    print("\n" + "-" * 40)
    print("Decay statistics:")
    print("-" * 40)

    for key, value in sync_mod.get_decay_stats().items():
        print(f"  {key}: {value:.4f}")

    # Test different selection types
    print("\n" + "-" * 40)
    print("Selection type comparison:")
    print("-" * 40)

    for select_type in ['random-pairing', 'first-last', 'random']:
        mod = SynchronisationModule(
            d_model=d_model,
            n_synch_pairs=n_synch_pairs,
            neuron_select_type=select_type
        )
        state = torch.randn(batch_size, d_model)
        sync, _, _ = mod(state)
        print(f"  {select_type}: output shape {sync.shape}")

    # Test DualSynchronisation
    print("\n" + "-" * 40)
    print("DualSynchronisation test:")
    print("-" * 40)

    dual_sync = DualSynchronisation(
        d_model=d_model,
        n_synch_action=32,
        n_synch_out=64
    )

    state = torch.randn(batch_size, d_model)
    sync_action, sync_out, accumulators = dual_sync(state)

    print(f"Action sync shape: {sync_action.shape}")
    print(f"Output sync shape: {sync_out.shape}")

    print("\n" + "=" * 60)
    print("SynchronisationModule tests PASSED!")
    print("=" * 60)
