"""File-backed navigator state: current space + history stack.

State lives next to the MCP server so per-repo-clone isolation works
(no global ~/.vibemind/ collision when multiple checkouts run side-by-side).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_STATE_FILE = Path(__file__).resolve().parent / "state.json"
_HISTORY_MAX = 20

_DEFAULT_SPACE = "ideas"


def _load() -> Dict[str, Any]:
    if not _STATE_FILE.exists():
        return {
            "current": _DEFAULT_SPACE,
            "since": time.time(),
            "history": [],
            "visit_counts": {},
        }
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "current": _DEFAULT_SPACE,
            "since": time.time(),
            "history": [],
            "visit_counts": {},
        }


def _save(state: Dict[str, Any]) -> None:
    try:
        _STATE_FILE.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def current() -> Dict[str, Any]:
    s = _load()
    return {
        "space": s.get("current", _DEFAULT_SPACE),
        "since": s.get("since", time.time()),
        "history": s.get("history", [])[-10:],
    }


def goto(space_id: str) -> Dict[str, Any]:
    s = _load()
    prev = s.get("current", _DEFAULT_SPACE)
    if prev != space_id:
        hist: List[Dict[str, Any]] = s.get("history", [])
        hist.append({"space": prev, "left_at": time.time()})
        if len(hist) > _HISTORY_MAX:
            hist = hist[-_HISTORY_MAX:]
        s["history"] = hist
    counts: Dict[str, int] = s.get("visit_counts", {})
    counts[space_id] = counts.get(space_id, 0) + 1
    s["visit_counts"] = counts
    s["current"] = space_id
    s["since"] = time.time()
    _save(s)
    return {"space": space_id, "previous": prev}


def back() -> Optional[str]:
    """Pop history → return space-id to navigate to, or None if empty."""
    s = _load()
    hist: List[Dict[str, Any]] = s.get("history", [])
    if not hist:
        return None
    last = hist.pop()
    s["history"] = hist
    _save(s)
    return last.get("space")


def recent(limit: int = 5) -> List[Dict[str, Any]]:
    """Return spaces sorted by visit-count (descending)."""
    s = _load()
    counts: Dict[str, int] = s.get("visit_counts", {})
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [{"space": sid, "visits": n} for sid, n in ranked[:limit]]


def history(limit: int = 10) -> List[Dict[str, Any]]:
    s = _load()
    return s.get("history", [])[-limit:]
