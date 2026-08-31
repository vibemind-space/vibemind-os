"""paypal_webhook_handler — the ONLY writer of contributions.paid_at (G12).

Two drive modes (mirrors delivered_webhook.py, Worker D):

  HTTP receiver (default)
      python -m spaces.marketing.workers.paypal_webhook_handler --serve
      Listens on 127.0.0.1:5514 for the payment-infra event forward
      (PAYMENT_EVENT_FORWARD_URL=http://127.0.0.1:5514/event). payment-infra
      has ALREADY verified the PayPal signature — this bind is loopback-only
      and additionally guarded by a shared secret header.

  Reconcile poll (--reconcile)
      python -m spaces.marketing.workers.paypal_webhook_handler --reconcile
      Proven fallback for dropped webhooks/closed browsers: for every
      unpaid ledger row, GET the order status via the payment-infra SDK;
      APPROVED -> capture -> paid. COMPLETED -> paid.

Safety:
  * paid_at set atomically with WHERE paid_at IS NULL — duplicate events
    are no-ops (idempotent).
  * every write lands in marketing.audit_log.
  * emits 'contribution_paid' on the webhook bus for downstream consumers.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
PAYMENT_INFRA = REPO_ROOT.parent / "VibeMind-OS" / "payment-infra"
if str(PAYMENT_INFRA) not in sys.path:
    sys.path.insert(0, str(PAYMENT_INFRA))

from spaces.marketing.sync import _db  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("marketing.paypal_webhook_handler")

_PORT = int(os.environ.get("CROWDFUNDING_WEBHOOK_PORT", "5514"))
_SECRET = os.environ.get("CROWDFUNDING_WEBHOOK_SECRET", "")


def _audit(action: str, target: str, payload: dict) -> None:
    _db.execute_via_docker(
        f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
        f"VALUES ('paypal_webhook_handler', {_db._sql_literal(action)}, "
        f"        'marketing.crowdfunding_contributions', "
        f"        {_db._sql_literal(json.dumps(payload))}::jsonb)"
    )


def mark_paid(order_id: str, capture_id: str | None,
              source: str) -> bool:
    """Atomic paid_at write. Returns True iff THIS call flipped the row."""
    row = _db.query_one(
        f"SELECT id::text AS id, batch_id::text AS batch_id, recipient_id, "
        f"       paid_at IS NOT NULL AS already_paid "
        f"FROM marketing.crowdfunding_contributions "
        f"WHERE order_id = {_db._sql_literal(order_id)}"
    )
    if not row:
        logger.warning("unknown order_id %s (source=%s) — no write", order_id, source)
        _audit("paid.unknown_order", order_id,
               {"order_id": order_id, "source": source})
        return False
    if row["already_paid"]:
        logger.info("order %s already paid — idempotent no-op", order_id)
        return False
    _db.execute_via_docker(
        f"UPDATE marketing.crowdfunding_contributions "
        f"SET paid_at = now(), status = 'paid', "
        f"    capture_id = {_db._sql_literal(capture_id)} "
        f"WHERE order_id = {_db._sql_literal(order_id)} "
        f"  AND paid_at IS NULL"
    )
    _audit("paid.marked", order_id, {
        "order_id": order_id, "capture_id": capture_id,
        "recipient_id": row["recipient_id"], "batch_id": row["batch_id"],
        "source": source,
    })
    _db.execute_via_docker(
        f"SELECT marketing.emit_webhook_event('contribution_paid', "
        f"jsonb_build_object('order_id', {_db._sql_literal(order_id)}, "
        f"'batch_id', {_db._sql_literal(row['batch_id'])}, "
        f"'recipient_id', {_db._sql_literal(row['recipient_id'])}), NULL, NULL)"
    )
    logger.info("PAID: order=%s recipient=%s batch=%s (source=%s)",
                order_id, row["recipient_id"], row["batch_id"][:8], source)
    return True


# ─── HTTP receiver ───────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        if self.path != "/event":
            self.send_response(404); self.end_headers(); return
        if _SECRET and self.headers.get("X-Crowdfunding-Secret", "") != _SECRET:
            self.send_response(401); self.end_headers(); return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.send_response(400); self.end_headers(); return
        event_type = body.get("event_type", "")
        order_id = body.get("order_id")
        if event_type == "PAYMENT.CAPTURE.COMPLETED" and order_id:
            mark_paid(order_id, body.get("capture_id"), source="webhook")
        else:
            logger.info("ignored event %s (order=%s)", event_type, order_id)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, fmt, *args):  # quiet default access log
        pass


def serve() -> None:
    srv = HTTPServer(("127.0.0.1", _PORT), _Handler)
    logger.info("listening on 127.0.0.1:%s (secret=%s)",
                _PORT, "set" if _SECRET else "OFF/dev")
    srv.serve_forever()


# ─── reconcile poll (webhook fallback, proven in Phase-0 spike) ─────────────

def reconcile() -> dict:
    from providers import get_provider  # payment-infra SDK
    provider = get_provider("paypal")
    rows = _db.query_via_docker(
        "SELECT order_id FROM marketing.crowdfunding_contributions "
        "WHERE paid_at IS NULL AND order_id IS NOT NULL "
        "ORDER BY created_at LIMIT 50"
    )
    stats = {"checked": 0, "captured": 0, "paid": 0}
    for r in rows:
        oid = r["order_id"]
        stats["checked"] += 1
        try:
            st = provider.get_order_status(oid)
        except Exception as exc:
            logger.warning("status poll failed for %s: %s", oid, exc)
            continue
        if st.status == "APPROVED":
            cap = provider.capture(oid)
            if cap.ok:
                stats["captured"] += 1
                if mark_paid(oid, cap.capture_id, source="reconcile+capture"):
                    stats["paid"] += 1
        elif st.status == "COMPLETED":
            if mark_paid(oid, None, source="reconcile"):
                stats["paid"] += 1
    logger.info("reconcile: %s", stats)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="paid_at single-writer (G12)")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--reconcile", action="store_true")
    ap.add_argument("--simulate-order", default="",
                    help="testing: mark this order_id paid via mark_paid()")
    args = ap.parse_args()
    if args.simulate_order:
        mark_paid(args.simulate_order, "SIMULATED", source="simulate")
        return 0
    if args.reconcile:
        reconcile()
        return 0
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
