"""Capability Validator — Phase 3.

After a direct-execution capability returns a result, run a separate
validator agent (a `validator_target` declared on the capability in YAML)
that signs off pass/fail with a reason. The validator's verdict is
attached to the discourse record under `validation` so callers can:

  - reject a result that the producer thinks succeeded but the validator
    flags as wrong (e.g. score returned but bubble didn't actually exist),
  - log the validator's reason for telemetry / Phase 5 self-curation,
  - trigger a retry path when YAML opts in via `on_fail: retry`.

Two validator kinds are supported in Phase 3, mirroring Phase 1.5's
direct-executor shape:

  validator: "rule:<rule_name>"          # cheap deterministic check
  validator: "agent:<openfang_agent>"    # LLM-based check via OpenFang

A YAML entry looks like:

  validator:
    kind: rule:non_empty_result
    on_fail: report   # or 'retry' or 'block'

Or:

  validator:
    kind: agent:brain-coder
    prompt_template: |
      A direct-execution tool returned this result for intent {intent}:
      {raw_result}
      Reply VALID or INVALID + one-sentence reason.
    on_fail: report

`on_fail` semantics:
  - report  : record verdict, return result anyway (default)
  - retry   : on first fail, re-call the executor once with the same args
  - block   : return ok=False with the validator reason as the error

The validator never raises — failures bubble up as `validator_error`
fields in the record. The caller's path stays the same.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


# ── Built-in deterministic rules ───────────────────────────────────────

def _rule_non_empty_result(raw: Any, *, intent: str = "", arg: Any = None) -> Dict[str, Any]:
    """Pass if raw_result is non-None and not an obvious empty container."""
    if raw is None:
        return {"valid": False, "reason": "result is None"}
    if isinstance(raw, (list, dict, str)) and len(raw) == 0:
        return {"valid": False, "reason": f"result is an empty {type(raw).__name__}"}
    return {"valid": True, "reason": "non-empty result"}


def _rule_has_score(raw: Any, **_) -> Dict[str, Any]:
    """Pass if raw is a dict with a numeric 'score' or 'total_score' field."""
    if not isinstance(raw, dict):
        return {"valid": False, "reason": "expected dict for score check"}
    for k in ("total_score", "score"):
        v = raw.get(k)
        if isinstance(v, (int, float)):
            return {"valid": True, "reason": f"{k}={v}"}
    return {"valid": False, "reason": "no numeric score/total_score key"}


def _rule_bubble_id_present(raw: Any, **_) -> Dict[str, Any]:
    """Pass if raw indicates a bubble was created or identifies one.
    Accepts dict-with-bubble_id, string with 'bubble_id', or the legacy
    voice-tool string output 'Created new space ...' / 'Bubble X created'."""
    if isinstance(raw, dict) and ("bubble_id" in raw or "id" in raw):
        return {"valid": True, "reason": f"bubble_id={raw.get('bubble_id') or raw.get('id')}"}
    if isinstance(raw, dict):
        # voice-tool returns dict like {success: True, message: 'Created ...'}
        msg = raw.get("message") or raw.get("response_hint") or ""
        if isinstance(msg, str) and re.search(
            r"(created|added|new)\s+(space|bubble|topic)", msg, re.IGNORECASE,
        ):
            return {"valid": True, "reason": f"bubble creation confirmed: {msg[:80]!r}"}
        if raw.get("success") or raw.get("ok"):
            return {"valid": True, "reason": "tool reported success=true"}
    if isinstance(raw, str):
        if re.search(r"bubble[_ -]?id", raw, re.IGNORECASE):
            return {"valid": True, "reason": "bubble id mentioned in string output"}
        if re.search(
            r"(created|added|new)\s+(space|bubble|topic)", raw, re.IGNORECASE,
        ):
            return {"valid": True, "reason": f"bubble creation string: {raw[:80]!r}"}
        if re.search(
            r"(already exists|already created|exists already)", raw, re.IGNORECASE,
        ):
            return {"valid": True, "reason": f"bubble already exists: {raw[:80]!r}"}
    return {"valid": False, "reason": "no bubble_id or creation confirmation in result"}


def _rule_idea_created(raw: Any, **_) -> Dict[str, Any]:
    """Pass if the idea-creation tool returned a positive confirmation.

    Phase 11.W2 — the hardened create_op returns {ok, node_id, ...}. An
    error dict has ok=False, so check that explicitly before the id keys
    (an error dict has no id key, but be defensive). For a brand-new
    write the strict `rule:canvas_node_persisted` is preferred; this rule
    stays the lenient default for the legacy idea_add capability.
    """
    if isinstance(raw, dict):
        if raw.get("ok") is False:
            return {
                "valid": False,
                "reason": raw.get("error") or "create reported ok=False",
            }
        ok = raw.get("ok") or raw.get("success") or raw.get("created")
        if ok or raw.get("idea_id") or raw.get("id") or raw.get("node_id"):
            return {"valid": True, "reason": "idea creation confirmed"}
    if isinstance(raw, str) and re.search(r"(created|added|saved|got it)", raw, re.IGNORECASE):
        return {"valid": True, "reason": "string confirms idea creation"}
    return {"valid": False, "reason": "no idea-creation confirmation"}


def _rule_canvas_node_persisted(raw: Any, **_) -> Dict[str, Any]:
    """Phase 11.W2 (A.2) — HARD verification that a canvas_node write
    actually persisted to the DB.

    Unlike `idea_created`, this does NOT accept a bare string with the
    word "created" — the old rule passed on a freely-worded success
    string AND failed to catch create_op's early-return error strings,
    so Brain reported "ok" while nothing was written. This rule only
    passes for the structured dict that the hardened create_op returns
    AFTER its read-back verify: it requires `ok is True` AND a real
    `node_id`. Anything else (error dict, string, None) is a hard fail —
    pair it with `on_fail: block` so the plan reports the truth.
    """
    if not isinstance(raw, dict):
        return {
            "valid": False,
            "reason": f"expected a dict from create_op, got {type(raw).__name__}",
        }
    if raw.get("ok") is not True:
        return {
            "valid": False,
            "reason": (
                f"create_op reported ok={raw.get('ok')!r}: "
                f"{raw.get('error') or raw.get('message') or 'no detail'}"
            ),
        }
    node_id = raw.get("node_id")
    if not node_id or not isinstance(node_id, str):
        return {
            "valid": False,
            "reason": "create_op ok=True but no node_id — write not verified",
        }
    return {"valid": True, "reason": f"canvas node {node_id} verified in DB"}


def _rule_score_in_range(raw: Any, **_) -> Dict[str, Any]:
    """Pass if total_score is in [0, 100]."""
    if not isinstance(raw, dict):
        return {"valid": False, "reason": "expected dict for range check"}
    s = raw.get("total_score") or raw.get("score")
    if not isinstance(s, (int, float)):
        return {"valid": False, "reason": "no numeric score"}
    if 0 <= s <= 100:
        return {"valid": True, "reason": f"score {s} in [0,100]"}
    return {"valid": False, "reason": f"score {s} out of range"}


def _rule_flowzen_result(raw: Any, **_) -> Dict[str, Any]:
    """Validate the operation-specific Flowzen result envelope."""
    if not isinstance(raw, dict) or raw.get("ok") is not True:
        return {"valid": False, "reason": "Flowzen operation did not report ok=true"}
    event_id = raw.get("event_id")
    if event_id == "rose.recommend":
        recommendation = raw.get("recommendation")
        valid = isinstance(recommendation, dict) and bool(
            recommendation.get("recommendation_id") and recommendation.get("category")
        ) and raw.get("mutated") is False
    elif event_id == "rose.accept":
        valid = raw.get("status") == "accepted" and raw.get("verified") is True and bool(raw.get("activity_id"))
    elif event_id == "rose.status":
        valid = isinstance(raw.get("status"), dict) and raw.get("mutated") is False
    else:
        valid = False
    return {"valid": valid, "reason": f"Flowzen {event_id or 'unknown'} contract {'valid' if valid else 'invalid'}"}
def _rule_mirofish_evidence(raw: Any, **_) -> Dict[str, Any]:
    """Require real transport evidence and the operation's durable identity."""
    if not isinstance(raw, dict):
        return {"valid": False, "reason": "expected MiroFish result envelope"}
    operation = raw.get("operation")
    evidence = raw.get("evidence")
    if not isinstance(evidence, dict):
        return {"valid": False, "reason": "missing MiroFish transport evidence"}
    if evidence.get("service") != "mirofish" or evidence.get("response_success") is not True:
        return {"valid": False, "reason": "MiroFish backend did not confirm success"}
    if not evidence.get("endpoint") or not raw.get("state"):
        return {"valid": False, "reason": "missing MiroFish endpoint/state evidence"}
    if operation in {"graph.build", "simulate", "predict", "evaluate", "status"}:
        if not raw.get("job_id"):
            return {"valid": False, "reason": f"{operation} has no durable job identity"}
    if operation == "graph.build" and not raw.get("project_id"):
        return {"valid": False, "reason": "graph build has no project identity"}
    if operation == "graph.search" and not raw.get("graph_id"):
        return {"valid": False, "reason": "graph search has no graph identity"}
    if operation == "interview" and not raw.get("simulation_id"):
        return {"valid": False, "reason": "interview has no simulation identity"}
    if operation in {"simulate", "predict", "evaluate"} and not raw.get("model_id"):
        return {"valid": False, "reason": f"{operation} has no model identity"}
    return {"valid": True, "reason": "MiroFish identity and transport evidence verified"}
