"""Worker B — Filesystem to DB sync.

Watches `~/.rowboat/knowledge/Marketing/People/` for file events:

  - File DELETED  -> DELETE FROM marketing.accounts WHERE handle=<...>
                     (cascade-delete propagates to emails, tags, etc.)
  - File MODIFIED -> compare content-hash against Worker A's last-write
                     hash. If identical -> own echo, ignore.
                     If different -> log warning (Felix edited frontmatter,
                     not allowed in Phase 5; future Phase: parse + apply
                     body-section changes).
  - File CREATED  -> probably user manually created a file. Same handling
                     as MODIFIED (don't touch DB; log).

Loop-prevention:
  Before any DB write, set the session GUC `marketing.sync_origin = 'fs'`
  so the trigger skips outbox emit. No echo back to FS via Worker A.

Watchdog dependency:
  pip install watchdog

CLI:
    python -m spaces.marketing.sync.worker_fs_to_db

Stop with Ctrl-C.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

from . import _db
from ._filename import sanitize_handle_for_filename
from ._frontmatter import parse_frontmatter

# Use watchdog if available; fall back to a simple polling loop.
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

# ─── config ─────────────────────────────────────────────────────────────
VAULT_DIR = Path(os.environ.get(
    "MARKETING_VAULT_DIR",
    str(Path.home() / ".rowboat" / "knowledge" / "Marketing" / "People"),
))
HASH_STORE = Path(os.environ.get(
    "MARKETING_HASH_STORE",
    str(Path.home() / ".rowboat" / "knowledge" / "Marketing" / ".sync_hashes.json"),
))
POLL_INTERVAL = int(os.environ.get("MARKETING_FS_POLL_SEC", "5"))

_shutdown = False


def _on_sigterm(signum, frame):
    global _shutdown
    _shutdown = True
    print("[worker_b] received signal, will exit", flush=True)


signal.signal(signal.SIGINT, _on_sigterm)
signal.signal(signal.SIGTERM, _on_sigterm)


# ─── hash store (shared with Worker A) ──────────────────────────────────


def _load_hash_store() -> dict:
    if HASH_STORE.exists():
        try:
            return json.loads(HASH_STORE.read_text())
        except Exception:
            pass
    return {}


def _save_hash_store(store: dict) -> None:
    HASH_STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HASH_STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, indent=2, sort_keys=True))
    tmp.replace(HASH_STORE)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ─── DB writeback ────────────────────────────────────────────────────────


def delete_account_in_db(handle: str, container: str) -> bool:
    """Delete marketing.accounts row for this handle. Cascade flows through
    emails/email_tags/audience_members. Uses sync_origin='fs' to prevent
    the trigger from emitting another outbox event (= no loop back to FS).
    """
    # Wrap in a transaction so set_config + DELETE share the same session
    sql = (
        "BEGIN; "
        "SELECT set_config('marketing.sync_origin', 'fs', true); "
        f"DELETE FROM marketing.accounts WHERE handle = '{handle.replace(chr(39), chr(39)*2)}'; "
        "COMMIT;"
    )
    try:
        out = _db.execute_via_docker(sql, container=container)
        print(f"[worker_b] DELETE  handle={handle}  result={out.strip()[:80]}", flush=True)
        return True
    except Exception as e:
        print(f"[worker_b] DELETE  handle={handle}  ERROR: {e}", flush=True)
        return False


# ─── event handlers ──────────────────────────────────────────────────────


def _filename_to_handle(path: Path) -> str | None:
    """Try to recover the original handle from a filename.

    First-line attempt: read frontmatter. The frontmatter has the canonical
    `handle:` field which survives any filename sanitization.

    Fallback: use the filename stem if file is unreadable (e.g. on DELETE event).
    """
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:4096]
            parsed = parse_frontmatter(text)
            if parsed and parsed.get("handle"):
                return str(parsed["handle"])
        except Exception:
            pass
    # File doesn't exist anymore (DELETE) — use the stem
    return path.stem


def _handle_event(path: Path, kind: str, container: str, hash_store: dict) -> None:
    """Dispatch a file system event to the appropriate DB action."""
    if path.suffix != ".md":
        return
    if path.name.startswith("."):
        return

    if kind == "deleted":
        handle = path.stem  # file gone, can't read frontmatter
        # Was this a known file? Forget the hash either way.
        hash_store.pop(str(path), None)
        _save_hash_store(hash_store)
        if delete_account_in_db(handle, container):
            print(f"[worker_b] propagated FS-delete -> DB.delete  handle={handle}", flush=True)
        return

    if kind in ("created", "modified"):
        if not path.exists():
            # Race: was deleted between event and our read
            return
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[worker_b] cannot read {path}: {e}", flush=True)
            return

        observed_hash = _content_hash(text)
        last_hash = hash_store.get(str(path))

        if observed_hash == last_hash:
            # Same content as last Worker A write — own echo, ignore silently
            return

        # Content has diverged from what Worker A wrote.
        # Phase 5 policy: log warning, do NOT propagate frontmatter edits.
        # Future phase: parse parts of body section, apply allowed fields.
        handle = _filename_to_handle(path)
        print(f"[worker_b] WARN   file changed by user — not propagating  handle={handle}  path={path}",
              flush=True)
        # Refresh the hash so we don't warn again about the same content
        hash_store[str(path)] = observed_hash
        _save_hash_store(hash_store)


# ─── watchdog mode ──────────────────────────────────────────────────────


if HAS_WATCHDOG:
    class MarketingVaultHandler(FileSystemEventHandler):
        def __init__(self, container: str, hash_store: dict):
            self.container = container
            self.hash_store = hash_store

        def on_deleted(self, event):
            if event.is_directory:
                return
            _handle_event(Path(event.src_path), "deleted", self.container, self.hash_store)

        def on_modified(self, event):
            if event.is_directory:
                return
            _handle_event(Path(event.src_path), "modified", self.container, self.hash_store)

        def on_created(self, event):
            if event.is_directory:
                return
            _handle_event(Path(event.src_path), "created", self.container, self.hash_store)


def _run_watchdog(container: str) -> None:
    if not HAS_WATCHDOG:
        raise RuntimeError("watchdog not installed — pip install watchdog")
    hash_store = _load_hash_store()
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    handler = MarketingVaultHandler(container, hash_store)
    observer = Observer()
    observer.schedule(handler, str(VAULT_DIR), recursive=False)
    observer.start()
    print(f"[worker_b] watching {VAULT_DIR}", flush=True)
    try:
        while not _shutdown:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


# ─── polling fallback (no watchdog) ─────────────────────────────────────


def _run_polling(container: str) -> None:
    """If watchdog isn't available, poll the directory."""
    hash_store = _load_hash_store()
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    # Track which files we've seen, so we can detect deletions
    seen: dict[str, str] = {}  # path -> content_hash
    for p in VAULT_DIR.glob("*.md"):
        try:
            seen[str(p)] = _content_hash(p.read_text(encoding="utf-8"))
        except Exception:
            pass

    print(f"[worker_b] polling mode, interval={POLL_INTERVAL}s, watching {VAULT_DIR}", flush=True)
    print(f"[worker_b] tracking {len(seen)} initial files", flush=True)

    while not _shutdown:
        time.sleep(POLL_INTERVAL)
        if _shutdown:
            break
        try:
            current = set()
            for p in VAULT_DIR.glob("*.md"):
                current.add(str(p))
                try:
                    h = _content_hash(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(p) not in seen:
                    _handle_event(p, "created", container, hash_store)
                    seen[str(p)] = h
                elif h != seen[str(p)]:
                    _handle_event(p, "modified", container, hash_store)
                    seen[str(p)] = h
            # detect deletions
            for path_str in list(seen.keys()):
                if path_str not in current:
                    _handle_event(Path(path_str), "deleted", container, hash_store)
                    del seen[path_str]
        except Exception as e:
            print(f"[worker_b] poll loop error: {e}", flush=True)


# ─── CLI ────────────────────────────────────────────────────────────────


def _main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vault-dir", help="Override MARKETING_VAULT_DIR")
    p.add_argument("--force-polling", action="store_true", help="Use polling even if watchdog is installed")
    args = p.parse_args()

    if args.vault_dir:
        global VAULT_DIR
        VAULT_DIR = Path(args.vault_dir)

    container = _db.find_supabase_container()
    print(f"[worker_b] container={container[:12]}  vault={VAULT_DIR}  watchdog={HAS_WATCHDOG}",
          flush=True)

    if HAS_WATCHDOG and not args.force_polling:
        _run_watchdog(container)
    else:
        _run_polling(container)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
