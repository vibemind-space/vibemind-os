"""
Temporal CTM - Continuous Temporal Machine for Tool Control

Extends KlotskiCTM with explicit temporal dynamics for tool call generation.

Key Innovations:
    1. Continuous Latent Dynamics: ḣ(t) = f(h(t), s(t))
       - Hidden state evolves continuously over time
       - Input s(t) is the 3-part brain state

    2. Timing Gate: σ(t) = g(h(t))
       - Learns WHEN to emit actions
       - Outputs probability of action at each timestep
       - High σ(t) → emit action, Low σ(t) → wait

    3. Discrete Action Emission: aₖ ~ π(h(tₖ))
       - When σ(t) crosses threshold, emit action
       - Action is sampled from policy over Drumpad cells
       - Policy π learned from training data

Integration with Tahlamus:
    - Receives: TemporalBrainState (3-part state)
    - Produces: Drumpad activations + timing signal
    - Respects: Tonic/Phasic tool activations
    - Blocks: On conflict states

The Temporal CTM is Layer 4 in the hierarchical planner.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import deque

from core.temporal_state_builder import TemporalBrainState
from core.drumpad import Drumpad, DrumpadAction, CellSemantics
from core.tonic_phasic_activation import TonicPhasicActivation, ActivationVector

# Phase 1b: Oscillator imports for synchronization-based control
try:
    from core.action_potential_oscillator import ActionPotentialOscillator, Channel
    from core.synchrony_encoder import SynchronyEncoder, SynchronyVector
    from core.regime_detector import RegimeDetector, Regime, RegimeClassification
    from core.drumpad_3xN import Drumpad3xN, DrumpadPattern
    from core.path_skeleton import EpisodeBuilder, PathChannel, PathRegime
    OSCILLATOR_AVAILABLE = True
except ImportError as e:
    print(f"[TemporalCTM] Oscillator modules not available: {e}")
    OSCILLATOR_AVAILABLE = False

# Try to import KlotskiCTM for integration
try:
    from core.klotski_ctm import KlotskiCTM, CTMInsight, KLOTSKI_AVAILABLE
except ImportError:
    KLOTSKI_AVAILABLE = False
    KlotskiCTM = None
    CTMInsight = None

# Phase 1c: Mamba SSM for enhanced sequence modeling
try:
    from mamba_ssm import Mamba
    MAMBA_AVAILABLE = True
    print("[TemporalCTM] Mamba SSM available - can use MambaLatentDynamics")
except ImportError:
    MAMBA_AVAILABLE = False
    Mamba = None


@dataclass
class TemporalDecision:
    """Decision output from Temporal CTM"""
    # Action information
    action: DrumpadAction
    cell_probabilities: np.ndarray

    # Timing information
    should_act: bool
    timing_confidence: float
    wait_time_ms: float

    # State information
    hidden_state_norm: float
    state_change_magnitude: float

    # Reasoning trace (if from KlotskiCTM)
    ctm_insight: Optional[Any] = None

    # Phase 1b: Oscillator-based decision info
    synchrony_vector: Optional[np.ndarray] = None
    regime: Optional[str] = None
    regime_confidence: float = 0.0
    drumpad_pattern: Optional[Any] = None  # DrumpadPattern from 3xN

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    blocked_by_conflict: bool = False
    block_reason: str = ""

    def to_dict(self) -> Dict:
        result = {
            'action': self.action.to_dict(),
            'should_act': self.should_act,
            'timing_confidence': self.timing_confidence,
            'wait_time_ms': self.wait_time_ms,
            'hidden_state_norm': self.hidden_state_norm,
            'blocked_by_conflict': self.blocked_by_conflict,
            'block_reason': self.block_reason
        }
        # Add oscillator info if available
        if self.synchrony_vector is not None:
            result['synchrony_vector'] = self.synchrony_vector.tolist()
        if self.regime:
            result['regime'] = self.regime
            result['regime_confidence'] = self.regime_confidence
        return result


class LatentDynamics(nn.Module):
    """
    Continuous latent dynamics module

    Implements: ḣ(t) = f(h(t), s(t))

    Uses GRU-style update for stable training.
    """

    def __init__(self, hidden_dim: int = 128, state_dim: int = 192):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.state_dim = state_dim

        # GRU-style dynamics
        self.update_gate = nn.Linear(hidden_dim + state_dim, hidden_dim)
        self.reset_gate = nn.Linear(hidden_dim + state_dim, hidden_dim)
        self.candidate = nn.Linear(hidden_dim + state_dim, hidden_dim)

        # Initial hidden state
        self.h0 = nn.Parameter(torch.zeros(hidden_dim))

    def forward(
        self,
        state: torch.Tensor,
        hidden: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Update hidden state based on input state

        Args:
            state: Input state [batch, state_dim]
            hidden: Previous hidden state [batch, hidden_dim]

        Returns:
            New hidden state [batch, hidden_dim]
        """
        batch_size = state.shape[0]

        if hidden is None:
            hidden = self.h0.unsqueeze(0).expand(batch_size, -1)

        # Concatenate hidden and state
        combined = torch.cat([hidden, state], dim=-1)

        # GRU-style update
        z = torch.sigmoid(self.update_gate(combined))
        r = torch.sigmoid(self.reset_gate(combined))
        h_candidate = torch.tanh(self.candidate(torch.cat([r * hidden, state], dim=-1)))

        # New hidden state
        h_new = (1 - z) * hidden + z * h_candidate

        return h_new

    def get_initial_state(self, batch_size: int = 1) -> torch.Tensor:
        """Get initial hidden state"""
        return self.h0.unsqueeze(0).expand(batch_size, -1)


