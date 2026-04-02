# -*- coding: utf-8 -*-
"""
Model client utilities for MCP agents.
Provides unified model client creation for OpenAI-compatible APIs.
"""
import os
from typing import Any, AsyncGenerator, Mapping, Sequence, Union
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core import CancellationToken, FunctionCall
from autogen_core.models import (
    CreateResult,
    LLMMessage,
    ModelInfo,
    RequestUsage,
)


class EmptyArgsSafeModelClient(OpenAIChatCompletionClient):
    """
    A wrapper around OpenAIChatCompletionClient that fixes empty tool arguments.

    When models return tool calls with empty arguments (empty string instead of "{}"),
    this wrapper ensures they are converted to valid empty JSON objects.
    """

    def _fix_empty_arguments(self, result: CreateResult) -> CreateResult:
        """Fix empty string arguments in FunctionCall objects."""
        if isinstance(result.content, list):
            for item in result.content:
                if isinstance(item, FunctionCall):
                    # Fix empty arguments: "" -> "{}"
                    if item.arguments == "" or item.arguments is None:
                        # FunctionCall.arguments is a string field, not a dict
                        # We need to set it to a valid empty JSON string
                        object.__setattr__(item, 'arguments', '{}')
                    elif isinstance(item.arguments, str):
                        # Also handle whitespace-only arguments
                        stripped = item.arguments.strip()
                        if stripped == "" or stripped is None:
                            object.__setattr__(item, 'arguments', '{}')
        return result

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Any] = [],
        json_output: bool | type[Any] | None = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: CancellationToken | None = None,
    ) -> CreateResult:
        """Override create to fix empty arguments in tool calls."""
        result = await super().create(
            messages,
            tools=tools,
            json_output=json_output,
            extra_create_args=extra_create_args,
            cancellation_token=cancellation_token,
        )
        return self._fix_empty_arguments(result)

    async def create_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Any] = [],
        json_output: bool | type[Any] | None = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: CancellationToken | None = None,
    ) -> AsyncGenerator[Union[str, CreateResult], None]:
        """Override create_stream to fix empty arguments in final result."""
        async for item in super().create_stream(
            messages,
            tools=tools,
            json_output=json_output,
            extra_create_args=extra_create_args,
            cancellation_token=cancellation_token,
        ):
            if isinstance(item, CreateResult):
                yield self._fix_empty_arguments(item)
            else:
                yield item

# Model capabilities for non-OpenAI models used via OpenRouter
MODEL_INFO_REGISTRY = {
    "anthropic/claude-opus-4.5": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "anthropic/claude-opus-4": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "anthropic/claude-opus-4-20250514": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "anthropic/claude-sonnet-4.5": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "anthropic/claude-haiku-4.5": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "anthropic/claude-sonnet-4": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "anthropic/claude-3.5-sonnet": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "anthropic/claude-3-opus": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="claude",
    ),
    "google/gemini-2.0-flash": ModelInfo(
        vision=True,
        function_calling=True,
        json_output=True,
        structured_output=True,
        family="gemini",
    ),
    "meta-llama/llama-3.3-70b-instruct": ModelInfo(
        vision=False,
        function_calling=True,
        json_output=True,
        structured_output=False,
        family="llama",
    ),
}


def get_model_client(model: str) -> EmptyArgsSafeModelClient:
    """
    Create an OpenAI-compatible chat completion client with empty args fix.

    This uses EmptyArgsSafeModelClient which automatically fixes empty tool
    arguments ("" -> "{}") to prevent JSON parsing errors.

    Args:
        model: Model identifier (e.g., "gpt-4o", "openai/gpt-4o-mini", "llama3.1")

    Returns:
        EmptyArgsSafeModelClient instance configured for the specified model

    Environment Variables:
        OPENAI_API_KEY: API key for OpenAI or compatible service
        OPENAI_BASE_URL: Optional base URL for API (e.g., for local models)
        OPENAI_MODEL: Optional default model override

    Examples:
        >>> client = get_model_client("gpt-4o")
        >>> client = get_model_client("openai/gpt-4o-mini")
    """
    # Get API configuration from environment
    # Priority: OpenRouter > OpenAI > Local
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL")  # For local models

    if openrouter_key:
        # Use OpenRouter API - keep full model name with provider prefix
        # OpenRouter expects format like "anthropic/claude-opus-4.5" or "openai/gpt-4o"

        # Get model_info for non-OpenAI models
        model_info = MODEL_INFO_REGISTRY.get(model)

        if model_info:
            client = EmptyArgsSafeModelClient(
                model=model,  # Keep full name for OpenRouter
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                model_info=model_info
            )
        else:
            # For OpenAI models or unknown models, let AutoGen figure it out
            client = EmptyArgsSafeModelClient(
                model=model,
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1"
            )
    elif base_url:
        # Use custom base URL (local inference)
        # Strip provider prefix if present (e.g., "openai/gpt-4o" -> "gpt-4o")
        model_name = model.split("/", 1)[1] if "/" in model else model
        client = EmptyArgsSafeModelClient(
            model=model_name,
            api_key=openai_key,
            base_url=base_url
        )
    else:
        # Use OpenAI API directly
        # Strip provider prefix if present (e.g., "openai/gpt-4o" -> "gpt-4o")
        model_name = model.split("/", 1)[1] if "/" in model else model
        client = EmptyArgsSafeModelClient(
            model=model_name,
            api_key=openai_key
        )

    return client


def get_default_model() -> str:
    """
    Get the default model from environment or use fallback.

    Returns:
        Model identifier string

    Environment Variables:
        OPENAI_MODEL: Preferred model name
        MODEL: Alternative model name variable
        OPENAI_BASE_URL: If set, defaults to "llama3.1" for local inference

    Fallback:
        - "gpt-4o" if using OpenAI API
        - "llama3.1" if using local inference (OPENAI_BASE_URL set)
    """
    # Check environment variables
    model = os.getenv("OPENAI_MODEL") or os.getenv("MODEL")

    if model:
        return model

    # Fallback based on whether we're using local inference
    if os.getenv("OPENAI_BASE_URL"):
        return "llama3.1"  # Common local model
    else:
        return "gpt-4o"  # OpenAI default


if __name__ == "__main__":
    # Test model client creation
    print("Testing model client creation...")

    test_model = get_default_model()
    print(f"Default model: {test_model}")

    try:
        client = get_model_client(test_model)
        print(f"✓ Successfully created client for model: {test_model}")
        print(f"  Type: {type(client).__name__}")
    except Exception as e:
        print(f"✗ Error creating client: {e}")
