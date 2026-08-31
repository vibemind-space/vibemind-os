"""Routing-matrix auto-train DRAIN WORKER (batch, idle/periodic).

Built 2026-05-19. Moved here from `scripts/routing_autotrain_drain.py`
(2026-05-19, plan: production-saubere Stack-Sidecar-Architektur) so it lands
in the `vibemind-brain-core:latest` image via the Dockerfile
`COPY brain/the_brain/ /app/` — the swarm `brain-autotrain-drain` sidecar
runs `python -m production.autotrain_drain`. Pairs with
`core/routing_matrix_autotrain.py` (the queue hook).

WHAT
----
The hook appends trustworthy {task, capability} routing decisions to the
autotrain queue JSONL (instant, on Brain's routing path). This worker
drains that queue OFFLINE: for each new line it does the expensive
/predict (~53s) + /feedback round-trip against the ProductionPlanner
(brain-api :5001), so the matrix learns organically from real shortcut
routing WITHOUT the LLM-planner's mistakes (Approach B) and WITHOUT
loading the routing path.

WHY a separate worker (not inline)
----------------------------------
/predict is ~53s (HierarchicalPlanner: SBERT + RadialNetwork) and
/feedback needs the REAL prediction.brain_state.gates from it (synthetic
gates would poison the matrix). 53s/decision inline is far too heavy. A
periodic drain (the sidecar's `while true; sleep 1800` loop) decouples it.

OFFSET TRACKING
---------------
Queue is append-only JSONL. We track how many lines we've processed in a
sibling `<queue>.offset` file. Crash-safe: offset advances only after a
line's /feedback succeeds (or is permanently skipped), rewritten
atomically. Re-running is safe (resumes at offset). If the queue is
rotated/truncated below the offset, we reset to 0.

USAGE
-----
  python -m production.autotrain_drain            # drain all pending
  python -m production.autotrain_drain --max 20   # cap this run
  python -m production.autotrain_drain --dry-run  # show, don't call

Env:
  ROUTING_AUTOTRAIN_API     default http://127.0.0.1:5001
                            (sidecar sets http://brain-api:5001 — overlay DNS)
  ROUTING_AUTOTRAIN_QUEUE   default <the_brain>/data/routing_autotrain_queue.jsonl
                            (sidecar + brain-core both set /app/data/...)
  AUTOTRAIN_PREDICT_TIMEOUT default 120  (s — /predict is ~53s, headroom)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# This file lives at the_brain/production/autotrain_drain.py, so
# parent.parent == the_brain/ (== /app in the container). The queue's
# canonical home is the_brain/data/ (the bind/named volume mounted at
# /app/data). The sidecar + brain-core override ROUTING_AUTOTRAIN_QUEUE
# explicitly anyway; this default just keeps a host/dev invocation sane.
_THE_BRAIN = Path(__file__).resolve().parent.parent
_API = os.environ.get("ROUTING_AUTOTRAIN_API", "http://127.0.0.1:5001").rstrip("/")
_QUEUE = Path(
    os.environ.get(
        "ROUTING_AUTOTRAIN_QUEUE",
        str(_THE_BRAIN / "data" / "routing_autotrain_queue.jsonl"),
    )
)
_OFFSET = Path(str(_QUEUE) + ".offset")
_TIMEOUT = float(os.environ.get("AUTOTRAIN_PREDICT_TIMEOUT", "120"))


def _log(msg: str) -> None:
    print(f"[autotrain-drain] {msg}", flush=True)


def _read_offset() -> int:
    try:
        return int(_OFFSET.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def _write_offset(n: int) -> None:
    tmp = Path(str(_OFFSET) + ".tmp")
    tmp.write_text(str(n), encoding="utf-8")
    tmp.replace(_OFFSET)  # atomic on same filesystem


def _post(path: str, body: dict) -> dict | None:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{_API}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def _api_up() -> bool:
    try:
        with urllib.request.urlopen(f"{_API}/health", timeout=8) as r:
            return r.status == 200
    except Exception:
        return False


def _train_one(entry: dict, dry: bool) -> bool:
    """Returns True if the entry is 'done' (advance offset past it):
    success OR a permanent skip (malformed). Returns False only on a
    transient failure we want to retry next run (API down mid-batch)."""
    task = (entry.get("task") or "").strip()
    cap = (entry.get("capability") or "").strip()
    if not task or not cap:
        _log(f"skip malformed entry: {entry!r}")
        return True  # never retriable — advance past it
    if dry:
        _log(f"DRY would train: {task[:60]!r} -> {cap}")
        return True
    try:
        pred = _post("/predict", {"task": task})
        if not isinstance(pred, dict) or "prediction" not in pred:
            _log(f"predict gave no prediction for {task[:50]!r}; skip")
            return True  # malformed response — don't loop forever on it
        # NOTE (2026-05-19): send the FULL /predict response as
        # `prediction`, NOT just pred["prediction"]. provide_feedback
        # reads prediction['brain_state']['gates'] (the real learning
        # signal) — those gates live at the TOP LEVEL of the /predict
        # response, parallel to "prediction", not inside it. Sending only
        # pred["prediction"] → KeyError 'brain_state' → /feedback 500.
        _post(
            "/feedback",
            {
                "task": task,
                "prediction": pred,
                "actual_action": cap,
                "success": bool(entry.get("success", True)),
                "user_rating": 0.95,  # shortcut = high-confidence label
                "source": "routing_autotrain_drain",
            },
        )
        _log(f"trained: {task[:55]!r} -> {cap}")
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        _log(f"transient failure ({e}); will retry next run")
        return False
    except Exception as e:
        _log(f"unexpected ({type(e).__name__}: {e}); skip entry")
        return True  # don't poison the whole queue on one bad entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0,
                    help="max entries this run (0 = all pending)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not _QUEUE.exists():
        _log(f"no queue file yet ({_QUEUE}); nothing to do")
        return 0

    lines = _QUEUE.read_text(encoding="utf-8").splitlines()
    offset = _read_offset()
    if offset > len(lines):
        _log(f"offset {offset} > {len(lines)} lines — queue rotated; reset 0")
        offset = 0

    pending = len(lines) - offset
    if pending <= 0:
        _log(f"queue drained (offset={offset}, lines={len(lines)})")
        return 0
    _log(f"{pending} pending (offset={offset}/{len(lines)}), API={_API}")

    if not args.dry_run and not _api_up():
        _log(f"API {_API} not reachable — abort, retry next run")
        return 0  # not an error; just nothing done

    done = 0
    i = offset
    while i < len(lines):
        if args.max and done >= args.max:
            _log(f"--max {args.max} reached; {len(lines) - i} still pending")
            break
        raw = lines[i].strip()
        if not raw:
            i += 1
            _write_offset(i)
            continue
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            _log(f"unparseable line {i}; skip")
            i += 1
            _write_offset(i)
            continue
        ok = _train_one(entry, args.dry_run)
        if not ok:
            _log(f"stopping at line {i} (transient); resume next run")
            break
        i += 1
        _write_offset(i)
        done += 1
        if not args.dry_run:
            time.sleep(1)  # gentle pacing between heavy predict calls

    _log(f"run done: processed {done}, offset now {_read_offset()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
