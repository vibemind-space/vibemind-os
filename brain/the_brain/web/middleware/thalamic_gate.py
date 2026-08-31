"""
Thalamic Gate Middleware — request priority tagging.

Inspired by the thalamus's role as the brain's sensory relay, this
middleware stamps every incoming request with a *priority class* and
*urgency score* derived from the URL prefix.  Response headers carry
the classification back to the caller for observability.
"""

from __future__ import annotations

import time
from typing import Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Prefix → (label, urgency)  — ordered most-specific first
# ---------------------------------------------------------------------------
_PREFIX_MAP: list[Tuple[str, str, float]] = [
    ("/api/cortex",      "cognitive",      0.9),
    ("/ws",              "streaming",      0.8),
    ("/api/knowledge",   "mnemonic",       0.7),
    ("/api/swarm",       "executive",      0.6),
    ("/api/oscillator",  "temporal",       0.4),
    ("/api/introspect",  "introspective",  0.3),
    ("/api/train",       "cerebellar",     0.1),
]

_DEFAULT_LABEL = "unknown"
_DEFAULT_URGENCY = 0.5


def _classify(path: str) -> Tuple[str, float]:
    """Return ``(label, urgency)`` for the given URL path."""
    for prefix, label, urgency in _PREFIX_MAP:
        if path.startswith(prefix):
            return label, urgency
    return _DEFAULT_LABEL, _DEFAULT_URGENCY


class ThalamicGateMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that tags each request with brain-priority metadata."""

    async def dispatch(self, request: Request, call_next) -> Response:
        received_at = time.time()
        label, urgency = _classify(request.url.path)

        # Attach to request state so downstream handlers can read it
        request.state.priority = label
        request.state.urgency = urgency
        request.state.received_at = received_at

        response: Response = await call_next(request)

        # Observability headers
        latency_ms = (time.time() - received_at) * 1000.0
        response.headers["X-Brain-Priority"] = label
        response.headers["X-Brain-Latency-Ms"] = f"{latency_ms:.2f}"

        return response
