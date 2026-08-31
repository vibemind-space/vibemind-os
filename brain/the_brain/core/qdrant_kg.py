"""
Unified Brain Knowledge Graph on Qdrant.

One collection `brain-kg` hosts every node type (thought / response /
bubble / idea / space / event / snapshot) with:
  - `semantic` vector (3072-dim, embedding-service) — live
  - `neural` vector  (20484-dim, TriBE fMRI) — reserved slot, filled
    later when TriBE runs through the voice/STT path (phase G.5+).

Design doc: docs/UNIFIED_KG_DESIGN.md

Key ideas:
  - Filter by `node_type` payload field when you want type-specific
    queries. No multi-collection juggling.
  - Edges live bidirectionally in `payload.linked.*` arrays, capped at
    50 per list to avoid hot-node payload bloat.
  - Writer thread batches upserts so CTE / BrainChat hot paths stay fast.
  - Graceful degradation: if Qdrant is unreachable the whole module
    becomes a no-op; Brain keeps running.

Environment:
  QDRANT_URL                default http://127.0.0.1:16333
  BRAIN_KG_COLLECTION       default "brain-kg"
  BRAIN_KG_EMBED_MODEL      default "Qwen/Qwen3-Embedding-0.6B"
  BRAIN_KG_EDGE_THRESHOLD   default 0.55
  BRAIN_KG_BATCH_SIZE       default 8
  BRAIN_KG_BATCH_FLUSH_MS   default 3000
  BRAIN_KG_NEURAL_DIM       default 20484 (TriBE slot size — only used
                            when creating the collection; wrapper still
                            writes semantic-only for now)
"""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import requests
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

# Phase B3: via central config (Swarm /run/secrets -> env -> .env). The
# config default is the SAME literal, so this is behaviour-neutral. Fail-safe
# fallback keeps the module importable if config can't load.
try:
    from core import config as _cfg_qd
    QDRANT_URL = _cfg_qd.qdrant_url()
except Exception:
    QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:16333")
EMBED_MODEL = os.environ.get(
    "BRAIN_KG_EMBED_MODEL",
    "Qwen/Qwen3-Embedding-0.6B",
)
SEMANTIC_DIM = 3072
NEURAL_DIM = int(os.environ.get("BRAIN_KG_NEURAL_DIM", "20484"))
EDGE_THRESHOLD = float(os.environ.get("BRAIN_KG_EDGE_THRESHOLD", "0.55"))
BATCH_SIZE = int(os.environ.get("BRAIN_KG_BATCH_SIZE", "8"))
BATCH_FLUSH_MS = int(os.environ.get("BRAIN_KG_BATCH_FLUSH_MS", "3000"))
MAX_LINKED = 50

# Bump this suffix any time SEMANTIC_DIM changes again — ensure_collections()
# creates a fresh physical collection per suffix and aliases the logical name
# to it, so a dimension change never requires a caller-visible rename.
PHYSICAL_VERSION_SUFFIX = "-3072-v1"


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


# TriBE integration flags (all default OFF — see docs plan tribe-active-integration).
# TRIBE_PROFILE_ENABLED      → compute & store the 8-bridge profile per thought
# TRIBE_NEURAL_VECTOR_ENABLED → also write the full 20484-dim vector into the Qdrant `neural` slot
# Both run only inside the async flush worker, so the CTE/BrainChat hot paths stay fast.
TRIBE_PROFILE_ENABLED = _flag("TRIBE_PROFILE_ENABLED")
TRIBE_NEURAL_VECTOR_ENABLED = _flag("TRIBE_NEURAL_VECTOR_ENABLED")
# Baustein C — prefix the recognised intent to the TriBE input, so the neural
# profile reflects the absicht behind a thought, not only its wording.
TRIBE_INTENT_GROUNDING = _flag("TRIBE_INTENT_GROUNDING")
# Store the 16 cortical ROIs (finer than the 8 bridges) per thought. Empirically
# discriminates functional/motor thoughts better than bridges alone.
TRIBE_ROI_ENABLED = _flag("TRIBE_ROI_ENABLED")
# Cap the text length handed to TriBE — predict latency scales with tokens.
TRIBE_PROFILE_MAXLEN = int(os.environ.get("TRIBE_PROFILE_MAXLEN", "400"))

# ──────────────────────────────────────────────────────────────────────
# Cognitive Collections (Modell C)
# ──────────────────────────────────────────────────────────────────────
# Each Brain memory kind lives in its own Qdrant collection. All share
# the same 3072-dim semantic space, so a UUID from one collection
# can be referenced as `linked.*` in another.

COLLECTIONS: Dict[str, str] = {
    "episodic":   "brain-episodic",    # thoughts, responses — Hippocampus-like
    "semantic":   "brain-semantic",    # facts, concepts — temporal cortex-like
    "procedural": "brain-procedural",  # spaces, events — basal-ganglia-like
    "state":      "brain-state",       # snapshots — working memory
    "artifacts":  "rowboat-artifacts", # bubbles, ideas — external refs (read-mostly)
    "aggregated": "aggregated-kg",     # topic/finding/decision from discourse aggregator (R.4)
    "mirofish":   "mirofish-kg",       # read-only mirror of Mirofish Neo4j entities (R.6)
    "decisions":  "brain-decisions",   # Phase 10.1 — past Plans + outcomes for recall
    "self":       "brain-self",        # Phase 10.2 — self-model: capability-confidence over time
}

