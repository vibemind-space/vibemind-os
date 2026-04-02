"""
Predictive Router - Forward Models and Anticipatory Gate Adjustment

This module implements predictive routing for the ATM-R architecture,
enabling the system to pre-adjust attention gates based on predicted
future states rather than reacting purely to current inputs.

Key Components:
- ForwardModel: Predicts next-timestep latent states per modality
- AnticipatedGateComputer: Computes anticipatory gates from predictions
- TemporalRoutingPattern: Learns recurring routing sequences
- PredictiveRouter: Main orchestrator combining all components

Critical Invariant: Gates MUST always sum to 1.0
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class PredictiveState:
    """State for predictive routing system."""
    predicted_latents: Dict[str, np.ndarray]  # v_pred[m] per modality
    anticipated_gates: np.ndarray  # g_anticipated
    prediction_confidence: float  # How confident in predictions
    temporal_context: np.ndarray  # Sequence history encoding


@dataclass
class RoutingPrediction:
    """Output from predictive router."""
    blended_gates: np.ndarray  # Final gates (sum to 1.0)
    gate_deltas: np.ndarray  # Anticipatory adjustments
    prediction_error: float  # For learning
    confidence: float  # Current confidence level


class ForwardModel:
    """
    Predicts next-timestep latent states per modality.

    Uses a simple MLP architecture: v[t] -> v_pred[t+1]
    Each modality has its own forward model to capture
    modality-specific temporal dynamics.
    """

    def __init__(
        self,
        modalities: List[str],
        latent_dims: Dict[str, int],
        hidden_dim: int = 64,
        lr: float = 0.01
    ):
        """
        Initialize forward models for each modality.

        Args:
            modalities: List of modality names
            latent_dims: Dict mapping modality -> latent dimension
            hidden_dim: Hidden layer size for MLP
            lr: Learning rate for model updates
        """
        self.modalities = modalities
        self.latent_dims = latent_dims
        self.hidden_dim = hidden_dim
        self.lr = lr

        # Forward models F[m]: v[t] -> v_pred[t+1]
        # Each model is a 2-layer MLP
        self.F: Dict[str, Dict[str, np.ndarray]] = {}
        for m in modalities:
            dim = latent_dims.get(m, 32)
            self.F[m] = {
                'W1': np.random.randn(hidden_dim, dim) * 0.1,
                'b1': np.zeros(hidden_dim),
                'W2': np.random.randn(dim, hidden_dim) * 0.1,
                'b2': np.zeros(dim)
            }

        # Cache for backprop
        self._hidden_cache: Dict[str, np.ndarray] = {}

    def predict(
        self,
        v_current: Dict[str, np.ndarray],
        gates: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Predict next-step latent states for all modalities.

        Args:
            v_current: Current latent states per modality
            gates: Current gate values (used for modulation)

        Returns:
            Dict of predicted latent states per modality
        """
        v_pred = {}

        for i, m in enumerate(self.modalities):
            # Get current latent or default to zeros
            dim = self.latent_dims.get(m, 32)
            v = v_current.get(m, np.zeros(dim))

            # Ensure correct dimension
            if len(v) != dim:
                v = np.zeros(dim)

            # Gate-weighted modulation (attend more to likely-relevant modalities)
            gate_weight = gates[i] if i < len(gates) else 1.0 / len(self.modalities)

            # Forward pass through F[m]
            h = np.tanh(self.F[m]['W1'] @ v + self.F[m]['b1'])
            self._hidden_cache[m] = h  # Cache for learning

            v_pred[m] = self.F[m]['W2'] @ h + self.F[m]['b2']

            # Gate modulation: scale prediction by gate relevance
            # Higher gate -> more confident prediction
            v_pred[m] *= (0.5 + 0.5 * gate_weight)

        return v_pred

    def update(
        self,
        v_predicted: Dict[str, np.ndarray],
        v_actual: Dict[str, np.ndarray],
        v_input: Dict[str, np.ndarray]
    ) -> float:
        """
        Learn from prediction errors.

        Args:
            v_predicted: Previously predicted latents
            v_actual: Actual observed latents
            v_input: Input latents used for prediction

        Returns:
            Mean prediction error across modalities
        """
        total_error = 0.0
        n_updated = 0

        for m in self.modalities:
            if m not in v_actual or m not in v_predicted:
                continue

            # Prediction error
            error = v_actual[m] - v_predicted[m]
            total_error += np.mean(error ** 2)
            n_updated += 1

            # Get cached hidden state (or recompute)
            if m in self._hidden_cache:
                h = self._hidden_cache[m]
            else:
                v_in = v_input.get(m, np.zeros(self.latent_dims.get(m, 32)))
                h = np.tanh(self.F[m]['W1'] @ v_in + self.F[m]['b1'])

            # Gradient descent on output layer
            dW2 = np.outer(error, h)
            db2 = error

            self.F[m]['W2'] += self.lr * dW2
            self.F[m]['b2'] += self.lr * db2

            # Backprop to hidden layer (simplified)
            dh = self.F[m]['W2'].T @ error
            dh_pre = dh * (1 - h ** 2)  # tanh derivative

            v_in = v_input.get(m, np.zeros(self.latent_dims.get(m, 32)))
            if len(v_in) == self.F[m]['W1'].shape[1]:
                dW1 = np.outer(dh_pre, v_in)
                self.F[m]['W1'] += self.lr * 0.5 * dW1  # Smaller LR for hidden
                self.F[m]['b1'] += self.lr * 0.5 * dh_pre

        return total_error / max(n_updated, 1)

    def get_state(self) -> Dict:
        """Get serializable state."""
        return {
            'modalities': self.modalities,
            'latent_dims': self.latent_dims,
            'F': {m: {k: v.tolist() for k, v in params.items()}
                  for m, params in self.F.items()}
        }


