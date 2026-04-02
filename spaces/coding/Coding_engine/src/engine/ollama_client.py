"""
Ollama Client — Local LLM interface via Ollama REST API.

Wraps the Ollama /api/chat endpoint to provide a simple
chat-completion interface for all Minibook agents.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 300  # 5 min for large generations


@dataclass
class OllamaMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class OllamaResponse:
    content: str
    model: str
    total_duration_ms: int = 0
    prompt_eval_count: int = 0
    eval_count: int = 0
    done: bool = True
    error: Optional[str] = None


class OllamaClient:
    """Synchronous client for the Ollama REST API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        temperature: float = 0.4,
        num_ctx: int = 32768,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.num_ctx = num_ctx
        self._client = httpx.Client(timeout=timeout)
        logger.info("OllamaClient init model=%s url=%s", model, base_url)

    # ------------------------------------------------------------------
    # Core chat completion
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> OllamaResponse:
        """
        Send a chat completion request to Ollama.

        Args:
            messages: List of {"role": ..., "content": ...} dicts
            system: Optional system prompt (prepended automatically)
            temperature: Override instance temperature
            max_tokens: Limit output tokens (num_predict)
            json_mode: Request JSON output format

        Returns:
            OllamaResponse with content and metadata
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [],
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
                "num_ctx": self.num_ctx,
            },
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        if json_mode:
            payload["format"] = "json"

        # Prepend system message
        if system:
            payload["messages"].append({"role": "system", "content": system})

        payload["messages"].extend(messages)

        start = time.time()
        try:
            resp = self._client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            duration_ms = int((time.time() - start) * 1000)
            content = data.get("message", {}).get("content", "")

            logger.info(
                "ollama_chat model=%s tokens_in=%d tokens_out=%d duration=%dms",
                self.model,
                data.get("prompt_eval_count", 0),
                data.get("eval_count", 0),
                duration_ms,
            )

            return OllamaResponse(
                content=content,
                model=data.get("model", self.model),
                total_duration_ms=duration_ms,
                prompt_eval_count=data.get("prompt_eval_count", 0),
                eval_count=data.get("eval_count", 0),
                done=data.get("done", True),
            )

        except httpx.HTTPStatusError as e:
            logger.error("ollama HTTP error: %s", e)
            return OllamaResponse(
                content="",
                model=self.model,
                done=False,
                error=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except httpx.ConnectError:
            logger.error("ollama not reachable at %s", self.base_url)
            return OllamaResponse(
                content="",
                model=self.model,
                done=False,
                error=f"Cannot connect to Ollama at {self.base_url}. Is it running?",
            )
        except Exception as e:
            logger.error("ollama unexpected error: %s", e)
            return OllamaResponse(
                content="",
                model=self.model,
                done=False,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Convenience: single prompt
    # ------------------------------------------------------------------
    def ask(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Simple one-shot question → answer string."""
        resp = self.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            temperature=temperature,
        )
        if resp.error:
            raise RuntimeError(f"Ollama error: {resp.error}")
        return resp.content

    # ------------------------------------------------------------------
    # Convenience: structured JSON output
    # ------------------------------------------------------------------
    def ask_json(
        self,
        prompt: str,
        system: Optional[str] = None,
    ) -> Any:
        """Ask for JSON output and parse it."""
        resp = self.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            json_mode=True,
        )
        if resp.error:
            raise RuntimeError(f"Ollama error: {resp.error}")
        try:
            return json.loads(resp.content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from Ollama response, returning raw")
            return resp.content

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def is_healthy(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            resp = self._client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            # Check if our model (or its base name) is available
            base_model = self.model.split(":")[0]
            return any(base_model in m for m in models)
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """List all available Ollama models."""
        try:
            resp = self._client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []

    def close(self) -> None:
        self._client.close()
