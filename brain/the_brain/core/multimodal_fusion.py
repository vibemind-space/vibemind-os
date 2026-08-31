"""
Multi-Modal Fusion - AGI Phase 6

Integrates multiple sensory modalities into unified representations.
Enables cross-modal learning and robust perception.

Key Features:
- Vision, Audio, Text, Proprioception fusion
- Cross-modal attention mechanisms
- Modality-agnostic representations
- Missing modality handling
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class Modality(Enum):
    """Supported sensory modalities."""
    VISION = "vision"
    AUDIO = "audio"
    TEXT = "text"
    PROPRIOCEPTION = "proprioception"
    TOUCH = "touch"
    TEMPERATURE = "temperature"
    FORCE = "force"


@dataclass
class ModalityConfig:
    """Configuration for a modality encoder."""
    modality: Modality
    input_dim: int
    latent_dim: int
    encoder_type: str = "mlp"
    dropout: float = 0.1


@dataclass
class FusedRepresentation:
    """Fused multi-modal representation."""
    unified_embedding: np.ndarray
    modality_embeddings: Dict[Modality, np.ndarray]
    attention_weights: Dict[Modality, float]
    confidence: float
    missing_modalities: List[Modality] = field(default_factory=list)


@dataclass
class FusionStats:
    """Statistics for fusion module."""
    total_fusions: int = 0
    modality_usage: Dict[str, int] = field(default_factory=dict)
    avg_modalities_present: float = 0.0


class ModalityEncoder(nn.Module, ABC):
    """Abstract base class for modality-specific encoders."""

    def __init__(self, input_dim: int, latent_dim: int):
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim

    @abstractmethod
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode modality input to latent space."""
        pass


class MLPEncoder(ModalityEncoder):
    """Simple MLP encoder for any modality."""

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
        hidden_dim: int = 256,
        num_layers: int = 2,
        dropout: float = 0.1
    ):
        super().__init__(input_dim, latent_dim)

        layers = []
        in_dim = input_dim
        for i in range(num_layers - 1):
            layers.extend([
                nn.Linear(in_dim, hidden_dim),
                nn.ReLU(),
                nn.LayerNorm(hidden_dim),
                nn.Dropout(dropout)
            ])
            in_dim = hidden_dim

        layers.append(nn.Linear(in_dim, latent_dim))
        self.encoder = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)


