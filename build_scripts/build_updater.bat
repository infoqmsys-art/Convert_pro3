@echo off
chcp 65001 > nul
echo ========================================
echo update.exe 빌드
echo ========================================
echo.

powershell -ExecutionPolicy Bypass -File build_updater.ps1

pause
