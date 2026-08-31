"""Migrate VibeMind SQLite data to local Supabase (PostgreSQL).

Usage:
    python migrate_sqlite_to_supabase.py
    python migrate_sqlite_to_supabase.py --supabase-url http://localhost:54321 --anon-key <key>
"""
import argparse
import json
import sqlite3
import sys
import urllib.request
import urllib.error

SQLITE_PATH = "../voice/python/vibemind.db"

# Tables to migrate with their column mappings (SQLite -> Supabase)
# Order matters: parent tables first (FKs)
TABLES = [
    "ideas",
    "projects",
    "canvas_nodes",
    "canvas_edges",
    "conversation_sessions",
    "conversation_history",
    "shuttles",
    "exploration_sessions",
    "exploration_nodes",
    "discovered_edges",
    "mermaid_diagrams",
    "scheduled_tasks",
    "flowzen_checkins",
    "flowzen_activity",
    "flowzen_diary",
    "videos",
    "video_projects",
    "video_project_persons",
    "video_pipeline_steps",
    "persistent_tasks",
    "user_preferences",
]


def migrate(sqlite_path: str, supabase_url: str, anon_key: str):
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    total = 0
    for table in TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            print(f"  [{table}] table not in SQLite — skip")
            continue

        if not rows:
            print(f"  [{table}] 0 rows — skip")
            continue

        # Convert rows to dicts, handle JSON columns
        records = []
        for row in rows:
            d = dict(row)
            # Convert JSON string columns to actual JSON for Supabase
            for k, v in d.items():
                if isinstance(v, str) and v.startswith(("[", "{")):
                    try:
                        d[k] = json.loads(v)
                    except json.JSONDecodeError:
                        pass
                # Skip None/null embedding vectors (too large)
                if k == "embedding_vector" and v is not None:
                    try:
                        d[k] = json.loads(v) if isinstance(v, str) else None
                    except Exception:
                        d[k] = None
            # Skip rows with NULL primary key
            if d.get("id") is None:
                continue
            # Remove columns that don't exist in Postgres schema
            # (SQLite may have extra columns from old migrations)
            records.append(d)

        if not records:
            print(f"  [{table}] 0 valid rows after filtering -- skip")
            continue

        # Query Postgres columns to filter out SQLite-only fields
        try:
            col_url = f"{supabase_url}/rest/v1/{table}?select=*&limit=0"
            col_req = urllib.request.Request(col_url, headers={
                "apikey": anon_key, "Authorization": f"Bearer {anon_key}"
            })
            col_resp = urllib.request.urlopen(col_req, timeout=5)
            # Extract column names from Content-Profile or response headers
            # Simpler: just try the POST and let it fail, or use schema query
        except Exception:
            pass

        # Filter records to only include columns that exist in Postgres
        # by querying the schema once
        try:
            schema_url = f"{supabase_url}/rest/v1/{table}?limit=0"
            schema_req = urllib.request.Request(schema_url, headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {anon_key}",
                "Accept": "application/json",
            })
            schema_resp = urllib.request.urlopen(schema_req, timeout=5)
            # PostgREST returns empty array for limit=0, but the OPTIONS
            # endpoint gives columns. Use a simpler approach: try POST,
            # if column error, remove that column and retry.
        except Exception:
            pass

        # POST to Supabase REST API (PostgREST)
        url = f"{supabase_url}/rest/v1/{table}"
        headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",  # Upsert
        }
        body = json.dumps(records, default=str, ensure_ascii=False).encode("utf-8")

        # Retry loop: strip unknown columns on PGRST204 errors
        max_retries = 15
        for attempt in range(max_retries):
            body = json.dumps(records, default=str, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                print(f"  [{table}] {len(records)} rows -> HTTP {resp.status}")
                total += len(records)
                break
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
                # Extract missing column name from error
                if "PGRST204" in err_body or "Could not find the" in err_body:
                    import re
                    m = re.search(r"'(\w+)' column", err_body)
                    if m:
                        bad_col = m.group(1)
                        records = [{k: v for k, v in r.items() if k != bad_col} for r in records]
                        print(f"  [{table}] Stripped unknown column '{bad_col}', retrying...")
                        continue
                print(f"  [{table}] {len(records)} rows -> ERROR {e.code}: {err_body}")
                break
            except Exception as e:
                print(f"  [{table}] ERROR: {e}")
                break

    conn.close()
    print(f"\nMigrated {total} rows total")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=SQLITE_PATH)
    parser.add_argument("--supabase-url", default="http://localhost:54321")
    parser.add_argument("--anon-key", default=None,
                        help="Supabase anon key (auto-detected from 'npx supabase status')")
    args = parser.parse_args()

    # Auto-detect anon key if not provided
    anon_key = args.anon_key
    if not anon_key:
        import subprocess
        try:
            r = subprocess.run(
                ["npx", "supabase", "status", "--output", "json"],
                capture_output=True, text=True, timeout=15,
                cwd=str(__import__("pathlib").Path(__file__).parent)
            )
            status = json.loads(r.stdout)
            anon_key = status.get("ANON_KEY", status.get("anon_key", ""))
            api_url = status.get("API_URL", status.get("api_url", args.supabase_url))
            print(f"Supabase API: {api_url}")
            print(f"Anon key: {anon_key[:20]}...")
            args.supabase_url = api_url
        except Exception as e:
            print(f"Could not auto-detect Supabase config: {e}")
            print("Provide --anon-key manually")
            sys.exit(1)

    print(f"\nMigrating {args.sqlite} -> {args.supabase_url}")
    print("-" * 50)
    migrate(args.sqlite, args.supabase_url, anon_key)


if __name__ == "__main__":
    main()
