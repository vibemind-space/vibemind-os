#Requires -Version 5.1
<#
.SYNOPSIS
    Startet das Desktop-Streaming-System mit Auto-Restart
.DESCRIPTION
    Startet Desktop-Client und Backend-Services.
    Überwacht die Prozesse und startet sie bei Absturz automatisch neu.
.NOTES
    Version: 1.0
    Autor: TRAE Unity AI Platform
#>

param(
    [switch]$NoBackend,      # Nur Desktop-Client starten
    [switch]$NoClient,       # Nur Backend starten
    [switch]$Debug,          # Debug-Modus
    [int]$RestartDelay = 5   # Sekunden zwischen Neustarts
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host @"
╔══════════════════════════════════════════════════════════════╗
║         TRAE Desktop Streaming - Startup Script              ║
║                   Version 1.0                                ║
╚══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan

# Konfiguration
$Config = @{
    DesktopClientPath = "$ProjectRoot\desktop-client\dual_screen_capture_client.py"
    BackendPath = "$ProjectRoot\backend\autogen_service\api_server.py"
    LogDir = "$ProjectRoot\logs"
    PythonCmd = "python"
}

# Log-Verzeichnis erstellen
if (-not (Test-Path $Config.LogDir)) {
    New-Item -ItemType Directory -Path $Config.LogDir -Force | Out-Null
}

$LogFile = "$($Config.LogDir)\streaming_$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] [$Level] $Message"
    Write-Host $LogMessage -ForegroundColor $(switch ($Level) {
        "ERROR" { "Red" }
        "WARN"  { "Yellow" }
        "OK"    { "Green" }
        default { "White" }
    })
    Add-Content -Path $LogFile -Value $LogMessage
}

function Test-PythonAvailable {
    try {
        $version = & python --version 2>&1
        Write-Log "Python gefunden: $version" "OK"
        return $true
    } catch {
        Write-Log "Python nicht gefunden! Bitte installieren Sie Python 3.8+" "ERROR"
        return $false
    }
}

function Start-DesktopClient {
    Write-Log "Starte Desktop-Client..." "INFO"
    
    $args = @(
        $Config.DesktopClientPath,
        "--fps", "10",
        "--quality", "75"
    )
    
    if ($Debug) {
        $args += "--debug"
    }
    
    $process = Start-Process -FilePath $Config.PythonCmd `
        -ArgumentList $args `
        -WorkingDirectory "$ProjectRoot\desktop-client" `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput "$($Config.LogDir)\desktop_client_stdout.log" `
        -RedirectStandardError "$($Config.LogDir)\desktop_client_stderr.log"
    
    Write-Log "Desktop-Client gestartet (PID: $($process.Id))" "OK"
    return $process
}

function Start-Backend {
    Write-Log "Starte Backend-Server..." "INFO"
    
    $process = Start-Process -FilePath $Config.PythonCmd `
        -ArgumentList @($Config.BackendPath) `
        -WorkingDirectory "$ProjectRoot\backend\autogen_service" `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput "$($Config.LogDir)\backend_stdout.log" `
        -RedirectStandardError "$($Config.LogDir)\backend_stderr.log"
    
    Write-Log "Backend-Server gestartet (PID: $($process.Id))" "OK"
    return $process
}

function Watch-Processes {
    param(
        [System.Diagnostics.Process]$ClientProcess,
        [System.Diagnostics.Process]$BackendProcess
    )
    
    $running = $true
    Write-Log "Überwache Prozesse... (Drücken Sie Ctrl+C zum Beenden)" "INFO"
    
    try {
        while ($running) {
            Start-Sleep -Seconds 5
            
            # Prüfe Desktop-Client
            if ($ClientProcess -and $ClientProcess.HasExited) {
                Write-Log "Desktop-Client beendet (Exit Code: $($ClientProcess.ExitCode)) - Neustart in $RestartDelay Sekunden..." "WARN"
                Start-Sleep -Seconds $RestartDelay
                $ClientProcess = Start-DesktopClient
            }
            
            # Prüfe Backend
            if ($BackendProcess -and $BackendProcess.HasExited) {
                Write-Log "Backend beendet (Exit Code: $($BackendProcess.ExitCode)) - Neustart in $RestartDelay Sekunden..." "WARN"
                Start-Sleep -Seconds $RestartDelay
                $BackendProcess = Start-Backend
            }
        }
    } catch {
        Write-Log "Überwachung beendet: $_" "WARN"
    }
}

# Hauptlogik
Write-Log "Projektverzeichnis: $ProjectRoot"
Write-Log "Log-Datei: $LogFile"

if (-not (Test-PythonAvailable)) {
    exit 1
}

$clientProcess = $null
$backendProcess = $null

try {
    # Desktop-Client starten
    if (-not $NoClient) {
        if (Test-Path $Config.DesktopClientPath) {
            $clientProcess = Start-DesktopClient
        } else {
            Write-Log "Desktop-Client nicht gefunden: $($Config.DesktopClientPath)" "ERROR"
        }
    }
    
    # Backend starten (optional)
    if (-not $NoBackend) {
        if (Test-Path $Config.BackendPath) {
            $backendProcess = Start-Backend
        } else {
            Write-Log "Backend nicht gefunden: $($Config.BackendPath) - Überspringe" "WARN"
        }
    }
    
    # Prozesse überwachen
    if ($clientProcess -or $backendProcess) {
        Watch-Processes -ClientProcess $clientProcess -BackendProcess $backendProcess
    }
    
} finally {
    # Cleanup bei Beendigung
    Write-Log "Beende alle Prozesse..." "INFO"
    
    if ($clientProcess -and -not $clientProcess.HasExited) {
        Stop-Process -Id $clientProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Log "Desktop-Client beendet" "INFO"
    }
    
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Log "Backend beendet" "INFO"
    }
    
    Write-Log "Alle Prozesse beendet" "OK"
}