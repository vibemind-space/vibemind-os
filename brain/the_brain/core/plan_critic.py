"""Phase 10.3 — Plan Critic.

Adversarial self-critique of a Brain-generated multi-hop plan BEFORE
execution. Same LLM as the planner but a hostile prompt and elevated
temperature so it doesn't just rubber-stamp its own work.

Returns a structured risk assessment. The PlanExecutor uses
`recommend` to decide whether to proceed, replan once, or proceed
with a warning flag.

Public API:
  critique(plan, intent, dispatcher, kg=None) -> {
    "risks": [{description, severity}, ...],
    "score": 0..1,                # higher = riskier
    "recommend": "proceed"|"replan"|"warn",
    "raw": str (LLM raw output for debugging),
  }

Defaults are tuned for cheap latency: groq_subagent + max 320 tokens.
The whole pass adds ~600-1500ms to a plan and is bypassable via env.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_CRITIC_SYSTEM = """You are a hostile, skeptical reviewer of execution plans.
Your job is to find what is WRONG with the plan, not to praise it.
You are paranoid, focused on failure modes, and concise.
Output ONLY valid JSON. No prose outside the JSON object.
"""

_CRITIC_PROMPT = """An autonomous AI assistant produced this plan to handle a user intent.
Assume the user is non-technical and will be unhappy if anything fails.

USER INTENT:
{intent}

PLAN RATIONALE:
{rationale}

PLAN HOPS (in execution order):
{hops_block}

Your task: identify SPECIFIC risks that could make this plan fail.
Do not list generic concerns. Each risk must be concrete and tied to a hop or
to the plan's structure.

For each risk, score severity 1-5 (1=minor, 5=plan-breaking).

Output JSON exactly in this shape (no markdown fence, no extra keys):
{{
  "risks": [
    {{"description": "<one specific risk>", "severity": <1-5>, "hop": "<step_id or 'plan'>"}},
    ...
  ],
  "overall_severity": <0.0-1.0>,
  "recommend": "proceed" | "replan" | "warn"
}}

Rules for `recommend`:
  - "replan"  if any risk has severity 5, OR overall_severity > 0.7
  - "warn"    if overall_severity > 0.4 but no severity-5 risks
  - "proceed" otherwise

