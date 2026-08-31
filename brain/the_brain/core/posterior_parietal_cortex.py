"""
Posterior Parietal Cortex (PPC)

Spatial attention, sensorimotor integration, and action planning in space.

Andersen & Buneo (2002): PPC encodes intentions in spatial coordinates,
transforming sensory information into motor plans through gain-field
mechanisms. The PPC sits at the intersection of perception and action,
maintaining priority maps that combine bottom-up salience with top-down
goal relevance.

Four components:

1. SpatialAttentionMap:
   Priority map combining visual salience (bottom-up) with goal
   relevance (top-down) to direct spatial attention.

2. ReferenceFrameTransformer:
   Coordinate transformations between eye-centred, head-centred,
   body-centred, and world-centred frames via gain fields.

3. ActionPlanner:
   Plans spatially-directed actions (reaching, grasping) given a
   target location and the current motor state.

4. PosteriorParietalCortex (main):
   Orchestrates all three components in a single processing cycle.
"""

import logging
import time
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger('brain.ppc')

# ─── Reference frame identifiers ────────────────────────────────────────

FRAMES = ('eye', 'head', 'body', 'world')
_FRAME_IDX = {f: i for i, f in enumerate(FRAMES)}


# ─── Stats ───────────────────────────────────────────────────────────────

@dataclass
class PPCStats:
    """Posterior parietal cortex statistics."""
    total_cycles: int = 0
    avg_peak_salience: float = 0.0
    frame_transforms: int = 0
    action_plans_generated: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_peak_salience': round(self.avg_peak_salience, 4),
            'frame_transforms': self.frame_transforms,
            'action_plans_generated': self.action_plans_generated,
        }


# ─── Spatial Attention Map ───────────────────────────────────────────────

class SpatialAttentionMap:
    """
    Priority map for spatial attention.

    Combines bottom-up visual salience with top-down goal relevance
    into a single priority surface.  The peak of the map indicates
    the most behaviourally relevant location.
    """

    def __init__(self, map_size: int = 16):
        self.map_size = map_size
        self._priority: np.ndarray = np.zeros(map_size)
        self._peak_history: deque = deque(maxlen=50)

    def update_map(
        self,
        visual_salience: np.ndarray,
        goal_relevance: np.ndarray,
    ) -> np.ndarray:
        """
        Combine bottom-up salience and top-down relevance.

        Both arrays are clipped to [0, 1] and then averaged with
        equal weight.  A small temporal smoothing (alpha=0.3) blends
        the new map with the previous one to avoid abrupt jumps.
        """
        sal = np.clip(visual_salience[:self.map_size], 0.0, 1.0)
        rel = np.clip(goal_relevance[:self.map_size], 0.0, 1.0)
        raw = 0.5 * sal + 0.5 * rel
        alpha = 0.3
        self._priority = alpha * self._priority + (1.0 - alpha) * raw
        peak = float(np.max(self._priority))
        self._peak_history.append(peak)
        return self._priority.copy()

    def get_peak_location(self) -> int:
        """Return index of highest priority."""
        return int(np.argmax(self._priority))

    def get_avg_peak(self) -> float:
        if not self._peak_history:
            return 0.0
        return float(np.mean(list(self._peak_history)))


# ─── Reference Frame Transformer ────────────────────────────────────────

class ReferenceFrameTransformer:
    """
    Coordinate transformations via gain fields.

    Each pair of reference frames has a learned gain matrix that
    modulates the input signal to produce coordinates in the target
    frame.  Gain fields are initialised near identity and are
    deliberately simple (linear transform) to stay interpretable.
    """

    def __init__(self, dim: int, n_frames: int = 4):
        self.dim = dim
        self.n_frames = n_frames
        # Gain matrices between adjacent frames (eye->head->body->world)
        self._gains: Dict[str, np.ndarray] = {}
        for i in range(n_frames - 1):
            key = f"{FRAMES[i]}->{FRAMES[i + 1]}"
            self._gains[key] = np.eye(dim) + 0.01 * np.random.randn(dim, dim)
            inv_key = f"{FRAMES[i + 1]}->{FRAMES[i]}"
            self._gains[inv_key] = np.eye(dim) + 0.01 * np.random.randn(dim, dim)

    def transform(
        self,
        signal: np.ndarray,
        from_frame: str,
        to_frame: str,
    ) -> np.ndarray:
        """
        Transform *signal* from *from_frame* to *to_frame*.

        Chains adjacent gain-field multiplications when frames are
        more than one step apart.
        """
        if from_frame == to_frame:
            return signal.copy()

        fi = _FRAME_IDX.get(from_frame)
        ti = _FRAME_IDX.get(to_frame)
        if fi is None or ti is None:
            logger.warning("Unknown frame: %s or %s", from_frame, to_frame)
            return signal.copy()

        result = signal.copy()
        step = 1 if ti > fi else -1
        idx = fi
        while idx != ti:
            nxt = idx + step
            key = f"{FRAMES[idx]}->{FRAMES[nxt]}"
            gain = self._gains.get(key)
            if gain is not None:
                result = gain @ result
            idx = nxt
        return result


# ─── Action Planner ──────────────────────────────────────────────────────

