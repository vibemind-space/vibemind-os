"""
GameControllerAgent - Adversarial Round Manager
===================================================
Manages the flow of each round:
  1. Red Team attacks
  2. Settle pause
  3. Blue Team detection
  4. Judge evaluation
  5. Cleanup
"""

import asyncio
import json

from autogen_core import (
    AgentId,
    RoutedAgent,
    message_handler,
    MessageContext,
)

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "defense", "os_shield"))

from messages import (
    GameRoundStart, AttackPhaseComplete,
    JudgeRequest, JudgeVerdict,
    RedTeamReport, BlueTeamReport,
)
from config import SETTLE_PAUSE, USE_INTEGRATED_PIPELINE, PIPELINE_ALERT_ENABLED
from cleanup import cleanup_round
from infra import check_all_targets, get_available_target_summary

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "red_team"))
from win_conditions import check_win_conditions, declare_red_wins

# Blue Team imports
try:
    from poc_os_shield_messages import ShieldRequest as BlueShieldRequest
    from poc_os_shield_messages import SecurityReport as BlueSecurityReport
except ImportError:
    # Will be imported via sys.path in main.py
    pass


class GameControllerAgent(RoutedAgent):

    def __init__(self, baseline: dict | None = None):
        super().__init__("GameControllerAgent")
        self._baseline = baseline

    @message_handler
    async def handle_round(
        self, message: GameRoundStart, ctx: MessageContext
    ) -> JudgeVerdict:
        round_num = message.round_number
        total = message.total_rounds

        print(f"\n{'=' * 60}", flush=True)
        print(f"  ROUND {round_num}/{total}", flush=True)
        print(f"{'=' * 60}", flush=True)

        # ---- Phase 0: Infrastructure Check ----
        targets = check_all_targets()
        active = [k for k, v in targets.items() if v]
        if active:
            print(f"  [GAME] External targets: {', '.join(active)}", flush=True)
        else:
            print(f"  [GAME] No external targets (local simulation only)", flush=True)

        # ---- Phase 1: Red Team Attack ----
        print(f"\n  [GAME] Phase 1: Red Team Attack...", flush=True)

        attack_result: AttackPhaseComplete = await self.send_message(
            message,
            recipient=AgentId("red_team_orchestrator", "default"),
        )

        # Parse attack results for ground truth
        try:
            attacks = json.loads(attack_result.attacks_executed_json)
        except (json.JSONDecodeError, TypeError):
            attacks = []

        successful_attacks = [a for a in attacks if a.get("success", False)]
        categories = set(a.get("category", "") for a in successful_attacks)

        print(
            f"  [GAME] Red Team: {len(successful_attacks)} attacks "
            f"across {len(categories)} categories",
            flush=True,
        )

        # ---- Win Condition Check (after Red Team) ----
        win = check_win_conditions()
        if win:
            print(f"\n  [GAME] *** RED TEAM ACHIEVED WIN CONDITION: {win['name']} ***", flush=True)
            declare_red_wins(win)
            # Still run Blue Team for scoring, but Red has already won

        # ---- Phase 2: Settle Pause ----
        print(f"  [GAME] Phase 2: Settle pause ({SETTLE_PAUSE}s)...", flush=True)
        await asyncio.sleep(SETTLE_PAUSE)

        # ---- Phase 3: Blue Team Detection ----
        print(f"  [GAME] Phase 3: Blue Team Scan...", flush=True)

        if USE_INTEGRATED_PIPELINE:
            # Use integrated pipeline for richer detection
            print(f"  [GAME] Using integrated pipeline (OS Shield + Log Analyzer + Forensics)...", flush=True)
            blue_report_dict = await self._run_pipeline_scan(round_num)
        else:
            # Standard Blue Team scan via OrchestratorAgent
            blue_report_dict = await self._run_standard_blue_scan(round_num)

        # ---- Phase 4: Judge ----
        print(f"  [GAME] Phase 4: Judge evaluation...", flush=True)

        verdict: JudgeVerdict = await self.send_message(
            JudgeRequest(
                round_number=round_num,
                red_report_json=json.dumps({
                    "attacks_executed": len(successful_attacks),
                    "categories": list(categories),
                    "attacks": successful_attacks,
                }, default=str),
                blue_report_json=json.dumps(blue_report_dict, default=str),
                attack_ground_truth_json=attack_result.attacks_executed_json,
            ),
            recipient=AgentId("judge_agent", "default"),
        )

        # Print round summary
        print(f"\n  {'-' * 50}", flush=True)
        print(f"  ROUND {round_num} VERDICT:", flush=True)
        print(f"    Red Score:  {verdict.red_score:.0f}/100", flush=True)
        print(f"    Blue Score: {verdict.blue_score:.0f}/100", flush=True)
        print(f"    Detection:  {verdict.detection_rate:.0%}", flush=True)
        print(f"    FP Rate:    {verdict.false_positive_rate:.0%}", flush=True)
        if verdict.narrative:
            print(f"    {verdict.narrative[:200]}", flush=True)
        print(f"  {'-' * 50}", flush=True)

        # ---- Phase 5: Cleanup ----
        print(f"  [GAME] Phase 5: Cleanup...", flush=True)
        await cleanup_round(attack_result.artifacts_created_json)

        # VM cleanup if VM attacks were used
        try:
            from red_team.vm_attack_tools import vm_cleanup_all
            attacks = json.loads(attack_result.attacks_executed_json)
            vm_attacks = [a for a in attacks if a.get("category", "").startswith("vm_")]
            if vm_attacks:
                print(f"  [GAME] VM Cleanup ({len(vm_attacks)} VM attacks)...", flush=True)
                await vm_cleanup_all()
        except ImportError:
            pass

        # ---- Phase 6: Save Round Report ----
        print(f"  [GAME] Phase 6: Saving round report...", flush=True)
        await self._save_round_report(round_num, attacks, blue_report_dict, verdict)

        return verdict

    async def _save_round_report(self, round_num, attacks, blue_report, verdict):
        """Save detailed round report to file."""
        report_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(report_dir, exist_ok=True)

        report = {
            "round": round_num,
            "red_team": {
                "attacks_executed": len([a for a in attacks if a.get("success")]),
                "attacks_failed": len([a for a in attacks if not a.get("success")]),
                "categories": list(set(a.get("category", "") for a in attacks)),
                "attacks": attacks,
            },
            "blue_team": blue_report,
            "verdict": {
                "red_score": verdict.red_score,
                "blue_score": verdict.blue_score,
                "detection_rate": verdict.detection_rate,
                "false_positive_rate": verdict.false_positive_rate,
                "narrative": verdict.narrative,
                "gaps": verdict.gaps_json,
                "recommendations": verdict.recommendations_json,
            },
        }

        filepath = os.path.join(report_dir, f"round_{round_num:02d}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        print(f"  [GAME] Report saved: {filepath}", flush=True)

    async def _run_standard_blue_scan(self, round_num: int) -> dict:
        """Run standard Blue Team scan via OrchestratorAgent."""
        blue_messages = _import_blue_messages()
        ShieldRequest = blue_messages["ShieldRequest"]
        SecurityReport = blue_messages["SecurityReport"]

        baseline_json = json.dumps(self._baseline) if self._baseline else ""

        blue_report = await self.send_message(
            ShieldRequest(
                scan_domains="process,network,registry,usb,binary",
                mode=f"redblue_round_{round_num}",
                baseline_json=baseline_json,
            ),
            recipient=AgentId("orchestrator_agent", "default"),
        )

        if blue_report is None:
            print("  [GAME] WARNING: Blue Team returned None! Using fallback.", flush=True)
            return {
                "report_text": "Blue Team scan returned no results.",
                "overall_severity": "UNKNOWN",
                "finding_count": 0,
                "actions_taken": 0,
            }

        print(
            f"  [GAME] Blue Team: {blue_report.finding_count} findings, "
            f"severity={blue_report.overall_severity}",
            flush=True,
        )
        return {
            "report_text": blue_report.report_text[:3000],
            "overall_severity": blue_report.overall_severity,
            "finding_count": blue_report.finding_count,
            "actions_taken": blue_report.actions_taken,
        }

    async def _run_pipeline_scan(self, round_num: int) -> dict:
        """Run integrated detection pipeline (OS Shield + Log Analyzer + Forensics)."""
        try:
            pipeline_path = os.path.join(os.path.dirname(__file__), "..", "..", "defense", "os_shield")
            if pipeline_path not in sys.path:
                sys.path.insert(0, os.path.abspath(pipeline_path))

            from pipeline import run_integrated_scan

            pipeline_result = await run_integrated_scan(
                baseline=self._baseline,
                hours=1,  # Only look at last hour for game context
                alert_enabled=PIPELINE_ALERT_ENABLED,
            )

            finding_count = pipeline_result.get("finding_count", 0)
            by_severity = pipeline_result.get("by_severity", {})
            by_source = pipeline_result.get("by_source", {})
            overall_severity = _highest_severity(by_severity)

            print(
                f"  [GAME] Pipeline: {finding_count} findings, "
                f"severity={overall_severity}, "
                f"sources={json.dumps(by_source)}",
                flush=True,
            )

            # Build report text from top findings
            top_findings = pipeline_result.get("findings", [])[:20]
            report_lines = []
            for f in top_findings:
                report_lines.append(
                    f"[{f.get('severity')}] {f.get('source')}: "
                    f"{f.get('title', '')[:100]}"
                )

            return {
                "report_text": "\n".join(report_lines)[:3000],
                "overall_severity": overall_severity,
                "finding_count": finding_count,
                "actions_taken": 0,
                "pipeline_sources": by_source,
                "correlations": pipeline_result.get("correlations", []),
            }

        except Exception as e:
            print(f"  [GAME] Pipeline error: {e}. Falling back to standard scan.", flush=True)
            return await self._run_standard_blue_scan(round_num)


def _highest_severity(severity_counts: dict) -> str:
    """Return the highest severity level that has a count > 0."""
    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        if severity_counts.get(level, 0) > 0:
            return level
    return "INFO"


def _import_blue_messages():
    """Get Blue Team message types from the already-loaded modules.

    The Blue Team OrchestratorAgent was loaded in main.py and registered
    its message types. We must use the SAME classes (same identity in memory)
    for autogen message routing to work.
    """
    # The Blue Team modules were loaded in main.py and stored in sys.modules
    # under their blue_path names. Find the messages module that the
    # OrchestratorAgent is actually using.

    # Check all loaded modules for ShieldRequest
    for mod_name, mod in sys.modules.items():
        if hasattr(mod, "ShieldRequest") and hasattr(mod, "SecurityReport"):
            # Make sure it's the OS Shield one (has scan_domains field)
            sr = mod.ShieldRequest
            if hasattr(sr, "__dataclass_fields__") and "scan_domains" in sr.__dataclass_fields__:
                return {
                    "ShieldRequest": sr,
                    "SecurityReport": mod.SecurityReport,
                }

    # Fallback: direct import from file
    import importlib.util
    blue_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "defense", "os_shield"))
    spec = importlib.util.spec_from_file_location(
        "blue_messages",
        os.path.join(blue_path, "messages.py"),
    )
    blue_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(blue_mod)

    return {
        "ShieldRequest": blue_mod.ShieldRequest,
        "SecurityReport": blue_mod.SecurityReport,
    }
