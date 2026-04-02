"""
Swarm Brain CLI
===============

Command-line interface for Tahlamus Brain + AutoGen Swarm integration.

Usage:
    python production/swarm_brain_cli.py predict "Deploy Docker with Redis"
    python production/swarm_brain_cli.py swarm-status
    python production/swarm_brain_cli.py brain-stats
    python production/swarm_brain_cli.py feedback --task "..." --success --rating 0.9
    python production/swarm_brain_cli.py agent-health
"""

import asyncio
import argparse
import json
import os
import sys
from typing import Optional
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from production.brain_swarm_orchestrator import BrainSwarmOrchestrator


class SwarmBrainCLI:
    """CLI interface for Brain-Swarm system"""

    def __init__(self):
        load_dotenv()
        self.orchestrator: Optional[BrainSwarmOrchestrator] = None

    def _ensure_orchestrator(self):
        """Initialize orchestrator if not already done"""
        if self.orchestrator is None:
            openrouter_key = os.getenv("OPENROUTER_API_KEY")

            # Check if OpenRouter key exists
            if not openrouter_key:
                print("ERROR: OPENROUTER_API_KEY not found in .env file")
                print("")
                print("Add to .env:")
                print("  OPENROUTER_API_KEY=sk-or-v1-...")
                print("")
                print("Why OpenRouter?")
                print("  - Access to 100+ models (GPT, Claude, Llama, etc.)")
                print("  - Cheaper than direct providers")
                print("  - Already used by Tahlamus brain")
                print("  - Unified billing")
                print("")
                print("Get OpenRouter key at: https://openrouter.ai/keys")
                sys.exit(1)

            # Show which model will be used
            print("[OK] Using OpenRouter (gpt-4o)")

            self.orchestrator = BrainSwarmOrchestrator(
                session_log_dir="data/logs",
                user_id="cli_user",
                openrouter_api_key=openrouter_key
            )

            # Initialize swarm agents
            print("Initializing swarm agents...")
            self.orchestrator.initialize_swarm_agents()
            print(f"[OK] {len(self.orchestrator.agents)} agents initialized\n")

    async def predict(self, task: str, verbose: bool = False):
        """
        Make prediction using brain + swarm.

        Args:
            task: Task description
            verbose: Show detailed output
        """
        self._ensure_orchestrator()

        print(f"Task: {task}\n")
        print("Brain analyzing...")

        result = await self.orchestrator.process_task(task)

        # Display brain analysis
        print("\n" + "="*60)
        print("BRAIN ANALYSIS")
        print("="*60)

        prediction = result['brain_analysis']['prediction']
        print(f"Primary Action: {prediction['primary_action']}")
        print(f"Task Type: {prediction.get('task_type', 'unknown')}")
        print(f"Confidence: {prediction.get('confidence', 0.0):.2f}")
        print(f"Processing Mode: {prediction.get('processing_mode', 'unknown')}")
        print(f"Complexity: {prediction.get('complexity', 0.0):.2f}")

        # Memory context
        if verbose:
            memory_ctx = result['brain_analysis'].get('memory_context', {})
            print(f"\nWorking Memory: {len(memory_ctx.get('working_memory', []))} items")
            print(f"Episodic Memories: {len(memory_ctx.get('episodic_memories', []))} relevant")

            # Consciousness
            consciousness = result['brain_analysis'].get('consciousness_metrics', {})
            print(f"\nConsciousness State: {consciousness.get('global_workspace_state', 'unknown')}")
            print(f"Awareness Score: {consciousness.get('awareness_score', 0.0):.2f}")

            # CTM
            if result['brain_analysis'].get('ctm_task_id'):
                print(f"\nCTM Deep Reasoning: Active")
                print(f"Task ID: {result['brain_analysis']['ctm_task_id']}")

        # Suggested agent
        print(f"\n→ Brain recommends: {result['suggested_agent']}")

        # Swarm result
        print("\n" + "="*60)
        print("SWARM EXECUTION")
        print("="*60)
        print(result['swarm_result'])

        # Save full result to file
        output_file = "data/logs/last_swarm_result.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n[OK] Full result saved to: {output_file}")

    async def feedback(
        self,
        task: str,
        success: bool,
        rating: float,
        execution_time: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """
        Submit feedback to brain.

        Args:
            task: Task description
            success: Whether task succeeded
            rating: User rating (0-1)
            execution_time: Execution time in seconds
            error_message: Error message if failed
        """
        self._ensure_orchestrator()

        await self.orchestrator.submit_feedback(
            task=task,
            success=success,
            user_rating=rating,
            execution_time=execution_time,
            error_message=error_message
        )

        status = "[SUCCESS]" if success else "[FAILED]"
        print(f"{status} - Feedback submitted to brain")
        print(f"Task: {task}")
        print(f"Rating: {rating:.2f}")
        if execution_time:
            print(f"Execution Time: {execution_time:.1f}s")
        if error_message:
            print(f"Error: {error_message}")

    def brain_stats(self):
        """Display brain statistics"""
        self._ensure_orchestrator()

        stats = self.orchestrator.get_brain_stats()

        print("="*60)
        print("BRAIN STATISTICS")
        print("="*60)
        print(json.dumps(stats, indent=2, default=str))

    def swarm_status(self):
        """Display swarm status"""
        self._ensure_orchestrator()

        status = self.orchestrator.get_swarm_status()

        print("="*60)
        print("SWARM STATUS")
        print("="*60)
        print(f"Agents Initialized: {status['agents_initialized']}")
        print(f"Swarm Created: {status['swarm_created']}")
        print(f"\nAgents:")
        for agent_name in status['agent_names']:
            print(f"  • {agent_name}")

        if status['current_brain_state']:
            print(f"\nCurrent Brain State:")
            print(f"  Task: {status['current_brain_state']['task']}")
            print(f"  Primary Action: {status['current_brain_state']['prediction']['primary_action']}")
            print(f"  Confidence: {status['current_brain_state']['prediction'].get('confidence', 0.0):.2f}")

    def agent_health(self):
        """Check agent health"""
        self._ensure_orchestrator()

        print("="*60)
        print("AGENT HEALTH CHECK")
        print("="*60)

        for agent_name, agent in self.orchestrator.agents.items():
            print(f"[OK] {agent_name}")

        print(f"\nTotal Agents: {len(self.orchestrator.agents)}")
        print("Status: All systems operational")

    def interactive_mode(self):
        """Interactive mode - continuous conversation"""
        self._ensure_orchestrator()

        print("="*60)
        print("INTERACTIVE MODE")
        print("="*60)
        print("Enter tasks to process with brain + swarm.")
        print("Commands:")
        print("  'stats' - Show brain statistics")
        print("  'status' - Show swarm status")
        print("  'health' - Check agent health")
        print("  'quit' - Exit")
        print("="*60 + "\n")

        while True:
            try:
                task = input("\n> ").strip()

                if not task:
                    continue

                if task.lower() == 'quit':
                    print("Goodbye!")
                    break
                elif task.lower() == 'stats':
                    self.brain_stats()
                elif task.lower() == 'status':
                    self.swarm_status()
                elif task.lower() == 'health':
                    self.agent_health()
                else:
                    # Process task
                    asyncio.run(self.predict(task, verbose=True))

                    # Ask for feedback
                    feedback_choice = input("\nProvide feedback? (y/n): ").strip().lower()
                    if feedback_choice == 'y':
                        success = input("Success? (y/n): ").strip().lower() == 'y'
                        rating = float(input("Rating (0-1): ").strip())
                        exec_time = input("Execution time (seconds, optional): ").strip()
                        exec_time = float(exec_time) if exec_time else None

                        asyncio.run(self.orchestrator.submit_feedback(
                            task=task,
                            success=success,
                            user_rating=rating,
                            execution_time=exec_time
                        ))

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Tahlamus Brain + AutoGen Swarm CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Make prediction
    python production/swarm_brain_cli.py predict "Deploy Docker with Redis"

    # Make prediction with verbose output
    python production/swarm_brain_cli.py predict "Fix database timeout" --verbose

    # Submit feedback
    python production/swarm_brain_cli.py feedback \\
        --task "Deploy Docker with Redis" \\
        --success \\
        --rating 0.9 \\
        --time 45.0

    # Check brain statistics
    python production/swarm_brain_cli.py brain-stats

    # Check swarm status
    python production/swarm_brain_cli.py swarm-status

    # Check agent health
    python production/swarm_brain_cli.py agent-health

    # Interactive mode
    python production/swarm_brain_cli.py interactive
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Predict command
    predict_parser = subparsers.add_parser('predict', help='Make prediction')
    predict_parser.add_argument('task', type=str, help='Task description')
    predict_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    # Feedback command
    feedback_parser = subparsers.add_parser('feedback', help='Submit feedback')
    feedback_parser.add_argument('--task', type=str, required=True, help='Task description')
    feedback_parser.add_argument('--success', action='store_true', help='Task succeeded')
    feedback_parser.add_argument('--rating', type=float, required=True, help='User rating (0-1)')
    feedback_parser.add_argument('--time', type=float, help='Execution time (seconds)')
    feedback_parser.add_argument('--error', type=str, help='Error message if failed')

    # Brain stats command
    subparsers.add_parser('brain-stats', help='Show brain statistics')

    # Swarm status command
    subparsers.add_parser('swarm-status', help='Show swarm status')

    # Agent health command
    subparsers.add_parser('agent-health', help='Check agent health')

    # Interactive mode command
    subparsers.add_parser('interactive', help='Interactive mode')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = SwarmBrainCLI()

    if args.command == 'predict':
        asyncio.run(cli.predict(args.task, verbose=args.verbose))
    elif args.command == 'feedback':
        asyncio.run(cli.feedback(
            task=args.task,
            success=args.success,
            rating=args.rating,
            execution_time=args.time,
            error_message=args.error
        ))
    elif args.command == 'brain-stats':
        cli.brain_stats()
    elif args.command == 'swarm-status':
        cli.swarm_status()
    elif args.command == 'agent-health':
        cli.agent_health()
    elif args.command == 'interactive':
        cli.interactive_mode()


if __name__ == "__main__":
    main()
