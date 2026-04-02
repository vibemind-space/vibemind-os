#!/usr/bin/env python3
"""Simulate Qdrant MCP Agent with a realistic task.

NOTE: Requires Qdrant running on localhost:6333
Start with: docker run -d -p 6333:6333 qdrant/qdrant
"""
import subprocess
import sys
import os
import socket

def check_qdrant():
    """Check if Qdrant is running."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("localhost", 6333))
        s.close()
        return True
    except:
        return False

def main():
    """Run qdrant agent simulation."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("Qdrant Agent Simulation")
    print("=" * 60)
    print("Task: List all Qdrant collections")
    print()

    if not check_qdrant():
        print("[SKIP] Qdrant not running on localhost:6333")
        print("Start with: docker run -d -p 6333:6333 qdrant/qdrant")
        return 2  # Skip exit code

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(script_dir, "agent.py"),
             "--task", "List all collections in Qdrant",
             "--session-id", "sim_qdrant_test"],
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
