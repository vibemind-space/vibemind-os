# core/outcome_reward.py
"""
OutcomeRewardTracker — outcome-based reward signals for neuroplasticity.

Instead of evaluating thought *quality* (ThoughtJury does that),
this tracks whether thoughts produce real outcomes:

  Signal 1: Thought → new Moltbook entry          reward=+0.5
  Signal 2: Thought → new Meta-KG edge             reward=+0.8
  Signal 3: Thought cited in chat response          reward=+0.9
  Signal 4: Thought repeats existing knowledge      reward=-0.2

All signals feed into ThoughtRadialBridge.record_reward() →
Hebbian.update_with_reward() → real neuroplasticity.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger('brain.outcome_reward')


class OutcomeRewardTracker:

    def __init__(self, bridge, cte,
                 moltbook_store=None, meta_graph=None):
        self._bridge = bridge
        self._cte = cte
        self._moltbook = moltbook_store
        self._meta_graph = meta_graph
        self._lock = threading.Lock()
        self._rewarded_ids: Dict[str, bool] = {}
        self._stats = {
            'moltbook_entry': 0,
            'mkg_edge': 0,
            'cited': 0,
            'redundant': 0,
        }

    # ── Signal 1: Thought led to Moltbook entry ──────────────

    def on_moltbook_entry(self, thought_id: str) -> None:
        if not thought_id or not self._bridge:
            return
        if self._already_rewarded(thought_id, 'moltbook_entry'):
            return
        self._bridge.record_reward(thought_id, 0.5, "moltbook_entry")
        self._stats['moltbook_entry'] += 1
        logger.debug(f"Outcome reward: moltbook_entry for {thought_id}")

    # ── Signal 2: Consolidation created new MKG edges ────────

    def on_new_mkg_edges(self, new_edge_count: int) -> None:
        if new_edge_count <= 0 or not self._bridge or not self._cte:
            return
        # Reward top-3 recent high-relevance thoughts
        try:
            with self._cte._thought_lock:
                recent = sorted(
                    list(self._cte._thoughts)[-20:],
                    key=lambda t: t.relevance, reverse=True,
                )[:3]
        except Exception:
            return
        for t in recent:
            tid = getattr(t, 'thought_id', '')
            if tid and not self._already_rewarded(tid, 'mkg_edge'):
                self._bridge.record_reward(tid, 0.8, "mkg_edge_created")
                self._stats['mkg_edge'] += 1
        logger.debug(f"Outcome reward: {new_edge_count} new MKG edges")

    # ── Signal 3: Thought cited in chat response ─────────────

    def on_thoughts_cited(self, thought_ids: List[str]) -> None:
        if not self._bridge:
            return
        for tid in thought_ids:
            if tid and not self._already_rewarded(tid, 'cited'):
                self._bridge.record_reward(tid, 0.9, "cited_in_response")
                self._stats['cited'] += 1
                logger.debug(f"Outcome reward: cited {tid}")

    # ── Signal 4: Thought repeats existing knowledge ─────────

    def check_redundancy(self, thought) -> None:
        if not self._moltbook or not self._bridge:
            return
        content = getattr(thought, 'content', '')
        tid = getattr(thought, 'thought_id', '')
        if not content or not tid:
            return
        try:
            idx = self._moltbook.semantic_index
            emb = idx.embed(content[:300])
            results = idx.search(emb, top_k=1, threshold=0.85)
            if results:
                self._bridge.record_reward(tid, -0.2, "redundant_thought")
                self._stats['redundant'] += 1
        except Exception:
            pass

    # ── Dedup + Stats ────────────────────────────────────────

    def _already_rewarded(self, thought_id: str, outcome: str) -> bool:
        key = f"{thought_id}:{outcome}"
        with self._lock:
            if key in self._rewarded_ids:
                return True
            self._rewarded_ids[key] = True
            if len(self._rewarded_ids) > 500:
                keys = list(self._rewarded_ids.keys())
                for k in keys[:250]:
                    del self._rewarded_ids[k]
            return False

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
