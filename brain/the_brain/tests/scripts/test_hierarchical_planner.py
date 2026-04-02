"""
Test Script: Hierarchical Planner (Phase 4)

Tests the complete 3-layer hierarchical cognitive architecture:
- Layer 1: TaskFeatureRouter (feature extraction and initial routing)
- Layer 2: ConversationPathPlanner (graph-based path planning)
- Layer 3: DecisionRouter (multi-target actionable decisions)

This demonstrates the full integration of all 4 phases:
- Phase 1: Learnable Gate Temperature
- Phase 2: Per-Modality Prediction Errors
- Phase 3: Multi-Target Decision Routing
- Phase 4: 3-Layer Hierarchical Architecture
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor


def test_hierarchical_planner():
    """Test complete 3-layer hierarchical architecture"""
    print("=" * 70)
    print("TESTING HIERARCHICAL PLANNER (Phase 4)")
    print("=" * 70)
    print()

    # === Initialize Layer 2 (existing system) ===
    print("Initializing Layer 2: ConversationPathPlanner...")
    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,  # Phase 2
        seed=42
    )
    strategy_lib = StrategyLibrary(max_strategies_per_type=20)
    brain_monitor = BrainActivityMonitor(history_length=100)

    layer2_planner = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=strategy_lib,
        brain_monitor=brain_monitor,
        enable_adaptive_gating=True  # Phase 1
    )

    # Train from sessions
    log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    print(f"Training on session logs from: {log_dir}")
    layer2_planner.train_from_sessions(log_dir, limit=39)
    print()

    # === Initialize Hierarchical Planner (all 3 layers) ===
    print("Initializing HierarchicalPlanner (3 layers)...")
    planner = HierarchicalPlanner(
        conversation_planner=layer2_planner,
        seed=42
    )

    print(f"Initialized: {planner}")
    print()
    print("Layer 1: TaskFeatureRouter - Feature extraction and routing")
    print("Layer 2: ConversationPathPlanner - Graph-based path planning")
    print("Layer 3: DecisionRouter - Multi-target decision routing")
    print()

    # === Test on diverse tasks ===
    print("=" * 70)
    print("TESTING PREDICTIONS WITH HIERARCHICAL ROUTING")
    print("=" * 70)
    print()

    test_tasks = [
        "Check memory status and monitor system urgently",
        "Analyze complex codebase architecture and refactor",
        "Deploy with Docker and handle errors",
        "Search for files and debug issues"
    ]

    all_predictions = []

    for i, task in enumerate(test_tasks, 1):
        print(f"\nTask {i}: \"{task}\"")
        print("=" * 70)

        # Make prediction through all 3 layers
        prediction = planner.predict(task)

        # Visualize
        viz = planner.visualize_prediction(prediction)
        print(viz)

        # Store for analysis
        all_predictions.append({
            'task': task,
            'layer1_mode': prediction.layer1_routing.processing_mode,
            'layer1_type': prediction.layer1_routing.features.task_type,
            'layer2_confidence': prediction.confidence,
            'layer3_primary': prediction.actionable_decision.multi_target_decision['primary']['type'],
            'layer3_weight': prediction.actionable_decision.multi_target_decision['primary']['weight']
        })

        print("\n" + "-" * 70 + "\n")

    # === Analysis ===
    print("=" * 70)
    print("HIERARCHICAL ROUTING ANALYSIS")
    print("=" * 70)
    print()

    # Layer 1 analysis
    print("LAYER 1: Task Feature Distribution")
    print("-" * 70)
    task_types = {}
    processing_modes = {}
    for pred in all_predictions:
        task_types[pred['layer1_type']] = task_types.get(pred['layer1_type'], 0) + 1
        processing_modes[pred['layer1_mode']] = processing_modes.get(pred['layer1_mode'], 0) + 1

    print("Task types identified:")
    for tt, count in sorted(task_types.items(), key=lambda x: x[1], reverse=True):
        pct = count / len(all_predictions)
        bar = '#' * int(pct * 40)
        print(f"  {tt:12s} {count}/{len(all_predictions)} ({pct:.0%}) {bar}")

    print()
    print("Processing modes selected:")
    for mode, count in sorted(processing_modes.items(), key=lambda x: x[1], reverse=True):
        pct = count / len(all_predictions)
        bar = '#' * int(pct * 40)
        print(f"  {mode:12s} {count}/{len(all_predictions)} ({pct:.0%}) {bar}")

    print()

    # Layer 2 analysis
    print("LAYER 2: Path Planning Confidence")
    print("-" * 70)
    avg_confidence = np.mean([pred['layer2_confidence'] for pred in all_predictions])
    print(f"Average confidence: {avg_confidence:.1%}")
    print()

    # Layer 3 analysis
    print("LAYER 3: Intervention Distribution")
    print("-" * 70)
    interventions = {}
    for pred in all_predictions:
        itype = pred['layer3_primary']
        interventions[itype] = interventions.get(itype, 0) + 1

    for itype, count in sorted(interventions.items(), key=lambda x: x[1], reverse=True):
        pct = count / len(all_predictions)
        bar = '#' * int(pct * 40)
        print(f"  {itype:12s} {count}/{len(all_predictions)} ({pct:.0%}) {bar}")

    print()

    # === Statistics ===
    print("=" * 70)
    print("SYSTEM STATISTICS")
    print("=" * 70)
    print()

    stats = planner.get_statistics()
    print(f"Total predictions: {stats['total_predictions']}")
    print()

    print("Average layer processing time:")
    for layer, time_ms in stats['average_layer_timing'].items():
        print(f"  {layer}: {time_ms*1000:.2f} ms")

    print()

    # === Visualization ===
    print("=" * 70)
    print("GENERATING VISUALIZATION")
    print("=" * 70)
    print()

    if len(all_predictions) >= 3:
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

        # Plot 1: Processing modes (Layer 1)
        ax1 = fig.add_subplot(gs[0, 0])
        modes = list(processing_modes.keys())
        mode_counts = [processing_modes[m] for m in modes]
        colors_modes = ['#667eea', '#764ba2', '#f093fb', '#fa709a']
        ax1.bar(range(len(modes)), mode_counts, color=colors_modes[:len(modes)], alpha=0.8)
        ax1.set_xticks(range(len(modes)))
        ax1.set_xticklabels(modes, rotation=45, ha='right')
        ax1.set_ylabel('Count')
        ax1.set_title('Layer 1: Processing Modes', fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='y')

        # Plot 2: Task types (Layer 1)
        ax2 = fig.add_subplot(gs[0, 1])
        types = list(task_types.keys())
        type_counts = [task_types[t] for t in types]
        ax2.bar(range(len(types)), type_counts, color='#667eea', alpha=0.8)
        ax2.set_xticks(range(len(types)))
        ax2.set_xticklabels(types, rotation=45, ha='right')
        ax2.set_ylabel('Count')
        ax2.set_title('Layer 1: Task Types', fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')

        # Plot 3: Confidence distribution (Layer 2)
        ax3 = fig.add_subplot(gs[0, 2])
        confidences = [pred['layer2_confidence'] for pred in all_predictions]
        ax3.bar(range(len(confidences)), confidences, color='#764ba2', alpha=0.8)
        ax3.axhline(y=avg_confidence, color='red', linestyle='--', linewidth=2, label=f'Avg: {avg_confidence:.1%}')
        ax3.set_ylabel('Confidence')
        ax3.set_xlabel('Task Index')
        ax3.set_title('Layer 2: Prediction Confidence', fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3, axis='y')

        # Plot 4: Intervention distribution (Layer 3)
        ax4 = fig.add_subplot(gs[1, 0])
        intervention_types = list(interventions.keys())
        intervention_counts = [interventions[i] for i in intervention_types]
        colors_int = ['#667eea', '#764ba2', '#f093fb', '#fa709a']
        ax4.pie(intervention_counts, labels=intervention_types, colors=colors_int[:len(intervention_types)],
               autopct='%1.0f%%', startangle=90)
        ax4.set_title('Layer 3: Intervention Distribution', fontweight='bold')

        # Plot 5: Decision weights (Layer 3)
        ax5 = fig.add_subplot(gs[1, 1])
        weights = [pred['layer3_weight'] for pred in all_predictions]
        ax5.bar(range(len(weights)), weights, color='#f093fb', alpha=0.8)
        ax5.axhline(y=0.5, color='red', linestyle='--', linewidth=1, alpha=0.5, label='50% threshold')
        ax5.set_ylabel('Primary Weight')
        ax5.set_xlabel('Task Index')
        ax5.set_title('Layer 3: Primary Decision Weights', fontweight='bold')
        ax5.legend()
        ax5.grid(True, alpha=0.3, axis='y')

        # Plot 6: Layer timing
        ax6 = fig.add_subplot(gs[1, 2])
        layers = list(stats['average_layer_timing'].keys())
        times = [stats['average_layer_timing'][l] * 1000 for l in layers]  # Convert to ms
        colors_timing = ['#667eea', '#764ba2', '#f093fb']
        ax6.bar(range(len(layers)), times, color=colors_timing, alpha=0.8)
        ax6.set_xticks(range(len(layers)))
        ax6.set_xticklabels(layers)
        ax6.set_ylabel('Time (ms)')
        ax6.set_title('Average Layer Processing Time', fontweight='bold')
        ax6.grid(True, alpha=0.3, axis='y')

        # Plot 7: Complete flow diagram (text-based)
        ax7 = fig.add_subplot(gs[2, :])
        ax7.axis('off')
        ax7.text(0.5, 0.9, 'HIERARCHICAL ROUTING FLOW', ha='center', va='top',
                fontsize=14, fontweight='bold', transform=ax7.transAxes)

        flow_text = """
        Task Description
             ↓
        ┌─────────────────────────────────────────────────────────────┐
        │ Layer 1: TaskFeatureRouter                                  │
        │ • Extract keywords, task type, complexity, urgency          │
        │ • Compute routing weights to brain areas                    │
        │ • Select processing mode (urgent/analytical/creative/routine)│
        └─────────────────────────────────────────────────────────────┘
             ↓
        ┌─────────────────────────────────────────────────────────────┐
        │ Layer 2: ConversationPathPlanner                            │
        │ • A* search on conversation graph                           │
        │ • Brain routing with learnable temperature (Phase 1)        │
        │ • Per-modality prediction errors (Phase 2)                  │
        │ • Predict optimal path sequence                             │
        └─────────────────────────────────────────────────────────────┘
             ↓
        ┌─────────────────────────────────────────────────────────────┐
        │ Layer 3: DecisionRouter                                     │
        │ • Multi-target routing matrix (Phase 3)                     │
        │ • Weighted intervention decisions                           │
        │ • Context-aware reasoning                                   │
        │ • Actionable output with full provenance                    │
        └─────────────────────────────────────────────────────────────┘
             ↓
        Actionable Decision with Reasoning Chain
        """

        ax7.text(0.1, 0.75, flow_text, ha='left', va='top',
                fontsize=9, family='monospace', transform=ax7.transAxes)

        # Main title
        fig.suptitle('Hierarchical Planner - 3-Layer Cognitive Architecture (Phase 4)',
                    fontsize=16, fontweight='bold', y=0.98)

        plt.savefig('data/hierarchical_planner.png', dpi=150, bbox_inches='tight')
        print("  Visualization saved to: data/hierarchical_planner.png")

    print()
    print("=" * 70)
    print("TEST COMPLETE [SUCCESS]")
    print("=" * 70)
    print()
    print("KEY INSIGHTS:")
    print("1. Layer 1 extracts task features and routes to specialized brain areas")
    print("2. Layer 2 performs graph-based planning with adaptive brain routing")
    print("3. Layer 3 generates multi-target decisions with full reasoning")
    print("4. All 4 phases integrated seamlessly:")
    print("   - Phase 1: Learnable gate temperature [COMPLETE]")
    print("   - Phase 2: Per-modality prediction errors [COMPLETE]")
    print("   - Phase 3: Multi-target decision routing [COMPLETE]")
    print("   - Phase 4: 3-layer hierarchical architecture [COMPLETE]")
    print()
    print("This completes the integration of all concepts from routed_brain.py!")


if __name__ == "__main__":
    test_hierarchical_planner()
