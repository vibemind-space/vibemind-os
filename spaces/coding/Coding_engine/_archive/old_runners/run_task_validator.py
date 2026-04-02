# -*- coding: utf-8 -*-
"""
CLI entry point for the Task Validator.

Reads failed/skipped tasks from an epic task JSON file and uses the
MCP Orchestrator + Claude CLI to fix them automatically.

Usage:
    python run_task_validator.py                        # Run fix loop
    python run_task_validator.py --dry-run               # Show plan only
    python run_task_validator.py --task-file <path>       # Custom task file
    python run_task_validator.py --max-iterations 5       # More retries
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))


def find_latest_task_file() -> str:
    """Find the most recent epic-*-tasks.json in Data/."""
    data_dir = Path("Data/all_services")
    if not data_dir.exists():
        return ""

    candidates = []
    for project_dir in data_dir.iterdir():
        if not project_dir.is_dir():
            continue
        tasks_dir = project_dir / "tasks"
        if tasks_dir.exists():
            for f in tasks_dir.glob("epic-*-tasks.json"):
                candidates.append(f)

    if not candidates:
        return ""

    # Return most recently modified
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0])


async def main():
    parser = argparse.ArgumentParser(description="Task Validator - Fix failed tasks via MCP")
    parser.add_argument(
        "--task-file",
        default=None,
        help="Path to epic-*-tasks.json (auto-detected if omitted)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Project output directory (default: output)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Max fix attempts per failed task (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    args = parser.parse_args()

    # Resolve task file
    task_file = args.task_file or find_latest_task_file()
    if not task_file:
        print("Error: No task file found. Use --task-file to specify one.")
        sys.exit(1)

    print(f"Task file: {task_file}")
    print(f"Output dir: {args.output_dir}")
    print()

    from src.tools.task_validator import TaskValidator

    validator = TaskValidator(
        task_file=task_file,
        output_dir=args.output_dir,
    )

    summary_before = validator.get_summary()
    print("Before:")
    for status, count in sorted(summary_before.items()):
        print(f"  {status}: {count}")
    print()

    # Show failed tasks
    failed = validator.get_failed_tasks()
    if not failed:
        print("No failed tasks - nothing to fix!")
        return

    print(f"Failed tasks ({len(failed)}):")
    for t in failed:
        blocked = validator.get_blocked_by(t["id"])
        print(f"  [{t['id']}] {t.get('title', '')}")
        print(f"    Error: {(t.get('error_message') or '')[:120]}")
        print(f"    Blocks: {len(blocked)} downstream tasks")
    print()

    # Run
    result = await validator.run_fix_loop(
        max_iterations=args.max_iterations,
        dry_run=args.dry_run,
    )

    # Print result
    if args.dry_run:
        print("=== DRY RUN PLAN ===")
        for plan_item in result.get("failed_tasks", []):
            print(f"\n  [{plan_item['task_id']}] {plan_item['title']}")
            print(f"    Type: {plan_item['type']}")
            print(f"    Error: {plan_item['error'][:100]}")
            print(f"    Fix strategy: {plan_item['fix_strategy']}")
            print(f"    Has fixer: {plan_item['has_fixer']}")
            print(f"    Blocks: {plan_item['blocks_count']} tasks")
        print(f"\n  Total blocked tasks: {result['total_blocked']}")
    else:
        print("=== RESULTS ===")
        print(f"Tasks attempted: {result['tasks_attempted']}")
        print(f"Tasks fixed: {result['tasks_fixed']}")
        print()

        for r in result.get("results", []):
            status = "FIXED" if r["fixed"] else "FAILED"
            print(f"  [{status}] {r['task_id']} ({r['iterations']} iterations)")
            if r["errors"]:
                for err in r["errors"][-1:]:  # show last error
                    print(f"    Last error: {str(err)[:120]}")
        print()

        print("After:")
        for status, count in sorted(result["after"].items()):
            print(f"  {status}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