# Baustein D.2 — execution-log collection (RAG-index over multihop history).
# Only registered when EXECUTION_LOG_ENABLED, so existing deployments don't get
# a new collection unless they opt in. Stores one embedded summary per step with
# the claimed-vs-verified diff, queryable via search() and direct payload filters.
EXECUTION_LOG_ENABLED = _flag("EXECUTION_LOG_ENABLED")
if EXECUTION_LOG_ENABLED:
    COLLECTIONS["execlog"] = "brain-execution-log"

# Identity stamping (Phase C). Returns {} for the default identity so every
# payload stays BYTE-IDENTICAL to before — fields only appear once BRAIN_ID/
# SPACE_ID are explicitly set (Phase D/E multi-brain). Fail-safe: if the
# config module can't import, identity stamping is simply a no-op.
def _identity_payload() -> Dict[str, Any]:
    try:
        from core import config as _cfg
        out: Dict[str, Any] = {}
        bid = _cfg.brain_id()
        if bid and bid != _cfg.BRAIN_ID_DEFAULT:
            out["brain_id"] = bid
        sid = _cfg.space_id()
        if sid:
            out["space_id"] = sid
        return out
    except Exception:
        return {}


# Back-compat: legacy single-collection code paths fall back to 'episodic'.
# This is what old `BRAIN_KG_COLLECTION=brain-kg` users now default to.
LEGACY_COLLECTION = os.environ.get("BRAIN_KG_COLLECTION", "brain-kg")

# Node type constants
NT_THOUGHT = "thought"
NT_RESPONSE = "response"
NT_FACT = "fact"              # new — for K.2+
NT_CONCEPT = "concept"        # new — consolidated
NT_BUBBLE = "bubble"
NT_IDEA = "idea"
NT_SPACE = "space"
NT_EVENT = "event"
NT_SNAPSHOT = "snapshot"
NT_TOPIC = "topic"             # R.4 — aggregator output
NT_FINDING = "finding"         # R.4 — aggregator output
NT_DECISION = "decision"       # R.4 — aggregator output
NT_META_TOPIC = "meta_topic"   # S.5 — cross-session theme, lives in aggregated
NT_MIROFISH_ENTITY = "mirofish_entity"  # R.6 — Neo4j mirror
NT_DECISION_RECORD = "decision_record"  # Phase 10.1 — past plan with outcome
NT_SELF_TRAIT = "self_trait"            # Phase 10.2 — capability-confidence belief
NT_EXEC_STEP = "exec_step"              # Baustein D.2 — one execution-trace step

ALL_NODE_TYPES = (
    NT_THOUGHT, NT_RESPONSE, NT_FACT, NT_CONCEPT,
    NT_BUBBLE, NT_IDEA, NT_SPACE, NT_EVENT, NT_SNAPSHOT,
    NT_TOPIC, NT_FINDING, NT_DECISION, NT_META_TOPIC,
    NT_MIROFISH_ENTITY,
    NT_DECISION_RECORD, NT_SELF_TRAIT, NT_EXEC_STEP,
)

NODE_TYPE_TO_COLLECTION: Dict[str, str] = {
    NT_THOUGHT:  "episodic",
    NT_RESPONSE: "episodic",
    NT_FACT:     "semantic",
    NT_CONCEPT:  "semantic",
    NT_SPACE:    "procedural",
    NT_EVENT:    "procedural",
    NT_SNAPSHOT: "state",
    NT_BUBBLE:   "artifacts",
    NT_IDEA:     "artifacts",
    NT_TOPIC:    "aggregated",
    NT_FINDING:  "aggregated",
    NT_DECISION: "aggregated",
    NT_META_TOPIC: "aggregated",  # S.5 cross-session
    NT_MIROFISH_ENTITY: "mirofish",
    "plan_execution": "episodic",  # Phase 6.14.4 — multi-hop plan summaries
    NT_DECISION_RECORD: "decisions",   # Phase 10.1
    NT_SELF_TRAIT:      "self",        # Phase 10.2
    NT_EXEC_STEP:       "execlog",     # Baustein D.2
}

# Brain-owned collections (not rowboat-artifacts / fungus-code).
# Used to decide where to search by default and which to maintain.
BRAIN_COLLECTIONS = ("episodic", "semantic", "procedural", "state")


# ──────────────────────────────────────────────────────────────────────
# Embedder — 3072-dim, embedding-service client, lazy-loaded
# ──────────────────────────────────────────────────────────────────────

