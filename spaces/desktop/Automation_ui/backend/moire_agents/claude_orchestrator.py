"""
Claude Code Orchestrator - Calls Claude Code CLI with MCP handoff tools.

Usage:
    python claude_orchestrator.py "open notepad and type hello"
    python claude_orchestrator.py --interactive
"""

import subprocess
import sys
import json
import os

# Path to claude CLI - use npm global install location on Windows
CLAUDE_CMD = os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd")

# MCP config path
MCP_CONFIG = os.path.join(os.path.dirname(__file__), "..", "..", ".mcp.json")


def call_claude(prompt: str, use_mcp: bool = True) -> dict:
    """
    Call Claude Code CLI with a prompt.

    Args:
        prompt: The task/question for Claude
        use_mcp: Whether to use MCP servers (handoff tools)

    Returns:
        dict with stdout, stderr, returncode
    """
    cmd = [CLAUDE_CMD]

    # Add MCP config if available
    if use_mcp and os.path.exists(MCP_CONFIG):
        cmd.extend(["--mcp-config", MCP_CONFIG])

    # Add prompt flag for non-interactive mode
    cmd.extend(["-p", prompt])

    # Run claude CLI
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=os.path.dirname(__file__)
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Claude CLI timed out after 5 minutes",
            "stdout": "",
            "stderr": ""
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "Claude CLI not found. Make sure 'claude' is in PATH.",
            "stdout": "",
            "stderr": ""
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stdout": "",
            "stderr": ""
        }


def call_claude_streaming(prompt: str, use_mcp: bool = True):
    """
    Call Claude Code CLI with streaming output.

    Args:
        prompt: The task/question for Claude
        use_mcp: Whether to use MCP servers

    Yields:
        Lines of output as they come
    """
    cmd = [CLAUDE_CMD]

    if use_mcp and os.path.exists(MCP_CONFIG):
        cmd.extend(["--mcp-config", MCP_CONFIG])

    cmd.extend(["-p", prompt])

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=os.path.dirname(__file__)
    )

    for line in process.stdout:
        yield line

    process.wait()


def desktop_command(task: str) -> dict:
    """
    Execute a desktop automation task using Claude + handoff MCP.

    Args:
        task: Natural language description of the task

    Returns:
        Result from Claude
    """
    prompt = f"""Use the handoff MCP tools to accomplish this task:

{task}

Available tools:
- handoff_plan: Create an automation plan
- handoff_execute: Execute plan steps
- handoff_action: Direct actions (hotkey, type, press, click, sleep)
- handoff_read_screen: Read screen content via OCR/screenshot
- handoff_validate: Find UI elements
- handoff_status: Check system status

Execute the task and report the result."""

    return call_claude(prompt)


def interactive_mode():
    """Run interactive mode where user can give commands."""
    print("=" * 60)
    print("Claude Desktop Commander - Interactive Mode")
    print("=" * 60)
    print("Enter desktop automation tasks. Type 'quit' to exit.")
    print()

    while True:
        try:
            task = input("Task> ").strip()

            if not task:
                continue

            if task.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break

            print(f"\nExecuting: {task}")
            print("-" * 40)

            # Stream output
            for line in call_claude_streaming(task):
                print(line, end='')

            print()
            print("-" * 40)

        except KeyboardInterrupt:
            print("\nInterrupted. Goodbye!")
            break
        except EOFError:
            break


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python claude_orchestrator.py \"<task>\"")
        print("  python claude_orchestrator.py --interactive")
        print()
        print("Examples:")
        print("  python claude_orchestrator.py \"open notepad and type hello world\"")
        print("  python claude_orchestrator.py \"send a message to Claude Desktop\"")
        print("  python claude_orchestrator.py \"read the screen and tell me what you see\"")
        sys.exit(1)

    if sys.argv[1] == "--interactive":
        interactive_mode()
    else:
        task = " ".join(sys.argv[1:])
        print(f"Task: {task}")
        print("=" * 60)

        # Use streaming for real-time output
        for line in call_claude_streaming(task):
            print(line, end='')
