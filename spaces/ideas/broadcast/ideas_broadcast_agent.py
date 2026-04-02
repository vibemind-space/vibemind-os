"""
IdeasBroadcastAgent - Fan-out agent for Ideas/Bubbles domain.

Merges the functionality of:
- IdeasAgent (backend_agents/ideas_agent.py) - 38+ idea tools
- BubblesAgent (backend_agents/bubbles_agent.py) - 13 bubble tools

Domain prefixes: idea.*, bubble.*

Contains an internal AutoGen Swarm team (optional via USE_AG2_SWARM)
for LLM-based reasoning when executing complex multi-step tasks.
"""

import logging
from typing import Dict, Set, Callable, Optional

from swarm.broadcast.base_broadcast_agent import BaseBroadcastAgent

logger = logging.getLogger(__name__)


class IdeasBroadcastAgent(BaseBroadcastAgent):
    """
    Broadcast agent for Ideas + Bubbles domain.

    Merges IdeasAgent + BubblesAgent EVENT_TO_TOOL and PARAM_MAPPING.
    """

    # --- Merged EVENT_TO_TOOL from IdeasAgent + BubblesAgent ---
    EVENT_TO_TOOL = {
        # === Bubble events (from BubblesAgent) ===
        "bubble.list": "list_bubbles",
        "bubble.create": "create_bubble",
        "bubble.enter": "enter_bubble",
        "bubble.exit": "exit_bubble",
        "bubble.back": "exit_bubble",
        "bubble.delete": "delete_bubble",
        "bubble.delete_all_except": "delete_all_bubbles_except",
        "bubble.update": "update_bubble",
        "bubble.find": "find_bubble",
        "bubble.stats": "get_bubble_stats",
        "bubble.score": "score_bubble",
        "bubble.evaluate": "evaluate_bubble_evolution",
        "bubble.promote": "promote_bubble",
        "bubble.current": "get_current_space",
        # === Idea events (from IdeasAgent) ===
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
        # Format conversion tools
        "idea.format_note": "convert_format",
        "idea.format_action_list": "convert_format",
        "idea.format_pros_cons": "convert_format",
        "idea.format_hierarchy": "convert_format",
        "idea.format_specs": "convert_format",
        "idea.convert_format": "convert_format",
        "idea.list_formats": "list_available_formats",
        # Figma-inspired formats
        "idea.format_kanban": "convert_format",
        "idea.format_mindmap": "convert_format",
        "idea.format_swot": "convert_format",
        "idea.format_user_story": "convert_format",
        "idea.format_flowchart": "convert_format",
        # Advanced AI tools
        "idea.summarize": "summarize_idea",
        "idea.whitepaper": "generate_white_paper",
        "idea.white_paper": "generate_white_paper",
        "idea.expand": "expand_ideas",
        "idea.explain": "explain_idea",
        # Exploration (AI-Scientist Tree Search)
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
        # One-Shot Exploration (Paper + Requirements + Connections)
        "idea.explore.complete": "explore_bubble_complete",
        "idea.analyze.complete": "explore_bubble_complete",
        "idea.paper.generate": "explore_bubble_complete",
    }

    # --- Merged PARAM_MAPPING from IdeasAgent + BubblesAgent ---
    PARAM_MAPPING = {
        # === Bubble param mappings ===
        "bubble.create": {
            "bubble_name": "title",
            "name": "title",
            "space": "title",
            "space_name": "title",
        },
        "bubble.enter": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.delete": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.delete_all_except": {
            "ausnahme": "exceptions",
            "ausnahmen": "exceptions",
            "behalten": "keep",
            "keep": "exceptions",
            "au\u00dfer": "exceptions",
            "ausser": "exceptions",
            "bubble_name": "exceptions",
            "title": "exceptions",
        },
        "bubble.find": {
            "title": "query",
            "name": "query",
            "space": "query",
            "space_name": "query",
            "search": "query",
        },
        "bubble.stats": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.score": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.evaluate": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.promote": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.update": {
            "title": "new_title",
            "name": "new_title",
            "neuer_name": "new_title",
            "description": "new_description",
            "beschreibung": "new_description",
        },
        # === Idea param mappings ===
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
        # Format conversion param mappings
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
        # Exploration param mappings
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
        # One-Shot Exploration param mappings
        "idea.explore.complete": {
            "id": "bubble_id",
            "bubble": "bubble_id",
            "space": "bubble_id",
            "typ": "output_type",
            "type": "output_type",
            "ausgabe": "output_type",
            "modus": "exploration_mode",
            "mode": "exploration_mode",
            "tiefe": "depth",
            "journal": "target_journal",
            "stil": "citation_style",
            "style": "citation_style",
        },
        "idea.analyze.complete": {
            "id": "bubble_id",
            "bubble": "bubble_id",
            "space": "bubble_id",
            "_inject": {"output_type": "all"},
        },
        "idea.paper.generate": {
            "id": "bubble_id",
            "bubble": "bubble_id",
            "space": "bubble_id",
            "_inject": {"output_type": "paper"},
        },
    }

    @property
    def name(self) -> str:
        return "ideas_agent"

    @property
    def domain_prefixes(self) -> Set[str]:
        return {"idea.", "bubble."}

    @property
    def profiling_perspective(self) -> str:
        return (
            "Ideas/Wissensmanagement: Gedankenorganisation, Themen-Muster, "
            "Format-Praeferenzen, kreative Arbeitsgewohnheiten, "
            "Verbindungsdenken, Wissensstrukturierung"
        )

    def _load_tools(self) -> Dict[str, Callable]:
        """Load merged bubble + idea + exploration tools."""
        tools = {}

        # --- Bubble tools ---
        try:
            from spaces.ideas.adapted.bubble_tools import (
                list_bubbles,
                create_bubble,
                enter_bubble,
                exit_bubble,
                delete_bubble,
                delete_all_bubbles_except,
                get_bubble_stats,
                score_bubble,
                evaluate_bubble_evolution,
                promote_bubble,
                update_bubble,
            )
            from tools.bubble_tools import find_bubble
            from tools.idea_tools import get_current_space

            tools.update({
                "list_bubbles": list_bubbles,
                "create_bubble": create_bubble,
                "enter_bubble": enter_bubble,
                "exit_bubble": exit_bubble,
                "delete_bubble": delete_bubble,
                "delete_all_bubbles_except": delete_all_bubbles_except,
                "update_bubble": update_bubble,
                "find_bubble": find_bubble,
                "get_bubble_stats": get_bubble_stats,
                "score_bubble": score_bubble,
                "evaluate_bubble_evolution": evaluate_bubble_evolution,
                "promote_bubble": promote_bubble,
                "get_current_space": get_current_space,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} bubble tools")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load bubble tools: {e}")

        # --- Idea tools ---
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
                "format_idea_as_table": format_idea_as_table,
                "summarize_idea": summarize_idea,
                "generate_white_paper": generate_white_paper,
                "expand_ideas": expand_ideas,
                "analyze_and_suggest_links": analyze_and_suggest_links,
                "explain_idea": explain_idea,
            })
            logger.info(f"{self.name}: Loaded idea tools, total: {len(tools)}")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load idea tools: {e}")

        # --- Format dispatcher tools ---
        try:
            from tools.format_dispatcher import convert_format, list_available_formats
            tools.update({
                "convert_format": convert_format,
                "list_available_formats": list_available_formats,
            })
            logger.info(f"{self.name}: Loaded format dispatcher tools")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load format tools: {e}")

        # --- Exploration tools ---
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
            logger.info(f"{self.name}: Loaded exploration tools, total: {len(tools)}")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load exploration tools: {e}")

        return tools


# --- Singleton ---

_ideas_broadcast_agent: Optional[IdeasBroadcastAgent] = None


def get_ideas_broadcast_agent() -> IdeasBroadcastAgent:
    """Get or create IdeasBroadcastAgent singleton."""
    global _ideas_broadcast_agent
    if _ideas_broadcast_agent is None:
        _ideas_broadcast_agent = IdeasBroadcastAgent()
    return _ideas_broadcast_agent


__all__ = ["IdeasBroadcastAgent", "get_ideas_broadcast_agent"]
