"""
IdeasClient — Brain side of the Ideas-Space connector (Phase O.1.B).

Talks to the local Ideas-Space HTTP wrapper (default port 5102). Pattern
mirrors MinibookClient: stateless wrapper, graceful offline-fallback,
no hard dependency on the remote service being up.

Used by:
  - web/brain_server.py (state.ideas_client)
  - web/routers/introspection.py (HTTP proxy endpoints)
  - core/auto_dispatcher.py (local-first dispatch when @vibemind_ideas
    is mentioned)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    HAS_REQUESTS = False
    logger.warning("requests not installed — IdeasClient will operate in stub mode")


class IdeasClient:
    """REST client for the local Ideas-Space HTTP wrapper.

    All methods degrade gracefully if Ideas is unreachable; callers should
    inspect `is_online` and the `ok` field on returned dicts.

    Parameters
    ----------
    base_url: str
        Default ``http://127.0.0.1:5102`` or env ``IDEAS_URL``.
    api_key: str
        Optional ``X-API-Key`` header value (env ``IDEAS_API_KEY``).
    timeout: float
        HTTP timeout per call. Search + expand override this.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = (
            base_url or os.environ.get("IDEAS_URL", "http://127.0.0.1:5102")
        ).rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get("IDEAS_API_KEY", "")
        self._timeout = timeout
        self._online = False
        self._last_check = 0.0
        self._idea_count: Optional[int] = None

    # ── Properties ────────────────────────────────────────────────────

    @property
    def is_online(self) -> bool:
        """Whether Ideas-Space was reachable on last call."""
        return self._online

    @property
    def base_url(self) -> str:
        return self._base_url

    # ── Low-level HTTP ────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None,
             timeout: Optional[float] = None) -> Dict[str, Any]:
        if not HAS_REQUESTS:
            return {"error": "requests not installed"}
        try:
            r = requests.get(
                f"{self._base_url}{path}", params=params or {},
                headers=self._headers(),
                timeout=timeout or self._timeout,
            )
            self._online = True
            if r.status_code >= 400:
                return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
            return r.json()
        except requests.exceptions.ConnectionError:
            self._online = False
            return {"error": "ideas_offline", "url": f"{self._base_url}{path}"}
        except Exception as e:
            self._online = False
            return {"error": type(e).__name__, "detail": str(e)}

    def _post(self, path: str, payload: Dict[str, Any],
              timeout: Optional[float] = None) -> Dict[str, Any]:
        if not HAS_REQUESTS:
            return {"error": "requests not installed"}
        try:
            r = requests.post(
                f"{self._base_url}{path}", json=payload,
                headers=self._headers(),
                timeout=timeout or self._timeout,
            )
            self._online = True
            if r.status_code >= 400:
                return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
            return r.json()
        except requests.exceptions.ConnectionError:
            self._online = False
            return {"error": "ideas_offline", "url": f"{self._base_url}{path}"}
        except Exception as e:
            self._online = False
            return {"error": type(e).__name__, "detail": str(e)}

    # ── Public API ────────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        """Returns Ideas health snapshot. Updates ``is_online`` + count."""
        h = self._get("/api/health", timeout=3)
        if isinstance(h, dict) and h.get("status") == "alive":
            self._idea_count = h.get("idea_count")
        self._last_check = time.time()
        return h

    def list_ideas(
        self,
        limit: int = 20,
        query: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if parent_id is not None:
            params["parent_id"] = parent_id
        return self._get("/api/ideas", params=params)

    def create_idea(
        self,
        title: str,
        content: str = "",
        tags: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        source: str = "brain",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
            "source": source,
        }
        if tags:
            payload["tags"] = tags
        if parent_id is not None:
            payload["parent_id"] = parent_id
        return self._post("/api/ideas", payload)

    def search_ideas(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.3,
    ) -> Dict[str, Any]:
        return self._post(
            "/api/ideas/search",
            {"query": query, "limit": limit, "min_score": min_score},
            timeout=30,
        )

    def expand_idea(
        self,
        idea_id: str,
        prompt: Optional[str] = None,
        count: int = 3,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"count": count}
        if prompt:
            payload["prompt"] = prompt
        return self._post(
            f"/api/ideas/{idea_id}/expand", payload, timeout=120,
        )

    # ── Bubbles (Block 1) ─────────────────────────────────────────────

    def list_bubbles(self, limit: int = 50) -> Dict[str, Any]:
        # Phase 11.U.J: HTTP path first, then Supabase fallback when
        # Ideas-HTTP :5102 is offline. Keeps the Brain Dashboard alive
        # even if the legacy SQLite-fronted service hasn't been started.
        result = self._get("/api/bubbles", params={"limit": limit})
        if isinstance(result, dict) and result.get("error") == "ideas_offline":
            sb = self._supabase_list_bubbles(limit=limit)
            if sb is not None:
                return sb
        return result

    # ── Supabase fallback (Phase 11.U.J) ──────────────────────────────────
    # When the Ideas-HTTP wrapper on :5102 is down, read the same data
    # straight from Supabase REST. Keeps the UI alive even if the legacy
    # SQLite-fronted service hasn't been started. Uses requests (sync) —
    # SupabaseIdeasClient is async and would need a fresh loop here.

    def _supabase_base(self) -> Optional[str]:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        return url or None

    def _supabase_headers(self) -> Optional[Dict[str, str]]:
        # Two resolution paths: direct env var, or docker secret file via
        # the *_FILE convention (compose mounts /run/secrets/<name> and
        # sets SUPABASE_ANON_KEY_FILE to that path).
        key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
        if not key:
            key_file = os.environ.get("SUPABASE_ANON_KEY_FILE", "").strip()
            if key_file:
                try:
                    with open(key_file, "r", encoding="utf-8") as f:
                        key = f.read().strip()
                except OSError:
                    key = ""
        if not key:
            return None
        h = {"apikey": key, "Content-Type": "application/json"}
        # Bearer only for real JWTs (3 dot-separated parts). Local Supabase
        # rejects "Bearer anon" with 401 PGRST301 — apikey header alone is
        # enough for anon RLS. Same logic as SupabaseIdeasClient._headers.
        if key.count(".") == 2:
            h["Authorization"] = f"Bearer {key}"
        return h

    def _supabase_list_bubbles(self, *, limit: int = 50) -> Optional[Dict[str, Any]]:
        if not HAS_REQUESTS:
            return None
        base = self._supabase_base()
        headers = self._supabase_headers()
        if not base or not headers:
            return None
        try:
            r = requests.get(
                f"{base}/rest/v1/ideas",
                params={
                    "select": "id,title,parent_id,score,status",
                    "parent_id": "is.null",
                    "limit": str(limit),
                },
                headers=headers,
                timeout=5,
            )
            if r.status_code >= 400:
                return None
            rows = r.json() or []
            return {"bubbles": rows, "count": len(rows), "source": "supabase"}
        except Exception:
            return None

    def _supabase_state(self) -> Optional[Dict[str, Any]]:
        """Approximate the Ideas-HTTP /api/state shape from Supabase counts."""
        if not HAS_REQUESTS:
            return None
        base = self._supabase_base()
        headers = self._supabase_headers()
        if not base or not headers:
            return None
        try:
            counts: Dict[str, int] = {}
            for table in ("ideas", "canvas_nodes", "canvas_edges", "projects"):
                rr = requests.head(
                    f"{base}/rest/v1/{table}",
                    headers={**headers, "Prefer": "count=exact"},
                    timeout=5,
                )
                # PostgREST returns count in Content-Range: "0-N/<total>"
                cr = rr.headers.get("Content-Range", "")
                total = cr.rsplit("/", 1)[-1] if "/" in cr else ""
                try:
                    counts[table] = int(total) if total.isdigit() else 0
                except Exception:
                    counts[table] = 0
            return {
                "source": "supabase",
                "counts": counts,
                "active_bubble": None,  # not tracked in Supabase
                "stale_ideas": 0,       # not computed here
            }
        except Exception:
            return None

    def create_bubble(
        self,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        source: str = "brain",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "title": title,
            "description": description,
            "source": source,
        }
        if tags:
            payload["tags"] = tags
        return self._post("/api/bubbles", payload)

    def delete_bubble(self, bubble_id: str, force: bool = False) -> Dict[str, Any]:
        if not HAS_REQUESTS:
            return {"error": "requests not installed"}
        try:
            r = requests.delete(
                f"{self._base_url}/api/bubbles/{bubble_id}",
                params={"force": "true"} if force else {},
                headers=self._headers(),
                timeout=self._timeout,
            )
            self._online = True
            if r.status_code >= 400:
                return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
            return r.json()
        except requests.exceptions.ConnectionError:
            self._online = False
            return {"error": "ideas_offline"}
        except Exception as e:
            self._online = False
            return {"error": type(e).__name__, "detail": str(e)}

    def move_idea(
        self, idea_id: str, parent_id: Optional[str],
    ) -> Dict[str, Any]:
        """Move an idea to a different parent bubble. parent_id=None
        promotes to top-level."""
        return self._post(
            f"/api/ideas/{idea_id}/move",
            {"parent_id": parent_id if parent_id is not None else ""},
        )

    # ── Q.5 extensions ────────────────────────────────────────────────

    def kg_stats(self) -> Dict[str, Any]:
        """Stats of the ideas-kg Qdrant collection."""
        return self._get("/api/kg/stats")

    def kg_search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.3,
        node_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Semantic search directly against the Qdrant ideas-kg index
        (faster than `/api/ideas/search` which falls back to substring)."""
        payload: Dict[str, Any] = {
            "query": query, "limit": limit, "threshold": threshold,
        }
        if node_type:
            payload["node_type"] = node_type
        return self._post("/api/kg/search", payload, timeout=30)

    def state(self) -> Dict[str, Any]:
        """Mini-Brain state snapshot (counts, active bubbles, stale ideas)."""
        result = self._get("/api/state")
        if isinstance(result, dict) and result.get("error") == "ideas_offline":
            sb = self._supabase_state()
            if sb is not None:
                return sb
        return result

    def sync_stats(self) -> Dict[str, Any]:
        return self._get("/api/sync/stats")

    def sync_full(self) -> Dict[str, Any]:
        """Trigger immediate full SQLite -> ideas-kg resync (blocking)."""
        return self._post("/api/sync/full", {}, timeout=300)

    def consolidate_now(self) -> Dict[str, Any]:
        return self._post("/api/consolidate", {}, timeout=120)

    def consolidate_suggestions(
        self, status: str = "pending", limit: int = 20,
    ) -> Dict[str, Any]:
        return self._get(
            "/api/consolidate/suggestions",
            params={"status": status, "limit": limit},
        )

    def consolidate_accept(self, suggestion_id: str) -> Dict[str, Any]:
        return self._post(
            f"/api/consolidate/suggestions/{suggestion_id}/accept", {},
        )

    def consolidate_reject(self, suggestion_id: str) -> Dict[str, Any]:
        return self._post(
            f"/api/consolidate/suggestions/{suggestion_id}/reject", {},
        )

    def record_reward(
        self, idea_id: str, delta: float, reason: str = "",
    ) -> Dict[str, Any]:
        """Bump the score of an idea (positive or negative).

        Implementation: PATCH-like via update_idea endpoint when added,
        or — for now — direct SQLite UPDATE. We do this through the
        ideas HTTP wrapper to keep the SoT model intact.
        """
        return self._post(
            f"/api/ideas/{idea_id}/reward",
            {"delta": float(delta), "reason": reason},
            timeout=10,
        )
