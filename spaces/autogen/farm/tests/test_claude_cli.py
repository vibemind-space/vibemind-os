import subprocess, os
env = dict(os.environ)
env.pop("CLAUDECODE", None)
with open("test_claude_output.txt", "w") as f:
    r = subprocess.run(
        "claude.cmd -p hi --output-format text",
        shell=True, capture_output=True, text=True, timeout=60, env=env
    )
    f.write(f"RC: {r.returncode}\n")
    f.write(f"OUT: {repr(r.stdout[:300])}\n")
    f.write(f"ERR: {repr(r.stderr[:300])}\n")
