"""External integrations bridge — Gmail / Notion / Sheets / Tavily / CSV.

Every integration here is READ-ONLY at the source and PROPOSAL-ONLY at the
sink. No SMTP. No campaign_sends. No emails.* writes. No audiences.* writes.
The send-worker NEVER reads from these paths.

Contract:
  - kind MUST be in ALLOWED_INTEGRATION_KINDS (hardcoded set, not env)
  - the matching marketing.external_sources row MUST exist (migration 011
    seeded the Phase-1 five), MUST have enabled=true, and is asserted to
    have can_send=false (defense-in-depth -- the CHECK constraint already
    guarantees this at the DB level, but we re-verify before each import
    so a corrupted row would fail loud not silently route to send)
  - every import lands a row in marketing.audience_proposals via
    marketing_tools.propose_audience -- so the same staging-table-only
    contract used by the Hand-bridge applies here too

This is the "what does OpenFang Skills/Channels integration look like
when no email can leak" answer.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from ..sync import _db

# NB: marketing_tools is lazy-imported inside propose_audience_from_source
# to avoid a circular import (marketing_tools re-exports our entry-points
# in its __all__).


logger = logging.getLogger("marketing.integrations")


# Hardcoded allowlist. Adding a new kind requires:
#   1. seed row in migration 011 (or follow-up)
#   2. an entry below
#   3. (if it has its own importer) a handler in _IMPORTERS
ALLOWED_INTEGRATION_KINDS = frozenset({
    "gmail-search",
    "notion-page",
    "sheets-row",
    "tavily-search",
    "manual-csv",
})

# Hard ceilings per import (extra layer above propose_audience's own
# _PROPOSAL_CANDIDATE_CAP=500). Per-source defaults so noisy sources
# can be reined in without changing propose_audience.
_PER_KIND_CAP = {
    "gmail-search":  200,
    "notion-page":   500,
    "sheets-row":    500,
    "tavily-search": 100,
    "manual-csv":    500,
}

# RFC-5322-lite email regex. Stricter validation happens at the
# propose_audience layer; this filters obvious garbage from raw payloads.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class IntegrationError(Exception):
    """Refused at the integration layer (allowlist, disabled, schema invariant)."""


# ─── Pre-flight asserts ────────────────────────────────────────────────


def _assert_source_safe(kind: str) -> Dict[str, Any]:
    """Refuse to proceed unless EVERY layer agrees this source is read-only.

    Raises IntegrationError on:
      - kind not in ALLOWED_INTEGRATION_KINDS
      - no marketing.external_sources row for the kind
      - row has enabled=false
      - row somehow has can_send=true (would mean the CHECK was dropped --
        defense-in-depth, refuse loud)
    Returns the row on success.
    """
    if kind not in ALLOWED_INTEGRATION_KINDS:
        raise IntegrationError(
            f"unknown integration kind {kind!r}; "
            f"allowed: {sorted(ALLOWED_INTEGRATION_KINDS)}"
        )
    row = _db.query_one(
        f"SELECT kind, label, enabled, can_send, openfang_skill, required_env "
        f"FROM marketing.external_sources "
        f"WHERE kind = {_db._sql_literal(kind)}"
    )
    if not row:
        raise IntegrationError(
            f"no external_sources row for kind={kind!r}; run migration 011"
        )
    if row.get("can_send") is True:
        # CHECK should make this impossible, but if it ever returns true
        # the schema invariant was tampered with -- refuse loud.
        raise IntegrationError(
            f"INVARIANT BROKEN: external_sources.{kind!r}.can_send=true; "
            f"refusing to import. Restore the CHECK constraint."
        )
    if not row.get("enabled"):
        raise IntegrationError(
            f"integration {kind!r} is disabled (enabled=false); "
            f"flip enabled=true on the row before importing"
        )
    return row


# ─── Per-source extractors ─────────────────────────────────────────────
#
# Each extractor takes a kind-specific payload and returns a list of
# candidate dicts shaped for propose_audience. Extractors do NOT touch
# the network -- they parse what the caller passed in. The CALLER is
# responsible for fetching from Gmail/Notion/Sheets/Tavily and shipping
# the raw payload here.
#
# This split keeps the SQL-write codepath inside our process and the
# network-fetch codepath either:
#   (a) inside the OpenFang Hand prompt (which then POSTs to us), or
#   (b) inside an explicit operator-driven CLI command.
# Either way we never embed OAuth credentials in this module.


def _extract_gmail_search(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """payload: {messages: [{from, subject, body, date}, ...], query: str}.

    Pulls email addresses from From + Reply-To headers. Body is scanned
    too but only for emails matching the From-domain (low false-positive).
    """
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        raise IntegrationError("payload.messages must be a list")
    candidates: List[Dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        # Prefer Reply-To when set
        addr = (m.get("reply_to") or m.get("from") or "").strip().lower()
        email_match = _EMAIL_RE.search(addr)
        if not email_match:
            continue
        email = email_match.group(0)
        candidates.append({
            "email": email,
            "display_name": m.get("from_name", "") or "",
            "company": m.get("company", "") or "",
            "discovery_source": "gmail-search",
            "discovery_query": payload.get("query", "") or "",
            "confidence": 0.7,                            # known good sender
            "raw_enrichment": {
                "subject": (m.get("subject") or "")[:200],
                "date": m.get("date"),
            },
        })
    return candidates


def _extract_notion_page(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """payload: {page_id: str, blocks: [{rich_text: str}, ...]} or
                {page_id: str, contacts: [{email, name, ...}, ...]}.

    If contacts is provided, use it directly. Otherwise scan blocks for
    email-shaped strings.
    """
    candidates: List[Dict[str, Any]] = []
    contacts = payload.get("contacts")
    if isinstance(contacts, list):
        for c in contacts:
            if not isinstance(c, dict):
                continue
            email = (c.get("email") or "").strip().lower()
            if not email or not _EMAIL_RE.fullmatch(email):
                continue
            candidates.append({
                "email": email,
                "display_name": c.get("name", "") or "",
                "company": c.get("company", "") or "",
                "title": c.get("title", "") or "",
                "discovery_source": f"notion-page:{payload.get('page_id', '?')}",
                "confidence": 0.8,                        # structured Notion DB
                "raw_enrichment": {k: c.get(k) for k in c
                                   if k not in ("email", "name", "company", "title")},
            })
        return candidates
    # Fallback: scan free-text blocks
    blocks = payload.get("blocks") or []
    if not isinstance(blocks, list):
        raise IntegrationError("notion payload needs contacts[] or blocks[]")
    seen = set()
    for b in blocks:
        text = ""
        if isinstance(b, dict):
            text = b.get("rich_text") or b.get("text") or ""
        elif isinstance(b, str):
            text = b
        for match in _EMAIL_RE.finditer(text or ""):
            email = match.group(0).lower()
            if email in seen:
                continue
            seen.add(email)
            candidates.append({
                "email": email,
                "discovery_source": f"notion-page:{payload.get('page_id', '?')}",
                "confidence": 0.5,                        # unstructured -- lower
                "raw_enrichment": {"context_block": text[:200]},
            })
    return candidates


def _extract_sheets_row(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """payload: {sheet_id, range, rows: [{email, name?, ...}]}.

    rows is required and each row MUST have an `email` field. We don't
    guess columns -- the caller (operator or Hand) normalises shape.
    """
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        raise IntegrationError("sheets payload needs rows[]")
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        email = (r.get("email") or "").strip().lower()
        if not email or not _EMAIL_RE.fullmatch(email):
            continue
        out.append({
            "email": email,
            "display_name": r.get("name", "") or "",
            "company": r.get("company", "") or "",
            "title": r.get("title", "") or "",
            "discovery_source": f"sheets:{payload.get('sheet_id', '?')}",
            "discovery_query": payload.get("range", "") or "",
            "confidence": 0.9,                            # operator-curated
            "raw_enrichment": {k: r.get(k) for k in r
                               if k not in ("email", "name", "company", "title")},
        })
    return out


def _extract_tavily_search(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """payload: {query, results: [{url, title, content}, ...]}.

    Scrapes emails out of result-content. Low-trust source -- confidence
    capped at 0.4 even if the email looks valid.
    """
    results = payload.get("results") or []
    if not isinstance(results, list):
        raise IntegrationError("tavily payload needs results[]")
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in results:
        if not isinstance(r, dict):
            continue
        text = " ".join(str(r.get(k) or "") for k in ("title", "content", "snippet"))
        for match in _EMAIL_RE.finditer(text):
            email = match.group(0).lower()
            if email in seen:
                continue
            seen.add(email)
            out.append({
                "email": email,
                "discovery_source": "tavily-search",
                "discovery_query": payload.get("query", "") or "",
                "confidence": 0.4,                        # web-scrape -- low
                "raw_enrichment": {
                    "url": r.get("url"),
                    "title": (r.get("title") or "")[:200],
                },
            })
    return out


def _extract_manual_csv(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """payload: {csv_text: str, source_label: str?}.

    Pure-stdlib CSV parsing. Header row required, at minimum an `email`
    column. Other columns become raw_enrichment.
    """
    text = payload.get("csv_text") or ""
    if not isinstance(text, str) or not text.strip():
        raise IntegrationError("manual-csv payload needs csv_text (non-empty)")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "email" not in [
        (f or "").strip().lower() for f in reader.fieldnames
    ]:
        raise IntegrationError("csv_text must have an 'email' column")
    # Normalise field-name casing
    email_field = next(f for f in reader.fieldnames
                       if (f or "").strip().lower() == "email")
    source_label = payload.get("source_label", "manual-csv") or "manual-csv"
    out: List[Dict[str, Any]] = []
    for row in reader:
        email = (row.get(email_field) or "").strip().lower()
        if not email or not _EMAIL_RE.fullmatch(email):
            continue
        out.append({
            "email": email,
            "display_name": (row.get("name") or row.get("display_name") or "").strip(),
            "company": (row.get("company") or "").strip(),
            "title": (row.get("title") or "").strip(),
            "discovery_source": source_label,
            "confidence": 0.95,                           # operator vouched
            "raw_enrichment": {k: v for k, v in row.items()
                               if k not in (email_field, "name", "company",
                                            "title", "display_name")},
        })
    return out


_IMPORTERS = {
    "gmail-search":  _extract_gmail_search,
    "notion-page":   _extract_notion_page,
    "sheets-row":    _extract_sheets_row,
    "tavily-search": _extract_tavily_search,
    "manual-csv":    _extract_manual_csv,
}


# ─── Public entry ──────────────────────────────────────────────────────


def propose_audience_from_source(kind: str,
                                 payload: Dict[str, Any],
                                 *,
                                 audience_name: Optional[str] = None,
                                 filter_dsl: Optional[Dict[str, Any]] = None,
                                 rationale: str = "",
                                 hand_notes: str = "") -> Dict[str, Any]:
    """Generic import that funnels every external source into propose_audience.

    Flow:
      1. Pre-flight: kind in allowlist, external_sources row exists,
         enabled=true, can_send=false (defensive recheck).
      2. Per-source extractor turns payload into candidate dicts.
      3. Hand off to marketing_tools.propose_audience -- which writes to
         audience_proposals + lead_candidates. NEVER touches send pipeline.
      4. Update external_sources.last_synced_at + counters.
      5. Audit row.

    Returns the propose_audience envelope plus a `source` field.
    """
    src_row = _assert_source_safe(kind)        # raises IntegrationError on any violation

    cap = _PER_KIND_CAP.get(kind, 200)
    extractor = _IMPORTERS.get(kind)
    if extractor is None:
        raise IntegrationError(f"no extractor wired for {kind!r}")

    try:
        candidates = extractor(payload or {})
    except IntegrationError:
        raise
    except Exception as e:
        # Shape-validation failures -- treat as IntegrationError so callers
        # can distinguish from underlying DB issues.
        raise IntegrationError(f"{kind} extractor failed: {type(e).__name__}: {e}")

    if not candidates:
        return {
            "success": False,
            "message": f"{kind}: 0 candidates extracted from payload",
            "data": {"kind": kind, "candidates_extracted": 0},
        }

    # Per-kind cap before delegation (propose_audience has its own 500 cap).
    truncated = False
    if len(candidates) > cap:
        candidates = candidates[:cap]
        truncated = True

    name = (audience_name or "").strip() or f"{src_row['label']} ({kind})"
    # propose_audience expects a Hand-style source string. We pass the
    # integration kind via hand_notes for traceability AND use 'manual'
    # for source -- integrations are operator-curated, not Hand-generated.
    notes = hand_notes
    notes_prefix = f"[source={kind}] "
    if notes_prefix not in notes:
        notes = notes_prefix + notes

    # Lazy import to break circular dep with marketing_tools.
    from . import marketing_tools as mt
    result = mt.propose_audience(
        name=name,
        filter_dsl=filter_dsl or {"integration_source": kind},
        candidate_emails=candidates,
        description=src_row.get("label", ""),
        rationale=rationale or f"Imported from {kind}",
        hand_notes=notes,
        source="manual",       # integrations are operator-curated, NOT hand
    )
    if not result.get("success"):
        return result

    # Bookkeeping on the source row
    inserted = int(result["data"].get("candidates_inserted", 0))
    try:
        _db.execute_via_docker(
            f"UPDATE marketing.external_sources "
            f"SET last_synced_at = now(), "
            f"    proposals_generated = proposals_generated + 1, "
            f"    candidates_collected = candidates_collected + {int(inserted)} "
            f"WHERE kind = {_db._sql_literal(kind)}"
        )
    except Exception as e:
        logger.warning("[integrations] %s counter update failed: %s", kind, e)

    # Audit
    try:
        _db.execute_via_docker(
            f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
            f"VALUES ("
            f"  {_db._sql_literal('integrations:' + kind)}, "
            f"  'import.proposal', "
            f"  'marketing.audience_proposals', "
            f"  {_db._sql_literal(json.dumps({'kind': kind, 'proposal_id': result['data'].get('proposal_id'), 'candidates_inserted': inserted, 'truncated': truncated, 'audience_name': name}))}::jsonb"
            f")"
        )
    except Exception as e:
        logger.warning("[integrations] audit insert failed: %s", e)

    result.setdefault("data", {})
    result["data"]["source"] = kind
    result["data"]["truncated"] = truncated
    return result


def list_external_sources(enabled_only: bool = True) -> Dict[str, Any]:
    """Read-only listing of registered integrations."""
    where = "WHERE enabled = true" if enabled_only else ""
    rows = _db.query_via_docker(
        f"SELECT kind, label, description, category, can_read, "
        f"       can_write_proposal, can_send, enabled, openfang_skill, "
        f"       required_env, last_synced_at::text AS last_synced_at, "
        f"       proposals_generated, candidates_collected "
        f"FROM marketing.external_sources {where} ORDER BY kind"
    )
    return {"success": True, "message": f"{len(rows)} integration(s)", "data": rows}


def get_source_capabilities(kind: str) -> Dict[str, Any]:
    """Detailed view of one integration's capabilities (for UI)."""
    if kind not in ALLOWED_INTEGRATION_KINDS:
        return {"success": False,
                "message": f"unknown kind {kind!r}", "data": None}
    row = _db.query_one(
        f"SELECT kind, label, description, category, can_read, "
        f"       can_write_proposal, can_send, enabled, openfang_skill, "
        f"       required_env, last_synced_at::text AS last_synced_at, "
        f"       proposals_generated, candidates_collected "
        f"FROM marketing.external_sources "
        f"WHERE kind = {_db._sql_literal(kind)}"
    )
    if not row:
        return {"success": False,
                "message": f"no row for kind={kind!r}", "data": None}
    return {"success": True, "message": "ok", "data": row}


__all__ = [
    "ALLOWED_INTEGRATION_KINDS",
    "IntegrationError",
    "propose_audience_from_source",
    "list_external_sources",
    "get_source_capabilities",
]
