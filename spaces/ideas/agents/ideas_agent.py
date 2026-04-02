"""
Ideas Agent - Backend agent for Idea/Note management

Listens to events:tasks:ideas stream and executes:
- Idea tools: list, create, find, update, delete, connect, move, format, summarize, explore

Supports two execution modes:
- Direct dispatch (default): EVENT_TO_TOOL → tool(**params)
- AG2 Swarm (USE_AG2_SWARM=true): AutoGen 0.4 multi-agent team with LLM reasoning

MIGRATED FROM: swarm/backend_agents/ideas_agent.py
"""

import asyncio
import json
import logging
import os
from typing import Dict, Callable, Optional, Any

# NOTE: These imports will be updated as core migration progresses
from swarm.backend_agents.base_agent import BaseBackendAgent
from swarm.event_bus import EventBus

logger = logging.getLogger(__name__)

USE_AG2_SWARM = os.getenv("USE_AG2_SWARM", "false").lower() in ("true", "1", "yes")


class IdeasAgent(BaseBackendAgent):
    """
    Backend agent for Ideas/Notes domain.

    Handles 38+ tools for managing ideas/notes within bubbles.
    """

    # Event type to tool name mapping
    EVENT_TO_TOOL = {
        # Core idea events
        "idea.list": "list_ideas",
        "idea.count": "count_ideas",
        "idea.create": "create_idea",
        "idea.find": "find_idea",
        "idea.update": "update_idea",
        "idea.delete": "delete_idea",
        "idea.move": "move_idea",
        "idea.current_space": "get_current_space",
        # Connection events
        "idea.connect": "connect_ideas",
        "idea.disconnect": "disconnect_ideas",
        "idea.connect_multi": "connect_ideas_multi",
        "idea.link_to_root": "link_idea_to_root",
        "idea.auto_link": "auto_link_ideas",
        "idea.analyze_links": "analyze_and_suggest_links",
        # Classification & content
        "idea.classify": "classify_idea",
        "idea.add_image": "add_image",
        "idea.format_table": "format_idea_as_table",
        # Format conversion tools (format_dispatcher)
        "idea.format_note": "convert_format",
        "idea.format_action_list": "convert_format",
        "idea.format_pros_cons": "convert_format",
        "idea.format_hierarchy": "convert_format",
        "idea.format_specs": "convert_format",
        "idea.convert_format": "convert_format",
        "idea.list_formats": "list_available_formats",
        # Figma-inspired format events
        "idea.format_kanban": "convert_format",
        "idea.format_mindmap": "convert_format",
        "idea.format_swot": "convert_format",
        "idea.format_user_story": "convert_format",
        "idea.format_flowchart": "convert_format",
        # Advanced idea tools (AI)
        "idea.summarize": "summarize_idea",
        "idea.whitepaper": "generate_white_paper",
        "idea.white_paper": "generate_white_paper",  # Alias
        "idea.expand": "expand_ideas",
        "idea.explain": "explain_idea",
        # Exploration events (AI-Scientist Tree Search)
        "idea.explore.start": "start_exploration",
        "idea.explore.stop": "stop_exploration",
        "idea.explore.status": "get_exploration_status",
        "idea.explore.accept": "accept_connection",
        "idea.explore.reject": "reject_connection",
        "idea.explore.depth": "explore_deeper",
        "idea.explore.visualize": "visualize_exploration",
        "idea.explore.respond": "respond_to_exploration_question",
        "idea.explore.direction": "set_exploration_direction",
        "idea.explore.continue": "continue_exploration",
        # Project documentation export
        "idea.generate_doc": "generate_project_doc",
    }

    # Parameter normalization: map classifier output to tool expected params
    PARAM_MAPPING = {
        # idea.create expects "title" and "content"
        "idea.create": {
            "name": "title",
            "idea_name": "title",
            "idea": "title",
            "idea_title": "title",
            "idea_description": "content",
            "description": "content",
            "text": "content",
            "body": "content",
        },
        # Idea tools
        "idea.find": {
            "text": "query",
            "search": "query",
            "term": "query",
            "title": "query",
            "name": "query",
        },
        "idea.update": {
            "title": "idea_name",
            "name": "idea_name",
            "description": "new_content",
            "text": "new_content",
        },
        "idea.delete": {
            "title": "idea_name",
            "name": "idea_name",
        },
        "idea.move": {
            "title": "idea_name",
            "name": "idea_name",
            "idea": "idea_name",
            "ziel": "target_bubble",
            "target": "target_bubble",
            "nach": "target_bubble",
        },
        "idea.connect": {
            "source": "idea1",
            "target": "idea2",
            "from_idea": "idea1",
            "to_idea": "idea2",
        },
        "idea.disconnect": {
            "source": "idea1",
            "target": "idea2",
            "from_idea": "idea1",
            "to_idea": "idea2",
            "von": "idea1",
            "zu": "idea2",
            "erste": "idea1",
            "zweite": "idea2",
        },
        "idea.connect_multi": {
            "ideen": "idea_names",
            "ideas": "idea_names",
            "names": "idea_names",
            "title": "idea_names",
            "titles": "idea_names",
        },
        "idea.link_to_root": {
            "title": "idea_name",
            "name": "idea_name",
            "idea": "idea_name",
        },
        "idea.classify": {
            "title": "idea_name",
            "name": "idea_name",
            "idea": "idea_name",
        },
        # idea.format_table expects "idea_name" and optionally "custom_columns"
        "idea.format_table": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "columns": "custom_columns",
            "headers": "custom_columns",
            "spalten": "custom_columns",
            "instruction": "format_instruction",
            "format": "format_instruction",
        },
        # Advanced idea tools parameter mappings
        "idea.summarize": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "stil": "style",
        },
        "idea.whitepaper": {
            "name": "start_node",
            "title": "start_node",
            "idea": "start_node",
            "idee": "start_node",
        },
        "idea.white_paper": {
            "name": "start_node",
            "title": "start_node",
            "idea": "start_node",
            "idee": "start_node",
        },
        "idea.expand": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "anzahl": "count",
            "number": "count",
        },
        "idea.explain": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
        },
        # Format conversion tools (all use convert_format with target_format)
        "idea.format_note": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "note"},
        },
        "idea.format_action_list": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "action_list"},
        },
        "idea.format_pros_cons": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "pros_cons"},
        },
        "idea.format_hierarchy": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "hierarchy"},
        },
        "idea.format_specs": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "specs"},
        },
        "idea.convert_format": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "format": "target_format",
            "zielformat": "target_format",
        },
        "idea.list_formats": {},
        "idea.analyze_links": {},
        # Figma-inspired format parameter mappings
        "idea.format_kanban": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "kanban"},
        },
        "idea.format_mindmap": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "mindmap"},
        },
        "idea.format_swot": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "swot"},
        },
        "idea.format_user_story": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "user_story"},
        },
        "idea.format_flowchart": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
            "_inject": {"target_format": "flowchart"},
        },
        # Project documentation parameter mappings
        "idea.generate_doc": {
            "name": "bubble_name",
            "title": "bubble_name",
            "bubble": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        # Exploration parameter mappings
        "idea.explore.start": {
            "id": "bubble_id",
            "bubble": "bubble_id",
            "space": "bubble_id",
            "tiefe": "depth",
            "modus": "mode",
            "richtung": "context",
            "direction": "context",
        },
        "idea.explore.respond": {
            "id": "question_id",
            "frage": "question_id",
            "antwort": "response_type",
            "response": "response_type",
            "option": "selected_option",
            "auswahl": "selected_option",
        },
        "idea.explore.direction": {
            "richtung": "direction",
            "thema": "direction",
            "bubble": "bubble_id",
            "space": "bubble_id",
        },
        "idea.explore.accept": {
            "id": "connection_id",
            "verbindung": "connection_id",
        },
        "idea.explore.reject": {
            "id": "connection_id",
            "verbindung": "connection_id",
        },
        "idea.explore.depth": {
            "id": "connection_id",
            "verbindung": "connection_id",
        },
    }

    @property
    def stream(self) -> str:
        return EventBus.STREAM_TASKS_IDEAS

    @property
    def name(self) -> str:
        return "IdeasAgent"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load idea tools."""
        tools = {}

        # Load core idea tools
        try:
            from spaces.ideas.adapted.idea_tools import (
                list_ideas,
                create_idea,
                find_idea,
                update_idea,
                delete_idea,
                connect_ideas,
                disconnect_ideas,
                add_image,
                get_current_space,
                auto_link_ideas,
                format_idea_as_table,
                summarize_idea,
                generate_white_paper,
                expand_ideas,
                analyze_and_suggest_links,
                explain_idea,
            )
            from tools.idea_tools import (
                count_ideas,
                move_idea,
                connect_ideas_multi,
                link_idea_to_root,
                classify_idea,
            )

            tools.update({
                "list_ideas": list_ideas,
                "count_ideas": count_ideas,
                "create_idea": create_idea,
                "find_idea": find_idea,
                "update_idea": update_idea,
                "delete_idea": delete_idea,
                "move_idea": move_idea,
                "connect_ideas": connect_ideas,
                "disconnect_ideas": disconnect_ideas,
                "connect_ideas_multi": connect_ideas_multi,
                "link_idea_to_root": link_idea_to_root,
                "classify_idea": classify_idea,
                "auto_link_ideas": auto_link_ideas,
                "add_image": add_image,
                "get_current_space": get_current_space,
                "format_idea_as_table": format_idea_as_table,
                "summarize_idea": summarize_idea,
                "generate_white_paper": generate_white_paper,
                "expand_ideas": expand_ideas,
                "analyze_and_suggest_links": analyze_and_suggest_links,
                "explain_idea": explain_idea,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} idea tools")

            # Load project doc generation tool
            from spaces.ideas.tools.summary_tools import generate_project_doc
            tools["generate_project_doc"] = generate_project_doc
            logger.info(f"{self.name}: Loaded generate_project_doc tool")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load idea tools: {e}")

        # Load format dispatcher tools
        try:
            from tools.format_dispatcher import convert_format, list_available_formats

            tools.update({
                "convert_format": convert_format,
                "list_available_formats": list_available_formats,
            })
            logger.info(f"{self.name}: Loaded format dispatcher tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load format dispatcher tools: {e}")

        # Load exploration tools (AI-Scientist Tree Search)
        try:
            from spaces.ideas.tools.exploration_tools import (
                start_exploration,
                stop_exploration,
                get_exploration_status,
                accept_connection,
                reject_connection,
                explore_deeper,
                visualize_exploration,
                respond_to_exploration_question,
                set_exploration_direction,
            )

            tools.update({
                "start_exploration": start_exploration,
                "stop_exploration": stop_exploration,
                "get_exploration_status": get_exploration_status,
                "accept_connection": accept_connection,
                "reject_connection": reject_connection,
                "explore_deeper": explore_deeper,
                "visualize_exploration": visualize_exploration,
                "respond_to_exploration_question": respond_to_exploration_question,
                "set_exploration_direction": set_exploration_direction,
                "continue_exploration": start_exploration,
            })
            logger.info(f"{self.name}: Loaded 10 exploration tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load exploration tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool name."""
        return self.EVENT_TO_TOOL.get(event_type)

    # --- AG2 Swarm Integration ---

    async def _handle_event(self, event):
        """
        Handle incoming event.

        When USE_AG2_SWARM is enabled, routes through AutoGen 0.4 Swarm
        for LLM-based reasoning. Otherwise falls back to direct dispatch.
        """
        if not USE_AG2_SWARM:
            return await super()._handle_event(event)

        # AG2 Swarm path
        job_id = event.job_id or "unknown"
        event_type = event.event_type
        payload = event.payload

        logger.info(f"{self.name}: [AG2 Swarm] Received {event_type} (job={job_id})")

        try:
            await self._publish_status(job_id, "started", event_type=event_type)

            # Build natural language task from event
            task = self._build_swarm_task(event_type, payload)
            logger.info(f"{self.name}: [AG2 Swarm] Task: {task}")

            # Run through Swarm
            result = await self._run_swarm(task)

            await self._publish_status(
                job_id,
                "completed",
                result=result,
                event_type=event_type,
            )
            logger.info(f"{self.name}: [AG2 Swarm] Completed {event_type} (job={job_id})")

        except Exception as e:
            logger.error(f"{self.name}: [AG2 Swarm] Error: {e}", exc_info=True)
            await self._publish_error(job_id, str(e), event_type=event_type)

    def _build_swarm_task(self, event_type: str, payload: Dict[str, Any]) -> str:
        """
        Build a natural language task description from event_type + payload.

        The Swarm coordinator uses this to decide which specialist agent to invoke.
        """
        # Clean payload: remove internal fields
        clean = {
            k: v for k, v in payload.items()
            if k not in (
                "job_id", "user_id", "session_id", "priority",
                "bubble_context", "metadata", "_user_input", "_conversation_history",
            ) and v  # skip empty values
        }

        # Use user_input if available (most natural for LLM)
        user_input = payload.get("_user_input", "")
        if user_input:
            return f"{user_input}\n\n[Event: {event_type}, Params: {json.dumps(clean, ensure_ascii=False)}]"

        # Fallback: structured task
        if clean:
            params_str = ", ".join(f"{k}={v!r}" for k, v in clean.items())
            return f"Führe aus: {event_type} mit {params_str}"

        return f"Führe aus: {event_type}"

    async def _run_swarm(self, task: str) -> str:
        """
        Run a task through the AG2 Ideas Swarm.

        Returns the final response text from the Swarm.
        """
        from spaces.ideas.swarm.ideas_swarm import get_ideas_swarm

        swarm = get_ideas_swarm()
        task_result = await swarm.run(task=task)

        # Extract final message content
        if task_result.messages:
            last_msg = task_result.messages[-1]
            content = getattr(last_msg, "content", str(last_msg))
            if content:
                return content

        return "Swarm hat die Aufgabe abgeschlossen (keine Antwort)."


# Singleton instance
_ideas_agent: Optional[IdeasAgent] = None


def get_ideas_agent() -> IdeasAgent:
    """Get or create IdeasAgent singleton."""
    global _ideas_agent
    if _ideas_agent is None:
        _ideas_agent = IdeasAgent()
    return _ideas_agent


__all__ = ["IdeasAgent", "get_ideas_agent"]
