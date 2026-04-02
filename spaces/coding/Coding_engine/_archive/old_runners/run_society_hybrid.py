#!/usr/bin/env python3
"""
Society of Mind Hybrid Runner - Full Autonomous Code Generation.

This script combines:
1. Project Scaffolding for guaranteed structure
2. HybridPipeline for initial code generation
3. Society of Mind for continuous testing, building, and fixing
4. Completeness checking to verify all requirements implemented
5. Continuous Sandbox Testing - 30-second deployment verification loop

Usage:
    python run_society_hybrid.py requirements.json --output-dir ./output

    # Full autonomous mode (default) - keeps running until 100% complete
    python run_society_hybrid.py requirements.json --autonomous

    # With continuous sandbox testing (30-second cycles from start)
    python run_society_hybrid.py requirements.json --continuous-sandbox --enable-vnc

The system will:
1. Scaffold complete project structure
2. Install all dependencies
3. Start continuous sandbox loop (if enabled) - tests every 30 seconds
4. Generate initial code from requirements
5. Start live preview (http://localhost:5173)
6. Continuously run tests, builds, and validators
7. Automatically fix ALL failures
8. Verify completeness of implementation
9. Only stop when 100% working OR hard timeout (1 hour)
"""

# Load environment variables from .env FIRST before any other imports
# This ensures ANTHROPIC_API_KEY is available for Claude SDK
from pathlib import Path as _Path
from dotenv import load_dotenv as _load_dotenv
_env_path = _Path(__file__).parent / '.env'
if _env_path.exists():
    _load_dotenv(_env_path)

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# Fix Windows encoding issue - ensure UTF-8 for all streams
# This prevents 'charmap' codec errors with Unicode characters like → ≤ ≥
if sys.platform == 'win32':
    import io
    # Wrap stdout/stderr with UTF-8 encoding
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.mind.integration import (
    HybridSocietyConfig,
    HybridSocietyRunner,
    run_hybrid_society,
)
from src.mind.convergence import (
    ConvergenceCriteria,
    STRICT_CRITERIA,
    RELAXED_CRITERIA,
    FAST_ITERATION_CRITERIA,
    DEFAULT_CRITERIA,
    AUTONOMOUS_CRITERIA,
)
# Direct module imports to avoid circular import issues
from src.scaffolding.project_initializer import ProjectInitializer, initialize_project
from src.mind.completeness_checker import CompletenessChecker, check_completeness
from src.engine.tech_stack import TechStack, load_tech_stack
from src.tools.dev_container_tool import start_dev_container

# Optional: Claude Monitor for AI-powered error analysis
try:
    from src.monitoring.claude_monitor import ClaudeMonitor, create_monitor
    HAS_CLAUDE_MONITOR = True
except ImportError:
    HAS_CLAUDE_MONITOR = False
    ClaudeMonitor = None
    create_monitor = None

# Design Pipeline for pre-generation planning
try:
    from src.design import DesignPipeline
    from src.design.models import ExecutionPlan
    HAS_DESIGN_PIPELINE = True
except ImportError:
    HAS_DESIGN_PIPELINE = False
    DesignPipeline = None
    ExecutionPlan = None


# ============================================================================
# DEFAULT CONFIGURATION AND OUTPUT DIRECTORY GENERATION
# ============================================================================

def load_society_defaults() -> dict:
    """Load default configuration from config/society_defaults.json."""
    config_file = Path(__file__).parent / "config" / "society_defaults.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def get_next_output_dir(base_pattern: str = "output", requirements_file: str = None) -> str:
    """
    Generate incremental output directory with UUID.

    Format: output_{incremental_id}_{short_uuid}
    Example: output_001_a3f2b1c8

    Tracks history in Data/run_history.json
    """
    history_file = Path(__file__).parent / "Data" / "run_history.json"

    if history_file.exists():
        try:
            history = json.loads(history_file.read_text())
            next_id = history.get("last_id", 0) + 1
        except json.JSONDecodeError:
            history = {"last_id": 0, "runs": []}
            next_id = 1
    else:
        history = {"last_id": 0, "runs": []}
        next_id = 1

    short_uuid = uuid.uuid4().hex[:8]
    output_dir = f"{base_pattern}_{next_id:03d}_{short_uuid}"

    # Update history
    history["last_id"] = next_id
    history["runs"].append({
        "id": next_id,
        "uuid": short_uuid,
        "timestamp": datetime.now().isoformat(),
        "output_dir": output_dir,
        "requirements_file": requirements_file,
    })

    # Keep only last 100 runs in history
    if len(history["runs"]) > 100:
        history["runs"] = history["runs"][-100:]

    history_file.parent.mkdir(exist_ok=True)
    history_file.write_text(json.dumps(history, indent=2))

    return output_dir


def apply_defaults_to_args(args, defaults: dict) -> None:
    """
    Apply default configuration values to args.
    CLI arguments take precedence over defaults.
    """
    # Boolean flags that should be True by default
    bool_flags = [
        "autonomous", "continuous_sandbox", "enable_vnc", "enable_sandbox",
        "enable_validation", "validation_docker", "dashboard", "persistent_deploy",
        "verbose", "inject_secrets", "shell_stream"
    ]

    for key, value in defaults.items():
        arg_name = key.replace("-", "_")

        if hasattr(args, arg_name):
            current = getattr(args, arg_name)

            # For boolean flags, only apply if not explicitly set to True on CLI
            if arg_name in bool_flags:
                if current is False or current is None:
                    setattr(args, arg_name, value)
            # For non-boolean, apply if None or default value
            elif current is None:
                setattr(args, arg_name, value)


# ============================================================================
# REQUIREMENT PARSING HELPERS
# ============================================================================

