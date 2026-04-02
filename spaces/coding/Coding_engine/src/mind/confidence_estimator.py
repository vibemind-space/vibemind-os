"""
ConfidenceEstimator - Fix Success Probability Estimation.

Estimates the likelihood of a fix succeeding based on:
1. Error type base confidence (historical patterns)
2. Pattern matching (high/low confidence indicators)
3. Historical success rates (within-session learning)
4. Available context quality (files, stack traces, etc.)

Used by EscalationManager to decide when to escalate vs. retry.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from src.mind.escalation_manager import EscalationLevel

logger = structlog.get_logger(__name__)


class ConfidenceCategory(Enum):
    """Categories that affect confidence estimation."""

    VERY_HIGH = "very_high"  # 0.85-1.0
    HIGH = "high"  # 0.65-0.84
    MEDIUM = "medium"  # 0.40-0.64
    LOW = "low"  # 0.20-0.39
    VERY_LOW = "very_low"  # 0.0-0.19


@dataclass
class ConfidenceScore:
    """Detailed confidence score with component breakdown."""

    overall: float  # 0.0 - 1.0 combined score
    historical: float  # Based on past success rates
    complexity: float  # Based on error complexity
    context_quality: float  # Based on available context
    explanation: str  # Human-readable reasoning
    category: ConfidenceCategory = field(init=False)

    def __post_init__(self) -> None:
        """Set category based on overall score."""
        if self.overall >= 0.85:
            self.category = ConfidenceCategory.VERY_HIGH
        elif self.overall >= 0.65:
            self.category = ConfidenceCategory.HIGH
        elif self.overall >= 0.40:
            self.category = ConfidenceCategory.MEDIUM
        elif self.overall >= 0.20:
            self.category = ConfidenceCategory.LOW
        else:
            self.category = ConfidenceCategory.VERY_LOW


@dataclass
class ErrorSignature:
    """Signature for matching similar errors."""

    error_type: str  # e.g., "TS2339", "ModuleNotFoundError"
    error_category: str  # e.g., "type_error", "import_error"
    file_pattern: str  # e.g., "*.tsx", "api/*.py"
    key_tokens: list[str] = field(default_factory=list)  # Important error keywords


@dataclass
class FixOutcome:
    """Record of a fix attempt outcome."""

    signature: ErrorSignature
    escalation_level: int  # EscalationLevel value
    success: bool
    confidence_before: float
    timestamp: datetime = field(default_factory=datetime.now)
    fix_approach: str = ""  # Brief description of what was tried


# Base confidence scores by error type
# These are informed by common patterns in TypeScript/React/Python projects
ERROR_TYPE_BASE_CONFIDENCE: dict[str, float] = {
    # High confidence - usually simple fixes
    "import_error": 0.85,
    "missing_import": 0.85,
    "module_not_found": 0.80,
    "undefined_variable": 0.75,
    "typo": 0.90,
    "syntax_error": 0.70,
    "missing_semicolon": 0.95,
    "missing_bracket": 0.90,
    # Medium confidence - need more context
    "type_error": 0.55,
    "property_not_exist": 0.50,
    "type_mismatch": 0.45,
    "null_undefined": 0.50,
    "interface_mismatch": 0.45,
    # Low confidence - complex issues
    "runtime_error": 0.35,
    "logic_error": 0.25,
    "race_condition": 0.20,
    "memory_leak": 0.15,
    "state_management": 0.30,
    # Database errors - varies by type
    "database_connection": 0.60,
    "schema_mismatch": 0.40,
    "migration_error": 0.35,
    "foreign_key_violation": 0.45,
    # Build/deploy errors
    "build_error": 0.50,
    "bundle_error": 0.40,
    "deploy_error": 0.30,
    # Default
    "unknown": 0.40,
}

# Patterns that indicate high confidence
HIGH_CONFIDENCE_PATTERNS: list[str] = [
    "Cannot find module",
    "is not defined",
    "is not a function",
    "Expected",
    "Missing",
    "Unterminated",
    "Unexpected token",
    "Cannot read property",
    "undefined is not an object",
    "SyntaxError:",
    "Import declaration",
    "export",
]

# Patterns that indicate low confidence
LOW_CONFIDENCE_PATTERNS: list[str] = [
    "Maximum call stack",
    "out of memory",
    "ECONNREFUSED",
    "ETIMEDOUT",
    "race condition",
    "deadlock",
    "infinite loop",
    "memory leak",
    "heap",
    "stack overflow",
    "segmentation fault",
    "core dumped",
]


class ConfidenceEstimator:
    """
    Estimates confidence in fix success.

    Combines multiple signals:
    - Error type base confidence (historical patterns)
    - Pattern matching (high/low confidence indicators)
    - Historical success rates (within-session learning)
    - Available context quality (files, stack traces, etc.)

    Used to decide:
    - Should we retry at current escalation level?
    - Should we escalate to a more powerful approach?
    - Should we ask for human help?
    """

    # Thresholds for decision-making
    ESCALATE_THRESHOLD = 0.30  # Below this, escalate to next level
    HELP_THRESHOLD = 0.15  # Below this, ask for human help
    RETRY_THRESHOLD = 0.50  # Above this, retry at same level is worthwhile

    def __init__(self) -> None:
        self._history: list[FixOutcome] = []
        self._success_rates: dict[str, tuple[int, int]] = {}  # category -> (successes, total)
        self.logger = logger.bind(component="ConfidenceEstimator")

    def estimate_confidence(
        self,
        error_type: str,
        error_message: str,
        escalation_level: int,
        context_files: Optional[list[str]] = None,
        stack_trace: Optional[str] = None,
        previous_attempts: int = 0,
    ) -> ConfidenceScore:
        """
        Estimate confidence for fixing an error.

        Args:
            error_type: Categorized error type (e.g., "type_error", "import_error")
            error_message: Full error message text
            escalation_level: Current EscalationLevel value
            context_files: List of files available for context
            stack_trace: Full stack trace if available
            previous_attempts: Number of previous fix attempts

        Returns:
            ConfidenceScore with breakdown and explanation
        """
        # 1. Base confidence from error type
        base = ERROR_TYPE_BASE_CONFIDENCE.get(
            error_type.lower(), ERROR_TYPE_BASE_CONFIDENCE["unknown"]
        )

        # 2. Adjust for escalation level (higher levels = harder problems)
        level_multiplier = self._get_level_multiplier(escalation_level)
        level_adjusted = base * level_multiplier

        # 3. Pattern matching adjustments
        pattern_adjustment = self._analyze_patterns(error_message)
        pattern_adjusted = min(1.0, max(0.0, level_adjusted + pattern_adjustment))

        # 4. Historical success rate
        historical = self._get_historical_rate(error_type)

        # 5. Context quality score
        context_quality = self._assess_context_quality(context_files, stack_trace)

        # 6. Attempt penalty (each retry reduces confidence)
        attempt_penalty = min(0.3, previous_attempts * 0.1)

        # 7. Combine scores (weighted average)
        overall = (
            pattern_adjusted * 0.35  # Current error analysis
            + historical * 0.25  # Past success
            + context_quality * 0.25  # Available context
            - attempt_penalty  # Retry penalty
        )

        # Ensure bounds
        overall = min(1.0, max(0.0, overall))

        # Build explanation
        explanation = self._build_explanation(
            error_type=error_type,
            base=base,
            level_multiplier=level_multiplier,
            pattern_adjustment=pattern_adjustment,
            historical=historical,
            context_quality=context_quality,
            attempt_penalty=attempt_penalty,
            overall=overall,
        )

        score = ConfidenceScore(
            overall=overall,
            historical=historical,
            complexity=1.0 - (level_adjusted * level_multiplier),
            context_quality=context_quality,
            explanation=explanation,
        )

        self.logger.debug(
            "confidence_estimated",
            error_type=error_type,
            overall=f"{overall:.2f}",
            category=score.category.value,
        )

        return score

    def _get_level_multiplier(self, escalation_level: int) -> float:
        """
        Get confidence multiplier based on escalation level.

        Higher levels mean the problem is harder, so confidence is lower.
        """
        multipliers = {
            1: 1.0,  # PATTERN_FIX - full confidence in base rate
            2: 0.85,  # LLM_TARGETED - slightly harder
            3: 0.70,  # LLM_BROAD - needs more context
            4: 0.50,  # SCOPE_REDUCTION - significant reduction
            5: 0.30,  # HUMAN_REVIEW - low confidence
        }
        return multipliers.get(escalation_level, 0.50)

    def _analyze_patterns(self, error_message: str) -> float:
        """
        Analyze error message for confidence-affecting patterns.

        Returns adjustment value (-0.3 to +0.3).
        """
        message_lower = error_message.lower()

        # Check for high confidence patterns
        high_matches = sum(1 for p in HIGH_CONFIDENCE_PATTERNS if p.lower() in message_lower)

        # Check for low confidence patterns
        low_matches = sum(1 for p in LOW_CONFIDENCE_PATTERNS if p.lower() in message_lower)

        # Calculate adjustment
        adjustment = (high_matches * 0.05) - (low_matches * 0.10)

        return max(-0.3, min(0.3, adjustment))

    def _get_historical_rate(self, error_type: str) -> float:
        """
        Get historical success rate for this error type.

        Returns 0.5 (neutral) if no history available.
        """
        category = error_type.lower()

        if category in self._success_rates:
            successes, total = self._success_rates[category]
            if total > 0:
                return successes / total

        # Check for similar categories
        for key, (successes, total) in self._success_rates.items():
            if key in category or category in key:
                if total > 0:
                    return successes / total

        return 0.5  # Neutral default

    def _assess_context_quality(
        self,
        context_files: Optional[list[str]],
        stack_trace: Optional[str],
    ) -> float:
        """
        Assess the quality of available context.

        More context = higher confidence we can fix the issue.
        """
        score = 0.3  # Base score with minimal context

        # Add for context files
        if context_files:
            file_count = len(context_files)
            if file_count >= 5:
                score += 0.3
            elif file_count >= 2:
                score += 0.2
            elif file_count >= 1:
                score += 0.1

        # Add for stack trace
        if stack_trace:
            # More detailed stack traces are better
            lines = stack_trace.count("\n")
            if lines >= 10:
                score += 0.25
            elif lines >= 5:
                score += 0.15
            elif lines >= 1:
                score += 0.05

            # Bonus if stack trace has file:line references
            if ":" in stack_trace and (".ts" in stack_trace or ".py" in stack_trace):
                score += 0.15

        return min(1.0, score)

    def _build_explanation(
        self,
        error_type: str,
        base: float,
        level_multiplier: float,
        pattern_adjustment: float,
        historical: float,
        context_quality: float,
        attempt_penalty: float,
        overall: float,
    ) -> str:
        """Build human-readable explanation of confidence score."""
        parts = []

        # Overall assessment
        if overall >= 0.70:
            parts.append(f"High confidence ({overall:.0%}) for {error_type}")
        elif overall >= 0.40:
            parts.append(f"Medium confidence ({overall:.0%}) for {error_type}")
        else:
            parts.append(f"Low confidence ({overall:.0%}) for {error_type}")

        # Key factors
        factors = []

        if base >= 0.70:
            factors.append(f"error type typically fixable ({base:.0%} base)")
        elif base <= 0.35:
            factors.append(f"error type is challenging ({base:.0%} base)")

        if level_multiplier < 0.70:
            factors.append("escalated to higher level")

        if pattern_adjustment > 0.1:
            factors.append("error patterns suggest straightforward fix")
        elif pattern_adjustment < -0.1:
            factors.append("error patterns suggest complexity")

        if historical > 0.6:
            factors.append(f"good historical success ({historical:.0%})")
        elif historical < 0.4 and historical != 0.5:
            factors.append(f"low historical success ({historical:.0%})")

        if context_quality >= 0.7:
            factors.append("rich context available")
        elif context_quality <= 0.4:
            factors.append("limited context")

        if attempt_penalty > 0:
            factors.append(f"retry penalty applied (-{attempt_penalty:.0%})")

        if factors:
            parts.append(". Factors: " + "; ".join(factors))

        return "".join(parts)

    def record_fix(
        self,
        error_type: str,
        error_message: str,
        escalation_level: int,
        success: bool,
        confidence_before: float,
        fix_approach: str = "",
    ) -> None:
        """
        Record a fix attempt outcome for learning.

        This updates historical success rates used in future estimates.
        """
        # Create error signature
        signature = ErrorSignature(
            error_type=self._extract_error_code(error_message),
            error_category=error_type.lower(),
            file_pattern=self._extract_file_pattern(error_message),
            key_tokens=self._extract_key_tokens(error_message),
        )

        # Record outcome
        outcome = FixOutcome(
            signature=signature,
            escalation_level=escalation_level,
            success=success,
            confidence_before=confidence_before,
            fix_approach=fix_approach,
        )
        self._history.append(outcome)

        # Update success rates
        category = error_type.lower()
        if category not in self._success_rates:
            self._success_rates[category] = (0, 0)

        successes, total = self._success_rates[category]
        if success:
            self._success_rates[category] = (successes + 1, total + 1)
        else:
            self._success_rates[category] = (successes, total + 1)

        self.logger.info(
            "fix_outcome_recorded",
            error_type=error_type,
            success=success,
            escalation_level=escalation_level,
            confidence_before=f"{confidence_before:.2f}",
            new_rate=f"{self._success_rates[category][0]}/{self._success_rates[category][1]}",
        )

    def _extract_error_code(self, error_message: str) -> str:
        """Extract error code like TS2339, E0001, etc."""
        import re

        # TypeScript errors
        ts_match = re.search(r"TS\d+", error_message)
        if ts_match:
            return ts_match.group()

        # Python errors
        py_match = re.search(r"E\d{4}", error_message)
        if py_match:
            return py_match.group()

        # ESLint errors
        eslint_match = re.search(r"@typescript-eslint/[\w-]+", error_message)
        if eslint_match:
            return eslint_match.group()

        return "unknown"

    def _extract_file_pattern(self, error_message: str) -> str:
        """Extract file pattern from error message."""
        import re

        # Look for file extensions
        file_match = re.search(r"[\w/\\]+\.(tsx?|jsx?|py|json|css|scss)", error_message)
        if file_match:
            path = file_match.group()
            # Return pattern like "*.tsx" or "api/*.py"
            ext = path.split(".")[-1]
            if "/" in path or "\\" in path:
                parts = path.replace("\\", "/").split("/")
                if len(parts) > 1:
                    return f"{parts[-2]}/*.{ext}"
            return f"*.{ext}"

        return "*"

    def _extract_key_tokens(self, error_message: str) -> list[str]:
        """Extract important tokens from error message."""
        # Common important words
        keywords = [
            "undefined",
            "null",
            "property",
            "module",
            "import",
            "export",
            "type",
            "interface",
            "function",
            "class",
            "component",
            "hook",
            "state",
            "props",
            "async",
            "await",
            "promise",
        ]

        message_lower = error_message.lower()
        found = [kw for kw in keywords if kw in message_lower]

        return found[:5]  # Limit to 5 tokens

    def should_seek_help(self, confidence: float, attempt_count: int) -> bool:
        """
        Determine if we should ask for human help.

        Returns True if:
        - Confidence is very low (below HELP_THRESHOLD)
        - Many attempts with low confidence
        """
        if confidence < self.HELP_THRESHOLD:
            return True

        if attempt_count >= 3 and confidence < self.ESCALATE_THRESHOLD:
            return True

        return False

    def should_escalate(self, confidence: float, attempt_count: int) -> bool:
        """
        Determine if we should escalate to next level.

        Returns True if:
        - Confidence is below ESCALATE_THRESHOLD
        - Multiple attempts at current level
        """
        if confidence < self.ESCALATE_THRESHOLD:
            return True

        if attempt_count >= 2 and confidence < self.RETRY_THRESHOLD:
            return True

        return False

    def should_retry(self, confidence: float) -> bool:
        """
        Determine if retry at current level is worthwhile.

        Returns True if confidence is above RETRY_THRESHOLD.
        """
        return confidence >= self.RETRY_THRESHOLD

    def get_recommendation(
        self,
        confidence: float,
        attempt_count: int,
    ) -> str:
        """
        Get action recommendation based on confidence and attempts.

        Returns: "retry", "escalate", or "seek_help"
        """
        if self.should_seek_help(confidence, attempt_count):
            return "seek_help"
        elif self.should_escalate(confidence, attempt_count):
            return "escalate"
        else:
            return "retry"

    def get_statistics(self) -> dict:
        """Get estimator statistics for monitoring."""
        total_outcomes = len(self._history)
        successes = sum(1 for o in self._history if o.success)

        # Success rate by category
        category_stats = {}
        for category, (succ, total) in self._success_rates.items():
            if total > 0:
                category_stats[category] = {
                    "successes": succ,
                    "total": total,
                    "rate": succ / total,
                }

        # Recent performance (last 20 outcomes)
        recent = self._history[-20:] if self._history else []
        recent_success = sum(1 for o in recent if o.success)
        recent_rate = recent_success / len(recent) if recent else 0

        return {
            "total_outcomes": total_outcomes,
            "overall_success_rate": successes / total_outcomes if total_outcomes > 0 else 0,
            "recent_success_rate": recent_rate,
            "categories": category_stats,
            "thresholds": {
                "escalate": self.ESCALATE_THRESHOLD,
                "help": self.HELP_THRESHOLD,
                "retry": self.RETRY_THRESHOLD,
            },
        }

    def reset(self) -> None:
        """Reset estimator for new session (keeps some learning)."""
        # Keep success rates but clear detailed history
        self._history.clear()
        self.logger.info(
            "confidence_estimator_reset",
            preserved_categories=len(self._success_rates),
        )
