"""End-to-end real-case loopback smoke for the marketing pipeline.

5 steps:
  1. Mailcow mailbox felix.test@vibemind.space (idempotent, password persisted
     to .env under MARKETING_TEST_PASS).
  2. marketing.accounts + marketing.emails inserts (idempotent).
  3. marketing.audiences + marketing.audience_members (idempotent by name).
  4. SMTP send marketing@vibemind.space -> felix.test@vibemind.space.
     NO row written to marketing.campaign_sends -> trg_flip_investor_sent
     is intentionally NOT exercised (out-of-scope per task constraints).
  5. IMAP verify in felix.test INBOX.
  5b. Optional: worker_imap_sync --once -> marketing.inbound_messages.

Stdlib-only + spaces.marketing.sync._db (docker-exec psql). No new
migrations. No edits to existing files (except this script). Idempotent.

Note: this smoke does NOT INSERT marketing.campaign_sends -- the sticky
lockout (investor_already_sent) is verified to stay false before/after.
"""
from __future__ import annotations

import argparse
import imaplib
import json
import os
import re
import secrets
import smtplib
import ssl
import string
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from pathlib import Path

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
# Fail loud + early if the script ever moves and we mis-resolve the root.
assert (REPO_ROOT / "spaces" / "marketing" / "sync" / "_db.py").exists(), (
    f"REPO_ROOT mis-detected: {REPO_ROOT}"
)

ENV_PATH = REPO_ROOT / ".env"
DOMAIN = "vibemind.space"
TEST_LOCAL = "felix.test"
TEST_EMAIL = f"{TEST_LOCAL}@{DOMAIN}"
TEST_HANDLE = "real-case-test"
TEST_SOURCE = "real-case-test"
AUDIENCE_NAME = "real-case-test"
ENV_PW_KEY = "MARKETING_TEST_PASS"
MARKER_TAG = "real-case-test"


# ─── .env helpers ────────────────────────────────────────────────────────


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text("utf-8", errors="replace").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def env_upsert(key: str, value: str) -> None:
    """Atomic idempotent upsert of a single .env line."""
    txt = ENV_PATH.read_text("utf-8") if ENV_PATH.exists() else ""
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pat.search(txt):
        txt = pat.sub(new_line, txt)
    else:
        if txt and not txt.endswith("\n"):
            txt += "\n"
        txt += new_line + "\n"
    tmp = ENV_PATH.with_suffix(".env.tmp")
    tmp.write_text(txt, "utf-8")
    tmp.replace(ENV_PATH)


def gen_password(n: int = 24) -> str:
    alpha = string.ascii_letters + string.digits + "._+-"
    return "".join(secrets.choice(alpha) for _ in range(n))


# ─── STEP 1 — Mailcow mailbox ────────────────────────────────────────────


def ensure_mailbox() -> str:
    mailcow_url = os.environ.get("MAILCOW_URL", "https://127.0.0.1:8443")
    api_key = os.environ["MAILCOW_API_KEY"]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def call(method: str, path: str, payload=None):
        data = json.dumps(payload).encode() if payload else None
        hdrs = {"X-API-Key": api_key, **({"Content-Type": "application/json"} if data else {})}
        req = urllib.request.Request(mailcow_url + path, data=data, method=method, headers=hdrs)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            body = r.read()
            return json.loads(body) if body else {}

    def ok(resp):
        items = resp if isinstance(resp, list) else [resp]
        for it in items:
            if isinstance(it, dict) and it.get("type") == "danger":
                return False, ", ".join(str(p) for p in it.get("msg", []))
        return True, "ok"

    existing = call("GET", "/api/v1/get/mailbox/all") or []
    usernames = {e.get("username", "") for e in existing if isinstance(e, dict)}
    pw = os.environ.get(ENV_PW_KEY)

    if TEST_EMAIL in usernames:
        if pw:
            return pw
        # Mailbox exists but we lost the pw — rotate via /edit/mailbox.
        pw = gen_password()
        resp = call(
            "POST",
            "/api/v1/edit/mailbox",
            {"items": [TEST_EMAIL], "attr": {"password": pw, "password2": pw, "force_pw_update": "0"}},
        )
        good, msg = ok(resp)
        if not good:
            raise RuntimeError(f"Mailcow rotate failed: {msg}")
    else:
        pw = gen_password()
        resp = call(
            "POST",
            "/api/v1/add/mailbox",
            {
                "local_part": TEST_LOCAL,
                "domain": DOMAIN,
                "name": "Felix Test (real-case)",
                "quota": 50,
                "password": pw,
                "password2": pw,
                "active": 1,
                "force_pw_update": 0,
                "tls_enforce_in": 1,
                "tls_enforce_out": 1,
            },
        )
        good, msg = ok(resp)
        if not good:
            raise RuntimeError(f"Mailcow create failed: {msg}")

    env_upsert(ENV_PW_KEY, pw)
    os.environ[ENV_PW_KEY] = pw
    return pw


