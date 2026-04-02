"""
Summary Tools - Voice-callable summarization functions

These tools allow voice agents to create AI-powered summaries of ideas.

Pipeline (using OpenRouter for all LLM calls):
1. summarize_idea: Get content, call GPT-4o-mini via OpenRouter for initial summary
2. Optionally call Gemini via OpenRouter for rewrite/polish
3. Save to database

Usage:
    Voice: "Summarize this idea"
    Voice: "Create a summary of my cooking notes"
"""

import sys
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING

from llm_config import get_model, get_client

# Add python/ root to path (4 levels up from spaces/ideas/tools/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from data import CanvasRepository, IdeasRepository, ProjectsRepository, ShuttlesRepository, ShuttleStage, STAGE_PROGRESS

# OpenAI import check (still needed for type reference in legacy code)
HAS_OPENAI = False
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    OpenAI = None  # Define as None so type annotations don't fail

# Import Electron broadcast and bubble position getter
try:
    from tools.workspace_tools import _broadcast_to_electron, get_bubble_position
except ImportError:
    def _broadcast_to_electron(msg):
        pass
    def get_bubble_position(bubble_db_id):
        return None

logger = logging.getLogger(__name__)

# Repository instances
_ideas_repo: Optional[IdeasRepository] = None
_canvas_repo: Optional[CanvasRepository] = None
_shuttles_repo: Optional[ShuttlesRepository] = None
_projects_repo: Optional[ProjectsRepository] = None

# LLM Client (provider-agnostic via llm_config) - use Any for type since OpenAI might not be imported
_openrouter_client: Any = None


def _get_ideas_repo() -> IdeasRepository:
    """Get or create ideas repository."""
    global _ideas_repo
    if _ideas_repo is None:
        _ideas_repo = IdeasRepository()
    return _ideas_repo


def _get_canvas_repo() -> CanvasRepository:
    """Get or create canvas repository."""
    global _canvas_repo
    if _canvas_repo is None:
        _canvas_repo = CanvasRepository()
    return _canvas_repo


def _get_shuttles_repo() -> ShuttlesRepository:
    """Get or create shuttles repository."""
    global _shuttles_repo
    if _shuttles_repo is None:
        _shuttles_repo = ShuttlesRepository()
    return _shuttles_repo


def _get_projects_repo() -> ProjectsRepository:
    """Get or create projects repository."""
    global _projects_repo
    if _projects_repo is None:
        _projects_repo = ProjectsRepository()
    return _projects_repo


def _broadcast_stage_update(shuttle_id: str, stage: str, shuttle_db_id: str = None):
    """
    Broadcast shuttle stage update to Electron for real-time visualization.

    Args:
        shuttle_id: Visual shuttle ID
        stage: Stage key from ShuttleStage (mining, requirements, validation, etc.)
        shuttle_db_id: Database ID to also update persistence (optional)
    """
    # Broadcast to Electron
    _broadcast_to_electron({
        "type": "shuttle_stage_update",
        "shuttle_id": shuttle_id,
        "stage": stage,
        "progress": STAGE_PROGRESS.get(stage, 0.0)
    })

    # Update database if shuttle_db_id provided
    if shuttle_db_id:
        repo = _get_shuttles_repo()
        repo.update_stage(shuttle_db_id, stage)

    logger.info(f"Shuttle {shuttle_id} stage: {stage}")


def _get_openrouter_client() -> Optional[Any]:
    """Get or create LLM client (provider-agnostic via llm_config)."""
    global _openrouter_client
    if _openrouter_client is None:
        try:
            _openrouter_client = get_client("summary")
            logger.info("LLM client initialized via llm_config")
        except Exception as e:
            logger.warning(f"Failed to create LLM client: {e}")
    return _openrouter_client


def _get_idea_content(idea_id: str) -> tuple:
    """
    Get all content from an idea (bubble) for summarization.

    Returns:
        tuple: (title, combined_content, node_count)
    """
    ideas_repo = _get_ideas_repo()
    canvas_repo = _get_canvas_repo()

    idea = ideas_repo.get(idea_id)
    if not idea:
        return None, None, 0

    # Get all nodes linked to this idea
    all_nodes = canvas_repo.list_nodes(limit=1000)
    idea_nodes = [n for n in all_nodes if n.linked_idea_id == idea_id]

    # Combine all content
    content_parts = []
    for node in idea_nodes:
        if node.title:
            content_parts.append(f"## {node.title}")
        if node.content:
            content_parts.append(node.content)
        content_parts.append("")

    combined_content = "\n".join(content_parts)

    return idea.title, combined_content, len(idea_nodes)


def _call_summarization(title: str, content: str, max_tokens: int = 500) -> Optional[str]:
    """
    Call OpenRouter API for summarization using GPT-4o-mini.
    """
    client = _get_openrouter_client()
    if not client:
        logger.error("OpenRouter client not available")
        return None

    # Use GPT-4o-mini for cost-efficient summarization
    model = get_model("summary")

    system_prompt = """You are a concise summarization assistant.
Your task is to create clear, informative summaries of ideas and notes.
Focus on:
- Key concepts and main points
- Important details and insights
- Actionable items if present
Keep the summary focused and avoid redundancy."""

    user_prompt = f"""Summarize the following content:

Title: {title or 'Untitled'}

Content:
{content}

Provide a clear, concise summary that captures the essence of this idea."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.5
        )

        summary = response.choices[0].message.content.strip()
        logger.info(f"✓ OpenRouter ({model}) generated summary ({len(summary)} chars)")
        return summary

    except Exception as e:
        logger.error(f"OpenRouter API error: {e}")
        return None


def _call_rewrite(
    initial_summary: str,
    title: str = None,
    style: str = "concise"
) -> Optional[str]:
    """
    Call OpenRouter API with Gemini to rewrite/polish the summary.
    """
    client = _get_openrouter_client()
    if not client:
        return initial_summary

    # Use Gemini for rewrite (larger context, good at following style instructions)
    model = get_model("rewrite")

    style_instructions = {
        "concise": "Make it more concise and punchy. Remove any fluff.",
        "detailed": "Expand with relevant details while keeping it organized.",
        "actionable": "Focus on action items and next steps. Use bullet points."
    }

    style_guide = style_instructions.get(style, style_instructions["concise"])

    prompt = f"""Rewrite this summary to make it better:

Title: {title or 'Untitled'}

Original summary:
{initial_summary}

Instructions: {style_guide}

Provide only the rewritten summary, no explanations."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )

        rewritten = response.choices[0].message.content.strip()
        logger.info(f"✓ OpenRouter ({model}) rewrote summary ({len(rewritten)} chars, style: {style})")
        return rewritten

    except Exception as e:
        logger.error(f"OpenRouter rewrite error: {e}")
        return initial_summary  # Fallback to original


# ==============================================================================
# CLIENT TOOLS
# ==============================================================================

def summarize_idea(params: Dict[str, Any]) -> str:
    """
    Summarize a specific idea/bubble or a single note using AI via OpenRouter.

    Voice triggers: "Summarize this idea", "Create summary for cooking"

    Args (via params):
        idea_name: Name of the idea/bubble OR note to summarize (optional - uses current bubble if not specified)
        style: Summary style - "concise", "detailed", "actionable" (default: "concise")

    Returns:
        str: The generated summary or error message
    """
    idea_name = (params.get("idea_name") or "").strip()
    style = params.get("style") or "concise"

    logger.info(f"summarize_idea called: idea_name='{idea_name}', style='{style}'")

    # Check OpenRouter availability
    if not HAS_OPENAI:
        return "Summarization requires OpenAI package. Install with: pip install openai"

    if not _get_openrouter_client():
        return "LLM client not available. Check your API key configuration."

    # Get current bubble context - use local import from spaces
    current_bubble_id = None
    try:
        from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id
        current_bubble_id = get_current_bubble_db_id()
    except ImportError:
        pass

    ideas_repo = _get_ideas_repo()
    canvas_repo = _get_canvas_repo()

    # Strategy:
    # 1. If idea_name given, first try to find a NOTE (CanvasNode) in current bubble
    # 2. If not found, try to find a BUBBLE (Idea)
    # 3. If no name given, summarize entire current bubble

    target_node = None
    target_idea_id = None

    if idea_name:
        # First: Search for a NOTE (CanvasNode) in current bubble
        all_nodes = canvas_repo.list_nodes(limit=1000)

        # If inside a bubble, search ONLY nodes in that bubble
        if current_bubble_id:
            bubble_nodes = [n for n in all_nodes if n.linked_idea_id == current_bubble_id]
        else:
            bubble_nodes = all_nodes

        # Case-insensitive search for note title
        idea_name_lower = idea_name.lower()
        for node in bubble_nodes:
            node_title = (node.title or "").lower()
            if idea_name_lower == node_title or idea_name_lower in node_title:
                target_node = node
                logger.info(f"Found matching note: '{node.title}' (id: {node.id})")
                break

        # Second: If no note found, search for a BUBBLE (Idea)
        if not target_node:
            idea = ideas_repo.get_by_title(idea_name)
            if idea:
                target_idea_id = idea.id
                logger.info(f"Found matching bubble: '{idea.title}' (id: {idea.id})")
    else:
        # No name given - use current bubble
        if current_bubble_id:
            target_idea_id = current_bubble_id
        else:
            return "Which idea should I summarize? Say the name or enter a bubble first."

    # Now generate summary based on what we found
    if target_node:
        # Summarize a single NOTE
        title = target_node.title or "Untitled Note"
        content = target_node.content or ""

        if not content:
            return f"'{title}' has no content to summarize."

        # Generate summary for single note
        initial_summary = _call_summarization(title, content)
        if not initial_summary:
            return "Failed to generate summary. Check your API key configuration."

        final_summary = _call_rewrite(initial_summary, title, style)

        # Save summary to the node
        target_node.summary = final_summary
        canvas_repo.update_node(target_node)
        logger.info(f"Saved summary to note {target_node.id}")

        # Broadcast
        _broadcast_to_electron({
            "type": "idea_summarized",
            "idea_id": target_node.linked_idea_id or "unknown",
            "node_id": target_node.id,
            "idea_title": title,
            "summary": final_summary,
            "style": style,
            "node_count": 1
        })

        return f"Here's the summary of '{title}': {final_summary}"

    elif target_idea_id:
        # Summarize entire BUBBLE (all notes inside)
        title, content, node_count = _get_idea_content(target_idea_id)

        if not content or node_count == 0:
            return f"'{title or 'This space'}' has no content to summarize yet. Add some notes first!"

        # Step 1: Initial summarization with GPT-4o-mini via OpenRouter
        initial_summary = _call_summarization(title, content)
        if not initial_summary:
            return "Failed to generate summary. Check your API key configuration."

        # Step 2: Rewrite with Gemini via OpenRouter
        final_summary = _call_rewrite(initial_summary, title, style)

        # Save summary to the first node
        all_nodes = canvas_repo.list_nodes(limit=1000)
        idea_nodes = [n for n in all_nodes if n.linked_idea_id == target_idea_id]

        if idea_nodes:
            first_node = idea_nodes[0]
            first_node.summary = final_summary
            canvas_repo.update_node(first_node)
            logger.info(f"Saved summary to node {first_node.id}")

        # Broadcast to Electron
        _broadcast_to_electron({
            "type": "idea_summarized",
            "idea_id": target_idea_id,
            "idea_title": title,
            "summary": final_summary,
            "style": style,
            "node_count": node_count
        })

        return f"Here's the summary of '{title}': {final_summary}"

    else:
        return f"I couldn't find an idea or note called '{idea_name}'."

