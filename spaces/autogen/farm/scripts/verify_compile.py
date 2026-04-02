#!/usr/bin/env python3
import py_compile
import sys

files = [
    "minibook/swarm/docker_ops.py",
    "minibook/swarm/input_parser.py",
    "minibook/swarm/pipeline.py",
    "minibook/swarm/todo_implementer.py",
]
ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"  OK  {f}")
    except py_compile.PyCompileError as e:
        print(f"  FAIL {f}: {e}")
        ok = False

if ok:
    print("\nAll files compile OK")
else:
    print("\nCOMPILATION ERRORS FOUND")
    sys.exit(1)
