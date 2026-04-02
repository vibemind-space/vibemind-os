# Desktop Client Auto-Start Setup Script
# Run this script to automatically configure the desktop client to start on Windows boot

Write-Host "🚀 Desktop Client Auto-Start Setup" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""

# Get the current directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VBSPath = Join-Path $ScriptDir "start-desktop-client-hidden.vbs"
$BATPath = Join-Path $ScriptDir "start-desktop-client.bat"

# Check if files exist
if (-not (Test-Path $VBSPath)) {
    Write-Host "❌ Error: start-desktop-client-hidden.vbs not found" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $BATPath)) {
    Write-Host "❌ Error: start-desktop-client.bat not found" -ForegroundColor Red
    exit 1
}

Write-Host "📋 Found required files:" -ForegroundColor Green
Write-Host "   - $VBSPath" -ForegroundColor Gray
Write-Host "   - $BATPath" -ForegroundColor Gray
Write-Host ""

# Prompt user for setup method
Write-Host "Choose auto-start method:" -ForegroundColor Yellow
Write-Host "  1. Startup Folder (easiest, starts on user login)" -ForegroundColor White
Write-Host "  2. Task Scheduler (recommended, more control)" -ForegroundColor White
Write-Host "  3. Both (maximum reliability)" -ForegroundColor White
Write-Host "  4. Cancel" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Enter choice (1-4)"

switch ($choice) {
    "1" {
        # Startup Folder method
        Write-Host ""
        Write-Host "📂 Creating startup shortcut..." -ForegroundColor Cyan

        $StartupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
        $ShortcutPath = Join-Path $StartupFolder "Desktop Client.lnk"

        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $VBSPath
        $Shortcut.WorkingDirectory = $ScriptDir
        $Shortcut.Description = "Desktop Client Auto-Start"
        $Shortcut.Save()

        Write-Host "✅ Startup shortcut created at:" -ForegroundColor Green
        Write-Host "   $ShortcutPath" -ForegroundColor Gray
    }

    "2" {
        # Task Scheduler method
        Write-Host ""
        Write-Host "📅 Creating scheduled task..." -ForegroundColor Cyan

        $Action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$VBSPath`""
        $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0)

        try {
            Register-ScheduledTask -TaskName "Desktop Client Auto-Start" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
            Write-Host "✅ Scheduled task created: Desktop Client Auto-Start" -ForegroundColor Green
        } catch {
            Write-Host "❌ Error creating scheduled task: $($_.Exception.Message)" -ForegroundColor Red
            exit 1
        }
    }

    "3" {
        # Both methods
        Write-Host ""
        Write-Host "📂 Creating startup shortcut..." -ForegroundColor Cyan

        $StartupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
        $ShortcutPath = Join-Path $StartupFolder "Desktop Client.lnk"

        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $VBSPath
        $Shortcut.WorkingDirectory = $ScriptDir
        $Shortcut.Description = "Desktop Client Auto-Start"
        $Shortcut.Save()

        Write-Host "✅ Startup shortcut created" -ForegroundColor Green

        Write-Host ""
        Write-Host "📅 Creating scheduled task..." -ForegroundColor Cyan

        $Action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$VBSPath`""
        $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0)

        try {
            Register-ScheduledTask -TaskName "Desktop Client Auto-Start" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
            Write-Host "✅ Scheduled task created" -ForegroundColor Green
        } catch {
            Write-Host "❌ Error creating scheduled task: $($_.Exception.Message)" -ForegroundColor Red
        }
    }

    "4" {
        Write-Host ""
        Write-Host "❌ Setup cancelled" -ForegroundColor Yellow
        exit 0
    }

    default {
        Write-Host ""
        Write-Host "❌ Invalid choice" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "🎉 Auto-start setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Yellow
Write-Host "   1. Edit start-desktop-client.bat to configure USER_ID and FRIENDLY_NAME" -ForegroundColor White
Write-Host "   2. Log out and log back in (or restart) to test auto-start" -ForegroundColor White
Write-Host "   3. Check Task Manager > Processes for python.exe to verify it's running" -ForegroundColor White
Write-Host ""
Write-Host "💡 To test now without restarting:" -ForegroundColor Cyan
Write-Host "   cd desktop-client" -ForegroundColor Gray
Write-Host "   .\start-desktop-client.bat" -ForegroundColor Gray
Write-Host ""
