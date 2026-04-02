"""
Safety Layer - AGI Phase 2

Ensures safe decision-making through action validation,
constraint checking, and reversibility assessment.

Key Features:
- Action masking for dangerous actions
- Constraint satisfaction verification
- Reversibility scoring
- Safe exploration bounds
- Emergency stop mechanisms
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    """Safety classification levels."""
    SAFE = "safe"
    CAUTION = "caution"
    WARNING = "warning"
    DANGEROUS = "dangerous"
    FORBIDDEN = "forbidden"


class ConstraintType(Enum):
    """Types of safety constraints."""
    STATE_BOUND = "state_bound"
    ACTION_LIMIT = "action_limit"
    TEMPORAL = "temporal"
    RESOURCE = "resource"
    INVARIANT = "invariant"


@dataclass
class SafetyConstraint:
    """Definition of a safety constraint."""
    name: str
    constraint_type: ConstraintType
    check_fn: Callable[[Any, Any], bool]
    violation_penalty: float = -100.0
    is_hard: bool = True  # Hard constraints cannot be violated
    description: str = ""


@dataclass
class SafetyReport:
    """Report from safety check."""
    is_safe: bool
    safety_level: SafetyLevel
    violated_constraints: List[str]
    warnings: List[str]
    reversibility_score: float
    risk_score: float
    recommended_action: Optional[int] = None


@dataclass
class SafetyStats:
    """Statistics for safety monitoring."""
    total_checks: int = 0
    violations_prevented: int = 0
    warnings_issued: int = 0
    emergency_stops: int = 0
    avg_risk_score: float = 0.0


class SafetyChecker(ABC):
    """Abstract base class for safety checkers."""

    @abstractmethod
    def check(self, state: Any, action: int) -> SafetyReport:
        """Check if action is safe in given state."""
        pass


class BoundedStateChecker(SafetyChecker):
    """Checks if actions keep state within safe bounds."""

    def __init__(
        self,
        state_bounds: Dict[int, Tuple[float, float]],
        dynamics_model: Optional[Callable] = None
    ):
        """
        Initialize bounded state checker.

        Args:
            state_bounds: Dictionary mapping state indices to (min, max) bounds
            dynamics_model: Function to predict next state
        """
        self.state_bounds = state_bounds
        self.dynamics_model = dynamics_model

    def check(self, state: np.ndarray, action: int) -> SafetyReport:
        """Check if action respects state bounds."""
        violations = []
        warnings = []

        # Check current state
        for idx, (min_val, max_val) in self.state_bounds.items():
            if idx < len(state):
                val = state[idx]
                margin = (max_val - min_val) * 0.1  # 10% margin

                if val < min_val or val > max_val:
                    violations.append(f"State[{idx}] = {val:.3f} out of bounds [{min_val}, {max_val}]")
                elif val < min_val + margin or val > max_val - margin:
                    warnings.append(f"State[{idx}] = {val:.3f} near boundary")

        # Predict next state if dynamics model available
        if self.dynamics_model is not None:
            try:
                next_state = self.dynamics_model(state, action)
                for idx, (min_val, max_val) in self.state_bounds.items():
                    if idx < len(next_state):
                        val = next_state[idx]
                        if val < min_val or val > max_val:
                            violations.append(f"Predicted state[{idx}] = {val:.3f} would violate bounds")
            except Exception as e:
                warnings.append(f"Could not predict next state: {e}")

        # Determine safety level
        if violations:
            safety_level = SafetyLevel.DANGEROUS
            is_safe = False
        elif warnings:
            safety_level = SafetyLevel.CAUTION
            is_safe = True
        else:
            safety_level = SafetyLevel.SAFE
            is_safe = True

        return SafetyReport(
            is_safe=is_safe,
            safety_level=safety_level,
            violated_constraints=violations,
            warnings=warnings,
            reversibility_score=1.0 if is_safe else 0.0,
            risk_score=len(violations) * 0.5 + len(warnings) * 0.1
        )


class ActionMaskChecker(SafetyChecker):
    """Checks actions against a mask of forbidden actions."""

    def __init__(self, forbidden_actions: Optional[Set[int]] = None):
        self.forbidden_actions = forbidden_actions or set()
        self.conditional_masks: List[Tuple[Callable, Set[int]]] = []

    def add_forbidden_action(self, action: int):
        """Add action to forbidden set."""
        self.forbidden_actions.add(action)

    def add_conditional_mask(self, condition_fn: Callable[[Any], bool], actions: Set[int]):
        """Add conditional action mask."""
        self.conditional_masks.append((condition_fn, actions))

    def check(self, state: Any, action: int) -> SafetyReport:
        """Check if action is forbidden."""
        violations = []
        warnings = []

        # Check permanent forbidden actions
        if action in self.forbidden_actions:
            violations.append(f"Action {action} is permanently forbidden")

        # Check conditional masks
        for condition_fn, masked_actions in self.conditional_masks:
            try:
                if condition_fn(state) and action in masked_actions:
                    violations.append(f"Action {action} is forbidden in current state")
            except Exception as e:
                warnings.append(f"Conditional check failed: {e}")

        is_safe = len(violations) == 0
        safety_level = SafetyLevel.FORBIDDEN if violations else SafetyLevel.SAFE

        return SafetyReport(
            is_safe=is_safe,
            safety_level=safety_level,
            violated_constraints=violations,
            warnings=warnings,
            reversibility_score=1.0 if is_safe else 0.0,
            risk_score=1.0 if violations else 0.0
        )


class ReversibilityChecker(SafetyChecker):
    """Assesses how easily an action can be reversed."""

    def __init__(
        self,
        inverse_actions: Dict[int, int],
        dynamics_model: Optional[Callable] = None,
        threshold: float = 0.5
    ):
        """
        Initialize reversibility checker.

        Args:
            inverse_actions: Mapping from action to its inverse
            dynamics_model: For checking if inverse brings back to original state
            threshold: Minimum reversibility score to be considered safe
        """
        self.inverse_actions = inverse_actions
        self.dynamics_model = dynamics_model
        self.threshold = threshold

    def check(self, state: np.ndarray, action: int) -> SafetyReport:
        """Check reversibility of action."""
        warnings = []

        # Check if action has known inverse
        if action in self.inverse_actions:
            inverse_action = self.inverse_actions[action]
            reversibility = 1.0

            # If dynamics model available, verify inverse
            if self.dynamics_model is not None:
                try:
                    next_state = self.dynamics_model(state, action)
                    recovered_state = self.dynamics_model(next_state, inverse_action)
                    # Reversibility = 1 - normalized distance
                    dist = np.linalg.norm(state - recovered_state)
                    max_dist = np.linalg.norm(state) + 1e-8
                    reversibility = max(0, 1 - dist / max_dist)
                except Exception as e:
                    warnings.append(f"Could not verify reversibility: {e}")
                    reversibility = 0.5
        else:
            reversibility = 0.0
            warnings.append(f"Action {action} has no known inverse")

        is_safe = reversibility >= self.threshold
        if reversibility >= 0.8:
            safety_level = SafetyLevel.SAFE
        elif reversibility >= 0.5:
            safety_level = SafetyLevel.CAUTION
        elif reversibility >= 0.2:
            safety_level = SafetyLevel.WARNING
        else:
            safety_level = SafetyLevel.DANGEROUS

        return SafetyReport(
            is_safe=is_safe,
            safety_level=safety_level,
            violated_constraints=[],
            warnings=warnings,
            reversibility_score=reversibility,
            risk_score=1.0 - reversibility
        )


class SafetyLayer:
    """
    Main safety layer that combines multiple safety checkers.

    Validates actions before execution and provides safe alternatives.
    """

    def __init__(
        self,
        action_dim: int,
        enable_emergency_stop: bool = True,
        risk_threshold: float = 0.7,
        max_consecutive_warnings: int = 5
    ):
        self.action_dim = action_dim
        self.enable_emergency_stop = enable_emergency_stop
        self.risk_threshold = risk_threshold
        self.max_consecutive_warnings = max_consecutive_warnings

        # Safety checkers
        self.checkers: List[SafetyChecker] = []

        # Constraints
        self.constraints: List[SafetyConstraint] = []

        # Statistics
        self.stats = SafetyStats()
        self._consecutive_warnings = 0
        self._emergency_stop_active = False

    def add_checker(self, checker: SafetyChecker):
        """Add a safety checker."""
        self.checkers.append(checker)

    def add_constraint(self, constraint: SafetyConstraint):
        """Add a safety constraint."""
        self.constraints.append(constraint)

    def check_action(self, state: Any, action: int) -> SafetyReport:
        """
        Comprehensive safety check for an action.

        Args:
            state: Current state
            action: Proposed action

        Returns:
            SafetyReport with overall assessment
        """
        self.stats.total_checks += 1

        all_violations = []
        all_warnings = []
        total_risk = 0.0
        min_reversibility = 1.0

        # Run all checkers
        for checker in self.checkers:
            report = checker.check(state, action)
            all_violations.extend(report.violated_constraints)
            all_warnings.extend(report.warnings)
            total_risk += report.risk_score
            min_reversibility = min(min_reversibility, report.reversibility_score)

        # Check constraints
        for constraint in self.constraints:
            try:
                if not constraint.check_fn(state, action):
                    if constraint.is_hard:
                        all_violations.append(f"Constraint '{constraint.name}' violated")
                    else:
                        all_warnings.append(f"Soft constraint '{constraint.name}' violated")
            except Exception as e:
                all_warnings.append(f"Constraint check failed: {constraint.name} - {e}")

        # Aggregate results
        avg_risk = total_risk / max(len(self.checkers), 1)
        is_safe = len(all_violations) == 0 and avg_risk < self.risk_threshold

        # Determine safety level
        if all_violations:
            safety_level = SafetyLevel.DANGEROUS
        elif avg_risk >= 0.7:
            safety_level = SafetyLevel.WARNING
        elif all_warnings or avg_risk >= 0.3:
            safety_level = SafetyLevel.CAUTION
        else:
            safety_level = SafetyLevel.SAFE

        # Update warning counter
        if all_warnings:
            self._consecutive_warnings += 1
            self.stats.warnings_issued += 1
        else:
            self._consecutive_warnings = 0

        # Check for emergency stop
        if self.enable_emergency_stop:
            if self._consecutive_warnings >= self.max_consecutive_warnings:
                self._emergency_stop_active = True
                self.stats.emergency_stops += 1
                all_violations.append("Emergency stop triggered due to consecutive warnings")
                is_safe = False
                safety_level = SafetyLevel.FORBIDDEN

        # Find recommended safe action if current is unsafe
        recommended_action = None
        if not is_safe:
            self.stats.violations_prevented += 1
            recommended_action = self._find_safe_action(state)

        # Update statistics
        self.stats.avg_risk_score = 0.9 * self.stats.avg_risk_score + 0.1 * avg_risk

        return SafetyReport(
            is_safe=is_safe,
            safety_level=safety_level,
            violated_constraints=all_violations,
            warnings=all_warnings,
            reversibility_score=min_reversibility,
            risk_score=avg_risk,
            recommended_action=recommended_action
        )

    def _find_safe_action(self, state: Any) -> Optional[int]:
        """Find the safest alternative action."""
        best_action = None
        best_risk = float('inf')

        for action in range(self.action_dim):
            report = self.check_action(state, action)
            if report.is_safe and report.risk_score < best_risk:
                best_risk = report.risk_score
                best_action = action

        return best_action

    def get_safe_actions(self, state: Any) -> List[int]:
        """Get list of all safe actions in current state."""
        safe_actions = []
        for action in range(self.action_dim):
            report = self.check_action(state, action)
            if report.is_safe:
                safe_actions.append(action)
        return safe_actions

    def get_action_mask(self, state: Any) -> np.ndarray:
        """Get binary mask of safe actions (1 = safe, 0 = unsafe)."""
        mask = np.zeros(self.action_dim)
        for action in range(self.action_dim):
            report = self.check_action(state, action)
            mask[action] = 1.0 if report.is_safe else 0.0
        return mask

    def reset_emergency_stop(self):
        """Reset emergency stop state."""
        self._emergency_stop_active = False
        self._consecutive_warnings = 0
        logger.info("Emergency stop reset")

    def is_emergency_stopped(self) -> bool:
        """Check if emergency stop is active."""
        return self._emergency_stop_active


class SafeExplorationWrapper:
    """
    Wraps an agent to ensure safe exploration.

    Intercepts actions and validates/modifies them for safety.
    """

    def __init__(
        self,
        safety_layer: SafetyLayer,
        fallback_action: int = 0,
        log_violations: bool = True
    ):
        self.safety_layer = safety_layer
        self.fallback_action = fallback_action
        self.log_violations = log_violations

    def filter_action(
        self,
        state: Any,
        proposed_action: int
    ) -> Tuple[int, SafetyReport]:
        """
        Filter proposed action through safety layer.

        Args:
            state: Current state
            proposed_action: Action proposed by agent

        Returns:
            final_action: Safe action to execute
            report: Safety report
        """
        report = self.safety_layer.check_action(state, proposed_action)

        if report.is_safe:
            return proposed_action, report
        else:
            if self.log_violations:
                logger.warning(f"Unsafe action {proposed_action} blocked: {report.violated_constraints}")

            # Use recommended action or fallback
            safe_action = report.recommended_action
            if safe_action is None:
                safe_action = self.fallback_action
                logger.warning(f"No safe action found, using fallback: {safe_action}")

            return safe_action, report

    def mask_action_probs(
        self,
        state: Any,
        action_probs: np.ndarray
    ) -> np.ndarray:
        """
        Mask action probabilities to zero out unsafe actions.

        Args:
            state: Current state
            action_probs: Original action probabilities

        Returns:
            Masked action probabilities (renormalized)
        """
        mask = self.safety_layer.get_action_mask(state)
        masked_probs = action_probs * mask

        # Renormalize
        total = masked_probs.sum()
        if total > 0:
            masked_probs = masked_probs / total
        else:
            # All actions unsafe - use uniform over safest
            masked_probs = np.zeros_like(action_probs)
            masked_probs[self.fallback_action] = 1.0

        return masked_probs
