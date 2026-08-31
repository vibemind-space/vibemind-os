"""
Phase S.5 — Cross-Session Discourse Memory Consolidator.

Periodic consolidator over aggregated-kg (Phase R.4 output: topics +
findings + decisions). Clusters topics with DBSCAN over semantic vectors,
synthesises one meta_topic per cluster via groq_subagent, links source
topics back via linked.meta_topic_id.

Effect: after a few days of discourse, Brain has structured "themes"
that span individual aggregations — "what have we been talking about
all week?" becomes answerable.

Pattern lifted directly from ConsolidationEngine (consolidation_engine.py:75)
with two changes:
  - source collection = aggregated (not episodic)
  - source node_type = topic (not thought)
  - target node_type = meta_topic (not concept)

Tick interval default 6h. Reward-trigger via tick_now_async() called from
brain_chat.py reward-feedback hook is added in S.5.B.
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

# ── Config ─────────────────────────────────────────────────────────────

ENABLED = os.environ.get("DISCOURSE_META_ENABLED", "1") == "1"
TICK_INTERVAL_S = float(os.environ.get("DISCOURSE_META_INTERVAL_S", "21600"))  # 6h
INITIAL_DELAY_S = float(os.environ.get("DISCOURSE_META_INITIAL_DELAY", "900"))  # 15min
LOOKBACK_HOURS = float(os.environ.get("DISCOURSE_META_LOOKBACK_H", "168"))  # 7d
SAMPLE_LIMIT = int(os.environ.get("DISCOURSE_META_SAMPLE_LIMIT", "200"))
MIN_CLUSTER_SIZE = int(os.environ.get("DISCOURSE_META_MIN_CLUSTER_SIZE", "3"))
DBSCAN_EPS = float(os.environ.get("DISCOURSE_META_DBSCAN_EPS", "0.20"))
MAX_NEW_PER_TICK = int(os.environ.get("DISCOURSE_META_MAX_NEW", "5"))


SYNTH_PROMPT = """Below are {n} discourse topics that the Brain's
multi-agent system produced over time. Each topic is a condensed summary
of one 3-hour aggregation window. Many of them appear similar.

Topics:
{topics}

