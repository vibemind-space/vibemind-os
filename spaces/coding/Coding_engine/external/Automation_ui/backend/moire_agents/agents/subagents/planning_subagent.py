"""
Planning Subagent - Generates action plans using different approaches.

Each PlanningSubagent instance specializes in ONE approach:
- KEYBOARD: Prefers keyboard shortcuts and typing
- MOUSE: Prefers clicking and visual navigation
- HYBRID: Combines both based on efficiency

Multiple instances run in parallel, each exploring their approach.
The best plan (highest confidence) is selected by the aggregator.

Example:
    Goal: "Open Microsoft Word"

    KEYBOARD approach:
    1. Press Windows key
    2. Type "Word"
    3. Press Enter

    MOUSE approach:
    1. Click Start button
    2. Scroll to find Word
    3. Click on Word icon

    HYBRID approach:
    1. Press Windows key
    2. Type "Word"
    3. Click on search result
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .base_subagent import BaseSubagent, SubagentContext, SubagentOutput

logger = logging.getLogger(__name__)


class PlanningApproach(Enum):
    """Planning approaches."""
    KEYBOARD = "keyboard"  # Prefer hotkeys and typing
    MOUSE = "mouse"       # Prefer clicking
    HYBRID = "hybrid"     # Best of both


@dataclass
class PlannedAction:
    """A single planned action."""
    action: str          # click, type, press_key, scroll, wait, drag
    params: Dict[str, Any]
    description: str
    confidence: float = 1.0
    can_parallel: bool = False
    depends_on: Optional[str] = None


# Approach-specific prompts for LLM planning
APPROACH_PROMPTS = {
    PlanningApproach.KEYBOARD: """You are a keyboard-focused automation planner.

RULES:
1. ALWAYS prefer keyboard shortcuts over mouse clicks
2. Use hotkeys (Ctrl+, Alt+, Win+) whenever possible
3. Use Tab/Arrow keys to navigate instead of clicking
4. Type to search instead of scrolling through lists
5. Only use mouse when absolutely necessary

AVAILABLE ACTIONS:
- press_key: key (single key like "enter", "tab", "escape", "win", "f1")
- hotkey: keys (combination like "ctrl+s", "alt+f4", "win+r")
- type: text (type text, use for searches and inputs)
- wait: duration (wait in seconds)
- click: ONLY if no keyboard alternative exists

OUTPUT FORMAT (JSON):
{
  "actions": [
    {"action": "press_key", "key": "win", "description": "Open Start menu"},
    {"action": "type", "text": "Word", "description": "Search for Word"},
    {"action": "press_key", "key": "enter", "description": "Open first result"}
  ],
  "confidence": 0.95,
  "reasoning": "Using keyboard-only approach via Start menu search"
}
""",

    PlanningApproach.MOUSE: """You are a mouse-focused automation planner.

RULES:
1. ALWAYS prefer visual clicking over keyboard
2. Click on visible UI elements directly
3. Use right-click context menus when helpful
4. Scroll to find elements instead of searching
5. Double-click to open items
6. Only use keyboard for text input

AVAILABLE ACTIONS:
- click: target (description of what to click, will be located visually)
- double_click: target (double-click to open)
- right_click: target (open context menu)
- scroll: direction, amount (scroll up/down/left/right)
- drag: from_target, to_target (drag and drop)
- type: text (only for text input fields)
- wait: duration (wait in seconds)

OUTPUT FORMAT (JSON):
{
  "actions": [
    {"action": "click", "target": "Start button in taskbar", "description": "Open Start menu"},
    {"action": "scroll", "direction": "down", "amount": 3, "description": "Scroll to find Word"},
    {"action": "click", "target": "Microsoft Word icon", "description": "Open Word"}
  ],
  "confidence": 0.75,
  "reasoning": "Using visual navigation through Start menu"
}
""",

    PlanningApproach.HYBRID: """You are an efficient automation planner that uses the best tool for each step.

