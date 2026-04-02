"""
Cortical Feedback Loops for Top-Down Attention and Executive Control

Implements bidirectional cortical feedback completing the cortico-thalamo-cortical
circuit in the ATM-R architecture.

Biological Inspiration:
- Layer 6 Corticothalamic Feedback: Modulates thalamic gain and selectivity
- Prefrontal Executive Control: Task-dependent attention allocation
- Top-down Expectation: Biases bottom-up sensory processing
- Attentional Suppression: TRN inhibition of irrelevant modalities

System Flow:
1. AttentionController computes attention weights from goal, oscillator, PE
2. FeedbackGenerator produces prior/TRN modulation signals
3. CorticalProcessor coordinates feedback generation
4. Thalamus applies feedback to modulate routing

Integration:
    from core.cortical_feedback import CorticalProcessor
    from core.action_potential_oscillator import ActionPotentialOscillator
    from core.neuromodulation import NeuromodulationSystem

    osc = ActionPotentialOscillator()
    neuromod = NeuromodulationSystem()
    cortex = CorticalProcessor(n_modalities=6, goal_dim=32, state_dim=128)

    # Generate feedback from thalamic output
    feedback = cortex.step(
        thalamic_output=thalamic_out,
        goal=goal_vector,
        oscillator_state=osc.state,
        neuromod_levels=neuromod.levels
    )
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels


def softmax(x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Numerically stable softmax."""
    x_scaled = x / temperature
    x_scaled = x_scaled - np.max(x_scaled)
    exp_x = np.exp(x_scaled)
    return exp_x / np.sum(exp_x)


def normalize(x: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    """Normalize to sum to 1."""
    total = np.sum(x) + eps
    return x / total


@dataclass
class CorticalState:
    """
    Current state of the cortical processor.

    Attributes:
        attention_weights: Per-modality attention weights [M]
        expectation: Expected input for each modality
        goal_context: Current task/goal encoding
        feedback_gain: Global feedback strength (arousal-modulated)
        prediction_errors: Most recent PEs per modality
    """
    attention_weights: np.ndarray
    expectation: Dict[str, np.ndarray] = field(default_factory=dict)
    goal_context: np.ndarray = field(default_factory=lambda: np.zeros(32))
    feedback_gain: float = 1.0
    prediction_errors: np.ndarray = field(default_factory=lambda: np.zeros(1))


@dataclass
class CorticalFeedback:
    """
    Feedback signals from cortex to thalamus.

    Attributes:
        prior_modulation: Delta to apply to thalamic priors [M]
        trn_modulation: Delta to apply to TRN inhibition matrix [M x M]
        gain_modulation: Multiplicative gain for thalamic activity
        attention_weights: Current attention distribution (for monitoring)
    """
    prior_modulation: np.ndarray
    trn_modulation: np.ndarray
    gain_modulation: float
    attention_weights: np.ndarray

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'prior_modulation': self.prior_modulation.tolist(),
            'trn_modulation': self.trn_modulation.tolist(),
            'gain_modulation': self.gain_modulation,
            'attention_weights': self.attention_weights.tolist()
        }


