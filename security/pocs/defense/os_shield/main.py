"""
OS Shield - Autonomous LLM-Driven OS Security System
======================================================
Scannt Windows 11 autonom auf Bedrohungen mittels GPT-4o Tool Calling.

Architektur:
  OrchestratorAgent (LLM) -> MonitorAgent (I/O) -> ThreatAnalyzerAgent (LLM)
  -> EnforcerAgent (Countermeasures) -> ReporterAgent (Report)

Nutzung:
  python main.py --scan                    # Einmal-Scan
  python main.py --watch                   # Dauerhafter Waechter (30s Intervall)
  python main.py --watch --interval 10     # Alle 10 Sekunden
  python main.py --scan --auto-enforce     # Automatisch blockieren
  python main.py --scan --baseline b.json  # Baseline laden/speichern
"""

import argparse
import asyncio
import ctypes
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_client, get_model

from autogen_core import AgentId, SingleThreadedAgentRuntime

from messages import ShieldRequest, SecurityReport
from orchestrator import OrchestratorAgent
from monitor_agent import MonitorAgent
from analyzer import ThreatAnalyzerAgent
from enforcer import EnforcerAgent
from reporter import ReporterAgent
from baselines import capture_baseline, save_baseline, load_baseline
from config import WATCH_INTERVAL, OPENAI_API_KEY


def is_admin() -> bool:
    """Check if running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


async def run_scan(
    runtime: SingleThreadedAgentRuntime,
    baseline: dict | None,
    mode: str = "oneshot",
) -> SecurityReport:
    """Run a single security scan cycle."""
    baseline_json = json.dumps(baseline) if baseline else ""

    report: SecurityReport = await runtime.send_message(
        ShieldRequest(
            scan_domains="process,network,registry,usb,binary",
            mode=mode,
            baseline_json=baseline_json,
        ),
        AgentId("orchestrator_agent", "default"),
    )

    # Print report
    print(report.report_text)

    # Color-coded verdict
    colors = {
        "CRITICAL": "\033[91m",  # red
        "HIGH": "\033[93m",      # yellow
        "MEDIUM": "\033[93m",    # yellow
        "LOW": "\033[92m",       # green
        "INFO": "\033[90m",      # gray
    }
    reset = "\033[0m"
    color = colors.get(report.overall_severity, "")
    print(f"  {color}SEVERITY: {report.overall_severity}{reset}")
    print(f"  Findings: {report.finding_count} | Actions: {report.actions_taken}")
    print()

    return report


async def main():
    parser = argparse.ArgumentParser(
        description="OS Shield - Autonomous LLM-Driven OS Security"
    )
    parser.add_argument("--scan", action="store_true", help="One-shot scan")
    parser.add_argument("--watch", action="store_true", help="Continuous watch mode")
    parser.add_argument("--auto-enforce", action="store_true", help="Auto-enforce actions")
    parser.add_argument("--interval", type=int, default=WATCH_INTERVAL, help="Watch interval (seconds)")
    parser.add_argument("--baseline", type=str, default="baseline.json", help="Baseline file path")
    args = parser.parse_args()

    if not args.scan and not args.watch:
        parser.print_help()
        sys.exit(1)

    # Banner
    print()
    print("=" * 60)
    print("  OS SHIELD")
    print("  Autonomous LLM-Driven OS Security System")
    print("=" * 60)
    print()

    # Admin check
    if is_admin():
        print("  [OK] Running as Administrator")
    else:
        print("  [WARN] Not running as Administrator!")
        print("         Some checks will have limited access.")
        print("         Run as Admin for full functionality.")
    print()

    # OpenAI API key (loaded from .env via config.py)
    if not OPENAI_API_KEY:
        print("  [ERROR] OPENAI_API_KEY not set!")
        print("  Add it to .env or: export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    print(f"  [OK] LLM Model: {get_model('blue_team')}")
    llm_client = get_client("blue_team")

    # Setup runtime
    print("  [SETUP] Registering agents...", flush=True)

    runtime = SingleThreadedAgentRuntime()

    await OrchestratorAgent.register(
        runtime, "orchestrator_agent",
        lambda: OrchestratorAgent(llm_client),
    )
    await MonitorAgent.register(
        runtime, "monitor_agent",
        lambda: MonitorAgent(),
    )
    await ThreatAnalyzerAgent.register(
        runtime, "analyzer_agent",
        lambda: ThreatAnalyzerAgent(llm_client),
    )
    await EnforcerAgent.register(
        runtime, "enforcer_agent",
        lambda: EnforcerAgent(auto_enforce=args.auto_enforce),
    )
    await ReporterAgent.register(
        runtime, "reporter_agent",
        lambda: ReporterAgent(),
    )

    runtime.start()
    print("  [SETUP] Agents ready.\n", flush=True)

    # Load or capture baseline
    baseline = await load_baseline(args.baseline)
    if baseline is None:
        print("  [BASELINE] No baseline found. Capturing current state...", flush=True)
        baseline = await capture_baseline()
        await save_baseline(baseline, args.baseline)

    if args.scan:
        # ---- One-shot mode ----
        report = await run_scan(runtime, baseline, mode="oneshot")
        await runtime.stop()

        # Update baseline after scan
        new_baseline = await capture_baseline()
        await save_baseline(new_baseline, args.baseline)

        # Exit code based on severity
        if report.overall_severity == "CRITICAL":
            sys.exit(2)
        elif report.overall_severity in ("HIGH", "MEDIUM"):
            sys.exit(1)
        else:
            sys.exit(0)

    elif args.watch:
        # ---- Continuous watch mode ----
        print(f"  [WATCH] Continuous mode. Interval: {args.interval}s")
        print(f"  [WATCH] Press Ctrl+C to stop.\n")

        cycle = 0
        try:
            while True:
                cycle += 1
                print(f"\n{'#' * 60}")
                print(f"  WATCH CYCLE {cycle}")
                print(f"{'#' * 60}\n")

                await run_scan(runtime, baseline, mode=f"continuous_cycle_{cycle}")

                # Update baseline
                baseline = await capture_baseline()
                await save_baseline(baseline, args.baseline)

                print(f"\n  [WATCH] Next scan in {args.interval}s...\n")
                await asyncio.sleep(args.interval)

        except KeyboardInterrupt:
            print("\n  [WATCH] Stopped by user.")

        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
