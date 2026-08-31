"""Worker E — async MX validation drainer.

Polls marketing.mx_validation_jobs every N seconds, claims pending
jobs via SELECT FOR UPDATE SKIP LOCKED, runs the existing
validate_proposal_mx synchronous helper, stamps result. NEVER opens
SMTP -- DNS-only, same defense-in-depth as the sync path.

CLI:
    python -m spaces.marketing.workers.mx_worker --once   # drain pending, exit
    python -m spaces.marketing.workers.mx_worker           # daemon
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.sync import _db  # noqa: E402
from spaces.marketing.tools.approval import validate_proposal_mx  # noqa: E402


logger = logging.getLogger("marketing.mx_worker")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


POLL_SEC = int(os.environ.get("MARKETING_MX_POLL_SEC", "10"))
MAX_ATTEMPTS = int(os.environ.get("MARKETING_MX_MAX_ATTEMPTS", "3"))

_shutdown = False


def _on_signal(signum, _frame):
    global _shutdown
    _shutdown = True
    logger.info("[mx_worker] received signal %s -- will exit after current job", signum)


for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(sig, _on_signal)
    except (ValueError, OSError):
        pass


def _claim_one_job() -> dict | None:
    """Atomic claim: flip status pending->running, return the row.

    Uses CTE + UPDATE with SKIP LOCKED so two workers can't pick the
    same job. RETURNING gives us the claimed row.
    """
    out = _db.execute_via_docker(
        "WITH claimed AS ("
        "  SELECT id FROM marketing.mx_validation_jobs "
        "  WHERE status = 'pending' "
        "  ORDER BY created_at "
        "  FOR UPDATE SKIP LOCKED "
        "  LIMIT 1"
        ") "
        "UPDATE marketing.mx_validation_jobs j "
        "SET status='running', started_at=now(), attempt_count=attempt_count+1 "
        "FROM claimed "
        "WHERE j.id = claimed.id "
        "RETURNING j.id::text AS id, j.proposal_id::text AS proposal_id, "
        "          j.domain, j.attempt_count"
    )
    # psql -tAc returns one row per line, pipe-separated. The execute_via_docker
    # helper returns stdout directly; we parse manually.
    line = next(
        (l for l in (out or "").splitlines()
         if l.strip() and "|" in l and not l.startswith("UPDATE")),
        None,
    )
    if not line:
        return None
    parts = line.split("|")
    if len(parts) < 4:
        return None
    return {
        "id": parts[0].strip(),
        "proposal_id": parts[1].strip() or None,
        "domain": parts[2].strip() or None,
        "attempt_count": int(parts[3].strip() or 0),
    }


def _finish_job(job_id: str, *, status: str,
                result: dict | None = None,
                error: str | None = None) -> None:
    sets = [f"status = {_db._sql_literal(status)}", "finished_at = now()"]
    if result is not None:
        sets.append(f"result = {_db._sql_literal(json.dumps(result))}::jsonb")
    if error is not None:
        sets.append(f"error_message = {_db._sql_literal(error)}")
    _db.execute_via_docker(
        f"UPDATE marketing.mx_validation_jobs "
        f"SET {', '.join(sets)} "
        f"WHERE id = {_db._sql_literal(job_id)}::uuid"
    )


def process_one() -> bool:
    """Claim + run + finish one job. Returns True if a job was processed."""
    job = _claim_one_job()
    if not job:
        return False
    logger.info("[mx_worker] claimed job=%s proposal=%s domain=%s",
                job["id"][:8], (job["proposal_id"] or "?")[:8], job["domain"])
    try:
        if not job.get("proposal_id"):
            _finish_job(job["id"], status="error",
                        error="job has no proposal_id (domain-only not yet supported)")
            return True
        result = validate_proposal_mx(job["proposal_id"])
        if not result.get("success"):
            # We treat "no candidates" as success-with-zero rather than error
            _finish_job(job["id"], status="done",
                        result={"message": result.get("message"),
                                "data": result.get("data")})
            return True
        _finish_job(job["id"], status="done", result=result.get("data"))
        return True
    except Exception as e:
        logger.exception("[mx_worker] job %s failed: %s", job["id"], e)
        # Retry up to MAX_ATTEMPTS by re-flipping to pending; otherwise mark error
        if job["attempt_count"] < MAX_ATTEMPTS:
            _db.execute_via_docker(
                f"UPDATE marketing.mx_validation_jobs SET status='pending' "
                f"WHERE id = {_db._sql_literal(job['id'])}::uuid"
            )
        else:
            _finish_job(job["id"], status="error", error=str(e)[:500])
        return True


def enqueue_mx_validation(proposal_id: str,
                          *,
                          requested_by: str = "manual") -> dict:
    """Public tool entry: enqueue a job for a proposal_id.
    Returns swarm-envelope. Worker picks it up asynchronously.
    """
    out = _db.execute_via_docker(
        f"INSERT INTO marketing.mx_validation_jobs "
        f"  (proposal_id, requested_by) "
        f"VALUES ({_db._sql_literal(proposal_id)}::uuid, "
        f"        {_db._sql_literal(requested_by)}) "
        f"RETURNING id"
    )
    job_id = next(
        (l.strip() for l in (out or "").splitlines()
         if l.strip() and "-" in l and not l.startswith("INSERT")),
        None,
    )
    if not job_id:
        return {"success": False, "message": "could not enqueue job",
                "data": None}
    return {
        "success": True,
        "message": f"enqueued mx validation for proposal {proposal_id[:8]}",
        "data": {"job_id": job_id, "proposal_id": proposal_id, "status": "pending"},
    }


def list_mx_jobs(limit: int = 20, status: str | None = None) -> dict:
    where = ""
    if status:
        where = f"WHERE status = {_db._sql_literal(status)}"
    rows = _db.query_via_docker(
        f"SELECT id::text AS id, proposal_id::text AS proposal_id, "
        f"       domain, status, attempt_count, error_message, "
        f"       created_at::text AS created_at, "
        f"       finished_at::text AS finished_at "
        f"FROM marketing.mx_validation_jobs {where} "
        f"ORDER BY created_at DESC LIMIT {min(max(1, int(limit)), 200)}"
    )
    return {"success": True, "message": f"{len(rows)} job(s)", "data": rows}


# ─── CLI ───────────────────────────────────────────────────────────────


def _main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true",
                   help="Drain pending queue once and exit")
    args = p.parse_args()

    if args.once:
        n = 0
        while process_one():
            n += 1
        logger.info("[mx_worker] drained %d job(s)", n)
        return 0

    logger.info("[mx_worker] daemon mode, poll=%ds", POLL_SEC)
    while not _shutdown:
        try:
            while process_one():
                if _shutdown:
                    break
        except Exception as e:
            logger.exception("[mx_worker] poll loop error: %s", e)
        for _ in range(POLL_SEC):
            if _shutdown:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
