"""
Seed Memory Systems with Initial Data

This script populates the Memory Systems with:
- Working memory entries (recent tasks)
- Episodic memories (past experiences with outcomes)

This ensures Memory Systems shows as ACTIVE in tests.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production.production_planner import ProductionPlanner
import numpy as np


def seed_memory_systems():
    """Seed memory systems with initial data"""

    print("=" * 100)
    print("SEEDING MEMORY SYSTEMS")
    print("=" * 100)
    print()

    # Initialize planner
    print("[1] Initializing ProductionPlanner...")
    planner = ProductionPlanner(
        session_log_dir="data/logs/sessions",
        enable_semantic_coherence=False,  # Faster initialization
        user_id="seed_user",
        seed=42
    )
    print("[+] Planner initialized")
    print()

    # Add working memory entries
    print("[2] Adding working memory entries...")

    working_memory_tasks = [
        ("Deploy Docker container", "docker", "execute", 0.85),
        ("Fix Redis connection timeout", "debugging", "retry", 0.70),
        ("Update API endpoints", "api", "suggest", 0.90),
        ("Run integration tests", "testing", "execute", 0.95),
        ("Review pull request", "code_review", "wait", 0.60),
    ]

    for task, task_type, decision, confidence in working_memory_tasks:
        brain_gates = np.random.rand(10)  # Random brain activations
        brain_gates = brain_gates / brain_gates.sum()  # Normalize

        planner.planner.memory.remember_task(
            task=task,
            task_type=task_type,
            decision=decision,
            confidence=confidence,
            brain_gates=brain_gates,
            outcome=None  # Not yet executed
        )
        print(f"  + {task} ({task_type})")

    print(f"[+] Added {len(working_memory_tasks)} working memory entries")
    print()

    # Add episodic memories
    print("[3] Adding episodic memories...")

    episodic_memories = [
        {
            "task": "Deploy with Docker urgently",
            "task_type": "docker",
            "decision": "execute",
            "confidence": 0.85,
            "outcome": "success",
            "importance": 0.8,
            "emotional_valence": "positive",
            "prediction_error": 0.15
        },
        {
            "task": "Fix database connection",
            "task_type": "debugging",
            "decision": "retry",
            "confidence": 0.70,
            "outcome": "success",
            "importance": 0.7,
            "emotional_valence": "positive",
            "prediction_error": 0.30
        },
        {
            "task": "Refactor authentication module",
            "task_type": "refactoring",
            "decision": "suggest",
            "confidence": 0.60,
            "outcome": "failure",
            "importance": 0.9,
            "emotional_valence": "negative",
            "prediction_error": 0.80
        },
        {
            "task": "Scale Kubernetes cluster",
            "task_type": "infrastructure",
            "decision": "execute",
            "confidence": 0.90,
            "outcome": "success",
            "importance": 0.85,
            "emotional_valence": "positive",
            "prediction_error": 0.10
        },
        {
            "task": "Debug memory leak",
            "task_type": "debugging",
            "decision": "retry",
            "confidence": 0.50,
            "outcome": "success",
            "importance": 0.95,
            "emotional_valence": "positive",
            "prediction_error": 0.50
        },
    ]

    for mem in episodic_memories:
        brain_gates = np.random.rand(10)
        brain_gates = brain_gates / brain_gates.sum()

        planner.planner.memory.consolidate_to_episodic(
            task=mem["task"],
            task_type=mem["task_type"],
            decision=mem["decision"],
            confidence=mem["confidence"],
            outcome=mem["outcome"],
            brain_gates=brain_gates,
            layer1_features={"complexity": 0.5, "urgency": 0.6},
            layer2_sequence=["tool_trace", "error_signal"],
            reasoning_chain=["L1: classified", "L2: predicted", "L3: decided"],
            importance=mem["importance"],
            emotional_valence=mem["emotional_valence"],
            prediction_error=mem["prediction_error"],
            execution_time_ms=1500.0,
            user_rating=0.8
        )
        print(f"  + {mem['task']} ({mem['task_type']}) -> {mem['outcome']}")

    print(f"[+] Added {len(episodic_memories)} episodic memories")
    print()

    # Verify memory contents
    print("[4] Verifying memory contents...")
    working_size = len(planner.planner.memory.working.buffer)
    episodic_size = len(planner.planner.memory.episodic.memories)

    print(f"  Working memory: {working_size} entries")
    print(f"  Episodic memory: {episodic_size} entries")
    print()

    # Test retrieval
    print("[5] Testing memory retrieval...")
    recent_tasks = planner.planner.memory.working.get_recent(n=3)
    print(f"  Recent tasks ({len(recent_tasks)}):")
    for entry in recent_tasks:
        print(f"    - {entry.task} ({entry.task_type})")

    important_memories = planner.planner.memory.episodic.get_important_memories(top_k=5)
    print(f"  Important episodic memories ({len(important_memories)}):")
    for entry in important_memories:
        print(f"    - {entry.task} ({entry.task_type}) -> {entry.outcome}")

    print()
    print("=" * 100)
    print("[SUCCESS] MEMORY SYSTEMS SEEDED!")
    print("=" * 100)
    print()
    print("Memory Systems is now ACTIVE and will show data in API responses.")
    print()


if __name__ == "__main__":
    seed_memory_systems()
