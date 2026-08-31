"""Phase 11.U.C.7 — Brain's async Supabase REST client for ideas + edges.

Why: Brain runs in a different process from Voice, but both need to read/write
the same canvas_nodes/canvas_edges. Voice talks to Supabase via
`supabase-client.js` (Electron) and `supabase_database.py` (Voice/Python).
Brain previously had no path to this data — connection-related capabilities
(`idea_connect`, `idea_disconnect`, `idea_auto_link`) were wired to
`direct:idea_tools.connect_ideas` which fails because Brain has no
canvas_repo binding.

This module gives Brain its own minimal async path:

  client = SupabaseIdeasClient()
  hits = await client.find_canvas_node_by_title("Alpha")
  ok = await client.create_edge(from_id, to_id, "related")
  edges = await client.list_edges(from_id=..., to_id=...)
  ok = await client.delete_edge(edge_id)

Design:
- Uses the shared httpx.AsyncClient from multi_llm_router (keepalive pool)
- Supabase URL + (optional) anon-key from env: SUPABASE_URL, SUPABASE_ANON_KEY
- No supabase-py dep — plain REST
- All methods return primitive dicts/lists or None on failure
- Errors are logged, not raised; callers decide how to surface
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://192.168.178.65:54321").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "anon").strip()


class SupabaseIdeasClient:
    """Async REST client for canvas_nodes + canvas_edges (and ideas)."""

    def __init__(
        self,
        url: Optional[str] = None,
        anon_key: Optional[str] = None,
    ) -> None:
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.key = (anon_key or SUPABASE_KEY).strip() or "anon"
        self.rest = f"{self.url}/rest/v1"
        # Stats for /api/llm/stats-style introspection
        self.stats: Dict[str, Any] = {
            "calls": 0, "errors": 0, "last_error": None,
            "edges_created": 0, "edges_deleted": 0,
        }

    def _headers(self, *, prefer: Optional[str] = None) -> Dict[str, str]:
        h = {
            "apikey": self.key,
            "Content-Type": "application/json",
        }
        # Only set Bearer when key looks like a real JWT (3 dot-separated parts).
        # Local Supabase rejects "Bearer anon" with 401 PGRST301 because it
        # tries to JWT-verify it. Plain `apikey: anon` is enough for anon RLS.
        if self.key and self.key.count(".") == 2:
            h["Authorization"] = f"Bearer {self.key}"
        if prefer:
            h["Prefer"] = prefer
        return h

    async def _request(
        self, method: str, path: str, *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        prefer: Optional[str] = None,
    ) -> Optional[Any]:
        """Single REST call. Returns parsed JSON (or None on failure).

        Phase 11.U.C — uses a fresh httpx.AsyncClient per call. The
        process-wide cached client from multi_llm_router doesn't survive
        SupabaseExecutor's asyncio.run-per-call pattern (the previous loop
        closes its associated transports). Per-call clients are slower but
        correct; if we ever push enough Supabase traffic to care, we'll
        wire this onto the FastAPI event loop instead.
        """
        import httpx as _httpx
        url = f"{self.rest}{path}"
        self.stats["calls"] += 1
        try:
            async with _httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request(
                    method, url,
                    headers=self._headers(prefer=prefer),
                    params=params or None,
                    json=json,
                )
            if resp.status_code >= 400:
                body = ""
                try:
                    body = resp.text[:300]
                except Exception:
                    pass
                self.stats["errors"] += 1
                self.stats["last_error"] = f"HTTP {resp.status_code}: {body}"
                logger.warning(f"[supabase] {method} {path} -> {resp.status_code} {body}")
                return None
            if resp.status_code == 204 or not resp.content:
                return True  # DELETE / no-body success
            return resp.json()
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"{type(e).__name__}: {e}"
            logger.warning(f"[supabase] {method} {path} crash: {e}")
            return None

    # ── canvas_nodes ──────────────────────────────────────────────────────

    async def find_canvas_node_by_title(
        self, title: str, *, limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Case-insensitive prefix + contains match. Returns ranked hits.

        Strategy: exact (case-insensitive) first; if none, ilike contains.
        Caller picks the top one (or asks the user to disambiguate).
        """
        t = (title or "").strip()
        if not t:
            return []
        # Exact case-insensitive: ilike with no wildcards
        exact = await self._request(
            "GET", "/canvas_nodes",
            params={
                "select": "id,title,linked_idea_id",
                "title": f"ilike.{t}",
                "limit": str(limit),
            },
        )
        if exact:
            return exact
        # Fall back to substring match
        sub = await self._request(
            "GET", "/canvas_nodes",
            params={
                "select": "id,title,linked_idea_id",
                "title": f"ilike.*{t}*",
                "limit": str(limit),
            },
        )
        return sub or []

    async def get_canvas_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        hits = await self._request(
            "GET", "/canvas_nodes",
            params={"select": "*", "id": f"eq.{node_id}", "limit": "1"},
        )
        return hits[0] if hits else None

    async def list_canvas_nodes_in_bubble(
        self, bubble_id: Optional[str], *, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List nodes in a given bubble (linked_idea_id=bubble_id). If
        bubble_id is None, returns all top-level nodes (linked_idea_id IS NULL)."""
        params = {"select": "id,title,linked_idea_id", "limit": str(limit)}
        if bubble_id:
            params["linked_idea_id"] = f"eq.{bubble_id}"
        else:
            params["linked_idea_id"] = "is.null"
        return await self._request("GET", "/canvas_nodes", params=params) or []

    async def get_canvas_node_in_bubble(
        self, bubble_id: str, title: str,
    ) -> Optional[Dict[str, Any]]:
        """Phase 11.W2 — read-back a single node by (bubble, exact title).

        Used by create_op to VERIFY a write actually persisted before
        reporting success. Scoped to the bubble (linked_idea_id) and a
        case-insensitive exact title — same key the dedup in
        create_canvas_node uses. Returns the row or None.
        """
        bid = (bubble_id or "").strip()
        t = (title or "").strip()
        if not bid or not t:
            return None
        rows = await self._request(
            "GET", "/canvas_nodes",
            params={
                "select": "*",
                "linked_idea_id": f"eq.{bid}",
                "title": f"ilike.{t}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def create_canvas_node(
        self,
        bubble_id: str,
        title: str,
        content: str = "",
        *,
        node_type: str = "note",
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Insert a node into a bubble's canvas. Idempotent on (bubble, title):
        if a node with the same title already exists in this bubble it is
        returned untouched instead of creating a duplicate.

        Columns mirror the live schema (verified against a real E-Ticketing
        node): id, node_type, title, content, x, y, linked_idea_id, metadata.
        Voice's canvas_manager and the renderer key off linked_idea_id +
        title; metadata.width/height keep the 3D box sized like every other
        node.
        """
        bid = (bubble_id or "").strip()
        t = (title or "").strip()
        if not bid or not t:
            return None
        # Dedup: same title already in this bubble → return it, don't insert.
        existing = await self._request(
            "GET", "/canvas_nodes",
            params={
                "select": "*",
                "linked_idea_id": f"eq.{bid}",
                "title": f"ilike.{t}",
                "limit": "1",
            },
        )
        if existing:
            return existing[0]
        # Spread new nodes deterministically so they don't all stack at 0,0.
        # Voice re-layouts on enter anyway; this is just a sane initial spot.
        import random as _random
        node = {
            "id": uuid.uuid4().hex[:8],
            "node_type": node_type,
            "title": t,
            "content": content or t,
            "x": int(x) if x is not None else _random.randint(120, 900),
            "y": int(y) if y is not None else _random.randint(80, 600),
            "linked_idea_id": bid,
            "metadata": {"width": 200.0, "height": 100.0},
        }
        result = await self._request(
            "POST", "/canvas_nodes",
            json=node, prefer="return=representation",
        )
        if result:
            self.stats["nodes_created"] = self.stats.get("nodes_created", 0) + 1
            return result[0] if isinstance(result, list) and result else node
        return None

    async def update_canvas_node(
        self, node_id: str, fields: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """PATCH a node by id. `fields` is a whitelist-checked partial
        (title/content/summary/x/y/node_type/metadata). Returns the updated
        row or None."""
        nid = (node_id or "").strip()
        if not nid or not isinstance(fields, dict) or not fields:
            return None
        allowed = {"title", "content", "summary", "x", "y",
                   "node_type", "metadata"}
        patch = {k: v for k, v in fields.items() if k in allowed}
        if not patch:
            return None
        result = await self._request(
            "PATCH", "/canvas_nodes",
            params={"id": f"eq.{nid}"},
            json=patch, prefer="return=representation",
        )
        if result:
            self.stats["nodes_updated"] = self.stats.get("nodes_updated", 0) + 1
            return result[0] if isinstance(result, list) and result else True
        return None

    # ── canvas_edges ──────────────────────────────────────────────────────

    async def list_edges(
        self, *,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"select": "*", "limit": str(limit)}
        if from_id:
            params["from_node_id"] = f"eq.{from_id}"
        if to_id:
            params["to_node_id"] = f"eq.{to_id}"
        return await self._request("GET", "/canvas_edges", params=params) or []

    async def find_edge_between(
        self, a_id: str, b_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Find an edge between a and b regardless of direction."""
        # Supabase REST `or` filter: or=(...)
        params = {
            "select": "*",
            "or": (
                f"(and(from_node_id.eq.{a_id},to_node_id.eq.{b_id}),"
                f"and(from_node_id.eq.{b_id},to_node_id.eq.{a_id}))"
            ),
            "limit": "1",
        }
        hits = await self._request("GET", "/canvas_edges", params=params)
        return (hits or [None])[0]

    async def create_edge(
        self, from_id: str, to_id: str, edge_type: str = "related",
    ) -> Optional[Dict[str, Any]]:
        """Insert an edge. Returns the created row or None on failure."""
        if not from_id or not to_id:
            return None
        if from_id == to_id:
            logger.warning(f"[supabase] refusing self-loop {from_id}")
            return None
        # Pre-check: edge already exists?
        existing = await self.find_edge_between(from_id, to_id)
        if existing:
            return existing
        edge = {
            "id": uuid.uuid4().hex,
            "from_node_id": from_id,
            "to_node_id": to_id,
            "edge_type": edge_type,
        }
        result = await self._request(
            "POST", "/canvas_edges",
            json=edge, prefer="return=representation",
        )
        if result:
            self.stats["edges_created"] += 1
            return result[0] if isinstance(result, list) and result else edge
        return None

    async def delete_edge(self, edge_id: str) -> bool:
        ok = await self._request(
            "DELETE", "/canvas_edges",
            params={"id": f"eq.{edge_id}"},
        )
        if ok is not None and ok is not False:
            self.stats["edges_deleted"] += 1
            return True
        return False

    async def delete_edge_between(self, a_id: str, b_id: str) -> int:
        """Delete any edge between a and b. Returns number deleted."""
        edge = await self.find_edge_between(a_id, b_id)
        if edge is None:
            return 0
        ok = await self.delete_edge(edge["id"])
        return 1 if ok else 0

    # ── ideas (bubble-level) ──────────────────────────────────────────────

    async def list_bubbles(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        return await self._request(
            "GET", "/ideas",
            params={
                "select": "id,title,parent_id",
                "parent_id": "is.null",
                "limit": str(limit),
            },
        ) or []

    async def get_idea(self, idea_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single idea (bubble) row by id."""
        nid = (idea_id or "").strip()
        if not nid:
            return None
        hits = await self._request(
            "GET", "/ideas",
            params={"select": "*", "id": f"eq.{nid}", "limit": "1"},
        )
        return hits[0] if hits else None

    async def find_bubble_by_title(
        self, title: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolve a top-level bubble by exact (case-insensitive) title."""
        t = (title or "").strip()
        if not t:
            return None
        hits = await self._request(
            "GET", "/ideas",
            params={
                "select": "id,title,parent_id,score,status,metadata",
                "title": f"ilike.{t}",
                "parent_id": "is.null",
                "limit": "1",
            },
        )
        return hits[0] if hits else None

    async def update_idea_eval(
        self,
        idea_id: str,
        ai_eval: Dict[str, Any],
        score: float,
        *,
        status: str = "scored",
    ) -> Optional[Dict[str, Any]]:
        """Merge an ai_eval block into ideas.metadata and set score/status.

        Reads the current metadata first so we never clobber sibling keys
        (impact/novelty/position/eval_history/last_eval). Mirrors exactly
        what the spaces-ideas evaluate_bubble_evolution path used to write,
        so the renderer's `bubble_evolution_scored` handler + DB-fallback
        keep working unchanged.
        """
        nid = (idea_id or "").strip()
        if not nid or not isinstance(ai_eval, dict):
            return None
        row = await self.get_idea(nid)
        meta = dict((row or {}).get("metadata") or {})
        meta["ai_eval"] = ai_eval
        # Keep a small rolling eval_history so trend is visible.
        hist = list(meta.get("eval_history") or [])
        hist.append({
            "ts": int(__import__("time").time()),
            "score": round(float(score), 1),
            "dims": {k: ai_eval.get(k) for k in
                     ("completeness", "structure", "actionability", "depth")},
        })
        meta["eval_history"] = hist[-20:]
        patch = {
            "metadata": meta,
            "score": round(float(score), 1),
            "status": status,
        }
        result = await self._request(
            "PATCH", "/ideas",
            params={"id": f"eq.{nid}"},
            json=patch, prefer="return=representation",
        )
        if result:
            self.stats["evals_written"] = self.stats.get("evals_written", 0) + 1
            return result[0] if isinstance(result, list) and result else True
        return None

    # ── Phase 11.U.H — generic CRUD for the full-cap migration ──────────
    # These back the 36 capabilities that used to call direct:spaces.* (a
    # code path that does not exist in the Brain container). Everything is
    # REST against Supabase — the single source of truth.

    async def create_bubble(
        self, title: str, *, description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Insert a top-level bubble (ideas row, parent_id NULL).
        Idempotent on title — returns the existing one if present."""
        t = (title or "").strip()
        if not t:
            return None
        existing = await self.find_bubble_by_title(t)
        if existing:
            return existing
        row = {
            "id": uuid.uuid4().hex[:8],
            "title": t,
            "description": (description or "").strip(),
            "parent_id": None,
            "score": 0,
            "status": "active",
            "source": "brain",
            "tags": tags or [],
            "metadata": {},
        }
        result = await self._request(
            "POST", "/ideas", json=row, prefer="return=representation",
        )
        if result:
            self.stats["bubbles_created"] = self.stats.get("bubbles_created", 0) + 1
            return result[0] if isinstance(result, list) and result else row
        return None

    async def promote_bubble(
        self, bubble: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Create a project and link the source bubble to it in Supabase.

        The project row is the externally queryable execution result. If the
        bubble link cannot be persisted, remove the new project so callers do
        not receive a fabricated successful promotion.
        """
        bubble_id = str((bubble or {}).get("id") or "").strip()
        title = str((bubble or {}).get("title") or "").strip()
        if not bubble_id or not title:
            return None

        project_row = {
            "id": uuid.uuid4().hex[:8],
            "name": title,
            "description": str((bubble or {}).get("description") or "").strip(),
            "status": "active",
            "from_idea_id": bubble_id,
            "metadata": {
                "source_space": "bubbles",
                "source_bubble_id": bubble_id,
                "source_score": (bubble or {}).get("score", 0),
            },
        }
        created = await self._request(
            "POST", "/projects", json=project_row,
            prefer="return=representation",
        )
        if not created:
            return None
        project = created[0] if isinstance(created, list) else project_row
        project_id = str(project.get("id") or project_row["id"])

        linked = await self._request(
            "PATCH", "/ideas",
            params={"id": f"eq.{bubble_id}"},
            json={
                "status": "promoted",
                "promoted_to_project_id": project_id,
            },
            prefer="return=representation",
        )
        if not linked:
            await self._request(
                "DELETE", "/projects", params={"id": f"eq.{project_id}"},
            )
            return None

        self.stats["bubbles_promoted"] = self.stats.get("bubbles_promoted", 0) + 1
        return project

    async def list_top_bubbles(
        self, *, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._request(
            "GET", "/ideas",
            params={
                "select": "id,title,score,status,parent_id",
                "parent_id": "is.null",
                "order": "title",
                "limit": str(limit),
            },
        ) or []

    async def find_bubbles_like(
        self, query: str, *, limit: int = 10,
    ) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return await self.list_top_bubbles(limit=limit)
        return await self._request(
            "GET", "/ideas",
            params={
                "select": "id,title,score,status",
                "title": f"ilike.*{q}*",
                "parent_id": "is.null",
                "limit": str(limit),
            },
        ) or []

    async def update_idea(
        self, idea_id: str, fields: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """PATCH an ideas row (whitelist-checked)."""
        nid = (idea_id or "").strip()
        if not nid or not isinstance(fields, dict) or not fields:
            return None
        allowed = {"title", "description", "status", "score",
                   "tags", "metadata", "parent_id"}
        patch = {k: v for k, v in fields.items() if k in allowed}
        if not patch:
            return None
        result = await self._request(
            "PATCH", "/ideas",
            params={"id": f"eq.{nid}"},
            json=patch, prefer="return=representation",
        )
        return (result[0] if isinstance(result, list) and result else True) \
            if result else None

    async def delete_idea_row(self, idea_id: str) -> bool:
        nid = (idea_id or "").strip()
        if not nid:
            return False
        ok = await self._request(
            "DELETE", "/ideas", params={"id": f"eq.{nid}"},
        )
        return ok is not None and ok is not False

    async def create_project_from_idea(
        self, idea: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Create the canonical project row for an idea/bubble."""
        idea_id = str(idea.get("id") or "").strip()
        name = str(idea.get("title") or "").strip()
        if not idea_id or not name:
            return None
        existing = await self._request(
            "GET", "/projects",
            params={"select": "*", "from_idea_id": f"eq.{idea_id}", "limit": "1"},
        )
        if existing:
            return existing[0]
        row = {
            "id": uuid.uuid4().hex,
            "name": name,
            "description": str(idea.get("description") or ""),
            "status": "active",
            "from_idea_id": idea_id,
            "progress": 0.0,
            "metadata": {"source": "brain", "source_space": "ideas"},
            "generation_status": "pending",
        }
        result = await self._request(
            "POST", "/projects", json=row, prefer="return=representation",
        )
        return result[0] if isinstance(result, list) and result else None

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        pid = (project_id or "").strip()
        if not pid:
            return None
        rows = await self._request(
            "GET", "/projects",
            params={"select": "*", "id": f"eq.{pid}", "limit": "1"},
        )
        return rows[0] if rows else None

    async def mark_idea_promoted(self, idea_id: str, project_id: str) -> bool:
        result = await self._request(
            "PATCH", "/ideas", params={"id": f"eq.{idea_id}"},
            json={"promoted_to_project_id": project_id, "status": "promoted"},
            prefer="return=representation",
        )
        return bool(result)

    async def bubble_node_stats(
        self, bubble_id: str,
    ) -> Dict[str, Any]:
        """Count + node-type breakdown + edge count for a bubble."""
        nodes = await self.list_canvas_nodes_in_bubble(bubble_id, limit=1000)
        full: List[Dict[str, Any]] = []
        for n in nodes[:1000]:
            full.append(n)
        types: Dict[str, int] = {}
        for n in full:
            nt = n.get("node_type") or "note"
            types[nt] = types.get(nt, 0) + 1
        edges = await self.list_edges(limit=1000)
        node_ids = {n["id"] for n in full}
        edge_ct = sum(
            1 for e in edges
            if e.get("from_node_id") in node_ids
            or e.get("to_node_id") in node_ids
        )
        return {
            "node_count": len(full),
            "by_type": types,
            "edge_count": edge_ct,
        }

    async def find_node_by_title(
        self, title: str, *, bubble_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve a single canvas node by title, optionally scoped to a
        bubble. Returns the full row."""
        t = (title or "").strip()
        if not t:
            return None
        params = {"select": "*", "title": f"ilike.{t}", "limit": "1"}
        if bubble_id:
            params["linked_idea_id"] = f"eq.{bubble_id}"
        hits = await self._request("GET", "/canvas_nodes", params=params)
        if hits:
            return hits[0]
        # fall back to substring
        params["title"] = f"ilike.*{t}*"
        hits = await self._request("GET", "/canvas_nodes", params=params)
        return hits[0] if hits else None

    async def delete_canvas_node(self, node_id: str) -> bool:
        nid = (node_id or "").strip()
        if not nid:
            return False
        # remove dangling edges first
        await self._request(
            "DELETE", "/canvas_edges",
            params={"from_node_id": f"eq.{nid}"},
        )
        await self._request(
            "DELETE", "/canvas_edges",
            params={"to_node_id": f"eq.{nid}"},
        )
        ok = await self._request(
            "DELETE", "/canvas_nodes", params={"id": f"eq.{nid}"},
        )
        return ok is not None and ok is not False

    async def format_canvas_node(
        self, node_id: str, fmt: str,
    ) -> Optional[Dict[str, Any]]:
        """Set a node's format_schema.type + last_formatted. The renderer
        re-renders on the realtime UPDATE. Content stays; the visual
        format flips. Stores the previous content_json for revert."""
        node = await self.get_canvas_node(node_id)
        if node is None:
            return None
        prev = node.get("content_json") or {"text": node.get("content", ""),
                                            "type": node.get("node_type", "note")}
        import time as _t
        patch = {
            "format_schema": {"type": fmt},
            "content_json": {"type": fmt, "title": node.get("title", ""),
                             "text": node.get("content", "")},
            "previous_content_json": prev,
            "last_formatted": __import__("datetime").datetime.utcnow()
            .isoformat() + "+00:00",
        }
        result = await self._request(
            "PATCH", "/canvas_nodes",
            params={"id": f"eq.{node_id}"},
            json=patch, prefer="return=representation",
        )
        return (result[0] if isinstance(result, list) and result else True) \
            if result else None
