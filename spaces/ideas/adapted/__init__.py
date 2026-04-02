"""
VibeMind Ideas Space - Adapted Tools for AutoGen Swarm

Typed wrappers around Dict-based tools for use as FunctionTool in AssistantAgent.
"""

from .bubble_tools import (
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
    BUBBLE_TOOLS,
)

from .idea_tools import (
    list_ideas,
    count_ideas,
    create_idea,
    add_image,
    find_idea,
    update_idea,
    delete_idea,
    move_idea,
    connect_ideas,
    disconnect_ideas,
    connect_ideas_multi,
    link_idea_to_root,
    classify_idea,
    get_current_space,
    auto_link_ideas,
    format_idea_as_table,
    summarize_idea,
    generate_white_paper,
    expand_ideas,
    analyze_and_suggest_links,
    explain_idea,
    IDEA_TOOLS,
)

__all__ = [
    # Bubble tools
    "list_bubbles",
    "create_bubble",
    "enter_bubble",
    "exit_bubble",
    "delete_bubble",
    "delete_all_bubbles_except",
    "get_bubble_stats",
    "score_bubble",
    "evaluate_bubble_evolution",
    "promote_bubble",
    "update_bubble",
    "BUBBLE_TOOLS",
    # Idea tools
    "list_ideas",
    "count_ideas",
    "create_idea",
    "add_image",
    "find_idea",
    "update_idea",
    "delete_idea",
    "move_idea",
    "connect_ideas",
    "disconnect_ideas",
    "connect_ideas_multi",
    "link_idea_to_root",
    "classify_idea",
    "get_current_space",
    "auto_link_ideas",
    "format_idea_as_table",
    "summarize_idea",
    "generate_white_paper",
    "expand_ideas",
    "analyze_and_suggest_links",
    "explain_idea",
    "IDEA_TOOLS",
]
