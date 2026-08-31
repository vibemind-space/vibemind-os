"""bubble_classifier_runner — autonomous bubble classification (Schicht 8.0, Phase 2).

Polls unclassified top-level bubbles and lets an LLM assign:

  category   -- marketing | crowdfunding | code_project | research | general
  color      -- fixed mapping from category (UI hint)
  channels[] -- suggested outbound channels (marketing/crowdfunding only)
  confidence -- 0..1; below threshold the bubble stays category=NULL (white)

V1 design decision (plan: docs/2026-07-02-bubble-auto-dispatch-plan.md):
LLM-only (gpt-4o-mini via OpenAI direct) — NO Mirofish persona-sim, NO
embedding-kNN yet. Those are quality upgrades once V1 misclassifies too much.

Write semantics:
  confidence >= threshold -> category/color/channels set, auto_classified=true
  confidence <  threshold -> category stays NULL, auto_classified=false
  classified_at is ALWAYS set (prevents endless re-polling; to force a
  re-classification set classified_at back to NULL).

The classifier reason is stored in metadata.classifier for explainability.

Usage:
    python -m spaces.marketing.workers.bubble_classifier_runner            # loop
    python -m spaces.marketing.workers.bubble_classifier_runner --once
    python -m spaces.marketing.workers.bubble_classifier_runner --once --dry-run
    python -m spaces.marketing.workers.bubble_classifier_runner --ids a,b --once
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
logger = logging.getLogger("marketing.bubble_classifier")

# ─── config ──────────────────────────────────────────────────────────────────

_POLL_INTERVAL_S = float(os.environ.get("BUBBLE_CLASSIFIER_POLL_S", "30"))
_THRESHOLD = float(os.environ.get("BUBBLE_CLASSIFIER_THRESHOLD", "0.7"))
_MODEL = os.environ.get("BUBBLE_CLASSIFIER_MODEL", "gpt-4o-mini")
_BATCH = int(os.environ.get("BUBBLE_CLASSIFIER_BATCH", "5"))
# Only bubbles created at/after this date are auto-picked (historical bubbles
# need an explicit --ids run — avoids burning tokens on thousands of old rows).
_SINCE = os.environ.get("BUBBLE_CLASSIFIER_SINCE", "2026-07-02")

_CATEGORIES = ("marketing", "crowdfunding", "code_project", "research", "general")
_COLOR = {
    "marketing":    "#dc2626",
    "crowdfunding": "#ea580c",
    "code_project": "#2563eb",
    "research":     "#9333ea",
    "general":      "#ffffff",
}
# Channels the classifier may propose. A channel only belongs here once it
# can actually be delivered — otherwise the dispatcher fans out proposals
# that no n8n workflow will ever post.
#   'x' removed 2026-07-14: X's API charges for posting (~$100/mo Basic tier)
#   and we have no app. Re-add together with a working n8n credential.
_ALLOWED_CHANNELS = {
    "linkedin", "email", "reddit", "discord", "mastodon", "telegram",
    "instagram", "linkedin-dm",
}

_SYSTEM_PROMPT = """\
You classify "bubbles" (idea notes) of the VibeMind agentic OS into exactly one category.

Categories:
- marketing:    outbound announcements, social posts, launch news, growth content
- crowdfunding: asking people to financially back/support the project (payment links, backer outreach)
- code_project: software to build — features, apps, bugs, technical implementation work
- research:     questions to investigate, papers, knowledge gathering, analysis
- general:      personal notes, todos, anything that fits none of the above

Also suggest outbound channels — ONLY for marketing (broadcast: linkedin, email,
reddit, discord, mastodon, telegram, instagram) or crowdfunding (direct: email,
linkedin-dm). For code_project/research/general return [].

confidence: 0.0-1.0 — how certain you are about the category. Be honest: mixed or
vague texts deserve < 0.7.

The text may be German or English.

Respond with JSON only:
{"category": "...", "channels": ["..."], "confidence": 0.0, "reason": "one sentence"}"""


# ─── LLM call ────────────────────────────────────────────────────────────────

def _load_env_fallback() -> None:
    """Pull OPENAI_API_KEY from repo .env if not already in the environment."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("OPENAI_API_KEY=") :
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            return


