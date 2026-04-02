"""Launch and manage real terminal windows running Claude Code."""

import ctypes
import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional

import pyautogui

logger = logging.getLogger("eyeterm.launcher")

# Windows API constants
SW_SHOW = 5
SW_RESTORE = 9


@dataclass
class TerminalPane:
    """A terminal window running Claude Code."""
    index: int
    workdir: str
    session_name: str
    process: Optional[subprocess.Popen] = None
    hwnd: Optional[int] = None  # Windows window handle


class TerminalLauncher:
    """Launch and position terminal windows in a grid layout."""

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self._sw = screen_width
        self._sh = screen_height
        self._panes: List[TerminalPane] = []

    @property
    def panes(self) -> List[TerminalPane]:
        return self._panes

    def launch(self, workdirs: List[str]) -> List[TerminalPane]:
        """Launch terminal windows in a 2x2 grid.

        Each terminal runs: claude --resume pane-N
        """
        n = len(workdirs)
        if n == 0:
            return []

        # Calculate grid positions
        cols = 2 if n > 1 else 1
        rows = (n + 1) // 2

        cell_w = self._sw // cols
        cell_h = self._sh // rows

        for idx, workdir in enumerate(workdirs):
            col = idx % cols
            row = idx // cols
            x = col * cell_w
            y = row * cell_h

            session_name = f"pane-{idx}"
            pane = TerminalPane(
                index=idx,
                workdir=workdir,
                session_name=session_name,
            )

            try:
                # Launch Windows Terminal or cmd with Claude Code
                cmd = f'start "Claude {idx}" /D "{workdir}" cmd /k "claude --resume {session_name}"'
                proc = subprocess.Popen(
                    cmd,
                    shell=True,
                    cwd=workdir,
                )
                pane.process = proc
                logger.info("Launched terminal %d in %s", idx, workdir)
            except Exception as e:
                logger.error("Failed to launch terminal %d: %s", idx, e)

            self._panes.append(pane)

        # Give terminals time to open, then position them
        time.sleep(2.0)
        self._position_windows(cell_w, cell_h, cols)

        return self._panes

    def _position_windows(self, cell_w: int, cell_h: int, cols: int) -> None:
        """Find and position the launched terminal windows."""
        try:
            import win32gui
            import win32con

            def enum_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    for pane in self._panes:
                        if f"Claude {pane.index}" in title and pane.hwnd is None:
                            pane.hwnd = hwnd
                            results.append((pane.index, hwnd))

            results = []
            win32gui.EnumWindows(enum_callback, results)

            for pane in self._panes:
                if pane.hwnd:
                    col = pane.index % cols
                    row = pane.index // cols
                    x = col * cell_w
                    y = row * cell_h
                    win32gui.MoveWindow(pane.hwnd, x, y, cell_w, cell_h, True)
                    logger.info("Positioned terminal %d at (%d,%d) %dx%d",
                                pane.index, x, y, cell_w, cell_h)

        except ImportError:
            logger.warning("win32gui not available — terminals won't be auto-positioned")

    def focus_pane(self, pane_idx: int) -> bool:
        """Bring the terminal window for the given pane to the foreground."""
        if pane_idx >= len(self._panes):
            return False

        pane = self._panes[pane_idx]
        if pane.hwnd is None:
            return False

        try:
            import win32gui
            import win32con
            # Restore if minimized, then bring to front
            win32gui.ShowWindow(pane.hwnd, SW_RESTORE)
            win32gui.SetForegroundWindow(pane.hwnd)
            return True
        except ImportError:
            # Fallback: try ctypes
            try:
                user32 = ctypes.windll.user32
                user32.ShowWindow(pane.hwnd, SW_RESTORE)
                user32.SetForegroundWindow(pane.hwnd)
                return True
            except Exception:
                return False
        except Exception as e:
            logger.warning("Failed to focus pane %d: %s", pane_idx, e)
            return False

    def send_text(self, pane_idx: int, text: str) -> bool:
        """Type text into the focused terminal and press Enter."""
        if not self.focus_pane(pane_idx):
            return False

        time.sleep(0.1)  # Wait for window focus
        try:
            pyautogui.typewrite(text, interval=0.02)
            pyautogui.press('enter')
            logger.info("Sent text to pane %d: %s", pane_idx, text[:50])
            return True
        except Exception as e:
            logger.error("Failed to send text to pane %d: %s", pane_idx, e)
            return False

    def send_escape(self, pane_idx: int) -> bool:
        """Send double Escape to the focused terminal (cancel in Claude Code)."""
        if not self.focus_pane(pane_idx):
            return False

        time.sleep(0.05)
        try:
            pyautogui.press('escape')
            time.sleep(0.05)
            pyautogui.press('escape')
            logger.info("Sent Esc Esc to pane %d", pane_idx)
            return True
        except Exception as e:
            logger.error("Failed to send escape to pane %d: %s", pane_idx, e)
            return False

    def close_all(self) -> None:
        """Close all terminal windows."""
        for pane in self._panes:
            if pane.process:
                try:
                    pane.process.terminate()
                except Exception:
                    pass
        self._panes.clear()
