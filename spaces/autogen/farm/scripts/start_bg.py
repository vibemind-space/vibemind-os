#!/usr/bin/env python3
"""Start auto_answer.py and the pipeline as detached background processes."""
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Start auto-answerer
p1 = subprocess.Popen(
    [sys.executable, "-u", "auto_answer.py"],
    stdout=open("output/auto_answer.log", "w"),
    stderr=subprocess.STDOUT,
    creationflags=0x00000008 | 0x00000200,
)
print(f"Auto-answerer PID: {p1.pid}")

# Start pipeline
p2 = subprocess.Popen(
    [sys.executable, "-u", "minibook/autogen_swarm.py",
     "Build AI sales organization from input.md and image.png"],
    stdout=open("output/pipeline_run_v2.log", "w"),
    stderr=subprocess.STDOUT,
    creationflags=0x00000008 | 0x00000200,
)
print(f"Pipeline PID: {p2.pid}")

# Write PIDs to file for later reference
with open("output/pids.txt", "w") as f:
    f.write(f"auto_answer={p1.pid}\npipeline={p2.pid}\n")

print("Both processes started. Check output/auto_answer.log and output/pipeline_run_v2.log")
