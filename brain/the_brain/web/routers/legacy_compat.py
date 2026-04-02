"""
Legacy Compatibility Router — maps old Flask endpoint paths to new unified paths.

The original 6 Flask servers used flat paths like ``/api/state``, ``/api/entries``,
``/api/brain/chat``.  The unified Nervous System uses prefixed paths like
``/api/knowledge/state``, ``/api/cortex/chat``.

This router adds 307 redirects so existing HTML dashboard templates continue
to work without modification.  307 preserves HTTP method + body for POST routes.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["legacy-compat"])

# ===================================================================
# Moltbook Dashboard (old port 5006) → /api/knowledge/*
# ===================================================================

# The moltbook_dashboard.html calls these flat paths:
@router.get("/api/state")
async def legacy_state():
    return RedirectResponse("/api/knowledge/state", status_code=307)

@router.get("/api/entries")
async def legacy_entries():
    return RedirectResponse("/api/knowledge/entries", status_code=307)

@router.get("/api/debug")
async def legacy_debug():
    return RedirectResponse("/api/knowledge/debug", status_code=307)

@router.post("/api/search")
async def legacy_search():
    return RedirectResponse("/api/knowledge/search", status_code=307)

@router.post("/api/forum/discuss")
async def legacy_forum_discuss():
    return RedirectResponse("/api/knowledge/forum/discuss", status_code=307)

@router.get("/api/forum/history")
async def legacy_forum_history():
    return RedirectResponse("/api/knowledge/forum/history", status_code=307)

@router.get("/api/graph")
async def legacy_graph():
    return RedirectResponse("/api/knowledge/graph", status_code=307)

# Some templates also prefix with /api/moltbook/*
@router.get("/api/moltbook/state")
async def legacy_moltbook_state():
    return RedirectResponse("/api/knowledge/state", status_code=307)

@router.get("/api/moltbook/entries")
async def legacy_moltbook_entries():
    return RedirectResponse("/api/knowledge/entries", status_code=307)

@router.get("/api/moltbook/debug")
async def legacy_moltbook_debug():
    return RedirectResponse("/api/knowledge/debug", status_code=307)


# ===================================================================
# Brain Chat (old port 5006) → /api/cortex/*
# ===================================================================

@router.get("/api/brain/thoughts")
async def legacy_brain_thoughts():
    return RedirectResponse("/api/cortex/thoughts", status_code=307)

@router.post("/api/brain/chat")
async def legacy_brain_chat():
    return RedirectResponse("/api/cortex/chat", status_code=307)

@router.get("/api/brain/state")
async def legacy_brain_state():
    return RedirectResponse("/api/cortex/state", status_code=307)


# ===================================================================
# Swarm Dashboard (old port 5002) → /api/swarm/*
# ===================================================================

@router.get("/api/stats")
async def legacy_swarm_stats():
    return RedirectResponse("/api/swarm/stats", status_code=307)

@router.post("/api/execute")
async def legacy_swarm_execute():
    return RedirectResponse("/api/swarm/execute", status_code=307)

@router.get("/api/logs")
async def legacy_swarm_logs():
    return RedirectResponse("/api/swarm/logs", status_code=307)


# ===================================================================
# Oscillator Dashboard (old port 5005)
# ===================================================================

@router.get("/api/token/stats")
async def legacy_token_stats():
    return RedirectResponse("/api/oscillator/stats", status_code=307)


# ===================================================================
# Knowledge feed/evaluate/curate (old flat paths)
# ===================================================================

@router.post("/api/feed")
async def legacy_feed():
    return RedirectResponse("/api/knowledge/feed", status_code=307)

@router.post("/api/evaluate")
async def legacy_evaluate():
    return RedirectResponse("/api/knowledge/evaluate", status_code=307)

@router.post("/api/curate")
async def legacy_curate():
    return RedirectResponse("/api/knowledge/curate", status_code=307)

@router.post("/api/feedback")
async def legacy_feedback():
    return RedirectResponse("/api/knowledge/feedback", status_code=307)

@router.post("/api/research")
async def legacy_research():
    return RedirectResponse("/api/knowledge/research", status_code=307)

@router.post("/api/research/cycle")
async def legacy_research_cycle():
    return RedirectResponse("/api/knowledge/research", status_code=307)
