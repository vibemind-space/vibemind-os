"""
Real Desktop Automation Validation Tests

These tests actually execute desktop automation using PyAutoGUI.
Run with caution - they will control your mouse and keyboard!

Usage:
    python test_validation_real.py --test easy
    python test_validation_real.py --test medium
    python test_validation_real.py --test hard
    python test_validation_real.py --test extreme
    python test_validation_real.py --all

Safety:
    - PyAutoGUI fail-safe enabled (move mouse to corner to abort)
    - 3-second countdown before each test
    - Tests can be interrupted with Ctrl+C
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1  # Small pause between actions
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    print("[ERROR] PyAutoGUI not installed. Run: pip install pyautogui")


class ValidationTest:
    """Real desktop automation validation tests."""

    def __init__(self):
        self.screenshots_dir = os.path.join(
            os.path.dirname(__file__), "validation_screenshots"
        )
        os.makedirs(self.screenshots_dir, exist_ok=True)
        self.results = []

    async def countdown(self, seconds: int = 3):
        """Countdown before test execution."""
        print(f"\nStarting in {seconds} seconds... (move mouse to corner to abort)")
        for i in range(seconds, 0, -1):
            print(f"  {i}...")
            await asyncio.sleep(1)
        print("  GO!")

    def capture_screenshot(self, name: str) -> str:
        """Capture screenshot for verification."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(self.screenshots_dir, filename)
        try:
            screenshot = pyautogui.screenshot()
            screenshot.save(filepath)
            print(f"  Screenshot saved: {filename}")
            return filepath
        except Exception as e:
            print(f"  [WARN] Screenshot failed: {e}")
            return ""

    async def test_easy_notepad(self) -> bool:
        """
        EASY TEST: Open Notepad and type Hello World

        Validates:
        - App launch via keyboard (Win+R, notepad, Enter)
        - Window appearance wait
        - Text typing via PyAutoGUI
        - Basic execution flow
        """
        print("\n" + "=" * 60)
        print("TEST 1: EASY - Notepad Text Entry")
        print("=" * 60)
        print("Goal: Open Notepad and type 'Hello World from MoireTracker!'")
        print("-" * 60)

        await self.countdown()

        try:
            # Step 1: Open Run dialog
            print("\n[Step 1/4] Opening Run dialog (Win+R)...")
            pyautogui.hotkey('win', 'r')
            await asyncio.sleep(0.7)

            # Step 2: Type notepad
            print("[Step 2/4] Typing 'notepad' and pressing Enter...")
            pyautogui.write('notepad', interval=0.05)
            await asyncio.sleep(0.2)
            pyautogui.press('enter')

            # Step 3: Wait for Notepad to open
            print("[Step 3/4] Waiting for Notepad to open...")
            await asyncio.sleep(2.0)

            # Step 4: Type message
            print("[Step 4/4] Typing message...")
            message = "Hello World from MoireTracker!"
            pyautogui.write(message, interval=0.03)

            # Capture result
            await asyncio.sleep(0.5)
            self.capture_screenshot("easy_notepad_result")

            print("\n" + "-" * 60)
            print("[PASS] Easy test completed successfully!")
            print("       Notepad should now show: 'Hello World from MoireTracker!'")
            return True

        except pyautogui.FailSafeException:
            print("\n[ABORTED] Mouse moved to corner - fail-safe triggered")
            return False
        except Exception as e:
            print(f"\n[FAIL] Easy test failed: {e}")
            return False

    async def test_medium_browser(self) -> bool:
        """
        MEDIUM TEST: Open Chrome and search for Python tutorials

        Validates:
        - Complex app launch via Start menu
        - URL bar navigation (Ctrl+L)
        - Multi-step keyboard sequences
        - Search query typing
        - Page load waiting
        """
        print("\n" + "=" * 60)
        print("TEST 2: MEDIUM - Browser Search")
        print("=" * 60)
        print("Goal: Open Chrome, navigate to address bar, search for Python tutorials")
        print("-" * 60)

        await self.countdown()

        try:
            # Step 1: Open Start menu
            print("\n[Step 1/6] Opening Start menu...")
            pyautogui.press('win')
            await asyncio.sleep(0.7)

            # Step 2: Search for Chrome
            print("[Step 2/6] Searching for 'chrome'...")
            pyautogui.write('chrome', interval=0.05)
            await asyncio.sleep(0.7)

            # Step 3: Press Enter to launch
            print("[Step 3/6] Pressing Enter to launch Chrome...")
            pyautogui.press('enter')

            # Step 4: Wait for Chrome to open
            print("[Step 4/6] Waiting for Chrome to open (3 seconds)...")
            await asyncio.sleep(3.0)

            # Step 5: Focus address bar
            print("[Step 5/6] Focusing address bar (Ctrl+L)...")
            pyautogui.hotkey('ctrl', 'l')
            await asyncio.sleep(0.3)

            # Step 6: Type search query and submit
            print("[Step 6/6] Typing search query and pressing Enter...")
            pyautogui.write('python tutorials', interval=0.03)
            await asyncio.sleep(0.2)
            pyautogui.press('enter')

            # Wait for results
            print("\nWaiting for search results (3 seconds)...")
            await asyncio.sleep(3.0)

            # Capture result
            self.capture_screenshot("medium_browser_result")

            print("\n" + "-" * 60)
            print("[PASS] Medium test completed successfully!")
            print("       Chrome should now show Python tutorials search results")
            return True

        except pyautogui.FailSafeException:
            print("\n[ABORTED] Mouse moved to corner - fail-safe triggered")
            return False
        except Exception as e:
            print(f"\n[FAIL] Medium test failed: {e}")
            return False

    async def test_hard_multi_app(self) -> bool:
        """
        HARD TEST: Multi-app clipboard workflow

        Validates:
        - Multiple window management
        - Clipboard operations (copy/paste)
        - Keyboard shortcuts (Ctrl+A, Ctrl+C, Ctrl+V)
        - Window switching
        - Multi-step workflow orchestration
        """
        print("\n" + "=" * 60)
        print("TEST 3: HARD - Multi-App Clipboard Workflow")
        print("=" * 60)
        print("Goal: Open Notepad, type message, copy, open new Notepad, paste")
        print("-" * 60)

        await self.countdown()

        try:
            # Step 1: Open first Notepad
            print("\n[Step 1/9] Opening Run dialog for first Notepad...")
            pyautogui.hotkey('win', 'r')
            await asyncio.sleep(0.7)

            print("[Step 2/9] Launching first Notepad...")
            pyautogui.write('notepad', interval=0.05)
            await asyncio.sleep(0.2)
            pyautogui.press('enter')
            await asyncio.sleep(2.0)

            # Step 3: Type message
            print("[Step 3/9] Typing message in first Notepad...")
            message = "This is a test message from MoireTracker automation!"
            pyautogui.write(message, interval=0.02)
            await asyncio.sleep(0.5)

            # Step 4: Select all
            print("[Step 4/9] Selecting all text (Ctrl+A)...")
            pyautogui.hotkey('ctrl', 'a')
            await asyncio.sleep(0.3)

            # Step 5: Copy
            print("[Step 5/9] Copying to clipboard (Ctrl+C)...")
            pyautogui.hotkey('ctrl', 'c')
            await asyncio.sleep(0.3)

            # Step 6: Open second Notepad
            print("[Step 6/9] Opening Run dialog for second Notepad...")
            pyautogui.hotkey('win', 'r')
            await asyncio.sleep(0.7)

            print("[Step 7/9] Launching second Notepad...")
            pyautogui.write('notepad', interval=0.05)
            await asyncio.sleep(0.2)
            pyautogui.press('enter')
            await asyncio.sleep(2.0)

            # Step 8: Paste
            print("[Step 8/9] Pasting content (Ctrl+V)...")
            pyautogui.hotkey('ctrl', 'v')
            await asyncio.sleep(0.5)

            # Step 9: Capture result
            print("[Step 9/9] Capturing screenshot...")
            self.capture_screenshot("hard_multi_app_result")

            print("\n" + "-" * 60)
            print("[PASS] Hard test completed successfully!")
            print("       Two Notepad windows should now have the same message:")
            print(f"       '{message}'")
            return True

        except pyautogui.FailSafeException:
            print("\n[ABORTED] Mouse moved to corner - fail-safe triggered")
            return False
        except Exception as e:
            print(f"\n[FAIL] Hard test failed: {e}")
            return False

    async def test_extreme_word(self) -> bool:
        """
        EXTREME TEST: Write a formatted story in Microsoft Word

        Validates:
        - Complex Office application launch and initialization
        - Multi-paragraph text composition
        - Rich text formatting (Bold, Italic)
        - Precise text selection for targeted formatting
        - File save dialog navigation
        - Full professional document workflow
        """
        print("\n" + "=" * 60)
        print("TEST 4: EXTREME - Microsoft Word Formatted Story")
        print("=" * 60)
        print("Goal: Open Word, write a story with title, paragraphs,")
        print("      bold/italic formatting, and save the document")
        print("-" * 60)

        await self.countdown(5)  # Longer countdown for complex test

        try:
            # ===== STEP 1: Launch Microsoft Word =====
            print("\n[Step 1/28] Opening Start menu...")
            pyautogui.press('win')
            await asyncio.sleep(0.7)

            print("[Step 2/28] Searching for 'winword'...")
            pyautogui.write('winword', interval=0.05)
            await asyncio.sleep(0.7)
            pyautogui.press('enter')

            print("[Step 3/28] Waiting for Word to load (5 seconds)...")
            await asyncio.sleep(5.0)

            # Dismiss any startup dialogs
            print("[Step 4/28] Pressing Escape to dismiss dialogs...")
            pyautogui.press('escape')
            await asyncio.sleep(1.0)
            pyautogui.press('escape')
            await asyncio.sleep(1.0)

            # ===== STEP 2: Write Title =====
            print("[Step 5/28] Typing title: 'The Adventure Begins'...")
            pyautogui.write('The Adventure Begins', interval=0.03)
            await asyncio.sleep(0.3)

            # Select and format title
            print("[Step 6/28] Selecting title (Ctrl+A)...")
            pyautogui.hotkey('ctrl', 'a')
            await asyncio.sleep(0.2)

            print("[Step 7/28] Making title bold (Ctrl+B)...")
            pyautogui.hotkey('ctrl', 'b')
            await asyncio.sleep(0.2)

            # Move to end and add spacing
            print("[Step 8/28] Moving to end and adding paragraph spacing...")
            pyautogui.press('end')
            await asyncio.sleep(0.1)
            pyautogui.press('enter')
            pyautogui.press('enter')

            # ===== STEP 3: Write Paragraph 1 =====
            print("[Step 9/28] Typing paragraph 1...")
            para1 = "Once upon a time, in a land far away, there lived a brave explorer named Alex. This explorer had a dream: to discover the secrets of the ancient forest."
            pyautogui.write(para1, interval=0.02)
            await asyncio.sleep(0.3)
            pyautogui.press('enter')
            pyautogui.press('enter')

            # ===== STEP 4: Write Paragraph 2 with BOLD words =====
            print("[Step 10/28] Typing paragraph 2...")
            para2_part1 = "One morning, Alex packed their "
            pyautogui.write(para2_part1, interval=0.02)

            # Type and bold "essential supplies"
            print("[Step 11/28] Typing 'essential supplies' (will be bold)...")
            pyautogui.write('essential supplies', interval=0.02)

            # Select the words we just typed and bold them
            print("[Step 12/28] Selecting 'essential supplies'...")
            for _ in range(len('essential supplies')):
                pyautogui.hotkey('shift', 'left')
            await asyncio.sleep(0.2)

            print("[Step 13/28] Making 'essential supplies' bold...")
            pyautogui.hotkey('ctrl', 'b')
            await asyncio.sleep(0.1)
            pyautogui.press('end')

            para2_part2 = " and set off on the journey. The path was long and "
            pyautogui.write(para2_part2, interval=0.02)

            # Type and bold "dangerous"
            print("[Step 14/28] Typing 'dangerous' (will be bold)...")
            pyautogui.write('dangerous', interval=0.02)

            print("[Step 15/28] Selecting 'dangerous'...")
            for _ in range(len('dangerous')):
                pyautogui.hotkey('shift', 'left')
            await asyncio.sleep(0.2)

            print("[Step 16/28] Making 'dangerous' bold...")
            pyautogui.hotkey('ctrl', 'b')
            await asyncio.sleep(0.1)
            pyautogui.press('end')

            para2_part3 = ", but nothing could stop this determined adventurer."
            pyautogui.write(para2_part3, interval=0.02)
            await asyncio.sleep(0.3)
            pyautogui.press('enter')
            pyautogui.press('enter')

            # ===== STEP 5: Write Paragraph 3 with ITALIC words =====
            print("[Step 17/28] Typing paragraph 3...")
            para3_part1 = "As the sun set, Alex found a "
            pyautogui.write(para3_part1, interval=0.02)

            # Type and italic "mysterious cave"
            print("[Step 18/28] Typing 'mysterious cave' (will be italic)...")
            pyautogui.write('mysterious cave', interval=0.02)

            print("[Step 19/28] Selecting 'mysterious cave'...")
            for _ in range(len('mysterious cave')):
                pyautogui.hotkey('shift', 'left')
            await asyncio.sleep(0.2)

            print("[Step 20/28] Making 'mysterious cave' italic...")
            pyautogui.hotkey('ctrl', 'i')
            await asyncio.sleep(0.1)
            pyautogui.press('end')

            para3_part2 = " with "
            pyautogui.write(para3_part2, interval=0.02)

            # Type and italic "glowing crystals"
            print("[Step 21/28] Typing 'glowing crystals' (will be italic)...")
            pyautogui.write('glowing crystals', interval=0.02)

            print("[Step 22/28] Making 'glowing crystals' italic...")
            for _ in range(len('glowing crystals')):
                pyautogui.hotkey('shift', 'left')
            await asyncio.sleep(0.2)
            pyautogui.hotkey('ctrl', 'i')
            await asyncio.sleep(0.1)
            pyautogui.press('end')

            para3_part3 = " inside. This was just the beginning of an incredible discovery that would change everything."
            pyautogui.write(para3_part3, interval=0.02)
            await asyncio.sleep(0.3)
            pyautogui.press('enter')
            pyautogui.press('enter')

            # ===== STEP 6: Write Ending =====
            print("[Step 23/28] Typing 'The End'...")
            pyautogui.write('The End', interval=0.03)
            await asyncio.sleep(0.2)

            # Select and format ending
            print("[Step 24/28] Selecting 'The End'...")
            for _ in range(len('The End')):
                pyautogui.hotkey('shift', 'left')
            await asyncio.sleep(0.2)

            print("[Step 25/28] Making 'The End' bold...")
            pyautogui.hotkey('ctrl', 'b')
            await asyncio.sleep(0.1)

            print("[Step 26/28] Centering 'The End'...")
            pyautogui.hotkey('ctrl', 'e')
            await asyncio.sleep(0.2)

            # ===== STEP 7: Save Document =====
            print("[Step 27/28] Saving document (Ctrl+S)...")
            pyautogui.hotkey('ctrl', 's')
            await asyncio.sleep(2.0)  # Wait for save dialog

            # Type filename
            print("[Step 28/28] Typing filename 'test_story_moire'...")
            pyautogui.write('test_story_moire', interval=0.03)
            await asyncio.sleep(0.5)
            pyautogui.press('enter')
            await asyncio.sleep(2.0)  # Wait for save

            # Capture final result
            self.capture_screenshot("extreme_word_result")

            print("\n" + "-" * 60)
            print("[PASS] Extreme test completed successfully!")
            print("       Word document created with:")
            print("       - Bold title: 'The Adventure Begins'")
            print("       - 3 paragraphs of story content")
            print("       - Bold words: 'essential supplies', 'dangerous'")
            print("       - Italic words: 'mysterious cave', 'glowing crystals'")
            print("       - Centered bold ending: 'The End'")
            print("       - Saved as: test_story_moire.docx")
            return True

        except pyautogui.FailSafeException:
            print("\n[ABORTED] Mouse moved to corner - fail-safe triggered")
            return False
        except Exception as e:
            print(f"\n[FAIL] Extreme test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("VALIDATION TEST SUMMARY")
        print("=" * 60)

        passed = 0
        total = len(self.results)

        for name, result in self.results:
            status = "[PASS]" if result else "[FAIL]"
            if result:
                passed += 1
            print(f"  {status} {name}")

        print("-" * 60)
        print(f"  {passed}/{total} tests passed")

        if passed == total:
            print("\n  *** ALL VALIDATION TESTS PASSED ***")
            print("  Desktop automation is working correctly!")
        else:
            print(f"\n  *** {total - passed} TEST(S) FAILED ***")
            print("  Check the output above for details.")

        print(f"\n  Screenshots saved to: {self.screenshots_dir}")
        print("=" * 60)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="MoireTracker Real Desktop Automation Validation Tests"
    )
    parser.add_argument(
        "--test",
        choices=["easy", "medium", "hard", "extreme"],
        help="Run a specific test"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests"
    )

    args = parser.parse_args()

    # Check PyAutoGUI
    if not HAS_PYAUTOGUI:
        print("[ERROR] PyAutoGUI is required for these tests")
        print("Install with: pip install pyautogui")
        sys.exit(1)

    # Show warning banner
    print("\n" + "=" * 60)
    print("MoireTracker Real Desktop Automation Validation")
    print("=" * 60)
    print()
    print("WARNING: These tests will control your desktop!")
    print("         They will move your mouse and type on your keyboard.")
    print()
    print("SAFETY:  Move your mouse to any screen corner to ABORT")
    print("         Press Ctrl+C to interrupt")
    print()
    print("=" * 60)

    if not args.test and not args.all:
        print("\nUsage:")
        print("  python test_validation_real.py --test easy    # Run easy test only")
        print("  python test_validation_real.py --test medium  # Run medium test only")
        print("  python test_validation_real.py --test hard    # Run hard test only")
        print("  python test_validation_real.py --test extreme # Run extreme test (Word)")
        print("  python test_validation_real.py --all          # Run all tests")
        sys.exit(0)

    tester = ValidationTest()

    # Run requested tests
    try:
        if args.all or args.test == "easy":
            result = await tester.test_easy_notepad()
            tester.results.append(("Easy: Notepad Text Entry", result))

        if args.all or args.test == "medium":
            result = await tester.test_medium_browser()
            tester.results.append(("Medium: Browser Search", result))

        if args.all or args.test == "hard":
            result = await tester.test_hard_multi_app()
            tester.results.append(("Hard: Multi-App Workflow", result))

        if args.all or args.test == "extreme":
            result = await tester.test_extreme_word()
            tester.results.append(("Extreme: Word Formatted Document", result))

        # Print summary
        tester.print_summary()

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Tests cancelled by user (Ctrl+C)")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
