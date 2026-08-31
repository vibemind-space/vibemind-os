"""Phase 8.3 — Self-Steerer.

Closes the loop: cluster activation → automatic capability dispatch →
result fed back as a thought-event (Phase 7.5) → next cycle re-activates
or quietens the cluster.

This is the autonomous-execution layer the user described: semantic noise
activates regions, activated regions trigger via OpenFang an
execution-reflection loop, the system steers itself.

Design:
  - 30s tick (env SELF_STEER_TICK_S=30)
  - Reads ClusterEngine.get_activations()
  - For each cluster with activation > CLUSTER_DISPATCH_THRESHOLD (env, 0.7):
      1. require ≥2 consecutive_high_ticks (hysteresis — set by ClusterEngine)
      2. require time.time() - last_dispatch_ts > cooldown (default 600s)
      3. require we haven't exceeded the hourly budget cap
      4. look up cluster_capabilities.yaml for the dominant_topic
      5. build executor via capability_targets.build_executor / capability_router
      6. call with the rendered prompt
      7. on result: ClusterEngine.mark_dispatched + push event to CTE
  - Hourly budget: SELF_STEER_MAX_DISPATCHES_PER_HOUR=6
    persisted to data/self_steer_budget.json (timestamp ring)
  - Re-arm: cluster has to fall under 0.5 before it can fire again

Reuse:
  - core/capability_targets.py:build_executor  → multi-protocol dispatch
  - core/capability_router.py:get_capability    → resolve capability name
  - core/cluster_engine.py:get_activations      → snapshot + mark_dispatched
  - brain_chat.continuous_thinking.record_event → loop-back as thought event
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# ── Config ──────────────────────────────────────────────────────────────

TICK_INTERVAL_S = float(os.environ.get("SELF_STEER_TICK_S", "30"))
DISPATCH_THRESHOLD = float(os.environ.get("CLUSTER_DISPATCH_THRESHOLD", "0.7"))
REARM_THRESHOLD = float(os.environ.get("CLUSTER_REARM_THRESHOLD", "0.5"))
DEFAULT_COOLDOWN_S = float(os.environ.get("CLUSTER_COOLDOWN_S", "600"))
HOURLY_CAP = int(os.environ.get("SELF_STEER_MAX_DISPATCHES_PER_HOUR", "6"))
HYSTERESIS_TICKS = int(os.environ.get("SELF_STEER_HYSTERESIS_TICKS", "2"))
ENABLED = os.environ.get("SELF_STEER_ENABLED", "1") not in ("0", "false", "False")

CONFIG_PATH = Path(os.environ.get(
    "CLUSTER_CAPABILITIES_PATH",
    str(Path(__file__).resolve().parent.parent / "configs" / "cluster_capabilities.yaml"),
))
BUDGET_PATH = Path(os.environ.get(
    "SELF_STEER_BUDGET_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "self_steer_budget.json"),
))


# ── Mappings ────────────────────────────────────────────────────────────


@dataclass
class ClusterMapping:
    dominant_topic: str
    capability: str
    prompt: str = ""
    cooldown_s: float = DEFAULT_COOLDOWN_S


# ── Engine ──────────────────────────────────────────────────────────────


class SelfSteerer:
    """30s loop. Watches cluster activations. Fires capabilities."""

    def __init__(
        self,
        cluster_engine,
        capability_router=None,
        brain_chat=None,
        decision_graph=None,
    ) -> None:
        self.cluster_engine = cluster_engine
        self.capability_router = capability_router
        self.brain_chat = brain_chat
        self.decision_graph = decision_graph
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._mappings: List[ClusterMapping] = []
        self._fired_at: Deque[float] = deque(maxlen=HOURLY_CAP * 4)
        self._armed: Dict[str, bool] = {}  # cluster_id -> armed (after re-arm)
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "dispatches": 0,
            "skipped_cooldown": 0,
            "skipped_budget": 0,
            "skipped_no_mapping": 0,
            "skipped_hysteresis": 0,
            "errors": 0,
            "last_error": None,
            "last_dispatch_ts": None,
            "last_dispatch_cluster": None,
            "last_dispatch_capability": None,
        }
        self._load_mappings()
        self._load_budget()

    # ── Mappings + budget ─────────────────────────────────────────────

    def _load_mappings(self) -> None:
        try:
            if not CONFIG_PATH.exists():
                logger.warning(f"[self-steer] config missing: {CONFIG_PATH}")
                return
            data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or []
            self._mappings = [
                ClusterMapping(
                    dominant_topic=str(d.get("dominant_topic", "")).lower(),
                    capability=str(d.get("capability", "")),
                    prompt=str(d.get("prompt") or ""),
                    cooldown_s=float(d.get("cooldown_s") or DEFAULT_COOLDOWN_S),
                )
                for d in data if isinstance(d, dict)
            ]
            logger.info(f"[self-steer] loaded {len(self._mappings)} cluster→capability mappings")
        except Exception as e:
            logger.warning(f"[self-steer] mapping load failed: {e}")

    def reload_mappings(self) -> int:
        with self._lock:
            self._mappings = []
            self._load_mappings()
            return len(self._mappings)

    def set_capability_router(self, router) -> None:
        """Inject capability_router after init — brain_server.py builds the
        router AFTER SelfSteerer (init ordering)."""
        self.capability_router = router

    def attach_decision_graph(self, dg) -> None:
        """Phase 8.B — wire Neo4j so dispatches become visible in the
        decision-theatre UI."""
        self.decision_graph = dg

    def _load_budget(self) -> None:
        try:
            if BUDGET_PATH.exists():
                data = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
                self._fired_at = deque(
                    [float(t) for t in data.get("fired_at", [])],
                    maxlen=HOURLY_CAP * 4,
                )
        except Exception as e:
            logger.debug(f"[self-steer] budget load failed: {e}")

    def _persist_budget(self) -> None:
        try:
            BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
            now = time.time()
            # Drop entries older than 1h before persist
            recent = [t for t in self._fired_at if now - t < 3600]
            self._fired_at = deque(recent, maxlen=HOURLY_CAP * 4)
            BUDGET_PATH.write_text(
                json.dumps({"fired_at": list(self._fired_at)}),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug(f"[self-steer] budget persist failed: {e}")

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[self-steer] disabled via SELF_STEER_ENABLED=0")
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="SelfSteererLoop",
        )
        self._worker.start()
        logger.info(
            f"[self-steer] started "
            f"(tick={TICK_INTERVAL_S}s, threshold={DISPATCH_THRESHOLD}, "
            f"cap/hr={HOURLY_CAP})"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        # Initial delay so cluster engine has time to populate
        self._stop.wait(60.0)
        while not self._stop.is_set():
            try:
                self.tick_once()
                self.stats["ticks"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"{type(e).__name__}: {e}"
                logger.warning(f"[self-steer] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Tick ──────────────────────────────────────────────────────────

    def tick_once(self) -> Dict[str, Any]:
        """One scan + maybe-dispatch. Returns summary."""
        if self.cluster_engine is None:
            return {"ok": False, "reason": "no cluster engine"}

        clusters = self.cluster_engine.get_activations()
        now = time.time()
        fired_this_tick: List[Dict[str, Any]] = []

        # Hourly cap check (drop stale entries first)
        recent = [t for t in self._fired_at if now - t < 3600]
        self._fired_at = deque(recent, maxlen=HOURLY_CAP * 4)

        for c in clusters:
            cid = c.get("cluster_id")
            act = float(c.get("activation") or 0.0)

            # Re-arm: if cluster is below re-arm threshold, mark armed
            if act < REARM_THRESHOLD:
                self._armed[cid] = True
                continue

            if act < DISPATCH_THRESHOLD:
                continue

            # Hysteresis: must have been high for ≥N consecutive ticks
            if int(c.get("consecutive_high_ticks") or 0) < HYSTERESIS_TICKS:
                self.stats["skipped_hysteresis"] += 1
                continue

            # Re-arm gate: must have dropped below REARM since last fire
            if not self._armed.get(cid, True):
                continue

            # Per-cluster cooldown
            mapping = self._find_mapping(c.get("dominant_topic") or c.get("label") or "")
            cooldown = mapping.cooldown_s if mapping else DEFAULT_COOLDOWN_S
            last_dispatch = float(c.get("last_dispatch_ts") or 0.0)
            if last_dispatch > 0 and (now - last_dispatch) < cooldown:
                self.stats["skipped_cooldown"] += 1
                continue

            # Hourly budget
            if len(self._fired_at) >= HOURLY_CAP:
                self.stats["skipped_budget"] += 1
                continue

            # No mapping → log + skip
            if mapping is None:
                self.stats["skipped_no_mapping"] += 1
                continue

            # Fire
            result = self._dispatch(c, mapping)
            fired_this_tick.append({
                "cluster_id": cid,
                "capability": mapping.capability,
                "ok": result.get("ok"),
            })
            self._fired_at.append(now)
            self._armed[cid] = False  # require re-arm
            self.cluster_engine.mark_dispatched(cid)
            self.stats["dispatches"] += 1
            self.stats["last_dispatch_ts"] = now
            self.stats["last_dispatch_cluster"] = cid
            self.stats["last_dispatch_capability"] = mapping.capability
            self._persist_budget()

        return {"ok": True, "fired": fired_this_tick, "candidates": len(clusters)}

    # ── Mapping resolution ────────────────────────────────────────────

    def _find_mapping(self, topic: str) -> Optional[ClusterMapping]:
        topic = (topic or "").lower().strip()
        if not topic:
            return None
        # Exact match first
        for m in self._mappings:
            if m.dominant_topic == topic:
                return m
        # Substring fallback (cluster topic CONTAINS map key)
        for m in self._mappings:
            if m.dominant_topic and m.dominant_topic in topic:
                return m
        # Reverse substring (map key CONTAINS topic — handles short topics)
        for m in self._mappings:
            if topic and len(topic) > 3 and topic in m.dominant_topic:
                return m
        return None

    # ── Dispatch ──────────────────────────────────────────────────────

    def _dispatch(self, cluster: Dict[str, Any], mapping: ClusterMapping) -> Dict[str, Any]:
        """Resolve capability → executor → call → loop-back as thought."""
        # Resolve capability to an executor target
        target = mapping.capability  # could be "openfang:brain-coder" OR "code_search"
        original = target
        if ":" not in target and self.capability_router is not None:
            try:
                detail = self.capability_router.get_capability(target)
                if detail and detail.get("execution_target"):
                    target = detail["execution_target"]
                elif detail and detail.get("primary"):
                    # Broadcast capability — no direct target, fall back to OpenFang
                    primary = detail["primary"][0] if detail["primary"] else None
                    if primary:
                        target = f"openfang:{primary}"
                        logger.info(
                            f"[self-steer] broadcast cap {original!r} -> openfang:{primary}"
                        )
            except Exception as e:
                logger.debug(f"[self-steer] capability resolve failed: {e}")

        # Phase 8 polish — last-resort fallback. If the capability is still
        # unresolved (no router, missing capability, or capability has neither
        # execution_target nor primary agents), pick a default OpenFang agent
        # we know exists. This guarantees that EVERY cluster activation
        # produces a real LLM call instead of silently failing.
        if ":" not in target:
            default_agent = os.environ.get(
                "SELF_STEER_DEFAULT_AGENT", "openfang:brain-coder",
            )
            logger.info(
                f"[self-steer] no target for {original!r}, defaulting to {default_agent}"
            )
            target = default_agent

        if ":" not in target:
            return {"ok": False, "error": f"unresolved capability: {target}"}

        # Render prompt
        try:
            prompt = (mapping.prompt or
                      "Cluster '{label}' active (act={act:.2f}). Top thoughts: {top_thoughts}.")
            prompt = prompt.format(
                label=cluster.get("label") or cluster.get("cluster_id"),
                act=float(cluster.get("activation") or 0.0),
                top_thoughts=" / ".join(cluster.get("top_thoughts") or []),
                cluster_id=cluster.get("cluster_id") or "?",
                topic=cluster.get("dominant_topic") or "",
            )
        except Exception:
            prompt = f"Cluster {cluster.get('cluster_id')} active. Investigate."

        # Build executor
        try:
            from .capability_targets import build_executor
            exe = build_executor(target)
        except Exception as e:
            return {"ok": False, "error": f"executor build: {e}"}

        # Call
        try:
            result = exe.call_with_arg(prompt)
        except Exception as e:
            result = {"ok": False, "error": f"call: {type(e).__name__}: {e}"}

        # Loop-back to ContinuousThinkingEngine (Phase 7.5)
        cte = None
        try:
            cte = (
                self.brain_chat._continuous_thinking
                if self.brain_chat is not None else None
            )
        except Exception:
            cte = None
        if cte is not None and hasattr(cte, "record_event"):
            try:
                summary = ""
                if isinstance(result.get("result"), dict):
                    summary = (result["result"].get("text") or
                               result["result"].get("response") or
                               json.dumps(result["result"])[:200])
                else:
                    summary = str(result.get("result") or result.get("error") or "")[:200]
                cte.record_event("self_steer_dispatch", {
                    "cluster_id": cluster.get("cluster_id"),
                    "capability": mapping.capability,
                    "target": target,
                    "ok": bool(result.get("ok")),
                    "summary": summary[:200],
                })
            except Exception as e:
                logger.debug(f"[self-steer] CTE feedback failed: {e}")

        # Phase 8.B — record dispatch in Neo4j decision graph
        if self.decision_graph is not None and self.decision_graph.is_connected():
            try:
                summary = ""
                if isinstance(result.get("result"), dict):
                    summary = (result["result"].get("text") or
                               result["result"].get("response") or
                               json.dumps(result["result"])[:200])
                else:
                    summary = str(result.get("result") or result.get("error") or "")[:200]
                self.decision_graph.upsert_dispatch(
                    cluster_id=cluster.get("cluster_id"),
                    capability=mapping.capability,
                    target=target,
                    ok=bool(result.get("ok")),
                    summary=summary,
                )
            except Exception as e:
                logger.debug(f"[self-steer] decision-graph dispatch upsert failed: {e}")

        logger.info(
            f"[self-steer] FIRED cluster={cluster.get('cluster_id')} "
            f"-> {target} ok={result.get('ok')}"
        )
        return result

    # ── Stats ─────────────────────────────────────────────────────────

    def stats_dict(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            recent = [t for t in self._fired_at if now - t < 3600]
            return {
                **self.stats,
                "tick_interval_s": TICK_INTERVAL_S,
                "threshold": DISPATCH_THRESHOLD,
                "rearm_threshold": REARM_THRESHOLD,
                "hourly_cap": HOURLY_CAP,
                "hysteresis_ticks": HYSTERESIS_TICKS,
                "running": bool(self._worker and self._worker.is_alive()),
                "mappings_loaded": len(self._mappings),
                "fired_last_hour": len(recent),
            }
