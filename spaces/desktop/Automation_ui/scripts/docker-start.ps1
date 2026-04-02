# =============================================================================
# TRAE Desktop Streaming - Docker Start Script (PowerShell)
# =============================================================================
# Startet alle Docker-Container und den Desktop-Client auf dem Host
# =============================================================================

param(
    [switch]$Build,
    [switch]$NoDesktop,
    [switch]$Attach,
    [switch]$Help
)

# ANSI Colors
$Green = "`e[32m"
$Yellow = "`e[33m"
$Red = "`e[31m"
$Blue = "`e[34m"
$Reset = "`e[0m"

function Write-Status($status, $message, $color = $Green) {
    Write-Host "${color}[$status]${Reset} $message"
}

function Show-Help {
    Write-Host ""
    Write-Host "TRAE Desktop Streaming - Docker Start Script"
    Write-Host ""
    Write-Host "Usage: .\docker-start.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Build       Rebuild Docker images before starting"
    Write-Host "  -NoDesktop   Don't start the Desktop Capture Client"
    Write-Host "  -Attach      Show container logs in console"
    Write-Host "  -Help        Show this help message"
    Write-Host ""
    exit 0
}

if ($Help) { Show-Help }

Write-Host ""
Write-Host "========================================"
Write-Host "  TRAE Desktop Streaming - Docker Setup"
Write-Host "========================================"
Write-Host ""

# Prüfe Docker
try {
    docker info 2>&1 | Out-Null
    Write-Status "OK" "Docker laeuft"
} catch {
    Write-Status "ERROR" "Docker ist nicht gestartet!" $Red
    Write-Host "        Bitte starten Sie Docker Desktop und versuchen Sie es erneut."
    exit 1
}

# Wechsle ins Projektverzeichnis
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# .env Setup
if (-not (Test-Path ".env")) {
    if (Test-Path "docker/.env.example") {
        Write-Status "SETUP" "Kopiere docker/.env.example nach .env" $Yellow
        Copy-Item "docker/.env.example" ".env"
    } else {
        Write-Status "WARN" "Keine .env Datei gefunden. Standard-Werte werden verwendet." $Yellow
    }
}

# Docker Container starten
Write-Host ""
Write-Status "DOCKER" "Starte Container..."
Write-Host ""

if ($Build) {
    Write-Status "DOCKER" "Baue Images neu..." $Yellow
    docker-compose build --no-cache
}

if ($Attach) {
    # Starte im Vordergrund in neuem Fenster
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "docker-compose up" -WorkingDirectory $ProjectRoot
    Start-Sleep -Seconds 5
} else {
    docker-compose up -d
}

# Warte auf Backend
Write-Host ""
Write-Status "WAIT" "Warte auf Backend-Bereitschaft..."

$maxRetries = 30
$retries = 0
$backendReady = $false

while ($retries -lt $maxRetries -and -not $backendReady) {
    $retries++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8007/api/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
        }
    } catch {
        Write-Host "        Warte auf Backend... ($retries/$maxRetries)"
        Start-Sleep -Seconds 2
    }
}

if ($backendReady) {
    Write-Status "OK" "Backend ist bereit!"
} else {
    Write-Status "WARN" "Backend ist nach $maxRetries Versuchen nicht bereit!" $Yellow
    Write-Host "        Pruefen Sie die Logs: docker-compose logs backend"
}

# Desktop-Client starten
if (-not $NoDesktop) {
    Write-Host ""
    Write-Status "HOST" "Starte Desktop Capture Client..."
    Write-Host "        (Laeuft auf dem HOST fuer Zugriff auf physische Monitore)"
    Write-Host ""
    
    # Prüfe Python
    try {
        python --version 2>&1 | Out-Null
    } catch {
        Write-Status "ERROR" "Python ist nicht installiert oder nicht im PATH!" $Red
        Write-Host "        Bitte installieren Sie Python 3.8+ und fuegen Sie es zum PATH hinzu."
        exit 1
    }
    
    # Prüfe Desktop-Client
    $desktopClientPath = Join-Path $ProjectRoot "desktop-client\dual_screen_capture_client.py"
    if (-not (Test-Path $desktopClientPath)) {
        Write-Status "ERROR" "Desktop-Client nicht gefunden: $desktopClientPath" $Red
        exit 1
    }
    
    # Starte Desktop-Client
    $desktopClientDir = Join-Path $ProjectRoot "desktop-client"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$desktopClientDir`" && python dual_screen_capture_client.py --server-url ws://localhost:8007/ws/live-desktop --backend-url http://localhost:8007/api/client" -WorkingDirectory $desktopClientDir
    
    Write-Status "OK" "Desktop-Client gestartet"
}

# Zusammenfassung
Write-Host ""
Write-Host "========================================"
Write-Host "  TRAE Desktop Streaming - Bereit!"
Write-Host "========================================"
Write-Host ""
Write-Host "  Frontend:       http://localhost:5173"
Write-Host "  Backend API:    http://localhost:8007"
Write-Host "  OCR Engine:     http://localhost:8008"
Write-Host "  Qdrant:         http://localhost:6333"
Write-Host ""
Write-Host "  Container-Logs: docker-compose logs -f"
Write-Host "  Stoppen:        docker-compose down"
Write-Host ""
Write-Host "========================================"
Write-Host ""

if (-not $Attach) {
    Write-Host "Druecken Sie eine beliebige Taste zum Beenden (Container laufen weiter)..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}