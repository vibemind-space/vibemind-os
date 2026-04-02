"""
ResponseAgent -- reads cortical area activations and produces deliberation output.

The ResponseAgent is the "reader" in the brain's architecture:
  1. Reads activation levels from all cortical areas
  2. Selects the top-K most activated areas (above threshold)
  3. Gathers their recent thoughts
  4. Computes confidence from the activation distribution
  5. Records to KotlinGraph episodic memory (optional)
  6. Returns a structured deliberation result for LLM verbalization

Confidence formula:
    confidence = mean(activations)
    if len(activations) > 1:
        confidence = min(1.0, confidence + std(activations) * 0.5)

This encourages selecting areas with high *and* diverse activation levels --
a spread of strongly-activated areas boosts confidence more than a single one.
"""

import logging
import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from core.cortical_area import CorticalArea
from core.kotlin_graph import KotlinGraph

logger = logging.getLogger('brain.response_agent')


# ---- Config ---------------------------------------------------------------

@dataclass
class ResponseAgentConfig:
    """Configuration for the ResponseAgent."""
    top_k: int = 3
    min_activation: float = 0.01


# ---- ResponseAgent --------------------------------------------------------

class ResponseAgent:
    """
    Reads cortical area activations, selects the top-K areas, gathers their
    thoughts, deliberates, and produces a structured result dict.

    Parameters
    ----------
    config : ResponseAgentConfig or None
        Agent configuration.  Defaults are top_k=3, min_activation=0.01.
    """

    def __init__(self, config: Optional[ResponseAgentConfig] = None):
        self.config = config or ResponseAgentConfig()
        self.memory: Optional[KotlinGraph] = None
        self._total_deliberations: int = 0

        logger.info(
            "ResponseAgent initialised: top_k=%d, min_activation=%.4f",
            self.config.top_k, self.config.min_activation,
        )

    # ---- selection --------------------------------------------------------

    def select_active_areas(self, areas: List[CorticalArea]) -> List[CorticalArea]:
        """
        Filter cortical areas by minimum activation, sort descending by
        activation, and return the top-K.

        Parameters
        ----------
        areas : list of CorticalArea
            All cortical areas to consider.

        Returns
        -------
        list of CorticalArea
            Top-K areas that pass the min_activation threshold, sorted by
            activation descending.
        """
        above_threshold = [a for a in areas if a.activation >= self.config.min_activation]
        above_threshold.sort(key=lambda a: a.activation, reverse=True)
        return above_threshold[: self.config.top_k]

    # ---- thought gathering ------------------------------------------------

    def gather_thoughts(self, areas: List[CorticalArea]) -> List[Dict[str, Any]]:
        """
        Collect recent thoughts from each area, tagging every thought with
        the area's name and current activation.

        Parameters
        ----------
        areas : list of CorticalArea
            Areas to gather thoughts from.

        Returns
        -------
        list of dict
            Thought dicts augmented with ``area_name`` and ``area_activation``.
        """
        all_thoughts: List[Dict[str, Any]] = []
        for area in areas:
            recent = area.get_recent_thoughts(n=5)
            for thought in recent:
                tagged: Dict[str, Any] = dict(thought)
                tagged['area_name'] = area.name
                tagged['area_activation'] = area.activation
                all_thoughts.append(tagged)
        return all_thoughts

    # ---- deliberation (full cycle) ----------------------------------------

    def deliberate(self, areas: List[CorticalArea]) -> Dict[str, Any]:
        """
        Full deliberation cycle.

        1. Select the most activated areas.
        2. Gather their recent thoughts.
        3. Compute confidence from activation distribution.
        4. Record to KotlinGraph memory (if attached).
        5. Return a structured result dict.

        Parameters
        ----------
        areas : list of CorticalArea
            All cortical areas in the brain.

        Returns
        -------
        dict
            Deliberation result with keys: summary, selected_areas,
            confidence, thought_count, area_activations.
        """
        # Step 1: select
        selected = self.select_active_areas(areas)

        # Step 2: gather thoughts
        thoughts = self.gather_thoughts(selected)

        # Step 3: compute confidence
        if selected:
            activations = [a.activation for a in selected]
            confidence = float(np.mean(activations))
            if len(activations) > 1:
                spread = float(np.std(activations))
                confidence = min(1.0, confidence + spread * 0.5)
        else:
            confidence = 0.0

        # Build summary list -- one entry per selected area
        summary: List[Dict[str, Any]] = []
        for area in selected:
            recent = area.get_recent_thoughts(n=5)
            if recent:
                avg_pe = float(np.mean([t['error_magnitude'] for t in recent]))
            else:
                avg_pe = 0.0
            summary.append({
                'name': area.name,
                'activation': area.activation,
                'specialty': area.specialty,
                'avg_prediction_error': round(avg_pe, 6),
            })

        # Build full activation map over *all* areas
        area_activations: Dict[str, float] = {a.name: a.activation for a in areas}

        # Step 4: record to episodic memory
        if self.memory is not None and selected:
            self.memory.add_event(
                state={
                    "areas": [a.name for a in selected],
                    "activations": {a.name: a.activation for a in selected},
                },
                action=f"deliberate_from_{','.join(a.name for a in selected)}",
                next_state={
                    "confidence": confidence,
                    "thought_count": len(thoughts),
                },
                reward=confidence,
                done=True,
                consciousness=confidence,
            )

        self._total_deliberations += 1

        logger.debug(
            "Deliberation #%d: %d areas selected, confidence=%.4f, %d thoughts",
            self._total_deliberations, len(selected), confidence, len(thoughts),
        )

        # Step 5: return result
        return {
            "summary": summary,
            "selected_areas": [a.name for a in selected],
            "confidence": confidence,
            "thought_count": len(thoughts),
            "area_activations": area_activations,
        }

    # ---- state introspection ----------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return agent state for dashboards / diagnostics."""
        return {
            "total_deliberations": self._total_deliberations,
            "top_k": self.config.top_k,
            "min_activation": self.config.min_activation,
            "has_memory": self.memory is not None,
        }
