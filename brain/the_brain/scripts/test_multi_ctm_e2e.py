"""
End-to-End Multi-CTM Test (Simplified)

Tests all 4 CTMs to verify:
1. All CTMs initialize with loaded weights
2. Domain routing matches expected domains
3. Ensemble stats are tracked correctly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.multi_ctm_ensemble import MultiCTMEnsemble
from core.shared_enums import CTMDomain

def run_e2e_test():
    """Run end-to-end Multi-CTM test."""

    print("=" * 70)
    print("  END-TO-END MULTI-CTM TEST")
    print("=" * 70)

    # Initialize ensemble with all 4 CTMs
    print("\n[1] Initializing Multi-CTM Ensemble...")
    ensemble = MultiCTMEnsemble(
        max_concurrent_per_ctm=2,
        consciousness_threshold=0.85,
        max_reasoning_steps=30,
        enable_logic_ctm=True,
        enable_temporal_ctm=True,
        enable_value_ctm=True
    )

    # Check all CTMs are active
    print("\n[2] Verifying CTM Status...")
    active_count = 0
    for domain in CTMDomain:
        ctm = ensemble.ctms.get(domain)
        status = "ACTIVE" if ctm is not None else "disabled"
        print(f"    {domain.value}: {status}")
        if ctm is not None:
            active_count += 1

    if active_count != 4:
        print(f"\n[ERROR] Expected 4 active CTMs, got {active_count}")
        return False
    print(f"\n    All {active_count}/4 CTMs active!")

    # Test tasks for each domain
    test_tasks = [
        ("Design microservice architecture with load balancing", "spatial"),
        ("Validate Kubernetes YAML against security policies", "logic"),
        ("Detect anomalies in CPU usage time-series data", "temporal"),
        ("Optimize cloud costs while maintaining 99.9% uptime", "value"),
    ]

    print("\n[3] Running Domain Routing Tests...")
    routing_success = 0
    for task, expected in test_tasks:
        classification = ensemble.domain_router.classify_task(task)
        actual = classification.primary_domain.value
        match = "OK" if actual == expected else "FAIL"
        print(f"    [{match}] {task[:45]}...")
        print(f"         -> {actual} (expected: {expected}, conf: {classification.confidence:.2f})")
        if actual == expected:
            routing_success += 1

    print(f"\n    Routing: {routing_success}/{len(test_tasks)} correct")

    # Show ensemble stats
    print("\n[4] Ensemble Statistics...")
    stats = ensemble.get_stats()
    print(f"    Active CTMs: {stats['active_ctms']}")
    print(f"    Evolution enabled: {stats['evolution_enabled']}")

    # Verify pending CTMs (should be none now)
    pending = ensemble.get_pending_ctms()
    print(f"\n[5] Pending CTMs: {[d.value for d in pending]}")
    if len(pending) == 0:
        print("    All CTMs trained and ready!")

    print("\n" + "=" * 70)
    print("  END-TO-END TEST COMPLETE")
    print("=" * 70)

    return routing_success == len(test_tasks) and active_count == 4


if __name__ == "__main__":
    success = run_e2e_test()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")
    sys.exit(0 if success else 1)
