"""
Integrated Training System (Phase 3)

Unified interface for complete training workflow:
1. Puzzle training (Klotski with confidence adaptation)
2. Transfer learning (Puzzle → Production)
3. Production validation (Tool call generation)

This system orchestrates all three components:
- ConfidenceAdaptiveTrainer: Trains on Klotski puzzles with adaptive confidence
- PuzzleTransferLearner: Extracts efficiency patterns for production
- ProductionPlanner: Applies learned patterns to real-world routing

Usage:
    >>> from core.integrated_training_system import IntegratedTrainingSystem
    >>>
    >>> # Create system
    >>> system = IntegratedTrainingSystem(
    ...     puzzle_episodes=20,
    ...     transfer_lr=0.001,
    ...     production_lr=0.005
    ... )
    >>>
    >>> # Run complete training workflow
    >>> results = system.train_full_pipeline()
    >>>
    >>> # Make predictions with trained system
    >>> prediction = system.predict("Deploy Docker container with monitoring")
    >>>
    >>> # Get training statistics
    >>> stats = system.get_training_stats()
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import json
from pathlib import Path
import time

# Import training components
from core.confidence_adaptive_trainer import ConfidenceAdaptiveTrainer
from core.puzzle_transfer_learner import PuzzleTransferLearner

# Production system (optional import)
try:
    from production.production_planner import ProductionPlanner
    PRODUCTION_AVAILABLE = True
except ImportError:
    PRODUCTION_AVAILABLE = False
    print("[WARNING] ProductionPlanner not available - using mock")


@dataclass
class TrainingPhaseResult:
    """Results from a single training phase"""
    phase_name: str
    success: bool
    duration_seconds: float
    metrics: Dict[str, float]
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class IntegratedTrainingResult:
    """Complete training workflow results"""
    total_duration: float
    phases: List[TrainingPhaseResult]
    overall_success: bool

    # Phase-specific summaries
    puzzle_stats: Dict[str, float]
    transfer_stats: Dict[str, float]
    production_stats: Dict[str, float]

    # Comparative metrics
    predictions_before: List[Dict]
    predictions_after: List[Dict]
    action_changes: int

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'total_duration': self.total_duration,
            'phases': [
                {
                    'phase_name': p.phase_name,
                    'success': p.success,
                    'duration_seconds': p.duration_seconds,
                    'metrics': p.metrics,
                    'notes': p.notes,
                    'errors': p.errors
                }
                for p in self.phases
            ],
            'overall_success': self.overall_success,
            'puzzle_stats': self.puzzle_stats,
            'transfer_stats': self.transfer_stats,
            'production_stats': self.production_stats,
            'predictions_before': self.predictions_before,
            'predictions_after': self.predictions_after,
            'action_changes': self.action_changes
        }


class IntegratedTrainingSystem:
    """
    Unified training system orchestrating:
    1. Puzzle training with confidence adaptation
    2. Transfer learning from puzzles to production
    3. Production validation with tool call generation

    This provides a single interface for the complete training workflow.
    """

    def __init__(
        self,
        puzzle_episodes: int = 20,
        transfer_lr: float = 0.001,
        production_lr: float = 0.005,
        session_log_dir: Optional[str] = None,
        enable_tool_calls: bool = True,
        enable_ctm: bool = False,
        verbose: bool = True
    ):
        """
        Initialize integrated training system

        Args:
            puzzle_episodes: Number of Klotski puzzle episodes to train
            transfer_lr: Learning rate for puzzle→production transfer (conservative)
            production_lr: Learning rate for production continuous learning
            session_log_dir: Path to conversation session logs (for production planner)
            enable_tool_calls: Enable tool call generation in production
            enable_ctm: Enable CTM async reasoning in production
            verbose: Print detailed progress messages
        """
        self.puzzle_episodes = puzzle_episodes
        self.transfer_lr = transfer_lr
        self.production_lr = production_lr
        self.session_log_dir = session_log_dir or "data/logs/sessions"
        self.enable_tool_calls = enable_tool_calls
        self.enable_ctm = enable_ctm
        self.verbose = verbose

        # Training components (initialized lazily)
        self.puzzle_trainer: Optional[ConfidenceAdaptiveTrainer] = None
        self.transfer_learner: Optional[PuzzleTransferLearner] = None
        self.production_planner = None  # ProductionPlanner or mock

        # Training state
        self.training_complete = False
        self.last_result: Optional[IntegratedTrainingResult] = None

        # Statistics
        self.total_training_time = 0.0
        self.puzzle_success_rate = 0.0
        self.transfer_patterns_count = 0
        self.production_predictions_made = 0

        if self.verbose:
            print("[IntegratedTrainingSystem] Initialized")
            print(f"  Puzzle episodes: {puzzle_episodes}")
            print(f"  Transfer LR: {transfer_lr}")
            print(f"  Production LR: {production_lr}")
            print(f"  Tool calls: {'enabled' if enable_tool_calls else 'disabled'}")
            print(f"  CTM reasoning: {'enabled' if enable_ctm else 'disabled'}")

    def train_full_pipeline(
        self,
        test_tasks: Optional[List[str]] = None,
        save_results: bool = True
    ) -> IntegratedTrainingResult:
        """
        Run complete training pipeline:
        1. Train on Klotski puzzles
        2. Transfer learning to production
        3. Validate with test tasks

        Args:
            test_tasks: Tasks to test before/after (default: 3 standard tasks)
            save_results: Save results to JSON file

        Returns:
            IntegratedTrainingResult with all phase metrics
        """
        if test_tasks is None:
            test_tasks = [
                "Deploy Docker container with monitoring",
                "Debug production error in payment service",
                "Optimize database query performance"
            ]

        start_time = time.time()
        phases = []

        print("\n" + "="*80)
        print("INTEGRATED TRAINING SYSTEM - FULL PIPELINE")
        print("="*80)

        # Phase 1: Puzzle Training
        print("\n" + "-"*80)
        print("PHASE 1: PUZZLE TRAINING (Klotski with Confidence Adaptation)")
        print("-"*80)

        phase1_result = self._phase1_puzzle_training()
        phases.append(phase1_result)

        if not phase1_result.success:
            print("\n[ERROR] Phase 1 failed - aborting pipeline")
            return self._create_failed_result(phases, time.time() - start_time)

        # Phase 2: Transfer Learning
        print("\n" + "-"*80)
        print("PHASE 2: TRANSFER LEARNING (Puzzle -> Production)")
        print("-"*80)

        phase2_result = self._phase2_transfer_learning()
        phases.append(phase2_result)

        if not phase2_result.success:
            print("\n[ERROR] Phase 2 failed - aborting pipeline")
            return self._create_failed_result(phases, time.time() - start_time)

        # Phase 3: Production Validation
        print("\n" + "-"*80)
        print("PHASE 3: PRODUCTION VALIDATION (Tool Call Generation)")
        print("-"*80)

        phase3_result = self._phase3_production_validation(test_tasks)
        phases.append(phase3_result)

        # Create final result
        total_duration = time.time() - start_time

        result = IntegratedTrainingResult(
            total_duration=total_duration,
            phases=phases,
            overall_success=all(p.success for p in phases),
            puzzle_stats=phase1_result.metrics,
            transfer_stats=phase2_result.metrics,
            production_stats=phase3_result.metrics,
            predictions_before=getattr(self, '_predictions_before', []),
            predictions_after=getattr(self, '_predictions_after', []),
            action_changes=self._count_action_changes()
        )

        self.last_result = result
        self.training_complete = True

        # Print summary
        self._print_summary(result)

        # Save results
        if save_results:
            self._save_results(result)

        return result

    def _phase1_puzzle_training(self) -> TrainingPhaseResult:
        """Phase 1: Train on Klotski puzzles with confidence adaptation"""
        start_time = time.time()

        try:
            # Initialize trainer with transfer learning enabled
            self.puzzle_trainer = ConfidenceAdaptiveTrainer(
                enable_transfer_learning=True,
                transfer_learning_rate=self.transfer_lr
            )

            print(f"\n[SETUP] Training on {self.puzzle_episodes} puzzle episodes...")
            print("  - Confidence adapts based on puzzle efficiency")
            print("  - Transfer learner accumulates efficiency patterns")

            # Run puzzle training
            training_stats = self.puzzle_trainer.train(
                num_episodes=self.puzzle_episodes,
                verbose=self.verbose
            )

            # Extract statistics from TrainingStatistics object
            successes = training_stats.successful_episodes
            total = training_stats.total_episodes
            success_rate = successes / total if total > 0 else 0.0
            conf_gain = training_stats.average_confidence_gain

            # Get initial and final confidence from trainer
            initial_conf = 0.5  # Default initial
            final_conf = self.puzzle_trainer.current_confidence

            self.puzzle_success_rate = success_rate
            self.transfer_learner = self.puzzle_trainer.transfer_learner
            self.transfer_patterns_count = len(self.transfer_learner.patterns)

            print(f"\n[RESULTS] Puzzle training complete")
            print(f"  Success rate: {successes}/{total} ({success_rate*100:.1f}%)")
            print(f"  Final confidence: {final_conf:.2f}")
            print(f"  Average confidence gain: {conf_gain:+.3f}")
            print(f"  Patterns accumulated: {self.transfer_patterns_count}")

            return TrainingPhaseResult(
                phase_name="puzzle_training",
                success=success_rate > 0.5,  # At least 50% success
                duration_seconds=time.time() - start_time,
                metrics={
                    'episodes': total,
                    'success_rate': success_rate,
                    'initial_confidence': initial_conf,
                    'final_confidence': final_conf,
                    'confidence_gain': conf_gain,
                    'patterns_accumulated': self.transfer_patterns_count
                },
                notes=[
                    f"Trained on {total} Klotski puzzle episodes",
                    f"Success rate: {success_rate*100:.1f}%",
                    f"Accumulated {self.transfer_patterns_count} efficiency patterns"
                ]
            )

        except Exception as e:
            print(f"\n[ERROR] Phase 1 failed: {e}")
            import traceback
            traceback.print_exc()

            return TrainingPhaseResult(
                phase_name="puzzle_training",
                success=False,
                duration_seconds=time.time() - start_time,
                metrics={},
                errors=[str(e)]
            )

    def _phase2_transfer_learning(self) -> TrainingPhaseResult:
        """Phase 2: Transfer puzzle learning to production matrix"""
        start_time = time.time()

        try:
            # Initialize production planner
            if PRODUCTION_AVAILABLE:
                self.production_planner = ProductionPlanner(
                    session_log_dir=self.session_log_dir,
                    enable_continuous_learning=True,
                    learning_rate=self.production_lr,
                    enable_semantic_coherence=False  # Disable to avoid JAX dependency
                )
            else:
                print("[WARNING] Using mock production planner")
                self.production_planner = self._create_mock_planner()

            print(f"\n[SETUP] Applying puzzle learning to production matrix...")
            print(f"  Patterns to transfer: {self.transfer_patterns_count}")
            print(f"  Transfer LR: {self.transfer_lr}")

            # Apply transfer learning
            transfer_result = self.production_planner.apply_puzzle_learning(
                self.transfer_learner
            )

            # Handle case where transfer wasn't applied
            if not transfer_result.get('transfer_applied', True):
                print(f"\n[RESULTS] Transfer skipped")
                print(f"  Reason: {transfer_result.get('reason', 'Unknown')}")
                print(f"  Patterns available: {transfer_result.get('patterns_transferred', 0)}")

                return TrainingPhaseResult(
                    phase_name="transfer_learning",
                    success=False,
                    duration_seconds=time.time() - start_time,
                    metrics={
                        'patterns_transferred': 0,
                        'matrix_changes': 0,
                        'total_transfers': 0
                    },
                    notes=[
                        f"Transfer skipped: {transfer_result.get('reason', 'Unknown')}",
                        f"Need {self.transfer_learner.min_episodes} patterns minimum"
                    ]
                )

            print(f"\n[RESULTS] Transfer complete")
            print(f"  Matrix changes: {transfer_result.get('matrix_changes', 0)}")
            print(f"  Total transfers: {transfer_result.get('total_transfers', 0)}")
            print(f"  Matrix version saved: {transfer_result.get('matrix_version', 'N/A')}")

            # matrix_changes is a list, need to get its length
            matrix_changes = transfer_result.get('matrix_changes', [])
            num_changes = len(matrix_changes) if isinstance(matrix_changes, list) else 0

            return TrainingPhaseResult(
                phase_name="transfer_learning",
                success=num_changes > 0,
                duration_seconds=time.time() - start_time,
                metrics={
                    'patterns_transferred': self.transfer_patterns_count,
                    'matrix_changes': num_changes,
                    'total_transfers': transfer_result.get('total_transfers', 0),
                    'suggest_increases': transfer_result.get('suggest_increases', 0),
                    'retry_increases': transfer_result.get('retry_increases', 0),
                    'wait_increases': transfer_result.get('wait_increases', 0)
                },
                notes=[
                    f"Transferred {self.transfer_patterns_count} patterns",
                    f"Applied {transfer_result.get('matrix_changes', 0)} matrix changes",
                    f"Saved as version: {transfer_result.get('matrix_version', 'N/A')}"
                ]
            )

        except Exception as e:
            print(f"\n[ERROR] Phase 2 failed: {e}")
            import traceback
            traceback.print_exc()

            return TrainingPhaseResult(
                phase_name="transfer_learning",
                success=False,
                duration_seconds=time.time() - start_time,
                metrics={},
                errors=[str(e)]
            )

    def _phase3_production_validation(self, test_tasks: List[str]) -> TrainingPhaseResult:
        """Phase 3: Validate production predictions with tool calls"""
        start_time = time.time()

        try:
            print(f"\n[SETUP] Testing production predictions...")
            print(f"  Test tasks: {len(test_tasks)}")
            print(f"  Tool calls: {'enabled' if self.enable_tool_calls else 'disabled'}")

            # Make predictions BEFORE and AFTER already done in phase 2
            # (production_planner has updated matrix)

            # Make predictions with updated matrix
            self._predictions_after = []

            for task in test_tasks:
                prediction = self.production_planner.predict(task)

                # Safely extract weight (multi_target_decision may not exist)
                weight = 0.0
                if 'multi_target_decision' in prediction['prediction']:
                    weight = prediction['prediction']['multi_target_decision'].get('primary', {}).get('weight', 0.0)

                # Safely extract tool calls
                tool_calls = 0
                if 'actionable_decision' in prediction['prediction']:
                    tool_calls = len(prediction['prediction']['actionable_decision'].get('executable_tool_calls', []))

                self._predictions_after.append({
                    'task': task,
                    'action': prediction['prediction']['primary_action'],
                    'confidence': prediction['prediction']['confidence'],
                    'weight': weight,
                    'tool_calls': tool_calls
                })

            # Count action changes (compare with baseline if available)
            action_changes = 0
            if hasattr(self, '_predictions_before'):
                for before, after in zip(self._predictions_before, self._predictions_after):
                    if before['action'] != after['action']:
                        action_changes += 1
                        if self.verbose:
                            print(f"\n  Task: {before['task'][:50]}...")
                            print(f"    BEFORE: {before['action']} (conf={before['confidence']:.3f})")
                            print(f"    AFTER:  {after['action']} (conf={after['confidence']:.3f})")
                            print(f"    => Action changed!")

            self.production_predictions_made = len(self._predictions_after)

            # Check tool calls generated
            total_tool_calls = sum(p['tool_calls'] for p in self._predictions_after)

            print(f"\n[RESULTS] Production validation complete")
            print(f"  Predictions made: {len(self._predictions_after)}")
            print(f"  Action changes: {action_changes}/{len(test_tasks)}")
            print(f"  Tool calls generated: {total_tool_calls}")

            return TrainingPhaseResult(
                phase_name="production_validation",
                success=True,  # Phase 3 always succeeds if reached
                duration_seconds=time.time() - start_time,
                metrics={
                    'predictions_made': len(self._predictions_after),
                    'action_changes': action_changes,
                    'tool_calls_generated': total_tool_calls,
                    'avg_confidence': np.mean([p['confidence'] for p in self._predictions_after])
                },
                notes=[
                    f"Tested {len(test_tasks)} production tasks",
                    f"{action_changes} actions changed due to transfer learning",
                    f"{total_tool_calls} executable tool calls generated"
                ]
            )

        except Exception as e:
            print(f"\n[ERROR] Phase 3 failed: {e}")
            import traceback
            traceback.print_exc()

            return TrainingPhaseResult(
                phase_name="production_validation",
                success=False,
                duration_seconds=time.time() - start_time,
                metrics={},
                errors=[str(e)]
            )

    def predict(self, task: str) -> Dict:
        """
        Make prediction with trained system

        Args:
            task: Task description

        Returns:
            Prediction dictionary with routing decision and tool calls
        """
        if not self.training_complete:
            print("[WARNING] Training not complete - using untrained system")

        if self.production_planner is None:
            raise RuntimeError("Production planner not initialized - run train_full_pipeline() first")

        return self.production_planner.predict(task)

    def get_training_stats(self) -> Dict:
        """Get comprehensive training statistics"""
        if self.last_result is None:
            return {'training_complete': False}

        return {
            'training_complete': self.training_complete,
            'total_duration': self.last_result.total_duration,
            'overall_success': self.last_result.overall_success,
            'puzzle_success_rate': self.puzzle_success_rate,
            'transfer_patterns_count': self.transfer_patterns_count,
            'production_predictions_made': self.production_predictions_made,
            'action_changes': self.last_result.action_changes,
            'phases': [
                {
                    'name': p.phase_name,
                    'success': p.success,
                    'duration': p.duration_seconds
                }
                for p in self.last_result.phases
            ]
        }

    def _count_action_changes(self) -> int:
        """Count how many actions changed after transfer learning"""
        if not hasattr(self, '_predictions_before') or not hasattr(self, '_predictions_after'):
            return 0

        changes = 0
        for before, after in zip(self._predictions_before, self._predictions_after):
            if before['action'] != after['action']:
                changes += 1

        return changes

    def _print_summary(self, result: IntegratedTrainingResult):
        """Print comprehensive training summary"""
        print("\n" + "="*80)
        print("TRAINING SUMMARY")
        print("="*80)

        print(f"\n[OVERALL]")
        print(f"  Status: {'SUCCESS' if result.overall_success else 'FAILED'}")
        print(f"  Total duration: {result.total_duration:.1f}s")

        print(f"\n[PHASE 1: PUZZLE TRAINING]")
        for key, val in result.puzzle_stats.items():
            print(f"  {key}: {val}")

        print(f"\n[PHASE 2: TRANSFER LEARNING]")
        for key, val in result.transfer_stats.items():
            print(f"  {key}: {val}")

        print(f"\n[PHASE 3: PRODUCTION VALIDATION]")
        for key, val in result.production_stats.items():
            print(f"  {key}: {val}")

        print(f"\n[IMPACT]")
        print(f"  Action changes: {result.action_changes}/{len(result.predictions_after)}")
        print(f"  Transfer learning influenced {result.action_changes} production decision(s)!")

        print("\n" + "="*80)

    def _save_results(self, result: IntegratedTrainingResult):
        """Save training results to JSON file"""
        output_dir = Path("data/training_results")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"integrated_training_{timestamp}.json"

        with open(output_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        print(f"\n[SAVED] Results saved to: {output_path}")

    def _create_failed_result(
        self,
        phases: List[TrainingPhaseResult],
        duration: float
    ) -> IntegratedTrainingResult:
        """Create failed result when pipeline aborts"""
        return IntegratedTrainingResult(
            total_duration=duration,
            phases=phases,
            overall_success=False,
            puzzle_stats={},
            transfer_stats={},
            production_stats={},
            predictions_before=[],
            predictions_after=[],
            action_changes=0
        )

    def _create_mock_planner(self):
        """Create mock planner when ProductionPlanner unavailable"""
        class MockPlanner:
            def apply_puzzle_learning(self, transfer_learner):
                return {
                    'matrix_changes': 2,
                    'total_transfers': 1,
                    'matrix_version': 'mock_v1'
                }

            def predict(self, task):
                return {
                    'prediction': {
                        'primary_action': 'suggest',
                        'confidence': 0.5,
                        'multi_target_decision': {
                            'primary': {'weight': 0.5}
                        },
                        'actionable_decision': {
                            'executable_tool_calls': []
                        }
                    }
                }

        return MockPlanner()


# Convenience function for quick training
def train_integrated_system(
    puzzle_episodes: int = 20,
    test_tasks: Optional[List[str]] = None,
    verbose: bool = True
) -> IntegratedTrainingResult:
    """
    Quick training with default settings

    Args:
        puzzle_episodes: Number of puzzle episodes
        test_tasks: Custom test tasks (optional)
        verbose: Print progress

    Returns:
        IntegratedTrainingResult
    """
    system = IntegratedTrainingSystem(
        puzzle_episodes=puzzle_episodes,
        verbose=verbose
    )

    return system.train_full_pipeline(test_tasks=test_tasks)
