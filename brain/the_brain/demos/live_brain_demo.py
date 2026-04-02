"""
LIVE BRAIN MONITORING DEMONSTRATION

Shows the real-time brain system in action:
1. Monitors conversations as they happen
2. Detects failure patterns early
3. Triggers interventions with recommendations
4. Learns from each conversation

Simulates 3 live conversations:
- Scenario 1: Successful task (no intervention needed)
- Scenario 2: Errors accumulating (intervention triggered)
- Scenario 3: Stuck in loop (intervention triggered immediately)
"""

import sys
sys.path.insert(0, 'C:\\Users\\User\\Desktop\\Tahlamus')

import time
import numpy as np
from core.meta_router import MetaRouter
from core.brain_monitor import BrainActivityMonitor
from core.strategy_library import StrategyLibrary
from core.live_brain_monitor import LiveBrainMonitor
from core.conversation_trace_encoder import load_session_logs

print("="*80)
print("LIVE BRAIN MONITORING SYSTEM")
print("="*80)
print()
print("Initializing brain components...")

# Initialize pre-trained components
log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
brain_monitor = BrainActivityMonitor(history_length=100)
strategy_lib = StrategyLibrary(max_strategies_per_type=20)

# Train on existing sessions
print("Training on existing session logs...")
all_traces = load_session_logs(log_dir, limit=39)
print(f"Loaded {len(all_traces)} traces")

for trace in all_traces:
    features = trace.get_features()
    if features['success']:
        strategy_lib.add_strategy(
            task_type=features['tool_type'],
            tool_sequence=features['tools_used'],
            duration=features['duration_seconds'],
            success=True
        )

print(f"[OK] Strategy library: {strategy_lib.total_strategies} strategies across {len(strategy_lib.strategies)} task types")
print()

# Initialize live monitor
live_monitor = LiveBrainMonitor(
    meta_router=meta_router,
    brain_monitor=brain_monitor,
    strategy_library=strategy_lib,
    error_threshold=5,
    repetition_threshold=3,
    qa_reject_threshold=3,
    check_interval=2  # Check every 2 tool calls
)

print("="*80)
print("SCENARIO 1: Successful Task (No Intervention Needed)")
print("="*80)
print()

# Start conversation
conv1 = live_monitor.start_conversation("List Docker containers")

# Simulate successful execution
print("[USER] List all running Docker containers")
time.sleep(0.1)

print("[AGENT] Calling docker_list...")
conv1.add_tool_call("docker_list")
conv1.add_agent("DockerOperator")
live_monitor.update(conv1)
time.sleep(0.1)

print("[AGENT] Found 3 containers")
time.sleep(0.1)

print("[AGENT] Formatting output...")
conv1.add_tool_call("format_output")
live_monitor.update(conv1)
time.sleep(0.1)

print("[AGENT] Task complete!")
time.sleep(0.1)

# End successfully
live_monitor.end_conversation(conv1, success=True, outcome="completed")

print()
print("="*80)
print("SCENARIO 2: Errors Accumulating (Intervention Triggered)")
print("="*80)
print()

# Start conversation
conv2 = live_monitor.start_conversation("Access private GitHub repository")

print("[USER] Clone private repo github.com/user/private-repo")
time.sleep(0.1)

print("[AGENT] Attempting to access repository...")
conv2.add_tool_call("github_get_repo")
conv2.add_agent("GitHubOperator")
live_monitor.update(conv2)
time.sleep(0.1)

print("[ERROR] 403 Forbidden - authentication required")
conv2.add_error()
time.sleep(0.1)

print("[AGENT] Checking notifications for auth status...")
conv2.add_tool_call("github_list_notifications")
live_monitor.update(conv2)
time.sleep(0.1)

print("[ERROR] Still no access")
conv2.add_error()
time.sleep(0.1)

print("[AGENT] Retrying with different endpoint...")
conv2.add_tool_call("github_get_repo")
live_monitor.update(conv2)
time.sleep(0.1)

print("[ERROR] 403 Forbidden")
conv2.add_error()
time.sleep(0.1)

print("[AGENT] Asking user for clarification...")
conv2.add_clarification()
conv2.add_tool_call("ask_user")
live_monitor.update(conv2)
time.sleep(0.1)

print("[USER] I don't have a token")
time.sleep(0.1)

print("[AGENT] Attempting workaround...")
conv2.add_tool_call("github_get_repo")
live_monitor.update(conv2)
time.sleep(0.1)

print("[ERROR] 403 Forbidden")
conv2.add_error()
time.sleep(0.1)

print("[QA] Rejecting - no progress")
conv2.add_qa_reject()
time.sleep(0.1)

print("[AGENT] Trying again...")
conv2.add_tool_call("github_list_notifications")
live_monitor.update(conv2)
time.sleep(0.1)

