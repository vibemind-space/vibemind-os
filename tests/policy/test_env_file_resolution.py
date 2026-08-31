"""ENVFILE-4 [PHASE-2 ENFORCEMENT] — deterministische BACKER_ENV_FILE
(Guardrail 4).

Vorinstallierte Falle per POL-0 `test_activation_mechanism` (skipif-absent).
Ehrliche Einordnung (POL-0): das Sibling-Anti-Pattern (x-pathfinder/.env,
OS app.py:29-33) ist in V1 nicht exerzierbar — dieser Test ist eine Falle,
kein Bug-Beweis. Wird Phase-2-Code korrekt geschrieben, flippt er grün,
ohne den Fang je demonstriert zu haben.

Policy: docs/policy/backer-sandbox-guardrails.md -> deterministic_env_file.
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


class TestDeterministicEnvFile:
    def test_unset_backer_env_file_raises(self, env_guard, monkeypatch):
        monkeypatch.delenv("BACKER_ENV_FILE", raising=False)
        with pytest.raises(Exception):
            env_guard.load_backer_env()

    def test_missing_file_raises(self, env_guard, monkeypatch, tmp_path):
        monkeypatch.setenv("BACKER_ENV_FILE", str(tmp_path / "nope.env"))
        with pytest.raises(Exception):
            env_guard.load_backer_env()

    def test_explicit_file_is_the_only_source(self, env_guard, monkeypatch, tmp_path):
        env_file = tmp_path / "backer.env"
        env_file.write_text("PAYPAL_ENV=sandbox\n", encoding="utf-8")
        monkeypatch.setenv("BACKER_ENV_FILE", str(env_file))
        monkeypatch.delenv("PAYPAL_ENV", raising=False)
        env_guard.load_backer_env()
        import os
        assert os.environ.get("PAYPAL_ENV") == "sandbox"

    def test_no_walkup_or_sibling_fallback_in_source(self):
        """The OS 4-way resolution chain must not be copied: no
        find_dotenv(usecwd=True), no x-pathfinder sibling fallback."""
        app_src = (BACKER / "app.py").read_text(encoding="utf-8")
        assert "find_dotenv" not in app_src, (
            "app.py re-introduces find_dotenv walk-up (OS app.py:29-33)")
        assert "x-pathfinder" not in app_src, (
            "app.py re-introduces the x-pathfinder/.env sibling fallback")
