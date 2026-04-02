"""
Steering Agent Automation Test

Tests the SteeringAgent with:
1. Action categorization (SAFE vs VISUAL_DEPENDENT)
2. Visual validation with bounding box detection
3. Change region feedback
4. Recovery on failure

Usage:
    python test_steering_automation.py "Open Notepad and type Hello World"
    python test_steering_automation.py --dry-run "Open Chrome"
    python test_steering_automation.py --no-validation "Open Notepad"

Requirements:
    - MoireServer running at ws://localhost:8765 (for visual validation)
    - ANTHROPIC_API_KEY in environment or .env file
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.task_decomposer import TaskDecomposer
from agents.steering_agent import SteeringAgent, ActionCategory

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print the application banner."""
    print("\n" + "=" * 70)
    print("  Steering Agent Automation")
    print("  Visual Validation + Action Categorization + Recovery Handling")
    print("=" * 70)


def format_action(action: dict) -> str:
    """Format an action dictionary as a readable string."""
    if not action:
        return "No action"

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
    elif action_type == "find_and_click":
        target = action.get("target", "?")
        return f'find_and_click("{target}")'
    else:
        return str(action)


def format_category(action: dict) -> str:
    """Format the action category."""
    if not action:
        return "NONE"

    action_type = action.get("type", "")

    if action_type in SteeringAgent.SAFE_ACTIONS:
        return "SAFE"
    elif action_type in SteeringAgent.FIND_ACTIONS:
        return "FIND"
    elif action_type in SteeringAgent.VISUAL_ACTIONS:
        return "VISUAL"
    elif action_type in SteeringAgent.WAIT_ACTIONS:
        return "WAIT"
    else:
        return "UNKNOWN"


async def main():
    parser = argparse.ArgumentParser(
        description="Steering Agent Automation with Visual Validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python test_steering_automation.py "Open Notepad and type Hello World"
    python test_steering_automation.py "Open Chrome and search for Python"
    python test_steering_automation.py --dry-run "Open Calculator"
    python test_steering_automation.py --no-validation "Open Notepad"
        """
    )
    parser.add_argument(
        "goal",
        nargs="?",
        default="Open Notepad and type Hello from Steering Agent",
        help="Natural language description of the task"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the plan without executing"
    )
    parser.add_argument(
        "--no-validation",
        action="store_true",
        help="Execute without visual validation"
    )
    parser.add_argument(
        "--no-countdown",
        action="store_true",
        help="Skip the 3-second countdown"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print_banner()

    print(f"\n[GOAL] {args.goal}")

    if args.dry_run:
        print("\n[DRY RUN] No actions will be executed")

    # Initialize TaskDecomposer
    print("\n[AI] Generating execution plan with Claude...")
    decomposer = TaskDecomposer()

    try:
        # Get LLM-generated plan
        subtasks = await decomposer.decompose_with_actions(args.goal)

        if not subtasks:
            print("\n[ERROR] Could not generate execution plan")
            return 1

        # Display the generated plan with categories
        print(f"\n[OK] Generated {len(subtasks)} steps:")
        print("-" * 60)

        for i, st in enumerate(subtasks):
            action = st.context.get("pyautogui_action", {})
            action_str = format_action(action)
            category = format_category(action)
            wait = st.context.get("wait_after", 0)

            print(f"\n  Step {i+1}: {st.description}")
            print(f"    -> Action: {action_str}")
            print(f"    -> Category: {category}")
            if wait > 0:
                print(f"    -> Wait: {wait}s")

        print("\n" + "-" * 60)

        if args.dry_run:
            print("\n[OK] Dry run complete - plan generated but not executed")

            # Show category summary
            safe_count = sum(1 for st in subtasks
                           if format_category(st.context.get("pyautogui_action", {})) == "SAFE")
            find_count = sum(1 for st in subtasks
                           if format_category(st.context.get("pyautogui_action", {})) == "FIND")
            visual_count = sum(1 for st in subtasks
                             if format_category(st.context.get("pyautogui_action", {})) == "VISUAL")

            print(f"\n[SUMMARY]")
            print(f"  Safe actions (no validation): {safe_count}")
            print(f"  Find actions (OCR/vision search): {find_count}")
            print(f"  Visual actions (with validation): {visual_count}")
            return 0

        # Countdown
        if not args.no_countdown:
            print("\n[WARNING] Executing in 3 seconds... (move mouse to corner to abort)")
            for i in range(3, 0, -1):
                print(f"  {i}...")
                await asyncio.sleep(1)

        # Initialize SteeringAgent
        agent = SteeringAgent()

        try:
            # Connect to MoireServer (if validation enabled)
            if not args.no_validation:
                print("\n[MOIRE] Connecting to MoireServer...")
                connected = await agent.connect()
                if connected:
                    print("[OK] Connected - visual validation enabled")
                else:
                    print("[WARNING] Could not connect - running without visual validation")
            else:
                print("\n[SKIP] Visual validation disabled")

            # Execute with steering
            print("\n[EXEC] Starting execution with steering...")
            print("=" * 60)

            def on_progress(step, total, message, regions):
                # Progress is handled in steering agent
                pass

            result = await agent.execute_with_steering(
                subtasks=subtasks,
                goal=args.goal,
                on_progress=on_progress
            )

            print("=" * 60)

            # Show results
            print(f"\n[RESULT]")
            print(f"  Success: {result.success}")
            print(f"  Goal achieved: {result.goal_achieved}")
            print(f"  Actions executed: {result.actions_executed}/{len(subtasks)}")
            print(f"  Actions validated: {result.actions_validated}")
            print(f"  Actions failed: {result.actions_failed}")
            print(f"  Recovery attempts: {result.recovery_attempts}")
            print(f"  Duration: {result.total_time_seconds:.1f}s")

            if result.change_regions:
                print(f"\n[CHANGE REGIONS] Detected {len(result.change_regions)} regions:")
                for region in result.change_regions[:5]:  # Show first 5
                    bounds = region.get("bounds", {})
                    intensity = region.get("intensity", "?")
                    print(f"    Region {region.get('id')}: ({bounds.get('x')}, {bounds.get('y')}) "
                          f"{bounds.get('width')}x{bounds.get('height')} - {intensity}")
                if len(result.change_regions) > 5:
                    print(f"    ... and {len(result.change_regions) - 5} more")

            print(f"\n[SUMMARY] {result.summary}")

            # Final status
            if result.success and result.goal_achieved:
                print("\n[SUCCESS]")
                return 0
            elif result.success:
                print("\n[PARTIAL SUCCESS] Actions executed but goal may not be achieved")
                return 0
            else:
                print("\n[FAILED]")
                return 1

        finally:
            await agent.disconnect()

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] User cancelled")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        logger.exception("Execution failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
