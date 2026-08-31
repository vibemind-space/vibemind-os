"""
OrchestratorAgent - Autonomous OS Security via OpenAI Function Calling
========================================================================
Receives ShieldRequest, uses GPT-4o to autonomously decide which monitors
to run and in what order. Dispatches MonitorTasks, collects results, then
forwards to ThreatAnalyzerAgent, EnforcerAgent, and ReporterAgent.
"""

import json
import os
import sys
import uuid

from openai import AsyncOpenAI

from autogen_core import (
    AgentId,
    RoutedAgent,
    message_handler,
    MessageContext,
)

from messages import (
    ShieldRequest, MonitorTask, MonitorResult,
    ThreatAnalysisRequest, ThreatAnalysis,
    EnforceRequest, EnforceResult,
    ReportRequest, SecurityReport,
)
from tools import TOOL_DEFINITIONS, think

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model


class OrchestratorAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("OrchestratorAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_shield_request(
        self, message: ShieldRequest, ctx: MessageContext
    ) -> SecurityReport:
        print(f"\n  [ORCHESTRATOR] Mode: {message.mode}", flush=True)
        print(f"  [ORCHESTRATOR] Domains: {message.scan_domains}", flush=True)

        # Build baseline context for the LLM
        baseline_context = ""
        if message.baseline_json:
            try:
                baseline = json.loads(message.baseline_json)
                baseline_context = (
                    f"\nBaseline available (captured at {baseline.get('timestamp', '?')}):\n"
                    f"- {len(baseline.get('process_pids', []))} known PIDs\n"
                    f"- {len(baseline.get('known_remote_ips', []))} known remote IPs\n"
                    f"- {len(baseline.get('autorun_entries', []))} autorun entries\n"
                    f"- {len(baseline.get('usb_device_ids', []))} USB devices\n\n"
                    f"Use baseline data with detect_new_processes, "
                    f"detect_suspicious_connections, and check_registry_autoruns "
                    f"to find deviations.\n"
                    f"Baseline PIDs JSON: {json.dumps(baseline.get('process_pids', []))}\n"
                    f"Baseline Remote IPs JSON: {json.dumps(baseline.get('known_remote_ips', []))}\n"
                    f"Baseline Autoruns JSON: {json.dumps(baseline.get('autorun_entries', []))}\n"
                )
            except json.JSONDecodeError:
                pass

        system_prompt = (
            "You are an autonomous OS security monitor for Windows 11.\n\n"
            "Your mission: Scan the local system for security threats and anomalies.\n\n"
            "Available tools:\n"
            "BASIC MONITORING:\n"
            "- list_processes: Broad process scan\n"
            "- detect_new_processes: Diff vs baseline PIDs\n"
            "- check_binary_signature: Verify if an .exe/.dll is signed\n"
            "- check_file_integrity: Hash files and compare vs baseline\n"
            "- list_network_connections: All active connections\n"
            "- detect_suspicious_connections: Find unknown remote IPs\n"
            "- manage_firewall_rule: Add/remove/list firewall rules\n"
            "- list_usb_devices: Enumerate USB devices\n"
            "- check_registry_autoruns: Inspect autorun registry keys\n\n"
            "ADVANCED THREAT DETECTION:\n"
            "- detect_parent_child_anomalies: Catch malware chains (Word->PowerShell, Browser->cmd)\n"
            "- detect_encoded_commands: Find Base64/obfuscated PowerShell commands\n"
            "- detect_beaconing: Monitor for C2 check-in patterns (takes ~30s)\n"
            "- detect_suspicious_paths: Find processes running from Temp/Downloads\n"
            "- detect_lsass_access: Detect credential theft (mimikatz, procdump)\n"
            "- detect_data_exfiltration: Monitor for large data uploads (takes ~5s)\n\n"
            "PRIVILEGE ESCALATION DETECTION:\n"
            "- detect_token_manipulation: Token elevation, privilege abuse, Potato exploits\n"
            "- detect_uac_bypass_attempts: UAC bypass registry keys + process chains (fodhelper, eventvwr)\n"
            "- detect_service_tampering: Suspicious service/autorun entries, exploitation keywords\n\n"
            "EXECUTION DETECTION:\n"
            "- detect_wmi_execution: WmiPrvSE spawning children, wmic process call create\n"
            "- detect_dll_anomalies: Unsigned/tiny DLLs in temp paths, sideloading indicators\n"
            "- detect_script_chains: Multi-stage script chains (cmd->ps->wscript), .vbs/.js in temp\n\n"
            "IMPACT DETECTION:\n"
            "- detect_mass_file_operations: Rapid file creation/modification (ransomware pattern)\n"
            "- detect_ransom_indicators: Encrypted file extensions, ransom notes\n"
            "- detect_service_disruption: Disabled/stopped tasks and services\n\n"
            "DISCOVERY DETECTION:\n"
            "- detect_system_enumeration: Catch systeminfo, ipconfig, net user, whoami recon commands\n"
            "- detect_network_reconnaissance: Catch nmap, arp, route, net share, sc query activity\n\n"
            "COLLECTION DETECTION:\n"
            "- detect_collection_activity: Screenshot files, keylog files, clipboard data, staging archives\n"
            "- detect_sensitive_file_access: Browser DBs, credential files, SSH keys in temp dirs\n\n"
            "ANTI-FORENSICS DETECTION:\n"
            "- detect_log_tampering: Timestomped files, log clearing markers, indicator removal traces\n\n"
            "CREDENTIAL/LATERAL/C2 DETECTION:\n"
            "- detect_brute_force_attempts: Rapid net use failures, authentication attempts\n"
            "- detect_lateral_movement_tools: mstsc (RDP), winrs (WinRM), PsExec, net use remote\n"
            "- detect_c2_channels: HTTP beaconing, DNS tunneling, self-signed certs, suspicious listeners\n\n"
            "EXTERNAL TARGET DETECTION:\n"
            "- detect_vault_attacks: Brute force artifacts, JWT tokens, credential dumps targeting secret-vault\n"
            "- detect_api_scanning: API enumeration output, processes with many connections\n"
            "- detect_credential_exfiltration: Files with tokens, passwords, keys in temp dirs\n"
            "- detect_port_scanning: Scan result files, nmap/masscan processes\n"
            "- detect_ssh_lateral_movement: SSH tools, credentials in cmdline, outbound SSH\n"
            "- detect_supply_chain_tampering: REDBLUE_ files in shared folders\n"
            "- detect_llm_manipulation: Prompt injection artifacts, Ollama connections\n"
            "- detect_abnormal_cleanup: BleachBit/CCleaner processes\n\n"
            "VM DEFENSE:\n"
            "- scan_vm_threats: COMPREHENSIVE VM scan — backdoors, processes, credentials, network, logs, vault, files, privilege escalation, IDS status. Run this EVERY round for VM visibility.\n\n"
            "- think: Reason about findings step-by-step\n\n"
            "Strategy:\n"
            "1. BROAD SCAN: list_processes + list_network_connections + check_registry_autoruns\n"
            "2. THREAT HUNT: detect_parent_child_anomalies + detect_encoded_commands + detect_lsass_access\n"
            "3. PRIVILEGE ESCALATION: detect_token_manipulation + detect_uac_bypass_attempts + detect_service_tampering\n"
            "4. EXECUTION: detect_wmi_execution + detect_dll_anomalies + detect_script_chains\n"
            "5. IMPACT: detect_mass_file_operations + detect_ransom_indicators + detect_service_disruption\n"
            "6. DISCOVERY: detect_system_enumeration + detect_network_reconnaissance\n"
            "7. COLLECTION: detect_collection_activity + detect_sensitive_file_access\n"
            "8. ANTI-FORENSICS: detect_log_tampering\n"
            "9. CREDENTIAL/LATERAL/C2: detect_brute_force_attempts + detect_lateral_movement_tools + detect_c2_channels\n"
            "10. THINK about combined findings\n"
            "11. DEEP DIVE: detect_suspicious_paths + detect_beaconing + detect_data_exfiltration\n"
            "12. INVESTIGATE: check_binary_signature on suspicious binaries, list_usb_devices\n"
            "13. CORRELATE: Use think to connect findings across all tools\n"
            "14. EXTERNAL TARGETS: detect_vault_attacks + detect_api_scanning + detect_port_scanning\n"
            "15. VM DEFENSE: scan_vm_threats for comprehensive VM threat detection\n"
            "When satisfied, respond with a text summary (no tool call)\n\n"
            "Be thorough. Run ALL detection tools across all categories. Focus on real threats.\n"
            f"{baseline_context}"
        )

        user_prompt = (
            f"Scan this Windows 11 system for security threats.\n"
            f"Mode: {message.mode}\n"
            f"Requested domains: {message.scan_domains}\n\n"
            f"Begin the security scan."
        )

        messages_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        all_results = []
        max_iterations = 20

        for iteration in range(max_iterations):
            print(f"\n  [ORCHESTRATOR] LLM call #{iteration + 1}...", flush=True)

            response = await self._llm_client.chat.completions.create(
                model=get_model("blue_team"),
                temperature=0,
                messages=messages_history,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )

            choice = response.choices[0]

            # Done?
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                print(
                    f"  [ORCHESTRATOR] Done. {len(all_results)} results collected.",
                    flush=True,
                )
                messages_history.append({
                    "role": "assistant",
                    "content": choice.message.content or "",
                })
                break

            messages_history.append(choice.message.model_dump())

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    print(f"  [ORCHESTRATOR] -> {fn_name}(INVALID JSON -- skipping)", flush=True)
                    messages_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"error": "Invalid JSON in tool arguments"}),
                    })
                    continue
                task_id = str(uuid.uuid4())[:8]

                print(
                    f"  [ORCHESTRATOR] -> {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:80]})",
                    flush=True,
                )

                if fn_name == "think":
                    think_result = await think(
                        fn_args["reasoning_prompt"], self._llm_client
                    )
                    tool_output = json.dumps(think_result)
                    print(
                        f"  [ORCHESTRATOR]    Think: {think_result['severity_assessment']}",
                        flush=True,
                    )
                else:
                    # Dispatch to MonitorAgent
                    task = MonitorTask(
                        tool_name=fn_name,
                        arguments_json=json.dumps(fn_args),
                        task_id=task_id,
                    )

                    try:
                        result: MonitorResult = await self.send_message(
                            task,
                            recipient=AgentId("monitor_agent", "default"),
                        )
                        result_data = json.loads(result.result_json)
                        all_results.append({
                            "task_id": result.task_id,
                            "tool_name": result.tool_name,
                            "success": result.success,
                            "result": result_data,
                        })
                        tool_output = result.result_json

                        warning = result_data.get("warning")
                        if warning:
                            print(f"  [ORCHESTRATOR]    WARNING: {warning[:80]}", flush=True)
                        else:
                            print(f"  [ORCHESTRATOR]    OK", flush=True)

                    except Exception as e:
                        tool_output = json.dumps({"error": str(e)})
                        print(f"  [ORCHESTRATOR]    Error: {e}", flush=True)

                messages_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output,
                })

        # ---- Phase 2: Threat Analysis ----
        print(
            f"\n  [ORCHESTRATOR] Sending {len(all_results)} results to analyzer...",
            flush=True,
        )

        analysis: ThreatAnalysis = await self.send_message(
            ThreatAnalysisRequest(
                all_results_json=json.dumps(all_results, indent=2, default=str),
                context=message.mode,
            ),
            recipient=AgentId("analyzer_agent", "default"),
        )
        print(
            f"  [ORCHESTRATOR] Analysis: {analysis.severity}",
            flush=True,
        )

        # ---- Phase 3: Enforcement ----
        enforcement_results = []
        try:
            actions = json.loads(analysis.recommended_actions_json)
        except (json.JSONDecodeError, TypeError):
            actions = []

        if actions:
            print(
                f"  [ORCHESTRATOR] {len(actions)} enforcement actions recommended.",
                flush=True,
            )

            for action in actions:
                enforce_req = EnforceRequest(
                    action_type=action.get("action_type", ""),
                    parameters_json=json.dumps(action.get("parameters", {})),
                    severity=action.get("severity", "MEDIUM"),
                    requires_confirmation=action.get("severity", "") in ("CRITICAL", "HIGH"),
                )

                enforce_result: EnforceResult = await self.send_message(
                    enforce_req,
                    recipient=AgentId("enforcer_agent", "default"),
                )

                enforcement_results.append({
                    "action_type": enforce_result.action_type,
                    "success": enforce_result.success,
                    "details": enforce_result.details,
                })

                status = "OK" if enforce_result.success else "FAILED"
                print(
                    f"  [ORCHESTRATOR] Enforce [{status}]: {enforce_result.details[:60]}",
                    flush=True,
                )

        # ---- Phase 4: Report ----
        print(f"  [ORCHESTRATOR] Generating report...", flush=True)

        report: SecurityReport = await self.send_message(
            ReportRequest(
                scan_results_json=json.dumps(all_results, indent=2, default=str),
                analysis_reasoning=analysis.reasoning,
                analysis_severity=analysis.severity,
                analysis_findings_json=analysis.findings_json,
                enforcement_results_json=json.dumps(enforcement_results),
            ),
            recipient=AgentId("reporter_agent", "default"),
        )

        print(
            f"  [ORCHESTRATOR] Report ready. "
            f"{report.finding_count} findings, {report.actions_taken} actions.",
            flush=True,
        )

        return report
