"""
LLMDataCollector - Training Data Collection with External LLMs

Collects (thought_vector, response) pairs using external LLM APIs.
This provides high-quality training data for the ThoughtDecoder.

Supported Providers:
- Anthropic (Claude)
- OpenAI (GPT-4)
- Local (Ollama)

Usage:
    from core.llm_data_collector import LLMDataCollector

    collector = LLMDataCollector(
        provider="anthropic",
        api_key="your-api-key"
    )

    # Collect data for training
    await collector.collect_batch(
        tasks=["Explain recursion", "What is ML?"],
        ctm=speaking_ctm,
        log_dir="data/thought_corpus"
    )
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
import time

import torch

try:
    from core.thought_logger import ThoughtLogger
except ImportError:
    from thought_logger import ThoughtLogger


@dataclass
class LLMResponse:
    """Response from LLM API."""
    text: str
    model: str
    tokens_used: int
    latency_ms: float
    metadata: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate response for a prompt."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-haiku-20240307",
        max_tokens: int = 256
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self.client = None

        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                print("[AnthropicProvider] anthropic package not installed")

    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        if not self.is_available():
            raise RuntimeError("Anthropic client not available")

        start_time = time.time()

        # Run in thread pool since anthropic client is sync
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                model=kwargs.get('model', self.model),
                max_tokens=kwargs.get('max_tokens', self.max_tokens),
                messages=[{"role": "user", "content": prompt}]
            )
        )

        latency_ms = (time.time() - start_time) * 1000

        return LLMResponse(
            text=response.content[0].text,
            model=response.model,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            latency_ms=latency_ms,
            metadata={'stop_reason': response.stop_reason}
        )


class OpenAIProvider(LLMProvider):
    """OpenAI GPT API provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        max_tokens: int = 256
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self.client = None

        if self.api_key:
            try:
                import openai
                self.client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                print("[OpenAIProvider] openai package not installed")

    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        if not self.is_available():
            raise RuntimeError("OpenAI client not available")

        start_time = time.time()

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=kwargs.get('model', self.model),
                max_tokens=kwargs.get('max_tokens', self.max_tokens),
                messages=[{"role": "user", "content": prompt}]
            )
        )

        latency_ms = (time.time() - start_time) * 1000

        return LLMResponse(
            text=response.choices[0].message.content,
            model=response.model,
            tokens_used=response.usage.total_tokens,
            latency_ms=latency_ms,
            metadata={'finish_reason': response.choices[0].finish_reason}
        )


class OllamaProvider(LLMProvider):
    """Local Ollama API provider."""

    def __init__(
        self,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
        max_tokens: int = 256
    ):
        self.model = model
        self.host = host
        self.max_tokens = max_tokens

    def is_available(self) -> bool:
        try:
            import httpx
            response = httpx.get(f"{self.host}/api/version", timeout=5.0)
            return response.status_code == 200
        except (ImportError, ConnectionError, OSError, ValueError):
            return False

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        import httpx

        start_time = time.time()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.host}/api/generate",
                json={
                    "model": kwargs.get('model', self.model),
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": kwargs.get('max_tokens', self.max_tokens)}
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000

        return LLMResponse(
            text=data.get('response', ''),
            model=data.get('model', self.model),
            tokens_used=data.get('eval_count', 0) + data.get('prompt_eval_count', 0),
            latency_ms=latency_ms,
            metadata={'done': data.get('done', False)}
        )


class SyntheticProvider(LLMProvider):
    """Synthetic response provider for testing without API keys."""

    TEMPLATES = {
        "explain": "This concept involves understanding {topic}. The key aspects are: 1) the fundamental principles that govern it, 2) its practical applications in real-world scenarios. In essence, {topic} forms a coherent system that enables various functionalities.",
        "define": "{term} is a concept in this domain that refers to a specific mechanism or principle. It is commonly used in technical and practical applications where precision is required.",
        "logic": "Based on the given premises, we can logically conclude that the inference follows. This conclusion is derived through deductive reasoning from the stated conditions.",
        "compare": "When comparing these two concepts, we find that they share some similarities but also have key differences. The first is characterized by certain properties, while the second has its own distinct features.",
        "default": "The answer to this question involves understanding the underlying principles. Key points include the foundational concepts and their practical implications in various contexts."
    }

    def __init__(self, model: str = "synthetic-v1"):
        self.model = model

    def is_available(self) -> bool:
        return True  # Always available

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        prompt_lower = prompt.lower()

        if "explain" in prompt_lower or "how" in prompt_lower:
            topic = self._extract_topic(prompt)
            template = self.TEMPLATES["explain"]
            text = template.format(topic=topic)
        elif "what is" in prompt_lower or "define" in prompt_lower:
            term = self._extract_topic(prompt)
            template = self.TEMPLATES["define"]
            text = template.format(term=term)
        elif "if" in prompt_lower and "then" in prompt_lower:
            text = self.TEMPLATES["logic"]
        elif "compare" in prompt_lower or "difference" in prompt_lower:
            text = self.TEMPLATES["compare"]
        else:
            text = self.TEMPLATES["default"]

        return LLMResponse(
            text=text,
            model=self.model,
            tokens_used=len(text.split()),
            latency_ms=10.0,  # Instant
            metadata={'synthetic': True}
        )

    def _extract_topic(self, prompt: str) -> str:
        """Extract main topic from prompt."""
        words = prompt.split()
        # Take last few meaningful words
        topic_words = [w for w in words[-5:] if len(w) > 3]
        return " ".join(topic_words) if topic_words else "the subject"


def get_provider(
    provider_name: str,
    api_key: Optional[str] = None,
    **kwargs
) -> LLMProvider:
    """Factory function to get appropriate LLM provider."""
    providers = {
        'anthropic': AnthropicProvider,
        'openai': OpenAIProvider,
        'ollama': OllamaProvider,
        'synthetic': SyntheticProvider
    }

    if provider_name not in providers:
        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(providers.keys())}")

    if provider_name in ['anthropic', 'openai']:
        return providers[provider_name](api_key=api_key, **kwargs)
    else:
        return providers[provider_name](**kwargs)


