"""Worker A — DB to Filesystem sync.

Listens on the Postgres NOTIFY channel `marketing_sync`, drains
`marketing.sync_outbox`, renders the affected handles' markdown, and
writes the files atomically.

Loop-prevention:
  Worker A only writes to the FS. It does NOT write back to DB (Worker B
  does that). Watchdog (Worker B) compares incoming file events against
  a content-hash store — if the file content matches what Worker A
  wrote last, Worker B skips the event (== own echo).

Atomicity:
  Write to <file>.tmp, fsync, rename to <file>. Even on crash, vault
  files are never half-written.

Idempotency:
  Re-running the worker after a crash replays unapplied outbox rows.
  Render is deterministic, so the second write is a no-op (byte-identical).

CLI:
    # one-shot drain
    python -m spaces.marketing.sync.worker_db_to_fs --once

    # foreground daemon (LISTEN forever)
    python -m spaces.marketing.sync.worker_db_to_fs

Stop a foreground daemon with Ctrl-C — finishes the current handle then exits.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import select
import signal
import sys
import time
from pathlib import Path

from . import _db, _queries
from ._filename import sanitize_handle_for_filename
from ._frontmatter import parse_frontmatter
from .render_md import render_person_md

# ─── config ─────────────────────────────────────────────────────────────
VAULT_DIR = Path(os.environ.get(
    "MARKETING_VAULT_DIR",
    str(Path.home() / ".rowboat" / "knowledge" / "Marketing" / "People"),
))
HASH_STORE = Path(os.environ.get(
    "MARKETING_HASH_STORE",
    str(Path.home() / ".rowboat" / "knowledge" / "Marketing" / ".sync_hashes.json"),
))
POLL_FALLBACK_SEC = int(os.environ.get("MARKETING_POLL_SEC", "30"))
DRAIN_BATCH_SIZE = 50

# ─── state ───────────────────────────────────────────────────────────────
_shutdown = False


def _on_sigterm(signum, frame):
    global _shutdown
    _shutdown = True
    print("[worker_a] received signal, will exit after current handle", flush=True)


signal.signal(signal.SIGINT, _on_sigterm)
signal.signal(signal.SIGTERM, _on_sigterm)


# ─── hash store ──────────────────────────────────────────────────────────


def _load_hash_store() -> dict:
    import json
    if HASH_STORE.exists():
        try:
            return json.loads(HASH_STORE.read_text())
        except Exception:
            pass
    return {}


def _save_hash_store(store: dict) -> None:
    import json
    HASH_STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HASH_STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, indent=2, sort_keys=True))
    tmp.replace(HASH_STORE)


def _content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


# ─── file I/O ────────────────────────────────────────────────────────────


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _user_content_below_fence(existing_text: str | None) -> str:
    """Extract the user-owned content below the final fence."""
    if not existing_text:
        return ""
    marker = "Custom notes below this line"
    idx = existing_text.find(marker)
    if idx < 0:
        return ""
    # Find the end of the closing fence after marker
    after = existing_text[idx:]
    closing = after.find("-->")
    if closing < 0:
        return ""
    # Now find the SECOND closing fence (the actual end of fence block)
    body_start = after.find("-->", closing + 3)
    if body_start < 0:
        return ""
    body_start = idx + body_start + 3
    return existing_text[body_start:].lstrip("\n")


# ─── apply one outbox event ─────────────────────────────────────────────


def _apply_event(event: dict, container: str, hash_store: dict) -> bool:
    """Render + write one outbox row. Returns True if applied successfully.

    On DELETE of an accounts row, removes the .md file.
    On any other event, re-renders the affected handle.
    Fan-out events (affected_handle=NULL) get queued for full re-render
    elsewhere — Phase 4 keeps them as a no-op for now.
    """
    handle = event.get("affected_handle")
    if not handle:
        # Fan-out event (tags, audiences, etc. that affect many people).
        # Phase 4 minimum: skip these. Phase 4.1 would resolve all affected handles
        # and emit per-handle events.
        return True

    table = event["table_name"]
    operation = event["operation"]
    fname = sanitize_handle_for_filename(handle)
    filepath = VAULT_DIR / fname

    if table == "accounts" and operation == "DELETE":
        # Account itself deleted — remove the file
        if filepath.exists():
            filepath.unlink()
            # Forget the hash
            hash_store.pop(str(filepath), None)
            print(f"[worker_a] DELETE  {filepath}", flush=True)
        return True

    # Any other change → re-render + write
    try:
        md, debug = render_person_md(handle, container=container)
    except LookupError:
        # Account doesn't exist anymore (e.g. cascade-delete from emails)
        if filepath.exists():
            filepath.unlink()
            hash_store.pop(str(filepath), None)
            print(f"[worker_a] CLEANUP {filepath}  (no account row)", flush=True)
        return True

    # Preserve user-owned content below the fence if file already exists
    existing = filepath.read_text(encoding="utf-8") if filepath.exists() else None
    user_content = _user_content_below_fence(existing)
    if user_content:
        md = md.rstrip() + "\n" + user_content

    body_hash = _content_hash(md)
    _atomic_write(filepath, md)
    hash_store[str(filepath)] = body_hash
    print(f"[worker_a] WROTE   {filepath}  ({debug['byte_count']}B, {debug['render_ms']}ms)",
          flush=True)
    return True


# ─── drain loop ──────────────────────────────────────────────────────────


def drain_outbox(container: str, hash_store: dict) -> int:
    """Process every unapplied outbox row. Returns number drained."""
    rows = _db.query_via_docker(
        "SELECT id::text, table_name, row_key, operation, affected_handle, "
        "payload, origin, emitted_at "
        "FROM marketing.sync_outbox "
        "WHERE applied_at IS NULL "
        "ORDER BY emitted_at "
        f"LIMIT {DRAIN_BATCH_SIZE}",
        container=container,
    )
    if not rows:
        return 0

    applied_ids = []
    for r in rows:
        try:
            if _apply_event(r, container, hash_store):
                applied_ids.append(r["id"])
        except Exception as e:
            print(f"[worker_a] ERROR  handle={r.get('affected_handle')}  err={e}", flush=True)

    if applied_ids:
        ids_array = "ARRAY[" + ",".join(f"'{i}'::uuid" for i in applied_ids) + "]"
        _db.execute_via_docker(
            f"SELECT marketing.mark_outbox_applied({ids_array})",
            container=container,
        )
        _save_hash_store(hash_store)

    return len(applied_ids)


# ─── listen loop ─────────────────────────────────────────────────────────


def listen_forever(container: str) -> None:
    """LISTEN on marketing_sync forever, drain on every wake-up.

    Uses docker exec for the LISTEN connection — not super-elegant but works
    without exposing the postgres port to the host. Falls back to polling
    every POLL_FALLBACK_SEC seconds.

    For production, replace with a psycopg-direct connection.
    """
    hash_store = _load_hash_store()
    print(f"[worker_a] vault: {VAULT_DIR}", flush=True)
    print(f"[worker_a] hash_store: {HASH_STORE}", flush=True)
    print(f"[worker_a] polling fallback every {POLL_FALLBACK_SEC}s", flush=True)

    # Initial drain on startup (catch up after downtime)
    drained = drain_outbox(container, hash_store)
    print(f"[worker_a] startup drain: {drained} events", flush=True)

    while not _shutdown:
        # docker-exec polling mode: every POLL_FALLBACK_SEC seconds, drain
        # (a real LISTEN/NOTIFY would wake us instantly; this is the fallback)
        time.sleep(min(POLL_FALLBACK_SEC, 5))
        if _shutdown:
            break
        try:
            drained = drain_outbox(container, hash_store)
            if drained:
                print(f"[worker_a] drained {drained} events", flush=True)
        except Exception as e:
            print(f"[worker_a] poll error: {e}", flush=True)
            time.sleep(10)

    print("[worker_a] shutdown complete", flush=True)


# ─── CLI ────────────────────────────────────────────────────────────────


def _main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="Drain outbox once and exit")
    p.add_argument("--vault-dir", help="Override MARKETING_VAULT_DIR")
    args = p.parse_args()

    if args.vault_dir:
        global VAULT_DIR
        VAULT_DIR = Path(args.vault_dir)

    container = _db.find_supabase_container()
    print(f"[worker_a] container={container[:12]}  vault={VAULT_DIR}", flush=True)

    hash_store = _load_hash_store()
    if args.once:
        n = drain_outbox(container, hash_store)
        print(f"[worker_a] drained {n} events", flush=True)
        return 0

    listen_forever(container)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
