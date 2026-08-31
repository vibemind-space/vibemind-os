"""One-shot backup of pathx-origin data living in marketing.accounts + marketing.emails.

Reads the rows whose source/strategy_id marks them as pathfinder-imports
and writes them to backups/marketing-snapshots/<timestamp>/ as CSVs.

Reason: pathfinder container is gone, so marketing.* is the only copy.
This script makes a second copy outside the DB that survives an accidental
docker volume wipe.

Run:
    python -m spaces.marketing.scripts.snapshot_pathx_data
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
from pathlib import Path

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.sync import _db  # noqa: E402


SNAPSHOT_ROOT = REPO_ROOT / "backups" / "marketing-snapshots"


# Tables to snapshot in full (marketing-ops-space is small; full dump is fine).
TABLES = [
    "accounts",
    "emails",
    "strategies",
    "runs",
    "tags",
    "email_tags",
    "audiences",
    "audience_members",
    "templates",
    "campaigns",
    "campaign_sends",
    "inbound_messages",
    "audit_log",
]


def snapshot_table(table: str, out_dir: Path) -> int:
    rows = _db.query_via_docker(f"SELECT row_to_json(t) AS row FROM marketing.{table} t")
    if not rows:
        # Empty table — still write an empty CSV with just the header.
        cols = _db.query_via_docker(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema='marketing' AND table_name='{table}' "
            f"ORDER BY ordinal_position"
        )
        header = [c["column_name"] for c in cols]
        out_path = out_dir / f"{table}.csv"
        with out_path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(header)
        return 0

    # query_via_docker returns the wrapped column 'row' as a dict
    sample = rows[0]["row"]
    header = list(sample.keys())
    out_path = out_dir / f"{table}.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            data = r["row"]
            # Flatten dicts/lists to JSON strings so CSV stays readable
            flat = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                    for k, v in data.items()}
            w.writerow(flat)
    return len(rows)


def main() -> int:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = SNAPSHOT_ROOT / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[snapshot] writing to {out_dir}", flush=True)

    summary = {}
    for t in TABLES:
        try:
            n = snapshot_table(t, out_dir)
            summary[t] = n
            print(f"  {t:<22} {n:>7} rows", flush=True)
        except Exception as e:
            summary[t] = f"ERROR: {e}"
            print(f"  {t:<22} ERROR: {e}", file=sys.stderr, flush=True)

    manifest = {
        "snapshot_at": ts,
        "tables": summary,
        "source": "marketing.* (supabase-db) -- pathx already retired",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"\n[snapshot] done -- manifest at {out_dir / 'manifest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
