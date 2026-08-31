"""Phase C — SoM/Team Progress-Registry (Brain-seitig, in-memory).

Die Detached-SoM/Team-Runner laufen als eigene Host-Subprozesse und schreiben
ihren State nur lokal (state/runs/*.yaml) — der Brain-Container sieht das nicht
(kein Mount). Statt das tote Minibook wiederzubeleben: PUSH-Modell. Die Runner
POSTen Phasen-Fortschritt an POST /api/som/progress; diese Registry hält ihn
in-memory; GET /api/som/runs liefert das Dashboard.

Container-Boundary-sicher (Push statt Mount), kein neuer Dienst, überlebt die
Detached-Subprozesse. Thread-safe (mehrere Runner pushen parallel). Gecappt
(RAM-Schutz). now_fn injizierbar (deterministischer Test ohne Date.now).
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

# Status die als "aktiv" gelten (Run läuft noch) vs. terminal
_ACTIVE = {"planning", "executing", "validating", "needs_input", "awaiting_approval"}
_TERMINAL = {"ready", "failed", "cancelled", "needs_human", "done"}


class SomProgressRegistry:
    """In-memory Fortschritts-Register pro Run. run_id → {status, intent, source,
    created, updated, phases:[{status, at}]}."""

    def __init__(self, now_fn: Optional[Callable[[], float]] = None, max_runs: int = 100) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max = max_runs
        if now_fn is not None:
            self._now = now_fn
        else:
            import time
            self._now = time.time

    def record(self, run_id: Optional[str], status: str,
               intent: Optional[str] = None, source: Optional[str] = None) -> None:
        """Trägt eine Status-Transition ein (vom Runner gepusht). Leere run_id
        wird ignoriert. intent/source nur beim ersten Mal gesetzt (bleiben stabil)."""
        if not run_id or not isinstance(run_id, str):
            return
        now = self._now()
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                run = {"run_id": run_id, "intent": intent or "", "source": source or "",
                       "created": now, "updated": now, "status": status, "phases": []}
                self._runs[run_id] = run
            else:
                if intent and not run.get("intent"):
                    run["intent"] = intent
                if source and not run.get("source"):
                    run["source"] = source
            run["status"] = status
            run["updated"] = now
            run["phases"].append({"status": status, "at": now})
            self._cap_locked()

    def _cap_locked(self) -> None:
        """Hält die Registry auf max_runs (jüngste nach updated behalten)."""
        if len(self._runs) <= self._max:
            return
        ordered = sorted(self._runs.values(), key=lambda r: r["updated"], reverse=True)
        keep = {r["run_id"] for r in ordered[: self._max]}
        for rid in list(self._runs):
            if rid not in keep:
                del self._runs[rid]

    def snapshot(self) -> dict[str, Any]:
        """Dashboard: alle Runs + getrennt active/done, jüngste zuerst."""
        with self._lock:
            runs = sorted((dict(r) for r in self._runs.values()),
                          key=lambda r: r["updated"], reverse=True)
        active = [r for r in runs if r["status"] in _ACTIVE]
        done = [r for r in runs if r["status"] in _TERMINAL]
        return {"runs": runs, "active": active, "done": done,
                "n_active": len(active), "n_total": len(runs)}


# Modul-Singleton (vom Brain-Router + ggf. lokalem Push genutzt)
_REGISTRY: Optional[SomProgressRegistry] = None


def get_registry() -> SomProgressRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SomProgressRegistry()
    return _REGISTRY
