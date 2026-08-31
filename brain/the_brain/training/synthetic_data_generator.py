"""
Synthetic Data Generator for Temporal CTM Training

Generates training trajectories for each operational regime:
- EXPLOIT: Sequential goal-directed actions (A-dominant, all in-phase)
- EXPLORE: Branching alternatives (B-dominant, A-C anti-phase)
- REPAIR: Error correction loops (C-dominant, converging phases)
- TRANSITION: Regime changes (smooth phase transitions)
- DEADLOCK: Stuck states (all suppressed, drifting phases)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import random

# Import from temporal_dataset
from .temporal_dataset import (
    TemporalStep,
    TemporalTrajectory,
    TemporalDataset,
    Regime
)


@dataclass
class SyncPattern:
    """Target synchrony pattern for a regime"""
    # Amplitudes [|A|, |B|, |C|]
    amp_A: float
    amp_B: float
    amp_C: float

    # Phase differences
    cos_ab: float  # cos(θ_A - θ_B)
    sin_ab: float  # sin(θ_A - θ_B)
    cos_ac: float  # cos(θ_A - θ_C)
    sin_ac: float  # sin(θ_A - θ_C)
    cos_bc: float  # cos(θ_B - θ_C)
    sin_bc: float  # sin(θ_B - θ_C)

    def to_vector(self, noise: float = 0.0) -> np.ndarray:
        """Convert to 9-D synchrony vector with optional noise"""
        vec = np.array([
            self.amp_A, self.amp_B, self.amp_C,
            self.cos_ab, self.sin_ab,
            self.cos_ac, self.sin_ac,
            self.cos_bc, self.sin_bc
        ])
        if noise > 0:
            vec = vec + np.random.randn(9) * noise
            # Clamp amplitudes to [0, 1]
            vec[:3] = np.clip(vec[:3], 0.0, 1.0)
            # Clamp phase components to [-1, 1]
            vec[3:] = np.clip(vec[3:], -1.0, 1.0)
        return vec


# Target synchrony patterns for each regime
REGIME_SYNC_PATTERNS = {
    Regime.EXPLOIT: SyncPattern(
        amp_A=0.8, amp_B=0.2, amp_C=0.1,  # A dominant
        cos_ab=1.0, sin_ab=0.0,           # A-B in-phase
        cos_ac=1.0, sin_ac=0.0,           # A-C in-phase
        cos_bc=1.0, sin_bc=0.0            # B-C in-phase (all synchronized)
    ),
    Regime.EXPLORE: SyncPattern(
        amp_A=0.2, amp_B=0.8, amp_C=0.2,  # B dominant
        cos_ab=0.0, sin_ab=1.0,           # A-B free (90° offset)
        cos_ac=-1.0, sin_ac=0.0,          # A-C anti-phase
        cos_bc=0.0, sin_bc=-1.0           # B-C free
    ),
    Regime.REPAIR: SyncPattern(
        amp_A=0.3, amp_B=0.3, amp_C=0.7,  # C dominant
        cos_ab=0.5, sin_ab=0.5,           # A-B partially locked
        cos_ac=1.0, sin_ac=0.0,           # A-C in-phase (C leads)
        cos_bc=0.5, sin_bc=0.5            # B-C partially locked
    ),
    Regime.TRANSITION: SyncPattern(
        amp_A=0.4, amp_B=0.4, amp_C=0.4,  # Balanced
        cos_ab=0.0, sin_ab=0.0,           # No lock
        cos_ac=0.0, sin_ac=0.0,
        cos_bc=0.0, sin_bc=0.0
    ),
    Regime.DEADLOCK: SyncPattern(
        amp_A=0.1, amp_B=0.1, amp_C=0.1,  # All suppressed
        cos_ab=0.0, sin_ab=0.0,           # Drifting
        cos_ac=0.0, sin_ac=0.0,
        cos_bc=0.0, sin_bc=0.0
    ),
}


class SyntheticDataGenerator:
    """
    Generate synthetic training trajectories for Temporal CTM

    Creates trajectories with realistic patterns for each regime,
    including proper synchrony signatures and timing decisions.
    """

    def __init__(
        self,
        state_dim: int = 192,
        num_cells: int = 24,  # 3x8 drumpad
        noise_level: float = 0.1,
        seed: Optional[int] = None
    ):
        """
        Initialize generator

        Args:
            state_dim: Dimension of state vectors
            num_cells: Number of drumpad cells (3x8 = 24)
            noise_level: Amount of noise to add to patterns
            seed: Random seed for reproducibility
        """
        self.state_dim = state_dim
        self.num_cells = num_cells
        self.noise_level = noise_level

        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)

        # Drumpad layout: 3 rows (A/B/C) x 8 columns (phase buckets)
        self.num_rows = 3
        self.num_cols = num_cells // 3

    def _generate_state_vector(
        self,
        regime: Regime,
        progress: float = 0.0,
        intent_embedding: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Generate a state vector for a given regime

        Args:
            regime: Current regime
            progress: Task progress (0.0 to 1.0)
            intent_embedding: Optional intent embedding to include

        Returns:
            State vector [state_dim]
        """
        state = np.zeros(self.state_dim)

        # First 64 dims: Regime-specific encoding
        regime_idx = list(Regime).index(regime)
        regime_one_hot = np.zeros(5)
        regime_one_hot[regime_idx] = 1.0
        state[:5] = regime_one_hot

        # Next 32 dims: Progress encoding
        progress_encoding = np.array([
            progress,
            np.sin(progress * np.pi),
            np.cos(progress * np.pi),
            1.0 - progress
        ])
        state[5:9] = progress_encoding

        # Next 64 dims: Random context (simulates other brain state)
        state[64:128] = np.random.randn(64) * 0.3

        # Last 64 dims: Intent embedding or noise
        if intent_embedding is not None:
            state[128:192] = intent_embedding[:64]
        else:
            state[128:192] = np.random.randn(64) * 0.2

        return state

    def _select_cell(self, channel: int, phase_bucket: int) -> int:
        """
        Select drumpad cell from channel and phase bucket

        Args:
            channel: 0=A (Advance), 1=B (Explore), 2=C (Correct)
            phase_bucket: 0-7 (phase position)

        Returns:
            Cell index (0-23)
        """
        return channel * self.num_cols + phase_bucket

    def generate_exploit_trajectory(
        self,
        num_steps: int = 5,
        task_description: str = "Execute goal-directed task"
    ) -> TemporalTrajectory:
        """
        Generate EXPLOIT regime trajectory

        Characteristics:
        - A-dominant (advance channel)
        - Sequential actions, increasing phase
        - High action frequency
        - All oscillators in-phase
        """
        steps = []
        pattern = REGIME_SYNC_PATTERNS[Regime.EXPLOIT]

        for i in range(num_steps):
            progress = i / max(num_steps - 1, 1)
            phase_bucket = i % self.num_cols

            step = TemporalStep(
                state_vector=self._generate_state_vector(Regime.EXPLOIT, progress),
                sync_vector=pattern.to_vector(self.noise_level),
                target_cell=self._select_cell(0, phase_bucket),  # A channel
                target_should_act=True,  # High action frequency in exploit
                target_regime=Regime.EXPLOIT,
                transition_expected=False,
                tool_name=f"advance_step_{i}",
                tool_success=True,
                timestamp_ms=i * 100
            )
            steps.append(step)

        return TemporalTrajectory(
            steps=steps,
            task_description=task_description,
            success=True,
            task_id=f"exploit_{random.randint(1000, 9999)}"
        )

    def generate_explore_trajectory(
        self,
        num_steps: int = 8,
        task_description: str = "Explore alternatives"
    ) -> TemporalTrajectory:
        """
        Generate EXPLORE regime trajectory

        Characteristics:
        - B-dominant (explore channel)
        - Varied phase buckets (trying alternatives)
        - Lower action frequency (more waiting)
        - A-C anti-phase
        """
        steps = []
        pattern = REGIME_SYNC_PATTERNS[Regime.EXPLORE]

        for i in range(num_steps):
            progress = i / max(num_steps - 1, 1)
            # Varied phase buckets during exploration
            phase_bucket = random.randint(0, self.num_cols - 1)

            step = TemporalStep(
                state_vector=self._generate_state_vector(Regime.EXPLORE, progress),
                sync_vector=pattern.to_vector(self.noise_level),
                target_cell=self._select_cell(1, phase_bucket),  # B channel
                target_should_act=(i % 2 == 0),  # Lower action frequency
                target_regime=Regime.EXPLORE,
                transition_expected=False,
                tool_name=f"explore_option_{i}",
                tool_success=True,
                timestamp_ms=i * 150
            )
            steps.append(step)

        return TemporalTrajectory(
            steps=steps,
            task_description=task_description,
            success=True,
            task_id=f"explore_{random.randint(1000, 9999)}"
        )

    def generate_repair_trajectory(
        self,
        num_steps: int = 6,
        task_description: str = "Repair error and retry"
    ) -> TemporalTrajectory:
        """
        Generate REPAIR regime trajectory

        Characteristics:
        - C-dominant (correct channel)
        - Retry patterns (same phase bucket repeated)
        - Mixed success/failure
        - Phases converging
        """
        steps = []
        pattern = REGIME_SYNC_PATTERNS[Regime.REPAIR]

        # Simulate: fail, wait, retry, fail, wait, succeed
        actions = [True, False, True, False, True, True]
        successes = [False, True, False, True, True, True]

        for i in range(num_steps):
            progress = i / max(num_steps - 1, 1)
            # Repair often repeats same phase (retry)
            phase_bucket = (i // 2) % self.num_cols

            step = TemporalStep(
                state_vector=self._generate_state_vector(Regime.REPAIR, progress),
                sync_vector=pattern.to_vector(self.noise_level),
                target_cell=self._select_cell(2, phase_bucket),  # C channel
                target_should_act=actions[i % len(actions)],
                target_regime=Regime.REPAIR,
                transition_expected=False,
                tool_name=f"repair_attempt_{i}",
                tool_success=successes[i % len(successes)],
                timestamp_ms=i * 200
            )
            steps.append(step)

        return TemporalTrajectory(
            steps=steps,
            task_description=task_description,
            success=True,  # Eventually succeeds
            task_id=f"repair_{random.randint(1000, 9999)}"
        )

    def generate_transition_trajectory(
        self,
        from_regime: Regime = Regime.EXPLOIT,
        to_regime: Regime = Regime.EXPLORE,
        transition_steps: int = 3,
        task_description: str = "Transition between regimes"
    ) -> TemporalTrajectory:
        """
        Generate regime transition trajectory

        Characteristics:
        - Starts in one regime, ends in another
        - Smooth phase transitions
        - Transition steps marked
        """
        steps = []

        from_pattern = REGIME_SYNC_PATTERNS[from_regime]
        to_pattern = REGIME_SYNC_PATTERNS[to_regime]

        # Steps in from_regime
        for i in range(2):
            step = TemporalStep(
                state_vector=self._generate_state_vector(from_regime, 0.2 * i),
                sync_vector=from_pattern.to_vector(self.noise_level),
                target_cell=self._select_cell(list(Regime).index(from_regime) % 3, i),
                target_should_act=True,
                target_regime=from_regime,
                transition_expected=False,
                timestamp_ms=i * 100
            )
            steps.append(step)

        # Transition steps (interpolated patterns)
        for i in range(transition_steps):
            t = (i + 1) / (transition_steps + 1)

            # Interpolate sync vectors
            from_vec = from_pattern.to_vector(0)
            to_vec = to_pattern.to_vector(0)
            interp_vec = (1 - t) * from_vec + t * to_vec
            interp_vec += np.random.randn(9) * self.noise_level

            step = TemporalStep(
                state_vector=self._generate_state_vector(Regime.TRANSITION, 0.4 + 0.2 * i),
                sync_vector=interp_vec,
                target_cell=self._select_cell(1, i + 2),  # Varied
                target_should_act=(i % 2 == 0),
                target_regime=Regime.TRANSITION,
                transition_expected=True,  # Mark as transition
                timestamp_ms=(2 + i) * 100
            )
            steps.append(step)

        # Steps in to_regime
        for i in range(2):
            step = TemporalStep(
                state_vector=self._generate_state_vector(to_regime, 0.8 + 0.1 * i),
                sync_vector=to_pattern.to_vector(self.noise_level),
                target_cell=self._select_cell(list(Regime).index(to_regime) % 3, i + 4),
                target_should_act=True,
                target_regime=to_regime,
                transition_expected=False,
                timestamp_ms=(2 + transition_steps + i) * 100
            )
            steps.append(step)

        return TemporalTrajectory(
            steps=steps,
            task_description=task_description,
            success=True,
            task_id=f"transition_{from_regime.name}_{to_regime.name}_{random.randint(1000, 9999)}"
        )

    def generate_deadlock_trajectory(
        self,
        num_steps: int = 4,
        task_description: str = "Stuck in deadlock"
    ) -> TemporalTrajectory:
        """
        Generate DEADLOCK trajectory (failed task)

        Characteristics:
        - All oscillators suppressed
        - No actions emitted
        - Phases drifting randomly
        """
        steps = []
        pattern = REGIME_SYNC_PATTERNS[Regime.DEADLOCK]

        for i in range(num_steps):
            # Random drifting phases
            sync = pattern.to_vector(0)
            sync[3:] = np.random.randn(6) * 0.3  # Random phase differences

            step = TemporalStep(
                state_vector=self._generate_state_vector(Regime.DEADLOCK, i / num_steps),
                sync_vector=sync,
                target_cell=random.randint(0, self.num_cells - 1),
                target_should_act=False,  # No actions in deadlock
                target_regime=Regime.DEADLOCK,
                transition_expected=False,
                tool_name=None,
                tool_success=None,
                timestamp_ms=i * 500  # Slow
            )
            steps.append(step)

        return TemporalTrajectory(
            steps=steps,
            task_description=task_description,
            success=False,  # Deadlock = failure
            task_id=f"deadlock_{random.randint(1000, 9999)}"
        )

    def generate_mixed_trajectory(
        self,
        regimes: List[Regime] = None,
        steps_per_regime: int = 3,
        task_description: str = "Complex multi-regime task"
    ) -> TemporalTrajectory:
        """
        Generate trajectory with multiple regime transitions

        Args:
            regimes: Sequence of regimes to traverse
            steps_per_regime: Steps in each regime
            task_description: Task description

        Returns:
            Combined trajectory
        """
        if regimes is None:
            regimes = [Regime.EXPLOIT, Regime.EXPLORE, Regime.REPAIR, Regime.EXPLOIT]

        all_steps = []
        timestamp = 0

        for regime_idx, regime in enumerate(regimes):
            pattern = REGIME_SYNC_PATTERNS[regime]
            channel = list(Regime).index(regime) % 3

            for i in range(steps_per_regime):
                progress = (regime_idx * steps_per_regime + i) / (len(regimes) * steps_per_regime)

                # Is this a transition step?
                is_transition = (
                    i == 0 and regime_idx > 0 and
                    regimes[regime_idx] != regimes[regime_idx - 1]
                )

                step = TemporalStep(
                    state_vector=self._generate_state_vector(regime, progress),
                    sync_vector=pattern.to_vector(self.noise_level),
                    target_cell=self._select_cell(channel, i % self.num_cols),
                    target_should_act=(regime != Regime.DEADLOCK),
                    target_regime=regime,
                    transition_expected=is_transition,
                    tool_name=f"{regime.name.lower()}_step_{i}",
                    tool_success=(regime != Regime.DEADLOCK),
                    timestamp_ms=timestamp
                )
                all_steps.append(step)
                timestamp += 100

        return TemporalTrajectory(
            steps=all_steps,
            task_description=task_description,
            success=(regimes[-1] != Regime.DEADLOCK),
            task_id=f"mixed_{'_'.join(r.name[:3] for r in regimes)}_{random.randint(1000, 9999)}"
        )

    def generate_dataset(
        self,
        num_exploit: int = 20,
        num_explore: int = 15,
        num_repair: int = 15,
        num_transition: int = 10,
        num_deadlock: int = 5,
        num_mixed: int = 10
    ) -> TemporalDataset:
        """
        Generate a complete training dataset

        Args:
            num_exploit: Number of exploit trajectories
            num_explore: Number of explore trajectories
            num_repair: Number of repair trajectories
            num_transition: Number of transition trajectories
            num_deadlock: Number of deadlock trajectories
            num_mixed: Number of mixed trajectories

        Returns:
            TemporalDataset with all trajectories
        """
        trajectories = []

        # Exploit trajectories
        for i in range(num_exploit):
            steps = random.randint(4, 8)
            traj = self.generate_exploit_trajectory(
                num_steps=steps,
                task_description=f"Exploit task {i+1}"
            )
            trajectories.append(traj)

        # Explore trajectories
        for i in range(num_explore):
            steps = random.randint(6, 10)
            traj = self.generate_explore_trajectory(
                num_steps=steps,
                task_description=f"Explore task {i+1}"
            )
            trajectories.append(traj)

        # Repair trajectories
        for i in range(num_repair):
            steps = random.randint(4, 8)
            traj = self.generate_repair_trajectory(
                num_steps=steps,
                task_description=f"Repair task {i+1}"
            )
            trajectories.append(traj)

        # Transition trajectories
        transitions = [
            (Regime.EXPLOIT, Regime.EXPLORE),
            (Regime.EXPLORE, Regime.REPAIR),
            (Regime.REPAIR, Regime.EXPLOIT),
            (Regime.EXPLOIT, Regime.REPAIR),
        ]
        for i in range(num_transition):
            from_r, to_r = transitions[i % len(transitions)]
            traj = self.generate_transition_trajectory(
                from_regime=from_r,
                to_regime=to_r,
                task_description=f"Transition {from_r.name} to {to_r.name}"
            )
            trajectories.append(traj)

        # Deadlock trajectories
        for i in range(num_deadlock):
            steps = random.randint(3, 5)
            traj = self.generate_deadlock_trajectory(
                num_steps=steps,
                task_description=f"Deadlock scenario {i+1}"
            )
            trajectories.append(traj)

        # Mixed trajectories
        regime_sequences = [
            [Regime.EXPLOIT, Regime.EXPLORE, Regime.EXPLOIT],
            [Regime.EXPLOIT, Regime.REPAIR, Regime.EXPLOIT],
            [Regime.EXPLORE, Regime.REPAIR, Regime.EXPLORE],
            [Regime.EXPLOIT, Regime.EXPLORE, Regime.REPAIR, Regime.EXPLOIT],
        ]
        for i in range(num_mixed):
            regimes = regime_sequences[i % len(regime_sequences)]
            traj = self.generate_mixed_trajectory(
                regimes=regimes,
                steps_per_regime=random.randint(2, 4),
                task_description=f"Mixed task {i+1}"
            )
            trajectories.append(traj)

        # Shuffle
        random.shuffle(trajectories)

        return TemporalDataset(
            trajectories=trajectories,
            state_dim=self.state_dim
        )


if __name__ == "__main__":
    print("=" * 70)
    print("SYNTHETIC DATA GENERATOR - Testing")
    print("=" * 70)
    print()

    # Create generator
    print("[1] Creating SyntheticDataGenerator...")
    generator = SyntheticDataGenerator(seed=42)
    print("    [OK] Generator created")
    print()

    # Test individual trajectory types
    print("[2] Testing individual trajectory generation...")

    traj_exploit = generator.generate_exploit_trajectory()
    print(f"    EXPLOIT: {traj_exploit.num_steps} steps, success={traj_exploit.success}")

    traj_explore = generator.generate_explore_trajectory()
    print(f"    EXPLORE: {traj_explore.num_steps} steps, success={traj_explore.success}")

    traj_repair = generator.generate_repair_trajectory()
    print(f"    REPAIR: {traj_repair.num_steps} steps, success={traj_repair.success}")

    traj_transition = generator.generate_transition_trajectory()
    print(f"    TRANSITION: {traj_transition.num_steps} steps, success={traj_transition.success}")

    traj_deadlock = generator.generate_deadlock_trajectory()
    print(f"    DEADLOCK: {traj_deadlock.num_steps} steps, success={traj_deadlock.success}")

    traj_mixed = generator.generate_mixed_trajectory()
    print(f"    MIXED: {traj_mixed.num_steps} steps, success={traj_mixed.success}")
    print()

    # Test sync vectors
    print("[3] Testing synchrony vector patterns...")
    for regime, pattern in REGIME_SYNC_PATTERNS.items():
        vec = pattern.to_vector(0.0)
        print(f"    {regime.name}: |A|={vec[0]:.1f} |B|={vec[1]:.1f} |C|={vec[2]:.1f} cos_AB={vec[3]:.1f}")
    print()

    # Test dataset generation
    print("[4] Testing dataset generation...")
    dataset = generator.generate_dataset(
        num_exploit=10,
        num_explore=8,
        num_repair=8,
        num_transition=5,
        num_deadlock=3,
        num_mixed=6
    )

    stats = dataset.get_statistics()
    print(f"    Num trajectories: {stats['num_trajectories']}")
    print(f"    Total steps: {stats['total_steps']}")
    print(f"    Avg length: {stats['avg_length']:.1f}")
    print(f"    Success rate: {stats['success_rate']:.1%}")
    print(f"    Regime distribution:")
    for regime, count in stats['regime_distribution'].items():
        print(f"        {regime}: {count}")
    print()

    # Test single item
    print("[5] Testing single item retrieval...")
    item = dataset[0]
    print(f"    state_vectors shape: {item['state_vectors'].shape}")
    print(f"    sync_vectors shape: {item['sync_vectors'].shape}")
    print(f"    target_cells: {item['target_cells'][:3].tolist()}...")
    print(f"    target_timing: {item['target_timing'][:3].tolist()}...")
    print()

    print("=" * 70)
    print("SYNTHETIC DATA GENERATOR TESTS COMPLETE")
    print("=" * 70)
