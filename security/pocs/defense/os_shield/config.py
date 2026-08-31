"""
OS Shield Configuration
========================
Central constants for the autonomous OS security system.
"""

import os
import sys
from pathlib import Path

import winreg
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(_env_path)

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from llm_client import get_model

# ================================================================
# LLM Configuration
# ================================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = get_model("blue_team")

# ================================================================
# Severity Levels
# ================================================================

SEVERITY_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

# ================================================================
# File Integrity Monitoring - Critical Directories
# ================================================================

WATCHED_DIRS = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\System32\drivers",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]

# Max files to hash per directory (prevent runaway scans)
MAX_FILES_PER_DIR = 500

# ================================================================
# Registry Autorun Keys
# ================================================================

AUTORUN_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Run"),
]

HIVE_NAMES = {
    winreg.HKEY_LOCAL_MACHINE: "HKLM",
    winreg.HKEY_CURRENT_USER: "HKCU",
    winreg.HKEY_CLASSES_ROOT: "HKCR",
}

# ================================================================
# Suspicious Process Indicators
# ================================================================

SUSPICIOUS_PROCESS_NAMES = [
    "mimikatz", "psexec", "psexesvc",
    "cobaltstrike", "beacon",
    "metasploit", "msfconsole", "meterpreter",
    "nc.exe", "ncat.exe", "netcat",
    "lazagne", "procdump",
    "rubeus", "sharphound", "bloodhound",
    "powershell_ise",
    "certutil",  # often abused for download
    "bitsadmin",  # often abused for download
    "wmic",  # lateral movement
    "mshta",  # script execution bypass
    "regsvr32",  # script execution bypass
    "rundll32",  # dll execution
]

# ================================================================
# Trusted Binary Publishers
# ================================================================

TRUSTED_PUBLISHERS = [
    "Microsoft Corporation",
    "Microsoft Windows",
    "Microsoft Windows Publisher",
    "Google LLC",
    "Mozilla Corporation",
    "Apple Inc.",
]

# ================================================================
# Network - Suspicious Ports (outbound)
# ================================================================

SUSPICIOUS_OUTBOUND_PORTS = [
    4444,   # Metasploit default
    5555,   # Common RAT
    1337,   # Leet port / backdoor
    31337,  # Back Orifice
    6666, 6667, 6668, 6669,  # IRC (C2)
    8888,   # Common RAT
    9999,   # Common RAT
    12345,  # NetBus
    54321,  # Common backdoor
]

# ================================================================
# Watch Mode Settings
# ================================================================

WATCH_INTERVAL = 30  # seconds between scans in continuous mode
AUTO_ENFORCE = False  # if True, enforce without confirmation (except CRITICAL)

# ================================================================
# Quarantine
# ================================================================

QUARANTINE_DIR = r"C:\os_shield_quarantine"

# ================================================================
# Baseline
# ================================================================

DEFAULT_BASELINE_PATH = "baseline.json"
