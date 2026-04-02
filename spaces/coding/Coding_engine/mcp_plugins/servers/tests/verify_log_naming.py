#!/usr/bin/env python3
"""Quick verification that log naming format is correct"""
import os
import re
from datetime import datetime

def verify_log_naming():
    """Check all session logs have correct naming format"""
    log_dir = '../../../../data/logs/sessions'

    if not os.path.exists(log_dir):
        print(f"[ERROR] Log directory not found: {log_dir}")
        return False

    log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]

    print(f"\n{'='*70}")
    print("SESSION LOG NAMING VERIFICATION")
    print(f"{'='*70}\n")
    print(f"Log directory: {log_dir}")
    print(f"Total log files: {len(log_files)}\n")

    # Expected format: {tool}_{timestamp}_{session_id}.log
    # Example: time_20251008_221258_Cjf-zpPjf4h2HpkIu-1Gog.log
    pattern = re.compile(r'^([a-z0-9-]+)_(\d{8}_\d{6})_([A-Za-z0-9_-]+)\.log$')

    correct_format = []
    old_format = []

    for f in sorted(log_files):
        match = pattern.match(f)
        if match:
            tool, timestamp, session_id = match.groups()
            correct_format.append({
                'file': f,
                'tool': tool,
                'timestamp': timestamp,
                'session_id': session_id
            })
            print(f"[OK] {f}")
            print(f"     Tool: {tool}, Time: {timestamp}, Session: {session_id}")
        else:
            old_format.append(f)
            print(f"[OLD FORMAT] {f}")

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}\n")
    print(f"Correct format: {len(correct_format)}")
    print(f"Old format: {len(old_format)}")

    if correct_format:
        print(f"\nTools with correct log naming:")
        tools = sorted(set(log['tool'] for log in correct_format))
        for tool in tools:
            count = sum(1 for log in correct_format if log['tool'] == tool)
            print(f"  - {tool:20s} ({count} logs)")

    if old_format:
        print(f"\n[WARN] {len(old_format)} files still use old format")

    print(f"\n{'='*70}\n")

    return len(old_format) == 0

if __name__ == '__main__':
    import sys
    success = verify_log_naming()
    sys.exit(0 if success else 1)
