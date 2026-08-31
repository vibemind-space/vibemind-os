"""
Test LLM-Enhanced Hierarchical Planner

This shows how to integrate LLM-enhanced active inference
into the complete 12-phase cognitive system.

With LLM enhancement:
  - Questions are natural and context-aware
  - Hypotheses can be more diverse
  - Decision reasoning is more explainable

Run with mock LLM:
    python demos/test_llm_enhanced_planner.py

Run with real LLM:
    python demos/test_llm_enhanced_planner.py --use-llm --api-key YOUR_KEY
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
from typing import Dict, List

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor
from core.llm_enhanced_inference import LLM_Enhanced_ActiveInference


class MockLLM:
    """Mock LLM for testing"""

    def generate(self, prompt: str) -> str:
        """Generate mock response"""
        # For Docker task
        if "docker" in prompt.lower() and "container" in prompt.lower():
            return json.dumps([
                {
                    "question": "Do you want to list all containers (including stopped ones) or only running containers?",
                    "purpose": "Clarify the scope of Docker container listing",
                    "expected_info_gain": 0.7
                },
                {
                    "question": "Should I retrieve logs for all containers, or only for specific ones?",
                    "purpose": "Understand log retrieval scope to avoid large data fetches",
                    "expected_info_gain": 0.6
                }
            ])

        # For GitHub task
        elif "github" in prompt.lower() or "pull request" in prompt.lower():
            return json.dumps([
                {
                    "question": "Would you like me to review the code changes and provide feedback, or just merge it?",
                    "purpose": "Clarify whether review is needed",
                    "expected_info_gain": 0.8
                },
                {
                    "question": "Should I wait for CI checks to pass before merging?",
                    "purpose": "Safety check for merge process",
                    "expected_info_gain": 0.6
                }
            ])

        # For file cleanup task
        elif "clean" in prompt.lower() or "delete" in prompt.lower():
            return json.dumps([
                {
                    "question": "Should I delete files immediately, or would you like to review them first?",
                    "purpose": "Safety check before deletion",
                    "expected_info_gain": 0.9
                }
            ])

        # Generic
        else:
            return json.dumps([
                {
                    "question": "Could you provide more details about what you'd like me to do?",
                    "purpose": "Get clarification on task intent",
                    "expected_info_gain": 0.5
                }
            ])


def create_llm_enhanced_planner(use_real_llm=False):
    """
    Create hierarchical planner with LLM-enhanced active inference
    """
    print("[1/3] Initializing LLM-enhanced cognitive system...")
    print()

    # Create LLM client
    if use_real_llm:
        print("  Using REAL LLM via vibemind_shared (brain_planning role)")
        try:
            from vibemind_shared import get_client_sync
            llm = get_client_sync("brain_planning")
        except Exception as e:
            print(f"  [ERROR] vibemind_shared get_client_sync failed: {e}")
            print("  Falling back to mock LLM")
            llm = MockLLM()
    else:
        print("  Using MOCK LLM (demonstration)")
        llm = MockLLM()

    print()

    # Create LLM-enhanced active inference
    llm_inference = LLM_Enhanced_ActiveInference(
        llm_client=llm,
        use_llm_for={
            'question_generation': True,      # Enable LLM for questions
            'hypothesis_generation': False,   # Keep cognitive (faster)
            'decision_reasoning': False       # Keep cognitive (faster)
        },
        max_hypotheses=5,
        max_questions=3,
        ask_threshold=0.7
    )

    # Initialize Layer 2
    meta_router = MetaRouter(enable_hippocampus=True, seed=42)
    planner_layer2 = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=StrategyLibrary(),
        brain_monitor=BrainActivityMonitor()
    )

    # Optional: Train from sessions
    session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    if os.path.exists(session_dir):
        print(f"  Training from sessions...")
        planner_layer2.train_from_sessions(session_dir, limit=20)
        print(f"  [OK] Trained on 20 sessions")
    else:
        print(f"  [SKIP] No training data available")

    print()

    # Create hierarchical planner
    # NOTE: We'll manually replace the active_inference module after creation
    planner = HierarchicalPlanner(
        conversation_planner=planner_layer2,
        intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
        enable_memory=True,
        enable_predictive_coding=True,
        enable_attention=True,
        enable_meta_learning=True,
        enable_dream_mode=True,
        enable_neuromodulation=True,
        enable_temporal_memory=True,
        enable_active_inference=True,
        enable_compositional_reasoning=True,
        enable_tool_creation=True,
        enable_consciousness_metrics=True,
        enable_multi_brain_swarm=True,
        num_swarm_brains=5,
        seed=42
    )

    # Replace with LLM-enhanced inference
    planner.active_inference = llm_inference

    print(f"  [OK] LLM-enhanced hierarchical planner created")
    print(f"  [OK] LLM enabled for: question generation")
    print()

    return planner


def test_task(planner, task_description):
    """
    Test a single task with LLM-enhanced planner
    """
    print(f"Task: '{task_description}'")
    print("-" * 70)

    # Make prediction
    prediction = planner.predict(task_description)

    # Extract decision
    decision_dict = prediction.actionable_decision.multi_target_decision
    primary_decision = decision_dict['primary']

    # Show decision
    print(f"Decision: {primary_decision['type'].upper()}")
    print(f"Confidence: {primary_decision['weight']:.1%}")
    print(f"Processing time: {prediction.total_processing_time*1000:.1f}ms")
    print()

    # Show active inference results
    if prediction.inference_state:
        inf = prediction.inference_state
        print(f"Active Inference (with LLM enhancement):")
        print(f"  Hypotheses: {len(inf.hypotheses)}")
        print(f"  Total uncertainty: {inf.total_uncertainty:.2f}")
        print(f"  Should ask question: {inf.should_ask_question}")
        print()

        # Show questions (LLM-enhanced!)
        if inf.questions:
            print(f"  LLM-Enhanced Questions ({len(inf.questions)} generated):")
            for i, q in enumerate(inf.questions, 1):
                print(f"    {i}. {q.question_text}")
                print(f"       Type: {q.question_type}, Info gain: {q.expected_information_gain:.2f}")
            print()
        else:
            print(f"  No questions needed (uncertainty below threshold)")
            print()

    print()


def main():
    parser = argparse.ArgumentParser(description="Test LLM-enhanced hierarchical planner")
    parser.add_argument('--use-llm', action='store_true', help='Use real LLM via vibemind_shared (set keys in .env)')
    args = parser.parse_args()

    print()
    print("=" * 70)
    print("LLM-ENHANCED HIERARCHICAL PLANNER TEST")
    print("=" * 70)
    print()
    print("This demonstrates the complete cognitive system with LLM enhancement")
    print("for natural question generation.")
    print()

    # Create planner
    planner = create_llm_enhanced_planner(use_real_llm=args.use_llm)

    print("[2/3] Testing with real tasks...")
    print("=" * 70)
    print()

    # Test tasks
    test_tasks = [
        "list all my containers in docker and get the logs",
        "review and merge the pull request on GitHub",
        "clean up temporary files in /tmp directory"
    ]

    for i, task in enumerate(test_tasks, 1):
        print(f"Test {i}/{len(test_tasks)}:")
        print()
        test_task(planner, task)

    print()
    print("[3/3] Statistics")
    print("=" * 70)
    print()

    # Get LLM statistics
    if hasattr(planner.active_inference, 'get_llm_statistics'):
        llm_stats = planner.active_inference.get_llm_statistics()
        print("LLM Usage:")
        print(f"  Total LLM calls: {llm_stats['llm_calls']}")
        print(f"  Fallbacks to cognitive: {llm_stats['llm_fallbacks']}")
        print(f"  Success rate: {llm_stats['llm_success_rate']:.1%}")
        print()

    # Get active inference statistics
    ai_stats = planner.active_inference.get_statistics()
    print("Active Inference:")
    print(f"  Hypotheses generated: {ai_stats['total_hypotheses_generated']}")
    print(f"  Questions asked: {ai_stats['total_questions_asked']}")
    print()

    # Get overall statistics
    planner_stats = planner.get_statistics()
    print("Overall System:")
    print(f"  Total predictions: {planner_stats['total_predictions']}")
    if 'memory_stats' in planner_stats:
        print(f"  Working memory: {planner_stats['memory_stats']['working_memory_size']} items")
    print()

    print()
    print("=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print()
    print("The LLM-enhanced system:")
    print("  [+] Generates natural, context-aware questions")
    print("  [+] Understands task semantics (Docker, GitHub, etc.)")
    print("  [+] Asks about real ambiguities")
    print("  [+] Falls back to cognitive if LLM fails")
    print()
    print("Performance:")
    print("  - Cognitive-only: ~3ms per prediction")
    print("  - LLM-enhanced: ~100ms per prediction (only when questions needed)")
    print("  - Hybrid approach: Fast routing + Smart questions")
    print()
    print("Next steps:")
    print("  1. Add your Anthropic API key to use real LLM")
    print("  2. Enable LLM for hypothesis generation (slower but more diverse)")
    print("  3. Enable LLM for decision reasoning (natural explanations)")
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
