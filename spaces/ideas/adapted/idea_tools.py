"""
Adapted Idea Tools for AutoGen Swarm

Typed wrappers around the original Dict-based idea/note tools.
These can be used directly as FunctionTool in AssistantAgent.
"""

from typing import Optional, List
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add python/ root to path (4 levels up from spaces/ideas/adapted/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def list_ideas() -> str:
    """
    List all notes/ideas in the current bubble/space.

    Must be inside a bubble first (use enter_bubble).

    Returns:
        Formatted list of notes in current bubble
    """
    from spaces.ideas.tools.idea_tools import list_ideas as _list_ideas
    return _list_ideas({})


def create_idea(title: str = None, content: str = "", type: str = "note") -> str:
    """
    Create a new note/idea in the current bubble.

    Args:
        title: Short title for the note (required)
        content: Full content/description (optional)
        type: Type of node - 'idea', 'note', 'link', 'image' (default: 'note')

    Returns:
        Confirmation message
    """
    if not title:
        return "Error: No title provided. Please tell me what the idea should be called."
    from spaces.ideas.tools.idea_tools import create_idea as _create_idea
    return _create_idea({"title": title, "content": content, "type": type})


def add_image(url: str = None, title: str = "Image") -> str:
    """
    Add an image to the current bubble/space.

    Args:
        url: URL of the image (required)
        title: Caption/title for the image (optional)

    Returns:
        Confirmation message
    """
    if not url:
        return "Error: No URL provided. Please tell me which image to add."
    from spaces.ideas.tools.idea_tools import add_image as _add_image
    return _add_image({"url": url, "title": title})


def find_idea(query: str = None) -> str:
    """
    Search for notes matching a query.

    Args:
        query: Search text

    Returns:
        Matching notes or 'no matches'
    """
    if not query:
        return "Error: No search term provided. Please tell me what to search for."
    from spaces.ideas.tools.idea_tools import find_idea as _find_idea
    return _find_idea({"query": query})


def update_idea(idea_name: str = None, new_content: str = "", new_title: str = "") -> str:
    """
    Update an existing note/idea.

    Args:
        idea_name: Name/title of the idea to update
        new_content: New content (optional)
        new_title: New title (optional)

    Returns:
        Confirmation message
    """
    if not idea_name:
        return "Error: No idea name. Please tell me which idea to update."
    from spaces.ideas.tools.idea_tools import update_idea as _update_idea
    return _update_idea({
        "idea_name": idea_name,
        "new_content": new_content,
        "new_title": new_title,
    })


def connect_ideas(idea1: str = None, idea2: str = None) -> str:
    """
    Connect two ideas with an edge/link.

    Args:
        idea1: First idea name
        idea2: Second idea name

    Returns:
        Confirmation message
    """
    if not idea1 or not idea2:
        return "Error: Two idea names needed. Please tell me which ideas to connect."
    from spaces.ideas.tools.idea_tools import connect_ideas as _connect_ideas
    return _connect_ideas({"idea1": idea1, "idea2": idea2})


def disconnect_ideas(idea1: str = None, idea2: str = None) -> str:
    """
    Disconnect/unlink two ideas by removing their edge.

    Voice triggers: "Trenne Tools von Frontend", "Entferne Verbindung"

    Args:
        idea1: First idea name
        idea2: Second idea name

    Returns:
        Confirmation message
    """
    if not idea1 or not idea2:
        return "Error: Two idea names needed. Please tell me which connection to remove."
    from spaces.ideas.tools.idea_tools import disconnect_ideas as _disconnect_ideas
    return _disconnect_ideas({"idea1": idea1, "idea2": idea2})


def delete_idea(idea_name: str = None) -> str:
    """
    Delete a note/idea.

    Args:
        idea_name: Name of idea to delete

    Returns:
        Confirmation message
    """
    if not idea_name:
        return "Error: No idea name. Please tell me which idea to delete."
    from spaces.ideas.tools.idea_tools import delete_idea as _delete_idea
    return _delete_idea({"idea_name": idea_name})


def get_current_space() -> str:
    """
    Get information about current location (which bubble/space).

    Returns:
        Current location description
    """
    from spaces.ideas.tools.idea_tools import get_current_space as _get_current_space
    return _get_current_space({})


def auto_link_ideas(threshold: float = 0.5, max_links: int = 10) -> str:
    """
    Automatically analyze all ideas in current bubble and create links
    between semantically related pairs using embedding similarity.

    Voice triggers: "Verlinke die Ideen sinnvoll", "Link related ideas",
                   "Verbinde ähnliche Notizen automatisch"

    Args:
        threshold: Minimum similarity score (0-1), default 0.5
        max_links: Maximum number of links to create, default 10

    Returns:
        Summary of created links
    """
    from spaces.ideas.tools.idea_tools import auto_link_ideas as _auto_link_ideas
    return _auto_link_ideas({"threshold": threshold, "max_links": max_links})


def format_idea_as_table(
    idea_name: str = None,
    custom_columns: List[str] = None,
    format_instruction: str = ""
) -> str:
    """
    Format an existing idea's content into a structured table.

    Voice triggers: "Formatiere die Idee X als Tabelle",
                   "Erstelle eine Tabelle aus der Idee X",
                   "Mach eine Tabelle mit Spalten X, Y, Z"

    Args:
        idea_name: Name/title of the idea to format (required)
        custom_columns: Optional custom column headers (e.g., ["Calls ID", "Requirement", "Content"])
        format_instruction: Optional formatting instruction

    Returns:
        Confirmation with table preview
    """
    if not idea_name:
        return "Error: No idea name. Please tell me which idea to format."
    from tools.structured_formatting_tools import format_idea_as_table as _format_idea_as_table
    return _format_idea_as_table(
        idea_name=idea_name,
        custom_columns=custom_columns,
        format_instruction=format_instruction
    )


def summarize_idea(idea_name: str = None, style: str = "concise") -> str:
    """
    Summarize a specific idea or the current bubble using AI.

    Voice triggers: "Fasse die Idee zusammen", "Erstelle eine Zusammenfassung",
                   "Summarize this idea"

    Args:
        idea_name: Name of the idea to summarize (optional - uses current bubble if not specified)
        style: Summary style - "concise", "detailed", "actionable" (default: "concise")

    Returns:
        AI-generated summary of the idea
    """
    from spaces.ideas.tools.summary_tools import summarize_idea as _summarize_idea
    return _summarize_idea({"idea_name": idea_name, "style": style})


def generate_white_paper(start_node: str = None, task: str = "project overview", max_depth: int = 5) -> str:
    """
    Generate a structured White Paper document from linked ideas using graph traversal.

    Voice triggers: "Erstelle ein Whitepaper", "Generiere eine Projektübersicht",
                   "Mach ein White Paper aus den Ideen"

    Args:
        start_node: Name of the idea to start from (uses first idea if not specified)
        task: Description of what kind of document to create (default: "project overview")
        max_depth: Maximum graph traversal depth (default: 5)

    Returns:
        Structured White Paper document
    """
    from spaces.ideas.tools.summary_tools import generate_white_paper as _generate_white_paper
    return _generate_white_paper({"start_node": start_node, "task": task, "max_depth": max_depth})


def expand_ideas(idea_name: str = None, count: int = 3) -> str:
    """
    Expand existing ideas using AI to generate related concepts.

    Voice triggers: "Erweitere die Ideen", "Generiere verwandte Ideen",
                   "Mach mehr Ideen aus den bestehenden"

    Args:
        idea_name: Optional - specific idea to expand (uses all ideas if not specified)
        count: Number of ideas to generate (default: 3)

    Returns:
        Summary of newly generated ideas
    """
    from spaces.ideas.tools.idea_tools import expand_ideas as _expand_ideas
    return _expand_ideas({"source_idea": idea_name, "count": count})


def analyze_and_suggest_links() -> str:
    """
    Analyze all ideas in current bubble and suggest meaningful links
    WITHOUT creating them. User can confirm to create links.

    Voice triggers: "Analysiere die Ideen", "Schlage Verlinkungen vor",
                   "Welche Ideen gehören zusammen"

    Returns:
        Top 5 suggested link pairs with reasoning
    """
    from spaces.ideas.tools.idea_tools import analyze_and_suggest_links as _analyze_and_suggest_links
    return _analyze_and_suggest_links({})


def explain_idea(idea_name: str) -> str:
    """
    Explain what an idea is about using AI analysis.

    Voice triggers: "Erkläre die Idee X", "Was bedeutet X?", "Explain the idea X"

    Args:
        idea_name: Name of the idea to explain (fuzzy matched)

    Returns:
        AI-generated explanation of the idea
    """
    from spaces.ideas.tools.idea_tools import explain_idea as _explain_idea
    return _explain_idea({"idea_name": idea_name})


def count_ideas() -> str:
    """
    Count the number of ideas/notes in the current bubble/space.

    Voice triggers: "Wie viele Ideen?", "How many ideas?", "Anzahl der Ideen"

    Returns:
        Count of ideas in current space
    """
    from spaces.ideas.tools.idea_tools import count_ideas as _count_ideas
    result = _count_ideas()
    if isinstance(result, dict):
        return result.get("message", str(result))
    return str(result)


def move_idea(idea_name: str = None, target_space: str = None) -> str:
    """
    Move an idea/note from the current space to another space.

    Voice triggers: "Verschiebe X nach Y", "Move idea X to space Y"

    Args:
        idea_name: Name of the idea to move (fuzzy matched)
        target_space: Name of the destination space (fuzzy matched)

    Returns:
        Confirmation or error message
    """
    if not idea_name:
        return "Error: No idea name. Please tell me which idea to move."
    if not target_space:
        return "Error: No target Space provided. Please tell me where to move the idea."
    from spaces.ideas.tools.idea_tools import move_idea as _move_idea
    return _move_idea({"idea_name": idea_name, "target_space": target_space})


def connect_ideas_multi(source: str = None, targets: list = None) -> str:
    """
    Connect one idea to multiple others by name or index.

    Voice triggers: "Verbinde 2 mit 3, 4 und 5", "Link 1 to 2, 3, 4"

    Args:
        source: Source idea (name or index)
        targets: Target ideas (list of names/indices)

    Returns:
        Confirmation message listing successful connections
    """
    if not source:
        return "Error: No source idea provided. Please tell me which idea to connect."
    if not targets:
        return "Error: No target ideas provided. Please tell me which ideas to connect with."
    from spaces.ideas.tools.idea_tools import connect_ideas_multi as _connect_ideas_multi
    return _connect_ideas_multi({"source": source, "targets": targets})


def link_idea_to_root(idea_name: str = None, bubble_id: str = None) -> str:
    """
    Link an idea to the root node of the current bubble.

    Voice triggers: "Verknüpfe das mit dem Root", "Link to root"

    Args:
        idea_name: Name of the idea to link (required)
        bubble_id: Optional bubble ID (uses current if not provided)

    Returns:
        Confirmation message
    """
    if not idea_name:
        return "Error: No idea name. Please tell me which idea to link with Root."
    from spaces.ideas.tools.idea_tools import link_idea_to_root as _link_idea_to_root
    params = {"idea_name": idea_name}
    if bubble_id:
        params["bubble_id"] = bubble_id
    return _link_idea_to_root(params)


def classify_idea(idea_name: str = None) -> str:
    """
    Classify an idea using AI backend analysis.

    Voice triggers: "Klassifiziere die Idee", "Analyze this idea"

    Args:
        idea_name: Name/title of the idea to classify

    Returns:
        Classification result
    """
    if not idea_name:
        return "Error: No idea name. Please tell me which idea to classify."
    from spaces.ideas.tools.idea_tools import classify_idea as _classify_idea
    return _classify_idea({"idea_name": idea_name})


# Collect all tools for export
IDEA_TOOLS = [
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
]


__all__ = [
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
