' Silent launcher for Brain HTTP server.
' Called from Windows Task Scheduler at user logon.
' Starts python start_server.py with no visible window, logs to temp.

Set WshShell = CreateObject("WScript.Shell")
logPath = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Temp\brain_server.log")
scriptDir = "C:\Users\User\Desktop\Vibemind_V1\vibemind-os\brain\the_brain"

' Change working directory, then exec python with full redirection.
' 0 = hidden window, False = do not wait for exit.
WshShell.CurrentDirectory = scriptDir
WshShell.Run "cmd /c python start_server.py > """ & logPath & """ 2>&1", 0, False