class AttentionController:
    """
    PFC-like executive attention control.

    Computes top-down attention weights based on:
    1. Goal-driven attention: What modalities are task-relevant?
    2. Oscillator-modulated attention: ADVANCE = focused, EXPLORE = broad
    3. PE-driven attention: Attend to surprising modalities

    Mathematical Model:
        a_goal = softmax(W_goal @ goal)
        a_osc = sigmoid(W_osc @ osc_6d)
        a_pe = softmax(PE / tau_pe)
        attention = normalize(alpha * a_goal + beta * a_osc + gamma * a_pe)
    """

    def __init__(
        self,
        n_modalities: int,
        goal_dim: int = 32,
        hidden_dim: int = 64,
        # Blend weights for attention components
        alpha_goal: float = 0.4,    # Goal-driven weight
        beta_osc: float = 0.3,      # Oscillator-modulated weight
        gamma_pe: float = 0.3,      # PE-driven weight
        # Temperature for PE-based attention
        tau_pe: float = 0.5,
        # Learning rate for attention weights
        lr_attention: float = 0.01,
        seed: int = 42
    ):
        """
        Initialize attention controller.

        Args:
            n_modalities: Number of modalities to attend to
            goal_dim: Dimension of goal/task encoding
            hidden_dim: Hidden layer dimension (for future expansion)
            alpha_goal: Weight for goal-driven attention
            beta_osc: Weight for oscillator-modulated attention
            gamma_pe: Weight for PE-driven attention
            tau_pe: Temperature for PE softmax
            lr_attention: Learning rate for weight adaptation
            seed: Random seed
        """
        self.n_modalities = n_modalities
        self.goal_dim = goal_dim
        self.hidden_dim = hidden_dim
        self.alpha = alpha_goal
        self.beta = beta_osc
        self.gamma = gamma_pe
        self.tau_pe = tau_pe
        self.lr = lr_attention

        self.rng = np.random.default_rng(seed)

        # Goal to attention weights: goal_dim -> n_modalities
        # Initialize with small random weights
        self.W_goal = self.rng.normal(0, 0.1, (n_modalities, goal_dim))
        self.b_goal = np.zeros(n_modalities)

        # Oscillator to attention weights: 6D oscillator -> n_modalities
        # Initialize to spread attention when EXPLORE (high amplitude variance)
        self.W_osc = self.rng.normal(0, 0.1, (n_modalities, 6))
        self.b_osc = np.zeros(n_modalities)

        # Oscillator mode effects (learned biases)
        # ADVANCE (channel 0 dominant) -> focus on primary modality
        # EXPLORE (channel 1 dominant) -> broaden attention
        # CORRECT (channel 2 dominant) -> attend to error signals
        self.mode_biases = np.array([
            [1.0, 0.5, 0.3, 0.2, 0.1, 0.05],  # ADVANCE: focus on early modalities
            [0.3, 0.3, 0.3, 0.3, 0.3, 0.3],   # EXPLORE: uniform-ish
            [0.1, 0.1, 0.2, 0.3, 0.5, 1.0]    # CORRECT: focus on error signals
        ])[:, :n_modalities] if n_modalities <= 6 else np.ones((3, n_modalities)) / n_modalities

        # Statistics
        self.attention_history: List[np.ndarray] = []
        self.steps = 0

    def compute_attention(
        self,
        goal: np.ndarray,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        prediction_errors: Optional[np.ndarray] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None
    ) -> np.ndarray:
        """
        Compute top-down attention weights.

        Args:
            goal: Goal/task encoding vector [goal_dim]
            oscillator_state: Current oscillator state (for attention mode)
            prediction_errors: Per-modality prediction errors [M]
            neuromod_levels: Neuromodulator levels (for gain modulation)

        Returns:
            attention: Normalized attention weights [M]
        """
        # 1) Goal-driven attention
        if goal is not None and len(goal) == self.goal_dim:
            goal_logits = self.W_goal @ goal + self.b_goal
            a_goal = softmax(goal_logits)
        else:
            # No goal: uniform attention
            a_goal = np.ones(self.n_modalities) / self.n_modalities

        # 2) Oscillator-modulated attention
        if oscillator_state is not None:
            osc_6d = oscillator_state.to_6d_vector()
            osc_logits = self.W_osc @ osc_6d + self.b_osc

            # Determine dominant mode from oscillator
            dominant = oscillator_state.dominant_channel()
            if hasattr(dominant, 'value'):
                dominant = dominant.value
            if isinstance(dominant, int) and dominant < 3:
                mode_bias = self.mode_biases[dominant]
                if len(mode_bias) < self.n_modalities:
                    mode_bias = np.pad(mode_bias, (0, self.n_modalities - len(mode_bias)),
                                       constant_values=1.0/self.n_modalities)
                osc_logits = osc_logits + mode_bias

            a_osc = softmax(osc_logits)
        else:
            a_osc = np.ones(self.n_modalities) / self.n_modalities

        # 3) PE-driven attention (attend to surprising modalities)
        if prediction_errors is not None and len(prediction_errors) == self.n_modalities:
            # Higher PE = more attention
            a_pe = softmax(prediction_errors, temperature=self.tau_pe)
        else:
            a_pe = np.ones(self.n_modalities) / self.n_modalities

        # 4) Blend attention components
        # Adjust blend weights based on neuromodulation
        alpha, beta, gamma = self.alpha, self.beta, self.gamma
        if neuromod_levels is not None:
            # High dopamine: increase goal-driven attention
            alpha = self.alpha * (1 + 0.5 * (neuromod_levels.dopamine - 0.5))
            # High norepinephrine: increase PE-driven attention (alertness)
            gamma = self.gamma * (1 + 0.5 * (neuromod_levels.norepinephrine - 0.5))
            # Renormalize
            total = alpha + beta + gamma
            alpha, beta, gamma = alpha/total, beta/total, gamma/total

        attention = normalize(alpha * a_goal + beta * a_osc + gamma * a_pe)

        # Track history
        self.attention_history.append(attention.copy())
        if len(self.attention_history) > 100:
            self.attention_history.pop(0)
        self.steps += 1

        return attention

    def update_weights(
        self,
        attention: np.ndarray,
        reward: float,
        goal: np.ndarray,
        oscillator_state: Optional['TripleOscillatorState'] = None
    ):
        """
        Update attention weights based on reward.

        Learning rule: Increase weights that led to attended modalities
        when reward is positive, decrease when negative.

        Args:
            attention: Attention weights that were used
            reward: Reward signal (+1 for success, -1 for failure)
            goal: Goal that was used
            oscillator_state: Oscillator state that was used
        """
        if goal is not None and len(goal) == self.goal_dim:
            # Outer product: attention (what we attended) x goal (what predicted it)
            delta_W = self.lr * reward * np.outer(attention, goal)
            self.W_goal += delta_W

        if oscillator_state is not None:
            osc_6d = oscillator_state.to_6d_vector()
            delta_W = self.lr * reward * np.outer(attention, osc_6d)
            self.W_osc += delta_W

    def get_statistics(self) -> Dict:
        """Get attention controller statistics."""
        return {
            'steps': self.steps,
            'n_modalities': self.n_modalities,
            'blend_weights': {'alpha': self.alpha, 'beta': self.beta, 'gamma': self.gamma},
            'recent_attention_mean': np.mean(self.attention_history[-10:], axis=0).tolist()
                if self.attention_history else [],
            'attention_entropy': float(-np.sum(
                self.attention_history[-1] * np.log(self.attention_history[-1] + 1e-10)
            )) if self.attention_history else 0.0
        }


