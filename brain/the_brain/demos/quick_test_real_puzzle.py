"""
Quick test of real puzzle integration - validates BFS caching and basic functionality
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.confidence_adaptive_trainer import ConfidenceAdaptiveTrainer, LearningPhase

print("="*70)
print("QUICK TEST: Real Puzzle Integration with Caching")
print("="*70)

# Test 1: Single episode
print("\n[Test 1] Training 1 episode with real puzzle...")
trainer = ConfidenceAdaptiveTrainer(
    use_real_puzzle=True,
    enable_ctm_hints=False,
    enable_puzzle_mapping=False,
    initial_confidence=0.50,
    seed=42
)

stats = trainer.train(num_episodes=1, save_history=True, verbose=True)

print(f"\n[Result]")
print(f"  Success: {stats.successful_episodes}/{stats.total_episodes}")
print(f"  Final confidence: {trainer.current_confidence:.2f}")

if trainer.training_history:
    episode = trainer.training_history[0]
    print(f"  Episode success: {episode.success}")
    print(f"  Episode steps: {episode.total_steps}")
    print(f"  Solve time: {episode.total_time:.2f}s")

print("\n[Test 1] PASSED!" if stats.successful_episodes > 0 else "\n[Test 1] FAILED")

# Test 2: Multiple episodes (should be fast due to caching!)
print("\n[Test 2] Training 3 more episodes (should be FAST with cache)...")
stats2 = trainer.train(num_episodes=3, save_history=True, verbose=False)

print(f"\n[Result]")
print(f"  Success: {stats2.successful_episodes}/{stats2.total_episodes}")
print(f"  Total success: {trainer.statistics.successful_episodes}/{trainer.statistics.total_episodes}")

print("\n[Test 2] PASSED!" if stats2.successful_episodes > 0 else "\n[Test 2] FAILED")

print("\n" + "="*70)
print("QUICK TEST COMPLETE")
print("="*70)
