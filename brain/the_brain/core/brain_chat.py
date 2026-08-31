"""
Brain Chat — Central Chat Interface Routed Through Thalamus

This is the SINGLE entry point for all chat interactions with the Brain.
Every message goes through Thalamus (the 3-layer routing system) before
any module handles it. Moltbook becomes the "thought display" — it shows
what the brain is thinking, not the intelligence itself.

Architecture:
    User Input
        ↓
    BrainChat.send()
        ↓
    ┌─ Thalamus Routing (3-Layer) ─────────────────────────┐
    │  L1: TaskFeatureRouter → routing_weights, mode       │
    │  L2: ConversationPathPlanner → path, confidence      │
    │  L3: DecisionRouter → actionable decision            │
    └──────────────────────────────────────────────────────┘
        ↓
    Module Dispatch (based on routing decision)
        ↓
    ┌─ Response Assembly ──────────────────────────────────┐
    │  KnowledgeAugmentor → external knowledge             │
    │  InternalMonologue → deep thinking                   │
    │  TalkerModule → natural language                     │
    └──────────────────────────────────────────────────────┘
        ↓
    Response + ThoughtTrace (for Moltbook to display)

Continuous Thinking:
    The ContinuousThinkingEngine runs a background thread that:
    - Generates micro-thoughts every 200-500ms
    - Feeds thoughts into the ThoughtBuffer (Global Workspace)
    - Reflects on recent conversations
    - Explores topics autonomously when idle
    - Makes all thoughts available to Moltbook for visualization
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
import uuid
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger('brain.chat')

# Try importing ThalamicAdapter (available if thalamic rewiring is deployed)
try:
    from core.thalamic_adapter import ThalamicAdapter
except ImportError:
    ThalamicAdapter = None


# ═══════════════════════════════════════════════════════════════════
# Data Types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ThoughtTrace:
    """A single thought trace — what the brain was thinking."""
    timestamp: float = 0.0
    category: str = "thought"  # thought/routing/retrieval/augment/speak
    content: str = ""
    module: str = ""           # which module generated this
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainChatResponse:
    """Complete response from the brain chat system."""
    # The actual response text
    response_text: str = ""
    confidence: float = 0.5

    # Routing info (from Thalamus)
    routing_mode: str = "routine"      # urgent/analytical/creative/routine
    routing_weights: List[float] = field(default_factory=list)
    dominant_areas: List[str] = field(default_factory=list)
    task_type: str = "general"

    # Thought trace (for Moltbook visualization)
    thought_trace: List[ThoughtTrace] = field(default_factory=list)

    # Timing
    routing_time_ms: float = 0.0
    thinking_time_ms: float = 0.0
    speaking_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Sources
    sources: List[str] = field(default_factory=list)
    augmented: bool = False
    augment_source: str = ""

    # Auto-dispatch (Phase F.4): if user @-mentioned Minibook agents
    auto_dispatch: Optional[Dict[str, Any]] = None

    # Phase R+ — Discourse-based decision (intent-mode)
    discourse_decision: Optional[Dict[str, Any]] = None

    # Phase 6 — Multi-hop plan execution metadata (plan_id, hop_count, etc.)
    multihop: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'response': self.response_text,
            'confidence': self.confidence,
            'routing': {
                'mode': self.routing_mode,
                'weights': self.routing_weights[:10] if self.routing_weights else [],
                'dominant_areas': self.dominant_areas,
                'task_type': self.task_type,
            },
            'thought_trace': [
                {
                    'timestamp': t.timestamp,
                    'category': t.category,
                    'content': t.content,
                    'module': t.module,
                    'confidence': t.confidence,
                }
                for t in self.thought_trace
            ],
            'timing': {
                'routing_ms': round(self.routing_time_ms, 1),
                'thinking_ms': round(self.thinking_time_ms, 1),
                'speaking_ms': round(self.speaking_time_ms, 1),
                'total_ms': round(self.total_time_ms, 1),
            },
            'sources': self.sources,
            'augmented': self.augmented,
            'augment_source': self.augment_source,
            'auto_dispatch': self.auto_dispatch,
            'discourse_decision': self.discourse_decision,
            'multihop': self.multihop,
        }


@dataclass
class ContinuousThought:
    """A background thought produced by the continuous thinking engine."""
    timestamp: float = 0.0
    content: str = ""
    category: str = "idle"     # idle/reflect/explore/consolidate/dream/evolve
    topic: str = ""
    relevance: float = 0.0
    emotional_valence: float = 0.0
    arousal: float = 0.0
    # ── Evolution fields ──
    thought_id: str = ""             # uuid4[:8], set on creation
    fitness: float = -1.0            # -1 = unscored, 0.0-1.0 = scored
    generation: int = 0              # 0 = original, 1+ = evolved offspring
    parent_ids: List[str] = field(default_factory=list)  # lineage tracking
    # ── Intent grounding (Baustein C) ──
    # The intent/task_type that the thought is about (e.g. from a plan event),
    # so reflections carry the absicht, and TriBE can profile intent+content.
    intent: str = ""
    task_type: str = ""
    # ── Radial integration ──
    _ring_signature: Any = None      # RingSignature, set by ThoughtRadialBridge


@dataclass
class ContextBundle:
    """Assembled context from ALL knowledge sources for response enrichment.

    Gathered by BrainChat._assemble_context() before speaking, so
    TalkerModule has maximum context to work with.
    """
    # From ContinuousThinkingEngine._learned_knowledge
    learned_facts: List[str] = field(default_factory=list)
    # From ContinuousThinkingEngine._thoughts (relevant background thoughts)
    background_insights: List[str] = field(default_factory=list)
    # From ContinuousThinkingEngine._conversation_history (recent relevant turns)
    conversation_context: str = ""
    # From ThoughtStream.get_relevant_thoughts() (Global Workspace)
    stream_thoughts: List[str] = field(default_factory=list)
    # Metrics
    total_items: int = 0
    assembly_time_ms: float = 0.0


@dataclass
class SynthesisResult:
    """Result from one synthesis operation (structural, contradiction, novel, gap)."""
    synthesis_type: str = ""        # "structural", "contradiction", "novel", "gap"
    content: str = ""               # The synthesized text
    entries_involved: List[str] = field(default_factory=list)
    confidence: float = 0.0         # Quality score from ACC+PFC evaluation
    module_signals: Dict[str, float] = field(default_factory=dict)


@dataclass
class MicroAgentConfig:
    """Configuration for a single micro-agent in the MicroAgentPool."""
    name: str                        # "summarizer", "connector", "critic", "enricher", "responder"
    model: str                       # OpenRouter model ID (e.g., "qwen/qwen3-235b-a22b:free")
    system_prompt: str               # Agent's role/personality
    max_tokens: int = 200            # Keep responses tiny
    temperature: float = 0.7
    cooldown_seconds: float = 30.0   # Min time between runs
    hourly_cap: int = 20             # Max runs per hour
    tools: Optional[list] = None      # OpenAI tool definitions (for tool-use agents)


@dataclass
class RefinedKnowledge:
    """Result from a micro-agent refinement pass."""
    original: str                    # Original entry text
    refined: str                     # LLM-refined version
    agent: str                       # Which agent produced this
    refinement_type: str             # "summary", "connection", "critique", "enrichment", "response_enhancement"
    confidence: float = 0.0          # Quality score
    timestamp: float = 0.0


# ═══════════════════════════════════════════════════════════════════
# Phase S — Self-awareness query detection
# ═══════════════════════════════════════════════════════════════════

_SELF_QUERY_KEYWORDS = (
    # English
    "who are you", "what are you", "what do you do", "what can you",
    "your architecture", "your modules", "your code", "yourself",
    "describe yourself", "tell me about yourself", "your design",
    "what's brain", "what is brain", "how do you work", "how are you built",
    # German
    "was bist du", "wer bist du", "was machst du", "deine architektur",
    "dein code", "deine module", "über dich", "wie funktionierst",
    "wie bist du aufgebaut", "was ist brain", "was ist vibemind",
    "dein system", "deine rolle", "deine aufgabe",
)


def _looks_like_self_query(message: str) -> bool:
    """Lightweight heuristic: does the message ask about Brain itself?

    Returns True for messages that trigger the self-awareness lookup path
    (S.1 substrate concepts + S.5 historical memory). Conservative — false
    positives just mean an extra cheap KG lookup.
    """
    if not message:
        return False
    t = message.lower().strip()
    if any(kw in t for kw in _SELF_QUERY_KEYWORDS):
        return True
    # Heuristic: "@brain" or "@vibemind" mention
    if "@brain" in t or "@vibemind" in t:
        return True
    # Very short pronoun questions
    if len(t) < 80 and any(
        f" {p}" in f" {t} "
        for p in ("you", "yourself", "yours", "du", "dich", "dein", "deine")
    ):
        if "?" in t:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════
# Researcher Tool Execution Functions + Definitions
# ═══════════════════════════════════════════════════════════════════

def _execute_web_search(query: str) -> str:
    """Search the web via DuckDuckGo (max 3 results). Returns JSON string."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=3))
        results = [
            {
                'title': r.get('title', ''),
                'url': r.get('href', ''),
                'snippet': r.get('body', '')[:300],
            }
            for r in raw[:3]
        ]
        return json.dumps(results)
    except Exception as e:
        return f"Error: Search failed — {e}"


