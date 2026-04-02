"""
Structured Formatting Tools for LLM-driven content formatting.

These tools enable LLMs to format idea content into structured formats
like action lists, tables, and hierarchies, with validation against schemas.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import asyncio

from data.format_schemas import (
    get_format_schema,
    validate_format_type,
    get_available_format_types,
    FORMAT_SCHEMAS
)
from data.models import CanvasNode
from data.repository import CanvasRepository

logger = logging.getLogger(__name__)

# =============================================================================
# SCHEMA VALIDATION
# =============================================================================

def validate_format_schema(content_json: Dict[str, Any], format_type: str) -> Tuple[bool, str]:
    """
    Validate structured content against its format schema.

    Args:
        content_json: The structured content to validate
        format_type: The expected format type (e.g., "action_list")

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Type aliases: LLM may return different type names that map to the same format
    TYPE_ALIASES = {
        "technical_specs": "specs",
        "pros_cons_table": "pros_cons",
        "simple_table": "table",
        "mind_map": "mindmap",
        "user_stories": "user_story",
        "flow": "flowchart",
    }

    try:
        # Check if format type is supported
        if not validate_format_type(format_type):
            available = get_available_format_types()
            return False, f"Unsupported format type '{format_type}'. Available: {available}"

        # Basic structure validation
        if not isinstance(content_json, dict):
            return False, "Content must be a JSON object"

        # Normalize both actual and expected types using aliases
        actual_type = content_json.get("type")
        expected_normalized = TYPE_ALIASES.get(format_type, format_type)
        actual_normalized = TYPE_ALIASES.get(actual_type, actual_type)

        if actual_normalized != expected_normalized:
            return False, f"Content type '{actual_type}' does not match expected '{format_type}'"

        # Get schema for detailed validation
        schema = get_format_schema(format_type)

        # Basic required fields check
        required_fields = schema.get("required", [])
        missing_fields = [field for field in required_fields if field not in content_json]
        if missing_fields:
            return False, f"Missing required fields: {missing_fields}"

        # Type-specific validation
        if format_type == "action_list":
            return _validate_action_list(content_json)
        elif format_type == "pros_cons_table":
            return _validate_pros_cons_table(content_json)
        elif format_type == "technical_specs":
            return _validate_technical_specs(content_json)
        elif format_type == "hierarchy":
            return _validate_hierarchy(content_json)
        elif format_type == "comparison_table":
            return _validate_comparison_table(content_json)
        elif format_type == "simple_table":
            return _validate_simple_table(content_json)
        elif format_type == "kanban":
            return _validate_kanban(content_json)
        elif format_type == "mindmap":
            return _validate_mindmap(content_json)
        elif format_type == "swot":
            return _validate_swot(content_json)
        elif format_type == "user_story":
            return _validate_user_story(content_json)
        elif format_type == "flowchart":
            return _validate_flowchart(content_json)

        return True, "Validation passed"

    except Exception as e:
        logger.error(f"Schema validation error: {e}")
        return False, f"Validation error: {str(e)}"

