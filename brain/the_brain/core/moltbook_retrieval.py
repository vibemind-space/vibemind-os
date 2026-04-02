"""
Moltbook Retrieval Layer — Predictive Knowledge Activation

Provides:
  - MarkovKnowledgeChain:  Topic transition model (predicts next topics)
  - SpeculativeRetrieval:  Pre-fetch knowledge based on Markov predictions
  - ContextPredictor:      Conversation state prediction
  - RelevanceScorer:       Real-time relevance scoring of retrieved entries
  - KnowledgeDecay:        Ebbinghaus-based forgetting curve
  - AttentionDrivenRetrieval: ACh-modulated retrieval width

Architecture Inspirations:
  - Speculative Decoding (EAGLE-3 / Apple Mirror-SD) — draft-verify pattern
  - DeepRetrieval (MDP-based) — arxiv 2503.00223
  - Lisman-Jensen Model — theta-gamma ~7±2 workspace capacity
  - Ebbinghaus Forgetting Curve — exponential decay with spacing effect
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.moltbook.retrieval')


# ═══════════════════════════════════════════════════════════════════
# [16] MarkovKnowledgeChain — Topic Transition Model
# ═══════════════════════════════════════════════════════════════════

class MarkovKnowledgeChain:
    """
    Learns topic transition probabilities from conversation sequences.

    When topic A is active, predicts which topics B, C are likely next.
    Uses 1st and 2nd order Markov chains for prediction.

    Extends the brain's existing temporal memory concepts.
    """

    def __init__(self, moltbook=None, lookahead: int = 2):
        self._moltbook = moltbook    # MoltbookStore (optional)
        self._lookahead = lookahead

        # Transition counts: {topic: {next_topic: count}}
        self._transitions_1: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        # 2nd order: {(topic1, topic2): {next_topic: count}}
        self._transitions_2: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        # Total counts per source
        self._total_from: Dict[str, float] = defaultdict(float)
        self._total_from_2: Dict[Tuple[str, str], float] = defaultdict(float)

        # Topic history
        self._topic_history: deque = deque(maxlen=1000)
        self._total_updates = 0

        logger.info(f"MarkovKnowledgeChain initialized (lookahead={lookahead})")

    def update(self, topic_sequence: List[str]) -> None:
        """
        Update transition model from observed topic sequence.

        Called after each conversation to learn what topics follow what.
        """
        if len(topic_sequence) < 2:
            return

        # 1st order transitions
        for i in range(len(topic_sequence) - 1):
            src = topic_sequence[i]
            dst = topic_sequence[i + 1]
            self._transitions_1[src][dst] += 1.0
            self._total_from[src] += 1.0

        # 2nd order transitions
        for i in range(len(topic_sequence) - 2):
            pair = (topic_sequence[i], topic_sequence[i + 1])
            dst = topic_sequence[i + 2]
            self._transitions_2[pair][dst] += 1.0
            self._total_from_2[pair] += 1.0

        # Record in history
        for t in topic_sequence:
            self._topic_history.append(t)

        self._total_updates += 1

    def predict_next_topics(self, current_topics: List[str],
                            n: int = 5) -> List[Tuple[str, float]]:
        """
        Predict the N most likely next topics.

        Uses 2nd order Markov (if available) with 1st order fallback.

        Returns list of (topic, probability) sorted by probability desc.
        """
        if not current_topics:
            return []

        predictions: Dict[str, float] = defaultdict(float)

        # 2nd order prediction (if we have 2+ current topics)
        if len(current_topics) >= 2:
            pair = (current_topics[-2], current_topics[-1])
            if pair in self._transitions_2:
                total = self._total_from_2[pair]
                if total > 0:
                    for topic, count in self._transitions_2[pair].items():
                        predictions[topic] += 0.6 * (count / total)  # 60% weight for 2nd order

        # 1st order prediction (always)
        last_topic = current_topics[-1]
        if last_topic in self._transitions_1:
            total = self._total_from[last_topic]
            if total > 0:
                for topic, count in self._transitions_1[last_topic].items():
                    predictions[topic] += 0.4 * (count / total)  # 40% weight for 1st order

        # Sort and return top N
        sorted_preds = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
        return sorted_preds[:n]

    def get_transition_probability(self, from_topic: str, to_topic: str) -> float:
        """Get the transition probability from one topic to another."""
        total = self._total_from.get(from_topic, 0)
        if total == 0:
            return 0.0
        return self._transitions_1.get(from_topic, {}).get(to_topic, 0) / total

    def get_popular_topics(self, n: int = 10) -> List[Tuple[str, int]]:
        """Get the most frequently seen topics."""
        topic_counts: Dict[str, int] = defaultdict(int)
        for topic in self._topic_history:
            topic_counts[topic] += 1
        return sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:n]

    def save(self, path: str) -> None:
        """Save transition model to disk."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        data = {
            'transitions_1': dict(self._transitions_1),
            'total_from': dict(self._total_from),
            'transitions_2': {f"{k[0]}|||{k[1]}": dict(v)
                              for k, v in self._transitions_2.items()},
            'total_from_2': {f"{k[0]}|||{k[1]}": v
                             for k, v in self._total_from_2.items()},
            'total_updates': self._total_updates,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> bool:
        """Load transition model from disk. Returns True if loaded."""
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            # Restore 1st order
            for src, dests in data.get('transitions_1', {}).items():
                for dst, count in dests.items():
                    self._transitions_1[src][dst] = count
            for src, total in data.get('total_from', {}).items():
                self._total_from[src] = total

            # Restore 2nd order
            for key_str, dests in data.get('transitions_2', {}).items():
                parts = key_str.split('|||')
                if len(parts) == 2:
                    pair = (parts[0], parts[1])
                    for dst, count in dests.items():
                        self._transitions_2[pair][dst] = count
            for key_str, total in data.get('total_from_2', {}).items():
                parts = key_str.split('|||')
                if len(parts) == 2:
                    self._total_from_2[(parts[0], parts[1])] = total

            self._total_updates = data.get('total_updates', 0)
            return True
        except Exception as e:
            logger.warning(f"Failed to load Markov model: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        return {
            'unique_topics': len(self._transitions_1),
            'unique_pairs': len(self._transitions_2),
            'total_updates': self._total_updates,
            'history_size': len(self._topic_history),
        }


