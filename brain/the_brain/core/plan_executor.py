"""Plan Executor — Phase 6 core.

Takes a validated Plan, walks the DAG topologically, runs each Hop via the
existing capability_router → capability_targets → capability_validator
pipeline, threads results through `pipeline_state` with `{{state.X}}`
substitution, and emits SSE-ready events for the UI.

Reuses Phase 1.5/4 (DirectExecutor + multi-protocol targets) and Phase 3
(validator). Does NOT reuse the older `multi_agent_executor.execute_pipeline`
because that one operates on registered tool-pools, not on capability-router
matches — different abstraction. We keep the same DAG ideas but on Phase 6
primitives.

Public surface:
    pe = PlanExecutor(capability_router, validator, dispatcher)
    result = pe.execute(plan)            # blocking; returns dict
    q = pe.subscribe()                   # asyncio.Queue of SSE events
    pe.unsubscribe(q)
    pe.recorder                          # PlanRecorder instance (Phase 6.12)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import weakref
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

from .plan_schema import (
    HopResult, HopSpec, Plan, contract_pass_from,
    ON_FAIL_ABORT, ON_FAIL_CONTINUE, ON_FAIL_REPLAN,
)

logger = logging.getLogger(__name__)


# Phase 11.N — accept both `{{state.ideas.0}}` (dot) and `{{state.ideas[0]}}`
# (bracket) syntaxes. The capture group is the path AFTER the leading
# `state.` prefix, possibly mixing `.` and `[N]` segments.
_TEMPLATE_RE = re.compile(r"\{\{\s*state\.([a-zA-Z_][\w.\[\]]*?)\s*\}\}")
_MAX_REPLANS = int(os.environ.get("PLAN_MAX_REPLANS", "1"))
_MAX_PARALLEL = int(os.environ.get("PLAN_MAX_PARALLEL", "4"))
# A failing diary enqueue means a permanently lost episode, so it must be
# loud — but a queue that is broken is broken for EVERY plan, so logging each
# one would be a log bomb. First failure + every Nth after it.
_DIARY_FAIL_LOG_EVERY = 50


# ── Plan recording (Phase 6.12) ──────────────────────────────────────


class PlanRecorder:
    """Bounded in-memory ring + JSONL append. Survives Brain restart for
    history-replay UI."""

    def __init__(self, path: Optional[Path] = None, max_in_memory: int = 100) -> None:
        if path is None:
            path = Path(__file__).resolve().parent.parent / "data" / "multihop_history.jsonl"
        self.path = Path(path)
        self._recent: Deque[Dict[str, Any]] = deque(maxlen=max_in_memory)
        self._by_id: Dict[str, Dict[str, Any]] = {}
        # E2E-Trace (2026-06-09): trace_id-Index (Spiegel zu _by_id), damit auch
        # plan-lose Zweige (SoM/som-team/meta/easy/no-plan) per trace_id auffindbar
        # sind. GET /api/trace/{id} liest hier.
        self._by_trace: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f.readlines()[-100:]:
                        try:
                            d = json.loads(line)
                            if d.get("plan_id") or d.get("trace_id"):
                                self._recent.append(d)
                                if d.get("plan_id"):
                                    self._by_id[d["plan_id"]] = d
                                if d.get("trace_id"):
                                    self._by_trace[d["trace_id"]] = d
                        except Exception:
                            continue
        except Exception as e:
            logger.debug(f"[plan-recorder] load skipped: {e}")

    def record(self, snapshot: Dict[str, Any]) -> None:
        with self._lock:
            self._recent.append(snapshot)
            if snapshot.get("plan_id"):
                self._by_id[snapshot["plan_id"]] = snapshot
            if snapshot.get("trace_id"):
                self._by_trace[snapshot["trace_id"]] = snapshot
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")
            except Exception as e:
                logger.debug(f"[plan-recorder] persist failed: {e}")
            # 2026-05-19 — Approach B routing-matrix auto-train. Fire-and-
            # forget: feeds ONLY trustworthy shortcut+ok decisions to the
            # :5001 ProductionPlanner so the matrix learns organically from
            # live routing without cementing LLM-planner mistakes. Fully
            # best-effort — import + call are guarded so a missing/broken
            # hook can never disturb plan execution.
            try:
                from core.routing_matrix_autotrain import maybe_autotrain
                maybe_autotrain(snapshot)
            except Exception as e:
                logger.debug(f"[plan-recorder] autotrain skipped: {e}")
            # Baustein A — learn agent SEQUENCES per intent. Fire-and-forget;
            # no-op unless SEQUENCE_LEARNER_ENABLED. Uses ok=True (= verified
            # with Baustein D) as the success signal.
            try:
                from core.sequence_learner import maybe_observe
                maybe_observe(snapshot)
            except Exception as e:
                logger.debug(f"[plan-recorder] seq-learn skipped: {e}")

    def list(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._recent)[-limit:][::-1]
            return [
                {
                    "plan_id": s.get("plan_id"),
                    "ts": s.get("ts"),
                    "intent": (s.get("intent") or "")[:200],
                    "hop_count": s.get("hop_count"),
                    "ok": s.get("ok"),
                    "elapsed_s": s.get("elapsed_s"),
                }
                for s in items
            ]

    def get(self, plan_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._by_id.get(plan_id)

    # ── E2E-Trace (2026-06-09) ────────────────────────────────────────────────
    def get_by_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Volle Trace-Kette per trace_id (eingabe->...->ausgabe). Fuer
        GET /api/trace/{trace_id}."""
        with self._lock:
            return self._by_trace.get(trace_id)

    def attach_final(self, plan_id: str, text: str) -> None:
        """Haengt die AUSGABE (synthesis final_text) an einen schon recordeten
        Plan — bisher wurde final_text nie gespeichert. Patcht den in-memory-
        Snapshot + persistiert eine Patch-Zeile (best-effort)."""
        with self._lock:
            snap = self._by_id.get(plan_id)
            if snap is None:
                return
            snap["final_text"] = text
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"_patch": "final_text", "plan_id": plan_id,
                                        "trace_id": snap.get("trace_id"), "final_text": text},
                                       ensure_ascii=False, default=str) + "\n")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[plan-recorder] attach_final persist failed: {e}")

    def record_lite(self, trace_id: str, intent: str, routed_via: str,
                    final_text: str = "") -> None:
        """Mini-Snapshot fuer plan-lose Zweige (SoM/som-team/meta/easy/no-plan),
        damit auch sie im Trace auftauchen (trace_id + routed_via + Ausgabe).
        Per-Schritt-stages der SoM-Worker werden via append_stage gemerged."""
        import time as _t
        snap = {"trace_id": trace_id, "intent": (intent or "")[:500],
                "routed_via": routed_via, "final_text": final_text,
                "ts": _t.time(), "stages": [
                    {"stage": "eingabe", "component": "multihop_execute",
                     "ts": _t.time(), "outcome": "received"},
                    {"stage": "route", "component": "difficulty_router",
                     "ts": _t.time(), "outcome": routed_via},
                ], "ok": True}
        self.record(snap)

    def append_stage(self, trace_id: str, stage: str, component: str,
                     outcome: str = "") -> None:
        """Haengt ein Stage-Event an den Trace (von SoM-Workern via
        POST /api/trace/{id}/stage + intern). Legt einen leeren Trace an, falls
        die trace_id noch unbekannt ist (Race: Worker pusht vor record_lite)."""
        import time as _t
        with self._lock:
            snap = self._by_trace.get(trace_id)
            if snap is None:
                snap = {"trace_id": trace_id, "intent": "", "routed_via": "",
                        "stages": [], "ts": _t.time(), "ok": True}
                self._by_trace[trace_id] = snap
                self._recent.append(snap)
            snap.setdefault("stages", []).append(
                {"stage": stage, "component": component, "ts": _t.time(), "outcome": outcome})


# ── Plan executor ─────────────────────────────────────────────────────


