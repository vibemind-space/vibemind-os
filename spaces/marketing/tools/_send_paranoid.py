"""Phase-2 send-worker core (defensive). Private module.

DO NOT import this directly from agents -- go through send_campaign() in
marketing_tools.py, which preserves the swarm-standard envelope.

Three modes
-----------

  DRY_RUN  (default)
    Returns {confirm_token, recipient_count, recipients_preview (first 5),
    audience_id, gates_passed}. NEVER opens an SMTP connection. NEVER
    writes a campaign_sends row. Audit-log entry written.

  SHADOW
    Goes through every motion EXCEPT external delivery: opens an SMTP
    connection to 127.0.0.1:54325 (Mailpit sink), generates real
    Message-IDs, writes campaign_sends rows (sent_at set, delivered_at
    NULL). Mails are visible in Mailpit-UI on :54324 and never leave.
    Used to stress-test the pipeline without touching Postfix / real
    recipients.

  LIVE
    Real send via SMTP_HOST:SMTP_PORT (Mailcow 127.0.0.1:465 by default).
    Requires:
      - MARKETING_SEND_ENABLED=true env var (kill-switch)
      - logs/marketing/FREEZE file ABSENT (manual-rm-only)
      - confirm_token matching the audience-recipient snapshot SHA256
      - all gates pass (domain-allowlist, investor-lockout, postfix-probe)
    Postfix loopback-block is the SECOND line of defence; this worker is
    the first.

The investor-lockout landmine (db/005:39-50)
---------------------------------------------

`trg_flip_investor_sent` fires AFTER INSERT OR UPDATE OF delivered_at on
marketing.campaign_sends. ANY transition NULL->non-NULL of delivered_at
flips marketing.emails.investor_already_sent=true PERMANENTLY for that
recipient. There is no tag check -- the trigger treats every campaign as
investor-grade.

This worker therefore NEVER writes delivered_at. SMTP-accept moves us
from queued_at -> sent_at only. A future Mailcow-webhook-listener
worker will own the sent_at -> delivered_at transition, and that
worker is the only place where the investor-lockout is intentionally
allowed to fire.

Gates in linear order (each is a single function in this module):

  1. kill-switch env (LIVE only)
  2. freeze-file absent (LIVE only)
  3. resolve campaign + reject terminal status (sent/cancelled/failed)
  4. snapshot recipients via same JOIN as audience_count()
     - investor_already_sent=false
     - smtp_valid=1
     - unsubscribed_at IS NULL
  5. domain-allowlist scan
     - ASCII-only domain
     - idna.encode(domain) == domain (Unicode lookalike defence)
     - domain in ALLOWED_DOMAINS = {"vibemind.space"}
  6. investor-lockout defense-in-depth scan
     (the SELECT filter in step 4 should already exclude these,
      but we recount and bail if anything snuck through)
  7. confirm-token verify (LIVE only)
     token = sha256_hex("v1\\n" + cid + "\\n" + aid + "\\n" + str(count)
                       + "\\n" + sha256_hex(sorted_lower_email_list)
                       + "\\n" + sha256_hex(sorted_allowed_domains))
  8. SMTP_HOST/PORT mode-pin + Mailpit pre-ping (SHADOW only)
  9. Postfix loopback probe (LIVE only) on the SAME connection that
     will deliver -- RCPT TO with an EXTERNAL test address (probe@example.org),
     expect SMTPRecipientsRefused with 554. Anything else = ABORT + FREEZE.
 10. Send loop:
       - INSERT campaign_sends (campaign_id, email)
         ON CONFLICT (campaign_id, email) DO NOTHING RETURNING id
         (uniq constraint from migration 008; only rows actually
          returned proceed to sendmail)
       - On each row, per-recipient RCPT TO probe BEFORE DATA on the
         SAME connection -- 554 = expected for non-vibemind.space
         and ABORT, 250 = expected for vibemind.space
       - On 250: send DATA; UPDATE campaign_sends SET sent_at=now(),
                 message_id=<core>; never touch delivered_at
       - On SMTPException: UPDATE campaign_sends SET bounced_at=now(),
                           bounce_reason=str(exc); never touch sent_at
       - Recipient cap: HARD_RECIPIENT_CAP=1000; abort early on hit
       - Token-bucket rate-limit: 10/sec, configurable per run
 11. Mailcow mailq audit (LIVE only)
     GET /api/v1/get/mailq/all; if any recipient outside vibemind.space
     in the queue, write FREEZE and raise. Defense behind the postfix
     PCRE block.
 12. Final audit + status flip (campaign.status -> 'sent') in the SAME
     transaction as the last row update. No 'queued + partially sent'
     orphan state.

Every gate raises a ParanoidAbort(guard_name, detail) on failure. The
top-level run() catches it, writes the audit row, and returns the
swarm-standard {success, message, data{guard}} envelope.
"""
from __future__ import annotations

import enum
import hashlib
import hmac
import json
import logging
import os
import re
import smtplib
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..sync import _db

logger = logging.getLogger("marketing.send")


# ─── Constants ─────────────────────────────────────────────────────────


class SendMode(enum.Enum):
    DRY_RUN = "dry_run"
    SHADOW = "shadow"
    LIVE = "live"


# Domain allowlist is HARDCODED in code. Never load from env or DB --
# changing it requires a code review.
ALLOWED_DOMAINS = frozenset({"vibemind.space"})

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
FREEZE_PATH = REPO_ROOT / "logs" / "marketing" / "FREEZE"

