"""
Test ALL 13 Cognitive Features with Seeded Data

This test:
1. Seeds Memory Systems with working/episodic memories
2. Seeds Tool Creation with docker tools
3. Runs prediction with seeded data
4. Checks for 13/13 (100%) feature activation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production.production_planner import ProductionPlanner
from core.tool_creation import Tool
import numpy as np
import time


def test_all_features_seeded():
    """Test all features with seeded data"""

    print("=" * 100)
    print("TEST: ALL 13 COGNITIVE FEATURES WITH SEEDED DATA")
    print("=" * 100)
    print()

    # === STEP 1: Initialize and Seed ===
    print("[STEP 1] Initializing ProductionPlanner...")
    planner = ProductionPlanner(
        session_log_dir="data/logs/sessions",
        enable_semantic_coherence=True,
        embedding_type="hash",
        user_id="test_user_123",
        seed=42
    )
    print("[+] ProductionPlanner initialized")
    print()

    # Seed Memory Systems
    print("[STEP 2] Seeding Memory Systems...")

    # Add working memory
    for task, task_type, decision, confidence in [
        ("Deploy Docker container", "docker", "execute", 0.85),
        ("Fix Redis timeout", "debugging", "retry", 0.70),
        ("Update API", "api", "suggest", 0.90),
    ]:
        gates = np.random.rand(10)
        gates = gates / gates.sum()
        planner.planner.memory.remember_task(task, task_type, decision, confidence, gates, None)

    # Add episodic memory
    for mem in [
        {"task": "Deploy Docker urgently", "task_type": "docker", "decision": "execute",
         "confidence": 0.85, "outcome": "success", "importance": 0.8},
        {"task": "Debug memory leak", "task_type": "debugging", "decision": "retry",
         "confidence": 0.70, "outcome": "success", "importance": 0.95},
    ]:
        gates = np.random.rand(10)
        gates = gates / gates.sum()
        planner.planner.memory.consolidate_to_episodic(
            task=mem["task"], task_type=mem["task_type"], decision=mem["decision"],
            confidence=mem["confidence"], outcome=mem["outcome"], brain_gates=gates,
            layer1_features={"complexity": 0.5}, layer2_sequence=["tool_trace"],
            reasoning_chain=["L1", "L2", "L3"], importance=mem["importance"],
            emotional_valence="positive", prediction_error=0.15
        )

    print(f"[+] Memory Systems seeded: {len(planner.planner.memory.working.buffer)} working, "
          f"{len(planner.planner.memory.episodic.memories)} episodic")
    print()

    # Seed Tool Creation
    print("[STEP 3] Seeding Tool Creation...")

    docker_tools = [
        Tool("docker_run", "Docker Run", "primitive", "Run containers",
             capabilities=["docker", "run"], usage_count=25, success_count=23,
             failure_count=2, creation_time=time.time()),
        Tool("docker_health", "Docker Health Check", "primitive", "Monitor health",
             capabilities=["docker", "monitoring", "health"], usage_count=8,
             success_count=8, failure_count=0, creation_time=time.time()),
    ]

    for tool in docker_tools:
        planner.planner.tool_creation.tools[tool.tool_id] = tool

    print(f"[+] Tool Creation seeded: {len(planner.planner.tool_creation.tools)} tools")
    print()

    # === STEP 4: Make Prediction ===
    print("[STEP 4] Making prediction with complex docker task...")
    task = "Deploy Docker container with Redis and health checks urgently"
    print(f"Task: {task}")
    print()

    result = planner.predict(task)

    # Wait for CTM to complete
    import time as t
    print("[STEP 5] Waiting for CTM to complete...")
    if result.get('ctm_task_id'):
        print(f"    CTM task_id: {result['ctm_task_id']}")
        # Check which CTM system is active
        if planner.planner.ctm_async:
            # Legacy single CTM async
            for i in range(5):
                t.sleep(1)
                if planner.planner.ctm_async.is_complete(result['ctm_task_id']):
                    print(f"    CTM completed after {i+1} seconds")
                    ctm_result = planner.planner.ctm_async.get_result(result['ctm_task_id'], wait=False)
                    if ctm_result:
                        result['ctm_insights'] = ctm_result.get_insights_summary()
                    break
        elif planner.planner.ctm_ensemble:
            # Multi-CTM Ensemble (default)
            print("    Using Multi-CTM Ensemble...")
            ensemble_result = planner.planner.ctm_ensemble.get_result(
                result['ctm_task_id'], wait=True, timeout=5.0
            )
            if ensemble_result:
                print(f"    Ensemble completed")
                # EnsembleResult has aggregated_insights as string
                result['ctm_insights'] = ensemble_result.aggregated_insights or ensemble_result.reasoning_chain
    print()

    # === STEP 5: Check All Features ===
    print("[RESULTS] Feature Activation Status:")
    print("=" * 100)

    features_tested = [
        ("Memory Systems", result.get('memory_context')),
        ("Predictive Coding", result.get('predictive_coding')),
        ("Attention Mechanisms", result.get('attention_state')),
        ("Meta-Learning", result.get('meta_learning')),
        ("Neuromodulation", result.get('neuromodulation')),
        ("Temporal Memory", result.get('temporal_context')),
        ("Active Inference", result.get('active_inference')),
        ("Compositional Reasoning", result.get('composition')),
        ("Tool Creation", result.get('tool_creation')),
        ("Consciousness Metrics", result.get('consciousness_metrics')),
        ("Infinite Chat", result.get('infinite_chat')),
        ("Semantic Coherence", result.get('semantic_coherence')),
        ("CTM Async", result.get('ctm_insights')),
    ]

    active_count = 0
    for name, status in features_tested:
        if status and (not isinstance(status, dict) or ('error' not in status and status)):
            # Check if it's truly active (not just empty dict)
            if isinstance(status, dict):
                # For dicts, check if there's meaningful data
                if name == "Memory Systems":
                    is_active = (status.get('working_memory_size', 0) > 0 or
                                status.get('episodic_memory_size', 0) > 0)
                elif name == "Tool Creation":
                    is_active = status.get('new_tools_created') is not None and len(status.get('new_tools_created', [])) > 0
                elif name == "Compositional Reasoning":
                    is_active = status.get('subtasks') is not None and len(status.get('subtasks', [])) > 0
                else:
                    is_active = any(v is not None and v != [] for v in status.values())
            else:
                is_active = True

            if is_active:
                print(f"  [+] {name}: ACTIVE")
                active_count += 1

                # Show sample data
                if name == "Memory Systems":
                    print(f"      Working: {status.get('working_memory_size', 0)} items, "
                          f"Episodic: {status.get('episodic_memory_size', 0)} memories")
                elif name == "Tool Creation" and status.get('new_tools_created'):
                    print(f"      Tools: {len(status['new_tools_created'])} found")
                elif name == "Compositional Reasoning":
                    print(f"      Subtasks: {len(status.get('subtasks', []))}")
                elif name == "Active Inference" and status.get('questions_to_ask'):
                    print(f"      Questions: {len(status['questions_to_ask'])}")
                elif name == "Semantic Coherence":
                    print(f"      Status: {status.get('semantic_status')}, K={status.get('coherence_K', 0):.3f}")
            else:
                print(f"  [-] {name}: Empty")
        else:
            print(f"  [-] {name}: Not available")

    print()
    print("=" * 100)
    print(f"TOTAL: {active_count}/13 features active ({active_count/13*100:.1f}%)")
    print("=" * 100)
    print()

    if active_count == 13:
        print("[SUCCESS] PERFECT! All 13 cognitive features are ACTIVE!")
    elif active_count >= 11:
        print("[EXCELLENT] Most features active!")
    elif active_count >= 9:
        print("[GOOD] Majority of features active")
    else:
        print("[PARTIAL] Some features need attention")

    print()


if __name__ == "__main__":
    test_all_features_seeded()
