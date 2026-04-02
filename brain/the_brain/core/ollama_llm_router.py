"""
Ollama LLM Router for Token Classification

Connects to local Ollama instance (localhost:11434) for fast token classification.
Replaces OpenRouter for local-first, cost-free inference.

Usage:
    from core.ollama_llm_router import OllamaLLMRouter, OllamaConfig

    router = OllamaLLMRouter(OllamaConfig(model="llama3.2:1b"))
    result = router.classify_token("deploy")
    # {'token': 'deploy', 'class': 'ACTION', 'confidence': 0.95}
"""

import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import re


@dataclass
class OllamaConfig:
    """Configuration for Ollama connection"""
    host: str = "localhost"
    port: int = 11434
    model: str = "llama3.2:1b"  # Fast, small model for classification
    timeout: float = 5.0
    retry_count: int = 2
    batch_size: int = 5  # For batch classification


class OllamaLLMRouter:
    """
    Local Ollama router for token classification

    Provides a local-first LLM interface for the TokenFrequencyAdapter.
    Falls back gracefully if Ollama is not available.
    """

    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or OllamaConfig()
        self.base_url = f"http://{self.config.host}:{self.config.port}"

        # Statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_tokens_classified = 0
        self.avg_latency_ms = 0.0

        # Connection state
        self.is_available = self._verify_connection()
        self.available_models: List[str] = []

        if self.is_available:
            self._load_available_models()
            print(f"[OllamaLLMRouter] Connected to {self.base_url}")
            print(f"[OllamaLLMRouter] Using model: {self.config.model}")
        else:
            print(f"[OllamaLLMRouter] WARNING: Ollama not available at {self.base_url}")

    def _verify_connection(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def _load_available_models(self) -> None:
        """Load list of available models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                data = response.json()
                self.available_models = [m['name'] for m in data.get('models', [])]
        except Exception:
            self.available_models = []

    def classify_token(self, token: str) -> Dict[str, Any]:
        """
        Classify a single token into a category

        Args:
            token: The token to classify

        Returns:
            Dict with 'token', 'class', and 'confidence'
        """
        if not self.is_available:
            return {"token": token, "class": "CONTENT", "confidence": 0.5, "source": "fallback"}

        prompt = f"""Classify this token into exactly one category:
Token: "{token}"

Categories:
- ACTION (deploy, run, execute, start, build, create, delete)
- EXPLORATION (or, maybe, alternatively, perhaps, could)
- CONSTRAINT (not, never, must, only, limit)
- TEMPORAL (then, after, before, when, until, while)
- NEGATION (no, cancel, stop, abort, deny)
- CONFIRMATION (yes, correct, ok, exactly, absolutely)
- UNCERTAINTY (might, possibly, probably, seems)
- CONTENT (other semantic content like nouns, names)
- FILLER (the, a, is, and, for, to)
- PUNCTUATION (., ,, !, ?, ;)

Reply with ONLY the category name, nothing else."""

        start_time = datetime.now()
        self.total_requests += 1

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 15,
                        "top_p": 0.9
                    }
                },
                timeout=self.config.timeout
            )

            if response.status_code != 200:
                self.failed_requests += 1
                return {"token": token, "class": "CONTENT", "confidence": 0.5, "source": "error"}

            result = response.json()
            raw_response = result.get("response", "CONTENT").strip()

            # Parse the category from response
            category = self._parse_category(raw_response)

            # Calculate latency
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            self._update_latency(latency_ms)

            self.successful_requests += 1
            self.total_tokens_classified += 1

            return {
                "token": token,
                "class": category,
                "confidence": 0.85,  # Ollama confidence
                "source": "ollama",
                "latency_ms": latency_ms
            }

        except requests.Timeout:
            self.failed_requests += 1
            return {"token": token, "class": "CONTENT", "confidence": 0.5, "source": "timeout"}
        except Exception as e:
            self.failed_requests += 1
            return {"token": token, "class": "CONTENT", "confidence": 0.5, "source": "error", "error": str(e)}

    def _parse_category(self, response: str) -> str:
        """Parse category from LLM response"""
        # Clean up response
        response = response.upper().strip()

        # Valid categories
        valid = {
            "ACTION", "EXPLORATION", "CONSTRAINT", "TEMPORAL",
            "NEGATION", "CONFIRMATION", "UNCERTAINTY", "CONTENT",
            "FILLER", "PUNCTUATION"
        }

        # Direct match
        if response in valid:
            return response

        # Find category in response
        for cat in valid:
            if cat in response:
                return cat

        # Default
        return "CONTENT"

    def _update_latency(self, latency_ms: float) -> None:
        """Update rolling average latency"""
        if self.successful_requests == 1:
            self.avg_latency_ms = latency_ms
        else:
            # Exponential moving average
            alpha = 0.2
            self.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.avg_latency_ms

    def classify_batch(self, tokens: List[str]) -> List[Dict[str, Any]]:
        """
        Classify multiple tokens (batch processing)

        Args:
            tokens: List of tokens to classify

        Returns:
            List of classification results
        """
        results = []
        for token in tokens:
            results.append(self.classify_token(token))
        return results

    def classify_with_context(
        self,
        tokens: List[str],
        target_idx: int
    ) -> Dict[str, Any]:
        """
        Classify a token considering its surrounding context.

        Args:
            tokens: List of tokens (the full context)
            target_idx: Index of the token to classify

        Returns:
            Dict with 'token', 'class', 'confidence', and 'context_used'
        """
        if not self.is_available:
            return {
                "token": tokens[target_idx] if 0 <= target_idx < len(tokens) else "",
                "class": "CONTENT",
                "confidence": 0.5,
                "source": "fallback",
                "context_used": False
            }

        # Extract context window around target
        context_start = max(0, target_idx - 2)
        context_end = min(len(tokens), target_idx + 3)
        context_tokens = tokens[context_start:context_end]
        target_token = tokens[target_idx]

        # Build context string
        context_str = ' '.join(context_tokens)

        prompt = f"""Classify the token "{target_token}" in this context:

Context: "{context_str}"
Target token: "{target_token}"

Categories:
- ACTION (deploy, run, execute, start, build, create, delete)
- EXPLORATION (or, maybe, alternatively, perhaps, could)
- CONSTRAINT (not, never, must, only, limit)
- TEMPORAL (then, after, before, when, until, while)
- NEGATION (no, cancel, stop, abort, deny)
- CONFIRMATION (yes, correct, ok, exactly, absolutely)
- UNCERTAINTY (might, possibly, probably, seems)
- CONTENT (other semantic content like nouns, names)
- FILLER (the, a, is, and, for, to)
- PUNCTUATION (., ,, !, ?, ;)

Consider the surrounding context when classifying. For example:
- "but not" together indicates CONSTRAINT
- "do not" together indicates NEGATION
- "and then" together indicates TEMPORAL

Reply with ONLY the category name, nothing else."""

        start_time = datetime.now()
        self.total_requests += 1

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 15,
                        "top_p": 0.9
                    }
                },
                timeout=self.config.timeout
            )

            if response.status_code != 200:
                self.failed_requests += 1
                return {
                    "token": target_token,
                    "class": "CONTENT",
                    "confidence": 0.5,
                    "source": "error",
                    "context_used": True
                }

            result = response.json()
            raw_response = result.get("response", "CONTENT").strip()

            # Parse the category from response
            category = self._parse_category(raw_response)

            # Calculate latency
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            self._update_latency(latency_ms)

            self.successful_requests += 1
            self.total_tokens_classified += 1

            return {
                "token": target_token,
                "class": category,
                "confidence": 0.9,  # Higher confidence with context
                "source": "ollama_context",
                "context": context_str,
                "context_used": True,
                "latency_ms": latency_ms
            }

        except requests.Timeout:
            self.failed_requests += 1
            return {
                "token": target_token,
                "class": "CONTENT",
                "confidence": 0.5,
                "source": "timeout",
                "context_used": True
            }
        except Exception as e:
            self.failed_requests += 1
            return {
                "token": target_token,
                "class": "CONTENT",
                "confidence": 0.5,
                "source": "error",
                "error": str(e),
                "context_used": True
            }

    def classify_sequence(self, tokens: List[str]) -> List[Dict[str, Any]]:
        """
        Classify all tokens in a sequence with context awareness.

        Args:
            tokens: List of tokens to classify

        Returns:
            List of classification results with context
        """
        results = []
        for i in range(len(tokens)):
            results.append(self.classify_with_context(tokens, i))
        return results

    def route(self, function: str, prompt: str, **kwargs) -> str:
        """
        Generic route for compatibility with existing LLM router interface

        This allows OllamaLLMRouter to be used as a drop-in replacement
        for MultiLLMRouter in TokenFrequencyAdapter.
        """
        if not self.is_available:
            return ""

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": kwargs.get("temperature", 0.7),
                        "num_predict": kwargs.get("max_tokens", 100)
                    }
                },
                timeout=self.config.timeout
            )

            if response.status_code == 200:
                return response.json().get("response", "")
            return ""

        except Exception:
            return ""

    def get_statistics(self) -> Dict[str, Any]:
        """Get router statistics"""
        return {
            "is_available": self.is_available,
            "base_url": self.base_url,
            "model": self.config.model,
            "available_models": self.available_models,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.successful_requests / max(1, self.total_requests),
            "total_tokens_classified": self.total_tokens_classified,
            "avg_latency_ms": self.avg_latency_ms
        }

    def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        was_available = self.is_available
        self.is_available = self._verify_connection()

        return {
            "status": "healthy" if self.is_available else "unhealthy",
            "was_available": was_available,
            "is_available": self.is_available,
            "base_url": self.base_url,
            "model": self.config.model
        }


# Quick test
if __name__ == "__main__":
    print("=" * 60)
    print("  OLLAMA LLM ROUTER TEST")
    print("=" * 60)

    router = OllamaLLMRouter()

    if router.is_available:
        print(f"\nAvailable models: {router.available_models}")

        test_tokens = ["deploy", "not", "maybe", "then", "yes", "the", "nginx"]

        print("\nClassifying tokens:")
        print("-" * 40)

        for token in test_tokens:
            result = router.classify_token(token)
            print(f"  {token:12} -> {result['class']:12} ({result.get('latency_ms', 0):.0f}ms)")

        print("\nStatistics:")
        stats = router.get_statistics()
        print(f"  Success rate: {stats['success_rate']:.1%}")
        print(f"  Avg latency: {stats['avg_latency_ms']:.0f}ms")
    else:
        print("\nOllama not available. Start with:")
        print("  ollama serve")
        print("  ollama pull llama3.2:1b")

    print("\n" + "=" * 60)
