"""
Compare Cognitive-Only vs LLM-Enhanced Question Generation

This demo shows the difference between:
1. Template-based cognitive question generation (fast, deterministic)
2. LLM-enhanced question generation (natural, context-aware)

Run with real LLM:
    python demos/compare_cognitive_vs_llm.py --use-llm --api-key YOUR_KEY

Run with mock LLM (demonstration):
    python demos/compare_cognitive_vs_llm.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import time
from typing import List

from core.active_inference import ActiveInference, Hypothesis
from core.llm_enhanced_inference import LLM_Enhanced_ActiveInference


class MockLLM:
    """
    Mock LLM for demonstration purposes
    Shows what LLM-enhanced questions would look like
    """

    def generate(self, prompt: str) -> str:
        """
        Generate mock LLM response based on prompt content
        """
        # Parse the task from prompt
        if "list all my containers in docker" in prompt.lower():
            return json.dumps([
                {
                    "question": "Do you want to list all containers (including stopped ones) or only running containers?",
                    "purpose": "Clarify scope: Docker commands behave differently with --all flag",
                    "expected_info_gain": 0.7
                },
                {
                    "question": "Should I retrieve logs for all containers, or do you want logs for specific containers?",
                    "purpose": "Understand output scope: fetching all logs could be large dataset",
                    "expected_info_gain": 0.6
                }
            ])

        elif "deploy" in prompt.lower() and "production" in prompt.lower():
            return json.dumps([
                {
                    "question": "Do you want me to proceed with deployment now, or would you like to review the deployment plan first?",
                    "purpose": "Safety check: production deployments should be confirmed",
                    "expected_info_gain": 0.8
                },
                {
                    "question": "Should I run health checks after deployment, or just complete the deployment?",
                    "purpose": "Clarify post-deployment actions",
                    "expected_info_gain": 0.5
                }
            ])

        else:
            # Generic response
            return json.dumps([
                {
                    "question": "Could you clarify what you'd like me to focus on first?",
                    "purpose": "Understand task priorities",
                    "expected_info_gain": 0.5
                }
            ])


def create_mock_hypotheses() -> List[Hypothesis]:
    """
    Create mock hypotheses for Docker task
    """
    return [
        Hypothesis(
            hypothesis_id="h1",
            description="List all containers including stopped ones, then get logs for each",
            task_type="docker",
            decision_type="wait",
            prior_probability=0.4,
            posterior_probability=0.42,
            epistemic_uncertainty=0.7,  # High - should trigger question
            aleatoric_uncertainty=0.3
        ),
        Hypothesis(
            hypothesis_id="h2",
            description="List only running containers, get logs for running ones only",
            task_type="docker",
            decision_type="execute",
            prior_probability=0.35,
            posterior_probability=0.38,
            epistemic_uncertainty=0.6,
            aleatoric_uncertainty=0.2
        ),
        Hypothesis(
            hypothesis_id="h3",
            description="Get container status and recent logs summary",
            task_type="docker",
            decision_type="suggest",
            prior_probability=0.25,
            posterior_probability=0.20,
            epistemic_uncertainty=0.5,
            aleatoric_uncertainty=0.4
        )
    ]


def demo_cognitive_only():
    """
    Demonstrate cognitive-only (template-based) question generation
    """
    print("=" * 70)
    print("COGNITIVE-ONLY QUESTION GENERATION")
    print("=" * 70)
    print()

    # Create cognitive system
    inference = ActiveInference(
        max_hypotheses=5,
        max_questions=3,
        ask_threshold=0.7
    )

    # Task
    task = "list all my containers in docker and get the logs"
    print(f"Task: '{task}'")
    print()

    # Generate hypotheses (mock)
    hypotheses = create_mock_hypotheses()
    print(f"Generated {len(hypotheses)} hypotheses:")
    for i, h in enumerate(hypotheses, 1):
        print(f"  {i}. {h.description}")
        print(f"     Decision: {h.decision_type}, Probability: {h.posterior_probability:.1%}")
        print(f"     Epistemic uncertainty: {h.epistemic_uncertainty:.2f}")
    print()

    # Generate questions
    start_time = time.time()
    questions = inference.generate_questions(hypotheses, task)
    elapsed = (time.time() - start_time) * 1000

    print(f"Questions generated ({elapsed:.1f}ms):")
    print("-" * 70)
    for i, q in enumerate(questions, 1):
        print(f"{i}. {q.question_text}")
        print(f"   Type: {q.question_type}")
        print(f"   Info gain: {q.expected_information_gain:.2f}")
        print()

    print("Characteristics:")
    print("  [+] Fast: ~1ms")
    print("  [+] Deterministic: same input -> same questions")
    print("  [+] No external dependencies")
    print("  [-] Template-based: repetitive patterns")
    print("  [-] Limited context understanding")
    print("  [-] Can generate redundant questions (e.g., 'docker or docker?')")
    print()


def demo_llm_enhanced(use_real_llm=False, api_key=None):
    """
    Demonstrate LLM-enhanced question generation
    """
    print("=" * 70)
    print("LLM-ENHANCED QUESTION GENERATION")
    print("=" * 70)
    print()

    # Create LLM client (mock or real)
    if use_real_llm and api_key:
        print("Using REAL LLM (Anthropic Claude)")
        try:
            from anthropic import Anthropic
            llm = Anthropic(api_key=api_key)
        except ImportError:
            print("  [ERROR] anthropic package not installed")
            print("  Install with: pip install anthropic")
            return
    else:
        print("Using MOCK LLM (demonstration)")
        llm = MockLLM()

    print()

    # Create LLM-enhanced system
    inference = LLM_Enhanced_ActiveInference(
        llm_client=llm,
        use_llm_for={
            'question_generation': True,
            'hypothesis_generation': False,
            'decision_reasoning': False
        },
        max_hypotheses=5,
        max_questions=3,
        ask_threshold=0.7
    )

    # Task
    task = "list all my containers in docker and get the logs"
    print(f"Task: '{task}'")
    print()

    # Generate hypotheses (mock)
    hypotheses = create_mock_hypotheses()
    print(f"Generated {len(hypotheses)} hypotheses:")
    for i, h in enumerate(hypotheses, 1):
        print(f"  {i}. {h.description}")
        print(f"     Decision: {h.decision_type}, Probability: {h.posterior_probability:.1%}")
        print(f"     Epistemic uncertainty: {h.epistemic_uncertainty:.2f}")
    print()

    # Generate questions
    start_time = time.time()
    questions = inference.generate_questions(hypotheses, task)
    elapsed = (time.time() - start_time) * 1000

    print(f"Questions generated ({elapsed:.1f}ms):")
    print("-" * 70)
    for i, q in enumerate(questions, 1):
        print(f"{i}. {q.question_text}")
        print(f"   Type: {q.question_type}")
        print(f"   Info gain: {q.expected_information_gain:.2f}")
        print()

    print("Characteristics:")
    print("  [+] Natural: human-like phrasing")
    print("  [+] Context-aware: understands Docker semantics")
    print("  [+] Specific: addresses actual ambiguities")
    print("  [+] Intelligent: no redundant questions")
    print("  [-] Slower: ~100-500ms (LLM latency)")
    print("  [-] Non-deterministic: questions may vary")
    print("  [-] External dependency: requires LLM API")
    print("  [-] Cost: API calls cost money")
    print()

    # Show statistics
    stats = inference.get_llm_statistics()
    print("LLM Statistics:")
    print(f"  LLM calls: {stats['llm_calls']}")
    print(f"  Fallbacks: {stats['llm_fallbacks']}")
    print(f"  Success rate: {stats['llm_success_rate']:.1%}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Compare cognitive-only vs LLM-enhanced question generation")
    parser.add_argument('--use-llm', action='store_true', help='Use real LLM instead of mock')
    parser.add_argument('--api-key', type=str, help='Anthropic API key (if using real LLM)')
    parser.add_argument('--interactive', action='store_true', help='Use interactive prompts')
    args = parser.parse_args()

    print()
    print("=" * 70)
    print("COMPARISON: COGNITIVE-ONLY VS LLM-ENHANCED")
    print("=" * 70)
    print()
    print("This demo compares two approaches to question generation:")
    print("  1. Cognitive-only: Fast, deterministic, template-based")
    print("  2. LLM-enhanced: Natural, context-aware, intelligent")
    print()
    print("Task: 'list all my containers in docker and get the logs'")
    print()

    if args.interactive:
        input("Press Enter to see cognitive-only generation...")
    print()

    # Demo 1: Cognitive-only
    demo_cognitive_only()

    print()
    if args.interactive:
        input("Press Enter to see LLM-enhanced generation...")
    print()

    # Demo 2: LLM-enhanced
    demo_llm_enhanced(use_real_llm=args.use_llm, api_key=args.api_key)

    print()
    print("=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print()
    print("Cognitive-Only Questions:")
    print("  'Is this task primarily about docker or docker?'")
    print("  'Should I wait for this task, or is there a better action?'")
    print()
    print("LLM-Enhanced Questions:")
    print("  'Do you want to list all containers (including stopped ones) or only running containers?'")
    print("  'Should I retrieve logs for all containers, or do you want logs for specific containers?'")
    print()
    print("The LLM-enhanced version:")
    print("  - Understands Docker semantics (all vs running containers)")
    print("  - Asks about actual ambiguities (--all flag, log scope)")
    print("  - Phrases questions naturally")
    print("  - Avoids redundant questions")
    print()
    print("Trade-off:")
    print("  Cognitive: 1ms, free, deterministic")
    print("  LLM-enhanced: 100ms, costs ~$0.001/call, creative")
    print()
    print("Recommendation:")
    print("  Use HYBRID approach:")
    print("    - Cognitive routing for speed (3ms)")
    print("    - LLM enhancement for critical interactions (100ms)")
    print("    - Fallback to cognitive if LLM fails")
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
