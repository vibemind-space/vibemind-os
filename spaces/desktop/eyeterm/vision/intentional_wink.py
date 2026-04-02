"""IntentionalWinkDetector — velocity & asymmetry-based wink classification.

Distinguishes intentional winks from natural blinks by measuring:
1. EAR closing velocity (natural blinks are fast, intentional winks are slower)
2. Asymmetry duration (one eye stays open while the other closes)
3. Both-eyes-closed duration (>400ms = intentional gesture, not blink)

Uses an adaptive EAR baseline so the threshold adjusts to each user's eyes.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from typing import Any, Optional, Tuple

from .wink import WinkDetector

logger = logging.getLogger("eyeterm.intentional_wink")


class IntentionalWinkDetector:
    """Deflection-aware wink detector that wraps WinkDetector's EAR computation.

    Parameters
    ----------
    velocity_threshold : float
        EAR change per second — below this = intentional (default 1.5).
    asymmetry_min_ms : int
        Min ms of asymmetry required for wink (default 150).
    both_closed_min_ms : int
        Min ms of both-eyes-closed for intentional gesture (default 400).
    both_closed_max_ms : int
        Max ms — beyond this assume user is just resting eyes (default 2000).
    cooldown_ms : int
        Cooldown between detected events (default 800).
    baseline_ema_alpha : float
        EMA smoothing for open-eye baseline (default 0.01).
    buffer_size : int
        EAR ring buffer size in frames (default 30 ≈ 1s at 30fps).
    """

    def __init__(
        self,
        velocity_threshold: float = 1.5,
        asymmetry_min_ms: int = 150,
        both_closed_min_ms: int = 400,
        both_closed_max_ms: int = 2000,
        cooldown_ms: int = 800,
        baseline_ema_alpha: float = 0.01,
        buffer_size: int = 30,
    ) -> None:
        self._velocity_thresh = velocity_threshold
        self._asymmetry_min_ms = asymmetry_min_ms
        self._both_closed_min_ms = both_closed_min_ms
        self._both_closed_max_ms = both_closed_max_ms
        self._cooldown_ms = cooldown_ms
        self._baseline_alpha = baseline_ema_alpha

        # EAR ring buffer: (timestamp_ms, left_ear, right_ear)
        self._buffer: deque[Tuple[int, float, float]] = deque(maxlen=buffer_size)

        # Adaptive baseline (open-eye EAR average)
        self._baseline_left: float = 0.28   # typical open-eye EAR
        self._baseline_right: float = 0.28
        self._baseline_initialized: bool = False
        self._baseline_samples: int = 0

        # Threshold derived from baseline
        self._threshold_frac: float = 0.65  # closed = baseline * 0.65

        # Asymmetry tracking
        self._asymmetry_start_ms: int = 0   # when one eye closed, other open
        self._asymmetry_side: Optional[str] = None  # "left" or "right"

        # Both-closed tracking
        self._both_closed_start_ms: int = 0

        # Cooldown
        self._last_event_ms: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def threshold(self) -> float:
        """Current adaptive EAR threshold for 'eye closed'."""
        avg_baseline = (self._baseline_left + self._baseline_right) / 2
        return avg_baseline * self._threshold_frac

    @property
    def baseline(self) -> Tuple[float, float]:
        """Current (left, right) open-eye EAR baseline."""
        return (self._baseline_left, self._baseline_right)

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    def update(self, landmarks: Any, timestamp_ms: int) -> Optional[str]:
        """Process one frame. Returns event or None.

        Returns
        -------
        ``"confirm"`` — intentional left wink (left eye closed, right open)
        ``"cancel"`` — intentional right wink (right eye closed, left open)
        ``"both_closed"`` — intentional both-eyes-closed gesture
        ``None`` — no event (natural blink or no wink)
        """
        left_ear, right_ear = WinkDetector.get_ear_values(landmarks)
        self._buffer.append((timestamp_ms, left_ear, right_ear))

        # Update adaptive baseline (only when both eyes clearly open)
        thresh = self.threshold
        if left_ear > thresh * 1.3 and right_ear > thresh * 1.3:
            self._update_baseline(left_ear, right_ear)

        # Classify eye states
        left_closed = left_ear < thresh
        right_closed = right_ear < thresh

        # Cooldown check
        if (timestamp_ms - self._last_event_ms) < self._cooldown_ms:
            # Still track state for when cooldown expires, but don't emit
            self._track_state(left_closed, right_closed, timestamp_ms)
            return None

        # Both eyes closed
        if left_closed and right_closed:
            return self._handle_both_closed(timestamp_ms)

        # One eye closed (asymmetric)
        if left_closed and not right_closed:
            return self._handle_asymmetry("left", left_ear, timestamp_ms)
        if right_closed and not left_closed:
            return self._handle_asymmetry("right", right_ear, timestamp_ms)

        # Both open — reset tracking
        self._reset_tracking()
        return None

    def get_ear_values(self, landmarks: Any) -> Tuple[float, float]:
        """Convenience wrapper for EAR values."""
        return WinkDetector.get_ear_values(landmarks)

    # ------------------------------------------------------------------
    # Internal: asymmetry detection
    # ------------------------------------------------------------------

    def _handle_asymmetry(self, side: str, closed_ear: float, ts_ms: int) -> Optional[str]:
        """Handle one-eye-closed state."""
        if self._asymmetry_side != side:
            # New asymmetry — start tracking
            self._asymmetry_start_ms = ts_ms
            self._asymmetry_side = side
            self._both_closed_start_ms = 0
            return None

        # Same side continuing — check duration
        duration_ms = ts_ms - self._asymmetry_start_ms
        if duration_ms < self._asymmetry_min_ms:
            return None  # not long enough yet

        # Check velocity (how fast did the eye close?)
        velocity = self._compute_closing_velocity(side)
        if velocity is not None and velocity > self._velocity_thresh:
            # Too fast — likely natural partial blink, not intentional
            return None

        # Intentional wink confirmed
        event = "confirm" if side == "left" else "cancel"
        self._last_event_ms = ts_ms
        self._reset_tracking()
        logger.info(
            "Intentional %s wink (duration=%dms, velocity=%.2f EAR/s)",
            side, duration_ms, velocity or 0.0,
        )
        return event

    def _handle_both_closed(self, ts_ms: int) -> Optional[str]:
        """Handle both-eyes-closed state."""
        self._asymmetry_side = None
        self._asymmetry_start_ms = 0

        if self._both_closed_start_ms == 0:
            self._both_closed_start_ms = ts_ms
            return None

        duration_ms = ts_ms - self._both_closed_start_ms
        if duration_ms < self._both_closed_min_ms:
            return None  # not long enough — probably natural blink

        if duration_ms > self._both_closed_max_ms:
            return None  # too long — user resting, not gesturing

        # Intentional both-closed
        self._last_event_ms = ts_ms
        self._both_closed_start_ms = 0
        logger.info("Intentional both-closed gesture (duration=%dms)", duration_ms)
        return "both_closed"

    def _track_state(self, left_closed: bool, right_closed: bool, ts_ms: int) -> None:
        """Track state during cooldown (don't emit, but maintain timers)."""
        if left_closed and right_closed:
            if self._both_closed_start_ms == 0:
                self._both_closed_start_ms = ts_ms
            self._asymmetry_side = None
        elif left_closed and not right_closed:
            if self._asymmetry_side != "left":
                self._asymmetry_start_ms = ts_ms
                self._asymmetry_side = "left"
            self._both_closed_start_ms = 0
        elif right_closed and not left_closed:
            if self._asymmetry_side != "right":
                self._asymmetry_start_ms = ts_ms
                self._asymmetry_side = "right"
            self._both_closed_start_ms = 0
        else:
            self._reset_tracking()

    def _reset_tracking(self) -> None:
        """Reset all tracking state."""
        self._asymmetry_start_ms = 0
        self._asymmetry_side = None
        self._both_closed_start_ms = 0

    # ------------------------------------------------------------------
    # Internal: velocity computation
    # ------------------------------------------------------------------

    def _compute_closing_velocity(self, side: str) -> Optional[float]:
        """Compute how fast the eye closed (EAR change per second).

        Looks back in the buffer to find the transition from open → closed.
        Returns None if not enough data.
        """
        if len(self._buffer) < 3:
            return None

        idx = 1 if side == "left" else 2  # index into buffer tuple
        thresh = self.threshold

        # Find the last "open" frame before current "closed" sequence
        frames = list(self._buffer)
        open_frame = None
        for i in range(len(frames) - 2, -1, -1):
            if frames[i][idx] > thresh * 1.2:  # clearly open
                open_frame = frames[i]
                break

        if open_frame is None:
            return None

        # Current frame
        current = frames[-1]
        dt_s = (current[0] - open_frame[0]) / 1000.0
        if dt_s < 0.01:
            return None

        d_ear = abs(open_frame[idx] - current[idx])
        return d_ear / dt_s

    # ------------------------------------------------------------------
    # Internal: adaptive baseline
    # ------------------------------------------------------------------

    def _update_baseline(self, left_ear: float, right_ear: float) -> None:
        """Update the open-eye baseline via EMA."""
        if not self._baseline_initialized:
            self._baseline_samples += 1
            if self._baseline_samples < 10:
                # Accumulate initial samples
                self._baseline_left = (
                    self._baseline_left * (self._baseline_samples - 1) + left_ear
                ) / self._baseline_samples
                self._baseline_right = (
                    self._baseline_right * (self._baseline_samples - 1) + right_ear
                ) / self._baseline_samples
            else:
                self._baseline_initialized = True
            return

        alpha = self._baseline_alpha
        self._baseline_left = (1 - alpha) * self._baseline_left + alpha * left_ear
        self._baseline_right = (1 - alpha) * self._baseline_right + alpha * right_ear

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return current detector state for debugging."""
        return {
            "baseline": (round(self._baseline_left, 3), round(self._baseline_right, 3)),
            "threshold": round(self.threshold, 3),
            "asymmetry_side": self._asymmetry_side,
            "both_closed_tracking": self._both_closed_start_ms > 0,
            "buffer_len": len(self._buffer),
        }
