"""
OpenClaw Setup — Installs and configures OpenClaw Gateway for AgentFarm.

Handles:
1. Check if OpenClaw is installed
2. Configure agent + channel bindings
3. Start/stop Gateway daemon
4. Register ACP runtimes (Claude CLI, Kilo)
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Paths
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_OPENCLAW_SUBMODULE = _PROJECT_ROOT / "external" / "openclaw"
_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
_AGENTS_CONFIG = _CONFIG_DIR / "openclaw_agents.yaml"


def is_openclaw_installed() -> bool:
    """Check if OpenClaw CLI is available."""
    return shutil.which("openclaw") is not None


def is_gateway_running() -> bool:
    """Check if OpenClaw Gateway daemon is running."""
    try:
        result = subprocess.run(
            ["openclaw", "health"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def install_openclaw() -> bool:
    """Install OpenClaw from the submodule."""
    if is_openclaw_installed():
        logger.info("OpenClaw already installed")
        return True

    if not _OPENCLAW_SUBMODULE.is_dir():
        logger.error("OpenClaw submodule not found at external/openclaw/")
        return False

    try:
        logger.info("Installing OpenClaw from submodule...")
        result = subprocess.run(
            ["npm", "install", "-g", "."],
            cwd=str(_OPENCLAW_SUBMODULE),
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            logger.info("OpenClaw installed successfully")
            return True
        else:
            logger.error(f"OpenClaw install failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"OpenClaw install error: {e}")
        return False


def start_gateway() -> bool:
    """Start OpenClaw Gateway daemon."""
    if is_gateway_running():
        logger.info("OpenClaw Gateway already running")
        return True

    try:
        result = subprocess.run(
            ["openclaw", "daemon", "start"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info("OpenClaw Gateway started")
            return True
        else:
            logger.error(f"Gateway start failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Gateway start error: {e}")
        return False


def stop_gateway() -> bool:
    """Stop OpenClaw Gateway daemon."""
    try:
        result = subprocess.run(
            ["openclaw", "daemon", "stop"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def configure_agent() -> bool:
    """Configure the agentfarm-orchestrator agent in OpenClaw."""
    if not is_openclaw_installed():
        logger.error("OpenClaw not installed")
        return False

    try:
        from llm_config import get_model
        # Register agent
        result = subprocess.run(
            ["openclaw", "agents", "add", "agentfarm-orchestrator",
             "--model", get_model("agentfarm")],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logger.warning(f"Agent registration: {result.stderr}")

        logger.info("AgentFarm orchestrator configured in OpenClaw")
        return True
    except Exception as e:
        logger.error(f"Agent config error: {e}")
        return False


def configure_acp_runtimes() -> bool:
    """Register Claude CLI and Kilo as ACP runtimes."""
    if not is_openclaw_installed():
        return False

    runtimes = []

    # Claude CLI
    if shutil.which("claude"):
        runtimes.append(("claude", "claude"))
        logger.info("Claude CLI found — registering as ACP runtime")

    # Kilo Code
    if shutil.which("kilocode"):
        runtimes.append(("kilo", "kilocode"))
        logger.info("Kilo Code found — registering as ACP runtime")

    for name, cmd in runtimes:
        try:
            subprocess.run(
                ["openclaw", "config", "set",
                 f"acp.runtimes.{name}.command", cmd],
                capture_output=True, text=True, timeout=10,
            )
        except Exception as e:
            logger.warning(f"ACP runtime {name} config failed: {e}")

    return len(runtimes) > 0


def start_docker_gateway() -> bool:
    """Start OpenClaw Gateway via docker-compose (preferred for VibeMind)."""
    compose_file = _PROJECT_ROOT / "docker-compose.openclaw.yml"
    if not compose_file.exists():
        logger.error("docker-compose.openclaw.yml not found")
        return False

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            logger.info("OpenClaw Gateway Docker container started (vibemind-openclaw)")
            return True
        else:
            logger.error(f"Docker start failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Docker start error: {e}")
        return False


def stop_docker_gateway() -> bool:
    """Stop OpenClaw Gateway Docker container."""
    compose_file = _PROJECT_ROOT / "docker-compose.openclaw.yml"
    if not compose_file.exists():
        return False
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_docker_gateway_running() -> bool:
    """Check if OpenClaw is running as Docker container."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", "vibemind-openclaw"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


def get_status() -> dict:
    """Get full OpenClaw status for AgentFarm."""
    return {
        "installed": is_openclaw_installed(),
        "gateway_running": is_gateway_running() or is_docker_gateway_running(),
        "docker_running": is_docker_gateway_running(),
        "submodule_present": _OPENCLAW_SUBMODULE.is_dir(),
        "config_present": _AGENTS_CONFIG.is_file(),
        "claude_cli_available": shutil.which("claude") is not None,
        "kilo_cli_available": shutil.which("kilocode") is not None,
    }


def setup_all(use_docker: bool = True) -> dict:
    """Full setup: start gateway (Docker preferred) → configure → register ACP.

    Args:
        use_docker: If True, starts OpenClaw as Docker container (recommended).
                    If False, uses local CLI daemon.
    """
    results = {}

    if use_docker:
        # Docker mode — no local install needed
        results["start_gateway"] = start_docker_gateway()
        if results["start_gateway"]:
            results["mode"] = "docker"
            # ACP runtimes run inside container, configured via YAML mount
            results["configure_acp"] = True
            return results

        logger.warning("Docker start failed, falling back to local CLI")

    # Local CLI mode
    results["install"] = install_openclaw()
    if not results["install"]:
        return results

    results["configure_agent"] = configure_agent()
    results["configure_acp"] = configure_acp_runtimes()
    results["start_gateway"] = start_gateway()
    results["mode"] = "local"

    return results
