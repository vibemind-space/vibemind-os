"""
Shared Enums: Consolidated enum definitions for the_brain

This module provides canonical definitions of enums used across multiple
modules to avoid duplication and ensure type consistency.

Usage:
    from core.shared_enums import CTMDomain, LearningPhase, ReasoningStatus
"""

from enum import Enum


class CTMDomain(Enum):
    """
    Cognitive domains for CTM (Continuous Thought Machine) specialization.

    Each domain represents a distinct cognitive capability:
    - SPATIAL: Architecture, infrastructure, topology, visual-spatial reasoning
    - LOGIC: Verification, constraints, rules, formal reasoning
    - TEMPORAL: Patterns, scheduling, time-series, sequential processing
    - VALUE: Decisions, trade-offs, optimization, utility evaluation
    """
    SPATIAL = "spatial"
    LOGIC = "logic"
    TEMPORAL = "temporal"
    VALUE = "value"


class LearningPhase(Enum):
    """
    Learning phases based on confidence thresholds.

    Used to adapt training strategy based on current competence:
    - NOVICE: confidence < 0.3, heavy exploration
    - INTERMEDIATE: 0.3 <= confidence < 0.7, balanced exploration/exploitation
    - EXPERT: confidence >= 0.7, exploitation-focused
    """
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"


class ReasoningStatus(Enum):
    """
    Status of async reasoning tasks.

    Tracks the lifecycle of CTM reasoning operations:
    - PENDING: Task queued but not started
    - RUNNING: Task actively processing
    - COMPLETED: Task finished successfully
    - FAILED: Task encountered an error
    - INTERRUPTED: Task was cancelled or timed out
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_learning_phase(confidence: float) -> LearningPhase:
    """
    Determine learning phase from confidence score.

    Args:
        confidence: Confidence score between 0 and 1

    Returns:
        Appropriate LearningPhase based on confidence thresholds
    """
    if confidence < 0.3:
        return LearningPhase.NOVICE
    elif confidence < 0.7:
        return LearningPhase.INTERMEDIATE
    else:
        return LearningPhase.EXPERT


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  SHARED ENUMS TEST")
    print("=" * 60)

    print("\nCTMDomain values:")
    for domain in CTMDomain:
        print(f"  {domain.name}: {domain.value}")

    print("\nLearningPhase values:")
    for phase in LearningPhase:
        print(f"  {phase.name}: {phase.value}")

    print("\nReasoningStatus values:")
    for status in ReasoningStatus:
        print(f"  {status.name}: {status.value}")

    print("\nget_learning_phase tests:")
    for conf in [0.1, 0.3, 0.5, 0.7, 0.9]:
        phase = get_learning_phase(conf)
        print(f"  confidence={conf:.1f} -> {phase.name}")

    print("\n" + "=" * 60)
    print("  All enums working correctly!")
    print("=" * 60)