class AnticipatedGateComputer:
    """
    Computes anticipatory gates from predicted latent states.

    Maps concatenated predicted latents to gate relevance scores,
    then applies softmax to ensure gates sum to 1.0.
    """

    def __init__(
        self,
        modalities: List[str],
        latent_dims: Dict[str, int],
        temperature: float = 1.0,
        lr: float = 0.01
    ):
        """
        Initialize gate computer.

        Args:
            modalities: List of modality names
            latent_dims: Dict mapping modality -> latent dimension
            temperature: Softmax temperature (lower = more peaked)
            lr: Learning rate
        """
        self.modalities = modalities
        self.n_modalities = len(modalities)
        self.latent_dims = latent_dims
        self.temperature = temperature
        self.lr = lr

        # Total dimension of concatenated latents
        self.total_dim = sum(latent_dims.get(m, 32) for m in modalities)

        # Weights: predicted latent -> gate relevance score
        self.W_gate = np.random.randn(self.n_modalities, self.total_dim) * 0.1
        self.bias = np.zeros(self.n_modalities)

    def compute(
        self,
        v_predicted: Dict[str, np.ndarray],
        context: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Compute anticipated gates from predicted states.

        Args:
            v_predicted: Predicted latent states per modality
            context: Optional context vector for modulation

        Returns:
            Anticipated gates (sum to 1.0)
        """
        # Concatenate predicted latents
        v_parts = []
        for m in self.modalities:
            dim = self.latent_dims.get(m, 32)
            v = v_predicted.get(m, np.zeros(dim))
            if len(v) != dim:
                v = np.zeros(dim)
            v_parts.append(v)

        v_concat = np.concatenate(v_parts)

        # Compute relevance scores
        scores = self.W_gate @ v_concat + self.bias

        # Context modulation (if provided)
        if context is not None and len(context) >= self.n_modalities:
            scores += 0.2 * context[:self.n_modalities]

        # Softmax with temperature -> gates (ALWAYS sum to 1.0)
        scores = scores / self.temperature
        exp_scores = np.exp(scores - np.max(scores))  # Numerical stability
        gates = exp_scores / np.sum(exp_scores)

        # Verify invariant
        assert np.isclose(np.sum(gates), 1.0), f"Gates must sum to 1.0, got {np.sum(gates)}"

        return gates

    def update(
        self,
        v_predicted: Dict[str, np.ndarray],
        target_gates: np.ndarray,
        computed_gates: np.ndarray
    ):
        """
        Learn to better predict gates.

        Args:
            v_predicted: Input predictions
            target_gates: What gates should have been
            computed_gates: What we computed
        """
        # Gate error
        error = target_gates - computed_gates

        # Concatenate inputs
        v_parts = []
        for m in self.modalities:
            dim = self.latent_dims.get(m, 32)
            v = v_predicted.get(m, np.zeros(dim))
            if len(v) != dim:
                v = np.zeros(dim)
            v_parts.append(v)
        v_concat = np.concatenate(v_parts)

        # Gradient update (simplified - ignores softmax Jacobian)
        dW = np.outer(error, v_concat)
        self.W_gate += self.lr * dW
        self.bias += self.lr * error


class TemporalRoutingPattern:
    """
    Learns recurring temporal patterns in routing decisions.

    Stores a library of observed gate sequences and uses
    pattern matching to predict upcoming gates.
    """

    def __init__(
        self,
        n_modalities: int,
        sequence_length: int = 5,
        n_patterns: int = 10,
        match_threshold: float = 0.5
    ):
        """
        Initialize temporal pattern learning.

        Args:
            n_modalities: Number of modalities
            sequence_length: Length of patterns to learn
            n_patterns: Maximum patterns to store
            match_threshold: Minimum score for pattern match
        """
        self.n_modalities = n_modalities
        self.sequence_length = sequence_length
        self.n_patterns = n_patterns
        self.match_threshold = match_threshold

        # Pattern library: stored routing sequences
        self.patterns = np.random.rand(n_patterns, sequence_length, n_modalities)
        # Normalize each timestep's gates
        for p in range(n_patterns):
            for t in range(sequence_length):
                self.patterns[p, t] /= np.sum(self.patterns[p, t])

        # Pattern usage counts (for prioritization and LRU replacement)
        self.usage_counts = np.zeros(n_patterns)

        # Confidence scores for each pattern
        self.pattern_confidence = np.ones(n_patterns) * 0.5

        # Current sequence buffer
        self.gate_history: List[np.ndarray] = []

    def record(self, gates: np.ndarray):
        """
        Record gate configuration to history.

        Args:
            gates: Current gate values (must sum to 1.0)
        """
        self.gate_history.append(gates.copy())

        # Keep buffer bounded
        if len(self.gate_history) > self.sequence_length * 2:
            self.gate_history.pop(0)

        # Check if we have a complete sequence to learn
        if len(self.gate_history) >= self.sequence_length:
            recent_seq = np.array(self.gate_history[-self.sequence_length:])
            self._maybe_learn_pattern(recent_seq)

    def predict_next(self) -> Optional[np.ndarray]:
        """
        Predict next gates based on pattern matching.

        Returns:
            Predicted gates or None if no good match
        """
        if len(self.gate_history) < self.sequence_length - 1:
            return None

        # Get recent history (all but the "next" step we're predicting)
        recent = np.array(self.gate_history[-(self.sequence_length-1):])

        # Find best matching pattern
        best_match = -1
        best_score = -np.inf

        for p in range(self.n_patterns):
            # Compare to pattern prefix (all but last timestep)
            pattern_prefix = self.patterns[p, :-1]

            # Similarity score (negative MSE)
            mse = np.mean((recent - pattern_prefix) ** 2)
            score = -mse

            # Bonus for frequently used patterns
            score += 0.1 * np.log1p(self.usage_counts[p])

            # Weight by pattern confidence
            score *= self.pattern_confidence[p]

            if score > best_score:
                best_score = score
                best_match = p

        # Check if match is good enough
        if best_match >= 0 and best_score > -self.match_threshold:
            self.usage_counts[best_match] += 1

            # Return predicted next gate (last timestep of pattern)
            predicted = self.patterns[best_match, -1].copy()

            # Ensure normalization
            predicted = np.maximum(predicted, 1e-8)  # Avoid zeros
            predicted /= np.sum(predicted)

            return predicted

        return None

    def _maybe_learn_pattern(self, gate_sequence: np.ndarray):
        """
        Potentially store a new routing pattern.

        Args:
            gate_sequence: Complete sequence of gates
        """
        if len(gate_sequence) != self.sequence_length:
            return

        # Check if this pattern is novel enough
        for p in range(self.n_patterns):
            mse = np.mean((gate_sequence - self.patterns[p]) ** 2)
            if mse < 0.1:  # Too similar to existing
                # Reinforce existing pattern
                self.usage_counts[p] += 0.5
                self.pattern_confidence[p] = min(1.0, self.pattern_confidence[p] + 0.05)
                return

        # Find slot for new pattern (LRU replacement)
        min_idx = np.argmin(self.usage_counts)

        # Store normalized sequence
        self.patterns[min_idx] = gate_sequence.copy()
        for t in range(self.sequence_length):
            self.patterns[min_idx, t] /= np.sum(self.patterns[min_idx, t])

        self.usage_counts[min_idx] = 1
        self.pattern_confidence[min_idx] = 0.5

    def learn_pattern(self, gate_sequence: np.ndarray):
        """
        Explicitly store a routing pattern.

        Args:
            gate_sequence: Sequence of gates to store
        """
        if len(gate_sequence) != self.sequence_length:
            return

        self._maybe_learn_pattern(gate_sequence)

    def update_confidence(self, pattern_idx: int, success: bool):
        """
        Update confidence in a pattern based on prediction success.

        Args:
            pattern_idx: Which pattern was used
            success: Whether prediction was accurate
        """
        if 0 <= pattern_idx < self.n_patterns:
            delta = 0.1 if success else -0.1
            self.pattern_confidence[pattern_idx] = np.clip(
                self.pattern_confidence[pattern_idx] + delta,
                0.1, 1.0
            )


class PredictiveRouter:
    """
    Complete predictive routing system.

    Combines forward models, anticipated gate computation, and
    temporal pattern learning to generate predictive routing adjustments.
    """

    def __init__(
        self,
        modalities: List[str],
        latent_dims: Dict[str, int],
        blend_alpha: float = 0.3,
        hidden_dim: int = 64,
        temperature: float = 1.0,
        sequence_length: int = 5,
        n_patterns: int = 10
    ):
        """
        Initialize predictive router.

        Args:
            modalities: List of modality names
            latent_dims: Dict mapping modality -> latent dimension
            blend_alpha: Weight for anticipated gates (0-1)
            hidden_dim: Hidden dimension for forward models
            temperature: Softmax temperature for gates
            sequence_length: Length of temporal patterns
            n_patterns: Number of patterns to store
        """
        self.modalities = modalities
        self.n_modalities = len(modalities)
        self.latent_dims = latent_dims
        self.blend_alpha = blend_alpha

        # Components
        self.forward_model = ForwardModel(
            modalities, latent_dims, hidden_dim
        )
        self.gate_computer = AnticipatedGateComputer(
            modalities, latent_dims, temperature
        )
        self.temporal = TemporalRoutingPattern(
            len(modalities), sequence_length, n_patterns
        )

        # State
        self.prev_prediction: Optional[Dict[str, np.ndarray]] = None
        self.prev_gates: Optional[np.ndarray] = None
        self.confidence: float = 0.5

        # Metrics
        self.total_predictions: int = 0
        self.prediction_errors: List[float] = []

    def step(
        self,
        v_current: Dict[str, np.ndarray],
        current_gates: np.ndarray,
        context: Optional[np.ndarray] = None
    ) -> RoutingPrediction:
        """
        Generate predictive routing adjustment.

        Args:
            v_current: Current latent states per modality
            current_gates: Current gate values (must sum to 1.0)
            context: Optional context vector

        Returns:
            RoutingPrediction with blended gates
        """
        self.total_predictions += 1

        # Verify input gates
        if not np.isclose(np.sum(current_gates), 1.0):
            current_gates = current_gates / np.sum(current_gates)

        # 1) Forward prediction: predict next latent states
        v_pred = self.forward_model.predict(v_current, current_gates)

        # 2) Compute anticipated gates from predictions
        g_anticipated = self.gate_computer.compute(v_pred, context)

        # 3) Check temporal patterns for additional prediction
        temporal_prediction = self.temporal.predict_next()
        if temporal_prediction is not None:
            # Blend forward-model gates with temporal pattern
            g_anticipated = 0.7 * g_anticipated + 0.3 * temporal_prediction
            g_anticipated /= np.sum(g_anticipated)  # Renormalize

        # 4) Blend with current gates
        # Scale blend factor by confidence
        alpha = self.blend_alpha * self.confidence
        g_blended = (1 - alpha) * current_gates + alpha * g_anticipated

        # CRITICAL: Ensure gates sum to 1.0
        g_blended = np.maximum(g_blended, 1e-8)  # Avoid zeros
        g_blended /= np.sum(g_blended)

        assert np.isclose(np.sum(g_blended), 1.0), \
            f"Blended gates must sum to 1.0, got {np.sum(g_blended)}"

        # 5) Record for temporal learning
        self.temporal.record(current_gates)

        # 6) Compute prediction error for learning (from previous step)
        pred_error = 0.0
        if self.prev_prediction is not None:
            for m in self.modalities:
                if m in v_current and m in self.prev_prediction:
                    pred_error += np.mean(
                        (v_current[m] - self.prev_prediction[m]) ** 2
                    )
            pred_error /= len(self.modalities)
            self.prediction_errors.append(pred_error)

            # Update confidence based on prediction accuracy
            # Good predictions -> higher confidence -> more aggressive blending
            self.confidence = 0.9 * self.confidence + 0.1 * np.exp(-pred_error)
            self.confidence = np.clip(self.confidence, 0.1, 0.9)

        # Store for next step
        self.prev_prediction = v_pred
        self.prev_gates = current_gates.copy()

        return RoutingPrediction(
            blended_gates=g_blended,
            gate_deltas=g_blended - current_gates,
            prediction_error=pred_error,
            confidence=self.confidence
        )

    def learn(
        self,
        v_actual: Dict[str, np.ndarray],
        v_input: Dict[str, np.ndarray]
    ):
        """
        Update forward models from actual outcomes.

        Args:
            v_actual: Actual observed latent states
            v_input: Input latents used for prediction
        """
        if self.prev_prediction is not None:
            error = self.forward_model.update(
                self.prev_prediction, v_actual, v_input
            )

            # Also update gate computer if we have previous gates
            if self.prev_gates is not None:
                # Use actual gates as "target" for learning
                actual_gates = self._compute_actual_gates(v_actual)
                if actual_gates is not None:
                    computed = self.gate_computer.compute(self.prev_prediction)
                    self.gate_computer.update(
                        self.prev_prediction, actual_gates, computed
                    )

    def _compute_actual_gates(
        self,
        v_actual: Dict[str, np.ndarray]
    ) -> Optional[np.ndarray]:
        """
        Compute what gates should have been given actual states.

        This is a heuristic based on state magnitudes.
        """
        magnitudes = []
        for m in self.modalities:
            if m in v_actual:
                magnitudes.append(np.linalg.norm(v_actual[m]))
            else:
                magnitudes.append(0.0)

        magnitudes = np.array(magnitudes)
        if np.sum(magnitudes) < 1e-8:
            return None

        # Softmax over magnitudes
        exp_mags = np.exp(magnitudes - np.max(magnitudes))
        return exp_mags / np.sum(exp_mags)

    def get_metrics(self) -> Dict:
        """Get performance metrics."""
        return {
            'total_predictions': self.total_predictions,
            'current_confidence': self.confidence,
            'mean_prediction_error': (
                np.mean(self.prediction_errors[-100:])
                if self.prediction_errors else 0.0
            ),
            'temporal_patterns_used': np.sum(self.temporal.usage_counts > 0)
        }

    def reset(self):
        """Reset state for new episode."""
        self.prev_prediction = None
        self.prev_gates = None
        self.confidence = 0.5
        self.temporal.gate_history.clear()

    def get_state(self) -> Dict:
        """Get serializable state."""
        return {
            'modalities': self.modalities,
            'latent_dims': self.latent_dims,
            'blend_alpha': self.blend_alpha,
            'confidence': self.confidence,
            'forward_model': self.forward_model.get_state(),
            'metrics': self.get_metrics()
        }
