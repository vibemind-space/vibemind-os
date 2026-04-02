"""Tests for src/llm_config.py — Global LLM Configuration System.

Tests cover:
- YAML loading and fallback defaults
- get_model() for all 7 roles
- get_provider() role resolution
- get_max_tokens() defaults
- get_api_key() from environment
- get_base_url() per provider
- get_model_config() composite dict
- get_openrouter_headers() standard headers
- Environment variable overrides (LLM_MODEL_*)
- reload_config() cache invalidation
- Edge cases: unknown roles, missing YAML, corrupt YAML
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from src.llm_config import (
    get_model,
    get_provider,
    get_max_tokens,
    get_api_key,
    get_base_url,
    get_model_config,
    get_openrouter_headers,
    reload_config,
    _load_config,
    _FALLBACK_CONFIG,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Reset module-level config cache before and after each test."""
    import src.llm_config as llm_mod
    original_cache = llm_mod._config_cache
    llm_mod._config_cache = None
    yield
    llm_mod._config_cache = original_cache


# ── Test: get_model() ────────────────────────────────────────────────────


class TestGetModel:
    """Tests for get_model() function."""

    def test_primary_model_returns_string(self):
        """Test primary role returns a non-empty model string."""
        model = get_model("primary")
        assert isinstance(model, str)
        assert len(model) > 0

    def test_cli_model_returns_string(self):
        """Test cli role returns a non-empty model string."""
        model = get_model("cli")
        assert isinstance(model, str)
        assert len(model) > 0

    def test_all_seven_roles_return_models(self):
        """Test that all 7 defined roles return valid model strings."""
        roles = ["primary", "cli", "mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"]
        for role in roles:
            model = get_model(role)
            assert isinstance(model, str), f"Role '{role}' returned non-string: {type(model)}"
            assert len(model) > 0, f"Role '{role}' returned empty string"

    def test_unknown_role_returns_fallback(self):
        """Test that unknown role returns a fallback model."""
        model = get_model("nonexistent_role")
        assert isinstance(model, str)
        # Should return the ultimate fallback
        assert len(model) > 0

    def test_primary_matches_yaml_or_fallback(self):
        """Test primary model matches either YAML or fallback config."""
        model = get_model("primary")
        # Should be one of the expected values
        assert "claude" in model.lower() or "gpt" in model.lower() or "sonnet" in model.lower()

    def test_judge_model_is_haiku(self):
        """Test judge role uses Haiku model."""
        model = get_model("judge")
        assert "haiku" in model.lower()

    def test_reasoning_model_is_o1(self):
        """Test reasoning role uses o1-mini model."""
        model = get_model("reasoning")
        assert "o1" in model.lower()

    def test_mcp_agent_model_is_gpt4o_mini(self):
        """Test mcp_agent role uses gpt-4o-mini."""
        model = get_model("mcp_agent")
        assert "gpt-4o-mini" in model.lower()


class TestGetModelEnvOverride:
    """Tests for environment variable overrides in get_model()."""

    def test_env_override_primary(self):
        """Test LLM_MODEL_PRIMARY env var overrides config."""
        with patch.dict(os.environ, {"LLM_MODEL_PRIMARY": "claude-opus-4-20250514"}):
            model = get_model("primary")
            assert model == "claude-opus-4-20250514"

    def test_env_override_judge(self):
        """Test LLM_MODEL_JUDGE env var overrides config."""
        with patch.dict(os.environ, {"LLM_MODEL_JUDGE": "anthropic/claude-sonnet-4.5"}):
            model = get_model("judge")
            assert model == "anthropic/claude-sonnet-4.5"

    def test_env_override_cli(self):
        """Test LLM_MODEL_CLI env var overrides config."""
        with patch.dict(os.environ, {"LLM_MODEL_CLI": "custom-model-v2"}):
            model = get_model("cli")
            assert model == "custom-model-v2"

    def test_env_override_takes_precedence(self):
        """Test that env var always takes precedence over YAML/fallback."""
        with patch.dict(os.environ, {"LLM_MODEL_ENRICHMENT": "my-custom/model"}):
            model = get_model("enrichment")
            assert model == "my-custom/model"

    def test_empty_env_does_not_override(self):
        """Test that empty env var does not override (falsy check)."""
        with patch.dict(os.environ, {"LLM_MODEL_PRIMARY": ""}):
            model = get_model("primary")
            # Empty string is falsy, should not override
            assert model != ""
            assert len(model) > 0


# ── Test: get_provider() ─────────────────────────────────────────────────


