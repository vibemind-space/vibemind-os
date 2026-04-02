#Requires -Version 5.1
<#
.SYNOPSIS
    Richtet den Desktop-Streaming-Client für Windows-Autostart ein
.DESCRIPTION
    Erstellt eine Verknüpfung im Windows Autostart-Ordner oder entfernt diese.
.PARAMETER Remove
    Entfernt den Autostart-Eintrag
.EXAMPLE
    .\setup-autostart.ps1           # Aktiviert Autostart
    .\setup-autostart.ps1 -Remove   # Deaktiviert Autostart
#>

param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

# Pfade definieren
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartupFolder = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupFolder "TRAE Desktop Streaming.lnk"
$TargetScript = Join-Path $ProjectRoot "scripts\start-desktop-streaming.ps1"
$WorkingDir = $ProjectRoot

Write-Host @"
╔══════════════════════════════════════════════════════════════╗
║      TRAE Desktop Streaming - Autostart Setup                ║
╚══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan

Write-Host "Autostart-Ordner: $StartupFolder" -ForegroundColor Gray
Write-Host "Projektverzeichnis: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

if ($Remove) {
    # Autostart entfernen
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
        Write-Host "✅ Autostart-Eintrag wurde entfernt!" -ForegroundColor Green
        Write-Host "   Der Desktop-Client startet nicht mehr automatisch." -ForegroundColor Yellow
    } else {
        Write-Host "⚠️ Kein Autostart-Eintrag gefunden." -ForegroundColor Yellow
    }
} else {
    # Prüfe ob Skript existiert
    if (-not (Test-Path $TargetScript)) {
        Write-Host "❌ FEHLER: Start-Skript nicht gefunden: $TargetScript" -ForegroundColor Red
        exit 1
    }
    
    # Erstelle Verknüpfung
    try {
        $WScriptShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
        
        # Starte PowerShell mit dem Skript
        $Shortcut.TargetPath = "powershell.exe"
        $Shortcut.Arguments = "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$TargetScript`" -NoBackend"
        $Shortcut.WorkingDirectory = $WorkingDir
        $Shortcut.Description = "TRAE Desktop Streaming Client"
        $Shortcut.IconLocation = "powershell.exe,0"
        $Shortcut.WindowStyle = 7  # Minimiert
        $Shortcut.Save()
        
        Write-Host "✅ Autostart-Eintrag wurde erstellt!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Der Desktop-Streaming-Client startet jetzt automatisch" -ForegroundColor Yellow
        Write-Host "beim Windows-Start (versteckt im Hintergrund)." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Verknüpfung: $ShortcutPath" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Zum Deaktivieren: .\setup-autostart.ps1 -Remove" -ForegroundColor Cyan
        
    } catch {
        Write-Host "❌ FEHLER beim Erstellen der Verknüpfung: $_" -ForegroundColor Red
        exit 1
    }
    
    # Optional: Auch Task Scheduler für robusteren Autostart
    Write-Host ""
    Write-Host "Möchten Sie zusätzlich einen Windows Task Scheduler Eintrag erstellen?" -ForegroundColor Cyan
    Write-Host "(Dieser ist robuster und startet auch mit Administratorrechten neu)" -ForegroundColor Gray
    $response = Read-Host "Eingabe: [J]a / [N]ein"
    
    if ($response -match '^[Jj]') {
        try {
            $TaskName = "TRAE Desktop Streaming"
            $TaskPath = "\TRAE\"
            
            # Lösche existierenden Task falls vorhanden
            Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false -ErrorAction SilentlyContinue
            
            # Erstelle neuen Task
            $Action = New-ScheduledTaskAction `
                -Execute "powershell.exe" `
                -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$TargetScript`" -NoBackend" `
                -WorkingDirectory $WorkingDir
            
            $Trigger = New-ScheduledTaskTrigger -AtLogOn
            
            $Settings = New-ScheduledTaskSettingsSet `
                -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries `
                -StartWhenAvailable `
                -RestartCount 3 `
                -RestartInterval (New-TimeSpan -Minutes 1)
            
            $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
            
            Register-ScheduledTask `
                -TaskName $TaskName `
                -TaskPath $TaskPath `
                -Action $Action `
                -Trigger $Trigger `
                -Settings $Settings `
                -Principal $Principal `
                -Description "Startet den TRAE Desktop Streaming Client automatisch bei Anmeldung" | Out-Null
            
            Write-Host ""
            Write-Host "✅ Task Scheduler Eintrag erstellt!" -ForegroundColor Green
            Write-Host "   Task: $TaskPath$TaskName" -ForegroundColor Gray
            
        } catch {
            Write-Host "⚠️ Task Scheduler Eintrag konnte nicht erstellt werden: $_" -ForegroundColor Yellow
            Write-Host "   Der Autostart über die Verknüpfung funktioniert aber trotzdem." -ForegroundColor Gray
        }
    }
}

Write-Host ""
Write-Host "Setup abgeschlossen!" -ForegroundColor Green