# SHADOW SMTP target. Mailpit's :1025 listener is intentionally NOT
# host-published in the swarm stack (see infra/swarm/vibemind-stack.yml
# inbucket service for the security rationale: Swarm-mode does not
# support hostip binding, so a 0.0.0.0 bind would expose an auth-less
# SMTP sink to the LAN).
#
# To drive SHADOW from a host-native send-worker, start an EXTRA
# Mailpit container locally with:
#     docker run --rm -d -p 127.0.0.1:54325:1025 axllent/mailpit
# then export MARKETING_SHADOW_HOST=127.0.0.1 / MARKETING_SHADOW_PORT=54325.
# When the send-worker runs CONTAINERISED next to the stack, it can
# reach the stack-Mailpit via the overlay-network DNS name
# `supabase-inbucket:1025` (set MARKETING_SHADOW_HOST=supabase-inbucket
# MARKETING_SHADOW_PORT=1025).
#
# Defaults below intentionally point at a non-reachable address so the
# pre-ping (gate 8) fails loud rather than racing into a half-configured
# send. Operator must set envs explicitly.
SHADOW_HOST = os.environ.get("MARKETING_SHADOW_HOST", "127.0.0.1")
SHADOW_PORT = int(os.environ.get("MARKETING_SHADOW_PORT", "0"))   # 0 = disabled

KILL_SWITCH_ENV = "MARKETING_SEND_ENABLED"

# Hard ceiling. Cannot be raised via env. Aborts mid-loop on hit.
HARD_RECIPIENT_CAP = 1000

# Token-bucket: max sends per second. Default-conservative.
DEFAULT_RATE_PER_SEC = 10

# Mailcow API base (used only for queue audit). Resolves to 127.0.0.1 by
# .env convention -- the worker re-asserts this at startup.
MAILCOW_URL_DEFAULT = "https://127.0.0.1:8443"

# Postfix loopback probe target -- must be a syntactically valid email
# in a non-allowed domain. example.org is RFC2606-reserved and cannot
# clash with anything real.
LOOPBACK_PROBE_RECIPIENT = "loopback-probe@example.org"


class ParanoidAbort(Exception):
    """Raised by any gate on failure. Caught by run()."""

    def __init__(self, guard: str, detail: str = ""):
        super().__init__(f"{guard}: {detail}" if detail else guard)
        self.guard = guard
        self.detail = detail


# ─── Gates 1+2: kill-switch + freeze ────────────────────────────────────


def _check_kill_switch() -> None:
    if os.environ.get(KILL_SWITCH_ENV, "").strip().lower() not in ("true", "1", "yes"):
        raise ParanoidAbort(
            "kill_switch",
            f"{KILL_SWITCH_ENV} must equal 'true' for LIVE mode (currently absent or false)",
        )


def _check_freeze() -> None:
    if FREEZE_PATH.exists():
        contents = ""
        try:
            contents = FREEZE_PATH.read_text(encoding="utf-8", errors="replace")[:240]
        except Exception:
            pass
        raise ParanoidAbort(
            "freeze_file",
            f"{FREEZE_PATH} present -- manual review + rm required. Last note: {contents!r}",
        )


def _write_freeze(reason: str) -> None:
    """FREEZE the send-worker on a Phase-1-contract violation."""
    try:
        FREEZE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FREEZE_PATH.write_text(
            f"FROZEN at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"reason: {reason}\n"
            f"manual review + rm required before any further sends.\n",
            encoding="utf-8",
        )
        logger.error("[freeze] %s", reason)
    except Exception as e:
        logger.exception("could not write FREEZE: %s", e)


# ─── Gate 3: resolve campaign ──────────────────────────────────────────


_TERMINAL_STATUSES = {"sent", "cancelled", "failed"}


def _resolve_campaign(campaign_id: str) -> Dict[str, Any]:
    row = _db.query_one(
        f"SELECT id::text AS id, name, channel, status, audience_id::text AS audience_id, "
        f"       template_id::text AS template_id, is_loopback "
        f"FROM marketing.campaigns "
        f"WHERE id = {_db._sql_literal(campaign_id)}::uuid"
    )
    if not row:
        raise ParanoidAbort("resolve_campaign", f"campaign {campaign_id} not found")
    if row["status"] in _TERMINAL_STATUSES:
        raise ParanoidAbort(
            "resolve_campaign",
            f"campaign status='{row['status']}' is terminal; re-create campaign to re-send",
        )
    if not row.get("audience_id"):
        raise ParanoidAbort("resolve_campaign", "campaign has no audience_id")
    return row


def _resolve_template(template_id: Optional[str]) -> Dict[str, Any]:
    """Load template body+subject for a campaign's template_id.

    Returns {subject, body_text, body_html} or {} if no template_id.
    Empty/None body fields stay empty -- _build_mail uses fallback text.
    """
    if not template_id:
        return {}
    row = _db.query_one(
        f"SELECT subject, body_text, body_html, "
        f"       COALESCE(tracking_enabled, false) AS tracking_enabled "
        f"FROM marketing.templates "
        f"WHERE id = {_db._sql_literal(template_id)}::uuid"
    )
    return row or {}


# ─── Gate 4: snapshot recipients ───────────────────────────────────────


