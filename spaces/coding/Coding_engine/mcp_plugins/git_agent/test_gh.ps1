# Test GitHub REST API for repo create/delete
$env:PATH += ";C:\Program Files\GitHub CLI"

# Load .env
Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

$token = $env:GITHUB_TOKEN
$headers = @{
    "Authorization" = "Bearer $token"
    "Accept" = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

# Create repo via REST API
Write-Host "Creating test repo via REST API..." -ForegroundColor Cyan
$body = @{
    name = "test-mcp-repo"
    private = $true
    description = "Test repo for MCP - will be deleted"
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method Post -Headers $headers -Body $body -ContentType "application/json"
    Write-Host "Repo created: $($response.html_url)" -ForegroundColor Green
} catch {
    Write-Host "Error creating repo: $($_.Exception.Message)" -ForegroundColor Red
    $_.ErrorDetails.Message | ConvertFrom-Json | Format-List
}

# List repos
Write-Host "`nListing repos..." -ForegroundColor Cyan
gh repo list --limit 5

# Delete repo via REST API
Write-Host "`nDeleting test repo via REST API..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "https://api.github.com/repos/Flissel/test-mcp-repo" -Method Delete -Headers $headers
    Write-Host "Repo deleted!" -ForegroundColor Green
} catch {
    Write-Host "Error deleting repo: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nDone!" -ForegroundColor Green
