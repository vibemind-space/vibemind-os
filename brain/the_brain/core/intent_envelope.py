"""Phase 11.B — vibemind.intent.v1 Envelope Builder.

Brain dispatches a hop to an OpenFang-Agent. The agent (Sonnet/Opus/etc)
needs structured context to decide which MCP-tool to call and how. The
envelope provides:

  - event_type        the bubble.create / idea.expand / etc.
  - space             which Space the event lives in
  - preferred_tool    which MCP-tool the agent should try first
  - required_params   what the tool needs at minimum
  - params            args from the plan (rendered_arg)
  - context           {user_text, plan_rationale, recall, self_prior, prev_outputs}
  - user_text         original intent

Schema: vibemind.intent.v1 (already documented in brain-bubbles agent.toml).

Usage:
  envelope = build_envelope(
      hop=hop, plan=plan, event_id="bubble.create",
      preferred_tool="bubble_create",
      decision_context={...}, prev_outputs={...},
  )
  # Then POST envelope as JSON-string in {"message": json.dumps(envelope)}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


_SPACE_INPUT_ALIASES = {
    "shuttles": "bubbles",
}


def normalize_space_id(space: str) -> str:
    """Normalize legacy input spellings before routing or persistence."""
    normalized = (space or "").strip().lower()
    return _SPACE_INPUT_ALIASES.get(normalized, normalized)


def _truncate(s: str, n: int = 240) -> str:
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def build_envelope(
    *,
    event_id: str,
    params: Dict[str, Any],
    plan_intent: str = "",
    plan_rationale: str = "",
    plan_id: str = "",
    step_id: str = "",
    preferred_tool: str = "",
    decision_context: Optional[Dict[str, Any]] = None,
    prev_outputs: Optional[Dict[str, Any]] = None,
    space_override: str = "",
) -> Dict[str, Any]:
    """Build vibemind.intent.v1 envelope.

    The agent's system_prompt knows this schema and will:
      1. Try preferred_tool with provided params
      2. Fill missing required_params from context.user_text
      3. Use context.recall for similar past attempts
    """
    # Infer space from event_id namespace (e.g. bubble.create -> "bubbles")
    namespace = event_id.split(".", 1)[0] if "." in event_id else "general"
    space = normalize_space_id(space_override or namespace)

    # Pluralize to match agent.toml conventions (space:bubbles, space:ideas)
    if space and not space.endswith("s"):
        # Conservative: only add 's' for known singular-namespaces
        if space in ("bubble", "idea", "code", "video"):
            space = space + "s"

    ctx = decision_context or {}
    recall = ctx.get("recall") or []
    self_prior = ctx.get("self_prior") or {}
    critic = ctx.get("critic") or {}

    envelope: Dict[str, Any] = {
        "schema": "vibemind.intent.v1",
        "event_type": event_id,
        "space": space,
        "params": params or {},
        "user_text": _truncate(plan_intent, 600),
        "context": {
            "plan_id": plan_id,
            "step_id": step_id,
            "plan_rationale": _truncate(plan_rationale, 400),
            "recall": [
                {
                    "intent": _truncate(r.get("intent", ""), 100),
                    "outcome": r.get("outcome", ""),
                    "success_rate": r.get("success_rate", 0),
                    "chain": " -> ".join((r.get("capability_chain") or [])[:5]),
                }
                for r in (recall[:3] if isinstance(recall, list) else [])
            ],
            "self_prior_best": {
                "capability": self_prior.get("best_capability", ""),
                "confidence": self_prior.get("best_confidence", 0),
            } if self_prior else {},
            "critic_recommend": critic.get("recommend", ""),
            "previous_hop_outputs": _normalize_prev_outputs(prev_outputs or {}),
        },
    }

    if preferred_tool:
        envelope["preferred_tool"] = preferred_tool

    return envelope


def _normalize_prev_outputs(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Trim previous hop outputs to keep envelope compact.
    Each value: max 240 chars. Drop binary/large data."""
    out: Dict[str, Any] = {}
    for k, v in (outputs or {}).items():
        if isinstance(v, (dict, list)):
            try:
                serialized = json.dumps(v, default=str)
                out[k] = (serialized[:240] + "...") if len(serialized) > 240 else json.loads(serialized)
            except Exception:
                out[k] = str(v)[:240]
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v if not isinstance(v, str) else _truncate(v, 240)
        else:
            out[k] = str(v)[:240]
    return out


def envelope_to_message(envelope: Dict[str, Any]) -> str:
    """Serialize envelope as the message payload for OpenFang.
    OpenFang's /api/agents/<id>/message expects {"message": "..."}.
    The agent's system_prompt parses the JSON-stringified envelope.
    """
    return json.dumps(envelope, ensure_ascii=False)
