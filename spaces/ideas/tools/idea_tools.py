"""
Note/Canvas Content Management Tools for Conversational Memory Agent

Tools for managing notes/content INSIDE a bubble/space.
These are the CanvasNodes that live inside Ideas/Bubbles.

Architecture:
- Bubbles = Ideas (managed by bubble_tools.py)
- Notes inside bubbles = CanvasNodes (managed by THIS file)
- CanvasNodes link to their parent Idea via linked_idea_id

Tool Categories:
- list_ideas: List all notes in current bubble
- create_idea: Create a new note/canvas item
- find_idea: Search for notes
- update_idea: Update an existing note
- connect_ideas: Link two notes together
- delete_idea: Remove a note
- get_current_space: Get info about current location

MIGRATED FROM: tools/idea_tools.py
"""

import sys
import math
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging
from llm_config import get_model, get_client

logger = logging.getLogger(__name__)


# =============================================================================
# FUZZY MATCHING HELPERS
# =============================================================================

def _similarity_ratio(s1: str, s2: str) -> float:
    """
    Calculate similarity ratio between two strings using sequence matching.

    Returns a value between 0.0 and 1.0 where 1.0 means identical.
    """
    from difflib import SequenceMatcher
    return SequenceMatcher(None, s1, s2).ratio()


def _normalize_for_matching(text: str) -> str:
    """
    Normalize text for matching by removing hyphens, spaces, underscores.

    This helps match "In-Hand-Analyse" with "In Hand Analyse" or "InHandAnalyse".
    """
    import re
    return re.sub(r'[-\s_]', '', text.lower())


def _fuzzy_find_idea(nodes: List, name: str) -> Optional:
    """
    Find an idea by name with fuzzy matching.

    Tries matching in order:
    1. Exact match (case-insensitive)
    2. Normalized match (remove hyphens/spaces - finds "In-Hand-Analyse" when searching "In Hand Analyse")
    3. Substring match (name contained in title)
    4. Reverse substring (title contained in name)
    5. Fuzzy similarity match (>70% similar)

    Args:
        nodes: List of canvas nodes to search
        name: Name to search for

    Returns:
        Matching node or None
    """
    if not name:
        return None

    name_lower = name.lower().strip()
    name_normalized = _normalize_for_matching(name)

    # 1. Exact match
    for n in nodes:
        title_lower = (n.title or "").lower()
        if title_lower == name_lower:
            return n

    # 2. Normalized match (ignores hyphens, spaces, underscores)
    for n in nodes:
        title_normalized = _normalize_for_matching(n.title or "")
        if title_normalized == name_normalized:
            logger.debug(f"Normalized match: '{name}' -> '{n.title}'")
            return n

    # 3. Substring match (search term in title)
    for n in nodes:
        title_lower = (n.title or "").lower()
        if name_lower in title_lower:
            return n

    # 4. Reverse substring (title in search term - for multi-word queries)
    for n in nodes:
        title_lower = (n.title or "").lower()
        if title_lower and title_lower in name_lower:
            return n

    # 5. Fuzzy match (>70% similarity)
    best_match = None
    best_ratio = 0.0
    for n in nodes:
        title_lower = (n.title or "").lower()
        if not title_lower:
            continue
        ratio = _similarity_ratio(name_lower, title_lower)
        if ratio > best_ratio and ratio > 0.7:
            best_ratio = ratio
            best_match = n

    return best_match


def _get_available_idea_names(nodes: List, exclude: Optional = None, limit: int = 5) -> str:
    """
    Get a formatted string of available idea names for error messages.

    Args:
        nodes: List of nodes
        exclude: Node to exclude from list
        limit: Max number of names to return

    Returns:
        Comma-separated string of idea titles
    """
    names = []
    for n in nodes[:limit + 1]:
        if n != exclude and n.title:
            names.append(n.title)
        if len(names) >= limit:
            break
    return ", ".join(names) if names else "none"


def calculate_spiral_position(
    count: int,
    existing_positions: List[Tuple[float, float]],
    center_x: float = 300,
    center_y: float = 300,
    min_distance: float = 150
) -> Tuple[int, int]:
    """
    Calculate non-overlapping spiral position for a new node.

    Uses Archimedean spiral to distribute nodes outward from center,
    with collision detection to avoid overlapping existing nodes.

    Args:
        count: Number of existing nodes (determines spiral position)
        existing_positions: List of (x, y) tuples of existing nodes
        center_x: Center X coordinate
        center_y: Center Y coordinate
        min_distance: Minimum distance between nodes

    Returns:
        Tuple of (x, y) coordinates for the new node
    """
    logger.debug("calculate_spiral_position: count=%s, center=(%s,%s)", count, center_x, center_y)
    angle_step = 0.7  # radians per node (golden angle approximation)
    radius_step = 35  # pixels per loop

    # Calculate initial position on spiral
    angle = count * angle_step
    radius = 80 + (count * radius_step)

    x = center_x + radius * math.cos(angle)
    y = center_y + radius * math.sin(angle)

    # Check collision with existing positions and adjust if needed
    max_iterations = 10
    for _ in range(max_iterations):
        collision = False
        for ex_x, ex_y in existing_positions:
            distance = math.sqrt((x - ex_x) ** 2 + (y - ex_y) ** 2)
            if distance < min_distance:
                collision = True
                # Move further out on the spiral
                radius += min_distance
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
                break

        if not collision:
            break

    return int(x), int(y)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from data import CanvasRepository

# Import Electron broadcast function from workspace_tools
from tools.workspace_tools import _broadcast_to_electron

# Import the current bubble DB ID getter from local bubble_tools
from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id

# Repository instance
_canvas_repo: Optional[CanvasRepository] = None


def _get_canvas_repo() -> CanvasRepository:
    """Get or create the canvas repository."""
    global _canvas_repo
    if _canvas_repo is None:
        _canvas_repo = CanvasRepository()
    return _canvas_repo


def _get_current_bubble_id() -> Optional[str]:
    """Get the current bubble ID (database UUID) from bubble_tools state.

    Returns the Idea ID (string UUID) that corresponds to the current bubble.
    This is the DB UUID, not the local Electron int ID.
    """
    # Use the bubble_tools module-level state which is set by enter_bubble()
    return get_current_bubble_db_id()


def _get_bubble_info(bubble_id: str) -> Optional[Dict[str, Any]]:
    """Get bubble info from database by UUID.

    Args:
        bubble_id: The database UUID string of the bubble/idea

    Returns:
        Dict with 'id' and 'title' keys, or None if not found
    """
    try:
        from data import IdeasRepository
        repo = IdeasRepository()
        idea = repo.get(bubble_id)
        if idea:
            return {"id": idea.id, "title": idea.title}
        return None
    except Exception as e:
        logger.warning(f"Could not get bubble info for {bubble_id}: {e}")
        return None


# =============================================================================
# IDEA TOOLS
# =============================================================================

