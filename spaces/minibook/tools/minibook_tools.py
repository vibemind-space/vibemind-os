"""Fail-closed REST execution target for canonical Minibook events.

Minibook is a collaboration projection. This boundary may read it and create
Minibook discussion/task posts, but it exposes no lifecycle or foreign-system
mutation operation.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Mapping
from urllib.parse import quote

import requests


_ALLOWED_EVENTS = {
    "minibook.discuss",
    "minibook.collaborate",
    "minibook.status",
    "minibook.list_projects",
}
_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "cookie", "password", "secret", "token",
}
_TOKEN_VALUE = re.compile(r"(?i)\b(bearer\s+\S+|(?:api[_-]?key|token|secret)\s*[=:]\s*\S+)")


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, str):
        return _TOKEN_VALUE.sub("[REDACTED]", value)
    return value


def _envelope(*, event: str, ok: bool, status: str, result: Any = None,
              error: str | None = None) -> Dict[str, Any]:
    return {
        "ok": ok,
        "space": "minibook",
        "event": event,
        "truth": {"status": status, "source": "minibook"},
        "result": _redact(result),
        "error": error,
    }


def _params(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        return {"topic": raw.strip()}
    return {}


def execute(raw: Any) -> Dict[str, Any]:
    params = _params(raw)
    event = str(params.get("event") or "")
    if event not in _ALLOWED_EVENTS:
        return _envelope(
            event=event,
            ok=False,
            status="rejected",
            error="event is outside the canonical Minibook execution boundary",
        )

    # The destination is operator configuration, never caller-controlled.
    # This keeps a voice/API payload inside the Minibook boundary.
    base_url = str(os.environ.get("MINIBOOK_URL") or "http://127.0.0.1:8800").rstrip("/")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = os.environ.get("MINIBOOK_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    method = "GET"
    url = f"{base_url}/api/v1/status"
    request_kwargs: Dict[str, Any] = {}

    if event == "minibook.list_projects":
        url = f"{base_url}/api/v1/projects"
    elif event in {"minibook.discuss", "minibook.collaborate"}:
        topic = str(params.get("topic") or params.get("value") or "").strip()
        project_id = str(params.get("project_id") or os.environ.get("MINIBOOK_PROJECT_ID") or "").strip()
        if not topic or not project_id:
            return _envelope(
                event=event,
                ok=False,
                status="rejected",
                error="topic and project_id are required",
            )
        method = "POST"
        url = f"{base_url}/api/v1/projects/{quote(project_id, safe='')}/posts"
        post_type = "discussion" if event == "minibook.discuss" else "task"
        body = {
            "title": str(params.get("title") or topic)[:120],
            "content": topic,
            "type": post_type,
            "author_name": "VibeMind Brain",
        }
        if event == "minibook.collaborate" and isinstance(params.get("target_agents"), list):
            body["target_agents"] = [str(agent) for agent in params["target_agents"]]
        request_kwargs["json"] = body

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=float(os.environ.get("MINIBOOK_TIMEOUT_S", "10")),
            **request_kwargs,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return _envelope(
            event=event,
            ok=False,
            status="unavailable",
            error="Minibook execution target unavailable",
        )

    return _envelope(event=event, ok=True, status="verified", result=payload)


def discuss(raw: Any) -> Dict[str, Any]:
    return execute({**_params(raw), "event": "minibook.discuss"})


def collaborate(raw: Any) -> Dict[str, Any]:
    return execute({**_params(raw), "event": "minibook.collaborate"})


def status(raw: Any = None) -> Dict[str, Any]:
    return execute({**_params(raw), "event": "minibook.status"})


def list_projects(raw: Any = None) -> Dict[str, Any]:
    return execute({**_params(raw), "event": "minibook.list_projects"})
