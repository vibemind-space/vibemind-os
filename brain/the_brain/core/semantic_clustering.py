"""
Semantic Clustering — Groups ideas by embedding similarity using DBSCAN.

Uses numpy for cosine distance and a simple DBSCAN implementation
to avoid requiring scikit-learn as a dependency.
"""

import logging
import numpy as np
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Stop words for label generation (DE + EN)
_STOP_WORDS = frozenset({
    "der", "die", "das", "und", "in", "von", "mit", "für", "ein", "eine",
    "auf", "ist", "im", "den", "dem", "des", "zu", "nicht", "sich", "aus",
    "the", "a", "an", "and", "is", "for", "to", "of", "in", "on", "at",
    "by", "with", "from", "or", "as", "it", "be", "are", "was", "has",
})


@dataclass
class SemanticCluster:
    cluster_id: int
    label: str
    ideas: List[Dict[str, Any]]
    coherence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "ideas": [
                {"id": i.get("id", ""), "title": i.get("title", ""), "bubble": i.get("bubble_title", "")}
                for i in self.ideas
            ],
            "size": len(self.ideas),
            "coherence": round(self.coherence, 3),
        }


def _cosine_distance_matrix(vectors: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine distance matrix."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    normalized = vectors / norms
    sim = np.dot(normalized, normalized.T)
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    return np.clip(dist, 0.0, 2.0)


def _dbscan(distance_matrix: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    """Simple DBSCAN on a precomputed distance matrix. Returns label array (-1 = noise)."""
    n = distance_matrix.shape[0]
    labels = np.full(n, -1, dtype=int)
    visited = np.zeros(n, dtype=bool)
    cluster_id = 0

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True

        neighbors = np.where(distance_matrix[i] <= eps)[0]
        if len(neighbors) < min_samples:
            continue  # noise

        labels[i] = cluster_id
        seed_set = list(neighbors)
        j = 0
        while j < len(seed_set):
            q = seed_set[j]
            if not visited[q]:
                visited[q] = True
                q_neighbors = np.where(distance_matrix[q] <= eps)[0]
                if len(q_neighbors) >= min_samples:
                    seed_set.extend(q_neighbors.tolist())
            if labels[q] == -1:
                labels[q] = cluster_id
            j += 1

        cluster_id += 1

    return labels


def _generate_label(members: List[Dict[str, Any]]) -> str:
    """Auto-generate a cluster label from the most common title words."""
    words = []
    for m in members:
        for w in m.get("title", "").split():
            w_clean = w.strip(".,;:!?()[]{}\"'").lower()
            if len(w_clean) > 2 and w_clean not in _STOP_WORDS:
                words.append(w_clean)
    if not words:
        return "Cluster"
    common = Counter(words).most_common(3)
    return " / ".join(w.title() for w, _ in common)


def _compute_coherence(vectors: np.ndarray) -> float:
    """Average pairwise cosine similarity within a cluster."""
    if len(vectors) < 2:
        return 1.0
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    normalized = vectors / norms
    sim = np.dot(normalized, normalized.T)
    n = len(vectors)
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += sim[i, j]
            count += 1
    return total / count if count > 0 else 0.0


def embed_texts(texts: List[str]) -> Optional[np.ndarray]:
    """Embed texts using sentence-transformers if available, else return None."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return embeddings
    except ImportError:
        logger.warning("[Clustering] sentence-transformers not available, trying fallback")
    except Exception as e:
        logger.error(f"[Clustering] Embedding failed: {e}")

    # Fallback: simple hash-based pseudo-embeddings (low quality but functional)
    import hashlib
    dim = 64
    result = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        h = hashlib.sha256(text.encode("utf-8")).digest()
        for j in range(dim):
            result[i, j] = (h[j % len(h)] - 128) / 128.0
    return result


def cluster_ideas(
    ideas: List[Dict[str, Any]],
    eps: float = 0.5,
    min_samples: int = 2,
) -> List[SemanticCluster]:
    """Cluster ideas by semantic similarity.

    Args:
        ideas: List of dicts with at least 'id', 'title', and optionally 'content', 'bubble_title'.
        eps: DBSCAN distance threshold (0-1, lower = tighter clusters).
        min_samples: Minimum cluster size.

    Returns:
        List of SemanticCluster sorted by size descending.
    """
    if len(ideas) < min_samples:
        return []

    # Build text for embedding: title + first 200 chars of content
    texts = []
    for idea in ideas:
        title = idea.get("title", "")
        content = idea.get("content", "")[:200]
        texts.append(f"{title}. {content}" if content else title)

    vectors = embed_texts(texts)
    if vectors is None:
        return []

    distance_matrix = _cosine_distance_matrix(vectors)
    labels = _dbscan(distance_matrix, eps=eps, min_samples=min_samples)

    # Group by cluster
    cluster_map: Dict[int, List[Tuple[int, Dict]]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        if label not in cluster_map:
            cluster_map[label] = []
        cluster_map[label].append((idx, ideas[idx]))

    clusters = []
    for cid, members_with_idx in cluster_map.items():
        indices = [m[0] for m in members_with_idx]
        member_ideas = [m[1] for m in members_with_idx]
        member_vecs = vectors[indices]

        clusters.append(SemanticCluster(
            cluster_id=int(cid),
            label=_generate_label(member_ideas),
            ideas=member_ideas,
            coherence=float(_compute_coherence(member_vecs)),
        ))

    clusters.sort(key=lambda c: len(c.ideas), reverse=True)

    logger.info(
        f"[Clustering] {len(clusters)} clusters from {len(ideas)} ideas "
        f"(eps={eps}, min_samples={min_samples})"
    )
    return clusters
