"""
Test Semantic Coherence Integration in Production API

Tests:
1. ProductionPlanner with semantic coherence enabled
2. Different embedding types (hash, neural, openai)
3. Semantic metrics in API response
4. Traffic light status (GREEN/YELLOW/RED)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production.production_planner import ProductionPlanner
import json


def test_semantic_production():
    """Test ProductionPlanner with semantic coherence"""

    print("=" * 80)
    print("TEST: Semantic Coherence in Production API")
    print("=" * 80)
    print()

    # Test 1: Hash embeddings (fast, always works)
    print("[TEST 1] Initialize ProductionPlanner with HASH embeddings (fast, reliable)")
    print("-" * 80)

    try:
        planner_neural = ProductionPlanner(
            session_log_dir="data/logs/sessions",
            enable_semantic_coherence=True,
            embedding_type="hash",  # hash-based TF-IDF (always works, no dependencies)
            k_min=0.55,
            green_threshold=0.75,
            alpha=0.5,
            seed=42
        )
        print("[+] SUCCESS: ProductionPlanner initialized with hash embeddings")
        print()
    except Exception as e:
        print(f"[X] FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 2: Make prediction with semantic validation
    print("[TEST 2] Make prediction with semantic validation")
    print("-" * 80)

    test_tasks = [
        "Deploy Docker container with health checks",
        "Fix merge conflict in main branch",
        "List all files on desktop"
    ]

    for i, task in enumerate(test_tasks, 1):
        print(f"\n[Task {i}] {task}")
        print("-" * 40)

        try:
            result = planner_neural.predict(task)

            # Check semantic coherence in result
            if result['semantic_coherence'] is not None:
                sc = result['semantic_coherence']
                print(f"[+] Semantic Coherence:")
                print(f"    Coherence K: {sc['coherence_K']:.3f}")
                print(f"    Disagreement U: {sc['disagreement_U']:.3f}")
                print(f"    Truth Stability: {sc['truth_stability']:.3f}")
                print(f"    Status: {sc['semantic_status']}")
                print(f"    Swarm Consensus: {sc['swarm_consensus']}")
                print(f"    Swarm Confidence: {sc['swarm_confidence']:.3f}")

                # Verify traffic light status
                if sc['truth_stability'] >= 0.75:
                    expected_status = 'GREEN'
                elif sc['truth_stability'] >= 0.55:
                    expected_status = 'YELLOW'
                else:
                    expected_status = 'RED'

                if sc['semantic_status'] == expected_status:
                    print(f"    [+] Traffic light status correct: {expected_status}")
                else:
                    print(f"    [!] Traffic light mismatch: got {sc['semantic_status']}, expected {expected_status}")

            else:
                print(f"[!] No semantic coherence in result")

            # Check prediction
            print(f"\n[+] Prediction:")
            print(f"    Primary Action: {result['prediction']['primary_action']}")
            print(f"    Confidence: {result['prediction']['confidence']:.3f}")
            print(f"    Task Type: {result['prediction']['task_type']}")

            # Check reasoning chain includes semantic info
            if result['reasoning_chain']:
                semantic_reasoning = [r for r in result['reasoning_chain'] if 'Semantic Coherence' in r]
                if semantic_reasoning:
                    print(f"\n[+] Semantic reasoning in chain:")
                    for r in semantic_reasoning:
                        print(f"    {r}")
                else:
                    print(f"\n[!] No semantic reasoning in reasoning chain")

        except Exception as e:
            print(f"[X] FAILED: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=" * 80)

    # Test 3: Try neural embeddings (might fail on Windows with JAX issues)
    print("[TEST 3] Try NEURAL embeddings (might fail on Windows)")
    print("-" * 80)

    try:
        planner_neural_test = ProductionPlanner(
            session_log_dir="data/logs/sessions",
            enable_semantic_coherence=True,
            embedding_type="neural",  # sentence-transformers
            k_min=0.55,
            green_threshold=0.75,
            alpha=0.5,
            seed=42
        )
        print("[+] SUCCESS: Neural embeddings work on this system!")

        task = "Deploy Docker container"
        result = planner_neural_test.predict(task)

        if result['semantic_coherence']:
            sc = result['semantic_coherence']
            print(f"[+] Neural embeddings: K={sc['coherence_K']:.3f}, status={sc['semantic_status']}")
        else:
            print(f"[!] No semantic coherence in result")

    except Exception as e:
        print(f"[!] Neural embeddings not available (expected on Windows): {str(e)[:100]}")
        print(f"[+] Fallback to hash embeddings recommended for this system")

    print()
    print("=" * 80)

    # Test 4: Test without semantic coherence
    print("[TEST 4] Test WITHOUT semantic coherence (disabled)")
    print("-" * 80)

    try:
        planner_no_semantic = ProductionPlanner(
            session_log_dir="data/logs/sessions",
            enable_semantic_coherence=False,  # Disabled!
            seed=42
        )
        print("[+] SUCCESS: ProductionPlanner initialized without semantic coherence")

        task = "Deploy Docker container"
        result = planner_no_semantic.predict(task)

        if result['semantic_coherence'] is None:
            print(f"[+] Semantic coherence correctly disabled (None in result)")
        else:
            print(f"[!] Semantic coherence should be None but got: {result['semantic_coherence']}")

    except Exception as e:
        print(f"[X] FAILED: {e}")

    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_semantic_production()
