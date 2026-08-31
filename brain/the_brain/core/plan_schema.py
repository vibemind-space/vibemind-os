"""Plan Schema — Phase 6.

Dataclasses + validator for the multi-hop plan executor. Kept independent
of any LLM/dispatcher so unit tests can exercise the schema without a
running stack.

A Plan describes a DAG of hops:

  Plan
    plan_id, intent, rationale, final_synthesis_prompt
    hops: [HopSpec, ...]
      step_id, description
      capability  (optional — name from capabilities.yaml)
      execution_target (optional — Phase 4 string, overrides capability target)
      arg_kwarg, arg_template (with `{{state.X}}` substitution)
      depends_on: [step_id, ...]
      output_var (key under which the result lands in pipeline_state)
      on_fail: 'abort' | 'continue' | 'replan'
      validator: optional dict (same shape as YAML validator block)

`validate_plan(plan)` returns a list of error strings — empty list means
the plan is structurally sound (acyclic, references resolve, template
placeholders match available output_vars). The DAG check uses Kahn's
algorithm; cycle = remaining edges after topological pass.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set


# Public on_fail enum values
ON_FAIL_ABORT = "abort"
ON_FAIL_CONTINUE = "continue"
ON_FAIL_REPLAN = "replan"
_ON_FAIL_VALID = {ON_FAIL_ABORT, ON_FAIL_CONTINUE, ON_FAIL_REPLAN}


_TEMPLATE_REF_RE = re.compile(r"\{\{\s*state\.([a-zA-Z_][\w.]*)\s*\}\}")
# Phase 6.15.1 — also recognise {{item}} / {{loop.index}} / {{loop.index0}}
# which are valid inside a hop with `repeat:` set; validator must NOT flag them.
_REPEAT_REF_RE = re.compile(r"\{\{\s*(item|loop\.index0?|loop\.value)\s*\}\}")


@dataclass
class HopSpec:
    step_id: str
    description: str
    capability: Optional[str] = None
    execution_target: Optional[str] = None
    arg_kwarg: Optional[str] = None
    arg_template: str = ""
    depends_on: List[str] = field(default_factory=list)
    output_var: str = ""
    on_fail: str = ON_FAIL_ABORT
    validator: Optional[Dict[str, Any]] = None
    timeout_s: float = 60.0
    retries: int = 1
    # Baustein B — workflow contract: conditions that MUST hold before this hop
    # may run (pre-execution enforcement, not just depends_on advice). Each is a
    # string like "s1.completed" | "s1.verified" | "s1.ok". Checked against the
    # executed-state before run; if unmet, the hop is blocked. Only enforced when
    # CONTRACT_ENFORCEMENT_ENABLED (default OFF, fail-open).
    start_when: List[str] = field(default_factory=list)
    # Phase 6.15.1 — Iteration support. When set, executor expands this
    # hop into N sub-hops at runtime, one per item.
    #
    # Two shapes accepted:
    #   repeat: {items: ["a", "b", "c"]}                 — explicit list
    #   repeat: {items_from: "state.idea_titles"}         — pull from prior output_var
    #
    # The arg_template can reference {{item}} (the current item) and
    # {{loop.index}} (1-based) / {{loop.index0}} (0-based).
    repeat: Optional[Dict[str, Any]] = None

    def template_refs(self) -> List[str]:
        """Return list of `state.X` paths referenced by this hop's arg_template.

        Phase 11.U.E — coerce non-string arg_template (GPT-4o sometimes emits
        a dict like `{"idea1": "...", "idea2": "..."}` instead of a literal
        string). We stringify so findall works; if there are no template-refs
        in the rendered form, findall returns [] anyway.
        """
        if not self.arg_template:
            return []
        if not isinstance(self.arg_template, str):
            try:
                import json as _json
                arg_str = _json.dumps(self.arg_template, ensure_ascii=False)
            except Exception:
                arg_str = str(self.arg_template)
            return _TEMPLATE_REF_RE.findall(arg_str)
        return _TEMPLATE_REF_RE.findall(self.arg_template)


@dataclass
class Plan:
    plan_id: str
    intent: str
    rationale: str
    hops: List[HopSpec]
    final_synthesis_prompt: str = ""
    estimated_cost_usd: float = 0.0
    # E2E-Trace (2026-06-09): durchgaengige Correlation-ID, am multihop_execute-
    # Entry gesetzt (auch fuer SoM/som-team/no-plan-Zweige, die kein plan_id haben).
    trace_id: str = ""
    # Laufzeit-Stage-Events (PLAN/EXECUTION/...): {stage, component, ts, outcome}.
    # Nicht in to_dict serialisiert (der PlanRecorder-Snapshot zieht es separat).
    _stages: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def make_id(cls) -> str:
        return f"plan_{uuid.uuid4().hex[:10]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent": self.intent,
            "rationale": self.rationale,
            "hops": [asdict(h) for h in self.hops],
            "final_synthesis_prompt": self.final_synthesis_prompt,
            "estimated_cost_usd": self.estimated_cost_usd,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Plan":
        # Phase 11.U.E — robust handling of LLM-emitted arg_template.
        # GPT-4o sometimes emits a dict (multi-arg cases like idea_connect):
        #   "arg_template": {"idea1": "Payment_Layer", "idea2": "Stripe"}
        # Strategy:
        #   - if dict + we have multiple keys: JSON-stringify (so it lands
        #     as a JSON-blob param value the tool can re-parse). Also drop
        #     arg_kwarg so the base executor passes it as a dict payload
        #     rather than wrapping it again.
        #   - if dict with 1 key: pull the value out as the primary arg
        #     (matches the single-arg shape the planner usually emits).
        import json as _json
        cleaned_hops = []
        for h in (d.get("hops") or []):
            if isinstance(h, dict):
                at = h.get("arg_template")
                if at is not None and not isinstance(at, str):
                    if isinstance(at, dict) and len(at) == 1:
                        # collapse single-key dict to its value
                        h = {**h, "arg_template": str(list(at.values())[0])}
                    elif isinstance(at, dict):
                        # multi-key: JSON-encode + null arg_kwarg so the
                        # base executor uses the dict as the full payload
                        try:
                            h = {
                                **h,
                                "arg_template": _json.dumps(at, ensure_ascii=False),
                                "arg_kwarg": None,
                            }
                        except Exception:
                            h = {**h, "arg_template": str(at)}
                    else:
                        h = {**h, "arg_template": str(at)}
            cleaned_hops.append(h)
        hops = [HopSpec(**h) for h in cleaned_hops]
        return cls(
            plan_id=d.get("plan_id") or cls.make_id(),
            intent=d.get("intent") or "",
            rationale=d.get("rationale") or "",
            hops=hops,
            final_synthesis_prompt=d.get("final_synthesis_prompt") or "",
            estimated_cost_usd=float(d.get("estimated_cost_usd") or 0.0),
            trace_id=d.get("trace_id") or "",
        )


@dataclass
class HopResult:
    step_id: str
    ok: bool
    result: Any = None
    error: Optional[str] = None
    elapsed_s: float = 0.0
    validator_verdict: Optional[Dict[str, Any]] = None
    capability: Optional[str] = None
    target: Optional[str] = None
    rendered_arg: Any = None
    kg_hits: List[Dict[str, Any]] = field(default_factory=list)
    discourse_replies: List[Dict[str, Any]] = field(default_factory=list)
    # Phase 9.0 — captured MCP tool-calls from streaming OpenFang responses.
    # Each entry: {seq, tool, input, result, ts_start, ts_end, elapsed_ms,
    #              approval_status, mcp_server, kind}
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    retried: int = 0
    # Phase 6.13 — TriBE-grounded bridge levels (dict of 8 floats, keys:
    # cortex, limbic, defense, motor, visceral, social, integration, memory).
    # None when TriBE hook is disabled or fails.
    bridges: Optional[Dict[str, float]] = None
    # Phase 1 — gate-derived learning signal (outcome-gate semantics, mirrors
    # voice/python/swarm/routing/outcome_gate.py without importing across the
    # voice/brain boundary). None means UNVERIFIED, never a success.
    contract_pass: Optional[bool] = None
    reward: float = 0.0  # mirrors contract_pass: True->1.0, False->-1.0, None->0.0


def contract_pass_from(ok: bool, verdict: Optional[Dict[str, Any]]) -> Optional[bool]:
    """Phase 1 — derive the outcome-gate verdict for a hop from its raw `ok`
    flag and the (optional) `truth:` validator verdict dict.

    - `ok` falsy -> False (the hop itself failed; no need for a validator).
    - `ok` truthy but no validator ran (verdict is None/not a dict/no usable
      `verified` key) -> None. UNVERIFIED must NEVER become True — "did not
      crash" is not proof of success.
    - `ok` truthy and validator ran -> mirrors `verdict['verified']` exactly
      (True -> True, False -> False, anything else incl. missing -> None).
    """
    if not ok:
        return False
    if not isinstance(verdict, dict):
        return None
    verified = verdict.get("verified")
    if verified is True:
        return True
    if verified is False:
        return False
    return None


# ── Validator ─────────────────────────────────────────────────────────


def validate_plan(
    plan: Plan,
    *,
    known_capabilities: Optional[Set[str]] = None,
    known_target_kinds: Optional[Set[str]] = None,
    max_hops: int = 5,
) -> List[str]:
    """Returns a list of human-readable validation errors. Empty list = ok.

    Checks:
      - plan_id, intent non-empty
      - hop count in [1, max_hops]
      - step_ids unique + non-empty
      - on_fail values valid
      - depends_on references existing step_ids
      - DAG is acyclic (Kahn's)
      - template refs `{{state.X}}` resolve to an earlier hop's output_var
      - if known_capabilities given: capability names exist
      - if known_target_kinds given: execution_target prefix is supported
    """
    errors: List[str] = []

    if not plan.plan_id:
        errors.append("plan_id is empty")
    if not plan.intent:
        errors.append("intent is empty")
    if not plan.hops:
        errors.append("plan has zero hops")
        return errors
    if len(plan.hops) > max_hops:
        errors.append(f"plan has {len(plan.hops)} hops (max {max_hops})")

    # Step-id uniqueness + on_fail values + capability/target validity
    seen_ids: Set[str] = set()
    output_vars: Dict[str, str] = {}  # output_var -> producing step_id
    for h in plan.hops:
        if not h.step_id:
            errors.append("hop has empty step_id")
            continue
        if h.step_id in seen_ids:
            errors.append(f"duplicate step_id: {h.step_id}")
        seen_ids.add(h.step_id)

        if h.on_fail not in _ON_FAIL_VALID:
            errors.append(
                f"hop '{h.step_id}': invalid on_fail={h.on_fail!r} "
                f"(must be one of {sorted(_ON_FAIL_VALID)})"
            )

        # Need either capability or execution_target
        if not h.capability and not h.execution_target:
            errors.append(
                f"hop '{h.step_id}': must specify capability or execution_target"
            )

        if h.capability and known_capabilities is not None:
            if h.capability not in known_capabilities:
                errors.append(
                    f"hop '{h.step_id}': unknown capability {h.capability!r}"
                )

        if h.execution_target and known_target_kinds is not None:
            if ":" not in h.execution_target:
                errors.append(
                    f"hop '{h.step_id}': execution_target {h.execution_target!r} "
                    f"missing kind prefix"
                )
            else:
                kind = h.execution_target.split(":", 1)[0].lower()
                if kind not in known_target_kinds:
                    errors.append(
                        f"hop '{h.step_id}': unsupported target kind {kind!r}"
                    )

        if h.output_var:
            if h.output_var in output_vars:
                errors.append(
                    f"hop '{h.step_id}': output_var {h.output_var!r} already "
                    f"produced by '{output_vars[h.output_var]}'"
                )
            output_vars[h.output_var] = h.step_id

    # depends_on references
    for h in plan.hops:
        for dep in h.depends_on:
            if dep not in seen_ids:
                errors.append(
                    f"hop '{h.step_id}': depends_on unknown step '{dep}'"
                )
            if dep == h.step_id:
                errors.append(f"hop '{h.step_id}': self-dependency")

    # Cycle detection (Kahn's). Skip if depends_on already has bad refs.
    if not any("depends_on unknown step" in e for e in errors):
        in_degree: Dict[str, int] = {h.step_id: len(h.depends_on) for h in plan.hops}
        children: Dict[str, List[str]] = {h.step_id: [] for h in plan.hops}
        for h in plan.hops:
            for dep in h.depends_on:
                children[dep].append(h.step_id)
        ready = [sid for sid, d in in_degree.items() if d == 0]
        topo: List[str] = []
        while ready:
            n = ready.pop(0)
            topo.append(n)
            for c in children[n]:
                in_degree[c] -= 1
                if in_degree[c] == 0:
                    ready.append(c)
        if len(topo) < len(plan.hops):
            unresolved = [sid for sid, d in in_degree.items() if d > 0]
            errors.append(
                f"DAG has a cycle (unresolved steps: {sorted(unresolved)})"
            )

    # Template-ref resolution. Walk transitive dependencies — a hop's
    # template can reference any output_var produced by any ancestor in
    # the DAG, not just direct depends_on.
    available_vars: Dict[str, str] = dict(output_vars)
    parents: Dict[str, List[str]] = {h.step_id: list(h.depends_on) for h in plan.hops}

    def _ancestors(sid: str) -> Set[str]:
        seen: Set[str] = set()
        stack = list(parents.get(sid, []))
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(parents.get(n, []))
        return seen

    for h in plan.hops:
        for ref in h.template_refs():
            base = ref.split(".", 1)[0]
            if base not in available_vars:
                errors.append(
                    f"hop '{h.step_id}': template references "
                    f"{{{{state.{ref}}}}} but no hop produces output_var "
                    f"{base!r}"
                )
            elif available_vars[base] == h.step_id:
                errors.append(
                    f"hop '{h.step_id}': template references its own output_var"
                )
            elif available_vars[base] not in _ancestors(h.step_id):
                producer = available_vars[base]
                errors.append(
                    f"hop '{h.step_id}': template references {{{{state.{base}}}}} "
                    f"produced by '{producer}' but '{producer}' is not an "
                    f"ancestor (add it to depends_on chain)"
                )

    return errors
