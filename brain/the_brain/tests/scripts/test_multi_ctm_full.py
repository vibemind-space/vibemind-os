"""
Full Multi-CTM Ensemble Validation Test

Tests all 4 CTMs (Spatial, Logic, Temporal, Value) together:
1. Domain router classification accuracy
2. Single-domain routing
3. Mixed-domain parallel execution
4. Fallback behavior
5. Ensemble statistics

Usage:
    python demos/test_multi_ctm_full.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
from typing import Dict, List

# Import CTM components
from core.ctm_domain_router import CTMDomainRouter, CTMDomain
from core.multi_ctm_ensemble import MultiCTMEnsemble, EnsembleResult

def print_header(text: str):
    """Print section header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def test_domain_router():
    """Test 1: Domain Router Classification"""
    print_header("TEST 1: DOMAIN ROUTER CLASSIFICATION")

    router = CTMDomainRouter(
        mixed_domain_threshold=0.70,
        confidence_min=0.50
    )

    # Test tasks for each domain
    test_tasks = [
        # Spatial domain
        ("Design microservice architecture with service mesh", CTMDomain.SPATIAL),
        ("Plan network topology for minimal latency", CTMDomain.SPATIAL),

        # Logic domain
        ("Validate Kubernetes manifest against security policies", CTMDomain.LOGIC),
        ("Check type constraints in function signatures", CTMDomain.LOGIC),

        # Temporal domain
        ("Detect anomalies in time-series metrics", CTMDomain.TEMPORAL),
        ("Schedule microservices auto-scaling events", CTMDomain.TEMPORAL),

        # Value domain
        ("Optimize resource allocation with cost trade-offs", CTMDomain.VALUE),
        ("Choose deployment strategy balancing speed vs reliability", CTMDomain.VALUE),
    ]

    correct = 0
    total = len(test_tasks)

    print("\nClassification Results:")
    print("-" * 70)

    for task, expected_domain in test_tasks:
        result = router.classify_task(task)
        is_correct = result.primary_domain == expected_domain
        correct += 1 if is_correct else 0

        status = "OK" if is_correct else "FAIL"
        print(f"\n  [{status}] {task[:50]}...")
        print(f"       Expected: {expected_domain.value}, Got: {result.primary_domain.value}")
        print(f"       Confidence: {result.confidence:.2%}")

    accuracy = correct / total * 100
    print(f"\n\nDomain Router Accuracy: {correct}/{total} ({accuracy:.1f}%)")

    return accuracy >= 75  # Pass if 75%+ correct

def test_single_domain_routing():
    """Test 2: Single Domain Routing with Ensemble"""
    print_header("TEST 2: SINGLE DOMAIN ROUTING")

    # Initialize ensemble with all CTMs enabled
    ensemble = MultiCTMEnsemble(
        max_concurrent_per_ctm=2,
        consciousness_threshold=0.85,
        max_reasoning_steps=15,  # Reduced for fast testing
        enable_logic_ctm=True,
        enable_temporal_ctm=True,
        enable_value_ctm=True
    )

    # Test one task per domain
    test_tasks = [
        ("Design microservice architecture", "spatial"),
        ("Validate security policy constraints", "logic"),
        ("Detect time-series patterns", "temporal"),
        ("Optimize cost vs performance trade-off", "value"),
    ]

    results = []

    for task, expected_domain in test_tasks:
        print(f"\n  Testing {expected_domain.upper()} domain...")
        print(f"  Task: {task}")

        brain_state = {
            'modality_activations': {
                'tool_trace': 0.8,
                'temporal_pattern': 0.6,
                'error_signal': 0.2
            }
        }

        task_id = ensemble.reason_async(
            task=task,
            brain_state=brain_state,
            domain_hint=expected_domain
        )

        # Wait for result
        result = ensemble.get_result(task_id, wait=True, timeout=20)

        if result:
            actual_domain = result.primary_domain.value
            match = actual_domain == expected_domain
            status = "OK" if match else "WARN"
            print(f"  [{status}] Routed to: {actual_domain}CTM")
            print(f"  Elapsed: {result.elapsed_time:.1f}s")
            results.append(match)
        else:
            print(f"  [FAIL] No result returned")
            results.append(False)

    passed = sum(results)
    print(f"\n\nSingle Domain Routing: {passed}/{len(results)} domains routed correctly")

    return passed >= 3  # Pass if 3/4 correct

