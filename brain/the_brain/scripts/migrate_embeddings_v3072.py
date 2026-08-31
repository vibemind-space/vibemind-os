"""
Migrate every cognitive Qdrant collection from the old 1024-dim Qwen
embedding space to the new 3072-dim embedding-service space, preserving
point IDs and payload — only the `semantic` vector changes (any existing
`neural` vector is carried over unchanged, never dropped).

Prerequisite: the embedding-service container must be reachable (this
script re-embeds via core.qdrant_kg.Embedder, the same client brain-core
uses) and brain-core (+ siblings) should be scaled to replicas:0 for the
ENTIRE migration window — from before the first --commit run until
--cutover actually reports "cutover done: '<name>' now aliases '<new>'"
for every collection, NOT just until --commit finishes. Because --cutover
never auto-deletes, it can stop partway at an intermediate state
("... already archived as '<archive>' — delete it manually ...") that
persists indefinitely until a human deletes the old raw collection and
re-runs --cutover; don't scale brain-core back up while any collection is
still in that intermediate state (see docs/superpowers/specs/2026-07-13-
brain-embedder-external-api-design.md, "Migration" section).

Usage:
    # 1. Show what would happen, no writes (safe to run any time)
    python scripts/migrate_embeddings_v3072.py --dry-run

    # 2. Populate the new 3072-dim physical collections (old ones untouched)
    python scripts/migrate_embeddings_v3072.py --commit

    # 3. After manually comparing old vs. new point counts printed above:
    #    create an archive alias for the old raw collection (kept, NOT
    #    deleted) and attempt to swap the logical alias onto the new
    #    physical collection. Mirrors migrate_kg_to_cognitive.py's own
    #    --archive-old convention: this script NEVER deletes a collection
    #    itself — a human deletes the old raw collection manually once
    #    satisfied, then re-runs --cutover to finish the alias swap.
    python scripts/migrate_embeddings_v3072.py --cutover
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, Set

_HERE = os.path.dirname(os.path.abspath(__file__))
_BRAIN_ROOT = os.path.dirname(_HERE)  # .../the_brain
if _BRAIN_ROOT not in sys.path:
    sys.path.insert(0, _BRAIN_ROOT)

from core.qdrant_kg import (  # noqa: E402
    COLLECTIONS, QDRANT_URL, PHYSICAL_VERSION_SUFFIX, NEURAL_DIM, SEMANTIC_DIM,
    Embedder,
)
from core import config as _cfg  # noqa: E402

SCROLL_BATCH = 100  # also the embedding-service /embed/batch chunk size


def _collect_ids(client, collection_name: str) -> Set[str]:
    """Scroll every point id in a collection (no payload/vectors) into a set."""
    ids: Set[str] = set()
    offset = None
    while True:
        batch, next_offset = client.scroll(
            collection_name=collection_name, limit=SCROLL_BATCH, offset=offset,
            with_payload=False, with_vectors=False,
        )
        ids.update(str(rec.id) for rec in batch)
        if next_offset is None:
            break
        offset = next_offset
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print plan, don't write (default)")
    ap.add_argument("--commit", action="store_true",
                     help="re-embed and populate new 3072-dim collections "
                          "(old ones untouched). Scale brain-core + siblings to "
                          "replicas:0 first and keep them there until --cutover "
                          "reports every collection's swap complete — not just "
                          "until this command finishes; --cutover can stop at an "
                          "intermediate 'archived, delete manually' state that "
                          "isn't done yet.")
    ap.add_argument("--cutover", action="store_true",
                     help="archive the old raw collection under an alias (kept, "
                          "never auto-deleted) and attempt to swap the logical "
                          "alias onto the new physical collection — run only "
                          "after verifying --commit's point counts")
    ap.add_argument("--url", default=QDRANT_URL, help=f"Qdrant URL (default: {QDRANT_URL})")
    ap.add_argument("--embedding-service-url", default=_cfg.embedding_service_url(),
                     help="embedding-service base URL")
    args = ap.parse_args()

    if not (args.dry_run or args.commit or args.cutover):
        args.dry_run = True  # be safe

    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm

    client = QdrantClient(url=args.url, timeout=60)

    print(f"[migrate] Qdrant URL:     {args.url}")
    print(f"[migrate] Embed service:  {args.embedding_service_url}")
    print(f"[migrate] Collections:    {len(COLLECTIONS)}")
    print()

    vectors_config = {
        "semantic": qm.VectorParams(size=SEMANTIC_DIM, distance=qm.Distance.COSINE),
        "neural": qm.VectorParams(size=NEURAL_DIM, distance=qm.Distance.COSINE, on_disk=True),
    }

    # ── --cutover: never auto-deletes. Mirrors migrate_kg_to_cognitive.py's
    # own --archive-old convention exactly: archive the old raw collection
    # under an alias, then attempt the real alias swap. If the raw collection
    # still exists, Qdrant refuses to let an alias share its name, so that
    # second call fails — we catch it and tell the operator to delete the
    # raw collection by hand and re-run. Re-running is idempotent: it detects
    # work already done (archive alias present / cutover already complete)
    # and skips it.
    if args.cutover:
        try:
            existing_collections = {c.name for c in client.get_collections().collections}
            existing_aliases = {a.alias_name: a.collection_name
                                 for a in client.get_aliases().aliases}
        except Exception as e:
            print(f"[migrate] ERROR: could not reach Qdrant at '{args.url}': {e}")
            return 1

        for logical, old_name in COLLECTIONS.items():
            new_name = f"{old_name}{PHYSICAL_VERSION_SUFFIX}"

            if existing_aliases.get(old_name) == new_name:
                print(f"[migrate] {old_name}: already aliased to '{new_name}' — nothing to do")
                continue

            old_is_alias = old_name in existing_aliases
            old_is_raw = old_name in existing_collections and not old_is_alias
            old_is_gone = old_name not in existing_collections and not old_is_alias

            if old_is_alias and not old_is_gone:
                print(f"[migrate] SKIP {old_name}: unexpected alias state "
                      f"('{old_name}' -> '{existing_aliases[old_name]}') — investigate manually")
                continue

            try:
                new_info = client.get_collection(new_name)
            except Exception as e:
                print(f"[migrate] SKIP {old_name}: target '{new_name}' not found "
                      f"(run --commit first): {e}")
                continue

            if old_is_raw:
                try:
                    old_info = client.get_collection(old_name)
                except Exception as e:
                    print(f"[migrate] SKIP {old_name}: {e}")
                    continue
                if old_info.points_count != new_info.points_count:
                    print(f"[migrate] REFUSING cutover for {old_name}: "
                          f"old={old_info.points_count} new={new_info.points_count} "
                          f"point counts differ — investigate before cutting over.")
                    continue

                print(f"[migrate] {old_name}: comparing point ID sets against "
                      f"'{new_name}' (this may take a while for large collections)...")
                old_ids = _collect_ids(client, old_name)
                new_ids = _collect_ids(client, new_name)
                if old_ids != new_ids:
                    missing = old_ids - new_ids
                    extra = new_ids - old_ids
                    print(f"[migrate] REFUSING cutover for {old_name}: point ID sets differ "
                          f"(in old but not new: {len(missing)}, in new but not old: "
                          f"{len(extra)}) — investigate before cutting over.")
                    continue

                existing_archive_alias = next(
                    (alias for alias, coll in existing_aliases.items()
                     if coll == old_name and alias.startswith(f"{old_name}-archive-")),
                    None,
                )
                if existing_archive_alias:
                    archive_name = existing_archive_alias
                    print(f"[migrate] {old_name}: an archive alias already exists "
                          f"('{archive_name}'), skipping re-archive")
                else:
                    archive_name = f"{old_name}-archive-{time.strftime('%Y%m%d-%H%M%S')}"
                    print(f"[migrate] archiving '{old_name}' -> alias '{archive_name}' "
                          f"(raw collection is kept, NOT deleted)")
                    client.update_collection_aliases(change_aliases_operations=[
                        qm.CreateAliasOperation(create_alias=qm.CreateAlias(
                            collection_name=old_name, alias_name=archive_name,
                        )),
                    ])

                try:
                    client.update_collection_aliases(change_aliases_operations=[
                        qm.CreateAliasOperation(create_alias=qm.CreateAlias(
                            collection_name=new_name, alias_name=old_name,
                        )),
                    ])
                    print(f"[migrate] cutover done: '{old_name}' now aliases '{new_name}'")
                except Exception as e:
                    print(f"[migrate] the collection '{old_name}' still exists as a raw "
                          f"collection (already archived as '{archive_name}') — delete it "
                          f"manually once you've verified '{new_name}', then re-run "
                          f"--cutover to complete the alias swap. ({e})")
                continue

            # old_is_gone: raw collection was already deleted manually by the
            # operator after a previous --cutover attempt — just finish the swap.
            print(f"[migrate] '{old_name}' no longer exists as a raw collection — "
                  f"completing alias swap to '{new_name}'")
            client.update_collection_aliases(change_aliases_operations=[
                qm.CreateAliasOperation(create_alias=qm.CreateAlias(
                    collection_name=new_name, alias_name=old_name,
                )),
            ])
            print(f"[migrate] cutover done: '{old_name}' now aliases '{new_name}'")
        return 0

    embedder = None
    existing_collections: Set[str] = set()
    try:
        # Needed even in --dry-run so a collection already cut over (old_name
        # aliases new_name) is reported as skipped instead of re-scanned.
        existing_aliases = {a.alias_name: a.collection_name
                             for a in client.get_aliases().aliases}
    except Exception as e:
        print(f"[migrate] ERROR: could not reach Qdrant at '{args.url}': {e}")
        return 1

    if args.commit:
        if args.embedding_service_url:
            # Embedder (core.qdrant_kg) reads its base URL from core.config at
            # construction time, so set the env var it looks at rather than
            # duplicating/under-validating the HTTP call ourselves — this way
            # we automatically inherit Embedder's dimension-mismatch check.
            os.environ["EMBEDDING_SERVICE_URL"] = args.embedding_service_url
        embedder = Embedder.get()
        # Minor: fetch the existing-collections set once, not once per collection.
        try:
            existing_collections = {c.name for c in client.get_collections().collections}
        except Exception as e:
            print(f"[migrate] ERROR: could not reach Qdrant at '{args.url}': {e}")
            return 1

    total_migrated = 0
    for logical, old_name in COLLECTIONS.items():
        new_name = f"{old_name}{PHYSICAL_VERSION_SUFFIX}"

        if existing_aliases.get(old_name) == new_name:
            print(f"[migrate] '{old_name}' already cut over to '{new_name}' — "
                  f"skipping (nothing to re-migrate).")
            continue

        try:
            old_info = client.get_collection(old_name)
        except Exception as e:
            print(f"[migrate] source '{old_name}' not found, skipping: {e}")
            continue
        print(f"[migrate] {old_name}: {old_info.points_count} points -> {new_name}")

        if args.commit and new_name not in existing_collections:
            client.create_collection(collection_name=new_name, vectors_config=vectors_config)
            existing_collections.add(new_name)
            print(f"[migrate]   created '{new_name}'")

        offset = None
        moved = 0
        t0 = time.time()
        while True:
            try:
                batch, next_offset = client.scroll(
                    collection_name=old_name, limit=SCROLL_BATCH, offset=offset,
                    with_payload=True, with_vectors=args.commit,
                )
            except Exception:
                print(f"[migrate] FAILED scrolling '{old_name}' at offset={offset!r} "
                      f"({moved} points already handled in this collection before the failure)")
                raise
            if not batch:
                break
            texts = [rec.payload.get("content", "") for rec in batch]
            if args.commit:
                try:
                    new_vectors = embedder.encode_batch(texts)
                    points = []
                    for i, rec in enumerate(batch):
                        vector_payload: Dict[str, object] = {"semantic": new_vectors[i]}
                        # Preserve any existing `neural` (TriBE, 20484-dim) vector
                        # unchanged — only `semantic` is re-embedded. rec.vector is
                        # a Dict[str, VectorOutput] for a named-vector collection
                        # per qdrant_client's VectorStructOutput type alias, where a
                        # dense named vector's VectorOutput is a plain List[float] —
                        # confirmed by reading qdrant_client's models.py in this
                        # environment, but NOT round-tripped against a live Qdrant
                        # server in this session; re-verify this exact shape against
                        # a real server response before trusting it in production.
                        if isinstance(rec.vector, dict) and rec.vector.get("neural"):
                            vector_payload["neural"] = rec.vector["neural"]
                        points.append(qm.PointStruct(
                            id=rec.id,
                            vector=vector_payload,
                            payload=rec.payload,
                        ))
                    client.upsert(collection_name=new_name, points=points, wait=True)
                except Exception:
                    print(f"[migrate] FAILED embedding/upserting batch for '{old_name}' at "
                          f"offset={offset!r} ({moved} points already re-embedded in this "
                          f"collection before the failure; re-running --commit from scratch "
                          f"is safe — point IDs are preserved — just wasteful)")
                    raise
            moved += len(batch)
            if next_offset is None:
                break
            offset = next_offset
        dt = time.time() - t0
        verb = "would re-embed" if args.dry_run else "re-embedded"
        print(f"[migrate]   {verb} {moved} points in {dt:.1f}s")
        total_migrated += moved

    print()
    if args.dry_run:
        print(f"[migrate] DRY RUN — {total_migrated} points would be migrated. "
              f"Re-run with --commit to actually write.")
        return 0

    print("[migrate] verifying counts old vs. new...")
    for logical, old_name in COLLECTIONS.items():
        new_name = f"{old_name}{PHYSICAL_VERSION_SUFFIX}"
        try:
            old_count = client.get_collection(old_name).points_count
            new_count = client.get_collection(new_name).points_count
            flag = "OK" if old_count == new_count else "MISMATCH"
            print(f"[migrate]   {old_name}: old={old_count} new={new_count} [{flag}]")
        except Exception as e:
            print(f"[migrate]   {old_name}: ERROR {e}")

    print()
    print("[migrate] If all counts show OK, re-run with --cutover to swap the aliases "
          "(point-ID-set equality is re-checked there before anything is touched).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
