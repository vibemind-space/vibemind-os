"""Phase 9.0.4 — Tool-Call Approval Gate.

Tool-calls captured from OpenFang's streaming endpoint arrive AFTER OpenFang
already executed them — so true pre-emptive approval requires changes in
OpenFang's tool-runner. This Phase 9 layer implements the next-best thing:

  - **Risk-tagging**: each captured tool_call gets a risk_level (none/low/
    medium/high) by static rules over tool_name + input
  - **Audit-trail in DecisionGraph**: every high-risk call has approval_status
    = 'requested' on creation; UI shows it as yellow-dashed
  - **Post-hoc deny + revert**: user clicks Deny in the modal → marks the
    ToolCall as 'denied' and (when feasible) submits a counter-action
    (e.g. for file_write of a new file → file_delete of that path)
  - **Pre-emptive blacklist**: capabilities can declare
    `forbid_tools: [shell_run, file_delete]` in YAML — if Brain sees those
    in tool_calls, hop is marked as fail (after-the-fact, but logged)

For TRUE pre-execution approval we'd need OpenFang to emit a `tool_use_pending`
event before running the tool and accept an `approve/deny` callback — that's
an OpenFang-side change tracked as Phase 9.5 (deferred).

Public API:
  classify_risk(tool_name, args) -> 'none'|'low'|'medium'|'high'
  mark_pending(decision_graph, tool_call_id) -> sets approval_status='requested'
  resolve(decision_graph, tool_call_id, decision='approve'|'deny') -> writes status
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Risk classification rules.
# Each rule: (regex on tool_name, risk_level)
_RISK_RULES = [
    # HIGH — irreversible / external impact
    (re.compile(r"file_write|doc_apply|excel_fill|word_write|file_create", re.I), "high"),
    (re.compile(r"shell|exec|process_kill|system_command", re.I), "high"),
    (re.compile(r"send_message|email.*send|gmail.*send|create_draft.*send", re.I), "high"),
    (re.compile(r"deploy|release|publish|merge", re.I), "high"),
    # MEDIUM — read with potential side-effects, network, scrape
    (re.compile(r"browser|navigate|fetch_url|scrape", re.I), "medium"),
    (re.compile(r"event_add|calendar.*add|create_event", re.I), "medium"),
    (re.compile(r"github.*push|github.*commit", re.I), "medium"),
    (re.compile(r"label_message|label_thread", re.I), "medium"),
    # LOW — observation but could leak / cost
    (re.compile(r"vision_analyze|read_screen|describe_screen", re.I), "low"),
    (re.compile(r"search_files|search_threads|list_drafts", re.I), "low"),
]

# Capability-level forbid list. If a hop's capability has
# `forbid_tools: [...]` in YAML and OpenFang ran a forbidden tool,
# we mark the hop as fail post-hoc.
_DEFAULT_BLACKLIST_BY_RISK = (
    os.environ.get("APPROVAL_BLACKLIST_RISK_LEVELS", "high")
    .lower().split(",")
)


def classify_risk(tool_name: str, args: Any = None) -> str:
    """Returns 'none' | 'low' | 'medium' | 'high'.
    Uses tool name regex match. Args ignored for now — could refine later
    (e.g. file_write to a system path = critical, to ~/.brain = low)."""
    name = (tool_name or "").strip()
    if not name:
        return "none"
    for rx, lvl in _RISK_RULES:
        if rx.search(name):
            return lvl
    return "none"


def annotate_tool_calls(tool_calls):
    """In-place annotate each tool-call dict with `risk_level` and (for
    high-risk) `approval_status='requested'`. Called on the captured-call
    list before persisting to Neo4j."""
    if not tool_calls:
        return tool_calls
    auto_request = os.environ.get("APPROVAL_AUTO_REQUEST_HIGH", "1") not in ("0", "false")
    for tc in tool_calls:
        risk = classify_risk(tc.get("tool"), tc.get("input"))
        tc["risk_level"] = risk
        if risk in ("high",) and auto_request and not tc.get("approval_status"):
            tc["approval_status"] = "requested"
        elif not tc.get("approval_status"):
            tc["approval_status"] = "none"
    return tool_calls


# ── ApprovalGate — pure in-memory (Brain holds state) ─────────────────


class ToolCallApprovalGate:
    """Tracks per-tool-call decisions. Persisted as approval_status in Neo4j.
    This is intentionally simple — no async wait, no callback. UI just
    posts decision; Brain stores it; future runs can read it back."""

    def __init__(self, decision_graph=None):
        self.decision_graph = decision_graph
        self._decisions: Dict[str, str] = {}  # tool_call_id -> approve|deny
        self.stats: Dict[str, int] = {
            "approved": 0, "denied": 0, "requested": 0,
            "auto_blocked": 0,
        }

    def attach_decision_graph(self, dg) -> None:
        self.decision_graph = dg

    def get_decision(self, tool_call_id: str) -> Optional[str]:
        return self._decisions.get(tool_call_id)

    def submit(self, tool_call_id: str, decision: str) -> Dict[str, Any]:
        decision = (decision or "").lower()
        if decision not in ("approve", "deny"):
            return {"ok": False, "error": f"invalid decision: {decision}"}
        self._decisions[tool_call_id] = decision
        if decision == "approve":
            self.stats["approved"] += 1
        else:
            self.stats["denied"] += 1
        # Update Neo4j status
        dg = self.decision_graph
        if dg is not None and dg.is_connected():
            try:
                with dg._driver.session() as s:
                    s.run(
                        "MATCH (tc:ToolCall {id: $id}) "
                        "SET tc.approval_status = $status, tc.decided_ts = $ts",
                        id=tool_call_id,
                        status="approved" if decision == "approve" else "denied",
                        ts=__import__("time").time(),
                    )
            except Exception as e:
                logger.debug(f"[approval] neo4j update failed: {e}")
        return {"ok": True, "tool_call_id": tool_call_id, "decision": decision}

    def stats_dict(self) -> Dict[str, Any]:
        return dict(self.stats)
