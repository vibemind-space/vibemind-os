"""
ThoughtProjector - CTM State to Thought Vector Projection

Projects CTM internal states into a unified thought vector that can be
decoded by a text decoder (GPT-2) to generate natural language.

Architecture:
    sync_out (64) ────────────────→ Linear(64→512) ─────┐
    certainties (N) ─→ Certainty Encoder (128) ─────────┼→ Fusion MLP → 2048
    consciousness_trajectory ─→ GRU(256) ───────────────┘

The thought vector captures:
1. Synchronisation patterns (what neurons are thinking together)
2. Certainty progression (how confident the reasoning became)
3. Consciousness trajectory (the path of awareness during reasoning)

Usage:
    from core.thought_projector import ThoughtProjector

    projector = ThoughtProjector(sync_dim=64, thought_dim=2048)
    thought_vector = projector(sync_out, certainties, consciousness_trajectory)
"""

import torch
import torch.nn as nn
from typing import List, Optional, Union


class ThoughtProjector(nn.Module):
    """
    Projects CTM reasoning states into a unified thought vector.

    The thought vector is designed to capture the essence of the CTM's
    reasoning process in a format suitable for text generation.

    Parameters:
        sync_dim: Dimension of sync_out from CTM (default: 64)
        thought_dim: Output thought vector dimension (default: 2048)
        certainty_embed_dim: Dimension for certainty embedding (default: 128)
        consciousness_hidden: Hidden dimension for consciousness GRU (default: 256)
        dropout: Dropout rate for regularization (default: 0.1)
    """

    def __init__(
        self,
        sync_dim: int = 64,
        thought_dim: int = 2048,
        certainty_embed_dim: int = 128,
        consciousness_hidden: int = 256,
        dropout: float = 0.1
    ):
        super().__init__()
        self.sync_dim = sync_dim
        self.thought_dim = thought_dim
        self.certainty_embed_dim = certainty_embed_dim
        self.consciousness_hidden = consciousness_hidden

        # 1. Sync projector: sync_out → 512-dim
        self.sync_projector = nn.Sequential(
            nn.Linear(sync_dim, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, 512),
            nn.LayerNorm(512),
            nn.GELU()
        )

        # 2. Certainty encoder: certainty values → 128-dim
        # Uses a small MLP that processes mean, std, final certainty
        self.certainty_encoder = nn.Sequential(
            nn.Linear(4, 64),  # [mean, std, final, max]
            nn.GELU(),
            nn.Linear(64, certainty_embed_dim),
            nn.LayerNorm(certainty_embed_dim)
        )

        # 3. Consciousness encoder: trajectory → 256-dim via GRU
        self.consciousness_gru = nn.GRU(
            input_size=1,
            hidden_size=consciousness_hidden,
            num_layers=1,
            batch_first=True
        )
        self.consciousness_projector = nn.Sequential(
            nn.Linear(consciousness_hidden, consciousness_hidden),
            nn.LayerNorm(consciousness_hidden),
            nn.GELU()
        )

        # 4. Fusion layer: Concat(512 + 128 + 256) = 896 → 2048
        fusion_input_dim = 512 + certainty_embed_dim + consciousness_hidden
        self.fusion_layer = nn.Sequential(
            nn.Linear(fusion_input_dim, 1024),
            nn.LayerNorm(1024),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(1024, thought_dim),
            nn.LayerNorm(thought_dim)
        )

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize weights with Xavier/Glorot initialization."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def _encode_certainties(
        self,
        certainties: torch.Tensor,
        batch_size: int,
        device: torch.device
    ) -> torch.Tensor:
        """
        Encode certainty values into a fixed-size embedding.

        Args:
            certainties: (batch, num_steps) certainty values
            batch_size: Batch size
            device: Target device

        Returns:
            (batch, certainty_embed_dim) certainty embedding
        """
        # Compute statistics
        cert_mean = certainties.mean(dim=-1, keepdim=True)
        cert_std = certainties.std(dim=-1, keepdim=True)
        cert_final = certainties[:, -1:] if certainties.size(-1) > 0 else cert_mean
        cert_max = certainties.max(dim=-1, keepdim=True)[0]

        # Concatenate statistics
        cert_features = torch.cat([cert_mean, cert_std, cert_final, cert_max], dim=-1)

        return self.certainty_encoder(cert_features)

    def _encode_consciousness(
        self,
        consciousness_trajectory: Union[List[float], torch.Tensor],
        batch_size: int,
        device: torch.device
    ) -> torch.Tensor:
        """
        Encode consciousness trajectory using GRU.

        Args:
            consciousness_trajectory: List of consciousness values or tensor
            batch_size: Batch size
            device: Target device

        Returns:
            (batch, consciousness_hidden) consciousness embedding
        """
        # Convert list to tensor if needed
        if isinstance(consciousness_trajectory, list):
            # Assume same trajectory for all batch items
            traj = torch.tensor(consciousness_trajectory, dtype=torch.float32, device=device)
            traj = traj.unsqueeze(0).expand(batch_size, -1)  # (batch, seq_len)
        else:
            traj = consciousness_trajectory

        # Add feature dimension for GRU
        traj = traj.unsqueeze(-1)  # (batch, seq_len, 1)

        # Process through GRU
        _, hidden = self.consciousness_gru(traj)  # hidden: (1, batch, hidden)
        hidden = hidden.squeeze(0)  # (batch, hidden)

        return self.consciousness_projector(hidden)

    def forward(
        self,
        sync_out: torch.Tensor,
        certainties: torch.Tensor,
        consciousness_trajectory: Union[List[float], torch.Tensor],
        return_components: bool = False
    ) -> Union[torch.Tensor, dict]:
        """
        Project CTM states into thought vector.

        Args:
            sync_out: (batch, sync_dim) final synchronisation output from CTM
            certainties: (batch, num_steps) certainty values over reasoning steps
            consciousness_trajectory: List of consciousness values or (batch, num_steps) tensor
            return_components: If True, return dict with intermediate components

        Returns:
            thought_vector: (batch, thought_dim) unified thought representation
            OR dict with 'thought_vector' and intermediate components
        """
        batch_size = sync_out.size(0)
        device = sync_out.device

        # 1. Project sync output
        sync_encoded = self.sync_projector(sync_out)  # (batch, 512)

        # 2. Encode certainties
        cert_encoded = self._encode_certainties(certainties, batch_size, device)  # (batch, 128)

        # 3. Encode consciousness trajectory
        cons_encoded = self._encode_consciousness(
            consciousness_trajectory, batch_size, device
        )  # (batch, 256)

        # 4. Fuse all components
        fused = torch.cat([sync_encoded, cert_encoded, cons_encoded], dim=-1)  # (batch, 896)
        thought_vector = self.fusion_layer(fused)  # (batch, 2048)

        if return_components:
            return {
                'thought_vector': thought_vector,
                'sync_encoded': sync_encoded,
                'cert_encoded': cert_encoded,
                'cons_encoded': cons_encoded,
                'fused': fused
            }

        return thought_vector

    def get_num_parameters(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def get_parameter_breakdown(self) -> dict:
        """Return parameter count by component."""
        return {
            'sync_projector': sum(p.numel() for p in self.sync_projector.parameters()),
            'certainty_encoder': sum(p.numel() for p in self.certainty_encoder.parameters()),
            'consciousness_gru': sum(p.numel() for p in self.consciousness_gru.parameters()),
            'consciousness_projector': sum(p.numel() for p in self.consciousness_projector.parameters()),
            'fusion_layer': sum(p.numel() for p in self.fusion_layer.parameters()),
            'total': self.get_num_parameters()
        }

    def extra_repr(self) -> str:
        return (
            f'sync_dim={self.sync_dim}, thought_dim={self.thought_dim}, '
            f'certainty_embed_dim={self.certainty_embed_dim}, '
            f'consciousness_hidden={self.consciousness_hidden}'
        )


class ThoughtProjectorWithAttention(ThoughtProjector):
    """
    Extended ThoughtProjector with cross-attention over reasoning steps.

    This version can attend to individual reasoning steps instead of
    just using the final sync_out, potentially capturing more nuanced
    reasoning patterns.
    """

    def __init__(
        self,
        sync_dim: int = 64,
        thought_dim: int = 2048,
        num_heads: int = 8,
        **kwargs
    ):
        super().__init__(sync_dim, thought_dim, **kwargs)

        # Multi-head attention over reasoning steps
        self.step_attention = nn.MultiheadAttention(
            embed_dim=sync_dim,
            num_heads=num_heads,
            batch_first=True
        )

        # Learnable query for aggregating steps
        self.step_query = nn.Parameter(torch.randn(1, 1, sync_dim))

    def forward_with_steps(
        self,
        sync_history: torch.Tensor,  # (batch, steps, sync_dim)
        certainties: torch.Tensor,
        consciousness_trajectory: Union[List[float], torch.Tensor]
    ) -> torch.Tensor:
        """
        Forward pass using full sync history with attention.

        Args:
            sync_history: (batch, steps, sync_dim) sync outputs over all steps
            certainties: (batch, steps) certainty values
            consciousness_trajectory: List or tensor of consciousness values

        Returns:
            thought_vector: (batch, thought_dim)
        """
        batch_size = sync_history.size(0)

        # Expand query for batch
        query = self.step_query.expand(batch_size, -1, -1)

        # Attend over steps
        attended, _ = self.step_attention(
            query, sync_history, sync_history
        )  # (batch, 1, sync_dim)
        sync_out = attended.squeeze(1)  # (batch, sync_dim)

        # Use parent forward
        return super().forward(sync_out, certainties, consciousness_trajectory)


if __name__ == "__main__":
    # Test the ThoughtProjector
    print("=" * 60)
    print("Testing ThoughtProjector")
    print("=" * 60)

    # Create projector
    projector = ThoughtProjector(
        sync_dim=64,
        thought_dim=2048,
        certainty_embed_dim=128,
        consciousness_hidden=256
    )

    print(f"\nModule: {projector}")
    print(f"\nParameter breakdown:")
    for name, count in projector.get_parameter_breakdown().items():
        print(f"  {name}: {count:,}")

    # Test forward pass
    print("\n" + "-" * 40)
    print("Forward pass test:")
    print("-" * 40)

    batch_size = 2
    num_steps = 15

    sync_out = torch.randn(batch_size, 64)
    certainties = torch.rand(batch_size, num_steps)
    consciousness_trajectory = [0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.82, 0.85, 0.87, 0.88, 0.89, 0.9]

    print(f"Input sync_out shape: {sync_out.shape}")
    print(f"Input certainties shape: {certainties.shape}")
    print(f"Input consciousness trajectory length: {len(consciousness_trajectory)}")

    with torch.no_grad():
        thought_vector = projector(sync_out, certainties, consciousness_trajectory)

    print(f"\nOutput thought_vector shape: {thought_vector.shape}")
    print(f"Output range: [{thought_vector.min():.3f}, {thought_vector.max():.3f}]")
    print(f"Output mean: {thought_vector.mean():.3f}")
    print(f"Output std: {thought_vector.std():.3f}")

    # Test with return_components
    print("\n" + "-" * 40)
    print("Component analysis:")
    print("-" * 40)

    with torch.no_grad():
        result = projector(sync_out, certainties, consciousness_trajectory, return_components=True)

    for name, tensor in result.items():
        if isinstance(tensor, torch.Tensor):
            print(f"  {name}: {tensor.shape}")

    # Test gradient flow
    print("\n" + "-" * 40)
    print("Gradient test:")
    print("-" * 40)

    sync_out = torch.randn(batch_size, 64, requires_grad=True)
    certainties = torch.rand(batch_size, num_steps, requires_grad=True)

    thought_vector = projector(sync_out, certainties, consciousness_trajectory)
    loss = thought_vector.sum()
    loss.backward()

    print(f"Gradient flows to sync_out: {sync_out.grad is not None}")
    print(f"Gradient flows to certainties: {certainties.grad is not None}")

    # Test ThoughtProjectorWithAttention
    print("\n" + "-" * 40)
    print("ThoughtProjectorWithAttention test:")
    print("-" * 40)

    attn_projector = ThoughtProjectorWithAttention(
        sync_dim=64,
        thought_dim=2048,
        num_heads=8
    )

    sync_history = torch.randn(batch_size, num_steps, 64)

    with torch.no_grad():
        thought_vector_attn = attn_projector.forward_with_steps(
            sync_history, certainties, consciousness_trajectory
        )

    print(f"Attention projector output shape: {thought_vector_attn.shape}")
    print(f"Attention projector params: {attn_projector.get_num_parameters():,}")

    print("\n" + "=" * 60)
    print("ThoughtProjector tests PASSED!")
    print("=" * 60)
