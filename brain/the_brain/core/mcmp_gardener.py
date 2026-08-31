"""
MCMP Graph Gardener for Brain's cognitive collections.

A lightweight Monte-Carlo Pheromone walker inspired by slime-mold /
la-fungus-search's MCMPRetriever. Walks over `brain-episodic` and
`brain-semantic` points, reinforcing heavily-traversed edges and
pruning orphan / low-activation points over time.

Design
------
Each tick:
  1. Pick N random seed points from brain-episodic (weighted by recency)
  2. For each seed, run K random walks via payload.linked.* edges
  3. Every visited node gets its `activation_strength` bumped
  4. Every traversed edge (A→B) bumps a small `edge_weight` in A.edge_weights[B]
  5. Periodically: decay all activation_strength × 0.98, prune points with
     activation_strength < eps AND 0 linked AND older than TTL

This is NOT the full la-fungus MCMPRetriever (which does adaptive chemotaxis
with vector fields). It's a cheaper graph-structural variant specialized
for Brain's KG.

Runs as a daemon thread. Tick interval: 60s default.

Environment:
  MCMP_TICK_INTERVAL_S     default 60
  MCMP_SEEDS_PER_TICK      default 5
  MCMP_WALKS_PER_SEED      default 3
  MCMP_WALK_MAX_STEPS      default 4
  MCMP_DECAY_EVERY_N_TICKS default 10
  MCMP_DECAY_FACTOR        default 0.98
  MCMP_PRUNE_AFTER_H       default 24     # prune orphan thoughts after N hours
  MCMP_MIN_ACTIVATION      default 0.1
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


TICK_INTERVAL_S = float(os.environ.get("MCMP_TICK_INTERVAL_S", "60"))
SEEDS_PER_TICK = int(os.environ.get("MCMP_SEEDS_PER_TICK", "5"))
WALKS_PER_SEED = int(os.environ.get("MCMP_WALKS_PER_SEED", "3"))
WALK_MAX_STEPS = int(os.environ.get("MCMP_WALK_MAX_STEPS", "4"))
DECAY_EVERY_N = int(os.environ.get("MCMP_DECAY_EVERY_N_TICKS", "10"))
DECAY_FACTOR = float(os.environ.get("MCMP_DECAY_FACTOR", "0.98"))
PRUNE_AFTER_H = float(os.environ.get("MCMP_PRUNE_AFTER_H", "24"))
MIN_ACTIVATION = float(os.environ.get("MCMP_MIN_ACTIVATION", "0.1"))

# Collections the gardener WALKS (can follow edges into any of these).
GARDEN_COLLECTIONS = ("brain-episodic", "brain-semantic", "brain-procedural", "rowboat-artifacts")

# Collections the gardener may MODIFY (bump activation, prune orphans).
# Read-only collections (artifacts) are visited for walks but never pruned.
MUTABLE_COLLECTIONS = {"brain-episodic", "brain-semantic", "brain-procedural"}


class MCMPGardener:
    """Pheromone walker + pruner over Brain cognitive collections."""

    def __init__(self, kg) -> None:
        """kg: the QdrantKG instance (must already have ensure_collections ran)."""
        self.kg = kg
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._tick_count = 0
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "walks_done": 0,
            "steps_taken": 0,
            "nodes_visited": 0,
            "activation_bumps": 0,
            "decays_applied": 0,
            "pruned": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="MCMPGardener",
        )
        self._worker.start()
        logger.info(
            f"[MCMP] gardener started "
            f"(tick={TICK_INTERVAL_S}s, seeds={SEEDS_PER_TICK}, "
            f"walks={WALKS_PER_SEED}, steps<={WALK_MAX_STEPS})"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        # Wait a bit so Brain startup completes before we hammer Qdrant
        self._stop.wait(10.0)
        while not self._stop.is_set():
            try:
                self._tick()
                self._tick_count += 1
                self.stats["ticks"] = self._tick_count
                self.stats["last_tick_ts"] = time.time()
                if self._tick_count % DECAY_EVERY_N == 0:
                    self._decay_and_prune()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                logger.debug(f"[MCMP] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Core MCMP ops ────────────────────────────────────────────────

    def _tick(self) -> None:
        """Run SEEDS_PER_TICK random-walk exploration passes."""
        seeds = self._sample_seeds(SEEDS_PER_TICK)
        if not seeds:
            return
        for seed in seeds:
            for _ in range(WALKS_PER_SEED):
                self._walk_from(seed)
                self.stats["walks_done"] += 1

    def _sample_seeds(self, n: int) -> List[Tuple[str, str, Dict[str, Any]]]:
        """Pick n random points from any GARDEN_COLLECTION.
        Returns list of (collection, point_id, payload).

        Distribution: episodic 50%, semantic 20%, procedural 20%,
        artifacts 10%. Falls through to next if a coll is empty.
        """
        seeds: List[Tuple[str, str, Dict[str, Any]]] = []
        # Weighted order — episodic first (most thoughts), then variety
        colls_to_try = list(GARDEN_COLLECTIONS)
        random.shuffle(colls_to_try)
        if random.random() < 0.5:
            colls_to_try = ["brain-episodic"] + [c for c in colls_to_try if c != "brain-episodic"]
        elif random.random() < 0.5:
            colls_to_try = ["brain-procedural"] + [c for c in colls_to_try if c != "brain-procedural"]

        for coll in colls_to_try:
            try:
                scrolled, _ = self.kg.client.scroll(
                    collection_name=coll,
                    limit=max(n * 3, 20),
                    with_payload=True,
                    with_vectors=False,
                )
                if not scrolled:
                    continue  # empty collection — try the other
                random.shuffle(scrolled)
                for rec in scrolled[:n]:
                    seeds.append((coll, str(rec.id), rec.payload or {}))
                return seeds
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"sample_seeds from '{coll}': {type(e).__name__}: {e}"
                logger.warning(f"[MCMP] sample_seeds from '{coll}' failed: {e}")
                continue
        if not seeds:
            self.stats["last_error"] = "sample_seeds: all GARDEN_COLLECTIONS empty"
        return seeds

    def _walk_from(self, seed: Tuple[str, str, Dict[str, Any]]) -> None:
        """Random walk from a seed along payload.linked.* edges."""
        coll, pid, payload = seed
        visited: Set[str] = {pid}
        self._bump_activation(coll, pid, 1.0)
        self.stats["nodes_visited"] += 1

        current_payload = payload
        current_coll = coll
        for step in range(WALK_MAX_STEPS):
            # Gather candidate neighbors from linked.*
            linked = current_payload.get("linked") or {}
            candidates: List[str] = []
            for neighbors in linked.values():
                if isinstance(neighbors, list):
                    candidates.extend(n for n in neighbors if isinstance(n, str))
            if not candidates:
                break
            # Pick one we haven't visited
            unseen = [c for c in candidates if c not in visited]
            if not unseen:
                break
            next_ref = random.choice(unseen)
            # The ref can be an external_id or a UUID. We need to find its
            # collection. Search the 4 brain + artifacts collections by id.
            hit = self._locate(next_ref)
            if hit is None:
                break
            next_coll, next_pid, next_payload = hit
            self._bump_activation(next_coll, next_pid, 0.5)
            self.stats["nodes_visited"] += 1
            self.stats["steps_taken"] += 1
            visited.add(next_pid)
            current_payload = next_payload
            current_coll = next_coll

    def _locate(self, ref: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """Find a point by external id OR UUID in any cognitive collection.

        Handles two forms:
          - UUID directly → qdrant retrieve
          - external id (thought_id, bubble_id, idea_id, ...) → deterministic
            UUID via same hash as qdrant_kg._point_id, then retrieve
        """
        from core.qdrant_kg import COLLECTIONS, _point_id
        # Compute the deterministic UUID for the external id form
        try:
            uuid_guess = _point_id(ref)
        except Exception:
            uuid_guess = None

        candidates = [ref]
        if uuid_guess and uuid_guess != ref:
            candidates.append(uuid_guess)

        for logical, coll_name in COLLECTIONS.items():
            for cand in candidates:
                try:
                    rec = self.kg.client.retrieve(
                        collection_name=coll_name, ids=[cand], with_payload=True,
                    )
                    if rec:
                        return coll_name, str(rec[0].id), rec[0].payload or {}
                except Exception:
                    continue
        return None

    def _bump_activation(self, coll: str, pid: str, delta: float) -> None:
        """Increment `activation_strength` on a point. Skip if collection
        is read-only (e.g. rowboat-artifacts)."""
        if coll not in MUTABLE_COLLECTIONS:
            return
        try:
            # Fetch current to compute new value
            rec = self.kg.client.retrieve(
                collection_name=coll, ids=[pid], with_payload=True,
            )
            if not rec:
                return
            current = float(rec[0].payload.get("activation_strength", 0.0) or 0.0)
            new_val = current + delta
            self.kg.client.set_payload(
                collection_name=coll,
                payload={"activation_strength": new_val},
                points=[pid],
            )
            self.stats["activation_bumps"] += 1
        except Exception as e:
            logger.debug(f"[MCMP] bump failed on {coll}/{pid}: {e}")

    def _decay_and_prune(self) -> None:
        """Apply global decay and prune orphan points older than TTL.
        Only operates on MUTABLE_COLLECTIONS (not rowboat-artifacts)."""
        cutoff_ts = time.time() - PRUNE_AFTER_H * 3600
        for coll in MUTABLE_COLLECTIONS:
            try:
                # Scroll through collection, process in batches
                offset = None
                to_prune: List[str] = []
                to_decay: List[Tuple[str, float]] = []
                while True:
                    batch, next_offset = self.kg.client.scroll(
                        collection_name=coll,
                        limit=200,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    if not batch:
                        break
                    for rec in batch:
                        p = rec.payload or {}
                        act = float(p.get("activation_strength", 0.0) or 0.0)
                        created = float(p.get("created_at", time.time()))
                        linked = p.get("linked") or {}
                        total_links = sum(
                            len(v) for v in linked.values() if isinstance(v, list)
                        )
                        # Prune: very low activation AND no edges AND old
                        if (act < MIN_ACTIVATION
                                and total_links == 0
                                and created < cutoff_ts):
                            to_prune.append(str(rec.id))
                        else:
                            # Decay
                            new_act = act * DECAY_FACTOR
                            to_decay.append((str(rec.id), new_act))
                    if next_offset is None:
                        break
                    offset = next_offset
                # Apply decays (batch set_payload)
                for pid, new_val in to_decay:
                    try:
                        self.kg.client.set_payload(
                            collection_name=coll,
                            payload={"activation_strength": new_val},
                            points=[pid],
                        )
                    except Exception:
                        pass
                self.stats["decays_applied"] += len(to_decay)
                # Prune
                if to_prune:
                    try:
                        self.kg.client.delete(
                            collection_name=coll,
                            points_selector=to_prune,
                        )
                        self.stats["pruned"] += len(to_prune)
                        logger.info(f"[MCMP] pruned {len(to_prune)} orphans from {coll}")
                    except Exception as e:
                        logger.debug(f"[MCMP] prune failed: {e}")
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"decay/prune {coll}: {e}"
                logger.debug(f"[MCMP] decay/prune {coll} failed: {e}")
