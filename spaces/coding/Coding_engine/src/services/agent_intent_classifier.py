"""Agent Intent Classifier – classifies agent intents and maps to actions.

Maintains a registry of known intents with patterns and confidence
thresholds. Classifies input text by matching against registered
patterns and returns ranked intent matches.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Intent:
    intent_id: str
    name: str
    category: str
    patterns: List[str]  # keywords/phrases to match
    action: str  # action to trigger
    min_confidence: float
    priority: int
    tags: List[str]
    total_matched: int
    created_at: float
    updated_at: float


@dataclass
class _Classification:
    classification_id: str
    input_text: str
    matched_intent_id: str
    matched_intent_name: str
    confidence: float
    agent: str
    created_at: float


class AgentIntentClassifier:
    """Classifies agent intents based on pattern matching."""

    CATEGORIES = ("command", "query", "action", "navigation", "system", "custom")

    def __init__(self, max_intents: int = 10000, max_classifications: int = 500000):
        self._intents: Dict[str, _Intent] = {}
        self._classifications: Dict[str, _Classification] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_intents = max_intents
        self._max_classifications = max_classifications
        self._seq = 0

        # stats
        self._total_intents = 0
        self._total_classifications = 0
        self._total_matched = 0
        self._total_unmatched = 0

    # ------------------------------------------------------------------
    # Intent Registration
    # ------------------------------------------------------------------

    def register_intent(
        self,
        name: str,
        patterns: Optional[List[str]] = None,
        category: str = "custom",
        action: str = "",
        min_confidence: float = 0.5,
        priority: int = 5,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if name in self._name_index:
            return ""
        if len(self._intents) >= self._max_intents:
            return ""
        if not patterns:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        iid = "int-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        intent = _Intent(
            intent_id=iid,
            name=name,
            category=category,
            patterns=[p.lower() for p in patterns],
            action=action,
            min_confidence=max(0.0, min(1.0, min_confidence)),
            priority=priority,
            tags=tags or [],
            total_matched=0,
            created_at=now,
            updated_at=now,
        )
        self._intents[iid] = intent
        self._name_index[name] = iid
        self._total_intents += 1
        self._fire("intent_registered", {"intent_id": iid, "name": name})
        return iid

    def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        i = self._intents.get(intent_id)
        if not i:
            return None
        return {
            "intent_id": i.intent_id,
            "name": i.name,
            "category": i.category,
            "patterns": list(i.patterns),
            "action": i.action,
            "min_confidence": i.min_confidence,
            "priority": i.priority,
            "tags": list(i.tags),
            "total_matched": i.total_matched,
            "created_at": i.created_at,
            "updated_at": i.updated_at,
        }

    def get_intent_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        iid = self._name_index.get(name)
        if not iid:
            return None
        return self.get_intent(iid)

    def remove_intent(self, intent_id: str) -> bool:
        i = self._intents.pop(intent_id, None)
        if not i:
            return False
        self._name_index.pop(i.name, None)
        # cascade remove classifications
        to_remove = [cid for cid, c in self._classifications.items()
                     if c.matched_intent_id == intent_id]
        for cid in to_remove:
            self._classifications.pop(cid, None)
        self._fire("intent_removed", {"intent_id": intent_id})
        return True

    def update_intent(
        self,
        intent_id: str,
        patterns: Optional[List[str]] = None,
        action: Optional[str] = None,
        min_confidence: Optional[float] = None,
        priority: Optional[int] = None,
    ) -> bool:
        i = self._intents.get(intent_id)
        if not i:
            return False
        if patterns is not None:
            i.patterns = [p.lower() for p in patterns]
        if action is not None:
            i.action = action
        if min_confidence is not None:
            i.min_confidence = max(0.0, min(1.0, min_confidence))
        if priority is not None:
            i.priority = priority
        i.updated_at = time.time()
        return True

    def list_intents(
        self,
        category: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for i in self._intents.values():
            if category and i.category != category:
                continue
            if tag and tag not in i.tags:
                continue
            results.append(self.get_intent(i.intent_id))
        return results

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, text: str, agent: str = "") -> Optional[Dict[str, Any]]:
        """Classify text against registered intents. Returns best match or None."""
        if not text:
            return None
        if len(self._classifications) >= self._max_classifications:
            return None

        text_lower = text.lower()
        best_intent = None
        best_confidence = 0.0

        for intent in self._intents.values():
            confidence = self._compute_confidence(text_lower, intent.patterns)
            if confidence >= intent.min_confidence and confidence > best_confidence:
                best_confidence = confidence
                best_intent = intent

        self._seq += 1
        now = time.time()
        self._total_classifications += 1

        if best_intent:
            raw = f"{text}-{best_intent.intent_id}-{now}-{self._seq}"
            cid = "cls-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            cls = _Classification(
                classification_id=cid,
                input_text=text,
                matched_intent_id=best_intent.intent_id,
                matched_intent_name=best_intent.name,
                confidence=best_confidence,
                agent=agent,
                created_at=now,
            )
            self._classifications[cid] = cls
            best_intent.total_matched += 1
            self._total_matched += 1
            self._fire("intent_classified", {
                "classification_id": cid,
                "intent": best_intent.name,
                "confidence": best_confidence,
            })
            return {
                "classification_id": cid,
                "intent_id": best_intent.intent_id,
                "intent_name": best_intent.name,
                "action": best_intent.action,
                "confidence": best_confidence,
                "category": best_intent.category,
            }
        else:
            self._total_unmatched += 1
            self._fire("intent_unmatched", {"text": text})
            return None

    def classify_multi(self, text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return top N matching intents ranked by confidence."""
        if not text:
            return []
        text_lower = text.lower()
        matches = []
        for intent in self._intents.values():
            confidence = self._compute_confidence(text_lower, intent.patterns)
            if confidence >= intent.min_confidence:
                matches.append({
                    "intent_id": intent.intent_id,
                    "intent_name": intent.name,
                    "action": intent.action,
                    "confidence": confidence,
                    "category": intent.category,
                    "priority": intent.priority,
                })
        matches.sort(key=lambda m: (-m["confidence"], -m["priority"]))
        return matches[:limit]

    def get_classification(self, classification_id: str) -> Optional[Dict[str, Any]]:
        c = self._classifications.get(classification_id)
        if not c:
            return None
        return {
            "classification_id": c.classification_id,
            "input_text": c.input_text,
            "matched_intent_id": c.matched_intent_id,
            "matched_intent_name": c.matched_intent_name,
            "confidence": c.confidence,
            "agent": c.agent,
            "created_at": c.created_at,
        }

    def search_classifications(
        self,
        intent_id: str = "",
        agent: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for c in self._classifications.values():
            if intent_id and c.matched_intent_id != intent_id:
                continue
            if agent and c.agent != agent:
                continue
            results.append(self.get_classification(c.classification_id))
        return results

    def _compute_confidence(self, text: str, patterns: List[str]) -> float:
        """Simple pattern matching confidence: fraction of patterns found in text."""
        if not patterns:
            return 0.0
        matched = sum(1 for p in patterns if p in text)
        return matched / len(patterns)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_intents": len(self._intents),
            "current_classifications": len(self._classifications),
            "total_intents": self._total_intents,
            "total_classifications": self._total_classifications,
            "total_matched": self._total_matched,
            "total_unmatched": self._total_unmatched,
        }

    def reset(self) -> None:
        self._intents.clear()
        self._classifications.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_intents = 0
        self._total_classifications = 0
        self._total_matched = 0
        self._total_unmatched = 0
