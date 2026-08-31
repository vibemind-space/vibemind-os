"""
Basal Ganglia - Action Selection through Go/NoGo Competition

Implements a biologically-inspired Basal Ganglia (BG) system for:
- Action selection through Go/NoGo pathway competition
- Dopamine-modulated reinforcement learning
- Integration with oscillator and thalamic systems

Architecture:

    ActionPotentialOscillator (A/B/C channels)
               │
               ▼
    ┌─────────────────────────────────────────┐
    │          BASAL GANGLIA                   │
    │  ┌─────────────┐  ┌─────────────┐       │
    │  │ D1 MSNs(Go) │  │ D2 MSNs(NoGo)│       │
    │  └──────┬──────┘  └──────┬──────┘       │
    │         ▼                 ▼              │
    │   Direct Path      Indirect Path   STN  │
    │   (Go)             (NoGo)      Hyperdirect│
    │         └────────┬────────┘──────┘      │
    │                  ▼                       │
    │             GPi/SNr Output               │
    └─────────────────┬───────────────────────┘
                      ▼
            Thalamo-Hippocampal System

Channel-Action Mapping:
    - ADVANCE (A) → Action 0: Goal-directed execution (Go bias)
    - EXPLORE (B) → Action 1: Alternative seeking (balanced)
    - CORRECT (C) → Action 2: Validation/repair (NoGo bias)

Based on neuroscience research:
    - Go/NoGo pathways (Frank, 2005)
    - Dopamine modulation of D1/D2 MSNs (Gerfen & Surmeier, 2011)
    - Actor-Critic reinforcement learning (Joel et al., 2002)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class BGAction(Enum):
    """Basal ganglia action types mapped to oscillator channels"""
    ADVANCE = 0   # Go-biased: goal-directed execution
    EXPLORE = 1   # Balanced: alternative seeking
    CORRECT = 2   # NoGo-biased: validation/repair


@dataclass
class StriatumState:
    """
    State of striatal medium spiny neurons (MSNs)

    D1 MSNs express D1 dopamine receptors (Go pathway)
    D2 MSNs express D2 dopamine receptors (NoGo pathway)
    """
    d1_activity: np.ndarray  # [n_actions] D1 MSN firing rates
    d2_activity: np.ndarray  # [n_actions] D2 MSN firing rates
    dopamine: float = 0.5    # Current dopamine level

    @property
    def go_signal(self) -> np.ndarray:
        """Go signal strength per action"""
        return self.d1_activity

    @property
    def nogo_signal(self) -> np.ndarray:
        """NoGo signal strength per action"""
        return self.d2_activity

    @property
    def competition(self) -> np.ndarray:
        """Go - NoGo competition per action"""
        return self.d1_activity - self.d2_activity

    def to_dict(self) -> Dict:
        return {
            'd1_activity': self.d1_activity.tolist(),
            'd2_activity': self.d2_activity.tolist(),
            'dopamine': float(self.dopamine),
            'go_signal': self.go_signal.tolist(),
            'nogo_signal': self.nogo_signal.tolist(),
            'competition': self.competition.tolist()
        }


@dataclass
class BasalGangliaOutput:
    """
    Complete output of the Basal Ganglia system
    """
    # Action selection
    action_gates: np.ndarray      # [n_actions] softmax probabilities
    selected_action: int          # Winning action index
    selection_confidence: float   # Max gate value (confidence)

    # Pathway activities
    direct_output: np.ndarray     # Go pathway output
    indirect_output: np.ndarray   # NoGo pathway output
    hyperdirect_output: float     # Global inhibition from STN

    # Internal state
    striatum_state: StriatumState
    gpi_activity: np.ndarray      # GPi/SNr output nucleus activity

    # Learning-related
    eligibility_traces: np.ndarray  # For TD learning

    def to_dict(self) -> Dict:
        return {
            'action_gates': self.action_gates.tolist(),
            'selected_action': int(self.selected_action),
            'selection_confidence': float(self.selection_confidence),
            'action_name': BGAction(self.selected_action).name,
            'direct_output': self.direct_output.tolist(),
            'indirect_output': self.indirect_output.tolist(),
            'hyperdirect_output': float(self.hyperdirect_output),
            'gpi_activity': self.gpi_activity.tolist(),
            'striatum': self.striatum_state.to_dict()
        }


class Striatum:
    """
    Striatum with D1 and D2 MSN populations

    D1 MSNs: Enhanced by dopamine (Go pathway)
    D2 MSNs: Suppressed by dopamine (NoGo pathway)

    Mathematical model:
        D1_activity = σ(W_d1 @ input + DA * d1_gain)
        D2_activity = σ(W_d2 @ input - DA * d2_gain)
    """

    def __init__(
        self,
        n_inputs: int = 6,      # 6D oscillator state (3 channels x 2 components)
        n_actions: int = 3,      # ADVANCE, EXPLORE, CORRECT
        d1_gain: float = 1.0,    # Dopamine enhancement for D1
        d2_gain: float = 1.0,    # Dopamine suppression for D2
        baseline_activity: float = 0.2
    ):
        self.n_inputs = n_inputs
        self.n_actions = n_actions
        self.d1_gain = d1_gain
        self.d2_gain = d2_gain
        self.baseline = baseline_activity

        # Initialize weights with slight biases matching channel-action mapping
        # A -> ADVANCE (Go bias), B -> EXPLORE (balanced), C -> CORRECT (NoGo bias)
        self.W_d1 = np.random.randn(n_actions, n_inputs) * 0.1 + 0.1
        self.W_d2 = np.random.randn(n_actions, n_inputs) * 0.1 + 0.1

        # Set initial biases for channel-action mapping
        # Input layout: [A_real, A_imag, B_real, B_imag, C_real, C_imag]
        # Action 0 (ADVANCE): stronger D1 for channel A
        self.W_d1[0, 0:2] += 0.3   # A channel -> Go for ADVANCE
        # Action 1 (EXPLORE): balanced for channel B
        self.W_d1[1, 2:4] += 0.15  # B channel -> moderate Go for EXPLORE
        self.W_d2[1, 2:4] += 0.15  # B channel -> moderate NoGo for EXPLORE
        # Action 2 (CORRECT): stronger D2 for channel C
        self.W_d2[2, 4:6] += 0.3   # C channel -> NoGo for CORRECT

    def forward(
        self,
        cortical_input: np.ndarray,
        dopamine: float = 0.5
    ) -> StriatumState:
        """
        Compute striatal MSN activities

        Args:
            cortical_input: [n_inputs] from oscillator (6D vector)
            dopamine: Current dopamine level [0, 1]

        Returns:
            StriatumState with D1 and D2 activities
        """
        # Normalize dopamine deviation from baseline (0.5)
        da_deviation = dopamine - 0.5

        # D1 MSN activity: enhanced by dopamine
        d1_input = self.W_d1 @ cortical_input + da_deviation * self.d1_gain
        d1_activity = self._sigmoid(d1_input + self.baseline)

        # D2 MSN activity: suppressed by dopamine
        d2_input = self.W_d2 @ cortical_input - da_deviation * self.d2_gain
        d2_activity = self._sigmoid(d2_input + self.baseline)

        return StriatumState(
            d1_activity=d1_activity,
            d2_activity=d2_activity,
            dopamine=dopamine
        )

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        """Sigmoid activation with numerical stability"""
        return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))

    def update_weights(
        self,
        td_error: float,
        eligibility_d1: np.ndarray,
        eligibility_d2: np.ndarray,
        learning_rate: float = 0.01
    ):
        """
        Update striatal weights based on TD error

        Positive TD error strengthens active D1 synapses (Go learning)
        Negative TD error strengthens active D2 synapses (NoGo learning)
        """
        # Go learning: positive TD error -> strengthen D1
        self.W_d1 += learning_rate * td_error * eligibility_d1

        # NoGo learning: negative TD error -> strengthen D2
        # (implemented as positive TD weakening D2)
        self.W_d2 -= learning_rate * td_error * eligibility_d2

        # Weight normalization to prevent unbounded growth
        self.W_d1 = np.clip(self.W_d1, -2.0, 2.0)
        self.W_d2 = np.clip(self.W_d2, -2.0, 2.0)


class DirectPathway:
    """
    Direct (Go) Pathway: Striatum D1 → GPi/SNr

    Disinhibits thalamus by inhibiting GPi
    Promotes action execution
    """

    def __init__(self, n_actions: int = 3):
        self.n_actions = n_actions
        # Direct pathway weights (inhibitory connection to GPi)
        self.W_go = np.eye(n_actions) * 0.8 + np.random.randn(n_actions, n_actions) * 0.05

    def forward(self, d1_activity: np.ndarray) -> np.ndarray:
        """
        Compute direct pathway output (Go signal)

        Args:
            d1_activity: [n_actions] D1 MSN activity

        Returns:
            [n_actions] Go signal strength
        """
        return self.W_go @ d1_activity

    def update_weights(self, td_error: float, eligibility: np.ndarray, lr: float = 0.01):
        """Update Go pathway weights based on TD error"""
        # Positive TD error strengthens Go pathway
        self.W_go += lr * td_error * eligibility
        self.W_go = np.clip(self.W_go, 0.0, 2.0)


class IndirectPathway:
    """
    Indirect (NoGo) Pathway: Striatum D2 → GPe → STN → GPi

    Increases GPi activity by disinhibiting STN
    Suppresses action execution

    Simplified as: D2 → STN → GPi
    """

    def __init__(self, n_actions: int = 3, stn_baseline: float = 0.3):
        self.n_actions = n_actions
        self.stn_baseline = stn_baseline

        # D2 -> GPe (inhibitory)
        self.W_d2_gpe = np.eye(n_actions) * 0.6

        # GPe -> STN (inhibitory, so we model D2 as disinhibiting STN)
        # Simplified: higher D2 -> higher STN via disinhibition
        self.W_stn = np.eye(n_actions) * 0.7 + np.random.randn(n_actions, n_actions) * 0.05

    def forward(self, d2_activity: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute indirect pathway output (NoGo signal)

        Args:
            d2_activity: [n_actions] D2 MSN activity

        Returns:
            stn_activity: [n_actions] STN activity
            nogo_signal: [n_actions] NoGo signal strength to GPi
        """
        # D2 activity disinhibits STN through GPe
        gpe_inhibition = self.W_d2_gpe @ d2_activity
        stn_activity = self.stn_baseline + (1 - gpe_inhibition) * 0.5

        # STN excites GPi
        nogo_signal = self.W_stn @ stn_activity

        return stn_activity, nogo_signal

    def update_weights(self, td_error: float, eligibility: np.ndarray, lr: float = 0.01):
        """Update NoGo pathway weights based on TD error"""
        # Negative TD error strengthens NoGo pathway
        self.W_stn -= lr * td_error * eligibility
        self.W_stn = np.clip(self.W_stn, 0.0, 2.0)


