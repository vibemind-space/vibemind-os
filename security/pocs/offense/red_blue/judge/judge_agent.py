"""
JudgeAgent - Impartial Round Evaluator
==========================================
Uses LLM to evaluate each round: compares Red Team ground truth
against Blue Team detections, scores both teams, identifies gaps.
"""

import json

from openai import AsyncOpenAI

from autogen_core import RoutedAgent, message_handler, MessageContext

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from messages import JudgeRequest, JudgeVerdict
from config import JUDGE_MODEL
from judge.scoring import compute_detection_rate, compute_false_positive_rate, compute_scores, compute_response_score, compute_resilience_score


class JudgeAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("JudgeAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_judge_request(
        self, message: JudgeRequest, ctx: MessageContext
    ) -> JudgeVerdict:
        print(f"\n  [JUDGE] Evaluating round {message.round_number}...", flush=True)

        # Parse inputs
        try:
            attacks = json.loads(message.attack_ground_truth_json)
        except (json.JSONDecodeError, TypeError):
            attacks = []

        try:
            blue_report = json.loads(message.blue_report_json)
        except (json.JSONDecodeError, TypeError):
            blue_report = {}

        # Extract Blue Team findings
        blue_findings = []
        if isinstance(blue_report, dict):
            try:
                findings_str = blue_report.get("findings_json", "[]")
                if isinstance(findings_str, str):
                    blue_findings = json.loads(findings_str)
                elif isinstance(findings_str, list):
                    blue_findings = findings_str
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract report text for broader matching
        blue_report_text = ""
        if isinstance(blue_report, dict):
            blue_report_text = blue_report.get("report_text", "")

        # Deterministic scoring
        successful_attacks = [a for a in attacks if a.get("success", False)]
        detection_rate, detected, undetected = compute_detection_rate(
            successful_attacks, blue_findings, blue_report_text=blue_report_text
        )
        false_positive_rate = compute_false_positive_rate(blue_findings, successful_attacks)

        categories_used = len(set(a.get("category", "") for a in successful_attacks))

        # Compute response_score from enforcement_results in blue_report
        enforcement_results = blue_report.get("enforcement_results", []) if isinstance(blue_report, dict) else []
        if not isinstance(enforcement_results, list):
            enforcement_results = []
        recommended_count = len(blue_findings)
        response_score = compute_response_score(enforcement_results, recommended_count)

        # Resilience score placeholder (game_controller will override later)
        resilience_score = 100.0

        red_score, blue_score = compute_scores(
            detection_rate, false_positive_rate, len(successful_attacks), categories_used,
            response_score=response_score, resilience_score=resilience_score,
        )

        print(f"  [JUDGE] Detection: {detection_rate:.0%} | Red: {red_score:.0f} | Blue: {blue_score:.0f}", flush=True)

        # LLM analysis for gaps and recommendations
        gaps, recommendations, narrative = await self._llm_analysis(
            message.round_number, attacks, blue_report,
            detected, undetected, detection_rate,
            red_score, blue_score,
        )

        return JudgeVerdict(
            round_number=message.round_number,
            red_score=round(red_score, 1),
            blue_score=round(blue_score, 1),
            detection_rate=round(detection_rate, 3),
            false_positive_rate=round(false_positive_rate, 3),
            response_score=round(response_score, 1),
            resilience_score=round(resilience_score, 1),
            gaps_json=json.dumps(gaps, ensure_ascii=False),
            recommendations_json=json.dumps(recommendations, ensure_ascii=False),
            narrative=narrative,
        )

    async def _llm_analysis(
        self,
        round_number: int,
        attacks: list,
        blue_report: dict,
        detected: list,
        undetected: list,
        detection_rate: float,
        red_score: float,
        blue_score: float,
    ) -> tuple[list, dict, str]:
        """Use LLM for qualitative gap analysis and recommendations."""

        system_prompt = (
            "Du bist ein neutraler Schiedsrichter fuer eine Red Team vs Blue Team Sicherheitsuebung.\n"
            "Analysiere die Ergebnisse dieser Runde und identifiziere:\n"
            "1. GAPS: Welche Angriffe wurden nicht erkannt und warum?\n"
            "2. RECOMMENDATIONS: Was sollte jedes Team verbessern?\n"
            "3. NARRATIVE: Eine kurze Zusammenfassung der Runde.\n\n"
            "Antworte IMMER im folgenden JSON-Format:\n"
            "```json\n"
            "{\n"
            '  "gaps": [{"category": "...", "description": "...", "severity": "HIGH|MEDIUM|LOW"}],\n'
            '  "recommendations": {\n'
            '    "blue_team": ["..."],\n'
            '    "red_team": ["..."]\n'
            '  },\n'
            '  "narrative": "..."\n'
            "}\n"
            "```"
        )

        user_prompt = (
            f"RUNDE {round_number} ERGEBNISSE:\n\n"
            f"DETECTION RATE: {detection_rate:.0%}\n"
            f"RED SCORE: {red_score:.0f}/100\n"
            f"BLUE SCORE: {blue_score:.0f}/100\n\n"
            f"ERKANNTE ANGRIFFE ({len(detected)}):\n"
            f"{json.dumps(detected, indent=2, ensure_ascii=False, default=str)[:2000]}\n\n"
            f"NICHT ERKANNTE ANGRIFFE ({len(undetected)}):\n"
            f"{json.dumps(undetected, indent=2, ensure_ascii=False, default=str)[:2000]}\n\n"
            f"BLUE TEAM REPORT:\n"
            f"{json.dumps(blue_report, indent=2, ensure_ascii=False, default=str)[:2000]}\n\n"
            "Analysiere die Ergebnisse und gib dein Urteil ab."
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=JUDGE_MODEL,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            content = response.choices[0].message.content or ""

            # Parse JSON from response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(content[json_start:json_end])
                return (
                    result.get("gaps", []),
                    result.get("recommendations", {}),
                    result.get("narrative", ""),
                )
        except Exception as e:
            print(f"  [JUDGE] LLM analysis error: {e}", flush=True)

        # Fallback
        return (
            [{"category": "unknown", "description": "LLM analysis failed", "severity": "LOW"}],
            {"blue_team": [], "red_team": []},
            f"Runde {round_number}: {detection_rate:.0%} Detection Rate.",
        )
