"""Thin OpenRouter client for the LLM tiebreaker layer.

The navigator only uses the LLM when keyword and embedding layers can't
resolve confidently. Kept minimal and synchronous — no async machinery
just for one call per-tool-invocation.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import urllib.error
import urllib.request


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = os.environ.get("NAVIGATOR_LLM_MODEL", "openai/gpt-4o-mini")
_TIMEOUT = float(os.environ.get("NAVIGATOR_LLM_TIMEOUT", "2.0"))


def is_available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def chat_json(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Call the LLM and return the parsed JSON object, or None on any error."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    body = {
        "model": model or _DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "max_tokens": 200,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        _OPENROUTER_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://vibemind.local/space-navigator",
            "X-Title": "VibeMind Space Navigator",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None

    try:
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, ValueError, TypeError):
        return None
