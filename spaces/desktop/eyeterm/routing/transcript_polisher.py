"""AI-powered transcript polishing via OpenRouter API."""

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional

logger = logging.getLogger("eyeterm.polisher")

_POLISH_PROMPT = """Polish this voice-dictated transcript for the given context.
Fix grammar, improve clarity, keep the original intent.
Return ONLY the polished text, nothing else.

Context:
- App: {app_name}
- Element: {element_type}: {element_name}
- Current value: {current_value}

Raw transcript:
{transcript}

Polished text:"""


class TranscriptPolisher:
    """Polish voice transcripts using LLM before submission.

    Runs in a background thread to avoid blocking the main loop.
    Calls on_complete(polished_text) when done.
    """

    def __init__(
        self,
        model: str = None,
        max_workers: int = 1,
    ) -> None:
        if model is None:
            from llm_config import get_model as _get_model
            model = _get_model("desktop_orchestrator")
        self._model = model
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="polisher")
        self._current_future = None
        self._lock = threading.Lock()

    def polish(
        self,
        transcript: str,
        element_context: Optional[Dict] = None,
        on_complete: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Start polishing in background thread.

        Args:
            transcript: Raw voice transcript to polish.
            element_context: Dict from UIElementContext.to_orchestrator_context().
            on_complete: Called with polished text when done (on worker thread).
        """
        with self._lock:
            # Cancel any in-progress polish
            if self._current_future and not self._current_future.done():
                self._current_future.cancel()

            self._current_future = self._executor.submit(
                self._do_polish, transcript, element_context, on_complete
            )

    def cancel(self) -> None:
        """Cancel in-progress polish."""
        with self._lock:
            if self._current_future and not self._current_future.done():
                self._current_future.cancel()
                self._current_future = None

    def _do_polish(
        self,
        transcript: str,
        element_context: Optional[Dict],
        on_complete: Optional[Callable[[str], None]],
    ) -> None:
        """Worker: call LLM API and invoke callback."""
        try:
            polished = self._call_llm(transcript, element_context)
            if on_complete:
                on_complete(polished)
        except Exception as e:
            logger.error("Polish failed: %s", e)
            # On failure, return the original transcript
            if on_complete:
                on_complete(transcript)

    def _call_llm(self, transcript: str, element_context: Optional[Dict]) -> str:
        """Call OpenRouter API for polishing."""
        if not self._api_key:
            logger.warning("No OPENROUTER_API_KEY — returning transcript as-is")
            return transcript

        ctx = element_context or {}
        prompt = _POLISH_PROMPT.format(
            app_name=ctx.get("gaze_app", "Unknown"),
            element_type=ctx.get("gaze_element", "Unknown").split(":")[0] if ctx.get("gaze_element") else "Unknown",
            element_name=ctx.get("gaze_element", "Unknown").split(":")[-1].strip() if ctx.get("gaze_element") else "Unknown",
            current_value=ctx.get("gaze_value", "(none)")[:200],
            transcript=transcript,
        )

        import urllib.request

        payload = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            polished = data["choices"][0]["message"]["content"].strip()
            logger.info("Polished: %r → %r", transcript[:40], polished[:40])
            return polished

    def shutdown(self) -> None:
        """Shutdown the thread pool."""
        self._executor.shutdown(wait=False)
