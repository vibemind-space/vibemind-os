"""
Sensory Processing Modules

Implements the four sensory/perceptual modules:
- VIS: Visual processing (CNN encoder)
- AUD: Auditory processing (Spectral encoder)
- SOM: Somatosensory/Spatial processing (Graph network)
- LAN: Language processing (Transformer encoder)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple
import math

from neurosymbolic.modules.base_module import BrainModule


class VISModule(BrainModule):
    """
    Visual Processing Module (BA 17-19)

    Implements hierarchical visual processing using CNN:
    - Stage 1: Edge detection (low-level features)
    - Stage 2: Contours and shapes (mid-level features)
    - Stage 3: Object parts (high-level features)

    Architecture: Conv2D → BatchNorm → ReLU → MaxPool
    """

    def __init__(
        self,
        input_channels: int = 3,
        hidden_dims: Tuple[int, int, int] = (64, 128, 128),
        output_dim: int = 256
    ):
        """
        Initialize VIS module

        Args:
            input_channels: Number of input channels (3 for RGB)
            hidden_dims: Hidden dimensions for 3 conv stages
            output_dim: Final output dimension
        """
        super().__init__(
            module_id="VIS",
            module_name="Visual Processing",
            input_dim=input_channels,
            output_dim=output_dim,
            brodmann_areas="17-19"
        )

        # Stage 1: Edge detection
        self.conv1 = nn.Conv2d(input_channels, hidden_dims[0], kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(hidden_dims[0])

        # Stage 2: Contours and shapes
        self.conv2 = nn.Conv2d(hidden_dims[0], hidden_dims[1], kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(hidden_dims[1])

        # Stage 3: Object parts
        self.conv3 = nn.Conv2d(hidden_dims[1], hidden_dims[2], kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(hidden_dims[2])

        # Global pooling + projection
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Linear(hidden_dims[2], output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Process visual input

        Args:
            x: Input tensor [batch, channels, height, width]

        Returns:
            Visual features [batch, output_dim]
        """
        # Stage 1: Edges
        h = F.relu(self.bn1(self.conv1(x)))
        h = F.max_pool2d(h, 2)

        # Stage 2: Shapes
        h = F.relu(self.bn2(self.conv2(h)))
        h = F.max_pool2d(h, 2)

        # Stage 3: Parts
        h = F.relu(self.bn3(self.conv3(h)))
        h = F.max_pool2d(h, 2)

        # Global pooling
        h = self.pool(h)  # [batch, hidden_dims[2], 1, 1]
        h = h.view(h.size(0), -1)  # [batch, hidden_dims[2]]

        # Projection
        out = self.fc(h)  # [batch, output_dim]

        return out