class HyperdirectPathway:
    """
    Hyperdirect Pathway: Cortex → STN → GPi

    Provides rapid global inhibition
    Used for stopping ongoing actions and urgency modulation
    """

    def __init__(
        self,
        n_inputs: int = 6,
        n_actions: int = 3,
        baseline_inhibition: float = 0.1
    ):
        self.n_inputs = n_inputs
        self.n_actions = n_actions
        self.baseline = baseline_inhibition

        # Cortical input to STN
        self.W_cortex_stn = np.random.randn(n_inputs) * 0.1 + 0.1

    def forward(
        self,
        cortical_input: np.ndarray,
        urgency: float = 0.5
    ) -> float:
        """
        Compute hyperdirect pathway output (global inhibition)

        Args:
            cortical_input: [n_inputs] cortical activity
            urgency: Urgency signal [0, 1] (from norepinephrine)

        Returns:
            Global inhibition strength (scalar broadcast to all actions)
        """
        # Cortical drive to STN
        cortical_drive = np.dot(self.W_cortex_stn, cortical_input)

        # Urgency modulates hyperdirect strength
        # High urgency -> stronger global inhibition (prevents hasty decisions)
        hyperdirect_output = self.baseline + cortical_drive * (0.5 + urgency * 0.5)

        return float(np.clip(hyperdirect_output, 0.0, 1.0))


