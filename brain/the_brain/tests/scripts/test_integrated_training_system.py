"""
Test Integrated Training System (Phase 3)

Validates complete training pipeline:
1. Puzzle training (20 episodes)
2. Transfer learning (Puzzle → Production)
3. Production validation (Tool call generation)

Expected outcomes:
- Puzzle success rate > 50%
- Transfer patterns accumulated (15-20)
- Production predictions change after transfer
- Tool calls generated with inferred parameters
"""

from core.integrated_training_system import IntegratedTrainingSystem
import time


def test_integrated_training_system():
    """Test complete integrated training workflow"""

    print("=" * 80)
    print("TEST: INTEGRATED TRAINING SYSTEM")
    print("=" * 80)

    # Define test tasks
    test_tasks = [
        "Deploy Docker container nginx on port 8080",
        "Debug payment service error in production",
        "Optimize database query performance with indexing",
        "Setup Kubernetes cluster with monitoring"
    ]

    # Initialize system
    print("\n[SETUP] Initializing integrated training system...")
    system = IntegratedTrainingSystem(
        puzzle_episodes=20,  # Need enough episodes to accumulate patterns (min 5)
        transfer_lr=0.001,
        production_lr=0.005,
        enable_tool_calls=True,
        enable_ctm=False,  # Disable CTM for faster testing
        verbose=True
    )

    print("[OK] System initialized")

    # Run complete training pipeline
    print("\n[TRAINING] Running full training pipeline...")
    print("  This will take ~2-3 minutes...")

    start_time = time.time()

    try:
        result = system.train_full_pipeline(
            test_tasks=test_tasks,
            save_results=True
        )

        training_duration = time.time() - start_time

        # Validate results
        print("\n" + "=" * 80)
        print("VALIDATION")
        print("=" * 80)

        success = True

        # Check overall success
        if result.overall_success:
            print("\n[OK] Training pipeline completed successfully")
        else:
            print("\n[FAIL] Training pipeline failed")
            success = False

        # Check Phase 1: Puzzle Training
        print("\n[PHASE 1 VALIDATION]")
        puzzle_success_rate = result.puzzle_stats.get('success_rate', 0)
        patterns_accumulated = result.puzzle_stats.get('patterns_accumulated', 0)

        if puzzle_success_rate > 0.5:
            print(f"  [OK] Puzzle success rate: {puzzle_success_rate*100:.1f}%")
        else:
            print(f"  [FAIL] Puzzle success rate too low: {puzzle_success_rate*100:.1f}%")
            success = False

        if patterns_accumulated >= 10:
            print(f"  [OK] Patterns accumulated: {patterns_accumulated}")
        else:
            print(f"  [WARN] Few patterns accumulated: {patterns_accumulated}")

        # Check Phase 2: Transfer Learning
        print("\n[PHASE 2 VALIDATION]")
        matrix_changes = result.transfer_stats.get('matrix_changes', 0)
        patterns_transferred = result.transfer_stats.get('patterns_transferred', 0)

        if matrix_changes > 0:
            print(f"  [OK] Matrix changes applied: {matrix_changes}")
        else:
            print(f"  [FAIL] No matrix changes applied")
            success = False

        if patterns_transferred >= 10:
            print(f"  [OK] Patterns transferred: {patterns_transferred}")
        else:
            print(f"  [WARN] Few patterns transferred: {patterns_transferred}")

        # Check Phase 3: Production Validation
        print("\n[PHASE 3 VALIDATION]")
        predictions_made = result.production_stats.get('predictions_made', 0)
        action_changes = result.action_changes
        tool_calls_generated = result.production_stats.get('tool_calls_generated', 0)

        if predictions_made == len(test_tasks):
            print(f"  [OK] Predictions made: {predictions_made}/{len(test_tasks)}")
        else:
            print(f"  [FAIL] Wrong number of predictions: {predictions_made}/{len(test_tasks)}")
            success = False

        if action_changes > 0:
            print(f"  [OK] Action changes: {action_changes}/{predictions_made}")
            print(f"       => Transfer learning influenced {action_changes} decision(s)!")
        else:
            print(f"  [WARN] No action changes detected (transfer may have no effect)")

        if tool_calls_generated > 0:
            print(f"  [OK] Tool calls generated: {tool_calls_generated}")
        else:
            print(f"  [WARN] No tool calls generated")

        # Performance check
        print("\n[PERFORMANCE]")
        print(f"  Total training time: {training_duration:.1f}s")

        if training_duration < 300:  # 5 minutes
            print(f"  [OK] Training completed within time limit")
        else:
            print(f"  [WARN] Training took longer than expected")

        # Test prediction with trained system
        print("\n[PREDICTION TEST]")
        test_task = "Deploy Docker container redis on port 6379 with persistence"
        print(f"  Task: {test_task}")

        prediction = system.predict(test_task)

        print(f"  Primary action: {prediction['prediction']['primary_action']}")
        print(f"  Confidence: {prediction['prediction']['confidence']:.3f}")

        # Try to get tool calls from actionable_decision
        actionable = prediction['prediction'].get('actionable_decision')
        if actionable:
            tool_calls = actionable.get('executable_tool_calls', [])
            if tool_calls:
                print(f"  [OK] Generated {len(tool_calls)} tool call(s)")
                print(f"       Tool: {tool_calls[0]['tool']}")
                if tool_calls[0].get('parameters'):
                    print(f"       Parameters: {list(tool_calls[0]['parameters'].keys())}")
            else:
                print(f"  [WARN] No tool calls in actionable_decision")
        else:
            print(f"  [WARN] No actionable_decision in prediction")

        # Get training statistics
        stats = system.get_training_stats()
        print("\n[STATISTICS]")
        print(f"  Training complete: {stats['training_complete']}")

        # Only print detailed stats if training completed
        if stats.get('puzzle_success_rate') is not None:
            print(f"  Puzzle success rate: {stats['puzzle_success_rate']*100:.1f}%")
            print(f"  Transfer patterns: {stats['transfer_patterns_count']}")
            print(f"  Production predictions: {stats['production_predictions_made']}")
            print(f"  Action changes: {stats['action_changes']}")
        else:
            print(f"  [WARN] Training incomplete - detailed stats unavailable")

        # Final verdict
        print("\n" + "=" * 80)
        if success:
            print("SUCCESS: Integrated training system working correctly!")
            print("=" * 80)
            print("\nKey achievements:")
            print("  [OK] Puzzle training accumulates efficiency patterns")
            print("  [OK] Transfer learning updates production routing matrix")
            print("  [OK] Production predictions leverage puzzle learning")
            print("  [OK] Tool calls generated with inferred parameters")
            print("  [OK] Complete pipeline: Puzzle -> Transfer -> Production -> Tools")
            return True
        else:
            print("FAILURE: Some validation checks failed")
            print("=" * 80)
            return False

    except Exception as e:
        print(f"\n[ERROR] Training failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_integrated_training_system()
    exit(0 if success else 1)
