"""HTTP wrapper around OpenAI's embeddings API.

Sole purpose: one place that holds the OpenAI credential for embedding
calls, instead of every brain-core variant mounting it separately, and one
interface (`/embed`, `/embed/batch`) that other consumers (mirofish,
rowboat-rag-worker) could adopt later without a redesign.
"""
from __future__ import annotations

import logging
import os
import time
from typing import List

from fastapi import FastAPI, HTTPException
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel

MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large")
MAX_RETRIES = int(os.environ.get("EMBEDDING_MAX_RETRIES", "2"))
RETRY_BACKOFF_SECONDS = float(os.environ.get("EMBEDDING_RETRY_BACKOFF", "0.5"))

logger = logging.getLogger("embedding_service")

app = FastAPI(title="embedding-service")

_client: OpenAI | None = None


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    vector: List[float]


def _read_secret(name: str) -> str:
    """Same precedence as brain-core's core/config.py get_secret(): a
    Swarm-mounted secret file, then the default /run/secrets mount, then a
    plain env var."""
    file_path = os.environ.get(f"{name}_FILE")
    if file_path and os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    default_mount = f"/run/secrets/{name.lower()}"
    if os.path.exists(default_mount):
        with open(default_mount, "r", encoding="utf-8") as f:
            return f.read().strip()
    return os.environ.get(name, "").strip()


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = _read_secret("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not configured (checked _FILE, /run/secrets, env)"
            )
        _client = OpenAI(api_key=api_key)
    return _client


@app.get("/health")
def health():
    try:
        get_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"status": "ok", "model": MODEL}


def _is_transient(e: APIError) -> bool:
    """Network/timeout errors, rate limits, and 5xx are worth a retry.
    Everything else (4xx client errors like bad request/auth) is not."""
    if isinstance(e, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if isinstance(e, APIStatusError) and e.status_code >= 500:
        return True
    return False


def _embed_with_retry(inputs: List[str]) -> List[List[float]]:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            client = get_client()
            resp = client.embeddings.create(model=MODEL, input=inputs)
            return [d.embedding for d in resp.data]
        except APIError as e:
            last_exc = e
            if _is_transient(e) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            raise
    raise last_exc  # pragma: no cover — loop always returns or raises above


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    try:
        vectors = _embed_with_retry([req.text])
        vector = vectors[0]
    except Exception as e:
        logger.warning(f"/embed failed: {e}")
        raise HTTPException(status_code=502, detail="embedding request failed")
    return EmbedResponse(vector=vector)


class EmbedBatchRequest(BaseModel):
    texts: List[str]


class EmbedBatchResponse(BaseModel):
    vectors: List[List[float]]


@app.post("/embed/batch", response_model=EmbedBatchResponse)
def embed_batch(req: EmbedBatchRequest):
    if not req.texts:
        return EmbedBatchResponse(vectors=[])
    try:
        vectors = _embed_with_retry(req.texts)
        if len(vectors) != len(req.texts):
            raise ValueError(
                f"expected {len(req.texts)} embeddings, got {len(vectors)}"
            )
    except Exception as e:
        logger.warning(f"/embed/batch failed: {e}")
        raise HTTPException(status_code=502, detail="embedding request failed")
    return EmbedBatchResponse(vectors=vectors)
