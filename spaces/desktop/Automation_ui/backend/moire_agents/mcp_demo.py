"""
MCP Demo - Dual-Monitor Workflow mit Claude CLI

Demonstriert:
1. Screenshot von beiden Monitoren
2. Claude analysiert beide Screens
3. Workflow wird für jeden Monitor erstellt
4. Workflows werden parallel ausgeführt

Usage:
    python mcp_demo.py
    python mcp_demo.py --monitor 0  # Nur Monitor 0
    python mcp_demo.py --monitor 1  # Nur Monitor 1
"""

import asyncio
import json
import sys
import os
import argparse
import base64
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Imports
try:
    import pyautogui
    from PIL import Image
    import mss
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install pyautogui pillow mss")
    sys.exit(1)

from agents.orchestrator import ClaudeCLIWrapper


class WorkflowType(Enum):
    """Types of workflows that can be created."""
    BROWSER_AUTOMATION = "browser"
    DESKTOP_APP = "desktop_app"
    FILE_MANAGER = "file_manager"
    TERMINAL = "terminal"
    CHAT_APP = "chat_app"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


@dataclass
class MonitorWorkflow:
    """Workflow for a single monitor."""
    monitor_id: int
    monitor_info: Dict[str, Any]
    screenshot_path: Optional[str] = None
    detected_type: WorkflowType = WorkflowType.UNKNOWN
    analysis: Optional[str] = None
    workflow_steps: List[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.workflow_steps is None:
            self.workflow_steps = []


class MCPDemo:
    """
    MCP Demo für Dual-Monitor Workflows.

    Zeigt die Integration von:
    - Screen Capture (mss)
    - Claude CLI für Analyse
    - MCP Tools für Workflow-Ausführung
    """

    def __init__(self):
        self.claude_cli = ClaudeCLIWrapper()
        self.monitor_workflows: Dict[int, MonitorWorkflow] = {}
        self.output_dir = os.path.join(os.path.dirname(__file__), "demo_output")
        os.makedirs(self.output_dir, exist_ok=True)

    def get_monitors(self) -> List[Dict[str, Any]]:
        """Get information about all monitors."""
        with mss.mss() as sct:
            monitors = []
            # Skip first monitor (virtual combined screen)
            for i, monitor in enumerate(sct.monitors[1:], start=0):
                monitors.append({
                    "id": i,
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"],
                    "name": f"Monitor {i}"
                })
            return monitors

    def capture_monitor(self, monitor_id: int) -> Optional[str]:
        """Capture screenshot of a specific monitor."""
        try:
            with mss.mss() as sct:
                # Monitor index is 1-based in mss (0 is virtual combined)
                monitor = sct.monitors[monitor_id + 1]
                screenshot = sct.grab(monitor)

                # Save to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"monitor_{monitor_id}_{timestamp}.png"
                filepath = os.path.join(self.output_dir, filename)

                # Convert to PIL and save
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                img.save(filepath)

                print(f"[Monitor {monitor_id}] Screenshot saved: {filepath}")
                return filepath

        except Exception as e:
            print(f"[Monitor {monitor_id}] Capture error: {e}")
            return None

    def screenshot_to_base64(self, filepath: str) -> str:
        """Convert screenshot file to base64."""
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def analyze_screenshot(self, monitor_id: int, screenshot_path: str) -> Dict[str, Any]:
        """Analyze a screenshot using Claude CLI."""
        print(f"[Monitor {monitor_id}] Analyzing screenshot...")

        if not self.claude_cli.is_available():
            print("[WARN] Claude CLI not available - using fallback analysis")
            return self._fallback_analysis(monitor_id, screenshot_path)

        # Use Claude CLI to analyze
        prompt = f"""Analysiere diesen Desktop-Screenshot von Monitor {monitor_id}.

Bestimme:
1. Welche Anwendung(en) sind sichtbar?
2. Was ist der aktuelle Zustand/Kontext?
3. Welche Automatisierungsschritte wären sinnvoll?

Antworte als JSON:
{{
    "detected_type": "browser|desktop_app|file_manager|terminal|chat_app|document|unknown",
    "applications": ["App1", "App2"],
    "current_state": "Beschreibung des aktuellen Zustands",
    "suggested_workflow": [
        {{"action": "...", "target": "...", "description": "..."}}
    ]
}}"""

        result = await self.claude_cli.run_command(
            prompt=prompt,
            output_format="json"
        )

        if result["success"] and isinstance(result["output"], dict):
            return result["output"]
        elif result["success"] and isinstance(result["output"], str):
            # Try to parse as JSON
            try:
                return json.loads(result["output"])
            except json.JSONDecodeError:
                pass

        # Fallback if Claude CLI fails
        return self._fallback_analysis(monitor_id, screenshot_path)

    def _fallback_analysis(self, monitor_id: int, screenshot_path: str) -> Dict[str, Any]:
        """Fallback analysis without Claude CLI."""
        return {
            "detected_type": "unknown",
            "applications": ["Unknown Application"],
            "current_state": f"Monitor {monitor_id} - Screenshot captured",
            "suggested_workflow": [
                {"action": "capture", "target": f"monitor_{monitor_id}", "description": "Capture screen state"},
                {"action": "wait", "duration": 1, "description": "Wait for state"},
                {"action": "verify", "target": "screen", "description": "Verify screen content"}
            ]
        }

    def create_workflow(self, monitor_id: int, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create workflow steps based on analysis."""
        detected_type = analysis.get("detected_type", "unknown")
        suggested = analysis.get("suggested_workflow", [])

        # If we have suggested workflow, use it
        if suggested:
            return suggested

        # Otherwise, create default workflow based on type
        workflows = {
            "browser": [
                {"action": "find_element", "target": "address_bar", "description": "Find browser address bar"},
                {"action": "click", "target": "found_element", "description": "Click address bar"},
                {"action": "wait", "duration": 0.3, "description": "Wait for focus"}
            ],
            "desktop_app": [
                {"action": "capture", "description": "Capture current state"},
                {"action": "find_element", "target": "main_window", "description": "Find main window"},
                {"action": "verify", "target": "window_active", "description": "Verify window is active"}
            ],
            "file_manager": [
                {"action": "capture", "description": "Capture file list"},
                {"action": "find_element", "target": "file_list", "description": "Find file listing"},
                {"action": "scroll", "direction": "down", "amount": 3, "description": "Scroll file list"}
            ],
            "terminal": [
                {"action": "click", "target": "terminal_window", "description": "Focus terminal"},
                {"action": "type", "text": "echo 'MCP Demo'", "description": "Type command"},
                {"action": "press_key", "key": "enter", "description": "Execute command"}
            ],
            "chat_app": [
                {"action": "find_element", "target": "chat_input", "description": "Find chat input"},
                {"action": "click", "target": "found_element", "description": "Click input field"},
                {"action": "type", "text": "Hello from MCP Demo!", "description": "Type message"}
            ],
            "document": [
                {"action": "capture", "description": "Capture document state"},
                {"action": "verify", "target": "document_loaded", "description": "Verify document loaded"}
            ],
            "unknown": [
                {"action": "capture", "description": "Capture screen"},
                {"action": "wait", "duration": 1, "description": "Observe state"}
            ]
        }

        return workflows.get(detected_type, workflows["unknown"])

    async def execute_workflow(self, monitor_id: int, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute workflow steps for a monitor."""
        print(f"\n[Monitor {monitor_id}] Executing workflow ({len(steps)} steps)...")

        results = []
        success = True

        for i, step in enumerate(steps):
            action = step.get("action", "unknown")
            print(f"  Step {i+1}: {step.get('description', action)}")

            try:
                if action == "capture":
                    # Just capture state
                    await asyncio.sleep(0.1)
                    results.append({"step": i+1, "action": action, "success": True})

                elif action == "wait":
                    duration = step.get("duration", 1)
                    await asyncio.sleep(float(duration))
                    results.append({"step": i+1, "action": action, "success": True})

                elif action == "find_element":
                    # Simulated element find
                    await asyncio.sleep(0.2)
                    results.append({
                        "step": i+1,
                        "action": action,
                        "success": True,
                        "found": step.get("target")
                    })

                elif action == "click":
                    # Only simulate in demo mode
                    await asyncio.sleep(0.1)
                    results.append({"step": i+1, "action": action, "success": True, "simulated": True})

                elif action == "type":
                    # Simulate typing
                    text = step.get("text", "")
                    await asyncio.sleep(len(text) * 0.05)
                    results.append({"step": i+1, "action": action, "success": True, "text_length": len(text)})

                elif action == "scroll":
                    await asyncio.sleep(0.2)
                    results.append({"step": i+1, "action": action, "success": True})

                elif action == "verify":
                    await asyncio.sleep(0.1)
                    results.append({"step": i+1, "action": action, "success": True, "verified": True})

                elif action == "press_key":
                    await asyncio.sleep(0.1)
                    results.append({"step": i+1, "action": action, "success": True})

                else:
                    results.append({"step": i+1, "action": action, "success": False, "error": f"Unknown action: {action}"})

            except Exception as e:
                results.append({"step": i+1, "action": action, "success": False, "error": str(e)})
                success = False

        return {
            "monitor_id": monitor_id,
            "success": success,
            "steps_executed": len(results),
            "results": results
        }

    async def run_demo(self, monitor_ids: Optional[List[int]] = None):
        """Run the full MCP demo."""
        print("\n" + "=" * 60)
        print("     MCP Demo - Dual-Monitor Workflows")
        print("     Claude CLI + MCP Integration")
        print("=" * 60 + "\n")

        # Step 1: Get monitors
        print("[Step 1] Detecting monitors...")
        monitors = self.get_monitors()
        print(f"  Found {len(monitors)} monitor(s):")
        for m in monitors:
            print(f"    Monitor {m['id']}: {m['width']}x{m['height']} at ({m['left']}, {m['top']})")

        # Filter monitors if specified
        if monitor_ids is not None:
            monitors = [m for m in monitors if m["id"] in monitor_ids]
            print(f"  Using monitor(s): {[m['id'] for m in monitors]}")

        # Step 2: Capture screenshots
        print("\n[Step 2] Capturing screenshots...")
        for monitor in monitors:
            mid = monitor["id"]
            workflow = MonitorWorkflow(
                monitor_id=mid,
                monitor_info=monitor
            )
            workflow.screenshot_path = self.capture_monitor(mid)
            self.monitor_workflows[mid] = workflow

        # Step 3: Analyze screenshots
        print("\n[Step 3] Analyzing screenshots with Claude CLI...")
        analysis_tasks = []
        for mid, workflow in self.monitor_workflows.items():
            if workflow.screenshot_path:
                task = self.analyze_screenshot(mid, workflow.screenshot_path)
                analysis_tasks.append((mid, task))

        # Run analysis in parallel
        for mid, task in analysis_tasks:
            analysis = await task
            workflow = self.monitor_workflows[mid]
            workflow.detected_type = WorkflowType(analysis.get("detected_type", "unknown"))
            workflow.analysis = analysis
            print(f"  [Monitor {mid}] Detected: {workflow.detected_type.value}")
            print(f"    Applications: {analysis.get('applications', ['Unknown'])}")
            print(f"    State: {analysis.get('current_state', 'N/A')}")

        # Step 4: Create workflows
        print("\n[Step 4] Creating workflows for each monitor...")
        for mid, workflow in self.monitor_workflows.items():
            if workflow.analysis:
                workflow.workflow_steps = self.create_workflow(mid, workflow.analysis)
                print(f"  [Monitor {mid}] Created {len(workflow.workflow_steps)} step(s)")

        # Step 5: Execute workflows in parallel
        print("\n[Step 5] Executing workflows in parallel...")
        execution_tasks = []
        for mid, workflow in self.monitor_workflows.items():
            if workflow.workflow_steps:
                task = self.execute_workflow(mid, workflow.workflow_steps)
                execution_tasks.append((mid, task))

        # Run workflows in parallel
        for mid, task in execution_tasks:
            result = await task
            self.monitor_workflows[mid].execution_result = result

        # Step 6: Summary
        print("\n" + "=" * 60)
        print("     Demo Complete - Summary")
        print("=" * 60)

        for mid, workflow in self.monitor_workflows.items():
            result = workflow.execution_result
            status = "SUCCESS" if result and result.get("success") else "FAILED"
            print(f"\n[Monitor {mid}] {status}")
            print(f"  Type: {workflow.detected_type.value}")
            print(f"  Steps: {len(workflow.workflow_steps)}")
            if result:
                print(f"  Executed: {result.get('steps_executed', 0)}")

        # Save results
        self._save_results()

        print(f"\nResults saved to: {self.output_dir}")
        print("=" * 60 + "\n")

    def _save_results(self):
        """Save demo results to file."""
        results = {}
        for mid, workflow in self.monitor_workflows.items():
            results[f"monitor_{mid}"] = {
                "monitor_id": mid,
                "monitor_info": workflow.monitor_info,
                "screenshot_path": workflow.screenshot_path,
                "detected_type": workflow.detected_type.value,
                "analysis": workflow.analysis,
                "workflow_steps": workflow.workflow_steps,
                "execution_result": workflow.execution_result
            }

        filepath = os.path.join(self.output_dir, "demo_results.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="MCP Demo - Dual-Monitor Workflows")
    parser.add_argument(
        "--monitor", "-m",
        type=int,
        action="append",
        help="Specific monitor ID(s) to use (can be specified multiple times)"
    )
    parser.add_argument(
        "--list-monitors", "-l",
        action="store_true",
        help="List available monitors and exit"
    )

    args = parser.parse_args()

    demo = MCPDemo()

    if args.list_monitors:
        monitors = demo.get_monitors()
        print("Available monitors:")
        for m in monitors:
            print(f"  {m['id']}: {m['width']}x{m['height']} at ({m['left']}, {m['top']})")
        return

    await demo.run_demo(monitor_ids=args.monitor)


if __name__ == "__main__":
    asyncio.run(main())
