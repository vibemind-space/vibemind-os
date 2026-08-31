"""Multi-channel send-eligibility helpers.

Read-only listing of marketing.channel_config + the assert_channel_configured
gate the send-worker uses at gate 4.5 (between campaign-resolve and
recipient-snapshot).

NO new send path. This module REFUSES sends on unimplemented channels;
it does NOT enable them. Adding a real send-channel still requires:
  1. A new migration that flips send_implemented=true for that row.
  2. A per-channel send module (tools/_send_<channel>.py) with its
     own 12-gate stack.
  3. Tests including no-cross-channel regression-guards.
  4. Operator action setting `enabled=true` once env-creds are filled.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ..sync import _db


logger = logging.getLogger("marketing.channels")


def list_channels(only_implemented: bool = False,
                  only_enabled: bool = False) -> Dict[str, Any]:
    """Read-only list of all known channels + their gates."""
    where_clauses = []
    if only_implemented:
        where_clauses.append("send_implemented = true")
    if only_enabled:
        where_clauses.append("enabled = true")
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = _db.query_via_docker(
        f"SELECT channel, label, openfang_adapter, auth_kind, "
        f"       required_env, send_implemented, enabled, "
        f"       rate_limit_per_minute, last_send_at::text AS last_send_at, "
        f"       notes "
        f"FROM marketing.channel_config {where} ORDER BY channel"
    )
    return {"success": True, "message": f"{len(rows)} channel(s)", "data": rows}


def get_channel(channel: str) -> Dict[str, Any]:
    row = _db.query_one(
        f"SELECT channel, label, openfang_adapter, auth_kind, "
        f"       required_env, send_implemented, enabled, "
        f"       rate_limit_per_minute, last_send_at::text AS last_send_at, "
        f"       notes "
        f"FROM marketing.channel_config "
        f"WHERE channel = {_db._sql_literal(channel)}"
    )
    if not row:
        return {"success": False, "message": f"unknown channel {channel!r}",
                "data": None}
    return {"success": True, "message": "ok", "data": row}


# ─── Send-worker gate 4.5 ──────────────────────────────────────────────


def assert_channel_configured(channel: str) -> Dict[str, Any]:
    """Used by _send_paranoid as gate 4.5 (between campaign-resolve and
    recipient-snapshot). Raises ParanoidAbort on:
      - unknown channel
      - send_implemented=false (no per-channel send module)
      - enabled=false (operator hasn't turned it on)
      - missing required env vars

    Returns the channel row on success.
    """
    from ._send_paranoid import ParanoidAbort

    row = _db.query_one(
        f"SELECT channel, send_implemented, enabled, required_env, "
        f"       rate_limit_per_minute "
        f"FROM marketing.channel_config "
        f"WHERE channel = {_db._sql_literal(channel)}"
    )
    if not row:
        raise ParanoidAbort(
            "channel_unknown",
            f"campaign.channel={channel!r} not in marketing.channel_config; "
            f"register the channel via a new migration before sending",
        )
    if not row.get("send_implemented"):
        raise ParanoidAbort(
            "channel_not_implemented",
            f"channel {channel!r} has send_implemented=false. Per-channel "
            f"send module + tests + migration required to enable it.",
        )
    if not row.get("enabled"):
        raise ParanoidAbort(
            "channel_disabled",
            f"channel {channel!r} has enabled=false. Operator must set "
            f"enabled=true on marketing.channel_config row once env-creds "
            f"are configured.",
        )
    # Env-var sanity check
    required = row.get("required_env") or []
    if isinstance(required, str):
        # In case the JSONB came back as a JSON string
        import json
        try:
            required = json.loads(required)
        except Exception:
            required = []
    missing = [k for k in required
               if not os.environ.get(k, "").strip()]
    if missing:
        raise ParanoidAbort(
            "channel_env_missing",
            f"channel {channel!r}: missing required env vars: {missing}",
        )
    return row


# ─── Channel readiness detection + opt-in auto-enable ─────────────────


_AUTO_ENABLE_ENV = "MARKETING_AUTO_ENABLE_CHANNELS"


def _required_env_for_channel(row: Dict[str, Any]) -> List[str]:
    """Decode required_env which comes back as list, str, or jsonb."""
    required = row.get("required_env") or []
    if isinstance(required, str):
        import json
        try:
            required = json.loads(required)
        except Exception:
            return []
    return [k for k in required if isinstance(k, str)]


def detect_channel_readiness() -> Dict[str, Any]:
    """Read-only scan: for every channel in marketing.channel_config,
    decide whether it is fully ready to send.

    A channel is `ready` iff:
      - send_implemented = true   (per-channel send module exists, reviewed)
      - all required_env vars are present in os.environ AND non-empty
      - enabled = true            (operator has flipped the soft gate)

    Returns swarm-envelope with a per-channel breakdown that the UI
    can render directly. NEVER mutates the DB.
    """
    rows = _db.query_via_docker(
        "SELECT channel, label, send_implemented, enabled, required_env, "
        "       openfang_adapter "
        "FROM marketing.channel_config ORDER BY channel"
    )
    out = []
    for row in rows:
        required = _required_env_for_channel(row)
        missing = [k for k in required
                   if not os.environ.get(k, "").strip()]
        env_present = (len(missing) == 0)
        ready = bool(row.get("send_implemented")) and env_present and bool(row.get("enabled"))
        could_enable = bool(row.get("send_implemented")) and env_present and not row.get("enabled")
        out.append({
            "channel": row["channel"],
            "label": row.get("label"),
            "send_implemented": bool(row.get("send_implemented")),
            "enabled": bool(row.get("enabled")),
            "env_present": env_present,
            "missing_env": missing,
            "ready": ready,
            "could_auto_enable": could_enable,
            "openfang_adapter": row.get("openfang_adapter"),
        })
    summary = {
        "channels_total": len(out),
        "channels_ready": sum(1 for c in out if c["ready"]),
        "channels_could_auto_enable": sum(1 for c in out if c["could_auto_enable"]),
    }
    return {
        "success": True,
        "message": (f"{summary['channels_ready']} ready, "
                    f"{summary['channels_could_auto_enable']} could auto-enable"),
        "data": {"summary": summary, "channels": out},
    }


def auto_enable_ready_channels(*, dry_run: bool = False,
                                actor: str = "auto_enable") -> Dict[str, Any]:
    """Flip `enabled = true` on every channel that:
      - has send_implemented = true
      - has all required_env vars present
      - is currently enabled = false

    HARDCODED safeguards (so a silent env-mutation can't enable a channel):
      1. MARKETING_AUTO_ENABLE_CHANNELS env MUST equal 'true'. Otherwise
         returns a no-op envelope with a clear refused message.
      2. send_implemented STAYS gated by migrations -- this function
         NEVER flips send_implemented. Only the soft `enabled` gate.
      3. Audit row written for every flipped channel.
      4. Never disables a channel that is enabled. Operator-disabled
         channels stay disabled until manual re-enable.
    """
    enabled_flag = os.environ.get(_AUTO_ENABLE_ENV, "").strip().lower()
    if enabled_flag not in ("true", "1", "yes"):
        return {
            "success": False,
            "message": f"{_AUTO_ENABLE_ENV} must equal 'true' to auto-enable channels "
                       f"(currently {enabled_flag!r}). No-op.",
            "data": {"enabled_count": 0, "flipped": []},
        }

    readiness = detect_channel_readiness()["data"]["channels"]
    candidates = [c for c in readiness if c["could_auto_enable"]]
    if not candidates:
        return {
            "success": True,
            "message": "0 channels eligible for auto-enable",
            "data": {"enabled_count": 0, "flipped": [], "dry_run": dry_run},
        }

    flipped = []
    for c in candidates:
        if dry_run:
            flipped.append({"channel": c["channel"], "missing_env": []})
            continue
        try:
            _db.execute_via_docker(
                f"UPDATE marketing.channel_config "
                f"SET enabled = true "
                f"WHERE channel = {_db._sql_literal(c['channel'])} "
                f"  AND enabled = false "      # idempotent re-run
                f"  AND send_implemented = true"
            )
            flipped.append({"channel": c["channel"], "missing_env": []})
        except Exception as e:
            logger.exception("[auto_enable] flipping %s failed", c["channel"])
            flipped.append({"channel": c["channel"], "error": str(e)[:200]})

    # Audit (single row covering the whole batch)
    if not dry_run and flipped:
        import json
        try:
            _db.execute_via_docker(
                f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
                f"VALUES ("
                f"  {_db._sql_literal('channels:auto_enable:' + actor)}, "
                f"  'channel_config.auto_enabled', "
                f"  'marketing.channel_config', "
                f"  {_db._sql_literal(json.dumps({'flipped': flipped, 'dry_run': dry_run}))}::jsonb"
                f")"
            )
        except Exception as e:
            logger.warning("[auto_enable] audit insert failed: %s", e)

    return {
        "success": True,
        "message": (f"DRY RUN: would auto-enable {len(flipped)} channel(s): "
                    f"{[c['channel'] for c in flipped]}"
                    if dry_run else
                    f"auto-enabled {len(flipped)} channel(s): "
                    f"{[c['channel'] for c in flipped]}"),
        "data": {
            "enabled_count": len(flipped),
            "flipped": flipped,
            "dry_run": dry_run,
        },
    }


__all__ = [
    "list_channels",
    "get_channel",
    "assert_channel_configured",
    "detect_channel_readiness",
    "auto_enable_ready_channels",
]
