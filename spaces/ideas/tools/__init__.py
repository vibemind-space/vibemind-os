"""
VibeMind Ideas Space Tools

Tools for bubble and idea management.
Local implementations with backward-compatible re-exports.

MIGRATED FROM: tools/bubble_tools.py, tools/idea_tools.py, tools/summary_tools.py
           swarm/tools/exploration_tools.py
"""

# =============================================================================
# BUBBLE TOOLS (migrated - local implementation)
# =============================================================================
from .bubble_tools import (
    # Bubble management
    list_bubbles,
    find_bubble,
    create_bubble,
    update_bubble,
    get_bubble_stats,
    score_bubble,
    evaluate_bubble_evolution,
    promote_bubble,
    delete_bubble,
    delete_all_bubbles_except,
    enter_bubble,
    exit_bubble,
    # Utilities
    generate_bubble_embeddings,
    get_pending_agent_switch,
    get_current_bubble_db_id,
    get_current_bubble,
    # Registry
    BUBBLE_TOOLS,
    register_bubble_tools,
)

# =============================================================================
# IDEA TOOLS (migrated - local implementation)
# =============================================================================
from .idea_tools import (
    # Core idea tools
    list_ideas,
    count_ideas,
    create_idea,
    create_idea_batch,
    add_image,
    find_idea,
    update_idea,
    classify_idea,
    delete_idea,
    get_current_space,
    # Connection tools
    connect_ideas,
    disconnect_ideas,
    connect_ideas_multi,
    link_idea_to_root,
    # AI-powered tools
    expand_ideas,
    auto_link_ideas,
    analyze_and_suggest_links,
    explain_idea,
    # Movement
    move_idea,
    # Formatting
    format_idea_as_table,
    # Registry
    IDEA_TOOLS,
    register_idea_tools,
    # Helpers
    _fuzzy_find_idea,
    _get_available_idea_names,
    calculate_spiral_position,
)

# =============================================================================
# SUMMARY TOOLS (migrated - local implementation)
# =============================================================================
from .summary_tools import (
    # Client tools
    summarize_idea,
    list_summaries,
    get_summary,
    generate_white_paper,
    generate_project_structure,
    generate_feature_docs,
    submit_to_req_orchestrator,
    get_requirement_clarifications,
    sync_shuttle_from_orchestrator,
    create_stage_shuttles,
    generate_project_doc,
    # Helper functions
    _fetch_orchestrator_project_state,
    # Registry
    SUMMARY_TOOLS,
    register_summary_tools,
)

# =============================================================================
# EXPLORATION TOOLS (migrated - local implementation)
# =============================================================================
from .exploration_tools import (
    # Core exploration functions
    start_exploration,
    stop_exploration,
    get_exploration_status,
    accept_connection,
    reject_connection,
    explore_deeper,
    visualize_exploration,
    respond_to_exploration_question,
    set_exploration_direction,
    # Paper/Research functions
    parse_bubble_content_for_paper,
    generate_requirements_from_sections,
    optimize_paper_coherence,
    generate_complete_research_paper,
    explore_bubble_complete,
    conduct_autogen_research,
    # Registry
    get_exploration_tools,
    EXPLORATION_TOOLS,
)

__all__ = [
    # Bubble Tools (migrated)
    "list_bubbles",
    "find_bubble",
    "create_bubble",
    "update_bubble",
    "get_bubble_stats",
    "score_bubble",
    "evaluate_bubble_evolution",
    "promote_bubble",
    "delete_bubble",
    "delete_all_bubbles_except",
    "enter_bubble",
    "exit_bubble",
    "generate_bubble_embeddings",
    "get_pending_agent_switch",
    "get_current_bubble_db_id",
    "get_current_bubble",
    "BUBBLE_TOOLS",
    "register_bubble_tools",
    # Idea Tools (migrated)
    "list_ideas",
    "count_ideas",
    "create_idea",
    "create_idea_batch",
    "add_image",
    "find_idea",
    "update_idea",
    "classify_idea",
    "connect_ideas",
    "disconnect_ideas",
    "connect_ideas_multi",
    "link_idea_to_root",
    "delete_idea",
    "get_current_space",
    "expand_ideas",
    "move_idea",
    "auto_link_ideas",
    "analyze_and_suggest_links",
    "explain_idea",
    "format_idea_as_table",
    "IDEA_TOOLS",
    "register_idea_tools",
    "_fuzzy_find_idea",
    "_get_available_idea_names",
    "calculate_spiral_position",
    # Summary Tools (migrated)
    "summarize_idea",
    "list_summaries",
    "get_summary",
    "generate_white_paper",
    "generate_project_structure",
    "generate_feature_docs",
    "submit_to_req_orchestrator",
    "get_requirement_clarifications",
    "sync_shuttle_from_orchestrator",
    "create_stage_shuttles",
    "generate_project_doc",
    "_fetch_orchestrator_project_state",
    "SUMMARY_TOOLS",
    "register_summary_tools",
    # Exploration Tools (migrated)
    "start_exploration",
    "stop_exploration",
    "get_exploration_status",
    "accept_connection",
    "reject_connection",
    "explore_deeper",
    "visualize_exploration",
    "respond_to_exploration_question",
    "set_exploration_direction",
    "parse_bubble_content_for_paper",
    "generate_requirements_from_sections",
    "optimize_paper_coherence",
    "generate_complete_research_paper",
    "explore_bubble_complete",
    "conduct_autogen_research",
    "get_exploration_tools",
    "EXPLORATION_TOOLS",
]
