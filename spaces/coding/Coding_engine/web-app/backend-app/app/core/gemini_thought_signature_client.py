"""
Gemini Chat Completion Client with thought_signature support.

This module provides a chat completion client for Gemini models that properly
handles thought_signature preservation for function calling.
"""

import json
import logging
from typing import Any, Dict, Literal, Mapping, Optional, Sequence

import httpx
from autogen_core import CancellationToken
from autogen_core.models import CreateResult, LLMMessage, ModelInfo
from autogen_core.tools import Tool, ToolSchema
from autogen_ext.models.openai import BaseOpenAIChatCompletionClient
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class _ThoughtSignatureHTTPClient(httpx.AsyncClient):
    """
    Custom HTTP client that intercepts requests and responses for thought_signature handling.

    Gemini's OpenAI-compatible API includes thought_signature in the response at:
    tool_calls[].extra_content.google.thought_signature

    This client:
    1. Extracts thought_signature from responses when the model makes function calls
    2. Injects thought_signature back into requests when sending function results

    The OpenAI SDK discards the extra_content field, so we intercept at the HTTP level.
    """

    def __init__(self, signature_store: Dict[str, str], *args, **kwargs):
        """
        Initialize the HTTP client with a shared signature store.

        Args:
            signature_store: Dictionary to store thought signatures mapped by call_id
            *args: Additional positional arguments for httpx.AsyncClient
            **kwargs: Additional keyword arguments for httpx.AsyncClient
        """
        super().__init__(*args, **kwargs)
        self._signature_store = signature_store

    async def send(self, request, *args, **kwargs):
        """
        Override send to intercept requests and responses.

        This method:
        1. Intercepts outgoing requests to inject thought_signature into tool calls
        2. Sends the request (possibly modified)
        3. Intercepts incoming responses to extract thought_signature from tool calls

        Args:
            request: The httpx.Request to send
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            The httpx.Response from the server
        """
        # Step 1: Intercept outgoing request to inject thought_signature
        if "chat/completions" in str(request.url) and request.method == "POST":
            try:
                # Read the request content
                content_bytes = b""
                if hasattr(request, "stream"):
                    async for chunk in request.stream:
                        content_bytes += chunk
                elif hasattr(request, "content"):
                    content_bytes = request.content

                if content_bytes:
                    request_data = json.loads(content_bytes)
                    messages = request_data.get("messages", [])
                    modified = False

                    # Check each assistant message for tool calls that need thought_signature
                    for message in messages:
                        if message.get("role") == "assistant" and "tool_calls" in message:
                            for tool_call in message["tool_calls"]:
                                call_id = tool_call.get("id")

                                # Inject stored thought_signature if available
                                if call_id and call_id in self._signature_store:
                                    signature = self._signature_store[call_id]

                                    if "extra_content" not in tool_call:
                                        tool_call["extra_content"] = {}
                                    if "google" not in tool_call["extra_content"]:
                                        tool_call["extra_content"]["google"] = {}

                                    tool_call["extra_content"]["google"]["thought_signature"] = signature
                                    modified = True

                                    logger.debug(
                                        f"Injected thought_signature for call_id {call_id}: {signature[:50]}..."
                                    )

                    # Create new request with modified content if needed
                    if modified:
                        new_content = json.dumps(request_data).encode("utf-8")
                        request = httpx.Request(
                            method=request.method,
                            url=request.url,
                            headers={
                                k: v
                                for k, v in request.headers.items()
                                if k.lower() not in ["content-length", "transfer-encoding"]
                            },
                            content=new_content,
                        )

            except Exception as e:
                logger.warning(f"Error injecting thought_signature: {e}")

        # Step 2: Send the request
        response = await super().send(request, *args, **kwargs)

        # Step 3: Intercept incoming response to extract thought_signature
        if (
            response.status_code == 200
            and "chat/completions" in str(request.url)
            and request.method == "POST"
        ):
            try:
                data = json.loads(response.text)

                # Extract thought_signature from tool calls in the response
                if "choices" in data:
                    for choice in data["choices"]:
                        message = choice.get("message", {})
                        tool_calls = message.get("tool_calls", [])

                        for tool_call in tool_calls:
                            extra_content = tool_call.get("extra_content", {})
                            google_data = extra_content.get("google", {})
                            thought_sig = google_data.get("thought_signature")

                            if thought_sig:
                                call_id = tool_call.get("id")
                                if call_id:
                                    self._signature_store[call_id] = thought_sig
                                    logger.debug(
                                        f"Extracted thought_signature for call_id {call_id}: {thought_sig[:50]}..."
                                    )

            except Exception as e:
                logger.warning(f"Error extracting thought_signature: {e}")

        return response


