"""Navigator metadata keyed by canonical VibeMind space IDs.

Every space gets:
  - label:        Human-readable name (voice-friendly).
  - event_prefix: Brain event namespace (idea., code., etc.).
  - stream:       Redis stream the backend agent listens on (or None).
  - aliases:      Voice/text shortcuts that resolve to this space.
  - description:  One sentence for embedding-based semantic match.
  - use_when:     Heuristic for the LLM-layer tiebreaker.
  - capabilities: Top event-types this space handles.

Both the navigator MCP and (eventually) voice/python/tools/navigation_tools.py
should import from here so there's one canonical list.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class SpaceMeta(TypedDict, total=False):
    label: str
    event_prefix: str
    stream: Optional[str]
    aliases: List[str]
    description: str
    use_when: str
    capabilities: List[str]
    # Renderer ID = name used by the Electron Multiverse JS scene
    # (window.multiverseApp.spaces keys). None = space exists in the Brain
    # registry but has no 3D representation in the renderer (e.g. minibook,
    # schedule, research). Verified live via CDP 2026-06-02.
    renderer_id: Optional[str]


SPACES: Dict[str, SpaceMeta] = {
    "agentfarm": {
        "label": "AgentFarm",
        "event_prefix": "agentfarm.",
        "stream": "events:tasks:agentfarm",
        "aliases": ["agents", "team", "farm", "autogen", "multi-agent"],
        "description": "Multi-agent teams, AutoGen orchestration, agent crews collaborating on tasks.",
        "use_when": "User wants a team of AI agents to collaborate on a problem",
        "capabilities": ["agentfarm.create_team", "agentfarm.run", "agentfarm.list_teams"],
        "renderer_id": "agentfarm",
    },
    "brain": {
        "label": "Brain",
        "event_prefix": "brain.",
        "stream": None,
        "aliases": ["thalamus", "cortex", "cognitive", "mind"],
        "description": "Cognitive state, thinking, neuroscience-inspired reasoning, Thalamus + MicroAgentPool.",
        "use_when": "User asks about cognition, reasoning, thinking, or wants to query the brain itself",
        "capabilities": ["brain.think", "brain.state", "brain.diagnostics"],
        "renderer_id": "thebrain",
    },
    "coding": {
        "label": "Coding",
        "event_prefix": "code.",
        "stream": "events:tasks:coding",
        "aliases": ["dev", "engine", "code", "programming", "vibe coder", "build"],
        "description": "Generate code, build apps, autonomous coding pipeline, vibe coder.",
        "use_when": "User wants to program, generate, or build software",
        "capabilities": ["code.generate", "code.status", "project.create"],
        "renderer_id": "projects",
    },
    "desktop": {
        "label": "Desktop",
        "event_prefix": "desktop.",
        "stream": "events:tasks:desktop",
        "aliases": ["adam", "automation", "os", "computer", "click", "screenshot"],
        "description": "Desktop automation, mouse/keyboard control, screen reading, application control.",
        "use_when": "User wants to automate the desktop, control apps, or interact with the OS",
        "capabilities": ["desktop.open_app", "desktop.click", "desktop.screenshot"],
        "renderer_id": "desktop",
    },
    "flowzen": {
        "label": "Flowzen",
        "event_prefix": "flowzen.",
        "stream": None,
        "aliases": ["flow", "zen", "visual", "diagram"],
        "description": "Visual flow diagrams, data pipelines, visual programming, node-graph orchestration.",
        "use_when": "User wants to visualize data flow or build a node-graph pipeline",
        "capabilities": ["flowzen.create", "flowzen.run"],
        "renderer_id": "flowzen",
    },
    "ideas": {
        "label": "Ideas",
        "event_prefix": "idea.",
        "stream": "events:tasks:ideas",
        "aliases": ["bubbles", "rachel", "multiverse", "thoughts", "notes", "brainstorm"],
        "description": "Idea-space, bubbles as idea containers, brainstorming, knowledge graph of thoughts.",
        "use_when": "User wants to capture, organize, or explore ideas and bubbles",
        "capabilities": ["idea.create", "idea.list", "bubble.create", "bubble.enter"],
        "renderer_id": "ideas",
    },
    "minibook": {
        "label": "Minibook",
        "event_prefix": "minibook.",
        "stream": "events:tasks:minibook",
        "aliases": ["bus", "hub", "messages", "log"],
        "description": "Central message bus, collaboration hub, agent communication log.",
        "use_when": "User wants to inspect agent messages or the collaboration hub",
        "capabilities": ["minibook.post", "minibook.read"],
        "renderer_id": None,
    },
    "mirofish": {
        "label": "MiroFish",
        "event_prefix": "mirofish.",
        "stream": "events:tasks:mirofish_pred",
        "aliases": ["miro", "predict", "forecast", "fish"],
        "description": "Predictive analytics, forecasting, time-series prediction.",
        "use_when": "User wants predictions, forecasts, or time-series analysis",
        "capabilities": ["mirofish.predict"],
        "renderer_id": "mirofish",
    },
    "n8n": {
        "label": "n8n",
        "event_prefix": "n8n.",
        "stream": "events:tasks:n8n",
        "aliases": ["workflow", "automation-graph", "integration", "zapier"],
        "description": "Workflow automation, integration pipelines, n8n nodes, trigger-action chains.",
        "use_when": "User wants to build a workflow that connects services or automates a multi-step process",
        "capabilities": ["n8n.generate", "n8n.list", "n8n.activate"],
        "renderer_id": None,
    },
    "research": {
        "label": "Research",
        "event_prefix": "research.",
        "stream": "events:tasks:zeroclaw",
        "aliases": ["zeroclaw", "web", "search", "fact-find", "investigate"],
        "description": "Web research, source aggregation, fact-finding, ZeroClaw deep-search.",
        "use_when": "User wants to research, gather facts, or find information on the web",
        "capabilities": ["research.query", "research.deep"],
        "renderer_id": None,
    },
    "roarboot": {
        "label": "Rowboat",
        "event_prefix": "roarboot.",
        "stream": "events:tasks:roarboot",
        "aliases": ["roarboot", "kg", "knowledge-graph", "retrieval"],
        "description": "Knowledge graph retrieval, structured-data queries, Rowboat KG.",
        "use_when": "User wants to query a knowledge graph or retrieve structured facts",
        "capabilities": ["roarboot.query"],
        "renderer_id": "roarboot",
    },
    "schedule": {
        "label": "Schedule",
        "event_prefix": "schedule.",
        "stream": "events:tasks:schedule",
        "aliases": ["cron", "tasks", "timer", "reminder", "scheduled"],
        "description": "Scheduled tasks, cron jobs, timers, reminders, APScheduler.",
        "use_when": "User wants to schedule a task or set a recurring reminder",
        "capabilities": ["schedule.create", "schedule.list"],
        "renderer_id": None,
    },
    "bubbles": {
        "label": "Bubbles",
        "event_prefix": "bubble.",
        "stream": None,
        "aliases": ["pipeline", "swe", "requirements", "ship"],
        "description": "Bubble->project pipeline, requirements engineering, SWE Design shuttles.",
        "use_when": "User wants to promote a bubble to a project or run the requirements pipeline",
        "capabilities": ["bubble.evaluate", "bubble.promote"],
        "renderer_id": "swedesign",
    },
    "video": {
        "label": "Video",
        "event_prefix": "video.",
        "stream": "events:tasks:video",
        "aliases": ["clip", "render", "movie", "footage"],
        "description": "Video generation, clip rendering, footage processing.",
        "use_when": "User wants to create or process a video",
        "capabilities": ["video.generate", "video.render"],
        "renderer_id": "video",
    },
}


SPACE_NAMES: List[str] = list(SPACES.keys())


def resolve_alias(query: str) -> Optional[str]:
    """Layer 1 resolver: keyword/alias match. Returns canonical space-id or None.

    Also resolves the renderer-side names (projects, thebrain, roarboot,
    swedesign) back to the canonical Brain registry id, so callers can use
    whichever vocabulary they have on hand.
    """
    if not query:
        return None
    q = query.strip().lower()
    legacy_aliases = {
        "autogen": "agentfarm",
        "rowboat": "roarboot",
        "shuttles": "bubbles",
    }
    q = legacy_aliases.get(q, q)
    if q in SPACES:
        return q
    for space_id, meta in SPACES.items():
        if meta["label"].lower() == q:
            return space_id
        if q in [a.lower() for a in meta["aliases"]]:
            return space_id
        # Renderer-id round-trip: "projects" -> "coding", "thebrain" -> "brain"
        if meta.get("renderer_id") and meta["renderer_id"].lower() == q:
            return space_id
    return None


def get_renderer_id(space_id: str) -> Optional[str]:
    """Map a canonical space-id to the name used by the Electron Multiverse JS scene.

    Returns None when the space exists in Brain's registry but has no 3D
    representation in the renderer (minibook, n8n, research, schedule).
    The caller should then either skip the UI-sync or fall back to a stub
    page. Verified live against window.multiverseApp.spaces 2026-06-02.
    """
    meta = SPACES.get(space_id)
    if not meta:
        return None
    return meta.get("renderer_id")


def search_aliases(query: str) -> List[str]:
    """Layer 1 fuzzy: partial alias/label/id matches. Returns ranked space-ids."""
    if not query:
        return []
    q = query.strip().lower()
    hits: List[tuple[int, str]] = []
    for space_id, meta in SPACES.items():
        score = 0
        if q == space_id or q == meta["label"].lower():
            score += 100
        if q in space_id or q in meta["label"].lower():
            score += 30
        for alias in meta["aliases"]:
            al = alias.lower()
            if q == al:
                score += 80
            elif q in al or al in q:
                score += 20
        if score > 0:
            hits.append((score, space_id))
    hits.sort(reverse=True)
    return [sid for _, sid in hits]


def get_meta(space_id: str) -> Optional[SpaceMeta]:
    return SPACES.get(space_id)


def embedding_corpus(space_id: str) -> str:
    """Build a dense text blob for embedding indexing."""
    m = SPACES[space_id]
    return (
        f"{m['label']}. {m['description']} "
        f"Use when: {m['use_when']}. "
        f"Aliases: {', '.join(m['aliases'])}. "
        f"Handles: {', '.join(m['capabilities'])}."
    )
