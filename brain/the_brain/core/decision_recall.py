"""Phase 10.1 — Decision Recall.

Brain remembers what it decided before. When a new intent arrives,
we semantic-search `brain-decisions` for past plans on similar intents
and surface them so the planner has memory of its own track record.

Schema of a decision_record (lives in `brain-decisions`):
  external_id     "decision::<plan_id>"
  node_type       "decision_record"
  content         "{intent}\n---\n{rationale}\n---\n{summary}"
  payload:
    plan_id           Multi-hop plan id
    intent            Original user intent text
    rationale         Plan rationale from Llama
    capability_chain  ["bubble_create", "openfang:brain-coder", ...]
    hops_count        int
    success_count     int (hops where ok=True)
    fail_count        int
    outcome           "success" | "partial" | "failure"
    reward            float in [-1, 1]  — explicit user feedback if any
    duration_ms       Plan wall-clock
    created_at        unix-ts

Public API:
  record(plan_id, intent, plan, hop_results, outcome, reward, kg) -> id
  recall(intent_text, kg, k=5, min_score=0.45) -> List[Dict]

Search ranks by Qwen-cosine on intent text. Returns enriched records
with success_rate computed for downstream prompt-injection.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _summarize(plan: Any, hop_results: List[Any]) -> str:
    """Compact human-readable summary for recall display + embedding."""
    parts = []
    for hr in hop_results or []:
        step_id = getattr(hr, "step_id", None) or (hr.get("step_id") if isinstance(hr, dict) else None)
        ok = getattr(hr, "ok", None) if not isinstance(hr, dict) else hr.get("ok")
        cap = getattr(hr, "capability", None) if not isinstance(hr, dict) else hr.get("capability")
        ok_str = "✓" if ok else ("✗" if ok is False else "?")
        parts.append(f"  [{ok_str}] {step_id} {cap or ''}".strip())
    return "\n".join(parts) if parts else "(no hops)"


def record(
    plan_id: str,
    intent: str,
    plan: Any,
    hop_results: List[Any],
    outcome: str,
    reward: Optional[float],
    kg: Any,
    duration_ms: Optional[int] = None,
) -> Optional[str]:
    """Persist a finished plan as a recallable decision_record.

    Best-effort: failures are logged and swallowed so the executor
    never breaks because of memory-write hiccups.
    """
    if kg is None or not getattr(kg, "client", None):
        logger.debug("[recall] kg unavailable, skipping record")
        return None

    try:
        rationale = (
            getattr(plan, "rationale", None)
            or (plan.get("rationale") if isinstance(plan, dict) else "")
            or ""
        )
        hops = (
            getattr(plan, "hops", None)
            or (plan.get("hops") if isinstance(plan, dict) else [])
            or []
        )
        success_count = 0
        fail_count = 0
        capability_chain: List[str] = []
        for hr in hop_results or []:
            ok = getattr(hr, "ok", None) if not isinstance(hr, dict) else hr.get("ok")
            cap = getattr(hr, "capability", None) if not isinstance(hr, dict) else hr.get("capability")
            if ok is True:
                success_count += 1
            elif ok is False:
                fail_count += 1
            if cap:
                capability_chain.append(str(cap))

        summary = _summarize(plan, hop_results)
        content_blob = f"{intent}\n---rationale---\n{rationale}\n---hops---\n{summary}"

        payload = {
            "plan_id": plan_id,
            "intent": intent,
            "rationale": rationale,
            "capability_chain": capability_chain,
            "hops_count": len(hops),
            "success_count": success_count,
            "fail_count": fail_count,
            "outcome": outcome,
            "reward": float(reward) if reward is not None else 0.0,
            "duration_ms": int(duration_ms) if duration_ms else 0,
            "summary": summary,
            "created_at": int(time.time()),
        }

        external_id = f"decision::{plan_id}"
        return kg._upsert_point(
            external_id=external_id,
            node_type="decision_record",
            text=content_blob,
            payload_extra=payload,
        )
    except Exception as e:
        logger.warning(f"[recall] record failed: {e}")
        return None


def recall(
    intent_text: str,
    kg: Any,
    k: int = 5,
    min_score: float = 0.45,
) -> List[Dict[str, Any]]:
    """Find past decisions on similar intents. Returns list of dicts:
        {plan_id, intent, capability_chain, outcome, reward,
         success_rate, age_seconds, score}
    sorted by relevance score desc.
    """
    if kg is None or not getattr(kg, "client", None) or not (intent_text or "").strip():
        return []

    try:
        hits = kg.search(
            query=intent_text,
            node_type="decision_record",
            collection="decisions",
            limit=k,
            score_threshold=min_score,
        )
    except Exception as e:
        logger.debug(f"[recall] search failed: {e}")
        return []

    out: List[Dict[str, Any]] = []
    now = time.time()
    for h in hits or []:
        p = h.get("payload") or {}
        sc = p.get("success_count", 0) or 0
        fc = p.get("fail_count", 0) or 0
        total = max(1, sc + fc)
        success_rate = sc / total
        out.append({
            "plan_id": p.get("plan_id"),
            "intent": p.get("intent"),
            "rationale": (p.get("rationale") or "")[:240],
            "capability_chain": p.get("capability_chain", []),
            "outcome": p.get("outcome"),
            "reward": p.get("reward", 0.0),
            "success_rate": round(success_rate, 2),
            "hops_count": p.get("hops_count", 0),
            "age_seconds": int(now - (p.get("created_at") or now)),
            "score": float(h.get("score", 0.0)),
        })
    return out


def format_for_prompt(recalled: List[Dict[str, Any]]) -> str:
    """Render recall hits as a compact prompt-block for the planner.
    Returns empty string if no useful history."""
    if not recalled:
        return ""
    lines = ["## Past similar decisions (most relevant first)"]
    for r in recalled[:5]:
        age_h = r.get("age_seconds", 0) // 3600
        outcome = r.get("outcome", "?")
        sr = r.get("success_rate", 0)
        chain = " → ".join((r.get("capability_chain") or [])[:5]) or "(no chain)"
        intent = (r.get("intent") or "")[:120]
        lines.append(
            f"- [{outcome} sr={sr} {age_h}h ago] \"{intent}\"\n"
            f"  used: {chain}"
        )
    return "\n".join(lines)
