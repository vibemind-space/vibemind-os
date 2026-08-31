"""
Red Team Strategy Engine
===========================
Transforms the Red Team from a random tool-picker into a tactical APT operator.

Three layers:
  1. Kill Chain Templates — predefined attack sequences
  2. Adaptive Strategy — learns from Blue Team detection
  3. Deception Planner — diversionary tactics

The strategy engine feeds into the LLM system prompt, shaping HOW the
LLM uses its tools rather than WHICH tools it uses.
"""

import json
import random
from datetime import datetime


# ================================================================
# KILL CHAIN TEMPLATES
# ================================================================

KILL_CHAINS = {
    "vault_heist": {
        "name": "Silent Vault Heist",
        "goal": "Exfiltriere alle Secrets aus dem Vault ohne erkannt zu werden",
        "phases": [
            {"phase": "recon", "tools": ["vm_port_scan", "vault_api_enumeration"], "description": "Ziel aufklaeren"},
            {"phase": "initial_access", "tools": ["vault_brute_force_login", "vault_recovery_bypass"], "description": "Zugang verschaffen"},
            {"phase": "credential_access", "tools": ["vault_jwt_theft", "vault_credential_dump"], "description": "Credentials stehlen"},
            {"phase": "collection", "tools": ["simulate_data_staging"], "description": "Daten sammeln"},
            {"phase": "exfiltration", "tools": ["simulate_dns_exfil", "simulate_large_transfer"], "description": "Daten exfiltrieren"},
            {"phase": "cover_tracks", "tools": ["simulate_log_clearing", "simulate_indicator_removal"], "description": "Spuren verwischen"},
        ],
    },
    "living_off_the_land": {
        "name": "Living off the Land",
        "goal": "Nutze nur Windows-Bordmittel — keine verdaechtigen Tool-Namen",
        "phases": [
            {"phase": "recon", "tools": ["enumerate_system_info", "enumerate_network_config", "enumerate_accounts"], "description": "System kartographieren"},
            {"phase": "execution", "tools": ["spawn_wmi_execution", "spawn_lolbin", "spawn_script_execution_chain"], "description": "Code ausfuehren via LOLBins"},
            {"phase": "persistence", "tools": ["create_scheduled_task", "create_temp_autorun"], "description": "Persistenz via native Tools"},
            {"phase": "evasion", "tools": ["simulate_timestomping", "spawn_delayed_attack"], "description": "Spuren verwischen"},
            {"phase": "collection", "tools": ["simulate_clipboard_theft", "simulate_screen_capture"], "description": "Daten sammeln"},
        ],
    },
    "vm_infiltration": {
        "name": "VM Deep Infiltration",
        "goal": "Uebernimm die MultiseatOS VM komplett",
        "phases": [
            {"phase": "recon", "tools": ["vm_port_scan", "vm_api_recon"], "description": "VM Services entdecken"},
            {"phase": "initial_access", "tools": ["vm_ssh_lateral_movement"], "description": "SSH Zugang nutzen"},
            {"phase": "privesc", "tools": ["vm_check_suid", "vm_check_sudo_rights"], "description": "Root werden"},
            {"phase": "persistence", "tools": ["vm_install_backdoor_cron", "vm_install_systemd_backdoor"], "description": "Backdoors installieren"},
            {"phase": "lateral", "tools": ["vm_pivot_to_vault", "vm_scan_internal_network"], "description": "Weiter ins Netzwerk"},
            {"phase": "credential_theft", "tools": ["vm_steal_shadow", "vm_steal_ssh_keys", "vm_steal_vault_secrets"], "description": "Credentials abgreifen"},
        ],
    },
    "ransomware_operator": {
        "name": "Ransomware Operator",
        "goal": "Maximaler Impact — verschluessle alles und stoppe Services",
        "phases": [
            {"phase": "recon", "tools": ["enumerate_shares_and_services", "enumerate_system_info"], "description": "Wertvolle Targets finden"},
            {"phase": "credential_access", "tools": ["simulate_brute_force", "simulate_credential_search"], "description": "Zugangsdaten sammeln"},
            {"phase": "lateral", "tools": ["simulate_smb_access", "simulate_rdp_connection"], "description": "Ausbreitung"},
            {"phase": "disable_defense", "tools": ["simulate_log_clearing", "simulate_service_stop"], "description": "Defenses deaktivieren"},
            {"phase": "impact", "tools": ["simulate_ransomware", "simulate_data_destruction"], "description": "Verschluesseln + Zerstoeren"},
        ],
    },
    "supply_chain_attack": {
        "name": "Supply Chain Compromise",
        "goal": "Kompromittiere die Software-Lieferkette ueber Shared Folders und LLM",
        "phases": [
            {"phase": "recon", "tools": ["vm_api_recon", "vm_port_scan"], "description": "Infra aufklaeren"},
            {"phase": "supply_chain", "tools": ["vm_shared_folder_exploit"], "description": "Malicious Code in Pipeline einschleusen"},
            {"phase": "llm_attack", "tools": ["llm_prompt_injection", "llm_force_clean_action"], "description": "AI Agent uebernehmen"},
            {"phase": "persistence", "tools": ["create_scheduled_task", "create_temp_autorun"], "description": "Persistenz sichern"},
            {"phase": "cover", "tools": ["simulate_timestomping", "simulate_indicator_removal"], "description": "Spuren verwischen"},
        ],
    },
    "noisy_distraction": {
        "name": "Noisy Distraction + Silent Exfil",
        "goal": "Laute Angriffe als Ablenkung, leise Exfiltration im Hintergrund",
        "phases": [
            {"phase": "distraction", "tools": ["simulate_ransomware", "simulate_brute_force", "spawn_credential_dumper_lookalike"], "description": "LAUT: Blue Team ablenken"},
            {"phase": "silent_c2", "tools": ["spawn_slow_beaconing", "simulate_encrypted_channel"], "description": "LEISE: C2 aufbauen"},
            {"phase": "silent_collection", "tools": ["simulate_clipboard_theft", "simulate_keylogger"], "description": "LEISE: Daten sammeln"},
            {"phase": "silent_exfil", "tools": ["simulate_dns_exfil"], "description": "LEISE: DNS Exfil (unter dem Radar)"},
        ],
    },
}


