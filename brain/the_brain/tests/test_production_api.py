"""
Test Production API with direct curl-like requests

NOTE: This test requires the production API server to be running on port 5001.
Run it manually with: python tests/test_production_api.py
"""

import requests
import json

BASE_URL = "http://localhost:5001"


def main():
    """Run production API tests."""
    print("=" * 70)
    print("TESTING TAHLAMUS PRODUCTION API")
    print("=" * 70)
    print()

    # Test 1: Health check
    print("1. Health Check")
    print("-" * 70)
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

    # Test 2: Make predictions
    print("2. Making Predictions")
    print("-" * 70)

    test_tasks = [
        "Deploy with Docker urgently",
        "git commit and push to GitHub",
        "Critical database failure - immediate action needed",
        "Routine memory status check"
    ]

    results = []

    for i, task in enumerate(test_tasks, 1):
        print(f"\nTask {i}: \"{task}\"")

        response = requests.post(
            f"{BASE_URL}/predict",
            json={'task': task}
        )

        result = response.json()
        results.append(result)

        pred = result['prediction']
        print(f"  Primary: {pred['primary_action']} ({pred['primary_weight']:.1%})")
        print(f"  Confidence: {pred['confidence']:.1%}")
        print(f"  Mode: {pred['processing_mode']}")
        print(f"  Reasoning: {pred['primary_reasoning']}")

        # Show alternatives
        print(f"  Alternatives:")
        for alt in pred['alternatives'][:2]:
            print(f"    - {alt['action']}: {alt['weight']:.1%}")

    print()
    print()

    # Test 3: Submit feedback
    print("3. Submitting Feedback")
    print("-" * 70)

    for i, (task, result) in enumerate(zip(test_tasks[:2], results[:2]), 1):
        print(f"\nFeedback {i}: {task}")

        # Simulate execution
        success = True
        rating = 0.8 + (i * 0.05)  # 0.85, 0.90

        feedback_response = requests.post(
            f"{BASE_URL}/feedback",
            json={
                'task': task,
                'prediction': result,
                'actual_action': result['prediction']['primary_action'],
                'success': success,
                'user_rating': rating
            }
        )

        fb_result = feedback_response.json()
        print(f"  Success: {success}, Rating: {rating:.2f}")
        print(f"  Response: {fb_result['message']}")
        print(f"  Total feedback: {fb_result['total_feedback']}")

    print()
    print()

    # Test 4: Get statistics
    print("4. System Statistics")
    print("-" * 70)

    response = requests.get(f"{BASE_URL}/stats")
    stats = response.json()

    print(f"Total Predictions: {stats['total_predictions']}")
    print(f"Total Feedback: {stats['total_feedback']}")
    print(f"Feedback Rate: {stats['total_feedback']/stats['total_predictions']:.1%}")
    print(f"Current Matrix: {stats['current_matrix_version']}")
    print(f"Recent Accuracy: {stats['recent_accuracy']:.1%}")
    print(f"Avg Confidence: {stats['recent_avg_confidence']:.3f}")
    print(f"Continuous Learning: {stats['continuous_learning_enabled']}")

    print()
    print()

    # Test 5: List matrices
    print("5. Available Matrices")
    print("-" * 70)

    response = requests.get(f"{BASE_URL}/matrices")
    matrices_data = response.json()

    if matrices_data['matrices']:
        for matrix in matrices_data['matrices']:
            print(f"\n{matrix['version']}:")
            print(f"  Accuracy: {matrix.get('accuracy', 0):.1%}")
            print(f"  Predictions: {matrix.get('num_predictions', 0)}")
            print(f"  Confidence: {matrix.get('avg_confidence', 0):.3f}")
            print(f"  Notes: {matrix.get('notes', 'N/A')}")
    else:
        print("No matrices found")

    print()
    print()

    # Test 6: Advanced prediction with reasoning chain
    print("6. Detailed Prediction with Full Reasoning")
    print("-" * 70)

    task = "URGENT: Production deployment failure - critical bug"
    print(f"Task: \"{task}\"")
    print()

    response = requests.post(
        f"{BASE_URL}/predict",
        json={'task': task}
    )

    result = response.json()

    print("PREDICTION DETAILS:")
    print(f"  Task Type: {result['prediction']['task_type']}")
    print(f"  Complexity: {result['prediction']['complexity']:.2f}")
    print(f"  Urgency: {result['prediction']['urgency']:.2f}")
    print(f"  Processing Mode: {result['prediction']['processing_mode']}")
    print()

    print("PRIMARY DECISION:")
    print(f"  Action: {result['prediction']['primary_action']}")
    print(f"  Weight: {result['prediction']['primary_weight']:.1%}")
    print(f"  Confidence: {result['prediction']['confidence']:.1%}")
    print(f"  Reasoning: {result['prediction']['primary_reasoning']}")
    print()

    print("BRAIN STATE:")
    print(f"  Dominant Modalities: {', '.join(result['brain_state']['dominant_modalities'])}")
    if result['brain_state']['gates']:
        modalities = ['vision', 'audio', 'touch', 'taste', 'vestibular',
                     'threat', 'tool_trace', 'temporal', 'error', 'success']
        gates = result['brain_state']['gates']
        print("  Gate Values:")
        for mod, gate in zip(modalities, gates):
            if gate > 0.15:  # Only show significant activations
                bar = '#' * int(gate * 40)
                print(f"    {mod:15s} {gate:.3f} {bar}")
    print()

    print("REASONING CHAIN:")
    for i, step in enumerate(result['reasoning_chain'][:8], 1):
        print(f"  {i}. {step}")

    print()
    print("=" * 70)
    print("ALL TESTS COMPLETE!")
    print("=" * 70)
    print()
    print("The API is working perfectly!")
    print("You can now integrate this into any application using HTTP requests.")


if __name__ == "__main__":
    main()
