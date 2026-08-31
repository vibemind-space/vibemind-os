"""World Observer — ground-truth post-condition checks (Baustein D.1).

The validation that exists today (capability_validator) only inspects what a
tool *claims* it returned. This module checks what the *world* actually looks
like after an action: is the process running, is the port open, does the file
exist, does the HTTP endpoint respond. That observed signal is the honest
ground truth behind "action_verified".

Design rules:
  - **Fail-safe**: an observer error NEVER counts as an action failure. If we
    cannot observe, we return UNVERIFIED (not FAILURE) — the action's own
    claimed outcome stands, we just couldn't confirm it.
  - **Flag-gated**: does nothing unless GROUND_TRUTH_ENABLED. Default OFF, so
    the live Brain is unchanged.
  - **Declarative**: a capability declares its post-condition in YAML, e.g.
        postcondition: { check: process_running, name: chrome }
        postcondition: { check: port_open, port: 9223 }
        postcondition: { check: file_exists, path: /tmp/out.json }
        postcondition: { check: http_ok, url: http://127.0.0.1:4200/health }
  - **No hard deps**: psutil/requests imported lazily; absence → UNVERIFIED.

Returns a `Verification` with verdict in {VERIFIED, UNVERIFIED, REFUTED}:
  VERIFIED  — world confirms the action took effect
  REFUTED   — world contradicts the claim (e.g. process not found)
  UNVERIFIED — could not observe (no check declared, observer error, missing dep)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


GROUND_TRUTH_ENABLED = _flag("GROUND_TRUTH_ENABLED")
# Network/probe timeout (seconds) — kept short so we never block a hot path.
OBSERVE_TIMEOUT = float(os.environ.get("GROUND_TRUTH_TIMEOUT", "2.0"))


# ── Verdict ────────────────────────────────────────────────────────────

VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"
REFUTED = "REFUTED"


@dataclass
class Verification:
    """Result of a ground-truth observation."""
    verdict: str = UNVERIFIED          # VERIFIED | UNVERIFIED | REFUTED
    check: str = ""                    # which check ran
    signal: Dict[str, Any] = field(default_factory=dict)  # observed facts
    reason: str = ""
    latency_ms: float = 0.0

    @property
    def verified_ok(self) -> Optional[bool]:
        """True/False if conclusive, None if unverified."""
        if self.verdict == VERIFIED:
            return True
        if self.verdict == REFUTED:
            return False
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "check": self.check,
            "signal": self.signal,
            "reason": self.reason,
            "latency_ms": round(self.latency_ms, 2),
        }


# ── Individual checks (each returns (ok: Optional[bool], signal, reason)) ──

def _check_process_running(spec: Dict[str, Any]):
    name = (spec.get("name") or "").lower()
    if not name:
        return None, {}, "no process name given"
    try:
        import psutil  # lazy
    except Exception:
        return None, {}, "psutil not available"
    found = []
    for p in psutil.process_iter(["name"]):
        try:
            pn = (p.info.get("name") or "").lower()
            if name in pn:
                found.append(pn)
        except Exception:
            continue
    if found:
        return True, {"process": name, "matches": found[:5]}, f"process running: {found[0]}"
    return False, {"process": name}, "process not found"


def _check_port_open(spec: Dict[str, Any]):
    port = spec.get("port")
    host = spec.get("host", "127.0.0.1")
    if not port:
        return None, {}, "no port given"
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(OBSERVE_TIMEOUT)
    try:
        rc = s.connect_ex((host, int(port)))
        if rc == 0:
            return True, {"host": host, "port": port}, f"port {port} open"
        return False, {"host": host, "port": port, "rc": rc}, f"port {port} closed (rc={rc})"
    except Exception as e:
        return None, {"host": host, "port": port}, f"port probe error: {e}"
    finally:
        try:
            s.close()
        except Exception:
            pass


def _check_file_exists(spec: Dict[str, Any]):
    path = spec.get("path")
    if not path:
        return None, {}, "no path given"
    try:
        exists = os.path.exists(path)
        if exists:
            sz = os.path.getsize(path) if os.path.isfile(path) else None
            return True, {"path": path, "size": sz}, "file exists"
        return False, {"path": path}, "file missing"
    except Exception as e:
        return None, {"path": path}, f"stat error: {e}"


def _check_http_ok(spec: Dict[str, Any]):
    url = spec.get("url")
    if not url:
        return None, {}, "no url given"
    expect_lt = int(spec.get("expect_status_lt", 400))
    try:
        import requests  # lazy
    except Exception:
        return None, {}, "requests not available"
    try:
        r = requests.get(url, timeout=OBSERVE_TIMEOUT)
        ok = r.status_code < expect_lt
        return ok, {"url": url, "status_code": r.status_code}, f"http {r.status_code}"
    except Exception as e:
        return None, {"url": url}, f"http probe error: {e}"


def _check_supabase_row(spec: Dict[str, Any]):
    """Ground-truth for supabase ops via an INDEPENDENT re-query (Baustein D.1).

    Instead of trusting the op's self-reported result, ask supabase directly
    whether the expected end-state holds. spec:
        {check: supabase_row, table: ideas, match: "id=eq.<x>", expect: present}
        {check: supabase_row, table: ideas, match: "title=eq.<x>", expect: absent}
    `match` is a PostgREST filter; `expect` ∈ {present, absent}. Returns
    (ok|None, signal, reason). Observer/transport errors → None (UNVERIFIED,
    fail-safe — a probe failure must never fail the action itself)."""
    table = (spec.get("table") or "ideas").strip()
    match = (spec.get("match") or "").strip()
    expect = (spec.get("expect") or "present").lower()
    if not match:
        return None, {}, "no match filter (nothing to re-query)"
    base = os.environ.get("SUPABASE_URL", "http://192.168.178.65:54321").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "anon")
    try:
        import requests  # lazy
    except Exception:
        return None, {}, "requests not available"
    try:
        r = requests.get(
            f"{base}/rest/v1/{table}?{match}&select=id&limit=1",
            headers={"apikey": key}, timeout=OBSERVE_TIMEOUT,
        )
        if r.status_code >= 400:
            return None, {"status_code": r.status_code}, f"supabase re-query {r.status_code}"
        rows = r.json() if r.content else []
        present = isinstance(rows, list) and len(rows) > 0
        ok = present if expect == "present" else (not present)
        return ok, {
            "table": table, "match": match, "expect": expect,
            "rows_found": len(rows) if isinstance(rows, list) else 0,
        }, f"supabase: {'row present' if present else 'row absent'} (expected {expect})"
    except Exception as e:  # fail-safe
        return None, {"match": match}, f"supabase probe error: {e}"


def _check_supabase_edge(spec: Dict[str, Any]):
    """Ground-truth for idea connect/disconnect — resolve the two node TITLES to ids,
    then check whether an edge exists between them (bidirectional). spec:
        {check: supabase_edge, title_a: X, title_b: Y, expect: present|absent}
    A missing endpoint / transport error → None (UNVERIFIED, fail-safe)."""
    title_a = (spec.get("title_a") or "").strip()
    title_b = (spec.get("title_b") or "").strip()
    expect = (spec.get("expect") or "present").lower()
    if not title_a or not title_b:
        return None, {}, "missing edge endpoints (cannot verify)"
    base = os.environ.get("SUPABASE_URL", "http://192.168.178.65:54321").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "anon")
    try:
        import requests  # lazy
        import urllib.parse as _u
    except Exception:
        return None, {}, "requests not available"
    hdr = {"apikey": key}

    def _node_id(title):
        r = requests.get(
            f"{base}/rest/v1/canvas_nodes?title=eq.{_u.quote(title)}&select=id&limit=1",
            headers=hdr, timeout=OBSERVE_TIMEOUT)
        rows = r.json() if (r.status_code < 400 and r.content) else []
        return rows[0]["id"] if rows else None

    try:
        a, b = _node_id(title_a), _node_id(title_b)
        if not a or not b:
            return None, {"id_a": a, "id_b": b}, "edge endpoint node not found (cannot verify)"
        flt = (f"or=(and(from_node_id.eq.{a},to_node_id.eq.{b}),"
               f"and(from_node_id.eq.{b},to_node_id.eq.{a}))")
        r = requests.get(f"{base}/rest/v1/canvas_edges?{flt}&select=id&limit=1",
                         headers=hdr, timeout=OBSERVE_TIMEOUT)
        if r.status_code >= 400:
            return None, {"status_code": r.status_code}, f"edge re-query {r.status_code}"
        rows = r.json() if r.content else []
        present = isinstance(rows, list) and len(rows) > 0
        ok = present if expect == "present" else (not present)
        return ok, {
            "title_a": title_a, "title_b": title_b, "expect": expect,
            "edges_found": len(rows) if isinstance(rows, list) else 0,
        }, f"supabase: edge {'present' if present else 'absent'} (expected {expect})"
    except Exception as e:  # fail-safe
        return None, {"a": title_a, "b": title_b}, f"edge probe error: {e}"


def _check_supabase_node_in_bubble(spec: Dict[str, Any]):
    """Ground-truth for idea_move — confirm the node is now under the target bubble.
    Resolve the bubble TITLE to its id (ideas row), then check canvas_nodes for the
    node under that bubble_id. spec:
        {check: supabase_node_in_bubble, node_title: X, bubble_title: Y, expect: present}
    Unresolved bubble / transport error → None (UNVERIFIED, fail-safe)."""
    node_title = (spec.get("node_title") or "").strip()
    bubble_title = (spec.get("bubble_title") or "").strip()
    expect = (spec.get("expect") or "present").lower()
    if not node_title or not bubble_title:
        return None, {}, "missing node/bubble (cannot verify)"
    base = os.environ.get("SUPABASE_URL", "http://192.168.178.65:54321").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "anon")
    try:
        import requests  # lazy
        import urllib.parse as _u
    except Exception:
        return None, {}, "requests not available"
    hdr = {"apikey": key}
    try:
        r = requests.get(
            f"{base}/rest/v1/ideas?title=eq.{_u.quote(bubble_title)}&select=id&limit=1",
            headers=hdr, timeout=OBSERVE_TIMEOUT)
        brows = r.json() if (r.status_code < 400 and r.content) else []
        if not brows:
            return None, {"bubble": bubble_title}, "target bubble not found (cannot verify)"
        bid = brows[0]["id"]
        # canvas_nodes link to their bubble via linked_idea_id (the bubble is an
        # ideas row); confirmed against the live schema 2026-06-24.
        r2 = requests.get(
            f"{base}/rest/v1/canvas_nodes?title=eq.{_u.quote(node_title)}"
            f"&linked_idea_id=eq.{bid}&select=id&limit=1",
            headers=hdr, timeout=OBSERVE_TIMEOUT)
        if r2.status_code >= 400:
            return None, {"status_code": r2.status_code}, f"node re-query {r2.status_code}"
        rows = r2.json() if r2.content else []
        present = isinstance(rows, list) and len(rows) > 0
        ok = present if expect == "present" else (not present)
        return ok, {
            "node": node_title, "bubble": bubble_title, "expect": expect,
            "found": len(rows) if isinstance(rows, list) else 0,
        }, f"supabase: node {'in' if present else 'not in'} bubble (expected {expect})"
    except Exception as e:  # fail-safe
        return None, {"node": node_title, "bubble": bubble_title}, f"node-in-bubble probe error: {e}"


# Map of check-name → fn. To add a check, add one function above + an entry here.
_CHECKS = {
    "process_running": _check_process_running,
    "port_open": _check_port_open,
    "file_exists": _check_file_exists,
    "http_ok": _check_http_ok,
    "supabase_row": _check_supabase_row,
    "supabase_edge": _check_supabase_edge,
    "supabase_node_in_bubble": _check_supabase_node_in_bubble,
}


def available_checks() -> list:
    return sorted(_CHECKS.keys())


def observe(postcondition: Optional[Dict[str, Any]]) -> Verification:
    """Run a declared post-condition check against the real world.

    `postcondition` is a dict like {check: process_running, name: chrome}.
    Returns a Verification; never raises.
    """
    t0 = time.time()
    if not GROUND_TRUTH_ENABLED:
        return Verification(verdict=UNVERIFIED, reason="GROUND_TRUTH_ENABLED off")
    if not postcondition or not isinstance(postcondition, dict):
        return Verification(verdict=UNVERIFIED, reason="no postcondition declared")
    check = postcondition.get("check") or ""
    fn = _CHECKS.get(check)
    if fn is None:
        return Verification(verdict=UNVERIFIED, check=check,
                            reason=f"unknown check '{check}'")
    try:
        ok, signal, reason = fn(postcondition)
    except Exception as e:  # fail-safe: observer error ≠ action failure
        logger.debug("[world_observer] check %s errored: %s", check, e)
        return Verification(verdict=UNVERIFIED, check=check,
                            reason=f"observer error: {e}",
                            latency_ms=(time.time() - t0) * 1000)
    dt = (time.time() - t0) * 1000
    if ok is True:
        return Verification(verdict=VERIFIED, check=check, signal=signal,
                            reason=reason, latency_ms=dt)
    if ok is False:
        return Verification(verdict=REFUTED, check=check, signal=signal,
                            reason=reason, latency_ms=dt)
    return Verification(verdict=UNVERIFIED, check=check, signal=signal,
                        reason=reason, latency_ms=dt)
