"""
Sleep Consolidation System for ATM-R Architecture

Implements biologically-inspired sleep consolidation with:
- Wake/Sleep state machine (WAKE → DROWSY → NREM1 → NREM2 → NREM3 → REM)
- Synaptic homeostasis (weight scaling during offline periods)
- Sharp-Wave Ripple (SWR) simulation for memory replay
- Integration with hippocampus, dream mode, and neuromodulation

Based on:
- Synaptic Homeostasis Hypothesis (Tononi & Cirelli, 2003)
- Two-stage memory consolidation (Diekelmann & Born, 2010)
- Sharp-wave ripple replay (Buzsáki, 2015)

Usage:
    from core.sleep_consolidation import SleepConsolidation, SleepConsolidationConfig

    config = SleepConsolidationConfig()
    consolidator = SleepConsolidation(
        config=config,
        hippocampus=hippocampus,
        dream_mode=dream_mode,
        neuromodulation=neuromod
    )

    # Run a full sleep cycle
    result = consolidator.enter_sleep_cycle()

    # Or step-by-step
    output = consolidator.step(activity_level=0.1, dt=1.0)
"""

import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING
from collections import deque
import time

if TYPE_CHECKING:
    from core.hippocampus import Hippocampus, EpisodicMemory
    from core.dream_mode import DreamMode
    from core.neuromodulation import NeuromodulationSystem, NeuromodulatorLevels
    from core.thalamo_pc_adaptive import ThalamoPC6Adaptive
    from core.hierarchical_routing_system import HierarchicalRoutingSystem
    from core.basal_ganglia import BasalGanglia


# ============================================================================
# Enums and Data Classes
# ============================================================================

class SleepState(Enum):
    """Sleep stages following biological sleep architecture."""
    WAKE = "wake"           # Active processing, full learning
    DROWSY = "drowsy"       # Transition state, reduced activity
    NREM_N1 = "nrem_n1"     # Light NREM, sleep onset
    NREM_N2 = "nrem_n2"     # Deeper NREM, sleep spindles
    NREM_N3 = "nrem_n3"     # Deep NREM (SWS), SWR replay - MAIN CONSOLIDATION
    REM = "rem"             # REM sleep, emotional/counterfactual


@dataclass
class SleepConsolidationConfig:
    """Configuration for sleep consolidation system."""

    # State machine parameters
    idle_threshold_seconds: float = 60.0    # Idle time before sleep
    activity_wake_threshold: float = 0.5    # Activity level to force wake
    max_sleep_cycles: int = 4               # Max NREM→REM cycles

    # Stage durations (simulated seconds)
    drowsy_duration: float = 5.0
    nrem_n1_duration: float = 10.0
    nrem_n2_duration: float = 20.0
    nrem_n3_duration: float = 30.0          # Deep sleep - main consolidation
    rem_duration: float = 20.0

    # Synaptic homeostasis
    nrem_scaling_rate: float = 0.95         # 5% reduction per NREM cycle
    rem_scaling_rate: float = 0.98          # 2% reduction per REM
    selective_threshold: float = 0.7        # Activation level to preserve
    target_weight_norm: float = 1.0
    min_weight: float = 0.01
    max_weight: float = 5.0

    # Sharp-Wave Ripple
    swr_probability: float = 0.3            # Per timestep in NREM_N3
    swr_replay_count: int = 5               # Memories per ripple
    replay_compression: float = 10.0        # Time compression ratio

    # Dream mode integration
    nrem_replay_count: int = 5
    rem_dream_count: int = 5
    counterfactual_rate: float = 0.3

    # Neuromodulator targets by stage
    wake_dopamine: float = 0.5
    wake_serotonin: float = 0.5
    wake_norepinephrine: float = 0.5
    sleep_dopamine: float = 0.2
    sleep_serotonin: float = 0.7
    sleep_norepinephrine: float = 0.1

    # Gate modulation during sleep
    sleep_gate_temp_multiplier: float = 1.5
    sleep_layer_weight_l4: float = 0.70     # L4 dominates during sleep
    sleep_layer_weight_l1: float = 0.05     # Minimal sensory

    # Metrics
    track_detailed_metrics: bool = True
    metric_history_size: int = 1000

    # Random seed
    seed: int = 42


