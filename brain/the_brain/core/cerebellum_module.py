"""
Cerebellum Module - Neuroscience Architecture Extension Phase A1

Computational model of the cerebellum for prediction, timing, and
motor/cognitive error-driven learning.

Neuroscience basis:
- Purkinje cells: Primary computational units, inhibitory output
- Granule cells: Sparse expansion of mossy fiber inputs (100:1 biologically)
- Climbing fibers: Error signal from inferior olive (Ito, 1984)
- Mossy fibers: Contextual input from pontine nuclei
- Forward/Inverse models: Wolpert et al. (1998) internal models theory
- Timing circuits: Precise interval learning (Ivry & Spencer, 2004)

Key references:
- "Consensus Paper: Cerebellum and Ageing" (PubMed)
- "Physiology of the cerebellum" (PubMed)
- Wolpert, Miall & Kawato (1998): Internal models in the cerebellum
- Ito (2008): Control and coordination of voluntary movements

Integration points:
- Input: Sensory data (via Thalamus), motor commands (via Basal Ganglia)
- Output: Corrected motor programs, prediction errors back to Cortex
- Wiring: agent_loop.cerebellum = CerebellumModule.from_yaml(config)
"""

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.cerebellum')

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class CerebellarPrediction:
    """Result of a cerebellar forward-model prediction."""
    predicted_state: np.ndarray
    confidence: float = 0.5
    prediction_error: float = 0.0
    timing_error: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'predicted_state': self.predicted_state.tolist(),
            'confidence': self.confidence,
            'prediction_error': self.prediction_error,
            'timing_error': self.timing_error,
            'timestamp': self.timestamp,
        }


@dataclass
class CerebellarStats:
    """Aggregate stats for the cerebellum module."""
    total_predictions: int = 0
    total_corrections: int = 0
    avg_prediction_error: float = 0.0
    avg_timing_error: float = 0.0
    learning_rate_effective: float = 0.01
    purkinje_activity: float = 0.0
    granule_sparsity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_predictions': self.total_predictions,
            'total_corrections': self.total_corrections,
            'avg_prediction_error': self.avg_prediction_error,
            'avg_timing_error': self.avg_timing_error,
            'learning_rate_effective': self.learning_rate_effective,
            'purkinje_activity': self.purkinje_activity,
            'granule_sparsity': self.granule_sparsity,
        }


# ─── Granule Layer ─────────────────────────────────────────────────────────────

class GranuleLayer:
    """
    Granule cell layer: sparse expansion of mossy fiber inputs.

    Biologically: ~50 billion granule cells expand ~200 million mossy fibers
    (ratio ~250:1). We use a configurable expansion factor (default 4:1).

    Each granule cell receives input from ~4 mossy fibers and produces
    a sparse, high-dimensional representation enabling pattern separation.
    """

    def __init__(self, input_dim: int, expansion: int = 4, sparsity: float = 0.3):
        self.input_dim = input_dim
        self.output_dim = input_dim * expansion
        self.expansion = expansion
        self.sparsity = sparsity

        # Random projection weights (fixed, like biological connectivity)
        rng = np.random.RandomState(42)
        self.weights = rng.randn(input_dim, self.output_dim).astype(np.float32)
        self.weights *= np.sqrt(2.0 / input_dim)

        # Each granule cell only receives from ~4 mossy fibers (sparse connectivity)
        mask = rng.rand(input_dim, self.output_dim) > (4.0 / input_dim)
        self.weights[mask] = 0.0

        self.bias = np.zeros(self.output_dim, dtype=np.float32)
        self._last_activity = np.zeros(self.output_dim, dtype=np.float32)

    def forward(self, mossy_input: np.ndarray) -> np.ndarray:
        """
        Transform mossy fiber input through granule layer.

        Args:
            mossy_input: Input vector from mossy fibers [input_dim]

        Returns:
            Sparse high-dim representation [output_dim]
        """
        x = mossy_input.astype(np.float32)
        if x.ndim > 1:
            x = x.flatten()

        # Linear projection
        activation = x @ self.weights + self.bias

        # ReLU
        activation = np.maximum(0, activation)

        # Competitive inhibition: keep only top-k active (sparsity)
        k = max(1, int(self.output_dim * self.sparsity))
        if np.count_nonzero(activation) > k:
            threshold = np.partition(activation, -k)[-k]
            activation[activation < threshold] = 0.0

        self._last_activity = activation
        return activation

    def get_sparsity(self) -> float:
        """Return current sparsity ratio (fraction of zeros)."""
        if self._last_activity.size == 0:
            return 1.0
        return float(np.count_nonzero(self._last_activity == 0)) / self._last_activity.size

    def to_dict(self) -> Dict[str, Any]:
        return {
            'input_dim': self.input_dim,
            'output_dim': self.output_dim,
            'expansion': self.expansion,
            'sparsity_target': self.sparsity,
            'actual_sparsity': self.get_sparsity(),
        }


