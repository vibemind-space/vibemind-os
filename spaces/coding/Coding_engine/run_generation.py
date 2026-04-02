#!/usr/bin/env python3
"""
Standalone generation subprocess.

Runs EpicOrchestrator in its own process with its own event loop.
Called by the API via subprocess.Popen — does NOT share the uvicorn event loop.

Usage:
    python run_generation.py --project-path /app/Data/all_services/whatsapp-... --output-dir /app/output/whatsapp-...
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_plugins", "servers", "grpc_host"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_generation")


async def run(args):
    from epic_orchestrator import EpicOrchestrator

    project_path = args.project_path
    output_dir = args.output_dir
    project_id = args.project_id or Path(project_path).name

    # Set project-specific DATABASE_URL if db_schema provided
    if args.db_schema:
        db_host = os.environ.get("DB_HOST", "postgres")
        db_user = os.environ.get("DB_USER", "postgres")
        db_pass = os.environ.get("DB_PASS", "postgres")
        db_url = "postgresql://%s:%s@%s:5432/%s?schema=public" % (db_user, db_pass, db_host, args.db_schema)
        os.environ["DATABASE_URL"] = db_url
        logger.info("Using project DB: %s", args.db_schema)

        # Auto-create database if not exists
        try:
            import subprocess as _sp
            _sp.run(
                ["psql", "-U", db_user, "-h", db_host, "-tc",
                 "SELECT 1 FROM pg_database WHERE datname='%s'" % args.db_schema],
                capture_output=True, text=True, timeout=5,
            )
            _sp.run(
                ["psql", "-U", db_user, "-h", db_host, "-c",
                 "CREATE DATABASE %s" % args.db_schema],
                capture_output=True, text=True, timeout=5,
            )
            logger.info("Database '%s' ensured", args.db_schema)
        except Exception as e:
            logger.warning("DB create check failed (may already exist): %s", e)

    # Load SoM bridge config
    som_config = {}
    config_path = Path(__file__).parent / "config" / "society_defaults.json"
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            som_config = raw.get("som_bridge", {})
            som_config["vnc_port"] = args.vnc_port
            som_config["app_port"] = args.app_port
        except Exception:
            pass

    # Create output dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Auto-init git repo in output dir (needed for PR creation)
    if not (Path(output_dir) / ".git").exists():
        import subprocess as _sp
        logger.info("Initializing git repo in %s", output_dir)
        _sp.run(["git", "init"], cwd=output_dir, capture_output=True)
        _sp.run(["git", "config", "user.name", "Coding Engine"], cwd=output_dir, capture_output=True)
        _sp.run(["git", "config", "user.email", "engine@davefelix.dev"], cwd=output_dir, capture_output=True)
        gitignore = Path(output_dir) / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("node_modules/\ndist/\n.cache/\n*.log\n.env\n")
        _sp.run(["git", "add", ".gitignore"], cwd=output_dir, capture_output=True)
        _sp.run(["git", "commit", "-m", "initial scaffold", "--allow-empty"], cwd=output_dir, capture_output=True)

    # Write lock file
    lock_file = Path(output_dir) / ".generation_running"
    lock_file.write_text(json.dumps({
        "project_id": project_id,
        "started_at": time.time(),
        "pid": os.getpid(),
    }))

    logger.info("Starting generation: project=%s output=%s", project_path, output_dir)
    start_time = time.time()

    skip_task_gen = getattr(args, 'skip_task_gen', False)

    orchestrator = EpicOrchestrator(
        project_path=project_path,
        output_dir=output_dir,
        event_bus=None,  # No shared event bus — we're in our own process
        max_parallel_tasks=args.parallelism,
        enable_som=True,
        som_config=som_config,
        skip_task_gen=skip_task_gen,
    )

    # Find all epics
    tasks_dir = Path(project_path) / "tasks"
    epic_files = sorted(tasks_dir.glob("epic-*-tasks.json"))
    if not epic_files:
        logger.error("No epic task files found in %s", tasks_dir)
        sys.exit(1)

    epic_ids = []
    for f in epic_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        eid = data.get("epic_id", f.stem.replace("-tasks", ""))
        epic_ids.append(eid)

    logger.info("Found %d epics: %s", len(epic_ids), epic_ids)

    # ── Worker Pool: Run N epics concurrently, not all at once ──
    num_workers = min(args.parallelism, len(epic_ids))
    logger.info("Worker pool: %d workers for %d epics", num_workers, len(epic_ids))

    total_completed = 0
    total_failed = 0
    all_task_results = []
    results_lock = asyncio.Lock()

    epic_queue = asyncio.Queue()
    for eid in epic_ids:
        await epic_queue.put(eid)

    async def worker(worker_id: int):
        nonlocal total_completed, total_failed
        while True:
            try:
                epic_id = epic_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            logger.info("Worker-%d: === Running %s ===", worker_id, epic_id)
            try:
                result = await orchestrator.run_epic(epic_id)

                async with results_lock:
                    total_completed += result.completed_tasks
                    total_failed += result.failed_tasks

                logger.info(
                    "Worker-%d: %s done: %d completed, %d failed",
                    worker_id, epic_id, result.completed_tasks, result.failed_tasks,
                )

                # Auto-fix failed tasks before next epic
                if result.failed_tasks > 0:
                    await _auto_fix_between_epics(output_dir, epic_id, result)

                # Export task statuses for DB sync
                try:
                    epic_results = []
                    if hasattr(orchestrator, '_last_task_list') and orchestrator._last_task_list:
                        for task in orchestrator._last_task_list.tasks:
                            epic_results.append({
                                "task_id": task.id,
                                "epic_id": epic_id,
                                "status": task.status,
                                "error_message": task.error_message or "",
                                "output_files": getattr(task, 'output_files', []) or [],
                                "retry_count": getattr(task, 'retry_count', 0),
                            })
                    else:
                        enriched = Path(project_path) / "tasks" / f"{epic_id.lower()}-tasks-enriched.json"
                        if enriched.exists():
                            edata = json.loads(enriched.read_text(encoding="utf-8"))
                            tasks = edata.get("tasks", [])
                            for t in tasks:
                                tid = t.get("id", t.get("task_id", ""))
                                epic_results.append({
                                    "task_id": tid,
                                    "epic_id": epic_id,
                                    "status": "completed" if result.success else "failed",
                                    "error_message": "",
                                    "output_files": [],
                                    "retry_count": 0,
                                })
                    async with results_lock:
                        all_task_results.extend(epic_results)
                except Exception as te:
                    logger.warning("Worker-%d: Could not export task status for %s: %s", worker_id, epic_id, te)

            except Exception as e:
                logger.error("Worker-%d: %s failed: %s", worker_id, epic_id, e)
                async with results_lock:
                    total_failed += 1

    # Start worker pool
    workers = [asyncio.create_task(worker(i)) for i in range(num_workers)]
    await asyncio.gather(*workers)

    elapsed = time.time() - start_time
    logger.info(
        "Generation complete: %d completed, %d failed, %.1fs elapsed",
        total_completed, total_failed, elapsed,
    )

    # Write task-level status for DB sync
    task_status_file = Path(output_dir) / ".task_results.json"
    task_status_file.write_text(json.dumps(all_task_results, indent=2))
    logger.info("Wrote %d task results to %s", len(all_task_results), task_status_file)

    # Write status file for API to read
    status_file = Path(output_dir) / ".generation_status.json"
    status_file.write_text(json.dumps({
        "status": "completed" if total_failed == 0 else "completed_with_errors",
        "completed": total_completed,
        "failed": total_failed,
        "elapsed_seconds": round(elapsed, 1),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task_results_file": str(task_status_file),
    }, indent=2))

    # ── Post-Generation Fixes ──────────────────────────────────────────
    # Automatically fix common NestJS/React issues in the generated project
    try:
        from src.postgen.fix_nestjs_project import fix_nestjs_project
        logger.info("Running post-generation fixes on %s ...", output_dir)
        postgen_result = fix_nestjs_project(output_dir)
        fixes = postgen_result.get("fixes_applied", [])
        ts_errs = postgen_result.get("ts_errors", -1)
        vite_errs = postgen_result.get("vite_errors", -1)
        logger.info(
            "Post-gen complete: %d fixes applied, %d TS errors, %d Vite errors",
            len(fixes), ts_errs, vite_errs,
        )
        for fix in fixes:
            logger.info("  [postgen] %s", fix)
    except Exception as postgen_err:
        logger.warning("Post-generation fixes failed: %s", postgen_err)

    # Remove lock file
    lock_file = Path(output_dir) / ".generation_running"
    lock_file.unlink(missing_ok=True)
    logger.info("Lock file removed")

    # Auto-sync to DB via API (fire and forget)
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/dashboard/sync-tasks",
            data=json.dumps({"output_dir": output_dir}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("DB sync triggered via API")
    except Exception as se:
        logger.warning("DB sync API call failed (manual sync needed): %s", se)

    # Notify API that generation is complete (cleanup _active_generations)
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/dashboard/generation-complete",
            data=json.dumps({"project_id": project_id}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Generation-complete notification sent for %s", project_id)
    except Exception:
        pass


async def _auto_fix_between_epics(output_dir: str, epic_id: str, result):
    """Auto-fix common failures between epics so subsequent tasks don't get cancelled."""
    import subprocess as _sp
    import re as _re

    logger.info("Auto-fix: checking %d failed tasks from %s", result.failed_tasks, epic_id)

    output_path = Path(output_dir)
    schema_path = output_path / "prisma" / "schema.prisma"
    root_schema = output_path / "schema.prisma"

    # ── 1. Fix Prisma Migrations ──
    # If any migration tasks failed, try prisma db push
    if schema_path.exists() or root_schema.exists():
        # Copy root schema to prisma/ if needed
        if root_schema.exists() and not schema_path.exists():
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(root_schema, schema_path)

        db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/coding_engine?schema=public")

        for attempt in range(1, 4):
            logger.info("Auto-fix: prisma db push attempt %d/3", attempt)
            env = os.environ.copy()
            env["DATABASE_URL"] = db_url

            try:
                proc = _sp.run(
                    ["npx", "prisma", "db", "push", "--accept-data-loss", "--skip-generate"],
                    cwd=str(output_path),
                    capture_output=True, text=True, timeout=60, env=env,
                )
                if proc.returncode == 0:
                    logger.info("Auto-fix: prisma db push SUCCESS")
                    # Also generate client
                    _sp.run(
                        ["npx", "prisma", "generate"],
                        cwd=str(output_path),
                        capture_output=True, text=True, timeout=60, env=env,
                    )
                    break
                else:
                    error = proc.stderr or proc.stdout
                    logger.warning("Auto-fix: prisma push failed: %s", error[:300])

                    # Try to fix schema via GPT
                    if attempt < 3:
                        fixed = await _gpt_fix_schema(schema_path, error)
                        if fixed:
                            logger.info("Auto-fix: GPT fixed schema, retrying...")
                        else:
                            logger.warning("Auto-fix: GPT could not fix schema")
                            break
            except Exception as e:
                logger.warning("Auto-fix: prisma error: %s", e)
                break

    # ── 2. Fix ESLint ──
    try:
        _sp.run(
            ["npx", "eslint", "--fix", "src/**/*.{ts,tsx}"],
            cwd=str(output_path),
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass

    # ── 3. Fix missing deps ──
    pkg_json = output_path / "package.json"
    if pkg_json.exists():
        try:
            _sp.run(
                ["npm", "install", "--legacy-peer-deps"],
                cwd=str(output_path),
                capture_output=True, text=True, timeout=120,
            )
        except Exception:
            pass

    # ── 4. TypeScript build check ──
    try:
        tsc_result = _sp.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(output_path),
            capture_output=True, text=True, timeout=60,
        )
        error_count = tsc_result.stdout.count("error TS") + tsc_result.stderr.count("error TS")
        if error_count > 0:
            logger.warning("Auto-fix: %d TypeScript errors after %s", error_count, epic_id)
        else:
            logger.info("Auto-fix: TypeScript clean after %s", epic_id)
    except Exception as e:
        logger.debug("Auto-fix: tsc check failed: %s", e)

    # ── 5. Run postgen fixes (modules, prisma imports, frontend routing) ──
    try:
        from src.postgen.fix_nestjs_project import fix_nestjs_project
        postgen = fix_nestjs_project(str(output_path))
        if postgen.get("fixes_applied"):
            logger.info("Auto-fix: postgen applied %d fixes after %s", len(postgen["fixes_applied"]), epic_id)
    except Exception as e:
        logger.debug("Auto-fix: postgen failed: %s", e)

    logger.info("Auto-fix: done for %s", epic_id)


