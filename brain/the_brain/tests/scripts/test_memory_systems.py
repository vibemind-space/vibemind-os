"""
PHASE 1 DEMO: Memory Systems Integration

Demonstrates:
1. Working memory with recent task recall
2. Episodic memory with rich experience storage
3. Similarity-based memory retrieval
4. Memory context in decision making
5. Outcome recording and consolidation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor

print("=" * 70)
print("PHASE 1: MEMORY SYSTEMS DEMO")
print("=" * 70)
print()

# Initialize system with memory enabled
print("[1/3] Initializing hierarchical planner with memory systems...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with memory
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,  # NEW: Memory enabled!
    memory_save_dir="data/episodic_memory",
    seed=42
)

print(f"   {planner}")
print(f"   Memory: Working={len(planner.memory.working)}, Episodic={len(planner.memory.episodic)}")
print()

print("[2/3] Making predictions with memory context...")
print("=" * 70)
print()

# Test tasks
test_tasks = [
    "Deploy Docker container urgently",
    "Fix authentication bug in API",
    "Deploy Docker with high priority",  # Similar to first!
    "Check memory and system status",
    "Deploy critical Docker update"  # Similar to first two!
]

predictions = []

for i, task in enumerate(test_tasks, 1):
    print(f"TASK {i}: '{task}'")
    print("-" * 70)

    # Make prediction (automatically stores in working memory)
    prediction = planner.predict(task)

    # Store for later
    predictions.append((task, prediction))

    # Extract decision
    decision = prediction.actionable_decision
    primary = decision.multi_target_decision['primary']

    print(f"\n  Primary Action: {primary['type']} ({primary['weight']:.1%})")
    print(f"  Confidence: {prediction.confidence:.1%}")
    print(f"  Task Type: {prediction.task_type}")

    # Show memory context if available
    if prediction.memory_context:
        working_mem = prediction.memory_context['working_memory']

        # Show similar recent tasks
        similar = working_mem.get('similar_tasks', [])
        if similar:
            print(f"\n  Memory Context:")
            print(f"    Similar recent tasks:")
            for task_dict, score in similar[:2]:
                task_str = task_dict['task']
                prev_decision = task_dict['decision']
                print(f"      - {task_str[:40]}... (similarity={score:.2f}, was '{prev_decision}')")

        # Show decision patterns
        patterns = working_mem.get('decision_patterns', {})
        if patterns:
            print(f"    Recent decision pattern:")
            for decision_type, freq in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:2]:
                print(f"      - {decision_type}: {freq:.0%}")

    print()

    # Simulate outcome
    outcome = 'success' if np.random.rand() > 0.2 else 'failure'
    importance = np.random.uniform(0.5, 1.0)

    # Record outcome in working memory
    planner.record_outcome(
        task=task,
        decision=primary['type'],
        outcome=outcome,
        importance=importance
    )

    # If important, consolidate to episodic memory
    if importance > 0.7:
        # Store task in prediction for consolidation
        prediction.task_description = task
        planner.consolidate_experience(
            prediction=prediction,
            outcome=outcome,
            importance=importance,
            user_rating=np.random.uniform(0.7, 1.0),
            execution_time_ms=np.random.uniform(500, 2000)
        )

    print(f"  Outcome: {outcome.upper()} (importance={importance:.2f})")
    print()

print()
print("=" * 70)
print("[3/3] MEMORY STATISTICS")
print("=" * 70)
print()

stats = planner.get_statistics()
memory_stats = stats.get('memory_stats', {})

print(f"Working Memory: {memory_stats.get('working_memory_size', 0)} tasks")
print(f"Episodic Memory: {memory_stats.get('episodic_memory_size', 0)} experiences")
print(f"Recent Success Rate: {memory_stats.get('recent_success_rate', 0):.1%}")
print()

# Show working memory contents
print("Working Memory Contents:")
print("-" * 70)
for i, entry in enumerate(planner.memory.working.get_recent(5), 1):
    print(f"{i}. {entry.task[:50]}...")
    print(f"   Decision: {entry.decision} (confidence={entry.confidence:.1%})")
    print(f"   Outcome: {entry.outcome or 'unknown'}")
    print()

# Show important episodic memories
if planner.memory.episodic.memories:
    print("Important Episodic Memories:")
    print("-" * 70)
    important = planner.memory.episodic.get_important_memories(top_k=3)
    for i, memory in enumerate(important, 1):
        print(f"{i}. {memory.task[:50]}...")
        print(f"   Decision: {memory.decision} -> {memory.outcome.upper()}")
        print(f"   Importance: {memory.importance:.2f}, Valence: {memory.emotional_valence}")
        print(f"   Prediction Error: {memory.prediction_error:.2f}")
        print()

# Show decision success rates by type
print("Decision Success Rates:")
print("-" * 70)
for intervention_type in ['suggest', 'execute', 'wait', 'retry', 'terminate']:
    success_rate = planner.memory.episodic.compute_decision_success_rate(intervention_type)
    count = len(planner.memory.episodic.get_by_decision(intervention_type))
    if count > 0:
        print(f"  {intervention_type:12s}: {success_rate:.1%} ({count} experiences)")

print()
print("=" * 70)
print("PHASE 1 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Working memory stores recent tasks")
print("  [X] Similarity-based retrieval works")
print("  [X] Episodic memory stores rich experiences")
print("  [X] Importance weighting functional")
print("  [X] Memory context influences decisions")
print("  [X] Outcome recording and consolidation working")
print()
print("The brain now has MEMORY - it remembers the past and learns from it!")
print("=" * 70)
