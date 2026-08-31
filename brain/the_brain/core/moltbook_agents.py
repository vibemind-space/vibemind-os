"""
Moltbook Agents — Knowledge Feeding, Evaluation, Curation, Research, Feedback

Provides:
  - MoltbookFeeder:     Agent-to-Moltbook interface (post/comment/@mention)
  - EvaluationAgent:    Quality scoring (relevance, novelty, consistency)
  - CurationAgent:      Consolidation, merging, clustering, pruning
  - ResearchAgent:      Proactive knowledge gathering via gap detection
  - FeedbackAgent:      User feedback integration (uprank/downrank)

Architecture Inspirations:
  - A-MEM (arxiv 2502.12110) — Agentic Memory: agents feeding shared memory
  - MoA (ICLR 2025) — Mixture of Agents: Proposer/Aggregator pattern
  - OFC reversal learning — Value updates based on outcome prediction errors
  - Knowledge Gap Detection — Proactive research driven by failure patterns
"""

from __future__ import annotations

import logging
import time
import math
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger('brain.moltbook.agents')


# ═══════════════════════════════════════════════════════════════════
# Data Types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class EvaluationResult:
    """Result of evaluating a knowledge entry."""
    entry_id: str = ""
    relevance_score: float = 0.5
    novelty_score: float = 0.5
    consistency_score: float = 0.5
    overall_quality: float = 0.5
    recommendation: str = "keep"  # keep / demote / promote / flag
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'entry_id': self.entry_id,
            'relevance': self.relevance_score,
            'novelty': self.novelty_score,
            'consistency': self.consistency_score,
            'overall': self.overall_quality,
            'recommendation': self.recommendation,
            'reason': self.reason,
        }


@dataclass
class CurationAction:
    """Record of a curation action taken."""
    action_type: str = ""    # merge / prune / cluster / summarize
    entry_ids: List[str] = field(default_factory=list)
    result_id: Optional[str] = None  # ID of new/merged entry
    timestamp: float = field(default_factory=time.time)
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action': self.action_type,
            'entries': self.entry_ids,
            'result': self.result_id,
            'timestamp': self.timestamp,
            'details': self.details,
        }


@dataclass
class FeedbackRecord:
    """Record of user feedback on a response."""
    response_id: str = ""
    sentiment: float = 0.0       # -1 (negative) to +1 (positive)
    contributing_entries: List[str] = field(default_factory=list)
    correction: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'response_id': self.response_id,
            'sentiment': self.sentiment,
            'contributing_entries': self.contributing_entries,
            'correction': self.correction,
            'timestamp': self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════
# [6] MoltbookFeeder — Agent-to-Moltbook Interface
# ═══════════════════════════════════════════════════════════════════

