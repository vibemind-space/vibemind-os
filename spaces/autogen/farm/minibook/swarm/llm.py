"""LLM wrappers — Dual-provider: Anthropic (Claude) + OpenAI (GPT-4o).

Switch via LLM_PROVIDER env var (default: anthropic).
Anthropic uses the native Messages API with adaptive thinking.
OpenAI uses the Chat Completions API as before.
"""

import base64
import json
from pathlib import Path

from .constants import (
    LLM_PROVIDER, DEFAULT_MODEL,
    anthropic_client, openai_client,
)
from .knowledge import _handle_rag_tool_call


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# OpenAI models that require max_completion_tokens instead of max_tokens
_NEW_TOKEN_PARAM_MODELS = {"gpt-5.4", "gpt-5.4-pro", "o3", "o3-pro", "o4-mini"}


def _oai_token_kwarg(max_tokens: int) -> dict:
    """Return the correct max-tokens parameter for the current OpenAI model."""
    if any(DEFAULT_MODEL.startswith(m) for m in _NEW_TOKEN_PARAM_MODELS):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def _extract_text(response) -> str:
    """Extract text from an Anthropic Message response."""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


# ---------------------------------------------------------------------------
# call_gpt4o — plain text response
# ---------------------------------------------------------------------------

async def call_gpt4o(system_prompt: str, user_content: str, max_tokens: int = 4096) -> str:
    """Call the configured LLM provider. Returns plain text."""
    if LLM_PROVIDER == "anthropic":
        return await _anthropic_text(system_prompt, user_content, max_tokens)
    return await _openai_text(system_prompt, user_content, max_tokens)


async def _anthropic_text(system_prompt: str, user_content: str, max_tokens: int) -> str:
    try:
        response = await anthropic_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            temperature=0.4,
        )
        return _extract_text(response)
    except Exception as e:
        return f"[Anthropic Error: {e}]"


async def _openai_text(system_prompt: str, user_content: str, max_tokens: int) -> str:
    try:
        response = await openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            **_oai_token_kwarg(max_tokens),
            temperature=0.4,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[OpenAI Error: {e}]"


# ---------------------------------------------------------------------------
# call_gpt4o_json — JSON response
# ---------------------------------------------------------------------------

async def call_gpt4o_json(system_prompt: str, user_content: str, max_tokens: int = 2048) -> dict:
    """Call LLM with JSON response format. Returns parsed dict or empty dict."""
    if LLM_PROVIDER == "anthropic":
        return await _anthropic_json(system_prompt, user_content, max_tokens)
    return await _openai_json(system_prompt, user_content, max_tokens)


async def _anthropic_json(system_prompt: str, user_content: str, max_tokens: int) -> dict:
    try:
        # Anthropic: instruct JSON in system prompt + parse from text
        json_system = system_prompt + "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanation."
        response = await anthropic_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=json_system,
            messages=[{"role": "user", "content": user_content}],
            temperature=0.2,
        )
        text = _extract_text(response)
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        print(f"  [!] Anthropic JSON parse error: {e}")
        return {}
    except Exception as e:
        print(f"  [!] Anthropic JSON call error: {e}")
        return {}


async def _openai_json(system_prompt: str, user_content: str, max_tokens: int) -> dict:
    try:
        response = await openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            **_oai_token_kwarg(max_tokens),
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [!] OpenAI JSON parse error: {e}")
        return {}
    except Exception as e:
        print(f"  [!] OpenAI JSON call error: {e}")
        return {}


# ---------------------------------------------------------------------------
# call_gpt4o_with_tools — multi-turn tool calling
# ---------------------------------------------------------------------------

async def call_gpt4o_with_tools(system_prompt: str, user_content: str,
                                tools: list = None, max_tokens: int = 4096,
                                max_turns: int = 5) -> str:
    """Multi-turn LLM call with tool calling support (RAG tools)."""
    if LLM_PROVIDER == "anthropic":
        return await _anthropic_with_tools(system_prompt, user_content, tools, max_tokens, max_turns)
    return await _openai_with_tools(system_prompt, user_content, tools, max_tokens, max_turns)


def _convert_tools_oai_to_anthropic(oai_tools: list) -> list:
    """Convert OpenAI-format tool definitions to Anthropic format."""
    if not oai_tools:
        return []
    anthropic_tools = []
    for t in oai_tools:
        func = t.get("function", t)
        anthropic_tools.append({
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })
    return anthropic_tools


