"""
SeedEncoder — Convert task context into 384-dim thalamic seed embedding.

Takes structured task features (routing weights, complexity, urgency, task type,
processing mode) and produces a dense 384-dimensional numpy vector suitable for
RadialAttentionNetwork's thalamic encoder.

Uses a deterministic random projection (fixed seed) so identical task contexts
always produce identical seed embeddings.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Task type vocabulary (matches TaskFeatureRouter)
TASK_TYPES = [
    'memory', 'docker', 'github', 'search', 'file_ops',
    'analysis', 'testing', 'refactor', 'question',
    'knowledge', 'conversation', 'unknown',
]

# Processing mode vocabulary (matches TaskFeatureRouter)
PROCESSING_MODES = ['urgent', 'analytical', 'creative', 'routine']


@dataclass
class TaskContext:
    """Structured task context for seed encoding."""
    routing_weights: np.ndarray    # shape (10,) — modality gate values
    complexity: float = 0.5        # 0-1
    urgency: float = 0.5           # 0-1
    task_type: str = 'unknown'     # one of TASK_TYPES
    processing_mode: str = 'routine'  # one of PROCESSING_MODES
    keywords: Optional[List[str]] = None
    raw_description: str = ''


class SeedEncoder:
    """Encode task context into a 384-dim seed for RadialAttentionNetwork.

    Architecture:
        1. Build feature vector from task context (28 + 16 keyword dims = 44)
        2. Project via fixed random matrix to 384D
        3. L2-normalize for stable thalamic encoding

    The projection matrix is deterministic (numpy seed=42) so identical
    inputs always produce identical outputs.
    """

    FEATURE_DIM = 44   # 10 routing + 2 scalar + 12 type + 4 mode + 16 keyword
    SEED_DIM = 384

    def __init__(self, seed_dim: int = 384, rng_seed: int = 42):
        self.seed_dim = seed_dim
        # Fixed random projection: feature_dim -> seed_dim
        rng = np.random.RandomState(rng_seed)
        self._projection = rng.randn(self.FEATURE_DIM, seed_dim).astype(np.float32)
        # Xavier-like scaling
        self._projection *= np.sqrt(2.0 / (self.FEATURE_DIM + seed_dim))
        logger.info(f"SeedEncoder initialized: {self.FEATURE_DIM}D -> {seed_dim}D")

    def encode(self, ctx: TaskContext) -> np.ndarray:
        """Encode a TaskContext into a seed embedding.

        Args:
            ctx: Structured task context.

        Returns:
            np.ndarray of shape (1, seed_dim) — batch dimension included.
        """
        features = self._build_features(ctx)
        # Project to seed_dim
        seed = features @ self._projection  # (seed_dim,)
        # L2 normalize for stable thalamic encoding
        norm = np.linalg.norm(seed)
        if norm > 1e-8:
            seed = seed / norm
        return seed.reshape(1, self.seed_dim)

    def encode_from_description(self, description: str,
                                routing_weights: Optional[np.ndarray] = None) -> np.ndarray:
        """Convenience: encode from raw description with optional routing weights.

        If routing_weights not provided, uses uniform distribution.
        """
        if routing_weights is None:
            routing_weights = np.ones(10, dtype=np.float32) / 10.0

        ctx = TaskContext(
            routing_weights=routing_weights,
            complexity=min(1.0, len(description) / 500.0),
            urgency=0.5,
            task_type=self._infer_task_type(description),
            processing_mode='routine',
            raw_description=description,
        )
        return self.encode(ctx)

    def _build_features(self, ctx: TaskContext) -> np.ndarray:
        """Build flat feature vector from task context."""
        parts = []

        # 1. Routing weights (10D)
        rw = np.asarray(ctx.routing_weights, dtype=np.float32).ravel()
        if len(rw) < 10:
            rw = np.pad(rw, (0, 10 - len(rw)))
        parts.append(rw[:10])

        # 2. Scalar features (2D)
        parts.append(np.array([ctx.complexity, ctx.urgency], dtype=np.float32))

        # 3. Task type one-hot (12D)
        type_vec = np.zeros(len(TASK_TYPES), dtype=np.float32)
        if ctx.task_type in TASK_TYPES:
            type_vec[TASK_TYPES.index(ctx.task_type)] = 1.0
        else:
            type_vec[-1] = 1.0  # 'unknown'
        parts.append(type_vec)

        # 4. Processing mode one-hot (4D)
        mode_vec = np.zeros(len(PROCESSING_MODES), dtype=np.float32)
        if ctx.processing_mode in PROCESSING_MODES:
            mode_vec[PROCESSING_MODES.index(ctx.processing_mode)] = 1.0
        else:
            mode_vec[-1] = 1.0  # 'routine'
        parts.append(mode_vec)

        # 5. Keyword hash embedding (16D)
        kw_vec = np.zeros(16, dtype=np.float32)
        if ctx.keywords:
            for kw in ctx.keywords[:10]:
                h = int(hashlib.md5(kw.encode()).hexdigest(), 16)
                idx = h % 16
                kw_vec[idx] += 0.3
        elif ctx.raw_description:
            # Fallback: hash words from description
            words = ctx.raw_description.lower().split()[:10]
            for w in words:
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                idx = h % 16
                kw_vec[idx] += 0.2
        parts.append(kw_vec)

        return np.concatenate(parts)  # shape (44,)

    @staticmethod
    def _infer_task_type(description: str) -> str:
        """Simple heuristic task type inference from description."""
        desc_lower = description.lower()
        for task_type, keywords in _TYPE_KEYWORDS.items():
            if any(k in desc_lower for k in keywords):
                return task_type
        return 'unknown'


_TYPE_KEYWORDS = {
    'memory': ['memory', 'remember', 'recall', 'episodic'],
    'docker': ['docker', 'container', 'image', 'compose'],
    'github': ['github', 'git', 'commit', 'pull request', 'branch'],
    'search': ['search', 'find', 'look up', 'query'],
    'file_ops': ['file', 'directory', 'folder', 'move', 'copy', 'delete'],
    'analysis': ['analyze', 'analysis', 'examine', 'investigate'],
    'testing': ['test', 'assert', 'pytest', 'unittest'],
    'refactor': ['refactor', 'clean up', 'restructure', 'reorganize'],
    'question': ['what', 'why', 'how', 'explain', 'describe'],
    'knowledge': ['learn', 'knowledge', 'understand', 'concept'],
    'conversation': ['chat', 'talk', 'discuss', 'conversation'],
}