Be terse. Maximum 4 risks. JSON only."""


def _format_hops(plan: Any) -> str:
    hops = (
        getattr(plan, "hops", None)
        or (plan.get("hops") if isinstance(plan, dict) else [])
        or []
    )
    if not hops:
        return "(none)"
    lines = []
    for h in hops:
        sid = getattr(h, "step_id", None) or (h.get("step_id") if isinstance(h, dict) else "?")
        desc = getattr(h, "description", None) or (h.get("description") if isinstance(h, dict) else "")
        cap = getattr(h, "capability", None) or (h.get("capability") if isinstance(h, dict) else "")
        target = getattr(h, "execution_target", None) or (h.get("execution_target") if isinstance(h, dict) else "")
        lines.append(f"  {sid}: {desc[:120]}  [cap={cap}, target={target}]")
    return "\n".join(lines)


def _parse_json_lenient(text: str) -> Optional[Dict[str, Any]]:
    """Try strict json first, then fenced, then first {...} block."""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # strip ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*(\{[\s\S]+?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # last-resort: greedy first {...}
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def critique(
    plan: Any,
    intent: str,
    dispatcher: Any,
    timeout_s: float = 12.0,
) -> Dict[str, Any]:
    """Run hostile critique. Returns dict with risks/score/recommend/raw.

    On any LLM failure: returns a passthrough verdict (recommend='proceed',
    score=0, risks=[]) so plan execution is never blocked by critic outage.
    """
    bypass = os.environ.get("PLAN_CRITIC_DISABLED", "0") in ("1", "true", "True")
    if bypass or dispatcher is None:
        return {
            "risks": [],
            "score": 0.0,
            "recommend": "proceed",
            "raw": "",
            "skipped": True,
            "reason": "critic disabled or no dispatcher",
        }

    rationale = (
        getattr(plan, "rationale", None)
        or (plan.get("rationale") if isinstance(plan, dict) else "")
        or "(no rationale)"
    )
    hops_block = _format_hops(plan)
    prompt = _CRITIC_PROMPT.format(
        intent=(intent or "")[:500],
        rationale=rationale[:400],
        hops_block=hops_block[:1200],
    )

    tool = os.environ.get("PLAN_CRITIC_TOOL", "groq_subagent")
    model = os.environ.get(
        "PLAN_CRITIC_MODEL",
        "groq::llama-3.3-70b-versatile" if tool == "groq_subagent" else "anthropic/claude-haiku-4.5",
    )
    temperature = float(os.environ.get("PLAN_CRITIC_TEMPERATURE", "1.1"))
    max_tokens = int(os.environ.get("PLAN_CRITIC_MAX_TOKENS", "320"))

    t0 = time.time()
    try:
        result = dispatcher.dispatch(
            tool,
            prompt=prompt,
            system=_CRITIC_SYSTEM,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.warning(f"[critic] dispatch raised: {e}")
        return {
            "risks": [], "score": 0.0, "recommend": "proceed",
            "raw": "", "error": str(e), "skipped": True,
        }
    latency_ms = int((time.time() - t0) * 1000)

    if not result.get("ok"):
        logger.warning(f"[critic] LLM call failed: {result.get('error')}")
        return {
            "risks": [], "score": 0.0, "recommend": "proceed",
            "raw": result.get("text", ""), "error": result.get("error"),
            "skipped": True, "latency_ms": latency_ms,
        }

    raw = result.get("text", "") or ""
    parsed = _parse_json_lenient(raw)
    if not parsed:
        logger.warning(f"[critic] JSON parse failed, raw={raw[:200]!r}")
        return {
            "risks": [], "score": 0.0, "recommend": "proceed",
            "raw": raw, "error": "json parse failed",
            "skipped": True, "latency_ms": latency_ms,
        }

    risks_in = parsed.get("risks") or []
    risks: List[Dict[str, Any]] = []
    max_severity = 0
    for r in risks_in[:8]:
        try:
            sev = int(r.get("severity", 1))
        except Exception:
            sev = 1
        sev = max(1, min(5, sev))
        max_severity = max(max_severity, sev)
        risks.append({
            "description": str(r.get("description", ""))[:300],
            "severity": sev,
            "hop": str(r.get("hop", "plan"))[:40],
        })

    score = float(parsed.get("overall_severity", 0.0) or 0.0)
    score = max(0.0, min(1.0, score))

    rec = str(parsed.get("recommend", "")).strip().lower()
    if rec not in ("proceed", "replan", "warn"):
        # Apply our own rules as fallback
        if max_severity >= 5 or score > 0.7:
            rec = "replan"
        elif score > 0.4:
            rec = "warn"
        else:
            rec = "proceed"

    return {
        "risks": risks,
        "score": score,
        "recommend": rec,
        "raw": raw,
        "latency_ms": latency_ms,
        "model": model,
        "tool": tool,
    }


def format_for_ui(verdict: Dict[str, Any]) -> str:
    """Compact UI-render of a critique verdict."""
    if verdict.get("skipped"):
        return "(critic skipped)"
    rec = verdict.get("recommend", "?")
    score = verdict.get("score", 0.0)
    risks = verdict.get("risks") or []
    icon = {"proceed": "✓", "warn": "⚠", "replan": "✗"}.get(rec, "?")
    lines = [f"{icon} {rec.upper()} (score={score:.2f})"]
    for r in risks[:4]:
        sev = r.get("severity", 1)
        bar = "!" * min(sev, 5)
        lines.append(f"  [{bar}] {r.get('description', '')[:140]}")
    return "\n".join(lines)
