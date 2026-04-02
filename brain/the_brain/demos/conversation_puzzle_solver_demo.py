"""
Conversation Puzzle Solver - Complete Demo

Demonstrates the full vision of treating agent conversations as puzzles
that the brain can solve by predicting optimal command sequences.

The brain:
1. Learns from all 39 past agent sessions
2. Builds conversation graph (states + transitions)
3. Given a task (e.g., "git add and push"), finds optimal path
4. Predicts command sequence, expected duration, and errors

This is like solving a Klotski puzzle, but for agent conversations!
"""

import numpy as np
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.conversation_path_planner import ConversationPathPlanner, PathPrediction
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor


def print_section(title: str):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(title.center(80))
    print("=" * 80 + "\n")


def demonstrate_conversation_puzzle_solving():
    """
    Main demonstration of conversation puzzle solving
    """
    print_section("CONVERSATION PUZZLE SOLVER")

    print("Conversations as Puzzles:")
    print("  - Puzzle = Sequence of agent actions leading to goal")
    print("  - States = Conversation states (tools used, errors, context)")
    print("  - Moves = Tool calls, clarifications, etc.")
    print("  - Optimal Solution = Shortest path with fewest errors")
    print()
    print("The Brain learns patterns from past sessions and predicts")
    print("optimal command sequences for new tasks.")

    # === INITIALIZATION ===
    print_section("STEP 1: INITIALIZE BRAIN COMPONENTS")

    print("Initializing meta-cognitive system...")
    meta_router = MetaRouter(enable_hippocampus=True, seed=42)
    print("[OK] MetaRouter initialized")

    strategy_lib = StrategyLibrary(max_strategies_per_type=20)
    print("[OK] StrategyLibrary initialized")

    brain_monitor = BrainActivityMonitor(history_length=100)
    print("[OK] BrainActivityMonitor initialized")

    planner = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=strategy_lib,
        brain_monitor=brain_monitor
    )
    print("[OK] ConversationPathPlanner initialized")

    # === TRAINING ===
    print_section("STEP 2: TRAIN FROM ALL PAST SESSIONS")

    log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    print(f"Training from: {log_dir}")
    print("Loading all 39 session logs...")
    print()

    planner.train_from_sessions(log_dir, limit=None)  # All sessions

    # Show what was learned
    stats = planner.get_statistics()
    graph_stats = stats['graph_stats']
    strategy_stats = stats['strategy_stats']

    print("\n[LEARNING RESULTS]")
    print(f"  Conversation states discovered: {graph_stats['total_states']}")
    print(f"  State transitions mapped: {graph_stats['total_transitions']}")
    print(f"  Task types identified: {graph_stats['task_types']}")
    print(f"  Strategies learned: {strategy_stats['total_strategies']}")
    print(f"  Average success rate: {graph_stats['avg_success_rate']:.1%}")

    print("\n[TASK DISTRIBUTION]")
    for task_type, count in sorted(graph_stats['task_distribution'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {task_type}: {count} sessions")

    # === PATH PREDICTION ===
    print_section("STEP 3: PREDICT OPTIMAL PATHS FOR NEW TASKS")

    # Test tasks
    test_tasks = [
        ("I want to add all files and push to GitHub", "github"),
        ("Check memory usage and status", "memory"),
        ("Search for error in the logs", "search"),
        ("Get desktop information", "desktop"),
        ("Use playwright to scrape a website", "playwright")
    ]

    successful_predictions = []

    for task_description, expected_type in test_tasks:
        print(f"\n[TASK] \"{task_description}\"")
        print("-" * 80)

        prediction = planner.predict_optimal_path(task_description)

        if prediction:
            successful_predictions.append(prediction)

            print(f"\nPredicted Path:")
            for i, tool in enumerate(prediction.predicted_sequence, 1):
                print(f"  {i}. {tool}")

            print(f"\nExpected Outcome:")
            print(f"  Duration: ~{prediction.expected_duration:.1f}s")
            print(f"  Errors: ~{prediction.expected_errors}")
            print(f"  Success Probability: {prediction.success_probability:.1%}")
            print(f"  Confidence: {prediction.confidence:.1%}")

            print(f"\nEvidence:")
            print(f"  Based on {prediction.similar_sessions} similar past sessions")
            print(f"  Dominant brain areas: {', '.join(prediction.dominant_modalities)}")

            if prediction.alternative_paths:
                print(f"\nAlternative paths available: {len(prediction.alternative_paths)}")

        else:
            print(f"[NO PREDICTION] Not enough data for task type: {expected_type}")

        print()

    # === DETAILED ANALYSIS ===
    if successful_predictions:
        print_section("STEP 4: DETAILED ANALYSIS OF BEST PREDICTION")

        # Sort by confidence
        successful_predictions.sort(key=lambda p: p.confidence, reverse=True)
        best = successful_predictions[0]

        print(planner.visualize_prediction(best))

    # === BRAIN STATE ===
    print_section("STEP 5: BRAIN STATE")

    brain_state = meta_router.get_state()

    print("Meta-Router State:")
    print(f"  Traces processed: {brain_state['traces_processed']}")
    print(f"  Success rate: {brain_state['successes_encoded'] / brain_state['traces_processed']:.1%}")
    print(f"  Failures encoded: {brain_state['failures_encoded']}")
    print(f"  Memory efficiency: {brain_state['failures_encoded'] / brain_state['traces_processed']:.1%}")
    print()

    hc_state = brain_state['thalamo_hippocampal_state']['hippocampal']
    print("Hippocampal Memory:")
    print(f"  Episodic memories: {hc_state['num_memories']}")
    print(f"  Memory ages: {hc_state.get('memory_ages', [])} timesteps")
    print()

    # Show activation
    print("Current Activation Summary:")
    activation_summary = brain_monitor.get_activation_summary()
    for module, level in activation_summary['current_activation'].items():
        bar_length = int(level * 20)
        bar = "#" * bar_length + "-" * (20 - bar_length)
        print(f"  {module:20s} [{bar}] {level:.2f}")

    # === GRAPH VISUALIZATION ===
    print_section("STEP 6: CONVERSATION GRAPH SAMPLES")

    # Show graph for most common task types
    top_tasks = sorted(
        graph_stats['task_distribution'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]

    for task_type, count in top_tasks:
        print(f"\n[{task_type.upper()}] ({count} sessions)")
        print("-" * 80)
        viz = planner.graph.visualize_task_graph(task_type, max_states=5)
        print(viz)

    # === SUMMARY ===
    print_section("SUMMARY")

    print("[WHAT WE BUILT]")
    print("  1. ConversationGraph: Represents all sessions as state space")
    print("  2. PathPlanner: Searches graph for optimal command sequences")
    print("  3. Meta-Router: Thalamic routing + hippocampal memory")
    print("  4. StrategyLibrary: Stores proven successful patterns")
    print()

    print("[HOW IT WORKS]")
    print("  INPUT: Task description ('git add and push')")
    print("  PROCESS:")
    print("    1. Infer task type from keywords")
    print("    2. Search graph for similar past states")
    print("    3. Find optimal path using A* search")
    print("    4. Estimate outcome from statistics")
    print("  OUTPUT: Command sequence + expected duration/errors/success")
    print()

    print("[KEY INSIGHT]")
    print("  Treating conversations as puzzles enables the brain to:")
    print("  - Learn from ALL past sessions (not just recent)")
    print("  - Predict optimal paths BEFORE execution")
    print("  - Estimate expected outcomes based on evidence")
    print("  - Provide alternative paths if primary fails")
    print()

    print("[NEXT STEPS]")
    print("  - Improve path finding for tasks with few examples")
    print("  - Add real-time execution with intervention")
    print("  - Integrate with actual agent system")
    print("  - Build web UI for path visualization")

    print()
    print("=" * 80)
    print("DEMONSTRATION COMPLETE!".center(80))
    print("=" * 80)


if __name__ == "__main__":
    try:
        demonstrate_conversation_puzzle_solving()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