def classify(title: str, description: str) -> dict:
    """One LLM call -> {category, channels, confidence, reason}. Raises on error."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set (env or repo .env)")

    text = f"Title: {title or '(untitled)'}\n\n{description or '(no description)'}"
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": _MODEL,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
        },
        timeout=45,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI {resp.status_code}: {resp.text[:200]}")
    raw = resp.json()["choices"][0]["message"]["content"]
    out = json.loads(raw)

    category = str(out.get("category", "")).strip()
    if category not in _CATEGORIES:
        raise RuntimeError(f"LLM returned unknown category {category!r}")
    channels = [c for c in (out.get("channels") or []) if c in _ALLOWED_CHANNELS]
    if category not in ("marketing", "crowdfunding"):
        channels = []
    confidence = max(0.0, min(1.0, float(out.get("confidence", 0.0))))
    reason = str(out.get("reason", ""))[:300]
    return {"category": category, "channels": channels,
            "confidence": confidence, "reason": reason}


# ─── DB ──────────────────────────────────────────────────────────────────────

def _claim_unclassified(ids: list[str] | None) -> list[dict]:
    if ids:
        id_list = ", ".join(_db._sql_literal(i) for i in ids)
        where = f"id IN ({id_list})"
    else:
        where = (
            "parent_id IS NULL "
            "AND classified_at IS NULL "
            "AND status IS DISTINCT FROM 'archived' "
            f"AND created_at >= {_db._sql_literal(_SINCE)}::timestamptz"
        )
    return _db.query_via_docker(
        f"SELECT id, title, description FROM public.ideas "
        f"WHERE {where} LIMIT {_BATCH}"
    )


def _write_classification(bubble_id: str, result: dict) -> None:
    conf = result["confidence"]
    accepted = conf >= _THRESHOLD
    category_sql = _db._sql_literal(result["category"]) if accepted else "NULL"
    color = _COLOR[result["category"]] if accepted else _COLOR["general"]
    channels_json = json.dumps(result["channels"] if accepted else [])
    meta = json.dumps({
        "model": _MODEL,
        "reason": result["reason"],
        "raw_category": result["category"],
        "accepted": accepted,
    })
    _db.execute_via_docker(
        f"UPDATE public.ideas SET "
        f"  category = {category_sql}, "
        f"  color = {_db._sql_literal(color)}, "
        f"  channels = {_db._sql_literal(channels_json)}::jsonb, "
        f"  auto_classified = {str(accepted).lower()}, "
        f"  classification_confidence = {conf}, "
        f"  classified_at = now(), "
        f"  metadata = COALESCE(metadata, '{{}}'::jsonb) || "
        f"             jsonb_build_object('classifier', {_db._sql_literal(meta)}::jsonb) "
        f"WHERE id = {_db._sql_literal(bubble_id)}"
    )


# ─── main loop ───────────────────────────────────────────────────────────────

def run_pass(ids: list[str] | None, dry_run: bool) -> int:
    bubbles = _claim_unclassified(ids)
    if not bubbles:
        return 0
    done = 0
    for b in bubbles:
        bid = b["id"]
        try:
            result = classify(b.get("title", ""), b.get("description", ""))
        except Exception as exc:
            logger.error("[%s] classify failed: %s", bid[:8], exc)
            continue
        accepted = result["confidence"] >= _THRESHOLD
        logger.info(
            "[%s] %s conf=%.2f channels=%s %s-- %s",
            bid[:8], result["category"], result["confidence"],
            ",".join(result["channels"]) or "-",
            "" if accepted else "(below threshold -> stays white) ",
            result["reason"],
        )
        if not dry_run:
            _write_classification(bid, result)
            done += 1
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="Bubble auto-classifier (Schicht 8.0)")
    ap.add_argument("--once", action="store_true", help="single pass, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify + log only, write nothing")
    ap.add_argument("--ids", default="",
                    help="comma-separated bubble ids (bypasses SINCE filter)")
    args = ap.parse_args()

    _load_env_fallback()
    ids = [i.strip() for i in args.ids.split(",") if i.strip()] or None

    if args.once:
        n = run_pass(ids, args.dry_run)
        logger.info("single pass done, %d bubble(s) written", n)
        return 0

    logger.info("loop mode: poll=%ss threshold=%s model=%s since=%s",
                _POLL_INTERVAL_S, _THRESHOLD, _MODEL, _SINCE)
    while True:
        try:
            run_pass(ids, args.dry_run)
        except Exception as exc:
            logger.error("pass failed: %s", exc)
        time.sleep(_POLL_INTERVAL_S)


if __name__ == "__main__":
    sys.exit(main())
