"""
Test CTM Async Insights

This test properly waits for CTM to complete and captures the insights.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production.production_planner import ProductionPlanner
from core.tool_creation import Tool
import numpy as np
import time as time_module


def test_ctm_insights():
    """Test CTM async with proper waiting"""

    print("=" * 100)
    print("TEST: CTM ASYNC INSIGHTS")
    print("=" * 100)
    print()

    # Initialize planner
    print("[1] Initializing ProductionPlanner...")
    planner = ProductionPlanner(
        session_log_dir="data/logs/sessions",
        enable_semantic_coherence=False,  # Faster
        user_id="test_user_ctm",
        seed=42
    )
    print("[+] Initialized")
    print()

    # Seed memory
    print("[2] Seeding memory...")
    for task, task_type, decision, confidence in [
        ("Deploy Docker", "docker", "execute", 0.85),
    ]:
        gates = np.random.rand(10)
        gates = gates / gates.sum()
        planner.planner.memory.remember_task(task, task_type, decision, confidence, gates, None)
    print("[+] Memory seeded")
    print()

    # Seed tools
    print("[3] Seeding tools...")
    docker_tool = Tool("docker_run", "Docker Run", "primitive", "Run containers",
                      capabilities=["docker"], usage_count=25, success_count=23,
                      failure_count=2, creation_time=time_module.time())
    planner.planner.tool_creation.tools[docker_tool.tool_id] = docker_tool
    print("[+] Tools seeded")
    print()

    # Make prediction (CTM will start in background)
    print("[4] Making prediction...")
    task = "Deploy Docker container with Redis and health checks urgently"
    print(f"Task: {task}")
    print()

    result = planner.predict(task)

    # Check if CTM started
    print("[5] Checking CTM status...")
    if 'ctm_task_id' in result:
        ctm_task_id = result['ctm_task_id']
        print(f"[+] CTM started with task_id: {ctm_task_id}")
    else:
        print("[-] CTM not started (task complexity too low?)")
        print(f"    Task complexity: {result['prediction']['complexity']}")
        print(f"    CTM threshold: 0.4")
        return
    print()

    # Wait for CTM to complete
    print("[6] Waiting for CTM to complete (max 20 seconds)...")
    start_time = time_module.time()
    ctm_result = None

    # Check which CTM system is active
    if planner.planner.ctm_async:
        # Legacy single CTM async
        for i in range(20):
            time_module.sleep(1)
            if planner.planner.ctm_async.is_complete(ctm_task_id):
                elapsed = time_module.time() - start_time
                print(f"[+] CTM completed after {elapsed:.1f} seconds!")
                break
            if (i + 1) % 5 == 0:
                print(f"    ... still running ({i+1}s)")
        else:
            print("[-] CTM did not complete within 20 seconds")
            return
        print()
        print("[7] Retrieving CTM insights...")
        ctm_result = planner.planner.ctm_async.get_result(ctm_task_id, wait=False)
    elif planner.planner.ctm_ensemble:
        # Multi-CTM Ensemble (default)
        print("    Using Multi-CTM Ensemble...")
        ensemble_result = planner.planner.ctm_ensemble.get_result(
            ctm_task_id, wait=True, timeout=20.0
        )
        if ensemble_result:
            elapsed = time_module.time() - start_time
            print(f"[+] Ensemble completed after {elapsed:.1f} seconds!")
            print()
            print("[7] Ensemble Insights:")
            print(f"    Primary domain: {ensemble_result.primary_domain.value}")
            print(f"    Elapsed time: {ensemble_result.elapsed_time:.2f}s")
            # Get confidence from primary CTM result
            primary_result = ensemble_result.ctm_results.get(ensemble_result.primary_domain)
            if primary_result and primary_result.ctm_insight:
                print(f"    Consciousness: {primary_result.ctm_insight.final_consciousness:.0%}")
            insights = ensemble_result.aggregated_insights or ensemble_result.reasoning_chain
            if insights:
                print(f"    Insights: {insights[:200]}...")
            print()
            print("=" * 100)
            print("[SUCCESS] Multi-CTM Ensemble is ACTIVE and providing insights!")
            print("=" * 100)
            return
        else:
            print("[-] Ensemble did not complete within 20 seconds")
            return
    else:
        print("[-] No CTM system available")
        return

    if ctm_result:
        print(f"[+] CTM Result Retrieved:")
        print(f"    Status: {ctm_result.status.value}")
        print(f"    Steps taken: {ctm_result.steps_taken}")
        print(f"    Converged: {ctm_result.converged}")
        print(f"    Confidence: {ctm_result.confidence:.0%}")
        print(f"    Elapsed time: {ctm_result.elapsed_time:.1f}s")
        print()

        # Get insights summary
        insights_summary = ctm_result.get_insights_summary()
        print("[8] CTM Insights Summary:")
        print("-" * 100)
        print(insights_summary)
        print("-" * 100)
        print()

        # Show reasoning trace sample
        if ctm_result.reasoning_trace:
            print("[9] Reasoning Trace Sample:")
            print(f"    Total thoughts: {len(ctm_result.reasoning_trace)}")
            print("    First 3 thoughts:")
            for i, thought in enumerate(ctm_result.reasoning_trace[:3], 1):
                print(f"      {i}. {thought}")
            print("    Last 3 thoughts:")
            for i, thought in enumerate(ctm_result.reasoning_trace[-3:], len(ctm_result.reasoning_trace)-2):
                print(f"      {i}. {thought}")
        print()

        # Convert to dict
        print("[10] Full CTM Result (dict):")
        ctm_dict = ctm_result.to_dict()
        import json
        print(json.dumps(ctm_dict, indent=2))
        print()

        print("=" * 100)
        print("[SUCCESS] CTM Async is ACTIVE and providing insights!")
        print("=" * 100)
        print()
        print(f"CTM Analysis: {ctm_result.steps_taken} reasoning steps completed")
        print(f"Key Insight: {ctm_result.reasoning_trace[-1] if ctm_result.reasoning_trace else 'N/A'}")

    else:
        print("[-] Could not retrieve CTM result")


if __name__ == "__main__":
    test_ctm_insights()
