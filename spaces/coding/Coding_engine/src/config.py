"""Application configuration using Pydantic settings."""
from pathlib import Path
from typing import Optional
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Allow extra env vars without raising errors
    )

    # Application
    app_name: str = "coding-engine"
    app_env: str = "development"
    app_debug: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/coding_engine"
    database_pool_size: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic
    anthropic_api_key: Optional[str] = None
    default_model: str = "claude-sonnet-4-5"

    # LLM Backend Selection
    # Options: "openrouter" (default) | "kilo" | "claude"
    # "openrouter" uses API (free models), "kilo" uses Kilo CLI, "claude" uses Claude SDK/CLI
    # NOTE: kilo/claude require interactive login inside the container (kilo auth login / claude login)
    llm_backend: str = "kilo"

    # CLI Model Configuration
    # Model for Claude Code CLI (passed via --model flag)
    # NOTE: cli_wrapper.py reads from llm_models.yml via llm_config.get_model("cli")
    # This fallback is only used if llm_config import fails
    cli_model: str = "claude-sonnet-4-20250514"
    # Model for Kilo Code CLI (passed via --model flag)
    kilo_model: str = "openai/gpt-5.4"

    # OpenRouter (for free models)
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Model category: coding | reasoning | vision | general
    openrouter_model_category: str = "coding"

    # Git
    git_server_url: str = "http://localhost:3000"
    git_username: str = "coding-engine"
    git_password: str = "coding-engine"
    git_email: str = "engine@localhost"

    # Docker / Sandbox
    docker_host: str = "unix:///var/run/docker.sock"
    sandbox_image: str = "coding-engine/sandbox:latest"
    sandbox_memory_limit: str = "512m"
    sandbox_cpu_limit: float = 1.0
    sandbox_timeout: int = 300

    # CLI / Agent Timeouts
    cli_timeout: int = 3600  # Default 60 minutes for Kilo/Claude CLI calls (large feature tasks need >30min)

    # Adaptive Timeout Settings
    base_timeout: int = 600  # Base timeout in seconds (increased for LLM code generation)
    timeout_per_kb: float = 2.0  # Additional seconds per KB of prompt
    max_timeout: int = 1800  # Maximum timeout cap (30 minutes)
    min_timeout: int = 60  # Minimum timeout floor (1 minute)
    streaming_stall_timeout: int = 30  # Seconds with no output before considering stalled

    # Supermemory - Learning and Pattern Memory
    supermemory_enabled: bool = True  # Enable/disable memory features
    supermemory_api_key: Optional[str] = None  # API key for Supermemory
    supermemory_api_url: str = "https://api.supermemory.ai/v3"  # API base URL
    supermemory_container_tag: str = "coding_engine_v1"  # Container tag for all memories

    # VotingAI - Multi-Agent Voting and Consensus
    # Voting methods: majority | qualified_majority | ranked_choice | unanimous | weighted_majority
    voting_enabled: bool = True  # Enable voting for fix selection and verification
    voting_default_method: str = "qualified_majority"  # Default voting method
    voting_qualified_threshold: float = 0.67  # 2/3 majority for qualified voting
    voting_max_rounds: int = 3  # Maximum deliberation rounds
    voting_require_reasoning: bool = True  # Require solvers to provide reasoning
    voting_emit_events: bool = True  # Emit events to dashboard
    voting_proposal_timeout: int = 90  # Seconds per fix proposal (reduced from 120)
    voting_parallel_proposals: bool = True  # Generate proposals in parallel for faster recovery
    voting_stall_timeout: int = 30  # Abort proposal if no output for this many seconds

    # Kilo CLI - Parallel Code Generation
    # Note: Kilo CLI handles auth via interactive login (no API key needed)
    kilo_enabled: bool = True  # Enable Kilo CLI integration
    kilo_parallel_enabled: bool = True  # Enable --parallel mode for branch isolation
    kilo_parallel_workers: int = 3  # Maximum parallel workers
    kilo_parallel_timeout: int = 300  # Timeout per parallel worker (seconds)
    kilo_auto_merge: bool = True  # Automatically merge winning branches

    # A/B Solution Generation
    ab_generation_enabled: bool = True  # Enable A/B solution generation
    ab_num_solutions: int = 2  # Default number of A/B solutions
    ab_require_build_pass: bool = True  # Only consider solutions that build
    ab_require_test_pass: bool = False  # Require tests to pass (stricter)

    # Browser Error Detection
    # Browser options: chrome | firefox | webkit | msedge (NOT chromium!)
    # Playwright MCP only accepts: chrome, firefox, webkit, msedge
    browser_error_detector_browser: str = "chrome"
    browser_error_detector_enabled: bool = True  # Enable/disable browser console error detection

    # Storage
    artifact_storage_path: str = "/data/artifacts"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def get_settings() -> Settings:
    """Get settings instance (no caching - allows runtime config changes)."""
    return Settings()


