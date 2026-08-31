"""PORT-5 [PHASE-2 ENFORCEMENT] — Payment-App kollidiert nie mit Brain-Port
(Guardrail 5).

Vorinstallierte Falle per POL-0 `test_activation_mechanism` (skipif-absent).
Policy: docs/policy/backer-sandbox-guardrails.md -> port_collision.
Anti-Pattern (OS-Referenz): OS app.py:95 Flask-Default PORT=5000 kollidiert
mit BrainShadowObserver-Default localhost:5000 (brain_shadow.py:31).
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


class TestPortCollision:
    def test_default_port_is_not_5000(self, env_guard, monkeypatch):
        monkeypatch.delenv("PORT", raising=False)
        assert env_guard.resolve_payment_port() != 5000, (
            "payment default port collides with brain :5000 (POL-0: 5055)")

    def test_same_host_port_as_brain_raises(self, env_guard, monkeypatch):
        monkeypatch.setenv("PORT", "5000")
        with pytest.raises(env_guard.PortCollisionError):
            env_guard.assert_no_port_collision(
                payment=("localhost", 5000), brain=("localhost", 5000),
            )

    def test_distinct_ports_pass(self, env_guard):
        env_guard.assert_no_port_collision(
            payment=("localhost", 5055), brain=("localhost", 5000),
        )
