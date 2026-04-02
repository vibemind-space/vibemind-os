"""
Verification Debate Agent - Multi-Agent Debate for Requirement Verification.

This agent implements the Multi-Agent Debate pattern (AutoGen 0.4) for LLM-based
completeness verification in Phase 4. Multiple solver agents analyze requirements
from different perspectives and debate across rounds to reach a consensus.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │  VERIFICATION DEBATE AGENT                                  │
    │                                                             │
    │  ┌──────────┐   ┌──────────┐   ┌──────────┐              │
    │  │ Impl.    │◄─►│ Testing  │◄─►│ Deploy   │              │
    │  │ Solver   │   │ Solver   │   │ Solver   │              │
    │  └────┬─────┘   └────┬─────┘   └────┬─────┘              │
    │       │              │              │                     │
    │       └──────────────┼──────────────┘                     │
    │                      │                                    │
    │                      ▼                                    │
    │           ┌──────────────────┐                           │
    │           │   AGGREGATOR     │                           │
    │           │ (Majority Vote)  │                           │
    │           └──────────────────┘                           │
    └─────────────────────────────────────────────────────────────┘

Reference: https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/design-patterns/multi-agent-debate.html
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import json
import structlog

from .autonomous_base import AutonomousAgent, AgentStatus
from ..mind.event_bus import (
    EventBus, Event, EventType,
    verification_started_event,
    verification_failed_event,
    verification_passed_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool

logger = structlog.get_logger(__name__)


class VerificationVerdict(Enum):
    """Possible verdicts from verification."""
    VERIFIED = "verified"
    FAILED = "failed"
    NEEDS_MORE = "needs_more"
    INCONCLUSIVE = "inconclusive"


@dataclass
class VerificationRequest:
    """Request to verify a single requirement."""
    requirement_id: str
    requirement_text: str
    requirement_priority: str = "normal"
    code_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    related_features: list[str] = field(default_factory=list)


@dataclass
class SolverResponse:
    """Response from a single solver."""
    solver_id: str
    solver_perspective: str
    verdict: VerificationVerdict
    confidence: float  # 0.0 to 1.0
    reasoning: str
    suggested_actions: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "solver_id": self.solver_id,
            "perspective": self.solver_perspective,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "suggested_actions": self.suggested_actions,
            "evidence": self.evidence,
        }


@dataclass
class VerificationResult:
    """Final result from verification debate."""
    requirement_id: str
    verdict: VerificationVerdict
    confidence: float
    debate_rounds: int
    solver_responses: list[SolverResponse]
    actions_needed: list[str] = field(default_factory=list)
    return_to_phase3: bool = False

    def to_dict(self) -> dict:
        return {
            "requirement_id": self.requirement_id,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "debate_rounds": self.debate_rounds,
            "solver_responses": [s.to_dict() for s in self.solver_responses],
            "actions_needed": self.actions_needed,
            "return_to_phase3": self.return_to_phase3,
        }


class BaseSolver(ABC):
    """Base class for verification solvers."""

    def __init__(
        self,
        solver_id: str,
        perspective: str,
        working_dir: str,
        claude_tool: Optional[ClaudeCodeTool] = None,
    ):
        self.solver_id = solver_id
        self.perspective = perspective
        self.working_dir = working_dir
        self.claude_tool = claude_tool or ClaudeCodeTool(working_dir=working_dir, timeout=120)
        self.logger = logger.bind(solver=solver_id)

    @abstractmethod
    async def analyze(self, request: VerificationRequest) -> SolverResponse:
        """
        Analyze the requirement from this solver's perspective.

        Args:
            request: The verification request with requirement details

        Returns:
            SolverResponse with verdict and reasoning
        """
        pass

    @abstractmethod
    async def refine(
        self,
        request: VerificationRequest,
        peer_responses: list[SolverResponse],
    ) -> SolverResponse:
        """
        Refine the analysis based on peer responses (debate round).

        Args:
            request: The verification request
            peer_responses: Responses from other solvers in this round

        Returns:
            Refined SolverResponse
        """
        pass

    def _parse_verdict(self, verdict_str: str) -> VerificationVerdict:
        """Parse verdict string from LLM response."""
        verdict_lower = verdict_str.lower().strip()
        if "verified" in verdict_lower:
            return VerificationVerdict.VERIFIED
        elif "failed" in verdict_lower:
            return VerificationVerdict.FAILED
        elif "needs" in verdict_lower or "more" in verdict_lower:
            return VerificationVerdict.NEEDS_MORE
        else:
            return VerificationVerdict.INCONCLUSIVE

    def _parse_confidence(self, confidence_str: str) -> float:
        """Parse confidence score from LLM response."""
        try:
            # Try to extract a number
            import re
            match = re.search(r'(\d+(?:\.\d+)?)', confidence_str)
            if match:
                value = float(match.group(1))
                # Normalize to 0-1 range
                if value > 1:
                    value = value / 100
                return min(1.0, max(0.0, value))
        except:
            pass
        return 0.5  # Default confidence


class ImplementationSolver(BaseSolver):
    """Solver that verifies code implementation completeness."""

    def __init__(self, working_dir: str, claude_tool: Optional[ClaudeCodeTool] = None):
        super().__init__(
            solver_id="implementation_solver",
            perspective="Code Implementation Quality",
            working_dir=working_dir,
            claude_tool=claude_tool,
        )

    async def analyze(self, request: VerificationRequest) -> SolverResponse:
        """Analyze if the requirement is fully implemented."""
        prompt = f"""You are an Implementation Verification Solver. Analyze if this requirement is fully implemented.

