"""
Orchestrator Script - Claude Code sends tasks here

Usage:
    python orchestrate.py "open notepad and type hello"
    python orchestrate.py "send message to Claude Desktop"
"""
import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_server_handoff import handle_plan, handle_execute, cleanup


async def orchestrate(goal: str, auto_execute: bool = False):
    """
    Orchestrate a task using the handoff system.

    Args:
        goal: What to accomplish
        auto_execute: If True, execute even if not approved
    """
    print("=" * 60)
    print(f"  ORCHESTRATING: {goal}")
    print("=" * 60)

    # Step 1: Create plan
    print("\n[Step 1] Creating plan with LLM Planner + Critic...")
    result = await handle_plan(goal)

    plan = result.get('plan', [])
    approved = result.get('approved', False)
    issues = result.get('issues', [])
    confidence = result.get('planner_confidence', 0)

    print(f"  Approved: {approved}")
    print(f"  Confidence: {confidence:.0%}")
    print(f"  Steps: {len(plan)}")

    if plan:
        print("\n  Plan:")
        for i, step in enumerate(plan, 1):
            print(f"    {i}. [{step.get('type')}] {step.get('description')}")

    if issues:
        print(f"\n  Issues found:")
        for issue in issues:
            print(f"    - {issue}")

    # Step 2: Decide and execute
    print("\n[Step 2] Decision...")

    if approved:
        print("  Plan APPROVED - executing automatically")
        exec_result = await handle_execute(plan)
        print(f"\n  Execution: {'SUCCESS' if exec_result.get('success') else 'FAILED'}")
    elif auto_execute and plan:
        print("  Plan NOT approved, but auto_execute=True - proceeding anyway")
        exec_result = await handle_execute(plan)
        print(f"\n  Execution: {'SUCCESS' if exec_result.get('success') else 'FAILED'}")
    else:
        print("  Plan NOT approved - stopping")
        print("  (In Claude Code, I would decide: retry with modifications or ask user)")

    # Cleanup
    await cleanup()

    print("\n" + "=" * 60)
    print("  ORCHESTRATION COMPLETE")
    print("=" * 60)

    return result


async def main():
    if len(sys.argv) < 2:
        print("Usage: python orchestrate.py <goal>")
        print("Example: python orchestrate.py \"open notepad and type hello\"")
        return

    goal = " ".join(sys.argv[1:])
    auto = "--auto" in sys.argv

    await orchestrate(goal, auto_execute=auto)


if __name__ == "__main__":
    asyncio.run(main())
