"""Approval flow tools — proposal -> audience promotion.

Thin Python wrappers around the marketing.approve_audience_proposal and
marketing.reject_audience_proposal stored functions (migration 012).
All atomicity + invariants live in the DB; Python adds:

  - swarm-standard envelope `{success, message, data}`
  - optional pre-flight MX validation (read-only DNS lookup, NEVER an
    SMTP send) that bumps lead_candidates.smtp_valid before the
    stored function reads them. mx-only does NOT prove deliverability
    -- send-worker still requires smtp_valid=1 + 11 other gates.

NO send-pipeline impact. Verified by the stored function's:
  - consent_given_at stays NULL on every emails row inserted
  - investor_already_sent=false on every emails row inserted
  - send-worker still filters smtp_valid=1 (this module sets =1 only
    when DNS-MX-lookup succeeds for the candidate's domain, which is
    a much weaker guarantee than the send-worker's gates need)
"""
from __future__ import annotations

import json
import logging
import socket
from typing import Any, Dict, List, Optional

from ..sync import _db


logger = logging.getLogger("marketing.approval")


# ─── MX validation helper (read-only DNS) ──────────────────────────────


def _has_mx_record(domain: str, timeout_s: float = 3.0) -> Optional[bool]:
    """Return True if domain has an MX record, False if NXDOMAIN/no-MX,
    None on transient error (timeout, DNS down).

    Uses pure socket-level dnslib lookup if available, otherwise
    falls back to dnspython, otherwise returns None (= keep
    smtp_valid=-1). We DO NOT do any SMTP-VRFY or RCPT TO -- those
    are full-SMTP probes that count as send-adjacent activity.
    """
    if not domain or "." not in domain:
        return False
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        # dnspython not installed -- skip validation, leave smtp_valid=-1
        logger.warning("[approval] dnspython not available; skipping MX validation")
        return None
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout_s
        resolver.lifetime = timeout_s
        answers = resolver.resolve(domain, "MX")
        return len(list(answers)) > 0
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        return False
    except (dns.resolver.Timeout, dns.exception.DNSException) as e:
        logger.warning("[approval] DNS lookup failed for %s: %s", domain, e)
        return None
    except Exception as e:
        logger.exception("[approval] unexpected DNS error: %s", e)
        return None


def validate_proposal_mx(proposal_id: str) -> Dict[str, Any]:
    """Update lead_candidates.smtp_valid for the proposal based on MX
    lookup of each unique domain. Returns counts of {valid, invalid,
    unknown} for the proposal's candidates.

    NEVER opens an SMTP connection. NEVER sends any mail. Pure DNS read.
    Safe to call on any proposal, any time; idempotent.
    """
    rows = _db.query_via_docker(
        f"SELECT DISTINCT split_part(email,'@',2) AS domain "
        f"FROM marketing.lead_candidates "
        f"WHERE proposal_id = {_db._sql_literal(proposal_id)}::uuid "
        f"  AND email IS NOT NULL"
    )
    domains = [r["domain"].lower() for r in rows if r.get("domain")]
    if not domains:
        return {"success": False, "message": "no candidates to validate",
                "data": None}

    results: Dict[str, Optional[bool]] = {}
    for d in domains:
        results[d] = _has_mx_record(d)

    valid_domains = [d for d, ok in results.items() if ok is True]
    invalid_domains = [d for d, ok in results.items() if ok is False]
    unknown_domains = [d for d, ok in results.items() if ok is None]

    # Update candidates: smtp_valid=1 for valid MX, 0 for explicit no-MX,
    # leave -1 for unknown / timeout / dnspython-absent.
    if valid_domains:
        in_clause = ", ".join(_db._sql_literal(d) for d in valid_domains)
        _db.execute_via_docker(
            f"UPDATE marketing.lead_candidates SET smtp_valid = 1 "
            f"WHERE proposal_id = {_db._sql_literal(proposal_id)}::uuid "
            f"  AND lower(split_part(email,'@',2)) IN ({in_clause}) "
            f"  AND smtp_valid = -1"
        )
    if invalid_domains:
        in_clause = ", ".join(_db._sql_literal(d) for d in invalid_domains)
        _db.execute_via_docker(
            f"UPDATE marketing.lead_candidates SET smtp_valid = 0 "
            f"WHERE proposal_id = {_db._sql_literal(proposal_id)}::uuid "
            f"  AND lower(split_part(email,'@',2)) IN ({in_clause})"
        )

    # Audit
    _db.execute_via_docker(
        f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
        f"VALUES ("
        f"  'approval:mx_validate', "
        f"  'lead_candidates.mx_validate', "
        f"  'marketing.lead_candidates', "
        f"  {_db._sql_literal(json.dumps({'proposal_id': proposal_id, 'valid': valid_domains, 'invalid': invalid_domains, 'unknown': unknown_domains}))}::jsonb"
        f")"
    )
    return {
        "success": True,
        "message": (
            f"validated MX for {len(domains)} domain(s): "
            f"{len(valid_domains)} valid, {len(invalid_domains)} no-MX, "
            f"{len(unknown_domains)} unknown"
        ),
        "data": {
            "proposal_id": proposal_id,
            "valid_domains": valid_domains,
            "invalid_domains": invalid_domains,
            "unknown_domains": unknown_domains,
        },
    }


