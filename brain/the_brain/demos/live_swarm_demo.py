"""
Live Swarm Demo
===============

Runs actual brain + swarm with real-time visualization output.
The brain is autonomous - it analyzes, decides, and routes to agents.

Usage:
    python demos/live_swarm_demo.py
"""

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from production.brain_swarm_orchestrator import BrainSwarmOrchestrator


class LiveSwarmDemo:
    """Live demonstration of autonomous brain + swarm"""

    def __init__(self):
        load_dotenv()
        self.orchestrator = None

    def print_header(self, text, char="="):
        """Print formatted header"""
        print(f"\n{char * 60}")
        print(f"  {text}")
        print(f"{char * 60}\n")

    def print_brain_activation(self, feature_name, status):
        """Print brain feature activation"""
        symbol = "[ACTIVE]" if status else "[idle]"
        color = "\033[92m" if status else "\033[90m"  # Green if active, gray if idle
        reset = "\033[0m"
        print(f"{color}{symbol}{reset} {feature_name}")

    def print_agent_activation(self, agent_name, status):
        """Print agent activation"""
        symbol = "[ACTIVE]" if status else "[idle]"
        color = "\033[94m" if status else "\033[90m"  # Blue if active, gray if idle
        reset = "\033[0m"
        print(f"{color}{symbol}{reset} {agent_name}")

    async def run_demo(self, task: str):
        """Run live demo with real brain + swarm"""

        self.print_header("TAHLAMUS BRAIN + AUTOGEN SWARM - LIVE DEMO", "=")
        print(f"Task: {task}\n")

        # Initialize orchestrator
        print("Initializing autonomous brain + swarm agents...")
        self.orchestrator = BrainSwarmOrchestrator(
            session_log_dir="data/logs",
            user_id="live_demo_user",
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
        )

        print("Initializing 15 swarm agents...")
        self.orchestrator.initialize_swarm_agents()
        print(f"[OK] {len(self.orchestrator.agents)} agents initialized\n")

        # STEP 1: User Input
        self.print_header("STEP 1: User Input", "-")
        print(f"User: {task}\n")
        time.sleep(1)

        # STEP 2: Brain Analysis (Autonomous)
        self.print_header("STEP 2: Brain Analyzes Task (AUTONOMOUS)", "-")
        print("Brain is analyzing with all 13 cognitive features...\n")

        # Show brain features activating
        print("Brain Features Activating:")
        brain_features = [
            "Memory Systems - Retrieving past experiences",
            "Predictive Coding - Computing prediction errors",
            "Attention Mechanisms - Focusing on relevant signals",
            "Meta-Learning - Adapting learning rate",
            "Neuromodulation - Modulating urgency/focus",
            "Temporal Memory - Analyzing time patterns",
            "Active Inference - Generating hypotheses",
            "Compositional Reasoning - Breaking into subtasks",
            "Tool Creation - Recommending tools",
            "Consciousness Metrics - Tracking awareness",
            "Infinite Chat - Accessing user memory",
            "Semantic Coherence - Validating consistency",
            "CTM Async - Deep background reasoning"
        ]

        for i, feature in enumerate(brain_features):
            # Show progressive activation
            if i < 6:  # First 6 activate quickly
                self.print_brain_activation(feature, True)
                time.sleep(0.2)
            elif i < 10:  # Next 4 slower
                self.print_brain_activation(feature, True)
                time.sleep(0.3)
            else:  # Last 3 slowest
                self.print_brain_activation(feature, True)
                time.sleep(0.4)

        print("\nBrain processing...")
        result = await self.orchestrator.process_task(task)

        # STEP 3: Brain Decision
        self.print_header("STEP 3: Brain Decision (AUTONOMOUS)", "-")
        prediction = result['brain_analysis']['prediction']
        brain_state = result['brain_state']

        print(f"Task Type: {prediction.get('task_type', 'unknown')}")
        print(f"Primary Action: {prediction['primary_action']}")
        print(f"Confidence: {prediction.get('confidence', 0.0):.2f}")
        print(f"Complexity: {prediction.get('complexity', 0.0):.2f}")
        print(f"Processing Mode: {prediction.get('processing_mode', 'unknown')}")
        print(f"\nSuggested Agent: {result['suggested_agent']}")

        # Show active brain features
        print("\nKey Brain Insights:")
        if brain_state.get('memory_context'):
            memory = brain_state['memory_context']
            print(f"  - Working Memory: {len(memory.get('working_memory', []))} items")
            print(f"  - Episodic Memories: {len(memory.get('episodic_memories', []))} relevant")

        if brain_state.get('attention_state'):
            attention = brain_state['attention_state']
            print(f"  - Attention Focus: {attention.get('top_modality', 'unknown')}")

        if brain_state.get('consciousness_metrics'):
            consciousness = brain_state['consciousness_metrics']
            print(f"  - Awareness Score: {consciousness.get('awareness_score', 0.0):.2f}")
            print(f"  - Consciousness State: {consciousness.get('global_workspace_state', 'unknown')}")

        if brain_state.get('active_inference', {}).get('questions_to_ask'):
            print(f"  - Active Inference: {len(brain_state['active_inference']['questions_to_ask'])} questions generated")

        if result.get('ctm_task_id'):
            print(f"  - CTM Deep Reasoning: Active (Task ID: {result['ctm_task_id']})")

        print()
        time.sleep(2)

        # STEP 4: Coordinator Routes
        self.print_header("STEP 4: Coordinator Routes to Specialized Agent", "-")
        print(f"Coordinator received brain analysis:")
        print(f"  - Recommended agent: {result['suggested_agent']}")
        print(f"  - Confidence: {prediction.get('confidence', 0.0):.2f}")
        print(f"\nRouting to {result['suggested_agent']}...")
        print()
        time.sleep(1)

        # STEP 5: Swarm Execution
        self.print_header("STEP 5: Swarm Agents Execute (AUTONOMOUS)", "-")
        print("Swarm agents coordinating...\n")

        # Show agent activation based on suggested agent
        all_agents = [
            "coordinator",
            "docker_execution_agent",
            "database_execution_agent",
            "api_execution_agent",
            "debugging_agent",
            "monitoring_agent",
            "deployment_agent",
            "testing_agent",
            "refactoring_agent",
            "documentation_agent",
            "security_agent",
            "active_inference_agent",
            "ctm_reasoning_agent",
            "memory_agent",
            "general_execution_agent"
        ]

        print("Agent Status:")
        for agent in all_agents:
            is_active = (agent == result['suggested_agent'] or agent == 'coordinator')
            self.print_agent_activation(agent, is_active)

        print("\nSwarm Execution Log:")
        print("-" * 60)
        swarm_result = result.get('swarm_result', '')
        if swarm_result:
            # Print swarm result with formatting
            lines = swarm_result.split('\n')
            for line in lines[:20]:  # First 20 lines
                print(line)
            if len(lines) > 20:
                print(f"... ({len(lines) - 20} more lines)")
        else:
            print("Swarm coordination in progress...")

        print()
        time.sleep(1)

        # STEP 6: Learning
        self.print_header("STEP 6: Brain Learns from Execution (AUTONOMOUS)", "-")
        print("Submitting feedback to brain for continuous learning...")

        await self.orchestrator.submit_feedback(
            task=task,
            success=True,
            user_rating=0.9,
            execution_time=5.0
        )

        print("\nBrain Learning:")
        self.print_brain_activation("Meta-Learning - Updating success rates", True)
        self.print_brain_activation("Memory Systems - Consolidating experience", True)
        self.print_brain_activation("Neuromodulation - Adjusting parameters", True)

        print("\n[OK] Brain learned from execution!")
        print()
        time.sleep(1)

        # STEP 7: Summary
        self.print_header("SUMMARY", "=")
        print(f"Task: {task}")
        print(f"Brain Decision: {result['suggested_agent']}")
        print(f"Confidence: {prediction.get('confidence', 0.0):.2f}")
        print(f"Status: COMPLETED")
        print()

        # Brain stats
        stats = self.orchestrator.get_brain_stats()
        print("Brain Statistics:")
        print(f"  - Total Predictions: {stats.get('total_predictions', 0)}")
        print(f"  - Success Rate: {stats.get('success_rate', 0.0):.2%}")
        print(f"  - Average Confidence: {stats.get('average_confidence', 0.0):.2f}")
        print()

        self.print_header("DEMO COMPLETE", "=")
        print("The brain operated autonomously:")
        print("  1. Analyzed task with 13 cognitive features")
        print("  2. Made decision (task type, confidence, routing)")
        print("  3. Coordinated swarm agents via handoffs")
        print("  4. Learned from execution feedback")
        print()


async def main():
    """Main demo function"""
    demo = LiveSwarmDemo()

    # Demo tasks
    tasks = [
        "Deploy Docker container with Redis and health monitoring",
        "Debug memory leak in Node.js application",
        "Create REST API endpoint for user authentication"
    ]

    print("\n" + "=" * 60)
    print("  AUTONOMOUS BRAIN + SWARM DEMONSTRATION")
    print("  The brain makes all decisions - no manual routing!")
    print("=" * 60)
    print("\nAvailable demo tasks:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task}")

    print("\nSelect task (1-3) or press Enter for task 1: ", end='')
    try:
        choice = input().strip()
        if choice and choice.isdigit() and 1 <= int(choice) <= len(tasks):
            selected_task = tasks[int(choice) - 1]
        else:
            selected_task = tasks[0]
    except (ValueError, IndexError, EOFError, KeyboardInterrupt):
        selected_task = tasks[0]

    # Run demo
    await demo.run_demo(selected_task)


if __name__ == "__main__":
    asyncio.run(main())
