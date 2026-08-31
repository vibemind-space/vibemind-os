"""Proposal archival tools.

Thin Python wrappers around the migration-016 stored functions:
  marketing.archive_old_proposals(days_old, dry_run, archived_by)
  marketing.restore_proposal_from_archive(id, restored_by)

NO send impact. NEVER modifies emails / audiences / audience_members
/ campaign_sends. Only audience_proposals + lead_candidates move.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from ..sync import _db


logger = logging.getLogger("marketing.archival")


def archive_old_proposals(days_old: int = 90,
                         *,
                         dry_run: bool = False,
                         archived_by: str = "tool") -> Dict[str, Any]:
    """Archive approved/rejected proposals older than `days_old` days.

    dry_run=True returns the would-be counts without writing.
    """
    if days_old < 0:
        return {"success": False, "message": "days_old must be >= 0",
                "data": None}
    rows = _db.query_via_docker(
        f"SELECT * FROM marketing.archive_old_proposals("
        f"  {int(days_old)}, {'true' if dry_run else 'false'}, "
        f"  {_db._sql_literal(archived_by)})"
    )
    if not rows:
        return {"success": False, "message": "no rows returned by stored fn",
                "data": None}
    r = rows[0]
    archived = int(r.get("out_archived_count", 0))
    dropped = int(r.get("out_dropped_candidates", 0))
    return {
        "success": True,
        "message": (
            f"DRY RUN: would archive {archived} proposal(s) + drop "
            f"{dropped} candidate(s)"
            if dry_run else
            f"archived {archived} proposal(s); cascade-dropped {dropped} candidate(s)"
        ),
        "data": {
            "archived_count": archived,
            "dropped_candidates": dropped,
            "dry_run": bool(r.get("out_dry_run", dry_run)),
            "days_old": days_old,
        },
    }


def list_archive(limit: int = 50,
                 status: Optional[str] = None) -> Dict[str, Any]:
    """Read-only listing of archived proposals."""
    where = ""
    if status:
        where = f"WHERE status = {_db._sql_literal(status)}"
    rows = _db.query_via_docker(
        f"SELECT id::text AS id, name, source, status, "
        f"       approved_audience_id::text AS approved_audience_id, "
        f"       approved_at::text AS approved_at, "
        f"       archived_at::text AS archived_at, archived_by, "
        f"       candidate_count, candidate_domains "
        f"FROM marketing.audience_proposals_archive {where} "
        f"ORDER BY archived_at DESC LIMIT {min(max(1, int(limit)), 500)}"
    )
    return {"success": True, "message": f"{len(rows)} archived", "data": rows}


def restore_proposal(proposal_id: str,
                     *,
                     restored_by: str = "tool") -> Dict[str, Any]:
    """Move a proposal from archive back to the active table.

    NB: lead_candidates were cascade-dropped on archival; they are NOT
    restored. The proposal row comes back, but if it needs to be
    re-approved, you'll have to re-run the integration import to repopulate
    candidates.
    """
    try:
        rows = _db.query_via_docker(
            f"SELECT * FROM marketing.restore_proposal_from_archive("
            f"  {_db._sql_literal(proposal_id)}::uuid, "
            f"  {_db._sql_literal(restored_by)})"
        )
    except RuntimeError as e:
        return {"success": False,
                "message": f"restore failed: {e}", "data": None}
    if not rows:
        return {"success": False, "message": "no rows returned",
                "data": None}
    r = rows[0]
    return {
        "success": True,
        "message": (
            f"restored {r.get('out_proposal_id')} -- candidates NOT restored "
            f"(cascade-dropped during archival); re-import via "
            f"/api/integrations/{{kind}}/import if needed"
        ),
        "data": {
            "proposal_id": r.get("out_proposal_id"),
            "restored": bool(r.get("out_restored")),
        },
    }


__all__ = [
    "archive_old_proposals",
    "list_archive",
    "restore_proposal",
]
