"""
Test Script: Multi-Target Decision Routing (Phase 3)

Demonstrates weighted intervention decisions instead of single predictions.
Shows how uncertainty is quantified through routing weights.
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


def test_multi_target_routing():
    """Test multi-target decision routing with conversation path planner"""
    print("=" * 70)
    print("TESTING MULTI-TARGET DECISION ROUTING (Phase 3)")
    print("=" * 70)
    print()

    # Initialize components
    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,  # Phase 2
        seed=42
    )
    strategy_lib = StrategyLibrary(max_strategies_per_type=20)
    brain_monitor = BrainActivityMonitor(history_length=100)

    # Create path planner with all phases
    planner = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=strategy_lib,
        brain_monitor=brain_monitor,
        enable_adaptive_gating=True  # Phase 1
    )

    print("Path planner initialized with:")
    print("  - Phase 1: Learnable gate temperature")
    print("  - Phase 2: Per-modality prediction errors")
    print("  - Phase 3: Multi-target decision routing")
    print()

    # Train from sessions
    log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    planner.train_from_sessions(log_dir, limit=39)

    print("\n" + "=" * 70)
    print("TESTING PREDICTIONS WITH MULTI-TARGET DECISIONS")
    print("=" * 70)
    print()

    # Test different types of tasks
    test_tasks = [
        ("Check memory status", "memory"),
        ("Deploy with Docker", "docker"),
        ("git add and push", "github"),
        ("Search for files", "search")
    ]

    all_decisions = []

    for task_desc, expected_type in test_tasks:
        print(f"\nTASK: \"{task_desc}\"")
        print("=" * 70)

        prediction = planner.predict_optimal_path(task_desc)

        if prediction and prediction.multi_target_decision:
            mtd = prediction.multi_target_decision

            print(f"\n  Task Type: {prediction.task_type}")
            print(f"  Confidence: {prediction.confidence:.1%}")
            print(f"  Predicted Sequence: {' -> '.join(prediction.predicted_sequence)}")
            print()

            # Primary decision
            primary = mtd['primary']
            print(f"  PRIMARY DECISION ({primary['weight']:.1%}):")
            print(f"    Type:       {primary['type']}")
            print(f"    Confidence: {primary['confidence']:.1%}")
            print(f"    Reasoning:  {primary['reasoning']}")
            print()

            # Alternatives
            print("  ALTERNATIVE DECISIONS:")
            for alt in mtd['alternatives']:
                bar = '#' * int(alt['weight'] * 50)
                print(f"    {alt['type']:12s} {alt['weight']:.1%} {bar}")

            print()
            print(f"  Dominant Modalities: {', '.join(prediction.dominant_modalities)}")

            # Store for analysis
            all_decisions.append({
                'task': task_desc,
                'primary': primary['type'],
                'weight': primary['weight'],
                'alternatives': {alt['type']: alt['weight'] for alt in mtd['alternatives']}
            })

        else:
            print("  (No multi-target decision available)")

        print()
        print("-" * 70)

    # Analyze decision patterns
    print("\n" + "=" * 70)
    print("DECISION PATTERN ANALYSIS")
    print("=" * 70)
    print()

    if all_decisions:
        # Count intervention types
        intervention_counts = {}
        for dec in all_decisions:
            itype = dec['primary']
            intervention_counts[itype] = intervention_counts.get(itype, 0) + 1

        print("Primary Intervention Distribution:")
        total = len(all_decisions)
        for itype, count in sorted(intervention_counts.items(), key=lambda x: x[1], reverse=True):
            pct = count / total
            bar = '#' * int(pct * 30)
            print(f"  {itype:12s} {count}/{total} ({pct:.0%}) {bar}")

        print()

        # Average weights
        print("Average Decision Weights:")
        all_weights = {}
        for dec in all_decisions:
            all_weights[dec['primary']] = all_weights.get(dec['primary'], [])
            all_weights[dec['primary']].append(dec['weight'])

            for alt_type, alt_weight in dec['alternatives'].items():
                all_weights[alt_type] = all_weights.get(alt_type, [])
                all_weights[alt_type].append(alt_weight)

        for itype in sorted(all_weights.keys()):
            avg_weight = np.mean(all_weights[itype])
            print(f"  {itype:12s} avg: {avg_weight:.1%}")

    # Visualize multi-target routing
    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATION")
    print("=" * 70)
    print()

    if all_decisions and len(all_decisions) >= 3:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # Plot 1: Stacked bar chart of weighted decisions
        ax1.set_title('Multi-Target Decision Routing (Phase 3)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Task')
        ax1.set_ylabel('Decision Weight')

        task_labels = [dec['task'][:20] for dec in all_decisions]
        intervention_types = ['suggest', 'retry', 'wait', 'terminate']
        colors = ['#667eea', '#764ba2', '#f093fb', '#fa709a']

        # Prepare data for stacked bars
        weights_by_type = {itype: [] for itype in intervention_types}

        for dec in all_decisions:
            # Primary weight
            for itype in intervention_types:
                if dec['primary'] == itype:
                    weights_by_type[itype].append(dec['weight'])
                elif itype in dec['alternatives']:
                    weights_by_type[itype].append(dec['alternatives'][itype])
                else:
                    weights_by_type[itype].append(0.0)

        # Create stacked bars
        bottom = np.zeros(len(all_decisions))
        for itype, color in zip(intervention_types, colors):
            weights = weights_by_type[itype]
            ax1.bar(range(len(all_decisions)), weights, bottom=bottom,
                   label=itype, color=color, alpha=0.8)
            bottom += weights

        ax1.set_xticks(range(len(all_decisions)))
        ax1.set_xticklabels(task_labels, rotation=45, ha='right')
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3, axis='y')

        # Plot 2: Average intervention weights (pie chart)
        ax2.set_title('Average Intervention Distribution', fontsize=14, fontweight='bold')

        avg_intervention_weights = []
        for itype in intervention_types:
            avg_weight = np.mean(weights_by_type[itype]) if weights_by_type[itype] else 0
            avg_intervention_weights.append(avg_weight)

        # Normalize to sum to 1
        total_weight = sum(avg_intervention_weights)
        if total_weight > 0:
            avg_intervention_weights = [w / total_weight for w in avg_intervention_weights]

        ax2.pie(avg_intervention_weights, labels=intervention_types, colors=colors,
               autopct='%1.1f%%', startangle=90)

        plt.tight_layout()
        plt.savefig('data/multi_target_routing.png', dpi=150, bbox_inches='tight')
        print("  Graph saved to: data/multi_target_routing.png")

    print("\n" + "=" * 70)
    print("TEST COMPLETE [SUCCESS]")
    print("=" * 70)
    print()
    print("KEY INSIGHTS:")
    print("1. Each prediction has weighted intervention decisions")
    print("2. Not just 'suggest' but '40% suggest, 30% retry, 20% wait, 10% terminate'")
    print("3. Uncertainty is quantified through weight distribution")
    print("4. Multiple strategies can be executed with priorities")
    print("5. Dominant modalities influence reasoning")
    print()
    print("This is Phase 3 of 4 integration concepts from routed_brain.py!")


if __name__ == "__main__":
    test_multi_target_routing()
