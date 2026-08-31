"""PC Cleanup — delete safe cache/temp directories."""
import os
import shutil


def fmt(b):
    if b > 1024**3:
        return f"{b / 1024**3:.1f} GB"
    if b > 1024**2:
        return f"{b / 1024**2:.0f} MB"
    return f"{b / 1024:.0f} KB"


def clean_dir(path):
    freed = 0
    errors = 0
    try:
        items = os.listdir(path)
    except (PermissionError, OSError):
        return 0, 1
    for item in items:
        fp = os.path.join(path, item)
        try:
            if os.path.isfile(fp) or os.path.islink(fp):
                size = os.path.getsize(fp)
                os.remove(fp)
                freed += size
            elif os.path.isdir(fp):
                size = 0
                for r, d, files in os.walk(fp):
                    for f in files:
                        try:
                            size += os.path.getsize(os.path.join(r, f))
                        except (PermissionError, OSError):
                            pass
                shutil.rmtree(fp, ignore_errors=True)
                freed += size
        except (PermissionError, OSError):
            errors += 1
    return freed, errors


def main():
    localappdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    windir = os.environ.get("WINDIR", r"C:\Windows")
    home = os.path.expanduser("~")

    targets = [
        # User caches
        (os.path.join(localappdata, "Temp"), "User Temp"),
        (os.path.join(localappdata, "pip", "cache"), "pip Cache"),
        (os.path.join(localappdata, "uv", "cache"), "uv Cache"),
        (os.path.join(localappdata, "npm-cache"), "npm Cache"),
        (os.path.join(appdata, "npm-cache"), "npm Cache (Roaming)"),
        (os.path.join(localappdata, "pnpm", "store"), "pnpm Store"),
        (os.path.join(localappdata, "yarn", "Cache"), "Yarn Cache"),
        (os.path.join(localappdata, "NuGet", "Cache"), "NuGet Cache"),
        (os.path.join(home, ".cargo", "registry", "cache"), "Cargo Registry Cache"),
        (os.path.join(home, ".cargo", "registry", "src"), "Cargo Registry Src"),
        (os.path.join(localappdata, "ms-playwright"), "Playwright Browsers"),
        # Browsers (Chrome included here — assumes browser not running)
        (os.path.join(localappdata, "Google", "Chrome", "User Data", "Default", "Cache"), "Chrome Cache"),
        (os.path.join(localappdata, "Google", "Chrome", "User Data", "Default", "Code Cache"), "Chrome Code Cache"),
        (os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default", "Cache"), "Edge Cache"),
        (os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default", "Code Cache"), "Edge Code Cache"),
        # Misc
        (os.path.join(home, ".cache"), ".cache"),
        (os.path.join(home, ".pyenv", "pyenv-win", "install_cache"), "pyenv Cache"),
        (os.path.join(localappdata, "CrashDumps"), "Crash Dumps"),
        (os.path.join(localappdata, "Temp", "vscode-stable-user-x64"), "VSCode Update Cache"),
        (os.path.join(localappdata, "Microsoft", "Windows", "Explorer"), "Thumbnail Cache"),
        # Windows system (admin recommended)
        (os.path.join(windir, "SoftwareDistribution", "Download"), "Windows Update Downloads"),
        (os.path.join(windir, "Logs", "CBS"), "CBS Logs"),
        (os.path.join(programdata, "Microsoft", "Windows", "WER", "ReportQueue"), "WER ReportQueue"),
        (os.path.join(programdata, "Microsoft", "Windows", "WER", "ReportArchive"), "WER ReportArchive"),
    ]

    print()
    print("  Cleaning...")
    total_freed = 0
    admin_failed = []

    for path, name in targets:
        if os.path.exists(path):
            freed, errors = clean_dir(path)
            total_freed += freed
            err_str = f" ({errors} locked)" if errors else ""
            print(f"    {name:<35} {fmt(freed):>10}{err_str}")
            if errors > 0 and freed == 0 and ("Windows" in path or "ProgramData" in path):
                admin_failed.append(name)

    print()
    print(f"  TOTAL FREED: {fmt(total_freed)}")
    if admin_failed:
        print()
        print("  HINWEIS: Folgende Ordner brauchen Admin (uebersprungen):")
        for n in admin_failed:
            print(f"     - {n}")
    print()
    print("  Tipp: 'powercfg /h off' (Admin) entfernt hiberfil.sys (~RAM-Groesse).")
    print()


if __name__ == "__main__":
    main()
