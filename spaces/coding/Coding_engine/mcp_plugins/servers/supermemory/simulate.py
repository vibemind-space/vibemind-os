#!/usr/bin/env python3
"""Simulate Supermemory MCP Agent with a realistic task.

NOTE: Requires SUPERMEMORY_API_KEY environment variable
Get your API key from: https://console.supermemory.ai/
"""
import subprocess
import sys
import os

def main():
    """Run supermemory agent simulation."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("Supermemory Agent Simulation")
    print("=" * 60)
    print("Task: Search for React component patterns")
    print()

    if not os.getenv("SUPERMEMORY_API_KEY"):
        print("[SKIP] SUPERMEMORY_API_KEY not set")
        print("Get your API key from: https://console.supermemory.ai/")
        return 2  # Skip exit code

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(script_dir, "agent.py"),
             "--task", "Search for React component patterns in memory",
             "--session-id", "sim_supermemory_test"],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=script_dir,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )

        if "SESSION_ANNOUNCE" in result.stdout:
            print("[OK] Agent started successfully")
            print()
            print("Output (last 500 chars):")
            print("-" * 40)
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)

            if "TASK_COMPLETE" in result.stdout:
                print()
                print("[OK] Task completed successfully")
                return 0
            else:
                print()
                print("[WARN] Task may not have completed")
                return 1
        else:
            print("[FAIL] Agent failed to start")
            print("stderr:", result.stderr[:500] if result.stderr else "None")
            return 1

    except subprocess.TimeoutExpired:
        print("[FAIL] Agent timed out after 90s")
        return 1
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
