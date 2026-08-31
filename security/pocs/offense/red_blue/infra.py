"""
Red vs Blue - External Infrastructure Checker
================================================
Checks availability of external attack targets:
  - secret-vault (VM, port 8000 via NAT)
  - multiseat-os (VirtualBox VM, SSH port 2222)
  - LLM Target (OpenAI API — cloud, no local Ollama needed)

All targets are optional — the game degrades gracefully.
"""

import os
import sys
import socket
import urllib.request
import urllib.error
import json

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model

# ================================================================
# Connection Constants
# ================================================================

# Detect if running inside the VM (set by vm_exercise.py runner)
_VM_LOCAL_MODE = os.environ.get("VM_MODE") == "local"

if _VM_LOCAL_MODE:
    # Running INSIDE the VM — use localhost directly, no SSH needed
    VAULT_HOST = "127.0.0.1"
    VAULT_PORT = 8000                  # Direct, no NAT forwarding
    VM_SSH_HOST = "127.0.0.1"
    VM_SSH_PORT = 22                   # Local SSH
    VM_API_HOST = "127.0.0.1"
    VM_API_PORT = 9090                 # Direct
else:
    # Running on Windows host — use NAT forwarded ports
    VAULT_HOST = "127.0.0.1"
    VAULT_PORT = 18000                 # NAT: host 18000 -> VM 8000
    VM_SSH_HOST = "127.0.0.1"
    VM_SSH_PORT = 2222                 # NAT: host 2222 -> VM 22
    VM_API_HOST = "127.0.0.1"
    VM_API_PORT = 19090                # NAT: host 19090 -> VM 9090

VAULT_URL = f"http://{VAULT_HOST}:{VAULT_PORT}"

# MultiseatOS VM
VM_SSH_USER = "vibemind"
VM_SSH_PASS = "logitech66"
VM_WS_PORT = 9091

# LLM Target — Cloud (OpenAI API)
# No local Ollama needed. Uses the same OPENAI_API_KEY.
LLM_TARGET_TYPE = "openai"   # "openai" or "ollama"
LLM_TARGET_MODEL = get_model("llm_target")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


# ================================================================
# Availability Checks
# ================================================================

def check_vault_available() -> bool:
    """Check if secret-vault Docker container is running and responsive."""
    try:
        req = urllib.request.Request(
            f"{VAULT_URL}/api/auth/status",
            method="GET",
        )
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        return "first_run" in data or "locked" in data
    except Exception:
        return False


def check_vm_ssh_available() -> bool:
    """Check if multiseat-os VM is reachable via SSH port."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((VM_SSH_HOST, VM_SSH_PORT))
        # Read SSH banner
        banner = s.recv(256)
        s.close()
        return b"SSH" in banner
    except Exception:
        return False


def check_vm_api_available() -> bool:
    """Check if multiseat-os system monitor API is reachable."""
    try:
        req = urllib.request.Request(
            f"http://{VM_API_HOST}:{VM_API_PORT}/api/health",
            method="GET",
        )
        resp = urllib.request.urlopen(req, timeout=3)
        return resp.status == 200
    except Exception:
        return False


def check_llm_target_available() -> bool:
    """Check if the LLM target is reachable (OpenAI API or local Ollama)."""
    if LLM_TARGET_TYPE == "openai":
        return bool(OPENAI_API_KEY)
    else:
        # Fallback: check local Ollama
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:11434/api/tags", method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            return resp.status == 200
        except Exception:
            return False


def check_all_targets() -> dict:
    """Check all external targets and return availability status."""
    return {
        "vault": check_vault_available(),
        "vm_ssh": check_vm_ssh_available(),
        "vm_api": check_vm_api_available(),
        "llm_target": check_llm_target_available(),
    }


def get_available_target_summary() -> str:
    """Return a human-readable summary of available targets."""
    status = check_all_targets()
    lines = []
    if status["vault"]:
        lines.append(f"  - secret-vault: {VAULT_URL} (JWT Auth, AES Vault)")
    if status["vm_ssh"]:
        lines.append(f"  - multiseat-os VM: SSH {VM_SSH_HOST}:{VM_SSH_PORT}")
    if status["vm_api"]:
        lines.append(f"  - multiseat-os API: http://{VM_API_HOST}:{VM_API_PORT}")
    if status["llm_target"]:
        if LLM_TARGET_TYPE == "openai":
            lines.append(f"  - LLM Target: OpenAI Cloud ({LLM_TARGET_MODEL})")
        else:
            lines.append(f"  - LLM Target: Ollama (local)")

    if not lines:
        return "  (keine externen Targets verfuegbar - nur lokale Simulation)"

    return "\n".join(lines)
