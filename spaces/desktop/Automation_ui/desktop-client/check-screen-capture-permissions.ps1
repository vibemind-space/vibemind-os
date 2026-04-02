# Check and Enable Screen Capture Permissions
# Run this script to diagnose and fix screen capture issues

Write-Host "[*] Checking Windows Screen Capture Permissions..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    Write-Host "[OK] Running as Administrator" -ForegroundColor Green
} else {
    Write-Host "[WARN] Not running as Administrator - some checks may be limited" -ForegroundColor Yellow
    Write-Host "       Right-click and 'Run as Administrator' for full diagnostics" -ForegroundColor Yellow
}
Write-Host ""

# Check monitor status
Write-Host "[*] Checking Monitor Configuration..." -ForegroundColor Cyan
Add-Type -AssemblyName System.Windows.Forms
$screens = [System.Windows.Forms.Screen]::AllScreens

Write-Host "Found $($screens.Count) monitors:" -ForegroundColor Green
for ($i = 0; $i -lt $screens.Count; $i++) {
    $screen = $screens[$i]
    Write-Host "  Monitor $i`: $($screen.Bounds.Width)x$($screen.Bounds.Height) at ($($screen.Bounds.X), $($screen.Bounds.Y))" -ForegroundColor White
    if ($screen.Primary) {
        Write-Host "    (Primary Monitor)" -ForegroundColor Green
    }
}
Write-Host ""

# Check Privacy Settings for Screen Capture
Write-Host "[*] Checking Privacy Settings..." -ForegroundColor Cyan
$screencapturePath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\graphicsCaptureProgrammatic"

if (Test-Path $screencapturePath) {
    $captureValue = Get-ItemProperty -Path $screencapturePath -Name "Value" -ErrorAction SilentlyContinue
    if ($captureValue) {
        switch ($captureValue.Value) {
            "Allow" { Write-Host "[OK] Screen Capture: Allowed" -ForegroundColor Green }
            "Deny" {
                Write-Host "[ERROR] Screen Capture: DENIED" -ForegroundColor Red
                Write-Host "        Fix: Settings > Privacy > Screenshots > Allow apps to take screenshots" -ForegroundColor Yellow
            }
            "Prompt" { Write-Host "[WARN] Screen Capture: Will prompt for permission" -ForegroundColor Yellow }
        }
    }
} else {
    Write-Host "[WARN] Screen Capture privacy setting not found (may be OK on older Windows)" -ForegroundColor Yellow
}
Write-Host ""

# Check if monitors are active
Write-Host "[*] Checking Monitor Power State..." -ForegroundColor Cyan
$monitors = Get-WmiObject -Namespace root\wmi -Class WmiMonitorBasicDisplayParams -ErrorAction SilentlyContinue
if ($monitors) {
    Write-Host "[OK] Found $($monitors.Count) active monitor(s)" -ForegroundColor Green
} else {
    Write-Host "[WARN] Could not query monitor power state" -ForegroundColor Yellow
}
Write-Host ""

# Test Python MSS library
Write-Host "[*] Testing Python MSS Screen Capture..." -ForegroundColor Cyan
$pythonTest = @"
import mss
import sys

try:
    with mss.mss() as sct:
        monitors = sct.monitors
        print('[OK] MSS found ' + str(len(monitors)-1) + ' monitors (plus virtual desktop)')

        for i, monitor in enumerate(monitors[1:], 1):
            print('  Monitor ' + str(i) + ': ' + str(monitor))

            # Try to capture each monitor
            try:
                screenshot = sct.grab(monitor)

                # Convert raw bytes to RGB values
                import struct
                width = screenshot.width
                height = screenshot.height
                raw = screenshot.bgra

                # Count black pixels
                total_pixels = width * height
                black_pixels = 0

                for y in range(height):
                    for x in range(width):
                        offset = (y * width + x) * 4
                        b = raw[offset]
                        g = raw[offset + 1]
                        r = raw[offset + 2]

                        if r < 10 and g < 10 and b < 10:
                            black_pixels += 1

                black_percent = (black_pixels / total_pixels) * 100

                if black_percent > 90:
                    print('  [WARN] Monitor ' + str(i) + ' captured ' + str(round(black_percent, 1)) + '% black pixels!')
                    print('         This monitor may be sleeping or showing protected content')
                else:
                    print('  [OK] Monitor ' + str(i) + ' capture OK (' + str(round(black_percent, 1)) + '% black)')
            except Exception as e:
                print('  [ERROR] Monitor ' + str(i) + ' capture failed: ' + str(e))

except Exception as e:
    print('[ERROR] MSS test failed: ' + str(e))
    sys.exit(1)
"@

$pythonTest | python - 2>&1
Write-Host ""

# Recommendations
Write-Host "[*] Recommendations:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. [CHECK] Enable Screen Capture in Privacy Settings:" -ForegroundColor Yellow
Write-Host "   Settings > Privacy and Security > Screenshots" -ForegroundColor White
Write-Host "   OR Settings > Privacy > Screen Capture (older Windows)" -ForegroundColor White
Write-Host ""
Write-Host "2. [CHECK] Wake up all monitors:" -ForegroundColor Yellow
Write-Host "   Move mouse to each monitor to ensure they are active" -ForegroundColor White
Write-Host ""
Write-Host "3. [CHECK] Close DRM/protected content:" -ForegroundColor Yellow
Write-Host "   Close Netflix, Prime Video, or any video with HDCP protection" -ForegroundColor White
Write-Host ""
Write-Host "4. [CHECK] Run Python client with appropriate permissions:" -ForegroundColor Yellow
Write-Host "   cd desktop-client" -ForegroundColor White
Write-Host "   python dual_screen_capture_client.py" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"
