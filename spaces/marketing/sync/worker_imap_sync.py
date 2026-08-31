"""Worker C — Mailcow IMAP to DB sync.

Polls all marketing service-mailboxes via IMAP-IDLE (or polling fallback) and
ingests new messages into `marketing.inbound_messages`. Drives the Brevo-like
inbox view + future auto-reply / classifier hooks.

Architecture decisions:

  - **Read-only sync.** We never `\\Delete` server-side. The Mailcow store is
    authoritative; this worker only mirrors into Postgres. Idempotent re-runs
    are safe because every insert checks `message_id` uniqueness.
  - **Per-mailbox UID state.** `~/.rowboat/knowledge/Marketing/.imap_state.json`
    remembers the highest UID seen per `<mailbox>` so each poll only fetches
    new messages. Maps to IMAP `UID FETCH <last+1>:* RFC822`.
  - **Phase-1 inbox set.** The two service accounts that already send mail —
    `marketing@vibemind.space` and `noreply@vibemind.space`. Bounce-replies
    and out-of-office land here. Felix's personal `felix@` is excluded by
    default (privacy boundary).
  - **Bounce detection.** RFC-3464 reports + `X-Failed-Recipients` + 5xx SMTP
    status in the body are flagged as `is_bounce`. Simple regex heuristics —
    good enough for Phase 1 routing, not a full DSN parser.
  - **Reply-linkage.** `In-Reply-To` is captured into the inbound row.
    Migration 007 added `campaign_sends.message_id` + an AFTER-INSERT
    trigger on `inbound_messages` that auto-populates `linked_send_id`
    and stamps `campaign_sends.replied_at` whenever the in_reply_to
    header matches a known outbound Message-ID. The trigger does this
    in-DB; the worker just INSERTs the inbound row.

Env vars:

  MARKETING_IMAP_HOST      default 127.0.0.1   (Mailcow in WSL, host-localhost)
  MARKETING_IMAP_PORT      default 993         (SSL)
  MARKETING_IMAP_USE_SSL   default 1
  MARKETING_IMAP_MAILBOXES default "marketing@vibemind.space,noreply@vibemind.space"
  MARKETING_IMAP_POLL_SEC  default 60
  MARKETING_IMAP_STATE     default ~/.rowboat/knowledge/Marketing/.imap_state.json

Per-mailbox creds:

  MARKETING_IMAP_PASS_<localpart-upper>   e.g. MARKETING_IMAP_PASS_MARKETING
                                                MARKETING_IMAP_PASS_NOREPLY
  Falls back to SMTP_PASS / NOREPLY_PASS (same account, IMAP+SMTP unified).

CLI:
    python -m spaces.marketing.sync.worker_imap_sync             # daemon
    python -m spaces.marketing.sync.worker_imap_sync --once      # one cycle, then exit
    python -m spaces.marketing.sync.worker_imap_sync --probe     # connect + list mailboxes + exit
"""
from __future__ import annotations

import argparse
import email
import email.policy
import imaplib
import json
import os
import re
import signal
import socket
import ssl
import sys
import time
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from . import _db

# ─── config ─────────────────────────────────────────────────────────────

IMAP_HOST = os.environ.get("MARKETING_IMAP_HOST", "127.0.0.1")
IMAP_PORT = int(os.environ.get("MARKETING_IMAP_PORT", "993"))
IMAP_USE_SSL = os.environ.get("MARKETING_IMAP_USE_SSL", "1") not in ("0", "false", "False")
IMAP_POLL_SEC = int(os.environ.get("MARKETING_IMAP_POLL_SEC", "60"))
STATE_PATH = Path(os.environ.get(
    "MARKETING_IMAP_STATE",
    str(Path.home() / ".rowboat" / "knowledge" / "Marketing" / ".imap_state.json"),
))

DEFAULT_MAILBOXES = ["marketing@vibemind.space", "noreply@vibemind.space"]
MAILBOXES = [m.strip() for m in
             os.environ.get("MARKETING_IMAP_MAILBOXES", ",".join(DEFAULT_MAILBOXES)).split(",")
             if m.strip()]

# Heuristics for bounce / autoreply classification
BOUNCE_HINTS = (
    re.compile(r"X-Failed-Recipients:", re.IGNORECASE),
    re.compile(r"\b(mailer-daemon|postmaster)@", re.IGNORECASE),
    re.compile(r"\b5\.[0-9]\.[0-9]\b"),                  # 5xx SMTP status
    re.compile(r"delivery (status|failure) notification", re.IGNORECASE),
    re.compile(r"undeliverable", re.IGNORECASE),
)
AUTOREPLY_HINTS = (
    re.compile(r"Auto-Submitted:\s*auto-replied", re.IGNORECASE),
    re.compile(r"X-Auto-Response-Suppress:", re.IGNORECASE),
    re.compile(r"out of office", re.IGNORECASE),
    re.compile(r"\babwesenheits", re.IGNORECASE),
)