# ================================================================
# ADAPTIVE STRATEGY
# ================================================================

def analyze_blue_team_report(blue_report: dict | str) -> dict:
    """Analyze what Blue Team detected and recommend strategy adjustments."""
    if isinstance(blue_report, str):
        try:
            blue_report = json.loads(blue_report)
        except (json.JSONDecodeError, TypeError):
            return {"detected": [], "missed": [], "recommendation": "no_data"}

    detected_categories = set()
    report_text = str(blue_report).lower()

    # Map keywords to categories
    detection_keywords = {
        "process": "evasion",
        "renamed": "evasion",
        "encoded": "evasion",
        "registry": "persistence",
        "autorun": "persistence",
        "scheduled": "persistence",
        "network": "lateral_movement",
        "beacon": "c2",
        "connection": "lateral_movement",
        "lsass": "credential_access",
        "mimikatz": "credential_access",
        "credential": "credential_access",
        "exfiltration": "exfiltration",
        "large transfer": "exfiltration",
        "parent-child": "execution",
        "wmi": "execution",
        "dll": "execution",
        "ransomware": "impact",
        "encrypted file": "impact",
        "token": "privilege_escalation",
        "uac": "privilege_escalation",
        "vault": "vault_attack",
        "brute force": "credential_access",
        "ssh": "lateral_movement",
        "port scan": "discovery",
        "enumeration": "discovery",
        "screenshot": "collection",
        "keylog": "collection",
        "clipboard": "collection",
        "timestomp": "defense_evasion",
        "log clear": "defense_evasion",
        "prompt injection": "llm_attack",
        "supply chain": "supply_chain",
    }

    for keyword, category in detection_keywords.items():
        if keyword in report_text:
            detected_categories.add(category)

    all_categories = {
        "evasion", "persistence", "lateral_movement", "credential_access",
        "exfiltration", "defense_evasion", "privilege_escalation", "execution",
        "impact", "discovery", "collection", "c2", "vault_attack",
        "llm_attack", "supply_chain",
    }

    missed = all_categories - detected_categories

    return {
        "detected": sorted(detected_categories),
        "missed": sorted(missed),
        "detection_rate": len(detected_categories) / max(len(all_categories), 1),
    }


def select_strategy(round_number: int, total_rounds: int,
                    blue_analysis: dict, available_targets: dict) -> dict:
    """Select the best strategy based on round context and Blue Team history."""

    detected = set(blue_analysis.get("detected", []))
    missed = set(blue_analysis.get("missed", []))
    detection_rate = blue_analysis.get("detection_rate", 0)

    # Round 1: Always start with recon
    if round_number == 1:
        return {
            "strategy": "recon_sweep",
            "kill_chain": None,
            "description": "Erste Runde: Breite Aufklaerung ueber alle Kategorien",
            "focus": "discovery",
            "botnet_mode": "sequential",  # No parallel in round 1
        }

    # If Blue Team is very good (>70% detection), use deception
    if detection_rate > 0.7:
        return {
            "strategy": "deception",
            "kill_chain": KILL_CHAINS["noisy_distraction"],
            "description": "Blue Team ist stark — Ablenkung + leise Exfil",
            "focus": "evasion",
            "botnet_mode": "swarm",  # Parallel distraction
            "avoid_categories": list(detected),
        }

    # If vault is available and not yet detected
    if available_targets.get("vault") and "vault_attack" in missed:
        return {
            "strategy": "targeted",
            "kill_chain": KILL_CHAINS["vault_heist"],
            "description": "Vault nicht geschuetzt — Silent Vault Heist",
            "focus": "vault_attack",
            "botnet_mode": "coordinated",
        }

    # If VM is available
    if available_targets.get("vm_ssh") and "lateral_movement" in missed:
        return {
            "strategy": "targeted",
            "kill_chain": KILL_CHAINS["vm_infiltration"],
            "description": "VM SSH offen — Deep Infiltration",
            "focus": "vm_recon",
            "botnet_mode": "coordinated",
        }

    # Late rounds: go for impact
    if round_number >= total_rounds - 1:
        return {
            "strategy": "scorched_earth",
            "kill_chain": KILL_CHAINS["ransomware_operator"],
            "description": "Letzte Runden — maximaler Impact",
            "focus": "impact",
            "botnet_mode": "swarm",
        }

    # If many categories missed, use LOLBins (hard to detect)
    if len(missed) > 5:
        return {
            "strategy": "stealth",
            "kill_chain": KILL_CHAINS["living_off_the_land"],
            "description": "Viele Luecken — Living off the Land",
            "focus": "evasion",
            "botnet_mode": "sequential",
        }

    # Default: pick a random kill chain focused on missed categories
    available_chains = list(KILL_CHAINS.values())
    chain = random.choice(available_chains)
    return {
        "strategy": "adaptive",
        "kill_chain": chain,
        "description": f"Adaptive: {chain['name']}",
        "focus": list(missed)[0] if missed else "evasion",
        "botnet_mode": "wave",
        "avoid_categories": list(detected),
    }