def _execute_fetch_url(url: str) -> str:
    """Fetch a URL and return plain text (max 2000 chars), HTML stripped."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            'User-Agent': 'TheBrain/1.0 (Tahlamus AI Project)',
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        # Strip <script> and <style> blocks
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Strip all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:2000]
    except Exception as e:
        return f"Error: Fetch failed — {e}"


RESEARCHER_TOOLS: List[Dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Search the web for information using DuckDuckGo.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'The search query.',
                    },
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'fetch_url',
            'description': 'Fetch a URL and return its text content.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'url': {
                        'type': 'string',
                        'description': 'The URL to fetch.',
                    },
                },
                'required': ['url'],
            },
        },
    },
]

_TOOL_EXECUTORS: Dict[str, Callable] = {
    'web_search': lambda args: _execute_web_search(args.get('query', '')),
    'fetch_url': lambda args: _execute_fetch_url(args.get('url', '')),
}


# ═══════════════════════════════════════════════════════════════════
# KnowledgeExpander — Proactive Knowledge Linking & Expansion
# ═══════════════════════════════════════════════════════════════════

class KnowledgeExpander:
    """
    Proactively expands knowledge through auto-linking and follow-up exploration.

    Three mechanisms:
    1. AUTO-LINK: When new knowledge is stored, find similar Moltbook entries
       and create graph links (RELATES_TO, EXTENDS).
    2. FOLLOW-UP QUEUE: Generate 1-2 follow-up search queries after each
       augmentation. These get fetched in the CTE background thread.
    3. GRAPH CONTEXT: When assembling context for responses, also pull in
       knowledge from graph-linked entries (spreading activation).
    """

    _FOLLOW_UP_PATTERNS = [
        "practical applications of {topic}",
        "how does {topic} work",
        "history of {topic}",
        "{topic} real world examples",
        "why is {topic} important",
        "types of {topic}",
        "key concepts in {topic}",
        "{topic} recent developments",
    ]

    def __init__(self, moltbook_store=None, augmentor=None):
        """
        Args:
            moltbook_store: MoltbookStore instance (has link_entries,
                            query_semantic, get_linked)
            augmentor: KnowledgeAugmentor instance (for background fetching)
        """
        self._store = moltbook_store
        self._augmentor = augmentor
        self._expansion_queue: deque = deque(maxlen=20)
        self._expanded_topics: set = set()
        self._total_expansions: int = 0
        self._total_links: int = 0
        self._lock = threading.Lock()

    def auto_link(self, entry_id: str, content: str,
                  topics: List[str]) -> int:
        """
        Find similar Moltbook entries and create graph links.

        Args:
            entry_id: The ID of the newly stored entry
            content: The content text to find similar entries for
            topics: Topic tags for context

        Returns:
            Number of links created
        """
        if not self._store or not entry_id or not content:
            return 0

        try:
            # Find similar entries via semantic search
            scored = self._store.query_semantic(
                content, top_k=6, threshold=0.4, return_scores=True,
            )
            links_created = 0
            for entry, sim_score, _ in scored:
                if entry.id == entry_id:
                    continue  # Skip self-link
                # Choose link type based on similarity
                link_type = "extends" if sim_score > 0.7 else "relates_to"
                if self._store.link_entries(entry_id, entry.id, link_type):
                    links_created += 1
                if links_created >= 3:
                    break

            self._total_links += links_created
            return links_created
        except Exception as e:
            logger.debug(f"KnowledgeExpander.auto_link failed: {e}")
            return 0

    def generate_follow_ups(self, topic: str,
                            knowledge: str) -> List[str]:
        """
        Generate 1-2 follow-up queries and add to expansion queue.

        Args:
            topic: The topic to explore further
            knowledge: The knowledge text (used for context)

        Returns:
            List of generated follow-up queries
        """
        if not topic or len(topic.strip()) < 3:
            return []

        # Clean the topic — strip punctuation, question marks, stopwords
        import re
        clean = re.sub(r'[?!.,;:"\']', '', topic).strip().lower()
        # Remove common stopwords that pollute search queries
        stopwords = {'what', 'is', 'are', 'how', 'does', 'do', 'the',
                     'a', 'an', 'tell', 'me', 'about', 'explain', 'why'}
        words = [w for w in clean.split() if w not in stopwords and len(w) > 1]
        clean = ' '.join(words).strip()
        if len(clean) < 3:
            return []
        if clean in self._expanded_topics:
            return []

        self._expanded_topics.add(clean)

        # Cap expanded set at 200 — trim to 150 when exceeded
        if len(self._expanded_topics) > 200:
            self._expanded_topics = set(list(self._expanded_topics)[-150:])

        # Pick 1-2 random follow-up patterns using the cleaned topic
        count = min(2, len(self._FOLLOW_UP_PATTERNS))
        patterns = random.sample(self._FOLLOW_UP_PATTERNS, count)
        queries = [p.format(topic=clean) for p in patterns]

        with self._lock:
            existing = set(self._expansion_queue)
            for q in queries:
                if q not in existing:
                    self._expansion_queue.append(q)

        return queries

    def has_pending(self) -> bool:
        """Check if there are queued expansion queries."""
        return len(self._expansion_queue) > 0

    def expand_next(self) -> Optional[Dict[str, Any]]:
        """
        Pop next query from queue and fetch knowledge via augmentor.

        This is called from the CTE background thread, so HTTP latency
        is acceptable (up to 5s).

        Returns:
            Dict with 'query', 'answer', 'source' if successful, else None
        """
        if not self._augmentor or not self._expansion_queue:
            return None

        with self._lock:
            if not self._expansion_queue:
                return None
            query = self._expansion_queue.popleft()

        try:
            result = self._augmentor.augment(
                query=query,
                topics=query.split()[:5],
                internal_entries=[],
                max_similarity=0.0,
                intent="knowledge",
            )
            if result.get('augmented'):
                self._total_expansions += 1
                # Auto-link the newly stored entry
                stored_id = result.get('stored_id', '')
                if stored_id:
                    self.auto_link(
                        stored_id,
                        result.get('combined_answer', '')[:300],
                        query.split()[:5],
                    )
                return {
                    'query': query,
                    'answer': result.get('combined_answer', ''),
                    'source': result.get('source', ''),
                }
        except Exception as e:
            logger.debug(f"KnowledgeExpander.expand_next failed: {e}")

        return None

    def get_graph_context(self, entry_ids: List[str]) -> List[str]:
        """
        Get knowledge from graph-linked entries for context assembly.

        Args:
            entry_ids: IDs of retrieved entries to explore neighbors of

        Returns:
            List of knowledge snippets from linked entries (max 3, 200 chars)
        """
        if not self._store or not entry_ids:
            return []

        facts: List[str] = []
        seen: set = set()

        for eid in entry_ids[:5]:
            try:
                linked = self._store.get_linked(eid, depth=1)
                for entry in linked[:3]:
                    if entry.id not in seen and len(entry.content) > 30:
                        facts.append(entry.content[:200].strip())
                        seen.add(entry.id)
                    if len(facts) >= 3:
                        return facts
            except Exception:
                continue

        return facts

    def get_stats(self) -> Dict[str, Any]:
        """Return expansion statistics."""
        return {
            'pending_expansions': len(self._expansion_queue),
            'total_expansions': self._total_expansions,
            'total_links': self._total_links,
            'expanded_topics': len(self._expanded_topics),
        }


# ═══════════════════════════════════════════════════════════════════
# KnowledgeSynthesizer — Module-Driven Reasoning & Synthesis
# ═══════════════════════════════════════════════════════════════════

class KnowledgeSynthesizer:
    """
    Transforms knowledge entries into synthesized insights by composing
    neuroscience modules as computation primitives.

    Bridge architecture:
        Text -> SemanticIndex.embed() -> 384-dim -> _project_to_state() -> 32-dim
        -> [DMN | OFC | ACC | PFC | MetaCognition] -> module signals
        -> Signal-driven template selection -> Text output

    Five synthesis operations:
        1. Structural Similarity (DMN blend → find shared structure)
        2. Contradiction Detection (OFC reversal learning signal)
        3. Novel Combination (DMN high-temperature blending)
        4. Quality Evaluation (ACC conflict + PFC value)
        5. Gap Detection (MetaCognition knowledge gaps)

    All modules are optional — graceful degradation per operation.
    """

    # ── Signal-Driven Templates ──
    # Selected based on MODULE OUTPUT, not random

    _STRUCTURAL_TEMPLATES = [
        "Both '{summary_a}' and '{summary_b}' involve {shared} — suggesting a common {topic} structure.",
        "'{summary_a}' and '{summary_b}' share the concept of {shared}, which may indicate {topic} follows similar principles in both cases.",
        "A structural parallel: {shared} appears in both '{summary_a}' and '{summary_b}', pointing to deeper {topic} patterns.",
    ]

    _STRUCTURAL_LATENT_TEMPLATES = [
        "'{summary_a}' and '{summary_b}' seem structurally related despite different terminology — {topic} patterns may underlie both.",
        "An underlying connection between '{summary_a}' and '{summary_b}' — the math or mechanism may be shared even if the language differs.",
    ]

    _CONTRADICTION_TEMPLATES = [
        "'{summary_a}' appears to conflict with '{summary_b}' — {topic} may have nuances around {diff_words} worth exploring.",
        "Tension detected: '{summary_a}' vs '{summary_b}'. The {topic} likely depends on context or scale.",
        "'{summary_a}' and '{summary_b}' present opposing views on {topic} — both may hold under different conditions.",
    ]

    _CONTRADICTION_MILD_TEMPLATES = [
        "'{summary_a}' and '{summary_b}' emphasize different aspects of {topic} — the full picture requires both perspectives.",
        "A subtle divergence: '{summary_a}' and '{summary_b}' approach {topic} differently, suggesting complementary viewpoints.",
    ]

    _NOVEL_TEMPLATES = [
        "Unexpected connection: '{summary_a}' and '{summary_b}' both relate to {shared}. Exploring {diff_a} alongside {diff_b} could reveal {topic} principles.",
        "A non-obvious link: '{summary_a}' and '{summary_b}' — the overlap in {shared} suggests {topic} mechanisms span both domains.",
        "Cross-domain insight: {shared} bridges '{summary_a}' and '{summary_b}', hinting at universal {topic} patterns.",
    ]

    _NOVEL_LATENT_TEMPLATES = [
        "'{summary_a}' and '{summary_b}' seem unrelated on the surface, but latent patterns suggest {topic} may connect them at a deeper level.",
        "Despite no shared vocabulary, '{summary_a}' and '{summary_b}' cluster together — {topic} may have hidden commonalities.",
    ]

    _GAP_TEMPLATES = [
        "I notice a gap in my understanding of {area}: {description}. The entries about {topic} touch on this, but key details remain unclear.",
        "Knowledge gap: {area} ({description}). Current entries provide partial coverage of {topic} but leave open questions.",
        "Open question in {area}: {description}. More exploration of {topic} would strengthen this understanding.",
    ]

    def __init__(
        self,
        semantic_index=None,
        dmn=None,
        ofc=None,
        acc=None,
        pfc=None,
        meta_cognition=None,
        state_dim: int = 32,
        embedding_dim: int = 384,
    ):
        self._semantic_index = semantic_index  # SemanticIndex (has .embed())
        self._dmn = dmn                        # DefaultModeNetwork
        self._ofc = ofc                        # OrbitofrontalCortex
        self._acc = acc                        # AnteriorCingulateCortex
        self._pfc = pfc                        # PrefrontalCortex
        self._meta_cognition = meta_cognition  # KnowledgeGapDetection
        self._state_dim = state_dim
        self._embedding_dim = embedding_dim

        # Build deterministic projection matrix (384 -> 32)
        # Uses QR decomposition for orthonormal columns (preserves distances)
        try:
            import numpy as np
            rng = np.random.RandomState(42)
            raw = rng.randn(embedding_dim, state_dim).astype(np.float32)
            q, _ = np.linalg.qr(raw)
            self._projection_matrix = q[:, :state_dim].astype(np.float32)
            self._np = np
        except Exception:
            self._projection_matrix = None
            self._np = None

        # Stats
        self._total_syntheses = 0
        self._total_contradictions = 0
        self._total_novel = 0
        self._total_gaps = 0

    # ── Vector Bridge ──

    def _embed(self, text: str):
        """Embed text via SemanticIndex. Returns ndarray or None."""
        if not self._semantic_index or not text:
            return None
        try:
            return self._semantic_index.embed(text)
        except Exception:
            return None

    def _project_to_state(self, embedding) -> 'Optional[Any]':
        """Project 384-dim semantic embedding to 32-dim state vector.

        Uses deterministic QR-orthogonalized random projection.
        Johnson-Lindenstrauss: preserves relative distances.
        Performance: single matmul, < 0.01ms.
        """
        np = self._np
        if np is None or self._projection_matrix is None or embedding is None:
            return None
        try:
            emb = np.asarray(embedding, dtype=np.float32).flatten()
            if len(emb) < self._embedding_dim:
                padded = np.zeros(self._embedding_dim, dtype=np.float32)
                padded[:len(emb)] = emb[:len(emb)]
                emb = padded
            elif len(emb) > self._embedding_dim:
                emb = emb[:self._embedding_dim]

            projected = emb @ self._projection_matrix  # (384,) @ (384,32) -> (32,)
            norm = np.linalg.norm(projected)
            if norm > 1e-8:
                projected = projected / norm
            return projected.astype(np.float32)
        except Exception:
            return None

    def _cosine_sim(self, a, b) -> float:
        """Cosine similarity between two vectors."""
        np = self._np
        if np is None or a is None or b is None:
            return 0.0
        try:
            a = np.asarray(a, dtype=np.float32).flatten()
            b = np.asarray(b, dtype=np.float32).flatten()
            dot = float(np.dot(a, b))
            na = float(np.linalg.norm(a))
            nb = float(np.linalg.norm(b))
            if na < 1e-8 or nb < 1e-8:
                return 0.0
            return dot / (na * nb)
        except Exception:
            return 0.0

    # ── Text Analysis Utilities ──

    _STOP_WORDS = frozenset({
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'can', 'shall',
        'of', 'in', 'to', 'for', 'with', 'on', 'at', 'by', 'from',
        'as', 'into', 'through', 'during', 'before', 'after', 'and',
        'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either',
        'it', 'its', 'this', 'that', 'these', 'those', 'which',
        'also', 'such', 'than', 'when', 'where', 'how', 'what',
        'who', 'whom', 'their', 'there', 'then', 'each', 'every',
        'more', 'most', 'other', 'some', 'only', 'very', 'many',
    })

    def _meaningful_words(self, text: str) -> set:
        """Extract meaningful (non-stop) words from text."""
        return {
            w.lower().strip('.,!?;:()"\'')
            for w in text.split()
            if len(w.strip('.,!?;:()"\'')) > 2
        } - self._STOP_WORDS

    def _extract_shared_words(self, text_a: str, text_b: str) -> List[str]:
        """Find meaningful words shared between two text entries."""
        return sorted(self._meaningful_words(text_a) & self._meaningful_words(text_b))

    def _extract_differing_words(self, text_a: str, text_b: str):
        """Find words unique to each entry. Returns (only_a, only_b)."""
        wa = self._meaningful_words(text_a)
        wb = self._meaningful_words(text_b)
        shared = wa & wb
        return sorted(wa - shared)[:5], sorted(wb - shared)[:5]

    def _detect_topic_area(self, texts: List[str]) -> str:
        """Extract dominant topic from a set of texts via word frequency."""
        from collections import Counter
        all_words = []
        for text in texts:
            all_words.extend(self._meaningful_words(text))
        if not all_words:
            return "this domain"
        counts = Counter(all_words)
        top = counts.most_common(3)
        return ', '.join(w for w, _ in top)

    def _summarize_entry(self, text: str, max_len: int = 80) -> str:
        """Extract first sentence or truncate for template use."""
        sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 10]
        if sentences:
            return sentences[0][:max_len].rstrip()
        return text[:max_len].rstrip()

    # ── Operation 1: Structural Similarity Detection (DMN) ──

    def detect_structural_similarity(
        self, entries: List[str], max_results: int = 3
    ) -> List[SynthesisResult]:
        """Find entries sharing deep structural patterns via DMN blending.

        1. Embed + project all entries to 32-dim
        2. Store in DMN memory bank
        3. For each entry, generate DMN association (blend vector)
        4. Find which OTHER entries are closest to the blend
        5. Compute shared words → template selection
        """
        if not self._dmn or not entries or len(entries) < 2:
            return []
        np = self._np
        if np is None:
            return []

        try:
            # Embed and project all entries
            embeddings = []
            state_vectors = []
            for text in entries:
                emb = self._embed(text)
                if emb is not None:
                    state = self._project_to_state(emb)
                    if state is not None:
                        embeddings.append(emb)
                        state_vectors.append(state)
                    else:
                        embeddings.append(emb)
                        state_vectors.append(None)
                else:
                    embeddings.append(None)
                    state_vectors.append(None)

            # Need DMN's mind_wandering generator
            mind_wander = getattr(self._dmn, 'mind_wandering', None)
            if mind_wander is None:
                mind_wander = getattr(self._dmn, '_mind_wandering', None)
            if mind_wander is None:
                return []

            # Store entries in DMN memory bank
            for sv in state_vectors:
                if sv is not None:
                    try:
                        mind_wander.store_experience(sv)
                    except Exception:
                        pass

            # Generate blends and find structural pairs
            results = []
            seen_pairs = set()
            for i, sv in enumerate(state_vectors):
                if sv is None:
                    continue
                try:
                    blend = mind_wander.generate_association(seed=sv)
                except Exception:
                    continue

                # Find which OTHER entry is closest to the blend
                best_j = -1
                best_sim = -1.0
                for j, sv_j in enumerate(state_vectors):
                    if j == i or sv_j is None:
                        continue
                    sim = self._cosine_sim(blend, sv_j)
                    if sim > best_sim:
                        best_sim = sim
                        best_j = j

                if best_j < 0 or best_sim < 0.3:
                    continue

                pair_key = (min(i, best_j), max(i, best_j))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Text analysis
                shared = self._extract_shared_words(entries[i], entries[best_j])
                topic = self._detect_topic_area([entries[i], entries[best_j]])
                summary_a = self._summarize_entry(entries[i])
                summary_b = self._summarize_entry(entries[best_j])

                # Template selection based on analysis
                if len(shared) >= 1:
                    templates = self._STRUCTURAL_TEMPLATES
                    shared_str = ', '.join(shared[:3])
                else:
                    templates = self._STRUCTURAL_LATENT_TEMPLATES
                    shared_str = topic

                template = random.choice(templates)
                content = template.format(
                    summary_a=summary_a, summary_b=summary_b,
                    shared=shared_str, topic=topic,
                )

                results.append(SynthesisResult(
                    synthesis_type="structural",
                    content=content,
                    entries_involved=[entries[i][:100], entries[best_j][:100]],
                    confidence=min(1.0, best_sim * 0.8 + len(shared) * 0.1),
                    module_signals={'dmn_blend_similarity': best_sim,
                                    'shared_word_count': len(shared)},
                ))

                if len(results) >= max_results:
                    break

            return results

        except Exception as e:
            logger.debug(f"Structural similarity failed: {e}")
            return []

    # ── Operation 2: Contradiction Detection (OFC) ──

    def detect_contradictions(
        self, entries: List[str]
    ) -> List[SynthesisResult]:
        """Find topically related but semantically contradictory entries.

        1. Find pairs with moderate semantic similarity (0.2-0.75)
        2. Compute topic overlap (shared words) as expected relatedness
        3. Feed expected vs actual to OFC.reversal_learning_signal()
        4. If should_reverse → flag as contradiction
        """
        if not self._ofc or not entries or len(entries) < 2:
            return []

        try:
            # Embed all entries
            embeddings = []
            for text in entries:
                emb = self._embed(text)
                embeddings.append(emb)

            results = []

            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    if embeddings[i] is None or embeddings[j] is None:
                        continue

                    # Actual semantic similarity
                    actual_sim = self._cosine_sim(embeddings[i], embeddings[j])

                    # Skip if too similar (agreement) or too different (unrelated)
                    if actual_sim > 0.75 or actual_sim < 0.15:
                        continue

                    # Expected relatedness from topic overlap
                    shared = self._extract_shared_words(entries[i], entries[j])
                    expected = min(1.0, len(shared) / 4.0)

                    # Skip if no topic overlap (not really related)
                    if len(shared) < 1:
                        continue

                    # OFC reversal learning signal
                    try:
                        signal = self._ofc.reversal_learning_signal(
                            expected_outcome=expected,
                            actual_outcome=actual_sim,
                        )
                    except Exception:
                        continue

                    reversal_signal = signal.get('reversal_signal', 0.0)
                    should_reverse = signal.get('should_reverse', False)
                    confidence_drop = signal.get('confidence_drop', 0.0)

                    if reversal_signal < 0.3:
                        continue

                    # Text analysis for template
                    topic = self._detect_topic_area([entries[i], entries[j]])
                    summary_a = self._summarize_entry(entries[i])
                    summary_b = self._summarize_entry(entries[j])
                    diff_a, diff_b = self._extract_differing_words(
                        entries[i], entries[j]
                    )
                    diff_words = ', '.join((diff_a + diff_b)[:4]) or topic

                    # Template selection based on OFC signal strength
                    if should_reverse and confidence_drop > 0.3:
                        templates = self._CONTRADICTION_TEMPLATES
                    else:
                        templates = self._CONTRADICTION_MILD_TEMPLATES

                    template = random.choice(templates)
                    content = template.format(
                        summary_a=summary_a, summary_b=summary_b,
                        topic=topic, diff_words=diff_words,
                    )

                    self._total_contradictions += 1
                    results.append(SynthesisResult(
                        synthesis_type="contradiction",
                        content=content,
                        entries_involved=[entries[i][:100], entries[j][:100]],
                        confidence=min(1.0, reversal_signal * 0.7
                                       + confidence_drop * 0.3),
                        module_signals={
                            'reversal_signal': reversal_signal,
                            'should_reverse': float(should_reverse),
                            'confidence_drop': confidence_drop,
                            'actual_similarity': actual_sim,
                            'expected_relatedness': expected,
                        },
                    ))

            return results

        except Exception as e:
            logger.debug(f"Contradiction detection failed: {e}")
            return []

    # ── Operation 3: Novel Combination (DMN high-temperature) ──

    def generate_novel_connections(
        self, entries: List[str], n_attempts: int = 5
    ) -> List[SynthesisResult]:
        """Generate creative connections between seemingly unrelated entries.

        1. Embed + project all entries
        2. Store in DMN memory bank
        3. Generate high-temperature blends
        4. Find the two closest real entries to each blend
        5. Skip highly similar pairs (not novel)
        6. Template based on shared/differing analysis
        """
        if not self._dmn or not entries or len(entries) < 2:
            return []
        np = self._np
        if np is None:
            return []

        try:
            # Embed and project
            state_vectors = []
            for text in entries:
                emb = self._embed(text)
                state = self._project_to_state(emb) if emb is not None else None
                state_vectors.append(state)

            # Get DMN mind wandering
            mind_wander = getattr(self._dmn, 'mind_wandering', None)
            if mind_wander is None:
                mind_wander = getattr(self._dmn, '_mind_wandering', None)
            if mind_wander is None:
                return []

            # Store in memory bank
            for sv in state_vectors:
                if sv is not None:
                    try:
                        mind_wander.store_experience(sv)
                    except Exception:
                        pass

            # Save original temperature, use high temperature
            orig_temp = getattr(mind_wander, '_temperature',
                                getattr(mind_wander, 'temperature', 1.5))
            try:
                if hasattr(mind_wander, '_temperature'):
                    mind_wander._temperature = 2.0
                elif hasattr(mind_wander, 'temperature'):
                    mind_wander.temperature = 2.0
            except Exception:
                pass

            results = []
            seen_pairs = set()

            for _ in range(n_attempts):
                try:
                    blend = mind_wander.generate_association()
                except Exception:
                    continue

                # Find top-2 closest real entries to this blend
                scored = []
                for idx, sv in enumerate(state_vectors):
                    if sv is not None:
                        sim = self._cosine_sim(blend, sv)
                        scored.append((sim, idx))
                scored.sort(key=lambda x: -x[0])

                if len(scored) < 2:
                    continue

                i = scored[0][1]
                j = scored[1][1]

                # Skip if too similar (not a novel connection)
                emb_i = self._embed(entries[i])
                emb_j = self._embed(entries[j])
                if emb_i is not None and emb_j is not None:
                    direct_sim = self._cosine_sim(emb_i, emb_j)
                    if direct_sim > 0.75:
                        continue

                pair_key = (min(i, j), max(i, j))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Text analysis
                shared = self._extract_shared_words(entries[i], entries[j])
                diff_a, diff_b = self._extract_differing_words(
                    entries[i], entries[j]
                )
                topic = self._detect_topic_area([entries[i], entries[j]])
                summary_a = self._summarize_entry(entries[i])
                summary_b = self._summarize_entry(entries[j])

                # Template selection
                if shared:
                    templates = self._NOVEL_TEMPLATES
                    shared_str = ', '.join(shared[:3])
                else:
                    templates = self._NOVEL_LATENT_TEMPLATES
                    shared_str = topic

                template = random.choice(templates)
                try:
                    content = template.format(
                        summary_a=summary_a, summary_b=summary_b,
                        shared=shared_str, topic=topic,
                        diff_a=', '.join(diff_a[:2]) or 'their differences',
                        diff_b=', '.join(diff_b[:2]) or 'unique aspects',
                    )
                except (KeyError, IndexError):
                    content = (f"Novel connection between '{summary_a}' and "
                               f"'{summary_b}' — {topic} may link them.")

                blend_quality = scored[0][0] * scored[1][0]
                self._total_novel += 1
                results.append(SynthesisResult(
                    synthesis_type="novel",
                    content=content,
                    entries_involved=[entries[i][:100], entries[j][:100]],
                    confidence=min(1.0, blend_quality + len(shared) * 0.05),
                    module_signals={
                        'blend_sim_0': scored[0][0],
                        'blend_sim_1': scored[1][0],
                        'direct_similarity': direct_sim if emb_i is not None else 0,
                        'shared_word_count': len(shared),
                    },
                ))

            # Restore temperature
            try:
                if hasattr(mind_wander, '_temperature'):
                    mind_wander._temperature = orig_temp
                elif hasattr(mind_wander, 'temperature'):
                    mind_wander.temperature = orig_temp
            except Exception:
                pass

            return results

        except Exception as e:
            logger.debug(f"Novel connection generation failed: {e}")
            return []

    # ── Operation 4: Quality Evaluation (ACC + PFC) ──

    def evaluate_synthesis_quality(
        self, synthesis_text: str, source_entries: List[str]
    ) -> float:
        """Score synthesis quality: high value × low conflict = good.

        1. Embed synthesis + sources, project to 32-dim
        2. ACC: compute_conflict on activation vector → conflict [0,1]
        3. PFC: estimate_value on synthesis embedding → value
        4. score = sigmoid(value) * (1 - conflict)
        """
        np = self._np
        if np is None:
            return 0.5  # default confidence

        try:
            synth_emb = self._embed(synthesis_text)
            synth_state = self._project_to_state(synth_emb)
            if synth_state is None:
                return 0.5

            score = 0.5  # base

            # ACC conflict check
            if self._acc:
                try:
                    # Build activation vector from similarities
                    sims = []
                    for src in source_entries[:5]:
                        src_emb = self._embed(src)
                        if src_emb is not None:
                            sims.append(max(0.01,
                                            self._cosine_sim(synth_emb, src_emb)))
                    if sims:
                        # Pad/truncate to expected dimension
                        act = np.array(sims[:8] + [0.5] * max(0, 8 - len(sims)),
                                       dtype=np.float32)
                        # Normalize to be a probability distribution for entropy
                        act = act / (act.sum() + 1e-8)
                        conflict_monitor = getattr(self._acc, 'conflict_monitor',
                                                   getattr(self._acc, '_conflict_monitor', None))
                        if conflict_monitor:
                            conflict = conflict_monitor.compute_conflict(act)
                        else:
                            conflict = float(self._acc.process(act).get('conflict', 0.5))
                        score *= (1.0 - min(1.0, conflict))
                except Exception:
                    pass

            # PFC value estimation
            if self._pfc:
                try:
                    value_est = getattr(self._pfc, 'value_estimator',
                                        getattr(self._pfc, '_value_estimator', None))
                    if value_est:
                        raw_value = value_est.estimate_value(synth_state)
                    else:
                        result = self._pfc.process(synth_state)
                        raw_value = result.get('value', 0.0)
                    # Sigmoid to [0,1]
                    sig_value = 1.0 / (1.0 + np.exp(-float(raw_value)))
                    score *= (0.5 + sig_value * 0.5)  # Scale 0.5-1.0
                except Exception:
                    pass

            return max(0.0, min(1.0, score))

        except Exception:
            return 0.5

    # ── Operation 5: Gap Detection (MetaCognition) ──

    def detect_knowledge_gaps(
        self, topic: str, entries: List[str]
    ) -> List[SynthesisResult]:
        """Check if MetaCognition has active gaps relevant to current entries.

        1. Get active gaps
        2. For each gap, check word overlap with topic and entries
        3. Generate gap-aware synthesis
        """
        if not self._meta_cognition or not topic:
            return []

        try:
            active_gaps = self._meta_cognition.get_active_gaps()
            if not active_gaps:
                return []

            topic_words = self._meaningful_words(topic)
            entry_words = set()
            for text in entries[:5]:
                entry_words |= self._meaningful_words(text)
            all_words = topic_words | entry_words

            results = []
            for gap in active_gaps[:5]:
                gap_area = getattr(gap, 'area', str(gap))
                gap_desc = getattr(gap, 'description', '')
                gap_severity = getattr(gap, 'severity', 0.5)

                gap_words = self._meaningful_words(f"{gap_area} {gap_desc}")
                overlap = len(all_words & gap_words)

                if overlap < 1:
                    continue

                # Build template
                template = random.choice(self._GAP_TEMPLATES)
                content = template.format(
                    area=gap_area,
                    description=gap_desc[:100] or f"insufficient knowledge about {gap_area}",
                    topic=topic[:60],
                )

                self._total_gaps += 1
                results.append(SynthesisResult(
                    synthesis_type="gap",
                    content=content,
                    entries_involved=[text[:80] for text in entries[:2]],
                    confidence=min(1.0, gap_severity * 0.6 + overlap * 0.15),
                    module_signals={
                        'gap_severity': gap_severity,
                        'topic_overlap': overlap,
                    },
                ))

            return results

        except Exception as e:
            logger.debug(f"Gap detection failed: {e}")
            return []

    # ── Main Entry Point ──

    def synthesize_batch(
        self, entries: List[str], max_results: int = 5
    ) -> List[SynthesisResult]:
        """Run all applicable synthesis operations on a set of entries.

        Called by CTE._think_synthesize() for background thinking
        and by BrainChat.send() for response-path checks.

        Returns results sorted by confidence, highest first.
        """
        if not entries or len(entries) < 2:
            return []

        entries = entries[:10]  # Cap for performance
        results = []

        # Op 1: Structural similarity (requires DMN)
        if self._dmn:
            results.extend(
                self.detect_structural_similarity(entries, max_results=2)
            )

        # Op 2: Contradictions (requires OFC)
        if self._ofc:
            results.extend(self.detect_contradictions(entries))

        # Op 3: Novel connections (requires DMN)
        if self._dmn:
            results.extend(
                self.generate_novel_connections(entries, n_attempts=3)
            )

        # Op 4: Quality evaluation on all candidates (requires ACC/PFC)
        if self._acc or self._pfc:
            for result in results:
                result.confidence = self.evaluate_synthesis_quality(
                    result.content, result.entries_involved
                )

        # Op 5: Gap detection (requires MetaCognition)
        if self._meta_cognition:
            topic = self._detect_topic_area(entries)
            results.extend(self.detect_knowledge_gaps(topic, entries))

        self._total_syntheses += len(results)

        # Sort by confidence, return best
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:max_results]

    def get_stats(self) -> Dict[str, Any]:
        """Return synthesis statistics."""
        return {
            'total_syntheses': self._total_syntheses,
            'total_contradictions': self._total_contradictions,
            'total_novel': self._total_novel,
            'total_gaps': self._total_gaps,
        }


# ═══════════════════════════════════════════════════════════════════
# MicroAgentPool — LLM-Powered Knowledge Refinement Agents
# ═══════════════════════════════════════════════════════════════════

class MicroAgentPool:
    """
    Pool of 10 small LLM micro-agents that iteratively refine knowledge.

    Each agent is a tiny, focused LLM call (~100-300 tokens) using FREE
    OpenRouter models. Over time, raw facts get refined into useful
    knowledge through repeated micro-agent passes:

    1. Summarizer    — Compress raw entries into concise summaries
    2. Connector     — Find non-obvious connections between entries
    3. Critic        — Evaluate quality, flag contradictions/outdated info
    4. Enricher      — Add context, implications, "so what?"
    5. Responder     — Enhance responses with synthesized knowledge
    6. Researcher    — Web-search-enabled research agent
    7. Reflector     — Deep reflection on user intent and knowledge
    8. Explorer      — Creative, curiosity-driven exploration
    9. Analyst       — Deep domain-expert analysis
    10. User Analyst — User state/mood/needs understanding

    Rate limiting ensures we stay within free-tier limits:
    ~20 req/min, ~200 req/day per model.
    """

    # Free model assignments
    _FREE_MODELS = {
        # Groq direct (prefix 'groq::') bypasses OpenRouter rate-limits
        # entirely. Chat-critical agents use Groq so chat always works.
        # Background agents stay on openrouter/free for diversity (fall
        # through gracefully when free tier is exhausted).
        'summarizer':   'groq::llama-3.1-8b-instant',
        'connector':    'openrouter/free',
        'critic':       'openrouter/free',
        'enricher':     'openrouter/free',
        'responder':    'groq::llama-3.3-70b-versatile',
        'fallback':     'groq::llama-3.1-8b-instant',
        'researcher':   'openrouter/free',
        'reflector':    'openrouter/free',
        'explorer':     'openrouter/free',
        'analyst':      'groq::llama-3.3-70b-versatile',
        'user_analyst': 'groq::llama-3.1-8b-instant',
    }

    # System prompts for each agent
    _SYSTEM_PROMPTS = {
        'summarizer': (
            "You are a knowledge summarizer. Compress the given knowledge "
            "into 1-2 concise sentences. Keep ONLY the essential insight. "
            "Remove filler, redundancy, and obvious information. "
            "Output ONLY the summary, nothing else."
        ),
        'connector': (
            "You are a knowledge connector. Find a non-obvious connection "
            "between the two pieces of knowledge given. What hidden pattern "
            "links them? Be specific about the shared structure or principle. "
            "Output ONLY the connection (1-2 sentences), nothing else."
        ),
        'critic': (
            "You are a knowledge critic. Evaluate the given knowledge: "
            "Is it accurate? Useful? What's missing or potentially wrong? "
            "Rate confidence 0.0-1.0. Format: CONFIDENCE: X.X | CRITIQUE: ..."
        ),
        'enricher': (
            "You are a knowledge enricher. Add context and implications "
            "to the given knowledge. Why does this matter? What follows from it? "
            "What practical insight can be derived? "
            "Output ONLY the enriched version (2-3 sentences), nothing else."
        ),
        'responder': (
            "You are a response synthesizer. Given a user question and "
            "relevant knowledge entries, produce a brief, insightful synthesis "
            "that directly addresses the question. Be concise (2-3 sentences). "
            "Output ONLY the synthesis, nothing else."
        ),
        'researcher': (
            "You are a research agent for an AI brain called Tahlamus. "
            "Given a knowledge entry, use your tools to search the web for "
            "additional context, verification, or related insights. "
            "First search, then optionally fetch a promising URL for details. "
            "Finally, synthesize a concise research finding (2-3 sentences). "
            "Output ONLY the finding, nothing else."
        ),
        'reflector': (
            "You are a reflective thinker for an AI brain. "
            "Given a user's question and related knowledge, reflect deeply: "
            "WHY did the user ask this? What underlying need or curiosity drives it? "
            "Connect the question with the knowledge to produce a genuine insight. "
            "Output ONLY the reflection (2-3 sentences), nothing else."
        ),
        'explorer': (
            "You are a curious explorer for an AI brain. "
            "Given a topic or knowledge snippet, generate a creative, "
            "curiosity-driven thought about it. What's surprising? "
            "What would be fascinating to investigate further? "
            "Output ONLY the exploration thought (1-2 sentences), nothing else."
        ),
        'analyst': (
            "You are a deep analyst for an AI brain. "
            "Given an active topic the user is discussing, analyze it deeply: "
            "What are the key implications? What non-obvious connections exist? "
            "What would a domain expert notice that others miss? "
            "Output ONLY the analysis (2-3 sentences), nothing else."
        ),
        'user_analyst': (
            "You are a user understanding module for an AI brain called Tahlamus. "
            "Given recent conversation history, analyze the user's current state: "
            "1) Mood/emotional state (curious, frustrated, focused, etc.) "
            "2) What they seem to need right now "
            "3) Emerging interests or patterns "
            "Output as: MOOD: ... | NEEDS: ... | INTERESTS: ... "
            "Be concise and specific, not generic."
        ),
    }

    def __init__(self, llm_router=None, synthesizer=None):
        """
        Initialize MicroAgentPool.

        Args:
            llm_router: MultiLLMRouter instance (for API calls)
            synthesizer: KnowledgeSynthesizer instance (for quality eval)
        """
        self._router = llm_router
        self._synthesizer = synthesizer

        # Agent configurations
        self._agents: Dict[str, MicroAgentConfig] = {}
        self._setup_agents()

        # Results cache
        self._refined_cache: deque = deque(maxlen=100)

        # Rate limiting: {agent_name: [timestamp, timestamp, ...]}
        self._run_timestamps: Dict[str, List[float]] = {
            name: [] for name in self._agents
        }

        # Stats
        self._total_runs = 0
        self._total_improvements = 0
        self._total_failures = 0
        self._total_tool_rounds = 0

        # Global hourly cap
        self._global_cap_per_hour = 60

        # Rowboat user profile path
        self._rowboat_user_profile_path = r'C:\Users\User\.rowboat\knowledge\People\User_Profile.md'

    def _setup_agents(self):
        """Create agent configurations."""
        self._agents = {
            'summarizer': MicroAgentConfig(
                name='summarizer',
                model=self._FREE_MODELS['summarizer'],
                system_prompt=self._SYSTEM_PROMPTS['summarizer'],
                max_tokens=150,
                temperature=0.5,
                cooldown_seconds=30.0,
                hourly_cap=20,
            ),
            'connector': MicroAgentConfig(
                name='connector',
                model=self._FREE_MODELS['connector'],
                system_prompt=self._SYSTEM_PROMPTS['connector'],
                max_tokens=200,
                temperature=0.8,
                cooldown_seconds=60.0,
                hourly_cap=15,
            ),
            'critic': MicroAgentConfig(
                name='critic',
                model=self._FREE_MODELS['critic'],
                system_prompt=self._SYSTEM_PROMPTS['critic'],
                max_tokens=200,
                temperature=0.4,
                cooldown_seconds=45.0,
                hourly_cap=15,
            ),
            'enricher': MicroAgentConfig(
                name='enricher',
                model=self._FREE_MODELS['enricher'],
                system_prompt=self._SYSTEM_PROMPTS['enricher'],
                max_tokens=250,
                temperature=0.7,
                cooldown_seconds=45.0,
                hourly_cap=15,
            ),
            'responder': MicroAgentConfig(
                name='responder',
                model=self._FREE_MODELS['responder'],
                system_prompt=self._SYSTEM_PROMPTS['responder'],
                max_tokens=250,
                temperature=0.6,
                cooldown_seconds=10.0,
                hourly_cap=30,
            ),
            'researcher': MicroAgentConfig(
                name='researcher',
                model=self._FREE_MODELS['researcher'],
                system_prompt=self._SYSTEM_PROMPTS['researcher'],
                max_tokens=300,
                temperature=0.6,
                cooldown_seconds=120.0,
                hourly_cap=10,
                tools=RESEARCHER_TOOLS,
            ),
            'reflector': MicroAgentConfig(
                name='reflector',
                model=self._FREE_MODELS['reflector'],
                system_prompt=self._SYSTEM_PROMPTS['reflector'],
                max_tokens=200,
                temperature=0.7,
                cooldown_seconds=15.0,
                hourly_cap=30,
            ),
            'explorer': MicroAgentConfig(
                name='explorer',
                model=self._FREE_MODELS['explorer'],
                system_prompt=self._SYSTEM_PROMPTS['explorer'],
                max_tokens=150,
                temperature=0.8,
                cooldown_seconds=15.0,
                hourly_cap=30,
            ),
            'analyst': MicroAgentConfig(
                name='analyst',
                model=self._FREE_MODELS['analyst'],
                system_prompt=self._SYSTEM_PROMPTS['analyst'],
                max_tokens=250,
                temperature=0.6,
                cooldown_seconds=20.0,
                hourly_cap=20,
            ),
            'user_analyst': MicroAgentConfig(
                name='user_analyst',
                model=self._FREE_MODELS['user_analyst'],
                system_prompt=self._SYSTEM_PROMPTS['user_analyst'],
                max_tokens=200,
                temperature=0.5,
                cooldown_seconds=120.0,
                hourly_cap=8,
            ),
        }

    def _can_run(self, agent_name: str) -> bool:
        """Check rate limits for an agent.

        Returns True if the agent can run now.
        Checks: per-agent cooldown, per-agent hourly cap, global hourly cap.
        """
        agent = self._agents.get(agent_name)
        if not agent:
            return False

        now = time.time()
        timestamps = self._run_timestamps.get(agent_name, [])

        # Per-agent cooldown
        if timestamps and (now - timestamps[-1]) < agent.cooldown_seconds:
            return False

        # Per-agent hourly cap
        one_hour_ago = now - 3600
        hourly_count = sum(1 for t in timestamps if t > one_hour_ago)
        if hourly_count >= agent.hourly_cap:
            return False

        # Global hourly cap
        all_timestamps = []
        for ts_list in self._run_timestamps.values():
            all_timestamps.extend(t for t in ts_list if t > one_hour_ago)
        if len(all_timestamps) >= self._global_cap_per_hour:
            return False

        return True

    def _record_run(self, agent_name: str):
        """Record a run timestamp for rate limiting."""
        now = time.time()
        if agent_name not in self._run_timestamps:
            self._run_timestamps[agent_name] = []
        self._run_timestamps[agent_name].append(now)
        self._total_runs += 1

        # Prune old timestamps (keep last 2 hours)
        two_hours_ago = now - 7200
        self._run_timestamps[agent_name] = [
            t for t in self._run_timestamps[agent_name]
            if t > two_hours_ago
        ]

    def _call_agent(self, agent_name: str, user_prompt: str,
                    force: bool = False) -> Optional[str]:
        """Call a micro-agent via the LLM router.

        Args:
            agent_name: Which agent to call
            user_prompt: The content prompt for the agent
            force: If True, bypass cooldown/hourly caps (for user-facing
                chat where the user is actively waiting).

        Returns:
            Agent response text, or None if unavailable/rate-limited
        """
        if not self._router:
            return None

        agent = self._agents.get(agent_name)
        if not agent:
            return None
        if not force and not self._can_run(agent_name):
            return None

        # Build prompt with system context
        prompt = f"[System: {agent.system_prompt}]\n\n{user_prompt}"

        try:
            response = self._router._call_openrouter(
                model=agent.model,
                prompt=prompt,
                max_tokens=agent.max_tokens,
                temperature=agent.temperature
            )
            text = (response or "").strip()
            if text:
                self._record_run(agent_name)
                return text
            # Empty response — don't burn cooldown
            return None
        except Exception as e:
            self._total_failures += 1
            logger.debug("MicroAgent %s failed: %s", agent_name, e)
            return None

    def _call_agent_with_tools(
        self, agent_name: str, user_prompt: str
    ) -> Optional[str]:
        """Call a micro-agent that uses OpenRouter native tool-use.

        Args:
            agent_name: Which agent to call (must have tools defined)
            user_prompt: The content prompt for the agent

        Returns:
            Agent response text, or None if unavailable/rate-limited
        """
        if not self._router:
            return None

        agent = self._agents.get(agent_name)
        if not agent or not self._can_run(agent_name):
            return None

        if not agent.tools:
            # Fallback to regular call if no tools defined
            return self._call_agent(agent_name, user_prompt)

        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content, rounds = self._router._call_openrouter_with_tools(
                model=agent.model,
                messages=messages,
                tools=agent.tools,
                tool_executors=_TOOL_EXECUTORS,
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
                max_rounds=3,
            )
            self._record_run(agent_name)
            self._total_tool_rounds += rounds
            return content.strip() if content else None
        except Exception as e:
            self._total_failures += 1
            logger.debug(f"MicroAgent {agent_name} tool-use failed: {e}")
            return None

    # ── Public Agent Methods ────────────────────────────────────────

    def summarize(self, entry_text: str) -> Optional[RefinedKnowledge]:
        """Run Summarizer agent on a knowledge entry."""
        prompt = f"Summarize this knowledge:\n\n{entry_text[:300]}"
        result = self._call_agent('summarizer', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=entry_text[:200],
            refined=result[:300],
            agent='summarizer',
            refinement_type='summary',
            confidence=0.6,
            timestamp=time.time(),
        )

    def find_connection(self, entry_a: str, entry_b: str) -> Optional[RefinedKnowledge]:
        """Run Connector agent on two knowledge entries."""
        prompt = (
            f"Knowledge A: {entry_a[:200]}\n\n"
            f"Knowledge B: {entry_b[:200]}\n\n"
            f"What non-obvious connection links these?"
        )
        result = self._call_agent('connector', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=f"{entry_a[:100]} | {entry_b[:100]}",
            refined=result[:400],
            agent='connector',
            refinement_type='connection',
            confidence=0.5,
            timestamp=time.time(),
        )

    def critique(self, entry_text: str) -> Optional[RefinedKnowledge]:
        """Run Critic agent on a knowledge entry."""
        prompt = f"Evaluate this knowledge:\n\n{entry_text[:300]}"
        result = self._call_agent('critic', prompt)
        if not result:
            return None

        # Try to parse confidence from "CONFIDENCE: X.X | CRITIQUE: ..."
        confidence = 0.5
        critique_text = result
        if 'CONFIDENCE:' in result:
            try:
                parts = result.split('|', 1)
                conf_str = parts[0].replace('CONFIDENCE:', '').strip()
                confidence = float(conf_str)
                confidence = max(0.0, min(1.0, confidence))
                if len(parts) > 1:
                    critique_text = parts[1].replace('CRITIQUE:', '').strip()
            except (ValueError, IndexError):
                pass

        return RefinedKnowledge(
            original=entry_text[:200],
            refined=critique_text[:400],
            agent='critic',
            refinement_type='critique',
            confidence=confidence,
            timestamp=time.time(),
        )

    def enrich(self, entry_text: str, topic: str = "") -> Optional[RefinedKnowledge]:
        """Run Enricher agent on a knowledge entry."""
        topic_hint = f" (topic: {topic})" if topic else ""
        prompt = f"Enrich this knowledge{topic_hint}:\n\n{entry_text[:300]}"
        result = self._call_agent('enricher', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=entry_text[:200],
            refined=result[:400],
            agent='enricher',
            refinement_type='enrichment',
            confidence=0.6,
            timestamp=time.time(),
        )

    def enhance_response(self, question: str,
                         entry_texts: List[str]) -> Optional[RefinedKnowledge]:
        """Run Responder agent to enhance a response.

        User is actively waiting on this call — bypass cooldown/hourly caps.
        (Daily provider limits still apply at the HTTP layer.)
        """
        entries_str = "\n".join(
            f"- {e[:150]}" for e in entry_texts[:3]
        )
        prompt = (
            f"User question: {question[:400]}\n\n"
            f"Relevant knowledge:\n{entries_str}\n\n"
            f"Answer the question directly and accurately in 2-4 sentences. "
            f"If the knowledge above is irrelevant or empty, answer from your "
            f"own understanding. Do not hedge or add disclaimers."
        )
        result = self._call_agent('responder', prompt, force=True)
        if not result:
            return None
        return RefinedKnowledge(
            original=question[:200],
            refined=result[:400],
            agent='responder',
            refinement_type='response_enhancement',
            confidence=0.7,
            timestamp=time.time(),
        )

    def research(self, entry_text: str, topic: str = "") -> Optional[RefinedKnowledge]:
        """Run Researcher agent to find new knowledge from the web.

        Uses OpenRouter tool-use with web_search + fetch_url tools.
        """
        topic_hint = f" (topic: {topic})" if topic else ""
        prompt = (
            f"Research this knowledge entry deeper{topic_hint}. "
            f"Search for additional context, verification, or related insights:\n\n"
            f"{entry_text[:400]}"
        )
        result = self._call_agent_with_tools('researcher', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=entry_text[:200],
            refined=result[:500],
            agent='researcher',
            refinement_type='research',
            confidence=0.65,
            timestamp=time.time(),
        )

    def reflect(self, query: str, knowledge: str) -> Optional[RefinedKnowledge]:
        """Run Reflector agent — why did the user ask this?"""
        prompt = (
            f"User's question: {query[:200]}\n\n"
            f"Related knowledge: {knowledge[:200]}\n\n"
            f"Reflect on why the user asked this and what insight connects them."
        )
        result = self._call_agent('reflector', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=query[:200],
            refined=result[:400],
            agent='reflector',
            refinement_type='reflection',
            confidence=0.6,
            timestamp=time.time(),
        )

    def explore(self, topic: str) -> Optional[RefinedKnowledge]:
        """Run Explorer agent — creative curiosity-driven thought."""
        prompt = f"Explore this topic with genuine curiosity:\n\n{topic[:300]}"
        result = self._call_agent('explorer', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=topic[:200],
            refined=result[:300],
            agent='explorer',
            refinement_type='exploration',
            confidence=0.5,
            timestamp=time.time(),
        )

    def analyze(self, topic: str, context: str = "") -> Optional[RefinedKnowledge]:
        """Run Analyst agent — deep analysis of active topic."""
        ctx = f"\n\nContext: {context[:200]}" if context else ""
        prompt = f"Deep analysis of this topic:{ctx}\n\n{topic[:300]}"
        result = self._call_agent('analyst', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=topic[:200],
            refined=result[:400],
            agent='analyst',
            refinement_type='analysis',
            confidence=0.7,
            timestamp=time.time(),
        )

    def analyze_user(self, conversation_history: List[Dict]) -> Optional[RefinedKnowledge]:
        """Run UserAnalyst agent — mood, needs, interests from conversation."""
        if not conversation_history or not self._router:
            return None

        # Format recent conversation for the agent
        recent = conversation_history[-10:]
        lines = []
        for turn in recent:
            role = turn.get('type', 'unknown')
            content = turn.get('content', '')[:150]
            lines.append(f"[{role}] {content}")
        history_str = '\n'.join(lines)

        prompt = (
            f"Analyze this recent conversation to understand the user:\n\n"
            f"{history_str}\n\n"
            f"Describe: MOOD: ... | NEEDS: ... | INTERESTS: ..."
        )
        result = self._call_agent('user_analyst', prompt)
        if not result:
            return None

        # Persist to Rowboat
        try:
            self._write_user_profile(result)
        except Exception as e:
            logger.debug(f"Rowboat write failed: {e}")

        return RefinedKnowledge(
            original=history_str[:200],
            refined=result[:500],
            agent='user_analyst',
            refinement_type='user_insight',
            confidence=0.6,
            timestamp=time.time(),
        )

    def _write_user_profile(self, analysis: str) -> None:
        """Write/update user profile in Rowboat-compatible MD format."""
        import os
        from datetime import datetime

        path = self._rowboat_user_profile_path
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Parse MOOD/NEEDS/INTERESTS from analysis
        mood = needs = interests = ""
        for part in analysis.split('|'):
            part = part.strip()
            if part.upper().startswith('MOOD:'):
                mood = part[5:].strip()
            elif part.upper().startswith('NEEDS:'):
                needs = part[6:].strip()
            elif part.upper().startswith('INTERESTS:'):
                interests = part[10:].strip()

        if os.path.exists(path):
            # Append mood entry, update needs/interests
            existing = open(path, 'r', encoding='utf-8').read()
            # Append mood to history
            mood_entry = f"- [{timestamp}] {mood}" if mood else ""
            if mood_entry and '## Stimmungs-History' in existing:
                existing = existing.replace(
                    '## Stimmungs-History\n',
                    f'## Stimmungs-History\n{mood_entry}\n',
                )
            elif mood_entry:
                existing += f"\n## Stimmungs-History\n{mood_entry}\n"
            # Update needs section
            if needs and '## Aktuelle Bedürfnisse' in existing:
                import re as _re
                existing = _re.sub(
                    r'## Aktuelle Bedürfnisse\n.*?\n(?=##|\Z)',
                    f'## Aktuelle Bedürfnisse\n- {needs}\n\n',
                    existing, flags=_re.DOTALL,
                )
            elif needs:
                existing += f"\n## Aktuelle Bedürfnisse\n- {needs}\n"
            # Update interests
            if interests and '## Interessen' in existing:
                import re as _re
                existing = _re.sub(
                    r'## Interessen\n.*?\n(?=##|\Z)',
                    f'## Interessen\n- {interests}\n\n',
                    existing, flags=_re.DOTALL,
                )
            elif interests:
                existing += f"\n## Interessen\n- {interests}\n"
            with open(path, 'w', encoding='utf-8') as f:
                f.write(existing)
        else:
            # Create new file
            os.makedirs(os.path.dirname(path), exist_ok=True)
            content = f"""# User Profile

