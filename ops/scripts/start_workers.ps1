# start_workers.ps1 - Startet alle MCP Agents als gRPC Worker
# Usage: .\start_workers.ps1 [--all | --core | --agent-name]

param(
    [switch]$all,
    [switch]$core,
    [string[]]$agents
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Worker Konfiguration (Name -> Port)
$WorkerConfig = @{
    # Core Agents
    "filesystem" = 50072
    "docker" = 50063
    "redis" = 50066
    "playwright" = 50061
    "git" = 50079

    # Package Management
    "npm" = 50080
    "prisma" = 50081

    # Database
    "postgres" = 50082
    "supabase" = 50067
    "qdrant" = 50083

    # Search & Web
    "brave-search" = 50073
    "tavily" = 50078
    "fetch" = 50074

    # Utility
    "memory" = 50071
    "time" = 50068
    "context7" = 50065
    "taskmanager" = 50069
    "desktop" = 50064
    "windows-core" = 50070
    "github" = 50062
    "n8n" = 50076
    "supermemory" = 50084
}

$CoreAgents = @("filesystem", "docker", "redis", "playwright", "git", "postgres")

function Start-Worker {
    param(
        [string]$Name,
        [int]$Port
    )

    $AgentPath = Join-Path $ScriptDir "$Name\agent.py"

    if (-not (Test-Path $AgentPath)) {
        Write-Host "  [SKIP] $Name - agent.py nicht gefunden" -ForegroundColor Yellow
        return
    }

    Write-Host "  [START] $Name auf Port $Port..." -ForegroundColor Cyan

    $Process = Start-Process -FilePath "python" `
        -ArgumentList "$AgentPath", "--grpc", "--grpc-port", $Port `
        -WorkingDirectory $ScriptDir `
        -PassThru `
        -WindowStyle Hidden

    if ($Process) {
        Write-Host "    PID: $($Process.Id)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "   MCP Agent gRPC Worker Launcher" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

# Bestimme welche Agents gestartet werden sollen
$AgentsToStart = @()

if ($all) {
    $AgentsToStart = $WorkerConfig.Keys
    Write-Host "Starte ALLE Workers ($($AgentsToStart.Count))..." -ForegroundColor Yellow
} elseif ($core) {
    $AgentsToStart = $CoreAgents
    Write-Host "Starte CORE Workers ($($AgentsToStart.Count))..." -ForegroundColor Yellow
} elseif ($agents.Count -gt 0) {
    $AgentsToStart = $agents
    Write-Host "Starte ausgewählte Workers ($($AgentsToStart.Count))..." -ForegroundColor Yellow
} else {
    # Default: Core Agents
    $AgentsToStart = $CoreAgents
    Write-Host "Starte CORE Workers (default, $($AgentsToStart.Count))..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Optionen:" -ForegroundColor Gray
    Write-Host "  -all        Alle Workers starten" -ForegroundColor Gray
    Write-Host "  -core       Nur Core Workers (default)" -ForegroundColor Gray
    Write-Host "  -agents x,y Spezifische Workers" -ForegroundColor Gray
}

Write-Host ""

# Workers starten
foreach ($agent in $AgentsToStart) {
    if ($WorkerConfig.ContainsKey($agent)) {
        Start-Worker -Name $agent -Port $WorkerConfig[$agent]
    } else {
        Write-Host "  [WARN] Unbekannter Agent: $agent" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Workers gestartet!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Zum Stoppen: Get-Process python | Stop-Process" -ForegroundColor Gray
Write-Host ""
