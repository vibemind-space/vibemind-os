"""Bootstrap EventRoutingHead centroids from existing intent classifier logs.

Reads every JSONL line in `vibemind-os/voice/python/logs/intents/*.jsonl`,
extracts (user_input, event_type) pairs, and POSTs them to the Brain's
/api/cortex/classify/train endpoint as supervised training samples.

Usage:
    python vibemind-os/brain/the_brain/scripts/bootstrap_event_centroids.py
    python vibemind-os/brain/the_brain/scripts/bootstrap_event_centroids.py --brain http://localhost:5000

Notes:
- Prefers `original_intent` (the LLM's raw output) over `event_type` (after
  post-processing rules), because the post-processing rules occasionally
  overwrite a correct LLM answer with a wrong one. The LLM's raw output is
  the cleaner training signal.
- Skips entries with `event_type == conversation.unknown` (parser errors).
- Run this whenever new logs accumulate — it is idempotent (just shifts the
  centroids slightly more toward the same labels each time).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterator, Tuple

import urllib.request
import urllib.error


def find_log_files(repo_root: Path) -> list[Path]:
    """Locate every intents_*.jsonl under the standard log directory."""
    log_dir = repo_root / "vibemind-os" / "voice" / "python" / "logs" / "intents"
    if not log_dir.is_dir():
        return []
    return sorted(log_dir.glob("intents_*.jsonl"))


def iter_training_pairs(log_files: list[Path]) -> Iterator[Tuple[str, str]]:
    """Yield (user_input, event_type) pairs from the logs.

    Uses the LLM's raw output (original_intent) when present, else the
    post-processed event_type.
    """
    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    user_input = (entry.get("user_input") or "").strip()
                    if not user_input:
                        continue

                    classification = entry.get("classification") or {}
                    post = entry.get("post_processing") or {}

                    # Prefer the LLM's raw answer over post-processed
                    label = (
                        post.get("original_intent")
                        or classification.get("event_type")
                        or ""
                    )
                    label = label.strip()
                    if not label or label == "conversation.unknown":
                        continue

                    # Skip multi-step entries — Brain trains single-step only
                    if classification.get("is_multi_step"):
                        continue

                    yield user_input, label
        except OSError as e:
            print(f"  [WARN] Could not read {log_file}: {e}")


def post_train(brain_url: str, user_text: str, correct_event: str) -> bool:
    """POST one training sample. Returns True on success."""
    payload = json.dumps({
        "user_text": user_text,
        "correct_event_type": correct_event,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{brain_url.rstrip('/')}/api/cortex/classify/train",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        print(f"  [WARN] {e}")
        return False
    except Exception as e:
        print(f"  [WARN] {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--brain", default=os.environ.get("BRAIN_URL", "http://localhost:5000"),
        help="Brain server base URL (default: %(default)s)"
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[4]),
        help="Repo root containing vibemind-os/ (default: auto-detect)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't actually POST — just print what would be sent",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    log_files = find_log_files(repo_root)
    if not log_files:
        print(f"No log files found under {repo_root}/vibemind-os/voice/python/logs/intents/")
        return 1

    print(f"Found {len(log_files)} log file(s):")
    for f in log_files:
        print(f"  - {f.name}")

    pairs = list(iter_training_pairs(log_files))
    print(f"\nExtracted {len(pairs)} (user_input, event_type) pairs")

    if not pairs:
        print("Nothing to train on.")
        return 0

    # Show distribution
    counter = Counter(label for _, label in pairs)
    print(f"\nLabel distribution ({len(counter)} unique events):")
    for label, count in counter.most_common(20):
        print(f"  {count:4d}  {label}")
    if len(counter) > 20:
        print(f"  ... and {len(counter) - 20} more")

    if args.dry_run:
        print("\n[dry-run] no training calls made")
        return 0

    print(f"\nPosting to {args.brain} ...")
    sent = 0
    failed = 0
    t0 = time.time()
    for user_text, label in pairs:
        if post_train(args.brain, user_text, label):
            sent += 1
        else:
            failed += 1
        if (sent + failed) % 25 == 0:
            print(f"  ... {sent + failed}/{len(pairs)}")
    elapsed = time.time() - t0
    print(f"\nDone. Sent {sent}, failed {failed} in {elapsed:.1f}s")

    if sent > 0:
        try:
            with urllib.request.urlopen(
                f"{args.brain.rstrip('/')}/api/cortex/classify/stats", timeout=5
            ) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
                print(f"\nBrain stats after bootstrap:")
                print(json.dumps(stats, indent=2))
        except Exception as e:
            print(f"  [WARN] Could not fetch stats: {e}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
