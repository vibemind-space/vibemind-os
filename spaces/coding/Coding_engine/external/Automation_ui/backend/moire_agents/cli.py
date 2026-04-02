"""
MoireTracker Interactive CLI - Conversational Automation Interface

An interactive command-line interface for natural language automation.
Type tasks in plain English and watch the automation engine work.

Usage:
    python cli.py
    python cli.py --real  # Enable actual PyAutoGUI execution

Commands:
    help     - Show available commands
    status   - Show status of running tasks
    history  - Show recent task history
    cancel   - Cancel a running task
    clear    - Clear the screen
    exit     - Exit the CLI
"""

import asyncio
import sys
import os
import time
from typing import Optional

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import colorama for colored output
try:
    from colorama import init, Fore as _Fore, Style as _Style
    init()
    HAS_COLOR = True

    # Wrap to ensure DIM exists
    class Fore:
        GREEN = _Fore.GREEN
        YELLOW = _Fore.YELLOW
        RED = _Fore.RED
        CYAN = _Fore.CYAN
        MAGENTA = _Fore.MAGENTA
        BLUE = _Fore.BLUE
        WHITE = _Fore.WHITE
        RESET = _Fore.RESET
        DIM = getattr(_Fore, 'LIGHTBLACK_EX', '')  # Fallback for DIM

    class Style:
        BRIGHT = _Style.BRIGHT
        DIM = getattr(_Style, 'DIM', '')
        RESET_ALL = _Style.RESET_ALL

except ImportError:
    HAS_COLOR = False
    class Fore:
        GREEN = YELLOW = RED = CYAN = MAGENTA = BLUE = WHITE = RESET = DIM = ""
    class Style:
        BRIGHT = DIM = RESET_ALL = ""

