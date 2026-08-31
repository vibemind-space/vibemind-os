"""
Integration test: provider failover through the real MultiLLMRouter.aroute path.

Mocks only the leaf network call (_acall_openrouter); everything else — aroute,
_acall_llm, chain building, the shared breaker — is the real code. Proves the
failover wiring actually triggers end-to-end, and that the no-chain default is
a no-regress single attempt.
"""

import asyncio
import os

import pytest

import core.multi_llm_router as mod
from core.multi_llm_router import MultiLLMRouter


class _HTTPish(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")

        class _R:
            pass

        self.response = _R()
        self.response.status_code = status_code


@pytest.fixture(autouse=True)
def _reset_breaker():
    # The breaker is module-level shared state; reset between tests.
    mod._failover_breaker = None
    yield
    mod._failover_breaker = None


def _router():
    return MultiLLMRouter(openrouter_api_key="test-key")


def test_no_chain_single_attempt(monkeypatch):
    monkeypatch.delenv("BRAIN_LLM_FALLBACK_CHAIN", raising=False)
    monkeypatch.setenv("BRAIN_LLM_MAX_RETRIES", "0")  # exact old behaviour
    r = _router()
    seen = []

    async def fake(model, prompt, max_tokens, temperature):
        seen.append(model)
        return "hello"

    monkeypatch.setattr(r, "_acall_openrouter", fake)
    out = asyncio.run(r.aroute("path_planning", "hi"))
    assert out == "hello"
    assert len(seen) == 1  # no chain, no retry → one call


def test_chain_fails_over_to_second_provider(monkeypatch):
    # Primary will 429; chain provides a working fallback.
    monkeypatch.setenv("BRAIN_LLM_FALLBACK_CHAIN", "groq::working-model")
    monkeypatch.setenv("BRAIN_LLM_MAX_RETRIES", "0")
    r = _router()
    seen = []

    async def fake(model, prompt, max_tokens, temperature):
        seen.append(model)
        if "working" not in model:
            raise _HTTPish(429)
        return "recovered"

    monkeypatch.setattr(r, "_acall_openrouter", fake)
    out = asyncio.run(r.aroute("path_planning", "hi"))
    assert out == "recovered"
    assert len(seen) == 2  # primary (429) → fallback (ok)
    assert "working" in seen[1]


def test_retries_transient_on_same_model(monkeypatch):
    monkeypatch.delenv("BRAIN_LLM_FALLBACK_CHAIN", raising=False)
    monkeypatch.setenv("BRAIN_LLM_MAX_RETRIES", "2")
    r = _router()
    attempts = {"n": 0}

    async def fake(model, prompt, max_tokens, temperature):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _HTTPish(503)
        return "ok-after-retries"

    # No real sleeping: stub asyncio.sleep used by the failover backoff.
    # ProviderFailover captures provider_failover.asyncio.sleep as its default,
    # so patch it there (not in multi_llm_router).
    import core.provider_failover as pf

    async def no_sleep(_):
        return None

    monkeypatch.setattr(pf.asyncio, "sleep", no_sleep, raising=False)
    monkeypatch.setattr(r, "_acall_openrouter", fake)
    out = asyncio.run(r.aroute("path_planning", "hi"))
    assert out == "ok-after-retries"
    assert attempts["n"] == 3
