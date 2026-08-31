"""
Phase S — Pump self-awareness: drive enough discourse + aggregations
to populate aggregated-kg with cross-session-clustering candidates.

Runs:
  - 30 force-discourse-ticks (idle mode, slow rotation through SLICE_SOURCES)
  - 1 force-aggregate
  - 1 force-meta-consolidate

Useful after S.1 substrate is seeded but discourse hasn't accumulated
real volume yet. Each tick takes 5-30s depending on Mirofish-Sim
LLM-latency, so the script may run 5-15 min total.

Run::
    python pump_self_awareness.py
    python pump_self_awareness.py --ticks 50  # more rounds
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict

import requests

BRAIN = os.environ.get("BRAIN_URL", "http://127.0.0.1:5000").rstrip("/")


def _post(path: str, body: Dict[str, Any] = None, timeout: int = 120) -> Dict[str, Any]:
    try:
        r = requests.post(f"{BRAIN}{path}", json=body or {}, timeout=timeout)
        return r.json() if r.ok else {"ok": False, "status": r.status_code,
                                       "text": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get(path: str) -> Dict[str, Any]:
    try:
        r = requests.get(f"{BRAIN}{path}", timeout=30)
        return r.json() if r.ok else {"ok": False, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=30)
    args = ap.parse_args()

    print(f"[pump] target = {BRAIN}, ticks = {args.ticks}")

    # State before
    state0 = _get("/api/self_awareness/state")
    print(f"[pump] state before:")
    print(f"  substrate_concepts: {state0.get('substrate_concepts')}")
    print(f"  topics: {state0.get('aggregated_topic_count')}")
    print(f"  meta_topics: {state0.get('aggregated_meta_topic_count')}")

    # Drive discourse ticks
    success_ticks = 0
    failed_ticks = 0
    self_aware_ticks = 0
    for i in range(args.ticks):
        t0 = time.time()
        r = _post("/api/discourse/tick_now", timeout=120)
        dt = time.time() - t0
        if r.get("ok"):
            success_ticks += 1
            slice_info = r.get("slice", {})
            tweets = r.get("tweets", 0)
            # Detect self-aware slice (semantic + concept)
            is_sa = (slice_info.get("collection") == "semantic"
                     and slice_info.get("node_type") == "concept")
            if is_sa:
                self_aware_ticks += 1
            print(f"[pump] tick {i+1}/{args.ticks} "
                  f"slice={slice_info.get('collection')}/{slice_info.get('node_type')} "
                  f"tweets={tweets} ({dt:.1f}s)"
                  + (" [self-aware]" if is_sa else ""))
        else:
            failed_ticks += 1
            print(f"[pump] tick {i+1} FAILED: {r}")

    # Aggregate
    print()
    print(f"[pump] forcing aggregate ...")
    r = _post("/api/discourse/aggregate_now", timeout=180)
    print(f"  result: {r}")

    # Meta-consolidate
    print(f"[pump] forcing meta-consolidate ...")
    r = _post("/api/discourse/meta_consolidate_now", timeout=300)
    print(f"  result: {r}")

    # State after
    print()
    state1 = _get("/api/self_awareness/state")
    print(f"[pump] state after:")
    print(f"  substrate_concepts: {state1.get('substrate_concepts')}")
    print(f"  topics: {state1.get('aggregated_topic_count')}")
    print(f"  findings: {state1.get('aggregated_finding_count')}")
    print(f"  decisions: {state1.get('aggregated_decision_count')}")
    print(f"  meta_topics: {state1.get('aggregated_meta_topic_count')}")
    print()
    print(f"[pump] discourse summary: {success_ticks}/{args.ticks} ticks ok, "
          f"{self_aware_ticks} self-aware slices, {failed_ticks} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
