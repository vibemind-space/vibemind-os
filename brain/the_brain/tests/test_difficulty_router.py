"""Phase A — Tests für den semantischen Difficulty-Router (Qwen-Cosine).

classify(intent) -> {level, score, reason, method}
  level  ∈ easy | medium | hard | insane
  method ∈ qwen-cosine | heuristic

Deterministisch ohne echtes Modell: ein STUB-Embedder liefert bekannte Vektoren,
sodass die Cosine-Klassifikation prüfbar ist. Plus Fallback-Test (kein Embedder
→ Heuristik) und das Dispatch-Mapping (level → handler).

Aufruf:
    voice/.venv312/Scripts/python brain/the_brain/tests/test_difficulty_router.py
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import numpy as np

# Windows-Konsole auf UTF-8 (Pfeile/Umlaute in den Test-Prints)
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

_BRAIN = Path(__file__).resolve().parents[1]   # brain/the_brain/
if str(_BRAIN) not in sys.path:
    sys.path.insert(0, str(_BRAIN))

_spec = importlib.util.spec_from_file_location(
    "difficulty_router", _BRAIN / "core" / "difficulty_router.py")
_dr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dr)

_passed: list[str] = []
_failed: list[str] = []


def check(name, cond):
    (_passed if cond else _failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


# ── Stub-Embedder: jedes Level bekommt eine eigene Achse im Vektorraum ────────
# 4-dim, orthonormal: easy=[1,0,0,0], medium=[0,1,0,0], hard=[0,0,1,0], insane=[0,0,0,1].
# Ein Intent wird auf die Achse seines erwarteten Levels gemappt (+ etwas Rauschen),
# damit die Cosine-Nähe deterministisch das richtige Level wählt.
_AXIS = {"easy": 0, "medium": 1, "hard": 2, "insane": 3}


class StubEmbedder:
    """Mappt Text auf den Level-Achsen-Vektor anhand eines Schlüsselworts im Text.
    Anker-Texte enthalten ihr Level als Tag [[level]]; Test-Intents auch."""

    def _level_of(self, text: str) -> str:
        for lvl in _AXIS:
            if f"[[{lvl}]]" in text:
                return lvl
        return "medium"

    def encode(self, text: str):
        v = np.zeros(4, dtype=np.float32)
        v[_AXIS[self._level_of(text)]] = 1.0
        return v.tolist()

    def encode_batch(self, texts):
        return [self.encode(t) for t in texts]


def _router_with_stub():
    """Router mit Stub-Embedder + getaggten Ankern (jeder Anker trägt sein Level)."""
    anchors = {
        "easy":   ["[[easy]] danke", "[[easy]] wie spät ist es"],
        "medium": ["[[medium]] öffne example.com", "[[medium]] schalte das licht an"],
        "hard":   ["[[hard]] erstelle eine excel mit spalten", "[[hard]] plane meine bewerbung"],
        "insane": ["[[insane]] wie baue ich am besten einen newsletter-flow", "[[insane]] entwirf eine strategie"],
    }
    return _dr.DifficultyRouter(embedder=StubEmbedder(), anchors=anchors)


# ── Test 1: jede Stufe wird korrekt semantisch klassifiziert ──────────────────
def test_four_levels_classify():
    print("Test 1: Qwen-Cosine klassifiziert alle 4 Stufen")
    r = _router_with_stub()
    for lvl in ("easy", "medium", "hard", "insane"):
        out = r.classify(f"[[{lvl}]] irgendein intent")
        check(f"{lvl} korrekt", out["level"] == lvl)
        check(f"{lvl} method=qwen-cosine", out["method"] == "qwen-cosine")


# ── Test 2: der Excel-Fall (Auslöser der ganzen Rework) → hard, nicht medium ──
def test_excel_case_is_hard():
    print("Test 2: 'erstelle Excel' → hard (der Auslöser-Fall)")
    r = _router_with_stub()
    out = r.classify("[[hard]] erstelle mir eine Excel auf dem Desktop")
    check("Excel → hard", out["level"] == "hard")


# ── Test 3: Fallback auf Heuristik wenn kein Embedder verfügbar ──────────────
def test_heuristic_fallback():
    print("Test 3: kein Embedder → Heuristik-Fallback (kein Crash)")
    r = _dr.DifficultyRouter(disable_semantic=True)  # erzwingt Heuristik-Pfad
    out = r.classify("erstelle eine komplexe mehrstufige Pipeline mit allen Schritten")
    check("Fallback liefert ein Level", out["level"] in ("easy", "medium", "hard", "insane"))
    check("method=heuristic", out["method"] == "heuristic")
    out2 = r.classify("danke")
    check("Smalltalk bleibt klein (easy/medium)", out2["level"] in ("easy", "medium"))


# ── Test 4: Dispatch-Mapping level → handler ──────────────────────────────────
def test_dispatch_mapping():
    print("Test 4: level → handler (chat/shortcut/som/autogen)")
    check("easy → chat", _dr.handler_for("easy") == "chat")
    check("medium → shortcut", _dr.handler_for("medium") == "shortcut")
    check("hard → som", _dr.handler_for("hard") == "som")
    check("insane → autogen", _dr.handler_for("insane") == "autogen")


# ── Test 5: leerer/None-Intent kippt nicht um ─────────────────────────────────
def test_empty_intent_safe():
    print("Test 5: leerer Intent → sicheres Default, kein Crash")
    r = _router_with_stub()
    out = r.classify("")
    check("leerer Intent liefert Level", out["level"] in ("easy", "medium", "hard", "insane"))


# ── Test 6: Meta-Nachrichten (Summary/Transcript) → meta, NICHT planen ────────
# Root-Cause des SoM-Run-Storms: der Telegram-Gateway schickte Konversations-
# Summaries + "[Previous conversation context]"-Transcript an multihop_execute;
# die wurden als hard eingestuft → SoM-Run. Meta-Nachrichten dürfen NIE planen.
def test_meta_messages_not_planned():
    print("Test 6: Meta-Nachrichten → level=meta (kein SoM-Run)")
    r = _router_with_stub()  # Embedder darf egal sein — Meta-Filter greift VOR Cosine
    metas = [
        "Summarize the following conversation preserving key facts, decisions, "
        "user preferences, and important context. Output only the summary.",
        "[Previous conversation context]\nAn den SoM-Planner übergeben — das Ergebnis kommt per Telegram.",
        "[From: Felix] # deadzone — Hardware-Readiness\nStand: 2026-05-27",
        "[Assistant]\nplanner returned no plan\n\n[User]\nReply with exactly the digit 4",
    ]
    for m in metas:
        out = r.classify(m)
        check(f"meta erkannt: «{m[:35]}…»", out["level"] == "meta")
        check("handler(meta) plant nicht", _dr.handler_for("meta") in ("chat", "reject"))
    # Gegenprobe: ein echter Intent der ZUFÄLLIG ein Schlüsselwort enthält bleibt planbar
    out = r.classify("[[hard]] erstelle eine Zusammenfassung meiner Bewerbung als PDF")
    check("echter Intent mit 'Zusammenfassung' bleibt planbar (nicht meta)", out["level"] != "meta")


if __name__ == "__main__":
    test_four_levels_classify()
    test_excel_case_is_hard()
    test_heuristic_fallback()
    test_dispatch_mapping()
    test_empty_intent_safe()
    test_meta_messages_not_planned()
    print()
    print(f"=== {len(_passed)} PASSED, {len(_failed)} FAILED ===")
    if _failed:
        print("FEHLGESCHLAGEN:", _failed)
        sys.exit(1)
