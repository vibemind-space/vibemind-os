"""
MiroFish Docker Tools - Manage the MiroFish Docker stack

Voice-controllable tools to start, stop, restart, and check
the MiroFish Docker container stack (Flask + Neo4j + Ollama).
"""

import json
import logging
import subprocess
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _get_compose_path() -> str:
    """Get the path to MiroFish's docker-compose.yml."""
    from spaces.mirofish.config import get_config
    return get_config().docker_compose_path


def _broadcast_to_electron(message: Dict[str, Any]):
    """Broadcast message to Electron UI."""
    try:
        print(json.dumps(message), flush=True)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")


def _run_compose(args: list, timeout: int = 120) -> Dict[str, Any]:
    """Run a docker compose command."""
    compose_path = _get_compose_path()
    cmd = ["docker", "compose", "-f", compose_path] + args

    logger.info(f"MiroFish Docker: Running {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Command timed out after {timeout}s", "returncode": -1}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "Docker not found. Is Docker Desktop installed?", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def start_docker() -> Dict[str, Any]:
    """Start the MiroFish Docker stack (Flask + Neo4j + Ollama)."""
    logger.info("mirofish.docker.start: Starting MiroFish Docker stack")

    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": "starting",
        "message": "MiroFish Docker wird gestartet...",
    })

    result = _run_compose(["up", "-d"], timeout=180)

    if result["success"]:
        _broadcast_to_electron({
            "type": "mirofish_status",
            "status": "connected",
            "message": "MiroFish Docker gestartet",
        })
        return {
            "success": True,
            "message": "MiroFish Docker-Stack erfolgreich gestartet.",
            "response_hint": "MiroFish Docker ist jetzt gestartet und bereit.",
        }
    else:
        error = result["stderr"] or "Unknown error"
        _broadcast_to_electron({
            "type": "mirofish_status",
            "status": "error",
            "message": f"Docker Start fehlgeschlagen: {error}",
        })
        return {
            "success": False,
            "message": f"Docker Start fehlgeschlagen: {error}",
            "response_hint": "MiroFish Docker konnte nicht gestartet werden.",
        }


def stop_docker() -> Dict[str, Any]:
    """Stop the MiroFish Docker stack."""
    logger.info("mirofish.docker.stop: Stopping MiroFish Docker stack")

    result = _run_compose(["down"], timeout=60)

    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": "disconnected",
        "message": "MiroFish Docker gestoppt",
    })

    if result["success"]:
        return {
            "success": True,
            "message": "MiroFish Docker-Stack gestoppt.",
            "response_hint": "MiroFish Docker wurde gestoppt.",
        }
    return {
        "success": False,
        "message": f"Docker Stop fehlgeschlagen: {result['stderr']}",
        "response_hint": "MiroFish Docker konnte nicht gestoppt werden.",
    }


def restart_docker() -> Dict[str, Any]:
    """Restart the MiroFish Docker stack."""
    logger.info("mirofish.docker.restart: Restarting MiroFish Docker stack")

    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": "restarting",
        "message": "MiroFish Docker wird neu gestartet...",
    })

    result = _run_compose(["restart"], timeout=120)

    if result["success"]:
        _broadcast_to_electron({
            "type": "mirofish_status",
            "status": "connected",
            "message": "MiroFish Docker neu gestartet",
        })
        return {
            "success": True,
            "message": "MiroFish Docker-Stack neu gestartet.",
            "response_hint": "MiroFish Docker wurde neu gestartet.",
        }
    return {
        "success": False,
        "message": f"Docker Restart fehlgeschlagen: {result['stderr']}",
        "response_hint": "MiroFish Docker konnte nicht neu gestartet werden.",
    }


def docker_status() -> Dict[str, Any]:
    """Check the status of the MiroFish Docker containers."""
    logger.info("mirofish.docker.status: Checking Docker status")

    result = _run_compose(["ps", "--format", "json"])

    if not result["success"]:
        _broadcast_to_electron({
            "type": "mirofish_status",
            "status": "disconnected",
            "message": "Docker nicht erreichbar",
        })
        return {
            "success": False,
            "message": f"Docker Status nicht verfuegbar: {result['stderr']}",
            "response_hint": "MiroFish Docker ist nicht erreichbar.",
            "containers": [],
        }

    containers = []
    try:
        for line in result["stdout"].strip().split("\n"):
            if line.strip():
                container = json.loads(line)
                containers.append({
                    "name": container.get("Name", container.get("Service", "unknown")),
                    "state": container.get("State", "unknown"),
                    "status": container.get("Status", "unknown"),
                })
    except (json.JSONDecodeError, KeyError):
        containers = [{"raw": result["stdout"]}]

    running = sum(1 for c in containers if c.get("state") == "running")
    total = len(containers)

    status = "connected" if running > 0 else "disconnected"
    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": status,
        "containers": containers,
    })

    summary = f"{running}/{total} Container laufen."
    details = "\n".join(
        f"  - {c.get('name', '?')}: {c.get('state', '?')}"
        for c in containers if "name" in c
    )

    return {
        "success": running > 0,
        "message": f"{summary}\n{details}" if details else summary,
        "response_hint": f"MiroFish: {summary}",
        "containers": containers,
    }


__all__ = [
    "start_docker",
    "stop_docker",
    "restart_docker",
    "docker_status",
]
