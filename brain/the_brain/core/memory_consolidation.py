"""
MemoryConsolidator — Sleep-Inspired Memory Consolidation System

Runs a 7-phase consolidation cycle every 30s in a background thread,
mimicking biological sleep consolidation:

    Phase 1: DECAY       — Ebbinghaus forgetting on MoltbookStore entries
    Phase 2: STRENGTHEN  — Boost recently accessed/rated entries
    Phase 3: COMPRESS    — LLM summarizes thought clusters into wisdom entries
    Phase 4: CONNECT     — Embedding-based edge strengthening in MoltbookGraph
    Phase 5: RECORD      — Feed queued brain events into KotlinGraph via DualGraph
    Phase 6: MINE        — KuroGraph pattern extraction from KotlinGraph
    Phase 7: PERSIST     — Save everything to disk

Integration points:
    - MoltbookStore: Knowledge storage (Phase 1-4, 7)
    - KnowledgeDecay: Ebbinghaus forgetting (Phase 1)
    - DualGraph: Episodic (KotlinGraph) + semantic (KuroGraph) memory (Phase 5-7)
    - ThoughtEvolutionEngine: Evolved thought population (Phase 7)
    - MicroAgentPool: LLM summarization for compression (Phase 3)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger('brain.consolidation')


# ── Tombstone System ──────────────────────────────────────────────

@dataclass
class Tombstone:
    """Record of a forgotten knowledge entry."""
    entry_id: str
    tags: List[str]
    content_preview: str       # First 80 chars
    confidence: float
    reason: str                # 'activation_decay' | 'curation_prune' | 'lru_eviction'
    died_at: float
    age_hours: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            'entry_id': self.entry_id,
            'tags': self.tags,
            'content_preview': self.content_preview,
            'confidence': round(self.confidence, 4),
            'reason': self.reason,
            'died_at': self.died_at,
            'age_hours': round(self.age_hours, 2),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Tombstone':
        return cls(**d)


class TombstoneLog:
    """Lightweight log of deleted knowledge entries.

    Keeps a bounded deque of Tombstone records for tracking what the
    brain has forgotten. Enables concept death detection and
    'forgotten knowledge' awareness.
    """

    def __init__(self, max_tombstones: int = 1000,
                 persist_path: Optional[str] = None):
        self._tombstones: deque = deque(maxlen=max_tombstones)
        self._persist_path = persist_path
        self._total_forgotten: int = 0

    def record(self, entries: list, reason: str) -> None:
        """Create tombstones for a batch of dead entries."""
        now = time.time()
        for entry in entries:
            created = getattr(entry, 'created_at', now)
            tomb = Tombstone(
                entry_id=getattr(entry, 'id', 'unknown'),
                tags=list(getattr(entry, 'tags', [])),
                content_preview=str(getattr(entry, 'content', ''))[:80],
                confidence=float(getattr(entry, 'confidence', 0.0)),
                reason=reason,
                died_at=now,
                age_hours=round((now - created) / 3600, 2),
            )
            self._tombstones.append(tomb)
            self._total_forgotten += 1

    def recent(self, n: int = 20) -> List[Tombstone]:
        """Return the N most recent tombstones (newest first)."""
        items = list(self._tombstones)
        items.reverse()
        return items[:n]

    def forgotten_concepts(self) -> set:
        """Return all tags from all tombstones."""
        concepts: set = set()
        for t in self._tombstones:
            concepts.update(t.tags)
        return concepts

    def get_stats(self) -> Dict[str, Any]:
        """Summary statistics."""
        return {
            'total_forgotten': self._total_forgotten,
            'tombstone_count': len(self._tombstones),
        }

    def save(self) -> None:
        """Persist tombstones to JSONL file."""
        if not self._persist_path:
            return
        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
        with open(self._persist_path, 'w') as f:
            # First line: metadata
            json.dump({'total_forgotten': self._total_forgotten}, f)
            f.write('\n')
            for tomb in self._tombstones:
                json.dump(tomb.to_dict(), f)
                f.write('\n')

    def load(self) -> None:
        """Load tombstones from JSONL file."""
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, 'r') as f:
                lines = f.readlines()
            if not lines:
                return
            # First line is metadata
            meta = json.loads(lines[0])
            self._total_forgotten = meta.get('total_forgotten', 0)
            for line in lines[1:]:
                line = line.strip()
                if line:
                    self._tombstones.append(Tombstone.from_dict(json.loads(line)))
        except Exception as e:
            logger.warning("Failed to load tombstones: %s", e)


class MemoryConsolidator:
    """Sleep-inspired memory consolidation system.

    Runs a 7-phase cycle every interval_s seconds in a background thread.
    Each dependency is optional except moltbook_store — phases degrade
    gracefully when components are missing.
    """

    def __init__(
        self,
        moltbook_store,
        dual_graph=None,
        evolution_engine=None,
        micro_agent_pool=None,
        meta_knowledge_graph=None,
        klotski_ctm=None,
        knowledge_synthesizer=None,
        continuous_thinking_engine=None,
        interval_s: float = 30.0,
    ):
        """
        Args:
            moltbook_store: MoltbookStore instance (required).
            dual_graph: DualGraph instance (optional — enables Phase 5+6).
            evolution_engine: ThoughtEvolutionEngine instance (optional — enables evo persistence).
            micro_agent_pool: MicroAgentPool instance (optional — enables Phase 3 compression).
            meta_knowledge_graph: MetaKnowledgeGraph instance (optional — enables Phase 8-10).
            klotski_ctm: KlotskiCTM instance (optional — enables CTM reasoning in Phase 10).
            knowledge_synthesizer: KnowledgeSynthesizer instance (optional — enables Phase 9 synthesis).
            continuous_thinking_engine: CTE instance (optional — thought source for Phase 8).
            interval_s: Seconds between consolidation cycles (default 30).
        """
        self._moltbook = moltbook_store
        self._dual_graph = dual_graph
        self._evolution = evolution_engine
        self._pool = micro_agent_pool
        self._meta_graph = meta_knowledge_graph
        self._klotski_ctm = klotski_ctm
        self._knowledge_synth = knowledge_synthesizer
        self._cte = continuous_thinking_engine
        self._interval = interval_s

        # Reuse existing KnowledgeDecay for Phase 1
        try:
            from core.moltbook_retrieval import KnowledgeDecay
            self._decay = KnowledgeDecay(moltbook=moltbook_store)
        except Exception:
            self._decay = None

        # Event buffer: brain events queued for recording to DualGraph
        self._event_buffer: List[Dict[str, Any]] = []
        self._buffer_lock = threading.Lock()

        # Optional SocializationMetrics (Phase 3.5: MEASURE)
        self._socialization = None

        # Background thread
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Stats
        self._cycle_count = 0
        self._total_events_recorded = 0
        self._total_compressed = 0
        self._total_connections_made = 0
        self._total_decayed = 0
        self._total_strengthened = 0
        self._last_cycle_time = 0.0
        self._last_cycle_duration = 0.0

        # Paths
        self._evo_path = 'data/moltbook/evolution_state.json'

        # Tombstone log for tracking forgotten entries
        self._tombstone_log = TombstoneLog(
            max_tombstones=1000,
            persist_path='data/moltbook/tombstones.jsonl',
        )

        logger.info(
            "MemoryConsolidator initialized (interval=%.1fs, dual_graph=%s, "
            "evolution=%s, pool=%s)",
            interval_s,
            'YES' if dual_graph else 'NO',
            'YES' if evolution_engine else 'NO',
            'YES' if micro_agent_pool else 'NO',
        )

    # ── Event Queue (thread-safe) ────────────────────────────────

    def queue_brain_event(self, event: Dict[str, Any]) -> None:
        """Queue a brain event for recording to KotlinGraph.

        Called from CTE thread, chat thread, etc. — must be thread-safe.

        event keys: state, action, next_state, reward, done, metadata
        """
        with self._buffer_lock:
            self._event_buffer.append(event)

    def get_buffer_size(self) -> int:
        """Return current event buffer size."""
        with self._buffer_lock:
            return len(self._event_buffer)

    def set_socialization_metrics(self, metrics) -> None:
        """Attach SocializationMetrics for Phase 3.5 (MEASURE)."""
        self._socialization = metrics

    # ── Phase 1: DECAY ───────────────────────────────────────────

    def _phase_decay(self) -> Dict[str, int]:
        """Apply Ebbinghaus forgetting curve + evict dead entries.

        1. apply_decay() — compute activation for all entries
        2. Identify dead entries (activation < 0.01)
        3. Record tombstones for dead entries
        4. consolidate() — remove dead entries from store
        """
        if not self._decay:
            return {'decayed': 0, 'below_threshold': 0, 'evicted': 0}

        try:
            result = self._decay.apply_decay()
            self._total_decayed += result.get('decayed', 0)

            # Collect dead entries BEFORE deletion (for tombstones)
            dead_entries = [
                e for e in list(self._moltbook._entries.values())
                if e.compute_activation() < 0.01
            ]

            # Record tombstones
            if dead_entries:
                self._tombstone_log.record(dead_entries, 'activation_decay')

            # Actually evict dead entries
            eviction = self._moltbook.consolidate(activation_threshold=0.01)
            result['evicted'] = eviction.get('removed', 0)

            if result['evicted'] > 0:
                logger.info(
                    "Phase DECAY evicted %d entries (%d tombstones total)",
                    result['evicted'], self._tombstone_log._total_forgotten,
                )

            return result
        except Exception as e:
            logger.warning("Phase DECAY failed: %s", e)
            return {'decayed': 0, 'below_threshold': 0, 'evicted': 0}

    # ── Phase 2: STRENGTHEN ──────────────────────────────────────

    def _phase_strengthen(self, window_s: float = 60.0) -> int:
        """Boost entries accessed in the last window_s seconds.

        Recently accessed entries get an extra access() call to
        reinforce their activation — like spaced repetition.
        """
        if not self._moltbook:
            return 0

        now = time.time()
        boosted = 0

        try:
            for entry in list(self._moltbook._entries.values()):
                age = now - entry.last_accessed
                if age < window_s and entry.accessed_count > 0:
                    entry.access()
                    boosted += 1
        except Exception as e:
            logger.warning("Phase STRENGTHEN failed: %s", e)

        self._total_strengthened += boosted
        return boosted

    # ── Phase 3: COMPRESS ────────────────────────────────────────

    def _phase_compress(self) -> int:
        """Find similar thought-clusters, LLM-summarize into wisdom entries.

        Only runs if MicroAgentPool is available. Processes max 1 cluster
        per cycle to keep latency low (~1-2s for LLM call).
        """
        if not self._pool or not self._moltbook:
            return 0

        try:
            # Get recent entries (last 5 min) from thought-like sources
            now = time.time()
            thought_sources = {'thought', 'evolve', 'chat', 'unknown'}
            recent = [
                e for e in self._moltbook._entries.values()
                if now - e.last_accessed < 300
                and e.source_agent in thought_sources
            ]

            if len(recent) < 3:
                return 0

            # Find clusters via embedding similarity (cosine > 0.7)
            clusters = self._find_similar_clusters(recent, threshold=0.7, min_size=3)
            if not clusters:
                return 0

            # Take the largest cluster, summarize (max 1 per cycle)
            cluster = max(clusters, key=len)
            texts = [e.content[:200] for e in cluster[:5]]

            prompt = (
                f"Synthesize these {len(texts)} related thoughts into ONE concise wisdom entry "
                f"(2-3 sentences). Extract the core insight:\n\n"
                + "\n".join(f"- {t}" for t in texts)
                + "\n\nOutput ONLY the synthesized wisdom."
            )

            result = self._pool._call_agent('enricher', prompt)
            if result and len(result.strip()) > 10:
                self._moltbook.add_entry(
                    content=result.strip()[:300],
                    source_agent='consolidation',
                    entry_type='knowledge',
                    tags=['wisdom', 'compressed', 'consolidated'],
                    confidence=0.75,
                )
                self._total_compressed += 1
                return 1

        except Exception as e:
            logger.warning("Phase COMPRESS failed: %s", e)

        return 0

    def _find_similar_clusters(
        self, entries: list, threshold: float = 0.7, min_size: int = 3
    ) -> List[List]:
        """Find clusters of semantically similar entries.

        Uses pairwise cosine similarity on embeddings. Returns list of
        clusters, each cluster being a list of MoltbookEntry.
        """
        # Build list of entries with valid embeddings
        with_emb = [
            (e, e.semantic_embedding) for e in entries
            if e.semantic_embedding is not None
        ]

        if len(with_emb) < min_size:
            return []

        # Simple greedy clustering: pick seed, grab all similar, repeat
        used = set()
        clusters = []

        for i, (entry_i, emb_i) in enumerate(with_emb):
            if i in used:
                continue

            cluster = [entry_i]
            used.add(i)

            norm_i = np.linalg.norm(emb_i)
            if norm_i < 1e-8:
                continue

            for j, (entry_j, emb_j) in enumerate(with_emb):
                if j in used:
                    continue
                norm_j = np.linalg.norm(emb_j)
                if norm_j < 1e-8:
                    continue

                cosine = float(np.dot(emb_i, emb_j) / (norm_i * norm_j))
                if cosine >= threshold:
                    cluster.append(entry_j)
                    used.add(j)

            if len(cluster) >= min_size:
                clusters.append(cluster)

        return clusters

    # ── Phase 3.5: MEASURE ────────────────────────────────────────

    def _phase_measure(self) -> Dict[str, Any]:
        """Compute socialization metrics (from Moltbook Socialization paper).

        Runs after COMPRESS (Phase 3) to capture knowledge state after
        decay/strengthen/compress, but before new edges are created.
        """
        if not self._socialization:
            return {}

        try:
            return self._socialization.compute_all()
        except Exception as e:
            logger.warning("Phase MEASURE failed: %s", e)
            return {}

    # ── Phase 4: CONNECT ─────────────────────────────────────────

    def _phase_connect(self, window_s: float = 120.0) -> int:
        """Strengthen edges between entries accessed together recently.

        For pairs of entries accessed within the same time window,
        create or strengthen "consolidation" edges in MoltbookGraph
        if their embeddings have cosine similarity > 0.5.
        """
        if not self._moltbook:
            return 0

        # Get MoltbookGraph if available
        graph = getattr(self._moltbook, '_graph', None)
        if graph is None:
            return 0

        try:
            now = time.time()
            recent = [
                e for e in self._moltbook._entries.values()
                if now - e.last_accessed < window_s
                and e.semantic_embedding is not None
            ]

            if len(recent) < 2:
                return 0

            connections = 0
            for i in range(len(recent)):
                emb_i = recent[i].semantic_embedding
                norm_i = np.linalg.norm(emb_i)
                if norm_i < 1e-8:
                    continue

                for j in range(i + 1, min(i + 10, len(recent))):
                    emb_j = recent[j].semantic_embedding
                    norm_j = np.linalg.norm(emb_j)
                    if norm_j < 1e-8:
                        continue

                    cosine = float(np.dot(emb_i, emb_j) / (norm_i * norm_j))
                    if cosine > 0.5:
                        graph.link(
                            recent[i].id, recent[j].id,
                            link_type='consolidation',
                            weight=cosine,
                        )
                        connections += 1

            self._total_connections_made += connections
            return connections

        except Exception as e:
            logger.warning("Phase CONNECT failed: %s", e)
            return 0

    # ── Phase 5: RECORD ──────────────────────────────────────────

    def _phase_record(self) -> int:
        """Drain event buffer into DualGraph (KotlinGraph)."""
        if not self._dual_graph:
            # Still drain the buffer to prevent unbounded growth
            with self._buffer_lock:
                self._event_buffer.clear()
            return 0

        # Atomically grab all events
        with self._buffer_lock:
            events = list(self._event_buffer)
            self._event_buffer.clear()

        recorded = 0
        for evt in events:
            try:
                self._dual_graph.record_event(
                    state=evt.get('state', {}),
                    action=evt.get('action', 'unknown'),
                    next_state=evt.get('next_state', {}),
                    reward=evt.get('reward', 0.0),
                    done=evt.get('done', False),
                    metadata=evt.get('metadata'),
                )
                recorded += 1
            except Exception as e:
                logger.warning("Failed to record event: %s", e)

        self._total_events_recorded += recorded
        return recorded

    # ── Phase 6: MINE ────────────────────────────────────────────

    def _phase_mine(self) -> bool:
        """Run KuroGraph pattern mining on KotlinGraph episodes.

        Only mines if there are new episodes since last mine.
        """
        if not self._dual_graph:
            return False

        try:
            kg_stats = self._dual_graph.kotlingraph.get_statistics()
            if kg_stats.get('total_events', 0) < 5:
                return False  # Not enough data yet

            self._dual_graph.force_mine()
            return True
        except Exception as e:
            logger.warning("Phase MINE failed: %s", e)
            return False

    # ── Phase 7: PERSIST ─────────────────────────────────────────

    def _phase_persist(self) -> Dict[str, bool]:
        """Save all memory stores to disk."""
        results = {'moltbook': False, 'dual_graph': False, 'evolution': False}

        # MoltbookStore
        if self._moltbook:
            try:
                self._moltbook.save_to_disk()
                results['moltbook'] = True
            except Exception as e:
                logger.warning("Persist MoltbookStore failed: %s", e)

        # DualGraph (KotlinGraph + KuroGraph)
        if self._dual_graph:
            try:
                self._dual_graph.save('memory')
                results['dual_graph'] = True
            except Exception as e:
                logger.warning("Persist DualGraph failed: %s", e)

        # ThoughtEvolutionEngine
        if self._evolution:
            try:
                self._evolution.save_state(self._evo_path)
                results['evolution'] = True
            except Exception as e:
                logger.warning("Persist ThoughtEvolution failed: %s", e)

        # Tombstones
        try:
            self._tombstone_log.save()
        except Exception as e:
            logger.warning("Persist tombstones failed: %s", e)

        return results

    # ── Phase 8: CLUSTER ────────────────────────────────────────

    def _phase_cluster(self) -> Dict[str, Any]:
        """Level-2 clustering: group Klotski clusters into meta-areals.

        Uses cached Klotski cluster results (from /api/cortex/thought-clusters)
        and clusters their centroids to find higher-order knowledge domains.

        Level 1: 744 entries → 40 Klotski clusters (done by cortex.py)
        Level 2: 40 centroids → 3-8 meta-areals (done here)
        """
        if not self._meta_graph:
            return {'skipped': True, 'reason': 'no_meta_graph'}
        if not self._moltbook:
            return {'skipped': True, 'reason': 'no_moltbook'}

        # Get cached Klotski clusters (produced by /api/cortex/thought-clusters)
        # The Consolidator doesn't have direct access to app.state, so we
        # run Level-1 clustering inline if no cache exists.
        try:
            entries = list(self._moltbook._entries.values())

            # Build Level-1 clusters from Moltbook entries with embeddings
            import numpy as np
            from core.semantic_clustering import _cosine_distance_matrix, _dbscan
            from collections import Counter

            valid_entries = []
            vectors = []
            for entry in entries:
                emb = getattr(entry, 'semantic_embedding', None)
                if emb is not None and len(getattr(entry, 'content', '')) >= 10:
                    valid_entries.append(entry)
                    vectors.append(emb)

            if len(valid_entries) < 4:
                return {'skipped': True, 'reason': 'too_few_entries', 'count': len(valid_entries)}

            vec_matrix = np.array(vectors, dtype=np.float32)
            dist_matrix = _cosine_distance_matrix(vec_matrix)
            labels = _dbscan(dist_matrix, eps=0.45, min_samples=2)

            # Build Klotski cluster dicts
            cluster_map: Dict[int, List[int]] = {}
            for idx, lbl in enumerate(labels):
                if lbl != -1:
                    cluster_map.setdefault(int(lbl), []).append(idx)

            if len(cluster_map) < 2:
                return {'skipped': True, 'reason': 'too_few_l1_clusters', 'count': len(cluster_map)}

            klotski_clusters = []
            for cid, member_indices in sorted(cluster_map.items()):
                node_ids = [str(getattr(valid_entries[i], 'id', id(valid_entries[i]))) for i in member_indices]
                # Label from common words
                words = []
                for i in member_indices:
                    for w in valid_entries[i].content.split()[:10]:
                        cleaned = w.strip(".,;:!?()[]{}\"'-—").lower()
                        if len(cleaned) > 3:
                            words.append(cleaned)
                common = Counter(words).most_common(3)
                label = " / ".join(w.title() for w, _ in common) if common else f"Cluster {cid}"

                klotski_clusters.append({
                    'cluster_id': cid,
                    'label': label,
                    'size': len(member_indices),
                    'coherence': 0.5,
                    'node_ids': node_ids,
                })

            # Level-2: cluster the cluster centroids into meta-areals
            areals = self._meta_graph.update_from_klotski_clusters(
                klotski_clusters=klotski_clusters,
                klotski_entries=valid_entries,
            )

            return {
                'num_areals': len(areals),
                'l1_clusters': len(klotski_clusters),
                'l1_entries': len(valid_entries),
                'areal_topics': [a.dominant_topic for a in areals],
            }

        except Exception as e:
            logger.warning("Phase CLUSTER failed: %s", e)
            return {'error': str(e)}

    # ── Phase 9: SYNTHESIZE ──────────────────────────────────────

    def _phase_synthesize(self) -> Dict[str, Any]:
        """Cross-cluster LLM knowledge exchange.

        For the most connected cluster pair, extract representative thoughts
        and synthesize cross-cluster insights via LLM.
        Rate-limited to 1 LLM call per cycle.
        """
        if not self._meta_graph:
            return {'skipped': True, 'reason': 'no_meta_graph'}

        pairs = self._meta_graph.get_adjacent_pairs(top_k=1)
        if not pairs:
            return {'skipped': True, 'reason': 'no_adjacent_pairs'}

        cluster_a_id, cluster_b_id, similarity = pairs[0]
        cluster_a = self._meta_graph.get_cluster_by_id(cluster_a_id)
        cluster_b = self._meta_graph.get_cluster_by_id(cluster_b_id)

        if not cluster_a or not cluster_b:
            return {'skipped': True, 'reason': 'clusters_not_found'}

        # Try KnowledgeSynthesizer first, then MicroAgentPool
        synthesized = 0

        try:
            if self._knowledge_synth:
                # Use detect_structural_similarity for shared patterns
                entries = [
                    f"Cluster '{cluster_a.dominant_topic}': {', '.join(cluster_a.member_thought_ids[:3])}",
                    f"Cluster '{cluster_b.dominant_topic}': {', '.join(cluster_b.member_thought_ids[:3])}",
                ]
                results = self._knowledge_synth.detect_structural_similarity(entries, max_results=1)
                if results:
                    best = results[0]
                    self._meta_graph.add_synthesis(
                        cluster_a_id, cluster_b_id,
                        insight=best.content,
                        score=best.confidence if best.confidence > 0 else similarity,
                    )
                    synthesized += 1

            elif self._pool:
                # Fallback: direct LLM call via MicroAgentPool
                prompt = (
                    f"Two knowledge clusters have been identified:\n"
                    f"Cluster A ({cluster_a.dominant_topic}): {cluster_a.size} thoughts, "
                    f"coherence {cluster_a.coherence:.2f}\n"
                    f"Cluster B ({cluster_b.dominant_topic}): {cluster_b.size} thoughts, "
                    f"coherence {cluster_b.coherence:.2f}\n"
                    f"Similarity between clusters: {similarity:.2f}\n\n"
                    f"What emergent insight connects these two knowledge domains? "
                    f"Answer in 1-2 sentences."
                )
                try:
                    response = self._pool._call_agent('connector', prompt)
                    if response:
                        insight_text = response if isinstance(response, str) else str(response)
                        self._meta_graph.add_synthesis(
                            cluster_a_id, cluster_b_id,
                            insight=insight_text,
                            score=similarity,
                        )
                        synthesized += 1

                        # Store as MoltbookEntry
                        if self._moltbook:
                            self._moltbook.add_entry(
                                content=f"[Meta-Synthesis] {cluster_a.dominant_topic} <-> "
                                        f"{cluster_b.dominant_topic}: {insight_text}",
                                source_agent="meta_graph:synthesis",
                                entry_type="wisdom",
                                tags=["cluster_synthesis", "meta_graph",
                                      cluster_a.dominant_topic.lower(),
                                      cluster_b.dominant_topic.lower()],
                                confidence=similarity,
                            )
                except Exception as e:
                    logger.warning("LLM synthesis call failed: %s", e)

        except Exception as e:
            logger.warning("Phase SYNTHESIZE failed: %s", e)
            return {'error': str(e)}

        return {
            'synthesized': synthesized,
            'pair': f"{cluster_a.dominant_topic} <-> {cluster_b.dominant_topic}",
            'similarity': round(similarity, 3),
        }

    # ── Phase 10: META_ROOT ──────────────────────────────────────

    def _phase_meta_root(self) -> Dict[str, Any]:
        """Compute meta-graph root, run CTM reasoning, update KuroGraph overlay.

        1. Compute reachability → find meta-root
        2. KlotskiCTM reasons about cluster topology (optional)
        3. Record cluster transitions in DualGraph
        4. Update KuroGraph cluster overlay
        """
        if not self._meta_graph:
            return {'skipped': True, 'reason': 'no_meta_graph'}

        if not self._meta_graph._clusters:
            return {'skipped': True, 'reason': 'no_clusters'}

        result: Dict[str, Any] = {}

        try:
            # 1. Compute reachability
            meta_root_id = self._meta_graph.compute_reachability()
            meta_root = self._meta_graph.get_cluster_by_id(meta_root_id) if meta_root_id is not None else None
            result['meta_root_id'] = meta_root_id
            result['meta_root_topic'] = meta_root.dominant_topic if meta_root else None

            # 2. KlotskiCTM reasoning (optional)
            if self._klotski_ctm and meta_root:
                try:
                    cluster_topics = [c.dominant_topic for c in self._meta_graph._clusters]
                    task = (
                        f"Navigate knowledge graph with {len(self._meta_graph._clusters)} domains: "
                        f"{', '.join(cluster_topics[:5])}. "
                        f"Meta-root at '{meta_root.dominant_topic}' "
                        f"(reachability={self._meta_graph._meta_root_reachability:.2f}). "
                        f"Find optimal learning paths."
                    )
                    brain_state = {
                        f'cluster_{c.cluster_id}': c.avg_fitness
                        for c in self._meta_graph._clusters
                    }
                    ctm_result = self._klotski_ctm.reason(
                        task=task,
                        brain_state=brain_state,
                        max_steps=20,
                    )

                    from core.meta_knowledge_graph import CTMInsight
                    insight = CTMInsight(
                        meta_root_id=meta_root_id,
                        consciousness_score=ctm_result.consciousness,
                        reasoning_steps=ctm_result.steps_taken,
                        reasoning_trace=ctm_result.reasoning_trace[:5],
                    )
                    self._meta_graph.add_ctm_insight(insight)

                    result['ctm_consciousness'] = round(ctm_result.consciousness, 3)
                    result['ctm_steps'] = ctm_result.steps_taken
                except Exception as e:
                    logger.debug("CTM reasoning skipped: %s", e)
                    result['ctm_skipped'] = str(e)

            # 3. Record cluster transition in DualGraph
            if self._dual_graph:
                try:
                    cluster_state = {
                        'cluster_ids': [c.cluster_id for c in self._meta_graph._clusters],
                        'cluster_sizes': [c.size for c in self._meta_graph._clusters],
                        'meta_root': meta_root_id,
                    }
                    avg_coherence = float(
                        sum(c.coherence for c in self._meta_graph._clusters)
                        / max(1, len(self._meta_graph._clusters))
                    )
                    self._dual_graph.record_event(
                        state=cluster_state,
                        action='meta_cycle',
                        next_state=cluster_state,
                        reward=avg_coherence,
                        done=False,
                        metadata={'cycle': self._cycle_count},
                    )
                except Exception as e:
                    logger.debug("DualGraph record skipped: %s", e)

            # 4. Update KuroGraph cluster overlay
            if self._dual_graph:
                kuro = getattr(self._dual_graph, 'kurograph', None)
                if kuro:
                    try:
                        overlay_data = self._meta_graph.get_cluster_overlay()
                        kuro.set_cluster_overlay(overlay_data)
                    except Exception as e:
                        logger.debug("KuroGraph overlay skipped: %s", e)

        except Exception as e:
            logger.warning("Phase META_ROOT failed: %s", e)
            result['error'] = str(e)

        return result

    # ── Full Cycle ───────────────────────────────────────────────

    def run_cycle(self) -> Dict[str, Any]:
        """Execute all 10 phases in sequence. Returns cycle report."""
        t0 = time.time()
        report: Dict[str, Any] = {}

        try:
            report['decay'] = self._phase_decay()
            report['strengthened'] = self._phase_strengthen()
            report['compressed'] = self._phase_compress()
            report['measured'] = self._phase_measure()
            report['connections'] = self._phase_connect()
            report['recorded'] = self._phase_record()
            report['mined'] = self._phase_mine()
            # Phases 8-10: Meta-Knowledge Graph
            edges_before = len(self._meta_graph._inter_cluster_edges) if self._meta_graph else 0
            report['clustered'] = self._phase_cluster()
            edges_after = len(self._meta_graph._inter_cluster_edges) if self._meta_graph else 0
            if edges_after > edges_before and hasattr(self, '_outcome_tracker') and self._outcome_tracker:
                self._outcome_tracker.on_new_mkg_edges(edges_after - edges_before)
            report['synthesized'] = self._phase_synthesize()
            report['meta_root'] = self._phase_meta_root()
            # Persist LAST (after all phases including meta-graph)
            report['persisted'] = self._phase_persist()
        except Exception as e:
            logger.error("Consolidation cycle error: %s", e)
            report['error'] = str(e)

        duration = time.time() - t0
        self._cycle_count += 1
        self._last_cycle_time = time.time()
        self._last_cycle_duration = duration
        report['cycle'] = self._cycle_count
        report['duration_s'] = round(duration, 3)

        logger.info(
            "Consolidation cycle #%d complete (%.2fs): "
            "decay=%s, strengthened=%s, compressed=%s, "
            "measured=%s, recorded=%s, clustered=%s, meta_root=%s, persisted=%s",
            self._cycle_count, duration,
            report.get('decay'), report.get('strengthened'),
            report.get('compressed'), report.get('measured'),
            report.get('recorded'), report.get('clustered'),
            report.get('meta_root'), report.get('persisted'),
        )

        return report

    # ── Background Thread ────────────────────────────────────────

    def start(self) -> None:
        """Start the background consolidation thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True,
            name="MemoryConsolidator",
        )
        self._thread.start()
        logger.info("MemoryConsolidator started (every %.0fs)", self._interval)

    def stop(self) -> None:
        """Stop the background thread and run a final persist."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        # Final save
        try:
            self._phase_persist()
            logger.info("Final memory persistence complete")
        except Exception as e:
            logger.error("Final persist failed: %s", e)

    def _run_loop(self) -> None:
        """Background loop: sleep → consolidate → repeat."""
        # Initial delay to let system warm up
        time.sleep(5.0)

        while self._running:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error("Consolidation loop error: %s", e)

            # Sleep in small increments so stop() is responsive
            for _ in range(int(self._interval)):
                if not self._running:
                    break
                time.sleep(1.0)

    # ── Manual Controls ──────────────────────────────────────────

    def save_all(self) -> Dict[str, bool]:
        """Manual trigger for Phase 7 (PERSIST) only."""
        return self._phase_persist()

    # ── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return consolidation metrics."""
        return {
            'cycle_count': self._cycle_count,
            'total_events_recorded': self._total_events_recorded,
            'total_compressed': self._total_compressed,
            'total_connections_made': self._total_connections_made,
            'total_decayed': self._total_decayed,
            'total_strengthened': self._total_strengthened,
            'total_evicted': self._tombstone_log._total_forgotten,
            'tombstone_count': len(self._tombstone_log._tombstones),
            'last_cycle_time': self._last_cycle_time,
            'last_cycle_duration': self._last_cycle_duration,
            'buffer_size': self.get_buffer_size(),
            'running': self._running,
            'interval_s': self._interval,
        }
