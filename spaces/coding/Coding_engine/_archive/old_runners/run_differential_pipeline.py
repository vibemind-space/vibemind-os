#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Differential Pipeline CLI - Phase 23

End-to-end pipeline that chains:
  1. Differential Analysis (find gaps between docs and code)
  2. Gap-type routing (classify each gap)
  3. MCP Agent fixes (spawn filesystem/prisma/npm agents)
  4. Verification (re-run analysis to measure improvement)

Usage:
    # Dry-run: analysis only, no fixes
    python run_differential_pipeline.py --data-dir Data/all_services/whatsapp --dry-run

    # Fix top 3 critical gaps
    python run_differential_pipeline.py --data-dir Data/all_services/whatsapp --max-fixes 3

    # Fix + verify coverage improvement
    python run_differential_pipeline.py --data-dir Data/all_services/whatsapp --max-fixes 5 --verify

    # Filter to schema gaps only
    python run_differential_pipeline.py --data-dir Data/all_services/whatsapp --gap-types schema
"""

import argparse
import asyncio
import json
import os
import sys
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _pct(count: int, total: int) -> str:
    """Format count as percentage."""
    if total == 0:
        return "0%"
    return f"{count / total * 100:.0f}%"


def _determine_gap_type(gap) -> str:
    """Determine gap type using DifferentialFixAgent's static method."""
    from src.agents.differential_fix_agent import (
        DifferentialFixAgent,
        GAP_TYPE_KEYWORDS,
    )
    from src.mind.event_bus import Event, EventType

    # Build a mock event from the gap finding
    event = Event(
        type=EventType.CODE_FIX_NEEDED,
        source="pipeline",
        data={
            "gap_description": gap.gap_description or "",
            "reason": gap.requirement_title or "",
            "suggested_tasks": gap.suggested_tasks or [],
        },
    )
    return DifferentialFixAgent._determine_gap_type(event)


def _build_task(agent_name: str, gap) -> str:
    """Build a task description for the MCP agent."""
    from src.agents.differential_fix_agent import DifferentialFixAgent

    return DifferentialFixAgent._build_agent_task(
        agent_name=agent_name,
        requirement_id=gap.requirement_id,
        description=gap.gap_description or gap.requirement_title,
        suggested_tasks=gap.suggested_tasks or [],
    )