Synthesise these into ONE meta-pattern: a single sentence (≤ 200 chars)
describing what the recurring theme is. Do not list the topics. Do not
output JSON. Output the sentence only.
"""


def _meta_id(topic_ids: List[str]) -> str:
    """Deterministic UUID derived from sorted topic-ids."""
    h = hashlib.sha256("|".join(sorted(topic_ids)).encode("utf-8")).hexdigest()
    return str(uuid.UUID(h[:32]))


def _meta_pid(meta_id: str) -> str:
    """Same id space as Qdrant points (already a UUID)."""
    return meta_id


# ── Class ──────────────────────────────────────────────────────────────


class DiscourseMemoryConsolidator:
    """Background topic → meta_topic consolidator.

    Reads from aggregated-kg, writes meta_topic nodes back into
    aggregated-kg with linked.topics edges. Source topics get
    linked.meta_topic_id populated.
    """

    def __init__(self, kg, dispatcher) -> None:
        self.kg = kg
        self.dispatcher = dispatcher
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "topics_scanned": 0,
            "clusters_found": 0,
            "meta_topics_created": 0,
            "meta_topics_updated": 0,
            "edges_built": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
            "last_run_summary": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[discourse-meta] disabled")
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="DiscourseMemoryConsolidator",
        )
        self._worker.start()
        logger.info(
            f"[discourse-meta] started "
            f"(tick={TICK_INTERVAL_S}s, lookback={LOOKBACK_HOURS}h)"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        self._stop.wait(INITIAL_DELAY_S)
        while not self._stop.is_set():
            try:
                summary = self.run_once()
                self.stats["ticks"] += 1
                self.stats["last_tick_ts"] = time.time()
                self.stats["last_run_summary"] = summary
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                logger.warning(f"[discourse-meta] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    def tick_now_async(self) -> None:
        """Reward-triggered fire-and-forget tick (used by brain_chat hook).
        Runs in its own thread so the caller doesn't block."""
        threading.Thread(
            target=self.run_once, daemon=True,
            name="DiscourseMetaTickAsync",
        ).start()

    # ── Core ─────────────────────────────────────────────────────────

    def run_once(self) -> Dict[str, Any]:
        """One meta-consolidation pass. Returns summary dict."""
        try:
            from core.qdrant_kg import COLLECTIONS
        except Exception as e:
            return {"ok": False, "reason": f"import: {e}"}

        agg_coll = COLLECTIONS.get("aggregated")
        if not agg_coll:
            return {"ok": False, "reason": "no aggregated collection"}

        topics, vectors = self._fetch_recent_topics(agg_coll)
        self.stats["topics_scanned"] += len(topics)
        if len(topics) < MIN_CLUSTER_SIZE:
            return {"topics": len(topics), "clusters": 0, "meta_topics": 0,
                    "skip_reason": "too few topics"}

        clusters = self._dbscan_cluster(vectors)
        valid = {
            lbl: idxs for lbl, idxs in clusters.items()
            if lbl != -1 and len(idxs) >= MIN_CLUSTER_SIZE
        }
        self.stats["clusters_found"] += len(valid)

        if not valid:
            return {"topics": len(topics), "clusters": 0, "meta_topics": 0,
                    "skip_reason": "no valid clusters"}

        items = list(valid.items())
        items.sort(key=lambda x: -len(x[1]))
        items = items[:MAX_NEW_PER_TICK]

        created = updated = 0
        for label, idxs in items:
            members = [topics[i] for i in idxs]
            member_ids = [m["id"] for m in members if m.get("id")]
            if len(member_ids) < MIN_CLUSTER_SIZE:
                continue

            mid = _meta_id(member_ids)
            mpid = _meta_pid(mid)

            # Idempotent check
            already = False
            try:
                rec = self.kg.client.retrieve(
                    collection_name=agg_coll, ids=[mpid], with_payload=True,
                )
                if rec:
                    already = True
            except Exception:
                pass

            if already:
                self._update_meta_links(agg_coll, mpid, member_ids)
                updated += 1
                continue

            meta_text = self._synthesise_meta(members)
            if not meta_text:
                continue

            try:
                import numpy as np
                centroid = np.mean(
                    np.asarray([vectors[i] for i in idxs], dtype=np.float32),
                    axis=0,
                ).tolist()
            except Exception:
                centroid = vectors[idxs[0]]

            self._upsert_meta(agg_coll, mpid, mid, meta_text, centroid, member_ids)
            for tid in member_ids:
                self._add_meta_to_topic(agg_coll, tid, mid)
            created += 1
            self.stats["meta_topics_created"] += 1

        return {
            "topics": len(topics),
            "clusters_total": len(valid),
            "meta_topics_created": created,
            "meta_topics_updated": updated,
        }

    # ── Implementation details ───────────────────────────────────────

    def _fetch_recent_topics(
        self, coll: str,
    ) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
        """Scroll recent topic-nodes with their semantic vectors."""
        from qdrant_client.http import models as qm
        cutoff = int(time.time() - LOOKBACK_HOURS * 3600)
        topics: List[Dict[str, Any]] = []
        vectors: List[List[float]] = []
        try:
            qfilter = qm.Filter(must=[
                qm.FieldCondition(key="node_type",
                                   match=qm.MatchValue(value="topic")),
                qm.FieldCondition(key="created_at",
                                   range=qm.Range(gte=cutoff)),
            ])
            offset = None
            while len(topics) < SAMPLE_LIMIT:
                batch, next_off = self.kg.client.scroll(
                    collection_name=coll,
                    scroll_filter=qfilter,
                    limit=min(50, SAMPLE_LIMIT - len(topics)),
                    with_payload=True,
                    with_vectors=["semantic"],
                    offset=offset,
                )
                if not batch:
                    break
                for r in batch:
                    p = r.payload or {}
                    vec = (r.vector or {}).get("semantic")
                    if not vec:
                        continue
                    topics.append({
                        "id": str(r.id),
                        "title": p.get("title") or p.get("content", "")[:80],
                        "content": p.get("content") or "",
                        "created_at": p.get("created_at"),
                    })
                    vectors.append(vec)
                if not next_off:
                    break
                offset = next_off
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"fetch_topics: {e}"
            logger.debug(f"[discourse-meta] fetch failed: {e}")
        return topics, vectors

    def _dbscan_cluster(
        self, vectors: List[List[float]],
    ) -> Dict[int, List[int]]:
        try:
            import numpy as np
            from sklearn.cluster import DBSCAN
            X = np.asarray(vectors, dtype=np.float32)
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
            return {}

    def _synthesise_meta(
        self, members: List[Dict[str, Any]],
    ) -> Optional[str]:
        if not self.dispatcher:
            longest = max(members, key=lambda m: len(m.get("content") or ""))
            return (longest.get("title") or longest.get("content") or "")[:200]

        examples = members[:8]
        topics_block = "\n".join(
            f"- {(m.get('title') or '').strip()}: {(m.get('content') or '')[:160]}"
            for m in examples
        )
        prompt = SYNTH_PROMPT.format(n=len(members), topics=topics_block)

        try:
            result = self.dispatcher.dispatch(
                "groq_subagent",
                prompt=prompt,
                max_tokens=120,
                temperature=0.3,
                model=os.environ.get(
                    "DISCOURSE_META_MODEL",
                    "groq::llama-3.1-8b-instant",
                ),
            )
            if result.get("ok"):
                text = (result.get("text") or "").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                return text[:300] if text else None
            self.stats["last_error"] = (
                f"synth: {result.get('error', 'unknown')}"
            )
            return None
        except Exception as e:
            self.stats["last_error"] = f"synth: {e}"
            return None

    def _upsert_meta(
        self, coll: str, mpid: str, mid: str, text: str,
        centroid: List[float], member_ids: List[str],
    ) -> None:
        from qdrant_client.http import models as qm
        try:
            payload = {
                "node_type": "meta_topic",
                "meta_topic_id": mid,
                "title": text[:120],
                "content": text[:2000],
                "source": "discourse_memory_consolidator",
                "created_at": int(time.time()),
                "member_count": len(member_ids),
                "linked": {
                    "topics": list(member_ids)[-50:],
                    "findings": [],
                    "decisions": [],
                },
            }
            self.kg.client.upsert(
                collection_name=coll,
                points=[qm.PointStruct(
                    id=mpid,
                    vector={"semantic": centroid},
                    payload=payload,
                )],
                wait=True,
            )
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"upsert_meta: {e}"
            logger.debug(f"[discourse-meta] upsert_meta failed: {e}")

    def _update_meta_links(
        self, coll: str, mpid: str, new_member_ids: List[str],
    ) -> None:
        try:
            rec = self.kg.client.retrieve(
                collection_name=coll, ids=[mpid], with_payload=True,
            )
            if not rec:
                return
            p = rec[0].payload or {}
            linked = p.get("linked") or {}
            existing = list(linked.get("topics") or [])
            merged = existing + [m for m in new_member_ids if m not in existing]
            linked["topics"] = merged[-50:]
            self.kg.client.set_payload(
                collection_name=coll,
                payload={"linked": linked,
                         "member_count": len(merged)},
                points=[mpid],
            )
            mid = p.get("meta_topic_id")
            if mid:
                for tid in new_member_ids:
                    self._add_meta_to_topic(coll, tid, mid)
        except Exception as e:
            logger.debug(f"[discourse-meta] update_meta_links failed: {e}")

    def _add_meta_to_topic(
        self, coll: str, topic_pid: str, meta_id: str,
    ) -> None:
        try:
            rec = self.kg.client.retrieve(
                collection_name=coll, ids=[topic_pid], with_payload=True,
            )
            if not rec:
                return
            p = rec[0].payload or {}
            linked = p.get("linked") or {}
            metas = list(linked.get("meta_topics") or [])
            if meta_id in metas:
                return
            metas.append(meta_id)
            linked["meta_topics"] = metas[-20:]
            self.kg.client.set_payload(
                collection_name=coll,
                payload={"linked": linked, "meta_topic_id": meta_id},
                points=[topic_pid],
            )
            self.stats["edges_built"] += 1
        except Exception as e:
            logger.debug(f"[discourse-meta] add_meta_to_topic failed: {e}")

    # ── Recall (S.5.C) ───────────────────────────────────────────────

    def recall(self, query: str, days: int = 7, limit: int = 10) -> Dict[str, Any]:
        """Search aggregated-kg for meta_topics + topics matching query,
        filtered to last N days. Returns dedupe-sorted list."""
        try:
            from core.qdrant_kg import COLLECTIONS
        except Exception:
            return {"ok": False, "results": []}

        coll = COLLECTIONS.get("aggregated")
        if not coll:
            return {"ok": False, "results": []}

        cutoff = int(time.time() - days * 86400)
        # Reuse Brain's own search API which has dtype-mismatch fallback handling
        # built in. Returns zero hits on errors instead of raising.
        try:
            kg_hits = self.kg.search(
                query=query,
                limit=limit * 2,
                score_threshold=0.2,
                collection="aggregated",
            )
            # Filter to recent + topic|meta_topic only
            hits = []
            for h in kg_hits:
                p = h.get("payload") or {}
                if p.get("created_at", 0) < cutoff:
                    continue
                if p.get("node_type") not in ("topic", "meta_topic"):
                    continue
                # Adapt to original code's expected interface: object with .id, .score, .payload
                class _Hit:
                    pass
                hh = _Hit()
                hh.id = h.get("id")
                hh.score = h.get("score")
                hh.payload = p
                hits.append(hh)
            seen_topic_ids = set()
            results: List[Dict[str, Any]] = []
            # Pass 1: meta_topics (consume their member topic-ids)
            for h in hits:
                p = h.payload or {}
                if p.get("node_type") != "meta_topic":
                    continue
                results.append({
                    "node_type": "meta_topic",
                    "id": str(h.id),
                    "title": p.get("title"),
                    "content": (p.get("content") or "")[:500],
                    "score": h.score,
                    "member_count": p.get("member_count"),
                    "created_at": p.get("created_at"),
                })
                for t in (p.get("linked") or {}).get("topics") or []:
                    seen_topic_ids.add(t)
                if len(results) >= limit:
                    break
            # Pass 2: standalone topics (skip those covered by a meta_topic)
            if len(results) < limit:
                for h in hits:
                    p = h.payload or {}
                    if p.get("node_type") != "topic":
                        continue
                    if str(h.id) in seen_topic_ids:
                        continue
                    results.append({
                        "node_type": "topic",
                        "id": str(h.id),
                        "title": p.get("title"),
                        "content": (p.get("content") or "")[:300],
                        "score": h.score,
                        "created_at": p.get("created_at"),
                    })
                    if len(results) >= limit:
                        break
            return {"ok": True, "query": query, "days": days, "results": results}
        except Exception as e:
            self.stats["last_error"] = f"recall: {e}"
            return {"ok": False, "error": str(e), "results": []}

    # ── Public stats ─────────────────────────────────────────────────

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "enabled": ENABLED,
            "tick_interval_s": TICK_INTERVAL_S,
            "lookback_h": LOOKBACK_HOURS,
            "running": bool(self._worker and self._worker.is_alive()),
            **self.stats,
        }
