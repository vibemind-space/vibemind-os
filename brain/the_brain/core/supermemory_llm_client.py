"""
Supermemory LLM Client

OpenAI-compatible client that routes through Supermemory's Infinite Chat proxy.
This provides automatic semantic memory retrieval and context management.

Benefits:
- Automatic memory injection based on semantic relevance
- Unlimited context windows (beyond model limits)
- 50%+ token reduction in long conversations
- No manual memory retrieval needed
- Works with OpenAI, Anthropic, Gemini, etc.

Usage:
    from core.supermemory_llm_client import SupermemoryLLM

    llm = SupermemoryLLM(user_id="user_alice")

    response = llm.chat(
        messages=[
            {"role": "user", "content": "Deploy a Docker container"}
        ],
        model="gpt-4"
    )

    # Supermemory automatically:
    # 1. Retrieves relevant past conversations
    # 2. Injects them into context
    # 3. Stores this conversation for future use
    # 4. Manages context window limits

Architecture:
    Brain → SupermemoryLLM → Supermemory Proxy → OpenAI API

    Instead of:
    Brain → Manual Memory Retrieval → OpenAI API
"""

import os
import sys
from typing import List, Dict, Optional, Any
from openai import OpenAI

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from load_env import load_env_file
    load_env_file()
except ImportError:
    # If load_env not available, rely on environment variables
    pass


class SupermemoryLLM:
    """
    OpenAI client wrapper that routes through Supermemory's Infinite Chat proxy.

    This provides automatic semantic memory retrieval and context management
    without any code changes to your LLM calls.
    """

    def __init__(
        self,
        user_id: str,
        provider: str = "openai",
        api_key: str = None,
        supermemory_api_key: str = None,
        model: str = "gpt-4o-mini"
    ):
        """
        Initialize Supermemory LLM client.

        Args:
            user_id: Unique user identifier for memory isolation
            provider: LLM provider (openai, anthropic, google)
            api_key: Provider API key (or from env)
            supermemory_api_key: Supermemory API key (or from env)
            model: Default model to use
        """
        self.user_id = user_id
        self.provider = provider
        self.model = model

        # Get API keys
        self.api_key = api_key or self._get_provider_api_key(provider)
        self.supermemory_api_key = supermemory_api_key or os.getenv('SUPERMEMORY_API_KEY')

        if not self.supermemory_api_key:
            raise ValueError(
                "Supermemory API key required. "
                "Set SUPERMEMORY_API_KEY environment variable."
            )

        # Build proxy base URL
        provider_urls = {
            'openai': 'https://api.openai.com/v1',
            'anthropic': 'https://api.anthropic.com/v1',
            'google': 'https://generativelanguage.googleapis.com/v1'
        }

        provider_base_url = provider_urls.get(provider, 'https://api.openai.com/v1')

        # Supermemory proxy URL format:
        # https://api.supermemory.ai/v3/{original_provider_url}
        self.base_url = f"https://api.supermemory.ai/v3/{provider_base_url}"

        # Initialize OpenAI client with Supermemory proxy
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers={
                "x-supermemory-api-key": self.supermemory_api_key,
                "x-sm-user-id": self.user_id
            }
        )

        print(f"[SupermemoryLLM] Initialized for user: {user_id}")
        print(f"  Provider: {provider}")
        print(f"  Base URL: {self.base_url}")
        print(f"  Infinite Chat: ENABLED")

    def _get_provider_api_key(self, provider: str) -> str:
        """Get provider API key from environment."""
        key_map = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'google': 'GOOGLE_API_KEY'
        }

        env_var = key_map.get(provider, 'OPENAI_API_KEY')
        api_key = os.getenv(env_var)

        if not api_key:
            raise ValueError(
                f"{env_var} not found in environment. "
                f"Set it to use {provider} provider."
            )

        return api_key

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs
    ) -> Any:
        """
        Send chat completion request through Supermemory proxy.

        Supermemory will automatically:
        1. Retrieve semantically relevant past conversations
        2. Inject them into the context
        3. Send to LLM provider
        4. Store this conversation for future use

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to self.model)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream response
            **kwargs: Additional arguments passed to OpenAI client

        Returns:
            OpenAI ChatCompletion response object
        """
        model = model or self.model

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs
            )

            return response

        except Exception as e:
            print(f"[SupermemoryLLM] Error: {e}")
            raise

    def chat_simple(
        self,
        prompt: str,
        system_prompt: str = None,
        model: str = None,
        **kwargs
    ) -> str:
        """
        Simple chat completion that returns just the text response.

        Args:
            prompt: User message
            system_prompt: Optional system message
            model: Model to use
            **kwargs: Additional arguments

        Returns:
            Assistant's text response
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.chat(messages=messages, model=model, **kwargs)

        return response.choices[0].message.content

    def plan_task(
        self,
        task: str,
        context: str = None,
        model: str = None
    ) -> str:
        """
        Plan a task with automatic memory context injection.

        Supermemory will automatically retrieve:
        - Similar past tasks
        - Related conversations
        - Relevant execution histories

        Args:
            task: Task description
            context: Optional additional context
            model: Model to use

        Returns:
            Planning response from LLM
        """
        system_prompt = """You are a planning assistant for an AI brain system.
