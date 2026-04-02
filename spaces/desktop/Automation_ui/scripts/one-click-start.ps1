# ============================================================================
# TRAE Unity AI Platform - One-Click Start Script
# ============================================================================
#
# Starts all services required for the full application:
# 1. Frontend (Vite dev server)
# 2. Desktop Client (dual screen capture)
# 3. OCR Backend (EasyOCR/Tesseract)
# 4. AutoGen API (AI analysis)
# 5. MoireServer (UI Detection)
# 6. Electron App (optional, with -Electron flag)
#
# Usage:
#   .\scripts\one-click-start.ps1              # Web mode (opens browser)
#   .\scripts\one-click-start.ps1 -Electron    # Electron mode (native app)
#   .\scripts\one-click-start.ps1 -NoBrowser   # No auto-open
# ============================================================================

param(
    [switch]$SkipDesktopClient = $false,
    [switch]$SkipOCRBackend = $false,
    [switch]$SkipAutoGenAPI = $false,
    [switch]$SkipMoireServer = $false,
    [switch]$Electron = $false,
    [switch]$NoBrowser = $false,
    [int]$FrontendPort = 3003,
    [int]$OCRPort = 8007,
    [int]$AutoGenPort = 8008,
    [int]$MoirePort = 8766
)

# Colors for console output
$colors = @{
    Success = "Green"
    Warning = "Yellow"
    Error = "Red"
    Info = "Cyan"
    Header = "Magenta"
}

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
Set-Location $ProjectRoot

function Write-Status {
    param([string]$Message, [string]$Type = "Info")
    $color = $colors[$Type]
    $prefix = switch ($Type) {
        "Success" { "[OK]" }
        "Warning" { "[WARN]" }
        "Error" { "[ERR]" }
        "Info" { "[INFO]" }
        "Header" { "[>>]" }
        default { "*" }
    }
    Write-Host "$prefix $Message" -ForegroundColor $color
}

# ============================================================================
# HEADER
# ============================================================================
Write-Host ""
Write-Host "=======================================================================" -ForegroundColor $colors.Header
Write-Host "                                                                       " -ForegroundColor $colors.Header
Write-Host "     TRAE Unity AI Platform - One-Click Start                          " -ForegroundColor $colors.Header
Write-Host "     Desktop Automation with Live Streaming & AI Analysis              " -ForegroundColor $colors.Header
Write-Host "                                                                       " -ForegroundColor $colors.Header
Write-Host "=======================================================================" -ForegroundColor $colors.Header
Write-Host ""

# ============================================================================
# SYSTEM CHECK
# ============================================================================
Write-Status "Checking system requirements..." "Info"

# Check Node.js
try {
    $nodeVersion = & node --version 2>$null
    Write-Status "Node.js: $nodeVersion" "Success"
} catch {
    Write-Status "Node.js not found! Please install Node.js" "Error"
    exit 1
}

# Check Python
try {
    $pythonVersion = & python --version 2>$null
    Write-Status "Python: $pythonVersion" "Success"
} catch {
    Write-Status "Python not found! Please install Python 3.9+" "Error"
    exit 1
}

# Check npm dependencies
if (-not (Test-Path "node_modules")) {
    Write-Status "Installing npm dependencies..." "Info"
    npm install --silent
}

Write-Host ""

# ============================================================================
# STOP EXISTING PROCESSES
# ============================================================================
Write-Status "Stopping any existing processes..." "Info"

