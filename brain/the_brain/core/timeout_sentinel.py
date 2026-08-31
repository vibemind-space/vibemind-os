"""C2 — Timeout-Sentinel.

Turns capability/hop **timeouts** into ONE GitHub issue per capability, resiliently.

WHY OpenFang-free: a timeout is often OpenFang itself being down. Filing the issue
*through* an OpenFang agent (C1 gap-filer) would then also fail. So C2 is mechanical
and files **directly** via the issue-detector functions (which the brain can import
in-process; `push_to_github` shells out to `gh` — no OpenFang, no MCP transport).

STORM CONTROL (two independent layers, so a dead service can't flood issues):
  1. Frequency gate (here): only file once a capability has timed out >= THRESHOLD
     times within WINDOW seconds — a single transient timeout is ignored.
  2. Hash dedup (issue-detector): the title is **capability-only**
     ("Capability timeout: <cap>") so sha256(category:title) is stable per capability
     -> an already-open issue is never re-filed.

Flag: CAPABILITY_TIMEOUT_ISSUE_ENABLED (default OFF -> every entry point is a no-op).
Fail-safe: any internal error returns a result dict, never raises into the executor.

Integration (separate step): plan_executor's hop-failure path calls `on_hop_timeout(...)`
with the error string + context; detection (`is_timeout`) and frequency counting live here.
"""

from __future__ import annotations

import os
import time
import logging
import threading
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("brain.timeout_sentinel")

# In-memory sliding window of recent timeouts per capability — the DETERMINISTIC
# storm-control gate (no Qdrant dependency, no flush-delay, no semantic-search
# fuzziness). Resets on restart, which is fine: storm control is about a burst.
_history: Dict[str, List[float]] = {}
_hist_lock = threading.Lock()


def _record_and_count(capability: str, window_s: int) -> int:
    """Append 'now' for this capability, prune outside the window, return the count."""
    now = time.time()
    with _hist_lock:
        hist = [t for t in _history.get(capability, []) if now - t <= window_s]
        hist.append(now)
        _history[capability] = hist
        return len(hist)

# ── Flags / tunables ──────────────────────────────────────────────────────────
ENABLED = os.environ.get("CAPABILITY_TIMEOUT_ISSUE_ENABLED", "0") == "1"
THRESHOLD = int(os.environ.get("CAPABILITY_TIMEOUT_THRESHOLD", "3"))
WINDOW_S = int(os.environ.get("CAPABILITY_TIMEOUT_WINDOW_S", "600"))
DEFAULT_REPO = os.environ.get("ISSUE_DETECTOR_REPO", "")
# dry_run defaults TRUE while the component is being built/validated; flip via env.
DEFAULT_DRY_RUN = os.environ.get("CAPABILITY_TIMEOUT_DRY_RUN", "1") == "1"

CATEGORY = "capability-timeout"

# Substrings (lowercased) that mark a failure as a timeout / unreachable target.
# OpenFangUnavailable conflates timeout + 5xx, but for C2 the effect is identical:
# the capability produced no verified result because the target was slow/dead.
_TIMEOUT_SIGNATURES = (
    "timeout",
    "timed out",
    "timeouterror",
    "readtimeout",
    "connecttimeout",
    "openfangunavailable",
    "unreachable",
)


def is_timeout(error: Optional[str]) -> bool:
    """True if an executor error string looks like a timeout / unreachable target."""
    if not error:
        return False
    e = str(error).lower()
    return any(sig in e for sig in _TIMEOUT_SIGNATURES)


def build_finding(
    capability: str,
    *,
    intent: str = "",
    target: str = "",
    trace_id: str = "",
    elapsed_s: float = 0.0,
    error: str = "",
) -> dict:
    """Build the issue-detector finding for a capability timeout.

    The TITLE is capability-only on purpose: that is what drives the dedup hash, so
    every occurrence of the same capability maps to ONE issue. All volatile context
    (trace_id, elapsed, error) goes into `details`, which does NOT affect the hash.
    """
    return {
        "severity": "HIGH",
        "title": f"Capability timeout: {capability}",
        "category": CATEGORY,
        "source": "TimeoutSentinel",
        "details": (
            f"Capability `{capability}` timed out / target unreachable — no verified "
            f"world-change (D: UNVERIFIED).\n"
            f"- intent: {intent or 'n/a'}\n"
            f"- execution_target: {target or 'n/a'}\n"
            f"- elapsed_s: {round(float(elapsed_s or 0.0), 1)}\n"
            f"- error: {str(error)[:200] or 'n/a'}\n"
            f"- recent trace: {trace_id or 'n/a'}\n\n"
            f"Filed by C2 Timeout-Sentinel after >= {THRESHOLD} timeouts within "
            f"{WINDOW_S}s. A coder agent can pick this up to add a fallback / raise the "
            f"timeout / fix the target."
        ),
    }


