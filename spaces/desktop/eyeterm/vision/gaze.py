"""Gaze estimation, smoothing, screen mapping, and focus routing."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

import mediapipe as mp
import numpy as np

logger = logging.getLogger(__name__)


# ======================================================================
# Data
# ======================================================================

@dataclass
class GazeResult:
    """Raw gaze estimate produced by GazeEstimator.

    Contains both iris-based gaze (noisy, precise) and nose/ear-based
    head direction (stable, coarse).  Downstream fusion combines them.
    """

    x: float  # iris horizontal ratio 0..1 (left edge .. right edge)
    y: float  # iris vertical ratio 0..1 (top .. bottom)
    head_x: float = 0.5  # nose-ear horizontal ratio 0..1
    head_y: float = 0.5  # nose-ear vertical ratio 0..1
    landmarks: Any = field(repr=False, default=None)  # raw FaceMesh result


# ======================================================================
# GazeEstimator
# ======================================================================

class GazeEstimator:
    """Estimate gaze direction from a single RGB frame using MediaPipe Face Mesh.

    The 478-landmark model (``refine_landmarks=True``) includes iris centres
    and contour points which allow a reasonable gaze-ratio computation without
    a dedicated gaze-tracking model.
    """

    # -- Iris / eye landmark indices ------------------------------------
    LEFT_IRIS_CENTER = 468
    LEFT_EYE_LEFT_CORNER = 33
    LEFT_EYE_RIGHT_CORNER = 133
    LEFT_UPPER_LID = 159
    LEFT_LOWER_LID = 145

    RIGHT_IRIS_CENTER = 473
    RIGHT_EYE_LEFT_CORNER = 362
    RIGHT_EYE_RIGHT_CORNER = 263
    RIGHT_UPPER_LID = 386
    RIGHT_LOWER_LID = 374

    # -- Head pose landmarks (nose + ears) ------------------------------
    NOSE_TIP = 1
    LEFT_EAR_TRAGION = 234   # left ear tragion (stable anchor)
    RIGHT_EAR_TRAGION = 454  # right ear tragion (stable anchor)
    FOREHEAD = 10            # forehead center (vertical reference)
    CHIN = 152               # chin bottom (vertical reference)

    def __init__(self, min_confidence: float = 0.8) -> None:
        self._min_confidence = min_confidence
        self._frame_ts = 0  # monotonic timestamp counter for VIDEO mode

        # mediapipe >= 0.10.30 removed mp.solutions; use Task API (FaceLandmarker)
        import pathlib
        model_path = pathlib.Path(__file__).parent.parent / "models" / "face_landmarker.task"
        if not model_path.exists():
            raise FileNotFoundError(
                f"FaceLandmarker model not found at {model_path}. "
                "Download from: https://storage.googleapis.com/mediapipe-models/"
                "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
            )

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
        )
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate(self, frame_rgb: np.ndarray) -> Optional[GazeResult]:
        """Return a ``GazeResult`` or *None* if no face was detected.

        ``frame_rgb`` must be an RGB image (not BGR).
        """
        logger.debug("estimate called: frame shape=%s", frame_rgb.shape)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        self._frame_ts += 33  # ~30fps timestamp increment (ms)
        results = self._landmarker.detect_for_video(mp_image, self._frame_ts)
        if not results.face_landmarks:
            return None

        lms = results.face_landmarks[0]  # list of NormalizedLandmark

        # -- Confidence gate: check eye geometry is plausible -----------
        # If eye corners are too close (< threshold of image width),
        # the detection is unreliable → skip this frame.
        left_eye_width = abs(lms[self.LEFT_EYE_RIGHT_CORNER].x - lms[self.LEFT_EYE_LEFT_CORNER].x)
        right_eye_width = abs(lms[self.RIGHT_EYE_RIGHT_CORNER].x - lms[self.RIGHT_EYE_LEFT_CORNER].x)
        if left_eye_width < 0.01 or right_eye_width < 0.01:
            return None  # Degenerate eye geometry — skip

        # -- Horizontal ratio per eye -----------------------------------
        left_h = self._horizontal_ratio(
            lms, self.LEFT_IRIS_CENTER, self.LEFT_EYE_LEFT_CORNER, self.LEFT_EYE_RIGHT_CORNER,
        )
        right_h = self._horizontal_ratio(
            lms, self.RIGHT_IRIS_CENTER, self.RIGHT_EYE_LEFT_CORNER, self.RIGHT_EYE_RIGHT_CORNER,
        )

        # -- Vertical ratio per eye -------------------------------------
        left_v = self._vertical_ratio(
            lms, self.LEFT_IRIS_CENTER, self.LEFT_UPPER_LID, self.LEFT_LOWER_LID,
        )
        right_v = self._vertical_ratio(
            lms, self.RIGHT_IRIS_CENTER, self.RIGHT_UPPER_LID, self.RIGHT_LOWER_LID,
        )

        gaze_x = (left_h + right_h) / 2.0
        gaze_y = (left_v + right_v) / 2.0

        # Outlier rejection: if ratio is wildly outside 0..1 range, skip
        if not (-0.1 <= gaze_x <= 1.1 and -0.1 <= gaze_y <= 1.1):
            return None

        # -- Head pose from nose tip + ears -----------------------------
        # Horizontal: nose position relative to ear span (very stable)
        #   0.0 = looking far right, 0.5 = straight, 1.0 = looking far left
        # Vertical: nose position relative to forehead-chin span
        #   0.0 = looking up, 0.5 = straight, 1.0 = looking down
        head_x, head_y = self._head_pose(lms)

        # Mirror correction: webcam is selfie-view (horizontally flipped).
        # Looking RIGHT → iris moves LEFT in image → invert X for both signals.
        gaze_x = 1.0 - gaze_x
        head_x = 1.0 - head_x

        return GazeResult(x=gaze_x, y=gaze_y, head_x=head_x, head_y=head_y, landmarks=lms)

    def close(self) -> None:
        """Release the MediaPipe FaceLandmarker resources."""
        self._landmarker.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _head_pose(self, lms: Any) -> Tuple[float, float]:
        """Compute head direction from nose tip relative to ears and forehead/chin.

        Returns (head_x, head_y) each in ~0..1 range.

        Mathematical model:
          head_x = (nose.x - left_ear.x) / (right_ear.x - left_ear.x)
            → ear span is very stable (bone landmarks), giving a low-noise
              horizontal direction signal.  ~0.5 when looking straight ahead.

          head_y = (nose.y - forehead.y) / (chin.y - forehead.y)
            → forehead-chin span captures vertical head tilt.
              ~0.3-0.4 when looking straight (nose is above midpoint).
        """
        nose = lms[self.NOSE_TIP]
        left_ear = lms[self.LEFT_EAR_TRAGION]
        right_ear = lms[self.RIGHT_EAR_TRAGION]
        forehead = lms[self.FOREHEAD]
        chin = lms[self.CHIN]

        # Horizontal: nose within ear span
        ear_dx = right_ear.x - left_ear.x
        if abs(ear_dx) < 1e-6:
            head_x = 0.5
        else:
            head_x = (nose.x - left_ear.x) / ear_dx

        # Vertical: nose within forehead-chin span
        face_dy = chin.y - forehead.y
        if abs(face_dy) < 1e-6:
            head_y = 0.5
        else:
            head_y = (nose.y - forehead.y) / face_dy

        return (head_x, head_y)

    @staticmethod
    def _horizontal_ratio(lms: Any, iris_idx: int, left_idx: int, right_idx: int) -> float:
        iris = lms[iris_idx]
        left_corner = lms[left_idx]
        right_corner = lms[right_idx]
        denom = right_corner.x - left_corner.x
        if abs(denom) < 1e-6:
            return 0.5
        return (iris.x - left_corner.x) / denom

    @staticmethod
    def _vertical_ratio(lms: Any, iris_idx: int, upper_idx: int, lower_idx: int) -> float:
        iris = lms[iris_idx]
        upper = lms[upper_idx]
        lower = lms[lower_idx]
        denom = lower.y - upper.y
        if abs(denom) < 1e-6:
            return 0.5
        return (iris.y - upper.y) / denom


# ======================================================================
# GazeFusion — combine head pose + eye gaze
# ======================================================================

class GazeFusion:
    """Adaptive fusion of head direction (stable) and eye gaze (precise).

    **Key insight from CSV analysis:** raw head signal (nose/ears) can be
    *noisier* than iris signal at close camera distance.  Therefore the
    head signal is pre-smoothed with its own aggressive OneEuroFilter
    before fusion.  This makes the head channel a truly stable anchor.

    The head_weight adapts automatically based on head movement speed:

    - **Head still** → head_weight drops to ``hw_min`` (0.3)
      → eyes dominate → more precision for fine targeting
    - **Head moving** → head_weight rises to ``hw_max`` (0.7)
      → head dominates → stable during head turns

    Mathematical model::

        head_smooth = OneEuroFilter(head_raw)       # aggressive smoothing
        speed = ||head_smooth(t) - head_smooth(t-1)||
        t = clamp(speed / speed_threshold, 0, 1)
        α = hw_min + t × (hw_max - hw_min)
        fused = α · head_smooth + (1 - α) · eye_raw
    """

    def __init__(
        self,
        head_weight_min: float = 0.3,
        head_weight_max: float = 0.7,
        speed_threshold: float = 0.03,
        head_smooth_freq: float = 30.0,
    ) -> None:
        self._hw_min = head_weight_min
        self._hw_max = head_weight_max
        self._speed_thresh = speed_threshold
        # Pre-smooth head signal (very aggressive — min_cutoff=0.05 is ~20x
        # heavier than the main gaze smoother at 0.15)
        self._head_fx = OneEuroFilter(freq=head_smooth_freq, min_cutoff=0.05, beta=0.001)
        self._head_fy = OneEuroFilter(freq=head_smooth_freq, min_cutoff=0.05, beta=0.001)
        self._prev_shx: Optional[float] = None
        self._prev_shy: Optional[float] = None
        self._current_hw: float = head_weight_min  # exposed for CSV logging

    @property
    def current_head_weight(self) -> float:
        return self._current_hw

    def fuse(self, gaze: GazeResult) -> Tuple[float, float]:
        """Return (fused_x, fused_y) combining head + eye signals."""
        logger.debug("fuse called: eye=(%.3f, %.3f) head=(%.3f, %.3f)", gaze.x, gaze.y, gaze.head_x, gaze.head_y)
        # Pre-smooth head signal (removes nose landmark jitter)
        shx = self._head_fx(gaze.head_x)
        shy = self._head_fy(gaze.head_y)

        # Compute head speed from smoothed signal
        if self._prev_shx is not None:
            speed = math.hypot(shx - self._prev_shx, shy - self._prev_shy)
        else:
            speed = 0.0
        self._prev_shx = shx
        self._prev_shy = shy

        # Blend: still → more eyes (precision), moving → more head (stability)
        t = min(speed / self._speed_thresh, 1.0)
        hw = self._hw_min + t * (self._hw_max - self._hw_min)
        self._current_hw = hw

        ew = 1.0 - hw
        fx = hw * shx + ew * gaze.x
        fy = hw * shy + ew * gaze.y
        return (fx, fy)


# ======================================================================
# One-Euro Filter (adaptive jitter reduction)
# ======================================================================

class OneEuroFilter:
    """Speed-adaptive low-pass filter for noisy gaze signals.

    At low speed (still head) the cutoff frequency drops, producing heavy
    smoothing that eliminates jitter.  At high speed (saccade) the cutoff
    rises so the cursor tracks with minimal lag.

    Reference: Casiez, Roussel & Vogel, *1€ Filter*, CHI 2012.
    """

    def __init__(
        self,
        freq: float = 30.0,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ) -> None:
        self._freq = freq
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._x_prev: Optional[float] = None
        self._dx_prev: float = 0.0

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / self._freq
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x: float) -> float:
        if self._x_prev is None:
            self._x_prev = x
            return x
        te = 1.0 / self._freq
        dx = (x - self._x_prev) / te
        # Smooth the derivative
        a_d = self._alpha(self._d_cutoff)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        self._dx_prev = dx_hat
        # Adaptive cutoff: fast movement → higher cutoff → less smoothing
        cutoff = self._min_cutoff + self._beta * abs(dx_hat)
        a = self._alpha(cutoff)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_prev = x_hat
        return x_hat

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0


# ======================================================================
# GazeSmoother
# ======================================================================

class GazeSmoother:
    """One-Euro filter for gaze coordinates (x and y filtered independently).

    Replaces the old EMA-only smoother.  The ``alpha`` parameter is accepted
    for backward-compat but ignored — the One-Euro filter uses ``min_cutoff``
    and ``beta`` instead.
    """

    def __init__(
        self,
        alpha: float = 0.3,  # kept for API compat, unused
        freq: float = 30.0,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
    ) -> None:
        self._fx = OneEuroFilter(freq=freq, min_cutoff=min_cutoff, beta=beta)
        self._fy = OneEuroFilter(freq=freq, min_cutoff=min_cutoff, beta=beta)

    def smooth(self, raw: Tuple[float, float]) -> Tuple[float, float]:
        """Apply One-Euro filter and return the smoothed (x, y)."""
        return (self._fx(raw[0]), self._fy(raw[1]))

    def reset(self) -> None:
        """Clear internal state so the next sample is treated as the first."""
        self._fx.reset()
        self._fy.reset()


# ======================================================================
# GazeToScreen
# ======================================================================

class GazeToScreen:
    """Map normalised gaze ratios to screen pixel coordinates.

    If a ``calibration_matrix`` (2x3 ndarray) is supplied the mapping is an
    affine transform.  Otherwise the gaze range is auto-learned during the
    first ~3 seconds and then normalised so that the full screen is reachable.

    The iris ratio from MediaPipe typically covers only ~0.2–0.8 (the eye
    cannot rotate past its corners).  Without range normalisation this means
    the outer ~20% of the screen is unreachable.  Auto-range fixes this by
    collecting samples and remapping the observed 5th–95th percentile (plus
    a 10% margin) to the full screen dimensions.
    """

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        calibration_matrix: Optional[np.ndarray] = None,
        gaze_range_x: Tuple[float, float] = (0.20, 0.80),
        gaze_range_y: Tuple[float, float] = (0.25, 0.75),
    ) -> None:
        self._sw = screen_width
        self._sh = screen_height
        self._cal: Optional[np.ndarray] = calibration_matrix
        # Gaze range defaults (overridden by continuous expansion)
        self._gx_min, self._gx_max = gaze_range_x
        self._gy_min, self._gy_max = gaze_range_y
        # Continuous range expansion (only when no calibration matrix)
        self._auto_range = calibration_matrix is None

    @property
    def _screen_width(self) -> int:
        return self._sw

    @property
    def _screen_height(self) -> int:
        return self._sh

    def set_calibration(self, matrix: np.ndarray) -> None:
        """Update the calibration matrix (2x3 ndarray)."""
        self._cal = matrix
        self._auto_range = False  # calibration overrides auto-range

    def to_screen(self, gaze_x: float, gaze_y: float) -> Tuple[int, int]:
        """Return ``(px_x, px_y)`` clamped to the screen bounds."""
        if self._cal is not None:
            vec = np.array([gaze_x, gaze_y, 1.0])
            mapped = self._cal @ vec  # shape (2,)
            sx = int(np.clip(mapped[0], 0, self._sw - 1))
            sy = int(np.clip(mapped[1], 0, self._sh - 1))
        else:
            # Continuous range expansion: grow range when new extremes seen
            if self._auto_range:
                self._expand_range(gaze_x, gaze_y)
            # Normalise from observed range to 0..1
            rx = self._gx_max - self._gx_min
            ry = self._gy_max - self._gy_min
            nx = (gaze_x - self._gx_min) / max(rx, 0.01)
            ny = (gaze_y - self._gy_min) / max(ry, 0.01)
            sx = int(np.clip(nx * self._sw, 0, self._sw - 1))
            sy = int(np.clip(ny * self._sh, 0, self._sh - 1))
        return (sx, sy)

    def _expand_range(self, gx: float, gy: float) -> None:
        """Continuously expand the gaze range when new extremes are observed.

        Unlike the old learn-then-lock approach (3s window), this expands
        the range gradually as the user looks further.  Range only grows,
        never shrinks — so the usable screen area increases over time.
        A small margin (2%) is added on each expansion to prevent the
        cursor from being stuck at the exact edge.
        """
        margin = 0.02
        expanded = False
        if gx < self._gx_min:
            self._gx_min = gx - margin
            expanded = True
        if gx > self._gx_max:
            self._gx_max = gx + margin
            expanded = True
        if gy < self._gy_min:
            self._gy_min = gy - margin
            expanded = True
        if gy > self._gy_max:
            self._gy_max = gy + margin
            expanded = True
        if expanded:
            logger.debug(
                "Range expanded: x=[%.3f, %.3f] y=[%.3f, %.3f]",
                self._gx_min, self._gx_max, self._gy_min, self._gy_max,
            )


# ======================================================================
# FocusRouter
# ======================================================================

class FocusRouter:
    """Map a screen point to a pane index (2x2 grid) with dwell gating.

    A pane change is only reported once the user's gaze has remained in the
    same region for at least ``dwell_ms`` milliseconds.
    """

    def __init__(self, num_panes: int = 4, dwell_ms: int = 300,
                 screen_width: int = 1920, screen_height: int = 1080) -> None:
        if num_panes not in (1, 2, 4):
            raise ValueError("num_panes must be 1, 2, or 4")
        self._num_panes = num_panes
        self._dwell_ms = dwell_ms
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._mid_x = screen_width // 2
        self._mid_y = screen_height // 2
        self._current_pane: Optional[int] = None
        self._candidate_pane: Optional[int] = None
        self._candidate_start: Optional[int] = None

    def update(self, screen_x: int, screen_y: int, timestamp_ms: int) -> Optional[int]:
        """Return the pane index if the dwell threshold is met, else *None*.

        Pane layout for ``num_panes=4`` (2x2 grid)::

            0 | 1
            -----
            2 | 3
        """
        logger.debug("update called: screen=(%s, %s) ts=%s", screen_x, screen_y, timestamp_ms)
        pane = self._point_to_pane(screen_x, screen_y)

        if pane == self._current_pane:
            # Already focused on this pane — nothing to report.
            self._candidate_pane = None
            self._candidate_start = None
            return None

        if pane != self._candidate_pane:
            # New candidate region — start the dwell timer.
            self._candidate_pane = pane
            self._candidate_start = timestamp_ms
            return None

        # Same candidate — check dwell duration.
        assert self._candidate_start is not None
        elapsed = timestamp_ms - self._candidate_start
        if elapsed >= self._dwell_ms:
            self._current_pane = pane
            self._candidate_pane = None
            self._candidate_start = None
            return pane

        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def get_current_pane(self, screen_x: int, screen_y: int) -> int:
        """Return which pane a screen point falls in (no dwell gating)."""
        return self._point_to_pane(screen_x, screen_y)

    def _point_to_pane(self, sx: int, sy: int) -> int:
        if self._num_panes == 1:
            return 0
        if self._num_panes == 2:
            return 0 if sx < self._mid_x else 1
        # 4-pane 2x2 grid
        col = 0 if sx < self._mid_x else 1
        row = 0 if sy < self._mid_y else 1
        return row * 2 + col
