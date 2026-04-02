"""
Confidence-Adaptive Trainer - Phase 5
Integrates all components for complete training system

Components integrated:
1. Context-Aligned States (Phase 1) - State representation with temporal context
2. Ensemble Path Planning (Phase 2) - Multi-path exploration with checkpoints
3. Adaptive CTM Hints (Phase 3) - Proactive thinking and guidance
4. Puzzle-Agent Mapping (Phase 4) - Transfer learning from puzzle domain

Training strategy:
- Novice (confidence < 0.3): Intensive exploration, frequent hints, learn from mistakes
- Intermediate (0.3 <= confidence < 0.7): Balanced exploration/exploitation, hints on demand
- Expert (confidence >= 0.7): Minimal exploration, rare hints, efficient execution

Key innovation: Confidence level controls learning strategy dynamically.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable
import time
import random

from core.shared_enums import LearningPhase
from core.context_aligned_state import ContextAlignedState, ActionMetadata, ContextDimensions
from core.ensemble_path_planner import EnsemblePathPlanner, SolutionPath, MetaPath
from core.adaptive_ctm_hint_generator import AdaptiveCTMHintGenerator, CTMHint, HintType
from core.puzzle_agent_mapper import PuzzleAgentMapper, PuzzleMove, AgentAction
from learning_engine.synthetic_conversation_generator import SyntheticConversationGenerator

try:
    from core.real_puzzle_trainer import RealPuzzleTrainer
    REAL_PUZZLE_AVAILABLE = True
except ImportError:
    REAL_PUZZLE_AVAILABLE = False
    print("[WARNING] RealPuzzleTrainer not available - will use synthetic mode only")

try:
    from core.puzzle_transfer_learner import PuzzleTransferLearner
    TRANSFER_LEARNER_AVAILABLE = True
except ImportError:
    TRANSFER_LEARNER_AVAILABLE = False
    print("[WARNING] PuzzleTransferLearner not available - transfer learning disabled")


@dataclass
class TrainingEpisode:
    """Single training episode result"""
    episode_id: int
    initial_confidence: float
    final_confidence: float
    learning_phase: LearningPhase
    conversation: List[ContextAlignedState]
    puzzle_path: List[PuzzleMove]
    hints_received: List[CTMHint]
    solutions_explored: List[SolutionPath]
    meta_path: Optional[MetaPath]
    success: bool
    total_steps: int
    total_time: float
    checkpoints_reached: int
    mistakes_made: int


@dataclass
class TrainingStatistics:
    """Overall training statistics"""
    total_episodes: int = 0
    successful_episodes: int = 0
    total_steps: int = 0
    total_checkpoints: int = 0
    total_mistakes: int = 0
    average_confidence_gain: float = 0.0
    average_episode_length: float = 0.0
    hints_accepted: int = 0
    hints_rejected: int = 0

    # By learning phase
    novice_episodes: int = 0
    intermediate_episodes: int = 0
    expert_episodes: int = 0


class ConfidenceAdaptiveTrainer:
    """
    Complete training system integrating all 4 phases

    Training loop:
    1. Generate/load task
    2. Determine learning phase from confidence
    3. Start CTM hint generator (background thinking)
    4. Plan paths with ensemble (multiple strategies)
    5. Execute conversation with hints
    6. Map to puzzle representation
    7. Extract lessons and update confidence
    8. Repeat with adapted strategy

    Like human learning:
    - Beginners: Explore widely, make mistakes, need guidance
    - Intermediates: Balance learning and performance
    - Experts: Execute efficiently, rarely need help
    """

    def __init__(
        self,
        num_ensemble_solutions: int = 5,
        enable_ctm_hints: bool = True,
        enable_puzzle_mapping: bool = True,
        use_real_puzzle: bool = False,
        puzzle_layout_path: Optional[str] = None,
        max_bfs_nodes: int = 50000,
        initial_confidence: float = 0.5,
        confidence_learning_rate: float = 0.05,
        enable_transfer_learning: bool = True,
        transfer_learning_rate: float = 0.001,
        seed: int = 42
    ):
        """
        Args:
            num_ensemble_solutions: Number of diverse paths to explore
            enable_ctm_hints: Enable background thinking hints
            enable_puzzle_mapping: Enable puzzle-agent transfer learning
            use_real_puzzle: Use real Klotski puzzle solving (not synthetic)
            puzzle_layout_path: Path to Klotski layout JSON
            max_bfs_nodes: Maximum BFS nodes for puzzle solving
            initial_confidence: Starting confidence level
            confidence_learning_rate: How fast confidence adapts
            enable_transfer_learning: Enable puzzle→production transfer learning
            transfer_learning_rate: Conservative LR for matrix updates (default 0.001)
            seed: Random seed
        """
        self.enable_ctm_hints = enable_ctm_hints
        self.enable_puzzle_mapping = enable_puzzle_mapping
        self.use_real_puzzle = use_real_puzzle and REAL_PUZZLE_AVAILABLE
        self.confidence_learning_rate = confidence_learning_rate
        self.enable_transfer_learning = enable_transfer_learning
        self.random = random.Random(seed)

        # Check if real puzzle mode is requested but not available
        if use_real_puzzle and not REAL_PUZZLE_AVAILABLE:
            print("[WARNING] Real puzzle mode requested but not available - falling back to synthetic")

        # Initialize components
        self.ensemble_planner = EnsemblePathPlanner(
            num_solutions=num_ensemble_solutions,
            checkpoint_threshold=0.6,
            seed=seed
        )

        self.hint_generator = AdaptiveCTMHintGenerator(
            hint_cooldown_novice=2.0,
            hint_cooldown_intermediate=5.0,
            hint_cooldown_expert=10.0,
            enable_proactive=enable_ctm_hints,
            seed=seed
        )

        self.puzzle_mapper = PuzzleAgentMapper()

        self.conversation_generator = SyntheticConversationGenerator(seed=seed)

        # Initialize real puzzle trainer if enabled
        self.real_puzzle_trainer = None
        if self.use_real_puzzle:
            self.real_puzzle_trainer = RealPuzzleTrainer(
                puzzle_layout_path=puzzle_layout_path,
                max_bfs_nodes=max_bfs_nodes,
                seed=seed
            )

        # Initialize transfer learner if enabled
        self.transfer_learner = None
        if enable_transfer_learning and TRANSFER_LEARNER_AVAILABLE:
            self.transfer_learner = PuzzleTransferLearner(
                transfer_learning_rate=transfer_learning_rate,
                min_episodes_before_transfer=5,
                max_weight_change_per_transfer=0.05,
                enable_transfer=True
            )
            print(f"[INFO] Transfer learning enabled (LR={transfer_learning_rate})")
        elif enable_transfer_learning and not TRANSFER_LEARNER_AVAILABLE:
            print("[WARNING] Transfer learning requested but PuzzleTransferLearner not available")

        # Training state
        self.current_confidence = initial_confidence
        self.training_history: List[TrainingEpisode] = []
        self.statistics = TrainingStatistics()

    def train(
        self,
        num_episodes: int = 100,
        save_history: bool = True,
        verbose: bool = True
    ) -> TrainingStatistics:
        """
        Run training for specified number of episodes

        Args:
            num_episodes: Number of training episodes
            save_history: Whether to save episode history
            verbose: Print progress

        Returns:
            Training statistics
        """
        if verbose:
            print(f"\n{'='*70}")
            print(f"CONFIDENCE-ADAPTIVE TRAINING")
            print(f"{'='*70}")
            print(f"Episodes: {num_episodes}")
            print(f"Initial confidence: {self.current_confidence:.2f}")
            print(f"Training mode: {'REAL PUZZLE' if self.use_real_puzzle else 'SYNTHETIC'}")
            print(f"CTM hints: {'Enabled' if self.enable_ctm_hints else 'Disabled'}")
            print(f"Puzzle mapping: {'Enabled' if self.enable_puzzle_mapping else 'Disabled'}")

        start_time = time.time()

        for episode_id in range(num_episodes):
            # Run single episode
            episode = self._train_episode(episode_id, verbose=verbose)

            # Update statistics
            self._update_statistics(episode)

            # Save to history
            if save_history:
                self.training_history.append(episode)

            # Print progress
            if verbose and (episode_id + 1) % 10 == 0:
                self._print_progress(episode_id + 1, num_episodes)

        elapsed = time.time() - start_time

        if verbose:
            print(f"\n{'='*70}")
            print(f"TRAINING COMPLETE")
            print(f"{'='*70}")
            print(f"Total time: {elapsed:.1f}s")
            print(f"Success rate: {self.statistics.successful_episodes}/{num_episodes} ({self.statistics.successful_episodes/num_episodes:.1%})")
            print(f"Final confidence: {self.current_confidence:.2f}")
            print(f"Average confidence gain: {self.statistics.average_confidence_gain:.3f}")

        return self.statistics

    def _train_episode(
        self,
        episode_id: int,
        verbose: bool = False
    ) -> TrainingEpisode:
        """Run single training episode"""
        initial_confidence = self.current_confidence
        learning_phase = self._get_learning_phase(self.current_confidence)

        # ============================================================
        # Use REAL PUZZLE or SYNTHETIC mode
        # ============================================================
        if self.use_real_puzzle and self.real_puzzle_trainer:
            # REAL PUZZLE MODE: Train with actual Klotski solving
            puzzle_episode = self.real_puzzle_trainer.train_episode_with_puzzle(
                episode_id=episode_id,
                learning_phase=learning_phase,
                initial_confidence=initial_confidence,
                verbose=verbose
            )

            # Update confidence from puzzle results
            self.current_confidence = puzzle_episode.final_confidence

            # Feed to transfer learner if enabled (REAL PUZZLE MODE)
            if self.transfer_learner:
                self.transfer_learner.add_puzzle_episode(
                    learning_phase=learning_phase.value,  # Extract string from enum
                    efficiency=puzzle_episode.efficiency,
                    confidence_delta=puzzle_episode.confidence_delta,
                    optimal_moves=puzzle_episode.optimal_moves,
                    agent_moves=puzzle_episode.agent_moves,
                    success=puzzle_episode.solved,
                    is_real_puzzle=True  # Real Klotski puzzle with BFS ground truth
                )

            # Convert PuzzleTrainingEpisode to TrainingEpisode format
            return TrainingEpisode(
                episode_id=episode_id,
                initial_confidence=puzzle_episode.initial_confidence,
                final_confidence=puzzle_episode.final_confidence,
                learning_phase=learning_phase,
                conversation=puzzle_episode.conversation,
                puzzle_path=[],  # Already mapped in conversation
                hints_received=[],  # Not used in real puzzle mode yet
                solutions_explored=[],
                meta_path=None,
                success=puzzle_episode.solved,
                total_steps=len(puzzle_episode.conversation),
                total_time=puzzle_episode.solve_time_seconds,
                checkpoints_reached=puzzle_episode.checkpoints,
                mistakes_made=0  # Not tracked in puzzle mode
            )

        else:
            # SYNTHETIC MODE: Generate fake conversation (original behavior)
            context_type = self._choose_context_type(learning_phase)
            target_steps = self._choose_target_steps(learning_phase)

            conversation = self.conversation_generator.generate_conversation(
                task_description=f"Episode {episode_id}",
                target_steps=target_steps,
                context_type=context_type,
                include_errors=(learning_phase == LearningPhase.NOVICE)
            )

            # Start CTM hint generator if enabled
            hints_received = []
            if self.enable_ctm_hints and conversation:
                self.hint_generator.start_thinking(conversation[0], history=[])
                time.sleep(0.1)  # Brief thinking time
                hints_received = self.hint_generator.get_all_hints()
                self.hint_generator.stop_thinking()

            # Map to puzzle if enabled
            puzzle_path = []
            if self.enable_puzzle_mapping and conversation:
                puzzle_path = self.puzzle_mapper.map_conversation_to_puzzle_path(conversation)

            # Evaluate success (arbitrary thresholds - no ground truth)
            success = (
                len(conversation) > 0 and
                conversation[-1].path_progress >= 0.8 and
                sum(1 for s in conversation if s.is_checkpoint) >= 2
            )

            # Update confidence
            if success:
                self.current_confidence = min(1.0, self.current_confidence + self.confidence_learning_rate)
            else:
                self.current_confidence = max(0.0, self.current_confidence - self.confidence_learning_rate * 2)

            # Count stats
            checkpoints = sum(1 for s in conversation if s.is_checkpoint)
            mistakes = sum(1 for s in conversation if s.last_action and not s.last_action.success)
            total_time = conversation[-1].cumulative_time if conversation else 0.0

            # Feed to transfer learner if enabled (SYNTHETIC MODE)
            if self.transfer_learner:
                # Calculate synthetic efficiency metrics
                agent_moves = len(conversation)
                optimal_moves = target_steps  # Target steps is the "optimal" for synthetic

                # Efficiency = optimal / actual (0.0 to 1.0)
                efficiency = min(1.0, optimal_moves / agent_moves) if agent_moves > 0 else 0.0

                # Confidence delta
                confidence_delta = self.current_confidence - initial_confidence

                self.transfer_learner.add_puzzle_episode(
                    learning_phase=learning_phase.value,
                    efficiency=efficiency,
                    confidence_delta=confidence_delta,
                    optimal_moves=optimal_moves,
                    agent_moves=agent_moves,
                    success=success,
                    is_real_puzzle=False  # Synthetic conversation (fake efficiency)
                )

            return TrainingEpisode(
                episode_id=episode_id,
                initial_confidence=initial_confidence,
                final_confidence=self.current_confidence,
                learning_phase=learning_phase,
                conversation=conversation,
                puzzle_path=puzzle_path,
                hints_received=hints_received,
                solutions_explored=[],  # Not used in synthetic training
                meta_path=None,
                success=success,
                total_steps=len(conversation),
                total_time=total_time,
                checkpoints_reached=checkpoints,
                mistakes_made=mistakes
            )

    def _get_learning_phase(self, confidence: float) -> LearningPhase:
        """Determine learning phase from confidence"""
        if confidence < 0.3:
            return LearningPhase.NOVICE
        elif confidence < 0.7:
            return LearningPhase.INTERMEDIATE
        else:
            return LearningPhase.EXPERT

    def _choose_context_type(self, phase: LearningPhase) -> str:
        """Choose context type based on learning phase"""
        if phase == LearningPhase.NOVICE:
            # Novices explore new territory
            return self.random.choice(['new', 'new', 'balanced'])
        elif phase == LearningPhase.INTERMEDIATE:
            # Intermediates balance new and familiar
            return self.random.choice(['new', 'balanced', 'familiar'])
        else:  # EXPERT
            # Experts stay in familiar territory
            return self.random.choice(['familiar', 'familiar', 'balanced'])

    def _choose_target_steps(self, phase: LearningPhase) -> int:
        """Choose target steps based on learning phase"""
        if phase == LearningPhase.NOVICE:
            # Novices take more steps (exploration)
            return self.random.randint(15, 25)
        elif phase == LearningPhase.INTERMEDIATE:
            # Intermediates moderate steps
            return self.random.randint(10, 15)
        else:  # EXPERT
            # Experts minimize steps (efficiency)
            return self.random.randint(5, 10)

    def _update_statistics(self, episode: TrainingEpisode):
        """Update training statistics"""
        self.statistics.total_episodes += 1

        if episode.success:
            self.statistics.successful_episodes += 1

        self.statistics.total_steps += episode.total_steps
        self.statistics.total_checkpoints += episode.checkpoints_reached
        self.statistics.total_mistakes += episode.mistakes_made

        # Update confidence gain
        confidence_gain = episode.final_confidence - episode.initial_confidence
        n = self.statistics.total_episodes
        self.statistics.average_confidence_gain = (
            (self.statistics.average_confidence_gain * (n - 1) + confidence_gain) / n
        )

        # Update average episode length
        self.statistics.average_episode_length = (
            self.statistics.total_steps / self.statistics.total_episodes
        )

        # Count by phase
        if episode.learning_phase == LearningPhase.NOVICE:
            self.statistics.novice_episodes += 1
        elif episode.learning_phase == LearningPhase.INTERMEDIATE:
            self.statistics.intermediate_episodes += 1
        else:
            self.statistics.expert_episodes += 1

    def _print_progress(self, episode: int, total: int):
        """Print training progress"""
        success_rate = self.statistics.successful_episodes / max(1, episode)
        print(f"Episode {episode}/{total}: "
              f"Confidence={self.current_confidence:.2f}, "
              f"Success rate={success_rate:.1%}, "
              f"Avg steps={self.statistics.average_episode_length:.1f}")

    def get_episode_summary(self, episode_id: int) -> Optional[Dict]:
        """Get summary of specific episode"""
        if episode_id >= len(self.training_history):
            return None

        episode = self.training_history[episode_id]

        return {
            'episode_id': episode.episode_id,
            'learning_phase': episode.learning_phase.value,
            'initial_confidence': episode.initial_confidence,
            'final_confidence': episode.final_confidence,
            'success': episode.success,
            'steps': episode.total_steps,
            'checkpoints': episode.checkpoints_reached,
            'mistakes': episode.mistakes_made,
            'hints_received': len(episode.hints_received),
            'puzzle_moves': len(episode.puzzle_path)
        }

    def get_learning_curve(self) -> List[Tuple[int, float]]:
        """Get confidence over episodes (learning curve)"""
        return [
            (ep.episode_id, ep.final_confidence)
            for ep in self.training_history
        ]

    def get_statistics_summary(self) -> Dict:
        """Get complete statistics summary"""
        return {
            'total_episodes': self.statistics.total_episodes,
            'successful_episodes': self.statistics.successful_episodes,
            'success_rate': self.statistics.successful_episodes / max(1, self.statistics.total_episodes),
            'total_steps': self.statistics.total_steps,
            'total_checkpoints': self.statistics.total_checkpoints,
            'total_mistakes': self.statistics.total_mistakes,
            'average_confidence_gain': self.statistics.average_confidence_gain,
            'average_episode_length': self.statistics.average_episode_length,
            'final_confidence': self.current_confidence,
            'episodes_by_phase': {
                'novice': self.statistics.novice_episodes,
                'intermediate': self.statistics.intermediate_episodes,
                'expert': self.statistics.expert_episodes
            }
        }

    def get_transfer_learner(self) -> Optional['PuzzleTransferLearner']:
        """
        Get transfer learner for production planner integration

        Returns:
            PuzzleTransferLearner instance if enabled, None otherwise
        """
        return self.transfer_learner

    def get_transfer_statistics(self) -> Optional[Dict]:
        """
        Get transfer learning statistics

        Returns:
            Dictionary with transfer learning stats if enabled, None otherwise
        """
        if self.transfer_learner:
            return self.transfer_learner.get_statistics()
        return None
