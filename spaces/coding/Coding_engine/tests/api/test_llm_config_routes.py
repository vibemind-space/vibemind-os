"""Tests for the LLM Config API routes (src/api/routes/llm_config.py)."""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the route module directly to test helper functions
from src.api.routes.llm_config import (
    _validate_config,
    _get_yaml_path,
    VALID_PROVIDERS,
    VALID_ROLES,
    ModelRoleConfig,
    LLMConfigUpdateRequest,
)


# ── Validation Tests ─────────────────────────────────────────────────────


class TestValidateConfig:
    """Tests for the _validate_config helper."""

    def test_valid_anthropic_config(self):
        models = {
            "primary": ModelRoleConfig(
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                max_tokens=16384,
            )
        }
        result = _validate_config(models)
        assert result.valid is True
        assert result.errors == []

    def test_valid_openrouter_config(self):
        models = {
            "mcp_standard": ModelRoleConfig(
                provider="openrouter",
                model="anthropic/claude-sonnet-4.5",
                max_tokens=8192,
            )
        }
        result = _validate_config(models)
        assert result.valid is True
        assert result.errors == []

    def test_unknown_role(self):
        models = {
            "nonexistent_role": ModelRoleConfig(
                provider="anthropic",
                model="test-model",
                max_tokens=4096,
            )
        }
        result = _validate_config(models)
        assert result.valid is False
        assert any("Unknown role" in e for e in result.errors)

    def test_unknown_provider(self):
        models = {
            "primary": ModelRoleConfig(
                provider="google",
                model="gemini-pro",
                max_tokens=4096,
            )
        }
        result = _validate_config(models)
        assert result.valid is False
        assert any("Unknown provider" in e for e in result.errors)

    def test_empty_model_name(self):
        models = {
            "primary": ModelRoleConfig(
                provider="anthropic",
                model="",
                max_tokens=4096,
            )
        }
        result = _validate_config(models)
        assert result.valid is False
        assert any("cannot be empty" in e for e in result.errors)

    def test_max_tokens_too_low(self):
        models = {
            "primary": ModelRoleConfig(
                provider="anthropic",
                model="test-model",
                max_tokens=100,
            )
        }
        result = _validate_config(models)
        assert result.valid is False
        assert any("256" in e for e in result.errors)

    def test_max_tokens_very_high_warning(self):
        models = {
            "primary": ModelRoleConfig(
                provider="anthropic",
                model="test-model",
                max_tokens=300000,
            )
        }
        result = _validate_config(models)
        assert result.valid is True  # Warning only, not error
        assert len(result.warnings) > 0
        assert any("very high" in w for w in result.warnings)

    def test_anthropic_with_org_prefix_warning(self):
        models = {
            "primary": ModelRoleConfig(
                provider="anthropic",
                model="anthropic/claude-sonnet-4.5",
                max_tokens=4096,
            )
        }
        result = _validate_config(models)
        assert result.valid is True
        assert any("org/ prefix" in w for w in result.warnings)

    def test_openrouter_without_org_prefix_warning(self):
        models = {
            "mcp_standard": ModelRoleConfig(
                provider="openrouter",
                model="claude-sonnet-4.5",
                max_tokens=4096,
            )
        }
        result = _validate_config(models)
        assert result.valid is True
        assert any("org/model" in w for w in result.warnings)

    def test_multiple_roles_all_valid(self):
        models = {
            "primary": ModelRoleConfig(provider="anthropic", model="claude-sonnet-4-20250514", max_tokens=16384),
            "cli": ModelRoleConfig(provider="anthropic", model="claude-sonnet-4-5", max_tokens=16384),
            "judge": ModelRoleConfig(provider="openrouter", model="anthropic/claude-haiku-4.5", max_tokens=4096),
        }
        result = _validate_config(models)
        assert result.valid is True
        assert result.errors == []

    def test_multiple_errors(self):
        models = {
            "bad_role": ModelRoleConfig(provider="bad_provider", model="", max_tokens=10),
        }
        result = _validate_config(models)
        assert result.valid is False
        assert len(result.errors) >= 3  # unknown role + unknown provider + empty model + low tokens


class TestConstants:
    """Tests for module constants."""

    def test_valid_providers(self):
        assert "anthropic" in VALID_PROVIDERS
        assert "openrouter" in VALID_PROVIDERS
        assert len(VALID_PROVIDERS) == 2

    def test_valid_roles(self):
        expected = {"primary", "cli", "mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"}
        assert VALID_ROLES == expected

    def test_yaml_path_points_to_config(self):
        path = _get_yaml_path()
        assert path.name == "llm_models.yml"
        assert "config" in str(path)


class TestModelRoleConfig:
    """Tests for the Pydantic model."""

    def test_basic_creation(self):
        cfg = ModelRoleConfig(provider="anthropic", model="test", max_tokens=4096)
        assert cfg.provider == "anthropic"
        assert cfg.model == "test"
        assert cfg.max_tokens == 4096
        assert cfg.description is None

    def test_with_description(self):
        cfg = ModelRoleConfig(
            provider="openrouter",
            model="org/model",
            max_tokens=8192,
            description="Test model",
        )
        assert cfg.description == "Test model"

    def test_update_request(self):
        req = LLMConfigUpdateRequest(
            models={
                "primary": ModelRoleConfig(provider="anthropic", model="test", max_tokens=4096),
            }
        )
        assert "primary" in req.models
        assert req.models["primary"].model == "test"
