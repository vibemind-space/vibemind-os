"""
Adaptive Cognitive System (ACS) - Production End-to-End Test

Tests the complete integration of:
- Phase 5: Meta-CTM Supervisor
- Phase 6: Goal Graph in Hierarchical Planner
- Phase 7: Evolutionary CTM Selection

This validates that all ACS components work together in production.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
from datetime import datetime


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str):
    """Print a section header."""
    print(f"\n--- {title} ---")


def test_meta_ctm_supervisor():
    """Test Meta-CTM Supervisor functionality."""
    print_header("TEST 1: Meta-CTM Supervisor")

    from core.meta_ctm import MetaCTMSupervisor, CTMHealth

    # Initialize supervisor
    supervisor = MetaCTMSupervisor(
        consciousness_threshold=0.7,
        max_consecutive_failures=3
    )
    print("[OK] MetaCTMSupervisor initialized")

    # Test task selection
    print_section("Task Selection")

    tasks = [
        ("Design microservice architecture", "spatial"),
        ("Validate security policies", "logic"),
        ("Detect time-series anomalies", "temporal"),
        ("Optimize cost vs performance", "value"),
    ]

    for task, expected_domain in tasks:
        decision = supervisor.select_ctm(task=task, domain_hint=expected_domain)
        print(f"  Task: {task[:40]}")
        print(f"    Selected: {decision.selected_ctm}, Confidence: {decision.confidence:.2f}")
        assert decision.selected_ctm == expected_domain, f"Expected {expected_domain}"

    # Test health monitoring
    print_section("Health Monitoring")

    # Record some tasks
    for i in range(5):
        supervisor.record_task_result(
            task_id=f"task_{i}",
            domain="spatial",
            consciousness=0.85 + (i * 0.02),
            response_time=1.0 + (i * 0.1),
            success=True,
            task_description="Test task"
        )

    health = supervisor.get_health_status()
    print(f"  Spatial CTM Health: {health['spatial']['health']}")
    print(f"  Tasks Processed: {health['spatial']['total_tasks']}")
    print(f"  Success Rate: {health['spatial']['success_rate']:.1%}")

    assert health['spatial']['health'] == 'healthy'
    assert health['spatial']['total_tasks'] == 5

    print("\n[PASS] Meta-CTM Supervisor test completed")
    return True


def test_goal_graph():
    """Test Goal Graph functionality."""
    print_header("TEST 2: Goal Graph System")

    from core.goal_graph import GoalGraph, GoalPriority, GoalState

    # Initialize graph
    graph = GoalGraph()
    print("[OK] GoalGraph initialized")

    # Create goals
    print_section("Goal Creation")

    # Parent goal
    parent = graph.add_goal(
        description="Deploy production system",
        priority=GoalPriority.HIGH
    )
    print(f"  Created parent goal: {parent.goal_id[:8]}...")

    # Child goals
    child1 = graph.add_goal(
        description="Setup infrastructure",
        priority=GoalPriority.MEDIUM,
        parent_id=parent.goal_id
    )
    child2 = graph.add_goal(
        description="Deploy services",
        priority=GoalPriority.MEDIUM,
        parent_id=parent.goal_id
    )
    print(f"  Created 2 child goals")

    # Test hierarchy
    print_section("Goal Hierarchy")
    assert child1.parent_id == parent.goal_id
    assert child2.parent_id == parent.goal_id
    print(f"  Parent-child relationships verified")

    # Test goal states
    print_section("Goal State Transitions")

    # Start and complete child1
    graph.start_goal(child1.goal_id)
    assert graph.goals[child1.goal_id].state == GoalState.ACTIVE
    print(f"  Child1: PENDING -> ACTIVE")

    graph.complete_goal(child1.goal_id)
    assert graph.goals[child1.goal_id].state == GoalState.COMPLETED
    print(f"  Child1: ACTIVE -> COMPLETED")

    # Fail child2
    graph.start_goal(child2.goal_id)
    graph.fail_goal(child2.goal_id, "Test failure")
    assert graph.goals[child2.goal_id].state == GoalState.FAILED
    print(f"  Child2: ACTIVE -> FAILED")

    # Statistics
    print_section("Statistics")
    stats = graph.get_statistics()
    print(f"  Total Goals: {stats['total_goals']}")
    print(f"  Completed: {stats['completed_count']}")
    print(f"  Failed: {stats['failed_count']}")

    assert stats['total_goals'] == 3
    assert stats['completed_count'] == 1
    assert stats['failed_count'] == 1

    print("\n[PASS] Goal Graph test completed")
    return True


def test_evolutionary_selector():
    """Test Evolutionary CTM Selection functionality."""
    print_header("TEST 3: Evolutionary CTM Selection")

    from core.evolutionary_ctm_selector import (
        EvolutionaryCTMSelector, CTMGenes, CTMIndividual
    )

    # Initialize selector
    selector = EvolutionaryCTMSelector(
        population_size=10,
        elite_count=2,
        mutation_rate=0.15,
        crossover_rate=0.7
    )
    print("[OK] EvolutionaryCTMSelector initialized")

    # Check populations
    print_section("Population Initialization")
    for domain in ['spatial', 'logic', 'temporal', 'value']:
        pop_size = len(selector.populations[domain])
        print(f"  {domain.capitalize()}: {pop_size} individuals")
        assert pop_size == 10

    # Record performance
    print_section("Performance Recording")
    for i in range(5):
        best = selector.select_best_ctm('spatial')
        selector.record_performance(
            domain='spatial',
            individual_id=best.id,
            consciousness=0.8 + (i * 0.03),
            response_time=2.0 - (i * 0.2),
            success=True,
            complexity=0.7
        )
    print(f"  Recorded 5 performance samples for spatial")

    # Run evolution
    print_section("Evolution Cycle")
    result = selector.evolve_population('spatial')
    print(f"  Generation: {result['generation']}")
    print(f"  Pre-Evolution Best: {result['pre_evolution']['best_fitness']:.3f}")
    print(f"  Post-Evolution Best: {result['post_evolution']['best_fitness']:.3f}")

    # Get best genes
    print_section("Best Genes Retrieval")
    genes = selector.get_best_genes('spatial')
    print(f"  Consciousness Threshold: {genes.consciousness_threshold:.3f}")
    print(f"  Max Reasoning Steps: {genes.max_reasoning_steps}")
    print(f"  Learning Rate: {genes.learning_rate:.5f}")

    # Statistics
    print_section("Evolution Statistics")
    stats = selector.get_all_stats()
    for domain, domain_stats in stats.items():
        print(f"  {domain}: Gen {domain_stats['generation']}, "
              f"Best Fitness: {domain_stats['best_fitness']:.3f}")

    print("\n[PASS] Evolutionary CTM Selection test completed")
    return True


def test_multi_ctm_ensemble_integration():
    """Test Multi-CTM Ensemble with all ACS features."""
    print_header("TEST 4: Multi-CTM Ensemble Integration")

    from core.multi_ctm_ensemble import MultiCTMEnsemble, CTMDomain

    # Initialize ensemble with evolution enabled
    ensemble = MultiCTMEnsemble(
        max_concurrent_per_ctm=2,
        consciousness_threshold=0.85,
        max_reasoning_steps=20,
        device='cpu',
        enable_logic_ctm=True,
        enable_temporal_ctm=True,
        enable_value_ctm=True,
        enable_evolution=True,
        evolution_population_size=10
    )
    print("[OK] MultiCTMEnsemble initialized with evolution")

    # Check domains
    print_section("Domain Router")
    test_tasks = [
        ("Design distributed architecture", "spatial"),
        ("Verify compliance rules", "logic"),
        ("Analyze performance trends", "temporal"),
        ("Balance cost and quality", "value"),
    ]

    for task, expected in test_tasks:
        domain = ensemble.domain_router.classify_task(task)
        print(f"  '{task[:35]}...' -> {domain.primary_domain.value}")

    # Check evolution integration
    print_section("Evolution Integration")
    if ensemble.enable_evolution:
        stats = ensemble.get_evolution_stats()
        print(f"  Evolution enabled: True")
        print(f"  Domains with populations: {list(stats.keys())}")
        assert 'spatial' in stats
    else:
        print(f"  Evolution enabled: False")

    # Get statistics
    print_section("Ensemble Statistics")
    stats = ensemble.get_stats()
    print(f"  Total Tasks: {stats['total_tasks']}")
    print(f"  Active Tasks: {stats['active_tasks']}")
    print(f"  Completed Tasks: {stats['completed_tasks']}")

    print("\n[PASS] Multi-CTM Ensemble Integration test completed")
    return True


def test_full_system_integration():
    """Test complete ACS integration with HierarchicalPlanner."""
    print_header("TEST 5: Full System Integration")

    # Skip if heavy neural network loading would take too long
    print("[INFO] Testing lightweight integration (no neural network loading)")

    from core.meta_ctm import MetaCTMSupervisor
    from core.goal_graph import GoalGraph, GoalPriority
    from core.evolutionary_ctm_selector import EvolutionaryCTMSelector

    # Create all components
    supervisor = MetaCTMSupervisor()
    goal_graph = GoalGraph()
    selector = EvolutionaryCTMSelector(population_size=5)

    print("[OK] All ACS components initialized")

    # Simulate a complete workflow
    print_section("Simulated Workflow")

    # 1. Create a goal
    goal = goal_graph.add_goal(
        description="Complete complex task",
        priority=GoalPriority.HIGH
    )
    print(f"  1. Created goal: {goal.goal_id[:8]}...")

    # 2. Select CTM for the task
    decision = supervisor.select_ctm(
        task="Design microservice with auto-scaling",
        domain_hint="spatial"
    )
    print(f"  2. Selected CTM: {decision.selected_ctm} (confidence: {decision.confidence:.2f})")

    # 3. Get best genes for the domain
    genes = selector.get_best_genes(decision.selected_ctm)
    print(f"  3. Best genes: threshold={genes.consciousness_threshold:.2f}, "
          f"steps={genes.max_reasoning_steps}")

    # 4. Record task result
    supervisor.record_task_result(
        task_id="test_task",
        domain=decision.selected_ctm,
        consciousness=0.92,
        response_time=2.5,
        success=True,
        task_description="Design microservice with auto-scaling"
    )
    print(f"  4. Recorded task result")

    # 5. Record performance for evolution
    best = selector.select_best_ctm(decision.selected_ctm)
    selector.record_performance(
        domain=decision.selected_ctm,
        individual_id=best.id,
        consciousness=0.92,
        response_time=2.5,
        success=True
    )
    print(f"  5. Recorded performance for evolution")

    # 6. Complete goal
    goal_graph.start_goal(goal.goal_id)
    goal_graph.complete_goal(goal.goal_id)
    print(f"  6. Completed goal")

    # Verify final state
    print_section("Final State Verification")

    health = supervisor.get_health_status()
    print(f"  CTM Health: {health[decision.selected_ctm]['health']}")

    goal_stats = goal_graph.get_statistics()
    print(f"  Goals Completed: {goal_stats['completed_count']}/{goal_stats['total_goals']}")

    evo_stats = selector.get_all_stats()
    print(f"  Evolution Generation: {evo_stats[decision.selected_ctm]['generation']}")

    print("\n[PASS] Full System Integration test completed")
    return True


def main():
    """Run all production tests."""
    print_header("ADAPTIVE COGNITIVE SYSTEM - PRODUCTION TEST SUITE")
    print(f"Timestamp: {datetime.now().isoformat()}")

    tests = [
        ("Meta-CTM Supervisor", test_meta_ctm_supervisor),
        ("Goal Graph", test_goal_graph),
        ("Evolutionary CTM Selection", test_evolutionary_selector),
        ("Multi-CTM Ensemble Integration", test_multi_ctm_ensemble_integration),
        ("Full System Integration", test_full_system_integration),
    ]

    results = []

    for name, test_func in tests:
        try:
            start = time.time()
            success = test_func()
            elapsed = time.time() - start
            results.append((name, success, elapsed, None))
        except Exception as e:
            results.append((name, False, 0, str(e)))
            print(f"\n[FAIL] {name}: {e}")

    # Summary
    print_header("TEST SUMMARY")

    passed = sum(1 for _, success, _, _ in results if success)
    total = len(results)

    for name, success, elapsed, error in results:
        status = "[PASS]" if success else "[FAIL]"
        time_str = f"({elapsed:.2f}s)" if success else f"(ERROR: {error})"
        print(f"  {status} {name} {time_str}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n  [SUCCESS] All ACS production tests passed!")
        return 0
    else:
        print(f"\n  [FAILURE] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
