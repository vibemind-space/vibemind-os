"""PolynomialMapper: quadratic gaze-to-screen coordinate mapping.

Maps gaze ratios (0-1) to screen pixel coordinates using a quadratic polynomial:
  feature vector: [gx^2, gy^2, gx*gy, gx, gy, 1]  (6 features)
  Two independent outputs: screen_x and screen_y, each with 6 coefficients.
  Matrix shape: (2, 6) for polynomial, (2, 3) for legacy affine.

Ridge regression (Tikhonov) prevents extreme coefficients when the gaze input
range is narrow.  If the polynomial system is ill-conditioned (cond > 1e6),
fitting falls back to a plain affine (2, 3) matrix.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Condition-number threshold above which we fall back to affine.
_COND_THRESHOLD = 1e6


class PolynomialMapper:
    """Quadratic polynomial gaze-to-screen mapper with affine fallback.

    Attributes
    ----------
    matrix : np.ndarray or None
        Fitted coefficient matrix.  Shape is (2, 6) for polynomial or
        (2, 3) for affine (legacy or fallback).
    mapper_type : str
        ``"polynomial"`` or ``"affine"`` — set after :meth:`fit` or :meth:`load`.
    """

    def __init__(self) -> None:
        self.matrix: Optional[np.ndarray] = None
        self.mapper_type: str = "polynomial"

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    @staticmethod
    def feature_vector(gx: float, gy: float) -> np.ndarray:
        """Return the 6-element quadratic feature vector for a gaze point.

        Parameters
        ----------
        gx, gy : float
            Normalised gaze coordinates in [0, 1].

        Returns
        -------
        np.ndarray
            ``[gx**2, gy**2, gx*gy, gx, gy, 1.0]``, shape (6,).
        """
        return np.array(
            [gx ** 2, gy ** 2, gx * gy, gx, gy, 1.0],
            dtype=np.float64,
        )

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, gx: float, gy: float) -> Tuple[float, float]:
        """Map a normalised gaze point to screen pixel coordinates.

        Supports both the (2, 6) polynomial matrix and the (2, 3) legacy
        affine matrix.

        Parameters
        ----------
        gx, gy : float
            Normalised gaze coordinates in [0, 1].

        Returns
        -------
        tuple[float, float]
            ``(screen_x, screen_y)`` in pixels.

        Raises
        ------
        RuntimeError
            If no matrix has been fitted or loaded yet.
        """
        if self.matrix is None:
            raise RuntimeError(
                "No matrix available. Call fit() or load() first."
            )

        if self.matrix.shape == (2, 3):
            # Legacy affine: screen = M @ [gx, gy, 1]
            feat = np.array([gx, gy, 1.0], dtype=np.float64)
        else:
            # Polynomial (2, 6)
            feat = self.feature_vector(gx, gy)

        result = self.matrix @ feat
        return (float(result[0]), float(result[1]))

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(
        self,
        gaze_points: List[Tuple[float, float]],
        screen_targets: List[Tuple[float, float]],
        ridge_lambda: float = 0.01,
    ) -> np.ndarray:
        """Fit the polynomial mapper using ridge regression.

        Builds the design matrix A of shape (N, 6) where each row is
        ``feature_vector(gx, gy)``, then solves::

            (A^T A + ridge_lambda * I) @ W^T = A^T @ B

        where B is (N, 2) with [screen_x, screen_y] targets.

        If the condition number of A^T A exceeds ``_COND_THRESHOLD`` the
        method falls back to a plain affine least-squares fit with a (2, 3)
        matrix.

        Parameters
        ----------
        gaze_points : list of (float, float)
            Normalised gaze samples.
        screen_targets : list of (float, float)
            Corresponding screen pixel targets.
        ridge_lambda : float
            Regularisation strength (default 0.01).

        Returns
        -------
        np.ndarray
            The fitted matrix (2, 6) or (2, 3) affine fallback.
        """
        n = len(gaze_points)
        if n < 1:
            raise ValueError("Need at least one point to fit.")

        # Build polynomial design matrix (N, 6)
        A_poly = np.zeros((n, 6), dtype=np.float64)
        B = np.zeros((n, 2), dtype=np.float64)
        for i, ((gx, gy), (sx, sy)) in enumerate(
            zip(gaze_points, screen_targets)
        ):
            A_poly[i] = self.feature_vector(gx, gy)
            B[i] = [sx, sy]

        # Ridge: (A^T A + lambda * I)^-1 A^T B
        AtA = A_poly.T @ A_poly
        cond = float(np.linalg.cond(AtA))
        logger.debug("Polynomial design matrix condition number: %.3e", cond)

        if cond > _COND_THRESHOLD:
            logger.warning(
                "Polynomial system ill-conditioned (cond=%.2e > %.2e). "
                "Falling back to affine mapping.",
                cond,
                _COND_THRESHOLD,
            )
            self.matrix = self._fit_affine(gaze_points, screen_targets)
            self.mapper_type = "affine"
        else:
            reg_matrix = AtA + ridge_lambda * np.eye(6, dtype=np.float64)
            AtB = A_poly.T @ B
            # Solve reg_matrix @ W^T = AtB  →  W^T shape (6, 2)
            W_T = np.linalg.solve(reg_matrix, AtB)
            self.matrix = W_T.T.copy()  # shape (2, 6)
            self.mapper_type = "polynomial"

        return self.matrix

    @staticmethod
    def _fit_affine(
        gaze_points: List[Tuple[float, float]],
        screen_targets: List[Tuple[float, float]],
    ) -> np.ndarray:
        """Plain affine least-squares: screen = M @ [gx, gy, 1].

        Returns
        -------
        np.ndarray
            Shape (2, 3).
        """
        n = len(gaze_points)
        A = np.zeros((n, 3), dtype=np.float64)
        B = np.zeros((n, 2), dtype=np.float64)
        for i, ((gx, gy), (sx, sy)) in enumerate(
            zip(gaze_points, screen_targets)
        ):
            A[i] = [gx, gy, 1.0]
            B[i] = [sx, sy]
        solution, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
        return solution.T.copy()  # shape (2, 3)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save the mapper to a JSON file.

        The file contains a ``"type"`` field (``"polynomial"`` or
        ``"affine"``) and a ``"matrix"`` field with the coefficient list.

        Parameters
        ----------
        path : str
            Destination file path.

        Raises
        ------
        RuntimeError
            If no matrix has been fitted yet.
        """
        if self.matrix is None:
            raise RuntimeError(
                "No matrix to save. Call fit() first."
            )
        data = {
            "type": self.mapper_type,
            "matrix": self.matrix.tolist(),
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("PolynomialMapper saved to %s (type=%s)", path, self.mapper_type)

    @classmethod
    def load(cls, path: str) -> "PolynomialMapper":
        """Load a mapper from a JSON file.

        Backward-compatible: handles both (2, 3) affine files (which may
        lack a ``"type"`` key) and (2, 6) polynomial files.

        Parameters
        ----------
        path : str
            Source file path.

        Returns
        -------
        PolynomialMapper
            A new instance with :attr:`matrix` and :attr:`mapper_type` set.

        Raises
        ------
        ValueError
            If the matrix shape is not (2, 3) or (2, 6).
        """
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        matrix = np.array(raw["matrix"], dtype=np.float64)

        instance = cls()

        if matrix.shape == (2, 3):
            instance.mapper_type = raw.get("type", "affine")
            instance.matrix = matrix
        elif matrix.shape == (2, 6):
            instance.mapper_type = raw.get("type", "polynomial")
            instance.matrix = matrix
        else:
            raise ValueError(
                f"Unsupported matrix shape {matrix.shape}. "
                "Expected (2, 3) or (2, 6)."
            )

        logger.info(
            "PolynomialMapper loaded from %s (type=%s, shape=%s)",
            path,
            instance.mapper_type,
            matrix.shape,
        )
        return instance
