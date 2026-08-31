"""batch_sender — crowdfunding payment-link batch worker (Schicht 8.1, Phase 6).

For an APPROVED crowdfunding batch: per recipient create a unique payment
link via the payment-infra SDK (VibeMind-OS/payment-infra), render the
outreach message through the backer-outreach-template skill and — in
dry_run — write previews to outbox/ instead of sending anything.

Modes (mirrors send_worker's safety ladder):
  dry_run  -- creates REAL sandbox payment links + ledger rows, renders
              messages to logs/marketing/crowdfunding_outbox/<batch>/,
              sends NOTHING. Prints the confirm token for live mode.
  live     -- NOT IMPLEMENTED in Phase 6 (raises). The outbound channel
              transports (email/linkedin-dm/x-dm) land in Phase 7+ after
              per-channel consent + gate review. Mirrors the Phase-1
              send_worker contract: the mode exists, the gate chain runs,
              the transport refuses.

Gates (V1 — G9-G12 sharpen in Phase 7):
  G1 kill-switch    MARKETING_CROWDFUNDING_SEND_ENABLED (live only)
  G2 freeze file    logs/marketing/CROWDFUNDING_FREEZE
  G3 batch resolve  status must be 'approved'
  G4 provider up    payment-infra SDK import + OAuth round-trip
  G5 sandbox lock   PAYPAL_ENV must be sandbox unless --allow-live
  G6 recipients     snapshot from marketing.audience_members
  G7 idempotency    UNIQUE(batch_id, recipient_id) — second run skips
  G8 confirm token  sha256(batch|audience|amount) for live mode
  G12 paid_at       NEVER written here (single writer: paypal_webhook_handler)

Usage:
    python -m spaces.marketing.workers.batch_sender --batch-id <uuid> --mode dry_run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

# payment-infra lives in the sibling VibeMind-OS repo (standalone layer)
PAYMENT_INFRA = REPO_ROOT.parent / "VibeMind-OS" / "payment-infra"
if str(PAYMENT_INFRA) not in sys.path:
    sys.path.insert(0, str(PAYMENT_INFRA))

from spaces.marketing.sync import _db  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("marketing.batch_sender")

_FREEZE_FILE = REPO_ROOT / "logs" / "marketing" / "CROWDFUNDING_FREEZE"
_OUTBOX_ROOT = REPO_ROOT / "logs" / "marketing" / "crowdfunding_outbox"
_TEMPLATE_DIR = (REPO_ROOT / "vibemind-os" / "skills"
                 / "backer-outreach-template" / "templates")
_PUBLIC_BASE = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5060")


class GateAbort(SystemExit):
    def __init__(self, gate: str, msg: str):
        logger.error("GATE %s ABORT: %s", gate, msg)
        super().__init__(2)


# ─── gates ───────────────────────────────────────────────────────────────────

def gate_g2_freeze() -> None:
    if _FREEZE_FILE.exists():
        raise GateAbort("G2", f"freeze file present: {_FREEZE_FILE}")


def gate_g3_batch(batch_id: str) -> dict:
    row = _db.query_one(
        f"SELECT id::text AS id, bubble_id, channel, status, amount, currency, "
        f"       recipients_audience_id::text AS audience_id, message_template "
        f"FROM marketing.crowdfunding_batches "
        f"WHERE id = {_db._sql_literal(batch_id)}::uuid"
    )
    if not row:
        raise GateAbort("G3", f"batch {batch_id} not found")
    if row["status"] != "approved":
        raise GateAbort("G3", f"batch status={row['status']}, need 'approved'")
    return row


def gate_g4_provider():
    try:
        from providers import get_provider  # payment-infra
    except ImportError as exc:
        raise GateAbort("G4", f"payment-infra SDK not importable: {exc}")
    provider = get_provider("paypal")
    try:
        provider._access_token()  # OAuth round-trip = provider reachable
    except Exception as exc:
        raise GateAbort("G4", f"provider OAuth failed: {exc}")
    return provider


def gate_g5_sandbox(provider, allow_live: bool) -> None:
    if provider.env != "sandbox" and not allow_live:
        raise GateAbort("G5", f"PAYPAL_ENV={provider.env} but --allow-live "
                              f"not given")


def gate_g6_recipients(batch: dict) -> list[dict]:
    if not batch.get("audience_id"):
        raise GateAbort("G6", "batch has no recipients_audience_id")
    rows = _db.query_via_docker(
        f"SELECT email AS recipient_id, email "
        f"FROM marketing.audience_members "
        f"WHERE audience_id = {_db._sql_literal(batch['audience_id'])}::uuid "
        f"ORDER BY email"
    )
    if not rows:
        raise GateAbort("G6", "audience snapshot is empty")
    return rows


def compute_confirm_token(batch: dict, recipients: list[dict]) -> str:
    material = (f"crowdfunding-v1|{batch['id']}|{batch['audience_id']}|"
                f"{batch['amount']}|{batch['currency']}|{len(recipients)}")
    return hashlib.sha256(material.encode()).hexdigest()[:16]


# ─── template skill (V1: markdown templates + {{placeholder}} substitution) ──

def render_message(channel: str, recipient: dict, approve_url: str,
                   batch: dict) -> str:
    tpl_file = _TEMPLATE_DIR / f"{channel}.md"
    if not tpl_file.exists():
        tpl_file = _TEMPLATE_DIR / "email.md"   # fallback template
    if tpl_file.exists():
        tpl = tpl_file.read_text(encoding="utf-8")
    else:
        tpl = ("Hi {{recipient_name}},\n\n{{message}}\n\n"
               "Support us with {{amount}} {{currency}}: {{approve_url}}\n")
    subs = {
        "recipient_name": recipient.get("recipient_id", "there").split("@")[0],
        "recipient_id": recipient.get("recipient_id", ""),
        "approve_url": approve_url,
        "amount": batch["amount"],
        "currency": batch["currency"],
        "message": batch.get("message_template") or "",
    }
    for k, v in subs.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


# ─── core ────────────────────────────────────────────────────────────────────

def run(batch_id: str, mode: str, allow_live: bool,
        confirm_token: str | None) -> dict:
    gate_g2_freeze()
    batch = gate_g3_batch(batch_id)
    provider = gate_g4_provider()
    gate_g5_sandbox(provider, allow_live)
    recipients = gate_g6_recipients(batch)
    expected_token = compute_confirm_token(batch, recipients)

    if mode == "live":
        # G1 + G8 only bite in live mode
        if os.environ.get("MARKETING_CROWDFUNDING_SEND_ENABLED", "") != "true":
            raise GateAbort("G1", "MARKETING_CROWDFUNDING_SEND_ENABLED != true")
        if confirm_token != expected_token:
            raise GateAbort("G8", "confirm token mismatch — run dry_run first")
        raise GateAbort("LIVE", "live transport not implemented in Phase 6 "
                                "(by design — see module docstring)")

    outbox = _OUTBOX_ROOT / batch_id[:8]
    outbox.mkdir(parents=True, exist_ok=True)
    created = skipped = 0

    for r in recipients:
        rid = r["recipient_id"]
        # G7: idempotency — existing ledger row wins, reuse its link
        existing = _db.query_one(
            f"SELECT approve_url FROM marketing.crowdfunding_contributions "
            f"WHERE batch_id = {_db._sql_literal(batch_id)}::uuid "
            f"  AND recipient_id = {_db._sql_literal(rid)}"
        )
        if existing:
            approve_url = existing["approve_url"]
            skipped += 1
        else:
            link = provider.create_payment_link(
                amount=batch["amount"], currency=batch["currency"],
                return_url=f"{_PUBLIC_BASE}/return",
                cancel_url=f"{_PUBLIC_BASE}/cancel",
                description=f"VibeMind backer contribution",
                metadata={"reference": f"{batch_id[:8]}:{rid}"},
            )
            approve_url = link.approve_url
            _db.execute_via_docker(
                f"INSERT INTO marketing.crowdfunding_contributions "
                f"(batch_id, recipient_id, order_id, approve_url, amount, currency) "
                f"VALUES ({_db._sql_literal(batch_id)}::uuid, "
                f"        {_db._sql_literal(rid)}, "
                f"        {_db._sql_literal(link.order_id)}, "
                f"        {_db._sql_literal(approve_url)}, "
                f"        {_db._sql_literal(batch['amount'])}, "
                f"        {_db._sql_literal(batch['currency'])}) "
                f"ON CONFLICT (batch_id, recipient_id) DO NOTHING"
            )
            created += 1
        message = render_message(batch["channel"], r, approve_url, batch)
        safe_name = rid.replace("@", "_at_").replace("/", "_")
        (outbox / f"{safe_name}.txt").write_text(message, encoding="utf-8")
        logger.info("[%s] link %s (%s)", rid,
                    "created" if not existing else "reused",
                    approve_url[-24:])

    result = {
        "mode": mode, "batch_id": batch_id,
        "recipients": len(recipients),
        "links_created": created, "links_reused": skipped,
        "outbox": str(outbox),
        "confirm_token_for_live": expected_token,
        "sent": 0,  # dry_run sends nothing, ever
    }
    logger.info("dry_run done: %s", json.dumps(result, indent=2))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Crowdfunding batch sender")
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--mode", choices=["dry_run", "live"], default="dry_run")
    ap.add_argument("--allow-live", action="store_true",
                    help="permit PAYPAL_ENV=live (G5)")
    ap.add_argument("--confirm-token", default=None)
    args = ap.parse_args()
    run(args.batch_id, args.mode, args.allow_live, args.confirm_token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
