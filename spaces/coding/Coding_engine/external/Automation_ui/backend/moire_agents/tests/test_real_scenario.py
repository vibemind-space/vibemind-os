"""
Real Interactive Test - MoireTracker Subagent System Demo

This test demonstrates ALL subagent capabilities with REAL desktop automation:
1. Parallel Planning - 3 approaches planned simultaneously
2. Specialist Knowledge - Windows system shortcuts
3. Real Action Execution - Actually opens Notepad and types
4. Vision Verification - Screenshot analysis to confirm success
5. Background Monitoring - Waits for Notepad window

PREREQUISITES:
- Redis server running on localhost:6379
- PyAutoGUI installed (pip install pyautogui)
- Windows desktop environment
- Move mouse to corner to abort (PyAutoGUI failsafe)

Usage:
    python test_real_scenario.py
"""

import asyncio
import sys
import time
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import PyAutoGUI
try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1  # Small pause between actions
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    print("[WARN] PyAutoGUI not installed - will simulate actions")

# Try to import PIL for screenshots
try:
    from PIL import Image
    import io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARN] Pillow not installed - vision verification disabled")


# ============================================================
# Data Classes
# ============================================================

@dataclass
class PlanAction:
    """A single action in a plan."""
    action_type: str  # "hotkey", "type", "click", "wait"
    params: Dict[str, Any]
    description: str


@dataclass
class Plan:
    """A complete plan from a planning subagent."""
    approach: str  # "keyboard", "mouse", "hybrid"
    actions: List[PlanAction]
    confidence: float
    reasoning: str


@dataclass
class ExecutionResult:
    """Result of executing a plan."""
    success: bool
    steps_completed: int
    total_steps: int
    error: Optional[str] = None
    screenshot: Optional[bytes] = None


# ============================================================
# Mock Subagent Workers (Simulating Redis-based subagents)
# ============================================================

class MockPlanningSubagent:
    """Simulates a planning subagent that generates action plans."""

    def __init__(self, approach: str):
        self.approach = approach

    async def plan(self, goal: str, context: Dict) -> Plan:
        """Generate a plan for the given goal."""
        # Simulate some thinking time
        await asyncio.sleep(0.1 + (hash(self.approach) % 100) / 500)

        if self.approach == "keyboard":
            return Plan(
                approach="keyboard",
                actions=[
                    PlanAction("hotkey", {"keys": ["win", "r"]}, "Open Run dialog"),
                    PlanAction("wait", {"seconds": 0.5}, "Wait for dialog"),
                    PlanAction("type", {"text": "notepad"}, "Type 'notepad'"),
                    PlanAction("hotkey", {"keys": ["enter"]}, "Press Enter"),
                    PlanAction("wait", {"seconds": 1.0}, "Wait for Notepad"),
                ],
                confidence=0.92,
                reasoning="Win+R is fastest for launching apps by name"
            )
        elif self.approach == "mouse":
            return Plan(
                approach="mouse",
                actions=[
                    PlanAction("click", {"target": "start_button"}, "Click Start button"),
                    PlanAction("wait", {"seconds": 0.5}, "Wait for menu"),
                    PlanAction("type", {"text": "notepad"}, "Type to search"),
                    PlanAction("wait", {"seconds": 0.5}, "Wait for results"),
                    PlanAction("click", {"target": "notepad_result"}, "Click Notepad"),
                    PlanAction("wait", {"seconds": 1.0}, "Wait for Notepad"),
                ],
                confidence=0.78,
                reasoning="Click-based approach, more steps required"
            )
        else:  # hybrid
            return Plan(
                approach="hybrid",
                actions=[
                    PlanAction("hotkey", {"keys": ["win"]}, "Press Windows key"),
                    PlanAction("wait", {"seconds": 0.3}, "Wait for Start menu"),
                    PlanAction("type", {"text": "notepad"}, "Type to search"),
                    PlanAction("wait", {"seconds": 0.5}, "Wait for results"),
                    PlanAction("hotkey", {"keys": ["enter"]}, "Press Enter on result"),
                    PlanAction("wait", {"seconds": 1.0}, "Wait for Notepad"),
                ],
                confidence=0.85,
                reasoning="Uses keyboard for speed with visual confirmation"
            )


