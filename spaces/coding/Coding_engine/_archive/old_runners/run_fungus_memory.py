#!/usr/bin/env python3
"""
Fungus Memory MCMP Search CLI - Phase 18

Runs memory-augmented MCMP search against a project directory.
Indexes source files + Supermemory memories, runs swarm simulation,
and reports code<->memory correlations.

Usage:
    # Dry-run against test project
    python run_fungus_memory.py --project-dir Data/all_services/unnamed_project_20260204_165411 --dry-run

    # With specific memory query
    python run_fungus_memory.py --project-dir ./output --query "Hono auth patterns"

    # With learning (stores new patterns back to Supermemory)
    python run_fungus_memory.py --project-dir ./output --learn --report-file memory_report.json

    # Multiple seed queries
    python run_fungus_memory.py --project-dir ./output --query "auth patterns" --query "error handling"
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

# Load .env (OPENROUTER_API_KEY, SUPERMEMORY_API_KEY, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass


async def main():
    parser = argparse.ArgumentParser(
        description="Fungus Memory MCMP Search - Memory-augmented code correlation discovery"
    )
    parser.add_argument(
        "--project-dir", required=True,
        help="Path to the project directory to search",
    )
    parser.add_argument(
        "--query", action="append", default=None,
        help="Memory search query (can be specified multiple times)",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=3,
        help="Maximum search rounds (default: 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only, no pattern storage",
    )
    parser.add_argument(
        "--learn", action="store_true",
        help="Run learning round and store new patterns to Supermemory",
    )
    parser.add_argument(
        "--report-file", default=None,
        help="Write JSON report to this file",
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
    print(f"  Fungus Memory MCMP Search")
    print(f"  Project: {project_dir}")
    print(f"  Mode: {'dry-run' if args.dry_run else 'live'}")
    print(f"  Learning: {'enabled' if args.learn else 'disabled'}")
    print(f"  Swarm: {args.num_agents} agents, {args.max_iterations} max iterations")
    print(f"{'='*70}\n")

    # Build seed queries
    seed_queries = args.query or _default_seed_queries(project_dir)
    print(f"Seed queries: {seed_queries}\n")

    # Import after path setup
    from src.services.mcmp_background import SimulationConfig
    from src.services.fungus_memory_service import (
        FungusMemoryService,
        MemoryJudgeMode,
    )

    config = SimulationConfig(
        num_agents=args.num_agents,
        max_iterations=args.max_iterations,
        judge_every=5,
        steering_every=5,
        enable_llm_steering=True,
    )

    service = FungusMemoryService(
        working_dir=str(project_dir),
        event_bus=None,
        config=config,
        job_id="cli_memory",
    )

    # Start service
    print("Indexing project files and loading memories...")
    started = await service.start(seed_queries=seed_queries)
    if not started:
        print("Error: Failed to start memory service (no files indexed?)")
        sys.exit(1)

    print(f"Indexed {service.indexed_count} files, {service.memory_count} memories\n")

    # Build search queries
    queries = _build_search_queries(seed_queries, project_dir)

    # Run memory rounds
    all_reports = []
    for i, (query, mode) in enumerate(queries[:args.max_rounds]):
        print(f"{'='*70}")
        print(f"  Round {i+1}/{min(len(queries), args.max_rounds)}")
        print(f"  Query: {query}")
        print(f"  Mode: {mode.value}")
        print(f"{'='*70}")

        start_time = time.time()
        report = await service.run_memory_round(
            focus_query=query,
            mode=mode,
        )
        elapsed = time.time() - start_time

        all_reports.append(report)

        # Print correlations
        if report.correlations:
            for j, corr in enumerate(report.correlations):
                type_icon = {
                    "similar_pattern": "[PATTERN]",
                    "applicable_fix": "[FIX]",
                    "architecture_match": "[ARCH]",
                    "context_enrichment": "[CTX]",
                }.get(corr.correlation_type, "[?]")

                print(f"\n  {type_icon} {corr.correlation_type}")
                if corr.memory_id:
                    print(f"    Memory: {corr.memory_category}/{corr.memory_id}")
                if corr.related_code_files:
                    print(f"    Code: {', '.join(corr.related_code_files[:3])}")
                print(f"    Description: {corr.description}")
                if corr.suggested_action:
                    print(f"    Action: {corr.suggested_action}")
                print(f"    Relevance: {corr.relevance_score:.2f}")
        else:
            print("\n  No correlations found in this round.")

        if report.new_patterns_found:
            print(f"\n  New patterns to store: {report.new_patterns_found}")

        print(f"\n  Steps: {report.simulation_steps} | "
              f"Code: {report.code_files_analyzed} | "
              f"Memories: {report.memories_searched} | "
              f"Time: {elapsed:.1f}s")
        print()

    # Learning round
    if args.learn and not args.dry_run:
        print(f"{'='*70}")
        print(f"  Learning Round (storing new patterns)")
        print(f"{'='*70}")

        learning_report = await service.run_memory_round(
            focus_query="identify new patterns worth remembering from this project",
            mode=MemoryJudgeMode.LEARNING,
        )
        all_reports.append(learning_report)

        stored = await service.store_pending_patterns()
        print(f"\n  Stored {stored} new patterns to Supermemory")

    # Stop service
    await service.stop()

    # Summary
    total_correlations = sum(len(r.correlations) for r in all_reports)
    total_new_patterns = sum(r.new_patterns_found for r in all_reports)

    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Rounds: {len(all_reports)}")
    print(f"  Total correlations: {total_correlations}")
    print(f"  New patterns found: {total_new_patterns}")
    print(f"  Files indexed: {service.indexed_count}")
    print(f"  Memories loaded: {service.memory_count}")
    print(f"{'='*70}")

    # Write report if requested
    if args.report_file:
        report_data = {
            "project_dir": str(project_dir),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "seed_queries": seed_queries,
            "config": {
                "num_agents": args.num_agents,
                "max_iterations": args.max_iterations,
            },
            "rounds": [
                {
                    "round": r.round_number,
                    "focus_query": r.focus_query,
                    "code_files_analyzed": r.code_files_analyzed,
                    "memories_searched": r.memories_searched,
                    "simulation_steps": r.simulation_steps,
                    "new_patterns_found": r.new_patterns_found,
                    "correlations": [
                        {
                            "memory_id": c.memory_id,
                            "memory_category": c.memory_category,
                            "correlation_type": c.correlation_type,
                            "related_code_files": c.related_code_files,
                            "relevance_score": c.relevance_score,
                            "description": c.description,
                            "suggested_action": c.suggested_action,
                        }
                        for c in r.correlations
                    ],
                }
                for r in all_reports
            ],
            "summary": {
                "total_correlations": total_correlations,
                "new_patterns": total_new_patterns,
                "files_indexed": service.indexed_count,
                "memories_loaded": service.memory_count,
            },
        }

        report_path = Path(args.report_file)
        report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReport written to: {report_path}")


def _default_seed_queries(project_dir: Path) -> list:
    """Generate default seed queries based on project structure."""
    queries = ["code architecture and module structure"]

    # Check package.json for framework
    pkg_json = project_dir / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            if "hono" in deps:
                queries.append("Hono framework routing patterns")
            elif "express" in deps:
                queries.append("Express.js middleware patterns")
            elif "next" in deps:
                queries.append("Next.js page routing patterns")

            if "@prisma/client" in deps:
                queries.append("Prisma ORM database patterns")
            if "jose" in deps or "jsonwebtoken" in deps:
                queries.append("JWT authentication patterns")
        except Exception:
            pass

    # Check for Python project
    req_txt = project_dir / "requirements.txt"
    if req_txt.exists():
        try:
            content = req_txt.read_text(encoding="utf-8").lower()
            if "fastapi" in content:
                queries.append("FastAPI endpoint patterns")
            if "sqlalchemy" in content:
                queries.append("SQLAlchemy database patterns")
        except Exception:
            pass

    return queries


def _build_search_queries(seed_queries: list, project_dir: Path) -> list:
    """Build search queries with appropriate modes."""
    from src.services.fungus_memory_service import MemoryJudgeMode

    queries = []

    for q in seed_queries[:3]:
        queries.append((q, MemoryJudgeMode.PATTERN_RECALL))

    # Add error fix recall if there are error patterns
    queries.append((
        "common build errors and fixes for this project type",
        MemoryJudgeMode.ERROR_FIX_RECALL,
    ))

    # Add context enrichment
    queries.append((
        "architecture decisions and design patterns",
        MemoryJudgeMode.CONTEXT_ENRICHMENT,
    ))

    return queries


if __name__ == "__main__":
    asyncio.run(main())