def list_ideas(params: Dict[str, Any]) -> str:
    """
    List all NOTES (canvas items) inside the current space/bubble.

    NOT to be confused with list_bubbles which shows spaces in the multiverse.
    This tool shows the CONTENT inside the current space you are in.

    Voice triggers: "What notes do I have here?", "Show my ideas in this space",
                   "List notes", "What's in this bubble?"

    IMPORTANT: User must be inside a space first. If in multiverse view,
    this returns "Enter a space first".

    Returns:
        str: Formatted list of notes/canvas items in current bubble
    """
    bubble_id = _get_current_bubble_id()

    logger.info("=" * 50)
    logger.info(">>> list_ideas() CALLED <<<")
    logger.info(f"    bubble_id = {bubble_id}")
    logger.info(f"    Tool purpose: Show NOTES inside current bubble (NOT spaces)")
    logger.info("=" * 50)

    if bubble_id is None:
        logger.info("    Result: User is in multiverse view, no bubble entered")
        return "You're in the multiverse view. Enter a space first to see its notes. Use 'list bubbles' to see available spaces."

    repo = _get_canvas_repo()

    # Get all nodes and filter by linked_idea_id
    all_nodes = repo.list_nodes(limit=1000)
    nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]

    logger.info(f"    Total nodes in DB: {len(all_nodes)}")
    logger.info(f"    Nodes linked to bubble {bubble_id}: {len(nodes)}")
    for n in nodes[:5]:
        logger.info(f"      - {n.title or 'Untitled'} (id: {n.id[:8]}...)")

    if not nodes:
        return "This space is empty. Would you like me to add a note? Say 'Add a note about...'."

    # Store mapping for index-based voice referencing
    from tools.index_mapping import set_idea_mapping
    set_idea_mapping(nodes[:10], bubble_id)

    # Get titles or first 30 chars of content (with numbering for voice reference)
    titles = []
    indexed_ideas = []
    for i, n in enumerate(nodes[:10], 1):
        title = n.title or (n.content[:30] if n.content else "Untitled")
        titles.append(f"{i}. {title}")
        indexed_ideas.append({
            "index": i,
            "id": n.id,
            "title": title,
            "node_type": n.node_type
        })

    # Broadcast indexed list to Electron UI so numbers are visible
    _broadcast_to_electron({
        "type": "ideas_listed",
        "ideas": indexed_ideas,
        "bubble_id": bubble_id,
        "total": len(nodes)
    })

    return f"In this space you have {len(nodes)} notes: {', '.join(titles)}. Reference by number: 'connect 1 and 2' or 'add to 3'."


