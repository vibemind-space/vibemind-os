"""
Chat with Brain - Interactive CLI for Tahlamus Cognitive System

This provides a simple chat interface to interact with the full cognitive system
including Multi-LLM Router integration.
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


class BrainChat:
    """Interactive chat interface for the Tahlamus brain"""

    def __init__(self):
        """Initialize brain components"""
        print("=" * 70)
        print("TAHLAMUS BRAIN CHAT")
        print("=" * 70)
        print()
        print("Initializing brain components...")

        # Initialize Multi-LLM Router
        try:
            api_key = get_openrouter_key()
            if api_key:
                self.llm_router = MultiLLMRouter(openrouter_api_key=api_key)
                print(f"✓ Multi-LLM Router initialized ({self.llm_router.dev_mode and 'DEV MODE' or 'PRODUCTION MODE'})")
            else:
                self.llm_router = None
                print("⚠ Multi-LLM Router not available (no API key)")
        except Exception as e:
            self.llm_router = None
            print(f"⚠ Multi-LLM Router failed: {e}")

        # Initialize Hierarchical Planner
        try:
            meta_router = MetaRouter(enable_hippocampus=True, seed=42)
            planner_layer2 = ConversationPathPlanner(
                meta_router=meta_router,
                strategy_library=StrategyLibrary(),
                brain_monitor=BrainActivityMonitor()
            )

            self.planner = HierarchicalPlanner(
                conversation_planner=planner_layer2,
                intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
                enable_memory=True,
                enable_active_inference=True,
                seed=42
            )
            print("✓ Hierarchical Planner initialized")
        except Exception as e:
            self.planner = None
            print(f"✗ Hierarchical Planner failed: {e}")
            return

        print()
        print("=" * 70)
        print("Brain ready! Type your tasks below.")
        print("Commands: 'quit', 'exit', 'stats', 'help'")
        print("=" * 70)
        print()

    def process_task(self, task: str):
        """Process a task through the cognitive system"""
        if not self.planner:
            print("[ERROR] Planner not initialized")
            return

        print()
        print("=" * 70)
        print(f"Processing: {task}")
        print("=" * 70)
        print()

        # Step 1: Extract features with LLM (if available)
        if self.llm_router:
            try:
                print("[Phase 1] Extracting features with LLM...")
                features = self.llm_router.extract_features(task)
                print(f"  Task type: {features.get('task_type', 'unknown')}")
                print(f"  Complexity: {features.get('complexity', 0.5):.2f}")
                print(f"  Urgency: {features.get('urgency', 0.5):.2f}")
                print()
            except Exception as e:
                print(f"  [Warning] LLM feature extraction failed: {e}")
                print()

        # Step 2: Plan with hierarchical planner
        try:
            print("[Phase 2] Planning with hierarchical planner...")
            result = self.planner.predict(task)

            print(f"  Recommended action: {result.recommended_action}")
            print(f"  Confidence: {result.confidence:.2%}")
            print(f"  Reasoning: {result.reasoning}")
            print()

            if result.questions:
                print("  Questions generated:")
                for i, q in enumerate(result.questions, 1):
                    print(f"    {i}. {q.question_text}")
                print()

            if result.suggested_plan:
                print(f"  Suggested plan: {' -> '.join(result.suggested_plan)}")
                print()

        except Exception as e:
            print(f"  [Error] Planning failed: {e}")
            import traceback
            traceback.print_exc()
            print()

        # Step 3: Show LLM stats if available
        if self.llm_router:
            try:
                stats = self.llm_router.get_statistics()
                print("[LLM Statistics]")
                print(f"  Total calls: {stats['overall']['total_calls']}")
                print(f"  Total cost: ${stats['overall']['total_estimated_cost_usd']:.6f}")
                print()
            except (AttributeError, KeyError, TypeError):
                pass

        print("=" * 70)

    def show_stats(self):
        """Show system statistics"""
        print()
        print("=" * 70)
        print("SYSTEM STATISTICS")
        print("=" * 70)
        print()

        # LLM stats
        if self.llm_router:
            try:
                stats = self.llm_router.get_statistics()
                print("[Multi-LLM Router]")
                print(f"  Mode: {'DEV' if self.llm_router.dev_mode else 'PRODUCTION'}")
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
                        print(f"      Cost: ${model_stats['estimated_cost_usd']:.6f}")
                print()
            except Exception as e:
                print(f"[Multi-LLM Router] Error: {e}")
                print()
        else:
            print("[Multi-LLM Router] Not initialized")
            print()

        print("=" * 70)

    def show_help(self):
        """Show help message"""
        print()
        print("=" * 70)
        print("HELP")
        print("=" * 70)
        print()
        print("Commands:")
        print("  quit, exit  - Exit the chat")
        print("  stats       - Show system statistics")
        print("  help        - Show this help message")
        print()
        print("Example tasks:")
        print("  'Deploy Docker container to production'")
        print("  'List all running containers and get logs'")
        print("  'Search GitHub for Python examples'")
        print("  'Read file config.yaml and parse it'")
        print()
        print("The brain will:")
        print("  1. Extract features using LLM (DeepSeek R1 in dev mode)")
        print("  2. Plan actions using hierarchical planner")
        print("  3. Generate clarifying questions if needed")
        print("  4. Track costs and statistics")
        print()
        print("=" * 70)

    def run(self):
        """Run the interactive chat loop"""
        if not self.planner:
            print("[ERROR] Cannot start chat - planner failed to initialize")
            return

        while True:
            try:
                # Get user input
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ['quit', 'exit']:
                    print("\nGoodbye!")
                    break

                elif user_input.lower() == 'stats':
                    self.show_stats()

                elif user_input.lower() == 'help':
                    self.show_help()

                else:
                    # Process as a task
                    self.process_task(user_input)

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break

            except Exception as e:
                print(f"\n[ERROR] {e}")
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    chat = BrainChat()
    chat.run()