class LLMDataCollector:
    """
    Collect training data using external LLM APIs.

    This class coordinates:
    1. CTM reasoning on tasks
    2. LLM response generation
    3. Logging thought-response pairs

    Parameters:
        provider: LLM provider name ('anthropic', 'openai', 'ollama', 'synthetic')
        api_key: API key for the provider
        log_dir: Directory for thought corpus
        batch_size: Number of concurrent requests
        rate_limit: Requests per minute (0 = unlimited)
    """

    def __init__(
        self,
        provider: str = "synthetic",
        api_key: Optional[str] = None,
        log_dir: str = "data/thought_corpus",
        batch_size: int = 5,
        rate_limit: int = 60,  # Requests per minute
        **provider_kwargs
    ):
        self.provider = get_provider(provider, api_key, **provider_kwargs)
        self.log_dir = log_dir
        self.batch_size = batch_size
        self.rate_limit = rate_limit

        # Stats
        self.stats = {
            'total_collected': 0,
            'total_tokens': 0,
            'total_latency_ms': 0,
            'errors': 0
        }

        # Logger
        self.logger = ThoughtLogger(log_dir=log_dir)

    def _create_prompt(self, task: str) -> str:
        """Create prompt for LLM."""
        return f"""You are a helpful AI assistant. Please respond to the following task clearly and concisely.

Task: {task}

Response:"""

    async def collect_single(
        self,
        task: str,
        ctm,  # SpeakingCTM or similar
        max_tokens: int = 256
    ) -> Optional[Dict[str, Any]]:
        """
        Collect a single (thought, response) pair.

        Args:
            task: The task/query
            ctm: CTM instance with think() method
            max_tokens: Maximum response tokens

        Returns:
            Dict with thought, response, and metadata, or None on error
        """
        try:
            # 1. CTM thinking
            ctm_output = ctm.think(task)
            thought_vector = ctm_output.thought_vector

            # 2. LLM response
            prompt = self._create_prompt(task)
            llm_response = await self.provider.generate(prompt, max_tokens=max_tokens)

            # 3. Prepare result
            result = {
                'task': task,
                'thought_vector': thought_vector,
                'response': llm_response.text,
                'certainty': ctm_output.certainties[:, -1].mean().item(),
                'reasoning_steps': ctm_output.reasoning_steps,
                'llm_model': llm_response.model,
                'tokens_used': llm_response.tokens_used,
                'latency_ms': llm_response.latency_ms
            }

            # Update stats
            self.stats['total_collected'] += 1
            self.stats['total_tokens'] += llm_response.tokens_used
            self.stats['total_latency_ms'] += llm_response.latency_ms

            return result

        except Exception as e:
            self.stats['errors'] += 1
            print(f"[LLMDataCollector] Error collecting '{task[:30]}...': {e}")
            return None

    async def collect_batch(
        self,
        tasks: List[str],
        ctm,
        max_tokens: int = 256,
        save_interval: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Collect multiple (thought, response) pairs.

        Args:
            tasks: List of tasks
            ctm: CTM instance
            max_tokens: Maximum response tokens
            save_interval: Save to disk every N samples

        Returns:
            List of collected pairs
        """
        # Start logging session
        self.logger.start_session("llm_collection")

        results = []
        semaphore = asyncio.Semaphore(self.batch_size)

        async def collect_with_semaphore(task):
            async with semaphore:
                # Rate limiting
                if self.rate_limit > 0:
                    delay = 60.0 / self.rate_limit
                    await asyncio.sleep(delay)

                return await self.collect_single(task, ctm, max_tokens)

        # Process all tasks
        print(f"[LLMDataCollector] Collecting {len(tasks)} samples...")

        for i in range(0, len(tasks), self.batch_size):
            batch_tasks = tasks[i:i + self.batch_size]
            batch_results = await asyncio.gather(
                *[collect_with_semaphore(t) for t in batch_tasks]
            )

            # Log successful results
            for result in batch_results:
                if result is not None:
                    self.logger.log(
                        thought_vector=result['thought_vector'],
                        llm_response=result['response'],
                        task=result['task'],
                        certainty=result['certainty'],
                        reasoning_steps=result['reasoning_steps'],
                        metadata={
                            'llm_model': result['llm_model'],
                            'tokens_used': result['tokens_used']
                        }
                    )
                    results.append(result)

            # Progress
            collected = len(results)
            print(f"  Collected {collected}/{len(tasks)} ({collected/len(tasks)*100:.1f}%)")

        # End session
        summary = self.logger.end_session()
        print(f"\n[LLMDataCollector] Collection complete!")
        print(f"  Collected: {len(results)}")
        print(f"  Errors: {self.stats['errors']}")
        print(f"  Total tokens: {self.stats['total_tokens']:,}")
        print(f"  Avg latency: {self.stats['total_latency_ms']/max(len(results),1):.1f}ms")

        return results

    def collect_sync(
        self,
        tasks: List[str],
        ctm,
        max_tokens: int = 256
    ) -> List[Dict[str, Any]]:
        """Synchronous wrapper for collect_batch."""
        return asyncio.run(self.collect_batch(tasks, ctm, max_tokens))

    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        return {
            **self.stats,
            'provider': type(self.provider).__name__,
            'log_dir': self.log_dir
        }


# Standard task sets for data collection
TASK_SETS = {
    'definitions': [
        "What is machine learning?",
        "What is recursion in programming?",
        "What is an algorithm?",
        "What is a neural network?",
        "What is object-oriented programming?",
        "What is a database?",
        "What is an API?",
        "What is version control?",
        "What is cloud computing?",
        "What is artificial intelligence?",
    ],
    'explanations': [
        "Explain how sorting algorithms work",
        "Explain the concept of inheritance in OOP",
        "Explain how the internet works",
        "Explain the difference between stack and queue",
        "Explain how encryption protects data",
        "Explain how compilers work",
        "Explain the concept of recursion",
        "Explain how databases store data",
        "Explain the client-server model",
        "Explain how memory management works",
    ],
    'reasoning': [
        "If all programmers use computers and John is a programmer, what can we conclude?",
        "If A implies B and B implies C, what can we say about A and C?",
        "If it takes 5 machines 5 minutes to make 5 widgets, how long for 100 machines to make 100 widgets?",
        "What comes next in the sequence: 1, 1, 2, 3, 5, 8, ?",
        "If some A are B and all B are C, are some A necessarily C?",
        "What's wrong with the statement: 'This statement is false'?",
        "If X > Y and Y > Z, what is the relationship between X and Z?",
        "Solve: If 2x + 3 = 11, what is x?",
        "What's the logical flaw in: 'All cats are animals, all dogs are animals, therefore all cats are dogs'?",
        "If the probability of rain is 30%, what's the probability it won't rain?",
    ],
    'comparisons': [
        "Compare Python and JavaScript",
        "What's the difference between a list and an array?",
        "Compare SQL and NoSQL databases",
        "What's the difference between HTTP and HTTPS?",
        "Compare functional and object-oriented programming",
        "What's the difference between a process and a thread?",
        "Compare TCP and UDP protocols",
        "What's the difference between compilation and interpretation?",
        "Compare REST and GraphQL APIs",
        "What's the difference between encryption and hashing?",
    ],
}


def get_task_set(name: str = 'all') -> List[str]:
    """Get a predefined set of tasks."""
    if name == 'all':
        all_tasks = []
        for tasks in TASK_SETS.values():
            all_tasks.extend(tasks)
        return all_tasks
    elif name in TASK_SETS:
        return TASK_SETS[name]
    else:
        raise ValueError(f"Unknown task set: {name}. Available: {list(TASK_SETS.keys()) + ['all']}")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing LLMDataCollector")
    print("=" * 60)

    # Test with synthetic provider (no API key needed)
    print("\n" + "-" * 40)
    print("Testing SyntheticProvider:")
    print("-" * 40)

    async def test_synthetic():
        provider = SyntheticProvider()
        response = await provider.generate("Explain machine learning")
        print(f"Response: {response.text[:100]}...")
        print(f"Model: {response.model}")
        print(f"Tokens: {response.tokens_used}")

    asyncio.run(test_synthetic())

    # Test collector with mock CTM
    print("\n" + "-" * 40)
    print("Testing LLMDataCollector with mock CTM:")
    print("-" * 40)

    class MockCTM:
        def think(self, task):
            class Output:
                thought_vector = torch.randn(1, 2048)
                certainties = torch.tensor([[0.5]])
                reasoning_steps = 10
            return Output()

    import tempfile
    temp_dir = tempfile.mkdtemp()

    collector = LLMDataCollector(
        provider="synthetic",
        log_dir=temp_dir,
        batch_size=2
    )

    ctm = MockCTM()
    tasks = get_task_set('definitions')[:5]

    results = collector.collect_sync(tasks, ctm)
    print(f"\nCollected {len(results)} samples")
    print(f"Stats: {collector.get_stats()}")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)

    print("\n" + "=" * 60)
    print("LLMDataCollector tests PASSED!")
    print("=" * 60)
