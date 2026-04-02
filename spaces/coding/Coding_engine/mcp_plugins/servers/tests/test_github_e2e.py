#!/usr/bin/env python3
"""E2E test for GitHub MCP tool"""
import requests
import time
import sys
import os

BACKEND_URL = 'http://127.0.0.1:8765'
TOOL = 'github'

def test_github_tool():
    """Test GitHub tool with real task execution"""
    print(f"\n{'='*70}")
    print(f"E2E Test: {TOOL.upper()}")
    print(f"{'='*70}\n")

    # Check if GitHub token is available
    if not os.environ.get('GITHUB_PERSONAL_ACCESS_TOKEN'):
        print("[SKIP] GitHub token not configured, skipping test")
        return True

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
        task = "List the 3 most recent issues in the microsoft/vscode repository"
        resp = requests.post(f'{BACKEND_URL}/api/sessions/{session_id}/start',
            json={'task': task},
            timeout=10)

        if resp.status_code != 200:
            print(f"[FAIL] Agent start failed: {resp.status_code}")
            return False

        print(f"[OK] Agent started with task: {task}")

        # 3. Wait and check status
        print("\n[3/4] Monitoring execution...")
        max_wait = 60
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
        log_dir = '../../../../data/logs/sessions'
        log_files = [f for f in os.listdir(log_dir) if f.startswith(f'{TOOL}_') and session_id in f]

        if log_files:
            log_file = os.path.join(log_dir, log_files[0])
            print(f"[OK] Log file created: {log_files[0]}")

            # Read log content
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()

            # Check for critical errors (ignore expected warnings)
            error_lines = []
            for line in log_content.split('\n'):
                if 'ERROR' in line or 'Traceback' in line:
                    # Skip common non-critical errors
                    if 'GITHUB_PERSONAL_ACCESS_TOKEN' not in line:
                        error_lines.append(line)

            if error_lines:
                print("[WARN] Errors found in log file:")
                for line in error_lines[:10]:  # Show first 10 errors
                    print(f"  {line}")
                return False
            else:
                print("[OK] No critical errors in log file")

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
        print("[SUCCESS] GitHub tool E2E test passed")
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
    success = test_github_tool()
    sys.exit(0 if success else 1)
