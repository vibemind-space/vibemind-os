#!/usr/bin/env python3
"""Run all E2E tests for MCP tools and generate report"""
import subprocess
import json
import time
from datetime import datetime
import os

# Test configurations for each MCP tool
TEST_CONFIGS = {
    'time': {
        'task': 'Get the current time in UTC and convert it to PST timezone',
        'timeout': 30,
        'requires_credentials': False
    },
    'github': {
        'task': 'List the 3 most recent issues in the microsoft/vscode repository',
        'timeout': 60,
        'requires_credentials': True,
        'env_var': 'GITHUB_PERSONAL_ACCESS_TOKEN'
    },
    'playwright': {
        'task': 'Navigate to https://example.com and get the page title',
        'timeout': 60,
        'requires_credentials': False
    },
    'fetch': {
        'task': 'Fetch the content from https://example.com',
        'timeout': 30,
        'requires_credentials': False
    },
    'memory': {
        'task': 'Create an entity named "TestEntity" with type "test" and observation "This is a test"',
        'timeout': 30,
        'requires_credentials': False
    },
    'filesystem': {
        'task': 'List files in the current directory',
        'timeout': 30,
        'requires_credentials': False
    },
    'taskmanager': {
        'task': 'Create a new task named "Test Task" with description "E2E test task"',
        'timeout': 30,
        'requires_credentials': False
    },
    'windows-core': {
        'task': 'Get system information including OS version and hostname',
        'timeout': 30,
        'requires_credentials': False
    },
    'docker': {
        'task': 'List all Docker containers',
        'timeout': 45,
        'requires_credentials': False
    },
    'desktop': {
        'task': 'List files in the current directory',
        'timeout': 30,
        'requires_credentials': False
    }
}

BACKEND_URL = 'http://127.0.0.1:8765'

def run_generic_e2e_test(tool, config):
    """Run E2E test for a specific tool"""
    import requests

    print(f"\n{'='*70}")
    print(f"Testing: {tool.upper()}")
    print(f"Task: {config['task']}")
    print(f"{'='*70}\n")

    # Check credentials if required
    if config.get('requires_credentials'):
        env_var = config.get('env_var')
        if env_var and not os.environ.get(env_var):
            print(f"[SKIP] {env_var} not configured")
            return {'status': 'skipped', 'reason': f'{env_var} not configured'}

    session_id = None
    result = {
        'tool': tool,
        'status': 'unknown',
        'duration': 0,
        'errors': [],
        'log_file': None
    }

    start_time = time.time()

    try:
        # Create session
        print("[1/4] Creating session...")
        resp = requests.post(f'{BACKEND_URL}/api/sessions',
            json={'tool': tool, 'name': f'e2e-test-{tool}'},
            timeout=5)

        if resp.status_code != 200:
            result['status'] = 'failed'
            result['errors'].append(f'Session creation failed: {resp.status_code}')
            return result

        data = resp.json()
        session_id = data.get('session_id')
        print(f"[OK] Session: {session_id}")

        # Start agent
        print("[2/4] Starting agent...")
        resp = requests.post(f'{BACKEND_URL}/api/sessions/{session_id}/start',
            json={'task': config['task']},
            timeout=10)

        if resp.status_code != 200:
            result['status'] = 'failed'
            result['errors'].append(f'Agent start failed: {resp.status_code}')
            return result

        print("[OK] Agent started")

        # Monitor execution
        print("[3/4] Monitoring...")
        max_wait = config.get('timeout', 30)
        for i in range(max_wait):
            time.sleep(1)
            resp = requests.get(f'{BACKEND_URL}/api/sessions/{session_id}', timeout=5)

            if resp.status_code == 200:
                session_data = resp.json()
                status = session_data.get('status', 'unknown')
                print(f"  [{i+1}s] Status: {status}", end='\r')

                if status in ['completed', 'error']:
                    print(f"\n[OK] Finished: {status}")
                    break

        # Check logs
        print("\n[4/4] Checking logs...")
        log_dir = '../../../../data/logs/sessions'
        log_files = [f for f in os.listdir(log_dir) if f.startswith(f'{tool}_') and session_id in f]

        if log_files:
            log_file = os.path.join(log_dir, log_files[0])
            result['log_file'] = log_files[0]
            print(f"[OK] Log: {log_files[0]}")

            # Analyze log
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()

            # Check for errors
            for line in log_content.split('\n'):
                if any(keyword in line for keyword in ['ERROR', 'Traceback', 'Exception']):
                    if 'spawn_agent' not in line.lower() and 'deprecated' not in line.lower():
                        result['errors'].append(line.strip())

            if result['errors']:
                result['status'] = 'failed_with_errors'
                print(f"[WARN] {len(result['errors'])} errors found")
            else:
                result['status'] = 'success'
                print("[OK] No errors")
        else:
            result['status'] = 'failed'
            result['errors'].append('No log file created')

        result['duration'] = time.time() - start_time
        return result

    except Exception as e:
        result['status'] = 'exception'
        result['errors'].append(str(e))
        result['duration'] = time.time() - start_time
        return result

    finally:
        if session_id:
            try:
                requests.delete(f'{BACKEND_URL}/api/sessions/{session_id}', timeout=5)
            except:
                pass

def main():
    """Run all E2E tests"""
    print(f"\n{'#'*70}")
    print("MCP TOOLS E2E TEST SUITE")
    print(f"{'#'*70}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tools to test: {len(TEST_CONFIGS)}")
    print(f"{'#'*70}\n")

    results = []

    for tool, config in TEST_CONFIGS.items():
        result = run_generic_e2e_test(tool, config)
        results.append(result)
        time.sleep(2)  # Brief pause between tests

    # Generate report
    print(f"\n\n{'#'*70}")
    print("TEST RESULTS SUMMARY")
    print(f"{'#'*70}\n")

    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] in ['failed', 'failed_with_errors', 'exception'])
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')

    print(f"Total: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Skipped: {skipped_count}")
    print()

    # Detailed results
    for result in results:
        status_icon = {
            'success': '[PASS]',
            'failed': '[FAIL]',
            'failed_with_errors': '[FAIL]',
            'exception': '[ERROR]',
            'skipped': '[SKIP]'
        }.get(result['status'], '[?]')

        duration = f"{result['duration']:.1f}s" if result['duration'] > 0 else "N/A"
        print(f"{status_icon} {result['tool']:20s} ({duration})")

        if result['errors'] and result['status'] != 'skipped':
            print(f"  Errors: {len(result['errors'])}")
            for err in result['errors'][:3]:  # Show first 3 errors
                print(f"    - {err[:100]}")

    # Save JSON report
    report_file = f"../../../../data/test_results/e2e_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs(os.path.dirname(report_file), exist_ok=True)

    with open(report_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total': len(results),
            'success': success_count,
            'failed': failed_count,
            'skipped': skipped_count,
            'results': results
        }, f, indent=2)

    print(f"\nReport saved: {report_file}")
    print(f"\n{'#'*70}\n")

    return 0 if failed_count == 0 else 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
