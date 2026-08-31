# 🛡️ VibeMind Security Lab

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

Proof-of-concept modules for AI-augmented defense and adversarial testing — host/network
monitoring, forensics, botnet detection, and web-recon PoCs. Built for research and
education.

> **Disclaimer:** These are proof-of-concept tools for authorized security research only.
> Use responsibly and only on systems you own or have permission to test. See
> [SECURITY.md](SECURITY.md).

## Layout

```
security/
  llm_client.py            # shared LLM access used by the PoCs
  llm_config.yml           # LLM routing config (gitignored)
  run_tests.py             # self-check suite for the defense/infra PoCs
  requirements.txt
  pocs/
    defense/               # host & network monitoring, hardening, forensics
      vuln_scanner/        # installed-software / misconfig inventory (Windows registry)
      network_monitor/     # WiFi/ARP/DNS/TLS/ports + honeypot (MCP server)
      forensics/           # timeline reconstruction from Windows artifacts
      canary/              # honeypot canary-file deployment + watcher
      botnet_detector/     # DGA / C2-beacon / zombie behavioral analysis
      firewall/            # Windows Firewall management (MCP server)
      event_log/           # Windows Event Log analysis (MCP server)
      endpoint_hardening/  # Defender / BitLocker / secrets audit (MCP server)
      alerter/             # multi-channel alerts (Telegram/Slack/Email)
      pc_monitor/          # PC health / admin helper (MCP server)
      storage_manager/     # disk / storage management (MCP server)
      os_shield/           # real-time OS-level threat detection (blue team)
      log_analyzer/        # Windows security-log anomaly detection
      security_scanner/    # broader vuln / misconfiguration scanning
    offense/               # adversarial / red-team PoCs
      site_verifier/       # web recon: SSL, headers, CMS/XSS checks, reporting
      injection_chain/     # multi-step prompt-injection analysis (AutoGen)
      captcha_eval/        # browser-agent robustness eval on OWN local site
      red_blue/            # automated red/blue-team exercise framework (uses os_shield)
    infra/                 # shared lab plumbing
      grpc_host/           # distributed AutoGen agents over gRPC
      keycloak/            # OAuth2 device verification / RBAC
```

Generic (non-security) AutoGen/MCP tool-integration demos that used to live here have
moved to `../examples/mcp-agents/`.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Each PoC is self-contained; run it from its own directory. Examples:

```bash
# Vulnerability / software inventory
python pocs/defense/vuln_scanner/main.py

# Forensics timeline
python pocs/defense/forensics/main.py

# Botnet / DGA detector
python pocs/defense/botnet_detector/detector.py

# Web recon (own/authorized targets only)
python pocs/offense/site_verifier/run_audit.py
```

The MCP-server PoCs (`network_monitor`, `firewall`, `event_log`, `endpoint_hardening`,
`botnet_detector`, `site_verifier`) expose their tools over stdio and are wired into the
OpenFang agent stack via `openfang/openfang.vibemind.toml.template`. If you move or rename
these dirs, update those paths in lockstep.

## Self-check

```bash
python run_tests.py
```

Runs importable, host-local checks for the defense + infra PoCs (no external targets).
Some checks need Windows and/or admin rights; `keycloak` needs a local Keycloak container.

## License

MIT — Felix Baumann ([@Flissel](https://github.com/Flissel))
