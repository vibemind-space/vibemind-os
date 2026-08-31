"""
Red Team vs Blue Team - Autonomous Adversarial Loop
=======================================================
Entry point for the adversarial security exercise.

Usage:
  python main.py                     # 7 rounds (default)
  python main.py --rounds 3          # 3 rounds
  python main.py --rounds 5 --baseline baseline.json
"""

import argparse
import asyncio
import atexit
import ctypes
import json
import os
import sys
from datetime import datetime

from autogen_core import AgentId, SingleThreadedAgentRuntime

# Ensure our package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from config import (
    OPENAI_API_KEY, RED_TEAM_MODEL, BLUE_TEAM_MODEL, JUDGE_MODEL,
    NUM_ROUNDS,
)
from llm_client import get_client, get_provider_info
from messages import GameRoundStart, JudgeVerdict, GameSummary
from game_controller import GameControllerAgent
from cleanup import cleanup_by_prefix

# Red Team imports
from red_team.orchestrator import RedTeamOrchestrator
from red_team.attack_agent import AttackAgent

# Judge imports
from judge.judge_agent import JudgeAgent

# Blue Team imports (from poc_os_shield)
# Import via importlib to avoid sys.path collision with our own messages.py
import importlib.util

blue_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "defense", "os_shield"))

def _import_blue_modules():
    """Import all Blue Team modules with isolated sys.path."""
    # Save current path, temporarily replace with blue_path first
    saved_path = sys.path.copy()
    # Put blue_path FIRST so its messages.py is found before ours
    sys.path = [blue_path] + [p for p in saved_path if p != os.path.dirname(os.path.abspath(__file__))]

    # Force reload of messages module from blue path
    if "messages" in sys.modules:
        del sys.modules["messages"]
    if "config" in sys.modules:
        del sys.modules["config"]
    if "tools" in sys.modules:
        del sys.modules["tools"]

    import importlib
    _orchestrator = importlib.import_module("orchestrator")
    _monitor = importlib.import_module("monitor_agent")
    _analyzer = importlib.import_module("analyzer")
    _enforcer = importlib.import_module("enforcer")
    _reporter = importlib.import_module("reporter")
    _baselines = importlib.import_module("baselines")

    result = {
        "OrchestratorAgent": _orchestrator.OrchestratorAgent,
        "MonitorAgent": _monitor.MonitorAgent,
        "ThreatAnalyzerAgent": _analyzer.ThreatAnalyzerAgent,
        "EnforcerAgent": _enforcer.EnforcerAgent,
        "ReporterAgent": _reporter.ReporterAgent,
        "capture_baseline": _baselines.capture_baseline,
        "save_baseline": _baselines.save_baseline,
        "load_baseline": _baselines.load_baseline,
    }

    # Restore original sys.path and our modules
    sys.path = saved_path

    # Re-import our own messages
    if "messages" in sys.modules:
        del sys.modules["messages"]
    importlib.import_module("messages")

    return result

