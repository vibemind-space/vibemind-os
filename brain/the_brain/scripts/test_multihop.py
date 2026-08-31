"""Phase 6 smoke test — exercises the multi-hop pipeline end-to-end.

Run against a live Brain on http://127.0.0.1:5000:

    python vibemind-os/brain/the_brain/scripts/test_multihop.py

Each check is one row in the output table. PASS/FAIL prints inline so you
can pipe through grep -c PASS for a quick count.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable, Dict, Tuple

import requests


BRAIN = os.environ.get("BRAIN_URL", "http://127.0.0.1:5000").rstrip("/")
TIMEOUT = float(os.environ.get("BRAIN_TIMEOUT_S", "60"))


def _get(path: str) -> Any:
    r = requests.get(f"{BRAIN}{path}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: Dict[str, Any] = None) -> Any:
    r = requests.post(f"{BRAIN}{path}", json=body or {}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


CHECKS = []


def check(name: str):
    def deco(fn: Callable[[], Tuple[bool, str]]):
        CHECKS.append((name, fn))
        return fn
    return deco


# ── checks ────────────────────────────────────────────────────────────


@check("MH.1 brain alive")
def _c1():
    h = _get("/api/health")
    return h.get("status") == "alive", f"uptime={h.get('uptime', 0):.1f}s"


@check("MH.2 advisor stats endpoint")
def _c2():
    s = _get("/api/multihop/stats")
    return s.get("loaded") is True, f"loaded={s.get('loaded')}"


@check("MH.3 hand-built plan executes (no LLM)")
def _c3():
    plan = {
        "plan_id": "test_handbuilt",
        "intent": "smoke handbuilt",
        "rationale": "smoke",
        "estimated_cost_usd": 0.0,
        "final_synthesis_prompt": "",
        "hops": [
            {
                "step_id": "s1", "description": "health",
                "execution_target": "brain:GET:/api/health",
                "arg_template": "", "output_var": "h",
                "depends_on": [], "on_fail": "abort",
                "timeout_s": 5, "retries": 1,
            },
            {
                "step_id": "s2", "description": "caps stats",
                "execution_target": "brain:GET:/api/capabilities/stats",
                "arg_template": "", "output_var": "c",
                "depends_on": ["s1"], "on_fail": "continue",
                "timeout_s": 5, "retries": 1,
                "validator": {"kind": "rule:non_empty_result", "on_fail": "report"},
            },
        ],
    }
    out = _post("/api/multihop/execute", {"plan": plan})
    if not out.get("ok"):
        return False, f"plan failed: {out.get('error')}"
    ex = out.get("executed", {})
    if "s1" not in ex or "s2" not in ex:
        return False, f"missing executed steps: {list(ex.keys())}"
    return ex["s1"].get("ok") and ex["s2"].get("ok"), \
        f"hops={len(ex)} elapsed={out.get('elapsed_s')}s"


@check("MH.4 validator runs and verdict attached")
def _c4():
    plan = {
        "plan_id": "test_validator",
        "intent": "validator smoke",
        "rationale": "smoke",
        "hops": [
            {
                "step_id": "s1", "description": "caps",
                "execution_target": "brain:GET:/api/capabilities/stats",
                "arg_template": "", "output_var": "c",
                "depends_on": [], "on_fail": "continue",
                "timeout_s": 5, "retries": 1,
                "validator": {"kind": "rule:non_empty_result", "on_fail": "report"},
            },
        ],
    }
    out = _post("/api/multihop/execute", {"plan": plan})
    s1 = out.get("executed", {}).get("s1", {})
    v = s1.get("validator_verdict")
    if not v:
        return False, "no validator verdict"
    return bool(v.get("valid")), f"verdict={v.get('reason')}"


@check("MH.5 dependency-fail cascades correctly")
def _c5():
    plan = {
        "plan_id": "test_cascade",
        "intent": "cascade smoke",
        "rationale": "smoke",
        "hops": [
            {
                "step_id": "s1", "description": "intentionally bad",
                "execution_target": "brain:GET:/api/this-route-does-not-exist",
                "arg_template": "", "output_var": "x",
                "depends_on": [], "on_fail": "abort",
                "timeout_s": 5, "retries": 1,
            },
            {
                "step_id": "s2", "description": "depends on bad s1",
                "execution_target": "brain:GET:/api/health",
                "arg_template": "", "output_var": "y",
                "depends_on": ["s1"], "on_fail": "continue",
                "timeout_s": 5, "retries": 1,
            },
        ],
    }
    out = _post("/api/multihop/execute", {"plan": plan})
    ex = out.get("executed", {})
    s1_ok = ex.get("s1", {}).get("ok")
    s2_ok = ex.get("s2", {}).get("ok")
    s2_err = ex.get("s2", {}).get("error", "")
    if s1_ok or s2_ok:
        return False, f"expected both fail; s1_ok={s1_ok} s2_ok={s2_ok}"
    if "dependency failed" not in (s2_err or "").lower():
        return False, f"s2 didn't cascade: {s2_err!r}"
    return True, "s2 correctly skipped after s1 failed"


@check("MH.6 plan recorder persists snapshot")
def _c6():
    h = _get("/api/multihop/history?limit=10")
    plans = h.get("plans") or []
    if not plans:
        return False, "no plans in history"
    p0 = plans[0]
    detail = _get(f"/api/multihop/plan/{p0['plan_id']}")
    if "executed" not in detail:
        return False, "plan detail missing executed"
    return True, f"history has {len(plans)} plans, top={p0['plan_id']}"


@check("MH.7 PlannerLLM produces a plan from natural intent (Groq)")
def _c7():
    intent = ("create a bubble called PhaseSixSmoke, then add 2 ideas "
              "about routing, then evaluate it")
    out = _post("/api/multihop/plan", {"intent": intent})
    if not out.get("ok"):
        return False, f"planner failed: {out.get('error')}"
    plan = out.get("plan") or {}
    hops = plan.get("hops") or []
    if len(hops) < 2:
        return False, f"only {len(hops)} hops"
    return True, f"hops={len(hops)} rationale={(plan.get('rationale') or '')[:60]!r}"


@check("MH.8 stream endpoint reachable (SSE)")
def _c8():
    # Just confirm the route exists and returns text/event-stream.
    r = requests.get(f"{BRAIN}/api/multihop/stream", stream=True, timeout=5)
    ct = r.headers.get("content-type", "")
    r.close()
    if "event-stream" not in ct.lower():
        return False, f"content-type={ct!r}"
    return True, "text/event-stream"


@check("MH.9 routing UI markup served")
def _c9():
    r = requests.get(f"{BRAIN}/brain", timeout=10)
    if r.status_code != 200:
        return False, f"status={r.status_code}"
    body = r.text
    needles = ["routingPanel", "toggleRoutingPanel",
               "/api/multihop/stream", "Multi-Hop Routing"]
    missing = [n for n in needles if n not in body]
    if missing:
        return False, f"missing markup: {missing}"
    return True, "all routing UI markup present"


@check("MH.10 single-hop intent stays single-hop (no multihop hijack)")
def _c10():
    # Send a short, single-action intent that the advisor must reject.
    # We don't actually run /api/brain/chat (heavy) — just confirm advisor
    # heuristics on a representative phrase via direct stats inspection.
    # Trigger a known-multi vs. known-single via /api/capabilities/test
    # (it doesn't run the advisor, but the heuristic itself is local).
    from importlib import import_module
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")))
    try:
        mha = import_module("core.multihop_advisor")
    except Exception as e:
        return False, f"import failed: {e}"
    adv = mha.MultiHopAdvisor()
    v_simple = adv.should_decompose("evaluate the X bubble")
    v_complex = adv.should_decompose(
        "create a bubble called Foo, add 3 ideas about routing, then evaluate it")
    if v_simple.should_decompose:
        return False, "simple intent wrongly multihop"
    if not v_complex.should_decompose:
        return False, "complex intent wrongly single-hop"
    return True, f"simple={v_simple.triggered_by} complex={v_complex.triggered_by}"


# ── main ─────────────────────────────────────────────────────────────


def main() -> int:
    print(f"Brain: {BRAIN}\n")
    print(f"{'check':<48} | {'status':<6} | detail")
    print("-" * 100)
    pass_count = 0
    fail_count = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        if ok:
            pass_count += 1
            mark = "PASS"
        else:
            fail_count += 1
            mark = "FAIL"
        print(f"| {name:<46} | {mark:<6} | {detail}")
    total = pass_count + fail_count
    print(f"\nResult: {pass_count}/{total} passed")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
