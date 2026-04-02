"""
Explanation Generator - AGI Phase 5

Generates human-understandable explanations for AI decisions.
Provides transparency and interpretability for complex reasoning.

Key Features:
- Chain-of-Thought extraction
- Counterfactual explanations
- Feature attribution (SHAP-like)
- Natural language generation
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class ExplanationType(Enum):
    """Types of explanations."""
    CHAIN_OF_THOUGHT = "chain_of_thought"
    COUNTERFACTUAL = "counterfactual"
    FEATURE_ATTRIBUTION = "feature_attribution"
    CONTRASTIVE = "contrastive"
    EXAMPLE_BASED = "example_based"
    RULE_BASED = "rule_based"


class ExplanationLevel(Enum):
    """Level of detail in explanation."""
    BRIEF = "brief"  # One sentence
    STANDARD = "standard"  # Paragraph
    DETAILED = "detailed"  # Full analysis
    TECHNICAL = "technical"  # With formulas/code


@dataclass
class ReasoningStep:
    """Single step in chain-of-thought reasoning."""
    step_number: int
    description: str
    input_state: Any
    output_state: Any
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)
    alternatives_considered: List[str] = field(default_factory=list)


@dataclass
class FeatureContribution:
    """Contribution of a feature to the decision."""
    feature_name: str
    feature_value: Any
    contribution: float  # Positive = supports, Negative = opposes
    importance_rank: int
    baseline_value: Optional[Any] = None


@dataclass
class Counterfactual:
    """Counterfactual explanation."""
    original_input: Dict[str, Any]
    modified_input: Dict[str, Any]
    original_outcome: Any
    counterfactual_outcome: Any
    changes_required: List[str]
    minimal: bool = True  # Is this the minimal change?
    feasibility: float = 1.0  # How feasible is this change?


@dataclass
class Explanation:
    """Complete explanation for a decision."""
    explanation_type: ExplanationType
    decision: Any
    summary: str
    detailed_text: str
    confidence: float
    reasoning_steps: List[ReasoningStep] = field(default_factory=list)
    feature_contributions: List[FeatureContribution] = field(default_factory=list)
    counterfactuals: List[Counterfactual] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    timestamp: int = 0


@dataclass
class ExplainerStats:
    """Statistics for explanation generator."""
    total_explanations: int = 0
    avg_reasoning_steps: float = 0.0
    avg_features_used: float = 0.0
    counterfactuals_generated: int = 0


class ChainOfThoughtExtractor:
    """Extracts and reconstructs chain-of-thought reasoning."""

    def __init__(self, max_steps: int = 20):
        self.max_steps = max_steps
        self.reasoning_history: List[ReasoningStep] = []

    def record_step(
        self,
        description: str,
        input_state: Any,
        output_state: Any,
        confidence: float = 1.0,
        evidence: Optional[List[str]] = None,
        alternatives: Optional[List[str]] = None
    ):
        """Record a reasoning step."""
        step = ReasoningStep(
            step_number=len(self.reasoning_history) + 1,
            description=description,
            input_state=input_state,
            output_state=output_state,
            confidence=confidence,
            evidence=evidence or [],
            alternatives_considered=alternatives or []
        )
        self.reasoning_history.append(step)

        # Trim if too long
        if len(self.reasoning_history) > self.max_steps:
            self.reasoning_history = self.reasoning_history[-self.max_steps:]

    def extract_chain(
        self,
        start_idx: int = 0,
        end_idx: Optional[int] = None
    ) -> List[ReasoningStep]:
        """Extract reasoning chain."""
        end_idx = end_idx or len(self.reasoning_history)
        return self.reasoning_history[start_idx:end_idx]

    def generate_narrative(self, chain: List[ReasoningStep]) -> str:
        """Generate natural language narrative from reasoning chain."""
        if not chain:
            return "No reasoning steps recorded."

        narrative_parts = []

        for step in chain:
            # Build step narrative
            step_text = f"Step {step.step_number}: {step.description}"

            if step.evidence:
                step_text += f" (Evidence: {', '.join(step.evidence[:3])})"

            if step.alternatives_considered:
                step_text += f" [Also considered: {', '.join(step.alternatives_considered[:2])}]"

            if step.confidence < 0.8:
                step_text += f" (Confidence: {step.confidence:.0%})"

            narrative_parts.append(step_text)

        return "\n".join(narrative_parts)

    def summarize_chain(self, chain: List[ReasoningStep]) -> str:
        """Generate brief summary of reasoning."""
        if not chain:
            return "No reasoning available."

        # Extract key steps (first, pivotal, last)
        key_steps = []
        if chain:
            key_steps.append(chain[0].description)  # Starting point

        # Find pivotal step (lowest confidence or with alternatives)
        pivotal = min(chain, key=lambda s: s.confidence, default=None)
        if pivotal and pivotal != chain[0] and pivotal != chain[-1]:
            key_steps.append(f"Key consideration: {pivotal.description}")

        if len(chain) > 1:
            key_steps.append(f"Conclusion: {chain[-1].description}")

        return " -> ".join(key_steps)

    def clear(self):
        """Clear reasoning history."""
        self.reasoning_history = []


class FeatureAttributor:
    """
    Computes feature attributions for decisions.

    Uses SHAP-like approach with perturbation-based importance.
    """

    def __init__(
        self,
        feature_names: List[str],
        baseline: Optional[np.ndarray] = None,
        num_samples: int = 100
    ):
        self.feature_names = feature_names
        self.baseline = baseline
        self.num_samples = num_samples

    def compute_attributions(
        self,
        input_features: np.ndarray,
        predict_fn: Callable[[np.ndarray], Any],
        target_output: Optional[Any] = None
    ) -> List[FeatureContribution]:
        """
        Compute feature attributions using perturbation.

        Args:
            input_features: Input feature vector
            predict_fn: Function that returns prediction for features
            target_output: Specific output to explain

        Returns:
            List of feature contributions
        """
        contributions = []
        baseline = self.baseline if self.baseline is not None else np.zeros_like(input_features)

        # Get original prediction
        original_pred = predict_fn(input_features)

        # Compute contribution for each feature
        for i, feature_name in enumerate(self.feature_names):
            # Ablation: set feature to baseline
            ablated = input_features.copy()
            ablated[i] = baseline[i]
            ablated_pred = predict_fn(ablated)

            # Contribution = original - ablated
            contribution = self._compute_difference(original_pred, ablated_pred)

            contributions.append(FeatureContribution(
                feature_name=feature_name,
                feature_value=input_features[i],
                contribution=contribution,
                importance_rank=0,  # Will be set later
                baseline_value=baseline[i]
            ))

        # Sort by absolute contribution and assign ranks
        contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
        for rank, contrib in enumerate(contributions, 1):
            contrib.importance_rank = rank

        return contributions

    def _compute_difference(self, pred1: Any, pred2: Any) -> float:
        """Compute difference between predictions."""
        if isinstance(pred1, (int, float)):
            return float(pred1 - pred2)
        elif isinstance(pred1, np.ndarray):
            return float(np.sum(pred1 - pred2))
        elif isinstance(pred1, dict):
            # Handle dict outputs (e.g., {action: prob})
            if 'value' in pred1:
                return pred1['value'] - pred2.get('value', 0)
            return 0.0
        return 0.0

    def get_top_features(
        self,
        contributions: List[FeatureContribution],
        k: int = 5
    ) -> List[FeatureContribution]:
        """Get top k most important features."""
        sorted_contribs = sorted(
            contributions,
            key=lambda c: abs(c.contribution),
            reverse=True
        )
        return sorted_contribs[:k]


class CounterfactualGenerator:
    """
    Generates counterfactual explanations.

    Finds minimal changes to input that would change the decision.
    """

    def __init__(
        self,
        feature_names: List[str],
        feature_ranges: Dict[str, Tuple[float, float]],
        actionable_features: Optional[List[str]] = None
    ):
        self.feature_names = feature_names
        self.feature_ranges = feature_ranges
        self.actionable_features = actionable_features or feature_names

    def generate_counterfactual(
        self,
        input_features: Dict[str, Any],
        predict_fn: Callable[[Dict[str, Any]], Any],
        target_outcome: Any,
        max_changes: int = 3,
        num_candidates: int = 100
    ) -> Optional[Counterfactual]:
        """
        Generate counterfactual explanation.

        Args:
            input_features: Original input
            predict_fn: Prediction function
            target_outcome: Desired outcome
            max_changes: Maximum features to change
            num_candidates: Number of candidates to explore

        Returns:
            Counterfactual if found
        """
        original_outcome = predict_fn(input_features)

        if self._outcomes_match(original_outcome, target_outcome):
            return None  # Already at target

        best_counterfactual = None
        best_distance = float('inf')

        for _ in range(num_candidates):
            # Generate candidate by perturbing random features
            candidate = self._generate_candidate(
                input_features,
                max_changes
            )

            candidate_outcome = predict_fn(candidate)

            if self._outcomes_match(candidate_outcome, target_outcome):
                distance = self._compute_distance(input_features, candidate)

                if distance < best_distance:
                    best_distance = distance
                    changes = self._identify_changes(input_features, candidate)

                    best_counterfactual = Counterfactual(
                        original_input=input_features.copy(),
                        modified_input=candidate.copy(),
                        original_outcome=original_outcome,
                        counterfactual_outcome=candidate_outcome,
                        changes_required=changes,
                        minimal=(len(changes) <= 2),
                        feasibility=self._compute_feasibility(changes)
                    )

        return best_counterfactual

    def _generate_candidate(
        self,
        input_features: Dict[str, Any],
        max_changes: int
    ) -> Dict[str, Any]:
        """Generate candidate counterfactual."""
        candidate = input_features.copy()

        # Select random features to change
        num_changes = np.random.randint(1, max_changes + 1)
        features_to_change = np.random.choice(
            self.actionable_features,
            size=min(num_changes, len(self.actionable_features)),
            replace=False
        )

        for feature in features_to_change:
            if feature in self.feature_ranges:
                low, high = self.feature_ranges[feature]
                candidate[feature] = np.random.uniform(low, high)

        return candidate

    def _outcomes_match(self, outcome1: Any, outcome2: Any) -> bool:
        """Check if outcomes match."""
        if isinstance(outcome1, (int, str)):
            return outcome1 == outcome2
        elif isinstance(outcome1, float):
            return abs(outcome1 - outcome2) < 0.1
        elif isinstance(outcome1, np.ndarray):
            return np.allclose(outcome1, outcome2, atol=0.1)
        return outcome1 == outcome2

    def _compute_distance(
        self,
        original: Dict[str, Any],
        modified: Dict[str, Any]
    ) -> float:
        """Compute distance between inputs."""
        distance = 0.0
        for key in original:
            if key in modified:
                if isinstance(original[key], (int, float)):
                    # Normalize by range
                    if key in self.feature_ranges:
                        low, high = self.feature_ranges[key]
                        range_size = high - low
                        if range_size > 0:
                            distance += abs(original[key] - modified[key]) / range_size
                    else:
                        distance += abs(original[key] - modified[key])
                elif original[key] != modified[key]:
                    distance += 1.0  # Categorical change
        return distance

    def _identify_changes(
        self,
        original: Dict[str, Any],
        modified: Dict[str, Any]
    ) -> List[str]:
        """Identify what changed."""
        changes = []
        for key in original:
            if key in modified and original[key] != modified[key]:
                changes.append(f"{key}: {original[key]} -> {modified[key]}")
        return changes

    def _compute_feasibility(self, changes: List[str]) -> float:
        """Compute feasibility of changes."""
        # More changes = less feasible
        return max(0.0, 1.0 - len(changes) * 0.2)


class ContrastiveExplainer:
    """
    Generates contrastive explanations.

    Explains why decision A was made instead of decision B.
    """

    def __init__(self, decision_space: List[Any]):
        self.decision_space = decision_space

    def explain_contrast(
        self,
        input_features: Dict[str, Any],
        chosen_decision: Any,
        alternative_decision: Any,
        decision_scores: Dict[Any, float],
        feature_contributions: Dict[Any, List[FeatureContribution]]
    ) -> str:
        """
        Explain why chosen decision beats alternative.

        Args:
            input_features: Input features
            chosen_decision: The decision that was made
            alternative_decision: Alternative to contrast against
            decision_scores: Scores for each decision
            feature_contributions: Feature contributions per decision

        Returns:
            Contrastive explanation text
        """
        chosen_score = decision_scores.get(chosen_decision, 0)
        alt_score = decision_scores.get(alternative_decision, 0)

        # Get differentiating features
        chosen_contribs = feature_contributions.get(chosen_decision, [])
        alt_contribs = feature_contributions.get(alternative_decision, [])

        # Find features that favor chosen over alternative
        favoring_features = []
        opposing_features = []

        contrib_dict = {c.feature_name: c.contribution for c in chosen_contribs}
        alt_contrib_dict = {c.feature_name: c.contribution for c in alt_contribs}

        for feature in contrib_dict:
            diff = contrib_dict[feature] - alt_contrib_dict.get(feature, 0)
            if diff > 0.1:
                favoring_features.append(feature)
            elif diff < -0.1:
                opposing_features.append(feature)

        # Generate explanation
        explanation_parts = [
            f"Decision '{chosen_decision}' was chosen over '{alternative_decision}'",
            f"(scores: {chosen_score:.2f} vs {alt_score:.2f})."
        ]

        if favoring_features:
            explanation_parts.append(
                f"Key factors favoring this choice: {', '.join(favoring_features[:3])}."
            )

        if opposing_features:
            explanation_parts.append(
                f"Despite: {', '.join(opposing_features[:2])} favoring the alternative."
            )

        return " ".join(explanation_parts)


class ExplanationGenerator:
    """
    Main explanation generator combining multiple explanation techniques.

    Provides comprehensive, human-understandable explanations for AI decisions.
    """

    def __init__(
        self,
        feature_names: List[str],
        decision_space: Optional[List[Any]] = None,
        feature_ranges: Optional[Dict[str, Tuple[float, float]]] = None
    ):
        self.feature_names = feature_names
        self.decision_space = decision_space or []

        # Initialize components
        self.cot_extractor = ChainOfThoughtExtractor()
        self.attributor = FeatureAttributor(feature_names)
        self.counterfactual_gen = CounterfactualGenerator(
            feature_names,
            feature_ranges or {}
        )
        self.contrastive = ContrastiveExplainer(self.decision_space)

        # Statistics
        self.stats = ExplainerStats()
        self.timestamp = 0

    def record_reasoning_step(
        self,
        description: str,
        input_state: Any,
        output_state: Any,
        **kwargs
    ):
        """Record a step in the reasoning process."""
        self.cot_extractor.record_step(
            description,
            input_state,
            output_state,
            **kwargs
        )

    def generate_explanation(
        self,
        input_features: Union[np.ndarray, Dict[str, Any]],
        decision: Any,
        predict_fn: Optional[Callable] = None,
        explanation_type: ExplanationType = ExplanationType.CHAIN_OF_THOUGHT,
        level: ExplanationLevel = ExplanationLevel.STANDARD
    ) -> Explanation:
        """
        Generate comprehensive explanation for a decision.

        Args:
            input_features: Input that led to decision
            decision: The decision made
            predict_fn: Optional prediction function for attributions
            explanation_type: Type of explanation to generate
            level: Level of detail

        Returns:
            Complete explanation
        """
        self.timestamp += 1

        # Extract reasoning chain
        reasoning_chain = self.cot_extractor.extract_chain()

        # Generate based on type
        if explanation_type == ExplanationType.CHAIN_OF_THOUGHT:
            return self._generate_cot_explanation(
                input_features, decision, reasoning_chain, level
            )
        elif explanation_type == ExplanationType.FEATURE_ATTRIBUTION:
            return self._generate_attribution_explanation(
                input_features, decision, predict_fn, level
            )
        elif explanation_type == ExplanationType.COUNTERFACTUAL:
            return self._generate_counterfactual_explanation(
                input_features, decision, predict_fn, level
            )
        else:
            # Default to chain-of-thought
            return self._generate_cot_explanation(
                input_features, decision, reasoning_chain, level
            )

    def _generate_cot_explanation(
        self,
        input_features: Any,
        decision: Any,
        reasoning_chain: List[ReasoningStep],
        level: ExplanationLevel
    ) -> Explanation:
        """Generate chain-of-thought explanation."""
        if level == ExplanationLevel.BRIEF:
            summary = self.cot_extractor.summarize_chain(reasoning_chain)
            detailed = summary
        else:
            summary = self.cot_extractor.summarize_chain(reasoning_chain)
            detailed = self.cot_extractor.generate_narrative(reasoning_chain)

        # Compute confidence from reasoning steps
        if reasoning_chain:
            confidence = np.mean([s.confidence for s in reasoning_chain])
        else:
            confidence = 0.5

        # Extract evidence
        evidence = []
        for step in reasoning_chain:
            evidence.extend(step.evidence[:2])

        self.stats.total_explanations += 1
        self.stats.avg_reasoning_steps = (
            (self.stats.avg_reasoning_steps * (self.stats.total_explanations - 1)
             + len(reasoning_chain)) / self.stats.total_explanations
        )

        return Explanation(
            explanation_type=ExplanationType.CHAIN_OF_THOUGHT,
            decision=decision,
            summary=summary,
            detailed_text=detailed,
            confidence=confidence,
            reasoning_steps=reasoning_chain,
            supporting_evidence=evidence[:5],
            timestamp=self.timestamp
        )

    def _generate_attribution_explanation(
        self,
        input_features: Union[np.ndarray, Dict[str, Any]],
        decision: Any,
        predict_fn: Optional[Callable],
        level: ExplanationLevel
    ) -> Explanation:
        """Generate feature attribution explanation."""
        # Convert dict to array if needed
        if isinstance(input_features, dict):
            feature_array = np.array([input_features.get(f, 0) for f in self.feature_names])
        else:
            feature_array = input_features

        # Compute attributions
        if predict_fn is not None:
            contributions = self.attributor.compute_attributions(
                feature_array, predict_fn
            )
        else:
            # Dummy contributions
            contributions = [
                FeatureContribution(
                    feature_name=f,
                    feature_value=feature_array[i] if i < len(feature_array) else 0,
                    contribution=0.0,
                    importance_rank=i + 1
                )
                for i, f in enumerate(self.feature_names)
            ]

        # Get top features
        top_features = self.attributor.get_top_features(contributions, k=5)

        # Generate summary
        positive_features = [f for f in top_features if f.contribution > 0]
        negative_features = [f for f in top_features if f.contribution < 0]

        summary_parts = [f"Decision: {decision}."]

        if positive_features:
            pos_names = [f.feature_name for f in positive_features[:3]]
            summary_parts.append(f"Key factors: {', '.join(pos_names)}.")

        if negative_features:
            neg_names = [f.feature_name for f in negative_features[:2]]
            summary_parts.append(f"Counteracting: {', '.join(neg_names)}.")

        summary = " ".join(summary_parts)

        # Generate detailed text
        detailed_parts = [summary, "\nFeature Contributions:"]
        for contrib in top_features:
            sign = "+" if contrib.contribution > 0 else ""
            detailed_parts.append(
                f"  {contrib.feature_name}: {sign}{contrib.contribution:.3f} "
                f"(value: {contrib.feature_value})"
            )

        detailed = "\n".join(detailed_parts)

        self.stats.total_explanations += 1
        self.stats.avg_features_used = (
            (self.stats.avg_features_used * (self.stats.total_explanations - 1)
             + len(top_features)) / self.stats.total_explanations
        )

        return Explanation(
            explanation_type=ExplanationType.FEATURE_ATTRIBUTION,
            decision=decision,
            summary=summary,
            detailed_text=detailed,
            confidence=0.8,  # Attribution confidence
            feature_contributions=contributions,
            timestamp=self.timestamp
        )

    def _generate_counterfactual_explanation(
        self,
        input_features: Union[np.ndarray, Dict[str, Any]],
        decision: Any,
        predict_fn: Optional[Callable],
        level: ExplanationLevel
    ) -> Explanation:
        """Generate counterfactual explanation."""
        # Convert to dict if needed
        if isinstance(input_features, np.ndarray):
            features_dict = {
                self.feature_names[i]: input_features[i]
                for i in range(min(len(self.feature_names), len(input_features)))
            }
        else:
            features_dict = input_features

        counterfactuals = []

        # Try to generate counterfactuals for alternative decisions
        if predict_fn is not None and self.decision_space:
            for alt_decision in self.decision_space:
                if alt_decision != decision:
                    cf = self.counterfactual_gen.generate_counterfactual(
                        features_dict,
                        predict_fn,
                        alt_decision
                    )
                    if cf:
                        counterfactuals.append(cf)
                        self.stats.counterfactuals_generated += 1

                    if len(counterfactuals) >= 3:
                        break

        # Generate summary
        if counterfactuals:
            best_cf = min(counterfactuals, key=lambda c: len(c.changes_required))
            summary = (
                f"Decision: {decision}. "
                f"To get {best_cf.counterfactual_outcome} instead, "
                f"would need: {'; '.join(best_cf.changes_required[:2])}."
            )

            detailed_parts = [summary, "\nAlternative scenarios:"]
            for cf in counterfactuals:
                detailed_parts.append(
                    f"\n  To achieve '{cf.counterfactual_outcome}':"
                )
                for change in cf.changes_required:
                    detailed_parts.append(f"    - {change}")
                detailed_parts.append(f"    Feasibility: {cf.feasibility:.0%}")

            detailed = "\n".join(detailed_parts)
        else:
            summary = f"Decision: {decision}. No viable alternatives found."
            detailed = summary

        self.stats.total_explanations += 1

        return Explanation(
            explanation_type=ExplanationType.COUNTERFACTUAL,
            decision=decision,
            summary=summary,
            detailed_text=detailed,
            confidence=0.7,
            counterfactuals=counterfactuals,
            timestamp=self.timestamp
        )

    def explain_decision_process(
        self,
        input_features: Any,
        decision: Any,
        predict_fn: Optional[Callable] = None,
        include_counterfactuals: bool = True
    ) -> Dict[str, Explanation]:
        """
        Generate multiple types of explanations for a decision.

        Args:
            input_features: Input features
            decision: Decision made
            predict_fn: Prediction function
            include_counterfactuals: Whether to include counterfactuals

        Returns:
            Dictionary of explanations by type
        """
        explanations = {}

        # Chain of thought
        explanations['reasoning'] = self.generate_explanation(
            input_features, decision,
            explanation_type=ExplanationType.CHAIN_OF_THOUGHT
        )

        # Feature attribution
        if predict_fn:
            explanations['features'] = self.generate_explanation(
                input_features, decision, predict_fn,
                explanation_type=ExplanationType.FEATURE_ATTRIBUTION
            )

        # Counterfactuals
        if include_counterfactuals and predict_fn:
            explanations['counterfactuals'] = self.generate_explanation(
                input_features, decision, predict_fn,
                explanation_type=ExplanationType.COUNTERFACTUAL
            )

        return explanations

    def generate_natural_language_explanation(
        self,
        input_features: Any,
        decision: Any,
        context: Optional[str] = None
    ) -> str:
        """
        Generate a natural language explanation suitable for end users.

        Args:
            input_features: Input features
            decision: Decision made
            context: Optional context for the explanation

        Returns:
            Human-readable explanation
        """
        # Get reasoning chain
        chain = self.cot_extractor.extract_chain()

        parts = []

        if context:
            parts.append(f"Given {context}:")

        parts.append(f"The system decided: {decision}")

        if chain:
            parts.append("\nReasoning:")
            for step in chain[-5:]:  # Last 5 steps
                parts.append(f"  • {step.description}")

                if step.confidence < 0.7:
                    parts.append(f"    (with some uncertainty)")

        return "\n".join(parts)

    def get_explanation_for_audit(
        self,
        input_features: Any,
        decision: Any,
        predict_fn: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive audit trail for a decision.

        Returns structured data suitable for logging/compliance.
        """
        explanations = self.explain_decision_process(
            input_features, decision, predict_fn
        )

        return {
            'timestamp': self.timestamp,
            'decision': decision,
            'input_summary': str(input_features)[:200],
            'reasoning_chain': [
                {
                    'step': s.step_number,
                    'description': s.description,
                    'confidence': s.confidence
                }
                for s in explanations.get('reasoning', Explanation(
                    ExplanationType.CHAIN_OF_THOUGHT, decision, '', '', 0
                )).reasoning_steps
            ],
            'key_features': [
                {
                    'name': f.feature_name,
                    'contribution': f.contribution
                }
                for f in explanations.get('features', Explanation(
                    ExplanationType.FEATURE_ATTRIBUTION, decision, '', '', 0
                )).feature_contributions[:5]
            ],
            'alternatives_considered': [
                cf.counterfactual_outcome
                for cf in explanations.get('counterfactuals', Explanation(
                    ExplanationType.COUNTERFACTUAL, decision, '', '', 0
                )).counterfactuals
            ],
            'overall_confidence': np.mean([
                exp.confidence for exp in explanations.values()
            ]) if explanations else 0.5
        }

    def clear_reasoning_history(self):
        """Clear the reasoning history."""
        self.cot_extractor.clear()


def create_explainer(
    feature_names: List[str],
    decision_space: Optional[List[Any]] = None,
    feature_ranges: Optional[Dict[str, Tuple[float, float]]] = None
) -> ExplanationGenerator:
    """
    Factory function to create an explanation generator.

    Args:
        feature_names: Names of input features
        decision_space: Possible decisions
        feature_ranges: Valid ranges for each feature

    Returns:
        Configured ExplanationGenerator
    """
    return ExplanationGenerator(
        feature_names=feature_names,
        decision_space=decision_space,
        feature_ranges=feature_ranges
    )