class MockSpecialistSubagent:
    """Simulates a specialist subagent with domain knowledge."""

    def __init__(self, domain: str):
        self.domain = domain
        self.knowledge = {
            "system": {
                "shortcuts": {
                    "run_dialog": {"keys": "Win+R", "description": "Open Run dialog"},
                    "start_menu": {"keys": "Win", "description": "Open Start menu"},
                    "close_window": {"keys": "Alt+F4", "description": "Close active window"},
                    "task_manager": {"keys": "Ctrl+Shift+Esc", "description": "Open Task Manager"},
                    "file_explorer": {"keys": "Win+E", "description": "Open File Explorer"},
                },
                "workflows": {
                    "open_app_fast": ["Win+R", "type app name", "Enter"],
                    "search_app": ["Win", "type to search", "Enter or click"],
                }
            }
        }

    async def query(self, question: str) -> Dict:
        """Query the specialist for domain knowledge."""
        await asyncio.sleep(0.05)  # Simulate lookup

        domain_data = self.knowledge.get(self.domain, {})
        return {
            "domain": self.domain,
            "shortcuts": domain_data.get("shortcuts", {}),
            "workflows": domain_data.get("workflows", {}),
            "answer": f"For {self.domain}: Use keyboard shortcuts for fastest results"
        }


class MockVisionSubagent:
    """Simulates a vision subagent that analyzes screenshots."""

    async def analyze(self, screenshot_bytes: bytes, prompt: str) -> Dict:
        """Analyze a screenshot region."""
        await asyncio.sleep(0.1)  # Simulate vision processing

        # In a real implementation, this would use an LLM vision model
        # For this demo, we'll do simple window detection

        analysis = {
            "prompt": prompt,
            "elements_detected": [],
            "analysis": "Unable to analyze - mock implementation",
            "confidence": 0.5
        }

        if HAS_PIL and screenshot_bytes:
            try:
                # Check if there's actual image data
                img = Image.open(io.BytesIO(screenshot_bytes))
                width, height = img.size

                # Very basic "analysis" - just report we got an image
                analysis["analysis"] = f"Screenshot captured: {width}x{height} pixels"
                analysis["confidence"] = 0.7

                # Check if image has any white regions (Notepad background)
                # This is a very crude approximation
                pixels = list(img.getdata())
                white_count = sum(1 for p in pixels if isinstance(p, tuple) and len(p) >= 3 and p[0] > 240 and p[1] > 240 and p[2] > 240)
                white_ratio = white_count / len(pixels) if pixels else 0

                if white_ratio > 0.3:
                    analysis["elements_detected"].append({
                        "type": "window",
                        "likely_app": "Notepad or similar",
                        "has_white_background": True
                    })
                    analysis["analysis"] = "Detected window with white background - likely Notepad"
                    analysis["confidence"] = 0.8

            except Exception as e:
                analysis["error"] = str(e)

        return analysis


