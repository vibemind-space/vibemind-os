"""
Action Potential Oscillator - 3 Coupled Oscillators for Temporal Control

Implements 3 coupled oscillators (A, B, C) that encode action potentials:
    A(t) = Advance (Exploit)     - Move toward goal
    B(t) = Explore (Branch)      - Try alternatives
    C(t) = Correct (Stabilize)   - Repair/validate/retry

Each oscillator is represented as a complex number:
    X(t) = |X(t)| * e^(i * theta_X(t))

Where:
    |X(t)| = amplitude (activation strength)
    theta_X(t) = phase (position in cycle)

The coupling between oscillators creates emergent behavior:
    - In-phase: oscillators synchronized, collaborative
    - Anti-phase: oscillators alternating, competitive
    - Drifting: no lock, transitional state

Integration:
    - Reads: Tonic+Phasic activations from existing system
    - Updates: 3 oscillator states per beat
    - Outputs: Amplitudes + Phases for synchrony encoding
"""

import numpy as np
import torch
import torch.nn as nn
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import cmath


class Channel(Enum):
    """Action potential channels"""
    ADVANCE = "advance"   # A - Exploit, move toward goal
    EXPLORE = "explore"   # B - Branch, try alternatives
    CORRECT = "correct"   # C - Stabilize, repair/retry


@dataclass
class OscillatorState:
    """State of a single oscillator"""
    channel: Channel
    amplitude: float = 0.5       # |X| in [0, 1]
    phase: float = 0.0           # theta in [0, 2*pi)
    frequency: float = 1.0       # natural frequency (radians per beat)

    # History tracking
    amplitude_history: List[float] = field(default_factory=list)
    phase_history: List[float] = field(default_factory=list)

    @property
    def complex_value(self) -> complex:
        """Get complex representation: |X| * e^(i*theta)"""
        return cmath.rect(self.amplitude, self.phase)

    @property
    def real(self) -> float:
        """Real component: |X| * cos(theta)"""
        return self.amplitude * np.cos(self.phase)

    @property
    def imag(self) -> float:
        """Imaginary component: |X| * sin(theta)"""
        return self.amplitude * np.sin(self.phase)

    def to_vector(self) -> np.ndarray:
        """Convert to 2D vector [real, imag]"""
        return np.array([self.real, self.imag])

    def advance_phase(self, dt: float = 1.0):
        """Advance phase by dt * frequency"""
        self.phase = (self.phase + dt * self.frequency) % (2 * np.pi)

    def record_history(self, max_history: int = 100):
        """Record current state to history"""
        self.amplitude_history.append(self.amplitude)
        self.phase_history.append(self.phase)
        # Trim if too long
        if len(self.amplitude_history) > max_history:
            self.amplitude_history = self.amplitude_history[-max_history:]
            self.phase_history = self.phase_history[-max_history:]

    def to_dict(self) -> Dict:
        return {
            'channel': self.channel.value,
            'amplitude': self.amplitude,
            'phase': self.phase,
            'frequency': self.frequency,
            'real': self.real,
            'imag': self.imag
        }


@dataclass
class TripleOscillatorState:
    """Combined state of all 3 oscillators"""
    A: OscillatorState  # Advance
    B: OscillatorState  # Explore
    C: OscillatorState  # Correct

    beat_index: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def amplitudes(self) -> np.ndarray:
        """Get amplitude vector [|A|, |B|, |C|]"""
        return np.array([self.A.amplitude, self.B.amplitude, self.C.amplitude])

    @property
    def phases(self) -> np.ndarray:
        """Get phase vector [theta_A, theta_B, theta_C]"""
        return np.array([self.A.phase, self.B.phase, self.C.phase])

    @property
    def phase_differences(self) -> Dict[str, float]:
        """Get phase differences between pairs"""
        return {
            'AB': (self.A.phase - self.B.phase) % (2 * np.pi),
            'AC': (self.A.phase - self.C.phase) % (2 * np.pi),
            'BC': (self.B.phase - self.C.phase) % (2 * np.pi)
        }

    def to_6d_vector(self) -> np.ndarray:
        """Convert to 6D vector [A_real, A_imag, B_real, B_imag, C_real, C_imag]"""
        return np.concatenate([
            self.A.to_vector(),
            self.B.to_vector(),
            self.C.to_vector()
        ])

    def dominant_channel(self) -> Channel:
        """Get channel with highest amplitude"""
        amps = {'A': self.A.amplitude, 'B': self.B.amplitude, 'C': self.C.amplitude}
        max_channel = max(amps, key=amps.get)
        return {'A': Channel.ADVANCE, 'B': Channel.EXPLORE, 'C': Channel.CORRECT}[max_channel]

    def to_dict(self) -> Dict:
        return {
            'A': self.A.to_dict(),
            'B': self.B.to_dict(),
            'C': self.C.to_dict(),
            'beat_index': self.beat_index,
            'dominant': self.dominant_channel().value,
            'phase_differences': self.phase_differences
        }


