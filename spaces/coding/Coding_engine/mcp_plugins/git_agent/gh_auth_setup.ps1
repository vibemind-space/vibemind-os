# GitHub CLI Authentication Setup
# Usage: .\gh_auth_setup.ps1

param(
    [string]$EnvFile = ".env"
)

$GH_PATH = "C:\Program Files\GitHub CLI\gh.exe"

# Check if gh is installed
if (-not (Test-Path $GH_PATH)) {
    Write-Host "GitHub CLI not found. Installing..." -ForegroundColor Yellow
    winget install GitHub.cli --accept-package-agreements --accept-source-agreements
    $GH_PATH = "C:\Program Files\GitHub CLI\gh.exe"
}

# Import .env file
function Import-EnvFile {
    param([string]$Path)
    if (Test-Path $Path) {
        Get-Content $Path | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim()
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
        return $true
    }
    return $false
}

# Get token
$token = $null

if (Import-EnvFile $EnvFile) {
    $token = $env:GITHUB_TOKEN
    if ($token) {
        Write-Host "Using GITHUB_TOKEN from $EnvFile" -ForegroundColor Green
    }
}

if (-not $token) {
    # Interactive
    Write-Host "No token found in $EnvFile" -ForegroundColor Yellow
    Write-Host "Please enter your GitHub Personal Access Token:" -ForegroundColor Yellow
    Write-Host "(Create one at: https://github.com/settings/tokens)" -ForegroundColor Cyan
    Write-Host "Required scopes: repo, read:org, workflow" -ForegroundColor Cyan
    $token = Read-Host -Prompt "Token"

    # Save to .env
    $save = Read-Host "Save token to $EnvFile? (y/n)"
    if ($save -eq "y") {
        "GITHUB_TOKEN=$token" | Out-File $EnvFile -Encoding utf8
        Write-Host "Token saved to $EnvFile" -ForegroundColor Green
    }
}

# Authenticate
Write-Host "Authenticating with GitHub..." -ForegroundColor Cyan
$token | & $GH_PATH auth login --with-token

# Verify
Write-Host "`nVerifying authentication..." -ForegroundColor Cyan
& $GH_PATH auth status

Write-Host "`nDone!" -ForegroundColor Green
