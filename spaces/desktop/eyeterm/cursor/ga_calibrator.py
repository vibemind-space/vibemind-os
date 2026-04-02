"""GeneticCalibrator — two-tier (Base + Delta) grid-aware calibration via GA.

Architecture:
    Base genome  = current best calibration (frozen between merges)
    Delta pop    = evolves corrections ON TOP of base
    Merge cycle  = when delta improves > threshold → fold into base, reset delta

This ensures continuous iterative improvement: the base captures accumulated
knowledge while the delta always explores fresh corrections around it.

Genome layout (24 genes for 3×3 grid):
    [0:6]   — global 2×3 affine matrix  (base mapping gaze→screen)
    [6:24]  — 9 cells × 2 (dx, dy)     (local correction per cell)

Effective mapping:
    effective_genes = base_genes + delta_genes
    1. base_x, base_y = affine @ [gx, gy, 1]
    2. dx, dy = bilinear_interpolate(grid_corrections, base_x, base_y)
    3. screen_x = base_x + dx,  screen_y = base_y + dy

Fitness penalises empty grid cells (coverage_penalty) and weights the
worst-performing cell at 30% to prevent regional overfitting.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("eyeterm.ga_calibrator")

CALIBRATION_DIR = Path(os.getenv("EYETERM_DATA_DIR", ""))
if not CALIBRATION_DIR.name:
    CALIBRATION_DIR = Path.home() / ".eyeterm"


# ======================================================================
# Data types
# ======================================================================

@dataclass
class ClickPair:
    """A single (gaze_input → actual_click) observation."""
    gaze_x: float
    gaze_y: float
    click_x: int
    click_y: int


@dataclass
class _Individual:
    """One candidate delta genome."""
    genes: np.ndarray   # shape (num_genes,) — delta correction
    fitness: float = float("-inf")


# ======================================================================
# Grid helpers
# ======================================================================

def _bilinear_grid_correction(
    corrections: np.ndarray,   # (rows, cols, 2)
    x: float, y: float,
    sw: int, sh: int,
) -> Tuple[float, float]:
    """Bilinear interpolation of (dx, dy) from the correction grid."""
    rows, cols = corrections.shape[:2]
    cell_w = sw / cols
    cell_h = sh / rows
    fx = x / cell_w - 0.5
    fy = y / cell_h - 0.5
    col0 = int(math.floor(fx))
    row0 = int(math.floor(fy))
    tx = fx - col0
    ty = fy - row0

    dx = dy = 0.0
    for r, c, w in [
        (row0,     col0,     (1 - tx) * (1 - ty)),
        (row0,     col0 + 1, tx       * (1 - ty)),
        (row0 + 1, col0,     (1 - tx) * ty),
        (row0 + 1, col0 + 1, tx       * ty),
    ]:
        rc = max(0, min(rows - 1, r))
        cc = max(0, min(cols - 1, c))
        dx += w * corrections[rc, cc, 0]
        dy += w * corrections[rc, cc, 1]
    return dx, dy


def _apply_genome(
    genes: np.ndarray,
    gx: float, gy: float,
    sw: int, sh: int,
    grid_rows: int, grid_cols: int,
) -> Tuple[float, float]:
    """Map gaze → screen using a full genome (affine + grid corrections)."""
    mat = genes[:6].reshape(2, 3)
    vec = np.array([gx, gy, 1.0])
    base = mat @ vec

    n_cells = grid_rows * grid_cols
    corrections = genes[6:6 + n_cells * 2].reshape(grid_rows, grid_cols, 2)
    dx, dy = _bilinear_grid_correction(corrections, base[0], base[1], sw, sh)
    return base[0] + dx, base[1] + dy


# ======================================================================
# GeneticCalibrator (two-tier: Base + Delta)
# ======================================================================

class GeneticCalibrator:
    """Two-tier genetic calibration with continuous iterative improvement.

    The base genome stores accumulated calibration knowledge. The delta
    population evolves corrections on top of it. When a delta improves
    the overall fitness beyond a threshold, it is merged into the base
    and the delta population resets — creating an infinite improvement loop.

    Parameters
    ----------
    screen_w, screen_h : int
        Screen dimensions.
    grid_rows, grid_cols : int
        Correction grid (default 3×3).
    pop_size : int
        Delta population size (default 100).
    merge_threshold : float
        Min improvement (px) to trigger a base←delta merge (default 3.0).
    coverage_penalty : float
        Penalty per empty grid cell (default 50.0).
    """

    def __init__(
        self,
        screen_w: int = 1920,
        screen_h: int = 1080,
        grid_rows: int = 3,
        grid_cols: int = 3,
        pop_size: int = 100,
        elite_frac: float = 0.15,
        mutation_rate: float = 0.20,
        mutation_scale: float = 0.06,
        crossover_rate: float = 0.5,
        min_samples: int = 8,
        min_coverage: int = 3,
        evolve_interval: float = 2.0,
        merge_threshold: float = 3.0,
        coverage_penalty: float = 50.0,
    ) -> None:
        self._sw = screen_w
        self._sh = screen_h
        self._grid_rows = grid_rows
        self._grid_cols = grid_cols
        self._n_cells = grid_rows * grid_cols
        self._num_genes = 6 + self._n_cells * 2

        self._pop_size = pop_size
        self._elite_count = max(2, int(pop_size * elite_frac))
        self._mutation_rate = mutation_rate
        self._mutation_scale = mutation_scale
        self._crossover_rate = crossover_rate
        self._min_samples = min_samples
        self._min_coverage = min_coverage
        self._evolve_interval = evolve_interval
        self._merge_threshold = merge_threshold
        self._coverage_penalty = coverage_penalty

        # Thread-safe sample buffer
        self._lock = threading.Lock()
        self._samples: List[ClickPair] = []
        self._max_samples = 500

        # Two-tier state
        self._base_genes: np.ndarray = np.zeros(self._num_genes, dtype=np.float64)
        self._delta_population: List[_Individual] = []
        self._best_delta: Optional[_Individual] = None
        self._base_fitness = float("-inf")   # fitness of base alone
        self._best_combined_fitness = float("-inf")

        self._generation = 0
        self._merge_count = 0

        self._on_improved: Optional[Callable] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Sample collection
    # ------------------------------------------------------------------

    def add_sample(self, gaze_x: float, gaze_y: float, click_x: int, click_y: int) -> None:
        with self._lock:
            self._samples.append(ClickPair(gaze_x, gaze_y, click_x, click_y))
            if len(self._samples) > self._max_samples:
                self._samples = self._samples[-self._max_samples:]

    @property
    def sample_count(self) -> int:
        with self._lock:
            return len(self._samples)

    # ------------------------------------------------------------------
    # Grid-aware fitness
    # ------------------------------------------------------------------

    def _assign_to_cells(self, samples: List[ClickPair]) -> Dict[Tuple[int, int], List[ClickPair]]:
        cell_w = self._sw / self._grid_cols
        cell_h = self._sh / self._grid_rows
        buckets: Dict[Tuple[int, int], List[ClickPair]] = {}
        for s in samples:
            col = max(0, min(int(s.click_x / cell_w), self._grid_cols - 1))
            row = max(0, min(int(s.click_y / cell_h), self._grid_rows - 1))
            buckets.setdefault((row, col), []).append(s)
        return buckets

    def _evaluate_genes(self, effective_genes: np.ndarray,
                        cell_buckets: Dict[Tuple[int, int], List[ClickPair]]) -> float:
        """Evaluate a complete genome (base + delta) against cell-bucketed samples."""
        total_residual = 0.0
        n_total = 0

        for row in range(self._grid_rows):
            for col in range(self._grid_cols):
                cell_samples = cell_buckets.get((row, col), [])
                if not cell_samples:
                    total_residual += self._coverage_penalty
                    n_total += 1
                    continue
                for s in cell_samples:
                    sx, sy = _apply_genome(
                        effective_genes, s.gaze_x, s.gaze_y,
                        self._sw, self._sh, self._grid_rows, self._grid_cols,
                    )
                    total_residual += math.hypot(sx - s.click_x, sy - s.click_y)
                    n_total += 1

        mean_res = total_residual / max(n_total, 1)

        # Worst-cell penalty
        worst_cell = 0.0
        for cell_samples in cell_buckets.values():
            if not cell_samples:
                continue
            cell_res = sum(
                math.hypot(
                    _apply_genome(effective_genes, s.gaze_x, s.gaze_y,
                                  self._sw, self._sh, self._grid_rows, self._grid_cols)[0] - s.click_x,
                    _apply_genome(effective_genes, s.gaze_x, s.gaze_y,
                                  self._sw, self._sh, self._grid_rows, self._grid_cols)[1] - s.click_y,
                )
                for s in cell_samples
            ) / len(cell_samples)
            worst_cell = max(worst_cell, cell_res)

        return -(0.7 * mean_res + 0.3 * worst_cell)

    def _evaluate_delta(self, delta: _Individual,
                        cell_buckets: Dict[Tuple[int, int], List[ClickPair]]) -> float:
        """Evaluate base + delta combined."""
        effective = self._base_genes + delta.genes
        return self._evaluate_genes(effective, cell_buckets)

    # ------------------------------------------------------------------
    # Population management
    # ------------------------------------------------------------------

    def _init_base(self) -> None:
        """Seed the base genome from saved calibration or default."""
        saved = self._load_best()
        if saved is not None:
            self._base_genes = saved.copy()
            logger.info("Base genome loaded from disk")
        else:
            # Default: typical webcam range mapping
            rx, ry = 0.6, 0.5
            self._base_genes[:6] = [
                self._sw / rx, 0.0, -self._sw * 0.2 / rx,
                0.0, self._sh / ry, -self._sh * 0.25 / ry,
            ]
            # Grid corrections start at zero
            logger.info("Base genome initialized with default webcam range")

    def _init_delta_population(self) -> None:
        """Create a fresh delta population centred around zero (small corrections)."""
        self._delta_population = []
        ng = self._num_genes

        # Individual 0: zero delta (no change from base)
        self._delta_population.append(_Individual(genes=np.zeros(ng, dtype=np.float64)))

        # Rest: small random perturbations
        while len(self._delta_population) < self._pop_size:
            noise = np.zeros(ng, dtype=np.float64)
            # Small affine perturbations
            noise[:6] = np.random.normal(0, 0.02, size=6) * np.abs(self._base_genes[:6]).clip(1.0)
            # Small grid perturbations (±8px)
            noise[6:] = np.random.normal(0, 8.0, size=ng - 6)
            self._delta_population.append(_Individual(genes=noise))

        self._best_delta = None
        logger.info("Delta population reset: %d individuals", len(self._delta_population))

    # ------------------------------------------------------------------
    # Genetic operators
    # ------------------------------------------------------------------

    def _select_parent(self, ranked: List[_Individual]) -> _Individual:
        contestants = random.sample(ranked, min(3, len(ranked)))
        return max(contestants, key=lambda i: i.fitness)

    def _crossover(self, p1: _Individual, p2: _Individual) -> _Individual:
        child = np.empty(self._num_genes, dtype=np.float64)
        for i in range(self._num_genes):
            child[i] = p1.genes[i] if random.random() < self._crossover_rate else p2.genes[i]
        return _Individual(genes=child)

    def _mutate(self, ind: _Individual) -> None:
        for i in range(self._num_genes):
            if random.random() < self._mutation_rate:
                if i < 6:
                    # Affine delta: smaller scale since base already handles coarse mapping
                    base_mag = max(abs(self._base_genes[i]) * 0.02, 0.5)
                    ind.genes[i] += random.gauss(0, base_mag)
                else:
                    # Grid delta: ±8px corrections
                    ind.genes[i] += random.gauss(0, 8.0)

    # ------------------------------------------------------------------
    # Evolution + merge cycle
    # ------------------------------------------------------------------

    def _evolve_one_generation(self, cell_buckets: Dict) -> None:
        for ind in self._delta_population:
            ind.fitness = self._evaluate_delta(ind, cell_buckets)

        self._delta_population.sort(key=lambda i: i.fitness, reverse=True)

        if self._best_delta is None or self._delta_population[0].fitness > self._best_delta.fitness:
            self._best_delta = _Individual(
                genes=self._delta_population[0].genes.copy(),
                fitness=self._delta_population[0].fitness,
            )

        # Next generation
        new_pop = [_Individual(genes=ind.genes.copy(), fitness=ind.fitness)
                   for ind in self._delta_population[:self._elite_count]]

        while len(new_pop) < self._pop_size:
            p1 = self._select_parent(self._delta_population)
            p2 = self._select_parent(self._delta_population)
            child = self._crossover(p1, p2)
            self._mutate(child)
            new_pop.append(child)

        self._delta_population = new_pop
        self._generation += 1

    def _try_merge(self, cell_buckets: Dict) -> bool:
        """Check if delta improves enough to merge into base. Returns True if merged."""
        if self._best_delta is None:
            return False

        combined_fitness = self._best_delta.fitness
        combined_residual = -combined_fitness

        # Evaluate base alone (zero delta)
        base_fitness = self._evaluate_genes(self._base_genes, cell_buckets)
        base_residual = -base_fitness

        improvement = base_residual - combined_residual

        if improvement >= self._merge_threshold:
            # Merge: fold delta into base
            old_base_residual = base_residual
            self._base_genes = self._base_genes + self._best_delta.genes
            self._base_fitness = combined_fitness
            self._best_combined_fitness = combined_fitness
            self._merge_count += 1

            logger.info(
                "MERGE #%d @ gen=%d: base %.1fpx → %.1fpx (delta improved %.1fpx)",
                self._merge_count, self._generation,
                old_base_residual, combined_residual, improvement,
            )

            # Save merged base
            self._save_best(self._base_genes)

            # Notify headless
            if self._on_improved:
                try:
                    self._on_improved(self._base_genes.copy(), combined_residual)
                except Exception as e:
                    logger.error("on_improved callback failed: %s", e)

            # Reset delta population for next improvement cycle
            self._init_delta_population()
            return True

        return False

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def start(self, on_improved: Optional[Callable] = None) -> None:
        if self._running:
            return
        self._on_improved = on_improved
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="GA-Calibrator", daemon=True)
        self._thread.start()
        logger.info("GeneticCalibrator started (two-tier, grid=%dx%d, genes=%d)",
                     self._grid_rows, self._grid_cols, self._num_genes)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("GeneticCalibrator stopped (gen=%d, merges=%d)", self._generation, self._merge_count)

    def _run_loop(self) -> None:
        self._init_base()
        self._init_delta_population()

        # Apply base immediately on start (if loaded from disk)
        if self._on_improved and np.any(self._base_genes != 0):
            try:
                self._on_improved(self._base_genes.copy(), 0.0)
                logger.info("Applied saved base calibration on startup")
            except Exception:
                pass

        while self._running:
            with self._lock:
                n = len(self._samples)
                snapshot = list(self._samples) if n >= self._min_samples else []

            if not snapshot:
                time.sleep(self._evolve_interval)
                continue

            cell_buckets = self._assign_to_cells(snapshot)
            coverage = len(cell_buckets)

            # Evolve delta
            self._evolve_one_generation(cell_buckets)

            # Try merge if enough coverage
            if coverage >= self._min_coverage:
                self._try_merge(cell_buckets)

            # Progress logging
            if self._generation % 25 == 0 and self._best_delta:
                best_res = -self._best_delta.fitness
                base_res = -self._evaluate_genes(self._base_genes, cell_buckets)
                logger.info(
                    "GA gen=%d merges=%d samples=%d cov=%d/%d | base=%.1fpx combined=%.1fpx",
                    self._generation, self._merge_count, len(snapshot),
                    coverage, self._n_cells, base_res, best_res,
                )

            time.sleep(self._evolve_interval)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def map_gaze(self, gaze_x: float, gaze_y: float) -> Optional[Tuple[int, int]]:
        """Map gaze → screen using base + best delta."""
        if not np.any(self._base_genes != 0):
            return None
        effective = self._base_genes.copy()
        if self._best_delta is not None:
            effective += self._best_delta.genes
        sx, sy = _apply_genome(
            effective, gaze_x, gaze_y,
            self._sw, self._sh, self._grid_rows, self._grid_cols,
        )
        return (int(np.clip(sx, 0, self._sw - 1)), int(np.clip(sy, 0, self._sh - 1)))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_best(self, genes: np.ndarray) -> None:
        try:
            CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
            path = CALIBRATION_DIR / "ga_calibration.json"
            data = {
                "genes": genes.tolist(),
                "grid_rows": self._grid_rows,
                "grid_cols": self._grid_cols,
                "generation": self._generation,
                "merge_count": self._merge_count,
                "fitness": float(self._best_combined_fitness),
                "sample_count": self.sample_count,
                "timestamp": time.time(),
            }
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning("Failed to save GA calibration: %s", e)

    def _load_best(self) -> Optional[np.ndarray]:
        try:
            path = CALIBRATION_DIR / "ga_calibration.json"
            if path.exists():
                data = json.loads(path.read_text())
                if (data.get("grid_rows") == self._grid_rows
                        and data.get("grid_cols") == self._grid_cols):
                    genes = np.array(data["genes"], dtype=np.float64)
                    if genes.shape == (self._num_genes,):
                        self._merge_count = data.get("merge_count", 0)
                        logger.info(
                            "Loaded GA calibration (gen=%d, merges=%d, grid=%dx%d)",
                            data.get("generation", 0), self._merge_count,
                            self._grid_rows, self._grid_cols,
                        )
                        return genes
                else:
                    logger.info("Saved GA has different grid size, ignoring")
        except Exception as e:
            logger.warning("Failed to load GA calibration: %s", e)
        return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def best_residual(self) -> Optional[float]:
        return -self._best_delta.fitness if self._best_delta else None

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict:
        with self._lock:
            buckets = self._assign_to_cells(self._samples) if self._samples else {}
        base_res = None
        combined_res = None
        if self._best_delta is not None:
            combined_res = round(-self._best_delta.fitness, 1)
        if buckets and np.any(self._base_genes != 0):
            base_res = round(-self._evaluate_genes(self._base_genes, buckets), 1)
        return {
            "running": self._running,
            "generation": self._generation,
            "merges": self._merge_count,
            "samples": self.sample_count,
            "grid": f"{self._grid_rows}x{self._grid_cols}",
            "coverage": f"{len(buckets)}/{self._n_cells}",
            "base_residual_px": base_res,
            "combined_residual_px": combined_res,
        }