def list_summaries(params: Dict[str, Any]) -> str:
    """
    List all ideas that have summaries.

    Voice triggers: "Show my summaries", "What ideas have summaries?"

    Returns:
        str: List of ideas with summaries
    """
    logger.debug("list_summaries: listing all summaries")
    canvas_repo = _get_canvas_repo()
    ideas_repo = _get_ideas_repo()

    # Find nodes with summaries
    all_nodes = canvas_repo.list_nodes(limit=1000)
    nodes_with_summaries = [n for n in all_nodes if n.summary]

    if not nodes_with_summaries:
        return "No summaries yet. Say 'summarize this idea' to create one."

    # Get unique idea IDs
    idea_ids = set(n.linked_idea_id for n in nodes_with_summaries if n.linked_idea_id)

    summaries = []
    for idea_id in idea_ids:
        idea = ideas_repo.get(idea_id)
        if idea:
            summaries.append(idea.title)

    return f"You have summaries for {len(summaries)} ideas: {', '.join(summaries)}."


def get_summary(params: Dict[str, Any]) -> str:
    """
    Get the existing summary for an idea.

    Voice triggers: "Read me the summary", "What's the summary of cooking?"

    Args (via params):
        idea_name: Name of the idea (optional - uses current if not specified)

    Returns:
        str: The summary or message if none exists
    """
    idea_name = params.get("idea_name", "").strip()
    logger.debug("get_summary: idea_name=%s", idea_name)

    # Get current bubble if no name specified - use local import from spaces
    if not idea_name:
        try:
            from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id
            current_id = get_current_bubble_db_id()
            if current_id:
                idea = _get_ideas_repo().get(current_id)
                if idea:
                    idea_name = idea.title
        except ImportError:
            pass

    if not idea_name:
        return "Which idea's summary would you like? Say the name or enter a bubble first."

    # Find the idea
    ideas_repo = _get_ideas_repo()
    idea = ideas_repo.get_by_title(idea_name)
    if not idea:
        return f"I couldn't find an idea called '{idea_name}'."

    # Get summary from nodes
    canvas_repo = _get_canvas_repo()
    all_nodes = canvas_repo.list_nodes(limit=1000)
    idea_nodes = [n for n in all_nodes if n.linked_idea_id == idea.id and n.summary]

    if not idea_nodes:
        return f"'{idea.title}' doesn't have a summary yet. Say 'summarize this idea' to create one."

    return f"Summary of '{idea.title}': {idea_nodes[0].summary}"


def generate_white_paper(params: Dict[str, Any]) -> str:
    """
    Generate a structured White Paper document from linked ideas using graph traversal.

    Voice triggers: "Generate a white paper from [idea]", "Create project overview from [idea]"

    Args (via params):
        start_node: Name of the idea/note to start from (required)
        task: Description of what kind of document to create (e.g., "project overview", "technical spec")
        max_depth: Maximum graph traversal depth (default: 5)

    Returns:
        str: Confirmation message with summary of generated document
    """
    start_node_name = params.get("start_node", "").strip()
    task = params.get("task", "project overview").strip()
    max_depth = int(params.get("max_depth", 5))

    logger.info(f"generate_white_paper called: start_node='{start_node_name}', task='{task}', max_depth={max_depth}")

    # Check OpenRouter availability
    if not HAS_OPENAI:
        return "White Paper generation requires OpenAI package. Install with: pip install openai"

    if not _get_openrouter_client():
        return "LLM client not available. Check your API key configuration."

    if not start_node_name:
        return "Please specify which idea to start from. Say 'generate white paper from [idea name]'."

    # Get current bubble context - use local import from spaces
    current_bubble_id = None
    try:
        from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id
        current_bubble_id = get_current_bubble_db_id()
    except ImportError:
        pass

    canvas_repo = _get_canvas_repo()

    # Find the start node
    start_node = canvas_repo.get_node_by_title(start_node_name, idea_id=current_bubble_id)
    if not start_node:
        return f"I couldn't find a note called '{start_node_name}'. Make sure you're in the right bubble."

    # Traverse linked nodes using BFS
    nodes_by_distance = canvas_repo.traverse_linked_nodes(
        start_node_id=start_node.id,
        max_depth=max_depth,
        idea_id=current_bubble_id
    )

    if not nodes_by_distance:
        return f"No linked ideas found for '{start_node_name}'. Try linking some notes first."

    # Count total nodes
    total_nodes = sum(len(nodes) for nodes in nodes_by_distance.values())

    # Build hierarchical prompt for LLM
    hierarchical_content = _build_hierarchical_prompt(nodes_by_distance, task)

    # Generate White Paper using OpenRouter
    white_paper_md = _generate_white_paper_content(
        title=start_node.title or start_node_name,
        task=task,
        hierarchical_content=hierarchical_content
    )

    if not white_paper_md:
        return "Failed to generate White Paper. Check your API key configuration."

    # Create a canvas node for the whitepaper (appears as draggable node on canvas)
    wp_title = f"White Paper: {start_node.title or start_node_name}"

    # Position near start node or default
    wp_x = (start_node.x or 100) + 400
    wp_y = start_node.y or 100

    wp_node = canvas_repo.create_node(
        node_type="whitepaper",
        title=wp_title,
        content=white_paper_md,
        linked_idea_id=current_bubble_id,
        x=wp_x,
        y=wp_y
    )

    # Create edge from start node to whitepaper
    if wp_node:
        canvas_repo.create_edge(
            from_node_id=start_node.id,
            to_node_id=wp_node.id,
            edge_type="generated"
        )
        logger.info(f"Created whitepaper canvas node: {wp_node.id}")

        # Broadcast node creation to refresh canvas
        _broadcast_to_electron({
            "type": "canvas_node_created",
            "node_id": wp_node.id,
            "node_type": "whitepaper",
            "title": wp_title,
            "bubble_id": current_bubble_id
        })

    return f"I've created a {task} document from '{start_node.title}' with {total_nodes} linked ideas. It's now on your canvas."


def _build_hierarchical_prompt(nodes_by_distance: Dict[int, list], task: str) -> str:
    """
    Build a hierarchical prompt from nodes grouped by distance.

    Distance 0 = Main topic (Title)
    Distance 1 = Main sections
    Distance 2+ = Sub-sections
    """
    sections = []

    for distance in sorted(nodes_by_distance.keys()):
        nodes = nodes_by_distance[distance]

        if distance == 0:
            # Main topic
            for node in nodes:
                sections.append(f"### MAIN TOPIC (use as document title and introduction):")
                sections.append(f"Title: {node.title or 'Untitled'}")
                if node.content:
                    sections.append(f"Content: {node.content}")
                sections.append("")

        elif distance == 1:
            # Primary sections
            sections.append(f"### PRIMARY SECTIONS (use as main headings ## ):")
            for node in nodes:
                sections.append(f"- Section: {node.title or 'Untitled'}")
                if node.content:
                    sections.append(f"  Content: {node.content}")
            sections.append("")

        else:
            # Sub-sections
            sections.append(f"### SUPPORTING DETAILS (depth {distance}, use as sub-headings ### or bullet points):")
            for node in nodes:
                sections.append(f"- {node.title or 'Untitled'}: {node.content or '(no content)'}")
            sections.append("")

    return "\n".join(sections)


def _generate_white_paper_content(title: str, task: str, hierarchical_content: str) -> Optional[str]:
    """
    Call OpenRouter API to generate the White Paper document.
    """
    client = _get_openrouter_client()
    if not client:
        logger.error("OpenRouter client not available")
        return None

    # Use GPT-4o for better document generation
    model = get_model("whitepaper")

    system_prompt = """You are a professional technical writer. Your task is to create well-structured documents from interconnected ideas.

Output format: Clean Markdown with proper hierarchy:
- # for the document title
- ## for main sections
- ### for sub-sections
- Bullet points for lists
- Bold for emphasis

Keep the document focused, professional, and actionable. Synthesize the ideas into a coherent narrative, don't just list them."""

    user_prompt = f"""Create a "{task}" document from the following interconnected ideas:

{hierarchical_content}

Requirements:
1. Use the MAIN TOPIC as your document title and write a brief introduction
2. Use PRIMARY SECTIONS as your main ## headings
3. Integrate SUPPORTING DETAILS naturally under relevant sections
4. Synthesize and connect the ideas - don't just copy them
5. Make it professional and actionable
6. Target length: 500-1000 words

Output the document in clean Markdown format."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )

        content = response.choices[0].message.content.strip()
        logger.info(f"✓ White Paper generated ({len(content)} chars)")
        return content

    except Exception as e:
        logger.error(f"OpenRouter White Paper generation error: {e}")
        return None


# ==============================================================================
# PROJECT STRUCTURE GENERATION
# ==============================================================================

def generate_project_structure(params: Dict[str, Any]) -> str:
    """
    Convert bubble whitepaper/notes into a structured project with requirements.

    Voice triggers: "Generate project structure", "Extract requirements from this idea",
                   "Turn this into a project spec"

    This creates:
    - Project name and description
    - Functional requirements
    - Non-functional requirements
    - Feature list with descriptions
    - Implementation phases

    Args (via params):
        bubble_name: Name of bubble to structure (optional - uses current)
        create_nodes: Whether to create canvas nodes for each feature (default: True)

    Returns:
        str: Summary of generated project structure
    """
    bubble_name = params.get("bubble_name", "").strip()
    create_nodes = params.get("create_nodes", True)

    logger.info(f"generate_project_structure called: bubble_name='{bubble_name}', create_nodes={create_nodes}")

    # Check OpenRouter availability
    if not HAS_OPENAI:
        return "Project structure generation requires OpenAI package. Install with: pip install openai"

    if not _get_openrouter_client():
        return "LLM client not available. Check your API key configuration."

    # Get current bubble if no name specified - use local import from spaces
    current_bubble_id = None
    try:
        from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id
        current_bubble_id = get_current_bubble_db_id()
    except ImportError:
        pass

    ideas_repo = _get_ideas_repo()
    canvas_repo = _get_canvas_repo()

    # Find the bubble
    if bubble_name:
        idea = ideas_repo.get_by_title(bubble_name)
        if not idea:
            return f"Couldn't find bubble '{bubble_name}'"
    else:
        if current_bubble_id:
            idea = ideas_repo.get(current_bubble_id)
            if not idea:
                return "Current bubble not found"
        else:
            return "Specify a bubble name or enter one first."

    # Get bubble content
    title, content, node_count = _get_idea_content(idea.id)

    if not content or node_count == 0:
        return f"'{title}' has no content to analyze. Add a whitepaper or notes first!"

    # Generate project structure using OpenRouter
    project_structure = _call_project_structuring(title, content)

    if not project_structure:
        return "Failed to generate project structure. Try again."

    # Store in idea metadata
    idea.metadata["project_structure"] = project_structure
    ideas_repo.update(idea)

    # Create canvas nodes for each feature if requested
    created_nodes = []
    if create_nodes and project_structure.get("features"):
        # Get existing nodes to calculate position
        all_nodes = canvas_repo.list_nodes(limit=1000)
        idea_nodes = [n for n in all_nodes if n.linked_idea_id == idea.id]

        # Find max y position to place new nodes below
        max_y = max((n.y for n in idea_nodes), default=100) + 200
        x_offset = 100

        for i, feature in enumerate(project_structure["features"]):
            # Create a node for each feature
            feature_node = canvas_repo.create_node(
                node_type="feature",
                title=feature.get("name", f"Feature {i+1}"),
                content=f"**Description:** {feature.get('description', '')}\n\n**Priority:** {feature.get('priority', 'medium')}",
                linked_idea_id=idea.id,
                x=x_offset + (i % 3) * 350,
                y=max_y + (i // 3) * 200
            )
            created_nodes.append(feature_node)
            logger.info(f"Created feature node: {feature_node.title}")

    # Broadcast to Electron
    _broadcast_to_electron({
        "type": "project_structure_generated",
        "bubble_id": idea.id,
        "bubble_title": title,
        "structure": project_structure,
        "created_nodes": len(created_nodes),
        "node_ids": [n.id for n in created_nodes]
    })

    # Format response
    features = project_structure.get("features", [])
    func_reqs = project_structure.get("requirements", {}).get("functional", [])
    phases = project_structure.get("phases", [])

    response = f"Project structure for '{title}':\n\n"
    response += f"**Description:** {project_structure.get('description', 'N/A')[:100]}...\n\n"
    response += f"**Features:** {len(features)} identified\n"
    response += f"**Requirements:** {len(func_reqs)} functional requirements\n"
    response += f"**Phases:** {len(phases)} implementation phases\n"

    if created_nodes:
        response += f"\nCreated {len(created_nodes)} feature nodes on canvas."

    return response


def _call_project_structuring(title: str, content: str) -> Optional[Dict[str, Any]]:
    """
    Call OpenRouter API to extract project structure from content.

    Returns structured JSON with project details.
    """
    client = _get_openrouter_client()
    if not client:
        logger.error("OpenRouter client not available")
        return None

    model = get_model("structure_analysis")

    system_prompt = """You are a project analyst and requirements engineer. Your task is to analyze idea documents and extract structured project information.

