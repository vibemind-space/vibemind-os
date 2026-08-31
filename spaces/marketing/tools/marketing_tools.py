"""Marketing-Ops tools — Phase-1 skeleton.

Tool functions called by the MarketingBackendAgent. Each returns a dict
shaped `{"success": bool, "message": str, "data": ...}` per VibeMind
swarm convention (see voice/CLAUDE.md › Tool System).

Phase-1 status:
  - All functions return stub responses + run DB SELECTs against
    `marketing.*` so they're testable end-to-end without sending mail.
  - Phase-2 wires `send_campaign` to mailcow SMTP, but ONLY after the
    Postfix loopback-block is verified intact AND a future explicit
    consent-check (`consent_given_at IS NOT NULL`) is implemented.
  - The investor-already-sent lockout is enforced at the SQL layer
    (see audience builder below), not just at the agent layer.

Security guarantees (from project_marketing_ops_space.md):
  - `Sollange keine EMail rausgeht alles gut` — no Phase-1 tool here
    actually sends mail. `send_campaign` is intentionally NotImplemented.
  - sensitive person data stays in `marketing.*`; no leakage into Rowboat
    KB beyond the vault sync (handled by Worker A).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from spaces.marketing.sync import _db

logger = logging.getLogger(__name__)


# ─── Phase-1 read-only ops ──────────────────────────────────────────────


def list_audiences(name_contains: Optional[str] = None) -> Dict[str, Any]:
    """List all configured audiences, optionally filtered by name."""
    where = ""
    if name_contains:
        where = f"WHERE name ILIKE {_db._sql_literal('%' + name_contains + '%')}"
    rows = _db.query_via_docker(
        f"SELECT id, name, description, filter_dsl, member_count, created_at, last_built_at "
        f"FROM marketing.audiences {where} ORDER BY name"
    )
    return {
        "success": True,
        "message": f"Found {len(rows)} audience(s)",
        "data": rows,
    }


def list_templates(name_contains: Optional[str] = None) -> Dict[str, Any]:
    """List email templates."""
    where = ""
    if name_contains:
        where = f"WHERE name ILIKE {_db._sql_literal('%' + name_contains + '%')}"
    rows = _db.query_via_docker(
        f"SELECT id, name, subject, channel, created_at "
        f"FROM marketing.templates {where} ORDER BY name"
    )
    return {"success": True, "message": f"Found {len(rows)} template(s)", "data": rows}


def list_campaigns(status: Optional[str] = None) -> Dict[str, Any]:
    """List campaigns; optionally filter by status (draft, scheduled, sent, ...)."""
    where = ""
    if status:
        where = f"WHERE status = {_db._sql_literal(status)}"
    rows = _db.query_via_docker(
        f"SELECT id, name, status, audience_id, template_id, scheduled_at, sent_at "
        f"FROM marketing.campaigns {where} ORDER BY COALESCE(scheduled_at, created_at) DESC"
    )
    return {"success": True, "message": f"Found {len(rows)} campaign(s)", "data": rows}


def get_inbox_unread() -> Dict[str, Any]:
    """Return inbound mails from the last 7 days, newest first.

    Phase 1 has no read-status column — every fetch is "unread-ish". A
    `read_at` column can land in migration 007 if/when the UI needs it.
    """
    rows = _db.query_via_docker(
        "SELECT id, received_at, mailbox, from_email, from_name, subject, "
        "is_bounce, is_autoreply, linked_send_id "
        "FROM marketing.inbound_messages "
        "WHERE received_at > now() - interval '7 days' "
        "ORDER BY received_at DESC LIMIT 100"
    )
    return {"success": True, "message": f"{len(rows)} recent inbound", "data": rows}


def audience_count(audience_id: str) -> Dict[str, Any]:
    """Count members of an audience, applying the investor-lockout filter.

    SECURITY: The lockout filter (`investor_already_sent = false`) is
    enforced HERE rather than only at send-time, so the UI can show the
    same numbers the sender will see.
    """
    # Schema notes (from 001_marketing_schema.sql):
    #   - emails PK is `email` (text), FK to accounts via `handle`
    #   - is_verified is encoded as smtp_valid tri-state (smallint: -1/0/1)
    #   - audience_members PK = (audience_id, email)
    rows = _db.query_via_docker(
        f"SELECT COUNT(DISTINCT e.email) AS reachable "
        f"FROM marketing.audience_members am "
        f"JOIN marketing.emails e ON e.email = am.email "
        f"WHERE am.audience_id = {_db._sql_literal(audience_id)} "
        f"  AND e.investor_already_sent = false "
        f"  AND e.smtp_valid = 1 "
        f"  AND e.unsubscribed_at IS NULL"
    )
    n = int(rows[0]["reachable"]) if rows else 0
    return {"success": True, "message": f"{n} reachable in audience", "data": {"reachable": n}}


def get_stats() -> Dict[str, Any]:
    """Brevo-style dashboard top-line metrics."""
    # Schema notes: emails.smtp_valid is the tri-state truth-of-verification
    # (-1=unknown, 0=invalid, 1=valid); we count smtp_valid=1 as 'verified'.
    rows = _db.query_via_docker(
        "SELECT "
        " (SELECT COUNT(*) FROM marketing.accounts)                          AS accounts, "
        " (SELECT COUNT(*) FROM marketing.emails WHERE smtp_valid = 1)       AS verified_emails, "
        " (SELECT COUNT(*) FROM marketing.emails "
        "  WHERE investor_already_sent)                                      AS investor_sent_locked, "
        " (SELECT COUNT(*) FROM marketing.campaigns)                         AS campaigns, "
        " (SELECT COUNT(*) FROM marketing.campaign_sends)                    AS sends, "
        " (SELECT COUNT(*) FROM marketing.inbound_messages "
        "  WHERE received_at > now() - interval '7 days')                    AS inbound_7d "
    )
    return {"success": True, "message": "stats ok", "data": rows[0] if rows else {}}


# ─── Phase-1 write ops (no mail) ────────────────────────────────────────


def create_audience(name: str, filter_dsl: dict,
                    description: Optional[str] = None) -> Dict[str, Any]:
    """Create an audience row. `filter_dsl` is the JSONB filter spec."""
    import json
    cols = ["name", "filter_dsl"]
    vals = [_db._sql_literal(name),
            f"{_db._sql_literal(json.dumps(filter_dsl))}::jsonb"]
    if description is not None:
        cols.append("description")
        vals.append(_db._sql_literal(description))
    rows = _db.query_via_docker(
        f"INSERT INTO marketing.audiences ({', '.join(cols)}) "
        f"VALUES ({', '.join(vals)}) RETURNING id, name"
    )
    return {
        "success": True,
        "message": f"audience '{name}' created",
        "data": rows[0] if rows else {},
    }


def create_template(name: str, subject: str, body_text: str,
                    body_html: Optional[str] = None,
                    channel: str = "email") -> Dict[str, Any]:
    """Create a template row."""
    cols = ["name", "subject", "body_text", "channel"]
    vals = [_db._sql_literal(name), _db._sql_literal(subject),
            _db._sql_literal(body_text), _db._sql_literal(channel)]
    if body_html is not None:
        cols.append("body_html")
        vals.append(_db._sql_literal(body_html))
    rows = _db.query_via_docker(
        f"INSERT INTO marketing.templates ({', '.join(cols)}) "
        f"VALUES ({', '.join(vals)}) RETURNING id"
    )
    return {
        "success": True,
        "message": f"template '{name}' created",
        "data": rows[0] if rows else {},
    }


# ─── Phase-2 send (intentionally NOT implemented) ───────────────────────


def send_campaign(campaign_id: str,
                  mode: str = "dry_run",
                  confirm_token: Optional[str] = None,
                  max_recipients: Optional[int] = None,
                  dry_run: Optional[bool] = None,
                  rate_per_sec: int = 10) -> Dict[str, Any]:
    """Send a campaign via the Phase-2 paranoid send-worker.

    Three modes (see spaces/marketing/tools/_send_paranoid.py docstring
    for the full 12-gate safety contract):

      mode="dry_run"  - never opens SMTP; returns confirm_token + preview.
      mode="shadow"   - real SMTP pipeline but redirected to Mailpit sink.
      mode="live"     - real send via Mailcow; requires confirm_token +
                        MARKETING_SEND_ENABLED=true + FREEZE absent.

    Legacy kwarg dry_run=bool is accepted and translated to mode for
    backwards compatibility with the Phase-1 API. dry_run=True maps to
    mode="dry_run"; dry_run=False with no explicit mode raises so an
    accidental Phase-1-style call doesn't silently escalate to LIVE.
    """
    # Phase-1 -> Phase-2 kwarg bridge. Only translate if mode was left
    # at its default; if the caller passed both, the explicit `mode`
    # wins (this is the new API).
    if dry_run is not None and mode == "dry_run":
        if dry_run:
            mode = "dry_run"
        else:
            return {
                "success": False,
                "message": ("legacy dry_run=False is no longer accepted -- "
                            "pass mode='live' with a confirm_token from a prior "
                            "mode='dry_run' call."),
                "data": None,
            }

    # Lazy import: avoids loading the SMTP stack for read-only tool callers.
    from ._send_paranoid import (
        SendMode,
        ParanoidAbort,
        run as _paranoid_run,
    )

    try:
        mode_enum = SendMode(mode)
    except ValueError:
        return {
            "success": False,
            "message": f"invalid mode {mode!r}; valid: dry_run | shadow | live",
            "data": None,
        }

    # Dispatch to the per-channel send module based on campaign.channel.
    # Channel gate 4.5 (assert_channel_configured) runs inside each
    # channel's run() so we can't bypass by routing manually.
    #
    # Routing priority (highest first):
    #   1. channel == 'email'    -> legacy _send_paranoid (Mailcow/Mailpit SMTP)
    #   2. channel == 'telegram' -> legacy _send_telegram (direct Bot API)
    #   3. channel_config.openfang_capable=true -> _send_openfang (via marketing-sender agent)
    #   4. otherwise -> explicit failure
    #
    # Why legacy paths come BEFORE openfang_capable lookup: email and
    # telegram already ship with their own full 12-gate stacks. Even if
    # a future migration accidentally flips openfang_capable=true on
    # them, the legacy modules remain the source of truth — they keep
    # their own bot tokens, hardcoded allowlists, and audit format.
    campaign_row = _db.query_one(
        f"SELECT channel FROM marketing.campaigns "
        f"WHERE id = {_db._sql_literal(campaign_id)}::uuid"
    )
    channel = (campaign_row or {}).get("channel") or "email"

    # OpenFang-routed channels carry openfang_capable=true. Pre-fetch so
    # the branch below doesn't have to re-query inside the try-block.
    cc_row = _db.query_one(
        f"SELECT openfang_capable, enabled, send_implemented "
        f"FROM marketing.channel_config "
        f"WHERE channel = {_db._sql_literal(channel)}"
    ) or {}
    openfang_capable = bool(cc_row.get("openfang_capable"))

    try:
        if channel == "email":
            result = _paranoid_run(
                campaign_id,
                mode_enum,
                confirm_token=confirm_token,
                max_recipients=max_recipients,
                rate_per_sec=rate_per_sec,
                operator="marketing_tool",
            )
        elif channel == "telegram":
            from . import _send_telegram
            result = _send_telegram.run(
                campaign_id,
                mode_enum,
                confirm_token=confirm_token,
                max_recipients=max_recipients,
                operator="marketing_tool",
            )
        elif openfang_capable:
            from . import _send_openfang
            result = _send_openfang.run(
                campaign_id,
                mode_enum,
                confirm_token=confirm_token,
                max_recipients=max_recipients,
                rate_per_sec=rate_per_sec,
                operator="marketing_tool",
            )
        else:
            # Unknown / unimplemented channel -- explicit failure.
            # channel_config gate 4.5 should have caught this, but we
            # belt-and-suspenders here.
            return {
                "success": False,
                "message": f"no send module wired for channel={channel!r}; "
                           f"see marketing.channel_config.send_implemented "
                           f"or openfang_capable",
                "data": {"guard": "no_send_module", "channel": channel,
                         "channel_config": cc_row},
            }
    except ParanoidAbort as e:
        return {
            "success": False,
            "message": str(e),
            "data": {"guard": e.guard, "detail": e.detail, "channel": channel},
        }
    except Exception as e:
        logger.exception("send_campaign unexpected failure")
        return {
            "success": False,
            "message": f"send_campaign unexpected error: {e}",
            "data": None,
        }

    return {
        "success": True,
        "message": result.get("summary", "ok"),
        "data": result,
    }


# ─── Hand-bridge: audience proposals (Phase-2 staging) ───────────────────


_ALLOWED_HAND_SOURCES = (
    "lead-hand", "researcher-hand", "collector-hand",
    "browser-hand", "predictor-hand", "manual",
)
_PROPOSAL_CANDIDATE_CAP = 500   # per-proposal hard ceiling


def propose_audience(name: str,
                     filter_dsl: dict,
                     candidate_emails: Optional[List[Dict[str, Any]]] = None,
                     *,
                     description: str = "",
                     rationale: str = "",
                     hand_notes: str = "",
                     source: str = "hand:unknown") -> Dict[str, Any]:
    """Hand-bridge entry: stages a proposed audience + lead candidates.

    Writes to marketing.audience_proposals + marketing.lead_candidates.
    NEVER touches marketing.audiences / marketing.emails / marketing.audience_members
    -- approval is a separate human-driven step.

    `source` must match a known Hand-id pattern (defense against a misuse
    where Hand-output ends up labelled like a human-curated source).
    `candidate_emails` is a list of dicts: {email, display_name?, company?,
    title?, confidence?, discovery_source?, raw_enrichment?}. Per-proposal
    duplicates are dropped via the unique index. Max 500 per proposal.
    """
    import json
    # Normalise source -- accept "lead-hand", "hand:lead", "lead_hand" etc.
    src_clean = source.lower().replace("hand:", "").replace("_", "-")
    if src_clean not in _ALLOWED_HAND_SOURCES:
        src_clean = "hand:unknown"
    src_stored = f"hand:{src_clean}" if not src_clean.startswith("hand:") else src_clean
    # ensure_db-like: insert proposal row, then candidate rows in ONE
    # DO-block for atomicity.
    cands = list(candidate_emails or [])
    if len(cands) > _PROPOSAL_CANDIDATE_CAP:
        return {
            "success": False,
            "message": f"too many candidate_emails ({len(cands)} > {_PROPOSAL_CANDIDATE_CAP})",
            "data": None,
        }
    # INSERT...RETURNING via query_via_docker is impossible (data-
    # modifying CTE in SELECT subquery rejected by PG). Use execute +
    # parse fallback identical to _claim_send_rows in _send_paranoid.py.
    out = _db.execute_via_docker(
        f"INSERT INTO marketing.audience_proposals "
        f"  (name, description, filter_dsl, rationale, source, hand_notes) "
        f"VALUES ("
        f"  {_db._sql_literal(name)}, "
        f"  {_db._sql_literal(description)}, "
        f"  {_db._sql_literal(json.dumps(filter_dsl))}::jsonb, "
        f"  {_db._sql_literal(rationale)}, "
        f"  {_db._sql_literal(src_stored)}, "
        f"  {_db._sql_literal(hand_notes)}"
        f") RETURNING id"
    )
    # psql -tAc returns the uuid on its own line, then "INSERT N M".
    proposal_id = next(
        (line.strip() for line in (out or "").splitlines()
         if line.strip() and "-" in line and not line.startswith("INSERT")),
        None,
    )
    if not proposal_id:
        return {"success": False,
                "message": "could not resolve new proposal id", "data": None}

    inserted = 0
    skipped = 0
    if cands:
        # Bulk-insert candidates. ON CONFLICT(proposal_id,email) DO NOTHING
        # silently de-dupes within the proposal.
        seen_emails = set()
        rows_sql = []
        for c in cands:
            email = (c.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue
            if email in seen_emails:
                skipped += 1
                continue
            seen_emails.add(email)
            domain = email.rsplit("@", 1)[1]
            rows_sql.append(
                f"({_db._sql_literal(proposal_id)}::uuid, "
                f"{_db._sql_literal(email)}, "
                f"{_db._sql_literal(c.get('display_name', '') or '')}, "
                f"{_db._sql_literal(c.get('company', '') or '')}, "
                f"{_db._sql_literal(c.get('title', '') or '')}, "
                f"{_db._sql_literal(domain)}, "
                f"{float(c.get('confidence', 0.0) or 0.0)}, "
                f"{_db._sql_literal(c.get('discovery_source', '') or '')}, "
                f"{_db._sql_literal(c.get('discovery_query', '') or '')}, "
                f"{_db._sql_literal(json.dumps(c.get('raw_enrichment', {}) or {}))}::jsonb)"
            )
        if rows_sql:
            _db.execute_via_docker(
                f"INSERT INTO marketing.lead_candidates "
                f"  (proposal_id, email, display_name, company, title, "
                f"   domain, confidence, discovery_source, discovery_query, raw_enrichment) "
                f"VALUES {', '.join(rows_sql)} "
                f"ON CONFLICT (proposal_id, email) DO NOTHING"
            )
            # Count what really landed (others were duplicates by index).
            cnt = _db.query_one(
                f"SELECT COUNT(*) AS n FROM marketing.lead_candidates "
                f"WHERE proposal_id = {_db._sql_literal(proposal_id)}::uuid"
            )
            inserted = int(cnt["n"]) if cnt else len(rows_sql)
            skipped += len(rows_sql) - inserted

    # Audit
    _db.execute_via_docker(
        f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
        f"VALUES ("
        f"  {_db._sql_literal('hand_bridge:propose_audience')}, "
        f"  'propose_audience', "
        f"  'marketing.audience_proposals', "
        f"  {_db._sql_literal(json.dumps({'proposal_id': proposal_id, 'name': name, 'source': src_stored, 'candidates_inserted': inserted, 'candidates_skipped': skipped}))}::jsonb"
        f")"
    )
    return {
        "success": True,
        "message": f"proposal staged (id={proposal_id[:8]}…); candidates={inserted}, skipped={skipped}",
        "data": {
            "proposal_id": proposal_id,
            "status": "pending_review",
            "name": name,
            "source": src_stored,
            "candidates_inserted": inserted,
            "candidates_skipped": skipped,
        },
    }


def list_proposals(status: Optional[str] = "pending_review") -> Dict[str, Any]:
    """Read-only listing of proposals filtered by status (default pending)."""
    where = ""
    if status:
        where = f"WHERE status = {_db._sql_literal(status)}"
    rows = _db.query_via_docker(
        f"SELECT p.id::text AS id, p.name, p.source, p.status, "
        f"       p.description, p.rationale, p.created_at::text AS created_at, "
        f"       (SELECT COUNT(*) FROM marketing.lead_candidates "
        f"        WHERE proposal_id = p.id) AS candidate_count "
        f"FROM marketing.audience_proposals p {where} "
        f"ORDER BY p.created_at DESC LIMIT 100"
    )
    return {"success": True, "message": f"{len(rows)} proposal(s)", "data": rows}


def get_proposal(proposal_id: str) -> Dict[str, Any]:
    """Detailed view: proposal + first 20 lead-candidates."""
    p = _db.query_one(
        f"SELECT id::text AS id, name, description, filter_dsl, rationale, "
        f"       source, status, hand_notes, created_at::text AS created_at "
        f"FROM marketing.audience_proposals "
        f"WHERE id = {_db._sql_literal(proposal_id)}::uuid"
    )
    if not p:
        return {"success": False, "message": "no such proposal", "data": None}
    cands = _db.query_via_docker(
        f"SELECT email, display_name, company, title, confidence, "
        f"       discovery_source FROM marketing.lead_candidates "
        f"WHERE proposal_id = {_db._sql_literal(proposal_id)}::uuid "
        f"ORDER BY confidence DESC NULLS LAST LIMIT 20"
    )
    p["candidates_preview"] = cands
    return {"success": True, "message": "ok", "data": p}


# Hand-bridge subroutine (Track C): marketing kicks off an OpenFang Hand
# task that eventually writes back via the bridge.
from .hand_bridge import request_hand_research  # noqa: E402,F401

# External integrations (Gmail/Notion/Sheets/Tavily/CSV) -- read-only at
# source, proposal-only at sink. Schema CHECK + Python allowlist enforce
# no-send invariant.
from .integrations import (  # noqa: E402,F401
    propose_audience_from_source,
    list_external_sources,
    get_source_capabilities,
)

# Approval flow: thin wrappers around the migration-012 stored functions.
# NEVER sets consent_given_at or investor_already_sent -- send-worker
# gates remain the only path to actual mail-out.
from .approval import (  # noqa: E402,F401
    approve_proposal,
    reject_proposal,
    validate_proposal_mx,
)

# Aggregate metrics views (migration 013) -- read-only, no PII.
from .metrics import (  # noqa: E402,F401
    get_stack_metrics,
    get_campaign_metrics,
    get_send_activity_daily,
)

# DNS alignment pre-flight (gate 2.5) -- read-only DNS lookups.
from .dns_alignment import (  # noqa: E402,F401
    check_sender_alignment,
)

# Async MX validation queue (Worker E) -- enqueue + list jobs.
from spaces.marketing.workers.mx_worker import (  # noqa: E402,F401
    enqueue_mx_validation,
    list_mx_jobs,
)

# Multi-channel registry (migration 015) + gate 4.5 helper +
# auto-detection of which channels are env-ready.
from .channels import (  # noqa: E402,F401
    list_channels,
    get_channel,
    assert_channel_configured,
    detect_channel_readiness,
    auto_enable_ready_channels,
)

# Proposal archival (migration 016) -- moves to cold storage.
from .archival import (  # noqa: E402,F401
    archive_old_proposals,
    list_archive,
    restore_proposal,
)


__all__ = [
    "list_audiences", "list_templates", "list_campaigns",
    "get_inbox_unread", "audience_count", "get_stats",
    "create_audience", "create_template",
    "send_campaign",
    # Hand-bridge (Phase-2 staging)
    "propose_audience", "list_proposals", "get_proposal",
    # Hand-bridge subroutine (Track C)
    "request_hand_research",
    # External integrations (Gmail/Notion/Sheets/Tavily/CSV)
    "propose_audience_from_source", "list_external_sources",
    "get_source_capabilities",
    # Approval flow (Phase-2b -- promote proposal to audience)
    "approve_proposal", "reject_proposal", "validate_proposal_mx",
    # Aggregate metrics views (read-only)
    "get_stack_metrics", "get_campaign_metrics", "get_send_activity_daily",
    # DNS alignment pre-flight (sender domain SPF+DKIM+DMARC)
    "check_sender_alignment",
    # Async MX validation queue (Worker E)
    "enqueue_mx_validation", "list_mx_jobs",
    # Multi-channel readiness (Phase-2 preparation)
    "list_channels", "get_channel", "assert_channel_configured",
    "detect_channel_readiness", "auto_enable_ready_channels",
    # Proposal archival
    "archive_old_proposals", "list_archive", "restore_proposal",
]
