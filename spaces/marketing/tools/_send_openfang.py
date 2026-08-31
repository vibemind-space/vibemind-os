"""Generic multi-channel send-worker dispatching via OpenFang's channel_send tool.

This is the OpenFang-transport equivalent of _send_paranoid.py (email) and
_send_telegram.py (telegram). Instead of speaking SMTP or api.telegram.org
directly, it asks a dedicated OpenFang agent (`marketing-sender`) to
invoke its `channel_send` tool with a specific (channel, recipient, body)
tuple.

Why an agent and not a direct REST endpoint:
    OpenFang doesn't expose POST /api/channels/{name}/send for external
    callers. The only path into a channel-adapter is the `channel_send`
    agent-tool. So we instantiate a dedicated, instruct-only agent
    (system prompt enforces: "parse JSON → exactly one channel_send call →
    return result"), and call it via POST /api/agents/{id}/message.

Hard properties preserved from _send_paranoid / _send_telegram:
    Gate 1   — kill-switch via env (MARKETING_SEND_ENABLED).
    Gate 1.5 — freeze-file (shared FREEZE_PATH).
    Gate 2   — agent resolves (marketing-sender registered + Running).
    Gate 3   — campaign resolves; channel is openfang_capable=true in
               marketing.channel_config.
    Gate 4   — recipient snapshot from per-channel join.
    Gate 5   — recipient cap enforced (_HARD_RECIPIENT_CAP).
    Gate 6   — signed allowlist: every (channel, recipient_id) verified
               by HMAC-SHA256 over `MARKETING_PROPOSAL_API_KEY`. Tampered
               rows refused.
    Gate 7   — confirm-token (HMAC) over the sorted recipient set + allowlist.
    Gate 8   — shadow preping (OpenFang health + agent.ready check).
    Gate 9   — per-recipient probe is delegated to OpenFang's channel adapter
               (it'll fail the channel_send call cleanly if the recipient is
               unreachable; we record the bounce in campaign_sends_openfang).
    Gate 10  — atomic claim via UNIQUE(campaign_id, recipient_id).
    Gate 11  — rate-limit (per-campaign, default 1/s).
    Gate 12  — campaign.status flip + audit row.

Constraints carried over from email/telegram:
    - DRY_RUN  : resolves recipients + computes confirm_token; never hits OpenFang.
    - SHADOW   : agent.ready check ONLY (no channel_send call).
    - LIVE     : all gates pass + channel_send call.
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
from .sign_recipient import verify_recipient_sig


logger = logging.getLogger("marketing.openfang_send")


# ─── Constants ─────────────────────────────────────────────────────────


_KILL_SWITCH_ENV = "MARKETING_SEND_ENABLED"     # shared with email
_HARD_RECIPIENT_CAP = 100                       # tight
_DEFAULT_RATE_PER_SEC = 1                       # one msg/sec across channels
_OPENFANG_AGENT_NAME = "marketing-sender"
_OPENFANG_DEFAULT_BASE = "http://127.0.0.1:4200"
_OPENFANG_HEALTH_TIMEOUT_S = 6
_OPENFANG_SEND_TIMEOUT_S = 30


# ─── HTTP plumbing to OpenFang ────────────────────────────────────────


def _openfang_base() -> str:
    return os.environ.get("OPENFANG_BASE_URL", _OPENFANG_DEFAULT_BASE)


def _openfang_auth_headers() -> Dict[str, str]:
    """Optional Bearer auth if MARKETING_OPENFANG_API_KEY is set."""
    key = os.environ.get("MARKETING_OPENFANG_API_KEY", "").strip()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _http_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None,
               *, timeout: int) -> Dict[str, Any]:
    data: Optional[bytes] = None
    headers = {"Accept": "application/json"}
    headers.update(_openfang_auth_headers())
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read() or b"{}"
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return {"_http_status": e.code, "_body": body.decode("utf-8", "replace")}
    except Exception as e:
        return {"_transport_error": f"{type(e).__name__}: {e}"}
    try:
        return json.loads(body)
    except Exception:
        return {"_body": body.decode("utf-8", "replace")}


# ─── Gates ─────────────────────────────────────────────────────────────


def _check_kill_switch() -> None:
    """Gate 1 -- shared with email (same MARKETING_SEND_ENABLED env)."""
    if os.environ.get(_KILL_SWITCH_ENV, "").strip().lower() not in ("true", "1", "yes"):
        raise ParanoidAbort(
            "of_kill_switch",
            f"{_KILL_SWITCH_ENV} must equal 'true' for LIVE OpenFang send",
        )


def _resolve_agent_id(base: str) -> str:
    """Gate 2: marketing-sender agent must exist + be Running."""
    resp = _http_json("GET", f"{base}/api/agents", timeout=_OPENFANG_HEALTH_TIMEOUT_S)
    if not isinstance(resp, (list,)) and not (isinstance(resp, dict)
                                              and "agents" in resp):
        # Try treating the dict-with-error as failure
        if isinstance(resp, dict) and ("_http_status" in resp or "_transport_error" in resp):
            raise ParanoidAbort(
                "of_agent_resolve",
                f"OpenFang /api/agents unreachable: {resp}",
            )
        # Some installations wrap as {"agents": [...]}; some bare-list.
        agents = []
    else:
        agents = resp if isinstance(resp, list) else resp.get("agents", [])

    for a in agents:
        if not isinstance(a, dict):
            continue
        if a.get("name") == _OPENFANG_AGENT_NAME:
            if a.get("state") not in ("Running", "running"):
                raise ParanoidAbort(
                    "of_agent_resolve",
                    f"{_OPENFANG_AGENT_NAME} found but state={a.get('state')!r} "
                    "(expected Running)",
                )
            agent_id = a.get("id")
            if not agent_id:
                raise ParanoidAbort(
                    "of_agent_resolve",
                    f"{_OPENFANG_AGENT_NAME} has no id field",
                )
            return str(agent_id)
    raise ParanoidAbort(
        "of_agent_resolve",
        f"{_OPENFANG_AGENT_NAME!r} not registered in OpenFang. "
        f"Apply agents/marketing-sender/agent.toml + restart OpenFang.",
    )


def _resolve_campaign(campaign_id: str) -> Dict[str, Any]:
    """Gate 3: campaign resolves; channel is openfang_capable=true."""
    row = _db.query_one(
        f"SELECT c.id::text AS id, c.name, c.channel, c.status, "
        f"       c.audience_id::text AS audience_id, "
        f"       c.template_id::text AS template_id, "
        f"       cc.openfang_capable, cc.enabled, "
        f"       cc.openfang_channel_name "
        f"FROM marketing.campaigns c "
        f"LEFT JOIN marketing.channel_config cc ON cc.channel = c.channel "
        f"WHERE c.id = {_db._sql_literal(campaign_id)}::uuid"
    )
    if not row:
        raise ParanoidAbort("of_resolve_campaign", f"campaign {campaign_id} not found")
    if row["status"] in ("sent", "cancelled", "failed"):
        raise ParanoidAbort(
            "of_resolve_campaign",
            f"campaign status='{row['status']}' is terminal; re-create to re-send",
        )
    if not row.get("audience_id"):
        raise ParanoidAbort("of_resolve_campaign", "campaign has no audience_id")
    if not row.get("openfang_capable"):
        raise ParanoidAbort(
            "of_resolve_campaign",
            f"channel={row.get('channel')!r} is not openfang_capable. "
            "Apply a migration that flips openfang_capable=true before sending.",
        )
    if not row.get("enabled"):
        raise ParanoidAbort(
            "of_resolve_campaign",
            f"channel={row.get('channel')!r} has enabled=false. "
            "Operator must turn on the soft gate.",
        )
    if not row.get("openfang_channel_name"):
        raise ParanoidAbort(
            "of_resolve_campaign",
            f"channel={row.get('channel')!r} has openfang_channel_name=NULL "
            "(should be set by migration 018; default = channel column).",
        )
    return row


def _snapshot_recipients(campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gate 4: recipients = signed-allowlist rows for this channel, joined
    optionally with audience-membership.

    For OpenFang-mediated sends we do NOT mine marketing.emails for
    recipients: the channel is a notification target, not an outreach
    audience. The allowlist IS the audience.

    A campaign.audience_id is still required (template+context binding),
    but the allowlist defines who actually receives.
    """
    channel = campaign["channel"]
    rows = _db.query_via_docker(
        f"SELECT recipient_id, label, approved_by, hmac_sig "
        f"FROM marketing.channel_recipient_allowlist "
        f"WHERE channel = {_db._sql_literal(channel)} "
        f"  AND revoked_at IS NULL "
        f"ORDER BY recipient_id"
    )
    if not rows:
        raise ParanoidAbort(
            "of_snapshot",
            f"channel={channel!r} has 0 signed allowlist entries. "
            f"Use tools/sign_recipient.py to add at least one.",
        )
    if len(rows) > _HARD_RECIPIENT_CAP:
        raise ParanoidAbort(
            "of_recipient_cap",
            f"snapshot has {len(rows)} > _HARD_RECIPIENT_CAP={_HARD_RECIPIENT_CAP}",
        )
    return rows