@dataclass
class SleepStageConfig:
    """Configuration for a specific sleep stage."""
    duration: float
    swr_enabled: bool = False
    synaptic_scaling: bool = False
    counterfactual_enabled: bool = False
    dopamine_target: float = 0.5
    serotonin_target: float = 0.5
    norepinephrine_target: float = 0.5
    gate_temp_modifier: float = 1.0


@dataclass
class RippleEvent:
    """A Sharp-Wave Ripple event."""
    timestamp: float
    duration: int
    memories_replayed: List[int]  # Memory indices
    strength: float


@dataclass
class ConsolidationMetrics:
    """Metrics tracking consolidation progress."""
    total_sleep_time: float = 0.0
    time_per_stage: Dict[SleepState, float] = field(default_factory=dict)
    cycles_completed: int = 0
    replays_triggered: int = 0
    patterns_discovered: int = 0
    weight_reduction_ratio: float = 1.0
    memory_strength_changes: List[float] = field(default_factory=list)
    swr_events: List[RippleEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_sleep_time': self.total_sleep_time,
            'time_per_stage': {s.value: t for s, t in self.time_per_stage.items()},
            'cycles_completed': self.cycles_completed,
            'replays_triggered': self.replays_triggered,
            'patterns_discovered': self.patterns_discovered,
            'weight_reduction_ratio': self.weight_reduction_ratio,
            'num_swr_events': len(self.swr_events)
        }


@dataclass
class SleepConsolidationOutput:
    """Output from a single consolidation step."""
    state: SleepState
    state_changed: bool
    swr_triggered: bool
    replays_this_step: int
    neuromod_targets: Dict[str, float]
    gate_modulation: Dict[str, float]
    metrics: ConsolidationMetrics


# ============================================================================
# Sleep State Machine
# ============================================================================