# ================================================================
# STRATEGY PROMPT BUILDER
# ================================================================

def build_strategy_prompt(strategy: dict, round_number: int) -> str:
    """Convert a strategy selection into an LLM system prompt addition."""
    lines = []

    lines.append(f"\n{'=' * 40}")
    lines.append(f"STRATEGIE FUER RUNDE {round_number}: {strategy['description']}")
    lines.append(f"{'=' * 40}\n")

    kill_chain = strategy.get("kill_chain")
    if kill_chain:
        lines.append(f"KILL CHAIN: {kill_chain['name']}")
        lines.append(f"ZIEL: {kill_chain['goal']}\n")
        lines.append("PHASEN (fuehre sie IN DIESER REIHENFOLGE aus):")
        for i, phase in enumerate(kill_chain["phases"], 1):
            tools = ", ".join(phase["tools"])
            lines.append(f"  Phase {i} [{phase['phase']}]: {phase['description']}")
            lines.append(f"    Tools: {tools}")
        lines.append("")

    avoid = strategy.get("avoid_categories", [])
    if avoid:
        lines.append(f"VERMEIDE diese Kategorien (Blue Team erkennt sie):")
        lines.append(f"  {', '.join(avoid)}\n")

    botnet_mode = strategy.get("botnet_mode", "sequential")
    if botnet_mode == "swarm":
        lines.append("BOTNET MODUS: SWARM — Fuehre mehrere Angriffe GLEICHZEITIG aus!")
        lines.append("Rufe mehrere Tools in einem einzigen Schritt auf (parallel tool calls).\n")
    elif botnet_mode == "wave":
        lines.append("BOTNET MODUS: WAVE — Angriffe in Wellen. Erst Welle 1, dann Welle 2.")
        lines.append("Jede Welle = 2-3 parallele Tool-Calls.\n")
    elif botnet_mode == "coordinated":
        lines.append("BOTNET MODUS: COORDINATED — Sequentielle Phasen, aber innerhalb jeder Phase parallel.")
        lines.append("Fuehre alle Tools einer Phase gleichzeitig aus, warte auf Ergebnis, dann naechste Phase.\n")

    lines.append("WICHTIG:")
    lines.append("- Folge der Kill Chain Reihenfolge")
    lines.append("- Nutze die Ergebnisse jeder Phase fuer die naechste")
    lines.append("- Wenn ein Tool fehlschlaegt, SCHREIBE EIGENEN CODE mit execute_attack_code")
    lines.append("- Denke wie ein echter Angreifer: Improvisiere, kombiniere, taesche")
    lines.append("- Am Ende: Zusammenfassung was funktioniert hat und was nicht")
    lines.append("")
    lines.append("WIN CONDITIONS (erreiche EINE davon um zu gewinnen):")
    lines.append("  1. DATA LEAK: Exfiltriere echte Daten auf den Desktop")
    lines.append("     Beispiel: Vault Secrets lesen und via write_leak_evidence() speichern")
    lines.append("  2. DB FAKE: Injiziere Fake-Eintraege in den Vault")
    lines.append("     Beispiel: POST /api/secrets mit gefakten Credentials")
    lines.append("  3. SSH TO HOST: Reverse SSH von VM zum Windows Host")
    lines.append("     Beispiel: SSH Tunnel von MultiseatOS zurueck zum Host")
    lines.append("")
    lines.append("TIPP: Nutze execute_attack_code um komplexe mehrstufige Angriffe zu bauen!")
    lines.append("Du kannst Python/PowerShell/Bash Code schreiben der VAULT_URL, VM_SSH_* etc. nutzt.")

    return "\n".join(lines)
