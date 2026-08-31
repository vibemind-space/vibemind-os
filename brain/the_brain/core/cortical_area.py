"""
Cortical Area — wraps a single CanonicalMicrocircuit with area-level state.

Each CorticalArea represents one brain region (e.g. "language", "reasoning",
"memory").  It corresponds to one MoltBook community.

Responsibilities:
  - Wraps a CanonicalMicrocircuit (6-layer canonical column)
  - Tracks an activation level (float 0-1) that decays over time
  - Stores recent processing results ("thoughts") in a bounded deque
  - Records which specialty modules the area uses
  - Exposes state for the ResponseAgent to read

Activation update rule (exponential-moving-average style):
    output_mag = norm(column_output)
    activation = clamp(0.7 * activation + 0.3 * output_mag, 0, 1)

Decay rule (called by ``tick()`` when no new input arrives):
    activation = max(0, activation - decay_rate)
"""

import logging
import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import deque

from core.cortical_column import CanonicalMicrocircuit

logger = logging.getLogger('brain.cortical_area')


# ─── Config ──────────────────────────────────────────────────────────────

@dataclass
class CorticalAreaConfig:
    """Configuration for a single cortical area."""
    name: str
    specialty: List[str] = field(default_factory=list)
    layer_dim: int = 8
    decay_rate: float = 0.05
    max_thoughts: int = 100


# ─── CorticalArea ────────────────────────────────────────────────────────

class CorticalArea:
    """
    A named brain area backed by one CanonicalMicrocircuit.

    Parameters
    ----------
    config : CorticalAreaConfig
        Area configuration (name, specialty list, column dimensions, etc.).
    """

    def __init__(self, config: CorticalAreaConfig):
        self.config = config
        self.name: str = config.name
        self.specialty: List[str] = list(config.specialty)

        # Internal canonical microcircuit
        self._column = CanonicalMicrocircuit(layer_dim=config.layer_dim)

        # Area-level state
        self.activation: float = 0.0
        # Python 3.11 deque does NOT support slicing — always convert to list first
        self._thoughts: deque = deque(maxlen=config.max_thoughts)

        logger.info(
            "CorticalArea '%s' initialised: layer_dim=%d, specialties=%s",
            self.name, config.layer_dim, self.specialty,
        )

    # ── core processing ──────────────────────────────────────────────

    def receive_input(
        self,
        thalamic_input: np.ndarray,
        cortical_input: Optional[np.ndarray] = None,
        feedback: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Process input through the internal column, update activation,
        and store the result as a thought.

        Parameters
        ----------
        thalamic_input : ndarray (layer_dim,)
            Primary input signal.
        cortical_input : ndarray (layer_dim,) or None
            Lateral cortical input; defaults to zeros.
        feedback : ndarray (layer_dim,) or None
            Top-down feedback; defaults to zeros.

        Returns
        -------
        dict
            Column result dict augmented with ``activation``.
        """
        dim = self.config.layer_dim

        if cortical_input is None:
            cortical_input = np.zeros(dim)
        if feedback is None:
            feedback = np.zeros(dim)

        # Run through the canonical microcircuit
        result = self._column.process_column(thalamic_input, cortical_input, feedback)

        # Update activation (EMA blend of current activation and output magnitude)
        # result['output'] is a Python list — np.linalg.norm handles it fine
        output_mag = float(np.linalg.norm(result['output']))
        self.activation = min(1.0, max(0.0, self.activation * 0.7 + output_mag * 0.3))

        # Store thought
        thought: Dict[str, Any] = {
            'output': result['output'],
            'prediction': result['prediction'],
            'error_magnitude': result['error_magnitude'],
            'activation': self.activation,
        }
        self._thoughts.append(thought)

        # Return the full column result plus current activation
        result['activation'] = self.activation
        return result

    # ── time step (decay) ────────────────────────────────────────────

    def tick(self) -> None:
        """
        Advance one time-step without new input.

        Activation decays toward zero by ``config.decay_rate``.
        """
        self.activation = max(0.0, self.activation - self.config.decay_rate)

    # ── queries ──────────────────────────────────────────────────────

    def get_recent_thoughts(self, n: int = 10) -> List[Dict[str, Any]]:
        """
        Return the last *n* stored thoughts.

        GOTCHA: Python 3.11 deque does not support slicing.
        We convert to list first.
        """
        thought_list = list(self._thoughts)
        return thought_list[-n:]

    def get_state(self) -> Dict[str, Any]:
        """
        Return a summary of the area's current state.

        Used by the ResponseAgent and dashboard.
        """
        return {
            'name': self.name,
            'activation': round(self.activation, 6),
            'specialty': self.specialty,
            'avg_error': round(self._column.get_avg_error(), 6),
            'avg_activity': round(self._column.get_avg_activity(), 6),
            'thought_count': len(self._thoughts),
        }

    # ── reset ────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Zero activation and clear all stored thoughts."""
        self.activation = 0.0
        self._thoughts.clear()
        # Re-create the column so weights are fresh too
        self._column = CanonicalMicrocircuit(layer_dim=self.config.layer_dim)
        logger.info("CorticalArea '%s' reset.", self.name)

    # ── dunder ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"CorticalArea(name={self.name!r}, activation={self.activation:.4f}, "
            f"thoughts={len(self._thoughts)}, specialty={self.specialty})"
        )
