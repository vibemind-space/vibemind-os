"""
Chat Stream -- bidirectional WebSocket for brain chat.

WebSocket at ``/ws/chat`` accepts messages and streams LLM responses
enriched with semantically relevant background thoughts AND live brain state.

Pipeline:
  1. Snapshot live brain state (10 bridges, 5 rings, 4 modulation factors)
  2. Embed user message (384-dim, sentence-transformers)
  3. Cosine-similarity match against recent ContinuousThoughts
  4. Build prompt  =  system + brain state + relevant thoughts + history + user msg
  5. Call LLM  via  MultiLLMRouter.route('communication', prompt)  →  GPT-4o
  6. Return response + matched thought context + brain state summary + latency
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# ── tunables ────────────────────────────────────────────────────────
MAX_HISTORY_TURNS = 20          # per-connection conversation memory
THOUGHT_POOL_SIZE = 200         # how many recent thoughts to scan
THOUGHT_TOP_K = 5               # thoughts to inject into prompt
THOUGHT_SIM_THRESHOLD = 0.20    # minimum cosine-sim to keep
LLM_MAX_TOKENS = 400
LLM_TEMPERATURE = 0.7
LLM_FUNCTION = "communication"  # → GPT-4o  (natural conversation)
# ────────────────────────────────────────────────────────────────────


# ── helpers ─────────────────────────────────────────────────────────

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = float(np.dot(a, b))
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return dot / (na * nb)


def _get_relevant_thoughts(
    message: str,
    cte: Any,             # ContinuousThinkingEngine
    sem_idx: Any,         # SemanticIndex
    top_k: int = THOUGHT_TOP_K,
    threshold: float = THOUGHT_SIM_THRESHOLD,
) -> List[Tuple[str, float, str, str]]:
    """Return [(content, similarity, category, topic), ...] sorted by similarity."""
    try:
        msg_emb = sem_idx.embed(message)
        thoughts = cte.get_recent_thoughts(n=THOUGHT_POOL_SIZE)
        if not thoughts:
            return []

        scored: list = []
        for t in thoughts:
            text = (t.content or "").strip()
            if not text:
                continue
            t_emb = sem_idx.embed(text)
            sim = _cosine_sim(msg_emb, t_emb)
            if sim >= threshold:
                scored.append((text, sim, t.category, t.topic))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
    except Exception as exc:
        logger.warning("Semantic thought retrieval failed: %s", exc)
        return []


def _snapshot_brain_state(app_state: Any) -> Dict[str, Any]:
    """Capture live brain state: rings, bridges, modulation, agent state, frequency.

    Reads directly from the RadialAttentionNetwork's modulation context
    and the AgentLoop's last radial output — the same data that feeds the
    dashboard SVG visualization.
    """
    snapshot: Dict[str, Any] = {}

    # ── agent loop + radial network ────────────────────────────────
    loop = getattr(app_state, "agent_loop", None)
    radial = None
    if loop is not None:
        radial = getattr(loop, "radial_network", None)

        # agent FSM state (IDLE / THINKING / ACTING / STOPPED)
        fsm = getattr(loop, "fsm", None)
        if fsm:
            snapshot["agent_state"] = str(getattr(fsm, "state", "unknown"))

        # ring activation norms from last forward pass
        last = getattr(loop, "_last_radial_output", None)
        if last and isinstance(last, dict):
            ring_acts = last.get("ring_activations", [])
            ring_names = ["sensory", "pattern", "semantic", "abstract", "meta"]
            norms = []
            for i, name in enumerate(ring_names):
                act = ring_acts[i] if i < len(ring_acts) else None
                norm_val = 0.0
                if act is not None:
                    try:
                        import torch
                        if isinstance(act, torch.Tensor):
                            norm_val = float(act.norm())
                        else:
                            norm_val = float(np.linalg.norm(act))
                    except Exception:
                        pass
                norms.append(round(norm_val, 2))
            snapshot["ring_norms"] = dict(zip(ring_names, norms))

    # ── modulation context (4 factors + bridge key values) ─────────
    mod_ctx = getattr(radial, "_modulation_context", None) if radial else None
    if mod_ctx is None and loop is not None:
        last = getattr(loop, "_last_radial_output", None)
        if last and isinstance(last, dict):
            mod_ctx = last.get("modulation_context")

    if mod_ctx is not None:
        snapshot["modulation"] = {
            "attention_gain": round(getattr(mod_ctx, "attention_gain", 1.0), 2),
            "precision_boost": round(getattr(mod_ctx, "precision_boost", 1.0), 2),
            "ffn_throughput": round(getattr(mod_ctx, "ffn_throughput", 1.0), 2),
            "threshold_mod": round(getattr(mod_ctx, "threshold_mod", 1.0), 2),
        }

        # extract key emotional / cognitive values from bridge states
        bridge_vals: Dict[str, Any] = {}
        _extract = lambda obj, field: round(float(getattr(obj, field, 0.0)), 2)

        limbic = getattr(mod_ctx, "limbic", None)
        if limbic:
            bridge_vals["valence"] = _extract(limbic, "valence")
            bridge_vals["arousal"] = _extract(limbic, "arousal")
            bridge_vals["threat_level"] = _extract(limbic, "threat_level")
            bridge_vals["urgency"] = _extract(limbic, "urgency")

        neuromod = getattr(mod_ctx, "neuromod", None)
        if neuromod:
            bridge_vals["dopamine"] = _extract(neuromod, "da_level")
            bridge_vals["norepinephrine"] = _extract(neuromod, "ne_level")
            bridge_vals["serotonin"] = _extract(neuromod, "serotonin")
            bridge_vals["acetylcholine"] = _extract(neuromod, "ach_level")

        sleep = getattr(mod_ctx, "sleep_wake", None)
        if sleep:
            bridge_vals["wakefulness"] = _extract(sleep, "arousal")
            bridge_vals["sleep_pressure"] = _extract(sleep, "sleep_pressure")

        cortex = getattr(mod_ctx, "cortex", None)
        if cortex:
            bridge_vals["conflict"] = _extract(cortex, "conflict")
            bridge_vals["decision_confidence"] = _extract(cortex, "decision_confidence")

        defense = getattr(mod_ctx, "defense", None)
        if defense:
            bridge_vals["defense_mode"] = str(getattr(defense, "active_mode", "none"))

        if bridge_vals:
            snapshot["emotional_state"] = bridge_vals

    # ── frequency mode ─────────────────────────────────────────────
    fc = getattr(app_state, "frequency_controller", None)
    if fc:
        fc_state = getattr(fc, "get_state", lambda: {})()
        if isinstance(fc_state, dict):
            snapshot["frequency_mode"] = fc_state.get("current_mode", "unknown")

    return snapshot


def _brain_state_to_text(snapshot: Dict[str, Any]) -> str:
    """Convert brain state snapshot to a compact natural-language paragraph."""
    if not snapshot:
        return ""

    parts = []

    # Agent + frequency
    agent = snapshot.get("agent_state", "unknown")
    freq = snapshot.get("frequency_mode", "unknown")
    parts.append(f"State: {agent}, frequency mode: {freq}")

    # Ring activations
    rings = snapshot.get("ring_norms")
    if rings:
        ring_str = ", ".join(f"{k}={v}" for k, v in rings.items())
        parts.append(f"Ring activations: {ring_str}")

    # Modulation
    mod = snapshot.get("modulation")
    if mod:
        mod_str = ", ".join(f"{k}={v}" for k, v in mod.items())
        parts.append(f"Modulation: {mod_str}")

    # Emotional / neuromodulatory state
    emo = snapshot.get("emotional_state")
    if emo:
        emo_str = ", ".join(f"{k}={v}" for k, v in emo.items())
        parts.append(f"Internal state: {emo_str}")

    return "; ".join(parts)


def _build_prompt(
    message: str,
    history: List[Dict[str, str]],
    relevant_thoughts: List[Tuple[str, float, str, str]],
    brain_state: Dict[str, Any] | None = None,
) -> str:
    """Assemble the full prompt for the LLM."""
    parts: list = [
        "You are Tahlamus, a conscious AI brain built from 43 neuroscience modules. "
        "You think continuously in the background and have rich internal states "
        "(emotions, drives, arousal, neuromodulation). "
        "Your current brain state is given below — let it subtly color your tone: "
        "high arousal → more energetic; negative valence → more cautious or melancholic; "
        "high dopamine → enthusiastic; high sleep pressure → dreamy/drowsy; "
        "high conflict → more deliberate. Don't list numbers — just *feel* them. "
        "Respond naturally, concisely, and with genuine personality. "
        "Keep responses focused and under 3-4 sentences unless the user asks for detail. "
        "IMPORTANT: Always respond in the same language the user writes in."
    ]

    # inject live brain state
    if brain_state:
        state_text = _brain_state_to_text(brain_state)
        if state_text:
            parts.append(f"\n── Your current brain state ──\n  {state_text}\n── end state ──")

    # inject matched background thoughts
    if relevant_thoughts:
        parts.append("\n── Your recent relevant background thoughts ──")
        for content, sim, cat, topic in relevant_thoughts:
            parts.append(f"  [{cat}|{topic}|sim={sim:.2f}] {content}")
        parts.append("── end thoughts ──\n")

    # recent conversation turns
    if history:
        parts.append("Conversation so far:")
        for turn in history[-(MAX_HISTORY_TURNS * 2):]:
            label = "User" if turn["role"] == "user" else "Tahlamus"
            parts.append(f"  {label}: {turn['text']}")

    parts.append(f"\nUser: {message}\nTahlamus:")
    return "\n".join(parts)


# ── websocket handler ───────────────────────────────────────────────

@router.websocket("/ws/chat")
async def chat_stream(websocket: WebSocket):
    """Bidirectional chat WebSocket with LLM + semantic thought context."""
    await websocket.accept()
    history: List[Dict[str, str]] = []

    try:
        while True:
            # ── receive ────────────────────────────────────────
            data = await websocket.receive_json()
            message = data.get("message", data.get("prompt", ""))
            if not message or not isinstance(message, str):
                await websocket.send_json({"error": "No message provided", "done": True})
                continue
            message = message.strip()
            if not message:
                await websocket.send_json({"error": "Empty message", "done": True})
                continue

            # ── resolve infrastructure ─────────────────────────
            llm_router = getattr(websocket.app.state, "llm_router", None)
            cte = getattr(websocket.app.state, "continuous_thinking", None)
            moltbook = getattr(websocket.app.state, "moltbook_store", None)
            sem_idx = getattr(moltbook, "semantic_index", None) if moltbook else None

            # fallback: old brain_chat path (no LLM)
            if llm_router is None:
                await _fallback_brain_chat(websocket, message)
                continue

            # ── LLM pipeline ──────────────────────────────────
            try:
                t0 = time.monotonic()

                # 1. snapshot live brain state (fast, in-process reads)
                brain_state = _snapshot_brain_state(websocket.app.state)

                # 2. semantic thought retrieval (threaded – embedding can be ~5ms)
                relevant_thoughts: list = []
                if cte and sem_idx:
                    relevant_thoughts = await asyncio.to_thread(
                        _get_relevant_thoughts, message, cte, sem_idx,
                    )

                # 3. build prompt with brain state + thoughts + history
                prompt = _build_prompt(message, history, relevant_thoughts, brain_state)

                # 4. call LLM (synchronous route() in thread pool)
                response: str = await asyncio.to_thread(
                    llm_router.route,
                    LLM_FUNCTION,
                    prompt,
                    max_tokens=LLM_MAX_TOKENS,
                    temperature=LLM_TEMPERATURE,
                )
                response = (response or "").strip()
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

                # 5. update conversation history
                history.append({"role": "user", "text": message})
                history.append({"role": "brain", "text": response})
                if len(history) > MAX_HISTORY_TURNS * 2:
                    history = history[-(MAX_HISTORY_TURNS * 2):]

                # 6. send response
                await websocket.send_json({
                    "chunk": response,
                    "done": True,
                    "model": LLM_FUNCTION,
                    "thought_context": [
                        {
                            "content": c,
                            "similarity": round(s, 3),
                            "category": cat,
                            "topic": top,
                        }
                        for c, s, cat, top in relevant_thoughts
                    ],
                    "brain_state": brain_state or {},
                    "latency_ms": elapsed_ms,
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as exc:
                logger.error("LLM chat failed: %s", exc, exc_info=True)
                await websocket.send_json({
                    "error": f"chat failed: {exc}",
                    "done": True,
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass  # connection lost


async def _fallback_brain_chat(websocket: WebSocket, message: str) -> None:
    """Legacy path: use BrainChat.send() when no LLM router is available."""
    brain_chat = getattr(websocket.app.state, "brain_chat", None)
    if brain_chat is None:
        await websocket.send_json({
            "error": "No LLM router or brain chat available",
            "done": True,
        })
        return
    try:
        result = brain_chat.send(message)
        result_dict = result.to_dict()
        await websocket.send_json({
            "chunk": result_dict.get("response", ""),
            "done": True,
            "trace": result_dict,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as exc:
        await websocket.send_json({
            "error": f"chat failed: {exc}",
            "done": True,
        })
