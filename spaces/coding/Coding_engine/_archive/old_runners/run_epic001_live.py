# -*- coding: utf-8 -*-
"""
Live test: Run EPIC-001 with Society of Mind convergence loop.

Phase 25: Fail-forward execution + automatic differential validation.

Usage:
    python run_epic001_live.py                          # Auto-detect project
    python run_epic001_live.py --project-path <path>    # Explicit project
    python run_epic001_live.py --parallel 3              # Parallel execution
    python run_epic001_live.py --diff-fixes 5            # Fix top 5 gaps after run
    python run_epic001_live.py --no-diff                 # Skip differential validation
    python run_epic001_live.py --block-on-fail           # Old behavior: block on failed deps
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "mcp_plugins" / "servers" / "grpc_host"))

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


def find_latest_project() -> Path:
    """Find the most recently modified project in Data/all_services/."""
    data_dir = Path("Data/all_services")
    if not data_dir.exists():
        return Path("")

    candidates = []
    for project_dir in data_dir.iterdir():
        if project_dir.is_dir() and (project_dir / "tasks").exists():
            candidates.append(project_dir)

    if not candidates:
        return Path("")

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def load_som_config() -> dict:
    """Load SoM bridge config from society_defaults.json."""
    config_path = Path(__file__).parent / "config" / "society_defaults.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data.get("som_bridge", {})
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _pct(count: int, total: int) -> str:
    """Format count as percentage."""
    if total == 0:
        return "0%"
    return f"{count / total * 100:.0f}%"


# =============================================================================
# Post-Execution: Differential Validation + Auto-Fix
# =============================================================================

async def run_differential_validation(
    data_dir: str,
    code_dir: str,
    max_fixes: int = 0,
    verify: bool = False,
) -> dict:
    """
    Run differential analysis on the generated code vs documentation.

    Measures what was actually implemented, identifies gaps, and optionally
    spawns claude-code agents to fix the most critical ones.

    Args:
        data_dir: Path to project data (requirements, user stories, tasks)
        code_dir: Path to generated code output
        max_fixes: Number of critical gaps to auto-fix (0 = analysis only)
        verify: Re-run analysis after fixes to measure improvement

    Returns:
        Dict with coverage metrics and fix results
    """
    from src.services.differential_analysis_service import (
        AnalysisMode,
        DifferentialAnalysisService,
        ImplementationStatus,
        GapSeverity,
    )

    print(f"\n{'='*60}")
    print(f"  POST-RUN: Differential Validation")
    print(f"{'='*60}")
    print(f"  Data dir:    {data_dir}")
    print(f"  Code dir:    {code_dir}")
    print(f"  Auto-fix:    {max_fixes} gaps" if max_fixes > 0 else "  Auto-fix:    disabled")
    print(f"{'='*60}\n")

    # Phase 1: Load & Analyze
    print("[DIFF 1/3] Loading documentation and code...")

    service = DifferentialAnalysisService(
        data_dir=data_dir,
        code_dir=code_dir,
        job_id="post_epic_validation",
        enable_supermemory=False,  # Fast mode — no Supermemory
    )

    start_time = time.time()
    started = await service.start()
    if not started:
        print("  WARNING: Could not start differential analysis (missing data?)")
        return {"error": "start_failed", "coverage": 0}

    print(f"      {service.user_story_count} user stories, "
          f"{service.task_count} tasks, "
          f"{service.requirement_count} requirements")

    # Phase 2: Run analysis
    print("\n[DIFF 2/3] Running differential analysis (LLM Judge)...")

    report = await service.run_analysis(
        mode=AnalysisMode.FULL_DIFFERENTIAL,
    )

    elapsed = time.time() - start_time
    print(f"      Analysis complete in {elapsed:.0f}s")
    print(f"\n      Coverage Report:")
    print(f"        Total requirements:  {report.total_requirements}")
    print(f"        Implemented:         {report.implemented} ({_pct(report.implemented, report.total_requirements)})")
    print(f"        Partial:             {report.partial} ({_pct(report.partial, report.total_requirements)})")
    print(f"        Missing:             {report.missing} ({_pct(report.missing, report.total_requirements)})")
    print(f"        Coverage:            {report.coverage_percent:.1f}%")
    print(f"        Judge confidence:    {report.judge_confidence:.2f}")

    result = {
        "coverage_before": report.coverage_percent,
        "total_requirements": report.total_requirements,
        "implemented": report.implemented,
        "partial": report.partial,
        "missing": report.missing,
        "judge_confidence": report.judge_confidence,
        "fixes_attempted": 0,
        "fixes_succeeded": 0,
    }

    # Phase 3: Auto-fix critical gaps
    if max_fixes > 0:
        # Filter critical gaps for fixing
        min_conf = 0.6
        critical_gaps = [
            f for f in report.findings
            if f.severity == GapSeverity.CRITICAL
            and f.confidence >= min_conf
            and f.status != ImplementationStatus.IMPLEMENTED
        ]

        if not critical_gaps:
            print(f"\n[DIFF 3/3] No critical gaps to fix (all implemented or low confidence).")
        else:
            from src.agents.differential_fix_agent import (
                DifferentialFixAgent,
                GAP_AGENT_ROUTING,
                GAP_TYPE_KEYWORDS,
            )
            from src.mind.event_bus import Event, EventType

            gaps_to_fix = critical_gaps[:max_fixes]
            print(f"\n[DIFF 3/3] Auto-fixing {len(gaps_to_fix)} critical gaps via claude-code...")

            try:
                from src.mcp.agent_pool import MCPAgentPool

                pool = MCPAgentPool(working_dir=code_dir)
                available = pool.list_available()

                fix_results = []
                for i, gap in enumerate(gaps_to_fix, 1):
                    # Determine gap type for routing
                    event = Event(
                        type=EventType.CODE_FIX_NEEDED,
                        source="pipeline",
                        data={
                            "gap_description": gap.gap_description or "",
                            "reason": gap.requirement_title or "",
                            "suggested_tasks": gap.suggested_tasks or [],
                        },
                    )
                    gap_type = DifferentialFixAgent._determine_gap_type(event)
                    agents = GAP_AGENT_ROUTING.get(gap_type, GAP_AGENT_ROUTING["default"])

                    # Pick first available agent
                    agent_name = next((a for a in agents if a in available), None)
                    if not agent_name:
                        agent_name = "claude-code" if "claude-code" in available else None

                    if not agent_name:
                        print(f"  [{gap.requirement_id}] SKIP - no agents available")
                        continue

                    task_desc = DifferentialFixAgent._build_agent_task(
                        agent_name=agent_name,
                        requirement_id=gap.requirement_id,
                        description=gap.gap_description or gap.requirement_title,
                        suggested_tasks=gap.suggested_tasks or [],
                    )

                    print(f"\n  [{i}/{len(gaps_to_fix)}] {gap.requirement_id}: {gap.requirement_title}")
                    print(f"     Agent: {agent_name} | Type: {gap_type}")

                    spawn_result = await pool.spawn(agent_name, task_desc)
                    status = "OK" if spawn_result.success else "FAIL"
                    print(f"     Result: {status} ({spawn_result.duration:.0f}s)")

                    fix_results.append({
                        "requirement_id": gap.requirement_id,
                        "success": spawn_result.success,
                        "agent": agent_name,
                        "duration": spawn_result.duration,
                    })

                result["fixes_attempted"] = len(fix_results)
                result["fixes_succeeded"] = sum(1 for r in fix_results if r["success"])
                result["fix_details"] = fix_results

            except Exception as e:
                print(f"\n  ERROR: Auto-fix failed: {e}")
                result["fix_error"] = str(e)

        # Optional: re-run analysis to measure improvement
        if verify and result.get("fixes_succeeded", 0) > 0:
            print(f"\n  Re-running analysis to verify improvements...")
            service2 = DifferentialAnalysisService(
                data_dir=data_dir,
                code_dir=code_dir,
                job_id="post_epic_verify",
                enable_supermemory=False,
            )
            started2 = await service2.start()
            if started2:
                report2 = await service2.run_analysis(mode=AnalysisMode.FULL_DIFFERENTIAL)
                result["coverage_after"] = report2.coverage_percent
                delta = report2.coverage_percent - report.coverage_percent
                print(f"  Coverage: {report.coverage_percent:.1f}% -> {report2.coverage_percent:.1f}% ({'+' if delta >= 0 else ''}{delta:.1f}%)")
                await service2.stop()
    else:
        print(f"\n[DIFF 3/3] Auto-fix disabled (use --diff-fixes N to enable).")

    # Export report
    report_path = os.path.join(data_dir, "differential_report.json")
    service.export_report(report_path)
    print(f"\n  Report saved: {report_path}")

    await service.stop()
    return result


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="Run EPIC-001 with fail-forward execution + differential validation",
    )
    parser.add_argument("--project-path", default=None, help="Project directory")
    parser.add_argument("--parallel", type=int, default=3,
                        help="Max parallel tasks (default: 3, pipeline mode)")
    parser.add_argument("--no-som", action="store_true",
                        help="Disable SoM convergence loop")
    parser.add_argument("--max-tasks", type=int, default=None,
                        help="Limit execution to N tasks (respects dependency order)")
    parser.add_argument("--phases", type=str, default=None,
                        help="Execute only these phases (comma-separated: setup,schema,code)")

    # Fail-forward: DEFAULT behavior — failed deps don't block downstream
    parser.add_argument("--block-on-fail", action="store_true",
                        help="Block downstream tasks when dependencies fail (old behavior)")
    # Keep old flag as alias (backward compat)
    parser.add_argument("--skip-failed-deps", action="store_true",
                        help="(default) Treat failed deps as completed — same as not using --block-on-fail")

    # Differential validation after epic run
    parser.add_argument("--no-diff", action="store_true",
                        help="Skip differential validation after epic run")
    parser.add_argument("--diff-fixes", type=int, default=0,
                        help="Auto-fix N critical gaps via claude-code after epic run (default: 0 = analysis only)")
    parser.add_argument("--diff-verify", action="store_true",
                        help="Re-run analysis after auto-fixes to measure improvement")

    args = parser.parse_args()

    # Fail-forward is the default; --block-on-fail disables it
    skip_failed_deps = not args.block_on_fail

    # Resolve project path
    if args.project_path:
        project_path = Path(args.project_path)
    else:
        project_path = find_latest_project()

    if not project_path or not project_path.exists():
        print("Error: No project found. Use --project-path to specify one.")
        sys.exit(1)

    # Parse phases filter
    phases = [p.strip() for p in args.phases.split(",")] if args.phases else None

    print(f"\n{'='*70}")
    print(f"  EPIC-001 Runner (Phase 25: Fail-Forward + Diff Validation)")
    print(f"{'='*70}")
    print(f"  Project:     {project_path}")
    print(f"  Parallel:    {args.parallel}")
    print(f"  SoM:         {'disabled' if args.no_som else 'enabled'}")
    print(f"  Fail-forward: {'disabled (block on fail)' if args.block_on_fail else 'enabled (default)'}")
    if phases:
        print(f"  Phases:      {', '.join(phases)}")
    if args.max_tasks:
        print(f"  Max tasks:   {args.max_tasks}")
    if not args.no_diff:
        print(f"  Diff valid:  enabled (fixes: {args.diff_fixes})")
    else:
        print(f"  Diff valid:  disabled")
    print(f"{'='*70}\n")

    from epic_orchestrator import EpicOrchestrator

    som_config = load_som_config()

    # Use pipeline_max_parallel from config if --parallel not explicitly set
    parallel = args.parallel
    if parallel == 3 and som_config.get("pipeline_max_parallel"):
        parallel = som_config["pipeline_max_parallel"]

    orchestrator = EpicOrchestrator(
        str(project_path),
        max_parallel_tasks=parallel,
        enable_som=not args.no_som,
        som_config=som_config,
    )

    # =========================================================================
    # Step 1: Execute Epic (fail-forward)
    # =========================================================================
    print("=" * 70)
    print("  STEP 1: Running EPIC-001 (fail-forward)...")
    print("=" * 70)

    epic_start = time.time()

    result = await orchestrator.run_epic(
        "EPIC-001",
        max_tasks=args.max_tasks,
        phases=phases,
        skip_failed_deps=skip_failed_deps,
    )

    epic_duration = time.time() - epic_start

    print()
    print("=" * 70)
    status = "OK" if result.success else "PARTIAL"
    print(f"  [{status}] EPIC-001 execution ended")
    print(f"    Completed: {result.completed_tasks}/{result.total_tasks}")
    print(f"    Failed:    {result.failed_tasks}")
    print(f"    Skipped:   {result.skipped_tasks}")
    print(f"    Duration:  {epic_duration:.0f}s")
    print("=" * 70)

    # =========================================================================
    # Step 2: Differential Validation (automatic)
    # =========================================================================
    diff_result = None
    if not args.no_diff:
        code_dir = str(project_path / "output")
        if Path(code_dir).exists():
            diff_result = await run_differential_validation(
                data_dir=str(project_path),
                code_dir=code_dir,
                max_fixes=args.diff_fixes,
                verify=args.diff_verify,
            )
        else:
            print(f"\n  SKIP differential validation: no output dir at {code_dir}")

    # =========================================================================
    # Final Summary
    # =========================================================================
    total_duration = time.time() - epic_start

    print(f"\n{'='*70}")
    print(f"  FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"  Total duration:    {total_duration:.0f}s")
    print(f"  Epic tasks:        {result.completed_tasks}/{result.total_tasks} completed, "
          f"{result.failed_tasks} failed, {result.skipped_tasks} skipped")

    if diff_result and "error" not in diff_result:
        cov = diff_result.get("coverage_before", 0)
        impl = diff_result.get("implemented", 0)
        total_req = diff_result.get("total_requirements", 0)
        print(f"  Req coverage:      {cov:.1f}% ({impl}/{total_req} implemented)")
        if diff_result.get("fixes_attempted", 0) > 0:
            print(f"  Auto-fixes:        {diff_result['fixes_succeeded']}/{diff_result['fixes_attempted']} succeeded")
        if diff_result.get("coverage_after") is not None:
            delta = diff_result["coverage_after"] - cov
            print(f"  Coverage after fix: {diff_result['coverage_after']:.1f}% ({'+' if delta >= 0 else ''}{delta:.1f}%)")

    print(f"{'='*70}\n")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(main())
