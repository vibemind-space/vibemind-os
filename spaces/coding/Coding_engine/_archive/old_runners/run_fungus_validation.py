#!/usr/bin/env python3
"""
Fungus MCMP Validation CLI - Phase 17

Runs autonomous MCMP validation against a project directory.
Indexes source files, runs swarm simulation, and reports validation findings.

Usage:
    # Dry-run against test project (report only)
    python run_fungus_validation.py --project-dir Data/all_services/unnamed_project_20260204_165411 --dry-run

    # With epic task context
    python run_fungus_validation.py --project-dir Data/all_services/unnamed_project_20260204_165411 \
        --task-file Data/all_services/unnamed_project_20260204_165411/tasks/epic-001-tasks.json \
        --max-rounds 3

    # With seed patterns
    python run_fungus_validation.py --project-dir ./output --seed-framework Hono --seed-orm Prisma

    # Write JSON report
    python run_fungus_validation.py --project-dir ./output --report-file validation_report.json
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load .env (OPENROUTER_API_KEY etc.)
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass


async def main():
    parser = argparse.ArgumentParser(
        description="Fungus MCMP Validation - Autonomous code validation via swarm simulation"
    )
    parser.add_argument(
        "--project-dir", required=True,
        help="Path to the project directory to validate",
    )
    parser.add_argument(
        "--task-file", default=None,
        help="Path to epic tasks JSON file for context",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=3,
        help="Maximum validation rounds (default: 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only, no event injection",
    )
    parser.add_argument(
        "--report-file", default=None,
        help="Write JSON report to this file",
    )
    parser.add_argument(
        "--seed-framework", default=None,
        help="Framework seed pattern (e.g., Hono, Express, FastAPI)",
    )
    parser.add_argument(
        "--seed-orm", default=None,
        help="ORM seed pattern (e.g., Prisma, SQLAlchemy, Drizzle)",
    )
    parser.add_argument(
        "--num-agents", type=int, default=100,
        help="Number of MCMP swarm agents (default: 100)",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=30,
        help="Max simulation iterations per round (default: 30)",
    )

    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    if not project_dir.exists():
        print(f"Error: Project directory not found: {project_dir}")
        sys.exit(1)

    print(f"{'='*70}")
    print(f"  Fungus MCMP Validation")
    print(f"  Project: {project_dir}")
    print(f"  Mode: {'dry-run' if args.dry_run else 'live'}")
    print(f"  Swarm: {args.num_agents} agents, {args.max_iterations} max iterations")
    print(f"{'='*70}\n")

    # Build seed patterns
    seed_patterns = {}
    if args.seed_framework:
        seed_patterns["framework"] = args.seed_framework
    if args.seed_orm:
        seed_patterns["orm"] = args.seed_orm

    # Auto-detect seed patterns from project files
    if not seed_patterns:
        seed_patterns = _auto_detect_patterns(project_dir)
        if seed_patterns:
            print(f"Auto-detected patterns: {seed_patterns}")

    # Load task context if provided
    task_queries = _build_queries_from_tasks(args.task_file) if args.task_file else None

    # Import after path setup
    from src.services.mcmp_background import SimulationConfig
    from src.services.fungus_validation_service import (
        FungusValidationService,
        ValidationJudgeMode,
    )

    config = SimulationConfig(
        num_agents=args.num_agents,
        max_iterations=args.max_iterations,
        judge_every=5,
        steering_every=5,
        enable_llm_steering=True,
    )

    service = FungusValidationService(
        working_dir=str(project_dir),
        event_bus=None,  # No event bus in CLI mode
        config=config,
        job_id="cli_validation",
    )

    # Start service
    print("Indexing project files...")
    started = await service.start(seed_patterns=seed_patterns)
    if not started:
        print("Error: Failed to start validation service (no files indexed?)")
        sys.exit(1)

    print(f"Indexed {service.indexed_count} files\n")

    # Build validation queries
    if task_queries:
        queries = task_queries
    else:
        queries = _default_validation_queries(project_dir)

    # Run validation rounds
    all_reports = []
    for i, (query, mode) in enumerate(queries[:args.max_rounds]):
        print(f"{'='*70}")
        print(f"  Round {i+1}/{min(len(queries), args.max_rounds)}")
        print(f"  Query: {query}")
        print(f"  Mode: {mode.value}")
        print(f"{'='*70}")

        start_time = time.time()
        report = await service.run_validation_round(
            focus_query=query,
            mode=mode,
        )
        elapsed = time.time() - start_time

        all_reports.append(report)

        # Print findings
        if report.findings:
            for j, finding in enumerate(report.findings):
                severity_icon = {
                    "error": "[ERROR]",
                    "warning": "[WARN]",
                    "info": "[INFO]",
                }.get(finding.severity, "[?]")

                print(f"\n  {severity_icon} {finding.finding_type}")
                print(f"    File: {finding.file_path}")
                if finding.related_files:
                    print(f"    Related: {', '.join(finding.related_files[:3])}")
                print(f"    Description: {finding.description}")
                if finding.suggested_fix:
                    print(f"    Fix: {finding.suggested_fix}")
                print(f"    Confidence: {finding.confidence:.2f}")
        else:
            print("\n  No findings in this round.")

        print(f"\n  Steps: {report.simulation_steps} | "
              f"Files: {report.files_analyzed} analyzed / {report.files_indexed} indexed | "
              f"Time: {elapsed:.1f}s")
        print()

    # Stop service
    await service.stop()

    # Summary
    total_findings = sum(len(r.findings) for r in all_reports)
    total_errors = sum(len([f for f in r.findings if f.severity == "error"]) for r in all_reports)
    total_warnings = sum(len([f for f in r.findings if f.severity == "warning"]) for r in all_reports)

    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Rounds: {len(all_reports)}")
    print(f"  Total findings: {total_findings}")
    print(f"  Errors: {total_errors}")
    print(f"  Warnings: {total_warnings}")
    print(f"  Files indexed: {service.indexed_count}")
    print(f"{'='*70}")

    # Write report if requested
    if args.report_file:
        report_data = {
            "project_dir": str(project_dir),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "seed_patterns": seed_patterns,
            "config": {
                "num_agents": args.num_agents,
                "max_iterations": args.max_iterations,
            },
            "rounds": [
                {
                    "round": r.round_number,
                    "focus_query": r.focus_query,
                    "files_analyzed": r.files_analyzed,
                    "files_indexed": r.files_indexed,
                    "simulation_steps": r.simulation_steps,
                    "judge_confidence": r.judge_confidence,
                    "findings": [
                        {
                            "finding_type": f.finding_type,
                            "severity": f.severity,
                            "file_path": f.file_path,
                            "related_files": f.related_files,
                            "description": f.description,
                            "suggested_fix": f.suggested_fix,
                            "confidence": f.confidence,
                        }
                        for f in r.findings
                    ],
                }
                for r in all_reports
            ],
            "summary": {
                "total_findings": total_findings,
                "errors": total_errors,
                "warnings": total_warnings,
                "files_indexed": service.indexed_count,
            },
        }

        report_path = Path(args.report_file)
        report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReport written to: {report_path}")


def _auto_detect_patterns(project_dir: Path) -> dict:
    """Auto-detect framework and ORM patterns from project files."""
    patterns = {}

    # Check package.json for framework
    pkg_json = project_dir / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            # Framework detection
            if "hono" in deps:
                patterns["framework"] = "Hono"
            elif "express" in deps:
                patterns["framework"] = "Express"
            elif "next" in deps:
                patterns["framework"] = "Next.js"
            elif "@nestjs/core" in deps:
                patterns["framework"] = "NestJS"

            # ORM detection
            if "@prisma/client" in deps or "prisma" in deps:
                patterns["orm"] = "Prisma"
            elif "drizzle-orm" in deps:
                patterns["orm"] = "Drizzle"
            elif "typeorm" in deps:
                patterns["orm"] = "TypeORM"

            # Auth detection
            if "jose" in deps:
                patterns["auth"] = "JWT (jose)"
            elif "jsonwebtoken" in deps:
                patterns["auth"] = "JWT (jsonwebtoken)"
            elif "passport" in deps:
                patterns["auth"] = "Passport.js"

        except Exception:
            pass

    # Check for Python project
    req_txt = project_dir / "requirements.txt"
    if req_txt.exists():
        try:
            content = req_txt.read_text(encoding="utf-8").lower()
            if "fastapi" in content:
                patterns["framework"] = "FastAPI"
            elif "django" in content:
                patterns["framework"] = "Django"
            elif "flask" in content:
                patterns["framework"] = "Flask"
            if "sqlalchemy" in content:
                patterns["orm"] = "SQLAlchemy"
        except Exception:
            pass

    return patterns


def _build_queries_from_tasks(task_file: str) -> list:
    """Build validation queries from epic task file."""
    from src.services.fungus_validation_service import ValidationJudgeMode

    queries = []
    try:
        tasks = json.loads(Path(task_file).read_text(encoding="utf-8"))

        # Handle both list and dict formats
        if isinstance(tasks, dict):
            tasks = tasks.get("tasks", [])

        # Group tasks by type/phase
        completed_types = set()
        failed_types = set()
        for task in tasks:
            status = task.get("status", "pending")
            task_type = task.get("type", "")
            if status == "completed" and task_type:
                completed_types.add(task_type)
            elif status == "failed" and task_type:
                failed_types.add(task_type)

        # Build queries from failed tasks (priority)
        for task_type in list(failed_types)[:3]:
            queries.append((
                f"validate {task_type} implementation patterns",
                ValidationJudgeMode.DEPENDENCY_CHECK,
            ))

        # Build queries from completed tasks
        for task_type in list(completed_types)[:3]:
            queries.append((
                f"validate {task_type} code quality and consistency",
                ValidationJudgeMode.PATTERN_CHECK,
            ))

        # Always add cross-file validation
        queries.append((
            "validate cross-file imports and exports consistency",
            ValidationJudgeMode.CROSS_FILE,
        ))

    except Exception as e:
        print(f"Warning: Could not parse task file: {e}")

    return queries


def _default_validation_queries(project_dir: Path) -> list:
    """Generate default validation queries based on project structure."""
    from src.services.fungus_validation_service import ValidationJudgeMode

    queries = [
        ("validate import dependencies and module references", ValidationJudgeMode.DEPENDENCY_CHECK),
        ("validate code patterns and naming conventions", ValidationJudgeMode.PATTERN_CHECK),
        ("validate database schema alignment with TypeScript types", ValidationJudgeMode.SCHEMA_CONSISTENCY),
    ]

    # Add API validation if API files exist
    if list(project_dir.rglob("*.controller.*")) or list(project_dir.rglob("*routes*")):
        queries.append((
            "validate API endpoint implementations and contracts",
            ValidationJudgeMode.API_CONTRACT,
        ))

    # Add cross-file validation
    queries.append((
        "validate cross-file exports and barrel file completeness",
        ValidationJudgeMode.CROSS_FILE,
    ))

    return queries


if __name__ == "__main__":
    asyncio.run(main())
