"""
Notepad Test - Verify pyautogui is working correctly
"""

import asyncio
import pyautogui

# Safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


async def test_notepad():
    """Open Notepad and type text to verify pyautogui works."""
    print("\n" + "=" * 60)
    print("NOTEPAD Test - Verify pyautogui")
    print("=" * 60)

    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    # Open Run dialog
    print("\n[1/4] Opening Run dialog (Win+R)...")
    pyautogui.hotkey("win", "r")
    await asyncio.sleep(0.5)

    # Type notepad
    print("[2/4] Typing 'notepad'...")
    pyautogui.write("notepad", interval=0.05)
    await asyncio.sleep(0.3)

    # Press Enter
    print("[3/4] Pressing Enter...")
    pyautogui.press("enter")
    await asyncio.sleep(2)

    # Type test message
    print("[4/4] Typing test message...")
    pyautogui.write("Hello from pyautogui! If you see this, it works!", interval=0.02)

    print("\n" + "=" * 60)
    print("NOTEPAD TEST COMPLETE")
    print("Check if text appeared in Notepad!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_notepad())
