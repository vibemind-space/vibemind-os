"""Periodic retrainer — keeps the Brain EventRoutingHead in sync with new intent logs.

Runs as an asyncio background task inside brain_server's lifespan. On every
tick (default: every 1h), scans `vibemind-os/voice/python/logs/intents/*.jsonl`
for entries newer than the last processed timestamp, filters them through the
same clean-label rules as the bootstrap script, and trains the EventRoutingHead
via supervised updates. The processed cursor is persisted so we never train on
the same entry twice.

This closes the feedback loop end-to-end:
  user speaks → LLM classifies → intent_logger writes JSONL
  → (within retrain interval) log_retrainer picks it up
  → EventRoutingHead.train_supervised → centroid shifts
  → next time the user says the same thing, Brain fires confidently
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Tuple

import torch

logger = logging.getLogger('brain.log_retrainer')


def _repo_root() -> Path:
    """Locate the repo root by walking up from this file."""
    here = Path(__file__).resolve()
    # this file is at: vibemind-os/brain/the_brain/core/log_retrainer.py
    # -> repo root is 4 levels up
    return here.parents[4]


def _log_dir() -> Path:
    return _repo_root() / "vibemind-os" / "voice" / "python" / "logs" / "intents"


def load_cursor(cursor_path: Path) -> Optional[str]:
    """Return the ISO timestamp of the latest entry we've already trained on."""
    try:
        if cursor_path.exists():
            data = json.loads(cursor_path.read_text(encoding="utf-8"))
            return data.get("last_ts")
    except Exception as e:
        logger.debug(f"cursor load failed: {e}")
    return None


def save_cursor(cursor_path: Path, last_ts: str) -> None:
    try:
        cursor_path.parent.mkdir(parents=True, exist_ok=True)
        cursor_path.write_text(
            json.dumps({"last_ts": last_ts, "updated_at": datetime.utcnow().isoformat() + "Z"}),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"cursor save failed: {e}")


def _iter_entries_since(
    log_files: list[Path],
    since_ts: Optional[str],
) -> Iterator[Tuple[str, str, str]]:
    """Yield (user_input, event_type, timestamp) for every log entry newer than since_ts.

    Filters identical to bootstrap_event_centroids.py:
      - skip empty user_input
      - prefer original_intent (raw LLM output) over event_type (post-processed)
      - skip conversation.unknown labels
      - skip multi_step entries (Brain trains single-step only)
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

                    ts = entry.get("timestamp", "")
                    if since_ts and ts <= since_ts:
                        continue

                    user_input = (entry.get("user_input") or "").strip()
                    if not user_input:
                        continue

                    classification = entry.get("classification") or {}
                    if classification.get("is_multi_step"):
                        continue

                    post = entry.get("post_processing") or {}
                    label = (
                        post.get("original_intent")
                        or classification.get("event_type")
                        or ""
                    ).strip()
                    if not label or label == "conversation.unknown":
                        continue

                    yield user_input, label, ts
        except OSError as e:
            logger.warning(f"log retrainer could not read {log_file}: {e}")


def retrain_once(
    event_head,
    sbert,
    cursor_path: Path,
    lr: float = 0.03,
) -> int:
    """Single retraining pass — scan logs, train, advance cursor.

    Returns the number of new entries trained on.
    """
    if event_head is None or sbert is None:
        return 0
    log_dir = _log_dir()
    if not log_dir.is_dir():
        logger.debug(f"log retrainer: no log dir at {log_dir}")
        return 0

    log_files = sorted(log_dir.glob("intents_*.jsonl"))
    if not log_files:
        return 0

    since_ts = load_cursor(cursor_path)
    new_entries = list(_iter_entries_since(log_files, since_ts))
    if not new_entries:
        return 0

    trained = 0
    latest_ts = since_ts or ""
    for user_text, label, ts in new_entries:
        try:
            vec = sbert.encode([user_text[:200]], convert_to_numpy=True)
            emb = torch.tensor(vec, dtype=torch.float32)
            if event_head.train_supervised(emb, label, lr=lr):
                trained += 1
            if ts > latest_ts:
                latest_ts = ts
        except Exception as e:
            logger.debug(f"log retrainer train failed on {user_text[:40]}: {e}")

    if latest_ts:
        save_cursor(cursor_path, latest_ts)

    logger.info(
        f"[LogRetrainer] trained on {trained} new entries "
        f"(cursor now {latest_ts[:19]})"
    )
    return trained


async def periodic_retrainer_loop(
    app_state,
    interval_seconds: int = 3600,
) -> None:
    """Long-running asyncio task. Runs a retrain pass every `interval_seconds`.

    Started by brain_server's lifespan on startup, cancelled on shutdown.
    """
    # Initial startup delay so we don't hammer the brain during its own init
    await asyncio.sleep(60)

    cursor_path = _repo_root() / "vibemind-os" / "brain" / "the_brain" / "data" / "brain_checkpoints" / "retrain_cursor.json"

    while True:
        try:
            event_head = getattr(app_state, 'event_routing_head', None)
            sbert = getattr(app_state, 'sbert_encoder', None)
            ckpt_path = getattr(app_state, 'event_routing_head_ckpt', None)

            if event_head is None or sbert is None:
                logger.debug("log retrainer: head or sbert not ready yet, waiting")
            else:
                start = time.time()
                trained = retrain_once(event_head, sbert, cursor_path)
                elapsed = time.time() - start
                if trained > 0:
                    logger.info(
                        f"[LogRetrainer] tick complete: {trained} entries in {elapsed:.1f}s"
                    )
                    # Save centroids after a meaningful retrain pass
                    if ckpt_path:
                        try:
                            event_head.save(ckpt_path)
                        except Exception as e:
                            logger.warning(f"log retrainer checkpoint save failed: {e}")
        except asyncio.CancelledError:
            logger.info("log retrainer cancelled")
            raise
        except Exception as e:
            logger.warning(f"log retrainer tick failed: {e}")

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
