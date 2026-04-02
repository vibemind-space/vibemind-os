"""
SocializationMetrics — Proving the Brain Actually Learns

Implements 6 metrics from the Moltbook Socialization paper
("Does Socialization Emerge in AI Agent Society?") to quantify
whether knowledge evolution is genuine or just noise.

Metrics:
    1. Semantic Drift     — centroid movement between cycles
    2. Drift Consistency  — coherence of drift direction over time
    3. KNN Density        — diversity vs redundancy of knowledge
    4. Concept Turnover   — birth/death of concepts
    5. Influence Delta    — impact of user interactions on knowledge
    6. Net Progress       — convergence toward higher-quality entries

Integration:
    Called as Phase 3.5 (MEASURE) in MemoryConsolidator's 30s cycle,
    between COMPRESS and CONNECT.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter, deque
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger('brain.socialization')

# ── Stopwords (minimal, no NLP dependency) ──────────────────────────
STOPWORDS = frozenset({
    'the', 'and', 'for', 'that', 'this', 'with', 'from', 'are', 'was',
    'were', 'been', 'being', 'have', 'has', 'had', 'having', 'does',
    'did', 'will', 'would', 'could', 'should', 'may', 'might', 'shall',
    'can', 'need', 'must', 'not', 'but', 'nor', 'yet', 'also', 'just',
    'than', 'then', 'too', 'very', 'more', 'most', 'other', 'some',
    'such', 'only', 'own', 'same', 'into', 'over', 'after', 'before',
    'between', 'under', 'about', 'each', 'which', 'when', 'where',
    'how', 'what', 'who', 'whom', 'why', 'all', 'any', 'both', 'few',
    'many', 'much', 'several', 'these', 'those', 'here', 'there',
})

_WORD_RE = re.compile(r'[a-zA-Z]{3,}')


class SocializationMetrics:
    """Quantify whether the brain's knowledge genuinely evolves.

    All metrics are computed per consolidation cycle (~30s) and stored
    as time-series for trend analysis and dashboard visualization.
    """

    def __init__(
        self,
        moltbook_store,
        embedding_dim: int = 384,
        k_neighbors: int = 10,
        projection_dim: int = 32,
        max_history: int = 500,
    ):
        """
        Args:
            moltbook_store: MoltbookStore instance (required).
            embedding_dim: Dimensionality of entry embeddings (default 384).
            k_neighbors: K for KNN density computation (default 10).
            projection_dim: Target dim for random projection (default 32).
            max_history: Max data points per time-series (default 500).
        """
        self._moltbook = moltbook_store
        self._dim = embedding_dim
        self._k = k_neighbors
        self._proj_dim = projection_dim

        # Seeded RNG for deterministic sampling and projection
        self._rng = np.random.RandomState(42)

        # Gaussian random projection matrix (embedding_dim → projection_dim)
        # Johnson-Lindenstrauss: preserves pairwise distances with high prob
        self._proj_matrix = self._rng.randn(projection_dim, embedding_dim).astype(np.float32)
        self._proj_matrix /= np.linalg.norm(self._proj_matrix, axis=1, keepdims=True)

        # Time-series storage (capped deques)
        self._centroid_history: deque = deque(maxlen=max_history)
        self._drift_history: deque = deque(maxlen=max_history)
        self._consistency_history: deque = deque(maxlen=max_history)
        self._density_history: deque = deque(maxlen=max_history)
        self._birth_rate_history: deque = deque(maxlen=max_history)
        self._death_rate_history: deque = deque(maxlen=max_history)
        self._influence_history: deque = deque(maxlen=max_history)
        self._net_progress_history: deque = deque(maxlen=max_history)

        # Drift vectors for consistency calculation
        self._drift_vectors: deque = deque(maxlen=max_history)

        # Pre-interaction snapshot for influence delta
        self._pre_interaction_centroid: Optional[np.ndarray] = None

        # Previous concept vocabulary for turnover
        self._prev_concepts: Set[str] = set()

        # Previous centroid per confidence quartile (for net progress)
        self._prev_bottom_centroid: Optional[np.ndarray] = None
        self._prev_top_centroid: Optional[np.ndarray] = None

        # Stats
        self._total_measurements = 0

        logger.info(
            "SocializationMetrics initialized (dim=%d, K=%d, proj=%d, history=%d)",
            embedding_dim, k_neighbors, projection_dim, max_history,
        )

    # ── Main Entry Point ─────────────────────────────────────────────

    def compute_all(self) -> Dict[str, Any]:
        """Compute all 6 metrics. Called each consolidation cycle.

        Returns dict with metric values for the cycle report.
        """
        now = time.time()
        report: Dict[str, Any] = {}

        try:
            report['semantic_drift'] = self._compute_semantic_drift(now)
        except Exception as e:
            logger.warning("Metric semantic_drift failed: %s", e)
            report['semantic_drift'] = 0.0

        try:
            report['drift_consistency'] = self._compute_drift_consistency(now)
        except Exception as e:
            logger.warning("Metric drift_consistency failed: %s", e)
            report['drift_consistency'] = 0.0

        try:
            report['knn_density'] = self._compute_knn_density(now)
        except Exception as e:
            logger.warning("Metric knn_density failed: %s", e)
            report['knn_density'] = 0.0

        try:
            birth, death = self._compute_concept_turnover(now)
            report['concept_birth_rate'] = birth
            report['concept_death_rate'] = death
        except Exception as e:
            logger.warning("Metric concept_turnover failed: %s", e)
            report['concept_birth_rate'] = 0.0
            report['concept_death_rate'] = 0.0

        try:
            report['influence_delta'] = self._compute_influence_delta(now)
        except Exception as e:
            logger.warning("Metric influence_delta failed: %s", e)
            report['influence_delta'] = 0.0

        try:
            report['net_progress'] = self._compute_net_progress(now)
        except Exception as e:
            logger.warning("Metric net_progress failed: %s", e)
            report['net_progress'] = 0.0

        self._total_measurements += 1
        return report

    # ── Pre-interaction Snapshot ──────────────────────────────────────

    def snapshot_pre_interaction(self) -> None:
        """Capture current centroid BEFORE a user interaction.

        Called from BrainChat.send() before processing a user message.
        The influence delta metric compares this to the post-interaction centroid.
        """
        self._pre_interaction_centroid = self._get_centroid()

    # ── Metric 1: Semantic Drift ─────────────────────────────────────

    def _compute_semantic_drift(self, now: float) -> float:
        """1 - cos(prev_centroid, current_centroid).

        Zero means knowledge is stagnant. Higher means more change.
        """
        centroid = self._get_centroid()
        if centroid is None:
            return 0.0

        drift = 0.0
        if len(self._centroid_history) > 0:
            prev_centroid = self._centroid_history[-1][1]
            drift = self._cosine_distance(prev_centroid, centroid)

            # Store drift vector for consistency metric
            drift_vec = centroid - prev_centroid
            norm = np.linalg.norm(drift_vec)
            if norm > 1e-10:
                self._drift_vectors.append(drift_vec / norm)

        self._centroid_history.append((now, centroid.copy()))
        self._drift_history.append((now, drift))
        return round(drift, 6)

    # ── Metric 2: Drift Direction Consistency ────────────────────────

    def _compute_drift_consistency(self, now: float) -> float:
        """cos(latest_drift_vector, mean_drift_vector).

        High positive = coherent evolution direction.
        Near zero = random wandering.
        Negative = reversing previous learning.
        """
        if len(self._drift_vectors) < 2:
            self._consistency_history.append((now, 0.0))
            return 0.0

        latest = self._drift_vectors[-1]
        # Running mean of all drift vectors (excluding latest)
        mean_drift = np.mean(list(self._drift_vectors)[:-1], axis=0)
        norm = np.linalg.norm(mean_drift)
        if norm < 1e-10:
            self._consistency_history.append((now, 0.0))
            return 0.0

        mean_drift = mean_drift / norm
        consistency = float(np.dot(latest, mean_drift))
        self._consistency_history.append((now, consistency))
        return round(consistency, 6)

    # ── Metric 3: KNN Local Density ──────────────────────────────────

    def _compute_knn_density(self, now: float, sample_n: int = 100) -> float:
        """Average cosine distance to K nearest neighbors.

        Low density (small distances) = clustered/redundant knowledge.
        High density (large distances) = diverse/spread knowledge.

        Uses Gaussian random projection (384→32) for efficiency.
        """
        if not self._moltbook:
            return 0.0

        # Snapshot to avoid RuntimeError from concurrent dict mutation
        entries = [
            e for e in list(self._moltbook._entries.values())
            if e.semantic_embedding is not None
        ]

        if len(entries) < self._k + 1:
            self._density_history.append((now, 0.0))
            return 0.0

        # Sample for efficiency (seeded RNG for reproducibility)
        if len(entries) > sample_n:
            indices = self._rng.choice(len(entries), sample_n, replace=False)
            entries = [entries[i] for i in indices]

        # Stack embeddings and project to lower dimension
        embeddings = np.array([e.semantic_embedding for e in entries], dtype=np.float32)
        projected = embeddings @ self._proj_matrix.T  # (N, 32)

        # L2-normalize projected vectors for cosine distance via dot product
        norms = np.linalg.norm(projected, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        projected = projected / norms

        # Pairwise cosine similarity matrix
        sim_matrix = projected @ projected.T  # (N, N)
        np.fill_diagonal(sim_matrix, -1.0)  # exclude self

        # For each entry, find K nearest neighbors (highest similarity)
        # Distance = 1 - similarity
        k = min(self._k, len(entries) - 1)
        total_distance = 0.0
        for i in range(len(entries)):
            # Get top-K similarities (excluding self)
            top_k_sims = np.partition(sim_matrix[i], -k)[-k:]
            total_distance += np.mean(1.0 - top_k_sims)

        avg_density = total_distance / len(entries)
        self._density_history.append((now, avg_density))
        return round(avg_density, 6)

    # ── Metric 4: Concept Turnover ───────────────────────────────────

    def _compute_concept_turnover(self, now: float) -> Tuple[float, float]:
        """Track birth/death of concepts in the knowledge base.

        Birth rate = fraction of current concepts that are new.
        Death rate = fraction of previous concepts that disappeared.
        """
        current_concepts = self._extract_concepts()

        if not self._prev_concepts:
            # First cycle — no turnover to measure
            self._prev_concepts = current_concepts
            self._birth_rate_history.append((now, 0.0))
            self._death_rate_history.append((now, 0.0))
            return 0.0, 0.0

        if not current_concepts:
            self._birth_rate_history.append((now, 0.0))
            self._death_rate_history.append((now, 0.0))
            return 0.0, 0.0

        births = current_concepts - self._prev_concepts
        deaths = self._prev_concepts - current_concepts

        birth_rate = len(births) / max(len(current_concepts), 1)
        death_rate = len(deaths) / max(len(self._prev_concepts), 1)

        self._prev_concepts = current_concepts
        self._birth_rate_history.append((now, birth_rate))
        self._death_rate_history.append((now, death_rate))

        return round(birth_rate, 6), round(death_rate, 6)

    def _extract_concepts(self, top_unigrams: int = 200, top_bigrams: int = 100) -> Set[str]:
        """Extract key concepts from all entry content.

        Simple tokenization + frequency filtering. No NLP dependency.
        Returns a set of unigram + bigram concept strings.
        """
        if not self._moltbook:
            return set()

        word_counts: Counter = Counter()
        bigram_counts: Counter = Counter()

        for entry in list(self._moltbook._entries.values()):
            words = [
                w.lower() for w in _WORD_RE.findall(entry.content)
                if w.lower() not in STOPWORDS
            ]
            word_counts.update(words)

            # Bigrams from adjacent words
            for i in range(len(words) - 1):
                bigram_counts[f"{words[i]}_{words[i+1]}"] += 1

        # Keep top-N by frequency
        concepts = set()
        for word, _ in word_counts.most_common(top_unigrams):
            concepts.add(word)
        for bigram, _ in bigram_counts.most_common(top_bigrams):
            concepts.add(bigram)

        return concepts

    # ── Metric 5: Interaction Influence Delta ────────────────────────

    def _compute_influence_delta(self, now: float) -> float:
        """Centroid shift caused by user interaction.

        Requires snapshot_pre_interaction() to have been called before
        the interaction. Measures 1 - cos(pre, post).
        """
        if self._pre_interaction_centroid is None:
            self._influence_history.append((now, 0.0))
            return 0.0

        post_centroid = self._get_centroid()
        if post_centroid is None:
            self._pre_interaction_centroid = None
            self._influence_history.append((now, 0.0))
            return 0.0

        delta = self._cosine_distance(self._pre_interaction_centroid, post_centroid)

        # Clear snapshot — one-shot measurement
        self._pre_interaction_centroid = None

        self._influence_history.append((now, delta))
        return round(delta, 6)

    # ── Metric 6: Net Progress ───────────────────────────────────────

    def _compute_net_progress(self, now: float) -> float:
        """Compare drift of bottom-25% vs top-25% entries by confidence.

        Positive = low-quality entries drifting more (being revised).
        Negative = high-quality entries unstable.
        Zero = uniform change (no quality convergence).
        """
        if not self._moltbook:
            return 0.0

        entries = [
            e for e in list(self._moltbook._entries.values())
            if e.semantic_embedding is not None
        ]

        if len(entries) < 8:  # Need at least 2 per quartile
            self._net_progress_history.append((now, 0.0))
            return 0.0

        # Sort by confidence
        entries.sort(key=lambda e: e.confidence)
        q = len(entries) // 4

        bottom = entries[:q]
        top = entries[-q:]

        bottom_centroid = np.mean(
            [e.semantic_embedding for e in bottom], axis=0
        )
        top_centroid = np.mean(
            [e.semantic_embedding for e in top], axis=0
        )

        # Compare to previous quartile centroids
        delta_bottom = 0.0
        delta_top = 0.0

        if self._prev_bottom_centroid is not None:
            delta_bottom = self._cosine_distance(self._prev_bottom_centroid, bottom_centroid)
        if self._prev_top_centroid is not None:
            delta_top = self._cosine_distance(self._prev_top_centroid, top_centroid)

        self._prev_bottom_centroid = bottom_centroid.copy()
        self._prev_top_centroid = top_centroid.copy()

        net_progress = delta_bottom - delta_top
        self._net_progress_history.append((now, net_progress))
        return round(net_progress, 6)

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_centroid(self) -> Optional[np.ndarray]:
        """Compute confidence-weighted mean embedding of all entries.

        Uses confidence as weight so that decay/strengthen phases
        (which change confidence) produce visible centroid shifts
        even when embeddings themselves don't change.
        """
        if not self._moltbook:
            return None

        entries = [
            e for e in list(self._moltbook._entries.values())
            if e.semantic_embedding is not None
        ]

        if not entries:
            return None

        # Confidence-weighted centroid: higher-confidence entries
        # pull the centroid toward them more strongly
        weights = np.array(
            [max(e.confidence, 0.01) for e in entries], dtype=np.float32
        )
        embeddings = np.array(
            [e.semantic_embedding for e in entries], dtype=np.float32
        )
        centroid = np.average(embeddings, axis=0, weights=weights)
        norm = np.linalg.norm(centroid)
        if norm > 1e-10:
            centroid = centroid / norm
        return centroid

    @staticmethod
    def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
        """1 - cosine_similarity(a, b). Range [0, 2]."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        sim = float(np.dot(a, b) / (norm_a * norm_b))
        return 1.0 - sim

    # ── Stats & Time-Series ──────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return current metric values + summary statistics.

        Uses rolling mean of last 10 measurements for display values,
        so transient zeros between data bursts don't dominate the readout.
        """
        def _rolling_mean(history: deque, window: int = 10) -> float:
            if not history:
                return 0.0
            recent = [v for _, v in list(history)[-window:]]
            return float(np.mean(recent))

        def _peak(history: deque, window: int = 20) -> float:
            """Return max value in recent window — useful for burst metrics."""
            if not history:
                return 0.0
            recent = [v for _, v in list(history)[-window:]]
            return float(np.max(recent))

        def _trend(history: deque, window: int = 10) -> str:
            """Classify recent trend as increasing/decreasing/stable."""
            if len(history) < window:
                return 'insufficient_data'
            recent = [v for _, v in list(history)[-window:]]
            first_half = np.mean(recent[:window // 2])
            second_half = np.mean(recent[window // 2:])
            diff = second_half - first_half
            if abs(diff) < 0.001:
                return 'stable'
            return 'increasing' if diff > 0 else 'decreasing'

        return {
            'total_measurements': self._total_measurements,
            'semantic_drift': _rolling_mean(self._drift_history),
            'drift_consistency': _rolling_mean(self._consistency_history),
            'knn_density': _rolling_mean(self._density_history),
            'concept_birth_rate': _rolling_mean(self._birth_rate_history),
            'concept_death_rate': _rolling_mean(self._death_rate_history),
            'influence_delta': _rolling_mean(self._influence_history),
            'net_progress': _rolling_mean(self._net_progress_history),
            'peaks': {
                'semantic_drift': _peak(self._drift_history),
                'concept_birth_rate': _peak(self._birth_rate_history),
                'influence_delta': _peak(self._influence_history),
            },
            'trends': {
                'semantic_drift': _trend(self._drift_history),
                'knn_density': _trend(self._density_history),
                'concept_birth_rate': _trend(self._birth_rate_history),
                'net_progress': _trend(self._net_progress_history),
            },
            'history_size': len(self._drift_history),
        }

    def get_time_series(self, metric: Optional[str] = None) -> Dict[str, Any]:
        """Return time-series data for charting.

        Args:
            metric: Optional single metric name. If None, returns all.

        Returns:
            Dict of {metric_name: [[timestamp, value], ...]}
        """
        series_map = {
            'semantic_drift': self._drift_history,
            'drift_consistency': self._consistency_history,
            'knn_density': self._density_history,
            'concept_birth_rate': self._birth_rate_history,
            'concept_death_rate': self._death_rate_history,
            'influence_delta': self._influence_history,
            'net_progress': self._net_progress_history,
        }

        if metric and metric in series_map:
            return {
                metric: [[t, float(round(v, 6))] for t, v in series_map[metric]]
            }

        return {
            name: [[t, float(round(v, 6))] for t, v in history]
            for name, history in series_map.items()
        }
