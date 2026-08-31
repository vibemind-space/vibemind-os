"""
Task Feature Router (Phase 4 - Layer 1)

Concept from logical_brain/routed_brain.py:
Extract task features and route to specialized processing areas.

Original PyTorch implementation:
```python
class SensoryRouter(nn.Module):
    def route_sensory(self, inputs):
        # Extract features from sensory inputs
        features = self.feature_extractor(inputs)

        # Route to specialized areas
        routing_weights = self.routing_network(features)

        return routing_weights, features
```

Our NumPy adaptation:
- Extract features from task description (keywords, type, complexity, urgency)
- Compute routing weights to brain areas
- Determine processing mode based on task characteristics
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class TaskFeatures:
    """
    Extracted features from a task description
    """
    keywords: List[str]           # Key terms in task
    task_type: str                # Inferred type (e.g., 'memory', 'docker', 'github')
    complexity: float             # Estimated complexity (0-1)
    urgency: float                # Estimated urgency (0-1)
    raw_description: str          # Original task text

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'keywords': self.keywords,
            'task_type': self.task_type,
            'complexity': float(self.complexity),
            'urgency': float(self.urgency),
            'raw_description': self.raw_description
        }


@dataclass
class RoutingState:
    """
    Routing state from Layer 1 to Layer 2
    """
    features: TaskFeatures
    routing_weights: np.ndarray   # Weights to brain areas [10]
    processing_mode: str          # 'urgent', 'analytical', 'creative', 'routine'
    dominant_areas: List[str]     # Top brain areas for this task

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        weights = self.routing_weights
        if hasattr(weights, 'tolist'):
            weights = weights.tolist()
        return {
            'features': self.features.to_dict(),
            'routing_weights': weights,
            'processing_mode': self.processing_mode,
            'dominant_areas': self.dominant_areas
        }


class TaskFeatureRouter:
    """
    Layer 1: Routes task features to specialized processing areas

    Extracts features from task descriptions and computes initial routing
    weights to brain areas, setting up the processing mode for Layer 2.
    """

    def __init__(
        self,
        modalities: Optional[List[str]] = None,
        seed: int = 42
    ):
        """
        Initialize task feature router

        Args:
            modalities: List of brain modality names
            seed: Random seed
        """
        self.rng = np.random.RandomState(seed)

        # Default modalities (same as meta_router)
        if modalities is None:
            modalities = [
                'vision', 'audio', 'touch', 'taste', 'vestibular',
                'threat', 'tool_trace', 'temporal_pattern',
                'error_signal', 'success_signal'
            ]

        self.modalities = modalities
        self.num_modalities = len(modalities)

        # Task type patterns (regex patterns for classification)
        self.task_patterns = {
            'memory': r'\b(memory|status|check|monitor|dashboard|metrics)\b',
            'docker': r'\b(docker|container|deploy|build|image)\b',
            'github': r'\b(git|github|commit|push|pull|branch|merge)\b',
            'search': r'\b(search|find|locate|grep|look)\b',
            'file_ops': r'\b(file|read|write|edit|create|delete)\b',
            'analysis': r'\b(analyze|debug|investigate|profile|benchmark)\b',
            'testing': r'\b(test|pytest|unit|integration|validate)\b',
            'refactor': r'\b(refactor|clean|optimize|improve)\b',
            # Conversational / knowledge task types
            'question': r'\b(what|how|why|when|where|who|which|does|could)\b',
            'knowledge': r'\b(learn|know|tell|describe|define|meaning|concept|theory|difference|explain|understand)\b',
            'conversation': r'\b(think|opinion|feel|believe|agree|disagree|discuss|talk|chat)\b',
        }

        # Complexity indicators
        self.complexity_indicators = {
            'high': r'\b(complex|difficult|hard|challenging|intricate|multiple|all)\b',
            'medium': r'\b(some|several|few|moderate)\b',
            'low': r'\b(simple|easy|quick|trivial|single)\b'
        }

        # Urgency indicators
        self.urgency_indicators = {
            'high': r'\b(urgent|immediately|critical|asap|now|emergency)\b',
            'medium': r'\b(soon|important|priority)\b',
            'low': r'\b(eventually|when|later|someday)\b'
        }

        # Feature → Modality mapping
        # Which brain areas are activated by which task types
        self.feature_modality_map = {
            'memory': {'tool_trace': 0.8, 'temporal_pattern': 0.6, 'success_signal': 0.4},
            'docker': {'tool_trace': 0.9, 'error_signal': 0.7, 'threat': 0.5},
            'github': {'tool_trace': 0.8, 'temporal_pattern': 0.5, 'success_signal': 0.6},
            'search': {'tool_trace': 0.7, 'temporal_pattern': 0.4},
            'file_ops': {'tool_trace': 0.6, 'error_signal': 0.5},
            'analysis': {'tool_trace': 0.8, 'temporal_pattern': 0.7, 'error_signal': 0.6},
            'testing': {'tool_trace': 0.9, 'error_signal': 0.8, 'success_signal': 0.7},
            'refactor': {'tool_trace': 0.7, 'temporal_pattern': 0.6, 'success_signal': 0.5},
            # Conversational modalities: use cognitive/sensory areas, not tool traces
            'question': {'audio': 0.7, 'temporal_pattern': 0.5, 'success_signal': 0.3},
            'knowledge': {'audio': 0.6, 'vision': 0.4, 'temporal_pattern': 0.6},
            'conversation': {'audio': 0.8, 'vision': 0.3, 'success_signal': 0.4},
        }

        # Processing modes based on complexity and urgency
        self.processing_modes = ['urgent', 'analytical', 'creative', 'routine']

        # Statistics
        self.total_routed = 0
        self.task_type_counts = {tt: 0 for tt in self.task_patterns.keys()}
        self.task_type_counts['unknown'] = 0

    def extract_keywords(self, task_description: str) -> List[str]:
        """
        Extract important keywords from task description

        Args:
            task_description: Raw task text

        Returns:
            List of keywords
        """
        # Convert to lowercase
        text = task_description.lower()

        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'may', 'might', 'can', 'this', 'that'
        }

        # Extract words (alphanumeric only)
        words = re.findall(r'\b[a-z]+\b', text)

        # Filter stop words and short words
        keywords = [w for w in words if w not in stop_words and len(w) > 3]

        # Return unique keywords (preserve order)
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords[:10]  # Limit to top 10

    def infer_task_type(self, task_description: str) -> str:
        """
        Infer task type from description using regex patterns.

        Priority: action types (docker, github, etc.) > specific conversational
        types (knowledge, analysis) > generic question type.

        Args:
            task_description: Raw task text

        Returns:
            Task type string
        """
        text = task_description.lower()

        # Check each pattern
        matches = {}
        for task_type, pattern in self.task_patterns.items():
            match_count = len(re.findall(pattern, text))
            if match_count > 0:
                matches[task_type] = match_count

        if not matches:
            return 'unknown'

        # Priority resolution: prefer action types over conversational,
        # and specific conversational over generic 'question'
        action_types = {'memory', 'docker', 'github', 'search', 'file_ops',
                        'analysis', 'testing', 'refactor'}
        specific_conv = {'knowledge', 'conversation'}

        action_matches = {k: v for k, v in matches.items() if k in action_types}
        specific_matches = {k: v for k, v in matches.items() if k in specific_conv}

        # 1. If any action type matched, prefer it (these are the most specific)
        if action_matches:
            return max(action_matches.items(), key=lambda x: x[1])[0]

        # 2. If specific conversational type matched, prefer over generic 'question'
        if specific_matches:
            return max(specific_matches.items(), key=lambda x: x[1])[0]

        # 3. Fallback to best match overall (likely 'question')
        return max(matches.items(), key=lambda x: x[1])[0]

    def estimate_complexity(self, task_description: str) -> float:
        """
        Estimate task complexity (0-1)

        Args:
            task_description: Raw task text

        Returns:
            Complexity score (0=simple, 1=very complex)
        """
        text = task_description.lower()

        # Base complexity (length-based)
        length_complexity = min(len(text) / 200.0, 1.0)

        # Count complexity indicators
        high_count = len(re.findall(self.complexity_indicators['high'], text))
        medium_count = len(re.findall(self.complexity_indicators['medium'], text))
        low_count = len(re.findall(self.complexity_indicators['low'], text))

        # Compute indicator-based complexity
        if high_count > 0:
            indicator_complexity = 0.8
        elif medium_count > 0:
            indicator_complexity = 0.5
        elif low_count > 0:
            indicator_complexity = 0.2
        else:
            indicator_complexity = 0.5  # Default

        # Combine
        complexity = 0.3 * length_complexity + 0.7 * indicator_complexity

        return np.clip(complexity, 0.0, 1.0)

    def estimate_urgency(self, task_description: str) -> float:
        """
        Estimate task urgency (0-1)

        Args:
            task_description: Raw task text

        Returns:
            Urgency score (0=low, 1=urgent)
        """
        text = task_description.lower()

        # Count urgency indicators
        high_count = len(re.findall(self.urgency_indicators['high'], text))
        medium_count = len(re.findall(self.urgency_indicators['medium'], text))
        low_count = len(re.findall(self.urgency_indicators['low'], text))

        if high_count > 0:
            return 0.9
        elif medium_count > 0:
            return 0.6
        elif low_count > 0:
            return 0.3
        else:
            return 0.5  # Default

    def compute_routing_weights(
        self,
        features: TaskFeatures
    ) -> np.ndarray:
        """
        Compute routing weights to brain areas based on task features

        Args:
            features: Extracted task features

        Returns:
            Routing weights [num_modalities] (sums to 1.0)
        """
        # Initialize base weights (uniform)
        weights = np.ones(self.num_modalities) * 0.1

        # Activate modalities based on task type
        if features.task_type in self.feature_modality_map:
            activation_map = self.feature_modality_map[features.task_type]
            for modality, activation in activation_map.items():
                if modality in self.modalities:
                    idx = self.modalities.index(modality)
                    weights[idx] += activation

        # Adjust based on complexity
        # High complexity → More temporal_pattern and tool_trace
        if 'temporal_pattern' in self.modalities:
            idx = self.modalities.index('temporal_pattern')
            weights[idx] += features.complexity * 0.3

        if 'tool_trace' in self.modalities:
            idx = self.modalities.index('tool_trace')
            weights[idx] += features.complexity * 0.2

        # Adjust based on urgency
        # High urgency → More threat and error_signal
        if 'threat' in self.modalities:
            idx = self.modalities.index('threat')
            weights[idx] += features.urgency * 0.4

        if 'error_signal' in self.modalities:
            idx = self.modalities.index('error_signal')
            weights[idx] += features.urgency * 0.3

        # Normalize to sum to 1.0 (softmax-like, but simpler)
        weights = np.maximum(weights, 0.0)  # Ensure non-negative
        weight_sum = np.sum(weights)
        if weight_sum > 0:
            weights = weights / weight_sum
        else:
            # Fallback to uniform
            weights = np.ones(self.num_modalities) / self.num_modalities

        return weights

    def select_processing_mode(
        self,
        features: TaskFeatures,
        routing_weights: np.ndarray
    ) -> str:
        """
        Select processing mode based on features and routing

        Args:
            features: Extracted task features
            routing_weights: Computed routing weights

        Returns:
            Processing mode string
        """
        # Determine mode based on urgency and complexity
        if features.urgency > 0.7:
            return 'urgent'
        elif features.complexity > 0.7:
            return 'analytical'
        elif features.complexity < 0.3:
            return 'routine'
        else:
            return 'creative'

    def route_task(self, task_description: str) -> RoutingState:
        """
        Main routing function: Extract features and compute routing

        Args:
            task_description: Raw task description

        Returns:
            RoutingState with features, weights, mode, and dominant areas
        """
        # Extract features
        keywords = self.extract_keywords(task_description)
        task_type = self.infer_task_type(task_description)
        complexity = self.estimate_complexity(task_description)
        urgency = self.estimate_urgency(task_description)

        features = TaskFeatures(
            keywords=keywords,
            task_type=task_type,
            complexity=complexity,
            urgency=urgency,
            raw_description=task_description
        )

        # Compute routing weights
        routing_weights = self.compute_routing_weights(features)

        # Select processing mode
        processing_mode = self.select_processing_mode(features, routing_weights)

        # Identify dominant areas (top 3)
        top_indices = np.argsort(routing_weights)[::-1][:3]
        dominant_areas = [self.modalities[i] for i in top_indices]

        # Create routing state
        routing_state = RoutingState(
            features=features,
            routing_weights=routing_weights,
            processing_mode=processing_mode,
            dominant_areas=dominant_areas
        )

        # Update statistics
        self.total_routed += 1
        self.task_type_counts[task_type] += 1

        return routing_state

    def get_statistics(self) -> Dict:
        """Get routing statistics"""
        return {
            'total_routed': self.total_routed,
            'task_type_counts': self.task_type_counts.copy(),
            'task_type_distribution': {
                tt: count / self.total_routed if self.total_routed > 0 else 0.0
                for tt, count in self.task_type_counts.items()
            }
        }

    def reset_statistics(self):
        """Reset routing statistics"""
        self.total_routed = 0
        self.task_type_counts = {tt: 0 for tt in self.task_patterns.keys()}
        self.task_type_counts['unknown'] = 0

    def __repr__(self):
        return (
            f"TaskFeatureRouter("
            f"modalities={self.num_modalities}, "
            f"task_types={len(self.task_patterns)}, "
            f"routed={self.total_routed})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("TESTING TASK FEATURE ROUTER (Phase 4 - Layer 1)")
    print("=" * 70)
    print()

    # Initialize router
    router = TaskFeatureRouter(seed=42)

    print(f"Initialized: {router}")
    print(f"Modalities: {router.modalities}")
    print()

    # Test different task descriptions
    test_tasks = [
        "Check memory status and monitor dashboard",
        "Deploy with Docker and build container image",
        "git add, commit, and push to GitHub urgently",
        "Search for files containing error messages",
        "Analyze this complex codebase and understand the architecture"
    ]

    for i, task in enumerate(test_tasks, 1):
        print(f"Task {i}: \"{task}\"")
        print("-" * 70)

        routing_state = router.route_task(task)

        # Display results
        print(f"\n  EXTRACTED FEATURES:")
        print(f"    Task Type:   {routing_state.features.task_type}")
        print(f"    Complexity:  {routing_state.features.complexity:.2f}")
        print(f"    Urgency:     {routing_state.features.urgency:.2f}")
        print(f"    Keywords:    {', '.join(routing_state.features.keywords[:5])}")

        print(f"\n  ROUTING RESULTS:")
        print(f"    Mode:        {routing_state.processing_mode}")
        print(f"    Dominant:    {', '.join(routing_state.dominant_areas)}")

        print(f"\n  TOP ROUTING WEIGHTS:")
        sorted_indices = np.argsort(routing_state.routing_weights)[::-1]
        for idx in sorted_indices[:5]:
            modality = router.modalities[idx]
            weight = routing_state.routing_weights[idx]
            bar = '#' * int(weight * 50)
            print(f"    {modality:18s} {weight:.3f} {bar}")

        print()
        print("=" * 70)
        print()

    # Show statistics
    print("ROUTING STATISTICS")
    print("=" * 70)
    stats = router.get_statistics()
    print(f"Total routed: {stats['total_routed']}")
    print()
    print("Task type distribution:")
    for task_type, prob in sorted(stats['task_type_distribution'].items(),
                                   key=lambda x: x[1], reverse=True):
        if prob > 0:
            bar = '#' * int(prob * 50)
            print(f"  {task_type:12s} {prob:.1%} {bar}")

    print()
    print("=" * 70)
    print("LAYER 1 TEST COMPLETE!")
    print("=" * 70)
