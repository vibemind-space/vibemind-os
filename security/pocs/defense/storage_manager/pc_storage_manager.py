"""
PC Storage Manager — vollwertiges Speicher-Management-System.

Ein Tool fuer alles: Monitoring, Cleanup, Optimierung, Trends.

Regeln:
  - Performance-sensitive bleibt auf SSD (C:):
    Docker, aktive Projekte, IDEs, Datenbanken, .ollama, .pyenv
  - Archiv/Caches duerfen auf HDD (E:):
    Idle Projekte (>90d), grosse Medien, Backups
  - Caches werden automatisch geleert wenn C: kritisch

Commands:
    python pc_storage_manager.py                # Dashboard: Status + Empfehlungen
    python pc_storage_manager.py doctor         # Alle Checks + Empfehlungen
    python pc_storage_manager.py clean          # Caches leeren
    python pc_storage_manager.py deep-clean     # Aggressive Bereinigung (uv, playwright etc.)
    python pc_storage_manager.py archive        # Idle Projekte nach E: verschieben
    python pc_storage_manager.py scan           # Voller Disk-Scan (alle Ordner)
    python pc_storage_manager.py activity       # Projekt-Aktivitaetsreport
    python pc_storage_manager.py history        # Speicher-Trend anzeigen
    python pc_storage_manager.py auto           # Automatisch: clean + archive + notify
    python pc_storage_manager.py install        # Als Windows Scheduled Task (alle 2h)
    python pc_storage_manager.py uninstall      # Scheduled Task entfernen

    # Optimierungs-Tools:
    python pc_storage_manager.py duplicates     # Duplikat-Dateien finden (Hash-basiert)
    python pc_storage_manager.py big-files      # Groesste Einzeldateien auf C:
    python pc_storage_manager.py docker-prune   # Docker Images/Container/Volumes analysieren
    python pc_storage_manager.py git-gc         # Alle Git-Repos optimieren (gc + prune)
    python pc_storage_manager.py win-cleanup    # Windows Systembereinigung (DISM, Updates)
    python pc_storage_manager.py startup        # Autostart-Programme + Services analysieren
    python pc_storage_manager.py wsl-compact    # WSL2 vhdx komprimieren
    python pc_storage_manager.py python-cleanup # Unbenutzte Python-Versionen in pyenv
    python pc_storage_manager.py perf           # RAM/CPU/Disk Performance-Check
"""

import os
import sys
import json
import stat
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ════════════════════════════════════════════════════════════════
#  PATHS
# ════════════════════════════════════════════════════════════════

HOME = os.path.expanduser("~")
DESKTOP = os.path.join(HOME, "Desktop")
LA = os.environ.get("LOCALAPPDATA", "")
RA = os.environ.get("APPDATA", "")
DATA_DIR = os.path.join(HOME, ".pc_storage_manager")
HISTORY_FILE = os.path.join(DATA_DIR, "history.jsonl")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LOG_FILE = os.path.join(DATA_DIR, "manager.log")
E_PROJECTS = "E:\\Projects"

# ════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "warn_pct": 85,
    "critical_pct": 93,
    "idle_days": 90,
    "auto_clean_on_critical": True,
    "auto_archive_on_critical": False,
    "notify_desktop": True,
    "schedule_interval_hours": 2,

    # SSD-PFLICHT: Diese Ordner NIEMALS auf HDD verschieben
    "ssd_only": [
        "Docker", ".docker",       # Container I/O
        ".ollama",                  # LLM inference
        ".pyenv",                   # Python builds
        ".vscode", ".cursor",      # IDE performance
        ".rustup", ".cargo",       # Compiler
        "node_modules",            # JS builds (in aktiven Projekten)
    ],

    # Projekt-Ordner die gescannt werden
    "project_dirs": [DESKTOP],

    # Drives
    "ssd_drive": "C:\\",
    "hdd_drive": "E:\\",
}

RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}

# ════════════════════════════════════════════════════════════════
#  CACHE DEFINITIONS
# ════════════════════════════════════════════════════════════════

# Level 1: Safe caches (auto-clean OK)
SAFE_CACHES = [
    (os.path.join(LA, "Temp"), "User Temp"),
    (os.path.join(LA, "pip", "cache"), "pip Cache"),
    (os.path.join(LA, "npm-cache"), "npm Cache"),
    (os.path.join(LA, "pnpm", "store"), "pnpm Store"),
    (os.path.join(LA, "yarn", "Cache"), "Yarn Cache"),
    (os.path.join(LA, "NuGet", "Cache"), "NuGet Cache"),
    (os.path.join(HOME, ".cache"), ".cache"),
    (os.path.join(HOME, ".pyenv", "pyenv-win", "install_cache"), "pyenv Install Cache"),
    (os.path.join(LA, "CrashDumps"), "Crash Dumps"),
    (os.path.join(LA, "Microsoft", "Windows", "Explorer"), "Thumbnail Cache"),
    (os.path.join(LA, "Microsoft", "Windows", "INetCache"), "IE/Edge Cache"),
]

# Level 2: Deep caches (nur bei deep-clean)
DEEP_CACHES = [
    (os.path.join(LA, "uv", "cache"), "uv Cache"),
    (os.path.join(LA, "SquirrelTemp"), "SquirrelTemp"),
    (os.path.join(LA, "pypoetry", "Cache"), "pypoetry Cache"),
    (os.path.join(LA, "electron", "Cache"), "electron Cache"),
    (os.path.join(LA, "Docker Desktop Installer"), "Docker Installer"),
    (os.path.join(LA, "llama_index"), "llama_index Cache"),
    (os.path.join(HOME, ".chromium-browser-snapshots"), "Chromium Snapshots"),
    (os.path.join(LA, "claude-cli-nodejs"), "Claude CLI Cache"),
]

# ════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════

def fmt(b):
    if b > 1024**3:
        return f"{b / 1024**3:.1f} GB"
    if b > 1024**2:
        return f"{b / 1024**2:.0f} MB"
    return f"{b / 1024:.0f} KB"


def dir_size(path):
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total


def is_reserved(name):
    return name.split(".")[0].lower() in RESERVED_NAMES


def bar(pct, width=30):
    filled = int(width * pct / 100)
    return f"[{'#' * filled}{'.' * (width - filled)}] {pct:.0f}%"


def load_config():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    return DEFAULT_CONFIG.copy()


def log(msg):
    os.makedirs(DATA_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(f"  {line}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def force_rmtree(path):
    def on_error(func, fpath, exc_info):
        try:
            os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD)
            func(fpath)
        except Exception:
            pass
    shutil.rmtree(path, onerror=on_error)


def notify(title, message, cfg):
    if not cfg.get("notify_desktop", True):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x30)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
#  DRIVE STATUS
# ════════════════════════════════════════════════════════════════

def get_drives(cfg):
    results = {}
    for drive in [cfg["ssd_drive"], cfg["hdd_drive"]]:
        try:
            u = shutil.disk_usage(drive)
            results[drive] = {
                "total": u.total, "used": u.used, "free": u.free,
                "pct": round(u.used / u.total * 100, 1),
            }
        except (PermissionError, OSError):
            pass
    return results


def print_drives(drives, cfg):
    print()
    print("  LAUFWERKE")
    for drive, d in drives.items():
        dtype = "SSD" if drive == cfg["ssd_drive"] else "HDD"
        if d["pct"] >= cfg["critical_pct"]:
            status = "KRITISCH"
        elif d["pct"] >= cfg["warn_pct"]:
            status = "WARNUNG "
        else:
            status = "OK      "
        print(f"    {status}  {drive} ({dtype})  {bar(d['pct'])}  {fmt(d['free'])} frei")


