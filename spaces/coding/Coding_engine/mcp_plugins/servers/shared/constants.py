# -*- coding: utf-8 -*-
"""
Shared constants for all MCP server plugins.
Provides default configuration values that can be overridden by environment variables.
"""
import os

# UI Server Configuration
DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = int(os.getenv("MCP_UI_PORT", "0"))  # 0 = dynamic OS-assigned port

# Tool Names for different plugins
MCP_TOOLS = {
    "github": "GitHub MCP Server",
    "playwright": "Playwright MCP Server",
    "docker": "Docker MCP Server",
    "redis": "Redis MCP Server",
    "postgres": "PostgreSQL MCP Server",
    "npm": "npm/pnpm MCP Server",
    "prisma": "Prisma ORM MCP Server",
    "qdrant": "Qdrant Vector MCP Server",
    "git": "Git MCP Server",
    "time": "Time MCP Server",
    "fetch": "HTTP Fetch MCP Server",
    "filesystem": "Filesystem MCP Server",
    "memory": "Memory MCP Server",
    "supabase": "Supabase MCP Server",
    "desktop": "Desktop Commander MCP Server",
    "n8n": "n8n Workflow MCP Server",
    "tavily": "Tavily Search MCP Server",
    "brave-search": "Brave Search MCP Server",
    "taskmanager": "Task Manager MCP Server",
}

# MCP Event Types (for Society of Mind agents)
MCP_EVENT_SESSION_ANNOUNCE = "SESSION_ANNOUNCE"
MCP_EVENT_AGENT_MESSAGE = "AGENT_MESSAGE"
MCP_EVENT_AGENT_ERROR = "AGENT_ERROR"
MCP_EVENT_TASK_COMPLETE = "TASK_COMPLETE"
MCP_EVENT_CONVERSATION_HISTORY = "CONVERSATION_HISTORY"
MCP_EVENT_USER_INPUT_REQUEST = "USER_INPUT_REQUEST"
MCP_EVENT_USER_INPUT_RESPONSE = "USER_INPUT_RESPONSE"

# Session State Constants
SESSION_STATE_CREATED = "created"
SESSION_STATE_RUNNING = "running"
SESSION_STATE_STOPPED = "stopped"
SESSION_STATE_ERROR = "error"

def get_tool_display_name(tool: str) -> str:
    """Get human-readable display name for a tool."""
    return MCP_TOOLS.get(tool, f"{tool.capitalize()} MCP Server")
