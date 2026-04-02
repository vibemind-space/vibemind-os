"""
Test Confidence-Adaptive Trainer - Phase 5
Validates complete system integration of all 4 phases
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.confidence_adaptive_trainer import (
    ConfidenceAdaptiveTrainer,
    LearningPhase,
    TrainingEpisode,
    TrainingStatistics
)
import time


def test_basic_training():
    """Test 1: Basic training loop execution"""
    print("\n" + "="*70)
    print("TEST 1: Basic Training Loop Execution")
    print("="*70)

    trainer = ConfidenceAdaptiveTrainer(
        num_ensemble_solutions=3,
        enable_ctm_hints=True,
        enable_puzzle_mapping=True,
        initial_confidence=0.5,
        confidence_learning_rate=0.05,
        seed=42
    )

    print(f"\nInitial confidence: {trainer.current_confidence:.2f}")
    print(f"Initial learning phase: {trainer._get_learning_phase(trainer.current_confidence).value}")

    # Run 10 episodes
    print("\nRunning 10 training episodes...")
    stats = trainer.train(num_episodes=10, save_history=True, verbose=False)

    print(f"\nTraining Results:")
    print(f"  Total episodes: {stats.total_episodes}")
    print(f"  Successful episodes: {stats.successful_episodes}")
    print(f"  Success rate: {stats.successful_episodes/stats.total_episodes:.1%}")
    print(f"  Total steps: {stats.total_steps}")
    print(f"  Average episode length: {stats.average_episode_length:.1f}")
    print(f"  Final confidence: {trainer.current_confidence:.2f}")
    print(f"  Average confidence gain: {stats.average_confidence_gain:.3f}")

    if stats.total_episodes == 10 and len(trainer.training_history) == 10:
        print("\n[PASS] Basic training test passed!")
    else:
        print(f"\n[FAILED] Expected 10 episodes, got {stats.total_episodes}")


def test_learning_phases():
    """Test 2: Confidence adaptation across learning phases"""
    print("\n" + "="*70)
    print("TEST 2: Learning Phase Transitions")
    print("="*70)

    # Start as novice
    trainer_novice = ConfidenceAdaptiveTrainer(
        initial_confidence=0.2,
        confidence_learning_rate=0.1,  # Higher for faster transitions
        seed=42
    )

    print(f"\nStarting Phase: {trainer_novice._get_learning_phase(0.2).value}")
    assert trainer_novice._get_learning_phase(0.2) == LearningPhase.NOVICE

    # Run until intermediate
    print("Training to intermediate phase...")
    for i in range(5):
        episode = trainer_novice._train_episode(i, verbose=False)
        print(f"  Episode {i+1}: confidence={trainer_novice.current_confidence:.2f}, "
              f"phase={trainer_novice._get_learning_phase(trainer_novice.current_confidence).value}")

    # Check if reached intermediate
    current_phase = trainer_novice._get_learning_phase(trainer_novice.current_confidence)
    print(f"\nAfter 5 episodes:")
    print(f"  Current confidence: {trainer_novice.current_confidence:.2f}")
    print(f"  Current phase: {current_phase.value}")
    print(f"  Expected: intermediate or expert")

    if current_phase in [LearningPhase.INTERMEDIATE, LearningPhase.EXPERT]:
        print("\n[PASS] Learning phase transition test passed!")
    else:
        print(f"\n[FAILED] Still in {current_phase.value} phase")


def test_statistics_tracking():
    """Test 3: Statistics tracking across episodes"""
    print("\n" + "="*70)
    print("TEST 3: Statistics Tracking")
    print("="*70)

    trainer = ConfidenceAdaptiveTrainer(
        num_ensemble_solutions=3,
        initial_confidence=0.5,
        seed=42
    )

    # Run 15 episodes
    stats = trainer.train(num_episodes=15, save_history=True, verbose=False)

    print(f"\nStatistics Summary:")
    print(f"  Total episodes: {stats.total_episodes}")
    print(f"  Total steps: {stats.total_steps}")
    print(f"  Total checkpoints: {stats.total_checkpoints}")
    print(f"  Total mistakes: {stats.total_mistakes}")
    print(f"  Average episode length: {stats.average_episode_length:.1f}")

    print(f"\nEpisodes by Phase:")
    print(f"  Novice: {stats.novice_episodes}")
    print(f"  Intermediate: {stats.intermediate_episodes}")
    print(f"  Expert: {stats.expert_episodes}")
    print(f"  Total: {stats.novice_episodes + stats.intermediate_episodes + stats.expert_episodes}")

    # Validate statistics
    phase_sum = stats.novice_episodes + stats.intermediate_episodes + stats.expert_episodes
    if phase_sum == 15 and stats.total_episodes == 15:
        print("\n[PASS] Statistics tracking test passed!")
    else:
        print(f"\n[FAILED] Phase sum={phase_sum}, total={stats.total_episodes}")


def test_component_integration():
    """Test 4: Integration of all 4 phases"""
    print("\n" + "="*70)
    print("TEST 4: Component Integration (All 4 Phases)")
    print("="*70)

    trainer = ConfidenceAdaptiveTrainer(
        num_ensemble_solutions=3,
        enable_ctm_hints=True,
        enable_puzzle_mapping=True,
        initial_confidence=0.3,
        seed=42
    )

    # Run single episode and check all components
    episode = trainer._train_episode(0, verbose=False)

    print(f"\nEpisode Analysis:")
    print(f"  Episode ID: {episode.episode_id}")
    print(f"  Learning phase: {episode.learning_phase.value}")
    print(f"  Initial confidence: {episode.initial_confidence:.2f}")
    print(f"  Final confidence: {episode.final_confidence:.2f}")

    print(f"\nPhase 1 - Context-Aligned States:")
    print(f"  Total steps: {episode.total_steps}")
    print(f"  Checkpoints reached: {episode.checkpoints_reached}")
    print(f"  Mistakes made: {episode.mistakes_made}")
    print(f"  Success: {episode.success}")

    print(f"\nPhase 2 - Ensemble Path Planning:")
    print(f"  Solutions explored: {len(episode.solutions_explored)}")

    print(f"\nPhase 3 - Adaptive CTM Hints:")
    print(f"  Hints received: {len(episode.hints_received)}")
    if episode.hints_received:
        print(f"  First hint type: {episode.hints_received[0].hint_type.value}")
        print(f"  First hint confidence: {episode.hints_received[0].confidence:.2f}")

    print(f"\nPhase 4 - Puzzle-Agent Mapping:")
    print(f"  Puzzle moves: {len(episode.puzzle_path)}")
    if episode.puzzle_path:
        print(f"  First move type: {episode.puzzle_path[0].action_type.value}")

    # Validate all components present
    components_active = (
        episode.total_steps > 0 and
        len(episode.puzzle_path) > 0 and
        len(episode.hints_received) > 0
    )

    if components_active:
        print("\n[PASS] Component integration test passed!")
    else:
        print("\n[FAILED] Not all components active")


def test_confidence_adaptation():
    """Test 5: Confidence adaptation logic"""
    print("\n" + "="*70)
    print("TEST 5: Confidence Adaptation Logic")
    print("="*70)

    trainer = ConfidenceAdaptiveTrainer(
        initial_confidence=0.5,
        confidence_learning_rate=0.05,
        seed=42
    )

    print(f"\nInitial confidence: {trainer.current_confidence:.2f}")

    # Run 20 episodes and track confidence
    confidences = [trainer.current_confidence]
    for i in range(20):
        episode = trainer._train_episode(i, verbose=False)
        confidences.append(trainer.current_confidence)

    print(f"\nConfidence Progression (first 10 steps):")
    for i in range(min(10, len(confidences))):
        print(f"  Step {i}: {confidences[i]:.3f}")

    print(f"\nFinal confidence: {confidences[-1]:.3f}")
    print(f"  Initial: {confidences[0]:.3f}")
    print(f"  Change: {confidences[-1] - confidences[0]:+.3f}")

    # Check if confidence changed
    confidence_changed = abs(confidences[-1] - confidences[0]) > 0.01

    if confidence_changed:
        print("\n[PASS] Confidence adaptation test passed!")
    else:
        print("\n[FAILED] Confidence did not adapt")


def test_learning_curve():
    """Test 6: Learning curve generation"""
    print("\n" + "="*70)
    print("TEST 6: Learning Curve Generation")
    print("="*70)

    trainer = ConfidenceAdaptiveTrainer(
        initial_confidence=0.3,
        confidence_learning_rate=0.05,
        seed=42
    )

    # Train for 20 episodes
    trainer.train(num_episodes=20, save_history=True, verbose=False)

    # Get learning curve
    learning_curve = trainer.get_learning_curve()

    print(f"\nLearning Curve (first 10 points):")
    for i in range(min(10, len(learning_curve))):
        episode_id, confidence = learning_curve[i]
        print(f"  Episode {episode_id}: {confidence:.3f}")

    print(f"\nLearning Curve Summary:")
    print(f"  Total points: {len(learning_curve)}")
    print(f"  First confidence: {learning_curve[0][1]:.3f}")
    print(f"  Last confidence: {learning_curve[-1][1]:.3f}")
    print(f"  Overall change: {learning_curve[-1][1] - learning_curve[0][1]:+.3f}")

    if len(learning_curve) == 20:
        print("\n[PASS] Learning curve test passed!")
    else:
        print(f"\n[FAILED] Expected 20 points, got {len(learning_curve)}")


def test_episode_summary():
    """Test 7: Episode summary extraction"""
    print("\n" + "="*70)
    print("TEST 7: Episode Summary Extraction")
    print("="*70)

    trainer = ConfidenceAdaptiveTrainer(
        initial_confidence=0.5,
        seed=42
    )

    # Train 5 episodes
    trainer.train(num_episodes=5, save_history=True, verbose=False)

    # Get summaries
    print("\nEpisode Summaries:")
    for i in range(5):
        summary = trainer.get_episode_summary(i)
        if summary:
            print(f"\nEpisode {summary['episode_id']}:")
            print(f"  Learning phase: {summary['learning_phase']}")
            print(f"  Initial confidence: {summary['initial_confidence']:.3f}")
            print(f"  Final confidence: {summary['final_confidence']:.3f}")
            print(f"  Success: {summary['success']}")
            print(f"  Steps: {summary['steps']}")
            print(f"  Checkpoints: {summary['checkpoints']}")
            print(f"  Mistakes: {summary['mistakes']}")
            print(f"  Hints received: {summary['hints_received']}")
            print(f"  Puzzle moves: {summary['puzzle_moves']}")

    # Check if all summaries retrieved
    all_summaries_valid = all(
        trainer.get_episode_summary(i) is not None
        for i in range(5)
    )

    if all_summaries_valid:
        print("\n[PASS] Episode summary test passed!")
    else:
        print("\n[FAILED] Could not retrieve all summaries")


def test_end_to_end():
    """Test 8: End-to-end system validation"""
    print("\n" + "="*70)
    print("TEST 8: End-to-End System Validation")
    print("="*70)

    print("\nInitializing complete system...")
    trainer = ConfidenceAdaptiveTrainer(
        num_ensemble_solutions=3,
        enable_ctm_hints=True,
        enable_puzzle_mapping=True,
        initial_confidence=0.4,
        confidence_learning_rate=0.05,
        seed=42
    )

    print(f"Initial state:")
    print(f"  Confidence: {trainer.current_confidence:.2f}")
    print(f"  Learning phase: {trainer._get_learning_phase(trainer.current_confidence).value}")

    # Run complete training
    print("\nRunning 30 episodes (this may take 10-15 seconds)...")
    start_time = time.time()
    stats = trainer.train(num_episodes=30, save_history=True, verbose=False)
    elapsed = time.time() - start_time

    print(f"\nTraining Complete!")
    print(f"  Time elapsed: {elapsed:.1f}s")
    print(f"  Episodes/second: {30/elapsed:.2f}")

    # Get final statistics
    summary = trainer.get_statistics_summary()

    print(f"\nFinal Statistics:")
    print(f"  Total episodes: {summary['total_episodes']}")
    print(f"  Successful episodes: {summary['successful_episodes']}")
    print(f"  Success rate: {summary['success_rate']:.1%}")
    print(f"  Total steps: {summary['total_steps']}")
    print(f"  Total checkpoints: {summary['total_checkpoints']}")
    print(f"  Total mistakes: {summary['total_mistakes']}")
    print(f"  Average episode length: {summary['average_episode_length']:.1f}")
    print(f"  Final confidence: {summary['final_confidence']:.3f}")
    print(f"  Average confidence gain: {summary['average_confidence_gain']:.3f}")

    print(f"\nEpisodes by Phase:")
    for phase, count in summary['episodes_by_phase'].items():
        print(f"  {phase}: {count}")

    # Validate system health
    system_healthy = (
        summary['total_episodes'] == 30 and
        summary['total_steps'] > 0 and
        summary['total_checkpoints'] > 0 and
        len(trainer.training_history) == 30
    )

    if system_healthy:
        print("\n[PASS] End-to-end system test passed!")
        print("\nSYSTEM STATUS: ALL 4 PHASES INTEGRATED AND OPERATIONAL")
    else:
        print("\n[FAILED] System health check failed")


def main():
    print("="*70)
    print("CONFIDENCE-ADAPTIVE TRAINER TEST SUITE - PHASE 5")
    print("="*70)
    print("\nThis test validates integration of all 4 phases:")
    print("  Phase 1: Context-Aligned States")
    print("  Phase 2: Ensemble Path Planning")
    print("  Phase 3: Adaptive CTM Hints")
    print("  Phase 4: Puzzle-Agent Mapping")

    # Run all tests
    test_basic_training()
    test_learning_phases()
    test_statistics_tracking()
    test_component_integration()
    test_confidence_adaptation()
    test_learning_curve()
    test_episode_summary()
    test_end_to_end()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)
    print("\nPhase 5: Confidence-Adaptive Training - COMPLETE")


if __name__ == '__main__':
    main()
