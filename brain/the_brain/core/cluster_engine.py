"""Phase 8.1 — Cluster Engine.

Aggregates thought-clusters with activation-decay so we can drive a
self-steering loop (Phase 8.3) and a galaxy UI (Phase 8.2).

Design — REUSE first, DON'T re-implement:
  - `ThoughtEvolutionEngine.get_manifold()` already runs UMAP-3D + DBSCAN
    on thought embeddings and returns clusters with center_x/y/z,
    dominant_topic, and member-count
  - `MCMPGardener` already maintains `activation_strength` payload on KG
    nodes (decay 0.98 every 10 ticks, bumps from random walks)
  - We only do the cross-cutting aggregation: per-cluster activation
    (sum/normalised over its member nodes), per-cluster decay, and
    co-activation pair tracking

Loop:
  - 60s tick (env CLUSTER_ENGINE_TICK_S=60)
  - Per tick:
      1. snapshot = thought_evolution.get_manifold()
      2. for each cluster: sum activation_strength of member thoughts
         (we look them up in brain-episodic / brain-semantic by tid)
      3. apply CLUSTER_ACTIVATION_DECAY=0.95 to existing cluster scores
         not seen this tick
      4. blend new score with previous (EMA, alpha=0.4) for stability
      5. detect co-activation: any two clusters both >0.4 same tick →
         bump shared edge weight in `_pairs`
  - Persistence: rolling JSONL at data/cluster_state.jsonl (last 1000 ticks)
  - API:
      get_activations() -> List[Dict]
      get_co_activations() -> List[(a, b, weight)]
      bump(cluster_id, delta) -> for manual triggering / smoke tests
      stats_dict() -> for /api/clusters/stats
      start() / stop() / tick_once()

Cluster identity is `dominant_topic` (string) when present, falling back to
numeric `id`. This keeps state stable across DBSCAN re-labelings (Phase 8
risk: clustering jitter mitigation).
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Config ──────────────────────────────────────────────────────────────

TICK_INTERVAL_S = float(os.environ.get("CLUSTER_ENGINE_TICK_S", "60"))
DECAY = float(os.environ.get("CLUSTER_ACTIVATION_DECAY", "0.95"))
EMA_ALPHA = float(os.environ.get("CLUSTER_EMA_ALPHA", "0.4"))
CO_THRESHOLD = float(os.environ.get("CLUSTER_CO_ACTIVATION_THRESHOLD", "0.4"))
def _default_cluster_state_path() -> str:
    """Identity-namespaced cluster_state.jsonl (Phase C).

    ClusterEngine ticks every 60s and appends to this file. It's NOT gated
    by BRAIN_ROLE (the cluster activations drive SelfSteerer/routing, which
    inference replicas still need) — instead the FILE is per-identity so N
    brains never append to the same file. Default identity ->
    "<brain>/data/cluster_state.jsonl" exactly as before.
    """
    base = str(Path(__file__).resolve().parent.parent / "data")
    try:
        from core import config as _cfg
        d = _cfg.checkpoint_dir(kind="", base=base)  # base/<ns?>
        return str(Path(d) / "cluster_state.jsonl")
    except Exception:
        return str(Path(base) / "cluster_state.jsonl")


JSONL_PATH = Path(os.environ.get(
    "CLUSTER_STATE_PATH",
    _default_cluster_state_path(),
))
JSONL_MAX_LINES = int(os.environ.get("CLUSTER_STATE_MAX_LINES", "1000"))


# ── Data classes ────────────────────────────────────────────────────────


@dataclass
class ClusterState:
    cluster_id: str               # stable: dominant_topic or "cluster_<id>"
    raw_id: int                   # numeric DBSCAN label for current snapshot
    label: str                    # human-readable label
    activation: float = 0.0
    member_count: int = 0
    dominant_topic: str = ""
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    avg_fitness: float = 0.0
    top_thoughts: List[str] = field(default_factory=list)
    last_seen_ts: float = 0.0
    last_dispatch_ts: float = 0.0
    fire_count: int = 0
    consecutive_high_ticks: int = 0  # for self-steerer hysteresis

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Engine ──────────────────────────────────────────────────────────────


class ClusterEngine:
    """Aggregates per-cluster activation; runs as a daemon thread."""

    def __init__(
        self,
        brain_chat=None,
        kg=None,
        thought_evolution=None,
        decision_graph=None,
    ) -> None:
        self.brain_chat = brain_chat
        self.kg = kg
        # Optional explicit handle to the evolution engine (otherwise we
        # try to find it via brain_chat._evolution_engine). Bound at start().
        self._thought_evolution = thought_evolution
        # Phase 8.B — DecisionGraph (Neo4j) for persistent visualisation
        self._decision_graph = decision_graph
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        # cluster_id (stable string) -> ClusterState
        self._clusters: Dict[str, ClusterState] = {}
        # frozenset({a,b}) -> weight
        self._pairs: Dict[frozenset, float] = {}
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
            "manifold_unavailable_count": 0,
            "active_cluster_count": 0,
        }

    # ── Lifecycle ──────────────────────────────────────────────────────

    def attach_decision_graph(self, dg) -> None:
        """Phase 8.B — wire Neo4j DecisionGraph for persistent visualisation."""
        self._decision_graph = dg

    def _resolve_evolution_engine(self):
        if self._thought_evolution is not None:
            return self._thought_evolution
        if self.brain_chat is not None:
            return getattr(self.brain_chat, "_evolution_engine", None)
        return None

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="ClusterEngineLoop",
        )
        self._worker.start()
        logger.info(f"[cluster-engine] started (tick={TICK_INTERVAL_S}s)")

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        # Initial delay so brain has time to bootstrap thoughts
        self._stop.wait(20.0)
        while not self._stop.is_set():
            try:
                self.tick_once()
                self.stats["ticks"] += 1
                self.stats["last_tick_ts"] = time.time()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"{type(e).__name__}: {e}"
                logger.warning(f"[cluster-engine] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Tick ───────────────────────────────────────────────────────────

    def tick_once(self) -> Dict[str, Any]:
        """Run one aggregation tick. Returns summary."""
        evo = self._resolve_evolution_engine()
        manifold: Dict[str, Any] = {}
        if evo is not None:
            try:
                manifold = evo.get_manifold()
            except Exception as e:
                self.stats["last_error"] = f"manifold: {e}"
                manifold = {}

        clusters = manifold.get("clusters") or []
        nodes = manifold.get("nodes") or []

        # Phase 8 fallback: if evolution engine has no thoughts yet (e.g.
        # right after boot), build a quick cluster snapshot from the
        # ContinuousThinkingEngine `_thoughts` deque using lightweight
        # category-bucketing. Lets the galaxy UI show SOMETHING immediately
        # without waiting for the evolution-engine to warm up.
        if not clusters:
            try:
                clusters, nodes = self._fallback_clusters_from_cte()
            except Exception as e:
                logger.debug(f"[cluster-engine] cte fallback failed: {e}")

        if not clusters:
            self.stats["manifold_unavailable_count"] += 1
            return {"ok": False, "reason": "no clusters from evolution OR cte fallback"}
        # Build cluster_id -> [thought_id] map from nodes
        members_by_cluster: Dict[int, List[Dict[str, Any]]] = {}
        for n in nodes:
            cid = n.get("cluster_id")
            if cid is None or cid < 0:  # noise label
                continue
            members_by_cluster.setdefault(int(cid), []).append(n)

        with self._lock:
            seen_ids: set = set()
            now = time.time()

            for c in clusters:
                stable_id = self._stable_id(c)
                seen_ids.add(stable_id)
                # Compute new activation as the avg fitness of cluster members
                # (we don't have direct activation_strength on thoughts —
                # fitness is the closest proxy and already trends with use)
                raw_id = int(c.get("id", 0))
                avg_fit = float(c.get("avg_fitness") or 0.0)
                size = int(c.get("size") or 0)
                # Boost slightly by cluster size (more thoughts = more attention)
                size_boost = min(0.3, size / 20.0)
                new_score = max(0.0, min(1.0, avg_fit + size_boost))

                state = self._clusters.get(stable_id)
                if state is None:
                    state = ClusterState(
                        cluster_id=stable_id,
                        raw_id=raw_id,
                        label=c.get("dominant_topic") or f"cluster_{raw_id}",
                        activation=new_score,
                        member_count=size,
                        dominant_topic=c.get("dominant_topic") or "",
                        center_x=float(c.get("center_x") or 0.0),
                        center_y=float(c.get("center_y") or 0.0),
                        center_z=float(c.get("center_z") or 0.0),
                        avg_fitness=avg_fit,
                        top_thoughts=[
                            (n.get("content") or "")[:120]
                            for n in members_by_cluster.get(raw_id, [])[:3]
                        ],
                        last_seen_ts=now,
                    )
                    self._clusters[stable_id] = state
                else:
                    # EMA blend keeps state stable across re-clusterings
                    state.activation = round(
                        EMA_ALPHA * new_score + (1 - EMA_ALPHA) * state.activation,
                        3,
                    )
                    state.raw_id = raw_id
                    state.member_count = size
                    state.dominant_topic = c.get("dominant_topic") or state.dominant_topic
                    state.label = c.get("dominant_topic") or state.label
                    state.center_x = float(c.get("center_x") or 0.0)
                    state.center_y = float(c.get("center_y") or 0.0)
                    state.center_z = float(c.get("center_z") or 0.0)
                    state.avg_fitness = avg_fit
                    state.top_thoughts = [
                        (n.get("content") or "")[:120]
                        for n in members_by_cluster.get(raw_id, [])[:3]
                    ]
                    state.last_seen_ts = now

            # Decay clusters NOT seen this tick
            for stable_id, state in self._clusters.items():
                if stable_id not in seen_ids:
                    state.activation = round(state.activation * DECAY, 3)

            # Co-activation pairs: any two clusters >threshold this tick
            high = [
                stable_id for stable_id in seen_ids
                if self._clusters[stable_id].activation > CO_THRESHOLD
            ]
            for i, a in enumerate(high):
                for b in high[i + 1:]:
                    key = frozenset({a, b})
                    self._pairs[key] = round(min(1.0, self._pairs.get(key, 0.0) + 0.1), 3)
            # Decay all pairs
            self._pairs = {
                k: round(v * DECAY, 3) for k, v in self._pairs.items() if v * DECAY > 0.05
            }

            self.stats["active_cluster_count"] = sum(
                1 for s in self._clusters.values() if s.activation > 0.1
            )

            # Update consecutive_high_ticks for hysteresis (used by self_steerer)
            for state in self._clusters.values():
                if state.activation > 0.7:
                    state.consecutive_high_ticks += 1
                else:
                    state.consecutive_high_ticks = 0

        self._persist()

        # Phase 8.B — sync to Neo4j decision graph for visualisation
        dg = self._decision_graph
        if dg is not None and dg.is_connected():
            try:
                with self._lock:
                    for state in self._clusters.values():
                        if state.activation < 0.05:
                            continue
                        dg.upsert_cluster(state.to_dict())
                    for key, w in self._pairs.items():
                        if w < 0.1:
                            continue
                        a, b = list(key)
                        dg.upsert_co_activation(a, b, w)
            except Exception as e:
                logger.debug(f"[cluster-engine] decision-graph sync failed: {e}")

        return {
            "ok": True,
            "active_clusters": self.stats["active_cluster_count"],
            "total_clusters": len(self._clusters),
        }

    def _fallback_clusters_from_cte(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Lightweight fallback: bucket recent thoughts by category from
        ContinuousThinkingEngine when ThoughtEvolutionEngine is empty.
        Produces 'clusters' shape matching `get_manifold()` so the rest
        of the engine works unchanged."""
        if self.brain_chat is None:
            return [], []
        cte = getattr(self.brain_chat, "_continuous_thinking", None)
        if cte is None:
            return [], []
        thoughts = list(getattr(cte, "_thoughts", []))[-50:]  # last 50
        if len(thoughts) < 3:
            return [], []
        # Bucket by category — gives us 4-8 natural clusters
        buckets: Dict[str, List[Any]] = {}
        for t in thoughts:
            cat = getattr(t, "category", None) or "thought"
            buckets.setdefault(cat, []).append(t)

        clusters: List[Dict[str, Any]] = []
        nodes: List[Dict[str, Any]] = []
        # Synthetic 2D layout: clusters arranged on a circle
        import math as _math
        n = len(buckets)
        for i, (cat, ts) in enumerate(buckets.items()):
            if len(ts) < 1:
                continue
            angle = 2 * _math.pi * i / max(1, n)
            cx = round(_math.cos(angle) * 8.0, 3)
            cy = round(_math.sin(angle) * 8.0, 3)
            avg_rel = sum(getattr(t, "relevance", 0.5) or 0.5 for t in ts) / len(ts)
            clusters.append({
                "id": i,
                "size": len(ts),
                "center_x": cx,
                "center_y": cy,
                "center_z": 0.0,
                "avg_fitness": round(avg_rel, 3),
                "dominant_topic": cat,
            })
            for t in ts:
                nodes.append({
                    "cluster_id": i,
                    "content": (getattr(t, "content", "") or "")[:120],
                    "category": cat,
                })
        return clusters, nodes

    @staticmethod
    def _stable_id(cluster: Dict[str, Any]) -> str:
        """Stable id across DBSCAN re-labelings — prefer dominant_topic."""
        topic = (cluster.get("dominant_topic") or "").strip().lower()
        if topic:
            return f"topic:{topic}"
        return f"cluster:{cluster.get('id', 0)}"

    # ── Public API ─────────────────────────────────────────────────────

    def get_activations(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(
                [c.to_dict() for c in self._clusters.values()],
                key=lambda c: -c["activation"],
            )

    def get_co_activations(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for key, w in self._pairs.items():
                if w < 0.1:
                    continue
                a, b = list(key)
                out.append({"a": a, "b": b, "weight": round(w, 3)})
            out.sort(key=lambda p: -p["weight"])
            return out

    def bump(self, cluster_id: str, delta: float) -> Dict[str, Any]:
        """Manually nudge a cluster's activation. Used for tests + the
        UI's 'fire cluster X' button."""
        with self._lock:
            state = self._clusters.get(cluster_id)
            if state is None:
                # Try with topic:/cluster: prefix variants
                for prefix in ("topic:", "cluster:"):
                    if self._clusters.get(prefix + cluster_id):
                        state = self._clusters[prefix + cluster_id]
                        cluster_id = prefix + cluster_id
                        break
            if state is None:
                return {"ok": False, "error": f"cluster '{cluster_id}' not found"}
            state.activation = max(0.0, min(1.0, state.activation + float(delta)))
            return {"ok": True, "cluster_id": cluster_id, "activation": state.activation}

    def get_cluster(self, cluster_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            state = self._clusters.get(cluster_id)
            return state.to_dict() if state else None

    def mark_dispatched(self, cluster_id: str) -> None:
        """Self-steerer calls this after firing a capability so cooldown +
        fire_count are tracked."""
        with self._lock:
            state = self._clusters.get(cluster_id)
            if state is None:
                return
            state.last_dispatch_ts = time.time()
            state.fire_count += 1

    def stats_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self.stats,
                "tick_interval_s": TICK_INTERVAL_S,
                "decay": DECAY,
                "ema_alpha": EMA_ALPHA,
                "co_activation_threshold": CO_THRESHOLD,
                "running": bool(self._worker and self._worker.is_alive()),
                "total_clusters": len(self._clusters),
                "co_pair_count": len(self._pairs),
            }

    # ── Persistence ────────────────────────────────────────────────────

    def _persist(self) -> None:
        try:
            JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps({
                "ts": time.time(),
                "clusters": [c.to_dict() for c in self._clusters.values()],
                "pairs": [
                    {"a": list(k)[0], "b": list(k)[1], "w": w}
                    for k, w in self._pairs.items()
                ],
            }, default=str)
            with JSONL_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            # Trim if too long
            if self.stats["ticks"] % 50 == 0:
                self._trim_jsonl()
        except Exception as e:
            logger.debug(f"[cluster-engine] persist failed: {e}")

    @staticmethod
    def _trim_jsonl() -> None:
        try:
            if not JSONL_PATH.exists():
                return
            with JSONL_PATH.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > JSONL_MAX_LINES:
                with JSONL_PATH.open("w", encoding="utf-8") as f:
                    f.writelines(lines[-JSONL_MAX_LINES:])
        except Exception:
            pass
