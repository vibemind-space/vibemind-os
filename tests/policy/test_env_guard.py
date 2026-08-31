"""ENV-1 [PHASE-2 ENFORCEMENT] — fail-closed PAYPAL_ENV (Guardrail 1).

Vorinstallierte Falle per POL-0 `test_activation_mechanism`: solange
`backer-checkout/` in diesem Baum fehlt, wird geskippt (red-by-absence,
kein Bug-Beweis). Sobald Phase 2 das Verzeichnis anlegt, laufen diese
Tests automatisch und MÜSSEN bestehen — ein Phase-2-PR darf sie weder
löschen noch dauerhaft skippen.

Policy: docs/policy/backer-sandbox-guardrails.md -> paypal_env_fail_closed.
Anti-Pattern (OS-Referenz app.py:44): os.environ.get("PAYPAL_ENV", "sandbox")
— stiller Soft-Default ohne Assertion.
"""
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
def env_guard(monkeypatch):
    sys.path.insert(0, str(BACKER))
    try:
        import env_guard as eg
        yield eg
    finally:
        sys.path.remove(str(BACKER))


class TestPayPalEnvFailClosed:
    def test_unset_env_raises(self, env_guard, monkeypatch):
        monkeypatch.delenv("PAYPAL_ENV", raising=False)
        with pytest.raises(env_guard.PayPalEnvError):
            env_guard.require_paypal_env()

    def test_empty_env_raises(self, env_guard, monkeypatch):
        monkeypatch.setenv("PAYPAL_ENV", "")
        with pytest.raises(env_guard.PayPalEnvError):
            env_guard.require_paypal_env()

    def test_invalid_value_raises(self, env_guard, monkeypatch):
        monkeypatch.setenv("PAYPAL_ENV", "prod")
        with pytest.raises(env_guard.PayPalEnvError):
            env_guard.require_paypal_env()

    def test_sandbox_passes(self, env_guard, monkeypatch):
        monkeypatch.setenv("PAYPAL_ENV", "sandbox")
        assert env_guard.require_paypal_env() == "sandbox"

    def test_no_soft_default_in_app_source(self):
        # the OS anti-pattern must not be copied: no .get("PAYPAL_ENV", ...)
        app_src = (BACKER / "app.py").read_text(encoding="utf-8")
        assert 'get("PAYPAL_ENV",' not in app_src.replace("'", '"'), (
            "app.py re-introduces the soft-default anti-pattern (OS app.py:44)"
        )

    def test_invalid_env_never_reaches_requests_post(self, env_guard, monkeypatch):
        """No PayPal HTTP call may be attempted with an invalid PAYPAL_ENV."""
        monkeypatch.setenv("PAYPAL_ENV", "prod")
        sys.path.insert(0, str(BACKER))
        try:
            import paypal_client
            calls = []
            monkeypatch.setattr(
                paypal_client.requests, "post",
                lambda *a, **kw: calls.append(a) or pytest.fail("post reached"),
                raising=False,
            )
            with pytest.raises(Exception):
                paypal_client.create_order("test@example.com", 1.0)
            assert calls == []
        finally:
            sys.path.remove(str(BACKER))