class AUDModule(BrainModule):
    """
    Auditory Processing Module (BA 41-42, 22)

    Implements spectral processing using 1D convolutions:
    - Frequency analysis (Fourier-like)
    - Temporal patterns
    - Phoneme/tone extraction

    Architecture: Conv1D with multiple receptive fields
    """

    def __init__(
        self,
        input_dim: int = 128,  # Mel-spectrogram bins
        hidden_dim: int = 256,
        output_dim: int = 256
    ):
        """
        Initialize AUD module

        Args:
            input_dim: Input feature dimension (e.g., mel bins)
            hidden_dim: Hidden dimension
            output_dim: Output dimension
        """
        super().__init__(
            module_id="AUD",
            module_name="Auditory Processing",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="41-42,22"
        )

        # Multi-scale temporal convolutions
        self.conv1 = nn.Conv1d(input_dim, hidden_dim, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(hidden_dim, hidden_dim, kernel_size=5, padding=2)
        self.conv3 = nn.Conv1d(hidden_dim, hidden_dim, kernel_size=7, padding=3)

        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.bn2 = nn.BatchNorm1d(hidden_dim)
        self.bn3 = nn.BatchNorm1d(hidden_dim)

        # Global pooling + projection
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(hidden_dim, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Process auditory input

        Args:
            x: Input tensor [batch, input_dim, time_steps] or [batch, input_dim]

        Returns:
            Auditory features [batch, output_dim]
        """
        # Add time dimension if needed
        if x.dim() == 2:
            x = x.unsqueeze(-1)  # [batch, input_dim, 1]

        # Multi-scale processing
        h1 = F.relu(self.bn1(self.conv1(x)))
        h2 = F.relu(self.bn2(self.conv2(h1)))
        h3 = F.relu(self.bn3(self.conv3(h2)))

        # Global pooling
        h = self.pool(h3)  # [batch, hidden_dim, 1]
        h = h.squeeze(-1)  # [batch, hidden_dim]

        # Projection
        out = self.fc(h)  # [batch, output_dim]

        return out


class SOMModule(BrainModule):
    """
    Somatosensory/Spatial Processing Module (BA 1-3, 5, 7)

    Implements spatial/topological processing:
    - Body map representation
    - Spatial relationships
    - Topological features

    Architecture: Graph-like processing with MLPs
    """

    def __init__(
        self,
        input_dim: int = 256,
        hidden_dim: int = 256,
        output_dim: int = 256
    ):
        """
        Initialize SOM module

        Args:
            input_dim: Input dimension
            hidden_dim: Hidden dimension
            output_dim: Output dimension
        """
        super().__init__(
            module_id="SOM",
            module_name="Somatosensory Processing",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="1-3,5,7"
        )

        # Topological processing layers
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, output_dim)

        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.bn2 = nn.BatchNorm1d(hidden_dim)

        # Dropout for regularization
        self.dropout = nn.Dropout(0.1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Process somatosensory/spatial input

        Args:
            x: Input tensor [batch, input_dim]

        Returns:
            Spatial features [batch, output_dim]
        """
        h = F.relu(self.bn1(self.fc1(x)))
        h = self.dropout(h)

        h = F.relu(self.bn2(self.fc2(h)))
        h = self.dropout(h)

        out = self.fc3(h)

        return out


class LANModule(BrainModule):
    """
    Language Processing Module (BA 22, 37, 39, 44-45, 47)

    Implements language processing using simplified Transformer:
    - Token embeddings
    - Self-attention
    - Semantic representation

    Architecture: Single-layer Transformer encoder
    """

    def __init__(
        self,
        input_dim: int = 256,
        num_heads: int = 8,
        ff_dim: int = 512,
        output_dim: int = 256,
        max_seq_len: int = 32
    ):
        """
        Initialize LAN module

        Args:
            input_dim: Input embedding dimension
            num_heads: Number of attention heads
            ff_dim: Feed-forward dimension
            output_dim: Output dimension
            max_seq_len: Maximum sequence length
        """
        super().__init__(
            module_id="LAN",
            module_name="Language Processing",
            input_dim=input_dim,
            output_dim=output_dim,
            brodmann_areas="22,37,39,44-45,47"
        )

        self.max_seq_len = max_seq_len

        # Positional encoding
        self.pos_encoding = self._create_positional_encoding(max_seq_len, input_dim)

        # Transformer encoder layer
        self.attention = nn.MultiheadAttention(
            embed_dim=input_dim,
            num_heads=num_heads,
            batch_first=True
        )

        self.norm1 = nn.LayerNorm(input_dim)
        self.norm2 = nn.LayerNorm(input_dim)

        self.ff = nn.Sequential(
            nn.Linear(input_dim, ff_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(ff_dim, input_dim)
        )

        # Output projection
        self.fc_out = nn.Linear(input_dim, output_dim)

    def _create_positional_encoding(self, max_len: int, d_model: int) -> torch.Tensor:
        """Create sinusoidal positional encoding"""
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )

        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)

        return pe.unsqueeze(0)  # [1, max_len, d_model]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Process language input

        Args:
            x: Input tensor [batch, seq_len, input_dim] or [batch, input_dim]

        Returns:
            Language features [batch, output_dim]
        """
        # Add sequence dimension if needed
        if x.dim() == 2:
            x = x.unsqueeze(1)  # [batch, 1, input_dim]

        batch_size, seq_len, _ = x.shape

        # Add positional encoding
        if seq_len <= self.max_seq_len:
            pos_enc = self.pos_encoding[:, :seq_len, :].to(x.device)
            x = x + pos_enc

        # Self-attention
        attn_out, _ = self.attention(x, x, x)
        x = self.norm1(x + attn_out)

        # Feed-forward
        ff_out = self.ff(x)
        x = self.norm2(x + ff_out)

        # Pool over sequence (mean pooling)
        h = x.mean(dim=1)  # [batch, input_dim]

        # Output projection
        out = self.fc_out(h)  # [batch, output_dim]

        return out


if __name__ == "__main__":
    # Test sensory modules
    print("Testing Sensory Modules...")
    print("="*60)

    batch_size = 4

    # Test VIS
    print("\n1. VIS Module (Visual Processing)")
    vis = VISModule(input_channels=3, output_dim=256)
    print(f"   {vis}")
    x_vis = torch.randn(batch_size, 3, 64, 64)  # RGB image
    y_vis = vis(x_vis)
    print(f"   Input: {x_vis.shape} -> Output: {y_vis.shape}")
    print(f"   Parameters: {vis.get_info()['num_parameters']:,}")

    # Test AUD
    print("\n2. AUD Module (Auditory Processing)")
    aud = AUDModule(input_dim=128, output_dim=256)
    print(f"   {aud}")
    x_aud = torch.randn(batch_size, 128, 100)  # Mel spectrogram
    y_aud = aud(x_aud)
    print(f"   Input: {x_aud.shape} -> Output: {y_aud.shape}")
    print(f"   Parameters: {aud.get_info()['num_parameters']:,}")

    # Test SOM
    print("\n3. SOM Module (Somatosensory Processing)")
    som = SOMModule(input_dim=256, output_dim=256)
    print(f"   {som}")
    x_som = torch.randn(batch_size, 256)
    y_som = som(x_som)
    print(f"   Input: {x_som.shape} -> Output: {y_som.shape}")
    print(f"   Parameters: {som.get_info()['num_parameters']:,}")

    # Test LAN
    print("\n4. LAN Module (Language Processing)")
    lan = LANModule(input_dim=256, output_dim=256)
    print(f"   {lan}")
    x_lan = torch.randn(batch_size, 10, 256)  # Sequence of tokens
    y_lan = lan(x_lan)
    print(f"   Input: {x_lan.shape} -> Output: {y_lan.shape}")
    print(f"   Parameters: {lan.get_info()['num_parameters']:,}")

    print("\n" + "="*60)
    print("All sensory modules working correctly!")
