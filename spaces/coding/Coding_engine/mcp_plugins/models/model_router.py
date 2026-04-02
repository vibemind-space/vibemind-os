"""
Model Router for MCP Agents.
Provides intelligent model selection based on MCP server type and task complexity.
"""
import os
from typing import Dict, Any
from src.llm_config import get_model


# Default models for different task types via OpenRouter
MODELS = {
    "fast": get_model("mcp_standard"),      # Sonnet 4.5 for fast tasks
    "standard": get_model("mcp_standard"),  # Sonnet 4.5 for standard tasks
    "complex": get_model("mcp_standard"),   # Sonnet 4.5 for complex reasoning
    "reasoning": get_model("reasoning"),    # Deep reasoning tasks (keep o1-mini)
}

# MCP server to default model tier mapping
MCP_MODEL_TIERS = {
    # Simple operations - use fast model
    "time": "fast",
    "fetch": "fast",
    "memory": "fast",

    # Standard operations
    "git": "standard",
    "npm": "standard",
    "prisma": "standard",
    "filesystem": "standard",
    "docker": "standard",
    "redis": "standard",
    "taskmanager": "standard",

    # Complex operations - may need better reasoning
    "github": "standard",
    "playwright": "standard",
    "qdrant": "standard",
    "postgres": "standard",
    "supabase": "standard",
    "desktop": "standard",
    "n8n": "standard",

    # Search - linguistic understanding
    "tavily": "standard",
    "brave-search": "standard",
    "context7": "standard",
}

# Task keywords that suggest complexity
COMPLEX_KEYWORDS = [
    "analyze", "architecture", "design", "refactor", "optimize",
    "debug", "investigate", "complex", "multiple", "comprehensive"
]

REASONING_KEYWORDS = [
    "reason", "think through", "step by step", "explain why",
    "prove", "derive", "mathematical", "logical"
]


def get_model_for_mcp(mcp_server: str, task: str = "", api_key: str = None) -> Dict[str, Any]:
    """
    Get the appropriate model configuration for an MCP server and task.

    Args:
        mcp_server: Name of the MCP server (e.g., "git", "docker")
        task: Task description for complexity analysis
        api_key: OpenRouter API key

    Returns:
        Dict with model configuration including model, api_key, base_url
    """
    # Determine base tier from MCP server
    tier = MCP_MODEL_TIERS.get(mcp_server, "standard")

    # Upgrade tier based on task complexity
    if task:
        task_lower = task.lower()

        # Check for reasoning keywords
        if any(kw in task_lower for kw in REASONING_KEYWORDS):
            tier = "reasoning"
        # Check for complex keywords
        elif any(kw in task_lower for kw in COMPLEX_KEYWORDS):
            tier = "complex"

    # Get model for tier
    model = MODELS.get(tier, MODELS["standard"])

    # Build configuration
    config = {
        "model": model,
        "api_key": api_key or os.getenv("OPENROUTER_API_KEY"),
        "base_url": "https://openrouter.ai/api/v1",
        "extra_headers": {
            "HTTP-Referer": "https://coding-engine.local",
            "X-Title": f"Coding Engine MCP - {mcp_server}"
        }
    }

    return config


def get_available_models() -> Dict[str, str]:
    """Get all available model tiers and their models."""
    return MODELS.copy()
