"""Multi-Hop Advisor — Phase 6.

Decides whether an incoming intent should go through the multi-hop plan
executor or stay on the single-hop capability-router path. Cheap heuristic
only; no LLM call. Wrong answer is always recoverable: if advisor says
multi-hop but the planner can't decompose, BrainChat falls back to single-hop.

Triggers (any one wins):
  1. Explicit user mention: @plan, @multihop
  2. Connective phrases: "und dann", "und schreib", "then", "after that",
     "before", "step by step", "step-by-step", "danach", "anschliessend"
  3. ≥2 imperative verb-clusters in the intent
  4. Capability route is semantic (not regex) AND best similarity < 0.70 —
     means the router is unsure; multi-hop planner often does better.

Returns (should_decompose: bool, reason: str). The reason string is recorded
in telemetry so we can later tune which trigger fires most.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


# Compiled once at import — cheap regex matching on hot path.
_EXPLICIT_TRIGGERS = re.compile(
    r"@(plan|multihop)\b",
    re.IGNORECASE,
)

_CONNECTIVES = re.compile(
    r"\b("
    r"step[- ]by[- ]step|"
    r"first.*?(then|next|after that)|"
    r"und dann|und schreib|und erstell|und füg|und bewerte|und mach|und send|und speicher|"
    r"danach|anschliessend|nachdem|bevor|"
    r"then\s+(also|next|finally|create|add|evaluate|score|send)|"
    r"after\s+that|"
    r"finally"
    r")\b",
    re.IGNORECASE,
)

# Loose imperative-verb detector. We don't try to be perfect — extra
# false positives are fine because the planner is the one that ultimately
# decides if multi-hop adds value (it'll produce a 1-step plan if not).
_VERB_TOKENS_DE = (
    "erstell", "lege", "leg", "füg", "addier", "schreib", "send", "speicher",
    "bewerte", "evaluier", "analysier", "scan", "scann", "prüf", "such",
    "find", "lade", "lese", "extrahier", "report", "fass",
)
_VERB_TOKENS_EN = (
    "create", "make", "add", "append", "write", "send", "store", "save",
    "evaluate", "assess", "score", "rate", "analyze", "analyse", "scan",
    "check", "verify", "search", "find", "list", "show", "fetch", "read",
    "extract", "report", "summarize", "summarise", "draft", "compose",
)


@dataclass
class AdvisorVerdict:
    should_decompose: bool
    reason: str
    triggered_by: str            # 'explicit' | 'connective' | 'multi_verb' | 'low_confidence' | 'none'
    detected_verbs: int = 0
    intent_length: int = 0


class MultiHopAdvisor:
    """Tiny, opinionated decision layer between BrainChat and the multi-hop planner."""

    def __init__(
        self,
        *,
        min_verb_count: int = 2,
        semantic_low_confidence: float = 0.70,
        min_intent_words: int = 4,
    ) -> None:
        self.min_verb_count = min_verb_count
        self.semantic_low_confidence = semantic_low_confidence
        # Very short intents ("hi", "thanks") are never multi-hop.
        self.min_intent_words = min_intent_words
        self.stats = {
            "asked": 0,
            "decompose_true": 0,
            "decompose_false": 0,
            "by_trigger": {
                "explicit": 0,
                "connective": 0,
                "multi_verb": 0,
                "low_confidence": 0,
                "none": 0,
            },
        }

    def should_decompose(
        self,
        intent: str,
        route_match: Any = None,
    ) -> AdvisorVerdict:
        """Cheap heuristic. Returns an AdvisorVerdict the caller logs +
        acts on. Never raises — bad input → ('false', 'invalid intent')."""
        self.stats["asked"] += 1
        if not intent or not isinstance(intent, str):
            v = AdvisorVerdict(False, "empty/invalid intent", "none")
            self._record(v)
            return v

        text = intent.strip()
        words = text.split()
        if len(words) < self.min_intent_words:
            v = AdvisorVerdict(False, f"too short ({len(words)} words)", "none",
                               intent_length=len(words))
            self._record(v)
            return v

        # 1. Explicit mention wins
        if _EXPLICIT_TRIGGERS.search(text):
            v = AdvisorVerdict(True, "user explicitly requested multi-hop", "explicit",
                               intent_length=len(words))
            self._record(v)
            return v

        # 2. Connective phrase
        m = _CONNECTIVES.search(text)
        if m is not None:
            v = AdvisorVerdict(True, f"connective phrase: {m.group(0)!r}", "connective",
                               intent_length=len(words))
            self._record(v)
            return v

        # 3. ≥N imperative verbs
        verb_count = self._count_verbs(text)
        if verb_count >= self.min_verb_count:
            v = AdvisorVerdict(True, f"{verb_count} imperative verbs detected", "multi_verb",
                               detected_verbs=verb_count, intent_length=len(words))
            self._record(v)
            return v

        # 4. Low-confidence semantic match — planner often disambiguates
        if route_match is not None:
            method = getattr(route_match, "match_method", None)
            if method == "semantic":
                # matched_pattern looks like '<semantic sim=0.687 via anchor[2]>'
                pat = getattr(route_match, "matched_pattern", "") or ""
                m_sim = re.search(r"sim=([\d.]+)", pat)
                if m_sim:
                    try:
                        sim = float(m_sim.group(1))
                        if sim < self.semantic_low_confidence:
                            v = AdvisorVerdict(
                                True,
                                f"semantic confidence {sim:.2f} below "
                                f"{self.semantic_low_confidence}",
                                "low_confidence",
                                detected_verbs=verb_count,
                                intent_length=len(words),
                            )
                            self._record(v)
                            return v
                    except ValueError:
                        pass

        v = AdvisorVerdict(False, "single-hop sufficient", "none",
                           detected_verbs=verb_count, intent_length=len(words))
        self._record(v)
        return v

    def _count_verbs(self, text: str) -> int:
        """Count distinct imperative-verb stems present. Very loose: looks
        for known stem prefixes at word boundaries. Repeated stems count
        once each — repetition is not multi-step."""
        lower = text.lower()
        seen: set[str] = set()
        for stem in _VERB_TOKENS_DE + _VERB_TOKENS_EN:
            if re.search(rf"\b{re.escape(stem)}", lower):
                seen.add(stem)
        return len(seen)

    def _record(self, v: AdvisorVerdict) -> None:
        if v.should_decompose:
            self.stats["decompose_true"] += 1
        else:
            self.stats["decompose_false"] += 1
        bt = self.stats["by_trigger"]
        bt[v.triggered_by] = bt.get(v.triggered_by, 0) + 1

    def stats_dict(self) -> dict:
        return dict(self.stats)
