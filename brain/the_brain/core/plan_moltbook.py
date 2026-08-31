"""C5 — Plan persistence in Moltbook.

Store executed/planned multi-hop plans as Moltbook entries (the brain's notebook),
so plans become linkable + searchable knowledge nuggets instead of only flat JSONL
traces. "pläne wären sinnvoll in moltbook zu speichern".

A plan -> ONE Moltbook EXPERIENCE entry:
  content  = human-readable summary (intent + hop list + outcome)
  tags     = ['plan', 'task:<task_type>']
  metadata = {plan_id, intent, task_type, trace_id, ok, hops, stored_at}

Flag PLAN_MOLTBOOK_ENABLED (default OFF -> store_plan is a no-op). Fail-safe: any
error returns None and never breaks plan execution. Torch-free (Moltbook's semantic
index falls back to hash-embeddings when sentence-transformers is unavailable).
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("brain.plan_moltbook")

ENABLED = os.environ.get("PLAN_MOLTBOOK_ENABLED", "0") == "1"
PLAN_TAG = "plan"


def plan_to_content(plan: Dict[str, Any]) -> str:
    """Human-readable one-screen summary of a plan (what goes in the entry body)."""
    intent = plan.get("intent", "") or "(no intent)"
    hops = plan.get("hops") or []
    ok = plan.get("ok")
    outcome = "ok" if ok is True else ("failed" if ok is False else "n/a")
    lines = [f"PLAN: {intent}", f"outcome: {outcome}  hops: {len(hops)}"]
    for i, h in enumerate(hops):
        cap = h.get("capability") or h.get("execution_target") or "?"
        desc = h.get("description", "")
        lines.append(f"  s{i + 1}: {cap}" + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


def store_plan(store, plan: Dict[str, Any], *, source_agent: str = "plan_executor",
               enabled: Optional[bool] = None) -> Optional[str]:
    """Persist a plan into the Moltbook store. Returns the entry id, or None."""
    on = ENABLED if enabled is None else enabled
    if not on or store is None:
        return None
    try:
        task_type = plan.get("task_type") or "general"
        meta = {
            "plan_id": plan.get("plan_id"),
            "intent": plan.get("intent"),
            "task_type": task_type,
            "trace_id": plan.get("trace_id"),
            "ok": plan.get("ok"),
            "hops": plan.get("hops") or [],
            "stored_at": time.time(),
        }
        entry = store.add_entry(
            content=plan_to_content(plan),
            source_agent=source_agent,
            entry_type="experience",
            tags=[PLAN_TAG, f"task:{task_type}"],
            confidence=0.6,
            metadata=meta,
        )
        eid = getattr(entry, "id", None)
        logger.info("[plan-moltbook] stored plan %s as entry %s", meta.get("plan_id"), eid)
        return eid
    except Exception as exc:  # fail-safe — persistence must never break execution
        logger.warning("[plan-moltbook] store failed: %s", exc)
        return None


def get_plan(store, entry_id: str) -> Optional[Dict[str, Any]]:
    """Return the stored plan metadata for an entry id (or None)."""
    try:
        e = store.get_entry(entry_id)
        return dict(e.metadata) if e is not None else None
    except Exception as exc:
        logger.debug("[plan-moltbook] get_plan failed: %s", exc)
        return None


def load_plans(store, limit: int = 50) -> List[Dict[str, Any]]:
    """All stored plans (their metadata). Iterates entries + filters by the 'plan'
    tag — independent of the tag-index, which Moltbook does NOT rebuild on
    load_from_disk (so query_by_tag would miss freshly-loaded plans)."""
    out: List[Dict[str, Any]] = []
    try:
        entries = store.get_active_entries(top_k=max(limit * 4, 200))
        for entry in entries:
            if PLAN_TAG in getattr(entry, "tags", []):
                meta = getattr(entry, "metadata", None)
                if meta:
                    out.append(dict(meta))
                    if len(out) >= limit:
                        break
    except Exception as exc:
        logger.debug("[plan-moltbook] load_plans failed: %s", exc)
    return out
