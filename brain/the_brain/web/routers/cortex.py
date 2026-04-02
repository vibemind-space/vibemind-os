"""
Cortex Router -- FastAPI endpoints for the Brain's primary I/O.

Chat, continuous thoughts, thought evolution, and full brain state snapshot.

All state lives on ``request.app.state``:
  - ``brain_chat``           (BrainChat or None)
  - ``continuous_thinking``  (ContinuousThinkingEngine or None)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger('brain.cortex')

router = APIRouter()


# ===================================================================
# Route 1 — POST /api/cortex/chat
# ===================================================================

@router.post("/api/cortex/chat")
async def cortex_chat(request: Request) -> JSONResponse:
    """Primary chat endpoint -- routes through BrainChat.

    Body: ``{"message": "..."}`` (also accepts ``prompt`` key).
    """
    brain_chat = request.app.state.brain_chat
    if brain_chat is None:
        return JSONResponse(
            {"error": "brain chat not initialized"},
            status_code=503,
        )

    try:
        data: dict = await request.json()
    except ValueError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    except Exception:
        return JSONResponse({"error": "request parsing failed"}, status_code=400)

    message = data.get("message", data.get("prompt", ""))
    if not isinstance(message, str) or not message.strip():
        return JSONResponse({"error": "No message"}, status_code=400)
    message = message.strip()
    if len(message) > 10000:
        return JSONResponse(
            {"error": "message exceeds 10000 characters"}, status_code=400
        )

    # Snapshot pre-interaction centroid for influence delta measurement
    soc_metrics = getattr(request.app.state, 'socialization_metrics', None)
    if soc_metrics is not None:
        try:
            soc_metrics.snapshot_pre_interaction()
        except Exception:
            pass  # Non-critical — don't block chat

    try:
        result = brain_chat.send(message)
        return JSONResponse({
            **result.to_dict(),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as exc:
        return JSONResponse(
            {"error": f"chat failed: {exc}"},
            status_code=500,
        )


# ===================================================================
# Route 2 — GET /api/cortex/thoughts
# ===================================================================

@router.get("/api/cortex/thoughts")
async def cortex_thoughts(request: Request) -> JSONResponse:
    """Return continuous background thoughts from the CTE.

    Query params:
        n     — number of recent thoughts (default 20, max 200)
        since — timestamp; only return thoughts after this time
    """
    cte = request.app.state.continuous_thinking
    if cte is None:
        return JSONResponse({
            "thoughts": [],
            "stats": {},
            "thinking": False,
        })

    # --- validate & clamp 'n' ---
    try:
        n = max(1, min(int(request.query_params.get("n", 20)), 200))
    except (TypeError, ValueError):
        n = 20

    # --- validate & clamp 'since' ---
    try:
        since = max(0.0, float(request.query_params.get("since", 0.0)))
    except (TypeError, ValueError):
        since = 0.0

    try:
        if since > 0:
            thoughts = cte.get_thoughts_since(since)
        else:
            thoughts = cte.get_recent_thoughts(n)

        return JSONResponse({
            "thoughts": [
                {
                    "timestamp": t.timestamp,
                    "content": t.content,
                    "category": t.category,
                    "topic": t.topic,
                    "relevance": round(t.relevance, 3),
                    "emotional_valence": round(t.emotional_valence, 3),
                    "arousal": round(t.arousal, 3),
                    # Evolution fields
                    "thought_id": getattr(t, 'thought_id', ''),
                    "fitness": round(getattr(t, 'fitness', -1.0), 3),
                    "generation": getattr(t, 'generation', 0),
                    "parent_ids": getattr(t, 'parent_ids', None) or [],
                }
                for t in thoughts
            ],
            "stats": cte.get_stats(),
            "thinking": cte.is_running,
            "mode": cte.mode,
        })
    except Exception as exc:
        return JSONResponse(
            {"error": f"thoughts retrieval failed: {exc}"},
            status_code=500,
        )


# ===================================================================
# Route 3 — POST /api/cortex/thoughts/rate
# ===================================================================

@router.post("/api/cortex/thoughts/rate")
async def cortex_rate_thought(request: Request) -> JSONResponse:
    """Rate a thought's quality via the dashboard slider.

    Body: ``{"timestamp": float, "rating": int (1-100)}``
    """
    cte = request.app.state.continuous_thinking
    if cte is None:
        return JSONResponse(
            {"error": "continuous thinking not available"},
            status_code=503,
        )

    evo = getattr(cte, '_evolution_engine', None)
    if evo is None:
        return JSONResponse(
            {"error": "evolution engine not available"},
            status_code=503,
        )

    try:
        data: dict = await request.json()
    except (ValueError, Exception):
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    timestamp = data.get("timestamp")
    rating = data.get("rating")

    if timestamp is None or rating is None:
        return JSONResponse(
            {"error": "timestamp and rating required"},
            status_code=400,
        )

    try:
        rating_int = max(1, min(100, int(rating)))
    except (TypeError, ValueError):
        return JSONResponse({"error": "rating must be integer 1-100"}, status_code=400)

    evo.rate_thought(float(timestamp), rating_int / 100.0)
    return JSONResponse({"status": "ok", "rating": rating_int})


# ===================================================================
# Route 4 — GET /api/cortex/thought-graph
# ===================================================================

@router.get("/api/cortex/thought-graph")
async def cortex_thought_graph(request: Request) -> JSONResponse:
    """Return the semantic thought graph for visualization.

    Returns ``{"nodes": [...], "edges": [...]}`` with thought evolution
    lineage and semantic similarity links.
    """
    cte = request.app.state.continuous_thinking
    if cte is None:
        return JSONResponse({"nodes": [], "edges": []})

    evo = getattr(cte, '_evolution_engine', None)
    if evo is None:
        return JSONResponse({"nodes": [], "edges": []})

    try:
        graph = evo.get_graph()
        return JSONResponse(graph)
    except Exception as exc:
        return JSONResponse(
            {"error": f"graph retrieval failed: {exc}"},
            status_code=500,
        )


# ===================================================================
# Route 5 — GET /api/cortex/thought-manifold
# ===================================================================

@router.get("/api/cortex/thought-manifold")
async def cortex_thought_manifold(request: Request) -> JSONResponse:
    """Return 3D UMAP manifold projection of thought embeddings.

    Returns ``{nodes, edges, clusters, stats}`` with 3D coordinates
    for Three.js visualization.
    """
    cte = request.app.state.continuous_thinking
    if cte is None:
        return JSONResponse({
            'nodes': [], 'edges': [], 'clusters': [],
            'stats': {'total_nodes': 0, 'total_clusters': 0, 'avg_fitness': 0.0},
        })

    evo = getattr(cte, '_evolution_engine', None)
    if evo is None:
        return JSONResponse({
            'nodes': [], 'edges': [], 'clusters': [],
            'stats': {'total_nodes': 0, 'total_clusters': 0, 'avg_fitness': 0.0},
        })

    try:
        manifold = evo.get_manifold()
        return JSONResponse(manifold)
    except Exception as exc:
        return JSONResponse(
            {"error": f"manifold projection failed: {exc}"},
            status_code=500,
        )


# ===================================================================
# Route 6 — GET /api/cortex/state
# ===================================================================

@router.get("/api/cortex/state")
async def cortex_state(request: Request) -> JSONResponse:
    """Full brain state snapshot: routing + thinking + knowledge."""
    brain_chat = request.app.state.brain_chat
    cte = request.app.state.continuous_thinking

    try:
        chat_stats: dict = brain_chat.get_stats() if brain_chat else {}
    except Exception:
        chat_stats = {}

    try:
        thinking_stats: dict = cte.get_stats() if cte else {}
    except Exception:
        thinking_stats = {}

    recent_thoughts: list = []
    if cte is not None:
        try:
            recent = cte.get_recent_thoughts(5)
            recent_thoughts = [
                {
                    "content": t.content[:100],
                    "category": t.category,
                    "timestamp": t.timestamp,
                }
                for t in recent
            ]
        except Exception:
            pass

    return JSONResponse({
        "brain_chat": chat_stats,
        "continuous_thinking": thinking_stats,
        "recent_thoughts": recent_thoughts,
        "timestamp": datetime.now().isoformat(),
    })


# ===================================================================
# Route 7 — POST /api/cortex/thinking/toggle
# ===================================================================

@router.post("/api/cortex/thinking/toggle")
async def cortex_toggle_thinking(request: Request) -> JSONResponse:
    """Toggle the ContinuousThinkingEngine on/off.

    Body (optional): ``{"enabled": true/false}``
    If no body, toggles current state.
    """
    cte = request.app.state.continuous_thinking
    if cte is None:
        return JSONResponse(
            {"error": "CTE not initialized"},
            status_code=503,
        )

    try:
        data: dict = await request.json()
    except Exception:
        data = {}

    desired = data.get("enabled")
    if desired is None:
        desired = not cte.is_running

    if desired and not cte.is_running:
        cte.start()
    elif not desired and cte.is_running:
        cte.stop()

    return JSONResponse({
        "thinking": cte.is_running,
        "mode": getattr(cte, "mode", "unknown"),
    })


# ===================================================================
# Route 8 — GET /api/cortex/rowboat-data
# ===================================================================

@router.get("/api/cortex/rowboat-data")
async def cortex_rowboat_data(request: Request) -> JSONResponse:
    """Return summary of ingested Rowboat data."""
    rd = getattr(request.app.state, "_rowboat_data", None)
    if rd is None:
        return JSONResponse({
            "loaded": False,
            "stats": {"bubble_count": 0, "idea_count": 0, "edge_count": 0},
        })

    bubbles = rd.get("bubbles", [])
    return JSONResponse({
        "loaded": True,
        "stats": rd.get("stats", {}),
        "source_dir": rd.get("source_dir"),
        "bubbles": [b.to_dict() for b in bubbles],
    })


# ===================================================================
# Route 9 — POST /api/cortex/clusters
# ===================================================================

@router.post("/api/cortex/clusters")
async def cortex_create_clusters(request: Request) -> JSONResponse:
    """Create semantic clusters from ingested Rowboat ideas.

    Body (optional): ``{"eps": 0.5, "min_samples": 2}``
    """
    try:
        data: dict = await request.json()
    except Exception:
        data = {}

    eps = float(data.get("eps", 0.5))
    min_samples = int(data.get("min_samples", 2))

    rd = getattr(request.app.state, "_rowboat_data", None)
    if rd is None or not rd.get("all_ideas"):
        return JSONResponse({
            "clusters": [],
            "total_ideas": 0,
            "message": "No Rowboat data loaded. Check ~/.rowboat/vibemind/ideas/",
        })

    try:
        from core.semantic_clustering import cluster_ideas

        all_ideas = rd["all_ideas"]
        idea_dicts = [i.to_dict() for i in all_ideas]
        clusters = cluster_ideas(idea_dicts, eps=eps, min_samples=min_samples)

        clustered_count = sum(len(c.ideas) for c in clusters)
        result = {
            "clusters": [c.to_dict() for c in clusters],
            "total_ideas": len(idea_dicts),
            "clustered": clustered_count,
            "unclustered": len(idea_dicts) - clustered_count,
            "params": {"eps": eps, "min_samples": min_samples},
        }

        # Cache for GET
        request.app.state._cached_clusters = result
        return JSONResponse(result)

    except Exception as exc:
        return JSONResponse(
            {"error": f"clustering failed: {exc}"},
            status_code=500,
        )


# ===================================================================
# Route 10 — GET /api/cortex/clusters
# ===================================================================

@router.get("/api/cortex/clusters")
async def cortex_get_clusters(request: Request) -> JSONResponse:
    """Return most recently computed clusters (cached)."""
    cached = getattr(request.app.state, "_cached_clusters", None)
    if cached is None:
        return JSONResponse({
            "clusters": [],
            "message": "No clusters computed yet. POST /api/cortex/clusters to create.",
        })
    return JSONResponse(cached)


# ===================================================================
# Route 11 — POST /api/cortex/seed-rowboat
# ===================================================================

@router.post("/api/cortex/seed-rowboat")
async def cortex_seed_rowboat(request: Request) -> JSONResponse:
    """Seed the Moltbook and ThoughtStream with Rowboat bubble/idea data.

    Pipes all loaded Rowboat data into:
      1. MoltbookStore — as knowledge entries with embeddings
      2. ThoughtStream — as seeds for the CTE to think about

    This gives the brain initial material to think about from the start.

    Body (optional): ``{"max_seeds": 20, "include_ideas": true}``
    """
    moltbook = getattr(request.app.state, "moltbook_store", None)
    cte = request.app.state.continuous_thinking
    rd = getattr(request.app.state, "_rowboat_data", None)

    if rd is None or not rd.get("bubbles"):
        return JSONResponse({
            "seeded": False,
            "error": "No Rowboat data loaded. Check ~/.rowboat/vibemind/ideas/",
        }, status_code=404)

    if moltbook is None:
        return JSONResponse({
            "seeded": False,
            "error": "MoltbookStore not initialized",
        }, status_code=503)

    try:
        data: dict = await request.json()
    except Exception:
        data = {}

    max_seeds = int(data.get("max_seeds", 20))
    include_ideas = bool(data.get("include_ideas", True))

    bubbles = rd.get("bubbles", [])
    all_ideas = rd.get("all_ideas", [])

    moltbook_count = 0
    seed_count = 0
    seed_texts: list = []

    # --- Phase 1: Seed bubbles as knowledge entries ---
    for bubble in bubbles:
        # Build rich content from bubble metadata
        content_parts = [f"Bubble: {bubble.title}"]
        if bubble.description:
            content_parts.append(bubble.description)
        if bubble.notes:
            content_parts.append(f"Contains {len(bubble.notes)} ideas")

        content = " — ".join(content_parts)

        moltbook.add_entry(
            content=content,
            source_agent="rowboat:bubble",
            entry_type="knowledge",
            tags=["rowboat", "bubble", bubble.title.lower()],
            confidence=0.7,
            metadata={
                "rowboat_id": bubble.id,
                "bubble_title": bubble.title,
                "note_count": len(bubble.notes),
                "edge_count": len(bubble.edges),
            },
        )
        moltbook_count += 1

        # Add bubble as a thought seed — reference actual content
        idea_titles = [n.title for n in bubble.notes[:5] if getattr(n, "title", None)]
        if idea_titles:
            examples = ", ".join(idea_titles[:3])
            seed_text = f"In '{bubble.title}' gibt es Ideen wie {examples}. Welche Muster entstehen daraus?"
        else:
            seed_text = f"Wie lässt sich '{bubble.title}' mit anderen Themen verknüpfen?"
        seed_texts.append(seed_text)

    # --- Phase 2: Seed ideas as knowledge entries ---
    if include_ideas:
        for idea in all_ideas:
            # Build rich content from idea
            content_parts = [idea.title]
            if idea.content:
                # Truncate long content but keep meaningful length
                content_parts.append(idea.content[:500])
            if idea.bubble_title:
                content_parts.append(f"(aus Bubble: {idea.bubble_title})")

            content = " — ".join(content_parts)

            idea_tags = ["rowboat", "idea"]
            if idea.bubble_title:
                idea_tags.append(idea.bubble_title.lower())
            idea_tags.extend(t.lower() for t in (idea.tags or [])[:5])

            moltbook.add_entry(
                content=content,
                source_agent="rowboat:idea",
                entry_type="knowledge",
                tags=idea_tags,
                confidence=0.6,
                metadata={
                    "rowboat_id": idea.id,
                    "idea_title": idea.title,
                    "bubble_id": idea.bubble_id,
                    "bubble_title": idea.bubble_title,
                    "node_type": idea.node_type,
                },
            )
            moltbook_count += 1

            # Create concrete thought seeds referencing actual content
            if idea.content and len(idea.content) > 20:
                # Use actual content snippet, not just title
                snippet = idea.content[:80].strip().rstrip(".")
                seed_text = f"{idea.title}: {snippet}. Was folgt daraus?"
                seed_texts.append(seed_text)

    # --- Phase 3: Feed seeds into ThoughtStream ---
    if cte is not None:
        ts = getattr(cte, "_thought_stream", None)
        # Limit seeds to max_seeds, picking a diverse selection
        selected_seeds = seed_texts[:max_seeds] if len(seed_texts) <= max_seeds else (
            seed_texts[:max_seeds // 2] + seed_texts[-(max_seeds // 2):]
        )
        for seed in selected_seeds:
            if ts is not None:
                ts.add_seed(seed)
            seed_count += 1

        # Set exploration context with concrete bubble names
        bubble_names = [b.title for b in bubbles[:8]]
        topic_line = ", ".join(bubble_names)
        cte.set_topic(
            f"Denke konkret über diese Wissensgebiete nach: {topic_line}. "
            f"Finde Zusammenhänge, Widersprüche und neue Ideen. "
            f"Beziehe dich immer auf konkrete Inhalte aus den {len(all_ideas)} Ideen."
        )

    stats = rd.get("stats", {})
    return JSONResponse({
        "seeded": True,
        "moltbook_entries": moltbook_count,
        "thought_seeds": seed_count,
        "rowboat_stats": {
            "bubbles": len(bubbles),
            "ideas": len(all_ideas),
            "source_dir": rd.get("source_dir", ""),
        },
        "message": f"Seeded {moltbook_count} entries into Moltbook, {seed_count} thought seeds into CTE",
    })


# ===================================================================
# Route 12 — POST /api/cortex/thought-clusters
# ===================================================================

@router.post("/api/cortex/thought-clusters")
async def cortex_thought_clusters(request: Request) -> JSONResponse:
    """Cluster Moltbook entries and build a Klotski state-space 3D graph.

    Returns a full graph representation (nodes + edges + 3D positions)
    suitable for Three.js force-directed visualization.

    Each node = one Moltbook entry (idea, bubble, thought).
    Edges = semantic similarity connections above threshold.
    Clusters = DBSCAN groups, each colored differently.
    3D positions = PCA projection of embedding vectors.

    Body (optional): ``{"eps": 0.45, "min_samples": 2, "source": "all",
                        "edge_threshold": 0.6, "spread": 12.0}``
    """
    moltbook = getattr(request.app.state, "moltbook_store", None)
    if moltbook is None:
        return JSONResponse({
            "graph": {"nodes": [], "edges": []},
            "error": "MoltbookStore not initialized",
        }, status_code=503)

    try:
        data: dict = await request.json()
    except Exception:
        data = {}

    eps = float(data.get("eps", 0.45))
    min_samples = int(data.get("min_samples", 2))
    source_filter = data.get("source", "all")
    edge_threshold = float(data.get("edge_threshold", 0.6))
    spread = float(data.get("spread", 12.0))

    # Collect entries from Moltbook
    entries: List = []
    with moltbook._lock:
        for entry in moltbook._entries.values():
            if source_filter == "rowboat" and not entry.source_agent.startswith("rowboat:"):
                continue
            if source_filter == "thoughts" and entry.source_agent.startswith("rowboat:"):
                continue
            entries.append(entry)

    if len(entries) < min_samples:
        return JSONResponse({
            "graph": {"nodes": [], "edges": []},
            "clusters": [],
            "total_entries": len(entries),
            "message": f"Need at least {min_samples} entries, have {len(entries)}",
        })

    try:
        import numpy as np
        from collections import Counter
        from core.semantic_clustering import _cosine_distance_matrix, _dbscan

        # Extract embeddings
        valid_entries = []
        vectors = []
        for entry in entries:
            if entry.semantic_embedding is not None:
                valid_entries.append(entry)
                vectors.append(entry.semantic_embedding)

        if len(valid_entries) < min_samples:
            return JSONResponse({
                "graph": {"nodes": [], "edges": []},
                "clusters": [],
                "total_entries": len(entries),
                "message": "Not enough entries with embeddings",
            })

        vec_matrix = np.array(vectors, dtype=np.float32)
        n = len(valid_entries)

        # ── PCA to 3D for node positions ──
        mean = vec_matrix.mean(axis=0)
        centered = vec_matrix - mean
        # Covariance and top-3 eigenvectors
        cov = np.dot(centered.T, centered) / max(1, n - 1)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        # Top 3 components (largest eigenvalues are last)
        top3 = eigenvectors[:, -3:][:, ::-1]
        coords_3d = np.dot(centered, top3)
        # Scale to desired spread
        max_range = max(1e-6, float(np.abs(coords_3d).max()))
        coords_3d = coords_3d * (spread / max_range)

        # ── Cosine similarity matrix ──
        norms = np.linalg.norm(vec_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        normed = vec_matrix / norms
        sim_matrix = np.dot(normed, normed.T)

        # ── DBSCAN clustering ──
        dist_matrix = 1.0 - sim_matrix
        np.fill_diagonal(dist_matrix, 0.0)
        dist_matrix = np.clip(dist_matrix, 0.0, 2.0)
        labels = _dbscan(dist_matrix, eps=eps, min_samples=min_samples)

        # ── Build graph nodes ──
        graph_nodes = []
        for idx in range(n):
            entry = valid_entries[idx]
            cluster_id = int(labels[idx])
            bubble_title = entry.metadata.get("bubble_title", "")
            idea_title = entry.metadata.get("idea_title", "")
            display_title = idea_title or entry.content[:50]

            # Node size by content length
            content_len = len(entry.content)
            if content_len > 300:
                size = 3.0  # Core concept
            elif content_len > 100:
                size = 2.0  # Medium
            else:
                size = 1.2  # Small

            graph_nodes.append({
                "id": entry.id,
                "label": display_title,
                "content_preview": entry.content[:120],
                "source": entry.source_agent,
                "bubble": bubble_title,
                "cluster_id": cluster_id,
                "confidence": round(float(entry.confidence), 2),
                "tags": entry.tags[:5],
                "size": round(size, 1),
                "x": round(float(coords_3d[idx, 0]), 3),
                "y": round(float(coords_3d[idx, 1]), 3),
                "z": round(float(coords_3d[idx, 2]), 3),
            })

        # ── Build graph edges (similarity > threshold) ──
        graph_edges = []
        for i in range(n):
            for j in range(i + 1, n):
                sim_val = float(sim_matrix[i, j])
                if sim_val >= edge_threshold:
                    graph_edges.append({
                        "source": valid_entries[i].id,
                        "target": valid_entries[j].id,
                        "weight": round(sim_val, 3),
                    })

        # ── Cluster summaries ──
        cluster_map: Dict[int, list] = {}
        for idx, lbl in enumerate(labels):
            if lbl == -1:
                continue
            cluster_map.setdefault(int(lbl), []).append(idx)

        cluster_summaries = []
        for cid, member_indices in sorted(cluster_map.items()):
            members = [valid_entries[i] for i in member_indices]
            member_vecs = vec_matrix[member_indices]

            # Coherence
            if len(member_vecs) >= 2:
                m_norms = np.linalg.norm(member_vecs, axis=1, keepdims=True)
                m_norms[m_norms == 0] = 1e-10
                m_normed = member_vecs / m_norms
                m_sim = np.dot(m_normed, m_normed.T)
                mn = len(member_vecs)
                coherence = float(
                    sum(m_sim[i, j] for i in range(mn) for j in range(i + 1, mn))
                    / max(1, mn * (mn - 1) // 2)
                )
            else:
                coherence = 1.0

            # Label from common words
            words = []
            for m in members:
                for w in m.content.split()[:10]:
                    w_clean = w.strip(".,;:!?()[]{}\"'\u2014").lower()
                    if len(w_clean) > 3:
                        words.append(w_clean)
            common = Counter(words).most_common(3)
            label = " / ".join(w.title() for w, _ in common) if common else f"Cluster {cid}"

            # Cluster centroid position (average of member positions)
            c_coords = coords_3d[member_indices]
            centroid = c_coords.mean(axis=0)

            cluster_summaries.append({
                "cluster_id": cid,
                "label": label,
                "size": len(members),
                "coherence": round(coherence, 3),
                "centroid": {
                    "x": round(float(centroid[0]), 3),
                    "y": round(float(centroid[1]), 3),
                    "z": round(float(centroid[2]), 3),
                },
                "node_ids": [valid_entries[i].id for i in member_indices],
            })

        total_clustered = sum(len(c["node_ids"]) for c in cluster_summaries)

        result = {
            "graph": {
                "nodes": graph_nodes,
                "edges": graph_edges,
            },
            "clusters": cluster_summaries,
            "total_entries": len(entries),
            "total_with_embeddings": n,
            "clustered": total_clustered,
            "unclustered": n - total_clustered,
            "edge_count": len(graph_edges),
            "params": {
                "eps": eps,
                "min_samples": min_samples,
                "source": source_filter,
                "edge_threshold": edge_threshold,
                "spread": spread,
            },
        }

        # Cache for GET
        request.app.state._cached_thought_clusters = result
        return JSONResponse(result)

    except Exception as exc:
        logger.error(f"Thought clustering failed: {exc}", exc_info=True)
        return JSONResponse(
            {"error": f"clustering failed: {exc}"},
            status_code=500,
        )


# ===================================================================
# Route 13 — GET /api/cortex/thought-clusters
# ===================================================================

@router.get("/api/cortex/thought-clusters")
async def cortex_get_thought_clusters(request: Request) -> JSONResponse:
    """Return most recently computed thought clusters (cached)."""
    cached = getattr(request.app.state, "_cached_thought_clusters", None)
    if cached is None:
        return JSONResponse({
            "graph": {"nodes": [], "edges": []},
            "clusters": [],
            "message": "No thought clusters computed yet. POST /api/cortex/thought-clusters first.",
        })
    return JSONResponse(cached)


# ===================================================================
# Route 13 — GET /api/cortex/cluster-evolution
# ===================================================================

@router.get("/api/cortex/cluster-evolution")
async def cortex_cluster_evolution(request: Request) -> JSONResponse:
    """Return living DGM clusters, their fitness, and evolution stats.

    The ClusterEvolutionEngine runs inside the thought stream —
    clusters evolve, verify, and grow organically from rowboat user data.
    """
    brain_chat = getattr(request.app.state, 'brain_chat', None)
    engine = getattr(brain_chat, '_cluster_evolution_engine', None) if brain_chat else None

    if not engine:
        return JSONResponse({
            "clusters": [],
            "stats": {},
            "message": "ClusterEvolutionEngine not active.",
        })

    return JSONResponse({
        "clusters": engine.get_clusters(),
        "stats": engine.get_stats(),
    })


# ===================================================================
# Route 14 — GET /api/cortex/cluster-lineage
# ===================================================================

@router.get("/api/cortex/cluster-lineage")
async def cortex_cluster_lineage(request: Request) -> JSONResponse:
    """Return cluster evolution tree (nodes + edges).

    Shows how clusters split, merged, and mutated over time —
    living clusters + archived ancestors referenced by lineage.
    """
    brain_chat = getattr(request.app.state, 'brain_chat', None)
    engine = getattr(brain_chat, '_cluster_evolution_engine', None) if brain_chat else None

    if not engine:
        return JSONResponse({
            "nodes": [],
            "edges": [],
            "message": "ClusterEvolutionEngine not active.",
        })

    return JSONResponse(engine.get_lineage())


# ===================================================================
# Route 15 — POST /api/cortex/cluster-evolve
# ===================================================================

@router.post("/api/cortex/cluster-evolve")
async def cortex_cluster_evolve_manual(request: Request) -> JSONResponse:
    """Manually trigger one DGM cluster evolution step.

    Useful for testing or forcing evolution when the thought stream
    hasn't triggered it yet. Returns the thought produced by the step.
    """
    brain_chat = getattr(request.app.state, 'brain_chat', None)
    engine = getattr(brain_chat, '_cluster_evolution_engine', None) if brain_chat else None

    if not engine:
        return JSONResponse({
            "success": False,
            "message": "ClusterEvolutionEngine not active.",
        }, status_code=503)

    try:
        thought = engine.evolve_step()
        return JSONResponse({
            "success": True,
            "thought": {
                "content": thought.content if thought else None,
                "category": thought.category if thought else None,
                "topic": thought.topic if thought else None,
            },
            "stats": engine.get_stats(),
            "clusters": engine.get_clusters(),
        })
    except Exception as e:
        logger.error("Cluster evolution step failed: %s", e)
        return JSONResponse({
            "success": False,
            "error": str(e),
        }, status_code=500)


# ===================================================================
# Route 16 — GET /api/cortex/cluster-archive
# ===================================================================

@router.get("/api/cortex/cluster-archive")
async def cortex_cluster_archive(request: Request) -> JSONResponse:
    """Return the archive of high-fitness cluster snapshots.

    The archive preserves cluster configurations that scored well —
    a historical record of what the brain learned about its own structure.
    """
    brain_chat = getattr(request.app.state, 'brain_chat', None)
    engine = getattr(brain_chat, '_cluster_evolution_engine', None) if brain_chat else None

    if not engine:
        return JSONResponse({
            "archive": [],
            "message": "ClusterEvolutionEngine not active.",
        })

    return JSONResponse({
        "archive": engine._archive[-50:],
        "total": len(engine._archive),
    })


# ===================================================================
# Route 17 — GET /api/cortex/meta-graph
# ===================================================================

@router.get("/api/cortex/meta-graph")
async def cortex_meta_graph(request: Request) -> JSONResponse:
    """Return the meta-knowledge graph: clusters, inter-cluster edges,
    meta-root, LLM syntheses, and CTM insights.

    The MetaKnowledgeGraph is updated every 30s by MemoryConsolidator
    phases 8-10 (CLUSTER, SYNTHESIZE, META_ROOT).
    """
    meta_graph = getattr(request.app.state, 'meta_knowledge_graph', None)
    if meta_graph is None:
        return JSONResponse({
            "clusters": [],
            "inter_cluster_edges": [],
            "meta_root": None,
            "syntheses": [],
            "ctm_insights": [],
            "stats": {},
            "message": "MetaKnowledgeGraph not initialized.",
        })

    return JSONResponse(meta_graph.to_dict())


# ===================================================================
# Route 18 — POST /api/cortex/meta-graph/update
# ===================================================================

@router.post("/api/cortex/meta-graph/update")
async def cortex_meta_graph_update(request: Request) -> JSONResponse:
    """Build Level-2 meta-areals from existing Klotski clusters.

    Pipeline:
        1. Get cached Klotski clusters (from POST /api/cortex/thought-clusters)
        2. Compute 384-dim centroid for each Klotski cluster
        3. DBSCAN on centroids → meta-areals (groups of clusters)
        4. Compute meta-root (highest semantic reachability)

    This is a HIGHER abstraction than the Klotski graph:
        Level 1: 744 entries → 40 Klotski clusters
        Level 2: 40 cluster centroids → 3-8 meta-areals

    Body (optional): ``{"n_areals": 6}``
    Default n_areals = max(3, round(sqrt(n_clusters)))
    """
    meta_graph = getattr(request.app.state, 'meta_knowledge_graph', None)
    moltbook = getattr(request.app.state, 'moltbook_store', None)

    if meta_graph is None:
        return JSONResponse({"error": "MetaKnowledgeGraph not initialized"}, status_code=503)
    if moltbook is None:
        return JSONResponse({"error": "MoltbookStore not initialized"}, status_code=503)

    # Get optional params
    try:
        data: dict = await request.json()
    except Exception:
        data = {}
    n_areals = data.get("n_areals", None)
    if n_areals is not None:
        n_areals = int(n_areals)

    # Step 1: Get cached Klotski clusters
    cached = getattr(request.app.state, "_cached_thought_clusters", None)
    if cached is None or not cached.get("clusters"):
        return JSONResponse({
            "error": "No Klotski clusters available. POST /api/cortex/thought-clusters first.",
            "hint": "Click 'Seed + Cluster' in the Klotski 3D view.",
        })

    klotski_clusters = cached["clusters"]

    # Step 2: Get Moltbook entries (for embedding lookup)
    entries = list(moltbook._entries.values())

    try:
        # Step 3: Level-2 clustering
        areals = meta_graph.update_from_klotski_clusters(
            klotski_clusters=klotski_clusters,
            klotski_entries=entries,
            n_areals=n_areals,
        )

        # Step 4: Compute meta-root
        meta_root_id = meta_graph.compute_reachability()
        meta_root = meta_graph.get_cluster_by_id(meta_root_id) if meta_root_id is not None else None

        # Update KuroGraph overlay
        dual_graph = getattr(request.app.state, 'dual_graph', None)
        if dual_graph:
            kuro = getattr(dual_graph, 'kurograph', None)
            if kuro:
                kuro.set_cluster_overlay(meta_graph.get_cluster_overlay())

        return JSONResponse({
            "success": True,
            "areals": len(areals),
            "klotski_clusters_input": len(klotski_clusters),
            "meta_root_id": meta_root_id,
            "meta_root_topic": meta_root.dominant_topic if meta_root else None,
            "params": {"n_areals": n_areals or "auto"},
            "graph": meta_graph.to_dict(),
        })

    except Exception as exc:
        logger.error(f"Meta-graph update failed: {exc}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ===================================================================
# Route — GET /api/cortex/radial-bridge/stats
# ===================================================================

@router.get("/api/cortex/radial-bridge/stats")
async def radial_bridge_stats(request: Request) -> JSONResponse:
    """Stats for the ThoughtRadialBridge — thoughts processed, rewards, actions triggered."""
    bridge = getattr(request.app.state, 'thought_radial_bridge', None)
    if bridge is None:
        return JSONResponse({"error": "ThoughtRadialBridge not initialized"}, status_code=503)
    return JSONResponse(bridge.get_stats())


# ===================================================================
# Route — GET /api/cortex/thought-jury/stats
# ===================================================================

@router.get("/api/cortex/thought-jury/stats")
async def thought_jury_stats(request: Request) -> JSONResponse:
    """Stats for the ThoughtJury — evaluations, rewards, judge weights."""
    jury = getattr(request.app.state, 'thought_jury', None)
    if jury is None:
        return JSONResponse({"error": "ThoughtJury not initialized"}, status_code=503)
    return JSONResponse(jury.get_stats())


# ===================================================================
# Route — GET /api/cortex/thoughts/signatures
# ===================================================================

@router.get("/api/cortex/thoughts/signatures")
async def cortex_thought_signatures(request: Request) -> JSONResponse:
    """Recent thoughts with their RingSignatures — for dashboard visualization."""
    cte = request.app.state.continuous_thinking
    if cte is None:
        return JSONResponse({"error": "CTE not initialized"}, status_code=503)

    thoughts_data = []
    with cte._thought_lock:
        recent = list(cte._thoughts)[-20:]

    for t in recent:
        entry = {
            'thought_id': getattr(t, 'thought_id', ''),
            'content': t.content[:200],
            'category': t.category,
            'relevance': t.relevance,
            'timestamp': t.timestamp,
        }
        ring_sig = getattr(t, '_ring_signature', None)
        if ring_sig is not None:
            entry['ring_signature'] = ring_sig.to_dict()
        thoughts_data.append(entry)

    return JSONResponse({
        "thoughts": thoughts_data,
        "count": len(thoughts_data),
    })


# ===================================================================
# Route — GET /api/cortex/outcome-rewards/stats
# ===================================================================

@router.get("/api/cortex/outcome-rewards/stats")
async def outcome_reward_stats(request: Request) -> JSONResponse:
    """Stats for outcome-based rewards — moltbook entries, MKG edges, citations, redundancy."""
    tracker = getattr(request.app.state, 'outcome_tracker', None)
    if tracker is None:
        return JSONResponse({"error": "OutcomeRewardTracker not initialized"}, status_code=503)
    return JSONResponse(tracker.get_stats())


# ===================================================================
# Route — GET /api/brain/diagnostics
# ===================================================================

@router.get("/api/brain/diagnostics")
async def brain_diagnostics(request: Request) -> JSONResponse:
    """Full initialization status — what's running, what's None, what failed."""
    s = request.app.state
    agent_loop = getattr(s, 'agent_loop', None)
    cte = getattr(s, 'continuous_thinking', None)
    return JSONResponse({
        "brain_chat": s.brain_chat is not None,
        "continuous_thinking": cte is not None,
        "cte_running": getattr(cte, '_running', False) if cte else False,
        "cte_mode": getattr(cte, '_mode', None) if cte else None,
        "cte_thought_count": len(getattr(cte, '_thoughts', [])) if cte else 0,
        "cte_knowledge_count": len(getattr(cte, '_learned_knowledge', [])) if cte else 0,
        "agent_loop": agent_loop is not None,
        "radial_network": getattr(agent_loop, 'radial_network', None) is not None,
        "seed_encoder": getattr(agent_loop, 'seed_encoder', None) is not None,
        "experience_buffer": getattr(agent_loop, 'experience_buffer', None) is not None,
        "hebbian": getattr(agent_loop, 'hebbian', None) is not None,
        "thought_radial_bridge": getattr(s, 'thought_radial_bridge', None) is not None,
        "thought_jury": getattr(s, 'thought_jury', None) is not None,
        "outcome_tracker": getattr(s, 'outcome_tracker', None) is not None,
        "moltbook_store": getattr(s, 'moltbook_store', None) is not None,
        "moltbook_entries": len(getattr(getattr(s, 'moltbook_store', None), '_entries', {})) if getattr(s, 'moltbook_store', None) else 0,
        "memory_consolidator": getattr(s, 'memory_consolidator', None) is not None,
        "meta_knowledge_graph": getattr(s, 'meta_knowledge_graph', None) is not None,
        "thalamic_adapter": getattr(s, 'thalamic_adapter', None) is not None,
        "space_routing_head": getattr(s, 'space_routing_head', None) is not None,
    })