# ═══════════════════════════════════════════════════════════════════
# [17] SpeculativeRetrieval — Pre-fetch Knowledge
# ═══════════════════════════════════════════════════════════════════

class SpeculativeRetrieval:
    """
    Pre-fetches relevant Moltbook entries based on Markov predictions.

    Inspired by Speculative Decoding (EAGLE-3):
      1. Markov chain predicts next topics
      2. Pre-fetch entries for predicted topics
      3. When actual query arrives, entries are already loaded
      4. Track hit-rate to improve predictions

    Integration:
      - MarkovKnowledgeChain for topic predictions
      - MoltbookStore.query_semantic() for retrieval
      - SemanticIndex for embedding search
    """

    def __init__(self, markov=None, moltbook=None, semantic_index=None,
                 max_speculative: int = 20):
        self._markov = markov              # MarkovKnowledgeChain
        self._moltbook = moltbook          # MoltbookStore
        self._semantic_index = semantic_index  # SemanticIndex
        self._max_speculative = max_speculative

        # Speculative buffer: pre-fetched entries
        self._speculative_buffer: Dict[str, Any] = {}  # {entry_id: entry}
        self._lock = threading.Lock()

        # Hit tracking
        self._total_prefetched = 0
        self._total_hits = 0
        self._total_misses = 0

        logger.info("SpeculativeRetrieval initialized")

    def prefetch(self, current_topics: List[str],
                 top_k: int = 10) -> List[Any]:
        """
        Pre-fetch entries for predicted next topics.

        Args:
            current_topics: Current active topics
            top_k: Number of entries to pre-fetch per topic

        Returns:
            List of pre-fetched MoltbookEntry objects
        """
        if not self._markov or not self._moltbook:
            return []

        # Predict next topics
        predictions = self._markov.predict_next_topics(current_topics, n=5)
        if not predictions:
            return []

        prefetched = []
        with self._lock:
            for topic, prob in predictions:
                if prob < 0.05:  # Skip very unlikely topics
                    continue

                try:
                    # Retrieve entries for predicted topic
                    entries = self._moltbook.query_semantic(
                        topic, top_k=top_k,
                        threshold=0.3  # Lower threshold for speculative
                    )
                    for entry in entries:
                        if entry.id not in self._speculative_buffer:
                            self._speculative_buffer[entry.id] = entry
                            self._total_prefetched += 1
                        prefetched.append(entry)
                except Exception:
                    pass

            # Trim buffer if too large
            if len(self._speculative_buffer) > self._max_speculative * 2:
                # Keep only most recently added
                ids = list(self._speculative_buffer.keys())
                for old_id in ids[:len(ids) - self._max_speculative]:
                    del self._speculative_buffer[old_id]

        return prefetched[:top_k]

    def check_hit(self, entry_id: str) -> bool:
        """
        Check if an entry was pre-fetched (speculative hit).

        Call this when an entry is actually used in a response.
        """
        with self._lock:
            if entry_id in self._speculative_buffer:
                self._total_hits += 1
                return True
            else:
                self._total_misses += 1
                return False

    def get_buffer_contents(self) -> List[Any]:
        """Get all entries in the speculative buffer."""
        with self._lock:
            return list(self._speculative_buffer.values())

    def clear_buffer(self) -> None:
        """Clear the speculative buffer."""
        with self._lock:
            self._speculative_buffer.clear()

    @property
    def hit_rate(self) -> float:
        """Current speculative hit rate."""
        total = self._total_hits + self._total_misses
        return self._total_hits / max(1, total)

    def get_stats(self) -> Dict[str, Any]:
        return {
            'buffer_size': len(self._speculative_buffer),
            'total_prefetched': self._total_prefetched,
            'total_hits': self._total_hits,
            'total_misses': self._total_misses,
            'hit_rate': self.hit_rate,
        }


