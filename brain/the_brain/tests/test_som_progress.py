"""Phase C — Tests für die SoM-Progress-Registry (Brain-Endpoint-Kern).

Die Detached-SoM/Team-Runner POSTen Phasen-Fortschritt an den Brain
(POST /api/som/progress); GET /api/som/runs liest das Dashboard. Container-
Boundary-sicher (Push statt Mount). Getestet wird die reine Registry-Logik
(record/snapshot/Capping), nicht der HTTP-Layer.

Aufruf:
    voice/.venv312/Scripts/python brain/the_brain/tests/test_som_progress.py
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_BRAIN = Path(__file__).resolve().parents[1]
if str(_BRAIN) not in sys.path:
    sys.path.insert(0, str(_BRAIN))

_spec = importlib.util.spec_from_file_location(
    "som_progress", _BRAIN / "core" / "som_progress.py")
_sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sp)

_passed: list[str] = []
_failed: list[str] = []


def check(name, cond):
    (_passed if cond else _failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def _fresh():
    return _sp.SomProgressRegistry(now_fn=_clock())


_t = {"v": 1000.0}
def _clock():
    def now():
        _t["v"] += 1.0
        return _t["v"]
    return now


# ── Test 1: record legt einen Run an + Phasen-Historie ────────────────────────
def test_record_creates_run():
    print("Test 1: record() legt Run an + verfolgt Phasen")
    r = _fresh()
    r.record("run_1", status="planning", intent="erstelle excel", source="som")
    r.record("run_1", status="executing")
    r.record("run_1", status="ready")
    snap = r.snapshot()
    runs = {x["run_id"]: x for x in snap["runs"]}
    check("run_1 erfasst", "run_1" in runs)
    check("aktueller Status = ready", runs["run_1"]["status"] == "ready")
    check("intent gemerkt", runs["run_1"]["intent"] == "erstelle excel")
    check("source gemerkt", runs["run_1"]["source"] == "som")
    check("Phasen-Historie 3 Eintraege", len(runs["run_1"]["phases"]) == 3)


# ── Test 2: aktiv vs. fertig ──────────────────────────────────────────────────
def test_active_vs_done():
    print("Test 2: aktive (planning/executing) vs. fertige (ready/failed) Runs")
    r = _fresh()
    r.record("a", status="executing", intent="x", source="som")
    r.record("b", status="ready", intent="y", source="team")
    r.record("c", status="failed", intent="z", source="som")
    snap = r.snapshot()
    check("active enthaelt nur a", [x["run_id"] for x in snap["active"]] == ["a"])
    done_ids = {x["run_id"] for x in snap["done"]}
    check("done enthaelt b und c", done_ids == {"b", "c"})


# ── Test 3: Capping (RAM-Schutz, jüngste behalten) ───────────────────────────
def test_capping():
    print("Test 3: Registry cappt auf max_runs (juengste behalten)")
    r = _sp.SomProgressRegistry(now_fn=_clock(), max_runs=5)
    for i in range(8):
        r.record(f"run_{i}", status="ready", intent=f"i{i}", source="som")
    snap = r.snapshot()
    ids = {x["run_id"] for x in snap["runs"]}
    check("nur 5 behalten", len(ids) == 5)
    check("juengster (run_7) noch da", "run_7" in ids)
    check("aeltester (run_0) verworfen", "run_0" not in ids)


# ── Test 4: leere Registry kippt nicht ────────────────────────────────────────
def test_empty():
    print("Test 4: leere Registry -> leeres Dashboard")
    r = _fresh()
    snap = r.snapshot()
    check("runs leer", snap["runs"] == [])
    check("active leer", snap["active"] == [])


# ── Test 5: unbekannte/leere run_id robust ────────────────────────────────────
def test_robust_input():
    print("Test 5: leere/None run_id -> ignoriert, kein Crash")
    r = _fresh()
    r.record("", status="planning")      # leer -> ignoriert
    r.record(None, status="planning")    # None -> ignoriert
    snap = r.snapshot()
    check("keine Geister-Runs", snap["runs"] == [])


if __name__ == "__main__":
    test_record_creates_run()
    test_active_vs_done()
    test_capping()
    test_empty()
    test_robust_input()
    print()
    print(f"=== {len(_passed)} PASSED, {len(_failed)} FAILED ===")
    if _failed:
        print("FEHLGESCHLAGEN:", _failed)
        sys.exit(1)