REQUIREMENT:
ID: {request.requirement_id}
Description: {request.requirement_text}
Priority: {request.requirement_priority}

CODE FILES TO CHECK:
{chr(10).join(request.code_files[:20]) if request.code_files else "No specific files identified"}

ANALYSIS CHECKLIST:
1. Are ALL described features implemented?
2. Is the code syntactically correct?
3. Are there any missing components?
4. Does the implementation match the requirement description?
5. Are there any obvious bugs or issues?

RESPONSE FORMAT (respond with ONLY this JSON):
{{
    "verdict": "VERIFIED" | "FAILED" | "NEEDS_MORE",
    "confidence": 0.0-1.0,
    "reasoning": "Your detailed analysis...",
    "suggested_actions": ["action1", "action2"],
    "evidence": {{"key_files": [], "missing_features": [], "issues": []}}
}}
"""

        try:
            result = await self.claude_tool.execute(prompt)
            response_text = result.get("output", "") if isinstance(result, dict) else str(result)

            # Parse JSON response
            parsed = self._parse_llm_response(response_text)

            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=self._parse_verdict(parsed.get("verdict", "INCONCLUSIVE")),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                suggested_actions=parsed.get("suggested_actions", []),
                evidence=parsed.get("evidence", {}),
            )

        except Exception as e:
            self.logger.error("implementation_analysis_failed", error=str(e))
            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=VerificationVerdict.INCONCLUSIVE,
                confidence=0.0,
                reasoning=f"Analysis failed: {str(e)}",
            )

    async def refine(
        self,
        request: VerificationRequest,
        peer_responses: list[SolverResponse],
    ) -> SolverResponse:
        """Refine analysis based on peer perspectives."""
        peer_summary = "\n".join([
            f"- {r.solver_perspective}: {r.verdict.value} (confidence: {r.confidence:.2f})\n  Reasoning: {r.reasoning[:200]}..."
            for r in peer_responses
        ])

        prompt = f"""You are an Implementation Verification Solver in a debate with other solvers.

REQUIREMENT:
ID: {request.requirement_id}
Description: {request.requirement_text}

PEER RESPONSES:
{peer_summary}

Consider the peer perspectives and refine your verdict. You may change your verdict based on compelling arguments from peers.