# Kill existing processes on our ports
$portsToCheck = @($FrontendPort, $OCRPort, $AutoGenPort)
foreach ($port in $portsToCheck) {
    $existingProcess = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | Get-Unique
    if ($existingProcess) {
        Write-Status "Stopping process on port $port..." "Warning"
        Stop-Process -Id $existingProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

Write-Host ""

# ============================================================================
# START SERVICES
# ============================================================================
$processes = @()

# 1. Start Frontend
Write-Status "Starting Frontend (Vite dev server on port $FrontendPort)..." "Header"
$frontendJob = Start-Job -Name "Frontend" -ScriptBlock {
    param($ProjectRoot, $Port)
    Set-Location $ProjectRoot
    $env:PORT = $Port
    npm run dev 2>&1
} -ArgumentList $ProjectRoot, $FrontendPort
$processes += @{ Name = "Frontend"; Job = $frontendJob; Port = $FrontendPort }
Write-Status "Frontend started" "Success"

Start-Sleep -Seconds 3

# 2. Start OCR Backend
if (-not $SkipOCRBackend) {
    Write-Status "Starting OCR Backend (FastAPI on port $OCRPort)..." "Header"
    $ocrJob = Start-Job -Name "OCRBackend" -ScriptBlock {
        param($ProjectRoot, $Port)
        Set-Location $ProjectRoot
        & python "backend/ocr_backend/main.py" --port $Port 2>&1
    } -ArgumentList $ProjectRoot, $OCRPort
    $processes += @{ Name = "OCR Backend"; Job = $ocrJob; Port = $OCRPort }
    Write-Status "OCR Backend started" "Success"
    Start-Sleep -Seconds 2
}

# 3. Start AutoGen API
if (-not $SkipAutoGenAPI) {
    Write-Status "Starting AutoGen API (FastAPI on port $AutoGenPort)..." "Header"
    $autoGenJob = Start-Job -Name "AutoGenAPI" -ScriptBlock {
        param($ProjectRoot, $Port)
        Set-Location $ProjectRoot
        Set-Location "backend/autogen_service"
        & python "api_server.py" --port $Port 2>&1
    } -ArgumentList $ProjectRoot, $AutoGenPort
    $processes += @{ Name = "AutoGen API"; Job = $autoGenJob; Port = $AutoGenPort }
    Write-Status "AutoGen API started" "Success"
    Start-Sleep -Seconds 2
}

# 4. Start Desktop Client
if (-not $SkipDesktopClient) {
    Write-Status "Starting Desktop Client (Dual Screen Capture)..." "Header"
    $desktopJob = Start-Job -Name "DesktopClient" -ScriptBlock {
        param($ProjectRoot)
        Set-Location $ProjectRoot
        & python "desktop-client/dual_screen_capture_client.py" 2>&1
    } -ArgumentList $ProjectRoot
    $processes += @{ Name = "Desktop Client"; Job = $desktopJob; Port = 0 }
    Write-Status "Desktop Client started" "Success"
}

# 5. Start MoireServer (UI Detection)
if (-not $SkipMoireServer) {
    Write-Status "Starting MoireServer (UI Detection on port $MoirePort)..." "Header"
    $moireJob = Start-Job -Name "MoireServer" -ScriptBlock {
        param($ProjectRoot, $Port)
        Set-Location "$ProjectRoot\moire_server"
        npm run dev 2>&1
    } -ArgumentList $ProjectRoot, $MoirePort
    $processes += @{ Name = "MoireServer"; Job = $moireJob; Port = $MoirePort }
    Write-Status "MoireServer started" "Success"
    Start-Sleep -Seconds 2
}

Write-Host ""
Start-Sleep -Seconds 3

# ============================================================================
# STATUS SUMMARY
# ============================================================================
Write-Host "=======================================================================" -ForegroundColor $colors.Success
Write-Host "                     🎉 ALL SERVICES STARTED!                          " -ForegroundColor $colors.Success
Write-Host "=======================================================================" -ForegroundColor $colors.Success
Write-Host ""

Write-Host "Service Status:" -ForegroundColor $colors.Info
Write-Host "  * Frontend:       http://localhost:$FrontendPort" -ForegroundColor $colors.Success
if (-not $SkipOCRBackend) {
    Write-Host "  * OCR Backend:    http://localhost:$OCRPort" -ForegroundColor $colors.Success
}
if (-not $SkipAutoGenAPI) {
    Write-Host "  * AutoGen API:    http://localhost:$AutoGenPort" -ForegroundColor $colors.Success
}
if (-not $SkipMoireServer) {
    Write-Host "  * MoireServer:    http://localhost:$MoirePort (UI Detection)" -ForegroundColor $colors.Success
}
if (-not $SkipDesktopClient) {
    Write-Host "  * Desktop Client: Running (Dual Screen Capture)" -ForegroundColor $colors.Success
}

Write-Host ""
Write-Host "Quick Links:" -ForegroundColor $colors.Info
Write-Host "  📺 Multi-Desktop Streams: http://localhost:$FrontendPort/" -ForegroundColor $colors.Info
Write-Host "  🖥️  Electron Automation:   http://localhost:$FrontendPort/electron" -ForegroundColor $colors.Info
Write-Host "  🤖 Intent Chat:           http://localhost:$FrontendPort/electron (Chat Panel)" -ForegroundColor $colors.Info

Write-Host ""

# Start Electron app or open browser
if ($Electron) {
    Write-Status "Starting Electron app..." "Header"
    $electronJob = Start-Job -Name "Electron" -ScriptBlock {
        param($ProjectRoot)
        Set-Location "$ProjectRoot\electron-app"
        npm start 2>&1
    } -ArgumentList $ProjectRoot
    $processes += @{ Name = "Electron"; Job = $electronJob; Port = 0 }
    Write-Status "Electron app started (auto-connects to stream)" "Success"
} elseif (-not $NoBrowser) {
    Write-Status "Opening browser..." "Info"
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:$FrontendPort/multi-desktop"
}

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor $colors.Warning
Write-Host "║  Press Ctrl+C to stop all services                                    ║" -ForegroundColor $colors.Warning
Write-Host "=======================================================================" -ForegroundColor $colors.Warning
Write-Host ""

# ============================================================================
# MONITORING LOOP
# ============================================================================
try {
    $lastStatusCheck = Get-Date
    $statusInterval = 30 # seconds
    
    while ($true) {
        Start-Sleep -Seconds 2
        
        # Check job status
        foreach ($proc in $processes) {
            $job = $proc.Job
            if ($job.State -eq "Failed") {
                Write-Status "$($proc.Name) has stopped unexpectedly!" "Error"
                $output = Receive-Job -Job $job
                Write-Host $output -ForegroundColor $colors.Error
            }
        }
        
        # Periodic status check
        $now = Get-Date
        if (($now - $lastStatusCheck).TotalSeconds -gt $statusInterval) {
            $runningCount = ($processes | Where-Object { $_.Job.State -eq "Running" }).Count
            Write-Status "Services running: $runningCount/$($processes.Count)" "Info"
            $lastStatusCheck = $now
        }
    }
} finally {
    # Cleanup on exit
    Write-Host ""
    Write-Status "Shutting down all services..." "Warning"
    
    foreach ($proc in $processes) {
        Write-Status "Stopping $($proc.Name)..." "Info"
        Stop-Job -Job $proc.Job -ErrorAction SilentlyContinue
        Remove-Job -Job $proc.Job -Force -ErrorAction SilentlyContinue
    }
    
    Write-Status "All services stopped" "Success"
    Write-Host ""
}