class SleepStateMachine:
    """
    Manages wake/sleep state transitions based on activity and time.

    State progression:
        WAKE → DROWSY → NREM_N1 → NREM_N2 → NREM_N3 → REM → (cycle back to NREM_N2)
        Any state → WAKE (on high activity or max cycles)
    """

    def __init__(self, config: SleepConsolidationConfig):
        self.config = config
        self.current_state = SleepState.WAKE
        self.state_duration = 0.0
        self.idle_time = 0.0
        self.cycles_completed = 0

        # Stage configurations
        self.stage_configs = self._build_stage_configs()

        # History
        self.state_history: List[Tuple[SleepState, float]] = []
        self.max_history = 100

    def _build_stage_configs(self) -> Dict[SleepState, SleepStageConfig]:
        """Build configuration for each sleep stage."""
        c = self.config
        return {
            SleepState.WAKE: SleepStageConfig(
                duration=float('inf'),
                dopamine_target=c.wake_dopamine,
                serotonin_target=c.wake_serotonin,
                norepinephrine_target=c.wake_norepinephrine,
                gate_temp_modifier=1.0
            ),
            SleepState.DROWSY: SleepStageConfig(
                duration=c.drowsy_duration,
                dopamine_target=0.4,
                serotonin_target=0.6,
                norepinephrine_target=0.3,
                gate_temp_modifier=1.1
            ),
            SleepState.NREM_N1: SleepStageConfig(
                duration=c.nrem_n1_duration,
                dopamine_target=0.3,
                serotonin_target=0.6,
                norepinephrine_target=0.2,
                gate_temp_modifier=1.2
            ),
            SleepState.NREM_N2: SleepStageConfig(
                duration=c.nrem_n2_duration,
                dopamine_target=0.25,
                serotonin_target=0.65,
                norepinephrine_target=0.15,
                gate_temp_modifier=1.3
            ),
            SleepState.NREM_N3: SleepStageConfig(
                duration=c.nrem_n3_duration,
                swr_enabled=True,
                synaptic_scaling=True,
                dopamine_target=c.sleep_dopamine,
                serotonin_target=c.sleep_serotonin,
                norepinephrine_target=c.sleep_norepinephrine,
                gate_temp_modifier=c.sleep_gate_temp_multiplier
            ),
            SleepState.REM: SleepStageConfig(
                duration=c.rem_duration,
                counterfactual_enabled=True,
                synaptic_scaling=True,
                dopamine_target=0.4,
                serotonin_target=0.3,
                norepinephrine_target=0.1,
                gate_temp_modifier=1.2
            )
        }

    def step(self, activity_level: float, dt: float) -> Tuple[SleepState, bool]:
        """
        Update state machine based on activity level.

        Args:
            activity_level: Current activity level [0, 1]
            dt: Time delta

        Returns:
            (new_state, state_changed)
        """
        old_state = self.current_state
        self.state_duration += dt

        # Check for forced wake
        if activity_level > self.config.activity_wake_threshold:
            if self.current_state != SleepState.WAKE:
                self._transition_to(SleepState.WAKE)
                return self.current_state, True
            self.idle_time = 0.0
            return self.current_state, False

        # State-specific transitions
        if self.current_state == SleepState.WAKE:
            self.idle_time += dt
            if self.idle_time > self.config.idle_threshold_seconds:
                self._transition_to(SleepState.DROWSY)

        elif self.current_state == SleepState.DROWSY:
            if self.state_duration >= self.stage_configs[SleepState.DROWSY].duration:
                self._transition_to(SleepState.NREM_N1)

        elif self.current_state == SleepState.NREM_N1:
            if self.state_duration >= self.stage_configs[SleepState.NREM_N1].duration:
                self._transition_to(SleepState.NREM_N2)

        elif self.current_state == SleepState.NREM_N2:
            if self.state_duration >= self.stage_configs[SleepState.NREM_N2].duration:
                self._transition_to(SleepState.NREM_N3)

        elif self.current_state == SleepState.NREM_N3:
            if self.state_duration >= self.stage_configs[SleepState.NREM_N3].duration:
                self._transition_to(SleepState.REM)

        elif self.current_state == SleepState.REM:
            if self.state_duration >= self.stage_configs[SleepState.REM].duration:
                self.cycles_completed += 1
                if self.cycles_completed >= self.config.max_sleep_cycles:
                    self._transition_to(SleepState.WAKE)
                else:
                    self._transition_to(SleepState.NREM_N2)

        state_changed = self.current_state != old_state
        return self.current_state, state_changed

    def _transition_to(self, new_state: SleepState):
        """Transition to a new state."""
        self.state_history.append((self.current_state, self.state_duration))
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)

        self.current_state = new_state
        self.state_duration = 0.0

        if new_state == SleepState.WAKE:
            self.idle_time = 0.0
            self.cycles_completed = 0

    def force_wake(self):
        """Force immediate transition to WAKE."""
        self._transition_to(SleepState.WAKE)

    def force_state(self, state: SleepState):
        """Force transition to specific state (for testing)."""
        self._transition_to(state)

    def get_stage_config(self) -> SleepStageConfig:
        """Get configuration for current stage."""
        return self.stage_configs[self.current_state]

    def is_sleeping(self) -> bool:
        """Check if currently in a sleep state."""
        return self.current_state not in [SleepState.WAKE, SleepState.DROWSY]

    def get_state_duration(self) -> float:
        """Get time spent in current state."""
        return self.state_duration

    def reset(self):
        """Reset state machine to WAKE."""
        self.current_state = SleepState.WAKE
        self.state_duration = 0.0
        self.idle_time = 0.0
        self.cycles_completed = 0


# ============================================================================
# Synaptic Homeostasis
# ============================================================================

