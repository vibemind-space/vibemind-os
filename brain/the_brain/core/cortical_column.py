"""
Cortical Column / Canonical Microcircuit

The fundamental computational unit of the cerebral cortex.

Douglas & Martin (2004) described a canonical microcircuit: a
stereotyped 6-layer column with specific inter-layer connectivity.
Each column receives thalamic input (Layer 4), integrates lateral
cortical input (Layers 2/3), produces subcortical output (Layer 5),
and sends feedback to the thalamus (Layer 6).

Three components:

1. CorticalLayer:
   A single layer with learned weights and a nonlinear activation.
   Combines feedforward input with lateral recurrent input.

2. CanonicalMicrocircuit:
   A complete 6-layer column wired according to the canonical
   connectivity pattern.  Computes feature detection, prediction,
   and prediction-error signals.

3. CorticalColumn (main):
   An ensemble of multiple canonical columns that share lateral
   connections and produce a combined output.
"""

import logging
import time
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger('brain.cortical_column')

# ─── Layer identifiers ──────────────────────────────────────────────────

LAYER_NAMES = ('L1', 'L2/3', 'L4', 'L5', 'L6', 'L6b')


# ─── Stats ───────────────────────────────────────────────────────────────

@dataclass
class CorticalColumnStats:
    """Cortical column ensemble statistics."""
    total_activations: int = 0
    avg_output_magnitude: float = 0.0
    prediction_errors: int = 0
    avg_layer_activity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_activations': self.total_activations,
            'avg_output_magnitude': round(self.avg_output_magnitude, 4),
            'prediction_errors': self.prediction_errors,
            'avg_layer_activity': round(self.avg_layer_activity, 4),
        }


# ─── Cortical Layer ─────────────────────────────────────────────────────

class CorticalLayer:
    """
    Single cortical layer with feedforward and lateral weights.

    Activation: tanh(W_ff @ input + W_lat @ lateral + bias)
    """

    def __init__(self, input_dim: int, output_dim: int, lateral_dim: int):
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.lateral_dim = lateral_dim

        scale_ff = np.sqrt(2.0 / (input_dim + output_dim))
        scale_lat = np.sqrt(2.0 / (lateral_dim + output_dim))

        self._W_ff = scale_ff * np.random.randn(output_dim, input_dim)
        self._W_lat = scale_lat * np.random.randn(output_dim, lateral_dim)
        self._bias = np.zeros(output_dim)
        self._activation: np.ndarray = np.zeros(output_dim)

    def activate(
        self,
        input_signal: np.ndarray,
        lateral_input: np.ndarray,
    ) -> np.ndarray:
        """
        Compute layer activation.

        Args:
            input_signal:  Feedforward input.
            lateral_input: Lateral / recurrent input.

        Returns:
            Activation vector (output_dim,).
        """
        pre = (
            self._W_ff @ input_signal[:self.input_dim]
            + self._W_lat @ lateral_input[:self.lateral_dim]
            + self._bias
        )
        self._activation = np.tanh(pre)
        return self._activation.copy()

    @property
    def activity(self) -> float:
        return float(np.mean(np.abs(self._activation)))


# ─── Canonical Microcircuit ──────────────────────────────────────────────