RULES:
1. Use keyboard shortcuts when they're faster (Ctrl+S, Alt+Tab, etc.)
2. Use mouse clicks when targets are visually obvious
3. Combine typing with clicking for search (type query, click result)
4. Minimize total number of actions
5. Consider reliability - prefer deterministic actions

AVAILABLE ACTIONS:
- press_key: key (single key)
- hotkey: keys (combination)
- type: text (type text)
- click: target (click on element)
- double_click: target
- right_click: target
- scroll: direction, amount
- drag: from_target, to_target
- wait: duration

OUTPUT FORMAT (JSON):
{
  "actions": [
    {"action": "press_key", "key": "win", "description": "Open Start menu quickly"},
    {"action": "type", "text": "Word", "description": "Search is faster than scrolling"},
    {"action": "click", "target": "Microsoft Word in search results", "description": "Click ensures correct selection"}
  ],
  "confidence": 0.90,
  "reasoning": "Hybrid approach: keyboard for speed, click for accuracy"
}
"""
}


# Common app opening patterns (no LLM needed)
APP_PATTERNS = {
    "word": {
        PlanningApproach.KEYBOARD: [
            {"action": "press_key", "key": "win", "description": "Open Start menu"},
            {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
            {"action": "type", "text": "Word", "description": "Search for Word"},
            {"action": "wait", "duration": 0.5, "description": "Wait for results"},
            {"action": "press_key", "key": "enter", "description": "Open first result"}
        ],
        PlanningApproach.MOUSE: [
            {"action": "click", "target": "Start button", "description": "Open Start menu"},
            {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
            {"action": "click", "target": "Search box", "description": "Focus search"},
            {"action": "type", "text": "Word", "description": "Search for Word"},
            {"action": "wait", "duration": 0.5, "description": "Wait for results"},
            {"action": "click", "target": "Microsoft Word", "description": "Click Word"}
        ],
        PlanningApproach.HYBRID: [
            {"action": "press_key", "key": "win", "description": "Open Start menu"},
            {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
            {"action": "type", "text": "Word", "description": "Search for Word"},
            {"action": "wait", "duration": 0.5, "description": "Wait for results"},
            {"action": "click", "target": "Microsoft Word", "description": "Click exact match"}
        ]
    },
    "excel": {
        PlanningApproach.KEYBOARD: [
            {"action": "press_key", "key": "win", "description": "Open Start menu"},
            {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
            {"action": "type", "text": "Excel", "description": "Search for Excel"},
            {"action": "wait", "duration": 0.5, "description": "Wait for results"},
            {"action": "press_key", "key": "enter", "description": "Open first result"}
        ]
    },
    "chrome": {
        PlanningApproach.KEYBOARD: [
            {"action": "press_key", "key": "win", "description": "Open Start menu"},
            {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
            {"action": "type", "text": "Chrome", "description": "Search for Chrome"},
            {"action": "wait", "duration": 0.5, "description": "Wait for results"},
            {"action": "press_key", "key": "enter", "description": "Open first result"}
        ]
    },
    "notepad": {
        PlanningApproach.KEYBOARD: [
            {"action": "hotkey", "keys": "win+r", "description": "Open Run dialog"},
            {"action": "wait", "duration": 0.3, "description": "Wait for dialog"},
            {"action": "type", "text": "notepad", "description": "Type notepad"},
            {"action": "press_key", "key": "enter", "description": "Run notepad"}
        ]
    }
}


class PlanningSubagent(BaseSubagent):
    """
    Subagent that generates action plans using a specific approach.

    Each instance is configured with ONE approach (keyboard, mouse, hybrid).
    Multiple instances run in parallel, exploring different approaches.
    """

    def __init__(
        self,
        subagent_id: str,
        approach: PlanningApproach,
        openrouter_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the planning subagent.

        Args:
            subagent_id: Unique identifier
            approach: The planning approach to use
            openrouter_client: LLM client for complex planning
            config: Additional configuration
        """
        super().__init__(subagent_id, openrouter_client, config)
        self.approach = approach
        self.system_prompt = APPROACH_PROMPTS[approach]

    def get_capabilities(self) -> Dict[str, Any]:
        """Return capabilities of this planning subagent."""
        return {
            "type": "planning",
            "approach": self.approach.value,
            "can_handle": ["open_app", "navigate", "file_operations", "ui_interaction"],
            "requires_vision": self.approach == PlanningApproach.MOUSE
        }

    async def execute(self, context: SubagentContext) -> SubagentOutput:
        """
        Generate an action plan for the given goal.

        Args:
            context: SubagentContext with goal and parameters

        Returns:
            SubagentOutput with planned actions
        """
        goal = context.goal.lower()
        params = context.params

        logger.info(f"Planning [{self.approach.value}]: {goal}")

        # Try pattern matching first (fast, no LLM)
        pattern_result = self._try_pattern_match(goal)
        if pattern_result:
            return pattern_result

        # Fall back to LLM planning
        if self.client:
            return await self._plan_with_llm(context)

        # No LLM client - use generic pattern
        return self._generic_app_open(goal)

    def _try_pattern_match(self, goal: str) -> Optional[SubagentOutput]:
        """
        Try to match goal against known patterns.

        Returns None if no pattern matches.
        """
        # Extract app name from goal
        app_patterns = [
            (r"(?:open|start|launch|run)\s+(\w+)", 1),
            (r"(\w+)\s+(?:öffnen|starten)", 1),  # German
        ]

        app_name = None
        for pattern, group in app_patterns:
            match = re.search(pattern, goal, re.IGNORECASE)
            if match:
                app_name = match.group(group).lower()
                break

        if not app_name:
            return None

        # Check if we have a pattern for this app
        if app_name in APP_PATTERNS:
            app_data = APP_PATTERNS[app_name]
            if self.approach in app_data:
                actions = app_data[self.approach]
                return SubagentOutput(
                    success=True,
                    result={
                        "actions": actions,
                        "confidence": self._get_approach_confidence(),
                        "reasoning": f"Using {self.approach.value} pattern for {app_name}"
                    },
                    confidence=self._get_approach_confidence(),
                    reasoning=f"Pattern match: {app_name}"
                )

            # Fall back to keyboard pattern if approach not available
            if PlanningApproach.KEYBOARD in app_data:
                actions = app_data[PlanningApproach.KEYBOARD]
                return SubagentOutput(
                    success=True,
                    result={
                        "actions": actions,
                        "confidence": 0.7,
                        "reasoning": f"Using keyboard fallback for {app_name}"
                    },
                    confidence=0.7,
                    reasoning=f"Pattern fallback: {app_name}"
                )

        return None

    def _get_approach_confidence(self) -> float:
        """Get confidence score for this approach."""
        # Keyboard is generally more reliable
        confidence_map = {
            PlanningApproach.KEYBOARD: 0.95,
            PlanningApproach.HYBRID: 0.85,
            PlanningApproach.MOUSE: 0.75
        }
        return confidence_map.get(self.approach, 0.5)

    def _generic_app_open(self, goal: str) -> SubagentOutput:
        """
        Generate a generic app opening plan.

        Used when no specific pattern matches and no LLM is available.
        """
        # Extract what seems like an app name
        words = goal.split()
        app_name = words[-1] if words else "app"

        if self.approach == PlanningApproach.KEYBOARD:
            actions = [
                {"action": "press_key", "key": "win", "description": "Open Start menu"},
                {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
                {"action": "type", "text": app_name, "description": f"Search for {app_name}"},
                {"action": "wait", "duration": 0.5, "description": "Wait for results"},
                {"action": "press_key", "key": "enter", "description": "Open first result"}
            ]
            confidence = 0.8
        elif self.approach == PlanningApproach.MOUSE:
            actions = [
                {"action": "click", "target": "Start button", "description": "Open Start menu"},
                {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
                {"action": "type", "text": app_name, "description": f"Search for {app_name}"},
                {"action": "wait", "duration": 0.5, "description": "Wait for results"},
                {"action": "click", "target": f"{app_name} in search results", "description": f"Click {app_name}"}
            ]
            confidence = 0.65
        else:  # HYBRID
            actions = [
                {"action": "press_key", "key": "win", "description": "Open Start menu"},
                {"action": "wait", "duration": 0.5, "description": "Wait for menu"},
                {"action": "type", "text": app_name, "description": f"Search for {app_name}"},
                {"action": "wait", "duration": 0.5, "description": "Wait for results"},
                {"action": "click", "target": f"{app_name}", "description": f"Click exact match"}
            ]
            confidence = 0.75

        return SubagentOutput(
            success=True,
            result={
                "actions": actions,
                "confidence": confidence,
                "reasoning": f"Generic {self.approach.value} plan for: {goal}"
            },
            confidence=confidence,
            reasoning="Generic pattern"
        )

    async def _plan_with_llm(self, context: SubagentContext) -> SubagentOutput:
        """
        Use LLM to generate a custom plan.

        Called when no pattern matches.
        """
        try:
            # Build prompt
            user_prompt = f"""GOAL: {context.goal}

CONTEXT:
- Active app: {context.active_app or 'Desktop'}
- Screen elements: {len(context.screen_elements)} detected

Generate an action plan using the {self.approach.value} approach.
Return ONLY valid JSON with actions, confidence, and reasoning."""

            # Call LLM
            response = await self.client.chat_completion(
                model="openai/gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            # Parse response
            import json
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                plan_data = json.loads(json_match.group())
                return SubagentOutput(
                    success=True,
                    result=plan_data,
                    confidence=plan_data.get("confidence", 0.7),
                    reasoning=plan_data.get("reasoning", "LLM generated plan")
                )
            else:
                raise ValueError("No JSON found in LLM response")

        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
            # Fall back to generic plan
            return self._generic_app_open(context.goal)


# Runner for the planning subagent
from core.subagent_runner import SubagentRunner, SubagentType, SubagentTask, SubagentResult


class PlanningSubagentRunner(SubagentRunner):
    """
    Runner that wraps PlanningSubagent for Redis stream processing.

    Listens to moire:planning stream and processes tasks.
    """

    def __init__(
        self,
        redis_client,
        approach: PlanningApproach,
        worker_id: Optional[str] = None,
        openrouter_client: Optional[Any] = None
    ):
        super().__init__(
            redis_client=redis_client,
            agent_type=SubagentType.PLANNING,
            worker_id=worker_id or f"planning_{approach.value}"
        )
        self.approach = approach
        self.subagent = PlanningSubagent(
            subagent_id=self.worker_id,
            approach=approach,
            openrouter_client=openrouter_client
        )

    async def execute(self, task: SubagentTask) -> SubagentResult:
        """Process a planning task."""
        # Build context from task params
        context = SubagentContext(
            task_id=task.task_id,
            goal=task.params.get("goal", ""),
            params=task.params,
            active_app=task.params.get("context", {}).get("active_app"),
            screen_elements=task.params.get("context", {}).get("elements", []),
            timeout=task.timeout
        )

        # Execute planning
        output = await self.subagent.process(context)

        return SubagentResult(
            success=output.success,
            result=output.result,
            confidence=output.confidence,
            error=output.error
        )


# Convenience function to start planning workers
async def start_planning_workers(
    redis_client,
    openrouter_client=None,
    approaches: List[PlanningApproach] = None
) -> List[PlanningSubagentRunner]:
    """
    Start planning subagent workers for all approaches.

    Args:
        redis_client: Connected RedisStreamClient
        openrouter_client: Optional LLM client
        approaches: List of approaches (default: all)

    Returns:
        List of running PlanningSubagentRunner instances
    """
    import asyncio

    approaches = approaches or list(PlanningApproach)
    runners = []

    for approach in approaches:
        runner = PlanningSubagentRunner(
            redis_client=redis_client,
            approach=approach,
            openrouter_client=openrouter_client
        )
        runners.append(runner)
        asyncio.create_task(runner.run_forever())
        logger.info(f"Started planning worker: {approach.value}")

    return runners
