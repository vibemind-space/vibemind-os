"""
Test conversation trace parser on real session logs.
"""

import sys
sys.path.insert(0, 'C:\\Users\\User\\Desktop\\Tahlamus')

from core.conversation_trace_encoder import load_session_logs, ConversationTraceEncoder
import numpy as np

# Load session logs
print("Loading session logs...")
log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
traces = load_session_logs(log_dir, limit=10)  # Load first 10 for testing

print(f"\nLoaded {len(traces)} conversation traces\n")
print("="*80)

# Initialize encoder
encoder = ConversationTraceEncoder()

# Analyze each trace
for i, trace in enumerate(traces):
    print(f"\n[Trace {i+1}] {trace.filename}")
    print("-"*80)

    features = trace.get_features()

    print(f"Tool Type: {features['tool_type']}")
    print(f"Task: {features['task']}")
    print(f"Duration: {features['duration_seconds']:.1f}s")
    print(f"Lines: {features['num_lines']}")
    print(f"Tools Used: {features['tools_used']}")
    print(f"Max Tool Repetition: {features['max_tool_repetition']}")
    print(f"Agents: {features['agents_involved']}")
    print(f"Context Switches: {features['context_switches']}")
    print(f"Errors: {features['error_count']}")
    print(f"Clarifications: {features['clarification_count']}")
    print(f"QA Rejects: {features['qa_reject_count']}")
    print(f"Outcome: {features['outcome']}")
    print(f"Success: {features['success']}")

    # Encode as vectors
    encoded = encoder.encode_full(trace)

    print(f"\nEncoded Vectors:")
    print(f"  tool_trace: {encoded['tool_trace'].shape} - norm: {np.linalg.norm(encoded['tool_trace']):.3f}")
    print(f"  temporal_pattern: {encoded['temporal_pattern'].shape} - norm: {np.linalg.norm(encoded['temporal_pattern']):.3f}")
    print(f"  error_signal: {encoded['error_signal'].shape} - norm: {np.linalg.norm(encoded['error_signal']):.3f}")
    print(f"  success_signal: {encoded['success_signal'].shape} - norm: {np.linalg.norm(encoded['success_signal']):.3f}")

    print("="*80)

# Summary statistics
print("\n" + "="*80)
print("SUMMARY STATISTICS")
print("="*80)

tool_types = [t.get_features()['tool_type'] for t in traces]
outcomes = [t.get_features()['outcome'] for t in traces]
durations = [t.get_features()['duration_seconds'] for t in traces]

print(f"\nTool Types: {set(tool_types)}")
print(f"Outcomes: {set(outcomes)}")
print(f"Avg Duration: {np.mean(durations):.1f}s")
print(f"Max Duration: {np.max(durations):.1f}s")
print(f"Min Duration: {np.min(durations):.1f}s")

success_rate = sum(1 for o in outcomes if o not in ['failed', 'terminated']) / len(outcomes)
print(f"Success Rate: {success_rate*100:.1f}%")
