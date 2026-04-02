@echo off
REM Wrapper to run playwright agent with venv Python
cd /d "%~dp0"
set VENV_PYTHON=%~dp0..\..\..\..\.venv\Scripts\python.exe
"%VENV_PYTHON%" "%~dp0agent.py" %*
