"""RLS smoke-test for marketing.* schema.

Verifies the Phase-1 lockdown:
  - anon and authenticated roles get "permission denied" on any marketing.*
  - service_role can read/write all marketing.* tables

How the test reaches Postgres:
  The marketing schema is NOT exposed via PostgREST (PGRST106 — only
  `public, graphql_public` are reachable on :54321/rest/v1). That's by
  design for Phase 1 — UI talks via the MarketingAgent backend, not
  directly. So this test runs SQL via `docker exec vibemind_supabase-db
  psql` with explicit `SET ROLE <role>` to simulate the auth context
  PostgREST would set for a JWT-authenticated request.

Run:
    python spaces/marketing/scripts/test_rls.py

Exit 0 = all checks passed.
Exit 1 = at least one check failed — RLS not effective, do NOT proceed
with real data.
"""
from __future__ import annotations

import subprocess
import sys


def find_supabase_db_container() -> str | None:
    """Return the running supabase-db container ID (or None)."""
    res = subprocess.run(
        ["docker", "ps", "-qf", "name=vibemind_supabase-db"],
        capture_output=True, text=True, check=False,
    )
    cid = res.stdout.strip().split("\n")[0] if res.stdout else ""
    return cid or None


def psql_as(container: str, role: str, sql: str) -> tuple[int, str]:
    """Run a SQL statement as a given Postgres role. Returns (returncode, output)."""
    wrapped = f"SET ROLE {role}; {sql}"
    res = subprocess.run(
        ["docker", "exec", container, "psql", "-U", "supabase_admin", "-d", "postgres",
         "-tAc", wrapped],
        capture_output=True, text=True, check=False,
    )
    return res.returncode, (res.stdout + res.stderr).strip()


def check(label: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  — {detail}" if detail else ""))
    return cond


def main() -> int:
    container = find_supabase_db_container()
    if not container:
        print("ERROR: vibemind_supabase-db container not running")
        return 2
    print(f"Testing against supabase-db container {container[:12]}")
    print()

    results: list[bool] = []

    # Roles whose access must be DENIED on the marketing schema
    for role in ("anon", "authenticated"):
        print(f"== {role} ->  marketing.audiences SELECT  ==")
        rc, out = psql_as(container, role, "SELECT COUNT(*) FROM marketing.audiences")
        print(f"  rc={rc}  out={out[:200]}")
        denied = "permission denied" in out.lower()
        results.append(check(f"{role} read denied", denied, f"rc={rc}"))

        print(f"== {role} ->  marketing.audiences INSERT  ==")
        rc, out = psql_as(container, role,
                          "INSERT INTO marketing.audiences (name) VALUES ('rls-smoke-' || clock_timestamp()::text)")
        print(f"  rc={rc}  out={out[:200]}")
        denied = "permission denied" in out.lower()
        results.append(check(f"{role} write denied", denied, f"rc={rc}"))

        print(f"== {role} ->  marketing.audit_log SELECT (extra-sensitive)  ==")
        rc, out = psql_as(container, role, "SELECT COUNT(*) FROM marketing.audit_log")
        denied = "permission denied" in out.lower()
        results.append(check(f"{role} audit_log read denied", denied, f"rc={rc}"))
        print()

    # service_role: must SUCCEED.
    # Output may interleave "SET" / "INSERT 0 1" lines with the actual data.
    # We extract the last non-empty line that looks like a number.
    def last_numeric_line(text: str) -> str | None:
        for line in reversed(text.strip().splitlines()):
            stripped = line.strip()
            if stripped.isdigit():
                return stripped
        return None

    print("== service_role ->  marketing.audiences SELECT  ==")
    rc, out = psql_as(container, "service_role", "SELECT COUNT(*) FROM marketing.audiences")
    print(f"  rc={rc}  out={out[:200]}")
    num = last_numeric_line(out)
    succ = rc == 0 and num is not None
    results.append(check("service_role can read", succ, f"rows={num}"))

    print("== service_role ->  marketing.tags INSERT + DELETE roundtrip  ==")
    rc, out = psql_as(container, "service_role",
                      "INSERT INTO marketing.tags (name, color, kind) VALUES ('rls-smoke-test', '#000', 'system') RETURNING id")
    print(f"  rc={rc}  out={out[:200]}")
    new_id = last_numeric_line(out)
    insert_ok = rc == 0 and new_id is not None
    results.append(check("service_role can write", insert_ok, f"id={new_id}"))
    if insert_ok:
        rc2, out2 = psql_as(container, "service_role",
                            "DELETE FROM marketing.tags WHERE name='rls-smoke-test' RETURNING id")
        cleaned = last_numeric_line(out2)
        cleanup_ok = rc2 == 0 and cleaned is not None
        results.append(check("service_role cleanup", cleanup_ok, f"deleted={cleaned}"))

    print()
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"=== {passed}/{total} checks passed ===")
    if passed == total:
        print("RLS Phase-1 lockdown is effective.")
        return 0
    print("RLS lockdown FAILED. Do not proceed with real data.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
