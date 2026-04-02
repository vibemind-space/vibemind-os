# TRAE Unity AI Platform - Startup Script with Auto Dual Monitor Support
# Part of the autonomous programmer project

param(
    [switch]$ShowLogs = $false,
    [switch]$SkipDesktopClient = $false,
    [int]$WebSocketPort = 8084,
    [int]$FrontendPort = 5174,
    [switch]$AutoStartMonitors = $true
)

# Ensure we operate from the project root regardless of where this script lives
# $PSScriptRoot points to the current script directory (scripts/)
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "🚀 Starting TRAE Unity AI Platform with Auto Dual Monitor Support" -ForegroundColor Green
Write-Host "WebSocket Port: $WebSocketPort" -ForegroundColor Yellow
Write-Host "Frontend Port: $FrontendPort" -ForegroundColor Yellow
Write-Host "Auto Start Monitors: $AutoStartMonitors" -ForegroundColor Yellow

# Detect monitor setup
Write-Host "🖥️  Detecting monitor configuration..." -ForegroundColor Cyan
try {
    Add-Type -AssemblyName System.Windows.Forms
    $screens = [System.Windows.Forms.Screen]::AllScreens
    $monitorCount = $screens.Count
    
    Write-Host "Detected $monitorCount monitor(s):" -ForegroundColor Green
    for ($i = 0; $i -lt $screens.Count; $i++) {
        $screen = $screens[$i]
        $isPrimary = if ($screen.Primary) { " (Primary)" } else { "" }
        Write-Host "  Monitor $($i + 1): $($screen.Bounds.Width)x$($screen.Bounds.Height)$isPrimary" -ForegroundColor Cyan
    }
} catch {
    Write-Host "⚠️  Error detecting monitors, falling back to 1 monitor" -ForegroundColor Yellow
    $monitorCount = 1
}

# Check prerequisites
Write-Host "🔍 Checking system prerequisites..." -ForegroundColor Cyan

try {
    $nodeVersion = & node --version 2>$null
    Write-Host "✅ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found" -ForegroundColor Red
    exit 1
}

try {
    $npmVersion = & npm --version 2>$null
    Write-Host "✅ npm found: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ npm not found" -ForegroundColor Red
    exit 1
}

try {
    $pythonVersion = & python --version 2>$null
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found" -ForegroundColor Red
    exit 1
}

# Installing dependencies from project root
Write-Host "📦 Installing dependencies..." -ForegroundColor Cyan

Write-Host "  Frontend dependencies..." -ForegroundColor Yellow
& npm install --silent
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Frontend dependencies installation failed" -ForegroundColor Red
    exit 1
}

Write-Host "  Python dependencies..." -ForegroundColor Yellow
& python -m pip install -r desktop-client/requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python dependencies installation failed" -ForegroundColor Red
    exit 1
}

Write-Host "✅ All dependencies installed" -ForegroundColor Green

# Start services
$jobs = @()

# WebSocket Server
Write-Host "🌐 Starting WebSocket server..." -ForegroundColor Cyan
$wsJob = Start-Job -ScriptBlock {
    # Always run from project root to ensure relative paths resolve
    Set-Location $using:ProjectRoot
    # Start Local WebSocket Server for Desktop Streams
    try {
        Write-Host "[INFO] Starting Local WebSocket Server..." -ForegroundColor Cyan
        # Already running from project root via $using:ProjectRoot
        # Updated path to dev subfolder
        & node scripts/dev/local-websocket-server.js
        if ($LASTEXITCODE -ne 0) {
            throw "Local WebSocket Server exited with code $LASTEXITCODE"
        }
    } catch {
        Write-Error "[ERROR] Failed to start Local WebSocket Server: $_"
        exit 1
    }
} -Name "WebSocketServer"
$jobs += $wsJob

Start-Sleep -Seconds 3

# Frontend Server
Write-Host "🎨 Starting frontend development server..." -ForegroundColor Cyan
$frontendJob = Start-Job -ScriptBlock {
    Set-Location $using:ProjectRoot
    # Set PORT environment variable for dev server
    $env:PORT = $using:FrontendPort
    & npm run dev
} -Name "FrontendServer"
$jobs += $frontendJob

Start-Sleep -Seconds 5

# Auto Dual Monitor System (if enabled)
if ($AutoStartMonitors -and -not $SkipDesktopClient) {
    Write-Host "🖥️  Starting Auto Dual Monitor System..." -ForegroundColor Cyan
    $autoMonitorJob = Start-Job -ScriptBlock {
        param($serverUrl)
        Set-Location $using:ProjectRoot
        & python auto-start-dual-monitors.py --server-url $serverUrl
    } -ArgumentList "ws://localhost:$WebSocketPort" -Name "AutoMonitorSystem"
    $jobs += $autoMonitorJob
    
    Start-Sleep -Seconds 5
    Write-Host "✅ Auto Dual Monitor System started" -ForegroundColor Green
}

# Wait for services
Write-Host "⏳ Waiting for service initialization..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Show status
Write-Host ""
Write-Host "🎉 TRAE Unity AI Platform successfully started!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 System status:" -ForegroundColor Yellow
Write-Host "  ✅ WebSocket Server: ws://localhost:$WebSocketPort" -ForegroundColor Cyan
Write-Host "  ✅ Frontend Server: http://localhost:$FrontendPort" -ForegroundColor Cyan
if ($AutoStartMonitors -and -not $SkipDesktopClient) {
    Write-Host "  ✅ Auto Monitor System: $monitorCount monitor(s) detected" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "🌐 Main application: http://localhost:$FrontendPort/" -ForegroundColor Green
Write-Host "📺 Desktop streams: automatically available in the web interface" -ForegroundColor Green
Write-Host ""
Write-Host "💡 Expect $monitorCount monitor stream(s) in the web interface" -ForegroundColor Yellow
Write-Host ""

if ($ShowLogs) {
    Write-Host "📋 Showing logs (Press Ctrl+C to stop)..." -ForegroundColor Yellow
    try {
        while ($true) {
            foreach ($job in $jobs) {
                $output = Receive-Job -Job $job -Keep
                if ($output) {
                    $timestamp = Get-Date -Format "HH:mm:ss"
                    Write-Host "[$timestamp][$($job.Name)] $output" -ForegroundColor Gray
                }
            }
            Start-Sleep -Seconds 2
        }
    } finally {
        Write-Host ""
        Write-Host "🛑 Stopping all services..." -ForegroundColor Red
        $jobs | Stop-Job -PassThru | Remove-Job
        Write-Host "✅ All services stopped!" -ForegroundColor Green
    }
} else {
    Write-Host "ℹ️  Services are running in the background." -ForegroundColor Blue
    Write-Host "📋 Show logs: Get-Job | Receive-Job" -ForegroundColor Cyan
    Write-Host "🛑 Stop services: Get-Job | Stop-Job; Get-Job | Remove-Job" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "🔧 To exit: Press any key..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    
    Write-Host ""
    Write-Host "🛑 Stopping all services..." -ForegroundColor Red
    $jobs | Stop-Job -PassThru | Remove-Job
    Write-Host "✅ All services stopped!" -ForegroundColor Green
}