_shutdown = False


def _on_sigterm(signum, frame):
    global _shutdown
    _shutdown = True
    print("[worker_c] received signal, will exit after current cycle", flush=True)


signal.signal(signal.SIGINT, _on_sigterm)
signal.signal(signal.SIGTERM, _on_sigterm)


# ─── state store ────────────────────────────────────────────────────────


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_PATH)


# ─── credentials lookup ─────────────────────────────────────────────────


def _imap_pass_for(mailbox: str) -> str | None:
    """Resolve the IMAP password for a mailbox by checking, in order:
       1. MARKETING_IMAP_PASS_<LOCALPART>
       2. <LOCALPART>_PASS  (e.g. MARKETING_PASS for marketing@…)
       3. SMTP_PASS  (canonical service account)
       4. NOREPLY_PASS for noreply@…
    """
    local = mailbox.split("@", 1)[0].upper()
    for key in (
        f"MARKETING_IMAP_PASS_{local}",
        f"{local}_PASS",
    ):
        v = os.environ.get(key)
        if v:
            return v
    # canonical fallbacks
    if mailbox.startswith("marketing@"):
        return os.environ.get("SMTP_PASS")
    if mailbox.startswith("noreply@"):
        return os.environ.get("NOREPLY_PASS") or os.environ.get("SMTP_PASS")
    return os.environ.get("SMTP_PASS")


# ─── IMAP plumbing ──────────────────────────────────────────────────────


def _imap_connect(mailbox: str) -> imaplib.IMAP4 | None:
    """Open an IMAP connection + LOGIN as the mailbox owner."""
    pw = _imap_pass_for(mailbox)
    if not pw:
        print(f"[worker_c] no password resolvable for {mailbox} -- skipping", flush=True)
        return None
    try:
        if IMAP_USE_SSL:
            ctx = ssl.create_default_context()
            # Mailcow on WSL is usually self-signed for localhost — relax verify.
            # Strict verify only if MARKETING_IMAP_STRICT_TLS is set.
            if os.environ.get("MARKETING_IMAP_STRICT_TLS", "0") not in ("1", "true", "True"):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx, timeout=30)
        else:
            conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT, timeout=30)
        conn.login(mailbox, pw)
        return conn
    except (imaplib.IMAP4.error, OSError, socket.timeout) as e:
        print(f"[worker_c] IMAP connect failed for {mailbox}: {e}", flush=True)
        return None


