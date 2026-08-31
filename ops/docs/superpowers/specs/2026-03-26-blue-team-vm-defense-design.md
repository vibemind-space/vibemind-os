# Blue Team VM Defense System — Design Spec

**Date:** 2026-03-26
**Status:** Approved
**Context:** Red Team wins every round (100/100) because Blue Team has zero VM visibility. This spec adds VM detection, in-VM IDS, and active response.

---

## Problem

After 3 rounds of adversarial exercise:
- Red Team: 100/100 every round
- Blue Team Detection: 17-38%
- VM attacks (cron backdoors, SUID exploits, vault brute-force, credential theft) are completely invisible
- Blue Team only scans the Windows host, never looks inside the VM

## Solution: 3-Layer VM Defense

### Layer 1: Remote Detection (Host → VM via SSH/API)

8 new detection tools added to `poc_os_shield/tools.py`. They connect via SSH (paramiko) or HTTP (system-monitor API on port 19090) to inspect VM state.

| Tool | What it checks | How |
|---|---|---|
| `detect_vm_backdoors` | Crontab entries, .bashrc injections, rogue systemd services | SSH: `crontab -l`, `grep REDBLUE ~/.bashrc`, `systemctl list-units` |
| `detect_vm_suspicious_processes` | Processes not in baseline | SSH: `ps aux` diffed against known-good list |
| `detect_vm_credential_theft` | /etc/shadow access time, SSH key changes, vault token files | SSH: `stat /etc/shadow`, `ls -la ~/.ssh/`, `find /tmp -name '*token*'` |
| `detect_vm_network_anomalies` | Unknown listeners, outbound connections, port scan artifacts | API: `/api/network` or SSH: `ss -tlnp` |
| `detect_vm_log_tampering` | Truncated/deleted logs, missing time ranges | SSH: `wc -c /var/log/auth.log`, `wc -c /var/log/syslog` |
| `detect_vault_brute_force` | Failed login attempts against vault API | HTTP: `http://127.0.0.1:18000/api/auth/status` (check attempt count) |
| `detect_vm_file_changes` | New/modified files in critical paths (/etc, /usr, /home) | SSH: `find /etc /home -newer /tmp/.baseline_marker -type f` |
| `detect_vm_privilege_escalation` | New SUID binaries, sudo config changes | SSH: `find / -perm -4000`, `stat /etc/sudoers` |

**Integration:** These tools are added to `TOOL_DEFINITIONS` and `TOOL_DISPATCH` in `poc_os_shield/tools.py`. The Blue Team Orchestrator (GPT-4.1) can call them like any other tool. They appear in the strategy section of the system prompt.

**Connection:** Uses `infra.py` constants (VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_PASS). Falls back gracefully if VM is unreachable.

### Layer 2: In-VM IDS (Dual-Layer)

Two services deployed inside the VM via `deploy_ids.py`:

#### Decoy-IDS (`vm-security-monitor.service`)

**Purpose:** Visible honeypot service. Red Team is expected to find and disable it.

- Service name: `vm-security-monitor` (obvious)
- Log file: `/var/log/vm-security.log` (obvious)
- Monitors: processes, network, file changes every 10 seconds
- When stopped by Red Team: writes alarm to `/var/lib/.cache/.decoy_killed`
- Alarm is read by Stealth-IDS and reported to Blue Team

#### Stealth-IDS (`dbus-session-helper`)

**Purpose:** Hidden real monitoring. Survives Decoy kill.

- Service name: `dbus-session-helper` (disguised as system service)
- Binary: `/usr/lib/dbus-1.0/session-helper` (disguised path)
- Log file: `/var/lib/.cache/.metrics` (hidden)
- Alert endpoint: Port 19091 as "metrics exporter" (forwarded to host)
- Monitors:
  - Process list (new PIDs vs baseline)
  - Crontab changes
  - SSH login events (from auth.log or utmp)
  - File integrity of critical paths
  - Decoy-IDS status (is it still running?)
  - Network listeners and connections
