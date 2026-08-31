"""
SubagentDispatcher — execute LLM_AGENT ToolTemplates.

Phase E. Brain's ToolLibrary registers ToolTemplates (claude_subagent,
groq_subagent), but ToolLibrary itself only does parameter inference.
This module is the bridge: given a ToolCall (with parameters filled),
it actually invokes the right LLM via the existing MultiLLMRouter
infrastructure and returns the response.

Why not call MultiLLMRouter directly? Because Brain's call sites should
not need to know the routing details (Anthropic vs Groq, model strings,
fallback behavior, error handling). They just say "claude_subagent" or
"groq_subagent" and get text back.

Design:
  - Synchronous (caller waits for response — short subtasks <30s)
  - Falls back gracefully if router unavailable
  - Tracks per-tool stats (calls, failures, total tokens estimate)
  - Threadsafe (single dispatcher per Brain instance)

API:
    dispatcher = SubagentDispatcher(llm_router)
    result = dispatcher.dispatch("claude_subagent",
                                 prompt="Refactor this function...",
                                 system="You are a senior dev.",
                                 max_tokens=512)
    # result: {"text": str, "tool": str, "model": str, "ok": bool, "error": ...}
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SubagentDispatcher:
    """Execute LLM_AGENT ToolCalls via Brain's MultiLLMRouter."""

    def __init__(self, llm_router: Any) -> None:
        """
        Args:
            llm_router: a MultiLLMRouter instance (or None — dispatch becomes
                a graceful no-op).
        """
        self._router = llm_router
        self._lock = threading.Lock()
        self.stats: Dict[str, Any] = {
            "calls_total": 0,
            "calls_per_tool": {},
            "failures": 0,
            "last_error": None,
            "last_call_ts": None,
        }

    # ── Public API ────────────────────────────────────────────────────

    def dispatch(self, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute an LLM_AGENT subtask.

        Args:
            tool_name: 'claude_subagent' or 'groq_subagent'
            **kwargs: parameters for the tool (prompt, system, model, max_tokens, ...)

        Returns:
            {ok: bool, text: str, tool: str, model: str, latency_ms: float,
             error: Optional[str]}
        """
        with self._lock:
            self.stats["calls_total"] += 1
            self.stats["calls_per_tool"][tool_name] = (
                self.stats["calls_per_tool"].get(tool_name, 0) + 1
            )
            self.stats["last_call_ts"] = time.time()

        # `openai_subagent` and `ollama_subagent` don't need a router —
        # they use direct HTTP to OpenAI / local Ollama. Only the
        # OpenRouter-backed kinds (claude, groq) need _router.
        _NEEDS_ROUTER = {"claude_subagent", "groq_subagent"}
        if self._router is None and tool_name in _NEEDS_ROUTER:
            self._record_failure(tool_name, "no router")
            return {
                "ok": False, "tool": tool_name, "text": "",
                "error": "MultiLLMRouter not available",
            }

        if tool_name == "claude_subagent":
            return self._dispatch_llm(
                tool_name=tool_name,
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "anthropic/claude-haiku-4.5"),
                max_tokens=int(kwargs.get("max_tokens", 1024)),
                temperature=float(kwargs.get("temperature", 0)),
            )
        elif tool_name == "groq_subagent":
            return self._dispatch_llm(
                tool_name=tool_name,
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "groq::llama-3.3-70b-versatile"),
                max_tokens=int(kwargs.get("max_tokens", 512)),
                temperature=float(kwargs.get("temperature", 0.3)),
            )
        elif tool_name == "openai_subagent":
            # Direct OpenAI API (NOT via OpenRouter) — uses OPENAI_API_KEY.
            # Useful when OpenRouter is rate-limited / out of credit.
            return self._dispatch_openai(
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "gpt-4o-mini"),
                max_tokens=int(kwargs.get("max_tokens", 1500)),
                temperature=float(kwargs.get("temperature", 0.1)),
            )
        elif tool_name == "ollama_subagent":
            # Local Ollama — quota-free fallback. Defaults to llama3.1:8b
            # because it's the smallest model with strong JSON output.
            return self._dispatch_ollama(
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "llama3.1:latest"),
                max_tokens=int(kwargs.get("max_tokens", 1500)),
                temperature=float(kwargs.get("temperature", 0.1)),
            )
        else:
            self._record_failure(tool_name, "unknown tool")
            return {
                "ok": False, "tool": tool_name, "text": "",
                "error": f"unknown LLM_AGENT tool: {tool_name}",
            }

    # ── Implementation ────────────────────────────────────────────────

    def _dispatch_llm(
        self,
        tool_name: str,
        prompt: str,
        system: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """Single LLM call via MultiLLMRouter._call_openrouter."""
        if not prompt or len(prompt.strip()) < 1:
            self._record_failure(tool_name, "empty prompt")
            return {
                "ok": False, "tool": tool_name, "model": model, "text": "",
                "error": "empty prompt",
            }

        # Build full prompt with optional system context
        if system:
            full_prompt = f"[System: {system}]\n\n{prompt}"
        else:
            full_prompt = prompt

        t0 = time.time()
        try:
            text = self._router._call_openrouter(
                model=model,
                prompt=full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            latency_ms = (time.time() - t0) * 1000.0
            return {
                "ok": True,
                "tool": tool_name,
                "model": model,
                "text": (text or "").strip(),
                "latency_ms": round(latency_ms, 1),
                "prompt_len": len(full_prompt),
            }
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            self._record_failure(tool_name, f"{type(e).__name__}: {e}")
            return {
                "ok": False,
                "tool": tool_name,
                "model": model,
                "text": "",
                "latency_ms": round(latency_ms, 1),
                "error": f"{type(e).__name__}: {e}",
            }

    def _record_failure(self, tool: str, reason: str) -> None:
        with self._lock:
            self.stats["failures"] += 1
            self.stats["last_error"] = f"{tool}: {reason}"
        logger.debug("[SubagentDispatcher] %s failed: %s", tool, reason)

    def _dispatch_openai(
        self,
        prompt: str,
        system: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """Direct OpenAI Chat Completions call. Bypasses OpenRouter so
        callers with an OPENAI_API_KEY but no OpenRouter credit still work.

        Strips the optional 'openai/' prefix on model names so the same
        model strings work as in MultiLLMRouter. Auto-handles gpt-5+
        reasoning models (no temperature, max_completion_tokens)."""
        import os
        import time as _time
        import requests as _requests

        if not prompt or len(prompt.strip()) < 1:
            self._record_failure("openai_subagent", "empty prompt")
            return {"ok": False, "tool": "openai_subagent", "model": model,
                    "text": "", "error": "empty prompt"}

        try:
            from core import config as _cfg
            api_key = (_cfg.openai_key() or "").strip()
        except Exception:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            self._record_failure("openai_subagent", "OPENAI_API_KEY not set")
            return {"ok": False, "tool": "openai_subagent", "model": model,
                    "text": "", "error": "OPENAI_API_KEY env var not set"}

        # Strip openai/ prefix that some Brain configs include
        clean_model = model.split("/", 1)[1] if model.startswith("openai/") else model

        # gpt-5 / o1 / o3 family: reasoning models, no temperature, use max_completion_tokens
        is_reasoning = any(clean_model.startswith(p) for p in ("gpt-5", "o1", "o3"))

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: Dict[str, Any] = {
            "model": clean_model,
            "messages": messages,
        }
        if is_reasoning:
            body["max_completion_tokens"] = max(max_tokens, 2000)
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = temperature

        t0 = _time.time()
        try:
            resp = _requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            text = (
                (data.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "") or ""
            ).strip()
            latency_ms = (_time.time() - t0) * 1000.0
            return {
                "ok": True,
                "tool": "openai_subagent",
                "model": clean_model,
                "text": text,
                "latency_ms": round(latency_ms, 1),
                "error": None,
            }
        except Exception as e:
            latency_ms = (_time.time() - t0) * 1000.0
            self._record_failure("openai_subagent", f"{type(e).__name__}: {e}")
            return {
                "ok": False,
                "tool": "openai_subagent",
                "model": clean_model,
                "text": "",
                "latency_ms": round(latency_ms, 1),
                "error": f"{type(e).__name__}: {e}",
            }

    # ─── Phase 11.T.2 — Async siblings ────────────────────────────────────
    # adispatch() mirrors dispatch() but never blocks the event loop on the
    # underlying HTTP round-trip. All three provider paths (router, openai,
    # ollama) get an _a* variant. Sync API stays for non-async callers.

    async def adispatch(self, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
        """Async dispatch — mirrors dispatch() exactly but uses async paths."""
        with self._lock:
            self.stats["calls_total"] += 1
            self.stats["calls_per_tool"][tool_name] = (
                self.stats["calls_per_tool"].get(tool_name, 0) + 1
            )
            self.stats["last_call_ts"] = time.time()

        _NEEDS_ROUTER = {"claude_subagent", "groq_subagent"}
        if self._router is None and tool_name in _NEEDS_ROUTER:
            self._record_failure(tool_name, "no router")
            return {"ok": False, "tool": tool_name, "text": "",
                    "error": "MultiLLMRouter not available"}

        if tool_name == "claude_subagent":
            return await self._adispatch_llm(
                tool_name=tool_name,
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "anthropic/claude-haiku-4.5"),
                max_tokens=int(kwargs.get("max_tokens", 1024)),
                temperature=float(kwargs.get("temperature", 0)),
            )
        elif tool_name == "groq_subagent":
            return await self._adispatch_llm(
                tool_name=tool_name,
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "groq::llama-3.3-70b-versatile"),
                max_tokens=int(kwargs.get("max_tokens", 512)),
                temperature=float(kwargs.get("temperature", 0.3)),
            )
        elif tool_name == "openai_subagent":
            return await self._adispatch_openai(
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "gpt-4o-mini"),
                max_tokens=int(kwargs.get("max_tokens", 1500)),
                temperature=float(kwargs.get("temperature", 0.1)),
            )
        elif tool_name == "ollama_subagent":
            return await self._adispatch_ollama(
                prompt=kwargs.get("prompt", ""),
                system=kwargs.get("system", ""),
                model=kwargs.get("model", "llama3.1:latest"),
                max_tokens=int(kwargs.get("max_tokens", 1500)),
                temperature=float(kwargs.get("temperature", 0.1)),
            )
        else:
            self._record_failure(tool_name, "unknown tool")
            return {"ok": False, "tool": tool_name, "text": "",
                    "error": f"unknown LLM_AGENT tool: {tool_name}"}

    async def _adispatch_llm(
        self,
        tool_name: str,
        prompt: str,
        system: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """Async _dispatch_llm via MultiLLMRouter._acall_openrouter."""
        if not prompt or len(prompt.strip()) < 1:
            self._record_failure(tool_name, "empty prompt")
            return {"ok": False, "tool": tool_name, "model": model, "text": "",
                    "error": "empty prompt"}

        full_prompt = f"[System: {system}]\n\n{prompt}" if system else prompt
        t0 = time.time()
        try:
            text = await self._router._acall_openrouter(
                model=model,
                prompt=full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            latency_ms = (time.time() - t0) * 1000.0
            return {
                "ok": True, "tool": tool_name, "model": model,
                "text": (text or "").strip(),
                "latency_ms": round(latency_ms, 1),
                "prompt_len": len(full_prompt),
            }
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            self._record_failure(tool_name, f"{type(e).__name__}: {e}")
            return {
                "ok": False, "tool": tool_name, "model": model, "text": "",
                "latency_ms": round(latency_ms, 1),
                "error": f"{type(e).__name__}: {e}",
            }

    async def _adispatch_openai(
        self,
        prompt: str,
        system: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """Async direct OpenAI call."""
        import os as _os
        from core.multi_llm_router import _get_async_client

        if not prompt or len(prompt.strip()) < 1:
            self._record_failure("openai_subagent", "empty prompt")
            return {"ok": False, "tool": "openai_subagent", "model": model,
                    "text": "", "error": "empty prompt"}

        try:
            from core import config as _cfg
            api_key = (_cfg.openai_key() or "").strip()
        except Exception:
            api_key = _os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            self._record_failure("openai_subagent", "OPENAI_API_KEY not set")
            return {"ok": False, "tool": "openai_subagent", "model": model,
                    "text": "", "error": "OPENAI_API_KEY env var not set"}

        clean_model = model.split("/", 1)[1] if model.startswith("openai/") else model
        is_reasoning = any(clean_model.startswith(p) for p in ("gpt-5", "o1", "o3"))

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: Dict[str, Any] = {"model": clean_model, "messages": messages}
        if is_reasoning:
            body["max_completion_tokens"] = max(max_tokens, 2000)
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = temperature

        t0 = time.time()
        try:
            from core.multi_llm_router import _get_provider_semaphore
            sem = _get_provider_semaphore("openai")
            client = _get_async_client()
            async with sem:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=120.0,
                )
            resp.raise_for_status()
            data = resp.json()
            text = (
                (data.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "") or ""
            ).strip()
            return {
                "ok": True, "tool": "openai_subagent", "model": clean_model,
                "text": text, "latency_ms": round((time.time()-t0)*1000.0, 1),
                "error": None,
            }
        except Exception as e:
            self._record_failure("openai_subagent", f"{type(e).__name__}: {e}")
            return {
                "ok": False, "tool": "openai_subagent", "model": clean_model,
                "text": "", "latency_ms": round((time.time()-t0)*1000.0, 1),
                "error": f"{type(e).__name__}: {e}",
            }

    async def _adispatch_ollama(
        self,
        prompt: str,
        system: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """Async local Ollama call."""
        import os as _os
        from core.multi_llm_router import _get_async_client

        if not prompt or len(prompt.strip()) < 1:
            self._record_failure("ollama_subagent", "empty prompt")
            return {"ok": False, "tool": "ollama_subagent", "model": model,
                    "text": "", "error": "empty prompt"}

        clean_model = model.split("/", 1)[1] if model.startswith("ollama/") else model
        base = _os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": clean_model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        t0 = time.time()
        try:
            from core.multi_llm_router import _get_provider_semaphore
            sem = _get_provider_semaphore("ollama")
            client = _get_async_client()
            async with sem:
                resp = await client.post(f"{base}/api/chat", json=body, timeout=240.0)
            resp.raise_for_status()
            data = resp.json()
            text = ((data.get("message") or {}).get("content", "") or "").strip()
            return {
                "ok": True, "tool": "ollama_subagent", "model": clean_model,
                "text": text, "latency_ms": round((time.time()-t0)*1000.0, 1),
                "error": None,
            }
        except Exception as e:
            self._record_failure("ollama_subagent", f"{type(e).__name__}: {e}")
            return {
                "ok": False, "tool": "ollama_subagent", "model": clean_model,
                "text": "", "latency_ms": round((time.time()-t0)*1000.0, 1),
                "error": f"{type(e).__name__}: {e}",
            }

    def _dispatch_ollama(
        self,
        prompt: str,
        system: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """Local Ollama call — no API quota, no auth, fully offline.

        Uses /api/chat endpoint with messages. Model name passes through
        directly (`llama3.1:latest`, `phi3:mini`, `qwen2.5-coder:7b`).
        Strips an optional `ollama/` prefix so callers can mix conventions.
        """
        import os
        import time as _time
        import requests as _requests

        if not prompt or len(prompt.strip()) < 1:
            self._record_failure("ollama_subagent", "empty prompt")
            return {"ok": False, "tool": "ollama_subagent", "model": model,
                    "text": "", "error": "empty prompt"}

        clean_model = model.split("/", 1)[1] if model.startswith("ollama/") else model
        base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": clean_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        t0 = _time.time()
        try:
            resp = _requests.post(
                f"{base}/api/chat",
                json=body,
                timeout=240,
            )
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("message") or {}).get("content", "") or ""
            text = text.strip()
            latency_ms = (_time.time() - t0) * 1000.0
            return {
                "ok": True,
                "tool": "ollama_subagent",
                "model": clean_model,
                "text": text,
                "latency_ms": round(latency_ms, 1),
                "error": None,
            }
        except Exception as e:
            latency_ms = (_time.time() - t0) * 1000.0
            self._record_failure("ollama_subagent", f"{type(e).__name__}: {e}")
            return {
                "ok": False,
                "tool": "ollama_subagent",
                "model": clean_model,
                "text": "",
                "latency_ms": round(latency_ms, 1),
                "error": f"{type(e).__name__}: {e}",
            }
