"""
NeuronLevelModel - Per-neuron temporal processing (SakanaAI SuperLinear)

Based on SakanaAI's Continuous Thought Machine architecture:
https://github.com/SakanaAI/continuous-thought-machines

Each of the N neurons has UNIQUE weight parameters to process a history
of incoming signals, enabling fine-grained temporal dynamics.

Key Innovation:
- Standard nn.Linear: All neurons share weights
- SuperLinear/NLM: Each neuron has its own private weights

This enables:
1. Fine-grained temporal dynamics per neuron
2. Specialized processing based on each neuron's history
3. Richer internal representations

Usage:
    from core.neuron_level_model import NeuronLevelModel

    nlm = NeuronLevelModel(d_model=256, memory_length=10)
    state_trace = torch.randn(batch_size, 256, 10)  # (B, D, M)
    activated_state = nlm(state_trace)  # (B, D)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from typing import Optional


class NeuronLevelModel(nn.Module):
    """
    Per-neuron temporal processing (SakanaAI SuperLinear).

    Each of the N neurons has UNIQUE weight parameters to process
    a history of incoming signals (traces), enabling fine-grained
    temporal dynamics that standard shared-weight layers cannot achieve.

    Architecture:
    - Deep NLM (default): 2-layer MLP per neuron with GLU activations
    - Simple NLM: Single linear layer per neuron with GLU

    Parameters:
        d_model: Number of neurons (feature dimension)
        memory_length: Temporal history length (M in paper)
        hidden_dims: Hidden dimension for deep NLM
        deep_nlm: Use 2-layer NLM (True) or single-layer (False)
        dropout: Dropout rate for regularization

    Shape:
        Input: (batch, d_model, memory_length)
        Output: (batch, d_model)
    """

    def __init__(
        self,
        d_model: int,
        memory_length: int,
        hidden_dims: int = 64,
        deep_nlm: bool = True,
        dropout: float = 0.0
    ):
        super().__init__()
        self.d_model = d_model
        self.memory_length = memory_length
        self.hidden_dims = hidden_dims
        self.deep_nlm = deep_nlm

        if deep_nlm:
            # Layer 1: memory_length -> hidden_dims*2 (for GLU halving)
            # Weights shape: (M, H*2, D) where each neuron d has its own M->H*2 transform
            self.w1 = nn.Parameter(
                torch.empty(memory_length, hidden_dims * 2, d_model).uniform_(
                    -1 / math.sqrt(memory_length + hidden_dims),
                    1 / math.sqrt(memory_length + hidden_dims)
                )
            )
            self.b1 = nn.Parameter(torch.zeros(1, d_model, hidden_dims * 2))

            # Layer 2: hidden_dims -> 2 (for GLU -> 1)
            self.w2 = nn.Parameter(
                torch.empty(hidden_dims, 2, d_model).uniform_(
                    -1 / math.sqrt(hidden_dims + 2),
                    1 / math.sqrt(hidden_dims + 2)
                )
            )
            self.b2 = nn.Parameter(torch.zeros(1, d_model, 2))
        else:
            # Simple: memory_length -> 2 (for GLU -> 1)
            self.w1 = nn.Parameter(
                torch.empty(memory_length, 2, d_model).uniform_(
                    -1 / math.sqrt(memory_length + 2),
                    1 / math.sqrt(memory_length + 2)
                )
            )
            self.b1 = nn.Parameter(torch.zeros(1, d_model, 2))

        # Dropout and normalization
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        self.layer_norm = nn.LayerNorm(memory_length)

        # Learnable temperature/scaling factor
        self.T = nn.Parameter(torch.ones(1))

    def forward(self, state_trace: torch.Tensor) -> torch.Tensor:
        """
        Process temporal trace through per-neuron NLMs.

        The key operation is the einsum which applies N independent
        linear transformations - one per neuron:

            einsum('BDM,MHD->BDH', state_trace, w1)

        Where:
            B = batch size
            D = d_model (number of neurons)
            M = memory_length (temporal history)
            H = hidden_dims

        Each neuron d uses w1[:, :, d] (shape M x H) to transform
        its temporal trace state_trace[:, d, :] (shape B x M).

        Args:
            state_trace: (batch, d_model, memory_length) temporal history

        Returns:
            activated_state: (batch, d_model) post-activation states
        """
        # Apply dropout to input
        out = self.dropout(state_trace)

        # Layer normalization across time dimension
        out = self.layer_norm(out)

        if self.deep_nlm:
            # Layer 1: Per-neuron linear transform
            # einsum: for each neuron d, transform its M-length history to H*2 dims
            out = torch.einsum('BDM,MHD->BDH', out, self.w1) + self.b1
            out = F.glu(out, dim=-1)  # GLU halves: H*2 -> H

            # Layer 2: Per-neuron linear transform
            out = torch.einsum('BDH,HOD->BDO', out, self.w2) + self.b2
            out = F.glu(out, dim=-1)  # GLU halves: 2 -> 1
        else:
            # Simple single-layer NLM
            out = torch.einsum('BDM,MOD->BDO', out, self.w1) + self.b1
            out = F.glu(out, dim=-1)

        # Squeeze last dim and apply temperature scaling
        return out.squeeze(-1) / self.T

    def get_num_parameters(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters())

    def get_parameter_breakdown(self) -> dict:
        """Return breakdown of parameters by component."""
        breakdown = {
            'w1': self.w1.numel(),
            'b1': self.b1.numel(),
            'layer_norm': sum(p.numel() for p in self.layer_norm.parameters()),
            'T': self.T.numel()
        }
        if self.deep_nlm:
            breakdown['w2'] = self.w2.numel()
            breakdown['b2'] = self.b2.numel()
        breakdown['total'] = sum(breakdown.values())
        return breakdown

    def extra_repr(self) -> str:
        return (f'd_model={self.d_model}, memory_length={self.memory_length}, '
                f'hidden_dims={self.hidden_dims}, deep_nlm={self.deep_nlm}')


class Squeeze(nn.Module):
    """Helper module to squeeze a dimension in nn.Sequential."""

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x.squeeze(self.dim)


def create_nlm_trace_processor(
    d_model: int,
    memory_length: int,
    hidden_dims: int = 64,
    deep_nlm: bool = True,
    do_layernorm: bool = False,
    dropout: float = 0.0
) -> nn.Module:
    """
    Factory function to create NLM trace processor.

    This creates a sequential module matching SakanaAI's trace_processor
    architecture for easy drop-in replacement.

    Args:
        d_model: Number of neurons
        memory_length: Temporal history length
        hidden_dims: Hidden dimension for deep NLM
        deep_nlm: Use 2-layer (True) or 1-layer (False)
        do_layernorm: Apply layer norm (SakanaAI sets this False)
        dropout: Dropout rate

    Returns:
        nn.Module that processes (B, D, M) -> (B, D)
    """
    return NeuronLevelModel(
        d_model=d_model,
        memory_length=memory_length,
        hidden_dims=hidden_dims,
        deep_nlm=deep_nlm,
        dropout=dropout
    )


if __name__ == "__main__":
    # Test the NeuronLevelModel
    print("=" * 60)
    print("Testing NeuronLevelModel (SakanaAI SuperLinear)")
    print("=" * 60)

    # Create model
    d_model = 256
    memory_length = 10
    batch_size = 4

    nlm = NeuronLevelModel(
        d_model=d_model,
        memory_length=memory_length,
        hidden_dims=64,
        deep_nlm=True
    )

    print(f"\nModel: {nlm}")
    print(f"\nParameter breakdown:")
    for name, count in nlm.get_parameter_breakdown().items():
        print(f"  {name}: {count:,}")

    # Test forward pass
    print("\n" + "-" * 40)
    print("Forward pass test:")
    print("-" * 40)

    state_trace = torch.randn(batch_size, d_model, memory_length)
    print(f"Input shape:  {state_trace.shape}")

    with torch.no_grad():
        output = nlm(state_trace)

    print(f"Output shape: {output.shape}")
    print(f"Output range: [{output.min():.3f}, {output.max():.3f}]")
    print(f"Output mean:  {output.mean():.3f}")
    print(f"Output std:   {output.std():.3f}")

    # Test gradient flow
    print("\n" + "-" * 40)
    print("Gradient test:")
    print("-" * 40)

    state_trace = torch.randn(batch_size, d_model, memory_length, requires_grad=True)
    output = nlm(state_trace)
    loss = output.sum()
    loss.backward()

    print(f"Gradient flows to input: {state_trace.grad is not None}")
    print(f"w1 gradient norm: {nlm.w1.grad.norm():.4f}")
    print(f"w2 gradient norm: {nlm.w2.grad.norm():.4f}")

    # Compare with simple NLM
    print("\n" + "-" * 40)
    print("Simple vs Deep NLM comparison:")
    print("-" * 40)

    simple_nlm = NeuronLevelModel(
        d_model=d_model,
        memory_length=memory_length,
        deep_nlm=False
    )

    print(f"Deep NLM params:   {nlm.get_num_parameters():,}")
    print(f"Simple NLM params: {simple_nlm.get_num_parameters():,}")

    print("\n" + "=" * 60)
    print("NeuronLevelModel tests PASSED!")
    print("=" * 60)