# ─── STEP 2+3 — DB rows ─────────────────────────────────────────────────


def ensure_db_rows() -> None:
    sys.path.insert(0, str(PKG_ROOT))
    from spaces.marketing.sync import _db  # noqa: E402

    # DO NOT parameterize TEST_HANDLE / TEST_EMAIL / AUDIENCE_NAME via argparse
    # without switching to _db._sql_literal() -- constants only for now.
    sql = f"""
DO $$
DECLARE
  v_aud_id uuid;
BEGIN
  INSERT INTO marketing.accounts (handle, display_name, source, niche)
  VALUES ('{TEST_HANDLE}', 'Felix Test (real-case)', '{TEST_SOURCE}', 'internal-test')
  ON CONFLICT (handle) DO NOTHING;

  INSERT INTO marketing.emails
    (email, handle, smtp_valid, mx_valid, confidence, domain, country, strategy_id, investor_already_sent)
  VALUES
    ('{TEST_EMAIL}', '{TEST_HANDLE}', 1, true, 1.0, '{DOMAIN}', 'XX', '{TEST_SOURCE}', false)
  ON CONFLICT (email) DO UPDATE
    SET smtp_valid = 1, mx_valid = true, handle = EXCLUDED.handle;

  SELECT id INTO v_aud_id FROM marketing.audiences WHERE name = '{AUDIENCE_NAME}' LIMIT 1;
  IF v_aud_id IS NULL THEN
    INSERT INTO marketing.audiences (name, description, filter_dsl)
    VALUES ('{AUDIENCE_NAME}', 'Real-case end-to-end smoke audience',
            jsonb_build_object('source','{TEST_SOURCE}'))
    RETURNING id INTO v_aud_id;
  END IF;

  INSERT INTO marketing.audience_members (audience_id, email)
  VALUES (v_aud_id, '{TEST_EMAIL}')
  ON CONFLICT (audience_id, email) DO NOTHING;
END $$;
"""
    _db.execute_via_docker(sql)

    row = _db.query_one(
        f"SELECT 1 AS ok FROM marketing.emails e "
        f"JOIN marketing.audience_members am ON am.email = e.email "
        f"JOIN marketing.audiences a ON a.id = am.audience_id "
        f"WHERE e.email = '{TEST_EMAIL}' AND a.name = '{AUDIENCE_NAME}'"
    )
    if not row:
        raise RuntimeError("DB sanity check failed: rows not joinable")


def lockout_count() -> int:
    sys.path.insert(0, str(PKG_ROOT))
    from spaces.marketing.sync import _db  # noqa: E402
    row = _db.query_one(
        "SELECT COUNT(*) AS n FROM marketing.emails WHERE investor_already_sent = true"
    )
    return int(row["n"]) if row else 0


# ─── Migration-007 helpers (--with-send-row) ────────────────────────────


