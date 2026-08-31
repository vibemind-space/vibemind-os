"""
Entorhinal Cortex Module - Phase C1

Extends the hippocampus system with an explicit entorhinal cortex
for grid cells, path integration, and memory gateway functions.

Neuroscience basis:
- Grid cells (Moser & Moser, 2008): Metric spatial representation
- Border cells: Boundary detection
- Head direction cells: Orientation
- EC Layer II/III: Cortical input gateway to hippocampus
- EC Layer V/VI: Hippocampal output to cortex

Key references:
- Hafting et al. (2005): Microstructure of a spatial map
- "Spatially periodic computation in entorhinal-hippocampal circuit"

Integration:
- Sits between cortex and hippocampus
- All cortical inputs pass through EC before reaching hippocampus
- Hippocampal outputs pass through EC back to cortex
"""

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.entorhinal_cortex')


@dataclass
class GridCellActivation:
    """Activation pattern of a grid cell module."""
    module_id: int
    grid_scale: float
    activation: np.ndarray
    phase: np.ndarray


@dataclass
class ECStats:
    """Entorhinal cortex statistics."""
    total_inputs: int = 0
    total_outputs: int = 0
    path_integration_steps: int = 0
    avg_grid_coherence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_inputs': self.total_inputs,
            'total_outputs': self.total_outputs,
            'path_integration_steps': self.path_integration_steps,
            'avg_grid_coherence': round(self.avg_grid_coherence, 3),
        }


