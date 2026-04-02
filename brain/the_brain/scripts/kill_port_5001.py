"""Kill all processes listening on port 5001"""
import subprocess
import re

# Get all processes on port 5001
result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
lines = result.stdout.split('\n')

pids = set()
for line in lines:
    if ':5001' in line and 'LISTENING' in line or 'ABH' in line:  # ABH is German for LISTENING
        parts = line.split()
        if parts:
            pid = parts[-1]
            if pid.isdigit():
                pids.add(pid)

print(f"Found {len(pids)} processes on port 5001")
for pid in pids:
    print(f"Killing PID {pid}...")
    try:
        subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
        print(f"  Killed {pid}")
    except Exception as e:
        print(f"  Failed to kill {pid}: {e}")

print("\nDone! Port 5001 should now be clear.")