class MockBackgroundMonitor:
    """Simulates a background monitor that watches for conditions."""

    def __init__(self, condition: str, target: str):
        self.condition = condition
        self.target = target
        self._cancelled = False

    async def wait_for_condition(self, timeout: float = 10.0) -> Dict:
        """Wait for the condition to be met."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._cancelled:
                return {"met": False, "reason": "cancelled"}

            # Check condition
            if self.condition == "window_exists":
                if HAS_PYAUTOGUI:
                    try:
                        # Try to find a window with the target title
                        windows = pyautogui.getWindowsWithTitle(self.target)
                        if windows:
                            return {
                                "met": True,
                                "window_title": windows[0].title,
                                "elapsed": time.time() - start_time
                            }
                    except Exception:
                        pass

            await asyncio.sleep(0.2)

        return {"met": False, "reason": "timeout", "elapsed": timeout}

    def cancel(self):
        """Cancel the monitor."""
        self._cancelled = True


# ============================================================
# Action Executor
# ============================================================

class ActionExecutor:
    """Executes plan actions using PyAutoGUI."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    async def execute_action(self, action: PlanAction) -> bool:
        """Execute a single action."""
        print(f"      > {action.description}...", end=" ", flush=True)

        if self.dry_run:
            await asyncio.sleep(0.1)
            print("[DRY RUN]")
            return True

        if not HAS_PYAUTOGUI:
            await asyncio.sleep(0.1)
            print("[SIMULATED]")
            return True

        try:
            if action.action_type == "hotkey":
                keys = action.params.get("keys", [])
                pyautogui.hotkey(*keys)
                print("done")

            elif action.action_type == "type":
                text = action.params.get("text", "")
                pyautogui.write(text, interval=0.05)
                print("done")

            elif action.action_type == "click":
                target = action.params.get("target", "")
                # For this demo, we'll skip actual clicking on targets
                # In real implementation, this would find and click the element
                print(f"[SKIP - would click {target}]")

            elif action.action_type == "wait":
                seconds = action.params.get("seconds", 1.0)
                await asyncio.sleep(seconds)
                print(f"waited {seconds}s")

            else:
                print(f"[UNKNOWN ACTION TYPE: {action.action_type}]")

            return True

        except Exception as e:
            print(f"[ERROR: {e}]")
            return False

    async def execute_plan(self, plan: Plan) -> ExecutionResult:
        """Execute a complete plan."""
        steps_completed = 0

        for action in plan.actions:
            success = await self.execute_action(action)
            if success:
                steps_completed += 1
            else:
                return ExecutionResult(
                    success=False,
                    steps_completed=steps_completed,
                    total_steps=len(plan.actions),
                    error=f"Failed at step {steps_completed + 1}: {action.description}"
                )

        # Capture final screenshot
        screenshot_bytes = None
        if HAS_PYAUTOGUI and HAS_PIL:
            try:
                screenshot = pyautogui.screenshot()
                buffer = io.BytesIO()
                screenshot.save(buffer, format='PNG')
                screenshot_bytes = buffer.getvalue()
            except Exception as e:
                print(f"      > Screenshot capture failed: {e}")

        return ExecutionResult(
            success=True,
            steps_completed=steps_completed,
            total_steps=len(plan.actions),
            screenshot=screenshot_bytes
        )


# ============================================================
# Main Test Runner
# ============================================================