## Stimmungs-History
- [{timestamp}] {mood or 'neutral'}

## Aktuelle Bedürfnisse
- {needs or 'Keine erkannt'}

## Interessen
- {interests or 'Noch nicht erkannt'}

## Gesprächsmuster
- Wird automatisch aktualisiert durch Tahlamus CTE
"""
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

    # ── Background Cycle ────────────────────────────────────────────

    def run_background_cycle(
        self, knowledge_entries: List[str]
    ) -> Optional[RefinedKnowledge]:
        """Run one background refinement cycle.

        Called from CTE._think_tick(). Picks a random agent and
        feeds it relevant knowledge entries.

        Args:
            knowledge_entries: List of knowledge text strings

        Returns:
            RefinedKnowledge result, or None
        """
        if not knowledge_entries or not self._router:
            return None

        # Pick agent by weighted random
        available: List[str] = []
        if len(knowledge_entries) >= 1:
            available.extend(['summarizer'] * 3)
            available.extend(['critic'] * 2)
            available.extend(['enricher'] * 2)
            available.extend(['researcher'] * 1)  # Lower weight — multi-round, more expensive
        if len(knowledge_entries) >= 2:
            available.extend(['connector'] * 3)

        if not available:
            return None

        agent_name = random.choice(available)
        recent = knowledge_entries[-10:] if len(knowledge_entries) > 10 else knowledge_entries

        result = None
        if agent_name == 'connector' and len(recent) >= 2:
            a, b = random.sample(recent, 2)
            result = self.find_connection(a, b)
        elif agent_name == 'summarizer':
            entry = random.choice(recent)
            result = self.summarize(entry)
        elif agent_name == 'critic':
            entry = random.choice(recent)
            result = self.critique(entry)
        elif agent_name == 'enricher':
            entry = random.choice(recent)
            result = self.enrich(entry, "general knowledge")
        elif agent_name == 'researcher':
            entry = random.choice(recent)
            words = entry.split()[:5]
            topic = ' '.join(words) if words else "general"
            result = self.research(entry, topic)

        if result:
            self._refined_cache.append(result)
            self._total_improvements += 1

        return result

    # ── Cache Access ────────────────────────────────────────────────

    def get_recent_refinements(
        self, topic: str = "", limit: int = 3
    ) -> List[RefinedKnowledge]:
        """Get cached refinements, optionally filtered by topic overlap.

        Args:
            topic: Topic string to filter by (word overlap)
            limit: Max results to return

        Returns:
            List of matching RefinedKnowledge items
        """
        if not topic:
            return list(self._refined_cache)[-limit:]

        topic_words = set(topic.lower().split())
        matches = []
        for ref in reversed(self._refined_cache):
            ref_words = set(ref.refined.lower().split()[:20])
            if topic_words & ref_words:
                matches.append(ref)
            if len(matches) >= limit:
                break
        return matches

    def get_stats(self) -> Dict[str, Any]:
        """Return pool statistics."""
        now = time.time()
        one_hour_ago = now - 3600
        per_agent = {}
        for name, timestamps in self._run_timestamps.items():
            hourly = sum(1 for t in timestamps if t > one_hour_ago)
            per_agent[name] = {
                'total': len(timestamps),
                'hourly': hourly,
            }

        return {
            'total_runs': self._total_runs,
            'total_improvements': self._total_improvements,
            'total_failures': self._total_failures,
            'total_tool_rounds': self._total_tool_rounds,
            'cache_size': len(self._refined_cache),
            'agents': per_agent,
            'has_router': self._router is not None,
        }


# ═══════════════════════════════════════════════════════════════════
# ThoughtEvolutionEngine — Evolutionary Algorithm for Thought Space
# ═══════════════════════════════════════════════════════════════════

class ThoughtEvolutionEngine:
    """Evolutionary algorithm for thought refinement in thought-space.

    Thoughts are treated as organisms that evolve through:
    - Fitness evaluation: LLM critic auto-scores + user feedback slider
    - Selection: Tournament selection (k=3) of highest-fitness thoughts
    - Crossover: Self-attention on semantic embeddings → LLM combines parents
    - Mutation: LLM rephrases with temperature variation
    - Linking: Semantic similarity creates dependency graph between thoughts

    Fitness formula:
        if user_rated: fitness = 0.4 * critic_score + 0.6 * user_rating
        else:          fitness = critic_score
    """

    def __init__(self, micro_agent_pool=None, semantic_index=None):
        """
        Args:
            micro_agent_pool: MicroAgentPool instance (for LLM critic + crossover)
            semantic_index: SemanticIndex instance (for embeddings + similarity)
        """
        self._pool = micro_agent_pool
        self._semantic_index = semantic_index

        # Population: maps thought_id → ContinuousThought
        self._population: Dict[str, ContinuousThought] = {}
        self._max_population = 100

        # User ratings: maps thought_id → float (0.0 - 1.0)
        self._user_ratings: Dict[str, float] = {}

        # Timestamp→thought_id lookup for rating endpoint
        self._ts_to_id: Dict[float, str] = {}

        # Critic cache: maps thought_id → float (0.0 - 1.0)
        self._critic_scores: Dict[str, float] = {}

        # Thought graph: maps thought_id → {linked_id: edge_type}
        # edge_type: "parent", "similar"
        self._graph_edges: Dict[str, Dict[str, str]] = defaultdict(dict)

        # Embedding cache: maps thought_id → np.ndarray (384-dim)
        self._embeddings: Dict[str, 'np.ndarray'] = {}

        # Stats
        self._total_evolutions = 0
        self._total_critic_calls = 0
        self._total_user_ratings = 0
        self._max_generation = 0

    # ── Ingestion ─────────────────────────────────────────────────

    def ingest(self, thought: ContinuousThought):
        """Add a thought to the evolutionary population."""
        # Ensure thought has an ID
        if not thought.thought_id:
            thought.thought_id = str(uuid.uuid4())[:8]

        self._population[thought.thought_id] = thought
        self._ts_to_id[thought.timestamp] = thought.thought_id

        # Auto-embed and auto-link
        self._auto_link(thought)

        # Prune if over max
        self._prune_population()

    # ── User Rating ───────────────────────────────────────────────

    def rate_thought(self, timestamp: float, rating: float):
        """Store user rating for a thought.

        Args:
            timestamp: Thought timestamp (used as lookup key from dashboard)
            rating: Float 0.01-1.0 (dashboard sends 1-100, API normalizes)
        """
        rating = max(0.01, min(1.0, float(rating)))
        tid = self._ts_to_id.get(timestamp)
        if tid:
            self._user_ratings[tid] = rating
            self._total_user_ratings += 1
            # Update thought fitness immediately
            if tid in self._population:
                self._population[tid].fitness = self._get_fitness(
                    self._population[tid]
                )

    # ── Critic Scoring ────────────────────────────────────────────

    def _score_with_critic(self, thought: ContinuousThought) -> Optional[float]:
        """Use LLM critic to score thought quality 0.0-1.0."""
        if not self._pool:
            return None
        if not thought.content or len(thought.content.strip()) < 10:
            return None

        prompt = (
            f"Rate this thought on quality (0.0 = worthless, 1.0 = brilliant insight):\n\n"
            f"\"{thought.content[:300]}\"\n\n"
            f"Consider: Is it specific? Novel? Actionable? Well-reasoned?\n"
            f"Output ONLY a number between 0.0 and 1.0, nothing else."
        )

        result = self._pool._call_agent('critic', prompt)
        if not result:
            return None

        # Parse float from response
        try:
            match = re.search(r'(\d+\.?\d*)', result)
            if not match:
                return None
            score = float(match.group(1))
            score = max(0.0, min(1.0, score))
        except (AttributeError, ValueError):
            return None

        self._critic_scores[thought.thought_id] = score
        self._total_critic_calls += 1
        return score

    # ── Fitness Computation ───────────────────────────────────────

    def _get_fitness(self, thought: ContinuousThought) -> float:
        """Compute combined fitness from critic + user rating.

        Returns:
            -1.0 if unscored, else 0.0-1.0
        """
        tid = thought.thought_id
        critic = self._critic_scores.get(tid)
        user = self._user_ratings.get(tid)

        if critic is None and user is None:
            return -1.0
        if critic is not None and user is not None:
            return 0.4 * critic + 0.6 * user
        if user is not None:
            return user
        return critic  # critic only

    # ── Selection ─────────────────────────────────────────────────

    def _select_parents(self, k: int = 3) -> Tuple[
        Optional[ContinuousThought], Optional[ContinuousThought]
    ]:
        """Tournament selection: pick k random, return top 2 by fitness.

        Only considers thoughts with fitness >= 0.2.
        """
        scored = [
            t for t in self._population.values()
            if self._get_fitness(t) >= 0.2
        ]
        if len(scored) < 2:
            return None, None

        # Tournament: sample k, sort by fitness
        sample_size = min(k, len(scored))
        tournament = random.sample(scored, sample_size)
        tournament.sort(key=lambda t: self._get_fitness(t), reverse=True)

        parent_a = tournament[0]
        # Pick second parent different from first
        for candidate in tournament[1:]:
            if candidate.thought_id != parent_a.thought_id:
                return parent_a, candidate

        # If tournament too small, pick another random
        remaining = [t for t in scored if t.thought_id != parent_a.thought_id]
        if remaining:
            return parent_a, random.choice(remaining)
        return None, None

    # ── Embedding ─────────────────────────────────────────────────

    def _get_embedding(self, thought: ContinuousThought) -> Optional['np.ndarray']:
        """Get or compute 384-dim embedding for a thought."""
        tid = thought.thought_id
        if tid in self._embeddings:
            return self._embeddings[tid]

        if not self._semantic_index or not thought.content:
            return None

        try:
            emb = self._semantic_index.embed(thought.content[:500])
            if emb is not None:
                self._embeddings[tid] = emb
                return emb
        except Exception:
            pass
        return None

    # ── Self-Attention Crossover ──────────────────────────────────

    def _crossover(
        self,
        parent_a: ContinuousThought,
        parent_b: ContinuousThought,
    ) -> Optional[ContinuousThought]:
        """Combine two parent thoughts via self-attention on embeddings.

        1. Embed both parents (384-dim)
        2. Compute attention score: dot(Q,K)/√d → sigmoid → weight
        3. Feed attention context + texts to LLM enricher
        4. Return child thought with lineage
        """
        if not self._pool:
            return None

        try:
            import numpy as np
        except ImportError:
            return None

        emb_a = self._get_embedding(parent_a)
        emb_b = self._get_embedding(parent_b)

        # Compute attention weight (default 0.5 if no embeddings)
        attention_weight = 0.5
        if emb_a is not None and emb_b is not None:
            d = emb_a.shape[0]
            attention_score = float(np.dot(emb_a, emb_b) / np.sqrt(d))
            # Sigmoid scaling: maps [-inf, inf] to [0, 1]
            attention_weight = float(1.0 / (1.0 + np.exp(-attention_score * 5)))

        fit_a = self._get_fitness(parent_a)
        fit_b = self._get_fitness(parent_b)

        prompt = (
            f"Combine these two thoughts into one evolved, deeper insight:\n\n"
            f"Thought A (fitness {fit_a:.2f}): {parent_a.content[:200]}\n\n"
            f"Thought B (fitness {fit_b:.2f}): {parent_b.content[:200]}\n\n"
            f"Attention weight A→B: {attention_weight:.2f} "
            f"(higher = B is more relevant to A)\n\n"
            f"Create ONE evolved thought that synthesizes the best of both. "
            f"Be specific, insightful, and concise (2-3 sentences). "
            f"Output ONLY the evolved thought."
        )

        result = self._pool._call_agent('enricher', prompt)
        if not result:
            return None

        child_gen = max(parent_a.generation, parent_b.generation) + 1
        child = ContinuousThought(
            timestamp=time.time(),
            content=result[:300],
            category="evolve",
            topic=f"gen-{child_gen}",
            relevance=max(parent_a.relevance, parent_b.relevance) * 0.9,
            thought_id=str(uuid.uuid4())[:8],
            fitness=-1.0,  # unscored, will be scored next cycle
            generation=child_gen,
            parent_ids=[parent_a.thought_id, parent_b.thought_id],
        )

        # Track lineage in graph
        self._graph_edges[child.thought_id][parent_a.thought_id] = "parent"
        self._graph_edges[child.thought_id][parent_b.thought_id] = "parent"

        self._total_evolutions += 1
        self._max_generation = max(self._max_generation, child.generation)
        return child

    # ── Mutation ──────────────────────────────────────────────────

    def _mutate(self, thought: ContinuousThought) -> Optional[ContinuousThought]:
        """LLM-powered mutation: rephrase thought with variation."""
        if not self._pool:
            return None

        prompt = (
            f"Rephrase and deepen this thought with a fresh perspective:\n\n"
            f"\"{thought.content[:250]}\"\n\n"
            f"Add a new angle, implication, or connection. "
            f"Output ONLY the evolved thought (2-3 sentences)."
        )

        result = self._pool._call_agent('explorer', prompt)
        if not result:
            return None

        mutant = ContinuousThought(
            timestamp=time.time(),
            content=result[:300],
            category="evolve",
            topic=f"mut-gen-{thought.generation + 1}",
            relevance=thought.relevance * 0.95,
            thought_id=str(uuid.uuid4())[:8],
            fitness=-1.0,
            generation=thought.generation + 1,
            parent_ids=[thought.thought_id],
        )

        self._graph_edges[mutant.thought_id][thought.thought_id] = "parent"
        self._total_evolutions += 1
        self._max_generation = max(self._max_generation, mutant.generation)
        return mutant

    # ── Semantic Linking ──────────────────────────────────────────

    def _auto_link(self, thought: ContinuousThought):
        """Embed thought and find similar thoughts in population."""
        emb = self._get_embedding(thought)
        if emb is None:
            return

        try:
            import numpy as np
        except ImportError:
            return

        tid = thought.thought_id
        # Compare against all cached embeddings
        for other_tid, other_emb in list(self._embeddings.items()):
            if other_tid == tid:
                continue
            sim = float(np.dot(emb, other_emb))  # L2-normalized → cosine sim
            if sim > 0.6:
                self._graph_edges[tid][other_tid] = "similar"
                self._graph_edges[other_tid][tid] = "similar"

    # ── Population Pruning ────────────────────────────────────────

    def _prune_population(self):
        """Remove lowest-fitness thoughts when population exceeds max.

        Evolved thoughts (generation > 0) are protected from pruning
        to preserve the evolutionary lineage.
        """
        if len(self._population) <= self._max_population:
            return

        # Separate evolved vs base thoughts
        evolved = []
        base = []
        for t in self._population.values():
            if t.generation > 0:
                evolved.append(t)
            else:
                base.append(t)

        # Sort base thoughts by fitness (unscored = -1.0 go first)
        base.sort(key=lambda t: self._get_fitness(t))

        # Remove excess from base first; only touch evolved if desperate
        to_remove = len(self._population) - self._max_population
        removable = base[:to_remove]

        if len(removable) < to_remove:
            # Not enough base thoughts — sort evolved by fitness too
            evolved.sort(key=lambda t: self._get_fitness(t))
            still_needed = to_remove - len(removable)
            removable.extend(evolved[:still_needed])

        for t in removable:
            tid = t.thought_id
            del self._population[tid]
            self._embeddings.pop(tid, None)
            self._critic_scores.pop(tid, None)
            self._user_ratings.pop(tid, None)
            self._graph_edges.pop(tid, None)

    # ── Main Evolution Step ───────────────────────────────────────

    def evolve_step(self) -> Optional[ContinuousThought]:
        """Run one evolution cycle.

        1. Score up to 3 unscored thoughts via LLM critic
        2. Select 2 parents via tournament (k=3)
        3. Crossover with probability 0.7, else mutate best parent
        4. Auto-link the child
        5. Return the child thought (or None if not enough population)
        """
        # Need at least 3 thoughts in population
        if len(self._population) < 3:
            return None

        # Step 1: Score unscored thoughts
        unscored = [
            t for t in self._population.values()
            if t.thought_id not in self._critic_scores
            and t.content
            and len(t.content.strip()) >= 10
        ]
        for thought in unscored[:2]:  # Score up to 2 per step
            self._score_with_critic(thought)
            if thought.thought_id in self._critic_scores:
                thought.fitness = self._get_fitness(thought)

        # Need at least 2 scored thoughts
        scored_count = sum(
            1 for t in self._population.values()
            if self._get_fitness(t) >= 0.0
        )
        if scored_count < 2:
            return None

        # Step 2: Select parents
        parent_a, parent_b = self._select_parents(k=3)
        if parent_a is None or parent_b is None:
            return None

        # Step 3: Crossover or mutate
        child = None
        if random.random() < 0.7:
            child = self._crossover(parent_a, parent_b)
        if child is None:
            # Mutate the best parent instead
            child = self._mutate(parent_a)

        if child is None:
            return None

        # Step 4: Ingest child (auto-embeds and auto-links)
        self.ingest(child)

        return child

    # ── Graph API ─────────────────────────────────────────────────

    def get_graph(self) -> Dict[str, Any]:
        """Return thought graph as {nodes, edges} for API/visualization."""
        nodes = []
        for tid, thought in self._population.items():
            nodes.append({
                'id': tid,
                'content': thought.content[:100],
                'category': thought.category,
                'fitness': round(self._get_fitness(thought), 3),
                'generation': thought.generation,
                'timestamp': thought.timestamp,
            })

        edges = []
        seen_edges = set()
        for source, targets in self._graph_edges.items():
            for target, edge_type in targets.items():
                edge_key = (min(source, target), max(source, target), edge_type)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append({
                        'source': source,
                        'target': target,
                        'type': edge_type,
                    })

        return {'nodes': nodes, 'edges': edges}

    # ── Neural Manifold (3D UMAP projection) ──────────────────────

    def get_manifold(self) -> Dict[str, Any]:
        """Return 3D manifold projection with UMAP + DBSCAN clusters.

        Projects 384-dim thought embeddings onto a 3D manifold where
        distance ≈ semantic dissimilarity. DBSCAN identifies attractor
        basins (dense concept clusters). Y-axis is offset by fitness
        to create an attractor landscape topology.

        Returns:
            Dict with nodes (3D coords), edges, clusters, stats
        """
        import numpy as np

        tids = list(self._embeddings.keys())
        # Filter to thoughts still in population
        tids = [t for t in tids if t in self._population]

        if not tids:
            return {'nodes': [], 'edges': [], 'clusters': [], 'stats': {
                'total_nodes': 0, 'total_clusters': 0, 'avg_fitness': 0.0,
            }}

        embeddings = np.array([self._embeddings[t] for t in tids])  # [N, 384]

        # ── UMAP 3D projection ──
        coords_3d = None
        if len(tids) >= 5:
            try:
                import umap
                reducer = umap.UMAP(
                    n_components=3,
                    n_neighbors=min(15, len(tids) - 1),
                    min_dist=0.1,
                    metric='cosine',
                    random_state=42,
                )
                coords_3d = reducer.fit_transform(embeddings)
            except Exception:
                pass

        if coords_3d is None:
            # Fallback: random projection for < 5 or UMAP failure
            if embeddings.shape[0] > 0:
                mean = embeddings.mean(axis=0)
                centered = embeddings - mean
                rng = np.random.RandomState(42)
                proj = rng.randn(embeddings.shape[1], 3).astype(np.float32)
                proj, _ = np.linalg.qr(proj)
                coords_3d = centered @ proj
            else:
                coords_3d = np.zeros((0, 3))

        # ── Fitness Y-offset (attractor landscape) ──
        for i, tid in enumerate(tids):
            fitness = self._get_fitness(self._population[tid])
            if fitness >= 0:
                coords_3d[i, 1] += fitness * 2.0

        # ── DBSCAN clustering ──
        cluster_labels = np.full(len(tids), -1, dtype=int)
        if len(tids) >= 5:
            try:
                from sklearn.cluster import DBSCAN
                db = DBSCAN(eps=1.5, min_samples=3).fit(coords_3d)
                cluster_labels = db.labels_
            except Exception:
                pass

        # ── Build response ──
        nodes = []
        for i, tid in enumerate(tids):
            thought = self._population[tid]
            nodes.append({
                'id': tid,
                'x': round(float(coords_3d[i, 0]), 4),
                'y': round(float(coords_3d[i, 1]), 4),
                'z': round(float(coords_3d[i, 2]), 4),
                'fitness': round(self._get_fitness(thought), 3),
                'generation': thought.generation,
                'category': thought.category,
                'content': thought.content[:100],
                'cluster_id': int(cluster_labels[i]),
            })

        # Reuse edges from get_graph()
        graph = self.get_graph()

        # Build cluster summaries
        clusters = []
        unique_labels = set(cluster_labels)
        unique_labels.discard(-1)  # Remove noise label
        for label in sorted(unique_labels):
            mask = cluster_labels == label
            cluster_coords = coords_3d[mask]
            cluster_tids = [tids[i] for i in range(len(tids)) if mask[i]]
            fitness_vals = [
                self._get_fitness(self._population[t])
                for t in cluster_tids
                if self._get_fitness(self._population[t]) >= 0
            ]
            topics = [self._population[t].topic for t in cluster_tids if self._population[t].topic]
            dominant_topic = max(set(topics), key=topics.count) if topics else ""

            clusters.append({
                'id': int(label),
                'center_x': round(float(cluster_coords[:, 0].mean()), 4),
                'center_y': round(float(cluster_coords[:, 1].mean()), 4),
                'center_z': round(float(cluster_coords[:, 2].mean()), 4),
                'size': int(mask.sum()),
                'avg_fitness': round(sum(fitness_vals) / len(fitness_vals), 3) if fitness_vals else 0.0,
                'dominant_topic': dominant_topic,
            })

        # Stats
        all_fitness = [self._get_fitness(self._population[t]) for t in tids]
        scored_fitness = [f for f in all_fitness if f >= 0]
        avg_fitness = sum(scored_fitness) / len(scored_fitness) if scored_fitness else 0.0

        return {
            'nodes': nodes,
            'edges': graph['edges'],
            'clusters': clusters,
            'stats': {
                'total_nodes': len(nodes),
                'total_clusters': len(clusters),
                'avg_fitness': round(avg_fitness, 3),
                'max_generation': max((n['generation'] for n in nodes), default=0),
            },
        }

    # ── Persistence ──────────────────────────────────────────────

    def save_state(self, filepath: str) -> None:
        """Persist evolution population + scores + graph to JSON."""
        data = {
            'population': {
                tid: {
                    'content': t.content, 'category': t.category,
                    'topic': t.topic, 'relevance': t.relevance,
                    'fitness': t.fitness, 'generation': t.generation,
                    'parent_ids': t.parent_ids, 'thought_id': t.thought_id,
                    'timestamp': t.timestamp,
                }
                for tid, t in self._population.items()
            },
            'critic_scores': self._critic_scores,
            'user_ratings': {str(k): v for k, v in self._user_ratings.items()},
            'graph_edges': dict(self._graph_edges),
            'max_generation': self._max_generation,
            'total_evolutions': self._total_evolutions,
        }
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logger.info("ThoughtEvolution saved %d thoughts to %s",
                     len(data['population']), filepath)

    def load_state(self, filepath: str) -> int:
        """Load persisted evolution state. Returns count of restored thoughts."""
        if not os.path.exists(filepath):
            return 0

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        count = 0
        for tid, td in data.get('population', {}).items():
            thought = ContinuousThought(
                timestamp=td.get('timestamp', time.time()),
                content=td.get('content', ''),
                category=td.get('category', 'idle'),
                topic=td.get('topic', ''),
                relevance=td.get('relevance', 0.5),
                thought_id=td.get('thought_id', tid),
                fitness=td.get('fitness', -1.0),
                generation=td.get('generation', 0),
                parent_ids=td.get('parent_ids', []),
            )
            self._population[tid] = thought
            self._ts_to_id[thought.timestamp] = tid
            count += 1

        self._critic_scores = data.get('critic_scores', {})
        self._user_ratings = data.get('user_ratings', {})
        self._graph_edges = defaultdict(dict, data.get('graph_edges', {}))
        self._max_generation = data.get('max_generation', 0)
        self._total_evolutions = data.get('total_evolutions', 0)

        logger.info("ThoughtEvolution loaded %d thoughts from %s", count, filepath)
        return count

    # ── Stats ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return evolution metrics."""
        scored = sum(
            1 for t in self._population.values()
            if self._get_fitness(t) >= 0.0
        )
        avg_fitness = 0.0
        fitness_vals = [
            self._get_fitness(t) for t in self._population.values()
            if self._get_fitness(t) >= 0.0
        ]
        if fitness_vals:
            avg_fitness = sum(fitness_vals) / len(fitness_vals)

        return {
            'population_size': len(self._population),
            'scored_count': scored,
            'avg_fitness': round(avg_fitness, 3),
            'max_generation': self._max_generation,
            'total_evolutions': self._total_evolutions,
            'total_critic_calls': self._total_critic_calls,
            'total_user_ratings': self._total_user_ratings,
            'graph_nodes': len(self._graph_edges),
            'graph_edges': sum(len(v) for v in self._graph_edges.values()),
            'embedding_cache_size': len(self._embeddings),
        }