class MoltbookFeeder:
    """
    Interface for all agents to feed knowledge into the Moltbook.

    Each agent has its own "channel" (source_agent name). The feeder
    provides a clean API for posting knowledge, commenting on entries,
    and @mentioning entries for cross-referencing.

    Usage:
        feeder = MoltbookFeeder(moltbook=store, agent_name="research_agent")
        entry = feeder.post("Python GIL prevents true parallelism", tags=["python"])
        feeder.comment(entry.id, "But multiprocessing bypasses it")
        feeder.mention(entry.id, related_entry.id, "supports")
    """

    def __init__(self, moltbook=None, agent_name: str = "unknown",
                 graph=None):
        self._moltbook = moltbook        # MoltbookStore
        self._graph = graph              # MoltbookGraph (optional)
        self._agent_name = agent_name
        self._post_count = 0
        self._comment_count = 0
        self._mention_count = 0
        self._channel_log: deque = deque(maxlen=200)
        logger.info(f"MoltbookFeeder initialized for agent '{agent_name}'")

    @property
    def agent_name(self) -> str:
        return self._agent_name

    def post(self, content: str, tags: Optional[List[str]] = None,
             confidence: float = 0.5, entry_type: str = "post",
             emotional_valence: float = 0.0,
             metadata: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """
        Post new knowledge to the Moltbook.

        Args:
            content: Knowledge content text
            tags: Categorization tags
            confidence: Confidence in this knowledge (0-1)
            entry_type: Type (post/knowledge/thought/experience)
            emotional_valence: Emotional charge (-1 to +1)
            metadata: Extra metadata

        Returns:
            The created MoltbookEntry, or None if store unavailable
        """
        if not self._moltbook:
            logger.warning(f"Feeder '{self._agent_name}': no MoltbookStore connected")
            return None

        if not content.strip():
            return None

        try:
            entry = self._moltbook.add_entry(
                content=content,
                source_agent=self._agent_name,
                entry_type=entry_type,
                tags=tags or [],
                confidence=confidence,
                emotional_valence=emotional_valence,
                metadata=metadata or {},
            )
            self._post_count += 1
            self._channel_log.append({
                'action': 'post',
                'entry_id': entry.id,
                'timestamp': time.time(),
            })
            logger.debug(f"Feeder '{self._agent_name}' posted: {content[:60]}...")
            return entry
        except Exception as e:
            logger.error(f"Feeder post failed: {e}")
            return None

    def comment(self, entry_id: str, comment_content: str,
                confidence: float = 0.5) -> Optional[Any]:
        """
        Comment on an existing entry (creates linked child entry).

        The comment is stored as a new entry linked to the parent
        with a "comments" relationship.
        """
        if not self._moltbook:
            return None

        if not comment_content.strip():
            return None

        try:
            # Create the comment as a new entry
            comment_entry = self._moltbook.add_entry(
                content=comment_content,
                source_agent=self._agent_name,
                entry_type="comment",
                confidence=confidence,
                linked_to={entry_id: "comments"},
            )

            # Also create reverse link on the graph if available
            if self._graph:
                try:
                    self._graph.link(
                        source_id=entry_id,
                        target_id=comment_entry.id,
                        link_type="has_comment",
                    )
                except Exception:
                    pass

            self._comment_count += 1
            self._channel_log.append({
                'action': 'comment',
                'parent_id': entry_id,
                'comment_id': comment_entry.id,
                'timestamp': time.time(),
            })
            return comment_entry
        except Exception as e:
            logger.error(f"Feeder comment failed: {e}")
            return None

    def mention(self, source_id: str, target_id: str,
                link_type: str = "relates_to") -> bool:
        """
        @mention: Create a semantic link between two entries.

        This triggers spreading activation so related knowledge
        gets pre-activated for future retrieval.
        """
        if not self._moltbook:
            return False

        try:
            linked = self._moltbook.link_entries(source_id, target_id, link_type)
            if linked:
                self._mention_count += 1
                self._channel_log.append({
                    'action': 'mention',
                    'source_id': source_id,
                    'target_id': target_id,
                    'link_type': link_type,
                    'timestamp': time.time(),
                })

            # Also link in graph if available
            if self._graph and linked:
                try:
                    self._graph.link(source_id, target_id, link_type)
                except Exception:
                    pass

            return linked
        except Exception as e:
            logger.error(f"Feeder mention failed: {e}")
            return False

    def get_channel_log(self, n: int = 20) -> List[Dict[str, Any]]:
        """Get recent channel activity."""
        entries = list(self._channel_log)
        return entries[-n:]

    def get_stats(self) -> Dict[str, Any]:
        return {
            'agent_name': self._agent_name,
            'posts': self._post_count,
            'comments': self._comment_count,
            'mentions': self._mention_count,
            'total_actions': self._post_count + self._comment_count + self._mention_count,
        }


# ═══════════════════════════════════════════════════════════════════
# [7] EvaluationAgent — Knowledge Quality Scoring
# ═══════════════════════════════════════════════════════════════════

class EvaluationAgent:
    """
    Evaluates incoming knowledge entries for quality.

    Scoring dimensions:
      - Relevance: How relevant is this to current brain purposes?
      - Novelty: Does it add new information vs. what's already known?
      - Consistency: Does it contradict existing knowledge?

    Low-scored entries get lower retrieval priority.
    Uses OFC reversal_learning_signal() for value updates when
    expected vs actual quality diverge.
    """

    def __init__(self, moltbook=None, ofc=None, semantic_index=None):
        self._moltbook = moltbook            # MoltbookStore
        self._ofc = ofc                      # OrbitofrontalCortex (optional)
        self._semantic_index = semantic_index  # SemanticIndex (optional)
        self._total_evaluated = 0
        self._total_promoted = 0
        self._total_demoted = 0
        self._evaluation_history: deque = deque(maxlen=300)
        self._quality_thresholds = {
            'promote': 0.75,
            'keep': 0.35,
            'demote': 0.2,
        }
        logger.info("EvaluationAgent initialized")

    def evaluate(self, entry) -> EvaluationResult:
        """
        Evaluate a single MoltbookEntry for quality.

        Args:
            entry: A MoltbookEntry object

        Returns:
            EvaluationResult with scores and recommendation
        """
        self._total_evaluated += 1
        result = EvaluationResult(entry_id=getattr(entry, 'id', ''))

        # ── Relevance scoring ──
        result.relevance_score = self._score_relevance(entry)

        # ── Novelty scoring ──
        result.novelty_score = self._score_novelty(entry)

        # ── Consistency scoring ──
        result.consistency_score = self._score_consistency(entry)

        # ── Overall quality ──
        # Weighted combination: novelty matters most (new info > redundant)
        result.overall_quality = (
            0.3 * result.relevance_score +
            0.4 * result.novelty_score +
            0.3 * result.consistency_score
        )

        # ── Recommendation ──
        if result.overall_quality >= self._quality_thresholds['promote']:
            result.recommendation = "promote"
            result.reason = "High quality: novel, relevant, consistent"
            self._total_promoted += 1
        elif result.overall_quality >= self._quality_thresholds['keep']:
            result.recommendation = "keep"
            result.reason = "Acceptable quality"
        elif result.overall_quality >= self._quality_thresholds['demote']:
            result.recommendation = "demote"
            result.reason = "Low quality: may be redundant or inconsistent"
            self._total_demoted += 1
        else:
            result.recommendation = "flag"
            result.reason = "Very low quality: review needed"
            self._total_demoted += 1

        # ── OFC reversal learning signal ──
        if self._ofc:
            try:
                expected_quality = getattr(entry, 'confidence', 0.5)
                self._ofc.reversal_learning_signal(
                    expected_outcome=expected_quality,
                    actual_outcome=result.overall_quality,
                )
            except Exception:
                pass

        self._evaluation_history.append(result.to_dict())
        return result

    def evaluate_batch(self, entries: list) -> List[EvaluationResult]:
        """Evaluate a batch of entries."""
        return [self.evaluate(e) for e in entries]

    def _score_relevance(self, entry) -> float:
        """Score relevance based on content quality signals."""
        content = getattr(entry, 'content', '')
        if not content:
            return 0.0

        score = 0.5  # base

        # Length: too short or too long → less relevant
        words = content.split()
        word_count = len(words)
        if 10 <= word_count <= 200:
            score += 0.2
        elif word_count < 5:
            score -= 0.2

        # Has tags → more organized → more relevant
        tags = getattr(entry, 'tags', [])
        if tags:
            score += 0.1

        # Confidence from source agent
        confidence = getattr(entry, 'confidence', 0.5)
        score += (confidence - 0.5) * 0.3

        # Accessed before → has proven useful
        accessed = getattr(entry, 'accessed_count', 0)
        if accessed > 0:
            score += min(0.2, 0.05 * accessed)

        return max(0.0, min(1.0, score))

    def _score_novelty(self, entry) -> float:
        """Score novelty: how different is this from existing knowledge?"""
        content = getattr(entry, 'content', '')
        if not content or not self._moltbook:
            return 0.5  # can't assess without store

        try:
            # Search for similar entries
            similar = self._moltbook.query_semantic(content, top_k=3, threshold=0.5)
            if not similar:
                return 0.9  # Nothing similar → very novel

            # Check if any are nearly identical
            for s in similar:
                if getattr(s, 'id', '') == getattr(entry, 'id', ''):
                    continue
                s_content = getattr(s, 'content', '')
                # Simple word overlap check
                entry_words = set(content.lower().split())
                s_words = set(s_content.lower().split())
                if entry_words and s_words:
                    overlap = len(entry_words & s_words) / max(len(entry_words), 1)
                    if overlap > 0.8:
                        return 0.1  # Nearly duplicate
                    elif overlap > 0.5:
                        return 0.3  # Quite similar

            # Some similar entries found but not duplicates
            return 0.6
        except Exception:
            return 0.5

    def _score_consistency(self, entry) -> float:
        """Score consistency with existing knowledge."""
        content = getattr(entry, 'content', '')
        if not content or not self._moltbook:
            return 0.7  # assume consistent if can't check

        try:
            # Look for contradictions via linked entries
            linked = getattr(entry, 'linked_entries', {})
            contradiction_count = sum(
                1 for lt in linked.values() if lt == 'contradicts'
            )
            if contradiction_count > 0:
                return max(0.1, 0.7 - 0.2 * contradiction_count)

            # Check emotional alignment with similar entries
            similar = self._moltbook.query_semantic(content, top_k=3, threshold=0.5)
            if similar:
                entry_valence = getattr(entry, 'emotional_valence', 0.0)
                avg_valence = sum(
                    getattr(s, 'emotional_valence', 0.0) for s in similar
                ) / max(1, len(similar))
                valence_diff = abs(entry_valence - avg_valence)
                if valence_diff > 1.0:
                    return 0.4  # Emotionally inconsistent
                return 0.7 + 0.3 * (1.0 - valence_diff)

            return 0.7
        except Exception:
            return 0.7

    def apply_evaluation(self, entry, result: EvaluationResult) -> None:
        """Apply evaluation result to the entry (modify in-place)."""
        if result.recommendation == "promote":
            entry.relevance_score = min(1.0, entry.relevance_score + 0.15)
            entry.confidence = min(1.0, entry.confidence + 0.1)
        elif result.recommendation == "demote":
            entry.relevance_score = max(0.0, entry.relevance_score - 0.15)
            entry.confidence = max(0.0, entry.confidence - 0.1)
        elif result.recommendation == "flag":
            entry.relevance_score = max(0.0, entry.relevance_score - 0.25)
            if not hasattr(entry, 'metadata'):
                entry.metadata = {}
            entry.metadata['flagged'] = True

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_evaluated': self._total_evaluated,
            'total_promoted': self._total_promoted,
            'total_demoted': self._total_demoted,
            'promote_rate': self._total_promoted / max(1, self._total_evaluated),
            'demote_rate': self._total_demoted / max(1, self._total_evaluated),
        }


