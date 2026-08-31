"""Contract Gate — pre-execution enforcement of workflow contracts (Baustein B).

Today a hop's `depends_on` is an ADVICE the LLM planner writes; the topological
walk respects ordering, but nothing *enforces* a smart-contract-style precondition
like "the coder may only start once the planner has completed AND validated". This
module adds that enforcement: before a hop runs, its `start_when` conditions are
checked against the executed-state; if unmet, the hop is blocked.

It also provides capability-gating: a worker may be required to clear a trust /
permission check before its action is allowed (the trust_level today is tracked
but never gates anything).

Safety — fail-open by construction:
  - Enforcement is OFF unless CONTRACT_ENFORCEMENT_ENABLED. When off, allow().
  - If a condition references an unknown step or can't be parsed, we ALLOW (never
    block on uncertainty — a contract bug must not wedge execution).
  - Capability-gating only blocks on an EXPLICIT deny; unknown trust = allow.

Condition grammar (a `start_when` entry):
    "<step_id>.completed"  — step ran and ok=True
    "<step_id>.ok"         — alias of .completed
    "<step_id>.verified"   — step's validator returned ground-truth verified=True (Baustein D)
    "<step_id>.done"       — step ran (ok or not)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


CONTRACT_ENFORCEMENT_ENABLED = _flag("CONTRACT_ENFORCEMENT_ENABLED")
CAPABILITY_GATING_ENABLED = _flag("CAPABILITY_GATING_ENABLED")
# Minimum trust to allow a gated capability (0..1). Below → blocked.
MIN_TRUST = float(os.environ.get("CAPABILITY_MIN_TRUST", "0.0"))


@dataclass
class GateDecision:
    allowed: bool = True
    reason: str = ""
    unmet: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason,
                "unmet": self.unmet or []}


def _eval_condition(cond: str, executed: Dict[str, Any]) -> Optional[bool]:
    """Evaluate one start_when condition against executed-state.

    Returns True (met) / False (unmet) / None (can't evaluate → caller allows).
    `executed` maps step_id → HopResult-like (has .ok and .validator_verdict, or
    a dict with those keys).
    """
    try:
        if "." not in cond:
            return None
        step_id, pred = cond.rsplit(".", 1)
        hr = executed.get(step_id)
        if hr is None:
            # the referenced step hasn't run yet → condition not met (not unknown)
            return False

        def _get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        ok = bool(_get(hr, "ok", False))
        pred = pred.lower()
        if pred in ("completed", "ok"):
            return ok
        if pred == "done":
            return True  # present in executed → it ran
        if pred == "verified":
            verdict = _get(hr, "validator_verdict", None) or {}
            if isinstance(verdict, dict):
                v = verdict.get("verified")
                # verified True → met; False → unmet; None (unobserved) → fall
                # back to ok so we don't block when ground-truth is off.
                return bool(v) if v is not None else ok
            return ok
        return None  # unknown predicate → allow
    except Exception as e:
        logger.debug("[contract-gate] eval '%s' failed: %s", cond, e)
        return None


def check_start_when(hop: Any, executed: Dict[str, Any]) -> GateDecision:
    """Pre-execution contract check. Fail-open."""
    if not CONTRACT_ENFORCEMENT_ENABLED:
        return GateDecision(allowed=True, reason="enforcement off")
    conditions = list(getattr(hop, "start_when", None) or [])
    if not conditions:
        return GateDecision(allowed=True, reason="no contract")
    unmet: List[str] = []
    for cond in conditions:
        res = _eval_condition(cond, executed)
        if res is False:
            unmet.append(cond)
        # res None → can't evaluate → allow (fail-open), don't add to unmet
    if unmet:
        return GateDecision(allowed=False,
                            reason=f"contract not satisfied: {', '.join(unmet)}",
                            unmet=unmet)
    return GateDecision(allowed=True, reason="contract satisfied")


def check_capability_permission(capability: str,
                                trust_lookup=None) -> GateDecision:
    """Capability/worker gating. Fail-open: only an EXPLICIT low-trust blocks.

    `trust_lookup` is an optional callable capability→float in [0,1]. When None
    or it can't resolve, we ALLOW (unknown trust is not a denial).
    """
    if not CAPABILITY_GATING_ENABLED:
        return GateDecision(allowed=True, reason="gating off")
    if trust_lookup is None or not capability:
        return GateDecision(allowed=True, reason="no trust source")
    try:
        trust = trust_lookup(capability)
    except Exception:
        return GateDecision(allowed=True, reason="trust lookup error → allow")
    if trust is None:
        return GateDecision(allowed=True, reason="trust unknown → allow")
    if trust < MIN_TRUST:
        return GateDecision(allowed=False,
                            reason=f"trust {trust:.2f} < min {MIN_TRUST:.2f}")
    return GateDecision(allowed=True, reason=f"trust {trust:.2f} ok")
