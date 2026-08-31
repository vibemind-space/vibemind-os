"""
Knowledge Router -- FastAPI endpoints for the Moltbook knowledge system.

All state lives on ``request.app.state``:
  - ``moltbook_store``  (MoltbookStore or None)
  - ``moltbook_graph``  (MoltbookGraph or None)
  - ``moltbook_agents`` (dict of agent instances, empty ``{}`` in testing)

Every route gracefully handles absent / None dependencies.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _templates(request: Request):
    """Shortcut to the Jinja2Templates instance stored on app state."""
    return request.app.state.templates


# ===================================================================
# Knowledge Store Routes
# ===================================================================

@router.get("/api/knowledge/state")
async def knowledge_state(request: Request) -> JSONResponse:
    """Full system overview — stats from store + agents."""
    store = request.app.state.moltbook_store
    agents = request.app.state.moltbook_agents

    if store is None:
        return JSONResponse({
            "store": {"total_entries": 0, "sources": {}, "types": {},
                      "avg_confidence": 0.0, "avg_relevance": 0.0},
            "feeder": {},
            "evaluation": {},
            "curation": {},
            "research": {},
            "feedback": {},
            "forum": {},
            "message": "knowledge store not initialized",
            "timestamp": time.time(),
        })

    try:
        all_entries = store.get_active_entries(top_k=500)
        sources: dict[str, int] = {}
        types: dict[str, int] = {}
        total_conf, total_rel = 0.0, 0.0
        for e in all_entries:
            sources[e.source_agent] = sources.get(e.source_agent, 0) + 1
            types[e.entry_type] = types.get(e.entry_type, 0) + 1
            total_conf += e.confidence
            total_rel += e.relevance_score
        n = len(all_entries) or 1

        feeder = agents.get("feeder")
        evaluator = agents.get("evaluator")
        curator = agents.get("curator")
        researcher = agents.get("researcher")
        feedback = agents.get("feedback")
        forum_agent = agents.get("forum")

        return JSONResponse({
            "store": {
                "total_entries": len(all_entries),
                "sources": sources,
                "types": types,
                "avg_confidence": round(total_conf / n, 3),
                "avg_relevance": round(total_rel / n, 3),
            },
            "feeder": feeder.get_stats() if feeder else {},
            "evaluation": evaluator.get_stats() if evaluator else {},
            "curation": curator.get_stats() if curator else {},
            "research": researcher.get_stats() if researcher else {},
            "feedback": feedback.get_stats() if feedback else {},
            "forum": forum_agent.get_stats() if forum_agent else {},
            "timestamp": time.time(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/knowledge/entries")
async def knowledge_entries(request: Request) -> JSONResponse:
    """Recent entries."""
    store = request.app.state.moltbook_store
    if store is None:
        return JSONResponse({
            "entries": [],
            "count": 0,
            "message": "knowledge store not initialized",
        })

    try:
        top_k = int(request.query_params.get("top_k", "30"))
        top_k = min(top_k, 200)
        raw = store.get_active_entries(top_k=top_k)
        entries = []
        for e in raw:
            entries.append({
                "id": e.id,
                "content": e.content[:300],
                "source": e.source_agent,
                "type": e.entry_type,
                "confidence": round(e.confidence, 3),
                "relevance": round(e.relevance_score, 3),
                "tags": list(e.tags),
                "accessed": e.accessed_count,
                "age_hours": round((time.time() - e.created_at) / 3600, 1),
            })
        return JSONResponse({"entries": entries, "count": len(entries)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/knowledge/search")
async def knowledge_search(request: Request) -> JSONResponse:
    """Semantic search."""
    store = request.app.state.moltbook_store
    if store is None:
        return JSONResponse(
            {"error": "knowledge store not initialized"}, status_code=503
        )

    body = await request.json()
    query = body.get("query", "")
    if not query:
        return JSONResponse({"error": "No query"}, status_code=400)

    try:
        top_k = max(1, min(int(body.get("top_k", 10)), 200))
    except (TypeError, ValueError):
        top_k = 10

    try:
        raw = store.query_semantic(query, top_k=top_k, threshold=0.05)
        results = [{
            "id": e.id,
            "content": e.content[:300],
            "source": e.source_agent,
            "confidence": round(e.confidence, 3),
            "relevance": round(e.relevance_score, 3),
            "tags": list(e.tags),
        } for e in raw]
        return JSONResponse({
            "results": results,
            "count": len(results),
            "query": query,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/knowledge/feed")
async def knowledge_feed(request: Request) -> JSONResponse:
    """Feed new knowledge via Feeder agent."""
    agents = request.app.state.moltbook_agents
    feeder = agents.get("feeder")
    if feeder is None:
        return JSONResponse(
            {"error": "feeder not initialized"}, status_code=503
        )

    body = await request.json()
    content = body.get("content", "")
    if not content:
        return JSONResponse({"error": "No content"}, status_code=400)

    tags = body.get("tags", [])
    try:
        confidence = max(0.0, min(1.0, float(body.get("confidence", 0.6))))
    except (TypeError, ValueError):
        confidence = 0.6

    try:
        entry = feeder.post(content=content, tags=tags, confidence=confidence)
        return JSONResponse({
            "success": True,
            "entry_id": entry.id,
            "content": entry.content[:200],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/knowledge/evaluate")
async def knowledge_evaluate(request: Request) -> JSONResponse:
    """Evaluate entry by ID."""
    agents = request.app.state.moltbook_agents
    evaluator = agents.get("evaluator")
    if evaluator is None:
        return JSONResponse(
            {"error": "evaluator not initialized"}, status_code=503
        )

    store = request.app.state.moltbook_store
    body = await request.json()
    entry_id = body.get("entry_id", "")
    if not entry_id:
        return JSONResponse({"error": "No entry_id"}, status_code=400)

    try:
        entry = store.get_entry(entry_id) if store else None
        if not entry:
            return JSONResponse({"error": "Entry not found"}, status_code=404)

        result = evaluator.evaluate(entry)
        return JSONResponse({
            "entry_id": entry_id,
            "score": round(result.score, 3),
            "relevance": round(result.relevance, 3),
            "novelty": round(result.novelty, 3),
            "consistency": round(result.consistency, 3),
            "action": result.action,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/knowledge/curate")
async def knowledge_curate(request: Request) -> JSONResponse:
    """Run curation cycle."""
    agents = request.app.state.moltbook_agents
    curator = agents.get("curator")
    if curator is None:
        return JSONResponse(
            {"error": "curator not initialized"}, status_code=503
        )

    try:
        actions = curator.curate()
        return JSONResponse({
            "actions": [{
                "action_type": a.action_type,
                "entry_ids": a.entry_ids,
                "reason": a.reason,
            } for a in actions],
            "count": len(actions),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/knowledge/feedback")
async def knowledge_feedback(request: Request) -> JSONResponse:
    """Record user feedback."""
    agents = request.app.state.moltbook_agents
    feedback = agents.get("feedback")
    if feedback is None:
        return JSONResponse(
            {"error": "feedback agent not initialized"}, status_code=503
        )

    body = await request.json()
    try:
        sentiment = max(-1.0, min(1.0, float(body.get("sentiment", 0.0))))
    except (TypeError, ValueError):
        return JSONResponse({"error": "sentiment must be a number"}, status_code=400)
    entry_ids = body.get("entry_ids", [])
    if not isinstance(entry_ids, list):
        entry_ids = []
    correction = body.get("correction", None)

    try:
        feedback.record_feedback(
            sentiment=sentiment,
            contributing_entry_ids=entry_ids,
            correction=correction,
        )
        return JSONResponse({
            "success": True,
            "stats": feedback.get_stats(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/knowledge/research")
async def knowledge_research(request: Request) -> JSONResponse:
    """Run one research agent cycle."""
    agents = request.app.state.moltbook_agents
    researcher = agents.get("researcher")
    if researcher is None:
        return JSONResponse(
            {"error": "researcher not initialized"}, status_code=503
        )

    try:
        gaps = researcher.check_for_gaps()
        results = []
        for gap in gaps[:3]:
            r = researcher.process_gap(gap)
            if r:
                results.append({
                    "topic": gap.get("topic", "unknown"),
                    "entry_id": r.id,
                    "content": r.content[:200],
                })
        return JSONResponse({
            "gaps_found": len(gaps),
            "researched": results,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/knowledge/debug")
async def knowledge_debug(request: Request) -> JSONResponse:
    """Debug stream output."""
    # No debug_stream on app.state in testing — return fallback
    debug_stream = getattr(request.app.state, "debug_stream", None)
    if debug_stream is None:
        return JSONResponse({
            "enabled": False,
            "entries": [],
            "formatted": "",
        })

    try:
        n = max(1, min(int(request.query_params.get("n", "30")), 500))
    except (TypeError, ValueError):
        n = 30
    try:
        return JSONResponse({
            "enabled": debug_stream.enabled,
            "entries": debug_stream.get_recent(n),
            "formatted": debug_stream.get_formatted(n),
            "stats": debug_stream.get_stats(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===================================================================
# Forum Routes
# ===================================================================

@router.post("/api/knowledge/forum/discuss")
async def knowledge_forum_discuss(request: Request) -> JSONResponse:
    """Run multi-agent discussion about a topic."""
    agents = request.app.state.moltbook_agents
    forum = agents.get("forum")
    if forum is None:
        return JSONResponse(
            {"error": "forum not initialized"}, status_code=503
        )

    body = await request.json()
    query = body.get("query", body.get("topic", ""))
    if not query:
        return JSONResponse({"error": "No query/topic"}, status_code=400)

    try:
        top_k = max(1, min(int(body.get("top_k", 5)), 50))
    except (TypeError, ValueError):
        top_k = 5

    try:
        thread = forum.discuss(query, top_k=top_k)
        return JSONResponse(thread.to_dict())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/knowledge/forum/history")
async def knowledge_forum_history(request: Request) -> JSONResponse:
    """Recent discussion history."""
    agents = request.app.state.moltbook_agents
    forum = agents.get("forum")
    if forum is None:
        return JSONResponse({
            "discussions": [],
            "total": 0,
            "message": "forum not initialized",
        })

    try:
        n = max(1, min(int(request.query_params.get("n", "10")), 200))
    except (TypeError, ValueError):
        n = 10
    try:
        return JSONResponse({
            "discussions": forum.get_recent_discussions(n),
            "total": getattr(forum, "_total_discussions", 0),
        })
    except Exception as e:
        return JSONResponse({"discussions": [], "total": 0, "error": str(e)})


# ===================================================================
# Graph Route
# ===================================================================

@router.get("/api/knowledge/graph")
async def knowledge_graph(request: Request) -> JSONResponse:
    """Knowledge graph for visualization (nodes + edges)."""
    store = request.app.state.moltbook_store
    graph = request.app.state.moltbook_graph

    if store is None:
        return JSONResponse({"nodes": [], "edges": []})

    try:
        nodes = []
        edges = []
        edge_set: set[tuple[str, str]] = set()
        all_entries = store.get_active_entries(top_k=100)

        for e in all_entries:
            nodes.append({
                "id": e.id,
                "label": e.content[:40],
                "source": e.source_agent,
                "confidence": round(e.confidence, 3),
                "tags": list(e.tags),
            })

        # Explicit graph edges (snapshot to avoid concurrent mutation)
        if graph:
            raw_edges = dict(getattr(graph, "_edges", {}))
            for src_id, neighbors in raw_edges.items():
                for dst_id, edge_data in dict(neighbors).items():
                    key = (src_id, dst_id)
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append({
                            "source": src_id,
                            "target": dst_id,
                            "type": edge_data.get("type", "related"),
                            "weight": round(edge_data.get("weight", 0.5), 3),
                        })

        # Inferred edges: entries sharing tags
        tag_map: dict[str, list[str]] = {}
        for e in all_entries:
            for tag in e.tags:
                tag_map.setdefault(tag, []).append(e.id)
        for tag, ids in tag_map.items():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    key = tuple(sorted([ids[i], ids[j]]))
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append({
                            "source": ids[i],
                            "target": ids[j],
                            "type": f"shared:{tag}",
                            "weight": 0.6,
                        })

        return JSONResponse({"nodes": nodes, "edges": edges})
    except Exception as e:
        return JSONResponse({"nodes": [], "edges": [], "error": str(e)})


# ===================================================================
# Socialization Metrics (Moltbook Socialization paper)
# ===================================================================

@router.get("/api/knowledge/socialization")
async def knowledge_socialization(request: Request) -> JSONResponse:
    """Current socialization metrics — is the brain actually learning?"""
    metrics = getattr(request.app.state, 'socialization_metrics', None)
    if metrics is None:
        return JSONResponse({
            "metrics": {},
            "message": "socialization metrics not initialized",
            "timestamp": time.time(),
        })
    try:
        # Include eviction stats from consolidator if available
        consolidator = getattr(request.app.state, 'memory_consolidator', None)
        consolidation_stats = consolidator.get_stats() if consolidator else {}

        # Radial attention stats (if available)
        radial_net = getattr(request.app.state, 'radial_network', None)
        radial_stats = {}
        if radial_net is not None:
            radial_stats = radial_net.get_parameter_count()
            exp_buf = getattr(request.app.state, 'experience_buffer', None)
            if exp_buf:
                radial_stats['experience_buffer'] = exp_buf.get_stats()
            trainer = getattr(request.app.state, 'radial_trainer', None)
            if trainer:
                radial_stats['training'] = trainer.get_stats()

        return JSONResponse({
            "metrics": metrics.get_stats(),
            "total_evicted": consolidation_stats.get('total_evicted', 0),
            "tombstone_count": consolidation_stats.get('tombstone_count', 0),
            "radial": radial_stats,
            "timestamp": time.time(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/knowledge/socialization/timeseries")
async def knowledge_socialization_timeseries(request: Request) -> JSONResponse:
    """Time-series data for socialization metrics charts."""
    metrics = getattr(request.app.state, 'socialization_metrics', None)
    if metrics is None:
        return JSONResponse({
            "series": {},
            "message": "socialization metrics not initialized",
        })
    metric_name = request.query_params.get("metric", None)
    try:
        return JSONResponse({
            "series": metrics.get_time_series(metric=metric_name),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===================================================================
# UI page
# ===================================================================

@router.get("/ui/moltbook", response_class=HTMLResponse)
async def moltbook_ui(request: Request) -> HTMLResponse:
    """Render moltbook dashboard."""
    return _templates(request).TemplateResponse(
        request, "moltbook_dashboard.html"
    )
