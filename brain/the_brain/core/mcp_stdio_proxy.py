"""
Brain stdio-MCP proxy.

Claude Code speaks stdio-MCP. Brain speaks HTTP on port 5000. This file
bridges the two: it starts a stdio-MCP server that forwards each tool call
to the running Brain FastAPI instance.

Design:
  - Brain must already be running on BRAIN_URL (default http://127.0.0.1:5000).
  - If Brain is offline, each tool returns a structured error instead of
    crashing the MCP connection. Claude Code stays happy.
  - No Brain internals are imported here — this file only does HTTP.

Run directly for local testing:
    python mcp_stdio_proxy.py

Or via .mcp.json:
    {
      "brain-core": {
        "type": "stdio",
        "command": "python",
        "args": [".../core/mcp_stdio_proxy.py"],
        "env": { "BRAIN_URL": "http://127.0.0.1:5000" }
      }
    }
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests
from mcp.server.fastmcp import FastMCP


BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:5000").rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("BRAIN_HTTP_TIMEOUT", "120"))


mcp = FastMCP(
    "Brain Core",
    instructions=(
        "Stdio-MCP bridge to the running Brain HTTP server. "
        "Use 'think' to chat with the Brain (routes through Thalamus + "
        "MicroAgentPool + TalkerModule). Use 'brain_state' / 'bridges' / "
        "'diagnostics' for introspection. Brain must be running on "
        f"{BRAIN_URL} — start it with "
        "`python vibemind-os/brain/the_brain/start_server.py` if offline."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────

def _get(path: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    try:
        r = requests.get(f"{BRAIN_URL}{path}", timeout=timeout or HTTP_TIMEOUT)
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}", "body": r.text[:500], "url": path}
        try:
            return r.json()
        except ValueError:
            return {"text": r.text}
    except requests.exceptions.ConnectionError:
        return {"error": "brain_offline", "detail": f"cannot reach {BRAIN_URL}{path}"}
    except requests.exceptions.Timeout:
        return {"error": "timeout", "detail": f"no response from {path} within {timeout or HTTP_TIMEOUT}s"}
    except Exception as e:
        return {"error": type(e).__name__, "detail": str(e)}


def _post(path: str, payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
    try:
        r = requests.post(
            f"{BRAIN_URL}{path}",
            json=payload,
            timeout=timeout or HTTP_TIMEOUT,
            allow_redirects=True,
        )
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}", "body": r.text[:500], "url": path}
        try:
            return r.json()
        except ValueError:
            return {"text": r.text}
    except requests.exceptions.ConnectionError:
        return {"error": "brain_offline", "detail": f"cannot reach {BRAIN_URL}{path}"}
    except requests.exceptions.Timeout:
        return {"error": "timeout", "detail": f"no response from {path} within {timeout or HTTP_TIMEOUT}s"}
    except Exception as e:
        return {"error": type(e).__name__, "detail": str(e)}


# ──────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def think(message: str) -> Dict[str, Any]:
    """Send a message to the Brain for cognitive processing.

    Routes through Thalamus → Knowledge retrieval → InternalMonologue →
    MicroAgentPool (LLM) → TalkerModule. Returns the final response plus
    routing info, confidence, and a trace of modules that ran.

    Args:
        message: The prompt / question for the Brain.
    """
    result = _post("/api/brain/chat", {"message": message})
    # Slim down for MCP response — trace can be huge
    if isinstance(result, dict) and "thought_trace" in result:
        trace = result.get("thought_trace") or []
        result["thought_trace"] = [
            {
                "module": t.get("module"),
                "category": t.get("category"),
                "content": (t.get("content") or "")[:200],
                "confidence": t.get("confidence"),
            }
            for t in trace
        ]
    return result


@mcp.tool()
def brain_state() -> Dict[str, Any]:
    """Get the Brain's current cognitive state snapshot.

    Returns the radial meta-router state including attention gain, precision
    boost, FFN throughput, threshold modulation, and consciousness level.
    """
    return _get("/api/brain/state")


@mcp.tool()
def bridges() -> Dict[str, Any]:
    """Get the state of all 10 Brain bridges.

    Returns neuromodulation, cortex, limbic, sleep_wake, motor, defense,
    memory, integration, visceral, and social bridge activations.
    """
    return _get("/api/bridges")


@mcp.tool()
def diagnostics() -> Dict[str, Any]:
    """Get a high-level Brain health report.

    Returns boolean flags for every major subsystem (brain_chat,
    continuous_thinking, agent_loop, radial_network, etc.) plus counts
    (moltbook_entries, cte_thought_count).
    """
    return _get("/api/brain/diagnostics")


@mcp.tool()
def thoughts(limit: int = 10) -> Dict[str, Any]:
    """Get the Brain's recent autonomous thoughts (ThoughtStream).

    These are the 'idle thoughts' the ContinuousThinkingEngine generates
    in the background — not responses to user input.

    Args:
        limit: Max thoughts to return (default 10, max 100).
    """
    limit = max(1, min(100, int(limit)))
    return _get(f"/api/brain/thoughts?limit={limit}")


@mcp.tool()
def llm_stats() -> Dict[str, Any]:
    """Get LLM router call statistics.

    Returns per-model call counts, failures, token usage, estimated cost,
    and success rate. Useful for checking if the Brain is actually calling
    LLMs or falling back to template responses.
    """
    return _get("/api/llm/stats")


@mcp.tool()
def llm_probe() -> Dict[str, Any]:
    """Diagnostic: is the MicroAgentPool wired + can it call an LLM right now?

    Performs a live test call with the 'responder' agent. Useful for
    debugging 'Brain gives template answers' — tells you whether the LLM
    pipeline is the problem or something downstream.
    """
    return _get("/api/llm/probe", timeout=60)


@mcp.tool()
def modulation() -> Dict[str, Any]:
    """Get the 4 composite modulation factors + consciousness level."""
    return _get("/api/modulation")


@mcp.tool()
def health() -> Dict[str, Any]:
    """Quick liveness check for the Brain HTTP server."""
    return _get("/api/health", timeout=5)


# ──────────────────────────────────────────────────────────────────────
# Knowledge Graph tools (Qdrant-backed unified KG)
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def kg_search(
    query: str,
    node_type: str = "",
    collection: str = "",
    limit: int = 10,
    threshold: float = 0.0,
) -> Dict[str, Any]:
    """Semantic kNN search across cognitive Brain Knowledge Graph collections.

    The KG is split into cognitive categories:
      - episodic:   thoughts, chat responses (Hippocampus-like, flüchtig)
      - semantic:   facts, concepts (consolidated knowledge)
      - procedural: spaces, events (routing/action patterns)
      - state:      snapshots (working memory)
      - artifacts:  Rowboat bubbles + ideas (external refs)

    Args:
        query: Free-text query. Multilingual (DE/EN) via Qwen3-Embedding.
        node_type: Optional node_type filter (thought|response|bubble|
            idea|space|event|snapshot|fact|concept). Auto-narrows the
            collection.
        collection: Optional logical collection (episodic|semantic|
            procedural|state|artifacts). If empty, searches all cognitive
            collections and merges by score.
        limit: Max hits (default 10, capped at 50).
        threshold: Min cosine score (0.0–1.0). 0 = no filter.

    Returns: {query, node_type, collection, count, hits: [...]}
    """
    limit = max(1, min(50, int(limit)))
    from urllib.parse import urlencode
    params = {"q": query, "limit": limit, "threshold": threshold}
    if node_type:
        params["node_type"] = node_type
    if collection:
        params["collection"] = collection
    return _get(f"/api/kg/search?{urlencode(params)}", timeout=30)


@mcp.tool()
def kg_related(point_id: str) -> Dict[str, Any]:
    """Return the bidirectional edges (linked.*) of a KG point.

    Args:
        point_id: Qdrant UUID of the point (from a previous kg_search hit).

    Returns: {point_id, node_type, content, linked: {thoughts, responses,
        bubbles, ideas, spaces, events}, ...}
    """
    from urllib.parse import urlencode
    return _get(f"/api/kg/related?{urlencode({'point_id': point_id})}")


@mcp.tool()
def kg_stats() -> Dict[str, Any]:
    """Stats about the unified Brain Knowledge Graph.

    Returns point counts per node type, edges built, errors, and the
    underlying Qdrant collection name.
    """
    return _get("/api/kg/stats")


# ──────────────────────────────────────────────────────────────────────
# Bidirectional Minibook dispatch (Phase F)
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def claude_subagent(
    prompt: str,
    system: str = "",
    model: str = "anthropic/claude-haiku-4.5",
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """Dispatch a focused subtask to Claude as Brain's coding/reasoning subagent.

    Use for: code generation, refactoring, complex reasoning, text composition
    that exceeds Brain's heuristic responder.

    Args:
        prompt: clear, focused single-shot task
        system: optional system prompt (role/persona)
        model: OpenRouter model id (default: claude-haiku-4.5; can be claude-opus-4-6 etc.)
        max_tokens: max output tokens

    Returns: {ok, tool, model, text, latency_ms, error?}
    """
    payload = {"tool": "claude_subagent", "prompt": prompt}
    if system:
        payload["system"] = system
    if model:
        payload["model"] = model
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return _post("/api/brain/subagent", payload, timeout=120)


@mcp.tool()
def groq_subagent(
    prompt: str,
    model: str = "groq::llama-3.3-70b-versatile",
    max_tokens: int = 512,
) -> Dict[str, Any]:
    """Dispatch a fast/cheap subtask to Groq (Llama 3.3 70B by default).

    Use for: classification, summarization, quick reasoning. Faster + cheaper
    than claude_subagent.

    Args:
        prompt: focused subtask prompt
        model: 'groq::<model-name>' for direct Groq API
        max_tokens: max output tokens
    """
    payload = {
        "tool": "groq_subagent",
        "prompt": prompt,
        "model": model,
        "max_tokens": max_tokens,
    }
    return _post("/api/brain/subagent", payload, timeout=60)


@mcp.tool()
def subagent_stats() -> Dict[str, Any]:
    """Stats on Brain's subagent dispatcher (calls per tool, failures)."""
    return _get("/api/brain/subagent/stats")


