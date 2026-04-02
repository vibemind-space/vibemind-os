"""
LLM-Enhanced Active Inference (PHASE 8+)

Combines cognitive routing with LLM intelligence for:
- Natural question generation
- Context-aware hypothesis generation
- Intelligent decision reasoning
- Creative plan composition

This is a HYBRID approach:
- Cognitive system provides fast, structured reasoning
- LLM adds natural language intelligence and creativity
"""

from typing import Dict, List, Optional
import json

from core.active_inference import ActiveInference, Hypothesis, Question


class LLM_Enhanced_ActiveInference(ActiveInference):
    """
    Enhanced Active Inference with optional LLM capabilities

    Falls back to cognitive-only if LLM unavailable
    """

    def __init__(
        self,
        llm_client=None,  # Optional: Anthropic, OpenAI, etc.
        use_llm_for: Optional[Dict[str, bool]] = None,
        **kwargs
    ):
        """
        Initialize LLM-enhanced active inference

        Args:
            llm_client: Optional LLM client (Anthropic Claude, OpenAI, etc.)
            use_llm_for: Dict specifying which components use LLM
            **kwargs: Passed to parent ActiveInference
        """
        super().__init__(**kwargs)

        self.llm = llm_client
        self.use_llm_for = use_llm_for or {
            'question_generation': True,
            'hypothesis_generation': False,  # Keep cognitive for speed
            'decision_reasoning': False,
            'plan_composition': False
        }

        # Track LLM usage
        self.llm_calls = 0
        self.llm_fallbacks = 0

    def generate_questions(
        self,
        hypotheses: List[Hypothesis],
        task_description: str
    ) -> List[Question]:
        """
        Generate questions using LLM or fallback to template-based
        """
        # Try LLM if enabled and available
        if self.use_llm_for.get('question_generation') and self.llm:
            try:
                return self._llm_generate_questions(hypotheses, task_description)
            except Exception as e:
                print(f"[LLM] Question generation failed, using template fallback: {e}")
                self.llm_fallbacks += 1

        # Fallback to parent's template-based generation
        return super().generate_questions(hypotheses, task_description)

    def _llm_generate_questions(
        self,
        hypotheses: List[Hypothesis],
        task_description: str
    ) -> List[Question]:
        """
        Use LLM to generate intelligent, context-aware questions
        """
        self.llm_calls += 1

        # Build context for LLM
        hyp_descriptions = []
        for i, h in enumerate(hypotheses[:3], 1):  # Top 3
            hyp_descriptions.append(
                f"{i}. {h.description}\n"
                f"   - Probability: {h.posterior_probability:.1%}\n"
                f"   - Uncertainty: {h.total_uncertainty():.2f}\n"
                f"   - Suggested action: {h.decision_type}"
            )

        # Compute average uncertainty
        avg_uncertainty = sum(h.total_uncertainty() for h in hypotheses) / len(hypotheses)

        # LLM prompt for question generation
        prompt = f"""You are a cognitive assistant helping to understand user intent.

TASK: "{task_description}"

CURRENT INTERPRETATIONS (hypotheses):
{chr(10).join(hyp_descriptions)}

UNCERTAINTY LEVEL: {avg_uncertainty:.2f} (0=certain, 1=very uncertain)

Your goal: Generate 1-2 intelligent clarifying questions that would:
1. Help distinguish between competing interpretations
2. Reduce uncertainty about what the user wants
3. Be natural and specific to this task

Requirements:
- Questions should be concise (one sentence each)
- Focus on the most ambiguous aspects
- Help decide between different actions
- Don't ask obvious things

Return ONLY a JSON array of questions:
[
  {{
    "question": "Your question here?",
    "purpose": "Why this question helps",
    "expected_info_gain": 0.0-1.0
  }}
]
"""

        # Call LLM (example with Anthropic Claude API)
        try:
            response = self._call_llm(prompt)
            llm_questions_data = json.loads(response)

            # Convert to Question objects
            questions = []
            for i, q_data in enumerate(llm_questions_data[:self.max_questions]):
                question = Question(
                    question_id=f"llm_q{i+1}",
                    question_text=q_data['question'],
                    target_hypothesis=hypotheses[0].hypothesis_id if hypotheses else "unknown",
                    expected_information_gain=q_data.get('expected_info_gain', 0.5),
                    uncertainty_reduction=q_data.get('expected_info_gain', 0.5) * 0.8,
                    question_type="llm_generated"
                )
                questions.append(question)

            # Track in history
            self.question_history.extend(questions)

            return questions

        except Exception as e:
            print(f"[LLM] JSON parsing failed: {e}")
            raise

    def _call_llm(self, prompt: str) -> str:
        """
        Call LLM API (abstracted for different providers)

        Examples:
        - MultiLLMRouter: router.route(...)
        - Anthropic Claude: anthropic.messages.create(...)
        - OpenAI: openai.chat.completions.create(...)
        - Local: ollama.generate(...)
        """
        if not self.llm:
            raise ValueError("LLM client not configured")

        # MultiLLMRouter (preferred!)
        if hasattr(self.llm, 'route'):
            return self.llm.route('question_generation', prompt, temperature=0.8)

        # Example for Anthropic Claude
        elif hasattr(self.llm, 'messages'):
            response = self.llm.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text

        # Example for OpenAI
        elif hasattr(self.llm, 'chat'):
            response = self.llm.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content

        # Generic interface
        else:
            return self.llm.generate(prompt)

    def generate_hypotheses_llm(
        self,
        task_description: str,
        task_type: str,
        brain_gates,
        available_decisions: List[str],
        context: Optional[Dict] = None
    ) -> List[Hypothesis]:
        """
        Use LLM to generate diverse, context-aware hypotheses
        (Optional - can be enabled in use_llm_for config)
        """
        self.llm_calls += 1

        prompt = f"""You are analyzing a task to generate multiple plausible interpretations.

TASK: "{task_description}"
TASK TYPE: {task_type}
AVAILABLE ACTIONS: {', '.join(available_decisions)}

Generate 3-4 different interpretations of what the user might want.
Consider different:
- Scopes (all vs specific items)
- Depths (surface vs detailed)
- Outputs (what information to return)
- Actions (observe vs modify)

Return JSON array:
[
  {{
    "description": "Interpretation description",
    "decision_type": "suggest|wait|execute|retry|terminate",
    "confidence": 0.0-1.0,
    "reasoning": "Why this interpretation makes sense"
  }}
]
"""

        try:
            response = self._call_llm(prompt)
            llm_hyps = json.loads(response)

            # Convert to Hypothesis objects
            hypotheses = []
            for i, h_data in enumerate(llm_hyps[:self.max_hypotheses]):
                hypothesis = Hypothesis(
                    hypothesis_id=f"llm_h{i+1}",
                    description=h_data['description'],
                    task_type=task_type,
                    decision_type=h_data['decision_type'],
                    prior_probability=h_data['confidence'],
                    posterior_probability=h_data['confidence'],
                    epistemic_uncertainty=0.3,  # Medium uncertainty for LLM hypotheses
                    aleatoric_uncertainty=0.2
                )
                hypotheses.append(hypothesis)

            self.total_hypotheses_generated += len(hypotheses)
            self.hypothesis_history.extend(hypotheses)

            return hypotheses

        except Exception as e:
            print(f"[LLM] Hypothesis generation failed, using cognitive fallback: {e}")
            self.llm_fallbacks += 1
            # Fallback to parent's pattern-based generation
            return super().generate_hypotheses(
                task_description, task_type, brain_gates,
                available_decisions, context
            )

    def get_llm_statistics(self) -> Dict:
        """Get LLM usage statistics"""
        return {
            'llm_calls': self.llm_calls,
            'llm_fallbacks': self.llm_fallbacks,
            'llm_success_rate': (self.llm_calls - self.llm_fallbacks) / max(1, self.llm_calls),
            'llm_enabled_for': self.use_llm_for
        }


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("LLM-ENHANCED ACTIVE INFERENCE")
    print("=" * 70)
    print()
    print("This combines:")
    print("  - Fast cognitive routing (3ms)")
    print("  - Intelligent LLM enhancement (100ms)")
    print()
    print("LLM is used for:")
    print("  ✓ Natural question generation")
    print("  ✓ Context-aware hypotheses (optional)")
    print("  ✓ Intelligent reasoning (optional)")
    print()
    print("Benefits:")
    print("  - More natural interactions")
    print("  - Better context understanding")
    print("  - Creative problem solving")
    print()
    print("To use:")
    print("  # Option 1: Anthropic Claude")
    print("  from anthropic import Anthropic")
    print("  llm = Anthropic(api_key='...')")
    print()
    print("  # Option 2: OpenAI")
    print("  from openai import OpenAI")
    print("  llm = OpenAI(api_key='...')")
    print()
    print("  # Create enhanced inference")
    print("  inference = LLM_Enhanced_ActiveInference(")
    print("      llm_client=llm,")
    print("      use_llm_for={'question_generation': True}")
    print("  )")
    print()
    print("=" * 70)