class PlanExecutor:
    def __init__(
        self,
        capability_router: Any = None,
        validator: Any = None,
        dispatcher: Any = None,
        kg: Any = None,
        recorder: Optional[PlanRecorder] = None,
    ) -> None:
        self.capability_router = capability_router
        self.validator = validator
        self.dispatcher = dispatcher
        self.kg = kg                               # for KG-hit capture per hop
        # Baustein D.2 — execution-log (RAG index over the trace). Lazy; no-op
        # unless EXECUTION_LOG_ENABLED + a KG is present.
        self._exec_log = None
        try:
            from core.execution_log import ExecutionLog
            self._exec_log = ExecutionLog(kg)
        except Exception:
            self._exec_log = None
        self.recorder = recorder or PlanRecorder()
        self._subscribers: "weakref.WeakSet[asyncio.Queue]" = weakref.WeakSet()
        self._publish_loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.RLock()
        # Phase 11.U.A — multi-plan execution. Replaces the single-plan
        # mutex from Phase 6.14.1 with a bounded semaphore (N concurrent
        # plans) plus a tracking dict. Per-plan context (was instance
        # attrs) now flows as a parameter through _exec_hop.
        # Backward-compat: _exec_lock retained as Lock() for callers using
        # is_busy() during attach-phase, but no longer enforces serialisation.
        self._max_concurrent = int(os.environ.get("PLAN_MAX_CONCURRENT", "3"))
        self._exec_semaphore = threading.BoundedSemaphore(self._max_concurrent)
        self._exec_lock = threading.Lock()  # legacy, used only for is_busy reads
        self._active_plans: Dict[str, Dict[str, Any]] = {}
        self._active_plans_lock = threading.Lock()
        # Backward-compat shims read by stats / busy_status
        self._active_plan_id: Optional[str] = None
        self._active_plan_started_at: Optional[float] = None
        # Phase 6.14.2 — DiscourseEngine reference, set via attach_discourse_engine
        self._discourse_engine = None
        # Phase 6.14.3 — KG settle window (env-overridable)
        self._kg_settle_s = float(os.environ.get("MULTIHOP_KG_SETTLE_S", "0"))
        # Phase 6.14.4 — write plan + hop snapshots to brain-episodic
        self._episodic_enabled = os.environ.get(
            "MULTIHOP_EPISODIC_WRITE", "1",
        ) not in ("0", "false", "False")
        self.stats: Dict[str, Any] = {
            "plans_executed": 0,
            "hops_executed": 0,
            "hops_ok": 0,
            "hops_failed": 0,
            "replans_triggered": 0,
            "validator_blocks": 0,
            "total_elapsed_s": 0.0,
            "last_error": None,
            "rejected_busy": 0,
            "kg_settles": 0,
            "episodic_writes": 0,
            # Phase 1 diary queue. The queue is the ONLY path an executed plan
            # has to persistent memory, so a dropped enqueue is a permanently
            # lost episode. enqueue_plan never raises and only logs, which
            # makes "1 lost" and "10.000 lost" look identical — count them.
            "diary_enqueued": 0,
            "diary_enqueue_failures": 0,
        }

    # ── Pub/Sub for SSE (Phase 6.11) ───────────────────────────────

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the FastAPI event-loop so background threads can publish."""
        self._publish_loop = loop

    def attach_discourse_engine(self, de) -> None:
        """Phase 6.14.2 — wire DiscourseEngine so plan execution can pause
        idle/response loops and avoid concurrent KG writes."""
        self._discourse_engine = de

    def attach_continuous_thinking(self, cte) -> None:
        """Phase 7.5 — wire ContinuousThinkingEngine so plan completions and
        rewards become meaningful seeds for the thought stream."""
        self._continuous_thinking = cte

    def attach_decision_graph(self, dg) -> None:
        """Phase 8.B — wire Neo4j decision graph so plans/hops are visible
        in the decision-theatre UI."""
        self._decision_graph = dg

    # Phase 7.3 — provider success tracker. Maps (capability, target_kind)
    # to {success, fail} counts. After each hop we update the score; the
    # planner can later read it to break ties when multiple targets are
    # available. Read via get_provider_scores().
    def record_provider_outcome(
        self, capability: Optional[str], target: Optional[str], ok: bool,
    ) -> None:
        if not target:
            return
        kind = target.split(":", 1)[0].lower() if ":" in target else target.lower()
        key = f"{capability or '_any_'}:{kind}"
        with self._lock:
            scores = getattr(self, "_provider_scores", None)
            if scores is None:
                scores = {}
                self._provider_scores = scores
            entry = scores.setdefault(key, {"success": 0, "fail": 0})
            if ok:
                entry["success"] += 1
            else:
                entry["fail"] += 1

    def get_provider_scores(self) -> Dict[str, Any]:
        with self._lock:
            scores = dict(getattr(self, "_provider_scores", {}) or {})
        out = {}
        for key, e in scores.items():
            total = e["success"] + e["fail"]
            rate = (e["success"] / total) if total else 0.0
            out[key] = {**e, "total": total, "rate": round(rate, 3)}
        return out

    def record_plan_reward(self, plan_id: str, delta: float, reason: str = "") -> Dict[str, Any]:
        """Phase 7.1 — attach a user-feedback reward to a recently-executed plan.
        Updates the recorder snapshot's `reward_score` field and best-effort
        re-upserts the plan_execution episodic node so downstream consolidation
        sees the score. Idempotent for the same (plan_id, reason) pair."""
        snap = self.recorder.get(plan_id)
        if snap is None:
            return {"ok": False, "error": f"plan {plan_id} not in recorder"}
        prev = float(snap.get("reward_score") or 0.0)
        new_score = max(-2.0, min(2.0, prev + float(delta)))
        snap["reward_score"] = round(new_score, 3)
        snap["reward_reason"] = reason
        snap["reward_ts"] = time.time()
        # Re-publish into episodic with updated score so cross-session
        # consolidation picks the better-rated plans up.
        if self._episodic_enabled:
            try:
                self._episodic_write(snap)
            except Exception as e:
                logger.debug(f"[plan-executor] reward episodic re-upsert failed: {e}")
        # Also fire an SSE event so any listening UI updates the history badge
        self._publish("plan_rewarded", {
            "plan_id": plan_id, "delta": delta,
            "reward_score": new_score, "reason": reason,
        })
        # Phase 7.5 — surface to ContinuousThinkingEngine
        cte = getattr(self, "_continuous_thinking", None)
        if cte is not None:
            try:
                cte.record_event("plan_rewarded", {
                    "plan_id": plan_id,
                    "intent": (snap.get("intent") or "")[:120],
                    "score": new_score,
                    "reason": reason,
                })
            except Exception:
                pass
        with self._lock:
            self.stats.setdefault("rewards_recorded", 0)
            self.stats["rewards_recorded"] += 1
        return {"ok": True, "plan_id": plan_id, "reward_score": new_score, "delta": delta}

    def is_busy(self) -> bool:
        """Phase 11.U.A — busy means: at the concurrency cap. Below the
        cap, more plans are still acceptable."""
        with self._active_plans_lock:
            return len(self._active_plans) >= self._max_concurrent

    def busy_status(self) -> Dict[str, Any]:
        with self._active_plans_lock:
            active_list = [
                {
                    "plan_id": pid,
                    "intent_preview": (info.get("intent") or "")[:80],
                    "active_for_s": round(time.time() - info["started_at"], 2),
                }
                for pid, info in self._active_plans.items()
            ]
            in_flight = len(active_list)
        return {
            # `busy` semantics now: at-cap (no more plans accepted)
            "busy": in_flight >= self._max_concurrent,
            "in_flight": in_flight,
            "max_concurrent": self._max_concurrent,
            "active_plans": active_list,
            # Back-compat fields (most-recent plan if any)
            "active_plan_id": active_list[0]["plan_id"] if active_list else None,
            "active_for_s": active_list[0]["active_for_s"] if active_list else None,
        }

    def _expand_repeat_hop(
        self, hop: HopSpec, state: Dict[str, Any], executed: Dict[str, "HopResult"],
    ) -> "Tuple[List[HopSpec], HopResult]":
        """Phase 6.15.1 — expand a repeat-hop into N sibling sub-hops.
        Returns (children, fallback_parent_summary). If items list is
        empty, children=[] and parent_summary describes the no-op."""
        cfg = hop.repeat or {}
        items: List[Any] = []

        # Inline list takes precedence
        explicit = cfg.get("items")
        if isinstance(explicit, list):
            items = list(explicit)

        # Pull from state
        from_path = cfg.get("items_from")
        if not items and isinstance(from_path, str) and from_path:
            # Strip leading "state." if planner wrote it that way
            path = from_path
            if path.startswith("state."):
                path = path[len("state."):]
            cur: Any = state.get(path.split(".", 1)[0])
            for p in path.split(".")[1:]:
                if isinstance(cur, dict):
                    cur = cur.get(p)
                else:
                    cur = None
                    break
            if isinstance(cur, list):
                items = list(cur)

        # count: shorthand for "0..N-1" placeholders when planner couldn't
        # invent items but knows how many it wants.
        if not items:
            n = cfg.get("count")
            if isinstance(n, int) and n > 0:
                items = list(range(int(n)))

        # Hard cap so a runaway plan can't generate 10k sub-hops
        max_items = int(os.environ.get("MULTIHOP_REPEAT_MAX", "50"))
        if len(items) > max_items:
            items = items[:max_items]

        if not items:
            # Emit a synthetic parent result so dependents can proceed
            return [], HopResult(
                step_id=hop.step_id, ok=True,
                result={"expanded_into": [], "child_count": 0,
                        "note": "repeat-hop had no items"},
                capability=hop.capability, target=hop.execution_target,
                elapsed_s=0.0,
            )

        children: List[HopSpec] = []
        for i, item in enumerate(items):
            child_id = f"{hop.step_id}.{i}"
            children.append(HopSpec(
                step_id=child_id,
                description=f"{hop.description} [{i+1}/{len(items)}]",
                capability=hop.capability,
                execution_target=hop.execution_target,
                arg_kwarg=hop.arg_kwarg,
                arg_template=hop.arg_template,
                # children depend on the parent's deps, not on the parent
                # itself (parent is a synthetic aggregator)
                depends_on=list(hop.depends_on),
                # children write into per-iteration output_var
                output_var=f"{hop.output_var}_{i}" if hop.output_var else "",
                on_fail=hop.on_fail,
                validator=hop.validator,
                timeout_s=hop.timeout_s,
                retries=hop.retries,
                repeat=None,  # children are leaves
            ))
            # Attach the iteration context so _exec_hop can render {{item}}
            children[-1].__dict__["_repeat_ctx"] = {
                "item": item, "index": i + 1, "index0": i, "value": item,
            }
        # Update children's depends_on to include parent so any hop that
        # depends on the parent will wait for ALL children
        return children, HopResult(
            step_id=hop.step_id, ok=True,
            result={"expanded_into": [c.step_id for c in children],
                    "child_count": len(children)},
            capability=hop.capability, target=hop.execution_target,
            elapsed_s=0.0,
        )

    def _episodic_write(self, snapshot: Dict[str, Any]) -> None:
        """Phase 6.14.4 — push a plan-execution summary into brain-episodic
        as a thought-shaped node so consolidation + cross-session recall
        find it. Best-effort; never raises.
        """
        if self.kg is None:
            return
        upsert = getattr(self.kg, "_upsert_point", None)
        if upsert is None:
            return
        plan_id = snapshot.get("plan_id") or "plan_unknown"
        intent = snapshot.get("intent") or ""
        ok = bool(snapshot.get("ok"))
        executed = snapshot.get("executed") or {}
        hop_lines: List[str] = []
        for sid, hr in executed.items():
            mark = "OK" if hr.get("ok") else "FAIL"
            cap = hr.get("capability") or hr.get("target") or "?"
            err = hr.get("error") or ""
            line = f"  - {sid} [{mark}] {cap}"
            if err:
                line += f" :: {err[:120]}"
            hop_lines.append(line)
        text = (
            f"Multi-hop plan {plan_id} for intent: {intent}\n"
            f"Ok={ok} hops={snapshot.get('hop_count')} "
            f"elapsed={snapshot.get('elapsed_s')}s replans={snapshot.get('replans')}\n"
            + "\n".join(hop_lines[:10])
        )
        payload = {
            "plan_id": plan_id,
            "intent": intent[:500],
            "rationale": (snapshot.get("rationale") or "")[:500],
            "hop_count": snapshot.get("hop_count"),
            "ok": ok,
            "elapsed_s": snapshot.get("elapsed_s"),
            "source": "multihop_plan_executor",
            "tags": ["multihop", "plan_summary"],
            "ts": snapshot.get("ts"),
            # Phase 7.1 — user-attributed reward, default 0 until feedback
            "reward_score": snapshot.get("reward_score") or 0.0,
            "reward_reason": snapshot.get("reward_reason") or "",
        }
        try:
            pid = upsert(plan_id, "plan_execution", text, payload)
            if pid:
                with self._lock:
                    self.stats["episodic_writes"] += 1
        except Exception as e:
            logger.debug(f"[plan-executor] episodic upsert failed: {e}")

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.discard(q)
        except Exception:
            pass

    @staticmethod
    def _tappend(plan, stage: str, component: str, outcome: str = "") -> None:
        """E2E-Trace: ein Stage-Event an plan._stages haengen (landet im Recorder-
        Snapshot). NUR Liste-Append, KEIN I/O, try/except — kein Hot-Path-Risiko."""
        try:
            plan._stages.append({"stage": stage, "component": component,
                                 "ts": time.time(), "outcome": outcome})
        except Exception:  # noqa: BLE001
            pass

    def _publish(self, kind: str, payload: Dict[str, Any]) -> None:
        if not self._subscribers:
            return
        event = {"kind": kind, "payload": payload, "ts": time.time()}
        loop = self._publish_loop
        for q in list(self._subscribers):
            try:
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(self._safe_put, q, event)
                else:
                    # Best-effort sync fallback (test environment without a loop)
                    try:
                        q.put_nowait(event)
                    except Exception:
                        pass
            except Exception:
                pass

    @staticmethod
    def _safe_put(q: asyncio.Queue, event: Dict[str, Any]) -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                _ = q.get_nowait()  # drop oldest
                q.put_nowait(event)
            except Exception:
                pass

    # ── Public execute ────────────────────────────────────────────

    def execute(
        self,
        plan: Plan,
        *,
        replanner: Optional[Callable[[Plan, HopResult], Optional[Plan]]] = None,
        confirmed_events: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Walk the DAG. Returns a dict with `executed` (step_id → HopResult),
        `state`, `plan`, `ok`, `elapsed_s`, `replans`.

        Desktop-family events listed as mutating in the canonical space registry
        run only when their exact event id is present in ``confirmed_events``.

        Phase 6.14.1 — single-plan-at-a-time: parallel callers get a
        `busy` envelope back instead of stomping on shared state.
        Phase 6.14.2 — pauses DiscourseEngine for the duration of the run
        so idle/response ticks don't compete for KG/Supabase writes.
        """
        # Phase 11.U.A — Plan-Concurrency: bounded semaphore. Up to N plans
        # may run concurrently (default 3, env PLAN_MAX_CONCURRENT). Beyond
        # the cap, callers receive a `busy` envelope so the UI knows.
        if not self._exec_semaphore.acquire(blocking=False):
            with self._lock:
                self.stats["rejected_busy"] += 1
            with self._active_plans_lock:
                in_flight = len(self._active_plans)
            return {
                "ok": False,
                "busy": True,
                "in_flight": in_flight,
                "max_concurrent": self._max_concurrent,
                "error": (
                    f"plan-executor at concurrency cap "
                    f"({in_flight}/{self._max_concurrent}) — try again shortly"
                ),
                "plan_id": plan.plan_id,
            }

        t0 = time.time()
        # Register this plan in the active-plans dict
        with self._active_plans_lock:
            self._active_plans[plan.plan_id] = {
                "started_at": t0,
                "intent": plan.intent or "",
            }
            # Maintain back-compat instance attrs (point to most recent plan)
            self._active_plan_id = plan.plan_id
            self._active_plan_started_at = t0
        with self._lock:
            self.stats["plans_executed"] += 1

        # Phase 11.U.A — pause discourse only when *first* concurrent plan
        # arrives. Last-out resumes. With multi-plan execution we can't
        # rely on the de.is_paused() heuristic anymore — track ourselves.
        de = self._discourse_engine
        is_first_plan = False
        try:
            if de is not None:
                with self._active_plans_lock:
                    is_first_plan = len(self._active_plans) == 1
                if is_first_plan and not de.is_paused():
                    de.pause()
        except Exception:
            de = None  # broken engine — proceed without pause

        self._publish("plan_started", plan.to_dict())
        self._tappend(plan, "execution", "plan-executor", f"started {len(plan.hops)} hops")

        # ── Phase 10 — Self-Reflective pre-execution context ─────────
        # Fire decision-recall + self-prior + critic. All best-effort:
        # any failure here must NEVER block the actual execution.
        decision_context: Dict[str, Any] = {
            "recall": [], "self_prior": {}, "critic": {},
        }
        try:
            from . import decision_recall, decision_self_prior, plan_critic
            if self.kg is not None:
                try:
                    decision_context["recall"] = decision_recall.recall(
                        plan.intent or "", self.kg, k=5,
                    )
                except Exception as e:
                    logger.debug(f"[plan-executor] recall failed: {e}")
                try:
                    decision_context["self_prior"] = decision_self_prior.prior(
                        plan.intent or "", self.kg, k=8,
                    )
                except Exception as e:
                    logger.debug(f"[plan-executor] self_prior failed: {e}")
            try:
                decision_context["critic"] = plan_critic.critique(
                    plan, plan.intent or "", self.dispatcher,
                )
            except Exception as e:
                logger.debug(f"[plan-executor] critic failed: {e}")
            self._publish("plan_context", {
                "plan_id": plan.plan_id,
                "recall_count": len(decision_context["recall"] or []),
                "self_prior_best": (decision_context.get("self_prior") or {}).get("best_capability"),
                "critic_recommend": (decision_context.get("critic") or {}).get("recommend"),
                "critic_score": (decision_context.get("critic") or {}).get("score", 0.0),
            })
        except Exception as e:
            logger.debug(f"[plan-executor] phase-10 pre-context failed: {e}")
        # End Phase 10 pre-context

        # Phase 11.U.A — context as a per-call dict instead of instance attrs.
        # Pre-11.U.A this lived on `self`, which clobbered if two plans ran
        # concurrently. Per-call context = race-free multi-plan execution.
        plan_ctx: Dict[str, Any] = {
            "decision_context": decision_context,
            "plan_intent": plan.intent or "",
            "plan_rationale": getattr(plan, "rationale", "") or "",
            "plan_id": plan.plan_id,
            "trace_id": getattr(plan, "trace_id", "") or "",
            "confirmed_events": set(confirmed_events or ()),
        }

        executed: Dict[str, HopResult] = {}
        state: Dict[str, Any] = {}
        replan_count = 0

        all_hops_by_id: Dict[str, HopSpec] = {h.step_id: h for h in plan.hops}

        try:
            # Iterate until everyone is executed or we hit a dead-end.
            while len(executed) < len(all_hops_by_id):
                ready = [
                    h for h in all_hops_by_id.values()
                    if h.step_id not in executed
                    and all(d in executed for d in h.depends_on)
                ]
                if not ready:
                    # Either all blocked due to upstream failure, or weird state.
                    break

                # Skip steps whose dependencies failed AND on_fail says abort
                still_ready: List[HopSpec] = []
                for h in ready:
                    failed_deps = [d for d in h.depends_on if not executed[d].ok]
                    if failed_deps:
                        # Mark skipped — record a synthetic result
                        skipped = HopResult(
                            step_id=h.step_id,
                            ok=False,
                            error=f"dependency failed: {failed_deps}",
                            capability=h.capability,
                            target=h.execution_target,
                            contract_pass=False, reward=-1.0,
                        )
                        executed[h.step_id] = skipped
                        with self._lock:
                            self.stats["hops_failed"] += 1
                        self._publish("hop_completed", _hop_event(h, skipped))
                    else:
                        still_ready.append(h)

                # Phase 6.15.1 — expand repeat-hops into sub-hops at runtime.
                # We do this lazily so `repeat.items_from` can read state
                # produced by earlier hops in the same plan.
                expanded: List[HopSpec] = []
                for h in still_ready:
                    if not getattr(h, "repeat", None):
                        expanded.append(h)
                        continue
                    children, parent_summary = self._expand_repeat_hop(h, state, executed)
                    if not children:
                        # No items → mark parent as a no-op success and move on
                        executed[h.step_id] = parent_summary
                        with self._lock:
                            self.stats["hops_executed"] += 1
                            self.stats["hops_ok"] += 1
                        self._publish("hop_completed", _hop_event(h, parent_summary))
                        continue
                    # Add children to the master dict so future iterations see them
                    for c in children:
                        all_hops_by_id[c.step_id] = c
                    # Parent is replaced by aggregator — record it now so
                    # the loop doesn't reprocess
                    executed[h.step_id] = HopResult(
                        step_id=h.step_id,
                        ok=True,
                        result={"expanded_into": [c.step_id for c in children],
                                "child_count": len(children)},
                        capability=h.capability,
                        target=h.execution_target,
                        rendered_arg=h.arg_template,
                        elapsed_s=0.0,
                    )
                    with self._lock:
                        self.stats["hops_executed"] += 1
                        self.stats["hops_ok"] += 1
                    self._publish("hop_completed", _hop_event(h, executed[h.step_id]))
                    expanded.extend(children)
                still_ready = expanded

                if not still_ready:
                    continue

                # Baustein B — pre-execution contract gate. A hop with a
                # `start_when` contract is only allowed to run once its
                # conditions hold against executed-state. Fail-open: no-op unless
                # CONTRACT_ENFORCEMENT_ENABLED. Blocked hops become an explicit
                # failed result (never a silent hang).
                try:
                    from core.contract_gate import (
                        check_start_when, CONTRACT_ENFORCEMENT_ENABLED,
                    )
                    if CONTRACT_ENFORCEMENT_ENABLED:
                        allowed_ready = []
                        for h in still_ready:
                            dec = check_start_when(h, executed)
                            if dec.allowed:
                                allowed_ready.append(h)
                            else:
                                blocked = HopResult(
                                    step_id=h.step_id, ok=False,
                                    error=f"contract blocked: {dec.reason}",
                                    capability=h.capability,
                                    target=h.execution_target,
                                    contract_pass=False, reward=-1.0,
                                )
                                executed[h.step_id] = blocked
                                with self._lock:
                                    self.stats["hops_executed"] += 1
                                    self.stats.setdefault("contract_blocks", 0)
                                    self.stats["contract_blocks"] += 1
                                self._publish("hop_completed", _hop_event(h, blocked))
                        still_ready = allowed_ready
                        if not still_ready:
                            continue
                except Exception as _ce:
                    logger.debug(f"[plan-executor] contract gate skipped: {_ce}")

                # Run ready batch in parallel
                with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
                    futures: Dict[Future, HopSpec] = {
                        pool.submit(self._exec_hop, h, state, plan_ctx): h
                        for h in still_ready
                    }
                    self._publish_started(still_ready, state)
                    for f in as_completed(futures):
                        h = futures[f]
                        try:
                            hr: HopResult = f.result()
                        except Exception as e:
                            hr = HopResult(
                                step_id=h.step_id, ok=False,
                                error=f"executor crash: {type(e).__name__}: {e}",
                                capability=h.capability, target=h.execution_target,
                                contract_pass=False, reward=-1.0,
                            )
                        executed[h.step_id] = hr
                        with self._lock:
                            self.stats["hops_executed"] += 1
                            if hr.ok:
                                self.stats["hops_ok"] += 1
                            else:
                                self.stats["hops_failed"] += 1
                        if hr.ok and h.output_var:
                            state[h.output_var] = hr.result
                            # Phase 11.H — for repeat-block sub-hops (output_var
                            # like "ideas_0", "ideas_1", ...), also aggregate
                            # all results into a list under the parent's name
                            # ("ideas") so subsequent hops can use
                            # `repeat: { items_from: state.ideas }`.
                            try:
                                ov = h.output_var
                                # Detect "<base>_<int>" pattern
                                if "_" in ov and ov.rsplit("_", 1)[-1].isdigit():
                                    base = ov.rsplit("_", 1)[0]
                                    # Find ALL siblings, sort by index, build list
                                    sibling_keys = sorted(
                                        (k for k in state.keys()
                                         if k.startswith(base + "_")
                                         and k.rsplit("_", 1)[-1].isdigit()),
                                        key=lambda x: int(x.rsplit("_", 1)[-1]),
                                    )
                                    aggregated = []
                                    for k in sibling_keys:
                                        v = state[k]
                                        # Try to extract idea_id / bubble_id
                                        # from result-string or dict; otherwise
                                        # store raw result.
                                        if isinstance(v, str):
                                            import re as _re
                                            # Phase 11.H: prefer id= extraction for things like
                                            # bubble_create("Created bubble 'X' (id=abc)").
                                            m = _re.search(r"id=([^\s)]+)", v)
                                            if m:
                                                aggregated.append(m.group(1))
                                            else:
                                                # Phase 11.N: idea_add returns
                                                # "Added 'Idea N: title'" — extract the
                                                # quoted title so downstream format-hops
                                                # can address it by name (fuzzy match).
                                                tm = _re.search(
                                                    r"(?:Added|Created|Updated)\s+['\"]([^'\"]+)['\"]",
                                                    v,
                                                )
                                                aggregated.append(tm.group(1) if tm else v)
                                        elif isinstance(v, dict):
                                            aggregated.append(
                                                v.get("idea_id")
                                                or v.get("id")
                                                or v.get("bubble_id")
                                                or v.get("result")
                                                or v
                                            )
                                        else:
                                            aggregated.append(v)
                                    state[base] = aggregated
                            except Exception as _agg_err:
                                logger.debug(
                                    f"[plan-executor] sub-hop aggregation failed: {_agg_err}"
                                )
                        self._publish("hop_completed", _hop_event(h, hr))
                        self._tappend(plan, "execution",
                                     f"hop:{getattr(h,'capability','?')}",
                                     ("ok" if getattr(hr, "ok", False) else "fail")
                                     + f" ({getattr(h,'execution_target',None) or getattr(h,'capability','?')})")

                        # Replan trigger
                        if (
                            not hr.ok
                            and h.on_fail == ON_FAIL_REPLAN
                            and replanner is not None
                            and replan_count < _MAX_REPLANS
                        ):
                            replan_count += 1
                            with self._lock:
                                self.stats["replans_triggered"] += 1
                            new_plan = replanner(plan, hr)
                            if new_plan is not None:
                                # Merge: keep already-executed hops, replace remaining
                                done_ids = set(executed.keys())
                                fresh = [hs for hs in new_plan.hops if hs.step_id not in done_ids]
                                for hs in fresh:
                                    all_hops_by_id[hs.step_id] = hs
                                self._publish("plan_replanned", {
                                    "plan_id": plan.plan_id,
                                    "new_hops": [h.step_id for h in fresh],
                                    "trigger_step": h.step_id,
                                })

            elapsed = time.time() - t0
            with self._lock:
                self.stats["total_elapsed_s"] += elapsed
            ok = all(hr.ok for hr in executed.values())
            result = {
                "ok": ok,
                "plan": plan.to_dict(),
                "executed": {sid: asdict(hr) for sid, hr in executed.items()},
                "state": _safe_state_snapshot(state),
                "elapsed_s": round(elapsed, 2),
                "replans": replan_count,
                "decision_context": decision_context,
            }
            self._publish("plan_completed", {
                "plan_id": plan.plan_id,
                "ok": ok,
                "elapsed_s": result["elapsed_s"],
                "hop_count": len(executed),
            })
            self._tappend(plan, "execution", "plan-executor",
                         f"completed ok={ok} in {result['elapsed_s']}s")

            # Phase 8.B — sync to Neo4j decision graph
            dg = getattr(self, "_decision_graph", None)
            if dg is not None and dg.is_connected():
                try:
                    dg.upsert_plan(
                        plan_id=plan.plan_id,
                        intent=plan.intent,
                        ok=ok,
                        hop_count=len(executed),
                        reward_score=0.0,
                    )
                    for sid, hr in executed.items():
                        dg.upsert_hop(
                            plan_id=plan.plan_id,
                            step_id=sid,
                            capability=hr.capability or "",
                            target=hr.target or "",
                            ok=bool(hr.ok),
                            elapsed_s=float(hr.elapsed_s or 0.0),
                        )
                        # Phase 9.0.2 — persist captured MCP tool-calls
                        if hr.tool_calls:
                            hop_node_id = f"{plan.plan_id}:{sid}"
                            # Phase 9.0.4 — annotate risk + approval status
                            try:
                                from .approval_gate import annotate_tool_calls
                                annotate_tool_calls(hr.tool_calls)
                            except Exception as e:
                                logger.debug(f"[plan-executor] risk-annotate failed: {e}")
                            try:
                                dg.upsert_tool_calls(hop_node_id, hr.tool_calls)
                            except Exception as e:
                                logger.debug(f"[plan-executor] tool-calls upsert failed: {e}")
                except Exception as e:
                    logger.debug(f"[plan-executor] decision-graph sync failed: {e}")

            # ── Phase 10 — persist decision_record + update self-prior ───
            # Best-effort. Decisions go to brain-decisions for recall, and
            # each capability used updates the self-model belief.
            try:
                from . import decision_recall, decision_self_prior
                hop_results_list = list(executed.values())
                outcome = "success" if ok else (
                    "partial" if any(hr.ok for hr in hop_results_list) else "failure"
                )
                if self.kg is not None:
                    decision_recall.record(
                        plan_id=plan.plan_id,
                        intent=plan.intent or "",
                        plan=plan,
                        hop_results=hop_results_list,
                        outcome=outcome,
                        reward=None,  # explicit reward arrives later via /api/decisions/reward
                        kg=self.kg,
                        duration_ms=int(elapsed * 1000),
                    )
                    # Update self-model: one trait per capability used
                    seen_caps: set = set()
                    for hr in hop_results_list:
                        cap = hr.capability or ""
                        if not cap or cap in seen_caps:
                            continue
                        seen_caps.add(cap)
                        decision_self_prior.update(
                            intent_text=plan.intent or "",
                            capability=cap,
                            success=bool(hr.ok),
                            reward=None,
                            plan_id=plan.plan_id,
                            kg=self.kg,
                        )
            except Exception as e:
                logger.debug(f"[plan-executor] phase-10 persist failed: {e}")

            # Phase 7.5 — push meaningful event to ContinuousThinkingEngine
            cte = getattr(self, "_continuous_thinking", None)
            if cte is not None:
                try:
                    cte.record_event("plan_completed", {
                        "plan_id": plan.plan_id,
                        "intent": plan.intent,
                        "ok": ok,
                        "hop_count": len(executed),
                        "elapsed_s": result["elapsed_s"],
                    })
                except Exception:
                    pass
            # Baustein D.2 — plan-level trace stage (finish | plan_aborted).
            try:
                if self._exec_log is not None and self._exec_log.enabled:
                    self._exec_log.record_step(
                        plan_id=plan.plan_id, hop_k=None,
                        intent=plan.intent or "",
                        stage=("finish" if ok else "plan_aborted"),
                        source="executor", claimed_ok=ok, verified=None,
                        reason=f"{len(executed)} hops, {result.get('replans', 0)} replans",
                        trace_id=getattr(plan, "trace_id", "") or "",
                    )
            except Exception:
                pass
            return result

        finally:
            elapsed_total = time.time() - t0
            snapshot = None
            try:
                snapshot = {
                    "plan_id": plan.plan_id,
                    "ts": time.time(),
                    "intent": plan.intent,
                    "rationale": plan.rationale,
                    "hop_count": len(plan.hops),
                    "hops": [asdict(h) for h in plan.hops],
                    "executed": {sid: asdict(hr) for sid, hr in executed.items()},
                    "state": _safe_state_snapshot(state),
                    "ok": all(hr.ok for hr in executed.values()) if executed else False,
                    "elapsed_s": round(elapsed_total, 2),
                    "replans": replan_count,
                    # E2E-Trace (2026-06-09): trace_id + per-stage events in den
                    # persistenten Snapshot, damit GET /api/trace/{id} die Kette zeigt.
                    "trace_id": getattr(plan, "trace_id", ""),
                    "routed_via": "plan-executor",
                    "stages": list(getattr(plan, "_stages", [])),
                }
                self.recorder.record(snapshot)
            except Exception as e:
                logger.debug(f"[plan-executor] record failed: {e}")

            # Phase 6.14.4 — also push plan summary into brain-episodic
            # so consolidation + cross-session recall can see plans.
            if snapshot and self._episodic_enabled:
                try:
                    self._episodic_write(snapshot)
                except Exception as e:
                    logger.debug(f"[plan-executor] episodic write failed: {e}")

            # Phase 1 — episodisches Tagebuch: EINE Zeile pro Plan in die
            # geteilte Queue. NICHT direkt ins dual_graph: der HTTP-Prozess
            # (brain-core) hat N uvicorn-Worker und startet den
            # MemoryConsolidator nicht (BRAIN_BACKGROUND_LOOPS=0) — solche
            # Writes sind fluechtig und pro Worker verschieden. Der Drain im
            # Loop-Prozess (core/multihop_diary_drain.py) ist der einzige
            # Schreiber ins dual_graph, das persistiert wird.
            # enqueue_plan wirft nie.
            try:
                from core.multihop_kotlin_adapter import (
                    enqueue_plan, ingest_enabled,
                )
                if executed:
                    _tc = ""
                    if os.environ.get("TASK_CLASS_CLUSTERING", "0") in ("1", "true", "True"):
                        try:
                            from core.task_class_clusterer import TaskClassClusterer
                            _tc = TaskClassClusterer().cluster_id(plan.intent or "")
                        except Exception:
                            _tc = ""
                    _queued = enqueue_plan(
                        plan, executed,
                        trace_id=getattr(plan, "trace_id", "") or "",
                        task_class_id=_tc,
                    )
                    # A False here is only a FAILURE if we actually expected a
                    # write: `executed` is non-empty (checked above) and the
                    # ingest flag is on. A False from a flag-off ingest is a
                    # deliberate no-op, not a lost episode — do not count it.
                    if _queued:
                        with self._lock:
                            self.stats["diary_enqueued"] += 1
                    elif ingest_enabled():
                        with self._lock:
                            self.stats["diary_enqueue_failures"] += 1
                            _fails = self.stats["diary_enqueue_failures"]
                        # Loud on the FIRST failure (a broken queue = every
                        # future episode is lost, that must not hide in debug
                        # logs), then only every 50th — a persistent failure
                        # should be visible, not a log bomb.
                        if _fails == 1 or _fails % _DIARY_FAIL_LOG_EVERY == 0:
                            logger.warning(
                                "[plan-executor] diary enqueue FAILED for plan "
                                "%s — the episode is lost (the queue is the only "
                                "path to persistent memory). Running failures: %d",
                                plan.plan_id, _fails,
                            )
            except Exception as e:
                logger.debug(f"[plan-executor] diary enqueue skipped: {e}")

            # Phase 11.U.A — drop from active-plans dict, then resume
            # discourse only if this was the LAST plan running.
            is_last_plan = False
            with self._active_plans_lock:
                self._active_plans.pop(plan.plan_id, None)
                is_last_plan = len(self._active_plans) == 0
                # Update back-compat shims to point at remaining plan or None
                if self._active_plans:
                    pid, info = min(
                        self._active_plans.items(),
                        key=lambda kv: kv[1]["started_at"],
                    )
                    self._active_plan_id = pid
                    self._active_plan_started_at = info["started_at"]
                else:
                    self._active_plan_id = None
                    self._active_plan_started_at = None

            try:
                if de is not None and is_last_plan:
                    de.resume()
            except Exception:
                pass

            try:
                self._exec_semaphore.release()
            except Exception:
                pass

    def stats_dict(self) -> Dict[str, Any]:
        s = dict(self.stats)
        if s["plans_executed"] > 0:
            s["avg_hops_per_plan"] = round(
                s["hops_executed"] / s["plans_executed"], 2,
            )
            s["avg_elapsed_s"] = round(
                s["total_elapsed_s"] / s["plans_executed"], 2,
            )
        return s

    # ── Internals ──────────────────────────────────────────────

    def _exec_hop(
        self, hop: HopSpec, state: Dict[str, Any],
        plan_ctx: Optional[Dict[str, Any]] = None,
    ) -> HopResult:
        """Resolve template, build executor, call, validate, capture KG hits.

        Phase 11.U.A — `plan_ctx` carries the per-plan info (decision_context,
        intent, rationale, plan_id) that used to live as instance attrs. Passing
        it explicitly makes multi-plan execution race-free.
        """
        plan_ctx = plan_ctx or {}
        t0 = time.time()
        repeat_ctx = getattr(hop, "_repeat_ctx", None)
        rendered_arg = _render_template(hop.arg_template, state, repeat_ctx=repeat_ctx)

        # KG-hit capture (cheap — top-3 semantic hits for the hop description)
        kg_hits = self._capture_kg_hits(hop, rendered_arg)

        # Resolve target — prefer explicit, else look up via capability_router
        target = hop.execution_target
        if not target and hop.capability and self.capability_router is not None:
            try:
                detail = self.capability_router.get_capability(hop.capability)
                if detail:
                    target = detail.get("execution_target")
                    if not hop.arg_kwarg:
                        hop.arg_kwarg = detail.get("arg_kwarg")
                    if not hop.validator and detail.get("validator"):
                        hop.validator = detail.get("validator")
            except Exception as e:
                # Phase 1 — hard failure: gate False (see contract_pass_from)
                return HopResult(
                    step_id=hop.step_id, ok=False,
                    error=f"capability lookup: {type(e).__name__}: {e}",
                    capability=hop.capability, target=None,
                    rendered_arg=rendered_arg, kg_hits=kg_hits,
                    elapsed_s=time.time() - t0,
                    contract_pass=False, reward=-1.0,
                )

        # Canonical n8n events are declared in config/space_agent_registry.yml.
        # Resolve them without duplicating the registry's MCP tool names.
        if not target and hop.capability:
            try:
                from .capability_targets import resolve_registry_execution_target
                target = resolve_registry_execution_target(hop.capability)
            except Exception as e:
                if str(hop.capability).startswith("n8n."):
                    return HopResult(
                        step_id=hop.step_id, ok=False,
                        error=f"n8n registry lookup: {type(e).__name__}: {e}",
                        capability=hop.capability, target=None,
                        rendered_arg=rendered_arg, kg_hits=kg_hits,
                        elapsed_s=time.time() - t0,
                        contract_pass=False, reward=-1.0,
                    )

        # Phase 11.B — if registry maps this capability/event to an OpenFang agent,
        # build a vibemind.intent.v1 envelope and route through that agent
        # instead of direct-calling. The agent's MCP-allowed list contains the
        # right MCP-server (e.g. spaces-ideas), so Sonnet there picks the tool
        # and runs it with full context (recall+self_prior+previous_outputs).
        # If registry doesn't claim this event, falls back to direct target.
        try:
            from .agent_yaml_registry import get_registry
            from . import intent_envelope as _envelope_mod
            _registry = get_registry()
            # Map capability name to event_id (e.g. bubble_create -> bubble.create)
            cap_to_event = {
                "bubble_create": "bubble.create",
                "bubble_update": "bubble.update",
                "bubble_evaluate": "bubble.evaluate",
                "bubble_delete": "bubble.delete",
                "idea_create": "idea.create",
                "idea_add": "idea.create",
                "idea_update": "idea.update",
                "idea_expand": "idea.expand",
                "idea_connect": "idea.connect",
                "idea_to_project": "idea.to_project",
                "code_generate": "code.generate",
                "code_modify": "code.modify",
                "code_status": "code.status",
                "code_show": "code.show",
                "code_preview_start": "code.preview.start",
                "code_preview_stop": "code.preview.stop",
                "code_list": "code.list",
                "code_cancel": "code.cancel",
            }
            event_id = cap_to_event.get(hop.capability or "", hop.capability or "")
            desktop_route = None
            if hop.capability in ("desktop_skill", "browser_automation"):
                from .desktop_orchestration import DesktopOrchestration
                desktop_route = DesktopOrchestration.from_repository().resolve_capability(
                    hop.capability or "", plan_ctx.get("plan_intent", "") or hop.description
                )
                event_id = desktop_route.event_id
                confirmed = event_id in plan_ctx.get("confirmed_events", set())
                if desktop_route.requires_confirmation and not confirmed:
                    return HopResult(
                        step_id=hop.step_id,
                        ok=False,
                        error=f"confirmation required for mutating desktop event '{event_id}'",
                        capability=hop.capability,
                        target=target,
                        rendered_arg=rendered_arg,
                        kg_hits=kg_hits,
                        elapsed_s=time.time() - t0,
                        contract_pass=False,
                        reward=-1.0,
                    )
            if "." not in event_id:
                # If the capability already has a namespace.action pattern
                # in some other form, leave as-is; otherwise it won't match
                # a registry entry and we'll fall back to direct.
                pass
            assigned_agent = _registry.get_event_agent(event_id) if event_id else None

            # Explicit remote executors already are the execution authority
            # (n8n-mcp, coding-engine). Minibook targets return a structured,
            # redacted truth envelope from the external service. Re-routing any
            # of them through an LLM agent would discard that contract and
            # could turn prose into apparent success.
            preserve_structured_target = event_id.startswith("minibook.")
            if (assigned_agent and target
                    and not target.startswith(("openfang:", "n8n-mcp:", "coding-engine:"))
                    and not preserve_structured_target):
                # Probe: is the agent reachable in OpenFang? If not, skip
                # Phase 11.B routing and fall through to the direct target.
                _agent_known = False
                try:
                    _of_url = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200")
                    _r = __import__("requests").get(f"{_of_url}/api/agents", timeout=3)
                    if _r.ok:
                        _ag = _r.json()
                        _ag_list = _ag if isinstance(_ag, list) else _ag.get("agents", [])
                        _agent_known = any(
                            a.get("name") == assigned_agent for a in _ag_list
                        )
                except Exception as _e:
                    logger.debug(f"[plan-executor] openfang probe: {_e}")

                if _agent_known:
                    # Build envelope and override target
                    params = {}
                    if isinstance(rendered_arg, dict):
                        params = rendered_arg
                    elif isinstance(rendered_arg, str):
                        try:
                            params = json.loads(rendered_arg)
                            if not isinstance(params, dict):
                                params = {"value": params}
                        except Exception:
                            params = {"value": rendered_arg}
                    dc = plan_ctx.get("decision_context") or {}
                    envelope = _envelope_mod.build_envelope(
                        event_id=event_id,
                        params=params,
                        plan_intent=plan_ctx.get("plan_intent", ""),
                        plan_rationale=plan_ctx.get("plan_rationale", ""),
                        plan_id=plan_ctx.get("plan_id", ""),
                        step_id=hop.step_id,
                        preferred_tool=hop.capability or "",
                        decision_context=dc,
                        prev_outputs=state if state else {},
                    )
                    target = f"openfang:{assigned_agent}"
                    rendered_arg = _envelope_mod.envelope_to_message(envelope)
                    hop.arg_kwarg = None
                    logger.info(
                        f"[plan-executor] Phase 11.B route: {event_id} via openfang:{assigned_agent}"
                    )
                else:
                    logger.info(
                        f"[plan-executor] Phase 11.B: agent '{assigned_agent}' "
                        f"not in OpenFang — using direct target"
                    )
        except Exception as e:
            logger.debug(f"[plan-executor] Phase 11.B routing skipped: {e}")

        if not target:
            # L4 — GapSentinel (the REAL multihop NO_TOOL point). A hop whose capability
            # resolves to NO execution_target = the brain has no tool to run it (the
            # planner referenced an unknown/unresolvable capability). This is the multihop
            # analog of the discourse route()->None signal, grounded in execution (not the
            # answer text). Flag-gated (CAPABILITY_GAP_ENABLED); fire-and-forget daemon
            # dispatch to the gap-filer agent (files ONE issue per capability, dedup'd).
            try:
                from core import capability_gap as _gap
                if _gap.ENABLED:
                    import threading
                    _pc = plan_ctx or {}
                    _g = _gap.make_gap(
                        _gap.NO_TOOL,
                        missing_capability=hop.capability or hop.description,
                        intent=hop.description,
                        failure_patterns=[f"no execution target for capability '{hop.capability}'"],
                        evidence=f"trace_id={_pc.get('trace_id', '') or ''}",
                    )
                    threading.Thread(
                        target=_gap.handle, args=(_g,),
                        kwargs=dict(live=False, dispatcher=_gap.default_dispatcher),
                        daemon=True,
                    ).start()
            except Exception:
                pass  # never let L4 break execution
            return HopResult(
                step_id=hop.step_id, ok=False,
                error=f"no execution target for capability '{hop.capability}'",
                capability=hop.capability, target=None,
                rendered_arg=rendered_arg, kg_hits=kg_hits,
                elapsed_s=time.time() - t0,
                contract_pass=False, reward=-1.0,
            )

        # Build the right executor for the target prefix (Phase 4)
        try:
            from .capability_targets import build_executor
            exe = build_executor(target)
        except Exception as e:
            return HopResult(
                step_id=hop.step_id, ok=False,
                error=f"executor build: {e}",
                capability=hop.capability, target=target,
                rendered_arg=rendered_arg, kg_hits=kg_hits,
                elapsed_s=time.time() - t0,
                contract_pass=False, reward=-1.0,
            )

        # Call with retry support
        last = None
        # Phase 11.P — pass plan intent + step description as `_intent`/`_description`
        # so tools can re-extract auxiliary args the planner couldn't fit
        # into a single (arg_kwarg, arg_template) pair (e.g. update_bubble
        # needs both source-name AND new-name).
        _extra = {
            "_intent": plan_ctx.get("plan_intent", "") or "",
            "_description": hop.description or "",
            "_step_id": hop.step_id or "",
            # Phase 11.U.H — supabase: idea.format / idea.llm serve 15 / 6
            # capability variants from one op; they read _capability to
            # pick the right one (idea_format_mindmap vs _swot, etc).
            "_capability": getattr(hop, "capability", "") or "",
        }
        # Dynamic tool scope (plans/dynamic-agent-tools-prompt.md, Phase 2):
        # Fuer openfang:-Agenten (skill-coordinator/desktop/brain-coder-*/...) waehlt
        # der ToolScopeSelector pro Intent SEMANTISCH die relevanten Tools + baut
        # einen Prompt-Focus, den OpenFangExecutor als message-Praefix setzt
        # (lenkt das Agent-LLM weg vom 71-Tool-Loop). Default-off via
        # DYNAMIC_TOOL_SCOPE; graceful — bei jedem Fehler bleibt _extra unveraendert
        # (= heutiges Verhalten). _tool_allowlist wird mitgegeben fuer den spaeteren
        # per-Request-Rust-Filter; heute wirkt nur _system_prompt_focus.
        if (os.environ.get("DYNAMIC_TOOL_SCOPE", "0") not in ("0", "false", "False")
                and isinstance(target, str) and target.startswith("openfang:")):
            try:
                from .tool_scope_selector import get_selector
                _agent = target.split(":", 1)[1].strip()
                _allow, _focus = get_selector().select_tools(
                    _extra["_intent"] or rendered_arg or "", agent_name=_agent)
                if _focus:
                    _extra["_system_prompt_focus"] = _focus
                if _allow:
                    _extra["_tool_allowlist"] = _allow
            except Exception as e:  # noqa: BLE001 — nie den Hop daran scheitern lassen
                logger.warning(f"[plan_exec] tool-scope skipped ({e})")
        for attempt in range(max(1, hop.retries)):
            try:
                if hop.arg_kwarg:
                    last = exe.call_with_arg(rendered_arg, arg_kwarg=hop.arg_kwarg,
                                             extra_params=_extra)
                else:
                    last = exe.call_with_arg(rendered_arg, extra_params=_extra)
            except Exception as e:
                last = {
                    "ok": False,
                    "error": f"executor crash: {type(e).__name__}: {e}",
                    "elapsed_s": 0.0,
                    "target": target,
                }
            if last.get("ok"):
                break

        ok = bool(last.get("ok"))
        result_payload = last.get("result")
        err = None if ok else (last.get("error") or "executor returned not ok")

        # Phase 9.0 — extract MCP tool-call trace from streaming OpenFang
        # responses. Other executor kinds (direct, brain, http) return
        # plain payloads without tool_calls — that's fine, list stays empty.
        captured_tool_calls: List[Dict[str, Any]] = []
        if isinstance(result_payload, dict):
            tcs = result_payload.get("tool_calls")
            if isinstance(tcs, list):
                captured_tool_calls = tcs

        # Validation (Phase 3)
        verdict = None
        if ok and hop.validator and self.validator is not None:
            try:
                verdict = self.validator.validate(
                    hop.validator,
                    intent=hop.description,
                    arg=rendered_arg,
                    raw_result=result_payload,
                )
                # on_fail=block converts to overall fail
                if verdict and not verdict.get("valid") and verdict.get("on_fail") == "block":
                    ok = False
                    err = f"validator blocked: {verdict.get('reason')}"
                    with self._lock:
                        self.stats["validator_blocks"] += 1
            except Exception as e:
                logger.warning(f"[plan-executor] validator threw: {e}")
                verdict = {"valid": False, "reason": f"validator error: {e}"}

        # Baustein D.1 — ground-truth → thought-stream. If the validator ran a
        # `truth:` check, push the WORLD-observed verdict (not the claim) back
        # into the thinking loop as an event, so reflections are grounded in
        # what actually happened. Best-effort; never affects execution.
        if verdict is not None and ("verified" in verdict):
            v = verdict.get("verified")
            try:
                cte = getattr(self, "_continuous_thinking", None)
                if cte is not None:
                    kind = ("action_verified" if v is True
                            else "action_unverified" if v is None
                            else "action_refuted")
                    cte.record_event(kind, {
                        "intent": hop.description,
                        "capability": hop.capability,
                        "claimed_ok": bool(ok),
                        "verified": v,
                        "signal": verdict.get("verify_signal") or {},
                        "reason": verdict.get("reason", ""),
                    })
            except Exception:
                pass
            # Baustein D.2 — mirror the verified step into the execution-log
            # collection (claimed-vs-verified diff is queryable via RAG).
            try:
                if self._exec_log is not None and self._exec_log.enabled:
                    pc = plan_ctx or {}
                    self._exec_log.record_step(
                        plan_id=pc.get("plan_id", "") or "",
                        hop_k=getattr(hop, "step_id", None),
                        intent=hop.description, stage="verify",
                        capability=hop.capability, source="validator",
                        claimed_ok=bool(ok), verified=v,
                        verify_signal=verdict.get("verify_signal") or {},
                        reason=verdict.get("reason", ""),
                        trace_id=pc.get("trace_id", "") or "",
                    )
            except Exception:
                pass

        # Phase 6.13 — Optional TriBE bio-grounding. Off by default; opt
        # in via MULTIHOP_TRIBE_GROUNDING=1. Captures Brain's 8 bridge
        # activations (cortex/limbic/defense/motor/visceral/social/
        # integration/memory) for the hop's result text. UI shows them
        # as bridge-bars on the hop card.
        bridges = self._maybe_tribe_bridges(hop, result_payload, ok)

        # Phase 6.14.3 — KG settle-fence. After a hop that writes into
        # KG/Supabase, wait briefly so downstream hops see the new state.
        # Fixed-window (env MULTIHOP_KG_SETTLE_S, default 0). Enabled
        # automatically for capabilities whose name suggests a write.
        if ok and self._kg_settle_s > 0 and _looks_like_kg_write(hop):
            time.sleep(self._kg_settle_s)
            with self._lock:
                self.stats["kg_settles"] += 1

        # Baustein D.2 — trace stage `hop_failed`. Capture every failed hop with
        # its error + source so failures (esp. planner-team) are RAG-queryable.
        if not ok:
            try:
                if self._exec_log is not None and self._exec_log.enabled:
                    pc = plan_ctx or {}
                    src = "planner" if "plan" in (hop.capability or "").lower() else "executor"
                    self._exec_log.record_step(
                        plan_id=pc.get("plan_id", "") or "",
                        hop_k=getattr(hop, "step_id", None),
                        intent=hop.description, stage="hop_failed",
                        capability=hop.capability, source=src,
                        claimed_ok=False, verified=None,
                        reason=str(err or "hop failed")[:400],
                        trace_id=pc.get("trace_id", "") or "",
                    )
            except Exception:
                pass

        # C2 — Timeout-Sentinel: a timed-out hop -> ONE GitHub issue per capability.
        # Flag-gated (CAPABILITY_TIMEOUT_ISSUE_ENABLED); fire-and-forget in a daemon
        # thread so the gh-subprocess filing never blocks plan execution. Filing is
        # OpenFang-free on purpose (a timeout is often OpenFang itself being down).
        if not ok:
            try:
                from core.timeout_sentinel import (
                    ENABLED as _TO_ENABLED, is_timeout as _is_to,
                    on_hop_timeout as _on_to,
                )
                if _TO_ENABLED and _is_to(err):
                    import threading
                    _pc = plan_ctx or {}
                    threading.Thread(
                        target=_on_to,
                        args=(hop.capability or "",),
                        kwargs=dict(
                            intent=hop.description, target=target,
                            trace_id=_pc.get("trace_id", "") or "",
                            elapsed_s=round(time.time() - t0, 2),
                            error=str(err or ""),
                        ),
                        daemon=True,
                    ).start()
            except Exception:
                pass  # never let C2 break execution

        # L4 — GapSentinel in the REAL execution path. The multihop planner is a
        # catch-all (it always plans *something*), so the clean NO_TOOL signal is not
        # route()->None but an EXECUTION failure that proves no tool exists: a hop that
        # fails because the capability/agent is genuinely unresolvable (planner
        # hallucinated a cap, no executor) — NOT a transient outage (C2 owns timeouts;
        # is_no_tool_error filters OpenFang-down/connection). Grounded in the failed
        # hop (D's verdict), never the answer text. Flag-gated (CAPABILITY_GAP_ENABLED),
        # fire-and-forget daemon dispatch to the gap-filer (files ONE issue, dedup'd).
        if not ok:
            try:
                from core import capability_gap as _gap
                if _gap.ENABLED and _gap.is_no_tool_error(err):
                    import threading
                    _pc = plan_ctx or {}
                    _g = _gap.make_gap(
                        _gap.NO_TOOL,
                        missing_capability=hop.capability or hop.description,
                        intent=hop.description,
                        failure_patterns=[str(err or "")[:200]],
                        evidence=f"trace_id={_pc.get('trace_id', '') or ''}",
                    )
                    threading.Thread(
                        target=_gap.handle, args=(_g,),
                        kwargs=dict(live=False, dispatcher=_gap.default_dispatcher),
                        daemon=True,
                    ).start()
            except Exception:
                pass  # never let L4 break execution

        # Phase 7.3 — record provider outcome for adaptive routing
        try:
            self.record_provider_outcome(hop.capability, target, ok)
        except Exception:
            pass

        # Phase 1 — gate-derived learning signal (outcome-gate semantics — UNVERIFIED
        # never trains positive). contract_pass mirrors the truth-validator verdict
        # when one ran; ok=False always fails the contract regardless of a validator.
        _cp = contract_pass_from(ok, verdict)
        return HopResult(
            step_id=hop.step_id, ok=ok, result=result_payload, error=err,
            elapsed_s=round(time.time() - t0, 2),
            validator_verdict=verdict,
            capability=hop.capability, target=target,
            rendered_arg=rendered_arg, kg_hits=kg_hits,
            retried=max(0, attempt),
            bridges=bridges,
            tool_calls=captured_tool_calls,
            contract_pass=_cp,
            reward=(1.0 if _cp is True else (-1.0 if _cp is False else 0.0)),
        )

    def _maybe_tribe_bridges(
        self, hop: HopSpec, result_payload: Any, ok: bool,
    ) -> Optional[Dict[str, float]]:
        """Phase 6.13 — gated TriBE call. Returns 8-bridge dict or None.
        Never raises (TriBE may be disabled, lazy-loading, or in dummy mode)."""
        if os.environ.get("MULTIHOP_TRIBE_GROUNDING", "0") not in ("1", "true", "True"):
            return None
        try:
            text = self._tribe_text(hop, result_payload, ok)
            if not text:
                return None
            from core.tribe_encoder import bridge_levels_for_text
            br = bridge_levels_for_text(text)
            if not br:
                return None
            # Truncate to known bridge keys + round for clean JSON
            return {k: round(float(v), 3) for k, v in br.items()}
        except Exception as e:
            logger.debug(f"[plan-executor] tribe hook failed: {e}")
            return None

    @staticmethod
    def _tribe_text(hop: HopSpec, result_payload: Any, ok: bool) -> str:
        """Pick a stimulus string for TriBE. Prefer the hop description +
        a short result preview — combined ~400 chars max so we don't
        burn TriBE-latency on huge structured payloads."""
        parts: List[str] = []
        if hop.description:
            parts.append(hop.description.strip())
        if ok and result_payload is not None:
            try:
                preview = repr(result_payload)
                if len(preview) > 240:
                    preview = preview[:240] + "..."
                parts.append(preview)
            except Exception:
                pass
        text = " | ".join(parts)
        return text[:400]

    def _capture_kg_hits(self, hop: HopSpec, rendered_arg: Any) -> List[Dict[str, Any]]:
        """Cheap KG-search using the rendered hop arg or hop description.
        Best-effort; never fails the hop. Returns a slim list for the UI."""
        if self.kg is None:
            return []
        try:
            query = str(rendered_arg) if rendered_arg else hop.description
            if not query:
                return []
            hits = []
            try:
                # QdrantKG.search(query, limit, score_threshold) — most flexible
                results = self.kg.search(query, limit=3, score_threshold=0.4)
            except TypeError:
                results = self.kg.search(query, limit=3)
            for h in results or []:
                if isinstance(h, dict):
                    hits.append({
                        "title": h.get("title") or h.get("payload", {}).get("title"),
                        "node_type": h.get("node_type") or h.get("payload", {}).get("node_type"),
                        "score": h.get("score"),
                        "collection": h.get("collection"),
                    })
            return hits[:3]
        except Exception as e:
            logger.debug(f"[plan-executor] kg capture failed: {e}")
            return []

    def _publish_started(self, hops: List[HopSpec], state: Dict[str, Any]) -> None:
        for h in hops:
            self._publish("hop_started", {
                "step_id": h.step_id,
                "description": h.description,
                "capability": h.capability,
                "execution_target": h.execution_target,
                "depends_on": list(h.depends_on),
                "rendered_arg": _render_template(
                    h.arg_template, state,
                    repeat_ctx=getattr(h, "_repeat_ctx", None),
                ),
            })


