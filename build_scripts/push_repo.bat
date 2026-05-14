@echo off
REM Launcher only (ASCII) -- avoids cmd.exe UTF-8 / parenthesis parse bugs.
REM Logic: push_repo.ps1 (same folder)
setlocal
set "_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%_PS%" set "_PS=powershell.exe"

"%_PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0push_repo.ps1" %*

set "EXITCODE=%ERRORLEVEL%"
if "%EXITCODE%"=="0" exit /b 0
echo ERROR exit %EXITCODE%
pause
exit /b %EXITCODE%
