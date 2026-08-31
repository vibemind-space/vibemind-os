"""
ThoughtJury — autonomous thought evaluation via 5 embedding-based judges.

Each CTE thought is evaluated by 5 judges (no LLM, pure cosine sim):
  CoherenceJudge:  connects to stored knowledge? (Moltbook search)
  NoveltyJudge:    genuinely new vs recent thoughts? (cosine distance)
  RelevanceJudge:  serves current topic/goals? (cosine sim to topic)
  DepthJudge:      surface-level or deep? (RingSignature + text heuristic)
  ProgressJudge:   builds on previous or repeats? (sim sweet spot)

ConsensusGate: >= 3/5 positive → positive reward, else mild negative.
DeepReview: every N thoughts, LLM critic calibrates judge weights.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger('brain.thought_jury')


@dataclass
class JudgeResult:
    name: str
    score: float        # [0.0, 1.0]
    reason: str = ""


@dataclass
class JuryContext:
    """Read-only snapshot of CTE state, built once per evaluation."""
    thought_embedding: Optional[np.ndarray] = None
    recent_thought_embeddings: List[np.ndarray] = field(default_factory=list)
    current_topic: str = ""
    current_topic_embedding: Optional[np.ndarray] = None
    ring_signature: Any = None
    moltbook_available: bool = False


class BaseJudge:
    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight
        self._total_calls = 0
        self._total_time_ms = 0.0

    def evaluate(self, thought, context: JuryContext) -> JudgeResult:
        raise NotImplementedError

    def safe_evaluate(self, thought, context: JuryContext) -> JudgeResult:
        try:
            t0 = time.perf_counter()
            result = self.evaluate(thought, context)
            self._total_time_ms += (time.perf_counter() - t0) * 1000
            self._total_calls += 1
            return result
        except Exception as e:
            self._total_calls += 1
            return JudgeResult(name=self.name, score=0.5, reason=f"error: {e}")


class CoherenceJudge(BaseJudge):
    """Does this thought connect to stored knowledge?"""

    def __init__(self):
        super().__init__("coherence")
        self._semantic_index = None

    def evaluate(self, thought, context: JuryContext) -> JudgeResult:
        if not context.moltbook_available or self._semantic_index is None:
            return JudgeResult(name=self.name, score=0.0, reason="no-index")
        if context.thought_embedding is None:
            return JudgeResult(name=self.name, score=0.0, reason="no-embedding")

        results = self._semantic_index.search(
            context.thought_embedding, top_k=5, threshold=0.2)
        if not results:
            return JudgeResult(name=self.name, score=0.2, reason="no-matches")

        scores = [sim for _, sim in results]
        best_sim = max(scores)
        # Rescale: cosine sim 0.2→0.0, 0.5→1.0
        # Cross-domain thoughts vs specialized knowledge rarely exceed 0.5
        score = max(0.0, min(1.0, (best_sim - 0.2) / 0.3))
        return JudgeResult(
            name=self.name,
            score=score,
            reason=f"best={best_sim:.3f}",
        )


class NoveltyJudge(BaseJudge):
    """Is this genuinely new vs recent thoughts?"""

    def __init__(self):
        super().__init__("novelty")

    def evaluate(self, thought, context: JuryContext) -> JudgeResult:
        if context.thought_embedding is None:
            return JudgeResult(name=self.name, score=0.0, reason="no-embedding")
        if not context.recent_thought_embeddings:
            return JudgeResult(name=self.name, score=0.7, reason="first-thought")

        max_sim = 0.0
        for emb in context.recent_thought_embeddings:
            sim = float(np.dot(context.thought_embedding, emb))
            max_sim = max(max_sim, sim)

        # Rescale: sim 0.5→novel(0.8), sim 0.8→repetitive(0.2), sim 1.0→0.0
        # Sweet spot: some overlap (0.3-0.5) means the thought is related but new
        if max_sim > 0.85:
            score = 0.1  # too similar
        elif max_sim < 0.3:
            score = 0.8  # very novel
        else:
            score = max(0.0, min(1.0, 1.0 - (max_sim - 0.3) / 0.55))
        return JudgeResult(
            name=self.name, score=score,
            reason=f"max_sim={max_sim:.3f}",
        )


class RelevanceJudge(BaseJudge):
    """Does it serve the current topic/goals?"""

    def __init__(self):
        super().__init__("relevance")

    def evaluate(self, thought, context: JuryContext) -> JudgeResult:
        if not context.current_topic:
            return JudgeResult(name=self.name, score=0.0, reason="no-topic")
        if context.thought_embedding is None or context.current_topic_embedding is None:
            return JudgeResult(name=self.name, score=0.0, reason="no-embedding")

        sim = float(np.dot(context.thought_embedding, context.current_topic_embedding))
        score = max(0.0, min(1.0, sim))
        return JudgeResult(
            name=self.name, score=score,
            reason=f"topic_sim={sim:.3f}",
        )


class DepthJudge(BaseJudge):
    """Surface-level or deep thinking?"""

    def __init__(self):
        super().__init__("depth")

    def evaluate(self, thought, context: JuryContext) -> JudgeResult:
        content = getattr(thought, 'content', '') or ''

        # Text complexity heuristic: unique words / 15 (CTE thoughts are short)
        words = content.lower().split()
        unique = len(set(words))
        text_score = min(1.0, unique / 15.0) if words else 0.0

        # RingSignature semantic_richness (if available)
        ring_sig = context.ring_signature
        if ring_sig is not None:
            richness = getattr(ring_sig, 'semantic_richness', 0.0)
            score = 0.6 * richness + 0.4 * text_score
        else:
            score = text_score

        return JudgeResult(
            name=self.name, score=min(1.0, score),
            reason=f"text={text_score:.2f}",
        )


class ProgressJudge(BaseJudge):
    """Does this build on previous thoughts or repeat?"""

    def __init__(self):
        super().__init__("progress")

    def evaluate(self, thought, context: JuryContext) -> JudgeResult:
        if context.thought_embedding is None:
            return JudgeResult(name=self.name, score=0.0, reason="no-embedding")

        recent = context.recent_thought_embeddings[-5:] if context.recent_thought_embeddings else []
        if not recent:
            return JudgeResult(name=self.name, score=0.5, reason="first-thought")

        max_sim = 0.0
        for emb in recent:
            sim = float(np.dot(context.thought_embedding, emb))
            max_sim = max(max_sim, sim)

        # Sweet spot: 0.3-0.7 = building on previous (related but novel)
        if max_sim > 0.85:
            score = 0.1  # repetition
        elif max_sim < 0.2:
            score = 0.3  # disconnected
        else:
            # Peak at 0.5 similarity
            score = 0.5 + 0.5 * (1.0 - abs(max_sim - 0.5) * 2.0)

        return JudgeResult(
            name=self.name, score=max(0.0, min(1.0, score)),
            reason=f"max_sim={max_sim:.3f}",
        )


class ConsensusGate:
    """Aggregates judge results into a reward signal."""

    def __init__(self, positive_threshold: float = 0.45, min_positive_judges: int = 3):
        self.positive_threshold = positive_threshold
        self.min_positive_judges = min_positive_judges

    def aggregate(self, results: List[JudgeResult],
                  weights: Dict[str, float]) -> float:
        if not results:
            return 0.0

        # Only count judges that had real input (score > 0 means they computed)
        active_results = [r for r in results if r.score > 0.0]
        if not active_results:
            return 0.0  # No judge had data — abstain, don't punish

        positive_count = sum(
            1 for r in active_results if r.score > self.positive_threshold)

        # Adjust quorum: need majority of ACTIVE judges, min 2
        active_quorum = max(2, (len(active_results) + 1) // 2)

        if positive_count >= active_quorum:
            total_w = sum(weights.get(r.name, 1.0) for r in active_results)
            if total_w == 0:
                return 0.1
            reward = sum(
                r.score * weights.get(r.name, 1.0) for r in active_results
            ) / total_w
            return max(0.1, reward)
        else:
            avg = sum(r.score for r in active_results) / len(active_results)
            return -0.1 - 0.2 * (1.0 - avg)


class DeepReview:
    """Periodic LLM calibration of judge weights."""

    def __init__(self, micro_agent_pool=None, interval: int = 50):
        self._pool = micro_agent_pool
        self._interval = interval
        self._call_count = 0
        self._total_reviews = 0
        self._calibration_history: deque = deque(maxlen=20)

    def should_review(self) -> bool:
        self._call_count += 1
        return (self._pool is not None and
                self._call_count % self._interval == 0)

    def review_and_calibrate(self, thought, judge_results: List[JudgeResult],
                             weights: Dict[str, float]) -> Dict[str, float]:
        """LLM critic scores thought, adjusts weights based on agreement."""
        content = getattr(thought, 'content', '') or ''
        if not content:
            return weights

        # Use MicroAgentPool critic
        try:
            result = self._pool.summarize(content[:300])
            if result is None:
                return weights
            llm_score = getattr(result, 'confidence', 0.5)
        except Exception:
            return weights

        # Adjust weights: judges close to LLM get boosted
        new_weights = dict(weights)
        for jr in judge_results:
            error = abs(jr.score - llm_score)
            delta = 0.05 * (0.5 - error)
            old_w = new_weights.get(jr.name, 1.0)
            new_weights[jr.name] = max(0.5, min(2.0, old_w + delta))

        self._total_reviews += 1
        self._calibration_history.append({
            'llm_score': llm_score,
            'judge_scores': {jr.name: jr.score for jr in judge_results},
            'weight_updates': {k: round(new_weights[k] - weights.get(k, 1.0), 4)
                               for k in new_weights},
        })

        return new_weights


class ThoughtJury:
    """Autonomous thought evaluation — 5 judges + consensus + deep review."""

    def __init__(self, semantic_index=None, micro_agent_pool=None,
                 deep_review_interval: int = 50):
        self._semantic_index = semantic_index
        self._judges: List[BaseJudge] = [
            CoherenceJudge(),
            NoveltyJudge(),
            RelevanceJudge(),
            DepthJudge(),
            ProgressJudge(),
        ]
        # Wire semantic_index into CoherenceJudge
        if semantic_index is not None:
            self._judges[0]._semantic_index = semantic_index

        self._weights: Dict[str, float] = {j.name: 1.0 for j in self._judges}
        self._consensus = ConsensusGate()
        self._deep_review = DeepReview(micro_agent_pool, deep_review_interval)
        self._lock = threading.Lock()

        # Stats
        self._total_evaluations = 0
        self._total_positive = 0
        self._total_negative = 0
        self._avg_reward = 0.0

    def set_semantic_index(self, idx):
        self._semantic_index = idx
        self._judges[0]._semantic_index = idx

    def set_micro_agent_pool(self, pool):
        self._deep_review._pool = pool

    def evaluate(self, thought, cte_ref) -> float:
        """Evaluate a thought and return reward signal.

        Args:
            thought: ContinuousThought
            cte_ref: ContinuousThinkingEngine (read-only access for context)
        Returns:
            reward float: positive = good thought, negative = mild penalty
        """
        # 1. Build context snapshot
        context = self._build_context(thought, cte_ref)

        # 2. Run all judges (fast path, no LLM)
        results = [j.safe_evaluate(thought, context) for j in self._judges]

        # 3. Consensus gate
        with self._lock:
            reward = self._consensus.aggregate(results, self._weights)

        # 4. Periodic deep review
        if self._deep_review.should_review():
            try:
                new_weights = self._deep_review.review_and_calibrate(
                    thought, results, self._weights)
                with self._lock:
                    self._weights = new_weights
            except Exception:
                pass

        # 5. Update stats
        self._total_evaluations += 1
        if reward > 0:
            self._total_positive += 1
        else:
            self._total_negative += 1
        alpha = 0.01
        self._avg_reward = (1 - alpha) * self._avg_reward + alpha * reward

        return reward

    def _build_context(self, thought, cte_ref) -> JuryContext:
        """Build read-only context snapshot from CTE state."""
        # Recent thoughts (under lock, fast)
        with cte_ref._thought_lock:
            recent = list(cte_ref._thoughts)[-10:]

        recent_contents = [t.content for t in recent if t.content]

        # Embed thought content
        thought_emb = None
        if self._semantic_index and getattr(thought, 'content', ''):
            try:
                thought_emb = self._semantic_index.embed(thought.content[:300])
            except Exception:
                pass

        # Embed recent thoughts
        recent_embeddings = []
        if self._semantic_index:
            for c in recent_contents:
                try:
                    recent_embeddings.append(self._semantic_index.embed(c[:300]))
                except Exception:
                    pass

        # Topic embedding
        topic = getattr(cte_ref, '_current_topic', '') or ''
        topic_emb = None
        if topic and self._semantic_index:
            try:
                topic_emb = self._semantic_index.embed(topic)
            except Exception:
                pass

        ring_sig = getattr(thought, '_ring_signature', None)

        return JuryContext(
            thought_embedding=thought_emb,
            recent_thought_embeddings=recent_embeddings,
            current_topic=topic,
            current_topic_embedding=topic_emb,
            ring_signature=ring_sig,
            moltbook_available=self._semantic_index is not None,
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_evaluations': self._total_evaluations,
            'total_positive': self._total_positive,
            'total_negative': self._total_negative,
            'total_deep_reviews': self._deep_review._total_reviews,
            'avg_reward': round(self._avg_reward, 4),
            'judge_weights': {k: round(v, 3) for k, v in self._weights.items()},
            'judge_stats': {
                j.name: {
                    'calls': j._total_calls,
                    'avg_ms': round(j._total_time_ms / max(1, j._total_calls), 3),
                }
                for j in self._judges
            },
        }