# ──────────────────────────────────────────────────────────────────────
# Consolidation (Phase L)
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def consolidate_now() -> Dict[str, Any]:
    """Run one consolidation pass: cluster recent episodic thoughts via DBSCAN
    and create concept nodes in brain-semantic for dense clusters.

    Triggers groq_subagent calls to summarise each cluster. Idempotent: same
    cluster gets the same concept_id (just refreshes member links).

    Returns: {ok, summary: {thoughts, clusters_total, concepts_created,
                            concepts_updated}, stats: {...}}
    """
    return _post("/api/kg/consolidate", {}, timeout=120)


@mcp.tool()
def consolidation_stats() -> Dict[str, Any]:
    """Stats about Brain's consolidation engine (ticks, concepts, errors)."""
    return _get("/api/kg/consolidation_stats")


# ──────────────────────────────────────────────────────────────────────
# State Snapshots (Phase M)
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def snapshot_now() -> Dict[str, Any]:
    """Capture one Brain self-state snapshot (bridges + modulation +
    state) into the brain-state collection. Returns the new snapshot_id.

    Snapshots run automatically every 5 minutes, but call this for an
    immediate capture (e.g. before/after a notable event)."""
    return _post("/api/kg/snapshot", {}, timeout=15)


@mcp.tool()
def snapshot_stats() -> Dict[str, Any]:
    """Stats about Brain's snapshot engine (ticks, written, errors)."""
    return _get("/api/kg/snapshot_stats")


