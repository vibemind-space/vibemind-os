"""
Test Script for Claude Desktop Workflow

Tests the Progress Agent and Claude Desktop workflow integration.

Usage:
    python test_claude_workflow.py [--task "your task here"]
    python test_claude_workflow.py --docker-debug
    python test_claude_workflow.py --dry-run
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflows.claude_desktop import ClaudeDesktopWorkflow, send_to_claude
from agents.progress_agent import ProgressAgent, get_progress_agent

# Optional imports
try:
    from bridge.websocket_client import MoireWebSocketClient
    HAS_MOIRE = True
except ImportError:
    HAS_MOIRE = False
    MoireWebSocketClient = None

try:
    from agents.steering_agent import SteeringAgent
    HAS_STEERING = True
except ImportError:
    HAS_STEERING = False
    SteeringAgent = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_workflow_dry_run():
    """Test workflow definition without execution."""
    print("\n" + "="*60)
    print("DRY RUN: Testing workflow step definitions")
    print("="*60 + "\n")

    workflow = ClaudeDesktopWorkflow()

    # Test with Docker debug template
    task = workflow.TASK_TEMPLATES["docker_debug"]
    steps = workflow.define_steps(task=task, wait_for_response=True)

    print(f"Task: {task[:80]}...\n")
    print(f"Total steps: {len(steps)}\n")

    for i, step in enumerate(steps, 1):
        print(f"Step {i}: [{step.action_type}] {step.description}")
        print(f"         Params: {step.params}")
        print(f"         Timeout: {step.timeout}s")
        print()

    print("="*60)
    print("DRY RUN COMPLETE - No actions were executed")
    print("="*60)


async def test_progress_agent_basic():
    """Test Progress Agent basic functionality."""
    print("\n" + "="*60)
    print("Testing Progress Agent (basic)")
    print("="*60 + "\n")

    from core.event_queue import ActionEvent, ActionStatus

    # Create a simple progress agent without MoireServer
    progress_agent = ProgressAgent(moire_client=None)

    # Create test actions
    actions = [
        ActionEvent(
            id="test_1",
            task_id="test_task",
            action_type="wait",
            params={"duration": 0.5},
            description="Test wait 1"
        ),
        ActionEvent(
            id="test_2",
            task_id="test_task",
            action_type="press_key",
            params={"key": "win"},
            description="Test key press"
        ),
        ActionEvent(
            id="test_3",
            task_id="test_task",
            action_type="type",
            params={"text": "hello"},
            description="Test typing"
        ),
    ]

    # Start monitoring
    await progress_agent.start_monitoring(
        task_id="test_task",
        goal="Test the progress agent",
        actions=actions
    )

    print(f"Started monitoring with {len(actions)} actions")
    print(f"Progress: {progress_agent.get_progress_summary()}")

    # Simulate action completions
    for i in range(len(actions)):
        await asyncio.sleep(0.2)
        result = await progress_agent.action_completed(i, {"success": True})
        summary = progress_agent.get_progress_summary()
        print(f"Action {i+1} completed: {summary['progress_percentage']:.0f}%")

    # Stop monitoring
    final_progress = await progress_agent.stop_monitoring()

    print(f"\nFinal Progress:")
    print(f"  Completed: {final_progress.completed_actions}/{final_progress.total_actions}")
    print(f"  Percentage: {final_progress.progress_percentage:.0f}%")
    print(f"  Goal achieved: {final_progress.goal_achieved}")
    print(f"  Blockers: {final_progress.blockers}")

    print("\n" + "="*60)
    print("PROGRESS AGENT TEST COMPLETE")
    print("="*60)


async def test_claude_workflow_execute(task: str, wait_for_response: bool = False):
    """Execute the Claude Desktop workflow."""
    print("\n" + "="*60)
    print("EXECUTING Claude Desktop Workflow")
    print("="*60 + "\n")

    print(f"Task: {task}\n")
    print("Starting in 3 seconds... (switch to desktop if needed)\n")

    await asyncio.sleep(3)

    # Create workflow with optional progress agent
    moire_client = None
    progress_agent = None

    if HAS_MOIRE:
        try:
            # MoireWebSocketClient expects host and port separately, not a URL
            moire_client = MoireWebSocketClient(host="localhost", port=8765)
            await moire_client.connect()
            progress_agent = ProgressAgent(moire_client=moire_client)
            logger.info("Connected to MoireServer for progress tracking")
        except Exception as e:
            logger.warning(f"Could not connect to MoireServer: {e}")

    # Skip SteeringAgent to avoid detection timeouts - use direct execution
    steering_agent = None
    logger.info("Using direct execution (no SteeringAgent visual detection)")

    workflow = ClaudeDesktopWorkflow(
        steering_agent=steering_agent,  # None = direct pyautogui execution
        progress_agent=progress_agent
    )

    # Set up callbacks
    def on_step_start(step):
        print(f"  -> Starting: {step.description}")

    def on_step_complete(step):
        print(f"  [OK] Completed: {step.description}")

    def on_step_failed(step, error):
        print(f"  [FAIL] Failed: {step.description} - {error}")

    def on_progress(pct):
        print(f"  Progress: {pct:.0f}%")

    workflow.on_step_start = on_step_start
    workflow.on_step_complete = on_step_complete
    workflow.on_step_failed = on_step_failed
    workflow.on_progress = on_progress

    # Execute
    try:
        result = await workflow.send_task(task, wait_for_response=wait_for_response)

        print(f"\n" + "-"*40)
        print(f"Result: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"Steps: {result.steps_completed}/{result.steps_total}")
        print(f"Duration: {result.duration:.1f}s")

        if result.error:
            print(f"Error: {result.error}")

        if result.progress:
            print(f"\nProgress Details:")
            print(f"  Blockers: {result.progress.blockers}")
            print(f"  Goal achieved: {result.progress.goal_achieved}")

    except Exception as e:
        print(f"\nWorkflow error: {e}")
        logger.exception("Workflow execution failed")

    finally:
        # Cleanup
        if moire_client:
            try:
                await moire_client.disconnect()
            except:
                pass

    print("\n" + "="*60)
    print("WORKFLOW EXECUTION COMPLETE")
    print("="*60)


async def test_docker_debug():
    """Run the Docker debug workflow."""
    print("\n" + "="*60)
    print("Docker Debug Report Workflow")
    print("="*60 + "\n")

    task = ClaudeDesktopWorkflow.TASK_TEMPLATES["docker_debug"]
    await test_claude_workflow_execute(task, wait_for_response=True)


async def main():
    parser = argparse.ArgumentParser(description="Test Claude Desktop Workflow")
    parser.add_argument("--task", type=str, help="Custom task to send to Claude")
    parser.add_argument("--docker-debug", action="store_true", help="Run Docker debug report")
    parser.add_argument("--dry-run", action="store_true", help="Show steps without execution")
    parser.add_argument("--test-progress", action="store_true", help="Test progress agent only")
    parser.add_argument("--wait", action="store_true", help="Wait for Claude response")

    args = parser.parse_args()

    if args.dry_run:
        await test_workflow_dry_run()
    elif args.test_progress:
        await test_progress_agent_basic()
    elif args.docker_debug:
        await test_docker_debug()
    elif args.task:
        await test_claude_workflow_execute(args.task, wait_for_response=args.wait)
    else:
        # Default: dry run + progress test
        await test_workflow_dry_run()
        await test_progress_agent_basic()

        print("\n" + "="*60)
        print("To execute the workflow, run:")
        print("  python test_claude_workflow.py --task 'Your task here'")
        print("  python test_claude_workflow.py --docker-debug")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
