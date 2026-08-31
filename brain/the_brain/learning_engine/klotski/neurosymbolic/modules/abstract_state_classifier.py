"""
Abstract State Classifier for Phase 3

Maps concrete puzzle states to high-level abstract states for hierarchical planning.

Abstract States:
0. DMN_FAR: DMN piece far from goal (distance > 3)
1. DMN_BLOCKED: DMN blocked by other pieces
2. DMN_CLEARING: Actively moving blocking pieces
3. DMN_NEAR: DMN close to goal (distance ≤ 3)
4. SOLVED: DMN at goal position

This enables Markov chain planning at abstract level before concrete CTM execution.
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Tuple, Optional


class AbstractStateClassifier(nn.Module):
    """
    Classifier that maps concrete puzzle states to abstract states.

    Uses both heuristic features (Manhattan distance, blocking) and learned features
    for robust abstract state identification.
    """

    # Abstract state indices
    DMN_FAR = 0
    DMN_BLOCKED = 1
    DMN_CLEARING = 2
    DMN_NEAR = 3
    SOLVED = 4

    # Abstract state names
    STATE_NAMES = [
        "DMN_FAR",
        "DMN_BLOCKED",
        "DMN_CLEARING",
        "DMN_NEAR",
        "SOLVED"
    ]

    # Goal positions for DMN (2x2 block at bottom-center)
    GOAL_POSITIONS = {13, 14, 17, 18}

    def __init__(self, state_dim: int = 20, hidden_dim: int = 128):
        """
        Args:
            state_dim: Dimension of puzzle state (20 for 4x5 grid)
            hidden_dim: Hidden dimension for learned features
        """
        super().__init__()

        self.state_dim = state_dim
        self.hidden_dim = hidden_dim

        # Learned feature extractor (refines heuristic classification)
        self.feature_net = nn.Sequential(
            nn.Linear(state_dim + 5, hidden_dim),  # +5 for heuristic features
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim // 2, 5)  # 5 abstract states
        )

    def compute_manhattan_distance(self, dmn_pos: torch.Tensor) -> torch.Tensor:
        """
        Compute Manhattan distance from DMN to goal

        Args:
            dmn_pos: DMN top-left position (batch_size,)

        Returns:
            distance: Manhattan distance (batch_size,)
        """
        # DMN occupies 2x2, stored as top-left position
        # Goal is positions [13, 14, 17, 18] (bottom-center)
        # Goal center: (1.5, 3.5) in (col, row) coordinates

        # Convert position index to (row, col)
        row = dmn_pos // 5  # 5 columns
        col = dmn_pos % 5

        # Goal center in grid coordinates
        goal_row = 3.5
        goal_col = 1.5

        # Manhattan distance
        distance = torch.abs(row - goal_row) + torch.abs(col - goal_col)

        return distance

    def detect_blocking(self, state: torch.Tensor, dmn_pos: torch.Tensor) -> torch.Tensor:
        """
        Detect if DMN is blocked from moving toward goal

        Args:
            state: Puzzle state (batch_size, 5, 4) - (height, width)
            dmn_pos: DMN top-left position (batch_size,)

        Returns:
            is_blocked: Whether DMN is blocked (batch_size,)
        """
        batch_size = state.shape[0]
        is_blocked = torch.zeros(batch_size, dtype=torch.bool, device=state.device)

        for i in range(batch_size):
            pos = dmn_pos[i].item()
            row = pos // 5
            col = pos % 5

            # Check if DMN can move DOWN (toward goal at row 3)
            # DMN is 2x2, so check positions below it
            can_move_down = True
            if row < 3:  # Not at bottom
                # Check if spaces below DMN are empty
                # DMN occupies (row, col), (row, col+1), (row+1, col), (row+1, col+1)
                # Positions below: (row+2, col), (row+2, col+1)
                if row + 2 < 5:
                    below_left = state[i, row + 2, col]
                    below_right = state[i, row + 2, col + 1] if col + 1 < 4 else 1.0  # treat out of bounds as blocked
                    if below_left != 0.0 or below_right != 0.0:
                        can_move_down = False

            # Check if DMN can move RIGHT (toward goal at col ~1.5)
            can_move_right = True
            if col < 2:  # Not at goal column
                # Check if spaces to right of DMN are empty
                # Positions to right: (row, col+2), (row+1, col+2)
                if col + 2 < 4:
                    right_top = state[i, row, col + 2]
                    right_bottom = state[i, row + 1, col + 2] if row + 1 < 5 else 1.0
                    if right_top != 0.0 or right_bottom != 0.0:
                        can_move_right = False

            # Blocked if cannot move in preferred direction
            if not can_move_down and not can_move_right:
                is_blocked[i] = True

        return is_blocked

    def extract_heuristic_features(self, state: torch.Tensor) -> Tuple[torch.Tensor, dict]:
        """
        Extract heuristic features from puzzle state

        Args:
            state: Puzzle state (batch_size, 5, 4)

        Returns:
            features: Heuristic features (batch_size, 5)
            metadata: Dict with intermediate values for analysis
        """
        batch_size = state.shape[0]
        device = state.device

        # Find DMN position (assume it's encoded as specific value, e.g., piece ID)
        # For simplicity, assume DMN is the largest connected component
        # In actual implementation, would use piece encoding from PuzzleEnv

        # Placeholder: Find 2x2 block (DMN)
        dmn_pos = torch.zeros(batch_size, dtype=torch.long, device=device)
        for i in range(batch_size):
            # Scan for 2x2 block (heuristic: find matching 2x2 region)
            found = False
            for r in range(4):  # 5 rows - 2 = 3 possible top positions
                for c in range(3):  # 4 cols - 2 = 2 possible left positions
                    # Check if 2x2 region has same non-zero value
                    if state[i, r, c] != 0:
                        val = state[i, r, c]
                        if (state[i, r, c+1] == val and
                            state[i, r+1, c] == val and
                            state[i, r+1, c+1] == val):
                            dmn_pos[i] = r * 5 + c
                            found = True
                            break
                if found:
                    break

        # Feature 1: Manhattan distance to goal
        manhattan_dist = self.compute_manhattan_distance(dmn_pos)

        # Feature 2: Is blocked
        is_blocked = self.detect_blocking(state, dmn_pos).float()

        # Feature 3: Is at goal
        is_solved = torch.tensor([
            dmn_pos[i].item() in [13, 8]  # positions where top-left of 2x2 aligns with goal
            for i in range(batch_size)
        ], dtype=torch.float32, device=device)

        # Feature 4: Number of pieces blocking path (heuristic)
        num_blockers = torch.zeros(batch_size, dtype=torch.float32, device=device)
        for i in range(batch_size):
            pos = dmn_pos[i].item()
            row = pos // 5
            col = pos % 5

            # Count non-zero pieces between DMN and goal
            blockers = 0
            # Path is roughly down and slightly left
            for r in range(row + 2, 5):  # rows below DMN
                for c in range(max(0, col - 1), min(4, col + 3)):  # columns around DMN
                    if state[i, r, c] != 0:
                        blockers += 1
            num_blockers[i] = float(blockers)

        # Feature 5: Distance to goal (normalized)
        normalized_dist = manhattan_dist / 7.0  # max distance ~7

        features = torch.stack([
            manhattan_dist,
            is_blocked,
            is_solved,
            num_blockers,
            normalized_dist
        ], dim=1)  # (batch_size, 5)

        metadata = {
            'dmn_pos': dmn_pos,
            'manhattan_dist': manhattan_dist,
            'is_blocked': is_blocked,
            'is_solved': is_solved,
            'num_blockers': num_blockers
        }

        return features, metadata

    def heuristic_classification(self, features: torch.Tensor, metadata: dict) -> torch.Tensor:
        """
        Classify abstract state using heuristics

        Args:
            features: Heuristic features (batch_size, 5)
            metadata: Intermediate values

        Returns:
            abstract_state: Abstract state indices (batch_size,)
        """
        batch_size = features.shape[0]
        device = features.device

        manhattan_dist = metadata['manhattan_dist']
        is_blocked = metadata['is_blocked']
        is_solved = metadata['is_solved']
        num_blockers = metadata['num_blockers']

        abstract_state = torch.zeros(batch_size, dtype=torch.long, device=device)

        for i in range(batch_size):
            if is_solved[i]:
                abstract_state[i] = self.SOLVED
            elif manhattan_dist[i] <= 3.0 and not is_blocked[i]:
                abstract_state[i] = self.DMN_NEAR
            elif is_blocked[i] and num_blockers[i] > 0:
                abstract_state[i] = self.DMN_BLOCKED
            elif num_blockers[i] > 2:
                abstract_state[i] = self.DMN_CLEARING
            else:
                abstract_state[i] = self.DMN_FAR

        return abstract_state

    def forward(
        self,
        state: torch.Tensor,
        use_learned: bool = True
    ) -> Tuple[torch.Tensor, torch.Tensor, dict]:
        """
        Classify abstract state

        Args:
            state: Puzzle state (batch_size, 5, 4)
            use_learned: Whether to use learned classifier (True) or pure heuristic (False)

        Returns:
            logits: Abstract state logits (batch_size, 5)
            abstract_state: Predicted abstract state (batch_size,)
            metadata: Intermediate values for analysis
        """
        # Flatten state
        batch_size = state.shape[0]
        state_flat = state.view(batch_size, -1)  # (batch_size, 20)

        # Extract heuristic features
        heuristic_features, metadata = self.extract_heuristic_features(state)

        if use_learned:
            # Combine state and heuristic features
            combined = torch.cat([state_flat, heuristic_features], dim=1)  # (batch_size, 25)

            # Learned classification
            logits = self.feature_net(combined)  # (batch_size, 5)
            abstract_state = torch.argmax(logits, dim=1)
        else:
            # Pure heuristic classification
            abstract_state = self.heuristic_classification(heuristic_features, metadata)

            # Convert to one-hot logits
            logits = torch.zeros(batch_size, 5, device=state.device)
            logits.scatter_(1, abstract_state.unsqueeze(1), 1.0)

        metadata['heuristic_state'] = self.heuristic_classification(heuristic_features, metadata)
        metadata['learned_state'] = abstract_state

        return logits, abstract_state, metadata

    def get_state_name(self, state_idx: int) -> str:
        """Get human-readable name for abstract state"""
        return self.STATE_NAMES[state_idx]