class CouplingDynamics(nn.Module):
    """
    Neural network for oscillator coupling dynamics

    Learns how oscillators influence each other based on:
    - Current amplitudes and phases
    - External input (from Tonic+Phasic activations)
    """

    def __init__(self, hidden_dim: int = 32):
        super().__init__()

        # Input: 6D oscillator state + 3D external input = 9D
        # Output: 6D state update (delta for each oscillator)
        self.coupling_net = nn.Sequential(
            nn.Linear(9, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 6)
        )

        # Coupling strength matrix (learnable)
        # K[i,j] = how much oscillator j influences oscillator i
        self.coupling_matrix = nn.Parameter(torch.tensor([
            [0.0, -0.3, 0.2],    # A influenced by B (negative=competitive), C (positive=cooperative)
            [-0.3, 0.0, -0.2],   # B influenced by A (competitive), C (competitive)
            [0.2, -0.2, 0.0]     # C influenced by A (cooperative), B (competitive)
        ]))

    def forward(
        self,
        osc_state: torch.Tensor,    # [batch, 6] - current oscillator state
        external_input: torch.Tensor # [batch, 3] - Tonic+Phasic input for A, B, C
    ) -> torch.Tensor:
        """
        Compute state update

        Returns:
            [batch, 6] - delta to add to oscillator state
        """
        # Concatenate inputs
        combined = torch.cat([osc_state, external_input], dim=-1)

        # Neural coupling
        delta = self.coupling_net(combined)

        return delta


