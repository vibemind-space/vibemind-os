#!/usr/bin/env python3
"""E2E test for Time MCP tool"""
import requests
import time
import sys

BACKEND_URL = 'http://127.0.0.1:8765'
TOOL = 'time'

def test_time_tool():
    """Test time tool with real task execution"""
    print(f"\n{'='*70}")
    print(f"E2E Test: {TOOL.upper()}")
    print(f"{'='*70}\n")

    session_id = None

    try:
        # 1. Create session
        print("[1/4] Creating session...")
        resp = requests.post(f'{BACKEND_URL}/api/sessions',
            json={'tool': TOOL, 'name': f'e2e-test-{TOOL}'},
            timeout=5)

        if resp.status_code != 200:
            print(f"[FAIL] Session creation failed: {resp.status_code}")
            return False

        data = resp.json()
        session_id = data.get('session_id')
        print(f"[OK] Session created: {session_id}")

        # 2. Start agent
        print("\n[2/4] Starting agent...")
        task = "What is the current time in UTC and convert it to PST timezone?"
        resp = requests.post(f'{BACKEND_URL}/api/sessions/{session_id}/start',
            json={'task': task},
            timeout=10)

        if resp.status_code != 200:
            print(f"[FAIL] Agent start failed: {resp.status_code}")
            return False

        print(f"[OK] Agent started with task: {task}")

        # 3. Wait and check status
        print("\n[3/4] Monitoring execution...")
        max_wait = 30
        for i in range(max_wait):
            time.sleep(1)
            resp = requests.get(f'{BACKEND_URL}/api/sessions/{session_id}', timeout=5)

            if resp.status_code == 200:
                session_data = resp.json()
                status = session_data.get('status', 'unknown')
                print(f"  [{i+1}s] Status: {status}", end='\r')

                if status in ['completed', 'error']:
                    print(f"\n[OK] Agent finished with status: {status}")
                    break

            if i == max_wait - 1:
                print(f"\n[WARN] Timeout after {max_wait}s, agent still running")

        # 4. Check logs
        print("\n[4/4] Checking session logs...")
        import os
        log_dir = '../../../../data/logs/sessions'
        log_files = [f for f in os.listdir(log_dir) if f.startswith(f'{TOOL}_') and session_id in f]

        if log_files:
            log_file = os.path.join(log_dir, log_files[0])
            print(f"[OK] Log file created: {log_files[0]}")

            # Read log content
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()

            # Check for errors in logs
            if 'ERROR' in log_content or 'Exception' in log_content:
                print("[WARN] Errors found in log file:")
                for line in log_content.split('\n'):
                    if 'ERROR' in line or 'Exception' in line:
                        print(f"  {line}")
                return False
            else:
                print("[OK] No errors in log file")

            # Show last 10 lines of log
            lines = log_content.split('\n')
            print("\nLast 10 log lines:")
            for line in lines[-10:]:
                if line.strip():
                    print(f"  {line}")
        else:
            print(f"[FAIL] No log file found for session {session_id}")
            return False

        print(f"\n{'='*70}")
        print("[SUCCESS] Time tool E2E test passed")
        print(f"{'='*70}")
        return True

    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup
        if session_id:
            print("\nCleaning up...")
            try:
                requests.delete(f'{BACKEND_URL}/api/sessions/{session_id}', timeout=5)
                print("[OK] Session cleaned up")
            except:
                pass

if __name__ == '__main__':
    success = test_time_tool()
    sys.exit(0 if success else 1)
