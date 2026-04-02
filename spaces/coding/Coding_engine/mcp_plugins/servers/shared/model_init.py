"""
Shared model initialization utility for all MCP agents.
Provides intelligent model routing via OpenRouter with fallback to legacy config.
Includes runtime fallback for OpenRouter downtime (402 Payment Required errors).
"""
import os
import sys
import json
import importlib.util
from typing import Dict, Any, Optional
from pathlib import Path

# Autogen imports
from autogen_ext.models.openai import OpenAIChatCompletionClient

try:
    from autogen_ext.models.anthropic import AnthropicChatCompletionClient
    ANTHROPIC_CLIENT_AVAILABLE = True
except ImportError:
    ANTHROPIC_CLIENT_AVAILABLE = False

# Import global LLM config
from src.llm_config import get_model


class ResilientModelClient:
    """
    Wrapper around OpenAIChatCompletionClient that falls back to OpenAI
    if OpenRouter returns 402 Payment Required or other failures.
    """
    def __init__(self, primary_client: OpenAIChatCompletionClient, fallback_client: Optional[OpenAIChatCompletionClient] = None):
        self._primary = primary_client
        self._fallback = fallback_client
        self._using_fallback = False

    async def create(self, *args, **kwargs):
        """Try primary client, fall back to OpenAI on 402 errors."""
        if self._using_fallback and self._fallback:
            return await self._fallback.create(*args, **kwargs)

        try:
            return await self._primary.create(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            # Check for 402 Payment Required or OpenRouter downtime
            if "402" in error_str or "payment" in error_str.lower() or "credit" in error_str.lower():
                if self._fallback:
                    print(f"[RUNTIME FALLBACK] OpenRouter returned 402/payment error, switching to OpenAI")
                    print(f"[RUNTIME FALLBACK] Error: {e}")
                    self._using_fallback = True
                    return await self._fallback.create(*args, **kwargs)
            raise

    async def create_stream(self, *args, **kwargs):
        """Try primary client streaming, fall back to OpenAI on 402 errors."""
        if self._using_fallback and self._fallback:
            async for chunk in self._fallback.create_stream(*args, **kwargs):
                yield chunk
            return

        try:
            async for chunk in self._primary.create_stream(*args, **kwargs):
                yield chunk
        except Exception as e:
            error_str = str(e)
            # Check for 402 Payment Required or OpenRouter downtime
            if "402" in error_str or "payment" in error_str.lower() or "credit" in error_str.lower():
                if self._fallback:
                    print(f"[RUNTIME FALLBACK] OpenRouter streaming returned 402/payment error, switching to OpenAI")
                    print(f"[RUNTIME FALLBACK] Error: {e}")
                    self._using_fallback = True
                    async for chunk in self._fallback.create_stream(*args, **kwargs):
                        yield chunk
                    return
            raise

    def __getattr__(self, name):
        """Delegate all other attributes to primary client."""
        if self._using_fallback and self._fallback:
            return getattr(self._fallback, name)
        return getattr(self._primary, name)


def get_plugins_dir() -> str:
    """Get the MCP PLUGINS directory path."""
    # shared/model_init.py is at: .../MCP PLUGINS/servers/shared/model_init.py
    # Go up 2 levels: shared -> servers -> MCP PLUGINS
    current_file = Path(__file__).resolve()  # Get absolute path first
    plugins_dir = current_file.parent.parent.parent  # shared -> servers -> MCP PLUGINS
    return str(plugins_dir)


def get_models_dir() -> str:
    """Get the models directory path."""
    # models/ is a sibling of servers/, not inside github/
    return os.path.join(get_plugins_dir(), "models")


def get_servers_dir() -> str:
    """Get the servers directory path."""
    return os.path.join(get_plugins_dir(), "servers")


def load_model_config(server_name: str) -> Dict[str, Any]:
    """
    Load model configuration for a specific MCP server.

    Args:
        server_name: Name of the MCP server (e.g., "github", "docker")

    Returns:
        Model configuration dict
    """
    # Try server-specific model.json first
    server_dir = os.path.join(get_servers_dir(), server_name)
    model_config_path = os.path.join(server_dir, "model.json")

    if os.path.isfile(model_config_path):
        try:
            with open(model_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    # Fallback to global model config
    global_model_config = os.path.join(get_models_dir(), "model.json")
    if os.path.isfile(global_model_config):
        try:
            with open(global_model_config, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    # Final fallback to environment variables
    return {
        "model": os.getenv("OPENAI_MODEL", get_model("mcp_agent")),
        "base_url": os.getenv("OPENAI_BASE_URL"),
        "api_key_env": "OPENAI_API_KEY"
    }


def init_model_client(mcp_server: str, task: str = "") -> OpenAIChatCompletionClient:
    """
    Initialize model client with intelligent routing for any MCP server.

    This function provides:
    1. Respects llm_models.yml provider setting (anthropic vs openrouter)
    2. OpenRouter support with intelligent model selection based on task complexity
    3. Automatic fallback to legacy configuration if OpenRouter unavailable
    4. Task-aware model selection (reasoning models for complex tasks)

    Args:
        mcp_server: Name of the MCP server (e.g., "github", "docker", "playwright")
        task: Task description (optional, used for intelligent model selection)

    Returns:
        OpenAIChatCompletionClient configured with appropriate model

    Examples:
        # Simple task - uses fast model (Haiku)
        client = init_model_client("github", "List all repositories")

        # Complex reasoning task - uses reasoning model (o1-mini)
        client = init_model_client("github", "Analyze repository architecture and suggest improvements")
    """
    from src.llm_config import get_model_config as get_llm_model_config

    # ── Check if YAML says to use Anthropic directly ──────────────────
    # Determine which role applies to MCP agents
    role = "mcp_agent"
    llm_cfg = get_llm_model_config(role)
    if llm_cfg.get("provider") == "anthropic" and llm_cfg.get("api_key"):
        model_name = llm_cfg["model"]
        api_key = llm_cfg["api_key"]
        print(f"[Anthropic] Using model: {model_name} for {mcp_server} (via llm_models.yml)")

        if ANTHROPIC_CLIENT_AVAILABLE:
            # Native Anthropic client — proper Messages API support
            return AnthropicChatCompletionClient(
                model=model_name,
                api_key=api_key,
            )
        else:
            # Fallback: OpenAI-compatible client with Anthropic base URL
            model_info = {
                "family": "anthropic",
                "function_calling": True,
                "json_output": True,
                "vision": "claude-3" in model_name or "claude-sonnet" in model_name or "claude-opus" in model_name,
            }
            return OpenAIChatCompletionClient(
                model=model_name,
                api_key=api_key,
                base_url="https://api.anthropic.com/v1/",
                model_info=model_info,
            )

    # ── Try OpenRouter (if API key available and YAML provider is openrouter) ──
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        # Import model router - use absolute path
        models_dir = get_models_dir()
        if models_dir not in sys.path:
            sys.path.insert(0, models_dir)

        try:
            # Force reload if already imported to pick up changes
            model_router_path = os.path.join(models_dir, "model_router.py")
            spec = importlib.util.spec_from_file_location("model_router", model_router_path)
            if spec and spec.loader:
                model_router = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(model_router)
                get_model_for_mcp = model_router.get_model_for_mcp
            else:
                raise ImportError("Failed to load model_router module")

            # Get intelligent model selection
            config = get_model_for_mcp(mcp_server, task, openrouter_key)

            # Log model selection for debugging
            model_name = config.get("model", "unknown")
            print(f"[OpenRouter] Using model: {model_name} for {mcp_server}")
            if task:
                print(f"[OpenRouter] Task: {task[:100]}{'...' if len(task) > 100 else ''}")

            # Determine model capabilities for AutoGen v0.4.7+
            # Reasoning models (o1, o3, DeepSeek-R1) don't support function calling
            function_calling_supported = not any(
                reasoning_model in model_name.lower()
                for reasoning_model in ["o1", "o3", "deepseek-r1"]
            )

            # Determine model family from model name
            if "gpt" in model_name.lower() or "openai" in model_name.lower():
                family = "openai"
            elif "claude" in model_name.lower() or "anthropic" in model_name.lower():
                family = "anthropic"
            elif "gemini" in model_name.lower() or "google" in model_name.lower():
                family = "google"
            else:
                family = "unknown"

            model_info = {
                "family": family,
                "function_calling": function_calling_supported,
                "json_output": True,
                "vision": "gpt-4o" in model_name or "claude-3" in model_name or "gemini" in model_name
            }

            # Create OpenRouter primary client
            openrouter_client = OpenAIChatCompletionClient(
                model=config["model"],
                api_key=config["api_key"],
                base_url=config.get("base_url"),
                model_info=model_info,
                extra_headers=config.get("extra_headers", {})
            )

            # Create OpenAI fallback client (always, for runtime failover)
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                print(f"[RESILIENT] Creating OpenAI fallback for runtime 402 errors")
                fallback_client = OpenAIChatCompletionClient(
                    model=get_model("mcp_agent"),  # Fast, cheap fallback
                    api_key=openai_key,
                    model_info=model_info
                )
                return ResilientModelClient(openrouter_client, fallback_client)

            # No fallback available, return OpenRouter only
            return openrouter_client

        except Exception as e:
            print(f"[FALLBACK] OpenRouter initialization failed for {mcp_server}, using OpenAI fallback")
            print(f"[FALLBACK] Error: {e}")
            print(f"[FALLBACK] Reason: OpenRouter may be down or out of credits")

    # Fallback to legacy model.json configuration (OpenAI)
    cfg = load_model_config(mcp_server)
    api_key = os.getenv(cfg.get("api_key_env", "OPENAI_API_KEY"))
    if not api_key:
        raise ValueError(f"Missing API key: {cfg.get('api_key_env')}. Please set in .env file.")

    kwargs = {"model": cfg["model"], "api_key": api_key}
    if cfg.get("base_url"):
        kwargs["base_url"] = cfg["base_url"]

    print(f"[OpenAI] Using model: {cfg['model']} for {mcp_server} (OpenRouter not configured)")

    return OpenAIChatCompletionClient(**kwargs)


def get_available_models(mcp_server: str) -> Dict[str, Any]:
    """
    Get available model configurations for an MCP server.

    Args:
        mcp_server: Name of the MCP server

    Returns:
        Dict with primary, complex, and reasoning model options
    """
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        return {
            "status": "legacy",
            "message": "OpenRouter not configured, using legacy model config"
        }

    models_dir = get_models_dir()
    if models_dir not in sys.path:
        sys.path.insert(0, models_dir)

    try:
        from model_router import ModelRouter

        return {
            "status": "openrouter",
            "primary": ModelRouter.get_model_for_task(mcp_server, "primary"),
            "complex": ModelRouter.get_model_for_task(mcp_server, "complex"),
            "reasoning": ModelRouter.get_model_for_task(mcp_server, "reasoning"),
            "fallback": ModelRouter.get_fallback_models(mcp_server)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
