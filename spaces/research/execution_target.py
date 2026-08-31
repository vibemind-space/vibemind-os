"""Verified Research execution over existing OpenFang/OpenClaw tools.

The target deliberately rejects prose-only agent answers. A successful result
must contain an external tool call and at least one source URL, so unavailable
Fetch/Qdrant/OpenClaw infrastructure cannot be mistaken for live research.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

import requests


_URL_RE = re.compile(r"https?://[^\s<>()\]\[\"']+")
_OPERATIONS = {"web", "scrape", "summarize", "to_idea"}


def _urls(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, str):
        found.extend(_URL_RE.findall(value))
    elif isinstance(value, dict):
        for nested in value.values():
            found.extend(_urls(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_urls(nested))
    return list(dict.fromkeys(url.rstrip(".,;:") for url in found))


class ResearchTarget:
    """One health-checkable Research operation backed by real agent tools."""

    def __init__(self, target: str) -> None:
        operation = target.split(":", 1)[1] if ":" in target else ""
        if operation not in _OPERATIONS:
            raise ValueError(f"unsupported research operation: {operation!r}")
        self.target = target
        self.operation = operation

        # Imported lazily to keep the Space boundary independently testable.
        from core.capability_targets import OpenFangExecutor

        default_agent = (
            "openclaw-visible" if operation in {"web", "scrape"}
            else "brain-researcher"
        )
        agent = os.environ.get("RESEARCH_AGENT", default_agent)
        self._agent = OpenFangExecutor(f"openfang:{agent}")

    def call(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        try:
            payload = self._payload(args, kwargs)
            delegated = self._agent.call(message=self._instruction(payload))
            if not delegated.get("ok"):
                return {
                    "ok": False,
                    "error": f"research infrastructure unavailable: {delegated.get('error', 'agent call failed')}",
                    "target": self.target,
                }
            result = delegated.get("result")
            if not isinstance(result, dict):
                return self._unverified("agent returned no structured evidence")
            tool_calls = result.get("tool_calls")
            if not isinstance(tool_calls, list) or not tool_calls:
                return self._unverified("external tool evidence is missing")
            if self.operation == "to_idea" and not any(
                any(token in str(call.get("tool", "")).lower() for token in ("idea", "qdrant"))
                for call in tool_calls
                if isinstance(call, dict)
            ):
                return self._unverified("persisted idea evidence is missing")
            sources = _urls(result)
            if not sources:
                return self._unverified("source evidence is missing")
            return {
                "ok": True,
                "result": {
                    "operation": self.operation,
                    "content": result.get("response", ""),
                    "sources": sources,
                    "evidence": {"tool_calls": tool_calls},
                },
                "target": self.target,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "target": self.target,
            }

    def call_with_arg(
        self,
        arg: Any,
        arg_kwarg: str | None = None,
        extra_params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload = dict(extra_params or {})
        payload[arg_kwarg or "input"] = arg
        return self.call(**payload)

    def is_resolvable(self) -> bool:
        return self.health_check()["ok"]

    def health_check(self) -> Dict[str, Any]:
        openfang_url = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200").rstrip("/")
        qdrant_url = os.environ.get("QDRANT_URL", "http://127.0.0.1:16333").rstrip("/")
        components: Dict[str, Dict[str, Any]] = {}
        for name, url in {
            "openfang": f"{openfang_url}/api/agents",
            "qdrant": f"{qdrant_url}/healthz",
        }.items():
            try:
                response = requests.get(url, timeout=(2, 3))
                response.raise_for_status()
                components[name] = {"ok": True, "url": url}
            except Exception as exc:
                components[name] = {
                    "ok": False,
                    "url": url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        return {"ok": all(item["ok"] for item in components.values()), "components": components}

    def stats_dict(self) -> Dict[str, Any]:
        return {"target": self.target, "operation": self.operation, "health": self.health_check()}

    def _payload(self, args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        if kwargs:
            return {key: value for key, value in kwargs.items() if value not in (None, "")}
        if args and isinstance(args[0], dict):
            return args[0]
        return {"input": args[0]} if args else {}

    def _instruction(self, payload: Dict[str, Any]) -> str:
        return (
            f"Execute research.{self.operation} with the available Fetch, Qdrant, "
            "OpenClaw and idea tools. Do not answer from memory. Return source URLs "
            "and perform the external tool calls required for verifiable evidence. "
            f"Input: {payload!r}"
        )

    def _unverified(self, reason: str) -> Dict[str, Any]:
        return {"ok": False, "error": f"unverified research result: {reason}", "target": self.target}
