"""Command Executor for Voice-Controlled Desktop Automation.

Executes parsed intents using MCP tools and PyAutoGUI.
Connects the intent parser output to actual desktop automation.
"""

import os
import sys
import asyncio
import logging
import webbrowser
import time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Handle both module and standalone imports
try:
    from .intent_parser import ParsedIntent, Action, ActionType
except ImportError:
    from intent_parser import ParsedIntent, Action, ActionType

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing an action."""
    success: bool
    action: Action
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0


@dataclass
class ExecutionReport:
    """Report of executing all actions in an intent."""
    intent: ParsedIntent
    results: List[ExecutionResult] = field(default_factory=list)
    total_duration_ms: float = 0
    success: bool = True
    feedback_message: str = ""


class CommandExecutor:
    """Execute parsed intents on the desktop."""

    def __init__(
        self,
        on_action_start: Optional[Callable[[Action], None]] = None,
        on_action_complete: Optional[Callable[[ExecutionResult], None]] = None,
        on_feedback: Optional[Callable[[str], None]] = None,
        use_vision: bool = True
    ):
        """Initialize CommandExecutor.

        Args:
            on_action_start: Callback when action starts
            on_action_complete: Callback when action completes
            on_feedback: Callback for voice feedback messages
            use_vision: Whether to use vision agent for element detection
        """
        self.on_action_start = on_action_start
        self.on_action_complete = on_action_complete
        self.on_feedback = on_feedback
        self.use_vision = use_vision

        # Import pyautogui lazily
        self._pyautogui = None
        self._vision_agent = None

    def _get_pyautogui(self):
        """Get pyautogui module (lazy import)."""
        if self._pyautogui is None:
            import pyautogui
            pyautogui.FAILSAFE = True  # Move mouse to corner to abort
            pyautogui.PAUSE = 0.1  # Small pause between actions
            self._pyautogui = pyautogui
        return self._pyautogui

    async def _get_vision_agent(self):
        """Get vision agent (lazy import)."""
        if self._vision_agent is None and self.use_vision:
            try:
                from agents.vision_agent import get_vision_agent
                self._vision_agent = get_vision_agent()
            except ImportError:
                logger.warning("Vision agent not available")
        return self._vision_agent

    def _send_feedback(self, message: str):
        """Send feedback message."""
        if self.on_feedback:
            self.on_feedback(message)
        logger.info(f"Feedback: {message}")

    async def execute(self, intent: ParsedIntent) -> ExecutionReport:
        """Execute all actions in a parsed intent.

        Args:
            intent: ParsedIntent with actions to execute

        Returns:
            ExecutionReport with results
        """
        report = ExecutionReport(intent=intent)
        start_time = time.time()

        if intent.error:
            report.success = False
            report.feedback_message = f"Fehler beim Verstehen: {intent.error}"
            self._send_feedback(report.feedback_message)
            return report

        if not intent.actions:
            report.success = False
            report.feedback_message = "Keine Aktionen erkannt"
            self._send_feedback(report.feedback_message)
            return report

        # Announce what we're doing
        self._send_feedback(f"Führe {len(intent.actions)} Aktionen aus: {intent.context}")

        for action in intent.actions:
            if self.on_action_start:
                self.on_action_start(action)

            action_start = time.time()
            result = await self._execute_action(action)
            result.duration_ms = (time.time() - action_start) * 1000

            report.results.append(result)

            if self.on_action_complete:
                self.on_action_complete(result)

            if not result.success:
                report.success = False
                self._send_feedback(f"Fehler bei {action.description}: {result.error}")
                break

        report.total_duration_ms = (time.time() - start_time) * 1000

        if report.success:
            report.feedback_message = f"Erledigt: {intent.context}"
        else:
            report.feedback_message = f"Abgebrochen: {report.results[-1].error if report.results else 'Unbekannter Fehler'}"

        self._send_feedback(report.feedback_message)
        return report

    async def _execute_action(self, action: Action) -> ExecutionResult:
        """Execute a single action.

        Args:
            action: Action to execute

        Returns:
            ExecutionResult with outcome
        """
        try:
            handler = self._get_handler(action.type)
            if handler is None:
                return ExecutionResult(
                    success=False,
                    action=action,
                    error=f"Unknown action type: {action.type.value}"
                )

            result = await handler(action.params)
            return ExecutionResult(
                success=True,
                action=action,
                result=result
            )

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return ExecutionResult(
                success=False,
                action=action,
                error=str(e)
            )

    def _get_handler(self, action_type: ActionType):
        """Get handler function for action type."""
        handlers = {
            ActionType.OPEN_URL: self._handle_open_url,
            ActionType.CLICK: self._handle_click,
            ActionType.TYPE_TEXT: self._handle_type_text,
            ActionType.SCROLL: self._handle_scroll,
            ActionType.VISION_ANALYZE: self._handle_vision_analyze,
            ActionType.WAIT: self._handle_wait,
            ActionType.SCREENSHOT: self._handle_screenshot,
            ActionType.READ_SCREEN: self._handle_read_screen,
            ActionType.FIND_ELEMENT: self._handle_find_element,
            ActionType.KEY_PRESS: self._handle_key_press,
            ActionType.SEARCH: self._handle_search,
            ActionType.NAVIGATE: self._handle_navigate,
        }
        return handlers.get(action_type)

    async def _handle_open_url(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Open a URL in the browser."""
        url = params.get("url", "")
        if not url:
            raise ValueError("URL not specified")

        # Ensure URL has protocol
        if not url.startswith("http"):
            url = "https://" + url

        logger.info(f"Opening URL: {url}")
        webbrowser.open(url)

        return {"url": url, "opened": True}

    async def _handle_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Click at a position or on an element."""
        pyautogui = self._get_pyautogui()

        x = params.get("x")
        y = params.get("y")
        target = params.get("target")

        if x is not None and y is not None:
            # Direct coordinates
            logger.info(f"Clicking at ({x}, {y})")
            pyautogui.click(x, y)
            return {"x": x, "y": y, "clicked": True}

        elif target:
            # Find element first using vision
            if self.use_vision:
                element = await self._find_element_by_description(target)
                if element:
                    x, y = element.get("x"), element.get("y")
                    logger.info(f"Clicking element '{target}' at ({x}, {y})")
                    pyautogui.click(x, y)
                    return {"target": target, "x": x, "y": y, "clicked": True}

            raise ValueError(f"Could not find element: {target}")
        else:
            raise ValueError("No click target specified")

    async def _handle_type_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Type text."""
        pyautogui = self._get_pyautogui()

        text = params.get("text", "")
        target = params.get("target")

        if not text:
            raise ValueError("No text to type")

        # Click on target first if specified
        if target:
            await self._handle_click({"target": target})
            await asyncio.sleep(0.2)

        logger.info(f"Typing: {text[:50]}...")
        pyautogui.write(text, interval=0.02)

        return {"text": text, "typed": True}

    async def _handle_scroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Scroll the page."""
        pyautogui = self._get_pyautogui()

        direction = params.get("direction", "down")
        amount = params.get("amount", 500)

        # PyAutoGUI scroll: positive = up, negative = down
        scroll_amount = amount if direction == "up" else -amount

        # Convert to scroll units (roughly pixels to lines)
        scroll_clicks = scroll_amount // 100

        logger.info(f"Scrolling {direction} by {amount}")
        pyautogui.scroll(scroll_clicks)

        return {"direction": direction, "amount": amount, "scrolled": True}

    async def _handle_vision_analyze(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze screen with vision agent."""
        prompt = params.get("prompt", "Describe what is on the screen")

        vision_agent = await self._get_vision_agent()
        if not vision_agent:
            # Fallback: take screenshot and return path
            pyautogui = self._get_pyautogui()
            screenshot = pyautogui.screenshot()
            screenshot.save("vision_analysis.png")
            return {"analysis": "Vision agent not available", "screenshot": "vision_analysis.png"}

        try:
            # Get screenshot
            pyautogui = self._get_pyautogui()
            screenshot = pyautogui.screenshot()

            # Convert to bytes
            import io
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()

            # Analyze with vision agent
            result = await vision_agent.analyze_with_prompt(image_bytes, prompt)
            return {"analysis": result}

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return {"analysis": f"Error: {e}"}

    async def _handle_wait(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Wait for specified time."""
        seconds = params.get("seconds", 1)
        logger.info(f"Waiting {seconds} seconds")
        await asyncio.sleep(seconds)
        return {"waited": seconds}

    async def _handle_screenshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Take a screenshot."""
        pyautogui = self._get_pyautogui()

        filename = params.get("filename", "screenshot.png")
        screenshot = pyautogui.screenshot()
        screenshot.save(filename)

        logger.info(f"Screenshot saved: {filename}")
        return {"filename": filename, "saved": True}

    async def _handle_read_screen(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read text from screen using OCR."""
        region = params.get("region")  # Optional: (x, y, width, height)

        try:
            # Try using the MCP handoff tools
            from mcp_server_handoff import handle_read_screen
            result = await handle_read_screen(region=region)
            return result
        except ImportError:
            # Fallback: use vision_analyze
            return await self._handle_vision_analyze({"prompt": "Read all visible text on the screen"})

    async def _handle_find_element(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Find a UI element by description."""
        description = params.get("description", "")
        if not description:
            raise ValueError("No element description provided")

        return await self._find_element_by_description(description)

    async def _find_element_by_description(self, description: str) -> Dict[str, Any]:
        """Find element using vision agent."""
        vision_agent = await self._get_vision_agent()
        if not vision_agent:
            logger.warning("Vision agent not available, trying alternative approaches")
            # Try alternative: if it's a text field, try Tab or click center
            raise ValueError("Vision agent not available for element detection")

        # Get screenshot
        pyautogui = self._get_pyautogui()
        screenshot = pyautogui.screenshot()
        screen_width, screen_height = screenshot.size

        import io
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        # Ask vision agent to find element
        prompt = f"""Analyze this screenshot and find the UI element described as: "{description}"

The screen resolution is {screen_width}x{screen_height}.

Return ONLY a JSON object with these fields:
- found: true/false
- x: pixel x-coordinate of element center
- y: pixel y-coordinate of element center
- confidence: 0.0-1.0
- description: brief description of what you found

Example response:
{{"found": true, "x": 450, "y": 320, "confidence": 0.9, "description": "Search input field"}}

If you cannot find the element:
{{"found": false, "reason": "Element not visible on screen"}}

Important: Return ONLY the JSON, no other text."""

        logger.info(f"Vision search for: {description}")
        result = await vision_agent.analyze_with_prompt(image_bytes, prompt)
        logger.debug(f"Vision result: {result[:500] if result else 'None'}...")

        # Try to parse JSON from result
        import json
        import re

        # Try multiple JSON extraction patterns
        json_patterns = [
            r'\{[^{}]*"found"[^{}]*\}',  # Match JSON with "found" key
            r'```json\s*(\{[^`]*\})\s*```',  # Match JSON in code block
            r'(\{[^{}]*\})',  # Match any simple JSON
        ]

        for pattern in json_patterns:
            json_match = re.search(pattern, result, re.DOTALL)
            if json_match:
                try:
                    json_str = json_match.group(1) if '```' in pattern else json_match.group()
                    element_data = json.loads(json_str)
                    logger.info(f"Parsed element data: {element_data}")

                    if element_data.get("found"):
                        # Validate coordinates are within screen bounds
                        x = element_data.get("x", 0)
                        y = element_data.get("y", 0)
                        if 0 <= x <= screen_width and 0 <= y <= screen_height:
                            return element_data
                        else:
                            logger.warning(f"Coordinates out of bounds: ({x}, {y})")
                    else:
                        reason = element_data.get("reason", "Unknown")
                        logger.info(f"Element not found by vision: {reason}")
                except json.JSONDecodeError as e:
                    logger.debug(f"JSON parse failed: {e}")
                    continue

        raise ValueError(f"Element not found: {description}")

    async def _handle_key_press(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Press a key or key combination."""
        pyautogui = self._get_pyautogui()

        key = params.get("key", "")
        modifiers = params.get("modifiers", [])  # e.g., ["ctrl", "shift"]

        if not key:
            raise ValueError("No key specified")

        # Build hotkey if modifiers present
        if modifiers:
            hotkey = modifiers + [key]
            logger.info(f"Pressing hotkey: {'+'.join(hotkey)}")
            pyautogui.hotkey(*hotkey)
        else:
            logger.info(f"Pressing key: {key}")
            pyautogui.press(key)

        return {"key": key, "modifiers": modifiers, "pressed": True}

    async def _handle_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for text on screen."""
        query = params.get("query", "")
        if not query:
            raise ValueError("No search query specified")

        # Use Ctrl+F to open find dialog
        pyautogui = self._get_pyautogui()
        pyautogui.hotkey("ctrl", "f")
        await asyncio.sleep(0.3)

        # Type search query
        pyautogui.write(query, interval=0.02)

        return {"query": query, "searched": True}

    async def _handle_navigate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Navigate to a target (URL or application)."""
        target = params.get("target", "")

        if target.startswith("http") or "." in target:
            # URL
            return await self._handle_open_url({"url": target})
        else:
            # Try to open as application (Windows)
            import subprocess
            try:
                subprocess.Popen(["start", target], shell=True)
                return {"target": target, "opened": True}
            except Exception as e:
                raise ValueError(f"Could not navigate to: {target} - {e}")


class VoiceAutomationPipeline:
    """Complete voice automation pipeline: STT -> Intent -> Execute -> TTS."""

    def __init__(
        self,
        on_listening: Optional[Callable[[], None]] = None,
        on_thinking: Optional[Callable[[], None]] = None,
        on_executing: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None
    ):
        """Initialize the full pipeline.

        Args:
            on_listening: Callback when listening for speech
            on_thinking: Callback when processing intent
            on_executing: Callback when executing actions
            on_complete: Callback when complete with feedback
        """
        self.on_listening = on_listening
        self.on_thinking = on_thinking
        self.on_executing = on_executing
        self.on_complete = on_complete

        # Initialize components
        try:
            from .speech_to_text import SpeechToText, STTBackend
            from .intent_parser import IntentParser, QuickIntentParser
        except ImportError:
            from speech_to_text import SpeechToText, STTBackend
            from intent_parser import IntentParser, QuickIntentParser

        self.stt = SpeechToText(language="de")  # Auto-detect backend
        self.intent_parser = QuickIntentParser(fallback_parser=IntentParser())
        self.executor = CommandExecutor(
            on_feedback=self._handle_feedback
        )

        self._tts = None

    def _handle_feedback(self, message: str):
        """Handle feedback messages (for TTS)."""
        if self.on_complete:
            self.on_complete(message)

        # TTS feedback if available
        if self._tts:
            try:
                self._tts.speak(message)
            except Exception as e:
                logger.warning(f"TTS failed: {e}")

    async def process_audio(self, audio_data: bytes) -> ExecutionReport:
        """Process audio through the full pipeline.

        Args:
            audio_data: Raw audio bytes

        Returns:
            ExecutionReport with results
        """
        # 1. Transcribe audio
        if self.on_listening:
            self.on_listening()

        transcription = await self.stt.transcribe_audio(audio_data)
        if not transcription.text:
            return ExecutionReport(
                intent=ParsedIntent(original_text="", error="No speech detected"),
                success=False,
                feedback_message="Ich habe nichts verstanden"
            )

        logger.info(f"Transcribed: {transcription.text}")

        # 2. Parse intent
        if self.on_thinking:
            self.on_thinking()

        intent = await self.intent_parser.parse(transcription.text)

        # 3. Execute
        if self.on_executing:
            self.on_executing(intent.context or transcription.text)

        report = await self.executor.execute(intent)

        return report

    async def process_text(self, text: str) -> ExecutionReport:
        """Process text command through the pipeline (skip STT).

        Args:
            text: Text command

        Returns:
            ExecutionReport with results
        """
        if self.on_thinking:
            self.on_thinking()

        intent = await self.intent_parser.parse(text)

        if self.on_executing:
            self.on_executing(intent.context or text)

        report = await self.executor.execute(intent)

        return report


# Test/demo code
if __name__ == "__main__":
    async def main():
        print("=== Command Executor Test ===\n")

        # Test with simple commands
        from intent_parser import IntentParser, QuickIntentParser

        parser = QuickIntentParser()
        executor = CommandExecutor(
            on_feedback=lambda msg: print(f"[Feedback] {msg}")
        )

        test_commands = [
            "Scrolle nach unten",
            "Screenshot",
        ]

        for cmd in test_commands:
            print(f"\nCommand: {cmd}")
            intent = await parser.parse(cmd)
            report = await executor.execute(intent)

            print(f"Success: {report.success}")
            print(f"Duration: {report.total_duration_ms:.0f}ms")

            for result in report.results:
                status = "OK" if result.success else "FAILED"
                print(f"  [{status}] {result.action.description}")

    asyncio.run(main())