def ensure_campaign_for_send_row() -> str:
    """Idempotent: create a campaigns row for the real-case-test audience.

    Returns its UUID. Uses status='sending' so it never trips the
    scheduled-campaign partial index.
    """
    sys.path.insert(0, str(PKG_ROOT))
    from spaces.marketing.sync import _db  # noqa: E402

    # Template + audience prerequisites (idempotent inserts)
    _db.execute_via_docker(
        "INSERT INTO marketing.templates (name, channel, subject, body_text) "
        "VALUES ('real-case-test', 'email', 'real-case smoke', 'smoke') "
        "ON CONFLICT DO NOTHING"
    )
    # Campaign needs audience_id + template_id resolved -- audience was
    # already created by ensure_db_rows() above.
    sql = (
        "INSERT INTO marketing.campaigns (name, channel, status, is_loopback, "
        "                                 audience_id, template_id) "
        "SELECT 'real-case-test', 'email', 'sending', true, "
        "       (SELECT id FROM marketing.audiences WHERE name = 'real-case-test' LIMIT 1), "
        "       (SELECT id FROM marketing.templates WHERE name = 'real-case-test' LIMIT 1) "
        "WHERE NOT EXISTS (SELECT 1 FROM marketing.campaigns WHERE name = 'real-case-test')"
    )
    _db.execute_via_docker(sql)
    row = _db.query_one(
        "SELECT id::text AS id FROM marketing.campaigns "
        "WHERE name = 'real-case-test' LIMIT 1"
    )
    if not row:
        raise RuntimeError("could not resolve real-case-test campaign id")
    return row["id"]


def insert_send_row(campaign_id: str, msgid_core: str) -> None:
    """Insert campaign_sends with message_id matching the outbound mail.

    delivered_at is left NULL so trg_flip_investor_sent does NOT fire --
    investor_already_sent stays false for TEST_EMAIL.
    """
    sys.path.insert(0, str(PKG_ROOT))
    from spaces.marketing.sync import _db  # noqa: E402
    msgid_stored = f"{msgid_core}@{DOMAIN}"   # no angle brackets
    sql = (
        f"INSERT INTO marketing.campaign_sends "
        f"(campaign_id, email, sent_at, message_id) "
        f"VALUES ({_db._sql_literal(campaign_id)}, "
        f"        {_db._sql_literal(TEST_EMAIL)}, "
        f"        now(), "
        f"        {_db._sql_literal(msgid_stored)})"
    )
    _db.execute_via_docker(sql)


def smtp_send_reply(parent_core: str) -> str:
    """SMTP-send a reply pointing at the previous test mail."""
    host = os.environ.get("SMTP_HOST", "127.0.0.1")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    sender = os.environ.get("SMTP_FROM", user)

    msgid_core = f"realcase-reply-{int(time.time())}-{secrets.token_hex(4)}"
    msgid_full = f"<{msgid_core}@{DOMAIN}>"
    parent_full = f"<{parent_core}@{DOMAIN}>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Re: [real-case-test] Loopback smoke {parent_core}"
    msg["From"] = formataddr(("VibeMind Marketing (real-case)", sender))
    msg["To"] = formataddr(("Felix Test", TEST_EMAIL))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msgid_full
    msg["In-Reply-To"] = parent_full
    msg["References"] = parent_full
    msg["X-VibeMind-RealCaseTest"] = MARKER_TAG
    msg.attach(MIMEText(f"Reply to {parent_core}\n", "plain", "utf-8"))

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
        s.login(user, pw)
        s.sendmail(sender, [TEST_EMAIL], msg.as_string())

    return msgid_core


def verify_reply_linked(parent_core: str, reply_core: str,
                       retries: int = 8, sleep_s: float = 1.5) -> bool:
    """Poll DB until inbound_messages.linked_send_id is populated by 007 trigger."""
    sys.path.insert(0, str(PKG_ROOT))
    from spaces.marketing.sync import _db  # noqa: E402
    parent_stored = f"{parent_core}@{DOMAIN}"
    reply_stored = f"{reply_core}@{DOMAIN}"
    for _ in range(retries):
        row = _db.query_one(
            f"SELECT im.linked_send_id::text AS sid, "
            f"       cs.replied_at::text AS replied_at, "
            f"       cs.message_id AS send_msgid "
            f"FROM marketing.inbound_messages im "
            f"LEFT JOIN marketing.campaign_sends cs "
            f"  ON cs.id = im.linked_send_id "
            f"WHERE im.message_id = {_db._sql_literal(reply_stored)} "
            f"  AND im.in_reply_to = {_db._sql_literal(parent_stored)} "
            f"LIMIT 1"
        )
        if row and row.get("sid") and row.get("replied_at"):
            return True
        time.sleep(sleep_s)
    return False