class Embedder:
    """Singleton HTTP client for the embedding-service (docs/superpowers/specs/
    2026-07-13-brain-embedder-external-api-design.md). Replaces the former
    local sentence-transformers/Qwen model — same public interface
    (encode/encode_batch), so callers are unaffected by this swap.

    Concurrency: safe for concurrent GET/POST via requests.Session's
    connection pooling; no additional locking is applied by this class."""

    _instance: Optional["Embedder"] = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "Embedder":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        import requests
        from core import config as _cfg_embed

        self._base_url = _cfg_embed.embedding_service_url()
        self._session = requests.Session()
        self._timeout = float(os.environ.get("EMBEDDING_HTTP_TIMEOUT", "30"))
        logger.info(f"[KG] embedding-service client configured: {self._base_url}")

    def encode(self, text: str) -> List[float]:
        resp = self._session.post(
            f"{self._base_url}/embed", json={"text": text}, timeout=self._timeout,
        )
        resp.raise_for_status()
        vec = resp.json()["vector"]
        if len(vec) != SEMANTIC_DIM:
            raise RuntimeError(
                f"embedding-service returned {len(vec)}-dim vector, expected "
                f"{SEMANTIC_DIM} (SEMANTIC_DIM) — collection/model mismatch"
            )
        return vec

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        resp = self._session.post(
            f"{self._base_url}/embed/batch", json={"texts": texts}, timeout=self._timeout,
        )
        resp.raise_for_status()
        vecs = resp.json()["vectors"]
        for v in vecs:
            if len(v) != SEMANTIC_DIM:
                raise RuntimeError(
                    f"embedding-service returned {len(v)}-dim vector, expected "
                    f"{SEMANTIC_DIM} (SEMANTIC_DIM) — collection/model mismatch"
                )
        return vecs


# ──────────────────────────────────────────────────────────────────────
# Docs — one dataclass per node type
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ThoughtDoc:
    thought_id: str
    content: str
    category: str = "thought"
    source: str = "continuous_thinking"
    confidence: float = 0.5
    emotional_valence: float = 0.0
    arousal: float = 0.0
    created_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    space_hint: Optional[str] = None
    bridge_levels: Dict[str, float] = field(default_factory=dict)
    # 16 cortical ROIs (finer than the 8 bridges — discriminate better, esp.
    # functional/motor). Stored alongside bridge_levels when TRIBE_ROI_ENABLED.
    rois: Dict[str, float] = field(default_factory=dict)
    # Baustein C — intent grounding: the intent/task_type this thought is about.
    intent: str = ""
    task_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResponseDoc:
    response_id: str
    content: str
    user_query: str = ""
    routing_mode: str = ""
    task_type: str = ""
    confidence: float = 0.5
    llm_model: str = ""
    thinking_time_ms: float = 0.0
    source: str = "brain_chat"
    created_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BubbleDoc:
    bubble_id: str
    title: str
    description: str = ""
    notes: List[str] = field(default_factory=list)
    bubble_edges: List[str] = field(default_factory=list)
    source: str = "rowboat_reader"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IdeaDoc:
    idea_id: str
    title: str
    content: str = ""
    tags: List[str] = field(default_factory=list)
    bubble_id: Optional[str] = None
    node_subtype: str = "idea"
    source: str = "rowboat_reader"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceDoc:
    space_id: str
    title: str
    description: str = ""
    source: str = "manifest"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventDoc:
    event_id: str
    title: str
    trigger_description: str = ""
    typical_response_strategy: str = ""
    source: str = "manifest"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _point_id(external_id: str) -> str:
    """Deterministic UUID from external id so re-ingestion collapses
    duplicates instead of piling up."""
    h = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
    return str(uuid.UUID(h[:32]))


def _empty_linked() -> Dict[str, List[str]]:
    return {
        "thoughts": [],
        "responses": [],
        "bubbles": [],
        "ideas": [],
        "spaces": [],
        "events": [],
    }


# ──────────────────────────────────────────────────────────────────────
# QdrantKG
# ──────────────────────────────────────────────────────────────────────