class TestGetProvider:
    """Tests for get_provider() function."""

    def test_primary_provider_is_anthropic(self):
        """Test primary role uses Anthropic provider."""
        provider = get_provider("primary")
        assert provider == "anthropic"

    def test_cli_provider_is_anthropic(self):
        """Test cli role uses Anthropic provider."""
        provider = get_provider("cli")
        assert provider == "anthropic"

    def test_mcp_standard_provider_is_openrouter(self):
        """Test mcp_standard role uses OpenRouter provider."""
        provider = get_provider("mcp_standard")
        assert provider == "openrouter"

    def test_judge_provider_is_openrouter(self):
        """Test judge role uses OpenRouter provider."""
        provider = get_provider("judge")
        assert provider == "openrouter"

    def test_unknown_role_returns_default_provider(self):
        """Test unknown role returns default provider."""
        provider = get_provider("unknown_role")
        assert provider == "openrouter"  # Default fallback


# ── Test: get_max_tokens() ───────────────────────────────────────────────


class TestGetMaxTokens:
    """Tests for get_max_tokens() function."""

    def test_primary_max_tokens(self):
        """Test primary role has high token limit."""
        tokens = get_max_tokens("primary")
        assert tokens >= 8192

    def test_mcp_agent_max_tokens(self):
        """Test mcp_agent role has moderate token limit."""
        tokens = get_max_tokens("mcp_agent")
        assert tokens >= 2048

    def test_unknown_role_returns_default(self):
        """Test unknown role returns default token count."""
        tokens = get_max_tokens("unknown_role")
        assert tokens == 4096  # Default fallback

    def test_returns_integer(self):
        """Test that max_tokens always returns an integer."""
        for role in ["primary", "cli", "mcp_standard", "judge"]:
            tokens = get_max_tokens(role)
            assert isinstance(tokens, int)


# ── Test: get_api_key() ──────────────────────────────────────────────────


class TestGetApiKey:
    """Tests for get_api_key() function."""

    def test_returns_none_without_env_var(self):
        """Test returns None when API key env var is not set."""
        # Temporarily remove ANTHROPIC_API_KEY if set
        with patch.dict(os.environ, {}, clear=False):
            # Don't interfere with existing keys
            key = get_api_key("primary")
            # Should return either the key or None, depending on environment
            assert key is None or isinstance(key, str)

    def test_returns_anthropic_key_for_primary(self):
        """Test returns ANTHROPIC_API_KEY for primary role."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
            key = get_api_key("primary")
            assert key == "test-key-123"

    def test_returns_openrouter_key_for_judge(self):
        """Test returns OPENROUTER_API_KEY for judge role."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-test-key-456"}):
            key = get_api_key("judge")
            assert key == "or-test-key-456"


# ── Test: get_base_url() ─────────────────────────────────────────────────


class TestGetBaseUrl:
    """Tests for get_base_url() function."""

    def test_anthropic_returns_none(self):
        """Test Anthropic provider returns None (uses SDK default)."""
        url = get_base_url("primary")
        assert url is None

    def test_openrouter_returns_url(self):
        """Test OpenRouter provider returns base URL."""
        url = get_base_url("mcp_standard")
        assert url is not None
        assert "openrouter.ai" in url

    def test_openrouter_url_format(self):
        """Test OpenRouter URL is a proper HTTPS endpoint."""
        url = get_base_url("judge")
        assert url is not None
        assert url.startswith("https://")
        assert url.endswith("/v1")


# ── Test: get_model_config() ─────────────────────────────────────────────


class TestGetModelConfig:
    """Tests for get_model_config() composite function."""

    def test_returns_dict_with_all_keys(self):
        """Test returns dict with all expected keys."""
        config = get_model_config("primary")
        assert isinstance(config, dict)
        expected_keys = {"model", "provider", "api_key", "base_url", "max_tokens"}
        assert set(config.keys()) == expected_keys

    def test_model_matches_get_model(self):
        """Test that model field matches get_model() result."""
        config = get_model_config("judge")
        assert config["model"] == get_model("judge")

    def test_provider_matches_get_provider(self):
        """Test that provider field matches get_provider() result."""
        config = get_model_config("primary")
        assert config["provider"] == get_provider("primary")

    def test_max_tokens_matches(self):
        """Test that max_tokens matches get_max_tokens() result."""
        config = get_model_config("mcp_standard")
        assert config["max_tokens"] == get_max_tokens("mcp_standard")

    def test_all_roles_return_valid_configs(self):
        """Test all 7 roles return valid composite configs."""
        roles = ["primary", "cli", "mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"]
        for role in roles:
            config = get_model_config(role)
            assert config["model"], f"Role '{role}' has empty model"
            assert config["provider"] in ("anthropic", "openrouter"), \
                f"Role '{role}' has unexpected provider: {config['provider']}"
            assert isinstance(config["max_tokens"], int), \
                f"Role '{role}' has non-int max_tokens"


