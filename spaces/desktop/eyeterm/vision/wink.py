"""Wink detection via Eye Aspect Ratio (EAR) on MediaPipe Face Mesh landmarks."""

from __future__ import annotations

import logging
import math
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class WinkDetector:
    """Detect deliberate single-eye winks while ignoring natural blinks.

    * Left wink  (left EAR low, right EAR normal) for ``min_frames`` consecutive
      updates  ->  ``"confirm"``
    * Right wink (right EAR low, left EAR normal) for ``min_frames`` consecutive
      updates  ->  ``"cancel"``
    * Both eyes low  ->  natural blink, ignored.
    * A cooldown period prevents rapid-fire detections.
    """

    # -- Landmark indices for EAR calculation ---------------------------
    # Left eye
    L_P1 = 33
    L_P2 = 160
    L_P3 = 158
    L_P4 = 133
    L_P5 = 153
    L_P6 = 144

    # Right eye
    R_P1 = 362
    R_P2 = 385
    R_P3 = 387
    R_P4 = 263
    R_P5 = 373
    R_P6 = 380

    def __init__(
        self,
        ear_threshold: float = 0.21,
        min_frames: int = 3,
        cooldown_ms: int = 600,
    ) -> None:
        self._threshold = ear_threshold
        self._min_frames = min_frames
        self._cooldown_ms = cooldown_ms

        self._left_wink_count: int = 0
        self._right_wink_count: int = 0
        self._last_trigger_ts: Optional[int] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, landmarks: Any, timestamp_ms: int) -> Optional[str]:
        """Process a new frame's landmarks.

        ``landmarks`` is ``face_mesh_results.multi_face_landmarks[0].landmark``
        (a list-like of normalised landmarks).

        Returns ``"confirm"``, ``"cancel"``, or ``None``.
        """
        logger.debug("update called: ts=%s", timestamp_ms)
        left_ear, right_ear = self.get_ear_values(landmarks)

        left_closed = left_ear < self._threshold
        right_closed = right_ear < self._threshold

        # Both closed -> natural blink, reset counters.
        if left_closed and right_closed:
            self._left_wink_count = 0
            self._right_wink_count = 0
            return None

        # Left wink: left closed, right open.
        if left_closed and not right_closed:
            self._left_wink_count += 1
            self._right_wink_count = 0
        # Right wink: right closed, left open.
        elif right_closed and not left_closed:
            self._right_wink_count += 1
            self._left_wink_count = 0
        else:
            # Both open — reset.
            self._left_wink_count = 0
            self._right_wink_count = 0
            return None

        # Check cooldown.
        if self._last_trigger_ts is not None:
            if (timestamp_ms - self._last_trigger_ts) < self._cooldown_ms:
                return None

        # Emit event if threshold met.
        if self._left_wink_count >= self._min_frames:
            self._left_wink_count = 0
            self._last_trigger_ts = timestamp_ms
            return "confirm"

        if self._right_wink_count >= self._min_frames:
            self._right_wink_count = 0
            self._last_trigger_ts = timestamp_ms
            return "cancel"

        return None

    @classmethod
    def get_ear_values(cls, landmarks: Any) -> Tuple[float, float]:
        """Return ``(left_ear, right_ear)`` for the given landmarks.

        Useful for debug overlays that want to display the live EAR values.
        """
        left_ear = cls._ear(
            landmarks, cls.L_P1, cls.L_P2, cls.L_P3, cls.L_P4, cls.L_P5, cls.L_P6,
        )
        right_ear = cls._ear(
            landmarks, cls.R_P1, cls.R_P2, cls.R_P3, cls.R_P4, cls.R_P5, cls.R_P6,
        )
        return (left_ear, right_ear)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _dist(a: Any, b: Any) -> float:
        """Euclidean distance between two normalised landmarks."""
        return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)

    @classmethod
    def _ear(cls, lms: Any, p1: int, p2: int, p3: int, p4: int, p5: int, p6: int) -> float:
        """Eye Aspect Ratio.

        EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
        """
        vertical_a = cls._dist(lms[p2], lms[p6])
        vertical_b = cls._dist(lms[p3], lms[p5])
        horizontal = cls._dist(lms[p1], lms[p4])
        if horizontal < 1e-6:
            return 0.0
        return (vertical_a + vertical_b) / (2.0 * horizontal)