# ── Helpers ───────────────────────────────────────────────────────────


# Phase 6.14.3 — capabilities whose results need a settle-fence so the
# next hop reads consistent KG/Supabase state. Match by name OR by the
# direct: target containing one of these substrings.
_KG_WRITE_HINTS = (
    "create", "add", "promote", "score", "update", "delete", "move",
    "_set", "save", "store", "register", "seed", "consolidate",
)


def _looks_like_kg_write(hop) -> bool:
    cap = (getattr(hop, "capability", None) or "").lower()
    tgt = (getattr(hop, "execution_target", None) or "").lower()
    for h in _KG_WRITE_HINTS:
        if h in cap or h in tgt:
            return True
    return False


_REPEAT_TOKEN_RE = re.compile(
    r"\{\{\s*(item|loop\.index0?|loop\.value)\s*\}\}",
)


def _render_template(
    tmpl: str,
    state: Dict[str, Any],
    repeat_ctx: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a hop's arg_template:
       - `{{state.foo}}`    → state['foo']  (dotted path supported)
       - `{{item}}`         → repeat_ctx['item']
       - `{{loop.index}}`   → repeat_ctx['index'] (1-based)
       - `{{loop.index0}}`  → repeat_ctx['index0'] (0-based)
       - `{{loop.value}}`   → repeat_ctx['value']  (alias for item)
    """
    if not tmpl:
        return ""

    def state_repl(m):
        # Phase 11.N — Capture group has the leading `state.` already stripped
        # by the regex. Path can mix dot- and bracket-segments, e.g.
        # `ideas[0]`, `ideas.0`, `foo[2].bar`. Tokenize uniformly.
        raw = m.group(1)
        # Convert bracket-style `[N]` to dot-style `.N` so `re.split(r'\.')`
        # parses both forms identically.
        raw = re.sub(r"\[(\d+)\]", r".\1", raw).strip(".")
        path = [p for p in raw.split(".") if p]
        if not path:
            return ""
        cur: Any = state.get(path[0])
        for p in path[1:]:
            if isinstance(cur, dict):
                cur = cur.get(p)
            elif isinstance(cur, list):
                try:
                    idx = int(p)
                    cur = cur[idx] if -len(cur) <= idx < len(cur) else None
                except (ValueError, TypeError):
                    cur = None
                    break
            else:
                cur = None
                break
        if cur is None:
            return ""
        return str(cur)

    out = _TEMPLATE_RE.sub(state_repl, tmpl)

    if repeat_ctx is not None:
        def repeat_repl(m):
            tok = m.group(1)
            if tok == "item":
                return str(repeat_ctx.get("item", ""))
            if tok == "loop.index":
                return str(repeat_ctx.get("index", ""))
            if tok == "loop.index0":
                return str(repeat_ctx.get("index0", ""))
            if tok == "loop.value":
                return str(repeat_ctx.get("value", repeat_ctx.get("item", "")))
            return ""
        out = _REPEAT_TOKEN_RE.sub(repeat_repl, out)

    return out


def _safe_state_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    """Truncate state values for record/UI so big payloads don't blow JSONL."""
    out: Dict[str, Any] = {}
    for k, v in state.items():
        try:
            s = repr(v)
        except Exception:
            s = "<unrepr>"
        if len(s) > 1500:
            s = s[:1500] + "...<truncated>"
        out[k] = s
    return out


def _hop_event(h: HopSpec, hr: HopResult) -> Dict[str, Any]:
    """Trim hop result for SSE event payload."""
    res = hr.result
    try:
        result_preview = repr(res)[:500]
    except Exception:
        result_preview = "<unrepr>"
    return {
        "step_id": hr.step_id,
        "description": h.description,
        "capability": hr.capability,
        "target": hr.target,
        "ok": hr.ok,
        "error": hr.error,
        "elapsed_s": hr.elapsed_s,
        "validator": hr.validator_verdict,
        "result_preview": result_preview,
        "rendered_arg": hr.rendered_arg,
        "kg_hits": hr.kg_hits,
        "retried": hr.retried,
        "bridges": hr.bridges,
    }