class QdrantKG:
    """Unified knowledge graph backed by a single Qdrant collection."""

    def __init__(self, url: str = QDRANT_URL) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm
        self._qm = qm
        self.url = url
        self.client = QdrantClient(url=url, timeout=30)
        self._embedder: Optional[Embedder] = None
        self._embed_lock = threading.Lock()

        # Async writer
        self._queue: "queue.Queue[ThoughtDoc | ResponseDoc]" = queue.Queue(
            maxsize=1000
        )
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None

        self.stats: Dict[str, Any] = {
            "thoughts_indexed": 0,
            "responses_indexed": 0,
            "bubbles_indexed": 0,
            "ideas_indexed": 0,
            "spaces_indexed": 0,
            "events_indexed": 0,
            "edges_built": 0,
            "errors": 0,
            "last_error": None,
        }

    # ── Setup ─────────────────────────────────────────────────────────

    def ensure_collections(self) -> None:
        """Create every cognitive collection if missing. Idempotent.

        Each logical name in COLLECTIONS is always addressed as a Qdrant
        ALIAS, never a raw collection name — the alias resolves to a
        versioned physical collection (see PHYSICAL_VERSION_SUFFIX). This
        lets a future embedding-dimension change swap the alias onto a
        freshly migrated physical collection without touching any caller.

        Three states are handled per logical name:
          1. Alias already exists -> already migrated/set up, leave alone.
          2. Raw collection exists under that exact name, no alias -> a
             pre-migration deployment; leave it exactly as-is (this is
             what scripts/migrate_embeddings_v3072.py cuts over).
          3. Neither exists -> fresh deploy: create the physical collection
             and alias it.
        """
        qm = self._qm
        existing_collections = {c.name for c in self.client.get_collections().collections}
        existing_aliases = {a.alias_name: a.collection_name
                             for a in self.client.get_aliases().aliases}
        vectors_config = {
            "semantic": qm.VectorParams(
                size=SEMANTIC_DIM, distance=qm.Distance.COSINE,
            ),
            "neural": qm.VectorParams(
                size=NEURAL_DIM, distance=qm.Distance.COSINE,
                on_disk=True,
            ),
        }
        for logical_name, alias_name in COLLECTIONS.items():
            if alias_name in existing_aliases:
                logger.debug(
                    f"[KG] alias '{alias_name}' -> "
                    f"'{existing_aliases[alias_name]}' already set up"
                )
            elif alias_name in existing_collections:
                logger.debug(
                    f"[KG] '{alias_name}' exists as a raw collection "
                    f"(pre-migration) — leaving as-is"
                )
            else:
                physical_name = f"{alias_name}{PHYSICAL_VERSION_SUFFIX}"
                self.client.create_collection(
                    collection_name=physical_name,
                    vectors_config=vectors_config,
                )
                self.client.update_collection_aliases(change_aliases_operations=[
                    qm.CreateAliasOperation(create_alias=qm.CreateAlias(
                        collection_name=physical_name, alias_name=alias_name,
                    )),
                ])
                logger.info(
                    f"[KG] created '{physical_name}', aliased as '{alias_name}' "
                    f"(logical={logical_name}, semantic={SEMANTIC_DIM}d, "
                    f"neural={NEURAL_DIM}d on-disk)"
                )
            self._ensure_payload_indexes(alias_name)

    # Back-compat: old brain_server.py code still calls ensure_collection().
    def ensure_collection(self) -> None:
        """Back-compat wrapper. Delegates to ensure_collections()."""
        self.ensure_collections()

    def _ensure_payload_indexes(self, collection_name: str) -> None:
        """Create keyword/integer indexes on a specific collection.
        Idempotent; errors are swallowed since 'already exists' is normal."""
        qm = self._qm
        index_specs = [
            ("node_type", qm.PayloadSchemaType.KEYWORD),
            ("source", qm.PayloadSchemaType.KEYWORD),
            ("tags", qm.PayloadSchemaType.KEYWORD),
            ("space_hint", qm.PayloadSchemaType.KEYWORD),
            ("bubble_id", qm.PayloadSchemaType.KEYWORD),
            ("created_at", qm.PayloadSchemaType.INTEGER),
            # Phase C: per-brain / per-space filtering for Phase D/E multi-brain.
            # Harmless on existing collections (index of an absent field is a
            # no-op until points carry it).
            ("brain_id", qm.PayloadSchemaType.KEYWORD),
            ("space_id", qm.PayloadSchemaType.KEYWORD),
        ]
        for field_name, schema in index_specs:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=schema,
                )
            except Exception as e:  # already-exists or other minor errors
                logger.debug(f"[KG] index '{field_name}' on '{collection_name}': {e}")

    # ── Routing helpers ───────────────────────────────────────────────

    @staticmethod
    def collection_for(node_type: str) -> str:
        """Return the Qdrant collection name for a given node_type.
        Falls back to 'episodic' for unknown types (safer than crashing)."""
        logical = NODE_TYPE_TO_COLLECTION.get(node_type, "episodic")
        return COLLECTIONS[logical]

    # ── Embedder access ───────────────────────────────────────────────

    def _embedder_ready(self) -> Embedder:
        if self._embedder is None:
            with self._embed_lock:
                if self._embedder is None:
                    self._embedder = Embedder.get()
        return self._embedder

    # ── Single-shot upsert helpers (sync) ─────────────────────────────

    def _upsert_point(
        self, external_id: str, node_type: str, text: str,
        payload_extra: Dict[str, Any],
    ) -> Optional[str]:
        """Embed + upsert one point synchronously. Returns point id.
        Routes to the right cognitive collection based on node_type.

        IMPORTANT: Preserves existing `linked` payload on re-upserts so
        repeated bulk-imports (Rowboat startup, etc.) don't wipe back-edges
        that other nodes have already attached.
        """
        qm = self._qm
        coll = self.collection_for(node_type)
        try:
            vec = self._embedder_ready().encode(text)
            pid = _point_id(external_id)

            # Preserve existing linked.* if the point already exists
            existing_linked = None
            try:
                rec = self.client.retrieve(
                    collection_name=coll, ids=[pid], with_payload=True,
                )
                if rec and rec[0].payload:
                    existing_linked = rec[0].payload.get("linked")
            except Exception:
                pass

            payload: Dict[str, Any] = {
                "node_type": node_type,
                "content": text[:2000],
                "created_at": int(payload_extra.get("created_at", time.time())),
                "linked": existing_linked or _empty_linked(),
                # Phase C identity stamp — {} (no-op) for the default identity,
                # so payloads stay byte-identical until BRAIN_ID/SPACE_ID set.
                # Placed before payload_extra so an explicit caller value wins.
                **_identity_payload(),
                **payload_extra,
            }
            self.client.upsert(
                collection_name=coll,
                points=[qm.PointStruct(
                    id=pid,
                    vector={"semantic": vec},  # neural slot stays unfilled
                    payload=payload,
                )],
                wait=True,
            )
            return pid
        except (requests.exceptions.RequestException, RuntimeError) as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"upsert_point({node_type}->{coll}): {e}"
            logger.error(
                f"[KG] embedding-service call failed in upsert_point({node_type}->{coll}): {e}"
            )
            return None
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"upsert_point({node_type}->{coll}): {e}"
            logger.warning(f"[KG] upsert_point({node_type}->{coll}) failed: {e}")
            return None

    def upsert_bubble(self, doc: BubbleDoc, build_edges: bool = True) -> Optional[str]:
        text = f"{doc.title}\n{doc.description}\n" + "\n".join(doc.notes[:5])
        payload = {
            "bubble_id": doc.bubble_id,
            "title": doc.title,
            "description": doc.description,
            "notes": doc.notes[:20],
            "bubble_edges": doc.bubble_edges,
            "source": doc.source,
            **doc.metadata,
        }
        pid = self._upsert_point(doc.bubble_id, NT_BUBBLE, text, payload)
        if pid:
            self.stats["bubbles_indexed"] += 1
            if build_edges:
                self._build_edges(pid, text, NT_BUBBLE)
        return pid

    def upsert_idea(self, doc: IdeaDoc, build_edges: bool = True) -> Optional[str]:
        text = f"{doc.title}\n{doc.content}"
        payload = {
            "idea_id": doc.idea_id,
            "title": doc.title,
            "tags": doc.tags,
            "bubble_id": doc.bubble_id,
            "node_subtype": doc.node_subtype,
            "source": doc.source,
            **doc.metadata,
        }
        pid = self._upsert_point(doc.idea_id, NT_IDEA, text, payload)
        if pid:
            self.stats["ideas_indexed"] += 1
            if build_edges:
                self._build_edges(pid, text, NT_IDEA)
        return pid

    def upsert_space(self, doc: SpaceDoc, build_edges: bool = True) -> Optional[str]:
        text = f"{doc.title}\n{doc.description}"
        payload = {
            "space_id": doc.space_id,
            "title": doc.title,
            "description": doc.description,
            "source": doc.source,
            "activation_strength": 0.0,
            **doc.metadata,
        }
        pid = self._upsert_point(doc.space_id, NT_SPACE, text, payload)
        if pid:
            self.stats["spaces_indexed"] += 1
            if build_edges:
                self._build_edges(pid, text, NT_SPACE)
        return pid

    def upsert_event(self, doc: EventDoc, build_edges: bool = True) -> Optional[str]:
        text = f"{doc.title}\n{doc.trigger_description}\n{doc.typical_response_strategy}"
        payload = {
            "event_id": doc.event_id,
            "title": doc.title,
            "trigger_description": doc.trigger_description,
            "typical_response_strategy": doc.typical_response_strategy,
            "source": doc.source,
            "activation_strength": 0.0,
            **doc.metadata,
        }
        pid = self._upsert_point(doc.event_id, NT_EVENT, text, payload)
        if pid:
            self.stats["events_indexed"] += 1
            if build_edges:
                self._build_edges(pid, text, NT_EVENT)
        return pid

    def upsert_response(self, doc: ResponseDoc) -> Optional[str]:
        """Chat responses go through sync path — user is waiting."""
        payload = {
            "response_id": doc.response_id,
            "user_query": doc.user_query,
            "routing_mode": doc.routing_mode,
            "task_type": doc.task_type,
            "confidence": doc.confidence,
            "llm_model": doc.llm_model,
            "thinking_time_ms": doc.thinking_time_ms,
            "source": doc.source,
            "tags": doc.tags,
            **doc.metadata,
        }
        pid = self._upsert_point(doc.response_id, NT_RESPONSE, doc.content, payload)
        if pid:
            self.stats["responses_indexed"] += 1
            self._build_edges(pid, doc.content, NT_RESPONSE)
        return pid

    # ── Async thought queue ───────────────────────────────────────────

    def upsert_thought(self, doc: ThoughtDoc) -> None:
        """Queue a thought for async embed + upsert + edge-build."""
        try:
            self._queue.put_nowait(doc)
        except queue.Full:
            logger.warning("[KG] write queue full — dropping thought")

    def _flush_thoughts(self, batch: List[ThoughtDoc]) -> None:
        """Batch embed + upsert thoughts (→ episodic), then build edges."""
        if not batch:
            return
        qm = self._qm
        coll = COLLECTIONS["episodic"]
        try:
            vectors = self._embedder_ready().encode_batch([t.content for t in batch])
            # Read existing linked to avoid wiping back-edges on duplicate ids
            pids = [_point_id(t.thought_id) for t in batch]
            existing_links: Dict[str, Dict[str, list]] = {}
            try:
                recs = self.client.retrieve(
                    collection_name=coll, ids=pids, with_payload=True,
                )
                for r in recs:
                    if r.payload and r.payload.get("linked"):
                        existing_links[str(r.id)] = r.payload["linked"]
            except Exception:
                pass

            points: List[Any] = []
            for i, t in enumerate(batch):
                pid = pids[i]
                # TriBE neural signature (async, flag-gated, failure-safe). Computes
                # the 8-bridge interpretable profile and optionally the full 20484-dim
                # fMRI vector. Never let a TriBE error drop the thought — semantic
                # upsert must always proceed.
                bridge_levels = t.bridge_levels
                rois = t.rois
                neural_vec = None
                if (TRIBE_PROFILE_ENABLED or TRIBE_NEURAL_VECTOR_ENABLED or TRIBE_ROI_ENABLED) and t.content:
                    try:
                        from core.tribe_encoder import TribeEncoder
                        enc = TribeEncoder.get()
                        # Baustein C — ground the profile in the intent.
                        if TRIBE_INTENT_GROUNDING and getattr(t, "intent", ""):
                            text = (f"[intent: {t.intent}] {t.content}")[:TRIBE_PROFILE_MAXLEN]
                        else:
                            text = t.content[:TRIBE_PROFILE_MAXLEN]
                        vec = enc.predict(text)
                        if vec is not None:
                            if TRIBE_PROFILE_ENABLED and not bridge_levels:
                                bridge_levels = enc.bridge_levels(vec)
                            if TRIBE_ROI_ENABLED and not rois:
                                rois = {k: round(float(v), 6)
                                        for k, v in enc.aggregate_roi(vec).items()}
                            if TRIBE_NEURAL_VECTOR_ENABLED and len(vec) == NEURAL_DIM:
                                neural_vec = vec.tolist()
                    except Exception as te:
                        logger.debug(f"[KG] TriBE profile skipped: {te}")
                payload = {
                    "node_type": NT_THOUGHT,
                    "thought_id": t.thought_id,
                    "content": t.content[:2000],
                    "category": t.category,
                    "source": t.source,
                    "confidence": t.confidence,
                    "emotional_valence": t.emotional_valence,
                    "arousal": t.arousal,
                    "created_at": int(t.created_at),
                    "tags": t.tags,
                    "space_hint": t.space_hint,
                    "bridge_levels": bridge_levels,
                    "rois": rois,  # 16 cortical ROIs (finer than bridges)
                    # Baustein C — intent↔profil association: store the intent/
                    # task_type next to the bridge profile so {intent, profile}
                    # tuples are queryable + become training data for Baustein A.
                    "intent": getattr(t, "intent", "") or "",
                    "task_type": getattr(t, "task_type", "") or "",
                    "linked": existing_links.get(pid) or _empty_linked(),
                    **t.metadata,
                }
                vector_payload: Dict[str, Any] = {"semantic": vectors[i]}
                if neural_vec is not None:
                    vector_payload["neural"] = neural_vec
                points.append(qm.PointStruct(
                    id=pid,
                    vector=vector_payload,
                    payload=payload,
                ))
            self.client.upsert(collection_name=coll, points=points, wait=True)
            self.stats["thoughts_indexed"] += len(points)
            # Build edges for each thought using its pre-computed vector
            for i, t in enumerate(batch):
                pid = _point_id(t.thought_id)
                self._build_edges(pid, t.content, NT_THOUGHT, vector=vectors[i])
        except (requests.exceptions.RequestException, RuntimeError) as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"flush_thoughts: {e}"
            logger.error(f"[KG] embedding-service call failed in flush_thoughts: {e}")
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"flush_thoughts: {e}"
            logger.warning(f"[KG] flush_thoughts failed: {e}")

    # ── Edge building ────────────────────────────────────────────────

    # Plural key for each node_type → linked.<key>
    _PLURAL = {
        NT_THOUGHT: "thoughts",
        NT_RESPONSE: "responses",
        NT_FACT: "facts",
        NT_CONCEPT: "concepts",
        NT_BUBBLE: "bubbles",
        NT_IDEA: "ideas",
        NT_SPACE: "spaces",
        NT_EVENT: "events",
        NT_SNAPSHOT: "snapshots",
    }

    def _build_edges(
        self, self_pid: str, text: str, self_node_type: str,
        vector: Optional[List[float]] = None,
    ) -> None:
        """Find semantically-similar non-self points across ALL cognitive
        collections and materialize edges bidirectionally."""
        qm = self._qm
        try:
            if vector is None:
                vector = self._embedder_ready().encode(text)

            self_coll = self.collection_for(self_node_type)
            self_links: Dict[str, List[str]] = _empty_linked()
            all_hits: List[tuple] = []  # (collection_name, hit)

            # Search across every cognitive collection (Brain + Rowboat artifacts)
            for logical_name, coll_name in COLLECTIONS.items():
                try:
                    hits = self.client.query_points(
                        collection_name=coll_name,
                        query=vector,
                        using="semantic",
                        limit=10,
                        score_threshold=EDGE_THRESHOLD,
                        with_payload=True,
                    ).points
                except Exception as e:
                    logger.debug(f"[KG] search in '{coll_name}' failed: {e}")
                    continue
                for h in hits:
                    if coll_name == self_coll and str(h.id) == self_pid:
                        continue
                    if not h.payload:
                        continue
                    all_hits.append((coll_name, h))

            # Aggregate self.linked
            for coll_name, h in all_hits:
                nt = h.payload.get("node_type")
                key = self._PLURAL.get(nt)
                if not key:
                    continue
                ref = (
                    h.payload.get(f"{nt}_id")
                    or h.payload.get("thought_id")
                    or str(h.id)
                )
                if ref not in self_links[key]:
                    self_links[key].append(ref)
                if len(self_links[key]) >= MAX_LINKED:
                    self_links[key] = self_links[key][-MAX_LINKED:]

            # Write self-side
            self.client.set_payload(
                collection_name=self_coll,
                payload={"linked": self_links},
                points=[self_pid],
            )

            # Append self ref to each target's linked.<self_type>
            self_type_key = self._PLURAL.get(self_node_type)
            if self_type_key is None:
                return
            self_ref = self._external_id_from_type(self_node_type, self_pid, text, self_coll)
            for coll_name, h in all_hits:
                existing_linked = h.payload.get("linked") or _empty_linked()
                bucket = existing_linked.get(self_type_key) or []
                if self_ref in bucket:
                    continue
                bucket.append(self_ref)
                bucket = bucket[-MAX_LINKED:]
                existing_linked[self_type_key] = bucket
                try:
                    self.client.set_payload(
                        collection_name=coll_name,
                        payload={"linked": existing_linked},
                        points=[h.id],
                    )
                    self.stats["edges_built"] += 1
                except Exception as e:
                    logger.debug(f"[KG] back-edge update in '{coll_name}' failed: {e}")
        except (requests.exceptions.RequestException, RuntimeError) as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"build_edges: {e}"
            logger.error(f"[KG] embedding-service call failed in build_edges: {e}")
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"build_edges: {e}"
            logger.debug(f"[KG] build_edges failed: {e}")

    def _external_id_from_type(
        self, node_type: str, pid: str, text: str,
        coll_name: Optional[str] = None,
    ) -> str:
        """Fetch the external id (e.g. thought_id, bubble_id) for a point,
        so back-edges reference stable ids instead of UUIDs."""
        if coll_name is None:
            coll_name = self.collection_for(node_type)
        try:
            rec = self.client.retrieve(
                collection_name=coll_name, ids=[pid], with_payload=True,
            )
            if rec and rec[0].payload:
                p = rec[0].payload
                return (
                    p.get(f"{node_type}_id")
                    or p.get("thought_id")
                    or pid
                )
        except Exception:
            pass
        return pid

    def get_thought_profile(self, thought_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the stored TriBE bridge-profile for a thought (interpretation).

        Returns {thought_id, content, bridge_levels, profile, has_neural} or
        None if the thought isn't found. profile is the human-readable summary.
        """
        try:
            from core.tribe_encoder import describe_profile
        except Exception:
            describe_profile = lambda bl: ""  # noqa: E731
        coll = COLLECTIONS["episodic"]
        pid = _point_id(thought_id)
        try:
            recs = self.client.retrieve(
                collection_name=coll, ids=[pid],
                with_payload=True, with_vectors=False,
            )
        except Exception as e:
            logger.debug(f"[KG] get_thought_profile retrieve failed: {e}")
            return None
        if not recs:
            return None
        p = recs[0].payload or {}
        bl = p.get("bridge_levels") or {}
        # has_neural: cheap check whether the 20484-dim slot was populated
        has_neural = False
        try:
            vrecs = self.client.retrieve(
                collection_name=coll, ids=[pid],
                with_payload=False, with_vectors=["neural"],
            )
            if vrecs and getattr(vrecs[0], "vector", None):
                nv = vrecs[0].vector
                has_neural = bool(nv.get("neural")) if isinstance(nv, dict) else bool(nv)
        except Exception:
            pass
        return {
            "thought_id": thought_id,
            "content": p.get("content", ""),
            "bridge_levels": bl,
            "rois": p.get("rois") or {},   # 16 cortical ROIs (finer resolution)
            "intent": p.get("intent", ""),
            "task_type": p.get("task_type", ""),
            "profile": describe_profile(bl),
            "has_neural": has_neural,
        }

    # ── Search API ───────────────────────────────────────────────────

    def search(
        self, query: str, node_type: Optional[str] = None,
        collection: Optional[str] = None,
        limit: int = 10, score_threshold: float = 0.0,
        payload_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search across cognitive collections.

        Args:
            query: Free-text query (multilingual via Qwen).
            node_type: Optional node_type filter (thought/bubble/event/...).
                If set, implicitly narrows the collection to that type's
                home (e.g. node_type='space' → only procedural).
            collection: Optional logical collection name
                ('episodic', 'semantic', 'procedural', 'state', 'artifacts').
                If None: searches all cognitive collections and merges by score.
            limit: Max hits per collection (merged result may exceed if no collection specified).
            score_threshold: Min cosine score.

        Returns:
            List of {id, score, payload, collection} dicts, sorted by score desc.
        """
        qm = self._qm
        try:
            vec = self._embedder_ready().encode(query)

            # Determine which collections to hit
            if node_type is not None:
                colls_to_query = [self.collection_for(node_type)]
            elif collection is not None:
                qdrant_name = COLLECTIONS.get(collection)
                if qdrant_name is None:
                    # User passed a raw qdrant collection name? Try directly.
                    qdrant_name = collection
                colls_to_query = [qdrant_name]
            else:
                colls_to_query = [COLLECTIONS[c] for c in COLLECTIONS]

            # Optional node_type + payload filters (must-conditions)
            must = []
            if node_type:
                must.append(qm.FieldCondition(
                    key="node_type", match=qm.MatchValue(value=node_type),
                ))
            if payload_filter:
                for k, v in payload_filter.items():
                    must.append(qm.FieldCondition(
                        key=k, match=qm.MatchValue(value=v),
                    ))
            qfilter = qm.Filter(must=must) if must else None

            # Reverse lookup: qdrant collection name → logical name (for payload)
            name_to_logical = {v: k for k, v in COLLECTIONS.items()}

            all_hits: List[Dict[str, Any]] = []
            for coll in colls_to_query:
                try:
                    hits = self.client.query_points(
                        collection_name=coll,
                        query=vec,
                        using="semantic",
                        limit=limit,
                        score_threshold=score_threshold,
                        query_filter=qfilter,
                        with_payload=True,
                    ).points
                except Exception as e:
                    logger.debug(f"[KG] search in '{coll}' failed: {e}")
                    continue
                logical = name_to_logical.get(coll, coll)
                for h in hits:
                    all_hits.append({
                        "id": str(h.id),
                        "score": float(h.score),
                        "payload": h.payload or {},
                        "collection": logical,
                    })
            all_hits.sort(key=lambda x: x["score"], reverse=True)
            return all_hits[:limit] if len(colls_to_query) == 1 else all_hits
        except (requests.exceptions.RequestException, RuntimeError) as e:
            logger.error(f"[KG] embedding-service call failed in search: {e}")
            return []
        except Exception as e:
            logger.warning(f"[KG] search failed: {e}")
            return []

    # ── Worker lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="QdrantKG-writer",
        )
        self._worker.start()
        logger.info("[KG] background writer started")

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _worker_loop(self) -> None:
        batch: List[ThoughtDoc] = []
        last_flush = time.time()
        while not self._stop.is_set():
            try:
                doc = self._queue.get(timeout=0.5)
                batch.append(doc)
            except queue.Empty:
                pass
            now = time.time()
            time_to_flush = (now - last_flush) * 1000 >= BATCH_FLUSH_MS
            size_to_flush = len(batch) >= BATCH_SIZE
            if batch and (time_to_flush or size_to_flush):
                self._flush_thoughts(batch)
                batch = []
                last_flush = now
        if batch:
            self._flush_thoughts(batch)

    # ── CTE integration ─────────────────────────────────────────────

    def make_thought_callback(self) -> Callable[[Any], None]:
        """Build a callback compatible with CTE._on_thought_callbacks.

        CTE hands us either a ContinuousThought dataclass or a dict.
        We normalise into ThoughtDoc and queue it.
        """
        def cb(thought: Any) -> None:
            try:
                if isinstance(thought, dict):
                    get = thought.get
                    content = get("content") or get("text") or ""
                    tid = get("id") or get("thought_id") or str(uuid.uuid4())
                    category = get("category") or "thought"
                    conf = float(get("confidence", 0.5) or 0.5)
                    val = float(get("emotional_valence", 0.0) or 0.0)
                    ar = float(get("arousal", 0.0) or 0.0)
                    created = float(get("timestamp", time.time()))
                    tags = list(get("tags") or [])
                    space_hint = get("space_hint")
                    intent = get("intent") or ""
                    task_type = get("task_type") or ""
                else:
                    g = lambda k, d=None: getattr(thought, k, d)
                    content = g("content") or g("text") or ""
                    tid = g("id") or g("thought_id") or str(uuid.uuid4())
                    category = g("category") or "thought"
                    conf = float(g("confidence", 0.5) or 0.5)
                    val = float(g("emotional_valence", 0.0) or 0.0)
                    ar = float(g("arousal", 0.0) or 0.0)
                    created = float(g("timestamp", time.time()))
                    tags = list(g("tags") or [])
                    space_hint = g("space_hint")
                    intent = g("intent") or ""
                    task_type = g("task_type") or ""

                if not content or len(content.strip()) < 3:
                    return

                self.upsert_thought(ThoughtDoc(
                    thought_id=str(tid),
                    content=content[:2000],
                    category=str(category),
                    source="continuous_thinking",
                    confidence=conf,
                    emotional_valence=val,
                    arousal=ar,
                    created_at=created,
                    tags=tags,
                    space_hint=space_hint,
                    intent=str(intent)[:200],
                    task_type=str(task_type)[:80],
                ))
            except Exception as e:
                logger.debug(f"[KG] thought callback failed: {e}")

        return cb
