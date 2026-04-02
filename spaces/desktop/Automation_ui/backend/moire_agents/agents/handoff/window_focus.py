"""
Window Focus Utilities for Handoff MCP

Provides functions to check and verify which window is currently active,
helping prevent keystrokes from going to the wrong application.

Uses Windows API via ctypes (no additional dependencies).
"""

import ctypes
import asyncio
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Windows API
user32 = ctypes.windll.user32


async def get_active_window() -> Dict[str, Any]:
    """
    Get the currently active/focused window information.

    Returns:
        Dict with:
        - success: bool
        - hwnd: window handle (int)
        - title: window title (str)
        - pid: process ID (int)
    """
    try:
        hwnd = user32.GetForegroundWindow()

        if not hwnd:
            return {
                "success": False,
                "hwnd": None,
                "title": None,
                "pid": None,
                "error": "No foreground window found"
            }

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value

        # Get process ID
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        return {
            "success": True,
            "hwnd": hwnd,
            "title": title,
            "pid": pid.value
        }

    except Exception as e:
        logger.error(f"Error getting active window: {e}")
        return {
            "success": False,
            "hwnd": None,
            "title": None,
            "pid": None,
            "error": str(e)
        }


def find_window_by_title(target_title: str, exact: bool = False) -> Optional[int]:
    """
    Find a window handle by its title.

    Args:
        target_title: Window title to search for
        exact: If True, require exact match. If False, partial match.

    Returns:
        Window handle (hwnd) if found, None otherwise
    """
    found_hwnd = [None]
    target_lower = target_title.lower()

    def enum_callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value

                if exact:
                    if title == target_title:
                        found_hwnd[0] = hwnd
                        return False  # Stop enumeration
                else:
                    if target_lower in title.lower():
                        found_hwnd[0] = hwnd
                        return False  # Stop enumeration
        return True

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

    return found_hwnd[0]


def list_visible_windows() -> List[Dict[str, Any]]:
    """
    List all visible windows with titles.

    Returns:
        List of dicts with hwnd and title for each visible window
    """
    windows = []

    def enum_callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value
                if title.strip():  # Skip empty titles
                    windows.append({
                        "hwnd": hwnd,
                        "title": title
                    })
        return True

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

    return windows


async def focus_window(hwnd: int) -> bool:
    """
    Attempt to bring a window to the foreground.

    Args:
        hwnd: Window handle to focus

    Returns:
        True if successful, False otherwise
    """
    try:
        # Show window if minimized
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)

        # Bring to foreground
        result = user32.SetForegroundWindow(hwnd)

        # Small delay to let the focus change complete
        await asyncio.sleep(0.1)

        return bool(result)
    except Exception as e:
        logger.error(f"Error focusing window: {e}")
        return False


async def verify_window_focus(
    target_title: str,
    timeout: float = 3.0,
    auto_focus: bool = True
) -> Dict[str, Any]:
    """
    Verify that the target window is focused, optionally trying to focus it.

    Args:
        target_title: Partial or full window title to match
        timeout: How long to wait/retry (seconds)
        auto_focus: If True, attempt to focus the window if not already focused

    Returns:
        Dict with:
        - success: bool - True if window is now focused
        - is_focused: bool - True if window was already focused
        - recovered: bool - True if we had to focus the window
        - hwnd: window handle
        - title: actual window title
        - error: error message if failed
    """
    start_time = asyncio.get_event_loop().time()
    target_lower = target_title.lower()

    while asyncio.get_event_loop().time() - start_time < timeout:
        active = await get_active_window()

        if active["success"] and active["title"]:
            if target_lower in active["title"].lower():
                return {
                    "success": True,
                    "is_focused": True,
                    "recovered": False,
                    "hwnd": active["hwnd"],
                    "title": active["title"]
                }

        # If auto_focus is enabled and we haven't found the window focused, try to focus it
        if auto_focus:
            hwnd = find_window_by_title(target_title)
            if hwnd:
                logger.info(f"Window '{target_title}' not focused, attempting to focus...")
                focused = await focus_window(hwnd)

                if focused:
                    # Wait a bit and check again
                    await asyncio.sleep(0.2)
                    active = await get_active_window()

                    if active["success"] and active["title"]:
                        if target_lower in active["title"].lower():
                            return {
                                "success": True,
                                "is_focused": True,
                                "recovered": True,  # We had to focus it
                                "hwnd": active["hwnd"],
                                "title": active["title"]
                            }

        # Wait before next check
        await asyncio.sleep(0.2)

    # Timeout - could not verify focus
    return {
        "success": False,
        "is_focused": False,
        "recovered": False,
        "hwnd": None,
        "title": None,
        "error": f"Could not verify focus on window '{target_title}' within {timeout}s"
    }
