"""
MetaKnowledgeGraph — Emergent Knowledge Pipeline for Klotski 3D

Builds a meta-level knowledge graph from ContinuousThinkingEngine thoughts:
1. DBSCAN clusters on 384-dim thought embeddings
2. Inter-cluster edges via centroid cosine similarity
3. Meta-root computation (highest semantic reachability)
4. LLM cross-cluster synthesis storage
5. KlotskiCTM reasoning trace storage

Designed to be driven by MemoryConsolidator phases 8-10.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import networkx as nx
except ImportError:
    nx = None

from core.semantic_clustering import _cosine_distance_matrix, _dbscan

logger = logging.getLogger('brain.meta_knowledge_graph')


# ── Data Classes ──────────────────────────────────────────────────

@dataclass
class ClusterSnapshot:
    """Snapshot of a single thought cluster."""
    cluster_id: int
    centroid: np.ndarray            # 384-dim embedding centroid
    centroid_3d: np.ndarray         # PCA 3D position for visualization
    member_thought_ids: List[str]
    size: int
    dominant_topic: str
    avg_fitness: float
    coherence: float                # intra-cluster cosine similarity

    def to_dict(self) -> Dict[str, Any]:
        return {
            'cluster_id': self.cluster_id,
            'centroid_3d': {
                'x': round(float(self.centroid_3d[0]), 3),
                'y': round(float(self.centroid_3d[1]), 3),
                'z': round(float(self.centroid_3d[2]), 3),
            },
            'member_count': self.size,
            'dominant_topic': self.dominant_topic,
            'avg_fitness': round(self.avg_fitness, 3),
            'coherence': round(self.coherence, 3),
            'member_thought_ids': self.member_thought_ids,
        }


@dataclass
class CrossClusterSynthesis:
    """LLM-generated insight connecting two clusters."""
    cluster_a_id: int
    cluster_b_id: int
    insight: str
    score: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'cluster_a': self.cluster_a_id,
            'cluster_b': self.cluster_b_id,
            'insight': self.insight,
            'score': round(self.score, 3),
            'timestamp': self.timestamp,
        }


@dataclass
class CTMInsight:
    """KlotskiCTM reasoning result about cluster topology."""
    meta_root_id: int
    consciousness_score: float
    reasoning_steps: int
    reasoning_trace: List[str]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'meta_root_id': self.meta_root_id,
            'consciousness': round(self.consciousness_score, 3),
            'steps': self.reasoning_steps,
            'trace': self.reasoning_trace[:5],  # Truncate for API
            'timestamp': self.timestamp,
        }


# ── Stop words for topic extraction ──────────────────────────────

_STOP_WORDS = frozenset({
    "der", "die", "das", "und", "in", "von", "mit", "für", "ein", "eine",
    "auf", "ist", "im", "den", "dem", "des", "zu", "nicht", "sich", "aus",
    "the", "a", "an", "and", "is", "for", "to", "of", "in", "on", "at",
    "by", "with", "from", "or", "as", "it", "be", "are", "was", "has",
    "this", "that", "what", "how", "can", "will", "about", "into",
})


# ── Main Class ───────────────────────────────────────────────────

class MetaKnowledgeGraph:
    """NetworkX DiGraph where nodes = clusters, edges = semantic transitions.

    Driven by MemoryConsolidator phases:
        Phase 8 CLUSTER:    update_clusters()
        Phase 9 SYNTHESIZE: add_synthesis()
        Phase 10 META_ROOT: compute_reachability(), add_ctm_insight()
    """

    def __init__(self, semantic_index=None):
        self._graph = nx.DiGraph() if nx else None
        self._clusters: List[ClusterSnapshot] = []
        self._meta_root_id: Optional[int] = None
        self._meta_root_reachability: float = 0.0
        self._synthesis_results: List[CrossClusterSynthesis] = []
        self._ctm_insights: List[CTMInsight] = []
        self._semantic_index = semantic_index
        self._inter_cluster_edges: List[Dict[str, Any]] = []
        self._last_update: float = 0.0

        # Stats
        self._cycle_count: int = 0
        self._total_syntheses: int = 0

    # ── Phase 8: CLUSTER ─────────────────────────────────────────

    def update_clusters(
        self,
        thought_contents: List[str],
        thought_ids: List[str],
        thought_fitnesses: List[float],
        embeddings: np.ndarray,
        eps: float = 0.45,
        min_samples: int = 2,
        spread: float = 12.0,
    ) -> List[ClusterSnapshot]:
        """DBSCAN on thought embeddings, build cluster snapshots + inter-cluster edges.

        Args:
            thought_contents: Text content of each thought
            thought_ids: Unique ID of each thought
            thought_fitnesses: Fitness score of each thought
            embeddings: (N, 384) embedding matrix
            eps: DBSCAN epsilon (cosine distance)
            min_samples: DBSCAN minimum cluster size
            spread: PCA 3D spread factor

        Returns:
            List of ClusterSnapshot objects
        """
        n = len(thought_contents)
        if n < min_samples:
            logger.debug("Not enough thoughts for clustering: %d < %d", n, min_samples)
            return []

        # ── DBSCAN clustering ──
        dist_matrix = _cosine_distance_matrix(embeddings)
        labels = _dbscan(dist_matrix, eps=eps, min_samples=min_samples)

        # ── PCA to 3D for visualization ──
        coords_3d = self._pca_3d(embeddings, spread=spread)

        # ── Build cosine similarity matrix ──
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        normed = embeddings / norms
        sim_matrix = np.dot(normed, normed.T)

        # ── Build ClusterSnapshots ──
        cluster_map: Dict[int, List[int]] = {}
        for idx, lbl in enumerate(labels):
            if lbl == -1:
                continue
            cluster_map.setdefault(int(lbl), []).append(idx)

        snapshots: List[ClusterSnapshot] = []
        centroids_384: List[np.ndarray] = []
        centroids_3d: List[np.ndarray] = []

        for cid, member_indices in sorted(cluster_map.items()):
            member_vecs = embeddings[member_indices]
            member_3d = coords_3d[member_indices]

            # Centroid
            centroid = member_vecs.mean(axis=0)
            centroid_3d = member_3d.mean(axis=0)

            # Coherence (avg pairwise cosine similarity)
            if len(member_indices) >= 2:
                m_sims = sim_matrix[np.ix_(member_indices, member_indices)]
                mn = len(member_indices)
                coherence = float(
                    sum(m_sims[i, j] for i in range(mn) for j in range(i + 1, mn))
                    / max(1, mn * (mn - 1) // 2)
                )
            else:
                coherence = 1.0

            # Dominant topic (most common meaningful words)
            dominant_topic = self._extract_topic(
                [thought_contents[i] for i in member_indices]
            )

            # Average fitness
            avg_fitness = float(np.mean([thought_fitnesses[i] for i in member_indices]))

            snapshot = ClusterSnapshot(
                cluster_id=cid,
                centroid=centroid,
                centroid_3d=centroid_3d,
                member_thought_ids=[thought_ids[i] for i in member_indices],
                size=len(member_indices),
                dominant_topic=dominant_topic,
                avg_fitness=avg_fitness,
                coherence=coherence,
            )
            snapshots.append(snapshot)
            centroids_384.append(centroid)
            centroids_3d.append(centroid_3d)

        # ── Inter-cluster edges (centroid cosine similarity) ──
        self._inter_cluster_edges = []
        if len(centroids_384) >= 2:
            cent_matrix = np.array(centroids_384)
            c_norms = np.linalg.norm(cent_matrix, axis=1, keepdims=True)
            c_norms[c_norms == 0] = 1e-10
            c_normed = cent_matrix / c_norms
            c_sim = np.dot(c_normed, c_normed.T)

            for i in range(len(snapshots)):
                for j in range(i + 1, len(snapshots)):
                    sim_val = float(c_sim[i, j])
                    if sim_val > 0.3:  # Threshold for inter-cluster edge
                        self._inter_cluster_edges.append({
                            'source': snapshots[i].cluster_id,
                            'target': snapshots[j].cluster_id,
                            'similarity': round(sim_val, 3),
                        })

        # ── Update NetworkX graph ──
        if self._graph is not None:
            self._graph.clear()
            for snap in snapshots:
                self._graph.add_node(
                    snap.cluster_id,
                    topic=snap.dominant_topic,
                    size=snap.size,
                    fitness=snap.avg_fitness,
                    coherence=snap.coherence,
                )
            for edge in self._inter_cluster_edges:
                self._graph.add_edge(
                    edge['source'], edge['target'],
                    weight=edge['similarity'],
                )
                self._graph.add_edge(
                    edge['target'], edge['source'],
                    weight=edge['similarity'],
                )

        self._clusters = snapshots
        self._last_update = time.time()
        self._cycle_count += 1

        logger.info(
            "Meta-graph updated: %d clusters, %d inter-cluster edges, %d total thoughts",
            len(snapshots), len(self._inter_cluster_edges), n
        )

        return snapshots

    # ── Level-2 Clustering (Cluster-of-Clusters) ────────────────

    def update_from_klotski_clusters(
        self,
        klotski_clusters: List[Dict[str, Any]],
        klotski_entries: List[Any],
        n_areals: Optional[int] = None,
        spread: float = 10.0,
    ) -> List[ClusterSnapshot]:
        """Build meta-areals by clustering Klotski cluster centroids.

        This is LEVEL 2: instead of clustering raw entries, we cluster
        the centroids of existing Klotski clusters to find higher-order
        knowledge domains (areals).

        Uses agglomerative clustering (not DBSCAN) because cluster centroids
        from the same project have very similar cosine distances — DBSCAN
        can't find natural density gaps. Agglomerative with a fixed k
        guarantees meaningful separation.

        Args:
            klotski_clusters: List of cluster dicts from /api/cortex/thought-clusters
                              Each has: cluster_id, label, size, coherence, centroid, node_ids
            klotski_entries: List of Moltbook entries (for embedding lookup)
            n_areals: Target number of areals (default: max(3, round(sqrt(n_clusters))))
            spread: PCA 3D spread

        Returns:
            List of ClusterSnapshot (meta-areals)
        """
        if len(klotski_clusters) < 3:
            logger.debug("Not enough Klotski clusters for meta-areals: %d", len(klotski_clusters))
            return []

        # Build entry lookup for embeddings
        entry_by_id = {}
        for entry in klotski_entries:
            eid = str(getattr(entry, 'id', id(entry)))
            emb = getattr(entry, 'semantic_embedding', None)
            if emb is not None:
                entry_by_id[eid] = {
                    'embedding': emb,
                    'content': getattr(entry, 'content', ''),
                    'confidence': getattr(entry, 'confidence', 0.5),
                }

        # Compute centroid embedding for each Klotski cluster
        cluster_centroids_384 = []
        valid_klotski = []
        for kc in klotski_clusters:
            node_ids = kc.get('node_ids', [])
            member_embs = []
            for nid in node_ids:
                info = entry_by_id.get(nid)
                if info:
                    member_embs.append(info['embedding'])
            if not member_embs:
                continue
            centroid = np.mean(member_embs, axis=0)
            cluster_centroids_384.append(centroid)
            valid_klotski.append(kc)

        if len(cluster_centroids_384) < 3:
            logger.debug("Not enough clusters with embeddings: %d", len(cluster_centroids_384))
            return []

        centroid_matrix = np.array(cluster_centroids_384, dtype=np.float32)
        n = len(valid_klotski)

        # Target number of areals (user param takes precedence)
        if n_areals is None:
            n_areals = max(3, min(8, round(n ** 0.5)))
        n_areals = max(2, min(n_areals, n))

        # ── Agglomerative clustering on cosine distance ──
        dist_matrix = _cosine_distance_matrix(centroid_matrix)
        labels = self._agglomerative_cluster(dist_matrix, n_areals)

        # ── PCA 3D for areal positions ──
        coords_3d = self._pca_3d(centroid_matrix, spread=spread)

        # ── Cosine similarity between centroids ──
        norms = np.linalg.norm(centroid_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        normed = centroid_matrix / norms
        sim_matrix = np.dot(normed, normed.T)

        # ── Build meta-areal snapshots ──
        areal_map: Dict[int, List[int]] = {}
        for idx, lbl in enumerate(labels):
            if lbl == -1:
                continue
            areal_map.setdefault(int(lbl), []).append(idx)

        snapshots: List[ClusterSnapshot] = []
        areal_centroids_384: List[np.ndarray] = []

        for areal_id, member_indices in sorted(areal_map.items()):
            # Areal centroid = mean of member cluster centroids
            member_vecs = centroid_matrix[member_indices]
            areal_centroid = member_vecs.mean(axis=0)
            areal_centroid_3d = coords_3d[member_indices].mean(axis=0)

            # Collect all Klotski cluster info for this areal
            member_cluster_labels = [valid_klotski[i].get('label', f'Cluster {i}') for i in member_indices]
            member_cluster_sizes = [valid_klotski[i].get('size', 0) for i in member_indices]
            total_members = sum(member_cluster_sizes)

            # All node IDs from member clusters
            all_node_ids = []
            for i in member_indices:
                all_node_ids.extend(valid_klotski[i].get('node_ids', []))

            # Coherence (avg pairwise sim between member cluster centroids)
            if len(member_indices) >= 2:
                m_sims = sim_matrix[np.ix_(member_indices, member_indices)]
                mn = len(member_indices)
                coherence = float(
                    sum(m_sims[i, j] for i in range(mn) for j in range(i + 1, mn))
                    / max(1, mn * (mn - 1) // 2)
                )
            else:
                coherence = 1.0

            # Avg fitness from member cluster confidences
            avg_fitness = float(np.mean([
                valid_klotski[i].get('coherence', 0.5) for i in member_indices
            ]))

            # Dominant topic: combine cluster labels
            topic = self._combine_cluster_labels(member_cluster_labels)

            snapshot = ClusterSnapshot(
                cluster_id=areal_id,
                centroid=areal_centroid,
                centroid_3d=areal_centroid_3d,
                member_thought_ids=all_node_ids,
                size=total_members,
                dominant_topic=topic,
                avg_fitness=avg_fitness,
                coherence=coherence,
            )
            snapshots.append(snapshot)
            areal_centroids_384.append(areal_centroid)

        # ── Inter-areal edges ──
        self._inter_cluster_edges = []
        if len(areal_centroids_384) >= 2:
            a_matrix = np.array(areal_centroids_384)
            a_norms = np.linalg.norm(a_matrix, axis=1, keepdims=True)
            a_norms[a_norms == 0] = 1e-10
            a_normed = a_matrix / a_norms
            a_sim = np.dot(a_normed, a_normed.T)

            for i in range(len(snapshots)):
                for j in range(i + 1, len(snapshots)):
                    sim_val = float(a_sim[i, j])
                    if sim_val > 0.3:
                        self._inter_cluster_edges.append({
                            'source': snapshots[i].cluster_id,
                            'target': snapshots[j].cluster_id,
                            'similarity': round(sim_val, 3),
                        })

        # ── Update NetworkX graph ──
        if self._graph is not None:
            self._graph.clear()
            for snap in snapshots:
                self._graph.add_node(
                    snap.cluster_id,
                    topic=snap.dominant_topic,
                    size=snap.size,
                    fitness=snap.avg_fitness,
                    coherence=snap.coherence,
                )
            for edge in self._inter_cluster_edges:
                self._graph.add_edge(edge['source'], edge['target'], weight=edge['similarity'])
                self._graph.add_edge(edge['target'], edge['source'], weight=edge['similarity'])

        self._clusters = snapshots
        self._last_update = time.time()
        self._cycle_count += 1

        # Log unclustered
        unclustered = sum(1 for lbl in labels if lbl == -1)
        logger.info(
            "Meta-areals updated: %d areals from %d Klotski clusters (%d unclustered), %d inter-areal edges",
            len(snapshots), n, unclustered, len(self._inter_cluster_edges)
        )

        return snapshots

    @staticmethod
    def _combine_cluster_labels(labels: List[str], max_parts: int = 3) -> str:
        """Create a topic name from multiple cluster labels."""
        # Collect all meaningful words from cluster labels
        words: List[str] = []
        for label in labels:
            for part in label.replace('/', ' ').split():
                cleaned = part.strip(".,;:!?()[]{}\"'-—").strip()
                if len(cleaned) > 2 and cleaned.lower() not in _STOP_WORDS:
                    words.append(cleaned)

        if not words:
            return "Mixed Areal"

        common = Counter(words).most_common(max_parts)
        return " / ".join(w.title() for w, _ in common)

    @staticmethod
    def _agglomerative_cluster(dist_matrix: np.ndarray, k: int) -> np.ndarray:
        """Ward-linkage agglomerative clustering for balanced areals.

        Ward's method minimizes within-cluster variance at each merge step,
        producing much more balanced clusters than single/average linkage.
        Uses scipy when available, falls back to a simple implementation.

        Returns label array with exactly k clusters (0 to k-1).
        """
        n = dist_matrix.shape[0]
        if k >= n:
            return np.arange(n)

        try:
            from scipy.cluster.hierarchy import linkage, fcluster
            from scipy.spatial.distance import squareform

            # Convert square distance matrix to condensed form
            condensed = squareform(dist_matrix, checks=False)
            # Ward linkage for balanced clusters
            Z = linkage(condensed, method='ward')
            labels = fcluster(Z, t=k, criterion='maxclust') - 1  # 0-indexed
            return labels

        except ImportError:
            # Fallback: simple average-linkage
            labels = np.arange(n)
            current_k = n
            d = dist_matrix.copy()
            np.fill_diagonal(d, np.inf)

            while current_k > k:
                flat_idx = np.argmin(d)
                i, j = divmod(int(flat_idx), n)
                merge_from = labels[j]
                merge_to = labels[i]
                labels[labels == merge_from] = merge_to

                members_i = np.where(labels == merge_to)[0]
                for x in range(n):
                    if labels[x] == merge_to:
                        d[i, x] = np.inf
                        d[x, i] = np.inf
                        d[j, x] = np.inf
                        d[x, j] = np.inf
                    else:
                        avg_dist = float(np.mean([dist_matrix[x, m] for m in members_i]))
                        d[i, x] = avg_dist
                        d[x, i] = avg_dist
                        d[j, x] = np.inf
                        d[x, j] = np.inf
                current_k -= 1

            unique = sorted(set(labels))
            remap = {old: new for new, old in enumerate(unique)}
            return np.array([remap[l] for l in labels])

    # ── Phase 10: META_ROOT ──────────────────────────────────────

    def compute_reachability(self) -> Optional[int]:
        """Find meta-graph root = cluster with highest semantic reachability.

        Reachability = sum of cosine similarities to all other cluster centroids,
        weighted by cluster size. The root is the semantically most central node —
        from here you can reach any knowledge direction fastest.

        Returns:
            cluster_id of the meta-root, or None if no clusters
        """
        if len(self._clusters) < 2:
            if self._clusters:
                self._meta_root_id = self._clusters[0].cluster_id
                self._meta_root_reachability = 1.0
            return self._meta_root_id

        centroids = np.array([c.centroid for c in self._clusters])
        sizes = np.array([c.size for c in self._clusters], dtype=float)

        # Cosine similarity matrix
        norms = np.linalg.norm(centroids, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        normed = centroids / norms
        sim_matrix = np.dot(normed, normed.T)

        # Reachability = weighted sum of similarities
        # Weight by target cluster size (more knowledge = more important to reach)
        reachability = np.zeros(len(self._clusters))
        for i in range(len(self._clusters)):
            for j in range(len(self._clusters)):
                if i != j:
                    reachability[i] += sim_matrix[i, j] * sizes[j]

        root_idx = int(np.argmax(reachability))
        self._meta_root_id = self._clusters[root_idx].cluster_id
        self._meta_root_reachability = float(reachability[root_idx])

        logger.info(
            "Meta-root: cluster %d (%s), reachability=%.3f",
            self._meta_root_id,
            self._clusters[root_idx].dominant_topic,
            self._meta_root_reachability,
        )

        return self._meta_root_id

    # ── Synthesis Storage ────────────────────────────────────────

    def add_synthesis(
        self, cluster_a_id: int, cluster_b_id: int,
        insight: str, score: float
    ):
        """Store an LLM-generated cross-cluster insight."""
        synthesis = CrossClusterSynthesis(
            cluster_a_id=cluster_a_id,
            cluster_b_id=cluster_b_id,
            insight=insight,
            score=score,
        )
        self._synthesis_results.append(synthesis)
        self._total_syntheses += 1

        # Keep bounded
        if len(self._synthesis_results) > 100:
            self._synthesis_results = self._synthesis_results[-50:]

    def add_ctm_insight(self, insight: CTMInsight):
        """Store a KlotskiCTM reasoning result."""
        self._ctm_insights.append(insight)
        if len(self._ctm_insights) > 50:
            self._ctm_insights = self._ctm_insights[-25:]

    # ── Adjacent Cluster Pairs ───────────────────────────────────

    def get_adjacent_pairs(self, top_k: int = 3) -> List[Tuple[int, int, float]]:
        """Return top-K most connected cluster pairs for synthesis.

        Returns:
            List of (cluster_a_id, cluster_b_id, similarity) sorted by similarity desc
        """
        pairs = [
            (e['source'], e['target'], e['similarity'])
            for e in self._inter_cluster_edges
        ]
        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs[:top_k]

    def get_cluster_by_id(self, cluster_id: int) -> Optional[ClusterSnapshot]:
        """Look up a cluster by ID."""
        for c in self._clusters:
            if c.cluster_id == cluster_id:
                return c
        return None

    # ── Export ────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Export full meta-graph for /api/cortex/meta-graph endpoint."""
        meta_root_cluster = self.get_cluster_by_id(self._meta_root_id) if self._meta_root_id is not None else None

        return {
            'clusters': [c.to_dict() for c in self._clusters],
            'inter_cluster_edges': self._inter_cluster_edges,
            'meta_root': {
                'cluster_id': self._meta_root_id,
                'topic': meta_root_cluster.dominant_topic if meta_root_cluster else None,
                'reachability': round(self._meta_root_reachability, 3),
            } if self._meta_root_id is not None else None,
            'syntheses': [s.to_dict() for s in self._synthesis_results[-20:]],
            'ctm_insights': [i.to_dict() for i in self._ctm_insights[-5:]],
            'stats': {
                'total_clusters': len(self._clusters),
                'total_edges': len(self._inter_cluster_edges),
                'total_syntheses': self._total_syntheses,
                'cycle_count': self._cycle_count,
                'last_update': self._last_update,
            },
        }

    def get_cluster_overlay(self) -> List[Dict[str, Any]]:
        """Export cluster density data for KuroGraph overlay."""
        return [
            {
                'cluster_id': c.cluster_id,
                'dominant_topic': c.dominant_topic,
                'size': c.size,
                'avg_fitness': c.avg_fitness,
                'coherence': c.coherence,
                'connections': sum(
                    1 for e in self._inter_cluster_edges
                    if e['source'] == c.cluster_id or e['target'] == c.cluster_id
                ),
            }
            for c in self._clusters
        ]

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _pca_3d(vectors: np.ndarray, spread: float = 12.0) -> np.ndarray:
        """Project high-dim vectors to 3D via PCA."""
        n = vectors.shape[0]
        if n < 2:
            return np.zeros((n, 3))

        mean = vectors.mean(axis=0)
        centered = vectors - mean
        cov = np.dot(centered.T, centered) / max(1, n - 1)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        top3 = eigenvectors[:, -3:][:, ::-1]
        coords_3d = np.dot(centered, top3)

        max_range = max(1e-6, float(np.abs(coords_3d).max()))
        return coords_3d * (spread / max_range)

    @staticmethod
    def _extract_topic(contents: List[str], top_k: int = 3) -> str:
        """Extract dominant topic from thought contents."""
        words: List[str] = []
        for content in contents:
            for word in content.split()[:15]:
                cleaned = word.strip(".,;:!?()[]{}\"'-—").lower()
                if len(cleaned) > 3 and cleaned not in _STOP_WORDS:
                    words.append(cleaned)

        if not words:
            return "unknown"

        common = Counter(words).most_common(top_k)
        return " / ".join(w.title() for w, _ in common)
