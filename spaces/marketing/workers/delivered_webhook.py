"""Worker D - delivered_at writer.

Bridge from Mailcow delivery confirmations into
marketing.campaign_sends.delivered_at, which fires trg_flip_investor_sent
(migration 005) and sets marketing.emails.investor_already_sent=true.

That trigger is the only place where Phase-1 actively burns the sticky
lockout for a recipient -- by design, only the post-send delivery
confirmation should do this. Send-worker NEVER sets delivered_at
(verified by gate 12 tests). This worker is the ONLY writer.

Two ways to drive it:

  CLI simulator (no Mailcow webhook config needed)
    python -m spaces.marketing.workers.delivered_webhook --simulate \\
        --message-id <core>     -- bracket-stripped, e.g. "abc123@vibemind.space"

  HTTP endpoint (Phase-2b production cutover)
    python -m spaces.marketing.workers.delivered_webhook --serve [--port 5512]
    POST /webhook with JSON {"message_id": "<core>", "secret": "<env>"}
    Bind is 127.0.0.1-only. Shared secret in MARKETING_WEBHOOK_SECRET.

Safety:
  * Recipient-email of the matched send-row is checked against
    ALLOWED_DOMAINS (defense-in-depth -- send-worker already blocks
    non-vibemind.space). If a send-row's email is somehow non-allowed,
    we DO NOT set delivered_at and log a hard-warning (operator review).
  * delivered_at is set atomically with a WHERE delivered_at IS NULL
    guard -- second webhook for the same send is a no-op.
  * Every action is audit-logged.
"""
from __future__ import annotations

import argparse
import hmac
import http.server
import json
import logging
import os
import socketserver
import sys
import time
from pathlib import Path
from typing import Optional

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.sync import _db  # noqa: E402
from spaces.marketing.tools._send_paranoid import ALLOWED_DOMAINS  # noqa: E402

logger = logging.getLogger("marketing.delivered_webhook")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


# ─── Core: mark a send delivered ───────────────────────────────────────


def mark_delivered(message_id: str, *, actor: str = "webhook") -> dict:
    """Set delivered_at on the matching send-row.

    Returns {success, message, data}. Idempotent: second call on the
    same message_id sees delivered_at IS NOT NULL and reports
    'already_delivered'.
    """
    if not message_id or "@" not in message_id:
        return {"success": False, "message": "invalid message_id (need 'core@domain')",
                "data": None}

    # Look up the send-row. Defense-in-depth: also pull email so we can
    # re-check the allowlist.
    row = _db.query_one(
        f"SELECT cs.id::text AS id, cs.email, cs.delivered_at::text AS delivered_at "
        f"FROM marketing.campaign_sends cs "
        f"WHERE cs.message_id = {_db._sql_literal(message_id)}"
    )
    if not row:
        return {"success": False, "message": f"no send-row for message_id={message_id}",
                "data": None}

    if row.get("delivered_at"):
        return {"success": True, "message": "already_delivered",
                "data": {"send_id": row["id"], "email": row["email"]}}

    # Defense-in-depth: never write delivered_at for a recipient that
    # somehow ended up non-allowlisted. Should be impossible (send-worker
    # gate 5 blocks), but the lockout trigger is permanent so we doublecheck.
    email = (row.get("email") or "").lower()
    domain = email.rsplit("@", 1)[1] if "@" in email else ""
    if domain not in ALLOWED_DOMAINS:
        _audit("webhook.skip.non_allowlist", {
            "send_id": row["id"], "email": email, "message_id": message_id,
            "reason": "recipient domain not in ALLOWED_DOMAINS -- refusing to flip lockout",
        }, actor=actor)
        logger.error("[webhook] REFUSING delivered_at flip for non-allowlist email %s", email)
        return {"success": False,
                "message": f"recipient {email!r} not in allowlist; refusing to flip lockout",
                "data": {"send_id": row["id"], "email": email}}

    # Atomic flip. WHERE-guard makes second-webhook a no-op.
    # trg_flip_investor_sent fires here and flips marketing.emails
    # investor_already_sent=true for this recipient.
    _db.execute_via_docker(
        f"UPDATE marketing.campaign_sends SET delivered_at = now() "
        f"WHERE id = {_db._sql_literal(row['id'])}::uuid "
        f"  AND delivered_at IS NULL"
    )

    _audit("webhook.delivered", {
        "send_id": row["id"], "email": email, "message_id": message_id,
    }, actor=actor)
    logger.info("[webhook] delivered_at set for send=%s email=%s",
                row["id"][:8], email)
    return {"success": True, "message": "delivered_at set; lockout flipped via trigger",
            "data": {"send_id": row["id"], "email": email}}


