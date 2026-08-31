"""IMPORT-2 [PHASE-0 authored / PHASE-2 target] — Live-Transport-Import-Ban
(Guardrail 2, Zero-Send-Fundament).

Mechanismus per POL-0 `test_activation_mechanism`: xfail(strict=True).
Heute failt der Discovery-Assert (distribute.py existiert nicht) -> XFAIL,
Suite bleibt grün. Landet Phase-2-`distribute.py` UND der Scan ist sauber ->
XPASS -> strict=True macht daraus einen lauten Fehler -> der Marker wird im
Phase-2-PR entfernt und der Test wird permanenter CI-Gate.

Policy: docs/policy/backer-sandbox-guardrails.md -> live_transport_import_ban.
"""
import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# banned live-transport roots on the SANDBOX distribution path
BANNED = {"requests", "smtplib", "http", "socket", "paypal"}

# where Phase-2 distribution code may land (backer-checkout/ itself is the
# quarantined payment code and deliberately NOT scanned — allowlist per POL-0)
CANDIDATE_PATTERNS = (
    "spaces/**/distribute.py",
    "backer_sandbox/**/*.py",
    "backer-checkout/distribute.py",  # dry-run distribution MUST be file-only
)


def _candidates() -> list[Path]:
    found: list[Path] = []
    for pat in CANDIDATE_PATTERNS:
        found.extend(REPO_ROOT.glob(pat))
    return sorted(set(found))


def _banned_imports(path: Path) -> list[tuple[str, str]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    offenders: list[tuple[str, str]] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [(str(path), "<unparseable>")]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        offenders.extend((str(path), n) for n in names if n in BANNED)
    # belt-and-braces raw scan for dynamic imports
    for tok in BANNED:
        if re.search(rf"__import__\(\s*['\"]{tok}", src) or re.search(
            rf"importlib\.import_module\(\s*['\"]{tok}", src
        ):
            offenders.append((str(path), f"dynamic:{tok}"))
    return offenders


@pytest.mark.xfail(
    strict=True,
    reason="Phase-2 — distribute.py absent; XPASS erzwingt Marker-Entfernung (POL-0)",
)
def test_no_live_transport_in_sandbox():
    candidates = _candidates()
    # Discovery-Assert: today RED (nothing built) -> XFAIL keeps suite green
    assert candidates, (
        "no sandbox distribution code found yet (Phase 2 not landed) — "
        f"patterns: {CANDIDATE_PATTERNS}"
    )
    offenders = [o for p in candidates for o in _banned_imports(p)]
    assert not offenders, (
        f"live-transport symbols on the sandbox distribution path: {offenders} "
        "— Zero-Send guardrail violated (POL-0 Guardrail 2)"
    )
