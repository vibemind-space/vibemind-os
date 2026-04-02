# ==============================================================================
# FULL AUTONOMOUS RUN - Standard Configuration (PowerShell)
# ==============================================================================
# Aktiviert alle Features:
# - --autonomous: 100% Tests, 0 Fehler, 1 Stunde Timeout
# - --continuous-sandbox --enable-vnc: 30-Sekunden Docker Test-Zyklen mit VNC
# - --enable-validation: Test-Generierung + Debug Engine
# - --dashboard: Real-time Agent Monitoring
# ==============================================================================

param(
    [string]$Requirements = "Data/todo_app_requirements.json",
    [string]$TechStack = "Data/todo_app_tech_stack.json",
    [string]$OutputDir = ""
)

# Generate output dir if not provided
if (-not $OutputDir) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputDir = "./output_todo_app_$timestamp"
}

# Check if requirements file exists
if (-not (Test-Path $Requirements)) {
    Write-Host "ERROR: Requirements file not found: $Requirements" -ForegroundColor Red
    exit 1
}

# Check if tech stack file exists
$techStackArg = ""
if (Test-Path $TechStack) {
    $techStackArg = "--tech-stack `"$TechStack`""
} else {
    Write-Host "WARNING: Tech stack file not found: $TechStack" -ForegroundColor Yellow
    Write-Host "Running without tech stack configuration..."
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  FULL AUTONOMOUS CODE GENERATION" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Requirements:    $Requirements"
Write-Host "  Tech Stack:      $TechStack"
Write-Host "  Output Dir:      $OutputDir"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Features Enabled:" -ForegroundColor Green
Write-Host "  √ Autonomous Mode (100% tests, 0 errors, 1h timeout)" -ForegroundColor Green
Write-Host "  √ Continuous Sandbox Testing (30s cycles)" -ForegroundColor Green
Write-Host "  √ VNC Streaming (http://localhost:6080/vnc.html)" -ForegroundColor Green
Write-Host "  √ Validation Team (Test Generation + Debug Engine)" -ForegroundColor Green
Write-Host "  √ Dashboard (http://localhost:8080)" -ForegroundColor Green
Write-Host "  √ Live Preview (http://localhost:5173)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Build command arguments
$args = @(
    "run_society_hybrid.py",
    "`"$Requirements`"",
    "--output-dir", "`"$OutputDir`"",
    "--autonomous",
    "--continuous-sandbox",
    "--enable-vnc",
    "--vnc-port", "6080",
    "--enable-validation",
    "--validation-team",
    "--test-framework", "vitest",
    "--validation-docker",
    "--dashboard",
    "--dashboard-port", "8080",
    "--shell-stream",
    "--max-iterations", "200",
    "--max-time", "3600"
)

# Add tech stack if available
if ($techStackArg) {
    $args += "--tech-stack"
    $args += "`"$TechStack`""
}

# Execute
$cmd = "python " + ($args -join " ")
Write-Host "Running: $cmd"
Write-Host ""

python @args

# Capture exit code
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "  √ GENERATION COMPLETE" -ForegroundColor Green
    Write-Host "  Output: $OutputDir" -ForegroundColor Green
} else {
    Write-Host "  X GENERATION FAILED (Exit Code: $exitCode)" -ForegroundColor Red
}
Write-Host "============================================================" -ForegroundColor Cyan

exit $exitCode
