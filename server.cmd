@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "%~dp0monitoring\server.py"
) else (
  python "%~dp0monitoring\server.py"
)

pause