RESPONSE FORMAT (respond with ONLY this JSON):
{{
    "verdict": "VERIFIED" | "FAILED" | "NEEDS_MORE",
    "confidence": 0.0-1.0,
    "reasoning": "Your refined analysis considering peer input...",
    "suggested_actions": ["action1", "action2"],
    "evidence": {{"key_files": [], "missing_features": [], "issues": []}}
}}
"""

        try:
            result = await self.claude_tool.execute(prompt)
            response_text = result.get("output", "") if isinstance(result, dict) else str(result)
            parsed = self._parse_llm_response(response_text)

            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=self._parse_verdict(parsed.get("verdict", "INCONCLUSIVE")),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                suggested_actions=parsed.get("suggested_actions", []),
                evidence=parsed.get("evidence", {}),
            )
        except Exception as e:
            self.logger.error("implementation_refine_failed", error=str(e))
            return await self.analyze(request)  # Fallback to original analysis

    def _parse_llm_response(self, response: str) -> dict:
        """Parse LLM response, extracting JSON if present."""
        try:
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass

        # Fallback: extract verdict from text
        verdict = "INCONCLUSIVE"
        if "VERIFIED" in response.upper():
            verdict = "VERIFIED"
        elif "FAILED" in response.upper():
            verdict = "FAILED"

        return {
            "verdict": verdict,
            "confidence": 0.5,
            "reasoning": response[:500],
            "suggested_actions": [],
            "evidence": {},
        }


class TestingSolver(BaseSolver):
    """Solver that verifies test coverage and test results."""

    def __init__(self, working_dir: str, claude_tool: Optional[ClaudeCodeTool] = None):
        super().__init__(
            solver_id="testing_solver",
            perspective="Test Coverage & Quality",
            working_dir=working_dir,
            claude_tool=claude_tool,
        )

    async def analyze(self, request: VerificationRequest) -> SolverResponse:
        """Analyze test coverage for the requirement."""
        prompt = f"""You are a Testing Verification Solver. Analyze test coverage for this requirement.

REQUIREMENT:
ID: {request.requirement_id}
Description: {request.requirement_text}

TEST FILES:
{chr(10).join(request.test_files[:20]) if request.test_files else "No test files identified"}

ANALYSIS CHECKLIST:
1. Are there tests for this requirement?
2. Do tests cover all edge cases?
3. Are tests passing?
4. Is test coverage sufficient?
5. Are there missing test scenarios?

RESPONSE FORMAT (respond with ONLY this JSON):
{{
    "verdict": "VERIFIED" | "FAILED" | "NEEDS_MORE",
    "confidence": 0.0-1.0,
    "reasoning": "Your detailed analysis...",
    "suggested_actions": ["TEST:action1", "TEST:action2"],
    "evidence": {{"test_files": [], "missing_tests": [], "coverage_gaps": []}}
}}
"""

        try:
            result = await self.claude_tool.execute(prompt)
            response_text = result.get("output", "") if isinstance(result, dict) else str(result)
            parsed = self._parse_llm_response(response_text)

            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=self._parse_verdict(parsed.get("verdict", "INCONCLUSIVE")),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                suggested_actions=parsed.get("suggested_actions", []),
                evidence=parsed.get("evidence", {}),
            )
        except Exception as e:
            self.logger.error("testing_analysis_failed", error=str(e))
            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=VerificationVerdict.INCONCLUSIVE,
                confidence=0.0,
                reasoning=f"Analysis failed: {str(e)}",
            )

    async def refine(
        self,
        request: VerificationRequest,
        peer_responses: list[SolverResponse],
    ) -> SolverResponse:
        """Refine analysis based on peer perspectives."""
        peer_summary = "\n".join([
            f"- {r.solver_perspective}: {r.verdict.value} (confidence: {r.confidence:.2f})\n  Reasoning: {r.reasoning[:200]}..."
            for r in peer_responses
        ])

        prompt = f"""You are a Testing Verification Solver in a debate with other solvers.

REQUIREMENT:
ID: {request.requirement_id}
Description: {request.requirement_text}

PEER RESPONSES:
{peer_summary}

Consider the peer perspectives and refine your verdict on test coverage.

