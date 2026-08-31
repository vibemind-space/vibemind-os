"""End-to-end roundtrip test for the marketing sync system.

Asserts that:
  1. INSERT into marketing.accounts -> Worker A drains outbox -> .md file appears
  2. UPDATE marketing.accounts -> Worker A re-renders -> .md content changes
  3. DELETE marketing.accounts -> Worker A removes the .md file
  4. rm <file> -> Worker B propagates DELETE -> marketing.accounts row gone
  5. Worker B's propagated DELETE does NOT emit another outbox row (loop prevention)

This test uses an isolated VAULT_DIR (/tmp/sync-e2e) and a dedicated handle
so it doesn't collide with any real data. It cleans up its outbox entries
on exit.

Run:
    python -m spaces.marketing.sync.tests.test_e2e

Exit 0 on full PASS.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Setup before importing the sync module so VAULT_DIR is honoured
TEST_HANDLE = "e2e_test_sync_handle"
TEST_VAULT = Path("/tmp/sync-e2e-vault")
TEST_HASH = Path("/tmp/sync-e2e-hashes.json")
os.environ["MARKETING_VAULT_DIR"] = str(TEST_VAULT)
os.environ["MARKETING_HASH_STORE"] = str(TEST_HASH)

from spaces.marketing.sync import _db, worker_db_to_fs


def cleanup_vault():
    if TEST_VAULT.exists():
        shutil.rmtree(TEST_VAULT)
    if TEST_HASH.exists():
        TEST_HASH.unlink()


def cleanup_db(container: str) -> None:
    """Remove any DB rows or outbox entries for the test handle."""
    sql = (
        f"DELETE FROM marketing.accounts WHERE handle = '{TEST_HANDLE}'; "
        f"DELETE FROM marketing.sync_outbox WHERE affected_handle = '{TEST_HANDLE}';"
    )
    try:
        _db.execute_via_docker(sql, container=container)
    except Exception:
        pass


def db_account_exists(container: str) -> bool:
    rows = _db.query_via_docker(
        f"SELECT 1 AS x FROM marketing.accounts WHERE handle = '{TEST_HANDLE}'",
        container=container,
    )
    return bool(rows)


def outbox_pending_count(container: str) -> int:
    rows = _db.query_via_docker(
        f"SELECT COUNT(*) AS n FROM marketing.sync_outbox "
        f"WHERE affected_handle = '{TEST_HANDLE}' AND applied_at IS NULL",
        container=container,
    )
    return int(rows[0]["n"]) if rows else 0


def outbox_total_count(container: str) -> int:
    rows = _db.query_via_docker(
        f"SELECT COUNT(*) AS n FROM marketing.sync_outbox "
        f"WHERE affected_handle = '{TEST_HANDLE}'",
        container=container,
    )
    return int(rows[0]["n"]) if rows else 0


def drain(container: str) -> int:
    hash_store = worker_db_to_fs._load_hash_store()
    return worker_db_to_fs.drain_outbox(container, hash_store)


def check(label: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -- {detail}" if detail else ""))
    return cond


def main() -> int:
    container = _db.find_supabase_container()
    print(f"[e2e] container={container[:12]}  vault={TEST_VAULT}")

    cleanup_vault()
    cleanup_db(container)

    results = []
    file_path = TEST_VAULT / f"{TEST_HANDLE}.md"

    # ─── Scenario 1: DB INSERT -> file appears ───────────────────────────
    print("\n[1] DB INSERT -> .md file should appear")
    _db.execute_via_docker(
        f"INSERT INTO marketing.accounts (handle, display_name, niche, source) "
        f"VALUES ('{TEST_HANDLE}', 'E2E Test', 'TEST', 'e2e')",
        container=container,
    )
    results.append(check("1a: outbox has pending event", outbox_pending_count(container) >= 1))
    drained = drain(container)
    results.append(check(f"1b: drain processed event ({drained})", drained >= 1))
    results.append(check("1c: file exists at vault path", file_path.exists()))
    results.append(check("1d: file contains handle in frontmatter",
                         file_path.exists() and TEST_HANDLE in file_path.read_text(encoding="utf-8")))

    # ─── Scenario 2: DB UPDATE -> file content changes ───────────────────
    print("\n[2] DB UPDATE -> file content should change")
    original_text = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    _db.execute_via_docker(
        f"UPDATE marketing.accounts SET niche = 'UPDATED', followers = 777 "
        f"WHERE handle = '{TEST_HANDLE}'",
        container=container,
    )
    drained = drain(container)
    results.append(check(f"2a: drain processed update ({drained})", drained >= 1))
    updated_text = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    results.append(check("2b: new niche reflected in file", "niche: UPDATED" in updated_text))
    results.append(check("2c: new followers reflected in file", "followers: 777" in updated_text))
    results.append(check("2d: file content changed from original", original_text != updated_text))

    # ─── Scenario 3: DB DELETE -> file removed ───────────────────────────
    print("\n[3] DB DELETE -> file should disappear")
    _db.execute_via_docker(
        f"DELETE FROM marketing.accounts WHERE handle = '{TEST_HANDLE}'",
        container=container,
    )
    drained = drain(container)
    results.append(check(f"3a: drain processed delete ({drained})", drained >= 1))
    results.append(check("3b: file no longer exists", not file_path.exists()))
    results.append(check("3c: DB row gone", not db_account_exists(container)))

    # ─── Scenario 4: rm <file> -> Worker B propagates DELETE -> DB row gone
    print("\n[4] rm .md -> Worker B propagates -> DB DELETE")
    # First, recreate the row + file
    _db.execute_via_docker(
        f"INSERT INTO marketing.accounts (handle, display_name) "
        f"VALUES ('{TEST_HANDLE}', 'E2E Test 4')",
        container=container,
    )
    drain(container)
    results.append(check("4a: file recreated for delete test", file_path.exists()))

    # Now simulate Worker B's file-delete handling DIRECTLY (don't spin up watchdog)
    from spaces.marketing.sync import worker_fs_to_db
    hash_store_b = worker_fs_to_db._load_hash_store()
    # Snapshot outbox-total BEFORE the FS delete
    pre_outbox_total = outbox_total_count(container)
    file_path.unlink()  # actual rm
    worker_fs_to_db._handle_event(file_path, "deleted", container, hash_store_b)
    results.append(check("4b: DB row gone after Worker B handled delete",
                         not db_account_exists(container)))

    # ─── Scenario 5: Worker B's DELETE did NOT emit a NEW outbox event ───
    print("\n[5] Worker B's DELETE must NOT echo (loop prevention)")
    post_outbox_total = outbox_total_count(container)
    # The delete-via-Worker-B should have origin='fs', which the trigger skips.
    # So post_outbox_total should equal pre_outbox_total (no new rows added).
    results.append(check(
        f"5a: outbox row count unchanged (loop prevented)  pre={pre_outbox_total} post={post_outbox_total}",
        post_outbox_total == pre_outbox_total,
    ))

    # ─── Cleanup ─────────────────────────────────────────────────────────
    cleanup_db(container)
    cleanup_vault()

    # ─── Summary ─────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== {passed}/{total} checks passed ===")
    if passed == total:
        print("E2E sync system: VERIFIED")
        return 0
    print("E2E sync system: FAILED")
    return 1


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