# Fix Windows console encoding
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class InteractiveCLI:
    """Interactive CLI for the MoireTracker Automation Engine."""

    def __init__(self, real_execution: bool = False):
        self.real_execution = real_execution
        self.engine = None
        self.interface = None
        self.running_tasks = {}
        self._running = True

    async def initialize(self):
        """Initialize the automation engine."""
        from core.automation_engine import AutomationEngine
        from api.conversation_interface import ConversationInterface

        self.engine = AutomationEngine()
        self.interface = ConversationInterface(self.engine)

        if self.real_execution:
            try:
                import pyautogui
                pyautogui.FAILSAFE = True
                self._print_info("PyAutoGUI enabled - move mouse to corner to abort")
            except ImportError:
                self._print_warning("PyAutoGUI not available - running in simulation mode")
                self.real_execution = False

    def _print_banner(self):
        """Print the welcome banner."""
        print()
        print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{Style.BRIGHT}   MoireTracker - Interactive Automation CLI{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
        print()
        print(f"  {Fore.WHITE}Type natural language commands to automate your desktop.{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Type 'help' for available commands, 'exit' to quit.{Style.RESET_ALL}")
        print()
        if self.real_execution:
            print(f"  {Fore.GREEN}[REAL MODE]{Style.RESET_ALL} Actions will be executed on your desktop")
        else:
            print(f"  {Fore.YELLOW}[SIMULATION]{Style.RESET_ALL} Actions are simulated (use --real for actual execution)")
        print()

    def _print_info(self, message: str):
        """Print an info message."""
        print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {message}")

    def _print_success(self, message: str):
        """Print a success message."""
        print(f"{Fore.GREEN}[OK]{Style.RESET_ALL} {message}")

    def _print_warning(self, message: str):
        """Print a warning message."""
        print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {message}")

    def _print_error(self, message: str):
        """Print an error message."""
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")

    def _print_progress(self, status: dict):
        """Print a progress update."""
        state = status.get("state", "unknown")
        progress = status.get("progress", 0)

        if state == "decomposing":
            print(f"  {Fore.BLUE}[Analyzing]{Style.RESET_ALL} Breaking down your task...")
        elif state == "scheduling":
            total = status.get("subtasks_total", 0)
            print(f"  {Fore.BLUE}[Planning]{Style.RESET_ALL} Created {total} subtasks")
        elif state == "executing":
            phase = status.get("phase", "?")
            total_phases = status.get("total_phases", "?")
            bar = self._progress_bar(progress)
            print(f"  {Fore.YELLOW}[Phase {phase}/{total_phases}]{Style.RESET_ALL} {bar} {progress:.0%}")
        elif state == "executing_subtask":
            subtask = status.get("subtask", "unknown")
            approach = status.get("approach", "")
            print(f"    {Fore.MAGENTA}>{Style.RESET_ALL} {subtask} {Fore.DIM}[{approach}]{Style.RESET_ALL}")
        elif state == "completed":
            duration = status.get("duration", 0)
            success = status.get("success", False)
            if success:
                print(f"  {Fore.GREEN}[Complete]{Style.RESET_ALL} Task finished in {duration:.1f}s")
            else:
                print(f"  {Fore.RED}[Failed]{Style.RESET_ALL} Task failed after {duration:.1f}s")
        elif state == "failed":
            error = status.get("error", "Unknown error")
            print(f"  {Fore.RED}[Error]{Style.RESET_ALL} {error}")

    def _progress_bar(self, progress: float, width: int = 20) -> str:
        """Create a text progress bar."""
        filled = int(width * progress)
        empty = width - filled
        # Use ASCII for Windows compatibility
        bar = "#" * filled + "-" * empty
        return f"[{bar}]"

    async def _execute_task(self, goal: str):
        """Execute a task and show progress."""
        print()
        print(f"{Fore.CYAN}Task:{Style.RESET_ALL} {goal}")
        print(f"{Fore.CYAN}{'-' * 50}{Style.RESET_ALL}")

        start_time = time.time()

        # Progress callback
        async def on_progress(status):
            self._print_progress(status)

        try:
            result = await self.engine.execute_complex_task(
                goal=goal,
                context={"real_execution": self.real_execution},
                on_progress=on_progress
            )

            print()
            if result.success:
                self._print_success(f"Completed {result.subtasks_completed}/{result.subtasks_total} subtasks")
                if result.summary:
                    print(f"  {Fore.WHITE}Summary: {result.summary}{Style.RESET_ALL}")
            else:
                self._print_error(f"Task failed: {result.error or 'Unknown error'}")

            return result

        except KeyboardInterrupt:
            print()
            self._print_warning("Task interrupted by user")
            return None
        except Exception as e:
            print()
            self._print_error(f"Task failed: {e}")
            return None

    def _show_help(self):
        """Show help message."""
        print()
        print(f"{Fore.CYAN}Available Commands:{Style.RESET_ALL}")
        print()
        print(f"  {Fore.WHITE}Natural Language Tasks:{Style.RESET_ALL}")
        print("    Just type what you want to do, for example:")
        print(f"    {Fore.GREEN}> Open Notepad and type Hello World{Style.RESET_ALL}")
        print(f"    {Fore.GREEN}> Search for Python tutorials on Google{Style.RESET_ALL}")
        print(f"    {Fore.GREEN}> Create a new Word document{Style.RESET_ALL}")
        print()
        print(f"  {Fore.WHITE}System Commands:{Style.RESET_ALL}")
        print(f"    {Fore.YELLOW}help{Style.RESET_ALL}     - Show this help message")
        print(f"    {Fore.YELLOW}status{Style.RESET_ALL}   - Show status of current tasks")
        print(f"    {Fore.YELLOW}history{Style.RESET_ALL}  - Show recent task history")
        print(f"    {Fore.YELLOW}clear{Style.RESET_ALL}    - Clear the screen")
        print(f"    {Fore.YELLOW}mode{Style.RESET_ALL}     - Toggle real/simulation mode")
        print(f"    {Fore.YELLOW}exit{Style.RESET_ALL}     - Exit the CLI")
        print()

    def _show_status(self):
        """Show status of running tasks."""
        tasks = self.interface.get_running_tasks() if hasattr(self.interface, 'get_running_tasks') else []

        if not tasks and not self.running_tasks:
            self._print_info("No tasks currently running")
            return

        print()
        print(f"{Fore.CYAN}Running Tasks:{Style.RESET_ALL}")
        for task_id, task in self.running_tasks.items():
            print(f"  {task_id[:8]}... - {task.get('goal', 'Unknown')[:40]}")

    def _show_history(self):
        """Show task history."""
        if not hasattr(self.engine, 'progress') or not self.engine.progress:
            self._print_info("No task history available")
            return

        history = self.engine.progress.get_history(limit=5)
        if not history:
            self._print_info("No completed tasks yet")
            return

        print()
        print(f"{Fore.CYAN}Recent Tasks:{Style.RESET_ALL}")
        for task in history:
            status = "OK" if task.get("failed_subtasks", 0) == 0 else "PARTIAL"
            completed = task.get("completed_subtasks", 0)
            total = task.get("total_subtasks", 0)
            duration = task.get("duration", 0)
            print(f"  [{status}] {completed}/{total} subtasks, {duration:.1f}s")

    def _toggle_mode(self):
        """Toggle between real and simulation mode."""
        if self.real_execution:
            self.real_execution = False
            self._print_info("Switched to SIMULATION mode")
        else:
            try:
                import pyautogui
                self.real_execution = True
                self._print_info("Switched to REAL EXECUTION mode")
                self._print_warning("Actions will control your desktop!")
            except ImportError:
                self._print_error("PyAutoGUI not installed - cannot enable real mode")

    def _clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
        self._print_banner()

    async def run(self):
        """Main CLI loop."""
        await self.initialize()
        self._print_banner()

        while self._running:
            try:
                # Get input
                prompt = f"{Fore.GREEN}>{Style.RESET_ALL} "
                user_input = input(prompt).strip()

                if not user_input:
                    continue

                # Handle commands
                cmd = user_input.lower()

                if cmd == "exit" or cmd == "quit" or cmd == "q":
                    print()
                    self._print_info("Goodbye!")
                    break

                elif cmd == "help" or cmd == "?":
                    self._show_help()

                elif cmd == "status":
                    self._show_status()

                elif cmd == "history":
                    self._show_history()

                elif cmd == "clear" or cmd == "cls":
                    self._clear_screen()

                elif cmd == "mode":
                    self._toggle_mode()

                else:
                    # Treat as natural language task
                    await self._execute_task(user_input)

                print()  # Add spacing

            except KeyboardInterrupt:
                print()
                self._print_warning("Use 'exit' to quit")
            except EOFError:
                break
            except Exception as e:
                self._print_error(f"Error: {e}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="MoireTracker Interactive Automation CLI"
    )
    parser.add_argument(
        "--real", "-r",
        action="store_true",
        help="Enable real PyAutoGUI execution"
    )

    args = parser.parse_args()

    cli = InteractiveCLI(real_execution=args.real)
    await cli.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