async def run_pipeline(args):
    """Run the full differential pipeline."""
    from src.services.differential_analysis_service import (
        AnalysisMode,
        DifferentialAnalysisService,
        ImplementationStatus,
        GapSeverity,
    )
    from src.agents.differential_fix_agent import GAP_AGENT_ROUTING

    print(f"\n{'='*60}")
    print(f"  Differential Pipeline - Analysis > Fix > Verify")
    print(f"{'='*60}")
    print(f"  Data dir:     {args.data_dir}")
    print(f"  Code dir:     {args.code_dir or '<data-dir>/output'}")
    print(f"  Max fixes:    {args.max_fixes}")
    print(f"  Dry run:      {args.dry_run}")
    print(f"  Verify:       {args.verify}")
    print(f"  Gap types:    {args.gap_types or 'all'}")
    print(f"  Supermemory:  {'disabled' if args.no_supermemory else 'enabled'}")
    print(f"{'='*60}\n")

    # ----------------------------------------------------------------
    # Phase 1: Analysis
    # ----------------------------------------------------------------
    print("[1/4] Loading documentation and code...")

    service = DifferentialAnalysisService(
        data_dir=args.data_dir,
        code_dir=args.code_dir,
        job_id="pipeline_analysis",
        enable_supermemory=not args.no_supermemory,
    )

    start_time = time.time()
    started = await service.start()
    if not started:
        print("ERROR: Failed to start analysis service. Check data directory.")
        return 1

    print(f"      {service.user_story_count} user stories, "
          f"{service.task_count} tasks, "
          f"{service.requirement_count} requirements")

    # ----------------------------------------------------------------
    # Phase 2: Run differential analysis
    # ----------------------------------------------------------------
    print(f"\n[2/4] Running differential analysis...")

    report = await service.run_analysis(
        mode=AnalysisMode.FULL_DIFFERENTIAL,
    )

    elapsed_analysis = time.time() - start_time

    print(f"      Analysis complete in {elapsed_analysis:.1f}s")
    print(f"\n      Coverage Report:")
    print(f"        Total requirements:  {report.total_requirements}")
    print(f"        Implemented:         {report.implemented} ({_pct(report.implemented, report.total_requirements)})")
    print(f"        Partial:             {report.partial} ({_pct(report.partial, report.total_requirements)})")
    print(f"        Missing:             {report.missing} ({_pct(report.missing, report.total_requirements)})")
    print(f"        Coverage:            {report.coverage_percent:.1f}%")
    print(f"        Judge confidence:    {report.judge_confidence:.2f}")

    # LLM judge confidence thresholds
    min_conf_critical = 0.6
    min_conf_high = 0.5

    # Filter to critical gaps
    critical_gaps = [
        f for f in report.findings
        if f.severity == GapSeverity.CRITICAL
        and f.confidence >= min_conf_critical
        and f.status != ImplementationStatus.IMPLEMENTED
    ]

    # Also include high-severity missing
    high_gaps = [
        f for f in report.findings
        if f.severity == GapSeverity.HIGH
        and f.status == ImplementationStatus.MISSING
        and f.confidence >= min_conf_high
    ]

    all_gaps = critical_gaps + [g for g in high_gaps if g not in critical_gaps]

    # Classify each gap
    gap_info = []
    for gap in all_gaps:
        gap_type = _determine_gap_type(gap)
        agents = GAP_AGENT_ROUTING.get(gap_type, GAP_AGENT_ROUTING["default"])
        gap_info.append({
            "gap": gap,
            "type": gap_type,
            "agents": agents,
        })

    # Filter by gap types if specified
    if args.gap_types:
        gap_info = [g for g in gap_info if g["type"] in args.gap_types]

    # Limit to max_fixes
    gaps_to_fix = gap_info[:args.max_fixes]

    # ----------------------------------------------------------------
    # Phase 3: Show gaps / spawn fixes
    # ----------------------------------------------------------------
    if not gaps_to_fix:
        print(f"\n[3/4] No critical gaps to fix (all implemented or filtered out).")
    else:
        print(f"\n[3/4] {'Critical gaps for fixing' if args.dry_run else 'Fixing critical gaps'} ({len(gaps_to_fix)}/{len(gap_info)} total):")

        for i, info in enumerate(gaps_to_fix, 1):
            gap = info["gap"]
            print(f"\n  {i}. [{gap.requirement_id}] {gap.requirement_title}")
            print(f"     Severity: {gap.severity.value} | Confidence: {gap.confidence:.2f}")
            print(f"     Gap type: {info['type']} | Agents: {', '.join(info['agents'])}")
            if gap.gap_description:
                desc = gap.gap_description[:120]
                print(f"     Gap: {desc}")
            if gap.suggested_tasks:
                for task in gap.suggested_tasks[:3]:
                    print(f"       - {task[:80]}")

    fix_results = []

    if not args.dry_run and gaps_to_fix:
        print(f"\n  Spawning MCP agents...")

        try:
            from src.mcp.agent_pool import MCPAgentPool

            code_dir = args.code_dir or os.path.join(args.data_dir, "output")
            pool = MCPAgentPool(working_dir=code_dir)
            available = pool.list_available()
            print(f"  Available agents: {available}")

            for i, info in enumerate(gaps_to_fix, 1):
                gap = info["gap"]
                agent_names = [a for a in info["agents"] if a in available]

                if not agent_names:
                    if "filesystem" in available:
                        agent_names = ["filesystem"]
                    else:
                        print(f"  [{gap.requirement_id}] SKIP - no agents available")
                        fix_results.append({
                            "requirement_id": gap.requirement_id,
                            "success": False,
                            "error": "No agents available",
                            "agent": None,
                        })
                        continue

                agent_name = agent_names[0]
                task_desc = _build_task(agent_name, gap)

                print(f"\n  [{i}/{len(gaps_to_fix)}] Spawning {agent_name} for {gap.requirement_id}...")
                result = await pool.spawn(agent_name, task_desc)

                status = "OK" if result.success else "FAIL"
                print(f"    Result: {status} ({result.duration:.1f}s)")
                if result.error:
                    print(f"    Error: {result.error[:150]}")
                if result.output:
                    # Show last 200 chars of output
                    output_preview = result.output.strip()[-200:]
                    print(f"    Output: ...{output_preview}")

                fix_results.append({
                    "requirement_id": gap.requirement_id,
                    "success": result.success,
                    "agent": result.agent,
                    "duration": result.duration,
                    "error": result.error,
                })

        except Exception as e:
            print(f"\n  ERROR: MCPAgentPool failed: {e}")
            print(f"  Ensure MCP agents are registered in servers.json")

    # ----------------------------------------------------------------
    # Phase 4: Verify (optional)
    # ----------------------------------------------------------------
    coverage_before = report.coverage_percent
    coverage_after = None

    if args.verify and not args.dry_run and fix_results:
        print(f"\n[4/4] Re-running analysis to verify improvements...")

        # Need to reload code since agents may have modified files
        service2 = DifferentialAnalysisService(
            data_dir=args.data_dir,
            code_dir=args.code_dir,
            job_id="pipeline_verify",
            enable_supermemory=not args.no_supermemory,
        )

        started2 = await service2.start()
        if started2:
            report2 = await service2.run_analysis(
                mode=AnalysisMode.FULL_DIFFERENTIAL,
            )
            coverage_after = report2.coverage_percent

            print(f"\n      Verification Report:")
            print(f"        Coverage before: {coverage_before:.1f}%")
            print(f"        Coverage after:  {coverage_after:.1f}%")
            delta = coverage_after - coverage_before
            print(f"        Delta:           {'+' if delta >= 0 else ''}{delta:.1f}%")
            print(f"        Missing before:  {report.missing}")
            print(f"        Missing after:   {report2.missing}")

            # Export updated report
            output_path = service2.export_report()
            print(f"        Report saved:    {output_path}")

            await service2.stop()
        else:
            print(f"      WARNING: Failed to start verification analysis")
    elif args.verify:
        print(f"\n[4/4] Skipping verification (no fixes applied).")
    else:
        print(f"\n[4/4] Verification skipped (use --verify to enable).")

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    total_elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"  PIPELINE SUMMARY")
    print(f"{'='*60}")
    print(f"  Duration:          {total_elapsed:.1f}s")
    print(f"  Coverage:          {coverage_before:.1f}%", end="")
    if coverage_after is not None:
        delta = coverage_after - coverage_before
        print(f" -> {coverage_after:.1f}% ({'+' if delta >= 0 else ''}{delta:.1f}%)")
    else:
        print()
    print(f"  Gaps found:        {len(gap_info)} (critical + high)")
    print(f"  Fixes attempted:   {len(fix_results)}")
    if fix_results:
        successes = sum(1 for r in fix_results if r["success"])
        failures = len(fix_results) - successes
        print(f"  Fixes succeeded:   {successes}")
        print(f"  Fixes failed:      {failures}")
        if fix_results:
            print(f"\n  Fix details:")
            for r in fix_results:
                status = "OK" if r["success"] else "FAIL"
                agent = r.get("agent") or "none"
                print(f"    [{r['requirement_id']}] {agent} -> {status}")
    print(f"{'='*60}\n")

    # Export analysis report
    output_path = args.output or os.path.join(args.data_dir, "differential_report.json")
    service.export_report(output_path)
    print(f"  Analysis report: {output_path}")

    await service.stop()

    print(f"\nDone.\n")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Differential Pipeline: Analysis -> Fix -> Verify",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Path to service data directory (e.g., Data/all_services/whatsapp)",
    )
    parser.add_argument(
        "--code-dir",
        default=None,
        help="Path to generated code directory (default: <data-dir>/output)",
    )
    parser.add_argument(
        "--max-fixes",
        type=int,
        default=5,
        help="Maximum number of gaps to fix (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analysis only, no MCP agent fixes",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Re-run analysis after fixes to measure improvement",
    )
    parser.add_argument(
        "--gap-types",
        nargs="*",
        default=None,
        help="Filter to specific gap types (e.g., schema dependency migration)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for JSON report (default: <data-dir>/differential_report.json)",
    )
    parser.add_argument(
        "--no-supermemory",
        action="store_true",
        help="Disable Supermemory enrichment",
    )

    args = parser.parse_args()

    exit_code = asyncio.run(run_pipeline(args))
    sys.exit(exit_code or 0)


if __name__ == "__main__":
    main()
