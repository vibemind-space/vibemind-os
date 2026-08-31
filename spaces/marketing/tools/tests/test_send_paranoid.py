"""Unit tests for the Phase-2 send-worker gates.

All DB + SMTP + Mailcow-API calls are monkeypatched so the suite runs
without docker, supabase, mailcow, or mailpit. The goal is to lock in
the 12 safety gates so a future change that weakens one gate is caught
in CI rather than at SMTP-OPEN time.

Run:
    python -m spaces.marketing.tools.tests.test_send_paranoid

Exit 0 on PASS. Each gate is a separate test; one assertion failure
prints which gate and continues so we see the full pass/fail matrix.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))


from spaces.marketing.tools import _send_paranoid as sp  # noqa: E402


# ─── helpers ────────────────────────────────────────────────────────────


def _fake_campaign(audience_id: str = "aud-1", status: str = "draft") -> dict:
    return {
        "id": "camp-1",
        "name": "real-case-test",
        "channel": "email",
        "status": status,
        "audience_id": audience_id,
        "template_id": "tpl-1",
        "is_loopback": True,
    }


def _fake_recipients(*emails: str) -> list:
    return [{"email": e, "handle": e.split("@")[0], "domain": e.split("@")[1]} for e in emails]


class FakeDB:
    """Stand-in for spaces.marketing.sync._db.

    Records every call. query_one/query_via_docker can be programmed
    via .set_response(); execute_via_docker returns stored stdout.
    """

    def __init__(self):
        self.queries: list[str] = []
        self.executes: list[str] = []
        self._responses: dict[str, object] = {}
        self._default_query = []

    def set(self, key: str, value):
        self._responses[key] = value

    def query_one(self, sql, *a, **k):
        self.queries.append(sql)
        for needle, value in self._responses.items():
            if needle in sql and isinstance(value, dict):
                return value
        return None

    def query_via_docker(self, sql, *a, **k):
        self.queries.append(sql)
        for needle, value in self._responses.items():
            if needle in sql and isinstance(value, list):
                return value
        return self._default_query

    def execute_via_docker(self, sql, *a, **k):
        self.executes.append(sql)
        for needle, value in self._responses.items():
            if needle in sql and isinstance(value, str):
                return value
        return ""

    def _sql_literal(self, v):
        # Mirror real _db._sql_literal for accurate query inspection
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"


# ─── tests ──────────────────────────────────────────────────────────────


_FAILS: list[str] = []


def _check(label: str, cond: bool, detail: str = ""):
    mark = "PASS" if cond else "FAIL"
    line = f"  [{mark}] {label}"
    if detail and not cond:
        line += f"  -- {detail}"
    print(line)
    if not cond:
        _FAILS.append(label)


def with_db(test_fn):
    """Wrapper: every test gets a fresh FakeDB monkeypatched into sp._db."""

    def wrapper():
        fake = FakeDB()
        with mock.patch.object(sp, "_db", fake):
            test_fn(fake)

    wrapper.__name__ = test_fn.__name__
    return wrapper


@with_db
def test_kill_switch_off_aborts_live(fake):
    """Gate 1: LIVE without MARKETING_SEND_ENABLED=true must abort."""
    with mock.patch.dict(os.environ, {sp.KILL_SWITCH_ENV: ""}, clear=False):
        if sp.KILL_SWITCH_ENV in os.environ:
            del os.environ[sp.KILL_SWITCH_ENV]
        try:
            sp._check_kill_switch()
            _check("gate1_kill_switch_off_aborts_live", False, "no abort raised")
        except sp.ParanoidAbort as e:
            _check("gate1_kill_switch_off_aborts_live", e.guard == "kill_switch")


@with_db
def test_kill_switch_on_passes(fake):
    with mock.patch.dict(os.environ, {sp.KILL_SWITCH_ENV: "true"}, clear=False):
        try:
            sp._check_kill_switch()
            _check("gate1_kill_switch_on_passes", True)
        except sp.ParanoidAbort:
            _check("gate1_kill_switch_on_passes", False, "raised unexpectedly")


@with_db
def test_freeze_file_present_aborts(fake):
    """Gate 2: FREEZE file present must abort LIVE."""
    with tempfile.TemporaryDirectory() as td:
        fake_freeze = Path(td) / "FREEZE"
        fake_freeze.write_text("test reason", encoding="utf-8")
        with mock.patch.object(sp, "FREEZE_PATH", fake_freeze):
            try:
                sp._check_freeze()
                _check("gate2_freeze_present_aborts", False)
            except sp.ParanoidAbort as e:
                _check("gate2_freeze_present_aborts", e.guard == "freeze_file")


@with_db
def test_freeze_file_absent_passes(fake):
    with tempfile.TemporaryDirectory() as td:
        fake_freeze = Path(td) / "FREEZE-not-here"
        with mock.patch.object(sp, "FREEZE_PATH", fake_freeze):
            try:
                sp._check_freeze()
                _check("gate2_freeze_absent_passes", True)
            except sp.ParanoidAbort:
                _check("gate2_freeze_absent_passes", False)


@with_db
def test_resolve_campaign_terminal_aborts(fake):
    """Gate 3: campaign in terminal status must abort."""
    fake.set("FROM marketing.campaigns", _fake_campaign(status="sent"))
    try:
        sp._resolve_campaign("camp-1")
        _check("gate3_terminal_status_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate3_terminal_status_aborts",
               e.guard == "resolve_campaign" and "terminal" in str(e))


@with_db
def test_resolve_campaign_not_found_aborts(fake):
    try:
        sp._resolve_campaign("nope")
        _check("gate3_not_found_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate3_not_found_aborts",
               e.guard == "resolve_campaign" and "not found" in str(e))


@with_db
def test_domain_allowlist_external_aborts(fake):
    """Gate 5: external domain must abort."""
    recs = _fake_recipients("felix.test@vibemind.space", "leak@gmail.com")
    try:
        sp._scan_domain_allowlist(recs)
        _check("gate5_external_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate5_external_aborts",
               e.guard == "domain_allowlist" and "gmail.com" in str(e))


@with_db
def test_domain_allowlist_unicode_lookalike_aborts(fake):
    """Gate 5: unicode lookalike vibemínd.space (U+00ED) must abort."""
    recs = _fake_recipients("attacker@vibemínd.space")
    try:
        sp._scan_domain_allowlist(recs)
        _check("gate5_unicode_lookalike_aborts", False,
               "u00ed slipped through allowlist")
    except sp.ParanoidAbort as e:
        _check("gate5_unicode_lookalike_aborts",
               e.guard == "domain_allowlist")


@with_db
def test_domain_allowlist_only_vibemind_passes(fake):
    recs = _fake_recipients("a@vibemind.space", "b@vibemind.space")
    try:
        sp._scan_domain_allowlist(recs)
        _check("gate5_clean_passes", True)
    except sp.ParanoidAbort as e:
        _check("gate5_clean_passes", False, str(e))


@with_db
def test_investor_lockout_finds_locked(fake):
    """Gate 6: defense-in-depth recount catches snuck-in locked rows."""
    fake.set("WHERE email IN", {"n": 1})
    recs = _fake_recipients("snuck@vibemind.space")
    try:
        sp._check_investor_locked(recs)
        _check("gate6_locked_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate6_locked_aborts", e.guard == "investor_lockout")


@with_db
def test_investor_lockout_clean_passes(fake):
    fake.set("WHERE email IN", {"n": 0})
    recs = _fake_recipients("clean@vibemind.space")
    try:
        sp._check_investor_locked(recs)
        _check("gate6_clean_passes", True)
    except sp.ParanoidAbort as e:
        _check("gate6_clean_passes", False, str(e))


def test_confirm_token_deterministic():
    """Gate 7: same inputs -> same token."""
    recs = _fake_recipients("a@vibemind.space", "b@vibemind.space")
    t1 = sp.compute_confirm_token("c1", "a1", recs)
    t2 = sp.compute_confirm_token("c1", "a1", list(reversed(recs)))
    _check("gate7_token_deterministic", t1 == t2)


def test_confirm_token_audience_change_invalidates():
    """Gate 7: adding a member changes the token (anti-TOCTOU)."""
    recs_v1 = _fake_recipients("a@vibemind.space")
    recs_v2 = _fake_recipients("a@vibemind.space", "evil@vibemind.space")
    t1 = sp.compute_confirm_token("c1", "a1", recs_v1)
    t2 = sp.compute_confirm_token("c1", "a1", recs_v2)
    _check("gate7_token_audience_change_invalidates", t1 != t2)


def test_confirm_token_mismatch_aborts():
    """Gate 7: wrong token must abort."""
    try:
        sp._verify_confirm_token("aabbcc...wrong", "ddeeff...right")
        _check("gate7_token_mismatch_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate7_token_mismatch_aborts", e.guard == "confirm_token")


def test_confirm_token_missing_aborts():
    try:
        sp._verify_confirm_token(None, "any")
        _check("gate7_token_missing_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate7_token_missing_aborts", e.guard == "confirm_token")


@with_db
def test_recipient_cap_aborts(fake):
    """Gate 4: snapshot > HARD_RECIPIENT_CAP must abort."""
    huge = [{"email": f"r{i}@vibemind.space"} for i in range(sp.HARD_RECIPIENT_CAP + 1)]
    fake.set("FROM marketing.audience_members", huge)
    try:
        sp._snapshot_recipients("aud-1")
        _check("gate4_recipient_cap_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate4_recipient_cap_aborts", e.guard == "recipient_cap")


@with_db
def test_recipient_empty_aborts(fake):
    """Gate 4: zero reachable recipients must abort."""
    fake.set("FROM marketing.audience_members", [])
    try:
        sp._snapshot_recipients("aud-1")
        _check("gate4_empty_aborts", False)
    except sp.ParanoidAbort as e:
        _check("gate4_empty_aborts", e.guard == "snapshot_recipients")


# ─── Gate 8: SHADOW pre-ping ────────────────────────────────────────────


def test_shadow_preping_port_zero_aborts():
    """Gate 8: SHADOW_PORT<=0 (default) must abort loud with operator help."""
    with mock.patch.object(sp, "SHADOW_PORT", 0):
        try:
            sp._shadow_preping()
            _check("gate8_shadow_port0_aborts", False)
        except sp.ParanoidAbort as e:
            ok = e.guard == "shadow_preping" and "MARKETING_SHADOW_PORT" in str(e)
            _check("gate8_shadow_port0_aborts", ok, str(e))


def test_shadow_preping_unreachable_aborts():
    """Gate 8: configured-but-unreachable SHADOW host must abort."""
    # Pick a port that is almost certainly closed on localhost.
    with mock.patch.object(sp, "SHADOW_HOST", "127.0.0.1"), \
         mock.patch.object(sp, "SHADOW_PORT", 1):
        try:
            sp._shadow_preping()
            _check("gate8_shadow_unreachable_aborts", False)
        except sp.ParanoidAbort as e:
            _check("gate8_shadow_unreachable_aborts",
                   e.guard == "shadow_preping" and "unreachable" in str(e))


def test_shadow_preping_reachable_passes():
    """Gate 8: a reachable target (we open a fake listener) passes."""
    import socket as _s
    srv = _s.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        with mock.patch.object(sp, "SHADOW_HOST", "127.0.0.1"), \
             mock.patch.object(sp, "SHADOW_PORT", port):
            try:
                sp._shadow_preping()
                _check("gate8_shadow_reachable_passes", True)
            except sp.ParanoidAbort as e:
                _check("gate8_shadow_reachable_passes", False, str(e))
    finally:
        srv.close()


# ─── Gate 9: Postfix loopback probe ────────────────────────────────────


class _FakeSMTP:
    """Fake SMTP_SSL context-manager. Programmable RCPT response."""

    def __init__(self, *_args, **_kw):
        self.commands = []
        # default: behave like Postfix loopback-block hitting external
        self._rcpt_code = 554
        self._rcpt_msg = b"LOOPBACK-MODE"

    # context manager
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def set_rcpt_response(self, code, msg=b"ok"):
        self._rcpt_code = code
        self._rcpt_msg = msg

    def login(self, *_):
        self.commands.append(("login",))

    def mail(self, sender):
        self.commands.append(("mail", sender))
        return 250, b"ok"

    def rcpt(self, addr):
        self.commands.append(("rcpt", addr))
        return self._rcpt_code, self._rcpt_msg

    def rset(self):
        self.commands.append(("rset",))

    def data(self, payload):
        self.commands.append(("data", len(payload)))
        return 250, b"ok"

    def quit(self):
        self.commands.append(("quit",))


def test_postfix_probe_554_passes():
    """Gate 9: external rejected with 554 = correct loopback-block."""
    fake_smtp = _FakeSMTP()
    fake_smtp.set_rcpt_response(554, b"LOOPBACK-MODE - external blocked")
    factory = mock.MagicMock(return_value=fake_smtp)
    with mock.patch("smtplib.SMTP_SSL", factory):
        try:
            sp._postfix_loopback_probe("h", 465, "u", "p", "marketing@vibemind.space")
            _check("gate9_probe_554_passes", True)
        except sp.ParanoidAbort as e:
            _check("gate9_probe_554_passes", False, str(e))


def test_postfix_probe_250_writes_freeze_and_aborts():
    """Gate 9: 250 = PCRE BLOCK GONE = write FREEZE + abort."""
    fake_smtp = _FakeSMTP()
    fake_smtp.set_rcpt_response(250)
    factory = mock.MagicMock(return_value=fake_smtp)
    with tempfile.TemporaryDirectory() as td:
        fake_freeze = Path(td) / "FREEZE"
        with mock.patch("smtplib.SMTP_SSL", factory), \
             mock.patch.object(sp, "FREEZE_PATH", fake_freeze):
            try:
                sp._postfix_loopback_probe("h", 465, "u", "p", "marketing@vibemind.space")
                _check("gate9_probe_250_freeze_aborts", False,
                       "250 was accepted, no FREEZE written")
            except sp.ParanoidAbort as e:
                ok = (e.guard == "postfix_probe"
                      and "accepted" in str(e).lower()
                      and fake_freeze.exists())
                _check("gate9_probe_250_freeze_aborts", ok,
                       f"freeze_written={fake_freeze.exists()} guard={e.guard}")


# ─── Gate 10: send-loop atomic claim + SMTP mode-pinning ───────────────


@with_db
def test_resolve_smtp_target_shadow_uses_constants(fake):
    """Gate 10: SHADOW reads pinned constants, NOT env."""
    with mock.patch.object(sp, "SHADOW_HOST", "shadow-pin"), \
         mock.patch.object(sp, "SHADOW_PORT", 9999), \
         mock.patch.dict(os.environ, {"SMTP_HOST": "EVIL", "SMTP_PORT": "1"}, clear=False):
        host, port = sp._resolve_smtp_target(sp.SendMode.SHADOW)
        _check("gate10_shadow_pinned_target",
               host == "shadow-pin" and port == 9999, f"got {host}:{port}")


@with_db
def test_resolve_smtp_target_live_uses_env(fake):
    """Gate 10: LIVE pulls SMTP_HOST/PORT from env."""
    with mock.patch.dict(os.environ, {"SMTP_HOST": "live-host", "SMTP_PORT": "465"},
                         clear=False):
        host, port = sp._resolve_smtp_target(sp.SendMode.LIVE)
        _check("gate10_live_env_target",
               host == "live-host" and port == 465, f"got {host}:{port}")


@with_db
def test_claim_send_rows_filters_status_lines(fake):
    """Gate 10: psql's 'INSERT N M' status line MUST NOT be returned
    as a recipient (regression-guard from the SHADOW-bug commit)."""
    fake.set("RETURNING email",
             "felix.test@vibemind.space\nINSERT 0 1\n")
    recipients = _fake_recipients("felix.test@vibemind.space")
    claimed = sp._claim_send_rows("camp-1", recipients)
    _check("gate10_claim_filters_status",
           claimed == ["felix.test@vibemind.space"],
           f"got {claimed!r}")


@with_db
def test_claim_send_rows_empty_returns_empty(fake):
    """Gate 10: zero claimed (all rows already exist) returns [], not [None]."""
    fake.set("RETURNING email", "")
    recipients = _fake_recipients("a@vibemind.space")
    claimed = sp._claim_send_rows("camp-1", recipients)
    _check("gate10_claim_empty_returns_empty", claimed == [],
           f"got {claimed!r}")


# ─── Gate 11: Mailcow mailq audit ──────────────────────────────────────


def test_mailq_audit_external_recipient_freezes():
    """Gate 11: queue containing an external recipient => FREEZE + abort."""
    fake_resp = mock.MagicMock()
    fake_resp.read.return_value = (
        b'[{"recipients": [{"address": "marketing@vibemind.space"},'
        b' {"address": "evil@gmail.com"}]}]'
    )
    fake_resp.__enter__ = lambda self: self
    fake_resp.__exit__ = lambda *a: False

    with tempfile.TemporaryDirectory() as td:
        fake_freeze = Path(td) / "FREEZE"
        with mock.patch("urllib.request.urlopen", return_value=fake_resp), \
             mock.patch.object(sp, "FREEZE_PATH", fake_freeze), \
             mock.patch.dict(os.environ,
                             {"MAILCOW_API_KEY": "test", "MAILCOW_URL": "https://x"},
                             clear=False):
            try:
                sp._mailq_audit()
                _check("gate11_mailq_external_freezes", False,
                       "external recipient was not flagged")
            except sp.ParanoidAbort as e:
                ok = (e.guard == "mailq_audit"
                      and "evil@gmail.com" in str(e)
                      and fake_freeze.exists())
                _check("gate11_mailq_external_freezes", ok,
                       f"freeze_written={fake_freeze.exists()} guard={e.guard}")


def test_mailq_audit_clean_passes():
    """Gate 11: queue with only @vibemind.space passes silently."""
    fake_resp = mock.MagicMock()
    fake_resp.read.return_value = (
        b'[{"recipients": [{"address": "felix@vibemind.space"}]}]'
    )
    fake_resp.__enter__ = lambda self: self
    fake_resp.__exit__ = lambda *a: False

    with mock.patch("urllib.request.urlopen", return_value=fake_resp), \
         mock.patch.dict(os.environ,
                         {"MAILCOW_API_KEY": "test", "MAILCOW_URL": "https://x"},
                         clear=False):
        try:
            sp._mailq_audit()
            _check("gate11_mailq_clean_passes", True)
        except sp.ParanoidAbort as e:
            _check("gate11_mailq_clean_passes", False, str(e))


def test_mailq_audit_api_fail_freezes():
    """Gate 11: cannot prove queue is clean => FREEZE."""
    with tempfile.TemporaryDirectory() as td:
        fake_freeze = Path(td) / "FREEZE"
        with mock.patch("urllib.request.urlopen",
                        side_effect=OSError("connection refused")), \
             mock.patch.object(sp, "FREEZE_PATH", fake_freeze), \
             mock.patch.dict(os.environ,
                             {"MAILCOW_API_KEY": "test", "MAILCOW_URL": "https://x"},
                             clear=False):
            try:
                sp._mailq_audit()
                _check("gate11_mailq_api_fail_freezes", False)
            except sp.ParanoidAbort as e:
                _check("gate11_mailq_api_fail_freezes",
                       e.guard == "mailq_audit" and fake_freeze.exists())


# ─── Gate 12: status flip ──────────────────────────────────────────────


def test_status_flip_only_after_at_least_one_send():
    """Gate 12: campaign.status flips to 'sent' ONLY when >=1 recipient
    actually got delivered. SHADOW run with 1 claim should issue the
    UPDATE. We assert the SQL string was executed."""
    fake = FakeDB()
    # Campaign + recipients
    fake.set("FROM marketing.campaigns", _fake_campaign())
    fake.set("FROM marketing.audience_members",
             _fake_recipients("felix.test@vibemind.space"))
    fake.set("WHERE email IN", {"n": 0})
    # Claim succeeds for one row
    fake.set("RETURNING email", "felix.test@vibemind.space\n")
    # Gate 4.5: channel_config row for the campaign's channel (email)
    fake.set("FROM marketing.channel_config", {
        "channel": "email", "send_implemented": True,
        "enabled": True, "required_env": [],
        "rate_limit_per_minute": 0,
    })

    # SHADOW pin to a fake listener
    import socket as _s
    srv = _s.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    # Fake SMTP that accepts everything
    fake_smtp = _FakeSMTP()
    fake_smtp.set_rcpt_response(250)
    factory = mock.MagicMock(return_value=fake_smtp)

    try:
        with mock.patch.object(sp, "_db", fake), \
             mock.patch.object(sp, "SHADOW_HOST", "127.0.0.1"), \
             mock.patch.object(sp, "SHADOW_PORT", port), \
             mock.patch.dict(os.environ,
                             {"MARKETING_UNSUB_SECRET": "x" * 40}, clear=False), \
             mock.patch("smtplib.SMTP", factory):
            # Also patch channels._db -- gate 4.5 uses its own _db ref
            from spaces.marketing.tools import channels as ch
            with mock.patch.object(ch, "_db", fake):
                try:
                    r = sp.run("c1", sp.SendMode.SHADOW)
                    flip_executed = any(
                        "UPDATE marketing.campaigns SET status = 'sent'" in s
                        for s in fake.executes
                    )
                    _check("gate12_status_flip_on_success",
                           r.get("result", {}).get("sent", 0) >= 1 and flip_executed,
                           f"sent={r.get('result',{}).get('sent','?')} "
                           f"flip_executed={flip_executed}")
                except sp.ParanoidAbort as e:
                    _check("gate12_status_flip_on_success", False, str(e))
    finally:
        srv.close()


def test_status_no_flip_when_zero_claimed():
    """Gate 12: zero successful sends => NO status flip."""
    fake = FakeDB()
    fake.set("FROM marketing.campaigns", _fake_campaign())
    fake.set("FROM marketing.audience_members",
             _fake_recipients("felix.test@vibemind.space"))
    fake.set("WHERE email IN", {"n": 0})
    # Claim returns nothing (all rows already exist)
    fake.set("RETURNING email", "")
    # Gate 4.5: channel_config row for the campaign's channel (email)
    fake.set("FROM marketing.channel_config", {
        "channel": "email", "send_implemented": True,
        "enabled": True, "required_env": [],
        "rate_limit_per_minute": 0,
    })

    import socket as _s
    srv = _s.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    try:
        with mock.patch.object(sp, "_db", fake), \
             mock.patch.object(sp, "SHADOW_HOST", "127.0.0.1"), \
             mock.patch.object(sp, "SHADOW_PORT", port), \
             mock.patch("smtplib.SMTP", mock.MagicMock(return_value=_FakeSMTP())):
            from spaces.marketing.tools import channels as ch
            with mock.patch.object(ch, "_db", fake):
                try:
                    r = sp.run("c1", sp.SendMode.SHADOW)
                    flip_executed = any(
                        "UPDATE marketing.campaigns SET status = 'sent'" in s
                        for s in fake.executes
                    )
                    _check("gate12_no_flip_when_zero_sent",
                           r.get("result", {}).get("sent", 0) == 0 and not flip_executed,
                           f"sent={r.get('result',{}).get('sent','?')} "
                           f"flip_executed={flip_executed}")
                except sp.ParanoidAbort as e:
                    _check("gate12_no_flip_when_zero_sent", False, str(e))
    finally:
        srv.close()


# ─── Gate 4.5: channel-configured-check ────────────────────────────────


def test_gate_4_5_aborts_on_unimplemented_channel():
    """Gate 4.5: campaign.channel where send_implemented=false must abort."""
    from spaces.marketing.tools import channels as ch
    fake = FakeDB()
    fake.set("FROM marketing.campaigns",
             _fake_campaign())  # default channel='email'
    # channel row says NOT implemented
    fake.set("FROM marketing.channel_config", {
        "channel": "email",
        "send_implemented": False,
        "enabled": False,
        "required_env": [],
    })
    fake.set("FROM marketing.audience_members",
             _fake_recipients("felix.test@vibemind.space"))
    fake.set("WHERE email IN", {"n": 0})

    import socket as _s
    srv = _s.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        with mock.patch.object(sp, "_db", fake), \
             mock.patch.object(ch, "_db", fake), \
             mock.patch.object(sp, "SHADOW_HOST", "127.0.0.1"), \
             mock.patch.object(sp, "SHADOW_PORT", port), \
             mock.patch("smtplib.SMTP", mock.MagicMock(return_value=_FakeSMTP())):
            try:
                sp.run("c1", sp.SendMode.SHADOW)
                _check("gate_4_5_aborts_unimplemented", False,
                       "ParanoidAbort not raised")
            except sp.ParanoidAbort as e:
                _check("gate_4_5_aborts_unimplemented",
                       e.guard == "channel_not_implemented")
    finally:
        srv.close()


# ─── merge_render (template safety) ────────────────────────────────────


def test_merge_basic_substitution():
    r = sp.merge_render("Hi {{first_name}}!", {"first_name": "Felix"})
    _check("merge_basic_substitution", r == "Hi Felix!")


def test_merge_unknown_field_raises():
    try:
        sp.merge_render("Hi {{unknown_field}}", {"unknown_field": "x"})
        _check("merge_unknown_field_raises", False, "ValueError not raised")
    except ValueError as e:
        _check("merge_unknown_field_raises",
               "unknown merge field" in str(e))


def test_merge_html_escapes_values():
    """When the template contains '<' (= HTML), substituted values are
    HTML-escaped. Defeats injection via Hand-supplied display_name."""
    r = sp.merge_render(
        "<p>Hi {{first_name}}</p>",
        {"first_name": "<script>alert(1)</script>"},
    )
    ok = ("&lt;script&gt;" in r and "<script>" not in r
          and "<p>" in r)
    _check("merge_html_escapes_values", ok, f"r={r!r}")


def test_merge_plaintext_does_not_escape():
    """Plain-text template (no '<') leaves values raw -- escaping would
    look like garbage in a plain-text mail."""
    r = sp.merge_render("Hi {{first_name}}", {"first_name": "O'Brien"})
    _check("merge_plaintext_no_escape", r == "Hi O'Brien")


def test_merge_missing_value_substitutes_empty():
    """Allowlisted field but value missing -> empty string, not error.
    (Bad data is operationally common; unknown FIELDS are the real bug.)"""
    r = sp.merge_render("Hi {{first_name}}!", {"first_name": None})
    _check("merge_missing_substitutes_empty", r == "Hi !")


def test_dry_run_top_level_returns_token_and_no_smtp():
    """End-to-end: DRY_RUN never opens SMTP, returns confirm_token."""
    fake = FakeDB()
    fake.set("FROM marketing.campaigns", _fake_campaign())
    fake.set("FROM marketing.audience_members",
             _fake_recipients("felix.test@vibemind.space"))
    fake.set("WHERE email IN", {"n": 0})

    # If SMTP_SSL is ever called in DRY_RUN, that's a bug.
    smtp_open = mock.MagicMock(side_effect=AssertionError("SMTP opened in DRY_RUN"))
    with mock.patch.object(sp, "_db", fake), \
         mock.patch("smtplib.SMTP_SSL", smtp_open), \
         mock.patch("smtplib.SMTP", smtp_open):
        try:
            r = sp.run("c1", sp.SendMode.DRY_RUN)
            ok = (
                r.get("mode") == "dry_run"
                and r.get("recipient_count") == 1
                and isinstance(r.get("confirm_token"), str)
                and len(r["confirm_token"]) == 64
            )
            _check("end_to_end_dry_run_returns_token", ok,
                   f"got {r!r}")
        except sp.ParanoidAbort as e:
            _check("end_to_end_dry_run_returns_token", False, str(e))


# ─── runner ─────────────────────────────────────────────────────────────


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    tests = [
        test_kill_switch_off_aborts_live,
        test_kill_switch_on_passes,
        test_freeze_file_present_aborts,
        test_freeze_file_absent_passes,
        test_resolve_campaign_terminal_aborts,
        test_resolve_campaign_not_found_aborts,
        test_recipient_cap_aborts,
        test_recipient_empty_aborts,
        test_domain_allowlist_external_aborts,
        test_domain_allowlist_unicode_lookalike_aborts,
        test_domain_allowlist_only_vibemind_passes,
        test_investor_lockout_finds_locked,
        test_investor_lockout_clean_passes,
        test_confirm_token_deterministic,
        test_confirm_token_audience_change_invalidates,
        test_confirm_token_mismatch_aborts,
        test_confirm_token_missing_aborts,
        # Gates 8-12 (added in coverage push 2026-06-03)
        test_shadow_preping_port_zero_aborts,
        test_shadow_preping_unreachable_aborts,
        test_shadow_preping_reachable_passes,
        test_postfix_probe_554_passes,
        test_postfix_probe_250_writes_freeze_and_aborts,
        test_resolve_smtp_target_shadow_uses_constants,
        test_resolve_smtp_target_live_uses_env,
        test_claim_send_rows_filters_status_lines,
        test_claim_send_rows_empty_returns_empty,
        test_mailq_audit_external_recipient_freezes,
        test_mailq_audit_clean_passes,
        test_mailq_audit_api_fail_freezes,
        test_status_flip_only_after_at_least_one_send,
        test_status_no_flip_when_zero_claimed,
        # Gate 4.5 channel-configured
        test_gate_4_5_aborts_on_unimplemented_channel,
        # merge_render (template safety)
        test_merge_basic_substitution,
        test_merge_unknown_field_raises,
        test_merge_html_escapes_values,
        test_merge_plaintext_does_not_escape,
        test_merge_missing_value_substitutes_empty,
        # End-to-end
        test_dry_run_top_level_returns_token_and_no_smtp,
    ]

    print(f"[test_send_paranoid] running {len(tests)} tests")
    for t in tests:
        try:
            t()
        except Exception as e:
            _check(t.__name__, False, f"raised {type(e).__name__}: {e}")

    total = len(tests)
    fails = len(_FAILS)
    print(f"\n=== {total - fails}/{total} passed ===")
    if fails:
        print("FAILED:")
        for f in _FAILS:
            print(f"  - {f}")
        return 1
    print("test_send_paranoid: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
