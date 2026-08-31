"""L4 / GapSentinel — brain-side capability-gap detection + honest response + dispatch.

The glue that closes the loop the user asked for: when the brain has NO tool for an
intent, or a capability is UNRELIABLE (claims success but the world keeps disagreeing —
D's MISMATCH), or UNVERIFIABLE (no world-check possible), be HONEST about it ("sry, das
kann ich (noch) nicht — soll ich ein Issue erstellen?") and hand the gap to the
capability-gap-filer OpenFang agent (C1, live-green) to file a GitHub issue.

Builds on:
  - the routing no-match signal (capability_router.route() -> None)        -> NO_TOOL
  - D.2 execution_log reliability {match, mismatch, unverified, n}         -> UNRELIABLE / UNVERIFIABLE
  - C2 timeout_sentinel handles the TIMEOUT kind already (direct gh filing).

Hybrid UX (verified design): LIVE turn -> ask the user first (pending_question);
AUTONOMOUS run -> dispatch straight to the gap-filer. Reward/ground-truth comes ONLY
from D's verified ok — never from the answer text (so a friendly "hallo" with no world
change is itself the gap signal).

Flag CAPABILITY_GAP_ENABLED (default OFF). Fail-safe: detection/dispatch errors never
break the turn.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("brain.capability_gap")

ENABLED = os.environ.get("CAPABILITY_GAP_ENABLED", "0") == "1"
MIN_SUPPORT = int(os.environ.get("CAPABILITY_GAP_MIN_SUPPORT", "3"))
MISMATCH_THRESHOLD = float(os.environ.get("CAPABILITY_GAP_MISMATCH_THRESHOLD", "0.5"))

# gap kinds (TIMEOUT lives in C2 timeout_sentinel)
NO_TOOL = "NO_TOOL"
UNRELIABLE = "UNRELIABLE"
UNVERIFIABLE = "UNVERIFIABLE"

_GAP_AGENT_TARGET = "openfang:capability-gap-filer"  # the live-green C1 agent


def make_gap(kind: str, *, missing_capability: str, intent: str = "",
             frequency: int = 1, failure_patterns: Optional[list] = None,
             evidence: str = "", suggested_tools: Optional[list] = None) -> Dict[str, Any]:
    """Build a CapabilityGap (the payload the gap-filer agent + issue-detector consume)."""
    import hashlib
    gap_id = hashlib.md5(f"{kind}:{missing_capability}".encode()).hexdigest()[:12]
    return {
        "gap_id": gap_id, "kind": kind, "missing_capability": missing_capability,
        "intent": intent, "frequency": frequency,
        "failure_patterns": failure_patterns or [], "evidence": evidence,
        "suggested_tools": suggested_tools or [], "detected_at": time.time(),
    }


def assess_no_tool(intent: str, routed_capability: Optional[str]) -> Optional[Dict[str, Any]]:
    """route() returned None for this intent -> the brain has no tool. NO_TOOL gap."""
    if routed_capability:
        return None
    return make_gap(NO_TOOL, missing_capability=intent or "(unknown)", intent=intent,
                    failure_patterns=["capability_router.route() -> None (no match)"])


# Error substrings that mean the brain has NO tool for this (a real capability
# gap). Kept distinct from TRANSIENT outages (OpenFang down, timeout, connection
# refused) which are NOT a missing capability and must never file a NO_TOOL issue —
# those are C2/transient territory. Used by the multihop plan_executor hook so a
# genuinely-unresolvable hop (planner-hallucinated capability, no executor) files a
# gap, while an OpenFang outage or timeout does not.
_NO_TOOL_MARKERS = (
    "no execution target",  # plan_executor's exact error for an unresolvable capability
    "unknown capability", "no capability", "not registered", "no executor",
    "no tool", "route() -> none", "no such capability", "capability not found",
    "unsupported capability", "no matching capability",
)
_TRANSIENT_MARKERS = (
    "openfangunavailable", "unreachable", "timeout", "timed out", "connection",
    "temporarily", "refused", "503", "502", "transient",
)


def is_no_tool_error(error: Any) -> bool:
    """True only if a hop-failure error indicates a genuinely MISSING capability/tool
    (not a transient outage). The multihop GapSentinel hook uses this so a real 'no
    tool' failure files a NO_TOOL gap, while OpenFang-down / timeout (C2's domain)
    does not. Conservative: a transient marker anywhere wins (returns False)."""
    s = str(error or "").lower()
    if not s:
        return False
    if any(m in s for m in _TRANSIENT_MARKERS):
        return False
    return any(m in s for m in _NO_TOOL_MARKERS)


def assess_reliability(capability: str, reliability: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """From D.2 reliability {match, mismatch, unverified, n}: a capability that keeps
    claiming success while the world disagrees (UNRELIABLE), or can never be verified
    (UNVERIFIABLE). Needs >= MIN_SUPPORT attempts before judging (avoid over-reacting)."""
    try:
        n = int(reliability.get("n", 0))
        if n < MIN_SUPPORT:
            return None
        mismatch = int(reliability.get("mismatch", 0))
        unverified = int(reliability.get("unverified", 0))
        match = int(reliability.get("match", 0))
        if mismatch / n >= MISMATCH_THRESHOLD:
            return make_gap(UNRELIABLE, missing_capability=capability,
                            frequency=mismatch,
                            failure_patterns=[f"{mismatch}/{n} MISMATCH (claimed ok, world refuted)"],
                            evidence=f"reliability={reliability}")
        if match == 0 and unverified == n:
            return make_gap(UNVERIFIABLE, missing_capability=capability,
                            frequency=unverified,
                            failure_patterns=[f"{unverified}/{n} UNVERIFIED (no world-check possible)"],
                            evidence=f"reliability={reliability}")
        return None
    except Exception as exc:
        logger.debug("[gap-sentinel] reliability assess error: %s", exc)
        return None


_HONEST = {
    NO_TOOL: "Sry, dafür habe ich (noch) kein Werkzeug",
    UNRELIABLE: "Sry, das kann ich gerade nicht zuverlässig — es behauptet Erfolg, aber die Welt bestätigt es nicht",
    UNVERIFIABLE: "Ich kann das tun, aber NICHT garantieren dass es wirklich klappte",
}


def honest_response(gap: Dict[str, Any], *, offer_issue: bool = True) -> str:
    """The user-facing honest line for a gap (the 'sry kann ich nicht' surface)."""
    base = _HONEST.get(gap.get("kind"), "Sry, das kann ich nicht")
    cap = gap.get("missing_capability") or gap.get("intent") or ""
    msg = f"{base}: {cap}." if cap else f"{base}."
    if offer_issue:
        msg += " Soll ich ein Issue erstellen, damit es nachgerüstet wird?"
    return msg


def handle(gap: Optional[Dict[str, Any]], *, live: bool,
           dispatcher: Optional[Callable[[Dict[str, Any]], Any]] = None,
           enabled: Optional[bool] = None, dry_run: bool = True) -> Dict[str, Any]:
    """Hybrid gap handler. LIVE -> ask the user (pending_question, no dispatch);
    AUTONOMOUS -> dispatch to the gap-filer agent. Returns a result dict; never raises."""
    on = ENABLED if enabled is None else enabled
    if not on or not gap:
        return {"skipped": "disabled" if not on else "no_gap"}
    try:
        msg = honest_response(gap)
        if live:
            # surface to the user; the actual filing happens on their 'yes' next turn
            return {"pending_question": msg, "gap": gap, "target": _GAP_AGENT_TARGET}
        # autonomous: hand straight to the gap-filer agent (C1)
        payload = dict(gap); payload["dry_run"] = dry_run
        if dispatcher is None:
            return {"would_dispatch": _GAP_AGENT_TARGET, "gap": gap,
                    "note": "no dispatcher injected"}
        result = dispatcher(payload)
        logger.info("[gap-sentinel] dispatched %s gap '%s' -> %s",
                    gap.get("kind"), gap.get("missing_capability"), _GAP_AGENT_TARGET)
        return {"dispatched": True, "target": _GAP_AGENT_TARGET, "result": result}
    except Exception as exc:  # fail-safe — a gap-handling error must not break the turn
        logger.warning("[gap-sentinel] handle failed: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def default_dispatcher(gap: Dict[str, Any]) -> Any:
    """Dispatch a gap to the capability-gap-filer agent (C1, live-green) via the brain's
    OpenFangExecutor. The agent (Groq LLM, no GPU) turns the gap into a GitHub issue via
    issue-detector. dry_run defaults true. Used as the `dispatcher` for autonomous handle()."""
    import json
    from core.capability_targets import build_executor
    payload = dict(gap)
    payload.setdefault("dry_run", True)
    exe = build_executor(_GAP_AGENT_TARGET)
    return exe.call_with_arg(json.dumps(payload))
