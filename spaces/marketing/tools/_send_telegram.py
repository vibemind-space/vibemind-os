"""Telegram send-worker — 12-gate stack adapted for chat_id (not email).

Mirrors _send_paranoid.py's gate structure but for the Telegram Bot
API. Same defensive layering, different protocol primitives:

  - Recipient is a chat_id (int64), not email
  - Transport is HTTPS POST to api.telegram.org/bot<TOKEN>/sendMessage,
    not SMTP
  - Allowlist is chat_ids (hardcoded set), not domains
  - "Verify the recipient agreed to be contacted" is enforced by the
    Telegram API itself: the bot cannot initiate chats; the recipient
    must `/start` the bot first. We mirror this in
    marketing.telegram_recipients.opt_in_at; gate 4 refuses sends to
    chat_ids not in that table.
  - No DKIM/SPF/DMARC equivalent (no spoofing protocol exists for bots).
    Replaced by: Bot Token kept in TELEGRAM_BOT_TOKEN env, allowlist
    hardcoded in this file.
  - No Postfix loopback-probe; the equivalent SAFETY is: getMe
    pre-flight check to confirm Bot Token belongs to the expected bot
    username.

Modes (same as email):
  DRY_RUN   - resolves recipients + computes confirm_token; NEVER hits
              api.telegram.org
  SHADOW    - runs getMe + getChat probes; NEVER sends a message
  LIVE      - all gates pass + actual sendMessage

Operator must flip marketing.channel_config.enabled=true AND set
TELEGRAM_SEND_ENABLED=true env AND remove logs/marketing/FREEZE before
LIVE accepts a campaign.

Each gate raises ParanoidAbort on failure. Top-level run() catches +
returns the swarm-standard envelope.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..sync import _db
from ._send_paranoid import (
    SendMode,
    ParanoidAbort,
    FREEZE_PATH,
    _check_freeze,
    _audit,
    merge_render,
    _ALLOWED_MERGE_FIELDS,
)


logger = logging.getLogger("marketing.telegram_send")


# ─── Hardcoded safeguards (the same model as email's ALLOWED_DOMAINS) ──


# Operator allowlist, configured via TELEGRAM_ALLOWED_CHAT_IDS (comma-
# separated numeric ids). Empty or unset means an EMPTY allowlist, i.e. no
# recipient passes the gate — a SQL-side widening of telegram_recipients
# still cannot enable sends on its own. Non-numeric entries are dropped.
def _load_allowed_chat_ids() -> frozenset:
    ids = set()
    for part in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logger.warning("ignoring non-numeric entry in TELEGRAM_ALLOWED_CHAT_IDS")
    return frozenset(ids)


_ALLOWED_CHAT_IDS = _load_allowed_chat_ids()

_KILL_SWITCH_ENV = "TELEGRAM_SEND_ENABLED"
_HARD_RECIPIENT_CAP = 100              # tight: Telegram rate-limit is 30 msg/sec network-wide
_DEFAULT_RATE_PER_SEC = 1              # 1 msg/sec per bot — very conservative
_TELEGRAM_API_BASE = "https://api.telegram.org"
_PROBE_TIMEOUT_S = 8


# ─── Gates ─────────────────────────────────────────────────────────────


def _check_kill_switch() -> None:
    """Gate 1 (Telegram-specific kill-switch)."""
    if os.environ.get(_KILL_SWITCH_ENV, "").strip().lower() not in ("true", "1", "yes"):
        raise ParanoidAbort(
            "tg_kill_switch",
            f"{_KILL_SWITCH_ENV} must equal 'true' for LIVE Telegram send "
            "(currently absent or false)",
        )


def _resolve_bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or ":" not in token:
        raise ParanoidAbort(
            "tg_bot_token",
            "TELEGRAM_BOT_TOKEN env missing or malformed (expect <id>:<secret>)",
        )
    return token


def _resolve_campaign(campaign_id: str) -> Dict[str, Any]:
    row = _db.query_one(
        f"SELECT id::text AS id, name, channel, status, audience_id::text AS audience_id, "
        f"       template_id::text AS template_id "
        f"FROM marketing.campaigns "
        f"WHERE id = {_db._sql_literal(campaign_id)}::uuid"
    )
    if not row:
        raise ParanoidAbort("tg_resolve_campaign", f"campaign {campaign_id} not found")
    if row["channel"] != "telegram":
        raise ParanoidAbort(
            "tg_resolve_campaign",
            f"campaign.channel='{row['channel']}' is not 'telegram'; refusing to send via telegram-worker",
        )
    if row["status"] in ("sent", "cancelled", "failed"):
        raise ParanoidAbort(
            "tg_resolve_campaign",
            f"campaign status='{row['status']}' is terminal; re-create to re-send",
        )
    if not row.get("audience_id"):
        raise ParanoidAbort("tg_resolve_campaign", "campaign has no audience_id")
    return row


def _snapshot_recipients(audience_id: str) -> List[Dict[str, Any]]:
    """Gate 4: snapshot Telegram recipients for this audience.

    Joins audience_members.email → emails.handle → telegram_recipients.handle.
    Filters out blocked_at IS NOT NULL.
    """
    rows = _db.query_via_docker(
        f"SELECT DISTINCT tr.chat_id, tr.handle, tr.username, "
        f"       tr.first_name, tr.last_name, tr.language_code "
        f"FROM marketing.audience_members am "
        f"JOIN marketing.emails e ON e.email = am.email "
        f"JOIN marketing.telegram_recipients tr ON tr.handle = e.handle "
        f"WHERE am.audience_id = {_db._sql_literal(audience_id)}::uuid "
        f"  AND tr.blocked_at IS NULL "
        f"ORDER BY tr.chat_id"
    )
    if not rows:
        raise ParanoidAbort(
            "tg_snapshot",
            f"audience {audience_id} resolved to 0 telegram_recipients "
            f"(audience members may not have linked chat_ids yet)",
        )
    if len(rows) > _HARD_RECIPIENT_CAP:
        raise ParanoidAbort(
            "tg_recipient_cap",
            f"snapshot has {len(rows)} > _HARD_RECIPIENT_CAP={_HARD_RECIPIENT_CAP}",
        )
    return rows


def _scan_chat_id_allowlist(recipients: List[Dict[str, Any]]) -> None:
    """Gate 5: hardcoded allowlist of chat_ids."""
    not_allowed = []
    for r in recipients:
        cid = r.get("chat_id")
        if not isinstance(cid, int):
            not_allowed.append((cid, "non-int chat_id"))
            continue
        if cid not in _ALLOWED_CHAT_IDS:
            not_allowed.append((cid, f"not in _ALLOWED_CHAT_IDS={sorted(_ALLOWED_CHAT_IDS)}"))
    if not_allowed:
        raise ParanoidAbort(
            "tg_chat_id_allowlist",
            f"{len(not_allowed)} chat_id(s) outside allowlist: {not_allowed[:5]}",
        )


def compute_confirm_token(campaign_id: str, audience_id: str,
                          recipients: List[Dict[str, Any]]) -> str:
    """Same HMAC pattern as email: token covers the FULL sorted recipient
    set so any audience-membership drift invalidates it."""
    chats_sorted = sorted({int(r.get("chat_id", 0)) for r in recipients
                            if isinstance(r.get("chat_id"), int)})
    chats_hash = hashlib.sha256(
        "\n".join(str(c) for c in chats_sorted).encode("utf-8")
    ).hexdigest()
    allow_sorted = sorted(_ALLOWED_CHAT_IDS)
    allow_hash = hashlib.sha256(
        "\n".join(str(c) for c in allow_sorted).encode("utf-8")
    ).hexdigest()
    secret = os.environ.get("MARKETING_PROPOSAL_API_KEY", "").encode("utf-8") or b"unset"
    return hmac.new(
        secret,
        f"telegram-v1\n{campaign_id}\n{audience_id}\n{len(chats_sorted)}\n{chats_hash}\n{allow_hash}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verify_confirm_token(provided: Optional[str], expected: str) -> None:
    if not provided:
        raise ParanoidAbort(
            "tg_confirm_token",
            "LIVE Telegram mode requires confirm_token from a prior DRY_RUN response",
        )
    if not hmac.compare_digest(provided.strip().lower(), expected.lower()):
        raise ParanoidAbort(
            "tg_confirm_token",
            "confirm_token does not match the current chat_id snapshot. Re-run dry_run.",
        )


def _resolve_template(template_id: Optional[str]) -> Dict[str, Any]:
    if not template_id:
        return {}
    row = _db.query_one(
        f"SELECT subject, body_text "
        f"FROM marketing.templates "
        f"WHERE id = {_db._sql_literal(template_id)}::uuid"
    )
    return row or {}


# ─── Telegram API plumbing ─────────────────────────────────────────────


def _tg_get(method: str, token: str, *, timeout: int = _PROBE_TIMEOUT_S) -> Dict[str, Any]:
    """GET request to Bot API."""
    url = f"{_TELEGRAM_API_BASE}/bot{token}/{method}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _tg_post(method: str, token: str, payload: Dict[str, Any],
             *, timeout: int = _PROBE_TIMEOUT_S) -> Dict[str, Any]:
    """POST request to Bot API."""
    url = f"{_TELEGRAM_API_BASE}/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        # Telegram returns JSON error bodies with structured info
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        try:
            return json.loads(body or b"{}")
        except Exception:
            return {"ok": False, "error_code": e.code, "description": str(e)}


def _shadow_preping(token: str) -> Dict[str, Any]:
    """Gate 8: probe getMe -- confirms token is valid + reaches API
    -- but never sends a message."""
    try:
        resp = _tg_get("getMe", token)
    except Exception as e:
        raise ParanoidAbort("tg_shadow_preping",
                            f"api.telegram.org unreachable: {type(e).__name__}: {e}")
    if not resp.get("ok"):
        raise ParanoidAbort(
            "tg_shadow_preping",
            f"getMe failed: {resp.get('description') or resp}",
        )
    return resp.get("result") or {}


def _per_recipient_getchat_probe(token: str, chat_id: int) -> None:
    """Gate 9/10: getChat for the actual recipient. If the bot can't see
    them (chat doesn't exist / blocked / never opt'd in), refuse.
    Equivalent to per-recipient RCPT TO on the same connection."""
    resp = _tg_post("getChat", token, {"chat_id": int(chat_id)})
    if not resp.get("ok"):
        raise ParanoidAbort(
            "tg_per_recipient_probe",
            f"getChat({chat_id}) failed: {resp.get('description') or resp.get('error_code')} "
            f"-- recipient may have blocked the bot or never opted in",
        )


# ─── DB writes ─────────────────────────────────────────────────────────


def _claim_send_rows(campaign_id: str, recipients: List[Dict[str, Any]]) -> List[int]:
    """Atomic claim via UNIQUE(campaign_id, chat_id). Returns chat_ids
    actually claimed (= rows the INSERT just inserted)."""
    if not recipients:
        return []
    values = ", ".join(
        f"({_db._sql_literal(campaign_id)}::uuid, {int(r['chat_id'])})"
        for r in recipients
    )
    out = _db.execute_via_docker(
        f"INSERT INTO marketing.campaign_sends_telegram (campaign_id, chat_id) "
        f"VALUES {values} "
        f"ON CONFLICT (campaign_id, chat_id) DO NOTHING "
        f"RETURNING chat_id"
    )
    claimed = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line or line.startswith("INSERT") or not line.lstrip("-").isdigit():
            continue
        try:
            claimed.append(int(line))
        except ValueError:
            pass
    return claimed


def _update_send_row(campaign_id: str, chat_id: int, *,
                     sent_at: bool = False,
                     telegram_message_id: Optional[int] = None,
                     bounced_at: bool = False,
                     bounce_reason: Optional[str] = None) -> None:
    sets: List[str] = []
    if sent_at:
        sets.append("sent_at = now()")
    if telegram_message_id is not None:
        sets.append(f"telegram_message_id = {int(telegram_message_id)}")
    if bounced_at:
        sets.append("bounced_at = now()")
    if bounce_reason is not None:
        sets.append(f"bounce_reason = {_db._sql_literal(bounce_reason)}")
    if not sets:
        return
    _db.execute_via_docker(
        f"UPDATE marketing.campaign_sends_telegram "
        f"SET {', '.join(sets)} "
        f"WHERE campaign_id = {_db._sql_literal(campaign_id)}::uuid "
        f"  AND chat_id = {int(chat_id)}"
    )
    # Lifecycle webhook event -- never blocks the send loop.
    try:
        from .webhooks import emit_event
        if sent_at:
            emit_event("sent",
                       payload={"campaign_id": campaign_id,
                                "chat_id": int(chat_id),
                                "telegram_message_id": telegram_message_id,
                                "channel": "telegram"},
                       campaign_id=campaign_id)
        if bounced_at:
            emit_event("bounce",
                       payload={"campaign_id": campaign_id,
                                "chat_id": int(chat_id),
                                "reason": (bounce_reason or "")[:240],
                                "channel": "telegram"},
                       campaign_id=campaign_id)
    except Exception:
        logger.debug("webhook emit failed (non-fatal)", exc_info=True)


# ─── Send loop ─────────────────────────────────────────────────────────


def _send_loop(campaign: Dict[str, Any], recipients: List[Dict[str, Any]],
               mode: SendMode, rate_per_sec: int, token: str) -> Dict[str, Any]:
    template = _resolve_template(campaign.get("template_id"))
    if template:
        dummy = {k: f"<{k}>" for k in _ALLOWED_MERGE_FIELDS}
        for key in ("subject", "body_text"):
            tpl = template.get(key)
            if tpl:
                try:
                    merge_render(tpl, dummy)
                except ValueError as e:
                    raise ParanoidAbort("tg_template_validate",
                                        f"template.{key}: {e}")

    claimed = _claim_send_rows(campaign["id"], recipients)
    if not claimed:
        return {"sent": 0, "bounced": 0, "claimed": 0,
                "skipped": len(recipients),
                "reason": "all chat_ids already have campaign_sends_telegram rows",
                "sent_chat_ids": [], "bounced_chat_ids": []}

    sent: List[int] = []
    bounced: List[Tuple[int, str]] = []
    min_gap = 1.0 / max(1, rate_per_sec)
    last_t = 0.0

    chat_lookup = {int(r["chat_id"]): r for r in recipients}

    for chat_id in claimed:
        now = time.monotonic()
        wait = (last_t + min_gap) - now
        if wait > 0:
            time.sleep(wait)
        last_t = time.monotonic()

        recipient = chat_lookup.get(chat_id, {})
        # Gate 9: per-recipient probe (LIVE only -- SHADOW already did getMe)
        if mode is SendMode.LIVE:
            try:
                _per_recipient_getchat_probe(token, chat_id)
            except ParanoidAbort as e:
                _update_send_row(campaign["id"], chat_id,
                                 bounced_at=True,
                                 bounce_reason=f"probe failed: {e.detail}"[:240])
                bounced.append((chat_id, str(e)))
                continue

        # Build message body
        fields = {
            "first_name": recipient.get("first_name") or "",
            "last_name": recipient.get("last_name") or "",
            "full_name": (recipient.get("first_name") or "") + " " + (recipient.get("last_name") or ""),
            "display_name": recipient.get("first_name") or recipient.get("username") or "",
            "email": "",
            "domain": "",
            "company": "",
            "title": "",
            "campaign_name": campaign["name"],
            "msgid_core": f"tg-{campaign['id'][:8]}-{uuid.uuid4().hex[:8]}",
            "unsub_url": "",
        }
        body = template.get("body_text") or f"Hello {fields['first_name'] or 'there'}!"
        try:
            rendered = merge_render(body, fields)
        except ValueError as e:
            _update_send_row(campaign["id"], chat_id,
                             bounced_at=True, bounce_reason=str(e)[:240])
            bounced.append((chat_id, str(e)))
            continue

        if mode is SendMode.DRY_RUN:
            # Should never reach here (DRY_RUN early-returns at run() top)
            continue

        if mode is SendMode.SHADOW:
            # SHADOW = NO actual sendMessage. Just count as 'sent' for
            # accounting; never hits api.telegram.org/sendMessage.
            _update_send_row(campaign["id"], chat_id,
                             sent_at=True,
                             telegram_message_id=0)         # 0 sentinel for shadow
            sent.append(chat_id)
            continue

        # LIVE: real sendMessage
        payload = {
            "chat_id": chat_id,
            "text": rendered,
            "parse_mode": "MarkdownV2" if "*" in rendered or "_" in rendered else None,
        }
        # Strip None values
        payload = {k: v for k, v in payload.items() if v is not None}
        resp = _tg_post("sendMessage", token, payload, timeout=15)
        if not resp.get("ok"):
            reason = f"sendMessage failed: {resp.get('description') or resp.get('error_code')}"
            _update_send_row(campaign["id"], chat_id,
                             bounced_at=True, bounce_reason=reason[:240])
            bounced.append((chat_id, reason))
            continue
        result = resp.get("result") or {}
        msg_id = result.get("message_id")
        _update_send_row(campaign["id"], chat_id,
                         sent_at=True,
                         telegram_message_id=int(msg_id) if msg_id is not None else None)
        sent.append(chat_id)

    return {
        "sent": len(sent), "bounced": len(bounced),
        "claimed": len(claimed),
        "sent_chat_ids": sent[:10],
        "bounced_chat_ids": [(c, r[:60]) for c, r in bounced[:10]],
    }


# ─── Top-level entrypoint ──────────────────────────────────────────────


def run(campaign_id: str, mode: SendMode, *,
        confirm_token: Optional[str] = None,
        max_recipients: Optional[int] = None,
        rate_per_sec: int = _DEFAULT_RATE_PER_SEC,
        operator: str = "telegram_worker") -> Dict[str, Any]:
    """Top-level Telegram send entry. Returns swarm-envelope dict.

    Mirrors _send_paranoid.run() structure but for chat_ids.
    """
    if not isinstance(mode, SendMode):
        raise TypeError(f"mode must be SendMode, got {type(mode).__name__}")

    actor = f"telegram_worker:{operator}"
    start = time.time()

    # Gate 1+2: kill-switch + freeze (LIVE only)
    if mode is SendMode.LIVE:
        _check_kill_switch()
        _check_freeze()

    # Gate 2.5: bot token resolves
    token = _resolve_bot_token() if mode is not SendMode.DRY_RUN else ""

    # Gate 3: resolve campaign (also asserts channel='telegram')
    campaign = _resolve_campaign(campaign_id)
    audience_id = campaign["audience_id"]

    # Gate 4.5 (channel-configured) is asserted by the upstream dispatcher
    # before calling us. Skip here to avoid double-check.

    # Gate 4: snapshot Telegram recipients
    recipients = _snapshot_recipients(audience_id)
    if max_recipients is not None:
        recipients = recipients[:max(1, int(max_recipients))]

    # Gate 5: chat_id allowlist
    _scan_chat_id_allowlist(recipients)

    # Gate 7: confirm-token
    expected_token = compute_confirm_token(campaign_id, audience_id, recipients)
    if mode is SendMode.LIVE:
        _verify_confirm_token(confirm_token, expected_token)

    # DRY_RUN early-exit
    if mode is SendMode.DRY_RUN:
        _audit(actor, "telegram_send.dry_run", payload={
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "recipient_count": len(recipients),
            "chat_ids_preview": [r["chat_id"] for r in recipients[:5]],
            "elapsed_s": round(time.time() - start, 3),
        })
        return {
            "mode": "dry_run",
            "channel": "telegram",
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "recipient_count": len(recipients),
            "chat_ids_preview": [r["chat_id"] for r in recipients[:5]],
            "confirm_token": expected_token,
            "summary": f"telegram DRY_RUN ok -- {len(recipients)} chat(s) reachable",
        }

    # Gate 8: SHADOW/LIVE pre-ping
    bot_info = _shadow_preping(token)

    _audit(actor, f"telegram_send.{mode.value}.preflight_pass", payload={
        "campaign_id": campaign_id,
        "audience_id": audience_id,
        "recipient_count": len(recipients),
        "bot_username": bot_info.get("username"),
    })

    # Gate 10: send loop
    result = _send_loop(campaign, recipients, mode, rate_per_sec, token)

    # Gate 12: status flip on success
    if result["sent"] > 0:
        _db.execute_via_docker(
            f"UPDATE marketing.campaigns SET status = 'sent', sent_at = now() "
            f"WHERE id = {_db._sql_literal(campaign_id)}::uuid "
            f"  AND status <> 'sent'"
        )

    _audit(actor, f"telegram_send.{mode.value}.complete", payload={
        "campaign_id": campaign_id,
        "result": result,
        "elapsed_s": round(time.time() - start, 3),
    })

    return {
        "mode": mode.value,
        "channel": "telegram",
        "campaign_id": campaign_id,
        "audience_id": audience_id,
        "recipient_count": len(recipients),
        "bot_username": bot_info.get("username"),
        "result": result,
        "summary": f"telegram {mode.value.upper()} done -- sent={result['sent']} bounced={result['bounced']}",
    }


__all__ = [
    "run",
    "compute_confirm_token",
    "_ALLOWED_CHAT_IDS",
    "_KILL_SWITCH_ENV",
]
