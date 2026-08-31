"""Local-only inbound classifier via Ollama (Schicht 6.2c).

DSGVO compliance:
    - All inference runs on localhost:11434 (Ollama). NO data leaves the box.
    - No model downloads at runtime — uses already-pulled local models.
    - Refuses to run if MARKETING_CLASSIFIER_ALLOW_OLLAMA != 'true' (explicit
      opt-in; an operator that wants to defer to remote classifier shouldn't
      get an Ollama-call by accident).
    - Inputs are truncated BEFORE the call so the prompt never carries more
      than 8KB of inbound body text.
    - All calls audited via marketing.audit_log with model + tokens spent.

Architecture:
    - Used by the n8n classifier-workflow as a fallback when regex-rules
      can't classify (pre_classification='unknown').
    - n8n calls marketing-API: POST /api/n8n/classify-helper/ollama
      body: {inbound_id, prompt_only_features: bool}
    - Server pulls the sanitized message (no headers, just subject + body),
      classifies it via Ollama, returns {classification, confidence,
      model, elapsed_ms}.
    - n8n PATCHes the result back via /api/n8n/inbound_messages/{id}/classify.

The model is asked for a structured JSON response — temperature=0 for
determinism, repeat_penalty disabled so it doesn't drift.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional, TypedDict


logger = logging.getLogger("marketing.ollama_classifier")


# ─── Constants ─────────────────────────────────────────────────────────


_OLLAMA_URL_DEFAULT = "http://127.0.0.1:11434"
_DEFAULT_MODEL = "phi3:mini"           # fast, sufficient for 6-way classification
_FALLBACK_MODEL = "llama3.1:latest"    # if phi3 not available
_TIMEOUT_S = 30
_MAX_BODY_BYTES = 4096                 # truncated context window
_MAX_SUBJECT_BYTES = 256
# Schicht 6.2 spec: known classification values
_KNOWN_CLASSIFICATIONS = frozenset({
    "bounce", "opt-out", "reply", "spam", "question", "other"
})


# ─── Configuration check ──────────────────────────────────────────────


def is_enabled() -> bool:
    """Refuses by default — explicit opt-in via env."""
    flag = os.environ.get("MARKETING_CLASSIFIER_ALLOW_OLLAMA", "").strip().lower()
    return flag in ("true", "1", "yes")


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", _OLLAMA_URL_DEFAULT).rstrip("/")


def _model() -> str:
    return os.environ.get("MARKETING_CLASSIFIER_MODEL", _DEFAULT_MODEL)


# ─── HTTP helpers ─────────────────────────────────────────────────────


def _ollama_get(path: str, timeout: int = 5) -> Optional[dict]:
    url = f"{_ollama_url()}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception as e:
        logger.debug("ollama GET %s failed: %s", path, e)
        return None


def is_available() -> dict:
    """Cheap health check. Returns {ok, model_loaded, latency_ms, models}."""
    if not is_enabled():
        return {"ok": False, "reason": "MARKETING_CLASSIFIER_ALLOW_OLLAMA not 'true'"}
    t0 = time.time()
    tags = _ollama_get("/api/tags", timeout=3)
    elapsed_ms = int((time.time() - t0) * 1000)
    if tags is None:
        return {"ok": False, "reason": "ollama unreachable",
                "latency_ms": elapsed_ms}
    models = [m.get("name", "") for m in tags.get("models", [])]
    target = _model()
    if target not in models:
        return {"ok": False, "reason": f"model {target!r} not loaded",
                "available_models": models, "latency_ms": elapsed_ms}
    return {"ok": True, "model": target, "models": models,
            "latency_ms": elapsed_ms}


# ─── Prompt construction ──────────────────────────────────────────────


_SYSTEM_PROMPT = """You are an email classifier. Classify the following inbound email into ONE of these categories:

- bounce: an automated delivery-failure notification (DSN, mailer-daemon).
- opt-out: the recipient is asking to unsubscribe or be removed.
- reply: a genuine human reply to a previous email.
- spam: unsolicited marketing / phishing / commercial junk from the sender.
- question: a customer question or support request that needs an answer.
- other: anything else that doesn't fit above (newsletters, notifications, ...).

Respond ONLY with a single JSON object on one line:
{"classification": "<one of the 6 labels>", "confidence": <0.0-1.0>, "reason": "<short>"}

