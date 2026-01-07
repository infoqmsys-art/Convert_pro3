@echo off
chcp 65001 > nul
echo ========================================
echo Convert Pro 3 빌드
echo ========================================
echo.

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0build.ps1"

pause
