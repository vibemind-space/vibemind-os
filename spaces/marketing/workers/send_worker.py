"""Standalone CLI for the Phase-2 marketing send-worker.

Usage:
    python -m spaces.marketing.workers.send_worker --campaign-id <uuid> --mode dry_run
    python -m spaces.marketing.workers.send_worker --campaign-id <uuid> --mode shadow
    python -m spaces.marketing.workers.send_worker --campaign-id <uuid> --mode live --confirm-token <hex>

Modes (see _send_paranoid.py docstring for full safety contract):

    dry_run  -- never opens SMTP; never writes campaign_sends; returns
                the confirm_token + recipient preview.
    shadow   -- goes through full pipeline but redirects to Mailpit
                (127.0.0.1:54325) instead of Postfix; mails visible in
                Mailpit-UI :54324.
    live     -- real SMTP send via Mailcow. Requires:
                  * MARKETING_SEND_ENABLED=true env var
                  * logs/marketing/FREEZE absent
                  * --confirm-token matching the audience snapshot

This wrapper exits 0 on success, non-zero on guard fail. Prints JSON
result so it's cron-replayable + log-grepable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.tools._send_paranoid import (  # noqa: E402
    SendMode,
    ParanoidAbort,
    run as run_send,
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign-id", required=True, help="UUID of marketing.campaigns row")
    p.add_argument("--mode", required=True, choices=[m.value for m in SendMode],
                   help="dry_run | shadow | live")
    p.add_argument("--confirm-token",
                   help="64-char SHA256 hex from a prior dry_run (required for live)")
    p.add_argument("--max-recipients", type=int,
                   help="hard cap on recipient count for this run")
    p.add_argument("--rate-per-sec", type=int, default=10,
                   help="token-bucket rate limit (default 10/s)")
    p.add_argument("--operator", default="cli",
                   help="audit-log actor suffix (default 'cli')")
    args = p.parse_args(argv)

    try:
        mode = SendMode(args.mode)
    except ValueError:
        print(json.dumps({"success": False, "error": f"invalid mode: {args.mode}"}),
              file=sys.stderr)
        return 2

    try:
        result = run_send(
            args.campaign_id,
            mode,
            confirm_token=args.confirm_token,
            max_recipients=args.max_recipients,
            rate_per_sec=args.rate_per_sec,
            operator=args.operator,
        )
    except ParanoidAbort as e:
        print(json.dumps({
            "success": False,
            "guard": e.guard,
            "detail": e.detail,
            "summary": str(e),
        }, indent=2), file=sys.stderr)
        return 3
    except Exception as e:
        print(json.dumps({
            "success": False,
            "guard": "unexpected",
            "detail": str(e),
        }, indent=2), file=sys.stderr)
        return 4

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