_blue = _import_blue_modules()
OrchestratorAgent = _blue["OrchestratorAgent"]
MonitorAgent = _blue["MonitorAgent"]
ThreatAnalyzerAgent = _blue["ThreatAnalyzerAgent"]
EnforcerAgent = _blue["EnforcerAgent"]
ReporterAgent = _blue["ReporterAgent"]
capture_baseline = _blue["capture_baseline"]
save_baseline = _blue["save_baseline"]
load_baseline = _blue["load_baseline"]


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def print_banner(num_rounds: int):
    red_info = get_provider_info("red_team")
    blue_info = get_provider_info("blue_team")
    judge_info = get_provider_info("judge")
    print()
    print("=" * 60)
    print("  RED TEAM vs BLUE TEAM")
    print("  Autonomous Adversarial Security Exercise")
    print("=" * 60)
    print(f"  Rounds:     {num_rounds}")
    print(f"  Red Team:   {RED_TEAM_MODEL} via {red_info['provider']} (Attacker)")
    print(f"  Blue Team:  {BLUE_TEAM_MODEL} via {blue_info['provider']} (Defender)")
    print(f"  Judge:      {JUDGE_MODEL} via {judge_info['provider']} (Evaluator)")
    print(f"  Started:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()


def print_game_summary(verdicts: list[dict], num_rounds: int):
    from judge.scoring import aggregate_verdicts
    agg = aggregate_verdicts(verdicts)

    print()
    print("=" * 60)
    print("  RED TEAM vs BLUE TEAM — FINAL ASSESSMENT")
    print(f"  {num_rounds} Rounds | Windows 11 | Hybrid-Safe Mode")
    print("=" * 60)
    print()
    print("  ROUND SCORES:")
    for v in verdicts:
        gaps_count = 0
        try:
            gaps = json.loads(v.get("gaps_json", "[]"))
            gaps_count = len(gaps) if isinstance(gaps, list) else 0
        except (json.JSONDecodeError, TypeError):
            pass
        print(
            f"  R{v['round_number']}: "
            f"Red {v['red_score']:.0f} | "
            f"Blue {v['blue_score']:.0f} | "
            f"Detection {v['detection_rate']:.0%} | "
            f"Gaps: {gaps_count}"
        )

    print()
    print(f"  OVERALL:")
    print(f"  Red Team:  {agg['overall_red_score']:.1f} / 100")
    print(f"  Blue Team: {agg['overall_blue_score']:.1f} / 100")
    print(f"  Avg Detection Rate: {agg['avg_detection_rate']:.0%}")
    print()

    # Aggregate gaps
    all_gaps = []
    all_recs_blue = []
    all_recs_red = []
    for v in verdicts:
        try:
            gaps = json.loads(v.get("gaps_json", "[]"))
            if isinstance(gaps, list):
                all_gaps.extend(gaps)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            recs = json.loads(v.get("recommendations_json", "{}"))
            if isinstance(recs, dict):
                all_recs_blue.extend(recs.get("blue_team", []))
                all_recs_red.extend(recs.get("red_team", []))
        except (json.JSONDecodeError, TypeError):
            pass

    if all_gaps:
        print("  TOP SECURITY GAPS:")
        seen = set()
        for i, gap in enumerate(all_gaps[:5], 1):
            desc = gap.get("description", str(gap))
            if desc not in seen:
                seen.add(desc)
                cat = gap.get("category", "")
                sev = gap.get("severity", "")
                print(f"  {i}. [{sev}] {cat}: {desc}")
        print()

    if all_recs_blue:
        print("  HARDENING EMPFEHLUNGEN (Blue Team):")
        seen = set()
        for i, rec in enumerate(all_recs_blue[:5], 1):
            if rec not in seen:
                seen.add(rec)
                print(f"  {i}. {rec}")
        print()

    print("=" * 60)
    print()


async def main():
    parser = argparse.ArgumentParser(
        description="Red Team vs Blue Team - Adversarial Security Exercise"
    )
    parser.add_argument("--rounds", type=int, default=NUM_ROUNDS, help="Number of rounds")
    parser.add_argument("--baseline", type=str, default="baseline.json", help="Baseline file")
    args = parser.parse_args()

    num_rounds = args.rounds
    print_banner(num_rounds)

    # Admin check
    if is_admin():
        print("  [OK] Running as Administrator")
    else:
        print("  [WARN] Not running as Administrator")
        print("         Some Blue Team checks will have limited access.")
    print()

    llm_client = get_client("blue_team")  # Used by all agents

    # Register failsafe cleanup
    atexit.register(lambda: asyncio.run(cleanup_by_prefix()))

    # Setup runtime
    print("  [SETUP] Registering agents...", flush=True)
    runtime = SingleThreadedAgentRuntime()

    # Red Team
    await RedTeamOrchestrator.register(
        runtime, "red_team_orchestrator",
        lambda: RedTeamOrchestrator(llm_client),
    )
    await AttackAgent.register(
        runtime, "attack_agent",
        lambda: AttackAgent(),
    )

    # Blue Team (reused from poc_os_shield)
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
        lambda: EnforcerAgent(auto_enforce=True),  # Auto-enforce in game mode
    )
    await ReporterAgent.register(
        runtime, "reporter_agent",
        lambda: ReporterAgent(),
    )

    # Judge
    await JudgeAgent.register(
        runtime, "judge_agent",
        lambda: JudgeAgent(llm_client),
    )

    # Load baseline
    baseline_path = os.path.join(blue_path, args.baseline)
    baseline = await load_baseline(baseline_path)
    if baseline is None:
        print("  [BASELINE] Capturing current system state...", flush=True)
        baseline = await capture_baseline()
        await save_baseline(baseline, baseline_path)

    # Game Controller
    await GameControllerAgent.register(
        runtime, "game_controller",
        lambda: GameControllerAgent(baseline=baseline),
    )

    runtime.start()
    print(f"  [SETUP] All agents ready. Starting {num_rounds} rounds.\n", flush=True)

    # ---- Adversarial Loop ----
    verdicts = []
    red_history = []
    blue_history = []

    for round_num in range(1, num_rounds + 1):
        verdict: JudgeVerdict = await runtime.send_message(
            GameRoundStart(
                round_number=round_num,
                total_rounds=num_rounds,
                red_history_json=json.dumps(red_history, default=str),
                blue_history_json=json.dumps(blue_history, default=str),
            ),
            AgentId("game_controller", "default"),
        )

        # Store verdict for history
        verdict_dict = {
            "round_number": verdict.round_number,
            "red_score": verdict.red_score,
            "blue_score": verdict.blue_score,
            "detection_rate": verdict.detection_rate,
            "false_positive_rate": verdict.false_positive_rate,
            "gaps_json": verdict.gaps_json,
            "recommendations_json": verdict.recommendations_json,
            "narrative": verdict.narrative,
        }
        verdicts.append(verdict_dict)

        # Update histories for next round's adaptation
        red_history.append(verdict_dict)
        blue_history.append(verdict_dict)

        # Update baseline after each round
        baseline = await capture_baseline()

    # ---- Game Over ----
    await runtime.stop()

    print_game_summary(verdicts, num_rounds)

    # Final failsafe cleanup
    await cleanup_by_prefix()

    print("  [DONE] Adversarial exercise complete.\n")


if __name__ == "__main__":
    asyncio.run(main())