def _rule_minibook_verified_result(raw: Any, **_) -> Dict[str, Any]:
    """Accept only a response observed from the real Minibook target."""
    if not isinstance(raw, dict):
        return {"valid": False, "reason": "expected Minibook result envelope"}
    truth = raw.get("truth")
    verified = (
        raw.get("ok") is True
        and isinstance(truth, dict)
        and truth.get("status") == "verified"
        and truth.get("source") == "minibook"
    )
    return {
        "valid": verified,
        "reason": "Minibook target verified the result" if verified else "result is not verified by Minibook",
    }


# Registry — extend by adding to this dict, then reference from YAML as
#   validator: { kind: "rule:<name>" }
RULES: Dict[str, Callable[..., Dict[str, Any]]] = {
    "non_empty_result": _rule_non_empty_result,
    # Phase 11.N — alias used by Phase 11.A-N idea/bubble cap entries that
    # were authored with `string_nonempty` instead of `non_empty_result`.
    # Same semantics, just legacy naming. Both work.
    "string_nonempty": _rule_non_empty_result,
    "has_score": _rule_has_score,
    "score_in_range": _rule_score_in_range,
    "bubble_id_present": _rule_bubble_id_present,
    "idea_created": _rule_idea_created,
    # Phase 11.W2 — hard, read-back-verified canvas-node write check.
    "canvas_node_persisted": _rule_canvas_node_persisted,
    "flowzen_result": _rule_flowzen_result,
    "mirofish_evidence": _rule_mirofish_evidence,
    "minibook_verified_result": _rule_minibook_verified_result,
}