def _verify_signed_allowlist(channel: str,
                              recipients: List[Dict[str, Any]]) -> None:
    """Gate 6: HMAC-verify every (channel, recipient_id) row.

    Any failure aborts the whole send. We never partial-send on
    tampered allowlists.
    """
    secret = os.environ.get("MARKETING_PROPOSAL_API_KEY", "").strip()
    if not secret or len(secret) < 32:
        raise ParanoidAbort(
            "of_allowlist_secret",
            "MARKETING_PROPOSAL_API_KEY must be >= 32 chars to verify "
            "channel_recipient_allowlist signatures.",
        )
    secret_b = secret.encode("utf-8")
    failed: List[Tuple[str, str]] = []
    for r in recipients:
        rid = r.get("recipient_id")
        ab = r.get("approved_by")
        sig = r.get("hmac_sig")
        if not rid or not ab or not sig:
            failed.append((str(rid), "missing recipient_id/approved_by/hmac_sig"))
            continue
        ok = verify_recipient_sig(channel, str(rid), str(ab), str(sig),
                                  secret=secret_b)
        if not ok:
            failed.append((str(rid), "HMAC verify failed"))
    if failed:
        raise ParanoidAbort(
            "of_allowlist_verify",
            f"{len(failed)} allowlist row(s) failed HMAC verify: {failed[:5]}",
        )


