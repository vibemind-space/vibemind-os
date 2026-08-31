"""Unit tests for Worker D (delivered_at webhook).

Mocks _db so the tests run without supabase. Verifies:
  * unknown message_id -> no write
  * already-delivered -> no write, idempotent reply
  * non-allowlist recipient -> DEFENSIVE REJECT (does NOT flip lockout)
  * happy-path vibemind.space recipient -> UPDATE executed
  * audit-log row written on every action
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))

from spaces.marketing.workers import delivered_webhook as wh  # noqa: E402


_FAILS: list[str] = []


def _check(label: str, cond: bool, detail: str = ""):
    mark = "PASS" if cond else "FAIL"
    line = f"  [{mark}] {label}"
    if detail and not cond:
        line += f"  -- {detail}"
    print(line)
    if not cond:
        _FAILS.append(label)


class FakeDB:
    def __init__(self):
        self.queries: list[str] = []
        self.executes: list[str] = []
        self.row_response: dict | None = None

    def query_one(self, sql, *a, **k):
        self.queries.append(sql)
        return self.row_response

    def query_via_docker(self, sql, *a, **k):
        self.queries.append(sql)
        return []

    def execute_via_docker(self, sql, *a, **k):
        self.executes.append(sql)
        return ""

    def _sql_literal(self, v):
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"


def test_invalid_message_id_no_write():
    fake = FakeDB()
    with mock.patch.object(wh, "_db", fake):
        r = wh.mark_delivered("not-an-email", actor="test")
    no_update = not any("UPDATE marketing.campaign_sends" in s for s in fake.executes)
    _check("invalid_msgid_no_write",
           r["success"] is False and no_update,
           f"executes={fake.executes!r}")


def test_unknown_message_id_no_write():
    fake = FakeDB()
    fake.row_response = None
    with mock.patch.object(wh, "_db", fake):
        r = wh.mark_delivered("ghost@vibemind.space", actor="test")
    no_update = not any("UPDATE marketing.campaign_sends" in s for s in fake.executes)
    _check("unknown_msgid_no_write",
           r["success"] is False and "no send-row" in r["message"] and no_update)


def test_already_delivered_is_idempotent():
    fake = FakeDB()
    fake.row_response = {
        "id": "send-uuid", "email": "felix@vibemind.space",
        "delivered_at": "2026-06-03T10:00:00+00:00",
    }
    with mock.patch.object(wh, "_db", fake):
        r = wh.mark_delivered("abc@vibemind.space", actor="test")
    no_update = not any("UPDATE marketing.campaign_sends" in s for s in fake.executes)
    _check("already_delivered_idempotent",
           r["success"] and r["message"] == "already_delivered" and no_update)


def test_non_allowlist_recipient_refuses_flip():
    """Defense-in-depth: even if a non-allowlist email somehow got into
    campaign_sends, the webhook MUST refuse to flip the lockout."""
    fake = FakeDB()
    fake.row_response = {
        "id": "send-uuid", "email": "evil@gmail.com", "delivered_at": None,
    }
    with mock.patch.object(wh, "_db", fake):
        r = wh.mark_delivered("evil@gmail.com", actor="test")
    no_update = not any("UPDATE marketing.campaign_sends" in s for s in fake.executes)
    audit_present = any("audit_log" in s and "non_allowlist" in s for s in fake.executes)
    _check("non_allowlist_refuses_flip",
           r["success"] is False and "not in allowlist" in r["message"]
           and no_update and audit_present,
           f"update_skipped={no_update} audit={audit_present}")


def test_happy_path_vibemind_flips():
    """Allowlist recipient + null delivered_at => UPDATE executed."""
    fake = FakeDB()
    fake.row_response = {
        "id": "send-uuid-a", "email": "felix@vibemind.space", "delivered_at": None,
    }
    with mock.patch.object(wh, "_db", fake):
        r = wh.mark_delivered("xyz@vibemind.space", actor="test")
    updated = any(
        "UPDATE marketing.campaign_sends SET delivered_at = now()" in s
        for s in fake.executes
    )
    audit_present = any(
        "audit_log" in s and "webhook.delivered" in s for s in fake.executes
    )
    _check("happy_path_flips",
           r["success"] and updated and audit_present,
           f"update_executed={updated} audit={audit_present}")


# ─── runner ─────────────────────────────────────────────────────────────


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    tests = [
        test_invalid_message_id_no_write,
        test_unknown_message_id_no_write,
        test_already_delivered_is_idempotent,
        test_non_allowlist_recipient_refuses_flip,
        test_happy_path_vibemind_flips,
    ]

    print(f"[test_delivered_webhook] running {len(tests)} tests")
    for t in tests:
        try:
            t()
        except Exception as e:
            _check(t.__name__, False, f"raised {type(e).__name__}: {e}")

    total = len(tests)
    fails = len(_FAILS)
    print(f"\n=== {total - fails}/{total} passed ===")
    if fails:
        for f in _FAILS:
            print(f"  - {f}")
        return 1
    print("test_delivered_webhook: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
