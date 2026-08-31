# -*- coding: utf-8 -*-
"""
Playwright MCP plugin constants.
"""
import os

# Playwright-specific port (if different from default)
DEFAULT_PLAYWRIGHT_PORT = int(os.getenv("MCP_PLAYWRIGHT_PORT", "0"))

# Default system prompt
DEFAULT_SYSTEM_PROMPT = (
    "You are an AutoGen Assistant wired to an MCP server with browser automation tools (e.g., browser_*).\n"
    "Follow the TOOL USAGE contract strictly and call only the exposed tool names.\n"
    "Dynamic event hint: {MCP_EVENT}.\n"
    "For any browser-related task: navigate safely, wait for relevant selectors, avoid unnecessary actions, and minimize data extraction.\n"
)

# Default task prompt
DEFAULT_TASK_PROMPT = (
    "Use the available tools to accomplish the goal and stream your progress.\n"
    "For Playwright, prefer safe sources (e.g., Wikipedia) and extract minimal text/HTML.\n"
)

# Default servers.json configuration
DEFAULT_SERVERS_JSON = {
    "servers": [
        {
            "name": "playwright",
            "active": True,
            "type": "stdio",
            "command": "npx",
            "args": ["--yes", "@playwright/mcp@latest", "--browser", "msedge"],
            "read_timeout_seconds": 120
        }
    ]
}

# Default model.json configuration
DEFAULT_MODEL_JSON = {
    "model": os.getenv("OPENAI_MODEL") or os.getenv("MODEL") or (
        "llama3.1" if os.getenv("OPENAI_BASE_URL") else "gpt-4o"
    ),
    "base_url": os.getenv("OPENAI_BASE_URL"),
    "api_key_env": "OPENAI_API_KEY"
}