class FeedbackGenerator:
    """
    Layer 6-like feedback generator to thalamus.

    Generates modulation signals for:
    1. Prior modulation: Adjust thalamic priors based on attention
    2. TRN modulation: Adjust lateral inhibition to suppress unattended
    3. Gain modulation: Global arousal/responsiveness

    Mathematical Model:
        prior_delta[i] = attention[i] * (salience[i] - prior[i]) * lr_prior
        trn_delta[i,j] = -attention[i] * (1 - attention[j]) * lr_trn
    """

    def __init__(
        self,
        n_modalities: int,
        state_dim: int = 128,
        # Modulation strengths
        prior_strength: float = 0.1,
        trn_strength: float = 0.05,
        gain_baseline: float = 1.0,
        gain_scale: float = 0.3,
        # Learning rates
        lr_salience: float = 0.01,
        seed: int = 42
    ):
        """
        Initialize feedback generator.

        Args:
            n_modalities: Number of modalities
            state_dim: Total state dimension (for expectation learning)
            prior_strength: Strength of prior modulation
            trn_strength: Strength of TRN modulation
            gain_baseline: Baseline feedback gain
            gain_scale: Scale of gain modulation by arousal
            lr_salience: Learning rate for salience estimation
            seed: Random seed
        """
        self.n_modalities = n_modalities
        self.state_dim = state_dim
        self.prior_strength = prior_strength
        self.trn_strength = trn_strength
        self.gain_baseline = gain_baseline
        self.gain_scale = gain_scale
        self.lr_salience = lr_salience

        self.rng = np.random.default_rng(seed)

        # Expected salience per modality (learned)
        self.expected_salience = np.ones(n_modalities) * 0.5

        # Current priors (copied from thalamus for delta computation)
        self.current_priors = np.ones(n_modalities) * 0.5

        # Statistics
        self.feedback_history: List[CorticalFeedback] = []
        self.steps = 0

    def set_current_priors(self, priors: Dict[str, float], modality_order: List[str]):
        """Update current priors from thalamus."""
        self.current_priors = np.array([priors.get(m, 0.5) for m in modality_order])

    def generate_feedback(
        self,
        attention: np.ndarray,
        prediction_errors: Optional[np.ndarray] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None
    ) -> CorticalFeedback:
        """
        Generate feedback signals for thalamus.

        Args:
            attention: Current attention weights [M]
            prediction_errors: Per-modality PEs (for salience update)
            neuromod_levels: Neuromodulator levels (for gain)

        Returns:
            CorticalFeedback with prior/TRN/gain modulation
        """
        n = self.n_modalities

        # 1) Prior modulation
        # Increase prior for attended modalities, decrease for unattended
        prior_delta = np.zeros(n)
        for i in range(n):
            # Target: attention-weighted salience
            target = attention[i] * self.expected_salience[i]
            # Delta toward target
            prior_delta[i] = self.prior_strength * (target - self.current_priors[i])

        # 2) TRN modulation (lateral inhibition)
        # Suppress connections between attended and unattended modalities
        trn_delta = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i != j:
                    # If i is attended and j is not, increase inhibition i->j
                    # This suppresses unattended modalities
                    trn_delta[i, j] = -self.trn_strength * attention[i] * (1 - attention[j])

        # 3) Gain modulation (global arousal)
        gain = self.gain_baseline
        if neuromod_levels is not None:
            # Norepinephrine increases gain (arousal)
            gain += self.gain_scale * (neuromod_levels.norepinephrine - 0.5)
            # Serotonin provides stability (moderate gain increase)
            gain += self.gain_scale * 0.3 * (neuromod_levels.serotonin - 0.5)
        gain = np.clip(gain, 0.5, 2.0)

        # 4) Update salience estimates based on PE
        if prediction_errors is not None and len(prediction_errors) == n:
            # Modalities with high PE are salient
            self.expected_salience += self.lr_salience * (prediction_errors - self.expected_salience)
            self.expected_salience = np.clip(self.expected_salience, 0.1, 1.0)

        feedback = CorticalFeedback(
            prior_modulation=prior_delta,
            trn_modulation=trn_delta,
            gain_modulation=gain,
            attention_weights=attention.copy()
        )

        # Track history
        self.feedback_history.append(feedback)
        if len(self.feedback_history) > 50:
            self.feedback_history.pop(0)
        self.steps += 1

        return feedback

    def get_statistics(self) -> Dict:
        """Get feedback generator statistics."""
        return {
            'steps': self.steps,
            'expected_salience': self.expected_salience.tolist(),
            'current_priors': self.current_priors.tolist(),
            'gain_baseline': self.gain_baseline,
            'recent_gain': self.feedback_history[-1].gain_modulation
                if self.feedback_history else self.gain_baseline
        }