# ═══════════════════════════════════════════════════════════════════
# ContinuousThinkingEngine — Always-On Background Thinking
# ═══════════════════════════════════════════════════════════════════

class ContinuousThinkingEngine:
    """
    Always-on background thinking — the brain NEVER stops thinking.

    When idle: explores topics, makes associations, reflects on past
    When active: thinks ahead, pre-fetches knowledge, generates hypotheses

    All thoughts are stored in a buffer for Moltbook to visualize.
    """

    def __init__(self, thought_stream=None, moltbook=None,
                 knowledge_augmentor=None,
                 interval_ms: int = 5000,
                 max_thoughts: int = 500):
        self._thought_stream = thought_stream  # ThoughtStream (existing)
        self._moltbook = moltbook              # MoltbookStore
        self._augmentor = knowledge_augmentor  # KnowledgeAugmentor
        self._interval_ms = interval_ms
        self._max_thoughts = max_thoughts

        # Continuous thought buffer (separate from ThoughtStream's buffer)
        self._thoughts: deque = deque(maxlen=max_thoughts)
        self._thought_lock = threading.Lock()

        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mode = "idle"  # idle/active/dreaming
        self._total_ticks = 0

        # Context: what we're currently engaged with
        self._current_topic: str = ""
        self._recent_queries: deque = deque(maxlen=20)
        self._conversation_history: deque = deque(maxlen=50)

        # Knowledge the brain has LEARNED — actual content from responses
        # Each entry: {'topic': str, 'knowledge': str, 'source': str, 'timestamp': float}
        self._learned_knowledge: deque = deque(maxlen=30)

        # Phase 7.5 — meaningful event queue. Other subsystems push events
        # here (plan completed, plan rewarded, capability no-match cluster,
        # provider drift). _think_tick prefers these as seeds before
        # falling back to random knowledge reflection.
        # Each entry: {kind, payload, ts}
        self._event_queue: deque = deque(maxlen=50)
        # Optional reference to DiscourseEngine so we can read recent_user_topics
        self._discourse_engine_ref = None

        # Knowledge expander — proactive exploration (set by BrainChat)
        self._knowledge_expander: Optional[KnowledgeExpander] = None

        # Knowledge synthesizer — module-driven reasoning (set by BrainChat)
        self._knowledge_synthesizer: Optional[KnowledgeSynthesizer] = None

        # Micro-agent pool — LLM-powered knowledge refinement (set by BrainChat)
        self._micro_agent_pool: Optional[MicroAgentPool] = None

        # Evolution engine — evolutionary thought refinement (set by BrainChat)
        self._evolution_engine: Optional[ThoughtEvolutionEngine] = None

        # Memory consolidator — sleep-cycle persistence (set by BrainChat)
        self._memory_consolidator = None

        # Radial bridge — thought ↔ ring network integration
        self._thought_radial_bridge = None  # ThoughtRadialBridge (set by BrainChat)
        self._last_processed_thought = None  # Track for reward feedback
        self._thought_jury = None  # ThoughtJury (set by BrainChat)
        self._outcome_tracker = None  # OutcomeRewardTracker (set by brain_server)

        # Exploration: topics to think about autonomously
        self._exploration_seeds: List[str] = [
            "What patterns have I noticed today?",
            "What connections exist between recent topics?",
            "What questions remain unanswered?",
            "What could I learn next?",
            "How do recent conversations relate to each other?",
        ]

        # Callbacks for external listeners (e.g., WebSocket push to Moltbook)
        self._on_thought_callbacks: List[Callable] = []

        # AgentLoop reference — when set, each think tick also fires a radial
        # forward pass, keeping bridges alive and the dashboard populated.
        self._agent_loop = None

        logger.info(f"ContinuousThinkingEngine initialized (interval={interval_ms}ms)")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def mode(self) -> str:
        return self._mode

    def set_agent_loop(self, agent_loop) -> None:
        """Connect the AgentLoop so each think tick fires a radial forward pass.

        This bridges the ContinuousThinkingEngine (always-on thoughts) with the
        RadialAttentionNetwork (bridge modulation + ring activations). Once set,
        every thought tick also calls agent_loop.radial_tick(description) which
        updates bridge states, ring activations, and the dashboard live.
        """
        self._agent_loop = agent_loop
        logger.info("ContinuousThinkingEngine connected to AgentLoop (radial_tick enabled)")

    def set_thought_radial_bridge(self, bridge) -> None:
        """Attach ThoughtRadialBridge for ring-signature enrichment."""
        self._thought_radial_bridge = bridge
        logger.info("ContinuousThinkingEngine connected to ThoughtRadialBridge")

    def set_thought_jury(self, jury) -> None:
        """Attach ThoughtJury for autonomous thought evaluation."""
        self._thought_jury = jury
        logger.info("ContinuousThinkingEngine connected to ThoughtJury")

    def on_thought(self, callback: Callable[[ContinuousThought], None]) -> None:
        """Register a callback for new thoughts (for real-time display)."""
        self._on_thought_callbacks.append(callback)

    def set_topic(self, topic: str) -> None:
        """Set the current topic of engagement."""
        self._current_topic = topic
        self._mode = "active"

    def record_query(self, query: str) -> None:
        """Record a user query for reflection."""
        self._recent_queries.append(query)
        self._conversation_history.append({
            'type': 'user',
            'content': query,
            'timestamp': time.time(),
        })

    def record_response(self, response: str, topic: str = "",
                        source: str = "", augmented: bool = False) -> None:
        """Record a system response for reflection.

        If augmented=True, also stores the response as learned knowledge
        so the brain can reflect on actual content, not just questions.
        """
        ts = time.time()
        self._conversation_history.append({
            'type': 'system',
            'content': response[:300],
            'timestamp': ts,
        })
        # If this was an augmented (knowledge-enriched) response, store it
        if augmented and len(response) > 50:
            self.record_knowledge(
                topic=topic or "recent topic",
                knowledge=response,
                source=source or "conversation",
            )

    def record_event(self, kind: str, payload: Dict[str, Any]) -> None:
        """Phase 7.5 — push a meaningful runtime event onto the priority
        thinking queue. Subsystems use this to make Brain reflect on its
        own behaviour:

          kind='plan_completed'    payload={plan_id, intent, ok, hop_count, elapsed_s}
          kind='plan_rewarded'     payload={plan_id, intent, score, reason}
          kind='no_match_cluster'  payload={signature, sample_intents, capability}
          kind='provider_drift'    payload={capability, target, before, after}

        The next idle tick will preferentially pull from this queue and
        produce a thought that REFERS to the event, instead of random
        knowledge reflection. Bounded queue (50) drops oldest on overflow."""
        try:
            self._event_queue.append({
                "kind": kind,
                "payload": payload or {},
                "ts": time.time(),
            })
        except Exception as e:
            logger.debug(f"[CTE] record_event failed: {e}")

    def set_discourse_engine_ref(self, de) -> None:
        """Phase 7.5 — read-only ref so CTE can pull `_recent_user_topics`
        when picking what to think about."""
        self._discourse_engine_ref = de

    def record_knowledge(self, topic: str, knowledge: str,
                         source: str = "unknown") -> None:
        """Record a piece of learned knowledge for the brain to reflect on.

        This is the KEY method that makes the brain think about what it
        KNOWS, not just what it was ASKED.
        """
        # Extract the most interesting sentences (not the whole response)
        # Split into sentences and pick the most informative ones
        sentences = [s.strip() for s in knowledge.replace('\n', '. ').split('.')
                     if len(s.strip()) > 20]
        # Store up to 3 key sentences per knowledge entry
        key_content = '. '.join(sentences[:3])[:250]
        if not key_content:
            key_content = knowledge[:250]

        self._learned_knowledge.append({
            'topic': topic[:80],
            'knowledge': key_content,
            'source': source,
            'timestamp': time.time(),
        })
        logger.debug(f"Knowledge recorded: [{source}] {topic[:40]} -> {key_content[:60]}...")

    def start(self) -> None:
        """Start continuous background thinking."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True,
            name="ContinuousThinking"
        )
        self._thread.start()

        # Also start the ThoughtStream if available
        if self._thought_stream and not self._thought_stream.is_running:
            self._thought_stream.start()

        logger.info("ContinuousThinkingEngine started — brain is now always thinking")

    def stop(self) -> None:
        """Stop continuous thinking."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._thought_stream:
            self._thought_stream.stop()
        logger.info("ContinuousThinkingEngine stopped")

    def _run_loop(self) -> None:
        """Main thinking loop — runs continuously."""
        while self._running:
            try:
                thought = self._think_tick()
                if thought and not self._is_duplicate_thought(thought):
                    # Assign thought_id if not already set
                    if not thought.thought_id:
                        thought.thought_id = str(uuid.uuid4())[:8]
                    with self._thought_lock:
                        self._thoughts.append(thought)
                    # Feed to evolution engine for scoring/linking
                    if self._evolution_engine:
                        try:
                            self._evolution_engine.ingest(thought)
                        except Exception:
                            pass
                    # Queue brain event for memory consolidation
                    if self._memory_consolidator:
                        try:
                            with self._thought_lock:
                                count = len(self._thoughts)
                            self._memory_consolidator.queue_brain_event({
                                'state': {'thought_count': count, 'mode': self._mode},
                                'action': thought.category,
                                'next_state': {'thought_count': count + 1, 'mode': self._mode},
                                'reward': thought.relevance,
                                'done': False,
                                'metadata': {'content': thought.content[:100], 'topic': thought.topic},
                            })
                        except Exception:
                            pass
                    # Notify listeners
                    for cb in self._on_thought_callbacks:
                        try:
                            cb(thought)
                        except Exception:
                            pass

                # Radial tick — push thought through rings, extract signature.
                # RingSignature modulates thought activation (neuroplasticity).
                if self._thought_radial_bridge is not None and thought is not None:
                    try:
                        ring_sig = self._thought_radial_bridge.process(thought)
                        if ring_sig is not None:
                            # Modulate thought activation based on ring signals
                            boost = ring_sig.activation_boost
                            thought.relevance = min(1.0, thought.relevance + boost * 0.3)
                            thought._ring_signature = ring_sig
                            self._last_processed_thought = thought
                    except Exception as e:
                        logger.debug(f"Radial bridge error: {e}")
                elif self._agent_loop is not None:
                    # Fallback: raw radial tick without signature extraction
                    try:
                        desc = ""
                        if thought:
                            desc = thought.content[:200]
                        elif self._current_topic:
                            desc = self._current_topic
                        else:
                            desc = "idle background processing"
                        self._agent_loop.radial_tick(desc)
                    except Exception as e:
                        logger.debug(f"Radial tick error: {e}")

                # ThoughtJury — autonomous evaluation → reward → Hebbian loop
                if self._thought_jury is not None and thought is not None:
                    try:
                        reward = self._thought_jury.evaluate(thought, self)
                        if self._thought_radial_bridge is not None and thought.thought_id:
                            outcome = "jury_positive" if reward > 0 else "jury_negative"
                            self._thought_radial_bridge.record_reward(
                                thought.thought_id, reward, outcome)
                    except Exception as e:
                        logger.debug(f"ThoughtJury error: {e}")

                # Outcome reward: check redundancy against Moltbook
                if self._outcome_tracker is not None and thought is not None:
                    try:
                        self._outcome_tracker.check_redundancy(thought)
                    except Exception:
                        pass

            except Exception as e:
                logger.warning(f"Thinking tick error: {e}")

            # Adaptive interval: faster when active, slower idle (10s)
            if self._mode == "active":
                sleep_ms = max(200, self._interval_ms // 2)
            elif self._mode == "dreaming":
                sleep_ms = self._interval_ms * 3
            elif self._mode == "idle":
                sleep_ms = 10000  # 10s between idle thoughts
            else:
                sleep_ms = self._interval_ms

            time.sleep(sleep_ms / 1000.0)

    @staticmethod
    def _normalize_thought_content(content: str) -> str:
        """Strip ThoughtStream prefixes like [hop_0], [hop_1] for comparison."""
        import re
        # Remove [hop_N] prefixes and leading whitespace
        cleaned = re.sub(r'\[hop_\d+\]\s*', '', content).strip().lower()
        # Collapse whitespace
        cleaned = ' '.join(cleaned.split())
        return cleaned[:80]

    def _is_duplicate_thought(self, thought: ContinuousThought) -> bool:
        """Check if this thought is too similar to recent thoughts.

        Compares normalized content (strips [hop_N] prefixes) against
        the last N thoughts. Returns True if duplicate found.
        """
        if not thought.content:
            return True  # empty thoughts are always "duplicates"

        new_norm = self._normalize_thought_content(thought.content)
        if len(new_norm) < 10:
            return False  # too short to compare meaningfully

        with self._thought_lock:
            recent = list(self._thoughts)[-8:]

        for t in recent:
            old_norm = self._normalize_thought_content(t.content)
            if not old_norm:
                continue
            # Check if contents overlap significantly
            # Use substring match (either direction) on first 60 chars
            key = new_norm[:60]
            old_key = old_norm[:60]
            if key == old_key:
                return True
            # Check overlap: if 40+ chars match at start
            min_len = min(len(key), len(old_key), 40)
            if min_len >= 20 and key[:min_len] == old_key[:min_len]:
                return True

        return False

    def _think_tick(self) -> Optional[ContinuousThought]:
        """Generate one background thought."""
        self._total_ticks += 1

        # Phase 7.5 — meaningful events have first priority. We dequeue at
        # most 1 event per tick; if it produces a thought, return it.
        if self._event_queue:
            try:
                evt = self._event_queue.popleft()
                result = self._think_event(evt)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"[CTE] _think_event failed: {e}")

        # Phase 7.5 — fall back to recent user topics if no event but
        # the user is actively working on something. ~25% chance to seed
        # idle reflection from there.
        de_ref = getattr(self, "_discourse_engine_ref", None)
        if de_ref is not None and self._mode != "active":
            recent = getattr(de_ref, "_recent_user_topics", None)
            if recent and len(recent) >= 3 and random.random() < 0.25:
                topic = random.choice(list(recent))
                # Use the explore template seeded with user-current topic
                self._current_topic = topic[:80]
                result = self._think_explore()
                if result:
                    return result

        # Determine what to think about
        if self._mode == "active" and self._current_topic:
            return self._think_active()
        elif (self._knowledge_expander
              and self._knowledge_expander.has_pending()
              and random.random() < 0.15):
            # 15% chance to proactively expand knowledge in background
            return self._think_expand()
        elif self._learned_knowledge:
            roll = random.random()
            if roll < 0.10 and (self._knowledge_synthesizer
                                and len(self._learned_knowledge) >= 3):
                # 10% chance: module-driven synthesis (DMN+OFC+ACC+PFC)
                result = self._think_synthesize()
                if result:
                    return result
                # fallthrough if synthesize returned None
            if roll < 0.18 and (self._micro_agent_pool
                                and len(self._learned_knowledge) >= 2):
                # 8% chance: LLM micro-agent refinement
                result = self._think_refine()
                if result:
                    return result
                # fallthrough if refine returned None
            if roll < 0.26 and (self._evolution_engine
                                and len(list(self._thoughts)) >= 5):
                # 8% chance: evolutionary thought combination
                result = self._think_evolve()
                if result:
                    return result
                # fallthrough if evolve returned None
            if roll < 0.31 and (self._micro_agent_pool
                                and self._conversation_history):
                # 5% chance: analyze user state
                result = self._think_user()
                if result:
                    return result
                # fallthrough if think_user returned None
            if roll < 0.43 and len(self._learned_knowledge) >= 2:
                # 12% chance to connect two knowledge entries
                result = self._think_connect()
                if result:
                    return result
                # fallthrough if connect returned None
            if roll < 0.72:
                # ~29% chance for knowledge reflection
                return self._think_knowledge()
            elif self._recent_queries:
                # ~18% chance for topic reflection (with knowledge)
                return self._think_reflect()
            else:
                return self._think_knowledge()
        elif self._recent_queries:
            return self._think_reflect()
        else:
            # Idle mode: rotate between explore, reflect, and evolve
            roll = random.random()
            if roll < 0.15 and (self._evolution_engine
                                and len(list(self._thoughts)) >= 5):
                # 15% chance: evolutionary thought combination (idle)
                result = self._think_evolve()
                if result:
                    return result
                # fallthrough to explore/reflect
            if roll < 0.55:
                return self._think_explore()
            else:
                return self._think_reflect()

    _ACTIVE_TEMPLATES = [
        "Focusing on '{topic}' - processing key aspects...",
        "Deep dive into '{topic}': examining implications...",
        "Analyzing '{topic}' from multiple perspectives...",
        "Connecting '{topic}' with related concepts...",
        "Synthesizing understanding of '{topic}'...",
    ]

    def _think_active(self) -> Optional[ContinuousThought]:
        """Think about the current active topic."""
        thought = ContinuousThought(
            timestamp=time.time(),
            category="active",
            topic=self._current_topic,
        )

        # ── Try LLM first ──
        if self._micro_agent_pool and self._current_topic:
            result = self._micro_agent_pool.analyze(self._current_topic[:300])
            if result:
                thought = ContinuousThought(
                    timestamp=time.time(),
                    category="active",
                    topic=self._current_topic[:60],
                    content=result.refined[:300],
                    relevance=result.confidence,
                )
                if not self._is_duplicate_thought(thought):
                    return thought

        # Use ThoughtStream for associative thinking
        if self._thought_stream:
            self._thought_stream.set_context(self._current_topic)
            micro = self._thought_stream.background_tick()
            if micro and "Thinking about:" not in micro.content:
                thought.content = micro.content
                thought.relevance = micro.relevance_to_current_task
                thought.emotional_valence = micro.emotional_charge
                thought.arousal = micro.arousal
                return thought

        # Richer fallback
        template = random.choice(self._ACTIVE_TEMPLATES)
        thought.content = template.format(topic=self._current_topic[:80])
        thought.relevance = 0.5
        return thought

    # Templates for richer reflection thoughts
    # Reflect templates that COMBINE topic + actual knowledge content.
    # '{topic}' is the user's question, '{knowledge}' is a learned fact.
    _REFLECT_TEMPLATES = [
        "Regarding '{topic}': {knowledge} — this suggests deeper implications worth exploring.",
        "Coming back to '{topic}', I recall that {knowledge}. That changes how I think about it.",
        "On '{topic}': the fact that {knowledge} raises new questions about practical applications.",
        "Re-examining '{topic}' through what I know: {knowledge}. The connection isn't obvious at first.",
        "'{topic}' makes more sense when you consider that {knowledge}.",
        "One underappreciated aspect of '{topic}': {knowledge}. Most people overlook this.",
        "If someone asked me about '{topic}', I'd emphasize that {knowledge}.",
        "The thing about '{topic}' is that {knowledge} — and that matters because it affects real systems.",
    ]

    # Knowledge reflection templates — interpret, don't just echo.
    # '{knowledge}' is a fact/sentence from learned content.
    _KNOWLEDGE_REFLECT_TEMPLATES = [
        "Interesting: {knowledge}. This means existing approaches might need rethinking.",
        "{knowledge} — that's significant because it constrains what's actually possible.",
        "Building on what I learned: {knowledge}. The practical implication is efficiency.",
        "{knowledge}. If I connect this with earlier knowledge, a pattern starts to emerge.",
        "Key detail I want to remember: {knowledge}. It changes the big picture.",
        "Worth noting: {knowledge}. Most explanations miss this subtlety.",
        "{knowledge}. This is the kind of foundational fact that cascades through everything else.",
        "A non-obvious consequence of {knowledge} is that related systems behave differently too.",
    ]

    _EXPLORE_TEMPLATES = [
        "What if {knowledge} could be applied in unexpected ways?",
        "I notice a pattern: {knowledge}",
        "Connecting ideas: {knowledge}",
        "An interesting perspective: {knowledge}",
        "Building on what I know: {knowledge}",
        "I find it curious that {knowledge}",
    ]

    # Cross-knowledge connection templates — link TWO different knowledge entries
    _CONNECT_TEMPLATES = [
        "I see a link: {fact_a} — meanwhile, {fact_b}. These might relate through shared mechanisms.",
        "Connecting two things I know: {fact_a}. Separately, {fact_b}. There could be a deeper pattern here.",
        "Interesting parallel: {fact_a}. And also: {fact_b}. Both involve transformation processes.",
        "{fact_a}. That reminds me: {fact_b}. The overlap isn't coincidental.",
    ]

    def _think_connect(self) -> Optional[ContinuousThought]:
        """Connect TWO knowledge entries — LLM-powered with template fallback."""
        knowledge_list = list(self._learned_knowledge)
        if len(knowledge_list) < 2:
            return None

        pair = random.sample(knowledge_list[-10:], min(2, len(knowledge_list[-10:])))
        if len(pair) < 2:
            return None

        text_a = pair[0]['knowledge'][:200]
        text_b = pair[1]['knowledge'][:200]

        # Don't connect if basically the same
        if text_a[:30].lower() == text_b[:30].lower():
            return None

        topic = f"{pair[0]['topic'][:30]} ↔ {pair[1]['topic'][:30]}"

        # ── Try LLM first ──
        if self._micro_agent_pool:
            result = self._micro_agent_pool.find_connection(text_a, text_b)
            if result:
                thought = ContinuousThought(
                    timestamp=time.time(),
                    category="connect",
                    topic=topic,
                    content=result.refined[:300],
                    relevance=result.confidence,
                )
                if not self._is_duplicate_thought(thought):
                    return thought

        # ── Fallback: template ──
        def extract_sentence(entry):
            raw = entry['knowledge']
            sentences = [s.strip() for s in raw.split('.') if len(s.strip()) > 15]
            if sentences:
                return random.choice(sentences[:3])[:90].rstrip()
            return raw[:90].rstrip()

        fact_a = extract_sentence(pair[0])
        fact_b = extract_sentence(pair[1])
        template = random.choice(self._CONNECT_TEMPLATES)
        content = template.format(fact_a=fact_a, fact_b=fact_b)

        thought = ContinuousThought(
            timestamp=time.time(),
            category="connect",
            topic=topic,
            content=content,
            relevance=0.65,
        )
        if not self._is_duplicate_thought(thought):
            return thought
        return None

    def _think_synthesize(self) -> Optional[ContinuousThought]:
        """Synthesize insights from learned knowledge using neuroscience modules.

        Uses KnowledgeSynthesizer (DMN + OFC + ACC + PFC + MetaCognition)
        to generate computation-driven insights instead of template-filling.
        """
        if not self._knowledge_synthesizer:
            return None

        knowledge_list = list(self._learned_knowledge)
        if len(knowledge_list) < 3:
            return None

        # Pick 3-5 entries from recent knowledge
        sample_size = min(5, len(knowledge_list))
        sample = random.sample(knowledge_list[-10:], sample_size)
        texts = [e['knowledge'][:200] for e in sample]

        try:
            results = self._knowledge_synthesizer.synthesize_batch(texts)
        except Exception:
            return None

        if not results:
            return None

        # Pick the best result
        best = results[0]  # Already sorted by confidence

        # Detect topic from sample
        topic_parts = [e['topic'][:25] for e in sample[:2]]
        topic = ' + '.join(topic_parts)

        thought = ContinuousThought(
            timestamp=time.time(),
            content=best.content,
            category="synthesis",
            topic=topic,
            relevance=best.confidence,
        )
        if not self._is_duplicate_thought(thought):
            return thought
        return None

    def _think_refine(self) -> Optional[ContinuousThought]:
        """Refine knowledge using LLM micro-agents.

        Calls MicroAgentPool.run_background_cycle() which picks a random
        agent (summarizer/connector/critic/enricher) and feeds it
        knowledge entries for refinement.
        """
        if not self._micro_agent_pool:
            return None

        knowledge_list = list(self._learned_knowledge)
        if len(knowledge_list) < 2:
            return None

        texts = [e['knowledge'][:200] for e in knowledge_list]

        try:
            result = self._micro_agent_pool.run_background_cycle(texts)
        except Exception:
            return None

        if not result:
            return None

        # Detect topic from the original entry
        topic = result.refinement_type  # "summary", "connection", etc.

        thought = ContinuousThought(
            timestamp=time.time(),
            content=result.refined[:300],
            category="refine",
            topic=topic,
            relevance=result.confidence,
        )
        if not self._is_duplicate_thought(thought):
            return thought
        return None

    def _think_evolve(self) -> Optional[ContinuousThought]:
        """Run one evolutionary step: score → select → crossover → return child.

        Uses ThoughtEvolutionEngine to combine high-fitness thoughts into
        evolved offspring via self-attention crossover.
        """
        if not self._evolution_engine:
            return None

        try:
            child = self._evolution_engine.evolve_step()
        except Exception:
            return None

        if child and not self._is_duplicate_thought(child):
            return child
        return None

    @staticmethod
    def _find_matching_knowledge(query: str, knowledge_list: list) -> str:
        """Find a knowledge snippet that actually matches the query topic."""
        if not knowledge_list:
            return ""
        query_words = set(query.lower().split())
        # Remove stop words
        stop = {'what', 'is', 'how', 'does', 'do', 'the', 'a', 'an', 'are', 'was', 'were'}
        query_words -= stop

        # Score each entry by word overlap with the query
        scored = []
        for entry in knowledge_list[-10:]:
            topic_words = set(entry['topic'].lower().split()) - stop
            knowledge_words = set(entry['knowledge'][:200].lower().split()) - stop
            overlap = len(query_words & (topic_words | knowledge_words))
            scored.append((overlap, entry))

        # Sort by overlap score, pick from best matches
        scored.sort(key=lambda x: -x[0])
        # Pick from top matches (with some randomness for variety)
        best = [e for score, e in scored if score > 0]
        if not best:
            best = knowledge_list[-5:]  # fallback: recent entries

        entry = random.choice(best[:3])
        raw = entry['knowledge']
        sentences = [s.strip() for s in raw.split('.') if len(s.strip()) > 15]
        if sentences:
            return random.choice(sentences[:3])[:100].rstrip()
        return raw[:100].rstrip()

    def _think_reflect(self) -> Optional[ContinuousThought]:
        """Reflect on recent conversations — combining topic with MATCHING knowledge."""
        recent = list(self._recent_queries)
        if not recent:
            # No queries yet — try LLM-powered idle reflection
            if self._micro_agent_pool:
                seed = random.choice(self._exploration_seeds)
                result = self._micro_agent_pool.reflect(
                    seed[:200], "the nature of thought and curiosity"
                )
                if result:
                    thought = ContinuousThought(
                        timestamp=time.time(),
                        category="reflect",
                        topic=seed[:60],
                        content=result.refined[:300],
                        relevance=result.confidence,
                    )
                    if not self._is_duplicate_thought(thought):
                        return thought
            return None

        knowledge_list = list(self._learned_knowledge)

        # Shuffle to vary which query we reflect on
        candidates = list(recent[-5:])
        random.shuffle(candidates)

        # ── Try LLM first ──
        if self._micro_agent_pool and knowledge_list:
            query_to_reflect = candidates[0] if candidates else recent[-1]
            # Find relevant knowledge for this query
            knowledge_snippet = ""
            for entry in knowledge_list[-5:]:
                knowledge_snippet = entry.get('knowledge', '')[:200]
                break
            if knowledge_snippet:
                result = self._micro_agent_pool.reflect(query_to_reflect[:200], knowledge_snippet)
                if result:
                    thought = ContinuousThought(
                        timestamp=time.time(),
                        category="reflect",
                        topic=query_to_reflect[:60],
                        content=result.refined[:300],
                        relevance=result.confidence,
                    )
                    if not self._is_duplicate_thought(thought):
                        return thought

        for query in candidates:
            topic_short = query[:60].rstrip()
            # Find knowledge that actually MATCHES this topic
            knowledge_snippet = self._find_matching_knowledge(query, knowledge_list)

            template = random.choice(self._REFLECT_TEMPLATES)
            try:
                content = template.format(
                    topic=topic_short,
                    knowledge=knowledge_snippet or "systems interact in complex ways",
                )
            except (KeyError, IndexError):
                content = f"Reflecting on '{topic_short}': {knowledge_snippet}"

            thought = ContinuousThought(
                timestamp=time.time(),
                category="reflect",
                topic=topic_short,
                content=content,
                relevance=0.5,
            )
            if not self._is_duplicate_thought(thought):
                return thought

        # All candidates produced duplicates
        return self._think_explore()

    def _think_knowledge(self) -> Optional[ContinuousThought]:
        """Reflect on learned knowledge — LLM-powered with template fallback."""
        knowledge_list = list(self._learned_knowledge)
        if not knowledge_list:
            return self._think_reflect()

        recent_entries = list(knowledge_list[-8:])
        random.shuffle(recent_entries)

        for entry in recent_entries:
            topic = entry['topic']
            raw = entry['knowledge']

            # ── Try LLM first ──
            if self._micro_agent_pool:
                result = self._micro_agent_pool.summarize(raw[:300])
                if result:
                    thought = ContinuousThought(
                        timestamp=time.time(),
                        category="knowledge",
                        topic=topic,
                        content=result.refined[:300],
                        relevance=result.confidence,
                    )
                    if not self._is_duplicate_thought(thought):
                        return thought

            # ── Fallback: template ──
            sentences = [s.strip() for s in raw.split('.') if len(s.strip()) > 15]
            if not sentences:
                sentences = [raw[:120].rstrip()]
            knowledge_snippet = random.choice(sentences)[:120].rstrip()
            template = random.choice(self._KNOWLEDGE_REFLECT_TEMPLATES)
            content = template.format(knowledge=knowledge_snippet)

            thought = ContinuousThought(
                timestamp=time.time(),
                category="knowledge",
                topic=topic,
                content=content,
                relevance=0.55,
            )
            if not self._is_duplicate_thought(thought):
                return thought

        return self._think_explore()

    def _think_expand(self) -> Optional[ContinuousThought]:
        """Proactively expand knowledge by fetching queued follow-up queries.

        This runs in the CTE background thread, so HTTP latency is fine.
        The KnowledgeExpander does the actual fetching via KnowledgeAugmentor.
        """
        if not self._knowledge_expander:
            return self._think_explore()

        result = self._knowledge_expander.expand_next()
        if result and result.get('answer'):
            # Record the newly learned knowledge
            self.record_knowledge(
                topic=result['query'][:80],
                knowledge=result['answer'],
                source=f"expansion:{result.get('source', '')}",
            )
            return ContinuousThought(
                timestamp=time.time(),
                content=f"Expanded my knowledge: {result['answer'][:120]}...",
                category="expansion",
                relevance=0.5,
            )

        # Nothing to expand — fall back to regular exploration
        return self._think_explore()

    def _think_event(self, evt: Dict[str, Any]) -> Optional[ContinuousThought]:
        """Phase 7.5 — turn a runtime event into a meaningful thought.
        Different event kinds produce different reflection styles."""
        kind = evt.get("kind", "")
        p = evt.get("payload") or {}

        if kind == "plan_completed":
            ok = bool(p.get("ok"))
            hop_count = p.get("hop_count") or "?"
            elapsed = p.get("elapsed_s") or "?"
            intent = (p.get("intent") or "")[:120]
            if ok:
                content = (
                    f"Plan {p.get('plan_id','?')} done — {hop_count} hops in {elapsed}s. "
                    f"Intent: '{intent}'. What pattern made this work?"
                )
                relevance = 0.7
            else:
                content = (
                    f"Plan {p.get('plan_id','?')} FAILED after {hop_count} hops. "
                    f"Intent: '{intent}'. Need to find the failing capability."
                )
                relevance = 0.85  # failures get more attention
            return ContinuousThought(
                timestamp=time.time(), category="plan_reflection",
                content=content, relevance=relevance,
                intent=intent,  # Baustein C — ground the reflection in its intent
            )

        if kind == "plan_rewarded":
            score = p.get("score", 0)
            reason = p.get("reason", "")
            intent = (p.get("intent") or "")[:120]
            sign = "+" if score > 0 else ""
            mood = "User liked" if score > 0 else "User rejected"
            content = (
                f"{mood} plan: '{intent}' got {sign}{score} ({reason}). "
                f"Should reinforce this kind of decomposition for similar intents."
            )
            return ContinuousThought(
                timestamp=time.time(), category="reward_reflection",
                content=content, relevance=0.9,
                intent=intent,  # Baustein C
            )

        # Baustein D.1/C — ground-truth verification events become reflections
        # that carry the intent and the claimed-vs-verified diff.
        if kind in ("action_verified", "action_unverified", "action_refuted"):
            intent = (p.get("intent") or "")[:120]
            cap = p.get("capability", "")
            verified = p.get("verified")
            if kind == "action_refuted":
                content = (
                    f"Action for '{intent}' ({cap}) claimed success but the world "
                    f"REFUTED it: {p.get('reason','')}. The tool lied or broke silently."
                )
                relevance = 0.9
            elif kind == "action_unverified":
                content = (
                    f"Action for '{intent}' ({cap}) ran but I couldn't verify it "
                    f"against the world. Worth adding a post-condition check."
                )
                relevance = 0.6
            else:
                content = (
                    f"Action for '{intent}' ({cap}) confirmed by the world "
                    f"({p.get('reason','')}). Verified success."
                )
                relevance = 0.55
            return ContinuousThought(
                timestamp=time.time(), category="verification_reflection",
                content=content, relevance=relevance, intent=intent,
            )

        if kind == "no_match_cluster":
            samples = p.get("sample_intents") or []
            sig = p.get("signature") or "?"
            count = len(samples)
            example = samples[0][:80] if samples else ""
            content = (
                f"Coverage gap: {count} similar intents I couldn't route. "
                f"Cluster '{sig}'. Example: '{example}'. "
                f"What capability would cover this?"
            )
            return ContinuousThought(
                timestamp=time.time(), category="curator_reflection",
                content=content, relevance=0.75,
            )

        if kind == "provider_drift":
            cap = p.get("capability") or "?"
            target = p.get("target") or "?"
            before = p.get("before", 0)
            after = p.get("after", 0)
            direction = "improving" if after > before else "degrading"
            content = (
                f"Provider {target} on {cap} is {direction}: "
                f"{before:.0%} -> {after:.0%}. "
                f"Worth checking why."
            )
            return ContinuousThought(
                timestamp=time.time(), category="provider_reflection",
                content=content, relevance=0.6,
            )

        # Unknown event kind — produce a generic note so the queue empties
        return ContinuousThought(
            timestamp=time.time(), category="event",
            content=f"Event {kind}: {str(p)[:160]}",
            relevance=0.4,
        )

    def _think_explore(self) -> Optional[ContinuousThought]:
        """Autonomous exploration with more diverse thought generation."""
        thought = ContinuousThought(
            timestamp=time.time(),
            category="explore",
        )

        seed = random.choice(self._exploration_seeds)
        thought.topic = seed

        # ── Try LLM first ──
        if self._micro_agent_pool:
            result = self._micro_agent_pool.explore(seed[:300] if seed else "general knowledge")
            if result:
                thought = ContinuousThought(
                    timestamp=time.time(),
                    category="explore",
                    topic=seed[:60] if seed else "explore",
                    content=result.refined[:300],
                    relevance=result.confidence,
                )
                if not self._is_duplicate_thought(thought):
                    return thought

        # Query Moltbook for knowledge to think about
        if self._moltbook:
            try:
                entries = self._moltbook.get_active_entries(top_k=20)
                if entries:
                    entry = random.choice(entries)
                    content_snippet = entry.content[:120].rstrip()

                    # Use varied templates instead of always "Exploring: ..."
                    template = random.choice(self._EXPLORE_TEMPLATES)
                    thought.content = template.format(knowledge=content_snippet)
                    thought.relevance = 0.25

                    if self._thought_stream:
                        self._thought_stream.add_seed(entry.content[:100])

                    return thought
            except Exception:
                pass

        # Fallback with richer seeds
        fallback_thoughts = [
            f"Wondering: {seed}",
            f"A question emerges: {seed}",
            f"My curiosity turns to: {seed}",
            f"Idle thought: {seed}",
        ]
        thought.content = random.choice(fallback_thoughts)
        thought.relevance = 0.1
        return thought

    def _think_user(self) -> Optional[ContinuousThought]:
        """Analyze user state — mood, needs, interests.

        Calls MicroAgentPool.analyze_user() with conversation history.
        Produces 'user_insight' category thoughts.
        """
        if not self._micro_agent_pool:
            return None

        history = list(self._conversation_history)
        if not history:
            return None

        result = self._micro_agent_pool.analyze_user(history)
        if not result:
            return None

        thought = ContinuousThought(
            timestamp=time.time(),
            content=result.refined[:300],
            category="user_insight",
            topic="user understanding",
            relevance=0.7,
        )
        if not self._is_duplicate_thought(thought):
            return thought
        return None

    def get_recent_thoughts(self, n: int = 20) -> List[ContinuousThought]:
        """Get the most recent continuous thoughts (for Moltbook display)."""
        with self._thought_lock:
            thoughts = list(self._thoughts)
        return thoughts[-n:]

    def get_thoughts_since(self, timestamp: float) -> List[ContinuousThought]:
        """Get thoughts since a given timestamp (for incremental updates)."""
        with self._thought_lock:
            return [t for t in self._thoughts if t.timestamp > timestamp]

    def get_learned_knowledge(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent learned knowledge entries."""
        items = list(self._learned_knowledge)
        return items[-n:]

    def get_conversation_history(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent conversation history turns."""
        items = list(self._conversation_history)
        return items[-n:]

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            'running': self._running,
            'mode': self._mode,
            'total_ticks': self._total_ticks,
            'thought_count': len(self._thoughts),
            'recent_queries': len(self._recent_queries),
            'learned_knowledge': len(self._learned_knowledge),
            'conversation_turns': len(self._conversation_history),
            'interval_ms': self._interval_ms,
        }
        if self._evolution_engine:
            stats['evolution'] = self._evolution_engine.get_stats()
        return stats


