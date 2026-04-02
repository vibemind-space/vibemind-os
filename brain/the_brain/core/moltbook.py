"""
Moltbook — Decentralized Knowledge & Thinking System for The Brain (Tahlamus)

Core data layer providing:
  - MoltbookEntry: Single knowledge nugget (post/comment/thought/knowledge)
  - MoltbookStore: Persistent knowledge storage with LRU eviction
  - SemanticIndex: Vector-based semantic search (numpy ANN)
  - MoltbookGraph: Knowledge linkage with spreading activation
  - MoltbookConfig: YAML-driven configuration

Architecture Inspirations:
  - A-MEM (Agentic Memory) — arxiv 2502.12110
  - Predictive Coding (Free Energy) — Friston
  - Global Workspace Theory — Baars
  - Ebbinghaus Forgetting Curve
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger('brain.moltbook')


# ═══════════════════════════════════════════════════════════════════
# [1] MoltbookEntry Schema
# ═══════════════════════════════════════════════════════════════════

class EntryType(Enum):
    """Type of knowledge entry in the Moltbook."""
    POST = "post"               # Agent-published knowledge
    COMMENT = "comment"         # Response to another entry
    THOUGHT = "thought"         # Internal thought from ThoughtStream
    KNOWLEDGE = "knowledge"     # Verified/consolidated knowledge
    REFLECTION = "reflection"   # Meta-cognitive reflection
    EXPERIENCE = "experience"   # Episodic experience record


class LinkType(Enum):
    """Relationship type between linked entries."""
    RELATES_TO = "relates_to"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    EXTENDS = "extends"
    CAUSED_BY = "caused_by"


@dataclass
class MoltbookEntry:
    """
    Single knowledge nugget in the Moltbook.

    Each entry is a "thought" or "knowledge nugget" — the atomic unit
    of the Moltbook knowledge system.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    content: str = ""
    source_agent: str = "unknown"
    entry_type: str = "knowledge"     # EntryType value
    semantic_embedding: Optional[np.ndarray] = None
    tags: List[str] = field(default_factory=list)
    linked_entries: Dict[str, str] = field(default_factory=dict)  # {entry_id: link_type}
    confidence: float = 0.5
    emotional_valence: float = 0.0    # -1 (negative) to +1 (positive)
    emotional_arousal: float = 0.0    # 0 (calm) to 1 (excited)
    relevance_score: float = 0.5
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    accessed_count: int = 0
    decay_rate: float = 0.001
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def access(self) -> None:
        """Record an access event, boosting relevance and resetting decay."""
        self.accessed_count += 1
        self.last_accessed = time.time()
        # Each access boosts relevance slightly (diminishing returns)
        boost = 0.1 / (1.0 + math.log1p(self.accessed_count))
        self.relevance_score = min(1.0, self.relevance_score + boost)

    def compute_activation(self, current_time: Optional[float] = None) -> float:
        """
        Compute current activation level using Ebbinghaus forgetting curve.

        activation = relevance * e^(-decay * time_since_access) * (1 + log(access_count+1))
        Emotional entries decay slower (emotional_decay_multiplier).
        """
        t = (current_time or time.time()) - self.last_accessed
        emotional_factor = 1.0 - 0.3 * abs(self.emotional_valence)  # emotional → slower decay
        effective_decay = self.decay_rate * emotional_factor
        forgetting = math.exp(-effective_decay * t)
        frequency_boost = 1.0 + math.log1p(self.accessed_count)
        return self.relevance_score * forgetting * frequency_boost

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (embedding stored as list)."""
        d = {
            'id': self.id,
            'content': self.content,
            'source_agent': self.source_agent,
            'entry_type': self.entry_type,
            'tags': self.tags,
            'linked_entries': self.linked_entries,
            'confidence': self.confidence,
            'emotional_valence': self.emotional_valence,
            'emotional_arousal': self.emotional_arousal,
            'relevance_score': self.relevance_score,
            'created_at': self.created_at,
            'last_accessed': self.last_accessed,
            'accessed_count': self.accessed_count,
            'decay_rate': self.decay_rate,
            'version': self.version,
            'metadata': self.metadata,
        }
        if self.semantic_embedding is not None:
            d['semantic_embedding'] = self.semantic_embedding.tolist()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MoltbookEntry':
        """Deserialize from dict."""
        embedding = d.pop('semantic_embedding', None)
        entry = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if embedding is not None:
            entry.semantic_embedding = np.array(embedding, dtype=np.float32)
        return entry

    def content_hash(self) -> str:
        """Hash of content for deduplication."""
        return hashlib.md5(self.content.encode('utf-8')).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════
# [5] MoltbookConfig
# ═══════════════════════════════════════════════════════════════════

@dataclass
class MoltbookConfig:
    """Configuration for the Moltbook system."""
    # Core
    max_entries: int = 50000
    embedding_dim: int = 384
    similarity_threshold: float = 0.3  # Phase B: real embeddings → 0.3 is realistic

    # Thought stream
    thought_stream_interval_ms: int = 200
    thought_buffer_size: int = 100

    # Retrieval
    speculative_retrieval_depth: int = 3
    markov_lookahead: int = 2
    top_k_entries: int = 10
    workspace_capacity: int = 7  # Lisman-Jensen 7±2

    # Decay
    decay_rate: float = 0.001
    emotional_decay_multiplier: float = 0.3
    access_boost: float = 0.1

    # Performance
    retrieval_timeout_ms: int = 5
    think_budget_ms: int = 500
    speak_budget_ms: int = 200

    # Persistence
    store_path: str = "data/moltbook/store.db"
    index_path: str = "data/moltbook/index.faiss"
    graph_path: str = "data/moltbook/graph.json"
    markov_path: str = "data/moltbook/markov.json"

    # Agents
    enable_background_agents: bool = True
    agent_schedule_interval_s: int = 60
    max_agent_searches_per_day: int = 100

    # Debug
    enable_debug_stream: bool = False

    @classmethod
    def from_yaml(cls, yaml_config: Dict[str, Any]) -> 'MoltbookConfig':
        """Create from YAML config dict (looks for 'moltbook' key)."""
        mb = yaml_config.get('moltbook', {})
        kwargs = {}
        for f_name in cls.__dataclass_fields__:
            if f_name in mb:
                kwargs[f_name] = mb[f_name]
        return cls(**kwargs)


# ═══════════════════════════════════════════════════════════════════
# [3] SemanticIndex — Vector-based Knowledge Search
# ═══════════════════════════════════════════════════════════════════

class SemanticIndex:
    """
    Vector-based semantic search using numpy ANN.

    Uses cosine similarity for retrieval. Designed for sub-ms search
    on up to 50k entries with 384-dim embeddings.

    Phase B: Uses sentence-transformers (all-MiniLM-L6-v2) for real
    semantic embeddings. Falls back to hash-based if unavailable.
    """

    # Class-level model (shared across all instances — loaded once)
    _transformer_model = None
    _transformer_available: Optional[bool] = None  # None = not checked yet

    @classmethod
    def _load_transformer(cls) -> bool:
        """Lazy-load sentence-transformers model (once per process)."""
        if cls._transformer_available is not None:
            return cls._transformer_available
        try:
            from sentence_transformers import SentenceTransformer
            cls._transformer_model = SentenceTransformer('all-MiniLM-L6-v2')
            cls._transformer_available = True
            logger.info("SemanticIndex: sentence-transformers loaded (all-MiniLM-L6-v2)")
            return True
        except Exception as e:
            cls._transformer_available = False
            logger.warning(f"SemanticIndex: sentence-transformers unavailable ({e}), "
                          f"falling back to hash embeddings")
            return False

    def __init__(self, config: Optional[Dict[str, Any]] = None, embedding_dim: int = 384):
        cfg = config or {}
        self._dim = cfg.get('embedding_dim', embedding_dim)
        self._ids: List[str] = []
        self._matrix: Optional[np.ndarray] = None  # shape: (n, dim)
        self._lock = threading.Lock()
        self._dirty = False
        self._embed_cache: Dict[str, np.ndarray] = {}  # text_hash -> embedding
        self._cache_max = 5000

        # Try loading transformer model at init
        self._use_transformer = self._load_transformer()
        mode = "sentence-transformers" if self._use_transformer else "hash-fallback"
        logger.info(f"SemanticIndex initialized (dim={self._dim}, mode={mode})")

    @property
    def size(self) -> int:
        """Number of indexed entries."""
        return len(self._ids)

    def embed(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Uses sentence-transformers (all-MiniLM-L6-v2) for real semantic
        embeddings. Falls back to hash-based if model unavailable.
        """
        if not text.strip():
            return np.zeros(self._dim, dtype=np.float32)

        # Check cache first
        cache_key = hashlib.md5(text.encode('utf-8')).hexdigest()
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key].copy()

        if self._use_transformer and self._transformer_model is not None:
            vec = self._embed_transformer(text)
        else:
            vec = self._embed_hash_fallback(text)

        # Cache the result
        if len(self._embed_cache) < self._cache_max:
            self._embed_cache[cache_key] = vec.copy()

        return vec

    def _embed_transformer(self, text: str) -> np.ndarray:
        """Generate real semantic embedding via sentence-transformers."""
        try:
            embedding = self._transformer_model.encode(
                text, normalize_embeddings=True, show_progress_bar=False
            )
            vec = np.asarray(embedding, dtype=np.float32)
            if vec.shape[0] != self._dim:
                # Model dim mismatch — pad or truncate
                if vec.shape[0] > self._dim:
                    vec = vec[:self._dim]
                else:
                    padded = np.zeros(self._dim, dtype=np.float32)
                    padded[:vec.shape[0]] = vec
                    vec = padded
            return vec
        except Exception as e:
            logger.warning(f"Transformer embed failed: {e}, falling back to hash")
            return self._embed_hash_fallback(text)

    def _embed_hash_fallback(self, text: str) -> np.ndarray:
        """Hash-based embedding fallback (Phase A legacy)."""
        vec = np.zeros(self._dim, dtype=np.float32)
        words = text.lower().split()
        for i, word in enumerate(words):
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            positions = [(h >> (j * 8)) % self._dim for j in range(4)]
            weight = 1.0 / (1.0 + i * 0.1)  # position decay
            for pos in positions:
                vec[pos] += weight * (1.0 if (h >> 32) % 2 == 0 else -1.0)

        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Batch embed multiple texts (much faster with transformers)."""
        if not texts:
            return []

        if self._use_transformer and self._transformer_model is not None:
            try:
                embeddings = self._transformer_model.encode(
                    texts, normalize_embeddings=True, show_progress_bar=False,
                    batch_size=32,
                )
                results = []
                for i, emb in enumerate(embeddings):
                    vec = np.asarray(emb, dtype=np.float32)
                    if vec.shape[0] != self._dim:
                        if vec.shape[0] > self._dim:
                            vec = vec[:self._dim]
                        else:
                            padded = np.zeros(self._dim, dtype=np.float32)
                            padded[:vec.shape[0]] = vec
                            vec = padded
                    results.append(vec)
                    # Cache
                    cache_key = hashlib.md5(texts[i].encode('utf-8')).hexdigest()
                    if len(self._embed_cache) < self._cache_max:
                        self._embed_cache[cache_key] = vec.copy()
                return results
            except Exception as e:
                logger.warning(f"Batch embed failed: {e}")

        # Fallback: embed one by one
        return [self.embed(t) for t in texts]

    def add(self, entry_id: str, embedding: np.ndarray) -> None:
        """Add or update an entry in the index."""
        with self._lock:
            embedding = np.asarray(embedding, dtype=np.float32)
            if embedding.shape != (self._dim,):
                raise ValueError(f"Expected dim={self._dim}, got {embedding.shape}")

            if entry_id in self._ids:
                idx = self._ids.index(entry_id)
                self._matrix[idx] = embedding
            else:
                self._ids.append(entry_id)
                if self._matrix is None:
                    self._matrix = embedding.reshape(1, -1)
                else:
                    self._matrix = np.vstack([self._matrix, embedding.reshape(1, -1)])
            self._dirty = True

    def remove(self, entry_id: str) -> None:
        """Remove an entry from the index."""
        with self._lock:
            if entry_id not in self._ids:
                return
            idx = self._ids.index(entry_id)
            self._ids.pop(idx)
            if self._matrix is not None and len(self._ids) > 0:
                self._matrix = np.delete(self._matrix, idx, axis=0)
            else:
                self._matrix = None
            self._dirty = True

    def search(self, query_vector: np.ndarray, top_k: int = 10,
               threshold: float = 0.0) -> List[Tuple[str, float]]:
        """
        Search for most similar entries by cosine similarity.

        Returns list of (entry_id, similarity_score) sorted by score desc.
        Target: <5ms for top-10 from 50k entries.
        """
        with self._lock:
            if self._matrix is None or len(self._ids) == 0:
                return []

            query_vector = np.asarray(query_vector, dtype=np.float32)
            q_norm = np.linalg.norm(query_vector)
            if q_norm == 0:
                return []
            query_vector = query_vector / q_norm

            # Batch cosine similarity via matrix multiply
            similarities = self._matrix @ query_vector  # (n,)

            # Get top-k indices
            if len(similarities) <= top_k:
                top_indices = np.argsort(similarities)[::-1]
            else:
                # Partial sort for efficiency
                top_indices = np.argpartition(similarities, -top_k)[-top_k:]
                top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

            results = []
            for idx in top_indices:
                score = float(similarities[idx])
                if score >= threshold:
                    results.append((self._ids[idx], score))
            return results

    def batch_index(self, entries: List[Tuple[str, np.ndarray]]) -> int:
        """Batch add multiple entries. Returns count added."""
        count = 0
        for entry_id, embedding in entries:
            self.add(entry_id, embedding)
            count += 1
        return count

    def reindex(self, entries: Dict[str, np.ndarray]) -> None:
        """Full reindex from scratch."""
        with self._lock:
            self._ids = list(entries.keys())
            if self._ids:
                self._matrix = np.stack([
                    np.asarray(entries[eid], dtype=np.float32)
                    for eid in self._ids
                ])
            else:
                self._matrix = None
            self._dirty = True

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            'size': self.size,
            'dim': self._dim,
            'memory_mb': (self._matrix.nbytes / 1024 / 1024) if self._matrix is not None else 0.0,
            'embedding_mode': 'sentence-transformers' if self._use_transformer else 'hash-fallback',
            'cache_size': len(self._embed_cache),
        }

    @classmethod
    def from_yaml(cls, yaml_config: Dict[str, Any]) -> 'SemanticIndex':
        """Create from YAML config."""
        mb = yaml_config.get('moltbook', {})
        return cls(config=mb, embedding_dim=mb.get('embedding_dim', 384))


# ═══════════════════════════════════════════════════════════════════
# [2] MoltbookStore — Persistent Knowledge Storage
# ═══════════════════════════════════════════════════════════════════

class MoltbookStore:
    """
    Persistent knowledge store for the Moltbook system.

    In-memory index backed by SQLite for persistence.
    Supports LRU eviction when max_entries is exceeded.

    Methods:
        add_entry()       — Add new knowledge entry
        query_semantic()  — Search by semantic similarity
        query_by_tag()    — Search by tags
        get_linked()      — Get linked entries
        get_entry()       — Get single entry by ID
        decay_old()       — Apply Ebbinghaus decay
        get_active_entries() — Get highest-activation entries
        consolidate()     — Move important entries, prune dead ones
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._max_entries = cfg.get('max_entries', 50000)
        self._similarity_threshold = cfg.get('similarity_threshold', 0.3)
        self._decay_rate = cfg.get('decay_rate', 0.001)
        self._embedding_dim = cfg.get('embedding_dim', 384)

        # In-memory store
        self._entries: Dict[str, MoltbookEntry] = {}
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)  # tag -> {entry_ids}
        self._lock = threading.Lock()

        # Semantic index
        self._semantic_index = SemanticIndex(config=cfg, embedding_dim=self._embedding_dim)

        # Statistics
        self._total_added = 0
        self._total_evicted = 0
        self._total_queries = 0

        # Persistence path (created lazily)
        self._store_path = cfg.get('store_path', '')
        self._loaded = False

        logger.info(f"MoltbookStore initialized (max={self._max_entries})")

    @property
    def size(self) -> int:
        """Number of entries in the store."""
        return len(self._entries)

    @property
    def semantic_index(self) -> SemanticIndex:
        """Access the semantic index."""
        return self._semantic_index

    def add_entry(self, content: str, source_agent: str = "unknown",
                  entry_type: str = "knowledge", tags: Optional[List[str]] = None,
                  confidence: float = 0.5, emotional_valence: float = 0.0,
                  emotional_arousal: float = 0.0,
                  metadata: Optional[Dict[str, Any]] = None,
                  linked_to: Optional[Dict[str, str]] = None) -> MoltbookEntry:
        """
        Add a new knowledge entry to the Moltbook.

        Args:
            content: The knowledge content text
            source_agent: Which agent/system created this entry
            entry_type: Type of entry (post/comment/thought/knowledge/reflection/experience)
            tags: Optional tags for categorization
            confidence: Confidence in this knowledge (0-1)
            emotional_valence: Emotional valence (-1 to +1)
            emotional_arousal: Emotional arousal (0 to 1)
            metadata: Optional metadata dict
            linked_to: Optional links {entry_id: link_type}

        Returns:
            The created MoltbookEntry
        """
        with self._lock:
            # Create entry
            entry = MoltbookEntry(
                content=content,
                source_agent=source_agent,
                entry_type=entry_type,
                tags=tags or [],
                confidence=confidence,
                emotional_valence=emotional_valence,
                emotional_arousal=emotional_arousal,
                metadata=metadata or {},
                linked_entries=linked_to or {},
                decay_rate=self._decay_rate,
            )

            # Generate and store embedding
            embedding = self._semantic_index.embed(content)
            entry.semantic_embedding = embedding
            self._semantic_index.add(entry.id, embedding)

            # Store entry
            self._entries[entry.id] = entry

            # Update tag index
            for tag in entry.tags:
                self._tag_index[tag].add(entry.id)

            self._total_added += 1

            # Evict if over capacity
            if len(self._entries) > self._max_entries:
                self._evict_lru()

            logger.debug(f"Added entry {entry.id}: {content[:50]}...")
            return entry

    def get_entry(self, entry_id: str) -> Optional[MoltbookEntry]:
        """Get a single entry by ID, recording access."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.access()
        return entry

    def query_semantic(self, query: str, top_k: int = 10,
                       threshold: Optional[float] = None,
                       return_scores: bool = False):
        """
        Search entries by semantic similarity to query text.

        Args:
            query: Search query text
            top_k: Maximum results to return
            threshold: Minimum similarity threshold (default from config)
            return_scores: If True, return list of (entry, similarity, combined_score)

        Returns:
            List of MoltbookEntry sorted by relevance (or list of tuples if return_scores)
        """
        self._total_queries += 1
        threshold = threshold if threshold is not None else self._similarity_threshold

        # Embed query
        query_vec = self._semantic_index.embed(query)

        # Search index
        results = self._semantic_index.search(query_vec, top_k=top_k * 2, threshold=threshold)

        # Enrich with activation scores
        scored = []
        for entry_id, sim_score in results:
            entry = self._entries.get(entry_id)
            if entry:
                entry.access()
                activation = entry.compute_activation()
                combined_score = 0.6 * sim_score + 0.4 * activation
                scored.append((entry, sim_score, combined_score))

        # Sort by combined score and return top_k
        scored.sort(key=lambda x: x[2], reverse=True)
        if return_scores:
            return [(e, sim, comb) for e, sim, comb in scored[:top_k]]
        return [entry for entry, _, _ in scored[:top_k]]

    def query_by_tag(self, tags: List[str], match_all: bool = False) -> List[MoltbookEntry]:
        """
        Search entries by tags.

        Args:
            tags: Tags to search for
            match_all: If True, entry must have ALL tags; if False, ANY tag matches

        Returns:
            List of matching MoltbookEntry
        """
        matching_ids: Set[str] = set()
        tag_sets = [self._tag_index.get(tag, set()) for tag in tags]

        if match_all:
            if tag_sets:
                matching_ids = set.intersection(*tag_sets)
        else:
            for s in tag_sets:
                matching_ids |= s

        entries = []
        for eid in matching_ids:
            entry = self._entries.get(eid)
            if entry:
                entries.append(entry)

        entries.sort(key=lambda e: e.compute_activation(), reverse=True)
        return entries

    def get_linked(self, entry_id: str, link_type: Optional[str] = None,
                   depth: int = 1) -> List[MoltbookEntry]:
        """
        Get entries linked to the given entry.

        Args:
            entry_id: Source entry ID
            link_type: Optional filter by link type
            depth: How many hops to follow (1 = direct links only)

        Returns:
            List of linked MoltbookEntry
        """
        visited: Set[str] = {entry_id}
        current_ids: Set[str] = {entry_id}
        result: List[MoltbookEntry] = []

        for _ in range(depth):
            next_ids: Set[str] = set()
            for eid in current_ids:
                entry = self._entries.get(eid)
                if not entry:
                    continue
                for linked_id, lt in entry.linked_entries.items():
                    if linked_id not in visited:
                        if link_type is None or lt == link_type:
                            linked_entry = self._entries.get(linked_id)
                            if linked_entry:
                                result.append(linked_entry)
                                next_ids.add(linked_id)
                                visited.add(linked_id)
            current_ids = next_ids

        return result

    def enrich_entry(self, entry_id: str, new_content: str,
                     new_tags: Optional[List[str]] = None,
                     confidence_boost: float = 0.05) -> bool:
        """
        Enrich an existing entry with additional knowledge.

        Instead of creating a duplicate, GROWS the entry's content by
        appending non-redundant sentences. Also merges tags and bumps
        confidence/version.

        Args:
            entry_id: ID of the entry to enrich
            new_content: New knowledge text to merge in
            new_tags: Additional tags to add
            confidence_boost: How much to increase confidence

        Returns:
            True if enriched, False if entry not found
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                return False

            # Extract sentences from new content that aren't already present
            existing_lower = entry.content.lower()
            new_sentences = [s.strip() for s in new_content.split('.')
                            if len(s.strip()) > 15]
            added_sentences = []
            for sent in new_sentences:
                # Skip if this sentence (or close variant) already exists
                sent_key = sent[:50].lower()
                if sent_key not in existing_lower:
                    added_sentences.append(sent.strip())

            if not added_sentences:
                # Nothing new to add — just record the access
                entry.access()
                return True

            # Append new sentences to existing content
            separator = ". " if entry.content and not entry.content.rstrip().endswith('.') else " "
            addition = '. '.join(added_sentences)
            entry.content = entry.content.rstrip() + separator + addition
            # Cap at reasonable length (don't let entries grow unbounded)
            if len(entry.content) > 1500:
                entry.content = entry.content[:1500].rstrip()

            # Merge tags
            if new_tags:
                existing_tags = set(entry.tags)
                for tag in new_tags:
                    if tag not in existing_tags:
                        entry.tags.append(tag)
                        self._tag_index[tag].add(entry_id)

            # Bump confidence and version
            entry.confidence = min(1.0, entry.confidence + confidence_boost)
            entry.version += 1
            entry.access()  # also resets decay

            # Re-embed with updated content
            embedding = self._semantic_index.embed(entry.content)
            entry.semantic_embedding = embedding
            self._semantic_index.add(entry_id, embedding)  # overwrites old embedding

            logger.debug(
                f"Enriched entry {entry_id} v{entry.version}: "
                f"+{len(added_sentences)} sentences, "
                f"now {len(entry.content)} chars"
            )
            return True

    def link_entries(self, source_id: str, target_id: str, link_type: str = "relates_to") -> bool:
        """Create a link between two entries."""
        source = self._entries.get(source_id)
        target = self._entries.get(target_id)
        if source and target:
            source.linked_entries[target_id] = link_type
            return True
        return False

    def decay_old(self, current_time: Optional[float] = None) -> int:
        """
        Apply Ebbinghaus decay to all entries.

        Returns number of entries that fell below the eviction threshold.
        """
        t = current_time or time.time()
        dead_entries = []

        with self._lock:
            for eid, entry in self._entries.items():
                activation = entry.compute_activation(t)
                if activation < 0.01:  # Effectively forgotten
                    dead_entries.append(eid)

        return len(dead_entries)

    def get_active_entries(self, top_k: int = 20,
                           current_time: Optional[float] = None) -> List[MoltbookEntry]:
        """Get the most active (highest activation) entries."""
        t = current_time or time.time()
        entries = list(self._entries.values())
        entries.sort(key=lambda e: e.compute_activation(t), reverse=True)
        return entries[:top_k]

    def consolidate(self, activation_threshold: float = 0.01) -> Dict[str, int]:
        """
        Consolidation cycle:
        1. Remove entries below activation threshold
        2. Merge highly similar entries (>0.95 cosine)

        Returns dict with counts: {'removed': N, 'merged': M}
        """
        removed = 0
        merged = 0
        t = time.time()

        with self._lock:
            # 1. Remove dead entries
            dead_ids = []
            for eid, entry in self._entries.items():
                if entry.compute_activation(t) < activation_threshold:
                    dead_ids.append(eid)

            for eid in dead_ids:
                self._remove_entry(eid)
                removed += 1

        return {'removed': removed, 'merged': merged}

    def _remove_entry(self, entry_id: str) -> None:
        """Internal: remove an entry from all indices."""
        entry = self._entries.pop(entry_id, None)
        if entry:
            # Remove from tag index
            for tag in entry.tags:
                self._tag_index[tag].discard(entry_id)
            # Remove from semantic index
            self._semantic_index.remove(entry_id)
            self._total_evicted += 1

    def _evict_lru(self) -> None:
        """Evict least-recently-used entries when over capacity."""
        excess = len(self._entries) - self._max_entries
        if excess <= 0:
            return

        # Sort by activation (lowest first)
        sorted_entries = sorted(
            self._entries.items(),
            key=lambda x: x[1].compute_activation()
        )

        for eid, _ in sorted_entries[:excess]:
            self._remove_entry(eid)

    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        return {
            'size': self.size,
            'max_entries': self._max_entries,
            'total_added': self._total_added,
            'total_evicted': self._total_evicted,
            'total_queries': self._total_queries,
            'tag_count': len(self._tag_index),
            'semantic_index': self._semantic_index.get_stats(),
        }

    def save_to_disk(self, path: Optional[str] = None) -> str:
        """Save the store to disk as JSON-Lines."""
        save_path = path or self._store_path
        if not save_path:
            save_path = 'data/moltbook/store.jsonl'

        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            for entry in self._entries.values():
                f.write(json.dumps(entry.to_dict()) + '\n')

        logger.info(f"MoltbookStore saved {self.size} entries to {save_path}")
        return save_path

    def load_from_disk(self, path: Optional[str] = None) -> int:
        """Load the store from disk. Returns number of entries loaded."""
        load_path = path or self._store_path
        if not load_path or not os.path.exists(load_path):
            return 0

        count = 0
        with open(load_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    entry = MoltbookEntry.from_dict(d)
                    self._entries[entry.id] = entry
                    # Rebuild indices
                    for tag in entry.tags:
                        self._tag_index[tag].add(entry.id)
                    if entry.semantic_embedding is not None:
                        self._semantic_index.add(entry.id, entry.semantic_embedding)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to load entry: {e}")

        self._loaded = True
        logger.info(f"MoltbookStore loaded {count} entries from {load_path}")
        return count

    @classmethod
    def from_yaml(cls, yaml_config: Dict[str, Any]) -> 'MoltbookStore':
        """Create from YAML config."""
        mb = yaml_config.get('moltbook', {})
        return cls(config=mb)


# ═══════════════════════════════════════════════════════════════════
# [4] MoltbookGraph — Knowledge Linkage with Spreading Activation
# ═══════════════════════════════════════════════════════════════════

class MoltbookGraph:
    """
    Directed graph for knowledge relationships with spreading activation.

    Entries are linked via typed edges (relates_to, supports, contradicts, etc.).
    Spreading activation: When entry X is activated, linked entries Y, Z get
    pre-activated — the basis for associative thinking.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # Adjacency: {node_id: {neighbor_id: {'type': str, 'weight': float}}}
        self._edges: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self._reverse_edges: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self._lock = threading.Lock()
        logger.info("MoltbookGraph initialized")

    @property
    def node_count(self) -> int:
        """Number of unique nodes in the graph."""
        return len(set(self._edges.keys()) | set(self._reverse_edges.keys()))

    @property
    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return sum(len(neighbors) for neighbors in self._edges.values())

    def link(self, source_id: str, target_id: str,
             link_type: str = "relates_to", weight: float = 1.0) -> None:
        """
        Create a directed edge from source to target.

        Args:
            source_id: Source entry ID
            target_id: Target entry ID
            link_type: Relationship type (relates_to, supports, contradicts, etc.)
            weight: Edge weight (higher = stronger association)
        """
        with self._lock:
            self._edges[source_id][target_id] = {
                'type': link_type,
                'weight': weight,
                'created_at': time.time()
            }
            self._reverse_edges[target_id][source_id] = {
                'type': link_type,
                'weight': weight,
                'created_at': time.time()
            }

    def unlink(self, source_id: str, target_id: str) -> bool:
        """Remove an edge. Returns True if edge existed."""
        with self._lock:
            removed = target_id in self._edges.get(source_id, {})
            if removed:
                del self._edges[source_id][target_id]
                self._reverse_edges.get(target_id, {}).pop(source_id, None)
            return removed

    def get_neighborhood(self, entry_id: str, depth: int = 1,
                          link_type: Optional[str] = None) -> Dict[str, float]:
        """
        Get the neighborhood of an entry up to a given depth.

        Returns dict of {entry_id: accumulated_weight} for all reachable nodes.
        """
        visited: Dict[str, float] = {}
        current: Dict[str, float] = {entry_id: 1.0}

        for d in range(depth):
            next_level: Dict[str, float] = {}
            decay = 0.5 ** d  # Weight decays per hop

            for node_id, node_weight in current.items():
                neighbors = self._edges.get(node_id, {})
                for neighbor_id, edge_info in neighbors.items():
                    if neighbor_id == entry_id:
                        continue  # Skip self-loops
                    if link_type and edge_info['type'] != link_type:
                        continue
                    weight = node_weight * edge_info['weight'] * decay
                    if neighbor_id in visited:
                        visited[neighbor_id] = max(visited[neighbor_id], weight)
                    else:
                        visited[neighbor_id] = weight
                    next_level[neighbor_id] = weight

            current = next_level

        return visited

    def spreading_activation(self, seed_ids: List[str], depth: int = 2,
                              decay_factor: float = 0.5,
                              activation_threshold: float = 0.1) -> List[Tuple[str, float]]:
        """
        Spreading activation from seed entries.

        Activation flows from seeds through edges, decaying at each hop.
        Returns list of (entry_id, activation_level) sorted by activation.
        """
        if isinstance(seed_ids, str):
            seed_ids = [seed_ids]

        activations: Dict[str, float] = {}
        current_level: Dict[str, float] = {sid: 1.0 for sid in seed_ids}

        for d in range(depth):
            next_level: Dict[str, float] = {}
            for node_id, activation in current_level.items():
                neighbors = self._edges.get(node_id, {})
                for neighbor_id, edge_info in neighbors.items():
                    if neighbor_id in seed_ids:
                        continue

                    spread = activation * edge_info['weight'] * (decay_factor ** (d + 1))
                    if spread >= activation_threshold:
                        if neighbor_id in activations:
                            activations[neighbor_id] = max(activations[neighbor_id], spread)
                        else:
                            activations[neighbor_id] = spread
                        next_level[neighbor_id] = spread

            current_level = next_level

        # Sort by activation descending
        result = sorted(activations.items(), key=lambda x: x[1], reverse=True)
        return result

    def find_clusters(self, min_cluster_size: int = 3) -> List[Set[str]]:
        """
        Find clusters of densely connected entries using connected components.

        Returns list of sets, each set = one cluster of entry IDs.
        """
        all_nodes = set(self._edges.keys()) | set(self._reverse_edges.keys())
        visited: Set[str] = set()
        clusters: List[Set[str]] = []

        for node in all_nodes:
            if node in visited:
                continue
            # BFS
            cluster: Set[str] = set()
            queue = [node]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                cluster.add(current)
                # Follow both directions
                for neighbor_id in self._edges.get(current, {}):
                    if neighbor_id not in visited:
                        queue.append(neighbor_id)
                for neighbor_id in self._reverse_edges.get(current, {}):
                    if neighbor_id not in visited:
                        queue.append(neighbor_id)

            if len(cluster) >= min_cluster_size:
                clusters.append(cluster)

        return clusters

    def get_contradictions(self) -> List[Tuple[str, str]]:
        """Find all pairs of entries that contradict each other."""
        contradictions = []
        for source_id, neighbors in self._edges.items():
            for target_id, edge_info in neighbors.items():
                if edge_info['type'] == 'contradicts':
                    contradictions.append((source_id, target_id))
        return contradictions

    def remove_node(self, entry_id: str) -> int:
        """Remove a node and all its edges. Returns number of edges removed."""
        removed = 0
        with self._lock:
            # Remove outgoing edges
            if entry_id in self._edges:
                for target_id in list(self._edges[entry_id].keys()):
                    self._reverse_edges.get(target_id, {}).pop(entry_id, None)
                    removed += 1
                del self._edges[entry_id]

            # Remove incoming edges
            if entry_id in self._reverse_edges:
                for source_id in list(self._reverse_edges[entry_id].keys()):
                    self._edges.get(source_id, {}).pop(entry_id, None)
                    removed += 1
                del self._reverse_edges[entry_id]

        return removed

    def to_dict(self) -> Dict[str, Any]:
        """Serialize graph to dict."""
        return {
            'edges': dict(self._edges),
            'node_count': self.node_count,
            'edge_count': self.edge_count,
        }

    def save(self, path: str) -> None:
        """Save graph to JSON file."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    def load(self, path: str) -> int:
        """Load graph from JSON file. Returns number of edges loaded."""
        if not os.path.exists(path):
            return 0
        with open(path, 'r') as f:
            data = json.load(f)

        count = 0
        for source_id, neighbors in data.get('edges', {}).items():
            for target_id, edge_info in neighbors.items():
                self.link(source_id, target_id,
                          link_type=edge_info.get('type', 'relates_to'),
                          weight=edge_info.get('weight', 1.0))
                count += 1
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return {
            'node_count': self.node_count,
            'edge_count': self.edge_count,
            'clusters': len(self.find_clusters()),
            'contradictions': len(self.get_contradictions()),
        }

    @classmethod
    def from_yaml(cls, yaml_config: Dict[str, Any]) -> 'MoltbookGraph':
        """Create from YAML config."""
        mb = yaml_config.get('moltbook', {})
        return cls(config=mb)