class SynapticHomeostasis:
    """
    Implements synaptic scaling based on the Synaptic Homeostasis Hypothesis.

    During wake: Synaptic weights tend to increase (learning)
    During sleep: Weights scale down globally, but strongly-activated
                  synapses are selectively preserved.
    """

    def __init__(self, config: SleepConsolidationConfig):
        self.config = config
        self.rng = np.random.default_rng(config.seed)

        # Track activation history for selective strengthening
        self.activation_history: Dict[str, np.ndarray] = {}
        self.total_scaling_applied = 1.0

    def record_activation(self, name: str, activation: np.ndarray):
        """
        Record activation pattern for later selective preservation.

        Args:
            name: Weight matrix name
            activation: Activation values
        """
        if name not in self.activation_history:
            self.activation_history[name] = np.zeros_like(activation)

        # Exponential moving average
        alpha = 0.1
        self.activation_history[name] = (
            (1 - alpha) * self.activation_history[name] +
            alpha * np.abs(activation)
        )

    def apply_homeostasis(
        self,
        weights: Dict[str, np.ndarray],
        sleep_stage: SleepState
    ) -> Dict[str, np.ndarray]:
        """
        Apply synaptic homeostasis based on sleep stage.

        Args:
            weights: Dict mapping name -> weight matrix
            sleep_stage: Current sleep stage

        Returns:
            Scaled weights
        """
        if sleep_stage == SleepState.NREM_N3:
            return self._apply_nrem_scaling(weights)
        elif sleep_stage == SleepState.REM:
            return self._apply_rem_scaling(weights)
        else:
            return weights

    def _apply_nrem_scaling(
        self,
        weights: Dict[str, np.ndarray]
    ) -> Dict[str, np.ndarray]:
        """Apply NREM synaptic downscaling with selective preservation."""
        scaled = {}

        for name, W in weights.items():
            # Global downscaling
            W_scaled = W * self.config.nrem_scaling_rate

            # Selective strengthening for highly-activated synapses
            if name in self.activation_history:
                activation = self.activation_history[name]

                # Normalize activation to [0, 1]
                if np.max(activation) > 0:
                    norm_activation = activation / np.max(activation)
                else:
                    norm_activation = activation

                # Boost synapses above threshold
                strong_mask = norm_activation > self.config.selective_threshold
                W_scaled[strong_mask] *= 1.05  # 5% boost for strong synapses

            # Clip to bounds
            W_scaled = np.clip(W_scaled, self.config.min_weight, self.config.max_weight)

            # Renormalize to target
            current_norm = np.linalg.norm(W_scaled, 'fro')
            if current_norm > 0:
                W_scaled = W_scaled * (self.config.target_weight_norm / current_norm)

            scaled[name] = W_scaled

        self.total_scaling_applied *= self.config.nrem_scaling_rate
        return scaled

    def _apply_rem_scaling(
        self,
        weights: Dict[str, np.ndarray]
    ) -> Dict[str, np.ndarray]:
        """Apply milder REM scaling (local consolidation)."""
        scaled = {}

        for name, W in weights.items():
            W_scaled = W * self.config.rem_scaling_rate
            W_scaled = np.clip(W_scaled, self.config.min_weight, self.config.max_weight)
            scaled[name] = W_scaled

        self.total_scaling_applied *= self.config.rem_scaling_rate
        return scaled

    def get_scaling_ratio(self) -> float:
        """Get total scaling applied since last reset."""
        return self.total_scaling_applied

    def reset(self):
        """Reset activation history and scaling tracker."""
        self.activation_history.clear()
        self.total_scaling_applied = 1.0


# ============================================================================
# Sharp-Wave Ripple Generator
# ============================================================================

class SharpWaveRippleGenerator:
    """
    Simulates Sharp-Wave Ripples (SWR) during NREM_N3 sleep.

    SWRs are high-frequency (150-250Hz) bursts in hippocampus that
    trigger memory replay and consolidation.
    """

    def __init__(self, config: SleepConsolidationConfig):
        self.config = config
        self.rng = np.random.default_rng(config.seed + 100)

        self.active_ripple: Optional[RippleEvent] = None
        self.ripple_history: List[RippleEvent] = []
        self.timestep = 0

    def check_for_ripple(self, sleep_stage: SleepState, timestep: int) -> bool:
        """
        Check if a SWR should occur at this timestep.

        SWRs only occur during NREM_N3 (deep sleep).
        """
        self.timestep = timestep

        if sleep_stage != SleepState.NREM_N3:
            return False

        # Probabilistic ripple generation
        if self.rng.random() < self.config.swr_probability:
            return True

        return False

    def generate_ripple(self, timestamp: float) -> RippleEvent:
        """Generate a new SWR event."""
        ripple = RippleEvent(
            timestamp=timestamp,
            duration=self.rng.integers(3, 8),  # 3-8 timesteps
            memories_replayed=[],
            strength=0.5 + 0.5 * self.rng.random()
        )
        self.active_ripple = ripple
        return ripple

    def select_memories_for_replay(
        self,
        memories: List['EpisodicMemory'],
        k: int
    ) -> List[int]:
        """
        Select memories for replay during a ripple.

        Selection is weighted by:
        1. Recency (newer memories)
        2. Prediction error (novel experiences)
        3. Memory strength (important memories)

        Args:
            memories: List of episodic memories
            k: Number of memories to select

        Returns:
            Indices of selected memories
        """
        if len(memories) == 0:
            return []

        k = min(k, len(memories))

        # Compute selection weights
        weights = np.ones(len(memories))

        for i, mem in enumerate(memories):
            # Recency weight (exponential decay)
            age = self.timestep - mem.timestamp
            recency_weight = np.exp(-0.01 * age)

            # Novelty weight (prediction error)
            novelty_weight = 1.0 + mem.prediction_error

            # Strength weight
            strength_weight = mem.strength

            weights[i] = recency_weight * novelty_weight * strength_weight

        # Normalize
        weights = weights / np.sum(weights)

        # Sample without replacement
        selected = self.rng.choice(
            len(memories),
            size=k,
            replace=False,
            p=weights
        )

        return selected.tolist()

    def complete_ripple(self, memories_replayed: List[int]):
        """Mark ripple as complete with replay results."""
        if self.active_ripple:
            self.active_ripple.memories_replayed = memories_replayed
            self.ripple_history.append(self.active_ripple)
            self.active_ripple = None

    def get_ripple_count(self) -> int:
        """Get total number of ripples generated."""
        return len(self.ripple_history)

    def reset(self):
        """Reset ripple generator."""
        self.active_ripple = None
        self.ripple_history.clear()
        self.timestep = 0


