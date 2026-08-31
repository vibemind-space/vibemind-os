"""
Phase L — Consolidation episodic → semantic.

Periodic background job that:
  1. Pulls episodic thoughts (with their semantic vectors) from Qdrant
  2. Clusters them via DBSCAN on cosine distance
  3. For each cluster of size >= MIN_CLUSTER_SIZE: asks the SubagentDispatcher
     (groq_subagent) to summarise it into a concept
  4. Upserts the concept as node_type=concept into brain-semantic
  5. Cross-links concept.linked.thoughts <-> thought.linked.concepts

Why DBSCAN: density-based, no need to pick K, handles arbitrary cluster
shapes, native cosine support.

Run interval: default 5 minutes. Idempotent (concept ids derived from
sorted member-ids hash, so re-running same cluster updates the same
concept point).

Environment:
  CONSOLIDATION_TICK_INTERVAL_S      default 300 (5 min)
  CONSOLIDATION_MIN_CLUSTER_SIZE     default 3
  CONSOLIDATION_MAX_NEW_PER_TICK     default 5  (cap LLM cost)
  CONSOLIDATION_DBSCAN_EPS           default 0.18 (cosine distance — ~0.82 sim)
  CONSOLIDATION_SAMPLE_LIMIT         default 1000  (max thoughts per scan)
  CONSOLIDATION_LOOKBACK_HOURS       default 24
  CONSOLIDATION_ENABLED              default 1
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


TICK_INTERVAL_S = float(os.environ.get("CONSOLIDATION_TICK_INTERVAL_S", "300"))
MIN_CLUSTER_SIZE = int(os.environ.get("CONSOLIDATION_MIN_CLUSTER_SIZE", "3"))
MAX_NEW_PER_TICK = int(os.environ.get("CONSOLIDATION_MAX_NEW_PER_TICK", "5"))
DBSCAN_EPS = float(os.environ.get("CONSOLIDATION_DBSCAN_EPS", "0.18"))
SAMPLE_LIMIT = int(os.environ.get("CONSOLIDATION_SAMPLE_LIMIT", "1000"))
LOOKBACK_HOURS = float(os.environ.get("CONSOLIDATION_LOOKBACK_HOURS", "24"))
ENABLED = os.environ.get("CONSOLIDATION_ENABLED", "1").lower() in ("1", "true", "yes")

# Concept synthesis prompt template
SYNTH_PROMPT = """Below are {n} thoughts that the brain has produced and that
cluster together semantically. Distill ONE concise concept (1-2 sentences,
present tense, German if inputs are German else English) that captures what
they have in common. Output ONLY the concept text, no preamble.

THOUGHTS:
{thoughts}

