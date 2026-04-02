#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Electron App Post-Install Script für Desktop-Streaming
    Wird automatisch nach der Electron-App-Installation ausgeführt

.DESCRIPTION
    Dieses Skript:
    1. Prüft/installiert Python
    2. Installiert Python-Dependencies
    3. Richtet den Desktop-Stream-Client als Windows-Service ein
    4. Konfiguriert Autostart

.PARAMETER InstallPath
    Installationspfad der Electron-App (Standard: $env:LOCALAPPDATA\YourAppName)

.PARAMETER Silent
    Führt Installation ohne Benutzer-Prompts aus
#>

param(
    [string]$InstallPath = "$env:LOCALAPPDATA\AutomationUI",
    [switch]$Silent = $false
)

# Konfiguration
$AppName = "AutomationUI Desktop Stream"
$DesktopClientFolder = "desktop-client"
$PythonMinVersion = "3.9"
$RequiredPackages = @("mss", "Pillow", "websockets")

# Logging
$LogFile = Join-Path $InstallPath "install.log"
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    if (-not $Silent) {
        switch ($Level) {
            "ERROR" { Write-Host $logMessage -ForegroundColor Red }
            "WARN"  { Write-Host $logMessage -ForegroundColor Yellow }
            "SUCCESS" { Write-Host $logMessage -ForegroundColor Green }
            default { Write-Host $logMessage }
        }
    }
    
    # Ensure log directory exists
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    Add-Content -Path $LogFile -Value $logMessage
}

# ============================================================================
# 1. Python Installation prüfen/durchführen
# ============================================================================
function Test-PythonInstallation {
    try {
        $pythonVersion = & python --version 2>&1
        if ($pythonVersion -match "Python (\d+\.\d+)") {
            $version = [version]$matches[1]
            $minVersion = [version]$PythonMinVersion
            return $version -ge $minVersion
        }
    } catch {
        return $false
    }
    return $false
}

function Install-Python {
    Write-Log "Python nicht gefunden oder zu alt. Installiere Python..."
    
    $pythonInstallerUrl = "https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe"
    $installerPath = Join-Path $env:TEMP "python-installer.exe"
    
    try {
        # Download Python Installer
        Write-Log "Lade Python-Installer herunter..."
        Invoke-WebRequest -Uri $pythonInstallerUrl -OutFile $installerPath -UseBasicParsing
        
        # Stille Installation
        Write-Log "Installiere Python (silent)..."
        $installArgs = @(
            "/quiet",
            "InstallAllUsers=0",
            "PrependPath=1",
            "Include_pip=1",
            "Include_test=0"
        )
        Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -NoNewWindow
        
        # PATH aktualisieren
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + 
                    [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        
        Write-Log "Python erfolgreich installiert" "SUCCESS"
        return $true
    } catch {
        Write-Log "Python-Installation fehlgeschlagen: $_" "ERROR"
        return $false
    } finally {
        if (Test-Path $installerPath) {
            Remove-Item $installerPath -Force
        }
    }
}

# ============================================================================
# 2. Python-Dependencies installieren
# ============================================================================
function Install-PythonDependencies {
    Write-Log "Installiere Python-Dependencies..."
    
    $desktopClientPath = Join-Path $InstallPath $DesktopClientFolder
    $requirementsFile = Join-Path $desktopClientPath "requirements.txt"
    
    try {
        if (Test-Path $requirementsFile) {
            & python -m pip install --upgrade pip --quiet
            & python -m pip install -r $requirementsFile --quiet
        } else {
            foreach ($package in $RequiredPackages) {
                Write-Log "Installiere $package..."
                & python -m pip install $package --quiet
            }
        }
        Write-Log "Python-Dependencies erfolgreich installiert" "SUCCESS"
        return $true
    } catch {
        Write-Log "Fehler bei der Installation der Dependencies: $_" "ERROR"
        return $false
    }
}

# ============================================================================
# 3. Desktop-Client als geplante Aufgabe einrichten
# ============================================================================
function Register-DesktopStreamTask {
    Write-Log "Richte Desktop-Stream als geplante Aufgabe ein..."
    
    $taskName = "AutomationUI_DesktopStream"
    $desktopClientPath = Join-Path $InstallPath $DesktopClientFolder
    $pythonScript = Join-Path $desktopClientPath "dual_screen_capture_client.py"
    
    # Prüfe ob Script existiert
    if (-not (Test-Path $pythonScript)) {
        Write-Log "Desktop-Client-Script nicht gefunden: $pythonScript" "ERROR"
        return $false
    }
    
    try {
        # Existierende Task entfernen
        $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($existingTask) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Log "Existierende Aufgabe entfernt"
        }
        
        # Python-Pfad ermitteln
        $pythonPath = (Get-Command python).Source
        
        # Action erstellen
        $action = New-ScheduledTaskAction `
            -Execute $pythonPath `
            -Argument "`"$pythonScript`" --fps 4 --quality 75" `
            -WorkingDirectory $desktopClientPath
        
        # Trigger: Bei Benutzeranmeldung
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        
        # Einstellungen
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -RestartInterval (New-TimeSpan -Minutes 1) `
            -RestartCount 999 `
            -ExecutionTimeLimit (New-TimeSpan -Days 365)
        
        # Principal (Benutzerkontext)
        $principal = New-ScheduledTaskPrincipal `
            -UserId $env:USERNAME `
            -LogonType Interactive `
            -RunLevel Limited
        
        # Task registrieren
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description "Startet den Desktop-Streaming-Client für AutomationUI" `
            -Force
        
        Write-Log "Geplante Aufgabe '$taskName' erfolgreich erstellt" "SUCCESS"
        return $true
    } catch {
        Write-Log "Fehler beim Erstellen der geplanten Aufgabe: $_" "ERROR"
        return $false
    }
}

