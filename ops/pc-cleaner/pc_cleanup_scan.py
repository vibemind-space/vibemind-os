"""Quick PC cleanup scan — safe, read-only analysis."""
import os


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


def fmt(b):
    if b > 1024**3:
        return f"{b / 1024**3:.1f} GB"
    if b > 1024**2:
        return f"{b / 1024**2:.0f} MB"
    return f"{b / 1024:.0f} KB"


def main():
    temp = os.environ.get("TEMP", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    home = os.path.expanduser("~")

    programdata = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    windir = os.environ.get("WINDIR", r"C:\Windows")

    targets = [
        (temp, "Windows Temp", True),
        (os.path.join(localappdata, "Temp"), "User Temp", True),
        (os.path.join(localappdata, "Microsoft", "Windows", "INetCache"), "IE/Edge Cache", True),
        # Python toolchain caches
        (os.path.join(localappdata, "pip", "cache"), "pip Cache", True),
        (os.path.join(localappdata, "uv", "cache"), "uv Cache", True),
        # Node toolchain caches
        (os.path.join(localappdata, "npm-cache"), "npm Cache", True),
        (os.path.join(appdata, "npm-cache"), "npm Cache (Roaming)", True),
        (os.path.join(localappdata, "pnpm", "store"), "pnpm Store", True),
        (os.path.join(localappdata, "yarn", "Cache"), "Yarn Cache", True),
        (os.path.join(localappdata, "NuGet", "Cache"), "NuGet Cache", True),
        # Rust toolchain
        (os.path.join(home, ".cargo", "registry", "cache"), "Cargo Registry Cache", True),
        (os.path.join(home, ".cargo", "registry", "src"), "Cargo Registry Src", True),
        # Browser test runners
        (os.path.join(localappdata, "ms-playwright"), "Playwright Browsers", True),
        # Browsers
        (os.path.join(localappdata, "Google", "Chrome", "User Data", "Default", "Cache"), "Chrome Cache", True),
        (os.path.join(localappdata, "Google", "Chrome", "User Data", "Default", "Code Cache"), "Chrome Code Cache", True),
        (os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default", "Cache"), "Edge Cache", True),
        (os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default", "Code Cache"), "Edge Code Cache", True),
        # Generic / pyenv / VSCode
        (os.path.join(home, ".cache"), ".cache", True),
        (os.path.join(home, ".pyenv", "pyenv-win", "install_cache"), "pyenv Install Cache", True),
        (os.path.join(localappdata, "CrashDumps"), "Crash Dumps", True),
        (os.path.join(home, "AppData", "Local", "Temp", "vscode-stable-user-x64"), "VSCode Update Cache", True),
        (os.path.join(localappdata, "Microsoft", "Windows", "Explorer"), "Thumbnail Cache", True),
        # Windows system-level remnants (admin recommended)
        (os.path.join(windir, "SoftwareDistribution", "Download"), "Windows Update Downloads", True),
        (os.path.join(windir, "Logs", "CBS"), "CBS Logs", True),
        (os.path.join(programdata, "Microsoft", "Windows", "WER", "ReportQueue"), "WER ReportQueue", True),
        (os.path.join(programdata, "Microsoft", "Windows", "WER", "ReportArchive"), "WER ReportArchive", True),
        (os.path.join(windir, "Installer", "$PatchCache$"), "Windows Patch Cache", True),
        # Risky / data-bearing
        (os.path.join(localappdata, "Docker", "wsl"), "Docker WSL Data", False),
        (os.path.join(localappdata, "Packages"), "UWP App Packages", False),
        (os.path.join(home, "Downloads"), "Downloads", False),
        # Heavy hitters (opt-in only — list shown for awareness)
        (os.path.join(home, ".ollama", "models"), "Ollama Models (opt-in)", False),
        (os.path.join(home, ".android", "avd"), "Android AVDs (opt-in)", False),
        (os.path.join(home, ".pyenv", "pyenv-win", "versions"), "pyenv Python Versions (opt-in)", False),
    ]

    # Hibernate file — special: not a folder, single sparse file
    hiber = r"C:\hiberfil.sys"
    hiber_size = 0
    if os.path.exists(hiber):
        try:
            hiber_size = os.path.getsize(hiber)
        except OSError:
            pass

    print()
    print("=" * 60)
    print("  PC CLEANUP ANALYSE (read-only, loescht nichts)")
    print("=" * 60)
    print()
    print(f"  {'Ordner':<42} {'Groesse':>10} {'Safe?':>6}")
    print("  " + "-" * 60)

    total_safe = 0
    total_risky = 0
    cleanable = []

    for path, name, safe in targets:
        if os.path.exists(path):
            size = dir_size(path)
            if size > 1024 * 1024:  # >1MB
                tag = "JA" if safe else "NEIN"
                print(f"  {name:<42} {fmt(size):>10} {tag:>6}")
                if safe:
                    total_safe += size
                    cleanable.append((path, name, size))
                else:
                    total_risky += size

    print()
    print(f"  Sicher loeschbar:     {fmt(total_safe)}")
    print(f"  Nicht antasten:       {fmt(total_risky)}")
    print()

    if cleanable:
        print("  Top 5 zum Aufraeumen:")
        cleanable.sort(key=lambda x: x[2], reverse=True)
        for path, name, size in cleanable[:5]:
            print(f"    {fmt(size):>10}  {name}")
            print(f"              {path}")

    if hiber_size > 0:
        print()
        print(f"  HIBERNATE-DATEI:        {fmt(hiber_size):>10}  C:\\hiberfil.sys")
        print(f"     -> Befehl (Admin):  powercfg /h off   (deaktiviert Ruhezustand, gibt RAM-grossen Block frei)")

    print()
    print("  HEAVY HITTERS (opt-in, eigene CLI verwenden):")
    print("    Ollama Models    -> 'ollama list' / 'ollama rm <name>'")
    print("    pyenv Versionen  -> 'pyenv versions' / 'pyenv uninstall <ver>'")
    print("    Android AVDs     -> 'avdmanager list avd' / 'avdmanager delete avd -n <name>'")

    print()
    return cleanable


if __name__ == "__main__":
    cleanable = main()
    if cleanable:
        print("  Soll ich diese Ordner leeren? (Starte pc_cleanup_nochrome.py)")
