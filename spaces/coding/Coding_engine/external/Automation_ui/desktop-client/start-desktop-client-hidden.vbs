Set WshShell = CreateObject("WScript.Shell")
' Get the directory where this script is located
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
' Run the batch file hidden (0 = hidden window, False = don't wait for completion)
WshShell.Run chr(34) & strPath & "\start-desktop-client.bat" & Chr(34), 0, False
Set WshShell = Nothing
