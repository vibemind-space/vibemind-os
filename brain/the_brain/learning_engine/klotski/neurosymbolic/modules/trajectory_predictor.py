"""
Trajectory Prediction Module

Implements Sakana AI's trajectory prediction from the Mazes example.
Predicts ENTIRE action sequences instead of single actions.

Key benefits:
- Multi-step planning capability
- Better credit assignment for long-term strategies
- Learns full solution paths, not just next actions
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple


class TrajectoryPredictor(nn.Module):
    """
    Predicts entire action trajectories from CTM synchronization

    Uses LSTM decoder to generate sequences of actions, similar to
    sequence-to-sequence models but conditioned on CTM's thought process.

    Based on Sakana AI CTM Mazes example.
    """

    def __init__(
        self,
        synch_dim: int = 32,
        hidden_dim: int = 256,
        action_dim: int = 5,
        max_trajectory_len: int = 60,
        num_layers: int = 2,
        dropout: float = 0.1
    ):
        """
        Args:
            synch_dim: CTM synchronization dimension
            hidden_dim: LSTM hidden dimension
            action_dim: Number of possible actions
            max_trajectory_len: Maximum trajectory length to predict
            num_layers: Number of LSTM layers
            dropout: Dropout rate
        """
        super().__init__()
        self.synch_dim = synch_dim
        self.hidden_dim = hidden_dim
        self.action_dim = action_dim
        self.max_trajectory_len = max_trajectory_len
        self.num_layers = num_layers

        # Project synchronization to initial hidden state
        self.synch_to_hidden = nn.Linear(synch_dim, hidden_dim * num_layers)
        self.synch_to_cell = nn.Linear(synch_dim, hidden_dim * num_layers)

        # Action embedding (for teacher forcing)
        self.action_embedding = nn.Embedding(action_dim, hidden_dim)

        # LSTM decoder
        self.decoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            batch_first=True
        )

        # Action head
        self.action_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, action_dim)
        )

        # Start token (learned)
        self.register_parameter(
            'start_token',
            nn.Parameter(torch.randn(1, hidden_dim))
        )

    def forward(
        self,
        synch: torch.Tensor,
        target_actions: Optional[torch.Tensor] = None,
        max_len: Optional[int] = None,
        teacher_forcing_ratio: float = 0.5
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Predict action trajectory

        Args:
            synch: (batch, synch_dim) - CTM synchronization representation
            target_actions: (batch, trajectory_len) - ground truth actions (for training)
            max_len: Override max trajectory length
            teacher_forcing_ratio: Probability of using ground truth vs predicted action

        Returns:
            trajectory_logits: (batch, trajectory_len, action_dim) - action logits at each step
            attention_weights: (batch, trajectory_len) - optional attention over trajectory
        """
        batch_size = synch.shape[0]
        max_len = max_len or self.max_trajectory_len

        # Initialize LSTM hidden/cell states from synchronization
        h_0 = self.synch_to_hidden(synch)  # (batch, hidden*layers)
        c_0 = self.synch_to_cell(synch)

        # Reshape to (num_layers, batch, hidden)
        h_0 = h_0.view(batch_size, self.num_layers, self.hidden_dim).transpose(0, 1).contiguous()
        c_0 = c_0.view(batch_size, self.num_layers, self.hidden_dim).transpose(0, 1).contiguous()

        # Start token: (batch, 1, hidden)
        decoder_input = self.start_token.expand(batch_size, -1).unsqueeze(1)

        # Storage for outputs
        trajectory_logits = []

        # Autoregressive generation
        for t in range(max_len):
            # Decode one step
            decoder_output, (h_0, c_0) = self.decoder(decoder_input, (h_0, c_0))

            # Predict action
            action_logits = self.action_head(decoder_output.squeeze(1))  # (batch, action_dim)
            trajectory_logits.append(action_logits)

            # Teacher forcing: use ground truth or predicted action
            if target_actions is not None and t < target_actions.shape[1] - 1:
                # Training mode
                use_teacher_forcing = torch.rand(1).item() < teacher_forcing_ratio

                if use_teacher_forcing:
                    # Use ground truth next action
                    next_action = target_actions[:, t]
                else:
                    # Use predicted next action
                    next_action = torch.argmax(action_logits, dim=-1)
            else:
                # Inference mode - always use predicted
                next_action = torch.argmax(action_logits, dim=-1)

            # Embed next action for next step
            decoder_input = self.action_embedding(next_action).unsqueeze(1)

        # Stack trajectory: (batch, trajectory_len, action_dim)
        trajectory_logits = torch.stack(trajectory_logits, dim=1)

        return trajectory_logits, None

    def compute_trajectory_loss(
        self,
        synch: torch.Tensor,
        target_actions: torch.Tensor,
        mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Compute loss for trajectory prediction

        Args:
            synch: (batch, synch_dim) - CTM synchronization
            target_actions: (batch, trajectory_len) - ground truth actions
            mask: (batch, trajectory_len) - optional mask for padding

        Returns:
            loss: Scalar trajectory prediction loss
        """
        trajectory_logits, _ = self.forward(synch, target_actions, teacher_forcing_ratio=0.5)

        # Reshape for cross entropy
        batch_size, trajectory_len, action_dim = trajectory_logits.shape

        # Truncate to match target length
        target_len = target_actions.shape[1]
        trajectory_logits = trajectory_logits[:, :target_len, :]

        # Compute cross entropy
        logits_flat = trajectory_logits.reshape(-1, action_dim)
        targets_flat = target_actions.reshape(-1)

        loss = F.cross_entropy(logits_flat, targets_flat, reduction='none')

        # Apply mask if provided
        if mask is not None:
            loss = loss * mask.reshape(-1)
            loss = loss.sum() / mask.sum()
        else:
            loss = loss.mean()

        return loss


class TrajectoryPredictorWithAttention(TrajectoryPredictor):
    """
    Trajectory predictor with attention over CTM thinking process

    Can attend to different parts of CTM's inner thought loop
    to generate better long-term plans.
    """

    def __init__(
        self,
        synch_dim: int = 32,
        hidden_dim: int = 256,
        action_dim: int = 5,
        max_trajectory_len: int = 60,
        num_layers: int = 2,
        dropout: float = 0.1,
        num_attention_heads: int = 4
    ):
        super().__init__(
            synch_dim=synch_dim,
            hidden_dim=hidden_dim,
            action_dim=action_dim,
            max_trajectory_len=max_trajectory_len,
            num_layers=num_layers,
            dropout=dropout
        )

        self.num_attention_heads = num_attention_heads

        # Multi-head attention over CTM ticks
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=num_attention_heads,
            dropout=dropout,
            batch_first=True
        )

        # Context projection
        self.context_proj = nn.Linear(synch_dim, hidden_dim)

    def forward(
        self,
        synch: torch.Tensor,
        ctm_synchs: Optional[torch.Tensor] = None,
        target_actions: Optional[torch.Tensor] = None,
        max_len: Optional[int] = None,
        teacher_forcing_ratio: float = 0.5
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Predict trajectory with attention over CTM thinking

        Args:
            synch: (batch, synch_dim) - Final CTM synchronization
            ctm_synchs: (batch, ticks, synch_dim) - All CTM synchronizations (optional)
            target_actions: (batch, trajectory_len) - Ground truth for training
            max_len: Override max trajectory length
            teacher_forcing_ratio: Teacher forcing ratio

        Returns:
            trajectory_logits: (batch, trajectory_len, action_dim)
            attention_weights: (batch, trajectory_len, ticks)
        """
        batch_size = synch.shape[0]
        max_len = max_len or self.max_trajectory_len

        # Initialize LSTM states
        h_0 = self.synch_to_hidden(synch)
        c_0 = self.synch_to_cell(synch)
        h_0 = h_0.view(batch_size, self.num_layers, self.hidden_dim).transpose(0, 1).contiguous()
        c_0 = c_0.view(batch_size, self.num_layers, self.hidden_dim).transpose(0, 1).contiguous()

        # Prepare attention context if available
        if ctm_synchs is not None:
            # Project CTM synchs to hidden dim: (batch, ticks, hidden)
            attention_context = self.context_proj(ctm_synchs)
        else:
            # Use final synch repeated
            attention_context = self.context_proj(synch.unsqueeze(1))

        # Start token
        decoder_input = self.start_token.expand(batch_size, -1).unsqueeze(1)

        trajectory_logits = []
        attention_weights_list = []

        for t in range(max_len):
            # Decode one step
            decoder_output, (h_0, c_0) = self.decoder(decoder_input, (h_0, c_0))

            # Attend to CTM thinking
            query = decoder_output  # (batch, 1, hidden)
            context, attn_weights = self.attention(
                query,
                attention_context,
                attention_context
            )

            # Combine decoder output with context
            combined = decoder_output + context

            # Predict action
            action_logits = self.action_head(combined.squeeze(1))
            trajectory_logits.append(action_logits)
            attention_weights_list.append(attn_weights.squeeze(1))

            # Teacher forcing
            if target_actions is not None and t < target_actions.shape[1] - 1:
                use_teacher_forcing = torch.rand(1).item() < teacher_forcing_ratio
                if use_teacher_forcing:
                    next_action = target_actions[:, t]
                else:
                    next_action = torch.argmax(action_logits, dim=-1)
            else:
                next_action = torch.argmax(action_logits, dim=-1)

            decoder_input = self.action_embedding(next_action).unsqueeze(1)

        trajectory_logits = torch.stack(trajectory_logits, dim=1)
        attention_weights = torch.stack(attention_weights_list, dim=1)

        return trajectory_logits, attention_weights