def compute_confirm_token(campaign_id: str, audience_id: str,
                          channel: str,
                          recipients: List[Dict[str, Any]]) -> str:
    """Same HMAC pattern as email + telegram: token covers the FULL sorted
    recipient set so any membership drift invalidates it."""
    rids_sorted = sorted({str(r.get("recipient_id", "")) for r in recipients})
    rids_hash = hashlib.sha256(
        "\n".join(rids_sorted).encode("utf-8")
    ).hexdigest()
    secret = os.environ.get("MARKETING_PROPOSAL_API_KEY", "").encode("utf-8") or b"unset"
    return hmac.new(
        secret,
        f"openfang-v1\n{channel}\n{campaign_id}\n{audience_id}\n"
        f"{len(rids_sorted)}\n{rids_hash}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verify_confirm_token(provided: Optional[str], expected: str) -> None:
    if not provided:
        raise ParanoidAbort(
            "of_confirm_token",
            "LIVE OpenFang mode requires confirm_token from a prior DRY_RUN response",
        )
    if not hmac.compare_digest(provided.strip().lower(), expected.lower()):
        raise ParanoidAbort(
            "of_confirm_token",
            "confirm_token does not match the current recipient snapshot. Re-run dry_run.",
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


# ─── Atomic claim ─────────────────────────────────────────────────────


def _claim_send_rows(campaign_id: str, channel: str,
                     recipients: List[Dict[str, Any]]) -> List[str]:
    """Atomic claim via UNIQUE(campaign_id, recipient_id) on
    campaign_sends_openfang. Returns recipient_ids actually claimed.
    """
    if not recipients:
        return []
    # marketing.campaign_sends_openfang is created by migration 018.5
    # (see end of 018_openfang_adapter_mapping.sql).
    values = ", ".join(
        f"({_db._sql_literal(campaign_id)}::uuid, "
        f"{_db._sql_literal(channel)}, "
        f"{_db._sql_literal(str(r['recipient_id']))})"
        for r in recipients
    )
    out = _db.execute_via_docker(
        f"INSERT INTO marketing.campaign_sends_openfang "
        f"(campaign_id, channel, recipient_id) "
        f"VALUES {values} "
        f"ON CONFLICT (campaign_id, channel, recipient_id) DO NOTHING "
        f"RETURNING recipient_id"
    )
    claimed = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line or line.startswith("INSERT") or line.startswith("---"):
            continue
        # recipient_id is text; ignore the "INSERT N M" footer
        if line.lower().startswith("recipient_id"):
            continue
        claimed.append(line)
    return claimed


def _update_send_row(campaign_id: str, channel: str, recipient_id: str, *,
                     sent_at: bool = False,
                     openfang_message_ref: Optional[str] = None,
                     bounced_at: bool = False,
                     bounce_reason: Optional[str] = None) -> None:
    sets: List[str] = []
    if sent_at:
        sets.append("sent_at = now()")
    if openfang_message_ref is not None:
        sets.append(f"openfang_message_ref = {_db._sql_literal(openfang_message_ref[:240])}")
    if bounced_at:
        sets.append("bounced_at = now()")
    if bounce_reason is not None:
        sets.append(f"bounce_reason = {_db._sql_literal(bounce_reason[:240])}")
    if not sets:
        return
    _db.execute_via_docker(
        f"UPDATE marketing.campaign_sends_openfang "
        f"SET {', '.join(sets)} "
        f"WHERE campaign_id = {_db._sql_literal(campaign_id)}::uuid "
        f"  AND channel = {_db._sql_literal(channel)} "
        f"  AND recipient_id = {_db._sql_literal(recipient_id)}"
    )
    # Lifecycle webhook event -- never blocks the send loop.
    try:
        from .webhooks import emit_event
        if sent_at:
            emit_event("sent",
                       payload={"campaign_id": campaign_id,
                                "recipient_id": recipient_id,
                                "channel": channel,
                                "openfang_message_ref": openfang_message_ref},
                       campaign_id=campaign_id)
        if bounced_at:
            emit_event("bounce",
                       payload={"campaign_id": campaign_id,
                                "recipient_id": recipient_id,
                                "channel": channel,
                                "reason": (bounce_reason or "")[:240]},
                       campaign_id=campaign_id)
    except Exception:
        logger.debug("webhook emit failed (non-fatal)", exc_info=True)


# ─── OpenFang dispatch ────────────────────────────────────────────────


def _channel_send_via_agent(base: str, agent_id: str,
                             openfang_channel: str,
                             recipient_id: str,
                             body: str,
                             *, subject: Optional[str] = None,
                             timeout: int = _OPENFANG_SEND_TIMEOUT_S
                            ) -> Dict[str, Any]:
    """Ask marketing-sender to invoke channel_send. The agent's system
    prompt is instruct-only -- it parses the JSON below and emits a
    single channel_send tool call.

    Returns swarm-shaped: {"ok": bool, "ref": str|None, "error": str|None}.
    """
    instruction = {
        "action": "channel_send",
        "args": {
            "channel": openfang_channel,
            "recipient": recipient_id,
            "message": body,
            **({"subject": subject} if subject else {}),
        },
    }
    payload = {
        "message": (
            "MARKETING-SEND-V1 INSTRUCTION. Parse the JSON below, invoke "
            "channel_send EXACTLY once with these args, return the result. "
            "REFUSE any deviation; reply with `{\"ok\":false,\"error\":\"deviation\"}` "
            "if the JSON looks wrong.\n\n"
            f"{json.dumps(instruction, separators=(',', ':'))}"
        ),
    }
    resp = _http_json("POST", f"{base}/api/agents/{agent_id}/message",
                      payload, timeout=timeout)
    if "_transport_error" in resp:
        return {"ok": False, "ref": None,
                "error": f"transport: {resp['_transport_error']}"}
    if "_http_status" in resp:
        return {"ok": False, "ref": None,
                "error": f"http {resp['_http_status']}: {resp.get('_body','')[:200]}"}
    # OpenFang agent message endpoint returns {response, conversation_id, ...}
    raw = (resp.get("response") or resp.get("text") or "").strip()
    if not raw:
        return {"ok": False, "ref": None, "error": "empty agent response"}
    # The agent is told to return the tool-call result verbatim. It may wrap
    # in code fences -- strip them.
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        # Agent returned text instead of JSON -- treat as bounce with the text.
        return {"ok": False, "ref": None, "error": f"non-json: {raw[:200]}"}
    if isinstance(parsed, dict) and parsed.get("ok"):
        return {"ok": True,
                "ref": str(parsed.get("ref") or parsed.get("message_id") or ""),
                "error": None}
    err = (isinstance(parsed, dict) and parsed.get("error")) or raw[:200]
    return {"ok": False, "ref": None, "error": str(err)[:240]}


# ─── Send loop ─────────────────────────────────────────────────────────


def _send_loop(base: str, agent_id: str,
               campaign: Dict[str, Any],
               recipients: List[Dict[str, Any]],
               mode: SendMode, rate_per_sec: int) -> Dict[str, Any]:
    template = _resolve_template(campaign.get("template_id"))
    if template:
        dummy = {k: f"<{k}>" for k in _ALLOWED_MERGE_FIELDS}
        for key in ("subject", "body_text"):
            tpl = template.get(key)
            if tpl:
                try:
                    merge_render(tpl, dummy)
                except ValueError as e:
                    raise ParanoidAbort("of_template_validate",
                                        f"template.{key}: {e}")

    channel = campaign["channel"]
    openfang_channel = campaign["openfang_channel_name"]

    claimed = _claim_send_rows(campaign["id"], channel, recipients)
    if not claimed:
        return {"sent": 0, "bounced": 0, "claimed": 0,
                "skipped": len(recipients),
                "reason": "all recipient_ids already have campaign_sends_openfang rows",
                "sent_recipient_ids": [], "bounced_recipient_ids": []}

    sent: List[str] = []
    bounced: List[Tuple[str, str]] = []
    min_gap = 1.0 / max(1, rate_per_sec)
    last_t = 0.0

    rcpt_lookup = {str(r["recipient_id"]): r for r in recipients}

    for rid in claimed:
        now = time.monotonic()
        wait = (last_t + min_gap) - now
        if wait > 0:
            time.sleep(wait)
        last_t = time.monotonic()

        recipient = rcpt_lookup.get(rid, {})
        fields = {
            "first_name": "",
            "last_name": "",
            "full_name": "",
            "display_name": recipient.get("label") or rid,
            "email": "",
            "domain": "",
            "company": "",
            "title": "",
            "campaign_name": campaign["name"],
            "msgid_core": f"of-{campaign['id'][:8]}-{uuid.uuid4().hex[:8]}",
            "unsub_url": "",
        }
        body_tpl = template.get("body_text") or f"[{campaign['name']}] notification"
        try:
            rendered = merge_render(body_tpl, fields)
        except ValueError as e:
            _update_send_row(campaign["id"], channel, rid,
                             bounced_at=True, bounce_reason=str(e))
            bounced.append((rid, str(e)))
            continue

        subject = None
        if template.get("subject"):
            try:
                subject = merge_render(template["subject"], fields)
            except ValueError:
                subject = template["subject"]

        if mode is SendMode.SHADOW:
            # SHADOW = mark claimed rows as sent without calling OpenFang.
            _update_send_row(campaign["id"], channel, rid,
                             sent_at=True,
                             openfang_message_ref="shadow")
            sent.append(rid)
            continue

        # LIVE
        result = _channel_send_via_agent(
            base, agent_id, openfang_channel, rid, rendered,
            subject=subject,
        )
        if result["ok"]:
            _update_send_row(campaign["id"], channel, rid,
                             sent_at=True,
                             openfang_message_ref=result.get("ref"))
            sent.append(rid)
        else:
            _update_send_row(campaign["id"], channel, rid,
                             bounced_at=True,
                             bounce_reason=result.get("error") or "unknown")
            bounced.append((rid, result.get("error") or "unknown"))

    return {
        "sent": len(sent), "bounced": len(bounced),
        "claimed": len(claimed),
        "sent_recipient_ids": sent[:10],
        "bounced_recipient_ids": [(r, e[:60]) for r, e in bounced[:10]],
    }


# ─── Top-level entrypoint ──────────────────────────────────────────────


def run(campaign_id: str, mode: SendMode, *,
        confirm_token: Optional[str] = None,
        max_recipients: Optional[int] = None,
        rate_per_sec: int = _DEFAULT_RATE_PER_SEC,
        operator: str = "openfang_worker") -> Dict[str, Any]:
    """Top-level OpenFang send entry. Returns swarm-envelope dict.

    Mirrors _send_paranoid.run() / _send_telegram.run() but routes the
    transport through OpenFang's marketing-sender agent.
    """
    if not isinstance(mode, SendMode):
        raise TypeError(f"mode must be SendMode, got {type(mode).__name__}")

    actor = f"openfang_worker:{operator}"
    start = time.time()

    # Gate 1+2: kill-switch + freeze (LIVE only)
    if mode is SendMode.LIVE:
        _check_kill_switch()
        _check_freeze()

    base = _openfang_base()

    # Gate 3: resolve campaign (also asserts openfang_capable + enabled)
    campaign = _resolve_campaign(campaign_id)
    channel = campaign["channel"]
    audience_id = campaign["audience_id"]

    # Gate 4: signed-allowlist snapshot
    recipients = _snapshot_recipients(campaign)
    if max_recipients is not None:
        recipients = recipients[:max(1, int(max_recipients))]

    # Gate 6: verify every (channel, recipient_id) HMAC
    _verify_signed_allowlist(channel, recipients)

    # Gate 7: confirm-token
    expected_token = compute_confirm_token(campaign_id, audience_id,
                                            channel, recipients)
    if mode is SendMode.LIVE:
        _verify_confirm_token(confirm_token, expected_token)

    # DRY_RUN early-exit (before any OpenFang call)
    if mode is SendMode.DRY_RUN:
        _audit(actor, "openfang_send.dry_run", payload={
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "channel": channel,
            "openfang_channel_name": campaign["openfang_channel_name"],
            "recipient_count": len(recipients),
            "recipient_ids_preview": [r["recipient_id"] for r in recipients[:5]],
            "elapsed_s": round(time.time() - start, 3),
        })
        return {
            "mode": "dry_run",
            "channel": channel,
            "openfang_channel_name": campaign["openfang_channel_name"],
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "recipient_count": len(recipients),
            "recipient_ids_preview": [r["recipient_id"] for r in recipients[:5]],
            "confirm_token": expected_token,
            "summary": f"openfang DRY_RUN ok -- {len(recipients)} recipient(s) signed+allowlisted",
        }

    # Gate 2 (deferred until SHADOW/LIVE): agent resolves + Running
    agent_id = _resolve_agent_id(base)

    # Gate 8: ping the agent's conversation endpoint via health probe.
    # OpenFang's /api/health is the lightweight check.
    h = _http_json("GET", f"{base}/api/health", timeout=_OPENFANG_HEALTH_TIMEOUT_S)
    if "_transport_error" in h or "_http_status" in h:
        raise ParanoidAbort(
            "of_shadow_preping",
            f"OpenFang /api/health unhealthy: {h}",
        )

    _audit(actor, f"openfang_send.{mode.value}.preflight_pass", payload={
        "campaign_id": campaign_id,
        "audience_id": audience_id,
        "channel": channel,
        "openfang_channel_name": campaign["openfang_channel_name"],
        "agent_id": agent_id,
        "recipient_count": len(recipients),
    })

    result = _send_loop(base, agent_id, campaign, recipients, mode, rate_per_sec)

    # Gate 12: status flip on success
    if result["sent"] > 0:
        _db.execute_via_docker(
            f"UPDATE marketing.campaigns SET status = 'sent', sent_at = now() "
            f"WHERE id = {_db._sql_literal(campaign_id)}::uuid "
            f"  AND status <> 'sent'"
        )

    _audit(actor, f"openfang_send.{mode.value}.complete", payload={
        "campaign_id": campaign_id,
        "channel": channel,
        "result": result,
        "elapsed_s": round(time.time() - start, 3),
    })

    return {
        "mode": mode.value,
        "channel": channel,
        "openfang_channel_name": campaign["openfang_channel_name"],
        "campaign_id": campaign_id,
        "audience_id": audience_id,
        "recipient_count": len(recipients),
        "agent_id": agent_id,
        "result": result,
        "summary": f"openfang {mode.value.upper()} done -- "
                   f"sent={result['sent']} bounced={result['bounced']}",
    }


__all__ = [
    "run",
    "compute_confirm_token",
    "_KILL_SWITCH_ENV",
    "_OPENFANG_AGENT_NAME",
]
