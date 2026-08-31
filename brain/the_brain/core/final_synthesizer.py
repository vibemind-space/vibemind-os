"""Final Synthesizer — Phase 6.

Takes the executed plan + per-hop results and produces a single, concise
user-facing answer via Groq Llama-3.3-70b. Used by BrainChat after the
multi-hop executor finishes.

Falls back to a plain-text summary (no LLM) if the dispatcher is missing
or the LLM call fails — caller never crashes because of synthesis.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_DEFAULT_PROMPT = """\
A user asked: {intent}

Brain decomposed this into a multi-hop plan and executed it. Here is the
per-step summary:

{step_block}

Summarise the result for the user. Be concise (≤180 words), reference the
key findings, and surface any failures or warnings honestly. Don't invent
facts beyond the per-step results. Plain prose — no bullet salad."""


class FinalSynthesizer:
    def __init__(
        self,
        dispatcher: Any = None,
        *,
        model: Optional[str] = None,
        max_tokens: int = 600,
        temperature: float = 0.3,
        fallback_model: Optional[str] = None,
    ) -> None:
        import os as _os
        self.dispatcher = dispatcher
        self.model = model or _os.environ.get(
            "SYNTHESIZER_MODEL", "groq::llama-3.3-70b-versatile",
        )
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.fallback_model = fallback_model or _os.environ.get(
            "SYNTHESIZER_FALLBACK_MODEL", "groq::llama-3.1-8b-instant",
        )
        self.stats: Dict[str, Any] = {
            "syntheses": 0,
            "llm_used": 0,
            "fallback_used": 0,
            "errors": 0,
            "total_latency_ms": 0.0,
            "last_error": None,
        }

    def synthesize(
        self,
        *,
        intent: str,
        plan: Any,
        executed: Dict[str, Any],
        state: Dict[str, Any],
        custom_prompt: Optional[str] = None,
    ) -> str:
        """Returns a user-facing string. Always succeeds — never raises."""
        t0 = time.time()
        self.stats["syntheses"] += 1

        step_block = self._build_step_block(plan, executed)

        # If no dispatcher → fallback to plain summary
        if self.dispatcher is None:
            text = self._fallback(intent, plan, executed, step_block)
            self.stats["fallback_used"] += 1
            self._record_latency(t0)
            return text

        prompt = (custom_prompt or _DEFAULT_PROMPT).format(
            intent=intent.strip(),
            step_block=step_block,
        )

        # Try primary, then fallback model on 429/5xx, then deterministic fallback
        for model_to_try in (self.model, self.fallback_model):
            if not model_to_try:
                continue
            # Pick subagent kind by model prefix (Ollama-local, OpenAI-direct,
            # Anthropic-via-OpenRouter, or Groq).
            lower = model_to_try.lower()
            if lower.startswith("ollama/") or lower.startswith("llama3") or lower.startswith("phi3") or lower.startswith("qwen2"):
                tool_name = "ollama_subagent"
            elif lower.startswith("openai/") or lower.startswith("gpt-") or lower.startswith("o1") or lower.startswith("o3"):
                tool_name = "openai_subagent"
            elif lower.startswith("anthropic/") or lower.startswith("claude") or "haiku" in lower or "sonnet" in lower or "opus" in lower:
                tool_name = "claude_subagent"
            else:
                tool_name = "groq_subagent"
            try:
                resp = self.dispatcher.dispatch(
                    tool_name,
                    prompt=prompt,
                    system="You synthesise multi-step execution results into a single concise answer.",
                    model=model_to_try,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
            except Exception as e:
                self.stats["last_error"] = f"dispatch crash ({model_to_try}): {type(e).__name__}: {e}"
                continue
            if not resp.get("ok"):
                self.stats["last_error"] = f"groq error ({model_to_try}): {resp.get('error')}"
                continue
            text = (resp.get("text") or "").strip()
            if text:
                self.stats["llm_used"] += 1
                self._record_latency(t0)
                return text

        # All LLM paths failed → deterministic plain-text fallback
        self.stats["errors"] += 1
        text = self._fallback(intent, plan, executed, step_block)
        self.stats["fallback_used"] += 1
        self._record_latency(t0)
        return text

    # ─── Phase 11.T.3 — Async sibling ─────────────────────────────────────
    # asynthesize() lets multihop endpoints await synthesis without burning
    # a threadpool worker. Mirrors synthesize() exactly, just using the
    # async dispatcher path.

    async def asynthesize(
        self,
        *,
        intent: str,
        plan: Any,
        executed: Dict[str, Any],
        state: Dict[str, Any],
        custom_prompt: Optional[str] = None,
    ) -> str:
        """Async version of synthesize() — uses dispatcher.adispatch() so the
        FastAPI worker isn't blocked on the LLM round-trip."""
        t0 = time.time()
        self.stats["syntheses"] += 1
        step_block = self._build_step_block(plan, executed)

        if self.dispatcher is None:
            text = self._fallback(intent, plan, executed, step_block)
            self.stats["fallback_used"] += 1
            self._record_latency(t0)
            return text

        prompt = (custom_prompt or _DEFAULT_PROMPT).format(
            intent=intent.strip(),
            step_block=step_block,
        )

        for model_to_try in (self.model, self.fallback_model):
            if not model_to_try:
                continue
            lower = model_to_try.lower()
            if lower.startswith("ollama/") or lower.startswith("llama3") or lower.startswith("phi3") or lower.startswith("qwen2"):
                tool_name = "ollama_subagent"
            elif lower.startswith("openai/") or lower.startswith("gpt-") or lower.startswith("o1") or lower.startswith("o3"):
                tool_name = "openai_subagent"
            elif lower.startswith("anthropic/") or lower.startswith("claude") or "haiku" in lower or "sonnet" in lower or "opus" in lower:
                tool_name = "claude_subagent"
            else:
                tool_name = "groq_subagent"

            # Dispatcher may not yet have adispatch (older instance) — fallback
            adispatch = getattr(self.dispatcher, "adispatch", None)
            if adispatch is None:
                # No async path → run sync dispatch in a thread to keep the
                # event loop responsive.
                import asyncio as _asyncio
                try:
                    resp = await _asyncio.to_thread(
                        self.dispatcher.dispatch, tool_name,
                        prompt=prompt,
                        system="You synthesise multi-step execution results into a single concise answer.",
                        model=model_to_try,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
                except Exception as e:
                    self.stats["last_error"] = f"dispatch crash ({model_to_try}): {type(e).__name__}: {e}"
                    continue
            else:
                try:
                    resp = await adispatch(
                        tool_name,
                        prompt=prompt,
                        system="You synthesise multi-step execution results into a single concise answer.",
                        model=model_to_try,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
                except Exception as e:
                    self.stats["last_error"] = f"dispatch crash ({model_to_try}): {type(e).__name__}: {e}"
                    continue
            if not resp.get("ok"):
                self.stats["last_error"] = f"async error ({model_to_try}): {resp.get('error')}"
                continue
            text = (resp.get("text") or "").strip()
            if text:
                self.stats["llm_used"] += 1
                self._record_latency(t0)
                return text

        self.stats["errors"] += 1
        text = self._fallback(intent, plan, executed, step_block)
        self.stats["fallback_used"] += 1
        self._record_latency(t0)
        return text

    def stats_dict(self) -> Dict[str, Any]:
        s = dict(self.stats)
        if s["syntheses"] > 0:
            s["avg_latency_ms"] = round(s["total_latency_ms"] / s["syntheses"], 1)
        return s

    # ── Internals ──────────────────────────────────────────────

    def _build_step_block(self, plan: Any, executed: Dict[str, Any]) -> str:
        """Render hops + outcomes as a compact bullet block for the LLM."""
        lines: List[str] = []
        # plan may be a Plan dataclass OR a dict (depending on caller).
        if isinstance(plan, dict):
            hops = plan.get("hops") or []
        else:
            hops = getattr(plan, "hops", None) or []
        for h in hops:
            if isinstance(h, dict):
                sid = h.get("step_id")
                desc = h.get("description") or ""
                cap = h.get("capability") or ""
                tgt = h.get("execution_target") or ""
            else:
                sid = getattr(h, "step_id", None)
                desc = getattr(h, "description", "") or ""
                cap = getattr(h, "capability", "") or ""
                tgt = getattr(h, "execution_target", "") or ""
            hr = executed.get(sid)
            if not hr:
                lines.append(f"- {sid}: {desc} → SKIPPED (not executed)")
                continue
            ok = hr.get("ok") if isinstance(hr, dict) else getattr(hr, "ok", False)
            err = hr.get("error") if isinstance(hr, dict) else getattr(hr, "error", None)
            res = hr.get("result") if isinstance(hr, dict) else getattr(hr, "result", None)
            res_preview = _short_repr(res)
            verdict = hr.get("validator_verdict") if isinstance(hr, dict) else getattr(hr, "validator_verdict", None)

            mark = "OK" if ok else "FAIL"
            via = cap or tgt or "?"
            entry = f"- {sid} [{mark}] via {via}: {desc[:80]}"
            if ok:
                entry += f" -> {res_preview}"
            else:
                entry += f" -> ERROR {err}"
            if verdict and verdict.get("reason"):
                v_ok = "ok" if verdict.get("valid") else "fail"
                entry += f" (validator {v_ok}: {verdict['reason'][:80]})"
            lines.append(entry)
        return "\n".join(lines) if lines else "(no steps executed)"

    def _fallback(self, intent: str, plan: Any, executed: Dict[str, Any], step_block: str) -> str:
        ok_count = sum(
            1 for hr in executed.values()
            if (hr.get("ok") if isinstance(hr, dict) else getattr(hr, "ok", False))
        )
        total = len(executed)
        header = f"Multi-hop plan: {ok_count}/{total} steps succeeded for intent: {intent[:120]}"
        return header + "\n\n" + step_block

    def _record_latency(self, t0: float) -> None:
        ms = (time.time() - t0) * 1000
        self.stats["total_latency_ms"] += ms


def _short_repr(value: Any, limit: int = 200) -> str:
    if value is None:
        return "None"
    try:
        s = repr(value)
    except Exception:
        s = "<unrepr>"
    s = re.sub(r"\s+", " ", s)
    if len(s) > limit:
        s = s[: limit - 3] + "..."
    return s