# ─── STEP 4 — SMTP send ─────────────────────────────────────────────────


def smtp_send() -> str:
    host = os.environ.get("SMTP_HOST", "127.0.0.1")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    sender = os.environ.get("SMTP_FROM", user)

    msgid_core = f"realcase-{int(time.time())}-{secrets.token_hex(4)}"
    msgid_full = f"<{msgid_core}@{DOMAIN}>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[real-case-test] Loopback smoke {msgid_core}"
    msg["From"] = formataddr(("VibeMind Marketing (real-case)", sender))
    msg["To"] = formataddr(("Felix Test", TEST_EMAIL))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msgid_full
    msg["X-VibeMind-RealCaseTest"] = MARKER_TAG
    msg.attach(
        MIMEText(
            f"Real-case test - id={msgid_core}\nIf you see this, loopback works.\n",
            "plain",
            "utf-8",
        )
    )
    msg.attach(
        MIMEText(
            f"<p>Real-case test <code>{msgid_core}</code></p>"
            "<p>If you see this, loopback works.</p>",
            "html",
            "utf-8",
        )
    )

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
        s.login(user, pw)
        s.sendmail(sender, [TEST_EMAIL], msg.as_string())

    return msgid_core


# ─── STEP 5 — IMAP verify ───────────────────────────────────────────────


def imap_verify(msgid_core: str, retries: int = 8, sleep_s: float = 1.5) -> bool:
    host = os.environ.get("MARKETING_IMAP_HOST", "127.0.0.1")
    port = int(os.environ.get("MARKETING_IMAP_PORT", "993"))
    pw = os.environ[ENV_PW_KEY]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    full_msgid = f"<{msgid_core}@{DOMAIN}>"
    subject_marker = f"[real-case-test] Loopback smoke {msgid_core}"

    for attempt in range(retries):
        try:
            conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=15)
            conn.login(TEST_EMAIL, pw)
            conn.select("INBOX", readonly=True)
            typ, data = conn.search(None, "HEADER", "Message-ID", full_msgid)
            hit = typ == "OK" and data and data[0].split()
            if not hit:
                # Some servers don't index Message-ID for HEADER search; fall
                # back to Subject (msgid_core is collision-free per run).
                typ, data = conn.search(None, "HEADER", "Subject", subject_marker)
                hit = typ == "OK" and data and data[0].split()
            conn.logout()
            if hit:
                return True
        except Exception as e:
            print(f"  [imap retry {attempt + 1}/{retries}] {e}", file=sys.stderr)
        time.sleep(sleep_s)
    return False


# ─── STEP 5b — Worker --once probe ─────────────────────────────────────


