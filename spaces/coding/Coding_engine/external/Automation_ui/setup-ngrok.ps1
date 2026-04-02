# Ngrok Setup Script for External Access
# This script downloads and configures ngrok for instant external access

Write-Host "Setting up Ngrok for external access..." -ForegroundColor Green

# Download ngrok
$ngrokUrl = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
$ngrokZip = "$env:TEMP\ngrok.zip"
$ngrokDir = "$env:USERPROFILE\ngrok"

Write-Host "Downloading ngrok..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $ngrokUrl -OutFile $ngrokZip

Write-Host "Extracting ngrok..." -ForegroundColor Yellow
if (!(Test-Path $ngrokDir)) {
    New-Item -ItemType Directory -Path $ngrokDir
}
Expand-Archive -Path $ngrokZip -DestinationPath $ngrokDir -Force

# Add to PATH
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$ngrokDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$ngrokDir", "User")
    Write-Host "Added ngrok to PATH" -ForegroundColor Green
}

Write-Host "Ngrok installed successfully!" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Sign up at https://ngrok.com for a free account" -ForegroundColor White
Write-Host "2. Get your auth token from the dashboard" -ForegroundColor White
Write-Host "3. Run: ngrok config add-authtoken YOUR_TOKEN" -ForegroundColor White
Write-Host "4. Run: ngrok http 8080 (for web app)" -ForegroundColor White
Write-Host "5. Run: ngrok tcp 8084 (for websocket)" -ForegroundColor White

# Clean up
Remove-Item $ngrokZip -Force