async def _gpt_fix_schema(schema_path: Path, error: str) -> bool:
    """Use OpenAI to fix a broken Prisma schema."""
    import urllib.request

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return False

    schema = schema_path.read_text(encoding="utf-8", errors="replace")

    prompt = (
        "Fix this Prisma schema. The error is:\n%s\n\n"
        "Rules:\n"
        "- For self-referencing models, add named @relation with reverse fields\n"
        "- Every @relation(\"Name\", fields:...) needs a reverse field on the target model\n"
        "- Keep all existing models and fields\n"
        "- Output ONLY the complete fixed schema, no markdown fences\n\n"
        "Schema:\n%s"
    ) % (error[:500], schema[:6000])

    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps({
                "model": "gpt-4.1",
                "messages": [
                    {"role": "system", "content": "You are a Prisma schema expert. Output only valid schema code."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 8000,
                "temperature": 0.1,
            }).encode(),
            headers={
                "Authorization": "Bearer %s" % api_key,
                "Content-Type": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]

        # Strip markdown fences
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]

        schema_path.write_text(content.strip(), encoding="utf-8")
        return True
    except Exception as e:
        logger.warning("GPT schema fix failed: %s", e)
        return False


def main():
    parser = argparse.ArgumentParser(description="Run code generation as standalone process")
    parser.add_argument("--project-path", required=True, help="Path to project data directory")
    parser.add_argument("--output-dir", required=True, help="Path to write generated code")
    parser.add_argument("--project-id", default="", help="Project identifier for tracking")
    parser.add_argument("--db-schema", default="", help="Postgres database name for this project")
    parser.add_argument("--vnc-port", type=int, default=6090)
    parser.add_argument("--app-port", type=int, default=3100)
    parser.add_argument("--parallelism", type=int, default=1)
    parser.add_argument("--max-rounds", type=int, default=10, help="Max generation rounds (auto-restart loop)")
    parser.add_argument("--no-loop", action="store_true", help="Run once, no auto-restart")
    parser.add_argument("--skip-task-gen", action="store_true", help="Skip task generation, only execute existing tasks")
    args = parser.parse_args()

    if args.no_loop:
        asyncio.run(run(args))
        return

    # Auto-restart loop: run → fixall → run → fixall → ... until all done or max rounds
    max_rounds = args.max_rounds
    for round_num in range(1, max_rounds + 1):
        logger.info("=== GENERATION ROUND %d/%d ===", round_num, max_rounds)

        asyncio.run(run(args))

        # Read results to check progress
        task_status_file = Path(args.output_dir) / ".task_results.json"
        if task_status_file.exists():
            results = json.loads(task_status_file.read_text())
            completed = sum(1 for t in results if t.get("status") == "completed")
            failed = sum(1 for t in results if t.get("status") == "failed")
            skipped = sum(1 for t in results if t.get("status") == "skipped")
            pending = sum(1 for t in results if t.get("status") == "pending")
            total = len(results)

            logger.info(
                "Round %d result: %d/%d completed, %d failed, %d skipped, %d pending",
                round_num, completed, total, failed, skipped, pending,
            )

            # All done?
            if completed + failed >= total or (skipped == 0 and pending == 0):
                logger.info("All tasks processed — generation loop complete!")
                break

            # No new progress? (same completed count as before)
            prev_status_file = Path(args.output_dir) / ".prev_round_completed"
            prev_completed = 0
            if prev_status_file.exists():
                try:
                    prev_completed = int(prev_status_file.read_text().strip())
                except (ValueError, OSError):
                    prev_completed = 0

            if completed <= prev_completed and round_num > 1:
                logger.warning("No progress in round %d (still %d completed) — stopping loop", round_num, completed)
                break

            prev_status_file.write_text(str(completed))

            # Auto-fix failed tasks between rounds
            if failed > 0:
                logger.info("Auto-fixing %d failed tasks before next round...", failed)
                try:
                    import urllib.request
                    req = urllib.request.Request(
                        "http://127.0.0.1:8000/api/v1/dashboard/fixall",
                        data=json.dumps({"project_name": args.project_id}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    resp = urllib.request.urlopen(req, timeout=300)
                    fix_data = json.loads(resp.read())
                    logger.info("Fixall result: %s", json.dumps(fix_data)[:200])
                except Exception as fe:
                    logger.warning("Auto-fixall failed: %s", fe)

            # Delete cached task results so next round starts fresh
            task_status_file.unlink(missing_ok=True)

            # Brief pause between rounds
            logger.info("Waiting 10s before next round...")
            time.sleep(10)
        else:
            logger.warning("No task results file — stopping loop")
            break

    logger.info("=== GENERATION LOOP FINISHED after %d rounds ===", round_num)


if __name__ == "__main__":
    main()
