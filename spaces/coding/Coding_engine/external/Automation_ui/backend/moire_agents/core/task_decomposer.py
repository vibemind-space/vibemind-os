"""
Task Decomposer - Breaks complex goals into actionable subtasks.

Uses LLM to analyze natural language goals and decompose them into:
- Sequential subtasks with clear descriptions
- Dependency relationships between subtasks
- Recommended approach for each subtask (keyboard, mouse, vision, etc.)
- Parallelization opportunities
- Executable PyAutoGUI actions (when using decompose_with_actions)

Example:
    decomposer = TaskDecomposer(openrouter_client)
    subtasks = await decomposer.decompose(
        goal="Open Chrome, search for news, summarize headlines",
        context={"os": "Windows"}
    )

    # Or with executable actions:
    subtasks = await decomposer.decompose_with_actions(
        goal="Open Notepad and type Hello World"
    )
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Enhanced prompt for generating PyAutoGUI actions
DECOMPOSE_WITH_ACTIONS_PROMPT = '''You are a Windows desktop automation expert. Decompose this task into PyAutoGUI actions.

Task: {goal}
OS: Windows 11

For EACH step, provide a JSON object with:
1. description: What this step does (human readable)
2. approach: keyboard | mouse | hybrid | vision
3. pyautogui_action: The exact PyAutoGUI command to execute
   - {{"type": "hotkey", "keys": ["win", "r"]}} → pyautogui.hotkey("win", "r")
   - {{"type": "write", "text": "notepad", "interval": 0.05}} → pyautogui.write()
   - {{"type": "press", "key": "enter"}} → pyautogui.press("enter")
   - {{"type": "click", "x": 100, "y": 200}} → pyautogui.click(100, 200)
   - {{"type": "find_and_click", "target": "Button text or element description"}} → Find element on screen and click it
   - {{"type": "sleep", "seconds": 2}} → asyncio.sleep(2)
   - {{"type": "select_text", "chars": 15, "direction": "left"}} → Shift+arrow selection
4. wait_after: Seconds to wait after this action (0.1-5.0)
5. dependencies: Indices of steps this depends on (0-indexed)

IMPORTANT RULES:
- Use keyboard shortcuts when possible (faster, more reliable)
- Always wait after opening apps (2-5 seconds)
- For text selection, use Shift+arrows or Ctrl+A
- For formatting: Ctrl+B (bold), Ctrl+I (italic), Ctrl+U (underline), Ctrl+E (center)
- To open apps: Win+R then type app name, OR Win key then type to search
- Use find_and_click when you need to click on a specific UI element by name (contacts, buttons, menu items)
- Return ONLY a valid JSON array, no explanations or markdown

Example for "Open Notepad and type Hello":
[
  {{"description": "Open Run dialog", "approach": "keyboard", "pyautogui_action": {{"type": "hotkey", "keys": ["win", "r"]}}, "wait_after": 0.5, "dependencies": []}},
  {{"description": "Type notepad", "approach": "keyboard", "pyautogui_action": {{"type": "write", "text": "notepad", "interval": 0.05}}, "wait_after": 0.2, "dependencies": [0]}},
  {{"description": "Press Enter to launch", "approach": "keyboard", "pyautogui_action": {{"type": "press", "key": "enter"}}, "wait_after": 2.0, "dependencies": [1]}},
  {{"description": "Type Hello", "approach": "keyboard", "pyautogui_action": {{"type": "write", "text": "Hello", "interval": 0.03}}, "wait_after": 0.2, "dependencies": [2]}}
]
'''


class SubtaskApproach(Enum):
    """Recommended approach for executing a subtask."""
    KEYBOARD = "keyboard"  # Keyboard shortcuts and typing
    MOUSE = "mouse"  # Mouse clicks and movements
    HYBRID = "hybrid"  # Combination of keyboard and mouse
    VISION = "vision"  # Screen analysis and element detection
    SPECIALIST = "specialist"  # Domain specialist query
    ORCHESTRATOR = "orchestrator"  # Full orchestrator with reflection


@dataclass
class Subtask:
    """A single subtask decomposed from a complex goal."""
    id: str
    description: str
    approach: str
    dependencies: List[str] = field(default_factory=list)
    can_parallel: bool = False
    timeout: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)
    order: int = 0

    @classmethod
    def create(
        cls,
        description: str,
        approach: str = "orchestrator",
        dependencies: List[str] = None,
        can_parallel: bool = False,
        timeout: float = None,
        context: Dict = None,
        order: int = 0
    ) -> "Subtask":
        """Create a new subtask with auto-generated ID."""
        return cls(
            id=str(uuid4()),
            description=description,
            approach=approach,
            dependencies=dependencies or [],
            can_parallel=can_parallel,
            timeout=timeout,
            context=context or {},
            order=order
        )


class TaskDecomposer:
    """
    Decomposes complex natural language goals into subtasks.

    Uses an LLM to:
    1. Understand the user's goal
    2. Break it into sequential steps
    3. Identify dependencies between steps
    4. Recommend execution approach for each step
    5. Identify parallelization opportunities
    """

    def __init__(self, openrouter_client=None):
        """
        Initialize the decomposer.

        Args:
            openrouter_client: OpenRouter client for LLM calls
        """
        self.llm_client = openrouter_client

        # Pattern-based decomposition for common tasks
        self.patterns = self._build_patterns()

    def _build_patterns(self) -> Dict[str, List[Dict]]:
        """Build pattern library for common task types."""
        return {
            # App launching patterns
            "open_app": [
                {"description": "Open Run dialog", "approach": "keyboard", "action": "win+r"},
                {"description": "Type application name", "approach": "keyboard"},
                {"description": "Press Enter to launch", "approach": "keyboard"},
                {"description": "Wait for application window", "approach": "vision"}
            ],
            # Search patterns
            "web_search": [
                {"description": "Focus browser address bar", "approach": "keyboard", "action": "ctrl+l"},
                {"description": "Type search query", "approach": "keyboard"},
                {"description": "Press Enter to search", "approach": "keyboard"},
                {"description": "Wait for results", "approach": "vision"}
            ],
            # Document editing patterns
            "create_document": [
                {"description": "Open application", "approach": "hybrid"},
                {"description": "Create new document", "approach": "keyboard", "action": "ctrl+n"},
                {"description": "Enter content", "approach": "keyboard"},
                {"description": "Save document", "approach": "keyboard", "action": "ctrl+s"}
            ],
            # File operations
            "save_file": [
                {"description": "Open save dialog", "approach": "keyboard", "action": "ctrl+s"},
                {"description": "Enter filename", "approach": "keyboard"},
                {"description": "Confirm save", "approach": "keyboard"}
            ]
        }

    async def decompose(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Subtask]:
        """
        Decompose a complex goal into subtasks.

        Args:
            goal: Natural language description of the task
            context: Optional context (OS, current app, screen state)

        Returns:
            List of Subtask objects in execution order
        """
        context = context or {}

        # Try pattern-based decomposition first (faster)
        pattern_subtasks = self._try_pattern_match(goal, context)
        if pattern_subtasks:
            logger.info(f"Decomposed '{goal}' using pattern matching")
            return pattern_subtasks

        # Fall back to LLM-based decomposition
        if self.llm_client:
            return await self._llm_decompose(goal, context)

        # Final fallback: simple heuristic decomposition
        return self._heuristic_decompose(goal, context)

    def _try_pattern_match(
        self,
        goal: str,
        context: Dict[str, Any]
    ) -> Optional[List[Subtask]]:
        """Try to match goal against known patterns."""
        goal_lower = goal.lower()

        # Check for app launching
        app_match = re.search(
            r'(?:open|start|launch|run)\s+(\w+)',
            goal_lower
        )
        if app_match:
            app_name = app_match.group(1)
            return self._create_app_launch_subtasks(app_name, context)

        # Check for web search
        search_match = re.search(
            r'(?:search|google|look up|find)\s+(?:for\s+)?(.+?)(?:\s+(?:and|then)|$)',
            goal_lower
        )
        if search_match:
            query = search_match.group(1).strip()
            return self._create_search_subtasks(query, context)

        # Check for document creation
        doc_match = re.search(
            r'(?:create|make|write)\s+(?:a\s+)?(?:new\s+)?(\w+)\s+(?:document|file)',
            goal_lower
        )
        if doc_match:
            doc_type = doc_match.group(1)
            return self._create_document_subtasks(doc_type, goal, context)

        return None

    def _create_app_launch_subtasks(
        self,
        app_name: str,
        context: Dict
    ) -> List[Subtask]:
        """Create subtasks for launching an application."""
        subtasks = []

        # Subtask 1: Open Run dialog
        subtasks.append(Subtask.create(
            description=f"Open Run dialog (Win+R)",
            approach="keyboard",
            context={"keys": ["win", "r"]},
            order=1
        ))

        # Subtask 2: Type app name
        subtasks.append(Subtask.create(
            description=f"Type '{app_name}'",
            approach="keyboard",
            dependencies=[subtasks[0].id],
            context={"text": app_name},
            order=2
        ))

        # Subtask 3: Press Enter
        subtasks.append(Subtask.create(
            description="Press Enter to launch",
            approach="keyboard",
            dependencies=[subtasks[1].id],
            context={"keys": ["enter"]},
            order=3
        ))

        # Subtask 4: Verify launch
        subtasks.append(Subtask.create(
            description=f"Verify {app_name} window opened",
            approach="vision",
            dependencies=[subtasks[2].id],
            context={"target": app_name},
            order=4
        ))

        return subtasks

    def _create_search_subtasks(
        self,
        query: str,
        context: Dict
    ) -> List[Subtask]:
        """Create subtasks for web search."""
        subtasks = []

        # Check if browser is already open
        browser_open = context.get("active_app", "").lower() in [
            "chrome", "firefox", "edge", "browser"
        ]

        if not browser_open:
            # Need to open browser first
            subtasks.append(Subtask.create(
                description="Open browser",
                approach="hybrid",
                order=1
            ))
            deps = [subtasks[0].id]
        else:
            deps = []

        # Focus address bar
        subtasks.append(Subtask.create(
            description="Focus address bar (Ctrl+L)",
            approach="keyboard",
            dependencies=deps,
            context={"keys": ["ctrl", "l"]},
            order=len(subtasks) + 1
        ))

        # Type search query
        subtasks.append(Subtask.create(
            description=f"Type search query: {query}",
            approach="keyboard",
            dependencies=[subtasks[-1].id],
            context={"text": f"https://www.google.com/search?q={query}"},
            order=len(subtasks) + 1
        ))

        # Execute search
        subtasks.append(Subtask.create(
            description="Press Enter to search",
            approach="keyboard",
            dependencies=[subtasks[-1].id],
            context={"keys": ["enter"]},
            order=len(subtasks) + 1
        ))

        # Analyze results
        subtasks.append(Subtask.create(
            description="Analyze search results",
            approach="vision",
            dependencies=[subtasks[-1].id],
            context={"analysis_type": "search_results"},
            order=len(subtasks) + 1
        ))

        return subtasks

    def _create_document_subtasks(
        self,
        doc_type: str,
        full_goal: str,
        context: Dict
    ) -> List[Subtask]:
        """Create subtasks for document creation."""
        subtasks = []

        # Determine application
        app_map = {
            "word": "winword",
            "excel": "excel",
            "powerpoint": "powerpnt",
            "text": "notepad",
            "note": "notepad"
        }
        app = app_map.get(doc_type.lower(), "notepad")

        # Open application
        subtasks.append(Subtask.create(
            description=f"Open {doc_type} application",
            approach="hybrid",
            context={"app": app},
            order=1
        ))

        # Create new document
        subtasks.append(Subtask.create(
            description="Create new document (Ctrl+N)",
            approach="keyboard",
            dependencies=[subtasks[0].id],
            context={"keys": ["ctrl", "n"]},
            order=2
        ))

        # Extract content from goal if specified
        content_match = re.search(
            r'(?:write|type|add|with)\s+["\']?(.+?)["\']?\s*$',
            full_goal,
            re.IGNORECASE
        )

        if content_match:
            content = content_match.group(1)
            subtasks.append(Subtask.create(
                description=f"Type content: {content[:50]}...",
                approach="keyboard",
                dependencies=[subtasks[-1].id],
                context={"text": content},
                order=3
            ))

        return subtasks

    async def _llm_decompose(
        self,
        goal: str,
        context: Dict[str, Any]
    ) -> List[Subtask]:
        """Use LLM to decompose the goal."""
        prompt = f"""Decompose this automation task into sequential subtasks:

