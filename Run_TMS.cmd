@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Python environment missing. Install requirements first; see README.md.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m tms_pc.main
