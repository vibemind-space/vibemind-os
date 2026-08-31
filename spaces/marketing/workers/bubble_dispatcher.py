"""bubble_dispatcher — per-channel fan-out for classified bubbles (Schicht 8.0, Phase 3).

Watches marketing-classified bubbles and turns each into N approval-gated
broadcast_proposals — one per channel in bubble.channels[]:

  Stage 1  FAN-OUT (direct SQL, idempotent):
      eligible bubble -> INSERT one bp per channel (status=draft,
      bubble_id set -> migration 037 aggregates bubble.status).
      V1 body: bubble.description verbatim (Template-Skill kommt später).

  Stage 2  APPROVAL (via marketing-API, retry-safe):
      own draft-bps without approval_requested_at ->
      POST /api/curator/broadcast_proposals/{id}/request_approval
      (channel=openfang). The API owns HMAC-minting + OpenFang-card
      registration — we do NOT reimplement that security logic here.
      If the API is down we warn and retry next cycle.

Eligibility (V1, conservative):
  auto_classified AND category='marketing' AND channels != []
  AND status='draft' AND no bp exists yet for this bubble.
  crowdfunding bubbles are Phase 6 (crowdfunding_batches), code_project/
  research/general have no outbound channels by definition.

Channels not present in marketing.channel_config are skipped with a warning
(FK would reject them); the bubble still counts as fanned-out if >=1 bp
was created.

Usage:
    python -m spaces.marketing.workers.bubble_dispatcher            # loop
    python -m spaces.marketing.workers.bubble_dispatcher --once
    python -m spaces.marketing.workers.bubble_dispatcher --once --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.sync import _db  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("marketing.bubble_dispatcher")

_POLL_INTERVAL_S = float(os.environ.get("BUBBLE_DISPATCHER_POLL_S", "30"))
_BATCH = int(os.environ.get("BUBBLE_DISPATCHER_BATCH", "5"))
_API_URL = os.environ.get("MARKETING_HTTP_URL", "http://127.0.0.1:5510").rstrip("/")
_CREATED_BY = "bubble-dispatcher"


_ENV_KEYS = (
    "MARKETING_PROPOSAL_API_KEY",   # approval requests against the marketing-API
    "DISCORD_CHANNEL_ID",           # target channel for discord broadcasts
    "TELEGRAM_CHAT_ID",             # target chat for telegram broadcasts
)


def _load_env_fallback() -> None:
    """Pull the keys we need from the repo .env (never override the process env)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    missing = [k for k in _ENV_KEYS if not os.environ.get(k)]
    if not missing:
        return
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        for k in missing:
            if line.startswith(k + "="):
                os.environ[k] = line.split("=", 1)[1].strip().strip('"').strip("'")


# ─── stage 1: fan-out ────────────────────────────────────────────────────────

def _eligible_bubbles() -> list[dict]:
    # status: voice/MCP-created bubbles default to 'raw' (ideas table
    # default), UI drafts use 'draft', legacy rows 'idea' — all three are
    # pre-pipeline states and eligible. Anything already in the pipeline
    # (predicting/pending_approval/sent/...) or archived is not.
    return _db.query_via_docker(
        "SELECT i.id, i.title, i.description, i.channels::text AS channels "
        "FROM public.ideas i "
        "WHERE i.auto_classified "
        "  AND i.category = 'marketing' "
        "  AND jsonb_array_length(i.channels) > 0 "
        "  AND i.status IN ('raw', 'idea', 'draft') "
        "  AND NOT EXISTS (SELECT 1 FROM marketing.broadcast_proposals bp "
        "                  WHERE bp.bubble_id = i.id) "
        f"LIMIT {_BATCH}"
    )


def _known_channels() -> set[str]:
    rows = _db.query_via_docker("SELECT channel FROM marketing.channel_config")
    return {r["channel"] for r in rows}


def _channel_params(channel: str) -> dict:
    """Per-channel routing details the n8n workflow needs to deliver.

    They ride along on the proposal (draft_channel_params) and are copied
    into the broadcast_approved bus event, so the workflow never has to
    query back. Missing config is NOT fatal here — the workflow surfaces it
    as a failed execution rather than us blocking the approval card.
    """
    if channel == "discord":
        cid = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
        if not cid:
            logger.warning("DISCORD_CHANNEL_ID not set — discord proposal "
                           "will have no target channel")
            return {}
        return {"discord_channel_id": cid}
    if channel == "telegram":
        chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        return {"chat_id": chat} if chat else {}
    return {}


