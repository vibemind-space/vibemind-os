"""Phase 10.2 — Self-Model for Decision-Making (intent → capability prior).

NOTE: This is distinct from the V2 `self_model.py` (P6.76-78) which is
a domain/capability tracking system on a different schema. This module
is purely about Brain's belief "for intents like X, I trust capability Y
at confidence Z" — embedded over intent-text in `brain-self`.

Stored in `brain-self` Qdrant collection. Indexed semantically on intent
text so retrieval is fuzzy.

Schema of a self_trait:
  external_id   "self::<sha256(intent_pattern + '|' + capability)[:16]>"
  node_type     "self_trait"
  content       "When asked: {intent_pattern}\nI use: {capability}"
  payload:
    intent_pattern   Representative intent text
    capability       Single capability id ("openfang:brain-coder", "bubble_create", ...)
    n_observations   int
    n_success        int
    n_failure        int
    confidence       Bayesian success-rate w/ Beta(2,2) prior
    avg_reward       EMA of explicit user-rewards
    last_updated     unix-ts
    last_plan_id     str

Public API:
  prior(intent_text, kg, k=8)
      -> {capabilities, best_capability, best_confidence}
  update(intent_text, capability, success, reward, plan_id, kg)
      -> trait dict
  snapshot(kg, limit=200) -> list[trait]
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_PRIOR_ALPHA = 2.0
_PRIOR_BETA = 2.0
_REWARD_ALPHA = 0.3   # EMA factor


def _trait_id(intent_pattern: str, capability: str) -> str:
    h = hashlib.sha256(f"{intent_pattern}|{capability}".encode("utf-8")).hexdigest()[:16]
    return f"self::{h}"


def _bayesian_confidence(n_success: int, n_failure: int) -> float:
    a = _PRIOR_ALPHA + n_success
    b = _PRIOR_BETA + n_failure
    return a / (a + b)


def update(
    intent_text: str,
    capability: str,
    success: bool,
    reward: Optional[float],
    plan_id: Optional[str],
    kg: Any,
) -> Optional[Dict[str, Any]]:
    """Record an observation. Idempotent on (intent_pattern, capability):
    updates the existing trait if found, else creates new one."""
    if kg is None or not getattr(kg, "client", None):
        return None
    if not capability or not (intent_text or "").strip():
        return None

    trait_ext_id = _trait_id(intent_text, capability)
    existing = _get_trait(kg, trait_ext_id)

    if existing:
        n_obs = int(existing.get("n_observations", 0)) + 1
        n_success = int(existing.get("n_success", 0)) + (1 if success else 0)
        n_failure = int(existing.get("n_failure", 0)) + (0 if success else 1)
        prev_reward = float(existing.get("avg_reward", 0.0))
    else:
        n_obs = 1
        n_success = 1 if success else 0
        n_failure = 0 if success else 1
        prev_reward = 0.0

    new_reward = prev_reward
    if reward is not None:
        new_reward = (1 - _REWARD_ALPHA) * prev_reward + _REWARD_ALPHA * float(reward)

    confidence = _bayesian_confidence(n_success, n_failure)

    payload = {
        "intent_pattern": intent_text,
        "capability": capability,
        "n_observations": n_obs,
        "n_success": n_success,
        "n_failure": n_failure,
        "confidence": round(confidence, 4),
        "avg_reward": round(new_reward, 4),
        "last_updated": int(time.time()),
        "last_plan_id": plan_id or "",
    }

    content_blob = f"When asked: {intent_text}\nI use: {capability}"

    try:
        kg._upsert_point(
            external_id=trait_ext_id,
            node_type="self_trait",
            text=content_blob,
            payload_extra=payload,
        )
        return payload
    except Exception as e:
        logger.warning(f"[self_prior] update failed: {e}")
        return None


def _get_trait(kg: Any, external_id: str) -> Optional[Dict[str, Any]]:
    """Direct point lookup by external_id-derived UUID."""
    try:
        from .qdrant_kg import _point_id  # type: ignore
        point_uuid = _point_id(external_id)
    except Exception:
        return _search_trait_by_ext(kg, external_id)

    try:
        recs = kg.client.retrieve(
            collection_name="brain-self",
            ids=[point_uuid],
            with_payload=True,
            with_vectors=False,
        )
        if recs:
            return dict(recs[0].payload or {})
    except Exception as e:
        logger.debug(f"[self_prior] retrieve failed: {e}")
    return None


def _search_trait_by_ext(kg: Any, external_id: str) -> Optional[Dict[str, Any]]:
    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        flt = Filter(must=[FieldCondition(
            key="external_id", match=MatchValue(value=external_id)
        )])
        recs, _ = kg.client.scroll(
            collection_name="brain-self",
            scroll_filter=flt,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if recs:
            return dict(recs[0].payload or {})
    except Exception:
        pass
    return None


def prior(intent_text: str, kg: Any, k: int = 8) -> Dict[str, Any]:
    """For a new intent, retrieve top-k semantically similar traits.
    Returns {"capabilities": [...], "best_capability": str|None, "best_confidence": float}."""
    empty = {"capabilities": [], "best_capability": None, "best_confidence": 0.0}
    if kg is None or not getattr(kg, "client", None) or not (intent_text or "").strip():
        return empty

    try:
        hits = kg.search(
            query=intent_text,
            node_type="self_trait",
            collection="self",
            limit=k,
            score_threshold=0.40,
        )
    except Exception as e:
        logger.debug(f"[self_prior] prior search failed: {e}")
        return empty

    rows: List[Dict[str, Any]] = []
    for h in hits or []:
        p = h.get("payload") or {}
        rows.append({
            "capability": p.get("capability"),
            "confidence": float(p.get("confidence", 0.5)),
            "n": int(p.get("n_observations", 0)),
            "avg_reward": float(p.get("avg_reward", 0.0)),
            "score": float(h.get("score", 0.0)),
            "intent_pattern": (p.get("intent_pattern") or "")[:120],
        })

    # Rank: confidence × similarity × low-n penalty
    def _rank(r: Dict[str, Any]) -> float:
        n_factor = min(1.0, r["n"] / 5.0)
        return r["confidence"] * r["score"] * (0.5 + 0.5 * n_factor)

    rows.sort(key=_rank, reverse=True)
    if rows:
        best = rows[0]
        return {
            "capabilities": rows,
            "best_capability": best["capability"],
            "best_confidence": best["confidence"],
        }
    return empty


def format_for_prompt(prior_data: Dict[str, Any]) -> str:
    """Compact prompt-block for the planner."""
    caps = prior_data.get("capabilities") or []
    if not caps:
        return ""
    lines = ["## My self-knowledge (capabilities I've used for similar intents)"]
    for c in caps[:6]:
        cap = c.get("capability", "?")
        conf = c.get("confidence", 0.5)
        n = c.get("n", 0)
        rw = c.get("avg_reward", 0.0)
        marker = "★" if conf >= 0.7 else ("·" if conf >= 0.4 else "✗")
        lines.append(
            f"- {marker} {cap}  confidence={conf:.2f}  n={n}  avg_reward={rw:+.2f}"
        )
    return "\n".join(lines)


def snapshot(kg: Any, limit: int = 200) -> List[Dict[str, Any]]:
    """Full self-model dump for UI / introspection."""
    if kg is None or not getattr(kg, "client", None):
        return []
    try:
        recs, _ = kg.client.scroll(
            collection_name="brain-self",
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        logger.debug(f"[self_prior] snapshot scroll failed: {e}")
        return []

    out: List[Dict[str, Any]] = []
    for r in recs or []:
        p = dict(r.payload or {})
        if p.get("node_type") != "self_trait":
            continue
        out.append({
            "intent_pattern": p.get("intent_pattern"),
            "capability": p.get("capability"),
            "confidence": p.get("confidence"),
            "n_observations": p.get("n_observations"),
            "n_success": p.get("n_success"),
            "n_failure": p.get("n_failure"),
            "avg_reward": p.get("avg_reward"),
            "last_updated": p.get("last_updated"),
        })
    out.sort(key=lambda x: (x.get("n_observations") or 0), reverse=True)
    return out
