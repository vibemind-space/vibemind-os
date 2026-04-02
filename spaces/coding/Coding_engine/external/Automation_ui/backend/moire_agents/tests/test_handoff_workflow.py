"""
Test Handoff Workflow - Claude Desktop Automation

Tests the AutoGen handoff pattern with a real workflow:
1. Orchestrator receives task
2. Delegates to Execution for hotkey
3. Delegates to Vision for finding input
4. Delegates to Execution for typing
5. Returns final result

Usage:
    python test_handoff_workflow.py
    python test_handoff_workflow.py --docker-debug
    python test_handoff_workflow.py --dry-run
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.handoff import (
    AgentRuntime,
    UserTask,
    OrchestratorAgent,
    ExecutionAgent,
    VisionHandoffAgent,
    RecoveryAgent,
    ProgressUpdate
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def on_progress(update: ProgressUpdate):
    """Progress callback."""
    print(f"  [{update.agent_name}] {update.progress_percentage:.0f}% - {update.current_action}")
    if update.blockers:
        print(f"    Blockers: {update.blockers}")


async def test_handoff_workflow(task_message: str, dry_run: bool = False):
    """
    Test the handoff workflow with Claude Desktop.

    Args:
        task_message: Message to send to Claude Desktop
        dry_run: If True, just print what would happen
    """
    print("\n" + "=" * 60)
    print("HANDOFF WORKFLOW TEST")
    print("=" * 60)
    print(f"\nTask: {task_message[:80]}...")
    print(f"Dry run: {dry_run}")

    # Create runtime with progress callback
    # Each action needs ~2 handoffs (orchestrator → agent → orchestrator)
    # So 6 actions need ~15-20 handoffs
    runtime = AgentRuntime(
        max_handoffs=25,
        task_timeout=120.0,
        on_progress=on_progress
    )

    # Create agents
    orchestrator = OrchestratorAgent()
    execution = ExecutionAgent(use_clipboard_for_text=True)
    vision = VisionHandoffAgent()
    recovery = RecoveryAgent(max_retries=2)

    # Register agents
    await runtime.register_agent("orchestrator", orchestrator)
    await runtime.register_agent("execution", execution)
    await runtime.register_agent("vision", vision)
    await runtime.register_agent("recovery", recovery)

    print(f"\nRegistered agents: {runtime.list_agents()}")

    # Create the task
    task = UserTask(
        goal=f"Send message to Claude Desktop: {task_message}",
        context={
            "workflow": "claude_desktop",
            "message": task_message,
            "vision_fallback": True  # Use fallback if vision fails
        }
    )

    print("\nStarting in 3 seconds... (switch to desktop if needed)")
    await asyncio.sleep(3)

    if dry_run:
        print("\n[DRY RUN] Would execute:")
        actions = orchestrator._plan_claude_desktop_workflow(task)
        for i, action in enumerate(actions):
            print(f"  {i+1}. {action.get('type')}: {action.get('description', '')}")
        return

    # Run the workflow
    print("\n" + "-" * 40)
    print("EXECUTING WORKFLOW")
    print("-" * 40)

    try:
        response = await runtime.run_task(task, entry_agent="orchestrator")

        print("\n" + "-" * 40)
        print("RESULT")
        print("-" * 40)
        print(f"Success: {response.success}")
        print(f"Error: {response.error}" if response.error else "No errors")

        if response.result:
            if isinstance(response.result, dict):
                print(f"Completed actions: {response.result.get('total_steps', 0)}")
            else:
                print(f"Result: {response.result}")

        # Show stats
        stats = runtime.get_stats()
        print(f"\nRuntime stats:")
        print(f"  Tasks processed: {stats['tasks_processed']}")
        print(f"  Handoffs routed: {stats['handoffs_routed']}")
        print(f"  Sessions completed: {stats['sessions_completed']}")
        print(f"  Errors: {stats['errors']}")

        # Show agent stats
        print(f"\nAgent stats:")
        for agent_name in runtime.list_agents():
            agent = runtime.get_agent(agent_name)
            agent_stats = agent.get_stats()
            print(f"  {agent_name}: {agent_stats['tasks_processed']} tasks, "
                  f"{agent_stats['handoffs_made']} handoffs")

    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Test handoff workflow")
    parser.add_argument("--docker-debug", action="store_true",
                       help="Send Docker debug task")
    parser.add_argument("--dry-run", action="store_true",
                       help="Just print what would happen")
    parser.add_argument("--message", type=str, default=None,
                       help="Custom message to send")

    args = parser.parse_args()

    if args.message:
        task_message = args.message
    elif args.docker_debug:
        task_message = (
            "Generate a comprehensive debug report about Docker containers. "
            "Include: container status, running containers, recent logs, "
            "resource usage (CPU/memory), and any errors or warnings. "
            "Format the report as a Word document (.docx)."
        )
    else:
        task_message = "Hello from the handoff workflow test! This is a test message."

    await test_handoff_workflow(task_message, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
