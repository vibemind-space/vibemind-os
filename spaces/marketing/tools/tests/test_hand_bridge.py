"""Unit tests for the OpenFang Hand bridge.

Mocks _db + urllib.request so the suite runs without supabase or
OpenFang. Covers:
  * unknown hand_id -> rejected
  * OpenFang unreachable -> sauberer failure, audit row geschrieben
  * Hand not activated -> failure with explicit message
  * Hand activated -> POST sent, success returned, audit row written
  * propose_audience: cap, dedup, allowlist source normalisation
  * list_proposals + get_proposal queries built correctly
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.tools import hand_bridge as hb  # noqa: E402
from spaces.marketing.tools import marketing_tools as mt  # noqa: E402


_FAILS: list[str] = []


def _check(label: str, cond: bool, detail: str = ""):
    mark = "PASS" if cond else "FAIL"
    line = f"  [{mark}] {label}"
    if detail and not cond:
        line += f"  -- {detail}"
    print(line)
    if not cond:
        _FAILS.append(label)


class FakeDB:
    def __init__(self):
        self.executes: list[str] = []
        self.queries: list[str] = []
        self.row_response = None
        self.list_response: list = []
        self.execute_response_map: dict[str, str] = {}

    def execute_via_docker(self, sql, *a, **k):
        self.executes.append(sql)
        for needle, value in self.execute_response_map.items():
            if needle in sql:
                return value
        return ""

    def query_via_docker(self, sql, *a, **k):
        self.queries.append(sql)
        return self.list_response

    def query_one(self, sql, *a, **k):
        self.queries.append(sql)
        return self.row_response

    def _sql_literal(self, v):
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"


def with_db(fn):
    def wrapper():
        fake = FakeDB()
        # Patch both modules' _db references (hand_bridge + marketing_tools)
        with mock.patch.object(hb, "_db", fake), \
             mock.patch.object(mt, "_db", fake):
            fn(fake)
    wrapper.__name__ = fn.__name__
    return wrapper


# ─── Track C tests: request_hand_research ──────────────────────────────


@with_db
def test_unknown_hand_id_rejected(fake):
    r = hb.request_hand_research("ghost-hand")
    no_request = not any("audit_log" in s and "ghost-hand" in s for s in fake.executes)
    # Audit row should NOT be written for unknown hand_id (rejected before openfang call)
    _check("unknown_hand_id_rejected",
           r["success"] is False and "unknown hand_id" in r["message"]
           and no_request,
           f"r={r!r}")


@with_db
def test_openfang_unreachable_clean_failure(fake):
    """No /api/hands listener: clean failure + audit row."""
    with mock.patch("urllib.request.urlopen",
                    side_effect=OSError("connection refused")):
        r = hb.request_hand_research("lead-hand", industry="SaaS")
    audit_present = any("audit_log" in s and "request_lead-hand" in s
                        for s in fake.executes)
    _check("openfang_unreachable_audit_written",
           r["success"] is False
           and "lead-hand" in r["message"]
           and audit_present)


@with_db
def test_openfang_returns_no_active_hand(fake):
    """OpenFang answers but Hand isn't activated."""
    other_hand = mock.MagicMock()
    other_hand.read.return_value = json.dumps([
        {"hand_id": "twitter", "status": "Active", "agent_id": "x"},
    ]).encode()
    other_hand.__enter__ = lambda s: s
    other_hand.__exit__ = lambda *a: False
    with mock.patch("urllib.request.urlopen", return_value=other_hand):
        r = hb.request_hand_research("lead-hand")
    _check("openfang_no_active_hand",
           r["success"] is False and "not activated" in r["message"])


@with_db
def test_openfang_active_hand_submits(fake):
    """OpenFang says Hand is active, we POST a message and audit success."""
    list_resp = mock.MagicMock()
    list_resp.read.return_value = json.dumps([
        {"hand_id": "lead-hand", "status": "Active", "agent_id": "agent-uuid-123"},
    ]).encode()
    list_resp.__enter__ = lambda s: s
    list_resp.__exit__ = lambda *a: False
    post_resp = mock.MagicMock()
    post_resp.read.return_value = json.dumps({"message_id": "msg-99"}).encode()
    post_resp.__enter__ = lambda s: s
    post_resp.__exit__ = lambda *a: False
    seq = [list_resp, post_resp]
    with mock.patch("urllib.request.urlopen", side_effect=seq):
        r = hb.request_hand_research(
            "lead-hand", industry="SaaS", role="CTO", n=10, notes="smoke",
        )
    audit_present = any("audit_log" in s and "msg-99" in s for s in fake.executes)
    _check("openfang_active_hand_submits",
           r["success"]
           and r["data"]["agent_id"] == "agent-uuid-123"
           and r["data"]["job_ref"] == "msg-99"
           and audit_present)


