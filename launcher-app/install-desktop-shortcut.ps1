<#
.SYNOPSIS
    Creates a Desktop shortcut to the released VibeMind Launcher .exe.
.DESCRIPTION
    Run after `npm run build` finishes. The bundler writes the exe to
    src-tauri\target\release\VibeMind Launcher.exe. This script creates
    a .lnk on the user's Desktop pointing at it, with the icon set to
    icon.ico from the bundle.

    Idempotent: overwrites an existing shortcut. -Remove deletes it.
.PARAMETER Remove
    Remove the existing Desktop shortcut.
.EXAMPLE
    .\install-desktop-shortcut.ps1
    .\install-desktop-shortcut.ps1 -Remove
#>
param([switch]$Remove)

$ErrorActionPreference = 'Stop'

$thisDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
# Tauri names the exe after the Cargo package (vibemind-launcher), NOT
# after productName in tauri.conf.json — checked empirically 2026-05-20.
$exePath   = Join-Path $thisDir 'src-tauri\target\release\vibemind-launcher.exe'
$iconPath  = Join-Path $thisDir 'src-tauri\icons\icon.ico'
$desktop   = [Environment]::GetFolderPath('Desktop')
$linkPath  = Join-Path $desktop 'VibeMind.lnk'

if ($Remove) {
    if (Test-Path $linkPath) {
        Remove-Item $linkPath -Force
        Write-Host "Removed: $linkPath" -ForegroundColor Yellow
    } else {
        Write-Host "Nothing to remove ($linkPath does not exist)." -ForegroundColor Gray
    }
    return
}

if (-not (Test-Path $exePath)) {
    Write-Host "[ERROR] exe not found at: $exePath" -ForegroundColor Red
    Write-Host "        Run 'npm run build' (or 'cargo tauri build') first." -ForegroundColor Gray
    exit 1
}

# Repo root (3 levels up: launcher-app -> vibemind-os -> Vibemind_V1)
$repoRoot = Split-Path -Parent (Split-Path -Parent $thisDir)

$wshell = New-Object -ComObject WScript.Shell
$lnk = $wshell.CreateShortcut($linkPath)
$lnk.TargetPath       = $exePath
$lnk.WorkingDirectory = $repoRoot
$lnk.IconLocation     = "$iconPath, 0"
$lnk.Description      = 'VibeMind Launcher — start / stop the local stack'
$lnk.Save()

Write-Host "Created: $linkPath" -ForegroundColor Green
Write-Host "  Target  : $exePath" -ForegroundColor Gray
Write-Host "  WorkDir : $repoRoot" -ForegroundColor Gray
Write-Host "  Icon    : $iconPath" -ForegroundColor Gray
