"""Routing-matrix auto-train — Approach B, BATCH-QUEUE design.

Built 2026-05-19 (user: "was zum automatisch mit trainieren? … als
entscheidungs abgleich"; architecture chosen: batch-queue + idle drain).

WHY a queue (not live training)
-------------------------------
The :5001 ProductionPlanner's `/predict` takes ~53s (HierarchicalPlanner
forward: SBERT + RadialNetwork). `/feedback` REQUIRES the real
`prediction.brain_state.gates` from that call (synthetic gates would
poison the matrix), so the expensive call is unavoidable. Doing it inline
on every routing decision is far too heavy. So:

  HOOK (this file, runs in Brain): on a trustworthy decision, append ONE
  line to a queue file. Instant, no thread, no network, cannot disturb
  the routing path.

  DRAIN WORKER (scripts/routing_autotrain_drain.py, periodic/idle): reads
  the queue, does the 53s /predict + /feedback per entry, advances an
  offset. Decoupled entirely from routing latency.

THE LABEL (Approach B)
----------------------
Only `plan_id` starting "shortcut_" AND ok=True is queued. A shortcut
plan means a deterministic capabilities.yaml regex matched and bypassed
the unreliable LLM planner — that capability choice is known-good by
construction. LLM-planner results are NEVER queued (could be wrong, would
cement errors into the matrix). `ok=true` alone is NOT trusted (the
gmail→example.com bug was ok=true but wrong).

QUEUE FILE
----------
`data/routing_autotrain_queue.jsonl` — append-only JSONL, one
`{ts, task, capability, success}` per line. Lives in the `data/` volume
which is bind-mounted (compose: `./data:/app/data`), so the host drain
worker and the containerised Brain share the exact same file. The drain
worker tracks a byte/line offset in a sibling `.offset` file; the queue
is never mutated by the hook beyond appends (safe concurrent append).

Kill switch: env ROUTING_AUTOTRAIN=0.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.environ.get("ROUTING_AUTOTRAIN", "1") not in ("0", "false", "False")

# data/ is the bind-mounted volume shared host<->container. Resolve
# relative to this file (core/ -> ../data) so it works both in the
# container (/app/core -> /app/data) and on the host.
_QUEUE_PATH = Path(
    os.environ.get(
        "ROUTING_AUTOTRAIN_QUEUE",
        str(Path(__file__).resolve().parent.parent / "data"
            / "routing_autotrain_queue.jsonl"),
    )
)

_lock = threading.Lock()


def _first_capability(snapshot: Dict[str, Any]) -> Optional[str]:
    hops = snapshot.get("hops")
    if not hops and isinstance(snapshot.get("plan"), dict):
        hops = snapshot["plan"].get("hops")
    if isinstance(hops, list) and hops:
        h0 = hops[0]
        if isinstance(h0, dict):
            cap = h0.get("capability")
            if isinstance(cap, str) and cap.strip():
                return cap.strip()
    return None


def _is_trustworthy(snapshot: Dict[str, Any]) -> bool:
    """Approach B: only a deterministic-shortcut plan that executed ok."""
    plan_id = str(snapshot.get("plan_id") or "")
    if not plan_id.startswith("shortcut_"):
        return False
    if snapshot.get("ok") is not True:
        return False
    if not (snapshot.get("intent") or "").strip():
        return False
    return _first_capability(snapshot) is not None


def maybe_autotrain(snapshot: Dict[str, Any]) -> None:
    """Called by PlanRecorder.record() after every multihop execution.
    On a trustworthy shortcut decision, append ONE queue line. This is
    intentionally trivial — a single buffered file append under a lock,
    no network, no thread, no slow work. It can never disturb the
    routing path. The expensive predict+feedback happens later in the
    drain worker."""
    if not _ENABLED:
        return
    try:
        if not _is_trustworthy(snapshot):
            return
        task = (snapshot.get("intent") or "").strip()
        cap = _first_capability(snapshot)
        if not task or not cap:
            return
        line = json.dumps(
            {
                "ts": snapshot.get("ts"),
                "plan_id": snapshot.get("plan_id"),
                "task": task,
                "capability": cap,
                "success": True,  # ok=True is part of _is_trustworthy
            },
            ensure_ascii=False,
            default=str,
        )
        with _lock:
            _QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _QUEUE_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        logger.debug("[autotrain] queued %s -> %s", task[:60], cap)
    except Exception as e:  # never disturb the multihop path
        logger.debug("[autotrain] queue append skipped: %s", e)
