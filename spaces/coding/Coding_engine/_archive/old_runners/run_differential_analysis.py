#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Differential Analysis CLI - Phase 20

Compares documentation/requirements against generated code to identify
implementation gaps using Fungus MCMP simulation.

Usage:
    # Full analysis on whatsapp service
    python run_differential_analysis.py --data-dir Data/all_services/whatsapp

    # With explicit code directory
    python run_differential_analysis.py --data-dir Data/all_services/whatsapp --code-dir Data/all_services/whatsapp/output

    # Dry run (no LLM calls, heuristic only)
    python run_differential_analysis.py --data-dir Data/all_services/whatsapp --dry-run

    # Focus on specific analysis mode
    python run_differential_analysis.py --data-dir Data/all_services/whatsapp --mode api_completeness

    # Export to specific file
    python run_differential_analysis.py --data-dir Data/all_services/whatsapp --output report.json
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


async def main():
    parser = argparse.ArgumentParser(
        description="Differential Analysis: Documentation vs Generated Code",
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
        "--mode",
        choices=[
            "full_differential",
            "requirement_coverage",
            "api_completeness",
            "schema_coverage",
            "user_story_trace",
        ],
        default="full_differential",
        help="Analysis mode (default: full_differential)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for JSON report (default: <data-dir>/differential_report.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls, use heuristic matching only",
    )
    parser.add_argument(
        "--no-supermemory",
        action="store_true",
        help="Disable Supermemory enrichment",
    )
    parser.add_argument(
        "--focus",
        nargs="*",
        default=None,
        help="Focus on specific requirement IDs (e.g., WA-AUTH-001 WA-PROF-002)",
    )

    args = parser.parse_args()

    # Force dry-run by removing API key if requested
    if args.dry_run:
        os.environ.pop("OPENROUTER_API_KEY", None)

    from src.services.differential_analysis_service import (
        AnalysisMode,
        DifferentialAnalysisService,
        ImplementationStatus,
    )

    print(f"\n{'='*60}")
    print(f"  Differential Analysis - Documentation vs Code")
    print(f"{'='*60}")
    print(f"  Data dir:  {args.data_dir}")
    print(f"  Code dir:  {args.code_dir or '<data-dir>/output'}")
    print(f"  Mode:      {args.mode}")
    print(f"  Dry run:   {args.dry_run}")
    print(f"  Supermemory: {'disabled' if args.no_supermemory else 'enabled'}")
    print(f"{'='*60}\n")

    # Map mode string to enum
    mode_map = {
        "full_differential": AnalysisMode.FULL_DIFFERENTIAL,
        "requirement_coverage": AnalysisMode.REQUIREMENT_COVERAGE,
        "api_completeness": AnalysisMode.API_COMPLETENESS,
        "schema_coverage": AnalysisMode.SCHEMA_COVERAGE,
        "user_story_trace": AnalysisMode.USER_STORY_TRACE,
    }
    mode = mode_map[args.mode]

    # Create service
    service = DifferentialAnalysisService(
        data_dir=args.data_dir,
        code_dir=args.code_dir,
        job_id="cli_analysis",
        enable_supermemory=not args.no_supermemory,
    )

    start_time = time.time()

    # Start service
    print("[1/3] Loading documentation and code...")
    started = await service.start()
    if not started:
        print("ERROR: Failed to start analysis. Check data directory.")
        return 1

    print(f"      Loaded {service.user_story_count} user stories, {service.task_count} tasks")
    print(f"      Loaded {service.requirement_count} requirements")

    # Run analysis
    print(f"\n[2/3] Running {args.mode} analysis...")
    report = await service.run_analysis(
        mode=mode,
        focus_requirements=args.focus,
    )

    elapsed = time.time() - start_time

    # Print summary
    print(f"\n[3/3] Analysis complete in {elapsed:.1f}s")
    print(f"\n{'='*60}")
    print(f"  COVERAGE REPORT")
    print(f"{'='*60}")
    print(f"  Total requirements:  {report.total_requirements}")
    print(f"  Implemented:         {report.implemented} ({_pct(report.implemented, report.total_requirements)})")
    print(f"  Partial:             {report.partial} ({_pct(report.partial, report.total_requirements)})")
    print(f"  Missing:             {report.missing} ({_pct(report.missing, report.total_requirements)})")
    print(f"  Unknown:             {report.unknown} ({_pct(report.unknown, report.total_requirements)})")
    print(f"  Coverage:            {report.coverage_percent:.1f}%")
    print(f"  Judge confidence:    {report.judge_confidence:.2f}")
    print(f"{'='*60}")

    # Print critical gaps
    critical = service.get_critical_gaps()
    if critical:
        print(f"\n  CRITICAL GAPS ({len(critical)}):")
        for gap in critical:
            print(f"    [{gap.requirement_id}] {gap.requirement_title}")
            print(f"       Status: {gap.status.value} | Priority: {gap.priority}")
            if gap.gap_description:
                print(f"       Gap: {gap.gap_description[:100]}")
            print()

    # Print missing requirements
    missing = [f for f in report.findings if f.status == ImplementationStatus.MISSING]
    if missing and len(missing) <= 20:
        print(f"\n  MISSING REQUIREMENTS ({len(missing)}):")
        for m in missing:
            print(f"    [{m.requirement_id}] {m.requirement_title} ({m.priority})")

    # Export report
    output_path = args.output or str(service.data_dir / "differential_report.json")
    service.export_report(output_path)
    print(f"\n  Report saved to: {output_path}")

    # Stop service
    await service.stop()

    print(f"\nDone.\n")
    return 0


def _pct(count: int, total: int) -> str:
    """Format count as percentage."""
    if total == 0:
        return "0%"
    return f"{count / total * 100:.0f}%"


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code or 0)
