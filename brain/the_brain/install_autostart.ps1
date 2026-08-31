#requires -Version 5.0
<#
Installs a Windows Task Scheduler task that starts the Brain HTTP server
silently at user logon. Idempotent — re-running updates the existing task.

Run from PowerShell (no admin needed for per-user tasks):
    powershell -ExecutionPolicy Bypass -File install_autostart.ps1

To uninstall:
    Unregister-ScheduledTask -TaskName "VibemindBrain" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$taskName = "VibemindBrain"
$launcher = "C:\Users\User\Desktop\Vibemind_V1\vibemind-os\brain\the_brain\launch_brain_silent.vbs"

if (-not (Test-Path $launcher)) {
    throw "Launcher script not found: $launcher"
}

# Remove existing task if present (makes the script idempotent).
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing task '$taskName'..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$launcher`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Starts the Vibemind Brain HTTP server (port 5000) silently at user logon." | Out-Null

Write-Host "Task '$taskName' installed."
Write-Host "It will start Brain automatically at next login."
Write-Host ""
Write-Host "To start Brain RIGHT NOW without logging out:"
Write-Host "    Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""
Write-Host "To check status:"
Write-Host "    Get-ScheduledTask -TaskName '$taskName' | Get-ScheduledTaskInfo"
