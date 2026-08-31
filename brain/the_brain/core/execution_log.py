"""Execution Log — RAG-queryable trace of what the system actually did (Baustein D.2).

The multihop executor already writes an append-only audit trail to
`multihop_history.jsonl`. This module mirrors a *summary per step* into a Qdrant
collection (`brain-execution-log`, node_type=exec_step) so the execution history
is semantically searchable AND carries the honest **diff** between what a tool
*claimed* and what the world actually *showed* (from Baustein D.1).

Why a separate collection (Variante B): JSONL stays the crash-safe audit truth;
this is an additive RAG index. Flag-gated by EXECUTION_LOG_ENABLED — does nothing
unless the collection is registered, so existing deployments are unaffected.

Each record:
  { node_type: exec_step, plan_id, hop_k, trace_id, intent, stage,
    summary (embedded RAG text),
    claimed_ok, verified (True|False|None), diff (MATCH|MISMATCH|UNVERIFIED),
    capability, source (planner|executor|validator), reason, created_at }

The `diff` field is the queryable heart: ask "which actions claimed success but
weren't verified?" via a payload filter, or search the summaries semantically.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


EXECUTION_LOG_ENABLED = _flag("EXECUTION_LOG_ENABLED")

MATCH = "MATCH"
MISMATCH = "MISMATCH"
UNVERIFIED = "UNVERIFIED"


def compute_diff(claimed_ok: Optional[bool], verified: Optional[bool]) -> str:
    """The claimed-vs-verified differential.

    verified is None      → UNVERIFIED (world not observed)
    claimed == verified    → MATCH      (tool told the truth)
    claimed != verified    → MISMATCH   (tool lied / broke silently)
    """
    if verified is None:
        return UNVERIFIED
    if bool(claimed_ok) == bool(verified):
        return MATCH
    return MISMATCH


def _summarize(intent: str, capability: str, claimed_ok: Optional[bool],
               verified: Optional[bool], diff: str, reason: str) -> str:
    """Compact, human/RAG-readable one-liner for the step."""
    claim = "ok" if claimed_ok else "failed" if claimed_ok is not None else "?"
    vw = ("verified" if verified is True else
          "refuted" if verified is False else "unverified")
    base = f"[{diff}] {capability or 'step'} for '{intent[:80]}' — claimed {claim}, world {vw}"
    if reason:
        base += f" ({reason[:100]})"
    return base


class ExecutionLog:
    """Writes exec-step summaries into the brain-execution-log collection.

    Holds a reference to the QdrantKG instance and reuses its embedder/client
    via `_upsert_point`. All writes are best-effort and never raise.
    """

    def __init__(self, kg: Any):
        self._kg = kg
        self.stats = {"written": 0, "errors": 0, "by_diff": {}}

    @property
    def enabled(self) -> bool:
        return EXECUTION_LOG_ENABLED and self._kg is not None

    def record_step(
        self,
        *,
        plan_id: str,
        hop_k: Optional[int],
        intent: str,
        stage: str = "exec",
        capability: str = "",
        source: str = "executor",
        claimed_ok: Optional[bool] = None,
        verified: Optional[bool] = None,
        verify_signal: Optional[Dict[str, Any]] = None,
        reason: str = "",
        trace_id: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Write one execution-trace step. Returns point id or None."""
        if not self.enabled:
            return None
        try:
            from core.qdrant_kg import NT_EXEC_STEP
            diff = compute_diff(claimed_ok, verified)
            summary = _summarize(intent, capability, claimed_ok, verified, diff, reason)
            ext_id = f"{plan_id}:{hop_k if hop_k is not None else stage}:{stage}:{int(time.time()*1000)}"
            payload = {
                "plan_id": plan_id,
                "hop_k": hop_k,
                "trace_id": trace_id,
                "intent": intent[:500],
                "stage": stage,
                "capability": capability,
                "source": source,
                "claimed_ok": claimed_ok,
                "verified": verified,
                "diff": diff,
                "verify_signal": verify_signal or {},
                "reason": reason[:500],
            }
            if extra:
                payload.update(extra)
            pid = self._kg._upsert_point(ext_id, NT_EXEC_STEP, summary, payload)
            self.stats["written"] += 1
            self.stats["by_diff"][diff] = self.stats["by_diff"].get(diff, 0) + 1
            return pid
        except Exception as e:
            self.stats["errors"] += 1
            logger.debug("[exec-log] record_step failed: %s", e)
            return None

    def search(self, query: str, *, diff: Optional[str] = None,
               source: Optional[str] = None, limit: int = 20):
        """Semantic search over exec-steps, optionally filtered by diff/source.

        Returns the KG search hits (list of {id, score, payload, ...}).
        """
        if not self.enabled:
            return []
        try:
            from core.qdrant_kg import NT_EXEC_STEP
            extra_filter = {}
            if diff:
                extra_filter["diff"] = diff
            if source:
                extra_filter["source"] = source
            return self._kg.search(
                query, node_type=NT_EXEC_STEP,
                limit=limit, payload_filter=extra_filter or None,
            )
        except Exception as e:
            logger.debug("[exec-log] search failed: %s", e)
            return []
