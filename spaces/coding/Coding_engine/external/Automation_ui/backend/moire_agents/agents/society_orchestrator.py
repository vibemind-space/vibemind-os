"""
Society of Mind Orchestrator für MoireTracker_v2

Implementiert das AutoGen SocietyOfMindAgent Pattern mit:
- Inner Teams: PlanningTeam (Planner + Critic), ReflectionTeam (Vision + GoalChecker)
- Outer Team: Kombiniert Inner Teams für hierarchische Task-Ausführung
- Integration mit MoireServer für Screenshots und State
- SQLite Memory für Persistence (Conversation History, Task Memory, UI Cache, Patterns)
- Validation Chain für Schritt-Verifikation
"""

import asyncio
import logging
import base64
import os
import sys
import uuid
import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# AutoGen Imports
try:
    from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
    from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
    from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
    from autogen_agentchat.ui import Console
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    HAS_AUTOGEN_AGENTCHAT = True
except ImportError:
    HAS_AUTOGEN_AGENTCHAT = False
    logging.warning("autogen-agentchat not installed. Run: pip install autogen-agentchat autogen-ext[openai]")

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.openrouter_client import OpenRouterClient, get_openrouter_client

# Memory System Import
try:
    from memory.sqlite_memory import (
        AgentMemory,
        ConversationMessage,
        TaskRecord,
        TaskStatus,
        UIElementCache,
        ActionPattern,
        get_memory,
        learn_from_successful_task
    )
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    logging.warning("Memory module not found. Running without persistence.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== Custom Tools für Desktop Automation ====================

class DesktopTools:
    """Desktop Automation Tools die von den Agents genutzt werden können."""

    def __init__(
        self,
        moire_client: Optional[Any] = None,
        interaction_agent: Optional[Any] = None,
        memory: Optional['AgentMemory'] = None
    ):
        self.moire_client = moire_client
        self.interaction_agent = interaction_agent
        self.memory = memory
        self._last_screenshot: Optional[bytes] = None
        self._last_state: Optional[Dict[str, Any]] = None
        self._last_ui_context: Optional[Any] = None
        self._current_application: str = "Windows"

    async def capture_screenshot(self) -> str:
        """Captured einen Screenshot und gibt ihn als base64 zurück."""
        if not self.moire_client:
            return "ERROR: Kein MoireServer Client verfügbar"
        
        try:
            if hasattr(self.moire_client, 'ensure_connected'):
                await self.moire_client.ensure_connected()
            
            if hasattr(self.moire_client, 'capture_and_wait_for_complete'):
                result = await self.moire_client.capture_and_wait_for_complete(timeout=30)
                if result.success:
                    self._last_ui_context = result.ui_context
                    if result.screenshot_base64:
                        if result.screenshot_base64.startswith('data:'):
                            _, data = result.screenshot_base64.split(',', 1)
                        else:
                            data = result.screenshot_base64
                        self._last_screenshot = base64.b64decode(data)
                    return f"Screenshot captured: {result.boxes_count} boxes, {result.texts_count} texts found in {result.processing_time_ms:.0f}ms"
                else:
                    return f"Screenshot capture failed: {result.error}"
            
            if hasattr(self.moire_client, 'request_capture'):
                await self.moire_client.request_capture()
                await asyncio.sleep(0.3)
            
            if hasattr(self.moire_client, 'get_last_screenshot'):
                screenshot = await self.moire_client.get_last_screenshot()
                if screenshot:
                    self._last_screenshot = screenshot
                    return f"Screenshot captured: {len(screenshot)} bytes"
            
            return "Screenshot captured (cached)"
        except Exception as e:
            return f"ERROR capturing screenshot: {e}"
    
    async def get_screen_state(self) -> str:
        """Holt den aktuellen Bildschirm-State mit UI-Elementen und OCR-Texten."""
        if not self.moire_client:
            return "ERROR: Kein MoireServer Client verfügbar"
        
        try:
            if hasattr(self.moire_client, 'capture_and_wait_for_complete'):
                result = await self.moire_client.capture_and_wait_for_complete(timeout=30)
                if result.success:
                    self._last_ui_context = result.ui_context
                    
                    if result.ui_context:
                        elements = result.ui_context.elements if hasattr(result.ui_context, 'elements') else []
                        texts_list = [
                            {
                                "text": e.text,
                                "x": e.bounds.get("x", 0) if e.bounds else 0,
                                "y": e.bounds.get("y", 0) if e.bounds else 0,
                                "width": e.bounds.get("width", 0) if e.bounds else 0,
                                "height": e.bounds.get("height", 0) if e.bounds else 0,
                                "confidence": e.confidence,
                                "category": getattr(e, 'category', None)  # NEU: CNN Category
                            }
                            for e in elements if e.text
                        ]
                        boxes_list = [
                            {
                                "id": e.id,
                                "type": e.type,
                                "text": e.text,
                                "x": e.bounds.get("x", 0) if e.bounds else 0,
                                "y": e.bounds.get("y", 0) if e.bounds else 0,
                                "width": e.bounds.get("width", 0) if e.bounds else 0,
                                "height": e.bounds.get("height", 0) if e.bounds else 0,
                                "confidence": e.confidence,
                                "category": getattr(e, 'category', None)  # NEU: CNN Category
                            }
                            for e in elements
                        ]
                        self._last_state = {
                            "boxes": boxes_list,
                            "texts": texts_list,
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        self._last_state = {
                            "boxes": [],
                            "texts": [],
                            "timestamp": datetime.now().isoformat()
                        }
                    
                    boxes_count = len(self._last_state["boxes"])
                    texts = self._last_state.get("texts", [])
                    boxes = self._last_state.get("boxes", [])
                    
                    # NEU: Kategorien zählen
                    categories: Dict[str, int] = {}
                    for box in boxes:
                        cat = box.get('category') or 'unknown'
                        categories[cat] = categories.get(cat, 0) + 1
                    
                    state_summary = f"Screen State:\n"
                    state_summary += f"- {boxes_count} UI elements detected\n"
                    state_summary += f"- {len(texts)} text regions found\n"
                    
                    # NEU: Kategorie-Verteilung anzeigen
                    if categories:
                        state_summary += f"- Categories: {', '.join(f'{k}:{v}' for k, v in sorted(categories.items()))}\n"
                    
                    if texts:
                        state_summary += "\nVisible Text:\n"
                        for t in texts[:20]:
                            text_content = t.get("text", "")[:50]
                            category = t.get("category", "")
                            if text_content:
                                cat_str = f" [{category}]" if category else ""
                                state_summary += f"  - \"{text_content}\"{cat_str}\n"
                    
                    # NEU: Buttons und Icons besonders hervorheben
                    buttons = [b for b in boxes if b.get("category") == "button"]
                    icons = [b for b in boxes if b.get("category") == "icon"]
                    inputs = [b for b in boxes if b.get("category") == "input"]
                    
                    if buttons:
                        state_summary += f"\nButtons ({len(buttons)}):\n"
                        for btn in buttons[:10]:
                            text = btn.get("text", "")[:30] or f"at ({btn.get('x')},{btn.get('y')})"
                            state_summary += f"  - {text}\n"
                    
                    if icons:
                        state_summary += f"\nIcons ({len(icons)}):\n"
                        for icon in icons[:10]:
                            text = icon.get("text", "")[:30] or f"at ({icon.get('x')},{icon.get('y')})"
                            state_summary += f"  - {text}\n"
                    
                    if inputs:
                        state_summary += f"\nInput Fields ({len(inputs)}):\n"
                        for inp in inputs[:10]:
                            text = inp.get("text", "")[:30] or f"at ({inp.get('x')},{inp.get('y')})"
                            state_summary += f"  - {text}\n"
                    
                    self._last_state["boxes"] = boxes_list
                    self._last_state["texts"] = texts_list
                    self._last_state["timestamp"] = datetime.now().isoformat()
                    
                    return state_summary
                else:
                    return f"ERROR getting screen state: {result.error}"
            
            if hasattr(self.moire_client, 'get_ui_context'):
                ui_context = await self.moire_client.get_ui_context()
                if ui_context:
                    self._last_state = ui_context
                    return f"Screen state retrieved: {len(ui_context.get('boxes', []))} elements"
            
            return "ERROR: Could not retrieve screen state"
        except Exception as e:
            return f"ERROR getting screen state: {e}"
    
    async def find_elements_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Findet alle UI-Elemente einer bestimmten CNN-Kategorie.
        
        Verfügbare Kategorien:
        - button: Schaltflächen
        - icon: Icons/Symbole
        - input: Eingabefelder
        - text: Textbereiche
        - checkbox: Checkboxen
        - radio: Radio-Buttons
        - dropdown: Dropdown-Menüs
        - link: Links
        - container: Container/Gruppen
        - menu: Menüs
        - toolbar: Toolbars
        """
        if not self._last_state:
            await self.get_screen_state()
        
        if not self._last_state:
            return []
        
        boxes = self._last_state.get('boxes', [])
        return [b for b in boxes if b.get('category', '').lower() == category.lower() or
                (b.get('type', '').lower() == category.lower() and not b.get('category'))]
    
    async def click_by_category(self, category: str, text: Optional[str] = None, index: int = 0) -> str:
        """
        Klickt auf ein Element basierend auf seiner CNN-Kategorie.
        
        Args:
            category: Die Kategorie (button, icon, input, etc.)
            text: Optional - nur Elemente mit diesem Text
            index: Welches Element wenn mehrere gefunden (0 = erstes)
        
        Beispiele:
        - click_by_category("button", "OK") - Klickt auf den OK-Button
        - click_by_category("icon") - Klickt auf das erste Icon
        - click_by_category("input", index=1) - Klickt auf das zweite Eingabefeld
        """
        elements = await self.find_elements_by_category(category)
        
        if not elements:
            return f"ERROR: No elements found with category '{category}'"
        
        # Filter by text if specified
        if text:
            filtered = [e for e in elements if text.lower() in (e.get("text") or "").lower()]
            if filtered:
                elements = filtered
            else:
                return f"ERROR: No {category} found with text '{text}'"
        
        # Select by index
        if index >= len(elements):
            return f"ERROR: Only {len(elements)} {category}(s) found, cannot select index {index}"
        
        element = elements[index]
        x = element.get("x", 0) + element.get("width", 0) // 2
        y = element.get("y", 0) + element.get("height", 0) // 2
        
        element_text = element.get("text", "")[:30] or f"at ({x},{y})"
        logger.info(f"Clicking {category} '{element_text}' at ({x}, {y})")
        
        return await self.click(x, y)
    
    async def get_buttons(self) -> List[Dict[str, Any]]:
        """Gibt alle erkannten Buttons zurück."""
        return await self.find_elements_by_category("button")
    
    async def get_icons(self) -> List[Dict[str, Any]]:
        """Gibt alle erkannten Icons zurück."""
        return await self.find_elements_by_category("icon")
    
    async def get_inputs(self) -> List[Dict[str, Any]]:
        """Gibt alle erkannten Eingabefelder zurück."""
        return await self.find_elements_by_category("input")

    async def click(self, x: int, y: int) -> str:
        """Klickt an die angegebenen Koordinaten."""
        if self.interaction_agent:
            try:
                result = await self.interaction_agent.click((x, y))
                return f"Clicked at ({x}, {y}): {result}"
            except Exception as e:
                return f"ERROR clicking at ({x}, {y}): {e}"
        
        if self.moire_client and hasattr(self.moire_client, 'send_command'):
            try:
                await self.moire_client.send_command({"type": "click", "x": x, "y": y})
                return f"Clicked at ({x}, {y})"
            except Exception as e:
                return f"ERROR clicking: {e}"
        
        return "ERROR: No interaction agent available"
    
    async def click_by_text(self, text: str, exact_match: bool = False) -> str:
        """Klickt auf ein Element anhand seines Texts."""
        if not self._last_state:
            await self.get_screen_state()
        
        if not self._last_state:
            return f"ERROR: Could not get screen state to find '{text}'"
        
        texts = self._last_state.get("texts", [])
        for t in texts:
            t_text = t.get("text") or ""  # FIX G2: None -> ""
            if exact_match:
                if t_text == text:
                    x = t.get("x", 0) + t.get("width", 0) // 2
                    y = t.get("y", 0) + t.get("height", 0) // 2
                    return await self.click(x, y)
            else:
                if text.lower() in t_text.lower():
                    x = t.get("x", 0) + t.get("width", 0) // 2
                    y = t.get("y", 0) + t.get("height", 0) // 2
                    return await self.click(x, y)
        
        boxes = self._last_state.get("boxes", [])
        for b in boxes:
            b_text = b.get("text") or ""  # FIX G2: None -> ""
            if exact_match:
                if b_text == text:
                    x = b.get("x", 0) + b.get("width", 0) // 2
                    y = b.get("y", 0) + b.get("height", 0) // 2
                    return await self.click(x, y)
            else:
                if b_text and text.lower() in b_text.lower():  # FIX G2: Check b_text exists
                    x = b.get("x", 0) + b.get("width", 0) // 2
                    y = b.get("y", 0) + b.get("height", 0) // 2
                    return await self.click(x, y)
        
        return f"ERROR: Could not find element with text '{text}'"
    
    async def type_text(self, text: str) -> str:
        """Tippt den angegebenen Text."""
        if self.interaction_agent:
            try:
                result = await self.interaction_agent.type_text(text)
                return f"Typed: '{text}'"
            except Exception as e:
                return f"ERROR typing '{text}': {e}"
        
        if self.moire_client and hasattr(self.moire_client, 'send_command'):
            try:
                await self.moire_client.send_command({"type": "type", "text": text})
                return f"Typed: '{text}'"
            except Exception as e:
                return f"ERROR typing: {e}"
        
        return "ERROR: No interaction agent available"
    
    async def press_key(self, key: str) -> str:
        """Drückt eine Taste."""
        if self.interaction_agent:
            try:
                result = await self.interaction_agent.press_key(key)
                return f"Pressed key: {key}"
            except Exception as e:
                return f"ERROR pressing key '{key}': {e}"
        
        if self.moire_client and hasattr(self.moire_client, 'send_command'):
            try:
                await self.moire_client.send_command({"type": "key_press", "key": key})
                return f"Pressed key: {key}"
            except Exception as e:
                return f"ERROR pressing key: {e}"
        
        return "ERROR: No interaction agent available"
    
    async def wait(self, seconds: float) -> str:
        """Wartet die angegebene Zeit."""
        await asyncio.sleep(seconds)
        return f"Waited {seconds} seconds"
    
    async def hotkey(self, *keys: str) -> str:
        """Drückt eine Tastenkombination."""
        if self.interaction_agent:
            try:
                result = await self.interaction_agent.hotkey(*keys)
                return f"Pressed hotkey: {'+'.join(keys)}"
            except Exception as e:
                return f"ERROR pressing hotkey {'+'.join(keys)}: {e}"
        
        if self.moire_client and hasattr(self.moire_client, 'send_command'):
            try:
                await self.moire_client.send_command({"type": "hotkey", "keys": list(keys)})
                return f"Pressed hotkey: {'+'.join(keys)}"
            except Exception as e:
                return f"ERROR pressing hotkey: {e}"
        
        return "ERROR: No interaction agent available for hotkey"
    
    async def scroll(self, direction: str = "down", amount: int = 3) -> str:
        """Scrollt in eine Richtung."""
        if self.interaction_agent:
            try:
                result = await self.interaction_agent.scroll(direction=direction, amount=amount)
                return f"Scrolled {direction} by {amount}"
            except Exception as e:
                return f"ERROR scrolling {direction}: {e}"
        
        if self.moire_client and hasattr(self.moire_client, 'send_command'):
            try:
                await self.moire_client.send_command({"type": "scroll", "direction": direction, "amount": amount})
                return f"Scrolled {direction} by {amount}"
            except Exception as e:
                return f"ERROR scrolling: {e}"
        
        return "ERROR: No interaction agent available for scroll"
    
    async def open_start_menu(self) -> str:
        """Öffnet das Windows Start-Menü."""
        if self.interaction_agent:
            try:
                if hasattr(self.interaction_agent, 'open_start_menu'):
                    result = await self.interaction_agent.open_start_menu()
                    return "Opened Start menu"
                else:
                    result = await self.interaction_agent.press_key('win')
                    return "Pressed Win key to open Start menu"
            except Exception as e:
                return f"ERROR opening Start menu: {e}"
        
        return await self.press_key('win')

    def get_last_screenshot(self) -> Optional[bytes]:
        return self._last_screenshot
    
    def get_last_state(self) -> Optional[Dict[str, Any]]:
        return self._last_state


# ==================== Agent System Prompts ====================

PLANNER_SYSTEM_PROMPT = """
You are a Planning Agent for desktop automation tasks.

Your role:
1. Analyze the user's goal and break it down into specific, actionable steps
2. Consider the current screen state when planning
3. Output a numbered list of steps to achieve the goal

AVAILABLE ACTIONS:
- click on "text" - Click on element containing text
- click at (x, y) - Click at specific coordinates
- type "text" - Type text into the focused field
- press KEY - Press a single key
- hotkey KEY1+KEY2 - Press key combination (e.g., ctrl+c, win+r, alt+tab)
- scroll DIRECTION AMOUNT - Scroll up/down/left/right (e.g., scroll down 5)
- wait SECONDS - Wait for specified time

AVAILABLE KEYS:
- Navigation: enter, tab, escape, backspace, delete, space
- Arrows: up, down, left, right
- System: win (Windows key), alt, ctrl, shift
- Function: f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12
- Special: home, end, pageup, pagedown, insert, printscreen

EXAMPLES:
- To open Start menu: "Press win key"
- To copy text: "Press ctrl+c hotkey"
- To switch windows: "Press alt+tab hotkey"
- To run dialog: "Press win+r hotkey"
- To scroll page: "Scroll down 5"
- To close window: "Press alt+f4 hotkey"

Format your response as:
PLAN:
1. [First step]
2. [Second step]
...

Each step should be concrete and actionable. Use the exact action format above.
"""


CRITIC_SYSTEM_PROMPT = """
You are a Critic Agent that reviews plans for desktop automation.

Your role:
1. Review the proposed plan for completeness and correctness
2. Identify potential issues or missing steps
3. Suggest improvements if needed

Format your response as:
REVIEW:
- Assessment: [APPROVED/NEEDS_REVISION]
- Issues: [List any issues found]
- Suggestions: [List any improvements]

If the plan is good, respond with "APPROVED" and the plan can proceed.
"""


VISION_SYSTEM_PROMPT = """
You are a Vision Agent that analyzes screenshots for UI elements.

Your role:
1. Analyze the current screen state
2. Identify relevant UI elements for the current task
3. Provide coordinates or descriptions of elements

When given a screenshot and a goal, identify:
- Buttons, text fields, menus that are relevant
- The current state of the application
- Any obstacles or errors visible
"""


GOAL_CHECKER_SYSTEM_PROMPT = """
You are a Goal Checker Agent that verifies if goals have been achieved.

Your role:
1. Compare the current screen state with the expected outcome
2. Determine if the goal has been achieved
3. Provide confidence level and reasoning

Format your response as:
GOAL_CHECK:
- Achieved: [YES/NO/PARTIAL]
- Confidence: [0-100]%
- Evidence: [What you observed]
- Next: [What should happen next, if not achieved]
"""


EXECUTOR_SYSTEM_PROMPT = """
You are an Executor Agent that performs desktop automation actions.

Available tools:
- capture_screenshot(): Take a screenshot
- get_screen_state(): Get current UI elements and text
- click(x, y): Click at coordinates
- click_by_text(text): Click on element containing text
- type_text(text): Type text
- press_key(key): Press a key (enter, tab, escape, etc.)
- wait(seconds): Wait for specified time

Execute one action at a time and wait for the result before proceeding.
Respond with DONE when the task is complete.
"""


# Key-Map für _execute_step
KEY_ALIASES = {
    'win': 'win', 'windows': 'win', 'start': 'win', 'winkey': 'win', 'super': 'win',
    'alt': 'alt', 'option': 'alt',
    'ctrl': 'ctrl', 'control': 'ctrl', 'strg': 'ctrl',
    'shift': 'shift',
    'enter': 'enter', 'return': 'enter', 'ret': 'enter',
    'tab': 'tab',
    'escape': 'escape', 'esc': 'escape',
    'backspace': 'backspace', 'back': 'backspace', 'bs': 'backspace',
    'delete': 'delete', 'del': 'delete',
    'space': 'space', 'spacebar': 'space',
    'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right',
    'home': 'home', 'end': 'end',
    'pageup': 'pageup', 'pagedown': 'pagedown',
    'f1': 'f1', 'f2': 'f2', 'f3': 'f3', 'f4': 'f4', 'f5': 'f5', 'f6': 'f6',
    'f7': 'f7', 'f8': 'f8', 'f9': 'f9', 'f10': 'f10', 'f11': 'f11', 'f12': 'f12',
}


# ==================== Dataclasses ====================

@dataclass
class TaskContext:
    """Kontext für eine laufende Task."""
    task_id: str
    goal: str
    plan: List[str] = field(default_factory=list)
    current_step: int = 0
    status: str = "pending"
    history: List[Dict[str, Any]] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    screenshots: List[bytes] = field(default_factory=list)


@dataclass
class ExecutionRecord:
    """Record für einen ausgeführten Schritt mit Verifikation."""
    step_index: int
    step_text: str
    action_type: str
    action_params: Dict[str, Any] = field(default_factory=dict)
    result: str = ""
    success: bool = False
    screen_before: str = ""
    screen_after: str = ""
    verification: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_summary(self) -> str:
        status = "✓" if self.success and self.verification.get("verified") else "✗"
        changes = self.verification.get("changes", "No changes detected")
        return f"{status} Step {self.step_index + 1}: {self.step_text} → {changes}"


# ==================== SocietyOfMindOrchestrator ====================

class SocietyOfMindOrchestrator:
    """Orchestriert ein Society of Mind Agent-Team für Desktop-Automation."""
    
    def __init__(
        self,
        moire_client: Optional[Any] = None,
        interaction_agent: Optional[Any] = None,
        openrouter_client: Optional[OpenRouterClient] = None,
        memory: Optional['AgentMemory'] = None,
        model: str = "anthropic/claude-sonnet-4"
    ):
        self.moire_client = moire_client
        self.interaction_agent = interaction_agent
        self.openrouter_client = openrouter_client or get_openrouter_client()
        self.memory = memory or (get_memory() if HAS_MEMORY else None)
        self.model = model
        
        self.tools = DesktopTools(
            moire_client=moire_client,
            interaction_agent=interaction_agent,
            memory=self.memory
        )
        
        self._model_client = None
        self._planner_agent = None
        self._current_task: Optional[TaskContext] = None
        
        logger.info(f"SocietyOfMindOrchestrator initialized with model: {model}")
    
    async def _init_agents(self) -> None:
        """Initialisiert die AutoGen Agents."""
        if not HAS_AUTOGEN_AGENTCHAT:
            raise ImportError("autogen-agentchat is required")
        
        if self._model_client is not None:
            return
        
        openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        if not openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        
        self._model_client = OpenAIChatCompletionClient(
            model=self.model,
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            model_info={"family": "claude", "vision": True, "function_calling": True, "json_output": True}
        )
        
        self._planner_agent = AssistantAgent(
            name="Planner",
            model_client=self._model_client,
            system_message=PLANNER_SYSTEM_PROMPT
        )
        
        logger.info("AutoGen agents initialized")
    
    async def _execute_step(self, step: str) -> str:
        """Führt einen einzelnen Schritt aus."""
        try:
            if step is None:
                return "ERROR: Step is None - invalid plan"
            
            step_lower = step.lower()
            
            # HOTKEY
            hotkey_patterns = [
                r'(?:press\s+)?(\w+)\+(\w+)(?:\+(\w+))?\s*(?:hotkey)?',
                r'hotkey\s+(\w+)\+(\w+)(?:\+(\w+))?'
            ]
            
            for pattern in hotkey_patterns:
                match = re.search(pattern, step_lower)
                if match:
                    keys = [k for k in match.groups() if k]
                    normalized_keys = [KEY_ALIASES.get(k.strip(), k.strip()) for k in keys]
                    if len(normalized_keys) >= 2:
                        return await self.tools.hotkey(*normalized_keys)
            
            # SCROLL
            scroll_match = re.search(r'scroll\s+(up|down|left|right)(?:\s+(\d+))?', step_lower)
            if scroll_match:
                direction = scroll_match.group(1)
                amount = int(scroll_match.group(2)) if scroll_match.group(2) else 3
                return await self.tools.scroll(direction, amount)
            
            # CLICK
            if "click" in step_lower:
                coord_match = re.search(r'\(?\s*(\d+)\s*,\s*(\d+)\s*\)?', step)
                if coord_match:
                    x, y = int(coord_match.group(1)), int(coord_match.group(2))
                    return await self.tools.click(x, y)
                
                if "on" in step_lower or "the" in step_lower:
                    parts = re.split(r'\bon\b|\bthe\b', step_lower, 1)
                    if len(parts) > 1:
                        target = parts[1].strip().strip('"\'')
                        target = re.sub(r'\b(button|link|icon|menu|element)\b', '', target).strip()
                        if target:
                            return await self.tools.click_by_text(target)
                
                quoted = re.findall(r'["\']([^"\']+)["\']', step)
                if quoted:
                    return await self.tools.click_by_text(quoted[0])
                
                return "Need specific target to click"
            
            # TYPE
            if any(kw in step_lower for kw in ["type", "enter text", "input", "write"]):
                quoted = re.findall(r'["\']([^"\']+)["\']', step)
                if quoted:
                    return await self.tools.type_text(quoted[0])
                
                type_match = re.search(r'type\s+(\S+)', step_lower)
                if type_match:
                    return await self.tools.type_text(type_match.group(1))
                
                return "Need text to type"
            
            # PRESS
            if "press" in step_lower:
                key_match = re.search(r'press\s+(?:the\s+)?(\w+)(?:\s+key)?', step_lower)
                if key_match:
                    key = key_match.group(1).strip()
                    normalized_key = KEY_ALIASES.get(key, key)
                    return await self.tools.press_key(normalized_key)
                return "Unknown key to press"
            
            # WAIT
            if "wait" in step_lower:
                numbers = re.findall(r'(\d+)', step)
                if numbers:
                    return await self.tools.wait(float(numbers[0]))
                return await self.tools.wait(1)
            
            # SCREENSHOT
            if "screenshot" in step_lower or "capture" in step_lower:
                return await self.tools.capture_screenshot()
            
            # START MENU
            if "start menu" in step_lower:
                return await self.tools.open_start_menu()
            
            # DEFAULT
            return await self.tools.click_by_text(step)
            
        except Exception as e:
            return f"ERROR executing step: {e}"
    
    def _detect_action_type(self, step: str) -> Tuple[str, Dict[str, Any]]:
        """Erkennt den Action-Typ und Parameter."""
        if step is None:
            return "unknown", {"raw": "None"}
        
        step_lower = step.lower()
        
        if re.search(r'\w+\+\w+', step_lower):
            keys = re.findall(r'(\w+)\+(\w+)', step_lower)
            if keys:
                return "hotkey", {"keys": list(keys[0])}
        
        if "scroll" in step_lower:
            match = re.search(r'scroll\s+(up|down|left|right)', step_lower)
            if match:
                return "scroll", {"direction": match.group(1)}
        
        if "click" in step_lower:
            quoted = re.findall(r'["\']([^"\']+)["\']', step)
            if quoted:
                return "click", {"target": quoted[0]}
            return "click", {"target": "unknown"}
        
        if any(kw in step_lower for kw in ["type", "enter text", "input", "write"]):
            quoted = re.findall(r'["\']([^"\']+)["\']', step)
            if quoted:
                return "type", {"text": quoted[0]}
            return "type", {"text": "unknown"}
        
        if "press" in step_lower:
            match = re.search(r'press\s+(?:the\s+)?(\w+)', step_lower)
            if match:
                return "press", {"key": match.group(1)}
            return "press", {"key": "unknown"}
        
        if "wait" in step_lower:
            numbers = re.findall(r'(\d+)', step)
            return "wait", {"seconds": numbers[0] if numbers else "1"}
        
        return "unknown", {"raw": step}
    
    async def _plan_task(self, goal: str, screen_state: str, error_context: Optional[str] = None) -> List[str]:
        """Plant die Task."""
        try:
            prompt = f"""Goal: {goal}

Current Screen State:
{screen_state}
"""
            if error_context:
                prompt += f"""

PREVIOUS ATTEMPT FAILED:
{error_context}

Please create a NEW plan that avoids the previous error.
"""
            
            prompt += """
Create a step-by-step plan to achieve this goal.
Format as numbered steps. Be specific about what to click, type, etc.
"""
            
            response = await self.openrouter_client.chat(
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model=self.model
            )
            
            if response and response.content:
                content = response.content
                steps = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line and len(line) > 2:
                        # Check if line starts with a number (e.g., "1.", "2)", "10.")
                        if line[0].isdigit():
                            # Handle "1.", "1)", "1:" formats
                            if len(line) > 1 and line[1] in '.)::':
                                step = line[2:].strip()
                                if step:
                                    steps.append(step)
                            # Handle "10.", "11)" etc
                            elif len(line) > 2 and line[1].isdigit() and line[2] in '.)::':
                                step = line[3:].strip()
                                if step:
                                    steps.append(step)
                return steps if steps else [goal]
            
            return [goal]
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return []
    
    async def _validate_step(self, step: str, action_result: str, screen_before: str, screen_after: str) -> Dict[str, Any]:
        """Validiert ob ein Schritt erfolgreich war."""
        try:
            prompt = f"""Analyze if this desktop automation step was successful:

STEP: {step}
ACTION RESULT: {action_result}

SCREEN BEFORE:
{screen_before[:800]}

SCREEN AFTER:
{screen_after[:800]}

Respond in this exact format:
VERIFIED: [YES/NO]
CHANGES: [Brief description of what changed]
EVIDENCE: [What you observed]
CONFIDENCE: [0-140]"""

            response = await self.openrouter_client.chat(
                messages=[
                    {"role": "system", "content": "You are a verification agent."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model
            )
            
            if response and response.content:
                content = response.content.upper()
                verified = "VERIFIED: YES" in content
                
                changes_match = re.search(r'CHANGES:\s*(.+?)(?:\n|EVIDENCE:|$)', content, re.IGNORECASE | re.DOTALL)
                changes = changes_match.group(1).strip() if changes_match else "Unknown"
                
                evidence_match = re.search(r'EVIDENCE:\s*(.+?)(?:\n|CONFIDENCE:|$)', content, re.IGNORECASE | re.DOTALL)
                evidence = evidence_match.group(1).strip() if evidence_match else ""
                
                confidence_match = re.search(r'CONFIDENCE:\s*(\d+)', content)
                confidence = int(confidence_match.group(1)) if confidence_match else (80 if verified else 30)
                
                return {"verified": verified, "changes": changes, "evidence": evidence, "confidence": confidence}
            
            is_error = any(err in action_result.lower() for err in ['error', 'could not', 'failed'])
            return {"verified": not is_error, "changes": "Could not analyze", "evidence": action_result, "confidence": 50}
            
        except Exception as e:
            logger.warning(f"Step validation failed: {e}")
            return {"verified": False, "changes": f"Validation error: {e}", "evidence": "", "confidence": 0}
    
    def _get_execution_summary(self, records: List[ExecutionRecord], goal: str) -> str:
        """Erstellt eine Zusammenfassung der Ausführung."""
        if not records:
            return "No steps executed yet."
        
        summary = f"EXECUTION HISTORY for goal: {goal}\n{'=' * 50}\n\n"
        
        successful = [r for r in records if r.success and r.verification.get("verified")]
        failed = [r for r in records if not r.success or not r.verification.get("verified")]
        
        if successful:
            summary += "✓ COMPLETED STEPS (verified):\n"
            for r in successful:
                summary += f"  {r.to_summary()}\n"
            summary += "\n"
        
        if failed:
            summary += "✗ FAILED/UNVERIFIED STEPS:\n"
            for r in failed:
                summary += f"  {r.to_summary()}\n"
            summary += "\n"
        
        if records:
            summary += f"CURRENT SCREEN STATE:\n{records[-1].screen_after[:400]}\n"
        
        return summary
    
    async def _check_goal(self, goal: str, screen_state: str, execution_records: Optional[List[ExecutionRecord]] = None) -> Dict[str, Any]:
        """Prüft ob das Ziel erreicht wurde.
        
        FIX G3: Berücksichtigt jetzt auch die Execution History als Evidenz.
        """
        try:
            # Build execution summary if records provided
            execution_summary = ""
            if execution_records:
                successful_steps = [r for r in execution_records if r.success and r.verification.get("verified")]
                execution_summary = f"\n\nEXECUTION HISTORY ({len(successful_steps)}/{len(execution_records)} steps verified successful):\n"
                for r in execution_records[-5:]:  # Last 5 steps
                    status = "✓" if r.success else "✗"
                    execution_summary += f"  {status} {r.step_text} → {r.result[:50]}\n"
            
            prompt = f"""Goal: {goal}

Current Screen State:
{screen_state}
{execution_summary}
IMPORTANT: If the execution history shows all steps completed successfully (especially if the final step was pressing enter/send), 
the goal is likely achieved even if the screen doesn't show obvious confirmation.

Has the goal been achieved? Respond with:
- achieved: true/false
- confidence: 0-100
- reason: explanation"""

            response = await self.openrouter_client.chat(
                messages=[
                    {"role": "system", "content": GOAL_CHECKER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model=self.model
            )
            
            if response and response.content:
                content = response.content.lower()
                achieved = "achieved: true" in content or "yes" in content[:50]
                
                # FIX G3: If all steps succeeded and verified, boost confidence
                if execution_records:
                    all_verified = all(r.success and r.verification.get("verified") for r in execution_records)
                    if all_verified and not achieved:
                        # Check if last step was a "send" action (enter, click send button)
                        last_step = execution_records[-1].step_text.lower() if execution_records else ""
                        if any(kw in last_step for kw in ["enter", "send", "submit", "confirm"]):
                            achieved = True
                            logger.info("G3 FIX: All steps verified + final send action → marking as achieved")
                
                confidence_match = re.search(r'confidence[:\s]+(\d+)', content)
                confidence = int(confidence_match.group(1)) if confidence_match else (80 if achieved else 20)
                return {"achieved": achieved, "confidence": confidence, "reason": content[:200]}
            
            return {"achieved": False, "confidence": 0, "reason": "Could not check goal"}
            
        except Exception as e:
            logger.error(f"Goal check failed: {e}")
            return {"achieved": False, "confidence": 0, "reason": str(e)}
    
    async def execute_task(self, goal: str, max_rounds: int = 20) -> Dict[str, Any]:
        """Führt eine Task mit Validation Chain aus."""
        await self._init_agents()
        
        task_id = str(uuid.uuid4())[:8]
        self._current_task = TaskContext(task_id=task_id, goal=goal, status="running")
        execution_records: List[ExecutionRecord] = []
        replan_count = 0
        max_replans = 4
        
        logger.info(f"Starting task {task_id}: {goal}")
        
        try:
            screen_state = await self.tools.get_screen_state()
            logger.info(f"Initial screen state: {screen_state[:200]}...")
            
            plan = await self._plan_task(goal, screen_state, error_context=None)
            if not plan:
                return {"success": False, "error": "Planning failed", "rounds": [], "execution_records": []}
            
            plan = [s for s in plan if s is not None and s.strip()]
            self._current_task.plan = plan
            logger.info(f"Plan created with {len(plan)} steps: {plan}")
            
            step_index = 0
            iteration = 0
            
            while iteration < max_rounds:
                iteration += 1
                logger.info(f"Iteration {iteration}/{max_rounds}")
                
                # Check if all steps executed
                if step_index >= len(plan):
                    logger.info("All steps executed, checking goal...")
                    screen_state = await self.tools.get_screen_state()
                    goal_check = await self._check_goal(goal, screen_state, execution_records)
                    
                    if goal_check.get("achieved"):
                        logger.info(f"Goal achieved with confidence {goal_check.get('confidence', 0)}%")
                        self._current_task.status = "completed"
                        return {
                            "success": True,
                            "task_id": task_id,
                            "goal": goal,
                            "steps_executed": len(execution_records),
                            "rounds": [r.to_summary() for r in execution_records],  # FIX G1: Add rounds key
                            "execution_records": [r.to_summary() for r in execution_records],
                            "history": self._current_task.history,
                            "goal_check": goal_check,
                            "replans": replan_count
                        }
                    
                    if replan_count < max_replans:
                        logger.warning("Goal not achieved, attempting re-plan...")
                        execution_summary = self._get_execution_summary(execution_records, goal)
                        error_context = f"{execution_summary}\n\nPROBLEM: All steps executed but goal not achieved."
                        new_plan = await self._plan_task(goal, screen_state, error_context)
                        if new_plan:
                            plan = [s for s in new_plan if s is not None and s.strip()]
                            self._current_task.plan = plan
                            step_index = 0
                            replan_count += 1
                            continue
                    
                    # Max replans reached
                    logger.warning("Max replans reached, task incomplete")
                    self._current_task.status = "incomplete"
                    return {
                        "success": False,
                        "task_id": task_id,
                        "goal": goal,
                        "steps_executed": len(execution_records),
                        "rounds": [r.to_summary() for r in execution_records],  # FIX G1: Add rounds key
                        "execution_records": [r.to_summary() for r in execution_records],
                        "history": self._current_task.history,
                        "error": "Max replans reached without achieving goal",
                        "replans": replan_count
                    }
                
                # EXECUTE CURRENT STEP
                current_step = plan[step_index]
                logger.info(f"Step {step_index + 1}/{len(plan)}: {current_step}")
                self._current_task.current_step = step_index
                
                # Screenshot before
                screen_before = await self.tools.get_screen_state()
                
                # Detect action type
                action_type, action_params = self._detect_action_type(current_step)
                
                # Execute the step
                result = await self._execute_step(current_step)
                logger.info(f"Step result: {result}")
                
                # Wait briefly for UI to update
                await asyncio.sleep(0.5)
                
                # Screenshot after
                screen_after = await self.tools.get_screen_state()
                
                # Validate step
                verification = await self._validate_step(current_step, result, screen_before, screen_after)
                
                # Create execution record
                record = ExecutionRecord(
                    step_index=step_index,
                    step_text=current_step,
                    action_type=action_type,
                    action_params=action_params,
                    result=result,
                    success="error" not in result.lower(),
                    screen_before=screen_before[:500],
                    screen_after=screen_after[:500],
                    verification=verification
                )
                execution_records.append(record)
                
                # Add to task history
                self._current_task.history.append({
                    "step": step_index + 1,
                    "action": current_step,
                    "result": result,
                    "verified": verification.get("verified", False)
                })
                
                # Check if step failed
                if "error" in result.lower() and not verification.get("verified", False):
                    logger.warning(f"Step failed: {result}")
                    
                    # Try re-planning after failed step
                    if replan_count < max_replans:
                        logger.warning("Step failed, attempting re-plan...")
                        execution_summary = self._get_execution_summary(execution_records, goal)
                        error_context = f"{execution_summary}\n\nFAILED STEP: {current_step}\nERROR: {result}"
                        new_plan = await self._plan_task(goal, screen_after, error_context)
                        if new_plan:
                            plan = [s for s in new_plan if s is not None and s.strip()]
                            self._current_task.plan = plan
                            step_index = 0
                            replan_count += 1
                            continue
                
                # Move to next step
                step_index += 1
            
            # Max iterations reached
            logger.warning("Max iterations reached")
            self._current_task.status = "incomplete"
            return {
                "success": False,
                "task_id": task_id,
                "goal": goal,
                "steps_executed": len(execution_records),
                "rounds": [r.to_summary() for r in execution_records],  # FIX G1: Add rounds key
                "execution_records": [r.to_summary() for r in execution_records],
                "history": self._current_task.history,
                "error": "Max iterations reached",
                "replans": replan_count
            }
                
        except Exception as e:
            logger.error(f"Task failed: {e}")
            import traceback
            traceback.print_exc()
            self._current_task.status = "failed"
            return {
                "success": False,
                "task_id": task_id,
                "goal": goal,
                "error": str(e),
                "rounds": [r.to_summary() for r in execution_records] if execution_records else [],  # FIX G1: Add rounds key
                "execution_records": [r.to_summary() for r in execution_records] if execution_records else [],
                "history": self._current_task.history
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt den aktuellen Status zurück."""
        status = {
            "status": "idle",
            "model": self.model,
            "has_moire_client": self.moire_client is not None,
            "has_interaction_agent": self.interaction_agent is not None,
            "has_memory": self.memory is not None
        }
        
        if self._current_task:
            status.update({
                "status": self._current_task.status,
                "task_id": self._current_task.task_id,
                "goal": self._current_task.goal,
                "current_step": self._current_task.current_step,
                "total_steps": len(self._current_task.plan),
                "history_count": len(self._current_task.history)
            })
        
        return status


# ==================== Factory Functions ====================

async def create_society_orchestrator(
    moire_client: Optional[Any] = None,
    interaction_agent: Optional[Any] = None,
    model: str = "anthropic/claude-sonnet-4"
) -> SocietyOfMindOrchestrator:
    """Factory function für SocietyOfMindOrchestrator."""
    return SocietyOfMindOrchestrator(
        moire_client=moire_client,
        interaction_agent=interaction_agent,
        model=model
    )


_society_orchestrator_instance: Optional[SocietyOfMindOrchestrator] = None

def get_society_orchestrator(
    moire_client: Optional[Any] = None,
    interaction_agent: Optional[Any] = None,
    model_name: str = "anthropic/claude-sonnet-4"
) -> SocietyOfMindOrchestrator:
    """Singleton Factory für SocietyOfMindOrchestrator."""
    global _society_orchestrator_instance
    
    if _society_orchestrator_instance is None:
        _society_orchestrator_instance = SocietyOfMindOrchestrator(
            moire_client=moire_client,
            interaction_agent=interaction_agent,
            model=model_name
        )
        logger.info(f"SocietyOfMindOrchestrator Singleton erstellt mit Model: {model_name}")
    else:
        if moire_client is not None:
            _society_orchestrator_instance.moire_client = moire_client
            _society_orchestrator_instance.tools.moire_client = moire_client
        if interaction_agent is not None:
            _society_orchestrator_instance.interaction_agent = interaction_agent
            _society_orchestrator_instance.tools.interaction_agent = interaction_agent
    
    return _society_orchestrator_instance


def shutdown_society_orchestrator():
    """Fährt den Singleton Orchestrator herunter."""
    global _society_orchestrator_instance
    _society_orchestrator_instance = None
    logger.info("SocietyOfMindOrchestrator Singleton heruntergefahren")


# ==================== Main ====================

async def main():
    """Test der SocietyOfMindOrchestrator."""
    logging.basicConfig(level=logging.INFO)
    
    print("Testing SocietyOfMindOrchestrator...")
    orchestrator = await create_society_orchestrator()
    print("Orchestrator created successfully!")
    print(f"Status: {orchestrator.get_status()}")


if __name__ == "__main__":
    asyncio.run(main())