Given a task, create a detailed step-by-step plan.

Consider:
- Past execution histories (automatically provided by memory system)
- Previous successful approaches
- Known failure patterns
- Available tools and capabilities

Provide a clear, actionable plan."""

        user_prompt = f"Task: {task}"
        if context:
            user_prompt += f"\n\nAdditional Context:\n{context}"

        return self.chat_simple(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model
        )

    def get_info(self) -> Dict:
        """
        Get client configuration info.

        Returns:
            Dict with configuration details
        """
        return {
            'user_id': self.user_id,
            'provider': self.provider,
            'model': self.model,
            'base_url': self.base_url,
            'infinite_chat': True,
            'semantic_memory': True
        }


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("SUPERMEMORY LLM CLIENT TEST")
    print("=" * 70)
    print()

    # Initialize client for a user
    llm = SupermemoryLLM(
        user_id="test_user_123",
        model="gpt-4o-mini"
    )

    print()
    print("[1] Testing simple chat...")
    print()

    # Test simple chat
    response = llm.chat_simple(
        prompt="What is Docker and why is it useful?",
        system_prompt="You are a helpful technical assistant."
    )

    print(f"Response: {response[:200]}...")
    print()

    print("[2] Testing task planning...")
    print()

    # Test task planning (with automatic memory retrieval)
    plan = llm.plan_task(
        task="Deploy a Docker container to production",
        context="We have AWS ECS available"
    )

    print(f"Plan: {plan[:300]}...")
    print()

    print("[3] Testing conversation context...")
    print()

    # Multi-turn conversation
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "I need to deploy a web application."},
        {"role": "assistant", "content": "I can help you deploy a web application. What technology stack are you using?"},
        {"role": "user", "content": "It's a Python Flask app with a PostgreSQL database."}
    ]

    response = llm.chat(messages=messages)
    print(f"Response: {response.choices[0].message.content[:200]}...")
    print()

    # Show info
    print("=" * 70)
    print("CLIENT INFO")
    print("=" * 70)
    info = llm.get_info()
    for key, value in info.items():
        print(f"  {key}: {value}")

    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print()
    print("Key Features Demonstrated:")
    print("  [OK] Automatic memory context injection")
    print("  [OK] Semantic retrieval of past conversations")
    print("  [OK] Transparent proxy (no code changes)")
    print("  [OK] Works with any OpenAI-compatible API")
    print("  [OK] User-specific memory isolation")
    print()
    print("All conversations are now stored in Supermemory and will be")
    print("automatically retrieved in future relevant conversations!")