@mcp.tool()
def tribe_predict(text: str) -> Dict[str, Any]:
    """TriBE v2 biological grounding: text -> cortical activation -> 10 bridge levels.

    Uses Meta's TriBE v2 fMRI encoder to produce a biologically-plausible
    neural signature for any text. Returns per-ROI activations and per-bridge
    levels (cortex, limbic, defense, motor, memory, integration, etc.).

    If the gated Llama-3.2-3B weights aren't yet approved by Meta and
    TRIBE_DUMMY=1 is set, returns a deterministic pseudo-vector.

    Args:
        text: input text to neurally-encode
    """
    return _post("/api/tribe/predict", {"text": text}, timeout=120)


@mcp.tool()
def tribe_status() -> Dict[str, Any]:
    """Diagnostic: is TriBE loaded, model path, last error, call stats."""
    return _get("/api/tribe/status")


@mcp.tool()
def auto_dispatch_stats() -> Dict[str, Any]:
    """Stats on BrainChat's auto-dispatch (Phase F.4): how often user
    @-mentions of Minibook agents were forwarded as tasks."""
    return _get("/api/brain/auto_dispatch_stats")


# ──────────────────────────────────────────────────────────────────────
# Ideas-Space (Phase O.1) — Brain's first external service connector.
# Brain proxies to the Ideas HTTP wrapper at port 5102.
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def idea_list(limit: int = 20, query: str = "") -> Dict[str, Any]:
    """List ideas from VibeMind Ideas-Space.

    Args:
        limit: max ideas to return (default 20, capped at 200).
        query: optional substring filter on title/description.
    """
    limit = max(1, min(200, int(limit)))
    params = {"limit": limit}
    if query:
        params["query"] = query
    from urllib.parse import urlencode
    return _get(f"/api/ideas/list?{urlencode(params)}")


