"""
Chat Demo - Automated demonstration of brain chat functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from load_env import get_openrouter_key
from core.multi_llm_router import MultiLLMRouter
from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor
import time


def demo_chat():
    """Run automated demo of brain chat"""
    print("=" * 70)
    print("TAHLAMUS BRAIN CHAT - DEMO MODE")
    print("=" * 70)
    print()
    print("Initializing brain components...")
    print()

    # Initialize Multi-LLM Router
    llm_router = None
    try:
        api_key = get_openrouter_key()
        if api_key:
            llm_router = MultiLLMRouter(openrouter_api_key=api_key)
            mode = "DEV MODE" if llm_router.dev_mode else "PRODUCTION MODE"
            print(f"[OK] Multi-LLM Router initialized ({mode})")

            # Show configured models
            print("\nConfigured LLM Models:")
            for llm_name, config in llm_router.llm_configs.items():
                print(f"  - {llm_name}: {config.model}")
        else:
            print("[WARNING] Multi-LLM Router not available (no API key)")
    except Exception as e:
        print(f"[WARNING] Multi-LLM Router failed: {e}")

    # Initialize Hierarchical Planner
    planner = None
    try:
        print("\nInitializing Hierarchical Planner...")
        meta_router = MetaRouter(enable_hippocampus=True, seed=42)
        planner_layer2 = ConversationPathPlanner(
            meta_router=meta_router,
            strategy_library=StrategyLibrary(),
            brain_monitor=BrainActivityMonitor()
        )

        planner = HierarchicalPlanner(
            conversation_planner=planner_layer2,
            intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
            enable_memory=True,
            enable_active_inference=True,
            seed=42
        )
        print("[OK] Hierarchical Planner initialized")
    except Exception as e:
        print(f"[ERROR] Hierarchical Planner failed: {e}")
        return

    print()
    print("=" * 70)
    print("Running automated demo with test tasks...")
    print("=" * 70)
    print()

    # Test tasks
    test_tasks = [
        "Deploy Docker container to production",
        "List all running containers and get logs",
        "Search GitHub for Python ML examples"
    ]

    for i, task in enumerate(test_tasks, 1):
        print(f"\n{'=' * 70}")
        print(f"DEMO TASK {i}/{len(test_tasks)}")
        print(f"{'=' * 70}")
        print(f"\n> {task}\n")

        time.sleep(0.5)  # Pause for readability

        # Phase 1: Extract features with LLM
        if llm_router:
            try:
                print("[Phase 1] Extracting features with LLM...")
                features = llm_router.extract_features(task)
                print(f"  [OK] Task type: {features.get('task_type', 'unknown')}")
                print(f"  [OK] Complexity: {features.get('complexity', 0.5):.2f}")
                print(f"  [OK] Urgency: {features.get('urgency', 0.5):.2f}")
                if features.get('keywords'):
                    print(f"  [OK] Keywords: {', '.join(features['keywords'])}")
                print()
                time.sleep(0.3)
            except Exception as e:
                print(f"  [WARNING] LLM feature extraction failed: {e}")
                print()

        # Phase 2: Plan with hierarchical planner
        try:
            print("[Phase 2] Planning with hierarchical planner...")
            result = planner.predict(task)

            print(f"  [OK] Task type detected: {result.task_type}")
            print(f"  [OK] Confidence: {result.confidence:.1%}")

            if result.predicted_sequence:
                print(f"  [OK] Predicted sequence: {' -> '.join(result.predicted_sequence)}")

            if result.actionable_decision:
                print(f"  [OK] Action recommended: {result.actionable_decision.intervention_type}")
                if hasattr(result.actionable_decision, 'reasoning'):
                    print(f"  [OK] Reasoning: {result.actionable_decision.reasoning}")
            print()

            time.sleep(0.5)

        except Exception as e:
            print(f"  [ERROR] Planning failed: {e}")
            import traceback
            traceback.print_exc()
            print()

    # Final statistics
    if llm_router:
        print("\n" + "=" * 70)
        print("FINAL STATISTICS")
        print("=" * 70)
        print()

        try:
            stats = llm_router.get_statistics()
            print("[Multi-LLM Router]")
            print(f"  Mode: {'DEV' if llm_router.dev_mode else 'PRODUCTION'}")
            print(f"  Total calls: {stats['overall']['total_calls']}")
            print(f"  Total tokens: {stats['overall']['total_tokens_used']}")
            print(f"  Total cost: ${stats['overall']['total_estimated_cost_usd']:.6f}")
            print()

            # Per-model breakdown
            print("  Per-model breakdown:")
            for model_name, model_stats in stats.items():
                if model_name != 'overall' and model_stats['total_calls'] > 0:
                    print(f"    {model_name}:")
                    print(f"      Model: {model_stats['model']}")
                    print(f"      Calls: {model_stats['total_calls']}")
                    print(f"      Avg latency: {model_stats['avg_latency_ms']:.0f}ms")
                    print(f"      Cost: ${model_stats['estimated_cost_usd']:.6f}")
            print()
        except Exception as e:
            print(f"  Error getting statistics: {e}")
            print()

    print("=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print()
    print("To chat interactively, run: python chat_with_brain.py")
    print()


if __name__ == "__main__":
    demo_chat()