def calculate_adaptive_timeout(
    prompt: str,
    base_timeout: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> int:
    """
    Calculate adaptive timeout based on prompt size.

    Larger prompts need more time to process. This function calculates
    an appropriate timeout based on the prompt length.

    Args:
        prompt: The prompt text to calculate timeout for
        base_timeout: Override base timeout (default: from settings)
        settings: Settings instance (default: get_settings())

    Returns:
        Calculated timeout in seconds

    Example:
        >>> timeout = calculate_adaptive_timeout("short prompt")  # ~120s
        >>> timeout = calculate_adaptive_timeout("..." * 50000)   # ~220s for 50KB
    """
    if settings is None:
        settings = get_settings()

    # Use provided base or settings default
    base = base_timeout if base_timeout is not None else settings.base_timeout

    # Calculate prompt size in KB
    prompt_kb = len(prompt.encode("utf-8")) / 1024

    # Calculate adaptive timeout: base + (KB * timeout_per_kb)
    adaptive_timeout = base + int(prompt_kb * settings.timeout_per_kb)

    # Clamp to min/max bounds
    clamped_timeout = max(
        settings.min_timeout,
        min(settings.max_timeout, adaptive_timeout)
    )

    return clamped_timeout


def get_stall_timeout(settings: Optional[Settings] = None) -> int:
    """
    Get the streaming stall timeout value.

    This is the number of seconds with no output before
    considering the stream stalled.

    Args:
        settings: Settings instance (default: get_settings())

    Returns:
        Stall timeout in seconds
    """
    if settings is None:
        settings = get_settings()
    return settings.streaming_stall_timeout


# Free Models Configuration
_free_models_cache: Optional[dict] = None


def load_free_models() -> dict:
    """
    Load free models configuration from YAML.

    Returns:
        Dict with model categories and mappings
    """
    global _free_models_cache
    if _free_models_cache is not None:
        return _free_models_cache

    config_path = Path(__file__).parent.parent / "config" / "free_models.yml"
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        _free_models_cache = yaml.safe_load(f)

    return _free_models_cache or {}


def get_free_model(
    category: str = "coding",
    task: Optional[str] = None,
    use_fallback: bool = False,
) -> str:
    """
    Get a free model for the specified category or task.

    Args:
        category: Model category (coding, reasoning, vision, general)
        task: Optional task type to auto-select category
        use_fallback: If True, return first fallback instead of primary

    Returns:
        Model ID string (e.g., "mistralai/devstral-2512:free")
    """
    models = load_free_models()
    if not models:
        return "mistralai/devstral-2512:free"  # Default fallback

    # Auto-select category from task
    if task and "task_mapping" in models:
        category = models["task_mapping"].get(task, category)

    # Get category config
    cat_config = models.get(category, models.get("coding", {}))
    if not cat_config:
        return "mistralai/devstral-2512:free"

    if use_fallback and cat_config.get("fallback"):
        return cat_config["fallback"][0]

    return cat_config.get("primary", "mistralai/devstral-2512:free")


def get_model_context_limit(model_id: str) -> int:
    """
    Get context limit for a model.

    Args:
        model_id: Full model ID

    Returns:
        Context limit in tokens
    """
    models = load_free_models()
    limits = models.get("context_limits", {})
    return limits.get(model_id, 128000)  # Default 128K