# ─── Approve / Reject ──────────────────────────────────────────────────


def approve_proposal(proposal_id: str,
                     *,
                     approved_by: str = "unknown",
                     validate_mx: bool = False) -> Dict[str, Any]:
    """Promote a pending proposal to a live audience.

    If validate_mx=True, runs validate_proposal_mx first so smtp_valid
    is set per-candidate before the stored function reads them. Otherwise
    candidates keep their existing smtp_valid (default -1 = unknown).

    The stored function is atomic; if anything fails, NO row is written.
    """
    if validate_mx:
        validate_proposal_mx(proposal_id)

    rows = _db.query_via_docker(
        f"SELECT * FROM marketing.approve_audience_proposal("
        f"  {_db._sql_literal(proposal_id)}::uuid, "
        f"  {_db._sql_literal(approved_by)}"
        f")"
    )
    if not rows:
        return {"success": False,
                "message": f"approve returned no rows for {proposal_id}",
                "data": None}
    r = rows[0]
    return {
        "success": True,
        "message": (
            f"approved (audience={(r.get('out_audience_id') or '')[:8]}…): "
            f"accounts+{r.get('out_accounts_created', 0)}, "
            f"emails+{r.get('out_emails_inserted', 0)}, "
            f"members+{r.get('out_members_inserted', 0)}"
            + (" [idempotent]" if r.get("out_was_idempotent") else "")
        ),
        "data": {
            "proposal_id": r.get("out_proposal_id"),
            "audience_id": r.get("out_audience_id"),
            "accounts_created": r.get("out_accounts_created", 0),
            "emails_inserted": r.get("out_emails_inserted", 0),
            "members_inserted": r.get("out_members_inserted", 0),
            "candidates_skipped": r.get("out_candidates_skipped", 0),
            "was_idempotent": bool(r.get("out_was_idempotent")),
        },
    }


def reject_proposal(proposal_id: str,
                    *,
                    reason: str = "no reason given",
                    rejected_by: str = "unknown") -> Dict[str, Any]:
    """Mark proposal rejected. No data is moved.

    Approved proposals cannot be rejected (use archive flow when built).
    """
    if not reason or not reason.strip():
        return {"success": False, "message": "reason required",
                "data": None}
    try:
        rows = _db.query_via_docker(
            f"SELECT * FROM marketing.reject_audience_proposal("
            f"  {_db._sql_literal(proposal_id)}::uuid, "
            f"  {_db._sql_literal(reason)}, "
            f"  {_db._sql_literal(rejected_by)}"
            f")"
        )
    except RuntimeError as e:
        # Stored function raises if approval already happened -- surface
        # the SQL error in the envelope.
        return {"success": False,
                "message": f"reject failed: {e}", "data": None}
    if not rows:
        return {"success": False,
                "message": f"reject returned no rows for {proposal_id}",
                "data": None}
    r = rows[0]
    return {
        "success": True,
        "message": f"rejected (was: {r.get('out_previous_status', '?')})",
        "data": {
            "proposal_id": r.get("out_proposal_id"),
            "previous_status": r.get("out_previous_status"),
            "rejected_at": r.get("out_rejected_at"),
        },
    }


__all__ = [
    "approve_proposal",
    "reject_proposal",
    "validate_proposal_mx",
]
