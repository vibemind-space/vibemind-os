"""PC RAM scan — top processes with friendly names, zombie hints, pagefile check.

Read-only. Mirrors the memory_inspect / zombie_detect / pagefile_inspect MCP tools.
"""
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timedelta


def fmt(b):
    if b > 1024**3:
        return f"{b / 1024**3:.2f} GB"
    if b > 1024**2:
        return f"{b / 1024**2:.0f} MB"
    return f"{b / 1024:.0f} KB"


INTERPRETERS = {"python.exe", "pythonw.exe", "node.exe", "ruby.exe", "java.exe", "dotnet.exe"}


def friendly(name, cmdline):
    if not name:
        return "?"
    base = name.lower()
    if base not in INTERPRETERS:
        return name
    cmd = (cmdline or "").strip()
    if not cmd:
        return name
    try:
        tokens = shlex.split(cmd, posix=False)
    except Exception:  # noqa: BLE001
        tokens = cmd.split()
    if len(tokens) < 2:
        return name
    args = tokens[1:]
    label = None
    port = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-c", "-X"):
            i += 2
            continue
        if a == "-m" and i + 1 < len(args):
            label = args[i + 1].strip('"')
            i += 2
            continue
        if a in ("--port", "-p", "--listen-port") and i + 1 < len(args):
            try:
                port = int(args[i + 1].strip('"'))
            except ValueError:
                pass
            i += 2
            continue
        if label is None and not a.startswith("-"):
            label = os.path.basename(a.strip('"')) or a
        i += 1
    short = label or name
    if port is not None:
        short = f"{short}:{port}"
    interp = base.replace(".exe", "")
    return f"{interp}:{short}"


def list_processes():
    cmd = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId, Name, CommandLine, WorkingSetSize, PrivatePageCount, CreationDate | "
        "ConvertTo-Json -Compress -Depth 3"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {e}")
        return []
    if res.returncode != 0 or not res.stdout.strip():
        return []
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    procs = []
    for p in data:
        try:
            procs.append({
                "pid": int(p.get("ProcessId") or 0),
                "name": p.get("Name") or "",
                "cmdline": p.get("CommandLine") or "",
                "ws": int(p.get("WorkingSetSize") or 0),
                "priv": int(p.get("PrivatePageCount") or 0),
                "started": p.get("CreationDate"),
            })
        except (TypeError, ValueError):
            continue
    return procs


def parse_started(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    if isinstance(s, dict):
        s = s.get("DateTime") or s.get("value")
    if not isinstance(s, str):
        return None
    for fmt_ in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%d.%m.%Y %H:%M:%S",
        "%Y%m%d%H%M%S.%f",
    ):
        try:
            return datetime.strptime(s.split("+")[0].strip(), fmt_)
        except ValueError:
            continue
    return None


def memory_totals():
    cmd = (
        "$m = Get-CimInstance Win32_OperatingSystem; "
        "[PSCustomObject]@{ TotalKB = $m.TotalVisibleMemorySize; FreeKB = $m.FreePhysicalMemory } "
        "| ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        d = json.loads(res.stdout)
        return int(d["TotalKB"]) * 1024, int(d["FreeKB"]) * 1024
    except Exception:  # noqa: BLE001
        return 0, 0


def pagefile_info():
    cmd = (
        "Get-CimInstance Win32_PageFileUsage | "
        "Select-Object Name, CurrentUsage, PeakUsage, AllocatedBaseSize | "
        "ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        d = json.loads(res.stdout)
        if isinstance(d, dict):
            d = [d]
        return d
    except Exception:  # noqa: BLE001
        return []


def main():
    print()
    print("=" * 64)
    print("  RAM SCAN  (read-only)")
    print("=" * 64)

    total, free = memory_totals()
    used = total - free
    pct = (used / total * 100) if total else 0
    print()
    print(f"  RAM total: {fmt(total):>10}")
    print(f"  RAM used:  {fmt(used):>10}  ({pct:.1f}%)")
    print(f"  RAM free:  {fmt(free):>10}")

    procs = list_processes()
    procs.sort(key=lambda p: p["priv"], reverse=True)

    print()
    print("  TOP 15 nach Private Memory (Pagefile+RAM committed):")
    print(f"  {'PID':>6}  {'Private':>10}  {'WorkSet':>10}  Friendly Name")
    print("  " + "-" * 62)
    for p in procs[:15]:
        print(f"  {p['pid']:>6}  {fmt(p['priv']):>10}  {fmt(p['ws']):>10}  {friendly(p['name'], p['cmdline'])}")

    # Zombie hint
    cutoff = datetime.now() - timedelta(minutes=30)
    wanted = {"python.exe", "node.exe"}
    zombies = []
    for p in procs:
        if p["name"].lower() not in wanted:
            continue
        if p["ws"] >= 5 * 1024 * 1024:
            continue
        st = parse_started(p["started"])
        if st is None or st > cutoff:
            continue
        zombies.append((p, st))

    print()
    if zombies:
        print(f"  ZOMBIE-VERDACHT ({len(zombies)} Treffer, Working Set < 5 MB, > 30 min alt):")
        print("  Diese Prozesse sind komplett ausgelagert. Pruefe ob noch gebraucht!")
        for p, st in zombies[:10]:
            age = datetime.now() - st
            mins = int(age.total_seconds() / 60)
            print(f"    PID {p['pid']:>6}  age={mins}min  priv={fmt(p['priv']):>8}  {friendly(p['name'], p['cmdline'])}")
        print("  Stoppen: Stop-Process -Id <PID> -Force   (vorher: pruefen ob aktiv!)")
    else:
        print("  Keine offensichtlichen Zombie-Prozesse gefunden.")

    print()
    pfs = pagefile_info()
    if pfs:
        ram_gb = total / 1024**3
        alloc_gb = sum(int(p.get("AllocatedBaseSize") or 0) for p in pfs) / 1024
        cur_gb = sum(int(p.get("CurrentUsage") or 0) for p in pfs) / 1024
        rec_max = max(8.0, ram_gb * 1.5)
        print("  PAGEFILE:")
        for p in pfs:
            print(f"    {p.get('Name', '?'):<25} allocated={int(p.get('AllocatedBaseSize') or 0)/1024:.0f} GB  "
                  f"current={int(p.get('CurrentUsage') or 0)/1024:.1f} GB  peak={int(p.get('PeakUsage') or 0)/1024:.1f} GB")
        if alloc_gb > ram_gb * 2.5:
            print(f"  EMPFEHLUNG: Pagefile {alloc_gb:.0f} GB ist viel zu gross fuer {ram_gb:.0f} GB RAM.")
            print(f"     Auf ~{rec_max:.0f} GB begrenzen (sysdm.cpl -> Erweitert -> Virt. Speicher).")
        else:
            print(f"  Pagefile-Groesse OK (Richtwert ~{rec_max:.0f} GB).")

    print()
    print("  Tipps:")
    print("    - 'Private' = committed memory (RAM + Pagefile). 'WorkSet' = aktuell im RAM.")
    print("    - Niedriger WorkSet bei hoher Private = Prozess ist paged out (idle).")
    print("    - Windows verwaltet RAM gut. 'RAM-Cleaner'-Tools sind meist kontraproduktiv.")
    print()


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This script is Windows-only.")
        sys.exit(1)
    main()
