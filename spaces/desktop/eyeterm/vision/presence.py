"""PresenceDetector — debounced face present/absent tracking.

Fires state transitions only after sustained presence or absence,
preventing false triggers during blinks or brief head turns.

States:
    present  — face continuously detected for ≥ return_debounce_s
    absent   — face continuously missing for ≥ leave_debounce_s
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("eyeterm.presence")


class PresenceDetector:
    """Track face presence with debounced transitions.

    Parameters
    ----------
    leave_debounce_s : float
        Seconds face must be absent before firing ``face_lost`` (default 3.0).
    return_debounce_s : float
        Seconds face must be back before firing ``face_returned`` (default 0.5).
    """

    def __init__(
        self,
        leave_debounce_s: float = 3.0,
        return_debounce_s: float = 0.5,
    ) -> None:
        self._leave_debounce = leave_debounce_s
        self._return_debounce = return_debounce_s

        self._present: bool = False          # confirmed state
        self._raw_present: bool = False       # raw per-frame detection
        self._transition_start: float = 0.0   # when raw state changed
        self._absent_since: float = 0.0       # timestamp when confirmed absent

    @property
    def present(self) -> bool:
        """Current confirmed presence state."""
        return self._present

    @property
    def absent_duration(self) -> float:
        """Seconds since confirmed absent (0.0 if present)."""
        if self._present:
            return 0.0
        if self._absent_since == 0.0:
            return 0.0
        return time.monotonic() - self._absent_since

    def update(self, face_detected: bool) -> str | None:
        """Update with per-frame face detection result.

        Returns
        -------
        str or None
            ``"face_lost"`` on confirmed absence transition,
            ``"face_returned"`` on confirmed return, or ``None``.
        """
        now = time.monotonic()

        # Track raw state changes
        if face_detected != self._raw_present:
            self._raw_present = face_detected
            self._transition_start = now

        # Check if debounce period has passed
        elapsed = now - self._transition_start

        if self._present and not self._raw_present:
            # Currently present, raw says absent → wait for leave debounce
            if elapsed >= self._leave_debounce:
                self._present = False
                self._absent_since = now
                logger.info("Presence: face_lost (absent for %.1fs)", elapsed)
                return "face_lost"

        elif not self._present and self._raw_present:
            # Currently absent, raw says present → wait for return debounce
            if elapsed >= self._return_debounce:
                self._present = True
                absent_dur = self.absent_duration
                self._absent_since = 0.0
                logger.info("Presence: face_returned (was absent %.1fs)", absent_dur)
                return "face_returned"

        return None
