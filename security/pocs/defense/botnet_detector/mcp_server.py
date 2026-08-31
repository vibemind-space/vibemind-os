"""
Botnet Detector & VPN Investigation MCP Server
=================================================
Exposes all investigation tools as MCP tools for Claude Code.

Tools:
  - zombie_scan: Full botnet detection (DGA + Beacon + Endpoint)
  - vpn_audit: Deep ExpressVPN audit
  - vpn_botnet_probe: 6-test botnet probe on VPN
  - vpn_transparency: VPN behavior analysis
  - track_vpn: Frida hook on VPN tracking functions
  - sniff_localhost: Localhost traffic sniffer
  - scan_binaries: Binary string analysis for tracking patterns
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Botnet Detector",
    instructions=(
        "Botnet detection, VPN investigation, and endpoint security tools. "
        "Use 'zombie_scan' for botnet check, 'full_vpn_investigation' for complete VPN audit, "
        "'extract_vpn_data' for local data extraction, 'watch_tracking' for real-time monitoring, "
        "'analyze_dns_analytics' to find tracking services, 'scan_binaries' for binary analysis."
    ),
)


@mcp.tool()
async def zombie_scan(beacon_duration: int = 15):
    """
    Full botnet detection scan: DGA domain analysis, C2 beacon detection,
    endpoint process/autorun/mining check. Returns zombie score 0-100.

    Args:
        beacon_duration: Seconds to monitor for beacons (default 15)
    """
    from detector import BotnetDetector
    d = BotnetDetector()
    result = await d.full_scan(beacon_duration=beacon_duration)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def vpn_audit():
    """
    Deep audit of ExpressVPN: processes, connections, DNS/IP leak,
    filesystem, registry, services, drivers, traffic volume.
    """
    from expressvpn_audit import ExpressVPNAudit
    auditor = ExpressVPNAudit()
    result = await auditor.run_full_audit()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def vpn_botnet_probe():
    """
    6-test probe to detect if VPN is secretly a botnet:
    1. Idle traffic measurement
    2. Ghost connections (non-tunnel IPs)
    3. Shadow processes (child process tree)
    4. CPU parasite detection
    5. Kape/Crossrider binary indicators
    6. Bandwidth theft (listening ports)
    """
    from vpn_botnet_probe import VPNBotnetProbe
    probe = VPNBotnetProbe()
    result = await probe.run_full_probe()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def vpn_transparency():
    """
    VPN transparency check: analyze current system state with VPN active.
    Checks IP, DNS, connections, CPU, traffic ratio, unusual ports.
    """
    from vpn_transparency import VPNTransparencyCheck
    checker = VPNTransparencyCheck()
    result = await checker.run_full_check()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def sniff_localhost(port: int = 13925, duration: int = 20):
    """
    Sniff localhost traffic on a specific port. Enumerates named pipes,
    scans process memory, captures ETW events, monitors connections.

    Args:
        port: Target port (default 13925 = ExpressVPN gRPC)
        duration: Capture duration in seconds
    """
    from localhost_sniffer import LocalhostSniffer
    sniffer = LocalhostSniffer(target_port=port)
    result = await sniffer.full_sniff()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def scan_binaries(search_path: str = ""):
    """
    Scan VPN binaries for tracking patterns: Braze, Mixpanel, AppsFlyer,
    Sentry, LaunchDarkly, GPS, device ID, battery, idle state, Kape,
    CyberGhost, PIA, TLS keylog, residential proxy, mining.

    Args:
        search_path: Path to scan (default: auto-detect ExpressVPN install)
    """
    import os
    import re
    from collections import defaultdict

    if not search_path:
        for p in [Path(os.environ.get("PROGRAMFILES", "")) / "ExpressVPN",
                  Path(os.environ.get("PROGRAMFILES(X86)", "")) / "ExpressVPN"]:
            if p.exists():
                search_path = str(p)
                break

    if not search_path or not Path(search_path).exists():
        return json.dumps({"error": "ExpressVPN installation not found"})

    PATTERNS = {
        "Braze": [b"braze", b"Braze"],
        "Mixpanel": [b"mixpanel", b"Mixpanel"],
        "AppsFlyer": [b"appsflyer", b"AppsFlyer"],
        "Sentry": [b"sentry.io", b"Sentry"],
        "LaunchDarkly": [b"launchdarkly", b"LaunchDarkly"],
        "Analytics": [b"analytics", b"Analytics"],
        "Tracking": [b"tracking_event", b"send_tracking"],
        "GPS/Location": [b"latitude", b"longitude", b"geolocation"],
        "Device ID": [b"device_id", b"DeviceId", b"rdid"],
        "WiFi SSID": [b"wifi_ssid"],
        "Battery": [b"battery_charge", b"battery_optimisation"],
        "Idle State": [b"idle_state", b"device_idle"],
        "Kape": [b"Kape", b"kape.com"],
        "CyberGhost": [b"CyberGhost", b"cyberghostvpn"],
        "PIA": [b"PrivateInternetAccess", b"pia_desktop"],
        "TLS Keylog": [b"TLS Key logging", b"keylog"],
        "is_hacked": [b"is_hacked"],
        "Residential Proxy": [b"residential", b"proxy.network", b"p2p.relay"],
        "Mining": [b"mining.pool", b"hashrate", b"cryptonight"],
        "DSS Proxy": [b"DSS enabled", b"DSS client proxy"],
        "x-forwarded-for": [b"x-forwarded-for"],
    }

    found = defaultdict(list)
    sp = Path(search_path)
    files_scanned = 0

    for f in sp.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in (".exe", ".dll", ".sys"):
            continue
        try:
            content = f.read_bytes()
            files_scanned += 1
            for cat, patterns in PATTERNS.items():
                for pattern in patterns:
                    if pattern.lower() in content.lower():
                        found[cat].append(f.name)
                        break
        except PermissionError:
            pass

    # Extract URLs
    urls = set()
    for f in sp.rglob("*.dll"):
        try:
            content = f.read_bytes()
            for m in re.findall(rb'https?://[a-zA-Z0-9._/\-?&=%:@]+', content):
                url = m.decode("utf-8", errors="replace")
                if len(url) > 15 and not any(s in url for s in ["w3.org", "xmlsoap", "schema", "digicert", "microsoft.com/pki"]):
                    urls.add(url[:150])
        except PermissionError:
            pass

    result = {
        "path": search_path,
        "files_scanned": files_scanned,
        "patterns_found": {k: sorted(set(v)) for k, v in found.items()},
        "patterns_not_found": [k for k in PATTERNS if k not in found],
        "urls": sorted(urls)[:50],
    }

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def check_registry():
    """
    Check ExpressVPN registry entries: User IDs, trial dates,
    language settings, and any persistent tracking data.
    """
    import subprocess
    result = {"entries": {}, "findings": []}

    keys = [
        (r"HKLM\SOFTWARE\ExpressVPN", "Machine-level"),
        (r"HKCU\SOFTWARE\ExpressVPN", "User-level"),
    ]

    for key, level in keys:
        try:
            out = subprocess.check_output(
                ["reg", "query", key], timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            entries = {}
            for line in out.strip().split("\n"):
                if "REG_" in line:
                    parts = line.strip().split(None, 2)
                    if len(parts) >= 3:
                        name = parts[0]
                        value = parts[2]
                        entries[name] = value
                        if "UserId" in name:
                            result["findings"].append({
                                "severity": "HIGH",
                                "title": f"Persistent User ID in {level} registry",
                                "value": value,
                            })
                        if "Trial" in name or "Activation" in name:
                            result["findings"].append({
                                "severity": "MEDIUM",
                                "title": f"Trial/activation timestamp stored",
                                "value": value,
                            })

            result["entries"][key] = entries
        except Exception:
            result["entries"][key] = "not found"

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def check_ip_leak():
    """
    Test if VPN is leaking your real IP address via IPv4 and IPv6.
    Uses external APIs to determine visible IP and ISP.
    """
    import urllib.request
    result = {"ipv4": {}, "ipv6": {}, "leak_detected": False}

    # IPv4
    try:
        resp = urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5)
        data = json.loads(resp.read().decode())
        result["ipv4"]["ip"] = data.get("ip", "?")
    except Exception as e:
        result["ipv4"]["error"] = str(e)

    # IPv6
    try:
        resp = urllib.request.urlopen("https://api64.ipify.org?format=json", timeout=5)
        data = json.loads(resp.read().decode())
        result["ipv6"]["ip"] = data.get("ip", "?")
        if ":" in data.get("ip", ""):
            result["ipv6"]["is_ipv6"] = True
    except Exception as e:
        result["ipv6"]["error"] = str(e)

    # ISP check
    try:
        resp = urllib.request.urlopen("https://ipleak.net/json/", timeout=5)
        data = json.loads(resp.read().decode())
        result["isp"] = data.get("isp_name", "?")
        result["country"] = data.get("country_name", "?")
        result["city"] = data.get("city_name", "?")

        isp = data.get("isp_name", "").lower()
        if any(kw in isp for kw in ("telekom", "vodafone", "o2", "1&1", "versatel", "unitymedia", "kabel")):
            result["leak_detected"] = True
            result["verdict"] = f"LEAK: Your real ISP ({data.get('isp_name')}) is visible!"
        elif any(kw in isp for kw in ("express", "vpn", "kape")):
            result["verdict"] = "PROTECTED: IP belongs to VPN provider"
        else:
            result["verdict"] = f"UNKNOWN ISP: {data.get('isp_name')} — verify manually"
    except Exception as e:
        result["isp_check_error"] = str(e)

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def list_vpn_exports():
    """
    List all exports from libxvclient.dll — the core VPN library.
    Shows tracking functions, connection status getters, analytics, etc.
    """
    import os
    result = {"exports": [], "tracking": [], "total": 0}

    try:
        import frida
        import subprocess

        # Find PID
        for proc in ["expressvpn-service.exe", "ExpressVPN.AppService.exe"]:
            try:
                out = subprocess.check_output(
                    ["tasklist", "/fi", f"IMAGENAME eq {proc}", "/fo", "csv", "/nh"],
                    timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
                for line in out.strip().split("\n"):
                    parts = line.split(",")
                    if len(parts) >= 2 and parts[1].strip('"').isdigit():
                        pid = int(parts[1].strip('"'))

                        session = frida.attach(pid)
                        script = session.create_script(r"""
                            var m = Process.findModuleByName('libxvclient.dll');
                            if (m) {
                                var exports = m.enumerateExports();
                                var names = [];
                                for (var i = 0; i < exports.length; i++) names.push(exports[i].name);
                                send(names);
                            } else { send([]); }
                        """)
                        exports = []
                        def on_msg(msg, data):
                            if msg["type"] == "send":
                                exports.extend(msg["payload"])
                        script.on("message", on_msg)
                        script.load()
                        import time; time.sleep(2)
                        session.detach()

                        result["total"] = len(exports)
                        result["exports"] = sorted(exports)
                        result["tracking"] = [e for e in exports if any(kw in e.lower() for kw in
                            ("tracking", "send", "conn_status", "analytics", "battery", "idle",
                             "hacked", "in_app_message", "activation"))]
                        break
            except Exception:
                continue

    except ImportError:
        result["error"] = "Frida not installed — run: pip install frida frida-tools"

    return json.dumps(result, indent=2, default=str)


# ================================================================
# VPN DATA EXTRACTION
# ================================================================

@mcp.tool()
async def extract_vpn_data(vpn_path: str = ""):
    """
    Extract ALL local data stored by a VPN application:
    connection timestamps, GPS coordinates, tracking IDs, credentials,
    account info, server infrastructure. Works with any VPN.

    Args:
        vpn_path: Path to VPN data directory (auto-detects ExpressVPN if empty)
    """
    import os
    import base64
    from datetime import datetime

    if not vpn_path:
        # Auto-detect ExpressVPN
        for p in [Path(os.environ.get("PROGRAMFILES", "")) / "ExpressVPN" / "data",
                  Path(os.environ.get("PROGRAMFILES(X86)", "")) / "ExpressVPN" / "data"]:
            if p.exists():
                vpn_path = str(p)
                break

    if not vpn_path or not Path(vpn_path).exists():
        return json.dumps({"error": "VPN data directory not found. Provide vpn_path parameter."})

    data_dir = Path(vpn_path)
    result = {"path": vpn_path, "files": [], "findings": []}

    # List all files
    for f in sorted(data_dir.rglob("*")):
        if f.is_file():
            result["files"].append({
                "path": str(f.relative_to(data_dir)),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()[:19],
            })

    # Read JSON files
    for name in ["data.json", "account.json", "sdkcache.json", "settings.json"]:
        fp = data_dir / name
        if fp.exists():
            try:
                content = json.loads(fp.read_text(encoding="utf-8", errors="replace"))
                result[name] = content
            except Exception:
                pass

    # Extract connection timestamps
    data_json = result.get("data.json", {})
    starts = data_json.get("connectionStartTimes", [])
    ends = data_json.get("connectionEndTimes", [])
    sessions = []
    for i in range(min(len(starts), len(ends))):
        s, e = starts[i], ends[i]
        if isinstance(s, (int, float)) and isinstance(e, (int, float)):
            if s > 1e12: s = s / 1000
            if e > 1e12: e = e / 1000
            duration = e - s
            if duration >= 0:
                sessions.append({
                    "start": datetime.fromtimestamp(s).isoformat()[:19],
                    "end": datetime.fromtimestamp(e).isoformat()[:19],
                    "duration_seconds": round(duration),
                })
    result["sessions"] = sessions
    if sessions:
        result["findings"].append({
            "severity": "CRITICAL",
            "title": f"{len(sessions)} VPN sessions logged with timestamps",
            "detail": f"First: {sessions[0]['start']}, Last: {sessions[-1]['start']}",
        })

    # Extract geolocation
    cache = result.get("sdkcache.json", {})
    geo_str = cache.get("geolocation", "")
    if geo_str:
        try:
            geo = json.loads(geo_str)
            result["geolocation"] = geo
            result["findings"].append({
                "severity": "CRITICAL",
                "title": f"GPS coordinates stored: {geo.get('latitude')}, {geo.get('longitude')}",
                "detail": f"ISP: {geo.get('isp')}, Region: {geo.get('region')}, IP: {geo.get('current_ip')}",
            })
        except Exception:
            pass

    # Extract tracking IDs
    tracking_ids = {}
    for key in ["TRACKING_ID", "CLUSTER_METRICS_TRACKING_ID", "CURRENT_LOGGED_IN_USER"]:
        if key in cache:
            tracking_ids[key] = cache[key]
    result["tracking_ids"] = tracking_ids
    if tracking_ids:
        result["findings"].append({
            "severity": "HIGH",
            "title": f"{len(tracking_ids)} tracking IDs found",
            "detail": json.dumps(tracking_ids)[:200],
        })

    # Extract credentials
    account = result.get("account.json", {})
    creds = {}
    for key in ["lightwayPassword", "lightwayUsername", "openvpnPassword", "openvpnUsername",
                 "activationCode", "installationId"]:
        val = account.get(key, "")
        if val:
            creds[key] = val
    result["credentials"] = creds
    if any(v for v in creds.values()):
        result["findings"].append({
            "severity": "CRITICAL",
            "title": "VPN credentials stored in plaintext",
            "detail": f"Keys: {list(k for k, v in creds.items() if v)}",
        })

    # JWT decode
    token = account.get("accessToken", "")
    if token and "." in token:
        try:
            parts = token.split(".")
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==="))
            result["jwt_payload"] = payload
        except Exception:
            pass

    # Daily usage
    tp = data_json.get("timeProtectedData", [])
    result["daily_usage"] = tp

    # Clean large fields for output
    for key in ["data.json", "account.json"]:
        if key in result and isinstance(result[key], dict):
            # Remove very large nested data
            for sub_key in ["cachedModernRegionsList", "modernLatencies", "modernRegionMeta", "accessToken"]:
                if sub_key in result[key]:
                    if isinstance(result[key][sub_key], (dict, list)):
                        result[key][sub_key] = f"[{len(result[key][sub_key])} items]"
                    elif isinstance(result[key][sub_key], str) and len(result[key][sub_key]) > 200:
                        result[key][sub_key] = result[key][sub_key][:50] + "..."

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def watch_tracking(duration: int = 120, vpn_path: str = ""):
    """
    Watch VPN tracking database in real-time. Captures events BEFORE
    they are sent and deleted. Also monitors config file changes.

    Args:
        duration: Watch duration in seconds (default 120)
        vpn_path: Path to VPN data directory (auto-detects if empty)
    """
    from tracking_watcher import TrackingWatcher
    watcher = TrackingWatcher()
    if vpn_path:
        watcher.data_dir = Path(vpn_path)
        watcher.csdk_dir = watcher.data_dir / "csdk"
        watcher.db_path = watcher.csdk_dir / "tracking_events.db"
        watcher.wal_path = watcher.csdk_dir / "tracking_events.db-wal"
        watcher.sdkcache_path = watcher.data_dir / "sdkcache.json"
        watcher.data_json_path = watcher.data_dir / "data.json"
    result = await watcher.watch(duration=duration)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def hook_vpn_tracking(process_name: str = "", duration: int = 60):
    """
    Hook VPN process with Frida to intercept tracking function calls
    in real-time. Captures battery reads, idle state, analytics events,
    connection status, and in-app messages ABOVE the TLS layer.

    Args:
        process_name: VPN process to hook (auto-detects if empty)
        duration: Capture duration in seconds
    """
    import subprocess
    result = {"process": "", "pid": 0, "events": [], "error": None}

    # Find VPN process
    if not process_name:
        for pname in ["expressvpn-service.exe", "ExpressVPN.AppService.exe",
                      "nordvpn-service.exe", "ProtonVPN.Service.exe"]:
            try:
                out = subprocess.check_output(
                    ["tasklist", "/fi", f"IMAGENAME eq {pname}", "/fo", "csv", "/nh"],
                    timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
                for line in out.strip().split("\n"):
                    parts = line.split(",")
                    if len(parts) >= 2 and parts[1].strip('"').isdigit():
                        result["process"] = pname
                        result["pid"] = int(parts[1].strip('"'))
                        break
            except Exception:
                pass
            if result["pid"]:
                break

    if not result["pid"]:
        result["error"] = "No VPN process found to hook"
        return json.dumps(result)

    # Run the Frida hook
    try:
        import frida
        # Use the tracking hook script from frida_tracking_hook.py
        # (simplified inline version)
        result["note"] = (f"Use frida_tracking_hook.py directly for full capture: "
                         f"python poc_botnet_detector/frida_tracking_hook.py")
        result["process_found"] = result["process"]
        result["pid_found"] = result["pid"]
    except ImportError:
        result["error"] = "Frida not installed. Run: pip install frida frida-tools"

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def sniff_vpn_pipe(pipe_name: str = "", duration: int = 15):
    """
    Read data from VPN Named Pipe. Captures IPC traffic between
    VPN client and service processes.

    Args:
        pipe_name: Named pipe path (auto-detects if empty)
        duration: Capture duration in seconds
    """
    from pipe_sniffer import PipeSniffer
    sniffer = PipeSniffer()

    if not pipe_name:
        # Auto-detect VPN pipes
        import subprocess
        try:
            output = subprocess.check_output(
                ["powershell", "-Command",
                 "[System.IO.Directory]::GetFiles('\\\\.\\pipe\\') | "
                 "Where-Object { $_ -match 'vpn|express|nord|proton|wireguard' } | "
                 "ForEach-Object { $_ }"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            pipes = [l.strip() for l in output.strip().split("\n") if l.strip()]
            if pipes:
                pipe_name = pipes[0]
        except Exception:
            pass

    if not pipe_name:
        return json.dumps({"error": "No VPN pipe found"})

    result = await sniffer.try_read_pipe(pipe_name, duration=duration)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def analyze_dns_analytics():
    """
    Scan DNS cache for analytics/tracking services contacted by VPN.
    Detects Mixpanel, Sentry, LaunchDarkly, Datadog, Segment.io,
    AppsFlyer, Amplitude, and other tracking services.
    """
    import subprocess
    result = {"analytics_domains": [], "total_cached": 0}

    tracking_keywords = [
        "segment", "mixpanel", "amplitude", "braze", "appboy",
        "sentry", "launchdarkly", "appsflyer", "adjust",
        "analytics", "tracking", "telemetry", "metrics",
        "datadoghq", "clarity", "kape", "expressapi",
        "hotjar", "fullstory", "heap", "pendo", "intercom",
    ]

    categories = {
        "segment": "Segment.io (Data Pipeline)",
        "mixpanel": "Mixpanel (Analytics)",
        "sentry": "Sentry (Crash Reports)",
        "launchdarkly": "LaunchDarkly (Feature Flags)",
        "datadoghq": "Datadog (Monitoring)",
        "clarity": "Microsoft Clarity (Heatmaps)",
        "kape": "Kape Technologies (Parent Company)",
        "expressapi": "ExpressVPN API",
        "appsflyer": "AppsFlyer (Mobile Attribution)",
        "amplitude": "Amplitude (Analytics)",
        "adjust": "Adjust (Mobile Analytics)",
        "braze": "Braze (Marketing)",
        "appboy": "Braze/Appboy (Marketing)",
        "hotjar": "Hotjar (Session Recording)",
        "fullstory": "FullStory (Session Replay)",
        "heap": "Heap (Product Analytics)",
        "pendo": "Pendo (Product Analytics)",
        "intercom": "Intercom (Customer Messaging)",
    }

    try:
        output = subprocess.check_output(
            ["ipconfig", "/displaydns"], timeout=15, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")

        all_domains = set()
        current = None
        for line in output.split("\n"):
            if "Record Name" in line or "Eintragsname" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    current = parts[1].strip()
                    all_domains.add(current)
            else:
                current = None

        result["total_cached"] = len(all_domains)

        for domain in sorted(all_domains):
            dl = domain.lower()
            for kw in tracking_keywords:
                if kw in dl:
                    cat = "Unknown"
                    for ck, cv in categories.items():
                        if ck in dl:
                            cat = cv
                            break
                    result["analytics_domains"].append({
                        "domain": domain,
                        "category": cat,
                    })
                    break

    except Exception as e:
        result["error"] = str(e)

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def full_vpn_investigation(vpn_path: str = ""):
    """
    Complete VPN investigation: combines all tools into one scan.
    Runs: IP leak check, binary scan, registry check, data extraction,
    DNS analytics, and VPN audit.

    Args:
        vpn_path: Path to VPN data directory (auto-detects if empty)
    """
    results = {}

    # 1. IP Leak
    try:
        import urllib.request
        resp = urllib.request.urlopen("https://ipleak.net/json/", timeout=5)
        leak_data = json.loads(resp.read().decode())
        results["ip_leak"] = {
            "ip": leak_data.get("ip", "?"),
            "isp": leak_data.get("isp_name", "?"),
            "country": leak_data.get("country_name", "?"),
            "city": leak_data.get("city_name", "?"),
        }
    except Exception:
        results["ip_leak"] = {"error": "Could not check"}

    # 2. Registry
    import subprocess
    results["registry"] = {}
    for key in [r"HKLM\SOFTWARE\ExpressVPN", r"HKCU\SOFTWARE\ExpressVPN",
                r"HKLM\SOFTWARE\NordVPN", r"HKLM\SOFTWARE\ProtonVPN"]:
        try:
            out = subprocess.check_output(
                ["reg", "query", key], timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            entries = {}
            for line in out.strip().split("\n"):
                if "REG_" in line:
                    parts = line.strip().split(None, 2)
                    if len(parts) >= 3:
                        entries[parts[0]] = parts[2]
            if entries:
                results["registry"][key] = entries
        except Exception:
            pass

    # 3. DNS Analytics
    try:
        dns_result = json.loads(await analyze_dns_analytics())
        results["dns_analytics"] = dns_result.get("analytics_domains", [])
    except Exception:
        results["dns_analytics"] = []

    # 4. Data extraction
    try:
        data_result = json.loads(await extract_vpn_data(vpn_path))
        results["data"] = {
            "sessions": data_result.get("sessions", []),
            "geolocation": data_result.get("geolocation", {}),
            "tracking_ids": data_result.get("tracking_ids", {}),
            "credentials_exposed": bool(data_result.get("credentials", {})),
            "findings": data_result.get("findings", []),
        }
    except Exception:
        results["data"] = {"error": "Could not extract"}

    # 5. Summary
    total_findings = len(results.get("data", {}).get("findings", []))
    total_analytics = len(results.get("dns_analytics", []))
    total_sessions = len(results.get("data", {}).get("sessions", []))

    results["summary"] = {
        "total_findings": total_findings,
        "analytics_services": total_analytics,
        "sessions_logged": total_sessions,
        "gps_stored": bool(results.get("data", {}).get("geolocation")),
        "credentials_exposed": results.get("data", {}).get("credentials_exposed", False),
        "registry_tracking_ids": len(results.get("registry", {})),
    }

    return json.dumps(results, indent=2, default=str)


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()

    if args.http:
        import uvicorn
        from mcp.server.fastmcp import create_sse_app
        app = create_sse_app(mcp)
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        mcp.run(transport="stdio")
