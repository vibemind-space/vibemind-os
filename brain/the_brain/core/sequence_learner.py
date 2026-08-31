"""Sequence Learner — learns which agent SEQUENCES succeed per intent (Baustein A).

The CTM/temporal router today learns the timing of a *single* tool. The agent
ORDER for a multi-hop plan is hand-written by the LLM planner (depends_on). This
module closes that gap: it watches completed plans and learns, per task_type,
which ordered capability-sequences tend to SUCCEED — then offers the best one as
a prior to the planner so it doesn't re-derive proven decompositions from scratch.

Honest by construction:
  - It only counts a sequence as successful when the plan's outcome is ok=True.
    With Baustein D's ground-truth, "ok" reflects verified reality, not claims.
  - It's frequency statistics, not a black box: `suggest()` returns the sequence
    with the best (success-weighted) score plus its support count, so the planner
    (and a human) can see WHY.

Flag-gated by SEQUENCE_LEARNER_ENABLED (default OFF). Persists a compact JSON
store so it survives restarts. All operations are best-effort and never raise
into the caller (plan execution must never be disturbed by learning).

Store shape (per task_type bucket):
  { task_type: { "<cap1>>cap2>cap3>": {"ok": int, "fail": int, "last_ts": float,
                                       "sample_intent": str} } }
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


SEQUENCE_LEARNER_ENABLED = _flag("SEQUENCE_LEARNER_ENABLED")
# Minimum successful observations before suggest() will recommend a sequence.
MIN_SUPPORT = int(os.environ.get("SEQUENCE_LEARNER_MIN_SUPPORT", "2"))
SEQ_SEP = ">"


def _extract_sequence(snapshot: Dict[str, Any]) -> List[str]:
    """Ordered list of capabilities actually executed, in dependency order.

    Uses `hops` order (already topologically arranged at plan build) and keeps
    only hops that were executed. Falls back to hop list if `executed` absent.
    """
    hops = snapshot.get("hops") or []
    executed = snapshot.get("executed") or {}
    seq: List[str] = []
    for h in hops:
        sid = h.get("step_id")
        cap = h.get("capability") or h.get("execution_target") or h.get("description", "")[:30]
        if not cap:
            continue
        # only include if it actually ran (present in executed), else include anyway
        if not executed or sid in executed:
            seq.append(str(cap))
    return seq


def _bucket_key(snapshot: Dict[str, Any]) -> str:
    """The intent bucket — prefer task_type, else a coarse intent prefix."""
    tt = snapshot.get("task_type")
    if tt:
        return str(tt)
    intent = (snapshot.get("intent") or "").strip().lower()
    # coarse bucket: first 4 words, so similar intents share a bucket
    return " ".join(intent.split()[:4]) or "unknown"


class SequenceLearner:
    """Frequency learner over (intent → successful agent sequence)."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            path = Path(__file__).resolve().parent.parent / "data" / "sequence_learner.json"
        self.path = Path(path)
        self._store: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock = threading.RLock()
        self.stats = {"observed": 0, "suggested": 0, "buckets": 0}
        self._load()

    @property
    def enabled(self) -> bool:
        return SEQUENCE_LEARNER_ENABLED

    def _load(self) -> None:
        try:
            if self.path.exists():
                self._store = json.loads(self.path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.debug("[seq-learner] load skipped: %s", e)
            self._store = {}

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._store, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("[seq-learner] persist failed: %s", e)

    # ── Learning ────────────────────────────────────────────────────────

    def observe(self, snapshot: Dict[str, Any]) -> None:
        """Update sequence stats from one completed plan snapshot. Best-effort."""
        if not self.enabled:
            return
        try:
            seq = _extract_sequence(snapshot)
            if len(seq) < 1:
                return
            bucket = _bucket_key(snapshot)
            seq_key = SEQ_SEP.join(seq)
            ok = bool(snapshot.get("ok"))
            ts = float(snapshot.get("ts") or 0.0)
            with self._lock:
                b = self._store.setdefault(bucket, {})
                entry = b.setdefault(seq_key, {"ok": 0, "fail": 0, "last_ts": 0.0,
                                               "sample_intent": ""})
                entry["ok" if ok else "fail"] += 1
                entry["last_ts"] = ts
                if not entry["sample_intent"]:
                    entry["sample_intent"] = (snapshot.get("intent") or "")[:160]
                self.stats["observed"] += 1
                self.stats["buckets"] = len(self._store)
            self._persist()
        except Exception as e:
            logger.debug("[seq-learner] observe failed: %s", e)

    # ── Suggesting ──────────────────────────────────────────────────────

    def _score(self, entry: Dict[str, Any]) -> float:
        ok, fail = entry.get("ok", 0), entry.get("fail", 0)
        total = ok + fail
        if total == 0:
            return 0.0
        # success rate weighted by log-support (more evidence → more trust)
        import math
        return (ok / total) * math.log1p(ok)

    def suggest(self, intent: str = "", task_type: str = "") -> Optional[Dict[str, Any]]:
        """Best learned sequence for an intent/task_type, or None.

        Returns {sequence: [caps], score, ok, fail, support, sample_intent, bucket}.
        """
        if not self.enabled:
            return None
        try:
            bucket = task_type or " ".join((intent or "").strip().lower().split()[:4]) or "unknown"
            with self._lock:
                b = self._store.get(bucket)
                if not b:
                    return None
                best_key, best_entry, best_score = None, None, -1.0
                for seq_key, entry in b.items():
                    if entry.get("ok", 0) < MIN_SUPPORT:
                        continue
                    s = self._score(entry)
                    if s > best_score:
                        best_key, best_entry, best_score = seq_key, entry, s
                if best_key is None:
                    return None
                self.stats["suggested"] += 1
                return {
                    "sequence": best_key.split(SEQ_SEP),
                    "score": round(best_score, 4),
                    "ok": best_entry.get("ok", 0),
                    "fail": best_entry.get("fail", 0),
                    "support": best_entry.get("ok", 0) + best_entry.get("fail", 0),
                    "sample_intent": best_entry.get("sample_intent", ""),
                    "bucket": bucket,
                }
        except Exception as e:
            logger.debug("[seq-learner] suggest failed: %s", e)
            return None

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "buckets": len(self._store),
                "total_sequences": sum(len(v) for v in self._store.values()),
                "stats": dict(self.stats),
            }


# ── Module-level singleton + convenience hooks ─────────────────────────

_instance: Optional[SequenceLearner] = None
_instance_lock = threading.Lock()


def get_learner() -> SequenceLearner:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SequenceLearner()
        return _instance


def maybe_observe(snapshot: Dict[str, Any]) -> None:
    """Fire-and-forget hook for PlanRecorder.record(). No-op unless enabled."""
    if not SEQUENCE_LEARNER_ENABLED:
        return
    try:
        get_learner().observe(snapshot)
    except Exception as e:
        logger.debug("[seq-learner] maybe_observe skipped: %s", e)


def suggest_sequence(intent: str = "", task_type: str = "") -> Optional[Dict[str, Any]]:
    """Convenience: best learned sequence prior for the planner. None unless enabled."""
    if not SEQUENCE_LEARNER_ENABLED:
        return None
    try:
        return get_learner().suggest(intent=intent, task_type=task_type)
    except Exception:
        return None
