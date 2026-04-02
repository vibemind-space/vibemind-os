"""eyeTerm main application — ties all subsystems into the control loop.

Usage:
    python -m spaces.desktop.eyeterm.app
    python -m spaces.desktop.eyeterm.app --dirs C:/project1 C:/project2
    python -m spaces.desktop.eyeterm.app --camera 1
"""

import argparse
import logging
import time
from typing import Optional

import cv2
import numpy as np

from .config import AppConfig, PaneConfig
from .cursor.cursor_driver import CursorDriver
from .routing.command_router import CommandRouter, RouteTarget
from .routing.transcript_polisher import TranscriptPolisher
from .state import State, Event, StateMachine
from .stream.camera_server import CameraStreamServer
from .vision.camera import CameraCapture
from .vision.gaze import GazeEstimator, GazeSmoother, GazeToScreen, FocusRouter
from .vision.wink import WinkDetector
from .screen.element_context import UIElementContext
from .ui.overlay import OverlayRenderer

logger = logging.getLogger("eyeterm")


class EyeTermApp:
    """Main eyeTerm application."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._sm = StateMachine()

        # Vision (initialized in run)
        self._camera: Optional[CameraCapture] = None
        self._gaze: Optional[GazeEstimator] = None
        self._smoother: Optional[GazeSmoother] = None
        self._screen_mapper: Optional[GazeToScreen] = None
        self._focus_router: Optional[FocusRouter] = None
        self._wink: Optional[WinkDetector] = None
        self._cursor_driver: Optional[CursorDriver] = None

        # Audio (lazy)
        self._stt = None
        self._stt_active = False

        # Screen understanding (lazy)
        self._uia = None

        # Command routing
        self._command_router = CommandRouter(
            on_direct=self._execute_direct,
            on_agent_team=self._route_to_agent_team,
            on_local_ai=self._route_to_local_ai,
        )

        # Terminal launcher (for real terminal windows)
        self._terminal_launcher = None

        # UI
        self._overlay: Optional[OverlayRenderer] = None

        # Transcript polisher
        self._polisher = TranscriptPolisher()

        # MJPEG camera stream server (for Electron embedding)
        self._camera_server: Optional[CameraStreamServer] = None

        # Runtime state
        self._transcript_partial = ""
        self._transcript_final = ""
        self._current_element: Optional[UIElementContext] = None
        self._show_debug = False
        self._ear_values = (0.0, 0.0)
        self._landmarks = None
        self._head_pose = None
        self._last_wink_event = None
        self._last_uia_query_ms = 0
        self._uia_throttle_ms = 200  # Query UIA max every 200ms
        self._polish_preview = None  # Dict with 'original' and 'polished' keys
        self._preview_start_ms = 0   # Timestamp for preview timeout
        self._preview_timeout_ms = 10000  # Auto-dismiss preview after 10s
        self._running = False

    def _init_vision(self):
        """Initialize camera + gaze + wink."""
        self._camera = CameraCapture(self._config.camera_index)
        self._camera.start()

        self._gaze = GazeEstimator()
        self._smoother = GazeSmoother(alpha=self._config.gaze.ema_alpha)

        # Get screen dimensions
        try:
            from screeninfo import get_monitors
            monitor = get_monitors()[0]
            sw, sh = monitor.width, monitor.height
        except Exception:
            sw, sh = 1920, 1080

        self._screen_mapper = GazeToScreen(sw, sh)
        self._focus_router = FocusRouter(
            num_panes=max(1, len(self._config.panes)),
            dwell_ms=self._config.gaze.dwell_ms,
            screen_width=sw,
            screen_height=sh,
        )
        self._wink = WinkDetector(
            ear_threshold=self._config.wink.ear_threshold,
            min_frames=self._config.wink.min_frames,
            cooldown_ms=self._config.wink.cooldown_ms,
        )
        self._cursor_driver = CursorDriver(
            enabled=self._config.cursor.enabled,
            deadzone_px=self._config.cursor.deadzone_px,
            require_face=self._config.cursor.require_face,
        )

    def _init_audio(self):
        """Initialize Vosk STT (lazy — only when needed)."""
        if self._stt is not None:
            return
        try:
            from .audio.stt_vosk import VoskSTT
            model_path = self._config.audio.vosk_model_path
            if not model_path:
                logger.warning("No Vosk model path configured. STT disabled.")
                return
            self._stt = VoskSTT(model_path, self._config.audio.sample_rate)
            logger.info("Vosk STT initialized: %s", model_path)
        except ImportError:
            logger.warning("vosk not installed. STT disabled. Run: pip install vosk")
        except Exception as e:
            logger.warning("Failed to init Vosk: %s", e)

    def _init_screen(self):
        """Initialize UI Automation inspector (lazy)."""
        if self._uia is not None:
            return
        try:
            from .screen.uia_inspector import UIAInspector
            self._uia = UIAInspector()
            logger.info("Windows UI Automation initialized")
        except Exception as e:
            logger.warning("UIA init failed: %s", e)

    def _start_stt(self):
        """Start speech-to-text capture."""
        self._init_audio()
        if self._stt is None:
            return
        self._transcript_partial = ""
        self._transcript_final = ""
        self._stt.start(
            on_partial=self._on_stt_partial,
            on_final=self._on_stt_final,
        )
        self._stt_active = True
        logger.debug("STT started")

    def _stop_stt(self):
        """Stop speech-to-text capture."""
        if self._stt and self._stt_active:
            self._stt.stop()
            self._stt_active = False
        self._transcript_partial = ""
        logger.debug("STT stopped")

    def _on_stt_partial(self, text: str):
        """Callback from Vosk with partial transcript."""
        self._transcript_partial = text

    def _on_stt_final(self, text: str):
        """Callback from Vosk with final transcript.

        Routes through CommandRouter: direct actions execute locally,
        complex tasks go to the agent team.
        Stores transcript for potential polish via left wink.
        """
        self._transcript_final = text
        self._transcript_partial = ""
        # Store for polish flow (left wink will trigger polishing)
        if text.strip():
            self._sm.pending_transcript = text.strip()
            self._command_router.route(text.strip(), self._current_element)

    def _execute_direct(self, cmd, element):
        """Callback: execute a direct desktop action locally."""
        from .action.executor import ActionExecutor
        try:
            if not hasattr(self, '_executor') or self._executor is None:
                self._executor = ActionExecutor()
            if element:
                result = self._executor.execute(cmd, element)
                logger.info("Direct action %s: %s", cmd.action, result.get("message", "")[:60])
            else:
                logger.info("Direct action %s (no element context)", cmd.action)
        except Exception as e:
            logger.error("Direct action failed: %s", e)

    def _route_to_agent_team(self, transcript, gaze_context):
        """Callback: route complex task to VibeMind orchestrator / MinibookHub."""
        logger.info("Agent team task: %s", transcript[:80])
        # Integration point: will be wired in Phase 6 to IntentOrchestrator or MinibookHub
        # For now, log and store for UI display
        self._transcript_final = f"[AGENT] {transcript}"

    def _route_to_local_ai(self, transcript, element):
        """Callback: use local AI (Claude CLI) for short freeform queries."""
        logger.info("Local AI query: %s", transcript[:80])
        # Integration point: will use IntentResolver from ai/intent_resolver.py
        self._transcript_final = f"[AI] {transcript}"

    def _handle_action(self, action: str):
        """Execute a state machine action."""
        if action == "focus_pane" or action == "update_focus":
            pass  # Visual update handled in render

        elif action == "unfocus":
            self._current_element = None
            self._polish_preview = None

        elif action == "send_escape":
            if self._terminal_launcher and self._sm.focused_pane is not None:
                self._terminal_launcher.send_escape(self._sm.focused_pane)
                logger.info("Sent Esc Esc to pane %d", self._sm.focused_pane)

        elif action == "send_text":
            # Handled directly in _on_stt_final for lower latency
            pass

        # --- Polish / Preview flow ---

        elif action == "start_polish":
            transcript = self._sm.pending_transcript
            if transcript:
                element_ctx = self._current_element.to_orchestrator_context() if self._current_element else None
                self._polish_preview = {"original": transcript, "polished": None}
                self._polisher.polish(
                    transcript,
                    element_context=element_ctx,
                    on_complete=self._on_polish_complete,
                )
                logger.info("Started polishing: %s", transcript[:60])

        elif action == "cancel_polish":
            self._polisher.cancel()
            self._polish_preview = None
            logger.info("Polish cancelled")

        elif action == "cancel_polish_and_unfocus":
            self._polisher.cancel()
            self._polish_preview = None
            self._current_element = None
            logger.info("Polish cancelled (gaze lost)")

        elif action == "show_preview":
            # polished_text was set via _on_polish_complete → state machine
            self._preview_start_ms = int(time.time() * 1000)
            logger.info("Showing polish preview")

        elif action == "submit_polished":
            polished = self._sm.polished_text
            if polished:
                self._command_router.route(polished, self._current_element)
                logger.info("Submitted polished text: %s", polished[:60])
            self._polish_preview = None
            self._sm.polished_text = None
            self._sm.pending_transcript = None

        elif action == "reject_polished":
            self._polish_preview = None
            self._sm.polished_text = None
            logger.info("Polished text rejected, can re-dictate")

        elif action == "dismiss_preview":
            self._polish_preview = None
            self._sm.polished_text = None
            logger.info("Preview auto-dismissed")

        elif action == "dismiss_preview_and_unfocus":
            self._polish_preview = None
            self._sm.polished_text = None
            self._current_element = None
            logger.info("Preview dismissed (gaze lost)")

    def _on_polish_complete(self, polished_text: str):
        """Callback from TranscriptPolisher (runs on worker thread).

        Triggers POLISH_COMPLETE event on the state machine.
        """
        # Update preview with polished text (thread-safe: simple attribute set)
        if self._polish_preview:
            self._polish_preview["polished"] = polished_text
        # Transition state machine
        _, action = self._sm.transition(Event.POLISH_COMPLETE, polished_text)
        if action:
            self._handle_action(action)

    def _check_preview_timeout(self, now_ms: int):
        """Auto-dismiss preview after timeout."""
        if self._sm.state == State.PREVIEWING and self._preview_start_ms > 0:
            if now_ms - self._preview_start_ms > self._preview_timeout_ms:
                _, action = self._sm.transition(Event.PREVIEW_TIMEOUT)
                if action:
                    self._handle_action(action)

    def _update_element_at_gaze(self, screen_x: int, screen_y: int, now_ms: int):
        """Query UI Automation for the element at gaze point (throttled)."""
        if now_ms - self._last_uia_query_ms < self._uia_throttle_ms:
            return
        self._last_uia_query_ms = now_ms

        self._init_screen()
        if self._uia is None:
            return
        try:
            self._current_element = self._uia.element_at_point(screen_x, screen_y)
        except Exception:
            self._current_element = None

    @staticmethod
    def _compute_head_pose(landmarks) -> tuple:
        """Estimate head yaw/pitch from landmark geometry."""
        nose = landmarks[1]
        left_eye = landmarks[33]
        right_eye = landmarks[263]
        mid_eye_x = (left_eye.x + right_eye.x) / 2
        mid_eye_y = (left_eye.y + right_eye.y) / 2
        yaw = mid_eye_x - nose.x
        pitch = nose.y - mid_eye_y
        return (yaw, pitch)

    def _run_calibration(self):
        """Run interactive calibration."""
        try:
            from .vision.calibrate import CalibrationRunner
            if self._gaze and self._camera and self._screen_mapper:
                runner = CalibrationRunner(
                    self._screen_mapper._screen_width,
                    self._screen_mapper._screen_height,
                )
                matrix = runner.run_calibration(self._gaze, self._camera)
                if matrix is not None:
                    self._screen_mapper.set_calibration(matrix)
                    logger.info("Calibration complete")
        except Exception as e:
            logger.error("Calibration failed: %s", e)

    def _build_pane_statuses(self):
        """Build pane status list for overlay."""
        statuses = []
        for i, pane in enumerate(self._config.panes):
            statuses.append({
                "name": pane.name,
                "is_busy": False,
                "last_snippet": "",
            })
        return statuses

    def _init_terminals(self):
        """Launch real terminal windows with Claude Code."""
        if not self._config.panes:
            return
        try:
            from .claude.launcher import TerminalLauncher
            try:
                from screeninfo import get_monitors
                monitor = get_monitors()[0]
                sw, sh = monitor.width, monitor.height
            except Exception:
                sw, sh = 1920, 1080

            self._terminal_launcher = TerminalLauncher(sw, sh)
            workdirs = [p.workdir for p in self._config.panes]
            self._terminal_launcher.launch(workdirs)
            logger.info("Launched %d terminal windows", len(workdirs))
        except Exception as e:
            logger.warning("Terminal launch failed: %s", e)

    def run(self):
        """Main loop. Blocks until 'q' key or window close."""
        logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
        logger.info("eyeTerm starting with %d panes", len(self._config.panes))

        self._init_vision()
        self._overlay = OverlayRenderer(
            self._config.window_width,
            self._config.window_height,
            max(1, len(self._config.panes)),
        )
        self._running = True

        # Launch real terminal windows if dirs configured
        if self._config.panes:
            self._init_terminals()

        # Start MJPEG camera stream if enabled
        if self._config.stream.enabled:
            self._camera_server = CameraStreamServer(port=self._config.stream.port)
            self._camera_server.start()

        # Start always-on STT if model configured
        self._init_audio()
        if self._stt:
            self._start_stt()
            logger.info("Voice dictation active (always-on mode)")

        cv2.namedWindow("eyeTerm", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("eyeTerm", self._config.window_width, self._config.window_height)

        frame_time_ms = 1000 // self._config.target_fps
        gaze_point = None

        while self._running:
            t_start = time.perf_counter_ns()

            # 1. Capture frame
            frame = self._camera.read() if self._camera else None
            if frame is None:
                time.sleep(0.01)
                continue

            # 2. Gaze estimation
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            gaze_result = self._gaze.estimate(frame_rgb)
            now_ms = int(time.time() * 1000)

            screen_x, screen_y = None, None
            if gaze_result is not None:
                sx, sy = self._smoother.smooth((gaze_result.x, gaze_result.y))
                gaze_point = (sx, sy)
                screen_x, screen_y = self._screen_mapper.to_screen(sx, sy)

                # Cursor control: move real cursor to gaze position
                if self._cursor_driver:
                    self._cursor_driver.set_face_detected(True)
                    self._cursor_driver.move(screen_x, screen_y)

                # Wink detection (needs landmarks from gaze estimator)
                if gaze_result.landmarks:
                    self._landmarks = gaze_result.landmarks
                    wink = self._wink.update(gaze_result.landmarks, now_ms)
                    self._ear_values = WinkDetector.get_ear_values(gaze_result.landmarks)
                    self._head_pose = self._compute_head_pose(gaze_result.landmarks)
                    self._last_wink_event = wink  # pass to overlay

                    if wink in ("confirm", "cancel"):
                        event = Event.LEFT_WINK if wink == "confirm" else Event.RIGHT_WINK
                        _, action = self._sm.transition(event)
                        if action:
                            self._handle_action(action)

                # Focus routing (skip during POLISHING/PREVIEWING — user is busy)
                if self._sm.state in (State.IDLE, State.FOCUSED):
                    pane = self._focus_router.update(screen_x, screen_y, now_ms)
                    if pane is not None:
                        _, action = self._sm.transition(Event.GAZE_DWELL, pane)
                        if action:
                            self._handle_action(action)
                        # Update element at gaze point
                        self._update_element_at_gaze(screen_x, screen_y, now_ms)
                    elif self._sm.state == State.FOCUSED:
                        # Check if gaze left current pane area
                        current_pane = self._focus_router.get_current_pane(screen_x, screen_y)
                        if current_pane != self._sm.focused_pane:
                            _, action = self._sm.transition(Event.GAZE_LOST)
                            if action:
                                self._handle_action(action)
            else:
                gaze_point = None
                if self._cursor_driver:
                    self._cursor_driver.set_face_detected(False)

            # 2b. Check preview timeout
            self._check_preview_timeout(now_ms)

            # 3. Render UI
            element_summary = ""
            if self._current_element:
                element_summary = self._current_element.summary()

            ui_frame = self._overlay.render(
                camera_frame=frame,
                state_name=self._sm.state.value,
                focused_pane=self._sm.focused_pane,
                element_summary=element_summary,
                pane_statuses=self._build_pane_statuses(),
                transcript_partial=self._transcript_partial,
                transcript_final=self._transcript_final,
                gaze_point=gaze_point,
                ear_values=self._ear_values,
                show_debug=self._show_debug,
                landmarks=self._landmarks,
                head_pose=self._head_pose,
                wink_event=self._last_wink_event,
                cursor_enabled=self._cursor_driver.enabled if self._cursor_driver else False,
                polish_preview=self._polish_preview,
            )
            self._last_wink_event = None  # consume after rendering

            # Push frame to MJPEG stream for Electron
            if self._camera_server:
                self._camera_server.update_frame(ui_frame)

            cv2.imshow("eyeTerm", ui_frame)

            # 4. Handle keyboard
            key = cv2.waitKey(max(1, frame_time_ms)) & 0xFF
            if key == ord('q'):
                self._running = False
            elif key == ord('c'):
                self._run_calibration()
            elif key == ord('d'):
                self._show_debug = not self._show_debug
            elif key == ord('g'):
                if self._cursor_driver:
                    state = self._cursor_driver.toggle()
                    logger.info("Cursor control: %s", "ON" if state else "OFF")
            elif key == ord('r'):
                self._sm.reset()
                self._stop_stt()

        self._cleanup()

    def _cleanup(self):
        """Release all resources."""
        self._stop_stt()
        if self._polisher:
            self._polisher.shutdown()
        if self._camera_server:
            self._camera_server.stop()
        if self._camera:
            self._camera.stop()
        if self._gaze:
            self._gaze.close()
        cv2.destroyAllWindows()
        logger.info("eyeTerm stopped")


def main():
    """CLI entry point."""
    logger.debug("main called")
    parser = argparse.ArgumentParser(description="eyeTerm - Hands-free screen controller")
    parser.add_argument("--dirs", nargs="+", help="Working directories for Claude Code panes")
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    parser.add_argument("--vosk-model", help="Path to Vosk model directory")
    args = parser.parse_args()

    if args.dirs:
        config = AppConfig.from_dirs(args.dirs, camera_index=args.camera)
    else:
        config = AppConfig.from_env()

    if args.vosk_model:
        config.audio.vosk_model_path = args.vosk_model

    config.camera_index = args.camera

    app = EyeTermApp(config)
    app.run()


if __name__ == "__main__":
    main()