class CanonicalMicrocircuit:
    """
    6-layer cortical column with canonical connectivity.

    Signal flow (simplified):
        thalamic_input  -> L4 (input layer)
        L4              -> L2/3 (lateral integration)
        cortical_input  -> L2/3 (also receives lateral cortical)
        L2/3            -> L5  (output layer, subcortical)
        L2/3            -> L6  (feedback / prediction)
        feedback        -> L1  (modulatory, top-down)
        L6 prediction vs thalamic_input -> error_signal

    Layers are indexed 0-5 corresponding to LAYER_NAMES.
    """

    def __init__(self, layer_dim: int = 8, n_layers: int = 6):
        self.layer_dim = layer_dim
        self.n_layers = n_layers

        # Create layers. Every layer has the same dimensionality
        # for simplicity; real cortex varies.
        self.layers: List[CorticalLayer] = []
        for _ in range(n_layers):
            self.layers.append(CorticalLayer(layer_dim, layer_dim, layer_dim))

        self._error_history: deque = deque(maxlen=100)

    def process_column(
        self,
        thalamic_input: np.ndarray,
        cortical_input: np.ndarray,
        feedback: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Run one processing cycle through the 6-layer column.

        Args:
            thalamic_input: Input from thalamus (layer_dim,).
            cortical_input: Lateral cortical input (layer_dim,).
            feedback:       Top-down feedback (layer_dim,).

        Returns:
            Dict with layer_activations, output (L5), prediction (L6),
            error_signal.
        """
        dim = self.layer_dim
        zero = np.zeros(dim)

        # L1: modulatory — modulated by feedback
        l1 = self.layers[0].activate(feedback, zero)

        # L4 (index 2): thalamic input, modulated by L1
        l4 = self.layers[2].activate(thalamic_input, l1)

        # L2/3 (index 1): combines L4 output and cortical lateral
        l23 = self.layers[1].activate(l4, cortical_input)

        # L5 (index 3): output layer — driven by L2/3
        l5 = self.layers[3].activate(l23, zero)

        # L6 (index 4): prediction / thalamic feedback
        l6 = self.layers[4].activate(l23, zero)

        # L6b (index 5): deep feedback
        l6b = self.layers[5].activate(l6, feedback)

        # Prediction error: discrepancy between L6 prediction and
        # thalamic input (a la predictive coding)
        error_signal = thalamic_input[:dim] - l6
        error_mag = float(np.linalg.norm(error_signal))
        self._error_history.append(error_mag)

        activations = {
            'L1': l1.tolist(),
            'L2/3': l23.tolist(),
            'L4': l4.tolist(),
            'L5': l5.tolist(),
            'L6': l6.tolist(),
            'L6b': l6b.tolist(),
        }

        return {
            'layer_activations': activations,
            'output': l5.tolist(),
            'prediction': l6.tolist(),
            'error_signal': error_signal.tolist(),
            'error_magnitude': round(error_mag, 4),
        }

    def get_avg_error(self) -> float:
        if not self._error_history:
            return 0.0
        return float(np.mean(list(self._error_history)))

    def get_avg_activity(self) -> float:
        return float(np.mean([layer.activity for layer in self.layers]))


# ─── Main CorticalColumn class ──────────────────────────────────────────

class CorticalColumn:
    """
    Ensemble of canonical cortical columns.

    Multiple columns process the same input in parallel, each with
    slightly different weight initialisation.  The ensemble output
    is the mean across columns, providing robustness.

    Standard interface: process / get_state / get_stats / reset /
    to_dict / from_yaml.
    """

    def __init__(
        self,
        n_columns: int = 4,
        layer_dim: int = 8,
        n_layers: int = 6,
    ):
        self.n_columns = n_columns
        self.layer_dim = layer_dim
        self.n_layers = n_layers

        self.columns: List[CanonicalMicrocircuit] = [
            CanonicalMicrocircuit(layer_dim, n_layers)
            for _ in range(n_columns)
        ]

        self._stats = CorticalColumnStats()
        logger.info(
            "CorticalColumn initialised: n_columns=%d, layer_dim=%d, n_layers=%d",
            n_columns, layer_dim, n_layers,
        )

    # ── core processing ──────────────────────────────────────────────

    def process(
        self,
        thalamic_input: np.ndarray,
        cortical_input: Optional[np.ndarray] = None,
        feedback: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Process input through all columns and aggregate.

        Args:
            thalamic_input: Primary sensory input (layer_dim,).
            cortical_input: Lateral cortical input (layer_dim,), default zeros.
            feedback:       Top-down feedback (layer_dim,), default zeros.

        Returns:
            Dict with output, prediction, error_signal, per_column details.
        """
        dim = self.layer_dim
        if cortical_input is None:
            cortical_input = np.zeros(dim)
        if feedback is None:
            feedback = np.zeros(dim)

        outputs = []
        predictions = []
        errors = []
        per_column = []

        for i, col in enumerate(self.columns):
            result = col.process_column(thalamic_input, cortical_input, feedback)
            outputs.append(np.array(result['output']))
            predictions.append(np.array(result['prediction']))
            errors.append(np.array(result['error_signal']))
            per_column.append({
                'column_index': i,
                'error_magnitude': result['error_magnitude'],
            })

        mean_output = np.mean(outputs, axis=0)
        mean_prediction = np.mean(predictions, axis=0)
        mean_error = np.mean(errors, axis=0)
        output_mag = float(np.linalg.norm(mean_output))
        error_mag = float(np.linalg.norm(mean_error))

        # Track prediction errors (when error exceeds threshold)
        if error_mag > 0.5:
            self._stats.prediction_errors += 1

        # Running average of output magnitude
        self._stats.total_activations += 1
        n = self._stats.total_activations
        self._stats.avg_output_magnitude += (
            output_mag - self._stats.avg_output_magnitude
        ) / n

        # Average layer activity across all columns
        activities = [col.get_avg_activity() for col in self.columns]
        self._stats.avg_layer_activity += (
            float(np.mean(activities)) - self._stats.avg_layer_activity
        ) / n

        logger.debug(
            "CorticalColumn cycle %d: output_mag=%.3f error_mag=%.3f",
            n, output_mag, error_mag,
        )

        return {
            'output': mean_output.tolist(),
            'prediction': mean_prediction.tolist(),
            'error_signal': mean_error.tolist(),
            'output_magnitude': round(output_mag, 4),
            'error_magnitude': round(error_mag, 4),
            'per_column': per_column,
        }

    def predictive_coding_signal(
        self,
        top_down_prediction: np.ndarray,
        bottom_up_input: np.ndarray,
    ) -> Dict[str, float]:
        """
        Predictive coding in cortical hierarchy (Rao & Ballard, 1999).

        Cortical columns implement predictive coding: higher layers send
        top-down predictions, lower layers compute prediction errors.
        Only the errors propagate upward, implementing efficient coding.
        This is a candidate unifying theory of cortical computation.

        Args:
            top_down_prediction: Prediction from higher cortical area
            bottom_up_input: Actual sensory input from lower area

        Returns:
            Dict with prediction_error, precision, update_signal
        """
        prediction = np.asarray(top_down_prediction, dtype=np.float32)
        sensory = np.asarray(bottom_up_input, dtype=np.float32)

        min_len = min(len(prediction), len(sensory))
        prediction = prediction[:min_len]
        sensory = sensory[:min_len]

        # Prediction error: bottom-up - top-down
        error = sensory - prediction
        error_magnitude = float(np.mean(np.abs(error))) if min_len > 0 else 0.0

        # Precision: confidence in prediction (inverse variance)
        variance = float(np.var(error)) if min_len > 1 else 0.5
        precision = max(0.0, 1.0 - variance * 2.0)

        # Update signal: precision-weighted prediction error
        update_signal = error_magnitude * precision

        return {
            'prediction_error': round(error_magnitude, 4),
            'precision': round(precision, 4),
            'update_signal': round(min(1.0, update_signal), 4),
            'model_accuracy': round(max(0.0, 1.0 - error_magnitude), 4),
        }

    # ── standard interface ───────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'n_columns': self.n_columns,
            'layer_dim': self.layer_dim,
            'avg_column_errors': [
                round(col.get_avg_error(), 4) for col in self.columns
            ],
        }

    def get_stats(self) -> CorticalColumnStats:
        return self._stats

    def reset(self):
        self._stats = CorticalColumnStats()
        self.columns = [
            CanonicalMicrocircuit(self.layer_dim, self.n_layers)
            for _ in range(self.n_columns)
        ]

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'CorticalColumn':
        section = config.get('cortical_column', {})
        return cls(
            n_columns=section.get('n_columns', 4),
            layer_dim=section.get('layer_dim', 8),
            n_layers=section.get('n_layers', 6),
        )