class GridCellModule:
    """
    A single grid cell module at a specific spatial scale.

    Each module tiles space at a different scale (geometric series).
    The firing pattern is a hexagonal grid (modeled as cosine sum).
    """

    def __init__(self, module_id: int, grid_scale: float, dim: int = 16):
        self.module_id = module_id
        self.grid_scale = grid_scale
        self.dim = dim

        # Grid orientation (3 axes for hexagonal grid, 60 degrees apart)
        rng = np.random.RandomState(module_id)
        base_angle = rng.uniform(0, math.pi / 3)
        self.orientations = [base_angle + i * math.pi / 3 for i in range(3)]

        # Current phase (position within the grid)
        self._phase = np.zeros(2, dtype=np.float32)
        self._activation = np.zeros(dim, dtype=np.float32)

    def compute_activation(self, position: np.ndarray) -> np.ndarray:
        """
        Compute grid cell firing rate at a given position.

        The activation is a sum of cosines along 3 axes,
        creating a hexagonal firing pattern.
        """
        pos = np.asarray(position, dtype=np.float32).flatten()[:2]
        if len(pos) < 2:
            pos = np.zeros(2, dtype=np.float32)

        activation = np.zeros(self.dim, dtype=np.float32)
        for i in range(min(3, self.dim)):
            theta = self.orientations[i]
            proj = pos[0] * math.cos(theta) + pos[1] * math.sin(theta)
            freq = 2 * math.pi / self.grid_scale
            activation[i] = (1 + math.cos(freq * proj)) / 2.0

        # Fill remaining dims with scaled copies
        for i in range(3, self.dim):
            activation[i] = activation[i % 3] * (1.0 - 0.1 * (i // 3))

        self._activation = np.clip(activation, 0.0, 1.0)
        return self._activation

    def update_phase(self, velocity: np.ndarray):
        """Update grid phase based on velocity (path integration)."""
        v = np.asarray(velocity, dtype=np.float32).flatten()[:2]
        if len(v) < 2:
            return
        self._phase += v / self.grid_scale

    @property
    def phase(self) -> np.ndarray:
        return self._phase.copy()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'module_id': self.module_id,
            'grid_scale': self.grid_scale,
            'activation_mean': round(float(self._activation.mean()), 3),
        }


class BorderCellLayer:
    """
    Border cells: fire when near environmental boundaries.
    """

    def __init__(self, boundary_dim: int = 4):
        self.boundary_dim = boundary_dim
        self._activation = np.zeros(boundary_dim, dtype=np.float32)

    def detect_boundaries(self, state: np.ndarray, bounds: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Detect proximity to boundaries.

        Args:
            state: Current position/state
            bounds: Boundary positions [boundary_dim, 2] or None

        Returns:
            Boundary proximity activation [boundary_dim]
        """
        s = np.asarray(state, dtype=np.float32).flatten()
        if bounds is not None:
            b = np.asarray(bounds, dtype=np.float32)
            for i in range(min(self.boundary_dim, len(b))):
                dist = np.abs(s[:len(b[i])] - b[i][:len(s)]).mean() if len(b) > i else 1.0
                self._activation[i] = max(0.0, 1.0 - dist)
        else:
            # Heuristic: use absolute values near 0 or 1 as "boundaries"
            for i in range(min(self.boundary_dim, len(s))):
                near_zero = max(0, 1.0 - abs(s[i]) * 5.0)
                near_one = max(0, 1.0 - abs(1.0 - abs(s[i])) * 5.0)
                self._activation[i] = max(near_zero, near_one)

        return self._activation.copy()


class HeadDirectionRing:
    """
    Head direction cells: ring attractor encoding current direction.
    """

    def __init__(self, n_directions: int = 8):
        self.n_directions = n_directions
        self._activation = np.zeros(n_directions, dtype=np.float32)
        self._current_direction = 0.0

    def update(self, angular_velocity: float = 0.0) -> np.ndarray:
        """Update head direction from angular velocity."""
        self._current_direction = (self._current_direction + angular_velocity) % (2 * math.pi)

        # Ring attractor: Gaussian bump centered at current direction
        for i in range(self.n_directions):
            preferred = 2 * math.pi * i / self.n_directions
            diff = abs(self._current_direction - preferred)
            diff = min(diff, 2 * math.pi - diff)
            self._activation[i] = math.exp(-diff ** 2 / 0.5)

        return self._activation.copy()

    @property
    def direction(self) -> float:
        return self._current_direction


class PathIntegrator:
    """
    Velocity-based path integration combining grid cells + head direction.
    """

    def __init__(self, state_dim: int = 16):
        self.state_dim = state_dim
        self._position = np.zeros(2, dtype=np.float32)
        self._step_count = 0

    def integrate(self, velocity: np.ndarray) -> np.ndarray:
        """
        Update position estimate from velocity.

        Returns:
            Estimated position [2]
        """
        v = np.asarray(velocity, dtype=np.float32).flatten()[:2]
        if len(v) < 2:
            v = np.zeros(2, dtype=np.float32)
        self._position += v
        self._step_count += 1
        return self._position.copy()

    def reset_position(self, position: Optional[np.ndarray] = None):
        """Reset position (e.g., when at a known location)."""
        if position is not None:
            self._position = np.asarray(position, dtype=np.float32).flatten()[:2]
        else:
            self._position[:] = 0.0

    @property
    def position(self) -> np.ndarray:
        return self._position.copy()


class MemoryGateway:
    """
    EC as gateway between cortex and hippocampus.

    EC Layer II/III: cortex -> hippocampus (encoding)
    EC Layer V/VI: hippocampus -> cortex (retrieval)
    """

    def __init__(self, cortical_dim: int = 32, hippocampal_dim: int = 16):
        self.cortical_dim = cortical_dim
        self.hippocampal_dim = hippocampal_dim

        # Encoding projection (cortex -> hippocampus)
        rng = np.random.RandomState(42)
        self._encode_weights = rng.randn(cortical_dim, hippocampal_dim).astype(np.float32)
        self._encode_weights *= np.sqrt(2.0 / cortical_dim)

        # Retrieval projection (hippocampus -> cortex)
        self._retrieve_weights = rng.randn(hippocampal_dim, cortical_dim).astype(np.float32)
        self._retrieve_weights *= np.sqrt(2.0 / hippocampal_dim)

    def encode(self, cortical_input: np.ndarray) -> np.ndarray:
        """Transform cortical input for hippocampus."""
        x = np.asarray(cortical_input, dtype=np.float32).flatten()
        padded = np.zeros(self.cortical_dim, dtype=np.float32)
        n = min(len(x), self.cortical_dim)
        padded[:n] = x[:n]
        return np.tanh(padded @ self._encode_weights)

    def retrieve(self, hippocampal_output: np.ndarray) -> np.ndarray:
        """Transform hippocampal output for cortex."""
        x = np.asarray(hippocampal_output, dtype=np.float32).flatten()
        padded = np.zeros(self.hippocampal_dim, dtype=np.float32)
        n = min(len(x), self.hippocampal_dim)
        padded[:n] = x[:n]
        return np.tanh(padded @ self._retrieve_weights)


class EntorhinalCortex:
    """
    Complete entorhinal cortex module.

    Functions:
    1. Grid cell spatial representation (multiple scales)
    2. Border cell boundary detection
    3. Head direction ring attractor
    4. Path integration (dead reckoning)
    5. Memory gateway (cortex <-> hippocampus)
    """

    def __init__(
        self,
        state_dim: int = 32,
        n_grid_modules: int = 4,
        grid_scales: Optional[List[float]] = None,
        n_directions: int = 8,
    ):
        self.state_dim = state_dim

        if grid_scales is None:
            grid_scales = [0.5, 1.0, 2.0, 4.0][:n_grid_modules]

        self.grid_modules = [
            GridCellModule(i, scale, dim=state_dim)
            for i, scale in enumerate(grid_scales)
        ]
        self.border_cells = BorderCellLayer(boundary_dim=4)
        self.head_direction = HeadDirectionRing(n_directions)
        self.path_integrator = PathIntegrator(state_dim)
        self.gateway = MemoryGateway(cortical_dim=state_dim, hippocampal_dim=state_dim // 2)

        self._stats = ECStats()

    def process_input(self, cortical_input: np.ndarray) -> np.ndarray:
        """Process cortical input through EC gateway toward hippocampus."""
        self._stats.total_inputs += 1
        return self.gateway.encode(cortical_input)

    def process_output(self, hippocampal_output: np.ndarray) -> np.ndarray:
        """Process hippocampal output through EC gateway toward cortex."""
        self._stats.total_outputs += 1
        return self.gateway.retrieve(hippocampal_output)

    def update_spatial(
        self,
        position: np.ndarray,
        velocity: Optional[np.ndarray] = None,
        angular_velocity: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Update all spatial representations.

        Args:
            position: Current position
            velocity: Current velocity (for path integration)
            angular_velocity: Angular velocity (for head direction)

        Returns:
            Dict with grid activations, head direction, position estimate
        """
        grid_activations = []
        for gm in self.grid_modules:
            act = gm.compute_activation(position)
            if velocity is not None:
                gm.update_phase(velocity)
            grid_activations.append(act)

        borders = self.border_cells.detect_boundaries(position)
        head_dir = self.head_direction.update(angular_velocity)

        if velocity is not None:
            self.path_integrator.integrate(velocity)
            self._stats.path_integration_steps += 1

        return {
            'grid_activations': grid_activations,
            'borders': borders,
            'head_direction': head_dir,
            'estimated_position': self.path_integrator.position,
        }

    def cognitive_map_distance(
        self,
        state_a: np.ndarray,
        state_b: np.ndarray,
    ) -> Dict[str, float]:
        """
        Cognitive map distance computation (Moser et al., 2008).

        Grid cells in EC don't just encode physical space — they also
        encode abstract conceptual spaces. The distance between two
        states in grid-cell space reflects their relational distance,
        enabling analogical reasoning and transfer learning.

        Args:
            state_a: First state/concept vector
            state_b: Second state/concept vector

        Returns:
            Dict with grid_distance, similarity, path_complexity
        """
        a = np.asarray(state_a, dtype=np.float32)
        b = np.asarray(state_b, dtype=np.float32)

        # Encode both states through grid modules
        min_dim = min(len(a), len(b))
        a = a[:min_dim]
        b = b[:min_dim]

        # Euclidean distance in state space
        euclidean = float(np.linalg.norm(a - b))

        # Grid-cell distance: periodic metric (wraps around)
        grid_dists = []
        for gm in self.grid_modules:
            scale = gm.grid_scale
            # Phase difference modulo grid scale
            phase_diff = float(np.mean(np.abs((a[:len(gm._phase)] - b[:len(gm._phase)]) % scale)))
            grid_dists.append(phase_diff)

        grid_distance = float(np.mean(grid_dists)) if grid_dists else euclidean

        # Similarity: inverse of normalized distance
        max_dist = max(0.01, euclidean + grid_distance)
        similarity = max(0.0, 1.0 - grid_distance / max_dist)

        # Path complexity: how many grid module boundaries crossed
        path_complexity = min(1.0, euclidean / (max(1.0, len(self.grid_modules)) * 0.5))

        return {
            'grid_distance': round(grid_distance, 4),
            'euclidean_distance': round(euclidean, 4),
            'similarity': round(similarity, 4),
            'path_complexity': round(path_complexity, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'n_grid_modules': len(self.grid_modules),
            'head_direction': round(self.head_direction.direction, 3),
            'position': self.path_integrator.position.tolist(),
        }

    def get_stats(self) -> ECStats:
        return self._stats

    def reset(self):
        self.path_integrator.reset_position()
        self._stats = ECStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'EntorhinalCortex':
        ec = config.get('entorhinal_cortex', {})
        state_dim = config.get('state_dim',
                    config.get('model', {}).get('input_dim', 32))
        return cls(
            state_dim=state_dim,
            n_grid_modules=ec.get('n_grid_modules', 4),
            grid_scales=ec.get('grid_scales', None),
        )