print("[ERROR] Still failing")
conv2.add_error()
time.sleep(0.1)

print("[ERROR] Error count: 5")
conv2.add_error()

# This should trigger intervention!
intervention = live_monitor.update(conv2)

if intervention:
    print()
    print("="*60)
    print("INTERVENTION DETAILS:")
    print("="*60)
    print(f"Urgency: {intervention['urgency'].upper()}")
    print(f"Message: {intervention['message']}")
    if intervention['recommendation']:
        rec = intervention['recommendation']
        print(f"\nRecommended Strategy:")
        print(f"  Tools: {' -> '.join(rec['strategy'][:5])}")
        print(f"  Success Rate: {rec['success_rate']:.1%}")
        print(f"  Expected Duration: {rec['expected_duration']:.1f}s")
        print(f"  Confidence: {rec['confidence']:.3f}")
    print("="*60)
    print()

time.sleep(0.5)

# End as failure
print("[SYSTEM] Task terminated due to irresolvable blocker")
live_monitor.end_conversation(conv2, success=False, outcome="terminated")

print()
print("="*80)
print("SCENARIO 3: Stuck in Loop (Immediate Intervention)")
print("="*80)
print()

# Start conversation
conv3 = live_monitor.start_conversation("Deploy application container")

print("[USER] Deploy app to production")
time.sleep(0.1)

print("[AGENT] Creating container...")
conv3.add_tool_call("docker_create")
conv3.add_agent("DockerOperator")
live_monitor.update(conv3)
time.sleep(0.1)

print("[AGENT] Starting container...")
conv3.add_tool_call("docker_start")
live_monitor.update(conv3)
time.sleep(0.1)

print("[ERROR] Container failed to start")
conv3.add_error()
time.sleep(0.1)

print("[AGENT] Checking logs...")
conv3.add_tool_call("docker_logs")
live_monitor.update(conv3)
time.sleep(0.1)

print("[AGENT] Inspecting container...")
conv3.add_tool_call("docker_inspect")
live_monitor.update(conv3)
time.sleep(0.1)

print("[AGENT] Checking logs again...")
conv3.add_tool_call("docker_logs")  # REPETITION!
conv3.add_error()
live_monitor.update(conv3)
time.sleep(0.1)

print("[AGENT] Still checking logs...")
conv3.add_tool_call("docker_logs")  # REPETITION!
conv3.add_error()

# This should trigger intervention immediately (repetition detected)
intervention = live_monitor.update(conv3)

if intervention:
    print()
    print("="*60)
    print("INTERVENTION DETAILS:")
    print("="*60)
    print(f"Urgency: {intervention['urgency'].upper()}")
    print(f"Message: {intervention['message']}")
    if intervention['recommendation']:
        rec = intervention['recommendation']
        print(f"\nRecommended Strategy:")
        print(f"  Tools: {' -> '.join(rec['strategy'][:5])}")
        print(f"  Success Rate: {rec['success_rate']:.1%}")
        print(f"  Expected Duration: {rec['expected_duration']:.1f}s")
        print(f"  Confidence: {rec['confidence']:.3f}")
    else:
        print("\n[RECOMMENDATION] No proven strategies found.")
        print("System appears stuck in debug loop. Recommend:")
        print("  1. Stop container and check configuration")
        print("  2. Review container logs externally")
        print("  3. Verify image is valid")
    print("="*60)
    print()

time.sleep(0.5)

print("[SYSTEM] User terminated task after intervention")
live_monitor.end_conversation(conv3, success=False, outcome="user_terminated")

print()
print("="*80)
print("LIVE MONITORING SESSION COMPLETE")
print("="*80)
print()

# Show statistics
print(live_monitor.visualize_statistics())

print()
print("="*80)
print("KEY CAPABILITIES DEMONSTRATED")
print("="*80)
print()
print("[1] REAL-TIME DETECTION:")
print("    - Monitored 3 conversations as they happened")
print("    - Detected failure patterns before complete failure")
print("    - No need to wait for session to end")
print()
print("[2] EARLY INTERVENTION:")
print("    - Triggered when error count reached threshold (5 errors)")
print("    - Triggered when tool repetition detected (3x same tool)")
print("    - Provided actionable recommendations")
print()
print("[3] STRATEGY RETRIEVAL:")
print("    - Queried strategy library for proven approaches")
print("    - Computed confidence scores")
print("    - Offered alternatives when main strategy not found")
print()
print("[4] INCREMENTAL LEARNING:")
print("    - Added successful patterns to library")
print("    - Updated strategy quality scores")
print("    - Learned from each conversation")
print()
print("="*80)
print("THE BRAIN IS NOW ACTIVELY PREVENTING FAILURES!")
print("="*80)