# ═══════════════════════════════════════════════════════════════════
# [8] CurationAgent — Knowledge Organization
# ═══════════════════════════════════════════════════════════════════

class CurationAgent:
    """
    Background agent for knowledge organization and maintenance.

    Operations:
      - Merge: Combine highly similar entries (>0.9 cosine) into one
      - Cluster: Auto-detect topic clusters and tag them
      - Prune: Remove stale, never-accessed entries
      - Summarize: Create summary entries for clusters

    Runs periodically or on-demand to keep the Moltbook clean.
    """

    def __init__(self, moltbook=None, semantic_index=None, graph=None,
                 merge_threshold: float = 0.85,
                 prune_min_age_hours: float = 48.0,
                 prune_min_accesses: int = 0):
        self._moltbook = moltbook              # MoltbookStore
        self._semantic_index = semantic_index    # SemanticIndex (optional)
        self._graph = graph                      # MoltbookGraph (optional)
        self._merge_threshold = merge_threshold
        self._prune_min_age = prune_min_age_hours * 3600  # Convert to seconds
        self._prune_min_accesses = prune_min_accesses
        self._total_merges = 0
        self._total_prunes = 0
        self._total_clusters_found = 0
        self._action_log: deque = deque(maxlen=200)
        logger.info("CurationAgent initialized")

    def curate(self) -> List[CurationAction]:
        """
        Run full curation cycle: merge → cluster → prune.

        Returns list of actions taken.
        """
        actions = []

        # Step 1: Merge similar entries
        merge_actions = self.merge_similar()
        actions.extend(merge_actions)

        # Step 2: Detect clusters
        cluster_actions = self.detect_clusters()
        actions.extend(cluster_actions)

        # Step 3: Prune stale entries
        prune_actions = self.prune_stale()
        actions.extend(prune_actions)

        return actions

    def merge_similar(self) -> List[CurationAction]:
        """
        Find and merge highly similar entries.

        Entries with >merge_threshold word overlap are merged:
        - Keep the one with higher confidence/access count
        - Transfer links from the merged entry
        - Update the survivor with combined tags
        """
        if not self._moltbook:
            return []

        actions = []
        try:
            all_entries = self._moltbook.get_active_entries(top_k=200)
            if len(all_entries) < 2:
                return []

            merged_ids: Set[str] = set()

            for i, entry_a in enumerate(all_entries):
                if entry_a.id in merged_ids:
                    continue
                for j in range(i + 1, len(all_entries)):
                    entry_b = all_entries[j]
                    if entry_b.id in merged_ids:
                        continue

                    # Compute word-level similarity
                    similarity = self._compute_similarity(entry_a, entry_b)
                    if similarity >= self._merge_threshold:
                        # Merge: keep the better one
                        survivor, consumed = self._pick_survivor(entry_a, entry_b)

                        # Transfer info from consumed to survivor
                        self._merge_entries(survivor, consumed)
                        merged_ids.add(consumed.id)

                        action = CurationAction(
                            action_type="merge",
                            entry_ids=[consumed.id, survivor.id],
                            result_id=survivor.id,
                            details=f"Merged (sim={similarity:.2f})",
                        )
                        actions.append(action)
                        self._total_merges += 1
                        self._action_log.append(action.to_dict())
        except Exception as e:
            logger.error(f"Merge failed: {e}")

        return actions

    def detect_clusters(self) -> List[CurationAction]:
        """
        Auto-detect topic clusters using tag co-occurrence.

        Groups entries by shared tags and suggests cluster labels.
        """
        if not self._moltbook:
            return []

        actions = []
        try:
            all_entries = self._moltbook.get_active_entries(top_k=200)
            if len(all_entries) < 3:
                return []

            # Group by shared tags
            tag_to_entries: Dict[str, List[str]] = defaultdict(list)
            for entry in all_entries:
                for tag in getattr(entry, 'tags', []):
                    tag_to_entries[tag].append(entry.id)

            # Find clusters: tags that co-occur in 3+ entries
            for tag, entry_ids in tag_to_entries.items():
                if len(entry_ids) >= 3:
                    action = CurationAction(
                        action_type="cluster",
                        entry_ids=entry_ids[:20],  # Cap at 20
                        details=f"Cluster around tag '{tag}' ({len(entry_ids)} entries)",
                    )
                    actions.append(action)
                    self._total_clusters_found += 1
                    self._action_log.append(action.to_dict())

            # Also try graph-based clustering if available
            if self._graph:
                try:
                    clusters = self._graph.find_clusters(min_cluster_size=3)
                    for cluster in clusters:
                        action = CurationAction(
                            action_type="cluster",
                            entry_ids=list(cluster)[:20],
                            details=f"Graph cluster ({len(cluster)} entries)",
                        )
                        actions.append(action)
                        self._total_clusters_found += 1
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Cluster detection failed: {e}")

        return actions

    def prune_stale(self) -> List[CurationAction]:
        """
        Remove stale, never-accessed entries older than threshold.

        Only prunes entries that:
        - Are older than prune_min_age
        - Have been accessed <= prune_min_accesses times
        - Have low relevance (<0.3)
        """
        if not self._moltbook:
            return []

        actions = []
        try:
            all_entries = self._moltbook.get_active_entries(top_k=500)
            current_time = time.time()
            prune_candidates = []

            for entry in all_entries:
                age = current_time - getattr(entry, 'created_at', current_time)
                accesses = getattr(entry, 'accessed_count', 0)
                relevance = getattr(entry, 'relevance_score', 0.5)

                if (age >= self._prune_min_age and
                        accesses <= self._prune_min_accesses and
                        relevance < 0.3):
                    prune_candidates.append(entry)

            for entry in prune_candidates:
                action = CurationAction(
                    action_type="prune",
                    entry_ids=[entry.id],
                    details=(f"Stale entry: age={int((current_time - entry.created_at) / 3600)}h, "
                             f"accesses={entry.accessed_count}, relevance={entry.relevance_score:.2f}"),
                )
                actions.append(action)
                self._total_prunes += 1
                self._action_log.append(action.to_dict())

                # Mark for removal (reduce relevance to near-zero)
                entry.relevance_score = 0.01
        except Exception as e:
            logger.error(f"Pruning failed: {e}")

        return actions

    def summarize_cluster(self, entry_ids: List[str]) -> Optional[Any]:
        """
        Create a summary entry for a cluster of related entries.

        Combines content from all entries in the cluster into one
        summary entry with higher confidence.
        """
        if not self._moltbook or not entry_ids:
            return None

        try:
            entries = []
            all_tags: Set[str] = set()
            for eid in entry_ids:
                entry = self._moltbook.get_entry(eid)
                if entry:
                    entries.append(entry)
                    all_tags.update(getattr(entry, 'tags', []))

            if len(entries) < 2:
                return None

            # Build summary content
            content_parts = [getattr(e, 'content', '')[:100] for e in entries[:5]]
            summary_content = f"[Summary of {len(entries)} entries] " + " | ".join(content_parts)

            # Average confidence (boosted by consensus)
            avg_conf = sum(getattr(e, 'confidence', 0.5) for e in entries) / len(entries)
            boosted_conf = min(1.0, avg_conf + 0.1)

            summary = self._moltbook.add_entry(
                content=summary_content,
                source_agent="curation_agent",
                entry_type="knowledge",
                tags=list(all_tags)[:10],
                confidence=boosted_conf,
                linked_to={eid: "summarizes" for eid in entry_ids[:10]},
            )

            action = CurationAction(
                action_type="summarize",
                entry_ids=entry_ids,
                result_id=summary.id,
                details=f"Summary of {len(entries)} entries",
            )
            self._action_log.append(action.to_dict())

            return summary
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return None

    def _compute_similarity(self, entry_a, entry_b) -> float:
        """Compute word-level Jaccard similarity between two entries."""
        content_a = getattr(entry_a, 'content', '').lower()
        content_b = getattr(entry_b, 'content', '').lower()
        words_a = set(content_a.split())
        words_b = set(content_b.split())
        if not words_a or not words_b:
            return 0.0
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / max(union, 1)

    def _pick_survivor(self, entry_a, entry_b) -> tuple:
        """Pick which entry survives a merge (higher quality wins)."""
        score_a = (getattr(entry_a, 'confidence', 0.5) +
                   getattr(entry_a, 'accessed_count', 0) * 0.1)
        score_b = (getattr(entry_b, 'confidence', 0.5) +
                   getattr(entry_b, 'accessed_count', 0) * 0.1)
        if score_a >= score_b:
            return entry_a, entry_b
        return entry_b, entry_a

    def _merge_entries(self, survivor, consumed) -> None:
        """Transfer data from consumed entry to survivor."""
        # Transfer tags
        survivor_tags = set(getattr(survivor, 'tags', []))
        consumed_tags = set(getattr(consumed, 'tags', []))
        survivor.tags = list(survivor_tags | consumed_tags)

        # Boost survivor confidence
        survivor.confidence = min(1.0, survivor.confidence + 0.05)

        # Transfer links
        consumed_links = getattr(consumed, 'linked_entries', {})
        for eid, lt in consumed_links.items():
            if eid != survivor.id:
                survivor.linked_entries[eid] = lt

        # Append consumed content if it adds significant new info
        if len(consumed.content) > 20:
            survivor.content = (survivor.content.rstrip() +
                                f" [merged: {consumed.content[:100]}]")

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_merges': self._total_merges,
            'total_prunes': self._total_prunes,
            'total_clusters': self._total_clusters_found,
            'recent_actions': len(self._action_log),
        }


