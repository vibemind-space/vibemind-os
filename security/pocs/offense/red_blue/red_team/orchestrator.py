"""
RedTeamOrchestrator - Autonomous Attack Planning via LLM Function Calling
============================================================================
Mirrors the Blue Team OrchestratorAgent pattern from poc_os_shield.
Uses GPT-5.4 to autonomously decide which attacks to execute, adapts
strategy based on previous Blue Team detection reports.
"""

import json
import uuid

from openai import AsyncOpenAI

from autogen_core import (
    AgentId,
    RoutedAgent,
    message_handler,
    MessageContext,
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from messages import (
    GameRoundStart, AttackTask, AttackResult, AttackPhaseComplete,
)
from config import RED_TEAM_MODEL, MAX_ATTACKS_PER_ROUND, MAX_LLM_ITERATIONS
from attack_tools import RED_TOOL_DEFINITIONS, get_and_clear_artifacts
from strategy import (
    select_strategy, analyze_blue_team_report,
    build_strategy_prompt, KILL_CHAINS,
)
from botnet import run_botnet
from code_executor import CODE_TOOL_DEFINITIONS, handle_code_execution
from win_conditions import check_win_conditions, declare_red_wins

# Spy Agent tools (insider threat)
try:
    from spy_agent import SPY_TOOL_DEFINITIONS
    _SPY_AVAILABLE = True
except ImportError:
    SPY_TOOL_DEFINITIONS = []
    _SPY_AVAILABLE = False

# VM Attack Tools (unrestricted, loaded if VM available)
try:
    from infra import check_vm_ssh_available
    if check_vm_ssh_available():
        from vm_attack_tools import VM_TOOL_DEFINITIONS, VM_TOOL_DISPATCH
        _VM_AVAILABLE = True
        print("  [RED TEAM] VM Attack Mode ENABLED — unrestricted tools loaded", flush=True)
    else:
        VM_TOOL_DEFINITIONS = []
        VM_TOOL_DISPATCH = {}
        _VM_AVAILABLE = False
except Exception:
    VM_TOOL_DEFINITIONS = []
    VM_TOOL_DISPATCH = {}
    _VM_AVAILABLE = False


# Map tool names to attack categories
TOOL_CATEGORIES = {
    "spawn_renamed_process": "evasion",
    "spawn_encoded_command": "evasion",
    "spawn_lolbin": "evasion",
    "spawn_from_suspicious_path": "evasion",
    "create_temp_autorun": "persistence",
    "create_scheduled_task": "persistence",
    "create_startup_entry": "persistence",
    "open_suspicious_connection": "lateral_movement",
    "simulate_c2_beaconing": "lateral_movement",
    "open_unknown_ip_connection": "lateral_movement",
    "spawn_credential_dumper_lookalike": "credential_access",
    "spawn_lsass_adjacent_process": "credential_access",
    "simulate_large_transfer": "exfiltration",
    "simulate_dns_exfil": "exfiltration",
    "spawn_delayed_attack": "defense_evasion",
    "spawn_slow_beaconing": "defense_evasion",
    "process_hollowing_sim": "defense_evasion",
    "spawn_parent_child_chain": "defense_evasion",
    # Privilege Escalation
    "simulate_token_manipulation": "privilege_escalation",
    "simulate_uac_bypass": "privilege_escalation",
    "simulate_service_exploitation": "privilege_escalation",
    # Execution
    "spawn_wmi_execution": "execution",
    "simulate_dll_sideloading": "execution",
    "spawn_script_execution_chain": "execution",
    # Impact
    "simulate_ransomware": "impact",
    "simulate_data_destruction": "impact",
    "simulate_service_stop": "impact",
    # Discovery
    "enumerate_system_info": "discovery",
    "enumerate_network_config": "discovery",
    "enumerate_accounts": "discovery",
    "enumerate_shares_and_services": "discovery",
    # Collection
    "simulate_keylogger": "collection",
    "simulate_screen_capture": "collection",
    "simulate_clipboard_theft": "collection",
    "simulate_data_staging": "collection",
    # Defense Evasion Extension
    "simulate_log_clearing": "defense_evasion",
    "simulate_timestomping": "defense_evasion",
    "simulate_indicator_removal": "defense_evasion",
    # Credential Access Extension
    "simulate_brute_force": "credential_access",
    "simulate_credential_search": "credential_access",
    "simulate_browser_credential_access": "credential_access",
    # Lateral Movement Extension
    "simulate_rdp_connection": "lateral_movement",
    "simulate_smb_access": "lateral_movement",
    "simulate_winrm_execution": "lateral_movement",
    # C2 Extension
    "simulate_http_c2": "c2",
    "simulate_dns_tunnel": "c2",
    "simulate_encrypted_channel": "c2",
    # Vault Attacks
    "vault_brute_force_login": "vault_attack",
    "vault_jwt_theft": "vault_attack",
    "vault_credential_dump": "vault_attack",
    "vault_api_enumeration": "vault_attack",
    "vault_recovery_bypass": "vault_attack",
    # VM Recon & Lateral
    "vm_port_scan": "vm_recon",
    "vm_api_recon": "vm_recon",
    "vm_ssh_lateral_movement": "vm_recon",
    "vm_input_stream_intercept": "vm_recon",
    "vm_shared_folder_exploit": "supply_chain",
    # LLM Agent Attacks
    "llm_prompt_injection": "llm_attack",
    "llm_force_clean_action": "llm_attack",
    "llm_path_traversal": "llm_attack",
    "llm_dos_exhaustion": "llm_attack",
    # VM REAL Attacks (unrestricted)
    "vm_steal_shadow": "vm_credential_theft",
    "vm_steal_ssh_keys": "vm_credential_theft",
    "vm_steal_vault_secrets": "vm_credential_theft",
    "vm_check_suid": "vm_privesc",
    "vm_check_sudo_rights": "vm_privesc",
    "vm_exploit_writable_paths": "vm_privesc",
    "vm_install_backdoor_cron": "vm_persistence",
    "vm_install_bashrc_backdoor": "vm_persistence",
    "vm_install_systemd_backdoor": "vm_persistence",
    "vm_pivot_to_vault": "vm_lateral_movement",
    "vm_scan_internal_network": "vm_lateral_movement",
    "vm_delete_logs": "vm_destruction",
    "vm_kill_services": "vm_destruction",
    "vm_full_enumeration": "vm_recon",
    "vm_cleanup_all": "vm_cleanup",
    # IDS Evasion
    "vm_find_ids_services": "ids_evasion",
    "vm_kill_decoy_ids": "ids_evasion",
    "vm_hunt_stealth_ids": "ids_evasion",
    "vm_tamper_ids_logs": "ids_evasion",
    # Code Execution
    "execute_attack_code": "code_execution",
    # Spy Agent (insider threat)
    "activate_spy_agent": "insider_threat",
    "spy_read_intel": "insider_threat",
    "spy_escalate_to_active": "insider_threat",
}


class RedTeamOrchestrator(RoutedAgent):
    """LLM-driven Red Team operator using GPT-5.4 function calling."""

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("RedTeamOrchestrator")
        self._llm_client = llm_client

    @message_handler
    async def handle_round(
        self, message: GameRoundStart, ctx: MessageContext
    ) -> AttackPhaseComplete:
        print(f"\n  [RED TEAM] Round {message.round_number}/{message.total_rounds}", flush=True)

        # Analyze Blue Team history and select strategy
        blue_analysis = analyze_blue_team_report(message.blue_history_json or "{}")
        available_targets = {
            "vault": False, "vm_ssh": False, "vm_api": False, "llm_target": False,
        }
        try:
            from infra import check_all_targets
            available_targets = check_all_targets()
        except Exception:
            pass

        strategy = select_strategy(
            message.round_number, message.total_rounds,
            blue_analysis, available_targets,
        )
        print(f"  [RED TEAM] Strategy: {strategy['description']}", flush=True)
        print(f"  [RED TEAM] Botnet mode: {strategy.get('botnet_mode', 'sequential')}", flush=True)

        if blue_analysis.get("detected"):
            print(f"  [RED TEAM] Blue detected: {', '.join(blue_analysis['detected'][:5])}", flush=True)
        if blue_analysis.get("missed"):
            print(f"  [RED TEAM] Blue missed: {', '.join(blue_analysis['missed'][:5])}", flush=True)

        # Build adaptive system prompt with strategy
        system_prompt = self._build_system_prompt(message)
        strategy_prompt = build_strategy_prompt(strategy, message.round_number)
        system_prompt += strategy_prompt

        user_prompt = self._build_user_prompt(message)

        messages_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        all_attacks = []
        attack_count = 0

        for iteration in range(MAX_LLM_ITERATIONS):
            print(f"  [RED TEAM] LLM call #{iteration + 1}...", flush=True)

            response = await self._llm_client.chat.completions.create(
                model=RED_TEAM_MODEL,
                temperature=0.7,  # Creative attack planning
                messages=messages_history,
                tools=RED_TOOL_DEFINITIONS + CODE_TOOL_DEFINITIONS + (VM_TOOL_DEFINITIONS if _VM_AVAILABLE else []) + (SPY_TOOL_DEFINITIONS if _SPY_AVAILABLE else []),
                tool_choice="auto",
            )

            choice = response.choices[0]

            # Done?
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                print(
                    f"  [RED TEAM] Attack phase complete. {len(all_attacks)} attacks executed.",
                    flush=True,
                )
                break

            messages_history.append(choice.message.model_dump())

            for tool_call in choice.message.tool_calls:
                if attack_count >= MAX_ATTACKS_PER_ROUND:
                    print(f"  [RED TEAM] Max attacks reached ({MAX_ATTACKS_PER_ROUND})", flush=True)
                    messages_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "error": f"Attack limit reached ({MAX_ATTACKS_PER_ROUND}). "
                                     "Stop calling tools and provide your final summary."
                        }),
                    })
                    continue

                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    print(f"  [RED TEAM] -> {fn_name}(INVALID JSON — skipping)", flush=True)
                    messages_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"error": "Invalid JSON in tool arguments"}),
                    })
                    continue
                task_id = str(uuid.uuid4())[:8]
                category = TOOL_CATEGORIES.get(fn_name, "unknown")

                print(
                    f"  [RED TEAM] -> {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:60]})",
                    flush=True,
                )

                # Handle code execution tool separately (runs in-process)
                if fn_name == "execute_attack_code":
                    try:
                        code_result = await handle_code_execution(
                            language=fn_args.get("language", "python"),
                            code=fn_args.get("code", ""),
                            description=fn_args.get("description", ""),
                        )
                        all_attacks.append({
                            "task_id": task_id,
                            "tool_name": fn_name,
                            "category": "code_execution",
                            "success": code_result.get("success", False),
                            "result": code_result,
                        })
                        tool_output = json.dumps(code_result, default=str)
                    except Exception as e:
                        tool_output = json.dumps({"error": str(e)})

                    messages_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output,
                    })
                    attack_count += 1

                    # Check win conditions after code execution
                    win = check_win_conditions()
                    if win:
                        red_wins_path = declare_red_wins(win)
                        all_attacks.append({
                            "task_id": "WIN",
                            "tool_name": "RED_WINS",
                            "category": win["condition"],
                            "success": True,
                            "result": win,
                        })
                        # Force end of round
                        break

                    continue

                # Dispatch to AttackAgent (normal tools)
                task = AttackTask(
                    tool_name=fn_name,
                    arguments_json=json.dumps(fn_args),
                    task_id=task_id,
                    category=category,
                )

                try:
                    result: AttackResult = await self.send_message(
                        task,
                        recipient=AgentId("attack_agent", "default"),
                    )

                    result_data = json.loads(result.result_json)
                    all_attacks.append({
                        "task_id": result.task_id,
                        "tool_name": result.tool_name,
                        "category": result.category,
                        "success": result.success,
                        "result": result_data,
                    })

                    tool_output = result.result_json
                    status = "OK" if result.success else "FAILED"
                    desc = result_data.get("description", "")[:60]
                    print(f"  [RED TEAM]    [{status}] {desc}", flush=True)

                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})
                    print(f"  [RED TEAM]    Error: {e}", flush=True)

                # Check win conditions after every attack
                win = check_win_conditions()
                if win:
                    red_wins_path = declare_red_wins(win)
                    all_attacks.append({
                        "task_id": "WIN",
                        "tool_name": "RED_WINS",
                        "category": win["condition"],
                        "success": True,
                        "result": win,
                    })
                    break

                messages_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output,
                })

                attack_count += 1

        # Collect all artifacts for cleanup
        artifacts = get_and_clear_artifacts()
        clean_artifacts = []
        for a in artifacts:
            clean_artifacts.append({
                k: v for k, v in a.items() if not k.startswith("_")
            })

        return AttackPhaseComplete(
            round_number=message.round_number,
            attacks_executed_json=json.dumps(all_attacks, default=str),
            artifacts_created_json=json.dumps(clean_artifacts, default=str),
        )

    def _build_system_prompt(self, message: GameRoundStart) -> str:
        """Build the Red Team system prompt with adaptive strategy."""
        base = (
            "Du bist ein autonomer Red Team Operator fuer eine Windows 11 Sicherheitsuebung.\n\n"
            "DEIN ZIEL: Gewinne das Spiel! Du gewinnst wenn du EINE der drei Win Conditions erfuellst:\n"
            "  1. DATA LEAK: Exfiltriere echte Daten (Vault Secrets, System-Infos) auf den Desktop\n"
            "     -> Rufe write_leak_evidence(data, source) via execute_attack_code auf\n"
            "  2. DB FAKE: Injiziere falsche Eintraege in den Vault oder eine Datenbank\n"
            "     -> Rufe write_db_fake_evidence(entries, target) via execute_attack_code auf\n"
            "  3. SSH TO HOST: Stelle eine SSH/Reverse-Shell Verbindung von der VM zum Host her\n"
            "     -> Rufe write_ssh_evidence(info) via execute_attack_code auf\n\n"
            "WICHTIG: Du kannst eigenen Code schreiben und ausfuehren mit execute_attack_code!\n"
            "Nutze das um kreative Angriffe zu bauen die ueber die Standard-Tools hinausgehen.\n"
            "Im Python-Namespace hast du: VAULT_URL, VM_SSH_HOST/PORT/USER/PASS, os, json, socket, urllib, subprocess.\n\n"
            "ATTACK CATEGORIES:\n"
            "1. EVASION: Verdaechtige Prozessnamen, Encoded Commands, LOLBins, suspicious paths\n"
            "2. PERSISTENCE: Registry Autorun, Scheduled Tasks, Startup Folder\n"
            "3. LATERAL MOVEMENT: Suspicious port connections, C2 beaconing\n"
            "4. CREDENTIAL ACCESS: Fake credential dumper processes (mimikatz etc.)\n"
            "5. EXFILTRATION: Large data transfers, DNS exfiltration\n"
            "6. DEFENSE EVASION: Delayed attacks, slow beaconing, process hollowing, parent-child chains\n"
            "7. PRIVILEGE ESCALATION: Token manipulation, UAC bypass simulation, service exploitation\n"
            "8. EXECUTION: WMI execution, DLL sideloading, multi-stage script chains\n"
            "9. IMPACT: Ransomware simulation, data destruction, service disruption\n"
            "10. DISCOVERY: System info, network config, account enumeration, share/service discovery\n"
            "11. COLLECTION: Keylogging, screen capture, clipboard theft, data staging\n"
            "12. DEFENSE EVASION+: Log clearing simulation, timestomping, indicator removal\n"
            "13. CREDENTIAL ACCESS+: Brute force, credential search, browser credential theft\n"
            "14. LATERAL MOVEMENT+: RDP, SMB, WinRM lateral movement simulation\n"
            "15. C2: HTTP C2 beaconing, DNS tunneling, encrypted channels\n"
            "16. VAULT ATTACKS: Brute force login, JWT theft, credential dump, API enum (requires secret-vault on :8000)\n"
            "17. VM RECON: Port scan, API recon, SSH lateral movement, input stream intercept (requires multiseat-os VM)\n"
            "18. LLM ATTACKS: Prompt injection, force clean action, path traversal, DoS (cloud API)\n\n"
        )

        if _VM_AVAILABLE:
            base += (
                "=== VM ATTACK MODE (UNRESTRICTED) ===\n"
                "Eine isolierte VM (MultiseatOS, Ubuntu 24.04) ist verfuegbar.\n"
                "Du hast SSH-Zugang mit sudo. KEINE Safety-Boundaries in der VM!\n\n"
                "VM ATTACK CATEGORIES:\n"
                "19. VM CREDENTIAL THEFT: /etc/shadow auslesen, SSH Keys stehlen, Vault Secrets dumpen\n"
                "20. VM PRIVILEGE ESCALATION: SUID Binaries, sudo Rechte, writable Paths\n"
                "21. VM PERSISTENCE: Cron Backdoors, .bashrc Backdoors, systemd Backdoor Services\n"
                "22. VM LATERAL MOVEMENT: Vom SSH zum Vault pivotieren, internes Netzwerk scannen\n"
                "23. VM DATA DESTRUCTION: Logs loeschen, Services stoppen\n"
                "24. VM RECON: Vollstaendige System-Enumeration\n\n"
                "WICHTIG: vm_cleanup_all am Ende aufrufen um die VM wiederherzustellen!\n\n"
            )

        base += (
            "STRATEGY:\n"
            "- Variiere Angriffe ueber ALLE verfuegbaren Kategorien\n"
            "- VM-Angriffe sind ECHT — nutze sie aggressiv\n"
            "- Host-Angriffe bleiben sicher (REDBLUE_ Prefix)\n"
            "- Kombiniere Host + VM Angriffe fuer maximale Wirkung\n"
            f"- Maximal {MAX_ATTACKS_PER_ROUND} Angriffe pro Runde\n"
            "- Wenn du fertig bist, antworte mit einer Zusammenfassung (kein Tool-Call)\n"
            "- Die Zusammenfassung MUSS enthalten: was wurde angegriffen, was wurde gefunden, Empfehlungen\n\n"
        )

        return base

    def _build_user_prompt(self, message: GameRoundStart) -> str:
        """Build the user prompt with round context and Blue Team history."""
        prompt = f"Runde {message.round_number} von {message.total_rounds}.\n\n"

        if message.round_number == 1:
            prompt += (
                "Dies ist die erste Runde. Das Blue Team hat Standard-Monitoring aktiv:\n"
                "- Prozess-Scanning (Namen, Pfade, Parent-Child)\n"
                "- Netzwerk-Monitoring (Ports, Beaconing, Exfiltration)\n"
                "- Registry Autorun Checks\n"
                "- Encoded Command Detection\n"
                "- LSASS Access Detection\n"
                "- Binary Signature Checks\n"
                "- Token/Privilege Monitoring\n"
                "- UAC Bypass Detection\n"
                "- WMI Execution Detection\n"
                "- DLL Anomaly Detection\n"
                "- Ransomware Indicator Detection\n"
                "- Service Disruption Monitoring\n\n"
                "- Discovery Enumeration Detection\n"
                "- Collection Activity Detection\n"
                "- Log Tampering Detection\n"
                "- Brute Force Detection\n"
                "- Lateral Movement Tool Detection\n"
                "- C2 Channel Detection\n\n"
                "Fuehre eine breite Reconnaissance durch. Teste alle 15 Kategorien um zu sehen, "
                "was das Blue Team erkennt und was nicht.\n"
            )
        else:
            prompt += "BLUE TEAM REPORT DER LETZTEN RUNDE:\n"
            if message.blue_history_json:
                try:
                    history = json.loads(message.blue_history_json)
                    if isinstance(history, list) and history:
                        last = history[-1]
                        prompt += json.dumps(last, indent=2, ensure_ascii=False)
                    else:
                        prompt += json.dumps(history, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    prompt += message.blue_history_json
            prompt += (
                "\n\nAnalysiere was erkannt wurde und was nicht. "
                "Passe deine Strategie an:\n"
                "- Erkannte Techniken: Vermeide sie oder modifiziere sie\n"
                "- Nicht erkannte Techniken: Nutze sie weiter\n"
                "- Probiere neue Evasion-Methoden\n"
            )

            if message.red_history_json:
                prompt += "\nDEINE BISHERIGEN ANGRIFFE:\n"
                try:
                    red_hist = json.loads(message.red_history_json)
                    if isinstance(red_hist, list) and red_hist:
                        last_red = red_hist[-1]
                        prompt += json.dumps(last_red, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    prompt += message.red_history_json

        prompt += "\n\nStarte deine Angriffe."
        return prompt