# ─── Purkinje Layer ────────────────────────────────────────────────────────────

class PurkinjeLayer:
    """
    Purkinje cell layer: main computational element of the cerebellum.

    Biologically: ~15 million Purkinje cells receive parallel fiber input
    from granule cells and climbing fiber error signals from inferior olive.

    Each Purkinje cell acts as a perceptron learning from:
    - Parallel fibers (granule cell output): the "context"
    - Climbing fibers (error signal): the "teaching signal"

    Long-term depression (LTD) at parallel fiber-Purkinje synapses is
    the primary learning mechanism (Ito, 1984).
    """

    def __init__(self, input_dim: int, output_dim: int, learning_rate: float = 0.01):
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.learning_rate = learning_rate

        # Parallel fiber -> Purkinje weights (learnable via LTD/LTP)
        self.weights = np.random.randn(input_dim, output_dim).astype(np.float32)
        self.weights *= np.sqrt(2.0 / input_dim)
        self.bias = np.zeros(output_dim, dtype=np.float32)

        # Eligibility traces for temporal credit assignment
        self._eligibility = np.zeros_like(self.weights)
        self._trace_decay = 0.95

        self._last_output = np.zeros(output_dim, dtype=np.float32)
        self._last_input = np.zeros(input_dim, dtype=np.float32)

    def forward(self, parallel_fiber_input: np.ndarray) -> np.ndarray:
        """
        Compute Purkinje cell output from parallel fiber input.

        Purkinje cells are inhibitory (GABAergic), so output is negated.
        """
        x = parallel_fiber_input.astype(np.float32)
        if x.ndim > 1:
            x = x.flatten()

        # Truncate or pad if dimension mismatch
        if x.shape[0] != self.input_dim:
            padded = np.zeros(self.input_dim, dtype=np.float32)
            n = min(x.shape[0], self.input_dim)
            padded[:n] = x[:n]
            x = padded

        self._last_input = x

        # Linear + tanh activation (Purkinje output is bounded)
        output = np.tanh(x @ self.weights + self.bias)

        # Update eligibility trace
        self._eligibility = (self._trace_decay * self._eligibility +
                             np.outer(x, output))

        self._last_output = output
        return output

    def learn_from_climbing_fiber(self, error_signal: np.ndarray) -> float:
        """
        Apply climbing fiber error signal for LTD learning.

        The climbing fiber from the inferior olive carries the prediction
        error. LTD weakens parallel fiber synapses that were active
        when the error occurred.

        Args:
            error_signal: Error vector [output_dim]

        Returns:
            Magnitude of weight update
        """
        error = error_signal.astype(np.float32)
        if error.ndim > 1:
            error = error.flatten()
        if error.shape[0] != self.output_dim:
            padded = np.zeros(self.output_dim, dtype=np.float32)
            n = min(error.shape[0], self.output_dim)
            padded[:n] = error[:n]
            error = padded

        # LTD: reduce weights proportional to eligibility * error
        delta = -self.learning_rate * self._eligibility * error[np.newaxis, :]
        self.weights += delta

        # Clip weights to prevent explosion
        np.clip(self.weights, -5.0, 5.0, out=self.weights)

        update_magnitude = float(np.abs(delta).mean())
        return update_magnitude

    def get_activity(self) -> float:
        """Return mean absolute Purkinje activity."""
        return float(np.abs(self._last_output).mean())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'input_dim': self.input_dim,
            'output_dim': self.output_dim,
            'learning_rate': self.learning_rate,
            'mean_activity': self.get_activity(),
            'weight_norm': float(np.linalg.norm(self.weights)),
        }