# ============================================================================
# Sleep Stage Manager
# ============================================================================

class SleepStageManager:
    """
    Manages stage-specific consolidation behaviors.

    NREM (N3): SWR-triggered hippocampal replay, synaptic downscaling
    REM: Emotional processing, counterfactual dreams
    """

    def __init__(self, config: SleepConsolidationConfig):
        self.config = config

    def get_neuromod_targets(self, stage: SleepState) -> Dict[str, float]:
        """Get target neuromodulator levels for a stage."""
        stage_targets = {
            SleepState.WAKE: {
                'dopamine': self.config.wake_dopamine,
                'serotonin': self.config.wake_serotonin,
                'norepinephrine': self.config.wake_norepinephrine
            },
            SleepState.DROWSY: {
                'dopamine': 0.4,
                'serotonin': 0.6,
                'norepinephrine': 0.3
            },
            SleepState.NREM_N1: {
                'dopamine': 0.3,
                'serotonin': 0.6,
                'norepinephrine': 0.2
            },
            SleepState.NREM_N2: {
                'dopamine': 0.25,
                'serotonin': 0.65,
                'norepinephrine': 0.15
            },
            SleepState.NREM_N3: {
                'dopamine': self.config.sleep_dopamine,
                'serotonin': self.config.sleep_serotonin,
                'norepinephrine': self.config.sleep_norepinephrine
            },
            SleepState.REM: {
                'dopamine': 0.4,
                'serotonin': 0.3,
                'norepinephrine': 0.1
            }
        }
        return stage_targets.get(stage, stage_targets[SleepState.WAKE])

    def get_gate_modulation(self, stage: SleepState) -> Dict[str, float]:
        """Get gate modulation parameters for a stage."""
        if stage in [SleepState.NREM_N3, SleepState.REM]:
            return {
                'temperature_multiplier': self.config.sleep_gate_temp_multiplier,
                'layer_weights': {
                    1: self.config.sleep_layer_weight_l1,
                    2: 0.10,
                    3: 0.15,
                    4: self.config.sleep_layer_weight_l4
                }
            }
        else:
            return {
                'temperature_multiplier': 1.0,
                'layer_weights': {1: 0.15, 2: 0.20, 3: 0.30, 4: 0.35}
            }

    def should_run_replay(self, stage: SleepState) -> bool:
        """Check if replay should run in this stage."""
        return stage == SleepState.NREM_N3

    def should_run_counterfactual(self, stage: SleepState) -> bool:
        """Check if counterfactual dreams should run."""
        return stage == SleepState.REM


# ============================================================================
# Main Sleep Consolidation Orchestrator
# ============================================================================