class ActionPotentialOscillator:
    """
    3 Coupled Oscillators for Temporal Action Control

    Manages three oscillators (A, B, C) that encode different action potentials:
    - A (Advance): Exploit mode, move toward goal
    - B (Explore): Branch mode, try alternatives
    - C (Correct): Stabilize mode, repair/validate/retry

    The oscillators are coupled through:
    1. Phase coupling (Kuramoto-style)
    2. Amplitude coupling (competition/cooperation)
    3. External input from Tonic+Phasic activations

    Usage:
        osc = ActionPotentialOscillator()

        # Update with external activation
        state = osc.step(external_input={'advance': 0.8, 'explore': 0.2, 'correct': 0.1})

        # Get synchrony-relevant info
        amplitudes = state.amplitudes
        phases = state.phases
    """

    def __init__(
        self,
        natural_frequencies: Tuple[float, float, float] = (1.0, 1.2, 0.8),
        coupling_strength: float = 0.5,
        amplitude_decay: float = 0.95,
        use_neural_coupling: bool = True,
        device: str = 'cpu'
    ):
        """
        Initialize oscillator system

        Args:
            natural_frequencies: Base frequencies for (A, B, C)
            coupling_strength: Global coupling strength
            amplitude_decay: Decay factor for amplitude (stability)
            use_neural_coupling: Use learned coupling dynamics
            device: Torch device
        """
        self.coupling_strength = coupling_strength
        self.amplitude_decay = amplitude_decay
        self.device = device

        # Initialize oscillators
        self.state = TripleOscillatorState(
            A=OscillatorState(
                channel=Channel.ADVANCE,
                amplitude=0.5,
                phase=0.0,
                frequency=natural_frequencies[0]
            ),
            B=OscillatorState(
                channel=Channel.EXPLORE,
                amplitude=0.5,
                phase=2 * np.pi / 3,  # 120 degrees offset
                frequency=natural_frequencies[1]
            ),
            C=OscillatorState(
                channel=Channel.CORRECT,
                amplitude=0.5,
                phase=4 * np.pi / 3,  # 240 degrees offset
                frequency=natural_frequencies[2]
            )
        )

        # Neural coupling (optional)
        self.use_neural_coupling = use_neural_coupling
        if use_neural_coupling:
            self.coupling_dynamics = CouplingDynamics().to(device)
            self.coupling_dynamics.eval()
        else:
            self.coupling_dynamics = None

        # History
        self.state_history: List[TripleOscillatorState] = []

    def step(
        self,
        external_input: Optional[Dict[str, float]] = None,
        dt: float = 1.0
    ) -> TripleOscillatorState:
        """
        Advance oscillators by one time step

        Args:
            external_input: Dict with keys 'advance', 'explore', 'correct'
                           Values are activation strengths [0, 1]
            dt: Time step size

        Returns:
            Updated TripleOscillatorState
        """
        # Record current state to history
        self.state.A.record_history()
        self.state.B.record_history()
        self.state.C.record_history()

        # Parse external input
        ext_A = external_input.get('advance', 0.0) if external_input else 0.0
        ext_B = external_input.get('explore', 0.0) if external_input else 0.0
        ext_C = external_input.get('correct', 0.0) if external_input else 0.0

        if self.use_neural_coupling and self.coupling_dynamics:
            # Neural coupling dynamics
            self._neural_step(ext_A, ext_B, ext_C, dt)
        else:
            # Analytical coupling (Kuramoto-style)
            self._kuramoto_step(ext_A, ext_B, ext_C, dt)

        # Update beat index
        self.state.beat_index += 1
        self.state.timestamp = datetime.now()

        # Store in history
        self.state_history.append(self._copy_state())
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]

        return self.state

    def _neural_step(self, ext_A: float, ext_B: float, ext_C: float, dt: float):
        """Update using neural coupling dynamics"""
        # Convert to tensors
        osc_state = torch.tensor(
            self.state.to_6d_vector(),
            dtype=torch.float32
        ).unsqueeze(0).to(self.device)

        external = torch.tensor(
            [ext_A, ext_B, ext_C],
            dtype=torch.float32
        ).unsqueeze(0).to(self.device)

        # Compute update
        with torch.no_grad():
            delta = self.coupling_dynamics(osc_state, external)
            delta = delta.squeeze(0).cpu().numpy()

        # Apply update
        self.state.A.amplitude = np.clip(
            self.amplitude_decay * self.state.A.amplitude + dt * delta[0] + ext_A * 0.3,
            0.0, 1.0
        )
        self.state.B.amplitude = np.clip(
            self.amplitude_decay * self.state.B.amplitude + dt * delta[2] + ext_B * 0.3,
            0.0, 1.0
        )
        self.state.C.amplitude = np.clip(
            self.amplitude_decay * self.state.C.amplitude + dt * delta[4] + ext_C * 0.3,
            0.0, 1.0
        )

        # Phase updates
        self.state.A.phase = (self.state.A.phase + dt * (self.state.A.frequency + delta[1])) % (2 * np.pi)
        self.state.B.phase = (self.state.B.phase + dt * (self.state.B.frequency + delta[3])) % (2 * np.pi)
        self.state.C.phase = (self.state.C.phase + dt * (self.state.C.frequency + delta[5])) % (2 * np.pi)

    def _kuramoto_step(self, ext_A: float, ext_B: float, ext_C: float, dt: float):
        """
        Update using Kuramoto-style coupling

        Phase dynamics: d(theta_i)/dt = omega_i + K * sum_j(A_j * sin(theta_j - theta_i))
        Amplitude dynamics: d(A_i)/dt = -decay * A_i + external_i + coupling_from_others
        """
        K = self.coupling_strength

        # Get current phases
        theta_A, theta_B, theta_C = self.state.A.phase, self.state.B.phase, self.state.C.phase
        amp_A, amp_B, amp_C = self.state.A.amplitude, self.state.B.amplitude, self.state.C.amplitude

        # Phase coupling (Kuramoto)
        dtheta_A = self.state.A.frequency + K * (
            amp_B * np.sin(theta_B - theta_A) +
            amp_C * np.sin(theta_C - theta_A)
        )
        dtheta_B = self.state.B.frequency + K * (
            amp_A * np.sin(theta_A - theta_B) +
            amp_C * np.sin(theta_C - theta_B)
        )
        dtheta_C = self.state.C.frequency + K * (
            amp_A * np.sin(theta_A - theta_C) +
            amp_B * np.sin(theta_B - theta_C)
        )

        # Amplitude competition (winner-take-all tendency)
        total_ext = ext_A + ext_B + ext_C + 1e-6
        norm_A, norm_B, norm_C = ext_A / total_ext, ext_B / total_ext, ext_C / total_ext

        # Update amplitudes
        self.state.A.amplitude = np.clip(
            self.amplitude_decay * amp_A + 0.3 * ext_A + 0.1 * norm_A,
            0.0, 1.0
        )
        self.state.B.amplitude = np.clip(
            self.amplitude_decay * amp_B + 0.3 * ext_B + 0.1 * norm_B,
            0.0, 1.0
        )
        self.state.C.amplitude = np.clip(
            self.amplitude_decay * amp_C + 0.3 * ext_C + 0.1 * norm_C,
            0.0, 1.0
        )

        # Update phases
        self.state.A.phase = (theta_A + dt * dtheta_A) % (2 * np.pi)
        self.state.B.phase = (theta_B + dt * dtheta_B) % (2 * np.pi)
        self.state.C.phase = (theta_C + dt * dtheta_C) % (2 * np.pi)

    def _expert_phase_step(
        self,
        ext_A: float,
        ext_B: float,
        ext_C: float,
        events: np.ndarray,           # [5] event flags/strengths
        expert_E: np.ndarray,         # [5] expert activations
        event_proj: np.ndarray,       # [5, 3] event -> channel projection
        W: np.ndarray,                # [5, 3] expert -> channel coupling
        lambda_scale: float,
        dt: float
    ):
        """
        Update phases using expert dynamics equation (Phase 4)

        Implements: φH[t+1] = φH[t] - λ * (ω ⊙ δ + W^T @ E)

        This extends the Kuramoto dynamics with:
        - Event-triggered phase changes (δ)
        - Expert coupling pressure (W^T @ E)
        - Hierarchical time scaling (λ)

        Args:
            ext_A, ext_B, ext_C: External activations for amplitude update
            events: [5] event strengths (error, goal, loop, novelty, timeout)
            expert_E: [5] expert activations (EXPLOIT, EXPLORE, REPAIR, TRANSITION, DEADLOCK)
            event_proj: [5, 3] learnable projection from events to channels
            W: [5, 3] learnable coupling matrix from experts to channels
            lambda_scale: Hierarchical time constant
            dt: Time step
        """
        # Current frequencies and amplitudes
        omega = np.array([
            self.state.A.frequency,
            self.state.B.frequency,
            self.state.C.frequency
        ])
        amp = np.array([
            self.state.A.amplitude,
            self.state.B.amplitude,
            self.state.C.amplitude
        ])

        # Project 5 events to 3 channels: event_proj^T @ events
        # [3, 5] @ [5] = [3]
        delta_channel = event_proj.T @ events

        # Frequency-weighted action potential: ω * amplitude
        omega_qf = omega * amp

        # Expert coupling: W^T @ E
        # [3, 5] @ [5] = [3]
        coupling = W.T @ expert_E

        # THE EQUATION: Δφ = -λ * (ω_qf ⊙ δ + coupling)
        delta_phi = -lambda_scale * (omega_qf * delta_channel + coupling)

        # Apply phase update
        self.state.A.phase = (self.state.A.phase + dt * delta_phi[0]) % (2 * np.pi)
        self.state.B.phase = (self.state.B.phase + dt * delta_phi[1]) % (2 * np.pi)
        self.state.C.phase = (self.state.C.phase + dt * delta_phi[2]) % (2 * np.pi)

        # Update amplitudes using same competition dynamics
        total_ext = ext_A + ext_B + ext_C + 1e-6
        norm_A, norm_B, norm_C = ext_A / total_ext, ext_B / total_ext, ext_C / total_ext

        self.state.A.amplitude = np.clip(
            self.amplitude_decay * amp[0] + 0.3 * ext_A + 0.1 * norm_A, 0.0, 1.0
        )
        self.state.B.amplitude = np.clip(
            self.amplitude_decay * amp[1] + 0.3 * ext_B + 0.1 * norm_B, 0.0, 1.0
        )
        self.state.C.amplitude = np.clip(
            self.amplitude_decay * amp[2] + 0.3 * ext_C + 0.1 * norm_C, 0.0, 1.0
        )

    def step_with_experts(
        self,
        external_input: Dict[str, float],
        events: np.ndarray,
        expert_E: np.ndarray,
        event_proj: np.ndarray,
        W: np.ndarray,
        lambda_scale: float = 0.1,
        dt: float = 0.1
    ) -> 'TripleOscillatorState':
        """
        Step oscillator with expert phase dynamics

        Convenience method that combines external input with expert dynamics.

        Args:
            external_input: Dict with 'advance', 'explore', 'correct' activations
            events: [5] event strengths
            expert_E: [5] expert activations
            event_proj: [5, 3] event projection matrix
            W: [5, 3] coupling matrix
            lambda_scale: Hierarchical λ
            dt: Time step

        Returns:
            Updated oscillator state
        """
        ext_A = external_input.get('advance', 0.0)
        ext_B = external_input.get('explore', 0.0)
        ext_C = external_input.get('correct', 0.0)

        self._expert_phase_step(
            ext_A, ext_B, ext_C,
            events, expert_E,
            event_proj, W,
            lambda_scale, dt
        )

        # Record history
        self.state_history.append(self._copy_state())
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)

        self.state.beat_index += 1
        return self.state

    def _copy_state(self) -> TripleOscillatorState:
        """Create a copy of current state"""
        return TripleOscillatorState(
            A=OscillatorState(
                channel=Channel.ADVANCE,
                amplitude=self.state.A.amplitude,
                phase=self.state.A.phase,
                frequency=self.state.A.frequency
            ),
            B=OscillatorState(
                channel=Channel.EXPLORE,
                amplitude=self.state.B.amplitude,
                phase=self.state.B.phase,
                frequency=self.state.B.frequency
            ),
            C=OscillatorState(
                channel=Channel.CORRECT,
                amplitude=self.state.C.amplitude,
                phase=self.state.C.phase,
                frequency=self.state.C.frequency
            ),
            beat_index=self.state.beat_index
        )

    def get_state(self) -> TripleOscillatorState:
        """Get current oscillator state"""
        return self.state

    def reset(self):
        """Reset to initial state"""
        self.state = TripleOscillatorState(
            A=OscillatorState(channel=Channel.ADVANCE, amplitude=0.5, phase=0.0),
            B=OscillatorState(channel=Channel.EXPLORE, amplitude=0.5, phase=2*np.pi/3),
            C=OscillatorState(channel=Channel.CORRECT, amplitude=0.5, phase=4*np.pi/3)
        )
        self.state_history.clear()

    def from_tonic_phasic(
        self,
        tonic_phasic_vector: Dict[str, float],
        tool_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """
        Convert Tonic+Phasic tool activations to oscillator inputs

        Maps tools to channels based on their semantic role:
        - Advance tools: deployment, create, start, apply
        - Explore tools: list, search, query, explore
        - Correct tools: fix, repair, validate, rollback, retry

        Args:
            tonic_phasic_vector: Dict of tool -> activation
            tool_mapping: Optional override for tool -> channel mapping

        Returns:
            Dict with 'advance', 'explore', 'correct' activations
        """
        # Default semantic mapping
        advance_keywords = ['deploy', 'create', 'start', 'apply', 'run', 'execute', 'build', 'install']
        explore_keywords = ['list', 'search', 'query', 'find', 'explore', 'scan', 'discover', 'get', 'read']
        correct_keywords = ['fix', 'repair', 'validate', 'rollback', 'retry', 'check', 'verify', 'test', 'debug']

        advance_sum = 0.0
        explore_sum = 0.0
        correct_sum = 0.0

        for tool, activation in tonic_phasic_vector.items():
            tool_lower = tool.lower()

            # Check custom mapping first
            if tool_mapping and tool in tool_mapping:
                channel = tool_mapping[tool]
                if channel == 'advance':
                    advance_sum += activation
                elif channel == 'explore':
                    explore_sum += activation
                elif channel == 'correct':
                    correct_sum += activation
                continue

            # Semantic keyword matching
            matched = False
            for kw in advance_keywords:
                if kw in tool_lower:
                    advance_sum += activation
                    matched = True
                    break

            if not matched:
                for kw in explore_keywords:
                    if kw in tool_lower:
                        explore_sum += activation
                        matched = True
                        break

            if not matched:
                for kw in correct_keywords:
                    if kw in tool_lower:
                        correct_sum += activation
                        matched = True
                        break

            if not matched:
                # Default: split evenly
                advance_sum += activation / 3
                explore_sum += activation / 3
                correct_sum += activation / 3

        # Normalize to [0, 1]
        max_val = max(advance_sum, explore_sum, correct_sum, 1.0)

        return {
            'advance': min(advance_sum / max_val, 1.0),
            'explore': min(explore_sum / max_val, 1.0),
            'correct': min(correct_sum / max_val, 1.0)
        }

    def get_statistics(self) -> Dict:
        """Get oscillator statistics"""
        return {
            'current_state': self.state.to_dict(),
            'beat_index': self.state.beat_index,
            'dominant_channel': self.state.dominant_channel().value,
            'history_length': len(self.state_history),
            'coupling_strength': self.coupling_strength,
            'amplitude_decay': self.amplitude_decay,
            'use_neural_coupling': self.use_neural_coupling
        }


if __name__ == "__main__":
    print("=" * 70)
    print("ACTION POTENTIAL OSCILLATOR - 3 Coupled Oscillators")
    print("=" * 70)
    print()
    print("Channels:")
    print("  A = Advance (Exploit)  - Move toward goal")
    print("  B = Explore (Branch)   - Try alternatives")
    print("  C = Correct (Stabilize)- Repair/validate/retry")
    print()

    # Create oscillator system
    osc = ActionPotentialOscillator(
        natural_frequencies=(1.0, 1.2, 0.8),
        coupling_strength=0.5,
        use_neural_coupling=False  # Use Kuramoto for testing
    )

    print("Initial state:")
    state = osc.get_state()
    print(f"  A: amp={state.A.amplitude:.3f}, phase={state.A.phase:.3f}")
    print(f"  B: amp={state.B.amplitude:.3f}, phase={state.B.phase:.3f}")
    print(f"  C: amp={state.C.amplitude:.3f}, phase={state.C.phase:.3f}")
    print(f"  Dominant: {state.dominant_channel().value}")
    print()

    # Simulate with different inputs
    print("Simulating with varying inputs:")
    print("-" * 70)

    scenarios = [
        {'advance': 0.8, 'explore': 0.1, 'correct': 0.1},  # Exploit mode
        {'advance': 0.2, 'explore': 0.7, 'correct': 0.1},  # Explore mode
        {'advance': 0.1, 'explore': 0.1, 'correct': 0.8},  # Correct mode
        {'advance': 0.4, 'explore': 0.4, 'correct': 0.2},  # Balanced
    ]

    for i, scenario in enumerate(scenarios):
        print(f"\nScenario {i+1}: {scenario}")

        # Run several steps
        for _ in range(5):
            state = osc.step(external_input=scenario)

        print(f"  After 5 steps:")
        print(f"    A: amp={state.A.amplitude:.3f}, phase={state.A.phase:.3f}")
        print(f"    B: amp={state.B.amplitude:.3f}, phase={state.B.phase:.3f}")
        print(f"    C: amp={state.C.amplitude:.3f}, phase={state.C.phase:.3f}")
        print(f"    Dominant: {state.dominant_channel().value}")
        print(f"    Phase diffs: {state.phase_differences}")

    print()
    print("=" * 70)
    print("Test from Tonic+Phasic mapping:")
    print("-" * 70)

    tonic_phasic = {
        'docker_run': 0.8,
        'docker_ps': 0.4,
        'kubectl_apply': 0.7,
        'file_read': 0.3,
        'validate_config': 0.5
    }

    channel_input = osc.from_tonic_phasic(tonic_phasic)
    print(f"Input tools: {list(tonic_phasic.keys())}")
    print(f"Mapped to channels: {channel_input}")

    print()
    print("Statistics:", osc.get_statistics())
    print()
    print("=" * 70)