RESPONSE FORMAT (respond with ONLY this JSON):
{{
    "verdict": "VERIFIED" | "FAILED" | "NEEDS_MORE",
    "confidence": 0.0-1.0,
    "reasoning": "Your refined analysis...",
    "suggested_actions": ["TEST:action1"],
    "evidence": {{}}
}}
"""

        try:
            result = await self.claude_tool.execute(prompt)
            response_text = result.get("output", "") if isinstance(result, dict) else str(result)
            parsed = self._parse_llm_response(response_text)

            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=self._parse_verdict(parsed.get("verdict", "INCONCLUSIVE")),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                suggested_actions=parsed.get("suggested_actions", []),
                evidence=parsed.get("evidence", {}),
            )
        except Exception as e:
            return await self.analyze(request)

    def _parse_llm_response(self, response: str) -> dict:
        """Parse LLM response."""
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass

        verdict = "INCONCLUSIVE"
        if "VERIFIED" in response.upper():
            verdict = "VERIFIED"
        elif "FAILED" in response.upper():
            verdict = "FAILED"

        return {
            "verdict": verdict,
            "confidence": 0.5,
            "reasoning": response[:500],
        }


class DeploymentSolver(BaseSolver):
    """Solver that verifies runtime behavior and deployment readiness."""

    def __init__(self, working_dir: str, claude_tool: Optional[ClaudeCodeTool] = None):
        super().__init__(
            solver_id="deployment_solver",
            perspective="Runtime & Deployment Readiness",
            working_dir=working_dir,
            claude_tool=claude_tool,
        )

    async def analyze(self, request: VerificationRequest) -> SolverResponse:
        """Analyze deployment readiness for the requirement."""
        prompt = f"""You are a Deployment Verification Solver. Analyze runtime readiness for this requirement.

REQUIREMENT:
ID: {request.requirement_id}
Description: {request.requirement_text}

CODE FILES:
{chr(10).join(request.code_files[:10]) if request.code_files else "No files identified"}

ANALYSIS CHECKLIST:
1. Will the app start without errors?
2. Does the feature work as described at runtime?
3. Are there runtime errors or crashes?
4. Is the feature accessible to users?
5. Are dependencies properly configured?

RESPONSE FORMAT (respond with ONLY this JSON):
{{
    "verdict": "VERIFIED" | "FAILED" | "NEEDS_MORE",
    "confidence": 0.0-1.0,
    "reasoning": "Your detailed analysis...",
    "suggested_actions": ["DEPLOY:action1"],
    "evidence": {{"runtime_issues": [], "deployment_blockers": []}}
}}
"""

        try:
            result = await self.claude_tool.execute(prompt)
            response_text = result.get("output", "") if isinstance(result, dict) else str(result)
            parsed = self._parse_llm_response(response_text)

            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=self._parse_verdict(parsed.get("verdict", "INCONCLUSIVE")),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                suggested_actions=parsed.get("suggested_actions", []),
                evidence=parsed.get("evidence", {}),
            )
        except Exception as e:
            self.logger.error("deployment_analysis_failed", error=str(e))
            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=VerificationVerdict.INCONCLUSIVE,
                confidence=0.0,
                reasoning=f"Analysis failed: {str(e)}",
            )

    async def refine(
        self,
        request: VerificationRequest,
        peer_responses: list[SolverResponse],
    ) -> SolverResponse:
        """Refine analysis based on peer perspectives."""
        peer_summary = "\n".join([
            f"- {r.solver_perspective}: {r.verdict.value} (confidence: {r.confidence:.2f})"
            for r in peer_responses
        ])

        prompt = f"""You are a Deployment Verification Solver in a debate.

REQUIREMENT: {request.requirement_text}

PEER RESPONSES:
{peer_summary}

Refine your deployment readiness verdict based on peer input.