Output ONLY valid JSON in this exact format:
{
    "project_name": "string - concise project name",
    "description": "string - 2-3 sentence project description",
    "requirements": {
        "functional": [
            {"id": "FR-01", "description": "string", "priority": "high|medium|low"}
        ],
        "non_functional": [
            {"id": "NFR-01", "description": "string", "category": "performance|security|usability|reliability"}
        ]
    },
    "features": [
        {"name": "string", "description": "string", "priority": "high|medium|low", "requirements": ["FR-01"]}
    ],
    "phases": [
        {"name": "Phase 1: ...", "features": ["feature name"], "deliverables": ["string"]}
    ]
}

Extract information from the content. If something isn't explicitly mentioned, make reasonable inferences based on the context. Ensure the output is valid JSON only."""

    user_prompt = f"""Analyze this project idea and extract a structured project specification:

Title: {title}

Content:
{content[:6000]}

Generate the JSON project structure."""

    try:
        import json

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=2000,
            temperature=0.3
        )

        result_text = response.choices[0].message.content.strip()

        # Handle markdown code blocks
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]

        project_structure = json.loads(result_text)
        logger.info(f"Project structure generated: {len(project_structure.get('features', []))} features")
        return project_structure

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse project structure JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"OpenRouter project structuring error: {e}")
        return None


# ==============================================================================
# FEATURE DOCUMENTATION GENERATION
# ==============================================================================

