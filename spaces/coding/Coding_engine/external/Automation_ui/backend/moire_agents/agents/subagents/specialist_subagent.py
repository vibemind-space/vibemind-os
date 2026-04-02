"""
Specialist Subagent - Domain experts with knowledge bases.

Each SpecialistSubagent instance specializes in ONE domain:
- OFFICE: Microsoft Office apps (Word, Excel, PowerPoint)
- BROWSER: Web browsers (Chrome, Firefox, Edge)
- GAMING: Gaming platforms (Steam, Discord, LoL)
- SYSTEM: Windows system (Settings, Explorer, Control Panel)
- CREATIVE: Creative tools (Adobe, Figma, Blender)
- DEVELOPMENT: Development tools (VS Code, terminals, Git)

Specialists provide:
- Keyboard shortcuts for actions
- Workflows for common tasks
- Domain-specific knowledge and patterns

Example:
    Query specialist for Office domain:
    Q: "How to make text bold in Word?"
    A: {shortcut: "Ctrl+B", workflow: ["select text", "press Ctrl+B"]}
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .base_subagent import BaseSubagent, SubagentContext, SubagentOutput

logger = logging.getLogger(__name__)


class SpecialistDomain(Enum):
    """Specialist domains."""
    OFFICE = "office"           # Word, Excel, PowerPoint
    BROWSER = "browser"         # Chrome, Firefox, Edge
    GAMING = "gaming"           # Steam, Discord, LoL
    SYSTEM = "system"           # Windows Settings, Explorer
    CREATIVE = "creative"       # Adobe, Figma, Blender
    DEVELOPMENT = "development" # VS Code, terminals, Git


@dataclass
class Shortcut:
    """A keyboard shortcut."""
    action: str
    keys: str
    description: str
    app: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "keys": self.keys,
            "description": self.description,
            "app": self.app
        }


@dataclass
class Workflow:
    """A workflow for a task."""
    task: str
    steps: List[str]
    shortcuts_used: List[str] = field(default_factory=list)
    estimated_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "steps": self.steps,
            "shortcuts_used": self.shortcuts_used,
            "estimated_time_seconds": self.estimated_time_seconds
        }


# Domain knowledge bases (embedded for reliability)
DOMAIN_KNOWLEDGE = {
    SpecialistDomain.OFFICE: {
        "apps": ["Microsoft Word", "Microsoft Excel", "Microsoft PowerPoint", "Microsoft Outlook"],
        "shortcuts": {
            # Common Office shortcuts
            "save": {"keys": "Ctrl+S", "description": "Save document"},
            "save_as": {"keys": "F12", "description": "Save As dialog"},
            "open": {"keys": "Ctrl+O", "description": "Open file"},
            "new": {"keys": "Ctrl+N", "description": "New document"},
            "print": {"keys": "Ctrl+P", "description": "Print"},
            "undo": {"keys": "Ctrl+Z", "description": "Undo last action"},
            "redo": {"keys": "Ctrl+Y", "description": "Redo"},
            "copy": {"keys": "Ctrl+C", "description": "Copy selection"},
            "cut": {"keys": "Ctrl+X", "description": "Cut selection"},
            "paste": {"keys": "Ctrl+V", "description": "Paste"},
            "select_all": {"keys": "Ctrl+A", "description": "Select all"},
            "find": {"keys": "Ctrl+F", "description": "Find"},
            "replace": {"keys": "Ctrl+H", "description": "Find and Replace"},
            # Word-specific
            "bold": {"keys": "Ctrl+B", "description": "Bold text", "app": "Word"},
            "italic": {"keys": "Ctrl+I", "description": "Italic text", "app": "Word"},
            "underline": {"keys": "Ctrl+U", "description": "Underline text", "app": "Word"},
            "font_dialog": {"keys": "Ctrl+D", "description": "Font dialog", "app": "Word"},
            "center": {"keys": "Ctrl+E", "description": "Center text", "app": "Word"},
            "left_align": {"keys": "Ctrl+L", "description": "Left align", "app": "Word"},
            "right_align": {"keys": "Ctrl+R", "description": "Right align", "app": "Word"},
            "justify": {"keys": "Ctrl+J", "description": "Justify text", "app": "Word"},
            # Excel-specific
            "sum": {"keys": "Alt+=", "description": "AutoSum", "app": "Excel"},
            "edit_cell": {"keys": "F2", "description": "Edit cell", "app": "Excel"},
            "insert_row": {"keys": "Ctrl+Shift++", "description": "Insert row", "app": "Excel"},
            "delete_row": {"keys": "Ctrl+-", "description": "Delete row", "app": "Excel"},
        },
        "workflows": {
            "create_document": ["Open Word (Win+type Word+Enter)", "Start typing", "Save with Ctrl+S"],
            "format_text": ["Select text", "Apply bold (Ctrl+B) or italic (Ctrl+I)", "Change font with Ctrl+D"],
            "create_spreadsheet": ["Open Excel", "Enter data in cells", "Use Tab to move right, Enter for down"],
        }
    },

    SpecialistDomain.BROWSER: {
        "apps": ["Google Chrome", "Mozilla Firefox", "Microsoft Edge", "Brave"],
        "shortcuts": {
            "new_tab": {"keys": "Ctrl+T", "description": "New tab"},
            "close_tab": {"keys": "Ctrl+W", "description": "Close tab"},
            "reopen_tab": {"keys": "Ctrl+Shift+T", "description": "Reopen closed tab"},
            "next_tab": {"keys": "Ctrl+Tab", "description": "Next tab"},
            "prev_tab": {"keys": "Ctrl+Shift+Tab", "description": "Previous tab"},
            "address_bar": {"keys": "Ctrl+L", "description": "Focus address bar"},
            "search": {"keys": "Ctrl+K", "description": "Search in address bar"},
            "find": {"keys": "Ctrl+F", "description": "Find on page"},
            "refresh": {"keys": "F5", "description": "Refresh page"},
            "hard_refresh": {"keys": "Ctrl+Shift+R", "description": "Hard refresh (clear cache)"},
            "back": {"keys": "Alt+Left", "description": "Go back"},
            "forward": {"keys": "Alt+Right", "description": "Go forward"},
            "bookmark": {"keys": "Ctrl+D", "description": "Bookmark page"},
            "history": {"keys": "Ctrl+H", "description": "Open history"},
            "downloads": {"keys": "Ctrl+J", "description": "Open downloads"},
            "dev_tools": {"keys": "F12", "description": "Developer tools"},
            "incognito": {"keys": "Ctrl+Shift+N", "description": "New incognito window"},
            "zoom_in": {"keys": "Ctrl++", "description": "Zoom in"},
            "zoom_out": {"keys": "Ctrl+-", "description": "Zoom out"},
            "zoom_reset": {"keys": "Ctrl+0", "description": "Reset zoom"},
        },
        "workflows": {
            "navigate_to_url": ["Press Ctrl+L", "Type URL", "Press Enter"],
            "search_web": ["Press Ctrl+K or Ctrl+L", "Type search query", "Press Enter"],
            "manage_tabs": ["Use Ctrl+Tab to switch", "Ctrl+W to close", "Ctrl+Shift+T to restore"],
        }
    },

    SpecialistDomain.GAMING: {
        "apps": ["Steam", "Discord", "Epic Games", "Battle.net", "League of Legends"],
        "shortcuts": {
            # Steam
            "steam_overlay": {"keys": "Shift+Tab", "description": "Steam overlay", "app": "Steam"},
            "steam_screenshot": {"keys": "F12", "description": "Take screenshot", "app": "Steam"},
            # Discord
            "discord_mute": {"keys": "Ctrl+Shift+M", "description": "Mute mic", "app": "Discord"},
            "discord_deafen": {"keys": "Ctrl+Shift+D", "description": "Deafen", "app": "Discord"},
            "discord_search": {"keys": "Ctrl+K", "description": "Quick switcher", "app": "Discord"},
            # General gaming
            "fullscreen": {"keys": "Alt+Enter", "description": "Toggle fullscreen"},
            "screenshot": {"keys": "Win+PrintScreen", "description": "Windows screenshot"},
            "game_bar": {"keys": "Win+G", "description": "Windows Game Bar"},
            "record_clip": {"keys": "Win+Alt+R", "description": "Record game clip"},
        },
        "workflows": {
            "launch_game": ["Open Steam/launcher", "Find game in library", "Click Play"],
            "join_discord_call": ["Open Discord", "Click voice channel", "or use Quick Switcher (Ctrl+K)"],
        }
    },

    SpecialistDomain.SYSTEM: {
        "apps": ["Windows Explorer", "Settings", "Control Panel", "Task Manager", "Command Prompt"],
        "shortcuts": {
            "explorer": {"keys": "Win+E", "description": "Open Explorer"},
            "run": {"keys": "Win+R", "description": "Run dialog"},
            "settings": {"keys": "Win+I", "description": "Open Settings"},
            "search": {"keys": "Win+S", "description": "Windows Search"},
            "lock": {"keys": "Win+L", "description": "Lock computer"},
            "task_view": {"keys": "Win+Tab", "description": "Task view"},
            "desktop": {"keys": "Win+D", "description": "Show desktop"},
            "minimize_all": {"keys": "Win+M", "description": "Minimize all windows"},
            "task_manager": {"keys": "Ctrl+Shift+Esc", "description": "Task Manager"},
            "switch_app": {"keys": "Alt+Tab", "description": "Switch application"},
            "clipboard": {"keys": "Win+V", "description": "Clipboard history"},
            "snip": {"keys": "Win+Shift+S", "description": "Snipping tool"},
            "emoji": {"keys": "Win+.", "description": "Emoji picker"},
            "action_center": {"keys": "Win+A", "description": "Action center"},
            "new_desktop": {"keys": "Win+Ctrl+D", "description": "New virtual desktop"},
            "close_desktop": {"keys": "Win+Ctrl+F4", "description": "Close virtual desktop"},
            "switch_desktop": {"keys": "Win+Ctrl+Left/Right", "description": "Switch desktop"},
            # Explorer
            "new_folder": {"keys": "Ctrl+Shift+N", "description": "New folder", "app": "Explorer"},
            "rename": {"keys": "F2", "description": "Rename", "app": "Explorer"},
            "delete": {"keys": "Delete", "description": "Delete to recycle bin", "app": "Explorer"},
            "perm_delete": {"keys": "Shift+Delete", "description": "Permanent delete", "app": "Explorer"},
            "properties": {"keys": "Alt+Enter", "description": "Properties", "app": "Explorer"},
        },
        "workflows": {
            "open_app": ["Press Win key", "Type app name", "Press Enter"],
            "manage_windows": ["Alt+Tab to switch", "Win+D for desktop", "Win+Arrow to snap"],
            "file_operations": ["Win+E for Explorer", "Navigate to folder", "Use Ctrl+C/V for copy/paste"],
        }
    },

    SpecialistDomain.CREATIVE: {
        "apps": ["Adobe Photoshop", "Adobe Premiere", "Figma", "Blender", "Adobe Illustrator"],
        "shortcuts": {
            # Photoshop
            "ps_brush": {"keys": "B", "description": "Brush tool", "app": "Photoshop"},
            "ps_eraser": {"keys": "E", "description": "Eraser tool", "app": "Photoshop"},
            "ps_move": {"keys": "V", "description": "Move tool", "app": "Photoshop"},
            "ps_select": {"keys": "M", "description": "Marquee select", "app": "Photoshop"},
            "ps_lasso": {"keys": "L", "description": "Lasso tool", "app": "Photoshop"},
            "ps_zoom": {"keys": "Z", "description": "Zoom tool", "app": "Photoshop"},
            "ps_hand": {"keys": "H", "description": "Hand tool", "app": "Photoshop"},
            "ps_new_layer": {"keys": "Ctrl+Shift+N", "description": "New layer", "app": "Photoshop"},
            # Figma
            "figma_frame": {"keys": "F", "description": "Frame tool", "app": "Figma"},
            "figma_rectangle": {"keys": "R", "description": "Rectangle", "app": "Figma"},
            "figma_ellipse": {"keys": "O", "description": "Ellipse", "app": "Figma"},
            "figma_line": {"keys": "L", "description": "Line", "app": "Figma"},
            "figma_text": {"keys": "T", "description": "Text tool", "app": "Figma"},
            "figma_hand": {"keys": "H", "description": "Hand tool", "app": "Figma"},
            "figma_comment": {"keys": "C", "description": "Comment", "app": "Figma"},
            # Common
            "zoom_in": {"keys": "Ctrl++", "description": "Zoom in"},
            "zoom_out": {"keys": "Ctrl+-", "description": "Zoom out"},
            "fit_view": {"keys": "Ctrl+0", "description": "Fit to view"},
        },
        "workflows": {
            "edit_image": ["Open in Photoshop", "Make selection", "Apply adjustments", "Save"],
            "design_ui": ["Create frame in Figma", "Add components", "Style with colors/fonts"],
        }
    },

    SpecialistDomain.DEVELOPMENT: {
        "apps": ["Visual Studio Code", "Terminal", "Git Bash", "PyCharm", "IntelliJ"],
        "shortcuts": {
            # VS Code
            "vsc_command": {"keys": "Ctrl+Shift+P", "description": "Command palette", "app": "VS Code"},
            "vsc_quick_open": {"keys": "Ctrl+P", "description": "Quick open file", "app": "VS Code"},
            "vsc_search": {"keys": "Ctrl+Shift+F", "description": "Search in files", "app": "VS Code"},
            "vsc_terminal": {"keys": "Ctrl+`", "description": "Toggle terminal", "app": "VS Code"},
            "vsc_sidebar": {"keys": "Ctrl+B", "description": "Toggle sidebar", "app": "VS Code"},
            "vsc_go_to_line": {"keys": "Ctrl+G", "description": "Go to line", "app": "VS Code"},
            "vsc_go_to_def": {"keys": "F12", "description": "Go to definition", "app": "VS Code"},
            "vsc_peek_def": {"keys": "Alt+F12", "description": "Peek definition", "app": "VS Code"},
            "vsc_rename": {"keys": "F2", "description": "Rename symbol", "app": "VS Code"},
            "vsc_format": {"keys": "Shift+Alt+F", "description": "Format document", "app": "VS Code"},
            "vsc_comment": {"keys": "Ctrl+/", "description": "Toggle comment", "app": "VS Code"},
            "vsc_multi_cursor": {"keys": "Ctrl+Alt+Down", "description": "Add cursor below", "app": "VS Code"},
            "vsc_select_word": {"keys": "Ctrl+D", "description": "Select word", "app": "VS Code"},
            "vsc_duplicate": {"keys": "Shift+Alt+Down", "description": "Duplicate line", "app": "VS Code"},
            "vsc_move_line": {"keys": "Alt+Up/Down", "description": "Move line", "app": "VS Code"},
            # Terminal
            "term_clear": {"keys": "Ctrl+L", "description": "Clear terminal"},
            "term_cancel": {"keys": "Ctrl+C", "description": "Cancel command"},
            "term_prev": {"keys": "Up", "description": "Previous command"},
            "term_search": {"keys": "Ctrl+R", "description": "Search history"},
        },
        "workflows": {
            "open_project": ["Open VS Code", "Ctrl+O or File > Open Folder", "Select project"],
            "code_navigation": ["Ctrl+P to find file", "F12 for definition", "Ctrl+Shift+F to search"],
            "git_workflow": ["Stage changes", "Commit with message", "Push to remote"],
        }
    }
}


class SpecialistSubagent(BaseSubagent):
    """
    Subagent that provides domain-specific knowledge.

    Each instance is configured with ONE domain.
    Provides shortcuts, workflows, and expert advice.
    """

    def __init__(
        self,
        subagent_id: str,
        domain: SpecialistDomain,
        openrouter_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        knowledge_dir: Optional[str] = None
    ):
        """
        Initialize the specialist subagent.

        Args:
            subagent_id: Unique identifier
            domain: The specialist domain
            openrouter_client: LLM client for complex queries
            config: Additional configuration
            knowledge_dir: Directory containing knowledge JSON files
        """
        super().__init__(subagent_id, openrouter_client, config)
        self.domain = domain
        self.knowledge = self._load_knowledge(knowledge_dir)

    def _load_knowledge(self, knowledge_dir: Optional[str]) -> Dict[str, Any]:
        """Load domain knowledge from embedded data or file."""
        # Use embedded knowledge
        knowledge = DOMAIN_KNOWLEDGE.get(self.domain, {})

        # Try to load additional knowledge from file
        if knowledge_dir:
            json_path = os.path.join(knowledge_dir, f"{self.domain.value}.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        file_knowledge = json.load(f)
                        # Merge file knowledge with embedded
                        for key, value in file_knowledge.items():
                            if key in knowledge and isinstance(value, dict):
                                knowledge[key].update(value)
                            else:
                                knowledge[key] = value
                    logger.info(f"Loaded additional knowledge from {json_path}")
                except Exception as e:
                    logger.warning(f"Failed to load knowledge file: {e}")

        return knowledge

    def get_capabilities(self) -> Dict[str, Any]:
        """Return capabilities of this specialist subagent."""
        return {
            "type": "specialist",
            "domain": self.domain.value,
            "can_handle": ["shortcuts", "workflows", "knowledge_query"],
            "apps": self.knowledge.get("apps", []),
            "shortcut_count": len(self.knowledge.get("shortcuts", {})),
            "workflow_count": len(self.knowledge.get("workflows", {}))
        }

    async def execute(self, context: SubagentContext) -> SubagentOutput:
        """
        Answer a domain-specific query.

        Args:
            context: SubagentContext with query and parameters

        Returns:
            SubagentOutput with answer, shortcuts, workflows
        """
        query = context.params.get("query", context.goal).lower()
        query_type = context.params.get("query_type", "auto")

        logger.info(f"Specialist [{self.domain.value}]: {query}")

        # Determine query type
        if query_type == "auto":
            if "shortcut" in query or "keyboard" in query or "keys" in query:
                query_type = "shortcut"
            elif "workflow" in query or "how to" in query or "steps" in query:
                query_type = "workflow"
            else:
                query_type = "general"

        # Handle query
        if query_type == "shortcut":
            return self._handle_shortcut_query(query)
        elif query_type == "workflow":
            return self._handle_workflow_query(query)
        else:
            return self._handle_general_query(query, context)

    def _handle_shortcut_query(self, query: str) -> SubagentOutput:
        """Handle a shortcut query."""
        shortcuts = self.knowledge.get("shortcuts", {})

        # Search for matching shortcuts
        matches = []
        query_words = set(query.lower().split())

        for action, data in shortcuts.items():
            # Match by action name or description
            action_words = set(action.lower().split('_'))
            desc_words = set(data.get("description", "").lower().split())

            if query_words & action_words or query_words & desc_words:
                matches.append(Shortcut(
                    action=action,
                    keys=data["keys"],
                    description=data.get("description", ""),
                    app=data.get("app")
                ))

        if matches:
            # Return best match
            best_match = matches[0]
            return SubagentOutput(
                success=True,
                result={
                    "answer": f"Use {best_match.keys} to {best_match.description}",
                    "shortcut": best_match.to_dict(),
                    "all_matches": [m.to_dict() for m in matches[:5]],
                    "domain": self.domain.value
                },
                confidence=0.95 if len(matches) == 1 else 0.8,
                reasoning=f"Found {len(matches)} matching shortcuts"
            )
        else:
            # Return all shortcuts for the domain
            all_shortcuts = {k: v for k, v in shortcuts.items()}
            return SubagentOutput(
                success=True,
                result={
                    "answer": "No exact match found. Here are available shortcuts:",
                    "shortcuts": all_shortcuts,
                    "domain": self.domain.value
                },
                confidence=0.5,
                reasoning="No exact shortcut match, returning all"
            )

    def _handle_workflow_query(self, query: str) -> SubagentOutput:
        """Handle a workflow query."""
        workflows = self.knowledge.get("workflows", {})

        # Search for matching workflow
        matches = []
        query_words = set(query.lower().split())

        for task, steps in workflows.items():
            task_words = set(task.lower().replace('_', ' ').split())
            if query_words & task_words:
                matches.append(Workflow(
                    task=task,
                    steps=steps if isinstance(steps, list) else [steps]
                ))

        if matches:
            best_match = matches[0]
            return SubagentOutput(
                success=True,
                result={
                    "answer": f"To {best_match.task}:",
                    "workflow": best_match.to_dict(),
                    "steps": best_match.steps,
                    "domain": self.domain.value
                },
                confidence=0.9,
                reasoning=f"Found matching workflow: {best_match.task}"
            )
        else:
            # Try LLM for custom workflow
            if self.client:
                return self._generate_workflow_with_llm(query)

            return SubagentOutput(
                success=True,
                result={
                    "answer": "No predefined workflow found. Available workflows:",
                    "workflows": list(workflows.keys()),
                    "domain": self.domain.value
                },
                confidence=0.4,
                reasoning="No matching workflow found"
            )

    def _handle_general_query(self, query: str, context: SubagentContext) -> SubagentOutput:
        """Handle a general knowledge query."""
        # Check if query mentions a specific app
        apps = self.knowledge.get("apps", [])
        mentioned_app = None
        for app in apps:
            if app.lower() in query:
                mentioned_app = app
                break

        # Get relevant shortcuts for the app
        shortcuts = self.knowledge.get("shortcuts", {})
        relevant_shortcuts = {}
        for action, data in shortcuts.items():
            if mentioned_app and data.get("app"):
                if data["app"].lower() in mentioned_app.lower():
                    relevant_shortcuts[action] = data
            elif not data.get("app"):  # Common shortcuts
                relevant_shortcuts[action] = data

        # Use LLM for complex queries
        if self.client:
            return self._answer_with_llm(query, context, relevant_shortcuts)

        # Basic answer
        return SubagentOutput(
            success=True,
            result={
                "answer": f"Query about {self.domain.value}",
                "domain": self.domain.value,
                "apps": apps,
                "shortcuts": relevant_shortcuts if relevant_shortcuts else shortcuts,
                "workflows": self.knowledge.get("workflows", {})
            },
            confidence=0.6,
            reasoning="General domain knowledge"
        )

    def _generate_workflow_with_llm(self, query: str) -> SubagentOutput:
        """Generate a custom workflow using LLM."""
        # Placeholder - would call LLM API
        return SubagentOutput(
            success=True,
            result={
                "answer": f"Custom workflow generation not implemented without LLM",
                "query": query,
                "domain": self.domain.value
            },
            confidence=0.3,
            reasoning="LLM workflow generation not implemented"
        )

    def _answer_with_llm(self, query: str, context: SubagentContext, shortcuts: Dict) -> SubagentOutput:
        """Answer using LLM with domain knowledge."""
        # Placeholder - would call LLM API with context
        return SubagentOutput(
            success=True,
            result={
                "answer": f"LLM-assisted answer not implemented",
                "query": query,
                "domain": self.domain.value,
                "relevant_shortcuts": shortcuts
            },
            confidence=0.4,
            reasoning="LLM answer generation not implemented"
        )

    def get_shortcut(self, action: str) -> Optional[Shortcut]:
        """Get a specific shortcut by action name."""
        shortcuts = self.knowledge.get("shortcuts", {})
        if action in shortcuts:
            data = shortcuts[action]
            return Shortcut(
                action=action,
                keys=data["keys"],
                description=data.get("description", ""),
                app=data.get("app")
            )
        return None

    def get_all_shortcuts(self, app: Optional[str] = None) -> List[Shortcut]:
        """Get all shortcuts, optionally filtered by app."""
        shortcuts = self.knowledge.get("shortcuts", {})
        result = []
        for action, data in shortcuts.items():
            if app and data.get("app") and app.lower() not in data["app"].lower():
                continue
            result.append(Shortcut(
                action=action,
                keys=data["keys"],
                description=data.get("description", ""),
                app=data.get("app")
            ))
        return result


# Runner for the specialist subagent
from core.subagent_runner import SubagentRunner, SubagentType, SubagentTask, SubagentResult


class SpecialistSubagentRunner(SubagentRunner):
    """
    Runner that wraps SpecialistSubagent for Redis stream processing.

    Listens to moire:specialist stream and processes queries.
    """

    def __init__(
        self,
        redis_client,
        domain: SpecialistDomain,
        worker_id: Optional[str] = None,
        openrouter_client: Optional[Any] = None,
        knowledge_dir: Optional[str] = None
    ):
        super().__init__(
            redis_client=redis_client,
            agent_type=SubagentType.SPECIALIST,
            worker_id=worker_id or f"specialist_{domain.value}"
        )
        self.domain = domain
        self.subagent = SpecialistSubagent(
            subagent_id=self.worker_id,
            domain=domain,
            openrouter_client=openrouter_client,
            knowledge_dir=knowledge_dir
        )

    async def execute(self, task: SubagentTask) -> SubagentResult:
        """Process a specialist query task."""
        # Build context from task params
        context = SubagentContext(
            task_id=task.task_id,
            goal=task.params.get("query", ""),
            params=task.params,
            timeout=task.timeout
        )

        # Execute query
        output = await self.subagent.process(context)

        return SubagentResult(
            success=output.success,
            result=output.result,
            confidence=output.confidence,
            error=output.error
        )


# Convenience function to start specialist workers
async def start_specialist_workers(
    redis_client,
    openrouter_client=None,
    domains: List[SpecialistDomain] = None,
    knowledge_dir: Optional[str] = None
) -> List[SpecialistSubagentRunner]:
    """
    Start specialist subagent workers for specified domains.

    Args:
        redis_client: Connected RedisStreamClient
        openrouter_client: Optional LLM client
        domains: List of domains (default: all)
        knowledge_dir: Directory containing knowledge JSON files

    Returns:
        List of running SpecialistSubagentRunner instances
    """
    import asyncio

    domains = domains or list(SpecialistDomain)
    runners = []

    for domain in domains:
        runner = SpecialistSubagentRunner(
            redis_client=redis_client,
            domain=domain,
            openrouter_client=openrouter_client,
            knowledge_dir=knowledge_dir
        )
        runners.append(runner)
        asyncio.create_task(runner.run_forever())
        logger.info(f"Started specialist worker: {domain.value}")

    return runners
