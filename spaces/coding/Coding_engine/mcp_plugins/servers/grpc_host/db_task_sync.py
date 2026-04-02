"""
Live DB Task Sync for EpicOrchestrator.

Provides a lightweight sync layer that writes task status changes
directly to PostgreSQL as they happen during generation.
Runs in the subprocess (run_generation.py), not the API process.

Usage in epic_orchestrator.py:
    from db_task_sync import DBTaskSync
    db_sync = DBTaskSync(db_url)
    db_sync.update_task("EPIC-001-SETUP", "completed")
    db_sync.update_task("EPIC-001-VERIFY-lint", "failed", "ESLint errors found")
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("db_task_sync")

# Try psycopg2 (sync) — works in subprocess without asyncio
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# Fallback: use urllib to call API
import json
import urllib.request


class DBTaskSync:
    """Syncs task status changes to PostgreSQL in real-time."""

    def __init__(self, db_url: str = "", api_url: str = "http://127.0.0.1:8000"):
        self.db_url = db_url or os.environ.get(
            "CODING_ENGINE_DB_URL",
            "postgresql://postgres:postgres@postgres:5432/coding_engine"
        )
        self.api_url = api_url
        self._conn = None
        self._use_db = HAS_PSYCOPG2
        self._connect()

    def _connect(self):
        """Connect to PostgreSQL directly."""
        if not self._use_db:
            logger.info("psycopg2 not available, using API fallback for DB sync")
            return

        try:
            self._conn = psycopg2.connect(self.db_url)
            self._conn.autocommit = True
            logger.info("DB sync connected directly to PostgreSQL")
        except Exception as e:
            logger.warning("DB direct connect failed, using API fallback: %s", e)
            self._use_db = False
            self._conn = None

    def update_task(self, task_id: str, status: str, error_message: str = "", execution_time_ms: int = 0):
        """Update a single task's status in the DB — called after each task executes."""
        if self._use_db and self._conn:
            self._update_via_db(task_id, status, error_message, execution_time_ms)
        else:
            self._update_via_api(task_id, status, error_message)

    def _update_via_db(self, task_id: str, status: str, error_message: str, execution_time_ms: int):
        """Direct PostgreSQL update — fastest."""
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """UPDATE tasks SET status = %s, status_message = %s,
                       execution_time_ms = COALESCE(%s, execution_time_ms),
                       updated_at = NOW()
                       WHERE task_id = %s""",
                    (status.upper(), error_message[:2000] if error_message else None,
                     execution_time_ms if execution_time_ms else None, task_id)
                )
                if cur.rowcount == 0:
                    logger.debug("Task %s not found in DB (may not exist yet)", task_id)
        except Exception as e:
            logger.warning("DB update failed for %s: %s", task_id, e)
            # Try to reconnect
            try:
                self._connect()
            except Exception:
                pass

    def _update_via_api(self, task_id: str, status: str, error_message: str):
        """Fallback: update via API endpoint."""
        try:
            req = urllib.request.Request(
                "%s/api/v1/dashboard/update-task-status" % self.api_url,
                data=json.dumps({
                    "task_id": task_id,
                    "status": status.upper(),
                    "status_message": error_message[:500] if error_message else "",
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.debug("API update failed for %s: %s", task_id, e)

    def bulk_update(self, updates: list):
        """Bulk update multiple tasks. updates = [{"task_id": ..., "status": ..., "error": ...}]"""
        if self._use_db and self._conn:
            try:
                with self._conn.cursor() as cur:
                    for u in updates:
                        cur.execute(
                            "UPDATE tasks SET status = %s, status_message = %s, updated_at = NOW() WHERE task_id = %s",
                            (u.get("status", "PENDING").upper(),
                             u.get("error", "")[:2000],
                             u.get("task_id", ""))
                        )
                logger.info("Bulk updated %d tasks in DB", len(updates))
            except Exception as e:
                logger.warning("Bulk DB update failed: %s", e)
        else:
            # API fallback
            try:
                task_ids = [u["task_id"] for u in updates if u.get("status", "").upper() == "COMPLETED"]
                if task_ids:
                    req = urllib.request.Request(
                        "%s/api/v1/dashboard/bulk-update-task-status" % self.api_url,
                        data=json.dumps({
                            "task_ids": task_ids,
                            "status": "COMPLETED",
                        }).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=10)
            except Exception as e:
                logger.warning("API bulk update failed: %s", e)

    def close(self):
        """Close DB connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
