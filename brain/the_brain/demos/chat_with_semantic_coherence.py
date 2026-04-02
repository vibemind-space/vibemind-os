"""
Chat with Brain - With Semantic Coherence Integration

Shows how semantic coherence would work in chat:
- Multiple brain perspectives on your question
- Semantic coherence analysis
- Truth stability measurement
- Traffic light status (GREEN/YELLOW/RED)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.multi_brain_swarm import MultiBrainSwarm
from core.semantic_coherence import SemanticEncoder


class SemanticBrainChat:
    """Chat with semantic coherence analysis"""

    def __init__(self):
        """Initialize brain with semantic coherence"""
        print("=" * 70)
        print("TAHLAMUS BRAIN CHAT - WITH SEMANTIC COHERENCE")
        print("=" * 70)
        print()
        print("Initializing brain with semantic analysis...")

        # Create multi-brain swarm with semantic coherence
        self.swarm = MultiBrainSwarm(
            num_brains=5,
            enable_semantic_coherence=True,
            k_min=0.55,
            green_threshold=0.75,
            alpha=0.5
        )

        # Enable neural embeddings
        if self.swarm.semantic_layer:
            self.swarm.semantic_layer.encoder = SemanticEncoder(use_simple=False)
            print("[+] Neural embeddings enabled (sentence-transformers)")

        print(f"[+] Created swarm with {len(self.swarm.brains)} specialized brains")
        print()

        for brain_id, brain in self.swarm.brains.items():
            print(f"  - {brain.brain_name} (expertise: {brain.expertise_level:.2f})")

        print()
        print("=" * 70)
        print()

    def chat(self, user_message: str, show_details: bool = True):
        """
        Process user message with semantic coherence

        Args:
            user_message: User's question/task
            show_details: Show detailed breakdown
        """
        print(f"\n[YOU] {user_message}")
        print()

        # Determine task type from message
        task_type = self._classify_task(user_message)

        # Get decision from swarm
        decision = self.swarm.collect_brain_votes(
            task_description=user_message,
            task_type=task_type,
            available_decisions=["suggest", "retry", "wait", "terminate"]
        )

        # Show brain responses
        if show_details:
            print("[BRAIN] Responses:")
            print("-" * 70)

            for brain_id in decision.participating_brains:
                vote = decision.brain_votes[brain_id]
                confidence = decision.confidence_weights[brain_id]
                brain = self.swarm.brains[brain_id]

                print(f"  {brain.brain_name}:")
                print(f"    Decision: {vote}")
                print(f"    Confidence: {confidence:.2f}")
                print()

        # Show semantic coherence analysis
        print("[ANALYSIS] Semantic Coherence:")
        print("-" * 70)
        print(f"  Coherence K: {decision.coherence_K:.3f} (similarity between brains)")
        print(f"  Disagreement U: {decision.disagreement_U:.3f} (variance)")
        print(f"  Voting Score: {decision.consensus_confidence:.3f}")
        print(f"  Truth Stability: {decision.truth_stability:.3f}")
        print()

        # Show status with explanation
        status_emoji = {
            'GREEN': '[G]',
            'YELLOW': '[Y]',
            'RED': '[R]'
        }

        status_meaning = {
            'GREEN': "High confidence - Brains agree semantically",
            'YELLOW': "Medium confidence - Some uncertainty",
            'RED': "Low confidence - Clarification needed"
        }

        print(f"[STATUS] {status_emoji[decision.semantic_status]} {decision.semantic_status}")
        print(f"   {status_meaning[decision.semantic_status]}")
        print()

        # Show final recommendation
        print("[RECOMMENDATION]:")
        print("-" * 70)
        print(f"  Action: {decision.consensus_decision.upper()}")
        print(f"  Consensus: {decision.consensus_mechanism}")

        if decision.semantic_status == 'RED':
            print()
            print("  [!] Low coherence detected!")
            print("  The brains disagree on the best approach.")
            print("  Consider:")
            print("    - Clarifying your request")
            print("    - Providing more context")
            print("    - Breaking into smaller tasks")
        elif decision.semantic_status == 'GREEN':
            print()
            print("  [+] High coherence!")
            print("  The brains agree this is the right approach.")

        print()
        print("=" * 70)

        return decision

    def _classify_task(self, message: str) -> str:
        """Simple task classification"""
        message_lower = message.lower()

        if any(word in message_lower for word in ['docker', 'container', 'deploy']):
            return 'docker'
        elif any(word in message_lower for word in ['git', 'github', 'commit', 'merge']):
            return 'github'
        elif any(word in message_lower for word in ['file', 'directory', 'read', 'write']):
            return 'filesystem'
        elif any(word in message_lower for word in ['command', 'shell', 'execute', 'run']):
            return 'terminal'
        elif any(word in message_lower for word in ['network', 'port', 'connection']):
            return 'network'
        else:
            return 'general'

    def interactive_loop(self):
        """Interactive chat loop"""
        print("Type your questions/tasks. Type 'quit' to exit.")
        print("Add '--details' to see detailed brain responses.")
        print()

        while True:
            try:
                user_input = input("[YOU] ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\nGoodbye! 👋")
                    break

                # Check for --details flag
                show_details = '--details' in user_input
                user_input = user_input.replace('--details', '').strip()

                # Process message
                self.chat(user_input, show_details=show_details)

            except KeyboardInterrupt:
                print("\n\nGoodbye! 👋")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                print()


def demo_mode():
    """Run demo with predefined examples"""
    print("DEMO MODE: Testing with example tasks\n")

    chat = SemanticBrainChat()

    examples = [
        ("Deploy Docker container with health checks", True),
        ("Fix merge conflict in Git repository", True),
        ("Handle ambiguous production error", True)
    ]

    for task, show_details in examples:
        chat.chat(task, show_details=show_details)
        input("\nPress Enter for next example...")


def main():
    """Main entry point"""
    import sys

    if '--demo' in sys.argv:
        demo_mode()
    else:
        chat = SemanticBrainChat()
        chat.interactive_loop()


if __name__ == "__main__":
    main()