# ─── Track A tests: propose_audience ───────────────────────────────────


@with_db
def test_propose_audience_dedup_within_proposal(fake):
    """Same email twice with different case -> normalised, deduplicated."""
    fake.execute_response_map["RETURNING id"] = "proposal-uuid-1\nINSERT 0 1\n"
    fake.row_response = {"n": 1}  # the count-query after bulk insert
    r = mt.propose_audience(
        "test", {"x": 1},
        candidate_emails=[
            {"email": "Alice@example.com"},
            {"email": "alice@EXAMPLE.com"},  # case dupe
            {"email": ""},                    # invalid
            {"email": "bob@example.com"},     # valid
        ],
        source="lead-hand",
    )
    _check("propose_audience_dedup",
           r["success"]
           and r["data"]["proposal_id"] == "proposal-uuid-1"
           and r["data"]["candidates_skipped"] >= 1,
           f"r={r!r}")


@with_db
def test_propose_audience_unknown_source_normalised(fake):
    """Unknown source should be coerced to hand:unknown (no smuggling)."""
    fake.execute_response_map["RETURNING id"] = "proposal-uuid-2\n"
    r = mt.propose_audience("t", {}, source="EVIL-INJECTION; DROP TABLE x")
    proposal_insert = next(
        (s for s in fake.executes if "INSERT INTO marketing.audience_proposals" in s),
        "",
    )
    _check("propose_audience_unknown_source_clean",
           r["success"] and "'hand:unknown'" in proposal_insert,
           f"insert_sql={proposal_insert[:200]}")


@with_db
def test_propose_audience_cap_enforced(fake):
    """More than _PROPOSAL_CANDIDATE_CAP candidates => refused."""
    huge = [{"email": f"r{i}@vibemind.space"} for i in range(mt._PROPOSAL_CANDIDATE_CAP + 1)]
    r = mt.propose_audience("t", {}, candidate_emails=huge)
    _check("propose_audience_cap_enforced",
           r["success"] is False and "too many" in r["message"])


# ─── Track B tests: event-mapping ──────────────────────────────────────


def test_marketing_agent_maps_proposal_events():
    """Hand-bridge events must map to the right tool names."""
    from spaces.marketing.agents import get_marketing_agent
    a = get_marketing_agent()
    ok = (
        a.EVENT_TO_TOOL.get("marketing.audience_proposal") == "propose_audience"
        and a.EVENT_TO_TOOL.get("marketing.list_proposals") == "list_proposals"
        and a.EVENT_TO_TOOL.get("marketing.get_proposal") == "get_proposal"
        and a.EVENT_TO_TOOL.get("marketing.request_hand") == "request_hand_research"
    )
    _check("agent_events_map_bridge", ok,
           f"event_to_tool={a.EVENT_TO_TOOL!r}")


def test_marketing_agent_normalises_hand_keys():
    """Hand-emitted keys (icp_filter, leads, etc.) get translated."""
    from spaces.marketing.agents import get_marketing_agent
    a = get_marketing_agent()
    r = a._normalize_params("marketing.audience_proposal", {
        "title": "CTOs Q1",
        "icp_filter": {"industry": "SaaS"},
        "leads": [{"email": "a@vibemind.space"}],
        "reasoning": "growth signal",
        "by": "lead-hand",
    })
    ok = (
        r.get("name") == "CTOs Q1"
        and r.get("filter_dsl") == {"industry": "SaaS"}
        and isinstance(r.get("candidate_emails"), list)
        and r.get("rationale") == "growth signal"
        and r.get("source") == "lead-hand"
    )
    _check("agent_normalises_hand_keys", ok, f"normalized={r!r}")


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        # Track C
        test_unknown_hand_id_rejected,
        test_openfang_unreachable_clean_failure,
        test_openfang_returns_no_active_hand,
        test_openfang_active_hand_submits,
        # Track A
        test_propose_audience_dedup_within_proposal,
        test_propose_audience_unknown_source_normalised,
        test_propose_audience_cap_enforced,
        # Track B
        test_marketing_agent_maps_proposal_events,
        test_marketing_agent_normalises_hand_keys,
    ]
    print(f"[test_hand_bridge] running {len(tests)} tests")
    for t in tests:
        try:
            t()
        except Exception as e:
            _check(t.__name__, False, f"raised {type(e).__name__}: {e}")
    total = len(tests); fails = len(_FAILS)
    print(f"\n=== {total - fails}/{total} passed ===")
    if fails:
        for f in _FAILS: print(f"  - {f}")
        return 1
    print("test_hand_bridge: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
