"""
Brain Frequency Controller - Operating Modes based on Neural Oscillations

Maps brain wave frequencies to AI system operational modes:

    DELTA (1-4 Hz):   Meta-Learning, Evolution, Global Reset
    THETA (4-8 Hz):   Planning, Goals, Sequences, Path-Traces
    ALPHA (8-12 Hz):  Thalamus-Routing, Focus, Task-Switching
    BETA (13-30 Hz):  Actions, Motor, Tool-Execution
    GAMMA (30-120 Hz): Feature-Binding, LLM-Bursts, CTM-Steps

Like the brain, multiple modes can be active simultaneously,
but one mode is typically dominant.

Usage:
    from core.brain_frequency_controller import BrainFrequencyController, FrequencyMode

    controller = BrainFrequencyController()

    # Set dominant mode
    controller.set_mode(FrequencyMode.THETA)  # Planning mode

    # Auto-switch based on context
    controller.auto_switch(context={'task_type': 'planning', 'urgency': 0.8})

    # Get current state
    state = controller.get_state()
    print(f"Dominant: {state['dominant_mode']}")
    print(f"Active: {state['active_modes']}")
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
import threading
import time
import numpy as np

if TYPE_CHECKING:
    from core.multi_band_oscillator import MultiBandOscillator, FrequencyBand as OscBand


class FrequencyMode(Enum):
    """Brain wave frequency modes mapped to operational modes"""
    DELTA = "delta"      # 1-4 Hz:   Meta-Learning, Evolution
    THETA = "theta"      # 4-8 Hz:   Planning, Goals, Sequences
    ALPHA = "alpha"      # 8-12 Hz:  Routing, Focus, Switching
    BETA = "beta"        # 13-30 Hz: Actions, Execution
    GAMMA = "gamma"      # 30+ Hz:   Reasoning, LLM, CTM bursts


@dataclass
class FrequencyBand:
    """Frequency band configuration"""
    mode: FrequencyMode
    min_hz: float
    max_hz: float
    description: str
    primary_function: str
    associated_components: List[str]
    activation_threshold: float = 0.5


@dataclass
class ModeActivation:
    """Current activation state for a frequency mode"""
    mode: FrequencyMode
    activation: float  # 0.0 to 1.0
    is_dominant: bool
    last_activated: Optional[datetime] = None
    activation_count: int = 0


@dataclass
class Marker:
    """Memory marker for path-tracing and recovery"""
    marker_id: str
    timestamp: datetime
    mode: FrequencyMode
    context: Dict[str, Any]
    state_snapshot: Dict[str, Any]
    decision_point: str
    alternatives: List[str] = field(default_factory=list)
    confidence: float = 0.5
    visited: bool = False


class BrainFrequencyController:
    """
    Brain Frequency Controller

    Orchestrates operational modes based on neural oscillation metaphor.
    Enables smooth transitions between planning, routing, acting, and learning.
    """

    # Frequency band definitions
    FREQUENCY_BANDS = {
        FrequencyMode.DELTA: FrequencyBand(
            mode=FrequencyMode.DELTA,
            min_hz=1.0,
            max_hz=4.0,
            description="Deep learning and evolution",
            primary_function="Meta-Learning",
            associated_components=[
                "DreamMode",
                "EvolutionaryTrainer",
                "CTMSelector",
                "GlobalReset"
            ]
        ),
        FrequencyMode.THETA: FrequencyBand(
            mode=FrequencyMode.THETA,
            min_hz=4.0,
            max_hz=8.0,
            description="Planning and sequencing",
            primary_function="Goal-Oriented Planning",
            associated_components=[
                "HierarchicalPlanner",
                "ConversationPathPlanner",
                "GoalTracer",
                "MarkerSystem"
            ]
        ),
        FrequencyMode.ALPHA: FrequencyBand(
            mode=FrequencyMode.ALPHA,
            min_hz=8.0,
            max_hz=12.0,
            description="Routing and focus",
            primary_function="Thalamus Routing",
            associated_components=[
                "ThalamoPC6",
                "CTMDomainRouter",
                "AttentionMechanisms",
                "TaskSwitcher"
            ]
        ),
        FrequencyMode.BETA: FrequencyBand(
            mode=FrequencyMode.BETA,
            min_hz=13.0,
            max_hz=30.0,
            description="Action and execution",
            primary_function="Motor/Execution",
            associated_components=[
                "ToolExecutor",
                "ActionQueue",
                "SwarmAgents",
                "APIHandler"
            ]
        ),
        FrequencyMode.GAMMA: FrequencyBand(
            mode=FrequencyMode.GAMMA,
            min_hz=30.0,
            max_hz=120.0,
            description="Feature binding and reasoning",
            primary_function="Cognitive Bursts",
            associated_components=[
                "MultiLLMRouter",
                "CTMReasoner",
                "FeatureExtractor",
                "PatternRecognition"
            ]
        )
    }

    def __init__(
        self,
        default_mode: FrequencyMode = FrequencyMode.ALPHA,
        enable_auto_switch: bool = True,
        marker_capacity: int = 1000
    ):
        """
        Initialize Brain Frequency Controller

        Args:
            default_mode: Initial dominant mode
            enable_auto_switch: Enable automatic mode switching
            marker_capacity: Maximum markers to retain
        """
        # Mode activations
        self.activations: Dict[FrequencyMode, ModeActivation] = {
            mode: ModeActivation(
                mode=mode,
                activation=0.0,
                is_dominant=False
            )
            for mode in FrequencyMode
        }

        # Set default dominant mode
        self.dominant_mode = default_mode
        self.activations[default_mode].activation = 1.0
        self.activations[default_mode].is_dominant = True
        self.activations[default_mode].last_activated = datetime.now()

        # Auto-switch settings
        self.enable_auto_switch = enable_auto_switch
        self.auto_switch_threshold = 0.7  # Threshold to trigger mode switch

        # Marker system (Theta mode)
        self.markers: List[Marker] = []
        self.marker_capacity = marker_capacity
        self.marker_counter = 0

        # Mode handlers (callbacks)
        self.mode_handlers: Dict[FrequencyMode, List[Callable]] = {
            mode: [] for mode in FrequencyMode
        }

        # Thread safety
        self._lock = threading.Lock()

        # Statistics
        self.mode_switches = 0
        self.start_time = datetime.now()

        print(f"[BrainFrequencyController] Initialized")
        print(f"[BrainFrequencyController] Default mode: {default_mode.value}")
        print(f"[BrainFrequencyController] Auto-switch: {enable_auto_switch}")

    def set_mode(
        self,
        mode: FrequencyMode,
        activation: float = 1.0,
        suppress_others: bool = False
    ) -> Dict[str, Any]:
        """
        Set frequency mode activation

        Args:
            mode: Frequency mode to activate
            activation: Activation level (0.0 to 1.0)
            suppress_others: If True, reduce other mode activations

        Returns:
            Mode change result
        """
        with self._lock:
            old_dominant = self.dominant_mode

            # Update activation
            self.activations[mode].activation = min(1.0, max(0.0, activation))
            self.activations[mode].last_activated = datetime.now()
            self.activations[mode].activation_count += 1

            # Optionally suppress other modes
            if suppress_others:
                for other_mode in FrequencyMode:
                    if other_mode != mode:
                        self.activations[other_mode].activation *= 0.5

            # Determine new dominant mode
            self._update_dominant_mode()

            # Track mode switch
            if self.dominant_mode != old_dominant:
                self.mode_switches += 1
                print(f"[BrainFrequencyController] Mode switch: {old_dominant.value} -> {self.dominant_mode.value}")

                # Trigger mode handlers
                self._trigger_handlers(self.dominant_mode)

            return {
                'mode': mode.value,
                'activation': self.activations[mode].activation,
                'is_dominant': self.activations[mode].is_dominant,
                'previous_dominant': old_dominant.value,
                'current_dominant': self.dominant_mode.value,
                'switched': self.dominant_mode != old_dominant
            }

    def _update_dominant_mode(self):
        """Update which mode is dominant based on activations"""
        max_activation = 0.0
        new_dominant = self.dominant_mode

        for mode, state in self.activations.items():
            state.is_dominant = False
            if state.activation > max_activation:
                max_activation = state.activation
                new_dominant = mode

        self.dominant_mode = new_dominant
        self.activations[new_dominant].is_dominant = True

    def auto_switch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically determine and switch to appropriate mode based on context

        Args:
            context: Current context with task_type, urgency, complexity, etc.

        Returns:
            Mode switch result
        """
        if not self.enable_auto_switch:
            return {'switched': False, 'reason': 'auto_switch_disabled'}

        # Extract context features
        task_type = context.get('task_type', 'general')
        urgency = context.get('urgency', 0.5)
        complexity = context.get('complexity', 0.5)
        requires_learning = context.get('requires_learning', False)
        requires_action = context.get('requires_action', False)

        # Determine target mode based on context
        target_mode = self._determine_mode(
            task_type=task_type,
            urgency=urgency,
            complexity=complexity,
            requires_learning=requires_learning,
            requires_action=requires_action
        )

        # Calculate target activation
        target_activation = self._calculate_activation(
            urgency=urgency,
            complexity=complexity
        )

        # Switch if above threshold
        if target_activation >= self.auto_switch_threshold:
            result = self.set_mode(target_mode, target_activation)
            result['auto_switched'] = True
            result['reason'] = f"Context: {task_type}, urgency={urgency:.2f}, complexity={complexity:.2f}"
            return result

        return {
            'switched': False,
            'reason': f'Activation {target_activation:.2f} below threshold {self.auto_switch_threshold}',
            'suggested_mode': target_mode.value
        }

    def _determine_mode(
        self,
        task_type: str,
        urgency: float,
        complexity: float,
        requires_learning: bool,
        requires_action: bool
    ) -> FrequencyMode:
        """Determine appropriate mode based on context"""

        # DELTA: Meta-learning, evolution
        if requires_learning or task_type in ['learning', 'evolution', 'training', 'dream']:
            return FrequencyMode.DELTA

        # THETA: Planning, sequencing
        if task_type in ['planning', 'sequencing', 'goal', 'pathfinding', 'strategy']:
            return FrequencyMode.THETA

        # BETA: Action execution
        if requires_action or task_type in ['execute', 'action', 'tool', 'api']:
            return FrequencyMode.BETA

        # GAMMA: Intensive reasoning
        if complexity >= 0.75 or task_type in ['reasoning', 'analysis', 'llm', 'ctm']:
            return FrequencyMode.GAMMA

        # ALPHA: Default routing/focus
        return FrequencyMode.ALPHA

    def _calculate_activation(
        self,
        urgency: float,
        complexity: float
    ) -> float:
        """Calculate activation level based on context"""
        # Higher urgency or complexity = higher activation
        return min(1.0, 0.5 + urgency * 0.3 + complexity * 0.2)

    def _trigger_handlers(self, mode: FrequencyMode):
        """Trigger registered handlers for mode"""
        for handler in self.mode_handlers[mode]:
            try:
                handler(mode)
            except Exception as e:
                print(f"[BrainFrequencyController] Handler error: {e}")

    def register_handler(
        self,
        mode: FrequencyMode,
        handler: Callable[[FrequencyMode], None]
    ):
        """Register a callback for mode activation"""
        self.mode_handlers[mode].append(handler)

    # =========================================================================
    # MARKER SYSTEM (Theta Mode Feature)
    # =========================================================================

    def set_marker(
        self,
        decision_point: str,
        context: Dict[str, Any],
        state_snapshot: Optional[Dict[str, Any]] = None,
        alternatives: Optional[List[str]] = None,
        confidence: float = 0.5
    ) -> Marker:
        """
        Set a memory marker at current decision point

        Markers are used for:
        - Path tracing and backtracking
        - Recovery after failed attempts
        - Episodic memory formation
        - Alternative path exploration

        Args:
            decision_point: Description of decision point
            context: Current context
            state_snapshot: Optional state to preserve
            alternatives: Alternative paths not taken
            confidence: Confidence in current path

        Returns:
            Created marker
        """
        with self._lock:
            self.marker_counter += 1
            marker_id = f"M{self.marker_counter:06d}"

            marker = Marker(
                marker_id=marker_id,
                timestamp=datetime.now(),
                mode=self.dominant_mode,
                context=context.copy() if context else {},
                state_snapshot=state_snapshot.copy() if state_snapshot else {},
                decision_point=decision_point,
                alternatives=alternatives or [],
                confidence=confidence
            )

            self.markers.append(marker)

            # Trim if over capacity
            if len(self.markers) > self.marker_capacity:
                self.markers = self.markers[-self.marker_capacity:]

            print(f"[Marker] Set {marker_id}: {decision_point} (confidence={confidence:.2f})")

            return marker

    def get_marker(self, marker_id: str) -> Optional[Marker]:
        """Retrieve marker by ID"""
        for marker in self.markers:
            if marker.marker_id == marker_id:
                return marker
        return None

    def get_recent_markers(self, count: int = 10) -> List[Marker]:
        """Get most recent markers"""
        return self.markers[-count:]

    def get_unvisited_alternatives(self) -> List[Tuple[Marker, str]]:
        """Get markers with unvisited alternative paths"""
        alternatives = []
        for marker in self.markers:
            if not marker.visited and marker.alternatives:
                for alt in marker.alternatives:
                    alternatives.append((marker, alt))
        return alternatives

    def mark_visited(self, marker_id: str) -> bool:
        """Mark a marker as visited"""
        marker = self.get_marker(marker_id)
        if marker:
            marker.visited = True
            return True
        return False

    def jump_to_marker(self, marker_id: str) -> Optional[Dict[str, Any]]:
        """
        Jump back to a previous marker for recovery or alternative exploration

        Args:
            marker_id: Marker ID to jump to

        Returns:
            Marker state snapshot or None
        """
        marker = self.get_marker(marker_id)
        if marker:
            print(f"[Marker] Jumping to {marker_id}: {marker.decision_point}")

            # Switch to appropriate mode
            self.set_mode(marker.mode)

            return {
                'marker_id': marker_id,
                'decision_point': marker.decision_point,
                'context': marker.context,
                'state_snapshot': marker.state_snapshot,
                'alternatives': marker.alternatives,
                'timestamp': marker.timestamp.isoformat()
            }
        return None

    # =========================================================================
    # MULTI-BAND OSCILLATOR INTEGRATION
    # =========================================================================

    def set_multi_band_mode(
        self,
        multi_band_osc: 'MultiBandOscillator',
        sync_with_brain_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Link MultiBandOscillator to brain frequency modes

        When sync_with_brain_mode is True, the oscillator's band weights
        will be automatically adjusted when brain modes change.

        Args:
            multi_band_osc: MultiBandOscillator instance to link
            sync_with_brain_mode: Auto-sync oscillator with mode changes

        Returns:
            Link status and current configuration
        """
        self._multi_band_osc = multi_band_osc
        self._sync_multi_band = sync_with_brain_mode

        # Register handler to sync oscillator with mode changes
        if sync_with_brain_mode:
            def _sync_handler(mode: FrequencyMode):
                weights = self.get_recommended_band_weights()
                # The oscillator will use these weights on next step
                self._current_band_weights = weights

            # Register for all modes
            for mode in FrequencyMode:
                self.register_handler(mode, _sync_handler)

        # Initialize weights based on current mode
        self._current_band_weights = self.get_recommended_band_weights()

        return {
            'linked': True,
            'sync_enabled': sync_with_brain_mode,
            'current_mode': self.dominant_mode.value,
            'initial_weights': self._current_band_weights
        }

    def get_recommended_band_weights(self) -> Dict[str, float]:
        """
        Get recommended MultiBandOscillator band weights for current brain mode

        Maps brain frequency modes to oscillator band emphasis:
            - DELTA: Emphasize theta (slow, memory consolidation)
            - THETA: Emphasize theta (planning, sequences)
            - ALPHA: Balanced, slight alpha emphasis (routing)
            - BETA: Emphasize gamma (action execution)
            - GAMMA: Strong gamma emphasis (reasoning, binding)

        Returns:
            Dict with 'theta', 'alpha', 'gamma' weights
        """
        mode = self.dominant_mode

        # Mode-specific band weight recommendations
        weight_profiles = {
            FrequencyMode.DELTA: {
                'theta': 0.6,   # Memory consolidation
                'alpha': 0.3,   # Reduced routing
                'gamma': 0.1    # Minimal fast activity
            },
            FrequencyMode.THETA: {
                'theta': 0.7,   # Planning, sequences
                'alpha': 0.2,   # Some routing
                'gamma': 0.1    # Minimal binding
            },
            FrequencyMode.ALPHA: {
                'theta': 0.2,   # Some planning context
                'alpha': 0.6,   # Primary: routing, attention
                'gamma': 0.2    # Some binding
            },
            FrequencyMode.BETA: {
                'theta': 0.1,   # Minimal planning
                'alpha': 0.3,   # Moderate routing
                'gamma': 0.6    # Action execution
            },
            FrequencyMode.GAMMA: {
                'theta': 0.1,   # Minimal planning
                'alpha': 0.2,   # Some routing
                'gamma': 0.7    # Reasoning, binding, bursts
            }
        }

        return weight_profiles.get(mode, {
            'theta': 0.33,
            'alpha': 0.34,
            'gamma': 0.33
        })

    def get_current_band_weights(self) -> Optional[Dict[str, float]]:
        """
        Get current band weights if multi-band oscillator is linked

        Returns:
            Band weights dict or None if not linked
        """
        return getattr(self, '_current_band_weights', None)

    def step_multi_band(
        self,
        external_input: Optional[Dict[str, float]] = None,
        dt: float = 1.0
    ) -> Optional[Any]:
        """
        Step the linked MultiBandOscillator with current band weights

        Convenience method that steps the oscillator using the
        recommended band weights for the current brain mode.

        Args:
            external_input: External input for oscillator
            dt: Time step

        Returns:
            MultiBandState or None if no oscillator linked
        """
        osc = getattr(self, '_multi_band_osc', None)
        if osc is None:
            return None

        weights = self.get_recommended_band_weights()
        return osc.step(
            external_input=external_input,
            dt=dt,
            band_weights=weights
        )

    # =========================================================================
    # STATE AND STATISTICS
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """Get current controller state"""
        with self._lock:
            active_modes = [
                mode.value for mode, state in self.activations.items()
                if state.activation > 0.1
            ]

            return {
                'dominant_mode': self.dominant_mode.value,
                'active_modes': active_modes,
                'activations': {
                    mode.value: {
                        'activation': state.activation,
                        'is_dominant': state.is_dominant,
                        'activation_count': state.activation_count
                    }
                    for mode, state in self.activations.items()
                },
                'mode_switches': self.mode_switches,
                'markers_count': len(self.markers),
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds()
            }

    def get_band_info(self, mode: FrequencyMode) -> Dict[str, Any]:
        """Get frequency band information"""
        band = self.FREQUENCY_BANDS[mode]
        return {
            'mode': mode.value,
            'frequency_range': f"{band.min_hz}-{band.max_hz} Hz",
            'description': band.description,
            'primary_function': band.primary_function,
            'associated_components': band.associated_components
        }

    def get_all_bands(self) -> List[Dict[str, Any]]:
        """Get all frequency band information"""
        return [self.get_band_info(mode) for mode in FrequencyMode]

    def reset(self, mode: FrequencyMode = FrequencyMode.ALPHA):
        """Reset controller to default state"""
        with self._lock:
            for m in FrequencyMode:
                self.activations[m].activation = 0.0
                self.activations[m].is_dominant = False

            self.activations[mode].activation = 1.0
            self.activations[mode].is_dominant = True
            self.dominant_mode = mode
            self.mode_switches += 1

            print(f"[BrainFrequencyController] Reset to {mode.value}")


# =============================================================================
# FREQUENCY MIXER - Combines multiple modes
# =============================================================================

class FrequencyMixer:
    """
    Frequency Mixer - Enables simultaneous multi-mode operation

    Like the brain, multiple frequency bands can be active at once.
    The mixer blends their contributions based on current weights.
    """

    def __init__(self, controller: BrainFrequencyController):
        """
        Initialize Frequency Mixer

        Args:
            controller: Brain Frequency Controller instance
        """
        self.controller = controller
        self.blend_weights: Dict[FrequencyMode, float] = {
            mode: 0.0 for mode in FrequencyMode
        }

    def set_blend(self, weights: Dict[str, float]):
        """
        Set frequency blend weights

        Args:
            weights: Dict mapping mode names to weights (0-1)
        """
        for mode_name, weight in weights.items():
            try:
                mode = FrequencyMode(mode_name)
                self.blend_weights[mode] = min(1.0, max(0.0, weight))
            except ValueError:
                print(f"[FrequencyMixer] Unknown mode: {mode_name}")

        # Normalize weights
        total = sum(self.blend_weights.values())
        if total > 0:
            self.blend_weights = {
                mode: w / total
                for mode, w in self.blend_weights.items()
            }

    def get_blended_components(self) -> List[str]:
        """Get list of components to activate based on blend"""
        components = []
        for mode, weight in self.blend_weights.items():
            if weight > 0.1:
                band = self.controller.FREQUENCY_BANDS[mode]
                components.extend(band.associated_components)
        return list(set(components))

    def suggest_processing_order(self) -> List[FrequencyMode]:
        """Suggest processing order based on blend weights"""
        # Sort by weight, descending
        sorted_modes = sorted(
            self.blend_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [mode for mode, weight in sorted_modes if weight > 0.1]


# =============================================================================
# DEMO
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  BRAIN FREQUENCY CONTROLLER DEMO")
    print("=" * 70)

    # Initialize controller
    controller = BrainFrequencyController(
        default_mode=FrequencyMode.ALPHA,
        enable_auto_switch=True
    )

    # Show all frequency bands
    print("\n[Frequency Bands]")
    for band_info in controller.get_all_bands():
        print(f"\n  {band_info['mode'].upper()} ({band_info['frequency_range']})")
        print(f"    {band_info['description']}")
        print(f"    Function: {band_info['primary_function']}")
        print(f"    Components: {', '.join(band_info['associated_components'][:3])}...")

    # Test mode switching
    print("\n" + "=" * 70)
    print("  MODE SWITCHING TEST")
    print("=" * 70)

    # Switch to planning mode
    print("\n[Test 1] Switching to THETA (Planning)")
    result = controller.set_mode(FrequencyMode.THETA)
    print(f"  Result: {result}")

    # Auto-switch based on context
    print("\n[Test 2] Auto-switch with high complexity task")
    result = controller.auto_switch({
        'task_type': 'reasoning',
        'urgency': 0.8,
        'complexity': 0.9
    })
    print(f"  Result: {result}")

    # Set marker
    print("\n" + "=" * 70)
    print("  MARKER SYSTEM TEST")
    print("=" * 70)

    print("\n[Test 3] Setting markers")
    marker1 = controller.set_marker(
        decision_point="Choose architecture pattern",
        context={'task': 'design_system'},
        alternatives=['microservices', 'monolith', 'serverless'],
        confidence=0.7
    )
    print(f"  Created: {marker1.marker_id}")

    marker2 = controller.set_marker(
        decision_point="Select database",
        context={'task': 'design_system'},
        alternatives=['postgresql', 'mongodb', 'redis'],
        confidence=0.6
    )
    print(f"  Created: {marker2.marker_id}")

    # Get unvisited alternatives
    print("\n[Test 4] Getting unvisited alternatives")
    alternatives = controller.get_unvisited_alternatives()
    for marker, alt in alternatives[:5]:
        print(f"  {marker.marker_id}: {marker.decision_point} -> {alt}")

    # Jump to marker
    print("\n[Test 5] Jump to marker")
    jump_result = controller.jump_to_marker(marker1.marker_id)
    if jump_result:
        print(f"  Jumped to: {jump_result['decision_point']}")
        print(f"  Alternatives: {jump_result['alternatives']}")

    # Get state
    print("\n" + "=" * 70)
    print("  FINAL STATE")
    print("=" * 70)
    state = controller.get_state()
    print(f"\n  Dominant mode: {state['dominant_mode']}")
    print(f"  Active modes: {state['active_modes']}")
    print(f"  Mode switches: {state['mode_switches']}")
    print(f"  Markers: {state['markers_count']}")

    # Test frequency mixer
    print("\n" + "=" * 70)
    print("  FREQUENCY MIXER TEST")
    print("=" * 70)

    mixer = FrequencyMixer(controller)
    mixer.set_blend({
        'theta': 0.4,   # Planning
        'gamma': 0.4,   # Reasoning
        'beta': 0.2     # Action
    })

    print("\n[Test 6] Blended operation")
    print(f"  Processing order: {[m.value for m in mixer.suggest_processing_order()]}")
    print(f"  Active components: {mixer.get_blended_components()[:5]}...")

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
