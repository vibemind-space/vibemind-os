"""
Demonstrate Continuous Learning in Production

Shows how the routing matrix improves over time with real feedback
"""

import requests
import json
import time

BASE_URL = "http://localhost:5001"

print("=" * 70)
print("CONTINUOUS LEARNING DEMONSTRATION")
print("=" * 70)
print()
print("This demo shows how the system learns from feedback in real-time.")
print("We'll submit the same task multiple times with feedback,")
print("and watch the predictions improve!")
print()

# Test task: Something that should trigger "retry" action
test_task = "Error: Connection timeout - database unreachable"

print(f"Test Task: '{test_task}'")
print()
print("Expected Behavior:")
print("  - High error_signal gate (connection error)")
print("  - Should learn to prefer 'retry' action")
print("  - Confidence should increase over iterations")
print()

# Get initial stats
initial_stats = requests.get(f"{BASE_URL}/stats").json()
print(f"Initial Stats:")
print(f"  Total Predictions: {initial_stats['total_predictions']}")
print(f"  Total Feedback: {initial_stats['total_feedback']}")
print(f"  Recent Accuracy: {initial_stats['recent_accuracy']:.1%}")
print()

print("-" * 70)
print("LEARNING ITERATIONS")
print("-" * 70)
print()

num_iterations = 10
predictions_history = []

for i in range(1, num_iterations + 1):
    print(f"Iteration {i}/{num_iterations}")
    print("-" * 40)

    # Make prediction
    response = requests.post(
        f"{BASE_URL}/predict",
        json={'task': test_task}
    )
    result = response.json()
    pred = result['prediction']

    # Show prediction
    print(f"  Predicted: {pred['primary_action']}")
    print(f"  Weight: {pred['primary_weight']:.1%}")
    print(f"  Confidence: {pred['confidence']:.1%}")

    # Store for comparison
    predictions_history.append({
        'iteration': i,
        'action': pred['primary_action'],
        'weight': pred['primary_weight'],
        'confidence': pred['confidence']
    })

    # Show brain state
    brain_state = result['brain_state']
    if brain_state['gates']:
        modalities = ['vision', 'audio', 'touch', 'taste', 'vestibular',
                     'threat', 'tool_trace', 'temporal', 'error', 'success']
        gates = brain_state['gates']

        # Show top 3 active gates
        gate_pairs = [(mod, g) for mod, g in zip(modalities, gates) if g > 0.1]
        gate_pairs.sort(key=lambda x: x[1], reverse=True)

        print(f"  Top Gates: ", end="")
        print(", ".join([f"{mod}={g:.2f}" for mod, g in gate_pairs[:3]]))

    # Submit feedback that "retry" was the correct action
    correct_action = "retry"
    is_correct = (pred['primary_action'] == correct_action)

    # Feedback strength based on correctness
    user_rating = 0.9 if is_correct else 0.3

    feedback_response = requests.post(
        f"{BASE_URL}/feedback",
        json={
            'task': test_task,
            'prediction': result,
            'actual_action': correct_action,
            'success': True,
            'user_rating': user_rating
        }
    )

    print(f"  Feedback: actual={correct_action}, rating={user_rating:.1f}")
    print(f"  Match: {'YES' if is_correct else 'NO'}")
    print()

    # Small delay to see progress
    time.sleep(0.5)

print()
print("=" * 70)
print("LEARNING PROGRESS SUMMARY")
print("=" * 70)
print()

# Show how predictions changed over time
print("Prediction Evolution:")
print(f"{'Iter':<6} {'Action':<12} {'Weight':<10} {'Confidence':<12}")
print("-" * 40)

for h in predictions_history:
    marker = " <-- CORRECT" if h['action'] == 'retry' else ""
    print(f"{h['iteration']:<6} {h['action']:<12} {h['weight']:<10.1%} {h['confidence']:<12.1%}{marker}")

print()

# Calculate improvement
first_pred = predictions_history[0]
last_pred = predictions_history[-1]

print("Improvement Analysis:")
print(f"  First iteration:")
print(f"    Action: {first_pred['action']}")
print(f"    Weight: {first_pred['weight']:.1%}")
print(f"    Confidence: {first_pred['confidence']:.1%}")
print()
print(f"  Last iteration:")
print(f"    Action: {last_pred['action']}")
print(f"    Weight: {last_pred['weight']:.1%}")
print(f"    Confidence: {last_pred['confidence']:.1%}")
print()

# Check if learning occurred
weight_change = last_pred['weight'] - first_pred['weight']
confidence_change = last_pred['confidence'] - first_pred['confidence']

if last_pred['action'] == 'retry':
    print("  Result: LEARNED SUCCESSFULLY!")
    print(f"    The system learned to prefer 'retry' for this error type")
else:
    print(f"  Result: LEARNING IN PROGRESS")
    print(f"    System needs more feedback to converge")

print(f"  Weight change: {weight_change:+.1%}")
print(f"  Confidence change: {confidence_change:+.1%}")
print()

# Get final stats
final_stats = requests.get(f"{BASE_URL}/stats").json()
print("Final Stats:")
print(f"  Total Predictions: {final_stats['total_predictions']}")
print(f"  Total Feedback: {final_stats['total_feedback']}")
print(f"  Recent Accuracy: {final_stats['recent_accuracy']:.1%}")
print(f"  Feedback collected: +{final_stats['total_feedback'] - initial_stats['total_feedback']}")
print()

print("=" * 70)
print("CONTINUOUS LEARNING DEMONSTRATION COMPLETE")
print("=" * 70)
print()
print("Key Takeaways:")
print("  1. System updates routing matrix after each feedback")
print("  2. Learning rate is conservative (0.005) for stability")
print("  3. More feedback -> better predictions")
print("  4. Matrix can be saved at any point for version control")
print()
print("Try different task types to see different learning patterns!")
