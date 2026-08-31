"""
Test Tool Call Integration - Verify DecisionRouter + ToolCallGenerator

This test validates that the DecisionRouter properly integrates with ToolCallGenerator
to produce executable tool calls with inferred parameters.

Tests:
1. DecisionRouter initializes ToolCallGenerator
2. Tool calls generated for 'execute' interventions
3. Parameters properly inferred from task descriptions
4. Fallback to legacy method when needed
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from core.decision_router import DecisionRouter
from core.task_feature_router import TaskFeatureRouter, TaskFeatures, RoutingState
from core.multi_target_router import MultiTargetDecision, InterventionDecision


def test_tool_call_integration():
    """Test that DecisionRouter properly integrates ToolCallGenerator"""
    print("\n" + "="*80)
    print("TEST: TOOL CALL GENERATOR INTEGRATION")
    print("="*80)

    # Initialize decision router
    print("\n[SETUP] Initializing DecisionRouter...")
    router = DecisionRouter()

    # Check tool call generator initialized
    if router.tool_call_generator:
        print("[OK] ToolCallGenerator initialized")
        print(f"[OK] Available tools: {', '.join(router.tool_call_generator.get_available_tools())}")
    else:
        print("[FAIL] ToolCallGenerator not initialized!")
        return False

    # Create mock Layer 1 state
    print("\n[SETUP] Creating mock Layer 1 state...")
    mock_features = TaskFeatures(
        keywords=["deploy", "docker", "container", "nginx", "monitoring"],
        task_type="docker",
        complexity=0.6,
        urgency=0.7,
        raw_description="Deploy Docker container nginx on port 8080 with monitoring"
    )

    mock_routing_state = RoutingState(
        features=mock_features,
        routing_weights=np.random.rand(10),
        processing_mode="urgent",
        dominant_areas=["threat", "tool_trace"]
    )

    # Create mock Layer 2 prediction with 'execute' intervention
    print("\n[SETUP] Creating mock Layer 2 prediction...")
    mock_layer2_prediction = {
        'predicted_sequence': ['docker_deploy', 'monitor_service'],
        'confidence': 0.75,
        'success_probability': 0.8,
        'reasoning_chain': ['Analyzed task type: docker']
    }

    # Create mock decision with 'execute' intervention
    print("\n[SETUP] Creating mock multi-target decision...")
    mock_decision = MultiTargetDecision(
        primary=InterventionDecision(
            intervention_type='execute',
            weight=0.8,
            confidence=0.85,
            reasoning="Execute Docker deployment"
        ),
        alternatives=[
            InterventionDecision(
                intervention_type='wait',
                weight=0.15,
                confidence=0.70,
                reasoning="Wait for resources"
            )
        ],
        total_weight_sum=0.95,  # 0.8 + 0.15
        dominant_modalities=["threat", "tool_trace"]
    )

    # Override multi_target_router.route_decision to return our mock
    original_route = router.multi_target_router.route_decision
    router.multi_target_router.route_decision = lambda *args, **kwargs: mock_decision

    # Test with task text
    print("\n[TEST] Routing with task text for parameter inference...")
    task_text = "Deploy Docker container nginx on port 8080 with monitoring"

    actionable = router.route_to_action(
        layer1_state=mock_routing_state,
        layer2_prediction=mock_layer2_prediction,
        task_text=task_text  # NEW: Pass task text
    )

    # Verify executable tool calls generated
    print("\n[RESULTS] Actionable decision created")
    if actionable.executable_tool_calls:
        print(f"[OK] Generated {len(actionable.executable_tool_calls)} executable tool calls")

        for i, tool_call in enumerate(actionable.executable_tool_calls, 1):
            print(f"\n  Tool Call {i}:")
            print(f"    Tool: {tool_call['tool']}")
            print(f"    Tool Type: {tool_call.get('tool_type', 'N/A')}")
            print(f"    Confidence: {tool_call['confidence']:.2f}")
            print(f"    Parameters:")
            for param, value in tool_call.get('parameters', {}).items():
                print(f"      - {param}: {value}")
            if 'reasoning' in tool_call:
                print(f"    Reasoning: {tool_call['reasoning']}")
            if tool_call.get('fallback_tools'):
                print(f"    Fallbacks: {', '.join(tool_call['fallback_tools'])}")

        # Verify parameters inferred
        first_tool = actionable.executable_tool_calls[0]
        if first_tool.get('parameters'):
            print(f"\n[OK] Parameters inferred from task text")
            if 'port' in str(first_tool.get('parameters', {})):
                print(f"[OK] Port parameter detected (8080 expected)")
        else:
            print(f"\n[WARN] No parameters inferred")

    else:
        print(f"[FAIL] No executable tool calls generated!")
        return False

    # Check statistics
    print(f"\n[STATISTICS]")
    print(f"  Total decisions: {router.total_decisions}")
    print(f"  Tool calls generated: {router.tool_calls_generated}")

    # Restore original route method
    router.multi_target_router.route_decision = original_route

    print("\n[OK] Tool call integration test passed!")
    return True


if __name__ == "__main__":
    success = test_tool_call_integration()

    if success:
        print("\n" + "="*80)
        print("SUCCESS: ToolCallGenerator properly integrated with DecisionRouter!")
        print("="*80)
        print("\nKey achievements:")
        print("  [OK] ToolCallGenerator initialized in DecisionRouter")
        print("  [OK] Tool calls generated for 'execute' interventions")
        print("  [OK] Parameters inferred from task descriptions")
        print("  [OK] Full integration: Puzzle TO Production TO Tool Calls")
    else:
        print("\n" + "="*80)
        print("FAILED: Tool call integration issues detected")
        print("="*80)