def _load_issue_detector():
    """Lazy-load the issue-detector module by path (no MCP transport, no OpenFang)."""
    import importlib.util

    here = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.normpath(
        os.path.join(here, "..", "..", "..", "issue-detector", "mcp_server.py")
    )
    path = os.environ.get("ISSUE_DETECTOR_PATH", default_path)
    spec = importlib.util.spec_from_file_location("vibemind_issue_detector", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"issue-detector not found at {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def _unwrap(t):  # FastMCP may wrap @mcp.tool() functions
        return getattr(t, "fn", t)

    return _unwrap(mod.findings_to_issues), _unwrap(mod.push_to_github)


def on_hop_timeout(
    capability: str,
    *,
    intent: str = "",
    target: str = "",
    trace_id: str = "",
    elapsed_s: float = 0.0,
    error: str = "",
    recent_count: Optional[int] = None,
    count_fn: Optional[Callable[[str], int]] = None,
    dry_run: Optional[bool] = None,
    repo: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> dict:
    """Entry point — called when a hop failed with a timeout-class error.

    Frequency gate -> build finding -> findings_to_issues -> push_to_github (gh).
    `recent_count` (or `count_fn(capability)`) is the number of recent timeouts for
    this capability within WINDOW_S; injected so this stays testable without a live
    execution_log. Returns a result dict; never raises.
    """
    on = ENABLED if enabled is None else enabled
    if not on:
        return {"skipped": "disabled"}
    dry = DEFAULT_DRY_RUN if dry_run is None else dry_run
    try:
        n = recent_count
        if n is None and count_fn is not None:
            n = int(count_fn(capability))
        if n is None:
            n = _record_and_count(capability, WINDOW_S)  # deterministic in-memory window
        logger.info("[timeout-sentinel] gate cap=%s recent=%s threshold=%s",
                    capability, n, THRESHOLD)
        if n < THRESHOLD:
            return {"skipped": "below_threshold", "recent": n, "threshold": THRESHOLD}

        finding = build_finding(
            capability, intent=intent, target=target, trace_id=trace_id,
            elapsed_s=elapsed_s, error=error,
        )
        findings_to_issues, push_to_github = _load_issue_detector()
        drafts = findings_to_issues([finding])["drafts"]
        result = push_to_github(drafts, repo=(repo or DEFAULT_REPO), dry_run=dry)
        logger.info(
            "[timeout-sentinel] capability=%s recent=%s dry_run=%s -> created=%s skipped_dedup=%s",
            capability, n, dry, len(result.get("created", [])),
            len(result.get("skipped_dedup", [])),
        )
        return {"filed": True, "dry_run": dry, "recent": n, "result": result,
                "hash": drafts[0]["hash"]}
    except Exception as exc:  # fail-safe — a filing error must never break execution
        logger.warning("[timeout-sentinel] filing failed: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def count_recent_timeouts(exec_log, capability: str, window_s: int = WINDOW_S) -> int:
    """Optional helper: count recent timeout exec-steps for a capability via D.2.

    Built on ExecutionLog.search; tolerant if execution_log/Qdrant is unavailable
    (returns 0 -> the gate then suppresses, which is the safe direction).
    """
    try:
        hits = exec_log.search("timeout", limit=50) or []
        import time as _t
        now = _t.time()
        n = 0
        for h in hits:
            pl = h.get("payload", h) if isinstance(h, dict) else {}
            if pl.get("capability") != capability:
                continue
            if not is_timeout(pl.get("reason") or pl.get("content")):
                continue
            ts = pl.get("created_at")
            if ts is None or (now - float(ts)) <= window_s:
                n += 1
        return n
    except Exception as exc:
        logger.debug("[timeout-sentinel] count failed: %s", exc)
        return 0