def _snapshot_recipients(audience_id: str) -> List[Dict[str, Any]]:
    rows = _db.query_via_docker(
        f"SELECT DISTINCT e.email, e.handle, e.domain "
        f"FROM marketing.audience_members am "
        f"JOIN marketing.emails e ON e.email = am.email "
        f"WHERE am.audience_id = {_db._sql_literal(audience_id)}::uuid "
        f"  AND e.investor_already_sent = false "
        f"  AND e.smtp_valid = 1 "
        f"  AND e.unsubscribed_at IS NULL "
        f"ORDER BY e.email"
    )
    if not rows:
        raise ParanoidAbort(
            "snapshot_recipients",
            f"audience {audience_id} resolved to 0 reachable recipients",
        )
    if len(rows) > HARD_RECIPIENT_CAP:
        raise ParanoidAbort(
            "recipient_cap",
            f"snapshot has {len(rows)} > HARD_RECIPIENT_CAP={HARD_RECIPIENT_CAP}",
        )
    return rows


# ─── Gate 5: domain allowlist + Unicode lookalike defence ──────────────


def _scan_domain_allowlist(recipients: List[Dict[str, Any]]) -> None:
    bad: List[Tuple[str, str]] = []
    for r in recipients:
        email = (r.get("email") or "").strip().lower()
        if "@" not in email:
            bad.append((email, "no @"))
            continue
        domain = email.rsplit("@", 1)[1]
        # ASCII-only: any byte > 0x7f is a Unicode lookalike attempt.
        try:
            domain.encode("ascii")
        except UnicodeEncodeError:
            bad.append((email, f"non-ascii domain: {domain!r}"))
            continue
        # IDNA round-trip: must equal the raw (i.e. nothing IDNA-decoded).
        try:
            idna_form = domain.encode("idna").decode("ascii")
        except Exception as e:
            bad.append((email, f"idna encode failed: {e}"))
            continue
        if idna_form != domain:
            bad.append((email, f"idna form differs: {idna_form!r} != {domain!r}"))
            continue
        if domain not in ALLOWED_DOMAINS:
            bad.append((email, f"domain {domain!r} not in allowlist {set(ALLOWED_DOMAINS)}"))
    if bad:
        raise ParanoidAbort(
            "domain_allowlist",
            f"{len(bad)} recipient(s) violated allowlist: {bad[:5]}",
        )


# ─── Gate 6: investor-lockout defense-in-depth ─────────────────────────


def _check_investor_locked(recipients: List[Dict[str, Any]]) -> None:
    emails = [r["email"] for r in recipients]
    if not emails:
        return
    in_clause = ", ".join(_db._sql_literal(e) for e in emails)
    row = _db.query_one(
        f"SELECT COUNT(*) AS n FROM marketing.emails "
        f"WHERE email IN ({in_clause}) AND investor_already_sent = true"
    )
    n = int(row["n"]) if row else 0
    if n > 0:
        raise ParanoidAbort(
            "investor_lockout",
            f"{n} recipient(s) in snapshot have investor_already_sent=true. "
            f"This SHOULD have been excluded by the snapshot filter -- "
            f"data drift between snapshot and recount. ABORT.",
        )


# ─── Gate 7: confirm-token ─────────────────────────────────────────────


