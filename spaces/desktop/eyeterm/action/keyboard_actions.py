"""Fallback: pyautogui keyboard/mouse automation."""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class KeyboardActions:
    """Keyboard and mouse automation via pyautogui as fallback for UIA."""

    def click_at(self, x: int, y: int) -> dict:
        """Click at screen coordinates.

        Args:
            x: Screen X coordinate.
            y: Screen Y coordinate.

        Returns:
            dict with success and message keys.
        """
        try:
            import pyautogui
            pyautogui.click(x, y)
            return {"success": True, "message": f"Clicked at ({x}, {y})"}
        except ImportError:
            return {"success": False, "message": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            logger.error("click_at(%d, %d) failed: %s", x, y, e)
            return {"success": False, "message": f"Click failed: {e}"}

    def type_text(self, text: str) -> dict:
        """Type text via keyboard.

        Args:
            text: The text to type.

        Returns:
            dict with success and message keys.
        """
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
            return {"success": True, "message": f"Typed '{text[:50]}'"}
        except ImportError:
            return {"success": False, "message": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            logger.error("type_text failed: %s", e)
            return {"success": False, "message": f"Type failed: {e}"}

    def insert_text(self, text: str) -> dict:
        """Insert text at cursor via clipboard paste (handles Unicode).

        Uses clipboard instead of typewrite() because pyautogui.typewrite()
        cannot handle non-ASCII characters (ä, ö, ü, ß, etc.).
        Saves and restores the clipboard contents.
        """
        try:
            import pyautogui
            import subprocess
            import time as _time

            # Save current clipboard
            try:
                old_clip = subprocess.run(
                    ["powershell", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=2,
                ).stdout.rstrip("\r\n")
            except Exception:
                old_clip = ""

            # Copy text to clipboard via powershell (handles Unicode)
            subprocess.run(
                ["powershell", "-Command", f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'"],
                timeout=2,
            )

            # Paste
            pyautogui.hotkey("ctrl", "v")
            _time.sleep(0.15)

            # Restore clipboard
            if old_clip:
                try:
                    subprocess.run(
                        ["powershell", "-Command", f"Set-Clipboard -Value '{old_clip.replace(chr(39), chr(39)+chr(39))}'"],
                        timeout=2,
                    )
                except Exception:
                    pass

            return {"success": True, "message": f"Inserted '{text[:50]}'"}
        except ImportError:
            return {"success": False, "message": "pyautogui not installed"}
        except Exception as e:
            logger.error("insert_text failed: %s", e)
            return {"success": False, "message": f"Insert failed: {e}"}

    def press_key(self, key: str) -> dict:
        """Press a single key or combo like 'ctrl+c'.

        Args:
            key: Key name or combo string (e.g., "enter", "ctrl+c").

        Returns:
            dict with success and message keys.
        """
        try:
            import pyautogui
            if "+" in key:
                return self.hotkey(*key.split("+"))
            pyautogui.press(key)
            return {"success": True, "message": f"Pressed '{key}'"}
        except ImportError:
            return {"success": False, "message": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            logger.error("press_key('%s') failed: %s", key, e)
            return {"success": False, "message": f"Key press failed: {e}"}

    def hotkey(self, *keys: str) -> dict:
        """Press key combination.

        Args:
            *keys: Keys to press simultaneously (e.g., "ctrl", "c").

        Returns:
            dict with success and message keys.
        """
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            combo = "+".join(keys)
            return {"success": True, "message": f"Pressed hotkey '{combo}'"}
        except ImportError:
            return {"success": False, "message": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            combo = "+".join(keys)
            logger.error("hotkey('%s') failed: %s", combo, e)
            return {"success": False, "message": f"Hotkey failed: {e}"}
