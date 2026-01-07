@echo off
chcp 65001 > nul
echo ========================================
echo update.exe 빌드
echo ========================================
echo.

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0build_updater.ps1"

pause
