"""
Path Skeleton - Abstractions for Temporal Path and Episode Representation

Provides Python dataclasses that mirror the Kotlin design for:
    - PathSkeleton: Complete path abstraction (the "Weg")
    - PathStep: Single step in the path
    - TemporalUnit: Single drumpad hit
    - Episode: Complete temporal trajectory

These structures enable:
    1. Compact representation of tool-call sequences
    2. Serialization for Kotlin/mobile interop
    3. Training data generation
    4. Path comparison and analysis

The abstraction separates:
    - WHAT: Action channel (Advance/Explore/Correct)
    - WHEN: Beat index + phase offset
    - HOW STRONG: Amplitude/intensity
    - WHERE: Synchrony signature (regime indicator)
"""

import json
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from core.action_potential_oscillator import Channel
from core.regime_detector import Regime


class PathChannel(Enum):
    """Action channel (mirrors Kotlin Channel enum)"""
    ADVANCE = "ADVANCE"
    EXPLORE = "EXPLORE"
    CORRECT = "CORRECT"

    @classmethod
    def from_channel(cls, channel: Channel) -> 'PathChannel':
        """Convert from action_potential_oscillator.Channel"""
        return {
            Channel.ADVANCE: cls.ADVANCE,
            Channel.EXPLORE: cls.EXPLORE,
            Channel.CORRECT: cls.CORRECT
        }[channel]


class PathRegime(Enum):
    """Operational regime (mirrors Kotlin Regime enum)"""
    EXPLOIT = "EXPLOIT"
    EXPLORE = "EXPLORE"
    REPAIR = "REPAIR"
    TRANSITION = "TRANSITION"
    DEADLOCK = "DEADLOCK"

    @classmethod
    def from_regime(cls, regime: Regime) -> 'PathRegime':
        """Convert from regime_detector.Regime"""
        return {
            Regime.EXPLOIT: cls.EXPLOIT,
            Regime.EXPLORE: cls.EXPLORE,
            Regime.REPAIR: cls.REPAIR,
            Regime.TRANSITION: cls.TRANSITION,
            Regime.DEADLOCK: cls.DEADLOCK
        }[regime]


