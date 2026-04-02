"""
WebFetchPipe — enriches CoderAgent context with API documentation fetched
via the VibeMind MCP server.
"""

import re
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger("web-fetch-pipe")


class WebFetchPipe:
    """Enriches CoderAgent context with API documentation fetched via web."""

    def __init__(self, mcp_url: str = "http://localhost:8809"):
        self.mcp_url = mcp_url
        self._timeout = 30.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enrich_coder_context(
        self,
        task_description: str,
        yaml_architecture: Optional[str] = None,
    ) -> str:
        """
        Build an enrichment string for the CoderAgent by:
          1. Extracting API/library references from the task description
          2. Fetching docs for each via web_fetch or api_docs_fetch
          3. Fetching AutoGen patterns via context7_query
          4. Returning a combined enrichment string

        Args:
            task_description: The coding task in natural language.
            yaml_architecture: Optional YAML architecture spec that may
                               contain additional library/API references.

        Returns:
            A markdown-formatted enrichment string ready to prepend to the
            CoderAgent system prompt or task context.
        """
        sections: list[str] = []

        # 1. Extract references
        references = self._extract_references(task_description, yaml_architecture)
        logger.info("Extracted references: %s", references)

        # 2. Fetch documentation for URLs (OpenAPI specs or regular pages)
        for ref in references.get("urls", []):
            doc = await self._fetch_url_docs(ref)
            if doc:
                sections.append(f"## Documentation: {ref}\n\n{doc}")

        # 3. Fetch library docs via web search or context7
        for lib in references.get("libraries", []):
            doc = await self._fetch_library_docs(lib, task_description)
            if doc:
                sections.append(f"## Library: {lib}\n\n{doc}")

        # 4. Always fetch AutoGen patterns if relevant
        if self._mentions_autogen(task_description, yaml_architecture):
            patterns = await self._fetch_autogen_patterns(task_description)
            if patterns:
                sections.append(f"## AutoGen Patterns\n\n{patterns}")

        if not sections:
            return ""

        header = "# Enriched Context (auto-fetched documentation)\n\n"
        return header + "\n\n---\n\n".join(sections)

    # ------------------------------------------------------------------
    # Reference extraction
    # ------------------------------------------------------------------

    def _extract_references(
        self,
        task_description: str,
        yaml_architecture: Optional[str] = None,
    ) -> dict[str, list[str]]:
        """Extract URLs and library names from task text and architecture YAML."""
        combined = task_description
        if yaml_architecture:
            combined += "\n" + yaml_architecture

        # Extract URLs
        urls = re.findall(r"https?://[^\s\)\]\},\"']+", combined)
        # Deduplicate while preserving order
        seen = set()
        unique_urls = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)

        # Extract library/package names via common patterns
        libraries: list[str] = []

        # pip install / npm install patterns
        install_matches = re.findall(
            r"(?:pip install|npm install|yarn add|pnpm add)\s+([\w\-]+)",
            combined,
            re.I,
        )
        libraries.extend(install_matches)

        # import patterns (Python)
        import_matches = re.findall(
            r"(?:^|\n)\s*(?:import|from)\s+([\w]+)", combined
        )
        libraries.extend(import_matches)

        # Common well-known libraries mentioned by name
        known_libs = [
            "fastapi", "flask", "django", "express", "nextjs", "react",
            "autogen", "langchain", "llamaindex", "openai", "anthropic",
            "httpx", "requests", "pydantic", "sqlalchemy", "prisma",
            "tailwind", "shadcn", "supabase", "firebase",
        ]
        lower_combined = combined.lower()
        for lib in known_libs:
            if lib in lower_combined and lib not in libraries:
                libraries.append(lib)

        # Deduplicate libraries
        seen_libs = set()
        unique_libs = []
        for lib in libraries:
            lib_lower = lib.lower()
            if lib_lower not in seen_libs:
                seen_libs.add(lib_lower)
                unique_libs.append(lib)

        return {"urls": unique_urls, "libraries": unique_libs}

    # ------------------------------------------------------------------
    # Fetching helpers
    # ------------------------------------------------------------------

    async def _call_tool(self, name: str, arguments: dict) -> Optional[str]:
        """Call a tool on the VibeMind MCP server."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self.mcp_url}/tools/call",
                    json={"name": name, "arguments": arguments},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content", [])
                if content:
                    return content[0].get("text")
                return None
        except Exception as exc:
            logger.warning("MCP tool call %s failed: %s", name, exc)
            return None

    async def _fetch_url_docs(self, url: str) -> Optional[str]:
        """Fetch a URL. Use api_docs_fetch for OpenAPI specs, web_fetch otherwise."""
        # Heuristic: if URL looks like an OpenAPI spec
        if any(kw in url.lower() for kw in [
            "openapi", "swagger", "/api-docs", "/v2/api-docs", "/v3/api-docs",
        ]) or url.endswith(".json"):
            doc = await self._call_tool("api_docs_fetch", {"url": url})
            if doc and "Failed to parse" not in doc:
                return doc

        # Fall back to regular fetch
        return await self._call_tool("web_fetch", {"url": url, "max_length": 5000})

    async def _fetch_library_docs(self, library: str, task: str) -> Optional[str]:
        """Fetch documentation for a library, preferring context7 then web search."""
        # Try context7 first
        doc = await self._call_tool(
            "context7_query",
            {"library_name": library, "query": task[:200]},
        )
        if doc and "No results" not in doc:
            return doc

        # Fall back to web search
        return await self._call_tool(
            "web_search",
            {"query": f"{library} documentation tutorial", "max_results": 3},
        )

    async def _fetch_autogen_patterns(self, task: str) -> Optional[str]:
        """Fetch AutoGen-specific patterns from context7."""
        return await self._call_tool(
            "context7_query",
            {"library_name": "autogen", "query": f"agent pattern for: {task[:150]}"},
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _mentions_autogen(
        task: str, yaml_arch: Optional[str] = None
    ) -> bool:
        combined = task.lower()
        if yaml_arch:
            combined += " " + yaml_arch.lower()
        return any(kw in combined for kw in ["autogen", "agent team", "agent farm", "multi-agent"])
