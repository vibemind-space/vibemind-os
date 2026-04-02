"""
Test script to simulate PlaywrightE2EAgent on output_memory_test_fixed.

This simulates the flow:
1. DEPLOY_SUCCEEDED event received
2. Capture screenshots via Claude CLI + Playwright MCP
3. Analyze with Claude Vision (if API key available)
4. Generate debugging plan
5. Execute tests
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState
from src.agents.playwright_e2e_agent import PlaywrightE2EAgent, PlaywrightE2EResult
from src.tools.vision_analysis_tool import VisionAnalysisTool


async def simulate_playwright_e2e():
    """Simulate the PlaywrightE2EAgent workflow."""
    print("=" * 60)
    print("PlaywrightE2EAgent Simulation")
    print("=" * 60)

    working_dir = Path("output_memory_test_fixed")
    preview_url = "http://localhost:5173"

    # Initialize components
    event_bus = EventBus()
    shared_state = SharedState()

    # Create the agent
    agent = PlaywrightE2EAgent(
        name="PlaywrightE2E",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(working_dir),
        memory_tool=None,  # No memory for this test
    )

    print(f"\n[1] Agent initialized")
    print(f"    - Vision enabled: {agent.vision_tool.enabled}")
    print(f"    - Working dir: {working_dir}")
    print(f"    - Screenshots dir: {agent._screenshots_dir}")

    # Simulate DEPLOY_SUCCEEDED event
    deploy_event = Event(
        type=EventType.DEPLOY_SUCCEEDED,
        source="DeployAgent",
        data={
            "url": preview_url,
            "preview_url": preview_url,
            "success": True,
        }
    )

    print(f"\n[2] Simulating DEPLOY_SUCCEEDED event")
    print(f"    - URL: {preview_url}")

    # Check if agent should act
    agent._handle_event(deploy_event)
    should_act = await agent.should_act([deploy_event])

    print(f"\n[3] Agent decision: should_act = {should_act}")

    if not should_act:
        print("    - Agent decided not to act (URL might not be accessible)")
        return

    print(f"\n[4] Running E2E tests...")
    print("    - Capturing screenshots via Playwright MCP")
    print("    - This uses Claude CLI with --mcp-config")

    # Run the agent's act method
    try:
        result_event = await agent.act([deploy_event])

        if result_event:
            print(f"\n[5] Test Results:")
            print(f"    - Event type: {result_event.type}")
            print(f"    - Success: {result_event.success}")

            data = result_event.data or {}
            print(f"    - Tests run: {data.get('tests_run', 0)}")
            print(f"    - Tests passed: {data.get('tests_passed', 0)}")
            print(f"    - Tests failed: {data.get('tests_failed', 0)}")
            print(f"    - Screenshots: {data.get('screenshots', [])}")
            print(f"    - Visual issues: {data.get('visual_issues_found', [])}")

            if data.get('error'):
                print(f"    - Error: {data.get('error')}")

            if data.get('debugging_plan'):
                print(f"\n[6] Debugging Plan:")
                plan = data.get('debugging_plan')
                print(f"    - Root cause: {plan.get('root_cause_hypothesis', 'N/A')}")
                print(f"    - Files to check: {plan.get('files_to_investigate', [])}")
        else:
            print("\n[5] No result event returned")

    except Exception as e:
        print(f"\n[5] Error during test execution: {e}")
        import traceback
        traceback.print_exc()


async def test_vision_tool_standalone():
    """Test the vision tool directly if we have screenshots."""
    print("\n" + "=" * 60)
    print("Vision Tool Standalone Test")
    print("=" * 60)

    vision_tool = VisionAnalysisTool()

    print(f"\n- Vision enabled: {vision_tool.enabled}")
    print(f"- Model: {vision_tool.model}")

    if not vision_tool.enabled:
        print("\n[!] Vision tool not available (no ANTHROPIC_API_KEY)")
        print("    Claude CLI uses OAuth, but direct API needs a key")
        print("    Set ANTHROPIC_API_KEY in .env to enable vision analysis")
        return

    # Look for existing screenshots
    screenshots_dir = Path("output_memory_test_fixed/screenshots")
    if screenshots_dir.exists():
        screenshots = list(screenshots_dir.glob("*.png"))
        if screenshots:
            print(f"\n- Found {len(screenshots)} existing screenshots")
            for ss in screenshots[:3]:
                print(f"    - {ss}")


async def test_screenshot_capture_only():
    """Test just the screenshot capture via Claude CLI + Playwright MCP."""
    print("\n" + "=" * 60)
    print("Screenshot Capture Test (Claude CLI + Playwright MCP)")
    print("=" * 60)

    import subprocess
    from pathlib import Path

    working_dir = Path("output_memory_test_fixed")
    screenshots_dir = working_dir / "screenshots" / "playwright_e2e"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = screenshots_dir / f"test_{timestamp}.png"

    # Build MCP config
    mcp_config = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-playwright"]
            }
        }
    }

    mcp_config_path = working_dir / ".mcp-test.json"
    with open(mcp_config_path, 'w') as f:
        json.dump(mcp_config, f)

    prompt = f"""Navigate to http://localhost:5173 and take a screenshot.

Steps:
1. Use browser_navigate to go to http://localhost:5173
2. Wait 3 seconds for the page to load
3. Take a screenshot using browser_take_screenshot
4. Save to: {screenshot_path}

If you cannot connect, report the error."""

    print(f"\n- MCP config: {mcp_config_path}")
    print(f"- Screenshot target: {screenshot_path}")
    print(f"\n- Running Claude CLI with Playwright MCP...")

    try:
        result = subprocess.run(
            ["claude", "--mcp-config", str(mcp_config_path), "-p", prompt],
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=120
        )

        print(f"\n- Exit code: {result.returncode}")
        print(f"- Output:\n{result.stdout[:1000]}")

        if result.stderr:
            print(f"- Stderr:\n{result.stderr[:500]}")

        if screenshot_path.exists():
            print(f"\n[SUCCESS] Screenshot captured: {screenshot_path}")
        else:
            print(f"\n[!] Screenshot not found at expected path")
            # Check if any screenshots were created
            for p in screenshots_dir.glob("*.png"):
                print(f"    Found: {p}")

    except subprocess.TimeoutExpired:
        print("\n[!] Claude CLI timed out after 120 seconds")
    except FileNotFoundError:
        print("\n[!] Claude CLI not found - make sure it's installed")
    finally:
        if mcp_config_path.exists():
            mcp_config_path.unlink()


if __name__ == "__main__":
    print("Starting PlaywrightE2EAgent simulation...\n")

    # Run tests
    asyncio.run(test_screenshot_capture_only())
    asyncio.run(test_vision_tool_standalone())
    # asyncio.run(simulate_playwright_e2e())  # Full simulation