def _fan_out(bubble: dict, known: set[str], dry_run: bool) -> int:
    bid = bubble["id"]
    channels = json.loads(bubble.get("channels") or "[]")
    body = (bubble.get("description") or "").strip() or (bubble.get("title") or "")
    if not body:
        logger.warning("[%s] empty description+title, skipping", bid[:8])
        return 0
    created = 0
    for ch in channels:
        if ch not in known:
            logger.warning("[%s] channel %r not in channel_config, skipped",
                           bid[:8], ch)
            continue
        params = _channel_params(ch)
        if dry_run:
            logger.info("[%s] DRY-RUN would create bp channel=%s (%d chars) "
                        "params=%s", bid[:8], ch, len(body), params or "-")
            created += 1
            continue
        _db.execute_via_docker(
            f"INSERT INTO marketing.broadcast_proposals "
            f"(channel, status, draft_body_text, draft_channel_params, "
            f" created_by, bubble_id) "
            f"VALUES ({_db._sql_literal(ch)}, 'draft', "
            f"        {_db._sql_literal(body)}, "
            f"        {_db._sql_literal(json.dumps(params))}::jsonb, "
            f"        {_db._sql_literal(_CREATED_BY)}, "
            f"        {_db._sql_literal(bid)})"
        )
        logger.info("[%s] bp created channel=%s params=%s",
                    bid[:8], ch, params or "-")
        created += 1
    return created


# ─── stage 2: approval requests ──────────────────────────────────────────────

def _pending_approval_requests() -> list[dict]:
    return _db.query_via_docker(
        f"SELECT id::text AS id, channel, bubble_id "
        f"FROM marketing.broadcast_proposals "
        f"WHERE created_by = {_db._sql_literal(_CREATED_BY)} "
        f"  AND status = 'draft' "
        f"  AND approval_requested_at IS NULL "
        f"LIMIT 20"
    )


def _request_approval(bp: dict, dry_run: bool) -> bool:
    api_key = os.environ.get("MARKETING_PROPOSAL_API_KEY", "")
    if not api_key:
        logger.error("MARKETING_PROPOSAL_API_KEY not set — cannot request approvals")
        return False
    if dry_run:
        logger.info("[bp %s] DRY-RUN would request approval (channel=%s)",
                    bp["id"][:8], bp["channel"])
        return True
    try:
        resp = requests.post(
            f"{_API_URL}/api/curator/broadcast_proposals/{bp['id']}/request_approval",
            json={"api_key": api_key, "channel": "openfang"},
            timeout=30,
        )
    except requests.ConnectionError:
        logger.warning("[bp %s] marketing-API unreachable at %s — retry next cycle",
                       bp["id"][:8], _API_URL)
        return False
    if resp.status_code != 200:
        logger.error("[bp %s] request_approval failed: %s %s",
                     bp["id"][:8], resp.status_code, resp.text[:200])
        return False
    logger.info("[bp %s] approval requested (channel=%s, bubble=%s)",
                bp["id"][:8], bp["channel"], (bp.get("bubble_id") or "?")[:8])
    return True


# ─── main ────────────────────────────────────────────────────────────────────

def run_pass(dry_run: bool) -> tuple[int, int]:
    known = _known_channels()
    fanned = 0
    for bubble in _eligible_bubbles():
        fanned += _fan_out(bubble, known, dry_run)
    approvals = 0
    for bp in _pending_approval_requests():
        if _request_approval(bp, dry_run):
            approvals += 1
    return fanned, approvals


def main() -> int:
    ap = argparse.ArgumentParser(description="Bubble fan-out dispatcher (Schicht 8.0)")
    ap.add_argument("--once", action="store_true", help="single pass, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="log what would happen, write/send nothing")
    args = ap.parse_args()

    _load_env_fallback()

    if args.once:
        fanned, approvals = run_pass(args.dry_run)
        logger.info("single pass done: %d bp(s) created, %d approval(s) requested",
                    fanned, approvals)
        return 0

    logger.info("loop mode: poll=%ss api=%s", _POLL_INTERVAL_S, _API_URL)
    while True:
        try:
            run_pass(args.dry_run)
        except Exception as exc:
            logger.error("pass failed: %s", exc)
        time.sleep(_POLL_INTERVAL_S)


if __name__ == "__main__":
    sys.exit(main())
