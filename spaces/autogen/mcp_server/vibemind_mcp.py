"""
VibeMind MCP Server — domain-specific tools that no existing Docker MCP server covers.

Runs on port 8809 and exposes tools via /tools/list (GET) and /tools/call (POST),
using the same response format as Docker MCP Gateway.
"""

import re
import json
import logging
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("vibemind-mcp")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="VibeMind MCP Server", version="1.0.0")

TOOL_DEFINITIONS = [
    {
        "name": "web_fetch",
        "description": "Fetch a URL and convert the HTML body to plain markdown text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch."},
                "max_length": {
                    "type": "integer",
                    "description": "Maximum character length of the returned text.",
                    "default": 5000,
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web via DuckDuckGo HTML (no API key required).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "api_docs_fetch",
        "description": "Fetch an OpenAPI/Swagger JSON spec and return an endpoints summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the OpenAPI/Swagger JSON document.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "context7_query",
        "description": "Proxy to Context7 MCP for up-to-date library documentation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_name": {
                    "type": "string",
                    "description": "Name of the library (e.g. 'fastapi', 'autogen').",
                },
                "query": {
                    "type": "string",
                    "description": "Documentation query to search for.",
                },
            },
            "required": ["library_name", "query"],
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HTTP_TIMEOUT = 30.0
HEADERS = {
    "User-Agent": "VibeMind-MCP/1.0 (compatible; +https://vibemind.io)"
}


def _strip_html(html: str) -> str:
    """Rough HTML-to-text conversion: strip tags, collapse whitespace."""
    # Remove script/style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    # Convert common block tags to newlines
    text = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.I)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common entities
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _web_fetch(url: str, max_length: int = 5000) -> str:
    """Fetch URL and convert HTML body to markdown-ish plain text."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    body = resp.text

    if "json" in content_type:
        # Return JSON as-is (pretty-printed), truncated
        try:
            parsed = json.loads(body)
            text = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            text = body
    elif "html" in content_type or body.strip().startswith("<"):
        text = _strip_html(body)
    else:
        text = body

    if len(text) > max_length:
        text = text[:max_length] + f"\n\n... [truncated at {max_length} chars]"

    return text


async def _web_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo HTML and parse results."""
    search_url = "https://html.duckduckgo.com/html/"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        resp = await client.post(search_url, data={"q": query})
        resp.raise_for_status()

    html = resp.text
    results = []

    # Parse result blocks — DuckDuckGo HTML uses class="result"
    result_blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.S,
    )

    for url, title_html, snippet_html in result_blocks[:max_results]:
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
        # DuckDuckGo wraps URLs in a redirect; extract actual URL
        actual_url = url
        uddg_match = re.search(r"uddg=([^&]+)", url)
        if uddg_match:
            from urllib.parse import unquote
            actual_url = unquote(uddg_match.group(1))
        results.append(f"**{title}**\n{actual_url}\n{snippet}")

    if not results:
        return f"No results found for: {query}"

    return "\n\n---\n\n".join(results)


async def _api_docs_fetch(url: str) -> str:
    """Fetch an OpenAPI/Swagger JSON spec and return an endpoints summary."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    try:
        spec = resp.json()
    except Exception:
        return f"Failed to parse JSON from {url}"

    title = spec.get("info", {}).get("title", "Unknown API")
    version = spec.get("info", {}).get("version", "?")
    description = spec.get("info", {}).get("description", "")

    lines = [f"# {title} v{version}"]
    if description:
        lines.append(description[:500])
    lines.append("")

    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            if method in ("get", "post", "put", "patch", "delete", "options", "head"):
                summary = details.get("summary", details.get("description", ""))
                if summary:
                    summary = summary[:120]
                lines.append(f"- **{method.upper()}** `{path}` — {summary}")

    if len(lines) <= 3:
        lines.append("(No paths found in spec)")

    return "\n".join(lines)


async def _context7_query(library_name: str, query: str) -> str:
    """
    Proxy to Context7 MCP server for library documentation.
    Attempts to reach a local Context7 MCP instance; falls back to a helpful
    message if Context7 is not available.
    """
    context7_url = "http://localhost:8808"  # Default Context7 MCP port
    payload = {
        "name": "query-docs",
        "arguments": {
            "library_name": library_name,
            "query": query,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(f"{context7_url}/tools/call", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "content" in data and data["content"]:
                return data["content"][0].get("text", str(data))
            return json.dumps(data, indent=2)
    except Exception as exc:
        logger.warning("Context7 proxy failed: %s", exc)
        # Fallback: try to fetch docs from the web instead
        search_query = f"{library_name} {query} documentation"
        return await _web_search(search_query, max_results=3)


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

TOOL_DISPATCH = {
    "web_fetch": _web_fetch,
    "web_search": _web_search,
    "api_docs_fetch": _api_docs_fetch,
    "context7_query": _context7_query,
}


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/tools/list")
async def list_tools():
    """Return available tools (MCP-compatible format)."""
    return {"tools": TOOL_DEFINITIONS}


@app.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    """
    Call a tool by name with arguments.
    Returns the same format as Docker MCP Gateway:
      {"content": [{"text": "result"}]}
    """
    handler = TOOL_DISPATCH.get(request.name)
    if not handler:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown tool: {request.name}. Available: {list(TOOL_DISPATCH.keys())}",
        )

    try:
        result = await handler(**request.arguments)
    except httpx.HTTPStatusError as exc:
        result = f"HTTP error {exc.response.status_code} fetching {exc.request.url}"
    except httpx.ConnectError as exc:
        result = f"Connection error: {exc}"
    except Exception as exc:
        logger.exception("Tool %s failed", request.name)
        result = f"Tool error: {type(exc).__name__}: {exc}"

    return {"content": [{"text": result}]}


@app.get("/health")
async def health():
    return {"status": "ok", "server": "vibemind-mcp", "port": 8809}