def worker_once_probe(msgid_core: str) -> bool | None:
    env = os.environ.copy()
    extra = f"{TEST_EMAIL},marketing@{DOMAIN},noreply@{DOMAIN}"
    env["MARKETING_IMAP_MAILBOXES"] = extra
    # PRIMARY env-name the worker reads: localpart.upper() == 'FELIX.TEST'.
    # On Windows Python the dotted env-name survives subprocess.run(env=…)
    # via CreateProcess's env-block; verified empirically.
    env["MARKETING_IMAP_PASS_FELIX.TEST"] = os.environ[ENV_PW_KEY]
    env["MARKETING_IMAP_PASS_FELIX_TEST"] = os.environ[ENV_PW_KEY]
    env["PYTHONIOENCODING"] = "utf-8"

    # Isolated UID-state per probe — guarantees last_uid=0 every run so the
    # worker never silently skips a fresh test mail.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        tf.write("{}")
        state_path = tf.name
    try:
        env["MARKETING_IMAP_STATE"] = state_path
        res = subprocess.run(
            [sys.executable, "-m", "spaces.marketing.sync.worker_imap_sync", "--once"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        try:
            os.unlink(state_path)
        except OSError:
            pass

    sys.path.insert(0, str(PKG_ROOT))
    from spaces.marketing.sync import _db  # noqa: E402
    # Worker C strips angle brackets before storing (see worker_imap_sync
    # line ~354: msg_id.strip("<>")). Canonical stored form: 'core@DOMAIN'.
    row = _db.query_one(
        f"SELECT 1 AS ok FROM marketing.inbound_messages "
        f"WHERE message_id = '{msgid_core}@{DOMAIN}' LIMIT 1"
    )

    # Always surface worker output on failure (incl. rc=0 but no row found).
    if not row:
        print(f"--- worker rc={res.returncode} ---", file=sys.stderr)
        print("--- worker stdout ---", file=sys.stderr)
        print(res.stdout, file=sys.stderr)
        print("--- worker stderr ---", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
    elif res.returncode != 0 or "no password resolvable" in (res.stdout + res.stderr):
        print(f"--- worker WARN rc={res.returncode} ---", file=sys.stderr)
        print(res.stdout, file=sys.stderr)
        print(res.stderr, file=sys.stderr)

    return bool(row)


# ─── main ───────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-worker", action="store_true",
                   help="skip worker_imap_sync --once probe (step 5b)")
    p.add_argument("--with-send-row", action="store_true",
                   help="also insert marketing.campaign_sends with the outbound "
                        "message_id, send a reply mail, and verify the 007 "
                        "trigger auto-populates linked_send_id + replied_at "
                        "(end-to-end pipeline test). delivered_at stays NULL so "
                        "the sticky-lockout invariant continues to hold.")
    args = p.parse_args(argv)

    load_env()

    locked_before = lockout_count()
    print(f"[pre ] investor_already_sent locked rows = {locked_before}", flush=True)

    print(f"[1/5] ensure mailbox {TEST_EMAIL} ...", flush=True)
    ensure_mailbox()

    print("[2/5] ensure DB rows (accounts + emails) ...", flush=True)
    ensure_db_rows()

    print("[3/5] (audience + member inserted in same DO-block as step 2)", flush=True)

    print(f"[4/5] SMTP send marketing@ -> {TEST_EMAIL} ...", flush=True)
    msgid = smtp_send()
    print(f"      Message-ID: <{msgid}@{DOMAIN}>")

    print("[5/5] IMAP verify (felix.test INBOX) ...", flush=True)
    if not imap_verify(msgid):
        print("FAIL: mail not landing in INBOX within retry budget", file=sys.stderr)
        return 1
    print("      INBOX hit OK")

    rc = 0
    if not args.no_worker:
        print("[5b ] worker_imap_sync --once -> marketing.inbound_messages ...",
              flush=True)
        landed = worker_once_probe(msgid)
        print(f"      DB row {'OK' if landed else 'MISSING'}")
        if not landed:
            rc = 2

    if args.with_send_row:
        print("[6/8] ensure campaign + insert campaign_sends row "
              "(message_id matches outbound) ...", flush=True)
        cid = ensure_campaign_for_send_row()
        insert_send_row(cid, msgid)
        print(f"      campaign={cid[:8]}... send-row inserted")

        print(f"[7/8] SMTP send REPLY (In-Reply-To <{msgid}@{DOMAIN}>) ...",
              flush=True)
        reply_msgid = smtp_send_reply(msgid)
        print(f"      reply Message-ID: <{reply_msgid}@{DOMAIN}>")

        if not args.no_worker:
            print("[7b ] worker_imap_sync --once (pick up the reply) ...",
                  flush=True)
            worker_once_probe(reply_msgid)

        print("[8/8] verify trg_link_inbound_to_send linked the reply ...",
              flush=True)
        if not verify_reply_linked(msgid, reply_msgid):
            print("FAIL: reply not linked to send-row by trigger 007",
                  file=sys.stderr)
            rc = rc or 4
        else:
            print("      linked_send_id + replied_at populated OK")

    locked_after = lockout_count()
    print(f"[post] investor_already_sent locked rows = {locked_after}", flush=True)
    if locked_after != locked_before:
        print(
            "WARN: investor_already_sent count changed - sticky-lockout invariant broken",
            file=sys.stderr,
        )
        rc = rc or 3

    print("\nreal-case-test " + ("OK" if rc == 0 else f"FAIL (rc={rc})"))
    return rc


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
