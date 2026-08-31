"""
Red vs Blue - Message Types
==============================
All dataclass messages for Red/Blue/Judge/Game communication.
"""

from dataclasses import dataclass


# ================================================================
# Game Control
# ================================================================

@dataclass
class GameRoundStart:
    """Sent by main.py to GameController to start a round."""
    round_number: int
    total_rounds: int
    red_history_json: str      # JSON: previous rounds' Red results (for adaptation)
    blue_history_json: str     # JSON: previous rounds' Blue findings


@dataclass
class AttackPlan:
    """Red Team Orchestrator's planned attacks for a round."""
    round_number: int
    attacks_json: str           # JSON array of planned attacks
    strategy_reasoning: str     # LLM reasoning about strategy


@dataclass
class AttackTask:
    """Dispatched from RedTeamOrchestrator to AttackAgent."""
    tool_name: str
    arguments_json: str
    task_id: str
    category: str               # evasion, persistence, lateral, credential, exfil, defense_evasion


@dataclass
class AttackResult:
    """Returned from AttackAgent after executing an attack tool."""
    task_id: str
    tool_name: str
    success: bool
    result_json: str
    category: str


@dataclass
class AttackPhaseComplete:
    """Red Team finished all attacks for a round."""
    round_number: int
    attacks_executed_json: str   # JSON: all attacks and results (ground truth)
    artifacts_created_json: str  # JSON: artifact manifest for cleanup


@dataclass
class DetectionPhaseComplete:
    """Blue Team finished scanning for a round."""
    round_number: int
    blue_report_json: str        # Serialized Blue Team SecurityReport


# ================================================================
# Reports
# ================================================================

@dataclass
class RedTeamReport:
    """Red Team's round summary."""
    round_number: int
    attacks_executed: int
    attacks_detected: int
    attacks_undetected: int
    techniques_json: str         # JSON: techniques used per category
    narrative: str               # Human-readable summary


@dataclass
class BlueTeamReport:
    """Blue Team's round summary."""
    round_number: int
    findings_count: int
    actions_taken: int
    severity: str
    narrative: str


# ================================================================
# Judge
# ================================================================

@dataclass
class JudgeRequest:
    """Sent to JudgeAgent for round evaluation."""
    round_number: int
    red_report_json: str
    blue_report_json: str
    attack_ground_truth_json: str  # What Red actually did (for scoring accuracy)


@dataclass
class JudgeVerdict:
    """JudgeAgent's evaluation of a round."""
    round_number: int
    red_score: float              # 0-100
    blue_score: float             # 0-100
    detection_rate: float         # 0.0-1.0
    false_positive_rate: float    # 0.0-1.0
    response_score: float             # 0-100: what % of threats were remediated
    resilience_score: float           # 0-100: is VM still compromised after response
    gaps_json: str                # JSON: identified security gaps
    recommendations_json: str     # JSON: recommendations for both teams
    narrative: str                # Human-readable verdict


# ================================================================
# Game Summary
# ================================================================

@dataclass
class GameSummary:
    """Final summary across all rounds."""
    total_rounds: int
    verdicts_json: str            # JSON: all JudgeVerdicts
    overall_red_score: float
    overall_blue_score: float
    avg_detection_rate: float
    summary_text: str             # Human-readable final report
