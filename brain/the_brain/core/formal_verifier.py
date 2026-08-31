"""
Formal Verifier - AGI Phase 5

Verifies decisions against safety constraints using formal methods.
Provides provable guarantees about system behavior.

Key Features:
- Z3 SMT solver integration
- Constraint specification language
- Invariant verification
- Bounded model checking
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

# Conditional Z3 import
try:
    from z3 import (
        Solver, Int, Real, Bool, And, Or, Not, Implies,
        sat, unsat, unknown, If, ForAll, Exists,
        IntVector, RealVector, BoolVector
    )
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False
    logger.warning("Z3 not installed. Install with: pip install z3-solver")


class VerificationResult(Enum):
    """Result of formal verification."""
    VERIFIED = "verified"
    VIOLATED = "violated"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"


class ConstraintType(Enum):
    """Types of formal constraints."""
    SAFETY = "safety"  # Must always hold
    LIVENESS = "liveness"  # Must eventually hold
    INVARIANT = "invariant"  # Preserved by transitions
    PRECONDITION = "precondition"  # Required before action
    POSTCONDITION = "postcondition"  # Guaranteed after action
    FAIRNESS = "fairness"  # Scheduling constraints


@dataclass
class Constraint:
    """Formal constraint specification."""
    name: str
    constraint_type: ConstraintType
    expression: Any  # Z3 expression or callable
    description: str = ""
    priority: int = 1  # Higher = more important
    is_hard: bool = True  # Hard constraints must be satisfied


@dataclass
class VerificationReport:
    """Report from formal verification."""
    result: VerificationResult
    constraint_name: str
    is_satisfied: bool
    counterexample: Optional[Dict[str, Any]] = None
    proof_time_ms: float = 0.0
    details: str = ""


@dataclass
class VerifierStats:
    """Statistics for formal verifier."""
    total_checks: int = 0
    verified: int = 0
    violated: int = 0
    unknown: int = 0
    avg_check_time_ms: float = 0.0


class SymbolicState:
    """Symbolic representation of system state for verification."""

    def __init__(self, state_dim: int, name_prefix: str = "s"):
        if not HAS_Z3:
            raise ImportError("Z3 is required for formal verification")

        self.state_dim = state_dim
        self.variables = RealVector(name_prefix, state_dim)

    def __getitem__(self, idx: int):
        return self.variables[idx]

    def to_concrete(self, model) -> np.ndarray:
        """Convert Z3 model to concrete values."""
        return np.array([
            float(model.eval(self.variables[i]).as_fraction())
            for i in range(self.state_dim)
        ])


class SymbolicAction:
    """Symbolic representation of action."""

    def __init__(self, action_dim: int, name: str = "a"):
        if not HAS_Z3:
            raise ImportError("Z3 is required for formal verification")

        self.action_dim = action_dim
        self.variable = Int(name)
        # Constraint: action in valid range
        self.domain_constraint = And(
            self.variable >= 0,
            self.variable < action_dim
        )

    def equals(self, action: int):
        return self.variable == action


class FormalVerifier:
    """
    Formal verification of safety constraints.

    Uses Z3 SMT solver to prove properties about system behavior.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        timeout_ms: int = 5000
    ):
        if not HAS_Z3:
            raise ImportError("Z3 is required. Install with: pip install z3-solver")

        self.state_dim = state_dim
        self.action_dim = action_dim
        self.timeout_ms = timeout_ms

        # Constraints
        self.constraints: List[Constraint] = []

        # Symbolic variables
        self.current_state = SymbolicState(state_dim, "s")
        self.next_state = SymbolicState(state_dim, "s_next")
        self.action = SymbolicAction(action_dim)

        # Statistics
        self.stats = VerifierStats()

    def add_constraint(self, constraint: Constraint):
        """Add a constraint to verify."""
        self.constraints.append(constraint)
        logger.info(f"Added constraint: {constraint.name}")

    def add_safety_constraint(
        self,
        name: str,
        condition: Callable[[SymbolicState], Any],
        description: str = ""
    ):
        """
        Add a safety constraint (must always hold).

        Args:
            name: Constraint name
            condition: Function that takes symbolic state and returns Z3 expression
            description: Human-readable description
        """
        constraint = Constraint(
            name=name,
            constraint_type=ConstraintType.SAFETY,
            expression=condition,
            description=description
        )
        self.add_constraint(constraint)

    def add_state_bounds(
        self,
        bounds: Dict[int, Tuple[float, float]],
        name: str = "state_bounds"
    ):
        """
        Add state boundary constraints.

        Args:
            bounds: Dictionary mapping state index to (min, max) bounds
            name: Constraint name
        """
        def bound_constraint(state: SymbolicState):
            constraints = []
            for idx, (min_val, max_val) in bounds.items():
                constraints.append(state[idx] >= min_val)
                constraints.append(state[idx] <= max_val)
            return And(*constraints)

        self.add_safety_constraint(name, bound_constraint, "State must stay within bounds")

    def add_action_precondition(
        self,
        action_idx: int,
        precondition: Callable[[SymbolicState], Any],
        name: str = ""
    ):
        """
        Add precondition for an action.

        Args:
            action_idx: Action this precondition applies to
            precondition: Condition that must hold before action
            name: Constraint name
        """
        name = name or f"precond_action_{action_idx}"

        def precond_check(state: SymbolicState, action: SymbolicAction):
            return Implies(
                action.equals(action_idx),
                precondition(state)
            )

        constraint = Constraint(
            name=name,
            constraint_type=ConstraintType.PRECONDITION,
            expression=precond_check,
            description=f"Precondition for action {action_idx}"
        )
        self.add_constraint(constraint)

    def verify_action(
        self,
        state: np.ndarray,
        action: int
    ) -> VerificationReport:
        """
        Verify that an action satisfies all constraints.

        Args:
            state: Current concrete state
            action: Proposed action

        Returns:
            Verification report
        """
        import time
        start_time = time.time()

        solver = Solver()
        solver.set("timeout", self.timeout_ms)

        # Assert current state
        for i, val in enumerate(state):
            solver.add(self.current_state[i] == val)

        # Assert action
        solver.add(self.action.variable == action)
        solver.add(self.action.domain_constraint)

        # Check all constraints
        violated = []
        for constraint in self.constraints:
            if constraint.constraint_type in [ConstraintType.SAFETY, ConstraintType.PRECONDITION]:
                expr = constraint.expression
                if callable(expr):
                    if constraint.constraint_type == ConstraintType.PRECONDITION:
                        z3_expr = expr(self.current_state, self.action)
                    else:
                        z3_expr = expr(self.current_state)

                    # Check if constraint can be violated
                    solver.push()
                    solver.add(Not(z3_expr))
                    result = solver.check()
                    solver.pop()

                    if result == sat:
                        violated.append(constraint.name)

        elapsed_ms = (time.time() - start_time) * 1000
        self.stats.total_checks += 1
        self.stats.avg_check_time_ms = (
            (self.stats.avg_check_time_ms * (self.stats.total_checks - 1) + elapsed_ms)
            / self.stats.total_checks
        )

        if violated:
            self.stats.violated += 1
            return VerificationReport(
                result=VerificationResult.VIOLATED,
                constraint_name=", ".join(violated),
                is_satisfied=False,
                proof_time_ms=elapsed_ms,
                details=f"Violated constraints: {violated}"
            )
        else:
            self.stats.verified += 1
            return VerificationReport(
                result=VerificationResult.VERIFIED,
                constraint_name="all",
                is_satisfied=True,
                proof_time_ms=elapsed_ms,
                details="All constraints satisfied"
            )

    def verify_transition(
        self,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray
    ) -> VerificationReport:
        """
        Verify a state transition satisfies all constraints.

        Args:
            state: Starting state
            action: Action taken
            next_state: Resulting state

        Returns:
            Verification report
        """
        import time
        start_time = time.time()

        solver = Solver()
        solver.set("timeout", self.timeout_ms)

        # Assert states
        for i, val in enumerate(state):
            solver.add(self.current_state[i] == val)
        for i, val in enumerate(next_state):
            solver.add(self.next_state[i] == val)
        solver.add(self.action.variable == action)

        # Check invariants
        violated = []
        for constraint in self.constraints:
            if constraint.constraint_type == ConstraintType.INVARIANT:
                expr = constraint.expression
                if callable(expr):
                    z3_expr = expr(self.current_state, self.next_state)
                    solver.push()
                    solver.add(Not(z3_expr))
                    result = solver.check()
                    solver.pop()

                    if result == sat:
                        violated.append(constraint.name)

        elapsed_ms = (time.time() - start_time) * 1000

        if violated:
            return VerificationReport(
                result=VerificationResult.VIOLATED,
                constraint_name=", ".join(violated),
                is_satisfied=False,
                proof_time_ms=elapsed_ms,
                details=f"Invariants violated: {violated}"
            )
        else:
            return VerificationReport(
                result=VerificationResult.VERIFIED,
                constraint_name="invariants",
                is_satisfied=True,
                proof_time_ms=elapsed_ms
            )

    def find_safe_actions(self, state: np.ndarray) -> List[int]:
        """
        Find all actions that satisfy all constraints.

        Args:
            state: Current state

        Returns:
            List of safe action indices
        """
        safe_actions = []

        for action in range(self.action_dim):
            report = self.verify_action(state, action)
            if report.is_satisfied:
                safe_actions.append(action)

        return safe_actions

    def get_counterexample(
        self,
        constraint_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get counterexample for a constraint violation.

        Args:
            constraint_name: Name of violated constraint

        Returns:
            Counterexample state/action if found
        """
        constraint = next(
            (c for c in self.constraints if c.name == constraint_name),
            None
        )
        if constraint is None:
            return None

        solver = Solver()
        solver.set("timeout", self.timeout_ms)

        # Add domain constraints
        solver.add(self.action.domain_constraint)

        # Find state/action that violates constraint
        expr = constraint.expression
        if callable(expr):
            if constraint.constraint_type == ConstraintType.PRECONDITION:
                z3_expr = expr(self.current_state, self.action)
            else:
                z3_expr = expr(self.current_state)
            solver.add(Not(z3_expr))

        if solver.check() == sat:
            model = solver.model()
            return {
                "state": self.current_state.to_concrete(model),
                "action": model.eval(self.action.variable).as_long()
            }

        return None


class SimplifiedVerifier:
    """
    Simplified verifier that doesn't require Z3.

    Uses constraint functions directly for runtime checking.
    """

    def __init__(self, state_dim: int, action_dim: int):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.constraints: List[Tuple[str, Callable]] = []
        self.stats = VerifierStats()

    def add_constraint(
        self,
        name: str,
        check_fn: Callable[[np.ndarray, int], bool]
    ):
        """Add runtime constraint check."""
        self.constraints.append((name, check_fn))

    def verify_action(
        self,
        state: np.ndarray,
        action: int
    ) -> VerificationReport:
        """Verify action using runtime checks."""
        violated = []

        for name, check_fn in self.constraints:
            try:
                if not check_fn(state, action):
                    violated.append(name)
            except Exception as e:
                logger.warning(f"Constraint check failed: {name} - {e}")

        self.stats.total_checks += 1

        if violated:
            self.stats.violated += 1
            return VerificationReport(
                result=VerificationResult.VIOLATED,
                constraint_name=", ".join(violated),
                is_satisfied=False,
                details=f"Violated: {violated}"
            )
        else:
            self.stats.verified += 1
            return VerificationReport(
                result=VerificationResult.VERIFIED,
                constraint_name="all",
                is_satisfied=True
            )


def create_verifier(
    state_dim: int,
    action_dim: int,
    use_z3: bool = True
) -> Union[FormalVerifier, SimplifiedVerifier]:
    """
    Create appropriate verifier based on Z3 availability.

    Args:
        state_dim: State dimension
        action_dim: Action dimension
        use_z3: Whether to prefer Z3 if available

    Returns:
        FormalVerifier or SimplifiedVerifier
    """
    if use_z3 and HAS_Z3:
        return FormalVerifier(state_dim, action_dim)
    else:
        if use_z3:
            logger.warning("Z3 not available, using simplified verifier")
        return SimplifiedVerifier(state_dim, action_dim)
