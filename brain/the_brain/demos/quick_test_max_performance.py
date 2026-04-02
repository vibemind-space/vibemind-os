"""
Quick test of max performance training system

Uses minimal episodes to verify functionality:
- 10 Synthetic episodes (~1s)
- 5 Real episodes (~15s) - will fallback to synthetic if Klotski not available
- Transfer learning
- 5 test tasks

Total time: ~20 seconds
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demos.run_max_performance_training import MaxPerformanceTrainingSystem


def main():
    print("="*80)
    print("QUICK TEST: Max Performance Training System")
    print("="*80)
    print("10 synthetic + 5 real episodes")
    print("Expected time: ~20 seconds")
    print("="*80)

    # Create system with minimal episodes
    system = MaxPerformanceTrainingSystem(
        synthetic_episodes=10,
        real_episodes=5,
        verbose=True
    )

    # Run with minimal test tasks
    test_tasks = [
        "Deploy Docker container with monitoring",
        "Debug production error in microservice",
        "Optimize database query performance",
        "Set up CI/CD pipeline",
        "Implement authentication flow"
    ]

    result = system.train_full_pipeline(test_tasks=test_tasks)

    # Print key metrics
    print("\n" + "="*80)
    print("QUICK TEST RESULTS")
    print("="*80)
    print(f"Overall success: {result['overall_success']}")
    print(f"Total time: {result['total_time']:.1f}s")
    print(f"Synthetic patterns: {result['phase1_synthetic']['patterns_accumulated']}")
    print(f"Real patterns: {result['phase2_real']['new_patterns']}")
    print(f"Matrix changes: {result['phase3_transfer']['matrix_changes']}")
    print(f"Predictions: {result['phase4_validation']['predictions']}")

    if result['overall_success']:
        print("\n[OK] System is working correctly!")
    else:
        print("\n[FAIL] System encountered errors")

    return result


if __name__ == "__main__":
    main()
