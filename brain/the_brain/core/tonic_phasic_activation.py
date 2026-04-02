"""
Tonic + Phasic Tool Activation Model

Like neuromodulation: steady baseline (tonic) + dynamic bursts (phasic) per tool.

    activation(tool, t) = τ_tool + φ(state, cell, t)
                          ↑         ↑
                       TONIC     PHASIC
                     (stable)   (dynamic)

TONIC (per tool):
    - Learned base firing rate for each tool
    - Slowly adapts over training
    - Provides stable learning signal
    - E.g., docker: τ=0.3, kubectl: τ=0.2, file_read: τ=0.5

PHASIC (dynamic):
    - CTM state-dependent bursts
    - Responds to current context
    - Can be positive (boost) or negative (suppress)
    - Changes rapidly based on temporal dynamics

Benefits:
    - Stable learning signal (tonic is predictable)
    - Dynamic adaptation (phasic responds to state)
    - Easier credit assignment
    - Matches neuromodulation patterns

Based on neuroscience research:
    - Tonic dopamine provides steady baseline motivation
    - Phasic dopamine bursts signal reward prediction errors
    - This model applies the same principle to tool selection
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque

from core.temporal_state_builder import TemporalBrainState


@dataclass
class ToolActivationProfile:
    """Activation profile for a single tool"""
    tool_name: str

    # Tonic (steady baseline)
    tonic_level: float = 0.3          # Base firing rate (0-1)
    tonic_learning_rate: float = 0.01  # How fast tonic adapts

    # Phasic (dynamic component)
    phasic_activation: float = 0.0    # Current phasic value (-1 to 1)
    phasic_decay: float = 0.1         # How fast phasic decays to 0

    # Statistics
    total_activations: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_duration_ms: float = 0.0

    # History
    activation_history: deque = field(default_factory=lambda: deque(maxlen=100))
    outcome_history: deque = field(default_factory=lambda: deque(maxlen=50))

    @property
    def current_activation(self) -> float:
        """Total activation = tonic + phasic"""
        return np.clip(self.tonic_level + self.phasic_activation, 0.0, 1.0)

    @property
    def success_rate(self) -> float:
        total = self.total_successes + self.total_failures
        return self.total_successes / total if total > 0 else 0.5

    def update_tonic(self, target: float):
        """Slowly adapt tonic toward target"""
        delta = target - self.tonic_level
        self.tonic_level += self.tonic_learning_rate * delta
        self.tonic_level = np.clip(self.tonic_level, 0.1, 0.9)

    def apply_phasic_burst(self, magnitude: float):
        """Apply a phasic burst (positive or negative)"""
        self.phasic_activation += magnitude
        self.phasic_activation = np.clip(self.phasic_activation, -0.5, 0.5)

    def decay_phasic(self):
        """Decay phasic component toward 0"""
        self.phasic_activation *= (1.0 - self.phasic_decay)

    def record_activation(self, success: bool, duration_ms: float):
        """Record an activation outcome"""
        self.total_activations += 1
        if success:
            self.total_successes += 1
        else:
            self.total_failures += 1

        # Update running average duration
        if self.avg_duration_ms == 0:
            self.avg_duration_ms = duration_ms
        else:
            self.avg_duration_ms = 0.9 * self.avg_duration_ms + 0.1 * duration_ms

        # Update histories
        self.activation_history.append((datetime.now(), self.current_activation))
        self.outcome_history.append((datetime.now(), success))

    def to_dict(self) -> Dict:
        return {
            'tool_name': self.tool_name,
            'tonic_level': self.tonic_level,
            'phasic_activation': self.phasic_activation,
            'current_activation': self.current_activation,
            'success_rate': self.success_rate,
            'total_activations': self.total_activations,
            'avg_duration_ms': self.avg_duration_ms
        }


@dataclass
class ActivationVector:
    """Combined activation vector for all tools"""
    activations: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_array(self, tool_order: List[str]) -> np.ndarray:
        """Convert to numpy array with given tool ordering"""
        return np.array([self.activations.get(tool, 0.0) for tool in tool_order])

    def get_top_k(self, k: int = 5) -> List[Tuple[str, float]]:
        """Get top k tools by activation"""
        sorted_tools = sorted(self.activations.items(), key=lambda x: x[1], reverse=True)
        return sorted_tools[:k]


class TonicPhasicActivation:
    """
    Tonic + Phasic activation model for tool selection

    Key features:
    - Per-tool tonic baselines that slowly adapt
    - Phasic bursts based on CTM state
    - State-dependent modulation
    - Outcome-based learning
    """

    # Default tonic levels for common tool categories
    DEFAULT_TONIC_LEVELS = {
        # High baseline (frequently useful)
        'file_read': 0.5,
        'file_list': 0.45,
        'search_files': 0.45,

        # Medium baseline
        'docker_run': 0.35,
        'docker_ps': 0.35,
        'kubectl_get': 0.35,
        'git_status': 0.4,

        # Lower baseline (more specific)
        'docker_build': 0.25,
        'kubectl_apply': 0.25,
        'git_push': 0.2,

        # Cautious baseline (dangerous operations)
        'file_delete': 0.15,
        'kubectl_delete': 0.15,
        'docker_stop': 0.2,

        # Default for unknown tools
        '__default__': 0.3
    }

    def __init__(
        self,
        known_tools: Optional[Set[str]] = None,
        tonic_learning_rate: float = 0.01,
        phasic_decay: float = 0.1,
        state_influence: float = 0.3
    ):
        """
        Initialize tonic-phasic activation model

        Args:
            known_tools: Set of known tool names
            tonic_learning_rate: How fast tonic adapts
            phasic_decay: How fast phasic decays
            state_influence: How much state affects phasic (0-1)
        """
        self.known_tools = known_tools or set()
        self.tonic_learning_rate = tonic_learning_rate
        self.phasic_decay = phasic_decay
        self.state_influence = state_influence

        # Tool profiles
        self.profiles: Dict[str, ToolActivationProfile] = {}

        # Initialize profiles for known tools
        for tool in self.known_tools:
            self._ensure_profile(tool)

        # State tracking
        self.last_state: Optional[TemporalBrainState] = None
        self.last_activation: Optional[ActivationVector] = None

    def _ensure_profile(self, tool_name: str) -> ToolActivationProfile:
        """Ensure a profile exists for a tool"""
        if tool_name not in self.profiles:
            default_tonic = self.DEFAULT_TONIC_LEVELS.get(
                tool_name,
                self.DEFAULT_TONIC_LEVELS['__default__']
            )
            self.profiles[tool_name] = ToolActivationProfile(
                tool_name=tool_name,
                tonic_level=default_tonic,
                tonic_learning_rate=self.tonic_learning_rate,
                phasic_decay=self.phasic_decay
            )
        return self.profiles[tool_name]

    def compute_activations(
        self,
        state: TemporalBrainState,
        tools: Optional[List[str]] = None
    ) -> ActivationVector:
        """
        Compute activation levels for all tools based on state

        Args:
            state: Current brain state
            tools: Specific tools to compute (all if None)

        Returns:
            ActivationVector with per-tool activations
        """
        tools_to_compute = tools or list(self.profiles.keys()) or list(self.known_tools)

        activations = {}

        for tool in tools_to_compute:
            profile = self._ensure_profile(tool)

            # Decay phasic component
            profile.decay_phasic()

            # Compute state-dependent phasic burst
            phasic_burst = self._compute_phasic_burst(tool, state)
            profile.apply_phasic_burst(phasic_burst * self.state_influence)

            # Record final activation
            activations[tool] = profile.current_activation

        self.last_state = state
        self.last_activation = ActivationVector(activations=activations)

        return self.last_activation

    def _compute_phasic_burst(
        self,
        tool: str,
        state: TemporalBrainState
    ) -> float:
        """
        Compute phasic burst for a tool based on current state

        State factors that influence burst:
        - Tool state (retry count, errors)
        - Static state (constraints)
        - Dynamic state (intent)
        - Conflicts (should suppress)
        """
        burst = 0.0

        # === Tool state influences ===
        tool_state = state.tool_state

        # Recent failure → suppress this tool
        if tool == tool_state.last_tool_name and not tool_state.last_tool_success:
            burst -= 0.2

        # High retry count → suppress
        if tool_state.retry_count > 2:
            burst -= 0.15

        # In backoff → strong suppression
        if tool_state.should_backoff:
            burst -= 0.3

        # === Static state influences ===
        static_state = state.static_state

        # Check if tool matches any constraints
        tool_lower = tool.lower()

        # Docker tools get boost if container IDs present
        if 'docker' in tool_lower and static_state.container_ids:
            burst += 0.1

        # File tools get boost if file paths present
        if 'file' in tool_lower and static_state.file_paths:
            burst += 0.1

        # Check prohibitions
        for prohibition in static_state.prohibitions:
            if tool_lower in prohibition.lower():
                burst -= 0.3  # Strong suppression for prohibited tools

        # === Dynamic state influences ===
        dynamic_state = state.dynamic_state

        # Intent matching
        intent = dynamic_state.current_intent.lower()

        if 'deploy' in intent and 'docker' in tool_lower:
            burst += 0.15
        if 'search' in intent and 'search' in tool_lower:
            burst += 0.15
        if 'debug' in intent and 'log' in tool_lower:
            burst += 0.1
        if 'check' in intent and ('status' in tool_lower or 'get' in tool_lower):
            burst += 0.1

        # Need clarification → suppress all tools
        if dynamic_state.needs_clarification:
            burst -= 0.2

        # === Conflict influences ===
        if state.has_conflicts:
            burst -= 0.3  # Strong suppression when conflicts exist

        return burst

    def record_outcome(
        self,
        tool: str,
        success: bool,
        duration_ms: float = 0.0
    ):
        """
        Record tool execution outcome for learning

        Args:
            tool: Tool that was executed
            success: Whether execution succeeded
            duration_ms: Execution duration
        """
        profile = self._ensure_profile(tool)
        profile.record_activation(success, duration_ms)

        # Update tonic based on success rate
        # Tools with higher success rates should have higher tonic
        target_tonic = 0.2 + 0.5 * profile.success_rate
        profile.update_tonic(target_tonic)

        # Apply phasic based on immediate outcome
        if success:
            profile.apply_phasic_burst(0.1)  # Small boost for success
        else:
            profile.apply_phasic_burst(-0.2)  # Suppress on failure

    def get_tool_activation(self, tool: str) -> float:
        """Get current activation for a specific tool"""
        if tool in self.profiles:
            return self.profiles[tool].current_activation
        return self.DEFAULT_TONIC_LEVELS.get(tool, self.DEFAULT_TONIC_LEVELS['__default__'])

    def get_tonic_levels(self) -> Dict[str, float]:
        """Get all tonic levels"""
        return {name: profile.tonic_level for name, profile in self.profiles.items()}

    def get_phasic_levels(self) -> Dict[str, float]:
        """Get all phasic levels"""
        return {name: profile.phasic_activation for name, profile in self.profiles.items()}

    def set_tonic_level(self, tool: str, level: float):
        """Manually set tonic level for a tool"""
        profile = self._ensure_profile(tool)
        profile.tonic_level = np.clip(level, 0.1, 0.9)

    def boost_tool(self, tool: str, magnitude: float = 0.2):
        """Apply a manual phasic boost to a tool"""
        profile = self._ensure_profile(tool)
        profile.apply_phasic_burst(magnitude)

    def suppress_tool(self, tool: str, magnitude: float = 0.2):
        """Apply a manual phasic suppression to a tool"""
        profile = self._ensure_profile(tool)
        profile.apply_phasic_burst(-magnitude)

    def get_activation_vector(self, tool_order: Optional[List[str]] = None) -> np.ndarray:
        """Get activation as numpy array"""
        if tool_order is None:
            tool_order = list(self.profiles.keys())

        return np.array([
            self.profiles[t].current_activation if t in self.profiles else 0.3
            for t in tool_order
        ])

    def decay_all_phasic(self):
        """Decay phasic component for all tools"""
        for profile in self.profiles.values():
            profile.decay_phasic()

    def get_statistics(self) -> Dict:
        """Get activation statistics"""
        if not self.profiles:
            return {'num_tools': 0}

        tonic_levels = [p.tonic_level for p in self.profiles.values()]
        phasic_levels = [p.phasic_activation for p in self.profiles.values()]
        success_rates = [p.success_rate for p in self.profiles.values()]

        return {
            'num_tools': len(self.profiles),
            'tonic_stats': {
                'mean': float(np.mean(tonic_levels)),
                'std': float(np.std(tonic_levels)),
                'min': float(np.min(tonic_levels)),
                'max': float(np.max(tonic_levels))
            },
            'phasic_stats': {
                'mean': float(np.mean(phasic_levels)),
                'std': float(np.std(phasic_levels))
            },
            'success_rate_mean': float(np.mean(success_rates)),
            'total_activations': sum(p.total_activations for p in self.profiles.values())
        }

    def get_profile_summary(self) -> Dict[str, Dict]:
        """Get summary of all tool profiles"""
        return {name: profile.to_dict() for name, profile in self.profiles.items()}

    def visualize_activations(self) -> str:
        """ASCII visualization of current activations"""
        lines = ["Tool Activations (Tonic | Phasic = Total):"]
        lines.append("-" * 60)

        for name, profile in sorted(self.profiles.items(), key=lambda x: -x[1].current_activation):
            tonic = profile.tonic_level
            phasic = profile.phasic_activation
            total = profile.current_activation

            # Create bar visualization
            tonic_bar = "█" * int(tonic * 20)
            phasic_bar = ("+" if phasic >= 0 else "-") * min(int(abs(phasic) * 20), 10)
            total_bar = "▓" * int(total * 20)

            lines.append(f"  {name:20s} [{tonic_bar:20s}|{phasic_bar:10s}] = {total:.2f}")

        return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 70)
    print("TONIC + PHASIC TOOL ACTIVATION MODEL")
    print("=" * 70)
    print()
    print("Formula: activation(tool, t) = τ_tool + φ(state, cell, t)")
    print("         TONIC (steady) + PHASIC (dynamic)")
    print()

    # Create model with some tools
    known_tools = {'docker_run', 'docker_ps', 'docker_build', 'file_read', 'file_write', 'kubectl_apply'}
    model = TonicPhasicActivation(known_tools=known_tools)

    print("Initial Tonic Levels:")
    for tool, level in model.get_tonic_levels().items():
        print(f"  {tool}: {level:.2f}")
    print()

    # Simulate some outcomes
    print("Simulating outcomes...")
    model.record_outcome('docker_run', success=True, duration_ms=1000)
    model.record_outcome('docker_run', success=True, duration_ms=1200)
    model.record_outcome('docker_ps', success=True, duration_ms=500)
    model.record_outcome('file_read', success=False, duration_ms=100)  # Failure
    model.record_outcome('kubectl_apply', success=True, duration_ms=2000)
    print()

    # Show updated levels
    print("After outcomes:")
    print(model.visualize_activations())
    print()

    # Create a sample state and compute activations
    from core.temporal_state_builder import TemporalBrainState, StaticState, DynamicState, ToolState

    state = TemporalBrainState(
        static_state=StaticState(
            container_ids={'nginx': 'nginx:latest'},
            prohibitions=['must not delete production']
        ),
        dynamic_state=DynamicState(
            current_intent='deploy docker container'
        ),
        tool_state=ToolState()
    )

    print("Computing activations with state context...")
    activations = model.compute_activations(state)
    print()

    print("Top 5 tools by activation:")
    for tool, activation in activations.get_top_k(5):
        profile = model.profiles[tool]
        print(f"  {tool}: {activation:.3f} (tonic={profile.tonic_level:.2f}, phasic={profile.phasic_activation:.2f})")

    print()
    print("Statistics:", model.get_statistics())
    print()
    print("=" * 70)
