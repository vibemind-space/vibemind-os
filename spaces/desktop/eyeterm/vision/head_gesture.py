"""HeadGestureDetector — detect nod (yes) and shake (no) head gestures.

Uses peak detection on head_y (nod) and head_x (shake) signals to identify
oscillation patterns. A gesture requires 2-3 direction reversals within a
time window.

            head_y
              ▲       ╱╲
    nod:      │     ╱    ╲     ╱╲
              │   ╱        ╲ ╱    ╲
              └──────────────────────► time

            head_x
              ▲       ╱╲       ╱╲
    shake:    │     ╱    ╲   ╱    ╲
              │   ╱        ╲╱       ╲
              └──────────────────────► time
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

logger = logging.getLogger("eyeterm.head_gesture")


class HeadGestureDetector:
    """Detect head nod and shake gestures from head pose ratios.

    Parameters
    ----------
    nod_amplitude : float
        Minimum head_y change per reversal to count as nod (default 0.06).
    shake_amplitude : float
        Minimum head_x change per reversal to count as shake (default 0.08).
    min_reversals : int
        Minimum direction reversals for a gesture (default 2).
    window_s : float
        Time window in which reversals must occur (default 1.5).
    cooldown_s : float
        Cooldown after a confirmed gesture (default 2.0).
    smoothing : float
        EMA smoothing factor for raw signal (default 0.4).
    """

    def __init__(
        self,
        nod_amplitude: float = 0.06,
        shake_amplitude: float = 0.08,
        min_reversals: int = 2,
        window_s: float = 1.5,
        cooldown_s: float = 2.0,
        smoothing: float = 0.4,
    ) -> None:
        self._nod_amp = nod_amplitude
        self._shake_amp = shake_amplitude
        self._min_reversals = min_reversals
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._smoothing = smoothing

        # Per-axis state
        self._y_tracker = _AxisTracker(nod_amplitude, min_reversals, window_s, smoothing)
        self._x_tracker = _AxisTracker(shake_amplitude, min_reversals, window_s, smoothing)

        self._last_gesture_time: float = 0.0

    def update(self, head_x: float, head_y: float) -> Optional[str]:
        """Feed per-frame head pose. Returns ``"nod"``, ``"shake"``, or ``None``."""
        now = time.monotonic()

        # Cooldown check
        if now - self._last_gesture_time < self._cooldown_s:
            # Still consume data to keep trackers warm
            self._y_tracker.update(head_y, now)
            self._x_tracker.update(head_x, now)
            return None

        nod = self._y_tracker.update(head_y, now)
        shake = self._x_tracker.update(head_x, now)

        if nod:
            self._last_gesture_time = now
            self._y_tracker.reset()
            self._x_tracker.reset()
            logger.info("Gesture detected: NOD")
            return "nod"

        if shake:
            self._last_gesture_time = now
            self._y_tracker.reset()
            self._x_tracker.reset()
            logger.info("Gesture detected: SHAKE")
            return "shake"

        return None


class _AxisTracker:
    """Track direction reversals on a single axis."""

    def __init__(self, amplitude: float, min_reversals: int,
                 window_s: float, smoothing: float) -> None:
        self._amplitude = amplitude
        self._min_reversals = min_reversals
        self._window_s = window_s
        self._alpha = smoothing

        self._smoothed: Optional[float] = None
        self._prev_smoothed: Optional[float] = None
        self._direction: int = 0  # +1 = rising, -1 = falling, 0 = unknown
        self._peak_value: float = 0.0

        # Reversal timestamps
        self._reversals: deque[float] = deque()

    def update(self, value: float, now: float) -> bool:
        """Update with new value. Returns True if gesture detected."""
        # EMA smoothing
        if self._smoothed is None:
            self._smoothed = value
            return False

        self._prev_smoothed = self._smoothed
        self._smoothed = self._alpha * value + (1 - self._alpha) * self._smoothed

        # Determine current direction
        delta = self._smoothed - self._prev_smoothed
        if abs(delta) < 0.001:
            return False  # No significant movement

        new_dir = 1 if delta > 0 else -1

        # Detect reversal
        if self._direction != 0 and new_dir != self._direction:
            # Check amplitude since last reversal
            amplitude = abs(self._smoothed - self._peak_value)
            if amplitude >= self._amplitude:
                self._reversals.append(now)
                self._peak_value = self._smoothed

                # Trim old reversals
                cutoff = now - self._window_s
                while self._reversals and self._reversals[0] < cutoff:
                    self._reversals.popleft()

                # Check if enough reversals in window
                if len(self._reversals) >= self._min_reversals:
                    return True
        elif new_dir != self._direction:
            self._peak_value = self._smoothed

        self._direction = new_dir
        return False

    def reset(self) -> None:
        """Reset after gesture detected."""
        self._reversals.clear()
        self._direction = 0
        self._peak_value = 0.0
