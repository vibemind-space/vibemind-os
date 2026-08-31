"""Rowboat client helper for async enrichment (Schicht 6.3a).

Architecture:
    - Marketing-API does NOT block waiting for Rowboat responses.
    - n8n fires a Rowboat-chat request with a request_id we generate.
    - n8n's HTTP node has its own timeout — it returns immediately with
      whatever Rowboat sent, then n8n PATCHes the result back to marketing
      via /api/curator/rowboat_callback/{request_id}.
    - This module provides:
        - generate_request_id() — uuid4 string, used as correlation token
        - chat_async() — fire+forget HTTP POST to Rowboat, returns (request_id, ok, error)
        - extract_context() — parser for Rowboat response shapes
    - If Rowboat is unavailable, all functions degrade gracefully (return None
      or empty dict) — the reply-proposal can still be created without context.

DSGVO:
    - Rowboat is a local container, payload stays on-host
    - We send only: question + recipient-email (to enable RAG-lookup)
    - We never send the full inbound body — that's curator-private
    - Rowboat-context is stored in marketing.reply_proposals.rowboat_context
      jsonb column, included in retention (Schicht 6.6)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional


logger = logging.getLogger("marketing.rowboat_client")


# ─── Constants ─────────────────────────────────────────────────────────


_DEFAULT_BASE = "http://127.0.0.1:3100"
_DEFAULT_PROJECT_ID = "c157ade4-7e8d-4f4f-a8f7-bafbbbcc"
_DEFAULT_BEARER = "vibemind-local-key"
_DEFAULT_TIMEOUT_S = 30


# ─── Configuration ────────────────────────────────────────────────────


def _base_url() -> str:
    return os.environ.get("ROWBOAT_BASE_URL", _DEFAULT_BASE).rstrip("/")


def _project_id() -> str:
    return os.environ.get("ROWBOAT_PROJECT_ID", _DEFAULT_PROJECT_ID)


def _bearer() -> str:
    return os.environ.get("ROWBOAT_BEARER_TOKEN", _DEFAULT_BEARER)


def is_configured() -> bool:
    """Cheap config-check — usable from health endpoints."""
    return bool(_base_url() and _project_id() and _bearer())


# ─── Health probe ─────────────────────────────────────────────────────


def is_available(*, timeout_s: int = 3) -> Dict[str, Any]:
    """Returns {ok, status, latency_ms, message}."""
    if not is_configured():
        return {"ok": False, "message": "rowboat not configured (env)"}
    base = _base_url()
    t0 = time.time()
    try:
        req = urllib.request.Request(f"{base}/", method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return {"ok": True, "status": r.status,
                    "latency_ms": int((time.time() - t0) * 1000)}
    except urllib.error.HTTPError as e:
        # HTTP error response still means rowboat is reachable
        return {"ok": True, "status": e.code,
                "latency_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False,
                "message": f"{type(e).__name__}: {e}",
                "latency_ms": int((time.time() - t0) * 1000)}


# ─── Request-id generation ────────────────────────────────────────────


def generate_request_id() -> str:
    """Correlation token. Used by n8n to link rowboat callback to a proposal."""
    return f"rb-{uuid.uuid4().hex[:16]}"


# ─── Sync (fire-with-timeout) call ────────────────────────────────────


def chat_sync(question: str, *,
              context_hints: Optional[Dict[str, str]] = None,
              timeout_s: int = _DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Synchronously chat with Rowboat. n8n typically calls this directly
    (via HTTP-node) and pipes the result back. Returns:

        {ok: bool, request_id, response, raw, error?, elapsed_ms}

    NEVER raises. On any failure, returns ok=False with error message.

    DSGVO note: question + context_hints are sent verbatim to local Rowboat.
    Callers must NOT include full inbound body. Typical pattern:
        question = "What do we know about sender X who sent re: subject Y?"
        context_hints = {"from_email": "X", "subject_brief": "Y"}
    """
    if not is_configured():
        return {"ok": False, "error": "rowboat not configured",
                "elapsed_ms": 0}

    request_id = generate_request_id()
    payload = {
        "messages": [{"role": "user", "content": question}],
    }
    if context_hints:
        # Keep context hints compact — they go into the prompt-context
        payload["context"] = context_hints

    url = f"{_base_url()}/api/v1/{_project_id()}/chat"
    headers = {
        "Authorization": f"Bearer {_bearer()}",
        "Content-Type": "application/json",
        "X-Vibemind-Request-Id": request_id,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw = r.read() or b"{}"
        elapsed_ms = int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return {"ok": False, "request_id": request_id,
                "error": f"HTTP {e.code}: {body[:200].decode('utf-8', 'replace')}",
                "elapsed_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "request_id": request_id,
                "error": f"{type(e).__name__}: {e}",
                "elapsed_ms": int((time.time() - t0) * 1000)}

    try:
        parsed = json.loads(raw)
    except Exception as e:
        return {"ok": False, "request_id": request_id,
                "error": f"non-JSON rowboat response: {e}",
                "raw": raw[:500].decode("utf-8", "replace"),
                "elapsed_ms": elapsed_ms}

    return {
        "ok": True,
        "request_id": request_id,
        "response": parsed.get("response") or parsed.get("message")
                    or parsed.get("text") or "",
        "raw": parsed,
        "elapsed_ms": elapsed_ms,
    }


# ─── Context extraction (parse Rowboat response into structured fields) ──


def extract_context(rowboat_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Pull structured fields from a Rowboat raw response.

    Different Rowboat versions return different shapes; this normalizes:
        {
            "summary": str,
            "sources": [{title, url, snippet}, ...],
            "tags": [str, ...],
            "raw_response_text": str,
        }
    Missing fields are empty/None — caller should treat as best-effort.
    """
    if not isinstance(rowboat_raw, dict):
        return {"summary": "", "sources": [], "tags": [], "raw_response_text": ""}
    response_text = (
        rowboat_raw.get("response")
        or rowboat_raw.get("message")
        or rowboat_raw.get("text")
        or ""
    )
    sources = []
    raw_sources = rowboat_raw.get("sources") or rowboat_raw.get("citations") or []
    if isinstance(raw_sources, list):
        for s in raw_sources[:10]:
            if not isinstance(s, dict):
                continue
            sources.append({
                "title": (s.get("title") or s.get("name") or "")[:200],
                "url": (s.get("url") or s.get("link") or "")[:500],
                "snippet": (s.get("snippet") or s.get("content") or "")[:500],
            })
    tags = rowboat_raw.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return {
        "summary": response_text[:2000],
        "sources": sources,
        "tags": [str(t)[:50] for t in tags[:20]],
        "raw_response_text": response_text[:5000],
    }


__all__ = [
    "is_configured", "is_available",
    "generate_request_id", "chat_sync", "extract_context",
]
