"""Move the real Windows cursor based on gaze coordinates."""

import ctypes
import logging
import math
from typing import Optional, Tuple

logger = logging.getLogger("eyeterm.cursor")


class CursorDriver:
    """Map gaze screen coordinates to the actual system cursor.

    Safety features:
    - Disabled by default (must call enable() or toggle())
    - Deadzone: ignores small jitter below threshold
    - Face gate: only moves when face is actively detected
    - Velocity clamp: caps max movement per frame (catches outliers)
    - Dwell lock: freezes cursor after N frames in deadzone
    """

    def __init__(
        self,
        enabled: bool = False,
        deadzone_px: int = 50,
        require_face: bool = True,
        max_speed_px: int = 800,
        dwell_lock_frames: int = 5,
    ) -> None:
        self._enabled = enabled
        self._deadzone = deadzone_px
        self._require_face = require_face
        self._max_speed = max_speed_px
        self._dwell_lock_threshold = dwell_lock_frames
        self._last_x: Optional[int] = None
        self._last_y: Optional[int] = None
        self._face_detected = False

        # Dwell lock state
        self._dwell_count: int = 0       # consecutive frames in deadzone
        self._locked: bool = False        # cursor frozen
        self._unlock_count: int = 0       # consecutive frames outside deadzone

        # Logging support — set by headless.py to capture move decisions
        self._last_move_info: dict = {}

        # Windows API
        try:
            self._user32 = ctypes.windll.user32
        except AttributeError:
            self._user32 = None
            logger.warning("ctypes.windll not available — cursor control disabled")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True
        self._last_x = None
        self._last_y = None
        self._dwell_count = 0
        self._locked = False
        self._unlock_count = 0
        logger.info("Cursor control ENABLED")

    def disable(self) -> None:
        self._enabled = False
        logger.info("Cursor control DISABLED")

    def toggle(self) -> bool:
        """Toggle enabled state. Returns new state."""
        if self._enabled:
            self.disable()
        else:
            self.enable()
        return self._enabled

    def set_face_detected(self, detected: bool) -> None:
        """Update face detection gate."""
        self._face_detected = detected

    def move(self, screen_x: int, screen_y: int) -> bool:
        """Move the system cursor to (screen_x, screen_y).

        Returns True if cursor was actually moved.
        """
        logger.debug("move called: screen=(%s, %s)", screen_x, screen_y)
        self._last_move_info = {"blocked_by": None, "dx": 0, "dy": 0, "clamped": False}

        if not self._enabled:
            self._last_move_info["blocked_by"] = "disabled"
            return False

        if self._require_face and not self._face_detected:
            self._last_move_info["blocked_by"] = "no_face"
            return False

        if self._user32 is None:
            self._last_move_info["blocked_by"] = "no_user32"
            return False

        # Compute delta from last position
        if self._last_x is not None and self._last_y is not None:
            dx = screen_x - self._last_x
            dy = screen_y - self._last_y
            adx = abs(dx)
            ady = abs(dy)
            self._last_move_info["dx"] = dx
            self._last_move_info["dy"] = dy

            # --- Velocity clamp: cap max movement per frame ---
            dist = math.hypot(adx, ady)
            if dist > self._max_speed and dist > 0:
                scale = self._max_speed / dist
                screen_x = self._last_x + int(dx * scale)
                screen_y = self._last_y + int(dy * scale)
                adx = abs(screen_x - self._last_x)
                ady = abs(screen_y - self._last_y)
                self._last_move_info["clamped"] = True

            # --- Deadzone check ---
            in_deadzone = adx < self._deadzone and ady < self._deadzone

            if in_deadzone:
                self._dwell_count += 1
                self._unlock_count = 0
                # Engage dwell lock after threshold
                if self._dwell_count >= self._dwell_lock_threshold:
                    self._locked = True
                self._last_move_info["blocked_by"] = "deadzone"
                return False

            # Outside deadzone
            if self._locked:
                # Need 2+ consecutive frames outside deadzone to unlock
                self._unlock_count += 1
                if self._unlock_count < 2:
                    self._last_move_info["blocked_by"] = "dwell_locked"
                    return False
                # Unlock
                self._locked = False
                self._dwell_count = 0
                self._unlock_count = 0

            # Reset dwell counter on movement
            self._dwell_count = 0

        self._user32.SetCursorPos(screen_x, screen_y)
        self._last_x = screen_x
        self._last_y = screen_y
        return True

    def get_position(self) -> Optional[Tuple[int, int]]:
        """Get current system cursor position."""
        if self._user32 is None:
            return None
        try:
            point = ctypes.wintypes.POINT()
            self._user32.GetCursorPos(ctypes.byref(point))
            return (point.x, point.y)
        except Exception:
            return None
