"""
Unified Brain Client
====================

Client library for services to connect to the unified brain instance.

Usage:
    from production.unified_brain_client import UnifiedBrainClient

    # Connect to unified brain
    client = UnifiedBrainClient(service_name='dashboard')

    # Make prediction
    result = client.predict("Deploy Docker container")

    # Call specific brain feature as tool
    memory = client.call_feature('memory_context', task="Deploy Docker")

    # Submit feedback
    client.submit_feedback(task, result['result'], success=True, user_rating=0.9)
"""

import requests
from typing import Dict, Any, Optional, List
import json


class UnifiedBrainClient:
    """Client for connecting to unified brain service"""

    def __init__(
        self,
        service_name: str,
        brain_url: str = "http://localhost:5003"
    ):
        """
        Initialize client

        Args:
            service_name: Name of the service (dashboard, api, swarm)
            brain_url: URL of unified brain service
        """
        self.service_name = service_name
        self.brain_url = brain_url
        self.session = requests.Session()

        # Register with unified brain
        self._register()

    def _register(self):
        """Register service with unified brain"""
        try:
            response = self.session.post(
                f"{self.brain_url}/register",
                json={'service_name': self.service_name},
                timeout=5
            )

            if response.status_code == 200:
                print(f"[{self.service_name}] [OK] Connected to unified brain at {self.brain_url}")
            else:
                print(f"[{self.service_name}] [WARN] Failed to register: {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"[{self.service_name}] [WARN] Could not connect to unified brain: {e}")
            print(f"[{self.service_name}] Make sure unified brain service is running at {self.brain_url}")

    def health_check(self) -> Dict[str, Any]:
        """Check unified brain health"""
        try:
            response = self.session.get(f"{self.brain_url}/health", timeout=5)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def predict(self, task: str) -> Dict[str, Any]:
        """
        Make prediction using unified brain

        Args:
            task: Task description

        Returns:
            Dictionary with prediction result
        """
        try:
            response = self.session.post(
                f"{self.brain_url}/predict",
                json={
                    'task': task,
                    'service_name': self.service_name
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def submit_feedback(
        self,
        task: str,
        prediction: Dict[str, Any],
        success: bool,
        user_rating: float,
        execution_time_ms: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Submit feedback to unified brain

        Args:
            task: Task description
            prediction: Prediction result from predict()
            success: Whether task succeeded
            user_rating: User rating (0-1)
            execution_time_ms: Execution time in milliseconds

        Returns:
            Dictionary with success status
        """
        try:
            response = self.session.post(
                f"{self.brain_url}/feedback",
                json={
                    'task': task,
                    'prediction': prediction,
                    'success': success,
                    'user_rating': user_rating,
                    'execution_time_ms': execution_time_ms,
                    'service_name': self.service_name
                },
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def get_statistics(self) -> Dict[str, Any]:
        """Get brain statistics"""
        try:
            response = self.session.get(f"{self.brain_url}/statistics", timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def get_brain_state(self) -> Dict[str, Any]:
        """Get current brain state"""
        try:
            response = self.session.get(f"{self.brain_url}/brain_state", timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def call_feature(
        self,
        feature: str,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a specific brain feature as a tool

        Args:
            feature: Feature name (memory_context, attention_state, etc.)
            task: Task description
            context: Optional context dictionary

        Returns:
            Dictionary with feature data
        """
        try:
            response = self.session.post(
                f"{self.brain_url}/feature_call",
                json={
                    'feature': feature,
                    'task': task,
                    'context': context or {},
                    'service_name': self.service_name
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def get_available_features(self) -> Dict[str, Any]:
        """Get list of all available brain features"""
        try:
            response = self.session.get(f"{self.brain_url}/available_features", timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}

        except requests.exceptions.RequestException as e:
            return {'error': str(e)}


# Example usage
if __name__ == '__main__':
    print("=" * 70)
    print("  UNIFIED BRAIN CLIENT - DEMO")
    print("=" * 70)
    print()

    # Connect to unified brain
    client = UnifiedBrainClient(service_name='demo')

    # Check health
    print("1. Health Check:")
    health = client.health_check()
    print(json.dumps(health, indent=2))
    print()

    # List available features
    print("2. Available Brain Features:")
    features = client.get_available_features()
    if 'features' in features:
        for feature, description in features['features'].items():
            print(f"   - {feature}: {description}")
    print()

    # Make prediction
    print("3. Make Prediction:")
    task = "Deploy Docker container with Redis and health monitoring"
    result = client.predict(task)
    if 'result' in result:
        pred = result['result']['prediction']
        print(f"   Task: {task}")
        print(f"   Primary Action: {pred['primary_action']}")
        print(f"   Confidence: {pred.get('confidence', 0.0):.2f}")
        print(f"   Task Type: {pred.get('task_type', 'unknown')}")
    print()

    # Call specific feature
    print("4. Call Memory Feature:")
    memory_result = client.call_feature('memory_context', task=task)
    if 'data' in memory_result:
        print(f"   Feature: {memory_result['feature']}")
        print(f"   Data: {str(memory_result['data'])[:100]}...")
    print()

    # Submit feedback
    print("5. Submit Feedback:")
    if 'result' in result:
        feedback_result = client.submit_feedback(
            task=task,
            prediction=result['result'],
            success=True,
            user_rating=0.9,
            execution_time_ms=2000.0
        )
        print(f"   Success: {feedback_result.get('success', False)}")
        print(f"   Message: {feedback_result.get('message', 'N/A')}")
    print()

    # Get statistics
    print("6. Get Statistics:")
    stats = client.get_statistics()
    if 'statistics' in stats:
        st = stats['statistics']
        print(f"   Total Predictions: {st.get('total_predictions', 0)}")
        print(f"   Success Rate: {st.get('success_rate', 0.0):.1%}")
        print(f"   Average Confidence: {st.get('average_confidence', 0.0):.2f}")
    print()

    print("=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