def _audit(action: str, payload: dict, *, actor: str = "webhook") -> None:
    try:
        _db.execute_via_docker(
            f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
            f"VALUES ({_db._sql_literal('delivered_webhook:' + actor)}, "
            f"        {_db._sql_literal(action)}, "
            f"        'marketing.campaign_sends', "
            f"        {_db._sql_literal(json.dumps(payload, default=str))}::jsonb)"
        )
    except Exception as e:
        logger.warning("audit insert failed: %s", e)


# ─── HTTP endpoint (Phase-2b production cutover) ───────────────────────


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # route HTTP logs through our logger
        logger.info("http: " + fmt, *args)

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/webhook":
            self._json(404, {"success": False, "message": "no such endpoint"})
            return

        # Shared-secret check. Header X-Webhook-Secret OR JSON.secret.
        expected = os.environ.get("MARKETING_WEBHOOK_SECRET", "").strip()
        if not expected:
            self._json(500, {"success": False,
                             "message": "MARKETING_WEBHOOK_SECRET not set on server"})
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as e:
            self._json(400, {"success": False, "message": f"invalid json: {e}"})
            return

        provided = (self.headers.get("X-Webhook-Secret")
                    or payload.get("secret", ""))
        # Constant-time comparison defeats remote timing attacks. hmac
        # rejects non-str inputs, so guard explicitly first.
        if (not isinstance(provided, str)
                or not hmac.compare_digest(provided.strip(), expected)):
            logger.warning("rejected webhook with bad/missing secret from %s",
                           self.client_address[0])
            self._json(401, {"success": False, "message": "invalid secret"})
            return

        message_id = (payload.get("message_id") or "").strip()
        if not message_id:
            self._json(400, {"success": False, "message": "message_id required"})
            return

        result = mark_delivered(message_id, actor="http")
        self._json(200 if result["success"] else 400, result)


def serve(host: str = "127.0.0.1", port: int = 5512) -> None:
    # Loopback-only enforcement. Webhook is the ONLY writer of
    # delivered_at; binding it to 0.0.0.0 would let any LAN client
    # flip the investor-lockout for any campaign_sends row (given
    # only the message_id, which is logged in many places). Refuse
    # to start unless the operator explicitly overrides via env.
    if host not in ("127.0.0.1", "::1", "localhost"):
        if os.environ.get("MARKETING_WEBHOOK_ALLOW_NONLOOPBACK", "").lower() not in (
            "true", "1", "yes",
        ):
            logger.error(
                "refusing to bind %s -- non-loopback. Set "
                "MARKETING_WEBHOOK_ALLOW_NONLOOPBACK=true to override "
                "AFTER confirming you have a real auth/TLS layer in front.",
                host,
            )
            sys.exit(2)
        logger.warning("non-loopback bind %s explicitly allowed via override env", host)
    if not os.environ.get("MARKETING_WEBHOOK_SECRET", "").strip():
        logger.error("MARKETING_WEBHOOK_SECRET missing -- refusing to start (would 500 every request)")
        sys.exit(2)
    with socketserver.TCPServer((host, port), _WebhookHandler) as srv:
        srv.allow_reuse_address = True
        logger.info("delivered_webhook listening on http://%s:%d/webhook", host, port)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            logger.info("shutdown requested -- bye")


# ─── CLI ───────────────────────────────────────────────────────────────


def _main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--simulate", action="store_true",
                   help="mark a single message_id as delivered (no HTTP)")
    g.add_argument("--serve", action="store_true",
                   help="run HTTP server on 127.0.0.1:5512")
    p.add_argument("--message-id", help="bracket-stripped Message-ID for --simulate")
    p.add_argument("--port", type=int, default=5512)
    p.add_argument("--bind", default="127.0.0.1")
    args = p.parse_args()

    if args.simulate:
        if not args.message_id:
            p.error("--simulate requires --message-id")
        result = mark_delivered(args.message_id, actor="cli")
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["success"] else 3

    serve(host=args.bind, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