@mcp.tool()
def idea_create(title: str, content: str = "", tags: Optional[list] = None) -> Dict[str, Any]:
    """Create a new idea in the Ideas-Space.

    Args:
        title: short title (required)
        content: longer description / body
        tags: optional list of tag strings
    """
    payload: Dict[str, Any] = {"title": title, "content": content}
    if tags:
        payload["tags"] = tags
    return _post("/api/ideas/create", payload)


@mcp.tool()
def idea_search(query: str, limit: int = 10, min_score: float = 0.3) -> Dict[str, Any]:
    """Semantic Qwen-embedding search over all ideas.

    Returns ideas sorted by cosine similarity to the query.

    Args:
        query: free-text query (multilingual DE/EN)
        limit: max hits (default 10, capped at 50)
        min_score: minimum cosine similarity 0..1 (default 0.3)
    """
    limit = max(1, min(50, int(limit)))
    return _post(
        "/api/ideas/search",
        {"query": query, "limit": limit, "min_score": min_score},
        timeout=30,
    )


@mcp.tool()
def idea_expand(idea_id: str, prompt: str = "", count: int = 3) -> Dict[str, Any]:
    """AI-expand an idea via Brain's groq_subagent (Llama 3.3 70b).

    Generates `count` related/extending concepts based on the existing
    idea's title and description. Optionally biased by `prompt`.

    Args:
        idea_id: id from idea_list / idea_search
        prompt: optional extra direction for the expansion
        count: number of suggestions (default 3)
    """
    payload: Dict[str, Any] = {"count": int(count)}
    if prompt:
        payload["prompt"] = prompt
    return _post(f"/api/ideas/{idea_id}/expand", payload, timeout=120)


@mcp.tool()
def idea_health() -> Dict[str, Any]:
    """Quick check of the Ideas-Space HTTP wrapper (port 5102)."""
    return _get("/api/ideas/health", timeout=5)


# ── Bubbles (Block 1) ──────────────────────────────────────────────────

@mcp.tool()
def bubble_list(limit: int = 50) -> Dict[str, Any]:
    """List top-level VibeMind bubbles (Spaces).

    Each bubble is a container for ideas. Returns titles, ids, and the
    number of child ideas (`child_count`) inside each.
    """
    limit = max(1, min(500, int(limit)))
    return _get(f"/api/bubbles/list?limit={limit}")


@mcp.tool()
def bubble_create(title: str, description: str = "", tags: Optional[list] = None) -> Dict[str, Any]:
    """Create a new top-level bubble (Space) for grouping ideas.

    Args:
        title: short name for the Space (required)
        description: optional longer description
        tags: optional list of tag strings
    """
    payload: Dict[str, Any] = {"title": title, "description": description}
    if tags:
        payload["tags"] = tags
    return _post("/api/bubbles/create", payload)


