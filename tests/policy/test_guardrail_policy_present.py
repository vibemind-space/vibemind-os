"""POL-0 (Phase 0) — the guardrail policy doc exists and covers all 6 anchors.

RED against today's tree: `docs/policy/backer-sandbox-guardrails.md` does not
exist -> existence assert fails.

GREEN after POL-0: doc present with all six policy anchors. This is the ONLY
WS4 test that is actively GREEN in Phase 0 — the enforcement tests
(ENV-1/IDEM-3/ENVFILE-4/PORT-5, IMPORT-2) are authored later as neutralized
traps (skipif-absent / xfail-strict) per the activation mechanism this doc
must define.
"""
from pathlib import Path

# policy -> tests -> vibemind-os
REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "policy" / "backer-sandbox-guardrails.md"

ANCHORS = [
    "paypal_env_fail_closed",
    "live_transport_import_ban",
    "idempotency_ledger_caps",
    "deterministic_env_file",
    "port_collision",
    "test_activation_mechanism",
]


def test_guardrail_policy_present():
    assert DOC.exists(), f"guardrail policy doc missing: {DOC}"
    text = DOC.read_text(encoding="utf-8")
    missing = [a for a in ANCHORS if a not in text]
    assert not missing, f"policy anchors missing from {DOC.name}: {missing}"
