"""
Orbitofrontal Cortex Module

Subjective value computation, outcome prediction, and flexible
stimulus-reward association updating for decision-making.

Neuroscience basis:
- Padoa-Schioppa & Assad (2006): OFC neurons encode subjective value
- Wallis (2007): OFC computes expected outcome values for decisions
- Schoenbaum et al. (2009): OFC represents "state space" for task structure
- Rudebeck & Murray (2014): OFC for credit assignment and value updating

Integration:
- Input: Feature vectors from PFC, reward history from VTA/NAcc
- Output: Subjective values to BG/ACC, predicted outcomes to PFC
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger('brain.ofc')


@dataclass
class OFCStats:
    """Orbitofrontal cortex statistics."""
    total_valuations: int = 0
    avg_subjective_value: float = 0.0
    reversals_detected: int = 0
    avg_decision_confidence: float = 0.0
    total_updates: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_valuations': self.total_valuations,
            'avg_subjective_value': round(self.avg_subjective_value, 3),
            'reversals_detected': self.reversals_detected,
            'avg_decision_confidence': round(self.avg_decision_confidence, 3),
            'total_updates': self.total_updates,
        }


class ValueComputer:
    """
    Computes subjective value of options.
    Subjective value = expected_reward * probability - effort_cost - risk_penalty
    where risk_penalty = risk_aversion * risk^2 (quadratic risk penalty).
    Reward history biases value (experienced rewards increase value).
    """

    def __init__(self, risk_aversion: float = 0.5, reward_bias: float = 0.3):
        self.risk_aversion = risk_aversion
        self.reward_bias = reward_bias
        self._value_history = deque(maxlen=100)

    def compute_value(self, features: np.ndarray, reward_history: float = 0.0,
                      effort_cost: float = 0.0, risk: float = 0.0) -> float:
        """Compute subjective value. Returns float (can be negative)."""
        features = np.asarray(features, dtype=np.float64).flatten()
        feature_signal = float(np.mean(np.clip(features, -1.0, 1.0)))
        probability = 1.0 / (1.0 + np.exp(-feature_signal * 3.0))
        expected_reward = ((1.0 - self.reward_bias) * probability +
                           self.reward_bias * max(0.0, min(1.0, reward_history)))
        risk_penalty = self.risk_aversion * (risk ** 2)
        subjective_value = expected_reward * probability - effort_cost - risk_penalty
        self._value_history.append(subjective_value)
        return float(subjective_value)

    def get_avg_value(self) -> float:
        if not self._value_history:
            return 0.0
        return float(np.mean(list(self._value_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'risk_aversion': self.risk_aversion,
            'reward_bias': self.reward_bias,
            'avg_value': round(self.get_avg_value(), 3),
        }


class OutcomePredictor:
    """
    Predicts expected outcomes via learned action-outcome mappings.
    Uses a simple linear model updated by gradient descent.
    """

    def __init__(self, n_features: int = 8, learning_rate: float = 0.1):
        self.n_features = n_features
        self.learning_rate = learning_rate
        self._weights_reward = np.zeros(n_features)
        self._weights_effort = np.zeros(n_features)
        self._update_count = 0
        self._prediction_errors = deque(maxlen=50)

    def _pad(self, action_features: np.ndarray) -> np.ndarray:
        feats = np.asarray(action_features, dtype=np.float64).flatten()
        padded = np.zeros(self.n_features)
        n = min(len(feats), self.n_features)
        padded[:n] = feats[:n]
        return padded

    def predict(self, action_features: np.ndarray) -> Dict[str, float]:
        """Returns predicted_reward, predicted_effort, prediction_confidence."""
        padded = self._pad(action_features)
        predicted_reward = float(np.dot(self._weights_reward, padded))
        predicted_effort = float(np.dot(self._weights_effort, padded))
        confidence = min(1.0, self._update_count / 20.0)
        if self._prediction_errors:
            recent_error = float(np.mean(list(self._prediction_errors)[-10:]))
            confidence *= max(0.1, 1.0 - recent_error)
        return {
            'predicted_reward': round(predicted_reward, 4),
            'predicted_effort': round(max(0.0, predicted_effort), 4),
            'prediction_confidence': round(confidence, 3),
        }

    def update(self, action_features: np.ndarray, actual_outcome: float) -> None:
        """Update model with actual outcome via gradient descent."""
        padded = self._pad(action_features)
        predicted = float(np.dot(self._weights_reward, padded))
        error = actual_outcome - predicted
        self._prediction_errors.append(abs(error))
        self._weights_reward += self.learning_rate * error * padded
        self._update_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_features': self.n_features,
            'update_count': self._update_count,
            'weights_norm': round(float(np.linalg.norm(self._weights_reward)), 3),
        }


class ValueUpdater:
    """
    Flexibly updates stimulus-reward associations with reversal learning.
    When outcome sign flips, learning rate is amplified by reversal_sensitivity.
    Key OFC function: not getting stuck on old values.
    """

    def __init__(self, learning_rate: float = 0.1,
                 reversal_sensitivity: float = 2.0, value_decay: float = 0.01):
        self.learning_rate = learning_rate
        self.reversal_sensitivity = reversal_sensitivity
        self.value_decay = value_decay
        self._associations: Dict[str, float] = {}
        self._reversal_count = 0

    def update_association(self, stimulus_id: str, outcome: float) -> Dict[str, float]:
        """Update stimulus-reward association. Returns new_value, value_change, reversal_detected."""
        old_value = self._associations.get(stimulus_id, 0.0)
        reversal_detected = False
        lr = self.learning_rate

        if abs(old_value) > 0.05:
            current_sign = 1.0 if outcome > 0 else (-1.0 if outcome < 0 else 0.0)
            stored_sign = 1.0 if old_value > 0 else (-1.0 if old_value < 0 else 0.0)
            if current_sign != 0 and stored_sign != 0 and current_sign != stored_sign:
                reversal_detected = True
                lr *= self.reversal_sensitivity
                self._reversal_count += 1

        value_change = lr * (outcome - old_value)
        new_value = old_value + value_change

        # Decay all other associations toward zero
        for sid in self._associations:
            if sid != stimulus_id:
                self._associations[sid] *= (1.0 - self.value_decay)

        self._associations[stimulus_id] = new_value
        return {
            'new_value': round(new_value, 4),
            'value_change': round(value_change, 4),
            'reversal_detected': reversal_detected,
        }

    @property
    def reversal_count(self) -> int:
        return self._reversal_count

    def get_value(self, stimulus_id: str) -> float:
        return self._associations.get(stimulus_id, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        top = {k: round(v, 3) for k, v in
               sorted(self._associations.items(),
                      key=lambda x: abs(x[1]), reverse=True)[:10]}
        return {
            'n_associations': len(self._associations),
            'reversal_count': self._reversal_count,
            'top_values': top,
        }


class DecisionVariableEncoder:
    """
    Encodes decision-relevant variables across multiple options.
    Computes relative advantages, best option, and choice difficulty.
    """

    def __init__(self):
        self._decision_history = deque(maxlen=50)

    def encode(self, options: List[Dict[str, float]]) -> Dict[str, Any]:
        """Encode decision variables. Returns best_option_idx, value_difference,
        decision_confidence, choice_difficulty."""
        if not options:
            return {'best_option_idx': -1, 'value_difference': 0.0,
                    'decision_confidence': 0.0, 'choice_difficulty': 1.0}

        net_values = []
        for opt in options:
            net = (opt.get('value', 0.0) - 0.5 * opt.get('effort', 0.0)
                   - 0.3 * opt.get('risk', 0.0) + 0.2 * opt.get('familiarity', 0.5))
            net_values.append(net)

        net_values = np.array(net_values)
        best_idx = int(np.argmax(net_values))
        sorted_vals = np.sort(net_values)[::-1]
        value_diff = float(sorted_vals[0] - sorted_vals[1]) if len(sorted_vals) >= 2 else float(sorted_vals[0])
        decision_confidence = float(1.0 / (1.0 + np.exp(-value_diff * 5.0)))
        self._decision_history.append(decision_confidence)

        return {
            'best_option_idx': best_idx,
            'value_difference': round(value_diff, 4),
            'decision_confidence': round(decision_confidence, 3),
            'choice_difficulty': round(1.0 - decision_confidence, 3),
        }

    def get_avg_confidence(self) -> float:
        if not self._decision_history:
            return 0.0
        return float(np.mean(list(self._decision_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'avg_confidence': round(self.get_avg_confidence(), 3),
            'n_decisions': len(self._decision_history),
        }


class OrbitofrontalCortex:
    """
    Complete Orbitofrontal Cortex module.

    Integrates ValueComputer, OutcomePredictor, ValueUpdater, and
    DecisionVariableEncoder for subjective valuation and flexible
    decision-making.
    """

    def __init__(self, n_features: int = 8, learning_rate: float = 0.1,
                 risk_aversion: float = 0.5, reversal_sensitivity: float = 2.0,
                 value_decay: float = 0.01):
        self.n_features = n_features
        self.value_computer = ValueComputer(risk_aversion=risk_aversion)
        self.outcome_predictor = OutcomePredictor(
            n_features=n_features, learning_rate=learning_rate)
        self.value_updater = ValueUpdater(
            learning_rate=learning_rate,
            reversal_sensitivity=reversal_sensitivity,
            value_decay=value_decay)
        self.decision_encoder = DecisionVariableEncoder()
        self._stats = OFCStats()
        self._value_accumulator = 0.0

    def process(self, features: np.ndarray, reward_history: float = 0.0,
                effort_cost: float = 0.0, risk: float = 0.0,
                options: Optional[List[Dict[str, float]]] = None) -> Dict[str, Any]:
        """Full OFC processing. Returns subjective_value, predicted_outcome,
        decision_variables, value_confidence."""
        subjective_value = self.value_computer.compute_value(
            features, reward_history, effort_cost, risk)
        predicted_outcome = self.outcome_predictor.predict(features)
        decision_variables = self.decision_encoder.encode(options) if options else {}
        value_confidence = predicted_outcome['prediction_confidence']

        self._stats.total_valuations += 1
        self._value_accumulator += subjective_value
        self._stats.avg_subjective_value = (
            self._value_accumulator / self._stats.total_valuations)
        self._stats.reversals_detected = self.value_updater.reversal_count
        self._stats.avg_decision_confidence = self.decision_encoder.get_avg_confidence()

        return {
            'subjective_value': round(subjective_value, 4),
            'predicted_outcome': predicted_outcome,
            'decision_variables': decision_variables,
            'value_confidence': round(value_confidence, 3),
        }

    def update_from_outcome(self, action_features: np.ndarray,
                            actual_reward: float) -> None:
        """Update predictor and associations from observed outcome."""
        self.outcome_predictor.update(action_features, actual_reward)
        feats = np.asarray(action_features, dtype=np.float64).flatten()
        stimulus_id = f"stim_{hash(feats.tobytes()) % 100000}"
        self.value_updater.update_association(stimulus_id, actual_reward)
        self._stats.total_updates += 1
        self._stats.reversals_detected = self.value_updater.reversal_count

    def reversal_learning_signal(
        self,
        expected_outcome: float,
        actual_outcome: float,
    ) -> Dict[str, float]:
        """
        Reversal learning computation (Rolls, 2000).

        OFC is critical for reversal learning — updating behavior when
        reward contingencies change. OFC lesions cause perseveration
        (continuing to choose previously-rewarded options despite reversal).
        This signal drives flexible behavior.

        Args:
            expected_outcome: What was expected [0, 1]
            actual_outcome: What actually happened [0, 1]

        Returns:
            Dict with reversal_signal, should_reverse, confidence_drop
        """
        # Outcome prediction error
        ope = actual_outcome - expected_outcome

        # Reversal signal: strong when expectations violated
        reversal_signal = min(1.0, abs(ope) * 2.0)

        # Should reverse strategy if negative surprise is large
        should_reverse = ope < -0.3

        # Confidence in current strategy drops with negative OPE
        confidence_drop = max(0.0, -ope)

        return {
            'reversal_signal': round(reversal_signal, 4),
            'outcome_prediction_error': round(ope, 4),
            'should_reverse': should_reverse,
            'confidence_drop': round(confidence_drop, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'value_computer': self.value_computer.to_dict(),
            'outcome_predictor': self.outcome_predictor.to_dict(),
            'value_updater': self.value_updater.to_dict(),
            'decision_encoder': self.decision_encoder.to_dict(),
        }

    def get_stats(self) -> OFCStats:
        return self._stats

    def reset(self):
        self._stats = OFCStats()
        self._value_accumulator = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'OrbitofrontalCortex':
        ofc = config.get('orbitofrontal_cortex', {})
        return cls(
            n_features=ofc.get('n_features', 8),
            learning_rate=ofc.get('learning_rate', 0.1),
            risk_aversion=ofc.get('risk_aversion', 0.5),
            reversal_sensitivity=ofc.get('reversal_sensitivity', 2.0),
            value_decay=ofc.get('value_decay', 0.01),
        )
