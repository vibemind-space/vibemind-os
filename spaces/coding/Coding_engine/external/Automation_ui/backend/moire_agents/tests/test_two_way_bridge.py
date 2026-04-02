"""
Test Two-Way Communication Bridge with Claude Desktop

This script demonstrates:
1. Sending a task to Claude Desktop via the handoff system
2. Monitoring for automation-report blocks in Claude's responses
3. Handling requests from Claude Desktop (save_file, run_command, etc.)

Usage:
    python test_two_way_bridge.py --print-instructions  # Print project instructions
    python test_two_way_bridge.py --test-parser         # Test report parsing
    python test_two_way_bridge.py --send "Your task"    # Send task and monitor
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.handoff import (
    ClaudeDesktopBridge,
    ClaudeDesktopReport,
    ReportType,
    ReportParser,
    EventStream,
    get_project_instructions,
    AgentRuntime,
    OrchestratorAgent,
    ExecutionAgent,
    VisionHandoffAgent,
    RecoveryAgent,
    UserTask
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_project_instructions():
    """Print the instructions to add to Claude Desktop project."""
    print("\n" + "=" * 70)
    print("CLAUDE DESKTOP PROJECT INSTRUCTIONS")
    print("=" * 70)
    print("\nCopy the following into your Claude Desktop project's 'Instructions' section:\n")
    print("-" * 70)
    print(get_project_instructions())
    print("-" * 70)
    print("\nAfter adding these instructions, Claude Desktop will output structured")
    print("automation-report blocks that this system can capture and act on.")
    print("=" * 70 + "\n")


def test_report_parser():
    """Test the report parser with sample text."""
    print("\n" + "=" * 60)
    print("TESTING REPORT PARSER")
    print("=" * 60)

    # Sample Claude Desktop response with automation-report blocks
    sample_response = '''
I'll help you analyze the Docker containers. Let me start by checking their status.

```automation-report
{"type": "status", "message": "Starting Docker analysis...", "data": {"progress": 10}}
```

I can see there are 5 containers running. Let me get more details.

```automation-report
{"type": "status", "message": "Analyzing container metrics", "data": {"progress": 50, "containers_found": 5}}
```

I've gathered all the information. Here's a summary:
- nginx: running, 45MB memory
- postgres: running, 256MB memory
- redis: running, 12MB memory

```automation-report
{"type": "request", "message": "Need to save the report", "request": {"action": "save_file", "params": {"path": "C:/reports/docker_report.txt", "content": "Docker Report\\n..."}}}
```

The analysis is complete!

```automation-report
{"type": "completion", "message": "Docker analysis complete", "data": {"total_containers": 5, "healthy": 5, "report_generated": true}}
```
'''

    print(f"\nSample text ({len(sample_response)} chars):\n")
    print(sample_response[:200] + "..." if len(sample_response) > 200 else sample_response)

    print("\n" + "-" * 40)
    print("PARSED REPORTS:")
    print("-" * 40)

    reports = ReportParser.parse_text(sample_response)

    for i, report in enumerate(reports, 1):
        print(f"\n{i}. [{report.report_type.value.upper()}]")
        print(f"   Message: {report.message}")
        print(f"   Data: {report.data}")
        if report.requested_action:
            print(f"   Action: {report.requested_action}")
            print(f"   Params: {report.action_params}")

    print(f"\n\nTotal reports found: {len(reports)}")
    print("=" * 60 + "\n")


async def test_event_stream():
    """Test the event stream with handlers."""
    print("\n" + "=" * 60)
    print("TESTING EVENT STREAM")
    print("=" * 60)

    stream = EventStream()

    # Register handlers
    def on_status(report: ClaudeDesktopReport):
        print(f"  [STATUS] {report.message} - {report.data}")

    def on_completion(report: ClaudeDesktopReport):
        print(f"  [COMPLETE] {report.message}")

    def on_request(report: ClaudeDesktopReport):
        print(f"  [REQUEST] {report.requested_action}: {report.action_params}")

    def on_any(report: ClaudeDesktopReport):
        print(f"  [ANY] Received {report.report_type.value} report")

    stream.on(ReportType.STATUS, on_status)
    stream.on(ReportType.COMPLETION, on_completion)
    stream.on(ReportType.REQUEST, on_request)
    stream.on_any(on_any)

    # Emit some test reports
    print("\nEmitting test reports:\n")

    await stream.emit(ClaudeDesktopReport(
        report_type=ReportType.STATUS,
        message="Processing task...",
        data={"progress": 25}
    ))

    await stream.emit(ClaudeDesktopReport(
        report_type=ReportType.REQUEST,
        message="Need to run command",
        requested_action="run_command",
        action_params={"cmd": "docker ps"}
    ))

    await stream.emit(ClaudeDesktopReport(
        report_type=ReportType.COMPLETION,
        message="Task finished!",
        data={"success": True}
    ))

    print(f"\nTotal reports in stream: {len(stream.get_reports())}")
    print("=" * 60 + "\n")


async def send_task_with_monitoring(task_message: str):
    """Send a task to Claude Desktop and monitor for reports."""
    print("\n" + "=" * 60)
    print("TWO-WAY COMMUNICATION TEST")
    print("=" * 60)
    print(f"\nTask: {task_message[:60]}...")

    # Create the bridge
    bridge = ClaudeDesktopBridge(poll_interval=2.0)

    # Register event handlers
    def on_status(report: ClaudeDesktopReport):
        print(f"  [Claude Status] {report.message}")

    def on_request(report: ClaudeDesktopReport):
        print(f"  [Claude Request] {report.requested_action}: {report.action_params}")

    def on_completion(report: ClaudeDesktopReport):
        print(f"  [Claude Complete] {report.message}")

    def on_error(report: ClaudeDesktopReport):
        print(f"  [Claude Error] {report.message}")

    bridge.event_stream.on(ReportType.STATUS, on_status)
    bridge.event_stream.on(ReportType.REQUEST, on_request)
    bridge.event_stream.on(ReportType.COMPLETION, on_completion)
    bridge.event_stream.on(ReportType.ERROR, on_error)

    # Create runtime and agents
    runtime = AgentRuntime(max_handoffs=15, task_timeout=120.0)

    orchestrator = OrchestratorAgent()
    execution = ExecutionAgent(use_clipboard_for_text=True)
    vision = VisionHandoffAgent()
    recovery = RecoveryAgent()

    await runtime.register_agent("orchestrator", orchestrator)
    await runtime.register_agent("execution", execution)
    await runtime.register_agent("vision", vision)
    await runtime.register_agent("recovery", recovery)

    print(f"\nRegistered agents: {runtime.list_agents()}")

    # Create task
    task = UserTask(
        goal=f"Send to Claude Desktop: {task_message}",
        context={
            "workflow": "claude_desktop",
            "message": task_message
        }
    )

    print("\nStarting in 3 seconds... (switch to desktop if needed)")
    await asyncio.sleep(3)

    # Start monitoring for reports
    await bridge.start_monitoring()

    print("\n" + "-" * 40)
    print("SENDING TASK")
    print("-" * 40)

    # Send the task
    response = await runtime.run_task(task, entry_agent="orchestrator")

    print(f"\nTask sent: {response.success}")

    # Monitor for a while
    print("\n" + "-" * 40)
    print("MONITORING FOR REPORTS (30 seconds)...")
    print("-" * 40)

    await asyncio.sleep(30)

    # Stop monitoring
    await bridge.stop_monitoring()

    # Show collected reports
    reports = bridge.event_stream.get_reports()
    print(f"\n\nCollected {len(reports)} reports from Claude Desktop")

    for report in reports:
        print(f"  - [{report.report_type.value}] {report.message}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Test Two-Way Claude Desktop Bridge")
    parser.add_argument("--print-instructions", action="store_true",
                       help="Print project instructions to add to Claude Desktop")
    parser.add_argument("--test-parser", action="store_true",
                       help="Test the report parser")
    parser.add_argument("--test-stream", action="store_true",
                       help="Test the event stream")
    parser.add_argument("--send", type=str, default=None,
                       help="Send a task and monitor for reports")

    args = parser.parse_args()

    if args.print_instructions:
        print_project_instructions()
    elif args.test_parser:
        test_report_parser()
    elif args.test_stream:
        await test_event_stream()
    elif args.send:
        await send_task_with_monitoring(args.send)
    else:
        # Default: print instructions and test parser
        print_project_instructions()
        test_report_parser()
        await test_event_stream()


if __name__ == "__main__":
    asyncio.run(main())