def generate_feature_docs(params: Dict[str, Any]) -> str:
    """
    Generate detailed markdown documents for each feature in a bubble.

    Creates multiple connected MD files:
    - A parent index document linking all features
    - Individual feature documents with requirements, acceptance criteria
    - Canvas nodes with edges showing feature relationships

    Voice triggers: "Generate feature docs", "Create feature documentation",
                   "Document all features"

    Args (via params):
        bubble_name: Name of bubble to document (optional - uses current)
        include_requirements: Include linked requirements in docs (default: True)
        connect_features: Create edges between related features (default: True)

    Returns:
        str: Summary of generated documentation
    """
    bubble_name = params.get("bubble_name", "").strip()
    include_requirements = params.get("include_requirements", True)
    connect_features = params.get("connect_features", True)

    logger.info(f"generate_feature_docs called: bubble_name='{bubble_name}'")

    # Check OpenRouter availability
    if not HAS_OPENAI:
        return "Feature docs generation requires OpenAI package. Install with: pip install openai"

    if not _get_openrouter_client():
        return "LLM client not available. Check your API key configuration."

    # Get current bubble if no name specified - use local import from spaces
    current_bubble_id = None
    try:
        from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id
        current_bubble_id = get_current_bubble_db_id()
    except ImportError:
        pass

    ideas_repo = _get_ideas_repo()
    canvas_repo = _get_canvas_repo()

    # Find the bubble
    if bubble_name:
        idea = ideas_repo.get_by_title(bubble_name)
        if not idea:
            return f"Couldn't find bubble '{bubble_name}'"
    else:
        if current_bubble_id:
            idea = ideas_repo.get(current_bubble_id)
            if not idea:
                return "Current bubble not found"
        else:
            return "Specify a bubble name or enter one first."

    # Check if project structure exists, generate if not
    project_structure = idea.metadata.get("project_structure")
    if not project_structure:
        # Generate project structure first
        title, content, node_count = _get_idea_content(idea.id)
        if not content or node_count == 0:
            return f"'{idea.title}' has no content. Add a whitepaper or notes first!"

        project_structure = _call_project_structuring(title, content)
        if not project_structure:
            return "Failed to generate project structure. Try again."

        idea.metadata["project_structure"] = project_structure
        ideas_repo.update(idea)

    features = project_structure.get("features", [])
    if not features:
        return "No features found in project structure. Generate structure first."

    requirements = project_structure.get("requirements", {})

    # Generate detailed docs for each feature
    feature_docs = []
    feature_nodes = []

    # Get existing nodes to calculate positions
    all_nodes = canvas_repo.list_nodes(limit=1000)
    idea_nodes = [n for n in all_nodes if n.linked_idea_id == idea.id]
    max_y = max((n.y for n in idea_nodes), default=100) + 300
    x_offset = 100

    for i, feature in enumerate(features):
        # Generate detailed feature document
        feature_doc = _generate_feature_document(
            feature=feature,
            project_name=project_structure.get("project_name", idea.title),
            requirements=requirements,
            include_requirements=include_requirements
        )

        if feature_doc:
            feature_docs.append(feature_doc)

            # Create canvas node for this feature doc
            feature_node = canvas_repo.create_node(
                node_type="feature_doc",
                title=f"Feature: {feature.get('name', f'Feature {i+1}')}",
                content=feature_doc,
                linked_idea_id=idea.id,
                x=x_offset + (i % 3) * 400,
                y=max_y + (i // 3) * 250
            )
            feature_nodes.append(feature_node)
            logger.info(f"Created feature doc node: {feature_node.title}")

    # Create parent index document
    index_doc = _generate_feature_index(
        project_name=project_structure.get("project_name", idea.title),
        project_description=project_structure.get("description", ""),
        features=features,
        phases=project_structure.get("phases", [])
    )

    # Create index node at the top
    index_node = canvas_repo.create_node(
        node_type="feature_index",
        title=f"{idea.title} - Feature Index",
        content=index_doc,
        linked_idea_id=idea.id,
        x=x_offset + 400,
        y=max_y - 150
    )
    logger.info(f"Created index node: {index_node.title}")

    # Connect features to index with edges
    created_edges = []
    if connect_features:
        for feature_node in feature_nodes:
            edge = canvas_repo.create_edge(
                from_node_id=index_node.id,
                to_node_id=feature_node.id,
                edge_type="contains"
            )
            created_edges.append(edge)

        # Connect related features based on shared requirements
        for i, f1 in enumerate(features):
            f1_reqs = set(f1.get("requirements", []))
            for j, f2 in enumerate(features[i+1:], start=i+1):
                f2_reqs = set(f2.get("requirements", []))
                if f1_reqs & f2_reqs:  # Shared requirements
                    edge = canvas_repo.create_edge(
                        from_node_id=feature_nodes[i].id,
                        to_node_id=feature_nodes[j].id,
                        edge_type="related"
                    )
                    created_edges.append(edge)

    # Broadcast to Electron
    _broadcast_to_electron({
        "type": "feature_docs_generated",
        "bubble_id": idea.id,
        "bubble_title": idea.title,
        "index_node_id": index_node.id,
        "feature_count": len(feature_docs),
        "feature_node_ids": [n.id for n in feature_nodes],
        "edge_count": len(created_edges)
    })

    return (f"Generated documentation for '{idea.title}':\n"
            f"- 1 feature index document\n"
            f"- {len(feature_docs)} feature documents\n"
            f"- {len(created_edges)} connections\n\n"
            f"Check the canvas to see the connected feature docs.")


def _generate_feature_document(
    feature: Dict[str, Any],
    project_name: str,
    requirements: Dict[str, Any],
    include_requirements: bool
) -> Optional[str]:
    """Generate detailed markdown document for a single feature."""
    client = _get_openrouter_client()
    if not client:
        return None

    model = get_model("feature_extraction")

    # Build requirements context
    req_context = ""
    if include_requirements:
        feature_reqs = feature.get("requirements", [])
        func_reqs = requirements.get("functional", [])
        related_reqs = [r for r in func_reqs if r.get("id") in feature_reqs]
        if related_reqs:
            req_context = "Related Requirements:\n" + "\n".join(
                f"- {r['id']}: {r['description']}" for r in related_reqs
            )

    system_prompt = """You are a technical writer creating feature documentation.
Output clean, professional Markdown with these sections:
- Overview (2-3 sentences)
- User Stories (3-5 bullet points starting with "As a...")
- Acceptance Criteria (5-8 checkboxes)
- Technical Notes (if applicable)
- Dependencies (if any)

Keep it concise but thorough."""

    user_prompt = f"""Create a feature document for:

Project: {project_name}
Feature: {feature.get('name', 'Unnamed Feature')}
Description: {feature.get('description', 'No description')}
Priority: {feature.get('priority', 'medium')}

{req_context}

Generate the feature documentation in Markdown."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.5
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Feature document generation error: {e}")
        return None


def _generate_feature_index(
    project_name: str,
    project_description: str,
    features: list,
    phases: list
) -> str:
    """Generate the parent index document linking all features."""
    lines = [
        f"# {project_name}",
        "",
        f"{project_description}",
        "",
        "## Features",
        ""
    ]

    for i, feature in enumerate(features, 1):
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
            feature.get("priority", "medium"), "⚪"
        )
        lines.append(f"{i}. **{feature.get('name', 'Feature')}** {priority_emoji}")
        lines.append(f"   {feature.get('description', '')[:100]}")
        lines.append("")

    if phases:
        lines.extend([
            "## Implementation Phases",
            ""
        ])
        for phase in phases:
            lines.append(f"### {phase.get('name', 'Phase')}")
            if phase.get("features"):
                lines.append(f"Features: {', '.join(phase['features'])}")
            if phase.get("deliverables"):
                lines.append("Deliverables:")
                for d in phase["deliverables"]:
                    lines.append(f"- {d}")
            lines.append("")

    return "\n".join(lines)


# ==============================================================================
# REQ-ORCHESTRATOR INTEGRATION
# ==============================================================================

# Try to import httpx for async HTTP calls
HAS_HTTPX = False
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    httpx = None

REQ_ORCHESTRATOR_URL = os.getenv("REQ_ORCHESTRATOR_URL", "http://localhost:8087")
REQ_SCORE_THRESHOLD = float(os.getenv("REQ_SCORE_THRESHOLD", "0.7"))


def _format_as_requirements(features: list, bubble_name: str) -> list:
    """
    Convert feature nodes to REQ format for req-orchestrator.

    Args:
        features: List of feature dicts with title and content
        bubble_name: Name of the source bubble

    Returns:
        List of {id, text} requirement dicts
    """
    requirements = []
    for i, feature in enumerate(features, 1):
        title = feature.get("title", f"Feature {i}")
        content = feature.get("content", "")

        # Format as proper requirement text
        req_text = f"The system must provide {title}"
        if content:
            req_text = f"The system must {content}" if not content.startswith("The") else content

        requirements.append({
            "id": f"REQ-{bubble_name[:3].upper()}-{i:03d}",
            "text": req_text
        })

    return requirements


def _evaluate_requirements(requirements: list, batch_size: int = 5, shuttle_id: str = None) -> list:
    """
    Call req-orchestrator to evaluate requirements quality.

    Args:
        requirements: List of {id, text} dicts
        batch_size: Number of requirements to process per batch (default 5)
        shuttle_id: Optional shuttle ID for progress broadcasting

    Returns:
        List of evaluation results
    """
    all_results = []
    total_batches = (len(requirements) + batch_size - 1) // batch_size

    logger.info(f"Evaluating {len(requirements)} requirements in {total_batches} batches of {batch_size}")

    for batch_idx in range(0, len(requirements), batch_size):
        batch = requirements[batch_idx:batch_idx + batch_size]
        texts = [req["text"] for req in batch]
        payload = {"items": texts, "threshold": REQ_SCORE_THRESHOLD}

        batch_num = batch_idx // batch_size + 1
        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)")

        try:
            if not HAS_HTTPX:
                import requests
                response = requests.post(
                    f"{REQ_ORCHESTRATOR_URL}/api/v1/validate/batch",
                    json=payload,
                    timeout=120
                )
                batch_results = response.json()
            else:
                with httpx.Client(timeout=120) as client:
                    response = client.post(
                        f"{REQ_ORCHESTRATOR_URL}/api/v1/validate/batch",
                        json=payload
                    )
                    batch_results = response.json()

            if isinstance(batch_results, list):
                all_results.extend(batch_results)

                # Broadcast batch progress to Electron for shuttle visualization
                if shuttle_id:
                    batch_passed = sum(1 for r in batch_results if r.get("verdict") == "pass")
                    batch_failed = len(batch_results) - batch_passed
                    _broadcast_to_electron({
                        "type": "batch_progress",
                        "shuttle_id": shuttle_id,
                        "batch_index": batch_num - 1,
                        "results": {
                            "passed": batch_passed,
                            "failed": batch_failed
                        }
                    })
            else:
                logger.warning(f"Unexpected batch response format: {type(batch_results)}")

        except Exception as e:
            logger.error(f"Batch {batch_num} failed: {e}")
            # Add placeholder results for failed batch
            for _ in batch:
                all_results.append({"score": 0, "verdict": "error", "error": str(e)})

            # Broadcast error progress
            if shuttle_id:
                _broadcast_to_electron({
                    "type": "batch_progress",
                    "shuttle_id": shuttle_id,
                    "batch_index": batch_num - 1,
                    "results": {"error": str(e)}
                })

    return all_results


def _get_pending_clarifications() -> list:
    """
    Get pending clarification questions from req-orchestrator.

    Returns:
        List of clarification questions
    """
    try:
        if not HAS_HTTPX:
            import requests
            response = requests.get(
                f"{REQ_ORCHESTRATOR_URL}/api/v1/clarifications/pending",
                timeout=30
            )
            data = response.json()
            # Handle both list and dict responses
            if isinstance(data, list):
                return data
            return data.get("items", data.get("clarifications", []))

        with httpx.Client(timeout=30) as client:
            response = client.get(f"{REQ_ORCHESTRATOR_URL}/api/v1/clarifications/pending")
            data = response.json()
            # Handle both list and dict responses
            if isinstance(data, list):
                return data
            return data.get("items", data.get("clarifications", []))
    except Exception as e:
        logger.error(f"Failed to get clarifications: {e}")
        return []


def _call_knowledge_graph_api(requirements: list) -> dict:
    """
    Call req-orchestrator /api/kg/build to build entity relationships.

    Args:
        requirements: List of requirement dicts with id and text

    Returns:
        Dict with nodes, edges, and entity information
    """
    # Check if KG API is enabled
    if os.getenv("USE_KG_API", "false").lower() != "true":
        logger.info("Knowledge Graph API disabled (USE_KG_API=false)")
        return {"nodes": [], "edges": [], "skipped": True}

    try:
        payload = {"requirements": requirements}

        if not HAS_HTTPX:
            import requests
            response = requests.post(
                f"{REQ_ORCHESTRATOR_URL}/api/kg/build",
                json=payload,
                timeout=120
            )
            if response.status_code == 200:
                return response.json()
            logger.warning(f"KG API returned {response.status_code}: {response.text[:200]}")
            return {"nodes": [], "edges": [], "error": response.text}

        with httpx.Client(timeout=120) as client:
            response = client.post(f"{REQ_ORCHESTRATOR_URL}/api/kg/build", json=payload)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"KG API returned {response.status_code}: {response.text[:200]}")
            return {"nodes": [], "edges": [], "error": response.text}

    except Exception as e:
        logger.error(f"Knowledge Graph API error: {e}")
        return {"nodes": [], "edges": [], "error": str(e)}


def _call_techstack_api(requirements: list) -> dict:
    """
    Call req-orchestrator /api/v1/techstack/detect to detect technology stack.

    Args:
        requirements: List of requirement dicts with id and text

    Returns:
        Dict with recommended_stack and technology suggestions
    """
    # Check if TechStack API is enabled
    if os.getenv("USE_TECHSTACK_API", "false").lower() != "true":
        logger.info("TechStack API disabled (USE_TECHSTACK_API=false)")
        return {"recommended_stack": "unknown", "skipped": True}

    try:
        # Format requirements for techstack detection
        req_texts = [req.get("text", "") for req in requirements]
        payload = {"requirements": req_texts}

        if not HAS_HTTPX:
            import requests
            response = requests.post(
                f"{REQ_ORCHESTRATOR_URL}/api/v1/techstack/detect",
                json=payload,
                timeout=60
            )
            if response.status_code == 200:
                return response.json()
            logger.warning(f"TechStack API returned {response.status_code}: {response.text[:200]}")
            return {"recommended_stack": "unknown", "error": response.text}

        with httpx.Client(timeout=60) as client:
            response = client.post(f"{REQ_ORCHESTRATOR_URL}/api/v1/techstack/detect", json=payload)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"TechStack API returned {response.status_code}: {response.text[:200]}")
            return {"recommended_stack": "unknown", "error": response.text}

    except Exception as e:
        logger.error(f"TechStack API error: {e}")
        return {"recommended_stack": "unknown", "error": str(e)}


def _export_requirements_to_markdown(
    requirements: list,
    evaluations: dict,
    output_dir: str,
    bubble_name: str
) -> int:
    """
    Export validated requirements as markdown files.

    Args:
        requirements: List of requirement dicts
        evaluations: Evaluation results from req-orchestrator
        output_dir: Directory to write files
        bubble_name: Name of source bubble

    Returns:
        Number of files written
    """
    from pathlib import Path
    import re

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    files_written = 0
    index_entries = []

    for req in requirements:
        req_id = req["id"]
        req_text = req["text"]

        # Find evaluation for this requirement
        eval_data = evaluations.get(req_id, {})
        score = eval_data.get("score", 0)
        verdict = eval_data.get("verdict", "unknown")
        criteria = eval_data.get("evaluation", [])

        # Generate filename from title
        title_slug = re.sub(r'[^a-z0-9]+', '_', req_text[:50].lower()).strip('_')
        filename = f"{req_id.lower()}_{title_slug}.md"

        # Build markdown content
        md_lines = [
            f"# {req_id}: {req_text[:80]}{'...' if len(req_text) > 80 else ''}",
            "",
            f"**Score:** {score:.2f} ({verdict.upper()})",
            f"**Threshold:** {REQ_SCORE_THRESHOLD}",
            "",
            "## Requirement",
            "",
            req_text,
            "",
            "## Quality Evaluation",
            "",
            "| Criterion | Score | Status | Feedback |",
            "|-----------|-------|--------|----------|",
        ]

        for c in criteria:
            status = "✅" if c.get("passed") else "❌"
            md_lines.append(
                f"| {c.get('criterion', 'N/A')} | {c.get('score', 0):.1f} | {status} | {c.get('feedback', '')[:50]} |"
            )

        md_lines.extend(["", f"---", f"*Generated from bubble: {bubble_name}*"])

        # Write file
        file_path = output_path / filename
        file_path.write_text("\n".join(md_lines), encoding="utf-8")
        files_written += 1

        index_entries.append({
            "id": req_id,
            "title": req_text[:80],
            "score": score,
            "verdict": verdict,
            "filename": filename
        })

    # Write index.md
    index_lines = [
        f"# Requirements Index: {bubble_name}",
        "",
        f"**Total Requirements:** {len(requirements)}",
        f"**Passing:** {sum(1 for e in index_entries if e['verdict'] == 'pass')}",
        f"**Threshold:** {REQ_SCORE_THRESHOLD}",
        "",
        "## Requirements",
        "",
        "| ID | Title | Score | Status |",
        "|----|-------|-------|--------|",
    ]

    for entry in sorted(index_entries, key=lambda x: x["id"]):
        status = "✅" if entry["verdict"] == "pass" else "❌"
        index_lines.append(
            f"| [{entry['id']}]({entry['filename']}) | {entry['title'][:40]}... | {entry['score']:.2f} | {status} |"
        )

    (output_path / "index.md").write_text("\n".join(index_lines), encoding="utf-8")
    files_written += 1

    return files_written


def submit_to_req_orchestrator(params: Dict[str, Any]) -> str:
    """
    Submit bubble requirements to req-orchestrator for validation.

    Voice triggers: "Validate my requirements", "Submit to arch team",
                   "Check requirement quality"

    Args (via params):
        bubble_name: Bubble to process (optional - uses current)
        output_dir: Directory for .md files (optional)

    Returns:
        str: Summary of evaluation results + any pending clarifications
    """
    bubble_name = params.get("bubble_name", "").strip()
    output_dir = params.get("output_dir", "").strip()

    logger.info(f"submit_to_req_orchestrator called: bubble_name='{bubble_name}', output_dir='{output_dir}'")

    # Get current bubble if not specified - use local import from spaces
    current_bubble_id = None
    try:
        from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id, get_current_bubble
        current_bubble_id = get_current_bubble_db_id()
        if not bubble_name:
            current = get_current_bubble()
            bubble_name = current.get("title", "current") if current else "current"
    except ImportError:
        pass

    # Get ideas repo
    ideas_repo = _get_ideas_repo()
    canvas_repo = _get_canvas_repo()

    # Find bubble by name if specified
    if bubble_name and bubble_name != "current":
        idea = ideas_repo.get_by_title(bubble_name)
        if idea:
            current_bubble_id = idea.id
            bubble_name = idea.title

    if not current_bubble_id:
        return "No bubble selected. Please enter a bubble first or specify a bubble name."

    # Get feature nodes from canvas
    all_nodes = canvas_repo.list_nodes(limit=500)
    feature_nodes = [
        {"title": n.title, "content": n.content}
        for n in all_nodes
        if n.linked_idea_id == current_bubble_id and n.node_type in ("feature", "note", "whitepaper")
    ]

    if not feature_nodes:
        return f"No features found in '{bubble_name}'. Generate project structure first with 'generate project structure'."

    # Format as requirements
    requirements = _format_as_requirements(feature_nodes, bubble_name)
    logger.info(f"Formatted {len(requirements)} requirements for evaluation")

    # Generate shuttle ID for visualization
    import time
    shuttle_id = f"shuttle-{bubble_name[:10]}-{int(time.time())}"
    batch_count = (len(requirements) + 4) // 5  # batch_size=5

    # PHASE 8: Create project FIRST with status="shuttling"
    # Project is created immediately when shuttle launches, not after completion
    projects_repo = _get_projects_repo()
    project = projects_repo.create(
        name=bubble_name,
        description=f"Processing {len(requirements)} requirements from '{bubble_name}'...",
        status="shuttling",  # Special status for shuttle-in-progress
        from_idea_id=current_bubble_id,
        metadata={"source_bubble": current_bubble_id, "shuttle_id": shuttle_id}
    )
    logger.info(f"Created project record: {project.id} with status='shuttling'")

    # Broadcast project creation to Electron for Projects Space visualization
    _broadcast_to_electron({
        "type": "project_created",
        "project": {
            "id": project.id,
            "name": project.name,
            "status": "shuttling",
            "from_idea_id": current_bubble_id
        }
    })

    # Get bubble position to store in shuttle metadata (persists across restarts)
    bubble_pos = get_bubble_position(current_bubble_id)
    logger.info(f"Bubble position for shuttle: {bubble_pos}")

    # Create shuttle record linked to project with position stored
    shuttles_repo = _get_shuttles_repo()
    shuttle = shuttles_repo.create(
        shuttle_id=shuttle_id,
        bubble_id=current_bubble_id,
        bubble_name=bubble_name,
        total_count=len(requirements),
        project_id=project.id,  # Link shuttle to project
        metadata={"start_position": bubble_pos} if bubble_pos else {}
    )
    logger.info(f"Created shuttle record: {shuttle.id} ({shuttle_id}) linked to project {project.id}")

    # Broadcast shuttle launched to Electron for visualization
    _broadcast_to_electron({
        "type": "shuttle_launched",
        "shuttle_id": shuttle_id,
        "bubble_id": current_bubble_id,  # Pass bubble ID for position lookup
        "project_id": project.id,  # Link to project for visualization
        "bubble_name": bubble_name,
        "total_requirements": len(requirements),
        "batch_count": batch_count,
        "currentStage": ShuttleStage.MINING,
        "start_position": bubble_pos  # Include position for immediate use
    })

    # Stage 1: Mining - Content extracted from bubble (already done)
    _broadcast_stage_update(shuttle_id, ShuttleStage.MINING, shuttle.id)

    # Stage 2: Requirements - Formatted and stored
    _broadcast_stage_update(shuttle_id, ShuttleStage.REQUIREMENTS, shuttle.id)

    # Stage 3: Validation - Submit to req-orchestrator for 9-criteria scoring
    _broadcast_stage_update(shuttle_id, ShuttleStage.VALIDATION, shuttle.id)

    # Submit to req-orchestrator
    try:
        results = _evaluate_requirements(requirements, shuttle_id=shuttle_id)
    except Exception as e:
        logger.error(f"req-orchestrator evaluation failed: {e}")
        return f"Failed to connect to req-orchestrator at {REQ_ORCHESTRATOR_URL}. Is it running?"

    # Process results
    evaluations = {}
    passed = 0
    failed = 0

    if isinstance(results, list):
        # Batch response is a list
        for i, result in enumerate(results):
            req_id = requirements[i]["id"] if i < len(requirements) else f"REQ-{i}"
            score = result.get("score", 0)
            verdict = result.get("verdict", "fail")
            evaluations[req_id] = result
            if verdict == "pass":
                passed += 1
            else:
                failed += 1
    elif isinstance(results, dict) and "results" in results:
        # Wrapped response
        for result in results["results"]:
            req_id = result.get("id", "")
            evaluations[req_id] = result
            if result.get("verdict") == "pass":
                passed += 1
            else:
                failed += 1

    # Export to markdown if output_dir specified
    files_written = 0
    if output_dir:
        try:
            files_written = _export_requirements_to_markdown(
                requirements, evaluations, output_dir, bubble_name
            )
            logger.info(f"Exported {files_written} markdown files to {output_dir}")
        except Exception as e:
            logger.error(f"Failed to export markdown: {e}")

    # Get pending clarifications
    clarifications = _get_pending_clarifications()

    # Build response
    response_lines = [
        f"Evaluated {len(requirements)} requirements from '{bubble_name}':",
        f"  [PASS] {passed} (score >= {REQ_SCORE_THRESHOLD})",
        f"  [FAIL] {failed} (need clarification)",
    ]

    if files_written > 0:
        response_lines.append(f"  [EXPORT] {files_written} files to {output_dir}")

    if clarifications:
        response_lines.append(f"\n{len(clarifications)} clarification questions pending.")
        response_lines.append("Ask me 'what clarifications are needed' to review them.")

    # Broadcast to Electron
    _broadcast_to_electron({
        "type": "requirements_evaluated",
        "bubble_name": bubble_name,
        "total": len(requirements),
        "passed": passed,
        "failed": failed,
        "clarifications_pending": len(clarifications)
    })

    # Calculate overall score (average of all requirements)
    all_scores = [evaluations[r["id"]].get("score", 0) for r in requirements if r["id"] in evaluations]
    overall_score = sum(all_scores) / len(all_scores) if all_scores else 0

    # Stage 4: Knowledge Graph - Build entity relationships
    _broadcast_stage_update(shuttle_id, ShuttleStage.KNOWLEDGE_GRAPH, shuttle.id)
    kg_result = _call_knowledge_graph_api(requirements)
    if not kg_result.get("skipped"):
        logger.info(f"KG built: {len(kg_result.get('nodes', []))} nodes, {len(kg_result.get('edges', []))} edges")
        # Store KG results in shuttle metadata
        shuttle.metadata = shuttle.metadata or {}
        shuttle.metadata["kg_nodes"] = len(kg_result.get("nodes", []))
        shuttle.metadata["kg_edges"] = len(kg_result.get("edges", []))

    # Stage 5: TechStack - Detect recommended technology stack
    _broadcast_stage_update(shuttle_id, ShuttleStage.TECHSTACK, shuttle.id)
    techstack_result = _call_techstack_api(requirements)
    recommended_stack = techstack_result.get("recommended_stack", "unknown")
    if not techstack_result.get("skipped"):
        logger.info(f"TechStack detected: {recommended_stack}")
        # Update project with tech stack info
        project.tech_stack = recommended_stack
        import json
        project.requirements_json = json.dumps([r["text"] for r in requirements])
        projects_repo.update(project)

    # Mark as complete
    final_stage = ShuttleStage.COMPLETE if overall_score >= REQ_SCORE_THRESHOLD else ShuttleStage.VALIDATION
    _broadcast_stage_update(shuttle_id, final_stage, shuttle.id)

    # Update project status based on shuttle completion
    project.status = "active" if overall_score >= REQ_SCORE_THRESHOLD else "needs_work"
    project.description = f"{len(requirements)} requirements evaluated. Score: {overall_score:.2f}"
    projects_repo.update(project)
    logger.info(f"Project {project.id} status updated to '{project.status}'")

    # Broadcast project status update
    _broadcast_to_electron({
        "type": "project_status_update",
        "project_id": project.id,
        "status": project.status,
        "linked_shuttle": shuttle_id
    })

    # Persist shuttle completion to database
    shuttles_repo.complete(
        shuttle_db_id=shuttle.id,
        final_score=overall_score,
        passed=passed,
        failed=failed,
        requirement_results=evaluations
    )
    logger.info(f"Shuttle {shuttle_id} completed: score={overall_score:.2f}, passed={passed}, failed={failed}")

    # Broadcast shuttle complete for visualization
    _broadcast_to_electron({
        "type": "shuttle_complete",
        "shuttle_id": shuttle_id,
        "project_id": project.id,
        "score": overall_score,
        "passed": passed,
        "failed": failed,
        "currentStage": final_stage,
        "tech_stack": recommended_stack
    })

    # Publish shuttle data to Rowboat knowledge base
    try:
        from publishing import get_ideas_publisher
        publisher = get_ideas_publisher()
        if hasattr(publisher, "publish_shuttle_data"):
            publisher.publish_shuttle_data(shuttle.bubble_id)
            logger.info(
                f"Shuttle data published to Rowboat for bubble {shuttle.bubble_id}"
            )
    except Exception as e:
        logger.debug(f"Shuttle Rowboat publish skipped: {e}")

    return "\n".join(response_lines)


def get_requirement_clarifications(params: Dict[str, Any]) -> str:
    """
    Get pending clarification questions for requirements.

    Voice triggers: "What clarifications are needed", "Show requirement questions"

    Returns:
        str: List of clarification questions
    """
    logger.debug("get_requirement_clarifications: checking pending clarifications")
    clarifications = _get_pending_clarifications()

    if not clarifications:
        return "No clarification questions pending. All requirements are clear!"

    lines = [f"Found {len(clarifications)} clarification questions:\n"]

    for i, q in enumerate(clarifications[:5], 1):  # Show first 5
        lines.append(f"{i}. [{q.get('requirement_id', 'N/A')}] {q.get('question', 'No question')}")

    if len(clarifications) > 5:
        lines.append(f"\n...and {len(clarifications) - 5} more questions.")

    lines.append("\nAnswer by saying 'answer clarification 1 with [your answer]'")

    return "\n".join(lines)


# ==============================================================================
# REQ-ORCHESTRATOR SYNC
# ==============================================================================

def _fetch_orchestrator_project_state(project_name: str = None, project_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Fetch project state from req-orchestrator API.

    Args:
        project_name: Name to search for (fuzzy match)
        project_id: Exact project ID if known

    Returns:
        Dict with project state or None if not found
    """
    try:
        if not HAS_HTTPX:
            import requests
            response = requests.get(
                f"{REQ_ORCHESTRATOR_URL}/api/v1/techstack/projects",
                timeout=30
            )
        else:
            with httpx.Client(timeout=30) as client:
                response = client.get(f"{REQ_ORCHESTRATOR_URL}/api/v1/techstack/projects")

        if response.status_code != 200:
            logger.warning(f"req-orchestrator projects API returned {response.status_code}")
            return None

        data = response.json()

        # Handle wrapped response: {"projects": [...]} or plain list
        if isinstance(data, dict) and "projects" in data:
            projects = data["projects"]
        elif isinstance(data, list):
            projects = data
        else:
            logger.warning(f"Unexpected API response format: {type(data)}")
            return None

        if not projects:
            return None

        # Find matching project
        if project_id:
            for p in projects:
                if isinstance(p, dict) and p.get("project_id") == project_id:
                    return p
        elif project_name:
            project_name_lower = project_name.lower()
            for p in projects:
                if not isinstance(p, dict):
                    continue
                p_name = p.get("project_name", "").lower()
                # Fuzzy match: either name contains the other
                if project_name_lower in p_name or p_name in project_name_lower:
                    return p

        return None
    except Exception as e:
        logger.error(f"Failed to fetch orchestrator project state: {e}")
        return None


def sync_shuttle_from_orchestrator(params: Dict[str, Any]) -> str:
    """
    Sync shuttle checkpoint state from req-orchestrator API.

    Voice triggers: "Sync shuttle progress", "Update shuttle from orchestrator",
                   "Check orchestrator status"

    Args (via params):
        bubble_name: Bubble/shuttle to sync (optional - uses current)

    Returns:
        str: Summary of sync result
    """
    from datetime import datetime

    bubble_name = params.get("bubble_name", "").strip()

    # Get current bubble if not specified - use local import from spaces
    if not bubble_name:
        try:
            from spaces.ideas.tools.bubble_tools import get_current_bubble
            current = get_current_bubble()
            if current:
                bubble_name = current.get("title", "")
        except ImportError:
            pass

    if not bubble_name:
        return "Specify a bubble name or enter one first."

    logger.info(f"sync_shuttle_from_orchestrator: bubble_name='{bubble_name}'")

    # Fetch state from req-orchestrator
    project_state = _fetch_orchestrator_project_state(project_name=bubble_name)

    if not project_state:
        return f"No matching project found in req-orchestrator for '{bubble_name}'."

    # Extract state
    orchestrator_stage = project_state.get("current_stage", "mining")
    validation_summary = project_state.get("validation_summary", {})
    avg_score = validation_summary.get("avg_score", 0.0)
    passed = validation_summary.get("passed", 0)
    failed = validation_summary.get("failed", 0)
    total = validation_summary.get("total", project_state.get("requirements_count", 0))

    # Map to VibeMind stage
    stage_map = {
        "mining": ShuttleStage.MINING,
        "requirements": ShuttleStage.REQUIREMENTS,
        "validation": ShuttleStage.VALIDATION,
        "knowledge_graph": ShuttleStage.KNOWLEDGE_GRAPH,
        "techstack": ShuttleStage.TECHSTACK,
    }
    vibemind_stage = stage_map.get(orchestrator_stage, ShuttleStage.MINING)

    # Find or create shuttle
    shuttles_repo = _get_shuttles_repo()
    ideas_repo = _get_ideas_repo()

    idea = ideas_repo.get_by_title(bubble_name)
    if not idea:
        return f"Bubble '{bubble_name}' not found in VibeMind."

    # Check for existing shuttle
    existing_shuttles = shuttles_repo.list(bubble_id=idea.id)

    if existing_shuttles:
        # Update existing shuttle
        shuttle = existing_shuttles[0]
        shuttle.current_stage = vibemind_stage
        shuttle.score = avg_score
        shuttle.passed_count = passed
        shuttle.failed_count = failed
        shuttle.total_count = total
        shuttle.metadata = shuttle.metadata or {}
        shuttle.metadata["orchestrator_project_id"] = project_state.get("project_id")
        shuttle.metadata["last_synced"] = datetime.now().isoformat()
        shuttles_repo.update(shuttle)
        action = "Updated"
        shuttle_id = shuttle.shuttle_id
    else:
        # Create new shuttle synced to orchestrator state
        import time
        shuttle_id = f"shuttle-{bubble_name[:10]}-{int(time.time())}"
        shuttle = shuttles_repo.create(
            shuttle_id=shuttle_id,
            bubble_id=idea.id,
            bubble_name=bubble_name,
            total_count=total,
            current_stage=vibemind_stage,
            score=avg_score,
            passed_count=passed,
            failed_count=failed,
            metadata={
                "orchestrator_project_id": project_state.get("project_id"),
                "last_synced": datetime.now().isoformat(),
                "synced_from_orchestrator": True
            }
        )
        action = "Created"

    logger.info(f"{action} shuttle {shuttle_id}: stage={vibemind_stage}, score={avg_score}")

    # Broadcast to Electron for real-time visualization
    _broadcast_to_electron({
        "type": "shuttle_synced",
        "shuttle_id": shuttle_id,
        "bubble_id": idea.id,  # Pass bubble ID for position lookup
        "bubble_name": bubble_name,
        "current_stage": vibemind_stage,
        "progress": STAGE_PROGRESS.get(vibemind_stage, 0.2),
        "score": avg_score,
        "passed": passed,
        "failed": failed,
        "total": total
    })

    progress_pct = STAGE_PROGRESS.get(vibemind_stage, 0.2) * 100
    return (f"{action} shuttle for '{bubble_name}' from req-orchestrator:\n"
            f"  Stage: {orchestrator_stage} → checkpoint {progress_pct:.0f}%\n"
            f"  Score: {avg_score:.2f} ({passed}/{total} passed)")


# ==============================================================================
# PHASE 13: STAGE-SPECIFIC SHUTTLE CREATION
# ==============================================================================

def _fetch_mining_data(bubble_id: str, bubble_name: str) -> Dict[str, Any]:
    """
    Extract requirements from bubble content (local extraction).

    This is the Mining stage - no external API needed, just local content extraction.

    Args:
        bubble_id: ID of the bubble to extract from
        bubble_name: Name of the bubble

    Returns:
        Dict with extracted requirements
    """
    canvas_repo = _get_canvas_repo()

    # Get all nodes from this bubble
    all_nodes = canvas_repo.list_nodes(limit=500)
    bubble_nodes = [
        n for n in all_nodes
        if n.linked_idea_id == bubble_id and n.node_type in ("feature", "note", "whitepaper")
    ]

    # Extract requirements from nodes
    requirements = []
    for i, node in enumerate(bubble_nodes, 1):
        title = node.title or f"Item {i}"
        content = node.content or ""

        # Format as requirement text
        if content:
            req_text = content if content.startswith("The") else f"The system must provide {title}: {content[:200]}"
        else:
            req_text = f"The system must provide {title}"

        requirements.append({
            "id": f"REQ-{bubble_name[:3].upper()}-{i:03d}",
            "text": req_text,
            "source_node_id": node.id,
            "source_node_type": node.node_type,
            "source_node_title": title
        })

    logger.info(f"Mining stage: extracted {len(requirements)} requirements from '{bubble_name}'")

    return {
        "requirements": requirements,
        "total_extracted": len(requirements),
        "source_nodes": len(bubble_nodes),
        "bubble_name": bubble_name
    }


def _fetch_validation_data(requirements: list) -> Dict[str, Any]:
    """
    Fetch validation scores from req-orchestrator for stage-specific shuttle.

    Args:
        requirements: List of requirement dicts with id and text

    Returns:
        Dict with validation results for the Validation stage shuttle
    """
    if not requirements:
        return {"results": [], "average_score": 0, "passed": 0, "failed": 0}

    # Call the existing evaluation function
    results = _evaluate_requirements(requirements, batch_size=5)

    # Process results into stage-specific format
    validation_results = []
    passed = 0
    failed = 0
    total_score = 0

    for i, result in enumerate(results):
        req_id = requirements[i]["id"] if i < len(requirements) else f"REQ-{i}"
        score = result.get("score", 0)
        verdict = result.get("verdict", "fail")
        criteria = result.get("evaluation", [])

        validation_results.append({
            "id": req_id,
            "text": requirements[i]["text"] if i < len(requirements) else "",
            "score": score,
            "verdict": verdict,
            "criteria": criteria,
            "status": "passed" if verdict == "pass" else "failed"
        })

        total_score += score
        if verdict == "pass":
            passed += 1
        else:
            failed += 1

    avg_score = total_score / len(results) if results else 0

    logger.info(f"Validation stage: {passed}/{len(results)} passed, avg score: {avg_score:.2f}")

    return {
        "results": validation_results,
        "average_score": avg_score,
        "passed": passed,
        "failed": failed,
        "total": len(results),
        "threshold": REQ_SCORE_THRESHOLD
    }


def _fetch_kg_data(requirements: list) -> Dict[str, Any]:
    """
    Fetch knowledge graph data from req-orchestrator for stage-specific shuttle.

    Args:
        requirements: List of requirement dicts

    Returns:
        Dict with KG entities and relationships for Knowledge Graph stage shuttle
    """
    # Call the existing KG API function
    kg_result = _call_knowledge_graph_api(requirements)

    if kg_result.get("skipped"):
        return {
            "entities": [],
            "relationships": [],
            "skipped": True,
            "message": "Knowledge Graph API disabled (USE_KG_API=false)"
        }

    # Format for stage shuttle
    entities = kg_result.get("nodes", kg_result.get("entities", []))
    relationships = kg_result.get("edges", kg_result.get("relationships", []))

    logger.info(f"KGraph stage: {len(entities)} entities, {len(relationships)} relationships")

    return {
        "entities": entities,
        "relationships": relationships,
        "entity_count": len(entities),
        "relationship_count": len(relationships),
        "error": kg_result.get("error")
    }


def _fetch_techstack_data(requirements: list) -> Dict[str, Any]:
    """
    Fetch techstack recommendations from req-orchestrator for stage-specific shuttle.

    Args:
        requirements: List of requirement dicts

    Returns:
        Dict with tech stack recommendations for TechStack stage shuttle
    """
    # Call the existing TechStack API function
    tech_result = _call_techstack_api(requirements)

    if tech_result.get("skipped"):
        return {
            "recommended_stack": "unknown",
            "templates": [],
            "skipped": True,
            "message": "TechStack API disabled (USE_TECHSTACK_API=false)"
        }

    logger.info(f"TechStack stage: recommended '{tech_result.get('recommended_stack', 'unknown')}'")

    return {
        "recommended_stack": tech_result.get("recommended_stack", "unknown"),
        "templates": tech_result.get("templates", []),
        "technologies": tech_result.get("technologies", []),
        "confidence": tech_result.get("confidence", 0),
        "error": tech_result.get("error")
    }


def create_stage_shuttles(params: Dict[str, Any]) -> str:
    """
    Create 4 stage-specific shuttles for a bubble (one per checkpoint).

    Voice triggers: "Create requirement shuttles", "Launch pipeline",
                   "Create stage shuttles"

    This creates separate shuttles that stay parked at each checkpoint:
    - Mining shuttle: Contains extracted requirements
    - Validation shuttle: Contains 9-criteria scoring results
    - Knowledge Graph shuttle: Contains entity relationships
    - TechStack shuttle: Contains architecture recommendations

    Args (via params):
        bubble_name: Bubble to process (optional - uses current)

    Returns:
        str: Summary of created shuttles
    """
    from data.models import ShuttleType

    bubble_name = params.get("bubble_name", "").strip()

    logger.info(f"create_stage_shuttles called: bubble_name='{bubble_name}'")

    # Get current bubble if not specified - use local import from spaces
    current_bubble_id = None
    try:
        from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id, get_current_bubble
        current_bubble_id = get_current_bubble_db_id()
        if not bubble_name:
            current = get_current_bubble()
            bubble_name = current.get("title", "current") if current else "current"
    except ImportError:
        pass

    # Get ideas repo
    ideas_repo = _get_ideas_repo()
    shuttles_repo = _get_shuttles_repo()

    # Find bubble by name if specified
    if bubble_name and bubble_name != "current":
        idea = ideas_repo.get_by_title(bubble_name)
        if idea:
            current_bubble_id = idea.id
            bubble_name = idea.title

    if not current_bubble_id:
        return "No bubble selected. Please enter a bubble first or specify a bubble name."

    # Delete any existing stage shuttles for this bubble (clean slate)
    deleted = shuttles_repo.delete_bubble_stage_shuttles(current_bubble_id)
    if deleted > 0:
        logger.info(f"Deleted {deleted} existing stage shuttles for bubble {current_bubble_id}")

    shuttles_created = []

    # Stage 1: Mining - Extract requirements from bubble
    logger.info("Creating Mining stage shuttle...")
    mining_data = _fetch_mining_data(current_bubble_id, bubble_name)

    if not mining_data.get("requirements"):
        return f"No content found in '{bubble_name}'. Add a whitepaper or notes first!"

    mining_shuttle = shuttles_repo.create_stage_shuttle(
        bubble_id=current_bubble_id,
        bubble_name=bubble_name,
        stage_type=ShuttleType.MINING,
        stage_data=mining_data
    )
    shuttles_created.append(("Mining", mining_shuttle, mining_data))

    # Broadcast mining shuttle created
    _broadcast_to_electron({
        "type": "stage_shuttle_created",
        "shuttle_id": mining_shuttle.shuttle_id,
        "bubble_id": current_bubble_id,
        "bubble_name": bubble_name,
        "stage_type": ShuttleType.MINING,
        "stage_data": mining_data,
        "total": mining_data.get("total_extracted", 0)
    })

    # Stage 2: Validation - Call validation API
    logger.info("Creating Validation stage shuttle...")
    requirements = mining_data.get("requirements", [])
    validation_data = _fetch_validation_data(requirements)

    validation_shuttle = shuttles_repo.create_stage_shuttle(
        bubble_id=current_bubble_id,
        bubble_name=bubble_name,
        stage_type=ShuttleType.VALIDATION,
        stage_data=validation_data
    )
    shuttles_created.append(("Validation", validation_shuttle, validation_data))

    # Broadcast validation shuttle created
    _broadcast_to_electron({
        "type": "stage_shuttle_created",
        "shuttle_id": validation_shuttle.shuttle_id,
        "bubble_id": current_bubble_id,
        "bubble_name": bubble_name,
        "stage_type": ShuttleType.VALIDATION,
        "stage_data": validation_data,
        "passed": validation_data.get("passed", 0),
        "failed": validation_data.get("failed", 0),
        "score": validation_data.get("average_score", 0)
    })

    # Stage 3: Knowledge Graph - Call KG API
    logger.info("Creating Knowledge Graph stage shuttle...")
    kg_data = _fetch_kg_data(requirements)

    kg_shuttle = shuttles_repo.create_stage_shuttle(
        bubble_id=current_bubble_id,
        bubble_name=bubble_name,
        stage_type=ShuttleType.KNOWLEDGE_GRAPH,
        stage_data=kg_data
    )
    shuttles_created.append(("Knowledge Graph", kg_shuttle, kg_data))

    # Broadcast KG shuttle created
    _broadcast_to_electron({
        "type": "stage_shuttle_created",
        "shuttle_id": kg_shuttle.shuttle_id,
        "bubble_id": current_bubble_id,
        "bubble_name": bubble_name,
        "stage_type": ShuttleType.KNOWLEDGE_GRAPH,
        "stage_data": kg_data,
        "entities": len(kg_data.get("entities", [])),
        "relationships": len(kg_data.get("relationships", []))
    })

    # Stage 4: TechStack - Call TechStack API
    logger.info("Creating TechStack stage shuttle...")
    techstack_data = _fetch_techstack_data(requirements)

    techstack_shuttle = shuttles_repo.create_stage_shuttle(
        bubble_id=current_bubble_id,
        bubble_name=bubble_name,
        stage_type=ShuttleType.TECHSTACK,
        stage_data=techstack_data
    )
    shuttles_created.append(("TechStack", techstack_shuttle, techstack_data))

    # Broadcast TechStack shuttle created
    _broadcast_to_electron({
        "type": "stage_shuttle_created",
        "shuttle_id": techstack_shuttle.shuttle_id,
        "bubble_id": current_bubble_id,
        "bubble_name": bubble_name,
        "stage_type": ShuttleType.TECHSTACK,
        "stage_data": techstack_data,
        "recommended_stack": techstack_data.get("recommended_stack", "unknown")
    })

    # Build summary response
    lines = [f"Created 4 stage shuttles for '{bubble_name}':\n"]

    for stage_name, shuttle, data in shuttles_created:
        if stage_name == "Mining":
            lines.append(f"  🏭 {stage_name}: {data.get('total_extracted', 0)} requirements extracted")
        elif stage_name == "Validation":
            lines.append(f"  ⚖️ {stage_name}: {data.get('passed', 0)}/{data.get('total', 0)} passed (score: {data.get('average_score', 0):.2f})")
        elif stage_name == "Knowledge Graph":
            if data.get("skipped"):
                lines.append(f"  🔗 {stage_name}: Skipped (API disabled)")
            else:
                lines.append(f"  🔗 {stage_name}: {len(data.get('entities', []))} entities, {len(data.get('relationships', []))} relationships")
        elif stage_name == "TechStack":
            if data.get("skipped"):
                lines.append(f"  📁 {stage_name}: Skipped (API disabled)")
            else:
                lines.append(f"  📁 {stage_name}: Recommended stack: {data.get('recommended_stack', 'unknown')}")

    lines.append(f"\nShuttles are now parked at their checkpoints in the 3D view.")

    logger.info(f"Created {len(shuttles_created)} stage shuttles for '{bubble_name}'")

    return "\n".join(lines)


# ==============================================================================
# PROJECT DOCUMENTATION GENERATION (LLM-SYNTHESIZED EXPORT)
# ==============================================================================

def _collect_bubble_content(bubble_id: str, idea) -> Dict[str, Any]:
    """
    Collect ALL content from a bubble for project documentation.

    Returns a dict with categorized content ready for LLM synthesis.
    """
    ideas_repo = _get_ideas_repo()
    canvas_repo = _get_canvas_repo()

    # 1. Child ideas (parent_id = bubble_id)
    from data.models import Idea
    child_rows = ideas_repo.db.fetch_all(
        "SELECT * FROM ideas WHERE parent_id = ?", (bubble_id,)
    )
    child_ideas = [Idea.from_dict(dict(r)) for r in child_rows]

    # 2. Canvas nodes grouped by type
    all_nodes = canvas_repo.list_nodes(limit=2000)
    bubble_nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]

    nodes_by_type = {}
    for node in bubble_nodes:
        ntype = node.node_type or "note"
        nodes_by_type.setdefault(ntype, []).append(node)

    # 3. Project structure from metadata
    project_structure = (idea.metadata or {}).get("project_structure")

    # 4. Mermaid diagrams
    mermaid_diagrams = []
    try:
        from data import MermaidDiagramsRepository
        mermaid_repo = MermaidDiagramsRepository()
        mermaid_diagrams = mermaid_repo.list_by_idea(bubble_id)
    except Exception as e:
        logger.debug(f"Could not load mermaid diagrams: {e}")

    # 5. Summaries from nodes
    summaries = [n for n in bubble_nodes if n.summary]

    return {
        "bubble": idea,
        "child_ideas": child_ideas,
        "nodes_by_type": nodes_by_type,
        "all_nodes": bubble_nodes,
        "project_structure": project_structure,
        "mermaid_diagrams": mermaid_diagrams,
        "summaries": summaries,
    }


