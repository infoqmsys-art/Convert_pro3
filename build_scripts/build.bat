@echo off
chcp 65001 > nul
echo ========================================
echo Convert Pro 3 빌드
echo ========================================
echo.

powershell -ExecutionPolicy Bypass -File build.ps1

pause
