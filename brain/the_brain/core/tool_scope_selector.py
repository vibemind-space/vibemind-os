"""Dynamische Tool- + System-Prompt-Vergabe für OpenFang-Agenten (Brain-seitig).

Problem: OpenFang-Agenten mit `tools=[]` bekommen ALLE ~71 Builtins (+ MCP) — gpt-5.5
verheddert sich im Tool-Loop (kein TASK_COMPLETE, Heartbeat-Crash). Statt statisch zu
kürzen wählt dieser Selector pro Intent SEMANTISCH die relevantesten Tools (Qwen-Cosine,
gleiches Embedder-Pattern wie difficulty_router) + baut einen fokussierten Prompt-Zusatz.

Architektur (plans/dynamic-agent-tools-prompt.md):
  select_tools(intent, agent_name) -> (tool_allowlist, prompt_focus)
  - tool_allowlist: Kern-Set (immer) + Top-N semantisch gewählte Tool-Namen.
  - prompt_focus: kurzer Prompt-Zusatz der die gewählten Tools auflistet (lenkt das LLM).

Die tool_allowlist wird vom Dispatch an OpenFang gegeben (per-Request, sobald der Rust-
Teil steht — bis dahin wirkt nur der prompt_focus via message-Präfix). Der Selector ist
unit-testbar: Embedder + Tool-Liste injizierbar (kein OpenFang/Modell nötig), wie
difficulty_router / som_team_runner.CapabilityTeamBuilder.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Optional

import numpy as np

logger = logging.getLogger("brain.tool_scope_selector")

# Kern-Set pro Agent: Tools die der Agent IMMER bekommt (damit er nie ohne
# Grundfähigkeit dasteht), unabhängig vom Intent. Bewusst minimal. Alles andere
# kommt semantisch. Agenten ohne Eintrag bekommen das generische Kern-Set.
_CORE_TOOLS: dict[str, list[str]] = {
    "skill-coordinator": [
        "skill_search", "skill_save_and_index", "vision_analyze",
        "app_launch_or_focus", "handoff_action",
    ],
    "desktop": [
        "handoff_action", "handoff_read_screen", "vision_analyze",
        "app_launch_or_focus",
    ],
    "openclaw-visible": [
        "handoff_action", "handoff_read_screen", "vision_analyze",
        "app_launch_or_focus",
    ],
    "_default": ["file_read", "memory_recall"],
}

_DEFAULT_TOP_N = int(os.environ.get("TOOL_SCOPE_TOP_N", "8"))
# /api/tools-Cache: einmal ziehen + embedden (328 Tools), dann gecacht. TTL EFFEKTIV
# EINMALIG pro Prozess (Default ~1 Jahr): das encode_batch(328) kostet auf der
# CPU-Maschine ~17 MIN (gemessen 2026-06-18, kein CUDA) — es darf NIE im Request
# laufen, sondern wird beim Startup vorgewärmt (brain_server _warm_embedder). Ein
# kurzer TTL (vorher 1800s) ließ den 17-min-Build alle 30 min im ersten Request
# nach Ablauf neu feuern → Hang. Tool-Defs ändern sich zur Laufzeit praktisch nie;
# ein Prozess-Neustart baut die Matrix ohnehin frisch.
_TOOLS_CACHE_TTL_S = int(os.environ.get("TOOL_SCOPE_CACHE_TTL_S", str(365 * 24 * 3600)))


def _now() -> float:
    # Date.now-frei (für Test/Determinismus über time.monotonic-Wrapper).
    return time.monotonic()


class ToolScopeSelector:
    """Wählt intent-relevante Tools (Qwen-Cosine) + baut einen Prompt-Focus.

    embedder: Objekt mit encode(text)->vec + encode_batch(texts)->[vec]. None →
              lazy core.qdrant_kg.Embedder.get(). Injizierbar für Test.
    tools_fn: callable()->[{name, description}]. None → GET /api/tools (gecacht).
              Injizierbar für Test (kein OpenFang nötig).
    """

    def __init__(
        self,
        embedder: Any = None,
        tools_fn: Optional[Callable[[], list[dict]]] = None,
        core_tools: Optional[dict[str, list[str]]] = None,
    ) -> None:
        self._embedder = embedder
        self._embedder_tried = embedder is not None
        self._tools_fn = tools_fn
        self._core = core_tools if core_tools is not None else _CORE_TOOLS
        # Cache: (timestamp, [tool dicts], np.ndarray normierte embeddings, [names])
        self._cache: Optional[tuple[float, list[dict], np.ndarray, list[str]]] = None

    # ── Embedder lazy (reuse difficulty_router/qdrant_kg) ─────────────────────
    def _get_embedder(self) -> Any:
        if self._embedder is not None:
            return self._embedder
        if self._embedder_tried:
            return None
        self._embedder_tried = True
        try:
            from core.qdrant_kg import Embedder
            self._embedder = Embedder.get()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[toolscope] Embedder nicht verfügbar ({e}), Fallback Kern-Set")
            self._embedder = None
        return self._embedder

    # ── Tool-Liste (von /api/tools, gecacht) ──────────────────────────────────
    def _fetch_tools(self) -> list[dict]:
        if self._tools_fn is not None:
            try:
                return self._tools_fn() or []
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[toolscope] tools_fn fehlgeschlagen ({e})")
                return []
        base = os.environ.get("OPENFANG_URL", "http://host.docker.internal:4200").rstrip("/")
        try:
            import requests
            r = requests.get(base + "/api/tools", timeout=5)
            d = r.json()
            tools = d if isinstance(d, list) else d.get("tools", d.get("data", []))
            return [t for t in tools if isinstance(t, dict) and t.get("name")]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[toolscope] GET /api/tools fehlgeschlagen ({e})")
            return []

    @staticmethod
    def _norm(v: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def _tool_matrix(self) -> tuple[list[dict], np.ndarray, list[str]]:
        """Tool-Defs + normierte Embeddings (gecacht). ([],empty,[]) wenn nichts."""
        if self._cache is not None and (_now() - self._cache[0]) < _TOOLS_CACHE_TTL_S:
            return self._cache[1], self._cache[2], self._cache[3]
        tools = self._fetch_tools()
        if not tools:
            return [], np.zeros((0, 0), dtype=np.float32), []
        embedder = self._get_embedder()
        if embedder is None:
            # Kein Embedder → kein Matrix; select_tools fällt auf Kern-Set + erste-N.
            self._cache = (_now(), tools, np.zeros((0, 0), dtype=np.float32),
                           [t["name"] for t in tools])
            return tools, self._cache[2], self._cache[3]
        texts = [f"{t.get('name','')} {t.get('description','')}" for t in tools]
        mat = np.asarray(embedder.encode_batch(texts), dtype=np.float32)
        # zeilenweise normieren (Qwen ist normalisiert → Cosine = Dot, aber sicher)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat = mat / norms
        names = [t["name"] for t in tools]
        self._cache = (_now(), tools, mat, names)
        return tools, mat, names

    # ── Öffentliche API ────────────────────────────────────────────────────────
    def select_tools(
        self, intent: str, agent_name: str = "_default", top_n: Optional[int] = None
    ) -> tuple[list[str], str]:
        """Top-N intent-relevante Tools (+ Kern-Set) + Prompt-Focus.

        Returns (tool_allowlist, prompt_focus). Bei fehlendem Embedder/Tools:
        nur Kern-Set + leerer Focus (sicherer Fallback — Dispatch nutzt dann das
        heutige Verhalten, sprich kein Filter / voller Tool-Satz).
        """
        n = top_n or _DEFAULT_TOP_N
        core = list(self._core.get(agent_name, self._core["_default"]))
        tools, mat, names = self._tool_matrix()
        if not tools:
            return core, ""  # nichts abrufbar → nur Kern-Set, kein Focus

        chosen: list[str]
        if mat.size == 0:
            # Kein Embedder → Kern-Set + erste (top_n) als grobe Heuristik
            chosen = names[:n]
        else:
            embedder = self._get_embedder()
            try:
                qv = self._norm(np.asarray(embedder.encode(intent), dtype=np.float32))
                sims = mat @ qv  # normiert → Cosine
                order = np.argsort(-sims)[:n]
                chosen = [names[i] for i in order]
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[toolscope] Cosine fehlgeschlagen ({e}), erste-N")
                chosen = names[:n]

        # Kern-Set + gewählte, dedupliziert, Reihenfolge: Kern zuerst.
        allow: list[str] = []
        for t in core + chosen:
            if t not in allow:
                allow.append(t)

        focus = self._build_prompt_focus(allow, tools)
        logger.info(f"[toolscope] agent={agent_name} intent={intent[:40]!r} "
                    f"-> {len(allow)} Tools (core={len(core)}, dyn={len(chosen)})")
        return allow, focus

    def _build_prompt_focus(self, allow: list[str], tools: list[dict]) -> str:
        """Kurzer Prompt-Zusatz der die gewählten Tools nennt (lenkt das LLM auf
        die relevanten, auch wenn technisch mehr verfügbar sind)."""
        if not allow:
            return ""
        desc_by_name = {t["name"]: (t.get("description") or "")[:80] for t in tools}
        lines = [f"- {n}: {desc_by_name.get(n, '')}".rstrip(": ") for n in allow]
        return (
            "FÜR DIESE AUFGABE RELEVANTE WERKZEUGE (nutze NUR diese, ignoriere andere):\n"
            + "\n".join(lines)
        )


# Modul-Singleton (wie get_router im difficulty_router).
_SELECTOR: Optional[ToolScopeSelector] = None


def get_selector() -> ToolScopeSelector:
    global _SELECTOR
    if _SELECTOR is None:
        _SELECTOR = ToolScopeSelector()
    return _SELECTOR
