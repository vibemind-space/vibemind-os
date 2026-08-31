"""
Temporal Dataset - PyTorch Dataset for Temporal CTM Training

Provides:
- TemporalTrajectory: Single episode dataclass
- TemporalDataset: PyTorch Dataset for batched training
- Collate functions for variable-length trajectories
"""

import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json


class Regime(Enum):
    """Operational regimes"""
    EXPLOIT = 0
    EXPLORE = 1
    REPAIR = 2
    TRANSITION = 3
    DEADLOCK = 4


@dataclass
class TemporalStep:
    """Single step in a temporal trajectory"""
    # State information
    state_vector: np.ndarray          # Brain state vector [state_dim]
    sync_vector: np.ndarray           # 9-D synchrony signature

    # Action information
    target_cell: int                  # Target drumpad cell (0-23 for 3x8)
    target_should_act: bool           # Should emit action at this step

    # Regime information
    target_regime: Regime             # Expected regime
    transition_expected: bool = False # Is regime transition expected here

    # Optional metadata
    tool_name: Optional[str] = None
    tool_success: Optional[bool] = None
    timestamp_ms: int = 0


@dataclass
class TemporalTrajectory:
    """
    Complete temporal trajectory (episode)

    Contains all steps for one task execution.
    """
    steps: List[TemporalStep]
    task_description: str
    success: bool
    task_id: Optional[str] = None
    total_duration_ms: int = 0

    @property
    def num_steps(self) -> int:
        return len(self.steps)

    @property
    def state_vectors(self) -> np.ndarray:
        """Stack all state vectors [num_steps, state_dim]"""
        return np.stack([s.state_vector for s in self.steps])

    @property
    def sync_vectors(self) -> np.ndarray:
        """Stack all sync vectors [num_steps, 9]"""
        return np.stack([s.sync_vector for s in self.steps])

    @property
    def target_cells(self) -> np.ndarray:
        """Array of target cells [num_steps]"""
        return np.array([s.target_cell for s in self.steps])

    @property
    def target_timing(self) -> np.ndarray:
        """Array of should_act flags [num_steps]"""
        return np.array([s.target_should_act for s in self.steps], dtype=np.float32)

    @property
    def target_regimes(self) -> np.ndarray:
        """Array of regime indices [num_steps]"""
        return np.array([s.target_regime.value for s in self.steps])

    @property
    def transition_mask(self) -> np.ndarray:
        """Boolean mask for expected transitions [num_steps]"""
        return np.array([s.transition_expected for s in self.steps])

    def to_dict(self) -> Dict:
        """Serialize trajectory to dict"""
        return {
            'steps': [
                {
                    'state_vector': s.state_vector.tolist(),
                    'sync_vector': s.sync_vector.tolist(),
                    'target_cell': s.target_cell,
                    'target_should_act': s.target_should_act,
                    'target_regime': s.target_regime.name,
                    'transition_expected': s.transition_expected,
                    'tool_name': s.tool_name,
                    'tool_success': s.tool_success,
                    'timestamp_ms': s.timestamp_ms
                }
                for s in self.steps
            ],
            'task_description': self.task_description,
            'success': self.success,
            'task_id': self.task_id,
            'total_duration_ms': self.total_duration_ms
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'TemporalTrajectory':
        """Deserialize trajectory from dict"""
        steps = [
            TemporalStep(
                state_vector=np.array(s['state_vector']),
                sync_vector=np.array(s['sync_vector']),
                target_cell=s['target_cell'],
                target_should_act=s['target_should_act'],
                target_regime=Regime[s['target_regime']],
                transition_expected=s.get('transition_expected', False),
                tool_name=s.get('tool_name'),
                tool_success=s.get('tool_success'),
                timestamp_ms=s.get('timestamp_ms', 0)
            )
            for s in d['steps']
        ]
        return cls(
            steps=steps,
            task_description=d['task_description'],
            success=d['success'],
            task_id=d.get('task_id'),
            total_duration_ms=d.get('total_duration_ms', 0)
        )

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'TemporalTrajectory':
        """Deserialize from JSON string"""
        return cls.from_dict(json.loads(json_str))


@dataclass
class TemporalBatch:
    """
    Batched temporal data for training

    All tensors have shape [batch, max_seq_len, ...]
    with padding for variable-length sequences.
    """
    state_vectors: torch.Tensor       # [batch, max_seq, state_dim]
    sync_vectors: torch.Tensor        # [batch, max_seq, 9]
    target_cells: torch.Tensor        # [batch, max_seq]
    target_timing: torch.Tensor       # [batch, max_seq]
    target_regimes: torch.Tensor      # [batch, max_seq]
    transition_mask: torch.Tensor     # [batch, max_seq]
    sequence_lengths: torch.Tensor    # [batch]
    padding_mask: torch.Tensor        # [batch, max_seq] True for valid positions
    success_labels: torch.Tensor      # [batch]


class TemporalDataset(Dataset):
    """
    PyTorch Dataset for temporal trajectories

    Supports:
    - Loading from trajectory list
    - Loading from JSON file
    - Filtering by success/failure
    - Filtering by regime
    """

    def __init__(
        self,
        trajectories: Optional[List[TemporalTrajectory]] = None,
        json_path: Optional[str] = None,
        filter_success: Optional[bool] = None,
        filter_regimes: Optional[List[Regime]] = None,
        state_dim: int = 192
    ):
        """
        Initialize dataset

        Args:
            trajectories: List of trajectories (optional)
            json_path: Path to JSON file with trajectories (optional)
            filter_success: If set, only include trajectories with this success value
            filter_regimes: If set, only include steps with these regimes
            state_dim: Expected state vector dimension
        """
        self.state_dim = state_dim
        self.trajectories: List[TemporalTrajectory] = []

        # Load trajectories
        if trajectories is not None:
            self.trajectories = trajectories
        elif json_path is not None:
            self.load_from_json(json_path)

        # Apply filters
        if filter_success is not None:
            self.trajectories = [
                t for t in self.trajectories
                if t.success == filter_success
            ]

        if filter_regimes is not None:
            regime_set = set(filter_regimes)
            # Filter trajectories that have at least one step with target regime
            self.trajectories = [
                t for t in self.trajectories
                if any(s.target_regime in regime_set for s in t.steps)
            ]

    def __len__(self) -> int:
        return len(self.trajectories)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """
        Get single trajectory as tensors

        Returns dict with:
        - state_vectors: [seq_len, state_dim]
        - sync_vectors: [seq_len, 9]
        - target_cells: [seq_len]
        - target_timing: [seq_len]
        - target_regimes: [seq_len]
        - transition_mask: [seq_len]
        - success: scalar
        """
        traj = self.trajectories[idx]

        return {
            'state_vectors': torch.tensor(traj.state_vectors, dtype=torch.float32),
            'sync_vectors': torch.tensor(traj.sync_vectors, dtype=torch.float32),
            'target_cells': torch.tensor(traj.target_cells, dtype=torch.long),
            'target_timing': torch.tensor(traj.target_timing, dtype=torch.float32),
            'target_regimes': torch.tensor(traj.target_regimes, dtype=torch.long),
            'transition_mask': torch.tensor(traj.transition_mask, dtype=torch.bool),
            'success': torch.tensor(traj.success, dtype=torch.float32),
            'seq_len': torch.tensor(traj.num_steps, dtype=torch.long)
        }

    def load_from_json(self, path: str):
        """Load trajectories from JSON file"""
        with open(path, 'r') as f:
            data = json.load(f)
        self.trajectories = [
            TemporalTrajectory.from_dict(d)
            for d in data['trajectories']
        ]

    def save_to_json(self, path: str):
        """Save trajectories to JSON file"""
        data = {
            'trajectories': [t.to_dict() for t in self.trajectories],
            'count': len(self.trajectories),
            'state_dim': self.state_dim
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def add_trajectory(self, trajectory: TemporalTrajectory):
        """Add a trajectory to the dataset"""
        self.trajectories.append(trajectory)

    def get_statistics(self) -> Dict:
        """Get dataset statistics"""
        if not self.trajectories:
            return {'empty': True}

        lengths = [t.num_steps for t in self.trajectories]
        success_count = sum(1 for t in self.trajectories if t.success)

        # Regime distribution
        regime_counts = {r.name: 0 for r in Regime}
        for t in self.trajectories:
            for s in t.steps:
                regime_counts[s.target_regime.name] += 1

        return {
            'num_trajectories': len(self.trajectories),
            'total_steps': sum(lengths),
            'avg_length': np.mean(lengths),
            'min_length': min(lengths),
            'max_length': max(lengths),
            'success_rate': success_count / len(self.trajectories),
            'regime_distribution': regime_counts
        }


def collate_temporal_batch(batch: List[Dict[str, torch.Tensor]]) -> TemporalBatch:
    """
    Collate function for DataLoader

    Pads variable-length sequences to max length in batch.

    Args:
        batch: List of dicts from TemporalDataset.__getitem__

    Returns:
        TemporalBatch with padded tensors
    """
    # Get max sequence length in batch
    seq_lens = [item['seq_len'].item() for item in batch]
    max_len = max(seq_lens)
    batch_size = len(batch)

    # Get dimensions
    state_dim = batch[0]['state_vectors'].shape[1]
    sync_dim = batch[0]['sync_vectors'].shape[1]

    # Initialize padded tensors
    state_vectors = torch.zeros(batch_size, max_len, state_dim)
    sync_vectors = torch.zeros(batch_size, max_len, sync_dim)
    target_cells = torch.zeros(batch_size, max_len, dtype=torch.long)
    target_timing = torch.zeros(batch_size, max_len)
    target_regimes = torch.zeros(batch_size, max_len, dtype=torch.long)
    transition_mask = torch.zeros(batch_size, max_len, dtype=torch.bool)
    padding_mask = torch.zeros(batch_size, max_len, dtype=torch.bool)

    # Fill tensors
    for i, item in enumerate(batch):
        seq_len = item['seq_len'].item()
        state_vectors[i, :seq_len] = item['state_vectors']
        sync_vectors[i, :seq_len] = item['sync_vectors']
        target_cells[i, :seq_len] = item['target_cells']
        target_timing[i, :seq_len] = item['target_timing']
        target_regimes[i, :seq_len] = item['target_regimes']
        transition_mask[i, :seq_len] = item['transition_mask']
        padding_mask[i, :seq_len] = True

    return TemporalBatch(
        state_vectors=state_vectors,
        sync_vectors=sync_vectors,
        target_cells=target_cells,
        target_timing=target_timing,
        target_regimes=target_regimes,
        transition_mask=transition_mask,
        sequence_lengths=torch.tensor(seq_lens),
        padding_mask=padding_mask,
        success_labels=torch.stack([item['success'] for item in batch])
    )


def create_dataloader(
    dataset: TemporalDataset,
    batch_size: int = 32,
    shuffle: bool = True,
    num_workers: int = 0
) -> DataLoader:
    """Create DataLoader with proper collate function"""
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        collate_fn=collate_temporal_batch
    )


if __name__ == "__main__":
    print("=" * 70)
    print("TEMPORAL DATASET - Testing")
    print("=" * 70)
    print()

    # Create test trajectories
    print("[1] Creating test trajectories...")

    def create_test_trajectory(
        num_steps: int,
        regime: Regime,
        success: bool
    ) -> TemporalTrajectory:
        """Create a test trajectory"""
        steps = []
        for i in range(num_steps):
            step = TemporalStep(
                state_vector=np.random.randn(192),
                sync_vector=np.random.rand(9) * 2 - 1,
                target_cell=np.random.randint(0, 24),
                target_should_act=(i % 2 == 0),  # Alternate
                target_regime=regime,
                transition_expected=(i == num_steps // 2),
                tool_name=f"tool_{i}",
                tool_success=True,
                timestamp_ms=i * 100
            )
            steps.append(step)

        return TemporalTrajectory(
            steps=steps,
            task_description=f"Test {regime.name} task",
            success=success,
            task_id=f"test_{regime.name}_{success}"
        )

    trajectories = [
        create_test_trajectory(5, Regime.EXPLOIT, True),
        create_test_trajectory(8, Regime.EXPLORE, True),
        create_test_trajectory(3, Regime.REPAIR, False),
        create_test_trajectory(6, Regime.EXPLOIT, True),
    ]

    print(f"    Created {len(trajectories)} trajectories")
    print()

    # Create dataset
    print("[2] Creating TemporalDataset...")
    dataset = TemporalDataset(trajectories=trajectories)
    stats = dataset.get_statistics()
    print(f"    Num trajectories: {stats['num_trajectories']}")
    print(f"    Total steps: {stats['total_steps']}")
    print(f"    Avg length: {stats['avg_length']:.1f}")
    print(f"    Success rate: {stats['success_rate']:.1%}")
    print()

    # Test single item
    print("[3] Testing single item retrieval...")
    item = dataset[0]
    print(f"    state_vectors shape: {item['state_vectors'].shape}")
    print(f"    sync_vectors shape: {item['sync_vectors'].shape}")
    print(f"    target_cells shape: {item['target_cells'].shape}")
    print(f"    seq_len: {item['seq_len'].item()}")
    print()

    # Test DataLoader
    print("[4] Testing DataLoader...")
    dataloader = create_dataloader(dataset, batch_size=2, shuffle=False)
    batch = next(iter(dataloader))
    print(f"    Batch state_vectors shape: {batch.state_vectors.shape}")
    print(f"    Batch sync_vectors shape: {batch.sync_vectors.shape}")
    print(f"    Batch target_cells shape: {batch.target_cells.shape}")
    print(f"    Batch sequence_lengths: {batch.sequence_lengths.tolist()}")
    print(f"    Batch padding_mask sum: {batch.padding_mask.sum().item()}")
    print()

    # Test JSON serialization
    print("[5] Testing JSON serialization...")
    traj = trajectories[0]
    json_str = traj.to_json()
    traj_restored = TemporalTrajectory.from_json(json_str)
    print(f"    Original steps: {traj.num_steps}")
    print(f"    Restored steps: {traj_restored.num_steps}")
    print(f"    JSON size: {len(json_str)} bytes")
    print()

    print("=" * 70)
    print("TEMPORAL DATASET TESTS COMPLETE")
    print("=" * 70)