# ============================================================================
# 4. Desktop-Client initial starten
# ============================================================================
function Start-DesktopStream {
    Write-Log "Starte Desktop-Stream-Client..."
    
    $taskName = "AutomationUI_DesktopStream"
    
    try {
        Start-ScheduledTask -TaskName $taskName
        Write-Log "Desktop-Stream gestartet" "SUCCESS"
        return $true
    } catch {
        Write-Log "Fehler beim Starten des Desktop-Streams: $_" "ERROR"
        return $false
    }
}

# ============================================================================
# 5. Konfigurationsdatei erstellen
# ============================================================================
function Create-ConfigFile {
    Write-Log "Erstelle Konfigurationsdatei..."
    
    $configPath = Join-Path $InstallPath "config.json"
    $config = @{
        installed = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        version = "1.0.0"
        streaming = @{
            fps = 4
            quality = 75
            autoStart = $true
        }
        supabase = @{
            url = if ($env:SUPABASE_WS_URL) { $env:SUPABASE_WS_URL } else { "ws://localhost:8007/ws/live-desktop" }
        }
    } | ConvertTo-Json -Depth 3
    
    try {
        Set-Content -Path $configPath -Value $config -Encoding UTF8
        Write-Log "Konfiguration gespeichert: $configPath" "SUCCESS"
        return $true
    } catch {
        Write-Log "Fehler beim Speichern der Konfiguration: $_" "ERROR"
        return $false
    }
}

# ============================================================================
# Hauptinstallation
# ============================================================================
function Main {
    Write-Log "=========================================="
    Write-Log "$AppName - Post-Install Setup"
    Write-Log "=========================================="
    Write-Log "Installationspfad: $InstallPath"
    
    $success = $true
    
    # Schritt 1: Python prüfen/installieren
    if (-not (Test-PythonInstallation)) {
        if (-not (Install-Python)) {
            Write-Log "KRITISCH: Python-Installation fehlgeschlagen" "ERROR"
            $success = $false
        }
    } else {
        $pythonVersion = & python --version 2>&1
        Write-Log "Python gefunden: $pythonVersion" "SUCCESS"
    }
    
    # Schritt 2: Dependencies installieren
    if ($success) {
        if (-not (Install-PythonDependencies)) {
            Write-Log "WARNUNG: Einige Dependencies konnten nicht installiert werden" "WARN"
        }
    }
    
    # Schritt 3: Geplante Aufgabe einrichten
    if ($success) {
        if (-not (Register-DesktopStreamTask)) {
            Write-Log "WARNUNG: Autostart konnte nicht eingerichtet werden" "WARN"
        }
    }
    
    # Schritt 4: Konfiguration erstellen
    if ($success) {
        Create-ConfigFile | Out-Null
    }
    
    # Schritt 5: Stream starten
    if ($success) {
        Start-DesktopStream | Out-Null
    }
    
    Write-Log "=========================================="
    if ($success) {
        Write-Log "Installation erfolgreich abgeschlossen!" "SUCCESS"
    } else {
        Write-Log "Installation mit Warnungen abgeschlossen" "WARN"
    }
    Write-Log "Log-Datei: $LogFile"
    Write-Log "=========================================="
    
    return $success
}

# Ausführen
$result = Main
exit $(if ($result) { 0 } else { 1 })