def _build_doc_input_text(content: Dict[str, Any]) -> str:
    """
    Build structured input text from collected content for LLM synthesis.
    """
    from spaces.ideas.tools.format_dispatcher import _extract_content_text

    parts = []
    bubble = content["bubble"]

    # Bubble overview
    parts.append(f"=== BUBBLE: {bubble.title} ===")
    if bubble.description:
        parts.append(f"Beschreibung: {bubble.description}")
    parts.append("")

    # Whitepaper content (highest quality existing synthesis)
    whitepapers = content["nodes_by_type"].get("whitepaper", [])
    if whitepapers:
        parts.append("=== WHITEPAPER (bereits generierte Zusammenfassung) ===")
        for wp in whitepapers:
            if wp.content:
                parts.append(wp.content)
        parts.append("")

    # Summaries
    if content["summaries"]:
        parts.append("=== ZUSAMMENFASSUNGEN ===")
        for node in content["summaries"]:
            parts.append(f"- {node.title}: {node.summary}")
        parts.append("")

    # Child ideas
    if content["child_ideas"]:
        parts.append("=== IDEEN ===")
        for idea in content["child_ideas"]:
            parts.append(f"### {idea.title}")
            if idea.description:
                parts.append(idea.description)
            if idea.tags:
                parts.append(f"Tags: {', '.join(idea.tags)}")
            parts.append("")

    # Regular notes
    notes = content["nodes_by_type"].get("note", [])
    if notes:
        parts.append("=== NOTIZEN ===")
        for node in notes:
            parts.append(f"### {node.title or 'Untitled'}")
            if node.content_json:
                parts.append(_extract_content_text(node.content_json, node.content or ""))
            elif node.content:
                parts.append(node.content)
            parts.append("")

    # Project structure
    ps = content["project_structure"]
    if ps:
        parts.append("=== PROJEKTSTRUKTUR ===")
        if ps.get("project_name"):
            parts.append(f"Projektname: {ps['project_name']}")
        if ps.get("description"):
            parts.append(f"Beschreibung: {ps['description']}")

        func_reqs = ps.get("requirements", {}).get("functional", [])
        if func_reqs:
            parts.append("\nFunktionale Anforderungen:")
            for req in func_reqs:
                parts.append(f"- [{req.get('id', '?')}] {req.get('description', '')} (Prioritaet: {req.get('priority', 'medium')})")

        nfunc_reqs = ps.get("requirements", {}).get("non_functional", [])
        if nfunc_reqs:
            parts.append("\nNicht-funktionale Anforderungen:")
            for req in nfunc_reqs:
                parts.append(f"- [{req.get('id', '?')}] {req.get('description', '')} ({req.get('category', '')})")

        features = ps.get("features", [])
        if features:
            parts.append("\nFeatures:")
            for f in features:
                parts.append(f"- {f.get('name', '?')}: {f.get('description', '')} (Prioritaet: {f.get('priority', 'medium')})")

        phases = ps.get("phases", [])
        if phases:
            parts.append("\nImplementierungsphasen:")
            for phase in phases:
                parts.append(f"- {phase.get('name', '?')}")
                for d in phase.get("deliverables", []):
                    parts.append(f"  - {d}")
        parts.append("")

    # Feature docs
    feature_docs = content["nodes_by_type"].get("feature_doc", [])
    if feature_docs:
        parts.append("=== FEATURE-DOKUMENTATION ===")
        for doc in feature_docs:
            parts.append(f"### {doc.title or 'Feature'}")
            if doc.content:
                parts.append(doc.content)
            parts.append("")

    # Structured content (SWOT, Kanban, etc.)
    structured_types = ["kanban", "swot", "mindmap", "user_story", "flowchart",
                        "action_list", "table", "pros_cons_table", "hierarchy",
                        "technical_specs", "comparison_table"]
    for node in content["all_nodes"]:
        if node.content_json and node.node_type not in ("whitepaper", "feature_doc", "feature_index", "projektdoku"):
            content_type = node.content_json.get("type", "")
            if content_type in structured_types:
                parts.append(f"=== STRUKTURIERTER INHALT: {node.title or content_type} ({content_type}) ===")
                parts.append(_extract_content_text(node.content_json, node.content or ""))
                parts.append("")

    # Mermaid diagrams
    if content["mermaid_diagrams"]:
        parts.append("=== DIAGRAMME ===")
        for diagram in content["mermaid_diagrams"]:
            parts.append(f"### {diagram.title} ({diagram.diagram_type})")
            parts.append(diagram.to_markdown())
            parts.append("")

    return "\n".join(parts)


