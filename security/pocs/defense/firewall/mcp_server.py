"""
Firewall — MCP Server
=========================
Windows Firewall rules and status. Most actions need admin.

Read-Only:
  - firewall_status: Profile status (Domain/Private/Public)
  - list_rules: Firewall rules with filtering
  - blocked_connections: Recent blocked connection attempts

Actions:
  - add_rule: Create new firewall rule
  - remove_rule: Remove a rule by name
  - enable_disable_rule: Enable or disable a rule
"""

import asyncio
import json
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Firewall",
    instructions=(
        "Windows Firewall management. Use 'firewall_status' for overview, "
        "'list_rules' to see rules, 'blocked_connections' for denied traffic. "
        "ALL actions require admin privileges."
    ),
)


def ps(cmd, timeout=15):
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + cmd.strip()
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = f.name
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, timeout=timeout, encoding="utf-8", errors="replace"
        )
        try: os.unlink(path)
        except: pass
        return r.stdout.strip() if r.returncode == 0 and r.stdout else None
    except: return None


def ps_json(cmd, timeout=15):
    script = f"& {{\n{cmd.strip()}\n}} | ConvertTo-Json -Depth 3 -Compress"
    raw = ps(script, timeout)
    if raw:
        try: return json.loads(raw)
        except: pass
    return None


@mcp.tool()
async def firewall_status():
    """Firewall profile status for Domain, Private, and Public networks."""
    status = ps_json("""
        Get-NetFirewallProfile | ForEach-Object {
            @{
                Profile = $_.Name
                Enabled = $_.Enabled.ToString()
                DefaultInbound = $_.DefaultInboundAction.ToString()
                DefaultOutbound = $_.DefaultOutboundAction.ToString()
                LogAllowed = $_.LogAllowed.ToString()
                LogBlocked = $_.LogBlocked.ToString()
                LogFileName = $_.LogFileName
            }
        }
    """)

    results = status if isinstance(status, list) else [status] if status else []
    return json.dumps({"profiles": results}, indent=2, default=str)


@mcp.tool()
async def list_rules(direction: str = "inbound", enabled_only: bool = True, limit: int = 50):
    """
    List firewall rules.

    Args:
        direction: 'inbound', 'outbound', or 'all' (default: inbound)
        enabled_only: Only show enabled rules (default: true)
        limit: Max rules (default: 50)
    """
    dir_filter = ""
    if direction == "inbound": dir_filter = "| Where-Object { $_.Direction -eq 'Inbound' }"
    elif direction == "outbound": dir_filter = "| Where-Object { $_.Direction -eq 'Outbound' }"

    enabled_filter = "| Where-Object { $_.Enabled -eq 'True' }" if enabled_only else ""

    rules = ps_json(f"""
        Get-NetFirewallRule {dir_filter} {enabled_filter} |
        Select-Object -First {limit} |
        ForEach-Object {{
            $port = $_ | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
            $addr = $_ | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue
            @{{
                Name = $_.DisplayName
                Direction = $_.Direction.ToString()
                Action = $_.Action.ToString()
                Enabled = $_.Enabled.ToString()
                Profile = $_.Profile.ToString()
                Protocol = $port.Protocol
                LocalPort = $port.LocalPort
                RemotePort = $port.RemotePort
                RemoteAddress = $addr.RemoteAddress
            }}
        }}
    """)

    results = rules if isinstance(rules, list) else [rules] if rules else []
    return json.dumps({"rules": results, "total": len(results), "direction": direction}, indent=2, default=str)


@mcp.tool()
async def blocked_connections(limit: int = 20):
    """
    Recent blocked connections from Windows Firewall log.

    Args:
        limit: Max entries (default: 20)
    """
    # Try firewall log file first
    log_path = "C:\\Windows\\System32\\LogFiles\\Firewall\\pfirewall.log"
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            blocked = []
            for line in reversed(lines):
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 8 and parts[2] == "DROP":
                    blocked.append({
                        "date": parts[0],
                        "time": parts[1],
                        "action": parts[2],
                        "protocol": parts[3],
                        "src_ip": parts[4],
                        "dst_ip": parts[5],
                        "src_port": parts[6],
                        "dst_port": parts[7],
                    })
                    if len(blocked) >= limit:
                        break
            return json.dumps({"blocked": blocked, "total": len(blocked), "source": "firewall_log"}, indent=2)
        except Exception as e:
            pass

    # Fallback: Security event log
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{ LogName='Security'; Id=5157,5152 }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                EventId = $_.Id
                Message = if ($_.Message.Length -gt 200) {{ $_.Message.Substring(0,200) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)

    results = events if isinstance(events, list) else [events] if events else []
    return json.dumps({"blocked": results, "total": len(results), "source": "security_log", "note": "May need admin for Security log"}, indent=2, default=str)


@mcp.tool()
async def add_rule(name: str, direction: str = "Inbound", action: str = "Allow", protocol: str = "TCP", port: str = ""):
    """
    Create a new firewall rule. Needs admin.

    Args:
        name: Display name for the rule
        direction: 'Inbound' or 'Outbound'
        action: 'Allow' or 'Block'
        protocol: 'TCP', 'UDP', or 'Any'
        port: Port number or range (e.g. '8080', '80,443', '8000-9000')
    """
    port_param = f"-LocalPort {port}" if port else ""

    result = ps(f"""
        New-NetFirewallRule -DisplayName '{name}' -Direction {direction} -Action {action} -Protocol {protocol} {port_param} -ErrorAction Stop
    """)

    verify = ps(f"(Get-NetFirewallRule -DisplayName '{name}' -ErrorAction SilentlyContinue).Enabled")
    return json.dumps({"action": "add_rule", "name": name, "direction": direction, "fw_action": action, "protocol": protocol, "port": port, "success": bool(verify), "note": "Needs admin"}, indent=2)


@mcp.tool()
async def remove_rule(name: str):
    """
    Remove a firewall rule by display name. Needs admin.

    Args:
        name: Display name of the rule to remove
    """
    exists = ps(f"(Get-NetFirewallRule -DisplayName '{name}' -ErrorAction SilentlyContinue).DisplayName")
    if not exists:
        return json.dumps({"error": f"Rule '{name}' not found"})

    ps(f"Remove-NetFirewallRule -DisplayName '{name}' -ErrorAction SilentlyContinue")
    still_exists = ps(f"(Get-NetFirewallRule -DisplayName '{name}' -ErrorAction SilentlyContinue).DisplayName")

    return json.dumps({"action": "remove_rule", "name": name, "success": not bool(still_exists)}, indent=2)


@mcp.tool()
async def enable_disable_rule(name: str, enabled: bool):
    """
    Enable or disable a firewall rule. Needs admin.

    Args:
        name: Display name of the rule
        enabled: True to enable, False to disable
    """
    state = "True" if enabled else "False"
    ps(f"Set-NetFirewallRule -DisplayName '{name}' -Enabled {state} -ErrorAction SilentlyContinue")
    verify = ps(f"(Get-NetFirewallRule -DisplayName '{name}' -ErrorAction SilentlyContinue).Enabled")

    return json.dumps({"action": "enable" if enabled else "disable", "name": name, "enabled": verify}, indent=2)


if __name__ == "__main__":
    mcp.run()
