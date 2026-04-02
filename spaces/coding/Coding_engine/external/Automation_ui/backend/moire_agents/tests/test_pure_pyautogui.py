"""
Pure PyAutoGUI Test - No MoireServer, No Detection
Tests the basic workflow using only pyautogui and pyperclip
"""

import asyncio
import pyautogui
import pyperclip
import time

# Safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


async def send_to_claude_desktop(task: str):
    """Send a task to Claude Desktop using pure pyautogui."""

    print("\n" + "=" * 60)
    print("PURE PyAutoGUI Claude Desktop Test")
    print("=" * 60)

    print(f"\nTask: {task[:80]}...")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    # Step 1: Open Claude Desktop with Ctrl+Alt+Space
    print("\n[1/6] Opening Claude Desktop (Ctrl+Alt+Space)...")
    pyautogui.hotkey("ctrl", "alt", "space")

    # Step 2: Wait for window to open
    print("[2/6] Waiting 2 seconds for window...")
    await asyncio.sleep(2)

    # Step 3: Click at center-bottom for chat input
    screen_width, screen_height = pyautogui.size()
    x = screen_width // 2
    y = int(screen_height * 0.85)
    print(f"[3/6] Clicking at ({x}, {y}) for chat input...")
    pyautogui.click(x, y)

    # Step 4: Wait for focus
    print("[4/6] Waiting 0.5s for focus...")
    await asyncio.sleep(0.5)

    # Step 5: Paste task using clipboard (more reliable than write)
    print(f"[5/6] Pasting task via clipboard ({len(task)} chars)...")
    pyperclip.copy(task)
    pyautogui.hotkey("ctrl", "v")
    await asyncio.sleep(0.3)

    # Step 6: Press Enter to send
    print("[6/6] Pressing Enter to send...")
    pyautogui.press("enter")

    print("\n" + "=" * 60)
    print("COMPLETE!")
    print("Check if the message appeared in Claude Desktop")
    print("=" * 60)


async def main():
    task = (
        "Generate a comprehensive debug report about Docker containers. "
        "Include: container status, running containers, recent logs, "
        "resource usage (CPU/memory), and any errors or warnings. "
        "Format the report as a Word document (.docx)."
    )

    await send_to_claude_desktop(task)


if __name__ == "__main__":
    asyncio.run(main())
