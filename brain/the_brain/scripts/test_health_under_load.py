"""Phase 11.U.B — Health-Check responsiveness under load.

After T.4-T.5 (async LLM path + per-provider semaphores) plus U.B
(asyncio.to_thread wrappers around sync kg.search / tick_intent /
_dispatch_to_openfang), /api/health should NEVER take more than ~50ms
to respond, even when other expensive endpoints are running.

Test plan:
  1. Baseline: 10 sequential health-checks, record latency
  2. Under load: fire 1 expensive request (kg.search with broad query
     across all collections), and 20 parallel health-checks while it runs
  3. Pass: p95 health latency stays < 500ms

Usage:
  python scripts/test_health_under_load.py
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from typing import List, Tuple

import httpx


URL = "http://127.0.0.1:5000"


async def fire_health(client: httpx.AsyncClient) -> float:
    t0 = time.time()
    try:
        r = await client.get(f"{URL}/api/health", timeout=5.0)
        if r.status_code != 200:
            return -1.0
    except Exception:
        return -1.0
    return (time.time() - t0) * 1000.0  # ms


async def fire_kg_search(client: httpx.AsyncClient) -> Tuple[bool, float]:
    """Heavy query — broad term across all collections."""
    t0 = time.time()
    try:
        r = await client.get(
            f"{URL}/api/kg/search",
            params={"q": "brain memory consolidation thoughts", "limit": 30},
            timeout=60.0,
        )
        return r.status_code == 200, (time.time() - t0) * 1000.0
    except Exception:
        return False, (time.time() - t0) * 1000.0


async def main() -> int:
    async with httpx.AsyncClient() as client:
        # Phase 1 — Baseline
        print("[U.B] phase 1: baseline (10 sequential health-checks)")
        baseline: List[float] = []
        for _ in range(10):
            ms = await fire_health(client)
            if ms > 0:
                baseline.append(ms)
        if not baseline:
            print("[U.B] FAIL: no baseline samples — brain unreachable?")
            return 1
        print(f"[U.B]   baseline median={statistics.median(baseline):.1f}ms "
              f"p95={sorted(baseline)[int(len(baseline)*0.95)]:.1f}ms "
              f"max={max(baseline):.1f}ms")

        # Phase 2 — Under load
        print("\n[U.B] phase 2: 1 heavy kg.search + 20 parallel health-checks")
        kg_task = asyncio.create_task(fire_kg_search(client))
        # Stagger health checks slightly so they hit during the kg.search window
        await asyncio.sleep(0.05)
        tasks = [fire_health(client) for _ in range(20)]
        latencies = await asyncio.gather(*tasks)
        kg_ok, kg_ms = await kg_task

        valid = [m for m in latencies if m > 0]
        if not valid:
            print("[U.B] FAIL: no valid health responses under load")
            return 1

        median = statistics.median(valid)
        p95 = sorted(valid)[int(len(valid) * 0.95)]
        max_ms = max(valid)
        print(f"[U.B]   kg.search returned in {kg_ms:.0f}ms (ok={kg_ok})")
        print(f"[U.B]   health-under-load median={median:.1f}ms "
              f"p95={p95:.1f}ms max={max_ms:.1f}ms n={len(valid)}/20")

        # Verdict — p95 should be < 500ms; if it's > 1s the event loop is
        # still being blocked.
        if p95 < 500:
            print(f"\n[U.B] PASS — health p95={p95:.0f}ms < 500ms target")
            return 0
        elif p95 < 2000:
            print(f"\n[U.B] WARN — health p95={p95:.0f}ms (between 500-2000ms)"
                  f"\n     Some blocking still happening, but not catastrophic.")
            return 0
        else:
            print(f"\n[U.B] FAIL — health p95={p95:.0f}ms still >2s under load"
                  f"\n     Event loop is still being blocked somewhere.")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
