"""
SEE THE BRAIN IN ACTION - Interactive Demo

This script shows real-time brain activity as it processes different tasks.
Watch how different modalities activate and compete!
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
import numpy as np
from core.task_feature_router import TaskFeatureRouter
from core.conversation_path_planner import ConversationPathPlanner
from core.conversation_graph import ConversationGraph
from core.hierarchical_planner import HierarchicalPlanner


def print_banner(text):
    """Print fancy banner"""
    width = 80
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width + "\n")


def visualize_brain_gates(gates, modalities):
    """Visualize brain gate distribution with bars"""
    print("\n  BRAIN MODALITY ACTIVATION:")
    print("  " + "-" * 76)

    # Sort by activation
    sorted_indices = np.argsort(gates)[::-1]

    for rank, idx in enumerate(sorted_indices, 1):
        modality = modalities[idx]
        value = gates[idx]

        # Color code by activation level
        if value > 0.3:
            indicator = ">>>"
        elif value > 0.15:
            indicator = ">>"
        elif value > 0.05:
            indicator = ">"
        else:
            indicator = ""

        # Bar visualization
        bar_length = int(value * 60)
        bar = "#" * bar_length

        print(f"  {rank:2d}. {modality:20s} {value:5.1%}  {bar} {indicator}")

    print("  " + "-" * 76)


def visualize_decision(decision):
    """Visualize multi-target decision"""
    print("\n  DECISION DISTRIBUTION:")
    print("  " + "-" * 76)

    # Primary
    primary = decision['primary']
    bar_length = int(primary['weight'] * 50)
    bar = "█" * bar_length
    print(f"  PRIMARY: {primary['type']:12s} {primary['weight']:5.1%}  {bar}")

    # Alternatives
    print(f"\n  ALTERNATIVES:")
    for alt in decision['alternatives']:
        bar_length = int(alt['weight'] * 50)
        bar = "▓" * bar_length
        print(f"    {alt['type']:12s} {alt['weight']:5.1%}  {bar}")

    print("  " + "-" * 76)


def show_reasoning_chain(chain):
    """Show reasoning chain"""
    print("\n  REASONING CHAIN:")
    print("  " + "-" * 76)
    for i, step in enumerate(chain, 1):
        # Wrap long lines
        if len(step) > 70:
            step = step[:67] + "..."
        print(f"  {i}. {step}")
    print("  " + "-" * 76)


def demo_task(planner, task_description):
    """Demo a single task through the brain"""
    print_banner(f"TASK: {task_description}")

    print("  Processing through 3-layer hierarchy...")
    print("  ⏳ Layer 1: Extracting features...")
    time.sleep(0.3)
    print("  ⏳ Layer 2: Planning sequence...")
    time.sleep(0.3)
    print("  ⏳ Layer 3: Routing decision...")
    time.sleep(0.3)

    # Make prediction
    start = time.time()
    prediction = planner.predict(task_description)
    elapsed = time.time() - start

    print(f"\n  ✓ Prediction complete in {elapsed*1000:.0f}ms\n")

    # Show task features
    features = prediction.layer1_routing.features
    print("  TASK ANALYSIS:")
    print("  " + "-" * 76)
    print(f"    Task Type:    {features.task_type}")
    print(f"    Complexity:   {features.complexity:.2f} / 1.0")
    print(f"    Urgency:      {features.urgency:.2f} / 1.0")
    print(f"    Mode:         {prediction.layer1_routing.processing_mode}")
    print("  " + "-" * 76)

    # Get brain gates
    brain_gates = None
    if hasattr(planner.layer2, 'brain_monitor') and planner.layer2.brain_monitor:
        if planner.layer2.brain_monitor.gate_history:
            brain_gates = list(planner.layer2.brain_monitor.gate_history)[-1]

    if brain_gates is None:
        brain_gates = prediction.layer1_routing.routing_weights

    # Visualize brain activation
    modalities = [
        'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
        'tool_trace', 'temporal_pattern', 'error_signal', 'success_signal'
    ]

    visualize_brain_gates(brain_gates, modalities)

    # Show dominant modalities
    print(f"\n  DOMINANT BRAIN AREAS:")
    print("  " + "-" * 76)
    for i, mod in enumerate(prediction.dominant_modalities[:3], 1):
        idx = modalities.index(mod) if mod in modalities else -1
        if idx >= 0:
            activation = brain_gates[idx]
            print(f"    {i}. {mod:20s} (activation: {activation:.1%})")
    print("  " + "-" * 76)

    # Visualize decision
    visualize_decision(prediction.actionable_decision.multi_target_decision)

    # Show confidence
    print(f"\n  CONFIDENCE: {prediction.confidence:.1%}")

    # Check CTM
    if prediction.ctm_task_id:
        print(f"\n  🧠 CTM DEEP REASONING: Started (task_id={prediction.ctm_task_id})")
        if prediction.ctm_insights:
            print(f"     Insights available!")
        else:
            print(f"     Still running in background...")

    # Show reasoning chain
    show_reasoning_chain(prediction.actionable_decision.reasoning_chain)

    print("\n  " + "=" * 76 + "\n")

    return prediction


def main():
    """Run interactive brain demo"""
    print_banner("🧠 TAHLAMUS BRAIN - LIVE DEMO")

    print("  Initializing cognitive system...")

    # Create planner - use existing session logs if available
    try:
        path_planner = ConversationPathPlanner(
            session_log_dir="data/logs/sessions"
        )
        print("  ✓ Loaded conversation graph from session logs")
    except Exception as e:
        print(f"  ! Using simplified planner (no session logs available)")
        # Create minimal graph
        from core.conversation_graph import ConversationGraph
        graph = ConversationGraph()
        path_planner = ConversationPathPlanner(
            conversation_graph=graph,
            session_log_dir=None
        )

    planner = HierarchicalPlanner(
        conversation_planner=path_planner,
        modalities=[
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal_pattern', 'error_signal', 'success_signal'
        ],
        intervention_types=['suggest', 'retry', 'wait', 'terminate'],
        enable_ctm_async=True,
        ctm_complexity_threshold=0.75,
        # Disable other systems for cleaner demo
        enable_memory=False,
        enable_predictive_coding=False,
        enable_attention=False,
        enable_meta_learning=False,
        enable_dream_mode=False,
        enable_neuromodulation=False,
        enable_temporal_memory=False,
        enable_active_inference=False,
        enable_compositional_reasoning=False,
        enable_tool_creation=False,
        enable_consciousness_metrics=False,
        enable_multi_brain_swarm=False,
        seed=42
    )

    print("  ✓ Brain initialized!\n")

    # Demo tasks with different characteristics
    tasks = [
        {
            'task': 'List files in current directory',
            'description': 'Simple, low-complexity task'
        },
        {
            'task': 'Deploy Docker container urgently for production',
            'description': 'High-urgency deployment task'
        },
        {
            'task': 'Debug failing authentication unit tests',
            'description': 'Moderate complexity debugging task'
        },
        {
            'task': 'Design distributed microservice architecture with auto-scaling and fault tolerance',
            'description': 'Very high complexity design task (triggers CTM!)'
        }
    ]

    for i, task_info in enumerate(tasks, 1):
        input(f"\n  Press Enter to see Task {i}/{len(tasks)}: {task_info['description']}...")
        demo_task(planner, task_info['task'])

        if i < len(tasks):
            print("\n" + "-" * 80)

    # Final statistics
    print_banner("SESSION STATISTICS")

    stats = planner.get_statistics()

    print(f"  Total Predictions:       {stats['total_predictions']}")
    print(f"  Avg Layer 1 Time:        {stats['average_layer_timing']['layer1']*1000:.1f}ms")
    print(f"  Avg Layer 2 Time:        {stats['average_layer_timing']['layer2']*1000:.1f}ms")
    print(f"  Avg Layer 3 Time:        {stats['average_layer_timing']['layer3']*1000:.1f}ms")

    if 'ctm_async_stats' in stats:
        ctm = stats['ctm_async_stats']
        print(f"\n  CTM Tasks Started:       {ctm['total_tasks_started']}")
        print(f"  CTM Tasks Completed:     {ctm['total_tasks_completed']}")
        print(f"  CTM Avg Time:            {ctm['average_reasoning_time']:.1f}s")

    print("\n  " + "=" * 76 + "\n")

    print_banner("✓ DEMO COMPLETE!")

    print("""
  You've just seen the brain in action!

  Key Observations:

  1. Different tasks activate different brain areas
     - Simple tasks: low threat, high tool_trace
     - Urgent tasks: high threat, high temporal_pattern
     - Debug tasks: high error_signal
     - Design tasks: high complexity → triggers CTM

  2. Brain gates always sum to 1.0 (competitive routing)

  3. Multi-target decisions provide alternatives
     - Not just one action, but a distribution
     - Enables graceful degradation

  4. CTM triggers automatically for complex tasks (>75% complexity)

  5. Complete reasoning chain shows decision process

  Want to see more?
  - Open http://localhost:5000 for the web dashboard
  - Run: python demos/test_ctm_async_integration.py
  - Run: python analyze_prediction_simple.py

""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Demo interrupted. Goodbye!")
    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback
        traceback.print_exc()