def _synthesize_project_doc(title: str, input_text: str, stats: Dict[str, int]) -> Optional[str]:
    """
    Call LLM to synthesize a cohesive project document from collected content.
    """
    client = _get_openrouter_client()
    if not client:
        logger.error("OpenRouter client not available for doc synthesis")
        return None

    model = get_model("doc_generation")

    system_prompt = """Du bist ein professioneller technischer Redakteur. Deine Aufgabe ist es,
aus fragmentierten Ideen, Notizen und strukturierten Inhalten ein kohaerentes, professionelles
Projektdokument zu erstellen.

REGELN:
- Schreibe auf Deutsch (es sei denn der Input ist komplett Englisch)
- Erstelle ein zusammenhaengendes Narrativ, keine blosse Auflistung
- Verwende sauberes Markdown mit klarer Hierarchie (# ## ### etc.)
- Mermaid-Diagramme UNVERAENDERT als ```mermaid Code-Bloecke einbetten
- Widersprueche zwischen Ideen erkennen und als "Hinweis:" markieren
- Luecken identifizieren (z.B. "Hinweis: Keine nicht-funktionalen Anforderungen definiert")
- SWOT-Analysen, Kanban-Boards etc. sinnvoll in den Fliesstext integrieren
- Am Ende ein kurzes Fazit mit naechsten Schritten

DOKUMENTSTRUKTUR:
1. Projektuebersicht (Einleitung + Kernidee)
2. Zusammenfassung (Executive Summary)
3. Ideen & Konzepte (thematisch gruppiert, nicht als Liste)
4. Anforderungen (funktional + nicht-funktional, falls vorhanden)
5. Features (mit Beschreibung und Prioritaet)
6. Implementierungsphasen (falls vorhanden)
7. Diagramme (Mermaid-Bloecke einbetten)
8. Analyse & Strukturierte Inhalte (SWOT, Kanban etc.)
9. Fazit & Naechste Schritte

Ueberspringe Sektionen die keine Inhalte haben. Beginne NICHT mit einem Inhaltsverzeichnis -
starte direkt mit der Projektuebersicht."""

    user_prompt = f"""Erstelle ein professionelles Projektdokument aus folgenden gesammelten Inhalten:

PROJEKTTITEL: {title}
STATISTIK: {stats.get('ideas', 0)} Ideen, {stats.get('features', 0)} Features, {stats.get('diagrams', 0)} Diagramme, {stats.get('nodes', 0)} Canvas-Nodes

--- GESAMMELTE INHALTE ---

{input_text[:12000]}

--- ENDE DER INHALTE ---

Erstelle jetzt das vollstaendige Projektdokument als sauberes Markdown.
Beginne mit: # {title} — Projektdokumentation"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=4000,
            temperature=0.4,
        )

        content = response.choices[0].message.content.strip()
        logger.info(f"Project doc synthesized ({len(content)} chars, model: {model})")
        return content

    except Exception as e:
        logger.error(f"LLM doc synthesis failed: {e}")
        return None


def _fallback_assemble_doc(title: str, content: Dict[str, Any]) -> str:
    """
    Fallback: assemble document without LLM when API is unavailable.
    """
    from spaces.ideas.tools.format_dispatcher import _extract_content_text
    from datetime import datetime

    lines = [
        f"# {title} — Projektdokumentation",
        "",
        f"> Generiert am {datetime.now().strftime('%d.%m.%Y %H:%M')} (ohne LLM-Synthese)",
        "",
    ]

    bubble = content["bubble"]
    if bubble.description:
        lines.extend(["## Projektuebersicht", "", bubble.description, ""])

    # Whitepapers
    for wp in content["nodes_by_type"].get("whitepaper", []):
        if wp.content:
            lines.extend(["## Whitepaper", "", wp.content, ""])

    # Ideas
    if content["child_ideas"]:
        lines.append("## Ideen")
        lines.append("")
        for idea in content["child_ideas"]:
            lines.append(f"### {idea.title}")
            if idea.description:
                lines.append(idea.description)
            lines.append("")

    # Project structure
    ps = content["project_structure"]
    if ps:
        features = ps.get("features", [])
        if features:
            lines.append("## Features")
            lines.append("")
            for f in features:
                lines.append(f"- **{f.get('name', '?')}** ({f.get('priority', 'medium')}): {f.get('description', '')}")
            lines.append("")

    # Mermaid diagrams
    if content["mermaid_diagrams"]:
        lines.append("## Diagramme")
        lines.append("")
        for d in content["mermaid_diagrams"]:
            lines.append(f"### {d.title}")
            lines.append(d.to_markdown())
            lines.append("")

    lines.extend(["---", f"*Automatisch generiert von VibeMind am {datetime.now().strftime('%d.%m.%Y')}*"])
    return "\n".join(lines)


def generate_project_doc(params: Dict[str, Any]) -> str:
    """
    Generate a cohesive project documentation from all bubble content via LLM.

    Collects ideas, whitepapers, project structures, feature docs, diagrams,
    and structured content — then synthesizes them into a professional
    Markdown document using an LLM.

    Voice triggers: "Erstelle Projektdoku", "Generiere Dokumentation",
                   "Exportiere als Dokument", "Erstelle Doku"

    Args (via params):
        bubble_name: Name of bubble to document (optional - uses current)

    Returns:
        str: Summary of generated documentation with file path
    """
    bubble_name = (params.get("bubble_name") or "").strip()

    logger.info(f"generate_project_doc called: bubble_name='{bubble_name}'")

    # Resolve bubble
    current_bubble_id = None
    try:
        from spaces.ideas.tools.bubble_tools import get_current_bubble_db_id
        current_bubble_id = get_current_bubble_db_id()
    except ImportError:
        pass

    ideas_repo = _get_ideas_repo()

    if bubble_name:
        idea = ideas_repo.get_by_title(bubble_name)
        if not idea:
            return f"Bubble '{bubble_name}' nicht gefunden."
    else:
        if current_bubble_id:
            idea = ideas_repo.get(current_bubble_id)
            if not idea:
                return "Aktuelle Bubble nicht gefunden."
        else:
            return "Bitte gib einen Bubble-Namen an oder betrete zuerst eine Bubble."

    # Phase A: Collect all content
    collected = _collect_bubble_content(idea.id, idea)

    # Check if there's anything to document
    total_nodes = len(collected["all_nodes"])
    total_ideas = len(collected["child_ideas"])
    if total_nodes == 0 and total_ideas == 0:
        return f"'{idea.title}' hat noch keine Inhalte. Fuege zuerst Ideen oder Notizen hinzu."

    # Build stats
    stats = {
        "ideas": total_ideas,
        "nodes": total_nodes,
        "features": len(collected["project_structure"].get("features", [])) if collected["project_structure"] else 0,
        "diagrams": len(collected["mermaid_diagrams"]),
    }

    # Phase B: LLM synthesis
    input_text = _build_doc_input_text(collected)
    doc_markdown = _synthesize_project_doc(idea.title, input_text, stats)

    # Fallback to assembly if LLM fails
    if not doc_markdown:
        logger.warning("LLM synthesis failed, using fallback assembly")
        doc_markdown = _fallback_assemble_doc(idea.title, collected)

    # Phase C: Persist
    # 1. Write to filesystem
    file_path = None
    try:
        from publishing import get_doc_publisher
        publisher = get_doc_publisher()
        from publishing.base_publisher import _slugify
        slug = _slugify(idea.title)
        file_path = publisher.publish_doc(slug, idea.title, doc_markdown)
    except Exception as e:
        logger.error(f"DocPublisher failed: {e}")

    # 2. Create canvas node
    canvas_repo = _get_canvas_repo()
    existing_nodes = [
        n for n in collected["all_nodes"]
        if n.node_type == "projektdoku"
    ]

    # Update existing or create new
    if existing_nodes:
        doc_node = existing_nodes[0]
        doc_node.content = doc_markdown
        canvas_repo.update_node(doc_node)
        logger.info(f"Updated existing projektdoku node: {doc_node.id}")
    else:
        doc_node = canvas_repo.create_node(
            node_type="projektdoku",
            title=f"{idea.title} — Projektdokumentation",
            content=doc_markdown,
            linked_idea_id=idea.id,
            x=100,
            y=-200,
        )
        logger.info(f"Created projektdoku canvas node: {doc_node.id}")

    # 3. Broadcast to Electron
    _broadcast_to_electron({
        "type": "projektdoku_generated",
        "bubble_id": idea.id,
        "bubble_title": idea.title,
        "node_id": doc_node.id,
        "file_path": str(file_path) if file_path else None,
        "stats": stats,
    })

    # Build response
    path_hint = f" Datei: {file_path}" if file_path else ""
    return (
        f"Projektdokumentation fuer '{idea.title}' erstellt — "
        f"{stats['ideas']} Ideen, {stats['features']} Features, "
        f"{stats['diagrams']} Diagramme.{path_hint}"
    )


# ==============================================================================
# TOOL REGISTRY
# ==============================================================================

SUMMARY_TOOLS = {
    "summarize_idea": summarize_idea,
    "list_summaries": list_summaries,
    "get_summary": get_summary,
    "generate_white_paper": generate_white_paper,
    "generate_project_structure": generate_project_structure,
    "generate_feature_docs": generate_feature_docs,
    "submit_to_req_orchestrator": submit_to_req_orchestrator,
    "get_requirement_clarifications": get_requirement_clarifications,
    "sync_shuttle_from_orchestrator": sync_shuttle_from_orchestrator,
    "create_stage_shuttles": create_stage_shuttles,
    "generate_project_doc": generate_project_doc,
}


def register_summary_tools(tools_manager) -> None:
    """Register all summary tools with the tools manager."""
    print("Registering summary tools with observer...")
    for tool_name, tool_func in SUMMARY_TOOLS.items():
        tools_manager.register_with_observer(tool_name, tool_func)
        print(f"  - {tool_name}")


__all__ = [
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
]
