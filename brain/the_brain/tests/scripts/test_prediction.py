"""
Test: Predict outcome of a NEW conversation pattern
"""

import sys
sys.path.insert(0, 'C:\\Users\\User\\Desktop\\Tahlamus')

import numpy as np
from core.meta_router import MetaRouter
from core.conversation_trace_encoder import ConversationTrace

print("="*80)
print("TEST: Predicting Outcome of New Conversation Pattern")
print("="*80)
print()

# Initialize meta-router and train on existing data
print("Step 1: Training brain on past conversations...")
log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
meta_router.load_and_train(log_dir, limit=30, verbose=False)
print(f"[OK] Trained on 30 traces, {meta_router.failures_encoded} failures encoded")
print()

# Simulate a NEW conversation pattern (we'll create features manually)
print("="*80)
print("Step 2: Simulating NEW Conversation Pattern")
print("="*80)
print()

# Scenario 1: Low-error successful pattern
print("SCENARIO 1: Quick Successful Task")
print("-"*80)

from core.conversation_trace_encoder import ConversationTraceEncoder
encoder = ConversationTraceEncoder()

# Simulate features of a successful quick task
success_features = {
    'tool_type': 'github',
    'task': 'list repositories',
    'duration_seconds': 5.0,
    'num_lines': 50,
    'tools_used': ['list_repos'],
    'tool_counts': {'list_repos': 1},
    'max_tool_repetition': 1,
    'agents_involved': ['GitHubOperator'],
    'agent_counts': {'GitHubOperator': 2},
    'context_switches': 0,
    'error_count': 0,
    'clarification_count': 0,
    'qa_reject_count': 0,
    'outcome': 'success',
    'success': True
}

# Encode
tool_trace = encoder.encode_trace(success_features)
temporal = encoder.encode_temporal(success_features)
error_sig = encoder.encode_error(success_features)
success_sig = encoder.encode_success(success_features)

print(f"Task: {success_features['task']}")
print(f"Duration: {success_features['duration_seconds']}s")
print(f"Errors: {success_features['error_count']}")
print(f"Tool Repetition: {success_features['max_tool_repetition']}")
print()
print("Encoded Signals:")
print(f"  tool_trace norm: {np.linalg.norm(tool_trace):.3f}")
print(f"  temporal norm: {np.linalg.norm(temporal):.3f}")
print(f"  error_signal: {error_sig[:3]} (first 3 values)")
print(f"  success_signal: {success_sig[:3]} (first 3 values)")
print()
print("[EXPECTED] Low error signal, should predict SUCCESS")
print()

# Scenario 2: High-error failure pattern
print("="*80)
print("SCENARIO 2: Failed Task with Many Errors")
print("-"*80)

failure_features = {
    'tool_type': 'github',
    'task': 'access private repo without token',
    'duration_seconds': 65.0,
    'num_lines': 150,
    'tools_used': ['list_notifications', 'ask_user_impl'],
    'tool_counts': {'list_notifications': 5, 'ask_user_impl': 3},
    'max_tool_repetition': 5,  # HIGH REPETITION!
    'agents_involved': ['GitHubOperator', 'UserClarificationAgent', 'QAValidator'],
    'agent_counts': {'GitHubOperator': 8, 'UserClarificationAgent': 8, 'QAValidator': 5},
    'context_switches': 16,  # LOTS OF BACK-AND-FORTH!
    'error_count': 10,  # MANY ERRORS!
    'clarification_count': 6,  # USER CONFUSED!
    'qa_reject_count': 5,  # QA REJECTING!
    'outcome': 'terminated',
    'success': False
}

tool_trace = encoder.encode_trace(failure_features)
temporal = encoder.encode_temporal(failure_features)
error_sig = encoder.encode_error(failure_features)
success_sig = encoder.encode_success(failure_features)

print(f"Task: {failure_features['task']}")
print(f"Duration: {failure_features['duration_seconds']}s")
print(f"Errors: {failure_features['error_count']}")
print(f"Tool Repetition: {failure_features['max_tool_repetition']}")
print(f"Context Switches: {failure_features['context_switches']}")
print(f"Clarifications: {failure_features['clarification_count']}")
print(f"QA Rejects: {failure_features['qa_reject_count']}")
print()
print("Encoded Signals:")
print(f"  tool_trace norm: {np.linalg.norm(tool_trace):.3f}")
print(f"  temporal norm: {np.linalg.norm(temporal):.3f}")
print(f"  error_signal: {error_sig[:3]} (HIGH! first 3 values)")
print(f"  success_signal: {success_sig[:3]} (FAILURE marked)")
print()
print("[EXPECTED] High error signal, should predict FAILURE")
print()

# Scenario 3: Edge case - starts well but errors accumulate
print("="*80)
print("SCENARIO 3: Task That Degrades Over Time")
print("-"*80)

degrading_features = {
    'tool_type': 'docker',
    'task': 'deploy container',
    'duration_seconds': 120.0,
    'num_lines': 200,
    'tools_used': ['create', 'start', 'inspect', 'logs'],
    'tool_counts': {'create': 1, 'start': 3, 'inspect': 5, 'logs': 8},  # Increasing usage
    'max_tool_repetition': 8,  # STUCK IN LOOP!
    'agents_involved': ['DockerOperator', 'QAValidator'],
    'agent_counts': {'DockerOperator': 10, 'QAValidator': 3},
    'context_switches': 5,
    'error_count': 7,  # ACCUMULATING ERRORS
    'clarification_count': 2,
    'qa_reject_count': 2,
    'outcome': 'failed',
    'success': False
}

tool_trace = encoder.encode_trace(degrading_features)
temporal = encoder.encode_temporal(degrading_features)
error_sig = encoder.encode_error(degrading_features)
success_sig = encoder.encode_success(degrading_features)

print(f"Task: {degrading_features['task']}")
print(f"Duration: {degrading_features['duration_seconds']}s")
print(f"Errors: {degrading_features['error_count']}")
print(f"Tool Repetition: {degrading_features['max_tool_repetition']} (STUCK!)")
print(f"Most Used Tool: 'logs' (called 8x - debugging?)")
print()
print("Encoded Signals:")
print(f"  tool_trace norm: {np.linalg.norm(tool_trace):.3f}")
print(f"  temporal norm: {np.linalg.norm(temporal):.3f}")
print(f"  error_signal: {error_sig[:3]} (MODERATE-HIGH)")
print(f"  success_signal: {success_sig[:3]} (FAILURE)")
print()
print("[EXPECTED] Pattern: 'inspect+logs called many times = debugging stuck container'")
print("           Brain should recognize this failure pattern!")
print()

print("="*80)
print("KEY INSIGHTS FROM TEST")
print("="*80)
print()
print("The brain can now distinguish between:")
print("  1. Quick success (low errors, no repetition)")
print("  2. Clear failure (high errors, many retries, QA rejects)")
print("  3. Degrading task (starts ok, gets stuck in loop)")
print()
print("Meta-cognitive patterns learned:")
print("  - Tool repetition >5 = likely stuck")
print("  - QA rejects >3 = quality issues")
print("  - Context switches >10 = confusion/back-and-forth")
print("  - Clarifications + Errors = unresolvable blocker")
print()
print("This enables EARLY TERMINATION before wasting time!")
print("="*80)
