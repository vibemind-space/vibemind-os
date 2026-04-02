"""
Meta-Cognitive Learning Demo

Demonstrates the self-reflective learning loop:
1. Load past conversation traces (39 sessions)
2. Train routing system to recognize failure patterns
3. Test on new traces to predict outcomes
4. Show which brain areas activate for different patterns
"""

import sys
sys.path.insert(0, 'C:\\Users\\User\\Desktop\\Tahlamus')

import numpy as np
from core.meta_router import MetaRouter
from core.conversation_trace_encoder import load_session_logs

print("="*80)
print("META-COGNITIVE LEARNING DEMONSTRATION")
print("="*80)
print()
print("This demo shows how the brain learns from past agentic conversations.")
print("We'll train on 39 real session logs and see if it can predict failures!")
print()

# Initialize meta-router
print("Initializing meta-cognitive routing system...")
meta_router = MetaRouter(
    enable_hippocampus=True,
    enable_meta_learning=True,
    novelty_threshold_meta=0.5,  # Encode failures as high-novelty
    memory_influence_meta=0.5,   # Strong influence from past failures
    seed=42
)
print("[OK] System initialized with 10 modalities (6 sensory + 4 trace modalities)")
print()

# Load training data
log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
print(f"Loading conversation traces from: {log_dir}")
print()

# Train on first 30 traces
print("="*80)
print("PHASE 1: TRAINING")
print("="*80)
meta_router.load_and_train(log_dir, limit=30, verbose=True)
print()

# Test on remaining traces
print("="*80)
print("PHASE 2: PREDICTION")
print("="*80)
print("Testing on unseen traces...")
print()

test_traces = load_session_logs(log_dir, limit=39)[30:]  # Last 9 traces

print(f"Testing on {len(test_traces)} unseen conversation traces:")
print()

for i, trace in enumerate(test_traces):
    features = trace.get_features()

    # Make prediction
    prediction = meta_router.predict_outcome(trace)

    print(f"[Test {i+1}] {trace.filename}")
    print(f"  Task: {features['task']}")
    print(f"  Duration: {features['duration_seconds']:.1f}s")
    print(f"  Actual Errors: {features['error_count']}")
    print(f"  Actual Outcome: {features['outcome']}")
    print(f"  -> Predicted Failure: {prediction['predicted_failure']}")
    print(f"  -> Error Gate Strength: {prediction['error_gate_strength']:.3f}")
    print(f"  -> Similar Cases Retrieved: {prediction['similar_cases_retrieved']}")

    # Check if prediction was correct
    actual_failure = not features['success']
    correct = prediction['predicted_failure'] == actual_failure
    print(f"  -> Prediction: {'[CORRECT]' if correct else '[WRONG]'}")
    print()

# Show final statistics
print("="*80)
print("FINAL STATISTICS")
print("="*80)
state = meta_router.get_state()
print(f"Total traces processed: {state['traces_processed']}")
print(f"Failures encoded: {state['failures_encoded']}")
print(f"Successes encoded: {state['successes_encoded']}")
print(f"Episodic memories stored: {state['thalamo_hippocampal_state']['hippocampal']['num_memories']}")
print()

print("="*80)
print("KEY INSIGHTS")
print("="*80)
print("- The hippocampus stores high-error traces as episodic memories")
print("- When a new trace arrives, similar past failures are retrieved")
print("- Error gate strength indicates predicted failure likelihood")
print("- This enables the system to recognize patterns like:")
print("  * 'Permission errors usually lead to task failure'")
print("  * 'User clarification + rejection = terminate early'")
print("  * 'High tool repetition (>5) suggests stuck loop'")
print()
print("The brain has learned from its own execution history!")
print("="*80)
