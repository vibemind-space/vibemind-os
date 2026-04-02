"""
Predictive Coding Infrastructure (PHASE 2)

Implements hierarchical predictive coding across all 3 layers:
- Each layer makes predictions about its inputs
- Prediction errors drive learning and attention
- Errors propagate up and down the hierarchy
- Curiosity-driven exploration based on prediction errors

Based on the Free Energy Principle and predictive processing:
- Brain constantly predicts sensory input
- Prediction errors signal novelty/importance
- Learning minimizes prediction error over time
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class PredictionError:
    """
    Prediction error with metadata
    """
    error_magnitude: float  # Scalar error magnitude
    error_vector: Optional[np.ndarray] = None  # Full error vector (optional)
    confidence: float = 1.0  # Confidence in the prediction
    surprise_level: str = 'normal'  # 'low', 'normal', 'high', 'extreme'

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        result = {
            'error_magnitude': float(self.error_magnitude),
            'confidence': float(self.confidence),
            'surprise_level': self.surprise_level
        }
        if self.error_vector is not None:
            result['error_vector'] = self.error_vector.tolist()
        return result


class PredictiveLayer(ABC):
    """
    Base class for predictive layers

    All layers in the hierarchy implement this interface:
    - Make predictions about their inputs
    - Compute prediction errors
    - Update predictions based on errors
    """

    def __init__(
        self,
        layer_name: str,
        prediction_history_size: int = 100
    ):
        """
        Initialize predictive layer

        Args:
            layer_name: Name of this layer
            prediction_history_size: How many PEs to store
        """
        self.layer_name = layer_name
        self.prediction_history_size = prediction_history_size

        # History
        self.prediction_errors: List[PredictionError] = []
        self.prediction_count = 0

    @abstractmethod
    def predict(self, context: Dict) -> Dict:
        """
        Make a prediction given context

        Args:
            context: Context information for prediction

        Returns:
            Dictionary with prediction
        """
        pass

    @abstractmethod
    def compute_error(
        self,
        prediction: Dict,
        actual: Dict
    ) -> PredictionError:
        """
        Compute prediction error

        Args:
            prediction: What was predicted
            actual: What actually happened

        Returns:
            PredictionError object
        """
        pass

    def record_error(self, error: PredictionError):
        """Record a prediction error"""
        self.prediction_errors.append(error)

        # Keep only recent history
        if len(self.prediction_errors) > self.prediction_history_size:
            self.prediction_errors.pop(0)

        self.prediction_count += 1

    def get_recent_error_stats(self, window: int = 10) -> Dict:
        """Get statistics about recent prediction errors"""
        if not self.prediction_errors:
            return {
                'mean_error': 0.0,
                'std_error': 0.0,
                'surprise_rate': 0.0
            }

        recent = self.prediction_errors[-window:]
        errors = [pe.error_magnitude for pe in recent]
        surprises = [pe for pe in recent if pe.surprise_level in ['high', 'extreme']]

        return {
            'mean_error': np.mean(errors),
            'std_error': np.std(errors),
            'surprise_rate': len(surprises) / len(recent)
        }

    def determine_surprise_level(self, error_magnitude: float) -> str:
        """
        Determine surprise level based on historical errors

        Args:
            error_magnitude: Current error magnitude

        Returns:
            'low', 'normal', 'high', or 'extreme'
        """
        if len(self.prediction_errors) < 5:
            return 'normal'  # Not enough history

        # Get recent error distribution
        recent_errors = [pe.error_magnitude for pe in self.prediction_errors[-20:]]
        mean_error = np.mean(recent_errors)
        std_error = np.std(recent_errors)

        if std_error < 1e-6:
            return 'normal'  # No variation

        # Z-score based surprise
        z_score = (error_magnitude - mean_error) / std_error

        if z_score < -0.5:
            return 'low'
        elif z_score < 1.0:
            return 'normal'
        elif z_score < 2.0:
            return 'high'
        else:
            return 'extreme'


class Layer1Predictor(PredictiveLayer):
    """
    Layer 1 predictor: Predicts task features

    Given recent task history, predicts:
    - Task type
    - Complexity
    - Urgency
    """

    def __init__(self):
        super().__init__("Layer1_TaskFeatures")

        # Simple frequency-based predictor
        self.task_type_history: List[str] = []
        self.complexity_history: List[float] = []
        self.urgency_history: List[float] = []

    def predict(self, context: Dict) -> Dict:
        """
        Predict next task features based on history

        Args:
            context: Should contain 'recent_tasks' if available

        Returns:
            Predicted task features
        """
        # Default predictions
        predicted = {
            'task_type': 'unknown',
            'complexity': 0.5,
            'urgency': 0.5
        }

        # If we have history, predict from it
        if self.task_type_history:
            # Most common recent task type
            from collections import Counter
            type_counts = Counter(self.task_type_history[-10:])
            predicted['task_type'] = type_counts.most_common(1)[0][0]

        if self.complexity_history:
            predicted['complexity'] = np.mean(self.complexity_history[-10:])

        if self.urgency_history:
            predicted['urgency'] = np.mean(self.urgency_history[-10:])

        return predicted

    def compute_error(
        self,
        prediction: Dict,
        actual: Dict
    ) -> PredictionError:
        """
        Compute error between predicted and actual task features

        Args:
            prediction: Predicted features
            actual: Actual features

        Returns:
            PredictionError
        """
        # Compute error for each feature
        errors = []

        # Task type (binary: correct or not)
        if 'task_type' in actual and 'task_type' in prediction:
            type_error = 0.0 if prediction['task_type'] == actual['task_type'] else 1.0
            errors.append(type_error)

        # Complexity (continuous)
        if 'complexity' in actual and 'complexity' in prediction:
            complexity_error = abs(prediction['complexity'] - actual['complexity'])
            errors.append(complexity_error)

        # Urgency (continuous)
        if 'urgency' in actual and 'urgency' in prediction:
            urgency_error = abs(prediction['urgency'] - actual['urgency'])
            errors.append(urgency_error)

        # Overall error magnitude
        error_magnitude = np.mean(errors) if errors else 0.0

        # Determine surprise level
        surprise_level = self.determine_surprise_level(error_magnitude)

        # Create prediction error
        pe = PredictionError(
            error_magnitude=error_magnitude,
            error_vector=np.array(errors),
            surprise_level=surprise_level
        )

        # Record it
        self.record_error(pe)

        # Update history
        if 'task_type' in actual:
            self.task_type_history.append(actual['task_type'])
        if 'complexity' in actual:
            self.complexity_history.append(actual['complexity'])
        if 'urgency' in actual:
            self.urgency_history.append(actual['urgency'])

        return pe


class Layer3Predictor(PredictiveLayer):
    """
    Layer 3 predictor: Predicts decision outcomes

    Given decision and context, predicts:
    - Success probability
    - Execution time
    """

    def __init__(self):
        super().__init__("Layer3_DecisionOutcomes")

        # History per decision type
        self.decision_history: Dict[str, List[Dict]] = {}

    def predict(self, context: Dict) -> Dict:
        """
        Predict outcome of a decision

        Args:
            context: Should contain 'decision_type', 'task_type', 'confidence'

        Returns:
            Predicted outcome
        """
        decision_type = context.get('decision_type', 'unknown')

        # Default prediction
        predicted = {
            'success_probability': 0.5,
            'execution_time_ms': 1000.0
        }

        # If we have history for this decision type
        if decision_type in self.decision_history:
            history = self.decision_history[decision_type]
            if history:
                # Average success rate
                successes = [h['success'] for h in history if 'success' in h]
                if successes:
                    predicted['success_probability'] = np.mean(successes)

                # Average execution time
                times = [h['execution_time_ms'] for h in history if 'execution_time_ms' in h]
                if times:
                    predicted['execution_time_ms'] = np.mean(times)

        return predicted

    def compute_error(
        self,
        prediction: Dict,
        actual: Dict
    ) -> PredictionError:
        """
        Compute error between predicted and actual outcomes

        Args:
            prediction: Predicted outcome
            actual: Actual outcome

        Returns:
            PredictionError
        """
        errors = []

        # Success prediction error
        if 'success_probability' in prediction and 'success' in actual:
            actual_success = 1.0 if actual['success'] else 0.0
            success_error = abs(prediction['success_probability'] - actual_success)
            errors.append(success_error)

        # Execution time error (normalized)
        if 'execution_time_ms' in prediction and 'execution_time_ms' in actual:
            time_error = abs(prediction['execution_time_ms'] - actual['execution_time_ms'])
            # Normalize by predicted time to get relative error
            if prediction['execution_time_ms'] > 0:
                time_error = time_error / prediction['execution_time_ms']
            errors.append(min(time_error, 2.0))  # Cap at 2x

        # Overall error
        error_magnitude = np.mean(errors) if errors else 0.0

        # Determine surprise
        surprise_level = self.determine_surprise_level(error_magnitude)

        # Create prediction error
        pe = PredictionError(
            error_magnitude=error_magnitude,
            error_vector=np.array(errors),
            surprise_level=surprise_level
        )

        # Record it
        self.record_error(pe)

        # Update history
        decision_type = actual.get('decision_type', 'unknown')
        if decision_type not in self.decision_history:
            self.decision_history[decision_type] = []

        self.decision_history[decision_type].append(actual)

        # Keep only recent history per decision type
        if len(self.decision_history[decision_type]) > 50:
            self.decision_history[decision_type].pop(0)

        return pe


class HierarchicalPredictiveCoding:
    """
    Coordinates predictive coding across all layers

    Features:
    - Error propagation up and down the hierarchy
    - Curiosity-driven attention allocation
    - Meta-level surprise tracking
    """

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'HierarchicalPredictiveCoding':
        """Create HierarchicalPredictiveCoding from YAML config dict (P5.71)."""
        pc = yaml_config.get('predictive_coding', {})
        instance = cls()
        history_size = pc.get('prediction_history_size', 100)
        instance.layer1_predictor.prediction_history_size = history_size
        instance.layer3_predictor.prediction_history_size = history_size
        return instance

    def __init__(self):
        """Initialize hierarchical predictive coding"""
        self.layer1_predictor = Layer1Predictor()
        self.layer3_predictor = Layer3Predictor()

        # Meta-level tracking
        self.total_predictions = 0
        self.high_surprise_events: List[Dict] = []

    def predict_task_features(self, context: Dict) -> Tuple[Dict, Dict]:
        """
        Make Layer 1 prediction about task features

        Args:
            context: Context for prediction

        Returns:
            (prediction, prediction_context)
        """
        prediction = self.layer1_predictor.predict(context)

        # Add context about prediction quality
        stats = self.layer1_predictor.get_recent_error_stats()
        prediction_context = {
            'prediction': prediction,
            'mean_recent_error': stats['mean_error'],
            'surprise_rate': stats['surprise_rate']
        }

        return prediction, prediction_context

    def update_task_prediction(
        self,
        prediction: Dict,
        actual: Dict
    ) -> PredictionError:
        """
        Update Layer 1 prediction with actual task features

        Args:
            prediction: What was predicted
            actual: What actually happened

        Returns:
            PredictionError
        """
        pe = self.layer1_predictor.compute_error(prediction, actual)

        # Track high surprise events
        if pe.surprise_level in ['high', 'extreme']:
            self.high_surprise_events.append({
                'layer': 'layer1',
                'error_magnitude': pe.error_magnitude,
                'surprise_level': pe.surprise_level,
                'prediction': prediction,
                'actual': actual
            })

        self.total_predictions += 1

        return pe

    def predict_decision_outcome(self, context: Dict) -> Tuple[Dict, Dict]:
        """
        Make Layer 3 prediction about decision outcome

        Args:
            context: Context for prediction (decision_type, task_type, etc.)

        Returns:
            (prediction, prediction_context)
        """
        prediction = self.layer3_predictor.predict(context)

        # Add context
        stats = self.layer3_predictor.get_recent_error_stats()
        prediction_context = {
            'prediction': prediction,
            'mean_recent_error': stats['mean_error'],
            'surprise_rate': stats['surprise_rate']
        }

        return prediction, prediction_context

    def update_decision_prediction(
        self,
        prediction: Dict,
        actual: Dict
    ) -> PredictionError:
        """
        Update Layer 3 prediction with actual outcome

        Args:
            prediction: What was predicted
            actual: What actually happened (must include 'decision_type')

        Returns:
            PredictionError
        """
        pe = self.layer3_predictor.compute_error(prediction, actual)

        # Track high surprise events
        if pe.surprise_level in ['high', 'extreme']:
            self.high_surprise_events.append({
                'layer': 'layer3',
                'error_magnitude': pe.error_magnitude,
                'surprise_level': pe.surprise_level,
                'prediction': prediction,
                'actual': actual
            })

        self.total_predictions += 1

        return pe

    def get_curiosity_signal(self) -> Dict:
        """
        Get curiosity signal based on prediction errors

        High prediction errors indicate novel/interesting situations
        that deserve more attention and exploration.

        Returns:
            Curiosity signal with recommendations
        """
        # Get recent errors from both layers
        l1_stats = self.layer1_predictor.get_recent_error_stats()
        l3_stats = self.layer3_predictor.get_recent_error_stats()

        # Overall curiosity level
        avg_error = (l1_stats['mean_error'] + l3_stats['mean_error']) / 2
        avg_surprise = (l1_stats['surprise_rate'] + l3_stats['surprise_rate']) / 2

        # Determine curiosity level
        if avg_surprise > 0.5 or avg_error > 0.7:
            curiosity_level = 'high'
            recommendation = 'explore'  # Explore new strategies
        elif avg_surprise > 0.2 or avg_error > 0.4:
            curiosity_level = 'moderate'
            recommendation = 'balanced'  # Mix of exploration and exploitation
        else:
            curiosity_level = 'low'
            recommendation = 'exploit'  # Stick with known strategies

        return {
            'curiosity_level': curiosity_level,
            'recommendation': recommendation,
            'layer1_error': l1_stats['mean_error'],
            'layer3_error': l3_stats['mean_error'],
            'layer1_surprise_rate': l1_stats['surprise_rate'],
            'layer3_surprise_rate': l3_stats['surprise_rate'],
            'total_predictions': self.total_predictions,
            'high_surprise_events': len(self.high_surprise_events)
        }

    def get_statistics(self) -> Dict:
        """Get statistics from predictive coding system"""
        return {
            'total_predictions': self.total_predictions,
            'layer1': {
                'prediction_count': self.layer1_predictor.prediction_count,
                'recent_stats': self.layer1_predictor.get_recent_error_stats()
            },
            'layer3': {
                'prediction_count': self.layer3_predictor.prediction_count,
                'recent_stats': self.layer3_predictor.get_recent_error_stats()
            },
            'high_surprise_events': len(self.high_surprise_events),
            'curiosity': self.get_curiosity_signal()
        }


if __name__ == "__main__":
    print("=" * 70)
    print("PREDICTIVE CODING INFRASTRUCTURE (PHASE 2)")
    print("=" * 70)
    print()
    print("This module implements hierarchical predictive coding:")
    print("  - Layer 1: Predicts task features")
    print("  - Layer 3: Predicts decision outcomes")
    print("  - Hierarchical error propagation")
    print("  - Curiosity-driven exploration")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_predictive_coding.py")
    print()
    print("=" * 70)
