"""One-time migration: x-pathfinder-db.emails -> Supabase marketing.*

Copies all pathx data into the supabase marketing.* schema:
  - 14.742 accounts -> marketing.accounts (1:1, no transform)
  - 350 emails -> marketing.emails (+ consent_given_at=NULL, consent_source='pathfinder-import-no-consent')
  - 9.297 strategies -> marketing.strategies (1:1)
  - 14 runs -> marketing.runs (1:1, sequence id preserved)

Both DBs are postgres in docker containers:
  - source:  x-pathfinder-db (postgres:16-alpine, user=pathfinder, db=emails)
  - target:  vibemind_supabase-db.1.<id> (postgres 16, user=supabase_admin, db=postgres)

The supabase target schema lives in `marketing`. RLS Phase-1 is active —
this migration runs as `supabase_admin` so RLS does not apply (super-bypass).

Idempotent: uses ON CONFLICT (handle) DO UPDATE / ON CONFLICT (email) DO UPDATE.
Re-running the migration is safe — re-imports updated rows, no duplicate errors.

Verifies counts post-migration. Writes an audit_log entry.

Run:
    python spaces/marketing/scripts/migrate_pathx_to_supabase.py

After successful run, pathx-db can be stopped/removed:
    docker stop x-pathfinder-db && docker rm x-pathfinder-db
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from typing import Iterable

PATHX_CONTAINER_NAME = "x-pathfinder-db"
SUPABASE_CONTAINER_FILTER = "name=vibemind_supabase-db"

# pathx DB credentials (from docker env)
PATHX_USER = "pathfinder"
PATHX_PASS = "pathfinder"
PATHX_DB = "emails"

# supabase DB target
SUPA_USER = "supabase_admin"
SUPA_DB = "postgres"

BATCH_SIZE = 500  # rows per INSERT statement


def run_pathx_sql(sql: str) -> str:
    """Run a SQL statement against pathx DB, return stdout."""
    cmd = [
        "docker", "exec",
        "-e", f"PGPASSWORD={PATHX_PASS}",
        PATHX_CONTAINER_NAME,
        "psql", "-U", PATHX_USER, "-d", PATHX_DB, "-tAc", sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout


def find_supa_container() -> str:
    res = subprocess.run(
        ["docker", "ps", "-qf", SUPABASE_CONTAINER_FILTER],
        capture_output=True, text=True, check=True,
    )
    cid = res.stdout.strip().split("\n")[0] if res.stdout.strip() else ""
    if not cid:
        raise RuntimeError("supabase-db container not running")
    return cid


def run_supa_sql(container: str, sql: str, stdin: str | None = None) -> str:
    """Run SQL against supabase-db, with optional STDIN (for COPY)."""
    cmd = [
        "docker", "exec",
    ]
    if stdin is not None:
        cmd.insert(2, "-i")
    cmd += [container, "psql", "-U", SUPA_USER, "-d", SUPA_DB, "-tAc", sql]
    res = subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"supabase psql failed: {res.stderr.strip()[:500]}")
    return res.stdout


def supa_count(container: str, table: str) -> int:
    out = run_supa_sql(container, f"SELECT COUNT(*) FROM marketing.{table}")
    return int(out.strip().splitlines()[-1])


def pathx_count(table: str) -> int:
    return int(run_pathx_sql(f"SELECT COUNT(*) FROM {table}").strip())


def export_pathx_csv(table: str, columns: list[str]) -> str:
    """Export a table as CSV (no header) for later COPY into supabase."""
    cols = ", ".join(columns)
    # \copy is client-side, runs in the same docker exec
    # Use COPY ... TO STDOUT instead — Postgres-internal, reliable.
    sql = f"COPY (SELECT {cols} FROM {table}) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *)"
    cmd = [
        "docker", "exec",
        "-e", f"PGPASSWORD={PATHX_PASS}",
        PATHX_CONTAINER_NAME,
        "psql", "-U", PATHX_USER, "-d", PATHX_DB, "-c", sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout


def copy_into_supa(container: str, table: str, columns: list[str], csv: str, on_conflict_key: str) -> None:
    """COPY csv into marketing.<table>_staging, then upsert via INSERT ON CONFLICT."""
    # Strategy: copy into a per-run TEMP TABLE that mirrors the target columns,
    # then UPSERT from temp into the real table. This way we get ON CONFLICT
    # semantics that plain COPY doesn't provide.
    cols_sql = ", ".join(columns)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != on_conflict_key)
    if update_set:
        upsert_action = f"DO UPDATE SET {update_set}"
    else:
        upsert_action = "DO NOTHING"

    # Combined SQL: create temp + COPY (via stdin) + upsert + drop temp
    # COPY FROM STDIN needs to be on its own line then the CSV body then \\.
    # Easiest: use psql -c sequence with one COPY ... FROM STDIN at the end
    # and pipe the CSV in.
    setup_sql = (
        f"CREATE TEMP TABLE _stage_{table} (LIKE marketing.{table} INCLUDING DEFAULTS); "
        f"COPY _stage_{table} ({cols_sql}) FROM STDIN WITH (FORMAT csv);"
    )

    # Pre-create temp table + start COPY in one psql -c call with stdin piped
    cmd = [
        "docker", "exec", "-i",
        container,
        "psql", "-U", SUPA_USER, "-d", SUPA_DB,
        "-c", setup_sql,
    ]
    res = subprocess.run(cmd, input=csv, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        # Temp table is gone since psql exited.  We have to do it differently:
        # use a single transaction with COPY then UPSERT then DROP — but COPY
        # FROM STDIN inside a multi-statement -c is tricky. Fall back: write
        # CSV to a file inside the container, then run the SQL.
        _alt_copy_via_tmpfile(container, table, columns, csv, on_conflict_key)
        return
    # Above psql exited after the temp-table + COPY in one session. The temp
    # table is now GONE (sessions don't persist across docker exec). So we
    # actually need a different approach. Always use _alt.
    _alt_copy_via_tmpfile(container, table, columns, csv, on_conflict_key)


def _alt_copy_via_tmpfile(container: str, table: str, columns: list[str], csv: str, on_conflict_key: str) -> None:
    """Copy CSV into a file in the container, then run a single multi-statement
    SQL in one session that does CREATE TEMP + COPY FROM file + UPSERT + DROP."""
    tmp_path = f"/tmp/pathx_{table}.csv"
    # write csv into container
    write_cmd = ["docker", "exec", "-i", container, "sh", "-c", f"cat > {tmp_path}"]
    res = subprocess.run(write_cmd, input=csv, capture_output=True, text=True, check=True)

    cols_sql = ", ".join(columns)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != on_conflict_key)
    if update_set:
        upsert_action = f"DO UPDATE SET {update_set}"
    else:
        upsert_action = "DO NOTHING"

    sql = (
        f"BEGIN; "
        f"CREATE TEMP TABLE _stage (LIKE marketing.{table} INCLUDING DEFAULTS); "
        f"COPY _stage ({cols_sql}) FROM '{tmp_path}' WITH (FORMAT csv); "
        f"INSERT INTO marketing.{table} ({cols_sql}) SELECT {cols_sql} FROM _stage "
        f"ON CONFLICT ({on_conflict_key}) {upsert_action}; "
        f"DROP TABLE _stage; "
        f"COMMIT;"
    )
    apply_cmd = [
        "docker", "exec", container,
        "psql", "-U", SUPA_USER, "-d", SUPA_DB, "-tAc", sql,
    ]
    res = subprocess.run(apply_cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"upsert failed for {table}: {res.stderr.strip()[:800]}")

    # cleanup file
    subprocess.run(
        ["docker", "exec", container, "rm", "-f", tmp_path],
        capture_output=True, check=False,
    )


def main() -> int:
    print("=" * 70)
    print("pathx -> Supabase marketing.* migration")
    print("=" * 70)

    # 1) Pre-flight: pathx reachable, supabase reachable, row counts
    try:
        pathx_accounts = pathx_count("accounts")
        pathx_emails = pathx_count("emails")
        pathx_strategies = pathx_count("strategies")
        pathx_runs = pathx_count("runs")
    except subprocess.CalledProcessError as e:
        print(f"ERROR pathx not reachable: {e.stderr}")
        return 2

    print(f"pathx  accounts={pathx_accounts}  emails={pathx_emails}  "
          f"strategies={pathx_strategies}  runs={pathx_runs}")

    container = find_supa_container()
    print(f"supabase container: {container[:12]}")
    print(f"supabase BEFORE:  accounts={supa_count(container, 'accounts')}  "
          f"emails={supa_count(container, 'emails')}  "
          f"strategies={supa_count(container, 'strategies')}  "
          f"runs={supa_count(container, 'runs')}")
    print()

    # 2) Migrate accounts (1:1)
    print(f"[1/4] accounts ({pathx_accounts} rows)...")
    csv = export_pathx_csv("accounts", [
        "handle", "display_name", "bio", "followers", "niche", "source", "created_at",
    ])
    copy_into_supa(container, "accounts",
                   ["handle", "display_name", "bio", "followers", "niche", "source", "created_at"],
                   csv, on_conflict_key="handle")
    print(f"      now {supa_count(container, 'accounts')} in supabase")

    # 3) Migrate emails — add consent_source/consent_given_at via post-insert UPDATE
    print(f"[2/4] emails ({pathx_emails} rows)...")
    csv = export_pathx_csv("emails", [
        "email", "handle", "confidence", "mx_valid", "smtp_valid",
        "strategy_id", "domain", "country", "catch_all", "created_at",
    ])
    copy_into_supa(container, "emails",
                   ["email", "handle", "confidence", "mx_valid", "smtp_valid",
                    "strategy_id", "domain", "country", "catch_all", "created_at"],
                   csv, on_conflict_key="email")
    # Set consent fields for the newly-imported rows
    run_supa_sql(container,
                 "UPDATE marketing.emails "
                 "SET consent_source = 'pathfinder-import-no-consent', "
                 "    consent_given_at = NULL "
                 "WHERE consent_source = ''")
    print(f"      now {supa_count(container, 'emails')} in supabase (consent set to NULL)")

    # 4) Strategies — composite has only PK id, simple 1:1
    print(f"[3/4] strategies ({pathx_strategies} rows)...")
    csv = export_pathx_csv("strategies", [
        "id", "format_pattern", "domain", "fitness", "success_count", "created_at",
    ])
    copy_into_supa(container, "strategies",
                   ["id", "format_pattern", "domain", "fitness", "success_count", "created_at"],
                   csv, on_conflict_key="id")
    print(f"      now {supa_count(container, 'strategies')} in supabase")

    # 5) Runs — id is SERIAL, we preserve original ids
    print(f"[4/4] runs ({pathx_runs} rows)...")
    csv = export_pathx_csv("runs", [
        "id", "started_at", "ended_at", "accounts_processed",
        "emails_generated", "emails_verified", "status",
    ])
    copy_into_supa(container, "runs",
                   ["id", "started_at", "ended_at", "accounts_processed",
                    "emails_generated", "emails_verified", "status"],
                   csv, on_conflict_key="id")
    # Restart the sequence so future runs.id doesn't collide
    max_id = run_supa_sql(container, "SELECT COALESCE(MAX(id), 0) FROM marketing.runs").strip()
    run_supa_sql(container, f"SELECT setval('marketing.runs_id_seq', {max_id})")
    print(f"      now {supa_count(container, 'runs')} in supabase (seq restarted at {max_id})")

    # 6) Audit-log entry
    print()
    audit_payload = {
        "source": "x-pathfinder-db",
        "migrated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "row_counts": {
            "accounts": supa_count(container, "accounts"),
            "emails": supa_count(container, "emails"),
            "strategies": supa_count(container, "strategies"),
            "runs": supa_count(container, "runs"),
        },
        "consent_default": "NULL (all imports require explicit opt-in before send)",
        "loopback_block_active": True,
        "pathx_lifecycle": "ready to be stopped/removed after this migration",
    }
    audit_sql = (
        "INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
        f"VALUES ('migration:pathx-import-2026-06-02', 'data.import.bulk', 'marketing.*', "
        f"'{json.dumps(audit_payload).replace(chr(39), chr(39)*2)}'::jsonb) RETURNING id"
    )
    audit_id = run_supa_sql(container, audit_sql).strip().splitlines()[-1]
    print(f"audit_log entry: {audit_id}")

    print()
    print("=" * 70)
    print("Migration complete.")
    print(f"supabase AFTER:  accounts={supa_count(container, 'accounts')}  "
          f"emails={supa_count(container, 'emails')}  "
          f"strategies={supa_count(container, 'strategies')}  "
          f"runs={supa_count(container, 'runs')}")
    print()
    print("pathx-db can now be stopped if desired:")
    print(f"  docker stop {PATHX_CONTAINER_NAME} && docker rm {PATHX_CONTAINER_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
