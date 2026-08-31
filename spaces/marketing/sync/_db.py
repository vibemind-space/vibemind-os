"""Thin DB access layer for the marketing sync workers.

Reaching supabase-db, auto-selected at call time:

  A) REMOTE docker-exec over SSH — when SUPABASE_SSH_HOST is set: run
     `ssh <host> docker exec -i <container> psql ...` against the container
     as its owner (supabase_admin, trust-auth). Introduced with the Proxmox
     split (2026-07-15) so the host-side marketing workers reach the
     AUTHORITATIVE Supabase on the offload VM (192.168.178.65) without
     exposing a network postgres role or granting extra DB privileges. SQL
     always travels on stdin, never a shell command line.

  B) LOCAL docker-exec — the historical default: `docker exec` against the
     local vibemind_supabase-db. Active when SUPABASE_SSH_HOST is unset.

Both expose the same query()/execute() surface and IDENTICAL output
semantics (results shipped as one jsonb_agg(row_to_json()) blob), so callers
are agnostic to which path is active. Flip between them by (un)setting one
env var — the re-point to Proxmox is fully reversible.

Selection env (read at call time; also honoured from the repo .env):
  SUPABASE_SSH_HOST      ssh alias/host of the VM (e.g. offload-vm) -> mode A
  SUPABASE_DB_CONTAINER  remote container name (e.g. debian-supabase-db-1)
  SUPABASE_DB_USER       psql role (default supabase_admin)
  SUPABASE_DB_NAME       database (default postgres)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

_PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
_REPO_ROOT = next((p for p in (_PKG_ROOT, *_PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), _PKG_ROOT)
_LOCAL_CONTAINER_NAME = "vibemind_supabase-db"

# Config keys accepted from the process env or, as a fallback, the repo .env.
_CONFIG_KEYS = ("SUPABASE_SSH_HOST", "SUPABASE_DB_CONTAINER",
                "SUPABASE_DB_USER", "SUPABASE_DB_NAME")
_config_loaded = False


# NOTE on encoding: psql in the Linux container emits UTF-8. With bare
# text=True Python decodes using the Windows locale codepage (cp1252) —
# bytes like 0x9D (e.g. inside a UTF-8 typographic quote U+201D) are
# undecodable there. On Windows the pipe is read by a helper thread; when
# its decode raises, communicate() silently returns stdout=None and the
# caller crashes far away from the real cause. Hence encoding='utf-8' +
# errors='replace' on EVERY subprocess.run below.

def _load_config_from_env_file() -> None:
    """One-time: fill any missing SUPABASE_* config keys from the repo .env.

    Never overrides values already present in the process env. Mirrors the
    workers' own .env fallback so `_db` picks up the Proxmox re-point whether
    or not the launcher injected the vars into the process environment.
    """
    global _config_loaded
    if _config_loaded:
        return
    _config_loaded = True
    env_file = _REPO_ROOT / ".env"
    missing = [k for k in _CONFIG_KEYS if not os.environ.get(k)]
    if not env_file.exists() or not missing:
        return
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        for k in missing:
            if line.startswith(k + "="):
                os.environ.setdefault(
                    k, line.split("=", 1)[1].strip().strip('"').strip("'"))


def _cfg(key: str, default: str = "") -> str:
    _load_config_from_env_file()
    return os.environ.get(key, default).strip()


def find_supabase_container() -> str:
    """Locate the running LOCAL supabase-db container ID (mode B only)."""
    res = subprocess.run(
        ["docker", "ps", "-qf", f"name={_LOCAL_CONTAINER_NAME}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=True,
    )
    cid = res.stdout.strip().split("\n")[0] if res.stdout.strip() else ""
    if not cid:
        raise RuntimeError(f"{_LOCAL_CONTAINER_NAME} container not running")
    return cid


def _resolve_container(container: str | None) -> str:
    """Pick the container to exec into: explicit arg > remote cfg > local lookup."""
    if container:
        return container
    if _cfg("SUPABASE_SSH_HOST"):
        name = _cfg("SUPABASE_DB_CONTAINER")
        if not name:
            raise RuntimeError(
                "SUPABASE_SSH_HOST is set but SUPABASE_DB_CONTAINER is missing")
        return name
    return find_supabase_container()


def _psql_argv(container: str) -> list[str]:
    """Build the argv for `psql` reading SQL from stdin, local or over SSH.

    SQL is fed on stdin (`-f -`), so it never passes through a shell command
    line — no quoting hazard regardless of the SQL's contents, which matters
    doubly for the SSH path where args are re-parsed by the remote shell.
    The fixed tokens below contain no spaces, so joining them for the remote
    shell is safe without per-token quoting.
    """
    user = _cfg("SUPABASE_DB_USER", "supabase_admin")
    db = _cfg("SUPABASE_DB_NAME", "postgres")
    inner = ["docker", "exec", "-i", container,
             "psql", "-U", user, "-d", db, "-tA", "-f", "-"]
    ssh_host = _cfg("SUPABASE_SSH_HOST")
    if ssh_host:
        return ["ssh", ssh_host, *inner]
    return inner


def _run_psql(sql: str, container: str | None) -> str:
    """Feed `sql` to psql on stdin (local or over SSH); return stdout, raise on error."""
    argv = _psql_argv(_resolve_container(container))
    res = subprocess.run(
        argv, input=sql, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr.strip()[:500]}")
    return res.stdout


def query_via_docker(sql: str, params: dict | None = None, container: str | None = None) -> list[dict]:
    """Execute SQL, return rows as list[dict].

    Uses jsonb_agg + row_to_json to ship results as a single JSON array,
    avoiding shell parsing of psql tabular output. Name kept for backwards
    compat — it now dispatches to local docker-exec OR remote ssh+docker-exec
    depending on SUPABASE_SSH_HOST (see module docstring).
    """
    if params:
        # crude but safe param-substitution: inline each %(name)s via the
        # GUC-independent _sql_literal quoter (see below).
        full = sql
        for k in params:
            full = full.replace(f"%({k})s", _sql_literal(params[k]))
    else:
        full = sql

    json_sql = (
        f"SELECT COALESCE(jsonb_agg(row_to_json(t)), '[]'::jsonb) AS rows FROM ({full}) t"
    )
    out = _run_psql(json_sql, container).strip()
    if not out:
        return []
    return json.loads(out)


def query_one(sql: str, params: dict | None = None, container: str | None = None) -> dict | None:
    rows = query_via_docker(sql, params, container)
    return rows[0] if rows else None


def execute_via_docker(sql: str, container: str | None = None) -> str:
    """Run a write/DDL statement (local or over SSH), return stdout."""
    return _run_psql(sql, container)


def _sql_literal(value: Any) -> str:
    """Safely quote a value for direct SQL substitution.

    GUC-independent escaping, modelled on libpq's PQescapeLiteral:
      - single quotes are always doubled ('');
      - if the value contains a backslash, the literal is emitted with an
        explicit E'...' prefix and backslashes are doubled, so the result is
        correct REGARDLESS of the server's `standard_conforming_strings`
        setting (a plain '...' literal would let a stray backslash escape the
        following quote when SCS is off, defeating the quote-doubling);
      - NUL (\\x00) is rejected — PostgreSQL text cannot store it, and because
        these literals are passed to `psql` as an argv string it would
        truncate the command at the NUL (DoS / query corruption).

    Hardened after an automated SQL-injection review (2026-06-16): several
    callers in api/server.py feed external HTTP input through this function, so
    it must be safe for untrusted input — not merely for trusted templates.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    # string
    s = str(value)
    if "\x00" in s:
        raise ValueError("NUL byte not allowed in SQL string literal")
    if "\\" in s:
        # Backslash present: doubling quotes alone is unsafe when
        # standard_conforming_strings=off. Use an escape-string literal and
        # double both backslashes and quotes — unambiguous in either GUC mode.
        s = s.replace("\\", "\\\\").replace("'", "''")
        return f"E'{s}'"
    s = s.replace("'", "''")
    return f"'{s}'"
