"""BlinkTracker — blink rate and fatigue score from EAR values.

Tracks natural blinks (both eyes closed simultaneously) over a sliding
window and derives a fatigue score.

Normal blink rate: 15-20 blinks/min
Fatigue indicators: <10 (staring/dry eyes) or >25 (excessive blinking)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional, Tuple

logger = logging.getLogger("eyeterm.blink_tracker")


class BlinkTracker:
    """Track blink rate and compute fatigue score from EAR values.

    Parameters
    ----------
    ear_threshold : float
        EAR below this = eye closed (default 0.21, matches WinkDetector).
    min_blink_frames : int
        Minimum consecutive frames both eyes must be closed (default 2).
    max_blink_frames : int
        Maximum frames for a natural blink (longer = intentional close, default 8).
    window_s : float
        Sliding window in seconds for blink rate calculation (default 60.0).
    broadcast_interval_s : float
        Seconds between fatigue broadcasts (default 10.0).
    """

    def __init__(
        self,
        ear_threshold: float = 0.21,
        min_blink_frames: int = 2,
        max_blink_frames: int = 8,
        window_s: float = 60.0,
        broadcast_interval_s: float = 10.0,
    ) -> None:
        self._ear_threshold = ear_threshold
        self._min_blink_frames = min_blink_frames
        self._max_blink_frames = max_blink_frames
        self._window_s = window_s
        self._broadcast_interval = broadcast_interval_s

        # Blink detection state
        self._both_closed_frames: int = 0
        self._in_blink: bool = False

        # Blink timestamps (sliding window)
        self._blinks: deque[float] = deque()

        # Broadcast timing
        self._last_broadcast: float = 0.0

    def update(self, left_ear: float, right_ear: float) -> Optional[dict]:
        """Feed per-frame EAR values. Returns broadcast dict every N seconds, else None."""
        now = time.monotonic()
        both_closed = left_ear < self._ear_threshold and right_ear < self._ear_threshold

        if both_closed:
            self._both_closed_frames += 1
        else:
            # Rising edge: eyes just opened
            if self._both_closed_frames >= self._min_blink_frames:
                if self._both_closed_frames <= self._max_blink_frames:
                    # Natural blink detected
                    self._blinks.append(now)
            self._both_closed_frames = 0

        # Trim old blinks outside window
        cutoff = now - self._window_s
        while self._blinks and self._blinks[0] < cutoff:
            self._blinks.popleft()

        # Broadcast periodically
        if now - self._last_broadcast >= self._broadcast_interval:
            self._last_broadcast = now
            rate = self.blink_rate
            score = self.fatigue_score
            return {
                "type": "eyeterm_fatigue",
                "blink_rate": round(rate, 1),
                "fatigue_score": round(score, 2),
                "blinks_in_window": len(self._blinks),
            }

        return None

    @property
    def blink_rate(self) -> float:
        """Blinks per minute (extrapolated from window)."""
        if not self._blinks:
            return 0.0
        count = len(self._blinks)
        return count * (60.0 / self._window_s)

    @property
    def fatigue_score(self) -> float:
        """Fatigue score 0.0 (alert) to 1.0 (fatigued).

        Normal range: 15-20 blinks/min → score ~0.0
        Low (<10): staring/concentration → moderate fatigue (0.4-0.6)
        High (>25): excessive blinking → high fatigue (0.6-1.0)
        """
        rate = self.blink_rate
        if rate == 0.0:
            return 0.0  # No data yet

        # Normal range: 12-22 blinks/min → score near 0
        if 12.0 <= rate <= 22.0:
            return 0.0

        # Below normal: staring/dry eyes
        if rate < 12.0:
            # 0 blinks → 0.8, 12 blinks → 0.0
            return min(1.0, (12.0 - rate) / 15.0)

        # Above normal: excessive blinking
        # 22 blinks → 0.0, 40+ blinks → 1.0
        return min(1.0, (rate - 22.0) / 18.0)