def _extract_requirements_list(requirements) -> list[str]:
    """Extract a list of requirement descriptions from various formats."""
    if not requirements:
        return None

    # If it's a dict with 'requirements' key (structured format)
    if isinstance(requirements, dict):
        reqs = requirements.get("requirements", [])
        return [
            r.get("title") or r.get("description") or str(r)
            for r in reqs if isinstance(r, dict)
        ]

    # If it's a list of dicts
    if isinstance(requirements, list):
        result = []
        for r in requirements:
            if isinstance(r, dict):
                result.append(r.get("title") or r.get("description") or str(r))
            else:
                result.append(str(r))
        return result

    return None


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Full Autonomous Code Generation - Kill the Programmer Job",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # AUTONOMOUS MODE (recommended) - 100% completion required
    python run_society_hybrid.py requirements.json --autonomous

    # With tech stack specification
    python run_society_hybrid.py requirements.json --tech-stack tech_stack.json --autonomous

    # Basic usage with defaults
    python run_society_hybrid.py requirements.json

    # Custom output directory
    python run_society_hybrid.py requirements.json --output-dir ./my-app

    # Strict mode (100% tests, 0 errors, faster timeout)
    python run_society_hybrid.py requirements.json --strict

    # Relaxed mode (80% tests, some errors allowed)
    python run_society_hybrid.py requirements.json --relaxed

    # Fast iteration (quick prototyping)
    python run_society_hybrid.py requirements.json --fast

    # Custom limits
    python run_society_hybrid.py requirements.json --max-iterations 100 --max-time 1800

    # Skip scaffolding (use existing project)
    python run_society_hybrid.py requirements.json --no-scaffold

    # Skip dependency installation
    python run_society_hybrid.py requirements.json --no-install
        """
    )

    parser.add_argument(
        "requirements",
        help="Path to requirements JSON file",
    )
    parser.add_argument(
        "--tech-stack", "-t",
        default=None,
        help="Path to tech stack JSON file (defines framework, database, styling, etc.)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Output directory for generated code (default: ./output)",
    )

    # Convergence criteria presets
    criteria_group = parser.add_mutually_exclusive_group()
    criteria_group.add_argument(
        "--autonomous",
        action="store_true",
        help="FULL AUTONOMOUS MODE: 100%% tests, 0 errors, 1 hour timeout",
    )
    criteria_group.add_argument(
        "--strict",
        action="store_true",
        help="Strict criteria (100%% tests, 0 errors, 10 min timeout)",
    )
    criteria_group.add_argument(
        "--relaxed",
        action="store_true",
        help="Relaxed criteria (80%% tests, some errors allowed)",
    )
    criteria_group.add_argument(
        "--fast",
        action="store_true",
        help="Fast iteration (quick prototyping, 5 min timeout)",
    )

    # Custom convergence settings
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum iterations (default: depends on mode)",
    )
    parser.add_argument(
        "--max-time",
        type=int,
        default=None,
        help="Maximum time in seconds (default: depends on mode)",
    )
    parser.add_argument(
        "--min-test-rate",
        type=float,
        default=None,
        help="Minimum test passing rate %% (default: depends on mode)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Minimum confidence score 0-1 (default: depends on mode)",
    )

    # Scaffolding settings
    parser.add_argument(
        "--no-scaffold",
        action="store_true",
        help="Skip project scaffolding (use existing structure)",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Skip dependency installation",
    )

    # Pipeline settings
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Max concurrent code generation tasks (default: 5)",
    )
    parser.add_argument(
        "--slice-size",
        type=int,
        default=3,
        help="Requirements slice size (default: 3)",
    )

    # Preview settings
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable live preview",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5173,
        help="Live preview port (default: 5173)",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Don't auto-open browser when preview is ready",
    )

    # Completeness check
    parser.add_argument(
        "--check-completeness",
        action="store_true",
        default=True,
        help="Check requirement completeness after generation (default: True)",
    )
    parser.add_argument(
        "--no-completeness-check",
        action="store_true",
        help="Skip completeness check",
    )

    # Async Services: E2E Testing and UX Review (run continuously parallel to Phase 3)
    parser.add_argument(
        "--async-e2e",
        action="store_true",
        help="Enable continuous async E2E testing (runs parallel to Phase 3 loop)",
    )
    parser.add_argument(
        "--async-ux",
        action="store_true",
        help="Enable continuous async UX review with Claude Vision (runs parallel to Phase 3 loop)",
    )
    parser.add_argument(
        "--async-services",
        action="store_true",
        help="Enable all async services (VNC Sandbox + E2E + UX Review)",
    )
    parser.add_argument(
        "--async-e2e-interval",
        type=int,
        default=60,
        help="Seconds between async E2E test cycles (default: 60)",
    )
    parser.add_argument(
        "--async-ux-interval",
        type=int,
        default=120,
        help="Seconds between async UX review cycles (default: 120)",
    )
    # Legacy aliases for backwards compatibility
    parser.add_argument(
        "--e2e-testing",
        action="store_true",
        help="[DEPRECATED] Use --async-e2e instead",
    )
    parser.add_argument(
        "--ux-review",
        action="store_true",
        help="[DEPRECATED] Use --async-ux instead",
    )
    parser.add_argument(
        "--phase5",
        action="store_true",
        help="[DEPRECATED] Use --async-services instead",
    )

    # LLM-based Verification (Multi-Agent Debate for Phase 4)
    parser.add_argument(
        "--llm-verification",
        action="store_true",
        help="Enable LLM-based verification with Multi-Agent Debate pattern",
    )
    parser.add_argument(
        "--verification-debate-rounds",
        type=int,
        default=3,
        help="Number of debate rounds for Multi-Agent Verification (default: 3)",
    )

    # Phase 10: VotingAI and Parallel Generation Settings
    parser.add_argument(
        "--enable-voting",
        action="store_true",
        default=True,
        help="Enable VotingAI for fix selection (default: True)",
    )
    parser.add_argument(
        "--disable-voting",
        action="store_true",
        help="Disable VotingAI for fix selection",
    )
    parser.add_argument(
        "--voting-method",
        choices=["majority", "qualified_majority", "ranked_choice", "unanimous", "weighted_majority"],
        default="qualified_majority",
        help="Voting method for fix selection (default: qualified_majority)",
    )
    parser.add_argument(
        "--enable-ab-generation",
        action="store_true",
        help="Enable A/B solution generation with Kilo parallel mode",
    )
    parser.add_argument(
        "--ab-solutions",
        type=int,
        default=2,
        help="Number of A/B solutions to generate (default: 2, max: 5)",
    )

    # Deployment Team: Sandbox and Cloud Testing
    parser.add_argument(
        "--enable-sandbox",
        action="store_true",
        help="Enable Docker sandbox testing for deployment verification",
    )
    parser.add_argument(
        "--enable-cloud-tests",
        action="store_true",
        help="Enable GitHub Actions cloud testing (requires GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--deployment-team",
        action="store_true",
        help="Enable full deployment team (sandbox + cloud tests if GITHUB_TOKEN set)",
    )
    parser.add_argument(
        "--enable-vnc",
        action="store_true",
        help="Enable VNC streaming for Electron apps in sandbox (view at http://localhost:6080/vnc.html)",
    )
    parser.add_argument(
        "--vnc-port",
        type=int,
        default=6080,
        help="noVNC web port for screen streaming (default: 6080)",
    )

    # Continuous Sandbox Testing (NEW)
    parser.add_argument(
        "--continuous-sandbox",
        action="store_true",
        help="Enable continuous sandbox testing - deploy/test/kill cycle every 30 seconds from the start",
    )
    parser.add_argument(
        "--sandbox-interval",
        type=int,
        default=30,
        help="Seconds between sandbox test cycles (default: 30)",
    )
    parser.add_argument(
        "--start-sandbox-immediately",
        action="store_true",
        default=True,
        help="Start sandbox loop immediately before code is ready (default: True)",
    )
    parser.add_argument(
        "--no-start-sandbox-immediately",
        action="store_true",
        help="Wait for BUILD_SUCCEEDED before starting sandbox tests",
    )

    # Continuous Debug Agent (Real-time error fixing during generation)
    parser.add_argument(
        "--enable-continuous-debug",
        action="store_true",
        help="Enable ContinuousDebugAgent for real-time error fixing during generation",
    )
    parser.add_argument(
        "--debug-cycle-interval",
        type=int,
        default=5,
        help="Seconds between debug cycles (default: 5)",
    )

    # Persistent Deployment (Final VNC deployment after convergence)
    parser.add_argument(
        "--persistent-deploy",
        action="store_true",
        help="Deploy to persistent VNC container when convergence is achieved",
    )
    parser.add_argument(
        "--persistent-vnc-port",
        type=int,
        default=6080,
        help="VNC port for persistent deployment (default: 6080)",
    )
    parser.add_argument(
        "--inject-secrets",
        action="store_true",
        default=True,
        help="Inject collected secrets into persistent container (default: True)",
    )

    # Development Container (Live VNC during generation)
    parser.add_argument(
        "--dev-container",
        action="store_true",
        help="Start dev container with VNC BEFORE code generation (watch files appear live)",
    )
    parser.add_argument(
        "--dev-container-port",
        type=int,
        default=6080,
        help="VNC port for dev container (default: 6080)",
    )

    # Microservices Architecture (Cloud-Ready)
    parser.add_argument(
        "--microservices",
        action="store_true",
        help="Enable microservice mode: generate 8 separate services with Docker/K8s deployment",
    )
    parser.add_argument(
        "--microservices-output",
        type=str,
        default="services",
        help="Subdirectory for microservice outputs (default: services)",
    )

    parser.add_argument(
        "--no-inject-secrets",
        action="store_true",
        help="Disable secret injection into persistent container",
    )

    # ValidationTeam: Test Generation + Debug Engine (NEW)
    parser.add_argument(
        "--enable-validation",
        action="store_true",
        help="Enable ValidationTeam for test generation and debug engine",
    )
    parser.add_argument(
        "--validation-team",
        action="store_true",
        help="Alias for --enable-validation",
    )
    parser.add_argument(
        "--test-framework",
        type=str,
        default="vitest",
        choices=["vitest", "jest", "pytest"],
        help="Test framework for validation (default: vitest)",
    )
    parser.add_argument(
        "--validation-docker",
        action="store_true",
        default=True,
        help="Use Docker for validation port isolation (default: True)",
    )
    parser.add_argument(
        "--no-validation-docker",
        action="store_true",
        help="Disable Docker for validation (run tests locally)",
    )
    parser.add_argument(
        "--validation-port-frontend",
        type=int,
        default=3100,
        help="Frontend port for validation Docker (default: 3100)",
    )
    parser.add_argument(
        "--validation-port-backend",
        type=int,
        default=8100,
        help="Backend port for validation Docker (default: 8100)",
    )
    parser.add_argument(
        "--max-debug-iterations",
        type=int,
        default=3,
        help="Max debug iterations for validation (default: 3)",
    )
    parser.add_argument(
        "--validation-timeout",
        type=int,
        default=300,
        help="Validation timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--shell-stream",
        action="store_true",
        default=True,
        help="Enable shell streaming for user feedback (default: True)",
    )
    parser.add_argument(
        "--no-shell-stream",
        action="store_true",
        help="Disable shell streaming",
    )

    # Dashboard settings
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Enable real-time dashboard to watch agents work (opens browser)",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8080,
        help="Dashboard HTTP port (default: 8080)",
    )

    # Documentation generation
    parser.add_argument(
        "--no-docs",
        action="store_true",
        help="Disable auto-generation of CLAUDE.md in output project",
    )

    # Rate Limit Recovery (Task 8)
    parser.add_argument(
        "--enable-checkpoints",
        action="store_true",
        default=True,
        help="Enable checkpoint saving for rate limit recovery (default: True)",
    )
    parser.add_argument(
        "--no-checkpoints",
        action="store_true",
        help="Disable checkpoint saving",
    )
    parser.add_argument(
        "--rate-limit-wait",
        type=float,
        default=4.0,
        help="Hours to wait after rate limit hit before first retry (default: 4.0)",
    )
    parser.add_argument(
        "--rate-limit-interval",
        type=float,
        default=0.5,
        help="Hours between retry attempts after initial wait (default: 0.5 = 30 min)",
    )
    parser.add_argument(
        "--rate-limit-max-retries",
        type=int,
        default=10,
        help="Maximum retry attempts before giving up (default: 10)",
    )

    # Verbosity
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed logging of all events, agent actions, and pipeline stages",
    )
    
    # JSON progress output for IPC (NEW)
    parser.add_argument(
        "--json-progress",
        action="store_true",
        help="Output progress in JSON format for IPC communication (used by VibeMind)",
    )
    
    # Claude Monitor for AI-powered error analysis (NEW)
    parser.add_argument(
        "--enable-monitor",
        action="store_true",
        help="Enable Claude Monitor for AI-powered error analysis and improvement suggestions",
    )
    parser.add_argument(
        "--monitor-api-key",
        type=str,
        default=None,
        help="Anthropic API key for Claude Monitor (defaults to ANTHROPIC_API_KEY env var)",
    )

    # Intelligent Chunking for Phase 2
    parser.add_argument(
        "--intelligent-chunking",
        action="store_true",
        help="Enable LLM-based intelligent chunk planning for optimal parallelization",
    )
    parser.add_argument(
        "--no-intelligent-chunking",
        action="store_true",
        help="Disable intelligent chunking (use fixed 3-requirement chunks)",
    )

    # Design Pipeline (Pre-Generation Planning)
    parser.add_argument(
        "--design-pipeline",
        action="store_true",
        help="Run Design Pipeline before code generation (transforms requirements into ExecutionPlan)",
    )
    parser.add_argument(
        "--design-only",
        action="store_true",
        help="Run ONLY the Design Pipeline without code generation (outputs ExecutionPlan.json)",
    )
    parser.add_argument(
        "--execution-plan",
        type=str,
        default=None,
        help="Path to existing ExecutionPlan.json to use for code generation (skips design phase)",
    )

    # Task 24: Backend Agent Feature Flags
    parser.add_argument(
        "--no-database-generation",
        action="store_false",
        dest="enable_database_generation",
        default=True,
        help="Disable automatic database schema generation (DatabaseAgent)",
    )
    parser.add_argument(
        "--no-api-generation",
        action="store_false",
        dest="enable_api_generation",
        default=True,
        help="Disable automatic API route generation (APIAgent)",
    )
    parser.add_argument(
        "--no-auth-setup",
        action="store_false",
        dest="enable_auth_setup",
        default=True,
        help="Disable automatic authentication setup (AuthAgent)",
    )
    parser.add_argument(
        "--no-infrastructure-setup",
        action="store_false",
        dest="enable_infrastructure_setup",
        default=True,
        help="Disable automatic infrastructure configuration (InfrastructureAgent)",
    )

    # Fungus Context System (la_fungus_search integration)
    parser.add_argument(
        "--enable-fungus",
        action="store_true",
        default=True,
        help="Enable la_fungus_search context system for semantic code search (default: enabled)",
    )
    parser.add_argument(
        "--disable-fungus",
        action="store_true",
        help="Disable la_fungus_search context system",
    )
    parser.add_argument(
        "--fungus-agents",
        type=int,
        default=200,
        help="Number of MCMP agents for fungus simulation (default: 200)",
    )
    parser.add_argument(
        "--fungus-iterations",
        type=int,
        default=50,
        help="Max iterations for MCMP simulation (default: 50)",
    )
    parser.add_argument(
        "--fungus-judge-provider",
        type=str,
        default="openrouter",
        choices=["openrouter", "ollama", "openai", "google", "grok"],
        help="LLM provider for Judge evaluation (default: openrouter)",
    )
    parser.add_argument(
        "--fungus-judge-model",
        type=str,
        default="anthropic/claude-haiku-4.5",
        help="Model for Judge LLM (default: anthropic/claude-haiku-4.5 for OpenRouter)",
    )
    # Phase 11: Advanced Fungus parameters for completeness checking
    parser.add_argument(
        "--fungus-top-k",
        type=int,
        default=20,
        help="Number of top results per query (default: 20)",
    )
    parser.add_argument(
        "--fungus-steering-every",
        type=int,
        default=3,
        help="LLM steering frequency (every N rounds, default: 3)",
    )
    parser.add_argument(
        "--fungus-exploration-bonus",
        type=float,
        default=0.15,
        help="Exploration bonus for less visited paths (default: 0.15)",
    )
    parser.add_argument(
        "--fungus-restart-every",
        type=int,
        default=10,
        help="Restart simulation every N steps for fresh exploration (default: 10)",
    )
    parser.add_argument(
        "--fungus-judge-every",
        type=int,
        default=3,
        help="Judge evaluation frequency (every N rounds, default: 3)",
    )
    parser.add_argument(
        "--fungus-min-confidence",
        type=float,
        default=0.6,
        help="Minimum confidence threshold for results (default: 0.6)",
    )

    return parser.parse_args()


def get_criteria(args) -> ConvergenceCriteria:
    """Get convergence criteria based on arguments."""
    # Select base criteria
    if args.autonomous:
        criteria = ConvergenceCriteria(
            require_all_tests_pass=True,
            min_tests_passing_rate=100.0,
            require_build_success=True,
            max_validation_errors=0,
            max_type_errors=0,
            max_lint_errors=0,
            min_confidence_score=0.95,
            max_iterations=200,
            min_iterations=3,
            max_time_seconds=3600,  # 1 hour
            require_assets_complete=True,
        )
    elif args.strict:
        criteria = ConvergenceCriteria(
            require_all_tests_pass=True,
            require_build_success=True,
            max_validation_errors=0,
            max_type_errors=0,
            max_lint_errors=0,
            min_confidence_score=0.95,
            max_iterations=50,
            max_time_seconds=600,  # 10 minutes
        )
    elif args.relaxed:
        criteria = ConvergenceCriteria(
            min_tests_passing_rate=80.0,
            require_build_success=True,
            max_validation_errors=5,
            max_type_errors=10,
            min_confidence_score=0.70,
            max_iterations=20,
            max_time_seconds=600,
        )
    elif args.fast:
        criteria = ConvergenceCriteria(
            min_tests_passing_rate=70.0,
            require_build_success=True,
            max_validation_errors=10,
            max_type_errors=20,
            min_confidence_score=0.60,
            max_iterations=10,
            max_time_seconds=300,  # 5 minutes
        )
    else:
        # Default to autonomous mode for full automation
        criteria = ConvergenceCriteria(
            require_all_tests_pass=True,
            min_tests_passing_rate=100.0,
            require_build_success=True,
            max_validation_errors=0,
            max_type_errors=0,
            min_confidence_score=0.90,
            max_iterations=100,
            max_time_seconds=1800,  # 30 minutes default
        )

    # Override with custom values if provided
    if args.max_iterations is not None:
        criteria.max_iterations = args.max_iterations
    if args.max_time is not None:
        criteria.max_time_seconds = args.max_time
    if args.min_test_rate is not None:
        criteria.min_tests_passing_rate = args.min_test_rate
    if args.min_confidence is not None:
        criteria.min_confidence_score = args.min_confidence

    return criteria


def print_progress(metrics, progress: float):
    """Print progress to console."""
    tests_info = f"{metrics.tests_passed}/{metrics.total_tests}" if metrics.total_tests > 0 else "N/A"
    build_status = "OK" if metrics.build_success else ("FAIL" if metrics.build_attempted else "...")

    print(
        f"\r[{progress:5.1f}%] "
        f"Iter:{metrics.iteration:3d} | "
        f"Tests:{tests_info:>10} ({metrics.tests_passing_rate:5.1f}%) | "
        f"Build:{build_status:4} | "
        f"Errors: V:{metrics.validation_errors} T:{metrics.type_errors} | "
        f"Confidence:{metrics.confidence_score:.1%}",
        end="",
        flush=True,
    )


def print_json_progress(metrics, progress: float):
    """Print progress in JSON format for IPC communication with VibeMind."""
    status = "completed" if progress >= 100 else "generating"
    if metrics.build_success and metrics.tests_passing_rate >= 100:
        status = "converging"
    elif metrics.build_attempted and not metrics.build_success:
        status = "testing"
    
    progress_data = {
        "status": status,
        "progress": round(progress, 1),
        "phase": f"Iteration {metrics.iteration}",
        "iteration": metrics.iteration,
        "tests_passed": metrics.tests_passed,
        "total_tests": metrics.total_tests,
        "tests_passing_rate": round(metrics.tests_passing_rate, 1),
        "build_success": metrics.build_success,
        "validation_errors": metrics.validation_errors,
        "type_errors": metrics.type_errors,
        "confidence_score": round(metrics.confidence_score, 2),
    }
    
    print(json.dumps(progress_data), flush=True)


async def run_scaffolding(args, requirements: dict, tech_stack: Optional[TechStack] = None) -> bool:
    """Run project scaffolding.

    Args:
        args: Command line arguments
        requirements: Parsed requirements dict
        tech_stack: Optional tech stack configuration (used to override project type detection)
    """
    from src.scaffolding.project_initializer import ProjectType

    print("\n[Phase 0] Project Scaffolding")
    print("-" * 40)

    # Derive project type from tech_stack if available
    # This ensures frontend scaffolding happens even when requirements mention backend tech
    project_type = None
    if tech_stack:
        # Check if frontend is specified in tech_stack
        if tech_stack.frontend_framework:
            frontend = tech_stack.frontend_framework.lower()
            if "react" in frontend or "vue" in frontend or "angular" in frontend:
                # Check platform for electron
                if tech_stack.platform and tech_stack.platform.lower() in ("electron", "desktop"):
                    project_type = ProjectType.REACT_ELECTRON
                    print(f"  Tech Stack Override: {tech_stack.frontend_framework} + Electron -> REACT_ELECTRON")
                else:
                    project_type = ProjectType.REACT_VITE
                    print(f"  Tech Stack Override: {tech_stack.frontend_framework} -> REACT_VITE")

        # If only backend specified, use backend type
        if project_type is None and tech_stack.backend_framework:
            backend = tech_stack.backend_framework.lower()
            if "fastapi" in backend or "flask" in backend or "django" in backend:
                project_type = ProjectType.PYTHON_FASTAPI
                print(f"  Tech Stack Override: {tech_stack.backend_framework} -> PYTHON_FASTAPI")
            elif "express" in backend or "node" in backend or "nest" in backend:
                project_type = ProjectType.NODE_EXPRESS
                print(f"  Tech Stack Override: {tech_stack.backend_framework} -> NODE_EXPRESS")

    initializer = ProjectInitializer(args.output_dir)
    result = await initializer.initialize(
        requirements=requirements,
        project_type=project_type,  # Pass the derived project type
        install_deps=not args.no_install,
    )

    if result.success:
        print(f"  Project Type: {result.project_type.value}")
        print(f"  Files Created: {len(result.files_created)}")
        print(f"  Files Verified: {len(result.files_verified)}")
        print(f"  Dependencies Installed: {'Yes' if result.dependencies_installed else 'No'}")
        print("  Status: SUCCESS")

        # Start dev container if enabled (VNC during generation)
        if hasattr(args, 'dev_container') and args.dev_container:
            print("\n[Dev Container] Starting live VNC environment...")
            dev_port = getattr(args, 'dev_container_port', 6080)
            try:
                dev_result = await start_dev_container(
                    project_dir=args.output_dir,
                    vnc_port=dev_port,
                    dev_port=5173,
                )
                if dev_result.success:
                    print(f"  VNC URL: {dev_result.vnc_url}")
                    print(f"  Dev Server: {dev_result.dev_server_url}")
                    print("  Files will appear live as they're generated!")
                else:
                    print(f"  Warning: Dev container failed to start: {dev_result.error}")
            except Exception as e:
                print(f"  Warning: Dev container startup failed: {e}")
    else:
        print("  Status: FAILED")
        for error in result.errors:
            print(f"  Error: {error}")

    return result.success


async def run_completeness_check(args, requirements: dict) -> dict:
    """Run completeness check."""
    print("\n[Phase 4] Completeness Verification")
    print("-" * 40)

    checker = CompletenessChecker(args.output_dir)
    result = checker.check(requirements)

    print(f"  Total Requirements: {result.total_requirements}")
    print(f"  Implemented: {result.implemented}")
    print(f"  Tested: {result.tested}")
    print(f"  Verified (tests pass): {result.verified}")
    print(f"  Failed (tests fail): {result.failed}")
    print(f"  Not Started: {result.not_started}")
    print(f"  Completeness Score: {result.completeness_score:.1f}%")

    if result.missing_requirements:
        print(f"\n  Missing Requirements ({len(result.missing_requirements)}):")
        for req in result.missing_requirements[:5]:
            print(f"    - {req[:60]}...")
        if len(result.missing_requirements) > 5:
            print(f"    ... and {len(result.missing_requirements) - 5} more")

    return result.to_dict()


async def main():
    """Main entry point."""
    import logging

    args = parse_args()

    # Configure logging level based on --verbose flag
    if args.verbose:
        # Enable debug-level logging for all components
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')
        logging.getLogger().setLevel(logging.DEBUG)
        print("[Verbose] Debug logging enabled - showing all events and actions")
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        logging.getLogger().setLevel(logging.INFO)

    # Load and apply defaults from config/society_defaults.json
    defaults = load_society_defaults()
    if defaults:
        apply_defaults_to_args(args, defaults)

    # Auto-generate output directory if using default
    if args.output_dir == "./output":
        args.output_dir = get_next_output_dir(
            base_pattern="output",
            requirements_file=args.requirements
        )
        print(f"[Auto] Output directory: {args.output_dir}")

    # Validate requirements path (file or RE documentation directory)
    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"Error: Requirements path not found: {args.requirements}")
        return 1

    # Load requirements - support both JSON files and RE documentation directories
    tech_stack = None
    if req_path.is_dir():
        from src.engine.spec_adapter import SpecAdapter
        adapter = SpecAdapter()
        try:
            normalized = adapter.load(req_path)
            requirements = normalized.to_simple_format()
            print(f"  Loaded Documentation Format: {len(requirements.get('requirements', []))} requirements")
            # Auto-extract tech stack from documentation
            if normalized.tech_stack:
                try:
                    tech_stack = TechStack.from_dict({"tech_stack": normalized.tech_stack})
                    print(f"  Detected tech stack: {normalized.tech_stack.get('name', 'unknown')}")
                except Exception:
                    pass
        except Exception as e:
            print(f"Error: Failed to load documentation directory: {e}")
            return 1
    else:
        try:
            with open(req_path, "r", encoding="utf-8") as f:
                requirements = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in requirements file: {e}")
            return 1

    # Load tech stack if provided (from file or embedded in requirements)
    if args.tech_stack:
        tech_stack_path = Path(args.tech_stack)
        if not tech_stack_path.exists():
            print(f"Error: Tech stack file not found: {args.tech_stack}")
            return 1
        try:
            tech_stack = load_tech_stack(str(tech_stack_path))
            if tech_stack is None:
                print(f"Error: Failed to parse tech stack file: {args.tech_stack}")
                return 1
        except Exception as e:
            print(f"Error: Failed to load tech stack: {e}")
            return 1
    elif "tech_stack" in requirements:
        # Tech stack embedded in requirements JSON
        try:
            tech_stack = TechStack.from_dict({"tech_stack": requirements["tech_stack"]})
            if not args.json_progress:
                print(f"  Detected embedded tech_stack in requirements")
        except Exception as e:
            if not args.json_progress:
                print(f"  Warning: Failed to parse embedded tech_stack: {e}")

    # Get convergence criteria
    criteria = get_criteria(args)

    # Determine mode name
    if args.autonomous:
        mode_name = "AUTONOMOUS (Full Automation)"
    elif args.strict:
        mode_name = "STRICT"
    elif args.relaxed:
        mode_name = "RELAXED"
    elif args.fast:
        mode_name = "FAST"
    else:
        mode_name = "DEFAULT"

    # ==== EARLY VARIABLE DEFINITIONS ====
    # These must be defined before they are used in the config print section

    # Async Services settings (E2E and UX run continuously parallel to Phase 3)
    # Support both new flags and legacy aliases
    enable_async_e2e = args.async_e2e or args.e2e_testing or args.phase5 or args.async_services
    enable_async_ux = args.async_ux or args.ux_review or args.phase5 or args.async_services
    async_e2e_interval = args.async_e2e_interval
    async_ux_interval = args.async_ux_interval

    # LLM-based Verification settings (Multi-Agent Debate for Phase 4)
    enable_llm_verification = getattr(args, 'llm_verification', False)
    verification_debate_rounds = getattr(args, 'verification_debate_rounds', 3)

    # Phase 10: VotingAI settings
    voting_enabled = getattr(args, 'enable_voting', True) and not getattr(args, 'disable_voting', False)
    voting_method = getattr(args, 'voting_method', 'qualified_majority')
    ab_generation_enabled = getattr(args, 'enable_ab_generation', False)
    ab_num_solutions = min(5, max(2, getattr(args, 'ab_solutions', 2)))

    # Deployment team settings
    enable_sandbox = args.enable_sandbox or args.deployment_team
    enable_cloud = args.enable_cloud_tests or (args.deployment_team and bool(os.getenv("GITHUB_TOKEN")))
    enable_vnc = args.enable_vnc
    
    # Continuous sandbox settings
    enable_continuous_sandbox = args.continuous_sandbox
    sandbox_interval = args.sandbox_interval
    start_sandbox_immediately = not args.no_start_sandbox_immediately

    # Continuous debug settings
    enable_continuous_debug = args.enable_continuous_debug
    debug_cycle_interval = args.debug_cycle_interval

    # DEBUG: Log received CLI arguments for troubleshooting
    print(f"[DEBUG CLI] enable_continuous_debug={enable_continuous_debug}, continuous_sandbox={enable_continuous_sandbox}")

    # ValidationTeam settings
    enable_validation = args.enable_validation or args.validation_team
    validation_use_docker = args.validation_docker and not args.no_validation_docker
    shell_stream_enabled = args.shell_stream and not args.no_shell_stream

    # Persistent deployment settings
    enable_persistent_deploy = args.persistent_deploy
    persistent_vnc_port = args.persistent_vnc_port
    inject_secrets = args.inject_secrets and not args.no_inject_secrets

    # Intelligent chunking settings (from defaults or CLI)
    enable_intelligent_chunking = (
        args.intelligent_chunking or
        (defaults.get("intelligent_chunking", False) and not args.no_intelligent_chunking)
    )

    # Progress callback - use JSON if requested
    progress_callback = print_json_progress if args.json_progress else print_progress

    # Print configuration (only if not using JSON progress)
    if not args.json_progress:
        print("=" * 60)
        print("FULL AUTONOMOUS CODE GENERATION")
        print("Kill the Programmer Job")
        print("=" * 60)
        print(f"Mode:         {mode_name}")
        print(f"Requirements: {args.requirements}")
        print(f"Output Dir:   {args.output_dir}")
        print(f"Scaffolding:  {'Enabled' if not args.no_scaffold else 'Disabled'}")
        print(f"Install Deps: {'Enabled' if not args.no_install else 'Disabled'}")
        print(f"Live Preview: {'Enabled' if not args.no_preview else 'Disabled'}")
        if not args.no_preview:
            print(f"Preview Port: {args.port}")
            print(f"Auto-Open Browser: {'Yes' if not args.no_open_browser else 'No'}")
        print(f"Dashboard:    {'Enabled (http://localhost:' + str(args.dashboard_port) + ')' if args.dashboard else 'Disabled'}")
        print(f"Verbose:      {'Enabled (full event logging)' if args.verbose else 'Disabled'}")
        print(f"Sandbox Test: {'Enabled' if enable_sandbox else 'Disabled'}")
        print(f"Cloud Tests:  {'Enabled' if enable_cloud else 'Disabled'}")
        
        # Continuous sandbox info
        if enable_continuous_sandbox:
            print(f"Continuous Sandbox: Enabled (every {sandbox_interval}s)")
            print(f"  Start Immediately: {'Yes' if start_sandbox_immediately else 'No'}")
        
        if enable_vnc:
            print(f"VNC Streaming: Enabled (http://localhost:{args.vnc_port}/vnc.html)")
        
        # ValidationTeam info
        if enable_validation:
            print(f"ValidationTeam: Enabled")
            print(f"  Test Framework: {args.test_framework}")
            print(f"  Docker Isolation: {'Yes' if validation_use_docker else 'No'}")
            if validation_use_docker:
                print(f"  Frontend Port: {args.validation_port_frontend}")
                print(f"  Backend Port: {args.validation_port_backend}")
            print(f"  Max Debug Iterations: {args.max_debug_iterations}")
            print(f"  Shell Streaming: {'Yes' if shell_stream_enabled else 'No'}")

        # Persistent deployment info
        if enable_persistent_deploy:
            print(f"Persistent Deploy: Enabled (VNC at http://localhost:{persistent_vnc_port}/vnc.html)")
            print(f"  Inject Secrets: {'Yes' if inject_secrets else 'No'}")

        # Dev Container info (live VNC during generation)
        if hasattr(args, 'dev_container') and args.dev_container:
            dev_port = getattr(args, 'dev_container_port', 6080)
            print(f"Dev Container: Enabled (VNC at http://localhost:{dev_port}/vnc.html)")
            print(f"  Mount: {args.output_dir} -> /app (live sync)")
            print(f"  Hot Reload: Enabled")

        # Async Services info (E2E and UX run continuously parallel to Phase 3)
        if enable_async_e2e or enable_async_ux:
            print()
            print("Async Services (parallel to Phase 3):")
            if enable_async_e2e:
                print(f"  E2E Tests: Enabled (every {async_e2e_interval}s)")
            if enable_async_ux:
                print(f"  UX Review: Enabled (every {async_ux_interval}s)")

        # LLM-based Verification info
        if enable_llm_verification:
            print()
            print("LLM Verification (Phase 4):")
            print(f"  Multi-Agent Debate: Enabled ({verification_debate_rounds} rounds)")

        # Intelligent Chunking info (Phase 2)
        if enable_intelligent_chunking:
            print()
            print("Intelligent Chunking (Phase 2):")
            print(f"  LLM-based service grouping: Enabled")
            print(f"  Max concurrent workers: {args.max_concurrent}")

        print(f"Max Iterations: {criteria.max_iterations}")
        print(f"Max Time: {criteria.max_time_seconds}s ({criteria.max_time_seconds // 60} min)")
        print(f"Min Test Rate: {criteria.min_tests_passing_rate}%")
        print(f"Min Confidence: {criteria.min_confidence_score:.0%}")

        # Rate limit recovery info (Task 8)
        if args.enable_checkpoints and not args.no_checkpoints:
            print()
            print("Rate Limit Recovery:")
            print(f"  Checkpoints: Enabled")
            print(f"  Initial Wait: {args.rate_limit_wait}h after rate limit")
            print(f"  Retry Interval: {args.rate_limit_interval * 60:.0f} min between retries")
            print(f"  Max Retries: {args.rate_limit_max_retries}")

        # Print tech stack info if provided
        if tech_stack:
            print()
            print("Tech Stack:")
            if tech_stack.frontend_framework:
                frontend_info = f"  Frontend: {tech_stack.frontend_framework}"
                if tech_stack.frontend_version:
                    frontend_info += f" v{tech_stack.frontend_version}"
                print(frontend_info)
            if tech_stack.backend_framework:
                print(f"  Backend: {tech_stack.backend_framework}")
            if tech_stack.database_name:
                print(f"  Database: {tech_stack.database_name}")
            if tech_stack.styling_framework:
                print(f"  Styling: {tech_stack.styling_framework}")
            print(f"  Platform: {tech_stack.platform}")
        
        print("=" * 60)

    # Phase -1: Design Pipeline (optional - transforms requirements into ExecutionPlan)
    execution_plan = None
    if args.execution_plan:
        # Load existing execution plan
        if not args.json_progress:
            print("\n[Phase -1] Loading Existing Execution Plan")
            print("-" * 40)
            print(f"  Loading: {args.execution_plan}")

        if HAS_DESIGN_PIPELINE:
            try:
                execution_plan = ExecutionPlan.load(args.execution_plan)
                if not args.json_progress:
                    stats = execution_plan.get_stats()
                    print(f"  Waves: {stats['total_waves']}")
                    print(f"  Tasks: {stats['total_tasks']}")
                    print(f"  Status: LOADED")
            except Exception as e:
                print(f"  Error: Failed to load execution plan: {e}")
                return 1
        else:
            print("  Error: Design Pipeline module not available")
            return 1

    elif args.design_pipeline or args.design_only:
        # Run design pipeline to generate execution plan
        if not HAS_DESIGN_PIPELINE:
            print("Error: Design Pipeline module not available. Install required dependencies.")
            return 1

        if not args.json_progress:
            print("\n[Phase -1] Design Pipeline")
            print("-" * 40)
            print("  Transforming requirements into ExecutionPlan...")

        try:
            design_pipeline = DesignPipeline(
                requirements_path=req_path,
                output_dir=args.output_dir,
                project_name=requirements.get("name", "project") if isinstance(requirements, dict) else "project",
            )
            result = await design_pipeline.run()

            if result.success:
                execution_plan = result.execution_plan
                if not args.json_progress:
                    stats = execution_plan.get_stats()
                    print(f"  Requirements Enriched: {len(result.enriched_requirements or [])}")
                    print(f"  Database Tables: {stats.get('database_tables', 0)}")
                    print(f"  API Endpoints: {stats.get('api_endpoints', 0)}")
                    print(f"  Components: {stats.get('components', 0)}")
                    print(f"  Execution Waves: {stats['total_waves']}")
                    print(f"  Total Tasks: {stats['total_tasks']}")
                    print(f"  Duration: {result.duration_seconds:.1f}s")
                    print(f"  Status: SUCCESS")
                    print(f"  Output: {args.output_dir}/execution_plan.json")
            else:
                if not args.json_progress:
                    print(f"  Error Agent: {result.error_agent}")
                    print(f"  Error: {result.error}")
                    print(f"  Status: FAILED")
                return 1
        except Exception as e:
            if not args.json_progress:
                print(f"  Error: Design Pipeline failed: {e}")
            return 1

        # If design-only mode, exit after design
        if args.design_only:
            if not args.json_progress:
                print("\n[Design-Only Mode] Skipping code generation")
                print(f"Execution plan saved to: {args.output_dir}/execution_plan.json")
            else:
                print(json.dumps({
                    "status": "design_complete",
                    "execution_plan": str(Path(args.output_dir) / "execution_plan.json"),
                    "waves": execution_plan.get_stats()["total_waves"],
                    "tasks": execution_plan.get_stats()["total_tasks"],
                }))
            return 0

    # Phase 0: Scaffolding
    if not args.no_scaffold:
        scaffold_success = await run_scaffolding(args, requirements, tech_stack)
        if not scaffold_success and not args.json_progress:
            print("\nWarning: Scaffolding had errors, continuing anyway...")

    # Phase 1-3: Code Generation + Society of Mind
    if not args.json_progress:
        print("\n[Phase 1-3] Code Generation + Society of Mind")
        print("-" * 40)
        print("Starting autonomous generation loop...")
        print()

    # Create config
    config = HybridSocietyConfig(
        requirements_path=str(req_path),
        output_dir=args.output_dir,
        criteria=criteria,
        # Design Pipeline execution plan (if available)
        execution_plan=execution_plan.to_dict() if execution_plan else None,
        max_concurrent=args.max_concurrent,
        slice_size=args.slice_size,
        enable_live_preview=not args.no_preview,
        preview_port=args.port,
        open_browser=not args.no_open_browser,
        enable_dashboard=args.dashboard,
        dashboard_port=args.dashboard_port,
        progress_callback=progress_callback,
        # Async Services (E2E and UX run continuously parallel to Phase 3)
        enable_async_e2e=enable_async_e2e,
        enable_async_ux=enable_async_ux,
        async_e2e_interval=async_e2e_interval,
        async_ux_interval=async_ux_interval,
        # LLM-based Verification (Multi-Agent Debate for Phase 4)
        enable_llm_verification=enable_llm_verification,
        verification_debate_rounds=verification_debate_rounds,
        # Phase 10: VotingAI configuration
        voting_enabled=voting_enabled,
        voting_method=voting_method,
        ab_generation_enabled=ab_generation_enabled,
        ab_num_solutions=ab_num_solutions,
        enable_auto_docs=not args.no_docs,
        enable_sandbox_testing=enable_sandbox,
        enable_cloud_tests=enable_cloud,
        enable_vnc_streaming=enable_vnc,
        vnc_port=args.vnc_port,
        # Continuous sandbox testing
        enable_continuous_sandbox=enable_continuous_sandbox,
        sandbox_cycle_interval=sandbox_interval,
        start_sandbox_immediately=start_sandbox_immediately,
        # Continuous debug agent
        enable_continuous_debug=enable_continuous_debug,
        debug_cycle_interval=debug_cycle_interval,
        requirements_list=_extract_requirements_list(requirements),
        # Tech stack configuration
        tech_stack=tech_stack,
        tech_stack_path=args.tech_stack,
        # ValidationTeam configuration
        enable_validation_team=enable_validation,
        validation_test_framework=args.test_framework,
        validation_use_docker=validation_use_docker,
        validation_docker_network="validation-net",
        validation_frontend_port=args.validation_port_frontend,
        validation_backend_port=args.validation_port_backend,
        validation_max_debug_iterations=args.max_debug_iterations,
        enable_shell_stream=shell_stream_enabled,
        # Claude Monitor configuration (NEW)
        enable_claude_monitor=args.enable_monitor,
        monitor_api_key=args.monitor_api_key,
        # Persistent deployment configuration
        enable_persistent_deploy=enable_persistent_deploy,
        persistent_vnc_port=persistent_vnc_port,
        inject_collected_secrets=inject_secrets,
        # Intelligent chunking configuration
        enable_intelligent_chunking=enable_intelligent_chunking,
        # Task 24: Backend Agent Feature Flags
        enable_database_generation=args.enable_database_generation,
        enable_api_generation=args.enable_api_generation,
        enable_auth_setup=args.enable_auth_setup,
        enable_infrastructure_setup=args.enable_infrastructure_setup,
        # Rate limit recovery (Task 8)
        enable_checkpoints=args.enable_checkpoints and not args.no_checkpoints,
        rate_limit_wait_hours=args.rate_limit_wait,
        rate_limit_interval_minutes=args.rate_limit_interval * 60,  # Convert hours to minutes
        rate_limit_max_retries=args.rate_limit_max_retries,
        # Fungus Context System (la_fungus_search integration)
        enable_fungus=args.enable_fungus and not getattr(args, 'disable_fungus', False),
        fungus_num_agents=getattr(args, 'fungus_agents', 200),
        fungus_max_iterations=getattr(args, 'fungus_iterations', 50),
        fungus_judge_provider=getattr(args, 'fungus_judge_provider', 'openrouter'),
        fungus_judge_model=getattr(args, 'fungus_judge_model', 'anthropic/claude-haiku-4.5'),
        # Phase 11: Advanced Fungus parameters for completeness checking
        fungus_top_k=getattr(args, 'fungus_top_k', 20),
        fungus_steering_every=getattr(args, 'fungus_steering_every', 3),
        fungus_exploration_bonus=getattr(args, 'fungus_exploration_bonus', 0.15),
        fungus_restart_every=getattr(args, 'fungus_restart_every', 10),
        fungus_judge_every=getattr(args, 'fungus_judge_every', 3),
        fungus_min_confidence=getattr(args, 'fungus_min_confidence', 0.6),
    )

    # Run
    runner = HybridSocietyRunner(config)
    result = await runner.run()

    # Phase 4: Completeness Check
    completeness_result = None
    if not args.no_completeness_check:
        completeness_result = await run_completeness_check(args, requirements)

    # Print final results (only if not using JSON progress)
    if not args.json_progress:
        print()
        print("=" * 60)
        print("FINAL RESULTS")
        print("=" * 60)

        if result.success:
            print("Status: SUCCESS - Project Complete!")
        else:
            print("Status: INCOMPLETE - Needs More Work")

        print(f"Converged: {'Yes' if result.converged else 'No'}")
        print(f"Initial Generation: {'Success' if result.initial_generation_success else 'Failed'}")
        print(f"Files Generated: {result.files_generated}")
        print(f"Iterations: {result.iterations}")
        print()
        print("Timing:")
        print(f"  Pipeline: {result.pipeline_duration_seconds:.1f}s")
        print(f"  Society:  {result.society_duration_seconds:.1f}s")
        print(f"  Total:    {result.total_duration_seconds:.1f}s")

        if result.preview_url:
            print()
            print(f"Preview URL: {result.preview_url}")
        
        # VNC URL if continuous sandbox was enabled
        if result.vnc_url:
            print(f"VNC URL: {result.vnc_url}")
        
        # Continuous sandbox stats
        if result.sandbox_cycles_completed > 0:
            print()
            print("Sandbox Testing:")
            print(f"  Cycles Completed: {result.sandbox_cycles_completed}")
            print(f"  Last Cycle Success: {'Yes' if result.sandbox_last_success else 'No'}")
        
        # ValidationTeam stats
        if result.validation_tests_passed > 0 or result.validation_tests_failed > 0:
            print()
            print("ValidationTeam Results:")
            print(f"  Tests Passed: {result.validation_tests_passed}")
            print(f"  Tests Failed: {result.validation_tests_failed}")
            print(f"  Pass Rate: {result.validation_pass_rate:.1f}%")
            print(f"  Debug Fixes Applied: {result.validation_fixes_applied}")

        if result.final_metrics:
            print()
            print("Final Metrics:")
            m = result.final_metrics
            print(f"  Tests: {m.tests_passed}/{m.total_tests} ({m.tests_passing_rate:.1f}%)")
            print(f"  Build: {'Success' if m.build_success else 'Failed'}")
            print(f"  Validation Errors: {m.validation_errors}")
            print(f"  Type Errors: {m.type_errors}")
            print(f"  Confidence: {m.confidence_score:.1%}")

        if completeness_result:
            print()
            print(f"Completeness Score: {completeness_result['completeness_score']:.1f}%")

        if result.errors:
            print()
            print("Errors:")
            for error in result.errors[:10]:
                print(f"  - {error}")
            if len(result.errors) > 10:
                print(f"  ... and {len(result.errors) - 10} more")

        print("=" * 60)
    else:
        # JSON final output
        final_output = {
            "status": "completed" if result.success else "failed",
            "progress": 100.0,
            "phase": "Completed" if result.success else "Failed",
            "converged": result.converged,
            "files_generated": result.files_generated,
            "iterations": result.iterations,
            "total_duration_seconds": result.total_duration_seconds,
            "preview_url": result.preview_url,
            "vnc_url": result.vnc_url,
            "completeness_score": completeness_result.get("completeness_score", 0) if completeness_result else None,
        }
        print(json.dumps(final_output), flush=True)

    # Return success if fully complete
    fully_complete = (
        result.success and
        (completeness_result is None or completeness_result.get("completeness_score", 0) >= 90)
    )

    return 0 if fully_complete else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
