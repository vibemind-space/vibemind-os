#!/usr/bin/env python3
"""
rerun.py — Re-run an existing core_vX agent team with updated framework code.

Usage:
  python rerun.py output/core_v57              # rerun + eval
  python rerun.py output/core_v57 --no-eval    # rerun only, no eval

This is faster than regenerating from scratch:
- Reuses the existing YAML/agent structure
- Updates main.py with the latest GENERIC_MAIN_PY template
- Updates claude_code in tools.py with the new OpenAI-API version
- Rebuilds Docker and reruns
"""
import asyncio
import re
import sys
import shutil
import time
from pathlib import Path

# Allow importing from minibook/swarm
sys.path.insert(0, str(Path(__file__).parent))

from minibook.swarm.knowledge import GENERIC_MAIN_PY
from minibook.swarm.pipeline import _fix_truncated_tools_py
from minibook.swarm.docker_ops import (
    docker_build_test,
    docker_run_test,
    docker_run_test_with_args,
)
from minibook.swarm.llm import call_gpt4o_json


async def main():
    if len(sys.argv) < 2:
        print("Usage: python rerun.py output/core_vX [--no-eval]")
        sys.exit(1)

    source_dir = Path(sys.argv[1])
    do_eval = "--no-eval" not in sys.argv

    if not source_dir.exists():
        print(f"ERROR: {source_dir} does not exist")
        sys.exit(1)

    src_dir = source_dir / "src"
    main_py = src_dir / "main.py"
    tools_py = src_dir / "tools.py"

    print(f"\n{'='*60}")
    print(f"  RERUN: {source_dir.name}")
    print(f"{'='*60}\n")

    # 1. Update main.py with current GENERIC_MAIN_PY
    if main_py.exists():
        print(f"[Rerun] Updating main.py with latest framework code...")
        main_py.write_text(GENERIC_MAIN_PY, encoding="utf-8")
        print(f"[Rerun] main.py updated ({len(GENERIC_MAIN_PY)} chars)")
    else:
        print(f"[Rerun] WARNING: main.py not found at {main_py}")

    # 2. Update claude_code in tools.py
    if tools_py.exists():
        print(f"[Rerun] Updating claude_code in tools.py...")
        code = tools_py.read_text(encoding="utf-8")
        fixed = _fix_truncated_tools_py(code)
        if fixed != code:
            tools_py.write_text(fixed, encoding="utf-8")
            print(f"[Rerun] tools.py claude_code updated")
        else:
            print(f"[Rerun] tools.py claude_code already up to date")
    else:
        print(f"[Rerun] WARNING: tools.py not found at {tools_py}")

    # 3. Build Docker
    print(f"\n[Rerun] Preparing Docker context...")
    import tempfile, os
    build_dir = Path(tempfile.mkdtemp(prefix="rerun_"))

    # Copy all source files to temp build dir (except old output)
    for item in source_dir.iterdir():
        if item.name in ("output", "output_rerun"):
            continue  # skip old output
        dest = build_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Overwrite with updated main.py and tools.py
    (build_dir / "src" / "main.py").write_text(GENERIC_MAIN_PY, encoding="utf-8")
    if tools_py.exists():
        shutil.copy2(tools_py, build_dir / "src" / "tools.py")

    # Create clean output dir
    (build_dir / "output").mkdir(exist_ok=True)

    print(f"[Rerun] Build dir: {build_dir}")
    print(f"[Rerun] Building Docker image...")
    start = time.time()

    build_result = await docker_build_test(build_dir)
    if build_result["status"] != "PASS":
        print(f"[Rerun] BUILD FAILED:\n{build_result['logs'][-2000:]}")
        sys.exit(1)
    print(f"[Rerun] Build PASS ({time.time()-start:.1f}s)")

    # 4. Run agent team
    print(f"\n[Rerun] Running agent team (timeout=900s)...")
    run_start = time.time()
    run_result = await docker_run_test(build_dir, timeout=900)
    duration = time.time() - run_start
    print(f"[Rerun] Run {run_result['status']} ({duration:.1f}s)")

    # Show output files
    output_dir = build_dir / "output"
    output_files = {}
    if output_dir.exists():
        for f in output_dir.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".txt", ".json"):
                content = f.read_text(encoding="utf-8", errors="replace")
                output_files[f.name] = content
                print(f"  - {f.name} ({len(content)} chars)")

    if not output_files:
        print(f"[Rerun] No output files produced!")
        if not do_eval:
            sys.exit(0)

    # 5. Evaluate output (optional)
    if do_eval and output_files:
        print(f"\n[Rerun] Evaluating output quality...")
        files_summary = "\n".join(
            f"- {name}: {content[:500]}" for name, content in list(output_files.items())[:6]
        )
        result = await call_gpt4o_json(
            "You are an expert evaluator. Score the agent team output.",
            f"Output files:\n{files_summary}\n\n"
            f"Score 1-10 based on: completeness, content quality, file count.\n"
            f"Return JSON: {{\"score\": N, \"verdict\": \"PASS|FAIL\", \"summary\": \"...\"}}"
        )
        score = result.get("score", 0)
        verdict = result.get("verdict", "FAIL")
        summary = result.get("summary", "")
        print(f"\n[Rerun] Eval: {verdict} (Score: {score}/10)")
        print(f"[Rerun] {summary}")

    # Copy output to source_dir/output_rerun/
    rerun_output = source_dir / "output_rerun"
    if rerun_output.exists():
        shutil.rmtree(rerun_output)
    shutil.copytree(output_dir, rerun_output)
    print(f"\n[Rerun] Output saved to: {rerun_output}")

    # Cleanup
    shutil.rmtree(build_dir, ignore_errors=True)
    print(f"[Rerun] Done!")


if __name__ == "__main__":
    asyncio.run(main())
