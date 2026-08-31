"""OpenFang Approvals UI <-> marketing-API bridge (Schicht 7.0b).

Watches OpenFang's /api/approvals every N seconds. For each
broadcast_proposals + reply_proposals row in pending_approval status with
openfang_approval_id set, look up the OpenFang state:

  pending  -> nothing to do
  approved -> POST /api/broadcast_proposals/{id}/approve with token
  rejected -> POST /api/broadcast_proposals/{id}/reject with token
  timeout  -> POST /api/broadcast_proposals/{id}/reject with reason='openfang_timeout'

The HMAC token is read from marketing.broadcast_proposals.approval_token_raw
(stored on request_approval; cleared on resolve). marketing-API itself does
the verify + clears the raw-token + emits webhook 'broadcast_proposal_status_changed'.

NEVER writes user-PII to logs. Polls both broadcast_proposals AND reply_proposals
(same lifecycle, same column-shape).

Designed to run as a long-lived sidecar:
    python -m spaces.marketing.workers.openfang_approval_bridge
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


PKG_ROOT = next(p.parent for p in Path(__file__).resolve().parents if p.name == "spaces")
REPO_ROOT = next((p for p in (PKG_ROOT, *PKG_ROOT.parents) if (p / "vibemind-os").is_dir()), PKG_ROOT)
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.sync import _db  # noqa: E402


logger = logging.getLogger("marketing.openfang_approval_bridge")


_POLL_INTERVAL_S = float(os.environ.get("OPENFANG_BRIDGE_POLL_INTERVAL_S", "3"))
_HTTP_TIMEOUT_S = 8


def _openfang_url() -> str:
    return os.environ.get("OPENFANG_URL", "http://localhost:4200").rstrip("/")


def _marketing_url() -> str:
    return os.environ.get(
        "MARKETING_API_URL", "http://127.0.0.1:5510"
    ).rstrip("/")


def _proposal_api_key() -> str:
    k = os.environ.get("MARKETING_PROPOSAL_API_KEY", "").strip()
    if not k or len(k) < 32:
        raise RuntimeError(
            "MARKETING_PROPOSAL_API_KEY required (>=32 chars) - "
            "bridge cannot relay approvals without it"
        )
    return k


def _http_get_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT_S) as r:
            return json.loads(r.read() or b"{}")
    except Exception as e:
        logger.debug("GET %s failed: %s", url, e)
        return None


def _http_post_json(url: str, body: dict) -> tuple[int, dict | None]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body_raw = b""
        try:
            body_raw = e.read()
        except Exception:
            pass
        try:
            return e.code, json.loads(body_raw or b"{}")
        except Exception:
            return e.code, {"raw": body_raw.decode("utf-8", "replace")[:300]}
    except Exception as e:
        return 0, {"transport_error": f"{type(e).__name__}: {e}"}


def _fetch_openfang_state() -> dict[str, str]:
    """Return {openfang_approval_id: status} for all approvals OpenFang knows."""
    resp = _http_get_json(f"{_openfang_url()}/api/approvals")
    if not resp:
        return {}
    out: dict[str, str] = {}
    for a in resp.get("approvals", []):
        if not isinstance(a, dict):
            continue
        aid = a.get("id")
        status = a.get("status")
        if aid and isinstance(aid, str) and len(aid) == 36 and status:
            out[aid] = status.lower()
    return out


def _pending_proposals(table: str) -> list[dict]:
    # Schicht 7.0b hardened: no more approval_token_raw; bridge auths via
    # api_key + server-side openfang_approval_id match.
    return _db.query_via_docker(
        f"SELECT id::text AS id, "
        f"       openfang_approval_id::text AS openfang_approval_id "
        f"FROM marketing.{table} "
        f"WHERE status = 'pending_approval' "
        f"  AND openfang_approval_id IS NOT NULL "
        f"LIMIT 50"
    )


def _relay(table: str, proposal_id: str, openfang_approval_id: str,
            decision: str, reason: str = "") -> tuple[int, str]:
    # decision: 'approve' or 'reject' -> hits /{decision}_via_bridge
    route_base = (
        "/api/broadcast_proposals" if table == "broadcast_proposals"
        else "/api/reply_proposals"
    )
    url = f"{_marketing_url()}{route_base}/{proposal_id}/{decision}_via_bridge"
    body = {
        "api_key": _proposal_api_key(),
        "openfang_approval_id": openfang_approval_id,
        "actor": "openfang-bridge",
    }
    if decision == "reject" and reason:
        body["reason"] = reason
    status, resp = _http_post_json(url, body)
    msg = (resp or {}).get("message", "")
    return status, msg


def _run_cycle() -> dict:
    stats = {"relayed_approve": 0, "relayed_reject": 0,
             "still_pending": 0, "no_openfang_row": 0, "errors": 0}
    of_state = _fetch_openfang_state()
    if not of_state:
        return stats

    for table in ("broadcast_proposals", "reply_proposals"):
        try:
            pendings = _pending_proposals(table)
        except Exception as e:
            logger.warning("query %s failed: %s", table, e)
            stats["errors"] += 1
            continue

        for row in pendings:
            of_id = row.get("openfang_approval_id")
            if not of_id:
                continue
            of_status = of_state.get(of_id)
            if of_status is None:
                stats["no_openfang_row"] += 1
                continue
            if of_status == "pending":
                stats["still_pending"] += 1
                continue
            if of_status == "approved":
                code, msg = _relay(table, row["id"], of_id, "approve")
                if code == 200:
                    stats["relayed_approve"] += 1
                    logger.info("[%s/%s] approved via OpenFang -> marketing",
                                table, row["id"])
                else:
                    stats["errors"] += 1
                    logger.warning("[%s/%s] approve relay HTTP %s: %s",
                                   table, row["id"], code, msg[:120])
            elif of_status in ("rejected", "timeout", "expired", "denied"):
                code, msg = _relay(
                    table, row["id"], of_id, "reject",
                    reason=f"openfang:{of_status}"
                )
                if code == 200:
                    stats["relayed_reject"] += 1
                    logger.info("[%s/%s] %s via OpenFang -> marketing",
                                table, row["id"], of_status)
                else:
                    stats["errors"] += 1
                    logger.warning("[%s/%s] reject relay HTTP %s: %s",
                                   table, row["id"], code, msg[:120])
            else:
                # SAFE-DEFAULT: unknown status -> do NOT touch marketing row.
                # This is the critical anti-misroute invariant: only known
                # decisions cause writes.
                logger.warning("[%s/%s] unknown OpenFang status %r - SKIPPING (safe-default)",
                               table, row["id"], of_status)
    return stats


def run_forever():
    logger.info("openfang_approval_bridge starting "
                "(poll=%.1fs, openfang=%s, marketing=%s)",
                _POLL_INTERVAL_S, _openfang_url(), _marketing_url())
    while True:
        try:
            stats = _run_cycle()
            if any(v for k, v in stats.items() if k != "still_pending"):
                logger.info("cycle: %s", stats)
        except KeyboardInterrupt:
            logger.info("interrupted, exiting")
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