CONCEPT:"""


def _concept_id(member_ids: List[str]) -> str:
    """Deterministic concept ID from sorted member thought ids."""
    key = "|".join(sorted(member_ids))
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"concept-{h[:16]}"


def _concept_pid(concept_id: str) -> str:
    """Convert external concept_id to deterministic UUID for Qdrant."""
    h = hashlib.sha256(concept_id.encode("utf-8")).hexdigest()
    return str(uuid.UUID(h[:32]))


class ConsolidationEngine:
    """Background episodic → semantic consolidator."""

    def __init__(self, kg, dispatcher) -> None:
        """
        Args:
            kg: QdrantKG instance (must already have ensure_collections ran)
            dispatcher: SubagentDispatcher (for concept synthesis via LLM)
        """
        self.kg = kg
        self.dispatcher = dispatcher
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._tick_count = 0
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "thoughts_scanned": 0,
            "clusters_found": 0,
            "concepts_created": 0,
            "concepts_updated": 0,
            "edges_built": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
            "last_run_summary": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[Consolidation] disabled via CONSOLIDATION_ENABLED=0")
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="ConsolidationEngine",
        )
        self._worker.start()
        logger.info(
            f"[Consolidation] started "
            f"(tick={TICK_INTERVAL_S}s, min_cluster={MIN_CLUSTER_SIZE}, "
            f"eps={DBSCAN_EPS}, max_new/tick={MAX_NEW_PER_TICK})"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        # Wait long enough for Brain to settle + first thoughts to arrive
        self._stop.wait(60.0)
        while not self._stop.is_set():
            try:
                summary = self.run_once()
                self._tick_count += 1
                self.stats["ticks"] = self._tick_count
                self.stats["last_tick_ts"] = time.time()
                self.stats["last_run_summary"] = summary
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                logger.warning(f"[Consolidation] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Core ─────────────────────────────────────────────────────────

    def run_once(self) -> Dict[str, Any]:
        """One consolidation pass. Returns summary dict."""
        from core.qdrant_kg import COLLECTIONS, NT_THOUGHT, NT_CONCEPT

        episodic = COLLECTIONS["episodic"]
        semantic = COLLECTIONS["semantic"]

        thoughts, vectors = self._fetch_recent_thoughts(episodic)
        self.stats["thoughts_scanned"] += len(thoughts)
        if len(thoughts) < MIN_CLUSTER_SIZE:
            return {"thoughts": len(thoughts), "clusters": 0, "concepts": 0,
                    "skip_reason": "too few thoughts"}

        clusters = self._dbscan_cluster(vectors)
        # clusters: dict[label -> [indices]], label=-1 means noise
        valid_clusters = {
            lbl: idxs for lbl, idxs in clusters.items()
            if lbl != -1 and len(idxs) >= MIN_CLUSTER_SIZE
        }
        self.stats["clusters_found"] += len(valid_clusters)

        if not valid_clusters:
            return {"thoughts": len(thoughts), "clusters": 0, "concepts": 0,
                    "skip_reason": "no valid clusters"}

        # Cap new-LLM-calls per tick (cost control)
        cluster_items = list(valid_clusters.items())
        cluster_items.sort(key=lambda x: -len(x[1]))  # densest first
        cluster_items = cluster_items[:MAX_NEW_PER_TICK]

        created = updated = 0
        for label, idxs in cluster_items:
            members = [thoughts[i] for i in idxs]
            member_ids = [m["thought_id"] for m in members if m.get("thought_id")]
            if len(member_ids) < MIN_CLUSTER_SIZE:
                continue

            cid = _concept_id(member_ids)
            cpid = _concept_pid(cid)

            # Check if concept already exists (idempotent)
            already_exists = False
            try:
                rec = self.kg.client.retrieve(
                    collection_name=semantic, ids=[cpid], with_payload=True,
                )
                if rec:
                    already_exists = True
            except Exception:
                pass

            if already_exists:
                # Just refresh links, no need to re-synthesise
                self._update_concept_links(semantic, cpid, member_ids, episodic)
                updated += 1
                continue

            # Synthesise concept via LLM
            concept_text = self._synthesise_concept(members)
            if not concept_text:
                continue

            # Compute average vector for the concept (centroid)
            try:
                import numpy as np
                centroid = np.mean(
                    np.asarray([vectors[i] for i in idxs], dtype=np.float32),
                    axis=0,
                ).tolist()
            except Exception:
                centroid = vectors[idxs[0]]  # fallback

            # Upsert concept point directly (bypass _upsert_point which embeds)
            self._upsert_concept(
                semantic, cpid, cid, concept_text, centroid, member_ids,
            )
            # Cross-link: each thought.linked.concepts += [cid]
            for tid in member_ids:
                self._add_concept_to_thought(episodic, tid, cid)
            created += 1
            self.stats["concepts_created"] += 1

        return {
            "thoughts": len(thoughts),
            "clusters_total": len(valid_clusters),
            "concepts_created": created,
            "concepts_updated": updated,
        }

    # ── Implementation details ───────────────────────────────────────

    def _fetch_recent_thoughts(
        self, coll: str,
    ) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
        """Scroll recent thoughts with their semantic vectors."""
        cutoff = int(time.time() - LOOKBACK_HOURS * 3600)
        thoughts: List[Dict[str, Any]] = []
        vectors: List[List[float]] = []
        try:
            offset = None
            while len(thoughts) < SAMPLE_LIMIT:
                batch, next_off = self.kg.client.scroll(
                    collection_name=coll,
                    limit=200,
                    offset=offset,
                    with_payload=True,
                    with_vectors=["semantic"],
                )
                if not batch:
                    break
                for rec in batch:
                    p = rec.payload or {}
                    if p.get("node_type") != "thought":
                        continue
                    if int(p.get("created_at", 0)) < cutoff:
                        continue
                    if not rec.vector or "semantic" not in rec.vector:
                        continue
                    thoughts.append({
                        "pid": str(rec.id),
                        "thought_id": p.get("thought_id"),
                        "content": p.get("content", ""),
                        "created_at": p.get("created_at"),
                    })
                    vectors.append(rec.vector["semantic"])
                if next_off is None:
                    break
                offset = next_off
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"fetch_recent_thoughts: {e}"
            logger.debug(f"[Consolidation] fetch failed: {e}")
        return thoughts, vectors

    def _dbscan_cluster(
        self, vectors: List[List[float]],
    ) -> Dict[int, List[int]]:
        """Run DBSCAN on cosine distance. Returns label -> [indices]."""
        try:
            import numpy as np
            from sklearn.cluster import DBSCAN
            X = np.asarray(vectors, dtype=np.float32)
            # Vectors are already L2-normalised by Qwen, so cosine distance
            # = 1 - dot product. DBSCAN with metric='cosine' handles this.
            db = DBSCAN(eps=DBSCAN_EPS, min_samples=MIN_CLUSTER_SIZE,
                        metric="cosine", n_jobs=-1)
            labels = db.fit_predict(X)
            clusters: Dict[int, List[int]] = {}
            for i, lbl in enumerate(labels):
                clusters.setdefault(int(lbl), []).append(i)
            return clusters
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"dbscan: {e}"
            logger.warning(f"[Consolidation] DBSCAN failed: {e}")
            return {}

    def _synthesise_concept(
        self, members: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Ask groq_subagent to summarise cluster into one concept."""
        if not self.dispatcher:
            # Fallback: use the longest thought as the concept "summary"
            longest = max(members, key=lambda m: len(m.get("content") or ""))
            return (longest.get("content") or "")[:300]

        # Build prompt — limit to 8 examples to stay cheap
        examples = members[:8]
        thoughts_block = "\n".join(
            f"- {(m.get('content') or '')[:200]}" for m in examples
        )
        prompt = SYNTH_PROMPT.format(n=len(members), thoughts=thoughts_block)

        try:
            result = self.dispatcher.dispatch(
                "groq_subagent",
                prompt=prompt,
                max_tokens=200,
                temperature=0.3,
            )
            if result.get("ok"):
                text = (result.get("text") or "").strip()
                # Strip code fences if any
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                return text[:500] if text else None
            else:
                self.stats["last_error"] = (
                    f"synth: {result.get('error', 'unknown')}"
                )
                return None
        except Exception as e:
            self.stats["last_error"] = f"synth: {e}"
            return None

    def _upsert_concept(
        self, coll: str, cpid: str, cid: str, text: str,
        centroid: List[float], member_ids: List[str],
    ) -> None:
        """Write the concept point with pre-computed centroid vector."""
        from qdrant_client.http import models as qm
        try:
            payload = {
                "node_type": "concept",
                "concept_id": cid,
                "content": text[:2000],
                "title": text[:80],
                "source": "consolidation",
                "created_at": int(time.time()),
                "member_count": len(member_ids),
                "linked": {
                    "thoughts": list(member_ids)[-50:],
                    "responses": [],
                    "bubbles": [],
                    "ideas": [],
                    "spaces": [],
                    "events": [],
                    "concepts": [],
                },
            }
            self.kg.client.upsert(
                collection_name=coll,
                points=[qm.PointStruct(
                    id=cpid,
                    vector={"semantic": centroid},
                    payload=payload,
                )],
                wait=True,
            )
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"upsert_concept: {e}"
            logger.debug(f"[Consolidation] upsert_concept failed: {e}")

    def _update_concept_links(
        self, semantic: str, cpid: str,
        new_member_ids: List[str], episodic: str,
    ) -> None:
        """Refresh existing concept's linked.thoughts (idempotent)."""
        try:
            rec = self.kg.client.retrieve(
                collection_name=semantic, ids=[cpid], with_payload=True,
            )
            if not rec:
                return
            p = rec[0].payload or {}
            linked = p.get("linked") or {}
            existing = list(linked.get("thoughts") or [])
            merged = existing + [m for m in new_member_ids if m not in existing]
            linked["thoughts"] = merged[-50:]
            self.kg.client.set_payload(
                collection_name=semantic,
                payload={"linked": linked,
                         "member_count": len(merged)},
                points=[cpid],
            )
            # Also push back-edges
            cid = p.get("concept_id")
            if cid:
                for tid in new_member_ids:
                    self._add_concept_to_thought(episodic, tid, cid)
        except Exception as e:
            logger.debug(f"[Consolidation] update_concept_links failed: {e}")

    def _add_concept_to_thought(
        self, episodic: str, thought_id: str, concept_id: str,
    ) -> None:
        """Append concept_id to thought.linked.concepts (idempotent)."""
        try:
            from core.qdrant_kg import _point_id
            tpid = _point_id(thought_id)
            rec = self.kg.client.retrieve(
                collection_name=episodic, ids=[tpid], with_payload=True,
            )
            if not rec:
                return
            p = rec[0].payload or {}
            linked = p.get("linked") or {}
            concepts = list(linked.get("concepts") or [])
            if concept_id in concepts:
                return
            concepts.append(concept_id)
            linked["concepts"] = concepts[-50:]
            self.kg.client.set_payload(
                collection_name=episodic,
                payload={"linked": linked},
                points=[tpid],
            )
            self.stats["edges_built"] += 1
        except Exception as e:
            logger.debug(f"[Consolidation] add_concept_to_thought failed: {e}")