"""
Migrate old single-collection brain-kg into cognitive Model C collections.

Reads every point from the legacy `brain-kg` collection, groups by
payload.node_type, and writes each group into the appropriate cognitive
collection (episodic / semantic / procedural / state / artifacts). Uses
the same UUIDs so the migration is idempotent and repeatable.

Usage:
    # Show what would happen, no writes
    python scripts/migrate_kg_to_cognitive.py --dry-run

    # Actually write to the new collections (old stays put)
    python scripts/migrate_kg_to_cognitive.py --commit

    # After verifying: delete/archive old collection
    python scripts/migrate_kg_to_cognitive.py --commit --archive-old
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, List

# Make core/ importable whether we run as script or module
_HERE = os.path.dirname(os.path.abspath(__file__))
_BRAIN_ROOT = os.path.dirname(_HERE)  # .../the_brain
if _BRAIN_ROOT not in sys.path:
    sys.path.insert(0, _BRAIN_ROOT)

from core.qdrant_kg import (  # noqa: E402
    COLLECTIONS, NODE_TYPE_TO_COLLECTION, LEGACY_COLLECTION,
    QDRANT_URL, SEMANTIC_DIM, NEURAL_DIM,
)

SCROLL_BATCH = 256


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print plan, don't write (default)")
    ap.add_argument("--commit", action="store_true",
                    help="write to new collections")
    ap.add_argument("--archive-old", action="store_true",
                    help="after successful commit, rename old collection to "
                         "<name>-archive-<timestamp> (dest cannot exist)")
    ap.add_argument("--source", default=LEGACY_COLLECTION,
                    help=f"source collection (default: {LEGACY_COLLECTION})")
    ap.add_argument("--url", default=QDRANT_URL,
                    help=f"Qdrant URL (default: {QDRANT_URL})")
    args = ap.parse_args()

    if not (args.dry_run or args.commit):
        args.dry_run = True  # be safe

    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm

    print(f"[migrate] Qdrant URL: {args.url}")
    print(f"[migrate] Source:     {args.source}")
    print(f"[migrate] Target map:")
    for nt, logical in NODE_TYPE_TO_COLLECTION.items():
        print(f"           node_type={nt:12} -> {COLLECTIONS[logical]}")
    print()

    client = QdrantClient(url=args.url, timeout=60)

    # Check source exists
    try:
        src_info = client.get_collection(args.source)
        src_count = src_info.points_count
        print(f"[migrate] source '{args.source}' has {src_count} points")
    except Exception as e:
        print(f"[migrate] ERROR: source '{args.source}' not found: {e}")
        return 1

    # Make sure all target collections exist with correct schema
    if args.commit:
        existing = {c.name for c in client.get_collections().collections}
        vectors_config = {
            "semantic": qm.VectorParams(size=SEMANTIC_DIM, distance=qm.Distance.COSINE),
            "neural":   qm.VectorParams(size=NEURAL_DIM, distance=qm.Distance.COSINE,
                                        on_disk=True),
        }
        for logical, target in COLLECTIONS.items():
            if target in existing:
                print(f"[migrate] target '{target}' (logical={logical}) exists")
            else:
                print(f"[migrate] creating target '{target}' (logical={logical})")
                client.create_collection(
                    collection_name=target,
                    vectors_config=vectors_config,
                )

    # Scroll through the source
    offset = None
    moved: Dict[str, int] = {v: 0 for v in COLLECTIONS.values()}
    skipped_unknown = 0
    total_seen = 0
    batches: Dict[str, List[qm.PointStruct]] = {v: [] for v in COLLECTIONS.values()}

    def flush_batches() -> None:
        if not args.commit:
            return
        for target, points in batches.items():
            if not points:
                continue
            client.upsert(collection_name=target, points=points, wait=True)
            points.clear()

    t0 = time.time()
    while True:
        batch, next_offset = client.scroll(
            collection_name=args.source,
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not batch:
            break
        for rec in batch:
            total_seen += 1
            payload = rec.payload or {}
            nt = payload.get("node_type")
            logical = NODE_TYPE_TO_COLLECTION.get(nt)
            if logical is None:
                skipped_unknown += 1
                continue
            target = COLLECTIONS[logical]
            moved[target] += 1
            if args.commit:
                batches[target].append(qm.PointStruct(
                    id=rec.id,
                    vector=rec.vector,
                    payload=payload,
                ))
                # Flush when any bucket gets large
                if any(len(b) >= 128 for b in batches.values()):
                    flush_batches()
        if next_offset is None:
            break
        offset = next_offset

    if args.commit:
        flush_batches()

    dt = time.time() - t0
    print()
    print(f"[migrate] scanned {total_seen} points in {dt:.1f}s")
    print(f"[migrate] unknown node_type skipped: {skipped_unknown}")
    for target, n in moved.items():
        verb = "would write" if args.dry_run else "wrote"
        print(f"[migrate] {verb} {n:>5} -> {target}")

    if args.dry_run:
        print()
        print("[migrate] DRY RUN. Re-run with --commit to actually write.")
        return 0

    # Verify
    print()
    print("[migrate] verifying counts...")
    for target in COLLECTIONS.values():
        try:
            info = client.get_collection(target)
            print(f"[migrate]   {target}: {info.points_count} points")
        except Exception as e:
            print(f"[migrate]   {target}: ERROR {e}")

    if args.archive_old:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        archive_name = f"{args.source}-archive-{stamp}"
        print()
        print(f"[migrate] archiving '{args.source}' -> (alias) '{archive_name}'")
        # Qdrant has no rename; safest is to alias + then delete.
        try:
            client.update_collection_aliases(change_aliases_operations=[
                qm.CreateAliasOperation(create_alias=qm.CreateAlias(
                    collection_name=args.source,
                    alias_name=archive_name,
                )),
            ])
            print(f"[migrate] alias created. You can delete '{args.source}' "
                  f"manually after final verification.")
        except Exception as e:
            print(f"[migrate] alias creation failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
