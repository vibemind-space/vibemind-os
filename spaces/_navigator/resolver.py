"""3-layer space resolver: keyword → embedding (Qwen3) → LLM tiebreaker.

Layer 1 (registry.resolve_alias): instant, deterministic, exact alias/label.
Layer 2 (this module): cosine-similarity over Qwen3-Embedding-0.6B vectors
        of each space's `description` + `use_when` + aliases blob.
Layer 3 (llm_config.chat_json): only when top-2 embed-scores are within
        0.05 of each other — disambiguates with one cheap LLM call.

Lazy import of sentence-transformers / numpy so the MCP can boot even when
torch isn't installed; `space_resolve` then falls through to layer 1 only.
"""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from . import llm_config
from .registry import (
    SPACE_NAMES,
    SPACES,
    embedding_corpus,
    resolve_alias,
    search_aliases,
)

_EMBED_MODEL_NAME = os.environ.get(
    "NAVIGATOR_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B"
)
_LLM_TIEBREAK_DELTA = float(os.environ.get("NAVIGATOR_LLM_TIEBREAK_DELTA", "0.05"))
_CACHE_SIZE = 256

_embed_lock = threading.Lock()
_embed_state: Dict[str, Any] = {
    "ready": False,
    "tried": False,
    "model": None,
    "matrix": None,
    "ids": [],
    "error": None,
}

_query_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_cache_lock = threading.Lock()


# ──────────────────────────────────────────────────────────────────────
# Embedding layer
# ──────────────────────────────────────────────────────────────────────

def _ensure_embed_index() -> bool:
    """Build the Qwen3 embedding index once. Returns True on success."""
    with _embed_lock:
        if _embed_state["ready"]:
            return True
        if _embed_state["tried"]:
            return False
        _embed_state["tried"] = True
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(_EMBED_MODEL_NAME)
            corpora = [embedding_corpus(sid) for sid in SPACE_NAMES]
            vecs = model.encode(
                corpora,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            _embed_state["model"] = model
            _embed_state["matrix"] = np.asarray(vecs, dtype="float32")
            _embed_state["ids"] = list(SPACE_NAMES)
            _embed_state["ready"] = True
            _embed_state["np"] = np
            return True
        except Exception as exc:  # missing deps, model download fail, OOM
            _embed_state["error"] = repr(exc)
            return False


def _embed_query(query: str) -> Optional[List[Tuple[str, float]]]:
    if not _ensure_embed_index():
        return None
    try:
        np = _embed_state["np"]
        model = _embed_state["model"]
        matrix = _embed_state["matrix"]
        ids = _embed_state["ids"]
        qvec = model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )
        qvec = np.asarray(qvec, dtype="float32")[0]
        sims = matrix @ qvec
        ranked = sorted(
            zip(ids, sims.tolist()), key=lambda kv: kv[1], reverse=True
        )
        return ranked
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# LLM tiebreaker
# ──────────────────────────────────────────────────────────────────────

_LLM_SYSTEM = (
    "You are a routing function for the VibeMind multiverse. "
    "Given a user query and a list of candidate spaces (each with description "
    "and 'use_when'), pick the single best space-id. "
    'Reply ONLY as JSON: {"space": "<id>", "reasoning": "<short>"}'
)


def _llm_pick(query: str, candidates: List[str]) -> Optional[Dict[str, Any]]:
    if not llm_config.is_available():
        return None
    catalog = []
    for sid in candidates:
        m = SPACES[sid]
        catalog.append({
            "id": sid,
            "label": m["label"],
            "description": m["description"],
            "use_when": m["use_when"],
        })
    user = json.dumps({"query": query, "candidates": catalog}, ensure_ascii=False)
    out = llm_config.chat_json(_LLM_SYSTEM, user)
    if not out:
        return None
    pick = out.get("space")
    if pick not in SPACES:
        return None
    return {
        "space": pick,
        "reasoning": str(out.get("reasoning", ""))[:200],
    }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        if key in _query_cache:
            _query_cache.move_to_end(key)
            return dict(_query_cache[key])
    return None


def _cache_put(key: str, value: Dict[str, Any]) -> None:
    with _cache_lock:
        _query_cache[key] = dict(value)
        _query_cache.move_to_end(key)
        while len(_query_cache) > _CACHE_SIZE:
            _query_cache.popitem(last=False)