# ─── Climbing Fiber Signal ─────────────────────────────────────────────────────

class ClimbingFiberSignal:
    """
    Climbing fiber pathway from the Inferior Olive.

    Computes the error signal between predicted and actual outcomes.
    This is the primary teaching signal for cerebellar learning.

    Biologically: Each Purkinje cell receives input from exactly one
    climbing fiber, which fires at ~1Hz and represents complex spike
    (error) signals.
    """

    def __init__(self, signal_dim: int, error_threshold: float = 0.1):
        self.signal_dim = signal_dim
        self.error_threshold = error_threshold
        self._error_history = deque(maxlen=100)
        self._last_error = np.zeros(signal_dim, dtype=np.float32)

    def compute_error(
        self,
        predicted: np.ndarray,
        actual: np.ndarray
    ) -> np.ndarray:
        """
        Compute climbing fiber error signal.

        Args:
            predicted: Predicted state/outcome
            actual: Actual observed state/outcome

        Returns:
            Error signal vector (only fires if above threshold)
        """
        pred = np.asarray(predicted, dtype=np.float32).flatten()
        act = np.asarray(actual, dtype=np.float32).flatten()

        # Match dimensions
        dim = min(len(pred), len(act), self.signal_dim)
        error = np.zeros(self.signal_dim, dtype=np.float32)
        error[:dim] = act[:dim] - pred[:dim]

        # Complex spike: only fires when error exceeds threshold
        error_mag = float(np.abs(error).mean())
        if error_mag < self.error_threshold:
            error *= 0.0  # Sub-threshold: no climbing fiber discharge

        self._last_error = error
        self._error_history.append(error_mag)
        return error

    def get_avg_error(self) -> float:
        """Return average error over recent history."""
        if not self._error_history:
            return 0.0
        return float(np.mean(list(self._error_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'signal_dim': self.signal_dim,
            'error_threshold': self.error_threshold,
            'avg_error': self.get_avg_error(),
            'last_error_mag': float(np.abs(self._last_error).mean()),
        }


# ─── Mossy Fiber Input ─────────────────────────────────────────────────────────

class MossyFiberInput:
    """
    Mossy fiber input pathway.

    Conveys contextual information from pontine nuclei, spinal cord,
    and other brainstem structures to the granule cells.

    Combines sensory state + motor efference copy into a unified
    mossy fiber signal.
    """

    def __init__(self, sensory_dim: int, motor_dim: int):
        self.sensory_dim = sensory_dim
        self.motor_dim = motor_dim
        self.output_dim = sensory_dim + motor_dim
        self._last_output = np.zeros(self.output_dim, dtype=np.float32)

    def combine(
        self,
        sensory_state: np.ndarray,
        motor_command: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Combine sensory state and motor efference copy.

        Args:
            sensory_state: Current sensory representation
            motor_command: Motor efference copy (optional)

        Returns:
            Combined mossy fiber signal
        """
        s = np.asarray(sensory_state, dtype=np.float32).flatten()

        # Pad/truncate sensory to expected dim
        sensory = np.zeros(self.sensory_dim, dtype=np.float32)
        n_s = min(len(s), self.sensory_dim)
        sensory[:n_s] = s[:n_s]

        # Motor component
        motor = np.zeros(self.motor_dim, dtype=np.float32)
        if motor_command is not None:
            m = np.asarray(motor_command, dtype=np.float32).flatten()
            n_m = min(len(m), self.motor_dim)
            motor[:n_m] = m[:n_m]

        output = np.concatenate([sensory, motor])
        self._last_output = output
        return output

    def to_dict(self) -> Dict[str, Any]:
        return {
            'sensory_dim': self.sensory_dim,
            'motor_dim': self.motor_dim,
            'output_dim': self.output_dim,
        }


# ─── Cerebellar Forward Model ─────────────────────────────────────────────────

class CerebellarForwardModel:
    """
    Internal forward model: predicts next state given (state, action).

    P(s_{t+1} | s_t, a_t)

    Uses the cerebellar microcircuit (granule -> Purkinje) to learn
    state transitions. Error-driven learning via climbing fibers
    produces accurate predictions over time.

    Wolpert et al. (1998): Multiple forward models exist in the
    cerebellum, each specialized for different contexts.
    """

    def __init__(self, state_dim: int, action_dim: int, hidden_expansion: int = 4):
        self.state_dim = state_dim
        self.action_dim = action_dim

        # Mossy fibers carry state + action
        self.mossy = MossyFiberInput(sensory_dim=state_dim, motor_dim=action_dim)

        # Granule layer: sparse expansion
        self.granule = GranuleLayer(
            input_dim=self.mossy.output_dim,
            expansion=hidden_expansion,
            sparsity=0.3
        )

        # Purkinje layer: maps expanded representation to predicted state
        self.purkinje = PurkinjeLayer(
            input_dim=self.granule.output_dim,
            output_dim=state_dim,
            learning_rate=0.01
        )

        # Climbing fiber: carries prediction error
        self.climbing_fiber = ClimbingFiberSignal(
            signal_dim=state_dim,
            error_threshold=0.05
        )

        self._prediction_count = 0

    def predict(self, state: np.ndarray, action: np.ndarray) -> CerebellarPrediction:
        """
        Predict next state given current state and action.

        Args:
            state: Current state vector
            action: Action vector (or one-hot encoded action)

        Returns:
            CerebellarPrediction with predicted state
        """
        # Mossy fiber input: combine state + action
        mossy_signal = self.mossy.combine(state, action)

        # Granule cell expansion
        granule_output = self.granule.forward(mossy_signal)

        # Purkinje cell computation
        predicted_delta = self.purkinje.forward(granule_output)

        # Predicted next state = current + delta
        state_flat = np.asarray(state, dtype=np.float32).flatten()
        padded_state = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(state_flat), self.state_dim)
        padded_state[:n] = state_flat[:n]

        predicted_state = padded_state + predicted_delta

        # Confidence based on recent error history
        avg_error = self.climbing_fiber.get_avg_error()
        confidence = max(0.0, 1.0 - avg_error)

        self._prediction_count += 1
        return CerebellarPrediction(
            predicted_state=predicted_state,
            confidence=confidence,
        )

    def learn(self, predicted: np.ndarray, actual: np.ndarray) -> float:
        """
        Update forward model from observed prediction error.

        Args:
            predicted: What was predicted
            actual: What actually happened

        Returns:
            Magnitude of the learning update
        """
        # Climbing fiber computes error
        error_signal = self.climbing_fiber.compute_error(predicted, actual)

        # Purkinje cells learn via LTD
        update_mag = self.purkinje.learn_from_climbing_fiber(error_signal)
        return update_mag

    def to_dict(self) -> Dict[str, Any]:
        return {
            'state_dim': self.state_dim,
            'action_dim': self.action_dim,
            'predictions': self._prediction_count,
            'avg_error': self.climbing_fiber.get_avg_error(),
            'granule_sparsity': self.granule.get_sparsity(),
            'purkinje_activity': self.purkinje.get_activity(),
        }


# ─── Cerebellar Inverse Model ─────────────────────────────────────────────────

class CerebellarInverseModel:
    """
    Internal inverse model: infers action given (state, desired_next_state).

    a_t = f(s_t, s*_{t+1})

    Computes what action is needed to reach a desired state.
    Used for motor planning and cognitive control.
    """

    def __init__(self, state_dim: int, action_dim: int, hidden_expansion: int = 4):
        self.state_dim = state_dim
        self.action_dim = action_dim

        # Mossy fibers carry current_state + desired_state
        self.mossy = MossyFiberInput(sensory_dim=state_dim, motor_dim=state_dim)

        # Granule layer
        self.granule = GranuleLayer(
            input_dim=self.mossy.output_dim,
            expansion=hidden_expansion,
            sparsity=0.3
        )

        # Purkinje layer: output is action probabilities
        self.purkinje = PurkinjeLayer(
            input_dim=self.granule.output_dim,
            output_dim=action_dim,
            learning_rate=0.01
        )

        self.climbing_fiber = ClimbingFiberSignal(
            signal_dim=action_dim,
            error_threshold=0.05
        )

    def infer_action(
        self,
        current_state: np.ndarray,
        desired_state: np.ndarray
    ) -> Tuple[int, np.ndarray]:
        """
        Infer action to reach desired state from current state.

        Args:
            current_state: Current state vector
            desired_state: Desired next state vector

        Returns:
            (best_action_index, action_probabilities)
        """
        mossy_signal = self.mossy.combine(current_state, desired_state)
        granule_output = self.granule.forward(mossy_signal)
        raw_output = self.purkinje.forward(granule_output)

        # Softmax to get action probabilities
        exp_out = np.exp(raw_output - raw_output.max())
        probs = exp_out / (exp_out.sum() + 1e-8)

        best_action = int(np.argmax(probs))
        return best_action, probs

    def learn(self, predicted_action: np.ndarray, actual_action: np.ndarray) -> float:
        """Learn from action prediction error."""
        error_signal = self.climbing_fiber.compute_error(predicted_action, actual_action)
        return self.purkinje.learn_from_climbing_fiber(error_signal)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'state_dim': self.state_dim,
            'action_dim': self.action_dim,
            'avg_error': self.climbing_fiber.get_avg_error(),
        }


# ─── Timing Circuit ────────────────────────────────────────────────────────────

class TimingCircuit:
    """
    Cerebellar timing circuit for precise interval learning.

    The cerebellum is essential for timing in the sub-second range.
    This circuit learns to predict when events will occur and
    generates appropriately timed responses.

    Based on: Ivry & Spencer (2004), Medina et al. (2000)
    - Delay eyeblink conditioning paradigm
    - Spectral timing: population of elements with different time constants
    """

    def __init__(
        self,
        n_timers: int = 16,
        min_interval: float = 0.05,
        max_interval: float = 5.0,
        learning_rate: float = 0.01
    ):
        self.n_timers = n_timers
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.learning_rate = learning_rate

        # Spectral timing: each timer has a preferred interval
        self.preferred_intervals = np.geomspace(
            min_interval, max_interval, n_timers
        ).astype(np.float32)

        # Weights for combining timer outputs
        self.weights = np.ones(n_timers, dtype=np.float32) / n_timers

        # State
        self._current_phases = np.zeros(n_timers, dtype=np.float32)
        self._last_event_time = time.time()
        self._interval_history = deque(maxlen=50)
        self._learned_interval = 0.5  # Default

    def tick(self, current_time: Optional[float] = None) -> np.ndarray:
        """
        Update timing circuit and return timer activations.

        Args:
            current_time: Current time (uses time.time() if None)

        Returns:
            Timer activation vector [n_timers]
        """
        if current_time is None:
            current_time = time.time()

        elapsed = current_time - self._last_event_time

        # Each timer ramps up based on its preferred interval
        for i in range(self.n_timers):
            phase = elapsed / self.preferred_intervals[i]
            # Gaussian activation centered at phase=1.0 (expected time)
            self._current_phases[i] = math.exp(-0.5 * ((phase - 1.0) ** 2) / 0.1)

        return self._current_phases * self.weights

    def signal_event(self, current_time: Optional[float] = None) -> float:
        """
        Signal that an event occurred. Learn the interval.

        Args:
            current_time: Time of event

        Returns:
            Timing error (predicted - actual interval)
        """
        if current_time is None:
            current_time = time.time()

        actual_interval = current_time - self._last_event_time
        predicted_interval = self.get_predicted_interval()
        timing_error = predicted_interval - actual_interval

        # Learn: update weights to favor timers matching the actual interval
        for i in range(self.n_timers):
            match = math.exp(-0.5 * ((actual_interval - self.preferred_intervals[i])
                                      / self.preferred_intervals[i]) ** 2)
            self.weights[i] += self.learning_rate * (match - self.weights[i])

        # Normalize weights
        w_sum = self.weights.sum()
        if w_sum > 0:
            self.weights /= w_sum

        self._interval_history.append(actual_interval)
        self._learned_interval = actual_interval
        self._last_event_time = current_time

        return timing_error

    def get_predicted_interval(self) -> float:
        """Return the current best estimate of the interval."""
        return float(np.dot(self.weights, self.preferred_intervals))

    def reset(self, current_time: Optional[float] = None):
        """Reset timing circuit."""
        self._last_event_time = current_time or time.time()
        self._current_phases[:] = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_timers': self.n_timers,
            'predicted_interval': self.get_predicted_interval(),
            'learned_interval': self._learned_interval,
            'history_size': len(self._interval_history),
        }


# ─── Main Cerebellum Module ───────────────────────────────────────────────────

class CerebellumModule:
    """
    Complete cerebellum module integrating all sub-circuits.

    The cerebellum:
    1. Receives sensory + motor signals (mossy fibers)
    2. Expands into sparse representations (granule cells)
    3. Computes predictions (Purkinje cells)
    4. Learns from errors (climbing fibers)
    5. Times sequences precisely (timing circuit)

    Supports both motor prediction (classic) and cognitive prediction
    (cerebellar cognitive affective syndrome - Schmahmann, 1998).
    """

    def __init__(
        self,
        state_dim: int = 32,
        action_dim: int = 4,
        hidden_expansion: int = 4,
        learning_rate: float = 0.01,
        n_timers: int = 16,
        timing_resolution: float = 0.05,
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.learning_rate = learning_rate

        # Core circuits
        self.forward_model = CerebellarForwardModel(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_expansion=hidden_expansion,
        )
        self.forward_model.purkinje.learning_rate = learning_rate

        self.inverse_model = CerebellarInverseModel(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_expansion=hidden_expansion,
        )
        self.inverse_model.purkinje.learning_rate = learning_rate

        self.timing = TimingCircuit(
            n_timers=n_timers,
            min_interval=timing_resolution,
            max_interval=5.0,
            learning_rate=learning_rate,
        )

        # Stats
        self._stats = CerebellarStats(learning_rate_effective=learning_rate)
        self._prediction_errors = deque(maxlen=200)
        self._timing_errors = deque(maxlen=200)

    def predict_next_state(
        self,
        state: np.ndarray,
        action: np.ndarray
    ) -> CerebellarPrediction:
        """
        Predict the next state given current state and action.

        This is the primary cerebellar function: given a motor command
        (or cognitive plan), predict what will happen next.

        Args:
            state: Current state [state_dim]
            action: Action vector [action_dim] or one-hot

        Returns:
            CerebellarPrediction with predicted state and confidence
        """
        prediction = self.forward_model.predict(state, action)

        # Add timing information
        timer_activations = self.timing.tick()
        prediction.timing_error = float(np.abs(timer_activations).mean())

        self._stats.total_predictions += 1
        return prediction

    def correct_motor_program(
        self,
        current_state: np.ndarray,
        desired_state: np.ndarray
    ) -> Tuple[int, np.ndarray]:
        """
        Use inverse model to correct a motor program.

        Given where we are and where we want to be, compute
        the corrective action.

        Args:
            current_state: Current state
            desired_state: Target state

        Returns:
            (best_action, action_probabilities)
        """
        action, probs = self.inverse_model.infer_action(current_state, desired_state)
        self._stats.total_corrections += 1
        return action, probs

    def update_from_outcome(
        self,
        predicted_state: np.ndarray,
        actual_state: np.ndarray
    ) -> float:
        """
        Learn from the difference between prediction and reality.

        This is the climbing fiber teaching signal.

        Args:
            predicted_state: What the forward model predicted
            actual_state: What actually occurred

        Returns:
            Prediction error magnitude
        """
        # Forward model learns
        update_mag = self.forward_model.learn(predicted_state, actual_state)

        # Track error
        error = float(np.mean(np.abs(
            np.asarray(actual_state).flatten()[:self.state_dim] -
            np.asarray(predicted_state).flatten()[:self.state_dim]
        )))
        self._prediction_errors.append(error)

        # Update stats
        if self._prediction_errors:
            self._stats.avg_prediction_error = float(np.mean(list(self._prediction_errors)))
        self._stats.purkinje_activity = self.forward_model.purkinje.get_activity()
        self._stats.granule_sparsity = self.forward_model.granule.get_sparsity()

        return error

    def signal_timing_event(self) -> float:
        """
        Signal that a timed event occurred.

        Returns:
            Timing error
        """
        timing_error = self.timing.signal_event()
        self._timing_errors.append(abs(timing_error))

        if self._timing_errors:
            self._stats.avg_timing_error = float(np.mean(list(self._timing_errors)))

        return timing_error

    def get_prediction_error(self) -> float:
        """Return current average prediction error."""
        return self._stats.avg_prediction_error

    def get_timing_prediction(self) -> float:
        """Return predicted interval until next event."""
        return self.timing.get_predicted_interval()

    def compute_sensory_prediction_error(
        self,
        predicted_sensory: np.ndarray,
        actual_sensory: np.ndarray,
    ) -> Dict[str, float]:
        """
        Sensory prediction error via climbing fiber signal (Marr, 1969; Ito, 2008).

        The cerebellum learns to predict sensory consequences of actions.
        When prediction fails, the inferior olive sends a climbing fiber
        error signal that triggers Purkinje cell LTD (long-term depression),
        updating the internal model. This is the basis of motor learning.

        Args:
            predicted_sensory: Predicted sensory outcome from forward model
            actual_sensory: Actual sensory feedback received

        Returns:
            Dict with prediction_error, learning_signal, model_confidence
        """
        predicted = np.asarray(predicted_sensory, dtype=np.float32)
        actual = np.asarray(actual_sensory, dtype=np.float32)

        min_len = min(len(predicted), len(actual))
        predicted = predicted[:min_len]
        actual = actual[:min_len]

        # Climbing fiber error = actual - predicted
        error = actual - predicted
        error_magnitude = float(np.linalg.norm(error)) / max(1.0, float(min_len ** 0.5))

        # Learning signal: proportional to error (climbing fiber)
        learning_signal = min(1.0, error_magnitude * 2.0)

        # Model confidence: inverse of recent prediction errors
        avg_pe = self.get_prediction_error()
        model_confidence = max(0.0, 1.0 - avg_pe * 2.0)

        return {
            'prediction_error': round(error_magnitude, 4),
            'learning_signal': round(learning_signal, 4),
            'model_confidence': round(model_confidence, 4),
            'should_update_model': error_magnitude > 0.1,
        }

    def get_state(self) -> Dict[str, Any]:
        """Return full cerebellum state for monitoring."""
        return {
            'stats': self._stats.to_dict(),
            'forward_model': self.forward_model.to_dict(),
            'inverse_model': self.inverse_model.to_dict(),
            'timing': self.timing.to_dict(),
        }

    def get_stats(self) -> CerebellarStats:
        """Return statistics object."""
        return self._stats

    def reset(self):
        """Reset cerebellum state."""
        self._stats = CerebellarStats(learning_rate_effective=self.learning_rate)
        self._prediction_errors.clear()
        self._timing_errors.clear()
        self.timing.reset()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    # ─── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'CerebellumModule':
        """
        Create CerebellumModule from YAML configuration.

        Expected config section:
            cerebellum:
              granule_expansion: 4
              learning_rate: 0.01
              timing_resolution: 10  # ms -> converted to seconds
              n_timers: 16
        """
        cb_config = config.get('cerebellum', {})

        state_dim = config.get('state_dim',
                    config.get('model', {}).get('input_dim', 32))
        action_dim = config.get('action_dim',
                     config.get('model', {}).get('output_dim', 4))

        timing_ms = cb_config.get('timing_resolution', 10)
        timing_sec = timing_ms / 1000.0 if timing_ms > 1.0 else timing_ms

        return cls(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_expansion=cb_config.get('granule_expansion', 4),
            learning_rate=cb_config.get('learning_rate', 0.01),
            n_timers=cb_config.get('n_timers', 16),
            timing_resolution=timing_sec,
        )
