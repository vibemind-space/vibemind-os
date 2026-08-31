"""
Test Transfer Learner Integration - Validation of Complete Integration

This test validates that the transfer learner is properly integrated into the
confidence_adaptive_trainer and can accumulate puzzle patterns during training.

Tests:
1. Create trainer with transfer learning enabled
2. Run 10 puzzle training episodes
3. Verify transfer learner accumulates patterns
4. Check transfer readiness after 5 episodes
5. Display transfer statistics
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.confidence_adaptive_trainer import ConfidenceAdaptiveTrainer


def test_transfer_learner_integration():
    """Test transfer learner integration with confidence_adaptive_trainer"""
    print("\n" + "="*80)
    print("TEST: TRANSFER LEARNER INTEGRATION")
    print("="*80)

    # Create trainer with transfer learning enabled
    print("\n[SETUP] Creating trainer with transfer learning enabled...")
    trainer = ConfidenceAdaptiveTrainer(
        use_real_puzzle=True,           # Enable real puzzle mode
        enable_ctm_hints=False,          # Disable hints for simplicity
        enable_puzzle_mapping=False,     # Already mapped in real mode
        enable_transfer_learning=True,   # ENABLE TRANSFER LEARNING
        transfer_learning_rate=0.001,    # Conservative learning rate
        initial_confidence=0.40,         # Start at intermediate
        seed=42
    )

    # Check transfer learner initialized
    transfer_learner = trainer.get_transfer_learner()
    if transfer_learner is None:
        print("\n[FAIL] Transfer learner not initialized!")
        return False

    print(f"[OK] Transfer learner initialized")
    print(f"  Learning rate: {transfer_learner.transfer_lr}")
    print(f"  Min episodes: {transfer_learner.min_episodes}")

    # Run 10 training episodes
    print("\n[TRAINING] Running 10 puzzle episodes...")
    stats = trainer.train(num_episodes=10, save_history=True, verbose=False)

    # Check transfer learner accumulated patterns
    print(f"\n[RESULTS] Training complete")
    print(f"  Total episodes: {stats.total_episodes}")
    print(f"  Success rate: {stats.successful_episodes}/{stats.total_episodes} ({stats.successful_episodes/stats.total_episodes:.1%})")
    print(f"  Final confidence: {trainer.current_confidence:.2f}")

    # Get transfer statistics
    transfer_stats = trainer.get_transfer_statistics()
    if transfer_stats is None:
        print("\n[FAIL] Transfer statistics not available!")
        return False

    print(f"\n[TRANSFER LEARNER STATUS]")
    print(f"  Patterns accumulated: {transfer_stats['patterns_accumulated']}")
    print(f"  Ready for transfer: {transfer_stats['ready_for_transfer']}")
    print(f"  Total transfers: {transfer_stats['total_transfers']}")
    print(f"  Matrix updates: {transfer_stats['matrix_updates_applied']}")

    # Validate patterns accumulated
    if transfer_stats['patterns_accumulated'] != 10:
        print(f"\n[FAIL] Expected 10 patterns, got {transfer_stats['patterns_accumulated']}")
        return False

    # Check transfer readiness (should be ready after 5+ episodes)
    if not transfer_stats['ready_for_transfer']:
        print(f"\n[WARN] Transfer not ready after 10 episodes (min={transfer_learner.min_episodes})")

    # Show detailed transfer stats
    if transfer_stats['total_transfers'] > 0:
        print(f"\n[TRANSFER DETAILS]")
        print(f"  Suggest weight increases: {transfer_stats['suggest_increases']}")
        print(f"  Retry weight increases: {transfer_stats['retry_increases']}")
        print(f"  Wait weight increases: {transfer_stats['wait_increases']}")
        print(f"  Average efficiency: {transfer_stats['avg_efficiency']:.3f}")
        print(f"  Average confidence gain: {transfer_stats['avg_confidence_gain']:+.3f}")

    print("\n[OK] Transfer learner integration test passed!")
    return True


if __name__ == "__main__":
    success = test_transfer_learner_integration()

    if success:
        print("\n" + "="*80)
        print("SUCCESS: Transfer learner properly integrated!")
        print("="*80)
        print("\nNext steps:")
        print("  1. Update ProductionPlanner to accept transfer learning updates")
        print("  2. Create end-to-end demo")
    else:
        print("\n" + "="*80)
        print("FAILED: Transfer learner integration issues detected")
        print("="*80)