class ExpectationNetwork:
    """
    Network for learning input expectations per modality.

    Learns to predict typical inputs for each modality based on
    context and goal. Used for top-down expectation-based processing.
    """

    def __init__(
        self,
        modality_dims: Dict[str, int],
        context_dim: int = 32,
        lr: float = 0.01,
        seed: int = 42
    ):
        """
        Initialize expectation network.

        Args:
            modality_dims: Dict mapping modality name to dimension
            context_dim: Dimension of context/goal input
            lr: Learning rate
            seed: Random seed
        """
        self.modality_dims = modality_dims
        self.context_dim = context_dim
        self.lr = lr

        self.rng = np.random.default_rng(seed)

        # Per-modality expectation weights: context -> modality_dim
        self.W = {}
        self.b = {}
        for m, dim in modality_dims.items():
            self.W[m] = self.rng.normal(0, 0.1, (dim, context_dim))
            self.b[m] = np.zeros(dim)

        # Running mean for each modality (baseline expectation)
        self.running_mean = {m: np.zeros(dim) for m, dim in modality_dims.items()}
        self.n_updates = 0

    def predict(self, context: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Predict expected inputs given context.

        Args:
            context: Context/goal vector [context_dim]

        Returns:
            Dict mapping modality -> expected input
        """
        if context is None or len(context) != self.context_dim:
            # Return running means as default expectation
            return {m: self.running_mean[m].copy() for m in self.modality_dims}

        predictions = {}
        for m in self.modality_dims:
            predictions[m] = np.tanh(self.W[m] @ context + self.b[m])
        return predictions

    def update(
        self,
        context: np.ndarray,
        actual_inputs: Dict[str, np.ndarray],
        attention: np.ndarray,
        modality_order: List[str]
    ):
        """
        Update expectations based on actual inputs.

        Only update modalities that were attended (attention-weighted learning).

        Args:
            context: Context that was used for prediction
            actual_inputs: Actual inputs that occurred
            attention: Attention weights (for weighted learning)
            modality_order: Order of modalities
        """
        if context is None or len(context) != self.context_dim:
            return

        for i, m in enumerate(modality_order):
            if m in actual_inputs and m in self.W:
                actual = actual_inputs[m]
                predicted = np.tanh(self.W[m] @ context + self.b[m])
                error = actual - predicted

                # Attention-weighted learning
                lr_effective = self.lr * attention[i]
                # Gradient: d(tanh)/dx = 1 - tanh^2
                grad = (1 - predicted**2) * error
                self.W[m] += lr_effective * np.outer(grad, context)
                self.b[m] += lr_effective * grad

                # Update running mean
                alpha = 0.01
                self.running_mean[m] = (1 - alpha) * self.running_mean[m] + alpha * actual

        self.n_updates += 1

    def get_statistics(self) -> Dict:
        """Get expectation network statistics."""
        return {
            'n_updates': self.n_updates,
            'modalities': list(self.modality_dims.keys()),
            'context_dim': self.context_dim
        }


class CorticalProcessor:
    """
    Complete cortical feedback system.

    Coordinates AttentionController, FeedbackGenerator, and ExpectationNetwork
    to produce coherent top-down feedback to thalamus.

    Integration:
        cortex = CorticalProcessor(n_modalities=6, goal_dim=32, state_dim=128)

        # In processing loop:
        feedback = cortex.step(
            thalamic_output=thalamic_out,
            goal=goal_vector,
            oscillator_state=osc.state,
            neuromod_levels=neuromod.levels
        )

        # Apply feedback to thalamus
        thalamus.apply_feedback(
            prior_delta=feedback.prior_modulation,
            trn_delta=feedback.trn_modulation,
            gain=feedback.gain_modulation
        )
    """

    def __init__(
        self,
        n_modalities: int,
        goal_dim: int = 32,
        state_dim: int = 128,
        modality_dims: Optional[Dict[str, int]] = None,
        modality_order: Optional[List[str]] = None,
        # Attention parameters
        alpha_goal: float = 0.4,
        beta_osc: float = 0.3,
        gamma_pe: float = 0.3,
        tau_pe: float = 0.5,
        # Feedback parameters
        prior_strength: float = 0.1,
        trn_strength: float = 0.05,
        gain_baseline: float = 1.0,
        # Learning
        enable_learning: bool = True,
        lr_attention: float = 0.01,
        lr_expectation: float = 0.01,
        seed: int = 42
    ):
        """
        Initialize cortical processor.

        Args:
            n_modalities: Number of modalities
            goal_dim: Dimension of goal/task encoding
            state_dim: Total state dimension
            modality_dims: Dict mapping modality -> dimension (for expectations)
            modality_order: Order of modalities
            alpha_goal: Weight for goal-driven attention
            beta_osc: Weight for oscillator-modulated attention
            gamma_pe: Weight for PE-driven attention
            tau_pe: Temperature for PE softmax
            prior_strength: Strength of prior modulation
            trn_strength: Strength of TRN modulation
            gain_baseline: Baseline feedback gain
            enable_learning: Enable weight adaptation
            lr_attention: Learning rate for attention
            lr_expectation: Learning rate for expectations
            seed: Random seed
        """
        self.n_modalities = n_modalities
        self.goal_dim = goal_dim
        self.state_dim = state_dim
        self.enable_learning = enable_learning

        # Default modality order
        if modality_order is None:
            modality_order = [f'modality_{i}' for i in range(n_modalities)]
        self.modality_order = modality_order

        # Initialize components
        self.attention = AttentionController(
            n_modalities=n_modalities,
            goal_dim=goal_dim,
            alpha_goal=alpha_goal,
            beta_osc=beta_osc,
            gamma_pe=gamma_pe,
            tau_pe=tau_pe,
            lr_attention=lr_attention,
            seed=seed
        )

        self.feedback = FeedbackGenerator(
            n_modalities=n_modalities,
            state_dim=state_dim,
            prior_strength=prior_strength,
            trn_strength=trn_strength,
            gain_baseline=gain_baseline,
            seed=seed + 1000
        )

        # Expectation network (optional, for learning input predictions)
        if modality_dims is not None:
            self.expectation = ExpectationNetwork(
                modality_dims=modality_dims,
                context_dim=goal_dim,
                lr=lr_expectation,
                seed=seed + 2000
            )
        else:
            self.expectation = None

        # Current state
        self.state = CorticalState(
            attention_weights=np.ones(n_modalities) / n_modalities,
            goal_context=np.zeros(goal_dim)
        )

        # Statistics
        self.steps = 0
        self.last_feedback: Optional[CorticalFeedback] = None

    def step(
        self,
        thalamic_output: Dict,
        goal: Optional[np.ndarray] = None,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        actual_inputs: Optional[Dict[str, np.ndarray]] = None
    ) -> CorticalFeedback:
        """
        Generate cortical feedback from thalamic output.

        Args:
            thalamic_output: Output from thalamus (contains PE, priors, etc.)
            goal: Current goal/task encoding
            oscillator_state: Current oscillator state
            neuromod_levels: Current neuromodulator levels
            actual_inputs: Actual sensory inputs (for expectation learning)

        Returns:
            CorticalFeedback to apply to thalamus
        """
        # Extract prediction errors from thalamic output
        pe_dict = thalamic_output.get('PE', {})
        if isinstance(pe_dict, dict):
            prediction_errors = np.array([
                pe_dict.get(m, 0.0) for m in self.modality_order
            ])
        else:
            prediction_errors = np.zeros(self.n_modalities)

        # Extract current priors
        priors = thalamic_output.get('priors', {})
        if priors:
            self.feedback.set_current_priors(priors, self.modality_order)

        # 1) Compute attention
        attention = self.attention.compute_attention(
            goal=goal,
            oscillator_state=oscillator_state,
            prediction_errors=prediction_errors,
            neuromod_levels=neuromod_levels
        )

        # 2) Generate feedback
        feedback = self.feedback.generate_feedback(
            attention=attention,
            prediction_errors=prediction_errors,
            neuromod_levels=neuromod_levels
        )

        # 3) Update expectations (if enabled and inputs provided)
        if self.enable_learning and self.expectation is not None and actual_inputs is not None:
            self.expectation.update(
                context=goal,
                actual_inputs=actual_inputs,
                attention=attention,
                modality_order=self.modality_order
            )

        # Update state
        self.state.attention_weights = attention.copy()
        self.state.prediction_errors = prediction_errors.copy()
        if goal is not None:
            self.state.goal_context = goal.copy()
        self.state.feedback_gain = feedback.gain_modulation

        self.last_feedback = feedback
        self.steps += 1

        return feedback

    def update_from_reward(
        self,
        reward: float,
        goal: np.ndarray,
        oscillator_state: Optional['TripleOscillatorState'] = None
    ):
        """
        Update attention weights based on reward signal.

        Args:
            reward: Reward signal (+1 success, -1 failure)
            goal: Goal that was used
            oscillator_state: Oscillator state that was used
        """
        if self.enable_learning:
            self.attention.update_weights(
                attention=self.state.attention_weights,
                reward=reward,
                goal=goal,
                oscillator_state=oscillator_state
            )

    def get_expected_inputs(self, goal: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Get expected inputs given current goal.

        Args:
            goal: Goal/context vector

        Returns:
            Dict mapping modality -> expected input
        """
        if self.expectation is not None:
            return self.expectation.predict(goal)
        return {}

    def get_state(self) -> CorticalState:
        """Get current cortical state."""
        return self.state

    def get_statistics(self) -> Dict:
        """Get comprehensive statistics."""
        stats = {
            'steps': self.steps,
            'n_modalities': self.n_modalities,
            'goal_dim': self.goal_dim,
            'current_attention': self.state.attention_weights.tolist(),
            'current_gain': self.state.feedback_gain,
            'attention_controller': self.attention.get_statistics(),
            'feedback_generator': self.feedback.get_statistics()
        }

        if self.expectation is not None:
            stats['expectation_network'] = self.expectation.get_statistics()

        if self.last_feedback is not None:
            stats['last_feedback'] = self.last_feedback.to_dict()

        return stats

    def reset(self):
        """Reset processor state (keep learned weights)."""
        self.state = CorticalState(
            attention_weights=np.ones(self.n_modalities) / self.n_modalities,
            goal_context=np.zeros(self.goal_dim)
        )
        self.last_feedback = None
        # Don't reset learned weights in attention/feedback/expectation

    def predict_next_attention(
        self,
        current_attention: np.ndarray,
        prediction_confidence: float = 0.5
    ) -> np.ndarray:
        """
        Predict next-step attention based on current state and goals.

        Used by PredictiveRouter to incorporate cortical predictions
        into anticipatory gate adjustment.

        Args:
            current_attention: Current attention weights [n_modalities]
            prediction_confidence: Confidence in predictions (0-1)

        Returns:
            Predicted next-step attention weights (sum to 1.0)
        """
        # Use expectation network for prediction if available
        if self.expectation is not None:
            # Get expected inputs based on current goal
            expected = self.expectation.predict(self.state.goal_context)

            if expected:
                # Compute expected salience from predictions
                expected_salience = np.zeros(self.n_modalities)
                for i, m in enumerate(self.modality_order):
                    if m in expected:
                        # Higher expected magnitude -> higher salience
                        expected_salience[i] = np.linalg.norm(expected[m])

                # Normalize to sum to 1
                if np.sum(expected_salience) > 1e-8:
                    expected_salience /= np.sum(expected_salience)

                    # Blend based on confidence
                    alpha = 0.3 * prediction_confidence
                    predicted = (1 - alpha) * current_attention + alpha * expected_salience

                    # Ensure normalization
                    predicted = np.maximum(predicted, 1e-8)
                    predicted /= np.sum(predicted)

                    return predicted

        # Fallback: use attention history trend if available
        if len(self.attention.attention_history) >= 2:
            recent = np.array(self.attention.attention_history[-3:])
            # Simple trend extrapolation
            if len(recent) >= 2:
                trend = recent[-1] - recent[-2]
                alpha = 0.2 * prediction_confidence
                predicted = current_attention + alpha * trend

                # Ensure valid distribution
                predicted = np.maximum(predicted, 1e-8)
                predicted /= np.sum(predicted)

                return predicted

        # Default: return current attention unchanged
        return current_attention.copy()
