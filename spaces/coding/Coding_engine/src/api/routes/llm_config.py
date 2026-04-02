"""
FastAPI routes for LLM Configuration management.

Provides REST endpoints to read and update config/llm_models.yml
from the dashboard, enabling live model switching without code changes.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/llm-config", tags=["LLM Config"])


# ── Pydantic Models ──────────────────────────────────────────────────────

class ModelRoleConfig(BaseModel):
    """Configuration for a single model role."""
    provider: str
    model: str
    max_tokens: int
    description: Optional[str] = None


class ProviderConfig(BaseModel):
    """Configuration for a provider."""
    base_url: Optional[str] = None
    api_key_env: str


class LLMConfigResponse(BaseModel):
    """Full LLM configuration response."""
    providers: Dict[str, ProviderConfig]
    models: Dict[str, ModelRoleConfig]
    source: str  # "yaml" or "fallback"
    yaml_path: str


class LLMConfigUpdateRequest(BaseModel):
    """Request to update one or more model roles."""
    models: Dict[str, ModelRoleConfig]


class ModelRoleUpdateRequest(BaseModel):
    """Request to update a single model role."""
    provider: str
    model: str
    max_tokens: int
    description: Optional[str] = None


class LLMConfigValidationResponse(BaseModel):
    """Validation result for config changes."""
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


# ── Helper Functions ─────────────────────────────────────────────────────

def _get_yaml_path() -> Path:
    """Get absolute path to llm_models.yml."""
    return Path(__file__).parent.parent.parent.parent / "config" / "llm_models.yml"


def _load_yaml() -> tuple[Dict[str, Any], str]:
    """Load YAML config. Returns (config_dict, source)."""
    import yaml

    yaml_path = _get_yaml_path()
    if yaml_path.exists():
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if config and "models" in config:
                return config, "yaml"
        except Exception as e:
            logger.warning("yaml_load_failed", error=str(e))

    # Return fallback
    from src.llm_config import _FALLBACK_CONFIG
    return _FALLBACK_CONFIG, "fallback"


def _save_yaml(config: Dict[str, Any]) -> None:
    """Save config back to llm_models.yml."""
    import yaml

    yaml_path = _get_yaml_path()

    # Build YAML content with header comments
    header = """# config/llm_models.yml \u2014 SINGLE SOURCE OF TRUTH for all LLM models
# Edit THIS file to change any model globally across the entire system.
#
# Roles:
#   primary      - Anthropic SDK direct (base agent, vision, monitor)
#   cli          - Claude CLI / Kilo CLI --model flag
#   mcp_standard - AutoGen teams, EventFix orchestrator, task executor
#   mcp_agent    - Individual MCP plugin agents (filesystem, docker, etc.)
#   judge        - MCMP judge, fungus agents, differential analysis
#   reasoning    - Complex reasoning, architecture analysis
#   enrichment   - Phase 30 schema discovery, task mapping
#
# Override any model via environment variable:
#   LLM_MODEL_PRIMARY=claude-opus-4-20250514
#   LLM_MODEL_JUDGE=anthropic/claude-sonnet-4.5
#   etc.