# ═══════════════════════════════════════════════════════════════════
# [9] ResearchAgent — Proactive Knowledge Gathering
# ═══════════════════════════════════════════════════════════════════

class ResearchAgent:
    """
    Proactively gathers knowledge to fill detected gaps.

    Flow:
      1. KnowledgeGapDetection flags an area with repeated failures
      2. ResearchAgent receives the gap info
      3. Generates research queries based on the gap
      4. Results are posted to Moltbook via MoltbookFeeder
      5. ExistentialPurpose filters: only purpose-aligned research

    Integration:
      - KnowledgeGapDetection (meta_cognition.py) → detects gaps
      - MoltbookFeeder → posts findings
      - ExistentialPurpose → prioritizes purpose-aligned research
    """

    def __init__(self, feeder: Optional[MoltbookFeeder] = None,
                 knowledge_gap_detection=None,
                 existential_purpose=None):
        self._feeder = feeder                        # MoltbookFeeder
        self._gap_detection = knowledge_gap_detection  # KnowledgeGapDetection
        self._purpose = existential_purpose            # ExistentialPurpose (optional)
        self._total_researched = 0
        self._total_entries_created = 0
        self._research_queue: deque = deque(maxlen=50)
        self._research_history: deque = deque(maxlen=200)
        self._active_topics: Set[str] = set()
        logger.info("ResearchAgent initialized")

    def check_for_gaps(self) -> List[Dict[str, Any]]:
        """
        Check KnowledgeGapDetection for areas needing research.

        Returns list of gap descriptions that need investigation.
        """
        if not self._gap_detection:
            return []

        gaps = []
        try:
            # KnowledgeGapDetection stores gaps internally
            if hasattr(self._gap_detection, '_gaps'):
                for area, gap in self._gap_detection._gaps.items():
                    if area not in self._active_topics:
                        gap_info = {
                            'area': area,
                            'description': getattr(gap, 'description', area),
                            'severity': getattr(gap, 'severity', 'unknown'),
                            'failure_count': getattr(gap, 'failure_count',
                                                      len(self._gap_detection._failure_buffer.get(area, []))),
                        }
                        gaps.append(gap_info)
        except Exception as e:
            logger.error(f"Gap check failed: {e}")

        return gaps

    def research_topic(self, topic: str, context: str = "",
                       max_findings: int = 5) -> List[Dict[str, Any]]:
        """
        Research a topic and post findings to Moltbook.

        In Phase A: generates structured research entries from context.
        Phase B+: will integrate with ToolUniverse for real web search.

        Args:
            topic: Topic to research
            context: Additional context about what we need
            max_findings: Max entries to create

        Returns:
            List of created findings (dicts with entry info)
        """
        self._total_researched += 1
        self._active_topics.add(topic)
        findings = []

        # Check purpose alignment if available
        purpose_aligned = True
        if self._purpose:
            try:
                if hasattr(self._purpose, 'check_alignment'):
                    alignment = self._purpose.check_alignment(topic)
                    if isinstance(alignment, (int, float)):
                        purpose_aligned = alignment > 0.3
                    elif isinstance(alignment, dict):
                        purpose_aligned = alignment.get('aligned', True)
            except Exception:
                pass

        if not purpose_aligned:
            logger.info(f"Research topic '{topic}' not aligned with purpose, skipping")
            self._research_history.append({
                'topic': topic,
                'status': 'skipped_not_aligned',
                'timestamp': time.time(),
            })
            return []

        # Phase A: Generate structured research entries from the topic/context
        research_entries = self._generate_research_entries(topic, context, max_findings)

        for entry_data in research_entries:
            if self._feeder:
                entry = self._feeder.post(
                    content=entry_data['content'],
                    tags=entry_data.get('tags', [topic]),
                    confidence=entry_data.get('confidence', 0.4),
                    entry_type="knowledge",
                    metadata={'source': 'research_agent', 'topic': topic},
                )
                if entry:
                    finding = {
                        'entry_id': entry.id,
                        'content': entry_data['content'],
                        'topic': topic,
                    }
                    findings.append(finding)
                    self._total_entries_created += 1

        self._research_history.append({
            'topic': topic,
            'status': 'completed',
            'findings': len(findings),
            'timestamp': time.time(),
        })
        self._active_topics.discard(topic)

        return findings

    def process_gap(self, gap: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process a single knowledge gap: research it and post findings.
        """
        topic = gap.get('area', '')
        context = gap.get('description', '')
        if not topic:
            return []
        return self.research_topic(topic, context=context)

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run one research cycle:
          1. Check for gaps
          2. Research top priorities
          3. Return summary

        Returns dict with cycle results.
        """
        gaps = self.check_for_gaps()
        total_findings = 0
        processed_gaps = 0

        for gap in gaps[:3]:  # Process top 3 gaps per cycle
            findings = self.process_gap(gap)
            total_findings += len(findings)
            processed_gaps += 1

        return {
            'gaps_found': len(gaps),
            'gaps_processed': processed_gaps,
            'findings_created': total_findings,
        }

    def _generate_research_entries(self, topic: str, context: str,
                                   max_entries: int) -> List[Dict[str, Any]]:
        """
        Generate research entry data for a topic.

        Phase B: Tries ToolUniverse web_search for real knowledge,
        falls back to structured placeholder entries.
        """
        entries = []

        # Phase B: Try web search via ToolUniverse
        web_results = self._web_search(topic, context)
        if web_results:
            for result in web_results[:max_entries]:
                entry = {
                    'content': result['content'][:500],
                    'tags': [topic.lower().replace(' ', '_'), 'research', 'web'],
                    'confidence': result.get('confidence', 0.5),
                }
                entries.append(entry)
            if entries:
                return entries[:max_entries]

        # Fallback: structured placeholder entries
        base_entry = {
            'content': f"Research note on '{topic}': {context}" if context else
                       f"Knowledge area identified for research: {topic}",
            'tags': [topic.lower().replace(' ', '_'), 'research'],
            'confidence': 0.3,
        }
        entries.append(base_entry)

        if context and len(context) > 20:
            detail_entry = {
                'content': f"Context for '{topic}': {context[:300]}",
                'tags': [topic.lower().replace(' ', '_'), 'research', 'context'],
                'confidence': 0.35,
            }
            entries.append(detail_entry)

        return entries[:max_entries]

    def _web_search(self, topic: str, context: str = "") -> List[Dict[str, Any]]:
        """
        Search the web for knowledge about a topic.

        Two-phase approach:
          1. ddgs (DuckDuckGo) → search results with snippets
          2. autogen SimpleTextBrowser → fetch full content of top URLs

        Returns list of dicts with 'content', 'confidence', 'source_url'.
        Non-blocking: returns empty list if no search package is available.
        """
        query = f"{topic} {context[:100]}".strip()

        # Phase 1: Search via ddgs
        raw_results = []
        try:
            from ddgs import DDGS as _DDGS
            ddgs = _DDGS()
            raw_results = list(ddgs.text(query, max_results=5))
        except ImportError:
            try:
                from duckduckgo_search import DDGS as _DDGS
                with _DDGS() as ddgs:
                    raw_results = list(ddgs.text(query, max_results=5))
            except ImportError:
                logger.debug("No web search package available (install ddgs)")
                return []
        except Exception as e:
            logger.debug(f"Web search failed for '{topic}': {e}")
            return []

        if not raw_results:
            return []

        results = []
        for r in raw_results:
            title = r.get('title', '')
            body = r.get('body', '')
            url = r.get('href', '')
            content = f"{title}: {body}"
            if content.strip():
                results.append({
                    'content': content[:500],
                    'confidence': 0.5,
                    'source_url': url,
                })

        if results:
            logger.info(f"ResearchAgent web search found {len(results)} results for '{topic}'")

        # Phase 2: Fetch full content of top URLs via autogen SimpleTextBrowser
        enriched = self._fetch_url_content(results[:2])
        if enriched:
            results = enriched + results[2:]

        return results

    def _fetch_url_content(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fetch full page content for search results using autogen's
        SimpleTextBrowser. Enriches the 'content' field with actual page text.

        Returns enriched results, or empty list if browser unavailable.
        """
        try:
            from autogen.browser_utils import SimpleTextBrowser
        except ImportError:
            return []

        enriched = []
        browser = SimpleTextBrowser(viewport_size=4096)

        for r in results:
            url = r.get('source_url', '')
            if not url or url.startswith('https://www.bing.com/aclick'):
                enriched.append(r)  # Skip ad URLs
                continue

            try:
                browser.visit_page(url)
                page_text = getattr(browser, 'page_content', '')
                if page_text and len(page_text) > 100:
                    # Extract meaningful text (strip HTML artifacts)
                    clean_text = page_text[:2000].strip()
                    enriched.append({
                        'content': f"{r.get('content', '')}\n\n--- Full content ---\n{clean_text}",
                        'confidence': min(0.7, r.get('confidence', 0.5) + 0.2),
                        'source_url': url,
                        'fetched': True,
                    })
                    logger.debug(f"Fetched {len(page_text)} chars from {url}")
                else:
                    enriched.append(r)
            except Exception as e:
                logger.debug(f"Failed to fetch {url}: {e}")
                enriched.append(r)

        return enriched

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_researched': self._total_researched,
            'total_entries_created': self._total_entries_created,
            'active_topics': len(self._active_topics),
            'queue_size': len(self._research_queue),
        }


# ═══════════════════════════════════════════════════════════════════
# [10] FeedbackAgent — User Feedback Integration
# ═══════════════════════════════════════════════════════════════════

class FeedbackAgent:
    """
    Integrates user feedback to improve Moltbook knowledge quality.

    Flow:
      1. User response → feedback extracted (positive/negative/correction)
      2. Entries that contributed to the response are identified
      3. Positive → uprank contributing entries
      4. Negative → downrank contributing entries
      5. Correction → create corrected entry, link to original

    Integration with MoralConscience:
      - Ethical feedback (fairness, bias) gets special treatment
      - Flagged content gets reviewed rather than auto-adjusted
    """

    def __init__(self, moltbook=None, moral_conscience=None,
                 uprank_amount: float = 0.1,
                 downrank_amount: float = 0.1):
        self._moltbook = moltbook                  # MoltbookStore
        self._moral_conscience = moral_conscience    # MoralConscience (optional)
        self._uprank_amount = uprank_amount
        self._downrank_amount = downrank_amount
        self._total_feedbacks = 0
        self._total_upranks = 0
        self._total_downranks = 0
        self._total_corrections = 0
        self._feedback_history: deque = deque(maxlen=300)
        self._entry_scores: Dict[str, float] = defaultdict(lambda: 0.0)
        logger.info("FeedbackAgent initialized")

    def record_feedback(self, sentiment: float,
                        contributing_entry_ids: Optional[List[str]] = None,
                        correction: Optional[str] = None,
                        response_id: str = "") -> FeedbackRecord:
        """
        Record user feedback on a response.

        Args:
            sentiment: -1 (very negative) to +1 (very positive)
            contributing_entry_ids: Moltbook entries that helped generate response
            correction: Optional correction text from user
            response_id: ID of the response being evaluated

        Returns:
            FeedbackRecord
        """
        self._total_feedbacks += 1
        entry_ids = contributing_entry_ids or []

        record = FeedbackRecord(
            response_id=response_id,
            sentiment=sentiment,
            contributing_entries=entry_ids,
            correction=correction,
        )

        # Apply uprank/downrank to contributing entries
        if sentiment > 0.2:
            self._uprank_entries(entry_ids, sentiment)
        elif sentiment < -0.2:
            self._downrank_entries(entry_ids, abs(sentiment))

        # Handle corrections
        if correction and correction.strip():
            self._apply_correction(correction, entry_ids)

        # Ethical feedback handling via MoralConscience
        if self._moral_conscience and abs(sentiment) > 0.5:
            self._check_ethical_implications(record)

        self._feedback_history.append(record.to_dict())
        return record

    def _uprank_entries(self, entry_ids: List[str], magnitude: float) -> None:
        """Boost relevance/confidence of entries that helped."""
        if not self._moltbook:
            return

        boost = self._uprank_amount * magnitude
        for eid in entry_ids:
            entry = self._moltbook.get_entry(eid)
            if entry:
                entry.relevance_score = min(1.0, entry.relevance_score + boost)
                entry.confidence = min(1.0, entry.confidence + boost * 0.5)
                self._entry_scores[eid] += boost
                self._total_upranks += 1

    def _downrank_entries(self, entry_ids: List[str], magnitude: float) -> None:
        """Reduce relevance/confidence of entries that caused bad response."""
        if not self._moltbook:
            return

        penalty = self._downrank_amount * magnitude
        for eid in entry_ids:
            entry = self._moltbook.get_entry(eid)
            if entry:
                entry.relevance_score = max(0.0, entry.relevance_score - penalty)
                entry.confidence = max(0.0, entry.confidence - penalty * 0.5)
                self._entry_scores[eid] -= penalty
                self._total_downranks += 1

    def _apply_correction(self, correction: str, original_entry_ids: List[str]) -> None:
        """Create a corrected entry and link to originals."""
        if not self._moltbook:
            return

        try:
            corrected = self._moltbook.add_entry(
                content=f"[Correction] {correction}",
                source_agent="feedback_agent",
                entry_type="knowledge",
                confidence=0.7,  # User-provided → higher confidence
                linked_to={eid: "corrects" for eid in original_entry_ids[:5]},
            )
            if corrected:
                self._total_corrections += 1
        except Exception as e:
            logger.error(f"Correction failed: {e}")

    def _check_ethical_implications(self, record: FeedbackRecord) -> None:
        """Check if feedback has ethical implications via MoralConscience."""
        if not self._moral_conscience:
            return

        try:
            # Check if correction contains ethical keywords
            correction = record.correction or ""
            ethical_keywords = {'bias', 'unfair', 'offensive', 'discriminat',
                                'harm', 'inappropri', 'racist', 'sexist'}
            text_lower = correction.lower()
            is_ethical = any(kw in text_lower for kw in ethical_keywords)

            if is_ethical:
                # Flag contributing entries for ethical review
                for eid in record.contributing_entries:
                    entry = self._moltbook.get_entry(eid) if self._moltbook else None
                    if entry:
                        if not hasattr(entry, 'metadata'):
                            entry.metadata = {}
                        entry.metadata['ethical_review'] = True
                        entry.metadata['ethical_feedback'] = correction[:200]
                        # Stronger downrank for ethical issues
                        entry.relevance_score = max(0.0, entry.relevance_score - 0.3)
        except Exception:
            pass

    def get_entry_cumulative_score(self, entry_id: str) -> float:
        """Get cumulative feedback score for an entry."""
        return self._entry_scores.get(entry_id, 0.0)

    def get_top_entries(self, n: int = 10) -> List[Tuple[str, float]]:
        """Get entries with highest cumulative feedback scores."""
        sorted_entries = sorted(self._entry_scores.items(),
                                key=lambda x: x[1], reverse=True)
        return sorted_entries[:n]

    def get_bottom_entries(self, n: int = 10) -> List[Tuple[str, float]]:
        """Get entries with lowest cumulative feedback scores."""
        sorted_entries = sorted(self._entry_scores.items(),
                                key=lambda x: x[1])
        return sorted_entries[:n]

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_feedbacks': self._total_feedbacks,
            'total_upranks': self._total_upranks,
            'total_downranks': self._total_downranks,
            'total_corrections': self._total_corrections,
            'tracked_entries': len(self._entry_scores),
            'avg_sentiment': (
                sum(r.get('sentiment', 0) for r in self._feedback_history) /
                max(1, len(self._feedback_history))
            ),
        }


# ═══════════════════════════════════════════════════════════════════
# [11] MoltbookForum — Multi-Agent Discussion System
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ForumPost:
    """Single contribution from an agent in a discussion."""
    agent: str = ""
    role: str = ""           # evaluator / curator / researcher / feedback / moderator
    content: str = ""
    action: str = ""         # opinion / proposal / question / verdict / synthesis
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent': self.agent,
            'role': self.role,
            'content': self.content,
            'action': self.action,
            'data': self.data,
            'timestamp': self.timestamp,
        }


@dataclass
class DiscussionThread:
    """A complete multi-agent discussion about a topic."""
    topic: str = ""
    query: str = ""
    posts: List[ForumPost] = field(default_factory=list)
    entries_discussed: List[str] = field(default_factory=list)
    consensus: Optional[str] = None
    synthesis: str = ""
    confidence: float = 0.5
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'topic': self.topic,
            'query': self.query,
            'posts': [p.to_dict() for p in self.posts],
            'entries_discussed': self.entries_discussed,
            'consensus': self.consensus,
            'synthesis': self.synthesis,
            'confidence': self.confidence,
            'actions_taken': self.actions_taken,
            'timestamp': self.timestamp,
            'duration_ms': self.duration_ms,
        }


class MoltbookForum:
    """
    Multi-Agent Discussion System for Moltbook Knowledge.

    Orchestrates a structured discussion between all Moltbook agents
    about a topic or query. Each agent contributes from its perspective:

      - EvaluationAgent:  Assesses quality of relevant entries
      - ResearchAgent:    Identifies knowledge gaps, proposes research
      - CurationAgent:    Suggests organizational improvements
      - FeedbackAgent:    Reports user sentiment patterns
      - Moderator:        Synthesizes all perspectives into a conclusion

    Architecture inspired by:
      - MoA (ICLR 2025) — Mixture of Agents: Proposer/Aggregator
      - Parliamentary debate — structured argument and synthesis
      - Delphi method — iterative expert convergence

    Usage:
      forum = MoltbookForum(store=store, evaluator=eval_agent, ...)
      thread = forum.discuss("What do we know about X?")
      # thread.posts contains all agent contributions
      # thread.synthesis is the final conclusion
    """

    def __init__(self, store=None, evaluator=None, curator=None,
                 researcher=None, feedback=None, graph=None):
        self._store = store               # MoltbookStore
        self._evaluator = evaluator       # EvaluationAgent
        self._curator = curator           # CurationAgent
        self._researcher = researcher     # ResearchAgent
        self._feedback = feedback         # FeedbackAgent
        self._graph = graph               # MoltbookGraph
        self._total_discussions = 0
        self._discussion_history: deque = deque(maxlen=50)
        logger.info("MoltbookForum initialized")

    def discuss(self, query: str, top_k: int = 5) -> DiscussionThread:
        """
        Run a full multi-agent discussion about a query.

        Flow:
          1. Retrieve relevant entries
          2. Each agent contributes their perspective
          3. Moderator synthesizes a conclusion
          4. Execute any agreed-upon actions

        Args:
            query: Topic or question to discuss
            top_k: Number of entries to retrieve for discussion

        Returns:
            DiscussionThread with all contributions
        """
        t0 = time.time()
        self._total_discussions += 1
        thread = DiscussionThread(topic=query, query=query)

        # ── Step 0: Retrieve relevant entries ──
        entries = []
        if self._store:
            try:
                entries = self._store.query_semantic(query, top_k=top_k, threshold=0.2)
                if not entries:
                    entries = self._store.get_active_entries(top_k=min(top_k, 5))
                thread.entries_discussed = [e.id for e in entries]
            except Exception:
                entries = list(self._store._entries.values())[:top_k] if self._store else []

        if not entries and self._store:
            entries = self._store.get_active_entries(top_k=5)
            thread.entries_discussed = [e.id for e in entries]

        # Opening statement
        thread.posts.append(ForumPost(
            agent='moderator', role='moderator', action='opening',
            content=f"Discussion opened on: '{query}'. {len(entries)} entries in scope.",
            data={'entry_count': len(entries), 'entry_ids': thread.entries_discussed},
        ))

        # ── Step 1: EvaluationAgent — quality assessment ──
        if self._evaluator and entries:
            eval_results = []
            promote_count = 0
            demote_count = 0
            flag_count = 0
            for entry in entries:
                try:
                    er = self._evaluator.evaluate(entry)
                    eval_results.append(er.to_dict())
                    if er.recommendation == 'promote':
                        promote_count += 1
                    elif er.recommendation in ('demote', 'flag'):
                        demote_count += 1
                        if er.recommendation == 'flag':
                            flag_count += 1
                except Exception:
                    pass

            avg_quality = (sum(r['overall'] for r in eval_results) / len(eval_results)) if eval_results else 0.0

            summary_parts = []
            summary_parts.append(f"Evaluated {len(eval_results)} entries: avg quality {avg_quality:.0%}")
            if promote_count:
                summary_parts.append(f"{promote_count} high-quality (promote)")
            if demote_count:
                summary_parts.append(f"{demote_count} low-quality (demote)")
            if flag_count:
                summary_parts.append(f"{flag_count} flagged for review")

            # Specific entry opinions
            entry_opinions = []
            for er in eval_results:
                eid = er['entry_id'][:8]
                entry_obj = next((e for e in entries if e.id.startswith(eid[:8])), None)
                snippet = entry_obj.content[:60] if entry_obj else eid
                entry_opinions.append(
                    f"  [{er['recommendation'].upper()}] {snippet}... "
                    f"(rel={er['relevance']:.0%}, nov={er['novelty']:.0%}, con={er['consistency']:.0%})"
                )

            thread.posts.append(ForumPost(
                agent='evaluation', role='evaluator', action='opinion',
                content=". ".join(summary_parts) + ".\n" + "\n".join(entry_opinions),
                data={'evaluations': eval_results, 'avg_quality': round(avg_quality, 3)},
            ))

        # ── Step 2: ResearchAgent — gap detection ──
        if self._researcher:
            gaps = []
            # Check if any gaps are known
            try:
                known_gaps = self._researcher.check_for_gaps()
                gaps.extend(known_gaps)
            except Exception:
                pass

            # Check topical coverage
            topic_words = set(query.lower().split())
            entry_words = set()
            for e in entries:
                entry_words.update(e.content.lower().split()[:20])

            missing_coverage = topic_words - entry_words - {'what', 'how', 'is', 'the', 'a',
                                                              'about', 'tell', 'me', 'do', 'we',
                                                              'know', 'does', 'can', 'all', 'in'}
            if missing_coverage:
                gaps.append({
                    'area': 'topical',
                    'description': f"No entries specifically covering: {', '.join(missing_coverage)}",
                    'severity': 'low' if entries else 'high',
                })

            if not entries:
                gaps.append({
                    'area': 'empty',
                    'description': 'No knowledge found at all for this query',
                    'severity': 'critical',
                })

            gap_text = f"Found {len(gaps)} knowledge gaps."
            if gaps:
                for g in gaps[:3]:
                    gap_text += f"\n  [GAP:{g.get('severity','?').upper()}] {g.get('description','')}"
                gap_text += "\n  Recommendation: Research needed on these topics."
            else:
                gap_text += " Coverage appears adequate."

            thread.posts.append(ForumPost(
                agent='research', role='researcher', action='opinion',
                content=gap_text,
                data={'gaps': gaps},
            ))

        # ── Step 3: CurationAgent — organization ──
        if self._curator and entries:
            curation_suggestions = []

            # Check for potential merges among discussed entries
            if len(entries) >= 2:
                for i, e1 in enumerate(entries):
                    for j in range(i + 1, len(entries)):
                        e2 = entries[j]
                        # Simple word overlap check
                        words1 = set(e1.content.lower().split())
                        words2 = set(e2.content.lower().split())
                        overlap = len(words1 & words2) / max(len(words1 | words2), 1)
                        if overlap > 0.5:
                            curation_suggestions.append({
                                'type': 'merge_candidate',
                                'entries': [e1.id, e2.id],
                                'overlap': round(overlap, 2),
                                'reason': f"High word overlap ({overlap:.0%})",
                            })

            # Check for tag consistency
            all_tags = set()
            for e in entries:
                all_tags.update(e.tags)

            untagged = [e for e in entries if not e.tags]
            if untagged:
                curation_suggestions.append({
                    'type': 'tag_needed',
                    'entries': [e.id for e in untagged],
                    'reason': f"{len(untagged)} entries have no tags",
                })

            # Check for stale entries
            now = time.time()
            stale = [e for e in entries if e.accessed_count == 0 and (now - e.created_at) > 3600]
            if stale:
                curation_suggestions.append({
                    'type': 'stale_warning',
                    'entries': [e.id for e in stale],
                    'reason': f"{len(stale)} entries never accessed after 1h+",
                })

            cur_text = f"Organization review of {len(entries)} entries."
            if curation_suggestions:
                for s in curation_suggestions[:5]:
                    cur_text += f"\n  [{s['type'].upper()}] {s['reason']}"
            else:
                cur_text += "\n  Knowledge base is well-organized. No actions needed."

            thread.posts.append(ForumPost(
                agent='curation', role='curator', action='proposal',
                content=cur_text,
                data={'suggestions': curation_suggestions},
            ))

        # ── Step 4: FeedbackAgent — sentiment report ──
        if self._feedback:
            fb_data = {}
            try:
                fb_data = {
                    'total_feedbacks': self._feedback._total_feedbacks,
                    'upranks': self._feedback._total_upranks,
                    'downranks': self._feedback._total_downranks,
                    'corrections': self._feedback._total_corrections,
                }
            except Exception:
                pass

            # Check if any discussed entries have feedback scores
            entry_sentiments = []
            for e in entries:
                score = self._feedback._entry_scores.get(e.id, 0.0) if self._feedback else 0.0
                if score != 0.0:
                    entry_sentiments.append((e.id[:8], score))

            fb_text = f"User feedback summary: {fb_data.get('total_feedbacks', 0)} total feedbacks received"
            fb_text += f" ({fb_data.get('upranks', 0)} positive, {fb_data.get('downranks', 0)} negative)"
            if entry_sentiments:
                fb_text += "\n  Entry-level sentiment:"
                for eid, score in entry_sentiments:
                    icon = '+' if score > 0 else '-'
                    fb_text += f"\n    [{icon}{abs(score):.2f}] {eid}..."
            else:
                fb_text += "\n  No entry-level feedback recorded for discussed entries."
            fb_text += f"\n  {fb_data.get('corrections', 0)} corrections submitted."

            thread.posts.append(ForumPost(
                agent='feedback', role='feedback', action='opinion',
                content=fb_text,
                data=fb_data,
            ))

        # ── Step 5: Graph context ──
        if self._graph and entries:
            connections = 0
            for e in entries:
                try:
                    neighbors = self._graph.get_neighbors(e.id) if hasattr(self._graph, 'get_neighbors') else []
                    connections += len(neighbors) if neighbors else 0
                except Exception:
                    pass

            if connections > 0:
                thread.posts.append(ForumPost(
                    agent='graph', role='analyst', action='opinion',
                    content=f"Knowledge graph: {connections} connections found among discussed entries.",
                    data={'total_connections': connections},
                ))

        # ── Step 6: Moderator synthesis ──
        synthesis = self._synthesize(thread, entries)
        thread.synthesis = synthesis['text']
        thread.confidence = synthesis['confidence']
        thread.consensus = synthesis['consensus']
        thread.actions_taken = synthesis.get('actions', [])

        thread.posts.append(ForumPost(
            agent='moderator', role='moderator', action='synthesis',
            content=synthesis['text'],
            data=synthesis,
        ))

        thread.duration_ms = (time.time() - t0) * 1000
        self._discussion_history.append(thread.to_dict())
        return thread

    def _synthesize(self, thread: DiscussionThread, entries: list) -> Dict[str, Any]:
        """
        Moderator synthesis: combine all agent perspectives into a verdict.

        Weighs:
          - Quality scores from evaluator
          - Gap analysis from researcher
          - Organizational state from curator
          - User sentiment from feedback
        """
        avg_quality = 0.5
        has_gaps = False
        gap_severity = 'none'
        has_merge_candidates = False
        user_sentiment_positive = True
        entry_count = len(entries)

        for post in thread.posts:
            if post.role == 'evaluator':
                avg_quality = post.data.get('avg_quality', 0.5)
            elif post.role == 'researcher':
                gaps = post.data.get('gaps', [])
                has_gaps = len(gaps) > 0
                for g in gaps:
                    if g.get('severity') in ('high', 'critical'):
                        gap_severity = g['severity']
            elif post.role == 'curator':
                for s in post.data.get('suggestions', []):
                    if s.get('type') == 'merge_candidate':
                        has_merge_candidates = True
            elif post.role == 'feedback':
                downranks = post.data.get('downranks', 0)
                upranks = post.data.get('upranks', 0)
                if downranks > upranks:
                    user_sentiment_positive = False

        # Build synthesis
        parts = []

        # Quality assessment
        if avg_quality >= 0.7:
            parts.append(f"Knowledge quality is strong ({avg_quality:.0%}).")
            consensus = 'high_confidence'
        elif avg_quality >= 0.4:
            parts.append(f"Knowledge quality is moderate ({avg_quality:.0%}).")
            consensus = 'moderate_confidence'
        else:
            parts.append(f"Knowledge quality needs improvement ({avg_quality:.0%}).")
            consensus = 'low_confidence'

        # Coverage
        if entry_count == 0:
            parts.append("No knowledge entries found. This is a blind spot.")
            consensus = 'no_coverage'
        elif has_gaps and gap_severity in ('high', 'critical'):
            parts.append(f"Significant knowledge gaps detected ({gap_severity}).")
        elif has_gaps:
            parts.append("Minor gaps exist but coverage is acceptable.")

        # Organization
        if has_merge_candidates:
            parts.append("Some entries could be merged to reduce redundancy.")

        # User satisfaction
        if not user_sentiment_positive:
            parts.append("User feedback trends negative. Review content quality.")
        elif self._feedback and self._feedback._total_feedbacks > 0:
            parts.append("User feedback is positive.")

        # Actions
        actions = []
        if gap_severity in ('high', 'critical') and self._researcher:
            actions.append({'type': 'research', 'reason': 'Critical gaps need filling'})
        if has_merge_candidates and self._curator:
            actions.append({'type': 'curate', 'reason': 'Merge candidates found'})
        if avg_quality < 0.3:
            actions.append({'type': 'evaluate', 'reason': 'Quality below threshold'})

        # Confidence based on all signals
        confidence = min(1.0, avg_quality * 0.4 + (0.3 if not has_gaps else 0.1) +
                         (0.2 if user_sentiment_positive else 0.0) +
                         (0.1 if entry_count > 3 else 0.0))

        return {
            'text': " ".join(parts),
            'confidence': round(confidence, 3),
            'consensus': consensus,
            'avg_quality': round(avg_quality, 3),
            'entry_count': entry_count,
            'has_gaps': has_gaps,
            'gap_severity': gap_severity,
            'actions': actions,
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_discussions': self._total_discussions,
            'recent_count': len(self._discussion_history),
        }

    def get_recent_discussions(self, n: int = 10) -> List[Dict[str, Any]]:
        return list(self._discussion_history)[-n:]
