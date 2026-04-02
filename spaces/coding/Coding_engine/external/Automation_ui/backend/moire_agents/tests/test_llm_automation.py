"""
LLM-Powered Desktop Automation Test

This script demonstrates true AI-powered desktop automation where:
1. User provides a natural language goal
2. Claude AI generates the execution plan dynamically
3. PyAutoGUI executes the AI-generated plan

Usage:
    python test_llm_automation.py "Open Notepad and type Hello World"
    python test_llm_automation.py "Open Word and write a story with bold formatting"
    python test_llm_automation.py "Open Chrome and search for Python tutorials"
    python test_llm_automation.py --dry-run "Open Notepad"  # Preview without execution

Safety:
    - PyAutoGUI fail-safe enabled (move mouse to corner to abort)
    - 3-second countdown before execution
    - Use --dry-run to preview the plan without executing

Requirements:
    - anthropic package installed (pip install anthropic)
    - ANTHROPIC_API_KEY in environment or .env file
    - pyautogui package installed
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.task_decomposer import TaskDecomposer
from core.action_executor import ActionExecutor

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="LLM-Powered Desktop Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python test_llm_automation.py "Open Notepad and type Hello World"
    python test_llm_automation.py "Open Chrome and search for Python tutorials"
    python test_llm_automation.py "Open Word, write a poem, make title bold"
    python test_llm_automation.py --dry-run "Open Calculator"
        """
    )
    parser.add_argument(
        "goal",
        nargs="?",
        default="Open Notepad and type Hello World from AI",
        help="Natural language description of the task to perform"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the plan without executing (no desktop actions)"
    )
    parser.add_argument(
        "--no-countdown",
        action="store_true",
        help="Skip the 3-second countdown before execution"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "=" * 70)
    print("  LLM-Powered Desktop Automation")
    print("  AI dynamically generates execution plans from natural language")
    print("=" * 70)

    print(f"\n[GOAL] {args.goal}")

    if args.dry_run:
        print("\n[DRY RUN] No actions will be executed")

    # Initialize components
    print("\n[AI] Asking Claude AI to generate execution plan...")
    decomposer = TaskDecomposer()
    executor = ActionExecutor(dry_run=args.dry_run)

    try:
        # Get LLM-generated plan
        subtasks = await decomposer.decompose_with_actions(args.goal)

        if not subtasks:
            print("\n[ERROR] Could not generate execution plan")
            return 1

        # Display the generated plan
        print(f"\n[OK] Generated {len(subtasks)} steps:")
        print("-" * 50)

        for i, st in enumerate(subtasks):
            action = st.context.get("pyautogui_action", {})
            action_str = _format_action(action) if action else "No action"
            wait = st.context.get("wait_after", 0)

            print(f"\n  Step {i+1}: {st.description}")
            print(f"    -> Action: {action_str}")
            if wait > 0:
                print(f"    -> Wait: {wait}s")

        print("\n" + "-" * 50)

        if args.dry_run:
            print("\n[OK] Dry run complete - plan generated but not executed")
            return 0

        # Countdown before execution
        if not args.no_countdown:
            print("\n[WARNING] Executing in 3 seconds... (move mouse to corner to abort)")
            for i in range(3, 0, -1):
                print(f"  {i}...")
                await asyncio.sleep(1)

        # Execute the plan
        print("\n[EXEC] Executing...")
        print("-" * 50)

        def on_progress(index, total, description):
            progress = (index + 1) / total * 100
            logger.debug(f"Progress: {progress:.0f}% - {description}")

        success = await executor.execute_subtasks(subtasks, on_progress=on_progress)

        print("-" * 50)

        if success:
            print("\n[SUCCESS] All steps executed!")
        else:
            print("\n[FAILED] Some steps could not be executed")
            return 1

        return 0

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] User cancelled")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        logger.exception("Execution failed")
        return 1


def _format_action(action: dict) -> str:
    """Format an action dictionary as a readable string."""
    action_type = action.get("type", "unknown")

    if action_type == "hotkey":
        keys = action.get("keys", [])
        return f"hotkey({'+'.join(keys)})"
    elif action_type == "write":
        text = action.get("text", "")
        if len(text) > 30:
            text = text[:30] + "..."
        return f'write("{text}")'
    elif action_type == "press":
        key = action.get("key", "?")
        return f"press({key})"
    elif action_type == "click":
        x = action.get("x", "?")
        y = action.get("y", "?")
        return f"click({x}, {y})"
    elif action_type == "sleep":
        seconds = action.get("seconds", 0)
        return f"sleep({seconds}s)"
    elif action_type == "select_text":
        chars = action.get("chars", 0)
        direction = action.get("direction", "left")
        return f"select_text({chars} chars {direction})"
    else:
        return str(action)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
