"""Operator-side CLI for signing entries in marketing.channel_recipient_allowlist.

Every (channel, recipient_id) the OpenFang send-worker may target must carry
an HMAC-SHA256 signature computed with MARKETING_PROPOSAL_API_KEY over the
canonical form:

    f"allowlist-v1\\n{channel}\\n{recipient_id}\\n{approved_by}"

This script generates the signature, optionally INSERTs the row directly,
and emits the SQL the operator can copy/paste if they prefer to apply it
through the DB-UI.

Usage:
    python -m spaces.marketing.tools.sign_recipient \\
        --channel discord \\
        --recipient-id 1234567890 \\
        --approved-by felix \\
        --label "team-notify #done"

    # Just emit SQL, no INSERT
    python -m spaces.marketing.tools.sign_recipient --emit-sql ...

Verification side (used by _send_openfang.py at gate 6):
    >>> from .sign_recipient import verify_recipient_sig
    >>> verify_recipient_sig("discord", "1234567890", "felix", "<hex>")
    True

The verify function is also exported as the canonical reference so tests
and the send-worker share the SAME signing logic.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
from typing import Optional


_CANONICAL_VERSION = "allowlist-v1"


def _resolve_secret() -> bytes:
    """Pull MARKETING_PROPOSAL_API_KEY from env. Refuse if absent or short."""
    secret = os.environ.get("MARKETING_PROPOSAL_API_KEY", "").strip()
    if not secret:
        print(
            "ERROR: MARKETING_PROPOSAL_API_KEY env var is required to sign or "
            "verify allowlist entries.",
            file=sys.stderr,
        )
        sys.exit(2)
    if len(secret) < 32:
        print(
            f"ERROR: MARKETING_PROPOSAL_API_KEY must be at least 32 chars "
            f"(currently {len(secret)}). Regenerate with: "
            f"python -c \"import secrets; print(secrets.token_urlsafe(48))\"",
            file=sys.stderr,
        )
        sys.exit(2)
    return secret.encode("utf-8")


def canonical_form(channel: str, recipient_id: str, approved_by: str) -> str:
    """The exact string we sign over. Sign and verify must use the SAME form."""
    return f"{_CANONICAL_VERSION}\n{channel}\n{recipient_id}\n{approved_by}"


def sign_recipient(channel: str, recipient_id: str, approved_by: str,
                    secret: Optional[bytes] = None) -> str:
    """Return hex HMAC-SHA256 over the canonical form."""
    if secret is None:
        secret = _resolve_secret()
    payload = canonical_form(channel, recipient_id, approved_by).encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_recipient_sig(channel: str, recipient_id: str,
                          approved_by: str, hmac_sig: str,
                          secret: Optional[bytes] = None) -> bool:
    """Constant-time verify a recipient signature.

    Called by _send_openfang.py at gate 6 (signed allowlist verify).
    Returns False on any kind of failure -- never raises -- so the
    send-worker can collect failures and present them together.
    """
    if not hmac_sig or not isinstance(hmac_sig, str):
        return False
    if not all(c in "0123456789abcdef" for c in hmac_sig.lower()):
        return False
    if secret is None:
        try:
            secret = _resolve_secret()
        except SystemExit:
            return False
    expected = sign_recipient(channel, recipient_id, approved_by, secret=secret)
    return hmac.compare_digest(expected.lower(), hmac_sig.lower())


def emit_sql(channel: str, recipient_id: str, approved_by: str,
              hmac_sig: str, label: Optional[str] = None,
              notes: Optional[str] = None) -> str:
    """Emit a single INSERT statement -- copy/paste friendly."""
    def lit(v: Optional[str]) -> str:
        if v is None:
            return "NULL"
        # Same escape pattern as marketing.sync._db._sql_literal
        return "'" + v.replace("'", "''") + "'"

    return (
        f"INSERT INTO marketing.channel_recipient_allowlist "
        f"(channel, recipient_id, approved_by, hmac_sig, label, notes) "
        f"VALUES ({lit(channel)}, {lit(recipient_id)}, {lit(approved_by)}, "
        f"{lit(hmac_sig)}, {lit(label)}, {lit(notes)});"
    )


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="sign_recipient",
        description="Sign an entry for marketing.channel_recipient_allowlist.",
    )
    p.add_argument("--channel", required=True,
                   help="The channel name (must exist in marketing.channel_config).")
    p.add_argument("--recipient-id", required=True,
                   help="The platform-specific recipient identifier "
                        "(e.g., Discord channel ID, Slack channel, Mastodon handle).")
    p.add_argument("--approved-by", required=True,
                   help="Operator identity (lowercase, e.g. 'felix').")
    p.add_argument("--label", default=None,
                   help="Human-readable label (e.g. 'team-notify #done').")
    p.add_argument("--notes", default=None,
                   help="Free-form notes (audit only).")
    p.add_argument("--emit-sql", action="store_true",
                   help="Only emit the INSERT statement. No DB write.")
    p.add_argument("--insert", action="store_true",
                   help="Actually run the INSERT against marketing.channel_recipient_allowlist.")
    ns = p.parse_args(argv)

    if ns.emit_sql and ns.insert:
        print("ERROR: --emit-sql and --insert are mutually exclusive.", file=sys.stderr)
        return 2

    secret = _resolve_secret()
    sig = sign_recipient(ns.channel, ns.recipient_id, ns.approved_by, secret=secret)
    sql = emit_sql(ns.channel, ns.recipient_id, ns.approved_by, sig,
                    label=ns.label, notes=ns.notes)

    print("# Canonical form (do not paste — used as input to HMAC):")
    print("#")
    for line in canonical_form(ns.channel, ns.recipient_id, ns.approved_by).split("\n"):
        print(f"#   {line!r}")
    print()
    print(f"# HMAC-SHA256: {sig}")
    print()

    if ns.emit_sql or not ns.insert:
        print("# SQL:")
        print(sql)

    if ns.insert:
        # Lazy import: only need _db when actually writing
        from ..sync import _db
        _db.execute_via_docker(sql)
        print()
        print(f"# INSERTed (channel='{ns.channel}', recipient_id='{ns.recipient_id}').")
        # Sanity-check round-trip read
        row = _db.query_one(
            "SELECT hmac_sig FROM marketing.channel_recipient_allowlist "
            f"WHERE channel = {_db._sql_literal(ns.channel)} "
            f"  AND recipient_id = {_db._sql_literal(ns.recipient_id)}"
        )
        if row and row.get("hmac_sig") == sig:
            print("# Verified: round-trip read returned matching hmac_sig.")
        else:
            print("# WARNING: round-trip read did not return matching hmac_sig.",
                  file=sys.stderr)
            return 1

    return 0


__all__ = [
    "canonical_form",
    "sign_recipient",
    "verify_recipient_sig",
    "emit_sql",
]


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
