"""IDEM-3 [PHASE-2 ENFORCEMENT] — PayPal-Request-Id + Ledger UNIQUE + Caps
(Guardrail 3).

Vorinstallierte Falle per POL-0 `test_activation_mechanism` (skipif-absent).
Policy: docs/policy/backer-sandbox-guardrails.md -> idempotency_ledger_caps.
Anti-Pattern (OS-Referenz paypal_client.py:76-97): create_order ohne
PayPal-Request-Id-Header, kein Ledger, kein Cap.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKER = REPO_ROOT / "backer-checkout"

pytestmark = pytest.mark.skipif(
    not BACKER.exists(),
    reason="Phase-2 ENFORCEMENT — backer-checkout absent (POL-0)",
)


@pytest.fixture()
def backer_path():
    sys.path.insert(0, str(BACKER))
    yield BACKER
    sys.path.remove(str(BACKER))


class TestIdempotencyKey:
    def test_create_order_sends_stable_paypal_request_id(self, backer_path, monkeypatch):
        """Same (run_id, recipient, amount) -> identical PayPal-Request-Id
        across retries, so PayPal dedupes instead of double-charging."""
        import paypal_client
        seen_headers = []

        def _fake_post(url, headers=None, **kw):
            seen_headers.append(headers or {})

            class R:
                status_code = 201

                def json(self):
                    return {"id": "ORDER-1", "links": []}

                def raise_for_status(self):
                    pass

            return R()

        monkeypatch.setattr(paypal_client.requests, "post", _fake_post)
        monkeypatch.setenv("PAYPAL_ENV", "sandbox")
        paypal_client.create_order("a@example.com", 1.0, run_id="run-1")
        paypal_client.create_order("a@example.com", 1.0, run_id="run-1")
        ids = [h.get("PayPal-Request-Id") for h in seen_headers]
        assert all(ids), "PayPal-Request-Id header missing (OS anti-pattern)"
        assert ids[0] == ids[1], "idempotency key not stable across retries"


class TestLedgerUnique:
    def test_duplicate_order_id_raises_integrity_error(self, backer_path, tmp_path):
        import ledger
        db = ledger.Ledger(tmp_path / "test-ledger.db")
        db.record_order(order_id="O-1", recipient="a@example.com", amount=1.0)
        with pytest.raises(sqlite3.IntegrityError):
            db.record_order(order_id="O-1", recipient="b@example.com", amount=1.0)


class TestOrderCap:
    def test_max_orders_per_run_enforced_before_paypal_call(self, backer_path, monkeypatch):
        """Order N+1 beyond MAX_ORDERS_PER_RUN -> rejected, NO PayPal call."""
        monkeypatch.setenv("MAX_ORDERS_PER_RUN", "2")
        monkeypatch.setenv("PAYPAL_ENV", "sandbox")
        import app as backer_app
        calls = []
        monkeypatch.setattr(
            backer_app, "_paypal_create", lambda *a, **kw: calls.append(a),
            raising=False,
        )
        # exact enforcement API is Phase-2 scope; the contract under test:
        # the cap check happens BEFORE any PayPal call and yields 429
        client = backer_app.app.test_client()
        for i in range(3):
            resp = client.post("/create-order", json={"recipient": f"r{i}@example.com"})
        assert resp.status_code == 429
        assert len(calls) <= 2
