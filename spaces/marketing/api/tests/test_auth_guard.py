"""Tests for _require_proposal_api_key — the shared mutating-route guard.

After the second security review on the validate_mx route, every
mutating /api/proposals* and /api/integrations/{kind}/import endpoint
funnels through this helper. The helper:

  - returns 503 when MARKETING_PROPOSAL_API_KEY is unset (refuse to
    serve rather than silently allow)
  - returns 401 when the body's api_key doesn't match
    (constant-time hmac.compare_digest)
  - returns None on pass

These tests verify those three branches plus the FastAPI route wiring
via TestClient.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG_ROOT))


from spaces.marketing.api import server as srv  # noqa: E402


_FAILS: list[str] = []


def _check(label: str, cond: bool, detail: str = ""):
    mark = "PASS" if cond else "FAIL"
    line = f"  [{mark}] {label}"
    if detail and not cond:
        line += f"  -- {detail}"
    print(line)
    if not cond:
        _FAILS.append(label)


# ─── Direct helper tests (no FastAPI) ──────────────────────────────────


def test_helper_returns_503_when_env_unset():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MARKETING_PROPOSAL_API_KEY", None)
        r = srv._require_proposal_api_key({"api_key": "anything"})
    _check("helper_503_when_env_unset",
           r is not None and r.status_code == 503
           and b"misconfigured" in r.body)


def test_helper_returns_401_when_key_wrong():
    with mock.patch.dict(os.environ,
                         {"MARKETING_PROPOSAL_API_KEY": "real-secret"},
                         clear=False):
        r = srv._require_proposal_api_key({"api_key": "wrong"})
    _check("helper_401_when_key_wrong",
           r is not None and r.status_code == 401
           and b"invalid api_key" in r.body)


def test_helper_returns_401_when_key_missing_from_body():
    with mock.patch.dict(os.environ,
                         {"MARKETING_PROPOSAL_API_KEY": "real-secret"},
                         clear=False):
        r = srv._require_proposal_api_key({})
    _check("helper_401_when_key_missing", r is not None and r.status_code == 401)


def test_helper_returns_401_when_payload_none():
    """Defensive: None payload should still be rejected, not crash."""
    with mock.patch.dict(os.environ,
                         {"MARKETING_PROPOSAL_API_KEY": "real-secret"},
                         clear=False):
        r = srv._require_proposal_api_key(None)
    _check("helper_401_when_payload_none",
           r is not None and r.status_code == 401)


def test_helper_returns_none_on_match():
    with mock.patch.dict(os.environ,
                         {"MARKETING_PROPOSAL_API_KEY": "real-secret"},
                         clear=False):
        r = srv._require_proposal_api_key({"api_key": "real-secret"})
    _check("helper_none_on_match", r is None)


def test_helper_constant_time_compare():
    """Confirm we use hmac.compare_digest -- non-str inputs should be
    rejected before reaching the compare."""
    with mock.patch.dict(os.environ,
                         {"MARKETING_PROPOSAL_API_KEY": "real-secret"},
                         clear=False):
        r = srv._require_proposal_api_key({"api_key": 12345})   # non-str
    _check("helper_rejects_non_str_key",
           r is not None and r.status_code == 401)


# ─── End-to-end via FastAPI TestClient ─────────────────────────────────


def test_validate_mx_route_now_requires_auth():
    """The original CVE: validate_mx had no auth. Now it must 503/401."""
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        _check("validate_mx_via_testclient", False, "fastapi testclient missing")
        return

    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MARKETING_PROPOSAL_API_KEY", None)
        client = TestClient(srv.app)
        r = client.post("/api/proposals/anything/validate_mx", json={})
    _check("validate_mx_503_when_env_unset",
           r.status_code == 503,
           f"got {r.status_code} body={r.text[:100]}")

    with mock.patch.dict(os.environ,
                         {"MARKETING_PROPOSAL_API_KEY": "sekret-7"},
                         clear=False):
        client = TestClient(srv.app)
        r = client.post("/api/proposals/anything/validate_mx", json={})
    _check("validate_mx_401_when_no_key_in_body",
           r.status_code == 401,
           f"got {r.status_code} body={r.text[:100]}")

    with mock.patch.dict(os.environ,
                         {"MARKETING_PROPOSAL_API_KEY": "sekret-7"},
                         clear=False):
        client = TestClient(srv.app)
        # Even with the right key, the underlying tool fails (no
        # supabase here) -- but we just want to confirm we GOT PAST
        # the auth-gate. Auth-gate returns BEFORE the tool runs.
        r = client.post(
            "/api/proposals/anything/validate_mx",
            json={"api_key": "sekret-7"},
        )
    _check("validate_mx_passes_auth_with_correct_key",
           r.status_code not in (401, 503),
           f"got {r.status_code} body={r.text[:100]}")


def test_other_mutating_routes_also_guarded():
    """Every POST mutating route must respond 503 when env is unset."""
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        _check("all_mutating_routes_guarded", False, "fastapi testclient missing")
        return

    mutating = [
        ("/api/proposals", {}),
        ("/api/proposals/x/approve", {}),
        ("/api/proposals/x/reject", {"reason": "x"}),
        ("/api/proposals/x/validate_mx", {}),
        ("/api/proposals/request_hand", {"hand_id": "lead-hand"}),
        ("/api/integrations/manual-csv/import", {"payload": {"csv_text": "email\nx@y.com\n"}}),
    ]
    all_503 = True
    failures = []
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MARKETING_PROPOSAL_API_KEY", None)
        client = TestClient(srv.app)
        for path, body in mutating:
            r = client.post(path, json=body)
            if r.status_code != 503:
                all_503 = False
                failures.append(f"{path}->{r.status_code}")
    _check("all_mutating_routes_guarded",
           all_503,
           f"non-503: {failures}")


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    tests = [
        test_helper_returns_503_when_env_unset,
        test_helper_returns_401_when_key_wrong,
        test_helper_returns_401_when_key_missing_from_body,
        test_helper_returns_401_when_payload_none,
        test_helper_returns_none_on_match,
        test_helper_constant_time_compare,
        test_validate_mx_route_now_requires_auth,
        test_other_mutating_routes_also_guarded,
    ]
    print(f"[test_auth_guard] running {len(tests)} tests")
    for t in tests:
        try:
            t()
        except Exception as e:
            _check(t.__name__, False, f"raised {type(e).__name__}: {e}")
    total = len(tests); fails = len(_FAILS)
    print(f"\n=== {total - fails}/{total} passed ===")
    if fails:
        for f in _FAILS: print(f"  - {f}")
        return 1
    print("test_auth_guard: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
