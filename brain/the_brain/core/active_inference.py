"""
Active Inference System (PHASE 8)

Implements hypothesis generation and information-seeking behavior:

1. Hypothesis Generation:
   - Generate multiple hypotheses about task interpretation
   - Estimate uncertainty for each hypothesis
   - Track evidence supporting each hypothesis

2. Question Generation:
   - Identify information gaps
   - Generate clarifying questions
   - Prioritize questions by information gain

3. Active Information Seeking:
   - Decide when to ask vs. act
   - Track question-asking history
   - Learn which questions reduce uncertainty most

4. Hypothesis Selection:
   - Bayesian updating with new evidence
   - Select best hypothesis based on posterior probability
   - Handle contradictory evidence

Based on neuroscience research:
- Active inference framework (Friston, 2010)
- Free energy principle (Friston, 2006)
- Curiosity-driven learning (Schmidhuber, 2010)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Hypothesis:
    """
    A hypothesis about task interpretation or outcome
    """
    hypothesis_id: str
    description: str
    task_type: str
    decision_type: str

    # Probability estimates
    prior_probability: float = 0.5
    posterior_probability: float = 0.5

    # Evidence
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)

    # Uncertainty
    epistemic_uncertainty: float = 0.5  # Uncertainty due to lack of knowledge
    aleatoric_uncertainty: float = 0.3  # Inherent randomness

    # Metadata
    generation_time: float = 0.0
    updates: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'hypothesis_id': self.hypothesis_id,
            'description': self.description,
            'task_type': self.task_type,
            'decision_type': self.decision_type,
            'prior_probability': self.prior_probability,
            'posterior_probability': self.posterior_probability,
            'epistemic_uncertainty': self.epistemic_uncertainty,
            'aleatoric_uncertainty': self.aleatoric_uncertainty,
            'supporting_evidence': len(self.supporting_evidence),
            'contradicting_evidence': len(self.contradicting_evidence),
            'updates': self.updates
        }

    def total_uncertainty(self) -> float:
        """Total uncertainty (epistemic + aleatoric)"""
        return self.epistemic_uncertainty + self.aleatoric_uncertainty


@dataclass
class Question:
    """
    A clarifying question to reduce uncertainty
    """
    question_id: str
    question_text: str
    target_hypothesis: str  # Which hypothesis this would help resolve

    # Information gain
    expected_information_gain: float = 0.5
    uncertainty_reduction: float = 0.3

    # Context
    related_hypotheses: List[str] = field(default_factory=list)
    question_type: str = "clarification"  # clarification, confirmation, exploration

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'question_id': self.question_id,
            'question_text': self.question_text,
            'target_hypothesis': self.target_hypothesis,
            'expected_information_gain': self.expected_information_gain,
            'uncertainty_reduction': self.uncertainty_reduction,
            'question_type': self.question_type,
            'related_hypotheses': len(self.related_hypotheses)
        }


@dataclass
class InferenceState:
    """
    Current state of active inference
    """
    hypotheses: List[Hypothesis]
    questions: List[Question]

    # Current best hypothesis
    best_hypothesis: Optional[Hypothesis] = None

    # Uncertainty metrics
    total_uncertainty: float = 1.0
    max_uncertainty: float = 1.0

    # Decision
    should_ask_question: bool = False
    ask_threshold: float = 0.7

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'num_hypotheses': len(self.hypotheses),
            'num_questions': len(self.questions),
            'best_hypothesis': self.best_hypothesis.to_dict() if self.best_hypothesis else None,
            'total_uncertainty': self.total_uncertainty,
            'should_ask_question': self.should_ask_question,
            'ask_threshold': self.ask_threshold
        }


class ActiveInference:
    """
    Active inference system for hypothesis generation and information seeking

    Key features:
    - Generate multiple hypotheses
    - Estimate uncertainty
    - Generate clarifying questions
    - Bayesian updating with evidence
    """

    def __init__(
        self,
        ask_threshold: float = 0.7,  # Uncertainty threshold to ask question
        max_hypotheses: int = 5,  # Max hypotheses to maintain
        max_questions: int = 3,  # Max questions to generate
        learning_rate: float = 0.1  # Evidence update rate
    ):
        """
        Initialize active inference system

        Args:
            ask_threshold: Uncertainty threshold above which to ask questions
            max_hypotheses: Maximum number of hypotheses to track
            max_questions: Maximum number of questions to generate
            learning_rate: Learning rate for Bayesian updates
        """
        self.ask_threshold = ask_threshold
        self.max_hypotheses = max_hypotheses
        self.max_questions = max_questions
        self.learning_rate = learning_rate

        # History
        self.hypothesis_history: List[Hypothesis] = []
        self.question_history: List[Question] = []

        # Statistics
        self.total_hypotheses_generated = 0
        self.total_questions_asked = 0
        self.questions_that_helped = 0
        self.avg_uncertainty_reduction = 0.0

        # Question effectiveness
        self.question_effectiveness: Dict[str, List[float]] = defaultdict(list)

    def generate_hypotheses(
        self,
        task_description: str,
        task_type: str,
        brain_gates: np.ndarray,
        available_decisions: List[str],
        context: Optional[Dict] = None
    ) -> List[Hypothesis]:
        """
        Generate multiple hypotheses about task interpretation

        Args:
            task_description: Task description
            task_type: Inferred task type
            brain_gates: Brain gate activations
            available_decisions: Available decision types
            context: Optional context (memory, patterns, etc.)

        Returns:
            List of hypotheses
        """
        hypotheses = []

        # Hypothesis 1: Most confident interpretation (from brain gates)
        dominant_modality = int(np.argmax(brain_gates))
        primary_decision = available_decisions[0] if available_decisions else "wait"

        h1 = Hypothesis(
            hypothesis_id="h1_confident",
            description=f"Task is {task_type}, route through modality_{dominant_modality}, action: {primary_decision}",
            task_type=task_type,
            decision_type=primary_decision,
            prior_probability=float(np.max(brain_gates)),
            posterior_probability=float(np.max(brain_gates)),
            epistemic_uncertainty=0.3,  # Moderate uncertainty
            aleatoric_uncertainty=0.2
        )
        hypotheses.append(h1)

        # Hypothesis 2: Alternative interpretation (second-best modality)
        if len(brain_gates) > 1:
            second_best_idx = int(np.argsort(brain_gates)[-2])
            alt_decision = available_decisions[1] if len(available_decisions) > 1 else primary_decision

            h2 = Hypothesis(
                hypothesis_id="h2_alternative",
                description=f"Alternative: {task_type} via modality_{second_best_idx}, action: {alt_decision}",
                task_type=task_type,
                decision_type=alt_decision,
                prior_probability=float(brain_gates[second_best_idx]),
                posterior_probability=float(brain_gates[second_best_idx]),
                epistemic_uncertainty=0.5,  # Higher uncertainty
                aleatoric_uncertainty=0.3
            )
            hypotheses.append(h2)

        # Hypothesis 3: Conservative interpretation (if uncertain)
        if np.max(brain_gates) < 0.5:  # High uncertainty
            h3 = Hypothesis(
                hypothesis_id="h3_conservative",
                description=f"Uncertain about {task_type}, suggest wait/gather-info",
                task_type=task_type,
                decision_type="wait",
                prior_probability=0.3,
                posterior_probability=0.3,
                epistemic_uncertainty=0.7,  # Very uncertain
                aleatoric_uncertainty=0.2
            )
            hypotheses.append(h3)

        # Hypothesis 4: Memory-based interpretation (if context available)
        if context and 'similar_tasks' in context:
            similar_tasks = context['similar_tasks']
            if similar_tasks:
                # Use most similar past task
                most_similar = similar_tasks[0]
                memory_decision = most_similar.get('decision', primary_decision)

                h4 = Hypothesis(
                    hypothesis_id="h4_memory",
                    description=f"Based on similar past task: {task_type}, action: {memory_decision}",
                    task_type=task_type,
                    decision_type=memory_decision,
                    prior_probability=0.4,
                    posterior_probability=0.4,
                    epistemic_uncertainty=0.4,
                    aleatoric_uncertainty=0.2
                )
                h4.supporting_evidence.append(f"Similar task: {most_similar.get('task', 'unknown')}")
                hypotheses.append(h4)

        # Hypothesis 5: Pattern-based interpretation (if patterns available)
        if context and 'patterns' in context:
            patterns = context['patterns']
            if patterns:
                pattern = patterns[0]
                pattern_decision = pattern.get('decision', primary_decision)

                h5 = Hypothesis(
                    hypothesis_id="h5_pattern",
                    description=f"Pattern suggests: {task_type}, action: {pattern_decision}",
                    task_type=task_type,
                    decision_type=pattern_decision,
                    prior_probability=0.35,
                    posterior_probability=0.35,
                    epistemic_uncertainty=0.45,
                    aleatoric_uncertainty=0.25
                )
                h5.supporting_evidence.append(f"Pattern: {pattern.get('task_type', 'unknown')}")
                hypotheses.append(h5)

        # Limit to max_hypotheses
        hypotheses = hypotheses[:self.max_hypotheses]

        # Track statistics
        self.total_hypotheses_generated += len(hypotheses)
        self.hypothesis_history.extend(hypotheses)

        return hypotheses

    def generate_questions(
        self,
        hypotheses: List[Hypothesis],
        task_description: str
    ) -> List[Question]:
        """
        Generate clarifying questions to reduce uncertainty

        Args:
            hypotheses: Current hypotheses
            task_description: Task description

        Returns:
            List of questions
        """
        questions = []

        # Sort hypotheses by uncertainty
        sorted_hyps = sorted(hypotheses, key=lambda h: h.total_uncertainty(), reverse=True)

        # Question 1: Clarify task type (if uncertain)
        if len(hypotheses) > 1:
            top_hyps = sorted_hyps[:2]
            if abs(top_hyps[0].posterior_probability - top_hyps[1].posterior_probability) < 0.2:
                q1 = Question(
                    question_id="q1_task_type",
                    question_text=f"Is this task primarily about {top_hyps[0].task_type} or {top_hyps[1].task_type}?",
                    target_hypothesis=top_hyps[0].hypothesis_id,
                    expected_information_gain=0.5,
                    uncertainty_reduction=0.4,
                    question_type="clarification"
                )
                q1.related_hypotheses = [h.hypothesis_id for h in top_hyps]
                questions.append(q1)

        # Question 2: Confirm decision (if high epistemic uncertainty)
        most_uncertain = sorted_hyps[0]
        if most_uncertain.epistemic_uncertainty > 0.6:
            q2 = Question(
                question_id="q2_decision",
                question_text=f"Should I {most_uncertain.decision_type} for this task, or is there a better action?",
                target_hypothesis=most_uncertain.hypothesis_id,
                expected_information_gain=0.6,
                uncertainty_reduction=0.5,
                question_type="confirmation"
            )
            questions.append(q2)

        # Question 3: Explore alternatives (if multiple plausible hypotheses)
        plausible = [h for h in hypotheses if h.posterior_probability > 0.25]
        if len(plausible) >= 3:
            q3 = Question(
                question_id="q3_alternatives",
                question_text=f"Are there specific constraints or requirements I should know about for this task?",
                target_hypothesis="multiple",
                expected_information_gain=0.4,
                uncertainty_reduction=0.3,
                question_type="exploration"
            )
            q3.related_hypotheses = [h.hypothesis_id for h in plausible]
            questions.append(q3)

        # Limit to max_questions
        questions = questions[:self.max_questions]

        # Track statistics
        self.question_history.extend(questions)

        return questions

    def update_hypotheses_with_evidence(
        self,
        hypotheses: List[Hypothesis],
        evidence: Dict[str, any],
        evidence_type: str = "observation"
    ) -> List[Hypothesis]:
        """
        Update hypothesis probabilities with new evidence (Bayesian update)

        Args:
            hypotheses: Current hypotheses
            evidence: New evidence dictionary
            evidence_type: Type of evidence (observation, answer, outcome)

        Returns:
            Updated hypotheses
        """
        for hypothesis in hypotheses:
            # Compute likelihood of evidence given hypothesis
            likelihood = self._compute_likelihood(hypothesis, evidence, evidence_type)

            # Bayesian update: P(H|E) ∝ P(E|H) * P(H)
            prior = hypothesis.posterior_probability
            posterior = likelihood * prior

            # Update posterior (with learning rate for smoothing)
            hypothesis.posterior_probability = (
                (1 - self.learning_rate) * hypothesis.posterior_probability +
                self.learning_rate * posterior
            )

            # Update uncertainty (evidence reduces epistemic uncertainty)
            if abs(likelihood - 0.5) > 0.3:  # Strong evidence
                hypothesis.epistemic_uncertainty *= 0.8

            # Track evidence
            if likelihood > 0.5:
                hypothesis.supporting_evidence.append(str(evidence))
            else:
                hypothesis.contradicting_evidence.append(str(evidence))

            hypothesis.updates += 1

        # Normalize probabilities
        total_prob = sum(h.posterior_probability for h in hypotheses)
        if total_prob > 0:
            for h in hypotheses:
                h.posterior_probability /= total_prob

        return hypotheses

    def _compute_likelihood(
        self,
        hypothesis: Hypothesis,
        evidence: Dict,
        evidence_type: str
    ) -> float:
        """Compute likelihood P(E|H)"""
        # Simple likelihood computation based on evidence type
        if evidence_type == "outcome":
            # If outcome matches hypothesis prediction
            if evidence.get('outcome') == 'success':
                return 0.7
            else:
                return 0.3

        elif evidence_type == "answer":
            # If answer confirms hypothesis
            answer = evidence.get('answer', '')
            if hypothesis.task_type.lower() in answer.lower():
                return 0.8
            else:
                return 0.2

        else:  # observation
            # Generic observation likelihood
            return 0.5

    def select_best_hypothesis(
        self,
        hypotheses: List[Hypothesis]
    ) -> Hypothesis:
        """
        Select best hypothesis based on posterior probability

        Args:
            hypotheses: Current hypotheses

        Returns:
            Best hypothesis
        """
        if not hypotheses:
            # Return default hypothesis
            return Hypothesis(
                hypothesis_id="default",
                description="Default hypothesis",
                task_type="unknown",
                decision_type="wait"
            )

        # Select hypothesis with highest posterior
        best = max(hypotheses, key=lambda h: h.posterior_probability)

        return best

    def should_ask_question(
        self,
        hypotheses: List[Hypothesis]
    ) -> bool:
        """
        Decide whether to ask a question or proceed with action

        Args:
            hypotheses: Current hypotheses

        Returns:
            True if should ask question, False otherwise
        """
        if not hypotheses:
            return False

        # Compute total uncertainty
        avg_uncertainty = np.mean([h.total_uncertainty() for h in hypotheses])

        # Ask if uncertainty is high
        should_ask = avg_uncertainty > self.ask_threshold

        if should_ask:
            self.total_questions_asked += 1

        return should_ask

    def perform_inference(
        self,
        task_description: str,
        task_type: str,
        brain_gates: np.ndarray,
        available_decisions: List[str],
        context: Optional[Dict] = None
    ) -> InferenceState:
        """
        Complete inference cycle: generate hypotheses, questions, select best

        Args:
            task_description: Task description
            task_type: Inferred task type
            brain_gates: Brain gate activations
            available_decisions: Available decisions
            context: Optional context

        Returns:
            InferenceState with hypotheses and questions
        """
        # Generate hypotheses
        hypotheses = self.generate_hypotheses(
            task_description,
            task_type,
            brain_gates,
            available_decisions,
            context
        )

        # Generate questions
        questions = self.generate_questions(hypotheses, task_description)

        # Select best hypothesis
        best_hypothesis = self.select_best_hypothesis(hypotheses)

        # Compute total uncertainty
        total_uncertainty = np.mean([h.total_uncertainty() for h in hypotheses])
        max_uncertainty = max([h.total_uncertainty() for h in hypotheses]) if hypotheses else 1.0

        # Decide whether to ask
        should_ask = self.should_ask_question(hypotheses)

        # Create inference state
        inference_state = InferenceState(
            hypotheses=hypotheses,
            questions=questions,
            best_hypothesis=best_hypothesis,
            total_uncertainty=total_uncertainty,
            max_uncertainty=max_uncertainty,
            should_ask_question=should_ask,
            ask_threshold=self.ask_threshold
        )

        return inference_state

    def get_statistics(self) -> Dict:
        """Get active inference statistics"""
        # Question effectiveness
        avg_effectiveness = {}
        for q_type, effectiveness_list in self.question_effectiveness.items():
            if effectiveness_list:
                avg_effectiveness[q_type] = np.mean(effectiveness_list)

        return {
            'total_hypotheses_generated': self.total_hypotheses_generated,
            'total_questions_asked': self.total_questions_asked,
            'questions_that_helped': self.questions_that_helped,
            'avg_uncertainty_reduction': self.avg_uncertainty_reduction,
            'question_effectiveness': avg_effectiveness,
            'hypothesis_history_size': len(self.hypothesis_history),
            'question_history_size': len(self.question_history)
        }

    def __repr__(self):
        return (
            f"ActiveInference("
            f"hypotheses={self.total_hypotheses_generated}, "
            f"questions={self.total_questions_asked}, "
            f"threshold={self.ask_threshold:.2f})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("ACTIVE INFERENCE SYSTEM (PHASE 8)")
    print("=" * 70)
    print()
    print("This module implements active inference and hypothesis generation:")
    print("  - Generate multiple hypotheses about task interpretation")
    print("  - Estimate uncertainty for each hypothesis")
    print("  - Generate clarifying questions to reduce uncertainty")
    print("  - Bayesian updating with new evidence")
    print("  - Information-seeking behavior")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_active_inference.py")
    print()
    print("=" * 70)
