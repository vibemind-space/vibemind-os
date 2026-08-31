"""Tests for channel-config gate 4.5 + proposal archival.

Mocks _db so the suite runs without supabase. Verifies:
  channels:
    - list_channels filter flags
    - assert_channel_configured raises on unknown / unimplemented /
      disabled / env-missing
    - assert_channel_configured passes when send_implemented + enabled
      + env present
  archival:
    - archive_old_proposals envelope + dry_run flag flows through
    - days_old < 0 rejected
    - restore_proposal envelope + cannot-restore failure
  no-send regression:
    - none of the above ever calls send_campaign / create_audience
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))


from spaces.marketing.tools import channels as ch  # noqa: E402
from spaces.marketing.tools import archival as ar  # noqa: E402
from spaces.marketing.tools import marketing_tools as mt  # noqa: E402
from spaces.marketing.tools._send_paranoid import ParanoidAbort  # noqa: E402


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
        self.row_lookup: dict[str, dict] = {}      # needle -> row dict
        self.list_lookup: dict[str, list] = {}     # needle -> list of dicts

    def query_one(self, sql, *a, **k):
        self.queries.append(sql)
        for needle, row in self.row_lookup.items():
            if needle in sql:
                return row
        return None

    def query_via_docker(self, sql, *a, **k):
        self.queries.append(sql)
        for needle, rows in self.list_lookup.items():
            if needle in sql:
                return rows
        return []

    def execute_via_docker(self, sql, *a, **k):
        self.executes.append(sql)
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
        with mock.patch.object(ch, "_db", fake), \
             mock.patch.object(ar, "_db", fake), \
             mock.patch.object(mt, "_db", fake):
            fn(fake)
    wrapper.__name__ = fn.__name__
    return wrapper


# ─── channels.assert_channel_configured ────────────────────────────────


@_with_db
def test_unknown_channel_aborts(fake):
    try:
        ch.assert_channel_configured("unicorn")
        _check("channel_unknown", False)
    except ParanoidAbort as e:
        _check("channel_unknown",
               e.guard == "channel_unknown" and "unicorn" in str(e))


@_with_db
def test_not_implemented_channel_aborts(fake):
    fake.row_lookup["FROM marketing.channel_config"] = {
        "channel": "telegram", "send_implemented": False,
        "enabled": True, "required_env": [],
        "rate_limit_per_minute": 0,
    }
    try:
        ch.assert_channel_configured("telegram")
        _check("channel_not_implemented", False)
    except ParanoidAbort as e:
        _check("channel_not_implemented",
               e.guard == "channel_not_implemented")


@_with_db
def test_disabled_channel_aborts(fake):
    fake.row_lookup["FROM marketing.channel_config"] = {
        "channel": "email", "send_implemented": True,
        "enabled": False, "required_env": [],
    }
    try:
        ch.assert_channel_configured("email")
        _check("channel_disabled", False)
    except ParanoidAbort as e:
        _check("channel_disabled",
               e.guard == "channel_disabled" and "enabled=true" in str(e))


@_with_db
def test_missing_env_aborts(fake):
    fake.row_lookup["FROM marketing.channel_config"] = {
        "channel": "email", "send_implemented": True,
        "enabled": True,
        "required_env": ["TOTALLY_MADE_UP_ENV_X9Y2Z"],
    }
    # ensure env is not present
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TOTALLY_MADE_UP_ENV_X9Y2Z", None)
        try:
            ch.assert_channel_configured("email")
            _check("channel_env_missing", False)
        except ParanoidAbort as e:
            _check("channel_env_missing",
                   e.guard == "channel_env_missing"
                   and "TOTALLY_MADE_UP_ENV_X9Y2Z" in str(e))


@_with_db
def test_happy_path_passes(fake):
    fake.row_lookup["FROM marketing.channel_config"] = {
        "channel": "email", "send_implemented": True,
        "enabled": True,
        "required_env": ["SMTP_HOST"],
        "rate_limit_per_minute": 0,
    }
    with mock.patch.dict(os.environ, {"SMTP_HOST": "127.0.0.1"}, clear=False):
        try:
            r = ch.assert_channel_configured("email")
            _check("channel_happy_path",
                   r.get("channel") == "email"
                   and r.get("send_implemented") is True)
        except Exception as e:
            _check("channel_happy_path", False, str(e))


@_with_db
def test_list_channels_filter_implemented(fake):
    fake.list_lookup["WHERE send_implemented = true"] = [
        {"channel": "email", "send_implemented": True, "enabled": False,
         "required_env": ["SMTP_HOST"]},
    ]
    r = ch.list_channels(only_implemented=True)
    _check("list_filter_implemented",
           r["success"]
           and len(r["data"]) == 1
           and r["data"][0]["channel"] == "email")


# ─── archival ──────────────────────────────────────────────────────────


@_with_db
def test_archive_negative_days_rejected(fake):
    r = ar.archive_old_proposals(-1)
    _check("archive_neg_days",
           r["success"] is False and "days_old must be >= 0" in r["message"])


@_with_db
def test_archive_dry_run_envelope(fake):
    fake.list_lookup["FROM marketing.archive_old_proposals"] = [{
        "out_archived_count": 5,
        "out_dropped_candidates": 12,
        "out_dry_run": True,
    }]
    r = ar.archive_old_proposals(90, dry_run=True)
    _check("archive_dry_run_envelope",
           r["success"]
           and r["data"]["archived_count"] == 5
           and r["data"]["dropped_candidates"] == 12
           and r["data"]["dry_run"] is True
           and "DRY RUN" in r["message"])


@_with_db
def test_archive_live_run_envelope(fake):
    fake.list_lookup["FROM marketing.archive_old_proposals"] = [{
        "out_archived_count": 3, "out_dropped_candidates": 7,
        "out_dry_run": False,
    }]
    r = ar.archive_old_proposals(90, dry_run=False, archived_by="cron")
    _check("archive_live_run",
           r["success"]
           and r["data"]["dry_run"] is False
           and "archived 3 proposal" in r["message"])


@_with_db
def test_archive_list_filter(fake):
    fake.list_lookup["WHERE status ="] = [
        {"id": "a", "name": "X", "status": "rejected",
         "archived_at": "2026-01-01"},
    ]
    r = ar.list_archive(status="rejected")
    _check("archive_list_filter",
           r["success"] and len(r["data"]) == 1
           and r["data"][0]["status"] == "rejected")


@_with_db
def test_restore_happy_path(fake):
    fake.list_lookup["FROM marketing.restore_proposal_from_archive"] = [{
        "out_proposal_id": "p1", "out_restored": True,
    }]
    r = ar.restore_proposal("p1", restored_by="op")
    _check("restore_happy_path",
           r["success"]
           and r["data"]["proposal_id"] == "p1"
           and "NOT restored" in r["message"])


@_with_db
def test_restore_missing_archive_raises(fake):
    """Stored function raises -- wrapper catches RuntimeError."""
    def raise_runtime(sql, *a, **k):
        fake.queries.append(sql)
        if "FROM marketing.restore_proposal_from_archive" in sql:
            raise RuntimeError("psql failed: ERROR: no archive row for ...")
        return []
    with mock.patch.object(fake, "query_via_docker", raise_runtime):
        r = ar.restore_proposal("ghost", restored_by="op")
    _check("restore_missing_archive",
           r["success"] is False and "no archive row" in r["message"])


# ─── No-send-path regression ───────────────────────────────────────────


@_with_db
def test_archival_never_calls_send(fake):
    fake.list_lookup["FROM marketing.archive_old_proposals"] = [{
        "out_archived_count": 1, "out_dropped_candidates": 1,
        "out_dry_run": False,
    }]
    with mock.patch.object(mt, "send_campaign") as send_spy, \
         mock.patch.object(mt, "create_audience") as ca_spy:
        ar.archive_old_proposals(90)
    _check("archival_never_calls_send",
           send_spy.call_count == 0 and ca_spy.call_count == 0)


@_with_db
def test_channel_check_never_calls_send(fake):
    fake.row_lookup["FROM marketing.channel_config"] = {
        "channel": "email", "send_implemented": True, "enabled": True,
        "required_env": [],
    }
    with mock.patch.object(mt, "send_campaign") as send_spy:
        ch.assert_channel_configured("email")
    _check("channel_check_never_calls_send", send_spy.call_count == 0)


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        # channels
        test_unknown_channel_aborts,
        test_not_implemented_channel_aborts,
        test_disabled_channel_aborts,
        test_missing_env_aborts,
        test_happy_path_passes,
        test_list_channels_filter_implemented,
        # archival
        test_archive_negative_days_rejected,
        test_archive_dry_run_envelope,
        test_archive_live_run_envelope,
        test_archive_list_filter,
        test_restore_happy_path,
        test_restore_missing_archive_raises,
        # no-send-path
        test_archival_never_calls_send,
        test_channel_check_never_calls_send,
    ]
    print(f"[test_channels_and_archival] running {len(tests)} tests")
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
    print("test_channels_and_archival: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