@mcp.tool()
def bubble_delete(bubble_id: str, force: bool = False) -> Dict[str, Any]:
    """Delete a bubble by id.

    By default refuses if the bubble has child ideas. Pass `force=True`
    to cascade-delete all children too.
    """
    from urllib.parse import urlencode
    try:
        r = requests.delete(
            f"{BRAIN_URL}/api/bubbles/{bubble_id}",
            params={"force": "true"} if force else {},
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
        return r.json()
    except Exception as e:
        return {"error": type(e).__name__, "detail": str(e)}


@mcp.tool()
def idea_move(idea_id: str, parent_id: str = "") -> Dict[str, Any]:
    """Move an idea to a different parent bubble.

    Args:
        idea_id: id of the idea to move
        parent_id: target bubble id. Empty string promotes idea to top-level
                   (it then becomes a bubble itself).
    """
    return _post(
        f"/api/ideas/{idea_id}/move",
        {"parent_id": parent_id},
    )


# ── Phase Q.5 — Ideas-Space mini-brain inspection ──────────────────────

@mcp.tool()
def idea_kg_stats() -> Dict[str, Any]:
    """Stats of the ideas-kg Qdrant collection (point count, sync ts)."""
    return _get("/api/ideas/kg_stats", timeout=10)


@mcp.tool()
def idea_kg_search(query: str, limit: int = 10, threshold: float = 0.3,
                   node_type: str = "") -> Dict[str, Any]:
    """Direct semantic Qdrant search against ideas-kg.

    Faster + cleaner than `idea_search` (which falls back to substring
    when the legacy endpoint is hit). Returns `{hits: [{id, score, payload}]}`.

    Args:
        query: free-text query (multilingual DE/EN)
        limit: max hits (default 10)
        threshold: min cosine score 0..1
        node_type: optional filter ("idea" or "bubble"); empty = both
    """
    payload: Dict[str, Any] = {
        "query": query, "limit": int(limit), "threshold": float(threshold),
    }
    if node_type:
        payload["node_type"] = node_type
    return _post("/api/ideas/kg_search", payload, timeout=30)


@mcp.tool()
def idea_state() -> Dict[str, Any]:
    """Mini-Brain state of the Ideas-Space: counts, active bubbles,
    stale ideas, last refresh timestamp."""
    return _get("/api/ideas/state", timeout=10)


@mcp.tool()
def idea_sync_full() -> Dict[str, Any]:
    """Trigger immediate full SQLite -> ideas-kg resync (blocking,
    can take seconds for large DBs)."""
    return _post("/api/ideas/sync_full", {}, timeout=300)


@mcp.tool()
def idea_consolidate_now() -> Dict[str, Any]:
    """Trigger one DBSCAN consolidation pass on ideas-kg. Generates
    theme suggestions for clusters of similar ideas. Suggestions are
    queued; user must accept/reject explicitly."""
    return _post("/api/ideas/consolidate", {}, timeout=120)


@mcp.tool()
def idea_consolidate_suggestions(status: str = "pending", limit: int = 20) -> Dict[str, Any]:
    """List consolidation suggestions.

    Args:
        status: pending | accepted | rejected (default pending)
        limit: max items
    """
    from urllib.parse import urlencode
    return _get(
        f"/api/ideas/consolidate/suggestions?{urlencode({'status': status, 'limit': limit})}"
    )


@mcp.tool()
def idea_consolidate_accept(suggestion_id: str) -> Dict[str, Any]:
    """Accept a consolidation suggestion: creates a new theme bubble
    and moves all member ideas into it."""
    return _post(
        f"/api/ideas/consolidate/suggestions/{suggestion_id}/accept", {}, timeout=15,
    )


@mcp.tool()
def idea_consolidate_reject(suggestion_id: str) -> Dict[str, Any]:
    """Reject a consolidation suggestion (won't be regenerated for the
    same cluster)."""
    return _post(
        f"/api/ideas/consolidate/suggestions/{suggestion_id}/reject", {}, timeout=10,
    )


# ── Phase R — Self-Discourse + Aggregator + Mirofish-KG-Sync ──────────

@mcp.tool()
def discourse_stats() -> Dict[str, Any]:
    """Stats of the 30s self-discourse engine (tweets, replies,
    failures, last sim_id, agents_loaded)."""
    return _get("/api/discourse/stats")


@mcp.tool()
def discourse_tick_now() -> Dict[str, Any]:
    """Force one immediate discourse round — picks a KG slice, asks
    1-3 agent phi3-clones to tweet about it via Mirofish."""
    return _post("/api/discourse/tick_now", {}, timeout=120)


@mcp.tool()
def discourse_aggregate_stats() -> Dict[str, Any]:
    """Stats of the 3-hour discourse aggregator (Topic/Finding/Decision)."""
    return _get("/api/discourse/aggregate_stats")


@mcp.tool()
def discourse_aggregate_now() -> Dict[str, Any]:
    """Force one aggregation pass: condense recent tweets into structured
    Topic/Finding/Decision nodes via Groq Llama-3.3-70b. Persists to
    aggregated-kg, Brain CTE, and ~/.rowboat/vibemind/discourse/*.md."""
    return _post("/api/discourse/aggregate_now", {}, timeout=300)


@mcp.tool()
def mirofish_sync_stats() -> Dict[str, Any]:
    """Stats of the Mirofish Neo4j -> Brain qdrant `mirofish-kg` mirror."""
    return _get("/api/mirofish/sync_stats")


@mcp.tool()
def mirofish_sync_now() -> Dict[str, Any]:
    """Trigger an immediate Mirofish KG sync (read-only mirror of Neo4j
    nodes + edges into Brain Qdrant `mirofish-kg`)."""
    return _post("/api/mirofish/sync_now", {}, timeout=120)


# ── Self-Awareness (S.4) ───────────────────────────────────────────────

@mcp.tool()
def self_awareness_stats() -> Dict[str, Any]:
    """Show the SelfAwarenessWatcher stats: how many architecture-substrate
    sources are tracked, how many were updated/added/removed since boot,
    last tick timestamp."""
    return _get("/api/self_awareness/manifest_stats")


@mcp.tool()
def self_awareness_reseed() -> Dict[str, Any]:
    """Force an immediate self-awareness reseed: hash all sources, re-upsert
    only the changed ones (preserves linked.* edges), delete nodes whose
    sources are gone, add nodes for new sources. Returns delta counts."""
    return _post("/api/self_awareness/reseed", {}, timeout=120)


@mcp.tool()
def discourse_meta_stats() -> Dict[str, Any]:
    """Show DiscourseMemoryConsolidator stats: how many topics scanned,
    how many meta_topics created/updated, last tick info."""
    return _get("/api/discourse/meta_stats")


@mcp.tool()
def discourse_meta_consolidate_now() -> Dict[str, Any]:
    """Force one cross-session meta-consolidation: cluster recent
    aggregated-kg topics, synthesise meta_topics. Useful for inspection
    or testing without waiting for the 6h tick."""
    return _post("/api/discourse/meta_consolidate_now", {}, timeout=300)


@mcp.tool()
def self_awareness_recall(
    query: str, days: int = 7, limit: int = 10
) -> Dict[str, Any]:
    """Recall meta_topics + topics from aggregated-kg matching the query,
    filtered to the last N days. Returns deduped, score-sorted results.

    Use this to ask 'what has Brain been thinking about regarding X
    over the last week?' — answers come from cross-session consolidated
    discourse, not just one aggregation window.
    """
    return _post(
        "/api/self_awareness/recall",
        {"query": query, "days": int(days), "limit": int(limit)},
        timeout=30,
    )


# ── Discourse pause/resume (R.3) ───────────────────────────────────────

@mcp.tool()
def discourse_pause() -> Dict[str, Any]:
    """Pause idle + response discourse loops without killing threads.
    Intent on-demand still works. Useful during Mirofish-Sim setup to
    stop interview-poll spam against an environment that isn't ready."""
    return _post("/api/discourse/pause", {}, timeout=10)


@mcp.tool()
def discourse_resume() -> Dict[str, Any]:
    """Resume idle + response discourse loops after a pause."""
    return _post("/api/discourse/resume", {}, timeout=10)


# ── Phase R+ — Three-Mode Discourse (intent / response) ────────────────

@mcp.tool()
def discourse_intent(message: str, auto_dispatch: bool = True) -> Dict[str, Any]:
    """Trigger an Intent-Mode discourse: all 26 phi3-clones reflect on
    a user task in parallel, then a Groq aggregator decides who should
    take it. With auto_dispatch=True (default), high-confidence
    decisions also fire a real OpenFang Sonnet call to the chosen agent.

    Args:
        message: the user task / intent
        auto_dispatch: if True, run end-to-end (decision + dispatch).
                       Set False to only see the discourse decision.

    Returns:
        {decision, tweet_count, high_confidence, dispatched}
    """
    return _post(
        "/api/discourse/intent",
        {"message": message, "auto_dispatch": auto_dispatch},
        timeout=300,
    )


@mcp.tool()
def discourse_response_tick_now() -> Dict[str, Any]:
    """Force one Mode-3 (response-assessment) discourse tick. Pulls the
    oldest queued Brain-response and asks 3-5 random agents what they
    think about it."""
    return _post("/api/discourse/response_tick_now", {}, timeout=120)


@mcp.tool()
def discourse_intent_decisions(limit: int = 10) -> Dict[str, Any]:
    """Last N intent-mode decisions (in-memory ring buffer of size 50).
    Each decision: {decision, tweet_count, high_confidence, intent, ts}."""
    from urllib.parse import urlencode
    return _get(f"/api/discourse/intent_decisions?{urlencode({'limit': int(limit)})}")


@mcp.tool()
def idea_reward(idea_id: str, delta: float, reason: str = "") -> Dict[str, Any]:
    """Adjust the score of an idea by `delta` (positive or negative).

    Args:
        idea_id: target idea
        delta: e.g. +0.7 for explicit positive feedback, -0.5 for negative
        reason: free-text label, stored in stats
    """
    return _post(
        f"/api/ideas/{idea_id}/reward",
        {"delta": float(delta), "reason": reason},
        timeout=10,
    )


@mcp.tool()
def snapshots(limit: int = 20) -> Dict[str, Any]:
    """List recent Brain self-state snapshots (newest first).

    Each snapshot is a frozen view of bridges + modulation + state at a
    point in time. Useful for 'how was Brain feeling at T'.

    Args:
        limit: max snapshots (default 20, capped at 200)
    """
    limit = max(1, min(200, int(limit)))
    return _get(f"/api/kg/snapshots?limit={limit}")


@mcp.tool()
def minibook_dispatch(
    agents: List[str],
    intent: str,
    project_id: str = "",
    task_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dispatch a task to one or more Minibook agents.

    The Brain pushes a task post to Minibook. Targeted agents (e.g.
    'vibemind_ideas', 'vibemind_coding') get notified via @mention and
    reply via comments. Use minibook_dispatch_comments(post_id) to poll
    their replies.

    Args:
        agents: list of agent names to mention (without '@')
        intent: short description of what should be done
        project_id: Minibook project UUID. Empty = default 'VibeMind
            Collaboration' (46daa2f8-...).
        task_spec: optional structured payload appended as JSON

    Returns: {post_id, project_id, agents, online, timestamp}
    """
    payload: Dict[str, Any] = {"agents": agents, "intent": intent}
    if project_id:
        payload["project_id"] = project_id
    if task_spec is not None:
        payload["task_spec"] = task_spec
    return _post("/api/brain/dispatch", payload)


@mcp.tool()
def minibook_dispatch_comments(post_id: str) -> Dict[str, Any]:
    """Get agent replies on a previously dispatched task.

    Args:
        post_id: UUID returned from minibook_dispatch
    """
    from urllib.parse import quote
    return _get(f"/api/brain/dispatch/{quote(post_id)}/comments")


# ──────────────────────────────────────────────────────────────────────
# Multi-hop Plan Executor (Phase 6)
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def multihop_plan(intent: str) -> Dict[str, Any]:
    """Phase 6 — produce a multi-hop plan for a complex intent WITHOUT
    executing it. Useful for inspecting how Brain would decompose the
    request before running anything.

    Args:
        intent: user intent text (≥4 words; connectives like 'und dann',
                multiple imperative verbs, or an explicit @plan trigger)
    Returns: {ok, plan: {plan_id, intent, rationale, hops:[...]}}
    """
    return _post("/api/multihop/plan", {"intent": intent}, timeout=60)


@mcp.tool()
def multihop_execute(intent: str) -> Dict[str, Any]:
    """Phase 6 — full multi-hop pipeline: plan → execute (with state-
    passing through {{state.X}} templates) → final synthesis.

    Each hop walks the existing capability_router → capability_targets →
    capability_validator pipeline. Falls back to single-hop if planner
    or executor fails.

    Returns: {ok, executed:{step_id->HopResult}, state, elapsed_s,
              replans, final_text}
    """
    return _post("/api/multihop/execute", {"intent": intent}, timeout=300)


@mcp.tool()
def multihop_stats() -> Dict[str, Any]:
    """Phase 6 — combined counters from advisor, planner, executor,
    synthesizer. Useful for telemetry + tuning."""
    return _get("/api/multihop/stats")


@mcp.tool()
def multihop_history(limit: int = 20) -> Dict[str, Any]:
    """Phase 6 — last N executed plans (compact: id, intent, hop_count,
    ok, elapsed). Use multihop_plan_detail for the full snapshot."""
    return _get(f"/api/multihop/history?limit={int(limit)}")


@mcp.tool()
def multihop_plan_detail(plan_id: str) -> Dict[str, Any]:
    """Phase 6 — full snapshot of an executed plan: every hop's
    HopResult, threaded state, KG-hits per hop, validator verdicts."""
    return _get(f"/api/multihop/plan/{plan_id}")


# ──────────────────────────────────────────────────────────────────────
# Phase 10 — Self-Reflective Decision Loop
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def decisions_recall(query: str, k: int = 5) -> Dict[str, Any]:
    """Phase 10.1 — Find past decisions on similar intents. Returns hits
    with capability_chain, outcome, success_rate, age."""
    return _get(f"/api/decisions/recall?q={query}&k={k}")


@mcp.tool()
def decisions_reward(plan_id: str, reward: float, comment: str = "") -> Dict[str, Any]:
    """Phase 10.1 — Attach an explicit reward in [-1, 1] to a past decision.
    Propagates to the self-model so future similar decisions are biased
    toward (or away from) the capabilities used."""
    return _post("/api/decisions/reward", {
        "plan_id": plan_id, "reward": reward, "comment": comment,
    })


@mcp.tool()
def self_prior(query: str, k: int = 8) -> Dict[str, Any]:
    """Phase 10.2 — Get Brain's self-model prior for an intent: which
    capabilities does Brain trust for this kind of request, with what
    confidence."""
    return _get(f"/api/self/prior?q={query}&k={k}")


@mcp.tool()
def self_snapshot(limit: int = 200) -> Dict[str, Any]:
    """Phase 10.2 — Full self-model dump. Lists every (intent_pattern,
    capability) pair Brain has learned, sorted by n_observations."""
    return _get(f"/api/self/snapshot?limit={limit}")


@mcp.tool()
def critic_preview(intent: str) -> Dict[str, Any]:
    """Phase 10.3 — Generate a plan for the intent and run the critic
    on it WITHOUT executing. Useful for "would this work?" questions."""
    return _post("/api/critic/preview", {"intent": intent})


# ──────────────────────────────────────────────────────────────────────
# Autopilot Control — full orchestration handles for evaluation
# These give Claude Code the same control surface the dashboard has,
# so we can drive Brain end-to-end + watch what happens, before
# building an autonomous goal-pursuit loop.
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def capabilities_list() -> Dict[str, Any]:
    """List every capability Brain knows about, grouped by execution
    target (bubble/idea/openfang-agent/brain-internal/n8n/etc).
    Use this BEFORE planning to know what Brain can actually do."""
    return _get("/api/capabilities/list")


@mcp.tool()
def capabilities_by_name(name: str) -> Dict[str, Any]:
    """Inspect a single capability — its bridges, validator, target,
    arg schema, forbid_tools list."""
    return _get(f"/api/capabilities/by_name/{name}")


@mcp.tool()
def capabilities_test(capability: str, arg: str = "") -> Dict[str, Any]:
    """Dry-run a capability without committing side-effects (where the
    target supports it). Useful for evaluating reach before a plan."""
    return _post("/api/capabilities/test", {"capability": capability, "arg": arg})


@mcp.tool()
def plan_active() -> Dict[str, Any]:
    """Returns whether a plan is currently executing (mutex held), with
    the plan_id and how long it's been active. Use this before triggering
    a new plan to avoid the busy-envelope bounce."""
    return _get("/api/multihop/busy")


@mcp.tool()
def plan_history(limit: int = 20) -> Dict[str, Any]:
    """Recent executed plans (rolling buffer, most recent first). Each
    item has plan_id, intent, ok, hop_count, elapsed_s, replans."""
    return _get(f"/api/multihop/history?limit={limit}")


@mcp.tool()
def plan_inspect(plan_id: str) -> Dict[str, Any]:
    """Full snapshot of one executed plan: every hop's HopResult with
    tool_calls, kg_hits, threaded state, validator verdicts, plus the
    Phase-10 decision_context (recall+self_prior+critic) attached.
    The single richest tool for evaluating what Brain actually did."""
    return _get(f"/api/multihop/plan/{plan_id}")


@mcp.tool()
def plan_reward(plan_id: str, reward: float, comment: str = "") -> Dict[str, Any]:
    """Apply explicit reward in [-1, 1] to a past plan. Propagates
    through Phase 10 to update self-model confidence per capability
    used in that plan. This is the feedback channel that lets Brain
    learn 'I'm good at X / weak at Y' over time."""
    return _post(f"/api/multihop/plan/{plan_id}/reward", {
        "reward": reward, "comment": comment,
    })


@mcp.tool()
def clusters_activations() -> Dict[str, Any]:
    """Phase 8 cluster engine — current cluster activation snapshot.
    Each cluster has dominant_topic, member_count, activation_score,
    co_activation_pairs. High-activation clusters trigger SelfSteerer
    autonomous dispatch."""
    return _get("/api/clusters/activations")


@mcp.tool()
def clusters_bump(cluster_id: int, delta: float = 1.0) -> Dict[str, Any]:
    """Manually boost a cluster's activation. Useful for testing the
    SelfSteerer dispatch path: bump > threshold for ≥2 ticks → Brain
    auto-dispatches a capability mapped to that cluster's topic."""
    return _post("/api/clusters/bump", {
        "cluster_id": cluster_id, "delta": delta,
    })


@mcp.tool()
def orchestrate(intent: str, want_critic: bool = True) -> Dict[str, Any]:
    """Full orchestration in one call:
       1. Critic-preview the intent → returns risks + recommend
       2. If recommend != 'replan' (or want_critic=False), execute
       3. Returns combined {critic_verdict, execution_result}

    This is the 'one-shot orchestrator' tool — the closest thing to a
    poor-man's autopilot. Build the autonomous loop ON TOP of this."""
    out: Dict[str, Any] = {}
    if want_critic:
        try:
            preview = _post("/api/critic/preview", {"intent": intent})
            out["critic_verdict"] = preview
            verdict = (preview or {}).get("verdict") or {}
            if verdict.get("recommend") == "replan":
                out["aborted"] = True
                out["reason"] = "critic recommended replan; aborting before execution"
                return out
        except Exception as e:
            out["critic_error"] = str(e)
    # Execute
    out["execution_result"] = _post("/api/multihop/execute", {"intent": intent})
    return out


# ──────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Log to stderr only — stdout is reserved for MCP JSON-RPC frames.
    print(f"[brain-core-mcp] proxy starting, target={BRAIN_URL}", file=sys.stderr)
    mcp.run()
