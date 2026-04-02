"""Calibration: interactive 5-point runner + headless 9-point state machine."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

from .camera import CameraCapture
from .gaze import GazeEstimator

logger = logging.getLogger(__name__)

# Default path for persisted calibration matrix
# __file__ = .../python/spaces/desktop/eyeterm/vision/calibrate.py
# We want: .../python/config/eyeterm_calibration.json
_CALIBRATION_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "config" / "eyeterm_calibration.json"

# Number of gaze samples collected per calibration point.
_SAMPLES_PER_POINT = 30


class CalibrationRunner:
    """Collect gaze samples at known screen positions and fit an affine mapping.

    The five calibration points are spread across the screen corners and centre.
    For each point the user fixates on it and confirms with a wink (or a key
    press, depending on the ``draw_callback`` integration).  The runner then
    fits a 2x3 affine matrix via least-squares so that
    ``[screen_x, screen_y]^T = M @ [gaze_x, gaze_y, 1]^T``.
    """

    POINTS: List[Tuple[float, float]] = [
        (0.1, 0.1),
        (0.9, 0.1),
        (0.5, 0.5),
        (0.1, 0.9),
        (0.9, 0.9),
    ]

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self._sw = screen_width
        self._sh = screen_height
        self._matrix: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Calibration routine
    # ------------------------------------------------------------------

    def run_calibration(
        self,
        gaze_estimator: GazeEstimator,
        camera: CameraCapture,
        draw_callback: Callable[[int, int, int, int], bool],
    ) -> Optional[np.ndarray]:
        """Run the interactive calibration loop.

        ``draw_callback(point_idx, screen_x, screen_y, collected)`` is called
        each iteration so the host application can render the target dot and
        any progress indicator.  It must return ``True`` to confirm that a
        sample should be captured (e.g. the user pressed a key or winked), or
        ``False`` to keep waiting.

        Returns the fitted 2x3 affine matrix, or *None* if calibration could
        not be completed (e.g. camera failure).
        """
        gaze_points: List[Tuple[float, float]] = []
        screen_targets: List[Tuple[float, float]] = []

        for idx, (rx, ry) in enumerate(self.POINTS):
            target_x = int(rx * self._sw)
            target_y = int(ry * self._sh)

            samples_x: List[float] = []
            samples_y: List[float] = []

            while len(samples_x) < _SAMPLES_PER_POINT:
                frame = camera.read()
                if frame is None:
                    logger.warning("Camera read failed during calibration.")
                    return None

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = gaze_estimator.estimate(frame_rgb)

                should_capture = draw_callback(idx, target_x, target_y, len(samples_x))

                if result is not None and should_capture:
                    samples_x.append(result.x)
                    samples_y.append(result.y)

            avg_gx = float(np.mean(samples_x))
            avg_gy = float(np.mean(samples_y))
            gaze_points.append((avg_gx, avg_gy))
            screen_targets.append((float(target_x), float(target_y)))

        # -- Fit affine matrix via least-squares -------------------------
        #    screen = M @ [gaze_x, gaze_y, 1]^T
        #    Build A (Nx3) and B (Nx2), solve for M^T (3x2).
        n = len(gaze_points)
        A = np.zeros((n, 3), dtype=np.float64)
        B = np.zeros((n, 2), dtype=np.float64)
        for i in range(n):
            A[i] = [gaze_points[i][0], gaze_points[i][1], 1.0]
            B[i] = [screen_targets[i][0], screen_targets[i][1]]

        # lstsq returns (solution, residuals, rank, sv)
        solution, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
        # solution shape: (3, 2) — transpose to get (2, 3)
        self._matrix = solution.T.copy()

        logger.info("Calibration complete. Matrix:\n%s", self._matrix)
        return self._matrix

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save the calibration matrix to a JSON file."""
        if self._matrix is None:
            raise RuntimeError("No calibration matrix to save. Run calibration first.")
        data = {"matrix": self._matrix.tolist()}
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Calibration saved to %s", path)

    def load(self, path: str) -> np.ndarray:
        """Load a calibration matrix from a JSON file and return it."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self._matrix = np.array(raw["matrix"], dtype=np.float64)
        if self._matrix.shape != (2, 3):
            raise ValueError(f"Expected (2,3) matrix, got {self._matrix.shape}")
        logger.info("Calibration loaded from %s", path)
        return self._matrix


# ======================================================================
# Headless 9-point calibration (non-blocking state machine)
# ======================================================================

class HeadlessCalibrationManager:
    """Non-blocking 9-point calibration for headless mode.

    Runs as a state machine inside ``EyeTermHeadless._tick()``.
    Each frame, call ``tick(fused_x, fused_y)`` with the fused gaze signal.

    State flow::

        INACTIVE → COUNTDOWN (1s) → COLLECTING (2s) → ADVANCING
            → [next point → COUNTDOWN] or [all done → FITTING → INACTIVE]

    On re-calibration the new matrix is merged with the old one
    (70% new + 30% old) to correct drift without losing prior data.
    """

    POINTS_9: List[Tuple[float, float]] = [
        (0.10, 0.10), (0.50, 0.10), (0.90, 0.10),
        (0.10, 0.50), (0.50, 0.50), (0.90, 0.50),
        (0.10, 0.90), (0.50, 0.90), (0.90, 0.90),
    ]

    INSTRUCTIONS: List[str] = [
        "Schau nach OBEN LINKS",
        "Schau nach OBEN MITTE",
        "Schau nach OBEN RECHTS",
        "Schau nach LINKS MITTE",
        "Schau in die MITTE",
        "Schau nach RECHTS MITTE",
        "Schau nach UNTEN LINKS",
        "Schau nach UNTEN MITTE",
        "Schau nach UNTEN RECHTS",
    ]

    _COUNTDOWN_FRAMES = 30   # 1s settle time
    _COLLECT_FRAMES = 60     # 2s sample collection

    def __init__(self) -> None:
        self._state = "inactive"
        self._point_index = 0
        self._frame_counter = 0
        self._samples: List[Tuple[float, float]] = []
        self._collected: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        self._old_matrix: Optional[np.ndarray] = None
        self._result_matrix: Optional[np.ndarray] = None
        self._broadcast: Optional[callable] = None
        self._sw = 1920
        self._sh = 1080

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        screen_width: int,
        screen_height: int,
        old_matrix: Optional[np.ndarray] = None,
        broadcast_fn: Optional[callable] = None,
    ) -> None:
        """Begin 9-point calibration sequence."""
        logger.debug("start called: screen=%sx%s", screen_width, screen_height)
        self._sw = screen_width
        self._sh = screen_height
        self._old_matrix = old_matrix
        self._broadcast = broadcast_fn
        self._result_matrix = None
        self._point_index = 0
        self._frame_counter = 0
        self._samples = []
        self._collected = []
        self._state = "countdown"
        logger.debug(
            "Calibration started (%s points, screen=%sx%s)",
            len(self.POINTS_9), screen_width, screen_height,
        )
        self._send_target()

    def _send_target(self) -> None:
        """Send current calibration target to Electron overlay."""
        if not self._broadcast or self._point_index >= len(self.POINTS_9):
            return
        rx, ry = self.POINTS_9[self._point_index]
        self._broadcast({
            "type": "calibration_target",
            "x": int(rx * self._sw),
            "y": int(ry * self._sh),
            "index": self._point_index,
            "total": len(self.POINTS_9),
        })

    @property
    def is_active(self) -> bool:
        return self._state != "inactive"

    @property
    def current_instruction(self) -> str:
        if self._point_index < len(self.INSTRUCTIONS):
            return self.INSTRUCTIONS[self._point_index]
        return ""

    @property
    def current_point_index(self) -> int:
        return self._point_index

    @property
    def total_points(self) -> int:
        return len(self.POINTS_9)

    @property
    def progress_fraction(self) -> float:
        """0.0..1.0 progress within current point (countdown + collection)."""
        total = self._COUNTDOWN_FRAMES + self._COLLECT_FRAMES
        if self._state == "countdown":
            return self._frame_counter / total
        elif self._state == "collecting":
            return (self._COUNTDOWN_FRAMES + self._frame_counter) / total
        return 1.0

    @property
    def result_matrix(self) -> Optional[np.ndarray]:
        return self._result_matrix

    # ------------------------------------------------------------------
    # Frame-by-frame tick
    # ------------------------------------------------------------------

    def tick(self, fused_x: float, fused_y: float) -> None:
        """Advance the calibration state machine by one frame."""
        if self._state == "inactive":
            return

        self._frame_counter += 1

        if self._state == "countdown":
            if self._frame_counter >= self._COUNTDOWN_FRAMES:
                self._state = "collecting"
                self._frame_counter = 0
                self._samples = []

        elif self._state == "collecting":
            self._samples.append((fused_x, fused_y))
            if self._frame_counter >= self._COLLECT_FRAMES:
                self._state = "advancing"
                self._frame_counter = 0

        elif self._state == "advancing":
            # Compute robust mean for this point
            mean_x, mean_y = self._robust_mean(self._samples)
            rx, ry = self.POINTS_9[self._point_index]
            screen_x = rx * self._sw
            screen_y = ry * self._sh
            self._collected.append(((mean_x, mean_y), (screen_x, screen_y)))
            logger.debug(
                "Point %s/%s: gaze=(%.3f, %.3f) -> screen=(%.0f, %.0f)",
                self._point_index + 1, len(self.POINTS_9),
                mean_x, mean_y, screen_x, screen_y,
            )

            self._point_index += 1
            if self._point_index < len(self.POINTS_9):
                self._state = "countdown"
                self._frame_counter = 0
                self._send_target()  # show next dot on screen
            else:
                self._do_fitting()

        elif self._state == "fitting":
            self._do_fitting()

    def _do_fitting(self) -> None:
        """Compute affine matrix, optionally merge with old, go inactive."""
        try:
            new_matrix = self._fit_affine()
            if self._old_matrix is not None:
                self._result_matrix = self.merge_matrices(self._old_matrix, new_matrix)
                logger.debug("Calibration merged with previous matrix (30%% old + 70%% new)")
            else:
                self._result_matrix = new_matrix
            logger.debug("Calibration matrix:\n%s", self._result_matrix)
        except Exception as e:
            logger.debug("Calibration fitting failed: %s", e)
            self._result_matrix = self._old_matrix  # keep old if fitting fails
        self._state = "inactive"
        # Remove calibration overlay from screen
        if self._broadcast:
            self._broadcast({"type": "calibration_done"})

    # ------------------------------------------------------------------
    # Math
    # ------------------------------------------------------------------

    def _fit_affine(self) -> np.ndarray:
        """Least-squares affine fit: screen = M @ [gaze_x, gaze_y, 1]."""
        n = len(self._collected)
        A = np.zeros((n, 3), dtype=np.float64)
        B = np.zeros((n, 2), dtype=np.float64)
        for i, (gaze, screen) in enumerate(self._collected):
            A[i] = [gaze[0], gaze[1], 1.0]
            B[i] = [screen[0], screen[1]]
        solution, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
        return solution.T.copy()  # shape (2, 3)

    @staticmethod
    def _robust_mean(samples: List[Tuple[float, float]]) -> Tuple[float, float]:
        """Mean after discarding outliers beyond 2 standard deviations."""
        if len(samples) < 5:
            xs = [s[0] for s in samples]
            ys = [s[1] for s in samples]
            return (float(np.mean(xs)), float(np.mean(ys)))

        xs = np.array([s[0] for s in samples])
        ys = np.array([s[1] for s in samples])
        # Filter by median absolute deviation
        mx, my = np.median(xs), np.median(ys)
        sx, sy = np.std(xs), np.std(ys)
        mask = (np.abs(xs - mx) < 2 * max(sx, 0.001)) & (np.abs(ys - my) < 2 * max(sy, 0.001))
        if mask.sum() < 3:
            mask[:] = True  # not enough inliers, keep all
        return (float(np.mean(xs[mask])), float(np.mean(ys[mask])))

    @staticmethod
    def merge_matrices(
        old: np.ndarray, new: np.ndarray, new_weight: float = 0.7,
    ) -> np.ndarray:
        """Weighted merge: result = new_weight * new + (1 - new_weight) * old."""
        return new_weight * new + (1.0 - new_weight) * old

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def save_calibration(
        cls, matrix: np.ndarray, path: Optional[Path] = None,
    ) -> None:
        """Save calibration matrix to JSON."""
        p = path or _CALIBRATION_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"matrix": matrix.tolist()}, indent=2), encoding="utf-8")
        logger.debug("Calibration saved to %s", p)

    @classmethod
    def load_calibration(
        cls, path: Optional[Path] = None,
    ) -> Optional[np.ndarray]:
        """Load calibration matrix from JSON, or None if not found."""
        p = path or _CALIBRATION_PATH
        if not p.exists():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            m = np.array(raw["matrix"], dtype=np.float64)
            if m.shape != (2, 3):
                return None
            return m
        except Exception:
            return None