# ════════════════════════════════════════════════════════════════
#  CACHE SCANNER + CLEANER
# ════════════════════════════════════════════════════════════════

def scan_caches(include_deep=False):
    caches = SAFE_CACHES[:]
    if include_deep:
        caches.extend(DEEP_CACHES)
    results = []
    for path, name in caches:
        if os.path.exists(path):
            size = dir_size(path)
            if size > 1024 * 1024:
                results.append({"path": path, "name": name, "size": size})
    results.sort(key=lambda x: -x["size"])
    return results


def clean_cache_dir(path):
    freed = 0
    errors = 0
    try:
        for item in os.listdir(path):
            fp = os.path.join(path, item)
            try:
                if os.path.isfile(fp) or os.path.islink(fp):
                    size = os.path.getsize(fp)
                    os.chmod(fp, stat.S_IWRITE)
                    os.remove(fp)
                    freed += size
                elif os.path.isdir(fp):
                    size = dir_size(fp)
                    force_rmtree(fp)
                    freed += size
            except (PermissionError, OSError):
                errors += 1
    except (PermissionError, OSError):
        errors += 1
    return freed, errors


def do_clean(include_deep=False):
    label = "DEEP CLEAN" if include_deep else "CACHE CLEAN"
    print()
    print(f"  {label}")
    print("  " + "=" * 55)

    caches = SAFE_CACHES[:]
    if include_deep:
        caches.extend(DEEP_CACHES)

    total_freed = 0
    for path, name in caches:
        if not os.path.exists(path):
            continue

        # For deep caches with subdirs (like uv/cache), delete subdirs
        size_before = dir_size(path)
        if size_before < 1024 * 1024:
            continue

        freed, errors = clean_cache_dir(path)
        total_freed += freed

        if freed > 0:
            err = f" ({errors} locked)" if errors else ""
            print(f"    {name:<35} {fmt(freed):>10}{err}")

    print()
    print(f"  TOTAL FREED: {fmt(total_freed)}")
    log(f"CLEAN: {fmt(total_freed)} befreit (deep={include_deep})")
    return total_freed


# ════════════════════════════════════════════════════════════════
#  PROJECT ACTIVITY SCANNER
# ════════════════════════════════════════════════════════════════