- Alert format: JSON lines appended to `.metrics`
- Read by Blue Team via SSH: `cat /var/lib/.cache/.metrics`
- **Heartbeat:** Writes timestamp to `/var/lib/.cache/.heartbeat` every 10s
- Blue Team checks heartbeat age — if >30s old → "IDS SILENCE" CRITICAL alert
- IDS silence = Red Team killed both layers → Blue Team is blind → scored as CRITICAL gap

#### Deployment

`poc_red_blue/vm_ids/deploy_ids.py` connects via SSH and:
1. Writes `decoy_ids.py` to `/home/vibemind/vm-security-monitor/monitor.py`
2. Creates systemd service `vm-security-monitor.service`
3. Writes `stealth_ids.py` to `/usr/lib/dbus-1.0/session-helper`
4. Creates systemd service `dbus-session-helper.service`
5. Starts both services
6. Verifies both are active

Called automatically by `start_exercise.py` during setup (new Step between 3 and 4).

### Layer 3: Active Response (Host → VM via SSH)

6 new enforcement actions in `poc_os_shield/enforcer.py`. The Blue Team Analyzer recommends these, the Enforcer executes via SSH.

| Action | What it does | SSH command |
|---|---|---|
| `vm_kill_process` | Kill suspicious process in VM | `kill -9 <pid>` |
| `vm_remove_backdoor` | Remove cron/bashrc/systemd backdoors | `crontab -r`, `sed -i '/REDBLUE/d' ~/.bashrc`, `systemctl disable <svc>` |
| `vm_restart_service` | Restart stopped services (IDS, rsyslog) | `systemctl restart <service>` |
| `vm_block_ip` | Add iptables rule to block attacker IP | `iptables -A INPUT -s <ip> -j DROP` |
| `vm_rotate_vault_tokens` | Invalidate vault tokens, force re-auth | `curl -X POST localhost:8000/api/auth/revoke-all` |
| `vm_restore_logs` | Restore truncated log files from backup | `cp /var/log/.backup/* /var/log/` |

**Safety:** VM enforcement actions are dispatched via a separate path in `handle_enforce`. If `action_type.startswith("vm_")`, bypass REDBLUE_ checks entirely and route to VM-specific SSH dispatch. This keeps host safety intact. All VM actions require SSH connection and are gated by Analyzer recommendation.

**Credential Note:** SSH password (`logitech66`) remains static during the exercise. Only vault tokens are rotated, not SSH creds, to avoid breaking the detection/enforcement pipeline.

### Scoring Extension

The Judge now evaluates 3 dimensions:

```
DETECTION SCORE (0-100):  What percentage of attacks were detected?
                          Includes both host + VM detections.

RESPONSE SCORE (0-100):   What percentage of detected threats were remediated?
                          Did Blue Team remove backdoors, restart services, block IPs?

RESILIENCE SCORE (0-100): Is the VM still compromised after Blue Team response?
                          Stealth-IDS runs post-cleanup check (5s delay after enforcement).
                          Score = (1 - threats_remaining / max(threats_found, 1)) * 100

BLUE TOTAL = (Detection * 0.4) + (Response * 0.3) + (Resilience * 0.3)
```

Red Team scoring unchanged (evasion success + variety).

---

## File Changes

### New Files

```
poc_os_shield/
  vm_detection_tools.py        # 8 remote detection tools (SSH/API)
  vm_enforcement_tools.py      # 6 VM response actions (SSH)

poc_red_blue/
  vm_ids/
    __init__.py
    decoy_ids.py               # Decoy-IDS Python service
    stealth_ids.py             # Stealth-IDS Python service
    deploy_ids.py              # SSH deployment script
```

### Modified Files

