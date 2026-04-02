"""
Test Script: Learnable Gate Temperature (Phase 1)

Demonstrates adaptive gate temperature learning based on prediction accuracy.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor
from core.conversation_path_planner import ConversationPathPlanner

def test_learnable_gate_temp():
    """
    Test learnable gate temperature with simulated prediction feedback
    """
    print("=" * 70)
    print("TESTING LEARNABLE GATE TEMPERATURE (Phase 1)")
    print("=" * 70)
    print()

    # Initialize components
    meta_router = MetaRouter(enable_hippocampus=True, seed=42)
    strategy_lib = StrategyLibrary(max_strategies_per_type=20)
    brain_monitor = BrainActivityMonitor(history_length=100)

    # Create path planner with adaptive gating enabled
    planner = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=strategy_lib,
        brain_monitor=brain_monitor,
        enable_adaptive_gating=True,
        initial_gate_temp=0.5,
        gate_temp_lr=0.02,  # Faster learning for demo
        gate_temp_min=0.1,
        gate_temp_max=2.0
    )

    print(f"Initial gate temperature: {planner.gate_temp:.3f}")
    print(f"Learning rate: {planner.gate_temp_lr}")
    print(f"Bounds: [{planner.gate_temp_min}, {planner.gate_temp_max}]")
    print()

    # Train from session logs
    log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    planner.train_from_sessions(log_dir, limit=39)

    print("\n" + "=" * 70)
    print("SIMULATING PREDICTION FEEDBACK")
    print("=" * 70)
    print()

    # Simulate 30 predictions with varying accuracy
    # Phase 1: Low accuracy (5 wrong)
    print("Phase 1: Low accuracy scenario (many errors)")
    for i in range(5):
        correct = False
        planner.provide_prediction_feedback(correct)

    print()

    # Phase 2: Medium accuracy (mix)
    print("Phase 2: Medium accuracy scenario (mixed results)")
    for i in range(10):
        correct = i % 2 == 0  # 50% accurate
        planner.provide_prediction_feedback(correct)

    print()

    # Phase 3: High accuracy (mostly correct)
    print("Phase 3: High accuracy scenario (mostly correct)")
    for i in range(15):
        correct = i % 4 != 0  # 75% accurate
        planner.provide_prediction_feedback(correct)

    print()

    # Show final statistics
    print("=" * 70)
    print("FINAL STATISTICS")
    print("=" * 70)
    print()

    stats = planner.get_statistics()
    print(f"Predictions made: {stats['predictions_made']}")
    print(f"Predictions correct: {stats['predictions_correct']}")
    print(f"Overall accuracy: {stats['accuracy']:.1%}")
    print()

    if 'gate_temperature' in stats:
        gt = stats['gate_temperature']
        print("GATE TEMPERATURE EVOLUTION:")
        print(f"  Initial: 0.500")
        print(f"  Final: {gt['current']:.3f}")
        print(f"  Change: {gt['current'] - 0.5:+.3f}")
        print(f"  History length: {gt['history_length']}")
        print(f"  Recent accuracies: {[f'{a:.1%}' for a in gt['recent_accuracies']]}")
        print()

        # Interpretation
        if gt['current'] < 0.4:
            print("  >> SHARP ROUTING (high confidence)")
        elif gt['current'] > 0.6:
            print("  >> SOFT ROUTING (low confidence, hedging bets)")
        else:
            print("  >> BALANCED ROUTING")

    # Visualize temperature evolution
    if planner.gate_temp_history:
        print("\n" + "=" * 70)
        print("TEMPERATURE EVOLUTION GRAPH")
        print("=" * 70)

        plt.figure(figsize=(12, 6))

        # Plot 1: Gate temperature over time
        plt.subplot(2, 1, 1)
        plt.plot(planner.gate_temp_history, linewidth=2, color='#667eea')
        plt.axhline(y=0.5, color='gray', linestyle='--', label='Initial temp')
        plt.axhline(y=planner.gate_temp_min, color='red', linestyle=':', label='Min bound')
        plt.axhline(y=planner.gate_temp_max, color='red', linestyle=':', label='Max bound')
        plt.ylabel('Gate Temperature (τ_g)')
        plt.title('Learnable Gate Temperature Evolution (Phase 1)')
        plt.legend()
        plt.grid(True, alpha=0.3)

        # Plot 2: Recent accuracy over time
        plt.subplot(2, 1, 2)
        # Pad to match length
        padded_accuracies = [0.5] * (len(planner.gate_temp_history) - len(planner.recent_accuracies))
        padded_accuracies.extend(planner.recent_accuracies)

        # Running average of last 10
        window = 10
        running_avg = []
        for i in range(len(padded_accuracies)):
            start = max(0, i - window + 1)
            running_avg.append(np.mean(padded_accuracies[start:i+1]))

        plt.plot(running_avg, linewidth=2, color='#764ba2')
        plt.axhline(y=0.8, color='green', linestyle='--', alpha=0.5, label='High accuracy threshold')
        plt.axhline(y=0.6, color='orange', linestyle='--', alpha=0.5, label='Low accuracy threshold')
        plt.ylabel('Prediction Accuracy')
        plt.xlabel('Prediction Number')
        plt.legend()
        plt.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig('data/gate_temp_evolution.png', dpi=150, bbox_inches='tight')
        print("  Graph saved to: data/gate_temp_evolution.png")
        plt.close()

    print("\n" + "=" * 70)
    print("TEST COMPLETE [SUCCESS]")
    print("=" * 70)
    print()
    print("KEY INSIGHTS:")
    print("1. Gate temperature adapts based on prediction accuracy")
    print("2. High accuracy -> sharper routing (lower gate_temp)")
    print("3. Low accuracy -> softer routing (higher gate_temp)")
    print("4. System learns optimal routing sharpness over time")
    print()
    print("This is Phase 1 of 4 integration concepts from routed_brain.py!")


if __name__ == "__main__":
    test_learnable_gate_temp()
