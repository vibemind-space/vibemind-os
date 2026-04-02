"""eyeTerm headless mode — runs without OpenCV GUI window.

Used when eyeTerm is embedded in VibeMind's Electron app.
The camera feed is served via MJPEG stream (port 8099) instead
of cv2.imshow. Voice commands are forwarded to the Moire Voice
WebSocket for processing.

Usage from electron_backend.py:
    from spaces.desktop.eyeterm.headless import EyeTermHeadless
    eyeterm = EyeTermHeadless()
    eyeterm.start()  # daemon thread
    # ...
    eyeterm.stop()
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from .config import AppConfig
from .state import State, Event, StateMachine
# Heavy imports (cv2, comtypes, numpy) are deferred to _init_components()
# to avoid 30s+ blocking import when running inside electron_backend.py

logger = logging.getLogger("eyeterm.headless")


class EyeTermHeadless:
    """Headless eyeTerm — no OpenCV window, MJPEG stream only.

    Designed to run as a daemon thread inside electron_backend.py.
    Provides:
    - Gaze tracking → real cursor movement
    - Wink detection → state machine transitions
    - MJPEG camera stream on port 8099
    - Status dict for REST API polling
    - Voice command callback for Moire Voice integration
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        on_voice_command: Optional[Callable[[str, Optional[Dict]], None]] = None,
        broadcast_fn: Optional[Callable[[Dict], None]] = None,
    ):
        self._config = config or AppConfig.from_env()
        self._config.stream.enabled = True  # Always enable MJPEG in headless mode
        self._on_voice_command = on_voice_command
        self._broadcast_fn = broadcast_fn  # IPC to Electron for calibration dots

        self._sm = StateMachine()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Components (initialized in _run)
        self._camera = None
        self._gaze = None
        self._fusion = None  # GazeFusion (head+eye weighted blend)
        self._calibration_mgr = None  # HeadlessCalibrationManager
        self._smoother = None
        self._screen_smoother_x = None  # Screen-space OneEuro (post-affine)
        self._screen_smoother_y = None
        self._screen_mapper = None
        self._residual_grid = None     # Click-learning correction grid
        self._accuracy_gate = None     # Phase-based cursor gate
        self._click_collector = None   # Windows mouse hook
        self._ga_calibrator = None     # Genetic algorithm calibration
        self._presence = None          # Face presence detector
        self._blink_tracker = None     # Blink rate / fatigue
        self._head_gesture = None      # Nod/shake detector
        self._focus_router = None
        self._wink = None
        self._intentional_wink = None  # IntentionalWinkDetector
        self._dictation = None         # DictationController
        self._keyboard_actions = None  # KeyboardActions
        self._cursor_driver = None
        self._camera_server = None
        self._overlay = None
        self._stt = None
        self._uia = None

        self._command_router = None  # Lazy — created in _init_components

        # Runtime state
        self._current_element = None
        self._transcript_partial = ""
        self._transcript_final = ""
        self._last_uia_query_ms = 0
        self._ear_values = (0.0, 0.0)
        self._gaze_screen_x: int = 0
        self._gaze_screen_y: int = 0
        self._gaze_valid: bool = False
        self._screen_width: int = 1920
        self._screen_height: int = 1080
        self._last_camera_retry: float = 0.0  # monotonic timestamp of last retry
        self._camera_retry_interval: float = 5.0  # seconds between retries

        # CSV data logger
        self._csv_file = None
        self._csv_writer = None
        self._csv_frame_count: int = 0
        self._csv_max_frames: int = 900  # ~30s at 30fps

        # Click-learning CSV (persistent, append mode, unlimited)
        self._click_csv_file = None
        self._click_csv_writer = None
        self._last_processed_click_ts: float = 0.0  # dedup clicks

    @property
    def status(self) -> Dict[str, Any]:
        """Status dict for REST API."""
        return {
            "running": self._running,
            "state": self._sm.state.value,
            "cursor_enabled": self._cursor_driver.enabled if self._cursor_driver else False,
            "stream_port": self._config.stream.port,
            "face_detected": (
                self._cursor_driver._face_detected if self._cursor_driver else False
            ),
        }

    @property
    def gaze(self) -> Dict[str, Any]:
        """Fast gaze position dict — polled at ~50ms by frontend."""
        return {
            "x": self._gaze_screen_x,
            "y": self._gaze_screen_y,
            "valid": self._gaze_valid,
            "sw": self._screen_width,
            "sh": self._screen_height,
        }

    def start(self):
        """Start eyeTerm in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("eyeTerm already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            name="eyeterm-headless",
            daemon=True,
        )
        self._thread.start()
        logger.info("eyeTerm headless started")

    def stop(self):
        """Stop eyeTerm."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("eyeTerm headless stopped")

    def toggle_cursor(self) -> bool:
        """Toggle cursor control, return new state."""
        if self._cursor_driver:
            return self._cursor_driver.toggle()
        return False

    def calibrate(self) -> bool:
        """Start non-blocking 9-point calibration. Returns False if not ready."""
        if not (self._gaze and self._fusion and self._screen_mapper):
            return False
        from .vision.calibrate import HeadlessCalibrationManager
        if self._calibration_mgr is None:
            self._calibration_mgr = HeadlessCalibrationManager()
        if self._calibration_mgr.is_active:
            return False
        old_matrix = self._screen_mapper._cal
        self._calibration_mgr.start(
            self._screen_width, self._screen_height,
            old_matrix=old_matrix,
            broadcast_fn=self._broadcast_fn,
        )
        return True

    @staticmethod
    def _log(msg: str):
        """Write to stderr AND a file — Electron may swallow daemon thread stderr."""
        line = f"[eyeTerm-thread] {msg}"
        logger.debug("%s", line)
        try:
            from pathlib import Path
            log_path = Path(__file__).parent.parent.parent.parent / "logs" / "eyeterm_debug.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                import datetime
                f.write(f"{datetime.datetime.now().isoformat()} {line}\n")
        except Exception:
            pass

    def _run(self):
        """Main loop — runs in background thread."""
        try:
            self._log("_init_components starting...")
            self._init_components()
            self._log("Components OK, entering main loop")
            logger.info("eyeTerm components initialized, entering main loop")

            frame_time = 1.0 / self._config.target_fps
            tick_errors = 0

            while self._running:
                t_start = time.monotonic()
                try:
                    self._tick()
                except Exception as tick_err:
                    tick_errors += 1
                    if tick_errors <= 5:
                        import traceback
                        self._log(f"tick error #{tick_errors}: {tick_err}\n{traceback.format_exc()}")
                    if tick_errors > 100:
                        self._log("Too many tick errors (>100), stopping")
                        break
                elapsed = time.monotonic() - t_start
                sleep_time = frame_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            self._log(f"Main loop exited (_running={self._running}, tick_errors={tick_errors})")

        except Exception as e:
            import traceback
            self._log(f"INIT CRASH: {e}\n{traceback.format_exc()}")
            logger.error("eyeTerm headless error: %s", e, exc_info=True)
        finally:
            self._log("_cleanup starting...")
            self._cleanup()
            self._log("Thread exiting")

    def _init_components(self):
        """Initialize vision, audio, streaming.

        All heavy imports (cv2, comtypes, numpy, mediapipe) happen here
        inside the daemon thread — NOT at module level.

        Startup order (critical — MJPEG must bind before camera opens):
          1. Heavy imports
          2. MJPEG server (port 8099)  ← frontend can connect immediately
          3. Cursor driver
          4. Camera (with timeout)     ← can block 10-30s on Windows
          5. Gaze / wink / overlay     ← non-fatal
          6. STT                       ← optional
        """
        # --- 1. Lazy-load heavy deps ---
        self._log("Loading heavy deps...")

        from .stream.camera_server import CameraStreamServer
        self._log("CameraStreamServer loaded (cv2+numpy)")

        from .routing.command_router import CommandRouter
        self._command_router = CommandRouter(
            on_direct=self._execute_direct,
            on_agent_team=self._route_to_agent_team,
            on_local_ai=self._route_to_local_ai,
        )
        self._log("CommandRouter loaded (comtypes)")

        from .cursor.cursor_driver import CursorDriver
        self._log("All heavy deps loaded")

        # --- 2. Kill stale processes holding camera/port ---
        self._kill_stale_eyeterm_processes()

        # --- 3. MJPEG server FIRST — so frontend can connect immediately ---
        self._camera_server = CameraStreamServer(port=self._config.stream.port)
        self._camera_server.start()
        self._log(f"MJPEG server on port {self._config.stream.port}")

        # --- 3. Cursor driver (lightweight — only ctypes) ---
        self._cursor_driver = CursorDriver(
            enabled=self._config.cursor.enabled,
            deadzone_px=self._config.cursor.deadzone_px,
            require_face=self._config.cursor.require_face,
            max_speed_px=self._config.cursor.max_speed_px,
            dwell_lock_frames=self._config.cursor.dwell_lock_frames,
        )

        # --- 4. Camera (with timeout — cv2.VideoCapture can block on Windows) ---
        self._open_camera_with_timeout()

        # --- 5. Gaze + Wink + Overlay (non-fatal) ---
        try:
            from .vision.gaze import GazeEstimator, GazeFusion, GazeSmoother, GazeToScreen, FocusRouter
            self._log("mediapipe/gaze imported")
            self._gaze = GazeEstimator(min_confidence=self._config.gaze.min_confidence)
            self._fusion = GazeFusion(
                head_weight_min=self._config.gaze.head_weight_min,
                head_weight_max=self._config.gaze.head_weight_max,
                speed_threshold=self._config.gaze.head_speed_threshold,
            )
            self._log(f"GazeFusion: adaptive hw=[{self._config.gaze.head_weight_min}, {self._config.gaze.head_weight_max}]")
            self._smoother = GazeSmoother(
                freq=float(self._config.target_fps),
                min_cutoff=self._config.gaze.min_cutoff,
                beta=self._config.gaze.beta,
            )

            # Screen-space smoothing (post-affine — cursor glides, never jumps)
            from .vision.gaze import OneEuroFilter
            self._screen_smoother_x = OneEuroFilter(
                freq=float(self._config.target_fps),
                min_cutoff=1.5,   # Hz — smooth but responsive (0.5=slow, 3.0=fast)
                beta=0.008,       # speed-adaptive release
            )
            self._screen_smoother_y = OneEuroFilter(
                freq=float(self._config.target_fps),
                min_cutoff=1.5,
                beta=0.008,
            )

            try:
                from screeninfo import get_monitors
                monitors = get_monitors()
                # Use full virtual desktop spanning all monitors
                max_right = max(m.x + m.width for m in monitors)
                max_bottom = max(m.y + m.height for m in monitors)
                sw = max_right
                sh = max_bottom
                self._log(f"Virtual desktop: {sw}x{sh} across {len(monitors)} monitor(s)")
            except Exception:
                sw, sh = 1920, 1080

            self._screen_width = sw
            self._screen_height = sh
            self._screen_mapper = GazeToScreen(
                sw, sh,
                gaze_range_x=(self._config.gaze.range_x_min, self._config.gaze.range_x_max),
                gaze_range_y=(self._config.gaze.range_y_min, self._config.gaze.range_y_max),
            )

            # Load saved calibration if exists
            try:
                from .vision.calibrate import HeadlessCalibrationManager
                saved = HeadlessCalibrationManager.load_calibration()
                if saved is not None:
                    self._screen_mapper.set_calibration(saved)
                    self._log("Loaded saved calibration matrix")
            except Exception as e:
                self._log(f"Calibration load failed (non-fatal): {e}")

            # --- ResidualGrid (local click-learning corrections) ---
            from .cursor.residual_grid import ResidualGrid
            gs = self._config.cursor.grid_size
            self._residual_grid = ResidualGrid(sw, sh, grid_cols=gs, grid_rows=gs)

            # --- AccuracyGate (cursor ON/OFF based on measured accuracy) ---
            import math as _math
            from .cursor.accuracy_gate import AccuracyGate
            self._accuracy_gate = AccuracyGate(
                sw, sh,
                threshold_on=self._config.cursor.accuracy_threshold,
                threshold_off=self._config.cursor.accuracy_off_threshold,
                accuracy_radius_frac=self._config.cursor.accuracy_radius_frac,
                drift_threshold_frac=self._config.cursor.drift_threshold_frac,
                min_clicks=self._config.cursor.accuracy_min_clicks,
            )

            # --- ClickCollector (Windows mouse hook for implicit calibration) ---
            from .cursor.click_collector import ClickCollector
            _diag = _math.hypot(sw, sh)
            self._click_collector = ClickCollector(
                maxlen=self._config.cursor.click_buffer_size,
                max_residual=float(int(self._config.cursor.click_max_residual_frac * _diag)),
                max_age=self._config.cursor.click_max_age_ms / 1000.0,
            )
            self._click_collector.start()
            self._log("ClickCollector + ResidualGrid + AccuracyGate initialized")

            # --- GeneticCalibrator (grid-aware piecewise-affine evolution) ---
            from .cursor.ga_calibrator import GeneticCalibrator
            self._ga_calibrator = GeneticCalibrator(
                screen_w=sw, screen_h=sh,
                grid_rows=3, grid_cols=3,
                pop_size=100,
                min_samples=8,
                min_coverage=3,
                evolve_interval=2.0,
                improvement_threshold=3.0,
                coverage_penalty=50.0,
            )

            def _on_ga_improved(genes: "np.ndarray", residual: float) -> None:
                # Extract the global affine from genes[0:6] for GazeToScreen
                import numpy as _np
                affine = _np.array(genes[:6], dtype=_np.float64).reshape(2, 3)
                self._screen_mapper.set_calibration(affine)
                if self._residual_grid:
                    self._residual_grid.reset()
                self._log(
                    f"GA calibration applied (residual={residual:.1f}px, "
                    f"gen={self._ga_calibrator.generation}, "
                    f"coverage={self._ga_calibrator.status().get('coverage', '?')})"
                )

            self._ga_calibrator.start(on_improved=_on_ga_improved)
            self._log("GeneticCalibrator started (3x3 grid, background evolution)")

            # --- T1 Detectors ---
            from .vision.presence import PresenceDetector
            self._presence = PresenceDetector(leave_debounce_s=3.0, return_debounce_s=0.5)

            from .vision.blink_tracker import BlinkTracker
            self._blink_tracker = BlinkTracker(
                ear_threshold=self._config.wink.ear_threshold,
                broadcast_interval_s=10.0,
            )

            from .vision.head_gesture import HeadGestureDetector
            self._head_gesture = HeadGestureDetector()

            self._log("T1 detectors initialized (presence, blink, gesture)")

            # --- Dictation Controller ---
            self._dictation = None
            if self._config.dictation.enabled:
                from .dictation.controller import DictationController
                from .routing.transcript_polisher import TranscriptPolisher

                polisher = TranscriptPolisher()
                keyboard = self._keyboard_actions

                def _dictation_state_event(event_name: str, payload=None):
                    """Route DictationController events to the state machine."""
                    event_map = {
                        "dictation_stop": Event.DICTATION_STOP,
                        "enhance_complete": Event.ENHANCE_COMPLETE,
                    }
                    ev = event_map.get(event_name)
                    if ev:
                        _, action = self._sm.transition(ev, payload)
                        if action:
                            self._handle_action(action)

                def _dictation_insert(text: str):
                    """Insert text at cursor via clipboard paste."""
                    if keyboard:
                        keyboard.insert_text(text)

                self._dictation = DictationController(
                    polisher=polisher,
                    on_state_event=_dictation_state_event,
                    on_insert_text=_dictation_insert,
                    silence_timeout_s=self._config.dictation.silence_timeout_s,
                )
                self._log("DictationController initialized")

            self._focus_router = FocusRouter(
                num_panes=1,
                dwell_ms=self._config.gaze.dwell_ms,
                screen_width=sw,
                screen_height=sh,
            )

            from .vision.wink import WinkDetector
            self._wink = WinkDetector(
                ear_threshold=self._config.wink.ear_threshold,
                min_frames=self._config.wink.min_frames,
                cooldown_ms=self._config.wink.cooldown_ms,
            )

            # IntentionalWinkDetector (velocity + asymmetry-based)
            if self._config.wink.use_intentional_detector:
                try:
                    from .vision.intentional_wink import IntentionalWinkDetector
                    self._intentional_wink = IntentionalWinkDetector(
                        velocity_threshold=self._config.wink.velocity_threshold,
                        asymmetry_min_ms=self._config.wink.asymmetry_min_ms,
                        both_closed_min_ms=self._config.wink.both_closed_min_ms,
                        both_closed_max_ms=self._config.wink.both_closed_max_ms,
                        cooldown_ms=self._config.wink.intentional_cooldown_ms,
                        baseline_ema_alpha=self._config.wink.baseline_ema_alpha,
                    )
                    self._log("IntentionalWinkDetector initialized (adaptive threshold)")
                except Exception as e:
                    self._log(f"IntentionalWinkDetector failed, using basic: {e}")

            # KeyboardActions (for text insertion)
            from .action.keyboard_actions import KeyboardActions
            self._keyboard_actions = KeyboardActions()

            from .ui.overlay import OverlayRenderer
            self._overlay = OverlayRenderer(
                self._config.window_width,
                self._config.window_height,
                1,
            )
            self._log("Gaze + wink + overlay OK")
        except Exception as e:
            import traceback
            self._log(f"Gaze init failed (non-fatal): {e}\n{traceback.format_exc()}")

        # --- 6. CSV data logger ---
        try:
            import csv
            from pathlib import Path
            log_dir = Path(__file__).parent.parent.parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            csv_path = log_dir / "eyeterm_gaze_log.csv"
            self._csv_file = open(csv_path, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "frame", "timestamp",
                "raw_x", "raw_y",
                "head_x", "head_y",
                "head_weight",
                "fused_x", "fused_y",
                "smooth_x", "smooth_y",
                "screen_x", "screen_y",
                "cursor_moved", "blocked_by", "clamped",
                "dx", "dy",
            ])
            self._log(f"CSV logger → {csv_path}")
        except Exception as e:
            self._log(f"CSV logger failed (non-fatal): {e}")

        # --- 7. Click-learning CSV (persistent, append mode) ---
        try:
            import csv
            from pathlib import Path
            log_dir = Path(__file__).parent.parent.parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            click_csv_path = log_dir / "eyeterm_click_learning.csv"
            write_header = not click_csv_path.exists() or click_csv_path.stat().st_size == 0
            self._click_csv_file = open(click_csv_path, "a", newline="", encoding="utf-8")
            self._click_csv_writer = csv.writer(self._click_csv_file)
            if write_header:
                self._click_csv_writer.writerow([
                    "timestamp", "click_x", "click_y",
                    "predicted_x", "predicted_y", "residual_px",
                    "accuracy_20", "phase",
                ])
            self._log(f"Click CSV → {click_csv_path} (append)")
        except Exception as e:
            self._log(f"Click CSV failed (non-fatal): {e}")

        # --- 8. STT (optional) ---
        try:
            from .audio.stt_vosk import VoskSTT
            model_path = self._config.audio.vosk_model_path
            if model_path:
                self._stt = VoskSTT(model_path, self._config.audio.sample_rate)
                self._stt.start(
                    on_partial=self._on_stt_partial,
                    on_final=self._on_stt_final,
                )
                logger.info("Voice dictation active")
        except Exception as e:
            logger.info("STT not available: %s", e)

    def _kill_stale_eyeterm_processes(self) -> None:
        """Kill stale Python processes holding the camera or port 8099.

        On Windows, crashed eyeTerm instances leave zombie python.exe
        processes that hold the webcam and MJPEG port. This prevents
        new instances from starting.
        """
        import subprocess
        import os

        my_pid = os.getpid()
        killed = 0

        try:
            # Find processes holding port 8099
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=5,
            )
            stale_pids = set()
            for line in result.stdout.splitlines():
                if ":8099" in line and "ABHR" in line.upper() or ":8099" in line and "LISTEN" in line.upper():
                    parts = line.split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                            if pid != my_pid and pid != 0:
                                stale_pids.add(pid)
                        except ValueError:
                            pass

            for pid in stale_pids:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, timeout=5,
                    )
                    killed += 1
                except Exception:
                    pass

            if killed:
                self._log(f"Killed {killed} stale process(es) holding port 8099")
                import time
                time.sleep(1)  # let OS release resources
        except Exception as e:
            self._log(f"Stale process cleanup failed (non-fatal): {e}")

    def _open_camera_with_timeout(self, timeout_sec: float = 10.0):
        """Open camera in a sub-thread with timeout.

        cv2.VideoCapture(0) on Windows can block for 10-30s during
        DirectShow device enumeration, or hang indefinitely if another
        process holds the camera. This method prevents that from
        blocking the entire eyeTerm startup.
        """
        import threading

        self._log(f"Opening camera (timeout={timeout_sec}s)...")
        result = [None]  # mutable container for sub-thread result

        def _try_open():
            import cv2
            from .vision.camera import CameraCapture

            cam = CameraCapture(self._config.camera_index)
            cam.start()
            if cam.is_open:
                result[0] = cam
                return

            # Default backend failed — try DirectShow on Windows
            cam.stop()
            try:
                cap = cv2.VideoCapture(self._config.camera_index, cv2.CAP_DSHOW)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cam._cap = cap
                    result[0] = cam
                else:
                    cap.release()
            except Exception:
                pass

        t = threading.Thread(target=_try_open, daemon=True, name="eyeterm-cam-open")
        t.start()
        t.join(timeout=timeout_sec)

        if result[0] is not None and result[0].is_open:
            self._camera = result[0]
            self._log(f"Camera opened OK (index={self._config.camera_index})")
        else:
            self._camera = None
            if t.is_alive():
                self._log("Camera open TIMED OUT — continuing without camera")
            else:
                self._log("Camera not available — continuing without camera")

    def _tick(self):
        """One frame of the main loop."""
        import cv2
        import numpy as np

        # Camera retry: if camera failed at startup, try again every 5s
        if self._camera is None:
            now_mono = time.monotonic()
            if now_mono - self._last_camera_retry >= self._camera_retry_interval:
                self._last_camera_retry = now_mono
                self._open_camera_with_timeout(timeout_sec=3.0)
                if self._camera is not None:
                    self._log("Camera connected on retry!")
                    self._placeholder_sent = False

        frame = self._camera.read() if self._camera else None
        if frame is None:
            # Send placeholder so MJPEG stream stays alive (not "offline")
            if self._camera_server and not getattr(self, '_placeholder_sent', False):
                black = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(black, "Waiting for camera...", (130, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2)
                self._camera_server.update_frame(black)
                self._placeholder_sent = True
            return
        self._placeholder_sent = False

        gaze_point = None
        raw_x = raw_y = smooth_x = smooth_y = float("nan")
        head_x = head_y = fused_x = fused_y = float("nan")
        screen_x = screen_y = 0
        cursor_moved = False

        # Gaze tracking (only if mediapipe initialized successfully)
        if self._gaze and self._smoother and self._screen_mapper:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            gaze_result = self._gaze.estimate(frame_rgb)
            now_ms = int(time.time() * 1000)

            if gaze_result is not None:
                raw_x, raw_y = gaze_result.x, gaze_result.y
                head_x, head_y = gaze_result.head_x, gaze_result.head_y

                # Fuse head direction + eye gaze before smoothing
                if self._fusion:
                    fx, fy = self._fusion.fuse(gaze_result)
                else:
                    fx, fy = raw_x, raw_y
                fused_x, fused_y = fx, fy

                # --- Calibration intercept ---
                if self._calibration_mgr and self._calibration_mgr.is_active:
                    self._calibration_mgr.tick(fx, fy)
                    # Check if just completed
                    if not self._calibration_mgr.is_active:
                        matrix = self._calibration_mgr.result_matrix
                        if matrix is not None:
                            self._screen_mapper.set_calibration(matrix)
                            from .vision.calibrate import HeadlessCalibrationManager
                            HeadlessCalibrationManager.save_calibration(matrix)
                            self._log("Calibration applied and saved")
                    # Skip smoother + cursor during calibration
                else:
                    # --- Normal path ---
                    # OneEuro filter on the fused signal
                    sx, sy = self._smoother.smooth((fx, fy))
                    smooth_x, smooth_y = sx, sy
                    gaze_point = (sx, sy)
                    # Primary: use GA grid mapping if available
                    ga_result = None
                    if self._ga_calibrator:
                        ga_result = self._ga_calibrator.map_gaze(sx, sy)

                    if ga_result is not None:
                        screen_x, screen_y = ga_result
                    else:
                        screen_x, screen_y = self._screen_mapper.to_screen(sx, sy)

                    # Screen-space smoothing: cursor glides to target, no jumps
                    if self._screen_smoother_x and self._screen_smoother_y:
                        screen_x = int(self._screen_smoother_x(float(screen_x)))
                        screen_y = int(self._screen_smoother_y(float(screen_y)))

                    # Residual grid correction (click-learning, supplements GA)
                    if self._residual_grid:
                        dx, dy = self._residual_grid.interpolate(screen_x, screen_y)
                        screen_x = int(screen_x + dx)
                        screen_y = int(screen_y + dy)

                    self._gaze_screen_x = screen_x
                    self._gaze_screen_y = screen_y
                    self._gaze_valid = True

                    # Update click collector with current prediction
                    if self._click_collector:
                        self._click_collector.update_prediction(screen_x, screen_y, True)

                    # Process new clicks only (dedup by timestamp)
                    if self._click_collector and self._residual_grid:
                        new_clicks = self._click_collector.get_recent(5)
                        had_new = False
                        for sample in new_clicks:
                            if sample.timestamp > self._last_processed_click_ts:
                                had_new = True
                                self._residual_grid.update(
                                    sample.predicted_x, sample.predicted_y,
                                    sample.click_x, sample.click_y,
                                )
                                # Feed GA with smoothed gaze input → actual click
                                if self._ga_calibrator:
                                    self._ga_calibrator.add_sample(
                                        smooth_x, smooth_y,
                                        sample.click_x, sample.click_y,
                                    )

                        # Accuracy gate + drift check ONLY when new clicks arrived
                        if had_new and self._accuracy_gate:
                            recent = self._click_collector.get_recent(20)
                            old_phase = self._accuracy_gate.phase
                            self._accuracy_gate.update(recent)
                            if self._accuracy_gate.phase != old_phase:
                                self._log(f"AccuracyGate: {old_phase} → {self._accuracy_gate.phase}")
                                # Reset grid once when entering degraded (drift detected)
                                if self._accuracy_gate.phase == "degraded" and self._residual_grid:
                                    self._residual_grid.reset()
                                    self._log("Grid reset (drift)")

                    if self._cursor_driver:
                        self._cursor_driver.set_face_detected(True)
                        # Cursor moves only when AccuracyGate allows AND driver is enabled
                        gate_ok = not self._accuracy_gate or self._accuracy_gate.cursor_enabled
                        if gate_ok:
                            cursor_moved = self._cursor_driver.move(screen_x, screen_y)

                    if gaze_result.landmarks and self._wink:
                        from .vision.wink import WinkDetector
                        self._ear_values = WinkDetector.get_ear_values(gaze_result.landmarks)

                        # Use IntentionalWinkDetector if available, else fallback
                        if self._intentional_wink:
                            wink = self._intentional_wink.update(gaze_result.landmarks, now_ms)
                        else:
                            wink = self._wink.update(gaze_result.landmarks, now_ms)

                        if wink in ("confirm", "cancel", "both_closed"):
                            event_map = {
                                "confirm": Event.LEFT_WINK,
                                "cancel": Event.RIGHT_WINK,
                                "both_closed": Event.BOTH_CLOSED,
                            }
                            event = event_map[wink]
                            _, action = self._sm.transition(event)
                            if action:
                                self._handle_action(action)

                    # --- T1: Blink rate tracking ---
                    if self._blink_tracker and self._ear_values:
                        fatigue_msg = self._blink_tracker.update(*self._ear_values)
                        if fatigue_msg and self._broadcast_fn:
                            try:
                                self._broadcast_fn(fatigue_msg)
                            except Exception:
                                pass

                    # --- T1: Head gesture detection ---
                    if self._head_gesture:
                        gesture = self._head_gesture.update(head_x, head_y)
                        if gesture:
                            if self._broadcast_fn:
                                try:
                                    self._broadcast_fn({
                                        "type": "eyeterm_gesture",
                                        "gesture": gesture,
                                    })
                                except Exception:
                                    pass

                            # Head-Nod → start dictation (when in IDLE or FOCUSED)
                            if (gesture == "nod"
                                    and self._dictation
                                    and self._sm.state in (State.IDLE, State.FOCUSED)):
                                _, action = self._sm.transition(Event.DICTATION_START)
                                if action:
                                    self._handle_action(action)

                    if self._focus_router and self._sm.state in (State.IDLE, State.FOCUSED):
                        pane = self._focus_router.update(screen_x, screen_y, now_ms)
                        if pane is not None:
                            _, action = self._sm.transition(Event.GAZE_DWELL, pane)
                            if action:
                                self._handle_action(action)
                            self._update_element_at_gaze(screen_x, screen_y, now_ms)
            else:
                self._gaze_valid = False
                if self._cursor_driver:
                    self._cursor_driver.set_face_detected(False)

            # --- T1: Presence detection (runs for both face/no-face) ---
            if self._presence and self._broadcast_fn:
                presence_event = self._presence.update(gaze_result is not None)
                if presence_event:
                    try:
                        self._broadcast_fn({
                            "type": "eyeterm_presence",
                            "present": self._presence.present,
                            "event": presence_event,
                            "absent_duration_s": round(self._presence.absent_duration, 1),
                        })
                    except Exception:
                        pass

        # Render composited frame for MJPEG (or raw frame if overlay unavailable)
        if self._overlay:
            if self._calibration_mgr and self._calibration_mgr.is_active:
                ui_frame = self._overlay.render_calibration(
                    camera_frame=frame,
                    instruction=self._calibration_mgr.current_instruction,
                    point_index=self._calibration_mgr.current_point_index,
                    total_points=self._calibration_mgr.total_points,
                    progress=self._calibration_mgr.progress_fraction,
                )
            else:
                try:
                    element_summary = self._current_element.summary() if self._current_element else ""
                except Exception:
                    element_summary = ""
                ui_frame = self._overlay.render(
                    camera_frame=frame,
                    state_name=self._sm.state.value,
                    focused_pane=self._sm.focused_pane,
                    element_summary=element_summary,
                    pane_statuses=[],
                    transcript_partial=self._transcript_partial,
                    transcript_final=self._transcript_final,
                    gaze_point=gaze_point,
                    ear_values=self._ear_values,
                    show_debug=False,
                    cursor_enabled=self._cursor_driver.enabled if self._cursor_driver else False,
                )
        else:
            # No overlay — send raw camera frame
            _, jpeg = cv2.imencode(".jpg", frame)
            ui_frame = frame

        # Draw click markers on MJPEG frame (predicted vs actual)
        if self._click_collector and isinstance(ui_frame, np.ndarray):
            recent_clicks = self._click_collector.get_recent(10)
            fh, fw = ui_frame.shape[:2]
            sx = fw / max(self._screen_width, 1)
            sy = fh / max(self._screen_height, 1)

            for i, sample in enumerate(recent_clicks):
                # Fade: newest = full opacity, oldest = dim
                age_factor = 1.0 - (i / max(len(recent_clicks), 1)) * 0.7
                green = (0, int(255 * age_factor), 0)
                red = (0, 0, int(255 * age_factor))

                # Map screen coords to frame coords
                cx = int(sample.click_x * sx)
                cy = int(sample.click_y * sy)
                px = int(sample.predicted_x * sx)
                py = int(sample.predicted_y * sy)

                # Green circle = actual click, Red circle = predicted
                cv2.circle(ui_frame, (cx, cy), 6, green, 2)
                cv2.circle(ui_frame, (px, py), 4, red, -1)
                # Line between them = error vector
                cv2.line(ui_frame, (px, py), (cx, cy), (100, 100, 100), 1)
                # Residual text on newest 3
                if i < 3:
                    cv2.putText(ui_frame, f"{int(sample.residual_px)}px",
                                (cx + 8, cy - 4), cv2.FONT_HERSHEY_SIMPLEX,
                                0.35, green, 1)

                # Write new clicks to persistent CSV
                if sample.timestamp > self._last_processed_click_ts:
                    if self._click_csv_writer:
                        acc = ""
                        phase = ""
                        if self._accuracy_gate:
                            phase = self._accuracy_gate.phase
                            # Compute accuracy from recent clicks
                            rc = self._click_collector.get_recent(20) if self._click_collector else []
                            if rc:
                                hits = sum(1 for c in rc if c.residual_px <= self._accuracy_gate.accuracy_radius_px)
                                acc = f"{hits / len(rc):.2f}"
                        self._click_csv_writer.writerow([
                            f"{sample.timestamp:.3f}",
                            sample.click_x, sample.click_y,
                            sample.predicted_x, sample.predicted_y,
                            f"{sample.residual_px:.1f}",
                            acc, phase,
                        ])
                        try:
                            self._click_csv_file.flush()
                        except Exception:
                            pass

            # Broadcast click data to Electron for desktop-stream overlay
            if self._broadcast_fn and recent_clicks:
                now_t = time.time()
                dots = []
                for s in recent_clicks:
                    age = now_t - s.timestamp
                    if age <= 10.0:
                        dots.append({
                            "cx": s.click_x, "cy": s.click_y,
                            "px": s.predicted_x, "py": s.predicted_y,
                            "r": round(s.residual_px, 1),
                            "age": round(age, 1),
                        })
                if dots:
                    try:
                        payload = {
                            "type": "eyeterm_click_dots",
                            "dots": dots,
                            "screen_w": self._screen_width or 1920,
                            "screen_h": self._screen_height or 1080,
                        }
                        if self._ga_calibrator:
                            payload["ga"] = self._ga_calibrator.status()
                        self._broadcast_fn(payload)
                    except Exception:
                        pass

            if recent_clicks:
                self._last_processed_click_ts = max(
                    s.timestamp for s in recent_clicks
                )

        # Broadcast live gaze cursor every frame (for permanent overlay)
        if self._broadcast_fn and self._gaze_valid:
            try:
                self._broadcast_fn({
                    "type": "eyeterm_gaze_cursor",
                    "x": self._gaze_screen_x,
                    "y": self._gaze_screen_y,
                    "screen_w": self._screen_width or 1920,
                    "screen_h": self._screen_height or 1080,
                })
            except Exception:
                pass

        if self._camera_server:
            self._camera_server.update_frame(ui_frame)
            self._camera_server.update_gaze(
                self._gaze_screen_x, self._gaze_screen_y,
                self._gaze_valid,
                self._screen_width, self._screen_height,
            )

        # CSV data logging (first 900 frames only)
        if self._csv_writer and self._csv_frame_count < self._csv_max_frames:
            move_info = self._cursor_driver._last_move_info if self._cursor_driver else {}
            def _fmt(v): return f"{v:.4f}" if v == v else ""  # NaN check
            hw = self._fusion.current_head_weight if self._fusion else 0.0
            self._csv_writer.writerow([
                self._csv_frame_count,
                f"{time.time():.3f}",
                _fmt(raw_x), _fmt(raw_y),
                _fmt(head_x), _fmt(head_y),
                f"{hw:.3f}",
                _fmt(fused_x), _fmt(fused_y),
                _fmt(smooth_x), _fmt(smooth_y),
                screen_x, screen_y,
                cursor_moved,
                move_info.get("blocked_by", ""),
                move_info.get("clamped", False),
                move_info.get("dx", 0),
                move_info.get("dy", 0),
            ])
            self._csv_frame_count += 1
            if self._csv_frame_count >= self._csv_max_frames:
                self._log(f"CSV logging complete ({self._csv_max_frames} frames)")
                try:
                    self._csv_file.flush()
                except Exception:
                    pass

    def _handle_action(self, action: str):
        """Execute state machine action."""
        if action in ("focus_pane", "update_focus"):
            pass
        elif action == "unfocus":
            self._current_element = None
        elif action == "send_escape":
            pass  # No terminal in headless mode
        elif action in ("start_polish", "start_polish_or_escape"):
            transcript = self._sm.pending_transcript
            if transcript:
                self._command_router.route(transcript, self._current_element)
                self._sm.pending_transcript = None

        # --- Dictation actions ---
        elif action == "start_dictation":
            if self._dictation:
                self._dictation.start_dictation()
                self._log("Dictation mode activated (head nod)")
        elif action == "start_enhancement":
            if self._dictation:
                gaze_ctx = None
                if self._current_element:
                    gaze_ctx = self._current_element.to_orchestrator_context()
                self._dictation.start_enhancement(gaze_context=gaze_ctx)
        elif action == "show_dictation_preview":
            self._log("Dictation preview ready")
        elif action == "cancel_dictation":
            if self._dictation:
                self._dictation.cancel()
                self._log("Dictation cancelled")
        elif action == "cancel_enhancement":
            if self._dictation:
                self._dictation.cancel()
                self._log("Enhancement cancelled")
        elif action == "insert_raw":
            if self._dictation:
                self._dictation.insert_raw()
                self._log("Inserted raw transcript")
        elif action == "insert_displayed":
            if self._dictation:
                self._dictation.insert_at_cursor()
                self._log("Inserted displayed text")
        elif action == "accept_enhanced":
            if self._dictation:
                self._dictation.accept_enhanced()
                self._log("Accepted enhanced text")
        elif action == "toggle_raw_enhanced":
            if self._dictation:
                mode = self._dictation.toggle_view()
                self._sm.showing_raw = (mode == "raw")
                self._log(f"Toggled to {mode}")
        elif action == "reject_polished":
            pass  # handled by existing flow
        elif action == "submit_polished":
            pass  # handled by existing flow

    def _on_stt_partial(self, text: str):
        self._transcript_partial = text
        # Route to dictation if in DICTATING state
        if self._dictation and self._sm.state == State.DICTATING:
            self._dictation.on_stt_partial(text)

    def _on_stt_final(self, text: str):
        self._transcript_final = text
        self._transcript_partial = ""
        if not text.strip():
            return
        # Dictation mode: feed to DictationController
        if self._dictation and self._sm.state == State.DICTATING:
            self._dictation.on_stt_final(text.strip())
            self._sm.raw_transcript = self._dictation.raw_transcript
        else:
            # Normal mode: route as command
            self._sm.pending_transcript = text.strip()
            self._command_router.route(text.strip(), self._current_element)

    def _execute_direct(self, cmd, element):
        """Direct desktop action — delegate to ActionExecutor."""
        try:
            from .action.executor import ActionExecutor
            if not hasattr(self, '_executor') or self._executor is None:
                self._executor = ActionExecutor()
            if element:
                self._executor.execute(cmd, element)
        except Exception as e:
            logger.error("Direct action failed: %s", e)

    def _route_to_agent_team(self, transcript, gaze_context):
        """Forward complex task to Moire Voice WebSocket."""
        logger.info("Agent team: %s", transcript[:80])
        if self._on_voice_command:
            self._on_voice_command(transcript, gaze_context)

    def _route_to_local_ai(self, transcript, element):
        """Forward short query to Moire Voice WebSocket."""
        logger.info("Local AI: %s", transcript[:80])
        if self._on_voice_command:
            ctx = element.to_orchestrator_context() if element else None
            self._on_voice_command(transcript, ctx)

    def _update_element_at_gaze(self, screen_x, screen_y, now_ms):
        if now_ms - self._last_uia_query_ms < 500:  # Throttle to 2 Hz (UIA is slow)
            return
        self._last_uia_query_ms = now_ms
        if self._uia is None:
            try:
                # COM must be initialized per-thread on Windows.
                # comtypes auto-inits MTA, but explicit init prevents
                # access violations in daemon threads.
                import ctypes
                try:
                    ctypes.windll.ole32.CoInitializeEx(0, 0)  # COINIT_MULTITHREADED
                except Exception:
                    pass
                from .screen.uia_inspector import UIAInspector
                self._uia = UIAInspector()
            except Exception:
                self._uia = False  # Mark as permanently failed
                return
        if self._uia is False:
            return
        try:
            self._current_element = self._uia.element_at_point(screen_x, screen_y)
        except Exception:
            self._current_element = None

    def _cleanup(self):
        if hasattr(self, '_ga_calibrator') and self._ga_calibrator:
            try:
                self._ga_calibrator.stop()
            except Exception:
                pass
        if hasattr(self, '_click_collector') and self._click_collector:
            try:
                self._click_collector.stop()
            except Exception:
                pass
        if self._click_csv_file:
            try:
                self._click_csv_file.close()
                self._log("Click CSV closed")
            except Exception:
                pass
        if self._csv_file:
            try:
                self._csv_file.close()
                self._log(f"CSV closed ({self._csv_frame_count} frames written)")
            except Exception:
                pass
        if self._stt:
            try:
                self._stt.stop()
            except Exception:
                pass
        if self._camera_server:
            self._camera_server.stop()
        if self._camera:
            self._camera.stop()
        if self._gaze:
            self._gaze.close()
        logger.info("eyeTerm headless cleanup complete")