class ActionPlanner:
    """
    Plans spatially-directed reaching / grasping actions.

    Given a target location (index on the priority map) and the
    current motor state, produces a simple action vector, a reach
    plan, and a confidence score.
    """

    def __init__(self, dim: int, planning_gain: float = 1.0):
        self.dim = dim
        self.planning_gain = planning_gain

    def plan(
        self,
        target_location: int,
        current_state: np.ndarray,
    ) -> Dict[str, Any]:
        """Compute action vector toward *target_location*."""
        target_vec = np.zeros(self.dim)
        target_idx = target_location % self.dim
        target_vec[target_idx] = 1.0

        action_vector = self.planning_gain * (target_vec - current_state)
        magnitude = float(np.linalg.norm(action_vector))
        confidence = 1.0 / (1.0 + magnitude)  # closer = more confident

        return {
            'action_vector': action_vector.tolist(),
            'reach_plan': {
                'target_index': target_idx,
                'distance': round(magnitude, 4),
            },
            'movement_confidence': round(confidence, 4),
        }


# ─── Main PPC class ─────────────────────────────────────────────────────

class PosteriorParietalCortex:
    """
    Posterior Parietal Cortex — spatial attention, reference-frame
    transformations, and action planning.

    Standard interface: process / get_state / get_stats / reset /
    to_dict / from_yaml.
    """

    def __init__(
        self,
        map_size: int = 16,
        n_frames: int = 4,
        planning_gain: float = 1.0,
    ):
        self.map_size = map_size
        self.n_frames = n_frames
        self.planning_gain = planning_gain

        self.attention_map = SpatialAttentionMap(map_size)
        self.frame_transformer = ReferenceFrameTransformer(map_size, n_frames)
        self.action_planner = ActionPlanner(map_size, planning_gain)

        self._stats = PPCStats()
        logger.info(
            "PPC initialised: map_size=%d, n_frames=%d, planning_gain=%.2f",
            map_size, n_frames, planning_gain,
        )

    # ── core processing ──────────────────────────────────────────────

    def process(
        self,
        visual_salience: Optional[np.ndarray] = None,
        goal_relevance: Optional[np.ndarray] = None,
        target_location: Optional[int] = None,
        current_state: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Full PPC processing cycle.

        Args:
            visual_salience: Bottom-up salience map (map_size,)
            goal_relevance:  Top-down goal relevance (map_size,)
            target_location: Index for action planning
            current_state:   Current motor state (map_size,)

        Returns:
            Dict with priority_map, peak_location, action_plan (if planned).
        """
        if visual_salience is None:
            visual_salience = np.zeros(self.map_size)
        if goal_relevance is None:
            goal_relevance = np.zeros(self.map_size)
        if current_state is None:
            current_state = np.zeros(self.map_size)

        priority = self.attention_map.update_map(visual_salience, goal_relevance)
        peak = self.attention_map.get_peak_location()

        result: Dict[str, Any] = {
            'priority_map': priority.tolist(),
            'peak_location': peak,
            'peak_salience': round(float(priority[peak]), 4),
        }

        # Plan an action if target is given (or fall back to peak)
        loc = target_location if target_location is not None else peak
        plan = self.action_planner.plan(loc, current_state)
        result['action_plan'] = plan
        self._stats.action_plans_generated += 1

        # Update running stats
        self._stats.total_cycles += 1
        n = self._stats.total_cycles
        avg = self._stats.avg_peak_salience
        self._stats.avg_peak_salience = avg + (result['peak_salience'] - avg) / n

        logger.debug("PPC cycle %d: peak=%d salience=%.3f",
                      n, peak, result['peak_salience'])
        return result

    def sensorimotor_transformation(
        self,
        target_location: int,
        current_state: float = 0.5,
    ) -> Dict[str, float]:
        """
        Sensorimotor coordinate transformation (Andersen & Buneo, 2002).

        PPC transforms sensory coordinates into motor plans. It converts
        "where is the target?" (sensory) into "how do I get there?" (motor).
        This is the bridge between perception and action.

        Args:
            target_location: Target position in attention map [0, map_size-1]
            current_state: Current position/state [0, 1]

        Returns:
            Dict with motor_vector, movement_magnitude, confidence
        """
        target = max(0, min(self.map_size - 1, target_location))
        target_norm = target / max(1, self.map_size - 1)

        # Motor vector: direction and magnitude to target
        motor_vector = target_norm - current_state
        movement_magnitude = abs(motor_vector)

        # Confidence: based on attention at target location
        priority = self.attention_map._priority
        target_attention = float(priority[target]) if target < len(priority) else 0.0
        confidence = min(1.0, target_attention * 1.5)

        return {
            'motor_vector': round(motor_vector, 4),
            'movement_magnitude': round(min(1.0, movement_magnitude), 4),
            'confidence': round(confidence, 4),
            'target_location': target,
        }

    # ── standard interface ───────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'current_priority_map': self.attention_map._priority.tolist(),
            'peak_location': self.attention_map.get_peak_location(),
        }

    def get_stats(self) -> PPCStats:
        return self._stats

    def reset(self):
        self._stats = PPCStats()
        self.attention_map = SpatialAttentionMap(self.map_size)
        self.frame_transformer = ReferenceFrameTransformer(self.map_size, self.n_frames)
        self.action_planner = ActionPlanner(self.map_size, self.planning_gain)

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'PosteriorParietalCortex':
        section = config.get('posterior_parietal_cortex', {})
        return cls(
            map_size=section.get('map_size', 16),
            n_frames=section.get('n_frames', 4),
            planning_gain=section.get('planning_gain', 1.0),
        )