def get_project_activity(path):
    """Get last activity date for a project."""
    # Try git first
    if os.path.exists(os.path.join(path, ".git")):
        try:
            result = subprocess.run(
                ["git", "-C", path, "log", "-1", "--format=%aI"],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0 and result.stdout and result.stdout.strip():
                return datetime.fromisoformat(result.stdout.strip()), "git"
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

    # Fallback: newest file
    newest = 0
    try:
        for root, dirs, files in os.walk(path):
            bn = os.path.basename(root)
            if bn in ("node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"):
                dirs.clear()
                continue
            for f in files:
                try:
                    mt = os.stat(os.path.join(root, f)).st_mtime
                    if mt > newest:
                        newest = mt
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass

    if newest > 0:
        return datetime.fromtimestamp(newest), "file"
    return None, None


def categorize_project(days):
    if days is None:
        return "UNBEKANNT", "?"
    if days <= 7:
        return "AKTIV", "C: (SSD)"
    if days <= 30:
        return "RECENT", "C: (SSD)"
    if days <= 90:
        return "IDLE", "C: oder E:"
    return "ARCHIV", "-> E: (HDD)"


def scan_projects(cfg):
    projects = []
    for base_dir in cfg["project_dirs"]:
        if not os.path.exists(base_dir):
            continue
        for item in sorted(os.listdir(base_dir)):
            fp = os.path.join(base_dir, item)
            if not os.path.isdir(fp) or item.startswith(".") or item.startswith("$"):
                continue

            size = dir_size(fp)
            if size < 50 * 1024 * 1024:
                continue

            last_activity, source = get_project_activity(fp)
            days = None
            if last_activity:
                days = (datetime.now() - last_activity.replace(tzinfo=None)).days

            category, rec = categorize_project(days)
            is_junction = os.path.islink(fp)

            # Check for bloated deps
            deps = []
            for dep_name in ["node_modules", "venv", ".venv"]:
                dep_path = os.path.join(fp, dep_name)
                if os.path.exists(dep_path):
                    dep_size = dir_size(dep_path)
                    if dep_size > 100 * 1024 * 1024:
                        deps.append({"name": dep_name, "size": dep_size})

            projects.append({
                "name": item, "path": fp, "size": size,
                "days": days, "category": category, "rec": rec,
                "source": source, "junction": is_junction,
                "last_activity": last_activity,
                "deps": deps,
            })

    return projects


def do_activity(cfg):
    print()
    print("  PROJEKT-AKTIVITAET")
    print("  " + "=" * 70)

    projects = scan_projects(cfg)
    cat_order = {"AKTIV": 0, "RECENT": 1, "IDLE": 2, "ARCHIV": 3, "UNBEKANNT": 4}
    projects.sort(key=lambda p: (cat_order.get(p["category"], 5), -p["size"]))

    current_cat = None
    for p in projects:
        if p["category"] != current_cat:
            current_cat = p["category"]
            labels = {
                "AKTIV": "AKTIV (< 7d) -- bleibt auf SSD",
                "RECENT": "RECENT (7-30d) -- bleibt auf SSD",
                "IDLE": "IDLE (30-90d) -- Kandidat fuer HDD",
                "ARCHIV": "ARCHIV (>90d) -- nach E: verschieben",
                "UNBEKANNT": "UNBEKANNT",
            }
            print(f"\n  --- {labels.get(current_cat, current_cat)} ---")

        days_str = f"{p['days']}d" if p['days'] is not None else "?"
        junc = " [E:]" if p["junction"] else ""
        date_str = p["last_activity"].strftime("%Y-%m-%d") if p["last_activity"] else "?"
        print(f"    {p['name']:<28} {fmt(p['size']):>10}  {days_str:>5} ago  ({date_str}){junc}")

        for dep in p["deps"]:
            idle_hint = " <- loeschbar!" if p["days"] and p["days"] > 60 else ""
            print(f"      {dep['name']:<26} {fmt(dep['size']):>10}{idle_hint}")

    # Summary
    total_archivable = sum(p["size"] for p in projects if p["category"] in ("IDLE", "ARCHIV") and not p["junction"])
    total_deps_idle = sum(
        d["size"] for p in projects if p["days"] and p["days"] > 60
        for d in p["deps"]
    )

    print()
    print(f"  Archivierbar (-> E:):   {fmt(total_archivable)}")
    print(f"  Deps in idle Projekten: {fmt(total_deps_idle)}")
    print()
    return projects


# ════════════════════════════════════════════════════════════════
#  ARCHIVE MOVER
# ════════════════════════════════════════════════════════════════

def copy_tree_safe(src, dst, skipped):
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if is_reserved(item):
            skipped.append(s)
            continue
        try:
            if os.path.isdir(s) and not os.path.islink(s):
                copy_tree_safe(s, d, skipped)
            else:
                try:
                    os.chmod(s, stat.S_IWRITE | stat.S_IREAD)
                except (PermissionError, OSError):
                    pass
                shutil.copy2(s, d)
        except (PermissionError, OSError) as e:
            skipped.append(f"{s} ({e})")


def delete_tree_safe(path):
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            fp = os.path.join(root, f)
            try:
                os.chmod(fp, stat.S_IWRITE)
                os.remove(fp)
            except (PermissionError, OSError):
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except (PermissionError, OSError):
                pass
    try:
        os.rmdir(path)
    except (PermissionError, OSError):
        pass


def do_archive(cfg, auto=False):
    print()
    print("  ARCHIVIERUNG -> E:\\Projects")
    print("  " + "=" * 55)

    projects = scan_projects(cfg)
    to_move = [
        p for p in projects
        if p["category"] == "ARCHIV" and not p["junction"]
    ]

    if not to_move:
        print("  Nichts zu archivieren.")
        return 0

    os.makedirs(E_PROJECTS, exist_ok=True)

    total_freed = 0
    for p in to_move:
        src = p["path"]
        dst = os.path.join(E_PROJECTS, p["name"])

        # Check SSD-only rule
        if any(ssd_name in p["name"] for ssd_name in cfg.get("ssd_only", [])):
            print(f"  SKIP  {p['name']} (SSD-only Regel)")
            continue

        print(f"  MOVE  {p['name']} ({fmt(p['size'])})")

        if os.path.exists(dst):
            print(f"        Ziel existiert, ueberspringe")
            continue

        if not auto:
            answer = input(f"        Verschieben? (j/n): ").strip().lower()
            if answer not in ("j", "ja", "y"):
                print(f"        Uebersprungen")
                continue

        skipped = []
        try:
            copy_tree_safe(src, dst, skipped)
            dst_size = dir_size(dst)

            if dst_size > p["size"] * 0.8:
                delete_tree_safe(src)
                shutil.rmtree(src, ignore_errors=True)

                if not os.path.exists(src):
                    subprocess.run(
                        ["cmd", "/c", "mklink", "/J", src, dst],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace"
                    )
                    print(f"        OK + Junction")
                    total_freed += p["size"]
                else:
                    remaining = dir_size(src)
                    total_freed += p["size"] - remaining
                    print(f"        TEIL ({fmt(remaining)} blieb)")
            else:
                print(f"        Kopie unvollstaendig, abgebrochen")

            if skipped:
                print(f"        {len(skipped)} Dateien uebersprungen (reserved names)")

        except Exception as e:
            print(f"        FEHLER: {e}")

    print(f"\n  TOTAL FREED: {fmt(total_freed)}")
    log(f"ARCHIVE: {fmt(total_freed)} nach E: verschoben")
    return total_freed


# ════════════════════════════════════════════════════════════════
#  FULL DISK SCAN
# ════════════════════════════════════════════════════════════════

def do_scan():
    print()
    print("  VOLLSTAENDIGER DISK-SCAN")
    print("  " + "=" * 70)

    u = shutil.disk_usage("C:\\")
    print(f"  C: Total {fmt(u.total)} | Belegt {fmt(u.used)} ({u.used/u.total*100:.0f}%) | Frei {fmt(u.free)}")

    sections = [
        ("User-Profil", HOME, 500),
        ("AppData Local", os.path.join(HOME, "AppData", "Local"), 500),
        ("AppData Roaming", os.path.join(HOME, "AppData", "Roaming"), 500),
        ("Desktop", DESKTOP, 500),
        ("Program Files", "C:\\Program Files", 1000),
        ("Program Files (x86)", "C:\\Program Files (x86)", 1000),
        ("ProgramData", "C:\\ProgramData", 1000),
    ]

    all_dirs = []

    for label, path, min_mb in sections:
        if not os.path.exists(path):
            continue
        print(f"\n  {label} (>{min_mb} MB)")
        print("  " + "-" * 60)

        entries = []
        try:
            for item in os.scandir(path):
                if item.is_dir(follow_symlinks=False):
                    try:
                        size = dir_size(item.path)
                        if size > min_mb * 1024 * 1024:
                            entries.append((size, item.name, item.path))
                            all_dirs.append((size, item.path))
                    except:
                        pass
        except:
            pass

        entries.sort(reverse=True)
        for size, name, fpath in entries:
            junc = " [JUNCTION]" if os.path.islink(fpath) else ""
            print(f"    {fmt(size):>10}  {name}/{junc}")

    # Top 20
    all_dirs.sort(reverse=True)
    print(f"\n  {'=' * 70}")
    print(f"  TOP 20 GROESSTE ORDNER")
    print(f"  {'=' * 70}")
    for i, (size, path) in enumerate(all_dirs[:20], 1):
        junc = " [E:]" if os.path.islink(path) else ""
        print(f"    {i:>2}. {fmt(size):>10}  {path}{junc}")
    print()


# ════════════════════════════════════════════════════════════════
#  HISTORY / TRENDS
# ════════════════════════════════════════════════════════════════

def save_snapshot(drives, caches_total, freed, action="check"):
    os.makedirs(DATA_DIR, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "action": action,
        "drives": {d: {"pct": v["pct"], "free_gb": round(v["free"] / 1024**3, 1)} for d, v in drives.items()},
        "caches_mb": round(caches_total / 1024**2),
        "freed_mb": round(freed / 1024**2),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def do_history():
    if not os.path.exists(HISTORY_FILE):
        print("  Keine History. Fuehre erst einen Check aus.")
        return

    entries = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass

    if not entries:
        print("  Keine History.")
        return

    print()
    print("  SPEICHER-TREND")
    print("  " + "=" * 75)
    print(f"  {'Datum':<18} {'Aktion':<12} {'C: Belegt':>9} {'C: Frei':>9} {'E: Belegt':>9} {'Freed':>9}")
    print("  " + "-" * 75)

    for e in entries[-30:]:
        ts = e["ts"][:16].replace("T", " ")
        action = e.get("action", "?")[:11]
        c = e["drives"].get("C:\\", {})
        ed = e["drives"].get("E:\\", {})
        freed = f"{e.get('freed_mb', 0)} MB" if e.get("freed_mb", 0) > 0 else "-"
        print(f"  {ts:<18} {action:<12} {c.get('pct','?'):>8}% {c.get('free_gb','?'):>7} GB {ed.get('pct','?'):>8}% {freed:>9}")

    # Trend
    if len(entries) >= 2:
        first_free = entries[0]["drives"].get("C:\\", {}).get("free_gb", 0)
        last_free = entries[-1]["drives"].get("C:\\", {}).get("free_gb", 0)
        diff = last_free - first_free
        days = max(1, (datetime.fromisoformat(entries[-1]["ts"]) - datetime.fromisoformat(entries[0]["ts"])).days)
        sign = "+" if diff > 0 else ""
        print(f"\n  Trend ueber {days} Tage: {sign}{diff:.1f} GB auf C:")
        if diff < 0 and last_free > 0:
            rate = abs(diff) / days
            days_left = last_free / rate if rate > 0 else 999
            print(f"  Warnung: Bei {rate:.1f} GB/Tag ist C: in ~{days_left:.0f} Tagen voll")
        elif diff > 0:
            print(f"  Gut: C: gewinnt {diff/days:.1f} GB/Tag")
    print()


# ════════════════════════════════════════════════════════════════
#  DOCTOR — Full Health Check
# ════════════════════════════════════════════════════════════════

def do_doctor(cfg):
    print()
    print("  ============================================================")
    print("  PC STORAGE DOCTOR")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("  ============================================================")

    drives = get_drives(cfg)
    print_drives(drives, cfg)

    # Caches
    caches = scan_caches(include_deep=True)
    total_cache = sum(c["size"] for c in caches)
    if caches:
        print(f"\n  CACHES ({fmt(total_cache)} loeschbar)")
        for c in caches[:10]:
            print(f"    {c['name']:<35} {fmt(c['size']):>10}")

    # Projects
    projects = scan_projects(cfg)
    archivable = [p for p in projects if p["category"] in ("IDLE", "ARCHIV") and not p["junction"]]
    total_archive = sum(p["size"] for p in archivable)

    bloated_deps = []
    for p in projects:
        if p["days"] and p["days"] > 60:
            for d in p["deps"]:
                bloated_deps.append({"project": p["name"], **d, "idle_days": p["days"]})
    total_deps = sum(d["size"] for d in bloated_deps)

    if archivable:
        print(f"\n  ARCHIVIERBAR ({fmt(total_archive)})")
        for p in sorted(archivable, key=lambda x: -x["size"])[:10]:
            print(f"    {p['name']:<28} {fmt(p['size']):>10}  {p['days']}d idle")

    if bloated_deps:
        print(f"\n  DEPS IN IDLE PROJEKTEN ({fmt(total_deps)})")
        for d in sorted(bloated_deps, key=lambda x: -x["size"])[:8]:
            print(f"    {d['project']}/{d['name']:<22} {fmt(d['size']):>10}  [{d['idle_days']}d idle]")

    # Windows system
    print(f"\n  SYSTEM-DATEIEN (Info)")
    for name, path in [("pagefile.sys", "C:\\pagefile.sys"), ("hiberfil.sys", "C:\\hiberfil.sys")]:
        if os.path.exists(path):
            try:
                size = os.path.getsize(path)
                print(f"    {name:<35} {fmt(size):>10}")
            except:
                pass
    wbt = "C:\\$Windows.~BT"
    if os.path.exists(wbt):
        size = dir_size(wbt)
        if size > 1024**3:
            print(f"    {'$Windows.~BT (altes Update)':<35} {fmt(size):>10}  <- Datentraegerbereinigung")

    # Docker
    docker_wsl = os.path.join(LA, "Docker", "wsl")
    if os.path.exists(docker_wsl):
        dsize = dir_size(docker_wsl)
        print(f"\n  DOCKER ({fmt(dsize)} auf SSD -- korrekt, bleibt hier)")
        print(f"    Tipp: 'docker system prune -a' kann unbenutzte Images loeschen")

    # Summary + recommendations
    total_potential = total_cache + total_archive + total_deps
    c_drive = drives.get(cfg["ssd_drive"], {})

    print()
    print("  ============================================================")
    print("  EMPFEHLUNGEN")
    print("  ============================================================")

    recs = []
    if total_cache > 500 * 1024 * 1024:
        recs.append(f"  1. pc_storage_manager.py deep-clean     Caches leeren ({fmt(total_cache)})")
    if total_archive > 1024**3:
        recs.append(f"  2. pc_storage_manager.py archive         Idle -> E: ({fmt(total_archive)})")
    if total_deps > 500 * 1024 * 1024:
        recs.append(f"  3. venv/node_modules in idle loeschen    ({fmt(total_deps)})")
    if os.path.exists(wbt):
        recs.append(f"  4. Datentraegerbereinigung ausfuehren    $Windows.~BT loeschen")

    if c_drive.get("pct", 0) >= cfg["critical_pct"]:
        recs.append(f"  !  KRITISCH: C: bei {c_drive['pct']}% — sofort handeln!")

    if recs:
        for r in recs:
            print(r)
    else:
        print("  Alles gut! Keine Massnahmen noetig.")

    print(f"\n  Potenzial: {fmt(total_potential)} freimachbar")
    print()

    save_snapshot(drives, total_cache, 0, "doctor")
    return total_potential


# ════════════════════════════════════════════════════════════════
#  AUTO MODE
# ════════════════════════════════════════════════════════════════

def do_auto(cfg):
    """Automatic mode: check, clean if needed, notify."""
    drives = get_drives(cfg)
    c_drive = drives.get(cfg["ssd_drive"])
    if not c_drive:
        return

    freed = 0

    # Auto-clean if critical
    if c_drive["pct"] >= cfg["critical_pct"] and cfg.get("auto_clean_on_critical"):
        log(f"AUTO: C: bei {c_drive['pct']}%, starte Clean...")
        freed += do_clean(include_deep=True)

        # Recheck
        drives = get_drives(cfg)
        c_drive = drives.get(cfg["ssd_drive"])

    # Auto-archive if still critical
    if c_drive and c_drive["pct"] >= cfg["critical_pct"] and cfg.get("auto_archive_on_critical"):
        log("AUTO: Immer noch kritisch, archiviere...")
        freed += do_archive(cfg, auto=True)

    # Notify if still critical
    drives = get_drives(cfg)
    c_drive = drives.get(cfg["ssd_drive"])
    if c_drive and c_drive["pct"] >= cfg["critical_pct"]:
        caches = scan_caches(include_deep=True)
        total_cache = sum(c["size"] for c in caches)
        notify(
            "PC Storage Manager: C: kritisch!",
            f"C: ist zu {c_drive['pct']}% belegt ({fmt(c_drive['free'])} frei).\n"
            f"Caches: {fmt(total_cache)} loeschbar.\n"
            f"Fuehre 'pc_storage_manager.py doctor' aus.",
            cfg
        )

    save_snapshot(drives, 0, freed, "auto")

    if freed > 0:
        log(f"AUTO: {fmt(freed)} befreit, C: jetzt bei {c_drive['pct']}%")
    else:
        log(f"AUTO: Check OK, C: bei {c_drive['pct']}%")


# ════════════════════════════════════════════════════════════════
#  TASK SCHEDULER
# ════════════════════════════════════════════════════════════════

TASK_NAME = "PC_Storage_Manager"

def do_install(cfg):
    script = os.path.abspath(__file__)
    python = sys.executable
    hours = cfg.get("schedule_interval_hours", 2)

    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <Repetition>
        <Interval>PT{hours}H</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-01-01T08:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT5M</Delay>
    </LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Hidden>false</Hidden>
    <Enabled>true</Enabled>
  </Settings>
  <Actions>
    <Exec>
      <Command>{python}</Command>
      <Arguments>"{script}" auto</Arguments>
    </Exec>
  </Actions>
</Task>'''

    xml_path = os.path.join(DATA_DIR, "task.xml")
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    if result.returncode == 0:
        print(f"\n  Task '{TASK_NAME}' installiert!")
        print(f"    Intervall:  alle {hours}h + 5min nach Login")
        print(f"    Aktion:     Auto-Clean wenn C: > {cfg['critical_pct']}%")
        print(f"    Config:     {CONFIG_FILE}")
        print(f"    Log:        {LOG_FILE}")
        print(f"    History:    {HISTORY_FILE}")
        log(f"INSTALL: Task erstellt (alle {hours}h)")
    else:
        print(f"  FEHLER: {result.stderr.strip()}")
        print(f"  Evtl. als Admin ausfuehren.")


def do_uninstall():
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode == 0:
        print(f"  Task '{TASK_NAME}' entfernt.")
        log("UNINSTALL: Task entfernt")
    else:
        print(f"  FEHLER: {result.stderr.strip()}")


# ════════════════════════════════════════════════════════════════
#  DUPLICATE FINDER
# ════════════════════════════════════════════════════════════════

def do_duplicates(cfg):
    """Find duplicate files by size + partial hash."""
    import hashlib

    print()
    print("  DUPLIKAT-FINDER")
    print("  " + "=" * 65)

    scan_dirs = [
        DESKTOP,
        os.path.join(HOME, "Downloads"),
        os.path.join(HOME, "Documents"),
        os.path.join(HOME, "Videos"),
    ]

    # Phase 1: Group files by size (fast pre-filter)
    print("  Phase 1: Dateien nach Groesse gruppieren...")
    size_groups = {}
    file_count = 0
    for scan_dir in scan_dirs:
        if not os.path.exists(scan_dir):
            continue
        for root, dirs, files in os.walk(scan_dir):
            bn = os.path.basename(root)
            if bn in ("node_modules", ".git", "__pycache__", "venv", ".venv", ".cache"):
                dirs.clear()
                continue
            for f in files:
                fp = os.path.join(root, f)
                try:
                    size = os.path.getsize(fp)
                    if size > 1024 * 1024:  # >1MB
                        if size not in size_groups:
                            size_groups[size] = []
                        size_groups[size].append(fp)
                        file_count += 1
                except (PermissionError, OSError):
                    pass

    # Only keep groups with >1 file (potential dupes)
    candidates = {s: paths for s, paths in size_groups.items() if len(paths) > 1}
    print(f"  {file_count} Dateien gescannt, {sum(len(v) for v in candidates.values())} Kandidaten")

    # Phase 2: Hash first 64KB of candidates
    print("  Phase 2: Hash-Vergleich...")

    def partial_hash(filepath, chunk_size=65536):
        h = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                h.update(f.read(chunk_size))
        except (PermissionError, OSError):
            return None
        return h.hexdigest()

    duplicates = []
    for size, paths in sorted(candidates.items(), reverse=True):
        hash_groups = {}
        for p in paths:
            h = partial_hash(p)
            if h:
                if h not in hash_groups:
                    hash_groups[h] = []
                hash_groups[h].append(p)

        for h, group in hash_groups.items():
            if len(group) > 1:
                duplicates.append((size, group))

    if not duplicates:
        print("  Keine Duplikate gefunden.")
        return

    # Report
    total_waste = 0
    duplicates.sort(key=lambda x: -x[0] * (len(x[1]) - 1))

    print()
    print(f"  {'Groesse':>10}  {'Kopien':>6}  {'Verschwendet':>12}  Dateien")
    print("  " + "-" * 75)

    for size, group in duplicates[:30]:
        waste = size * (len(group) - 1)
        total_waste += waste
        print(f"  {fmt(size):>10}  {len(group):>6}  {fmt(waste):>12}  {os.path.basename(group[0])}")
        for p in group:
            print(f"  {'':>10}  {'':>6}  {'':>12}    {p}")

    print()
    print(f"  TOTAL VERSCHWENDET: {fmt(total_waste)} (in {len(duplicates)} Duplikat-Gruppen)")
    print()


# ════════════════════════════════════════════════════════════════
#  BIG FILES FINDER
# ════════════════════════════════════════════════════════════════

def do_big_files():
    """Find largest individual files on C:."""
    print()
    print("  GROESSTE EINZELDATEIEN AUF C:")
    print("  " + "=" * 70)

    big = []
    scan_roots = [
        HOME,
        "C:\\code",
    ]

    for scan_root in scan_roots:
        if not os.path.exists(scan_root):
            continue
        for root, dirs, files in os.walk(scan_root):
            bn = os.path.basename(root)
            if bn in ("node_modules", ".git", "wsl"):
                dirs.clear()
                continue
            for f in files:
                fp = os.path.join(root, f)
                try:
                    size = os.path.getsize(fp)
                    if size > 100 * 1024 * 1024:  # >100MB
                        ext = os.path.splitext(f)[1].lower()
                        big.append((size, f, fp, ext))
                except (PermissionError, OSError):
                    pass

    big.sort(reverse=True)

    # Group by extension
    ext_totals = {}
    for size, name, path, ext in big:
        ext_totals[ext] = ext_totals.get(ext, 0) + size

    print(f"\n  Top 30 Dateien (>100 MB):")
    print(f"  {'Groesse':>10}  {'Typ':>6}  Pfad")
    print("  " + "-" * 75)

    for size, name, path, ext in big[:30]:
        print(f"  {fmt(size):>10}  {ext:>6}  {path}")

    print(f"\n  Nach Dateityp:")
    for ext, total in sorted(ext_totals.items(), key=lambda x: -x[1])[:15]:
        label = ext if ext else "(kein)"
        print(f"    {label:<10} {fmt(total):>10}")

    print(f"\n  TOTAL: {fmt(sum(s for s, _, _, _ in big))} in {len(big)} grossen Dateien")
    print()


# ════════════════════════════════════════════════════════════════
#  DOCKER OPTIMIZER
# ════════════════════════════════════════════════════════════════

def do_docker_prune():
    """Analyze Docker disk usage and offer cleanup."""
    print()
    print("  DOCKER ANALYSE")
    print("  " + "=" * 55)

    # Check if docker is available
    try:
        result = subprocess.run(
            ["docker", "system", "df", "-v"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            print("  Docker nicht erreichbar (laeuft Docker Desktop?)")
            return
        print()
        print(result.stdout)
    except FileNotFoundError:
        print("  Docker CLI nicht gefunden.")
        return
    except subprocess.TimeoutExpired:
        print("  Docker antwortet nicht (Timeout).")
        return

    # Show disk usage summary
    try:
        result = subprocess.run(
            ["docker", "system", "df"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            print("  ZUSAMMENFASSUNG:")
            print(result.stdout)
    except:
        pass

    # Dangling images
    try:
        result = subprocess.run(
            ["docker", "images", "-f", "dangling=true", "--format", "{{.Repository}}:{{.Tag}} {{.Size}}"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0 and result.stdout.strip():
            print("  DANGLING IMAGES (sicher loeschbar):")
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
    except:
        pass

    # Stopped containers
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "-f", "status=exited", "--format", "{{.Names}} ({{.Image}}) {{.Size}}"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0 and result.stdout.strip():
            print("\n  GESTOPPTE CONTAINER:")
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
    except:
        pass

    print()
    print("  AKTIONEN:")
    print("    docker system prune         Gestoppte Container + dangling Images")
    print("    docker system prune -a      ALLES unbenutzte loeschen (aggressiv)")
    print("    docker builder prune        Build-Cache leeren")
    print("    docker volume prune         Unbenutzte Volumes loeschen")
    print()


# ════════════════════════════════════════════════════════════════
#  GIT REPO OPTIMIZER
# ════════════════════════════════════════════════════════════════

def do_git_gc(cfg):
    """Run git gc + prune on all repos."""
    print()
    print("  GIT REPOSITORY OPTIMIERUNG")
    print("  " + "=" * 55)

    repos = []
    scan_dirs = cfg.get("project_dirs", [DESKTOP])
    scan_dirs.append(E_PROJECTS)

    for scan_dir in scan_dirs:
        if not os.path.exists(scan_dir):
            continue
        for item in os.listdir(scan_dir):
            fp = os.path.join(scan_dir, item)
            git_dir = os.path.join(fp, ".git")
            if os.path.isdir(fp) and os.path.exists(git_dir):
                git_size = dir_size(git_dir)
                repos.append((git_size, item, fp))

    repos.sort(reverse=True)

    print(f"\n  {len(repos)} Git-Repos gefunden\n")
    print(f"  {'Repo':<30} {'.git Groesse':>12} {'Nach gc':>12} {'Gespart':>10}")
    print("  " + "-" * 68)

    total_saved = 0
    for git_size, name, path in repos:
        if git_size < 10 * 1024 * 1024:  # Skip <10MB
            continue

        print(f"  {name:<30} {fmt(git_size):>12} ", end="", flush=True)

        try:
            subprocess.run(
                ["git", "-C", path, "gc", "--aggressive", "--prune=now"],
                capture_output=True, text=True, timeout=120,
                encoding="utf-8", errors="replace"
            )
            subprocess.run(
                ["git", "-C", path, "prune"],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace"
            )

            new_size = dir_size(os.path.join(path, ".git"))
            saved = git_size - new_size
            total_saved += max(0, saved)

            if saved > 0:
                print(f"{fmt(new_size):>12} {fmt(saved):>10}")
            else:
                print(f"{fmt(new_size):>12} {'--':>10}")

        except subprocess.TimeoutExpired:
            print(f"{'TIMEOUT':>12} {'--':>10}")
        except Exception as e:
            print(f"{'FEHLER':>12} {'--':>10}")

    print(f"\n  TOTAL GESPART: {fmt(total_saved)}")
    print()


# ════════════════════════════════════════════════════════════════
#  WINDOWS SYSTEM CLEANUP
# ════════════════════════════════════════════════════════════════

def do_win_cleanup():
    """Windows system cleanup analysis + actions."""
    print()
    print("  WINDOWS SYSTEMBEREINIGUNG")
    print("  " + "=" * 55)

    # 1. $Windows.~BT
    wbt = "C:\\$Windows.~BT"
    wbt_size = 0
    if os.path.exists(wbt):
        wbt_size = dir_size(wbt)
        print(f"\n  $Windows.~BT (altes Upgrade):  {fmt(wbt_size)}")
        print(f"    -> Datentraegerbereinigung -> 'Vorherige Windows-Installation'")

    # 2. Windows Update Cache
    wu = "C:\\Windows\\SoftwareDistribution\\Download"
    wu_size = 0
    if os.path.exists(wu):
        wu_size = dir_size(wu)
        print(f"  Windows Update Cache:          {fmt(wu_size)}")

    # 3. Windows Installer orphans
    wi = "C:\\Windows\\Installer"
    wi_size = 0
    if os.path.exists(wi):
        wi_size = dir_size(wi)
        print(f"  Windows Installer:             {fmt(wi_size)}")
        print(f"    -> Vorsicht: nur mit msizap/PatchCleaner bereinigen")

    # 4. pagefile + hiberfil
    print(f"\n  SYSTEM-DATEIEN:")
    for name, path in [("pagefile.sys", "C:\\pagefile.sys"), ("hiberfil.sys", "C:\\hiberfil.sys")]:
        if os.path.exists(path):
            try:
                size = os.path.getsize(path)
                print(f"    {name:<20} {fmt(size):>10}")
            except:
                pass

    # 5. DISM component cleanup check
    print(f"\n  DISM COMPONENT STORE:")
    try:
        result = subprocess.run(
            ["dism", "/Online", "/Cleanup-Image", "/AnalyzeComponentStore"],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if any(kw in line.lower() for kw in ["component store", "empfoh", "recommend", "size", "groesse"]):
                    print(f"    {line}")
        else:
            print(f"    Braucht Admin-Rechte")
    except subprocess.TimeoutExpired:
        print(f"    Timeout")
    except FileNotFoundError:
        print(f"    DISM nicht gefunden")

    # 6. Temp dirs in Windows
    print(f"\n  WINDOWS TEMP ORDNER:")
    win_temps = [
        ("C:\\Windows\\Temp", "Windows Temp"),
        ("C:\\Windows\\Prefetch", "Prefetch"),
        ("C:\\Windows\\Logs", "Windows Logs"),
    ]
    for path, name in win_temps:
        if os.path.exists(path):
            size = dir_size(path)
            if size > 50 * 1024 * 1024:
                print(f"    {name:<25} {fmt(size):>10}")

    total = wbt_size + wu_size
    print()
    print(f"  EMPFOHLENE AKTIONEN:")
    if wbt_size > 1024**3:
        print(f"    1. cleanmgr /d C:                     $Windows.~BT loeschen ({fmt(wbt_size)})")
    print(f"    2. powercfg /h off                    Ruhezustand deaktivieren (12.7 GB)")
    print(f"    3. Auslagerungsdatei auf 8-16 GB      pagefile reduzieren")
    if wu_size > 500 * 1024 * 1024:
        print(f"    4. SoftwareDistribution leeren        Update-Cache ({fmt(wu_size)})")
    print(f"    5. dism /Online /Cleanup-Image /StartComponentCleanup  (als Admin)")
    print()


# ════════════════════════════════════════════════════════════════
#  STARTUP / SERVICES ANALYZER
# ════════════════════════════════════════════════════════════════

def do_startup():
    """Analyze startup programs and heavy services."""
    print()
    print("  AUTOSTART + SERVICES ANALYSE")
    print("  " + "=" * 65)

    # 1. Startup programs
    print(f"\n  AUTOSTART-PROGRAMME:")
    try:
        result = subprocess.run(
            ["wmic", "startup", "get", "Name,Command,Location", "/format:csv"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip() and "Node" not in l]
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 3:
                    cmd = parts[1][:60] if len(parts[1]) > 60 else parts[1]
                    name = parts[2] if len(parts) > 2 else ""
                    print(f"    {name:<30} {cmd}")
    except:
        pass

    # Also check startup folders
    startup_dirs = [
        os.path.join(RA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"),
        "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\StartUp",
    ]
    print(f"\n  STARTUP-ORDNER:")
    for sd in startup_dirs:
        if os.path.exists(sd):
            items = os.listdir(sd)
            if items:
                for item in items:
                    if not item.startswith("desktop"):
                        print(f"    {item}")

    # 2. Heavy running services
    print(f"\n  SPEICHERINTENSIVE PROZESSE (Top 15):")
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name,@{N='RAM_MB';E={[math]::Round($_.WorkingSet64/1MB)}},CPU,Id | Format-Table -AutoSize"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
    except:
        print("    Konnte Prozesse nicht lesen")

    # 3. Services set to auto-start
    print(f"\n  AUTO-START SERVICES (laufend, die RAM fressen):")
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Service | Where-Object {$_.Status -eq 'Running' -and $_.StartType -eq 'Automatic'} | Select-Object Name,DisplayName | Format-Table -AutoSize"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            # Just show count + notable ones
            service_count = len([l for l in lines if l.strip() and "---" not in l and "Name" not in l])
            print(f"    {service_count} automatische Services laufen")
            print(f"    (Details: Get-Service | Where Status -eq Running)")
    except:
        pass

    print()


# ════════════════════════════════════════════════════════════════
#  WSL COMPACT
# ════════════════════════════════════════════════════════════════

def do_wsl_compact():
    """Compact WSL2 virtual hard disks."""
    print()
    print("  WSL2 VHDX KOMPRIMIERUNG")
    print("  " + "=" * 55)

    # Find all WSL vhdx files
    wsl_dirs = [
        os.path.join(LA, "Docker", "wsl"),
        os.path.join(LA, "Packages"),
    ]

    vhdx_files = []
    for wsl_dir in wsl_dirs:
        if not os.path.exists(wsl_dir):
            continue
        for root, dirs, files in os.walk(wsl_dir):
            for f in files:
                if f.endswith(".vhdx"):
                    fp = os.path.join(root, f)
                    try:
                        size = os.path.getsize(fp)
                        vhdx_files.append((size, f, fp))
                    except (PermissionError, OSError):
                        pass

    if not vhdx_files:
        print("  Keine WSL vhdx-Dateien gefunden.")
        return

    vhdx_files.sort(reverse=True)
    total = sum(s for s, _, _ in vhdx_files)

    print(f"\n  VHDX-Dateien: {fmt(total)} total\n")
    for size, name, path in vhdx_files:
        print(f"    {fmt(size):>10}  {path}")

    # List WSL distros
    print(f"\n  WSL DISTRIBUTIONEN:")
    try:
        result = subprocess.run(
            ["wsl", "--list", "--verbose"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if line.strip():
                    print(f"    {line.strip()}")
    except:
        print("    WSL nicht verfuegbar")

    print()
    print("  ZUM KOMPRIMIEREN (als Admin, WSL muss gestoppt sein):")
    print("    wsl --shutdown")
    print("    diskpart")
    print("      select vdisk file=\"<pfad>.vhdx\"")
    print("      compact vdisk")
    print()
    print("  Alternativ (Docker):")
    print("    wsl --shutdown")
    print("    Optimize-VHD -Path \"<pfad>.vhdx\" -Mode Full  (Hyper-V PowerShell)")
    print()


# ════════════════════════════════════════════════════════════════
#  PYTHON VERSION CLEANUP
# ════════════════════════════════════════════════════════════════

def do_python_cleanup():
    """Analyze pyenv Python installations and find unused versions."""
    print()
    print("  PYTHON VERSION CLEANUP")
    print("  " + "=" * 55)

    pyenv_versions = os.path.join(HOME, ".pyenv", "pyenv-win", "versions")
    pyenv_cache = os.path.join(HOME, ".pyenv", "pyenv-win", "install_cache")

    if not os.path.exists(pyenv_versions):
        print("  pyenv nicht gefunden.")
        return

    # List installed versions
    versions = []
    for item in os.listdir(pyenv_versions):
        fp = os.path.join(pyenv_versions, item)
        if os.path.isdir(fp):
            size = dir_size(fp)
            versions.append((size, item, fp))

    versions.sort(reverse=True)
    total = sum(s for s, _, _ in versions)

    print(f"\n  INSTALLIERTE PYTHON-VERSIONEN ({fmt(total)} total):\n")
    print(f"  {'Version':<20} {'Groesse':>10}")
    print("  " + "-" * 32)
    for size, name, path in versions:
        print(f"  {name:<20} {fmt(size):>10}")

    # Check which are actually used (look for .python-version files)
    print(f"\n  IN PROJEKTEN GENUTZT:")
    used_versions = set()
    for scan_dir in [DESKTOP, E_PROJECTS, "C:\\code"]:
        if not os.path.exists(scan_dir):
            continue
        for item in os.listdir(scan_dir):
            pv_file = os.path.join(scan_dir, item, ".python-version")
            if os.path.exists(pv_file):
                try:
                    with open(pv_file, "r") as f:
                        ver = f.read().strip()
                        used_versions.add(ver)
                        print(f"    {ver:<20} <- {item}")
                except:
                    pass

    # Install cache
    cache_size = 0
    if os.path.exists(pyenv_cache):
        cache_size = dir_size(pyenv_cache)

    print(f"\n  Install Cache: {fmt(cache_size)}")

    # Find unused
    unused = [(s, n, p) for s, n, p in versions if n not in used_versions]
    unused_total = sum(s for s, _, _ in unused)

    if unused:
        print(f"\n  NICHT IN .python-version REFERENZIERT ({fmt(unused_total)}):")
        for size, name, path in unused:
            print(f"    {name:<20} {fmt(size):>10}  <- pyenv uninstall {name}")

    print()
    if cache_size > 100 * 1024 * 1024:
        print(f"  Cache loeschen:  pyenv rehash && rd /s /q \"{pyenv_cache}\"")
    print()


# ════════════════════════════════════════════════════════════════
#  PERFORMANCE MONITOR
# ════════════════════════════════════════════════════════════════

def do_perf():
    """Quick system performance snapshot."""
    print()
    print("  SYSTEM PERFORMANCE CHECK")
    print("  " + "=" * 65)

    # 1. CPU + RAM
    print(f"\n  CPU + RAM:")
    try:
        result = subprocess.run(
            ["powershell", "-Command", """
$cpu = (Get-CimInstance Win32_Processor).LoadPercentage
$os = Get-CimInstance Win32_OperatingSystem
$totalRAM = [math]::Round($os.TotalVisibleMemorySize/1MB, 1)
$freeRAM = [math]::Round($os.FreePhysicalMemory/1MB, 1)
$usedRAM = $totalRAM - $freeRAM
$pctRAM = [math]::Round($usedRAM/$totalRAM*100, 0)
Write-Output "CPU: $cpu%"
Write-Output "RAM: $usedRAM / $totalRAM GB ($pctRAM%)"
Write-Output "RAM frei: $freeRAM GB"
"""],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
    except:
        print("    Konnte nicht lesen")

    # 2. Disk I/O (current)
    print(f"\n  DISK I/O (aktuelle Last):")
    try:
        result = subprocess.run(
            ["powershell", "-Command", """
$counters = Get-Counter '\\PhysicalDisk(*)\\Disk Bytes/sec','\\PhysicalDisk(*)\\% Disk Time' -SampleInterval 1 -MaxSamples 1
foreach ($sample in $counters.CounterSamples) {
    if ($sample.CookedValue -gt 0 -and $sample.InstanceName -ne '_total') {
        $name = $sample.InstanceName
        $path = $sample.Path
        $val = [math]::Round($sample.CookedValue, 1)
        if ($path -like '*bytes*') { $val = [math]::Round($val/1MB, 1); $unit = 'MB/s' }
        else { $unit = '%' }
        Write-Output "$name : $val $unit ($($path.Split('\\')[-1]))"
    }
}
"""],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
        else:
            print("    Braucht evtl. Admin-Rechte")
    except:
        print("    Konnte nicht lesen")

    # 3. Top RAM consumers
    print(f"\n  TOP 10 RAM-VERBRAUCHER:")
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 | ForEach-Object { '{0,-30} {1,8} MB' -f $_.ProcessName, [math]::Round($_.WorkingSet64/1MB) }"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
    except:
        print("    Konnte nicht lesen")

    # 4. Disk health (SMART basic)
    print(f"\n  DISK SMART STATUS:")
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus | Format-Table -AutoSize"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
    except:
        pass

    # 5. Boot time
    print(f"\n  SYSTEM UPTIME:")
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; $up = (Get-Date) - $boot; Write-Output \"Letzter Boot: $($boot.ToString('yyyy-MM-dd HH:mm'))\"; Write-Output \"Uptime: $($up.Days)d $($up.Hours)h $($up.Minutes)m\""],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
    except:
        pass

    print()


# ════════════════════════════════════════════════════════════════
#  EXECUTE APPROVED (from HTML approval UI)
# ════════════════════════════════════════════════════════════════

APPROVED_FILE = os.path.join(DATA_DIR, "approved.json")

# Map of action commands to executable functions
def execute_action(action, cfg):
    """Execute a single approved action. Returns bytes freed."""
    cmd = action["command"]
    action_id = action["id"]
    risk = action.get("risk_level", "check")

    # Safety gate: skip risky actions (need manual execution)
    if risk == "risky":
        print(f"    SKIP  {action['action']} (RISIKO — manuell ausfuehren)")
        print(f"           Befehl: {cmd}")
        return 0

    # Analysis-only actions
    if risk == "check":
        print(f"    INFO  {action['action']} (Analyse-Tool)")
        # Run the analysis command
        analysis_cmds = {
            "duplicates": lambda: do_duplicates(cfg),
            "big-files": do_big_files,
            "docker:prune": do_docker_prune,
            "python-cleanup": do_python_cleanup,
            "startup": do_startup,
            "perf": do_perf,
            "wsl-compact": do_wsl_compact,
        }
        handler = analysis_cmds.get(cmd)
        if handler:
            handler()
        else:
            print(f"           -> Fuehre manuell aus: pc_storage_manager.py {cmd}")
        return 0

    # Safe executable actions
    freed = 0

    if cmd == "clean":
        freed = do_clean(include_deep=False)

    elif cmd.startswith("deep-clean"):
        freed = do_clean(include_deep=True)

    elif cmd.startswith("archive:"):
        freed = do_archive(cfg, auto=True)

    elif cmd.startswith("rm-dep:"):
        dep_path_rel = cmd.split(":", 1)[1]
        # Check both Desktop and E:\Projects
        for base in [DESKTOP, E_PROJECTS]:
            dep_path = os.path.join(base, dep_path_rel)
            if os.path.exists(dep_path) and not os.path.islink(dep_path):
                size = dir_size(dep_path)
                force_rmtree(dep_path)
                if not os.path.exists(dep_path):
                    print(f"    DEL   {dep_path_rel} ({fmt(size)})")
                    freed += size
                    break

    elif cmd == "git-gc":
        do_git_gc(cfg)

    elif cmd == "install":
        do_install(cfg)

    else:
        print(f"    ?     Unbekannter Command: {cmd}")

    return freed


def do_execute_approved(cfg):
    """Read approved.json and execute all permission_granted actions."""
    print()
    print("  ============================================================")
    print("  EXECUTE APPROVED ACTIONS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("  ============================================================")

    if not os.path.exists(APPROVED_FILE):
        print(f"\n  Keine approved.json gefunden.")
        print(f"  1. Oeffne pc_optimization_checklist.html im Browser")
        print(f"  2. Hake Aktionen ab die erlaubt sind")
        print(f"  3. Klicke 'Approval exportieren'")
        print(f"  4. Speichere die Datei nach: {APPROVED_FILE}")
        print(f"  5. Fuehre diesen Befehl erneut aus")
        return

    with open(APPROVED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    actions = data.get("actions", [])
    if not actions:
        print("\n  Keine Aktionen in approved.json.")
        return

    granted = [a for a in actions if a.get("permission_granted")]
    if not granted:
        print("\n  Keine Aktionen mit permission_granted: true.")
        return

    safe_actions = [a for a in granted if a.get("risk_level") == "safe"]
    check_actions = [a for a in granted if a.get("risk_level") == "check"]
    risky_actions = [a for a in granted if a.get("risk_level") == "risky"]

    print(f"\n  Geladen: {len(granted)} genehmigte Aktionen")
    print(f"    Sicher (auto-ausfuehrbar):  {len(safe_actions)}")
    print(f"    Analyse (read-only):        {len(check_actions)}")
    print(f"    Risiko (nur manuell):       {len(risky_actions)}")
    print(f"    Geschaetztes Potenzial:     ~{data.get('total_estimated_gb', 0):.1f} GB")

    print(f"\n  Starte Ausfuehrung...\n")
    print("  " + "-" * 55)

    total_freed = 0
    executed = 0
    skipped = 0

    # Group safe actions by command to avoid running same cleanup twice
    seen_cmds = set()

    for action in granted:
        cmd = action["command"]

        # Deduplicate: don't run "clean" or "deep-clean" multiple times
        base_cmd = cmd.split(":")[0]
        if base_cmd in ("clean", "deep-clean", "archive") and base_cmd in seen_cmds:
            continue
        seen_cmds.add(base_cmd)

        print(f"\n  [{action['risk_level'].upper():>7}] {action['action']}")
        freed = execute_action(action, cfg)
        total_freed += freed
        if freed > 0 or action.get("risk_level") == "check":
            executed += 1
        else:
            skipped += 1

    # Summary
    drives = get_drives(cfg)

    print()
    print("  " + "=" * 55)
    print(f"  ERGEBNIS")
    print(f"    Ausgefuehrt:  {executed}")
    print(f"    Uebersprungen: {skipped} (Risiko/manuell)")
    print(f"    Platz befreit: {fmt(total_freed)}")
    print_drives(drives, cfg)

    # Save snapshot
    save_snapshot(drives, 0, total_freed, "execute-approved")

    # Rename approved.json to mark as processed
    processed = APPROVED_FILE.replace(".json", f"_done_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    os.rename(APPROVED_FILE, processed)
    print(f"\n  approved.json -> {os.path.basename(processed)}")
    print(f"  (Erstelle neue Genehmigungen ueber die HTML-Checklist)")
    print()


# ════════════════════════════════════════════════════════════════
#  DASHBOARD (Default)
# ════════════════════════════════════════════════════════════════

def do_dashboard(cfg):
    drives = get_drives(cfg)

    print()
    print("  ============================================================")
    print(f"  PC STORAGE MANAGER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("  ============================================================")

    print_drives(drives, cfg)

    # Quick cache total
    caches = scan_caches(include_deep=True)
    total_cache = sum(c["size"] for c in caches)

    # Quick project count
    projects = scan_projects(cfg)
    active = sum(1 for p in projects if p["category"] in ("AKTIV", "RECENT"))
    idle = sum(1 for p in projects if p["category"] in ("IDLE", "ARCHIV") and not p["junction"])
    on_e = sum(1 for p in projects if p["junction"])

    print()
    print(f"  Projekte:  {active} aktiv | {idle} idle/archiv | {on_e} auf E:")
    print(f"  Caches:    {fmt(total_cache)} loeschbar")

    c_drive = drives.get(cfg["ssd_drive"])
    if c_drive and c_drive["pct"] >= cfg["warn_pct"]:
        print()
        print(f"  ! C: bei {c_drive['pct']}% — nutze 'doctor' fuer Empfehlungen")

    print()
    print("  Befehle:")
    print("    doctor         Volle Analyse + Empfehlungen")
    print("    clean          Safe Caches leeren")
    print("    deep-clean     Aggressive Bereinigung")
    print("    archive        Idle Projekte -> E:")
    print("    scan           Voller Disk-Scan")
    print("    activity       Projekt-Aktivitaet")
    print("    history        Speicher-Trend")
    print()
    print("  Optimierung:")
    print("    duplicates     Duplikat-Dateien finden")
    print("    big-files      Groesste Einzeldateien")
    print("    docker-prune   Docker analysieren")
    print("    git-gc         Git-Repos optimieren")
    print("    win-cleanup    Windows Systembereinigung")
    print("    startup        Autostart + RAM-Fresser")
    print("    wsl-compact    WSL2 vhdx komprimieren")
    print("    python-cleanup Pyenv-Versionen pruefen")
    print("    perf           CPU/RAM/Disk Performance")
    print()
    print("  System:")
    print("    auto           Automatisch handeln")
    print("    install        Als Scheduled Task (alle 2h)")
    print()

    save_snapshot(drives, total_cache, 0, "dashboard")


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════

def main():
    cfg = load_config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dashboard"

    commands = {
        "dashboard": lambda: do_dashboard(cfg),
        "doctor": lambda: do_doctor(cfg),
        "clean": lambda: do_clean(include_deep=False),
        "deep-clean": lambda: do_clean(include_deep=True),
        "archive": lambda: do_archive(cfg),
        "scan": do_scan,
        "activity": lambda: do_activity(cfg),
        "history": do_history,
        "auto": lambda: do_auto(cfg),
        "install": lambda: do_install(cfg),
        "uninstall": do_uninstall,
        # Approval Pipeline
        "execute-approved": lambda: do_execute_approved(cfg),
        # Optimierungs-Tools
        "duplicates": lambda: do_duplicates(cfg),
        "big-files": do_big_files,
        "docker-prune": do_docker_prune,
        "git-gc": lambda: do_git_gc(cfg),
        "win-cleanup": do_win_cleanup,
        "startup": do_startup,
        "wsl-compact": do_wsl_compact,
        "python-cleanup": do_python_cleanup,
        "perf": do_perf,
    }

    if cmd in ("--help", "-h", "help"):
        print(__doc__)
        return

    handler = commands.get(cmd)
    if handler:
        handler()
    else:
        print(f"  Unbekannt: '{cmd}'")
        print(f"  Verfuegbar: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()