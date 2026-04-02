# Automated Setup Script for Desktop Client Permissions
# This script sets up all necessary permissions for screen capture

#Requires -RunAsAdministrator

Write-Host "[*] Desktop Client Permission Setup" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

# Function to set registry value safely
function Set-RegistryValue {
    param($Path, $Name, $Value, $Type)

    try {
        if (!(Test-Path $Path)) {
            New-Item -Path $Path -Force | Out-Null
        }
        Set-ItemProperty -Path $Path -Name $Name -Value $Value -Type $Type -Force
        return $true
    } catch {
        Write-Host "[ERROR] Failed to set $Path\$Name`: $_" -ForegroundColor Red
        return $false
    }
}

# 1. Enable Screen Capture globally (Windows 10 1903+)
Write-Host "[STEP 1] Enabling Screen Capture permissions..." -ForegroundColor Yellow

# Allow screen capture for all apps
$capturePath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\graphicsCaptureProgrammatic"
if (Set-RegistryValue -Path $capturePath -Name "Value" -Value "Allow" -Type String) {
    Write-Host "         [OK] Screen capture enabled globally" -ForegroundColor Green
}

# Also set for current user
$userCapturePath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\graphicsCaptureProgrammatic"
if (Set-RegistryValue -Path $userCapturePath -Name "Value" -Value "Allow" -Type String) {
    Write-Host "         [OK] Screen capture enabled for current user" -ForegroundColor Green
}

Write-Host ""

# 2. Disable monitor power saving during capture
Write-Host "[STEP 2] Configuring power settings..." -ForegroundColor Yellow
try {
    # Prevent monitor sleep when plugged in
    powercfg /change monitor-timeout-ac 0
    Write-Host "         [OK] Disabled monitor sleep when plugged in" -ForegroundColor Green
} catch {
    Write-Host "         [WARN] Could not modify power settings" -ForegroundColor Yellow
}

Write-Host ""

# 3. Create startup task (optional)
Write-Host "[STEP 3] Setting up auto-start (optional)..." -ForegroundColor Yellow
$createTask = Read-Host "         Create Windows Task to auto-start desktop client on login? (Y/N)"

if ($createTask -eq "Y" -or $createTask -eq "y") {
    $scriptPath = Join-Path $PSScriptRoot "dual_screen_capture_client.py"
    $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Path

    if ($pythonPath -and (Test-Path $scriptPath)) {
        $action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$scriptPath`"" -WorkingDirectory $PSScriptRoot
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

        try {
            Register-ScheduledTask -TaskName "DesktopCaptureClient" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
            Write-Host "         [OK] Auto-start task created" -ForegroundColor Green
            Write-Host "         Desktop client will start automatically on login" -ForegroundColor White
        } catch {
            Write-Host "         [ERROR] Failed to create task: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "         [ERROR] Could not find Python or script path" -ForegroundColor Red
    }
}

Write-Host ""

# 4. Test capture with diagnostics
Write-Host "[STEP 4] Running capture test..." -ForegroundColor Yellow

$testScript = @"
import mss
import mss.tools
import os

print('Testing screen capture...')
with mss.mss() as sct:
    monitors = sct.monitors[1:]  # Skip virtual desktop

    for i, monitor in enumerate(monitors, 1):
        try:
            # Capture monitor
            img = sct.grab(monitor)

            # Save test screenshot
            output_path = f'test_monitor_{i}.png'
            mss.tools.to_png(img.rgb, img.size, output=output_path)

            # Check if mostly black
            width = img.width
            height = img.height
            raw = img.bgra

            total = width * height
            black = 0

            for y in range(height):
                for x in range(width):
                    offset = (y * width + x) * 4
                    b = raw[offset]
                    g = raw[offset + 1]
                    r = raw[offset + 2]

                    if r < 10 and g < 10 and b < 10:
                        black += 1

            black_pct = (black / total) * 100

            if black_pct > 90:
                print(f'[WARN] Monitor {i}: {black_pct:.1f}% black - may be sleeping or protected')
            else:
                print(f'[OK] Monitor {i}: Capture OK ({black_pct:.1f}% black)')
                print(f'     Saved to: {os.path.abspath(output_path)}')

        except Exception as e:
            print(f'[ERROR] Monitor {i}: Capture failed - {e}')
"@

$testScript | python -
Write-Host ""

# Summary
Write-Host "[*] Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "[OK] Screen capture permissions enabled" -ForegroundColor White
Write-Host "[OK] Power settings configured" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Restart your computer (recommended)" -ForegroundColor White
Write-Host "2. Ensure all monitors are powered on and awake" -ForegroundColor White
Write-Host "3. Run: python dual_screen_capture_client.py" -ForegroundColor White
Write-Host ""
Write-Host "If you still have issues:" -ForegroundColor Yellow
Write-Host "  - Run: .\check-screen-capture-permissions.ps1 for diagnostics" -ForegroundColor White
Write-Host "  - Check if DRM content (Netflix, etc.) is open on Monitor 2" -ForegroundColor White
Write-Host "  - Try moving a window to Monitor 2 to wake it up" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"