class SleepConsolidation:
    """
    Main orchestrator for sleep consolidation.

    Coordinates:
    - Sleep state machine (wake/sleep transitions)
    - Synaptic homeostasis (weight scaling)
    - SWR generator (memory replay triggers)
    - Integration with hippocampus, dream mode, neuromodulation
    """

    def __init__(
        self,
        config: Optional[SleepConsolidationConfig] = None,
        hippocampus: Optional['Hippocampus'] = None,
        dream_mode: Optional['DreamMode'] = None,
        neuromodulation: Optional['NeuromodulationSystem'] = None,
        thalamus: Optional['ThalamoPC6Adaptive'] = None,
        routing_system: Optional['HierarchicalRoutingSystem'] = None,
        basal_ganglia: Optional['BasalGanglia'] = None
    ):
        """
        Initialize sleep consolidation system.

        Args:
            config: Configuration (uses defaults if None)
            hippocampus: Hippocampal memory system
            dream_mode: Dream mode for replay/counterfactual
            neuromodulation: Neuromodulation system
            thalamus: Adaptive thalamus (for weight scaling)
            routing_system: Hierarchical routing (for gate modulation)
            basal_ganglia: Basal ganglia (for eligibility trace reset)
        """
        self.config = config or SleepConsolidationConfig()

        # External components
        self.hippocampus = hippocampus
        self.dream_mode = dream_mode
        self.neuromodulation = neuromodulation
        self.thalamus = thalamus
        self.routing_system = routing_system
        self.basal_ganglia = basal_ganglia

        # Internal components
        self.state_machine = SleepStateMachine(self.config)
        self.synaptic_homeostasis = SynapticHomeostasis(self.config)
        self.swr_generator = SharpWaveRippleGenerator(self.config)
        self.stage_manager = SleepStageManager(self.config)

        # Metrics
        self.metrics = ConsolidationMetrics()
        self.metrics.time_per_stage = {state: 0.0 for state in SleepState}

        # State
        self.total_timesteps = 0
        self.is_consolidating = False

    def step(
        self,
        activity_level: float,
        dt: float = 1.0
    ) -> SleepConsolidationOutput:
        """
        Single consolidation timestep.

        Args:
            activity_level: Current system activity [0, 1]
            dt: Time delta

        Returns:
            SleepConsolidationOutput with current state and metrics
        """
        self.total_timesteps += 1

        # Update state machine
        state, state_changed = self.state_machine.step(activity_level, dt)

        # Track time per stage
        self.metrics.time_per_stage[state] = (
            self.metrics.time_per_stage.get(state, 0.0) + dt
        )
        self.metrics.total_sleep_time += dt if self.state_machine.is_sleeping() else 0

        # Get stage-specific parameters
        neuromod_targets = self.stage_manager.get_neuromod_targets(state)
        gate_modulation = self.stage_manager.get_gate_modulation(state)

        # Apply neuromodulation targets
        if self.neuromodulation is not None:
            self._apply_neuromod_targets(neuromod_targets)

        # Check for SWR and replay
        swr_triggered = False
        replays_this_step = 0

        if self.swr_generator.check_for_ripple(state, self.total_timesteps):
            swr_triggered = True
            ripple = self.swr_generator.generate_ripple(float(self.total_timesteps))
            replays_this_step = self._run_swr_replay(ripple)
            self.metrics.replays_triggered += replays_this_step
            self.metrics.swr_events.append(ripple)

        # Run counterfactual dreams in REM
        if state == SleepState.REM and self.dream_mode is not None:
            self._run_rem_dreams()

        # Apply synaptic homeostasis
        if state in [SleepState.NREM_N3, SleepState.REM]:
            self._apply_synaptic_homeostasis(state)

        # Apply gate modulation to routing system
        if self.routing_system is not None:
            self._apply_gate_modulation(gate_modulation)

        # Update metrics
        self.metrics.cycles_completed = self.state_machine.cycles_completed
        self.metrics.weight_reduction_ratio = self.synaptic_homeostasis.get_scaling_ratio()

        return SleepConsolidationOutput(
            state=state,
            state_changed=state_changed,
            swr_triggered=swr_triggered,
            replays_this_step=replays_this_step,
            neuromod_targets=neuromod_targets,
            gate_modulation=gate_modulation,
            metrics=self.metrics
        )

    def enter_sleep_cycle(
        self,
        max_duration: Optional[float] = None
    ) -> ConsolidationMetrics:
        """
        Run a complete sleep cycle (or until max duration).

        Args:
            max_duration: Maximum duration in simulated time

        Returns:
            ConsolidationMetrics after sleep
        """
        self.is_consolidating = True

        # Force transition to sleep
        self.state_machine.force_state(SleepState.DROWSY)

        elapsed = 0.0
        dt = 1.0

        while True:
            output = self.step(activity_level=0.0, dt=dt)
            elapsed += dt

            # Check exit conditions
            if output.state == SleepState.WAKE:
                break
            if max_duration and elapsed >= max_duration:
                self.state_machine.force_wake()
                break

        self.is_consolidating = False
        return self.metrics

    def immediate_consolidation(
        self,
        num_replays: int = 5
    ) -> ConsolidationMetrics:
        """
        Quick consolidation without full sleep cycle.

        Useful for immediate memory strengthening.

        Args:
            num_replays: Number of memories to replay

        Returns:
            ConsolidationMetrics
        """
        if self.hippocampus is None:
            return self.metrics

        # Select and replay memories
        memories = list(self.hippocampus.memories)
        if len(memories) > 0:
            indices = self.swr_generator.select_memories_for_replay(
                memories, min(num_replays, len(memories))
            )

            for idx in indices:
                memory = memories[idx]
                memory.strength = min(1.0, memory.strength + 0.1)
                memory.retrieval_count += 1
                self.metrics.replays_triggered += 1

        return self.metrics

    def _run_swr_replay(self, ripple: RippleEvent) -> int:
        """Run SWR-triggered hippocampal replay."""
        if self.hippocampus is None:
            return 0

        memories = list(self.hippocampus.memories)
        if len(memories) == 0:
            return 0

        # Select memories for replay
        k = self.config.swr_replay_count
        indices = self.swr_generator.select_memories_for_replay(memories, k)

        # Replay each memory
        for idx in indices:
            memory = memories[idx]

            # Pattern completion through CA3
            if hasattr(self.hippocampus, 'pattern_completion'):
                self.hippocampus.pattern_completion(memory.state, memory.context)

            # Strengthen memory
            memory.strength = min(1.0, memory.strength + 0.05 * ripple.strength)
            memory.retrieval_count += 1

            self.metrics.memory_strength_changes.append(0.05 * ripple.strength)

        self.swr_generator.complete_ripple(indices)
        return len(indices)

    def _run_rem_dreams(self):
        """Run REM-stage counterfactual dreams."""
        if self.dream_mode is None or self.hippocampus is None:
            return

        # Use dream_mode's existing dream cycle if available
        if hasattr(self.dream_mode, 'dream_cycle'):
            memories = list(self.hippocampus.memories)
            if len(memories) > 0:
                # Run a mini dream cycle
                if hasattr(self.dream_mode, 'enter_dream_state'):
                    self.dream_mode.enter_dream_state()

                # Extract patterns
                if hasattr(self.dream_mode, 'extract_patterns'):
                    patterns = self.dream_mode.extract_patterns(memories)
                    self.metrics.patterns_discovered += len(patterns)

                if hasattr(self.dream_mode, 'exit_dream_state'):
                    self.dream_mode.exit_dream_state()

    def _apply_neuromod_targets(self, targets: Dict[str, float]):
        """Apply neuromodulator targets."""
        if self.neuromodulation is None:
            return

        # Gradually move toward targets
        alpha = 0.1
        levels = self.neuromodulation.levels

        if hasattr(levels, 'dopamine'):
            levels.dopamine += alpha * (targets['dopamine'] - levels.dopamine)
        if hasattr(levels, 'serotonin'):
            levels.serotonin += alpha * (targets['serotonin'] - levels.serotonin)
        if hasattr(levels, 'norepinephrine'):
            levels.norepinephrine += alpha * (targets['norepinephrine'] - levels.norepinephrine)

    def _apply_synaptic_homeostasis(self, stage: SleepState):
        """Apply synaptic homeostasis to relevant weights."""
        if self.thalamus is None:
            return

        # Collect weights from thalamus
        weights = {}
        if hasattr(self.thalamus, 'W_in'):
            for m, W in self.thalamus.W_in.items():
                weights[f'W_in_{m}'] = W
        if hasattr(self.thalamus, 'G'):
            for m, G in self.thalamus.G.items():
                weights[f'G_{m}'] = G

        # Apply homeostasis
        scaled = self.synaptic_homeostasis.apply_homeostasis(weights, stage)

        # Write back
        for key, W in scaled.items():
            if key.startswith('W_in_'):
                m = key[5:]
                self.thalamus.W_in[m] = W
            elif key.startswith('G_'):
                m = key[2:]
                self.thalamus.G[m] = W

    def _apply_gate_modulation(self, modulation: Dict[str, Any]):
        """Apply gate modulation to hierarchical routing."""
        if self.routing_system is None:
            return

        # Update layer weights
        if 'layer_weights' in modulation:
            self.routing_system.update_layer_weights(modulation['layer_weights'])

    def should_sleep(self, activity_history: deque) -> bool:
        """
        Determine if system should enter sleep based on activity history.

        Args:
            activity_history: Recent activity levels

        Returns:
            True if sleep is recommended
        """
        if len(activity_history) < 10:
            return False

        recent = list(activity_history)[-30:]
        avg_activity = np.mean(recent)

        return avg_activity < 0.3

    def wake_up(self):
        """Force immediate wake-up."""
        self.state_machine.force_wake()
        self.is_consolidating = False

    def get_current_state(self) -> SleepState:
        """Get current sleep state."""
        return self.state_machine.current_state

    def is_sleeping(self) -> bool:
        """Check if currently in sleep state."""
        return self.state_machine.is_sleeping()

    def reset(self):
        """Reset consolidation system."""
        self.state_machine.reset()
        self.synaptic_homeostasis.reset()
        self.swr_generator.reset()
        self.metrics = ConsolidationMetrics()
        self.metrics.time_per_stage = {state: 0.0 for state in SleepState}
        self.total_timesteps = 0
        self.is_consolidating = False

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            'current_state': self.state_machine.current_state.value,
            'is_sleeping': self.is_sleeping(),
            'cycles_completed': self.state_machine.cycles_completed,
            'total_timesteps': self.total_timesteps,
            'metrics': self.metrics.to_dict(),
            'weight_scaling_ratio': self.synaptic_homeostasis.get_scaling_ratio(),
            'swr_count': self.swr_generator.get_ripple_count()
        }

    def get_state(self) -> Dict[str, Any]:
        """Get serializable state."""
        return {
            'current_state': self.state_machine.current_state.value,
            'state_duration': self.state_machine.state_duration,
            'cycles_completed': self.state_machine.cycles_completed,
            'total_timesteps': self.total_timesteps,
            'weight_scaling': self.synaptic_homeostasis.get_scaling_ratio(),
            'metrics': self.metrics.to_dict()
        }