class MambaLatentDynamics(nn.Module):
    """
    Mamba SSM-based latent dynamics (Phase 1c)

    Drop-in replacement for LatentDynamics using Selective State Space Model.

    Benefits over GRU:
    - Better long-range dependencies with selective state
    - Linear complexity O(L) with CUDA optimization
    - ~100x faster with custom CUDA kernels
    - Trainable SSM parameters

    Requires: pip install mamba-ssm torch>=2.0
    """

    def __init__(self, hidden_dim: int = 128, state_dim: int = 192):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.state_dim = state_dim

        if not MAMBA_AVAILABLE:
            raise ImportError(
                "Mamba SSM not available. Install with: pip install mamba-ssm"
            )

        # Input projection: state_dim → hidden_dim
        self.input_proj = nn.Linear(state_dim, hidden_dim)

        # Mamba SSM core
        self.mamba = Mamba(
            d_model=hidden_dim,
            d_state=16,           # SSM state dimension
            d_conv=4,             # Local convolution width
            expand=2,             # Expansion factor
            dt_rank='auto',       # Auto-tune delta rank
            dt_min=0.001,         # Min time scale
            dt_max=0.1,           # Max time scale
            dt_init='random',     # Random initialization
            dt_scale=1.0,
            dt_init_floor=1e-4,
            conv_bias=True,
            bias=False,
            use_fast_path=True    # CUDA optimizations
        )

        # Initial hidden state (for interface compatibility)
        self.h0 = nn.Parameter(torch.zeros(hidden_dim))

    def forward(
        self,
        state: torch.Tensor,
        hidden: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Update hidden state using Mamba SSM

        Args:
            state: Input state [batch, state_dim]
            hidden: Previous hidden state (ignored - Mamba manages state internally)

        Returns:
            New hidden state [batch, hidden_dim]
        """
        # Project input to hidden dimension
        x = self.input_proj(state)  # [batch, hidden_dim]

        # Add sequence dimension for Mamba
        x = x.unsqueeze(1)  # [batch, 1, hidden_dim]

        # Mamba forward pass
        y = self.mamba(x)  # [batch, 1, hidden_dim]

        # Remove sequence dimension
        return y.squeeze(1)  # [batch, hidden_dim]

    def get_initial_state(self, batch_size: int = 1) -> torch.Tensor:
        """Get initial hidden state (for interface compatibility)"""
        return self.h0.unsqueeze(0).expand(batch_size, -1)


class TimingGate(nn.Module):
    """
    Timing gate module

    Implements: σ(t) = g(h(t))

    Outputs probability of emitting action at current time.
    """

    def __init__(self, hidden_dim: int = 128):
        super().__init__()

        self.gate = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()
        )

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        """
        Compute timing probability

        Args:
            hidden: Hidden state [batch, hidden_dim]

        Returns:
            Timing probability [batch, 1]
        """
        return self.gate(hidden)


class ActionPolicy(nn.Module):
    """
    Action policy module

    Implements: π(a|h) - policy over Drumpad cells

    Outputs logits for 64 Drumpad cells.
    """

    def __init__(self, hidden_dim: int = 128, num_cells: int = 64):
        super().__init__()
        self.num_cells = num_cells

        self.policy = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, num_cells)
        )

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        """
        Compute action logits

        Args:
            hidden: Hidden state [batch, hidden_dim]

        Returns:
            Action logits [batch, num_cells]
        """
        return self.policy(hidden)

    def get_probabilities(self, hidden: torch.Tensor, temperature: float = 1.0) -> torch.Tensor:
        """Get action probabilities with temperature"""
        logits = self.forward(hidden) / temperature
        return F.softmax(logits, dim=-1)


class TemporalCTM:
    """
    Temporal Conscious Turing Machine

    Integrates:
    - Continuous latent dynamics
    - Timing gate for action emission
    - Action policy over Drumpad
    - Tonic/Phasic tool activations
    - KlotskiCTM for deep reasoning (optional)

    Information Flow:
        TemporalBrainState → Latent Dynamics → Hidden State
                                     ↓
                              Timing Gate → Should Act?
                                     ↓
                              Action Policy → Drumpad Cell
                                     ↓
                              Tonic/Phasic → Tool Activation
                                     ↓
                              TemporalDecision
    """

    def __init__(
        self,
        hidden_dim: int = 128,
        state_dim: int = 192,
        num_cells: int = 64,
        timing_threshold: float = 0.5,
        temperature: float = 1.0,
        use_klotski_ctm: bool = True,
        use_mamba: bool = False,
        use_oscillator_extended: bool = True,
        oscillator_dim: int = 9,
        device: str = 'cpu'
    ):
        """
        Initialize Temporal CTM

        Args:
            hidden_dim: Hidden state dimension
            state_dim: Input state dimension (from TemporalBrainState base)
            num_cells: Number of Drumpad cells
            timing_threshold: Threshold for action emission
            temperature: Softmax temperature for action selection
            use_klotski_ctm: Whether to use KlotskiCTM for deep reasoning
            use_mamba: Whether to use Mamba SSM for latent dynamics (Phase 1c)
            use_oscillator_extended: Whether to expect extended state with synchrony
            oscillator_dim: Dimension of oscillator synchrony vector (default 9)
            device: Torch device
        """
        self.hidden_dim = hidden_dim
        self.state_dim = state_dim
        self.num_cells = num_cells
        self.timing_threshold = timing_threshold
        self.temperature = temperature
        self.device = device

        # Token→Frequency: Extended state dimension
        self.use_oscillator_extended = use_oscillator_extended
        self.oscillator_dim = oscillator_dim
        self.effective_state_dim = state_dim + oscillator_dim if use_oscillator_extended else state_dim

        # Phase 1c: Choose dynamics module (Mamba SSM or GRU)
        self.use_mamba = use_mamba and MAMBA_AVAILABLE
        if self.use_mamba:
            self.dynamics = MambaLatentDynamics(hidden_dim, self.effective_state_dim).to(device)
            print(f"[TemporalCTM] Using Mamba SSM for latent dynamics (CUDA optimized)")
        else:
            self.dynamics = LatentDynamics(hidden_dim, self.effective_state_dim).to(device)
            if use_mamba and not MAMBA_AVAILABLE:
                print("[TemporalCTM] Mamba requested but not available, using GRU fallback")

        if use_oscillator_extended:
            print(f"[TemporalCTM] Extended state dimension: {self.effective_state_dim} ({state_dim} + {oscillator_dim} oscillator)")
        self.timing_gate = TimingGate(hidden_dim).to(device)
        self.action_policy = ActionPolicy(hidden_dim, num_cells).to(device)

        # Set to eval mode (inference)
        self.dynamics.eval()
        self.timing_gate.eval()
        self.action_policy.eval()

        # Current hidden state
        self.hidden_state: Optional[torch.Tensor] = None
        self.previous_hidden: Optional[torch.Tensor] = None

        # Initialize KlotskiCTM if available
        self.klotski_ctm = None
        if use_klotski_ctm and KLOTSKI_AVAILABLE:
            try:
                self.klotski_ctm = KlotskiCTM(
                    feature_dim=256,
                    consciousness_threshold=0.85,
                    max_reasoning_steps=30
                )
            except Exception as e:
                print(f"[TemporalCTM] Could not initialize KlotskiCTM: {e}")

        # Integration components
        self.drumpad = Drumpad(temperature=temperature)
        self.tonic_phasic = TonicPhasicActivation()

        # Phase 1b: Oscillator-based synchronization
        self.use_oscillator = OSCILLATOR_AVAILABLE
        self.oscillator = None
        self.synchrony_encoder = None
        self.regime_detector = None
        self.drumpad_3xN = None
        self.episode_builder = None

        if self.use_oscillator:
            try:
                self.oscillator = ActionPotentialOscillator(
                    natural_frequencies=(1.0, 1.2, 0.8),
                    coupling_strength=0.5,
                    use_neural_coupling=False  # Use Kuramoto for stability
                )
                self.synchrony_encoder = SynchronyEncoder(smoothing_alpha=0.1)
                self.regime_detector = RegimeDetector(stability_window=3)
                self.drumpad_3xN = Drumpad3xN(
                    amplitude_threshold=0.3,
                    multi_hit_enabled=True
                )
                self.episode_builder = None  # Created per-task
                print("[TemporalCTM] Phase 1b oscillator pipeline initialized")
            except Exception as e:
                print(f"[TemporalCTM] Oscillator init failed: {e}")
                self.use_oscillator = False

        # History tracking
        self.decision_history: deque = deque(maxlen=100)
        self.timing_history: deque = deque(maxlen=100)

        # Statistics
        self.total_decisions = 0
        self.total_actions = 0
        self.total_waits = 0
        self.total_blocks = 0

    def process(
        self,
        state: TemporalBrainState,
        task_description: str = "",
        force_reasoning: bool = False
    ) -> TemporalDecision:
        """
        Process brain state and produce temporal decision

        Args:
            state: Current 3-part brain state
            task_description: Optional task for deep reasoning
            force_reasoning: Force KlotskiCTM reasoning even if not needed

        Returns:
            TemporalDecision with action and timing
        """
        self.total_decisions += 1

        # Check for conflicts (blocks execution)
        if state.has_conflicts and state.conflict_count > 0:
            return self._create_blocked_decision(state, "Conflict detected in state")

        # Convert state to tensor (with or without oscillator extension)
        state_vector = state.to_vector(self.state_dim, include_oscillator=self.use_oscillator_extended)
        state_tensor = torch.tensor(state_vector, dtype=torch.float32).unsqueeze(0).to(self.device)

        # Update latent dynamics
        self.previous_hidden = self.hidden_state
        with torch.no_grad():
            self.hidden_state = self.dynamics(state_tensor, self.hidden_state)

        # Compute timing probability
        with torch.no_grad():
            timing_prob = self.timing_gate(self.hidden_state).item()

        # Compute action probabilities
        with torch.no_grad():
            action_probs = self.action_policy.get_probabilities(
                self.hidden_state,
                self.temperature
            ).squeeze(0).cpu().numpy()

        # Apply tonic/phasic modulation
        tool_activations = self.tonic_phasic.compute_activations(state)
        modulated_probs = self._apply_tonic_phasic(action_probs, tool_activations)

        # Decide whether to act
        should_act = timing_prob >= self.timing_threshold

        # Compute wait time if not acting
        wait_time_ms = 0.0
        if not should_act:
            # Wait time inversely proportional to timing probability
            wait_time_ms = (1.0 - timing_prob) * 1000.0  # Up to 1 second

        # Run KlotskiCTM if needed for deep reasoning
        ctm_insight = None
        if self.klotski_ctm and (force_reasoning or self._needs_deep_reasoning(state)):
            brain_state = {
                'modality_activations': {
                    'static': state.static_state.overall_confidence,
                    'dynamic': state.dynamic_state.intent_confidence,
                    'tool': state.tool_state.success_rate
                }
            }
            ctm_insight = self.klotski_ctm.reason(
                task_description or "Evaluate temporal action",
                brain_state,
                max_steps=20
            )

        # Get Drumpad action
        self.drumpad.current_probabilities = modulated_probs
        selected_cell = int(np.argmax(modulated_probs))
        action = self.drumpad._build_action(selected_cell, modulated_probs[selected_cell], None)

        # Calculate state change magnitude
        state_change = 0.0
        if self.previous_hidden is not None:
            state_change = torch.norm(self.hidden_state - self.previous_hidden).item()

        # Phase 1b: Oscillator pipeline for synchronization-based control
        sync_vector = None
        regime_name = None
        regime_conf = 0.0
        drumpad_pattern = None

        if self.use_oscillator and self.oscillator:
            try:
                # Convert tonic/phasic activations to oscillator inputs
                osc_input = self.oscillator.from_tonic_phasic(tool_activations.activations)

                # Step the oscillator
                osc_state = self.oscillator.step(external_input=osc_input)

                # Encode synchrony vector
                sync = self.synchrony_encoder.encode(osc_state)
                sync_vector = sync.vector

                # Detect regime
                regime_result = self.regime_detector.detect(sync)
                regime_name = regime_result.regime.value
                regime_conf = regime_result.confidence

                # Get 3×N drumpad pattern
                self.drumpad_3xN.reset_grid()
                drumpad_pattern = self.drumpad_3xN.activate(sync, regime_result.regime)

            except Exception as e:
                # Oscillator pipeline failed, continue with standard processing
                pass

        # Update statistics
        if should_act:
            self.total_actions += 1
        else:
            self.total_waits += 1

        # Create decision
        decision = TemporalDecision(
            action=action,
            cell_probabilities=modulated_probs,
            should_act=should_act,
            timing_confidence=timing_prob,
            wait_time_ms=wait_time_ms,
            hidden_state_norm=torch.norm(self.hidden_state).item(),
            state_change_magnitude=state_change,
            ctm_insight=ctm_insight,
            synchrony_vector=sync_vector,
            regime=regime_name,
            regime_confidence=regime_conf,
            drumpad_pattern=drumpad_pattern
        )

        # Record history
        self.decision_history.append(decision)
        self.timing_history.append((datetime.now(), timing_prob, should_act))

        return decision

    def _apply_tonic_phasic(
        self,
        cell_probs: np.ndarray,
        tool_activations: ActivationVector
    ) -> np.ndarray:
        """
        Apply tonic/phasic modulation to cell probabilities

        This combines the raw CTM policy with learned tool preferences.
        """
        # Get tool-to-cell mapping from drumpad
        tool_cells = self.drumpad.get_tool_cells()

        # Apply modulation for cells with known tool mappings
        modulated = cell_probs.copy()

        for tool, cell_id in tool_cells.items():
            if tool in tool_activations.activations:
                # Boost cell probability by tool activation
                tool_activation = tool_activations.activations[tool]
                modulated[cell_id] *= (0.5 + tool_activation)

        # Renormalize
        total = np.sum(modulated)
        if total > 0:
            modulated = modulated / total

        return modulated

    def _needs_deep_reasoning(self, state: TemporalBrainState) -> bool:
        """Check if deep CTM reasoning is needed"""
        # Need reasoning if:
        # - Uncertainty is high
        # - State changed significantly
        # - Multiple failures recently

        if state.overall_stability < 0.5:
            return True

        if state.dynamic_state.needs_clarification:
            return True

        if state.tool_state.consecutive_failures >= 2:
            return True

        return False

    def _create_blocked_decision(
        self,
        state: TemporalBrainState,
        reason: str
    ) -> TemporalDecision:
        """Create a blocked (no-op) decision"""
        self.total_blocks += 1

        # Return NOOP action
        noop_action = DrumpadAction(
            cell_id=0,
            semantic=CellSemantics.NOOP,
            tool_name=None,
            parameters={},
            confidence=0.0
        )

        return TemporalDecision(
            action=noop_action,
            cell_probabilities=np.zeros(self.num_cells),
            should_act=False,
            timing_confidence=0.0,
            wait_time_ms=1000.0,  # Wait 1 second
            hidden_state_norm=0.0,
            state_change_magnitude=0.0,
            blocked_by_conflict=True,
            block_reason=reason
        )

    def record_outcome(self, success: bool, tool_name: Optional[str] = None, duration_ms: float = 0.0):
        """Record outcome for learning"""
        if tool_name:
            self.tonic_phasic.record_outcome(tool_name, success, duration_ms)

        if self.decision_history:
            last_decision = self.decision_history[-1]
            cell_id = last_decision.action.cell_id
            self.drumpad.record_outcome(cell_id, success, duration_ms)

    def reset_state(self):
        """Reset hidden state to initial"""
        self.hidden_state = None
        self.previous_hidden = None

    def get_timing_statistics(self) -> Dict:
        """Get timing statistics"""
        if not self.timing_history:
            return {'no_data': True}

        probs = [p for _, p, _ in self.timing_history]
        acts = [a for _, _, a in self.timing_history]

        return {
            'mean_timing_prob': np.mean(probs),
            'std_timing_prob': np.std(probs),
            'action_rate': sum(acts) / len(acts),
            'history_size': len(self.timing_history)
        }

    def get_statistics(self) -> Dict:
        """Get overall statistics"""
        stats = {
            'hidden_dim': self.hidden_dim,
            'state_dim': self.state_dim,
            'effective_state_dim': self.effective_state_dim,
            'oscillator_extended': self.use_oscillator_extended,
            'oscillator_dim': self.oscillator_dim,
            'num_cells': self.num_cells,
            'timing_threshold': self.timing_threshold,
            'total_decisions': self.total_decisions,
            'total_actions': self.total_actions,
            'total_waits': self.total_waits,
            'total_blocks': self.total_blocks,
            'action_rate': self.total_actions / max(1, self.total_decisions),
            'block_rate': self.total_blocks / max(1, self.total_decisions),
            'timing_stats': self.get_timing_statistics(),
            'klotski_available': self.klotski_ctm is not None,
            'drumpad_stats': self.drumpad.get_statistics(),
            'tonic_phasic_stats': self.tonic_phasic.get_statistics()
        }

        # Phase 1b: Add oscillator statistics
        stats['oscillator_available'] = self.use_oscillator
        if self.use_oscillator and self.oscillator:
            stats['oscillator_stats'] = self.oscillator.get_statistics()
            if self.synchrony_encoder:
                stats['synchrony_stats'] = self.synchrony_encoder.get_statistics()
            if self.regime_detector:
                stats['regime_stats'] = self.regime_detector.get_statistics()
            if self.drumpad_3xN:
                stats['drumpad_3xN_stats'] = self.drumpad_3xN.get_statistics()

        # Phase 1c: Add Mamba SSM statistics
        stats['mamba_available'] = MAMBA_AVAILABLE
        stats['using_mamba'] = self.use_mamba
        stats['dynamics_type'] = 'MambaSSM' if self.use_mamba else 'GRU'

        return stats

    def save_state(self) -> Dict:
        """Save model state for persistence"""
        return {
            'dynamics': self.dynamics.state_dict(),
            'timing_gate': self.timing_gate.state_dict(),
            'action_policy': self.action_policy.state_dict(),
            'drumpad_mappings': self.drumpad.save_mappings(),
            'tonic_phasic_profiles': self.tonic_phasic.get_profile_summary()
        }

    def load_state(self, state: Dict):
        """Load model state from persistence"""
        if 'dynamics' in state:
            self.dynamics.load_state_dict(state['dynamics'])
        if 'timing_gate' in state:
            self.timing_gate.load_state_dict(state['timing_gate'])
        if 'action_policy' in state:
            self.action_policy.load_state_dict(state['action_policy'])
        if 'drumpad_mappings' in state:
            self.drumpad.load_mappings(state['drumpad_mappings'])


if __name__ == "__main__":
    print("=" * 70)
    print("TEMPORAL CTM - Continuous Temporal Machine for Tool Control")
    print("=" * 70)
    print()
    print("Key Components:")
    print("  1. Latent Dynamics: ḣ(t) = f(h(t), s(t))")
    print("  2. Timing Gate: σ(t) = g(h(t))")
    print("  3. Action Policy: aₖ ~ π(h(tₖ))")
    print()

    # Create Temporal CTM
    ctm = TemporalCTM(
        hidden_dim=128,
        state_dim=192,
        timing_threshold=0.5,
        use_klotski_ctm=False  # Disable for testing
    )

    print(f"Initialized TemporalCTM:")
    print(f"  Hidden dim: {ctm.hidden_dim}")
    print(f"  State dim: {ctm.state_dim}")
    print(f"  Timing threshold: {ctm.timing_threshold}")
    print()

    # Create sample state
    from core.temporal_state_builder import TemporalBrainState, StaticState, DynamicState, ToolState

    state = TemporalBrainState(
        static_state=StaticState(
            container_ids={'nginx': 'nginx:latest'},
            primary_goal='Deploy web server'
        ),
        dynamic_state=DynamicState(
            current_intent='deploy',
            intent_confidence=0.8
        ),
        tool_state=ToolState(
            last_tool_name='docker_ps',
            last_tool_success=True
        )
    )

    # Process state
    print("Processing state...")
    decision = ctm.process(state, task_description="Deploy nginx container")

    print()
    print("Decision:")
    print(f"  Cell ID: {decision.action.cell_id}")
    print(f"  Semantic: {decision.action.semantic.value}")
    print(f"  Should Act: {decision.should_act}")
    print(f"  Timing Confidence: {decision.timing_confidence:.3f}")
    print(f"  Wait Time: {decision.wait_time_ms:.0f}ms")
    print(f"  Hidden State Norm: {decision.hidden_state_norm:.3f}")
    print()

    # Process a few more times to see dynamics
    print("Processing multiple states to see dynamics:")
    for i in range(5):
        state.dynamic_state.current_turn = i + 1
        decision = ctm.process(state)
        print(f"  Turn {i+1}: timing={decision.timing_confidence:.3f}, "
              f"act={decision.should_act}, cell={decision.action.cell_id}")

    print()
    print("Statistics:", ctm.get_statistics())
    print()
    print("=" * 70)