"""

    yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)

    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(yaml_content)


VALID_PROVIDERS = {"anthropic", "openrouter", "openai", "gemini", "ollama", "custom"}
VALID_ROLES = {"primary", "cli", "mcp_standard", "mcp_agent", "judge", "reasoning", "enrichment"}


def _validate_config(models: Dict[str, ModelRoleConfig]) -> LLMConfigValidationResponse:
    """Validate model configuration changes."""
    errors = []
    warnings = []

    for role, cfg in models.items():
        if role not in VALID_ROLES:
            errors.append(f"Unknown role: '{role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}")

        if cfg.provider not in VALID_PROVIDERS:
            errors.append(f"Role '{role}': Unknown provider '{cfg.provider}'. Valid: {', '.join(VALID_PROVIDERS)}")

        if not cfg.model or not cfg.model.strip():
            errors.append(f"Role '{role}': Model name cannot be empty")

        if cfg.max_tokens < 256:
            errors.append(f"Role '{role}': max_tokens must be >= 256 (got {cfg.max_tokens})")

        if cfg.max_tokens > 200000:
            warnings.append(f"Role '{role}': max_tokens is very high ({cfg.max_tokens}), this may exceed model limits")

        # Provider-model consistency checks
        if cfg.provider == "anthropic" and "/" in cfg.model:
            warnings.append(
                f"Role '{role}': Anthropic SDK models typically don't use org/ prefix (got '{cfg.model}')"
            )
        if cfg.provider == "openrouter" and "/" not in cfg.model:
            warnings.append(
                f"Role '{role}': OpenRouter models typically use org/model format (got '{cfg.model}')"
            )

    return LLMConfigValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ── API Endpoints ────────────────────────────────────────────────────────

@router.get("", response_model=LLMConfigResponse)
async def get_llm_config() -> LLMConfigResponse:
    """
    Get the current LLM configuration.

    Returns all model roles, providers, and the source (yaml or fallback).
    """
    try:
        config, source = _load_yaml()

        providers = {}
        for name, pcfg in config.get("providers", {}).items():
            providers[name] = ProviderConfig(
                base_url=pcfg.get("base_url"),
                api_key_env=pcfg.get("api_key_env", ""),
            )

        models = {}
        for role, mcfg in config.get("models", {}).items():
            models[role] = ModelRoleConfig(
                provider=mcfg.get("provider", "openrouter"),
                model=mcfg.get("model", ""),
                max_tokens=mcfg.get("max_tokens", 4096),
                description=mcfg.get("description"),
            )

        return LLMConfigResponse(
            providers=providers,
            models=models,
            source=source,
            yaml_path=str(_get_yaml_path()),
        )

    except Exception as e:
        logger.error("llm_config_get_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to read LLM config: {str(e)}")


@router.put("", response_model=LLMConfigResponse)
async def update_llm_config(request: LLMConfigUpdateRequest) -> LLMConfigResponse:
    """
    Update one or more model roles in the LLM configuration.

    Validates the config before saving and triggers a reload.
    """
    try:
        # Validate first
        validation = _validate_config(request.models)
        if not validation.valid:
            raise HTTPException(
                status_code=422,
                detail={"errors": validation.errors, "warnings": validation.warnings},
            )

        # Load current config
        config, _ = _load_yaml()

        # Merge updates
        for role, new_cfg in request.models.items():
            if "models" not in config:
                config["models"] = {}
            config["models"][role] = {
                "provider": new_cfg.provider,
                "model": new_cfg.model,
                "max_tokens": new_cfg.max_tokens,
                "description": new_cfg.description or config["models"].get(role, {}).get("description", ""),
            }

        # Save to YAML
        _save_yaml(config)

        # Reload the module-level cache
        from src.llm_config import reload_config
        reload_config()

        logger.info(
            "llm_config_updated",
            roles_updated=list(request.models.keys()),
        )

        # Return the updated config
        return await get_llm_config()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("llm_config_update_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update LLM config: {str(e)}")


@router.put("/role/{role}", response_model=LLMConfigResponse)
async def update_single_role(role: str, request: ModelRoleUpdateRequest) -> LLMConfigResponse:
    """
    Update a single model role.

    Convenience endpoint for updating one role at a time.
    """
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role: '{role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}",
        )

    update = LLMConfigUpdateRequest(
        models={
            role: ModelRoleConfig(
                provider=request.provider,
                model=request.model,
                max_tokens=request.max_tokens,
                description=request.description,
            )
        }
    )
    return await update_llm_config(update)


@router.post("/validate", response_model=LLMConfigValidationResponse)
async def validate_config(request: LLMConfigUpdateRequest) -> LLMConfigValidationResponse:
    """
    Validate configuration changes without saving.

    Returns validation errors and warnings.
    """
    return _validate_config(request.models)


# ── API Key Management ──────────────────────────────────────────────────

# Keys that can be managed via UI (whitelist for security)
MANAGED_KEY_ENVS = {
    "ANTHROPIC_API_KEY": "Anthropic",
    "OPENROUTER_API_KEY": "OpenRouter",
    "OPENAI_API_KEY": "OpenAI",
    "GEMINI_API_KEY": "Google Gemini",
}


class APIKeyStatus(BaseModel):
    """Status of a single API key."""
    env_var: str
    provider: str
    is_set: bool
    preview: Optional[str] = None  # e.g. "sk-ant-...rdA" (first 6 + last 3)


class APIKeySetRequest(BaseModel):
    """Request to set an API key."""
    env_var: str
    value: str


class APIKeySetResponse(BaseModel):
    """Response after setting an API key."""
    env_var: str
    provider: str
    is_set: bool
    preview: str
    persisted: bool


def _key_preview(key: str) -> str:
    """Generate safe preview: first 8 chars + ... + last 3 chars."""
    if not key or len(key) < 12:
        return "***"
    return f"{key[:8]}...{key[-3:]}"


@router.get("/api-keys", response_model=List[APIKeyStatus])
async def get_api_key_status() -> List[APIKeyStatus]:
    """
    Get the status of all managed API keys (set/unset, safe preview).

    Never returns the full key value.
    """
    import os
    result = []
    for env_var, provider in MANAGED_KEY_ENVS.items():
        value = os.environ.get(env_var, "")
        result.append(APIKeyStatus(
            env_var=env_var,
            provider=provider,
            is_set=bool(value),
            preview=_key_preview(value) if value else None,
        ))
    return result


@router.put("/api-keys", response_model=APIKeySetResponse)
async def set_api_key(request: APIKeySetRequest) -> APIKeySetResponse:
    """
    Set an API key in the running process environment.

    Also persists to .env file in project root for container restarts.
    """
    import os

    if request.env_var not in MANAGED_KEY_ENVS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown env var '{request.env_var}'. Allowed: {', '.join(MANAGED_KEY_ENVS.keys())}",
        )

    if not request.value or not request.value.strip():
        raise HTTPException(status_code=422, detail="API key value cannot be empty")

    value = request.value.strip()

    # Set in current process environment (immediate effect)
    os.environ[request.env_var] = value

    # Persist to .env file for container restarts
    persisted = False
    try:
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        lines = []
        found = False

        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(f"{request.env_var}="):
                        lines.append(f"{request.env_var}={value}\n")
                        found = True
                    else:
                        lines.append(line)

        if not found:
            lines.append(f"{request.env_var}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        persisted = True
        logger.info("api_key_persisted", env_var=request.env_var, env_path=str(env_path))

    except Exception as e:
        logger.warning("api_key_persist_failed", env_var=request.env_var, error=str(e))

    logger.info("api_key_set", env_var=request.env_var, provider=MANAGED_KEY_ENVS[request.env_var])

    return APIKeySetResponse(
        env_var=request.env_var,
        provider=MANAGED_KEY_ENVS[request.env_var],
        is_set=True,
        preview=_key_preview(value),
        persisted=persisted,
    )


@router.delete("/api-keys/{env_var}")
async def remove_api_key(env_var: str):
    """Remove an API key from the environment."""
    import os

    if env_var not in MANAGED_KEY_ENVS:
        raise HTTPException(status_code=422, detail=f"Unknown env var '{env_var}'")

    os.environ.pop(env_var, None)

    # Also remove from .env file
    try:
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = [l for l in f if not l.strip().startswith(f"{env_var}=")]
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
    except Exception:
        pass

    logger.info("api_key_removed", env_var=env_var)
    return {"success": True, "env_var": env_var}


@router.post("/reload")
async def reload_llm_config():
    """
    Force reload the LLM config from YAML.

    Clears the module-level cache and reloads from disk.
    """
    try:
        from src.llm_config import reload_config
        reload_config()

        logger.info("llm_config_reloaded")
        return {"success": True, "message": "LLM config reloaded from YAML"}

    except Exception as e:
        logger.error("llm_config_reload_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to reload: {str(e)}")
