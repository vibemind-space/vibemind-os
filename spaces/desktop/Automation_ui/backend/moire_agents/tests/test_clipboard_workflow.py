"""
Clipboard Test - Test Claude Desktop with clipboard paste
(pyautogui.write() may not work with some Electron apps)
"""

import asyncio
import pyautogui
import pyperclip

# Safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


async def test_clipboard():
    """Test using clipboard paste instead of pyautogui.write()."""
    print("\n" + "=" * 60)
    print("CLIPBOARD Claude Desktop Test")
    print("=" * 60)

    task = (
        "Generate a simple Hello World message. "
        "Just respond with a greeting."
    )

    print(f"\nTask: {task}")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    # Step 1: Open Claude Desktop with Ctrl+Alt+Space
    print("\n[1/6] Opening Claude Desktop (Ctrl+Alt+Space)...")
    pyautogui.hotkey("ctrl", "alt", "space")

    # Step 2: Wait for window to open
    print("[2/6] Waiting 2 seconds for window...")
    await asyncio.sleep(2)

    # Step 3: Click on the center-bottom of screen (typical chat input location)
    screen_width, screen_height = pyautogui.size()
    x = screen_width // 2
    y = int(screen_height * 0.85)
    print(f"[3/6] Clicking at ({x}, {y}) for chat input...")
    pyautogui.click(x, y)

    # Step 4: Wait for focus
    print("[4/6] Waiting 0.5 seconds for focus...")
    await asyncio.sleep(0.5)

    # Step 5: Copy task to clipboard and paste
    print(f"[5/6] Pasting task via clipboard ({len(task)} chars)...")
    pyperclip.copy(task)
    pyautogui.hotkey("ctrl", "v")

    # Step 6: Press Enter
    print("[6/6] Pressing Enter to send...")
    await asyncio.sleep(0.3)
    pyautogui.press("enter")

    print("\n" + "=" * 60)
    print("CLIPBOARD TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_clipboard())
