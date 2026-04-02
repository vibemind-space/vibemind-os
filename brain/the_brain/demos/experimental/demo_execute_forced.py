"""
Force 'execute' intervention to demonstrate exact tool call generation
"""
import json

from core.decision_router import DecisionRouter
from core.task_feature_router import TaskFeatureRouter

print("=" * 80)
print("EXECUTE INTERVENTION - Forced Demonstration")
print("=" * 80)
print()

# Initialize routers
task_router = TaskFeatureRouter(seed=42)
decision_router = DecisionRouter(
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    seed=42
)

print("Configured with 5 interventions: suggest, retry, wait, terminate, EXECUTE")
print()

# Test scenarios
test_cases = [
    {
        'task': 'Push all changes to GitHub main branch',
        'predicted_sequence': ['git_add', 'git_commit', 'git_push'],
        'confidence': 0.85,
        'task_type': 'github'
    },
    {
        'task': 'Deploy Docker container to production',
        'predicted_sequence': ['build_image', 'test_container', 'deploy'],
        'confidence': 0.75,
        'task_type': 'docker'
    },
    {
        'task': 'Check memory usage and generate report',
        'predicted_sequence': ['monitor_memory', 'check_logs', 'report_status'],
        'confidence': 0.90,
        'task_type': 'memory'
    }
]

for i, test_case in enumerate(test_cases, 1):
    print(f"=" * 80)
    print(f"TEST CASE {i}: {test_case['task']}")
    print("=" * 80)
    print()

    # Get task features
    layer1_state = task_router.route_task(test_case['task'])

    # Create Layer 2 prediction
    layer2_prediction = {
        'predicted_sequence': test_case['predicted_sequence'],
        'confidence': test_case['confidence'],
        'success_probability': 0.80,
        'dominant_modalities': ['tool_trace', 'temporal_pattern', 'success_signal'],
        'task_type': test_case['task_type']
    }

    # Get decision
    decision = decision_router.route_to_action(
        layer1_state=layer1_state,
        layer2_prediction=layer2_prediction
    )

    # Manually generate tool calls to show what 'execute' would provide
    print("Layer 2 Predicted Sequence:")
    for step, tool in enumerate(test_case['predicted_sequence'], 1):
        print(f"  {step}. {tool}")
    print()

    # Force generate executable tool calls
    tool_calls = decision_router._generate_executable_tool_calls(
        predicted_sequence=test_case['predicted_sequence'],
        task_type=test_case['task_type'],
        confidence=test_case['confidence']
    )

    print("IF INTERVENTION = 'execute', PROVIDES THESE EXACT TOOL CALLS:")
    print("-" * 80)
    print()

    for tool_call in tool_calls:
        print(f"STEP {tool_call['step']}: {tool_call['tool']}")
        print(f"  Confidence: {tool_call['confidence']:.1%}")
        print(f"  Task Type: {tool_call['task_type']}")
        print()

        if tool_call['parameters']:
            print(f"  Parameters:")
            for key, value in tool_call['parameters'].items():
                print(f"    {key}: {value}")
            print()

        print(f"  Execution Metadata:")
        print(f"    Required: {tool_call['metadata']['required']}")
        print(f"    Can skip: {tool_call['metadata']['can_skip']}")
        print(f"    Retry on error: {tool_call['metadata']['retry_on_error']}")
        print(f"    Timeout: {tool_call['metadata']['timeout_seconds']} seconds")
        print()

    # Show as JSON for easy integration
    print("JSON FORMAT (for API integration):")
    print("-" * 80)
    print(json.dumps(tool_calls, indent=2))
    print()

print("=" * 80)
print("SUMMARY")
print("=" * 80)
print()
print("EXECUTE INTERVENTION provides:")
print("  1. Exact tool names (e.g., 'git_add', 'docker_build')")
print("  2. Inferred parameters (e.g., files='.', tag='latest')")
print("  3. Execution metadata (timeouts, retry logic)")
print("  4. JSON-serializable format for API consumption")
print()
print("NEXT STEPS:")
print("  1. Train 10x5 routing matrix (not 10x4)")
print("  2. Add 'execute' training examples")
print("  3. Update production API to return executable tool calls")
print("  4. Integrate with actual tool execution engine")
print()
print("=" * 80)