def _decode_header(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw or ""


def _msg_body_text(msg: email.message.EmailMessage) -> str:
    """Extract plain-text body; fall back to stripping html if needed."""
    body = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_payload(decode=True) or b""
                    body = payload.decode(part.get_content_charset() or "utf-8",
                                          errors="replace")
                    break
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        payload = part.get_payload(decode=True) or b""
                        html = payload.decode(part.get_content_charset() or "utf-8",
                                              errors="replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        break
        else:
            payload = msg.get_payload(decode=True) or b""
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    except Exception as e:
        body = f"<<extraction failed: {e}>>"
    # cap to ~256 KB to keep DB rows sane
    return body[:262144]


def _classify(headers_raw: str, body: str) -> tuple[bool, bool]:
    """Legacy: returns (is_bounce, is_autoreply) booleans for backwards-compat.

    The richer pre_classification string lives in _pre_classify_for_db() and
    is the source-of-truth from Schicht 6.2 forward.
    """
    haystack = headers_raw + "\n" + body[:4096]
    is_bounce = any(p.search(haystack) for p in BOUNCE_HINTS)
    is_autoreply = any(p.search(haystack) for p in AUTOREPLY_HINTS)
    return is_bounce, is_autoreply


def _check_message_id_known(message_id: str, container: str) -> bool:
    """Cheap lookup: is this message_id one we sent?
    Uses idx_sends_msgid partial unique index from migration 007."""
    if not message_id:
        return False
    try:
        rows = _db.query_via_docker(
            f"SELECT 1 AS x FROM marketing.campaign_sends "
            f"WHERE message_id = {_db._sql_literal(message_id)} "
            f"  AND message_id IS NOT NULL LIMIT 1",
            container=container,
        )
        return bool(rows)
    except Exception:
        return False


def _pre_classify_for_db(headers_raw: str, body: str,
                          container: str) -> tuple[str, bool]:
    """Pre-classify per Schicht 6.2 spec.

    Returns:
        (pre_classification, needs_review) where pre_classification ∈
        {'bounce', 'opt-out', 'reply', 'spam', 'unknown'}
    """
    from .inbound_pretag import pre_classify
    return pre_classify(
        headers_raw, body,
        check_message_id_known=lambda mid: _check_message_id_known(mid, container)
    )


# ─── DB sink ────────────────────────────────────────────────────────────


def _insert_inbound(row: dict, container: str) -> bool:
    """INSERT into marketing.inbound_messages, idempotent on (message_id).

    Returns True if a row was inserted (or already present), False on error.
    """
    # ON CONFLICT requires a unique constraint — we don't have one on
    # message_id (it's nullable + non-unique by spec). Instead, pre-check.
    msg_id = row.get("message_id") or ""
    if msg_id:
        existing = _db.query_via_docker(
            f"SELECT 1 AS x FROM marketing.inbound_messages "
            f"WHERE message_id = {_db._sql_literal(msg_id)} LIMIT 1",
            container=container,
        )
        if existing:
            return True

    cols = ["received_at", "mailbox", "from_email", "from_name", "to_email",
            "subject", "body_text", "message_id", "in_reply_to", "headers",
            "is_bounce", "is_autoreply",
            # Schicht 6.2: pre-classification fields
            "pre_classification", "pre_classified_by", "pre_classified_at",
            "needs_review"]
    placeholders = []
    for c in cols:
        v = row.get(c)
        if c == "headers" and v is not None:
            placeholders.append(f"{_db._sql_literal(json.dumps(v))}::jsonb")
        elif c == "received_at" and v is not None:
            placeholders.append(f"{_db._sql_literal(v)}::timestamptz")
        elif c == "pre_classified_at":
            # If pre_classification is set, stamp now() via SQL literal
            if row.get("pre_classification"):
                placeholders.append("now()")
            else:
                placeholders.append("NULL")
        elif c == "needs_review":
            placeholders.append("TRUE" if row.get(c, True) else "FALSE")
        else:
            placeholders.append(_db._sql_literal(v))

    sql = (
        f"INSERT INTO marketing.inbound_messages ({', '.join(cols)}) "
        f"VALUES ({', '.join(placeholders)})"
    )
    try:
        _db.execute_via_docker(sql, container=container)
    except Exception as e:
        print(f"[worker_c] insert failed mailbox={row.get('mailbox')} "
              f"subject={(row.get('subject') or '')[:40]!r}: {e}", flush=True)
        return False

    # Reply-linkage is handled by the DB trigger trg_link_inbound_to_send
    # (migration 007) -- it fires AFTER INSERT on this row, looks up
    # campaign_sends.message_id = in_reply_to via the partial unique index
    # idx_sends_msgid, and populates BOTH inbound_messages.linked_send_id
    # AND campaign_sends.replied_at atomically with split-GUC suppression
    # for the inbound double-emit. The Python side does nothing here.
    #
    # CONTRACT: do NOT set the marketing.sync_origin GUC before this
    # INSERT -- the trigger's split-GUC pattern depends on the prior
    # value being '' so that the campaign_sends.replied_at update emits
    # normally to sync_outbox.
    return True


# ─── single cycle ───────────────────────────────────────────────────────


def _sync_mailbox(mailbox: str, container: str, state: dict) -> tuple[int, int]:
    """Sync one mailbox. Returns (fetched, inserted)."""
    conn = _imap_connect(mailbox)
    if conn is None:
        return (0, 0)

    fetched = inserted = 0
    try:
        typ, _ = conn.select("INBOX", readonly=True)
        if typ != "OK":
            print(f"[worker_c] SELECT INBOX failed for {mailbox}", flush=True)
            return (0, 0)

        last_uid = int(state.get(mailbox, {}).get("last_uid", 0))
        # UID search returns *all* uids; we then fetch only > last_uid.
        # For mailboxes with millions of mails this would be expensive — for
        # service accounts (low volume), this is fine.
        search_criteria = f"UID {last_uid + 1}:*"
        typ, data = conn.uid("search", None, search_criteria)
        if typ != "OK" or not data or not data[0]:
            return (0, 0)

        uids = [u for u in data[0].split() if u]
        if not uids:
            return (0, 0)

        max_uid_seen = last_uid
        for uid in uids:
            try:
                uid_int = int(uid)
            except ValueError:
                continue
            if uid_int <= last_uid:
                # Stale match — server returned old UID. Skip.
                continue

            typ, msg_data = conn.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not msg_data:
                continue
            fetched += 1

            raw_bytes = b""
            for part in msg_data:
                if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
                    raw_bytes = part[1]
                    break
            if not raw_bytes:
                continue

            try:
                msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)
            except Exception as e:
                print(f"[worker_c] parse failed uid={uid}: {e}", flush=True)
                continue

            subject = _decode_header(msg.get("Subject"))
            from_raw = msg.get("From", "")
            from_name, from_email = parseaddr(from_raw)
            from_name = _decode_header(from_name)
            to_raw = msg.get("To", "")
            _, to_email = parseaddr(to_raw)
            msg_id = (msg.get("Message-ID") or "").strip().strip("<>")
            in_reply = (msg.get("In-Reply-To") or "").strip().strip("<>")
            date_raw = msg.get("Date")
            received = None
            if date_raw:
                try:
                    received = parsedate_to_datetime(date_raw).isoformat()
                except Exception:
                    pass
            body = _msg_body_text(msg)

            # Compact header dump for forensics (full headers can be large)
            headers = {k: _decode_header(v) for k, v in msg.items()}
            headers_raw = "\n".join(f"{k}: {v}" for k, v in headers.items())[:8192]

            is_bounce, is_autoreply = _classify(headers_raw, body)

            # Schicht 6.2: rich pre_classification + needs_review.
            # Wrapped in try -- pretag failure must NOT block the INSERT
            # (we'd rather have the row with unknown pre_classification
            # than lose the message entirely).
            pre_class: str | None = None
            needs_rev: bool = True
            try:
                pre_class, needs_rev = _pre_classify_for_db(headers_raw, body, container)
            except Exception as e:
                print(f"[worker_c] pretag failed for uid={uid_int}: {e}",
                      flush=True)

            row = {
                "received_at": received,
                "mailbox": mailbox,
                "from_email": from_email or None,
                "from_name": from_name or None,
                "to_email": to_email or None,
                "subject": subject or None,
                "body_text": body or None,
                "message_id": msg_id or None,
                "in_reply_to": in_reply or None,
                "headers": headers,
                "is_bounce": is_bounce,
                "is_autoreply": is_autoreply,
                "pre_classification": pre_class,
                "pre_classified_by": "worker_c:pretag_v1" if pre_class else None,
                "needs_review": needs_rev,
            }
            if _insert_inbound(row, container):
                inserted += 1

            if uid_int > max_uid_seen:
                max_uid_seen = uid_int

        # Persist new high-water UID
        state.setdefault(mailbox, {})["last_uid"] = max_uid_seen
        state[mailbox]["last_synced_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save_state(state)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass

    return (fetched, inserted)


def run_once(container: str | None = None) -> tuple[int, int]:
    if container is None:
        container = _db.find_supabase_container()
    state = _load_state()
    total_fetched = total_inserted = 0
    for mailbox in MAILBOXES:
        f, i = _sync_mailbox(mailbox, container, state)
        print(f"[worker_c] {mailbox}: fetched={f} inserted={i}", flush=True)
        total_fetched += f
        total_inserted += i
    return (total_fetched, total_inserted)


def run_daemon() -> None:
    container = _db.find_supabase_container()
    print(f"[worker_c] container={container[:12]} host={IMAP_HOST}:{IMAP_PORT} "
          f"mailboxes={MAILBOXES} poll={IMAP_POLL_SEC}s", flush=True)
    while not _shutdown:
        try:
            run_once(container)
        except Exception as e:
            print(f"[worker_c] cycle error: {e}", flush=True)
        # Sleep in small ticks so signals get serviced quickly
        for _ in range(IMAP_POLL_SEC):
            if _shutdown:
                break
            time.sleep(1)


def probe() -> int:
    """Connect to each mailbox, list available folders, exit."""
    print(f"[probe] host={IMAP_HOST}:{IMAP_PORT} ssl={IMAP_USE_SSL}", flush=True)
    rc = 0
    for mailbox in MAILBOXES:
        print(f"[probe] connecting {mailbox} …", flush=True)
        conn = _imap_connect(mailbox)
        if conn is None:
            rc = 1
            continue
        try:
            typ, mbs = conn.list()
            if typ == "OK":
                print(f"[probe] {mailbox} OK  folders={len(mbs)}", flush=True)
                for m in (mbs or [])[:5]:
                    print(f"  {m.decode(errors='replace') if isinstance(m, bytes) else m}",
                          flush=True)
            else:
                print(f"[probe] {mailbox} LIST not OK", flush=True)
                rc = 1
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    return rc


# ─── CLI ────────────────────────────────────────────────────────────────


def _main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="Run one cycle then exit")
    p.add_argument("--probe", action="store_true", help="Test connectivity to all mailboxes then exit")
    args = p.parse_args()

    if args.probe:
        return probe()
    if args.once:
        f, i = run_once()
        print(f"[worker_c] ONCE total fetched={f} inserted={i}", flush=True)
        return 0
    run_daemon()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
