"""C6 — Selector-based plan orchestration (AutoGen SelectorGroupChat).

"ein selector autogen agents grp chat zum orchestrieren des plans" — a multi-hop
plan is run by a SelectorGroupChat: a selector picks which agent handles the next
READY step (its deps satisfied, not yet done), in dependency order.

The selector decision logic here is DETERMINISTIC (driven by the plan's hop->agent
assignment + completion state derived from the chat thread), so it is testable
without an LLM/GPU. The AutoGen team is built with an INJECTED cloud model_client
(GPU-free, e.g. Groq/OpenAI — as C1c proved cloud LLM works) when actually run.

Dependencies: autogen_agentchat (installed). The participant agents + a model_client
need autogen_ext[openai] (NOT yet installed) — build_team raises a clear error until
then; the selector logic works standalone regardless. Flag PLAN_ORCHESTRATOR_ENABLED.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

logger = logging.getLogger("brain.plan_orchestrator")

ENABLED = os.environ.get("PLAN_ORCHESTRATOR_ENABLED", "0") == "1"


def _hops(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    return plan.get("hops") or []


def hop_agent(hop: Dict[str, Any]) -> Optional[str]:
    """The agent assigned to a hop: explicit 'agent', else derived from an
    'openfang:<name>' execution_target, else the capability name as a fallback."""
    if hop.get("agent"):
        return hop["agent"]
    tgt = hop.get("execution_target") or ""
    if isinstance(tgt, str) and tgt.startswith("openfang:"):
        return tgt.split(":", 1)[1]
    return hop.get("capability")


def participants(plan: Dict[str, Any]) -> List[str]:
    """Distinct agents the plan needs (the group-chat participants), in first-use order."""
    seen: List[str] = []
    for h in _hops(plan):
        a = hop_agent(h)
        if a and a not in seen:
            seen.append(a)
    return seen


def next_agent(plan: Dict[str, Any], completed: Set[str]) -> Optional[str]:
    """Pick the agent for the next READY hop: the first hop (in plan order) whose
    step_id is not completed AND all of whose depends_on are completed. None = done
    or blocked (no ready hop)."""
    for h in _hops(plan):
        sid = h.get("step_id")
        if not sid or sid in completed:
            continue
        deps = h.get("depends_on") or []
        if all(d in completed for d in deps):
            return hop_agent(h)
    return None


def next_step(plan: Dict[str, Any], completed: Set[str]) -> Optional[str]:
    """The step_id of the next ready hop (sibling of next_agent)."""
    for h in _hops(plan):
        sid = h.get("step_id")
        if not sid or sid in completed:
            continue
        if all(d in completed for d in (h.get("depends_on") or [])):
            return sid
    return None


def make_selector_func(plan: Dict[str, Any],
                       completed_from_thread: Callable[[Sequence[Any]], Set[str]]
                       ) -> Callable[[Sequence[Any]], Optional[str]]:
    """Build a SelectorGroupChat selector_func: given the message thread, derive the
    set of completed step_ids (via the injected reader) and return the next agent's
    name (or None to let AutoGen's default LLM-selector decide)."""
    def _selector(thread: Sequence[Any]) -> Optional[str]:
        try:
            done = completed_from_thread(thread)
            return next_agent(plan, done)
        except Exception as exc:  # never break the chat — fall back to LLM selector
            logger.debug("[plan-orchestrator] selector error -> LLM default: %s", exc)
            return None
    return _selector


def build_team(plan: Dict[str, Any], *, model_client: Any,
               agent_factory: Optional[Callable[[str], Any]] = None,
               completed_from_thread: Optional[Callable[[Sequence[Any]], Set[str]]] = None,
               max_messages: int = 30):
    """Construct an AutoGen SelectorGroupChat for the plan. Requires autogen_agentchat
    (installed) + a model_client (autogen_ext[openai], inject GPU-free cloud client).
    Raises a clear error if the deps are missing."""
    try:
        from autogen_agentchat.teams import SelectorGroupChat
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.conditions import MaxMessageTermination
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "autogen_agentchat unavailable — pip install autogen-agentchat"
        ) from exc
    if model_client is None:
        raise RuntimeError(
            "model_client required — pip install 'autogen-ext[openai]' and inject a "
            "GPU-free cloud client (e.g. Groq/OpenAI), as C1c proved works"
        )
    names = participants(plan)
    factory = agent_factory or (lambda n: AssistantAgent(name=n, model_client=model_client))
    agents = [factory(n) for n in names]
    reader = completed_from_thread or (lambda thread: set())
    selector = make_selector_func(plan, reader)
    return SelectorGroupChat(
        participants=agents,
        model_client=model_client,
        selector_func=selector,
        termination_condition=MaxMessageTermination(max_messages),
    )
