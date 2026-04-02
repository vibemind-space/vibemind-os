"""
Interactive CLI for Handoff Multi-Agent System

An interactive command-line interface for controlling the
desktop automation agents and Society of Mind teams.

Usage:
    python interactive_cli.py           # Rule-based mode (fast)
    python interactive_cli.py --llm     # LLM-powered mode (intelligent)
"""

import asyncio
import argparse
import sys
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.handoff import (
    AgentRuntime,
    UserTask,
    OrchestratorAgent,
    ExecutionAgent,
    VisionHandoffAgent,
    RecoveryAgent,
    PlanningTeam,
    ValidationTeam,
)


class InteractiveCLI:
    """Interactive CLI for the handoff system."""

    def __init__(self, use_llm: bool = False):
        self.runtime: Optional[AgentRuntime] = None
        self.planning_team: Optional[PlanningTeam] = None
        self.validation_team: Optional[ValidationTeam] = None
        self.running = False
        self.history = []
        self.use_llm = use_llm

    async def setup(self):
        """Initialize the agent runtime."""
        print("\n" + "=" * 60)
        print("  HANDOFF MULTI-AGENT SYSTEM")
        print("  Society of Mind + Sequential Handoffs")
        if self.use_llm:
            print("  ** LLM-POWERED MODE **")
        print("=" * 60)
        print("\nInitializing agents...")

        # Create runtime
        self.runtime = AgentRuntime()

        # Create and register agents
        orchestrator = OrchestratorAgent()
        execution = ExecutionAgent()
        vision = VisionHandoffAgent()
        recovery = RecoveryAgent()

        await self.runtime.register_agent("orchestrator", orchestrator)
        await self.runtime.register_agent("execution", execution)
        await self.runtime.register_agent("vision", vision)
        await self.runtime.register_agent("recovery", recovery)

        # Create Society of Mind teams
        self.planning_team = PlanningTeam(
            max_debate_rounds=2,
            use_llm=self.use_llm
        )
        self.validation_team = ValidationTeam(confidence_threshold=0.6)

        await self.planning_team.start()
        await self.validation_team.start()

        print(f"  Agents: {list(self.runtime._agents.keys())}")
        print(f"  Teams: planning_team, validation_team")
        print(f"  LLM: {'enabled' if self.use_llm else 'disabled'}")
        print("\nReady!")

    def print_help(self):
        """Print help message."""
        print("""
Commands:
  send <message>     Send message to Claude Desktop
  plan <goal>        Create a plan using PlanningTeam
  validate <target>  Validate an element using ValidationTeam
  hotkey <keys>      Execute hotkey (e.g., hotkey ctrl+alt+space)
  type <text>        Type text at current cursor
  press <key>        Press a key (e.g., enter, tab, escape)
  click <x> <y>      Click at coordinates
  sleep <seconds>    Wait for specified seconds
  status             Show system status
  history            Show command history
  help               Show this help message
  quit / exit        Exit the CLI

Examples:
  send Hello from the CLI!
  plan Send message to Claude Desktop
  validate chat input field
  hotkey ctrl+alt+space
  type Hello World
  press enter
""")

    def print_status(self):
        """Print system status."""
        print("\n" + "-" * 40)
        print("SYSTEM STATUS")
        print("-" * 40)

        if self.runtime:
            stats = self.runtime.get_stats()
            print(f"  Tasks processed: {stats.get('tasks_processed', 0)}")
            print(f"  Handoffs routed: {stats.get('handoffs_routed', 0)}")
            print(f"  Sessions: {stats.get('sessions_completed', 0)}")
            print(f"  Errors: {stats.get('errors', 0)}")
            print(f"\n  Registered agents:")
            for name in self.runtime._agents.keys():
                print(f"    - {name}")

        print(f"\n  Planning Team: {'active' if self.planning_team else 'inactive'}")
        print(f"  Validation Team: {'active' if self.validation_team else 'inactive'}")
        print("-" * 40)

    def print_history(self):
        """Print command history."""
        print("\n" + "-" * 40)
        print("COMMAND HISTORY")
        print("-" * 40)
        if not self.history:
            print("  (no commands yet)")
        else:
            for i, (ts, cmd, result) in enumerate(self.history[-10:], 1):
                status = "OK" if result else "FAIL"
                print(f"  {i}. [{ts}] {cmd} -> {status}")
        print("-" * 40)

    async def execute_send(self, message: str):
        """Send message to Claude Desktop."""
        print(f"\nSending: {message}")
        print("-" * 40)

        def progress_callback(update):
            agent = update.get("agent", "?")
            progress = update.get("progress", 0)
            msg = update.get("message", "")
            print(f"  [{agent}] {progress:.0f}% - {msg}")

        task = UserTask(
            goal=f"Send message to Claude Desktop: {message}",
            context={"message": message}
        )

        await self.runtime.start()
        result = await self.runtime.publish_task(
            task,
            target_agent="orchestrator",
            progress_callback=progress_callback
        )
        await self.runtime.stop()

        success = result.success if result else False
        print("-" * 40)
        print(f"Result: {'Success' if success else 'Failed'}")

        return success

    async def execute_plan(self, goal: str, context: Optional[Dict] = None):
        """Create a plan using PlanningTeam with user escalation."""
        print(f"\nPlanning: {goal}")
        print("-" * 40)

        result = await self.planning_team.create_plan(goal, context=context or {})

        # Display results
        print(f"\n  Success: {result.get('success')}")
        print(f"  Approved: {result.get('approved')}")
        print(f"  Confidence: {result.get('planner_confidence', 0):.0%}")
        print(f"  Risk Score: {result.get('risk_score', 0):.0%}")

        if result.get('issues'):
            print(f"\n  Issues:")
            for issue in result['issues']:
                print(f"    - {issue}")

        if result.get('plan'):
            print(f"\n  Plan ({len(result['plan'])} steps):")
            for i, step in enumerate(result['plan'], 1):
                print(f"    {i}. [{step.get('type')}] {step.get('description')}")

        print("-" * 40)

        # Handle escalation when not approved
        return await self._handle_plan_result(goal, result)

    async def _handle_plan_result(self, goal: str, result: Dict[str, Any]) -> bool:
        """Handle plan result with user escalation if needed."""
        plan = result.get('plan', [])
        approved = result.get('approved', False)

        # If approved, execute automatically
        if approved and plan:
            print("\nPlan approved - executing automatically...")
            return await self._execute_plan_steps(plan)

        # If not approved but we have a plan, ask user
        if not approved and plan:
            print("\n" + "!" * 40)
            print("  PLAN NOT APPROVED BY CRITIC")
            print("!" * 40)
            print("\nOptions:")
            print("  [p] Proceed anyway - execute the plan despite issues")
            print("  [r] Retry - provide feedback to improve the plan")
            print("  [a] Abort - cancel this operation")

            try:
                choice = input("\nChoice [p/r/a]: ").strip().lower()
            except EOFError:
                choice = 'a'

            if choice == 'p':
                print("\nProceeding with unapproved plan...")
                return await self._execute_plan_steps(plan)
            elif choice == 'r':
                try:
                    feedback = input("Your feedback: ").strip()
                except EOFError:
                    feedback = ""
                if feedback:
                    return await self._execute_plan_with_feedback(goal, feedback)
                else:
                    print("No feedback provided. Aborting.")
                    return False
            else:
                print("Aborted.")
                return False

        # No plan generated
        return result.get('success', False)

    async def _execute_plan_steps(self, plan: List[Dict[str, Any]]) -> bool:
        """Execute plan steps autonomously."""
        import pyautogui
        import pyperclip

        print(f"\n>>> EXECUTING PLAN ({len(plan)} steps) <<<\n")

        for i, step in enumerate(plan, 1):
            step_type = step.get('type', '')
            desc = step.get('description', '')
            print(f"  Step {i}: [{step_type}] {desc}")

            try:
                if step_type == 'hotkey':
                    keys = step.get('keys', '').replace('+', ' ').split()
                    if keys:
                        pyautogui.hotkey(*keys)
                elif step_type == 'sleep':
                    duration = step.get('duration', step.get('seconds', 1))
                    await asyncio.sleep(float(duration))
                elif step_type == 'write':
                    text = step.get('text', step.get('content', ''))
                    if text:
                        pyperclip.copy(text)
                        pyautogui.hotkey('ctrl', 'v')
                elif step_type == 'press':
                    key = step.get('key', 'enter')
                    pyautogui.press(key)
                elif step_type == 'click':
                    x = step.get('x', 0)
                    y = step.get('y', 0)
                    pyautogui.click(int(x), int(y))
                elif step_type == 'find_and_click':
                    # Use validation team to find element
                    target = step.get('target', step.get('text', ''))
                    if target and self.validation_team:
                        loc_result = await self.validation_team.validate_element(target)
                        if loc_result.get('element_location'):
                            loc = loc_result['element_location']
                            pyautogui.click(loc['x'], loc['y'])
                        else:
                            print(f"    Warning: Could not find '{target}'")
                else:
                    print(f"    Unknown step type: {step_type}")

                # Small delay between steps
                await asyncio.sleep(0.3)
                print(f"    Done")

            except Exception as e:
                print(f"    Error: {e}")
                return False

        print(f"\n>>> PLAN EXECUTED SUCCESSFULLY <<<")
        return True

    async def _execute_plan_with_feedback(self, goal: str, feedback: str) -> bool:
        """Retry planning with user feedback."""
        print(f"\nRetrying with feedback: {feedback}")
        print("-" * 40)

        # Pass feedback in context
        return await self.execute_plan(
            goal,
            context={"user_feedback": feedback}
        )

    async def execute_validate(self, target: str):
        """Validate an element using ValidationTeam."""
        print(f"\nValidating: {target}")
        print("-" * 40)

        result = await self.validation_team.validate_element(target)

        print(f"\n  Valid: {result.get('valid')}")
        print(f"  Confidence: {result.get('overall_confidence', 0):.0%}")
        print(f"  Validators: {result.get('validators_succeeded')}/{result.get('validators_total')}")

        if result.get('element_location'):
            loc = result['element_location']
            print(f"  Location: ({loc['x']}, {loc['y']})")

        if result.get('issues'):
            print(f"\n  Issues:")
            for issue in result['issues']:
                print(f"    - {issue}")

        print("-" * 40)
        return result.get('valid', False)

    async def execute_hotkey(self, keys: str):
        """Execute a hotkey."""
        import pyautogui

        key_list = keys.replace('+', ' ').split()
        print(f"\nHotkey: {'+'.join(key_list)}")

        pyautogui.hotkey(*key_list)
        print("  Done")
        return True

    async def execute_type(self, text: str):
        """Type text."""
        import pyautogui
        import pyperclip

        print(f"\nTyping: {text[:50]}{'...' if len(text) > 50 else ''}")

        # Use clipboard for reliability
        pyperclip.copy(text)
        pyautogui.hotkey('ctrl', 'v')
        print("  Done")
        return True

    async def execute_press(self, key: str):
        """Press a key."""
        import pyautogui

        print(f"\nPressing: {key}")
        pyautogui.press(key)
        print("  Done")
        return True

    async def execute_click(self, x: int, y: int):
        """Click at coordinates."""
        import pyautogui

        print(f"\nClicking: ({x}, {y})")
        pyautogui.click(x, y)
        print("  Done")
        return True

    async def execute_sleep(self, seconds: float):
        """Sleep for specified seconds."""
        print(f"\nSleeping: {seconds}s")
        await asyncio.sleep(seconds)
        print("  Done")
        return True

    async def process_command(self, cmd: str) -> bool:
        """Process a single command. Returns True to continue, False to exit."""
        cmd = cmd.strip()
        if not cmd:
            return True

        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        timestamp = datetime.now().strftime("%H:%M:%S")
        result = False

        try:
            if command in ('quit', 'exit', 'q'):
                return False

            elif command == 'help':
                self.print_help()
                result = True

            elif command == 'status':
                self.print_status()
                result = True

            elif command == 'history':
                self.print_history()
                result = True

            elif command == 'send':
                if not args:
                    print("Usage: send <message>")
                else:
                    result = await self.execute_send(args)

            elif command == 'plan':
                if not args:
                    print("Usage: plan <goal>")
                else:
                    result = await self.execute_plan(args)

            elif command == 'validate':
                if not args:
                    print("Usage: validate <target>")
                else:
                    result = await self.execute_validate(args)

            elif command == 'hotkey':
                if not args:
                    print("Usage: hotkey <keys> (e.g., hotkey ctrl+alt+space)")
                else:
                    result = await self.execute_hotkey(args)

            elif command == 'type':
                if not args:
                    print("Usage: type <text>")
                else:
                    result = await self.execute_type(args)

            elif command == 'press':
                if not args:
                    print("Usage: press <key>")
                else:
                    result = await self.execute_press(args)

            elif command == 'click':
                try:
                    coords = args.split()
                    x, y = int(coords[0]), int(coords[1])
                    result = await self.execute_click(x, y)
                except (ValueError, IndexError):
                    print("Usage: click <x> <y>")

            elif command == 'sleep':
                try:
                    seconds = float(args)
                    result = await self.execute_sleep(seconds)
                except ValueError:
                    print("Usage: sleep <seconds>")

            else:
                print(f"Unknown command: {command}")
                print("Type 'help' for available commands")

        except Exception as e:
            print(f"Error: {e}")
            result = False

        # Record in history (except help/status/history)
        if command not in ('help', 'status', 'history'):
            self.history.append((timestamp, cmd, result))

        return True

    async def run(self):
        """Run the interactive CLI loop."""
        await self.setup()

        print("\nType 'help' for commands, 'quit' to exit\n")
        self.running = True

        while self.running:
            try:
                # Get input
                cmd = input("\n> ").strip()

                # Process command
                continue_running = await self.process_command(cmd)
                if not continue_running:
                    break

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'quit' to exit.")
            except EOFError:
                break

        await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        print("\nShutting down...")

        if self.planning_team:
            # Close LLM client if it exists
            if hasattr(self.planning_team, 'llm_client') and self.planning_team.llm_client:
                await self.planning_team.llm_client.close()
            await self.planning_team.stop()
        if self.validation_team:
            await self.validation_team.stop()
        if self.runtime:
            await self.runtime.stop()

        print("Goodbye!")


async def main():
    parser = argparse.ArgumentParser(description="Interactive CLI for Handoff Multi-Agent System")
    parser.add_argument("--llm", action="store_true",
                       help="Enable LLM-powered mode for intelligent planning")
    args = parser.parse_args()

    cli = InteractiveCLI(use_llm=args.llm)
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
