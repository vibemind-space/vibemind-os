"""Tests for Worker E -- async MX validation queue.

Mocks _db so the suite runs without supabase. Verifies:
  * enqueue inserts a row and returns job_id
  * process_one claims pending -> running -> done atomically
  * empty queue returns False
  * retry-on-error stays under MAX_ATTEMPTS, marks 'error' after
  * domain-only jobs (no proposal_id) yield clear error
  * never_calls_send_campaign regression-guard
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))


from spaces.marketing.workers import mx_worker as mx  # noqa: E402
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
        self.execute_responses: dict[str, str] = {}
        self.query_responses: list[tuple[str, list]] = []

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
        for needle, val in self.execute_responses.items():
            if needle in sql:
                return val
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
        with mock.patch.object(mx, "_db", fake), \
             mock.patch.object(mt, "_db", fake):
            fn(fake)
    wrapper.__name__ = fn.__name__
    return wrapper


# ─── enqueue ───────────────────────────────────────────────────────────


@_with_db
def test_enqueue_returns_job_id(fake):
    fake.execute_responses["RETURNING id"] = "job-uuid-1\nINSERT 0 1\n"
    r = mx.enqueue_mx_validation("prop-1", requested_by="test")
    _check("enqueue_returns_job_id",
           r["success"]
           and r["data"]["job_id"] == "job-uuid-1"
           and r["data"]["status"] == "pending")


@_with_db
def test_enqueue_no_id_returns_failure(fake):
    fake.execute_responses["RETURNING id"] = "INSERT 0 1\n"  # no row id
    r = mx.enqueue_mx_validation("prop-1")
    _check("enqueue_no_id_failure",
           r["success"] is False)


# ─── process_one ───────────────────────────────────────────────────────


@_with_db
def test_process_one_empty_queue(fake):
    """No claim -> False."""
    fake.execute_responses["UPDATE marketing.mx_validation_jobs"] = ""
    r = mx.process_one()
    _check("process_empty_returns_false", r is False)


@_with_db
def test_process_one_happy_path(fake):
    """Claim job -> validate_proposal_mx -> finish 'done'."""
    fake.execute_responses["FOR UPDATE SKIP LOCKED"] = (
        "job-uuid-1|prop-1||0\nUPDATE 1\n"
    )
    # validate_proposal_mx is called via marketing_tools; spy on it
    with mock.patch("spaces.marketing.workers.mx_worker.validate_proposal_mx",
                    return_value={"success": True,
                                  "message": "ok",
                                  "data": {"valid_domains": ["x.com"]}}):
        r = mx.process_one()
    finish_sqls = [s for s in fake.executes if "status = 'done'" in s]
    _check("process_happy_path",
           r is True and len(finish_sqls) >= 1,
           f"executes={fake.executes!r}")


@_with_db
def test_process_one_no_proposal_id_errors(fake):
    """Job with no proposal_id (domain-only) marks error.

    Note: today domain-only jobs aren't yet supported by validate_proposal_mx.
    The worker should not crash -- it should mark the job error.
    """
    fake.execute_responses["FOR UPDATE SKIP LOCKED"] = (
        "job-uuid-2||example.com|0\nUPDATE 1\n"
    )
    r = mx.process_one()
    error_sqls = [s for s in fake.executes if "status = 'error'" in s]
    _check("process_no_proposal_errors",
           r is True and len(error_sqls) >= 1)


@_with_db
def test_process_one_retries_under_limit(fake):
    """Exception during validate -> attempt_count<MAX_ATTEMPTS -> flip back to pending."""
    fake.execute_responses["FOR UPDATE SKIP LOCKED"] = (
        "job-uuid-3|prop-3||0\nUPDATE 1\n"
    )
    with mock.patch("spaces.marketing.workers.mx_worker.validate_proposal_mx",
                    side_effect=RuntimeError("DNS down")):
        r = mx.process_one()
    pending_again = [s for s in fake.executes if "status='pending'" in s]
    _check("process_retries_under_limit",
           r is True and len(pending_again) >= 1,
           f"executes={fake.executes!r}")


@_with_db
def test_process_one_errors_at_max_attempts(fake):
    """attempt_count >= MAX_ATTEMPTS -> mark 'error' permanently."""
    fake.execute_responses["FOR UPDATE SKIP LOCKED"] = (
        f"job-uuid-4|prop-4||{mx.MAX_ATTEMPTS}\nUPDATE 1\n"
    )
    with mock.patch("spaces.marketing.workers.mx_worker.validate_proposal_mx",
                    side_effect=RuntimeError("DNS down")):
        r = mx.process_one()
    error_sqls = [s for s in fake.executes if "status = 'error'" in s]
    _check("process_errors_at_max",
           r is True and len(error_sqls) >= 1)


# ─── No-send-path regression ───────────────────────────────────────────


@_with_db
def test_worker_never_calls_send_campaign(fake):
    fake.execute_responses["FOR UPDATE SKIP LOCKED"] = (
        "job-uuid-5|prop-5||0\nUPDATE 1\n"
    )
    with mock.patch.object(mt, "send_campaign") as send_spy, \
         mock.patch("spaces.marketing.workers.mx_worker.validate_proposal_mx",
                    return_value={"success": True, "message": "ok",
                                  "data": {}}):
        mx.process_one()
    _check("worker_never_calls_send",
           send_spy.call_count == 0)


# ─── list_mx_jobs ──────────────────────────────────────────────────────


@_with_db
def test_list_mx_jobs_filter_by_status(fake):
    fake.query_responses.append(
        ("WHERE status = 'pending'", [
            {"id": "j1", "proposal_id": "p1", "domain": None,
             "status": "pending", "attempt_count": 0,
             "error_message": None, "created_at": "2026-06-08T12:00:00",
             "finished_at": None},
        ]),
    )
    r = mx.list_mx_jobs(status="pending")
    _check("list_filter_by_status",
           r["success"]
           and len(r["data"]) == 1
           and r["data"][0]["status"] == "pending")


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        test_enqueue_returns_job_id,
        test_enqueue_no_id_returns_failure,
        test_process_one_empty_queue,
        test_process_one_happy_path,
        test_process_one_no_proposal_id_errors,
        test_process_one_retries_under_limit,
        test_process_one_errors_at_max_attempts,
        test_worker_never_calls_send_campaign,
        test_list_mx_jobs_filter_by_status,
    ]
    print(f"[test_mx_worker] running {len(tests)} tests")
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
    print("test_mx_worker: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
