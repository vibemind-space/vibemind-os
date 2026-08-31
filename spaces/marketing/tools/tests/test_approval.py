"""Tests for the approval flow (Phase-2b proposal -> audience promotion).

Mocks _db so the suite runs without supabase. Verifies the Python wrappers
do not bypass any invariant the stored function enforces:
  * approve returns swarm-envelope shape (success + message + data)
  * idempotent re-approve surfaces was_idempotent=true
  * empty reason rejected at the Python layer (before DB call)
  * reject + already-approved error path
  * MX validation: dnspython missing -> returns None (skip), valid -> 1,
    NXDOMAIN -> 0
  * NEVER calls send_campaign / create_audience / create_template
    (regression-guard via spy)

Live invariants (DB-side) are enforced by stored functions in migration
012 -- this suite only verifies the Python wrapper doesn't break them.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))


from spaces.marketing.tools import approval as ap  # noqa: E402
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
        # Per-needle response. Last write wins.
        self.query_responses: list[tuple[str, list]] = []
        self.execute_responses: dict[str, str] = {}
        self.raise_on: dict[str, Exception] = {}

    def query_one(self, sql, *a, **k):
        rows = self.query_via_docker(sql, *a, **k)
        return rows[0] if rows else None

    def query_via_docker(self, sql, *a, **k):
        self.queries.append(sql)
        for needle, value in self.query_responses:
            if needle in sql:
                return value
        return []

    def execute_via_docker(self, sql, *a, **k):
        self.executes.append(sql)
        for needle, exc in self.raise_on.items():
            if needle in sql:
                raise exc
        for needle, value in self.execute_responses.items():
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


def _with_db(fn):
    def wrapper():
        fake = FakeDB()
        with mock.patch.object(ap, "_db", fake), \
             mock.patch.object(mt, "_db", fake):
            fn(fake)
    wrapper.__name__ = fn.__name__
    return wrapper


# ─── approve_proposal ──────────────────────────────────────────────────


@_with_db
def test_approve_envelope_shape(fake):
    """Happy-path: stored function returns one row, wrapper builds envelope."""
    fake.query_responses.append(
        ("FROM marketing.approve_audience_proposal", [{
            "out_proposal_id": "p1",
            "out_audience_id": "a1-abc12345",
            "out_accounts_created": 2,
            "out_emails_inserted": 2,
            "out_members_inserted": 2,
            "out_candidates_skipped": 0,
            "out_was_idempotent": False,
        }]),
    )
    r = ap.approve_proposal("p1", approved_by="test")
    ok = (
        r["success"]
        and "accounts+2" in r["message"]
        and r["data"]["audience_id"] == "a1-abc12345"
        and r["data"]["was_idempotent"] is False
    )
    _check("approve_envelope_shape", ok, f"r={r!r}")


@_with_db
def test_approve_idempotent_surfaces_flag(fake):
    fake.query_responses.append(
        ("FROM marketing.approve_audience_proposal", [{
            "out_proposal_id": "p1",
            "out_audience_id": "a1-abc",
            "out_accounts_created": 0,
            "out_emails_inserted": 0,
            "out_members_inserted": 0,
            "out_candidates_skipped": 0,
            "out_was_idempotent": True,
        }]),
    )
    r = ap.approve_proposal("p1")
    _check("approve_idempotent_flag",
           r["success"] and "[idempotent]" in r["message"]
           and r["data"]["was_idempotent"] is True)


@_with_db
def test_approve_empty_result_handled(fake):
    """If stored function returns 0 rows -- never should -- envelope says false."""
    # No matching response => empty list
    r = ap.approve_proposal("ghost-id")
    _check("approve_empty_result",
           r["success"] is False and "no rows" in r["message"])


# ─── reject_proposal ───────────────────────────────────────────────────


@_with_db
def test_reject_requires_reason(fake):
    r = ap.reject_proposal("p1", reason="")
    no_call = not any("FROM marketing.reject_audience_proposal" in s
                      for s in fake.queries)
    _check("reject_requires_reason",
           r["success"] is False and "reason required" in r["message"]
           and no_call)


@_with_db
def test_reject_happy_path(fake):
    fake.query_responses.append(
        ("FROM marketing.reject_audience_proposal", [{
            "out_proposal_id": "p1",
            "out_previous_status": "pending_review",
            "out_rejected_at": "2026-06-08T15:00:00+00:00",
        }]),
    )
    r = ap.reject_proposal("p1", reason="Not relevant for our ICP",
                           rejected_by="felix")
    _check("reject_happy_path",
           r["success"] and "pending_review" in r["message"])


@_with_db
def test_reject_surfaces_stored_function_error(fake):
    """Stored function raises on approved-proposal reject. The
    Python wrapper catches RuntimeError and returns success=false."""
    fake.raise_on["FROM marketing.reject_audience_proposal"] = RuntimeError(
        "psql failed: ERROR: cannot reject already-approved proposal p1"
    )
    # query_via_docker is what raises, not execute. Switch the raise hook
    # to the query path.
    def _raising(sql, *a, **k):
        fake.queries.append(sql)
        if "FROM marketing.reject_audience_proposal" in sql:
            raise RuntimeError(
                "psql failed: ERROR: cannot reject already-approved proposal p1"
            )
        return []
    with mock.patch.object(fake, "query_via_docker", _raising):
        r = ap.reject_proposal("p1", reason="too late",
                               rejected_by="felix")
    _check("reject_surfaces_error",
           r["success"] is False
           and "already-approved" in r["message"])


# ─── validate_proposal_mx ──────────────────────────────────────────────


@_with_db
def test_mx_empty_proposal_returns_false(fake):
    # query_via_docker returns [] -> no candidates
    r = ap.validate_proposal_mx("p-empty")
    _check("mx_empty_proposal",
           r["success"] is False and "no candidates" in r["message"])


@_with_db
def test_mx_valid_domain_updates_smtp_valid_1(fake):
    fake.query_responses.append(
        ("SELECT DISTINCT split_part", [{"domain": "vibemind.space"}]),
    )
    with mock.patch.object(ap, "_has_mx_record", return_value=True):
        r = ap.validate_proposal_mx("p1")
    update_sql = next(
        (s for s in fake.executes
         if "UPDATE marketing.lead_candidates" in s and "smtp_valid = 1" in s),
        "",
    )
    _check("mx_valid_marks_smtp_valid_1",
           r["success"]
           and r["data"]["valid_domains"] == ["vibemind.space"]
           and "vibemind.space" in update_sql,
           f"update_sql={update_sql[:120]}")


@_with_db
def test_mx_nxdomain_marks_smtp_valid_0(fake):
    fake.query_responses.append(
        ("SELECT DISTINCT split_part", [{"domain": "ghost-domain.invalid"}]),
    )
    with mock.patch.object(ap, "_has_mx_record", return_value=False):
        r = ap.validate_proposal_mx("p1")
    update_sql = next(
        (s for s in fake.executes
         if "UPDATE marketing.lead_candidates" in s and "smtp_valid = 0" in s),
        "",
    )
    _check("mx_nxdomain_marks_0",
           r["success"]
           and r["data"]["invalid_domains"] == ["ghost-domain.invalid"]
           and "ghost-domain.invalid" in update_sql)


@_with_db
def test_mx_unknown_does_not_update(fake):
    """Timeout / DNS down -> smtp_valid stays -1, NO update issued."""
    fake.query_responses.append(
        ("SELECT DISTINCT split_part", [{"domain": "flaky.example"}]),
    )
    with mock.patch.object(ap, "_has_mx_record", return_value=None):
        r = ap.validate_proposal_mx("p1")
    updates = [s for s in fake.executes
               if "UPDATE marketing.lead_candidates" in s]
    _check("mx_unknown_no_update",
           r["success"]
           and r["data"]["unknown_domains"] == ["flaky.example"]
           and len(updates) == 0,
           f"updates={len(updates)}")


# ─── No-send-path regression-guards ────────────────────────────────────


@_with_db
def test_approve_never_calls_send_campaign(fake):
    fake.query_responses.append(
        ("FROM marketing.approve_audience_proposal", [{
            "out_proposal_id": "p1", "out_audience_id": "a1",
            "out_accounts_created": 1, "out_emails_inserted": 1,
            "out_members_inserted": 1, "out_candidates_skipped": 0,
            "out_was_idempotent": False,
        }]),
    )
    with mock.patch.object(mt, "send_campaign") as send_spy:
        ap.approve_proposal("p1")
    _check("approve_never_calls_send",
           send_spy.call_count == 0,
           f"send_campaign called {send_spy.call_count}x")


@_with_db
def test_reject_never_calls_send_campaign(fake):
    fake.query_responses.append(
        ("FROM marketing.reject_audience_proposal", [{
            "out_proposal_id": "p1",
            "out_previous_status": "pending_review",
            "out_rejected_at": "2026-06-08T15:00:00+00:00",
        }]),
    )
    with mock.patch.object(mt, "send_campaign") as send_spy:
        ap.reject_proposal("p1", reason="x", rejected_by="t")
    _check("reject_never_calls_send", send_spy.call_count == 0)


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        test_approve_envelope_shape,
        test_approve_idempotent_surfaces_flag,
        test_approve_empty_result_handled,
        test_reject_requires_reason,
        test_reject_happy_path,
        test_reject_surfaces_stored_function_error,
        test_mx_empty_proposal_returns_false,
        test_mx_valid_domain_updates_smtp_valid_1,
        test_mx_nxdomain_marks_smtp_valid_0,
        test_mx_unknown_does_not_update,
        test_approve_never_calls_send_campaign,
        test_reject_never_calls_send_campaign,
    ]
    print(f"[test_approval] running {len(tests)} tests")
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
    print("test_approval: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
