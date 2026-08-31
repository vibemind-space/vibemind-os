"""Phase 11.U.A — Multi-plan concurrent execution.

Pre-U.A: PlanExecutor had a single-plan-at-a-time mutex (Phase 6.14.1).
Concurrent /api/multihop/execute calls returned "busy" envelopes for all
but the first.

Post-U.A: BoundedSemaphore allows up to PLAN_MAX_CONCURRENT plans to run
in parallel (default 3). Per-plan context flows through _exec_hop instead
of sitting on instance attrs, so no race on plan_intent / decision_context.

Test plan:
  1. Fire 3 parallel /api/multihop/execute requests
  2. Pass: ≥2 should return ok=True (or "rejected_busy" only if hit cap)
  3. Wall clock < 1.7× single-plan median (proves parallelism)
  4. /api/multihop/busy should reflect in_flight + max_concurrent

Usage:
  python scripts/test_multiplan.py [--n 3] [--url http://127.0.0.1:5000]
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from typing import Any, Dict, List

import httpx


SAMPLE_INTENTS = [
    "list all bubbles",
    "search for bubble named Inbox",
    "wie reif ist die bubble Marketing",
    "show me all ideas in bubble Inbox",
    "create a new bubble called MultiPlanTest_X",
    "find bubble Concept C",
]


async def fire_one(client: httpx.AsyncClient, url: str, intent: str, idx: int) -> Dict[str, Any]:
    t0 = time.time()
    try:
        r = await client.post(
            f"{url}/api/multihop/execute",
            json={"intent": intent},
            timeout=120.0,
        )
        latency = time.time() - t0
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "idx": idx,
            "intent": intent[:40],
            "status": r.status_code,
            "ok": bool(body.get("ok")),
            "busy": bool(body.get("busy")),
            "in_flight": body.get("in_flight"),
            "latency_s": round(latency, 2),
            "error": body.get("error"),
        }
    except Exception as e:
        return {
            "idx": idx,
            "intent": intent[:40],
            "status": 0,
            "ok": False,
            "busy": False,
            "latency_s": round(time.time() - t0, 2),
            "error": f"{type(e).__name__}: {e}",
        }


async def run_test(url: str, n: int) -> int:
    print(f"[U.A] firing {n} parallel /api/multihop/execute")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Health
        try:
            h = await client.get(f"{url}/api/health", timeout=5.0)
            if h.status_code != 200:
                print(f"[U.A] FAIL: brain health {h.status_code}")
                return 1
        except Exception as e:
            print(f"[U.A] FAIL: brain unreachable: {e}")
            return 1

        intents = [SAMPLE_INTENTS[i % len(SAMPLE_INTENTS)] for i in range(n)]
        wall_t0 = time.time()
        # Stagger by 50ms so each call sees prev plan(s) registered
        async def staggered(i: int, intent: str) -> Dict[str, Any]:
            await asyncio.sleep(i * 0.05)
            return await fire_one(client, url, intent, i)
        tasks = [staggered(i, intent) for i, intent in enumerate(intents)]
        results: List[Dict[str, Any]] = await asyncio.gather(*tasks)
        wall_s = time.time() - wall_t0

        # Quick busy_status snapshot AFTER (should report no active plans)
        try:
            br = await client.get(f"{url}/api/multihop/busy", timeout=5.0)
            busy = br.json() if br.status_code == 200 else {}
        except Exception:
            busy = {}

    # Print per-request results
    print(f"\n{'idx':>3}  {'status':>6}  {'ok':>5}  {'busy':>5}  {'lat_s':>7}  intent")
    for r in results:
        print(f"{r['idx']:>3}  {r['status']:>6}  {str(r['ok']):>5}  {str(r['busy']):>5}  {r['latency_s']:>7}  {r['intent']}")

    ok_count = sum(1 for r in results if r["ok"])
    busy_count = sum(1 for r in results if r.get("busy"))
    err_count = sum(1 for r in results if r["status"] >= 500)
    latencies = [r["latency_s"] for r in results if r["latency_s"] > 0]

    print(f"\n[U.A] wall_clock: {wall_s:.2f}s")
    if latencies:
        print(f"[U.A] median latency: {statistics.median(latencies):.2f}s")
        print(f"[U.A] max latency:    {max(latencies):.2f}s")
    print(f"[U.A] ok: {ok_count}/{n}   busy: {busy_count}/{n}   5xx: {err_count}/{n}")

    print(f"\n[U.A] /api/multihop/busy after: in_flight={busy.get('in_flight')} "
          f"max_concurrent={busy.get('max_concurrent')}")
    if busy.get("max_concurrent") is None:
        print(f"[U.A] WARN: no max_concurrent in busy_status — old code path?")

    # Verdict
    fails = []
    if err_count > 0:
        fails.append(f"{err_count} 5xx responses")
    if busy.get("max_concurrent") is None:
        fails.append("Phase U.A endpoint shape missing — restart needed?")
    # The big test: with multi-plan, at LEAST 2/3 should run successfully
    # (the third may hit the cap depending on PLAN_MAX_CONCURRENT, but a
    # default of 3 should fit all 3).
    if ok_count < min(n, 2):
        fails.append(f"only {ok_count}/{n} plans actually executed (expected at least min(n,2))")

    # Parallelism check: serial execution = sum of latencies, parallel = max.
    # If wall-clock is much closer to max than to sum, plans ran in parallel.
    if latencies and n >= 2 and ok_count >= 2:
        max_lat = max(latencies)
        sum_lat = sum(latencies)
        # Allow 30% slack on max for client-side scheduling overhead.
        if wall_s > max_lat * 1.3 and wall_s > sum_lat * 0.6:
            fails.append(
                f"wall_clock {wall_s:.1f}s ~= sum {sum_lat:.1f}s "
                f"(not max {max_lat:.1f}s) - plans appear serialised"
            )
        else:
            print(f"[U.A] parallelism: wall={wall_s:.1f}s close to max={max_lat:.1f}s "
                  f"(serial would be {sum_lat:.1f}s) PASS")

    if fails:
        print(f"\n[U.A] FAIL: {'; '.join(fails)}")
        return 1
    print(f"\n[U.A] PASS")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--url", default="http://127.0.0.1:5000")
    args = ap.parse_args()
    sys.exit(asyncio.run(run_test(args.url, args.n)))


if __name__ == "__main__":
    main()
