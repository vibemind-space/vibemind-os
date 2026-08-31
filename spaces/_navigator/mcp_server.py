"""Phase 11.B — Space-Navigator MCP Server.

Smart navigation for the VibeMind 14-space multiverse.

Layers:
  1. Keyword/alias  (instant, deterministic)
  2. Qwen3 embedding cosine search
  3. LLM tiebreaker (only when top-2 within 0.05)

Tools:
  space_list, space_current, space_goto, space_next, space_back, space_home,
  space_resolve, space_navigate_intent, space_suggest, space_recent, space_info,
  space_index_status

Run standalone:  python vibemind-os/spaces/_navigator/mcp_server.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure absolute imports work whether launched as module or script
_PKG_DIR = Path(__file__).resolve().parent
_ROOT = _PKG_DIR.parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import types as _types
if "spaces" not in sys.modules:
    sys.modules["spaces"] = _types.ModuleType("spaces")
    sys.modules["spaces"].__path__ = [str(_ROOT / "spaces")]
if "spaces._navigator" not in sys.modules:
    sys.modules["spaces._navigator"] = _types.ModuleType("spaces._navigator")
    sys.modules["spaces._navigator"].__path__ = [str(_PKG_DIR)]

from mcp.server.fastmcp import FastMCP

from spaces._navigator import electron_bridge, resolver, state
from spaces._navigator.registry import SPACES, get_meta, resolve_alias


mcp = FastMCP(
    "Space-Navigator",
    instructions=(
        "Navigate the VibeMind multiverse — 14 spaces (autogen, brain, coding, "
        "desktop, flowzen, ideas, minibook, mirofish, n8n, research, rowboat, "
        "schedule, shuttles, video). Use space_resolve / space_navigate_intent "
        "to map natural language to a space; space_goto for direct jumps. "
        "Every navigation broadcasts to the Electron UI. State persists across "
        "restarts in state.json."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _format_space(sid: str) -> Dict[str, Any]:
    m = get_meta(sid)
    if not m:
        return {"id": sid, "label": sid, "unknown": True}
    return {
        "id": sid,
        "label": m["label"],
        "event_prefix": m["event_prefix"],
        "stream": m["stream"],
        "aliases": m["aliases"],
        "use_when": m["use_when"],
        "capabilities": m["capabilities"],
    }


def _err(message: str, **extra: Any) -> Dict[str, Any]:
    return {"ok": False, "message": message, **extra}


# ──────────────────────────────────────────────────────────────────────
# Direct (deterministic) navigation
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def space_list() -> Dict[str, Any]:
    """List all 14 spaces in the multiverse with their metadata."""
    cur = state.current()
    return {
        "ok": True,
        "current": cur["space"],
        "count": len(SPACES),
        "spaces": [_format_space(sid) for sid in SPACES],
    }


@mcp.tool()
def space_current() -> Dict[str, Any]:
    """Return the currently active space, when entered, and recent history."""
    cur = state.current()
    sid = cur["space"]
    meta = get_meta(sid) or {}
    return {
        "ok": True,
        "space": sid,
        "label": meta.get("label", sid),
        "since_ts": cur["since"],
        "history": cur["history"],
    }


@mcp.tool()
def space_goto(space: str) -> Dict[str, Any]:
    """Jump directly to a named space (deterministic — no LLM/embedding).

    Accepts canonical id (e.g. 'n8n'), label ('n8n'), or any alias.
    """
    target = resolve_alias(space)
    if not target:
        return _err(
            f"unknown space '{space}' — use space_resolve for natural-language queries",
            available=list(SPACES.keys()),
        )
    transition = state.goto(target)
    bcast = electron_bridge.navigate(target, reason=f"space_goto({space})")
    return {
        "ok": True,
        "space": target,
        "previous": transition["previous"],
        "broadcast": bcast,
        "info": _format_space(target),
    }


@mcp.tool()
def space_next(direction: str = "next") -> Dict[str, Any]:
    """Cycle to the next or previous space (alphabetical order)."""
    direction = (direction or "next").strip().lower()
    if direction not in ("next", "prev", "previous"):
        return _err("direction must be 'next' or 'prev'")
    ids: List[str] = list(SPACES.keys())
    cur = state.current()["space"]
    try:
        idx = ids.index(cur)
    except ValueError:
        idx = 0
    step = 1 if direction == "next" else -1
    target = ids[(idx + step) % len(ids)]
    state.goto(target)
    bcast = electron_bridge.navigate(target, reason=f"space_next({direction})")
    return {"ok": True, "space": target, "previous": cur, "broadcast": bcast}


@mcp.tool()
def space_back() -> Dict[str, Any]:
    """Return to the previously active space (history pop)."""
    target = state.back()
    if not target:
        return _err("history is empty")
    cur_before = state.current()["space"]
    state.goto(target)
    bcast = electron_bridge.navigate(target, reason="space_back")
    return {"ok": True, "space": target, "previous": cur_before, "broadcast": bcast}


@mcp.tool()
def space_home() -> Dict[str, Any]:
    """Reset navigation to the default space (ideas — multiverse hub)."""
    target = "ideas"
    cur = state.current()["space"]
    state.goto(target)
    bcast = electron_bridge.navigate(target, reason="space_home")
    return {"ok": True, "space": target, "previous": cur, "broadcast": bcast}


# ──────────────────────────────────────────────────────────────────────
# Smart resolution (3-layer)
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def space_resolve(query: str, top_k: int = 3) -> Dict[str, Any]:
    """Resolve a natural-language query to the best space — without navigating.

    Use this when the user describes intent ('I want to build a workflow')
    rather than naming a space. Returns ranked candidates + which layer
    decided (alias / embed / llm / fuzzy).
    """
    return resolver.resolve(query, top_k=top_k)


@mcp.tool()
def space_navigate_intent(query: str) -> Dict[str, Any]:
    """Smart-resolve + jump in one call. The voice-friendly path.

    Example: 'where can I research something?' → research, broadcasts to UI.
    """
    res = resolver.resolve(query)
    if not res.get("ok") or not res.get("space"):
        return _err(
            f"could not resolve '{query}'",
            details=res,
        )
    target = res["space"]
    cur = state.current()["space"]
    state.goto(target)
    bcast = electron_bridge.navigate(
        target, reason=f"space_navigate_intent: {res.get('layer')}"
    )
    return {
        "ok": True,
        "space": target,
        "previous": cur,
        "confidence": res.get("confidence"),
        "layer": res.get("layer"),
        "reasoning": res.get("reasoning"),
        "candidates": res.get("candidates"),
        "broadcast": bcast,
    }


@mcp.tool()
def space_suggest(query: str, top_k: int = 3) -> Dict[str, Any]:
    """Return top-k candidate spaces for a query, with reasoning per candidate.

    Non-mutative — does NOT navigate. Use this to disambiguate before goto.
    """
    return resolver.suggest(query, top_k=top_k)


@mcp.tool()
def space_recent(limit: int = 5) -> Dict[str, Any]:
    """Spaces ranked by visit count — 'where do you spend your time?'"""
    return {"ok": True, "recent": state.recent(limit=limit)}


@mcp.tool()
def space_info(space: str = "") -> Dict[str, Any]:
    """Detailed metadata for a space. Empty arg → info on current space."""
    sid = resolve_alias(space) if space else state.current()["space"]
    if not sid:
        return _err(f"unknown space '{space}'")
    return {"ok": True, **_format_space(sid)}


@mcp.tool()
def space_index_status() -> Dict[str, Any]:
    """Diagnostics: is the embedding index ready? LLM available? cache size?"""
    return {"ok": True, **resolver.index_status()}


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if os.environ.get("NAVIGATOR_PREWARM_EMBED", "0") == "1":
        try:
            resolver._ensure_embed_index()  # noqa: SLF001 — intentional warm-up
        except Exception:
            pass
    mcp.run()
