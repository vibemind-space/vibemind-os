"""
Adapted Bubble Tools for AutoGen Swarm

Typed wrappers around the original Dict-based bubble tools.
These can be used directly as FunctionTool in AssistantAgent.
"""

from typing import Optional
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add python/ root to path (4 levels up from spaces/ideas/adapted/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def list_bubbles() -> str:
    """
    List all spaces/bubbles in the multiverse.

    Returns:
        Formatted list of bubbles with scores
    """
    from spaces.ideas.tools.bubble_tools import list_bubbles as _list_bubbles
    return _list_bubbles({})


def create_bubble(title: str = None, description: str = "") -> str:
    """
    Create a new bubble/space in the multiverse.

    Args:
        title: Name for the new space (required)
        description: Optional description

    Returns:
        Confirmation message
    """
    if not title:
        return "Error: No Space name provided. Please tell me what the Space should be called."
    from spaces.ideas.tools.bubble_tools import create_bubble as _create_bubble
    return _create_bubble({"title": title, "description": description})


def enter_bubble(bubble_name: str = None) -> str:
    """
    Enter a bubble/space to work on ideas inside it.

    Args:
        bubble_name: Name of the bubble to enter

    Returns:
        Confirmation message
    """
    if not bubble_name:
        return "Error: No Space name. Please tell me which Space to enter."
    from spaces.ideas.tools.bubble_tools import enter_bubble as _enter_bubble
    return _enter_bubble({"bubble_name": bubble_name})


def exit_bubble() -> str:
    """
    Exit current bubble and return to multiverse view.

    Returns:
        Confirmation message
    """
    from spaces.ideas.tools.bubble_tools import exit_bubble as _exit_bubble
    return _exit_bubble({})


def delete_bubble(bubble_name: str = None, _targets: list = None, _target_type: str = None) -> str:
    """
    Delete a bubble/space and all its content.

    Args:
        bubble_name: Name of bubble to delete
        _targets: List of bubble names to delete (from context resolution)
        _target_type: "all" if deleting multiple items from context

    Returns:
        Confirmation message
    """
    from spaces.ideas.tools.bubble_tools import delete_bubble as _delete_bubble

    # Handle batch deletion from context resolution
    if _targets and _target_type == "all":
        deleted = []
        failed = []
        for target in _targets:
            try:
                result = _delete_bubble({"bubble_name": target})
                if "gelöscht" in result.lower() or "deleted" in result.lower():
                    deleted.append(target)
                else:
                    failed.append(target)
            except Exception as e:
                failed.append(f"{target} ({e})")

        if deleted:
            msg = f"Deleted {len(deleted)} Spaces: {', '.join(deleted)}."
            if failed:
                msg += f" Failed: {', '.join(failed)}."
            return msg
        elif failed:
            return f"Could not delete any Spaces. Failed: {', '.join(failed)}."
        else:
            return "No Spaces found to delete."

    # Single bubble deletion
    if not bubble_name:
        return "Error: No Space name. Please tell me which Space to delete."
    return _delete_bubble({"bubble_name": bubble_name})


def delete_all_bubbles_except(exceptions: str = None, keep: str = None) -> str:
    """
    Delete all bubbles/spaces EXCEPT the specified ones.

    Voice triggers:
    - "Lösche alle Bubbles außer debug information"
    - "Delete all spaces except VibeMind"

    Args:
        exceptions: Bubble names to keep (comma-separated or single)
        keep: Alternative parameter name for exceptions

    Returns:
        Summary of what was deleted
    """
    from spaces.ideas.tools.bubble_tools import delete_all_bubbles_except as _delete_all_except

    # Try to get exceptions from session context if not provided
    if not exceptions and not keep:
        try:
            from swarm.context.session_context import get_session_context
            ctx = get_session_context()
            # Check user input for "außer X" pattern
            import re
            user_input = ctx.user_input or ""
            match = re.search(r'außer\s+["\']?([^"\']+)["\']?', user_input, re.IGNORECASE)
            if match:
                exceptions = match.group(1).strip()
        except Exception:
            pass

    params = {}
    if exceptions:
        params["exceptions"] = exceptions
    elif keep:
        params["exceptions"] = keep
    return _delete_all_except(params)


def get_bubble_stats(bubble_name: str = "") -> str:
    """
    Get statistics about a bubble (note count, connections, score).

    Args:
        bubble_name: Name of bubble to check (optional, uses current if empty)

    Returns:
        Statistics string
    """
    from spaces.ideas.tools.bubble_tools import get_bubble_stats as _get_bubble_stats
    return _get_bubble_stats({"bubble_name": bubble_name})


def score_bubble(bubble_name: str = "") -> str:
    """
    Calculate and update bubble score based on content richness.

    Args:
        bubble_name: Name of bubble to score (optional, uses current if empty)

    Returns:
        Score breakdown
    """
    from spaces.ideas.tools.bubble_tools import score_bubble as _score_bubble
    return _score_bubble({"bubble_name": bubble_name})


def evaluate_bubble_evolution(bubble_name: str = "") -> str:
    """
    Evaluate how evolved/complete a bubble's ideas are using AI analysis.

    Args:
        bubble_name: Name of bubble to evaluate (optional, uses current if empty)

    Returns:
        AI evaluation with scores and recommendations
    """
    from spaces.ideas.tools.bubble_tools import evaluate_bubble_evolution as _evaluate
    return _evaluate({"bubble_name": bubble_name})


def promote_bubble(bubble_name: str = "") -> str:
    """
    Promote a bubble/idea to a project.

    Args:
        bubble_name: Name of bubble to promote (optional, uses current if empty)

    Returns:
        Confirmation message
    """
    from spaces.ideas.tools.bubble_tools import promote_bubble as _promote_bubble
    return _promote_bubble({"bubble_name": bubble_name})


def update_bubble(bubble_name: str = "", new_title: str = "", new_description: str = "") -> str:
    """
    Update a bubble's title or description.

    Voice triggers: "Benenne den Space um", "Aendere den Namen zu X",
                   "Update den Bubble-Namen"

    Args:
        bubble_name: Current name of the bubble (optional - uses current if empty)
        new_title: New title for the bubble
        new_description: New description for the bubble

    Returns:
        Confirmation message
    """
    if not new_title and not new_description:
        return "Error: Please tell me the new name or description."
    from spaces.ideas.tools.bubble_tools import update_bubble as _update_bubble
    return _update_bubble({
        "bubble_name": bubble_name,
        "new_title": new_title,
        "new_description": new_description
    })


# Collect all tools for export
BUBBLE_TOOLS = [
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
]


__all__ = [
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
]
