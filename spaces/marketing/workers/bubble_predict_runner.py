"""bubble_predict_runner — drives Mirofish persona-sim for post_draft bubbles.

Polling-based worker that:

  1. Finds public.ideas WHERE kind='post_draft' AND status='predicting'
     AND mirofish_report_id IS NULL.
  2. For each: kick_off Mirofish pipeline, poll until done OR failed.
  3. On done: write mirofish_report_id + mirofish_score + flip status
     to 'ready_to_post'.
  4. On fail: flip status to 'eval_failed' + record the error.

State for in-progress pipelines is kept in-memory (this worker is the only
consumer of a bubble until done). If the worker dies mid-run, the bubble
will be re-picked next start (status='predicting' but no progress) — we
rate-limit re-kicks via mirofish_last_run_at.

Designed to run as a long-lived sidecar:
    python -m spaces.marketing.workers.bubble_predict_runner
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path


PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.sync import _db  # noqa: E402
from spaces.marketing.mirofish.predict_post_reception import (  # noqa: E402
    kick_off, poll_status, read_report,
)


logger = logging.getLogger("marketing.bubble_predict_runner")


_POLL_INTERVAL_S = float(os.environ.get("BUBBLE_PREDICT_POLL_S", "5"))
_RE_KICK_GRACE_S = 30  # don't re-kick a bubble whose last_run was less than this ago

# In-memory state per bubble. The worker is the only driver, so this is OK.
# If the worker dies, the bubble re-enters from scratch on next pick-up.
_STATE: dict[str, dict] = {}


def _claim_predicting() -> list[dict]:
    return _db.query_via_docker(
        "SELECT id, title, description, target_channel, "
        "       EXTRACT(EPOCH FROM (now() - COALESCE(mirofish_last_run_at, now()))) AS age_s "
        "FROM public.ideas "
        "WHERE kind = 'post_draft' "
        "  AND status = 'predicting' "
        "  AND mirofish_report_id IS NULL "
        "LIMIT 10"
    )


def _mark_done(bubble_id: str, report_id: str, score: int):
    _db.execute_via_docker(
        f"UPDATE public.ideas "
        f"SET mirofish_report_id = {_db._sql_literal(report_id)}, "
        f"    mirofish_score = {score}, "
        f"    status = 'ready_to_post' "
        f"WHERE id = {_db._sql_literal(bubble_id)}"
    )


def _mark_failed(bubble_id: str, err: str):
    err_short = (err or "unknown error")[:500]
    _db.execute_via_docker(
        f"UPDATE public.ideas "
        f"SET status = 'eval_failed', "
        f"    metadata = COALESCE(metadata, '{{}}'::jsonb) || "
        f"               jsonb_build_object('predict_error', {_db._sql_literal(err_short)}) "
        f"WHERE id = {_db._sql_literal(bubble_id)}"
    )


def _step(bubble_id: str, bubble: dict):
    state = _STATE.get(bubble_id)
    if state is None:
        # Honor grace period to avoid hammering Mirofish if the worker was
        # restarted between kick and complete.
        age_s = float(bubble.get("age_s") or 0)
        if age_s < _RE_KICK_GRACE_S and age_s > 0:
            logger.info(
                "[%s] holding off (last_run age=%.1fs < grace=%ds)",
                bubble_id, age_s, _RE_KICK_GRACE_S,
            )
            return
        try:
            state = kick_off(
                bubble_id=bubble_id,
                content=bubble["description"],
                channel=bubble.get("target_channel") or "twitter",
                bubble_title=bubble.get("title"),
            )
            _STATE[bubble_id] = state
            logger.info("[%s] kicked off, phase=%s", bubble_id, state["phase"])
        except Exception as e:
            logger.exception("[%s] kick_off failed", bubble_id)
            _mark_failed(bubble_id, f"kick_off: {e}")
        return

    try:
        state = poll_status(state)
        _STATE[bubble_id] = state
    except Exception as e:
        logger.exception("[%s] poll_status failed", bubble_id)
        _mark_failed(bubble_id, f"poll_status: {e}")
        _STATE.pop(bubble_id, None)
        return

    if state.get("phase") == "done":
        try:
            rep = read_report(state["report_id"])
            _mark_done(bubble_id, state["report_id"], int(rep.get("score") or 50))
            logger.info("[%s] DONE report_id=%s score=%s",
                        bubble_id, state["report_id"], rep.get("score"))
        except Exception as e:
            logger.exception("[%s] read_report failed", bubble_id)
            _mark_failed(bubble_id, f"read_report: {e}")
        _STATE.pop(bubble_id, None)
    elif state.get("phase") == "failed":
        _mark_failed(bubble_id, state.get("error") or "unknown")
        _STATE.pop(bubble_id, None)


def run_cycle() -> dict:
    """Single tick. Returns brief stats."""
    bubbles = _claim_predicting()
    stats = {"in_progress": len(_STATE), "candidates": len(bubbles), "errors": 0}
    for b in bubbles:
        bid = b["id"]
        try:
            _step(bid, b)
        except Exception as e:
            stats["errors"] += 1
            logger.exception("[%s] step error: %s", bid, e)
    return stats


def run_forever():
    logger.info("bubble_predict_runner starting "
                "(poll=%.1fs)", _POLL_INTERVAL_S)
    while True:
        try:
            stats = run_cycle()
            if stats["candidates"] or stats["errors"]:
                logger.info("cycle: %s", stats)
        except KeyboardInterrupt:
            return
        except Exception as e:
            logger.exception("cycle failed: %s", e)
        time.sleep(_POLL_INTERVAL_S)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_forever()