class CNNEncoder(ModalityEncoder):
    """CNN encoder for vision/spatial modalities."""

    def __init__(
        self,
        input_channels: int,
        latent_dim: int,
        image_size: int = 64
    ):
        # input_dim represents flattened size for compatibility
        super().__init__(input_channels * image_size * image_size, latent_dim)
        self.input_channels = input_channels
        self.image_size = image_size

        self.conv_layers = nn.Sequential(
            nn.Conv2d(input_channels, 32, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 128, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4))
        )

        self.fc = nn.Linear(128 * 4 * 4, latent_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Reshape if flattened
        if x.dim() == 2:
            batch_size = x.shape[0]
            x = x.view(batch_size, self.input_channels, self.image_size, self.image_size)

        features = self.conv_layers(x)
        features = features.view(features.size(0), -1)
        return self.fc(features)


class TransformerEncoder(ModalityEncoder):
    """Transformer encoder for sequential modalities (text, audio)."""

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
        num_heads: int = 4,
        num_layers: int = 2,
        max_seq_len: int = 128
    ):
        super().__init__(input_dim, latent_dim)

        self.embedding = nn.Linear(input_dim, latent_dim)
        self.pos_encoding = nn.Parameter(torch.randn(1, max_seq_len, latent_dim) * 0.02)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=latent_dim,
            nhead=num_heads,
            dim_feedforward=latent_dim * 4,
            dropout=0.1,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.pooling = nn.AdaptiveAvgPool1d(1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [batch, seq_len, input_dim] or [batch, input_dim]
        if x.dim() == 2:
            x = x.unsqueeze(1)  # Add sequence dimension

        batch_size, seq_len, _ = x.shape

        # Embed and add positional encoding
        x = self.embedding(x)
        x = x + self.pos_encoding[:, :seq_len, :]

        # Transform
        x = self.transformer(x)

        # Pool to single vector
        x = x.permute(0, 2, 1)  # [batch, latent, seq]
        x = self.pooling(x).squeeze(-1)

        return x


class CrossModalAttention(nn.Module):
    """
    Cross-modal attention for fusing different modalities.

    Allows each modality to attend to all others.
    """

    def __init__(self, latent_dim: int, num_heads: int = 4):
        super().__init__()
        self.latent_dim = latent_dim
        self.num_heads = num_heads

        self.attention = nn.MultiheadAttention(
            embed_dim=latent_dim,
            num_heads=num_heads,
            batch_first=True
        )

        self.norm = nn.LayerNorm(latent_dim)

    def forward(
        self,
        query_modality: torch.Tensor,
        all_modalities: torch.Tensor,
        mask: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Cross-modal attention.

        Args:
            query_modality: Query modality [batch, latent_dim]
            all_modalities: All modalities stacked [batch, num_modalities, latent_dim]
            mask: Optional attention mask

        Returns:
            attended: Attended representation
            attention_weights: Attention weights
        """
        # Add sequence dimension to query
        query = query_modality.unsqueeze(1)

        attended, weights = self.attention(
            query, all_modalities, all_modalities,
            key_padding_mask=mask
        )

        attended = attended.squeeze(1)
        attended = self.norm(attended + query_modality)

        return attended, weights.squeeze(1)


class GatedFusion(nn.Module):
    """
    Gated fusion mechanism for combining modalities.

    Learns to weight modalities based on content.
    """

    def __init__(self, latent_dim: int, num_modalities: int):
        super().__init__()
        self.latent_dim = latent_dim
        self.num_modalities = num_modalities

        # Gate network
        self.gate = nn.Sequential(
            nn.Linear(latent_dim * num_modalities, latent_dim),
            nn.ReLU(),
            nn.Linear(latent_dim, num_modalities),
            nn.Softmax(dim=-1)
        )

        # Fusion projection
        self.projection = nn.Linear(latent_dim, latent_dim)

    def forward(
        self,
        modality_embeddings: torch.Tensor,
        mask: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Gated fusion of modalities.

        Args:
            modality_embeddings: [batch, num_modalities, latent_dim]
            mask: [batch, num_modalities] - True for missing modalities

        Returns:
            fused: Fused representation
            gate_weights: Gate weights per modality
        """
        batch_size = modality_embeddings.shape[0]

        # Flatten for gate computation
        flat = modality_embeddings.view(batch_size, -1)

        # Compute gates
        gates = self.gate(flat)  # [batch, num_modalities]

        # Apply mask (zero out missing modalities)
        if mask is not None:
            gates = gates.masked_fill(mask, 0.0)
            # Renormalize
            gate_sum = gates.sum(dim=-1, keepdim=True) + 1e-8
            gates = gates / gate_sum

        # Weighted combination
        gates_expanded = gates.unsqueeze(-1)  # [batch, num_modalities, 1]
        fused = (modality_embeddings * gates_expanded).sum(dim=1)

        fused = self.projection(fused)

        return fused, gates


class ModalityDropout(nn.Module):
    """
    Randomly drops modalities during training.

    Improves robustness to missing modalities.
    """

    def __init__(self, drop_prob: float = 0.2, min_modalities: int = 1):
        super().__init__()
        self.drop_prob = drop_prob
        self.min_modalities = min_modalities

    def forward(
        self,
        modality_embeddings: torch.Tensor,
        existing_mask: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Apply modality dropout.

        Args:
            modality_embeddings: [batch, num_modalities, latent_dim]
            existing_mask: Existing mask for missing modalities

        Returns:
            masked_embeddings: Embeddings with dropped modalities zeroed
            combined_mask: Combined dropout and existing mask
        """
        if not self.training:
            if existing_mask is None:
                existing_mask = torch.zeros(
                    modality_embeddings.shape[:2],
                    dtype=torch.bool,
                    device=modality_embeddings.device
                )
            return modality_embeddings, existing_mask

        batch_size, num_modalities, _ = modality_embeddings.shape

        # Generate dropout mask
        dropout_mask = torch.rand(batch_size, num_modalities, device=modality_embeddings.device) < self.drop_prob

        # Ensure minimum modalities remain
        for i in range(batch_size):
            available = (~dropout_mask[i]).sum()
            if available < self.min_modalities:
                # Keep random modalities
                keep_indices = torch.randperm(num_modalities)[:self.min_modalities]
                dropout_mask[i, keep_indices] = False

        # Combine with existing mask
        if existing_mask is not None:
            combined_mask = dropout_mask | existing_mask
        else:
            combined_mask = dropout_mask

        # Apply mask
        masked_embeddings = modality_embeddings.clone()
        masked_embeddings[combined_mask] = 0.0

        return masked_embeddings, combined_mask


class MultiModalFusion(nn.Module):
    """
    Main multi-modal fusion module.

    Combines multiple sensory modalities into unified representations.
    """

    def __init__(
        self,
        modality_configs: List[ModalityConfig],
        unified_dim: int = 256,
        fusion_type: str = "attention",  # "attention", "gated", "concat"
        use_modality_dropout: bool = True,
        dropout_prob: float = 0.2
    ):
        super().__init__()
        self.unified_dim = unified_dim
        self.fusion_type = fusion_type
        self.modality_configs = {cfg.modality: cfg for cfg in modality_configs}
        self.modality_order = [cfg.modality for cfg in modality_configs]

        # Create encoders for each modality
        self.encoders = nn.ModuleDict()
        for cfg in modality_configs:
            encoder = self._create_encoder(cfg)
            self.encoders[cfg.modality.value] = encoder

        # Projection to unified dimension
        self.projections = nn.ModuleDict()
        for cfg in modality_configs:
            self.projections[cfg.modality.value] = nn.Linear(cfg.latent_dim, unified_dim)

        # Fusion mechanism
        num_modalities = len(modality_configs)
        if fusion_type == "attention":
            self.fusion = CrossModalAttention(unified_dim)
            self.final_projection = nn.Linear(unified_dim, unified_dim)
        elif fusion_type == "gated":
            self.fusion = GatedFusion(unified_dim, num_modalities)
        else:  # concat
            self.fusion = nn.Linear(unified_dim * num_modalities, unified_dim)

        # Modality dropout
        self.modality_dropout = ModalityDropout(dropout_prob) if use_modality_dropout else None

        # Statistics
        self.stats = FusionStats()

    def _create_encoder(self, cfg: ModalityConfig) -> ModalityEncoder:
        """Create encoder based on config."""
        if cfg.encoder_type == "cnn":
            return CNNEncoder(cfg.input_dim, cfg.latent_dim)
        elif cfg.encoder_type == "transformer":
            return TransformerEncoder(cfg.input_dim, cfg.latent_dim)
        else:
            return MLPEncoder(cfg.input_dim, cfg.latent_dim, dropout=cfg.dropout)

    def forward(
        self,
        modality_inputs: Dict[Modality, torch.Tensor],
        return_attention: bool = False
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, Dict[Modality, float]]]:
        """
        Fuse multiple modalities.

        Args:
            modality_inputs: Dictionary of modality name to input tensor
            return_attention: Whether to return attention weights

        Returns:
            unified: Unified representation
            attention_weights: Optional attention weights per modality
        """
        batch_size = next(iter(modality_inputs.values())).shape[0]
        device = next(iter(modality_inputs.values())).device

        # Encode each modality
        embeddings = []
        mask = []

        for modality in self.modality_order:
            if modality in modality_inputs:
                x = modality_inputs[modality]
                encoded = self.encoders[modality.value](x)
                projected = self.projections[modality.value](encoded)
                embeddings.append(projected)
                mask.append(False)
            else:
                # Missing modality - use zeros
                embeddings.append(torch.zeros(batch_size, self.unified_dim, device=device))
                mask.append(True)

        # Stack embeddings
        stacked = torch.stack(embeddings, dim=1)  # [batch, num_modalities, unified_dim]
        mask_tensor = torch.tensor(mask, device=device).unsqueeze(0).expand(batch_size, -1)

        # Apply modality dropout during training
        if self.modality_dropout is not None:
            stacked, mask_tensor = self.modality_dropout(stacked, mask_tensor)

        # Fuse modalities
        attention_weights = {}

        if self.fusion_type == "attention":
            # Use mean of available modalities as query
            available_mask = ~mask_tensor
            query = (stacked * available_mask.unsqueeze(-1).float()).sum(dim=1)
            query = query / (available_mask.sum(dim=1, keepdim=True).float() + 1e-8)

            unified, weights = self.fusion(query, stacked, mask_tensor)
            unified = self.final_projection(unified)

            for i, modality in enumerate(self.modality_order):
                attention_weights[modality] = weights[:, i].mean().item()

        elif self.fusion_type == "gated":
            unified, gates = self.fusion(stacked, mask_tensor)

            for i, modality in enumerate(self.modality_order):
                attention_weights[modality] = gates[:, i].mean().item()

        else:  # concat
            flat = stacked.view(batch_size, -1)
            unified = self.fusion(flat)

            # Equal weights for concat
            for modality in self.modality_order:
                attention_weights[modality] = 1.0 / len(self.modality_order)

        # Update stats
        self.stats.total_fusions += batch_size
        present_count = (~mask_tensor).sum(dim=1).float().mean().item()
        self.stats.avg_modalities_present = (
            0.9 * self.stats.avg_modalities_present + 0.1 * present_count
        )

        if return_attention:
            return unified, attention_weights
        return unified

    def encode_single_modality(
        self,
        modality: Modality,
        x: torch.Tensor
    ) -> torch.Tensor:
        """Encode a single modality."""
        encoded = self.encoders[modality.value](x)
        return self.projections[modality.value](encoded)


class MultiModalMemory(nn.Module):
    """
    Memory bank for multi-modal experiences.

    Stores and retrieves multi-modal memories for learning.
    """

    def __init__(
        self,
        unified_dim: int,
        memory_size: int = 1000,
        num_modalities: int = 4
    ):
        super().__init__()
        self.unified_dim = unified_dim
        self.memory_size = memory_size
        self.num_modalities = num_modalities

        # Memory banks
        self.register_buffer(
            'unified_memory',
            torch.zeros(memory_size, unified_dim)
        )
        self.register_buffer(
            'modality_memories',
            torch.zeros(num_modalities, memory_size, unified_dim)
        )
        self.register_buffer('memory_count', torch.tensor(0))

        # Attention for retrieval
        self.query_projection = nn.Linear(unified_dim, unified_dim)

    def store(
        self,
        unified: torch.Tensor,
        modality_embeddings: Optional[Dict[int, torch.Tensor]] = None
    ):
        """Store unified representation in memory."""
        batch_size = unified.shape[0]
        start_idx = self.memory_count.item() % self.memory_size

        for i in range(batch_size):
            idx = (start_idx + i) % self.memory_size
            self.unified_memory[idx] = unified[i].detach()

            if modality_embeddings:
                for mod_idx, emb in modality_embeddings.items():
                    if emb is not None:
                        self.modality_memories[mod_idx, idx] = emb[i].detach()

        self.memory_count += batch_size

    def retrieve(
        self,
        query: torch.Tensor,
        top_k: int = 5
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Retrieve relevant memories.

        Args:
            query: Query vector [batch, unified_dim]
            top_k: Number of memories to retrieve

        Returns:
            retrieved: Retrieved memories
            similarity: Similarity scores
        """
        valid_count = min(self.memory_count.item(), self.memory_size)
        if valid_count == 0:
            return torch.zeros(query.shape[0], 0, self.unified_dim), torch.zeros(query.shape[0], 0)

        # Project query
        query_proj = self.query_projection(query)

        # Compute similarity
        memory = self.unified_memory[:valid_count]
        similarity = F.cosine_similarity(
            query_proj.unsqueeze(1),
            memory.unsqueeze(0),
            dim=-1
        )

        # Get top-k
        k = min(top_k, valid_count)
        top_sim, top_idx = torch.topk(similarity, k, dim=-1)

        # Gather memories
        retrieved = memory[top_idx]

        return retrieved, top_sim


class CrossModalContrastiveLoss(nn.Module):
    """
    Contrastive loss for cross-modal alignment.

    Learns to align representations from different modalities.
    """

    def __init__(self, temperature: float = 0.07):
        super().__init__()
        self.temperature = temperature

    def forward(
        self,
        modality_a: torch.Tensor,
        modality_b: torch.Tensor,
        labels: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Compute cross-modal contrastive loss.

        Args:
            modality_a: Embeddings from modality A [batch, dim]
            modality_b: Embeddings from modality B [batch, dim]
            labels: Optional positive pair labels

        Returns:
            loss: Contrastive loss
        """
        # Normalize
        a_norm = F.normalize(modality_a, dim=-1)
        b_norm = F.normalize(modality_b, dim=-1)

        # Compute similarity matrix
        similarity = torch.matmul(a_norm, b_norm.T) / self.temperature

        # Labels: positive pairs are diagonal (same sample index)
        batch_size = modality_a.shape[0]
        if labels is None:
            labels = torch.arange(batch_size, device=modality_a.device)

        # Symmetric loss
        loss_a = F.cross_entropy(similarity, labels)
        loss_b = F.cross_entropy(similarity.T, labels)

        return (loss_a + loss_b) / 2


def create_multimodal_fusion(
    vision_dim: int = 512,
    audio_dim: int = 256,
    text_dim: int = 768,
    proprioception_dim: int = 64,
    unified_dim: int = 256,
    fusion_type: str = "attention"
) -> MultiModalFusion:
    """
    Factory function to create multi-modal fusion module.

    Args:
        vision_dim: Vision input dimension
        audio_dim: Audio input dimension
        text_dim: Text input dimension
        proprioception_dim: Proprioception input dimension
        unified_dim: Unified output dimension
        fusion_type: Type of fusion ("attention", "gated", "concat")

    Returns:
        Configured MultiModalFusion
    """
    configs = [
        ModalityConfig(Modality.VISION, vision_dim, unified_dim, "mlp"),
        ModalityConfig(Modality.AUDIO, audio_dim, unified_dim, "mlp"),
        ModalityConfig(Modality.TEXT, text_dim, unified_dim, "mlp"),
        ModalityConfig(Modality.PROPRIOCEPTION, proprioception_dim, unified_dim, "mlp"),
    ]

    return MultiModalFusion(
        modality_configs=configs,
        unified_dim=unified_dim,
        fusion_type=fusion_type
    )
