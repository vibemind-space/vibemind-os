"""
Multi-Target Decision Router (Phase 3)

Concept from logical_brain/routed_brain.py:
Instead of routing to a single output, route to multiple weighted targets.

Original PyTorch implementation:
```python
# Routing Matrix: [num_inputs] -> [num_outputs]
self.routing_matrix = nn.Parameter(torch.randn(6, 10) * 0.1)

# Compute routing weights
routing_weights = torch.matmul(gates, self.routing_matrix)
routing_weights = F.softmax(routing_weights, dim=-1)

# Jeder Output bekommt gewichtete Kombination aller Inputs
for i in range(num_outputs):
    output[i] = weighted_sum(inputs, routing_weights[i])
```

Our NumPy adaptation:
- Routing matrix: [num_modalities] -> [num_interventions]
- Maps brain gate distribution to weighted intervention decisions
- Returns not just "suggest", but "65% suggest, 25% retry, 8% wait, 2% terminate"
- Enables uncertainty quantification and multi-strategy execution
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class InterventionDecision:
    """
    A single intervention decision with weight and metadata
    """
    intervention_type: str  # e.g., 'suggest', 'retry', 'terminate', 'wait'
    weight: float          # Routing weight (0-1)
    confidence: float      # Confidence in this decision
    reasoning: str         # Brief explanation


@dataclass
class MultiTargetDecision:
    """
    Complete multi-target decision with primary + alternatives
    """
    primary: InterventionDecision
    alternatives: List[InterventionDecision]
    total_weight_sum: float  # Should be 1.0 (sanity check)
    dominant_modalities: List[str]  # Which brain areas drove this decision

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'primary': {
                'type': self.primary.intervention_type,
                'weight': float(self.primary.weight),
                'confidence': float(self.primary.confidence),
                'reasoning': self.primary.reasoning
            },
            'alternatives': [
                {
                    'type': alt.intervention_type,
                    'weight': float(alt.weight),
                    'confidence': float(alt.confidence),
                    'reasoning': alt.reasoning
                }
                for alt in self.alternatives
            ],
            'total_weight_sum': float(self.total_weight_sum),
            'dominant_modalities': self.dominant_modalities
        }


class MultiTargetDecisionRouter:
    """
    Routes brain output to multiple weighted intervention decisions

    Instead of: "The decision is: suggest"
    We get:     "65% suggest, 25% retry, 8% wait, 2% terminate"

    This enables:
    1. Uncertainty quantification
    2. Multi-strategy execution
    3. Fallback options
    4. Interpretability
    """

    def __init__(
        self,
        num_modalities: int = 10,
        intervention_types: Optional[List[str]] = None,
        routing_matrix: Optional[np.ndarray] = None,
        learning_rate: float = 0.001,
        seed: int = 42
    ):
        """
        Initialize multi-target decision router

        Args:
            num_modalities: Number of input modalities (default 10)
            intervention_types: List of intervention types
            routing_matrix: Optional pre-initialized routing matrix
            learning_rate: Learning rate for online adaptation
            seed: Random seed
        """
        self.num_modalities = num_modalities
        self.learning_rate = learning_rate
        self.rng = np.random.RandomState(seed)

        # Default intervention types
        if intervention_types is None:
            intervention_types = [
                'suggest',    # Suggest next action
                'retry',      # Retry failed operation
                'wait',       # Wait and observe
                'terminate'   # Stop and report failure
            ]

        self.intervention_types = intervention_types
        self.num_interventions = len(intervention_types)

        # Routing matrix: [num_modalities] -> [num_interventions]
        if routing_matrix is None:
            # Initialize with small random values
            self.routing_matrix = self.rng.randn(
                num_modalities, self.num_interventions
            ) * 0.1
        else:
            self.routing_matrix = routing_matrix.copy()

        # Statistics
        self.total_decisions = 0
        self.intervention_counts = {itype: 0 for itype in intervention_types}

    def route_decision(
        self,
        gates: np.ndarray,
        confidence: float = 0.5,
        dominant_modalities: Optional[List[str]] = None,
        per_modality_pes: Optional[Dict[str, float]] = None
    ) -> MultiTargetDecision:
        """
        Route gate distribution to weighted intervention decisions

        Args:
            gates: Gate distribution [num_modalities] (sums to 1.0)
            confidence: Overall prediction confidence
            dominant_modalities: Names of dominant modalities
            per_modality_pes: Optional per-modality prediction errors

        Returns:
            MultiTargetDecision with primary + alternatives
        """
        # Validate gates
        assert len(gates) == self.num_modalities, \
            f"Expected {self.num_modalities} gates, got {len(gates)}"
        assert np.abs(np.sum(gates) - 1.0) < 1e-6, \
            f"Gates must sum to 1.0, got {np.sum(gates):.6f}"

        # Compute intervention weights: gates @ routing_matrix
        intervention_logits = np.dot(gates, self.routing_matrix)

        # Softmax to get probabilities
        intervention_logits = intervention_logits - np.max(intervention_logits)  # Numerical stability
        exp_logits = np.exp(intervention_logits)
        intervention_weights = exp_logits / np.sum(exp_logits)

        # Sort by weight descending
        sorted_indices = np.argsort(intervention_weights)[::-1]

        # Create intervention decisions
        decisions = []
        for idx in sorted_indices:
            itype = self.intervention_types[idx]
            weight = float(intervention_weights[idx])

            # Generate reasoning based on dominant modalities and PEs
            reasoning = self._generate_reasoning(
                itype, weight, dominant_modalities, per_modality_pes
            )

            decisions.append(InterventionDecision(
                intervention_type=itype,
                weight=weight,
                confidence=confidence,
                reasoning=reasoning
            ))

        # Primary decision (highest weight)
        primary = decisions[0]

        # Alternative decisions (rest)
        alternatives = decisions[1:]

        # Sanity check
        total_weight = sum(d.weight for d in decisions)

        # Create multi-target decision
        decision = MultiTargetDecision(
            primary=primary,
            alternatives=alternatives,
            total_weight_sum=total_weight,
            dominant_modalities=dominant_modalities or []
        )

        # Update statistics
        self.total_decisions += 1
        self.intervention_counts[primary.intervention_type] += 1

        return decision

    def _generate_reasoning(
        self,
        intervention_type: str,
        weight: float,
        dominant_modalities: Optional[List[str]],
        per_modality_pes: Optional[Dict[str, float]]
    ) -> str:
        """
        Generate human-readable reasoning for an intervention

        Args:
            intervention_type: Type of intervention
            weight: Intervention weight
            dominant_modalities: Dominant modalities
            per_modality_pes: Per-modality PEs

        Returns:
            Reasoning string
        """
        # Base reasoning on intervention type
        reasoning_templates = {
            'suggest': "Proactive guidance based on",
            'retry': "Detected failure, attempting recovery via",
            'wait': "Uncertain state, monitoring via",
            'terminate': "Critical failure detected in"
        }

        base = reasoning_templates.get(intervention_type, "Decision driven by")

        # Add modality info if available
        if dominant_modalities:
            top_modalities = dominant_modalities[:2]
            modality_str = " + ".join(top_modalities)
            reasoning = f"{base} {modality_str}"
        else:
            reasoning = base + " brain routing"

        # Add PE info if available
        if per_modality_pes and dominant_modalities:
            # Check if dominant modalities have high PE
            high_pe_modalities = [
                m for m in dominant_modalities[:2]
                if m in per_modality_pes and per_modality_pes[m] > 0.5
            ]
            if high_pe_modalities:
                reasoning += f" (novel: {', '.join(high_pe_modalities)})"

        return reasoning

    def update_routing_matrix(
        self,
        gates: np.ndarray,
        target_intervention: str,
        feedback_strength: float = 1.0
    ):
        """
        Update routing matrix based on feedback (online learning)

        This implements a simple supervised update:
        If intervention X was correct, strengthen the connection
        from active gates to X.

        Args:
            gates: Gate distribution that led to decision
            target_intervention: Which intervention should have been chosen
            feedback_strength: How strong the update (0-1)
        """
        if target_intervention not in self.intervention_types:
            return

        target_idx = self.intervention_types.index(target_intervention)

        # Create one-hot target
        target_vector = np.zeros(self.num_interventions)
        target_vector[target_idx] = 1.0

        # Current prediction
        current_logits = np.dot(gates, self.routing_matrix)
        exp_logits = np.exp(current_logits - np.max(current_logits))
        current_probs = exp_logits / np.sum(exp_logits)

        # Error (target - prediction)
        error = target_vector - current_probs

        # Gradient: outer product of gates and error
        gradient = np.outer(gates, error)

        # Update with learning rate and feedback strength
        self.routing_matrix += self.learning_rate * feedback_strength * gradient

    def get_statistics(self) -> Dict:
        """Get routing statistics"""
        return {
            'total_decisions': self.total_decisions,
            'intervention_counts': self.intervention_counts.copy(),
            'intervention_distribution': {
                itype: count / self.total_decisions if self.total_decisions > 0 else 0.0
                for itype, count in self.intervention_counts.items()
            },
            'routing_matrix_shape': self.routing_matrix.shape,
            'routing_matrix_norm': float(np.linalg.norm(self.routing_matrix))
        }

    def get_routing_matrix(self) -> np.ndarray:
        """Get copy of routing matrix"""
        return self.routing_matrix.copy()

    def set_routing_matrix(self, matrix: np.ndarray):
        """Set routing matrix (for loading saved state)"""
        assert matrix.shape == (self.num_modalities, self.num_interventions)
        self.routing_matrix = matrix.copy()

    def reset_statistics(self):
        """Reset decision statistics (keep routing matrix)"""
        self.total_decisions = 0
        self.intervention_counts = {itype: 0 for itype in self.intervention_types}

    def __repr__(self):
        return (
            f"MultiTargetDecisionRouter("
            f"modalities={self.num_modalities}, "
            f"interventions={self.num_interventions}, "
            f"decisions={self.total_decisions})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("TESTING MULTI-TARGET DECISION ROUTING (Phase 3)")
    print("=" * 70)
    print()

    # Initialize router
    router = MultiTargetDecisionRouter(
        num_modalities=10,
        intervention_types=['suggest', 'retry', 'wait', 'terminate'],
        seed=42
    )

    print(f"Initialized: {router}")
    print(f"Routing matrix shape: {router.routing_matrix.shape}")
    print()

    # Simulate different gate distributions
    test_scenarios = [
        {
            'name': 'High tool_trace activation (task-focused)',
            'gates': np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.50, 0.10, 0.05, 0.05]),
            'confidence': 0.85,
            'dominant': ['tool_trace', 'temporal_pattern']
        },
        {
            'name': 'High error_signal (failure detected)',
            'gates': np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.10, 0.10, 0.40, 0.10]),
            'confidence': 0.45,
            'dominant': ['error_signal', 'threat']
        },
        {
            'name': 'High threat (critical failure)',
            'gates': np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.60, 0.05, 0.05, 0.05, 0.00]),
            'confidence': 0.30,
            'dominant': ['threat']
        },
        {
            'name': 'Balanced/uncertain',
            'gates': np.ones(10) / 10,
            'confidence': 0.50,
            'dominant': []
        }
    ]

    for i, scenario in enumerate(test_scenarios, 1):
        print(f"Scenario {i}: {scenario['name']}")
        print(f"  Gates sum: {np.sum(scenario['gates']):.6f}")
        print()

        decision = router.route_decision(
            gates=scenario['gates'],
            confidence=scenario['confidence'],
            dominant_modalities=scenario['dominant']
        )

        # Display decision
        print(f"  PRIMARY DECISION:")
        print(f"    Type:       {decision.primary.intervention_type}")
        print(f"    Weight:     {decision.primary.weight:.1%}")
        print(f"    Confidence: {decision.primary.confidence:.1%}")
        print(f"    Reasoning:  {decision.primary.reasoning}")
        print()

        print(f"  ALTERNATIVES:")
        for alt in decision.alternatives:
            print(f"    {alt.intervention_type:12s} {alt.weight:.1%}")

        print()
        print(f"  Weight sum check: {decision.total_weight_sum:.6f}")
        print()
        print("-" * 70)
        print()

    # Show final statistics
    print("=" * 70)
    print("ROUTING STATISTICS")
    print("=" * 70)
    print()

    stats = router.get_statistics()
    print(f"Total decisions: {stats['total_decisions']}")
    print()
    print("Intervention distribution:")
    for itype, prob in stats['intervention_distribution'].items():
        bar = '#' * int(prob * 50)
        print(f"  {itype:12s} {prob:.1%} {bar}")

    print()
    print("=" * 70)
    print("TEST COMPLETE!")
    print("=" * 70)
    print()
    print("KEY INSIGHTS:")
    print("1. Each decision comes with weighted alternatives")
    print("2. Not just 'suggest' but '65% suggest, 25% retry, ...'")
    print("3. Enables uncertainty quantification")
    print("4. Provides fallback options automatically")
