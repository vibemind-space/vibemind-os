"""
Example Client for Tahlamus Production API

Shows how to integrate the Tahlamus API into your application
"""

import requests
import json
from typing import Dict, Optional


class TahlamusClient:
    """Client for Tahlamus Production API"""

    def __init__(self, base_url: str = "http://localhost:5001"):
        """
        Initialize client

        Args:
            base_url: Base URL of the API server
        """
        self.base_url = base_url

    def predict(self, task: str) -> Dict:
        """
        Get prediction for a task

        Args:
            task: Task description

        Returns:
            Prediction result dict
        """
        response = requests.post(
            f"{self.base_url}/predict",
            json={'task': task}
        )
        response.raise_for_status()
        return response.json()

    def submit_feedback(
        self,
        task: str,
        prediction: Dict,
        actual_action: Optional[str] = None,
        success: bool = True,
        user_rating: Optional[float] = None,
        execution_time_ms: Optional[float] = None
    ) -> Dict:
        """
        Submit feedback for a prediction

        Args:
            task: Original task
            prediction: Prediction dict from predict()
            actual_action: What action was actually taken
            success: Whether it was successful
            user_rating: User satisfaction (0-1)
            execution_time_ms: Execution time

        Returns:
            Response dict
        """
        response = requests.post(
            f"{self.base_url}/feedback",
            json={
                'task': task,
                'prediction': prediction,
                'actual_action': actual_action,
                'success': success,
                'user_rating': user_rating,
                'execution_time_ms': execution_time_ms
            }
        )
        response.raise_for_status()
        return response.json()

    def get_stats(self) -> Dict:
        """Get system statistics"""
        response = requests.get(f"{self.base_url}/stats")
        response.raise_for_status()
        return response.json()

    def list_matrices(self) -> Dict:
        """List available matrix versions"""
        response = requests.get(f"{self.base_url}/matrices")
        response.raise_for_status()
        return response.json()

    def save_matrix(self, version_name: Optional[str] = None, notes: str = "") -> Dict:
        """Save current matrix"""
        response = requests.post(
            f"{self.base_url}/save_matrix",
            json={'version_name': version_name, 'notes': notes}
        )
        response.raise_for_status()
        return response.json()


def main():
    """Example usage"""
    print("=" * 70)
    print("TAHLAMUS CLIENT EXAMPLE")
    print("=" * 70)
    print()

    # Initialize client
    client = TahlamusClient()

    # Example 1: Simple prediction
    print("Example 1: Simple Prediction")
    print("-" * 70)

    task = "Deploy with Docker immediately"
    print(f"Task: {task}")

    result = client.predict(task)

    print(f"Primary Action: {result['prediction']['primary_action']}")
    print(f"Confidence: {result['prediction']['confidence']:.1%}")
    print(f"Weight: {result['prediction']['primary_weight']:.1%}")
    print(f"Reasoning: {result['prediction']['primary_reasoning']}")
    print()

    # Example 2: Prediction with feedback
    print("Example 2: Prediction with Feedback")
    print("-" * 70)

    task = "Fix critical bug in authentication"
    print(f"Task: {task}")

    result = client.predict(task)
    print(f"Predicted: {result['prediction']['primary_action']}")

    # Simulate execution
    actual_action = result['prediction']['primary_action']
    success = True
    user_rating = 0.85

    print(f"Executed: {actual_action}")
    print(f"Success: {success}")
    print(f"Rating: {user_rating}")

    # Submit feedback
    feedback_response = client.submit_feedback(
        task=task,
        prediction=result,
        actual_action=actual_action,
        success=success,
        user_rating=user_rating
    )

    print(f"Feedback submitted: {feedback_response['message']}")
    print()

    # Example 3: Get statistics
    print("Example 3: System Statistics")
    print("-" * 70)

    stats = client.get_stats()

    print(f"Total Predictions: {stats['total_predictions']}")
    print(f"Total Feedback: {stats['total_feedback']}")
    print(f"Current Matrix: {stats['current_matrix_version']}")
    print(f"Recent Accuracy: {stats['recent_accuracy']:.1%}")
    print(f"Avg Confidence: {stats['recent_avg_confidence']:.3f}")
    print()

    # Example 4: List matrices
    print("Example 4: Available Matrices")
    print("-" * 70)

    matrices_response = client.list_matrices()

    for matrix in matrices_response['matrices'][:3]:  # Show top 3
        print(f"{matrix['version']}:")
        print(f"  Accuracy: {matrix['accuracy']:.1%}")
        print(f"  Predictions: {matrix['num_predictions']}")
        print(f"  Confidence: {matrix['avg_confidence']:.3f}")
        print(f"  Notes: {matrix['notes']}")
        print()

    print("=" * 70)
    print("EXAMPLES COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to API server.")
        print("Make sure the server is running:")
        print("  python production/api_server.py")
    except Exception as e:
        print(f"Error: {e}")