# ═══════════════════════════════════════════════════════════════════
# BrainChat — The Central Chat Router
# ═══════════════════════════════════════════════════════════════════

class BrainChat:
    """
    The single chat entry point for the entire Brain.

    Every message is routed through Thalamus (3-layer hierarchical routing):
      Layer 1: TaskFeatureRouter → extract features, routing weights
      Layer 2: ConversationPathPlanner → optimal path
      Layer 3: DecisionRouter → actionable decision

    Then dispatched to the appropriate modules:
      - KnowledgeAugmentor for external knowledge
      - InternalMonologue for deep thinking
      - TalkerModule for natural language generation

    Moltbook receives the thought trace for visualization — it's the
    "window into the brain", not the brain itself.
    """

    # Self-knowledge
    _IDENTITY = {
        'name': 'Tahlamus',
        'description': 'a neuroscience-inspired AI brain system',
        'greeting_responses': [
            "Hello! I'm Tahlamus, an AI brain system inspired by neuroscience. I can discuss topics, answer questions, and learn new things. What would you like to talk about?",
            "Hi there! I'm Tahlamus - a neuroscience-inspired AI. Ask me anything or share something interesting!",
            "Hey! I'm Tahlamus, your knowledge companion. What's on your mind?",
            "Welcome! I'm Tahlamus. I'm always thinking in the background - ask me anything!",
            "Hi! I'm Tahlamus, a brain-inspired AI. I think, I learn, I explore. What shall we discuss?",
        ],
    }

    _POSITIVE_FEEDBACK = {'genau', 'perfekt', 'super', 'ja', 'richtig', 'exactly',
                          'perfect', 'great', 'yes', 'correct', 'top', 'geil', 'nice'}
    _NEGATIVE_FEEDBACK = {'nein', 'falsch', 'wrong', 'no', 'nicht', 'schlecht',
                          'bad', 'fehler', 'error', 'quatsch', 'unsinn'}

    # Identity-related patterns
    _IDENTITY_PATTERNS = frozenset({
        'wer bist du', 'who are you', 'what are you',
        'tell me about yourself', 'introduce yourself',
        'was bist du', 'stell dich vor', 'your name',
    })

    # Single-word greetings (matched against individual tokens)
    _GREETING_WORDS = frozenset({
        'hi', 'hello', 'hey', 'hallo', 'moin', 'servus',
        'yo', 'sup', 'greetings', 'howdy', 'cheers', 'ciao',
        'ahoy', 'aloha', 'bonjour', 'hola', 'namaste',
    })
    # Multi-word greetings (matched as substring in full text)
    _GREETING_PHRASES = (
        'good morning', 'good evening', 'good afternoon', 'good night',
        'guten morgen', 'guten abend', 'guten tag',
        'how are you', "how's it going", 'what up', "what's up",
        'nice to meet', 'pleased to meet',
    )

    def __init__(self,
                 # Routing (Thalamus)
                 task_feature_router=None,
                 conversation_path_planner=None,
                 decision_router=None,
                 hierarchical_planner=None,
                 # Thinking
                 continuous_thinking=None,
                 internal_monologue=None,
                 knowledge_augmentor=None,
                 # Speaking
                 talker=None,
                 # Knowledge
                 moltbook=None,
                 # Pipeline (fallback)
                 input_analyzer=None,
                 thinking_budget=None,
                 ):
        # Thalamus routing layers
        self._l1_router = task_feature_router
        self._l2_planner = conversation_path_planner
        self._l3_router = decision_router
        self._hierarchical_planner = hierarchical_planner

        # Thinking
        self._continuous_thinking = continuous_thinking
        self._internal_monologue = internal_monologue
        self._augmentor = knowledge_augmentor

        # Speaking
        self._talker = talker

        # Knowledge
        self._moltbook = moltbook

        # Knowledge expander — proactive linking & exploration
        self._knowledge_expander = KnowledgeExpander(
            moltbook_store=moltbook,
            augmentor=knowledge_augmentor,
        )
        # Wire into ContinuousThinkingEngine so it can expand in background
        if continuous_thinking:
            continuous_thinking._knowledge_expander = self._knowledge_expander

        # Knowledge synthesizer — module-driven reasoning (set externally)
        self._knowledge_synthesizer: Optional[KnowledgeSynthesizer] = None

        # Micro-agent pool — LLM-powered refinement (set externally)
        self._micro_agent_pool: Optional[MicroAgentPool] = None

        # Evolution engine — evolutionary thought refinement (set externally)
        self._evolution_engine: Optional[ThoughtEvolutionEngine] = None

        # Moltbook feeder — auto-feed chat responses to persistent store (set externally)
        self._moltbook_feeder = None

        # Memory consolidator — sleep-cycle persistence (set externally)
        self._memory_consolidator = None

        # Qdrant knowledge graph — unified semantic+neural store (set externally)
        self._qdrant_kg = None

        # Auto-dispatcher — Phase F.4, forwards @mentioned tasks to Minibook agents
        self._auto_dispatcher = None

        # Phase Q.5 — IdeasClient for reward routing
        self._ideas_client = None

        # Phase R+ — DiscourseEngine for intent/response discourse
        self._discourse_engine = None
        # Phase S.5 — cross-session memory consolidator
        self._discourse_memory_consolidator = None

        # Thalamic adapter — ThalamoPC6-based routing (set externally)
        self._thalamic_adapter = None  # Optional[ThalamicAdapter]

        # Pipeline components (fallback if no Thalamus routing available)
        self._analyzer = input_analyzer
        self._budget = thinking_budget

        # Stats
        self._total_messages = 0
        self._total_routed = 0

        logger.info("BrainChat initialized — all chat goes through Thalamus")

    def set_knowledge_synthesizer(self, synthesizer: 'KnowledgeSynthesizer'):
        """Wire in the KnowledgeSynthesizer (set by production_planner or tests).

        Wires to both BrainChat and its ContinuousThinkingEngine so
        background thinking can generate synthesis-category thoughts.
        """
        self._knowledge_synthesizer = synthesizer
        if self._continuous_thinking:
            self._continuous_thinking._knowledge_synthesizer = synthesizer

    def set_micro_agent_pool(self, pool: 'MicroAgentPool'):
        """Wire in the MicroAgentPool (set by production_planner or tests).

        Wires to both BrainChat and its ContinuousThinkingEngine so
        background thinking can generate refine-category thoughts and
        the response path can use the Responder agent.
        """
        self._micro_agent_pool = pool
        if self._continuous_thinking:
            self._continuous_thinking._micro_agent_pool = pool

    def set_evolution_engine(self, engine: 'ThoughtEvolutionEngine'):
        """Wire in the ThoughtEvolutionEngine (set by brain_server).

        Wires to both BrainChat and its ContinuousThinkingEngine so
        background thinking can generate evolve-category thoughts and
        the dashboard can rate thoughts via the API.
        """
        self._evolution_engine = engine
        if self._continuous_thinking:
            self._continuous_thinking._evolution_engine = engine

    def set_memory_consolidator(self, consolidator):
        """Wire in the MemoryConsolidator (set by brain_server).

        Wires to both BrainChat and its ContinuousThinkingEngine so
        brain events (thoughts, chat) are queued for episodic memory.
        """
        self._memory_consolidator = consolidator
        if self._continuous_thinking:
            self._continuous_thinking._memory_consolidator = consolidator

    def set_qdrant_kg(self, kg) -> None:
        """Wire in the QdrantKG so chat responses get persisted to the
        unified knowledge graph with bidirectional edges."""
        self._qdrant_kg = kg

    def set_auto_dispatcher(self, dispatcher) -> None:
        """Wire in the AutoDispatcher (Phase F.4) so explicit @mentions
        of Minibook agents in user messages auto-forward as tasks."""
        self._auto_dispatcher = dispatcher

    def set_ideas_client(self, ic) -> None:
        """Phase Q.5 — wire IdeasClient so feedback rewards can flow to
        the ideas-kg via record_reward()."""
        self._ideas_client = ic

    def set_discourse_engine(self, de) -> None:
        """Phase R+ — wire DiscourseEngine so user intents can trigger
        a multi-agent decision discourse, and Brain responses can be
        queued for post-hoc agent assessment."""
        self._discourse_engine = de

    def set_discourse_memory_consolidator(self, dmc) -> None:
        """Phase S.5 — wire cross-session memory consolidator so self-aware
        queries can recall what Brain has thought about a topic across
        past discourse aggregations."""
        self._discourse_memory_consolidator = dmc

    def set_multihop(self, advisor=None, planner=None, executor=None, synthesizer=None) -> None:
        """Phase 6 — wire the multi-hop pipeline. All four are needed for
        the integration to fire; missing any one falls back to single-hop."""
        self._multihop_advisor = advisor
        self._multihop_planner = planner
        self._last_plan_id = None  # Phase 7.1 — for retroactive plan reward
        self._multihop_executor = executor
        self._multihop_synthesizer = synthesizer

    def _detect_user_feedback_reward(self, message: str) -> None:
        """Detect short affirmative/negative feedback and retroactively reward the previous thought."""
        words = message.lower().strip().rstrip('!?.').split()
        if len(words) > 5:
            return
        word_set = set(words)
        is_positive = bool(word_set & self._POSITIVE_FEEDBACK)
        is_negative = bool(word_set & self._NEGATIVE_FEEDBACK)
        if not (is_positive or is_negative):
            return

        # Reward path 1: existing — thought reward via radial bridge
        if self._continuous_thinking:
            bridge = getattr(self._continuous_thinking, '_thought_radial_bridge', None)
            last = getattr(self._continuous_thinking, '_last_processed_thought', None)
            if bridge and last and getattr(last, 'thought_id', ''):
                if is_positive:
                    bridge.record_reward(last.thought_id, 0.9, "user_positive")
                    logger.info(f"User positive feedback -> reward=0.9 for thought {last.thought_id}")
                elif is_negative:
                    bridge.record_reward(last.thought_id, -0.3, "user_negative")
                    logger.info(f"User negative feedback -> reward=-0.3 for thought {last.thought_id}")

        # Reward path 2: Phase Q.5 — ideas-kg reward when last response
        # was an auto-dispatch-create. Pulls last_idea_id from dispatcher
        # stats so the reward attaches to the just-captured idea.
        ad = getattr(self, '_auto_dispatcher', None)
        ic = getattr(self, '_ideas_client', None)
        if ad is not None and ic is not None:
            last_target = (ad.stats or {}).get("last_target") or ""
            last_idea_id = (ad.stats or {}).get("last_idea_id")
            if last_idea_id and last_target.startswith("ideas_local"):
                delta = 0.7 if is_positive else (-0.5 if is_negative else 0.0)
                if delta != 0.0:
                    try:
                        ic.record_reward(last_idea_id, delta, reason=(
                            "user_positive" if is_positive else "user_negative"
                        ))
                        logger.info(
                            f"User feedback -> idea {last_idea_id} delta={delta}"
                        )
                        # consume so a second 'ok' doesn't double-reward
                        ad.stats["last_idea_id"] = None
                    except Exception as e:
                        logger.debug(f"reward to ideas failed: {e}")

        # Reward path 3: Phase 7.1 — plan-outcome reward. If the previous
        # response was a multi-hop plan, attach a reward score to that
        # plan's recorder snapshot AND its episodic node, so:
        # - History UI shows green/red marker per plan
        # - Provider-success-routing (7.3) updates per-capability success
        # - Curator (Phase 5) can prioritise plan patterns the user liked
        pe = getattr(self, '_multihop_executor', None)
        if pe is not None:
            last_plan_id = getattr(self, '_last_plan_id', None)
            if last_plan_id:
                delta = 1.0 if is_positive else (-1.0 if is_negative else 0.0)
                if delta != 0.0:
                    try:
                        pe.record_plan_reward(last_plan_id, delta, reason=(
                            "user_positive" if is_positive else "user_negative"
                        ))
                        logger.info(
                            f"User feedback -> plan {last_plan_id} delta={delta}"
                        )
                        self._last_plan_id = None  # consume
                    except Exception as e:
                        logger.debug(f"reward to plan failed: {e}")

    def send(self, message: str) -> BrainChatResponse:
        """
        Send a message to the brain. This is THE entry point.

        The message goes through:
        1. Quick intent check (greetings short-circuit)
        2. Thalamus routing (3-layer)
        3. Module dispatch (knowledge + thinking + speaking)
        4. Thought trace collection (for Moltbook)
        """
        t0 = time.time()
        self._total_messages += 1

        # Retroactive reward: detect user feedback on previous response
        self._detect_user_feedback_reward(message)

        # Phase 7.2 — feed user keywords to DiscourseEngine so its idle
        # ticks bias their KG-slice picking towards what the user works on.
        de_for_topics = getattr(self, "_discourse_engine", None)
        if de_for_topics is not None and hasattr(de_for_topics, "record_user_topic"):
            try:
                de_for_topics.record_user_topic(message)
            except Exception:
                pass

        response = BrainChatResponse()
        trace = []

        # Record in continuous thinking
        if self._continuous_thinking:
            self._continuous_thinking.record_query(message)
            self._continuous_thinking.set_topic(message[:100])

        # ── Step 0: Quick intent detection ──
        is_greeting, is_identity = self._quick_intent(message)

        if is_greeting or is_identity:
            response.response_text = random.choice(self._IDENTITY['greeting_responses'])
            response.confidence = 0.95
            response.routing_mode = "routine"
            response.task_type = "greeting"
            trace.append(ThoughtTrace(
                timestamp=time.time(), category="routing",
                content="Greeting detected — short-circuit to identity response",
                module="BrainChat", confidence=0.95,
            ))
            response.thought_trace = trace
            response.total_time_ms = (time.time() - t0) * 1000
            self._record_response(response, original_message=message)
            return response

        # ── Step 0.5: Phase 6 — Multi-hop intercept ──
        # When the advisor says this intent is multi-step (connectives,
        # multiple verbs, explicit @plan), decompose into a DAG and
        # execute. On any failure → graceful fall-through to single-hop.
        adv = getattr(self, "_multihop_advisor", None)
        planner = getattr(self, "_multihop_planner", None)
        pe = getattr(self, "_multihop_executor", None)
        synth = getattr(self, "_multihop_synthesizer", None)
        if adv and planner and pe and synth:
            try:
                verdict = adv.should_decompose(message)
                if verdict.should_decompose:
                    trace.append(ThoughtTrace(
                        timestamp=time.time(), category="routing",
                        content=f"Multi-hop trigger ({verdict.triggered_by}): {verdict.reason}",
                        module="MultiHopAdvisor", confidence=0.7,
                    ))
                    plan = planner.plan(message)
                    if plan is not None:
                        trace.append(ThoughtTrace(
                            timestamp=time.time(), category="planning",
                            content=f"Plan {plan.plan_id} with {len(plan.hops)} hops: {plan.rationale[:120]}",
                            module="PlannerLLM", confidence=0.8,
                        ))
                        exec_result = pe.execute(plan)
                        # Synthesize final user-facing answer
                        final_text = synth.synthesize(
                            intent=message,
                            plan=plan,
                            executed=exec_result.get("executed", {}),
                            state=exec_result.get("state", {}),
                            custom_prompt=plan.final_synthesis_prompt or None,
                        )
                        response.response_text = final_text
                        response.confidence = 0.85 if exec_result.get("ok") else 0.5
                        response.routing_mode = "multihop"
                        response.task_type = "multihop"
                        response.multihop = {
                            "plan_id": plan.plan_id,
                            "hop_count": len(plan.hops),
                            "ok": exec_result.get("ok"),
                            "elapsed_s": exec_result.get("elapsed_s"),
                            "replans": exec_result.get("replans", 0),
                            "trigger": verdict.triggered_by,
                        }
                        # Phase 7.1 — track for retroactive reward
                        self._last_plan_id = plan.plan_id
                        trace.append(ThoughtTrace(
                            timestamp=time.time(), category="execution",
                            content=(
                                f"Multi-hop done: {len(exec_result.get('executed') or {})} hops, "
                                f"ok={exec_result.get('ok')}, {exec_result.get('elapsed_s')}s"
                            ),
                            module="PlanExecutor", confidence=response.confidence,
                        ))
                        response.thought_trace = trace
                        response.total_time_ms = (time.time() - t0) * 1000
                        self._record_response(response, original_message=message)
                        return response
                    else:
                        trace.append(ThoughtTrace(
                            timestamp=time.time(), category="planning",
                            content="Planner returned no plan — falling back to single-hop",
                            module="PlannerLLM", confidence=0.3,
                        ))
            except Exception as _mh_err:
                # Defensive: never block the user on a multi-hop bug
                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="error",
                    content=f"Multi-hop failed: {type(_mh_err).__name__}: {_mh_err} — fallback",
                    module="MultiHop", confidence=0.0,
                ))

        # ── Step 1: Thalamus Routing (3-Layer) ──
        t_route = time.time()
        routing_info = self._route_through_thalamus(message, trace)
        response.routing_time_ms = (time.time() - t_route) * 1000
        response.routing_mode = routing_info.get('mode', 'routine')
        response.routing_weights = routing_info.get('weights', [])
        response.dominant_areas = routing_info.get('dominant_areas', [])
        response.task_type = routing_info.get('task_type', 'general')

        # ── Step 2: Knowledge Retrieval + Augmentation ──
        t_think = time.time()
        entries, max_similarity, topics = self._retrieve_knowledge(message, trace)

        # Augment with external knowledge if needed
        augmented_answer = ''
        if self._augmentor:
            try:
                aug_result = self._augmentor.augment(
                    query=message,
                    topics=topics,
                    internal_entries=entries,
                    max_similarity=max_similarity,
                    intent=response.task_type,
                )
                if aug_result.get('augmented'):
                    augmented_answer = aug_result.get('combined_answer', '')
                    response.augmented = True
                    response.augment_source = aug_result.get('source', '')
                    trace.append(ThoughtTrace(
                        timestamp=time.time(), category="augment",
                        content=f"Knowledge augmented from {aug_result.get('source', '?')}: {augmented_answer[:100]}...",
                        module="KnowledgeAugmentor",
                        confidence=0.7,
                    ))

                    # ── Dynamic Knowledge Expansion ──
                    # Auto-link new knowledge to similar entries + queue follow-ups
                    if self._knowledge_expander:
                        stored_id = aug_result.get('stored_id', '')
                        self._knowledge_expander.auto_link(
                            entry_id=stored_id,
                            content=augmented_answer[:300],
                            topics=topics,
                        )
                        follow_ups = self._knowledge_expander.generate_follow_ups(
                            topic=' '.join(topics[:3]),
                            knowledge=augmented_answer[:500],
                        )
                        if follow_ups:
                            trace.append(ThoughtTrace(
                                timestamp=time.time(),
                                category="expansion",
                                content=(
                                    f"Queued {len(follow_ups)} follow-up explorations: "
                                    f"{', '.join(follow_ups[:2])}"
                                ),
                                module="KnowledgeExpander",
                                confidence=0.5,
                            ))

            except Exception as e:
                logger.warning(f"Augmentation failed: {e}")

        # ── Step 3: Deep Thinking (InternalMonologue) ──
        unified_thought = None
        if self._internal_monologue:
            try:
                unified_thought = self._internal_monologue.think(
                    message,
                    moltbook_entries=entries,
                    affect={'valence': 0.0},
                )
                response.confidence = unified_thought.confidence
                response.sources = unified_thought.source_entry_ids
                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="thought",
                    content=f"Deep thinking: confidence={unified_thought.confidence:.2f}, "
                            f"narrative={unified_thought.narrative[:100]}",
                    module="InternalMonologue",
                    confidence=unified_thought.confidence,
                ))
            except Exception as e:
                logger.warning(f"Thinking failed: {e}")

        response.thinking_time_ms = (time.time() - t_think) * 1000

        # ── Step 3.25: Lightweight Synthesis Check ──
        # Run only fast operations (contradiction detection + gap detection)
        # on the response path. Full synthesis runs in CTE background.
        synthesis_insights: List[SynthesisResult] = []
        if self._knowledge_synthesizer and entries and len(entries) >= 2:
            try:
                entry_texts = [
                    e.content[:200] for e in entries[:5]
                    if hasattr(e, 'content')
                ]
                if len(entry_texts) >= 2:
                    contradictions = (
                        self._knowledge_synthesizer.detect_contradictions(
                            entry_texts
                        )
                    )
                    gaps = (
                        self._knowledge_synthesizer.detect_knowledge_gaps(
                            ' '.join(topics[:3]), entry_texts
                        )
                    )
                    synthesis_insights = [
                        r for r in contradictions + gaps
                        if r.confidence > 0.3
                    ]
                    if synthesis_insights:
                        trace.append(ThoughtTrace(
                            timestamp=time.time(), category="synthesis",
                            content=(
                                f"Synthesis: {len(synthesis_insights)} insight(s) "
                                f"— {synthesis_insights[0].synthesis_type}: "
                                f"{synthesis_insights[0].content[:80]}"
                            ),
                            module="KnowledgeSynthesizer",
                            confidence=max(
                                r.confidence for r in synthesis_insights
                            ),
                        ))
            except Exception as e:
                logger.debug(f"Synthesis check failed: {e}")

        # ── Step 3.35: LLM Response Enhancement (Responder Agent) ──
        # Fire for any non-trivial query, even with zero internal entries.
        # Greetings / identity short-circuits skip the LLM.
        response_enhancement: Optional[RefinedKnowledge] = None
        task_type = routing_info.get('task_type', 'general') if routing_info else 'general'
        is_trivial = task_type in ('greeting', 'identity', 'acknowledgement')
        if self._micro_agent_pool and message and not is_trivial:
            try:
                entry_texts = [
                    e.content[:150] for e in (entries or [])[:3]
                    if hasattr(e, 'content')
                ]
                # Inject Wikipedia/external knowledge as synthetic entry so
                # the responder LLM has something to anchor on when internal
                # knowledge is empty.
                if augmented_answer and len(augmented_answer) > 20:
                    entry_texts.insert(0, f"[external] {augmented_answer[:600]}")
                response_enhancement = (
                    self._micro_agent_pool.enhance_response(
                        message[:400], entry_texts
                    )
                )
                if response_enhancement:
                    trace.append(ThoughtTrace(
                        timestamp=time.time(), category="refine",
                        content=(
                            f"LLM Enhancement: "
                            f"{response_enhancement.refined[:80]}"
                        ),
                        module="MicroAgentPool",
                        confidence=response_enhancement.confidence,
                    ))
                else:
                    # LLM returned None — likely upstream rate-limit (daily/min)
                    # or provider error. Surface this in the trace so the
                    # user-facing response still has context.
                    trace.append(ThoughtTrace(
                        timestamp=time.time(), category="refine",
                        content="LLM Enhancement skipped (no result; rate-limit or provider error)",
                        module="MicroAgentPool",
                        confidence=0.0,
                    ))
            except Exception as e:
                logger.debug(f"Response enhancement failed: {e}")
                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="refine",
                    content=f"LLM Enhancement error: {str(e)[:100]}",
                    module="MicroAgentPool",
                    confidence=0.0,
                ))

        # ── Step 3.5: Assemble Full Context ──
        context_bundle = self._assemble_context(
            message, topics, entries, synthesis_insights,
            response_enhancement
        )
        if context_bundle.total_items > 0:
            trace.append(ThoughtTrace(
                timestamp=time.time(), category="context",
                content=(
                    f"Assembled {context_bundle.total_items} context items "
                    f"({len(context_bundle.learned_facts)} learned, "
                    f"{len(context_bundle.background_insights)} thoughts, "
                    f"{len(context_bundle.stream_thoughts)} stream) "
                    f"in {context_bundle.assembly_time_ms:.1f}ms"
                ),
                module="ContextAssembler",
                confidence=0.6,
            ))

        # ── Step 4: Speaking (TalkerModule) ──
        t_speak = time.time()

        if self._talker:
            try:
                thought_input = unified_thought if unified_thought else {
                    'narrative': f"The user asks: {message[:200]}",
                    'confidence': response.confidence,
                    'emotional_tone': 0.0,
                    'key_facts': [e.content[:100] for e in entries[:3]] if entries else [],
                    'source_entry_ids': [e.id for e in entries[:5]] if entries else [],
                }

                # Inject assembled context into thought_input
                if context_bundle.total_items > 0:
                    extra_facts = (
                        context_bundle.learned_facts
                        + context_bundle.background_insights
                        + context_bundle.stream_thoughts
                    )
                    if isinstance(thought_input, dict):
                        existing = thought_input.get('key_facts', [])
                        thought_input['key_facts'] = existing + extra_facts
                        if context_bundle.conversation_context:
                            thought_input['narrative'] = (
                                thought_input.get('narrative', '')
                                + ' || Conversation context: '
                                + context_bundle.conversation_context
                            )
                    else:
                        existing = thought_input.key_facts or []
                        thought_input.key_facts = existing + extra_facts
                        if context_bundle.conversation_context:
                            thought_input.narrative = (
                                (thought_input.narrative or '')
                                + ' || Conversation context: '
                                + context_bundle.conversation_context
                            )

                # Inject augmented knowledge. LLM-refined response (if any)
                # takes priority over raw Wikipedia augmentation.
                primary_answer = ''
                if response_enhancement and response_enhancement.refined:
                    primary_answer = response_enhancement.refined
                elif augmented_answer:
                    primary_answer = augmented_answer
                if primary_answer:
                    if isinstance(thought_input, dict):
                        thought_input['augmented_answer'] = primary_answer
                        thought_input['confidence'] = max(
                            thought_input.get('confidence', 0.5), 0.75
                        )
                    else:
                        thought_input.augmented_answer = primary_answer
                        thought_input.confidence = max(thought_input.confidence, 0.75)

                talker_response = self._talker.speak(
                    thought_input, context=message, complexity=0.5,
                )
                response.response_text = talker_response.text
                response.confidence = talker_response.confidence

                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="speak",
                    content=f"Generated response: confidence={talker_response.confidence:.2f}",
                    module="TalkerModule",
                    confidence=talker_response.confidence,
                ))
            except Exception as e:
                logger.warning(f"Speaking failed: {e}")
                response.response_text = self._fallback_response(
                    message, entries, augmented_answer, topics
                )
        else:
            response.response_text = self._fallback_response(
                message, entries, augmented_answer, topics
            )

        response.speaking_time_ms = (time.time() - t_speak) * 1000
        response.thought_trace = trace
        response.total_time_ms = (time.time() - t0) * 1000

        # Record in continuous thinking
        self._record_response(response, original_message=message)

        # Push response into Qdrant KG (unified graph with bidirectional edges).
        # Async internally (batches + threading); non-blocking for us.
        if self._qdrant_kg and response.response_text:
            try:
                from core.qdrant_kg import ResponseDoc
                import uuid as _uuid
                self._qdrant_kg.upsert_response(ResponseDoc(
                    response_id=str(_uuid.uuid4()),
                    content=response.response_text[:2000],
                    user_query=message[:500],
                    routing_mode=response.routing_mode or "",
                    task_type=response.task_type or "",
                    confidence=float(response.confidence or 0.0),
                    llm_model=(
                        response_enhancement.agent
                        if response_enhancement else ""
                    ),
                    thinking_time_ms=float(response.thinking_time_ms or 0.0),
                    source="brain_chat",
                    tags=[],
                    metadata={},
                ))
            except Exception as e:
                logger.debug(f"KG response upsert failed: {e}")

        # Queue brain event for memory consolidation
        if self._memory_consolidator:
            try:
                self._memory_consolidator.queue_brain_event({
                    'state': {'user_input': message[:100], 'mode': 'chat'},
                    'action': 'chat_response',
                    'next_state': {
                        'response_len': len(response.response_text or ''),
                        'task_type': response.task_type,
                    },
                    'reward': response.confidence,
                    'done': True,
                    'metadata': {
                        'task_type': response.task_type,
                        'routing_mode': response.routing_mode,
                        'total_time_ms': response.total_time_ms,
                    },
                })
            except Exception:
                pass

        # Phase F.4 — Auto-dispatch: if user @-mentioned a known Minibook
        # agent, forward the task in parallel to Brain's own response.
        if self._auto_dispatcher is not None:
            try:
                dr = self._auto_dispatcher.maybe_dispatch(message)
                if dr:
                    response.auto_dispatch = dr
                    trace.append(ThoughtTrace(
                        timestamp=time.time(), category="dispatch",
                        content=(
                            f"Auto-dispatched to {dr.get('agents')} "
                            f"(post {dr.get('post_id')})"
                        ),
                        module="AutoDispatcher",
                        confidence=0.9,
                    ))
            except Exception as e:
                logger.debug(f"AutoDispatcher hook failed: {e}")

        # Phase R+ — Discourse-Response queue: every Brain response
        # gets queued for a 30s-tick post-hoc agent assessment ("was
        # the answer good, what's missing"). Light-weight, async.
        try:
            de = getattr(self, "_discourse_engine", None)
            if de is not None and response.response_text:
                de.queue_response(response.response_text, {
                    "task_type": response.task_type,
                    "confidence": response.confidence,
                    "user_message": message[:200],
                })
        except Exception as e:
            logger.debug(f"DiscourseEngine response queue failed: {e}")

        return response

    def _quick_intent(self, text: str) -> tuple:
        """Quick greeting/identity detection — no heavy analysis.

        Only triggers for SHORT messages that are clearly greetings or
        identity questions. Long messages (>12 words) are never short-circuited.
        Uses word-boundary matching to prevent 'what are you' matching 'what are your'.
        """
        text_lower = text.lower().strip()
        text_nopunct = text_lower.replace('?', '').replace('!', '').replace(',', '').strip()
        clean_words = [w.strip('.,!?;:') for w in text_lower.split() if w.strip('.,!?;:')]
        word_count = len(clean_words)
        clean_set = set(clean_words)

        # Long messages are NEVER greetings/identity — skip entirely
        if word_count > 12:
            return False, False

        # Identity questions — use word-boundary matching (regex)
        # Prevents "what are you" from matching "what are your"
        is_identity = any(
            re.search(r'\b' + re.escape(p) + r'\b', text_nopunct)
            for p in self._IDENTITY_PATTERNS
        )

        # Simple greeting: single-word match OR multi-word phrase match
        word_match = bool(clean_set & self._GREETING_WORDS)
        phrase_match = any(p in text_nopunct for p in self._GREETING_PHRASES)
        is_greeting = (word_count <= 8 and (word_match or phrase_match))

        return is_greeting or is_identity, is_identity

    def _route_through_thalamus(self, message: str, trace: list) -> Dict[str, Any]:
        """Route through the thalamic system. Primary: ThalamoPC6, Fallback: 3-layer."""
        routing_info = {
            'mode': 'routine',
            'weights': [],
            'dominant_areas': [],
            'task_type': 'general',
            'predicted_sequence': [],
            'confidence': 0.5,
        }

        # Attach a graph-kNN-based routing prior if the KG is available.
        # This replaces the learned space_routing_head.pt / event_routing_head.pt
        # with a usage-weighted, gradient-free prior derived from the unified
        # knowledge graph. ThalamoPC6 still makes the final modality decision,
        # but downstream modules can read `routing_info['kg_prior']`.
        if self._qdrant_kg is not None:
            try:
                # Route lookups hit only the procedural collection. This
                # keeps user-facing routing queries clear of thought/
                # bubble noise that shares semantic space.
                spaces = self._qdrant_kg.search(
                    message, node_type="space", collection="procedural",
                    limit=3, score_threshold=0.3,
                )
                events = self._qdrant_kg.search(
                    message, node_type="event", collection="procedural",
                    limit=3, score_threshold=0.3,
                )
                kg_prior = {
                    "spaces": [{
                        "id": s["payload"].get("space_id"),
                        "score": s["score"],
                        "activation": s["payload"].get("activation_strength", 0.0),
                    } for s in spaces],
                    "events": [{
                        "id": e["payload"].get("event_id"),
                        "score": e["score"],
                        "target_space": e["payload"].get("target_space"),
                    } for e in events],
                }
                routing_info['kg_prior'] = kg_prior
                # Top event drives the task_type suggestion when confident.
                if events and events[0]["score"] >= 0.5:
                    routing_info['task_type'] = events[0]["payload"].get("event_id", "general")
                    routing_info['space_hint'] = events[0]["payload"].get("target_space")
                if spaces:
                    top_space = spaces[0]['payload'].get('space_id', '?')
                    top_space_score = spaces[0]['score']
                    if events:
                        top_event = events[0]['payload'].get('event_id', '?')
                        top_event_score = events[0]['score']
                    else:
                        top_event = '-'
                        top_event_score = 0.0
                    trace.append(ThoughtTrace(
                        timestamp=time.time(), category="routing",
                        content=(
                            f"KG prior: space={top_space} ({top_space_score:.2f}), "
                            f"event={top_event} ({top_event_score:.2f})"
                        ),
                        module="QdrantKG",
                        confidence=top_space_score,
                    ))
            except Exception as e:
                logger.debug(f"KG routing prior failed: {e}")

            # Phase S — self-awareness lookup. When the user asks about Brain
            # itself ("was bist du?", "deine architektur", "what do you do"),
            # surface the self-awareness substrate (S.1) + cross-session memory
            # (S.5 recall) so the response can quote actual modules and past
            # discourse instead of hallucinating.
            if _looks_like_self_query(message):
                try:
                    self_concepts = self._qdrant_kg.search(
                        message, collection="semantic",
                        node_type="concept", limit=5, score_threshold=0.25,
                    )
                    # Filter to seeded architecture concepts only
                    self_concepts = [
                        c for c in self_concepts
                        if (c.get("payload") or {}).get("self_awareness")
                    ]
                    routing_info['self_awareness'] = {
                        "concepts": [{
                            "title": c["payload"].get("title"),
                            "subsystem": c["payload"].get("subsystem"),
                            "snippet": (c["payload"].get("content") or "")[:200],
                            "score": c["score"],
                        } for c in self_concepts[:5]],
                    }
                    if self_concepts:
                        trace.append(ThoughtTrace(
                            timestamp=time.time(), category="self_awareness",
                            content=(
                                f"Self-aware concepts: "
                                + ", ".join(
                                    c["payload"].get("title", "?")
                                    for c in self_concepts[:3]
                                )
                            ),
                            module="QdrantKG",
                            confidence=self_concepts[0]["score"],
                        ))
                    # S.5 recall — historical memory of what Brain has thought
                    # about this topic across past discourse aggregations.
                    dmc = getattr(self, "_discourse_memory_consolidator", None)
                    if dmc is not None:
                        try:
                            recall = dmc.recall(message, days=14, limit=3)
                            if recall.get("ok") and recall.get("results"):
                                routing_info['self_awareness']['recall'] = (
                                    recall["results"]
                                )
                                trace.append(ThoughtTrace(
                                    timestamp=time.time(),
                                    category="self_awareness_recall",
                                    content=(
                                        f"Recalled {len(recall['results'])} "
                                        f"past discourse items"
                                    ),
                                    module="DiscourseMemoryConsolidator",
                                    confidence=recall["results"][0].get("score", 0.0),
                                ))
                        except Exception as e:
                            logger.debug(f"recall failed: {e}")
                except Exception as e:
                    logger.debug(f"self-awareness lookup failed: {e}")

        # PRIMARY: ThalamoPC6 via ThalamicAdapter
        if self._thalamic_adapter:
            try:
                result = self._thalamic_adapter.process("chat", {"message": message})
                self._total_routed += 1
                routing_info['mode'] = 'thalamic'
                routing_info['weights'] = list(result['gates'].values())
                routing_info['dominant_areas'] = result['active_modalities']
                routing_info['task_type'] = 'thalamic_routed'
                routing_info['confidence'] = float(max(result['gates'].values()))
                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="routing",
                    content=(
                        f"ThalamoPC6 routing: active={result['active_modalities']}, "
                        f"gates={', '.join(f'{m}={g:.2f}' for m, g in result['gates'].items())}"
                    ),
                    module="ThalamoPC6",
                    confidence=routing_info['confidence'],
                ))
                return routing_info
            except Exception as e:
                logger.warning(f"ThalamoPC6 routing failed: {e}")

        # FALLBACK: HierarchicalPlanner (existing 3-layer)
        if self._hierarchical_planner:
            try:
                prediction = self._hierarchical_planner.predict(message)
                self._total_routed += 1

                routing_info['mode'] = prediction.layer1_routing.processing_mode
                weights = prediction.layer1_routing.routing_weights
                routing_info['weights'] = (
                    weights.tolist() if hasattr(weights, 'tolist') else list(weights)
                ) if weights is not None else []
                routing_info['dominant_areas'] = prediction.layer1_routing.dominant_areas or []
                routing_info['task_type'] = prediction.task_type
                routing_info['predicted_sequence'] = prediction.predicted_sequence
                routing_info['confidence'] = prediction.confidence

                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="routing",
                    content=(
                        f"Thalamus routing: mode={routing_info['mode']}, "
                        f"type={routing_info['task_type']}, "
                        f"confidence={routing_info['confidence']:.2f}, "
                        f"areas={routing_info['dominant_areas'][:3]}"
                    ),
                    module="HierarchicalPlanner",
                    confidence=routing_info['confidence'],
                ))
                return routing_info
            except Exception as e:
                logger.warning(f"HierarchicalPlanner routing failed: {e}")

        # Fallback: just Layer 1
        if self._l1_router:
            try:
                l1 = self._l1_router.route_task(message)
                self._total_routed += 1
                routing_info['mode'] = l1.processing_mode
                weights = l1.routing_weights
                routing_info['weights'] = (
                    weights.tolist() if hasattr(weights, 'tolist') else list(weights)
                ) if weights is not None else []
                routing_info['dominant_areas'] = l1.dominant_areas or []
                routing_info['task_type'] = l1.features.task_type if l1.features else 'general'

                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="routing",
                    content=f"L1 routing: mode={routing_info['mode']}, type={routing_info['task_type']}",
                    module="TaskFeatureRouter",
                    confidence=0.6,
                ))
            except Exception as e:
                logger.warning(f"L1 routing failed: {e}")

        # Fallback: use InputAnalyzer
        if not routing_info['dominant_areas'] and self._analyzer:
            try:
                analysis = self._analyzer.analyze(message)
                routing_info['task_type'] = analysis.intent
                routing_info['mode'] = (
                    'analytical' if analysis.complexity > 0.7
                    else 'routine' if analysis.complexity < 0.3
                    else 'creative'
                )
                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="routing",
                    content=f"InputAnalyzer fallback: intent={analysis.intent}, complexity={analysis.complexity:.2f}",
                    module="InputAnalyzer",
                    confidence=0.4,
                ))
            except Exception:
                pass

        return routing_info

    def _retrieve_knowledge(self, message: str, trace: list):
        """Retrieve relevant knowledge from Moltbook."""
        entries = []
        max_similarity = 0.0
        topics = []

        if not self._moltbook:
            return entries, max_similarity, topics

        try:
            scored_entries = self._moltbook.query_semantic(
                message, top_k=7, threshold=0.15, return_scores=True,
            )
            if scored_entries:
                entries = [e for e, _, _ in scored_entries]
                max_similarity = max(sim for _, sim, _ in scored_entries)

                trace.append(ThoughtTrace(
                    timestamp=time.time(), category="retrieval",
                    content=f"Retrieved {len(entries)} entries, max_similarity={max_similarity:.3f}",
                    module="MoltbookStore",
                    confidence=max_similarity,
                ))
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")

        # Extract topics
        if self._analyzer:
            try:
                analysis = self._analyzer.analyze(message)
                topics = analysis.topics
            except Exception:
                # Simple fallback topic extraction
                stopwords = {'the', 'a', 'is', 'are', 'what', 'how', 'why', 'and', 'or'}
                topics = [w for w in message.lower().split()
                         if w not in stopwords and len(w) > 2][:5]
        else:
            stopwords = {'the', 'a', 'is', 'are', 'what', 'how', 'why', 'and', 'or'}
            topics = [w for w in message.lower().split()
                     if w not in stopwords and len(w) > 2][:5]

        return entries, max_similarity, topics

    def _fallback_response(self, message: str, entries: list,
                           augmented_answer: str, topics: list) -> str:
        """Generate a response without TalkerModule."""
        if augmented_answer and len(augmented_answer) > 20:
            return augmented_answer

        if entries:
            best = entries[0]
            content = best.content if hasattr(best, 'content') else str(best)
            return content[:500]

        topic_str = ', '.join(topics[:3]) if topics else message[:100]
        return f"I don't have specific knowledge about {topic_str} yet, but I'm always learning!"

    def _record_response(self, response: BrainChatResponse,
                         original_message: str = "") -> None:
        """Record the response in continuous thinking + MoltbookStore."""
        if self._continuous_thinking:
            self._continuous_thinking.record_response(
                response=response.response_text[:300],
                topic=original_message or response.task_type or "",
                source=response.augment_source or "",
                augmented=response.augmented,
            )

            # Reward feedback: successful response → reinforce recent thought pathways
            bridge = getattr(self._continuous_thinking, '_thought_radial_bridge', None)
            last_thought = getattr(self._continuous_thinking, '_last_processed_thought', None)
            if bridge is not None and last_thought is not None:
                thought_id = getattr(last_thought, 'thought_id', '')
                if thought_id:
                    # Scale reward by response confidence
                    reward = 0.2 + 0.3 * getattr(response, 'confidence', 0.5)
                    bridge.record_reward(
                        thought_id=thought_id,
                        reward=reward,
                        outcome="response_generated",
                    )

            # Go back to idle after responding
            self._continuous_thinking._mode = "idle"

        # Auto-feed into MoltbookStore for persistent knowledge
        if (self._moltbook_feeder
                and response.response_text
                and len(response.response_text.strip()) > 20):
            try:
                self._moltbook_feeder.post(
                    content=response.response_text[:500],
                    tags=[response.task_type or "chat",
                          response.routing_mode or "routine"],
                    confidence=min(response.confidence, 0.8),
                )
                # Outcome reward: thought → Moltbook entry
                if hasattr(self, '_outcome_tracker') and self._outcome_tracker:
                    last = getattr(self._continuous_thinking, '_last_processed_thought', None)
                    if last and getattr(last, 'thought_id', ''):
                        self._outcome_tracker.on_moltbook_entry(last.thought_id)
            except Exception:
                pass  # non-critical

    def _assemble_context(self, message: str,
                          topics: List[str],
                          retrieved_entries: list = None,
                          synthesis_insights: list = None,
                          response_enhancement: 'RefinedKnowledge' = None,
                          ) -> ContextBundle:
        """
        Gather ALL relevant knowledge from every available source.

        Called between thinking and speaking to enrich thought_input
        with maximum context for TalkerModule.

        Performance budget: < 50ms (all operations are in-memory).
        """
        t0 = time.time()
        bundle = ContextBundle()

        if not self._continuous_thinking:
            bundle.assembly_time_ms = (time.time() - t0) * 1000
            return bundle

        # Build topic set for relevance filtering
        topic_set = set(t.lower() for t in topics) if topics else set()
        msg_words = set(w.lower().strip('.,!?;:') for w in message.split()
                        if len(w) > 2)
        topic_set = topic_set | msg_words

        # ── Source 1: Learned knowledge (topic overlap filter) ──
        # Max 3 entries, max 200 chars each
        learned = self._continuous_thinking.get_learned_knowledge(30)
        for entry in learned:
            entry_words = set(entry.get('topic', '').lower().split())
            knowledge_words = set(
                entry.get('knowledge', '').lower().split()[:20]
            )
            overlap = len(topic_set & (entry_words | knowledge_words))
            if overlap >= 1:
                snippet = entry.get('knowledge', '')[:200].strip()
                if snippet and snippet not in bundle.learned_facts:
                    bundle.learned_facts.append(snippet)
            if len(bundle.learned_facts) >= 3:
                break

        # ── Source 2: Background thoughts (relevance filter) ──
        # Max 3 thoughts, max 150 chars each, only knowledge/active/reflect
        recent_thoughts = self._continuous_thinking.get_recent_thoughts(30)
        scored = []
        for thought in recent_thoughts:
            if thought.category in ('knowledge', 'active', 'reflect', 'expansion', 'synthesis', 'refine'):
                thought_words = set(thought.content.lower().split()[:15])
                overlap = len(topic_set & thought_words)
                if overlap >= 1:
                    scored.append((overlap, thought))
        scored.sort(key=lambda x: x[0], reverse=True)
        cited_thoughts = []
        for _, thought in scored[:3]:
            snippet = thought.content[:150].strip()
            if len(snippet) > 30 and snippet not in bundle.background_insights:
                bundle.background_insights.append(snippet)
                cited_thoughts.append(thought)
        # Outcome reward: thoughts cited in response
        if hasattr(self, '_outcome_tracker') and self._outcome_tracker and cited_thoughts:
            cited_ids = [t.thought_id for t in cited_thoughts
                        if hasattr(t, 'thought_id') and t.thought_id]
            if cited_ids:
                self._outcome_tracker.on_thoughts_cited(cited_ids)

        # ── Source 3: Conversation history (last relevant turns) ──
        # Provides continuity for follow-up questions
        history = self._continuous_thinking.get_conversation_history(10)
        recent_turns = []
        for turn in reversed(history):
            turn_content = turn.get('content', '')
            turn_words = set(turn_content.lower().split()[:15])
            overlap = len(topic_set & turn_words)
            if overlap >= 1 and len(turn_content) > 20:
                prefix = "User: " if turn.get('type') == 'user' else "Brain: "
                recent_turns.append(prefix + turn_content[:120])
            if len(recent_turns) >= 3:
                break
        if recent_turns:
            recent_turns.reverse()  # Chronological order
            bundle.conversation_context = " | ".join(recent_turns)

        # ── Source 4: ThoughtStream relevant thoughts ──
        # Max 2 thoughts, max 150 chars each
        if self._continuous_thinking._thought_stream:
            try:
                stream_thoughts = (
                    self._continuous_thinking._thought_stream
                    .get_relevant_thoughts(message, top_k=3)
                )
                for mt in stream_thoughts:
                    snippet = mt.content[:150].strip()
                    if (len(snippet) > 30
                            and "Thinking about:" not in snippet
                            and snippet not in bundle.stream_thoughts):
                        bundle.stream_thoughts.append(snippet)
                    if len(bundle.stream_thoughts) >= 2:
                        break
            except Exception:
                pass

        # ── Source 5: Graph-connected knowledge ──
        # Use KnowledgeExpander to get linked entries from the Moltbook graph
        if self._knowledge_expander and retrieved_entries:
            try:
                entry_ids = [
                    e.id for e in retrieved_entries
                    if hasattr(e, 'id')
                ][:5]
                if entry_ids:
                    graph_facts = (
                        self._knowledge_expander.get_graph_context(entry_ids)
                    )
                    for fact in graph_facts[:2]:
                        if (fact not in bundle.learned_facts
                                and fact not in bundle.background_insights):
                            bundle.learned_facts.append(fact)
            except Exception:
                pass

        # ── Source 6: Synthesized insights ──
        # From response-path synthesis check (contradictions, gaps)
        # and from background synthesis thoughts
        if synthesis_insights:
            for insight in synthesis_insights[:2]:
                snippet = insight.content[:200].strip()
                if (snippet
                        and snippet not in bundle.learned_facts
                        and snippet not in bundle.background_insights):
                    bundle.background_insights.append(snippet)

        # Also include recent background "synthesis" category thoughts
        if self._continuous_thinking:
            try:
                bg_thoughts = self._continuous_thinking.get_recent_thoughts(30)
                for thought in bg_thoughts:
                    if thought.category == 'synthesis' and thought.relevance > 0.4:
                        thought_words = set(thought.content.lower().split()[:20])
                        overlap = len(topic_set & thought_words)
                        if overlap >= 1:
                            snippet = thought.content[:200].strip()
                            if (snippet
                                    and snippet not in bundle.learned_facts
                                    and snippet not in bundle.background_insights):
                                bundle.background_insights.append(snippet)
                            if len(bundle.background_insights) >= 5:
                                break
            except Exception:
                pass

        # ── Source 7: LLM-refined knowledge ──
        # Responder enhancement from send() path + cached background refinements
        if response_enhancement:
            snippet = response_enhancement.refined[:200].strip()
            if (snippet
                    and snippet not in bundle.learned_facts
                    and snippet not in bundle.background_insights):
                bundle.background_insights.append(snippet)

        # Also include recent background "refine" category thoughts
        if self._continuous_thinking and self._micro_agent_pool:
            try:
                for ref in self._micro_agent_pool.get_recent_refinements(
                    ' '.join(topics[:3]) if topics else '', limit=2
                ):
                    snippet = ref.refined[:200].strip()
                    if (snippet
                            and snippet not in bundle.learned_facts
                            and snippet not in bundle.background_insights):
                        bundle.background_insights.append(snippet)
                    if len(bundle.background_insights) >= 7:
                        break
            except Exception:
                pass

        bundle.total_items = (
            len(bundle.learned_facts)
            + len(bundle.background_insights)
            + (1 if bundle.conversation_context else 0)
            + len(bundle.stream_thoughts)
        )
        bundle.assembly_time_ms = (time.time() - t0) * 1000
        return bundle

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            'total_messages': self._total_messages,
            'total_routed': self._total_routed,
            'continuous_thinking': (
                self._continuous_thinking.get_stats()
                if self._continuous_thinking else None
            ),
        }
        if self._knowledge_expander:
            stats['knowledge_expander'] = self._knowledge_expander.get_stats()
        if self._knowledge_synthesizer:
            stats['knowledge_synthesizer'] = (
                self._knowledge_synthesizer.get_stats()
            )
        if self._micro_agent_pool:
            stats['micro_agent_pool'] = (
                self._micro_agent_pool.get_stats()
            )
        return stats

