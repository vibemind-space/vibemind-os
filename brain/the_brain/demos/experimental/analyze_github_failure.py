"""
Analyze the failed GitHub session in detail.
"""

import sys
sys.path.insert(0, 'C:\\Users\\User\\Desktop\\Tahlamus')

from core.conversation_trace_encoder import ConversationTrace, ConversationTraceEncoder

# Load the github trace
trace = ConversationTrace(r'C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions\github_20251009_000258_5ClQAS3eT-v3HfJqptO0XQ.log')
with open(trace.log_path, 'r', encoding='utf-8', errors='ignore') as f:
    trace.parse(f.read())

features = trace.get_features()

print('='*80)
print('GITHUB SESSION ANALYSIS (Failed Task)')
print('='*80)
print(f'Task: {features["task"]}')
print(f'Duration: {features["duration_seconds"]:.1f}s')
print(f'Lines: {features["num_lines"]}')
print(f'Tools Used: {features["tools_used"]}')
print(f'Tool Counts: {features["tool_counts"]}')
print(f'Max Tool Repetition: {features["max_tool_repetition"]}')
print(f'Agents: {features["agents_involved"]}')
print(f'Agent Counts: {features["agent_counts"]}')
print(f'Context Switches: {features["context_switches"]}')
print(f'Errors: {features["error_count"]}')
print(f'Clarifications: {features["clarification_count"]}')
print(f'QA Rejects: {features["qa_reject_count"]}')
print(f'Outcome: {features["outcome"]}')
print(f'Success: {features["success"]}')

# Encode
encoder = ConversationTraceEncoder()
encoded = encoder.encode_full(trace)

print()
print('='*80)
print('ENCODED VECTORS (for routing system):')
print('='*80)
print(f'tool_trace (64d): {encoded["tool_trace"][:10]}...')
print(f'temporal_pattern (32d): {encoded["temporal_pattern"][:5]}...')
print(f'error_signal (16d): {encoded["error_signal"]}')
print(f'success_signal (8d): {encoded["success_signal"]}')

print()
print('='*80)
print('KEY INSIGHTS:')
print('='*80)
print(f'• Task repeatedly failed due to permission error (403)')
print(f'• User clarification requested but user could not provide token')
print(f'• QA Validator rejected output {features["qa_reject_count"]} times')
print(f'• Agent kept retrying same approach (repetition = {features["max_tool_repetition"]})')
print(f'• Should have terminated earlier based on user response')
print()
print('This pattern should be encoded to hippocampus to learn:')
print('  "When user cannot provide auth → terminate immediately"')
