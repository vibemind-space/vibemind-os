"""
IntentAggregator — Phase R+.3.

Reads the tweets from a Mode-2 (Intent) discourse round and decides
who should take the user's task. Calls Brain's groq_subagent
(Llama-3.3-70b) with a structured-JSON prompt.

Output schema::

    {
        "primary":     "agent-name",       # primary owner of the task
        "supporting":  ["agent2", ...],    # contributors
        "risks":       ["risk1", ...],     # concerns to flag
        "confidence":  0.0–1.0,            # decision confidence
        "reasoning":   "1-2 sentences"     # why
    }

If parsing fails or no dispatcher available, returns a fallback decision
with `confidence=0` so the caller falls back to user-confirm flow.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


SYNTH_PROMPT = """You are summarising a multi-agent discourse to make a routing decision.

A user just posted this intent / task:

  "{intent}"

Below are {n} VibeMind agent responses. Each agent self-classified as
"I CAN: ..." (would lead), "RELATED: ..." (would assist), or "NOT
MINE: ..." (would skip).

AGENT RESPONSES:
{tweets}

DECIDE: Who is the best fit to lead this task? Who should support?
What risks did the agents raise? How confident is your decision?

Output ONLY this JSON object (no preamble, no fences):

{{
  "primary":    "<best agent name from the list, or null if no clear fit>",
  "supporting": ["<agent name>", ...],
  "risks":      ["<concern raised>", ...],
  "confidence": <float 0.0 to 1.0>,
  "reasoning":  "<1-2 sentence justification>"
}}

Rules:
  - "primary" must be a name from the agents who replied "I CAN: ..."
    if any did. Otherwise null.
  - confidence ≥ 0.8 means: clear ownership + supporting agents agree.
  - confidence < 0.5 means: conflicting / unclear / no I CAN replies.
  - "risks" should mention concrete issues raised, not generic warnings.
  - reasoning: terse, factual.
"""


class IntentAggregator:
    """Groq-based decision-maker."""

    def __init__(self, dispatcher) -> None:
        """dispatcher: SubagentDispatcher (Brain core); used to call groq_subagent."""
        self.dispatcher = dispatcher

    def decide(
        self,
        intent: str,
        tweets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build prompt, call Groq, parse JSON, return decision."""
        if not tweets:
            return self._empty_decision("no agent tweets")
        if not self.dispatcher:
            return self._empty_decision("no dispatcher available")

        block_lines: List[str] = []
        for t in tweets[:30]:  # cap to 30 to keep prompt under TPM
            name = t.get("agent_name") or "?"
            resp = (t.get("response") or "").replace("\n", " ")[:240]
            block_lines.append(f"- @{name}: {resp}")
        block = "\n".join(block_lines)

        prompt = SYNTH_PROMPT.format(
            intent=intent[:600], n=len(tweets), tweets=block,
        )

        import os as _os
        try:
            result = self.dispatcher.dispatch(
                "groq_subagent",
                prompt=prompt,
                max_tokens=600,
                temperature=0.2,
                model=_os.environ.get(
                    "DISCOURSE_INTENT_MODEL",
                    "groq::llama-3.1-8b-instant",
                ),
            )
        except Exception as e:
            logger.warning(f"[intent-aggregator] dispatch failed: {e}")
            return self._empty_decision(f"dispatch error: {e}")

        if not result or not result.get("ok"):
            err = (result or {}).get("error", "unknown")
            return self._empty_decision(f"groq returned: {err}")

        text = (result.get("text") or "").strip()
        return self._parse_decision(text, fallback_reason="parse failed")

    @staticmethod
    def _parse_decision(text: str, fallback_reason: str = "no JSON") -> Dict[str, Any]:
        # Strip code fences if any
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        # Find first {...} block
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return IntentAggregator._empty_decision(fallback_reason)
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            return IntentAggregator._empty_decision(f"json parse: {e}")
        # Coerce types
        return {
            "primary":    d.get("primary") or None,
            "supporting": list(d.get("supporting") or [])[:5],
            "risks":      list(d.get("risks") or [])[:5],
            "confidence": float(max(0.0, min(1.0, d.get("confidence") or 0.0))),
            "reasoning":  str(d.get("reasoning") or "")[:500],
        }

    @staticmethod
    def _empty_decision(reason: str = "") -> Dict[str, Any]:
        return {
            "primary":    None,
            "supporting": [],
            "risks":      [],
            "confidence": 0.0,
            "reasoning":  f"(no decision: {reason})" if reason else "",
        }
