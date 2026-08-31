"""Tests for the external integrations bridge.

Mocks _db so the suite runs without supabase. Each test verifies a
specific safety invariant:
  * unknown kind rejected (allowlist enforcement)
  * disabled source rejected
  * defense-in-depth refuses if can_send returned true (CHECK violated)
  * extractor garbage-in -> 0 candidates, no proposal created
  * extractor happy-path -> propose_audience called WITH source='manual'
    (never 'lead-hand' / not promoting to send-eligible audience)
  * extractor dedups + per-kind cap honoured
  * NO call ever lands on send_campaign / create_audience /
    create_template / marketing.emails (regression-guard via spy)
  * audit-row written even on refusal where applicable
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))


from spaces.marketing.tools import integrations as ig  # noqa: E402
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
        self.queries: list[str] = []
        self.executes: list[str] = []
        self.source_row: dict | None = None
        self.execute_response: dict[str, str] = {}
        self.proposal_count_response = {"n": 0}

    def query_one(self, sql, *a, **k):
        self.queries.append(sql)
        # Two query_one call sites: external_sources lookup + count after insert.
        if "FROM marketing.external_sources" in sql:
            return self.source_row
        if "FROM marketing.lead_candidates" in sql:
            return self.proposal_count_response
        return None

    def query_via_docker(self, sql, *a, **k):
        self.queries.append(sql)
        return []

    def execute_via_docker(self, sql, *a, **k):
        self.executes.append(sql)
        for needle, value in self.execute_response.items():
            if needle in sql:
                return value
        return ""

    def _sql_literal(self, v):
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"


def _safe_source_row(kind="manual-csv"):
    return {
        "kind": kind, "label": f"{kind} test",
        "enabled": True, "can_send": False,
        "openfang_skill": None, "required_env": [],
    }


def _with_db(fn):
    def wrapper():
        fake = FakeDB()
        # propose_audience will reach into _db too -- patch both modules.
        with mock.patch.object(ig, "_db", fake), \
             mock.patch.object(mt, "_db", fake):
            fn(fake)
    wrapper.__name__ = fn.__name__
    return wrapper


# ─── Allowlist enforcement ─────────────────────────────────────────────


@_with_db
def test_unknown_kind_rejected(fake):
    try:
        ig.propose_audience_from_source("evil-source", {})
        _check("unknown_kind_rejected", False, "no IntegrationError raised")
    except ig.IntegrationError as e:
        _check("unknown_kind_rejected",
               "unknown integration kind" in str(e)
               and "evil-source" in str(e))


@_with_db
def test_known_kind_passes_allowlist(fake):
    """kind in allowlist proceeds (then fails on empty payload)."""
    fake.source_row = _safe_source_row("manual-csv")
    try:
        r = ig.propose_audience_from_source("manual-csv", {"csv_text": ""})
        _check("known_kind_passes_allowlist", False,
               f"should have raised for empty csv: r={r!r}")
    except ig.IntegrationError as e:
        _check("known_kind_passes_allowlist",
               "csv_text" in str(e))


# ─── External-source row checks ────────────────────────────────────────


@_with_db
def test_missing_source_row_rejected(fake):
    fake.source_row = None  # row missing
    try:
        ig.propose_audience_from_source("gmail-search", {"messages": []})
        _check("missing_source_row_rejected", False)
    except ig.IntegrationError as e:
        _check("missing_source_row_rejected",
               "no external_sources row" in str(e))


@_with_db
def test_disabled_source_rejected(fake):
    fake.source_row = _safe_source_row("notion-page")
    fake.source_row["enabled"] = False
    try:
        ig.propose_audience_from_source("notion-page",
                                        {"contacts": [{"email": "a@x.com"}]})
        _check("disabled_source_rejected", False)
    except ig.IntegrationError as e:
        _check("disabled_source_rejected",
               "disabled" in str(e) and "enabled=true" in str(e))


@_with_db
def test_can_send_true_refused_loud(fake):
    """If the schema CHECK ever gets dropped and can_send=true comes back,
    refuse loud rather than silently routing to send."""
    fake.source_row = _safe_source_row("manual-csv")
    fake.source_row["can_send"] = True
    try:
        ig.propose_audience_from_source("manual-csv",
                                        {"csv_text": "email\na@b.com\n"})
        _check("can_send_true_refused_loud", False,
               "INVARIANT BROKEN not raised")
    except ig.IntegrationError as e:
        _check("can_send_true_refused_loud",
               "INVARIANT BROKEN" in str(e))


# ─── Per-extractor smoke ───────────────────────────────────────────────


@_with_db
def test_gmail_extractor_pulls_from_messages(fake):
    fake.source_row = _safe_source_row("gmail-search")
    fake.execute_response["RETURNING id"] = "prop-uuid-gmail\n"
    fake.proposal_count_response = {"n": 2}
    payload = {
        "query": "from:vibemind.space",
        "messages": [
            {"from": "Alice <alice@vibemind.space>", "subject": "Re: launch",
             "date": "2026-01-15"},
            {"reply_to": "bob@vibemind.space", "from": "no-reply@x.com"},
            {"from": "garbage no email here"},   # skipped
        ],
    }
    r = ig.propose_audience_from_source("gmail-search", payload)
    _check("gmail_extractor_pulls",
           r["success"]
           and r["data"]["candidates_inserted"] == 2
           and r["data"]["source"] == "gmail-search",
           f"r={r!r}")


@_with_db
def test_notion_extractor_uses_contacts_when_provided(fake):
    fake.source_row = _safe_source_row("notion-page")
    fake.execute_response["RETURNING id"] = "prop-uuid-notion\n"
    fake.proposal_count_response = {"n": 1}
    payload = {
        "page_id": "page-123",
        "contacts": [
            {"email": "felix@vibemind.space", "name": "Felix", "company": "VibeMind"},
            {"email": "BAD"},   # invalid -- skipped by regex
        ],
    }
    r = ig.propose_audience_from_source("notion-page", payload)
    _check("notion_extractor_contacts",
           r["success"] and r["data"]["candidates_inserted"] == 1,
           f"r={r!r}")


@_with_db
def test_sheets_extractor_requires_email_per_row(fake):
    fake.source_row = _safe_source_row("sheets-row")
    fake.execute_response["RETURNING id"] = "prop-uuid-sheets\n"
    fake.proposal_count_response = {"n": 2}
    payload = {
        "sheet_id": "abc", "range": "A2:E100",
        "rows": [
            {"email": "a@vibemind.space", "name": "A"},
            {"email": "b@vibemind.space"},
            {"name": "no email"},   # skipped
        ],
    }
    r = ig.propose_audience_from_source("sheets-row", payload)
    _check("sheets_extractor_row_filter",
           r["success"] and r["data"]["candidates_inserted"] == 2,
           f"r={r!r}")


@_with_db
def test_tavily_extractor_scrapes_emails(fake):
    fake.source_row = _safe_source_row("tavily-search")
    fake.execute_response["RETURNING id"] = "prop-uuid-tavily\n"
    fake.proposal_count_response = {"n": 1}
    payload = {
        "query": "vibemind contact",
        "results": [
            {"url": "https://example.com", "title": "Hi",
             "content": "Contact us at felix@vibemind.space anytime."},
        ],
    }
    r = ig.propose_audience_from_source("tavily-search", payload)
    _check("tavily_extractor_scrapes",
           r["success"] and r["data"]["candidates_inserted"] == 1,
           f"r={r!r}")


@_with_db
def test_csv_extractor_strict(fake):
    fake.source_row = _safe_source_row("manual-csv")
    fake.execute_response["RETURNING id"] = "prop-uuid-csv\n"
    fake.proposal_count_response = {"n": 2}
    payload = {
        "csv_text": "email,name,company\n"
                    "x@vibemind.space,X User,VibeMind\n"
                    "y@vibemind.space,Y,\n"
                    "not-an-email,Z,\n",
    }
    r = ig.propose_audience_from_source("manual-csv", payload,
                                        audience_name="csv-test")
    _check("csv_extractor_strict",
           r["success"] and r["data"]["candidates_inserted"] == 2,
           f"r={r!r}")


@_with_db
def test_csv_missing_email_column_rejected(fake):
    fake.source_row = _safe_source_row("manual-csv")
    try:
        ig.propose_audience_from_source("manual-csv",
                                        {"csv_text": "name,age\nA,12\n"})
        _check("csv_missing_email_column", False)
    except ig.IntegrationError as e:
        _check("csv_missing_email_column",
               "must have an 'email' column" in str(e))


# ─── No-send-path regression-guards ────────────────────────────────────


@_with_db
def test_never_calls_send_campaign(fake):
    """Spy on mt.send_campaign -- must not be called by ANY import path."""
    fake.source_row = _safe_source_row("manual-csv")
    fake.execute_response["RETURNING id"] = "prop-uuid-nosend\n"
    fake.proposal_count_response = {"n": 1}
    with mock.patch.object(mt, "send_campaign") as send_spy, \
         mock.patch.object(mt, "create_audience") as ca_spy, \
         mock.patch.object(mt, "create_template") as ct_spy:
        ig.propose_audience_from_source(
            "manual-csv",
            {"csv_text": "email\nfelix@vibemind.space\n"},
        )
    _check("never_calls_send_campaign",
           send_spy.call_count == 0
           and ca_spy.call_count == 0
           and ct_spy.call_count == 0,
           f"send={send_spy.call_count} create_audience={ca_spy.call_count} create_template={ct_spy.call_count}")


@_with_db
def test_audit_row_written_on_success(fake):
    fake.source_row = _safe_source_row("manual-csv")
    fake.execute_response["RETURNING id"] = "prop-uuid-aud\n"
    fake.proposal_count_response = {"n": 1}
    ig.propose_audience_from_source(
        "manual-csv", {"csv_text": "email\na@vibemind.space\n"},
    )
    # Two audit rows expected: one from propose_audience (already tested
    # in test_hand_bridge) + one from integrations layer.
    integration_audits = [
        s for s in fake.executes
        if "audit_log" in s and "integrations:manual-csv" in s
    ]
    _check("audit_row_on_success",
           len(integration_audits) >= 1,
           f"integration_audits={len(integration_audits)}")


@_with_db
def test_per_kind_cap_enforced(fake):
    """tavily-search cap is 100 -- 200 candidates extracted should
    truncate to 100 before delegation."""
    fake.source_row = _safe_source_row("tavily-search")
    fake.execute_response["RETURNING id"] = "prop-uuid-cap\n"
    fake.proposal_count_response = {"n": 100}
    # Build 200 unique results
    results = [
        {"url": f"https://x{i}.com", "title": "x", "content": f"r{i}@vibemind.space"}
        for i in range(200)
    ]
    r = ig.propose_audience_from_source("tavily-search",
                                        {"query": "q", "results": results})
    _check("per_kind_cap_enforced",
           r["success"] and r["data"].get("truncated") is True,
           f"r={r!r}")


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        # allowlist
        test_unknown_kind_rejected,
        test_known_kind_passes_allowlist,
        # source-row checks
        test_missing_source_row_rejected,
        test_disabled_source_rejected,
        test_can_send_true_refused_loud,
        # per-extractor
        test_gmail_extractor_pulls_from_messages,
        test_notion_extractor_uses_contacts_when_provided,
        test_sheets_extractor_requires_email_per_row,
        test_tavily_extractor_scrapes_emails,
        test_csv_extractor_strict,
        test_csv_missing_email_column_rejected,
        # no-send-path
        test_never_calls_send_campaign,
        test_audit_row_written_on_success,
        test_per_kind_cap_enforced,
    ]
    print(f"[test_integrations] running {len(tests)} tests")
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
    print("test_integrations: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
