"""
Keyboard-Only Test - Focus input using Tab key navigation
"""

import asyncio
import pyautogui
import pyperclip

# Safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


async def test_keyboard_only():
    """Test using keyboard navigation only (no mouse clicks)."""
    print("\n" + "=" * 60)
    print("KEYBOARD-ONLY Claude Desktop Test")
    print("=" * 60)

    task = "Hello Claude! This is a test message."

    print(f"\nTask: {task}")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    # Step 1: Open Claude Desktop with Ctrl+Alt+Space
    print("\n[1/5] Opening Claude Desktop (Ctrl+Alt+Space)...")
    pyautogui.hotkey("ctrl", "alt", "space")

    # Step 2: Wait for window to open
    print("[2/5] Waiting 3 seconds for window...")
    await asyncio.sleep(3)

    # Step 3: Input field should already have focus in Claude Desktop
    # But let's try Tab to ensure we're in the input
    print("[3/5] Pressing Tab to ensure input focus...")
    pyautogui.press("tab")
    await asyncio.sleep(0.3)

    # Step 4: Copy task to clipboard and paste
    print(f"[4/5] Pasting task via Ctrl+V ({len(task)} chars)...")
    pyperclip.copy(task)
    pyautogui.hotkey("ctrl", "v")
    await asyncio.sleep(0.5)

    # Step 5: Press Enter
    print("[5/5] Pressing Enter to send...")
    pyautogui.press("enter")

    print("\n" + "=" * 60)
    print("KEYBOARD-ONLY TEST COMPLETE")
    print("Check if the message appeared in Claude Desktop!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_keyboard_only())
