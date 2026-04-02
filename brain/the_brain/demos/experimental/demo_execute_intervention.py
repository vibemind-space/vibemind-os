"""
Demonstrate the new 'execute' intervention with exact tool calls

This shows how the system provides executable tool sequences with parameters,
not just suggestions.
"""
import sys
import json
import numpy as np

# Add core to path
sys.path.insert(0, 'core')

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor

print("=" * 80)
print("EXECUTE INTERVENTION DEMO - Exact Tool Calls Generation")
print("=" * 80)
print()

print("NEW FEATURE: 'execute' intervention provides exact tool calls")
print("Previously: 4 interventions (suggest, retry, wait, terminate)")
print("NOW: 5 interventions (suggest, retry, wait, terminate, EXECUTE)")
print()

# Initialize brain components
print("[1/4] Initializing meta-cognitive system with 5 interventions...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
strategy_lib = StrategyLibrary()
brain_monitor = BrainActivityMonitor()

# Create conversation path planner
path_planner = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=strategy_lib,
    brain_monitor=brain_monitor
)

# Train on sessions
print("[2/4] Training on conversation logs...")
session_dir = "C:/Users/User/Desktop/sakana-desktop-assistant/data/logs/sessions"
path_planner.train_from_sessions(session_dir, limit=None)
print(f"       Trained on {meta_router.traces_processed} sessions")
print()

# Create hierarchical planner with execute capability
print("[3/4] Creating hierarchical planner with 'execute' capability...")
planner = HierarchicalPlanner(
    conversation_planner=path_planner,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],  # 5 interventions!
    seed=42
)
print("       Planner ready with 5-intervention routing")
print()

# Test tasks
test_tasks = [
    "Deploy Docker container urgently",
    "Push all changes to GitHub main branch",
    "Check memory and monitor system status"
]

print("[4/4] Making predictions with executable tool calls...")
print("=" * 80)
print()

for i, task in enumerate(test_tasks, 1):
    print(f"TASK {i}: '{task}'")
    print("-" * 80)

    # Make prediction
    result = planner.predict(task)

    # Extract decision
    decision = result.actionable_decision
    primary_action = decision.multi_target_decision['primary']['type']

    print(f"\nTask Type: {decision.task_features['task_type']}")
    print(f"Complexity: {decision.task_features['complexity']:.2f}")
    print(f"Urgency: {decision.task_features['urgency']:.2f}")
    print()

    print(f"PRIMARY INTERVENTION: {primary_action}")
    print(f"Weight: {decision.multi_target_decision['primary']['weight']:.1%}")
    print()

    # Show tool calls if execute
    if decision.executable_tool_calls:
        print("✅ EXECUTABLE TOOL CALLS GENERATED!")
        print()

        for tool_call in decision.executable_tool_calls:
            print(f"  Step {tool_call['step']}: {tool_call['tool']}")
            print(f"    Confidence: {tool_call['confidence']:.1%}")

            if tool_call['parameters']:
                print(f"    Parameters:")
                for key, value in tool_call['parameters'].items():
                    print(f"      - {key}: {value}")

            print(f"    Metadata:")
            print(f"      - Required: {tool_call['metadata']['required']}")
            print(f"      - Retry on error: {tool_call['metadata']['retry_on_error']}")
            print(f"      - Timeout: {tool_call['metadata']['timeout_seconds']}s")
            print()
    else:
        print(f"No executable tool calls (intervention is '{primary_action}', not 'execute')")
        print()

    print(f"ALTERNATIVES:")
    for alt in decision.multi_target_decision['alternatives'][:3]:
        print(f"  - {alt['type']:12s} {alt['weight']:.1%}")

    print()
    print("REASONING CHAIN:")
    for j, step in enumerate(decision.reasoning_chain[-5:], 1):  # Last 5 steps
        print(f"  {j}. {step}")

    print()
    print("=" * 80)
    print()

# Summary
print()
print("=" * 80)
print("SUMMARY: EXECUTE INTERVENTION")
print("=" * 80)
print()
print("WHAT 'execute' PROVIDES:")
print("  1. Exact tool names (from Layer 2 conversation graph)")
print("  2. Inferred parameters (based on task type and context)")
print("  3. Execution metadata (timeouts, retry logic, criticality)")
print("  4. Step-by-step sequence (ordered execution plan)")
print()
print("COMPARISON:")
print("  'suggest'   → Provides guidance (what to do)")
print("  'retry'     → Repeat previous action")
print("  'wait'      → Pause for more information")
print("  'terminate' → Stop/rollback for safety")
print("  'execute'   → Exact tool calls with parameters! ⭐ NEW")
print()
print("USE CASES:")
print("  - High confidence predictions (>70%)")
print("  - Routine tasks with known patterns")
print("  - When brain has seen similar tasks before")
print("  - Automated execution pipelines")
print()
print("=" * 80)
print("DEMO COMPLETE!")
print("=" * 80)
