"""
Environment Manager — MCP Server
====================================
PATH, environment variables, Python/Node/SDK versions.

Read-Only:
  - list_env: All environment variables (User + System)
  - path_entries: PATH with existence check + duplicate detection
  - python_versions: All Python installations
  - node_versions: Node.js installations
  - installed_sdks: .NET, Java, Rust, Go versions

Actions:
  - add_path: Add entry to user PATH
  - set_env: Set user environment variable
"""

import asyncio
import json
import os
import sys
import subprocess
import tempfile
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Environment Manager",
    instructions=(
        "Manage environment variables, PATH, and dev tool versions. "
        "Use 'list_env' for all env vars, 'path_entries' to check PATH health, "
        "'python_versions'/'node_versions'/'installed_sdks' for dev tools. "
        "Actions only modify User-scope variables (no admin needed)."
    ),
)

HOME = os.path.expanduser("~")


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


def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else None
    except: return None


@mcp.tool()
async def list_env(scope: str = "all"):
    """
    List environment variables.

    Args:
        scope: 'user', 'machine', or 'all' (default: all)
    """
    result = {}
    if scope in ("user", "all"):
        user_vars = ps_json("""
            [System.Environment]::GetEnvironmentVariables('User').GetEnumerator() |
            Sort-Object Name | ForEach-Object { @{ Name = $_.Name; Value = $_.Value } }
        """)
        result["user"] = user_vars if isinstance(user_vars, list) else [user_vars] if user_vars else []

    if scope in ("machine", "all"):
        machine_vars = ps_json("""
            [System.Environment]::GetEnvironmentVariables('Machine').GetEnumerator() |
            Sort-Object Name | ForEach-Object { @{ Name = $_.Name; Value = if ($_.Value.Length -gt 200) { $_.Value.Substring(0,200) + '...' } else { $_.Value } } }
        """)
        result["machine"] = machine_vars if isinstance(machine_vars, list) else [machine_vars] if machine_vars else []

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def path_entries():
    """Show all PATH entries with existence check, duplicate detection, and source (User vs Machine)."""
    result = ps_json("""
        $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User') -split ';'
        $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';'
        $all = @()
        $seen = @{}
        foreach ($p in $machinePath) {
            if (-not $p) { continue }
            $dup = $seen.ContainsKey($p.ToLower())
            $seen[$p.ToLower()] = $true
            $all += @{ Path = $p; Source = 'Machine'; Exists = (Test-Path $p); Duplicate = $dup }
        }
        foreach ($p in $userPath) {
            if (-not $p) { continue }
            $dup = $seen.ContainsKey($p.ToLower())
            $seen[$p.ToLower()] = $true
            $all += @{ Path = $p; Source = 'User'; Exists = (Test-Path $p); Duplicate = $dup }
        }
        $all
    """)

    entries = result if isinstance(result, list) else [result] if result else []
    missing = [e for e in entries if isinstance(e, dict) and not e.get("Exists")]
    dupes = [e for e in entries if isinstance(e, dict) and e.get("Duplicate")]

    return json.dumps({
        "entries": entries,
        "total": len(entries),
        "missing": len(missing),
        "duplicates": len(dupes),
        "warnings": [f"Missing: {e['Path']}" for e in missing] + [f"Duplicate: {e['Path']}" for e in dupes],
    }, indent=2, default=str)


@mcp.tool()
async def python_versions():
    """List all Python installations: pyenv, system, Windows Store."""
    versions = []

    # pyenv
    pyenv_dir = os.path.join(HOME, ".pyenv", "pyenv-win", "versions")
    if os.path.exists(pyenv_dir):
        for v in os.listdir(pyenv_dir):
            if os.path.isdir(os.path.join(pyenv_dir, v)):
                versions.append({"version": v, "source": "pyenv", "path": os.path.join(pyenv_dir, v)})

    # Active pyenv version
    active = run_cmd(["pyenv", "version"])

    # System python
    py_path = run_cmd(["where", "python"])
    py_ver = run_cmd(["python", "--version"])

    # pip
    pip_ver = run_cmd(["pip", "--version"])

    # uv
    uv_ver = run_cmd(["uv", "--version"])

    return json.dumps({
        "pyenv_versions": versions,
        "pyenv_active": active,
        "system_python": py_ver,
        "system_path": py_path,
        "pip": pip_ver,
        "uv": uv_ver,
    }, indent=2, default=str)


@mcp.tool()
async def node_versions():
    """List Node.js installations: nvm, system, npm, bun."""
    result = {}
    result["node"] = run_cmd(["node", "--version"])
    result["npm"] = run_cmd(["npm", "--version"])
    result["bun"] = run_cmd(["bun", "--version"])
    result["pnpm"] = run_cmd(["pnpm", "--version"])
    result["yarn"] = run_cmd(["yarn", "--version"])

    # nvm
    nvm_dir = os.path.join(os.environ.get("APPDATA", ""), "nvm")
    if os.path.exists(nvm_dir):
        nvm_versions = [d for d in os.listdir(nvm_dir) if os.path.isdir(os.path.join(nvm_dir, d)) and d.startswith("v")]
        result["nvm_versions"] = nvm_versions
    result["node_path"] = run_cmd(["where", "node"])

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def installed_sdks():
    """List installed development SDKs and runtimes: .NET, Java, Rust, Go, etc."""
    sdks = {}
    checks = {
        "dotnet": ["dotnet", "--version"],
        "dotnet_sdks": ["dotnet", "--list-sdks"],
        "java": ["java", "--version"],
        "rustc": ["rustc", "--version"],
        "cargo": ["cargo", "--version"],
        "go": ["go", "version"],
        "git": ["git", "--version"],
        "cmake": ["cmake", "--version"],
        "gcc": ["gcc", "--version"],
    }
    for name, cmd in checks.items():
        out = run_cmd(cmd)
        if out:
            sdks[name] = out.splitlines()[0] if out else None

    return json.dumps({"sdks": sdks}, indent=2, default=str)


@mcp.tool()
async def add_path(entry: str):
    """
    Add an entry to the User PATH. Checks for duplicates.

    Args:
        entry: Directory path to add to PATH
    """
    if not os.path.exists(entry):
        return json.dumps({"error": f"Path does not exist: {entry}"})

    current = ps("[System.Environment]::GetEnvironmentVariable('Path', 'User')")
    if current and entry.lower() in current.lower():
        return json.dumps({"error": f"Already in PATH: {entry}"})

    ps(f"$old = [System.Environment]::GetEnvironmentVariable('Path', 'User')\n[System.Environment]::SetEnvironmentVariable('Path', \"$old;{entry}\", 'User')")

    new_path = ps("[System.Environment]::GetEnvironmentVariable('Path', 'User')")
    success = new_path and entry.lower() in new_path.lower()

    return json.dumps({"action": "add_path", "entry": entry, "success": success, "note": "Restart apps to pick up PATH change"}, indent=2)


@mcp.tool()
async def set_env(name: str, value: str):
    """
    Set a User-scope environment variable.

    Args:
        name: Variable name
        value: Variable value
    """
    BLOCKED = ["PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE"]
    if name.upper() in BLOCKED:
        return json.dumps({"error": f"Cannot modify protected variable: {name}"})

    ps(f"[System.Environment]::SetEnvironmentVariable('{name}', '{value}', 'User')")
    verify = ps(f"[System.Environment]::GetEnvironmentVariable('{name}', 'User')")

    return json.dumps({"action": "set_env", "name": name, "value": value, "verified": verify == value}, indent=2)


if __name__ == "__main__":
    mcp.run()