class GPiSNr:
    """
    Globus Pallidus internal / Substantia Nigra pars reticulata

    Output nucleus of basal ganglia
    Tonically active, inhibits thalamus

    Go pathway inhibits GPi (disinhibits thalamus)
    NoGo pathway excites GPi (maintains inhibition)
    """

    def __init__(
        self,
        n_actions: int = 3,
        tonic_activity: float = 0.8,
        temperature: float = 0.5
    ):
        self.n_actions = n_actions
        self.tonic = tonic_activity
        self.temperature = temperature

    def forward(
        self,
        go_signal: np.ndarray,
        nogo_signal: np.ndarray,
        hyperdirect: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute GPi output and action gates

        GPi = tonic - Go + NoGo + Hyperdirect
        action_gates = softmax(-GPi / τ)

        Args:
            go_signal: [n_actions] from direct pathway
            nogo_signal: [n_actions] from indirect pathway
            hyperdirect: Scalar global inhibition

        Returns:
            gpi_activity: [n_actions] GPi firing rates
            action_gates: [n_actions] probability of each action
        """
        # GPi activity: tonic inhibition modulated by pathways
        gpi_activity = (
            self.tonic
            - go_signal         # Direct pathway inhibits GPi
            + nogo_signal       # Indirect pathway excites GPi
            + hyperdirect       # Hyperdirect adds global inhibition
        )

        # Clip to valid range
        gpi_activity = np.clip(gpi_activity, 0.0, 2.0)

        # Action gates: inverse of GPi (low GPi = high gate)
        # Using softmax for normalization
        action_gates = self._softmax(-gpi_activity / self.temperature)

        return gpi_activity, action_gates

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Numerically stable softmax"""
        exp_x = np.exp(x - np.max(x))
        return exp_x / (exp_x.sum() + 1e-8)


class BasalGanglia:
    """
    Complete Basal Ganglia system for action selection

    Integrates:
    - Striatum (D1/D2 MSNs)
    - Direct pathway (Go)
    - Indirect pathway (NoGo)
    - Hyperdirect pathway (global inhibition)
    - GPi/SNr output nucleus
    - TD-based learning

    Usage:
        bg = BasalGanglia()

        # Get oscillator state from ActionPotentialOscillator
        osc_input = oscillator.state.to_6d_vector()

        # Get neuromodulator levels
        dopamine = neuromod.levels.dopamine
        urgency = neuromod.levels.norepinephrine

        # Step BG
        output = bg.step(osc_input, dopamine, urgency)

        # Learn from TD error
        td_error = neuromod.reward_prediction_errors[-1]
        bg.update_weights(td_error, output.selected_action)
    """

    def __init__(
        self,
        n_inputs: int = 6,
        n_actions: int = 3,
        temperature: float = 0.5,
        learning_rate: float = 0.01,
        eligibility_decay: float = 0.9
    ):
        """
        Initialize Basal Ganglia system

        Args:
            n_inputs: Input dimension (6 for oscillator 6D vector)
            n_actions: Number of actions (3: ADVANCE, EXPLORE, CORRECT)
            temperature: Softmax temperature for action selection
            learning_rate: TD learning rate
            eligibility_decay: Decay rate for eligibility traces
        """
        self.n_inputs = n_inputs
        self.n_actions = n_actions
        self.learning_rate = learning_rate
        self.eligibility_decay = eligibility_decay

        # Initialize components
        self.striatum = Striatum(n_inputs=n_inputs, n_actions=n_actions)
        self.direct = DirectPathway(n_actions=n_actions)
        self.indirect = IndirectPathway(n_actions=n_actions)
        self.hyperdirect = HyperdirectPathway(n_inputs=n_inputs, n_actions=n_actions)
        self.gpi = GPiSNr(n_actions=n_actions, temperature=temperature)

        # Eligibility traces for TD learning
        self.eligibility_d1 = np.zeros((n_actions, n_inputs))
        self.eligibility_d2 = np.zeros((n_actions, n_inputs))
        self.eligibility_go = np.zeros((n_actions, n_actions))
        self.eligibility_nogo = np.zeros((n_actions, n_actions))

        # History tracking
        self.output_history: List[BasalGangliaOutput] = []
        self.action_history: List[int] = []
        self.max_history = 100

        # Statistics
        self.total_steps = 0
        self.action_counts = np.zeros(n_actions)

    def step(
        self,
        cortical_input: np.ndarray,
        dopamine: float = 0.5,
        urgency: float = 0.5
    ) -> BasalGangliaOutput:
        """
        Process cortical input through basal ganglia

        Args:
            cortical_input: [n_inputs] from oscillator (6D vector)
            dopamine: Current dopamine level [0, 1]
            urgency: Urgency/arousal signal [0, 1] (norepinephrine)

        Returns:
            BasalGangliaOutput with action gates and internal state
        """
        # Ensure input is numpy array
        cortical_input = np.asarray(cortical_input, dtype=np.float32)

        # 1. Striatum: compute D1/D2 MSN activity
        striatum_state = self.striatum.forward(cortical_input, dopamine)

        # 2. Direct pathway (Go)
        go_signal = self.direct.forward(striatum_state.d1_activity)

        # 3. Indirect pathway (NoGo)
        stn_activity, nogo_signal = self.indirect.forward(striatum_state.d2_activity)

        # 4. Hyperdirect pathway
        hyperdirect_output = self.hyperdirect.forward(cortical_input, urgency)

        # 5. GPi output and action gates
        gpi_activity, action_gates = self.gpi.forward(
            go_signal, nogo_signal, hyperdirect_output
        )

        # 6. Select action (highest gate)
        selected_action = int(np.argmax(action_gates))
        selection_confidence = float(action_gates[selected_action])

        # 7. Update eligibility traces
        self._update_eligibility(cortical_input, striatum_state, selected_action)

        # Create output
        output = BasalGangliaOutput(
            action_gates=action_gates,
            selected_action=selected_action,
            selection_confidence=selection_confidence,
            direct_output=go_signal,
            indirect_output=nogo_signal,
            hyperdirect_output=hyperdirect_output,
            striatum_state=striatum_state,
            gpi_activity=gpi_activity,
            eligibility_traces=self.eligibility_d1.copy()
        )

        # Update history
        self.output_history.append(output)
        if len(self.output_history) > self.max_history:
            self.output_history.pop(0)

        self.action_history.append(selected_action)
        if len(self.action_history) > self.max_history:
            self.action_history.pop(0)

        # Update statistics
        self.total_steps += 1
        self.action_counts[selected_action] += 1

        return output

    def _update_eligibility(
        self,
        cortical_input: np.ndarray,
        striatum_state: StriatumState,
        selected_action: int
    ):
        """
        Update eligibility traces for TD learning

        Traces decay over time and are boosted by current activity
        """
        # Decay existing traces
        self.eligibility_d1 *= self.eligibility_decay
        self.eligibility_d2 *= self.eligibility_decay
        self.eligibility_go *= self.eligibility_decay
        self.eligibility_nogo *= self.eligibility_decay

        # Boost traces for selected action
        # Outer product creates trace matrix: which input contributed to which action
        action_mask = np.zeros(self.n_actions)
        action_mask[selected_action] = 1.0

        # D1/D2 eligibility: input × action
        self.eligibility_d1 += np.outer(action_mask, cortical_input) * striatum_state.d1_activity[selected_action]
        self.eligibility_d2 += np.outer(action_mask, cortical_input) * striatum_state.d2_activity[selected_action]

        # Pathway eligibility
        self.eligibility_go += np.outer(action_mask, striatum_state.d1_activity)
        self.eligibility_nogo += np.outer(action_mask, striatum_state.d2_activity)

    def update_weights(self, td_error: float, action_taken: Optional[int] = None):
        """
        Update all weights based on TD error

        Implements actor-critic learning:
        - Positive TD error: strengthen Go pathway (action was better than expected)
        - Negative TD error: strengthen NoGo pathway (action was worse than expected)

        Args:
            td_error: Temporal difference error from reward prediction
            action_taken: Action to credit (uses last action if None)
        """
        if action_taken is None and self.action_history:
            action_taken = self.action_history[-1]

        # Update striatum weights
        self.striatum.update_weights(
            td_error,
            self.eligibility_d1,
            self.eligibility_d2,
            self.learning_rate
        )

        # Update pathway weights
        self.direct.update_weights(td_error, self.eligibility_go, self.learning_rate)
        self.indirect.update_weights(td_error, self.eligibility_nogo, self.learning_rate)

    def modulate_oscillator(self, bg_output: BasalGangliaOutput) -> Dict[str, float]:
        """
        Convert BG output to oscillator modulation

        Args:
            bg_output: Output from step()

        Returns:
            Dict with 'advance', 'explore', 'correct' modulation factors
        """
        gates = bg_output.action_gates

        return {
            'advance': float(gates[0]),
            'explore': float(gates[1]),
            'correct': float(gates[2])
        }

    def modulate_thalamic_gates(
        self,
        thalamic_gates: np.ndarray,
        bg_output: BasalGangliaOutput,
        modulation_strength: float = 0.3
    ) -> np.ndarray:
        """
        Apply BG modulation to thalamic gates

        Args:
            thalamic_gates: [n_modalities] current thalamic gate values
            bg_output: Output from step()
            modulation_strength: How strongly BG influences thalamus

        Returns:
            Modified thalamic gates (still sums to 1)
        """
        # Map BG action gates to thalamic modalities
        # This is a simplified mapping; could be learned
        n_modalities = len(thalamic_gates)

        # Create modulation vector based on BG action
        bg_modulation = np.zeros(n_modalities)

        # ADVANCE boosts action-oriented modalities (first third)
        # EXPLORE boosts exploration modalities (middle third)
        # CORRECT boosts validation modalities (last third)
        third = n_modalities // 3

        bg_modulation[:third] += bg_output.action_gates[0]
        bg_modulation[third:2*third] += bg_output.action_gates[1]
        bg_modulation[2*third:] += bg_output.action_gates[2]

        # Normalize modulation
        bg_modulation = bg_modulation / (bg_modulation.sum() + 1e-8)

        # Blend with original gates
        modulated = (1 - modulation_strength) * thalamic_gates + modulation_strength * bg_modulation

        # Ensure sum to 1
        return modulated / (modulated.sum() + 1e-8)

    def get_action_name(self, action_idx: int) -> str:
        """Get human-readable action name"""
        return BGAction(action_idx).name

    def get_state_description(self, bg_output: Optional[BasalGangliaOutput] = None) -> str:
        """Get human-readable description of BG state"""
        if bg_output is None and self.output_history:
            bg_output = self.output_history[-1]

        if bg_output is None:
            return "No BG output available"

        action_name = self.get_action_name(bg_output.selected_action)
        conf = bg_output.selection_confidence
        da = bg_output.striatum_state.dopamine

        # Describe Go/NoGo balance
        comp = bg_output.striatum_state.competition
        if np.mean(comp) > 0.2:
            balance = "Go-dominant"
        elif np.mean(comp) < -0.2:
            balance = "NoGo-dominant"
        else:
            balance = "Balanced"

        return (
            f"BG: {action_name} (conf={conf:.2f}) | "
            f"DA={da:.2f} | {balance} | "
            f"Gates=[{bg_output.action_gates[0]:.2f}, "
            f"{bg_output.action_gates[1]:.2f}, "
            f"{bg_output.action_gates[2]:.2f}]"
        )

    def get_statistics(self) -> Dict:
        """Get BG statistics"""
        action_probs = self.action_counts / (self.total_steps + 1e-8)

        recent_actions = self.action_history[-20:] if self.action_history else []
        if recent_actions:
            recent_counts = np.bincount(recent_actions, minlength=self.n_actions)
            recent_probs = recent_counts / len(recent_actions)
        else:
            recent_probs = np.ones(self.n_actions) / self.n_actions

        return {
            'total_steps': self.total_steps,
            'action_counts': self.action_counts.tolist(),
            'action_probabilities': action_probs.tolist(),
            'recent_action_probs': recent_probs.tolist(),
            'learning_rate': self.learning_rate,
            'n_actions': self.n_actions,
            'eligibility_decay': self.eligibility_decay
        }

    def reset(self):
        """Reset BG state"""
        self.eligibility_d1 = np.zeros((self.n_actions, self.n_inputs))
        self.eligibility_d2 = np.zeros((self.n_actions, self.n_inputs))
        self.eligibility_go = np.zeros((self.n_actions, self.n_actions))
        self.eligibility_nogo = np.zeros((self.n_actions, self.n_actions))
        self.output_history.clear()
        self.action_history.clear()
        self.total_steps = 0
        self.action_counts = np.zeros(self.n_actions)

    def __repr__(self):
        if self.output_history:
            last = self.output_history[-1]
            return f"BasalGanglia(action={self.get_action_name(last.selected_action)}, conf={last.selection_confidence:.2f})"
        return f"BasalGanglia(n_actions={self.n_actions})"


# ============================================================================
# Convenience Functions for Integration
# ============================================================================

def create_bg_from_oscillator_state(
    oscillator_state,  # TripleOscillatorState
    neuromod_levels,   # NeuromodulatorLevels
    bg: BasalGanglia
) -> BasalGangliaOutput:
    """
    Convenience function to step BG from oscillator and neuromod states

    Args:
        oscillator_state: TripleOscillatorState from ActionPotentialOscillator
        neuromod_levels: NeuromodulatorLevels from NeuromodulationSystem
        bg: BasalGanglia instance

    Returns:
        BasalGangliaOutput
    """
    # Extract 6D vector from oscillator
    cortical_input = oscillator_state.to_6d_vector()

    # Extract neuromodulator levels
    dopamine = neuromod_levels.dopamine
    urgency = neuromod_levels.norepinephrine

    return bg.step(cortical_input, dopamine, urgency)


# ============================================================================
# Demo
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("BASAL GANGLIA - Action Selection through Go/NoGo Competition")
    print("=" * 70)
    print()
    print("Actions:")
    for action in BGAction:
        print(f"  {action.value}: {action.name}")
    print()

    # Create BG system
    bg = BasalGanglia()

    print("Testing BG with different inputs:")
    print("-" * 70)

    # Simulate different oscillator states
    test_inputs = [
        # High ADVANCE channel (should select ADVANCE)
        np.array([0.8, 0.2, 0.1, 0.1, 0.1, 0.1]),
        # High EXPLORE channel (should select EXPLORE)
        np.array([0.1, 0.1, 0.8, 0.2, 0.1, 0.1]),
        # High CORRECT channel (should select CORRECT)
        np.array([0.1, 0.1, 0.1, 0.1, 0.8, 0.2]),
        # Balanced (depends on dopamine)
        np.array([0.4, 0.3, 0.4, 0.3, 0.4, 0.3]),
    ]

    dopamine_levels = [0.3, 0.5, 0.7, 0.5]

    for i, (input_vec, da) in enumerate(zip(test_inputs, dopamine_levels)):
        print(f"\nTest {i+1}:")
        print(f"  Input: {input_vec}")
        print(f"  Dopamine: {da}")

        output = bg.step(input_vec, dopamine=da, urgency=0.5)

        print(f"  Action gates: {output.action_gates}")
        print(f"  Selected: {bg.get_action_name(output.selected_action)} (conf={output.selection_confidence:.3f})")
        print(f"  Go signal: {output.direct_output}")
        print(f"  NoGo signal: {output.indirect_output}")
        print(f"  State: {bg.get_state_description(output)}")

    print()
    print("-" * 70)
    print("Testing TD learning:")
    print("-" * 70)

    # Simulate learning from reward
    print("\nBefore learning (action counts):", bg.action_counts)

    # Positive TD error (action was good)
    bg.update_weights(td_error=0.5, action_taken=0)
    print("After positive TD error: weights updated to favor Go")

    # Negative TD error (action was bad)
    bg.update_weights(td_error=-0.3, action_taken=2)
    print("After negative TD error: weights updated to favor NoGo")

    print()
    print("Statistics:", bg.get_statistics())
    print()
    print("=" * 70)
