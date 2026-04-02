"""
Data Augmentation for Klotski Puzzles

Generates augmented puzzle states through geometric transformations:
- Horizontal reflection
- Vertical reflection
- 180° rotation
- Piece relabeling (for identical pieces)

Increases training data diversity and improves generalization.
"""

import numpy as np
import torch
from typing import List, Tuple, Dict
from dataclasses import dataclass


@dataclass
class AugmentedState:
    """Augmented puzzle state with transformation info"""
    state: np.ndarray  # (4, 5) augmented board
    transform: str  # Name of transformation
    action_mapping: Dict[int, int]  # Old action -> new action mapping
    inverse_mapping: Dict[int, int]  # New action -> old action mapping


class PuzzleAugmenter:
    """
    Data augmentation for Klotski puzzles

    Applies geometric transformations while maintaining puzzle semantics.
    """

    def __init__(self, board_height: int = 4, board_width: int = 5):
        self.board_height = board_height
        self.board_width = board_width

    def horizontal_flip(self, state: np.ndarray) -> np.ndarray:
        """
        Flip board horizontally (left <-> right)

        Args:
            state: (4, 5) board state

        Returns:
            flipped: (4, 5) horizontally flipped board
        """
        return np.fliplr(state)

    def vertical_flip(self, state: np.ndarray) -> np.ndarray:
        """
        Flip board vertically (top <-> bottom)

        Args:
            state: (4, 5) board state

        Returns:
            flipped: (4, 5) vertically flipped board
        """
        return np.flipud(state)

    def rotate_180(self, state: np.ndarray) -> np.ndarray:
        """
        Rotate board 180 degrees

        Args:
            state: (4, 5) board state

        Returns:
            rotated: (4, 5) rotated board
        """
        return np.rot90(state, k=2)

    def get_action_mapping_hflip(self) -> Dict[int, int]:
        """
        Get action mapping for horizontal flip

        Actions are encoded as: piece_id * 4 + direction
        Directions: 0=up, 1=down, 2=left, 3=right

        After hflip: left <-> right
        """
        mapping = {}
        for action in range(40):  # 10 pieces × 4 directions
            piece_id = action // 4
            direction = action % 4

            # Swap left <-> right
            if direction == 2:  # left -> right
                new_direction = 3
            elif direction == 3:  # right -> left
                new_direction = 2
            else:  # up/down unchanged
                new_direction = direction

            new_action = piece_id * 4 + new_direction
            mapping[action] = new_action

        return mapping

    def get_action_mapping_vflip(self) -> Dict[int, int]:
        """
        Get action mapping for vertical flip

        After vflip: up <-> down
        """
        mapping = {}
        for action in range(40):
            piece_id = action // 4
            direction = action % 4

            # Swap up <-> down
            if direction == 0:  # up -> down
                new_direction = 1
            elif direction == 1:  # down -> up
                new_direction = 0
            else:  # left/right unchanged
                new_direction = direction

            new_action = piece_id * 4 + new_direction
            mapping[action] = new_action

        return mapping

    def get_action_mapping_rot180(self) -> Dict[int, int]:
        """
        Get action mapping for 180° rotation

        After rotation: up <-> down, left <-> right
        """
        mapping = {}
        for action in range(40):
            piece_id = action // 4
            direction = action % 4

            # Reverse direction
            direction_map = {0: 1, 1: 0, 2: 3, 3: 2}
            new_direction = direction_map[direction]

            new_action = piece_id * 4 + new_direction
            mapping[action] = new_action

        return mapping

    def augment(self, state: np.ndarray, transform: str) -> AugmentedState:
        """
        Apply transformation to state

        Args:
            state: (4, 5) board state
            transform: Transformation name
                - "identity": No transformation
                - "hflip": Horizontal flip
                - "vflip": Vertical flip
                - "rot180": 180° rotation

        Returns:
            AugmentedState with transformed board and action mappings
        """
        if transform == "identity":
            augmented = state.copy()
            action_mapping = {i: i for i in range(40)}

        elif transform == "hflip":
            augmented = self.horizontal_flip(state)
            action_mapping = self.get_action_mapping_hflip()

        elif transform == "vflip":
            augmented = self.vertical_flip(state)
            action_mapping = self.get_action_mapping_vflip()

        elif transform == "rot180":
            augmented = self.rotate_180(state)
            action_mapping = self.get_action_mapping_rot180()

        else:
            raise ValueError(f"Unknown transform: {transform}")

        # Create inverse mapping
        inverse_mapping = {v: k for k, v in action_mapping.items()}

        return AugmentedState(
            state=augmented,
            transform=transform,
            action_mapping=action_mapping,
            inverse_mapping=inverse_mapping
        )

    def augment_batch(
        self,
        states: np.ndarray,
        transforms: List[str] = None
    ) -> Tuple[np.ndarray, List[Dict[int, int]]]:
        """
        Augment batch of states

        Args:
            states: (batch, 4, 5) board states
            transforms: List of transform names (one per state)
                If None, randomly sample transforms

        Returns:
            Tuple of (augmented_states, action_mappings)
        """
        batch_size = len(states)

        if transforms is None:
            # Randomly sample transforms
            transform_options = ["identity", "hflip", "vflip", "rot180"]
            transforms = np.random.choice(transform_options, size=batch_size)

        augmented_states = []
        action_mappings = []

        for state, transform in zip(states, transforms):
            aug = self.augment(state, transform)
            augmented_states.append(aug.state)
            action_mappings.append(aug.action_mapping)

        return np.array(augmented_states), action_mappings

    def augment_trajectory(
        self,
        states: List[np.ndarray],
        actions: List[int],
        transform: str
    ) -> Tuple[List[np.ndarray], List[int]]:
        """
        Augment full trajectory (states + actions)

        Args:
            states: List of (4, 5) states
            actions: List of action indices
            transform: Transformation to apply

        Returns:
            Tuple of (augmented_states, augmented_actions)
        """
        # Get action mapping
        aug = self.augment(states[0], transform)
        action_mapping = aug.action_mapping

        # Augment all states
        augmented_states = [self.augment(s, transform).state for s in states]

        # Map all actions
        augmented_actions = [action_mapping[a] for a in actions]

        return augmented_states, augmented_actions