@dataclass
class PathStep:
    """
    Single step in the path

    Represents one action in the temporal sequence.
    """
    beat_index: int               # Global time (beat number)
    active_channel: PathChannel   # A, B, or C
    phase_offset: float           # 0.0 to 1.0 (maps to drumpad column)
    amplitude: float              # Activation strength [0, 1]

    # Optional metadata
    tool_name: Optional[str] = None
    tool_result: Optional[str] = None
    success: Optional[bool] = None

    @property
    def phase_bucket(self) -> int:
        """Phase bucket (0-7) for drumpad column"""
        return min(int(self.phase_offset * 8), 7)

    @property
    def phase_degrees(self) -> float:
        """Phase in degrees"""
        return self.phase_offset * 360.0

    def to_dict(self) -> Dict:
        """Convert to dict for serialization"""
        return {
            'beatIndex': self.beat_index,
            'activeChannel': self.active_channel.value,
            'phaseOffset': self.phase_offset,
            'amplitude': self.amplitude,
            'toolName': self.tool_name,
            'toolResult': self.tool_result,
            'success': self.success
        }

    def to_json(self) -> str:
        """Serialize to JSON (Kotlin-compatible)"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict) -> 'PathStep':
        """Create from dict"""
        return cls(
            beat_index=d['beatIndex'],
            active_channel=PathChannel(d['activeChannel']),
            phase_offset=d['phaseOffset'],
            amplitude=d['amplitude'],
            tool_name=d.get('toolName'),
            tool_result=d.get('toolResult'),
            success=d.get('success')
        )


@dataclass
class TemporalUnit:
    """
    Single drumpad hit - atomic temporal action unit

    This is the smallest unit of temporal action.
    """
    channel: PathChannel          # Which row (A, B, C)
    phase_bucket: int             # Which column (0-7)
    intensity: float              # Activation strength [0, 1]
    sync_vector: List[float]      # 9-D synchrony signature

    # Optional timing
    beat_index: int = 0
    timestamp_ms: int = 0

    @property
    def phase_offset(self) -> float:
        """Phase offset [0, 1]"""
        return self.phase_bucket / 8.0

    @property
    def cell_id(self) -> int:
        """Linear cell ID in 3×8 grid"""
        channel_idx = {'ADVANCE': 0, 'EXPLORE': 1, 'CORRECT': 2}[self.channel.value]
        return channel_idx * 8 + self.phase_bucket

    def to_dict(self) -> Dict:
        """Convert to dict"""
        return {
            'channel': self.channel.value,
            'phaseBucket': self.phase_bucket,
            'intensity': self.intensity,
            'syncVector': self.sync_vector,
            'beatIndex': self.beat_index,
            'timestampMs': self.timestamp_ms
        }

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict) -> 'TemporalUnit':
        """Create from dict"""
        return cls(
            channel=PathChannel(d['channel']),
            phase_bucket=d['phaseBucket'],
            intensity=d['intensity'],
            sync_vector=d['syncVector'],
            beat_index=d.get('beatIndex', 0),
            timestamp_ms=d.get('timestampMs', 0)
        )


@dataclass
class PathSkeleton:
    """
    Complete path abstraction - the "Weg"

    Represents a full trajectory of actions as a sequence of steps.
    """
    steps: List[PathStep]
    total_beats: int
    regime: PathRegime

    # Metadata
    task_description: Optional[str] = None
    success: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def num_steps(self) -> int:
        """Number of steps in path"""
        return len(self.steps)

    @property
    def channel_sequence(self) -> List[str]:
        """Sequence of channels (e.g., ['A', 'A', 'B', 'C'])"""
        return [s.active_channel.value[0] for s in self.steps]

    @property
    def channel_distribution(self) -> Dict[str, int]:
        """Count of each channel"""
        dist = {'ADVANCE': 0, 'EXPLORE': 0, 'CORRECT': 0}
        for step in self.steps:
            dist[step.active_channel.value] += 1
        return dist

    @property
    def mean_amplitude(self) -> float:
        """Mean amplitude across steps"""
        if not self.steps:
            return 0.0
        return sum(s.amplitude for s in self.steps) / len(self.steps)

    def get_step_at_beat(self, beat: int) -> Optional[PathStep]:
        """Get step at specific beat"""
        for step in self.steps:
            if step.beat_index == beat:
                return step
        return None

    def to_dict(self) -> Dict:
        """Convert to dict"""
        return {
            'steps': [s.to_dict() for s in self.steps],
            'totalBeats': self.total_beats,
            'regime': self.regime.value,
            'taskDescription': self.task_description,
            'success': self.success,
            'numSteps': self.num_steps,
            'channelDistribution': self.channel_distribution
        }

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: Dict) -> 'PathSkeleton':
        """Create from dict"""
        return cls(
            steps=[PathStep.from_dict(s) for s in d['steps']],
            total_beats=d['totalBeats'],
            regime=PathRegime(d['regime']),
            task_description=d.get('taskDescription'),
            success=d.get('success', False)
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'PathSkeleton':
        """Deserialize from JSON"""
        return cls.from_dict(json.loads(json_str))


@dataclass
class RegimeTransition:
    """Regime transition event"""
    beat_index: int
    from_regime: PathRegime
    to_regime: PathRegime

    def to_dict(self) -> Dict:
        return {
            'beatIndex': self.beat_index,
            'fromRegime': self.from_regime.value,
            'toRegime': self.to_regime.value
        }


@dataclass
class Episode:
    """
    Complete temporal trajectory - full episode of tool execution

    Contains all temporal units and regime transitions for one
    complete task execution.
    """
    units: List[TemporalUnit]
    regime_transitions: List[RegimeTransition]
    success: bool

    # Episode metadata
    task_id: Optional[str] = None
    task_description: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_duration_ms: int = 0

    @property
    def num_units(self) -> int:
        """Number of temporal units"""
        return len(self.units)

    @property
    def num_transitions(self) -> int:
        """Number of regime transitions"""
        return len(self.regime_transitions)

    @property
    def final_regime(self) -> Optional[PathRegime]:
        """Final regime (from last transition)"""
        if self.regime_transitions:
            return self.regime_transitions[-1].to_regime
        return None

    @property
    def channel_sequence(self) -> List[str]:
        """Sequence of channels"""
        return [u.channel.value[0] for u in self.units]

    def get_path_skeleton(self) -> PathSkeleton:
        """Convert episode to path skeleton"""
        steps = []
        for unit in self.units:
            step = PathStep(
                beat_index=unit.beat_index,
                active_channel=unit.channel,
                phase_offset=unit.phase_offset,
                amplitude=unit.intensity
            )
            steps.append(step)

        regime = self.final_regime or PathRegime.TRANSITION

        return PathSkeleton(
            steps=steps,
            total_beats=max(u.beat_index for u in self.units) + 1 if self.units else 0,
            regime=regime,
            task_description=self.task_description,
            success=self.success
        )

    def to_dict(self) -> Dict:
        """Convert to dict"""
        return {
            'units': [u.to_dict() for u in self.units],
            'regimeTransitions': [t.to_dict() for t in self.regime_transitions],
            'success': self.success,
            'taskId': self.task_id,
            'taskDescription': self.task_description,
            'totalDurationMs': self.total_duration_ms,
            'numUnits': self.num_units,
            'numTransitions': self.num_transitions,
            'channelSequence': self.channel_sequence
        }

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: Dict) -> 'Episode':
        """Create from dict"""
        return cls(
            units=[TemporalUnit.from_dict(u) for u in d['units']],
            regime_transitions=[
                RegimeTransition(
                    beat_index=t['beatIndex'],
                    from_regime=PathRegime(t['fromRegime']),
                    to_regime=PathRegime(t['toRegime'])
                )
                for t in d['regimeTransitions']
            ],
            success=d['success'],
            task_id=d.get('taskId'),
            task_description=d.get('taskDescription'),
            total_duration_ms=d.get('totalDurationMs', 0)
        )


class EpisodeBuilder:
    """Builder for constructing episodes incrementally"""

    def __init__(self, task_description: Optional[str] = None):
        self.task_description = task_description
        self.units: List[TemporalUnit] = []
        self.transitions: List[RegimeTransition] = []
        self.current_regime: Optional[PathRegime] = None
        self.start_time = datetime.now()
        self.beat_counter = 0

    def add_unit(
        self,
        channel: PathChannel,
        phase_bucket: int,
        intensity: float,
        sync_vector: List[float]
    ):
        """Add a temporal unit"""
        unit = TemporalUnit(
            channel=channel,
            phase_bucket=phase_bucket,
            intensity=intensity,
            sync_vector=sync_vector,
            beat_index=self.beat_counter,
            timestamp_ms=int((datetime.now() - self.start_time).total_seconds() * 1000)
        )
        self.units.append(unit)
        self.beat_counter += 1

    def set_regime(self, regime: PathRegime):
        """Set current regime (records transition if changed)"""
        if self.current_regime is None:
            self.current_regime = regime
        elif regime != self.current_regime:
            transition = RegimeTransition(
                beat_index=self.beat_counter,
                from_regime=self.current_regime,
                to_regime=regime
            )
            self.transitions.append(transition)
            self.current_regime = regime

    def build(self, success: bool) -> Episode:
        """Build the episode"""
        end_time = datetime.now()
        duration_ms = int((end_time - self.start_time).total_seconds() * 1000)

        return Episode(
            units=self.units,
            regime_transitions=self.transitions,
            success=success,
            task_description=self.task_description,
            start_time=self.start_time,
            end_time=end_time,
            total_duration_ms=duration_ms
        )


if __name__ == "__main__":
    print("=" * 70)
    print("PATH SKELETON - Temporal Path Abstraction")
    print("=" * 70)
    print()

    # Build an example episode
    print("Building example episode...")
    builder = EpisodeBuilder(task_description="Deploy nginx container")

    # Simulate some actions
    scenarios = [
        (PathChannel.ADVANCE, 0, 0.8, PathRegime.EXPLOIT),
        (PathChannel.ADVANCE, 1, 0.9, PathRegime.EXPLOIT),
        (PathChannel.EXPLORE, 3, 0.5, PathRegime.TRANSITION),
        (PathChannel.EXPLORE, 4, 0.7, PathRegime.EXPLORE),
        (PathChannel.CORRECT, 2, 0.6, PathRegime.REPAIR),
        (PathChannel.ADVANCE, 5, 0.85, PathRegime.EXPLOIT),
    ]

    for channel, phase, intensity, regime in scenarios:
        builder.set_regime(regime)
        builder.add_unit(
            channel=channel,
            phase_bucket=phase,
            intensity=intensity,
            sync_vector=[0.5, 0.3, 0.2, 0.8, 0.1, 0.7, 0.2, 0.6, 0.3]  # Example sync
        )

    episode = builder.build(success=True)

    print()
    print("Episode Summary:")
    print(f"  Task: {episode.task_description}")
    print(f"  Units: {episode.num_units}")
    print(f"  Transitions: {episode.num_transitions}")
    print(f"  Channel sequence: {episode.channel_sequence}")
    print(f"  Success: {episode.success}")
    print()

    # Convert to path skeleton
    skeleton = episode.get_path_skeleton()

    print("Path Skeleton:")
    print(f"  Total beats: {skeleton.total_beats}")
    print(f"  Regime: {skeleton.regime.value}")
    print(f"  Channel distribution: {skeleton.channel_distribution}")
    print(f"  Mean amplitude: {skeleton.mean_amplitude:.3f}")
    print()

    # Serialize to JSON
    print("Episode JSON (first 500 chars):")
    json_str = episode.to_json()
    print(json_str[:500] + "..." if len(json_str) > 500 else json_str)
    print()

    # Deserialize
    episode_restored = Episode.from_dict(json.loads(json_str))
    print(f"Restored episode has {episode_restored.num_units} units")
    print()

    print("=" * 70)