Task: {goal}

Context:
- Operating System: {context.get('os', 'Windows')}
- Current Application: {context.get('active_app', 'Desktop')}
- Additional Context: {json.dumps(context)}

For each subtask, provide:
1. description: Clear action description
2. approach: One of [keyboard, mouse, hybrid, vision, specialist, orchestrator]
3. dependencies: List of subtask indices this depends on (0-indexed)
4. can_parallel: true if can run with other subtasks in same dependency group
5. timeout: Estimated seconds needed (optional)

Approaches:
- keyboard: Use keyboard shortcuts and typing
- mouse: Use mouse clicks
- hybrid: Combination of keyboard and mouse (for complex UI)
- vision: Screen analysis needed (verify element, read content)
- specialist: Query domain knowledge (shortcuts, workflows)
- orchestrator: Full AI orchestrator with reflection loop

Return JSON array:
[
  {{"description": "...", "approach": "keyboard", "dependencies": [], "can_parallel": false}},
  ...
]
"""

        try:
            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="anthropic/claude-sonnet-4-20250514",
                temperature=0.3,
                max_tokens=2000
            )

            # Parse JSON from response
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Extract JSON array from response
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                subtask_data = json.loads(json_match.group())
                return self._parse_llm_subtasks(subtask_data)

        except Exception as e:
            logger.error(f"LLM decomposition failed: {e}")

        # Fall back to heuristic
        return self._heuristic_decompose(goal, context)

    def _parse_llm_subtasks(self, subtask_data: List[Dict]) -> List[Subtask]:
        """Parse LLM-generated subtask data into Subtask objects."""
        subtasks = []
        id_map = {}  # Map indices to UUIDs

        for i, data in enumerate(subtask_data):
            subtask_id = str(uuid4())
            id_map[i] = subtask_id

            # Convert dependency indices to UUIDs
            deps = []
            for dep_idx in data.get("dependencies", []):
                if dep_idx in id_map:
                    deps.append(id_map[dep_idx])

            subtasks.append(Subtask(
                id=subtask_id,
                description=data.get("description", f"Subtask {i+1}"),
                approach=data.get("approach", "orchestrator"),
                dependencies=deps,
                can_parallel=data.get("can_parallel", False),
                timeout=data.get("timeout"),
                context=data.get("context", {}),
                order=i + 1
            ))

        return subtasks

    def _heuristic_decompose(
        self,
        goal: str,
        context: Dict[str, Any]
    ) -> List[Subtask]:
        """Simple heuristic decomposition for fallback."""
        subtasks = []

        # Split by common conjunctions
        parts = re.split(r'\s+(?:and|then|,)\s+', goal.lower())

        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            # Determine approach based on keywords
            approach = "orchestrator"
            if any(k in part for k in ["click", "drag", "scroll"]):
                approach = "mouse"
            elif any(k in part for k in ["type", "press", "shortcut", "ctrl", "alt"]):
                approach = "keyboard"
            elif any(k in part for k in ["check", "verify", "read", "analyze", "see"]):
                approach = "vision"
            elif any(k in part for k in ["how to", "what is", "shortcut for"]):
                approach = "specialist"

            deps = [subtasks[-1].id] if subtasks else []

            subtasks.append(Subtask.create(
                description=part.capitalize(),
                approach=approach,
                dependencies=deps,
                order=i + 1
            ))

        # If no subtasks found, create single orchestrator task
        if not subtasks:
            subtasks.append(Subtask.create(
                description=goal,
                approach="orchestrator",
                order=1
            ))

        return subtasks

    async def decompose_with_actions(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Subtask]:
        """
        Decompose a goal into subtasks WITH executable PyAutoGUI actions.

        This method uses Claude API to generate a detailed execution plan
        with specific PyAutoGUI commands for each step.

        Args:
            goal: Natural language description of the task
            context: Optional context (OS, current app, screen state)

        Returns:
            List of Subtask objects with pyautogui_action in context
        """
        context = context or {}

        # Try Claude API first
        try:
            return await self._llm_decompose_with_actions(goal, context)
        except Exception as e:
            logger.error(f"LLM decomposition with actions failed: {e}")
            # Fall back to pattern-based (without actions)
            return await self.decompose(goal, context)

    async def _llm_decompose_with_actions(
        self,
        goal: str,
        context: Dict[str, Any]
    ) -> List[Subtask]:
        """Use Claude API to decompose goal with PyAutoGUI actions."""
        prompt = DECOMPOSE_WITH_ACTIONS_PROMPT.format(goal=goal)

        # Call Claude API
        response_text = await self._call_claude_api(prompt)

        # Parse JSON from response
        subtasks = self._parse_subtasks_with_actions(response_text)

        if subtasks:
            logger.info(f"Decomposed '{goal}' into {len(subtasks)} steps with actions")
            return subtasks

        # If parsing failed, fall back to regular decomposition
        logger.warning("Failed to parse LLM response, falling back to heuristic")
        return self._heuristic_decompose(goal, context)

    async def _call_claude_api(self, prompt: str) -> str:
        """Call Claude API using Anthropic SDK."""
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        # Get API key from environment
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            # Try loading from .env file
            env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    for line in f:
                        if line.startswith("ANTHROPIC_API_KEY="):
                            api_key = line.split("=", 1)[1].strip()
                            break

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment or .env file")

        client = anthropic.Anthropic(api_key=api_key)

        logger.info("Calling Claude API for task decomposition...")

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text
        logger.debug(f"Claude response: {response_text[:500]}...")

        return response_text

    def _parse_subtasks_with_actions(self, response_text: str) -> List[Subtask]:
        """Parse LLM response into Subtask objects with PyAutoGUI actions."""
        subtasks = []

        try:
            # Try to extract JSON array from response
            # Handle potential markdown code blocks
            json_text = response_text.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            # Find JSON array
            json_match = re.search(r'\[[\s\S]*\]', json_text)
            if json_match:
                json_text = json_match.group()

            subtask_data = json.loads(json_text)

            if not isinstance(subtask_data, list):
                logger.error("LLM response is not a JSON array")
                return []

            id_map = {}  # Map indices to UUIDs

            for i, data in enumerate(subtask_data):
                subtask_id = str(uuid4())
                id_map[i] = subtask_id

                # Convert dependency indices to UUIDs
                deps = []
                for dep_idx in data.get("dependencies", []):
                    if isinstance(dep_idx, int) and dep_idx in id_map:
                        deps.append(id_map[dep_idx])

                # Build context with pyautogui_action and wait_after
                subtask_context = {
                    "pyautogui_action": data.get("pyautogui_action"),
                    "wait_after": data.get("wait_after", 0.2)
                }

                subtasks.append(Subtask(
                    id=subtask_id,
                    description=data.get("description", f"Step {i+1}"),
                    approach=data.get("approach", "keyboard"),
                    dependencies=deps,
                    can_parallel=data.get("can_parallel", False),
                    timeout=data.get("timeout"),
                    context=subtask_context,
                    order=i + 1
                ))

            return subtasks

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.debug(f"Response was: {response_text[:500]}...")
            return []
        except Exception as e:
            logger.error(f"Error parsing subtasks: {e}")
            return []