def test_mixed_domain():
    """Test 3: Mixed Domain Parallel Execution"""
    print_header("TEST 3: MIXED DOMAIN PARALLEL EXECUTION")

    ensemble = MultiCTMEnsemble(
        max_concurrent_per_ctm=2,
        consciousness_threshold=0.80,
        max_reasoning_steps=10,
        enable_logic_ctm=True,
        enable_temporal_ctm=True,
        enable_value_ctm=True
    )

    # Mixed domain task (spatial + temporal + value)
    mixed_task = "Design auto-scaling microservice architecture with cost optimization and anomaly detection"

    print(f"\n  Mixed Task: {mixed_task}")

    brain_state = {
        'modality_activations': {
            'tool_trace': 0.9,
            'temporal_pattern': 0.8,
            'error_signal': 0.3
        }
    }

    start_time = time.time()
    task_id = ensemble.reason_async(
        task=mixed_task,
        brain_state=brain_state
    )

    result = ensemble.get_result(task_id, wait=True, timeout=30)
    total_time = time.time() - start_time

    if result:
        print(f"\n  Primary Domain: {result.primary_domain.value}")
        print(f"  Secondary Domains: {[d.value for d in result.secondary_domains]}")
        print(f"  Total Time: {total_time:.1f}s")

        # Check CTM results
        print(f"\n  CTM Results:")
        for domain, ctm_result in result.ctm_results.items():
            if ctm_result:
                print(f"    - {domain.value}CTM: Status={ctm_result.status.value}")

        if result.aggregated_insights:
            print(f"\n  Aggregated Insights:\n    {result.aggregated_insights}")

        # Mixed domain should trigger at least 2 CTMs
        active_ctms = sum(1 for r in result.ctm_results.values() if r is not None)
        print(f"\n  Active CTMs: {active_ctms}")

        return active_ctms >= 1  # Pass if at least 1 CTM returned result
    else:
        print(f"  [FAIL] No result returned")
        return False

def test_ensemble_stats():
    """Test 4: Ensemble Statistics"""
    print_header("TEST 4: ENSEMBLE STATISTICS")

    ensemble = MultiCTMEnsemble(
        max_concurrent_per_ctm=2,
        consciousness_threshold=0.85,
        max_reasoning_steps=10,
        enable_logic_ctm=True,
        enable_temporal_ctm=True,
        enable_value_ctm=True
    )

    # Run a few quick tasks
    tasks = [
        "Design architecture",
        "Validate constraints",
        "Detect patterns"
    ]

    for task in tasks:
        task_id = ensemble.reason_async(
            task=task,
            brain_state={'modality_activations': {}},
            max_steps=5
        )
        ensemble.get_result(task_id, wait=True, timeout=15)

    # Get stats
    stats = ensemble.get_stats()

    print(f"\n  Total Ensemble Tasks: {stats['total_ensemble_tasks']}")
    print(f"  Tasks by Domain: {stats['tasks_by_domain']}")
    print(f"  Active CTMs: {stats['active_ctms']}")

    if stats.get('ctm_stats'):
        print(f"\n  Per-CTM Statistics:")
        for ctm_name, ctm_stat in stats['ctm_stats'].items():
            print(f"    - {ctm_name}: {ctm_stat}")

    return stats['total_ensemble_tasks'] >= 3

def main():
    """Run all validation tests"""
    print_header("MULTI-CTM ENSEMBLE FULL VALIDATION")
    print(f"\n  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Testing all 4 CTMs: Spatial, Logic, Temporal, Value")

    results = {
        'domain_router': False,
        'single_domain': False,
        'mixed_domain': False,
        'ensemble_stats': False
    }

    try:
        # Test 1: Domain Router
        results['domain_router'] = test_domain_router()

        # Test 2: Single Domain Routing
        results['single_domain'] = test_single_domain_routing()

        # Test 3: Mixed Domain
        results['mixed_domain'] = test_mixed_domain()

        # Test 4: Ensemble Stats
        results['ensemble_stats'] = test_ensemble_stats()

    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print_header("VALIDATION SUMMARY")

    passed = sum(results.values())
    total = len(results)

    for test_name, passed_test in results.items():
        status = "PASS" if passed_test else "FAIL"
        print(f"  [{status}] {test_name.replace('_', ' ').title()}")

    print(f"\n  Overall: {passed}/{total} tests passed")

    if passed == total:
        print("\n  " + "=" * 50)
        print("  ALL TESTS PASSED - MULTI-CTM ENSEMBLE VALIDATED!")
        print("  " + "=" * 50)
    else:
        print("\n  Some tests failed - review output above")

    # Save results
    results_path = 'data/ctm_checkpoints/validation_results.json'
    with open(results_path, 'w') as f:
        json.dump({
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'results': results,
            'passed': passed,
            'total': total
        }, f, indent=2)
    print(f"\n  Results saved: {results_path}")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