def compute_confirm_token(campaign_id: str, audience_id: str,
                          recipients: List[Dict[str, Any]]) -> str:
    """SHA256 over (campaign_id, audience_id, full sorted lower-cased
    recipient list, sorted allowlist). Any composition change between
    dry-run and confirm invalidates the token by construction."""
    emails_sorted = sorted({(r.get("email") or "").strip().lower() for r in recipients})
    emails_hash = hashlib.sha256("\n".join(emails_sorted).encode("utf-8")).hexdigest()
    allow_sorted = sorted(ALLOWED_DOMAINS)
    allow_hash = hashlib.sha256("\n".join(allow_sorted).encode("utf-8")).hexdigest()
    payload = (
        f"v1\n{campaign_id}\n{audience_id}\n{len(emails_sorted)}\n"
        f"{emails_hash}\n{allow_hash}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_confirm_token(provided: Optional[str], expected: str) -> None:
    if not provided:
        raise ParanoidAbort(
            "confirm_token",
            "LIVE mode requires confirm_token from a prior DRY_RUN response",
        )
    if not hmac.compare_digest(provided.strip().lower(), expected.lower()):
        raise ParanoidAbort(
            "confirm_token",
            "confirm_token does not match the current audience snapshot. "
            "Membership probably changed between dry_run and live. Re-run dry_run.",
        )


# ─── Gate 8: SHADOW pre-ping ───────────────────────────────────────────


def _shadow_preping() -> None:
    # Fail-loud if SHADOW envs are not set: default SHADOW_PORT=0 means
    # the operator did not configure the sink. Refusing to fall through
    # to a default 0.0.0.0-published port is the whole point.
    if SHADOW_PORT <= 0:
        raise ParanoidAbort(
            "shadow_preping",
            "MARKETING_SHADOW_HOST + MARKETING_SHADOW_PORT must be set "
            "before SHADOW mode (e.g. start a local Mailpit with "
            "`docker run -p 127.0.0.1:54325:1025 axllent/mailpit` "
            "and export MARKETING_SHADOW_HOST=127.0.0.1 / MARKETING_SHADOW_PORT=54325)",
        )
    s = socket.socket()
    try:
        s.settimeout(3)
        s.connect((SHADOW_HOST, SHADOW_PORT))
    except Exception as e:
        raise ParanoidAbort("shadow_preping", f"{SHADOW_HOST}:{SHADOW_PORT} unreachable: {e}")
    finally:
        try:
            s.close()
        except Exception:
            pass


# ─── Gate 9: Postfix loopback probe ────────────────────────────────────


def _postfix_loopback_probe(smtp_host: str, smtp_port: int,
                            smtp_user: str, smtp_pass: str,
                            sender: str) -> None:
    """Open the SAME connection that will deliver, send MAIL FROM and a
    RCPT TO with an external test address. Expect 554.

    The connection is closed here; the send loop opens a fresh one for
    the actual delivery. Per-recipient RCPT TO probes inside the loop
    (gate 10) re-validate on the live connection.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=15) as s:
            s.login(smtp_user, smtp_pass)
            s.mail(sender)
            code, msg = s.rcpt(LOOPBACK_PROBE_RECIPIENT)
            # If the server accepted, the loopback PCRE is GONE -- this is
            # the worst case. FREEZE the worker.
            if code in (250, 251):
                _write_freeze(
                    f"postfix loopback probe accepted {LOOPBACK_PROBE_RECIPIENT} "
                    f"(code={code}). PCRE block missing? FROZEN."
                )
                raise ParanoidAbort(
                    "postfix_probe",
                    f"server accepted external recipient (code={code}). FREEZE written.",
                )
            if code != 554:
                # Other rejection (e.g. 450 throttle) is also unexpected.
                raise ParanoidAbort(
                    "postfix_probe",
                    f"unexpected RCPT TO response: code={code} msg={msg!r}",
                )
            try:
                s.rset()
            except Exception:
                pass
    except smtplib.SMTPRecipientsRefused as e:
        # Some smtplib versions raise here with the 554 reply -- treat as expected.
        for rcpt, (code, _msg) in (e.recipients or {}).items():
            if code != 554:
                raise ParanoidAbort(
                    "postfix_probe",
                    f"unexpected refusal code on probe: {rcpt}->{code}",
                )
    except smtplib.SMTPException as e:
        raise ParanoidAbort("postfix_probe", f"SMTP error during probe: {e}")


# ─── Gate 10: send loop with atomic claim + per-recipient probe ────────


def _claim_send_rows(campaign_id: str, recipients: List[Dict[str, Any]]) -> List[str]:
    """Atomic claim via the new unique constraint (migration 008).
    Returns the list of emails for rows actually inserted (= rows we
    own and must send to). Already-existing rows are silently skipped.

    Postgres rejects data-modifying CTEs inside a SELECT subquery
    (which is what query_via_docker would generate). Workaround:
    run INSERT...RETURNING via execute_via_docker and parse psql's
    tab-separated stdout. Aggressively single-quote-escaped via
    _sql_literal -- inputs are emails, no path for injection but we
    keep the same hygiene as everywhere else.
    """
    if not recipients:
        return []
    values = ", ".join(
        f"({_db._sql_literal(campaign_id)}::uuid, {_db._sql_literal(r['email'])})"
        for r in recipients
    )
    out = _db.execute_via_docker(
        f"INSERT INTO marketing.campaign_sends (campaign_id, email) "
        f"VALUES {values} "
        f"ON CONFLICT (campaign_id, email) DO NOTHING "
        f"RETURNING email"
    )
    # psql -tAc returns one returned-email per line (untyped, unaligned),
    # but it ALSO emits an "INSERT N M" status line at the end. Filter
    # out anything that doesn't look like an email.
    return [
        line.strip()
        for line in (out or "").splitlines()
        if line.strip() and "@" in line and not line.startswith("INSERT")
    ]


_MERGE_FIELD_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_ALLOWED_MERGE_FIELDS = frozenset({
    "first_name", "last_name", "full_name", "display_name",
    "email", "company", "title", "domain",
    "campaign_name", "msgid_core", "unsub_url",
})


def merge_render(template: str, fields: Dict[str, Any]) -> str:
    """Strict {{merge_field}} renderer with an allowlist.

    Why strict (no Jinja, no expressions):
      - Templates are operator-authored OR Hand-generated; Hand-generated
        text can contain prompt-injection. A full template engine
        (eval, includes, filters) would be a vector. We only substitute
        flat strings.
      - Unknown fields raise — silent fallback to empty string would
        hide typos like {{firstname}} (missing underscore) that ship
        broken mails.

    Allowlist (_ALLOWED_MERGE_FIELDS) is hardcoded; adding a field is
    a code review. Substituted values are HTML-safe-escaped if the
    template appears to be HTML (contains '<' chars in the template).
    """
    if not template:
        return ""
    missing = []
    is_html = "<" in template and ">" in template

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in _ALLOWED_MERGE_FIELDS:
            raise ValueError(f"unknown merge field {{{{ {key} }}}}; "
                             f"allowed: {sorted(_ALLOWED_MERGE_FIELDS)}")
        if key not in fields or fields[key] is None:
            missing.append(key)
            return ""
        val = str(fields[key])
        if is_html:
            # Tiny inline escape; avoids importing html only for this
            val = (val.replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;")
                      .replace('"', "&quot;")
                      .replace("'", "&#39;"))
        return val

    rendered = _MERGE_FIELD_RE.sub(_replace, template)
    if missing:
        # Caller can decide whether to abort or just log
        logger.warning(
            "[merge_render] missing field values for: %s -- substituted ''",
            sorted(set(missing)),
        )
    return rendered


def _resolve_recipient_merge_fields(recipient: str) -> Dict[str, Any]:
    """Pull per-recipient merge fields from the DB. Falls back to a
    sensible default if the row isn't there (e.g. ad-hoc smoke send)."""
    try:
        row = _db.query_one(
            f"SELECT a.handle, a.display_name, e.email, e.domain "
            f"FROM marketing.emails e "
            f"LEFT JOIN marketing.accounts a ON a.handle = e.handle "
            f"WHERE e.email = {_db._sql_literal(recipient.lower())}"
        )
    except Exception:
        row = None
    if not row:
        # Fallback: derive display_name from localpart
        local = recipient.split("@", 1)[0]
        return {
            "email": recipient,
            "display_name": local,
            "first_name": local.split(".")[0].capitalize() if "." in local else local.capitalize(),
            "domain": recipient.split("@", 1)[1] if "@" in recipient else "",
        }
    display = row.get("display_name") or row.get("handle") or recipient.split("@", 1)[0]
    # Best-effort first/last from display_name
    parts = (display or "").strip().split()
    first = parts[0] if parts else ""
    last = parts[-1] if len(parts) > 1 else ""
    return {
        "email": row.get("email") or recipient,
        "domain": row.get("domain") or recipient.split("@", 1)[1] if "@" in recipient else "",
        "display_name": display,
        "first_name": first,
        "last_name": last,
        "full_name": display,
    }


def _build_mail(sender: str, recipient: str, campaign_name: str,
                msgid_core: str,
                *,
                template_subject: Optional[str] = None,
                template_body_text: Optional[str] = None,
                template_body_html: Optional[str] = None,
                tracking_enabled: bool = False,
                campaign_id: Optional[str] = None) -> Tuple[str, str]:
    """Build a multipart message for the send.

    If template_* args are passed, they go through merge_render with
    per-recipient fields fetched from the DB. Otherwise a placeholder
    body is used (smoke-test case).

    Implements RFC 8058 one-click unsubscribe alongside the legacy
    mailto: form (Gmail/Outlook show the one-click button when both
    are present and the HTTPS endpoint responds 200 to a POST with
    body `List-Unsubscribe=One-Click`).

    Returns (message_id_core, full_RFC822_string).
    """
    msgid_full = f"<{msgid_core}@vibemind.space>"
    # The unsubscribe URL is the marketing-API endpoint. Token is a
    # keyed HMAC-SHA256 of (recipient, msgid_core) under
    # MARKETING_UNSUB_SECRET. Refuse to mint a token if the secret is
    # absent or too short -- otherwise the API endpoint would happily
    # verify a token forged by anyone who knows email+msg+empty-key.
    unsub_base = os.environ.get("MARKETING_UNSUB_URL",
                                "http://127.0.0.1:5510/api/unsubscribe")
    unsub_secret = os.environ.get("MARKETING_UNSUB_SECRET", "")
    if len(unsub_secret) < 32:
        raise ParanoidAbort(
            "unsub_secret",
            "MARKETING_UNSUB_SECRET must be set and >=32 chars before SHADOW/LIVE send "
            "(one-click unsubscribe URL would otherwise be forgeable)",
        )
    token = hmac.new(
        unsub_secret.encode("utf-8"),
        f"{recipient.lower()}|{msgid_core}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    unsub_url = (
        f"{unsub_base}?email={recipient}&msg={msgid_core}&t={token}"
    )

    # Per-recipient merge fields
    fields = _resolve_recipient_merge_fields(recipient)
    fields["campaign_name"] = campaign_name
    fields["msgid_core"] = msgid_core
    fields["unsub_url"] = unsub_url

    # Subject: template OR fallback to current placeholder
    if template_subject:
        try:
            rendered_subject = merge_render(template_subject, fields)
        except ValueError as e:
            raise ParanoidAbort("template_subject", str(e))
    else:
        rendered_subject = f"[{campaign_name}] vibemind-marketing test"

    # Plain-text body
    if template_body_text:
        try:
            rendered_text = merge_render(template_body_text, fields)
        except ValueError as e:
            raise ParanoidAbort("template_body_text", str(e))
    else:
        rendered_text = (
            f"This is an automated VibeMind marketing message.\n"
            f"Click to unsubscribe: {unsub_url}\n"
            f"Or reply with 'unsubscribe' in the subject.\n"
            f"(campaign: {campaign_name} -- id: {msgid_core})\n"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = rendered_subject
    msg["From"] = formataddr(("VibeMind Marketing", sender))
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msgid_full
    # RFC 8058 one-click: BOTH headers must be present and the URL must
    # POST-accept body `List-Unsubscribe=One-Click` returning 2xx.
    msg["List-Unsubscribe"] = f"<{unsub_url}>, <mailto:noreply@vibemind.space?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg["X-VibeMind-Campaign"] = campaign_name
    msg.attach(MIMEText(rendered_text, "plain", "utf-8"))

    # Optional HTML alternative
    if template_body_html:
        try:
            rendered_html = merge_render(template_body_html, fields)
        except ValueError as e:
            raise ParanoidAbort("template_body_html", str(e))
        # Tracking injection (Schicht 5.1 + 5.2). Only when:
        #   - template has tracking_enabled = true
        #   - campaign_id is known (passed in by caller)
        #   - tracking env (secret + base url) is configured
        #   - recipient has tracking_consent_given_at IS NOT NULL
        #     AND tracking_consent_revoked_at IS NULL (DSGVO gate,
        #     migration 024)
        # The helpers themselves are no-ops if any of those is missing,
        # so this is safe to call unconditionally.
        if tracking_enabled and campaign_id:
            try:
                consent_row = _db.query_one(
                    f"SELECT tracking_consent_given_at IS NOT NULL "
                    f"       AND tracking_consent_revoked_at IS NULL "
                    f"  AS may_track "
                    f"FROM marketing.emails "
                    f"WHERE email = {_db._sql_literal(recipient.lower())}"
                )
                may_track = bool(consent_row and consent_row.get("may_track"))
            except Exception:
                may_track = False
                logger.debug("tracking-consent lookup failed (non-fatal)",
                             exc_info=True)
            if may_track:
                try:
                    from .tracking import rewrite_links, inject_open_pixel
                    rendered_html = rewrite_links(
                        rendered_html, campaign_id, recipient, msgid_core
                    )
                    rendered_html = inject_open_pixel(
                        rendered_html, campaign_id, recipient, msgid_core
                    )
                except Exception:
                    logger.debug("tracking injection failed (non-fatal)",
                                 exc_info=True)
        msg.attach(MIMEText(rendered_html, "html", "utf-8"))

    return msgid_core, msg.as_string()


def _resolve_smtp_target(mode: SendMode) -> Tuple[str, int]:
    if mode is SendMode.SHADOW:
        return SHADOW_HOST, SHADOW_PORT
    # LIVE: pull from env, but the per-recipient RCPT TO probe is the
    # actual safeguard. SHADOW pins are constants above.
    host = os.environ.get("SMTP_HOST", "127.0.0.1")
    port = int(os.environ.get("SMTP_PORT", "465"))
    return host, port


def _update_send_row(campaign_id: str, email: str, *,
                     sent_at: bool = False, message_id: Optional[str] = None,
                     bounced_at: bool = False, bounce_reason: Optional[str] = None
                     ) -> None:
    sets: List[str] = []
    if sent_at:
        sets.append("sent_at = now()")
    if message_id is not None:
        sets.append(f"message_id = {_db._sql_literal(message_id)}")
    if bounced_at:
        sets.append("bounced_at = now()")
    if bounce_reason is not None:
        sets.append(f"bounce_reason = {_db._sql_literal(bounce_reason)}")
    if not sets:
        return
    _db.execute_via_docker(
        f"UPDATE marketing.campaign_sends "
        f"SET {', '.join(sets)} "
        f"WHERE campaign_id = {_db._sql_literal(campaign_id)}::uuid "
        f"  AND email = {_db._sql_literal(email)}"
    )
    # Lifecycle webhook event. Lazy import + try/except so webhook-bus
    # failures NEVER break the send-loop. emit_event() itself swallows
    # errors but this guards against import-time issues too.
    try:
        from .webhooks import emit_event
        if sent_at:
            emit_event("sent",
                       payload={"campaign_id": campaign_id, "email": email,
                                "message_id": message_id},
                       campaign_id=campaign_id, email=email)
        if bounced_at:
            emit_event("bounce",
                       payload={"campaign_id": campaign_id, "email": email,
                                "reason": (bounce_reason or "")[:240]},
                       campaign_id=campaign_id, email=email)
    except Exception:
        logger.debug("webhook emit failed (non-fatal)", exc_info=True)


def _send_loop(campaign: Dict[str, Any], recipients: List[Dict[str, Any]],
               mode: SendMode, rate_per_sec: int) -> Dict[str, Any]:
    sender = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "marketing@vibemind.space"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    # Load campaign template once -- per-recipient merge happens inside
    # _build_mail. Pre-validate the template at the top of the loop so a
    # bad merge field aborts BEFORE we open SMTP, not mid-batch.
    template = _resolve_template(campaign.get("template_id"))
    if template:
        # Pre-flight: render with dummy fields to surface bad {{field}}
        # references before any recipient is contacted.
        dummy = {k: f"<{k}>" for k in _ALLOWED_MERGE_FIELDS}
        for key in ("subject", "body_text", "body_html"):
            tpl = template.get(key)
            if tpl:
                try:
                    merge_render(tpl, dummy)
                except ValueError as e:
                    raise ParanoidAbort("template_validate",
                                        f"template.{key}: {e}")
    # SHADOW (Mailpit) is auth-less by design -- no creds needed. LIVE
    # speaks to Mailcow which requires SASL login.
    if mode is SendMode.LIVE and (not smtp_user or not smtp_pass):
        raise ParanoidAbort("smtp_creds", "SMTP_USER/SMTP_PASS missing in env (LIVE only)")

    smtp_host, smtp_port = _resolve_smtp_target(mode)

    claimed = _claim_send_rows(campaign["id"], recipients)
    if not claimed:
        return {"sent": 0, "bounced": 0, "claimed": 0,
                "skipped": len(recipients),
                "reason": "all recipients already have campaign_sends rows (prior run)",
                "sent_emails": [], "bounced_emails": []}

    sent: List[str] = []
    bounced: List[Tuple[str, str]] = []
    min_gap = 1.0 / max(1, rate_per_sec)
    last_t = 0.0

    ctx = ssl.create_default_context()
    if mode is SendMode.LIVE:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    # One connection for the whole loop (per-mode pinned target).
    try:
        if mode is SendMode.SHADOW:
            # Mailpit accepts plain SMTP; no auth required.
            smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
        else:
            smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=20)
            smtp.login(smtp_user, smtp_pass)
    except Exception as e:
        raise ParanoidAbort("smtp_connect",
                            f"could not connect to {smtp_host}:{smtp_port}: {e}")

    try:
        for email in claimed:
            # token-bucket
            now = time.monotonic()
            wait = (last_t + min_gap) - now
            if wait > 0:
                time.sleep(wait)
            last_t = time.monotonic()

            msgid_core = f"camp-{campaign['id'][:8]}-{uuid.uuid4().hex[:12]}"
            try:
                # Per-recipient RCPT TO probe on the SAME connection that
                # will deliver. The actual recipient -- not a stand-in.
                smtp.mail(sender)
                code, resp = smtp.rcpt(email)
                if code not in (250, 251):
                    smtp.rset()
                    bounce_reason = f"RCPT TO {email} rejected: {code} {resp!r}"
                    _update_send_row(campaign["id"], email,
                                     bounced_at=True, bounce_reason=bounce_reason[:240])
                    bounced.append((email, bounce_reason))
                    continue

                _msgid_core, rfc822 = _build_mail(
                    sender, email, campaign["name"], msgid_core,
                    template_subject=template.get("subject") or None,
                    template_body_text=template.get("body_text") or None,
                    template_body_html=template.get("body_html") or None,
                    tracking_enabled=bool(template.get("tracking_enabled")),
                    campaign_id=campaign["id"],
                )
                # smtp.data() sends DATA + the message string + closing dot.
                code, resp = smtp.data(rfc822)
                if code not in (250, 251):
                    bounce_reason = f"DATA rejected: {code} {resp!r}"
                    _update_send_row(campaign["id"], email,
                                     bounced_at=True, bounce_reason=bounce_reason[:240])
                    bounced.append((email, bounce_reason))
                    continue

                # Success -- atomic sent_at + message_id update; one
                # outbox row per send via the 004 trigger.
                _update_send_row(campaign["id"], email,
                                 sent_at=True, message_id=msgid_core + "@vibemind.space")
                sent.append(email)

            except smtplib.SMTPException as e:
                bounce_reason = f"SMTPException: {e}"
                _update_send_row(campaign["id"], email,
                                 bounced_at=True, bounce_reason=bounce_reason[:240])
                bounced.append((email, bounce_reason))
                # On connection-level error, reconnect once.
                try:
                    smtp.quit()
                except Exception:
                    pass
                try:
                    if mode is SendMode.SHADOW:
                        smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
                    else:
                        smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=20)
                        smtp.login(smtp_user, smtp_pass)
                except Exception as e2:
                    raise ParanoidAbort("smtp_reconnect", f"{smtp_host}:{smtp_port}: {e2}")
    finally:
        try:
            smtp.quit()
        except Exception:
            pass

    return {"sent": len(sent), "bounced": len(bounced),
            "claimed": len(claimed), "sent_emails": sent[:10],
            "bounced_emails": bounced[:10]}


