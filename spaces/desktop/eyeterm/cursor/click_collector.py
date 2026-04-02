"""ClickCollector — capture system-wide mouse clicks via WH_MOUSE_LL hook.

Clicks are stored as ClickSample objects comparing where the gaze model
predicted the click versus where the user actually clicked.  These samples
feed the AccuracyGate for implicit calibration without any explicit user
action.

Thread model
------------
- Hook thread  : installs WH_MOUSE_LL, runs Windows message pump, receives
                 WM_LBUTTONDOWN, appends to deque (no locks, no I/O in callback).
- Tick thread  : calls update_prediction() which does one atomic tuple write.
- Consumer     : calls get_recent() which reads the deque snapshot.

Windows constraints
-------------------
- WH_MOUSE_LL requires a message pump (GetMessageW loop) in the hook thread.
- Hook callback MUST return in < 300 ms — no file I/O or blocking calls.
- stop() posts WM_QUIT to break the message loop in the hook thread.
"""

import ctypes
import ctypes.wintypes
import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

logger = logging.getLogger("eyeterm.click_collector")

# Windows message constants
WM_LBUTTONDOWN = 0x0201
WM_QUIT = 0x0012

# WH_MOUSE_LL hook id
WH_MOUSE_LL = 14


@dataclass
class ClickSample:
    """A single left-button click paired with the gaze prediction at that instant.

    Attributes:
        timestamp:    Unix time of the click.
        click_x:      Actual click X in screen pixels.
        click_y:      Actual click Y in screen pixels.
        predicted_x:  Gaze-model predicted X at click time.
        predicted_y:  Gaze-model predicted Y at click time.
        residual_px:  Euclidean distance between prediction and click (computed).
    """

    timestamp: float
    click_x: int
    click_y: int
    predicted_x: int
    predicted_y: int
    residual_px: float = field(init=False)

    def __post_init__(self) -> None:
        self.residual_px = math.hypot(
            self.click_x - self.predicted_x,
            self.click_y - self.predicted_y,
        )


