"""
Test Ensemble Path Planner - Phase 2
Validates 5 search strategies and meta-path interpolation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ensemble_path_planner import (
    EnsemblePathPlanner,
    SearchStrategy,
    SolutionPath,
    CommonCheckpoint,
    MetaPath
)
from core.context_aligned_state import (
    ContextAlignedState,
    ActionMetadata,
    ContextDimensions
)
from datetime import datetime
import random


def create_mock_action(action_type: str, action_name: str, success: bool = True):
    """Create mock action function"""
    def action_fn(state: ContextAlignedState) -> ContextAlignedState:
        new_state = ContextAlignedState(
            state_id=f"state_{state.step_count + 1}",
            step_count=state.step_count + 1,
            context=ContextDimensions(
                technical_context=min(1.0, state.context.technical_context + 0.1),
                user_preference_context=state.context.user_preference_context,
                task_context=min(1.0, state.context.task_context + 0.1),
                conversation_continuity=min(1.0, state.context.conversation_continuity + 0.05)
            ),
            confidence_level=state.confidence_level,
            ctm_thinking_rate=state.ctm_thinking_rate,
            last_action=ActionMetadata(
                action_type=action_type,
                action_name=action_name,
                success=success,
                duration=random.uniform(0.5, 2.0)
            ),
            is_checkpoint=success and action_type == 'tool_call',
            checkpoint_type='tool_success' if success and action_type == 'tool_call' else '',
            reliability_score=random.uniform(0.7, 0.95) if success else random.uniform(0.3, 0.6),
            path_progress=min(1.0, state.path_progress + 0.1),
            cumulative_time=state.cumulative_time + random.uniform(0.5, 2.0)
        )
        return new_state
    return action_fn


def test_ensemble_search():
    """Test 1: Ensemble search with multiple strategies"""
    print("\n" + "="*70)
    print("TEST 1: Ensemble Search with 5 Strategies")
    print("="*70)

    # Create initial state
    initial_state = ContextAlignedState(
        state_id="state_0",
        step_count=0,
        context=ContextDimensions(
            technical_context=0.5,
            user_preference_context=0.5,
            task_context=0.5,
            conversation_continuity=0.0
        ),
        confidence_level=0.5,
        ctm_thinking_rate=0.5,
        path_progress=0.0,
        cumulative_time=0.0
    )

    # Define goal condition (reach 80% progress with 3+ checkpoints)
    def goal_condition(state: ContextAlignedState) -> bool:
        return state.path_progress >= 0.8 and state.step_count >= 3

    # Create available actions
    available_actions = [
        create_mock_action('tool_call', 'read_file', success=True),
        create_mock_action('tool_call', 'write_file', success=True),
        create_mock_action('tool_call', 'api_get', success=True),
        create_mock_action('agent_response', 'generate_response', success=True),
        create_mock_action('thinking', 'analyze', success=True),
    ]

    # Create planner
    planner = EnsemblePathPlanner(
        num_solutions=5,
        max_steps_per_search=20,
        checkpoint_threshold=0.6,
        seed=42
    )

    # Find ensemble solutions
    print("\nSearching for solutions with 5 strategies...")
    solutions = planner.find_ensemble_solutions(
        initial_state=initial_state,
        goal_condition=goal_condition,
        available_actions=available_actions
    )

    print(f"\nFound {len(solutions)} solutions:\n")

    for i, solution in enumerate(solutions):
        print(f"Solution {i+1} ({solution.strategy.value}):")
        print(f"  States: {len(solution.states)}")
        print(f"  Checkpoints: {solution.checkpoint_count}")
        print(f"  Total time: {solution.total_time:.2f}s")
        print(f"  Success: {solution.success}")
        print(f"  Reliability: {solution.reliability_score:.3f}")
        print()

    # Verify all strategies attempted
    strategies_found = {s.strategy for s in solutions}
    print(f"Strategies found: {[s.value for s in strategies_found]}")

    if len(solutions) >= 3:
        print("\n[PASS] Ensemble search test passed!")
    else:
        print("\n[FAILED] Expected at least 3 solutions")

    return solutions


def test_checkpoint_extraction(solutions: list):
    """Test 2: Common checkpoint extraction"""
    print("\n" + "="*70)
    print("TEST 2: Common Checkpoint Extraction")
    print("="*70)

    if not solutions:
        print("[SKIP] No solutions available")
        return []

    planner = EnsemblePathPlanner(checkpoint_threshold=0.4, seed=42)

    print("\nExtracting common checkpoints...")
    common_checkpoints = planner.extract_common_checkpoints(solutions)

    print(f"\nFound {len(common_checkpoints)} common checkpoints:\n")

    for i, checkpoint in enumerate(common_checkpoints):
        print(f"Checkpoint {i+1}:")
        print(f"  Action: {checkpoint.action_type} - {checkpoint.action_name}")
        print(f"  Occurrences: {checkpoint.occurrence_count}/{len(solutions)}")
        print(f"  Strategies: {[s.value for s in checkpoint.strategies]}")
        print(f"  Avg step: {checkpoint.average_step:.1f}")
        print(f"  Avg confidence: {checkpoint.average_confidence:.3f}")
        print(f"  Reliability: {checkpoint.reliability_score:.3f}")
        print()

    if len(common_checkpoints) > 0:
        print("[PASS] Checkpoint extraction test passed!")
    else:
        print("[FAILED] No common checkpoints found")

    return common_checkpoints


def test_meta_path_interpolation(solutions: list, common_checkpoints: list):
    """Test 3: Meta-path interpolation"""
    print("\n" + "="*70)
    print("TEST 3: Meta-Path Interpolation")
    print("="*70)

    if not solutions or not common_checkpoints:
        print("[SKIP] No solutions or checkpoints available")
        return None

    planner = EnsemblePathPlanner(checkpoint_threshold=0.4, seed=42)

    initial_state = solutions[0].states[0]

    print("\nInterpolating meta-path from multiple solutions...")
    meta_path = planner.interpolate_meta_path(
        solutions=solutions,
        common_checkpoints=common_checkpoints,
        initial_state=initial_state
    )

    print(f"\nMeta-Path Quality:")
    print(f"  Essential checkpoints: {len(meta_path.essential_checkpoints)}")
    print(f"  Interpolated states: {len(meta_path.interpolated_states)}")
    print(f"  Coverage score: {meta_path.coverage_score:.3f} (agreement across solutions)")
    print(f"  Efficiency score: {meta_path.efficiency_score:.3f} (time efficiency)")
    print(f"  Reliability score: {meta_path.reliability_score:.3f} (success probability)")

    print(f"\nMeta-Path Sequence:")
    for i, state in enumerate(meta_path.interpolated_states[:5]):  # Show first 5
        action_desc = f"{state.last_action.action_type} - {state.last_action.action_name}" if state.last_action else "initial"
        checkpoint = "[CHECKPOINT]" if state.is_checkpoint else ""
        print(f"  Step {i}: {action_desc} {checkpoint}")

    if meta_path.reliability_score > 0.5:
        print("\n[PASS] Meta-path interpolation test passed!")
    else:
        print("\n[FAILED] Meta-path has low reliability")

    return meta_path


def test_strategy_diversity():
    """Test 4: Strategy diversity (different paths for different strategies)"""
    print("\n" + "="*70)
    print("TEST 4: Strategy Diversity Verification")
    print("="*70)

    initial_state = ContextAlignedState(
        state_id="state_0",
        step_count=0,
        context=ContextDimensions(0.5, 0.5, 0.5, 0.0),
        confidence_level=0.5,
        ctm_thinking_rate=0.5,
        path_progress=0.0,
        cumulative_time=0.0
    )

    def goal_condition(state: ContextAlignedState) -> bool:
        return state.step_count >= 5

    available_actions = [
        create_mock_action('tool_call', f'action_{i}', success=True)
        for i in range(10)
    ]

    planner = EnsemblePathPlanner(
        num_solutions=5,
        max_steps_per_search=15,
        checkpoint_threshold=0.6,
        seed=42
    )

    solutions = planner.find_ensemble_solutions(
        initial_state, goal_condition, available_actions
    )

    print(f"\nAnalyzing path diversity across {len(solutions)} solutions...")

    # Compare paths
    path_signatures = []
    for solution in solutions:
        signature = tuple(
            s.last_action.action_name if s.last_action else 'init'
            for s in solution.states[:5]  # First 5 steps
        )
        path_signatures.append((solution.strategy.value, signature))

    print(f"\nPath signatures (first 5 steps):")
    for strategy, signature in path_signatures:
        print(f"  {strategy:15s}: {signature}")

    # Calculate diversity (unique paths / total paths)
    unique_paths = len(set(path_signatures))
    diversity_ratio = unique_paths / len(path_signatures) if path_signatures else 0.0

    print(f"\nDiversity Metrics:")
    print(f"  Unique paths: {unique_paths}/{len(path_signatures)}")
    print(f"  Diversity ratio: {diversity_ratio:.1%}")

    if diversity_ratio >= 0.4:  # At least 40% diverse
        print("\n[PASS] Strategy diversity test passed!")
    else:
        print("\n[FAILED] Strategies producing too similar paths")

    return diversity_ratio


def test_performance_benchmarks():
    """Test 5: Performance benchmarks"""
    print("\n" + "="*70)
    print("TEST 5: Performance Benchmarks")
    print("="*70)

    initial_state = ContextAlignedState(
        state_id="state_0",
        step_count=0,
        context=ContextDimensions(0.5, 0.5, 0.5, 0.0),
        confidence_level=0.5,
        ctm_thinking_rate=0.5,
        path_progress=0.0,
        cumulative_time=0.0
    )

    def goal_condition(state: ContextAlignedState) -> bool:
        return state.path_progress >= 0.9

    available_actions = [
        create_mock_action('tool_call', f'action_{i}', success=(i % 3 != 0))
        for i in range(8)
    ]

    planner = EnsemblePathPlanner(
        num_solutions=5,
        max_steps_per_search=25,
        checkpoint_threshold=0.5,
        seed=42
    )

    import time
    start_time = time.time()

    solutions = planner.find_ensemble_solutions(
        initial_state, goal_condition, available_actions
    )

    elapsed_time = time.time() - start_time

    print(f"\nPerformance Metrics:")
    print(f"  Elapsed time: {elapsed_time:.3f}s")
    print(f"  Solutions found: {len(solutions)}")
    print(f"  Time per solution: {elapsed_time / max(1, len(solutions)):.3f}s")

    stats = planner.get_statistics()
    print(f"\nPlanner Statistics:")
    print(f"  Total searches: {stats['total_searches']}")
    print(f"  Successful searches: {stats['successful_searches']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")

    if elapsed_time < 5.0:  # Should complete in < 5 seconds
        print("\n[PASS] Performance benchmark test passed!")
    else:
        print("\n[FAILED] Ensemble search too slow")


def main():
    print("="*70)
    print("ENSEMBLE PATH PLANNER TEST SUITE")
    print("="*70)

    # Run tests
    solutions = test_ensemble_search()
    common_checkpoints = test_checkpoint_extraction(solutions)
    meta_path = test_meta_path_interpolation(solutions, common_checkpoints)
    diversity = test_strategy_diversity()
    test_performance_benchmarks()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)


if __name__ == '__main__':
    main()
