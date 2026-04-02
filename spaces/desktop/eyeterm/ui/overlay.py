"""OpenCV-based UI renderer for eyeTerm — Camera Preview + Terminal Panes."""

import cv2
import logging
import math
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color scheme (BGR)
# ---------------------------------------------------------------------------
COLOR_BG = (30, 26, 26)
COLOR_GRID = (80, 80, 80)
COLOR_FOCUS = (255, 212, 0)       # cyan highlight (BGR for #00d4ff)
COLOR_LISTENING = (136, 255, 0)   # green
COLOR_CONFIRMING = (0, 220, 255)  # yellow
COLOR_EXECUTING = (0, 140, 255)   # orange
COLOR_TEXT = (220, 220, 220)
COLOR_DIM = (140, 140, 140)
COLOR_MESH = (0, 180, 0)          # green face mesh
COLOR_IRIS = (255, 212, 0)        # cyan iris
COLOR_WINK_BG = (0, 140, 200)    # orange badge bg
COLOR_DIFF_ADD = (0, 200, 0)
COLOR_DIFF_DEL = (0, 0, 200)
COLOR_PANE_HEADER = (50, 45, 45)
COLOR_PANE_ACTIVE = COLOR_FOCUS
COLOR_PANE_TEXT = (0, 220, 130)   # terminal green

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_MONO = cv2.FONT_HERSHEY_PLAIN
_LINE_HEIGHT = 22

COLOR_POLISHING = (200, 140, 0)     # blue-ish for polishing
COLOR_PREVIEWING = (0, 180, 220)    # yellow-ish for previewing

_STATE_COLORS = {
    "IDLE": (120, 120, 120),
    "FOCUSED": COLOR_FOCUS,
    "POLISHING": COLOR_POLISHING,
    "PREVIEWING": COLOR_PREVIEWING,
    "LISTENING": COLOR_LISTENING,
    "CONFIRMING": COLOR_CONFIRMING,
    "EXECUTING": COLOR_EXECUTING,
}

# ---------------------------------------------------------------------------
# Face mesh connection lists (key contours only)
# ---------------------------------------------------------------------------
_JAWLINE = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10,
]
_LEFT_EYE = [33, 160, 158, 133, 153, 144, 33]
_RIGHT_EYE = [362, 385, 387, 263, 373, 380, 362]
_LEFT_EYEBROW = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
_RIGHT_EYEBROW = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
_NOSE_BRIDGE = [168, 6, 197, 195, 5]
_NOSE_BOTTOM = [98, 97, 2, 326, 327]
_LIPS_OUTER = [
    61, 146, 91, 181, 84, 17, 314, 405, 321, 375,
    291, 409, 270, 269, 267, 0, 37, 39, 40, 185, 61,
]
_LIPS_INNER = [
    78, 95, 88, 178, 87, 14, 317, 402, 318, 324,
    308, 415, 310, 311, 312, 13, 82, 81, 80, 191, 78,
]
_LEFT_IRIS = [468, 469, 470, 471, 472]   # center + ring
_RIGHT_IRIS = [473, 474, 475, 476, 477]