class ClickCollector:
    """Collect left-button clicks and pair them with gaze predictions.

    Args:
        maxlen:        Maximum number of ClickSamples to keep (ring buffer).
        max_age:       Maximum seconds a prediction can be before it is
                       considered stale and the click is ignored.
        max_residual:  Maximum allowed residual (px) — clicks further away
                       than this are rejected as outliers (e.g., intentional
                       keyboard shortcuts, not gaze-driven).
    """

    def __init__(
        self,
        maxlen: int = 200,
        max_age: float = 0.5,
        max_residual: float = 300.0,
    ) -> None:
        self._maxlen = maxlen
        self._max_age = max_age
        self._max_residual = max_residual

        # Samples ring buffer — only appended in hook callback, never locked.
        self._samples: Deque[ClickSample] = deque(maxlen=maxlen)

        # Atomic prediction tuple: (x, y, valid, timestamp)
        # Written by tick thread, read by hook callback.  Python assignment of
        # a tuple reference is atomic in CPython (single bytecode STORE_ATTR).
        self._prediction: Tuple[int, int, bool, float] = (0, 0, False, 0.0)

        # Hook thread state
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._hook = None
        self._hook_func = None  # prevent GC of ctypes callback

        # Windows API handle — None on non-Windows platforms
        try:
            self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        except AttributeError:
            self._user32 = None
            logger.warning("ctypes.windll not available — click collection disabled")

    # ------------------------------------------------------------------
    # Prediction update (called from tick thread)
    # ------------------------------------------------------------------

    def update_prediction(self, x: int, y: int, valid: bool) -> None:
        """Atomically store the current gaze prediction.

        Called from the gaze tick thread.  CPython tuple assignment is
        atomic — no lock required.

        Args:
            x:     Predicted screen X.
            y:     Predicted screen Y.
            valid: True when face is detected and prediction is trustworthy.
        """
        self._prediction = (x, y, valid, time.time())

    # ------------------------------------------------------------------
    # Filtering (pure logic — testable without Windows)
    # ------------------------------------------------------------------

    def _should_accept(self, click_x: int, click_y: int) -> bool:
        """Return True if the click should be recorded as a calibration sample.

        Rejects clicks when:
        - Face is not detected / prediction is invalid.
        - Prediction is older than max_age seconds.
        - Residual would exceed max_residual (outlier / non-gaze click).
        """
        pred_x, pred_y, valid, pred_time = self._prediction

        if not valid:
            return False

        age = time.time() - pred_time
        if age > self._max_age:
            return False

        residual = math.hypot(click_x - pred_x, click_y - pred_y)
        if residual > self._max_residual:
            return False

        return True

    # ------------------------------------------------------------------
    # Click recording (called from hook callback — must be fast)
    # ------------------------------------------------------------------

    def _record_click(self, click_x: int, click_y: int) -> None:
        """Record a click sample if the current prediction is acceptable.

        Called directly from the low-level mouse hook callback.
        MUST NOT acquire locks, do file I/O, or call any blocking function.
        """
        if not self._should_accept(click_x, click_y):
            return

        pred_x, pred_y, _valid, _ts = self._prediction
        sample = ClickSample(
            timestamp=time.time(),
            click_x=click_x,
            click_y=click_y,
            predicted_x=pred_x,
            predicted_y=pred_y,
        )
        self._samples.append(sample)

    # ------------------------------------------------------------------
    # Hook thread
    # ------------------------------------------------------------------

    def _run_hook(self) -> None:
        """Hook thread entry point.

        Installs WH_MOUSE_LL, runs a Windows message pump, and unhooks on exit.
        """
        if self._user32 is None:
            logger.error("ClickCollector: user32 not available, hook thread exiting")
            return

        # Store thread id so stop() can post WM_QUIT to this thread
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_long),
        )

        def hook_proc(
            nCode: int,
            wParam: int,
            lParam: ctypes.POINTER(ctypes.c_long),
        ) -> int:
            if nCode >= 0 and wParam == WM_LBUTTONDOWN:
                # lParam points to a MSLLHOOKSTRUCT; first two LONGs are pt.x, pt.y
                self._record_click(lParam[0], lParam[1])
            return self._user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        # Keep reference alive for duration of hook
        self._hook_func = HOOKPROC(hook_proc)
        self._hook = self._user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self._hook_func,
            None,
            0,
        )

        if not self._hook:
            err = ctypes.get_last_error()
            logger.error("ClickCollector: SetWindowsHookExW failed (error %d)", err)
            return

        logger.info("ClickCollector: WH_MOUSE_LL hook installed")

        # Message pump — required for WH_MOUSE_LL to fire
        msg = ctypes.wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

        # Pump exited (WM_QUIT received)
        self._user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        logger.info("ClickCollector: hook removed, thread exiting")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the hook thread.  No-op if already running."""
        if self._thread is not None and self._thread.is_alive():
            logger.debug("ClickCollector: already running")
            return

        if self._user32 is None:
            logger.warning("ClickCollector: user32 unavailable, start() skipped")
            return

        self._thread = threading.Thread(
            target=self._run_hook,
            name="ClickCollector-hook",
            daemon=True,
        )
        self._thread.start()
        logger.info("ClickCollector: hook thread started")

    def stop(self) -> None:
        """Stop the hook thread by posting WM_QUIT and joining."""
        if self._thread is None or not self._thread.is_alive():
            return

        if self._user32 is not None and self._thread_id is not None:
            # PostThreadMessageW is safe to call from any thread
            self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            logger.warning("ClickCollector: hook thread did not stop in time")
        else:
            logger.info("ClickCollector: hook thread stopped")

        self._thread = None
        self._thread_id = None

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_recent(self, n: int) -> List[ClickSample]:
        """Return the last *n* ClickSamples (oldest first).

        Thread-safe: deque slice is a snapshot copy.

        Args:
            n: Number of samples to return.  If n > len(deque), returns all.

        Returns:
            List of ClickSample objects in chronological order.
        """
        samples = list(self._samples)
        return samples[-n:] if n < len(samples) else samples