def _validate_action_list(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate action list structure."""
    items = content.get("items", [])
    if not isinstance(items, list):
        return False, "Items must be an array"

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            return False, f"Item {i} must be an object"
        if "task" not in item:
            return False, f"Item {i} missing required 'task' field"

    return True, "Action list validation passed"

def _validate_pros_cons_table(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate pros/cons table structure."""
    pros = content.get("pros", [])
    cons = content.get("cons", [])

    if not isinstance(pros, list) or not isinstance(cons, list):
        return False, "Pros and cons must be arrays"

    for item in pros + cons:
        if not isinstance(item, dict) or "point" not in item:
            return False, "Each pro/con must have a 'point' field"

    return True, "Pros/cons table validation passed"

def _validate_technical_specs(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate technical specifications structure."""
    specs = content.get("specifications", [])
    if not isinstance(specs, list):
        return False, "Specifications must be an array"

    for spec in specs:
        if not isinstance(spec, dict) or "requirement" not in spec:
            return False, "Each specification must have a 'requirement' field"

    return True, "Technical specs validation passed"

def _validate_hierarchy(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate hierarchy structure."""
    levels = content.get("levels", [])
    if not isinstance(levels, list) or not levels:
        return False, "Hierarchy must have at least one level"

    for level in levels:
        if not isinstance(level, dict) or "items" not in level:
            return False, "Each level must have an 'items' array"

    return True, "Hierarchy validation passed"

def _validate_comparison_table(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate comparison table structure."""
    criteria = content.get("criteria", [])
    options = content.get("options", [])

    if not isinstance(criteria, list) or not isinstance(options, list):
        return False, "Criteria and options must be arrays"

    if not criteria or not options:
        return False, "Must have at least one criterion and one option"

    return True, "Comparison table validation passed"


def _validate_simple_table(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate simple table structure."""
    headers = content.get("headers", [])
    rows = content.get("rows", [])

    if not isinstance(headers, list) or not headers:
        return False, "Headers must be a non-empty array"

    if not isinstance(rows, list):
        return False, "Rows must be an array"

    # Validate each row has correct number of columns
    num_cols = len(headers)
    for i, row in enumerate(rows):
        if not isinstance(row, list):
            return False, f"Row {i} must be an array"
        if len(row) != num_cols:
            return False, f"Row {i} has {len(row)} columns, expected {num_cols}"

    return True, "Simple table validation passed"

def _validate_kanban(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate Kanban board structure."""
    columns = content.get("columns", [])

    if not isinstance(columns, list) or not columns:
        return False, "Kanban must have at least one column"

    for i, column in enumerate(columns):
        if not isinstance(column, dict):
            return False, f"Column {i} must be an object"
        if "name" not in column:
            return False, f"Column {i} missing required 'name' field"
        if "cards" not in column:
            return False, f"Column {i} missing required 'cards' field"

        cards = column.get("cards", [])
        if not isinstance(cards, list):
            return False, f"Column {i} cards must be an array"

        for j, card in enumerate(cards):
            if not isinstance(card, dict):
                return False, f"Card {j} in column {i} must be an object"
            if "title" not in card:
                return False, f"Card {j} in column {i} missing required 'title' field"

    return True, "Kanban validation passed"

def _validate_mindmap(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate mind map structure."""
    center = content.get("center")
    branches = content.get("branches", [])

    if not isinstance(center, dict) or "label" not in center:
        return False, "Mindmap must have a center with 'label' field"

    if not isinstance(branches, list) or not branches:
        return False, "Mindmap must have at least one branch"

    for i, branch in enumerate(branches):
        if not isinstance(branch, dict):
            return False, f"Branch {i} must be an object"
        if "label" not in branch:
            return False, f"Branch {i} missing required 'label' field"

    return True, "Mindmap validation passed"

def _validate_swot(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate SWOT analysis structure."""
    quadrants = ["strengths", "weaknesses", "opportunities", "threats"]

    for quadrant in quadrants:
        items = content.get(quadrant, [])
        if not isinstance(items, list):
            return False, f"{quadrant} must be an array"

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                return False, f"Item {i} in {quadrant} must be an object"
            if "point" not in item:
                return False, f"Item {i} in {quadrant} missing required 'point' field"

    return True, "SWOT validation passed"

def _validate_user_story(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate user stories structure."""
    stories = content.get("stories", [])

    if not isinstance(stories, list) or not stories:
        return False, "User stories must have at least one story"

    for i, story in enumerate(stories):
        if not isinstance(story, dict):
            return False, f"Story {i} must be an object"
        required_fields = ["role", "want", "benefit"]
        for field in required_fields:
            if field not in story:
                return False, f"Story {i} missing required '{field}' field"

    return True, "User story validation passed"

def _validate_flowchart(content: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate flowchart structure."""
    nodes = content.get("nodes", [])
    edges = content.get("edges", [])

    if not isinstance(nodes, list) or not nodes:
        return False, "Flowchart must have at least one node"

    if not isinstance(edges, list):
        return False, "Flowchart edges must be an array"

    # Validate nodes
    node_ids = set()
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            return False, f"Node {i} must be an object"
        if "id" not in node or "type" not in node or "label" not in node:
            return False, f"Node {i} missing required fields (id, type, label)"
        node_ids.add(node["id"])

    # Validate edges reference existing nodes
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            return False, f"Edge {i} must be an object"
        if "from" not in edge or "to" not in edge:
            return False, f"Edge {i} missing required fields (from, to)"
        if edge["from"] not in node_ids:
            return False, f"Edge {i} references non-existent source node '{edge['from']}'"
        if edge["to"] not in node_ids:
            return False, f"Edge {i} references non-existent target node '{edge['to']}'"

    return True, "Flowchart validation passed"

# =============================================================================
# LLM FORMATTING FUNCTIONS
# =============================================================================

async def format_idea_content(
    idea_content: str,
    format_type: str,
    idea_title: str = "",
    additional_context: str = ""
) -> Dict[str, Any]:
    """
    Use LLM to format idea content into structured format.

    Args:
        idea_content: The original text content of the idea
        format_type: Target format (action_list, pros_cons_table, etc.)
        idea_title: Title of the idea for context
        additional_context: Additional context for formatting

    Returns:
        Structured content dictionary with validation result
    """
    try:
        # Validate format type
        if not validate_format_type(format_type):
            available = get_available_format_types()
            raise ValueError(f"Unsupported format type '{format_type}'. Available: {available}")

        # Get format-specific prompt
        prompt = _build_formatting_prompt(
            idea_content, format_type, idea_title, additional_context
        )

        # Call LLM
        formatted_content = await _call_llm_for_formatting(prompt, format_type)

        # Validate result
        is_valid, error_msg = validate_format_schema(formatted_content, format_type)

        return {
            "success": is_valid,
            "content": formatted_content if is_valid else None,
            "error": error_msg if not is_valid else None,
            "format_type": format_type,
            "original_content": idea_content
        }

    except Exception as e:
        logger.error(f"Formatting error: {e}")
        return {
            "success": False,
            "content": None,
            "error": str(e),
            "format_type": format_type,
            "original_content": idea_content
        }

def _build_formatting_prompt(
    content: str,
    format_type: str,
    title: str,
    context: str
) -> str:
    """Build format-specific prompt for LLM."""

    base_prompt = f"""
Analysiere diesen Inhalt und formatiere ihn als {format_type}:

TITEL: {title}
INHALT: {content}
ZUSATZKONTEXT: {context}

"""

    if format_type == "action_list":
        return base_prompt + """
Formatiere als VibeMind-Aktionsliste im JSON-Format:
{
  "type": "action_list",
  "title": "Titel der Liste",
  "items": [
    {
      "task": "Konkrete VibeMind-Aktion",
      "status": "pending|in_progress|completed",
      "priority": "low|medium|high",
      "assignee": "Rachel|Antoni|Adam",
      "space": "IDEAS|CODING|DESKTOP",
      "action_type": "bubble.create|idea.create|code.generate|desktop.task"
    }
  ]
}

WICHTIG: Fokussiere auf IDEAS Space Actions (Rachel):
- bubble.create: Neue Bubble/Thema erstellen
- bubble.enter: Bestehende Bubble betreten
- idea.create: Neue Idee/Notiz hinzufügen
- idea.expand: Bestehende Ideen erweitern/generieren
- idea.connect: Ideen miteinander verlinken
- idea.auto_link: Alle Ideen automatisch verlinken

Beispiele:
- "Erstelle Bubble 'KI-Chatbot' mit Rachel"
- "Fuege Idee 'User-Interface' hinzu"
- "Erweitere die vorhandenen Ideen"
- "Verlinke alle Ideen sinnvoll"
"""

    elif format_type == "pros_cons_table":
        return base_prompt + """
Formatiere als Vor-/Nachteile-Tabelle im JSON-Format:
{
  "type": "pros_cons_table",
  "title": "Titel der Analyse",
  "topic": "Was wird analysiert",
  "pros": [
    {
      "point": "Vorteil",
      "weight": 1-5,
      "evidence": "Begründung"
    }
  ],
  "cons": [
    {
      "point": "Nachteil",
      "weight": 1-5,
      "evidence": "Begründung",
      "mitigation": "Lösungsansatz"
    }
  ]
}

Finde alle Vor- und Nachteile mit konkreten Begründungen.
"""

    elif format_type == "technical_specs":
        return base_prompt + """
Formatiere als technische Spezifikationen im JSON-Format:
{
  "type": "technical_specs",
  "title": "Titel der Spezifikation",
  "component": "Betroffene Komponente",
  "specifications": [
    {
      "category": "Kategorie (Performance/Security/Scalability)",
      "requirement": "Konkrete Anforderung",
      "priority": "must_have|should_have|nice_to_have",
      "acceptance_criteria": "Wie wird es getestet?"
    }
  ]
}

Extrahiere alle technischen Anforderungen und Spezifikationen.
"""

    elif format_type == "hierarchy":
        return base_prompt + """
Formatiere als hierarchische Struktur im JSON-Format:
{
  "type": "hierarchy",
  "title": "Titel der Hierarchie",
  "root_concept": "Hauptkonzept",
  "levels": [
    {
      "level": 1,
      "name": "Level-Name",
      "items": [
        {
          "name": "Element-Name",
          "description": "Beschreibung",
          "children": ["child1", "child2"]
        }
      ]
    }
  ]
}

Erstelle eine logische Hierarchie aus den Konzepten.
"""

    elif format_type == "comparison_table":
        return base_prompt + """
Formatiere als Vergleichstabelle im JSON-Format:
{
  "type": "comparison_table",
  "title": "Titel des Vergleichs",
  "criteria": [
    {
      "name": "Kriterium",
      "description": "Beschreibung",
      "weight": 1-5
    }
  ],
  "options": [
    {
      "name": "Option",
      "description": "Beschreibung",
      "scores": {"Kriterium1": 5, "Kriterium2": 3}
    }
  ]
}

Identifiziere Vergleichskriterien und -optionen.
"""

    elif format_type == "simple_table":
        return base_prompt + """
Formatiere als einfache Tabelle im JSON-Format:
{
  "type": "table",
  "title": "Titel der Tabelle",
  "headers": ["Spalte1", "Spalte2", "Spalte3"],
  "rows": [
    ["Wert1", "Wert2", "Wert3"],
    ["Wert4", "Wert5", "Wert6"]
  ]
}

WICHTIG:
- Extrahiere strukturierte Informationen aus dem Text
- Jede Zeile muss genau so viele Spalten haben wie Headers definiert sind
- Verwende leere Strings "" wenn ein Feld nicht gefüllt werden kann
- Die Headers sollten die gewünschten Spalten widerspiegeln (falls angegeben)
"""

    return base_prompt + f"""
Formatiere als {format_type} im gültigen JSON-Format.
Stelle sicher, dass die Ausgabe dem erwarteten Schema entspricht.
"""

async def _call_llm_for_formatting(prompt: str, format_type: str) -> Dict[str, Any]:
    """Call LLM to generate formatted content."""
    try:
        from llm_config import get_client, get_model

        client = get_client("rewrite")

        response = client.chat.completions.create(
            model=get_model("rewrite"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Balanced creativity and consistency
            max_tokens=2000,
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        elif not content.startswith("{") and "{" in content:
            first_brace = content.find("{")
            content = content[first_brace:]

        result = json.loads(content)

        # Ensure type field is set
        if "type" not in result:
            result["type"] = format_type

        return result

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise

# =============================================================================
# CONTENT MERGING
# =============================================================================

def merge_structured_content(
    existing_content: Optional[Dict[str, Any]],
    new_content: Dict[str, Any],
    merge_strategy: str = "replace"
) -> Dict[str, Any]:
    """
    Merge new structured content with existing content.

    Args:
        existing_content: Current structured content (can be None)
        new_content: New content to merge
        merge_strategy: How to merge ("replace", "append", "update")

    Returns:
        Merged content
    """
    if merge_strategy == "replace" or existing_content is None:
        return new_content.copy()

    if merge_strategy == "append":
        return _append_structured_content(existing_content, new_content)

    if merge_strategy == "update":
        return _update_structured_content(existing_content, new_content)

    # Default to replace
    return new_content.copy()

def _append_structured_content(existing: Dict[str, Any], new_content: Dict[str, Any]) -> Dict[str, Any]:
    """Append new content to existing structure."""
    result = existing.copy()

    content_type = existing.get("type", "")

    if content_type == "action_list":
        existing_items = existing.get("items", [])
        new_items = new_content.get("items", [])
        result["items"] = existing_items + new_items

    elif content_type == "pros_cons_table":
        result["pros"] = existing.get("pros", []) + new_content.get("pros", [])
        result["cons"] = existing.get("cons", []) + new_content.get("cons", [])

    # For other types, just replace
    else:
        result = new_content.copy()

    return result

def _update_structured_content(existing: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update existing content with new values."""
    result = existing.copy()

    def deep_update(target: Dict[str, Any], source: Dict[str, Any]):
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                deep_update(target[key], value)
            else:
                target[key] = value

    deep_update(result, updates)
    return result

# =============================================================================
# REPOSITORY INTEGRATION
# =============================================================================

def update_canvas_node_structured(
    node_id: str,
    content_json: Dict[str, Any],
    format_type: str
) -> bool:
    """
    Update a canvas node with structured content.

    Args:
        node_id: ID of the canvas node
        content_json: Structured content
        format_type: Format type for validation

    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate content
        is_valid, error_msg = validate_format_schema(content_json, format_type)
        if not is_valid:
            logger.error(f"Invalid structured content: {error_msg}")
            return False

        # Get repository
        repo = CanvasRepository()

        # Get existing node
        existing_node = repo.get_node(node_id)
        if not existing_node:
            logger.error(f"Node {node_id} not found")
            return False

        # Update structured fields
        existing_node.format_schema = get_format_schema(format_type)
        existing_node.content_json = content_json
        existing_node.last_formatted = datetime.now()

        # Save
        repo.update_node(existing_node)

        logger.info(f"Updated node {node_id} with structured content ({format_type})")
        return True

    except Exception as e:
        logger.error(f"Failed to update structured content: {e}")
        return False

# =============================================================================
# SQL TOOLS FOR STRUCTURED CONTENT
# =============================================================================

def update_idea_structured_content(
    idea_id: str,
    new_content_json: Dict[str, Any],
    format_type: str,
    merge: bool = False
) -> Dict[str, Any]:
    """
    SQL Tool: Update idea with structured content.

    This is designed to be called by LLMs via tool execution.

    Args:
        idea_id: Database ID of the idea/canvas node
        new_content_json: New structured content
        format_type: Format type (action_list, pros_cons_table, etc.)
        merge: Whether to merge with existing content

    Returns:
        Dict with success status and details
    """
    try:
        logger.info(f"SQL Tool: Updating idea {idea_id} with {format_type} content")

        # Validate format type
        if not validate_format_type(format_type):
            available = get_available_format_types()
            return {
                "success": False,
                "error": f"Unsupported format type '{format_type}'. Available: {available}",
                "idea_id": idea_id
            }

        # Validate content schema
        is_valid, error_msg = validate_format_schema(new_content_json, format_type)
        if not is_valid:
            return {
                "success": False,
                "error": f"Schema validation failed: {error_msg}",
                "idea_id": idea_id,
                "format_type": format_type
            }

        # Get repository
        repo = CanvasRepository()

        # Get existing node
        existing_node = repo.get_node(idea_id)
        if not existing_node:
            return {
                "success": False,
                "error": f"Idea/Canvas node {idea_id} not found",
                "idea_id": idea_id
            }

        # Handle merging if requested
        final_content = new_content_json
        if merge and existing_node.content_json:
            final_content = merge_structured_content(
                existing_node.content_json,
                new_content_json
            )

        # Update node
        existing_node.format_schema = get_format_schema(format_type)
        existing_node.content_json = final_content
        existing_node.last_formatted = datetime.now()

        # Save to database
        repo.update_node(existing_node)

        # Broadcast to Electron UI
        _broadcast_structured_update(existing_node.id, final_content, format_type)

        logger.info(f"Successfully updated idea {idea_id} with {format_type}")

        return {
            "success": True,
            "idea_id": idea_id,
            "format_type": format_type,
            "content_preview": format_content_preview(final_content, format_type),
            "updated_at": existing_node.last_formatted.isoformat()
        }

    except Exception as e:
        logger.error(f"SQL Tool error: {e}")
        return {
            "success": False,
            "error": str(e),
            "idea_id": idea_id,
            "format_type": format_type
        }

def query_structured_content(
    idea_id: str
) -> Dict[str, Any]:
    """
    SQL Tool: Query structured content of an idea.

    Args:
        idea_id: Database ID of the idea/canvas node

    Returns:
        Dict with content and metadata
    """
    try:
        repo = CanvasRepository()
        node = repo.get_node(idea_id)

        if not node:
            return {
                "success": False,
                "error": f"Idea {idea_id} not found",
                "idea_id": idea_id
            }

        result = {
            "success": True,
            "idea_id": idea_id,
            "has_structured_content": node.content_json is not None,
            "format_type": None,
            "content": None,
            "last_formatted": None
        }

        if node.content_json:
            # Determine format type from content
            content_type = node.content_json.get("type")
            result.update({
                "format_type": content_type,
                "content": node.content_json,
                "content_preview": format_content_preview(node.content_json, content_type) if content_type else None,
                "last_formatted": node.last_formatted.isoformat() if node.last_formatted else None
            })

        return result

    except Exception as e:
        logger.error(f"Query error: {e}")
        return {
            "success": False,
            "error": str(e),
            "idea_id": idea_id
        }

def _broadcast_structured_update(node_id: str, content: Dict[str, Any], format_type: str):
    """
    Broadcast structured content update to Electron UI.

    Args:
        node_id: Canvas node ID
        content: Structured content
        format_type: Format type
    """
    try:
        update_message = {
            "type": "node_structured_update",
            "node_id": node_id,
            "structured_content": content,
            "format_type": format_type,
            "timestamp": datetime.now().isoformat()
        }

        _broadcast_to_electron(update_message)
        logger.debug(f"Broadcast structured update for node {node_id}")

    except Exception as e:
        logger.error(f"Failed to broadcast structured update: {e}")

# =============================================================================
# VOICE-FRIENDLY TABLE FORMATTING TOOL
# =============================================================================

def format_idea_as_table(
    idea_name: str = None,
    custom_columns: List[str] = None,
    format_instruction: str = ""
) -> str:
    """
    Format an existing idea's content into a structured table.

    Voice triggers:
    - "Formatiere die Idee X als Tabelle"
    - "Erstelle eine Tabelle aus der Idee X"
    - "Format idea X as table with columns A, B, C"

    Args:
        idea_name: Name/title of the idea to format
        custom_columns: Optional list of column headers (e.g., ["Calls ID", "Requirement", "Content"])
        format_instruction: Additional formatting instructions from user

    Returns:
        Confirmation message with table preview
    """
    if not idea_name:
        return "Fehler: Kein Ideen-Name angegeben. Bitte sag mir welche Idee formatiert werden soll."

    try:
        # 1. Find the idea by name
        from tools.idea_tools import _get_current_bubble_id
        repo = CanvasRepository()

        # Get current bubble
        bubble_id = _get_current_bubble_id()
        if not bubble_id:
            return "Fehler: Bitte betrete zuerst einen Space mit 'enter_bubble'."

        # Search for the idea in current bubble
        all_nodes = repo.list_nodes(limit=500)
        matching_node = None

        # Try exact match first
        for node in all_nodes:
            if node.linked_idea_id == bubble_id:
                if node.title and node.title.lower() == idea_name.lower():
                    matching_node = node
                    break

        # Try partial match if no exact match
        if not matching_node:
            idea_name_lower = idea_name.lower()
            for node in all_nodes:
                if node.linked_idea_id == bubble_id:
                    if node.title and idea_name_lower in node.title.lower():
                        matching_node = node
                        break

        if not matching_node:
            return f"Fehler: Idee '{idea_name}' nicht im aktuellen Space gefunden."

        # 2. Get the content
        idea_content = matching_node.content or matching_node.title
        if not idea_content or len(idea_content.strip()) < 10:
            return f"Fehler: Die Idee '{idea_name}' hat nicht genug Inhalt zum Formatieren."

        # 3. Build additional context with column information
        additional_context = format_instruction or ""
        if custom_columns:
            columns_str = ", ".join(custom_columns)
            additional_context += f"\n\nGewünschte Spalten: {columns_str}"
            additional_context += f"\nVerwende genau diese {len(custom_columns)} Spalten als Headers."

        # 4. Call LLM to transform into table structure
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    format_idea_content(
                        idea_content=idea_content,
                        format_type="simple_table",
                        idea_title=matching_node.title,
                        additional_context=additional_context
                    )
                )
                result = future.result(timeout=30)
        else:
            result = asyncio.run(format_idea_content(
                idea_content=idea_content,
                format_type="simple_table",
                idea_title=matching_node.title,
                additional_context=additional_context
            ))

        if not result.get("success"):
            error_msg = result.get("error", "Unbekannter Fehler")
            return f"Fehler beim Formatieren: {error_msg}"

        table_content = result.get("content")
        if not table_content:
            return "Fehler: LLM konnte keine Tabelle generieren."

        # 5. If custom columns provided, ensure they're used
        if custom_columns:
            table_content["headers"] = custom_columns
            # Adjust rows if needed
            num_cols = len(custom_columns)
            adjusted_rows = []
            for row in table_content.get("rows", []):
                if len(row) < num_cols:
                    row = row + [""] * (num_cols - len(row))
                elif len(row) > num_cols:
                    row = row[:num_cols]
                adjusted_rows.append(row)
            table_content["rows"] = adjusted_rows

        # 6. Validate against schema
        is_valid, error_msg = _validate_simple_table(table_content)
        if not is_valid:
            return f"Fehler bei der Tabellenvalidierung: {error_msg}"

        # 7. Save to content_json
        matching_node.content_json = table_content
        matching_node.last_formatted = datetime.now()
        repo.update_node(matching_node)

        # 8. Send IPC message to update Electron UI
        _send_table_to_electron(matching_node.id, bubble_id, table_content)

        # 9. Return preview
        headers = table_content.get("headers", [])
        rows = table_content.get("rows", [])
        preview = f"Tabelle erstellt für '{matching_node.title}':\n"
        preview += f"Spalten: {', '.join(headers)}\n"
        preview += f"Zeilen: {len(rows)}"

        if rows:
            preview += f"\nBeispiel erste Zeile: {' | '.join(str(cell)[:20] for cell in rows[0])}"

        logger.info(f"Formatted idea '{idea_name}' as table with {len(headers)} columns and {len(rows)} rows")
        return preview

    except Exception as e:
        logger.error(f"format_idea_as_table error: {e}")
        return f"Fehler beim Tabellenformatieren: {str(e)}"


def _send_table_to_electron(node_id: str, bubble_id: str, table_data: Dict[str, Any]):
    """Send table content to Electron for rendering."""
    try:
        import json as json_module

        message = {
            "type": "node_structured_update",
            "node_id": node_id,
            "bubble_id": bubble_id,
            "content": table_data,
            "action": "update"
        }

        # Send via stdout (Electron backend IPC)
        print(json_module.dumps(message), flush=True)
        logger.debug(f"Sent table update to Electron for node {node_id}")

    except Exception as e:
        logger.error(f"Failed to send table to Electron: {e}")


def _broadcast_to_electron(message: Dict[str, Any]):
    """Broadcast any message to Electron via stdout."""
    try:
        import json as json_module
        print(json_module.dumps(message), flush=True)
    except Exception as e:
        logger.error(f"Failed to broadcast to Electron: {e}")


# =============================================================================
# TOOL REGISTRY FOR LLM ACCESS
# =============================================================================

STRUCTURED_FORMATTING_TOOLS = {
    "update_idea_structured_content": update_idea_structured_content,
    "query_structured_content": query_structured_content,
    "validate_format_schema": lambda content, fmt: {"valid": validate_format_schema(content, fmt)[0], "error": validate_format_schema(content, fmt)[1]},
    "get_supported_formats": lambda: {"formats": get_supported_formats()},
    "format_idea_as_table": format_idea_as_table,
}

def register_structured_formatting_tools(tools_manager):
    """
    Register structured formatting tools with the tools manager.

    Args:
        tools_manager: Tools manager instance
    """
    print("Registering structured formatting tools...")
    for tool_name, tool_func in STRUCTURED_FORMATTING_TOOLS.items():
        try:
            tools_manager.register_with_observer(tool_name, tool_func)
            print(f"  - {tool_name}")
        except ValueError:
            print(f"  - {tool_name} (skipped - already registered)")

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_supported_formats() -> List[str]:
    """Get list of supported format types."""
    return get_available_format_types()

def format_content_preview(content_json: Dict[str, Any], format_type: str, max_length: int = 200) -> str:
    """
    Generate a human-readable preview of structured content.

    Args:
        content_json: Structured content
        format_type: Format type
        max_length: Maximum preview length

    Returns:
        Preview string
    """
    try:
        if format_type == "action_list":
            items = content_json.get("items", [])
            preview = f"Aktionsliste mit {len(items)} Aufgaben"
            if items:
                first_task = items[0].get("task", "")
                if first_task:
                    preview += f": {first_task[:50]}..."

        elif format_type == "pros_cons_table":
            pros = len(content_json.get("pros", []))
            cons = len(content_json.get("cons", []))
            preview = f"Vor-/Nachteile: {pros} Pro, {cons} Contra"

        elif format_type == "technical_specs":
            specs = len(content_json.get("specifications", []))
            preview = f"Technische Specs: {specs} Anforderungen"

        elif format_type == "hierarchy":
            levels = len(content_json.get("levels", []))
            preview = f"Hierarchie mit {levels} Ebenen"

        elif format_type == "comparison_table":
            options = len(content_json.get("options", []))
            criteria = len(content_json.get("criteria", []))
            preview = f"Vergleich: {options} Optionen, {criteria} Kriterien"

        elif format_type == "simple_table" or format_type == "table":
            headers = content_json.get("headers", [])
            rows = content_json.get("rows", [])
            preview = f"Tabelle: {len(headers)} Spalten, {len(rows)} Zeilen"
            if headers:
                preview += f" ({', '.join(headers[:3])}{'...' if len(headers) > 3 else ''})"

        else:
            preview = f"Strukturiertes Format: {format_type}"

        return preview[:max_length]

    except Exception as e:
        logger.error(f"Preview generation failed: {e}")
        return f"Strukturiertes Format: {format_type}"