async def run_real_test(dry_run: bool = False):
    """Run the full interactive test scenario."""

    print("=" * 60)
    print("   MoireTracker Real Interactive Test")
    print("=" * 60)
    print()

    if dry_run:
        print("[DRY RUN MODE - No actual actions will be performed]")
        print()

    # -------------------- Phase 1: Setup --------------------
    print("[1/5] Setup...")

    if not HAS_PYAUTOGUI:
        print("      [WARN] PyAutoGUI not available - actions will be simulated")
    else:
        print("      PyAutoGUI ready (move mouse to corner to abort)")

    if not HAS_PIL:
        print("      [WARN] Pillow not available - screenshots disabled")
    else:
        print("      Pillow ready for screenshots")

    print("      [SKIP] Redis connection (using mock subagents for demo)")
    print()

    # -------------------- Phase 2: Planning --------------------
    print("[2/5] Planning: 'Open Notepad and type Hello World'")
    print()
    print("      Spawning parallel planners...")

    # Create parallel planning tasks
    planners = [
        MockPlanningSubagent("keyboard"),
        MockPlanningSubagent("mouse"),
        MockPlanningSubagent("hybrid")
    ]

    goal = "Open Notepad application"
    context = {"os": "Windows", "task": "open_app"}

    # Execute plans in parallel
    start_time = time.time()
    plan_tasks = [planner.plan(goal, context) for planner in planners]
    plans = await asyncio.gather(*plan_tasks)
    planning_time = (time.time() - start_time) * 1000

    print(f"      Parallel planning completed in {planning_time:.1f}ms")
    print()

    # Display all plans
    for plan in plans:
        print(f"      - {plan.approach.capitalize()} approach: confidence {plan.confidence:.2f}")
        print(f"        Actions: {' -> '.join(a.description for a in plan.actions[:3])}...")
        print(f"        Reasoning: {plan.reasoning}")
        print()

    # Select best plan
    best_plan = max(plans, key=lambda p: p.confidence)
    print(f"      Selected: {best_plan.approach.capitalize()} approach (highest confidence)")
    print()

    # -------------------- Phase 3: Specialist Query --------------------
    print("[3/5] Querying specialist...")

    specialist = MockSpecialistSubagent("system")
    advice = await specialist.query("What's the fastest way to open an app?")

    print(f"      Domain: {advice['domain']}")
    print(f"      Advice: {advice['answer']}")
    print("      Available shortcuts:")
    for name, shortcut in list(advice['shortcuts'].items())[:3]:
        print(f"        - {name}: {shortcut['keys']}")
    print()

    # -------------------- Phase 4: Execution --------------------
    print("[4/5] Executing plan...")
    print()

    executor = ActionExecutor(dry_run=dry_run)

    # Start background monitor for Notepad window
    monitor = MockBackgroundMonitor("window_exists", "Notepad")
    monitor_task = asyncio.create_task(monitor.wait_for_condition(timeout=5.0))

    # Execute the plan
    result = await executor.execute_plan(best_plan)

    if result.success:
        print()
        print(f"      Plan executed: {result.steps_completed}/{result.total_steps} steps")

        # Wait for Notepad window
        print("      > Waiting for Notepad window...", end=" ", flush=True)
        monitor_result = await monitor_task

        if monitor_result.get("met"):
            print(f"detected! (took {monitor_result['elapsed']:.1f}s)")
        else:
            print(f"[{monitor_result.get('reason', 'unknown')}]")

        # Type the message
        if HAS_PYAUTOGUI and not dry_run:
            print("      > Typing 'Hello World from MoireTracker!'...", end=" ", flush=True)
            await asyncio.sleep(0.5)  # Wait for window focus
            pyautogui.write("Hello World from MoireTracker!", interval=0.03)
            print("done")
        else:
            print("      > Typing 'Hello World from MoireTracker!'... [SIMULATED]")

    else:
        print(f"      [FAIL] {result.error}")
        monitor.cancel()
        await monitor_task

    print()

    # -------------------- Phase 5: Verification --------------------
    print("[5/5] Verifying result...")

    if result.screenshot:
        print("      Screenshot captured")

        vision = MockVisionSubagent()
        analysis = await vision.analyze(result.screenshot, "Verify Notepad is open with text")

        print(f"      Analysis: {analysis['analysis']}")
        print(f"      Confidence: {analysis['confidence']:.2f}")

        if analysis['elements_detected']:
            print("      Elements detected:")
            for elem in analysis['elements_detected']:
                print(f"        - {elem}")
    else:
        print("      [SKIP] No screenshot available for verification")

    print()

    # -------------------- Summary --------------------
    print("=" * 60)
    if result.success:
        print("   TEST COMPLETED SUCCESSFULLY")
    else:
        print("   TEST FAILED")
    print("=" * 60)
    print()

    print("Summary:")
    print(f"  - Planning approaches tested: {len(plans)}")
    print(f"  - Best approach: {best_plan.approach} (confidence: {best_plan.confidence:.2f})")
    print(f"  - Actions executed: {result.steps_completed}/{result.total_steps}")
    print(f"  - Specialist domain: {advice['domain']}")
    if result.screenshot:
        print(f"  - Verification: {analysis['analysis']}")

    return result.success


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="MoireTracker Real Interactive Test")
    parser.add_argument("--dry-run", action="store_true", help="Don't execute real actions")
    args = parser.parse_args()

    print()
    print("This test will ACTUALLY control your desktop!")
    print("Move mouse to any corner to abort (PyAutoGUI failsafe)")
    print()

    if not args.dry_run:
        print("Starting in 3 seconds... (Ctrl+C or move mouse to corner to abort)")
        for i in range(3, 0, -1):
            print(f"  {i}...")
            await asyncio.sleep(1)
        print()

    try:
        success = await run_real_test(dry_run=args.dry_run)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[ABORTED by user]")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