class GeminiThoughtSignatureClient(BaseOpenAIChatCompletionClient):
    """
    Chat completion client for Gemini models with thought_signature support.

    This client extends BaseOpenAIChatCompletionClient to properly handle Gemini's
    thought_signature requirement for function calling.

    **Gemini's thought_signature requirement:**

    When using function calling with Gemini's OpenAI-compatible API, the model includes
    a thought_signature in its responses. This signature must be preserved and sent back
    with function execution results to maintain reasoning context.

    **Implementation:**

    This client uses a custom HTTP client to:

    1. Intercept responses and extract thought_signature from tool calls
    2. Store signatures mapped by function call ID
    3. Inject signatures back into requests when sending function results

    **Usage:**

    .. code-block:: python

        from app.core.gemini_thought_signature_client import GeminiThoughtSignatureClient
        from autogen_core.models import UserMessage

        client = GeminiThoughtSignatureClient(
            model="gemini-3-flash-preview",
            api_key="your-api-key",  # Optional if GEMINI_API_KEY is set
            temperature=0.7,
            max_tokens=64000,
        )

        result = await client.create(
            messages=[UserMessage(content="What's the weather?", source="user")],
            tools=[weather_tool],
        )

    Args:
        model (optional, str): Model name. Defaults to settings.GEMINI_MODEL.
        api_key (optional, str): API key. Defaults to settings.GEMINI_API_KEY.
        base_url (optional, str): Base URL. Defaults to settings.GEMINI_API_BASE_URL.
        temperature (optional, float): Sampling temperature. Defaults to 0.7.
        max_tokens (optional, int): Maximum output tokens. Defaults to 64000 (Gemini-3 Flash max).
        **kwargs: Additional arguments passed to BaseOpenAIChatCompletionClient.

    Note:
        - Gemini-3 Flash supports up to 1M input tokens and 64K output tokens
        - parallel_tool_calls is automatically disabled for stability
        - For production use with complex tool calling, consider Claude 3.5 Sonnet or GPT-4o

    See Also:
        - Gemini thought_signature documentation: https://ai.google.dev/gemini-api/docs/thought-signatures
        - BaseOpenAIChatCompletionClient: The parent class this extends
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 64000,
        **kwargs,
    ):
        """
        Initialize Gemini client with thought_signature capture.

        Args:
            model: Model name (defaults to settings.GEMINI_MODEL)
            api_key: API key (defaults to settings.GEMINI_API_KEY)
            base_url: Base URL (defaults to settings.GEMINI_API_BASE_URL)
            temperature: Sampling temperature
            max_tokens: Maximum output tokens (Gemini-3 Flash: 64K)
            **kwargs: Additional arguments passed to parent
        """
        # Use settings if not provided
        model = model or settings.GEMINI_MODEL
        api_key = api_key or settings.GEMINI_API_KEY
        base_url = base_url or settings.GEMINI_API_BASE_URL

        # Store thought signatures: {call_id: thought_signature}
        self._thought_signatures: Dict[str, str] = {}

        # Create custom HTTP client that intercepts requests/responses
        http_client = _ThoughtSignatureHTTPClient(
            signature_store=self._thought_signatures,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

        # Create AsyncOpenAI client with our custom HTTP client
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
        )

        # Define model capabilities for Gemini-3 Flash
        model_info = ModelInfo(
            vision=True,
            function_calling=True,
            json_output=True,
            family="unknown",
            structured_output=True,
        )

        # Prepare create args
        create_args = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "parallel_tool_calls": False,  # Disable for stability
        }

        # Initialize parent class
        super().__init__(
            client=client,
            create_args=create_args,
            model_info=model_info,
            **kwargs,
        )

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
        tool_choice: Tool | Literal["auto", "required", "none"] = "auto",
        json_output: bool | type[BaseModel] | None = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: CancellationToken | None = None,
    ) -> CreateResult:
        """
        Create completion with automatic thought_signature handling.

        The custom HTTP client automatically:
        - Captures thought_signature from responses
        - Injects thought_signature into subsequent requests

        Args:
            messages: Sequence of messages
            tools: Available tools
            tool_choice: Tool selection mode
            json_output: Whether to use JSON output
            extra_create_args: Extra arguments
            cancellation_token: Cancellation token

        Returns:
            CreateResult with the model's response

        Raises:
            Exception: If the API request fails
        """
        try:
            result = await super().create(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                json_output=json_output,
                extra_create_args=extra_create_args,
                cancellation_token=cancellation_token,
            )
            return result

        except Exception as e:
            error_msg = str(e)

            # Provide helpful error message if thought_signature error occurs
            if "thought_signature" in error_msg:
                logger.error(
                    "Gemini thought_signature error occurred. "
                    "This should not happen with GeminiThoughtSignatureClient. "
                    f"Signatures in store: {len(self._thought_signatures)}. "
                    f"Error: {error_msg}"
                )

            raise