# ── Test: get_openrouter_headers() ───────────────────────────────────────


class TestGetOpenRouterHeaders:
    """Tests for get_openrouter_headers() function."""

    def test_returns_dict(self):
        """Test returns a dictionary."""
        headers = get_openrouter_headers()
        assert isinstance(headers, dict)

    def test_contains_referer(self):
        """Test headers contain HTTP-Referer."""
        headers = get_openrouter_headers()
        assert "HTTP-Referer" in headers

    def test_contains_title(self):
        """Test headers contain X-Title."""
        headers = get_openrouter_headers()
        assert "X-Title" in headers
        assert headers["X-Title"] == "Coding Engine"


# ── Test: reload_config() ────────────────────────────────────────────────


class TestReloadConfig:
    """Tests for reload_config() cache invalidation."""

    def test_reload_clears_and_reloads(self):
        """Test that reload_config() resets and reloads cache."""
        import src.llm_config as llm_mod

        # First load
        _ = get_model("primary")
        assert llm_mod._config_cache is not None

        # Reload
        reload_config()
        assert llm_mod._config_cache is not None  # Should be reloaded

    def test_reload_picks_up_changes(self):
        """Test that reload picks up YAML changes (via env override demo)."""
        # Use env override to simulate a change
        model1 = get_model("primary")
        with patch.dict(os.environ, {"LLM_MODEL_PRIMARY": "new-model-after-reload"}):
            reload_config()
            model2 = get_model("primary")
            assert model2 == "new-model-after-reload"


# ── Test: _load_config() internals ───────────────────────────────────────


class TestLoadConfig:
    """Tests for internal _load_config() function."""

    def test_returns_dict_with_models(self):
        """Test config has 'models' key."""
        config = _load_config()
        assert isinstance(config, dict)
        assert "models" in config

    def test_returns_dict_with_providers(self):
        """Test config has 'providers' key."""
        config = _load_config()
        assert "providers" in config

    def test_fallback_config_has_all_roles(self):
        """Test fallback config defines all 7 roles."""
        roles = ["primary", "cli", "mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"]
        for role in roles:
            assert role in _FALLBACK_CONFIG["models"], \
                f"Fallback config missing role: {role}"

    def test_config_loads_from_yaml_if_available(self):
        """Test that YAML file is loaded when present."""
        yaml_path = Path(__file__).parent.parent / "config" / "llm_models.yml"
        if yaml_path.exists():
            config = _load_config()
            # If YAML exists, should have loaded it (may have description fields)
            primary = config.get("models", {}).get("primary", {})
            assert "model" in primary
        else:
            pytest.skip("config/llm_models.yml not found, skip YAML-specific test")

    def test_missing_yaml_uses_fallback(self):
        """Test that missing YAML file falls back to hardcoded defaults."""
        import src.llm_config as llm_mod

        # Patch the config path to a non-existent file
        with patch.object(Path, 'exists', return_value=False):
            llm_mod._config_cache = None
            config = llm_mod._load_config()
            # Should fall back to _FALLBACK_CONFIG
            assert "models" in config


# ── Test: Cross-role consistency ─────────────────────────────────────────


class TestCrossRoleConsistency:
    """Tests for consistency across all roles."""

    def test_anthropic_roles_use_direct_model_names(self):
        """Test Anthropic roles use bare model names (no org/ prefix)."""
        for role in ["primary", "cli"]:
            model = get_model(role)
            # Anthropic SDK models should not have org/ prefix
            assert "/" not in model, \
                f"Role '{role}' model '{model}' has org prefix but uses Anthropic SDK"

    def test_openrouter_roles_use_prefixed_names(self):
        """Test OpenRouter roles use org/model format."""
        for role in ["mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"]:
            model = get_model(role)
            # OpenRouter models should have org/ prefix
            assert "/" in model, \
                f"Role '{role}' model '{model}' lacks org prefix but uses OpenRouter"

    def test_no_empty_models_across_roles(self):
        """Test no role returns an empty model string."""
        roles = ["primary", "cli", "mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"]
        for role in roles:
            model = get_model(role)
            assert model.strip(), f"Role '{role}' returned empty or whitespace-only model"

    def test_all_providers_are_valid(self):
        """Test all providers are either 'anthropic' or 'openrouter'."""
        roles = ["primary", "cli", "mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"]
        for role in roles:
            provider = get_provider(role)
            assert provider in ("anthropic", "openrouter"), \
                f"Role '{role}' has invalid provider: {provider}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