RESPONSE FORMAT (JSON only):
{{
    "verdict": "VERIFIED" | "FAILED" | "NEEDS_MORE",
    "confidence": 0.0-1.0,
    "reasoning": "...",
    "suggested_actions": []
}}
"""

        try:
            result = await self.claude_tool.execute(prompt)
            response_text = result.get("output", "") if isinstance(result, dict) else str(result)
            parsed = self._parse_llm_response(response_text)

            return SolverResponse(
                solver_id=self.solver_id,
                solver_perspective=self.perspective,
                verdict=self._parse_verdict(parsed.get("verdict", "INCONCLUSIVE")),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", ""),
                suggested_actions=parsed.get("suggested_actions", []),
            )
        except Exception as e:
            return await self.analyze(request)

    def _parse_llm_response(self, response: str) -> dict:
        """Parse LLM response."""
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass

        verdict = "INCONCLUSIVE"
        if "VERIFIED" in response.upper():
            verdict = "VERIFIED"
        elif "FAILED" in response.upper():
            verdict = "FAILED"

        return {"verdict": verdict, "confidence": 0.5, "reasoning": response[:500]}


class VotingMethod(Enum):
    """Supported voting methods for verification."""
    MAJORITY = "majority"                    # Simple majority wins
    QUALIFIED_MAJORITY = "qualified_majority"  # Requires 2/3 agreement
    RANKED_CHOICE = "ranked_choice"          # Ranked preferences with elimination
    UNANIMOUS = "unanimous"                  # All must agree
    WEIGHTED_MAJORITY = "weighted_majority"  # Current default - weighted by confidence


@dataclass
class VotingConfig:
    """Configuration for verification voting."""
    method: VotingMethod = VotingMethod.WEIGHTED_MAJORITY
    qualified_threshold: float = 0.67  # For qualified majority
    require_reasoning: bool = True
    max_discussion_rounds: int = 3
    emit_events: bool = True  # For dashboard integration


class VerificationAggregator:
    """
    Aggregates solver responses using configurable voting methods.

    Supports multiple voting strategies:
    - WEIGHTED_MAJORITY: Default - votes weighted by confidence
    - MAJORITY: Simple majority wins
    - QUALIFIED_MAJORITY: Requires threshold (e.g., 2/3) agreement
    - RANKED_CHOICE: Preference ranking with elimination
    - UNANIMOUS: All solvers must agree
    """

    def __init__(self, voting_config: Optional[VotingConfig] = None):
        self.config = voting_config or VotingConfig()
        self.logger = logger.bind(component="VerificationAggregator")

    def aggregate(
        self,
        requirement_id: str,
        responses: list[SolverResponse],
        debate_rounds: int,
        voting_method: Optional[VotingMethod] = None,
    ) -> VerificationResult:
        """
        Aggregate solver responses using configurable voting method.

        Args:
            requirement_id: ID of the requirement being verified
            responses: Final responses from all solvers
            debate_rounds: Number of debate rounds completed
            voting_method: Optional override for voting method

        Returns:
            VerificationResult with final verdict
        """
        if not responses:
            return VerificationResult(
                requirement_id=requirement_id,
                verdict=VerificationVerdict.INCONCLUSIVE,
                confidence=0.0,
                debate_rounds=debate_rounds,
                solver_responses=[],
            )

        # Use configured or overridden voting method
        method = voting_method or self.config.method

        # Apply voting method
        if method == VotingMethod.WEIGHTED_MAJORITY:
            winning_verdict, winning_confidence = self._weighted_majority(responses)
        elif method == VotingMethod.MAJORITY:
            winning_verdict, winning_confidence = self._simple_majority(responses)
        elif method == VotingMethod.QUALIFIED_MAJORITY:
            winning_verdict, winning_confidence = self._qualified_majority(responses)
        elif method == VotingMethod.RANKED_CHOICE:
            winning_verdict, winning_confidence = self._ranked_choice(responses)
        elif method == VotingMethod.UNANIMOUS:
            winning_verdict, winning_confidence = self._unanimous(responses)
        else:
            winning_verdict, winning_confidence = self._weighted_majority(responses)

        # Collect all suggested actions
        all_actions = []
        for response in responses:
            if response.verdict == VerificationVerdict.FAILED:
                all_actions.extend(response.suggested_actions)

        # Determine if we need to return to Phase 3
        return_to_phase3 = (
            winning_verdict == VerificationVerdict.FAILED or
            winning_verdict == VerificationVerdict.NEEDS_MORE
        )

        self.logger.info(
            "verification_aggregated",
            requirement_id=requirement_id,
            voting_method=method.value,
            verdict=winning_verdict.value,
            confidence=winning_confidence,
        )

        return VerificationResult(
            requirement_id=requirement_id,
            verdict=winning_verdict,
            confidence=winning_confidence,
            debate_rounds=debate_rounds,
            solver_responses=responses,
            actions_needed=list(set(all_actions)),
            return_to_phase3=return_to_phase3,
        )

    def _weighted_majority(
        self,
        responses: list[SolverResponse],
    ) -> tuple[VerificationVerdict, float]:
        """Weighted majority voting - votes weighted by confidence."""
        verdict_scores = {v: 0.0 for v in VerificationVerdict}

        for response in responses:
            verdict_scores[response.verdict] += response.confidence

        winning_verdict = max(verdict_scores, key=verdict_scores.get)
        total_score = sum(verdict_scores.values())
        winning_confidence = verdict_scores[winning_verdict] / total_score if total_score > 0 else 0

        return winning_verdict, winning_confidence

    def _simple_majority(
        self,
        responses: list[SolverResponse],
    ) -> tuple[VerificationVerdict, float]:
        """Simple majority voting - each vote counts equally."""
        verdict_counts = {v: 0 for v in VerificationVerdict}

        for response in responses:
            verdict_counts[response.verdict] += 1

        winning_verdict = max(verdict_counts, key=verdict_counts.get)
        total_votes = len(responses)
        winning_ratio = verdict_counts[winning_verdict] / total_votes if total_votes > 0 else 0

        # Confidence based on vote ratio and average solver confidence
        avg_confidence = sum(r.confidence for r in responses if r.verdict == winning_verdict) / max(1, verdict_counts[winning_verdict])
        winning_confidence = (winning_ratio + avg_confidence) / 2

        return winning_verdict, winning_confidence

    def _qualified_majority(
        self,
        responses: list[SolverResponse],
    ) -> tuple[VerificationVerdict, float]:
        """Qualified majority - requires threshold agreement (e.g., 2/3)."""
        verdict_counts = {v: 0 for v in VerificationVerdict}

        for response in responses:
            verdict_counts[response.verdict] += 1

        total_votes = len(responses)
        threshold = self.config.qualified_threshold

        # Check if any verdict meets threshold
        for verdict, count in verdict_counts.items():
            ratio = count / total_votes if total_votes > 0 else 0
            if ratio >= threshold:
                avg_confidence = sum(r.confidence for r in responses if r.verdict == verdict) / max(1, count)
                return verdict, avg_confidence

        # No consensus - return most common with reduced confidence
        winning_verdict = max(verdict_counts, key=verdict_counts.get)
        winning_ratio = verdict_counts[winning_verdict] / total_votes if total_votes > 0 else 0

        # Penalize confidence for not reaching threshold
        penalty = (threshold - winning_ratio) / threshold
        avg_confidence = sum(r.confidence for r in responses if r.verdict == winning_verdict) / max(1, verdict_counts[winning_verdict])
        adjusted_confidence = avg_confidence * (1 - penalty * 0.5)

        return winning_verdict, adjusted_confidence

    def _ranked_choice(
        self,
        responses: list[SolverResponse],
    ) -> tuple[VerificationVerdict, float]:
        """Ranked choice voting with elimination."""
        # For simplicity, use verdict preference order based on confidence
        # Higher confidence verdicts are ranked higher

        # Group responses by verdict with their confidence
        verdict_confidences = {}
        for response in responses:
            if response.verdict not in verdict_confidences:
                verdict_confidences[response.verdict] = []
            verdict_confidences[response.verdict].append(response.confidence)

        # Calculate total confidence for each verdict (as a proxy for rank)
        verdict_totals = {
            v: sum(confs) for v, confs in verdict_confidences.items()
        }

        if not verdict_totals:
            return VerificationVerdict.INCONCLUSIVE, 0.0

        # Sort by total confidence and pick winner
        sorted_verdicts = sorted(verdict_totals.items(), key=lambda x: x[1], reverse=True)
        winning_verdict = sorted_verdicts[0][0]

        # Confidence is based on proportion of total
        total = sum(verdict_totals.values())
        winning_confidence = verdict_totals[winning_verdict] / total if total > 0 else 0

        return winning_verdict, winning_confidence

    def _unanimous(
        self,
        responses: list[SolverResponse],
    ) -> tuple[VerificationVerdict, float]:
        """Unanimous voting - all solvers must agree."""
        if not responses:
            return VerificationVerdict.INCONCLUSIVE, 0.0

        first_verdict = responses[0].verdict
        all_agree = all(r.verdict == first_verdict for r in responses)

        if all_agree:
            avg_confidence = sum(r.confidence for r in responses) / len(responses)
            return first_verdict, avg_confidence
        else:
            # No consensus - return INCONCLUSIVE with low confidence
            return VerificationVerdict.INCONCLUSIVE, 0.2


class VerificationDebateAgent(AutonomousAgent):
    """
    Agent that orchestrates Multi-Agent Debate for requirement verification.

    Uses multiple solver agents with different perspectives to verify
    that each requirement has been fully implemented, tested, and is
    deployment-ready.

    Triggered by: GENERATION_COMPLETE, CONVERGENCE_ACHIEVED
    Publishes: VERIFICATION_PASSED, VERIFICATION_FAILED
    """

    def __init__(
        self,
        name: str = "VerificationDebate",
        event_bus: Optional[EventBus] = None,  # Task 25: Fixed type annotation
        shared_state: Optional[SharedState] = None,  # Task 25: Fixed type annotation
        working_dir: str = ".",
        requirements: Optional[list[dict]] = None,  # Task 25: Fixed type annotation
        num_debate_rounds: int = 3,
        memory_tool: Optional[Any] = None,
        voting_config: Optional[VotingConfig] = None,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            memory_tool=memory_tool,
        )

        self.requirements = requirements or []
        self.num_debate_rounds = num_debate_rounds
        self.voting_config = voting_config or VotingConfig()

        # Initialize solvers
        self.solvers = [
            ImplementationSolver(working_dir=working_dir),
            TestingSolver(working_dir=working_dir),
            DeploymentSolver(working_dir=working_dir),
        ]

        # Aggregator for final verdict with voting config
        self.aggregator = VerificationAggregator(voting_config=self.voting_config)

        # Track verification state
        self._verified_requirements: set[str] = set()
        self._failed_requirements: set[str] = set()

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events that trigger verification."""
        return [
            EventType.GENERATION_COMPLETE,
            EventType.CONVERGENCE_ACHIEVED,
            EventType.VERIFICATION_STARTED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Check if we should run verification."""
        for event in events:
            if event.type in self.subscribed_events:
                # Check if we have requirements to verify
                if self.requirements:
                    return True
                # Check if requirements are in event data
                if event.data and event.data.get("requirements"):
                    return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Run verification debate for all requirements."""
        self.logger.info("starting_verification_debate")

        # Get requirements to verify
        requirements_to_verify = self.requirements.copy()

        for event in events:
            if event.data and event.data.get("requirements"):
                requirements_to_verify.extend(event.data["requirements"])

        if not requirements_to_verify:
            self.logger.warning("no_requirements_to_verify")
            return None

        # Publish start event
        await self.event_bus.publish(verification_started_event(
            source=self.name,
            requirement_count=len(requirements_to_verify),
        ))

        # Verify each requirement
        results: list[VerificationResult] = []

        for req in requirements_to_verify:
            if isinstance(req, dict):
                req_id = req.get("id", str(len(results)))
                req_text = req.get("title") or req.get("description") or str(req)
                req_priority = req.get("priority", "normal")
            else:
                req_id = str(len(results))
                req_text = str(req)
                req_priority = "normal"

            # Skip already verified requirements
            if req_id in self._verified_requirements:
                continue

            # Create verification request
            ver_request = VerificationRequest(
                requirement_id=req_id,
                requirement_text=req_text,
                requirement_priority=req_priority,
                code_files=self._find_code_files(req_id),
                test_files=self._find_test_files(req_id),
            )

            # Run multi-agent debate
            result = await self._run_debate(ver_request)
            results.append(result)

            # Track verified/failed
            if result.verdict == VerificationVerdict.VERIFIED:
                self._verified_requirements.add(req_id)
            elif result.verdict == VerificationVerdict.FAILED:
                self._failed_requirements.add(req_id)

                # Publish failure event for Phase 3 to handle
                await self.event_bus.publish(verification_failed_event(
                    source=self.name,
                    requirement_id=req_id,
                    actions_needed=result.actions_needed,
                    result=result.to_dict(),
                ))

        # Calculate overall result
        verified_count = sum(1 for r in results if r.verdict == VerificationVerdict.VERIFIED)
        failed_count = sum(1 for r in results if r.verdict == VerificationVerdict.FAILED)
        total_count = len(results)

        overall_success = failed_count == 0 and verified_count == total_count

        self.logger.info(
            "verification_complete",
            verified=verified_count,
            failed=failed_count,
            total=total_count,
            success=overall_success,
        )

        # Update shared state
        await self.shared_state.update_metrics(
            verification_complete=True,
            verification_pass_rate=verified_count / total_count if total_count > 0 else 0,
        )

        # Publish final result event
        if overall_success:
            return verification_passed_event(
                source=self.name,
                verified_count=verified_count,
                failed_count=failed_count,
                total_count=total_count,
                results=[r.to_dict() for r in results],
            )
        else:
            return verification_failed_event(
                source=self.name,
                result={
                    "verified_count": verified_count,
                    "failed_count": failed_count,
                    "total_count": total_count,
                    "results": [r.to_dict() for r in results],
                },
            )

    async def _run_debate(self, request: VerificationRequest) -> VerificationResult:
        """
        Run multi-agent debate for a single requirement.

        Process:
        1. Initial analysis from each solver
        2. Multiple debate rounds where solvers refine based on peers
        3. Final aggregation with majority voting
        """
        self.logger.info(
            "debate_starting",
            requirement_id=request.requirement_id,
            rounds=self.num_debate_rounds,
        )

        # Step 1: Initial analysis from each solver (parallel)
        initial_tasks = [solver.analyze(request) for solver in self.solvers]
        responses = await asyncio.gather(*initial_tasks)

        # Step 2: Debate rounds
        for round_num in range(self.num_debate_rounds):
            self.logger.debug(
                "debate_round",
                round=round_num + 1,
                requirement_id=request.requirement_id,
            )

            # Each solver refines based on peer responses
            new_responses = []
            for i, solver in enumerate(self.solvers):
                peer_responses = [r for j, r in enumerate(responses) if j != i]
                refined = await solver.refine(request, peer_responses)
                new_responses.append(refined)

            responses = new_responses

        # Step 3: Final aggregation
        result = self.aggregator.aggregate(
            requirement_id=request.requirement_id,
            responses=responses,
            debate_rounds=self.num_debate_rounds,
        )

        self.logger.info(
            "debate_complete",
            requirement_id=request.requirement_id,
            verdict=result.verdict.value,
            confidence=result.confidence,
        )

        return result

    def _find_code_files(self, requirement_id: str) -> list[str]:
        """Find code files related to a requirement."""
        code_files = []
        working_path = Path(self.working_dir)

        # Search for files that might relate to this requirement
        for pattern in ["**/*.ts", "**/*.tsx", "**/*.py", "**/*.js", "**/*.jsx"]:
            for file_path in working_path.glob(pattern):
                # Skip node_modules and other ignore dirs
                if "node_modules" in str(file_path):
                    continue

                rel_path = str(file_path.relative_to(working_path))
                code_files.append(rel_path)

                # Limit to prevent overwhelming the LLM
                if len(code_files) >= 50:
                    break

        return code_files

    def _find_test_files(self, requirement_id: str) -> list[str]:
        """Find test files related to a requirement."""
        test_files = []
        working_path = Path(self.working_dir)

        for pattern in ["**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/test_*.py", "**/*_test.py"]:
            for file_path in working_path.glob(pattern):
                if "node_modules" in str(file_path):
                    continue

                rel_path = str(file_path.relative_to(working_path))
                test_files.append(rel_path)

                if len(test_files) >= 20:
                    break

        return test_files

    def get_verification_status(self) -> dict:
        """Get current verification status."""
        pending = []
        if self.requirements and isinstance(self.requirements[0], dict):
            pending = [
                r.get("id", i) for i, r in enumerate(self.requirements)
                if r.get("id", i) not in self._verified_requirements
                and r.get("id", i) not in self._failed_requirements
            ]

        return {
            "verified": list(self._verified_requirements),
            "failed": list(self._failed_requirements),
            "pending": pending,
        }
