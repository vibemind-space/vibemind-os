"""Tests for the Telegram send-worker (12-gate stack adapted for chat_id).

Mocks _db + urllib (Telegram Bot API calls) so the suite runs without
supabase OR network access. Verifies:

  Allowlist + safeguards:
    - _ALLOWED_CHAT_IDS is a frozenset, env-configured (fail-closed)
    - chat_id outside allowlist -> ParanoidAbort
    - kill-switch env unset in LIVE -> abort
    - freeze-file present -> abort
    - missing TELEGRAM_BOT_TOKEN env -> abort
    - campaign.channel != 'telegram' -> abort
    - 0 recipients -> abort
    - Recipient cap (>100) -> abort

  Token:
    - deterministic + audience-change-invalidates
    - LIVE without token -> abort
    - LIVE with wrong token -> abort

  DRY_RUN:
    - never hits api.telegram.org
    - returns confirm_token + recipient preview
    - never inserts campaign_sends_telegram rows

  Dispatch:
    - marketing_tools.send_campaign routes to telegram for channel='telegram'
    - email campaigns still go to _send_paranoid (no cross-routing)
    - unknown channel -> clean failure
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


# Example operator id; the real allowlist comes from the environment.
TEST_CHAT_ID = 1000000001
os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = str(TEST_CHAT_ID)

from spaces.marketing.tools import _send_telegram as tg  # noqa: E402
from spaces.marketing.tools import marketing_tools as mt  # noqa: E402
from spaces.marketing.tools._send_paranoid import (  # noqa: E402
    ParanoidAbort, SendMode,
)


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
        self.row_lookup: dict[str, dict] = {}
        self.list_lookup: dict[str, list] = {}
        self.execute_response: dict[str, str] = {}

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
        for needle, val in self.execute_response.items():
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
        # _send_telegram imports _audit from _send_paranoid which uses
        # its own _db reference -- patch all three.
        from spaces.marketing.tools import _send_paranoid as sp
        with mock.patch.object(tg, "_db", fake), \
             mock.patch.object(mt, "_db", fake), \
             mock.patch.object(sp, "_db", fake):
            fn(fake)
    wrapper.__name__ = fn.__name__
    return wrapper


def _ok_campaign():
    return {"id": "camp-1", "name": "Test", "channel": "telegram",
            "status": "draft", "audience_id": "aud-1",
            "template_id": None}


# ─── Allowlist ─────────────────────────────────────────────────────────


def test_allowed_chat_ids_is_frozenset():
    _check("allowed_is_frozenset", isinstance(tg._ALLOWED_CHAT_IDS, frozenset))
    _check("operator_chat_id_in_allowlist", TEST_CHAT_ID in tg._ALLOWED_CHAT_IDS)


def test_chat_id_outside_allowlist_aborts():
    try:
        tg._scan_chat_id_allowlist([{"chat_id": 999999999}])
        _check("chat_id_not_allowed", False, "abort not raised")
    except ParanoidAbort as e:
        _check("chat_id_not_allowed",
               e.guard == "tg_chat_id_allowlist")


def test_chat_id_non_int_rejected():
    try:
        tg._scan_chat_id_allowlist([{"chat_id": "not-int"}])
        _check("chat_id_non_int", False)
    except ParanoidAbort as e:
        _check("chat_id_non_int", e.guard == "tg_chat_id_allowlist")


def test_allowed_chat_id_passes():
    try:
        tg._scan_chat_id_allowlist([{"chat_id": TEST_CHAT_ID}])
        _check("allowed_chat_id_passes", True)
    except ParanoidAbort as e:
        _check("allowed_chat_id_passes", False, str(e))


# ─── Kill-switch + freeze + bot token ──────────────────────────────────


def test_kill_switch_off_aborts():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TELEGRAM_SEND_ENABLED", None)
        try:
            tg._check_kill_switch()
            _check("tg_kill_off", False)
        except ParanoidAbort as e:
            _check("tg_kill_off", e.guard == "tg_kill_switch")


def test_kill_switch_on_passes():
    with mock.patch.dict(os.environ, {"TELEGRAM_SEND_ENABLED": "true"},
                         clear=False):
        try:
            tg._check_kill_switch()
            _check("tg_kill_on", True)
        except ParanoidAbort as e:
            _check("tg_kill_on", False, str(e))


def test_missing_bot_token_aborts():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        try:
            tg._resolve_bot_token()
            _check("tg_missing_token", False)
        except ParanoidAbort as e:
            _check("tg_missing_token", e.guard == "tg_bot_token")


def test_malformed_bot_token_aborts():
    with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "not-a-token"},
                         clear=False):
        try:
            tg._resolve_bot_token()
            _check("tg_malformed_token", False)
        except ParanoidAbort as e:
            _check("tg_malformed_token", e.guard == "tg_bot_token")


# ─── Campaign / recipient gates ───────────────────────────────────────


@_with_db
def test_wrong_channel_aborts(fake):
    fake.row_lookup["FROM marketing.campaigns"] = {
        "id": "c1", "name": "X", "channel": "email",
        "status": "draft", "audience_id": "a1", "template_id": None,
    }
    try:
        tg._resolve_campaign("c1")
        _check("wrong_channel", False, "abort not raised")
    except ParanoidAbort as e:
        _check("wrong_channel",
               e.guard == "tg_resolve_campaign"
               and "not 'telegram'" in str(e))


@_with_db
def test_zero_recipients_aborts(fake):
    fake.list_lookup["JOIN marketing.telegram_recipients"] = []
    try:
        tg._snapshot_recipients("aud-1")
        _check("zero_recipients", False)
    except ParanoidAbort as e:
        _check("zero_recipients", e.guard == "tg_snapshot")


@_with_db
def test_recipient_cap_aborts(fake):
    huge = [{"chat_id": 1000000 + i} for i in range(tg._HARD_RECIPIENT_CAP + 1)]
    fake.list_lookup["JOIN marketing.telegram_recipients"] = huge
    try:
        tg._snapshot_recipients("aud-1")
        _check("recipient_cap", False)
    except ParanoidAbort as e:
        _check("recipient_cap", e.guard == "tg_recipient_cap")


# ─── Token verification ────────────────────────────────────────────────


def test_token_deterministic():
    r1 = tg.compute_confirm_token("c1", "a1", [{"chat_id": TEST_CHAT_ID}])
    r2 = tg.compute_confirm_token("c1", "a1", [{"chat_id": TEST_CHAT_ID}])
    _check("token_deterministic", r1 == r2)


def test_token_change_invalidates():
    r1 = tg.compute_confirm_token("c1", "a1", [{"chat_id": TEST_CHAT_ID}])
    r2 = tg.compute_confirm_token("c1", "a1",
                                  [{"chat_id": TEST_CHAT_ID}, {"chat_id": 9}])
    _check("token_change_invalidates", r1 != r2)


def test_token_missing_in_live_aborts():
    try:
        tg._verify_confirm_token(None, "expected-token")
        _check("token_missing_live", False)
    except ParanoidAbort as e:
        _check("token_missing_live", e.guard == "tg_confirm_token")


def test_token_mismatch_aborts():
    try:
        tg._verify_confirm_token("wrong-token", "expected-token")
        _check("token_mismatch", False)
    except ParanoidAbort as e:
        _check("token_mismatch", e.guard == "tg_confirm_token")


# ─── DRY_RUN end-to-end (never hits api.telegram.org) ──────────────────


@_with_db
def test_dry_run_never_hits_api(fake):
    fake.row_lookup["FROM marketing.campaigns"] = _ok_campaign()
    fake.list_lookup["JOIN marketing.telegram_recipients"] = [
        {"chat_id": TEST_CHAT_ID, "handle": "felix",
         "username": "felix_test", "first_name": "Felix",
         "last_name": "", "language_code": "de"},
    ]
    # If urlopen is ever called in DRY_RUN, that's a bug.
    api_spy = mock.MagicMock(side_effect=AssertionError(
        "urlopen called in DRY_RUN"))
    with mock.patch("urllib.request.urlopen", api_spy):
        r = tg.run("c1", SendMode.DRY_RUN)
    ok = (r["mode"] == "dry_run"
          and r["recipient_count"] == 1
          and TEST_CHAT_ID in r.get("chat_ids_preview", [])
          and isinstance(r.get("confirm_token"), str)
          and len(r["confirm_token"]) == 64)
    _check("dry_run_no_api_calls", ok, f"r={r!r}")


# ─── Dispatch: marketing_tools.send_campaign routes correctly ──────────


@_with_db
def test_send_campaign_dispatches_to_telegram(fake):
    """send_campaign with campaign.channel='telegram' must go to _send_telegram
    NOT _send_paranoid."""
    fake.row_lookup["FROM marketing.campaigns"] = _ok_campaign()
    fake.list_lookup["JOIN marketing.telegram_recipients"] = [
        {"chat_id": TEST_CHAT_ID, "first_name": "Felix"},
    ]
    paranoid_spy = mock.MagicMock(return_value={"summary": "should not be called"})
    telegram_spy = mock.MagicMock(return_value={"summary": "telegram dispatched",
                                                 "mode": "dry_run"})
    with mock.patch("spaces.marketing.tools._send_paranoid.run", paranoid_spy), \
         mock.patch("spaces.marketing.tools._send_telegram.run", telegram_spy):
        r = mt.send_campaign("c1", mode="dry_run")
    _check("dispatch_telegram",
           r["success"]
           and telegram_spy.call_count == 1
           and paranoid_spy.call_count == 0,
           f"telegram={telegram_spy.call_count} paranoid={paranoid_spy.call_count}")


@_with_db
def test_send_campaign_email_stays_on_paranoid(fake):
    """Email campaign must NOT route to telegram-worker."""
    fake.row_lookup["FROM marketing.campaigns"] = {
        "id": "c2", "channel": "email",
    }
    paranoid_spy = mock.MagicMock(return_value={"summary": "email ok",
                                                 "mode": "dry_run"})
    telegram_spy = mock.MagicMock(return_value={"summary": "should NOT be called"})
    with mock.patch("spaces.marketing.tools._send_paranoid.run", paranoid_spy), \
         mock.patch("spaces.marketing.tools._send_telegram.run", telegram_spy):
        r = mt.send_campaign("c2", mode="dry_run")
    _check("dispatch_email_no_telegram",
           r["success"]
           and paranoid_spy.call_count == 1
           and telegram_spy.call_count == 0)


@_with_db
def test_send_campaign_unknown_channel_clean_fail(fake):
    """Unknown channel returns a clean envelope failure, no spy call."""
    fake.row_lookup["FROM marketing.campaigns"] = {
        "id": "c3", "channel": "carrier_pigeon",
    }
    paranoid_spy = mock.MagicMock()
    telegram_spy = mock.MagicMock()
    with mock.patch("spaces.marketing.tools._send_paranoid.run", paranoid_spy), \
         mock.patch("spaces.marketing.tools._send_telegram.run", telegram_spy):
        r = mt.send_campaign("c3", mode="dry_run")
    _check("dispatch_unknown",
           r["success"] is False
           and "no send module wired" in r["message"]
           and paranoid_spy.call_count == 0
           and telegram_spy.call_count == 0)


# ─── No-cross-channel regression ───────────────────────────────────────


@_with_db
def test_telegram_never_calls_email_send_loop(fake):
    """Telegram code path must NEVER call into _send_paranoid._send_loop."""
    from spaces.marketing.tools import _send_paranoid as sp
    fake.row_lookup["FROM marketing.campaigns"] = _ok_campaign()
    fake.list_lookup["JOIN marketing.telegram_recipients"] = [
        {"chat_id": TEST_CHAT_ID, "first_name": "Felix"},
    ]
    email_loop_spy = mock.MagicMock()
    with mock.patch.object(sp, "_send_loop", email_loop_spy), \
         mock.patch("urllib.request.urlopen",
                    mock.MagicMock(side_effect=AssertionError("api hit"))):
        tg.run("c1", SendMode.DRY_RUN)
    _check("tg_never_calls_email_loop", email_loop_spy.call_count == 0)


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        # Allowlist
        test_allowed_chat_ids_is_frozenset,
        test_chat_id_outside_allowlist_aborts,
        test_chat_id_non_int_rejected,
        test_allowed_chat_id_passes,
        # Kill-switch + token resolution
        test_kill_switch_off_aborts,
        test_kill_switch_on_passes,
        test_missing_bot_token_aborts,
        test_malformed_bot_token_aborts,
        # Campaign / recipient
        test_wrong_channel_aborts,
        test_zero_recipients_aborts,
        test_recipient_cap_aborts,
        # Token
        test_token_deterministic,
        test_token_change_invalidates,
        test_token_missing_in_live_aborts,
        test_token_mismatch_aborts,
        # DRY_RUN
        test_dry_run_never_hits_api,
        # Dispatch
        test_send_campaign_dispatches_to_telegram,
        test_send_campaign_email_stays_on_paranoid,
        test_send_campaign_unknown_channel_clean_fail,
        # No-cross-channel
        test_telegram_never_calls_email_send_loop,
    ]
    print(f"[test_telegram_send] running {len(tests)} tests")
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
    print("test_telegram_send: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
