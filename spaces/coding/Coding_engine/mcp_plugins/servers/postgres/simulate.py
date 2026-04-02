#!/usr/bin/env python3
"""Simulate PostgreSQL MCP Agent with a realistic task.

NOTE: Requires DATABASE_URL environment variable set
"""
import subprocess
import sys
import os

def main():
    """Run postgres agent simulation."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("PostgreSQL Agent Simulation")
    print("=" * 60)
    print("Task: Check database connection status")
    print()

    if not os.getenv("DATABASE_URL"):
        print("[SKIP] DATABASE_URL not set")
        print("Set DATABASE_URL=postgresql://user:pass@localhost:5432/dbname")
        return 2  # Skip exit code

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(script_dir, "agent.py"),
             "--task", "Check database connection status and list available tables",
             "--session-id", "sim_postgres_test"],
            capture_output=True,
            text=True,
            timeout=60,
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
        print("[FAIL] Agent timed out after 60s")
        return 1
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
