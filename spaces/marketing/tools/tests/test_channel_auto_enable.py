"""Tests for channel auto-detection + opt-in auto-enable.

Mocks _db so the suite runs without supabase. Verifies:
  detect_channel_readiness:
    - env-present -> env_present=true, ready=true when enabled=true
    - env-missing -> env_present=false, missing_env populated
    - send_implemented=false -> never ready regardless of env
    - could_auto_enable iff send_implemented+env_present+not-enabled
  auto_enable_ready_channels:
    - refuses without MARKETING_AUTO_ENABLE_CHANNELS env
    - dry_run lists candidates without writing
    - writes UPDATE for each eligible row
    - audit row written on success
    - never_calls_send_campaign regression-spy
    - send_implemented=false never auto-flipped to true
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))


from spaces.marketing.tools import channels as ch  # noqa: E402
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
        self.list_lookup: dict[str, list] = {}
        self.row_lookup: dict[str, dict] = {}

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
             mock.patch.object(mt, "_db", fake):
            fn(fake)
    wrapper.__name__ = fn.__name__
    return wrapper


# ─── detect_channel_readiness ──────────────────────────────────────────


@_with_db
def test_detect_env_present_ready(fake):
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "email", "label": "Email",
        "send_implemented": True, "enabled": True,
        "required_env": ["SMTP_HOST"], "openfang_adapter": "email.rs",
    }]
    with mock.patch.dict(os.environ, {"SMTP_HOST": "127.0.0.1"}, clear=False):
        r = ch.detect_channel_readiness()
    c = r["data"]["channels"][0]
    _check("detect_env_present_ready",
           c["env_present"] is True
           and c["ready"] is True
           and c["could_auto_enable"] is False)


@_with_db
def test_detect_env_missing_lists_keys(fake):
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "telegram", "send_implemented": True,
        "enabled": False,
        "required_env": ["TELEGRAM_BOT_TOKEN"],
    }]
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        r = ch.detect_channel_readiness()
    c = r["data"]["channels"][0]
    _check("detect_env_missing",
           c["env_present"] is False
           and "TELEGRAM_BOT_TOKEN" in c["missing_env"]
           and c["ready"] is False
           and c["could_auto_enable"] is False)


@_with_db
def test_detect_implemented_env_present_could_auto_enable(fake):
    """The interesting state: ready to flip but not yet flipped."""
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "telegram", "send_implemented": True,
        "enabled": False,
        "required_env": ["TELEGRAM_BOT_TOKEN"],
    }]
    with mock.patch.dict(os.environ,
                         {"TELEGRAM_BOT_TOKEN": "123:abc"}, clear=False):
        r = ch.detect_channel_readiness()
    c = r["data"]["channels"][0]
    _check("detect_could_auto_enable",
           c["env_present"] is True
           and c["enabled"] is False
           and c["could_auto_enable"] is True
           and c["ready"] is False)


@_with_db
def test_detect_unimplemented_never_ready(fake):
    """send_implemented=false MUST stay non-ready even with env present."""
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "slack", "send_implemented": False,
        "enabled": True,                   # operator could set this in error
        "required_env": ["SLACK_BOT_TOKEN"],
    }]
    with mock.patch.dict(os.environ,
                         {"SLACK_BOT_TOKEN": "xoxb-fake"}, clear=False):
        r = ch.detect_channel_readiness()
    c = r["data"]["channels"][0]
    _check("detect_unimplemented_never_ready",
           c["send_implemented"] is False
           and c["ready"] is False
           and c["could_auto_enable"] is False)


@_with_db
def test_detect_summary_counts(fake):
    """Summary aggregates correctly."""
    fake.list_lookup["FROM marketing.channel_config"] = [
        {"channel": "email", "send_implemented": True, "enabled": True,
         "required_env": ["SMTP_HOST"]},
        {"channel": "telegram", "send_implemented": True, "enabled": False,
         "required_env": ["TELEGRAM_BOT_TOKEN"]},
        {"channel": "slack", "send_implemented": False, "enabled": False,
         "required_env": ["SLACK_BOT_TOKEN"]},
    ]
    with mock.patch.dict(os.environ, {
        "SMTP_HOST": "x", "TELEGRAM_BOT_TOKEN": "y",
    }, clear=False):
        os.environ.pop("SLACK_BOT_TOKEN", None)
        r = ch.detect_channel_readiness()
    s = r["data"]["summary"]
    _check("detect_summary",
           s["channels_total"] == 3
           and s["channels_ready"] == 1            # only email
           and s["channels_could_auto_enable"] == 1,  # only telegram
           f"summary={s}")


# ─── auto_enable_ready_channels ────────────────────────────────────────


@_with_db
def test_auto_enable_refused_without_env(fake):
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MARKETING_AUTO_ENABLE_CHANNELS", None)
        r = ch.auto_enable_ready_channels()
    no_update = not any("UPDATE marketing.channel_config" in s
                        for s in fake.executes)
    _check("auto_enable_refused_no_env",
           r["success"] is False
           and "must equal 'true'" in r["message"]
           and no_update)


@_with_db
def test_auto_enable_dry_run_no_writes(fake):
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "telegram", "send_implemented": True,
        "enabled": False,
        "required_env": ["TELEGRAM_BOT_TOKEN"],
    }]
    with mock.patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "MARKETING_AUTO_ENABLE_CHANNELS": "true",
    }, clear=False):
        r = ch.auto_enable_ready_channels(dry_run=True)
    no_update = not any("UPDATE marketing.channel_config" in s
                        for s in fake.executes)
    _check("auto_enable_dry_run_no_writes",
           r["success"]
           and r["data"]["enabled_count"] == 1
           and r["data"]["dry_run"] is True
           and no_update
           and "DRY RUN" in r["message"])


@_with_db
def test_auto_enable_live_writes_update(fake):
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "telegram", "send_implemented": True,
        "enabled": False,
        "required_env": ["TELEGRAM_BOT_TOKEN"],
    }]
    with mock.patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "MARKETING_AUTO_ENABLE_CHANNELS": "true",
    }, clear=False):
        r = ch.auto_enable_ready_channels(dry_run=False)
    # Should be exactly one UPDATE (for telegram) + one audit_log INSERT
    updates = [s for s in fake.executes if "UPDATE marketing.channel_config" in s]
    audit_writes = [s for s in fake.executes if "audit_log" in s]
    _check("auto_enable_live_writes",
           r["success"]
           and r["data"]["enabled_count"] == 1
           and len(updates) == 1
           and len(audit_writes) == 1
           and "WHERE channel = 'telegram'" in updates[0]
           and "send_implemented = true" in updates[0],  # guard in WHERE
           f"updates={len(updates)} audits={len(audit_writes)}")


@_with_db
def test_auto_enable_skips_unimplemented(fake):
    """send_implemented=false MUST never be auto-enabled, even if env is present."""
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "slack", "send_implemented": False,
        "enabled": False,
        "required_env": ["SLACK_BOT_TOKEN"],
    }]
    with mock.patch.dict(os.environ, {
        "SLACK_BOT_TOKEN": "x",
        "MARKETING_AUTO_ENABLE_CHANNELS": "true",
    }, clear=False):
        r = ch.auto_enable_ready_channels()
    no_update = not any("UPDATE marketing.channel_config" in s
                        for s in fake.executes)
    _check("auto_enable_skips_unimplemented",
           r["data"]["enabled_count"] == 0 and no_update)


@_with_db
def test_auto_enable_idempotent_skips_already_enabled(fake):
    """A channel already enabled=true is NOT touched again."""
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "email", "send_implemented": True,
        "enabled": True,                   # already on
        "required_env": ["SMTP_HOST"],
    }]
    with mock.patch.dict(os.environ, {
        "SMTP_HOST": "127.0.0.1",
        "MARKETING_AUTO_ENABLE_CHANNELS": "true",
    }, clear=False):
        r = ch.auto_enable_ready_channels()
    no_update = not any("UPDATE marketing.channel_config" in s
                        for s in fake.executes)
    _check("auto_enable_idempotent",
           r["data"]["enabled_count"] == 0 and no_update)


@_with_db
def test_auto_enable_never_flips_send_implemented(fake):
    """Defense-in-depth: even if a future bug added send_implemented to
    the UPDATE SET clause, the WHERE-guard `send_implemented = true`
    means a channel with send_implemented=false is never matched."""
    fake.list_lookup["FROM marketing.channel_config"] = []
    with mock.patch.dict(os.environ,
                         {"MARKETING_AUTO_ENABLE_CHANNELS": "true"},
                         clear=False):
        ch.auto_enable_ready_channels()
    # Inspect ALL execute strings: none should ever set send_implemented
    set_implemented = [s for s in fake.executes
                       if "SET send_implemented" in s
                       or "SET\\nsend_implemented" in s]
    _check("auto_enable_never_flips_send_implemented",
           len(set_implemented) == 0,
           f"unexpected SETs: {set_implemented}")


# ─── No-send-path regression ───────────────────────────────────────────


@_with_db
def test_auto_enable_never_calls_send_campaign(fake):
    fake.list_lookup["FROM marketing.channel_config"] = [{
        "channel": "telegram", "send_implemented": True,
        "enabled": False,
        "required_env": ["TELEGRAM_BOT_TOKEN"],
    }]
    with mock.patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "MARKETING_AUTO_ENABLE_CHANNELS": "true",
    }, clear=False), mock.patch.object(mt, "send_campaign") as send_spy:
        ch.auto_enable_ready_channels()
    _check("auto_enable_never_calls_send",
           send_spy.call_count == 0)


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        test_detect_env_present_ready,
        test_detect_env_missing_lists_keys,
        test_detect_implemented_env_present_could_auto_enable,
        test_detect_unimplemented_never_ready,
        test_detect_summary_counts,
        test_auto_enable_refused_without_env,
        test_auto_enable_dry_run_no_writes,
        test_auto_enable_live_writes_update,
        test_auto_enable_skips_unimplemented,
        test_auto_enable_idempotent_skips_already_enabled,
        test_auto_enable_never_flips_send_implemented,
        test_auto_enable_never_calls_send_campaign,
    ]
    print(f"[test_channel_auto_enable] running {len(tests)} tests")
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
    print("test_channel_auto_enable: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