class OverlayRenderer:
    """Draws the eyeTerm UI: camera preview with face mesh + terminal panes."""

    def __init__(
        self, width: int = 1280, height: int = 720, num_panes: int = 4
    ):
        self._w = width
        self._h = height
        self._num_panes = max(1, num_panes)
        # Wink indicator state
        self._last_wink_label = ""
        self._wink_count = 0
        self._wink_show_frames = 0

    def render(
        self,
        camera_frame: Optional[np.ndarray],
        state_name: str,
        focused_pane: Optional[int],
        element_summary: str,
        pane_statuses: List[Dict],
        transcript_partial: str,
        transcript_final: str,
        gaze_point: Optional[Tuple[float, float]],
        ear_values: Optional[Tuple[float, float]],
        show_debug: bool = False,
        landmarks: Any = None,
        head_pose: Optional[Tuple[float, float]] = None,
        wink_event: Optional[str] = None,
        cursor_enabled: bool = False,
        polish_preview: Optional[Dict[str, str]] = None,
    ) -> np.ndarray:
        """Compose the full UI frame."""
        logger.debug("render called: state=%s focused_pane=%s", state_name, focused_pane)

        canvas = np.full((self._h, self._w, 3), COLOR_BG, dtype=np.uint8)

        # Layout: camera left 40%, panes right 60%
        cam_w = int(self._w * 0.4)
        pane_x0 = cam_w
        pane_w = self._w - cam_w
        header_h = 32
        transcript_h = 44
        body_top = header_h
        body_bottom = self._h - transcript_h

        # 1. Camera preview with face mesh
        self._draw_camera_preview(
            canvas, camera_frame, landmarks, gaze_point, head_pose,
            ear_values, show_debug, 0, body_top, cam_w, body_bottom - body_top,
        )

        # 2. Wink indicator on camera
        self._update_wink(wink_event)
        self._draw_wink_indicator(canvas, cam_w)

        # 3. Terminal-style panes (right side)
        self._draw_terminal_panes(
            canvas, focused_pane, pane_statuses,
            pane_x0, body_top, pane_w, body_bottom - body_top,
        )

        # 4. Top header bar
        self._draw_header(canvas, state_name, element_summary, header_h,
                          cursor_enabled=cursor_enabled)

        # 5. Bottom transcript bar
        self._draw_transcript(canvas, transcript_partial, transcript_final, transcript_h)

        # 6. Polish preview overlay (on top of everything)
        if polish_preview:
            self._draw_polish_preview(canvas, polish_preview)

        return canvas

    # ------------------------------------------------------------------
    # Calibration overlay
    # ------------------------------------------------------------------

    def render_calibration(
        self,
        camera_frame: Optional[np.ndarray],
        instruction: str,
        point_index: int,
        total_points: int,
        progress: float,
    ) -> np.ndarray:
        """Render calibration UI over the camera frame.

        Shows instruction text, point counter, and progress bar.
        """
        logger.debug("render_calibration called: point %s/%s", point_index, total_points)
        canvas = np.full((self._h, self._w, 3), COLOR_BG, dtype=np.uint8)

        # Camera preview (dimmed for readability)
        if camera_frame is not None:
            resized = cv2.resize(camera_frame, (self._w, self._h))
            canvas = (resized * 0.4).astype(np.uint8)

        # "KALIBRIERUNG" header
        cv2.putText(canvas, "KALIBRIERUNG", (20, 40),
                    _FONT, 0.9, COLOR_FOCUS, 2, cv2.LINE_AA)

        # Point counter
        counter = f"Punkt {point_index + 1}/{total_points}"
        (cw, _), _ = cv2.getTextSize(counter, _FONT, 0.7, 1)
        cv2.putText(canvas, counter, (self._w - cw - 20, 40),
                    _FONT, 0.7, COLOR_TEXT, 1, cv2.LINE_AA)

        # Main instruction (centered, large, with background box)
        (tw, th), _ = cv2.getTextSize(instruction, _FONT, 1.2, 2)
        tx = (self._w - tw) // 2
        ty = self._h // 2
        pad = 24
        cv2.rectangle(canvas,
                      (tx - pad, ty - th - pad),
                      (tx + tw + pad, ty + pad),
                      (0, 0, 0), -1)
        cv2.rectangle(canvas,
                      (tx - pad, ty - th - pad),
                      (tx + tw + pad, ty + pad),
                      COLOR_FOCUS, 1)
        cv2.putText(canvas, instruction, (tx, ty),
                    _FONT, 1.2, (255, 255, 255), 2, cv2.LINE_AA)

        # Progress bar (bottom)
        bar_y = self._h - 60
        bar_h = 16
        margin = 40
        bar_w = self._w - margin * 2
        # Background
        cv2.rectangle(canvas, (margin, bar_y),
                      (margin + bar_w, bar_y + bar_h), (50, 50, 50), -1)
        # Fill
        fill_w = max(1, int(bar_w * progress))
        cv2.rectangle(canvas, (margin, bar_y),
                      (margin + fill_w, bar_y + bar_h), COLOR_FOCUS, -1)
        # Border
        cv2.rectangle(canvas, (margin, bar_y),
                      (margin + bar_w, bar_y + bar_h), COLOR_GRID, 1)

        return canvas

    # ------------------------------------------------------------------
    # Camera preview with face mesh
    # ------------------------------------------------------------------

    def _draw_camera_preview(
        self, canvas: np.ndarray,
        frame: Optional[np.ndarray],
        landmarks: Any,
        gaze_point: Optional[Tuple[float, float]],
        head_pose: Optional[Tuple[float, float]],
        ear_values: Optional[Tuple[float, float]],
        show_debug: bool,
        x0: int, y0: int, w: int, h: int,
    ) -> None:
        if frame is None:
            cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), COLOR_GRID, 1)
            cv2.putText(canvas, "No camera", (x0 + w // 3, y0 + h // 2),
                        _FONT, 0.6, COLOR_DIM, 1)
            return

        # Resize camera frame to fill the camera area
        resized = cv2.resize(frame, (w, h))

        # Draw face mesh on the resized frame
        if landmarks is not None:
            self._draw_face_mesh(resized, landmarks, w, h)

        # Place on canvas
        canvas[y0:y0 + h, x0:x0 + w] = resized

        # Head pose overlay (bottom-left of camera)
        if head_pose is not None:
            yaw, pitch = head_pose
            cv2.putText(canvas, f"Yaw: {yaw:+.3f}",
                        (x0 + 8, y0 + h - 30), _FONT, 0.45, COLOR_LISTENING, 1)
            cv2.putText(canvas, f"Pitch: {pitch:+.3f}",
                        (x0 + 8, y0 + h - 10), _FONT, 0.45, COLOR_LISTENING, 1)

        # EAR debug (top-right of camera)
        if show_debug and ear_values is not None:
            left_ear, right_ear = ear_values
            cv2.putText(canvas, f"EAR L:{left_ear:.3f} R:{right_ear:.3f}",
                        (x0 + w - 220, y0 + 20), _FONT, 0.4, COLOR_DIM, 1)

        # Title
        cv2.putText(canvas, "eyeTerm - Camera Preview",
                    (x0 + 8, y0 + 18), _FONT, 0.45, COLOR_DIM, 1)

        # Border
        cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), COLOR_GRID, 1)

    def _draw_face_mesh(
        self, frame: np.ndarray, landmarks: Any, w: int, h: int
    ) -> None:
        """Draw face mesh contours, iris, and landmarks on the camera frame."""

        def lm_pt(idx: int) -> Tuple[int, int]:
            lm = landmarks[idx]
            return (int(lm.x * w), int(lm.y * h))

        # Draw contour polylines
        for contour, color, thickness in [
            (_JAWLINE, COLOR_MESH, 1),
            (_LEFT_EYE, COLOR_MESH, 1),
            (_RIGHT_EYE, COLOR_MESH, 1),
            (_LEFT_EYEBROW, COLOR_MESH, 1),
            (_RIGHT_EYEBROW, COLOR_MESH, 1),
            (_NOSE_BRIDGE, COLOR_MESH, 1),
            (_NOSE_BOTTOM, COLOR_MESH, 1),
            (_LIPS_OUTER, COLOR_MESH, 1),
            (_LIPS_INNER, COLOR_MESH, 1),
        ]:
            pts = np.array([lm_pt(i) for i in contour], dtype=np.int32)
            cv2.polylines(frame, [pts], isClosed=False, color=color, thickness=thickness)

        # Draw iris landmarks (cyan filled circles)
        for iris_indices in [_LEFT_IRIS, _RIGHT_IRIS]:
            for i, idx in enumerate(iris_indices):
                pt = lm_pt(idx)
                radius = 3 if i == 0 else 2  # center bigger
                cv2.circle(frame, pt, radius, COLOR_IRIS, -1)

            # Draw iris ring connection
            ring_pts = np.array([lm_pt(idx) for idx in iris_indices[1:]], dtype=np.int32)
            if len(ring_pts) >= 3:
                cv2.polylines(frame, [ring_pts], isClosed=True, color=COLOR_IRIS, thickness=1)

    # ------------------------------------------------------------------
    # Wink indicator
    # ------------------------------------------------------------------

    def _update_wink(self, wink_event: Optional[str]) -> None:
        if wink_event:
            label = "confirm" if wink_event == "confirm" else "cancel"
            if label == self._last_wink_label:
                self._wink_count += 1
            else:
                self._wink_count = 1
                self._last_wink_label = label
            self._wink_show_frames = 45  # show for ~1.5s at 30fps
        elif self._wink_show_frames > 0:
            self._wink_show_frames -= 1

    def _draw_wink_indicator(self, canvas: np.ndarray, cam_w: int) -> None:
        if self._wink_show_frames <= 0 or not self._last_wink_label:
            return

        text = f"[wink] {self._last_wink_label} x{self._wink_count}"
        (tw, th), _ = cv2.getTextSize(text, _FONT, 0.55, 1)
        pad = 6
        x = (cam_w - tw) // 2 - pad
        y = 50
        # Orange badge background
        cv2.rectangle(canvas, (x, y), (x + tw + pad * 2, y + th + pad * 2), COLOR_WINK_BG, -1)
        cv2.putText(canvas, text, (x + pad, y + th + pad), _FONT, 0.55, (255, 255, 255), 1)

    # ------------------------------------------------------------------
    # Terminal-style panes
    # ------------------------------------------------------------------

    def _draw_terminal_panes(
        self, canvas: np.ndarray,
        focused: Optional[int],
        statuses: List[Dict],
        x0: int, y0: int, w: int, h: int,
    ) -> None:
        n = self._num_panes
        if n <= 0:
            return

        # Stack panes vertically, 2-column if 4 panes
        if n <= 2:
            cols, rows = 1, n
        else:
            cols = 2
            rows = (n + 1) // 2

        cell_w = w // cols
        cell_h = h // rows
        pane_header_h = 24

        for idx in range(n):
            col = idx % cols
            row = idx // cols
            px = x0 + col * cell_w
            py = y0 + row * cell_h
            pw = cell_w
            ph = cell_h

            status = statuses[idx] if idx < len(statuses) else {}
            name = status.get("name", f"Pane {idx}")
            is_busy = status.get("is_busy", False)
            snippet = status.get("last_snippet", "")
            is_focused = focused is not None and idx == focused

            # Pane background (dark terminal)
            cv2.rectangle(canvas, (px + 1, py + 1), (px + pw - 1, py + ph - 1),
                          (20, 18, 18), -1)

            # Header bar
            header_color = COLOR_PANE_ACTIVE if is_focused else COLOR_PANE_HEADER
            cv2.rectangle(canvas, (px, py), (px + pw, py + pane_header_h), header_color, -1)

            # Header text
            header_text = f" {name}"
            if is_busy:
                header_text += "  [running...]"
            text_color = (0, 0, 0) if is_focused else COLOR_TEXT
            cv2.putText(canvas, header_text, (px + 4, py + 16),
                        _FONT, 0.4, text_color, 1)

            # Claude icon indicator
            if is_focused:
                cv2.putText(canvas, "Claude Code", (px + pw - 90, py + 16),
                            _FONT, 0.35, (0, 0, 0), 1)

            # Terminal content area
            content_y = py + pane_header_h + 16
            if snippet:
                # Word-wrap snippet into terminal area
                max_chars = (pw - 16) // 7  # approximate char width
                lines = [snippet[i:i + max_chars] for i in range(0, len(snippet), max_chars)]
                for i, line in enumerate(lines[:6]):
                    cv2.putText(canvas, line,
                                (px + 8, content_y + i * 16),
                                _FONT_MONO, 1.0, COLOR_PANE_TEXT, 1)
            else:
                # Empty terminal prompt
                prompt = f"$ claude --resume pane-{idx}"
                cv2.putText(canvas, prompt, (px + 8, content_y),
                            _FONT_MONO, 1.0, COLOR_PANE_TEXT, 1)
                cv2.putText(canvas, "Waiting for command...",
                            (px + 8, content_y + 20), _FONT_MONO, 1.0, COLOR_DIM, 1)

            # Border (cyan if focused, gray otherwise)
            border_color = COLOR_PANE_ACTIVE if is_focused else COLOR_GRID
            thickness = 2 if is_focused else 1
            cv2.rectangle(canvas, (px, py), (px + pw, py + ph), border_color, thickness)

    # ------------------------------------------------------------------
    # Header bar
    # ------------------------------------------------------------------

    def _draw_header(self, canvas: np.ndarray, state_name: str,
                     element_summary: str, header_h: int,
                     cursor_enabled: bool = False) -> None:
        # Dark header background
        cv2.rectangle(canvas, (0, 0), (self._w, header_h), (20, 18, 18), -1)

        # State badge
        color = _STATE_COLORS.get(state_name.upper(), (120, 120, 120))
        badge = state_name.upper()
        (tw, th), _ = cv2.getTextSize(badge, _FONT, 0.5, 1)
        pad = 5
        cv2.rectangle(canvas, (6, 4), (6 + tw + pad * 2, 4 + th + pad * 2), color, -1)
        cv2.putText(canvas, badge, (6 + pad, 4 + th + pad), _FONT, 0.5, (0, 0, 0), 1)

        next_x = 6 + tw + pad * 2 + 10

        # Cursor control badge
        if cursor_enabled:
            cursor_text = "CURSOR ON"
            (cw, ch), _ = cv2.getTextSize(cursor_text, _FONT, 0.45, 1)
            cv2.rectangle(canvas, (next_x, 4), (next_x + cw + pad * 2, 4 + ch + pad * 2),
                          (0, 200, 0), -1)
            cv2.putText(canvas, cursor_text, (next_x + pad, 4 + ch + pad),
                        _FONT, 0.45, (0, 0, 0), 1)
            next_x += cw + pad * 2 + 10

        # Element info (to the right of badges)
        if element_summary:
            text = element_summary[:90]
            cv2.putText(canvas, text, (next_x, 20), _FONT, 0.4, COLOR_TEXT, 1)

    # ------------------------------------------------------------------
    # Transcript bar
    # ------------------------------------------------------------------

    def _draw_transcript(self, canvas: np.ndarray, partial: str, final: str,
                         bar_h: int) -> None:
        bar_y = self._h - bar_h
        cv2.rectangle(canvas, (0, bar_y), (self._w, self._h), (20, 18, 18), -1)
        cv2.line(canvas, (0, bar_y), (self._w, bar_y), COLOR_GRID, 1)

        text_y = bar_y + 28
        if final:
            cv2.putText(canvas, final[:120], (10, text_y), _FONT, 0.5, (255, 255, 255), 1)
        if partial:
            x_off = 10
            if final:
                (tw, _), _ = cv2.getTextSize(final[:120], _FONT, 0.5, 1)
                x_off = tw + 30
            cv2.putText(canvas, partial[:80], (x_off, text_y), _FONT, 0.5, COLOR_DIM, 1)

    # ------------------------------------------------------------------
    # Polish preview overlay
    # ------------------------------------------------------------------

    def _draw_polish_preview(self, canvas: np.ndarray, preview: Dict[str, str]) -> None:
        """Draw floating polish preview panel.

        Args:
            preview: Dict with 'original' and 'polished' keys.
                     If 'polished' is None, shows a "Polishing..." spinner.
        """
        original = preview.get("original", "")
        polished = preview.get("polished")
        is_loading = polished is None

        pad = 16
        line_h = _LINE_HEIGHT
        box_w = min(self._w - 60, 700)

        # Calculate height based on content
        lines_needed = 3  # header + original label + original text
        if not is_loading:
            lines_needed += 3  # polished label + polished text + instructions
        else:
            lines_needed += 1  # spinner
        lines_needed += 1  # instructions

        box_h = lines_needed * line_h + pad * 3
        x0 = (self._w - box_w) // 2
        y0 = (self._h - box_h) // 2

        # Semi-transparent background
        overlay = canvas.copy()
        cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), (20, 20, 30), -1)
        cv2.addWeighted(overlay, 0.92, canvas, 0.08, 0, canvas)

        # Border
        border_color = COLOR_POLISHING if is_loading else COLOR_PREVIEWING
        cv2.rectangle(canvas, (x0, y0), (x0 + box_w, y0 + box_h), border_color, 2)

        # Header
        header = "Polishing..." if is_loading else "Polish Preview"
        cv2.putText(canvas, header, (x0 + pad, y0 + pad + 14),
                    _FONT, 0.55, border_color, 1)

        y = y0 + pad + line_h + 10

        # Original text (dim)
        cv2.putText(canvas, "Original:", (x0 + pad, y + 14), _FONT, 0.4, COLOR_DIM, 1)
        y += line_h
        cv2.putText(canvas, original[:80], (x0 + pad, y + 14), _FONT, 0.45, COLOR_DIM, 1)
        y += line_h + 6

        if is_loading:
            # Spinner dots
            cv2.putText(canvas, "AI is polishing your text...",
                        (x0 + pad, y + 14), _FONT, 0.45, border_color, 1)
        else:
            # Polished text (bright)
            cv2.putText(canvas, "Polished:", (x0 + pad, y + 14), _FONT, 0.4, (0, 220, 130), 1)
            y += line_h
            cv2.putText(canvas, polished[:80], (x0 + pad, y + 14),
                        _FONT, 0.5, (255, 255, 255), 1)
            y += line_h + 10

            # Instructions
            instructions = "Right wink = Submit  |  Left wink = Reject"
            cv2.putText(canvas, instructions, (x0 + pad, y + 14),
                        _FONT, 0.4, COLOR_FOCUS, 1)

    # ------------------------------------------------------------------
    # Diff preview
    # ------------------------------------------------------------------

    def _draw_diff_preview(self, canvas: np.ndarray, lines: List[str]) -> None:
        if not lines:
            return
        pad = 16
        line_h = _LINE_HEIGHT
        box_h = min(len(lines) * line_h + pad * 2, self._h - 100)
        box_w = min(self._w - 80, 800)
        x0 = (self._w - box_w) // 2
        y0 = (self._h - box_h) // 2

        overlay = canvas.copy()
        cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.9, canvas, 0.1, 0, canvas)
        cv2.rectangle(canvas, (x0, y0), (x0 + box_w, y0 + box_h), COLOR_GRID, 1)

        max_lines = (box_h - pad * 2) // line_h
        for i, line in enumerate(lines[:max_lines]):
            text_y = y0 + pad + (i + 1) * line_h - 4
            if line.startswith("+"):
                color = COLOR_DIFF_ADD
            elif line.startswith("-"):
                color = COLOR_DIFF_DEL
            elif line.startswith("@@"):
                color = COLOR_FOCUS
            else:
                color = COLOR_TEXT
            cv2.putText(canvas, line[:100], (x0 + pad, text_y), _FONT, 0.42, color, 1)