# ═══════════════════════════════════════════════════════════════════
# [18] ContextPredictor — Conversation State Prediction
# ═══════════════════════════════════════════════════════════════════

class ContextPredictor:
    """
    Predicts the next conversation state / user intent.

    Combines:
      - MarkovKnowledgeChain topic predictions
      - Cerebellum prediction error tracking
      - Conversation type × topic → predicted next state
    """

    def __init__(self, cerebellum=None, markov=None):
        self._cerebellum = cerebellum    # CerebellumModule (optional)
        self._markov = markov            # MarkovKnowledgeChain (optional)

        # Prediction history for error tracking
        self._predictions: deque = deque(maxlen=100)
        self._actuals: deque = deque(maxlen=100)
        self._total_predictions = 0
        self._correct_predictions = 0

        logger.info("ContextPredictor initialized")

    def predict(self, current_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict next conversation state.

        Args:
            current_context: Dict with 'topics', 'intent', 'complexity', etc.

        Returns:
            Dict with predicted next state.
        """
        self._total_predictions += 1
        prediction = {
            'predicted_topics': [],
            'predicted_intent': 'unknown',
            'confidence': 0.0,
            'prediction_error': 0.0,
        }

        # Topic prediction via Markov
        topics = current_context.get('topics', [])
        if self._markov and topics:
            next_topics = self._markov.predict_next_topics(topics, n=3)
            prediction['predicted_topics'] = [t for t, _ in next_topics]
            if next_topics:
                prediction['confidence'] = next_topics[0][1]

        # Track prediction error via cerebellum
        if self._cerebellum:
            try:
                pred_result = self._cerebellum.process({
                    'prediction': prediction.get('predicted_topics', []),
                    'actual': topics,
                })
                if isinstance(pred_result, dict):
                    pe = pred_result.get('prediction_error',
                                         pred_result.get('sensory_prediction_error', 0.0))
                    prediction['prediction_error'] = float(pe) if isinstance(pe, (int, float)) else 0.0
            except Exception:
                pass

        # Store for accuracy tracking
        self._predictions.append(prediction)
        return prediction

    def record_actual(self, actual_topics: List[str]) -> float:
        """
        Record actual topics to compute prediction accuracy.
        Returns prediction error (0 = perfect, 1 = completely wrong).
        """
        if not self._predictions:
            return 1.0

        last_pred = self._predictions[-1]
        predicted = set(last_pred.get('predicted_topics', []))
        actual = set(actual_topics)

        if not predicted and not actual:
            self._correct_predictions += 1
            return 0.0

        if predicted and actual:
            overlap = len(predicted & actual)
            error = 1.0 - (overlap / max(len(predicted), len(actual)))
            if overlap > 0:
                self._correct_predictions += 1
        else:
            error = 1.0

        self._actuals.append(actual_topics)
        return error

    @property
    def accuracy(self) -> float:
        """Overall prediction accuracy."""
        return self._correct_predictions / max(1, self._total_predictions)

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_predictions': self._total_predictions,
            'correct_predictions': self._correct_predictions,
            'accuracy': self.accuracy,
        }


# ═══════════════════════════════════════════════════════════════════
# [19] RelevanceScorer — Real-time Relevance Scoring
# ═══════════════════════════════════════════════════════════════════

class RelevanceScorer:
    """
    Scores retrieved entries against the current context in real-time.

    Factors:
      - Semantic similarity (from SemanticIndex)
      - Recency (more recent = more relevant)
      - Past usefulness (entries that contributed to good answers)
      - Emotional alignment (affect-congruent entries preferred)

    Integration:
      - PrefrontalCortex.hierarchical_control_signal() for abstraction weighting
    """

    def __init__(self, prefrontal=None,
                 weights: Optional[Dict[str, float]] = None):
        self._prefrontal = prefrontal    # PrefrontalCortex (optional)
        self._weights = weights or {
            'semantic': 0.4,
            'activation': 0.25,
            'recency': 0.15,
            'emotional': 0.1,
            'confidence': 0.1,
        }
        self._total_scored = 0
        logger.info("RelevanceScorer initialized")

    def score(self, entries: List[Any], query: str,
              emotional_valence: float = 0.0) -> List[Any]:
        """
        Score and rank entries by relevance to query.

        Args:
            entries: List of MoltbookEntry objects
            query: Current query/context text
            emotional_valence: Current emotional state (-1 to 1)

        Returns:
            Entries sorted by combined relevance score (highest first)
        """
        if not entries:
            return []

        self._total_scored += len(entries)
        current_time = time.time()

        # Get abstraction level from PFC (if available)
        abstraction_weight = 0.5
        if self._prefrontal:
            try:
                pfc_result = self._prefrontal.process({
                    'task_type': 'scoring',
                    'query': query[:100]
                })
                if isinstance(pfc_result, dict):
                    abstraction_weight = pfc_result.get('abstraction_level', 0.5)
            except Exception:
                pass

        scored_entries = []
        for entry in entries:
            # Compute individual scores
            activation = entry.compute_activation(current_time)

            # Recency score
            age_hours = (current_time - entry.last_accessed) / 3600.0
            recency = math.exp(-0.01 * age_hours)

            # Emotional alignment
            emotional_alignment = 1.0 - abs(entry.emotional_valence - emotional_valence)

            # Combined score
            combined = (
                self._weights['activation'] * activation +
                self._weights['recency'] * recency +
                self._weights['emotional'] * emotional_alignment +
                self._weights['confidence'] * entry.confidence
            )

            # Semantic score from entry's existing relevance_score
            combined += self._weights['semantic'] * entry.relevance_score

            # Store score for sorting
            entry._combined_score = combined
            scored_entries.append(entry)

        # Sort by combined score
        scored_entries.sort(key=lambda e: getattr(e, '_combined_score', 0), reverse=True)

        return scored_entries

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_scored': self._total_scored,
            'weights': self._weights,
        }


# ═══════════════════════════════════════════════════════════════════
# [25] KnowledgeDecay — Ebbinghaus Forgetting Curve
# ═══════════════════════════════════════════════════════════════════

class KnowledgeDecay:
    """
    Manages Ebbinghaus-based forgetting for Moltbook entries.

    Frequently accessed → slow decay
    Rarely accessed → fast decay
    Emotionally charged → slower decay (amygdala-modulated)

    Integration:
      - MoltbookStore for entry updates
      - AmygdalaComplex for emotional modulation
      - DreamMode for offline consolidation
    """

    def __init__(self, moltbook=None, amygdala=None,
                 base_decay_rate: float = 0.001,
                 consolidation_threshold: float = 0.1):
        self._moltbook = moltbook
        self._amygdala = amygdala
        self._base_decay_rate = base_decay_rate
        self._consolidation_threshold = consolidation_threshold
        self._total_decayed = 0
        self._total_consolidated = 0
        logger.info("KnowledgeDecay initialized")

    def apply_decay(self, current_time: Optional[float] = None) -> Dict[str, int]:
        """
        Apply decay to all entries in the Moltbook.

        Returns dict with counts: {'decayed': N, 'below_threshold': M}
        """
        if not self._moltbook:
            return {'decayed': 0, 'below_threshold': 0}

        t = current_time or time.time()
        below_threshold = 0
        decayed = 0

        for entry in list(self._moltbook._entries.values()):
            activation = entry.compute_activation(t)
            if activation < self._consolidation_threshold:
                below_threshold += 1
            decayed += 1

        self._total_decayed += decayed
        return {'decayed': decayed, 'below_threshold': below_threshold}

    def consolidate(self) -> Dict[str, int]:
        """
        Run consolidation: remove dead entries, boost important ones.

        Should be called during dream/idle cycles.
        """
        if not self._moltbook:
            return {'removed': 0, 'boosted': 0}

        result = self._moltbook.consolidate(self._consolidation_threshold)
        self._total_consolidated += result.get('removed', 0)
        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_decayed': self._total_decayed,
            'total_consolidated': self._total_consolidated,
            'base_decay_rate': self._base_decay_rate,
        }


# ═══════════════════════════════════════════════════════════════════
# [20] AttentionDrivenRetrieval — ACh-modulated Retrieval
# ═══════════════════════════════════════════════════════════════════

class AttentionDrivenRetrieval:
    """
    Attention-modulated knowledge retrieval.

    ACh (acetylcholine) from BasalForebrain controls retrieval width:
      - High ACh → narrow, focused search (learning mode)
      - Low ACh → broad, exploratory search (retrieval mode)

    Theta-Gamma coupling from SeptalNuclei determines workspace capacity
    (how many entries can be simultaneously active).

    Implements Lisman-Jensen: max ~7±2 active knowledge chunks.
    """

    def __init__(self, basal_forebrain=None, septal_nuclei=None,
                 base_top_k: int = 7):
        self._basal_forebrain = basal_forebrain  # BasalForebrain (optional)
        self._septal_nuclei = septal_nuclei      # SeptalNuclei (optional)
        self._base_top_k = base_top_k
        self._total_retrievals = 0
        logger.info("AttentionDrivenRetrieval initialized")

    def get_retrieval_params(self) -> Dict[str, Any]:
        """
        Get current retrieval parameters based on neuromodulatory state.

        Returns dict with:
          - top_k: How many entries to retrieve
          - threshold: Similarity threshold
          - breadth: Search breadth factor
        """
        top_k = self._base_top_k
        threshold = 0.5
        breadth = 0.5

        # ACh modulation from basal forebrain
        if self._basal_forebrain:
            try:
                bf_result = self._basal_forebrain.process({
                    'task_type': 'retrieval'
                })
                if isinstance(bf_result, dict):
                    ach = bf_result.get('ach_level', bf_result.get('acetylcholine', 0.5))
                    if isinstance(ach, (int, float)):
                        # High ACh → narrow search (higher threshold, fewer results)
                        threshold = 0.3 + 0.4 * float(ach)
                        breadth = 1.0 - 0.5 * float(ach)
            except Exception:
                pass

        # Workspace capacity from septal nuclei
        if self._septal_nuclei:
            try:
                sn_result = self._septal_nuclei.process({
                    'mode': 'memory_capacity'
                })
                if isinstance(sn_result, dict):
                    capacity = sn_result.get('memory_capacity',
                                             sn_result.get('theta_gamma_capacity', 7))
                    if isinstance(capacity, (int, float)):
                        top_k = max(3, min(12, int(capacity)))
            except Exception:
                pass

        self._total_retrievals += 1
        return {
            'top_k': top_k,
            'threshold': threshold,
            'breadth': breadth,
        }

    def retrieve(self, moltbook, query: str) -> List[Any]:
        """
        Retrieve entries with attention-modulated parameters.

        Args:
            moltbook: MoltbookStore instance
            query: Search query

        Returns:
            List of relevant MoltbookEntry objects
        """
        params = self.get_retrieval_params()
        return moltbook.query_semantic(
            query,
            top_k=params['top_k'],
            threshold=params['threshold']
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_retrievals': self._total_retrievals,
            'base_top_k': self._base_top_k,
        }