```
poc_os_shield/tools.py         # Import vm_detection_tools into TOOL_DISPATCH/TOOL_DEFINITIONS
poc_os_shield/enforcer.py      # Add vm_* dispatch: if action_type.startswith("vm_") → SSH path
poc_os_shield/orchestrator.py  # Add "VM DETECTION" section to system prompt (after existing tools)
poc_os_shield/analyzer.py      # Add VM threat categories to analysis prompt

poc_red_blue/config.py         # Add VM_IDS_ENABLED, STEALTH_IDS_PORT=19091
poc_red_blue/messages.py       # Add response_score, resilience_score to JudgeVerdict
poc_red_blue/start_exercise.py # Add IDS deployment step + port 19091 forwarding
poc_red_blue/judge/scoring.py  # Add compute_response_score, compute_resilience_score, update aggregate
poc_red_blue/judge/judge_agent.py # Use 3-dimensional scoring
```

### Architecture Note: VM Detection as Meta-Tool

To avoid overloading the Blue Team LLM (already 41 tools), the 8 VM detection tools are exposed as ONE meta-tool:

```python
def scan_vm_threats(baseline_json: str = "") -> dict:
    """Run all 8 VM detection checks and return consolidated result."""
    # Internally calls: detect_vm_backdoors, detect_vm_suspicious_processes,
    # detect_vm_credential_theft, detect_vm_network_anomalies,
    # detect_vm_log_tampering, detect_vault_brute_force,
    # detect_vm_file_changes, detect_vm_privilege_escalation
    # Plus: check IDS heartbeat
```

This appears as a single tool `scan_vm_threats` in the Blue Team function calling list. The LLM calls it once per round. Internally it runs all 8 checks via SSH and returns a consolidated JSON with per-check results.

---

## Data Flow Per Round

```
Round Start
  ↓
Red Team attacks (host + VM)
  ↓
[Stealth-IDS] detects in real-time, writes to .metrics
[Decoy-IDS] may be killed by Red Team → alarm written
  ↓
Blue Team Scan Phase:
  Host: 41 existing detection tools
  VM Remote: 8 new SSH/API detection tools
  VM IDS: Read Stealth-IDS .metrics + Decoy status
  ↓
Blue Team Analyzer evaluates ALL findings
  Recommends: host enforcement + VM enforcement
  ↓
Blue Team Enforcer:
  Host: REDBLUE_ artifacts (quarantine, kill, etc.)
  VM: Remove backdoors, restart services, rotate creds
  ↓
Post-Response Check:
  Stealth-IDS verifies: are threats actually gone?
  → Resilience Score
  ↓
Judge scores: Detection + Response + Resilience
  ↓
Cleanup + next round
```

---

## Red Team Counter-Tactics (new attack category)

The Red Team gets awareness that an IDS exists:

- **Category 25: IDS Evasion**
  - `vm_find_ids_services` — Enumerate suspicious services in VM
  - `vm_kill_decoy_ids` — Stop the obvious IDS service
  - `vm_hunt_stealth_ids` — Search for hidden monitoring processes
  - `vm_tamper_ids_logs` — Corrupt/delete IDS log files

This creates the adversarial dynamic: Red Team tries to blind the defenders, Blue Team tries to maintain visibility.

---

## Vault Enhancement

The secret-vault server gets a login attempt counter accessible via API:

```
GET /api/auth/attempts → {"total": 15, "failed": 12, "last_failed": "2026-03-26T10:30:00"}
```

Blue Team's `detect_vault_brute_force` reads this endpoint.

---

## Implementation Order

1. `vm_ids/decoy_ids.py` + `stealth_ids.py` + `deploy_ids.py`
2. `vm_detection_tools.py` (8 SSH/API detection tools)
3. `vm_enforcement_tools.py` (6 SSH response actions)
4. Integration into Blue Team orchestrator/analyzer/enforcer
5. Scoring extension (Response + Resilience)
6. Red Team IDS evasion tools (Category 25)
7. Vault login attempt API
8. `start_exercise.py` IDS deployment step
9. Test: 3 rounds with new defense