class AugmentedDataset:
    """
    Dataset wrapper with on-the-fly augmentation

    Wraps an existing dataset and applies random augmentations.
    """

    def __init__(
        self,
        states: np.ndarray,
        actions: np.ndarray,
        rewards: np.ndarray,
        augment_prob: float = 0.5
    ):
        """
        Initialize augmented dataset

        Args:
            states: (N, 4, 5) board states
            actions: (N,) action indices
            rewards: (N,) rewards
            augment_prob: Probability of applying augmentation
        """
        self.states = states
        self.actions = actions
        self.rewards = rewards
        self.augment_prob = augment_prob

        self.augmenter = PuzzleAugmenter()
        self.transforms = ["identity", "hflip", "vflip", "rot180"]

    def __len__(self):
        return len(self.states)

    def __getitem__(self, idx):
        """Get item with random augmentation"""
        state = self.states[idx]
        action = self.actions[idx]
        reward = self.rewards[idx]

        # Randomly apply augmentation
        if np.random.rand() < self.augment_prob:
            transform = np.random.choice(self.transforms)
            aug = self.augmenter.augment(state, transform)

            state = aug.state
            action = aug.action_mapping[action]

        return {
            'state': torch.from_numpy(state).float(),
            'action': torch.tensor(action).long(),
            'reward': torch.tensor(reward).float()
        }


if __name__ == "__main__":
    # Test data augmentation
    print("Testing Puzzle Data Augmentation...")
    print("="*60)

    # Create sample board
    board = np.array([
        [1, 1, 2, 2, 3],
        [1, 1, 2, 2, 4],
        [5, 6, 6, 7, 4],
        [5, 0, 0, 7, 8]
    ])

    print("Original board:")
    print(board)

    # Create augmenter
    augmenter = PuzzleAugmenter()

    # Test each transformation
    transforms = ["hflip", "vflip", "rot180"]

    for transform in transforms:
        print(f"\n{transform.upper()}:")
        aug = augmenter.augment(board, transform)
        print(aug.state)
        print(f"Action 14 (piece 3, right) -> {aug.action_mapping[14]}")

    # Test batch augmentation
    print("\nBatch augmentation:")
    states = np.array([board, board, board, board])
    augmented, mappings = augmenter.augment_batch(states)

    print(f"Augmented {len(states)} states")
    print(f"Transforms applied: {len(set([id(m) for m in mappings]))} unique")

    # Test trajectory augmentation
    print("\nTrajectory augmentation:")
    trajectory_states = [board, board.copy(), board.copy()]
    trajectory_actions = [14, 3, 27]

    aug_states, aug_actions = augmenter.augment_trajectory(
        trajectory_states,
        trajectory_actions,
        transform="hflip"
    )

    print(f"Original actions: {trajectory_actions}")
    print(f"Augmented actions: {aug_actions}")

    # Test dataset wrapper
    print("\nDataset wrapper:")
    dataset = AugmentedDataset(
        states=np.array([board] * 10),
        actions=np.arange(10),
        rewards=np.random.randn(10),
        augment_prob=1.0
    )

    print(f"Dataset size: {len(dataset)}")
    sample = dataset[0]
    print(f"Sample keys: {sample.keys()}")
    print(f"Sample state shape: {sample['state'].shape}")

    print("\n" + "="*60)
    print("Data augmentation test complete!")
