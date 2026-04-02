"""ResidualGrid — 5x5 local correction grid for the polynomial gaze mapper.

Each cell stores the average click error (dx, dy) observed in that screen region.
Corrections are accumulated via EMA and applied via bilinear interpolation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class _Cell:
    """A single grid cell holding accumulated correction data."""
    dx: float = 0.0
    dy: float = 0.0
    count: int = 0


class ResidualGrid:
    """5x5 correction grid over the screen.

    Each cell accumulates the residual error between predicted and actual
    click positions using an exponential moving average (EMA). During
    inference, bilinear interpolation across the 4 nearest cell centres
    is applied to produce a smooth correction vector.

    Parameters
    ----------
    screen_w : int
        Screen width in pixels (default 1920).
    screen_h : int
        Screen height in pixels (default 1080).
    grid_cols : int
        Number of grid columns (default 5).
    grid_rows : int
        Number of grid rows (default 5).
    min_samples : int
        Minimum number of updates before a cell contributes to interpolation
        (default 3).
    """

    def __init__(
        self,
        screen_w: int = 1920,
        screen_h: int = 1080,
        grid_cols: int = 5,
        grid_rows: int = 5,
        min_samples: int = 3,
    ) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.grid_cols = grid_cols
        self.grid_rows = grid_rows
        self.min_samples = min_samples

        # Cell dimensions
        self.cell_w: float = screen_w / grid_cols
        self.cell_h: float = screen_h / grid_rows

        # Cap: half a cell width / height
        self.cap_x: float = self.cell_w / 2.0
        self.cap_y: float = self.cell_h / 2.0

        # Grid stored as flat list, row-major: index = row * cols + col
        self._cells: List[_Cell] = [
            _Cell() for _ in range(grid_rows * grid_cols)
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cell_index(self, col: int, row: int) -> int:
        return row * self.grid_cols + col

    def _pos_to_cell(self, x: float, y: float) -> Tuple[int, int]:
        """Return (col, row) for screen coordinate (x, y), clamped to grid."""
        col = int(x / self.cell_w)
        row = int(y / self.cell_h)
        col = max(0, min(self.grid_cols - 1, col))
        row = max(0, min(self.grid_rows - 1, row))
        return col, row

    def _cell_center(self, col: int, row: int) -> Tuple[float, float]:
        """Return screen coordinates of a cell's centre."""
        cx = (col + 0.5) * self.cell_w
        cy = (row + 0.5) * self.cell_h
        return cx, cy

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        return max(-limit, min(limit, value))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        predicted_x: float,
        predicted_y: float,
        click_x: float,
        click_y: float,
        alpha: float = 0.3,
    ) -> None:
        """Record a click observation and update the relevant cell.

        The residual is ``click - predicted`` (the correction needed to move
        the predicted position onto the actual click). The first observation
        is stored directly; subsequent ones are blended via EMA.

        Parameters
        ----------
        predicted_x, predicted_y : float
            Position predicted by the polynomial mapper.
        click_x, click_y : float
            Actual click position recorded from the user.
        alpha : float
            EMA smoothing factor (0 < alpha <= 1). Higher = faster adapt.
        """
        col, row = self._pos_to_cell(predicted_x, predicted_y)
        cell = self._cells[self._cell_index(col, row)]

        raw_dx = click_x - predicted_x
        raw_dy = click_y - predicted_y

        # Cap raw residual before incorporating
        raw_dx = self._clamp(raw_dx, self.cap_x)
        raw_dy = self._clamp(raw_dy, self.cap_y)

        if cell.count == 0:
            cell.dx = raw_dx
            cell.dy = raw_dy
        else:
            cell.dx = (1 - alpha) * cell.dx + alpha * raw_dx
            cell.dy = (1 - alpha) * cell.dy + alpha * raw_dy

        # Re-clamp after EMA in case numeric drift
        cell.dx = self._clamp(cell.dx, self.cap_x)
        cell.dy = self._clamp(cell.dy, self.cap_y)

        cell.count += 1

    def interpolate(self, screen_x: float, screen_y: float) -> Tuple[float, float]:
        """Return the interpolated correction vector at a given screen position.

        Uses bilinear interpolation across the 4 nearest cell centres whose
        sample counts meet ``min_samples``. Returns (0.0, 0.0) when no
        qualifying cells are found.

        Parameters
        ----------
        screen_x, screen_y : float
            Screen position to query.
        """
        # Find the fractional cell position
        fx = screen_x / self.cell_w - 0.5  # 0.0 = centre of col 0
        fy = screen_y / self.cell_h - 0.5  # 0.0 = centre of row 0

        col0 = int(math.floor(fx))
        row0 = int(math.floor(fy))

        # Bilinear weights
        tx = fx - col0  # [0, 1)
        ty = fy - row0

        # Four corners: (col0, row0), (col0+1, row0), (col0, row0+1), (col0+1, row0+1)
        corners = [
            (col0,     row0,     (1 - tx) * (1 - ty)),
            (col0 + 1, row0,     tx       * (1 - ty)),
            (col0,     row0 + 1, (1 - tx) * ty),
            (col0 + 1, row0 + 1, tx       * ty),
        ]

        total_weight = 0.0
        sum_dx = 0.0
        sum_dy = 0.0

        for col, row, w in corners:
            # Clamp to valid grid range
            col_c = max(0, min(self.grid_cols - 1, col))
            row_c = max(0, min(self.grid_rows - 1, row))
            cell = self._cells[self._cell_index(col_c, row_c)]

            if cell.count >= self.min_samples:
                sum_dx += w * cell.dx
                sum_dy += w * cell.dy
                total_weight += w

        if total_weight == 0.0:
            return 0.0, 0.0

        return sum_dx / total_weight, sum_dy / total_weight

    def reset(self) -> None:
        """Clear all accumulated corrections (e.g. on drift detection)."""
        self._cells = [_Cell() for _ in range(self.grid_rows * self.grid_cols)]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        """Serialise grid state to a JSON-compatible dictionary."""
        return {
            "screen_w": self.screen_w,
            "screen_h": self.screen_h,
            "grid_cols": self.grid_cols,
            "grid_rows": self.grid_rows,
            "min_samples": self.min_samples,
            "cells": [
                {"dx": c.dx, "dy": c.dy, "count": c.count}
                for c in self._cells
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ResidualGrid":
        """Restore a grid from a previously serialised dictionary."""
        grid = cls(
            screen_w=data["screen_w"],
            screen_h=data["screen_h"],
            grid_cols=data["grid_cols"],
            grid_rows=data["grid_rows"],
            min_samples=data["min_samples"],
        )
        for i, cd in enumerate(data["cells"]):
            grid._cells[i].dx = cd["dx"]
            grid._cells[i].dy = cd["dy"]
            grid._cells[i].count = cd["count"]
        return grid