# ============================================================================
# Factory Function
# ============================================================================

def create_sleep_consolidation(
    hippocampus: Optional['Hippocampus'] = None,
    dream_mode: Optional['DreamMode'] = None,
    neuromodulation: Optional['NeuromodulationSystem'] = None,
    seed: int = 42,
    **config_kwargs
) -> SleepConsolidation:
    """
    Factory function to create a SleepConsolidation system.

    Args:
        hippocampus: Hippocampal memory system
        dream_mode: Dream mode for replay
        neuromodulation: Neuromodulation system
        seed: Random seed
        **config_kwargs: Additional config parameters

    Returns:
        Configured SleepConsolidation
    """
    config = SleepConsolidationConfig(seed=seed, **config_kwargs)
    return SleepConsolidation(
        config=config,
        hippocampus=hippocampus,
        dream_mode=dream_mode,
        neuromodulation=neuromodulation
    )


# ============================================================================
# Demo
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SLEEP CONSOLIDATION SYSTEM DEMO")
    print("=" * 70)
    print()

    # Create system
    consolidator = create_sleep_consolidation()

    print("Sleep stages:")
    for state in SleepState:
        print(f"  - {state.value}")
    print()

    print("Simulating wake period (activity=0.6)...")
    for i in range(10):
        output = consolidator.step(activity_level=0.6, dt=1.0)
    print(f"  State: {output.state.value}")
    print()

    print("Simulating idle period (activity=0.1)...")
    for i in range(100):
        output = consolidator.step(activity_level=0.1, dt=1.0)
        if output.state_changed:
            print(f"  [{i}] Transitioned to: {output.state.value}")

    print()
    print(f"Final state: {output.state.value}")
    print(f"Cycles completed: {consolidator.state_machine.cycles_completed}")
    print()

    print("Statistics:")
    stats = consolidator.get_statistics()
    for key, value in stats.items():
        if not isinstance(value, dict):
            print(f"  {key}: {value}")
    print()
    print("=" * 70)
