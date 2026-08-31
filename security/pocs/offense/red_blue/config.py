"""
Red vs Blue - Configuration
=============================
Central constants for the adversarial loop system.
"""

import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(_env_path)

# ================================================================
# LLM Configuration
# ================================================================

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
RED_TEAM_MODEL = get_model("red_team")    # Red Team Orchestrator
BLUE_TEAM_MODEL = get_model("blue_team")  # Blue Team (unchanged from poc_os_shield)
JUDGE_MODEL = get_model("judge")          # Judge Agent

# ================================================================
# Game Settings
# ================================================================

NUM_ROUNDS = 7                 # Default number of adversarial rounds
MAX_ATTACKS_PER_ROUND = 8      # Prevent resource exhaustion
ATTACK_TIMEOUT = 30            # Seconds per attack tool
SETTLE_PAUSE = 5               # Seconds between attack and detection phase
MAX_LLM_ITERATIONS = 20       # Max function-calling iterations per phase

# ================================================================
# Safety Boundaries
# ================================================================

ARTIFACT_PREFIX = "REDBLUE_"
ARTIFACT_DIR = os.path.join(tempfile.gettempdir(), "redblue_artifacts")

# Only write to HKCU, never HKLM
SAFE_REGISTRY_HIVE = "HKCU"
SAFE_REGISTRY_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"

# Network simulation only on localhost
SAFE_HOST = "127.0.0.1"
SAFE_PORTS = [17771, 17772, 17773, 17774, 17775]

# Forbidden targets (never touch these)
FORBIDDEN_PROCESS_NAMES = [
    "lsass.exe", "csrss.exe", "smss.exe", "winlogon.exe",
    "services.exe", "wininit.exe", "System",
]

FORBIDDEN_PATHS = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]

# ================================================================
# Suspicious Ports (used by Red Team to trigger Blue Team detection)
# ================================================================

ATTACK_PORTS = [
    4444,   # Metasploit default
    5555,   # Common RAT
    1337,   # Leet port
    6667,   # IRC (C2)
    8888,   # Common RAT
    9999,   # Common RAT
]

# ================================================================
# Severity Levels (shared with Blue Team)
# ================================================================

SEVERITY_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

# ================================================================
# Ransomware Simulation
# ================================================================

RANSOM_XOR_KEY = 0x42              # Known key for simulated "encryption"
RANSOM_FILE_COUNT_DEFAULT = 10     # Default number of dummy files

# ================================================================
# Pipeline Integration
# ================================================================

USE_INTEGRATED_PIPELINE = False    # Set True to use full detection pipeline
PIPELINE_ALERT_ENABLED = False     # Set True to send alerts during game

# ================================================================
# Strategy & Botnet
# ================================================================

STRATEGY_ENABLED = True            # Set True to use kill chain strategy engine
BOTNET_ENABLED = True              # Set True to enable parallel botnet attacks
BOTNET_WAVE_SIZE = 3               # Attacks per wave in wave mode
BOTNET_DEFAULT_MODE = "wave"       # Default: sequential, wave, swarm, coordinated

# ================================================================
# VM IDS
# ================================================================

VM_IDS_ENABLED = True              # Deploy IDS during exercise setup
STEALTH_IDS_PORT = 19091           # Host port for stealth IDS metrics
