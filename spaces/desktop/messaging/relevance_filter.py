"""
Relevance Filter — Ollama-based relevance scoring for incoming messages.

Uses a local Ollama model (fast, no API cost) to decide whether an
incoming WhatsApp/Telegram message is relevant enough to interrupt
the user's voice session.

Score >= threshold → notify via inject_system_message + save to Rowboat
Score < threshold  → log only, no voice interrupt
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from llm_config import get_model

logger = logging.getLogger(__name__)

# Default Ollama settings (overridable via env)
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = get_model("messaging_relevance")
DEFAULT_RELEVANCE_THRESHOLD = 0.5

RELEVANCE_PROMPT = """Du bist ein Relevanz-Filter fuer eingehende Chat-Nachrichten.
Bewerte ob die folgende Nachricht fuer den User JETZT relevant ist und
ihn in seiner aktuellen Arbeit unterbrechen sollte.

Konversationskontext (letzte Aktionen des Users):
{context}

Eingehende Nachricht von {sender} via {platform}:
"{message}"

Bewertungskriterien:
- Direkte Antwort auf eine Nachricht, die der User gerade gesendet hat → HOCH (0.8-1.0)
- Persoenliche Nachricht von Freund/Familie → MITTEL-HOCH (0.6-0.8)
- Arbeitsbezogene Nachricht mit Zeitdruck → HOCH (0.7-1.0)
- Allgemeiner Chat / Smalltalk → NIEDRIG (0.2-0.4)
- Spam / Newsletter / Werbung → SEHR NIEDRIG (0.0-0.1)
- Gruppennachricht ohne direkte Erwaehnung → NIEDRIG (0.1-0.3)

Antworte NUR mit einem JSON-Objekt (kein anderer Text):
{{"relevant": true/false, "score": 0.0-1.0, "reason": "kurze Begruendung"}}"""


class RelevanceFilter:
    """Ollama-based relevance scoring for incoming messages."""

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        threshold: Optional[float] = None,
    ):
        self.model = model or get_model("messaging_relevance")
        self.host = host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        self.threshold = threshold or float(
            os.getenv("MESSAGING_RELEVANCE_THRESHOLD", str(DEFAULT_RELEVANCE_THRESHOLD))
        )
        logger.info(
            f"RelevanceFilter: model={self.model}, host={self.host}, "
            f"threshold={self.threshold}"
        )

    async def check(
        self,
        message: str,
        sender: str,
        platform: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Check relevance of an incoming message via Ollama.

        Args:
            message: The incoming message text
            sender: Sender name/ID
            platform: whatsapp, telegram, discord, etc.
            context: Recent conversation context (last actions)

        Returns:
            {"relevant": bool, "score": float, "reason": str}
        """
        prompt = RELEVANCE_PROMPT.format(
            context=context or "Kein Kontext verfuegbar.",
            sender=sender,
            platform=platform,
            message=message,
        )

        try:
            result = await self._query_ollama(prompt)
            parsed = self._parse_response(result)

            # Apply threshold
            parsed["relevant"] = parsed["score"] >= self.threshold

            logger.info(
                f"RelevanceFilter: [{sender}@{platform}] "
                f"score={parsed['score']:.2f} relevant={parsed['relevant']} "
                f"reason={parsed['reason']}"
            )
            return parsed

        except Exception as e:
            logger.error(f"RelevanceFilter error: {e}")
            # On error, assume moderately relevant (don't drop personal messages)
            return {
                "relevant": True,
                "score": 0.6,
                "reason": f"Fallback (Ollama error: {e})",
            }

    async def _query_ollama(self, prompt: str) -> str:
        """Send prompt to Ollama and return raw response text."""
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temp for consistent scoring
                "num_predict": 100,  # Short response expected
            },
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Parse Ollama JSON response, with fallback for malformed output."""
        # Try direct JSON parse
        try:
            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

            result = json.loads(cleaned)
            return {
                "relevant": bool(result.get("relevant", False)),
                "score": float(result.get("score", 0.5)),
                "reason": str(result.get("reason", "")),
            }
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: try to extract JSON from within the text
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            result = json.loads(raw[start:end])
            return {
                "relevant": bool(result.get("relevant", False)),
                "score": float(result.get("score", 0.5)),
                "reason": str(result.get("reason", "")),
            }
        except (ValueError, json.JSONDecodeError):
            pass

        # Last resort: heuristic from raw text
        logger.warning(f"RelevanceFilter: Could not parse response: {raw[:200]}")
        score = 0.5
        if any(w in raw.lower() for w in ["spam", "werbung", "newsletter"]):
            score = 0.1
        elif any(w in raw.lower() for w in ["wichtig", "dringend", "antwort"]):
            score = 0.8
        return {
            "relevant": score >= self.threshold,
            "score": score,
            "reason": "Heuristic fallback (could not parse Ollama response)",
        }

    async def health_check(self) -> bool:
        """Check if Ollama is reachable and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.host}/api/tags")
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    if self.model in models or any(self.model in m for m in models):
                        return True
                    logger.warning(
                        f"RelevanceFilter: Model '{self.model}' not found. "
                        f"Available: {models}"
                    )
                return False
        except Exception as e:
            logger.warning(f"RelevanceFilter health check failed: {e}")
            return False
