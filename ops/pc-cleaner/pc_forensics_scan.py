"""PC forensics scan — big files, git bloat, dead projects, autostart audit.

Read-only. Standalone version of the MCP big_files_scan / git_bloat_scan /
dead_projects_scan / autostart_audit tools.

Usage:
    python pc_forensics_scan.py                # all four scans, default roots
    python pc_forensics_scan.py big            # only big-files scan
    python pc_forensics_scan.py git            # only git-bloat
    python pc_forensics_scan.py dead           # only dead-projects
    python pc_forensics_scan.py auto           # only autostart
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta


def fmt(b):
    if b > 1024**3:
        return f"{b / 1024**3:.2f} GB"
    if b > 1024**2:
        return f"{b / 1024**2:.0f} MB"
    return f"{b / 1024:.0f} KB"


BIG_FILE_EXCLUDES = (
    r"\appdata\local\docker\\",
    r"\appdata\local\packages\\",
    r"\appdata\local\temp\\",
    r"\windows\installer\\",
    r"\windows\winsxs\\",
    r"\windows\softwaredistribution\\",
    r"\$recycle.bin\\",
    r"\$windows.~bt\\",
    r"\$windows.~ws\\",
    r"\system volume information\\",
    r"\node_modules\\",
    r"\.venv\\",
    r"\.venv312\\",
    r"\.venv311\\",
    r"\target\debug\\",
    r"\target\release\\",
)


def scan_big_files(root="C:\\Users", min_gb=0.5, top=20):
    print()
    print("=" * 64)
    print(f"  BIG FILES (root={root}, min={min_gb} GB)")
    print("=" * 64)
    threshold = int(min_gb * 1024**3)
    hits = []
    for dirpath, _d, files in os.walk(root):
        low = (dirpath + "\\").lower()
        if any(ex in low for ex in BIG_FILE_EXCLUDES):
            continue
        for f in files:
            full = os.path.join(dirpath, f)
            try:
                s = os.path.getsize(full)
            except (PermissionError, OSError):
                continue
            if s >= threshold:
                hits.append((s, full))
    hits.sort(reverse=True)
    for s, p in hits[:top]:
        print(f"  {fmt(s):>10}  {p}")
    print(f"\n  Total: {len(hits)} Treffer")


def scan_git_bloat(root="C:\\Users", min_gb=1.0):
    print()
    print("=" * 64)
    print(f"  GIT BLOAT (root={root}, min={min_gb} GB)")
    print("=" * 64)
    threshold = int(min_gb * 1024**3)
    repos = {}
    for dirpath, _d, files in os.walk(root):
        if r"\.git\objects\pack" not in dirpath.lower():
            continue
        for f in files:
            if not f.endswith(".pack"):
                continue
            full = os.path.join(dirpath, f)
            try:
                s = os.path.getsize(full)
            except (PermissionError, OSError):
                continue
            if s < threshold:
                continue
            repo = dirpath.lower().split(r"\.git\\")[0]
            # Use original case from dirpath
            idx = dirpath.lower().find(r"\.git")
            repo_orig = dirpath[:idx] if idx >= 0 else dirpath
            repos.setdefault(repo_orig, []).append((s, full))
    for repo, packs in sorted(repos.items(), key=lambda r: -sum(s for s, _ in r[1])):
        total = sum(s for s, _ in packs)
        print(f"\n  {fmt(total):>10}  {repo}")
        for s, p in sorted(packs, reverse=True):
            print(f"      {fmt(s):>8}  {os.path.basename(p)}")
        print(f"      Cleanup:  cd \"{repo}\" && git gc --aggressive --prune=now")


DEAD_ARTIFACTS = {"node_modules", ".venv", ".venv311", ".venv312", "target", "build", "dist", ".next", ".nuxt"}
DEAD_SRC_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java", ".md"}


def scan_dead_projects(root="C:\\Users\\User\\Desktop", days_idle=90, min_gb=0.1, top=15):
    print()
    print("=" * 64)
    print(f"  DEAD PROJECTS (root={root}, idle>={days_idle}d, artifact>={min_gb} GB)")
    print("=" * 64)
    cutoff = datetime.now() - timedelta(days=days_idle)
    threshold = int(min_gb * 1024**3)
    candidates = []
    for entry in os.listdir(root):
        full = os.path.join(root, entry)
        if not os.path.isdir(full):
            continue
        newest = 0.0
        artifacts = []
        for dirpath, dirs, files in os.walk(full):
            base = os.path.basename(dirpath)
            if base in DEAD_ARTIFACTS:
                sz = 0
                for r, _, fs in os.walk(dirpath):
                    for ff in fs:
                        try:
                            sz += os.path.getsize(os.path.join(r, ff))
                        except (PermissionError, OSError):
                            pass
                if sz >= threshold:
                    artifacts.append((dirpath, base, sz))
                dirs[:] = []
                continue
            if base.startswith(".") and base != ".github":
                dirs[:] = []
                continue
            for ff in files:
                if os.path.splitext(ff)[1].lower() in DEAD_SRC_EXTS:
                    try:
                        t = os.path.getmtime(os.path.join(dirpath, ff))
                    except (PermissionError, OSError):
                        continue
                    if t > newest:
                        newest = t
        if not artifacts:
            continue
        newest_dt = datetime.fromtimestamp(newest) if newest else None
        if newest_dt is None or newest_dt > cutoff:
            continue
        candidates.append((full, newest_dt, artifacts))
    candidates.sort(key=lambda c: -sum(a[2] for a in c[2]))
    for full, newest, arts in candidates[:top]:
        total = sum(a[2] for a in arts)
        age = (datetime.now() - newest).days
        print(f"\n  {fmt(total):>10}  {full}")
        print(f"     last source: {newest.strftime('%Y-%m-%d')} ({age} days idle)")
        for path, kind, sz in sorted(arts, key=lambda a: -a[2]):
            print(f"        {fmt(sz):>8}  ({kind})  {path}")
    print(f"\n  {len(candidates)} dead projects with reclaimable artifacts")


AUTOSTART_SAFE_DISABLE = {
    "spotify", "discord", "steam", "riotclient", "epic games launcher",
    "skype", "teams", "microsoftedgeautolaunch", "com.squirrel.teams.teams",
}
AUTOSTART_SUS = (
    (r"notepad\.exe", "Autostart launches notepad.exe — leftover PoC/test entry?"),
    (r"powershell.*-(enc|encoded|nop)", "Encoded/no-profile PowerShell on boot"),
    (r"\\Temp\\", "Autostart from a Temp directory"),
    (r"\\Downloads\\", "Autostart from Downloads"),
)


def scan_autostart():
    print()
    print("=" * 64)
    print("  AUTOSTART AUDIT")
    print("=" * 64)
    cmd = (
        "Get-CimInstance Win32_StartupCommand | "
        "Select-Object Name, Command, Location, User | "
        "ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=15, check=False,
        )
        data = json.loads(res.stdout)
        if isinstance(data, dict):
            data = [data]
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {e}")
        return

    suspicious, heavy, system = [], [], []
    for entry in data:
        name = (entry.get("Name") or "").strip()
        c = (entry.get("Command") or "").strip()
        item = (name, c)
        why = None
        for pat, reason in AUTOSTART_SUS:
            if re.search(pat, c, re.IGNORECASE):
                why = reason
                break
        if why:
            suspicious.append((name, c, why))
            continue
        if any(k in name.lower() for k in AUTOSTART_SAFE_DISABLE):
            heavy.append(item)
            continue
        system.append(item)

    if suspicious:
        print("\n  SUSPICIOUS (manuell pruefen!):")
        for n, c, why in suspicious:
            print(f"    [!] {n}: {why}")
            print(f"        {c[:120]}")
    if heavy:
        print("\n  HEAVY/OPTIONAL (oft sicher zu deaktivieren fuer schnelleren Boot):")
        for n, c in heavy:
            print(f"    - {n:<35} {c[:80]}")
    print(f"\n  System/Unknown: {len(system)} (nicht angetastet)")
    print()
    print("  Deaktivieren via Task-Manager -> Autostart-Tab")
    print("  oder: settings.ms-settings:startupapps")


def main():
    args = sys.argv[1:]
    if not args or "big" in args:
        scan_big_files()
    if not args or "git" in args:
        scan_git_bloat()
    if not args or "dead" in args:
        scan_dead_projects()
    if not args or "auto" in args:
        scan_autostart()


if __name__ == "__main__":
    if sys.platform != "win32":
        print("Windows only.")
        sys.exit(1)
    main()