# ─── Gate 11: Mailcow mailq audit (LIVE only) ──────────────────────────


def _mailq_audit() -> None:
    mailcow_url = os.environ.get("MAILCOW_URL", MAILCOW_URL_DEFAULT)
    api_key = os.environ.get("MAILCOW_API_KEY", "")
    if not api_key:
        # In strict-LIVE we'd FREEZE here; for Phase-2 first-version we
        # warn instead so the worker is still usable without the API key.
        logger.warning("[mailq_audit] MAILCOW_API_KEY missing -- skipping queue audit")
        return
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        mailcow_url + "/api/v1/get/mailq/all",
        headers={"X-API-Key": api_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            body = r.read()
            data = json.loads(body) if body else []
    except Exception as e:
        # Treat audit failure as FREEZE-worthy -- we cannot prove the
        # send didn't leak.
        _write_freeze(f"mailq audit failed: {e}")
        raise ParanoidAbort("mailq_audit", f"queue audit failed: {e}")

    leaked: List[str] = []
    if isinstance(data, list):
        for entry in data:
            rcpts = []
            if isinstance(entry, dict):
                # Mailcow's queue shape: {recipients: [{address: '...'}]}
                rcpts_raw = entry.get("recipients") or entry.get("recipient") or []
                if isinstance(rcpts_raw, list):
                    for rc in rcpts_raw:
                        if isinstance(rc, dict):
                            rcpts.append(rc.get("address", ""))
                        else:
                            rcpts.append(str(rc))
                elif isinstance(rcpts_raw, str):
                    rcpts.append(rcpts_raw)
            for rcpt in rcpts:
                rcpt = rcpt.lower().strip()
                if "@" not in rcpt:
                    continue
                domain = rcpt.rsplit("@", 1)[1]
                if domain not in ALLOWED_DOMAINS:
                    leaked.append(rcpt)
    if leaked:
        _write_freeze(f"mailq has external recipients: {leaked[:10]}")
        raise ParanoidAbort(
            "mailq_audit",
            f"queue contains external recipients: {leaked[:5]} -- FREEZE written",
        )


# ─── Audit ─────────────────────────────────────────────────────────────


def _audit(actor: str, action: str, target: str = "marketing.campaign_sends",
           payload: Optional[Dict[str, Any]] = None) -> None:
    payload = payload or {}
    safe_payload = {k: v for k, v in payload.items()
                    if k not in ("password", "smtp_pass", "api_key")}
    _db.execute_via_docker(
        f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
        f"VALUES ({_db._sql_literal(actor)}, "
        f"        {_db._sql_literal(action)}, "
        f"        {_db._sql_literal(target)}, "
        f"        {_db._sql_literal(json.dumps(safe_payload, default=str))}::jsonb)"
    )


# ─── Top-level entrypoint ──────────────────────────────────────────────


def run(campaign_id: str, mode: SendMode, *,
        confirm_token: Optional[str] = None,
        max_recipients: Optional[int] = None,
        rate_per_sec: int = DEFAULT_RATE_PER_SEC,
        operator: str = "send_worker") -> Dict[str, Any]:
    """Top-level entrypoint. Returns swarm-standard envelope dict."""
    if not isinstance(mode, SendMode):
        raise TypeError(f"mode must be SendMode, got {type(mode).__name__}")

    actor = f"send_worker:{operator}"
    start = time.time()

    # Gate 1+2: kill-switch + freeze (LIVE only)
    if mode is SendMode.LIVE:
        _check_kill_switch()
        _check_freeze()
        # Gate 2.5: DKIM/SPF/DMARC alignment on the sender domain
        # (LIVE only -- SHADOW goes to Mailpit which doesn't verify).
        # In Phase-1 dev mode (default) the result is informational;
        # set MARKETING_REQUIRE_DNS_ALIGNMENT=true to make it abort
        # on missing records. Either way the report is captured in
        # the audit payload below.
        sender_email = os.environ.get(
            "SMTP_FROM", os.environ.get("SMTP_USER", "marketing@vibemind.space")
        )
        from .dns_alignment import assert_alignment_or_abort
        dns_report = assert_alignment_or_abort(sender_email)
        if not dns_report["data"]["aligned"]:
            logger.warning(
                "[send] sender DNS alignment incomplete (missing: %s) -- "
                "MARKETING_REQUIRE_DNS_ALIGNMENT=false so continuing",
                dns_report["data"]["missing"],
            )
    else:
        dns_report = None

    # Gate 3: resolve campaign
    campaign = _resolve_campaign(campaign_id)
    audience_id = campaign["audience_id"]

    # Gate 4.5: assert channel is implemented + enabled (multi-channel
    # readiness check). Even in SHADOW mode -- you don't want a campaign
    # with channel='telegram' to silently go to Mailpit and then
    # surprise-deliver via email in LIVE mode because Mailpit accepted.
    # Skipped for DRY_RUN since dry-run never actually sends anywhere.
    if mode is not SendMode.DRY_RUN:
        from .channels import assert_channel_configured
        assert_channel_configured(campaign.get("channel") or "email")

    # Gate 4: snapshot recipients
    recipients = _snapshot_recipients(audience_id)
    if max_recipients is not None:
        recipients = recipients[:max(1, int(max_recipients))]

    # Gate 5: domain allowlist + Unicode lookalike defence
    _scan_domain_allowlist(recipients)

    # Gate 6: investor-lockout defense-in-depth recount
    _check_investor_locked(recipients)

    # Gate 7: confirm-token compute / verify
    expected_token = compute_confirm_token(campaign_id, audience_id, recipients)
    if mode is SendMode.LIVE:
        _verify_confirm_token(confirm_token, expected_token)

    # DRY_RUN exits here -- never opens SMTP, never writes sends.
    if mode is SendMode.DRY_RUN:
        _audit(actor, "send_campaign.dry_run", payload={
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "recipient_count": len(recipients),
            "rate_per_sec": rate_per_sec,
            "gates_passed": ["resolve_campaign", "snapshot_recipients",
                             "domain_allowlist", "investor_lockout"],
            "elapsed_s": round(time.time() - start, 3),
        })
        return {
            "mode": "dry_run",
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "recipient_count": len(recipients),
            "recipients_preview": [r["email"] for r in recipients[:5]],
            "confirm_token": expected_token,
            "summary": f"DRY_RUN ok -- {len(recipients)} reachable; pass confirm_token to live mode",
        }

    # Gate 8+9: pre-flight per mode
    if mode is SendMode.SHADOW:
        _shadow_preping()
    elif mode is SendMode.LIVE:
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        smtp_host = os.environ.get("SMTP_HOST", "127.0.0.1")
        smtp_port = int(os.environ.get("SMTP_PORT", "465"))
        sender = os.environ.get("SMTP_FROM", smtp_user)
        _postfix_loopback_probe(smtp_host, smtp_port, smtp_user, smtp_pass, sender)

    _audit(actor, f"send_campaign.{mode.value}.preflight_pass", payload={
        "campaign_id": campaign_id,
        "audience_id": audience_id,
        "recipient_count": len(recipients),
        "dns_alignment": dns_report["data"] if dns_report else None,
    })

    # Gate 10: send loop
    result = _send_loop(campaign, recipients, mode, rate_per_sec)

    # Gate 11: Mailcow mailq audit (LIVE only)
    if mode is SendMode.LIVE:
        _mailq_audit()

    # Gate 12: status flip if any actually sent
    if result["sent"] > 0:
        _db.execute_via_docker(
            f"UPDATE marketing.campaigns SET status = 'sent', sent_at = now() "
            f"WHERE id = {_db._sql_literal(campaign_id)}::uuid "
            f"  AND status <> 'sent'"
        )

    _audit(actor, f"send_campaign.{mode.value}.complete", payload={
        "campaign_id": campaign_id,
        "result": result,
        "elapsed_s": round(time.time() - start, 3),
    })

    return {
        "mode": mode.value,
        "campaign_id": campaign_id,
        "audience_id": audience_id,
        "recipient_count": len(recipients),
        "result": result,
        "summary": f"{mode.value.upper()} done -- sent={result['sent']} "
                   f"bounced={result['bounced']} claimed={result['claimed']}",
    }