def count_ideas(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Count the number of ideas/notes in the current space.

    Voice triggers: "How many ideas do I have?", "Wie viele Ideen?",
                   "Count the ideas", "Anzahl der Ideen"

    Returns:
        Dict with count, success status, and a message for voice response
    """
    bubble_id = _get_current_bubble_id()

    logger.info("=" * 50)
    logger.info(">>> count_ideas() CALLED <<<")
    logger.info(f"    bubble_id = {bubble_id}")
    logger.info("=" * 50)

    if bubble_id is None:
        logger.info("    Result: User is in multiverse view")
        return {
            "success": True,
            "count": 0,
            "message": "You are in the Multiverse. Enter a Space to count ideas."
        }

    repo = _get_canvas_repo()

    # Get all nodes and filter by linked_idea_id
    all_nodes = repo.list_nodes(limit=1000)
    count = len([n for n in all_nodes if n.linked_idea_id == bubble_id])

    logger.info(f"    Count: {count} ideas in bubble {bubble_id}")

    # Construct German message with proper grammar
    if count == 0:
        message = "There are no ideas in this Space."
    elif count == 1:
        message = "You have 1 idea in this Space."
    else:
        message = f"You have {count} ideas in this Space."

    return {
        "success": True,
        "count": count,
        "message": message
    }


def create_idea(params: Dict[str, Any]) -> str:
    """
    Create a new note in the current bubble/space.

    Voice triggers: "Add an idea about cooking", "Create a note for Python tips"

    Args (via params):
        title: Short title for the note (required)
        content: Full content/description (optional)
        type: Type of node - "idea", "note", "link", "image" (optional, default: "note")

    Returns:
        str: Confirmation message
    """
    title = params.get("title", "").strip()
    content = params.get("content", "").strip()
    node_type = params.get("type", "note")

    if not title:
        return "What should I call this note?"

    bubble_id = _get_current_bubble_id()

    if bubble_id is None:
        return "Enter a space first before adding notes."

    repo = _get_canvas_repo()

    # Get existing nodes for positioning
    all_nodes = repo.list_nodes(limit=1000)
    bubble_nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    count = len(bubble_nodes)

    # Calculate spiral position to avoid overlapping
    existing_positions = [(n.x or 0, n.y or 0) for n in bubble_nodes]
    x, y = calculate_spiral_position(count, existing_positions)

    # Create node in database with linked_idea_id pointing to parent bubble
    node = repo.create_node(
        node_type=node_type,
        title=title,
        content=content or title,
        x=x,
        y=y,
        linked_idea_id=bubble_id  # Link to parent Idea/Bubble
    )

    # Broadcast to Electron UI
    _broadcast_to_electron({
        "type": "node_added",
        "bubble_id": bubble_id,
        "node": {
            "id": node.id,
            "type": node.node_type,
            "position": {"x": node.x, "y": node.y},
            "content": {"title": node.title, "text": node.content},
            "connections": []
        }
    })

    # Publish updated bubble to Rowboat
    try:
        from publishing import get_ideas_publisher
        get_ideas_publisher().publish_bubble(bubble_id=bubble_id)
    except Exception:
        pass

    logger.info(f"Created note '{title}' in bubble {bubble_id}")
    return f"Added '{title}'"


def create_idea_batch(params: Dict[str, Any]) -> str:
    """
    Create multiple ideas/notes at once via LLM generation.

    Voice triggers: "Erstelle 15 Ideen ueber Autogen", "Generiere 5 Notizen zu KI"

    Args (via params):
        topic: Theme/topic for the ideas (required)
        count: Number of ideas to create (default: 5, max: 20)

    Returns:
        str: Confirmation with list of created ideas
    """
    topic = params.get("topic", "").strip()
    count = min(int(params.get("count", 5)), 20)

    if not topic:
        return "What topic should the ideas be about?"

    bubble_id = _get_current_bubble_id()
    if bubble_id is None:
        return "Enter a Space first before creating ideas."

    # Generate idea titles via LLM
    try:
        from openai import OpenAI
        import os
        import json as _json

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return "OPENROUTER_API_KEY not set."

        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=15.0,
        )

        response = client.chat.completions.create(
            model=get_model("space_agent"),
            messages=[
                {
                    "role": "system",
                    "content": "Du generierst Ideen-Titel und kurze Beschreibungen. "
                               "Antworte NUR als JSON-Array.",
                },
                {
                    "role": "user",
                    "content": f"Generiere genau {count} verschiedene Ideen zum Thema '{topic}'. "
                               f"Antworte als JSON-Array: "
                               f'[{{"title": "...", "content": "..."}}, ...]',
                },
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        response_text = response.choices[0].message.content.strip()
        # Strip markdown code fences
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        ideas = _json.loads(response_text)
    except Exception as e:
        logger.error(f"Failed to generate ideas: {e}")
        return f"Error generating ideas: {e}"

    # Create all ideas in the current bubble
    repo = _get_canvas_repo()
    all_nodes = repo.list_nodes(limit=1000)
    bubble_nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    existing_count = len(bubble_nodes)
    existing_positions = [(n.x or 0, n.y or 0) for n in bubble_nodes]

    created = []
    for i, idea in enumerate(ideas[:count]):
        title = idea.get("title", f"Idee {i+1}")
        content = idea.get("content", title)

        x, y = calculate_spiral_position(
            existing_count + i, existing_positions
        )
        existing_positions.append((x, y))

        node = repo.create_node(
            node_type="note",
            title=title,
            content=content,
            x=x,
            y=y,
            linked_idea_id=bubble_id,
        )

        _broadcast_to_electron({
            "type": "node_added",
            "bubble_id": bubble_id,
            "node": {
                "id": node.id,
                "type": node.node_type,
                "position": {"x": node.x, "y": node.y},
                "content": {"title": node.title, "text": node.content},
                "connections": [],
            },
        })
        created.append(title)

    # Publish updated bubble
    try:
        from publishing import get_ideas_publisher
        get_ideas_publisher().publish_bubble(bubble_id=bubble_id)
    except Exception:
        pass

    logger.info(f"Batch created {len(created)} ideas in bubble {bubble_id}")
    titles_str = ", ".join(created[:5])
    if len(created) > 5:
        titles_str += f" ... and {len(created) - 5} more"
    return f"{len(created)} ideas created for '{topic}': {titles_str}"


def add_image(params: Dict[str, Any]) -> str:
    """
    Add an image to the current bubble/space.

    Voice triggers: "Add an image", "Save this picture", "Add image from URL"

    Args (via params):
        url: URL of the image (required)
        title: Caption/title for the image (optional)

    Returns:
        str: Confirmation message
    """
    url = params.get("url", "").strip()
    title = params.get("title", "").strip() or "Image"

    if not url:
        return "What's the image URL?"

    # Validate URL has image extension or is a valid URL
    if not url.startswith(("http://", "https://", "data:")):
        return "Please provide a valid image URL starting with http:// or https://"

    bubble_id = _get_current_bubble_id()

    if bubble_id is None:
        return "Enter a space first before adding images."

    repo = _get_canvas_repo()

    # Get existing nodes for positioning
    all_nodes = repo.list_nodes(limit=1000)
    bubble_nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    count = len(bubble_nodes)

    # Calculate spiral position to avoid overlapping
    existing_positions = [(n.x or 0, n.y or 0) for n in bubble_nodes]
    x, y = calculate_spiral_position(count, existing_positions)

    # Create image node in database
    node = repo.create_node(
        node_type="image",
        title=title,
        content=url,  # Store URL in content field
        x=x,
        y=y,
        linked_idea_id=bubble_id,
        metadata={"url": url, "caption": title}  # Also store in metadata
    )

    # Broadcast to Electron UI
    _broadcast_to_electron({
        "type": "node_added",
        "bubble_id": bubble_id,
        "node": {
            "id": node.id,
            "type": "image",
            "position": {"x": node.x, "y": node.y},
            "content": {"url": url, "caption": title},
            "connections": []
        }
    })

    logger.info(f"Added image '{title}' ({url[:50]}...) in bubble {bubble_id}")
    return f"Added image '{title}'"


def find_idea(params: Dict[str, Any]) -> str:
    """
    Search for notes matching a query.

    Voice triggers: "Find my notes about Python", "Search for cooking ideas"

    Args (via params):
        query: Search text (required)

    Returns:
        str: Matching notes or "no matches"
    """
    query = params.get("query", "").strip().lower()
    logger.debug("find_idea: query=%s", query)

    if not query:
        return "What would you like me to search for?"

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get all nodes
    all_nodes = repo.list_nodes(limit=1000)

    # Filter by bubble if inside one, otherwise search all
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    # Filter by query with fuzzy matching support
    query_normalized = _normalize_for_matching(query)
    matches = []
    for n in nodes:
        title_lower = (n.title or "").lower()
        content_lower = (n.content or "").lower()
        title_normalized = _normalize_for_matching(n.title or "")

        # Match if query in title, content, or normalized title matches
        if (query in title_lower or
            query in content_lower or
            query_normalized == title_normalized or
            query_normalized in title_normalized):
            matches.append(n)

    if not matches:
        # Try fuzzy match as fallback
        fuzzy_match = _fuzzy_find_idea(nodes, query)
        if fuzzy_match:
            matches = [fuzzy_match]

    if not matches:
        return f"No notes found matching '{query}'"

    titles = []
    for m in matches[:5]:
        title = m.title or (m.content[:30] if m.content else "Untitled")
        titles.append(title)

    return f"Found {len(matches)} notes: {', '.join(titles)}"


def _generate_content_for_topic(topic: str, idea_title: str) -> str:
    """
    Generate content for a topic using OpenRouter LLM.

    Args:
        topic: What to generate content about
        idea_title: Title of the idea (for context)

    Returns:
        Generated content string
    """
    try:
        from openai import OpenAI
        import os

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return f"[Could not generate content - OPENROUTER_API_KEY missing]\n\nTopic: {topic}"

        client = get_client("summary")

        model = get_model("summary")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Du bist ein hilfreicher Assistent. Generiere strukturierten, informativen Content auf Deutsch. Nutze Bullet Points und klare Struktur."
                },
                {
                    "role": "user",
                    "content": f"Erstelle Content für die Idee '{idea_title}' zum Thema: {topic}\n\nSchreibe in deutscher Sprache, strukturiert und informativ."
                }
            ],
            max_tokens=1000,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"Content generation failed: {e}")
        return f"[Content generation failed: {e}]\n\nTopic: {topic}"


def update_idea(params: Dict[str, Any]) -> str:
    """
    Update an existing idea.

    Voice triggers: "Update the cooking idea", "Change my Python note"

    Args (via params):
        idea_name: Name/title of the idea to update (required)
        new_content: New content for literal mode (optional)
        new_title: New title (optional)
        mode: "literal" (default) or "generate"
        topic: What to generate content about (when mode="generate")

    Returns:
        str: Confirmation message
    """
    idea_name = params.get("idea_name", "").strip().lower()
    new_content = params.get("new_content", "").strip()
    new_title = params.get("new_title", "").strip()
    mode = params.get("mode", "literal")
    topic = params.get("topic", "").strip()

    if not idea_name:
        return "Which idea should I update?"

    # For generate mode, we need a topic instead of new_content
    if mode == "generate" and not topic:
        return "What should I generate? Please provide a topic."

    # For literal mode, we need new_content or new_title
    if mode != "generate" and not new_content and not new_title:
        return "What should I change it to?"

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    # Find matching node using fuzzy matching (handles "In-Hand-Analyse" vs "In Hand Analyse")
    match = _fuzzy_find_idea(nodes, idea_name)

    if not match:
        available = _get_available_idea_names(nodes)
        return f"Couldn't find an idea called '{idea_name}'. Available: {available}"

    # Update
    if new_title:
        match.title = new_title

    # Handle content based on mode
    if mode == "generate":
        # Generate content using LLM
        logger.info(f"Generating content for '{match.title}' with topic: {topic}")
        generated_content = _generate_content_for_topic(topic, match.title)
        match.content = generated_content
        logger.info(f"Generated {len(generated_content)} chars of content")
    elif new_content:
        # Literal mode - use provided content directly
        match.content = new_content

    repo.update_node(match)

    # Broadcast update
    _broadcast_to_electron({
        "type": "node_updated",
        "node_id": match.id,
        "updates": {
            "title": match.title,
            "content": {
                "title": match.title,
                "text": match.content
            }
        }
    })

    logger.info(f"Updated idea '{match.title}'")
    return f"Updated '{match.title}'"


def classify_idea(params: Dict[str, Any]) -> str:
    """
    Classify an idea using AI backend analysis.

    Voice triggers: "Klassifiziere die Idee", "Send to backend", "Analyze this idea"

    Args (via params):
        idea_name: Name/title of the idea to classify (optional - uses current if not specified)

    Returns:
        str: Classification result
    """
    idea_name = params.get("idea_name", "").strip().lower()

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes in current bubble
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    if not nodes:
        return "No ideas found to classify."

    # Find specific idea or use first one
    if idea_name:
        match = _fuzzy_find_idea(nodes, idea_name)
        if not match:
            available = _get_available_idea_names(nodes)
            return f"Idea '{idea_name}' not found. Available: {available}"
    else:
        # Use root node or first node
        match = nodes[0]
        for n in nodes:
            if n.title and "root" in n.title.lower():
                match = n
                break

    # Call backend for classification
    try:
        from openai import OpenAI
        import os

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return f"Classification not possible - OPENROUTER_API_KEY missing. Idea: {match.title}"

        client = get_client("summary")

        model = get_model("summary")

        # Build content for classification
        content_text = f"Titel: {match.title}\n\nInhalt: {match.content or 'Kein Inhalt'}"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """Du bist ein Klassifizierungs-Assistent. Analysiere die Idee und gib zurueck:
1. Kategorie (z.B. Projekt, Aufgabe, Notiz, Feature, Bug, Frage, Konzept)
2. Prioritaet (Hoch, Mittel, Niedrig)
3. Stichwoerter (3-5 relevante Tags)
4. Naechster Schritt (eine konkrete Empfehlung)

Antworte kurz und strukturiert auf Deutsch."""
                },
                {
                    "role": "user",
                    "content": f"Klassifiziere folgende Idee:\n\n{content_text}"
                }
            ],
            max_tokens=300,
            temperature=0.3
        )

        classification = response.choices[0].message.content.strip()
        logger.info(f"Classified idea '{match.title}'")

        return f"Classification for '{match.title}':\n\n{classification}"

    except Exception as e:
        logger.warning(f"Classification failed: {e}")
        return f"Classification failed: {e}"


def connect_ideas(params: Dict[str, Any]) -> str:
    """
    Connect two ideas with an edge.

    Voice triggers: "Link cooking to recipes", "Connect Python to coding",
                   "Verbinde Marketing mit Social Media"

    Args (via params):
        idea1 / source: First idea name (fuzzy matched)
        idea2 / target: Second idea name (fuzzy matched)

    Returns:
        str: Confirmation message or helpful error with available ideas
    """
    # Support both parameter naming conventions
    idea1 = params.get("idea1", params.get("source", "")).strip()
    idea2 = params.get("idea2", params.get("target", "")).strip()

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes in current bubble
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    # If no ideas provided or very few, show available ideas
    if not idea1 or not idea2:
        if not nodes:
            return "This Space has no ideas yet. Create some ideas first."
        available = _get_available_idea_names(nodes, limit=5)
        return f"Which ideas should I connect? Available: {available}"

    # Helper: Resolve numeric index (e.g., "1", "2") or fuzzy match
    def resolve_idea(ref: str):
        # Check for numeric reference (matches list_ideas() numbering)
        ref_clean = ref.strip().rstrip('.')
        if ref_clean.isdigit():
            idx = int(ref_clean) - 1  # 1-based to 0-based
            if 0 <= idx < len(nodes):
                return nodes[idx]
            return None
        # Fall back to fuzzy matching
        return _fuzzy_find_idea(nodes, ref)

    # Find both nodes using numeric index or fuzzy matching
    node1 = resolve_idea(idea1)
    node2 = resolve_idea(idea2)

    # Helpful error messages with available ideas
    if not node1:
        available = _get_available_idea_names(nodes, limit=5)
        return f"'{idea1}' not found. Available ideas: {available}"

    if not node2:
        available = _get_available_idea_names(nodes, exclude=node1, limit=5)
        return f"'{idea2}' not found. Available ideas: {available}"

    # Don't connect an idea to itself
    if node1.id == node2.id:
        return f"'{node1.title}' cannot be connected to itself."

    # Create edge
    edge = repo.create_edge(node1.id, node2.id, "related")

    # Broadcast
    _broadcast_to_electron({
        "type": "edge_added",
        "edge": {
            "from_node_id": node1.id,
            "to_node_id": node2.id,
            "label": "related"
        }
    })

    logger.info(f"Connected '{node1.title}' to '{node2.title}'")
    return f"'{node1.title}' and '{node2.title}' are now connected."


def disconnect_ideas(params: Dict[str, Any]) -> str:
    """
    Disconnect/unlink two ideas by removing their edge.

    Voice triggers: "Trenne Tools von Frontend", "Entferne Verbindung zwischen X und Y",
                   "Disconnect A from B", "Unlink these ideas"

    Args (via params):
        idea1 / source / from_idea: First idea name (fuzzy matched)
        idea2 / target / to_idea: Second idea name (fuzzy matched)

    Returns:
        str: Confirmation message or error if not connected
    """
    # Support multiple parameter naming conventions
    idea1 = (
        params.get("idea1") or
        params.get("source") or
        params.get("from_idea") or
        params.get("von") or
        ""
    ).strip()

    idea2 = (
        params.get("idea2") or
        params.get("target") or
        params.get("to_idea") or
        params.get("zu") or
        ""
    ).strip()

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes in current bubble
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    # If no ideas provided, show available ideas
    if not idea1 or not idea2:
        if not nodes:
            return "This Space has no ideas yet."
        available = _get_available_idea_names(nodes, limit=5)
        return f"Which ideas should I disconnect? Available: {available}"

    # Helper: Resolve numeric index or fuzzy match
    def resolve_idea(ref: str):
        ref_clean = ref.strip().rstrip('.')
        if ref_clean.isdigit():
            idx = int(ref_clean) - 1
            if 0 <= idx < len(nodes):
                return nodes[idx]
            return None

        # Fall back to fuzzy matching
        return _fuzzy_find_idea(nodes, ref)

    # Resolve both ideas
    node1 = resolve_idea(idea1)
    node2 = resolve_idea(idea2)

    if not node1:
        available = _get_available_idea_names(nodes, limit=5)
        return f"Idea '{idea1}' not found. Available: {available}"

    if not node2:
        available = _get_available_idea_names(nodes, limit=5)
        return f"Idea '{idea2}' not found. Available: {available}"

    # Find and delete the edge between them
    all_edges = repo.list_edges(limit=1000)
    edge_found = None
    for edge in all_edges:
        # Check both directions
        if (edge.from_node_id == node1.id and edge.to_node_id == node2.id) or \
           (edge.from_node_id == node2.id and edge.to_node_id == node1.id):
            edge_found = edge
            break

    if not edge_found:
        return f"'{node1.title}' and '{node2.title}' are not connected."

    # Delete the edge
    repo.delete_edge(edge_found.id)

    # Broadcast to Electron
    _broadcast_to_electron({
        "type": "edge_deleted",
        "edge_id": str(edge_found.id),
        "from_node_id": str(edge_found.from_node_id),
        "to_node_id": str(edge_found.to_node_id)
    })

    logger.info(f"Disconnected '{node1.title}' from '{node2.title}'")
    return f"Connection between '{node1.title}' and '{node2.title}' removed."


def connect_ideas_multi(params: Dict[str, Any]) -> str:
    """
    Connect one idea to multiple others by index or name.

    Voice triggers: "Verbinde 2 mit 3, 4 und 5", "Link 1 to 2, 3, 4",
                   "Connect 3 to 4 and 5 and 6"

    Args (via params):
        source: Source idea (index or name)
        targets: Target ideas (list or comma-separated string)

    Returns:
        str: Confirmation message listing successful connections
    """
    import re
    from tools.index_mapping import resolve_idea_index

    source = params.get("source", "").strip()
    targets = params.get("targets", [])

    # Handle string targets (comma-separated or "and"/"und" separated)
    if isinstance(targets, str):
        targets = re.split(r'[,]|\s+and\s+|\s+und\s+', targets)
        targets = [t.strip() for t in targets if t.strip()]

    if not source:
        return "Please specify the source idea (e.g. 'Connect 2 with 3, 4, 5')."

    if not targets:
        return "Please specify at least one target (e.g. 'Connect 2 with 3, 4, 5')."

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes in current bubble
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    if not nodes:
        return "This Space has no ideas yet. Create some ideas first."

    # Helper: Resolve numeric index (via index_mapping) or fuzzy match
    def resolve(ref: str):
        ref_clean = ref.strip().rstrip('.')
        # First try the persistent index mapping
        if ref_clean.isdigit():
            idea_id = resolve_idea_index(ref_clean)
            if idea_id:
                return next((n for n in nodes if n.id == idea_id), None)
            # Fallback to position-based (1-based to 0-based)
            idx = int(ref_clean) - 1
            if 0 <= idx < len(nodes):
                return nodes[idx]
            return None
        # Fuzzy match by name
        return _fuzzy_find_idea(nodes, ref)

    # Resolve source
    source_node = resolve(source)
    if not source_node:
        available = _get_available_idea_names(nodes, limit=5)
        return f"Source '{source}' not found. Available: {available}"

    # Connect to each target
    created = []
    failed = []
    already_connected = []

    # Get existing edges to avoid duplicates
    existing_edges = repo.list_edges(limit=1000)

    for target in targets:
        target_node = resolve(target)
        if not target_node:
            failed.append(target)
            continue

        if target_node.id == source_node.id:
            continue  # Skip self-connection silently

        # Check if already connected
        is_connected = any(
            (e.from_node_id == source_node.id and e.to_node_id == target_node.id) or
            (e.from_node_id == target_node.id and e.to_node_id == source_node.id)
            for e in existing_edges
        )
        if is_connected:
            already_connected.append(target_node.title or target)
            continue

        # Create edge
        repo.create_edge(source_node.id, target_node.id, "related")
        _broadcast_to_electron({
            "type": "edge_added",
            "edge": {
                "from_node_id": source_node.id,
                "to_node_id": target_node.id,
                "label": "related"
            }
        })
        created.append(target_node.title or target)

    # Build response message
    parts = []
    if created:
        parts.append(f"'{source_node.title}' connected with {len(created)} ideas: {', '.join(created)}")
    if already_connected:
        parts.append(f"Already connected: {', '.join(already_connected)}")
    if failed:
        parts.append(f"Not found: {', '.join(failed)}")

    if not parts:
        return "No connections created."

    logger.info(f"Multi-connect from '{source_node.title}': {len(created)} created")
    return ". ".join(parts)


def link_idea_to_root(params: Dict[str, Any]) -> str:
    """
    Link an idea to the root node of the current bubble.

    Voice triggers: "Verknüpfe das mit dem Root", "Link to root", "Connect to main node"

    Args (via params):
        idea_name: Name of idea to link (required)
        bubble_id: Optional bubble ID (uses current if not provided)

    Returns:
        str: Confirmation message
    """
    idea_name = params.get("idea_name", "").strip()
    bubble_id = params.get("bubble_id") or _get_current_bubble_id()

    if not idea_name:
        return "Please provide the name of the idea to link with the Root node."

    repo = _get_canvas_repo()

    # Get nodes in this bubble first
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    # Find the idea using fuzzy matching (pass nodes first, then name)
    idea = _fuzzy_find_idea(nodes, idea_name)
    if not idea:
        return f"Idea '{idea_name}' not found."

    # Find root node in this bubble
    root = next((n for n in nodes if n.node_type == "root"), None)
    if not root:
        return "No Root node found in this Space."

    # Check if idea is the root itself
    if idea.id == root.id:
        return "Root node cannot be linked with itself."

    # Check if already linked
    all_edges = repo.list_edges(limit=1000)
    already_linked = any(
        (e.from_node_id == root.id and e.to_node_id == idea.id) or
        (e.from_node_id == idea.id and e.to_node_id == root.id)
        for e in all_edges
    )
    if already_linked:
        return f"'{idea.title}' is already connected to the Root node."

    # Create edge from root to idea
    from data.models import CanvasEdge
    edge = CanvasEdge(
        id=str(uuid.uuid4()),
        from_node_id=root.id,
        to_node_id=idea.id,
        edge_type="hierarchy"
    )
    repo.create_edge(edge)

    # Broadcast to UI
    _broadcast_to_electron({
        "type": "edge_created",
        "edge": {
            "id": edge.id,
            "from_node_id": edge.from_node_id,
            "to_node_id": edge.to_node_id,
            "edge_type": edge.edge_type,
        }
    })

    logger.info(f"Linked '{idea.title}' to root node '{root.title}'")
    return f"'{idea.title}' linked with Root node '{root.title}'."


def delete_idea(params: Dict[str, Any]) -> str:
    """
    Delete an idea.

    Voice triggers: "Remove the old note", "Delete cooking idea"

    Args (via params):
        idea_name: Name of idea to delete (required)

    Returns:
        str: Confirmation message
    """
    idea_name = params.get("idea_name", "").strip()

    if not idea_name:
        return "Which idea should I delete?"

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes in this bubble first
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    # Use fuzzy matching (pass nodes first, then name)
    match = _fuzzy_find_idea(nodes, idea_name)

    if not match:
        return f"Couldn't find an idea called '{idea_name}'"

    # Prevent root node deletion
    if match.node_type == "root":
        return "The root node cannot be deleted."

    title = match.title
    node_id = match.id

    # Delete connected edges first to avoid orphans
    all_edges = repo.list_edges(limit=1000)
    for edge in all_edges:
        if edge.from_node_id == node_id or edge.to_node_id == node_id:
            repo.delete_edge(edge.id)

    repo.delete_node(node_id)

    # Broadcast
    _broadcast_to_electron({
        "type": "node_deleted",
        "node_id": node_id
    })

    # Publish updated bubble to Rowboat
    if bubble_id:
        try:
            from publishing import get_ideas_publisher
            get_ideas_publisher().publish_bubble(bubble_id=bubble_id)
        except Exception:
            pass

    logger.info(f"Deleted idea '{title}'")
    return f"Deleted '{title}'"


def get_current_space(params: Dict[str, Any]) -> str:
    """
    Get information about current location.

    Voice triggers: "Where am I?", "What space is this?"

    Returns:
        str: Current location description
    """
    logger.debug("get_current_space: resolving current location")
    bubble_id = _get_current_bubble_id()

    if bubble_id is None:
        return "You're in the multiverse view, looking at all your spaces"

    bubble_info = _get_bubble_info(bubble_id)
    if bubble_info:
        return f"You're inside {bubble_info.get('title', 'a space')}"

    return f"You're in space {bubble_id}"


def expand_ideas(params: Dict[str, Any]) -> str:
    """
    Expand existing ideas using AI to generate related concepts.

    Voice triggers: "Erweitere die Ideen", "Generiere verwandte Ideen",
                   "Mach mehr Ideen aus den bestehenden"

    Args (via params):
        source_idea: Optional - specific idea to expand
        count: Number of ideas to generate (default: 3)

    Returns:
        str: Summary of generated ideas
    """
    import asyncio

    source_idea = params.get("source_idea", "").strip()
    count = params.get("count", 3)

    # 1. Get current bubble
    bubble_id = _get_current_bubble_id()
    if bubble_id is None:
        return "Please enter a Space first."

    # 2. Get existing ideas
    repo = _get_canvas_repo()
    all_nodes = repo.list_nodes(limit=1000)
    nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]

    if not nodes:
        return "No ideas available to expand."

    # Filter by source_idea if specified
    if source_idea:
        nodes = [n for n in nodes if source_idea.lower() in (n.title or "").lower()]
        if not nodes:
            return f"No idea named '{source_idea}' found."

    # 3. Build context for LLM
    ideas_context = "\n".join([
        f"- {n.title}: {(n.content or '')[:200]}" for n in nodes
    ])

    # Create node ID lookup for linking
    node_lookup = {(n.title or "").lower(): n.id for n in nodes}

    # 4. Call LLM for expansion
    try:
        # Run async function in sync context - handle nested event loop case
        try:
            # Check if there's already a running loop
            asyncio.get_running_loop()
            # If we get here, there's a running loop - use thread pool
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                def run_in_thread():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(_generate_expansions(ideas_context, count))
                    finally:
                        loop.close()
                future = pool.submit(run_in_thread)
                expansions = future.result(timeout=30)
        except RuntimeError:
            # No running loop - safe to create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                expansions = loop.run_until_complete(_generate_expansions(ideas_context, count))
            finally:
                loop.close()
    except Exception as e:
        logger.error(f"LLM expansion failed: {e}")
        return f"Error generating ideas: {str(e)}"

    if not expansions:
        return "Could not generate new ideas."

    # 5. Create new ideas and links
    # Get all existing positions for collision detection (re-fetch to include any recent additions)
    all_nodes_fresh = repo.list_nodes(limit=1000)
    bubble_nodes_fresh = [n for n in all_nodes_fresh if n.linked_idea_id == bubble_id]
    existing_positions = [(n.x or 0, n.y or 0) for n in bubble_nodes_fresh]

    created = []
    for exp in expansions:
        try:
            # Calculate spiral position for this new node
            node_count = len(bubble_nodes_fresh) + len(created)
            x, y = calculate_spiral_position(node_count, existing_positions)

            # Create new node
            new_node = repo.create_node(
                node_type="note",
                title=exp.get("title", "Neue Idee"),
                content=exp.get("content", ""),
                x=x,
                y=y,
                linked_idea_id=bubble_id,
                metadata={"ai_generated": True, "source_title": exp.get("source_title")}
            )

            # Add position to existing for next iteration's collision detection
            existing_positions.append((x, y))

            # Create edge to source if we can find it
            source_title = exp.get("source_title", "").lower()
            if source_title and source_title in node_lookup:
                source_node_id = node_lookup[source_title]
                repo.create_edge(
                    from_node_id=source_node_id,
                    to_node_id=new_node.id,
                    edge_type="expanded_from"
                )

                # Broadcast edge
                _broadcast_to_electron({
                    "type": "edge_added",
                    "edge": {
                        "from_node_id": source_node_id,
                        "to_node_id": new_node.id,
                        "label": "expanded_from"
                    }
                })

            # Broadcast to UI
            _broadcast_to_electron({
                "type": "node_added",
                "bubble_id": bubble_id,
                "node": {
                    "id": new_node.id,
                    "type": new_node.node_type,
                    "position": {"x": new_node.x, "y": new_node.y},
                    "content": {"title": new_node.title, "text": new_node.content},
                    "connections": []
                }
            })

            created.append(new_node.title)
            logger.info(f"Created expanded idea: {new_node.title}")

        except Exception as e:
            logger.error(f"Failed to create idea: {e}")

    if not created:
        return "Could not create new ideas."

    return f"I generated {len(created)} new ideas: {', '.join(created)}"


async def _generate_expansions(ideas_context: str, count: int) -> List[Dict]:
    """
    Call LLM to generate idea expansions.

    Args:
        ideas_context: Formatted string of existing ideas
        count: Number of expansions to generate

    Returns:
        List of dicts with title, content, source_title
    """
    import os
    import json
    import re

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("OpenAI package not installed")
        return []

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY not set")
        return []

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )

    prompt = f"""Analysiere diese bestehenden Ideen und generiere {count} verwandte/erweiterte Ideen.

Bestehende Ideen:
{ideas_context}

Generiere fuer jede neue Idee:
- title: Kurzer Titel (max 50 Zeichen)
- content: Beschreibung (2-3 Saetze)
- source_title: Exakter Titel der Quell-Idee (aus der Liste oben)

Antworte NUR als JSON-Array, keine Erklaerungen:
[{{"title": "...", "content": "...", "source_title": "..."}}]
"""

    try:
        response = client.chat.completions.create(
            model=get_model("idea_enrichment"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000,
        )

        content = response.choices[0].message.content
        logger.info(f"LLM expansion response: {content[:200]}...")

        # Extract JSON from response
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())

        logger.warning("No JSON array found in LLM response")
        return []

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return []


# =============================================================================
# MOVE IDEA TOOL
# =============================================================================

def move_idea(params: Dict[str, Any]) -> str:
    """
    Move an idea/note from current space to another space.

    Voice triggers: "Verschiebe X nach Y", "Move idea X to space Y",
                   "Bringe X in den Space Y"

    Args (via params):
        idea_name: Name of the idea to move (fuzzy match)
        target_space: Name of destination space (fuzzy match)

    Returns:
        str: Confirmation or error message
    """
    idea_name = params.get("idea_name", "").strip().lower()
    target_space = params.get("target_space", "").strip().lower()

    if not idea_name:
        return "Which idea should I move?"
    if not target_space:
        return "Which Space should I move the idea to?"

    # 1. Get current bubble
    source_bubble_id = _get_current_bubble_id()
    if source_bubble_id is None:
        return "Please enter a Space first."

    # 2. Get repositories
    repo = _get_canvas_repo()
    ideas_repo = _get_ideas_repo()

    # 3. Find the node by name in current space
    all_nodes = repo.list_nodes(limit=1000)
    nodes_in_space = [n for n in all_nodes if n.linked_idea_id == source_bubble_id]

    match = None
    for n in nodes_in_space:
        if idea_name in (n.title or "").lower():
            match = n
            break

    if not match:
        return f"No idea named '{idea_name}' found in this Space."

    # 4. Find target space by name
    all_ideas = ideas_repo.list()
    target_idea = None
    for idea in all_ideas:
        if target_space in (idea.title or "").lower():
            target_idea = idea
            break

    if not target_idea:
        return f"Space '{target_space}' not found."

    if target_idea.id == source_bubble_id:
        return "The idea is already in this Space."

    # 5. Move: Update linked_idea_id
    old_bubble_id = match.linked_idea_id
    match.linked_idea_id = target_idea.id
    repo.update_node(match)

    # 6. Broadcast to Electron UI
    _broadcast_to_electron({
        "type": "node_moved",
        "node_id": match.id,
        "from_bubble_id": old_bubble_id,
        "to_bubble_id": target_idea.id,
        "node": {
            "id": match.id,
            "type": match.node_type,
            "position": {"x": match.x, "y": match.y},
            "content": {"title": match.title, "text": match.content}
        }
    })

    logger.info(f"Moved idea '{match.title}' from {old_bubble_id} to {target_idea.id}")
    return f"Moved '{match.title}' to '{target_idea.title}'."


def _get_ideas_repo():
    """Get the ideas repository for looking up spaces."""
    from spaces.ideas.tools.bubble_tools import _get_ideas_repo as get_repo
    return get_repo()


# =============================================================================
# AUTO-LINK IDEAS (Semantic Similarity)
# =============================================================================

def auto_link_ideas(params: Dict[str, Any]) -> str:
    """
    Automatically analyze all ideas in current bubble and create links
    between semantically related pairs.

    Voice triggers: "Verlinke die Ideen sinnvoll", "Link related ideas",
                   "Verbinde ähnliche Notizen automatisch"

    Uses embedding-based semantic similarity to find related ideas.
    Creates edges for pairs with similarity score > threshold.

    Args (via params):
        threshold: Minimum similarity score (0-1), default 0.5
        max_links: Maximum number of links to create, default 10

    Returns:
        str: Summary of created links
    """
    logger.info("=" * 50)
    logger.info(">>> auto_link_ideas() CALLED <<<")
    logger.info(f"    params = {params}")
    logger.info("=" * 50)

    threshold = params.get("threshold", 0.5)
    max_links = params.get("max_links", 10)

    # 1. Get current bubble
    bubble_id = _get_current_bubble_id()
    if bubble_id is None:
        return "Please enter a Space first."

    # 2. Get all ideas/nodes in this bubble
    repo = _get_canvas_repo()
    all_nodes = repo.list_nodes(limit=1000)
    nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]

    if len(nodes) < 2:
        return "Too few ideas to link. Create at least 2 ideas."

    logger.info(f"[auto_link_ideas] Found {len(nodes)} nodes in bubble {bubble_id}")

    # 3. Get existing edges to avoid duplicates
    existing_edges = set()
    try:
        edges = repo.list_edges()
        for edge in edges:
            # Store both directions to check
            existing_edges.add((edge.from_node_id, edge.to_node_id))
            existing_edges.add((edge.to_node_id, edge.from_node_id))
    except Exception as e:
        logger.warning(f"Could not load existing edges: {e}")

    # 4. Import embedding service and monitoring
    try:
        from data.embedding_service import get_embedding_service
        embedding_service = get_embedding_service()
    except ImportError as e:
        logger.error(f"Could not import embedding service: {e}")
        return "Embedding service not available. Install with: pip install sentence-transformers"

    # Import monitoring
    try:
        from swarm.monitoring.system_status import get_status_monitor
        _monitor = get_status_monitor()
    except ImportError:
        _monitor = None

    if not embedding_service.is_available:
        return "Embedding service not available. Install with: pip install sentence-transformers"

    # 5. Generate embeddings for all nodes
    node_texts = []
    for n in nodes:
        # Combine title and content for better semantic representation
        text = f"{n.title or ''} {n.content or ''}".strip()
        node_texts.append(text)

    # Track embedding generation with monitoring
    embed_op_id = None
    if _monitor:
        embed_op_id = _monitor.start_operation(
            "embedding",
            f"Generating embeddings for {len(node_texts)} ideas",
            {"count": len(node_texts)}
        )

    try:
        embeddings = embedding_service.embed_batch(node_texts)
        if _monitor and embed_op_id:
            _monitor.complete_operation(embed_op_id, success=True)
    except Exception as e:
        if _monitor and embed_op_id:
            _monitor.complete_operation(embed_op_id, success=False, error=str(e))
        logger.error(f"[auto_link_ideas] Embedding generation failed: {e}")
        return f"Error generating embeddings: {e}"

    logger.info(f"[auto_link_ideas] Generated {len([e for e in embeddings if e])} embeddings")

    # 6. Calculate pairwise similarities
    similarity_pairs = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if embeddings[i] is None or embeddings[j] is None:
                continue

            # Skip if edge already exists
            if (nodes[i].id, nodes[j].id) in existing_edges:
                continue

            similarity = embedding_service.similarity(embeddings[i], embeddings[j])
            if similarity >= threshold:
                similarity_pairs.append((i, j, similarity))

    # Sort by similarity descending
    similarity_pairs.sort(key=lambda x: x[2], reverse=True)

    # Limit number of links
    similarity_pairs = similarity_pairs[:max_links]

    logger.info(f"[auto_link_ideas] Found {len(similarity_pairs)} pairs above threshold {threshold}")

    # 7. Create edges for similar pairs
    created_links = []
    for i, j, score in similarity_pairs:
        node1 = nodes[i]
        node2 = nodes[j]

        try:
            # Create edge
            edge = repo.create_edge(node1.id, node2.id, "related")

            # Broadcast to Electron UI
            _broadcast_to_electron({
                "type": "edge_added",
                "edge": {
                    "from_node_id": node1.id,
                    "to_node_id": node2.id,
                    "label": "related"
                }
            })

            link_info = f"'{node1.title}' ↔ '{node2.title}' ({score:.0%})"
            created_links.append(link_info)
            logger.info(f"[auto_link_ideas] Created: {link_info}")

        except Exception as e:
            logger.error(f"Failed to create edge: {e}")

    # 8. Return summary
    if not created_links:
        return f"No matching connections found (threshold: {threshold:.0%}). Ideas are too different or already connected."

    summary = f"I created {len(created_links)} connections:\n"
    for link in created_links[:5]:  # Show max 5 in response
        summary += f"  • {link}\n"

    if len(created_links) > 5:
        summary += f"  ... and {len(created_links) - 5} more."

    return summary.strip()


def analyze_and_suggest_links(params: Dict[str, Any]) -> str:
    """
    Analyze all ideas in current bubble and suggest meaningful links
    WITHOUT creating them. User can confirm to create links.

    Voice triggers: "Analysiere die Ideen", "Schlage Verlinkungen vor",
                   "Welche Ideen gehören zusammen"

    Returns top 5 suggested link pairs with reasoning.

    Args (via params):
        threshold: Minimum similarity score (0-1), default 0.4
        max_suggestions: Maximum suggestions to return, default 5

    Returns:
        str: List of suggested links with similarity scores
    """
    threshold = params.get("threshold", 0.4)
    max_suggestions = params.get("max_suggestions", 5)

    # 1. Get current bubble
    bubble_id = _get_current_bubble_id()
    if bubble_id is None:
        return "Please enter a Space first."

    # Get bubble name for context
    ideas_repo = _get_ideas_repo()
    bubble = ideas_repo.get(bubble_id)
    bubble_name = bubble.title if bubble else "Current Space"

    # 2. Get all ideas/nodes in this bubble
    repo = _get_canvas_repo()
    all_nodes = repo.list_nodes(limit=1000)
    nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]

    if len(nodes) < 2:
        return f"Space '{bubble_name}' has {len(nodes)} ideas - at least 2 are needed."

    logger.info(f"[analyze_links] Found {len(nodes)} nodes in bubble {bubble_id}")

    # 3. Get existing edges to exclude
    existing_edges = set()
    try:
        edges = repo.list_edges()
        for edge in edges:
            existing_edges.add((edge.from_node_id, edge.to_node_id))
            existing_edges.add((edge.to_node_id, edge.from_node_id))
    except Exception as e:
        logger.warning(f"Could not load existing edges: {e}")

    # 4. Import embedding service
    try:
        from data.embedding_service import get_embedding_service, EmbeddingService
        embedding_service = get_embedding_service()
    except ImportError as e:
        logger.error(f"Could not import embedding service: {e}")
        embedding_service = None

    # 5. Generate text list for all nodes
    node_texts = []
    for n in nodes:
        text = f"{n.title or ''} {n.content or ''}".strip()
        node_texts.append(text)

    # 6. Calculate pairwise similarities
    similarity_pairs = []
    use_embeddings = embedding_service and embedding_service.is_available

    if use_embeddings:
        # Use semantic embeddings
        logger.info("[analyze_links] Using embedding-based similarity")
        embeddings = embedding_service.embed_batch(node_texts)

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if embeddings[i] is None or embeddings[j] is None:
                    continue

                # Skip if edge already exists
                if (nodes[i].id, nodes[j].id) in existing_edges:
                    continue

                similarity = embedding_service.similarity(embeddings[i], embeddings[j])
                if similarity >= threshold:
                    similarity_pairs.append((i, j, similarity))
    else:
        # Fallback to text-based similarity (Jaccard)
        logger.info("[analyze_links] Using text-based similarity (fallback)")
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                # Skip if edge already exists
                if (nodes[i].id, nodes[j].id) in existing_edges:
                    continue

                similarity = EmbeddingService.text_similarity(node_texts[i], node_texts[j])
                if similarity >= threshold:
                    similarity_pairs.append((i, j, similarity))

    # Sort by similarity descending
    similarity_pairs.sort(key=lambda x: x[2], reverse=True)
    similarity_pairs = similarity_pairs[:max_suggestions]

    # 7. Format suggestions
    if not similarity_pairs:
        return f"No matching links found in Space '{bubble_name}'. Ideas are too different or already linked."

    method_note = "" if use_embeddings else " (word-based)"
    suggestions = [f"In Space '{bubble_name}' I suggest {len(similarity_pairs)} links{method_note}:\n"]

    for idx, (i, j, score) in enumerate(similarity_pairs, 1):
        node1 = nodes[i]
        node2 = nodes[j]
        title1 = (node1.title or "Untitled")[:40]
        title2 = (node2.title or "Untitled")[:40]
        suggestions.append(f"{idx}. '{title1}' <-> '{title2}' ({score:.0%} similarity)")

    suggestions.append("\nSay 'Yes, link them' to create the connections.")

    return "\n".join(suggestions)


# =============================================================================
# EXPLAIN IDEA
# =============================================================================

def explain_idea(params: Dict[str, Any]) -> str:
    """
    Explain what an idea is about using AI analysis.

    Voice triggers: "Erkläre die Idee X", "Was bedeutet X?", "Explain the idea X"

    Args (via params):
        idea_name: Name of the idea to explain (fuzzy matched)

    Returns:
        str: AI-generated explanation of the idea
    """
    idea_name = params.get("idea_name", "").strip()

    if not idea_name:
        return "Which idea should I explain?"

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes in current bubble
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    if not nodes:
        return "No ideas found in this Space."

    # Find the idea using fuzzy matching
    match = _fuzzy_find_idea(nodes, idea_name)

    if not match:
        available = _get_available_idea_names(nodes, limit=5)
        return f"Idea '{idea_name}' not found. Available: {available}"

    # Build context from the idea
    title = match.title or "Unbenannt"
    content = match.content or ""

    # If content is very short, just return it directly
    if len(content) < 100 and content:
        return f"'{title}': {content}"

    # Use LLM to explain the idea
    try:
        from openai import OpenAI
        import os

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            # Fallback: return raw content
            if content:
                return f"'{title}': {content[:500]}"
            return f"The idea '{title}' has no content yet."

        client = get_client("summary")

        model = get_model("summary")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Du bist ein hilfreicher Assistent. Erkläre die Idee kurz und verständlich auf Deutsch. Maximal 2-3 Sätze."
                },
                {
                    "role": "user",
                    "content": f"Erkläre diese Idee:\n\nTitel: {title}\nInhalt: {content or 'Kein Inhalt vorhanden'}"
                }
            ],
            max_tokens=200,
            temperature=0.5
        )

        explanation = response.choices[0].message.content.strip()
        logger.info(f"Explained idea '{title}'")
        return f"'{title}': {explanation}"

    except Exception as e:
        logger.warning(f"Explanation failed: {e}")
        # Fallback: return raw content
        if content:
            return f"'{title}': {content[:500]}"
        return f"The idea '{title}' has no content yet."


# =============================================================================
# FORMAT IDEAS AS TABLE
# =============================================================================

def format_idea_as_table(params: Dict[str, Any]) -> str:
    """
    Format an idea's content as a table structure.

    Voice triggers: "Formatiere als Tabelle", "Mach eine Tabelle daraus"

    Args (via params):
        idea_name: Name of the idea to format

    Returns:
        str: Formatted table representation
    """
    idea_name = params.get("idea_name", "").strip()
    logger.debug("format_idea_as_table: idea_name=%s", idea_name)

    if not idea_name:
        return "Which idea should I format as a table?"

    bubble_id = _get_current_bubble_id()
    repo = _get_canvas_repo()

    # Get nodes in current bubble
    all_nodes = repo.list_nodes(limit=1000)
    if bubble_id:
        nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
    else:
        nodes = all_nodes

    match = _fuzzy_find_idea(nodes, idea_name)
    if not match:
        return f"Idea '{idea_name}' not found."

    # Get content and format as table
    content = match.content or ""
    if not content:
        return f"The idea '{match.title}' has no content to format."

    # Simple table formatting - split by lines
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return f"Not enough content for table format. Content: {content[:200]}"

    # Format as markdown table
    table = "| Entry | Details |\n|---------|----------|\n"
    for i, line in enumerate(lines[:10]):
        clean_line = line.strip().replace("|", "-")
        table += f"| {i+1} | {clean_line} |\n"

    return f"Table for '{match.title}':\n\n{table}"


# =============================================================================
# TOOL REGISTRY
# =============================================================================

IDEA_TOOLS = {
    "list_ideas": list_ideas,
    "count_ideas": count_ideas,
    "create_idea": create_idea,
    "add_image": add_image,
    "find_idea": find_idea,
    "update_idea": update_idea,
    "classify_idea": classify_idea,
    "connect_ideas": connect_ideas,
    "disconnect_ideas": disconnect_ideas,
    "connect_ideas_multi": connect_ideas_multi,
    "link_idea_to_root": link_idea_to_root,
    "delete_idea": delete_idea,
    "get_current_space": get_current_space,
    "expand_ideas": expand_ideas,
    "move_idea": move_idea,
    "auto_link_ideas": auto_link_ideas,
    "analyze_and_suggest_links": analyze_and_suggest_links,
    "explain_idea": explain_idea,
    "format_idea_as_table": format_idea_as_table,
}


def register_idea_tools(tools_manager) -> None:
    """Register all idea tools with the tools manager (with observer logging)."""
    print("Registering idea tools with observer...")
    for tool_name, tool_func in IDEA_TOOLS.items():
        try:
            tools_manager.register_with_observer(tool_name, tool_func)
            print(f"  - {tool_name}")
        except ValueError:
            # Tool already registered by workspace_tools - skip
            print(f"  - {tool_name} (skipped - already registered)")


__all__ = [
    "list_ideas",
    "count_ideas",
    "create_idea",
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
    # Helpers (exported for testing)
    "_fuzzy_find_idea",
    "_get_available_idea_names",
    "calculate_spiral_position",
]
