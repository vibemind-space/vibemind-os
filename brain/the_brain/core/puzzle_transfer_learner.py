"""
Puzzle Transfer Learner - Bridge Puzzle Training to Production

This module extracts learned patterns from puzzle-solving episodes and transfers
them to the production routing matrix. Enables objective puzzle performance to
improve real-world task predictions.

Key Insight: Puzzle efficiency correlates with decision quality
- High efficiency (≥80%) → Reinforce "suggest" intervention
- Medium efficiency (60-80%) → Slight "suggest" reinforcement
- Low efficiency (<60%) → Reinforce "retry" intervention

Transfer Learning Strategy:
1. Collect puzzle training statistics
2. Extract efficiency patterns by learning phase
3. Map puzzle performance → routing matrix adjustments
4. Apply conservative weight updates (LR=0.001)
5. Track transfer learning effectiveness
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskTypeMapping(Enum):
    """Map learning phases to task types for transfer"""
    NOVICE = "infrastructure_setup"      # Simple, foundational tasks
    INTERMEDIATE = "feature_development" # Standard development work
    EXPERT = "system_architecture"       # Complex, high-level design


@dataclass
class PuzzlePattern:
    """Extracted pattern from puzzle training episode"""
    learning_phase: str                  # "novice", "intermediate", "expert"
    efficiency: float                    # 0.0-1.0
    confidence_delta: float              # Change in confidence
    optimal_moves: int                   # BFS optimal solution length
    agent_moves: int                     # Agent's actual moves
    success: bool                        # Episode succeeded?

    # Derived metrics
    action_efficiency: float = 0.0       # How efficiently actions were taken
    planning_quality: float = 0.0        # How well agent planned ahead

    # Pattern source tracking (for weighted transfer learning)
    is_real_puzzle: bool = False         # True = Real Klotski, False = Synthetic
    pattern_weight: float = 1.0          # Weighting for transfer (Real=3.0, Synthetic=0.5)


@dataclass
class TransferStatistics:
    """Statistics tracking transfer learning effectiveness"""
    total_transfers: int = 0
    successful_transfers: int = 0
    matrix_updates_applied: int = 0

    # By intervention type
    suggest_weight_increases: int = 0
    retry_weight_increases: int = 0
    wait_weight_increases: int = 0

    # Effectiveness metrics
    average_efficiency_transferred: float = 0.0
    average_confidence_gain: float = 0.0

    # Tracking
    transfer_history: List[Dict] = field(default_factory=list)


class PuzzleTransferLearner:
    """
    Transfers learned patterns from puzzle training to production routing matrix

    Core Algorithm:
    1. Accumulate puzzle training episodes
    2. Extract efficiency patterns by learning phase
    3. Map patterns to task types (novice→infrastructure, etc.)
    4. Calculate routing matrix weight adjustments
    5. Apply conservative updates to production matrix

    Conservative Learning:
    - Learning rate: 0.001 (very slow updates)
    - Requires 5+ episodes before first transfer
    - Weight changes capped at ±0.05 per transfer
    """

    def __init__(
        self,
        transfer_learning_rate: float = 0.001,
        min_episodes_before_transfer: int = 5,
        max_weight_change_per_transfer: float = 0.05,
        enable_transfer: bool = True
    ):
        """
        Initialize transfer learner

        Args:
            transfer_learning_rate: How aggressively to update matrix (0.001 = conservative)
            min_episodes_before_transfer: Minimum episodes before applying transfer
            max_weight_change_per_transfer: Maximum weight change per transfer operation
            enable_transfer: Whether to enable transfer learning (for A/B testing)
        """
        self.transfer_lr = transfer_learning_rate
        self.min_episodes = min_episodes_before_transfer
        self.max_weight_change = max_weight_change_per_transfer
        self.enable_transfer = enable_transfer

        # Accumulated patterns
        self.patterns: List[PuzzlePattern] = []

        # Statistics
        self.statistics = TransferStatistics()

        # Task type mapping
        self.task_type_map = {
            "novice": "infrastructure_setup",
            "intermediate": "feature_development",
            "expert": "system_architecture"
        }

        logger.info(f"[PuzzleTransferLearner] Initialized with LR={transfer_learning_rate}, "
                   f"min_episodes={min_episodes_before_transfer}")

    def add_puzzle_episode(
        self,
        learning_phase: str,
        efficiency: float,
        confidence_delta: float,
        optimal_moves: int,
        agent_moves: int,
        success: bool,
        is_real_puzzle: bool = False
    ) -> None:
        """
        Add a puzzle training episode for pattern extraction

        Args:
            learning_phase: "novice", "intermediate", or "expert"
            efficiency: Puzzle solving efficiency (0.0-1.0)
            confidence_delta: Change in confidence after episode
            optimal_moves: Optimal solution length (from BFS)
            agent_moves: Agent's actual solution length
            success: Whether episode succeeded
            is_real_puzzle: True if from real Klotski puzzle, False if synthetic
        """
        # Calculate derived metrics
        action_efficiency = optimal_moves / agent_moves if agent_moves > 0 else 0.0

        # Planning quality: fewer wasted moves = better planning
        wasted_moves = agent_moves - optimal_moves
        planning_quality = 1.0 - (wasted_moves / max(agent_moves, 1))
        planning_quality = max(0.0, planning_quality)

        # Set pattern weight based on source (Real = 3x more valuable than Synthetic)
        pattern_weight = 3.0 if is_real_puzzle else 0.5

        pattern = PuzzlePattern(
            learning_phase=learning_phase,
            efficiency=efficiency,
            confidence_delta=confidence_delta,
            optimal_moves=optimal_moves,
            agent_moves=agent_moves,
            success=success,
            action_efficiency=action_efficiency,
            planning_quality=planning_quality,
            is_real_puzzle=is_real_puzzle,
            pattern_weight=pattern_weight
        )

        self.patterns.append(pattern)

        source = "REAL" if is_real_puzzle else "SYNTHETIC"
        logger.debug(f"[PuzzleTransferLearner] Added {source} pattern: phase={learning_phase}, "
                    f"efficiency={efficiency:.2f}, weight={pattern_weight}")

    def should_transfer(self) -> bool:
        """Check if we have enough data to perform transfer learning"""
        if not self.enable_transfer:
            return False

        return len(self.patterns) >= self.min_episodes

    def extract_patterns_by_phase(self) -> Dict[str, List[PuzzlePattern]]:
        """Group patterns by learning phase"""
        patterns_by_phase = {
            "novice": [],
            "intermediate": [],
            "expert": []
        }

        for pattern in self.patterns:
            phase = pattern.learning_phase
            if phase in patterns_by_phase:
                patterns_by_phase[phase].append(pattern)

        return patterns_by_phase

    def calculate_intervention_weights(
        self,
        patterns: List[PuzzlePattern]
    ) -> Dict[str, float]:
        """
        Calculate optimal intervention weights from patterns

        Strategy:
        - High efficiency (≥0.8) → Increase "suggest" (direct action)
        - Medium efficiency (0.6-0.8) → Slight "suggest" increase
        - Low efficiency (<0.6) → Increase "retry" (need correction)
        - Very low efficiency (<0.4) → Increase "wait" (need more info)

        NEW: Weighted averaging (Real patterns = 3.0, Synthetic = 0.5)

        Returns:
            Dict mapping intervention type to weight adjustment
        """
        if not patterns:
            return {"suggest": 0.0, "retry": 0.0, "wait": 0.0, "terminate": 0.0}

        # Calculate WEIGHTED average efficiency (Real patterns count 6x more)
        total_weight = sum(p.pattern_weight for p in patterns)
        avg_efficiency = sum(p.efficiency * p.pattern_weight for p in patterns) / total_weight
        avg_planning = sum(p.planning_quality * p.pattern_weight for p in patterns) / total_weight

        # Weighted success rate
        weighted_successes = sum(p.pattern_weight for p in patterns if p.success)
        success_rate = weighted_successes / total_weight

        # Base weights (neutral)
        weights = {
            "suggest": 0.0,
            "retry": 0.0,
            "wait": 0.0,
            "terminate": 0.0
        }

        # High efficiency → reinforce "suggest"
        if avg_efficiency >= 0.8:
            weights["suggest"] = +0.05 * success_rate
            logger.debug(f"  High efficiency ({avg_efficiency:.2f}) → suggest +{weights['suggest']:.3f}")

        # Medium efficiency → slight "suggest" increase
        elif avg_efficiency >= 0.6:
            weights["suggest"] = +0.02 * success_rate
            logger.debug(f"  Medium efficiency ({avg_efficiency:.2f}) → suggest +{weights['suggest']:.3f}")

        # Low efficiency → reinforce "retry"
        elif avg_efficiency >= 0.4:
            weights["retry"] = +0.03
            weights["suggest"] = -0.01  # Slightly decrease suggest
            logger.debug(f"  Low efficiency ({avg_efficiency:.2f}) → retry +{weights['retry']:.3f}")

        # Very low efficiency → reinforce "wait" (need more info)
        else:
            weights["wait"] = +0.04
            weights["suggest"] = -0.02
            logger.debug(f"  Very low efficiency ({avg_efficiency:.2f}) → wait +{weights['wait']:.3f}")

        # Good planning → reduce "wait" (don't need to wait)
        if avg_planning >= 0.7:
            weights["wait"] = min(weights["wait"], -0.01)

        # Cap weight changes
        for key in weights:
            weights[key] = np.clip(weights[key],
                                  -self.max_weight_change,
                                  self.max_weight_change)

        return weights

    def transfer_to_matrix(
        self,
        current_matrix: np.ndarray,
        matrix_shape: Tuple[int, int] = (10, 4)
    ) -> Tuple[np.ndarray, Dict[str, any]]:
        """
        Transfer learned patterns to routing matrix

        Args:
            current_matrix: Current routing matrix (10×4)
            matrix_shape: Expected matrix shape

        Returns:
            (updated_matrix, transfer_info)
        """
        if not self.should_transfer():
            logger.info(f"[PuzzleTransferLearner] Not enough episodes ({len(self.patterns)}/{self.min_episodes})")
            return current_matrix.copy(), {"transfer_applied": False}

        logger.info(f"[PuzzleTransferLearner] Transferring {len(self.patterns)} patterns to routing matrix")

        # Extract patterns by phase
        patterns_by_phase = self.extract_patterns_by_phase()

        # Calculate weight adjustments for each phase
        phase_adjustments = {}
        for phase, patterns in patterns_by_phase.items():
            if patterns:
                weights = self.calculate_intervention_weights(patterns)
                phase_adjustments[phase] = weights
                logger.info(f"  Phase '{phase}': {len(patterns)} patterns → {weights}")

        # Apply adjustments to matrix (conservative update)
        updated_matrix = current_matrix.copy()

        # Intervention mapping to matrix columns
        intervention_cols = {
            "suggest": 0,
            "retry": 1,
            "wait": 2,
            "terminate": 3
        }

        transfer_info = {
            "transfer_applied": True,
            "patterns_transferred": len(self.patterns),
            "phase_adjustments": phase_adjustments,
            "matrix_changes": []
        }

        # Apply adjustments (all rows get same adjustment for now)
        # Future: Could map specific modalities to specific patterns
        for phase, weights in phase_adjustments.items():
            for intervention, delta in weights.items():
                if abs(delta) < 0.001:  # Skip tiny changes
                    continue

                col_idx = intervention_cols[intervention]

                # Apply to all rows with conservative learning rate
                adjustment = delta * self.transfer_lr
                updated_matrix[:, col_idx] += adjustment

                transfer_info["matrix_changes"].append({
                    "phase": phase,
                    "intervention": intervention,
                    "adjustment": adjustment,
                    "column": col_idx
                })

                # Update statistics
                if delta > 0:
                    if intervention == "suggest":
                        self.statistics.suggest_weight_increases += 1
                    elif intervention == "retry":
                        self.statistics.retry_weight_increases += 1
                    elif intervention == "wait":
                        self.statistics.wait_weight_increases += 1

        # Normalize matrix rows to prevent drift
        row_sums = updated_matrix.sum(axis=1, keepdims=True)
        updated_matrix = updated_matrix / row_sums

        # Update statistics
        self.statistics.total_transfers += 1
        self.statistics.successful_transfers += 1
        self.statistics.matrix_updates_applied += len(transfer_info["matrix_changes"])

        avg_efficiency = np.mean([p.efficiency for p in self.patterns])
        avg_conf_gain = np.mean([p.confidence_delta for p in self.patterns])
        self.statistics.average_efficiency_transferred = avg_efficiency
        self.statistics.average_confidence_gain = avg_conf_gain

        # Add to history
        self.statistics.transfer_history.append({
            "patterns_count": len(self.patterns),
            "avg_efficiency": avg_efficiency,
            "phase_adjustments": phase_adjustments
        })

        logger.info(f"[PuzzleTransferLearner] Transfer complete: {len(transfer_info['matrix_changes'])} changes applied")

        # Clear patterns after transfer
        self.patterns = []

        return updated_matrix, transfer_info

    def get_statistics(self) -> Dict:
        """Get transfer learning statistics"""
        return {
            "total_transfers": self.statistics.total_transfers,
            "successful_transfers": self.statistics.successful_transfers,
            "matrix_updates_applied": self.statistics.matrix_updates_applied,
            "suggest_increases": self.statistics.suggest_weight_increases,
            "retry_increases": self.statistics.retry_weight_increases,
            "wait_increases": self.statistics.wait_weight_increases,
            "avg_efficiency": self.statistics.average_efficiency_transferred,
            "avg_confidence_gain": self.statistics.average_confidence_gain,
            "patterns_accumulated": len(self.patterns),
            "ready_for_transfer": self.should_transfer()
        }

    def reset(self):
        """Reset accumulated patterns (for testing)"""
        self.patterns = []
        logger.info("[PuzzleTransferLearner] Reset - cleared all accumulated patterns")


# Demo usage
if __name__ == "__main__":
    print("="*70)
    print("PUZZLE TRANSFER LEARNER - DEMO")
    print("="*70)

    # Create transfer learner
    learner = PuzzleTransferLearner(
        transfer_learning_rate=0.001,
        min_episodes_before_transfer=5
    )

    print(f"\n[Setup] Transfer LR: {learner.transfer_lr}")
    print(f"[Setup] Min episodes: {learner.min_episodes}")

    # Simulate puzzle training episodes
    print("\n[Simulation] Adding 10 puzzle training episodes...")

    episodes = [
        ("novice", 0.75, +0.02, 81, 108, True),      # Good novice performance
        ("novice", 0.65, +0.01, 81, 125, True),      # Acceptable novice
        ("intermediate", 0.82, +0.05, 81, 99, True), # Excellent intermediate
        ("intermediate", 0.78, +0.03, 81, 104, True),# Good intermediate
        ("intermediate", 0.55, -0.05, 81, 147, True),# Poor intermediate
        ("expert", 0.88, +0.07, 81, 92, True),       # Excellent expert
        ("expert", 0.85, +0.05, 81, 95, True),       # Excellent expert
        ("expert", 0.45, -0.08, 81, 180, False),     # Failed expert
        ("novice", 0.72, +0.02, 81, 113, True),      # Good novice
        ("intermediate", 0.68, +0.01, 81, 119, True) # Acceptable intermediate
    ]

    for i, (phase, eff, conf_delta, opt, agent, success) in enumerate(episodes):
        learner.add_puzzle_episode(phase, eff, conf_delta, opt, agent, success)
        print(f"  Episode {i+1}: phase={phase:12}, eff={eff:.2f}, conf_delta={conf_delta:+.2f}")

    # Check if ready for transfer
    print(f"\n[Status] Ready for transfer: {learner.should_transfer()}")
    print(f"[Status] Patterns accumulated: {len(learner.patterns)}")

    # Create mock routing matrix
    print("\n[Matrix] Creating mock 10×4 routing matrix...")
    mock_matrix = np.random.rand(10, 4)
    mock_matrix = mock_matrix / mock_matrix.sum(axis=1, keepdims=True)  # Normalize rows

    print(f"  Shape: {mock_matrix.shape}")
    print(f"  Initial suggest column mean: {mock_matrix[:, 0].mean():.3f}")
    print(f"  Initial retry column mean: {mock_matrix[:, 1].mean():.3f}")

    # Transfer patterns to matrix
    print("\n[Transfer] Applying transfer learning...")
    updated_matrix, transfer_info = learner.transfer_to_matrix(mock_matrix)

    print(f"\n[Results] Transfer applied: {transfer_info['transfer_applied']}")
    print(f"[Results] Patterns transferred: {transfer_info['patterns_transferred']}")
    print(f"[Results] Matrix changes: {len(transfer_info['matrix_changes'])}")

    for change in transfer_info["matrix_changes"]:
        print(f"  - Phase '{change['phase']}': {change['intervention']} column "
              f"adjusted by {change['adjustment']:+.6f}")

    print(f"\n[Matrix] Updated suggest column mean: {updated_matrix[:, 0].mean():.3f}")
    print(f"[Matrix] Updated retry column mean: {updated_matrix[:, 1].mean():.3f}")

    # Get statistics
    stats = learner.get_statistics()
    print(f"\n[Statistics]")
    print(f"  Total transfers: {stats['total_transfers']}")
    print(f"  Matrix updates applied: {stats['matrix_updates_applied']}")
    print(f"  Suggest weight increases: {stats['suggest_increases']}")
    print(f"  Retry weight increases: {stats['retry_increases']}")
    print(f"  Average efficiency: {stats['avg_efficiency']:.3f}")
    print(f"  Average confidence gain: {stats['avg_confidence_gain']:+.3f}")

    print("\n" + "="*70)
    print("DEMO COMPLETE")
    print("="*70)