def resolve(query: str, *, top_k: int = 3) -> Dict[str, Any]:
    """Smart 3-layer resolution. Always returns a dict; never raises."""
    q = (query or "").strip()
    if not q:
        return {
            "ok": False,
            "message": "empty query",
            "space": None,
            "candidates": [],
            "layer": "none",
        }

    cache_key = f"{top_k}::{q.lower()}"
    cached = _cache_get(cache_key)
    if cached:
        cached["cache_hit"] = True
        return cached

    # Layer 1 — exact alias / label / id
    direct = resolve_alias(q)
    if direct:
        result = {
            "ok": True,
            "space": direct,
            "confidence": 1.0,
            "candidates": [{"space": direct, "score": 1.0}],
            "layer": "alias",
            "reasoning": f"exact match for '{q}'",
        }
        _cache_put(cache_key, result)
        return result

    # Layer 1b — fuzzy alias (substring)
    fuzzy = search_aliases(q)

    # Layer 2 — embedding
    embed_ranked = _embed_query(q)
    if embed_ranked:
        top = embed_ranked[:top_k]
        best_id, best_score = top[0]
        candidates = [{"space": sid, "score": round(s, 4)} for sid, s in top]

        # tiebreaker: top-1 vs top-2 close → ask LLM
        needs_tiebreak = (
            len(top) >= 2
            and (top[0][1] - top[1][1]) < _LLM_TIEBREAK_DELTA
        )

        if needs_tiebreak:
            tiebreak_pool = [sid for sid, _ in top]
            picked = _llm_pick(q, tiebreak_pool)
            if picked:
                result = {
                    "ok": True,
                    "space": picked["space"],
                    "confidence": round(best_score, 4),
                    "candidates": candidates,
                    "layer": "llm",
                    "reasoning": picked["reasoning"],
                }
                _cache_put(cache_key, result)
                return result

        result = {
            "ok": True,
            "space": best_id,
            "confidence": round(best_score, 4),
            "candidates": candidates,
            "layer": "embed",
            "reasoning": f"embedding cosine={best_score:.3f}",
        }
        _cache_put(cache_key, result)
        return result

    # Embedding unavailable — fall back to fuzzy alias if we have something
    if fuzzy:
        best = fuzzy[0]
        result = {
            "ok": True,
            "space": best,
            "confidence": 0.5,
            "candidates": [{"space": s, "score": 0.5} for s in fuzzy[:top_k]],
            "layer": "fuzzy",
            "reasoning": f"alias substring match (embedding unavailable: {_embed_state.get('error')})",
        }
        _cache_put(cache_key, result)
        return result

    return {
        "ok": False,
        "space": None,
        "confidence": 0.0,
        "candidates": [],
        "layer": "none",
        "message": f"could not resolve '{q}' (embedding error: {_embed_state.get('error')})",
    }


def suggest(query: str, *, top_k: int = 3) -> Dict[str, Any]:
    """Like resolve, but always returns top-k with reasoning per candidate."""
    base = resolve(query, top_k=top_k)
    enriched: List[Dict[str, Any]] = []
    for cand in base.get("candidates", []):
        sid = cand["space"]
        meta = SPACES.get(sid, {})
        enriched.append({
            "space": sid,
            "label": meta.get("label", sid),
            "score": cand.get("score"),
            "use_when": meta.get("use_when", ""),
            "capabilities": meta.get("capabilities", []),
        })
    return {
        "ok": base.get("ok", False),
        "query": query,
        "top": enriched,
        "primary": base.get("space"),
        "layer": base.get("layer"),
        "reasoning": base.get("reasoning"),
    }


def index_status() -> Dict[str, Any]:
    return {
        "embed_ready": _embed_state["ready"],
        "embed_tried": _embed_state["tried"],
        "embed_model": _EMBED_MODEL_NAME,
        "embed_error": _embed_state.get("error"),
        "llm_available": llm_config.is_available(),
        "llm_tiebreak_delta": _LLM_TIEBREAK_DELTA,
        "cache_size": len(_query_cache),
        "spaces_indexed": len(_embed_state.get("ids", [])),
    }
