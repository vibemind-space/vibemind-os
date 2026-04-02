#!/usr/bin/env python3
"""Quick E2E test for 3 MCP tools to verify log naming"""
import requests
import time
import os
from datetime import datetime

BACKEND_URL = 'http://127.0.0.1:8765'

# Test 3 tools that should work
TOOLS = ['time', 'memory', 'taskmanager']

def test_tool(tool):
    """Quick test for one tool"""
    print(f"\n[{tool.upper()}]", end=" ", flush=True)

    try:
        # Create session
        resp = requests.post(f'{BACKEND_URL}/api/sessions',
            json={'tool': tool, 'name': f'quick-test-{tool}'},
            timeout=5)

        if resp.status_code != 200:
            print(f"FAIL - Session creation: {resp.status_code}")
            return False

        data = resp.json()
        session_id = data.get('session_id')
        if not session_id:
            print(f"FAIL - No session_id returned")
            return False

        print(f"Session: {session_id[:8]}...", end=" ", flush=True)

        # Start agent with simple task
        tasks = {
            'time': 'Get current UTC time',
            'memory': 'Create entity "TestEntity" type "test" observation "test"',
            'taskmanager': 'Create task "Test Task"'
        }

        resp = requests.post(f'{BACKEND_URL}/api/sessions/{session_id}/start',
            json={'task': tasks[tool]},
            timeout=10)

        if resp.status_code != 200:
            print(f"FAIL - Agent start: {resp.status_code}")
            return False

        print("Started", end=" ", flush=True)

        # Wait briefly
        time.sleep(3)

        # Check log file exists
        log_dir = '../../../../data/logs/sessions'
        log_files = [f for f in os.listdir(log_dir)
                    if f.startswith(f'{tool}_') and session_id in f]

        if log_files:
            print(f"✓ Log: {log_files[0]}")

            # Check for errors
            log_file = os.path.join(log_dir, log_files[0])
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if 'ERROR' in content or 'Exception' in content:
                error_count = content.count('ERROR') + content.count('Exception')
                print(f"  ⚠ Found {error_count} errors/exceptions in log")
                return 'errors'

            return True
        else:
            print("FAIL - No log file created")
            return False

    except Exception as e:
        print(f"FAIL - Exception: {e}")
        return False
    finally:
        # Cleanup
        if session_id:
            try:
                requests.delete(f'{BACKEND_URL}/api/sessions/{session_id}', timeout=2)
            except:
                pass

def main():
    print("="*70)
    print("QUICK E2E TEST - 3 MCP TOOLS")
    print("="*70)

    results = {}
    for tool in TOOLS:
        results[tool] = test_tool(tool)
        time.sleep(1)

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    success = sum(1 for r in results.values() if r is True)
    with_errors = sum(1 for r in results.values() if r == 'errors')
    failed = sum(1 for r in results.values() if r is False)

    print(f"Success: {success}/{len(TOOLS)}")
    print(f"With Errors: {with_errors}/{len(TOOLS)}")
    print(f"Failed: {failed}/{len(TOOLS)}")

    # Show log files
    print("\nLog Files Created:")
    log_dir = '../../../../data/logs/sessions'
    for f in sorted(os.listdir(log_dir)):
        if f.endswith('.log'):
            size = os.path.getsize(os.path.join(log_dir, f))
            print(f"  {f} ({size} bytes)")

    print("="*70)

    return 0 if failed == 0 else 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