async def _anthropic_with_tools(system_prompt: str, user_content: str,
                                tools: list, max_tokens: int, max_turns: int) -> str:
    anthropic_tools = _convert_tools_oai_to_anthropic(tools)
    messages = [{"role": "user", "content": user_content}]

    for turn in range(max_turns):
        kwargs = {
            "model": DEFAULT_MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
            "temperature": 0.4,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            response = await anthropic_client.messages.create(**kwargs)
        except Exception as e:
            return f"[Anthropic Error: {e}]"

        # Check for tool use
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            return _extract_text(response)

        # Process tool calls
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_use_blocks:
            result = _handle_rag_tool_call(tu.name, tu.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result,
            })
            print(f"  [RAG] Tool call: {tu.name}({tu.input}) -> {len(result)} chars")
        messages.append({"role": "user", "content": tool_results})

    # Max turns reached — force final response without tools
    try:
        response = await anthropic_client.messages.create(
            model=DEFAULT_MODEL, max_tokens=max_tokens,
            system=system_prompt, messages=messages, temperature=0.4,
        )
        return _extract_text(response)
    except Exception as e:
        return f"[Anthropic Error: {e}]"


async def _openai_with_tools(system_prompt: str, user_content: str,
                             tools: list, max_tokens: int, max_turns: int) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    for turn in range(max_turns):
        kwargs = {
            "model": DEFAULT_MODEL,
            "messages": messages,
            **_oai_token_kwarg(max_tokens),
            "temperature": 0.4,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await openai_client.chat.completions.create(**kwargs)
        except Exception as e:
            return f"[OpenAI Error: {e}]"

        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""

        messages.append(msg)
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result = _handle_rag_tool_call(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
            print(f"  [RAG] Tool call: {tc.function.name}({args}) -> {len(result)} chars")

    try:
        response = await openai_client.chat.completions.create(
            model=DEFAULT_MODEL, messages=messages,
            **_oai_token_kwarg(max_tokens), temperature=0.4,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"[OpenAI Error: {e}]"


# ---------------------------------------------------------------------------
# Vision calls
# ---------------------------------------------------------------------------

def _image_mime(image_path: Path) -> str:
    ext = image_path.suffix.lower()
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp"}.get(ext.lstrip("."), "image/png")


async def call_gpt4o_vision(system_prompt: str, user_text: str, image_path: Path,
                            max_tokens: int = 4096, detail: str = "high") -> str:
    """Call LLM with an image input. Returns text response."""
    if LLM_PROVIDER == "anthropic":
        return await _anthropic_vision(system_prompt, user_text, image_path, max_tokens)
    return await _openai_vision(system_prompt, user_text, image_path, max_tokens, detail)


async def _anthropic_vision(system_prompt: str, user_text: str, image_path: Path,
                            max_tokens: int) -> str:
    try:
        mime = _image_mime(image_path)
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        response = await anthropic_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": mime, "data": b64,
                    }},
                    {"type": "text", "text": user_text},
                ],
            }],
            temperature=0.3,
        )
        return _extract_text(response)
    except Exception as e:
        return f"[Anthropic Vision Error: {e}]"


async def _openai_vision(system_prompt: str, user_text: str, image_path: Path,
                         max_tokens: int, detail: str) -> str:
    try:
        mime = _image_mime(image_path)
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        response = await openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{b64}", "detail": detail,
                    }},
                ]},
            ],
            **_oai_token_kwarg(max_tokens),
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[OpenAI Vision Error: {e}]"


async def call_gpt4o_vision_json(system_prompt: str, user_text: str, image_path: Path,
                                 max_tokens: int = 4096, detail: str = "high") -> dict:
    """Call LLM with image input and JSON response. Returns parsed dict."""
    if LLM_PROVIDER == "anthropic":
        return await _anthropic_vision_json(system_prompt, user_text, image_path, max_tokens)
    return await _openai_vision_json(system_prompt, user_text, image_path, max_tokens, detail)


async def _anthropic_vision_json(system_prompt: str, user_text: str, image_path: Path,
                                 max_tokens: int) -> dict:
    try:
        mime = _image_mime(image_path)
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        json_system = system_prompt + "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanation."
        response = await anthropic_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=json_system,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": mime, "data": b64,
                    }},
                    {"type": "text", "text": user_text},
                ],
            }],
            temperature=0.2,
        )
        text = _extract_text(response)
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        print(f"  [!] Anthropic Vision JSON parse error: {e}")
        return {}
    except Exception as e:
        print(f"  [!] Anthropic Vision JSON call error: {e}")
        return {}


async def _openai_vision_json(system_prompt: str, user_text: str, image_path: Path,
                              max_tokens: int, detail: str) -> dict:
    try:
        mime = _image_mime(image_path)
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        response = await openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{b64}", "detail": detail,
                    }},
                ]},
            ],
            **_oai_token_kwarg(max_tokens),
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [!] OpenAI Vision JSON parse error: {e}")
        return {}
    except Exception as e:
        print(f"  [!] OpenAI Vision JSON call error: {e}")
        return {}