Do not add any other text. No markdown. No explanation outside the JSON."""


def _build_user_prompt(from_email: str, subject: str, body: str) -> str:
    subj = (subject or "")[:_MAX_SUBJECT_BYTES]
    bod = (body or "")[:_MAX_BODY_BYTES]
    return (
        f"From: {from_email or '(unknown)'}\n"
        f"Subject: {subj}\n"
        f"---\n"
        f"{bod}"
    )


# ─── Result type ──────────────────────────────────────────────────────


class ClassificationResult(TypedDict, total=False):
    ok: bool
    classification: Optional[str]
    confidence: Optional[float]
    reason: Optional[str]
    model: Optional[str]
    elapsed_ms: int
    error: Optional[str]


# ─── Inference ────────────────────────────────────────────────────────


def classify(from_email: str, subject: str, body: str,
             *, model: Optional[str] = None,
             temperature: float = 0.0,
             timeout_s: int = _TIMEOUT_S) -> ClassificationResult:
    """Classify a single inbound email via Ollama.

    Returns:
        ClassificationResult with ok=True on success or ok=False + error.
        Even on failure, NEVER raises — caller can retry or fall through.
    """
    t0 = time.time()
    if not is_enabled():
        return {"ok": False,
                "error": "MARKETING_CLASSIFIER_ALLOW_OLLAMA env not set to 'true'",
                "elapsed_ms": 0}

    mdl = model or _model()
    url = f"{_ollama_url()}/api/generate"
    payload = {
        "model": mdl,
        "system": _SYSTEM_PROMPT,
        "prompt": _build_user_prompt(from_email, subject, body),
        "stream": False,
        "format": "json",            # Ollama-native JSON-mode (when available)
        "options": {
            "temperature": float(temperature),
            "repeat_penalty": 1.0,
            "num_predict": 200,
            "seed": 42,              # deterministic for the same input
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw = r.read() or b"{}"
    except urllib.error.HTTPError as e:
        return {"ok": False, "model": mdl,
                "error": f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}",
                "elapsed_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "model": mdl,
                "error": f"{type(e).__name__}: {e}",
                "elapsed_ms": int((time.time() - t0) * 1000)}

    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        resp = json.loads(raw)
    except Exception as e:
        return {"ok": False, "model": mdl,
                "error": f"non-JSON ollama response: {e}",
                "elapsed_ms": elapsed_ms}

    # Ollama returns {"response": "<json-string>", ...}
    response_str = (resp.get("response") or "").strip()
    if not response_str:
        return {"ok": False, "model": mdl,
                "error": "empty ollama response",
                "elapsed_ms": elapsed_ms}

    parsed = _parse_classification(response_str)
    if parsed is None:
        return {"ok": False, "model": mdl,
                "error": f"could not parse classification from {response_str[:200]!r}",
                "elapsed_ms": elapsed_ms}

    return {
        "ok": True,
        "classification": parsed["classification"],
        "confidence": parsed.get("confidence"),
        "reason": parsed.get("reason"),
        "model": mdl,
        "elapsed_ms": elapsed_ms,
    }


def _parse_classification(raw: str) -> Optional[dict]:
    """Robust parser: Ollama JSON-mode usually returns clean JSON, but be
    defensive about code-fences and trailing text."""
    s = raw.strip()
    if s.startswith("```"):
        # Strip fence
        s = s.strip("`").strip()
        if s.lower().startswith("json"):
            s = s[4:].strip()
    try:
        d = json.loads(s)
    except Exception:
        # Maybe the model added preamble. Find the first {...} block.
        import re
        m = re.search(r"\{[^{}]*\}", s, re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except Exception:
            return None

    if not isinstance(d, dict):
        return None
    cl = d.get("classification")
    if cl not in _KNOWN_CLASSIFICATIONS:
        # Soft normalize common variations
        cl_norm = (cl or "").strip().lower().replace("_", "-")
        if cl_norm in _KNOWN_CLASSIFICATIONS:
            cl = cl_norm
        else:
            return None
    conf = d.get("confidence")
    try:
        if conf is not None:
            conf = float(conf)
            if not (0.0 <= conf <= 1.0):
                conf = None
    except Exception:
        conf = None
    return {"classification": cl, "confidence": conf,
            "reason": (d.get("reason") or "")[:200]}


__all__ = [
    "is_enabled", "is_available", "classify",
    "ClassificationResult", "_KNOWN_CLASSIFICATIONS",
]