class CapabilityValidator:
    """Holds shared state across validator runs (agent endpoint, telemetry).

    Stateless validators (rules) don't strictly need an instance, but having
    one makes wiring + stats consistent with DirectExecutor / capability_router.
    """

    def __init__(self, openfang_url: Optional[str] = None) -> None:
        self.openfang_url = (
            openfang_url or os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200")
        ).rstrip("/")
        self.stats: Dict[str, Any] = {
            "validations": 0,
            "valid": 0,
            "invalid": 0,
            "errors": 0,
            "retries_triggered": 0,
            "blocks_triggered": 0,
            "by_kind": {},
            "last_invalid_reason": None,
            "last_ts": None,
        }

    # ── Public API ──────────────────────────────────────────────────────

    def validate(
        self,
        validator_cfg: Dict[str, Any],
        *,
        intent: str,
        arg: Any,
        raw_result: Any,
    ) -> Dict[str, Any]:
        """Run the configured validator. Returns a dict shape:

            {
              "valid": bool,
              "reason": str,
              "kind": str,
              "elapsed_s": float,
              "on_fail": "report" | "retry" | "block",
              "error": str | None,    # only on internal errors
            }
        """
        t0 = time.time()
        self.stats["validations"] += 1
        self.stats["last_ts"] = t0
        kind = (validator_cfg or {}).get("kind") or ""
        on_fail = (validator_cfg or {}).get("on_fail") or "report"
        bk = self.stats["by_kind"]
        bk[kind] = bk.get(kind, 0) + 1

        try:
            if not kind:
                return self._envelope(
                    valid=True, reason="no validator configured",
                    kind="none", on_fail=on_fail, t0=t0,
                )
            if kind.startswith("rule:"):
                rule_name = kind.split(":", 1)[1]
                fn = RULES.get(rule_name)
                if fn is None:
                    self.stats["errors"] += 1
                    return self._envelope(
                        valid=False, reason=f"unknown rule '{rule_name}'",
                        kind=kind, on_fail=on_fail, t0=t0,
                        error=f"rule not registered: {rule_name}",
                    )
                verdict = fn(raw_result, intent=intent, arg=arg)
                return self._envelope(
                    valid=bool(verdict.get("valid")),
                    reason=str(verdict.get("reason") or ""),
                    kind=kind, on_fail=on_fail, t0=t0,
                    verified=(bool(verdict.get("valid")) if rule_name == "minibook_verified_result" else None),
                )
            if kind.startswith("agent:"):
                agent_name = kind.split(":", 1)[1]
                template = (validator_cfg or {}).get("prompt_template") or DEFAULT_AGENT_PROMPT
                return self._run_agent_validator(
                    agent_name=agent_name,
                    template=template,
                    intent=intent,
                    arg=arg,
                    raw_result=raw_result,
                    on_fail=on_fail,
                    t0=t0,
                )
            if kind.startswith("truth:"):
                # Ground-truth check (Baustein D.1): observe the real world via a
                # declared post-condition, NOT the claimed result. The check spec
                # lives on the validator cfg (or `kind` carries the check name).
                # UNVERIFIED never blocks — only an explicit REFUTED fails.
                return self._run_truth_validator(
                    kind=kind, validator_cfg=validator_cfg or {},
                    on_fail=on_fail, t0=t0,
                    arg=arg, raw_result=raw_result,
                )
            self.stats["errors"] += 1
            return self._envelope(
                valid=False, reason=f"unsupported validator kind '{kind}'",
                kind=kind, on_fail=on_fail, t0=t0,
                error=f"unsupported kind: {kind}",
            )
        except Exception as e:
            self.stats["errors"] += 1
            logger.warning(f"[validator] {kind} failed: {type(e).__name__}: {e}")
            return self._envelope(
                valid=False, reason=f"{type(e).__name__}: {e}",
                kind=kind, on_fail=on_fail, t0=t0,
                error=f"{type(e).__name__}: {e}",
            )

    # ── Internals ───────────────────────────────────────────────────────

    def _envelope(
        self,
        *,
        valid: bool,
        reason: str,
        kind: str,
        on_fail: str,
        t0: float,
        error: Optional[str] = None,
        verified: Optional[bool] = None,
        verify_signal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if valid:
            self.stats["valid"] += 1
        else:
            self.stats["invalid"] += 1
            self.stats["last_invalid_reason"] = reason
        env = {
            "valid": valid,
            "reason": reason,
            "kind": kind,
            "on_fail": on_fail,
            "elapsed_s": round(time.time() - t0, 3),
            "error": error,
        }
        # Ground-truth fields (Baustein D.1): `verified` is the world-observed
        # truth (True/False/None=unobserved), distinct from claim-based `valid`.
        if verified is not None or verify_signal is not None:
            env["verified"] = verified
            env["verify_signal"] = verify_signal or {}
        return env

    @staticmethod
    def _template_postcondition(pc: Dict[str, Any], arg: Any, raw_result: Any) -> Dict[str, Any]:
        """Fill {arg} / {result} / {result_id} placeholders in a post-condition from
        the op's arg + result, so a truth: check can re-query the SPECIFIC row the op
        just touched. {result_id} extracts the first id-like token from the result
        (supabase return=representation gives it). Returns a new dict."""
        import re
        rs = str(raw_result) if raw_result is not None else ""
        m = re.search(r"id['\"]?\s*[=:]\s*['\"]?([\w-]{6,})", rs)
        # {result_title}: the FIRST quoted name in the result — ops name the row they
        # actually touched ("Bubble 'X' deleted."), so an absent/present re-query on it
        # is grounded in the op's own target, not a guessed filter.
        # all quoted names, in order — {result_title} (first) + {result_title2}
        # (second) feed two-endpoint checks like edges ("'X' and 'Y' connected").
        quoted = re.findall(r"['\"]([^'\"]{1,80})['\"]", rs)
        # {result_format}: the format an idea_format_* op reports applying
        # ("... formatted as kanban.") — lets a truth: check confirm the stored
        # format_schema->>type actually matches, uniformly for all formatters.
        mf = re.search(r"formatted as (\w+)", rs)
        # {result_path}: first absolute file path in the result (Windows drive or
        # /-rooted, with an extension) — lets a file_exists check confirm a coding
        # agent's "written to `C:/.../x.py`" actually produced the file.
        mp = re.search(r"([A-Za-z]:[\\/][^\s`'\"<>]+\.\w{1,6}|/[\w./\-]+\.\w{1,6})", rs)
        subs = {"arg": str(arg or "").strip(), "result": rs[:200],
                "result_id": m.group(1) if m else "",
                "result_title": quoted[0] if quoted else "",
                "result_title2": quoted[1] if len(quoted) > 1 else "",
                "result_format": mf.group(1) if mf else "",
                "result_path": mp.group(1) if mp else ""}
        out = {}
        for k, val in (pc or {}).items():
            if isinstance(val, str):
                for sk, sv in subs.items():
                    # only fill when the value resolved to something — an empty
                    # fill leaves "{placeholder}" so the caller's guard → UNVERIFIED
                    # (never a malformed re-query like "id=eq." → false REFUTED)
                    if sv:
                        val = val.replace("{" + sk + "}", sv)
            out[k] = val
        return out

    def _run_truth_validator(
        self,
        *,
        kind: str,
        validator_cfg: Dict[str, Any],
        on_fail: str,
        t0: float,
        arg: Any = None,
        raw_result: Any = None,
    ) -> Dict[str, Any]:
        """Ground-truth validator (Baustein D.1) — observe the real world.

        The post-condition spec is taken from `validator_cfg["postcondition"]`,
        or built from `kind` ("truth:<check>") + the remaining cfg keys.
        UNVERIFIED is treated as valid=True (we couldn't observe → don't block),
        REFUTED is valid=False, VERIFIED is valid=True.
        """
        try:
            from core import world_observer as wo
        except Exception as e:
            return self._envelope(
                valid=True, reason=f"world_observer unavailable: {e}",
                kind=kind, on_fail=on_fail, t0=t0, verified=None,
            )
        # Resolve the post-condition spec.
        pc = validator_cfg.get("postcondition")
        if not pc:
            check = kind.split(":", 1)[1] if ":" in kind else ""
            pc = {k: v for k, v in validator_cfg.items()
                  if k not in ("kind", "on_fail", "prompt_template", "postcondition")}
            if check:
                pc["check"] = check
        # Fill {arg}/{result}/{result_id} from the op so the check re-queries the
        # exact row touched. If a placeholder can't resolve (left as "{...}"), we
        # cannot observe honestly → UNVERIFIED (never a false REFUTED).
        pc = self._template_postcondition(pc, arg, raw_result)
        if any(isinstance(val, str) and "{" in val for val in pc.values()):
            return self._envelope(
                valid=True, reason="ground-truth UNVERIFIED: postcondition placeholder unresolved",
                kind=kind, on_fail=on_fail, t0=t0, verified=None,
            )
        v = wo.observe(pc)
        verified = v.verified_ok  # True | False | None
        # Mutating capabilities may opt into fail-closed truth. Reads and
        # legacy capabilities retain the historical UNVERIFIED-as-reporting
        # behavior unless ``require_verified`` is explicitly set.
        require_verified = validator_cfg.get("require_verified") is True
        valid = (verified is True) if require_verified else (verified is not False)
        return self._envelope(
            valid=valid, reason=f"ground-truth {v.verdict}: {v.reason}",
            kind=kind, on_fail=on_fail, t0=t0,
            verified=verified, verify_signal=v.signal,
        )

    def _run_agent_validator(
        self,
        *,
        agent_name: str,
        template: str,
        intent: str,
        arg: Any,
        raw_result: Any,
        on_fail: str,
        t0: float,
    ) -> Dict[str, Any]:
        """LLM-based validator via OpenFang `/api/agents/<name>/message`."""
        try:
            agent_id = self._resolve_agent_id(agent_name)
        except Exception as e:
            return self._envelope(
                valid=False, reason=f"agent lookup failed: {e}",
                kind=f"agent:{agent_name}", on_fail=on_fail, t0=t0,
                error=f"{type(e).__name__}: {e}",
            )

        if not agent_id:
            return self._envelope(
                valid=False, reason=f"agent '{agent_name}' not found in OpenFang",
                kind=f"agent:{agent_name}", on_fail=on_fail, t0=t0,
                error="agent not registered",
            )

        # Render prompt — keep it small and focused so phi3-tier models can
        # answer in a parseable form.
        try:
            prompt = template.format(
                intent=intent,
                arg=arg or "",
                raw_result=_truncate(repr(raw_result), 1500),
            )
        except Exception as e:
            return self._envelope(
                valid=False, reason=f"prompt template error: {e}",
                kind=f"agent:{agent_name}", on_fail=on_fail, t0=t0,
                error=f"{type(e).__name__}: {e}",
            )

        try:
            resp = requests.post(
                f"{self.openfang_url}/api/agents/{agent_id}/message",
                json={"message": prompt},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        except Exception as e:
            return self._envelope(
                valid=False, reason=f"openfang call failed: {e}",
                kind=f"agent:{agent_name}", on_fail=on_fail, t0=t0,
                error=f"{type(e).__name__}: {e}",
            )

        content = (
            data.get("content")
            or data.get("response")
            or data.get("message")
            or ""
        ).strip()
        verdict = self._parse_agent_verdict(content)
        return self._envelope(
            valid=verdict["valid"],
            reason=verdict["reason"],
            kind=f"agent:{agent_name}",
            on_fail=on_fail,
            t0=t0,
        )

    def _resolve_agent_id(self, agent_name: str) -> Optional[str]:
        """Look up an OpenFang agent id by name. Cached per-instance."""
        cache = getattr(self, "_agent_cache", None)
        if cache is None:
            cache = {}
            self._agent_cache = cache
        if agent_name in cache:
            return cache[agent_name]
        try:
            resp = requests.get(f"{self.openfang_url}/api/agents", timeout=10)
            resp.raise_for_status()
            agents = resp.json() if resp.ok else []
            if isinstance(agents, dict):
                agents = agents.get("agents") or []
            for a in agents or []:
                aname = (a.get("name") or "").lower()
                if aname == agent_name.lower():
                    cache[agent_name] = a.get("id") or a.get("agent_id")
                    return cache[agent_name]
        except Exception as e:
            logger.debug(f"[validator] agent lookup failed: {e}")
        cache[agent_name] = None
        return None

    @staticmethod
    def _parse_agent_verdict(content: str) -> Dict[str, Any]:
        """Heuristic: look for VALID / INVALID / PASS / FAIL token at start.
        Falls back to 'sentiment' on the first line."""
        if not content:
            return {"valid": False, "reason": "empty agent response"}
        head = content.strip().splitlines()[0][:200] if content.strip() else ""
        upper = head.upper()
        if upper.startswith("VALID") or upper.startswith("PASS"):
            tail = head.split(":", 1)[1].strip() if ":" in head else "validator approved"
            return {"valid": True, "reason": tail or "validator approved"}
        if upper.startswith("INVALID") or upper.startswith("FAIL"):
            tail = head.split(":", 1)[1].strip() if ":" in head else "validator rejected"
            return {"valid": False, "reason": tail or "validator rejected"}
        # Loose fallback — accept if it sounds positive
        if re.search(r"\b(looks good|correct|seems fine|ok|ja\b)\b", content, re.IGNORECASE):
            return {"valid": True, "reason": head[:160]}
        return {"valid": False, "reason": head[:160] or "ambiguous response"}

    def stats_dict(self) -> Dict[str, Any]:
        return dict(self.stats)


DEFAULT_AGENT_PROMPT = (
    "A direct-execution tool ran in response to intent: {intent}\n"
    "Argument: {arg}\n"
    "Tool result (truncated):\n{raw_result}\n\n"
    "Is this result correct, sensible, and aligned with the user's intent? "
    "Reply with the single word VALID or INVALID, then a colon, then a "
    "one-sentence reason. Example:\n"
    "VALID: result contains a numeric score and a list of missing items.\n"
    "INVALID: result is empty or unrelated to the requested bubble."
)


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."
